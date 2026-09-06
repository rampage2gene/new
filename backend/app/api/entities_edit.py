"""Filling in and confirming values: the human rung of the verification ladder."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import get_db
from ..extraction import patterns as P
from ..extraction.verify import candidates_from_text
from ..models import Document, Entity, QCFlag
from .serializers import entity_dict

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["entities"])

# Flags about how a value was read; moot once the user has spoken.
READING_FLAGS = ("low_ocr_confidence", "reading_conflict", "reading_unverified", "reading_corrected", "discrepancy")


class EntityEdit(BaseModel):
    value_text: str | None = Field(default=None, max_length=128, description="the value as it should read, e.g. '125 A'; empty clears it")
    verified: bool | None = Field(default=None, description="tick or untick the value as confirmed")


def _set_value(e: Entity, extra: dict, text: str) -> None:
    """Store a typed value with the same normalisation the extractor applies."""
    picked = candidates_from_text(text, e.page_number, e.entity_type)
    if picked:
        p = picked[0]
        e.value, e.unit, e.value_text = p.value, p.unit or e.unit, p.value_text
        for key in ("awg", "nm_equivalent", "range"):
            if key in p.extra:
                extra[key] = p.extra[key]
    else:
        e.value = P.parse_number(text)
        e.value_text = text


def _remember_machine_reading(verification: dict, e: Entity) -> None:
    """Keep what the readers concluded so an untick can restore it."""
    if "before_user" not in verification:
        verification["before_user"] = {
            "status": verification.get("status"),
            "note": verification.get("note"),
            "confidence": e.confidence,
            "value_text": e.value_text,
            "value": e.value,
            "unit": e.unit,
        }


@router.patch("/entities/{entity_id}")
def edit_entity(entity_id: str, body: EntityEdit, db: Session = Depends(get_db)) -> dict:
    e = db.get(Entity, entity_id)
    if e is None:
        raise HTTPException(404, "Value not found")
    extra = dict(e.extra or {})
    verification = dict(extra.get("verification") or {})
    now = datetime.now(timezone.utc).isoformat()

    if body.value_text is not None:
        text = body.value_text.strip()
        _remember_machine_reading(verification, e)
        verification.setdefault("original", e.value_text)
        if text:
            _set_value(e, extra, text)
            e.verified, e.confidence = True, 1.0
            verification.update(status="user", note="filled in by you", at=now)
        else:
            e.value, e.value_text, e.verified, e.confidence = None, "", False, 0.0
            verification.update(status="to_fill", note="cleared", at=now)
    elif body.verified is True:
        if not e.value_text:
            raise HTTPException(400, "Fill in a value before confirming it")
        _remember_machine_reading(verification, e)
        e.verified, e.confidence = True, 1.0
        verification.update(status="user", note="confirmed by you", at=now)
    elif body.verified is False:
        before = verification.pop("before_user", None) or {}
        e.verified = False
        e.confidence = float(before.get("confidence", e.confidence if e.value_text else 0.0))
        if before.get("value_text") is not None:
            e.value_text, e.value, e.unit = before["value_text"], before["value"], before["unit"]
        verification["status"] = before.get("status") or ("single" if e.ocr_confidence is not None else "embedded")
        if before.get("note"):
            verification["note"] = before["note"]
        else:
            verification.pop("note", None)
        verification["at"] = now
    else:
        raise HTTPException(400, "Nothing to change")

    if e.verified:
        e.flags = [f for f in (e.flags or []) if f.get("type") not in READING_FLAGS]
        for flag in db.query(QCFlag).filter(QCFlag.entity_id == e.id, QCFlag.flag_type.in_(READING_FLAGS)):
            flag.resolved = True
    extra["verification"] = verification
    e.extra = extra
    db.flush()
    _refresh_counts(db, e.document_id)
    db.commit()
    log.info("value %s edited: %s", e.id, {k: v for k, v in body.model_dump().items() if v is not None})
    from ..exports.auto import schedule_export

    schedule_export(e.document_id)
    doc = db.get(Document, e.document_id)
    return entity_dict(e, (doc.title or doc.filename) if doc else None)


def _refresh_counts(db: Session, document_id: str) -> None:
    doc = db.get(Document, document_id)
    if not doc:
        return
    ents = db.query(Entity).filter(Entity.document_id == document_id).all()
    stats = dict(doc.stats or {})
    stats["to_fill"] = sum(1 for x in ents if ((x.extra or {}).get("verification") or {}).get("status") == "to_fill")
    stats["verified_by_user"] = sum(1 for x in ents if x.verified)
    doc.stats = stats
