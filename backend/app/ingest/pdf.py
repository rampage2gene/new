"""PDF reader built on PyMuPDF.

For each page we:
* pull embedded text as blocks/lines/spans with font metrics and bounding boxes,
* decide whether the embedded text is trustworthy (scanned PDFs have none, and
  some PDFs carry garbage encodings), and if not, render the page and OCR it,
* render a display image for the viewer,
* collect drawing/image statistics used to score diagram pages.
"""
from __future__ import annotations

import re
import statistics
from pathlib import Path

import pymupdf
from PIL import Image

from ..config import get_settings
from ..ocr.engine import run_ocr, run_ocr_readings
from ..ocr.postprocess import normalise_technical_text
from ..storage.files import page_image_path
from .types import RawBlock, RawPage

_GARBAGE_RE = re.compile(r"[^\x09\x0a\x0d\x20-\x7e -ɏ–—‘’“”•°²Ω±·…]")


def _text_quality(text: str) -> float:
    """Fraction of characters that look like real text (low for broken fonts)."""
    if not text:
        return 0.0
    bad = len(_GARBAGE_RE.findall(text))
    return 1.0 - bad / max(1, len(text))


def _pix_to_pil(pix: pymupdf.Pixmap) -> Image.Image:
    mode = "RGB" if pix.n < 4 else "RGBA"
    img = Image.frombytes(mode, (pix.width, pix.height), pix.samples)
    return img.convert("RGB")


def read_pdf(path: Path, document_id: str, progress=None) -> list[RawPage]:
    settings = get_settings()
    doc = pymupdf.open(path)
    pages: list[RawPage] = []
    try:
        for index, page in enumerate(doc):
            page_number = index + 1
            if progress:
                progress(f"Reading page {page_number}/{doc.page_count}")
            rect = page.rect
            raw = RawPage(page_number=page_number, width=float(rect.width), height=float(rect.height))
            raw.page_label = page.get_label() or None

            # Display render.
            zoom = settings.render_dpi / 72.0
            pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
            out = page_image_path(document_id, page_number)
            pix.save(out)
            raw.image_path = str(out)

            # Layout statistics.
            try:
                raw.drawings = len(page.get_drawings())
            except Exception:  # pragma: no cover - defensive
                raw.drawings = 0
            try:
                images = page.get_image_info()
                raw.images = len(images)
                area = 0.0
                for info in images:
                    x0, y0, x1, y1 = info.get("bbox", (0, 0, 0, 0))
                    area += max(0.0, x1 - x0) * max(0.0, y1 - y0)
                raw.image_area_ratio = min(1.0, area / max(1.0, rect.width * rect.height))
            except Exception:  # pragma: no cover
                raw.images = 0

            blocks = _embedded_blocks(page)
            text = "\n".join(b.text for b in blocks)
            usable = len(text.strip()) >= settings.min_embedded_chars_per_page and _text_quality(text) > 0.9
            if usable:
                raw.blocks = blocks
                raw.text_source = "embedded"
                # Tables from vector text.
                _attach_tables(page, raw)
            else:
                _ocr_page(page, raw)
            pages.append(raw)
    finally:
        doc.close()
    return pages


def _embedded_blocks(page: pymupdf.Page) -> list[RawBlock]:
    data = page.get_text("dict")
    words_by_block: dict[int, list[dict]] = {}
    try:
        for x0, y0, x1, y1, word, block_no, line_no, word_no in page.get_text("words"):
            words_by_block.setdefault(int(block_no), []).append(
                {"t": word, "c": 1.0, "bbox": [float(x0), float(y0), float(x1), float(y1)], "line": int(line_no)}
            )
    except Exception:  # pragma: no cover - defensive
        words_by_block = {}
    blocks: list[RawBlock] = []
    for b in data.get("blocks", []):
        if b.get("type") != 0:
            continue
        lines: list[str] = []
        line_sizes: list[float] = []
        sizes: list[float] = []
        bold_chars = 0
        total_chars = 0
        for line in b.get("lines", []):
            parts = []
            lsizes: list[float] = []
            for span in line.get("spans", []):
                t = span.get("text", "")
                if not t:
                    continue
                parts.append(t)
                n = len(t.strip())
                if n:
                    sizes.extend([float(span.get("size", 0))] * n)
                    lsizes.extend([float(span.get("size", 0))] * n)
                    total_chars += n
                    if span.get("flags", 0) & 16:
                        bold_chars += n
            line_text = "".join(parts).strip()
            if line_text:
                lines.append(line_text)
                line_sizes.append(statistics.median(lsizes) if lsizes else 0.0)
        text = "\n".join(lines).strip()
        if not text:
            continue
        x0, y0, x1, y1 = b["bbox"]
        blocks.append(
            RawBlock(
                text=text,
                bbox=(float(x0), float(y0), float(x1), float(y1)),
                source="embedded",
                confidence=1.0,
                font_size=statistics.median(sizes) if sizes else None,
                bold=total_chars > 0 and bold_chars / total_chars > 0.6,
                lines=lines,
                line_sizes=line_sizes,
                words=words_by_block.get(int(b.get("number", -1))) or None,
            )
        )
    return blocks


def _attach_tables(page: pymupdf.Page, raw: RawPage) -> None:
    try:
        finder = page.find_tables()
    except Exception:  # pragma: no cover - depends on PyMuPDF build
        return
    for table in getattr(finder, "tables", []):
        try:
            rows = table.extract()
        except Exception:  # pragma: no cover
            continue
        rows = [[(c or "").strip() for c in row] for row in rows]
        rows = [r for r in rows if any(r)]
        if len(rows) < 2 or max(len(r) for r in rows) < 2:
            continue
        tb = pymupdf.Rect(table.bbox)
        # Remove text blocks swallowed by the table and replace with one table block.
        kept: list[RawBlock] = []
        for b in raw.blocks:
            r = pymupdf.Rect(b.bbox)
            inter = r & tb
            if not r.is_empty and inter.get_area() > 0.6 * r.get_area():
                continue
            kept.append(b)
        text = "\n".join(" | ".join(c for c in row) for row in rows)
        table_words = [w for b in raw.blocks if b.words for w in b.words if pymupdf.Rect(w["bbox"]).intersects(tb)]
        kept.append(
            RawBlock(
                text=text,
                bbox=(float(tb.x0), float(tb.y0), float(tb.x1), float(tb.y1)),
                source="embedded",
                confidence=1.0,
                lines=[" | ".join(row) for row in rows],
                table={"rows": rows},
                block_type="table",
                words=table_words or None,
            )
        )
        kept.sort(key=lambda b: (round(b.bbox[1] / 5), b.bbox[0]))
        raw.blocks = kept


def _ocr_page(page: pymupdf.Page, raw: RawPage) -> None:
    """Render the page for OCR and fill `raw` with the best reading (blocks)
    and the second reader's lines (for verification)."""
    settings = get_settings()
    zoom = settings.ocr_dpi / 72.0
    pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
    img = _pix_to_pil(pix)
    ocr_image_into(img, zoom, raw)


def ocr_image_into(img: Image.Image, scale: float, raw: RawPage) -> None:
    """Run all readers on the image; the best becomes the page text, the next
    is kept as the independent second reading. Coordinates: pixel / scale."""
    readings = run_ocr_readings(img)
    if not readings:
        raw.blocks, raw.text_source, raw.ocr_confidence = [], "none", None
        return
    best = readings[0]
    blocks, conf = _blocks_from_reading(best.blocks, scale)
    raw.blocks = blocks
    raw.text_source = "ocr" if blocks else "none"
    raw.ocr_confidence = conf
    raw.ocr_engine = best.engine
    if len(readings) > 1:
        alt = readings[1]
        raw.alt_ocr_engine = alt.engine
        raw.alt_ocr = [
            {"t": ln.text, "c": round(ln.confidence, 3), "bbox": [v / scale for v in ln.bbox]}
            for b in alt.blocks
            for ln in b.lines
            if ln.text.strip()
        ]


def ocr_image_to_blocks(img: Image.Image, scale: float) -> tuple[list[RawBlock], float | None]:
    """OCR an image with the best reader and return blocks in page coordinates (pixel / scale)."""
    ocr_blocks, _ = run_ocr(img)
    return _blocks_from_reading(ocr_blocks, scale)


def _blocks_from_reading(ocr_blocks, scale: float) -> tuple[list[RawBlock], float | None]:
    blocks: list[RawBlock] = []
    confs: list[float] = []
    for ob in ocr_blocks:
        lines: list[str] = []
        words: list[dict] = []
        norms: list[dict] = []
        for ln in ob.lines:
            res = normalise_technical_text(ln.text)
            lines.append(res.text)
            norms.extend({"original": n.original, "normalised": n.normalised, "rule": n.rule} for n in res.normalisations)
            for w in ln.words:
                x0, y0, x1, y1 = w.bbox
                words.append({"t": w.text, "c": round(w.confidence, 3), "bbox": [x0 / scale, y0 / scale, x1 / scale, y1 / scale]})
        text = "\n".join(lines).strip()
        if not text:
            continue
        x0, y0, x1, y1 = ob.bbox
        line_heights = [(ln.bbox[3] - ln.bbox[1]) / scale for ln in ob.lines]
        blocks.append(
            RawBlock(
                text=text,
                bbox=(x0 / scale, y0 / scale, x1 / scale, y1 / scale),
                source="ocr",
                confidence=ob.confidence,
                font_size=statistics.median(line_heights) if line_heights else None,
                lines=lines,
                words=words,
                normalisations=norms,
            )
        )
        confs.append(ob.confidence)
    return blocks, (sum(confs) / len(confs) if confs else None)
