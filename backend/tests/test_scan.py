"""Photographing a document with the phone camera."""
from __future__ import annotations

from pathlib import Path

import pytest

from tests.fixtures import build_photo_image


@pytest.fixture(scope="module")
def photos(fixtures_dir: Path) -> list[Path]:
    manual = fixtures_dir / "XYZ-5000 Installation Manual.pdf"
    return [build_photo_image(manual, fixtures_dir / f"camera-{n}.jpg", page_index=n) for n in (1, 2)]


def test_two_photos_become_one_document(client, photos):
    files = [("pages", (p.name, p.read_bytes(), "image/jpeg")) for p in photos]
    resp = client.post("/api/documents/scan", files=files, data={"name": "Camera test"})
    assert resp.status_code == 201, resp.text
    summary = resp.json()
    assert summary["filename"] == "Camera test.pdf"

    doc = client.get(f"/api/documents/{summary['id']}").json()
    assert doc["status"] == "ready", doc.get("error")
    assert len(doc["pages"]) == 2
    # Photographs carry no text layer: this went through OCR like any other scan.
    assert all(p["text_source"] == "ocr" for p in doc["pages"])
    assert client.get(f"/api/documents/{summary['id']}/entities").json()


def test_the_name_is_optional(client, photos):
    files = [("pages", (photos[0].name, photos[0].read_bytes(), "image/jpeg"))]
    resp = client.post("/api/documents/scan", files=files)
    assert resp.status_code == 201, resp.text
    assert resp.json()["filename"].startswith("Scan ")


def test_anything_that_is_not_a_photo_is_refused(client, fixtures_dir):
    pdf = fixtures_dir / "XYZ-5000 Installation Manual.pdf"
    files = [("pages", (pdf.name, pdf.read_bytes(), "application/pdf"))]
    resp = client.post("/api/documents/scan", files=files)
    assert resp.status_code == 415
    assert "camera" in resp.json()["detail"].lower()
