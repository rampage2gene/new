"""Serialisation helpers shared by routes."""
from __future__ import annotations

from ..models import Block, Document, Entity, Page, QCFlag


def document_summary(d: Document) -> dict:
    return {
        "id": d.id,
        "filename": d.filename,
        "title": d.title or d.filename,
        "file_type": d.file_type,
        "mime_type": d.mime_type,
        "size_bytes": d.size_bytes,
        "status": d.status,
        "progress": d.progress,
        "error": d.error,
        "page_count": d.page_count,
        "ocr_pages": d.ocr_pages,
        "embedded_text_pages": d.embedded_text_pages,
        "manufacturer": d.manufacturer,
        "product": d.product,
        "model_number": d.model_number,
        "document_type": d.document_type,
        "revision": d.revision,
        "publication_date": d.publication_date,
        "equipment_types": d.equipment_types or [],
        "stats": d.stats or {},
        "uploaded_at": d.uploaded_at.isoformat() if d.uploaded_at else None,
        "processed_at": d.processed_at.isoformat() if d.processed_at else None,
    }


def document_detail(d: Document) -> dict:
    out = document_summary(d)
    out["structure"] = d.structure or {}
    return out


def page_summary(p: Page) -> dict:
    return {
        "page_number": p.page_number,
        "width": p.width,
        "height": p.height,
        "text_source": p.text_source,
        "ocr_confidence": p.ocr_confidence,
        "is_diagram": p.is_diagram,
        "diagram_score": p.diagram_score,
        "page_label": p.page_label,
        "char_count": p.char_count,
    }


def block_dict(b: Block, include_words: bool = False) -> dict:
    d = {
        "id": b.id,
        "page_number": b.page_number,
        "order_index": b.order_index,
        "block_type": b.block_type,
        "text": b.text,
        "bbox": [b.x0, b.y0, b.x1, b.y1],
        "section": b.section,
        "section_level": b.section_level,
        "source": b.source,
        "confidence": b.confidence,
        "table": b.table,
    }
    if include_words:
        d["words"] = b.words
    return d


def entity_dict(e: Entity, doc_name: str | None = None) -> dict:
    return {
        "id": e.id,
        "document_id": e.document_id,
        "document_name": doc_name,
        "entity_type": e.entity_type,
        "value": e.value,
        "unit": e.unit,
        "value_text": e.value_text,
        "raw_text": e.raw_text,
        "qualifier": e.qualifier,
        "application": e.application,
        "circuit": e.circuit,
        "equipment": e.equipment,
        "equipment_model": e.equipment_model,
        "device_type": e.device_type,
        "page": e.page_number,
        "section": e.section,
        "snippet": e.snippet,
        "block_id": e.block_id,
        "bbox": [e.x0, e.y0, e.x1, e.y1],
        "confidence": e.confidence,
        "ocr_confidence": e.ocr_confidence,
        "is_critical": e.is_critical,
        "verified": bool(e.verified),
        "verification": (e.extra or {}).get("verification") or {"status": "single" if e.ocr_confidence is not None else "embedded"},
        "flags": e.flags or [],
        "extra": e.extra or {},
    }


STATUS_LABELS = {
    "confirmed": "confirmed",
    "corrected": "corrected",
    "ai_confirmed": "confirmed (AI read the page)",
    "ai_corrected": "corrected (AI read the page)",
    "user": "confirmed by you",
    "to_fill": "TO FILL IN",
    "unverified": "one reading only",
    "single": "one reading only",
    "embedded": "from the PDF text",
}


def verification_note(d: dict) -> str:
    """One line for spreadsheets and reports: how the value was checked."""
    v = d.get("verification") or {}
    status = v.get("status") or ("embedded" if d.get("ocr_confidence") is None else "single")
    parts = [STATUS_LABELS.get(status, status)]
    if v.get("note") and status not in ("user",):
        parts.append(v["note"])
    readings = v.get("readings") or {}
    seen = [r for r in readings.values() if r]
    if status == "to_fill" and seen:
        parts.append("read as " + " / ".join(dict.fromkeys(seen)))
    elif status in ("corrected", "ai_corrected", "user") and v.get("original") and v["original"] != d.get("value_text"):
        parts.append(f"was '{v['original']}'")
    return "; ".join(parts)


def flag_dict(f: QCFlag) -> dict:
    return {
        "id": f.id,
        "document_id": f.document_id,
        "entity_id": f.entity_id,
        "page": f.page_number,
        "severity": f.severity,
        "flag_type": f.flag_type,
        "message": f.message,
        "details": f.details or {},
        "resolved": f.resolved,
    }
