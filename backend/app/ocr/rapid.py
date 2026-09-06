"""RapidOCR engine (PP-OCR detection + recognition models via onnxruntime).

An independent reader next to Tesseract. PP-OCR reads whole text lines with
a CRNN-style recogniser, Tesseract reads characters with an LSTM; they fail
in different ways, which is what makes their agreement on a value worth
trusting. The models ship inside the ``rapidocr`` wheel, run on the CPU and
never touch the network.
"""
from __future__ import annotations

import logging
import threading

from PIL import Image

from .base import OCRBlock, OCRLine, OCRWord

log = logging.getLogger(__name__)

_engine = None
_engine_error: str | None = None
_lock = threading.Lock()

Quad = list  # [[x, y] * 4]


def _load():
    """Import and build the RapidOCR runner once per process."""
    global _engine, _engine_error
    if _engine is not None or _engine_error is not None:
        return _engine
    with _lock:
        if _engine is not None or _engine_error is not None:
            return _engine
        try:
            logging.getLogger("RapidOCR").setLevel(logging.WARNING)
            from rapidocr import RapidOCR

            _engine = RapidOCR(params={"Global.return_word_box": True, "Global.log_level": "warning"})
            log.info("rapidocr: models loaded")
        except Exception as exc:  # noqa: BLE001 - any import/runtime failure means "not available"
            _engine_error = f"{type(exc).__name__}: {exc}"
            log.warning("rapidocr unavailable: %s", _engine_error)
    return _engine


def rapid_version() -> str | None:
    try:
        from importlib.metadata import version

        return version("rapidocr")
    except Exception:  # noqa: BLE001
        return None


def unavailable_reason() -> str | None:
    _load()
    return _engine_error


def _rect(quad) -> tuple[float, float, float, float]:
    xs = [float(p[0]) for p in quad]
    ys = [float(p[1]) for p in quad]
    return (min(xs), min(ys), max(xs), max(ys))


class RapidEngine:
    name = "rapidocr"

    def available(self) -> bool:
        return _load() is not None

    def recognize(self, image: Image.Image) -> list[OCRBlock]:
        import numpy as np

        engine = _load()
        if engine is None:
            return []
        arr = np.asarray(image.convert("RGB"))
        with _lock:
            result = engine(arr)
        return _to_blocks(result)


def _to_blocks(result) -> list[OCRBlock]:
    """Turn a RapidOCROutput into lines of words with pixel boxes."""
    lines: list[tuple[tuple[float, float, float, float], list[OCRWord]]] = []
    word_lines = getattr(result, "word_results", None) or ()
    txts = list(getattr(result, "txts", None) or [])
    scores = list(getattr(result, "scores", None) or [])
    boxes = getattr(result, "boxes", None)
    if word_lines and len(word_lines) == len(txts):
        # Word boxes for every line: the best case.
        for i, word_line in enumerate(word_lines):
            words = []
            for txt, score, quad in word_line:
                txt = str(txt).strip()
                if not txt or quad is None:
                    continue
                words.append(OCRWord(text=txt, confidence=_clamp(score), bbox=_rect(quad)))
            if words:
                lines.append((_rect(boxes[i]) if boxes is not None else _union(words), words))
    else:
        # Line boxes only: apportion each line across its words by character count.
        for i, txt in enumerate(txts):
            txt = str(txt).strip()
            if not txt or boxes is None:
                continue
            conf = _clamp(scores[i] if i < len(scores) else 0.0)
            bbox = _rect(boxes[i])
            words = _split_words(bbox, txt, conf)
            if words:
                lines.append((bbox, words))
    return group_lines(lines)


def _clamp(v) -> float:
    try:
        return max(0.0, min(1.0, float(v)))
    except (TypeError, ValueError):
        return 0.0


def _union(words: list[OCRWord]) -> tuple[float, float, float, float]:
    return (
        min(w.bbox[0] for w in words),
        min(w.bbox[1] for w in words),
        max(w.bbox[2] for w in words),
        max(w.bbox[3] for w in words),
    )


def _split_words(bbox: tuple[float, float, float, float], text: str, conf: float) -> list[OCRWord]:
    x0, y0, x1, y1 = bbox
    tokens = text.split()
    if not tokens:
        return []
    total = max(1, len(text))
    width = x1 - x0
    words: list[OCRWord] = []
    pos = 0
    for tok in tokens:
        start = text.find(tok, pos)
        if start < 0:
            start = pos
        end = start + len(tok)
        pos = end
        words.append(OCRWord(text=tok, confidence=conf, bbox=(x0 + width * start / total, y0, x0 + width * end / total, y1)))
    return words


def group_lines(lines: list[tuple[tuple[float, float, float, float], list[OCRWord]]]) -> list[OCRBlock]:
    """Group detected lines into blocks: consecutive lines (top to bottom) that
    are vertically close and horizontally overlapping belong together."""
    if not lines:
        return []
    ordered = sorted(lines, key=lambda ln: (round(ln[0][1] / 4), ln[0][0]))
    groups: list[list[tuple[tuple[float, float, float, float], list[OCRWord]]]] = []
    for ln in ordered:
        bx0, by0, bx1, by1 = ln[0]
        height = max(1.0, by1 - by0)
        if groups:
            last = groups[-1][-1][0]
            gap = by0 - last[3]
            overlap = min(bx1, last[2]) - max(bx0, last[0])
            if -height * 0.5 <= gap <= height * 0.9 and overlap > -height:
                groups[-1].append(ln)
                continue
        groups.append([ln])
    out: list[OCRBlock] = []
    for b_idx, group in enumerate(groups):
        ocr_lines: list[OCRLine] = []
        for l_idx, (_bbox, words) in enumerate(group):
            for w in words:
                w.block, w.paragraph, w.line = b_idx, 0, l_idx
            ocr_lines.append(OCRLine(words=list(words)))
        out.append(OCRBlock(lines=ocr_lines))
    return out
