"""Stateless document conversions (no ingestion, nothing stored).

PDF -> text / Markdown / JSON / PNG pages, images -> PDF, merge and split.
Text and structure come from the same reader the pipeline uses
(``ingest.pdf``), including OCR for pages without an embedded text layer, and
the same block classifier (``structure.layout``), so a Markdown conversion has
the same headings, tables and warnings the app shows.
"""
from __future__ import annotations

import io
import json
import re
import zipfile
from pathlib import Path
from typing import Iterable

import pymupdf
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..api.serializers import block_dict
from ..config import get_settings
from ..ingest.pdf import _attach_tables, _embedded_blocks, _ocr_page, _text_quality
from ..ingest.types import RawPage
from ..models import Block, Document, Page
from ..structure.layout import analyse_layout

TEXT_FORMATS = {"txt", "md", "json"}


# --------------------------------------------------------------------------- reading without storing

def read_pdf_bytes(data: bytes, ocr: bool = True) -> list[RawPage]:
    """Like ingest.pdf.read_pdf but from bytes, without rendering page images to disk."""
    settings = get_settings()
    doc = pymupdf.open("pdf", data)
    pages: list[RawPage] = []
    try:
        for index, page in enumerate(doc):
            raw = RawPage(page_number=index + 1, width=float(page.rect.width), height=float(page.rect.height))
            raw.page_label = page.get_label() or None
            blocks = _embedded_blocks(page)
            text = "\n".join(b.text for b in blocks)
            usable = len(text.strip()) >= settings.min_embedded_chars_per_page and _text_quality(text) > 0.9
            if usable:
                raw.blocks = blocks
                raw.text_source = "embedded"
                _attach_tables(page, raw)
            elif ocr:
                ocr_blocks, conf = _ocr_page(page)
                raw.blocks = ocr_blocks
                raw.text_source = "ocr" if ocr_blocks else "none"
                raw.ocr_confidence = conf
            pages.append(raw)
    finally:
        doc.close()
    analyse_layout(pages)
    return pages


# --------------------------------------------------------------------------- renderers

def _rows_to_markdown(rows: list[list]) -> str:
    if not rows:
        return ""
    width = max(len(r) for r in rows)
    norm = [[str(c).replace("|", "\\|").replace("\n", " ") for c in r] + [""] * (width - len(r)) for r in rows]
    out = ["| " + " | ".join(norm[0]) + " |", "|" + "---|" * width]
    out += ["| " + " | ".join(r) + " |" for r in norm[1:]]
    return "\n".join(out)


def blocks_to_markdown(blocks: Iterable[dict], page_number: int | None = None, page_break: bool = True) -> str:
    """Blocks as produced by serializers.block_dict (or RawBlock-like dicts)."""
    out: list[str] = []
    if page_number is not None and page_break:
        out.append(f"\n<!-- page {page_number} -->\n")
    for b in blocks:
        t = b.get("block_type")
        text = (b.get("text") or "").strip()
        if not text and t != "table":
            continue
        if t == "heading":
            level = max(1, min(4, int(b.get("section_level") or 1)))
            out.append("#" * level + " " + text.replace("\n", " "))
        elif t == "table":
            rows = (b.get("table") or {}).get("rows") or [line.split(" | ") for line in text.splitlines()]
            out.append(_rows_to_markdown(rows))
        elif t == "warning":
            out.append("> **WARNING** " + text.replace("\n", " "))
        elif t == "note":
            out.append("> " + text.replace("\n", " "))
        elif t == "caption":
            out.append("*" + text.replace("\n", " ") + "*")
        elif t == "list":
            out.append("\n".join("- " + re.sub(r"^\s*[-•·*]\s*", "", ln) for ln in text.splitlines() if ln.strip()))
        elif t in ("header", "footer", "page_number"):
            continue
        else:
            out.append(text.replace("\n", " "))
        out.append("")
    return "\n".join(out).strip() + "\n"


def _raw_block_dict(b) -> dict:
    return {
        "block_type": b.block_type, "text": b.text, "bbox": list(b.bbox), "section": b.section, "section_level": b.section_level,
        "source": b.source, "confidence": b.confidence, "table": b.table, "words": b.words,
    }


def pdf_to_text(data: bytes, ocr: bool = True) -> str:
    pages = read_pdf_bytes(data, ocr=ocr)
    return "\n\n".join(f"===== Page {p.page_number} =====\n\n{p.text}" for p in pages) + "\n"


def pdf_to_markdown(data: bytes, ocr: bool = True) -> str:
    pages = read_pdf_bytes(data, ocr=ocr)
    return "".join(blocks_to_markdown([_raw_block_dict(b) for b in p.blocks], p.page_number) for p in pages)


def pdf_to_json(data: bytes, ocr: bool = True, words: bool = False) -> dict:
    pages = read_pdf_bytes(data, ocr=ocr)
    out_pages = []
    for p in pages:
        blocks = []
        for b in p.blocks:
            d = _raw_block_dict(b)
            if not words:
                d.pop("words", None)
            blocks.append(d)
        out_pages.append({
            "page_number": p.page_number, "width": p.width, "height": p.height, "text_source": p.text_source,
            "ocr_confidence": p.ocr_confidence, "is_diagram": p.is_diagram, "blocks": blocks,
        })
    return {"pages": out_pages, "structure": analyse_layout(pages)}


def pdf_to_png_zip(data: bytes, dpi: int | None = None) -> bytes:
    dpi = dpi or get_settings().render_dpi
    doc = pymupdf.open("pdf", data)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zoom = dpi / 72.0
        for i, page in enumerate(doc, start=1):
            pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
            zf.writestr(f"page-{i:04d}.png", pix.tobytes("png"))
    doc.close()
    return buf.getvalue()


def images_to_pdf(files: list[tuple[str, bytes]]) -> bytes:
    """One page per image, page size = image size in points at 72 dpi (or the PDF's own pages)."""
    out = pymupdf.open()
    for name, data in files:
        ext = Path(name).suffix.lower().lstrip(".") or "png"
        if ext == "pdf":
            src = pymupdf.open("pdf", data)
            out.insert_pdf(src)
            src.close()
            continue
        img = pymupdf.open(stream=data, filetype=ext)
        pdf = pymupdf.open("pdf", img.convert_to_pdf())
        out.insert_pdf(pdf)
        pdf.close()
        img.close()
    result = out.tobytes(garbage=3, deflate=True)
    out.close()
    return result


def merge_pdfs(files: list[bytes]) -> bytes:
    out = pymupdf.open()
    for data in files:
        src = pymupdf.open("pdf", data)
        out.insert_pdf(src)
        src.close()
    result = out.tobytes(garbage=3, deflate=True)
    out.close()
    return result


def parse_ranges(spec: str, page_count: int) -> list[tuple[int, int]]:
    """'1-3,5,7-' -> [(1,3),(5,5),(7,n)] (1-based, inclusive)."""
    ranges: list[tuple[int, int]] = []
    for part in re.split(r"[,\s]+", spec.strip()):
        if not part:
            continue
        m = re.match(r"^(\d+)?\s*-\s*(\d+)?$", part)
        if m and (m.group(1) or m.group(2)):
            a = int(m.group(1) or 1)
            b = int(m.group(2) or page_count)
        elif part.isdigit():
            a = b = int(part)
        else:
            raise ValueError(f"Bad page range '{part}'")
        a, b = max(1, a), min(page_count, b)
        if a > b:
            raise ValueError(f"Empty page range '{part}'")
        ranges.append((a, b))
    if not ranges:
        raise ValueError("No page ranges given")
    return ranges


def split_pdf(data: bytes, ranges: str | None = None, base_name: str = "document") -> bytes:
    """Zip of one PDF per range (default: one PDF per page)."""
    src = pymupdf.open("pdf", data)
    parts = parse_ranges(ranges, src.page_count) if ranges else [(i, i) for i in range(1, src.page_count + 1)]
    buf = io.BytesIO()
    stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", Path(base_name).stem) or "document"
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for a, b in parts:
            out = pymupdf.open()
            out.insert_pdf(src, from_page=a - 1, to_page=b - 1)
            label = f"{a}" if a == b else f"{a}-{b}"
            zf.writestr(f"{stem}_p{label}.pdf", out.tobytes(garbage=3, deflate=True))
            out.close()
    src.close()
    return buf.getvalue()


# --------------------------------------------------------------------------- ingested documents

def document_to_text(db: Session, doc: Document) -> str:
    pages = db.execute(select(Page).where(Page.document_id == doc.id).order_by(Page.page_number)).scalars().all()
    return "\n\n".join(f"===== Page {p.page_number} =====\n\n{p.text or ''}" for p in pages) + "\n"


def document_to_markdown(db: Session, doc: Document) -> str:
    blocks = db.execute(select(Block).where(Block.document_id == doc.id).order_by(Block.page_number, Block.order_index)).scalars().all()
    by_page: dict[int, list[dict]] = {}
    for b in blocks:
        by_page.setdefault(b.page_number, []).append(block_dict(b))
    head = f"# {doc.title or doc.filename}\n\n" + " · ".join(str(m) for m in (doc.manufacturer, doc.model_number, doc.document_type, doc.revision) if m) + "\n"
    return head + "".join(blocks_to_markdown(by_page[p], p) for p in sorted(by_page))


def document_to_json(db: Session, doc: Document, words: bool = False) -> dict:
    from ..api.serializers import document_detail, page_summary

    pages = db.execute(select(Page).where(Page.document_id == doc.id).order_by(Page.page_number)).scalars().all()
    blocks = db.execute(select(Block).where(Block.document_id == doc.id).order_by(Block.page_number, Block.order_index)).scalars().all()
    by_page: dict[int, list[dict]] = {}
    for b in blocks:
        by_page.setdefault(b.page_number, []).append(block_dict(b, include_words=words))
    out = document_detail(doc)
    out["pages"] = [{**page_summary(p), "text": p.text, "blocks": by_page.get(p.page_number, [])} for p in pages]
    return out


def to_json_bytes(obj) -> bytes:
    return json.dumps(obj, indent=2, default=str).encode("utf-8")
