"""Document-to-calculator suggestions: propose input values from a document's
extracted entities, ranked by qualifier match and confidence. Shared by the
API and the spreadsheet exporter."""
from __future__ import annotations

from ..api.serializers import entity_dict
from ..models import Entity
from .base import Calculator


def suggest_inputs(calc: Calculator, ents: list[Entity], doc_name: str, per_input: int = 6) -> dict[str, list[dict]]:
    suggestions: dict[str, list[dict]] = {}
    for inp in calc.spec.inputs:
        if not inp.entity_types:
            continue
        cands = [e for e in ents if e.entity_type in inp.entity_types]
        if inp.key == "manufacturer_fuse":
            cands = [e for e in cands if e.qualifier != "maximum"]
        if inp.key == "manufacturer_max_fuse":
            cands = [e for e in cands if e.qualifier == "maximum"]

        def rank(e: Entity) -> tuple:
            q = 0 if (inp.qualifiers and e.qualifier in inp.qualifiers) else (1 if not inp.qualifiers else 2)
            if inp.key == "voltage" and e.circuit == "ac":
                q += 2
            return (q, -e.confidence, e.page_number)

        cands.sort(key=rank)
        suggestions[inp.key] = [entity_dict(e, doc_name) for e in cands[:per_input]]
    return suggestions


def prefill_from_suggestions(calc: Calculator, suggestions: dict[str, list[dict]]) -> dict[str, dict]:
    """Top suggestion per input as a calculator request payload
    ({key: {value, unit, source}})."""
    payload: dict[str, dict] = {}
    for inp in calc.spec.inputs:
        cands = suggestions.get(inp.key) or []
        if not cands:
            continue
        e = cands[0]
        value = e["value_text"] if inp.kind == "text" else e["value"]
        if value is None:
            continue
        payload[inp.key] = {
            "value": value,
            "unit": e.get("unit"),
            "source": {
                "document_id": e["document_id"],
                "document_name": e.get("document_name"),
                "page": e["page"],
                "section": e.get("section"),
                "entity_id": e["id"],
                "snippet": e.get("snippet"),
                "confidence": e.get("confidence"),
                "bbox": e.get("bbox"),
            },
        }
    return payload
