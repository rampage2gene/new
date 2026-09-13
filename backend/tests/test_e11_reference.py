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
    # The words a person reads come from the same two engines as the numbers,
    # so a label or a sentence changed in one and not the other fails here.
    if "present" in case:
        from app.reference.e11_present import condition_options, present_circuit

        want = case["present"]
        view = present_circuit(inputs, result, want.get("unit", "awg"), case.get("own") or {})
        for key, fields in (want.get("rows") or {}).items():
            row = next((r for r in view["rows"] if r["key"] == key), None)
            assert row, f"no presented row {key!r}; rows: {[r['key'] for r in view['rows']]}"
            for field, value in fields.items():
                if field == "note_contains":
                    assert isinstance(row["note"], str) and value in row["note"], f"{key} note {row['note']!r} lacks {value!r}"
                else:
                    assert row[field] == value, f"{key}.{field}: {row[field]!r}"
        if "groups" in want:
            assert list(dict.fromkeys(r["group"] for r in view["rows"])) == want["groups"]
        for key, labels in (want.get("condition_options") or {}).items():
            offered = condition_options(tables).get(key)
            assert offered, f"no options generated for {key!r}"
            assert [o["label"] for o in offered] == labels, f"options for {key}"
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
    hs = files["heat_shrink.json"]
    with pytest.raises(TableError, match="heat shrink S9: recovered_id must be above zero and below supplied_id"):
        load_tables({"h.json": {**hs, "rows": [{"size": "S9", "supplied_id": 3, "recovered_id": 3}]}}, allow_fixture=True)
    with pytest.raises(TableError, match='cable_dimensions needs diameter_unit "mm" or "in"'):
        load_tables({"c.json": {**files["cable_dimensions.json"], "diameter_unit": "cm"}}, allow_fixture=True)
    with pytest.raises(TableError, match="every lugs row needs size_awg, stud and part"):
        load_tables({"l.json": {**files["lugs.json"], "rows": [{"size_awg": "12", "stud": "M8"}]}}, allow_fixture=True)
    # A catalog table needs its source document but no page of the standard.
    load_tables({"l.json": {**files["lugs.json"], "source": {"document": "a lug catalog"}}}, allow_fixture=True)
    with pytest.raises(TableError, match="has no source.document"):
        load_tables({"l.json": {**files["lugs.json"], "source": {}}}, allow_fixture=True)
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
    from app.calculators.modules import CIRCUIT_TYPES

    assert CIRCUIT_TYPES == contract["circuit_types"]
    for c in CIRCUIT_TYPES.values():
        assert c["load_type"] in DEVICE_PROFILES, c["label"]


def test_fittings_helpers_match_the_library():
    from app.reference.e11_fittings import cable_outside_diameter, heat_shrink_for, lug_for, normalize_stud, to_mm
    from app.reference.e11_tables import load_tables

    for s in ['5/16"', " 5/16 ", "5/16 in", "5/16in"]:
        assert normalize_stud(s) == "5/16"
    assert normalize_stud("M8") == "m8" and normalize_stud(None) == ""
    assert to_mm(1, "in") == 25.4
    files = fixture_files()
    inches = {**files["cable_dimensions.json"], "diameter_unit": "in", "rows": [{"size_awg": "12", "outside_diameter": 0.25}]}
    t = load_tables({**files, "cable_dimensions.json": inches}, allow_fixture=True)
    od = cable_outside_diameter("12", t)
    assert (od["value"], od["unit"], od["mm"], od["source"]["document"]) == (0.25, "in", 6.35, inches["source"]["document"])
    t = fixture_tables()
    assert heat_shrink_for(2, None, t)["size"] == "S3"
    assert heat_shrink_for(2, 5, t)["size"] == "S6"
    none = heat_shrink_for(0.5, None, t)
    assert none["value"] is None and "shrinks below" in none["reason"] and none["ask"]["kind"] == "text"
    lug = lug_for("12", '5/16"', t)
    assert (lug["part"], lug["crimp_die"], lug["barrel_od_mm"]) == ("L12-516", "D12", 7)
    no_die = lug_for("12", "M8", t)
    assert no_die["crimp_die"] is None and no_die["die_ask"]["field"] == "own.crimp_die"
    own_die = lug_for("12", "M8", t, {"crimp_die": "DX"})
    assert (own_die["crimp_die"], own_die["die_source"]) == ("DX", {"by": "you"})
    assert "no 10 AWG row" in lug_for("10", "5/16", t)["reason"]


def test_a_page_that_defines_l_one_way_takes_half_the_loop():
    from app.reference.e11_circuit import size_circuit
    from app.reference.e11_tables import load_tables

    files = fixture_files()
    t = load_tables({**files, "constants.json": {**files["constants.json"], "length_definition": "one_way"}}, allow_fixture=True)
    base = {**VECTORS["defaults"]}
    loop = size_circuit({**base, "length": 10, "length_basis": "loop"}, t)
    one = size_circuit({**base, "length": 5}, t)
    assert loop["conductor"]["voltage_drop"]["cm_required"] == one["conductor"]["voltage_drop"]["cm_required"] == 2278.4
    assert "there and back" in loop["steps"][0]


def test_real_tables_load_when_present():
    """Guards the owner's confirmed tables once they exist in the library folder: no drafts, no fixture."""
    from app.reference.e11_tables import load_tables, read_dir

    files = read_dir(LIB / "tables")
    if not files:
        pytest.skip("no confirmed tables in packages/e11-calc/tables yet")
    t = load_tables(files)
    for table in t.by_id.values():
        assert table["status"] == "confirmed", table["id"]
