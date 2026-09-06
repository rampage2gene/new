"""Two ways in that never touch the browser upload: import by path, and the inbox folder."""
from __future__ import annotations

import shutil
from pathlib import Path

import pymupdf

from app.ingest import inbox


def test_import_by_path_processes_the_document(client, fixtures_dir: Path):
    src = fixtures_dir / "XYZ-5000 Installation Manual.pdf"
    resp = client.post("/api/documents/import", json={"paths": [str(src)]})
    assert resp.status_code == 201, resp.text
    doc = resp.json()[0]
    assert doc["filename"] == src.name
    detail = client.get(f"/api/documents/{doc['id']}").json()
    assert detail["status"] == "ready", detail.get("error")
    assert src.exists(), "importing must not move or delete the user's file"


def test_import_rejects_a_missing_path(client, tmp_path: Path):
    missing = tmp_path / "nowhere.pdf"
    resp = client.post("/api/documents/import", json={"paths": [str(missing)]})
    assert resp.status_code == 400
    assert str(missing) in resp.json()["detail"]


def test_import_rejects_a_non_document(client, tmp_path: Path):
    junk = tmp_path / "notes.txt"
    junk.write_text("not a document", encoding="utf-8")
    resp = client.post("/api/documents/import", json={"paths": [str(junk)]})
    assert resp.status_code == 415


def test_inbox_turns_a_scan_into_an_ocr_pdf(client, fixtures_dir: Path):
    """Copy a scanned PDF in; get `<name>.ocr.pdf` with a text layer out."""
    d = inbox.ensure_inbox()
    dropped = d / "dropped-scan.pdf"
    shutil.copyfile(fixtures_dir / "XYZ-5000 Manual (scanned).pdf", dropped)

    inbox.scan_once()  # first sight: size recorded, not taken yet (could still be copying)
    assert dropped.exists() and not list((d / "done").glob("dropped-scan*"))

    inbox.scan_once()  # size unchanged: ingested; processing is inline in tests, so it is ready
    inbox.scan_once()  # ready: written out and moved
    out = d / "done" / "dropped-scan.ocr.pdf"
    assert out.exists(), sorted(p.name for p in d.rglob("*"))
    assert (d / "done" / "dropped-scan.pdf").exists()
    assert not dropped.exists()

    with pymupdf.open(out) as pdf:
        assert pdf.page_count >= 1
        text = pdf[0].get_text()
    assert "XYZ-5000" in text or "Installation" in text, text[:200]


def test_inbox_moves_junk_to_failed(client):
    d = inbox.ensure_inbox()
    junk = d / "not-a-document.pdf"
    junk.write_text("this is not a pdf at all", encoding="utf-8")
    inbox.scan_once()  # size recorded
    inbox.scan_once()  # taken; inline processing fails on the bogus bytes
    inbox.scan_once()  # failure noticed: moved aside with a note
    assert not junk.exists()
    failed = d / "failed" / "not-a-document.pdf"
    assert failed.exists()
    note = d / "failed" / "not-a-document.pdf.error.txt"
    assert note.exists() and note.read_text(encoding="utf-8").strip(), "the note must say why"


def test_inbox_waits_for_a_file_still_being_copied(client):
    d = inbox.ensure_inbox()
    growing = d / "growing.pdf"
    growing.write_bytes(b"%PDF-1.4 partial")
    inbox.scan_once()
    growing.write_bytes(b"%PDF-1.4 partial and some more bytes")  # size changed
    inbox.scan_once()
    assert growing.exists(), "a file whose size is still changing must be left alone"
    growing.unlink()
    inbox.scan_once()
