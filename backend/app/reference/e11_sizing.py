"""Conductor sizing from the tables, one requirement at a time - the Python
twin of packages/e11-calc/src/sizing.ts, same names, same arithmetic order,
same rounding, so the two agree to the last digit on the shared vectors.

Every function answers with a dict carrying the size and its page, or a
blank: {"value": None, "reason": ..., "ask": {...}} where the ask names the
value a person can supply.
"""
from __future__ import annotations

import math
from typing import Any

from .e11_tables import E11Tables, usable

FT_PER_M = 1 / 0.3048
#: One circular mil in mm²: (0.0254 mm)² × π / 4. A unit conversion, not a table value.
MM2_PER_CIRCULAR_MIL = 0.0005067
#: Standard metric conductor sizes (IEC 60228). An industry standard, not E-11 data.
METRIC_STANDARD_MM2 = [0.5, 0.75, 1, 1.5, 2.5, 4, 6, 10, 16, 25, 35, 50, 70, 95, 120, 150, 185, 240, 300]


def round_half_up(v: float, digits: int = 1) -> float:
    """Half up, like the TypeScript copy (Python's round() is half-even)."""
    f = 10 ** digits
    return math.floor(v * f + 0.5) / f


def length_ft(length: float, unit: str) -> float:
    return length * FT_PER_M if unit == "m" else length


def to_mm2(circular_mils: float) -> float:
    return round_half_up(circular_mils * MM2_PER_CIRCULAR_MIL, 2)


def nearest_metric(mm2: float) -> float | None:
    for s in METRIC_STANDARD_MM2:
        if s >= mm2 - 1e-9:
            return s
    return None


def is_blank(x: Any) -> bool:
    return isinstance(x, dict) and x.get("value", 0) is None and "value" in x and isinstance(x.get("reason"), str)


def blank(reason: str, ask: dict | None = None) -> dict:
    out: dict = {"value": None, "reason": reason}
    if ask:
        out["ask"] = ask
    return out


def _src(t: dict, page: int) -> dict:
    return {"table": t["id"], "title": t["title"], "page": page}


def required_circular_mils(voltage: float, current: float, l_ft: float, drop_percent: float, tables: E11Tables, own_k: float | None = None) -> dict:
    """CM = K × I × L / E, with L as the page defines it (round trip or one way)."""
    constants = usable(tables, "constants")
    ask = {"field": "own.k", "unit": None, "prompt": "The constants table (K and the formula) is not confirmed under Reference. Type K for copper from the page."}
    if own_k is not None:
        k = own_k
        round_trip = constants["length_definition"] == "round_trip" if constants else True
        source: dict = {"by": "you"}
    elif constants:
        k = constants["values"]["K_copper"]["value"]
        round_trip = constants["length_definition"] == "round_trip"
        source = _src(constants, constants["values"]["K_copper"]["page"])
    else:
        return blank("The constants table (K and the formula) is not confirmed, so the required circular mils cannot be computed.", ask)
    if voltage <= 0 or current <= 0 or l_ft <= 0 or drop_percent <= 0:
        return blank("Voltage, current, length and the drop limit must all be above zero.")
    e_drop = voltage * drop_percent / 100
    l = 2 * l_ft if round_trip else l_ft
    return {"value": round_half_up(k * current * l / e_drop, 1), "k": k, "round_trip": round_trip, "source": source}


def size_for_circular_mils(cm: float, tables: E11Tables) -> dict:
    """The smallest listed size whose area is at least the required circular mils."""
    table = usable(tables, "circular_mils")
    if not table:
        return blank("The circular-mils table is not confirmed under Reference, so no size can be read for the required area.")
    rows = sorted(table["rows"], key=lambda r: r["circular_mils"])
    for r in rows:
        if r["circular_mils"] >= cm - 1e-9:
            return {"size_awg": r["size_awg"], "circular_mils": r["circular_mils"], "source": _src(table, r["page"])}
    largest = rows[-1]
    return blank(f"{_fmt(cm)} circular mils is more than the largest listed size, {largest['size_awg']} AWG at {_fmt(largest['circular_mils'])} circular mils (page {largest['page']}); conductors in parallel are needed.")


def _fmt(v: float) -> str:
    """Numbers as JavaScript prints them: no trailing .0."""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def size_from_printed_grid(voltage: float, current: float, l_ft: float, drop_percent: float, tables: E11Tables) -> dict:
    """The printed voltage-drop grid, only at its own nominal voltage."""
    table_id = "voltage_drop_3pct" if drop_percent == 3 else "voltage_drop_10pct" if drop_percent == 10 else None
    if not table_id:
        return {"size_awg": None, "applicable": False, "reason": f"No printed table for a {_fmt(drop_percent)} % limit, so the circular-mils formula and table are used instead."}
    grid = usable(tables, table_id)
    if not grid:
        return {"size_awg": None, "applicable": False, "reason": f"The printed {_fmt(drop_percent)} % table is not confirmed under Reference, so the circular-mils formula and table are used instead."}
    if abs(grid["nominal_voltage"] - voltage) > 1e-9:
        return {"size_awg": None, "applicable": False, "reason": f"No printed table for {_fmt(voltage)} V (the {_fmt(drop_percent)} % table is for {_fmt(grid['nominal_voltage'])} V), so the circular-mils formula and table are used instead."}
    l = l_ft / FT_PER_M if grid["length_unit"] == "m" else l_ft
    if grid["length_definition"] == "round_trip":
        l *= 2
    rows = sorted(grid["rows"], key=lambda r: r["current"])
    row = next((r for r in rows if r["current"] >= current - 1e-9), None)
    if row is None:
        return blank(f"The printed {_fmt(drop_percent)} % table on page {grid['source']['page']} stops at {_fmt(rows[-1]['current'])} A, so the circular-mils formula and table are used instead.")
    lengths = sorted(grid["lengths"])
    length = next((x for x in lengths if x >= l - 1e-9), None)
    if length is None:
        return blank(f"The printed {_fmt(drop_percent)} % table on page {row['page']} stops at {_fmt(lengths[-1])} {grid['length_unit']}, so the circular-mils formula and table are used instead.")
    size = row["sizes"].get(_fmt(length))
    if not size:
        return blank(f"The printed {_fmt(drop_percent)} % table on page {row['page']} has no size for {_fmt(row['current'])} A at {_fmt(length)} {grid['length_unit']}, so the circular-mils formula and table are used instead.")
    return {"size_awg": size, "source": _src(grid, row["page"]), "printed_current": row["current"], "printed_length": length}


def bundling_factor(count: int, tables: E11Tables, own: float | None = None) -> dict:
    ask = {"field": "own.bundling_factor", "unit": None, "prompt": f"Type the correction factor for {count} bundled conductors from the page (1 if the page applies none)."}
    if own is not None:
        return {"factor": own, "source": {"by": "you"}}
    table = usable(tables, "bundling_factors")
    if not table:
        return blank("The bundling table is not confirmed under Reference.", ask)
    for r in table["rows"]:
        if count >= r["min_conductors"] and (r["max_conductors"] is None or count <= r["max_conductors"]):
            return {"factor": r["factor"], "source": _src(table, r["page"])}
    return blank(f"The bundling table on page {table['source']['page']} has no row for {count} conductors.", ask)


def _ampacity_table(engine_space: bool, tables: E11Tables) -> dict | None:
    return usable(tables, "ampacity_inside_engine_space" if engine_space else "ampacity_outside_engine_space")


def _ampacity_ask(rating_c: float, engine_space: bool) -> dict:
    return {"field": "own.ampacity_a", "unit": "A", "prompt": f"Type the allowable current for that size at {_fmt(rating_c)} °C {'inside' if engine_space else 'outside'} an engine space, from the page."}


def _by_area(rows: list[dict], tables: E11Tables) -> list[dict] | None:
    cm_table = usable(tables, "circular_mils")
    if not cm_table:
        return None
    area = {r["size_awg"]: r["circular_mils"] for r in cm_table["rows"]}
    if any(r["size_awg"] not in area for r in rows):
        return None
    return sorted(rows, key=lambda r: area[r["size_awg"]])


def size_for_ampacity(current: float, rating_c: float, engine_space: bool, bundled: int, tables: E11Tables, own: dict | None = None) -> dict:
    """The smallest size whose derated ampacity carries the current."""
    own = own or {}
    factor = bundling_factor(bundled, tables, own.get("bundling_factor"))
    if is_blank(factor):
        return factor
    table = _ampacity_table(engine_space, tables)
    ask = _ampacity_ask(rating_c, engine_space)
    if not table:
        return blank(f"The ampacity table for {'inside' if engine_space else 'outside'} engine spaces is not confirmed under Reference.", ask)
    col = _fmt(rating_c)
    if col not in table["columns"]:
        return blank(f"The ampacity table on page {table['source']['page']} has no {col} °C column (it has {', '.join(table['columns'].keys())} °C).", ask)
    rows = _by_area(table["rows"], tables)
    if rows is None:
        return blank("The circular-mils table is needed to order sizes by area and is not confirmed under Reference.")
    largest: dict | None = None
    for r in rows:
        a = r["values"].get(col)
        if a is None:
            continue
        pick = {"size_awg": r["size_awg"], "ampacity_a": a, "derated_a": round_half_up(a * factor["factor"], 1), "bundling_factor": factor["factor"], "source": _src(table, r["page"]), "factor_source": factor["source"]}
        if pick["derated_a"] >= current - 1e-9:
            return pick
        largest = pick
    if not largest:
        return blank(f"The {col} °C column on page {table['source']['page']} has no values.", ask)
    return {
        "size_awg": None, "exceeded": True, "bundling_factor": factor["factor"], "source": largest["source"], "factor_source": factor["source"],
        "largest": {"size_awg": largest["size_awg"], "ampacity_a": largest["ampacity_a"], "derated_a": largest["derated_a"]},
        "reason": f"The largest listed size, {largest['size_awg']} AWG, carries {_fmt(largest['derated_a'])} A after derating (page {largest['source']['page']}), less than {_fmt(current)} A; conductors in parallel are needed.",
    }


def ampacity_of(size_awg: str, rating_c: float, engine_space: bool, tables: E11Tables) -> dict:
    """The allowable current of one named size, for checking a size chosen by another step."""
    table = _ampacity_table(engine_space, tables)
    ask = _ampacity_ask(rating_c, engine_space)
    if not table:
        return blank(f"The ampacity table for {'inside' if engine_space else 'outside'} engine spaces is not confirmed under Reference.", ask)
    col = _fmt(rating_c)
    if col not in table["columns"]:
        return blank(f"The ampacity table on page {table['source']['page']} has no {col} °C column.", ask)
    row = next((r for r in table["rows"] if r["size_awg"] == size_awg), None)
    a = row["values"].get(col) if row else None
    if row is None or a is None:
        return blank(f"The ampacity table on page {table['source']['page']} has no {col} °C value for {size_awg} AWG.", ask)
    return {"ampacity_a": a, "source": _src(table, row["page"])}


def parallel_conductors(required_cm: float | None, required_a: float, factor: float, rating_c: float, engine_space: bool, tables: E11Tables, max_count: int = 4) -> dict:
    """The fewest conductors, then the smallest listed size, that together meet the area and the current."""
    cm_table = usable(tables, "circular_mils")
    if not cm_table:
        return blank("The circular-mils table is not confirmed under Reference.")
    amp = _ampacity_table(engine_space, tables)
    col = _fmt(rating_c)
    rows = sorted(cm_table["rows"], key=lambda r: r["circular_mils"])
    for n in range(2, max_count + 1):
        for r in rows:
            cm_ok = required_cm is None or n * r["circular_mils"] >= required_cm - 1e-9
            a = None
            if amp:
                arow = next((x for x in amp["rows"] if x["size_awg"] == r["size_awg"]), None)
                a = arow["values"].get(col) if arow else None
            derated = None if a is None else round_half_up(n * a * factor, 1)
            amp_ok = derated is not None and derated >= required_a - 1e-9
            if cm_ok and amp_ok:
                return {"count": n, "size_awg": r["size_awg"], "circular_mils_each": r["circular_mils"], "ampacity_each_a": a, "derated_total_a": derated, "source": _src(cm_table, r["page"])}
    extra = f" and {_fmt(required_cm)} circular mils" if required_cm is not None else ""
    return blank(f"Even {max_count} conductors of the largest listed size in parallel do not meet {_fmt(required_a)} A{extra}.")


def compare_sizes(a: str, b: str, tables: E11Tables) -> float | None:
    cm_table = usable(tables, "circular_mils")
    if not cm_table:
        return None
    area = {r["size_awg"]: r["circular_mils"] for r in cm_table["rows"]}
    if a not in area or b not in area:
        return None
    return area[a] - area[b]


def circular_mils_of(size_awg: str, tables: E11Tables) -> dict | None:
    cm_table = usable(tables, "circular_mils")
    row = next((r for r in cm_table["rows"] if r["size_awg"] == size_awg), None) if cm_table else None
    if not cm_table or not row:
        return None
    return {"circular_mils": row["circular_mils"], "mm2": row.get("mm2"), "source": _src(cm_table, row["page"])}
