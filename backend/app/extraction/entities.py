"""Technical entity extraction with source traceability.

Every extracted entity records the page, block, section, the exact snippet it
came from, character offsets, a bounding box (word-level when available) and
a confidence that combines pattern certainty with OCR confidence.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict

from ..ingest.types import RawBlock, RawPage
from ..ocr.postprocess import awg_ambiguity, digit_alternatives
from . import patterns as P


@dataclass
class ExtractedEntity:
    entity_type: str
    value: float | None
    unit: str | None
    value_text: str
    raw_text: str
    page_number: int
    block_index: int
    snippet: str
    char_start: int
    char_end: int
    bbox: list[float]
    section: str | None = None
    qualifier: str | None = None
    application: str | None = None
    circuit: str | None = None
    equipment: str | None = None
    equipment_model: str | None = None
    device_type: str | None = None
    confidence: float = 0.9
    ocr_confidence: float | None = None
    is_critical: bool = False
    flags: list[dict] = field(default_factory=list)
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


# --------------------------------------------------------------------------- helpers


_SENT_BOUNDARY = re.compile(r"(?<=[.;!?])\s+(?=[A-Z(\u2022•\-–\d])|\n(?=\s*(?:[•\-–*]|\d{1,2}[.)]|[A-Z][a-z]+:)\s)|(?<=[.:;])\n")


def _sentence_window(text: str, start: int, end: int, radius: int = 220, table: bool = False) -> tuple[str, int, int]:
    """Return the sentence (or table row) containing [start, end) plus offsets.

    Wrapped lines inside a paragraph are joined; sentence punctuation, list
    bullets and table rows act as boundaries.
    """
    if table:
        ls = text.rfind("\n", 0, start) + 1
        le = text.find("\n", end)
        le = le if le != -1 else len(text)
        return text[ls:le].strip(), ls, le
    left = max(0, start - radius)
    right = min(len(text), end + radius)
    ls, le = left, right
    for m in _SENT_BOUNDARY.finditer(text, left, right):
        if m.end() <= start:
            ls = m.end()
        elif m.start() >= end:
            le = m.start()
            break
    seg = text[ls:le].replace("\n", " ")
    seg = re.sub(r"\s+", " ", seg).strip()
    return seg, ls, le


def _norm_token(t: str) -> str:
    return re.sub(r"[^\w/°²Ω.]+", "", t).lower()


def _locate_words(words: list[dict] | None, match_text: str, expected_ratio: float) -> tuple[list[float] | None, float | None]:
    """Find the OCR/embedded words that make up ``match_text``. Returns (bbox, min_conf)."""
    if not words:
        return None, None
    tokens = [_norm_token(t) for t in match_text.split() if _norm_token(t)]
    if not tokens:
        return None, None
    norm_words = [_norm_token(w["t"]) for w in words]
    candidates: list[tuple[int, int]] = []
    n = len(words)
    for i in range(n):
        j = i
        k = 0
        while j < n and k < len(tokens):
            nw, tk = norm_words[j], tokens[k]
            if not nw:
                j += 1
                continue
            digits = any(ch.isdigit() for ch in tk)
            if nw == tk or (len(tk) >= (2 if digits else 4) and tk in nw) or (len(nw) >= (2 if digits else 4) and nw in tk):
                j += 1
                k += 1
            elif k > 0 and (tk + tokens[k + 1] if k + 1 < len(tokens) else None) == nw:
                j += 1
                k += 2
            else:
                break
        if k == len(tokens):
            candidates.append((i, j))
    if not candidates:
        # Fall back to first token only (the number) to at least highlight the value.
        for i, nw in enumerate(norm_words):
            if nw == tokens[0]:
                candidates.append((i, i + 1))
        if not candidates:
            return None, None
    target = expected_ratio * n
    i, j = min(candidates, key=lambda c: abs(c[0] - target))
    span = words[i:j]
    bbox = [
        min(w["bbox"][0] for w in span),
        min(w["bbox"][1] for w in span),
        max(w["bbox"][2] for w in span),
        max(w["bbox"][3] for w in span),
    ]
    conf = min(float(w.get("c", 1.0)) for w in span)
    return bbox, conf


_GENERIC_PENALTY = {"nominal": 6, "required": 4, "recommended": 4, "operating": 2}
_CLAUSE_LEFT = re.compile(r"[;()\[\],]|(?<=[.!?])\s")
_CLAUSE_RIGHT = re.compile(r"[;()\[\],.!?]")


def _clause_bounds(context: str, pos: int) -> tuple[int, int]:
    left = 0
    for m in _CLAUSE_LEFT.finditer(context, 0, pos):
        left = m.end()
    right = len(context)
    m = _CLAUSE_RIGHT.search(context, pos)
    if m:
        right = m.start()
    return left, right


def _qualifiers(context: str, pos: int | None = None, window: int = 70) -> list[str]:
    """Qualifier keywords for the value at ``pos`` in ``context``.

    Keywords inside the same clause as the value are preferred; within the
    clause a specific qualifier (continuous, peak, charging...) beats a generic
    one (nominal, required, recommended) and nearer keywords beat farther ones.
    Outside the clause, plain distance within ``window`` applies.
    """
    if pos is None:
        return [q for q, pat in P.QUALIFIERS if pat.search(context)]
    cl, cr = _clause_bounds(context, pos)
    in_clause: list[tuple[float, str]] = []
    nearby: list[tuple[float, str]] = []
    for q, pat in P.QUALIFIERS:
        best_clause = None
        best_near = None
        for m in pat.finditer(context):
            d = (pos - m.end()) if m.end() <= pos else (m.start() - pos) + 3
            if cl <= m.start() and m.end() <= cr + 1:
                score = _GENERIC_PENALTY.get(q, 0) * 10 + d
                if best_clause is None or score < best_clause:
                    best_clause = score
            elif d <= window:
                score = _GENERIC_PENALTY.get(q, 0) + d
                if best_near is None or score < best_near:
                    best_near = score
        if best_clause is not None:
            in_clause.append((best_clause, q))
        elif best_near is not None:
            nearby.append((best_near, q))
    in_clause.sort()
    nearby.sort()
    return [q for _, q in in_clause] + [q for _, q in nearby]


def _primary_qualifier(quals: list[str], entity_type: str) -> str | None:
    """Closest qualifier wins; type priorities only break near-ties (handled by caller order)."""
    if not quals:
        return None
    priority = {
        "current": ["short_circuit", "surge", "peak", "continuous", "maximum", "minimum", "idle", "charging", "input", "output", "nominal", "recommended", "required"],
        "voltage": ["cutoff", "charging", "minimum", "maximum", "input", "output", "nominal", "operating"],
        "fuse": ["required", "recommended", "maximum", "minimum", "nominal"],
        "breaker": ["required", "recommended", "maximum", "minimum", "nominal"],
        "power": ["continuous", "peak", "surge", "maximum", "nominal", "input", "output", "idle"],
        "temperature": ["operating", "storage", "charging", "derating", "maximum", "minimum", "cutoff"],
        "torque": ["maximum", "recommended", "required"],
        "wire_size": ["minimum", "recommended", "required", "maximum"],
    }
    allowed = priority.get(entity_type)
    if allowed is None:
        return quals[0]
    for q in quals:  # nearest first
        if q in allowed:
            return q
    return quals[0]


def _circuit(context: str) -> str | None:
    dc = bool(P.CIRCUIT_DC.search(context))
    ac = bool(P.CIRCUIT_AC.search(context))
    ctl = bool(P.CIRCUIT_CONTROL.search(context))
    if ctl and not (dc or ac):
        return "control"
    if dc and not ac:
        return "dc"
    if ac and not dc:
        return "ac"
    if dc and ac:
        return "dc" if re.search(r"\bVDC\b|\bbattery\b", context, re.I) else "ac/dc"
    return None


def _application(context: str, before_text: str, table_row_label: str | None) -> str | None:
    if table_row_label:
        return table_row_label[:120]
    for label, pat in P.APPLICATION_PHRASES:
        if pat.search(context):
            return label
    # Noun phrase immediately preceding the value on the same line, e.g. "Battery cable: 4/0 AWG".
    m = re.search(r"([A-Za-z][A-Za-z /()\-]{2,60}?)\s*[:=\-–]\s*$", before_text)
    if m:
        return m.group(1).strip()[:120]
    return None


def _equipment(context: str) -> tuple[str | None, str | None]:
    equip = None
    for label, pat in P.EQUIPMENT_TERMS:
        if pat.search(context):
            equip = label
            break
    model = None
    mm = P.MODEL_RE.search(context)
    if mm:
        model = mm.group(1)
    return equip, model


def _table_row_label(block: RawBlock, char_start: int) -> tuple[str | None, str | None]:
    """For table blocks, return (row label, column header) for the cell containing char_start."""
    if not block.table:
        return None, None
    rows = block.table.get("rows") or []
    text = block.text
    line_idx = text.count("\n", 0, char_start)
    if line_idx >= len(rows):
        return None, None
    row = rows[line_idx]
    line_start = text.rfind("\n", 0, char_start) + 1
    col_offset = char_start - line_start
    # Column index by walking " | " separators.
    pos = 0
    col = 0
    for c_i, cell in enumerate(row):
        cell_len = len(cell)
        if pos <= col_offset < pos + cell_len + 3:
            col = c_i
            break
        pos += cell_len + 3
    label = None
    for cell in row:
        if cell and not re.match(r"^\s*-?\d", cell):
            label = cell.replace("\n", " ").strip()
            break
    header = None
    if rows and line_idx > 0 and col < len(rows[0]):
        header = rows[0][col].replace("\n", " ").strip() or None
    return label, header


# --------------------------------------------------------------------------- extraction


def extract_entities(pages: list[RawPage]) -> list[ExtractedEntity]:
    entities: list[ExtractedEntity] = []
    for page in pages:
        for b_idx, block in enumerate(page.blocks):
            if block.block_type in ("header", "footer", "page_number"):
                continue
            entities.extend(_extract_from_block(page, b_idx, block))
    _dedupe(entities)
    return entities


def _base_entity(page: RawPage, b_idx: int, block: RawBlock, m: re.Match, entity_type: str, value, unit, value_text, raw_text) -> ExtractedEntity:
    text = block.text
    start, end = m.start(), m.end()
    snippet, s0, s1 = _sentence_window(text, start, end, table=bool(block.table))
    ratio = start / max(1, len(text))
    wbbox, wconf = _locate_words(block.words, raw_text, ratio)
    bbox = wbbox or list(block.bbox)
    ocr_conf = None
    if block.source == "ocr":
        ocr_conf = wconf if wconf is not None else block.confidence
    row_label, col_header = _table_row_label(block, start)
    context = snippet
    prefix_len = 0
    if col_header:
        context = f"{col_header} {context}"
        prefix_len = len(col_header) + 1
    local_pos = prefix_len + len(re.sub(r"\s+", " ", text[s0:start].replace("\n", " ")).lstrip())
    quals = _qualifiers(context, local_pos)
    before = text[s0:start]
    ent = ExtractedEntity(
        entity_type=entity_type,
        value=value,
        unit=unit,
        value_text=value_text,
        raw_text=raw_text,
        page_number=page.page_number,
        block_index=b_idx,
        snippet=snippet[:400],
        char_start=start,
        char_end=end,
        bbox=[round(v, 2) for v in bbox],
        section=block.section,
        qualifier=_primary_qualifier(quals, entity_type),
        application=_application(context, before, row_label),
        circuit=_circuit(context),
        ocr_confidence=round(ocr_conf, 3) if ocr_conf is not None else None,
        is_critical=entity_type in P.SAFETY_CRITICAL_TYPES,
    )
    ent.equipment, ent.equipment_model = _equipment(context)
    if ent.equipment in ("fuse", "circuit breaker", "relay", "contactor", "busbar", "shunt") and entity_type not in ("fuse", "breaker", "equipment"):
        ent.equipment = None
    ent.extra["qualifiers"] = quals
    if col_header:
        ent.extra["column"] = col_header
    if block.block_type in ("warning",) or P.WARNING_CTX.search(context):
        ent.extra["in_warning"] = True
    # Confidence: pattern certainty × OCR confidence.
    base = 0.95 if block.source == "embedded" else 0.85
    if ocr_conf is not None:
        base = min(base, 0.5 + 0.5 * ocr_conf)
    ent.confidence = round(base, 3)
    return ent


def _extract_from_block(page: RawPage, b_idx: int, block: RawBlock) -> list[ExtractedEntity]:
    out: list[ExtractedEntity] = []
    text = block.text
    taken: list[tuple[int, int]] = []

    def overlaps(s: int, e: int) -> bool:
        return any(not (e <= ts or s >= te) for ts, te in taken)

    # --- Wire sizes ------------------------------------------------------
    for pat in (P.AWG_RE, P.AWG_REV_RE, P.AWG_GAUGE_RE):
        for m in pat.finditer(text):
            if overlaps(m.start(), m.end()):
                continue
            awg = P.normalise_awg(m.group("awg"))
            if not awg:
                continue
            ent = _base_entity(page, b_idx, block, m, "wire_size", P.awg_numeric(awg), "AWG", f"{awg} AWG", m.group(0))
            ent.extra["awg"] = awg
            ent.extra["mm2_equivalent"] = P.AWG_MM2.get(awg)
            note = awg_ambiguity(m.group(0))
            if note:
                ent.flags.append({"type": "awg_ambiguity", "message": note})
            taken.append((m.start(), m.end()))
            out.append(ent)
    for m in P.MM2_RE.finditer(text):
        if overlaps(m.start(), m.end()):
            continue
        val = P.parse_number(m.group("num"))
        ent = _base_entity(page, b_idx, block, m, "wire_size", val, "mm²", f"{m.group('num')} mm²", m.group(0))
        taken.append((m.start(), m.end()))
        out.append(ent)
    for m in P.KCMIL_RE.finditer(text):
        if overlaps(m.start(), m.end()):
            continue
        val = P.parse_number(m.group("num"))
        ent = _base_entity(page, b_idx, block, m, "wire_size", val, "kcmil", f"{m.group('num')} kcmil", m.group(0))
        taken.append((m.start(), m.end()))
        out.append(ent)

    # --- Currents -> current / fuse / breaker ------------------------------
    for m in P.CURRENT_RE.finditer(text):
        if overlaps(m.start(), m.end()):
            continue
        unit = m.group("unit")
        unit_norm = "A" if unit.lower().startswith(("a",)) and unit not in ("mA", "kA") else unit
        lo, hi = m.group("lo"), m.group("hi")
        if lo is not None:
            value = P.parse_number(hi)
            value_text = f"{lo}–{hi} {unit_norm}"
        else:
            value = P.parse_number(m.group("num"))
            value_text = f"{m.group('num')} {unit_norm}"
        if value is None:
            continue
        if unit_norm == "mA":
            value = value / 1000.0
        elif unit_norm == "kA":
            value = value * 1000.0
        ent = _base_entity(page, b_idx, block, m, "current", value, "A", value_text, m.group(0))
        ctx = ent.snippet
        if lo is not None:
            ent.extra["range"] = [P.parse_number(lo), P.parse_number(hi)]
        if P.FUSE_CTX.search(ctx) and not P.BREAKER_CTX.search(ctx):
            ent.entity_type = "fuse"
        elif P.BREAKER_CTX.search(ctx) and not P.FUSE_CTX.search(ctx):
            ent.entity_type = "breaker"
        elif P.FUSE_CTX.search(ctx) and P.BREAKER_CTX.search(ctx):
            # Both mentioned: pick the nearer term.
            fpos = min((abs(mm.start() - (m.start() - (m.start() - text.rfind("\n", 0, m.start()) - 1))) for mm in P.FUSE_CTX.finditer(ctx)), default=999)
            bpos = min((abs(mm.start() - (m.start() - (m.start() - text.rfind("\n", 0, m.start()) - 1))) for mm in P.BREAKER_CTX.finditer(ctx)), default=999)
            ent.entity_type = "fuse" if fpos <= bpos else "breaker"
            ent.extra["protection_ambiguous"] = True
        elif P.PROTECTION_CTX.search(ctx):
            ent.entity_type = "breaker" if re.search(r"\bbreaker\b", ctx, re.I) else "fuse"
            ent.extra["protection_generic"] = True
        if ent.entity_type in ("fuse", "breaker"):
            ent.qualifier = _primary_qualifier(ent.extra.get("qualifiers", []), ent.entity_type)
            fc = P.FUSE_CLASS_RE.search(ctx) if ent.entity_type == "fuse" else P.BREAKER_TYPE_RE.search(ctx)
            if fc:
                ent.device_type = re.sub(r"\s+", " ", fc.group(1)).strip()
        # Digit-confusion alternatives for OCR text with low confidence.
        if ent.ocr_confidence is not None and ent.ocr_confidence < 0.9:
            num = m.group("num") or m.group("hi")
            ent.extra["alternatives"] = [f"{a} {unit_norm}" for a in digit_alternatives(num.replace(",", ""))]
        taken.append((m.start(), m.end()))
        out.append(ent)

    # --- Voltages -------------------------------------------------------
    for m in P.VOLTAGE_RE.finditer(text):
        if overlaps(m.start(), m.end()):
            continue
        unit = m.group("unit")
        ac = (m.group("ac") or "").upper()
        if unit.upper() == "VDC":
            ac = "DC"
        elif unit.upper() == "VAC":
            ac = "AC"
        lo, hi = m.group("lo"), m.group("hi")
        if lo is not None:
            value = P.parse_number(hi)
            num_text = f"{lo}–{hi}"
        else:
            value = P.parse_number(m.group("num"))
            num_text = m.group("num")
        if value is None:
            continue
        if unit == "kV":
            value *= 1000
        elif unit == "mV":
            value /= 1000
        vt = f"{num_text} V{ac}" if ac else f"{num_text} V"
        ent = _base_entity(page, b_idx, block, m, "voltage", value, "V", vt, m.group(0))
        if lo is not None:
            ent.extra["range"] = [P.parse_number(lo), P.parse_number(hi)]
        if ac:
            ent.circuit = ac.lower()
        if ent.ocr_confidence is not None and ent.ocr_confidence < 0.9:
            ent.extra["alternatives"] = [f"{a} V{ac}" for a in digit_alternatives(num_text.replace(",", ""))]
        taken.append((m.start(), m.end()))
        out.append(ent)

    # --- Simple quantity types ------------------------------------------
    simple: list[tuple[re.Pattern, str, str | None]] = [
        (P.CAPACITY_RE, "capacity", None),
        (P.POWER_RE, "power", None),
        (P.FREQ_RE, "frequency", None),
        (P.TORQUE_RE, "torque", None),
        (P.RESISTANCE_RE, "resistance", None),
    ]
    for pat, etype, _ in simple:
        for m in pat.finditer(text):
            if overlaps(m.start(), m.end()):
                continue
            unit = m.group("unit")
            value = P.parse_number(m.group("num"))
            if value is None:
                continue
            unit_norm, value = _normalise_unit(etype, unit, value)
            ent = _base_entity(page, b_idx, block, m, etype, value, unit_norm, f"{m.group('num')} {unit_norm}", m.group(0))
            if etype == "torque":
                ent.extra["nm_equivalent"] = round(_to_nm(value, unit_norm), 2)
                tm = P.TERMINAL_RE.search(ent.snippet)
                if tm:
                    ent.extra["terminal"] = tm.group("term")
            if etype == "power" and unit_norm == "BTU/h":
                ent.extra["watts_equivalent"] = round(value * 0.29307, 1)
            taken.append((m.start(), m.end()))
            out.append(ent)

    for m in P.TEMP_RE.finditer(text):
        if overlaps(m.start(), m.end()):
            continue
        unit = "°" + m.group("unit")
        lo, hi = m.group("lo"), m.group("hi")
        if lo is not None:
            value = P.parse_number(hi)
            num_text = f"{lo} to {hi}"
        else:
            value = P.parse_number(m.group("num"))
            num_text = m.group("num")
        if value is None:
            continue
        ent = _base_entity(page, b_idx, block, m, "temperature", value, unit, f"{num_text} {unit}", m.group(0))
        if lo is not None:
            ent.extra["range"] = [P.parse_number(lo), P.parse_number(hi)]
        taken.append((m.start(), m.end()))
        out.append(ent)

    # --- Terminal sizes & clearances ------------------------------------
    for m in P.TERMINAL_RE.finditer(text):
        if overlaps(m.start(), m.end()):
            continue
        ctx, _, _ = _sentence_window(text, m.start(), m.end())
        if not re.search(r"\bterminal|stud|bolt|screw|lug|nut\b", ctx, re.I):
            continue
        ent = _base_entity(page, b_idx, block, m, "terminal_size", None, None, m.group("term"), m.group(0))
        ent.is_critical = False
        taken.append((m.start(), m.end()))
        out.append(ent)
    for m in P.LENGTH_RE.finditer(text):
        if overlaps(m.start(), m.end()):
            continue
        ctx, _, _ = _sentence_window(text, m.start(), m.end())
        if not re.search(r"\bclearance|ventilation|airflow|air ?gap|space|spacing|distance|above|below|around|sides?\b", ctx, re.I):
            continue
        if re.search(r"\bcable length|wire length|run\b", ctx, re.I):
            continue
        value = P.parse_number(m.group("num"))
        unit = m.group("unit")
        unit = {"\"": "in", "'": "ft", "feet": "ft", "inch": "in", "inches": "in"}.get(unit, unit)
        ent = _base_entity(page, b_idx, block, m, "clearance", value, unit, f"{m.group('num')} {unit}", m.group(0))
        ent.is_critical = False
        taken.append((m.start(), m.end()))
        out.append(ent)

    # --- Equipment mentions with model numbers --------------------------
    seen_equipment: set[tuple[str, str | None]] = set()
    equipment_spans: list[tuple[int, int]] = []
    for label, pat in P.EQUIPMENT_TERMS:
        for m in pat.finditer(text):
            if any(not (m.end() <= es or m.start() >= ee) for es, ee in equipment_spans):
                continue  # already covered by a more specific term (e.g. "battery bank" vs "battery")
            ctx, s0, s1 = _sentence_window(text, m.start(), m.end(), radius=90)
            mm = P.MODEL_RE.search(ctx)
            model = mm.group(1) if mm else None
            key = (label, model)
            if key in seen_equipment:
                continue
            seen_equipment.add(key)
            pm = P.POWER_RE.search(ctx)
            vm = P.VOLTAGE_RE.search(ctx)
            if model is None and not (pm or vm):
                continue  # generic mention without a model or rating; not an equipment record
            if model is None and label in ("fuse", "circuit breaker", "relay", "contactor", "busbar", "shunt"):
                continue
            equipment_spans.append((m.start(), m.end()))
            ent = _base_entity(page, b_idx, block, m, "equipment", None, None, model or label, m.group(0))
            ent.equipment = label
            ent.equipment_model = model
            ent.is_critical = False
            ent.confidence = round(ent.confidence * (0.9 if model else 0.6), 3)
            # Nearby rating: first power or voltage in the same context.
            if pm:
                ent.extra["rating"] = f"{pm.group('num')} {pm.group('unit')}"
            if vm:
                ent.extra["voltage"] = vm.group(0).strip()
            out.append(ent)
    return out


def _normalise_unit(etype: str, unit: str, value: float) -> tuple[str, float]:
    u = unit
    if etype == "capacity":
        lu = unit.lower().replace(" ", "").replace("-", "")
        if lu in ("ah", "amphour", "amphours"):
            return "Ah", value
        if lu == "kwh":
            return "kWh", value
        if lu == "wh":
            return "Wh", value
    if etype == "power":
        if unit.lower().startswith("watt"):
            return "W", value
        if unit.lower().startswith("btu"):
            return "BTU/h", value
        if unit.upper() == "HP":
            return "hp", value
        return unit, value
    if etype == "torque":
        lu = unit.lower().replace(" ", "").replace("-", "").replace("·", "").replace(".", "")
        if lu in ("nm",):
            return "N·m", value
        if lu in ("inlb", "inlbs", "lbin", "lbfin"):
            return "in-lb", value
        if lu in ("ftlb", "ftlbs", "lbft", "lbfft"):
            return "ft-lb", value
        if lu == "kgfcm":
            return "kgf·cm", value
    if etype == "resistance":
        lu = unit.lower()
        if lu.startswith("milli") or lu == "mω":
            return "mΩ", value
        if lu.startswith("ohm") or lu == "ω":
            return "Ω", value
        if lu == "kω":
            return "kΩ", value
    return u, value


def _to_nm(value: float, unit: str) -> float:
    return {"N·m": value, "in-lb": value * 0.1129848, "ft-lb": value * 1.3558179, "kgf·cm": value * 0.0980665}.get(unit, value)


def _dedupe(entities: list[ExtractedEntity]) -> None:
    seen: set[tuple] = set()
    keep: list[ExtractedEntity] = []
    seen_equipment: set[tuple] = set()
    for e in entities:
        key = (e.page_number, e.block_index, e.entity_type, e.value_text, e.char_start)
        if key in seen:
            continue
        seen.add(key)
        if e.entity_type == "equipment":
            ekey = (e.equipment, (e.equipment_model or "").upper())
            if ekey in seen_equipment:
                continue
            seen_equipment.add(ekey)
        keep.append(e)
    entities[:] = keep
