"""The words a person reads, from a circuit result - the Python twin of
packages/e11-calc/src/present.ts.

The groups, the row labels, the sentence that says what decided the size and
the list of bundle choices live here rather than in the calculator, so that
this app and anything else built on the same engine say the same thing. The
two copies are held equal by packages/e11-calc/tests/test-vectors.json.

Nothing here decides anything: every number has already been settled by
size_circuit, and a value it left blank stays blank here, with the reason it
gave.
"""
from __future__ import annotations

from typing import Any

from ..calculators.base import fmt
from .e11_tables import E11Tables, usable

GROUP_SIZE = "Cable size"
GROUP_HOW = "How it was decided"
GROUP_PROTECTION = "Protection"
GROUP_FITTINGS = "Fittings"
GROUP_BOM = "Bill of materials"

NO_TABLES = (
    "The ABYC E-11 tables are not installed or not yet confirmed, so nothing was computed. "
    "Open Calculators → ABYC E-11 reference, import each table from your copy of the standard, "
    "check it against the page and press Confirm."
)

ASSUMPTIONS = [
    "A conductor must satisfy two requirements and the larger size wins: carry the current without overheating (the ampacity table, derated for engine space and bundling) and deliver the voltage (the drop limit). When no single listed size does both, conductors are paralleled.",
    "The fuse protects the conductor: never above its derated ampacity, at least the load times its load-type factor, rounded up to a standard size.",
    "Every table value comes from your confirmed copy of ABYC E-11 and cites its page; mm² and the standard size lists are conversions and industry lists; load behaviour is industry guidance.",
]
FIXTURE_ASSUMPTION = "These figures come from the synthetic test tables, not from the standard."


def cite_source(src: dict | None) -> str:
    """Where a value came from, in a sentence: a page of the standard, one of
    the owner's catalogs, or the person."""
    if not src:
        return ""
    if "by" in src:
        return "entered by you"
    if "document" in src:
        return f"From {src['document']}" + (f", page {src['page']}" if src.get("page") else "")
    return f"ABYC E-11, {src.get('title') or src.get('table')}, page {src['page']}"


def size_note(result: dict, inputs: dict) -> str:
    """What decided the cable size, in plain words: the standard's rule is
    that the larger of the requirements wins, and this says which one it was."""
    c = result["conductor"]
    vd, pt, am = c["voltage_drop"], c["printed_table"], c["ampacity"]
    n, size, current = c["parallel"], c["size_awg"], fmt(inputs["current"])
    src = vd.get("source")
    page = f" (page {src['page']})" if src and "by" not in src and src.get("page") else ""
    if n > 1:
        total = result["protection"].get("conductor_ampacity_a")
        carries = f" carry {fmt(total)} A after derating" if total is not None else ""
        need = "the area the drop limit needs" if c["governed_by"] == "voltage_drop" else "the current"
        return f"No single listed size meets {need}: {n} × {size} AWG in parallel{carries}."
    g = c["governed_by"]
    if g == "printed_table":
        return (
            f"The printed {fmt(inputs['max_drop_percent'])} % table at {fmt(inputs['system_voltage'])} V asks for this size, "
            f"more than the formula's {vd['size_awg']} AWG; the larger is used."
        )
    if g == "voltage_drop":
        also = f"; it also carries {current} A ({am['size_awg']} AWG would)" if am.get("size_awg") else ""
        if pt.get("reason") and "stops at" in pt["reason"]:
            return f"{pt['reason'].split(', so')[0]}, so the circular-mils formula and the circular-mils table{page} set this size{also}."
        return (
            f"Set by the voltage-drop limit: {fmt(vd['cm_required'])} circular mils needed, "
            f"and this is the smallest listed size with at least that{page}{also}."
        )
    if g == "ampacity":
        allow = f"; the drop limit alone would allow {vd['size_awg']} AWG" if vd.get("size_awg") else ""
        return f"Set by the current: {current} A needs this size after derating{allow}."
    return "The larger of the requirements is used."


def bundle_options(tables: E11Tables) -> list[dict]:
    """The bundle choices: not bundled, then one per row of the confirmed
    bundling table (the factor and page shown, the row's lowest count as the
    value). Without that table there is nothing to list, so the count is typed
    instead - and no factor is assumed for it."""
    options = [{"value": "2", "label": "Not bundled (this circuit's two conductors)"}]
    table = usable(tables, "bundling_factors")
    if not table:
        options.append({"value": "count", "label": "Bundled: type the count below"})
        return options
    # The synthetic test tables carry made-up numbers; the pick list says so
    # where the choice is made, not only on the reference screen.
    mark = ", test data" if table.get("status") == "fixture" else ""
    seen = {"2"}
    for row in sorted(table["rows"], key=lambda r: r["min_conductors"]):
        hi = row.get("max_conductors")
        if hi is not None and hi <= 2:
            continue  # the "not bundled" row, already offered
        value = str(max(int(row["min_conductors"]), 3))
        if value in seen:
            continue
        seen.add(value)
        span = f"{row['min_conductors']} to {hi}" if hi is not None else f"{row['min_conductors']} or more"
        options.append({"value": value, "label": f"{span} conductors bundled (× {fmt(row['factor'])}, page {row['page']}{mark})"})
    return options


def present_no_tables() -> dict:
    """The one row shown when no table has been confirmed yet: an ask, not an answer."""
    return {
        "rows": [{"key": "size_awg", "label": "Cable size to use", "value": None, "unit": None,
                  "classification": "recommended_pending_verification", "note": NO_TABLES, "group": GROUP_SIZE}],
        "asks": [{"field": "reference", "reason": NO_TABLES, "own_field": None, "unit": None, "prompt": NO_TABLES, "kind": None}],
        "warnings": [NO_TABLES],
        "assumptions": [],
        "sources": [],
    }


def _row(key: str, label: str, value: Any, unit: str | None, classification: str, note: Any, group: str) -> dict:
    return {"key": key, "label": label, "value": value, "unit": unit, "classification": classification, "note": note, "group": group}


def present_circuit(inputs: dict, result: dict, unit: str = "awg", own: dict | None = None) -> dict:
    """The whole result as rows a person reads, in the order they read them."""
    from ..calculators.modules import CIRCUIT_TYPES, DEVICE_PROFILES

    in_mm2 = unit == "mm2"
    own = own or {}
    c, p, ft = result["conductor"], result["protection"], result["fittings"]
    rows: list[dict] = []

    # 1. The answer.
    n = c["parallel"]
    awg_text = (f"{n} × {c['size_awg']} AWG in parallel" if n > 1 else f"{c['size_awg']} AWG") if c["size_awg"] else None
    metric = c["metric_standard_mm2"] or c["size_mm2"]
    metric_text = None
    if c["size_awg"] and metric is not None:
        metric_text = f"{n} × {fmt(metric)} mm² in parallel ({n} × {c['size_awg']} AWG)" if n > 1 else f"{fmt(metric)} mm² ({c['size_awg']} AWG)"
    size_text = (metric_text or awg_text) if in_mm2 else awg_text
    note = size_note(result, inputs) if size_text else next((b["reason"] for b in result["blanks"] if b["field"].startswith("conductor.")), "No conductor size was settled.")
    rows.append(_row("size_awg", "Cable size to use", size_text, None, "documented_value" if size_text else "recommended_pending_verification", note, GROUP_SIZE))
    if c["size_mm2"] is not None:
        each = " each" if n > 1 else ""
        std = (f"{fmt(c['metric_standard_mm2'])} mm² is the smallest standard metric size (IEC 60228) at least as large."
               if c["metric_standard_mm2"] else "Larger than the largest standard metric size (IEC 60228), 300 mm².")
        rows.append(_row("size_mm2", "Exact area of that AWG size" if in_mm2 else "Same area in mm²", c["size_mm2"], "mm²", "calculated_estimate",
                         f"{c['size_awg']} AWG is {fmt(c['size_mm2'])} mm²{each}. {std} A conversion; the standard's sizes are AWG.", GROUP_SIZE))

    # 2. The working, always quoting the pages in AWG as they print it.
    vd, pt, am = c["voltage_drop"], c["printed_table"], c["ampacity"]
    rows.append(_row("cm_required", "Circular mils needed for the drop limit", vd["cm_required"], "CM", "documented_value", vd.get("reason") or cite_source(vd.get("source")), GROUP_HOW))
    rows.append(_row("printed_table_size", "Size from the printed table", f"{pt['size_awg']} AWG" if pt["size_awg"] else None, None, "documented_value", pt.get("reason") or cite_source(pt.get("source")), GROUP_HOW))
    rows.append(_row("voltage_drop_size", "Size for the voltage drop, from the formula", f"{vd['size_awg']} AWG" if vd["size_awg"] else None, None, "documented_value", vd.get("reason") or cite_source(vd.get("source")), GROUP_HOW))
    # A factor typed from the page always wins over the table, so saying so
    # here is simply whether they gave one.
    by_you = " (factor entered by you)" if own.get("bundling_factor") is not None else ""
    amp_note = am.get("reason") or f"{fmt(am['ampacity_a'])} A × bundling factor {fmt(am['bundling_factor'])}{by_you} ({cite_source(am.get('source'))})"
    rows.append(_row("ampacity_size", "Size for the current, derated", f"{am['size_awg']} AWG" if am["size_awg"] else None, None, "documented_value", amp_note, GROUP_HOW))
    d = c["drop_at_size"]
    rows.append(_row("drop_at_size", "Drop at the chosen size", d["volts"], "V", "calculated_estimate",
                     d.get("reason") or (f"{fmt(d['percent'])} % of {fmt(inputs['system_voltage'])} V" if d["percent"] is not None else None), GROUP_HOW))

    # 3. Protection.
    fuse_note = p.get("reason") or (f"At least {fmt(p['min_a'])} A for the load, within the conductor's {fmt(p['conductor_ampacity_a'])} A" if p["fuse_a"] is not None else None)
    rows.append(_row("fuse_a", "Fuse or breaker", p["fuse_a"], "A", "recommended_pending_verification", fuse_note, GROUP_PROTECTION))
    if p["characteristic"]:
        rows.append(_row("fuse_characteristic", "Characteristic", p["characteristic"], None, "recommended_pending_verification", p["guidance"], GROUP_PROTECTION))
    ic = p["interrupting"]
    classes = ", ".join(f"{x['class']} ({fmt(x['interrupting_rating_a'])} A{', suits this load' if x['suits_load'] else ''})" for x in ic["classes"]) or None
    rows.append(_row("interrupting", "Fuse classes with enough interrupting capacity", classes, None, "recommended_pending_verification",
                     ic.get("reason") or (f"The source can deliver {fmt(ic['required_a'])} A; ratings from the makers' datasheets" if classes else None), GROUP_PROTECTION))
    ctype = CIRCUIT_TYPES.get(inputs.get("circuit_type") or "general_dc", CIRCUIT_TYPES["general_dc"])
    profile = DEVICE_PROFILES[ctype["load_type"]]
    rows.append(_row("load_type", "Load type", profile["label"], None, "recommended_pending_verification",
                     f"Industry guidance, from the circuit type \"{ctype['label']}\": {profile['surge_note']}", GROUP_PROTECTION))

    # 4. Fittings: from the owner's catalog tables, or the person; never typical.
    od, hs, lug = ft["cable_od"], ft["heat_shrink"], ft["lug"]
    rows.append(_row("cable_od", "Cable outside diameter", od["value"], od["unit"], "documented_value", od.get("reason") or cite_source(od.get("source")), GROUP_FITTINGS))
    hs_text = None
    if hs["size"]:
        hs_text = hs["size"] + (f" ({fmt(hs['supplied_id'])} → {fmt(hs['recovered_id'])} {hs['unit']}{', adhesive-lined' if hs['adhesive'] else ''})" if hs["supplied_id"] is not None else "")
    rows.append(_row("heat_shrink", "Heat-shrink tubing", hs_text, None, "documented_value", hs.get("reason") or cite_source(hs.get("source")), GROUP_FITTINGS))
    rows.append(_row("lug", "Lug or terminal", f"{lug['part']} for a {lug['stud']} stud" if lug["part"] else None, None, "documented_value", lug.get("reason") or cite_source(lug.get("source")), GROUP_FITTINGS))
    rows.append(_row("crimp_die", "Crimp die or setting", lug["crimp_die"], None, "documented_value",
                     lug.get("die_reason") or cite_source(lug.get("die_source")) or ("No lug, so no die." if not lug["part"] else None), GROUP_FITTINGS))

    # 5. What to buy: counts for the set, from the parallel count and the loop length.
    q = ft["quantities"]
    if q and c["size_awg"]:
        size_each = f"{fmt(metric)} mm² ({c['size_awg']} AWG)" if in_mm2 and metric is not None else f"{c['size_awg']} AWG"
        rows.append(_row("bom_cable", "Cable to buy", f"{q['cables']} × {size_each}, {fmt(q['cable_length'])} {q['length_unit']}", None, "calculated_estimate",
                         f"{fmt(inputs['length'])} {q['length_unit']} there and back per cable, plus your own routing allowance; none is added here.", GROUP_BOM))
        rows.append(_row("bom_lugs", "Lugs", f"{q['lugs']} × {lug['part']}" if lug["part"] else f"{q['lugs']} lugs needed; part not chosen yet", None, "calculated_estimate", "Two per cable.", GROUP_BOM))
        rows.append(_row("bom_heat_shrink", "Heat shrink", f"{q['heat_shrink_pieces']} pieces of {hs['size']}" if hs["size"] else f"{q['heat_shrink_pieces']} pieces needed; size not chosen yet", None, "calculated_estimate", "Two per cable, one over each lug barrel.", GROUP_BOM))
        rows.append(_row("bom_fuse", "Fuse or breaker", f"1 × {fmt(p['fuse_a'])} A, {p['characteristic']}" if p["fuse_a"] is not None else "1, rating not yet settled", None,
                         "recommended_pending_verification", p["guidance"] if p["fuse_a"] is not None else p.get("reason"), GROUP_BOM))

    # The blanks, as things a person can answer.
    asks = []
    for b in result["blanks"]:
        ask = b.get("ask")
        asks.append({
            "field": b["field"], "reason": b["reason"],
            "own_field": ask["field"].split(".", 1)[1] if ask and ask["field"].startswith("own.") else (ask["field"] if ask else None),
            "unit": ask["unit"] if ask else None,
            "prompt": ask["prompt"] if ask else b["reason"],
            "kind": (ask.get("kind") or "number") if ask else None,
        })

    warnings = [b["reason"] for b in result["blanks"] if not b.get("ask")]
    if p["fits_conductor"] is False and p.get("reason"):
        warnings.append(p["reason"])
    # A typed fitting skips the fit checks a catalog row gets; say so.
    if hs.get("source") == {"by": "you"}:
        warnings.append(f"The heat-shrink size you typed ({hs['size']}) was not checked against the cable and lug diameters; a row in your heat-shrink table would be.")
    if lug.get("source") == {"by": "you"}:
        warnings.append(f"The lug part you typed ({lug['part']}) was not checked against the stud size; a row in your lugs table would be.")

    sources: list[dict] = []
    seen = set()
    for src in (vd.get("source"), pt.get("source"), am.get("source")):
        if not src or "by" in src or not src.get("page"):
            continue
        key = (src["table"], src["page"])
        if key in seen:
            continue
        seen.add(key)
        sources.append({"document_name": f"ABYC E-11 ({src.get('title') or src['table']})", "page": src["page"]})

    return {
        "rows": rows, "asks": asks, "warnings": warnings, "sources": sources,
        "assumptions": [*ASSUMPTIONS, FIXTURE_ASSUMPTION] if result["fixture"] else list(ASSUMPTIONS),
    }


# --------------------------------------------------------------------------- the conditions, offered from the tables

AMPACITY_IDS = ("ampacity_outside_engine_space", "ampacity_inside_engine_space")
DROP_GRIDS = (("3", "voltage_drop_3pct", "3 % (critical circuits)"), ("10", "voltage_drop_10pct", "10 % (non-critical)"))


def _from_page(page: int | None, fixture: bool) -> str:
    """" (page 4)" or " (page 4, test data)": where a choice comes from."""
    mark = ", test data" if fixture else ""
    if page:
        return f" (page {page}{mark})"
    return " (test data)" if fixture else ""


def rating_options(tables: E11Tables) -> list[dict]:
    """The insulation ratings to offer: the temperature columns the confirmed
    ampacity tables actually print, and no others. An empty list means no
    ampacity table is confirmed yet, so the rating is typed instead of picked -
    inventing a column here would be inventing a page."""
    seen: dict[float, str] = {}
    for tid in AMPACITY_IDS:
        table = usable(tables, tid)
        if not table:
            continue
        keys = list(table.get("columns") or {})
        if not keys:
            keys = list(dict.fromkeys(k for row in table["rows"] for k in (row.get("values") or {})))
        where = _from_page((table.get("source") or {}).get("page"), table.get("status") == "fixture")
        for key in keys:
            try:
                n = float(key)
            except (TypeError, ValueError):
                continue
            if n not in seen:
                seen[n] = where
    return [{"value": fmt(n), "label": f"{fmt(n)} °C{where}"} for n, where in sorted(seen.items())]


def drop_limit_options(tables: E11Tables) -> list[dict]:
    """The drop limits. The formula honours any limit, so all three are always
    offered; what the table adds is which of them has a printed grid behind it,
    and at what voltage, so the choice is made knowing that."""
    options = []
    for pct, tid, base in DROP_GRIDS:
        table = usable(tables, tid)
        printed = ""
        if table:
            printed = f" — printed table at {fmt(table['nominal_voltage'])} V{_from_page((table.get('source') or {}).get('page'), table.get('status') == 'fixture')}"
        options.append({"value": pct, "label": base + printed})
    options.append({"value": "other", "label": "other"})
    return options


def engine_space_options(tables: E11Tables) -> list[dict]:
    """Inside or outside an engine space, saying when the table that answer
    needs is not confirmed."""
    def tail(tid: str) -> str:
        return "" if usable(tables, tid) else " — that table is not confirmed yet"

    return [
        {"value": "no", "label": f"No{tail('ampacity_outside_engine_space')}"},
        {"value": "yes", "label": f"Yes{tail('ampacity_inside_engine_space')}"},
    ]


def condition_options(tables: E11Tables) -> dict[str, list[dict]]:
    """Every condition whose choices come from the tables, keyed by the input
    it fills."""
    return {
        "bundle": bundle_options(tables),
        "insulation_rating_c": rating_options(tables),
        "max_drop_percent": drop_limit_options(tables),
        "engine_space": engine_space_options(tables),
    }
