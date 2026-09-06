"""PDF outputs: searchable PDFs (invisible OCR text layer) and report PDFs.

Both use PyMuPDF only. The searchable PDF keeps the original page images and
adds each OCR'd word as invisible text at its bounding box so the file becomes
selectable and searchable in any viewer. Reports are laid out with
``pymupdf.Story`` from a small HTML template.
"""
from __future__ import annotations

import html
import io
import re
from datetime import datetime, timezone
from typing import Any

import pymupdf
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..api.entities import GROUPS
from ..api.serializers import entity_dict, flag_dict
from ..models import Block, Document, Entity, Page, QCFlag

# --------------------------------------------------------------------------- searchable PDF

_FONT = "helv"


def _insert_invisible_words(page: pymupdf.Page, words: list[dict], scale_x: float = 1.0, scale_y: float = 1.0) -> int:
    """Place each word as invisible (render_mode=3) text fitted to its bbox."""
    n = 0
    for w in words:
        text = (w.get("t") or "").strip()
        bbox = w.get("bbox")
        if not text or not bbox or len(bbox) != 4:
            continue
        x0, y0, x1, y1 = (bbox[0] * scale_x, bbox[1] * scale_y, bbox[2] * scale_x, bbox[3] * scale_y)
        width, height = max(1.0, x1 - x0), max(1.0, y1 - y0)
        unit = pymupdf.get_text_length(text, fontname=_FONT, fontsize=1) or 1.0
        fontsize = min(width / unit, height * 1.1)
        if fontsize < 1:
            fontsize = 1.0
        # Baseline sits slightly above the bottom of the box (descender allowance).
        baseline = y1 - 0.22 * fontsize
        try:
            page.insert_text((x0, baseline), text, fontname=_FONT, fontsize=fontsize, render_mode=3)
            n += 1
        except Exception:  # pragma: no cover - odd glyphs; skip the word rather than fail the file
            continue
    return n


def searchable_pdf(db: Session, doc: Document) -> bytes:
    """The original document with an invisible text layer on every OCR'd page."""
    pages = db.execute(select(Page).where(Page.document_id == doc.id).order_by(Page.page_number)).scalars().all()
    blocks = db.execute(select(Block).where(Block.document_id == doc.id, Block.source == "ocr").order_by(Block.page_number, Block.order_index)).scalars().all()
    words_by_page: dict[int, list[dict]] = {}
    for b in blocks:
        if b.words:
            words_by_page.setdefault(b.page_number, []).extend(b.words)
        elif b.text:  # OCR block without word boxes: place the block text in its bbox
            words_by_page.setdefault(b.page_number, []).append({"t": b.text.replace("\n", " "), "bbox": [b.x0, b.y0, b.x1, b.y1]})

    if doc.file_type == "pdf":
        out = pymupdf.open(doc.storage_path)
    else:
        # Image upload: build a one-page PDF whose page size equals the image size in pixels,
        # so the stored word boxes (image pixel units) map 1:1 onto points.
        img = pymupdf.open(doc.storage_path)
        out = pymupdf.open("pdf", img.convert_to_pdf())
        img.close()
        pg = out[0]
        stored = pages[0] if pages else None
        if stored and stored.width and stored.height:
            pg.set_mediabox(pymupdf.Rect(0, 0, stored.width, stored.height))
            pg.clean_contents()
            # convert_to_pdf scales the image to its page; redraw at the stored size
            pg.insert_image(pg.rect, filename=doc.storage_path, overlay=False)

    for p in pages:
        if p.text_source != "ocr" or p.page_number not in words_by_page:
            continue
        if p.page_number - 1 >= out.page_count:
            continue
        page = out[p.page_number - 1]
        sx = page.rect.width / p.width if p.width else 1.0
        sy = page.rect.height / p.height if p.height else 1.0
        _insert_invisible_words(page, words_by_page[p.page_number], sx, sy)
    out.set_metadata({**(out.metadata or {}), "producer": "Marine Electrical Document Intelligence", "subject": "Searchable copy with OCR text layer"})
    data = out.tobytes(garbage=3, deflate=True)
    out.close()
    return data


# --------------------------------------------------------------------------- report PDF

CSS = """
body { font-family: sans-serif; font-size: 9.5pt; color: #111827; }
h1 { font-size: 18pt; margin: 0 0 4pt 0; color: #0e2c54; }
h2 { font-size: 13pt; margin: 14pt 0 4pt 0; color: #0e2c54; border-bottom: 1px solid #cbd5e1; }
h3 { font-size: 10.5pt; margin: 10pt 0 3pt 0; }
p { margin: 3pt 0; }
.muted { color: #6b7280; }
.small { font-size: 8pt; }
table { border-collapse: collapse; width: 100%; margin: 4pt 0 8pt 0; }
th { background-color: #e5e7eb; text-align: left; font-size: 8.5pt; padding: 2pt 3pt; }
td { font-size: 8.5pt; padding: 2pt 3pt; border-bottom: 0.5px solid #e5e7eb; vertical-align: top; }
.badge { font-size: 7.5pt; font-weight: bold; padding: 1pt 3pt; }
.manufacturer_required { color: #065f46; }
.documented_value { color: #1d4ed8; }
.calculated_estimate { color: #92400e; }
.recommended_pending_verification { color: #7c2d12; }
.warn { color: #92400e; }
.crit { color: #991b1b; font-weight: bold; }
.box { border: 1px solid #cbd5e1; padding: 4pt; margin: 4pt 0; }
"""


def _e(v: Any) -> str:
    return html.escape("" if v is None else str(v))


def _fmt_num(v: Any) -> str:
    if isinstance(v, float):
        return f"{v:,.3f}".rstrip("0").rstrip(".")
    return _e(v)


def _md_to_html(md: str) -> str:
    """Small Markdown subset used by answers: headings, bullets, pipe tables, bold, paragraphs."""
    out: list[str] = []
    lines = md.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        if line.startswith("|") and i + 1 < len(lines) and re.match(r"^\|?\s*:?-{2,}", lines[i + 1]):
            header = [c.strip() for c in line.strip("|").split("|")]
            rows = []
            i += 2
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            out.append("<table><tr>" + "".join(f"<th>{_inline(h)}</th>" for h in header) + "</tr>")
            for r in rows:
                out.append("<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in r) + "</tr>")
            out.append("</table>")
            continue
        m = re.match(r"^(#{1,3})\s+(.*)", line)
        if m:
            level = min(3, len(m.group(1)) + 1)
            out.append(f"<h{level}>{_inline(m.group(2))}</h{level}>")
        elif re.match(r"^\s*[-*]\s+", line):
            items = []
            while i < len(lines) and re.match(r"^\s*[-*]\s+", lines[i]):
                items.append(re.sub(r"^\s*[-*]\s+", "", lines[i]))
                i += 1
            out.append("<ul>" + "".join(f"<li>{_inline(it)}</li>" for it in items) + "</ul>")
            continue
        elif line.strip():
            out.append(f"<p>{_inline(line)}</p>")
        i += 1
    return "\n".join(out)


def _inline(text: str) -> str:
    t = _e(text)
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"`(.+?)`", r"<code>\1</code>", t)
    return t


def _doc_header(doc: Document) -> str:
    meta = [doc.manufacturer, doc.product, doc.model_number, doc.document_type, f"rev {doc.revision}" if doc.revision else None, doc.publication_date]
    return (
        f"<h1>{_e(doc.title or doc.filename)}</h1>"
        f"<p class='muted'>{_e(' · '.join(str(m) for m in meta if m))}</p>"
        f"<p class='muted small'>{_e(doc.filename)} · {doc.page_count} pages · {doc.ocr_pages} OCR'd · processed {doc.processed_at.strftime('%Y-%m-%d') if doc.processed_at else ''}</p>"
    )


def _spec_extraction_html(db: Session, doc: Document) -> str:
    ents = db.execute(select(Entity).where(Entity.document_id == doc.id).order_by(Entity.page_number, Entity.char_start)).scalars().all()
    name = doc.title or doc.filename
    parts = ["<h2>Electrical specification extraction</h2>"]
    any_rows = False
    for key, g in GROUPS.items():
        rows = [entity_dict(e, name) for e in ents if e.entity_type in g["types"]]
        if not rows:
            continue
        any_rows = True
        parts.append(f"<h3>{_e(g['label'])} ({len(rows)})</h3><table><tr><th>Value</th><th>Qualifier</th><th>Application / equipment</th><th>Page</th><th>Section</th><th>Conf.</th><th>Context</th></tr>")
        for r in rows:
            ctx = " / ".join(str(x) for x in (r["application"], r["equipment"]) if x)
            flag = " <span class='crit'>!</span>" if any(f.get("severity") == "critical" for f in r["flags"]) else ""
            snippet = (r["snippet"] or "")[:160]
            parts.append(
                f"<tr><td><b>{_e(r['value_text'])}</b>{flag}</td><td>{_e(r['qualifier'] or '')}</td><td>{_e(ctx)}</td>"
                f"<td>{r['page']}</td><td>{_e(r['section'] or '')}</td><td>{int((r['confidence'] or 0) * 100)}%</td><td class='small'>{_e(snippet)}</td></tr>"
            )
        parts.append("</table>")
    warnings = (doc.structure or {}).get("warnings", [])
    if warnings:
        any_rows = True
        parts.append(f"<h3>Warnings in the document ({len(warnings)})</h3>")
        for w in warnings:
            parts.append(f"<p class='warn small'>p. {w['page']}: {_e(w['text'][:300])}</p>")
    if not any_rows:
        parts.append("<p class='muted'>No technical values were extracted from this document.</p>")
    return "\n".join(parts)


def _qc_html(db: Session, doc: Document) -> str:
    flags = db.execute(select(QCFlag).where(QCFlag.document_id == doc.id)).scalars().all()
    if not flags:
        return "<h2>Verification</h2><p class='muted'>No quality-control flags.</p>"
    order = {"critical": 0, "warning": 1, "info": 2}
    flags.sort(key=lambda f: (order.get(f.severity, 3), f.page_number or 0))
    parts = ["<h2>Verification</h2><table><tr><th>Severity</th><th>Page</th><th>Type</th><th>Message</th><th>Status</th></tr>"]
    for f in flags:
        d = flag_dict(f)
        cls = "crit" if d["severity"] == "critical" else ("warn" if d["severity"] == "warning" else "muted")
        parts.append(f"<tr><td class='{cls}'>{_e(d['severity'])}</td><td>{d['page'] or ''}</td><td>{_e(d['flag_type'])}</td><td>{_e(d['message'])}</td><td>{'resolved' if d['resolved'] else 'open'}</td></tr>")
    parts.append("</table>")
    return "\n".join(parts)


def _calculation_html(calc: dict) -> str:
    parts = [f"<h3>{_e(calc.get('calculator_name'))}</h3><p class='muted'><code>{_e(calc.get('formula'))}</code></p>"]
    parts.append("<table><tr><th>Result</th><th>Value</th><th>Classification</th><th>Note</th></tr>")
    for r in calc.get("results", []):
        cls = r.get("classification", "calculated_estimate")
        parts.append(
            f"<tr><td>{_e(r.get('label'))}</td><td><b>{_fmt_num(r.get('value'))} {_e(r.get('unit') or '')}</b></td>"
            f"<td><span class='badge {cls}'>{_e(cls.replace('_', ' ').upper())}</span></td><td class='small'>{_e(r.get('note') or '')}</td></tr>"
        )
    parts.append("</table>")
    inputs = calc.get("inputs") or {}
    if inputs:
        parts.append("<table><tr><th>Input</th><th>Value</th><th>Origin</th><th>Source</th></tr>")
        for k, v in inputs.items():
            if v is None or v.get("value") in (None, ""):
                continue
            src = v.get("source") or {}
            src_txt = f"{src.get('document_name') or ''}, p. {src.get('page')}" if src.get("page") else ""
            parts.append(f"<tr><td>{_e(k.replace('_', ' '))}</td><td>{_fmt_num(v.get('value'))} {_e(v.get('unit') or '')}</td><td>{_e(v.get('origin') or '')}</td><td class='small'>{_e(src_txt)}</td></tr>")
        parts.append("</table>")
    for w in calc.get("warnings", []):
        parts.append(f"<p class='warn'>Warning: {_e(w)}</p>")
    steps = calc.get("steps", [])
    if steps:
        parts.append("<p><b>Calculation</b></p><ol>" + "".join(f"<li>{_e(s)}</li>" for s in steps) + "</ol>")
    if calc.get("assumptions"):
        parts.append("<p class='small muted'>Assumptions: " + "; ".join(_e(a) for a in calc["assumptions"]) + "</p>")
    return "\n".join(parts)


def _answer_html(answer: dict) -> str:
    parts = ["<h2>Question and answer</h2>"]
    if answer.get("question"):
        parts.append(f"<p><b>Q:</b> {_e(answer['question'])}</p>")
    status = answer.get("status")
    parts.append(f"<p class='muted small'>status: {_e(status)} · {_e(answer.get('answer_kind') or '')}</p>")
    parts.append("<div class='box'>" + _md_to_html(answer.get("answer") or "") + "</div>")
    cits = answer.get("citations") or []
    if cits:
        parts.append("<p><b>Sources</b></p><table><tr><th>#</th><th>Document</th><th>Page</th><th>Section</th><th>Quote</th></tr>")
        for i, c in enumerate(cits, start=1):
            parts.append(f"<tr><td>{i}</td><td>{_e(c.get('document_name') or c.get('document_id'))}</td><td>{c.get('page')}</td><td>{_e(c.get('section') or '')}</td><td class='small'>{_e((c.get('quote') or '')[:240])}</td></tr>")
        parts.append("</table>")
    for w in answer.get("verification_warnings") or []:
        parts.append(f"<p class='warn small'>{_e(w)}</p>")
    return "\n".join(parts)


DISCLAIMER = (
    "Values in this report were extracted automatically from the listed documents and carry page references so they can be "
    "verified. Calculations are engineering estimates unless marked as manufacturer-required; verify against the manufacturer's "
    "documentation and applicable standards (e.g. ABYC E-11, ISO 13297) before installation."
)


def build_report_html(
    db: Session,
    docs: list[Document],
    sections: set[str],
    calculations: list[dict] | None = None,
    answer: dict | None = None,
    title: str | None = None,
) -> str:
    parts: list[str] = []
    if title:
        parts.append(f"<h1>{_e(title)}</h1>")
    if len(docs) > 1 or title:
        parts.append("<p class='muted'>Documents: " + "; ".join(_e(d.title or d.filename) for d in docs) + "</p>")
    for doc in docs:
        if not title and len(docs) == 1:
            parts.append(_doc_header(doc))
        elif len(docs) > 1:
            parts.append(f"<h2>{_e(doc.title or doc.filename)}</h2>")
        if "spec_extraction" in sections:
            parts.append(_spec_extraction_html(db, doc))
        if "qc" in sections:
            parts.append(_qc_html(db, doc))
    if calculations:
        parts.append("<h2>Calculations</h2>")
        for c in calculations:
            parts.append(_calculation_html(c))
    if answer:
        parts.append(_answer_html(answer))
    parts.append(f"<p class='small muted'>{_e(DISCLAIMER)}</p>")
    return "<body>" + "\n".join(parts) + "</body>"


def html_to_pdf(body_html: str, footer: str | None = None) -> bytes:
    """Lay out HTML with pymupdf.Story onto A4 pages, then stamp a footer on each page."""
    story = pymupdf.Story(html=body_html, user_css=CSS)
    mediabox = pymupdf.paper_rect("a4")
    where = mediabox + (40, 40, -40, -56)
    buf = io.BytesIO()
    writer = pymupdf.DocumentWriter(buf)
    more = 1
    guard = 0
    while more and guard < 500:
        dev = writer.begin_page(mediabox)
        more, _ = story.place(where)
        story.draw(dev)
        writer.end_page()
        guard += 1
    writer.close()
    doc = pymupdf.open("pdf", buf.getvalue())
    stamp = footer or f"Marine Electrical Document Intelligence · generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
    for i, page in enumerate(doc, start=1):
        page.insert_text((40, mediabox.height - 28), f"{stamp} · page {i} of {doc.page_count}", fontname=_FONT, fontsize=7.5, color=(0.42, 0.45, 0.5))
    doc.set_metadata({"producer": "Marine Electrical Document Intelligence", "title": "Report"})
    data = doc.tobytes(garbage=3, deflate=True)
    doc.close()
    return data


def build_report_pdf(db: Session, docs: list[Document], sections: set[str], calculations: list[dict] | None = None, answer: dict | None = None, title: str | None = None) -> bytes:
    return html_to_pdf(build_report_html(db, docs, sections, calculations, answer, title))
