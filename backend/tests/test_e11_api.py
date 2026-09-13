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
BASE = {"system_voltage": 24, "current": 10, "length": 10, "length_unit": "m", "max_drop_percent": "3", "insulation_rating_c": 105, "engine_space": "no", "bundle": "2", "circuit_type": "general_dc", "stud_size": "5/16"}


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
    assert [o["value"] for o in next(i for i in spec["inputs"] if i["key"] == "size_unit")["options"]] == ["awg", "mm2"]


def test_the_bundle_is_picked_from_the_confirmed_table(client):
    def options():
        spec = next(s for s in client.get("/api/calculators").json() if s["id"] == "circuit_e11")
        return next(i for i in spec["inputs"] if i["key"] == "bundle")["options"]

    opts = options()
    assert [o["value"] for o in opts] == ["2", "3", "7"]
    assert opts[1]["label"] == "3 to 6 conductors bundled (× 0.5, page 3, test data)"  # the fixture says so where the choice is made
    r = _run(client, bundle="7")
    assert "bundling factor 0.25" in {x["key"]: x for x in r["results"]}["ampacity_size"]["note"]
    # Without a confirmed table the count is typed, and the factor asked for.
    draft = {**_fixture("bundling_factors"), "status": "draft"}
    client.put("/api/reference/e11/tables/bundling_factors", json=draft)
    try:
        assert [o["value"] for o in options()] == ["2", "count"]
        assert client.post("/api/calculators/circuit_e11/run", json={"inputs": {**BASE, "bundle": "count"}}).status_code == 422
        r = _run(client, bundle="count", bundled_conductors=4)
        assert any(a["input_key"] == "own_bundling_factor" for a in r["asks"])
        r = _run(client, bundle="count", bundled_conductors=4, own_bundling_factor=0.5)
        assert "factor entered by you" in {x["key"]: x for x in r["results"]}["ampacity_size"]["note"]
    finally:
        client.delete("/api/reference/e11/tables/bundling_factors")


def test_every_condition_is_offered_from_the_tables(client):
    """A person picks from what their own pages print - the temperature
    columns the ampacity table carries, which drop limits have a printed grid
    behind them - and never from a list written into the code."""
    def field(key):
        spec = next(s for s in client.get("/api/calculators").json() if s["id"] == "circuit_e11")
        return next(i for i in spec["inputs"] if i["key"] == key)

    rating = field("insulation_rating_c")
    assert rating["kind"] == "select"  # a typed number until the pages say which columns exist
    assert [o["value"] for o in rating["options"]] == ["60", "105"]
    assert rating["options"][1]["label"] == "105 °C (page 2, test data)"
    assert rating["default"] == "105"

    drop = field("max_drop_percent")
    assert [o["value"] for o in drop["options"]] == ["3", "10", "other"]
    # The formula honours any limit; the label says which one has a page behind it.
    assert drop["options"][0]["label"] == "3 % (critical circuits) — printed table at 12 V (page 4, test data)"
    assert drop["options"][2]["label"] == "other"

    assert [o["label"] for o in field("engine_space")["options"]] == ["No", "Yes"]
    # Drop the inside-engine-space table and the choice says so rather than vanishing.
    draft = {**_fixture("ampacity_inside_engine_space"), "status": "draft"}
    client.put("/api/reference/e11/tables/ampacity_inside_engine_space", json=draft)
    try:
        assert [o["label"] for o in field("engine_space")["options"]] == ["No", "Yes — that table is not confirmed yet"]
        assert [o["value"] for o in field("insulation_rating_c")["options"]] == ["60", "105"]
    finally:
        client.delete("/api/reference/e11/tables/ampacity_inside_engine_space")


def test_sizes_can_be_shown_in_mm2(client):
    r = _run(client, size_unit="mm2")
    by = {x["key"]: x for x in r["results"]}
    assert by["size_awg"]["value"] == "6 mm² (12 AWG)" and by["size_awg"]["label"] == "Cable size to use"
    assert by["size_mm2"]["value"] == 4.05 and "12 AWG is 4.05 mm²" in by["size_mm2"]["note"]
    assert by["bom_cable"]["value"] == "1 × 6 mm² (12 AWG), 10 m"
    r = _run(client, size_unit="mm2", current=100, length=4, max_drop_percent="10", circuit_type="battery_main", short_circuit_a=5000)
    by = {x["key"]: x for x in r["results"]}
    assert by["size_awg"]["value"] == "2 × 6 mm² in parallel (2 × 12 AWG)" and "No single listed size" in by["size_awg"]["note"]


def test_the_note_says_when_the_printed_table_or_the_formula_decided(client):
    r = _run(client, system_voltage=12, current=5, length=20, length_unit="ft")
    assert "asks for this size, more than the formula's 14 AWG" in {x["key"]: x for x in r["results"]}["size_awg"]["note"]
    r = _run(client, system_voltage=12, current=25, length=10, length_unit="ft")
    note = {x["key"]: x for x in r["results"]}["size_awg"]["note"]
    assert note.startswith("The printed 3 % table on page 4 stops at 20 A, so the circular-mils formula")


def test_circuit_result_cites_pages_and_groups_results(client):
    r = _run(client)
    by = {x["key"]: x for x in r["results"]}
    assert by["size_awg"]["value"] == "12 AWG" and by["size_awg"]["group"] == "Cable size"
    assert "Set by the voltage-drop limit" in by["size_awg"]["note"] and "18 AWG would" in by["size_awg"]["note"]
    assert by["cm_required"]["group"] == "How it was decided"
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
    r = _run(client, max_drop_percent="other", max_drop_other=5, bundle="3")
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


def test_the_matcher_reads_the_words_printed_on_the_page():
    """Which detected table is which table of the standard is decided by the
    words on the page, and only when they are unambiguous."""
    from app.api.reference import match_detected_tables

    def t(page, *header, section=None):
        return {"page": page, "table_index": 0, "rows": [list(header)], "section": section}

    m = match_detected_tables([
        t(12, "Conductor size", "Circular mils", "mm2"),
        t(14, "Size", "60 C", "75 C", section="Allowable amperage of conductors inside engine spaces"),
        t(15, "Size", "60 C", "75 C", section="Allowable amperage of conductors inside engine spaces"),
        t(16, "Number of conductors bundled", "Correction factor"),
        t(18, "Amperes", "10", "15", section="Conductor sizes for a 13 % drop"),
        t(20, "Parameter", "Value"),
        t(22, "Size", "Correction factor for temperature"),
    ])
    assert [c["page"] for c in m["circular_mils"]] == [12]
    # Two pages of the same table: a question for the person, not a choice.
    assert [c["page"] for c in m["ampacity_inside_engine_space"]] == [14, 15]
    assert m["ampacity_outside_engine_space"] == []
    assert [c["page"] for c in m["bundling_factors"]] == [16]
    assert m["voltage_drop_3pct"] == [] and m["voltage_drop_10pct"] == []
    assert m["constants"] == []

    out = match_detected_tables([t(13, "Size", "60 C", section="Allowable amperage of conductors outside engine spaces")])
    assert [c["page"] for c in out["ampacity_outside_engine_space"]] == [13] and out["ampacity_inside_engine_space"] == []
    # A table that does not say which side belongs to both until they choose.
    both = match_detected_tables([t(17, "Size", "Ampacity")])
    assert [c["page"] for c in both["ampacity_inside_engine_space"]] == [17]
    assert [c["page"] for c in both["ampacity_outside_engine_space"]] == [17]
    grid = match_detected_tables([t(9, "Amperes", "10 ft", "15 ft", section="Conductor sizes for a 3 % drop")])
    assert [c["page"] for c in grid["voltage_drop_3pct"]] == [9] and grid["voltage_drop_10pct"] == []


def test_copying_every_table_says_what_it_could_not_do(client, manual_doc):
    """The manual fixture holds one Parameter/Value table, which is none of
    the standard's: nothing is copied and every table is accounted for."""
    draft = {**_fixture("bundling_factors"), "status": "draft"}
    assert client.put("/api/reference/e11/tables/bundling_factors", json=draft).status_code == 200
    try:
        report = client.post("/api/reference/e11/import-all", json={"document_id": manual_doc["id"]}).json()
        assert report["copied"] == [] and report["ambiguous"] == [] and report["unfit"] == []
        # Already the person's copy, so it is left exactly as it is.
        assert report["kept"] == ["bundling_factors"]
        assert report["not_found"] == ["constants", "circular_mils", "ampacity_outside_engine_space", "ampacity_inside_engine_space", "voltage_drop_3pct", "voltage_drop_10pct"]
    finally:
        client.delete("/api/reference/e11/tables/bundling_factors")
    assert client.post("/api/reference/e11/import-all", json={"document_id": "no-such-document"}).status_code == 404


def test_copying_every_table_drafts_the_one_it_recognises(client, manual_doc):
    """A page that reads as the circular-mils table is copied as a draft of
    the person's own, for them to check against the page and confirm."""
    from app.db import session_scope
    from app.models import Document

    with session_scope() as s:
        doc = s.get(Document, manual_doc["id"])
        before = doc.structure
        doc.structure = {**(before or {}), "tables": [{"page": 7, "section": "Conductor sizes", "rows": [
            ["Conductor size AWG", "Area in circular mils", "mm2"],
            ["18", "1620", "0.82"],
            ["16", "2580", "1.31"],
        ]}]}
    try:
        report = client.post("/api/reference/e11/import-all", json={"document_id": manual_doc["id"]}).json()
        assert report["copied"] == [{"id": "circular_mils", "page": 7}]
        t = client.get("/api/reference/e11/tables/circular_mils").json()
        assert t["origin"] == "yours" and t["status"] == "draft"
        assert t["source"]["page"] == 7 and [r["size_awg"] for r in t["rows"]] == ["18", "16"]
    finally:
        client.delete("/api/reference/e11/tables/circular_mils")
        with session_scope() as s:
            s.get(Document, manual_doc["id"]).structure = before


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
