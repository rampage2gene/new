"""The circuit calculator and the reference endpoints, over the API, on the
library's synthetic fixture (conftest.py points the reference at it)."""
from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest

LIB = Path(__file__).resolve().parents[2] / "packages" / "e11-calc"


def _fixture(name: str) -> dict:
    return json.loads((LIB / "tests" / "fixtures" / "tables" / f"{name}.json").read_text(encoding="utf-8"))


# The length is the whole loop (10 m there and back = the vectors' 5 m one way); the stud is given so the fixture lugs table answers.
BASE = {"system_voltage": 24, "current": 10, "length": 10, "length_unit": "m", "max_drop_percent": "3", "insulation_rating_c": 105, "engine_space": "no", "bundled": "no", "circuit_type": "general_dc", "stud_size": "5/16"}


def _run(client, **inputs) -> dict:
    r = client.post("/api/calculators/circuit_e11/run", json={"inputs": {**BASE, **inputs}})
    assert r.status_code == 200, r.text
    return r.json()


def test_circuit_calculator_is_registered_with_answer_inputs(client):
    specs = {s["id"]: s for s in client.get("/api/calculators").json()}
    spec = specs["circuit_e11"]
    answers = {i["key"]: i["answers"] for i in spec["inputs"] if i.get("answers")}
    assert answers == {
        "own_ampacity_a": "conductor.ampacity.size_awg", "own_bundling_factor": "conductor.ampacity.size_awg", "own_k": "conductor.voltage_drop.cm_required", "own_short_circuit_a": "protection.interrupting.required_a",
        "own_cable_od_mm": "fittings.cable_od", "own_heat_shrink_size": "fittings.heat_shrink.size", "own_lug_part": "fittings.lug.part", "own_crimp_die": "fittings.lug.crimp_die",
    }
    length = next(i for i in spec["inputs"] if i["key"] == "length")
    assert "there and back" in length["label"]
    assert [o["value"] for o in next(i for i in spec["inputs"] if i["key"] == "circuit_type")["options"]][:2] == ["battery_main", "inverter"]
    assert "entity" not in spec["description"].lower()


def test_circuit_result_cites_pages_and_groups_results(client):
    r = _run(client)
    by = {x["key"]: x for x in r["results"]}
    assert by["size_awg"]["value"] == "12 AWG" and by["size_awg"]["group"] == "Conductor"
    assert by["cm_required"]["value"] == 4556.7 and "page 1" in by["cm_required"]["note"]
    assert by["ampacity_size"]["value"] == "18 AWG" and "page 2" in by["ampacity_size"]["note"]
    assert by["fuse_a"]["value"] == 15 and by["fuse_a"]["group"] == "Protection"
    assert by["interrupting"]["value"] is None and "short-circuit current was not given" in by["interrupting"]["note"]
    assert [a["input_key"] for a in r["asks"]] == ["own_short_circuit_a"]
    assert any(s["page"] == 1 for s in r["sources"]) and r["reminders"][0]["clause"] == "F.1"
    assert "synthetic test tables" in " ".join(r["assumptions"])


def test_a_blank_becomes_a_value_when_the_person_answers(client):
    r = _run(client, insulation_rating_c=90)
    by = {x["key"]: x for x in r["results"]}
    assert by["size_awg"]["value"] is None and "no 90 °C column" in by["size_awg"]["note"]
    ask = next(a for a in r["asks"] if a["field"] == "conductor.ampacity.size_awg")
    assert ask["input_key"] == "own_ampacity_a" and ask["unit"] == "A"
    r2 = _run(client, insulation_rating_c=90, own_ampacity_a=40)
    by2 = {x["key"]: x for x in r2["results"]}
    assert by2["size_awg"]["value"] == "12 AWG"
    assert "entered by you" in by2["ampacity_size"]["note"]
    assert by2["fuse_a"]["value"] == 15
    assert all(a["field"] != "conductor.ampacity.size_awg" for a in r2["asks"])


def test_parallel_conductors_and_the_fuse_for_them(client):
    r = _run(client, current=100, length=4, max_drop_percent="10", circuit_type="battery_main", short_circuit_a=5000)
    by = {x["key"]: x for x in r["results"]}
    assert by["size_awg"]["value"] == "2 × 12 AWG in parallel"
    assert by["fuse_a"]["value"] == 100 and "Class X" in by["interrupting"]["value"]
    assert r["asks"] == [] and any(e["clause"] == "F.2" for e in r["reminders"])


def test_fittings_and_bill_of_materials_come_from_the_catalog_tables(client):
    r = _run(client)
    by = {x["key"]: x for x in r["results"]}
    assert by["cable_od"]["value"] == 4 and by["cable_od"]["unit"] == "mm" and by["cable_od"]["group"] == "Fittings"
    assert by["cable_od"]["note"].startswith("From SYNTHETIC TEST FIXTURE - not a cable catalog, page 1")
    assert by["heat_shrink"]["value"] == "S12 (12 → 4 mm, adhesive-lined)"
    assert by["lug"]["value"] == "L12-516 for a 5/16 stud" and by["crimp_die"]["value"] == "D12"
    assert by["load_type"]["value"] == "Resistive load (heater, lights)" and "circuit type" in by["load_type"]["note"]
    assert by["bom_cable"]["value"] == "1 × 12 AWG, 10 m" and "there and back per cable" in by["bom_cable"]["note"] and by["bom_cable"]["group"] == "Bill of materials"
    assert by["bom_lugs"]["value"] == "2 × L12-516" and by["bom_heat_shrink"]["value"] == "2 pieces of S12"
    assert by["bom_fuse"]["value"].startswith("1 × 15 A")
    assert any("there and back" in step for step in r["steps"])
    # The loop length is what the formula sees: 10 m there and back = 5 m each way, the vectors' number.
    assert by["cm_required"]["value"] == 4556.7


def test_a_text_blank_is_answered_by_typing(client):
    r = _run(client, stud_size="M10")
    by = {x["key"]: x for x in r["results"]}
    assert by["lug"]["value"] is None and "not M10" in by["lug"]["note"]
    ask = next(a for a in r["asks"] if a["field"] == "fittings.lug.part")
    assert ask["input_key"] == "own_lug_part" and ask["kind"] == "text" and ask["unit"] is None
    assert by["bom_lugs"]["value"] == "2 lugs needed; part not chosen yet"
    r2 = _run(client, stud_size="M10", own_lug_part="X-M10", own_crimp_die="DX")
    by2 = {x["key"]: x for x in r2["results"]}
    assert by2["lug"]["value"] == "X-M10 for a M10 stud" and by2["lug"]["note"] == "entered by you"
    assert by2["crimp_die"]["value"] == "DX" and by2["bom_lugs"]["value"] == "2 × X-M10"
    assert any("not checked against the stud" in w for w in r2["warnings"])
    assert all(a["field"] != "fittings.lug.part" for a in r2["asks"])
    # No stud at all: the ask points at the stud input itself.
    r3 = _run(client, stud_size="")
    ask3 = next(a for a in r3["asks"] if a["field"] == "fittings.lug.part")
    assert ask3["input_key"] == "stud_size" and ask3["kind"] == "text"


def test_catalog_tables_are_typed_not_imported(client, manual_doc):
    s = client.get("/api/reference/e11").json()
    assert {t["id"] for t in s["tables"]} >= {"cable_dimensions", "heat_shrink", "lugs"}
    assert client.post("/api/reference/e11/tables/lugs/import", json={"document_id": manual_doc["id"], "page": 1}).status_code == 422
    mine = {**_fixture("cable_dimensions"), "status": "confirmed", "source": {"document": "My cable catalog"}, "rows": [{"size_awg": "12", "outside_diameter": 0.2}], "diameter_unit": "in"}
    saved = client.put("/api/reference/e11/tables/cable_dimensions", json=mine).json()
    try:
        assert saved["status"] == "confirmed" and saved["origin"] == "yours" and saved["source"].get("page") is None
        by = {x["key"]: x for x in _run(client)["results"]}
        assert by["cable_od"]["value"] == 0.2 and by["cable_od"]["unit"] == "in" and by["cable_od"]["note"] == "From My cable catalog"
        assert by["heat_shrink"]["value"].startswith("S12")  # 0.2 in = 5.08 mm, the lug barrel is 7 mm
    finally:
        assert client.delete("/api/reference/e11/tables/cable_dimensions").status_code == 200


def test_a_fuse_that_would_exceed_the_conductor_is_a_warning_not_a_number(client):
    r = _run(client, system_voltage=48, current=30, length=2, max_drop_percent="10", circuit_type="windlass")
    by = {x["key"]: x for x in r["results"]}
    assert by["fuse_a"]["value"] is None and "would exceed the conductor" in by["fuse_a"]["note"]
    assert any("Use a larger conductor" in w for w in r["warnings"])


def test_other_drop_limit_and_bundling(client):
    r = _run(client, max_drop_percent="other", max_drop_other=5, bundled="yes", bundled_conductors=4)
    by = {x["key"]: x for x in r["results"]}
    assert by["printed_table_size"]["value"] is None and "5 % limit" in by["printed_table_size"]["note"]
    assert "bundling factor 0.5" in by["ampacity_size"]["note"]
    assert client.post("/api/calculators/circuit_e11/run", json={"inputs": {**BASE, "max_drop_percent": "other"}}).status_code == 422


def test_workbook_export_of_the_circuit_calculator(client):
    r = client.get("/api/export/workbook", params={"include": "calculators", "calculators": ["circuit_e11"]})
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/vnd.openxml")


def test_fuse_protection_prefers_the_confirmed_e11_ampacity(client, monkeypatch):
    r = client.post("/api/calculators/fuse_protection/run", json={"inputs": {"device_type": "resistive", "continuous_current": 10, "conductor_size": "12 AWG"}}).json()
    amp = next(x for x in r["results"] if x["key"] == "conductor_ampacity")
    assert amp["value"] == 60 and "from ABYC E-11" in amp["note"] and "page 2" in amp["note"]

    from app.reference import e11_tables

    monkeypatch.setattr(e11_tables, "_dirs", lambda: [("yours", Path("/nonexistent/a")), ("bundled", Path("/nonexistent/b"))])
    e11_tables.reset()
    try:
        r = client.post("/api/calculators/fuse_protection/run", json={"inputs": {"device_type": "resistive", "continuous_current": 10, "conductor_size": "12 AWG"}}).json()
        amp = next(x for x in r["results"] if x["key"] == "conductor_ampacity")
        assert amp["value"] == 45 and amp["note"].startswith("Typical published value")
        blank = client.post("/api/calculators/circuit_e11/run", json={"inputs": BASE}).json()
        assert blank["results"][0]["value"] is None and blank["asks"][0]["field"] == "reference"
    finally:
        monkeypatch.undo()
        e11_tables.reset()


def test_voltage_drop_gains_the_e11_rows_when_tables_are_confirmed(client):
    r = client.post("/api/calculators/voltage_drop/run", json={"inputs": {"voltage": 24, "current": 10, "length": 5, "length_unit": "m", "size": "12 AWG", "material": "copper"}}).json()
    by = {x["key"]: x for x in r["results"]}
    assert by["e11_size_3pct"]["value"] == "12 AWG" and "page 1" in by["e11_size_3pct"]["note"]
    assert by["e11_size_10pct"]["value"] == "16 AWG"  # 1367 circular mils needed; 18 AWG (1000) is too small


def test_reference_status_and_table_round_trip(client):
    s = client.get("/api/reference/e11").json()
    assert s["installed"] and s["fixture"] and s["missing"] == [] and len(s["tables"]) == 11
    assert all(t["layout"]["title"] for t in s["tables"])
    t = client.get("/api/reference/e11/tables/constants").json()
    assert t["status"] == "fixture" and t["origin"] == "bundled"

    mine = {**_fixture("constants"), "status": "draft", "values": {"K_copper": {"value": 11, "page": 7}}}
    saved = client.put("/api/reference/e11/tables/constants", json=mine).json()
    assert saved["status"] == "draft" and saved["origin"] == "yours"
    try:
        blank = client.post("/api/calculators/circuit_e11/run", json={"inputs": BASE}).json()
        assert any(a["input_key"] == "own_k" for a in blank["asks"]), "a draft is not usable"
        confirmed = client.put("/api/reference/e11/tables/constants", json={**mine, "status": "confirmed"}).json()
        assert confirmed["status"] == "confirmed"
        r = client.post("/api/calculators/circuit_e11/run", json={"inputs": BASE}).json()
        assert next(x for x in r["results"] if x["key"] == "cm_required")["value"] == 5012.4  # 11/10 of 4556.7
        assert client.put("/api/reference/e11/tables/constants", json={**mine, "status": "fixture"}).status_code == 422
        assert client.put("/api/reference/e11/tables/constants", json={**mine, "source": {"document": "x"}}).status_code == 422
        assert client.put("/api/reference/e11/tables/nope", json=mine).status_code == 404
        z = client.get("/api/reference/e11/download")
        names = zipfile.ZipFile(io.BytesIO(z.content)).namelist()
        assert "tables/constants.json" in names and "README.txt" in names
    finally:
        assert client.delete("/api/reference/e11/tables/constants").json()["origin"] == "bundled"


def test_import_drafts_a_table_from_a_detected_table(client, manual_doc):
    detected = client.get(f"/api/reference/e11/documents/{manual_doc['id']}/tables").json()
    if not detected:
        pytest.skip("the manual fixture has no detected table")
    first = detected[0]
    r = client.post("/api/reference/e11/tables/circular_mils/import", json={"document_id": manual_doc["id"], "page": first["page"], "table_index": first["table_index"]})
    try:
        if r.status_code == 200:
            t = r.json()
            assert t["status"] == "draft" and t["source"]["document_id"] == manual_doc["id"] and t["source"]["page"] == first["page"]
        else:
            assert r.status_code == 422 and "does not fit" in r.json()["detail"]
    finally:
        client.delete("/api/reference/e11/tables/circular_mils")
    assert client.post("/api/reference/e11/tables/circular_mils/import", json={"document_id": manual_doc["id"], "page": 999}).status_code == 404
    assert client.post("/api/reference/e11/tables/fuse_classes/import", json={"document_id": manual_doc["id"], "page": first["page"]}).status_code == 422


def test_cheatsheet_round_trip(client):
    s = client.get("/api/reference/e11/cheatsheet").json()
    assert len(s["entries"]) == 4 and s["markdown"].startswith("# Installation reminders") and s["origin"] == "bundled"
    mine = {"source": {"document": "My E-11"}, "entries": [{"topic": "T", "rule": "R", "clause": "C", "page": 4, "applies_to": ["always"], "status": "confirmed"}]}
    saved = client.put("/api/reference/e11/cheatsheet", json=mine).json()
    try:
        assert saved["origin"] == "yours" and saved["entries"][0]["clause"] == "C"
        assert client.put("/api/reference/e11/cheatsheet", json={"source": {"document": "x"}, "entries": [{"topic": "T", "rule": "R", "page": 1}]}).status_code == 422
        r = client.post("/api/calculators/circuit_e11/run", json={"inputs": BASE}).json()
        assert [e["clause"] for e in r["reminders"]] == ["C"]
    finally:
        from app.config import get_settings

        (get_settings().user_reference_dir / "cheatsheet" / "cheatsheet.json").unlink()
