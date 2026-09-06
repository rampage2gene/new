"""Tesseract OCR engine (via pytesseract)."""
from __future__ import annotations

import os
import shutil
import threading

from PIL import Image, ImageOps

from ..config import get_settings
from .base import OCRBlock, OCRWord, group_words


# Tesseract's OpenMP worker threads busy-wait; in containers with few cores two
# concurrent OCR runs can oversubscribe the CPU by an order of magnitude. One
# thread per process plus one OCR run at a time is faster and predictable.
os.environ.setdefault("OMP_THREAD_LIMIT", "1")
_OCR_LOCK = threading.Lock()


class TesseractEngine:
    name = "tesseract"

    def __init__(self, languages: str | None = None):
        self.languages = languages or get_settings().ocr_languages

    def available(self) -> bool:
        return shutil.which("tesseract") is not None

    def recognize(self, image: Image.Image) -> list[OCRBlock]:
        import pytesseract

        prepared = preprocess(image)
        # PSM 3 = fully automatic page segmentation; technical manuals are
        # multi-column with tables so we let Tesseract find the layout.
        config = "--oem 3 --psm 3"
        with _OCR_LOCK:
            data = pytesseract.image_to_data(
                prepared, lang=self.languages, config=config, output_type=pytesseract.Output.DICT
            )
        words: list[OCRWord] = []
        n = len(data["text"])
        for i in range(n):
            text = (data["text"][i] or "").strip()
            if not text:
                continue
            try:
                conf = float(data["conf"][i])
            except (TypeError, ValueError):
                conf = -1.0
            if conf < 0:
                conf = 0.0
            x, y, w, h = (data["left"][i], data["top"][i], data["width"][i], data["height"][i])
            words.append(
                OCRWord(
                    text=text,
                    confidence=max(0.0, min(1.0, conf / 100.0)),
                    bbox=(float(x), float(y), float(x + w), float(y + h)),
                    block=int(data["block_num"][i]),
                    paragraph=int(data["par_num"][i]),
                    line=int(data["line_num"][i]),
                )
            )
        return group_words(words)


def preprocess(image: Image.Image) -> Image.Image:
    """Light-touch preprocessing: grayscale, autocontrast, upscale small scans."""
    img = image.convert("L")
    img = ImageOps.autocontrast(img, cutoff=1)
    w, h = img.size
    if max(w, h) < 1500:
        factor = 2
        img = img.resize((w * factor, h * factor), Image.LANCZOS)
        img.info["mdi_scale"] = factor
    return img
