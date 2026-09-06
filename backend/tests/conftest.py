from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def data_dir(tmp_path_factory) -> Path:
    d = tmp_path_factory.mktemp("mdi-data")
    os.environ["MDI_DATA_DIR"] = str(d)
    os.environ["MDI_AI_ENABLED"] = "false"
    os.environ["MDI_BACKGROUND_PROCESSING"] = "false"
    os.environ["MDI_INBOX_WATCHER"] = "false"
    from app.config import get_settings
    from app.db import reset_engine

    get_settings.cache_clear()
    reset_engine()
    get_settings()
    return d


@pytest.fixture(scope="session")
def fixtures_dir(data_dir: Path) -> Path:
    from tests.fixtures import build_invoice_pdf, build_manual_pdf, build_photo_image, build_scanned_pdf

    d = data_dir / "fixtures"
    d.mkdir()
    manual = build_manual_pdf(d / "XYZ-5000 Installation Manual.pdf")
    build_scanned_pdf(manual, d / "XYZ-5000 Manual (scanned).pdf")
    build_invoice_pdf(d / "Harbor Marine Invoice.pdf")
    build_photo_image(manual, d / "battery-page-photo.jpg")
    return d


@pytest.fixture(scope="session")
def client(data_dir: Path):
    from fastapi.testclient import TestClient

    from app.main import create_app

    app = create_app()
    with TestClient(app) as c:
        yield c


def _ingest(client, path: Path) -> dict:
    """Upload; with MDI_BACKGROUND_PROCESSING=false the pipeline runs inside the request."""
    with path.open("rb") as f:
        resp = client.post("/api/documents", files=[("files", (path.name, f, "application/octet-stream"))])
    assert resp.status_code == 201, resp.text
    doc = resp.json()[0]
    return client.get(f"/api/documents/{doc['id']}").json()


@pytest.fixture(scope="session")
def manual_doc(client, fixtures_dir) -> dict:
    return _ingest(client, fixtures_dir / "XYZ-5000 Installation Manual.pdf")


@pytest.fixture(scope="session")
def scanned_doc(client, fixtures_dir) -> dict:
    return _ingest(client, fixtures_dir / "XYZ-5000 Manual (scanned).pdf")


@pytest.fixture(scope="session")
def invoice_doc(client, fixtures_dir) -> dict:
    return _ingest(client, fixtures_dir / "Harbor Marine Invoice.pdf")


@pytest.fixture(scope="session")
def photo_doc(client, fixtures_dir) -> dict:
    return _ingest(client, fixtures_dir / "battery-page-photo.jpg")
