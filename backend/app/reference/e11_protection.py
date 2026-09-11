"""Overcurrent protection for the conductor the sizing step chose - the
Python twin of packages/e11-calc/src/protection.ts.

A fuse protects the conductor, so it may never exceed the conductor's
derated ampacity; it must also be at least the load times its load-type
factor, rounded up to a standard size. Its interrupting rating must exceed
the source's short-circuit current, which comes from the battery datasheet -
typed by the person, never estimated here.
"""
from __future__ import annotations

from ..calculators import tables as T
from .e11_sizing import blank, round_half_up, _fmt
from .e11_tables import E11Tables, usable

GUIDANCE_LABEL = "industry guidance, verify with the maker"
DEFAULT_PROFILE = {"label": "Load", "factor": 1.25, "surge_note": "No load type given; 125 % of the continuous load is used.", "char": "per the equipment maker"}


def fuse_for_conductor(load_a: float, load_type: str, conductor_ampacity_a: float, manufacturer_fuse_a: float | None = None, profiles: dict | None = None, sizes: list[float] | None = None) -> dict:
    # Imported here: calculators.modules registers the circuit calculator,
    # which imports this module; a top-level import would be a cycle.
    from ..calculators.modules import DEVICE_PROFILES

    profiles = profiles or DEVICE_PROFILES
    sizes = sizes or T.STANDARD_FUSE_SIZES
    profile = profiles.get(load_type, DEFAULT_PROFILE)
    mfr = manufacturer_fuse_a if manufacturer_fuse_a is not None and manufacturer_fuse_a > 0 else None
    minimum = mfr if mfr is not None else round_half_up(load_a * profile["factor"], 2)
    standard = T.next_standard(minimum, sizes)
    max_for = T.prev_standard(conductor_ampacity_a, sizes)
    fits = standard is not None and standard <= conductor_ampacity_a + 1e-9
    pick = {
        "min_a": minimum, "fuse_a": standard if fits else None, "fits_conductor": fits, "conductor_ampacity_a": conductor_ampacity_a, "max_for_conductor_a": max_for,
        "characteristic": profile["char"], "surge_note": profile["surge_note"], "guidance": GUIDANCE_LABEL, "manufacturer_a": mfr,
    }
    if not fits:
        if standard is None:
            pick["reason"] = f"{_fmt(minimum)} A is above the largest standard fuse size ({_fmt(sizes[-1])} A)."
        else:
            pick["reason"] = f"A {_fmt(standard)} A fuse (the next standard size above {_fmt(minimum)} A) would exceed the conductor's {_fmt(conductor_ampacity_a)} A after derating; the largest size this conductor allows is {_fmt(max_for) if max_for is not None else 'none'} A, below the load's minimum. Use a larger conductor."
    return pick


def interrupting_check(short_circuit_a: float | None, load_type: str, tables: E11Tables, own: float | None = None) -> dict:
    sc = own if own is not None else short_circuit_a
    ask = {"field": "own.short_circuit_a", "unit": "A", "prompt": "Type the prospective short-circuit current of the source (the battery bank) from its datasheet, in A. The fuse's interrupting rating must be above it."}
    if sc is None or sc <= 0:
        return blank("The source's short-circuit current was not given, so no fuse class can be checked for interrupting capacity.", ask)
    table = usable(tables, "fuse_classes")
    if not table or not table["rows"]:
        return blank("No fuse classes have been entered yet. Add each class you use, with its interrupting rating from the datasheet, under Reference.")
    classes = [
        {"class": r["class"], "interrupting_rating_a": r["interrupting_rating_a"], "voltage_rating_v": r.get("voltage_rating_v"), "suits_load": load_type in r["suits"], "source": r["source"]}
        for r in table["rows"] if r["interrupting_rating_a"] >= sc - 1e-9
    ]
    classes.sort(key=lambda c: (not c["suits_load"], c["interrupting_rating_a"]))
    out = {"required_a": sc, "source": {"by": "you"} if own is not None else {"given": True}, "classes": classes}
    if not classes:
        out["reason"] = f"No entered fuse class has an interrupting rating of at least {_fmt(sc)} A."
    return out
