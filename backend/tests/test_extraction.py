from app.extraction import patterns as P
from app.extraction.entities import extract_entities
from app.ingest.types import RawBlock, RawPage
from app.structure.layout import analyse_layout


def _page(text: str, page_number: int = 1) -> RawPage:
    blocks = []
    y = 50
    for para in text.strip().split("\n\n"):
        blocks.append(RawBlock(text=para, bbox=(50, y, 550, y + 30), source="embedded", font_size=10, lines=para.split("\n")))
        y += 40
    page = RawPage(page_number=page_number, width=612, height=792, blocks=blocks, text_source="embedded")
    analyse_layout([page])
    return page


def _by_type(ents, t):
    return [e for e in ents if e.entity_type == t]


def test_awg_never_confuses_4_and_4_0():
    assert [m.group("awg") for m in P.AWG_RE.finditer("4/0 AWG and 4 AWG and #2 AWG")] == ["4/0", "4", "2"]


def test_voltage_never_reads_48_from_480():
    assert [m.group("num") for m in P.VOLTAGE_RE.finditer("480 V and 48 V and 5000 VA")] == ["480", "48"]


def test_current_ignores_awg_ac_ah():
    assert [m.group("num") for m in P.CURRENT_RE.finditer("300 A, 4 AWG, 120 VAC, 200 Ah, 30 amps")] == ["300", "30"]


def test_units_do_not_cross_line_breaks():
    assert [m.group(0) for m in P.VOLTAGE_RE.finditer("48 VDC\nDC input")] == ["48 VDC"]


def test_fuse_breaker_current_classification_and_qualifiers():
    page = _page(
        """Install a 300 A Class T fuse within 180 mm of the battery positive terminal.

The maximum continuous DC current is 125 A; peak current 250 A. Recommended fuse: 175 A (maximum 200 A).

Protect the AC input with a 32 A double-pole circuit breaker. AC input: 230 VAC, 50 Hz."""
    )
    ents = extract_entities([page])
    fuses = {(e.value_text, e.qualifier) for e in _by_type(ents, "fuse")}
    assert ("300 A", None) in fuses and ("175 A", "recommended") in fuses and ("200 A", "maximum") in fuses
    assert next(e for e in _by_type(ents, "fuse") if e.value_text == "300 A").device_type == "Class T"
    currents = {(e.value_text, e.qualifier) for e in _by_type(ents, "current")}
    assert ("125 A", "continuous") in currents and ("250 A", "peak") in currents
    breaker = _by_type(ents, "breaker")[0]
    assert breaker.value == 32 and breaker.device_type == "double-pole" and breaker.circuit == "ac"
    v = next(e for e in _by_type(ents, "voltage") if e.value == 230)
    assert v.value_text == "230 VAC" and v.circuit == "ac"


def test_wire_sizes_with_application_and_source():
    page = _page("Connect the inverter using 4/0 AWG battery cable.\n\nUse 6 mm² (10 AWG) wire for the AC input.", page_number=12)
    ents = _by_type(extract_entities([page]), "wire_size")
    by_text = {e.value_text: e for e in ents}
    assert by_text["4/0 AWG"].application == "Battery cable" and by_text["4/0 AWG"].page_number == 12
    assert by_text["4/0 AWG"].extra["awg"] == "4/0" and by_text["4/0 AWG"].value == -3
    assert by_text["10 AWG"].application == "AC input" and by_text["6 mm²"].value == 6
    assert all(e.is_critical for e in ents)
    assert all(e.snippet and e.bbox for e in ents)


def test_torque_temperature_equipment():
    page = _page("Torque the M8 battery terminals to 12 N·m (106 in-lb).\n\nOperating temperature -20 to 50 °C.\n\nModel: XYZ-5000 inverter, rated 5000 W continuous, 48 VDC nominal. Battery: BAT-48, 200 Ah.")
    ents = extract_entities([page])
    torques = {e.value_text: e for e in _by_type(ents, "torque")}
    assert torques["12 N·m"].extra["terminal"] == "M8"
    assert abs(torques["106 in-lb"].extra["nm_equivalent"] - 11.98) < 0.05
    temp = _by_type(ents, "temperature")[0]
    assert temp.extra["range"] == [-20.0, 50.0] and temp.qualifier == "operating"
    equip = {(e.equipment, e.equipment_model) for e in _by_type(ents, "equipment")}
    assert ("inverter", "XYZ-5000") in equip and ("battery", "BAT-48") in equip
    p = next(e for e in _by_type(ents, "power") if e.value == 5000)
    assert p.qualifier == "continuous" and p.equipment_model == "XYZ-5000"


def test_table_rows_provide_application_and_qualifier():
    rows = [["Parameter", "Value"], ["Maximum continuous DC current", "125 A"], ["Nominal DC voltage", "48 VDC"]]
    text = "\n".join(" | ".join(r) for r in rows)
    block = RawBlock(text=text, bbox=(50, 50, 400, 120), source="embedded", lines=text.split("\n"), table={"rows": rows}, block_type="table")
    page = RawPage(page_number=2, width=612, height=792, blocks=[block], text_source="embedded")
    analyse_layout([page])
    ents = extract_entities([page])
    cur = _by_type(ents, "current")[0]
    assert cur.application == "Maximum continuous DC current" and cur.qualifier == "continuous"
    volt = _by_type(ents, "voltage")[0]
    assert volt.application == "Nominal DC voltage" and volt.qualifier == "nominal"
