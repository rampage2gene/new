"""Quality-control layer for critical extracted data.

Validation signals:
1. OCR confidence of the exact words that form a value
2. Digit-confusion alternatives (300 A vs 800 A)
3. Unit / plausibility ranges
4. Repeated references inside the document (a low-confidence outlier against
   a value that is repeated several times is flagged as a discrepancy)
5. Cross-reference checks (4 AWG vs 4/0 AWG for the same application)
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from ..config import get_settings
from ..extraction.entities import ExtractedEntity
from ..extraction.patterns import AWG_MM2

STANDARD_MM2 = {0.5, 0.75, 1, 1.5, 2.5, 4, 6, 10, 16, 25, 35, 50, 70, 95, 120, 150, 185, 240, 300}


@dataclass
class QCFlagData:
    flag_type: str
    severity: str
    message: str
    entity_index: int | None = None
    page_number: int | None = None
    details: dict = field(default_factory=dict)


def _plausibility(e: ExtractedEntity) -> QCFlagData | None:
    v = e.value
    if v is None:
        return None
    t = e.entity_type
    if t == "voltage" and not (0 < v <= 1500):
        return QCFlagData("unit_out_of_range", "warning", f"Voltage {e.value_text} is outside the plausible range for marine systems (0–1500 V).")
    if t in ("current", "fuse", "breaker") and not (0 < v <= 10000):
        return QCFlagData("unit_out_of_range", "warning", f"Current {e.value_text} is outside the plausible range (0–10,000 A).")
    if t == "wire_size" and e.unit == "AWG":
        awg = e.extra.get("awg")
        if awg not in AWG_MM2:
            return QCFlagData("unit_out_of_range", "warning", f"Wire size {e.value_text} is not a standard AWG size.")
    if t == "wire_size" and e.unit == "mm²" and v not in STANDARD_MM2:
        return QCFlagData("nonstandard_size", "info", f"{e.value_text} is not a standard metric conductor size; verify the reading.")
    if t == "torque":
        nm = e.extra.get("nm_equivalent", v)
        if not (0.05 <= nm <= 500):
            return QCFlagData("unit_out_of_range", "warning", f"Torque {e.value_text} is outside the plausible range.")
    if t == "temperature":
        c = v if e.unit == "°C" else (v - 32) * 5 / 9
        if not (-80 <= c <= 250):
            return QCFlagData("unit_out_of_range", "warning", f"Temperature {e.value_text} is outside the plausible range.")
    if t == "frequency" and v not in (50, 60, 400) and not (40 <= v <= 70) and v < 1000:
        return QCFlagData("nonstandard_value", "info", f"Frequency {e.value_text} is unusual for marine AC systems (50/60 Hz).")
    return None


def _group_key(e: ExtractedEntity) -> tuple:
    return (e.entity_type, (e.application or "").lower(), (e.equipment_model or e.equipment or "").lower(), e.circuit or "")


def validate_entities(entities: list[ExtractedEntity]) -> list[QCFlagData]:
    settings = get_settings()
    threshold = settings.low_confidence_threshold
    flags: list[QCFlagData] = []

    for idx, e in enumerate(entities):
        if not e.is_critical:
            continue
        # 1. OCR confidence.
        if e.ocr_confidence is not None and e.ocr_confidence < threshold:
            alts = e.extra.get("alternatives") or []
            alt_text = f" The document may read {e.value_text} or {' / '.join(alts[:2])}." if alts else ""
            f = QCFlagData(
                "low_ocr_confidence",
                "critical" if e.entity_type in ("fuse", "breaker", "wire_size", "voltage") else "warning",
                f"OCR uncertainty detected for {e.entity_type.replace('_', ' ')} '{e.value_text}' on page {e.page_number} "
                f"(confidence {e.ocr_confidence:.0%}).{alt_text} Please verify the original page.",
                idx,
                e.page_number,
                {"ocr_confidence": e.ocr_confidence, "alternatives": alts},
            )
            flags.append(f)
            e.flags.append({"type": f.flag_type, "severity": f.severity, "message": f.message})
        # 2. Ambiguity notes recorded by the extractor.
        for fl in list(e.flags):
            if fl.get("type") == "awg_ambiguity" and "severity" not in fl:
                fl["severity"] = "critical"
                flags.append(QCFlagData("awg_ambiguity", "critical", fl["message"], idx, e.page_number))
        # 3. Plausibility.
        pf = _plausibility(e)
        if pf:
            pf.entity_index = idx
            pf.page_number = e.page_number
            flags.append(pf)
            e.flags.append({"type": pf.flag_type, "severity": pf.severity, "message": pf.message})

    # 4. Repeated references / discrepancies within the same application group.
    groups: dict[tuple, list[int]] = defaultdict(list)
    for idx, e in enumerate(entities):
        if e.is_critical and e.value is not None and e.entity_type in ("fuse", "breaker", "wire_size", "torque"):
            groups[_group_key(e)].append(idx)
    for key, idxs in groups.items():
        if len(idxs) < 2:
            continue
        counts: dict[str, list[int]] = defaultdict(list)
        for i in idxs:
            counts[entities[i].value_text].append(i)
        if len(counts) < 2:
            continue
        # The most repeated value is the reference; outliers with low confidence get flagged.
        ref_text, ref_idxs = max(counts.items(), key=lambda kv: len(kv[1]))
        if len(ref_idxs) < 2:
            continue
        for val_text, val_idxs in counts.items():
            if val_text == ref_text:
                continue
            for i in val_idxs:
                e = entities[i]
                low = e.ocr_confidence is not None and e.ocr_confidence < 0.95
                qualifier_differs = e.qualifier != entities[ref_idxs[0]].qualifier
                if qualifier_differs and not low:
                    continue  # e.g. "recommended 175 A" vs "maximum 200 A" is not a discrepancy
                sev = "critical" if low else "warning"
                msg = (
                    f"Possible discrepancy: {e.entity_type.replace('_', ' ')} '{val_text}' on page {e.page_number} "
                    f"differs from '{ref_text}' which appears {len(ref_idxs)} times for the same application"
                    f" ({key[1] or 'unspecified'}). Verify against the original page."
                )
                f = QCFlagData("discrepancy", sev, msg, i, e.page_number, {"reference": ref_text, "reference_pages": sorted({entities[j].page_number for j in ref_idxs})})
                flags.append(f)
                e.flags.append({"type": f.flag_type, "severity": f.severity, "message": f.message})

    # 5. Cross reference: N AWG vs N/0 AWG for the same application.
    by_app: dict[str, list[int]] = defaultdict(list)
    for idx, e in enumerate(entities):
        if e.entity_type == "wire_size" and e.unit == "AWG" and e.application:
            by_app[e.application.lower()].append(idx)
    for app, idxs in by_app.items():
        awgs = {entities[i].extra.get("awg") for i in idxs}
        for n in ("1", "2", "3", "4"):
            if n in awgs and f"{n}/0" in awgs:
                for i in idxs:
                    if entities[i].extra.get("awg") in (n, f"{n}/0") and entities[i].extra.get("in_warning") is not True:
                        f = QCFlagData(
                            "awg_cross_reference",
                            "warning",
                            f"Both {n} AWG and {n}/0 AWG are referenced for '{app}'. These differ by a factor of ~5 in cross-section; verify which applies.",
                            i,
                            entities[i].page_number,
                        )
                        flags.append(f)
                        entities[i].flags.append({"type": f.flag_type, "severity": f.severity, "message": f.message})
    return flags
