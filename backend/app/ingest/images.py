"""Image reader: a photograph or scan becomes a single OCR'd page."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageOps

from ..storage.files import page_image_path
from .pdf import ocr_image_to_blocks
from .types import RawPage

MAX_DISPLAY = 2200


def read_image(path: Path, document_id: str, progress=None) -> list[RawPage]:
    if progress:
        progress("Reading image")
    img = Image.open(path)
    img = ImageOps.exif_transpose(img).convert("RGB")
    w, h = img.size
    raw = RawPage(page_number=1, width=float(w), height=float(h))

    # Display copy (downscaled if enormous; the viewer scales overlays by page size).
    display = img.copy()
    if max(w, h) > MAX_DISPLAY:
        display.thumbnail((MAX_DISPLAY, MAX_DISPLAY))
    out = page_image_path(document_id, 1)
    display.save(out, format="PNG")
    raw.image_path = str(out)

    if progress:
        progress("Running OCR")
    blocks, conf = ocr_image_to_blocks(img, scale=1.0)
    raw.blocks = blocks
    raw.text_source = "ocr" if blocks else "none"
    raw.ocr_confidence = conf
    raw.images = 1
    raw.image_area_ratio = 1.0
    return [raw]
