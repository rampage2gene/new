"""Calculator modules. Register new calculators in REGISTRY at the bottom."""
from __future__ import annotations

import math
import re

from .base import CalcResult, CalculationError, Calculator, CalculatorSpec, InputSpec, InputValue, ResultValue, fmt, num
from . import tables as T


def _awg_key(size_text: str) -> str | None:
    s = str(size_text).upper().replace(" ", "").replace("AWG", "").replace("#", "")
    s = {"0000": "4/0", "000": "3/0", "00": "2/0", "0": "1/0"}.get(s, s)
    return s if s in T.AWG_MM2 else None


def _parse_size(size: str) -> tuple[str, float | str]:
    """Return ('awg', '4/0') or ('mm2', 35.0)."""
    s = str(size).strip()
    m = re.match(r"^\s*([\d.]+)\s*mm", s, re.I)
    if m:
        return "mm2", float(m.group(1))
    k = _awg_key(s)
    if k:
        return "awg", k
    try:
        v = float(s)
        if v in T.MM2_AMPACITY_105C or v > 40:
            return "mm2", v
        k = _awg_key(str(int(v)))
        if k:
            return "awg", k
    except ValueError:
        pass
    raise CalculationError(f"Unrecognised conductor size '{size}'. Use e.g. '4/0 AWG', '6 AWG' or '35 mm²'.")


# --------------------------------------------------------------------------- DC current

def _dc_current(i: dict[str, InputValue]) -> CalcResult:
    p, v = num(i, "power"), num(i, "voltage")
    if v <= 0:
        raise CalculationError("Voltage must be greater than zero")
    amps = p / v
    return CalcResult(
        calculator_id="dc_current", calculator_name="DC Current", formula="I = P ÷ V", inputs=i,
        steps=[f"I = {fmt(p)} W ÷ {fmt(v)} V = {fmt(amps)} A"],
        results=[ResultValue("current", "DC current", round(amps, 2), "A")],
        assumptions=["Steady-state DC load; no conversion losses included."],
    )


DC_CURRENT = Calculator(
    CalculatorSpec(
        id="dc_current", name="DC Current", category="Basic",
        description="Current drawn by a DC load from its power rating and system voltage.",
        formula="I = P ÷ V",
        inputs=[
            InputSpec("power", "Load power", "W", entity_types=["power"], qualifiers=["continuous", "nominal", "maximum"]),
            InputSpec("voltage", "System voltage", "V", entity_types=["voltage"], qualifiers=["nominal"]),
        ],
        outputs=[{"key": "current", "label": "DC current", "unit": "A"}],
        excel=[
            {"key": "current", "label": "DC current", "unit": "A", "formula": "={power}/{voltage}"},
        ],
    ),
    _dc_current,
)


# --------------------------------------------------------------------------- inverter DC current

def _inverter_dc_current(i: dict[str, InputValue]) -> CalcResult:
    p, v, eff = num(i, "power"), num(i, "voltage"), num(i, "efficiency")
    if eff > 1:
        eff = eff / 100.0
    if not (0 < eff <= 1):
        raise CalculationError("Efficiency must be between 0 and 100 %")
    if v <= 0:
        raise CalculationError("Voltage must be greater than zero")
    amps = p / v / eff
    low_v = num(i, "low_voltage")
    results = [ResultValue("current", "DC input current at nominal voltage", round(amps, 1), "A")]
    steps = [f"I = {fmt(p)} W ÷ {fmt(v)} V ÷ {fmt(eff, 3)} = {fmt(amps, 1)} A"]
    warnings = []
    if low_v:
        amps_low = p / low_v / eff
        results.append(ResultValue("current_low_voltage", f"DC current at {fmt(low_v)} V (low battery)", round(amps_low, 1), "A"))
        steps.append(f"At low battery voltage: I = {fmt(p)} W ÷ {fmt(low_v)} V ÷ {fmt(eff, 3)} = {fmt(amps_low, 1)} A")
    return CalcResult(
        calculator_id="inverter_dc_current", calculator_name="Inverter DC Current", formula="I = P ÷ V ÷ η", inputs=i,
        steps=steps, results=results,
        assumptions=[
            "Continuous output at the stated power; surge loads draw proportionally more.",
            "Efficiency treated as constant at this load point.",
            "Use the low-battery-voltage figure for conductor and fuse sizing, not the nominal one.",
        ],
        warnings=warnings,
    )


INVERTER_DC_CURRENT = Calculator(
    CalculatorSpec(
        id="inverter_dc_current", name="Inverter DC Current", category="Power conversion",
        description="DC input current an inverter draws for a given AC output power, accounting for efficiency.",
        formula="I = P ÷ V ÷ η",
        inputs=[
            InputSpec("power", "Inverter output power", "W", entity_types=["power"], qualifiers=["continuous", "nominal", "maximum"]),
            InputSpec("voltage", "Nominal DC voltage", "V", entity_types=["voltage"], qualifiers=["nominal", "input"]),
            InputSpec("efficiency", "Efficiency", "%", default=90, entity_types=["efficiency"], help="Typical 85–95 %"),
            InputSpec("low_voltage", "Low battery voltage (optional)", "V", required=False, entity_types=["voltage"], qualifiers=["cutoff", "minimum"]),
        ],
        outputs=[{"key": "current", "label": "DC input current", "unit": "A"}],
        excel=[
            {"key": "current", "label": "DC input current at nominal voltage", "unit": "A", "formula": "={power}/{voltage}/{pct:efficiency}"},
            {"key": "current_low_voltage", "label": "DC current at low battery voltage", "unit": "A", "formula": '=IF({low_voltage}>0,{power}/{low_voltage}/{pct:efficiency},"")'},
        ],
    ),
    _inverter_dc_current,
)


# --------------------------------------------------------------------------- voltage drop

def _voltage_drop(i: dict[str, InputValue]) -> CalcResult:
    v, amps, length = num(i, "voltage"), num(i, "current"), num(i, "length")
    size = i["size"].value
    material = (i["material"].value or "copper").lower()
    length_unit = (i["length_unit"].value or "m").lower()
    kind, key = _parse_size(size)
    factor = T.AL_FACTOR if material.startswith("al") else 1.0
    length_m = length * 0.3048 if length_unit.startswith("f") else length
    if kind == "awg":
        ohm_per_m = T.AWG_OHMS_PER_KFT_CU[key] / 304.8 * factor
        size_label = f"{key} AWG"
        area = T.AWG_MM2[key]
    else:
        rho = T.RHO_AL if factor > 1 else T.RHO_CU
        ohm_per_m = rho / key
        size_label = f"{key:g} mm²"
        area = key
    round_trip = 2 * length_m
    r_total = ohm_per_m * round_trip
    vd = amps * r_total
    pct = vd / v * 100 if v else 0
    steps = [
        f"Conductor: {size_label} {material}, ≈{area:g} mm² cross-section",
        f"Resistance per metre at 20 °C: {ohm_per_m*1000:.4f} mΩ/m",
        f"Circuit length (round trip): 2 × {fmt(length_m)} m = {fmt(round_trip)} m",
        f"Total resistance: {ohm_per_m*1000:.4f} mΩ/m × {fmt(round_trip)} m = {r_total*1000:.2f} mΩ",
        f"Voltage drop: {fmt(amps)} A × {r_total*1000:.2f} mΩ = {vd:.3f} V ({pct:.2f} %)",
    ]
    warnings = []
    if pct > 10:
        warnings.append("Voltage drop exceeds 10 % (the usual limit for non-critical circuits). Increase conductor size.")
    elif pct > 3:
        warnings.append("Voltage drop exceeds 3 % (the usual limit for critical circuits such as electronics, bilge pumps and navigation lights).")
    results = [
        ResultValue("voltage_drop", "Voltage drop", round(vd, 3), "V"),
        ResultValue("percent", "Voltage drop", round(pct, 2), "%"),
        ResultValue("voltage_at_load", "Voltage at load", round(v - vd, 2), "V"),
        ResultValue("resistance", "Circuit resistance", round(r_total * 1000, 2), "mΩ"),
    ]
    # With the owner's E-11 tables confirmed, say what size the standard's own
    # formula asks for at each limit - from its pages, not from these constants.
    from ..reference import e11_tables
    from ..reference.e11_sizing import is_blank, length_ft, required_circular_mils, size_for_circular_mils

    tables = e11_tables.get_tables()
    for limit in (3, 10):
        cm = required_circular_mils(v, amps, length_ft(length, "ft" if length_unit.startswith("f") else "m"), limit, tables)
        if is_blank(cm):
            continue
        pick = size_for_circular_mils(cm["value"], tables)
        if is_blank(pick):
            results.append(ResultValue(f"e11_size_{limit}pct", f"Size for a {limit} % drop by the ABYC E-11 formula", None, "AWG", classification="documented_value", note=pick["reason"]))
        else:
            results.append(ResultValue(f"e11_size_{limit}pct", f"Size for a {limit} % drop by the ABYC E-11 formula", f"{pick['size_awg']} AWG", None, classification="documented_value", note=f"{fmt(cm['value'])} circular mils needed (K = {fmt(cm['k'])}, {pick['source']['title']}, page {pick['source']['page']})"))
    return CalcResult(
        calculator_id="voltage_drop", calculator_name="Voltage Drop", formula="V_drop = I × R_per_m × 2 × L", inputs=i,
        steps=steps,
        results=results,
        assumptions=[
            "Conductor resistance at 20 °C; at 60 °C copper resistance is ≈16 % higher.",
            "Length is the one-way distance; both conductors are the same size (round trip = 2 × length).",
            "3 % / 10 % limits are typical ABYC E-11 guidance for critical / non-critical circuits.",
        ],
        warnings=warnings,
    )


VOLTAGE_DROP = Calculator(
    CalculatorSpec(
        id="voltage_drop", name="Voltage Drop", category="Conductors",
        description="Voltage drop and percentage for a DC circuit given current, one-way length and conductor size.",
        formula="V_drop = I × R × 2L",
        inputs=[
            InputSpec("voltage", "System voltage", "V", entity_types=["voltage"], qualifiers=["nominal"]),
            InputSpec("current", "Circuit current", "A", entity_types=["current", "fuse", "breaker"], qualifiers=["continuous", "maximum"]),
            InputSpec("length", "One-way length", None, help="Distance from source to load"),
            InputSpec("length_unit", "Length unit", None, kind="select", default="m", options=[{"value": "m", "label": "metres"}, {"value": "ft", "label": "feet"}]),
            InputSpec("size", "Conductor size", None, kind="text", entity_types=["wire_size"], help="e.g. 4/0 AWG, 6 AWG or 35 mm²"),
            InputSpec("material", "Conductor material", None, kind="select", default="copper", options=[{"value": "copper", "label": "Copper"}, {"value": "aluminium", "label": "Aluminium"}]),
        ],
        outputs=[{"key": "voltage_drop", "label": "Voltage drop", "unit": "V"}, {"key": "percent", "label": "Drop", "unit": "%"}],
        excel=[
            {"key": "awg_key", "label": "Conductor size key (AWG)", "kind": "helper", "formula": '=SUBSTITUTE(SUBSTITUTE(SUBSTITUTE(UPPER(TRIM({raw:size}))," ",""),"AWG",""),"#","")'},
            {"key": "is_al", "label": "Aluminium conductor?", "kind": "helper", "formula": '=LEFT(LOWER(TRIM({raw:material})),2)="al"'},
            {"key": "ohm_per_m", "label": "Resistance per metre at 20 °C", "unit": "Ω/m", "kind": "helper",
             "formula": '=IFERROR(VLOOKUP({h:awg_key},AwgTable,2,FALSE)/304.8*IF({h:is_al},1.64,1),IF({h:is_al},0.0282,0.01724)/VALUE(LEFT(TRIM({raw:size}),FIND("M",UPPER(TRIM({raw:size})))-1)))'},
            {"key": "length_m", "label": "One-way length", "unit": "m", "kind": "helper", "formula": '=IF(LEFT(LOWER(TRIM({raw:length_unit})),1)="f",{length}*0.3048,{length})'},
            {"key": "voltage_drop", "label": "Voltage drop", "unit": "V", "formula": "={current}*{h:ohm_per_m}*2*{h:length_m}"},
            {"key": "percent", "label": "Voltage drop", "unit": "%", "formula": "={r:voltage_drop}/{voltage}*100"},
            {"key": "voltage_at_load", "label": "Voltage at load", "unit": "V", "formula": "={voltage}-{r:voltage_drop}"},
            {"key": "resistance", "label": "Circuit resistance", "unit": "mΩ", "formula": "={h:ohm_per_m}*2*{h:length_m}*1000"},
            {"key": "check", "label": "Limit check", "kind": "text", "formula": '=IF({r:percent}>10,"Exceeds 10 % (non-critical limit)",IF({r:percent}>3,"Exceeds 3 % (critical-circuit limit)","Within 3 %"))'},
        ],
    ),
    _voltage_drop,
)


# --------------------------------------------------------------------------- battery runtime

def _battery_runtime(i: dict[str, InputValue]) -> CalcResult:
    cap, v, load, eff, dod = num(i, "capacity"), num(i, "voltage"), num(i, "load"), num(i, "efficiency"), num(i, "dod")
    if eff > 1:
        eff /= 100
    if dod > 1:
        dod /= 100
    if load <= 0:
        raise CalculationError("Load must be greater than zero")
    usable_wh = cap * v * dod
    dc_draw_w = load / eff
    hours = usable_wh / dc_draw_w
    return CalcResult(
        calculator_id="battery_runtime", calculator_name="Battery Runtime", formula="t = (C × V × DoD) ÷ (P ÷ η)", inputs=i,
        steps=[
            f"Usable energy: {fmt(cap)} Ah × {fmt(v)} V × {fmt(dod, 2)} = {fmt(usable_wh)} Wh",
            f"DC draw: {fmt(load)} W ÷ {fmt(eff, 3)} = {fmt(dc_draw_w)} W",
            f"Runtime: {fmt(usable_wh)} Wh ÷ {fmt(dc_draw_w)} W = {hours:.2f} h",
        ],
        results=[
            ResultValue("runtime_hours", "Estimated runtime", round(hours, 2), "h"),
            ResultValue("usable_energy", "Usable energy", round(usable_wh), "Wh"),
            ResultValue("dc_current", "Average DC current", round(dc_draw_w / v, 1), "A"),
        ],
        assumptions=[
            "Rated capacity at the stated discharge rate; Peukert effect and temperature derating not applied.",
            "Constant load for the whole period.",
            "Depth of discharge as entered (lead-acid typically 50 %, LiFePO4 80–90 %).",
        ],
    )


BATTERY_RUNTIME = Calculator(
    CalculatorSpec(
        id="battery_runtime", name="Battery Runtime", category="Batteries",
        description="How long a battery bank can supply a load.",
        formula="t = (C × V × DoD) ÷ (P ÷ η)",
        inputs=[
            InputSpec("capacity", "Battery capacity", "Ah", entity_types=["capacity"]),
            InputSpec("voltage", "Battery voltage", "V", entity_types=["voltage"], qualifiers=["nominal"]),
            InputSpec("load", "Load power", "W", entity_types=["power"]),
            InputSpec("efficiency", "Conversion efficiency", "%", default=90, help="100 % for a direct DC load"),
            InputSpec("dod", "Depth of discharge", "%", default=80),
        ],
        outputs=[{"key": "runtime_hours", "label": "Runtime", "unit": "h"}],
        excel=[
            {"key": "usable_energy", "label": "Usable energy", "unit": "Wh", "formula": "={capacity}*{voltage}*{pct:dod}"},
            {"key": "dc_draw", "label": "DC draw", "unit": "W", "kind": "helper", "formula": "={load}/{pct:efficiency}"},
            {"key": "runtime_hours", "label": "Estimated runtime", "unit": "h", "formula": "={r:usable_energy}/{h:dc_draw}"},
            {"key": "dc_current", "label": "Average DC current", "unit": "A", "formula": "={h:dc_draw}/{voltage}"},
        ],
    ),
    _battery_runtime,
)


# --------------------------------------------------------------------------- alternator charging

def _alternator_charging(i: dict[str, InputValue]) -> CalcResult:
    alt, cap = num(i, "alternator_output"), num(i, "capacity")
    derate = num(i, "derate")
    max_charge = num(i, "max_charge_current")
    soc_start, soc_end = num(i, "soc_start"), num(i, "soc_end")
    charge_eff = num(i, "charge_efficiency")
    if derate > 1:
        derate /= 100
    if charge_eff > 1:
        charge_eff /= 100
    if soc_start >= soc_end:
        raise CalculationError("End state of charge must be higher than start")
    available = alt * derate
    limits = [f"alternator hot output {fmt(alt)} A × {fmt(derate, 2)} = {fmt(available, 1)} A"]
    current = available
    limiting = "alternator"
    if max_charge and max_charge < current:
        current = max_charge
        limiting = "battery / BMS charge limit"
        limits.append(f"battery maximum charge current {fmt(max_charge)} A")
    ah_needed = cap * (soc_end - soc_start) / 100
    hours = ah_needed / (current * charge_eff)
    warnings = []
    if max_charge and available > max_charge:
        warnings.append(
            f"Alternator can deliver ≈{fmt(available, 1)} A but the battery limit is {fmt(max_charge)} A. An external regulator or DC-DC charger "
            "is needed to limit current; lithium banks can also overload an alternator that runs at full output continuously."
        )
    if cap and available / cap > 0.5:
        warnings.append("Charge rate exceeds 0.5C; confirm the battery manufacturer permits this rate.")
    return CalcResult(
        calculator_id="alternator_charging", calculator_name="Alternator Charging", formula="t = (C × ΔSoC) ÷ (I_charge × η)", inputs=i,
        steps=[
            "Available charge current is limited by: " + "; ".join(limits) + f" → {fmt(current, 1)} A ({limiting})",
            f"Charge required: {fmt(cap)} Ah × ({fmt(soc_end)} − {fmt(soc_start)}) % = {fmt(ah_needed, 1)} Ah",
            f"Time: {fmt(ah_needed, 1)} Ah ÷ ({fmt(current, 1)} A × {fmt(charge_eff, 2)}) = {hours:.2f} h",
        ],
        results=[
            ResultValue("charge_current", "Effective charge current", round(current, 1), "A", note=f"limited by {limiting}"),
            ResultValue("hours", "Estimated bulk charge time", round(hours, 2), "h"),
            ResultValue("ah_needed", "Charge required", round(ah_needed, 1), "Ah"),
        ],
        assumptions=[
            "Bulk-stage constant current; absorption tapering (lead-acid) adds significant time above ~80 % SoC.",
            "Hot alternator output derated by the factor given (typical 0.6–0.8 of cold rating).",
            "Engine at a speed where the alternator reaches rated output.",
        ],
        warnings=warnings,
    )


ALTERNATOR_CHARGING = Calculator(
    CalculatorSpec(
        id="alternator_charging", name="Alternator Charging", category="Charging",
        description="Charging current available from an alternator and the time to recharge a bank.",
        formula="t = (C × ΔSoC) ÷ (I × η)",
        inputs=[
            InputSpec("alternator_output", "Alternator rated output", "A", entity_types=["current"], qualifiers=["nominal", "maximum", "output"]),
            InputSpec("derate", "Hot derating factor", "%", default=70, help="Alternators lose output when hot"),
            InputSpec("capacity", "Battery bank capacity", "Ah", entity_types=["capacity"]),
            InputSpec("max_charge_current", "Battery max charge current (optional)", "A", required=False, entity_types=["current"], qualifiers=["charging", "maximum"]),
            InputSpec("soc_start", "Starting state of charge", "%", default=50),
            InputSpec("soc_end", "Target state of charge", "%", default=90),
            InputSpec("charge_efficiency", "Charge efficiency", "%", default=95),
        ],
        outputs=[{"key": "hours", "label": "Charge time", "unit": "h"}],
        excel=[
            {"key": "available", "label": "Alternator hot output", "unit": "A", "kind": "helper", "formula": "={alternator_output}*{pct:derate}"},
            {"key": "charge_current", "label": "Effective charge current", "unit": "A", "formula": "=IF(AND({max_charge_current}>0,{max_charge_current}<{h:available}),{max_charge_current},{h:available})"},
            {"key": "ah_needed", "label": "Charge required", "unit": "Ah", "formula": "={capacity}*({soc_end}-{soc_start})/100"},
            {"key": "hours", "label": "Estimated bulk charge time", "unit": "h", "formula": "={r:ah_needed}/({r:charge_current}*{pct:charge_efficiency})"},
            {"key": "limited_by", "label": "Limited by", "kind": "text", "formula": '=IF({r:charge_current}<{h:available},"battery / BMS charge limit","alternator")'},
        ],
    ),
    _alternator_charging,
)


# --------------------------------------------------------------------------- AC load

def _ac_load(i: dict[str, InputValue]) -> CalcResult:
    v, amps, pf, watts = num(i, "voltage"), num(i, "current"), num(i, "power_factor"), num(i, "power")
    if pf > 1:
        pf /= 100
    if amps is None and watts is None:
        raise CalculationError("Provide either current or power")
    steps = []
    if amps is not None:
        va = v * amps
        w = va * pf
        steps += [f"VA = {fmt(v)} V × {fmt(amps)} A = {fmt(va)} VA", f"W = {fmt(va)} VA × {fmt(pf, 2)} = {fmt(w)} W"]
    else:
        w = watts
        va = w / pf
        amps = va / v
        steps += [f"VA = {fmt(w)} W ÷ {fmt(pf, 2)} = {fmt(va)} VA", f"A = {fmt(va)} VA ÷ {fmt(v)} V = {fmt(amps, 2)} A"]
    return CalcResult(
        calculator_id="ac_load", calculator_name="AC Load", formula="W = V × A × PF;  VA = V × A", inputs=i,
        steps=steps,
        results=[
            ResultValue("watts", "Real power", round(w, 1), "W"),
            ResultValue("va", "Apparent power", round(va, 1), "VA"),
            ResultValue("amps", "Current", round(amps, 2), "A"),
        ],
        assumptions=["Single-phase AC; power factor as entered (1.0 for resistive loads, 0.6–0.9 for motors/electronics)."],
    )


AC_LOAD = Calculator(
    CalculatorSpec(
        id="ac_load", name="AC Load", category="AC",
        description="Convert between watts, volt-amps and amps for a single-phase AC load.",
        formula="W = V × A × PF",
        inputs=[
            InputSpec("voltage", "AC voltage", "V", default=120, entity_types=["voltage"]),
            InputSpec("current", "Current (optional)", "A", required=False, entity_types=["current", "breaker"]),
            InputSpec("power", "Power (optional)", "W", required=False, entity_types=["power"]),
            InputSpec("power_factor", "Power factor", None, default=1.0),
        ],
        outputs=[{"key": "watts", "label": "Watts", "unit": "W"}, {"key": "va", "label": "VA", "unit": "VA"}, {"key": "amps", "label": "Amps", "unit": "A"}],
        excel=[
            {"key": "pf", "label": "Power factor (fraction)", "kind": "helper", "formula": "={pct:power_factor}"},
            {"key": "amps", "label": "Current", "unit": "A", "formula": "=IF({current}>0,{current},({power}/{h:pf})/{voltage})"},
            {"key": "va", "label": "Apparent power", "unit": "VA", "formula": "={voltage}*{r:amps}"},
            {"key": "watts", "label": "Real power", "unit": "W", "formula": "=IF({current}>0,{r:va}*{h:pf},{power})"},
        ],
    ),
    _ac_load,
)


# --------------------------------------------------------------------------- fuse / circuit protection

DEVICE_PROFILES: dict[str, dict] = {
    "inverter": {"label": "Inverter / inverter-charger", "factor": 1.25, "surge_note": "Inverters draw large surge currents on motor/compressor start-up; use a time-delay / high-interrupt fuse (e.g. Class T or MRBF for large banks).", "char": "time-delay, high interrupt capacity (Class T recommended for banks able to deliver >5 kA fault current)"},
    "battery_main": {"label": "Battery bank main / positive feed", "factor": 1.0, "surge_note": "The main fuse protects the conductor, not the load; it is sized to the cable ampacity.", "char": "high interrupt capacity matched to the bank's prospective short-circuit current (Class T for lithium/large AGM banks; ANL/MEGA only where the AIC is adequate)"},
    "battery_charger": {"label": "Battery charger output", "factor": 1.25, "surge_note": "Charger output current is limited by the charger; size at 125 % of rated output.", "char": "standard blade/ANL/MRBF per manufacturer"},
    "alternator": {"label": "Alternator output", "factor": 1.25, "surge_note": "Never open an alternator output circuit while running (load-dump destroys diodes). ABYC requires overcurrent protection within 7\" (178 mm) unless self-limiting; some manufacturers advise against fusing the B+ lead - follow their documentation.", "char": "MRBF/ANL/MEGA sized ≥125 % of rated output, or per manufacturer"},
    "dc_dc": {"label": "DC-DC charger / converter", "factor": 1.25, "surge_note": "Protect both input and output leads; input current exceeds output current when stepping voltage up.", "char": "per manufacturer, typically blade/MIDI"},
    "solar": {"label": "Solar controller (PV or battery side)", "factor": 1.25, "surge_note": "PV side: 1.25 × Isc × 1.25 (irradiance); battery side: 1.25 × controller rated output.", "char": "DC-rated fuse or breaker"},
    "motor": {"label": "Motor (windlass, thruster, pump)", "factor": 1.5, "surge_note": "Locked-rotor / inrush current is 3–6× running current; use a slow-blow fuse or thermal breaker per the motor manufacturer's rating. Windlass/thruster breakers are usually specified by the manufacturer.", "char": "slow-blow / thermal breaker; manufacturer's rating takes precedence"},
    "capacitive": {"label": "Capacitive / electronic load", "factor": 1.25, "surge_note": "Input capacitors cause a brief inrush; use time-delay characteristics.", "char": "time-delay"},
    "resistive": {"label": "Resistive load (heater, lights)", "factor": 1.25, "surge_note": "No significant inrush.", "char": "fast-acting or standard"},
    "electronics": {"label": "Electronics / instruments", "factor": 1.25, "surge_note": "Follow the equipment manufacturer's fuse rating; small fuses protect the wire.", "char": "fast-acting (blade/glass) per manufacturer"},
}


TYPICAL_NOTE = "Typical published value; verify against the wire's actual rating"


def _ampacity(size: str | None, engine_space: bool) -> tuple[float | None, str | None, str | None]:
    """A conductor's allowable current: from the owner's confirmed ABYC E-11
    table when there is one (the engine-space table is already derated as
    the standard prints it), else the typical figures in tables.py, and a
    note that says which. Returns (amps, size label, note)."""
    if not size:
        return None, None, None
    kind, key = _parse_size(size)
    if kind == "awg":
        from ..reference import e11_tables
        from ..reference.e11_sizing import ampacity_of, is_blank

        found = ampacity_of(key, 105, engine_space, e11_tables.get_tables())
        if not is_blank(found):
            src = found["source"]
            return float(found["ampacity_a"]), f"{key} AWG", f"from ABYC E-11, {src['title']}, page {src['page']}"
        amp = T.AWG_AMPACITY_105C.get(key)
        label = f"{key} AWG"
    else:
        amp = T.MM2_AMPACITY_105C.get(float(key))
        if amp is None:
            # interpolate between neighbours
            keys = sorted(T.MM2_AMPACITY_105C)
            lower = max([k for k in keys if k <= key], default=None)
            upper = min([k for k in keys if k >= key], default=None)
            if lower and upper and lower != upper:
                a0, a1 = T.MM2_AMPACITY_105C[lower], T.MM2_AMPACITY_105C[upper]
                amp = a0 + (a1 - a0) * (key - lower) / (upper - lower)
        label = f"{key:g} mm²"
    if amp is None:
        return None, label, None
    if engine_space:
        amp *= T.ENGINE_SPACE_DERATE_105C
    return amp, label, TYPICAL_NOTE


def _fuse_protection(i: dict[str, InputValue]) -> CalcResult:
    device = (i["device_type"].value or "resistive")
    prof = DEVICE_PROFILES.get(device, DEVICE_PROFILES["resistive"])
    cont = num(i, "continuous_current")
    surge = num(i, "surge_current")
    surge_s = num(i, "surge_duration")
    v = num(i, "system_voltage")
    mfr = num(i, "manufacturer_fuse")
    mfr_max = num(i, "manufacturer_max_fuse")
    size = i["conductor_size"].value
    engine_space = str(i["engine_space"].value).lower() in ("true", "yes", "1")
    ampacity, size_label, amp_note = _ampacity(size, engine_space)

    steps: list[str] = []
    warnings: list[str] = []
    results: list[ResultValue] = []
    assumptions = [
        "Continuous load factor 125 % (ABYC E-11 / NEC practice for loads lasting > 3 h).",
        "Standard fuse sizes used; the next size up from the calculated minimum is chosen.",
        prof["surge_note"],
    ]
    mfr_source = i["manufacturer_fuse"].source

    # 1. Manufacturer requirement (documented) -----------------------------------
    if mfr:
        src = f" (source: {mfr_source.document_name}, page {mfr_source.page})" if mfr_source and mfr_source.document_name else ""
        results.append(ResultValue("manufacturer_required", "Manufacturer-specified fuse", mfr, "A", classification="manufacturer_required" if mfr_source else "documented_value", note=f"As stated in the manufacturer's documentation{src}." if mfr_source else "Entered by user as the manufacturer's value; attach a document source to confirm."))
        steps.append(f"Manufacturer specifies {fmt(mfr)} A{src}.")
    if mfr_max:
        results.append(ResultValue("manufacturer_maximum", "Manufacturer maximum fuse", mfr_max, "A", classification="manufacturer_required"))

    # 2. Calculated estimate ---------------------------------------------------------
    calc_min = None
    if cont:
        calc_min = cont * prof["factor"]
        steps.append(f"Calculated minimum = {fmt(cont)} A × {prof['factor']:.2f} ({prof['label']}) = {fmt(calc_min, 1)} A")
        if device == "battery_main" and ampacity:
            calc_min = max(calc_min, min(ampacity, cont * 1.25))
        if surge:
            ratio = surge / max(cont, 0.1)
            steps.append(f"Surge/inrush {fmt(surge)} A is {ratio:.1f}× continuous" + (f" for {fmt(surge_s, 1)} s" if surge_s else ""))
            if ratio > 2 and device in ("inverter", "motor", "capacitive"):
                assumptions.append("Time-delay fuses typically carry 200 % of rating for several seconds; verify the fuse's time-current curve against the surge duration.")
            if ratio > 4:
                warnings.append("Inrush exceeds 4× continuous current; a standard fuse sized at 125 % may nuisance-trip. Use a slow-blow characteristic or the manufacturer's rating.")
        est = T.next_standard(calc_min, T.STANDARD_FUSE_SIZES)
        results.append(ResultValue("calculated_estimate", "Calculated fuse size (engineering estimate)", est, "A", classification="calculated_estimate", note=f"Next standard size ≥ {fmt(calc_min, 1)} A"))
        steps.append(f"Next standard fuse size ≥ {fmt(calc_min, 1)} A → {fmt(est)} A")
    else:
        est = None
        if not mfr:
            raise CalculationError("Provide the continuous current or the manufacturer's fuse rating")

    # 3. Conductor protection check -----------------------------------------------------
    if size_label:
        if ampacity:
            typical = amp_note == TYPICAL_NOTE
            steps.append(f"Conductor {size_label}: {'typical ampacity ≈' if typical else 'ampacity '}{fmt(ampacity)} A (105 °C insulation{', engine space' if engine_space else ''}{'' if typical else '; ' + amp_note})")
            results.append(ResultValue("conductor_ampacity", f"Conductor ampacity ({size_label})", round(ampacity), "A", classification="calculated_estimate" if typical else "documented_value", note=amp_note))
            if cont and cont > ampacity:
                warnings.append(f"Continuous current {fmt(cont)} A exceeds the conductor ampacity (~{fmt(ampacity)} A). Increase the conductor size.")
        else:
            warnings.append(f"No ampacity table entry for {size_label}; enter the conductor's rated ampacity manually.")

    # 4. Recommendation pending verification -------------------------------------------
    rec = None
    rationale = []
    if mfr:
        rec = mfr
        rationale.append("manufacturer-specified value takes precedence")
        if est and abs(est - mfr) > 1e-6:
            rationale.append(f"calculated estimate ({fmt(est)} A) differs from the manufacturer value ({fmt(mfr)} A); manufacturer guidance governs unless it conflicts with conductor protection")
    elif est:
        rec = est
        rationale.append("no manufacturer rating supplied; using the calculated estimate")
    if rec and ampacity and rec > ampacity * 1.0 + 1e-6:
        down = T.prev_standard(ampacity, T.STANDARD_FUSE_SIZES)
        warnings.append(f"Recommended fuse {fmt(rec)} A exceeds the conductor ampacity (~{fmt(ampacity)} A). Either increase the conductor size or limit the fuse to {fmt(down)} A; the fuse must protect the wire.")
        rationale.append("capped by conductor ampacity")
        rec_capped = down
    else:
        rec_capped = rec
    if mfr_max and rec_capped and rec_capped > mfr_max:
        warnings.append(f"Recommendation exceeds the manufacturer's maximum fuse ({fmt(mfr_max)} A).")
        rec_capped = mfr_max
    if rec_capped:
        results.append(ResultValue("recommended", "Recommended protection (pending verification)", rec_capped, "A", classification="recommended_pending_verification", note="; ".join(rationale)))
    results.append(ResultValue("characteristic", "Fuse characteristic", prof["char"], None, classification="recommended_pending_verification"))
    if v and v >= 48 and device in ("inverter", "battery_main"):
        assumptions.append("At 48 V and above, confirm the fuse's DC voltage rating (many automotive fuses are rated 32 V DC).")
    if device == "alternator":
        warnings.append("Alternator output protection: confirm the alternator/regulator manufacturer's instructions before fusing the B+ lead.")
    assumptions.append("Interrupt (AIC) rating must exceed the battery bank's prospective short-circuit current.")

    return CalcResult(
        calculator_id="fuse_protection", calculator_name="Fuse & Circuit Protection", formula="I_fuse ≥ I_continuous × k (k per load type), rounded up to a standard size, and ≤ conductor ampacity", inputs=i,
        steps=steps, results=results, assumptions=assumptions, warnings=warnings,
        classification="recommended_pending_verification",
    )


FUSE_PROTECTION = Calculator(
    CalculatorSpec(
        id="fuse_protection", name="Fuse & Circuit Protection", category="Protection",
        description="Device-aware overcurrent protection analysis. Distinguishes manufacturer-required protection from calculated estimates and checks that the fuse protects the conductor.",
        formula="I_fuse ≥ I_continuous × k; next standard size; ≤ conductor ampacity",
        inputs=[
            InputSpec("device_type", "Device / load type", None, kind="select", default="inverter", options=[{"value": k, "label": v["label"]} for k, v in DEVICE_PROFILES.items()]),
            InputSpec("continuous_current", "Maximum continuous current", "A", required=False, entity_types=["current"], qualifiers=["continuous", "maximum", "input"]),
            InputSpec("surge_current", "Surge / inrush current (optional)", "A", required=False, entity_types=["current"], qualifiers=["surge", "peak"]),
            InputSpec("surge_duration", "Surge duration (optional)", "s", required=False),
            InputSpec("system_voltage", "System voltage", "V", required=False, entity_types=["voltage"], qualifiers=["nominal"]),
            InputSpec("manufacturer_fuse", "Manufacturer-specified fuse (optional)", "A", required=False, entity_types=["fuse", "breaker"], qualifiers=["recommended", "required"]),
            InputSpec("manufacturer_max_fuse", "Manufacturer maximum fuse (optional)", "A", required=False, entity_types=["fuse", "breaker"], qualifiers=["maximum"]),
            InputSpec("conductor_size", "Conductor being protected (optional)", None, kind="text", required=False, entity_types=["wire_size"], help="e.g. 4/0 AWG or 35 mm²"),
            InputSpec("engine_space", "Conductor runs through engine space", None, kind="select", default="no", options=[{"value": "no", "label": "No"}, {"value": "yes", "label": "Yes"}]),
        ],
        outputs=[{"key": "recommended", "label": "Recommended protection", "unit": "A"}],
        notes=[
            "Fuse selection depends on the device, its surge behaviour and the conductor - never on cable size alone.",
            "A calculated value is never presented as a manufacturer requirement.",
        ],
        excel=[
            {"key": "k", "label": "Load factor k (from device type)", "kind": "helper", "formula": "=IFERROR(VLOOKUP({raw:device_type},DeviceTable,2,FALSE),1.25)"},
            {"key": "awg_key", "label": "Conductor size key (AWG)", "kind": "helper", "formula": '=SUBSTITUTE(SUBSTITUTE(SUBSTITUTE(UPPER(TRIM({raw:conductor_size}))," ",""),"AWG",""),"#","")'},
            {"key": "mm2", "label": "Conductor size (mm², if metric)", "kind": "helper", "formula": '=IFERROR(VALUE(LEFT(TRIM({raw:conductor_size}),FIND("M",UPPER(TRIM({raw:conductor_size})))-1)),"")'},
            {"key": "derate", "label": "Engine-space derating", "kind": "helper", "formula": '=IF(LOWER(TRIM({raw:engine_space}))="yes",0.85,1)'},
            {"key": "calc_min", "label": "Calculated minimum (I × k)", "unit": "A", "kind": "helper", "formula": '=IF({continuous_current}>0,{continuous_current}*{h:k},"")'},
            {"key": "manufacturer_required", "label": "Manufacturer-specified fuse", "unit": "A", "classification": "manufacturer_required", "formula": '=IF({manufacturer_fuse}>0,{manufacturer_fuse},"")'},
            {"key": "calculated_estimate", "label": "Calculated fuse size (engineering estimate)", "unit": "A", "classification": "calculated_estimate",
             "formula": '=IF({continuous_current}>0,INDEX(FuseSizes,IFERROR(MATCH({h:calc_min}-0.000001,FuseSizes,1)+1,1)),"")'},
            {"key": "conductor_ampacity", "label": "Conductor ampacity (typical, 105 °C)", "unit": "A", "classification": "calculated_estimate",
             "formula": '=IFERROR(VLOOKUP({h:awg_key},AwgTable,3,FALSE)*{h:derate},IFERROR(VLOOKUP({h:mm2},Mm2Table,2,FALSE)*{h:derate},""))'},
            {"key": "rec_raw", "label": "Recommendation before conductor check", "unit": "A", "kind": "helper", "formula": '=IF({manufacturer_fuse}>0,{manufacturer_fuse},{r:calculated_estimate})'},
            {"key": "rec_capped", "label": "Recommendation capped by conductor", "unit": "A", "kind": "helper",
             "formula": '=IF(AND(ISNUMBER({r:conductor_ampacity}),ISNUMBER({h:rec_raw})),IF({h:rec_raw}>{r:conductor_ampacity},INDEX(FuseSizes,MATCH({r:conductor_ampacity},FuseSizes,1)),{h:rec_raw}),{h:rec_raw})'},
            {"key": "recommended", "label": "Recommended protection (pending verification)", "unit": "A", "classification": "recommended_pending_verification",
             "formula": '=IF(AND({manufacturer_max_fuse}>0,ISNUMBER({h:rec_capped})),MIN({h:rec_capped},{manufacturer_max_fuse}),{h:rec_capped})'},
            {"key": "conductor_check", "label": "Conductor protection check", "kind": "text", "classification": "recommended_pending_verification",
             "formula": '=IF(NOT(ISNUMBER({r:conductor_ampacity})),"no conductor size given",IF({continuous_current}>{r:conductor_ampacity},"CONTINUOUS CURRENT EXCEEDS CONDUCTOR AMPACITY",IF(AND(ISNUMBER({r:recommended}),{r:recommended}>{r:conductor_ampacity}),"FUSE EXCEEDS CONDUCTOR AMPACITY","OK - fuse protects the conductor")))'},
            {"key": "characteristic", "label": "Fuse characteristic", "kind": "text", "classification": "recommended_pending_verification", "formula": '=IFERROR(VLOOKUP({raw:device_type},DeviceTable,4,FALSE),"")'},
        ],
    ),
    _fuse_protection,
)


# --------------------------------------------------------------------------- circuit: conductor and protection (ABYC E-11)

def _yes(v) -> bool:
    return str(v).lower() in ("true", "yes", "1")


# The `own.*` fields the reference engine asks for -> the answer inputs below.
ANSWER_INPUTS = {"own.ampacity_a": "own_ampacity_a", "own.bundling_factor": "own_bundling_factor", "own.k": "own_k", "own.short_circuit_a": "own_short_circuit_a"}


def _circuit_e11(i: dict[str, InputValue]) -> CalcResult:
    """The whole procedure for one circuit from the owner's E-11 tables; see
    app.reference.e11_circuit. Every number cites a page or says "you"; a
    blank is a request with the input that answers it."""
    from ..reference import e11_cheatsheet, e11_tables
    from ..reference.e11_circuit import size_circuit
    from ..reference.e11_tables import TABLE_IDS, usable
    from .base import SourceRef

    limit_sel = str(i["max_drop_percent"].value or "3")
    limit = num(i, "max_drop_other") if limit_sel == "other" else float(limit_sel)
    if not limit or limit <= 0:
        raise CalculationError("Give the drop limit as a percentage above zero")
    bundled = int(num(i, "bundled_conductors") or 2) if _yes(i["bundled"].value) else 2
    inputs = {
        "system_voltage": num(i, "system_voltage"), "current": num(i, "current"), "length": num(i, "length"), "length_unit": (i["length_unit"].value or "m").lower()[:1].replace("f", "ft").replace("m", "m"),
        "max_drop_percent": limit, "insulation_rating_c": num(i, "insulation_rating_c") or 105, "engine_space": _yes(i["engine_space"].value),
        "bundled_conductors": bundled, "load_type": i["load_type"].value or "resistive", "short_circuit_a": num(i, "short_circuit_a"), "manufacturer_fuse_a": num(i, "manufacturer_fuse"),
    }
    own = {key.split(".", 1)[1]: num(i, inp) for key, inp in ANSWER_INPUTS.items() if num(i, inp) is not None}
    tables = e11_tables.get_tables()
    sheet, _ = e11_cheatsheet.get_cheatsheet()
    common = dict(calculator_id="circuit_e11", calculator_name="Circuit: conductor and protection (ABYC E-11)", formula="CM = K × I × L / E; ampacity × bundling factor; the larger wins; fuse ≥ load × k and ≤ conductor ampacity", inputs=i, classification="recommended_pending_verification")
    if not any(usable(tables, tid) for tid in TABLE_IDS):
        reason = "The ABYC E-11 tables are not installed or not yet confirmed, so nothing was computed. Open Calculators → ABYC E-11 reference, import each table from your copy of the standard, check it against the page and press Confirm."
        return CalcResult(**common, steps=[], results=[ResultValue("size_awg", "Conductor size", None, "AWG", note=reason, group="Conductor")], asks=[{"field": "reference", "input_key": None, "unit": None, "prompt": reason}], warnings=[reason])

    r = size_circuit(inputs, tables, own, sheet)
    c, p = r["conductor"], r["protection"]

    def cite(src: dict | None) -> str:
        if not src:
            return ""
        return "entered by you" if "by" in src else f"ABYC E-11, {src.get('title') or src.get('table')}, page {src['page']}"

    results: list[ResultValue] = []
    size_text = f"{c['parallel']} × {c['size_awg']} AWG in parallel" if c["size_awg"] and c["parallel"] > 1 else (f"{c['size_awg']} AWG" if c["size_awg"] else None)
    governed = {"voltage_drop": "the voltage-drop limit", "ampacity": "the current it must carry", "printed_table": "the printed table"}.get(c["governed_by"] or "", "")
    size_note = f"Governed by {governed}." if size_text else next((b["reason"] for b in r["blanks"] if b["field"].startswith("conductor.")), "No conductor size was settled.")
    results.append(ResultValue("size_awg", "Conductor size", size_text, None, classification="documented_value" if size_text else "recommended_pending_verification", note=size_note, group="Conductor"))
    if c["size_mm2"] is not None:
        results.append(ResultValue("size_mm2", "Same area in mm²", c["size_mm2"], "mm²", classification="calculated_estimate", note=f"Unit conversion (1 circular mil = 0.0005067 mm²); nearest standard metric size {fmt(c['metric_standard_mm2'])} mm²" if c["metric_standard_mm2"] else "Unit conversion (1 circular mil = 0.0005067 mm²)", group="Conductor"))
    vd = c["voltage_drop"]
    results.append(ResultValue("cm_required", "Circular mils needed for the drop limit", vd["cm_required"], "CM", classification="documented_value", note=vd.get("reason") or cite(vd.get("source")), group="Conductor"))
    results.append(ResultValue("voltage_drop_size", "Size for the voltage drop", f"{vd['size_awg']} AWG" if vd["size_awg"] else None, None, classification="documented_value", note=vd.get("reason") or cite(vd.get("source")), group="Conductor"))
    pt = c["printed_table"]
    results.append(ResultValue("printed_table_size", "Size from the printed table", f"{pt['size_awg']} AWG" if pt["size_awg"] else None, None, classification="documented_value", note=pt.get("reason") or cite(pt.get("source")), group="Conductor"))
    am = c["ampacity"]
    amp_note = am.get("reason") or f"{fmt(am['ampacity_a'])} A × bundling factor {fmt(am['bundling_factor'])} ({cite(am.get('source'))})"
    results.append(ResultValue("ampacity_size", "Size for the current, derated", f"{am['size_awg']} AWG" if am["size_awg"] else None, None, classification="documented_value", note=amp_note, group="Conductor"))
    d = c["drop_at_size"]
    results.append(ResultValue("drop_at_size", "Drop at that size", d["volts"], "V", classification="calculated_estimate", note=d.get("reason") or (f"{fmt(d['percent'])} % of {fmt(inputs['system_voltage'])} V" if d["percent"] is not None else None), group="Conductor"))

    fuse_note = p.get("reason") or (f"At least {fmt(p['min_a'])} A for the load, within the conductor's {fmt(p['conductor_ampacity_a'])} A" if p["fuse_a"] is not None else None)
    results.append(ResultValue("fuse_a", "Fuse or breaker", p["fuse_a"], "A", classification="recommended_pending_verification", note=fuse_note, group="Protection"))
    if p["characteristic"]:
        results.append(ResultValue("fuse_characteristic", "Characteristic", p["characteristic"], None, classification="recommended_pending_verification", note=p["guidance"], group="Protection"))
    ic = p["interrupting"]
    classes = ", ".join(f"{x['class']} ({fmt(x['interrupting_rating_a'])} A{', suits this load' if x['suits_load'] else ''})" for x in ic["classes"]) or None
    results.append(ResultValue("interrupting", "Fuse classes with enough interrupting capacity", classes, None, classification="recommended_pending_verification", note=ic.get("reason") or (f"The source can deliver {fmt(ic['required_a'])} A; ratings from the makers' datasheets" if classes else None), group="Protection"))

    asks = []
    for b in r["blanks"]:
        ask = b.get("ask")
        asks.append({"field": b["field"], "reason": b["reason"], "input_key": ANSWER_INPUTS.get(ask["field"]) if ask else None, "unit": ask["unit"] if ask else None, "prompt": ask["prompt"] if ask else b["reason"]})
    warnings = [b["reason"] for b in r["blanks"] if not b.get("ask")]
    if p["fits_conductor"] is False:
        warnings.append(p["reason"])
    sources: list[SourceRef] = []
    seen = set()
    for src in (vd.get("source"), pt.get("source"), am.get("source")):
        if src and "page" in src and (src["table"], src["page"]) not in seen:
            seen.add((src["table"], src["page"]))
            sources.append(SourceRef(document_name=f"ABYC E-11 ({src.get('title') or src['table']})", page=src["page"]))
    return CalcResult(
        **common, steps=r["steps"], results=results, asks=asks, reminders=r["reminders"], warnings=warnings, sources=sources,
        assumptions=[
            "A conductor must satisfy two requirements and the larger size wins: carry the current without overheating (the ampacity table, derated for engine space and bundling) and deliver the voltage (the drop limit). When no single listed size does both, conductors are paralleled.",
            "The fuse protects the conductor: never above its derated ampacity, at least the load times its load-type factor, rounded up to a standard size.",
            "Every table value comes from your confirmed copy of ABYC E-11 and cites its page; mm² and the standard size lists are conversions and industry lists; load behaviour is industry guidance.",
        ] + (["These figures come from the synthetic test tables, not from the standard."] if r["fixture"] else []),
    )


CIRCUIT_E11 = Calculator(
    CalculatorSpec(
        id="circuit_e11", name="Circuit: conductor and protection (ABYC E-11)", category="Conductors",
        description="From current, length and any nominal voltage to the conductor size (voltage drop first, then the current it must carry with engine-space and bundling derating, conductors in parallel when one is not enough) and the fuse for that conductor - from your confirmed copy of ABYC E-11, every number with its page. What the tables do not cover comes back as a blank you can fill in.",
        formula="CM = K × I × L / E; ampacity × bundling factor; larger wins; fuse ≥ load × k, ≤ conductor",
        inputs=[
            InputSpec("system_voltage", "System voltage", "V", entity_types=["voltage"], qualifiers=["nominal"], help="any nominal voltage: 12, 24, 32, 36, 48…"),
            InputSpec("current", "Circuit current", "A", entity_types=["current", "fuse", "breaker"], qualifiers=["continuous", "maximum"]),
            InputSpec("length", "One-way length", None, help="Distance from the source to the load"),
            InputSpec("length_unit", "Length unit", None, kind="select", default="m", options=[{"value": "m", "label": "metres"}, {"value": "ft", "label": "feet"}]),
            InputSpec("max_drop_percent", "Voltage-drop limit", None, kind="select", default="3", options=[{"value": "3", "label": "3 % (critical circuits)"}, {"value": "10", "label": "10 % (non-critical)"}, {"value": "other", "label": "other"}]),
            InputSpec("max_drop_other", "Other limit", "%", required=False, help="only when the limit is 'other'"),
            InputSpec("insulation_rating_c", "Insulation rating", "°C", default=105, help="as printed on the cable"),
            InputSpec("engine_space", "Runs through an engine space", None, kind="select", default="no", options=[{"value": "no", "label": "No"}, {"value": "yes", "label": "Yes"}]),
            InputSpec("bundled", "Bundled with other conductors", None, kind="select", default="no", options=[{"value": "no", "label": "No"}, {"value": "yes", "label": "Yes"}]),
            InputSpec("bundled_conductors", "Current-carrying conductors in the bundle", None, required=False, help="this circuit's two included"),
            InputSpec("load_type", "Load", None, kind="select", default="resistive", options=[{"value": k, "label": v["label"]} for k, v in DEVICE_PROFILES.items()]),
            InputSpec("short_circuit_a", "Source short-circuit current", "A", required=False, entity_types=["current"], qualifiers=["short circuit", "short-circuit", "fault"], help="from the battery datasheet"),
            InputSpec("manufacturer_fuse", "Maker's stated fuse", "A", required=False, entity_types=["fuse", "breaker"], qualifiers=["recommended", "required"]),
            InputSpec("own_ampacity_a", "Allowable current from the page", "A", required=False, answers="conductor.ampacity.size_awg"),
            InputSpec("own_bundling_factor", "Bundling factor from the page", None, required=False, answers="conductor.ampacity.size_awg"),
            InputSpec("own_k", "K from the page", None, required=False, answers="conductor.voltage_drop.cm_required"),
            InputSpec("own_short_circuit_a", "Source short-circuit current from the datasheet", "A", required=False, answers="protection.interrupting.required_a"),
        ],
        outputs=[{"key": "size_awg", "label": "Conductor size"}, {"key": "fuse_a", "label": "Fuse or breaker", "unit": "A"}],
        notes=["Every table value cites its page in your confirmed copy of ABYC E-11. What the tables do not cover comes back blank, with a box for the value from the page; what you type is marked as yours."],
        excel=[],
    ),
    _circuit_e11,
)


REGISTRY: dict[str, Calculator] = {
    c.spec.id: c
    for c in (CIRCUIT_E11, DC_CURRENT, INVERTER_DC_CURRENT, VOLTAGE_DROP, BATTERY_RUNTIME, ALTERNATOR_CHARGING, AC_LOAD, FUSE_PROTECTION)
}


def get_calculator(calc_id: str) -> Calculator:
    try:
        return REGISTRY[calc_id]
    except KeyError as exc:
        raise CalculationError(f"Unknown calculator '{calc_id}'") from exc


def list_specs() -> list[CalculatorSpec]:
    return [c.spec for c in REGISTRY.values()]
