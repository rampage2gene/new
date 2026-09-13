"""The fittings for the conductor the sizing step chose - the Python twin of
packages/e11-calc/src/fittings.ts: the cable's outside diameter, the
heat-shrink tubing that fits it, the lug for the stud it lands on with its
crimp die, and the counts for the set.

None of this is E-11: cable diameters, tubing sizes and lug parts differ by
maker, so they come from three catalog tables the owner types, or from the
person when a table does not cover the case. Nothing typical is carried here.
"""
from __future__ import annotations

import re

from .e11_sizing import _fmt, blank, is_blank, round_half_up
from .e11_tables import E11Tables, usable

MM_PER_IN = 25.4


def to_mm(value: float, unit: str) -> float:
    return value * MM_PER_IN if unit == "in" else value


def normalize_stud(stud: str | None) -> str:
    """'5/16"', ' M8 ', '3/8 in' and '5/16' compare equal."""
    s = re.sub(r'["”]', "", str(stud or "")).lower().strip()
    s = re.sub(r"\s*in(ch)?$", "", s)
    return re.sub(r"\s+", "", s)


def _catalog_source(t: dict, page: int | None) -> dict:
    out = {"table": t["id"], "title": t["title"], "document": t["source"]["document"]}
    if page is not None:
        out["page"] = page
    return out


def cable_outside_diameter(size_awg: str, tables: E11Tables, own: float | None = None) -> dict:
    ask = {"field": "own.cable_od_mm", "unit": "mm", "prompt": f"Type the outside diameter of {size_awg} AWG cable from the cable maker's catalog, in mm."}
    if own is not None and own > 0:
        return {"value": own, "unit": "mm", "mm": own, "source": {"by": "you"}}
    t = usable(tables, "cable_dimensions")
    if not t:
        return blank("No cable dimensions table is confirmed under Reference, so the cable's outside diameter is not known.", ask)
    row = next((r for r in t["rows"] if r["size_awg"] == size_awg), None)
    if not row:
        return blank(f"The cable dimensions table has no {size_awg} AWG row.", ask)
    return {"value": row["outside_diameter"], "unit": t["diameter_unit"], "mm": round_half_up(to_mm(row["outside_diameter"], t["diameter_unit"]), 3), "source": _catalog_source(t, row.get("page"))}


def heat_shrink_for(cable_od_mm: float | None, barrel_od_mm: float | None, tables: E11Tables, own: str | None = None) -> dict:
    """Tubing that slides over the cable (and the lug barrel, when known) and
    shrinks below the cable so it grips: the smallest such supplied size,
    adhesive-lined preferred when both exist."""
    ask = {"field": "own.heat_shrink_size", "unit": None, "prompt": "Type the heat-shrink size you use for this cable, from the tubing maker's catalog.", "kind": "text"}
    if own:
        return {"size": own, "supplied_id": None, "recovered_id": None, "unit": None, "adhesive": None, "source": {"by": "you"}}
    t = usable(tables, "heat_shrink")
    if not t:
        return blank("No heat-shrink table is confirmed under Reference, so no tubing size can be picked.", ask)
    if cable_od_mm is None:
        return blank("The cable's outside diameter is not known, so no tubing size can be picked.", ask)
    unit = t["diameter_unit"]
    over = max(cable_od_mm, barrel_od_mm or 0)
    fits = [r for r in t["rows"] if to_mm(r["supplied_id"], unit) >= over - 1e-9 and to_mm(r["recovered_id"], unit) <= cable_od_mm + 1e-9]
    if not fits:
        listed = ", ".join(f"{r['size']} ({_fmt(r['supplied_id'])}→{_fmt(r['recovered_id'])} {unit})" for r in t["rows"])
        return blank(f"No tubing in the table both slides over {_fmt(round_half_up(over, 2))} mm and shrinks below the cable's {_fmt(round_half_up(cable_od_mm, 2))} mm. Listed: {listed}.", ask)
    fits.sort(key=lambda r: (to_mm(r["supplied_id"], unit), not r.get("adhesive")))
    r = fits[0]
    return {"size": r["size"], "supplied_id": r["supplied_id"], "recovered_id": r["recovered_id"], "unit": unit, "adhesive": r.get("adhesive"), "source": _catalog_source(t, r.get("page"))}


def lug_for(size_awg: str, stud: str | None, tables: E11Tables, own: dict | None = None) -> dict:
    own = own or {}
    given = stud or own.get("stud")
    wanted = normalize_stud(given)
    ask_part = {"field": "own.lug_part", "unit": None, "prompt": f"Type the lug part for {size_awg} AWG on a {given or '?'} stud, from the lug maker's catalog.", "kind": "text"}
    ask_die = {"field": "own.crimp_die", "unit": None, "prompt": "Type the crimp die or setting for this lug and cable, from your crimper's chart.", "kind": "text"}
    if own.get("lug_part"):
        pick = {"part": own["lug_part"], "stud": given or "", "crimp_die": own.get("crimp_die"), "barrel_od_mm": None, "source": {"by": "you"}}
        if own.get("crimp_die"):
            pick["die_source"] = {"by": "you"}
        else:
            pick["die_reason"] = f"No crimp die is known for {own['lug_part']}."
            pick["die_ask"] = ask_die
        return pick
    if not wanted:
        return blank("No stud size was given, so no lug can be picked. Type the terminal stud the lug lands on (5/16, 3/8, M8, M10…).", {"field": "own.stud", "unit": None, "prompt": "Type the terminal stud size the lug lands on, as the lug catalog names it (5/16, 3/8, M8, M10…).", "kind": "text"})
    t = usable(tables, "lugs")
    if not t:
        return blank("No lugs table is confirmed under Reference, so no lug part can be picked.", ask_part)
    rows = [r for r in t["rows"] if r["size_awg"] == size_awg]
    if not rows:
        return blank(f"The lugs table has no {size_awg} AWG row.", ask_part)
    row = next((r for r in rows if normalize_stud(r["stud"]) == wanted), None)
    if not row:
        return blank(f"The lugs table lists {size_awg} AWG only for studs {', '.join(r['stud'] for r in rows)}, not {given}.", ask_part)
    unit = t.get("diameter_unit") or "mm"
    pick = {
        "part": row["part"], "stud": row["stud"], "crimp_die": own.get("crimp_die") or row.get("crimp_die"),
        "barrel_od_mm": round_half_up(to_mm(row["barrel_od"], unit), 3) if row.get("barrel_od") is not None else None,
        "source": _catalog_source(t, row.get("page")),
    }
    if own.get("crimp_die"):
        pick["die_source"] = {"by": "you"}
    elif row.get("crimp_die"):
        pick["die_source"] = pick["source"]
    else:
        pick["die_reason"] = f"The lugs table gives no crimp die for {row['part']}."
        pick["die_ask"] = ask_die
    return pick


def fittings_for(size_awg: str | None, parallel: int, stud: str | None, loop_length: float, length_unit: str, tables: E11Tables, own: dict | None = None) -> dict:
    """The fittings block of a circuit result, plus the blanks and steps it adds."""
    own = own or {}
    blanks: list[dict] = []
    steps: list[str] = []
    f = {
        "cable_od": {"value": None, "unit": None, "mm": None},
        "heat_shrink": {"size": None, "supplied_id": None, "recovered_id": None, "unit": None, "adhesive": None},
        "lug": {"part": None, "stud": None, "crimp_die": None},
        "quantities": None,
    }
    if not size_awg:
        reason = "No conductor size was settled, so no fittings can be picked."
        for key in ("cable_od", "heat_shrink", "lug"):
            f[key]["reason"] = reason
        return {"fittings": f, "blanks": blanks, "steps": steps}

    od = cable_outside_diameter(size_awg, tables, own.get("cable_od_mm"))
    od_mm = None
    if is_blank(od):
        f["cable_od"]["reason"] = od["reason"]
        blanks.append({"field": "fittings.cable_od", "reason": od["reason"], "ask": od["ask"]})
    else:
        od_mm = od["mm"]
        f["cable_od"] = {"value": od["value"], "unit": od["unit"], "mm": od["mm"], "source": od["source"]}

    lug = lug_for(size_awg, stud, tables, own)
    barrel_mm = None
    if is_blank(lug):
        f["lug"] = {"part": None, "stud": stud or own.get("stud"), "crimp_die": None, "reason": lug["reason"]}
        blanks.append({"field": "fittings.lug.part", "reason": lug["reason"], "ask": lug["ask"]})
    else:
        barrel_mm = lug["barrel_od_mm"]
        f["lug"] = {"part": lug["part"], "stud": lug["stud"], "crimp_die": lug["crimp_die"], "source": lug["source"]}
        if lug.get("die_source"):
            f["lug"]["die_source"] = lug["die_source"]
        if lug.get("die_reason"):
            f["lug"]["die_reason"] = lug["die_reason"]
        if lug.get("die_ask"):
            blanks.append({"field": "fittings.lug.crimp_die", "reason": lug.get("die_reason") or "The crimp die is not known.", "ask": lug["die_ask"]})

    hs = heat_shrink_for(od_mm, barrel_mm, tables, own.get("heat_shrink_size"))
    if is_blank(hs):
        f["heat_shrink"]["reason"] = hs["reason"]
        blanks.append({"field": "fittings.heat_shrink.size", "reason": hs["reason"], "ask": hs["ask"]})
    else:
        f["heat_shrink"] = {"size": hs["size"], "supplied_id": hs["supplied_id"], "recovered_id": hs["recovered_id"], "unit": hs["unit"], "adhesive": hs["adhesive"], "source": hs["source"]}

    n = max(1, int(parallel))
    f["quantities"] = {"cables": n, "lugs": 2 * n, "heat_shrink_pieces": 2 * n, "cable_length": round_half_up(n * loop_length, 2), "length_unit": length_unit, "note": "Counts for the set: two lugs and two pieces of tubing per cable; cable to buy is the loop length per cable, plus your own routing allowance."}
    od_text = f"outside diameter {_fmt(f['cable_od']['value'])} {f['cable_od']['unit']}" if f["cable_od"]["mm"] is not None else "outside diameter not known"
    hs_text = f"heat shrink {f['heat_shrink']['size']}" if f["heat_shrink"]["size"] else "no heat shrink picked"
    lug_text = f"lug {f['lug']['part']}{', die ' + f['lug']['crimp_die'] if f['lug']['crimp_die'] else ''}" if f["lug"]["part"] else "no lug picked"
    steps.append(f"Fittings for {f'{n} × ' if n > 1 else ''}{size_awg} AWG: {od_text}; {hs_text}; {lug_text}. {n} cable{'s' if n > 1 else ''} × {_fmt(loop_length)} {length_unit} = {_fmt(f['quantities']['cable_length'])} {length_unit} to buy, {2 * n} lugs, {2 * n} pieces of tubing.")
    return {"fittings": f, "blanks": blanks, "steps": steps}
