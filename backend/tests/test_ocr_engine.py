"""Two OCR readers: RapidOCR (PP-OCR) and Tesseract, and how a page's text is chosen."""
from __future__ import annotations

from pathlib import Path

import pymupdf
import pytest
from PIL import Image

from app.ocr import engine as E
from app.ocr.base import OCRBlock, OCRLine, OCRWord
from app.ocr.rapid import RapidEngine, group_lines
from app.ocr.tesseract import TesseractEngine, binarize, otsu_threshold


def _page_image(pdf: Path, index: int = 2, dpi: int = 300) -> Image.Image:
    doc = pymupdf.open(pdf)
    zoom = dpi / 72
    pix = doc[index].get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    doc.close()
    return img


def test_otsu_binarise_gives_two_levels():
    img = Image.new("L", (40, 40), 200)
    for x in range(10, 30):
        for y in range(10, 30):
            img.putpixel((x, y), 40)
    t = otsu_threshold(img)
    assert 40 <= t < 200
    out = binarize(img)
    assert set(out.getdata()) == {0, 255}
    assert out.getpixel((20, 20)) == 0 and out.getpixel((2, 2)) == 255


def test_rapidocr_reads_words_with_boxes(fixtures_dir: Path):
    eng = RapidEngine()
    if not eng.available():
        pytest.skip("rapidocr is not installed in this environment")
    blocks = eng.recognize(_page_image(fixtures_dir / "XYZ-5000 Manual (scanned).pdf"))
    words = [w for b in blocks for w in b.words]
    text = " ".join(w.text for w in words)
    assert "300 A" in text and "4/0 AWG" in text, text
    assert all(w.bbox[2] > w.bbox[0] and w.bbox[3] > w.bbox[1] for w in words)
    assert all(0.0 <= w.confidence <= 1.0 for w in words)
    # words in one line keep their order left to right
    line = next(ln for b in blocks for ln in b.lines if "300" in ln.text)
    xs = [w.bbox[0] for w in line.words]
    assert xs == sorted(xs)


def test_group_lines_joins_close_lines_into_one_block():
    def w(text, x0, y0, x1, y1):
        return OCRWord(text=text, confidence=0.9, bbox=(x0, y0, x1, y1))

    lines = [
        ((10, 10, 200, 30), [w("first", 10, 10, 60, 30), w("line", 70, 10, 120, 30)]),
        ((10, 34, 200, 54), [w("second", 10, 34, 80, 54)]),
        ((10, 200, 200, 220), [w("far", 10, 200, 40, 220)]),
    ]
    blocks = group_lines(lines)
    assert [b.text for b in blocks] == ["first line\nsecond", "far"]


def _reading(engine: str, texts: list[str], conf: float) -> E.OCRReading:
    words = [OCRWord(text=t, confidence=conf, bbox=(i * 10.0, 0.0, i * 10.0 + 8, 10.0)) for i, t in enumerate(texts)]
    return E.OCRReading(engine=engine, blocks=[OCRBlock(lines=[OCRLine(words=words)])])


def test_rank_keeps_the_preferred_reader_unless_it_is_clearly_worse():
    rapid = _reading("rapidocr", ["300", "A", "fuse"], 0.9)
    tess = _reading("tesseract", ["300", "A", "fuse"], 0.95)
    assert E._rank([rapid, tess])[0].engine == "rapidocr"  # small confidence gaps do not flip the choice
    sparse = _reading("rapidocr", ["300"], 0.99)
    assert E._rank([sparse, tess])[0].engine == "tesseract"  # it saw far less text
    unsure = _reading("rapidocr", ["300", "A", "fuse"], 0.5)
    assert E._rank([unsure, tess])[0].engine == "tesseract"  # it is far less sure


def test_tesseract_second_pass_runs_only_when_the_first_is_weak(monkeypatch):
    import pytesseract

    calls: list[str] = []

    def fake_image_to_data(img, lang, config, output_type):
        calls.append(config)
        conf = 40 if len(calls) == 1 else 90
        return {"text": ["300", "A"], "conf": [conf, conf], "left": [0, 20], "top": [0, 0], "width": [15, 10], "height": [10, 10],
                "block_num": [1, 1], "par_num": [1, 1], "line_num": [1, 1]}

    monkeypatch.setattr(pytesseract, "image_to_data", fake_image_to_data)
    monkeypatch.setattr(pytesseract, "Output", type("O", (), {"DICT": "dict"}))
    eng = TesseractEngine()
    blocks = eng.recognize(Image.new("RGB", (200, 50), "white"))
    assert len(calls) == 2, "a weak first pass triggers the binarised second pass"
    assert abs(blocks[0].confidence - 0.9) < 1e-6, "the better pass is kept"

    calls.clear()

    def strong(img, lang, config, output_type):
        calls.append(config)
        return {"text": ["300"], "conf": [95], "left": [0], "top": [0], "width": [15], "height": [10], "block_num": [1], "par_num": [1], "line_num": [1]}

    monkeypatch.setattr(pytesseract, "image_to_data", strong)
    eng.recognize(Image.new("RGB", (200, 50), "white"))
    assert len(calls) == 1, "a confident first pass is not repeated"


def test_engine_status_lists_the_readers():
    status = E.engine_status()
    assert set(status) >= {"configured", "tesseract", "rapidocr", "readers"}
    assert status["readers"] == [e.name for e in E.get_ocr_engines()]
