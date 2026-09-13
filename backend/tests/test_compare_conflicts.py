"""Conflict detection with two synthetic documents (inverter vs battery)."""
from __future__ import annotations

from pathlib import Path

import pymupdf

from tests.conftest import _ingest


def _pdf(path: Path, title: str, lines: list[str]) -> Path:
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((50, 60), title, fontsize=20, fontname="hebo")
    y = 100
    for ln in lines:
        page.insert_text((50, y), ln, fontsize=10)
        y += 18
    doc.save(path)
    doc.close()
    return path


def test_conflicts_between_inverter_and_battery(client, data_dir):
    inv = _pdf(data_dir / "Inverter Manual.pdf", "SP-3000 Inverter Installation Manual", [
        "The SP-3000 inverter operates at 24 VDC nominal.",
        "Maximum continuous DC current: 150 A. Recommended fuse: 200 A for the battery cable.",
        "Maximum charge current: 80 A. Absorption charge voltage: 29.4 V.",
    ])
    bat = _pdf(data_dir / "Battery Manual.pdf", "LFP-12 Lithium Battery Manual", [
        "The LFP-12 battery is a 12 V lithium battery with an integrated BMS.",
        "Continuous discharge current: 100 A. Maximum charge current: 50 A.",
        "Charge voltage: 14.4 V. Battery cable fuse: 125 A.",
    ])
    d1 = _ingest(client, inv)
    d2 = _ingest(client, bat)
    r = client.post("/api/compare", json={"document_ids": [d1["id"], d2["id"]]}).json()
    kinds = {c["type"] for c in r["conflicts"]}
    assert "voltage_mismatch" in kinds
    assert "discharge_limit" in kinds
    assert "charge_current" in kinds
    assert "charge_voltage" in kinds
    assert "fuse_recommendation" in kinds
    for c in r["conflicts"]:
        assert c["classification"] == "engineering_analysis" and all(s["page"] for s in c["sources"])
