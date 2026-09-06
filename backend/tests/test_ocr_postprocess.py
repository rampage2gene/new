from app.ocr.postprocess import awg_ambiguity, digit_alternatives, normalise_technical_text


def test_normalises_awg_and_units():
    r = normalise_technical_text("Use 4 / 0 AWG cable, fuse 3O0 A, 48 V DC, torque 12 N m, 35 mm2, 12, 000 BTU, 0.5 ohm")
    assert r.text == "Use 4/0 AWG cable, fuse 300 A, 48 VDC, torque 12 N·m, 35 mm², 12,000 BTU, 0.5 Ω"
    rules = {n.rule for n in r.normalisations}
    assert {"awg_slash", "letter_digit", "mm2", "thousands"} <= rules


def test_zero_awg_forms():
    assert normalise_technical_text("0000 AWG and 00 AWG").text == "4/0 AWG and 2/0 AWG"


def test_digit_alternatives():
    assert "800" in digit_alternatives("300")
    assert "48" not in digit_alternatives("48")


def test_awg_ambiguity_only_for_ambiguous_forms():
    assert awg_ambiguity("10 AWG") is None
    assert awg_ambiguity("4/0 AWG") is None
    assert awg_ambiguity("4 0 AWG") is not None
    assert awg_ambiguity("4O AWG") is not None
