"""Document library, viewer data and page images."""
from __future__ import annotations

import logging
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..ingest import pipeline
from ..ingest.identify import identify_file
from ..models import Block, Document, Page, QCFlag
from ..storage.files import delete_document_files, sha256_of, store_original
from .lan import is_loopback
from .serializers import block_dict, document_detail, document_summary, flag_dict, page_summary

router = APIRouter(prefix="/api/documents", tags=["documents"])

log = logging.getLogger(__name__)


def create_document_from_file(db: Session, path: Path, filename: str, size: int | None = None) -> Document:
    """Register a file that is already on disk and queue it for processing.

    Every way a document can arrive - the multipart upload, a path from the
    native Open dialog, a file copied into the inbox folder - ends here, so
    identification, hashing, storage and queuing are the same for all of them.
    Raises HTTPException(415) for anything that is not a PDF or an image.
    """
    ident = identify_file(path, filename)
    if size is None:
        size = path.stat().st_size
    log.info("ingest: %s (%d bytes, %s)", filename, size, ident.file_type)
    if ident.file_type == "unknown":
        log.warning("ingest rejected: %s is not a PDF or an image (%s)", filename, ident.mime_type)
        raise HTTPException(415, f"{filename}: unsupported file type. Upload a PDF or an image.")
    doc = Document(
        filename=filename,
        file_type=ident.file_type,
        mime_type=ident.mime_type,
        size_bytes=size,
        sha256=sha256_of(path),
        storage_path="",
        status="queued",
        progress="Queued",
    )
    db.add(doc)
    db.flush()
    doc.storage_path = str(store_original(doc.id, path, doc.filename))
    db.commit()
    pipeline.submit(doc.id)
    log.info("ingest: queued %s as document %s", doc.filename, doc.id)
    return doc


@router.post("", status_code=201)
async def upload_documents(files: list[UploadFile] = File(...), db: Session = Depends(get_db)) -> list[dict]:
    settings = get_settings()
    created: list[dict] = []
    # Log every arrival. When an upload fails in the desktop app this is what
    # separates "the browser never sent the file" (nothing here) from "the
    # server rejected it" (a line here saying why).
    log.info("upload: %d file(s): %s", len(files), ", ".join(f.filename or "?" for f in files))
    for up in files:
        with tempfile.NamedTemporaryFile(delete=False, suffix=Path(up.filename or "upload").suffix) as tmp:
            size = 0
            while True:
                chunk = await up.read(1 << 20)
                if not chunk:
                    break
                size += len(chunk)
                if size > settings.max_upload_mb * (1 << 20):
                    tmp.close()
                    Path(tmp.name).unlink(missing_ok=True)
                    log.warning("upload rejected: %s exceeds the %d MB limit", up.filename, settings.max_upload_mb)
                    raise HTTPException(413, f"{up.filename} exceeds the {settings.max_upload_mb} MB upload limit")
                tmp.write(chunk)
            tmp_path = Path(tmp.name)
        try:
            log.info("upload: received %s (%d bytes, %s)", up.filename, size, up.content_type or "no content-type")
            doc = create_document_from_file(db, tmp_path, up.filename or tmp_path.name, size)
            created.append(document_summary(doc))
        finally:
            tmp_path.unlink(missing_ok=True)
    return created


class ImportRequest(BaseModel):
    paths: list[str] = Field(..., min_length=1, max_length=200)


@router.post("/import", status_code=201)
def import_documents(request: Request, req: ImportRequest, db: Session = Depends(get_db)) -> list[dict]:
    """Ingest files by local path - what the desktop app's Open dialog uses.

    The bytes never travel through the web view: the server reads them off the
    disk itself. A path the user just picked in a native dialog needs no more
    checking than "is it a file", so this route names files on the computer's
    own disk and is refused to everything but the computer itself; a phone on
    the network uploads its pages instead.
    """
    if not is_loopback(request):
        raise HTTPException(403, "Files can only be imported by path on the computer running the app.")
    log.info("import: %d path(s): %s", len(req.paths), ", ".join(req.paths))
    created: list[dict] = []
    for raw in req.paths:
        path = Path(raw).expanduser()
        if not path.is_file():
            log.warning("import rejected: %s is not a file", raw)
            raise HTTPException(400, f"Not a file: {raw}")
        doc = create_document_from_file(db, path, path.name)
        created.append(document_summary(doc))
    return created


@router.post("/scan", status_code=201)
async def scan_pages(
    pages: list[UploadFile] = File(...),
    name: str | None = Form(None),
    db: Session = Depends(get_db),
) -> dict:
    """Turn photographs of the pages of one document into a single document.

    What the phone's **Scan with the camera** button posts: one shot per page,
    in order. The photos are bound into one PDF (`exports.convert.images_to_pdf`)
    and then take exactly the route an uploaded scan takes - both OCR readers,
    verification, the exports folder - so a photographed manual is not a
    second-class citizen.
    """
    from ..exports.convert import images_to_pdf

    settings = get_settings()
    log.info("scan: %d page photo(s)", len(pages))
    shots: list[tuple[str, bytes]] = []
    total = 0
    with tempfile.TemporaryDirectory() as tmpdir:
        for index, up in enumerate(pages, start=1):
            data = await up.read()
            total += len(data)
            if total > settings.max_upload_mb * (1 << 20):
                raise HTTPException(413, f"The photos exceed the {settings.max_upload_mb} MB limit.")
            shot_name = up.filename or f"page-{index}.jpg"
            probe = Path(tmpdir) / f"{index}-{Path(shot_name).name}"
            probe.write_bytes(data)
            if identify_file(probe, shot_name).file_type != "image":
                log.warning("scan rejected: %s is not a photo", shot_name)
                raise HTTPException(415, f"{shot_name}: that is not a photo. Take the pages with the camera.")
            shots.append((shot_name, data))
        if not shots:
            raise HTTPException(400, "No pages were sent.")
        stem = (name or "").strip() or f"Scan {datetime.now().strftime('%Y-%m-%d %H%M')}"
        pdf_path = Path(tmpdir) / "scan.pdf"
        pdf_path.write_bytes(images_to_pdf(shots))
        doc = create_document_from_file(db, pdf_path, f"{stem}.pdf")
    return document_summary(doc)


@router.get("")
def list_documents(db: Session = Depends(get_db)) -> list[dict]:
    docs = db.execute(select(Document).order_by(Document.uploaded_at.desc())).scalars().all()
    return [document_summary(d) for d in docs]


def _get_doc(db: Session, document_id: str) -> Document:
    doc = db.get(Document, document_id)
    if not doc:
        raise HTTPException(404, "Document not found")
    return doc


@router.get("/{document_id}")
def get_document(document_id: str, db: Session = Depends(get_db)) -> dict:
    doc = _get_doc(db, document_id)
    out = document_detail(doc)
    out["pages"] = [page_summary(p) for p in db.execute(select(Page).where(Page.document_id == doc.id).order_by(Page.page_number)).scalars()]
    return out


@router.delete("/{document_id}", status_code=204)
def delete_document(document_id: str, db: Session = Depends(get_db)) -> None:
    doc = _get_doc(db, document_id)
    from ..search.index import remove_document_index

    remove_document_index(db, doc.id)
    db.delete(doc)
    db.commit()
    delete_document_files(doc.id)


@router.post("/{document_id}/reprocess")
def reprocess_document(document_id: str, db: Session = Depends(get_db)) -> dict:
    doc = _get_doc(db, document_id)
    doc.status = "queued"
    doc.progress = "Queued for re-processing"
    db.commit()
    pipeline.submit(doc.id)
    return document_summary(doc)


@router.post("/{document_id}/export")
def export_document_now(document_id: str, db: Session = Depends(get_db)) -> dict:
    """Write (or rewrite) the document's exports folder right away."""
    from ..exports.auto import export_document_by_id

    doc = _get_doc(db, document_id)
    if doc.status != "ready":
        raise HTTPException(409, "The document has not finished processing")
    db.commit()  # release this session's view; the export opens its own
    folder = export_document_by_id(doc.id)
    db.expire_all()
    doc = _get_doc(db, document_id)
    return {"folder": str(folder) if folder else None, "files": (doc.stats or {}).get("export_files", [])}


@router.post("/{document_id}/verify")
def verify_document(document_id: str, db: Session = Depends(get_db)) -> dict:
    """Read the document again with every reader and re-run the verification
    ladder (useful after adding an API key). Values the user confirmed or
    filled in are kept."""
    return reprocess_document(document_id, db)


@router.get("/{document_id}/file")
def get_original(document_id: str, db: Session = Depends(get_db)):
    doc = _get_doc(db, document_id)
    path = Path(doc.storage_path)
    if not path.exists():
        raise HTTPException(404, "Original file missing")
    return FileResponse(path, media_type=doc.mime_type, filename=doc.filename)


@router.get("/{document_id}/pages")
def list_pages(document_id: str, db: Session = Depends(get_db)) -> list[dict]:
    _get_doc(db, document_id)
    return [page_summary(p) for p in db.execute(select(Page).where(Page.document_id == document_id).order_by(Page.page_number)).scalars()]


@router.get("/{document_id}/pages/{page_number}")
def get_page(document_id: str, page_number: int, words: bool = False, db: Session = Depends(get_db)) -> dict:
    _get_doc(db, document_id)
    page = db.execute(select(Page).where(Page.document_id == document_id, Page.page_number == page_number)).scalar_one_or_none()
    if not page:
        raise HTTPException(404, "Page not found")
    blocks = db.execute(select(Block).where(Block.document_id == document_id, Block.page_number == page_number).order_by(Block.order_index)).scalars().all()
    out = page_summary(page)
    out["document_id"] = document_id
    out["text"] = page.text
    out["blocks"] = [block_dict(b, include_words=words) for b in blocks]
    return out


@router.get("/{document_id}/pages/{page_number}/image")
def get_page_image(document_id: str, page_number: int, db: Session = Depends(get_db)):
    _get_doc(db, document_id)
    page = db.execute(select(Page).where(Page.document_id == document_id, Page.page_number == page_number)).scalar_one_or_none()
    if not page or not page.image_path or not Path(page.image_path).exists():
        raise HTTPException(404, "Page image not found")
    return FileResponse(page.image_path, media_type="image/png", headers={"Cache-Control": "private, max-age=86400"})


@router.get("/{document_id}/qc")
def get_qc_flags(document_id: str, db: Session = Depends(get_db)) -> list[dict]:
    _get_doc(db, document_id)
    flags = db.execute(select(QCFlag).where(QCFlag.document_id == document_id)).scalars().all()
    order = {"critical": 0, "warning": 1, "info": 2}
    flags.sort(key=lambda f: (order.get(f.severity, 3), f.page_number or 0))
    return [flag_dict(f) for f in flags]


@router.post("/{document_id}/qc/{flag_id}/resolve")
def resolve_flag(document_id: str, flag_id: str, resolved: bool = True, db: Session = Depends(get_db)) -> dict:
    flag = db.get(QCFlag, flag_id)
    if not flag or flag.document_id != document_id:
        raise HTTPException(404, "Flag not found")
    flag.resolved = resolved
    db.commit()
    return flag_dict(flag)
