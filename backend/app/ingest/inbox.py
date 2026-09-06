"""The inbox folder: drop a file in, get an OCR'd PDF out.

`<data dir>/inbox/` is watched while the app runs. Any PDF or image copied
there is ingested exactly as an upload would be; when processing finishes the
original moves to `inbox/done/` next to `<name>.ocr.pdf` (the same pages with
a text layer), or to `inbox/failed/` with a `.error.txt` saying why.

This exists because the desktop app's browser upload has one failure mode the
server cannot see or explain - the web view being unable to read the file. A
folder on disk has no such problem, and it needs no clicking at all.
"""
from __future__ import annotations

import logging
import shutil
import threading
import time
from pathlib import Path

from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import session_scope
from ..models import Document

log = logging.getLogger(__name__)

SUFFIXES = {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp", ".gif"}

# document id -> the inbox file it came from (only for files this process ingested)
_pending: dict[str, Path] = {}
# path -> size at the previous scan; a file is taken once its size stops changing
_sizes: dict[Path, int] = {}
_lock = threading.Lock()
_thread: threading.Thread | None = None


def inbox_dir() -> Path:
    return get_settings().data_dir / "inbox"


def ensure_inbox() -> Path:
    d = inbox_dir()
    for sub in (d, d / "done", d / "failed"):
        sub.mkdir(parents=True, exist_ok=True)
    return d


def _unique(dest: Path) -> Path:
    """Never overwrite an earlier result: manual.pdf, manual (2).pdf, ..."""
    if not dest.exists():
        return dest
    for n in range(2, 1000):
        cand = dest.with_name(f"{dest.stem} ({n}){dest.suffix}")
        if not cand.exists():
            return cand
    return dest


def _take_new_files(db: Session) -> None:
    from ..api.documents import create_document_from_file
    from fastapi import HTTPException

    d = inbox_dir()
    seen: set[Path] = set()
    for path in sorted(d.iterdir()):
        if not path.is_file() or path.suffix.lower() not in SUFFIXES or path.name.startswith((".", "~")):
            continue
        seen.add(path)
        size = path.stat().st_size
        previous = _sizes.get(path)
        _sizes[path] = size
        if previous is None or previous != size or size == 0:
            continue  # still being copied in; look again next scan
        if path in _pending.values():
            continue
        try:
            doc = create_document_from_file(db, path, path.name, size)
        except HTTPException as exc:
            _fail(path, str(exc.detail))
            _sizes.pop(path, None)
            continue
        except Exception as exc:  # noqa: BLE001 - keep the watcher alive
            log.exception("inbox: could not ingest %s", path)
            _fail(path, f"{type(exc).__name__}: {exc}")
            _sizes.pop(path, None)
            continue
        _pending[doc.id] = path
        log.info("inbox: took %s as document %s", path.name, doc.id)
    for stale in [p for p in _sizes if p not in seen]:
        _sizes.pop(stale, None)


def _fail(path: Path, reason: str) -> None:
    failed = inbox_dir() / "failed"
    failed.mkdir(parents=True, exist_ok=True)
    dest = _unique(failed / path.name)
    shutil.move(str(path), dest)
    dest.with_suffix(dest.suffix + ".error.txt").write_text(reason + "\n", encoding="utf-8")
    log.warning("inbox: %s failed: %s", path.name, reason)


def _finish_processed(db: Session) -> None:
    from ..exports.pdf import searchable_pdf

    for doc_id, path in list(_pending.items()):
        doc = db.get(Document, doc_id)
        if doc is None:
            _pending.pop(doc_id, None)
            continue
        db.refresh(doc)  # processing ran in another session; do not trust a cached status
        if doc.status == "ready":
            done = inbox_dir() / "done"
            done.mkdir(parents=True, exist_ok=True)
            out = _unique(done / f"{path.stem}.ocr.pdf")
            try:
                out.write_bytes(searchable_pdf(db, doc))
            except Exception as exc:  # noqa: BLE001
                log.exception("inbox: could not write %s", out)
                _fail(path, f"processed, but the OCR'd PDF could not be written: {exc}")
                _pending.pop(doc_id, None)
                continue
            if path.exists():
                shutil.move(str(path), _unique(done / path.name))
            _sizes.pop(path, None)
            _pending.pop(doc_id, None)
            log.info("inbox: %s done -> %s (%d pages, %d OCR'd)", path.name, out.name, doc.page_count or 0, doc.ocr_pages or 0)
        elif doc.status == "failed":
            if path.exists():
                _fail(path, doc.error or "processing failed")
            _sizes.pop(path, None)
            _pending.pop(doc_id, None)


def scan_once() -> None:
    """One pass: take finished copies, and finish documents that have processed."""
    with _lock:
        ensure_inbox()
        with session_scope() as db:
            _take_new_files(db)
            _finish_processed(db)


def _loop(interval: float) -> None:
    while True:
        try:
            scan_once()
        except Exception:  # noqa: BLE001 - never let the watcher die
            log.exception("inbox: scan failed")
        time.sleep(interval)


def start_watcher(interval: float = 2.0) -> None:
    global _thread
    if _thread is not None and _thread.is_alive():
        return
    ensure_inbox()
    _thread = threading.Thread(target=_loop, args=(interval,), name="inbox", daemon=True)
    _thread.start()
    log.info("inbox: watching %s", inbox_dir())
