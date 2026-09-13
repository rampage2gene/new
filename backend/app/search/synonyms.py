"""Marine-electrical synonym groups for query expansion."""
from __future__ import annotations

import re

SYNONYM_GROUPS: list[list[str]] = [
    ["battery charger", "charger", "charging system", "ac charger", "shore power charger", "shore charger", "mains charger", "battery charging source", "charging source"],
    ["inverter/charger", "inverter charger", "combi", "multiplus", "quattro", "inverter-charger"],
    ["inverter", "power inverter", "sine wave inverter", "dc-ac converter"],
    ["fuse", "fuses", "fusing", "fuse rating", "overcurrent protection", "ocpd", "circuit protection", "protection device"],
    ["breaker", "circuit breaker", "cb", "mcb", "breakers", "overcurrent protection", "circuit protection"],
    ["wire size", "cable size", "wire gauge", "cable gauge", "awg", "conductor size", "cross section", "mm²", "wire", "cable", "conductor"],
    ["battery", "batteries", "battery bank", "house bank", "lifepo4", "agm", "lithium"],
    ["bms", "battery management system", "battery management"],
    ["alternator", "alternators", "engine charging", "alternator charging", "external regulator"],
    ["generator", "genset", "generators", "gen set"],
    ["dc-dc", "dc/dc", "dc to dc", "battery to battery", "b2b", "dc-dc charger", "dc-dc converter"],
    ["solar", "pv", "photovoltaic", "solar panel", "solar controller", "mppt", "charge controller"],
    ["busbar", "bus bar", "bus-bar", "distribution bar", "power post"],
    ["torque", "tightening torque", "torque setting", "tighten", "nm", "n·m", "in-lb", "ft-lb"],
    ["voltage", "volts", "v", "vdc", "vac", "nominal voltage", "system voltage"],
    ["current", "amps", "amperes", "a", "amperage", "load current", "rated current"],
    ["power", "watts", "w", "kw", "output power", "rated power", "continuous power"],
    ["clearance", "ventilation", "airflow", "spacing", "mounting space", "installation clearance"],
    ["shore power", "shore", "dock power", "ac inlet", "shore inlet", "mains input", "ac input", "grid"],
    ["ground", "grounding", "earth", "earthing", "bonding", "chassis ground", "pe"],
    ["negative", "return", "neg", "-", "ground return"],
    ["positive", "pos", "+", "supply"],
    ["temperature", "temp", "thermal", "derating", "operating temperature", "ambient"],
    ["capacity", "ah", "amp hours", "amp-hours", "kwh", "battery capacity"],
    ["remote", "remote panel", "control panel", "display", "remote switch", "on/off remote"],
    ["installation", "install", "mounting", "mount", "fitting"],
    ["warning", "caution", "danger", "notice", "safety"],
    ["specifications", "specs", "technical data", "ratings", "datasheet", "specification"],
    ["efficiency", "losses", "conversion efficiency"],
    ["surge", "peak", "inrush", "starting current", "startup"],
    ["continuous", "rated", "nominal", "steady state"],
    ["low voltage disconnect", "lvd", "low battery cutoff", "undervoltage", "shutdown voltage"],
    ["absorption", "bulk", "float", "equalize", "charge profile", "charge algorithm", "charge voltage"],
]

_INDEX: dict[str, set[str]] = {}
for group in SYNONYM_GROUPS:
    for term in group:
        _INDEX.setdefault(term.lower(), set()).update(t.lower() for t in group)


def expand_terms(query: str) -> dict[str, set[str]]:
    """Return {original phrase: {synonyms}} for phrases in the query that have synonyms.
    Longer phrases are matched first so 'battery charger' isn't split into 'battery' + 'charger'."""
    q = query.lower()
    result: dict[str, set[str]] = {}
    phrases = sorted(_INDEX.keys(), key=len, reverse=True)
    consumed = [False] * len(q)
    for phrase in phrases:
        if len(phrase) < 2:
            continue
        for m in re.finditer(r"(?<![\w])" + re.escape(phrase) + r"(?:e?s)?(?![\w])", q):
            if any(consumed[m.start():m.end()]):
                continue
            for i in range(m.start(), m.end()):
                consumed[i] = True
            result[phrase] = _INDEX[phrase] - {phrase}
    return result
