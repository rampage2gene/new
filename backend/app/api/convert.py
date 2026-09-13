"""Document exports (searchable PDF, report PDF, text/Markdown/JSON) and
stateless file conversions."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..exports import convert as C
from ..exports.pdf import build_report_pdf, searchable_pdf
from ..models import Document

router = APIRouter(prefix="/api", tags=["convert"])

MEDIA = {
    "pdf": "application/pdf",
    "txt": "text/plain; charset=utf-8",
    "md": "text/markdown; charset=utf-8",
    "json": "application/json",
    "zip": "application/zip",
}


def _download(data: bytes, filename: str, kind: str) -> Response:
    return Response(data, media_type=MEDIA[kind], headers={"Content-Disposition": f'attachment; filename="{filename}"'})


def _stem(name: str | None) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", Path(name or "document").stem) or "document"


def _get_ready_doc(db: Session, document_id: str) -> Document:
    doc = db.get(Document, document_id)
    if not doc:
        raise HTTPException(404, "Document not found")
    if doc.status != "ready":
        raise HTTPException(409, f"Document is {doc.status}; exports are available once processing has finished")
    return doc


async def _read_upload(up: UploadFile) -> bytes:
    limit = get_settings().max_upload_mb * (1 << 20)
    data = await up.read()
    if len(data) > limit:
        raise HTTPException(413, f"{up.filename} exceeds the {get_settings().max_upload_mb} MB upload limit")
    return data


# --------------------------------------------------------------------------- per-document exports

@router.get("/documents/{document_id}/export/searchable-pdf")
def export_searchable_pdf(document_id: str, db: Session = Depends(get_db)) -> Response:
    """The original file with an invisible OCR text layer so scanned pages
    become selectable and searchable in any PDF viewer."""
    doc = _get_ready_doc(db, document_id)
    try:
        data = searchable_pdf(db, doc)
    except FileNotFoundError:
        raise HTTPException(404, "Original file missing")
    return _download(data, f"{_stem(doc.filename)}_searchable.pdf", "pdf")


@router.get("/documents/{document_id}/export/report.pdf")
def export_document_report(
    document_id: str,
    sections: str = Query(default="spec_extraction,qc", description="comma-separated: spec_extraction, qc"),
    db: Session = Depends(get_db),
) -> Response:
    doc = _get_ready_doc(db, document_id)
    parts = {p.strip() for p in sections.split(",") if p.strip()}
    data = build_report_pdf(db, [doc], parts)
    return _download(data, f"{_stem(doc.filename)}_report.pdf", "pdf")


class ReportRequest(BaseModel):
    document_ids: list[str] = []
    sections: list[str] = ["spec_extraction"]
    calculations: list[dict[str, Any]] = []
    answer: dict[str, Any] | None = None
    title: str | None = None


@router.post("/export/report.pdf")
def export_report(req: ReportRequest, db: Session = Depends(get_db)) -> Response:
    """A PDF report combining extracted specifications, verification flags,
    calculator results (as returned by /calculators/{id}/run) and an answer."""
    docs = []
    for did in req.document_ids:
        docs.append(_get_ready_doc(db, did))
    if not docs and not req.calculations and not req.answer:
        raise HTTPException(422, "Nothing to report: give document_ids, calculations or an answer")
    data = build_report_pdf(db, docs, set(req.sections), req.calculations, req.answer, req.title)
    return _download(data, "report.pdf", "pdf")


@router.get("/documents/{document_id}/export/{fmt}")
def export_document_text(document_id: str, fmt: str, words: bool = False, db: Session = Depends(get_db)) -> Response:
    """The processed document as plain text, Markdown (headings, tables,
    warnings) or JSON (pages, blocks, structure)."""
    if fmt not in C.TEXT_FORMATS:
        raise HTTPException(404, f"Unknown export format '{fmt}'. Use txt, md, json, searchable-pdf or report.pdf")
    doc = _get_ready_doc(db, document_id)
    stem = _stem(doc.filename)
    if fmt == "txt":
        return _download(C.document_to_text(db, doc).encode("utf-8"), f"{stem}.txt", "txt")
    if fmt == "md":
        return _download(C.document_to_markdown(db, doc).encode("utf-8"), f"{stem}.md", "md")
    return _download(C.to_json_bytes(C.document_to_json(db, doc, words=words)), f"{stem}.json", "json")


# --------------------------------------------------------------------------- stateless conversions

@router.post("/convert")
async def convert_files(
    files: list[UploadFile] = File(...),
    to: str = Form(...),
    ocr: bool = Form(default=True),
    dpi: int | None = Form(default=None),
) -> Response:
    """Convert without ingesting. `to`: pdf (images and PDFs -> one PDF),
    txt, md, json (PDF -> text with OCR for scanned pages), png (PDF -> zip of page images)."""
    to = to.lower().strip()
    if to not in {"pdf", "txt", "md", "json", "png"}:
        raise HTTPException(422, "to must be one of pdf, txt, md, json, png")
    payloads = [(up.filename or "file", await _read_upload(up)) for up in files]
    if to == "pdf":
        try:
            return _download(C.images_to_pdf(payloads), f"{_stem(payloads[0][0]) if len(payloads) == 1 else 'combined'}.pdf", "pdf")
        except Exception as exc:  # unsupported image / corrupt file
            raise HTTPException(415, f"Could not convert to PDF: {exc}") from exc
    if len(payloads) != 1:
        raise HTTPException(422, f"Converting to {to} takes exactly one PDF")
    name, data = payloads[0]
    if not data.startswith(b"%PDF"):
        # Allow images too: turn them into a PDF first so they can be OCR'd/rendered.
        try:
            data = C.images_to_pdf([(name, data)])
        except Exception as exc:
            raise HTTPException(415, f"Not a PDF or supported image: {exc}") from exc
    stem = _stem(name)
    if to == "txt":
        return _download(C.pdf_to_text(data, ocr=ocr).encode("utf-8"), f"{stem}.txt", "txt")
    if to == "md":
        return _download(C.pdf_to_markdown(data, ocr=ocr).encode("utf-8"), f"{stem}.md", "md")
    if to == "json":
        return _download(C.to_json_bytes(C.pdf_to_json(data, ocr=ocr)), f"{stem}.json", "json")
    return _download(C.pdf_to_png_zip(data, dpi), f"{stem}_pages.zip", "zip")


@router.post("/convert/merge")
async def merge_files(files: list[UploadFile] = File(...)) -> Response:
    """Merge PDFs (and images, one page each) into one PDF, in upload order."""
    payloads = [(up.filename or "file", await _read_upload(up)) for up in files]
    if len(payloads) < 2:
        raise HTTPException(422, "Upload at least two files to merge")
    try:
        return _download(C.images_to_pdf(payloads), "merged.pdf", "pdf")
    except Exception as exc:
        raise HTTPException(415, f"Could not merge: {exc}") from exc


@router.post("/convert/split")
async def split_file(file: UploadFile = File(...), ranges: str | None = Form(default=None)) -> Response:
    """Split a PDF into a zip of PDFs. `ranges` like "1-3,5,7-" (default: one file per page)."""
    data = await _read_upload(file)
    if not data.startswith(b"%PDF"):
        raise HTTPException(415, "Split needs a PDF")
    try:
        return _download(C.split_pdf(data, ranges, file.filename or "document"), f"{_stem(file.filename)}_split.zip", "zip")
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
