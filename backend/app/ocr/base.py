"""OCR engine abstraction.

Engines return words with pixel-space bounding boxes and per-word confidence
(0..1). The pipeline groups words into lines/blocks and converts coordinates
to page space, so an engine can be swapped without touching anything else.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from PIL import Image


@dataclass
class OCRWord:
    text: str
    confidence: float  # 0..1
    bbox: tuple[float, float, float, float]  # x0, y0, x1, y1 in image pixels
    block: int = 0
    paragraph: int = 0
    line: int = 0


@dataclass
class OCRLine:
    words: list[OCRWord] = field(default_factory=list)

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words)

    @property
    def bbox(self) -> tuple[float, float, float, float]:
        return _union([w.bbox for w in self.words])

    @property
    def confidence(self) -> float:
        return _mean([w.confidence for w in self.words])


@dataclass
class OCRBlock:
    lines: list[OCRLine] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n".join(line.text for line in self.lines)

    @property
    def bbox(self) -> tuple[float, float, float, float]:
        return _union([line.bbox for line in self.lines])

    @property
    def confidence(self) -> float:
        words = [w for line in self.lines for w in line.words]
        return _mean([w.confidence for w in words])

    @property
    def words(self) -> list[OCRWord]:
        return [w for line in self.lines for w in line.words]


def _union(boxes):
    if not boxes:
        return (0.0, 0.0, 0.0, 0.0)
    return (
        min(b[0] for b in boxes),
        min(b[1] for b in boxes),
        max(b[2] for b in boxes),
        max(b[3] for b in boxes),
    )


def _mean(values):
    return sum(values) / len(values) if values else 0.0


class ReaderStopped(RuntimeError):
    """A reader's process died or did not answer in time, so it never read the
    page. Distinct from an ordinary failure: the page can still be read by the
    other reader, and the reader itself can be started again."""


class OCREngine(Protocol):
    name: str

    def available(self) -> bool: ...

    def recognize(self, image: Image.Image) -> list[OCRBlock]: ...


def group_words(words: list[OCRWord]) -> list[OCRBlock]:
    """Group engine words into blocks/lines using their layout ids."""
    blocks: dict[int, dict[tuple[int, int], OCRLine]] = {}
    order: list[int] = []
    for w in words:
        if w.block not in blocks:
            blocks[w.block] = {}
            order.append(w.block)
        key = (w.paragraph, w.line)
        blocks[w.block].setdefault(key, OCRLine()).words.append(w)
    result: list[OCRBlock] = []
    for b in order:
        lines = [blocks[b][k] for k in sorted(blocks[b].keys())]
        lines = [ln for ln in lines if ln.words]
        if lines:
            result.append(OCRBlock(lines=lines))
    return result
