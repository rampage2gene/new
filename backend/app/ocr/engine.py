"""OCR engine selection."""
from __future__ import annotations

from PIL import Image

from ..config import get_settings
from .base import OCRBlock, OCREngine
from .tesseract import TesseractEngine


class NullEngine:
    name = "none"

    def available(self) -> bool:
        return True

    def recognize(self, image: Image.Image) -> list[OCRBlock]:
        return []


def get_ocr_engine() -> OCREngine:
    s = get_settings()
    if s.ocr_engine in ("auto", "tesseract"):
        eng = TesseractEngine()
        if eng.available():
            return eng
        if s.ocr_engine == "tesseract":
            raise RuntimeError("Tesseract OCR requested but the `tesseract` binary was not found")
    return NullEngine()


def run_ocr(image: Image.Image) -> tuple[list[OCRBlock], float]:
    """Run OCR on an image. Returns blocks in *image pixel* coordinates and the
    scale factor that was applied during preprocessing (coordinates are already
    divided back to the original image space)."""
    engine = get_ocr_engine()
    blocks = engine.recognize(image)
    # Undo the upscale applied in preprocess so bboxes map to the input image.
    from .tesseract import preprocess  # noqa: WPS433

    w, h = image.size
    scale = 2.0 if max(w, h) < 1500 and engine.name == "tesseract" else 1.0
    if scale != 1.0:
        for b in blocks:
            for ln in b.lines:
                for wd in ln.words:
                    x0, y0, x1, y1 = wd.bbox
                    wd.bbox = (x0 / scale, y0 / scale, x1 / scale, y1 / scale)
    return blocks, scale
