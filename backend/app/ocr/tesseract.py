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
        """Read the page; when the first pass is weak, read the binarised page
        too and keep whichever pass Tesseract was more sure about."""
        prepared = preprocess(image)
        first = self._pass(prepared, "--oem 3 --psm 3 -c preserve_interword_spaces=1")
        retry_below = get_settings().ocr_retry_below
        if retry_below > 0 and _mean_conf(first) < retry_below:
            second = self._pass(binarize(prepared), "--oem 3 --psm 3 -c preserve_interword_spaces=1")
            if second and _mean_conf(second) > _mean_conf(first):
                return second
        return first

    def recognize_line(self, image: Image.Image) -> list[OCRBlock]:
        """Read a small crop that holds a single line (used to re-check one value)."""
        prepared = preprocess(image)
        w, h = prepared.size
        if max(w, h) < 900:  # crops are tiny; Tesseract wants ~30 px x-height
            prepared = prepared.resize((w * 3, h * 3), Image.LANCZOS)
        # Grayscale, not binarised: on a sharp crop the anti-aliasing helps.
        return self._pass(prepared, "--oem 3 --psm 7 -c preserve_interword_spaces=1")

    def _pass(self, prepared: Image.Image, config: str) -> list[OCRBlock]:
        import pytesseract

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


def otsu_threshold(gray: Image.Image) -> int:
    """Otsu's threshold from the histogram (pure PIL, no numpy needed)."""
    hist = gray.histogram()[:256]
    total = sum(hist)
    if total == 0:
        return 128
    sum_all = sum(i * h for i, h in enumerate(hist))
    sum_bg = 0.0
    weight_bg = 0
    best, best_t = -1.0, 128
    for t in range(256):
        weight_bg += hist[t]
        if weight_bg == 0:
            continue
        weight_fg = total - weight_bg
        if weight_fg == 0:
            break
        sum_bg += t * hist[t]
        mean_bg = sum_bg / weight_bg
        mean_fg = (sum_all - sum_bg) / weight_fg
        between = weight_bg * weight_fg * (mean_bg - mean_fg) ** 2
        if between > best:
            best, best_t = between, t
    return best_t


def binarize(image: Image.Image) -> Image.Image:
    """Black-and-white copy: dark ink on a white page, faint shading removed."""
    gray = image if image.mode == "L" else image.convert("L")
    t = otsu_threshold(gray)
    return gray.point(lambda v: 255 if v > t else 0, mode="L")


def _mean_conf(blocks: list[OCRBlock]) -> float:
    words = [w for b in blocks for w in b.words]
    return sum(w.confidence for w in words) / len(words) if words else 0.0
