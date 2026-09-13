"""When a reader stops on a page, the document still finishes and says which values rest on one reading."""
from __future__ import annotations

import shutil

import pytest

from app.config import get_settings
from app.db import session_scope
from app.models import Page
from app.ocr.base import ReaderStopped
from app.ocr.rapid import RapidEngine
from tests.conftest import _ingest


@pytest.fixture()
def scanned(fixtures_dir, tmp_path):
    if not RapidEngine().available():
        pytest.skip("rapidocr is not installed in this environment")
    src = fixtures_dir / "XYZ-5000 Manual (scanned).pdf"
    return shutil.copy(src, tmp_path / "XYZ-5000 Manual (reader stops).pdf")


def _flags(client, doc_id):
    return [f for f in client.get(f"/api/documents/{doc_id}/qc").json() if f["flag_type"] == "reader_stopped"]


def _engines(doc_id) -> dict[int, tuple[str | None, str | None]]:
    with session_scope() as s:
        rows = s.query(Page).filter(Page.document_id == doc_id).order_by(Page.page_number).all()
        return {p.page_number: (p.ocr_engine, p.alt_ocr_engine) for p in rows}


def test_a_page_whose_reader_stopped_still_makes_a_ready_document(client, scanned, monkeypatch):
    original = RapidEngine.recognize
    calls = {"n": 0}

    def flaky(self, image):
        calls["n"] += 1
        if calls["n"] == 1:
            raise ReaderStopped("the RapidOCR reader stopped while reading the page (exit code -11)")
        return original(self, image)

    monkeypatch.setattr(RapidEngine, "recognize", flaky)
    doc = _ingest(client, scanned)
    assert doc["status"] == "ready"
    assert doc["stats"]["ocr_engines"] == ["rapidocr", "tesseract"]
    flags = _flags(client, doc["id"])
    assert len(flags) == 1 and flags[0]["page"] == 1
    assert "only Tesseract read it" in flags[0]["message"]
    engines = _engines(doc["id"])
    assert engines[1] == ("tesseract", None)  # one reading, honestly recorded
    assert engines[2][0] == "rapidocr" and engines[2][1] == "tesseract"


def test_after_the_budget_the_reader_sits_out_the_rest_of_the_document(client, scanned, monkeypatch):
    calls = {"n": 0}

    def always(self, image):
        calls["n"] += 1
        raise ReaderStopped("the RapidOCR reader stopped while reading the page (exit code -11)")

    monkeypatch.setattr(RapidEngine, "recognize", always)
    budget = get_settings().ocr_max_stops_per_document
    doc = _ingest(client, scanned)
    assert doc["status"] == "ready"
    assert doc["stats"]["ocr_engines"] == ["tesseract"]
    assert calls["n"] == budget  # not restarted for every page of the document
    flags = _flags(client, doc["id"])
    per_page = [f for f in flags if "sits" not in f["message"] and "times in this document" not in f["message"]]
    summary = [f for f in flags if "times in this document" in f["message"]]
    assert [f["page"] for f in per_page] == list(range(1, budget + 1))
    assert len(summary) == 1 and summary[0]["page"] == budget + 1
    assert summary[0]["details"]["pages"] == list(range(budget + 1, doc["page_count"] + 1))
