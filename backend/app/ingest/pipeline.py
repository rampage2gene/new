"""Document processing pipeline.

    upload -> identify -> read (embedded text | OCR) -> layout analysis ->
    metadata -> entity extraction -> QC validation -> chunk + index -> ready
"""
from __future__ import annotations

import logging
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import delete, select

from ..config import get_settings
from ..db import session_scope
from ..extraction.entities import extract_entities
from ..extraction.invoices import extract_invoice
from ..extraction.verify import verify_entities
from ..models import Block, Chunk, Document, Entity, Invoice, Page, QCFlag, DiagramAnalysis, new_id
from ..qc.validate import QCFlagData, validate_entities
from ..search.index import build_chunks, index_chunks, remove_document_index
from ..structure.layout import analyse_layout
from ..structure.metadata import detect_metadata
from .identify import identify_file
from .images import read_image
from .pdf import read_pdf
from .types import RawPage

log = logging.getLogger(__name__)
_executor: ThreadPoolExecutor | None = None
_lock = threading.Lock()


def submit(document_id: str) -> None:
    """Queue a document for processing (or process inline when configured)."""
    global _executor
    settings = get_settings()
    if not settings.background_processing:
        process_document(document_id)
        return
    if _executor is None:
        _executor = ThreadPoolExecutor(max_workers=settings.ingest_workers, thread_name_prefix="ingest")
    _executor.submit(process_document, document_id)


def _set_progress(document_id: str, message: str, status: str | None = None) -> None:
    with session_scope() as s:
        doc = s.get(Document, document_id)
        if doc:
            doc.progress = message
            if status:
                doc.status = status


def process_document(document_id: str) -> None:
    try:
        _set_progress(document_id, "Identifying file", "processing")
        with session_scope() as s:
            doc = s.get(Document, document_id)
            if not doc:
                return
            path = Path(doc.storage_path)
            filename = doc.filename
            file_type = doc.file_type
        pages = _read_pages(path, file_type, document_id)
        _set_progress(document_id, "Analysing document structure")
        structure = analyse_layout(pages)
        meta = detect_metadata(pages, filename)
        _set_progress(document_id, "Extracting technical entities")
        entities = extract_entities(pages)
        verification = None
        vflags: list = []
        if get_settings().verify:
            _set_progress(document_id, "Checking every value against a second reading")
            report, vflags = verify_entities(pages, entities, source_path=str(path), file_type=file_type)
            verification = report.as_dict()
        _set_progress(document_id, "Validating critical values")
        flags = validate_entities(entities) + vflags + _reader_flags(pages)
        invoice = None
        if meta.get("document_type") in ("Invoice", "Receipt"):
            invoice = extract_invoice(pages, meta.get("manufacturer"))
        _set_progress(document_id, "Indexing")
        with _lock:
            _persist(document_id, pages, structure, meta, entities, flags, invoice, verification)
        _set_progress(document_id, "Ready", "ready")
        if get_settings().auto_export:
            _set_progress(document_id, "Writing the exports folder")
            try:
                from ..exports.auto import export_document_by_id

                export_document_by_id(document_id)
            except Exception as exc:  # noqa: BLE001 - exports never fail a document
                log.warning("auto export failed for %s: %s", document_id, exc)
            _set_progress(document_id, "Ready", "ready")
    except Exception as exc:  # noqa: BLE001
        log.error("Processing failed for %s: %s\n%s", document_id, exc, traceback.format_exc())
        with session_scope() as s:
            doc = s.get(Document, document_id)
            if doc:
                doc.status = "failed"
                doc.error = f"{type(exc).__name__}: {exc}"
                doc.progress = "Failed"


_READER_NAMES = {"rapidocr": "RapidOCR", "tesseract": "Tesseract"}


def _reader_flags(pages: list[RawPage]) -> list[QCFlagData]:
    """A page whose second reader stopped still finishes, but its values rest
    on one reading. Say so, per page, where the checks are listed, with the
    page a click away."""
    flags: list[QCFlagData] = []
    for p in pages:
        if not p.reader_stopped:
            continue
        stopped = _READER_NAMES.get(p.reader_stopped, p.reader_stopped)
        if p.ocr_engine:
            read_by = _READER_NAMES.get(p.ocr_engine, p.ocr_engine)
            message = (
                f"The {stopped} reader stopped while reading page {p.page_number}, so only {read_by} read it and its "
                f"values rest on a single reading. Open the page and check them; processing the document again (\u21bb) "
                f"reads it with both readers."
            )
        else:
            message = (
                f"The {stopped} reader stopped while reading page {p.page_number} and no other reader was available, "
                f"so the page has no text. Process the document again (\u21bb) to read it."
            )
        flags.append(QCFlagData("reader_stopped", "warning", message, page_number=p.page_number,
                                details={"reader": p.reader_stopped, "read_by": p.ocr_engine}))
    skipped = [p for p in pages if p.reader_skipped]
    if skipped:
        first, last = skipped[0].page_number, skipped[-1].page_number
        reader = _READER_NAMES.get(skipped[0].reader_skipped, skipped[0].reader_skipped)
        span = f"page {first}" if first == last else f"pages {first}\u2013{last}"
        others = sorted({_READER_NAMES.get(p.ocr_engine, p.ocr_engine) for p in skipped if p.ocr_engine})
        by = f"{' and '.join(others)} alone" if others else "no reader at all"
        flags.append(QCFlagData(
            "reader_stopped", "warning",
            f"The {reader} reader stopped {get_settings().ocr_max_stops_per_document} times in this document, so {span} "
            f"were read by {by}. Their values rest on a single reading: check them against the page, or process the "
            f"document again (\u21bb) once the reader is back.",
            page_number=first, details={"reader": skipped[0].reader_skipped, "pages": [p.page_number for p in skipped]},
        ))
    return flags


def _read_pages(path: Path, file_type: str, document_id: str) -> list[RawPage]:
    def progress(msg: str) -> None:
        _set_progress(document_id, msg)

    if file_type == "pdf":
        return read_pdf(path, document_id, progress)
    if file_type == "image":
        return read_image(path, document_id, progress)
    ident = identify_file(path)
    if ident.file_type == "pdf":
        return read_pdf(path, document_id, progress)
    if ident.file_type == "image":
        return read_image(path, document_id, progress)
    raise ValueError("Unsupported file type; upload a PDF or an image (PNG, JPEG, TIFF, BMP, WEBP)")


def _edit_key(entity_type: str, page_number: int, x0: float, y0: float) -> tuple:
    """Where a value sits on its page: how a user's edit finds the same value again after reprocessing."""
    return (entity_type, page_number, round(x0 / 20), round(y0 / 20))


def _collect_user_edits(s, document_id: str) -> dict[tuple, dict]:
    """Values the user confirmed or filled in; they must survive a reprocess."""
    edits: dict[tuple, dict] = {}
    for e in s.execute(select(Entity).where(Entity.document_id == document_id, Entity.verified.is_(True))).scalars():
        edits[_edit_key(e.entity_type, e.page_number, e.x0, e.y0)] = {
            "value": e.value, "unit": e.unit, "value_text": e.value_text,
            "verification": (e.extra or {}).get("verification") or {"status": "user"},
        }
    return edits


def _persist(document_id: str, pages: list[RawPage], structure: dict, meta: dict, entities, flags, invoice, verification: dict | None = None) -> None:
    with session_scope() as s:
        doc = s.get(Document, document_id)
        if not doc:
            return
        user_edits = _collect_user_edits(s, document_id)
        # Clear any previous processing output (re-processing support).
        remove_document_index(s, document_id)
        for model in (Page, Block, Chunk, Entity, QCFlag, Invoice, DiagramAnalysis):
            s.execute(delete(model).where(model.document_id == document_id))
        s.flush()

        block_ids: dict[tuple[int, int], str] = {}
        block_objs: list[Block] = []
        for page in pages:
            s.add(
                Page(
                    document_id=document_id,
                    page_number=page.page_number,
                    width=page.width,
                    height=page.height,
                    text_source=page.text_source,
                    ocr_confidence=page.ocr_confidence,
                    is_diagram=page.is_diagram,
                    diagram_score=page.diagram_score,
                    image_path=page.image_path,
                    text=page.text,
                    char_count=page.char_count,
                    page_label=page.page_label,
                    ocr_engine=page.ocr_engine,
                    alt_ocr_engine=page.alt_ocr_engine,
                    alt_ocr=page.alt_ocr,
                )
            )
            for i, b in enumerate(page.blocks):
                blk = Block(
                    id=new_id(),
                    document_id=document_id,
                    page_number=page.page_number,
                    order_index=i,
                    block_type=b.block_type,
                    text=b.text,
                    x0=b.bbox[0], y0=b.bbox[1], x1=b.bbox[2], y1=b.bbox[3],
                    section=b.section,
                    section_level=b.section_level,
                    source=b.source,
                    confidence=b.confidence,
                    words=b.words,
                    table=b.table,
                )
                s.add(blk)
                block_objs.append(blk)
                block_ids[(page.page_number, i)] = blk.id
        s.flush()

        entity_objs: list[Entity] = []
        restored: set[int] = set()
        for e_idx, e in enumerate(entities):
            edit = user_edits.get(_edit_key(e.entity_type, e.page_number, e.bbox[0], e.bbox[1]))
            if edit:
                # The user's word beats every reading.
                e.value, e.unit, e.value_text = edit["value"], edit["unit"], edit["value_text"]
                e.confidence = 1.0
                e.extra = {**e.extra, "verification": edit["verification"]}
                e.flags = [f for f in e.flags if f.get("type") not in ("low_ocr_confidence", "reading_conflict")]
                restored.add(e_idx)
            ent = Entity(
                id=new_id(),
                document_id=document_id,
                page_number=e.page_number,
                block_id=block_ids.get((e.page_number, e.block_index)),
                entity_type=e.entity_type,
                value=e.value,
                unit=e.unit,
                value_text=e.value_text,
                raw_text=e.raw_text,
                qualifier=e.qualifier,
                application=e.application,
                circuit=e.circuit,
                equipment=e.equipment,
                equipment_model=e.equipment_model,
                device_type=e.device_type,
                section=e.section,
                snippet=e.snippet,
                char_start=e.char_start,
                char_end=e.char_end,
                x0=e.bbox[0], y0=e.bbox[1], x1=e.bbox[2], y1=e.bbox[3],
                confidence=e.confidence,
                ocr_confidence=e.ocr_confidence,
                is_critical=e.is_critical,
                verified=e_idx in restored,
                flags=e.flags,
                extra=e.extra,
            )
            s.add(ent)
            entity_objs.append(ent)
        s.flush()
        if restored:
            flags = [f for f in flags if not (f.entity_index in restored and f.flag_type in ("low_ocr_confidence", "reading_conflict", "reading_unverified"))]
            if verification:
                verification["to_fill"] = sum(1 for e in entities if (e.extra.get("verification") or {}).get("status") == "to_fill")
        for f in flags:
            s.add(
                QCFlag(
                    document_id=document_id,
                    entity_id=entity_objs[f.entity_index].id if f.entity_index is not None else None,
                    page_number=f.page_number,
                    severity=f.severity,
                    flag_type=f.flag_type,
                    message=f.message,
                    details=f.details,
                )
            )
        chunks = build_chunks(document_id, pages, block_ids)
        for c in chunks:
            s.add(c)
        s.flush()
        index_chunks(s, chunks)

        if invoice is not None:
            s.add(
                Invoice(
                    document_id=document_id,
                    vendor=invoice.vendor,
                    invoice_number=invoice.invoice_number,
                    invoice_date=invoice.invoice_date,
                    currency=invoice.currency,
                    subtotal=invoice.subtotal,
                    tax=invoice.tax,
                    total=invoice.total,
                    line_items=[li.__dict__ for li in invoice.line_items],
                    confidence=invoice.confidence,
                )
            )

        doc.page_count = len(pages)
        doc.ocr_pages = sum(1 for p in pages if p.text_source == "ocr")
        doc.embedded_text_pages = sum(1 for p in pages if p.text_source == "embedded")
        doc.title = meta.get("title")
        doc.manufacturer = meta.get("manufacturer")
        doc.product = meta.get("product")
        doc.model_number = meta.get("model_number")
        doc.document_type = meta.get("document_type")
        doc.revision = meta.get("revision")
        doc.publication_date = meta.get("publication_date")
        doc.equipment_types = meta.get("equipment_types", [])
        doc.structure = structure
        counts: dict[str, int] = {}
        for e in entities:
            counts[e.entity_type] = counts.get(e.entity_type, 0) + 1
        doc.stats = {
            "entities": counts,
            "qc_flags": len(flags),
            "critical_flags": sum(1 for f in flags if f.severity == "critical"),
            "chunks": len(chunks),
            "blocks": len(block_objs),
            "avg_ocr_confidence": _avg([p.ocr_confidence for p in pages if p.ocr_confidence is not None]),
            "ocr_engines": sorted({p.ocr_engine for p in pages if p.ocr_engine}),
            "verification": verification,
            "to_fill": (verification or {}).get("to_fill", 0),
            "verified_by_user": len(restored),
        }
        doc.processed_at = datetime.now(timezone.utc)
        doc.error = None


def _avg(vals: list[float]) -> float | None:
    return round(sum(vals) / len(vals), 3) if vals else None
