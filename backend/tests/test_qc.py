from app.extraction.entities import ExtractedEntity
from app.qc.validate import validate_entities


def _ent(**kw) -> ExtractedEntity:
    base = dict(entity_type="fuse", value=300.0, unit="A", value_text="300 A", raw_text="300 A", page_number=1, block_index=0, snippet="300 A fuse", char_start=0, char_end=5, bbox=[0, 0, 1, 1], application="Battery cable", is_critical=True)
    base.update(kw)
    return ExtractedEntity(**base)


def test_low_ocr_confidence_flags_alternatives():
    e = _ent(ocr_confidence=0.6, extra={"alternatives": ["800 A"]})
    flags = validate_entities([e])
    assert any(f.flag_type == "low_ocr_confidence" and "800 A" in f.message for f in flags)
    assert e.flags and e.flags[0]["severity"] == "critical"


def test_discrepancy_against_repeated_value():
    ents = [_ent(page_number=3), _ent(page_number=5), _ent(page_number=9, value=800.0, value_text="800 A", ocr_confidence=0.7, extra={"alternatives": ["300 A"]})]
    flags = validate_entities(ents)
    kinds = {f.flag_type for f in flags}
    assert "discrepancy" in kinds and "low_ocr_confidence" in kinds
    d = next(f for f in flags if f.flag_type == "discrepancy")
    assert d.entity_index == 2 and d.details["reference"] == "300 A"


def test_different_qualifiers_are_not_discrepancies():
    ents = [_ent(qualifier="recommended", value=175.0, value_text="175 A"), _ent(qualifier="recommended", value=175.0, value_text="175 A"), _ent(qualifier="maximum", value=200.0, value_text="200 A")]
    assert not [f for f in validate_entities(ents) if f.flag_type == "discrepancy"]


def test_out_of_range_voltage():
    e = _ent(entity_type="voltage", value=4800.0, unit="V", value_text="4800 V")
    assert any(f.flag_type == "unit_out_of_range" for f in validate_entities([e]))


def test_awg_cross_reference():
    ents = [_ent(entity_type="wire_size", value=-3, unit="AWG", value_text="4/0 AWG", extra={"awg": "4/0"}), _ent(entity_type="wire_size", value=4, unit="AWG", value_text="4 AWG", extra={"awg": "4"})]
    assert any(f.flag_type == "awg_cross_reference" for f in validate_entities(ents))
