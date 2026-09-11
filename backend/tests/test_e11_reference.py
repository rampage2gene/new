"""The ABYC E-11 reference: the Python twin of packages/e11-calc, held to the
same test vectors, the same loader refusals and the same cheat-sheet render.
The tables under test are the library's synthetic fixture (made-up round
numbers), which conftest.py lets the loader accept."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
LIB = REPO / "packages" / "e11-calc"
VECTORS = json.loads((LIB / "tests" / "test-vectors.json").read_text(encoding="utf-8"))


def fixture_files(omit: list[str] | None = None) -> dict:
    from app.reference.e11_tables import read_dir

    files = read_dir(LIB / "tests" / "fixtures" / "tables")
    return {name: raw for name, raw in files.items() if raw["id"] not in (omit or [])}


def fixture_tables(omit: list[str] | None = None):
    from app.reference.e11_tables import load_tables

    return load_tables(fixture_files(omit), allow_fixture=True)


def fixture_sheet() -> dict:
    from app.reference.e11_cheatsheet import load_cheatsheet

    return load_cheatsheet(json.loads((LIB / "tests" / "fixtures" / "cheatsheet" / "cheatsheet.json").read_text(encoding="utf-8")))


def assert_subset(actual, expected, path=""):
    if isinstance(expected, list):
        assert isinstance(actual, list), f"{path}: expected a list, got {actual!r}"
        assert len(actual) == len(expected), f"{path}: expected {len(expected)} items, got {actual!r}"
        for i, e in enumerate(expected):
            assert_subset(actual[i], e, f"{path}[{i}]")
    elif isinstance(expected, dict):
        assert isinstance(actual, dict), f"{path}: expected an object, got {actual!r}"
        for k, v in expected.items():
            assert_subset(actual.get(k), v, f"{path}.{k}" if path else k)
    else:
        assert actual == expected, f"{path}: expected {expected!r}, got {actual!r}"


def get_path(obj, path: str):
    for k in path.split("."):
        obj = obj.get(k) if isinstance(obj, dict) else None
    return obj


@pytest.mark.parametrize("case", VECTORS["cases"], ids=[c["name"] for c in VECTORS["cases"]])
def test_vector(case):
    from app.reference.e11_circuit import size_circuit

    tables = fixture_tables(case.get("omit"))
    inputs = {**VECTORS["defaults"], **case.get("inputs", {})}
    result = size_circuit(inputs, tables, case.get("own") or {}, fixture_sheet())
    assert_subset(result, case.get("expect", {}))
    for b in case.get("blanks", []):
        hit = next((x for x in result["blanks"] if x["field"] == b["field"]), None)
        assert hit, f"blank {b['field']} missing; blanks: {result['blanks']}"
        if b.get("reason_contains"):
            assert b["reason_contains"] in hit["reason"], hit["reason"]
        if b.get("ask_field"):
            assert hit.get("ask", {}).get("field") == b["ask_field"]
    if "blanks_count" in case:
        assert len(result["blanks"]) == case["blanks_count"], result["blanks"]
    if "reminders_count" in case:
        assert len(result["reminders"]) == case["reminders_count"]
    for path, text in case.get("reason_contains", {}).items():
        v = get_path(result, path)
        assert isinstance(v, str) and text in v, f"{path} = {v!r}"
    for text in case.get("steps_contain", []):
        assert any(text in s for s in result["steps"]), result["steps"]
    for b in result["blanks"]:
        assert b["field"] and b["reason"]
        if "ask" in b:
            assert b["ask"]["field"].startswith("own.")


def test_loader_refuses_what_could_pass_a_guess_off_as_the_standard():
    from app.reference.e11_tables import TableError, load_tables, tables_status, usable

    files = fixture_files()
    with pytest.raises(TableError, match="fixture"):
        load_tables(files)
    with pytest.raises(TableError, match=r"circular_mils\.json: has no source\.page"):
        load_tables({"circular_mils.json": {**files["circular_mils.json"], "source": {"document": "x"}}}, allow_fixture=True)
    amp = files["ampacity_outside_engine_space.json"]
    with pytest.raises(TableError, match="every ampacity row needs size_awg, values and page"):
        load_tables({"a.json": {**amp, "rows": [{"size_awg": "10", "values": {"105": 60}}]}}, allow_fixture=True)
    fc = files["fuse_classes.json"]
    with pytest.raises(TableError, match=r"fuse class Z needs source\.document and source\.page"):
        load_tables({"f.json": {**fc, "rows": [{"class": "Z", "interrupting_rating_a": 100, "suits": []}]}}, allow_fixture=True)
    with pytest.raises(TableError, match='unknown table id "mystery"'):
        load_tables({"x.json": {**files["constants.json"], "id": "mystery"}}, allow_fixture=True)
    draft = {**files["constants.json"], "status": "draft"}
    t = load_tables({**files, "constants.json": draft}, allow_fixture=True)
    assert usable(t, "constants") is None
    assert next(r for r in tables_status(t) if r["id"] == "constants")["status"] == "draft"


def test_the_owners_saved_table_wins_over_the_bundled_copy(data_dir):
    from app.config import get_settings
    from app.reference import e11_tables
    from app.reference.e11_circuit import size_circuit

    e11_tables.reset()
    before = size_circuit(VECTORS["defaults"], e11_tables.get_tables(), {}, None)
    assert before["conductor"]["voltage_drop"]["cm_required"] == 4556.7
    assert e11_tables.tables_status(e11_tables.get_tables())[0]["origin"] == "bundled"
    mine = {**fixture_files()["constants.json"], "status": "confirmed", "values": {"K_copper": {"value": 20, "page": 9}}}
    path = e11_tables.save_table(mine)
    try:
        assert path == get_settings().user_reference_dir / "tables" / "constants.json"
        after = size_circuit(VECTORS["defaults"], e11_tables.get_tables(), {}, None)
        assert after["conductor"]["voltage_drop"]["cm_required"] == 9113.4
        assert after["conductor"]["voltage_drop"]["cm_required"] == 2 * before["conductor"]["voltage_drop"]["cm_required"]
        assert e11_tables.tables_status(e11_tables.get_tables())[0]["origin"] == "yours"
    finally:
        assert e11_tables.delete_table("constants") is True
    assert size_circuit(VECTORS["defaults"], e11_tables.get_tables(), {}, None)["conductor"]["voltage_drop"]["cm_required"] == 4556.7


def test_cheat_sheet_render_matches_the_shared_expectation():
    from app.reference.e11_cheatsheet import CheatSheetError, load_cheatsheet, reminders_for, render_html, render_markdown

    sheet = fixture_sheet()
    assert render_markdown(sheet) == (LIB / "tests" / "cheatsheet-expected.md").read_text(encoding="utf-8")
    assert '<em class="draft">(draft)</em>' in render_html(sheet) and "<script" not in render_html(sheet)
    assert [e["clause"] for e in reminders_for(sheet, ["dc"])] == ["F.1"]
    assert [e["clause"] for e in reminders_for(sheet, ["parallel", "engine_space"])] == ["F.1", "F.2", "F.3"]
    with pytest.raises(CheatSheetError, match="entry 1 has no clause"):
        load_cheatsheet({"source": {"document": "d"}, "entries": [{"topic": "t", "rule": "r", "page": 1}]})
    with pytest.raises(CheatSheetError, match="has no page"):
        load_cheatsheet({"source": {"document": "d"}, "entries": [{"topic": "t", "rule": "r", "clause": "c"}]})


def test_python_profiles_equal_the_shared_contract():
    from app.calculators import tables as T
    from app.calculators.modules import DEVICE_PROFILES

    contract = json.loads((LIB / "profiles" / "device_profiles.json").read_text(encoding="utf-8"))
    assert DEVICE_PROFILES == contract["device_profiles"]
    assert T.STANDARD_FUSE_SIZES == contract["standard_fuse_sizes_a"]
    assert T.STANDARD_BREAKER_SIZES == contract["standard_breaker_sizes_a"]


def test_real_tables_load_when_present():
    """Guards the owner's confirmed tables once they exist in the library folder: no drafts, no fixture."""
    from app.reference.e11_tables import load_tables, read_dir

    files = read_dir(LIB / "tables")
    if not files:
        pytest.skip("no confirmed tables in packages/e11-calc/tables yet")
    t = load_tables(files)
    for table in t.by_id.values():
        assert table["status"] == "confirmed", table["id"]
