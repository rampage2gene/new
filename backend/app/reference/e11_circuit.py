"""The whole procedure for one circuit - the Python twin of
packages/e11-calc/src/circuit.ts, same keys, same steps, same blanks.

Order, on engineering grounds: the conductor must satisfy two independent
requirements and the larger size wins - carry the current without
overheating (ampacity, derated for engine space and bundling) and deliver
the voltage (the drop limit, from the printed grid where it applies or the
circular-mil formula for any voltage). When no single listed size meets
both, conductors are paralleled. The fuse is then sized to the conductor.
Every step either cites a page, says "you", or is a blank with an ask.
"""
from __future__ import annotations

from .e11_cheatsheet import reminders_for
from .e11_protection import GUIDANCE_LABEL, fuse_for_conductor, interrupting_check
from .e11_sizing import (
    _fmt, ampacity_of, bundling_factor, circular_mils_of, compare_sizes, is_blank, length_ft, nearest_metric,
    parallel_conductors, required_circular_mils, round_half_up, size_for_ampacity, size_for_circular_mils,
    size_from_printed_grid, to_mm2,
)
from .e11_tables import E11Tables


def _cite(s: dict | None) -> str:
    if not s:
        return ""
    if "by" in s:
        return " (entered by you)"
    return f" ({s.get('title') or s.get('table')}, page {s['page']})"


def size_circuit(inputs: dict, tables: E11Tables, own: dict | None = None, sheet: dict | None = None) -> dict:
    own = own or {}
    steps: list[str] = []
    blanks: list[dict] = []

    def add_blank(field: str, reason: str, ask: dict | None = None) -> None:
        blanks.append({"field": field, "reason": reason, "ask": ask} if ask else {"field": field, "reason": reason})

    voltage = float(inputs["system_voltage"])
    current = float(inputs["current"])
    l_ft = length_ft(float(inputs["length"]), inputs.get("length_unit", "m"))
    drop = float(inputs["max_drop_percent"])
    rating = float(inputs.get("insulation_rating_c", 105))
    engine = bool(inputs.get("engine_space", False))
    bundled = max(2, int(inputs.get("bundled_conductors") or 2))
    load_type = str(inputs.get("load_type") or "")

    # 1. Voltage drop: the circular-mil formula, for any voltage.
    cm = required_circular_mils(voltage, current, l_ft, drop, tables, own.get("k"))
    vd_size = None
    vd_source = None
    vd_reason = None
    cm_exceeded = False
    cm_required = None
    if is_blank(cm):
        add_blank("conductor.voltage_drop.cm_required", cm["reason"], cm.get("ask"))
        vd_reason = cm["reason"]
    else:
        cm_required = cm["value"]
        e_drop = round_half_up(voltage * drop / 100, 3)
        l = 2 * l_ft if cm["round_trip"] else l_ft
        by_you = " L taken as the round trip until the constants table is confirmed." if "by" in cm["source"] else ""
        steps.append(f"Voltage drop: allowed {_fmt(e_drop)} V ({_fmt(drop)} % of {_fmt(voltage)} V). CM = K × I × L / E = {_fmt(cm['k'])} × {_fmt(current)} × {_fmt(round_half_up(l, 1))} ft{' (round trip)' if cm['round_trip'] else ''} / {_fmt(e_drop)} = {_fmt(cm['value'])} circular mils{_cite(cm['source'])}.{by_you}")
        pick = size_for_circular_mils(cm["value"], tables)
        if is_blank(pick):
            if "parallel" in pick["reason"]:
                cm_exceeded = True
                vd_reason = pick["reason"]
            else:
                add_blank("conductor.voltage_drop.size_awg", pick["reason"])
                vd_reason = pick["reason"]
            steps.append(pick["reason"])
        else:
            vd_size = pick["size_awg"]
            vd_source = pick["source"]
            steps.append(f"Smallest listed size with at least {_fmt(cm['value'])} circular mils: {pick['size_awg']} AWG ({_fmt(pick['circular_mils'])} circular mils){_cite(pick['source'])}.")

    # 2. The printed grid, where it applies.
    grid = size_from_printed_grid(voltage, current, l_ft, drop, tables)
    printed_size = None
    printed_source = None
    printed_reason = None
    if "applicable" in grid:
        printed_reason = grid["reason"]
    elif is_blank(grid):
        printed_reason = grid["reason"]
        steps.append(grid["reason"])
    else:
        printed_size = grid["size_awg"]
        printed_source = grid["source"]
        steps.append(f"Printed {_fmt(drop)} % table at {_fmt(voltage)} V: {_fmt(grid['printed_current'])} A row, {_fmt(grid['printed_length'])} column gives {grid['size_awg']} AWG{_cite(grid['source'])}.")

    # 3. Ampacity with derating.
    amp = size_for_ampacity(current, rating, engine, bundled, tables, own)
    amp_size = None
    amp_a = None
    factor = None
    amp_source = None
    amp_reason = None
    amp_exceeded = False
    derated_a = None
    if is_blank(amp):
        f = bundling_factor(bundled, tables, own.get("bundling_factor"))
        if not is_blank(f):
            factor = f["factor"]
        ask = amp.get("ask")
        if ask and ask["field"] == "own.ampacity_a" and own.get("ampacity_a") is not None and vd_size and factor is not None:
            amp_a = float(own["ampacity_a"])
            derated_a = round_half_up(amp_a * factor, 1)
            amp_source = {"by": "you"}
            if derated_a >= current - 1e-9:
                amp_size = vd_size
                steps.append(f"Ampacity: {vd_size} AWG carries {_fmt(amp_a)} A × {_fmt(factor)} = {_fmt(derated_a)} A after derating (entered by you), enough for {_fmt(current)} A.")
            else:
                amp_reason = f"{vd_size} AWG carries only {_fmt(derated_a)} A after derating (entered by you), less than {_fmt(current)} A; a larger conductor is needed - type its allowable current."
                add_blank("conductor.ampacity.size_awg", amp_reason, ask)
                steps.append(amp_reason)
        else:
            amp_reason = amp["reason"]
            add_blank("conductor.ampacity.size_awg", amp["reason"], ask)
            steps.append(amp["reason"])
    elif amp.get("exceeded"):
        amp_exceeded = True
        factor = amp["bundling_factor"]
        amp_reason = amp["reason"]
        steps.append(f"Bundling factor {_fmt(factor)} for {bundled} conductors{_cite(amp['factor_source'])}. {amp['reason']}")
    else:
        amp_size = amp["size_awg"]
        amp_a = amp["ampacity_a"]
        derated_a = amp["derated_a"]
        factor = amp["bundling_factor"]
        amp_source = amp["source"]
        steps.append(f"Ampacity at {_fmt(rating)} °C {'inside' if engine else 'outside'} an engine space, bundling factor {_fmt(factor)} for {bundled} conductors{_cite(amp['factor_source'])}: smallest size carrying {_fmt(current)} A is {amp['size_awg']} AWG ({_fmt(amp['ampacity_a'])} A × {_fmt(factor)} = {_fmt(amp['derated_a'])} A){_cite(amp['source'])}.")

    # 4. The larger requirement wins; parallel conductors when a single size cannot.
    size = None
    parallel = 1
    governed = None
    conductor_ampacity_a = None
    need_parallel = cm_exceeded or amp_exceeded
    if need_parallel and factor is not None:
        p = parallel_conductors(cm_required if cm_exceeded else None, current, factor, rating, engine, tables)
        if is_blank(p):
            add_blank("conductor.size_awg", p["reason"])
            steps.append(p["reason"])
        else:
            size = p["size_awg"]
            parallel = p["count"]
            governed = "voltage_drop" if cm_exceeded else "ampacity"
            conductor_ampacity_a = p["derated_total_a"]
            if cm_exceeded:
                vd_source = p["source"]
            total = f", {_fmt(p['derated_total_a'])} A after derating" if p["derated_total_a"] is not None else ""
            steps.append(f"{p['count']} × {p['size_awg']} AWG in parallel: {p['count']} × {_fmt(p['circular_mils_each'])} circular mils{total}{_cite(p['source'])}.")
    elif vd_size and amp_size:
        candidates = [(vd_size, "voltage_drop"), (amp_size, "ampacity")]
        if printed_size:
            candidates.append((printed_size, "printed_table"))
        best = candidates[0]
        for c in candidates[1:]:
            cmp = compare_sizes(c[0], best[0], tables)
            if cmp is not None and cmp > 0:
                best = c
        size, governed = best
        if printed_size and vd_size and printed_size != vd_size:
            steps.append(f"The printed table gives {printed_size} AWG and the formula {vd_size} AWG; the larger is used.")
        steps.append(f"Larger of the two requirements: {size} AWG (governed by {governed.replace('_', ' ')}).")
        a = ampacity_of(size, rating, engine, tables)
        if not is_blank(a) and factor is not None:
            conductor_ampacity_a = round_half_up(a["ampacity_a"] * factor, 1)
        elif size == vd_size and derated_a is not None:
            conductor_ampacity_a = derated_a

    # 5. The size in both units, and the drop at that size.
    mm2 = None
    metric = None
    drop_v = None
    drop_pct = None
    drop_reason = None
    if size:
        area = circular_mils_of(size, tables)
        if area:
            mm2 = area["mm2"] if area["mm2"] is not None else to_mm2(area["circular_mils"])
            metric = nearest_metric(mm2)
            if not is_blank(cm):
                total_cm = parallel * area["circular_mils"]
                l = 2 * l_ft if cm["round_trip"] else l_ft
                drop_v = round_half_up(cm["k"] * current * l / total_cm, 2)
                drop_pct = round_half_up(cm["k"] * current * l / total_cm / voltage * 100, 1)
                steps.append(f"Drop at {f'{parallel} × ' if parallel > 1 else ''}{size} AWG: {_fmt(cm['k'])} × {_fmt(current)} × {_fmt(round_half_up(l, 1))} / {_fmt(total_cm)} = {_fmt(drop_v)} V, {_fmt(drop_pct)} % of {_fmt(voltage)} V.")
            else:
                drop_reason = "The drop at this size needs K from the constants table."

    # 6. Protection for that conductor.
    protection: dict = {
        "min_a": None, "fuse_a": None, "fits_conductor": None, "conductor_ampacity_a": conductor_ampacity_a, "characteristic": None, "guidance": GUIDANCE_LABEL,
        "interrupting": {"required_a": None, "classes": []},
    }
    if size and conductor_ampacity_a is not None:
        f = fuse_for_conductor(current, load_type, conductor_ampacity_a, inputs.get("manufacturer_fuse_a"))
        protection.update(min_a=f["min_a"], fuse_a=f["fuse_a"], fits_conductor=f["fits_conductor"], characteristic=f["characteristic"])
        if f.get("reason"):
            protection["reason"] = f["reason"]
            add_blank("protection.fuse_a", f["reason"])
        if f["fits_conductor"]:
            basis = "the maker's stated rating" if f["manufacturer_a"] is not None else f"{_fmt(current)} A × the {load_type.replace('_', ' ')} factor"
            steps.append(f"Fuse: at least {_fmt(f['min_a'])} A ({basis}), next standard size {_fmt(f['fuse_a'])} A, within the conductor's {_fmt(conductor_ampacity_a)} A. Characteristic: {f['characteristic']} ({f['guidance']}).")
        else:
            steps.append(f"Fuse: {f['reason']}")
    else:
        protection["reason"] = "The conductor's allowable current is not known, so no fuse can be sized to it." if size else "No conductor size was settled, so no fuse can be sized."
        add_blank("protection.fuse_a", protection["reason"])
    ic = interrupting_check(inputs.get("short_circuit_a"), load_type, tables, own.get("short_circuit_a"))
    if is_blank(ic):
        protection["interrupting"] = {"required_a": None, "classes": [], "reason": ic["reason"], **({"ask": ic["ask"]} if ic.get("ask") else {})}
        add_blank("protection.interrupting.required_a", ic["reason"], ic.get("ask"))
    else:
        protection["interrupting"] = {"required_a": ic["required_a"], "classes": ic["classes"], **({"reason": ic["reason"]} if ic.get("reason") else {})}
        if ic["classes"]:
            listed = ", ".join(f"{c['class']} ({_fmt(c['interrupting_rating_a'])} A{', suits this load' if c['suits_load'] else ''})" for c in ic["classes"])
            steps.append(f"Interrupting capacity: the source can deliver {_fmt(ic['required_a'])} A{' (entered by you)' if 'by' in ic['source'] else ''}; fuse classes rated at least that: {listed}.")
        else:
            steps.append(f"Interrupting capacity: {ic['reason']}")

    # 7. Reminders that apply.
    tags = ["dc", load_type]
    if engine:
        tags.append("engine_space")
    if bundled >= 3:
        tags.append("bundled")
    if parallel > 1:
        tags.append("parallel")
    reminders = reminders_for(sheet, tags) if sheet else []

    def opt(d: dict, **extra) -> dict:
        d.update({k: v for k, v in extra.items() if v is not None})
        return d

    return {
        "conductor": {
            "size_awg": size, "size_mm2": mm2, "metric_standard_mm2": metric, "parallel": parallel, "governed_by": governed,
            "voltage_drop": opt({"cm_required": cm_required, "size_awg": vd_size}, reason=vd_reason, source=vd_source),
            "printed_table": opt({"size_awg": printed_size}, reason=printed_reason, source=printed_source),
            "ampacity": opt({"size_awg": amp_size, "ampacity_a": amp_a, "bundling_factor": factor}, reason=amp_reason, source=amp_source),
            "drop_at_size": opt({"volts": drop_v, "percent": drop_pct}, reason=drop_reason),
        },
        "protection": protection,
        "reminders": reminders,
        "blanks": blanks,
        "steps": steps,
        "fixture": tables.fixture,
    }
