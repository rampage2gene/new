"""Calculator endpoints and document-to-calculator suggestions."""
from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..calculators.base import CalculationError
from ..calculators.modules import get_calculator, list_specs
from ..calculators.suggest import suggest_inputs as _suggest_inputs
from ..db import get_db
from ..models import Document, Entity

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
    suggestions = _suggest_inputs(calc, ents, name)
    return {"calculator": calc.spec.id, "document": {"id": doc.id, "name": name}, "suggestions": suggestions}


@router.post("/{calc_id}/export")
def export_calculator(calc_id: str, req: RunRequest, request: Request) -> Response:
    """The current calculation as an Excel workbook whose results are live
    formulas over the input cells."""
    from ..exports.workbook import build_calculator_workbook

    try:
        data = build_calculator_workbook(calc_id, req.inputs, base_url=str(request.base_url).rstrip("/"))
    except CalculationError as exc:
        raise HTTPException(422, str(exc)) from exc
    return Response(
        data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{calc_id}.xlsx"'},
    )
