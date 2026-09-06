"""Search, question answering, comparison, diagrams."""
from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..ai.compare import compare_documents
from ..ai.diagrams import analyse_page
from ..ai.qa import answer_question
from ..config import get_settings
from ..db import get_db
from ..search.query import search as run_search

router = APIRouter(prefix="/api", tags=["search"])


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    document_ids: list[str] | None = None
    limit: int = Field(default=12, ge=1, le=50)


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    document_ids: list[str] | None = None
    history: list[dict] | None = None


class CompareRequest(BaseModel):
    document_ids: list[str] = Field(min_length=2, max_length=8)
    question: str | None = None


@router.post("/search")
def search_endpoint(req: SearchRequest, db: Session = Depends(get_db)) -> dict:
    pq, hits = run_search(db, req.query, req.document_ids, req.limit)
    return {
        "query": {"raw": pq.raw, "entity_types": pq.entity_types, "value": pq.value, "unit": pq.unit, "expansions": {k: sorted(v) for k, v in pq.expansions.items()}},
        "hits": [asdict(h) for h in hits],
    }


@router.post("/ask")
def ask_endpoint(req: AskRequest, db: Session = Depends(get_db)) -> dict:
    return answer_question(db, req.question, req.document_ids, req.history)


@router.post("/compare")
def compare_endpoint(req: CompareRequest, db: Session = Depends(get_db)) -> dict:
    return compare_documents(db, req.document_ids, req.question)


@router.post("/documents/{document_id}/pages/{page_number}/diagram")
def diagram_endpoint(document_id: str, page_number: int, force: bool = False, db: Session = Depends(get_db)) -> dict:
    try:
        result = analyse_page(db, document_id, page_number, force=force)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    db.commit()
    return result


@router.get("/documents/{document_id}/pages/{page_number}/diagram")
def diagram_get(document_id: str, page_number: int, db: Session = Depends(get_db)) -> dict:
    from sqlalchemy import select

    from ..models import DiagramAnalysis

    rec = db.execute(select(DiagramAnalysis).where(DiagramAnalysis.document_id == document_id, DiagramAnalysis.page_number == page_number)).scalar_one_or_none()
    if not rec:
        raise HTTPException(404, "No analysis for this page yet")
    from ..ai.diagrams import _out

    return _out(rec)


@router.get("/status")
def status_endpoint() -> dict:
    from ..ai.client import ai_available
    from ..ocr.engine import get_ocr_engine
    from ..search.semantic import get_embedding_provider

    s = get_settings()
    return {
        "ocr_engine": get_ocr_engine().name,
        "ai_available": ai_available(),
        "ai_model": s.ai_model if ai_available() else None,
        "embedding_provider": get_embedding_provider().name,
        "version": "0.1.0",
    }
