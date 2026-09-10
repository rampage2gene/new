"""OCR engine selection and the two-reader run.

Every scanned page is read by every available engine. The reading with the
best text becomes the page's text (blocks, word boxes, search index); the
other readings are kept so the verification pass can check each extracted
value against an independent second reading of the same spot.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from PIL import Image

from ..config import get_settings
from .base import OCRBlock, OCREngine, ReaderStopped
from .rapid import RapidEngine, rapid_version, unavailable_reason
from .tesseract import TesseractEngine

log = logging.getLogger(__name__)


class NullEngine:
    name = "none"

    def available(self) -> bool:
        return True

    def recognize(self, image: Image.Image) -> list[OCRBlock]:
        return []


@dataclass
class OCRReading:
    engine: str
    blocks: list[OCRBlock]

    @property
    def mean_confidence(self) -> float:
        words = [w for b in self.blocks for w in b.words]
        return sum(w.confidence for w in words) / len(words) if words else 0.0

    @property
    def char_count(self) -> int:
        return sum(len(w.text) for b in self.blocks for w in b.words)


def get_ocr_engines(exclude: frozenset[str] = frozenset()) -> list[OCREngine]:
    """Engines to run, best first, according to `MDI_OCR_ENGINE`:
    auto (both when available) | rapid | tesseract | none. `exclude` names
    readers to leave out - one that has already stopped too often in the
    document being read."""
    s = get_settings()
    choice = (s.ocr_engine or "auto").lower()
    if choice == "none":
        return []
    engines: list[OCREngine] = []
    if choice in ("auto", "rapid", "rapidocr") and RapidEngine.name not in exclude:
        rapid = RapidEngine()
        if rapid.available():
            engines.append(rapid)
        elif choice != "auto":
            raise RuntimeError(f"RapidOCR requested but it could not be loaded: {unavailable_reason()}")
    if choice in ("auto", "tesseract") and TesseractEngine.name not in exclude:
        tess = TesseractEngine()
        if tess.available():
            engines.append(tess)
        elif choice == "tesseract":
            raise RuntimeError("Tesseract OCR requested but the `tesseract` binary was not found")
    return engines


def get_ocr_engine() -> OCREngine:
    """The primary engine (kept for callers that want a single reader)."""
    engines = get_ocr_engines()
    return engines[0] if engines else NullEngine()


def engine_status() -> dict:
    """What Diagnostics shows: which readers this installation has."""
    tess = TesseractEngine()
    rapid = RapidEngine()
    status = {
        "configured": get_settings().ocr_engine,
        "tesseract": tess.available(),
        "rapidocr": rapid.available(),
        "rapidocr_version": rapid_version() if rapid.available() else None,
        "rapidocr_error": None if rapid.available() else unavailable_reason(),
        "readers": [e.name for e in get_ocr_engines()],
    }
    if get_settings().ocr_isolate:
        from .worker import get_worker

        status["rapidocr_worker"] = get_worker().status()  # its process, and how often it has stopped
    return status


def _undo_upscale(engine: OCREngine, image: Image.Image, blocks: list[OCRBlock]) -> None:
    """Tesseract reads a 2x upscale of small images; map its boxes back."""
    from .tesseract import TesseractEngine as _T

    w, h = image.size
    if isinstance(engine, _T) and max(w, h) < 1500:
        for b in blocks:
            for ln in b.lines:
                for wd in ln.words:
                    x0, y0, x1, y1 = wd.bbox
                    wd.bbox = (x0 / 2.0, y0 / 2.0, x1 / 2.0, y1 / 2.0)


@dataclass
class PageReadings:
    readings: list[OCRReading]  # best first
    stopped: list[str]  # readers whose process died or did not answer on this page


def read_page(image: Image.Image, exclude: frozenset[str] | set[str] = frozenset()) -> PageReadings:
    """Run every configured engine on the image. Readings come back best
    first, all with bboxes in *image pixel* coordinates. A reader that stops
    is named rather than raised: the page goes on with the other reader, and
    the caller records what that page's values rest on."""
    readings: list[OCRReading] = []
    stopped: list[str] = []
    for engine in get_ocr_engines(frozenset(exclude)):
        try:
            blocks = engine.recognize(image)
        except ReaderStopped as exc:
            log.warning("ocr: the %s reader stopped on a page: %s", engine.name, exc)
            stopped.append(engine.name)
            continue
        except Exception as exc:  # noqa: BLE001 - one broken engine must not lose the page
            log.warning("ocr: %s failed on a page: %s", engine.name, exc)
            continue
        _undo_upscale(engine, image, blocks)
        readings.append(OCRReading(engine=engine.name, blocks=blocks))
    return PageReadings(_rank(readings), stopped)


def run_ocr_readings(image: Image.Image) -> list[OCRReading]:
    """The readings alone, for callers that do not track stopped readers."""
    return read_page(image).readings


def _rank(readings: list[OCRReading]) -> list[OCRReading]:
    """Pick the page text. The engines' confidences are not on the same scale
    (PP-OCR scores run higher than Tesseract's), so the order of preference is
    the configured order unless the preferred reading is clearly worse: it saw
    much less text, or it is far less sure of what it saw."""
    if len(readings) < 2:
        return readings
    best = readings[0]
    for other in readings[1:]:
        if best.char_count < 0.6 * other.char_count or best.mean_confidence + 0.15 < other.mean_confidence:
            best = other
    return [best] + [r for r in readings if r is not best]


def run_ocr(image: Image.Image) -> tuple[list[OCRBlock], float]:
    """Compatibility wrapper: the best reading's blocks in image coordinates
    and a scale of 1.0 (boxes are already mapped back to the input image)."""
    readings = run_ocr_readings(image)
    return (readings[0].blocks if readings else []), 1.0
