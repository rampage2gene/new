"""Layout analysis: classify blocks and assign them to sections.

Works on both embedded-text pages (font metrics available) and OCR pages
(line height used as a proxy for font size).
"""
from __future__ import annotations

import re
import statistics

from ..ingest.types import RawBlock, RawPage

WARNING_RE = re.compile(r"^\s*(?:⚠\s*)?(WARNING|DANGER|CAUTION|NOTICE|IMPORTANT|ATTENTION|AVERTISSEMENT)\b[:!\s]*", re.I)
NOTE_RE = re.compile(r"^\s*(NOTE|NOTES|TIP|HINT)\b[:\s]", re.I)
CAPTION_RE = re.compile(r"^\s*(Figure|Fig\.?|Table|Diagram|Drawing|Illustration|Photo)\s*\d+[A-Za-z]?\b", re.I)
NUMBERED_HEADING_RE = re.compile(r"^\s*(\d{1,2}(?:\.\d{1,2}){0,3})\.?\s+([A-Z][^\n]{2,90})$")
APPENDIX_RE = re.compile(r"^\s*(Appendix|Annex)\s+[A-Z0-9]+\b", re.I)
SECTION_WORD_RE = re.compile(r"^\s*(Section|Chapter)\s+\d+", re.I)
BULLET_RE = re.compile(r"^\s*(?:[•\-–•*]|\d{1,2}[.)]|[a-z][.)])\s+")
PAGE_NUM_RE = re.compile(r"^\s*(?:page\s*)?(\d{1,4})(?:\s*(?:of|/)\s*\d{1,4})?\s*$", re.I)
DIAGRAM_KEYWORDS = re.compile(r"\b(wiring diagram|schematic|single[- ]line|one[- ]line|block diagram|connection diagram|system diagram|interconnect)\b", re.I)
TITLE_CASE_RE = re.compile(r"^[A-Z][A-Za-z0-9&/(),'\- ]{2,80}$")


def _body_font_size(pages: list[RawPage]) -> float:
    sizes: list[float] = []
    for p in pages:
        for b in p.blocks:
            if b.font_size and len(b.text) > 40:
                sizes.extend([b.font_size] * min(50, len(b.text) // 10 + 1))
    if not sizes:
        for p in pages:
            for b in p.blocks:
                if b.font_size:
                    sizes.append(b.font_size)
    return statistics.median(sizes) if sizes else 10.0


def _looks_like_heading(b: RawBlock, body_size: float, page: RawPage) -> tuple[bool, int]:
    text = b.text.strip()
    if b.table or not text or len(text) > 120 or len(b.lines) > 2:
        return False, 0
    if text.endswith((".", ",", ";")) and not NUMBERED_HEADING_RE.match(text):
        return False, 0
    if re.search(r"\d\s*(V|A|W|AWG|Hz|mm²)\b", text) and not NUMBERED_HEADING_RE.match(text):
        return False, 0  # a spec line, not a heading
    m = NUMBERED_HEADING_RE.match(text)
    if m:
        level = m.group(1).count(".") + 1
        return True, min(level, 4)
    if APPENDIX_RE.match(text) or SECTION_WORD_RE.match(text):
        return True, 1
    ratio = (b.font_size or body_size) / body_size if body_size else 1.0
    words = text.split()
    if ratio >= 1.5 and len(words) <= 12:
        return True, 1
    if ratio >= 1.2 and len(words) <= 12:
        return True, 2
    if b.bold and len(words) <= 10 and ratio >= 0.95:
        return True, 3
    if text.isupper() and 2 <= len(words) <= 8 and len(text) >= 6 and ratio >= 0.95:
        return True, 2
    return False, 0


def _is_heading_line(line: str, size: float | None, block_min_size: float | None) -> bool:
    t = line.strip()
    if not t or len(t) > 90:
        return False
    if NUMBERED_HEADING_RE.match(t) or APPENDIX_RE.match(t):
        return True
    if size and block_min_size and size >= 1.2 * block_min_size and len(t.split()) <= 12:
        return True
    return False


def split_heading_lines(pages: list[RawPage]) -> None:
    """PDF extractors often merge a short heading with the paragraph before or
    after it. Split such blocks so each heading can anchor a section."""
    for page in pages:
        new_blocks: list[RawBlock] = []
        for b in page.blocks:
            if b.table or len(b.lines) < 2:
                new_blocks.append(b)
                continue
            sizes = b.line_sizes if b.line_sizes and len(b.line_sizes) == len(b.lines) else [None] * len(b.lines)
            min_size = min((sz for sz in sizes if sz), default=None)
            flags = [_is_heading_line(ln, sz, min_size) for ln, sz in zip(b.lines, sizes)]
            if not any(flags) or all(flags):
                new_blocks.append(b)
                continue
            # Build segments: each heading line alone; runs of body lines together.
            segments: list[tuple[int, int, bool]] = []  # (start, end, is_heading)
            i = 0
            while i < len(b.lines):
                if flags[i]:
                    segments.append((i, i + 1, True))
                    i += 1
                else:
                    j = i
                    while j < len(b.lines) and not flags[j]:
                        j += 1
                    segments.append((i, j, False))
                    i = j
            x0, y0, x1, y1 = b.bbox
            line_h = (y1 - y0) / len(b.lines)
            for st, en, is_head in segments:
                sy0, sy1 = y0 + st * line_h, y0 + en * line_h
                words = [w for w in (b.words or []) if sy0 - 1 <= (w["bbox"][1] + w["bbox"][3]) / 2 <= sy1 + 1] or None
                if words:
                    sy0 = min(sy0, min(w["bbox"][1] for w in words))
                    sy1 = max(sy1, max(w["bbox"][3] for w in words))
                seg_lines = b.lines[st:en]
                seg_sizes = [sz for sz in sizes[st:en] if sz]
                new_blocks.append(
                    RawBlock(
                        text="\n".join(seg_lines),
                        bbox=(x0, sy0, x1, sy1),
                        source=b.source,
                        confidence=b.confidence,
                        font_size=(statistics.median(seg_sizes) if seg_sizes else b.font_size),
                        bold=b.bold if is_head else False,
                        lines=seg_lines,
                        line_sizes=[sz for sz in sizes[st:en]] if b.line_sizes else None,
                        words=words,
                        normalisations=b.normalisations if not is_head else [],
                    )
                )
        page.blocks = new_blocks


def classify_blocks(pages: list[RawPage]) -> None:
    split_heading_lines(pages)
    body_size = _body_font_size(pages)
    for page in pages:
        page_h = page.height or 1.0
        for b in page.blocks:
            if b.table:
                b.block_type = "table"
                continue
            text = b.text.strip()
            y_top, y_bot = b.bbox[1] / page_h, b.bbox[3] / page_h
            short = len(text) <= 80 and len(b.lines) <= 1
            if PAGE_NUM_RE.match(text) and (y_bot > 0.9 or y_top < 0.08):
                b.block_type = "page_number"
                page.page_label = page.page_label or PAGE_NUM_RE.match(text).group(1)
                continue
            big = (b.font_size or body_size) / body_size >= 1.25 if body_size else False
            if short and not big and (y_bot > 0.94 or y_top < 0.05) and not NUMBERED_HEADING_RE.match(text):
                b.block_type = "footer" if y_bot > 0.94 else "header"
                continue
            if WARNING_RE.match(text):
                b.block_type = "warning"
                continue
            if NOTE_RE.match(text):
                b.block_type = "note"
                continue
            if CAPTION_RE.match(text) and len(text) < 200:
                b.block_type = "caption"
                continue
            is_heading, level = _looks_like_heading(b, body_size, page)
            if is_heading:
                b.block_type = "heading"
                b.section_level = level
                continue
            if BULLET_RE.match(text):
                b.block_type = "list"
                continue
            if len(text.split()) <= 3 and len(text) < 30:
                b.block_type = "label"
                continue
            b.block_type = "paragraph"


def assign_sections(pages: list[RawPage]) -> list[dict]:
    """Walk blocks in reading order, tracking a heading stack. Returns the
    section outline: [{title, level, page, bbox}]."""
    outline: list[dict] = []
    stack: list[tuple[int, str]] = []
    for page in pages:
        for b in page.blocks:
            if b.block_type == "heading":
                level = b.section_level or 2
                while stack and stack[-1][0] >= level:
                    stack.pop()
                stack.append((level, b.text.strip().replace("\n", " ")))
                outline.append({"title": stack[-1][1], "level": level, "page": page.page_number, "bbox": list(b.bbox)})
                b.section = stack[-1][1]
                b.section_level = level
            else:
                b.section = stack[-1][1] if stack else None
                b.section_level = stack[-1][0] if stack else 0
    return outline


def score_diagram_pages(pages: list[RawPage]) -> None:
    for page in pages:
        text_blocks = [b for b in page.blocks if b.block_type not in ("header", "footer", "page_number")]
        chars = sum(len(b.text) for b in text_blocks)
        short_labels = sum(1 for b in text_blocks if len(b.text) < 30)
        label_ratio = short_labels / len(text_blocks) if text_blocks else 0.0
        area = max(1.0, page.width * page.height)
        text_density = chars / area * 1000.0  # chars per 1000 pt²
        keyword = any(DIAGRAM_KEYWORDS.search(b.text) for b in text_blocks)
        score = 0.0
        if page.drawings > 150:
            score += 0.35
        elif page.drawings > 40:
            score += 0.2
        if label_ratio > 0.6 and len(text_blocks) >= 6:
            score += 0.3
        if text_density < 1.5:
            score += 0.15
        if keyword:
            score += 0.3
        if page.image_area_ratio > 0.5 and text_density < 2.0:
            score += 0.2
        page.diagram_score = round(min(1.0, score), 2)
        page.is_diagram = page.diagram_score >= 0.5


def analyse_layout(pages: list[RawPage]) -> dict:
    classify_blocks(pages)
    outline = assign_sections(pages)
    score_diagram_pages(pages)
    warnings = []
    figures = []
    tables = []
    for page in pages:
        for b in page.blocks:
            if b.block_type == "warning":
                warnings.append({"page": page.page_number, "text": b.text.strip(), "section": b.section, "bbox": list(b.bbox)})
            elif b.block_type == "caption":
                figures.append({"page": page.page_number, "caption": b.text.strip(), "section": b.section, "bbox": list(b.bbox)})
            elif b.block_type == "table":
                rows = (b.table or {}).get("rows", [])
                tables.append({"page": page.page_number, "section": b.section, "rows": rows, "bbox": list(b.bbox), "header": rows[0] if rows else []})
    return {
        "sections": outline,
        "warnings": warnings,
        "figures": figures,
        "tables": tables,
        "diagram_pages": [p.page_number for p in pages if p.is_diagram],
    }
