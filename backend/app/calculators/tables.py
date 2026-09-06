"""Reference tables for conductor calculations.

Values are typical published figures and are labelled as such in results.
They must be verified against the applicable standard and the actual wire
specification before use.
"""
from __future__ import annotations

# Copper conductor DC resistance at 20 °C, ohms per 1000 ft (NEC Chapter 9 Table 8, uncoated copper).
AWG_OHMS_PER_KFT_CU = {
    "4/0": 0.04901, "3/0": 0.06180, "2/0": 0.07793, "1/0": 0.09827, "1": 0.1239, "2": 0.1563, "3": 0.1970,
    "4": 0.2485, "6": 0.3951, "8": 0.6282, "10": 0.9989, "12": 1.588, "14": 2.525, "16": 4.016, "18": 6.385,
    "20": 10.15, "22": 16.14,
}
# Aluminium is ~1.64x copper resistance.
AL_FACTOR = 1.64

# Resistivity Ω·mm²/m at 20 °C.
RHO_CU = 0.01724
RHO_AL = 0.0282

# Typical allowable ampacity, 105 °C insulation, single conductor outside engine spaces
# (ABYC E-11 style table, commonly published). Engine-space derating factor applied separately.
AWG_AMPACITY_105C = {
    "18": 20, "16": 25, "14": 35, "12": 45, "10": 60, "8": 80, "6": 120, "4": 160, "3": 180, "2": 210,
    "1": 245, "1/0": 285, "2/0": 330, "3/0": 385, "4/0": 445,
}
ENGINE_SPACE_DERATE_105C = 0.85

# Typical ampacity for metric marine cable (approximate, 105 °C, free air).
MM2_AMPACITY_105C = {
    1.0: 20, 1.5: 25, 2.5: 35, 4: 45, 6: 60, 10: 80, 16: 110, 25: 145, 35: 180, 50: 230, 70: 290, 95: 350, 120: 410, 150: 470,
}

STANDARD_FUSE_SIZES = [1, 2, 3, 5, 7.5, 10, 15, 20, 25, 30, 35, 40, 50, 60, 70, 80, 90, 100, 110, 125, 150, 175, 200, 225, 250, 300, 350, 400, 450, 500, 600, 700, 800]
STANDARD_BREAKER_SIZES = [5, 10, 15, 16, 20, 25, 30, 32, 40, 50, 60, 63, 70, 80, 100, 125, 150, 175, 200, 225, 250, 300, 400]

AWG_MM2 = {
    "4/0": 107.2, "3/0": 85.0, "2/0": 67.4, "1/0": 53.5, "1": 42.4, "2": 33.6, "3": 26.7, "4": 21.2, "6": 13.3,
    "8": 8.37, "10": 5.26, "12": 3.31, "14": 2.08, "16": 1.31, "18": 0.823, "20": 0.518, "22": 0.326,
}


def next_standard(value: float, table: list[float]) -> float | None:
    for s in table:
        if s >= value - 1e-9:
            return s
    return None


def prev_standard(value: float, table: list[float]) -> float | None:
    best = None
    for s in table:
        if s <= value + 1e-9:
            best = s
    return best
