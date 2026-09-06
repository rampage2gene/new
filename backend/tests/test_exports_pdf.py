"""Searchable PDFs, report PDFs, text exports and stateless conversions."""
from __future__ import annotations

import io
import json
import re
import zipfile

import pymupdf


def _text(pdf_bytes: bytes) -> str:
    doc = pymupdf.open("pdf", pdf_bytes)
    flags = pymupdf.TEXTFLAGS_TEXT & ~pymupdf.TEXT_PRESERVE_LIGATURES  # "fi" ligatures -> plain letters
    return re.sub(r"\s+", " ", "\n".join(p.get_text(flags=flags) for p in doc))


def test_searchable_pdf_adds_text_layer(client, scanned_doc):
    r = client.get(f"/api/documents/{scanned_doc['id']}/export/searchable-pdf")
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    doc = pymupdf.open("pdf", r.content)
    assert doc.page_count == scanned_doc["page_count"]
    hits = [(i, p.search_for("300 A")) for i, p in enumerate(doc, start=1)]
    assert any(h for _, h in hits), "the OCR'd fuse rating should be findable in the PDF"
    # the layer is invisible: page 1 still renders as the scan (dark text on light background), not doubled text
    assert "Installation" in _text(r.content)


def test_searchable_pdf_for_photo(client, photo_doc):
    r = client.get(f"/api/documents/{photo_doc['id']}/export/searchable-pdf")
    assert r.status_code == 200
    doc = pymupdf.open("pdf", r.content)
    assert doc.page_count == 1 and "battery" in doc[0].get_text().lower()


def test_report_pdf_for_document(client, manual_doc):
    r = client.get(f"/api/documents/{manual_doc['id']}/export/report.pdf")
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    t = _text(r.content)
    assert manual_doc["title"] in t
    assert "Electrical specification extraction" in t and "Fuse ratings" in t and "Verification" in t
    assert "page 1 of" in t


def test_combined_report_with_calculation_and_answer(client, manual_doc):
    calc = client.post("/api/calculators/fuse_protection/run", json={"inputs": {"device_type": "inverter", "continuous_current": 125, "conductor_size": "4/0 AWG", "manufacturer_fuse": {"value": 300, "unit": "A", "source": {"document_id": manual_doc["id"], "document_name": manual_doc["title"], "page": 3}}}}).json()
    answer = client.post("/api/ask", json={"question": "What fuse is required for the DC input?", "document_ids": [manual_doc["id"]]}).json()
    r = client.post("/api/export/report.pdf", json={"document_ids": [manual_doc["id"]], "sections": ["spec_extraction"], "calculations": [calc], "answer": {**answer, "question": "What fuse is required?"}, "title": "Installation review"})
    assert r.status_code == 200
    t = _text(r.content)
    assert "Installation review" in t and "Fuse & Circuit Protection" in t
    assert "MANUFACTURER REQUIRED" in t and "CALCULATED ESTIMATE" in t
    assert "Question and answer" in t and "Sources" in t
    # nothing to report is an error, not an empty file
    assert client.post("/api/export/report.pdf", json={}).status_code == 422


def test_document_text_markdown_json(client, manual_doc):
    r = client.get(f"/api/documents/{manual_doc['id']}/export/txt")
    assert r.status_code == 200 and r.text.startswith("===== Page 1 =====")
    r = client.get(f"/api/documents/{manual_doc['id']}/export/md")
    assert r.status_code == 200 and r.text.startswith("# ") and "\n## " in r.text or "\n# " in r.text
    assert "|---|" in r.text  # the specification table survives as a pipe table
    r = client.get(f"/api/documents/{manual_doc['id']}/export/json")
    body = r.json()
    assert body["id"] == manual_doc["id"] and len(body["pages"]) == manual_doc["page_count"] and body["pages"][0]["blocks"]
    assert client.get(f"/api/documents/{manual_doc['id']}/export/docx").status_code == 404


def test_convert_pdf_to_markdown_and_images(client, fixtures_dir):
    path = fixtures_dir / "XYZ-5000 Manual (scanned).pdf"
    with path.open("rb") as f:
        r = client.post("/api/convert", files=[("files", (path.name, f, "application/pdf"))], data={"to": "md"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/markdown")
    assert "300 A" in r.text  # scanned pages are OCR'd during conversion
    with path.open("rb") as f:
        r = client.post("/api/convert", files=[("files", (path.name, f, "application/pdf"))], data={"to": "png", "dpi": "50"})
    names = zipfile.ZipFile(io.BytesIO(r.content)).namelist()
    assert names == [f"page-{i:04d}.png" for i in range(1, 5)]
    with path.open("rb") as f:
        r = client.post("/api/convert", files=[("files", (path.name, f, "application/pdf"))], data={"to": "json", "ocr": "false"})
    body = json.loads(r.content)
    assert len(body["pages"]) == 4 and "structure" in body


def test_convert_image_to_pdf_merge_and_split(client, fixtures_dir):
    photo = fixtures_dir / "battery-page-photo.jpg"
    manual = fixtures_dir / "XYZ-5000 Installation Manual.pdf"
    with photo.open("rb") as f:
        r = client.post("/api/convert", files=[("files", (photo.name, f, "image/jpeg"))], data={"to": "pdf"})
    assert r.status_code == 200 and pymupdf.open("pdf", r.content).page_count == 1
    with manual.open("rb") as a, photo.open("rb") as b:
        r = client.post("/api/convert/merge", files=[("files", ("a.pdf", a, "application/pdf")), ("files", ("b.jpg", b, "image/jpeg"))])
    assert r.status_code == 200 and pymupdf.open("pdf", r.content).page_count == 5
    with manual.open("rb") as a:
        r = client.post("/api/convert/split", files=[("file", ("manual.pdf", a, "application/pdf"))], data={"ranges": "1-2, 4-"})
    assert r.status_code == 200
    assert zipfile.ZipFile(io.BytesIO(r.content)).namelist() == ["manual_p1-2.pdf", "manual_p4.pdf"]
    with manual.open("rb") as a:
        r = client.post("/api/convert/split", files=[("file", ("manual.pdf", a, "application/pdf"))], data={"ranges": "9-12"})
    assert r.status_code == 422
    with manual.open("rb") as a:
        r = client.post("/api/convert/merge", files=[("files", ("a.pdf", a, "application/pdf"))])
    assert r.status_code == 422
