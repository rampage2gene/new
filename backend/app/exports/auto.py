"""Automatic outputs: every processed document gets its own folder.

    <data dir>/exports/<name>/
        <name>.ocr.pdf     the scan with a searchable text layer
        <name>.clean.pdf   text-only PDF: values table + full page text with
                           corrections applied and blanks marked [TO FILL IN]
        <name>.xlsx        workbook (Technical Data with Verified/Notes, To fill in, ...)
        <name>.values.csv  every value, blanks left blank, notes say why
        <name>.json        pages, blocks and values with their verification
        <name>.txt         plain text

Written when processing finishes and again (debounced) after each edit, so
the folder always holds the corrected versions. Failures are logged and never
fail the document.
"""
from __future__ import annotations

import csv
import io
import json
import logging
import re
import threading
from html import escape
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..api.serializers import STATUS_LABELS, entity_dict, verification_note
from ..config import get_settings
from ..db import session_scope
from ..models import Block, Document, Entity, Page

log = logging.getLogger(__name__)

_timers: dict[str, threading.Timer] = {}
_timers_lock = threading.Lock()
EDIT_DELAY = 5.0
FILL_MARK = "[TO FILL IN]"
FILES = ("ocr.pdf", "clean.pdf", "xlsx", "values.csv", "json", "txt")


def safe_stem(filename: str) -> str:
    stem = Path(filename).stem.strip() or "document"
    stem = re.sub(r"[^\w\-. ]+", "_", stem).strip(" .")
    return stem[:80] or "document"


def export_folder(doc: Document, root: Path | None = None) -> Path:
    """`<exports>/<stem>`; when another document already owns that name, `<stem>-<id>`."""
    root = root or get_settings().exports_dir
    stem = safe_stem(doc.filename)
    folder = root / stem
    marker = folder / ".document-id"
    if folder.exists() and marker.exists():
        try:
            owner = marker.read_text(encoding="utf-8").strip()
        except OSError:
            owner = ""
        if owner and owner != doc.id:
            folder = root / f"{stem}-{doc.id[:6]}"
    return folder


def export_document(db: Session, doc: Document, folder: Path) -> list[Path]:
    """Write every output for `doc` into `folder`; returns the files written."""
    from .convert import document_to_json, document_to_text
    from .pdf import searchable_pdf
    from .workbook import build_workbook

    folder.mkdir(parents=True, exist_ok=True)
    (folder / ".document-id").write_text(doc.id, encoding="utf-8")
    stem = safe_stem(doc.filename)
    written: list[Path] = []

    def write(suffix: str, producer) -> None:
        out = folder / f"{stem}.{suffix}"
        try:
            data = producer()
            out.write_bytes(data if isinstance(data, bytes) else str(data).encode("utf-8"))
            written.append(out)
        except Exception as exc:  # noqa: BLE001
            log.warning("export: could not write %s: %s", out, exc)

    ents = db.execute(select(Entity).where(Entity.document_id == doc.id).order_by(Entity.page_number, Entity.char_start)).scalars().all()
    name = doc.title or doc.filename
    write("ocr.pdf", lambda: searchable_pdf(db, doc))
    write("clean.pdf", lambda: clean_pdf(db, doc, ents))
    write("xlsx", lambda: build_workbook(db, [doc.id], {"data", "tables", "calculators", "invoices"}))
    write("values.csv", lambda: values_csv(ents, name))
    write("json", lambda: json.dumps(_json_payload(db, doc, ents), indent=2, default=str))
    write("txt", lambda: document_to_text(db, doc))
    return written


def export_document_by_id(document_id: str) -> Path | None:
    with session_scope() as s:
        doc = s.get(Document, document_id)
        if doc is None or doc.status != "ready":
            return None
        folder = export_folder(doc)
        files = export_document(s, doc, folder)
        stats = dict(doc.stats or {})
        stats["export_dir"] = str(folder)
        stats["export_files"] = [f.name for f in files]
        doc.stats = stats
        log.info("export: %s -> %s (%d files)", doc.filename, folder, len(files))
        return folder


def schedule_export(document_id: str, delay: float = EDIT_DELAY) -> None:
    """Rewrite the folder a few seconds after the last edit."""
    if not get_settings().auto_export:
        return
    with _timers_lock:
        old = _timers.pop(document_id, None)
        if old is not None:
            old.cancel()

        def run() -> None:
            with _timers_lock:
                _timers.pop(document_id, None)
            try:
                export_document_by_id(document_id)
            except Exception as exc:  # noqa: BLE001
                log.warning("export after edit failed for %s: %s", document_id, exc)

        t = threading.Timer(delay, run)
        t.daemon = True
        _timers[document_id] = t
        t.start()


def flush_exports() -> None:
    """Run pending debounced exports now (tests, shutdown)."""
    with _timers_lock:
        pending = list(_timers.items())
        _timers.clear()
    for doc_id, t in pending:
        t.cancel()
        export_document_by_id(doc_id)


# --------------------------------------------------------------------------- outputs


def values_csv(ents: list[Entity], name: str) -> str:
    from ..api.exports import ENTITY_COLUMNS, entity_rows

    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=ENTITY_COLUMNS, extrasaction="ignore")
    w.writeheader()
    for r in entity_rows((e, name) for e in ents):
        w.writerow({c: ("" if r.get(c) is None else r.get(c)) for c in ENTITY_COLUMNS})
    return buf.getvalue()


def _json_payload(db: Session, doc: Document, ents: list[Entity]) -> dict:
    from .convert import document_to_json

    out = document_to_json(db, doc)
    name = doc.title or doc.filename
    values = []
    for e in ents:
        d = entity_dict(e, name)
        d["notes"] = verification_note(d)
        if (d.get("verification") or {}).get("status") == "to_fill":
            d["value"], d["value_text"] = None, ""
        values.append(d)
    out["values"] = values
    out["verification"] = (doc.stats or {}).get("verification")
    return out


def corrected_block_text(block: Block, ents: list[Entity]) -> str:
    """The block's text with corrected/filled values substituted at their
    offsets and blanks marked, applied from the end so offsets stay valid."""
    text = block.text or ""
    edits = []
    for e in ents:
        status = ((e.extra or {}).get("verification") or {}).get("status")
        if status == "to_fill":
            edits.append((e.char_start, e.char_end, FILL_MARK))
        elif status in ("corrected", "ai_corrected", "user") and e.value_text:
            original = ((e.extra or {}).get("verification") or {}).get("original")
            if original and text[e.char_start:e.char_end] != e.value_text and e.char_end <= len(text):
                edits.append((e.char_start, e.char_end, e.value_text))
    for start, end, replacement in sorted(edits, key=lambda t: t[0], reverse=True):
        if 0 <= start < end <= len(text):
            text = text[:start] + replacement + text[end:]
    return text


def clean_pdf(db: Session, doc: Document, ents: list[Entity]) -> bytes:
    """A text-only PDF to hand to an AI: the values table, then every page's
    text with corrections applied and blanks marked."""
    from .pdf import html_to_pdf

    name = doc.title or doc.filename
    parts = [f"<h1>{escape(name)}</h1>"]
    meta = " · ".join(escape(str(m)) for m in (doc.manufacturer, doc.model_number, doc.document_type, doc.revision, doc.publication_date) if m)
    if meta:
        parts.append(f"<p class='muted'>{meta}</p>")
    v = (doc.stats or {}).get("verification") or {}
    if v:
        parts.append(
            "<p class='small'>Reading check: "
            f"{v.get('checked', 0)} values read from scanned pages, {v.get('confirmed', 0)} confirmed by two readers, "
            f"{v.get('corrected', 0)} corrected, {v.get('to_fill', 0)} left blank to fill in, {v.get('unverified', 0)} on one reading. "
            f"Blanks are marked {escape(FILL_MARK)}. A value marked confirmed was read the same way by two independent OCR engines or confirmed by the user.</p>"
        )
    parts.append("<h2>Values</h2>")
    parts.append("<table><tr><th>Type</th><th>Value</th><th>Qualifier</th><th>Application / equipment</th><th>Page</th><th>Status</th></tr>")
    for e in ents:
        d = entity_dict(e, name)
        status = (d.get("verification") or {}).get("status") or ("embedded" if d["ocr_confidence"] is None else "single")
        value = FILL_MARK if status == "to_fill" else (d["value_text"] or "")
        label = STATUS_LABELS.get(status, status)
        if d.get("verified"):
            label = "confirmed by you"
        elif status in ("confirmed", "ai_confirmed"):
            label = f"confirmed {int(round((d['confidence'] or 0) * 100))}%"
        app = d["application"] or (f"{d['equipment']} {d['equipment_model'] or ''}".strip() if d["equipment"] else "")
        parts.append(
            f"<tr><td>{escape(d['entity_type'].replace('_', ' '))}</td><td><b>{escape(value)}</b></td><td>{escape(d['qualifier'] or '')}</td>"
            f"<td>{escape(app)}</td><td>{d['page']}</td><td class='small'>{escape(label)}</td></tr>"
        )
    parts.append("</table>")

    pages = db.execute(select(Page).where(Page.document_id == doc.id).order_by(Page.page_number)).scalars().all()
    blocks = db.execute(select(Block).where(Block.document_id == doc.id).order_by(Block.page_number, Block.order_index)).scalars().all()
    by_block: dict[str, list[Entity]] = {}
    for e in ents:
        if e.block_id:
            by_block.setdefault(e.block_id, []).append(e)
    by_page: dict[int, list[Block]] = {}
    for b in blocks:
        by_page.setdefault(b.page_number, []).append(b)
    parts.append("<h2>Text</h2>")
    for p in pages:
        parts.append(f"<h3>Page {p.page_number}{' · ' + escape(p.page_label) if p.page_label else ''}"
                     f"{' (scanned, OCR)' if p.text_source == 'ocr' else ''}</h3>")
        for b in by_page.get(p.page_number, []):
            text = corrected_block_text(b, by_block.get(b.id, []))
            if not text.strip():
                continue
            tag = "h4" if b.block_type == "heading" else "p"
            parts.append(f"<{tag}>{escape(text).replace(chr(10), '<br/>')}</{tag}>")
    return html_to_pdf("<body>" + "\n".join(parts) + "</body>", footer=f"{name} · clean text with verified values")
