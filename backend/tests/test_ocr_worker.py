"""The RapidOCR reader runs in its own process; a crash there costs one page, not the app."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.config import get_settings
from app.ocr import rapid
from app.ocr import worker as W
from app.ocr.base import ReaderStopped
from app.ocr.rapid import RapidEngine
from tests.test_ocr_engine import _page_image

BACKEND = Path(__file__).resolve().parents[1]


@pytest.fixture()
def page(fixtures_dir):
    if not RapidEngine().available():
        pytest.skip("rapidocr is not installed in this environment")
    return _page_image(fixtures_dir / "XYZ-5000 Manual (scanned).pdf")


def _text(blocks) -> str:
    return " ".join(w.text for b in blocks for w in b.words)


def test_the_reader_runs_outside_the_server_process(page):
    blocks = RapidEngine().recognize(page)
    assert "300 A" in _text(blocks)
    status = W.get_worker().status()
    assert status["ready"] and status["pid"] not in (None, os.getpid())
    assert Path(status["log"]).exists()


def test_a_reader_that_dies_mid_page_is_reported_and_comes_back(page):
    w = W.get_worker()
    w.stop()
    w._crash_armed = True  # the next worker started dies on its first page, the way native code dies
    with pytest.raises(ReaderStopped, match="stopped while reading"):
        RapidEngine().recognize(page)
    first_stops = w.stops
    blocks = RapidEngine().recognize(page)  # started again, silently
    assert "300 A" in _text(blocks)
    assert w.stops == first_stops and w.status()["pid"] not in (None, os.getpid())


def test_a_reader_that_hangs_is_killed_at_the_deadline(page, monkeypatch):
    monkeypatch.setattr(get_settings(), "ocr_page_timeout", 0.01)
    with pytest.raises(ReaderStopped, match="did not answer"):
        RapidEngine().recognize(page)
    monkeypatch.setattr(get_settings(), "ocr_page_timeout", 180.0)
    assert "300 A" in _text(RapidEngine().recognize(page))


def test_the_in_process_path_still_works(page, monkeypatch):
    monkeypatch.setattr(get_settings(), "ocr_isolate", False)
    assert "300 A" in _text(RapidEngine().recognize(page))
    assert rapid.load() is not None  # the models were loaded in this process


def test_the_worker_imports_nothing_that_starts_the_app():
    code = (
        "import sys, app.ocr.worker, app.ocr.rapid; "
        "bad = [m for m in ('app.main', 'app.db', 'app.ingest.inbox', 'rapidocr', 'onnxruntime') if m in sys.modules]; "
        "assert not bad, bad"
    )
    subprocess.run([sys.executable, "-c", code], cwd=BACKEND, check=True)
