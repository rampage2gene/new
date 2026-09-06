"""Multi-document comparison and conflict detection.

Rule-based cross-referencing works without an API key; the AI question path
reuses the cited QA engine over the selected documents.
"""
from __future__ import annotations

from collections import Counter, defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Document, Entity
from .qa import _entity_dict, answer_question

# (key, label, entity type, preferred qualifiers, unit, fall back to unqualified values?)
SPEC_ROWS = [
    ("nominal_voltage", "Nominal / system voltage", "voltage", {"nominal"}, "V", True),
    ("max_continuous_current", "Max continuous current", "current", {"continuous", "maximum"}, "A", True),
    ("peak_current", "Peak / surge current", "current", {"peak", "surge"}, "A", False),
    ("charge_current", "Charge current (max)", "current", {"charging"}, "A", False),
    ("charge_voltage", "Charge / absorption voltage", "voltage", {"charging"}, "V", False),
    ("cutoff_voltage", "Low-voltage cutoff", "voltage", {"cutoff"}, "V", False),
    ("fuse", "Recommended fuse", "fuse", None, "A", True),
    ("breaker", "Breaker rating", "breaker", None, "A", True),
    ("wire_size", "Wire sizes", "wire_size", None, None, True),
    ("capacity", "Capacity", "capacity", None, "Ah", True),
    ("power", "Power rating", "power", {"continuous", "nominal", "maximum"}, "W", True),
    ("temperature", "Operating temperature", "temperature", {"operating"}, None, True),
    ("torque", "Terminal torque", "torque", None, None, True),
]

# Qualifiers that mark a value as something other than the headline figure.
_EXCLUDE_FOR_FALLBACK = {"charging", "cutoff", "idle", "short_circuit", "surge", "peak", "storage", "derating"}


def _pick(entities: list[Entity], etype: str, quals: set[str] | None, fallback: bool = True) -> list[Entity]:
    rows = [e for e in entities if e.entity_type == etype]
    if etype == "voltage":
        rows = [e for e in rows if e.circuit != "ac"] or rows
    if quals:
        q = [e for e in rows if e.qualifier in quals]
        if not q and fallback:
            q = [e for e in rows if e.qualifier not in _EXCLUDE_FOR_FALLBACK]
        rows = q
    # Most frequent values first, keep up to 4 distinct values.
    counts = Counter(e.value_text for e in rows)
    ordered = sorted(rows, key=lambda e: (-counts[e.value_text], e.page_number))
    seen: set[str] = set()
    out = []
    for e in ordered:
        if e.value_text in seen:
            continue
        seen.add(e.value_text)
        out.append(e)
        if len(out) >= 4:
            break
    return out


def compare_documents(session: Session, document_ids: list[str], question: str | None = None) -> dict:
    docs = session.execute(select(Document).where(Document.id.in_(document_ids))).scalars().all()
    docs.sort(key=lambda d: document_ids.index(d.id))
    ents_by_doc: dict[str, list[Entity]] = defaultdict(list)
    for e in session.execute(select(Entity).where(Entity.document_id.in_(document_ids))).scalars():
        ents_by_doc[e.document_id].append(e)

    table = []
    picks: dict[str, dict[str, list[Entity]]] = {}
    for key, label, etype, quals, unit, fallback in SPEC_ROWS:
        row = {"key": key, "label": label, "unit": unit, "cells": []}
        picks[key] = {}
        for d in docs:
            chosen = _pick(ents_by_doc[d.id], etype, quals, fallback)
            picks[key][d.id] = chosen
            row["cells"].append({"document_id": d.id, "values": [_entity_dict(e, d, []) for e in chosen]})
        if any(c["values"] for c in row["cells"]):
            table.append(row)

    conflicts = _detect_conflicts(docs, picks)
    result = {
        "documents": [
            {"id": d.id, "name": d.title or d.filename, "manufacturer": d.manufacturer, "model": d.model_number, "document_type": d.document_type, "equipment_types": d.equipment_types}
            for d in docs
        ],
        "table": table,
        "conflicts": conflicts,
        "note": "Values in the table are manufacturer-documented extractions with sources. Conflict checks are rule-based engineering analysis, not manufacturer statements.",
    }
    if question:
        result["answer"] = answer_question(session, question, document_ids)
    return result


def _doc_role(d: Document) -> set[str]:
    roles = set(d.equipment_types or [])
    if d.document_type and "battery" in (d.title or "").lower():
        roles.add("battery")
    return roles


def _detect_conflicts(docs: list[Document], picks: dict[str, dict[str, list[Entity]]]) -> list[dict]:
    conflicts: list[dict] = []

    def src(e: Entity, d: Document) -> dict:
        return {"document_id": d.id, "document_name": d.title or d.filename, "page": e.page_number, "section": e.section, "value_text": e.value_text, "entity_id": e.id, "bbox": [e.x0, e.y0, e.x1, e.y1]}

    # 1. Nominal voltage mismatch between documents.
    voltages: dict[str, tuple[Entity, Document]] = {}
    for d in docs:
        for e in picks.get("nominal_voltage", {}).get(d.id, [])[:1]:
            if e.circuit in (None, "dc") and e.value and e.value <= 60:
                voltages[d.id] = (e, d)
    distinct = {round(v[0].value) for v in voltages.values()}
    if len(distinct) > 1:
        conflicts.append(
            {
                "type": "voltage_mismatch",
                "severity": "critical",
                "message": "Documents state different nominal DC voltages: " + ", ".join(f"{d.title or d.filename}: {e.value_text}" for e, d in voltages.values()) + ". Confirm the equipment is configured for the same system voltage.",
                "classification": "engineering_analysis",
                "sources": [src(e, d) for e, d in voltages.values()],
            }
        )

    # 2. BMS / battery discharge limit vs inverter continuous current.
    inverter_docs = [d for d in docs if any(r in ("inverter", "inverter/charger") for r in _doc_role(d)) and "inverter" in (d.title or d.filename).lower() + " ".join(d.equipment_types or [])]
    battery_docs = [d for d in docs if ("battery" in _doc_role(d) or "bms" in _doc_role(d)) and d not in inverter_docs]
    for inv in inverter_docs:
        inv_i = picks.get("max_continuous_current", {}).get(inv.id, [])[:1]
        if not inv_i:
            continue
        for bat in battery_docs:
            bat_i = [e for e in picks.get("max_continuous_current", {}).get(bat.id, []) if e.value]
            if not bat_i:
                continue
            b = bat_i[0]
            if b.value < inv_i[0].value:
                conflicts.append(
                    {
                        "type": "discharge_limit",
                        "severity": "critical",
                        "message": f"{bat.title or bat.filename} lists a continuous current of {b.value_text} while {inv.title or inv.filename} can draw {inv_i[0].value_text}. The battery/BMS limit is lower than the inverter's maximum DC current.",
                        "classification": "engineering_analysis",
                        "sources": [src(inv_i[0], inv), src(b, bat)],
                    }
                )
    # 3. Charger charge current vs battery max charge current. Any non-battery document
    #    that states a charge current is treated as a charging source.
    charger_roles = ("battery charger", "inverter/charger", "alternator", "solar controller", "dc-dc converter")
    charger_docs = [d for d in docs if d not in battery_docs and (any(r in charger_roles for r in _doc_role(d)) or picks.get("charge_current", {}).get(d.id))]
    for ch in charger_docs:
        ch_i = [e for e in picks.get("charge_current", {}).get(ch.id, []) if e.value]
        if not ch_i:
            continue
        for bat in battery_docs:
            if bat is ch:
                continue
            bat_i = [e for e in picks.get("charge_current", {}).get(bat.id, []) if e.value]
            if bat_i and ch_i[0].value > bat_i[0].value:
                conflicts.append(
                    {
                        "type": "charge_current",
                        "severity": "warning",
                        "message": f"{ch.title or ch.filename} charge current {ch_i[0].value_text} exceeds the battery's maximum charge current {bat_i[0].value_text} in {bat.title or bat.filename}. Limit the charger output.",
                        "classification": "engineering_analysis",
                        "sources": [src(ch_i[0], ch), src(bat_i[0], bat)],
                    }
                )
            bat_v = [e for e in picks.get("charge_voltage", {}).get(bat.id, []) if e.value]
            ch_v = [e for e in picks.get("charge_voltage", {}).get(ch.id, []) if e.value]
            if bat_v and ch_v and ch_v[0].value > bat_v[0].value + 0.05:
                conflicts.append(
                    {
                        "type": "charge_voltage",
                        "severity": "critical",
                        "message": f"Charge voltage {ch_v[0].value_text} in {ch.title or ch.filename} is above the battery's stated charge voltage {bat_v[0].value_text} in {bat.title or bat.filename}.",
                        "classification": "engineering_analysis",
                        "sources": [src(ch_v[0], ch), src(bat_v[0], bat)],
                    }
                )
    # 4. Different fuse recommendations for the same application across documents.
    app_fuses: dict[str, list[tuple[Entity, Document]]] = defaultdict(list)
    for d in docs:
        for e in picks.get("fuse", {}).get(d.id, []):
            if e.application:
                app_fuses[e.application.lower()].append((e, d))
    for app, items in app_fuses.items():
        vals = {e.value_text for e, _ in items}
        if len(vals) > 1 and len({d.id for _, d in items}) > 1:
            conflicts.append(
                {
                    "type": "fuse_recommendation",
                    "severity": "warning",
                    "message": f"Different fuse ratings are given for '{app}': " + ", ".join(f"{e.value_text} ({d.title or d.filename}, p.{e.page_number})" for e, d in items) + ".",
                    "classification": "engineering_analysis",
                    "sources": [src(e, d) for e, d in items],
                }
            )
    return conflicts
