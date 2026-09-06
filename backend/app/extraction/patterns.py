"""Regular expressions for electrical quantities and devices.

Patterns are deliberately strict about what may follow a unit so that
``48 V`` is never read out of ``480 V``, ``4 AWG`` never out of ``4/0 AWG``,
``A`` is never matched inside ``AWG``/``AC``/``Ah``, and ``V`` never inside ``VA``.
"""
from __future__ import annotations

import re

NUM = r"(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"
SNUM = r"-?" + NUM
# A number may be a range: "10-15 A", "12 to 15 V", "-20 ~ +50 °C"
RANGE = rf"(?P<lo>{SNUM})[ \t]*(?:to|-|–|—|~|/)[ \t]*\+?(?P<hi>{SNUM})"

_END = r"(?![A-Za-z0-9²])"  # unit must not continue into another word

AWG_RE = re.compile(
    r"(?<![\w/.\-])(?:#[ \t]*)?(?P<awg>[1-4][ \t]*/[ \t]*0|0000|000|00|\d{1,2})[ \t]*(?:AWG|awg|Awg|B&S)" + _END
)
AWG_REV_RE = re.compile(r"\bAWG[ \t]*#?[ \t]*(?P<awg>[1-4]/0|\d{1,2})(?![\w/])")
AWG_GAUGE_RE = re.compile(r"(?<![\w/.\-])(?P<awg>[1-4]/0|\d{1,2})[ \t]*(?:ga\.|gauge)" + _END, re.I)
MM2_RE = re.compile(rf"(?<![\w.])(?P<num>{NUM})[ \t]*mm²" + _END)
KCMIL_RE = re.compile(rf"(?<![\w.])(?P<num>{NUM})[ \t]*(?:kcmil|MCM)" + _END)

VOLTAGE_RE = re.compile(
    rf"(?<![\w.\-])(?:(?:{RANGE})|(?P<num>{SNUM}))[ \t]*(?P<unit>kV|mV|VDC|VAC|V(?:olts?)?)(?:[ \t]*(?P<ac>DC|AC|dc|ac)(?![A-Za-z]))?" + _END
)
CURRENT_RE = re.compile(
    rf"(?<![\w.\-])(?:(?:{RANGE})|(?P<num>{SNUM}))[ \t]*(?P<unit>kA|mA|A|amps?|amperes?|Amps?)(?![A-Za-z0-9/²])"
)
CAPACITY_RE = re.compile(rf"(?<![\w.])(?P<num>{NUM})[ \t]*(?P<unit>Ah|Ah|amp[- ]?hours?|kWh|Wh)" + _END, re.I)
POWER_RE = re.compile(rf"(?<![\w.])(?P<num>{NUM})[ \t]*(?P<unit>kW|W|kVA|VA|watts?|hp|HP|BTU(?:/h(?:r)?)?)" + _END)
FREQ_RE = re.compile(rf"(?<![\w.])(?P<num>{NUM})[ \t]*(?P<unit>k?Hz)" + _END)
TORQUE_RE = re.compile(
    rf"(?<![\w.])(?P<num>{NUM})[ \t]*(?P<unit>N·m|N\.m|Nm|in[- ]?lbs?|lb[- ]?in|ft[- ]?lbs?|lb[- ]?ft|lbf[·. ]?ft|lbf[·. ]?in|kgf[·. ]?cm)" + _END
)
TEMP_RE = re.compile(rf"(?<![\w.])(?:(?:{RANGE})|(?P<num>{SNUM}))[ \t]*(?:°[ \t]*|deg(?:rees)?[ \t]*)(?P<unit>[CF])" + _END)
RESISTANCE_RE = re.compile(rf"(?<![\w.])(?P<num>{NUM})[ \t]*(?P<unit>mΩ|Ω|kΩ|ohms?|milliohms?)" + _END, re.I)
LENGTH_RE = re.compile(rf"(?<![\w.])(?P<num>{NUM})[ \t]*(?P<unit>mm|cm|m|in(?:ch(?:es)?)?|\"|ft|feet|')" + _END)
TERMINAL_RE = re.compile(r"\b(?P<term>M\d{1,2}|\d/\d{1,2}[ \t]*(?:\"|in(?:ch)?)|#\d{1,2}(?=[ \t]*(?:stud|screw|terminal|bolt)))(?:[ \t]*(?:stud|bolt|terminal|screw|nut))?\b")
FUSE_CLASS_RE = re.compile(
    r"\b(Class[ \t]*[TJGRKL]{1,2}|ANL|MRBF|MEGA|MIDI|AMI|AMG|ATO|ATC|MAXI|AGU|ANN|JLLN|JLLS|terminal[- ]fuse|slow[- ]blow|fast[- ]acting|time[- ]delay|dual[- ]element|gG|aM|NH\d?|cartridge)\b",
    re.I,
)
BREAKER_TYPE_RE = re.compile(
    r"\b(thermal[- ]magnetic|hydraulic[- ]magnetic|magnetic|thermal|DIN[- ]rail|ELCI|GFCI|RCD|RCBO|MCB|double[- ]pole|single[- ]pole|2[- ]?pole|1[- ]?pole|3[- ]?pole|trip[- ]free|push[- ]button|panel[- ]mount|surface[- ]mount|Type [A-D])\b",
    re.I,
)
MODEL_RE = re.compile(r"(?<![\w\-/])([A-Z]{2,8}(?:[- ]?[A-Z0-9]{1,6})?[- ]?\d{2,5}(?:[- /]?[A-Z0-9]{1,8})*)(?![\w\-/])")

FUSE_CTX = re.compile(r"\bfus(?:e|es|ed|ing)\b", re.I)
BREAKER_CTX = re.compile(r"\b(?:circuit[- ]?breakers?|breakers?|\bCB\b|MCB|RCBO|RCD|ELCI|GFCI)\b", re.I)
PROTECTION_CTX = re.compile(r"\b(?:overcurrent|over-current|protection device|OCPD|protective device)\b", re.I)
WIRE_CTX = re.compile(r"\b(?:cable|wire|wiring|conductor|lead|gauge|size)\b", re.I)

QUALIFIERS: list[tuple[str, re.Pattern]] = [
    ("continuous", re.compile(r"\bcontinuous(?:ly)?\b|\bcont\.", re.I)),
    ("peak", re.compile(r"\bpeak\b", re.I)),
    ("surge", re.compile(r"\bsurge\b|\binrush\b|\bstart(?:ing|-up)?\b(?=.{0,20}current)", re.I)),
    ("maximum", re.compile(r"\bmax(?:imum)?\.?\b|\bup to\b|\bnot exceed\b|\bno more than\b|\bat most\b", re.I)),
    ("minimum", re.compile(r"\bmin(?:imum)?\.?\b|\bat least\b|\bno less than\b|\bnot less than\b", re.I)),
    ("nominal", re.compile(r"\bnominal\b|\brated\b|\brating\b", re.I)),
    ("recommended", re.compile(r"\brecommend(?:ed|s|ation)?\b|\bsuggest(?:ed)?\b", re.I)),
    ("required", re.compile(r"\brequired?\b|\bmust\b|\bshall\b|\bmandatory\b", re.I)),
    ("input", re.compile(r"\binput\b|\bincoming\b|\bsupply\b", re.I)),
    ("output", re.compile(r"\boutput\b|\bload\b|\boutgoing\b", re.I)),
    ("charging", re.compile(r"\bcharg(?:e|ing|er)\b|\babsorption\b|\bbulk\b|\bfloat\b|\bequali[sz]", re.I)),
    ("idle", re.compile(r"\bidle\b|\bno[- ]load\b|\bstandby\b|\bquiescent\b|\bself[- ]consumption\b", re.I)),
    ("short_circuit", re.compile(r"\bshort[- ]circuit\b|\bfault current\b|\binterrupt(?:ing)? (?:capacity|rating)\b|\bAIC\b|\bbreaking capacity\b", re.I)),
    ("cutoff", re.compile(r"\bcut[- ]?off\b|\bshut[- ]?down\b|\bdisconnect\b|\balarm\b|\brestart\b", re.I)),
    ("operating", re.compile(r"\boperat(?:ing|ion|e)\b|\bworking\b|\bambient\b", re.I)),
    ("storage", re.compile(r"\bstorage\b|\bstore[d]?\b", re.I)),
    ("derating", re.compile(r"\bderat(?:e|ing)\b", re.I)),
]

CIRCUIT_DC = re.compile(r"\bDC\b|\bVDC\b|\bbattery\b|\bbatteries\b|\bsolar\b|\bPV\b|\balternator\b|\bnegative\b|\bpositive\b|\bbus ?bar\b", re.I)
CIRCUIT_AC = re.compile(r"\bAC\b|\bVAC\b|\bshore\b|\bgenerator\b|\bgenset\b|\bmains\b|\bgrid\b|\butility\b|\bneutral\b|\bline\b|\bhot\b|\bphase\b", re.I)
CIRCUIT_CONTROL = re.compile(r"\bcontrol\b|\bremote\b|\bsignal\b|\bsense\b|\bsensor\b|\bcommunication\b|\bVE\.Bus\b|\bCAN\b|\bdata\b|\bpanel\b|\bswitch wire\b", re.I)

APPLICATION_PHRASES: list[tuple[str, re.Pattern]] = [
    ("Battery cable", re.compile(r"\bbattery (?:cable|lead|wire|connection|positive|negative)s?\b", re.I)),
    ("DC input", re.compile(r"\bDC (?:input|supply|feed|connection)\b", re.I)),
    ("DC output", re.compile(r"\bDC output\b", re.I)),
    ("AC input", re.compile(r"\bAC[- ]?(?:in(?:put)?|supply|feed|source)\b|\bshore[- ]?power (?:input|inlet|cord)\b", re.I)),
    ("AC output", re.compile(r"\bAC[- ]?out(?:put)?\b", re.I)),
    ("Inverter connection", re.compile(r"\binverter (?:cable|connection|input|wiring|lead)s?\b", re.I)),
    ("Charger output", re.compile(r"\bcharger (?:output|cable|connection)s?\b", re.I)),
    ("Alternator output", re.compile(r"\balternator (?:output|cable|lead|wire|connection|B\+)s?\b", re.I)),
    ("Solar / PV input", re.compile(r"\b(?:solar|PV|panel) (?:input|cable|wire|array|string)s?\b", re.I)),
    ("Grounding / bonding", re.compile(r"\b(?:ground(?:ing)?|earth(?:ing)?|bonding|chassis) (?:cable|wire|conductor|lead|connection|strap)s?\b|\bgrounding\b|\bbonding\b", re.I)),
    ("Remote / control", re.compile(r"\b(?:remote|control|signal|sense|sensor|communication|switch|panel|display) (?:cable|wire|wiring|lead|connection|line)s?\b", re.I)),
    ("Temperature sensor", re.compile(r"\btemp(?:erature)? sens(?:or|e)\b", re.I)),
    ("Voltage sense", re.compile(r"\bvoltage sense\b|\bsense (?:wire|lead)s?\b", re.I)),
    ("Bus bar", re.compile(r"\bbus ?bars?\b", re.I)),
    ("Shore power", re.compile(r"\bshore[- ]?power\b", re.I)),
    ("Generator", re.compile(r"\bgenerator\b|\bgenset\b", re.I)),
    ("Windlass / thruster", re.compile(r"\bwindlass\b|\bthruster\b", re.I)),
    ("Starter", re.compile(r"\bstarter\b|\bstart(?:ing)? battery\b", re.I)),
]

EQUIPMENT_TERMS: list[tuple[str, re.Pattern]] = [
    ("inverter/charger", re.compile(r"\binverter[/ -]chargers?\b|\bcombi\b|\bmultiplus\b|\bquattro\b", re.I)),
    ("inverter", re.compile(r"\binverters?\b", re.I)),
    ("battery charger", re.compile(r"\bbattery chargers?\b|\b(?:AC|shore|mains) chargers?\b", re.I)),
    ("dc-dc charger", re.compile(r"\bDC[- /]?DC (?:chargers?|converters?)\b|\bDC to DC\b|\bbattery[- ]to[- ]battery\b|\bB2B\b", re.I)),
    ("solar controller", re.compile(r"\b(?:solar|PV) (?:charge )?controllers?\b|\bMPPT\b|\bPWM (?:charge )?controllers?\b", re.I)),
    ("alternator", re.compile(r"\balternators?\b", re.I)),
    ("generator", re.compile(r"\bgenerators?\b|\bgensets?\b", re.I)),
    ("battery bank", re.compile(r"\bbattery banks?\b|\bhouse bank\b", re.I)),
    ("battery", re.compile(r"\bbatter(?:y|ies)\b", re.I)),
    ("bms", re.compile(r"\bBMS\b|\bbattery management system\b", re.I)),
    ("busbar", re.compile(r"\bbus ?bars?\b", re.I)),
    ("battery switch", re.compile(r"\bbattery (?:selector )?switch(?:es)?\b|\bisolator switch\b|\bdisconnect switch\b", re.I)),
    ("relay", re.compile(r"\brelays?\b|\bVSR\b|\bACR\b", re.I)),
    ("contactor", re.compile(r"\bcontactors?\b|\bsolenoids?\b", re.I)),
    ("circuit breaker", re.compile(r"\bcircuit breakers?\b|\bbreakers?\b", re.I)),
    ("fuse", re.compile(r"\bfuses?\b|\bfuse (?:block|holder)s?\b", re.I)),
    ("distribution panel", re.compile(r"\bdistribution panels?\b|\bbreaker panels?\b|\bswitch panels?\b|\bDC panel\b|\bAC panel\b", re.I)),
    ("shunt", re.compile(r"\bshunts?\b", re.I)),
    ("battery monitor", re.compile(r"\bbattery monitors?\b", re.I)),
    ("isolation transformer", re.compile(r"\bisolation transformers?\b", re.I)),
    ("galvanic isolator", re.compile(r"\bgalvanic isolators?\b", re.I)),
    ("transfer switch", re.compile(r"\btransfer switch(?:es)?\b", re.I)),
]

WARNING_CTX = re.compile(r"\b(WARNING|DANGER|CAUTION|NOTICE)\b")
SAFETY_CRITICAL_TYPES = {"voltage", "current", "fuse", "breaker", "wire_size", "torque", "temperature"}


def parse_number(text: str) -> float | None:
    try:
        return float(text.replace(",", ""))
    except (TypeError, ValueError):
        return None


AWG_ORDER = {"4/0": -3, "3/0": -2, "2/0": -1, "1/0": 0}
AWG_MM2 = {  # nominal cross-section, mm²
    "4/0": 107.2, "3/0": 85.0, "2/0": 67.4, "1/0": 53.5, "1": 42.4, "2": 33.6, "3": 26.7, "4": 21.2,
    "5": 16.8, "6": 13.3, "7": 10.5, "8": 8.37, "9": 6.63, "10": 5.26, "11": 4.17, "12": 3.31,
    "13": 2.62, "14": 2.08, "15": 1.65, "16": 1.31, "17": 1.04, "18": 0.823, "19": 0.653, "20": 0.518,
    "21": 0.410, "22": 0.326, "23": 0.258, "24": 0.205, "25": 0.162, "26": 0.129, "27": 0.102, "28": 0.081,
    "29": 0.0642, "30": 0.0509,
}


def normalise_awg(raw: str) -> str | None:
    r = raw.replace(" ", "")
    if r in ("0000",):
        return "4/0"
    if r == "000":
        return "3/0"
    if r == "00":
        return "2/0"
    if r == "0":
        return "1/0"
    if re.fullmatch(r"[1-4]/0", r):
        return r
    if re.fullmatch(r"\d{1,2}", r):
        n = int(r)
        if 1 <= n <= 40:
            return str(n)
    return None


def awg_numeric(awg: str) -> float:
    return float(AWG_ORDER.get(awg, awg if awg not in AWG_ORDER else 0))
