"""The verification ladder: two readers, a third read, blanks instead of guesses."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.extraction import verify as V
from app.extraction.entities import extract_entities
from app.ingest.types import RawBlock, RawPage


def _page(text: str, alt_lines: list[str], y: float = 100.0) -> RawPage:
    """One OCR'd page with one block and the second reader's lines on the same spot."""
    words = []
    x = 50.0
    for tok in text.split():
        words.append({"t": tok, "c": 0.8, "bbox": [x, y, x + 8 * len(tok), y + 12]})
        x += 8 * len(tok) + 6
    page = RawPage(page_number=1, width=600.0, height=800.0, text_source="ocr", ocr_confidence=0.8, ocr_engine="rapidocr")
    page.blocks = [RawBlock(text=text, bbox=(50.0, y, x, y + 12), source="ocr", confidence=0.8, words=words)]
    page.alt_ocr_engine = "tesseract"
    page.alt_ocr = [{"t": ln, "c": 0.8, "bbox": [50.0, y, x, y + 12]} for ln in alt_lines]
    return page


def _run(monkeypatch, text: str, alt_lines: list[str], reread: str | None):
    monkeypatch.setattr(V.TieBreaker, "read", lambda self, page, ent: reread)
    monkeypatch.setattr(V.TieBreaker, "__init__", lambda self, *a, **k: setattr(self, "available", True))
    page = _page(text, alt_lines)
    ents = extract_entities([page])
    report, flags = V.verify_entities([page], ents)
    return ents, report, flags


def test_two_readers_agreeing_is_100_percent(monkeypatch):
    ents, report, flags = _run(monkeypatch, "Install a 300 A Class T fuse.", ["Install a 300 A Class T fuse."], None)
    fuse = next(e for e in ents if e.entity_type == "fuse")
    assert fuse.confidence == 1.0 and fuse.extra["verification"]["status"] == "confirmed"
    assert fuse.extra["verification"]["note"] == "2 readers"
    assert report.confirmed >= 1 and report.to_fill == 0
    assert not [f for f in flags if f.flag_type == "reading_conflict"]


def test_third_read_settles_a_disagreement_for_reader_one(monkeypatch):
    ents, report, _ = _run(monkeypatch, "Install a 300 A Class T fuse.", ["Install a 800 A Class T fuse."], "Install a 300 A Class T fuse.")
    fuse = next(e for e in ents if e.entity_type == "fuse")
    assert fuse.value_text == "300 A" and fuse.confidence == 0.95
    assert fuse.extra["verification"]["status"] == "confirmed" and fuse.extra["verification"]["note"] == "majority of 3"


def test_third_read_corrects_reader_one_when_the_other_two_agree(monkeypatch):
    ents, report, flags = _run(monkeypatch, "Install a 800 A Class T fuse.", ["Install a 300 A Class T fuse."], "Install a 300 A Class T fuse.")
    fuse = next(e for e in ents if e.entity_type == "fuse")
    assert fuse.value_text == "300 A" and fuse.value == 300 and fuse.confidence == 0.95
    v = fuse.extra["verification"]
    assert v["status"] == "corrected" and v["original"] == "800 A"
    assert report.corrected == 1
    assert any(f.flag_type == "reading_corrected" and "800 A" in f.message for f in flags)


def test_no_majority_leaves_the_value_blank(monkeypatch):
    ents, report, flags = _run(monkeypatch, "Install a 300 A Class T fuse.", ["Install a 800 A Class T fuse."], "Install a 900 A Class T fuse.")
    fuse = next(e for e in ents if e.entity_type == "fuse")
    assert fuse.value is None and fuse.value_text == "" and fuse.confidence == 0.0
    v = fuse.extra["verification"]
    assert v["status"] == "to_fill" and v["original"] == "300 A"
    assert set(v["readings"].values()) >= {"300 A", "800 A", "900 A"}
    assert report.to_fill == 1
    conflict = next(f for f in flags if f.flag_type == "reading_conflict")
    assert conflict.severity == "critical" and "blank" in conflict.message.lower()


def test_nobody_else_could_read_it_is_not_a_conflict(monkeypatch):
    ents, report, flags = _run(monkeypatch, "Install a 300 A Class T fuse.", ["(unreadable smudge)"], None)
    fuse = next(e for e in ents if e.entity_type == "fuse")
    assert fuse.value_text == "300 A" and fuse.extra["verification"]["status"] == "unverified"
    assert fuse.confidence <= 0.85, "a single reading never claims more than the OCR ceiling"
    assert report.unverified >= 1 and report.to_fill == 0
    assert any(f.flag_type == "reading_unverified" for f in flags)


def test_another_value_on_the_same_line_is_not_a_reading_of_this_one(monkeypatch):
    # Reader 2 saw only the AWG size on the line; it must not "correct" the mm² value to it.
    ents, report, _ = _run(monkeypatch, "Cable: 10 AWG (6 mm²)", ["Cable: 10 AWG (6 mm2)"], "Cable: 10 AWG (6 mm2)")
    mm2 = next(e for e in ents if e.entity_type == "wire_size" and e.unit == "mm²")
    assert mm2.value_text == "6 mm²", "not replaced by the neighbouring value"
    assert mm2.extra["verification"]["status"] in ("unverified", "confirmed")
    assert report.corrected == 0


def test_embedded_text_is_left_alone(monkeypatch):
    page = _page("Install a 300 A Class T fuse.", [])
    page.text_source = "embedded"
    page.ocr_confidence = None
    for b in page.blocks:
        b.source = "embedded"
    ents = extract_entities([page])
    report, flags = V.verify_entities([page], ents)
    assert report.checked == 0 and not flags
    assert all("verification" not in e.extra for e in ents)


def test_ai_check_can_settle_a_blank(monkeypatch):
    from app.ai import client as ai

    monkeypatch.setattr(ai, "ai_available", lambda: True)

    def fake_structured_call(system, content, schema, max_tokens=None):
        assert "never guess" in system.lower()
        return schema(verdicts=[{"index": 0, "legible": True, "value_text": "300 A"}, {"index": 1, "legible": False}])

    monkeypatch.setattr(ai, "structured_call", fake_structured_call)
    monkeypatch.setattr(V.TieBreaker, "read", lambda self, page, ent: "Install a 900 A Class T fuse.")
    monkeypatch.setattr(V.TieBreaker, "__init__", lambda self, *a, **k: setattr(self, "available", True))
    page = _page("Install a 300 A Class T fuse.", ["Install a 800 A Class T fuse."])
    page.image_path = str(Path(__file__))  # any readable file; the fake never looks at the bytes
    ents = extract_entities([page])
    fuse_idx = next(i for i, e in enumerate(ents) if e.entity_type == "fuse")
    assert fuse_idx == 0
    report, flags = V.verify_entities([page], ents)
    fuse = ents[fuse_idx]
    assert fuse.value_text == "300 A" and fuse.confidence == 1.0
    assert fuse.extra["verification"]["status"] == "ai_confirmed"
    assert report.to_fill == 0 and report.ai.startswith("settled 1")
    assert not [f for f in flags if f.flag_type == "reading_conflict"]


def test_no_api_key_means_no_ai_and_no_network(monkeypatch):
    ents, report, _ = _run(monkeypatch, "Install a 300 A Class T fuse.", ["Install a 800 A Class T fuse."], "Install a 900 A Class T fuse.")
    assert report.ai in ("skipped: no API key", "off")


def test_scanned_document_reports_its_readers(scanned_doc, client):
    """Integration: the real pipeline ran both engines and the ladder on every OCR'd value."""
    v = scanned_doc["stats"]["verification"]
    assert v["reader1"] and v["reader2"] and v["reader1"] != v["reader2"]
    assert v["checked"] > 10 and v["confirmed"] >= v["checked"] // 2
    ents = client.get(f"/api/documents/{scanned_doc['id']}/entities").json()
    ocr_ents = [e for e in ents if e["ocr_confidence"] is not None]
    assert ocr_ents and all(e["verification"]["status"] for e in ocr_ents)
    assert any(e["confidence"] == 1.0 and e["verification"]["status"] == "confirmed" for e in ocr_ents)
    assert "rapidocr" in scanned_doc["stats"]["ocr_engines"] or "tesseract" in scanned_doc["stats"]["ocr_engines"]
