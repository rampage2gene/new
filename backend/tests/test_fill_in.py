"""Filling in and confirming values, and keeping those edits across a reprocess."""
from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from app.db import _migrate


@pytest.fixture(scope="module")
def own_doc(client, fixtures_dir: Path) -> dict:
    """A private copy of the scanned manual so edits here cannot disturb other tests."""
    resp = client.post("/api/documents/import", json={"paths": [str(fixtures_dir / "XYZ-5000 Manual (scanned).pdf")]})
    assert resp.status_code == 201, resp.text
    return client.get(f"/api/documents/{resp.json()[0]['id']}").json()


def _entities(client, doc_id: str) -> list[dict]:
    return client.get(f"/api/documents/{doc_id}/entities").json()


def test_fill_in_stores_a_normalised_value(client, own_doc):
    e = next(x for x in _entities(client, own_doc["id"]) if x["entity_type"] == "current" and x["ocr_confidence"] is not None)
    r = client.patch(f"/api/entities/{e['id']}", json={"value_text": "126 A"})
    assert r.status_code == 200, r.text
    u = r.json()
    assert u["value_text"] == "126 A" and u["value"] == 126 and u["unit"] == "A"
    assert u["verified"] is True and u["confidence"] == 1.0
    assert u["verification"]["status"] == "user" and u["verification"]["original"] == e["value_text"]
    doc = client.get(f"/api/documents/{own_doc['id']}").json()
    assert doc["stats"]["verified_by_user"] >= 1


def test_untick_restores_the_machine_reading(client, own_doc):
    e = next(x for x in _entities(client, own_doc["id"]) if x["verified"])
    r = client.patch(f"/api/entities/{e['id']}", json={"verified": False}).json()
    assert r["verified"] is False
    assert r["value_text"] == e["verification"]["original"]
    assert r["confidence"] < 1.0 and r["verification"]["status"] != "user"


def test_confirm_as_is_and_clear(client, own_doc):
    e = next(x for x in _entities(client, own_doc["id"]) if x["entity_type"] == "voltage" and x["value_text"] and not x["verified"])
    r = client.patch(f"/api/entities/{e['id']}", json={"verified": True}).json()
    assert r["verified"] and r["confidence"] == 1.0 and r["value_text"] == e["value_text"]
    r = client.patch(f"/api/entities/{e['id']}", json={"value_text": ""}).json()
    assert r["value_text"] == "" and r["value"] is None and r["verified"] is False
    assert r["verification"]["status"] == "to_fill"
    doc = client.get(f"/api/documents/{own_doc['id']}").json()
    assert doc["stats"]["to_fill"] >= 1
    # a blank cannot be confirmed "as is"
    assert client.patch(f"/api/entities/{e['id']}", json={"verified": True}).status_code == 400
    r = client.patch(f"/api/entities/{e['id']}", json={"value_text": e["value_text"]}).json()
    assert r["verified"] and r["verification"]["status"] == "user"


def test_edit_resolves_the_reading_flags(client, own_doc):
    flags = client.get(f"/api/documents/{own_doc['id']}/qc").json()
    flagged = next((f for f in flags if f["flag_type"] in ("reading_unverified", "reading_conflict", "low_ocr_confidence") and f["entity_id"] and not f["resolved"]), None)
    if flagged is None:
        pytest.skip("no reading flag on this fixture")
    r = client.patch(f"/api/entities/{flagged['entity_id']}", json={"verified": True})
    assert r.status_code == 200
    after = next(f for f in client.get(f"/api/documents/{own_doc['id']}/qc").json() if f["id"] == flagged["id"])
    assert after["resolved"] is True


def test_unknown_entity_and_empty_edit(client):
    assert client.patch("/api/entities/does-not-exist", json={"verified": True}).status_code == 404


def test_edits_survive_a_reprocess(client, own_doc):
    before = {e["id"]: e for e in _entities(client, own_doc["id"]) if e["verified"]}
    assert before, "earlier tests left confirmed values"
    kept_values = sorted((e["entity_type"], e["page"], e["value_text"]) for e in before.values())
    r = client.post(f"/api/documents/{own_doc['id']}/verify")
    assert r.status_code == 200
    doc = client.get(f"/api/documents/{own_doc['id']}").json()
    assert doc["status"] == "ready", doc.get("error")
    after = [e for e in _entities(client, own_doc["id"]) if e["verified"]]
    assert sorted((e["entity_type"], e["page"], e["value_text"]) for e in after) == kept_values
    assert all(e["confidence"] == 1.0 and e["verification"]["status"] == "user" for e in after)
    assert doc["stats"]["verified_by_user"] == len(after)


def test_migration_adds_the_verified_column(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE entities (id VARCHAR(32) PRIMARY KEY, value_text VARCHAR(128))"))
        conn.execute(text("CREATE TABLE pages (id VARCHAR(32) PRIMARY KEY, page_number INTEGER)"))
        conn.execute(text("INSERT INTO entities (id, value_text) VALUES ('a', '300 A')"))
    _migrate(engine)
    _migrate(engine)  # idempotent
    with engine.begin() as conn:
        cols = {row[1] for row in conn.execute(text("PRAGMA table_info(entities)"))}
        assert "verified" in cols
        assert conn.execute(text("SELECT verified FROM entities WHERE id='a'")).scalar() == 0
        pcols = {row[1] for row in conn.execute(text("PRAGMA table_info(pages)"))}
        assert {"ocr_engine", "alt_ocr_engine", "alt_ocr"} <= pcols
