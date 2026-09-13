"""Technical data: entity listing and the Electrical Specification Extraction report."""
from __future__ import annotations

from collections import OrderedDict

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Document, Entity
from .serializers import entity_dict

router = APIRouter(prefix="/api", tags=["entities"])

GROUPS: "OrderedDict[str, dict]" = OrderedDict(
    [
        ("equipment", {"label": "Equipment", "types": ["equipment"]}),
        ("electrical_ratings", {"label": "Electrical ratings", "types": ["voltage", "current", "power", "frequency", "capacity", "resistance"]}),
        ("wire_sizes", {"label": "Wire sizes", "types": ["wire_size"]}),
        ("fuse_ratings", {"label": "Fuse ratings", "types": ["fuse"]}),
        ("breaker_ratings", {"label": "Breaker ratings", "types": ["breaker"]}),
        ("installation_requirements", {"label": "Installation requirements", "types": ["clearance", "terminal_size"]}),
        ("torque_specifications", {"label": "Torque specifications", "types": ["torque"]}),
        ("temperature_limits", {"label": "Temperature limits", "types": ["temperature"]}),
    ]
)


def _doc_names(db: Session, ids: set[str]) -> dict[str, str]:
    if not ids:
        return {}
    return {d.id: (d.title or d.filename) for d in db.execute(select(Document).where(Document.id.in_(ids))).scalars()}


@router.get("/entities")
def list_entities(
    document_ids: list[str] | None = Query(default=None),
    entity_type: list[str] | None = Query(default=None),
    q: str | None = None,
    critical_only: bool = False,
    limit: int = 500,
    db: Session = Depends(get_db),
) -> list[dict]:
    stmt = select(Entity)
    if document_ids:
        stmt = stmt.where(Entity.document_id.in_(document_ids))
    if entity_type:
        stmt = stmt.where(Entity.entity_type.in_(entity_type))
    if critical_only:
        stmt = stmt.where(Entity.is_critical.is_(True))
    if q:
        like = f"%{q}%"
        stmt = stmt.where((Entity.snippet.ilike(like)) | (Entity.value_text.ilike(like)) | (Entity.application.ilike(like)))
    stmt = stmt.order_by(Entity.document_id, Entity.page_number, Entity.char_start).limit(limit)
    ents = db.execute(stmt).scalars().all()
    names = _doc_names(db, {e.document_id for e in ents})
    return [entity_dict(e, names.get(e.document_id)) for e in ents]


@router.get("/documents/{document_id}/entities")
def document_entities(document_id: str, entity_type: list[str] | None = Query(default=None), db: Session = Depends(get_db)) -> list[dict]:
    doc = db.get(Document, document_id)
    if not doc:
        raise HTTPException(404, "Document not found")
    stmt = select(Entity).where(Entity.document_id == document_id)
    if entity_type:
        stmt = stmt.where(Entity.entity_type.in_(entity_type))
    ents = db.execute(stmt.order_by(Entity.page_number, Entity.char_start)).scalars().all()
    name = doc.title or doc.filename
    return [entity_dict(e, name) for e in ents]


@router.get("/documents/{document_id}/spec-extraction")
def spec_extraction(document_id: str, db: Session = Depends(get_db)) -> dict:
    """ELECTRICAL SPECIFICATION EXTRACTION: scan the whole document and build
    structured lists (wire sizes, circuit protection, equipment, ratings...)
    where every item keeps its source."""
    doc = db.get(Document, document_id)
    if not doc:
        raise HTTPException(404, "Document not found")
    ents = db.execute(select(Entity).where(Entity.document_id == document_id).order_by(Entity.page_number, Entity.char_start)).scalars().all()
    name = doc.title or doc.filename
    groups = []
    for key, g in GROUPS.items():
        rows = [entity_dict(e, name) for e in ents if e.entity_type in g["types"]]
        groups.append({"key": key, "label": g["label"], "count": len(rows), "items": rows})
    structure = doc.structure or {}
    warnings = structure.get("warnings", [])
    groups.append({"key": "warnings", "label": "Warnings", "count": len(warnings), "items": [{"page": w["page"], "text": w["text"], "section": w.get("section"), "bbox": w.get("bbox")} for w in warnings]})
    return {
        "document": {"id": doc.id, "name": name, "manufacturer": doc.manufacturer, "model_number": doc.model_number, "document_type": doc.document_type},
        "groups": groups,
        "critical_flags": sum(1 for e in ents for f in (e.flags or []) if f.get("severity") == "critical"),
    }
