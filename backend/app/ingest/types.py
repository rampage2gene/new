"""Intermediate representation shared by readers, OCR and structure analysis."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RawBlock:
    text: str
    bbox: tuple[float, float, float, float]
    source: str  # embedded | ocr
    confidence: float = 1.0
    font_size: float | None = None
    bold: bool = False
    lines: list[str] = field(default_factory=list)
    line_sizes: list[float] | None = None
    words: list[dict] | None = None  # OCR words: {"t":..., "c":..., "bbox":[...]} in page coords
    table: dict | None = None  # {"rows": [[...], ...]}
    block_type: str = "paragraph"
    section: str | None = None
    section_level: int = 0
    normalisations: list[dict] = field(default_factory=list)


@dataclass
class RawPage:
    page_number: int
    width: float
    height: float
    blocks: list[RawBlock] = field(default_factory=list)
    text_source: str = "none"  # embedded | ocr | none
    ocr_confidence: float | None = None
    image_path: str | None = None
    drawings: int = 0
    images: int = 0
    image_area_ratio: float = 0.0
    diagram_score: float = 0.0
    is_diagram: bool = False
    page_label: str | None = None
    ocr_engine: str | None = None  # engine that produced the page text (ocr pages)
    alt_ocr_engine: str | None = None  # the independent second reader, when there was one
    alt_ocr: list[dict] | None = None  # its lines: {"t": text, "c": conf, "bbox": [...]} in page coords

    @property
    def text(self) -> str:
        return "\n\n".join(b.text for b in self.blocks if b.text.strip())

    @property
    def char_count(self) -> int:
        return sum(len(b.text) for b in self.blocks)
