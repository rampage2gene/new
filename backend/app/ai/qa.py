"""Retrieval-augmented question answering with verified citations.

Flow: hybrid search -> entity lookup -> structured Claude answer -> citation
verification against the actual passages -> QC warnings attached. When the AI
layer is not configured (or fails), an *extractive* answer is returned: the
best-matching passages and entities with their sources, never a guess.
"""
from __future__ import annotations

import logging
import re
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Chunk, Document, Entity, QCFlag
from ..search.query import SearchHit, search
from .client import ai_available, structured_call
from .prompts import QA_SYSTEM

log = logging.getLogger(__name__)


class CitationOut(BaseModel):
    passage: int = Field(description="1-based passage number from the supplied context")
    quote: str = Field(description="Verbatim quote from that passage supporting the statement")
    note: str | None = Field(default=None, description="What this citation supports")


class AnswerOut(BaseModel):
    answer: str = Field(description="Markdown answer for the user")
    status: Literal["found", "partial", "not_found"]
    answer_kind: Literal["documented_fact", "calculation", "assumption", "engineering_interpretation", "mixed"]
    citations: list[CitationOut]
    conflicts: list[str] = Field(default_factory=list, description="Explicit conflicts between sources")
    verification_warnings: list[str] = Field(default_factory=list)
    follow_up_questions: list[str] = Field(default_factory=list)


def _normalise(s: str) -> str:
    return re.sub(r"[^a-z0-9/°²]+", " ", s.lower()).strip()


def _quote_in_passage(quote: str, passage: str) -> bool:
    q, p = _normalise(quote), _normalise(passage)
    if not q:
        return False
    if q in p:
        return True
    # Tolerate small OCR/formatting differences: require 80 % of the quote's tokens in order.
    qt = q.split()
    if len(qt) < 3:
        return q in p
    hits = sum(1 for t in qt if t in p)
    return hits / len(qt) >= 0.8


def _entity_rows(session: Session, hits: list[SearchHit], document_ids: list[str] | None, question: str) -> list[Entity]:
    """Entities that live inside the retrieved chunks (they carry the precise value + bbox)."""
    block_ids: set[str] = set()
    chunk_ids = [h.chunk_id for h in hits]
    if chunk_ids:
        for bids in session.execute(select(Chunk.block_ids).where(Chunk.id.in_(chunk_ids))).scalars():
            block_ids.update(bids or [])
    if not block_ids:
        return []
    stmt = select(Entity).where(Entity.block_id.in_(list(block_ids))).where(Entity.entity_type != "equipment")
    if document_ids:
        stmt = stmt.where(Entity.document_id.in_(document_ids))
    return session.execute(stmt.limit(60)).scalars().all()


def _context_block(hits: list[SearchHit], entities: list[Entity], flags_by_entity: dict[str, list[QCFlag]]) -> str:
    parts = []
    for n, h in enumerate(hits, 1):
        conf = ""
        parts.append(
            f"[Passage {n}] Document: {h.document_name} | Page {h.page_number} | Section: {h.section or '—'}{conf}\n{h.text.strip()}\n"
        )
    if entities:
        parts.append("Structured values extracted from these passages (with page):")
        for e in entities:
            flag_txt = ""
            fl = flags_by_entity.get(e.id) or []
            if fl:
                flag_txt = " ⚠ " + "; ".join(f.message for f in fl[:2])
            if e.ocr_confidence is not None and e.ocr_confidence < 0.9 and not fl:
                flag_txt = f" ⚠ low OCR confidence ({e.ocr_confidence:.0%})"
            desc = f"- {e.entity_type}: {e.value_text}"
            if e.qualifier:
                desc += f" ({e.qualifier})"
            if e.application:
                desc += f" — {e.application}"
            desc += f" [page {e.page_number}{', ' + e.section if e.section else ''}]{flag_txt}"
            parts.append(desc)
    return "\n".join(parts)


def _history_text(history: list[dict] | None) -> str:
    if not history:
        return ""
    lines = ["Previous conversation (for context only; cite passages from the current context):"]
    for turn in history[-6:]:
        role = turn.get("role", "user")
        content = str(turn.get("content", ""))[:1200]
        lines.append(f"{role}: {content}")
    return "\n".join(lines) + "\n\n"


def answer_question(session: Session, question: str, document_ids: list[str] | None = None, history: list[dict] | None = None) -> dict:
    settings = get_settings()
    pq, all_hits = search(session, question, document_ids, limit=settings.search_top_k)
    hits = [h for h in all_hits if h.strong]
    entities = _entity_rows(session, hits, document_ids, question)
    flags_by_entity: dict[str, list[QCFlag]] = {}
    if entities:
        for f in session.execute(select(QCFlag).where(QCFlag.entity_id.in_([e.id for e in entities]))).scalars():
            flags_by_entity.setdefault(f.entity_id, []).append(f)
    docs = {d.id: d for d in session.execute(select(Document).where(Document.id.in_({h.document_id for h in hits}))).scalars()} if hits else {}

    if not hits:
        return {
            "mode": "no_results",
            "answer": "I could not find this specification in the uploaded documentation." + ("" if document_ids or docs else " No processed documents are available yet - upload a manual first."),
            "status": "not_found",
            "answer_kind": "documented_fact",
            "citations": [],
            "conflicts": [],
            "verification_warnings": [],
            "entities": [],
            "passages": [],
            "query": _pq_dict(pq),
        }

    context = _context_block(hits, entities, flags_by_entity)
    passages = [_hit_dict(h, i + 1, docs.get(h.document_id)) for i, h in enumerate(hits)]
    entity_dicts = [_entity_dict(e, docs.get(e.document_id), flags_by_entity.get(e.id, [])) for e in entities]

    if ai_available():
        try:
            doc_summary = "; ".join(
                f"{d.title or d.filename} ({d.document_type or 'document'}{', ' + d.manufacturer if d.manufacturer else ''}{', model ' + d.model_number if d.model_number else ''})"
                for d in docs.values()
            )
            user = (
                f"{_history_text(history)}Documents available: {doc_summary}\n\n"
                f"Context passages:\n\n{context}\n\n"
                f"Question: {question}\n\n"
                "Answer using only the passages above. Cite passage numbers with verbatim quotes."
            )
            out: AnswerOut = structured_call(QA_SYSTEM, user, AnswerOut)
            return _finalise_ai_answer(out, hits, passages, entity_dicts, docs, pq)
        except Exception as exc:  # noqa: BLE001
            log.warning("AI answer failed, falling back to extractive mode: %s", exc)
            fallback = _extractive_answer(question, hits, passages, entity_dicts, pq)
            fallback["ai_error"] = str(exc)
            return fallback
    return _extractive_answer(question, hits, passages, entity_dicts, pq)


def _finalise_ai_answer(out: AnswerOut, hits: list[SearchHit], passages: list[dict], entity_dicts: list[dict], docs: dict, pq) -> dict:
    citations = []
    warnings = list(out.verification_warnings)
    for c in out.citations:
        idx = c.passage - 1
        if idx < 0 or idx >= len(hits):
            continue
        h = hits[idx]
        verified = _quote_in_passage(c.quote, h.text)
        citations.append(
            {
                "passage": c.passage,
                "document_id": h.document_id,
                "document_name": h.document_name,
                "page": h.page_number,
                "section": h.section,
                "chunk_id": h.chunk_id,
                "quote": c.quote,
                "note": c.note,
                "bbox": h.bbox,
                "verified": verified,
            }
        )
    verified_count = sum(1 for c in citations if c["verified"])
    status = out.status
    if status == "found" and verified_count == 0:
        status = "unverified"
        warnings.insert(0, "The answer's citations could not be verified against the document text. Treat the answer as unconfirmed and check the cited pages.")
    # Attach QC warnings for low-confidence values that were used.
    for e in entity_dicts:
        for f in e.get("flags", []):
            if f.get("severity") in ("critical", "warning") and f.get("message") not in warnings:
                warnings.append(f["message"])
    return {
        "mode": "ai",
        "answer": out.answer,
        "status": status,
        "answer_kind": out.answer_kind,
        "citations": citations,
        "conflicts": out.conflicts,
        "verification_warnings": warnings[:8],
        "follow_up_questions": out.follow_up_questions[:4],
        "entities": entity_dicts[:30],
        "passages": passages,
        "query": _pq_dict(pq),
    }


def _extractive_answer(question: str, hits: list[SearchHit], passages: list[dict], entity_dicts: list[dict], pq) -> dict:
    top = hits[:4]
    lines = []
    if pq.entity_types and entity_dicts:
        wanted = set(pq.entity_types)
        if "current" in wanted:
            wanted.update({"fuse", "breaker"})
        rows = [e for e in entity_dicts if e["entity_type"] in wanted]
        if rows:
            lines.append("Documented values matching your question:\n")
            lines.append("| Type | Value | Qualifier | Application | Source |")
            lines.append("|---|---|---|---|---|")
            for e in rows[:12]:
                src = f"{e['document_name']}, page {e['page']}" + (f", {e['section']}" if e.get("section") else "")
                lines.append(f"| {e['entity_type'].replace('_', ' ')} | {e['value_text']} | {e.get('qualifier') or '—'} | {e.get('application') or '—'} | {src} |")
            lines.append("")
    lines.append("Most relevant documented passages:\n")
    for i, h in enumerate(top, 1):
        snippet = re.sub(r"\s+", " ", h.text.strip())
        if len(snippet) > 420:
            snippet = snippet[:420] + "…"
        lines.append(f"{i}. **{h.document_name}**, page {h.page_number}{' — ' + h.section if h.section else ''}: “{snippet}”")
    lines.append("")
    lines.append("_AI reasoning is not configured (set `MDI_ANTHROPIC_API_KEY`), so this answer shows the documented passages and extracted values without interpretation._")
    citations = [
        {
            "passage": i + 1,
            "document_id": h.document_id,
            "document_name": h.document_name,
            "page": h.page_number,
            "section": h.section,
            "chunk_id": h.chunk_id,
            "quote": re.sub(r"\s+", " ", h.text.strip())[:200],
            "note": None,
            "bbox": h.bbox,
            "verified": True,
        }
        for i, h in enumerate(top)
    ]
    warnings = []
    for e in entity_dicts:
        for f in e.get("flags", []):
            if f.get("severity") in ("critical", "warning") and f["message"] not in warnings:
                warnings.append(f["message"])
    return {
        "mode": "extractive",
        "answer": "\n".join(lines),
        "status": "partial",
        "answer_kind": "documented_fact",
        "citations": citations,
        "conflicts": [],
        "verification_warnings": warnings[:8],
        "follow_up_questions": [],
        "entities": entity_dicts[:30],
        "passages": passages,
        "query": _pq_dict(pq),
    }


def _hit_dict(h: SearchHit, n: int, doc: Document | None) -> dict:
    return {
        "passage": n,
        "chunk_id": h.chunk_id,
        "document_id": h.document_id,
        "document_name": h.document_name,
        "page": h.page_number,
        "section": h.section,
        "text": h.text,
        "bbox": h.bbox,
        "score": h.score,
        "sources": h.sources,
        "highlights": h.highlights,
    }


def _entity_dict(e: Entity, doc: Document | None, flags: list[QCFlag]) -> dict:
    return {
        "id": e.id,
        "document_id": e.document_id,
        "document_name": (doc.title or doc.filename) if doc else "",
        "entity_type": e.entity_type,
        "value": e.value,
        "unit": e.unit,
        "value_text": e.value_text,
        "qualifier": e.qualifier,
        "application": e.application,
        "circuit": e.circuit,
        "equipment": e.equipment,
        "equipment_model": e.equipment_model,
        "device_type": e.device_type,
        "page": e.page_number,
        "section": e.section,
        "snippet": e.snippet,
        "bbox": [e.x0, e.y0, e.x1, e.y1],
        "confidence": e.confidence,
        "ocr_confidence": e.ocr_confidence,
        "is_critical": e.is_critical,
        "flags": [{"type": f.flag_type, "severity": f.severity, "message": f.message} for f in flags] or list(e.flags or []),
        "extra": e.extra or {},
    }


def _pq_dict(pq) -> dict:
    return {"entity_types": pq.entity_types, "value": pq.value, "unit": pq.unit, "expansions": {k: sorted(v) for k, v in pq.expansions.items()}}
