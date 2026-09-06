"""Calculator endpoints and document-to-calculator suggestions."""
from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..calculators.base import CalculationError
from ..calculators.modules import get_calculator, list_specs
from ..db import get_db
from ..models import Document, Entity
from .serializers import entity_dict

router = APIRouter(prefix="/api/calculators", tags=["calculators"])


class RunRequest(BaseModel):
    inputs: dict[str, Any]


@router.get("")
def list_calculators() -> list[dict]:
    return [asdict(s) for s in list_specs()]


@router.post("/{calc_id}/run")
def run_calculator(calc_id: str, req: RunRequest) -> dict:
    try:
        calc = get_calculator(calc_id)
        result = calc.run(req.inputs)
    except CalculationError as exc:
        raise HTTPException(422, str(exc)) from exc
    return result.to_dict()


@router.get("/{calc_id}/suggest")
def suggest_inputs(calc_id: str, document_id: str, db: Session = Depends(get_db)) -> dict:
    """Document-to-calculator workflow: propose input values from a document's
    extracted entities, ranked by qualifier match and confidence."""
    try:
        calc = get_calculator(calc_id)
    except CalculationError as exc:
        raise HTTPException(404, str(exc)) from exc
    doc = db.get(Document, document_id)
    if not doc:
        raise HTTPException(404, "Document not found")
    ents = db.execute(select(Entity).where(Entity.document_id == document_id)).scalars().all()
    name = doc.title or doc.filename
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
        suggestions[inp.key] = [entity_dict(e, name) for e in cands[:6]]
    return {"calculator": calc.spec.id, "document": {"id": doc.id, "name": name}, "suggestions": suggestions}
