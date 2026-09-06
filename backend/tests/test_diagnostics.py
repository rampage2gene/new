"""Diagnostics endpoints: the evidence trail behind the app's Diagnostics page."""
from __future__ import annotations

import logging
from pathlib import Path


def test_status_reports_the_upload_limit(client):
    """The UI pre-checks file sizes against this instead of uploading 200 MB to find out."""
    body = client.get("/api/status").json()
    assert isinstance(body["max_upload_mb"], int) and body["max_upload_mb"] > 0


def test_diagnostics_describes_the_installation(client, data_dir: Path):
    body = client.get("/api/diagnostics").json()
    assert body["version"]
    assert body["data_dir"] == str(data_dir)
    assert body["log_path"] == str(data_dir / "logs" / "app.log")
    assert body["ocr_engine"] in ("rapidocr", "tesseract", "none")
    assert set(body["ocr_engines"]) >= {"tesseract", "rapidocr", "readers"}
    assert set(body["documents"]) == {"total", "ready", "failed"}
    assert body["max_upload_mb"] > 0


def test_logs_404_when_there_is_no_log_file(client, data_dir: Path):
    log = data_dir / "logs" / "app.log"
    if log.exists():
        log.unlink()
    resp = client.get("/api/logs")
    assert resp.status_code == 404
    assert str(log) in resp.json()["detail"]


def test_logs_returns_the_tail(client, data_dir: Path):
    log = data_dir / "logs" / "app.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text("".join(f"line {i}\n" for i in range(50)), encoding="utf-8")
    try:
        body = client.get("/api/logs?tail=3").text
        assert body == "line 47\nline 48\nline 49\n"
        assert client.get("/api/diagnostics").json()["log_exists"] is True
    finally:
        log.unlink()


def test_upload_is_logged(client, fixtures_dir: Path, caplog):
    """A failed upload in the desktop app is diagnosed by whether a line lands here:
    nothing means the browser never sent the file."""
    path = fixtures_dir / "XYZ-5000 Installation Manual.pdf"
    with caplog.at_level(logging.INFO, logger="app.api.documents"):
        with path.open("rb") as f:
            resp = client.post("/api/documents", files=[("files", (path.name, f, "application/pdf"))])
    assert resp.status_code == 201, resp.text
    messages = " ".join(r.getMessage() for r in caplog.records)
    assert path.name in messages
    assert "queued" in messages


def test_unsupported_upload_is_logged_and_rejected(client, tmp_path, caplog):
    junk = tmp_path / "notes.txt"
    junk.write_text("this is not a document the app can read", encoding="utf-8")
    with caplog.at_level(logging.WARNING, logger="app.api.documents"):
        with junk.open("rb") as f:
            resp = client.post("/api/documents", files=[("files", (junk.name, f, "text/plain"))])
    assert resp.status_code == 415
    assert "notes.txt" in " ".join(r.getMessage() for r in caplog.records)
