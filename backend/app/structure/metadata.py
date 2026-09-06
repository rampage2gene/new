"""Document-level understanding: manufacturer, product, model, type, revision, date."""
from __future__ import annotations

import re

from ..ingest.types import RawPage

KNOWN_MANUFACTURERS = [
    "Victron Energy", "Victron", "Mastervolt", "Blue Sea Systems", "Blue Sea", "Balmar", "Xantrex",
    "Magnum Energy", "MagnaSine", "Schneider Electric", "Sterling Power", "Battle Born", "Lithionics",
    "Dakota Lithium", "Relion", "Renogy", "EPEver", "Morningstar", "Outback Power", "SMA", "Fronius",
    "Enphase", "Kohler", "Onan", "Cummins", "Fischer Panda", "Northern Lights", "Westerbeke", "Yanmar",
    "Volvo Penta", "Mercury", "Yamaha", "ProMariner", "Charles Industries", "Newmar", "Analytic Systems",
    "Ancor", "Bep Marine", "BEP", "Wakespeed", "Zeus", "Orion", "Garmin", "Raymarine", "Simrad", "B&G",
    "Lowrance", "Furuno", "Bluesea", "Littelfuse", "Bussmann", "Eaton", "ABB", "Siemens", "Carling",
    "Sea Dog", "Marinco", "Hubbell", "SmartPlug", "Vetus", "Quick", "Lofrans", "Maxwell", "Lewmar",
    "Iota", "Samlex", "AIMS Power", "Go Power", "Redarc", "Enerdrive", "Kisae", "Cotek", "Nature Power",
    "Bosch", "Delco", "Prestolite", "Leece-Neville", "Hitachi", "Denso", "CTEK", "NOCO", "Optima",
    "Trojan", "Rolls", "Lifeline", "Firefly", "Odyssey", "Deka", "East Penn", "Interstate", "Exide",
    "Epoch", "KiloVault", "SOK", "Ampere Time", "LiTime", "Eco-Worthy", "Fortress Power", "Pylontech",
    "Daly", "JBD", "Orion BMS", "REC BMS", "Electrodacus", "Overkill Solar", "JK BMS",
]

DOC_TYPE_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("Invoice", re.compile(r"\b(invoice|tax invoice)\b", re.I)),
    ("Receipt", re.compile(r"\b(receipt|sales receipt|order confirmation)\b", re.I)),
    ("Bill of Materials", re.compile(r"\b(bill of materials|BOM)\b", re.I)),
    ("Parts List", re.compile(r"\b(parts? list|parts catalog(ue)?)\b", re.I)),
    ("Load Schedule", re.compile(r"\b(load schedule|load calculation|load analysis)\b", re.I)),
    ("Wiring Diagram", re.compile(r"\b(wiring diagram|schematic|single[- ]line diagram|one[- ]line diagram)\b", re.I)),
    ("Installation Manual", re.compile(r"\b(installation (and operation )?(manual|guide|instructions)|install(ation)? guide)\b", re.I)),
    ("Service Manual", re.compile(r"\b(service manual|repair manual|workshop manual|technical manual)\b", re.I)),
    ("Owner's Manual", re.compile(r"\b(owner'?s manual|operator'?s manual|operating manual|operation manual)\b", re.I)),
    ("User Manual", re.compile(r"\b(user manual|user guide|user'?s guide)\b", re.I)),
    ("Datasheet", re.compile(r"\b(data ?sheet|specification sheet|spec sheet|technical data|product specifications?)\b", re.I)),
    ("Quick Start Guide", re.compile(r"\b(quick ?start|quick guide|quick reference)\b", re.I)),
    ("Manual", re.compile(r"\bmanual\b", re.I)),
]

EQUIPMENT_KEYWORDS: dict[str, re.Pattern] = {
    "inverter/charger": re.compile(r"\binverter[/ -]?chargers?\b|\bmulti(?:plus)?\b|\bquattro\b", re.I),
    "inverter": re.compile(r"\binverters?\b", re.I),
    "battery charger": re.compile(r"\bbattery chargers?\b|\bchargers?\b", re.I),
    "battery": re.compile(r"\bbatter(?:y|ies)\b|\blifepo4\b|\bAGM\b", re.I),
    "bms": re.compile(r"\bBMS\b|\bbattery management system\b", re.I),
    "alternator": re.compile(r"\balternators?\b", re.I),
    "generator": re.compile(r"\bgenerators?\b|\bgenset\b", re.I),
    "dc-dc converter": re.compile(r"\bDC[- /]?DC\b|\bDC to DC\b|\bconverters?\b", re.I),
    "solar controller": re.compile(r"\bsolar (charge )?controllers?\b|\bMPPT\b|\bPWM controller\b", re.I),
    "busbar": re.compile(r"\bbus ?bars?\b", re.I),
    "circuit breaker": re.compile(r"\bcircuit breakers?\b|\bbreakers?\b", re.I),
    "fuse": re.compile(r"\bfuses?\b", re.I),
    "distribution panel": re.compile(r"\bdistribution panels?\b|\bswitch ?panels?\b|\bbreaker panels?\b", re.I),
    "shunt/monitor": re.compile(r"\bshunt\b|\bbattery monitor\b", re.I),
    "switch": re.compile(r"\bbattery switch(?:es)?\b|\bisolator switch\b", re.I),
    "relay/contactor": re.compile(r"\brelays?\b|\bcontactors?\b|\bsolenoids?\b", re.I),
    "shore power": re.compile(r"\bshore ?power\b|\bshore cord\b|\bisolation transformer\b|\bgalvanic isolator\b", re.I),
    "motor/pump": re.compile(r"\bwindlass\b|\bbow thruster\b|\bbilge pump\b|\bwater ?maker\b|\bmotor\b", re.I),
}

MODEL_RE = re.compile(r"\b(?:model|model no\.?|model number|type|part no\.?|p/n|item)\s*[:#]?\s*([A-Z0-9][A-Z0-9\-/\.]{2,30})", re.I)
GENERIC_MODEL_RE = re.compile(r"\b([A-Z]{2,6}[- ]?\d{2,5}[A-Z0-9\-/]{0,12})\b")
REVISION_RE = re.compile(r"\b(?:rev(?:ision)?\.?|version|ver\.?|issue)\s*[:#]?\s*([A-Z]?\d+(?:\.\d+)*[A-Z]?|[A-Z])\b|\bv(\d+(?:\.\d+)+)\b", re.I)
DATE_RE = re.compile(
    r"\b((?:\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4})|(?:\d{4}[/\-.]\d{1,2}[/\-.]\d{1,2})|"
    r"(?:(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4})|"
    r"(?:(?<![\d.])\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+\d{4})|"
    r"(?:(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+\d{4}))\b"
)


def detect_metadata(pages: list[RawPage], filename: str) -> dict:
    first_pages = pages[:3]
    front_text = "\n".join(p.text for p in first_pages)
    all_text = "\n".join(p.text for p in pages[:40])
    meta: dict = {}

    # Title: largest text block on the first page, else filename.
    title = None
    if pages:
        cands = [b for b in pages[0].blocks if b.block_type in ("heading", "paragraph", "label") and 3 <= len(b.text) <= 120]
        cands.sort(key=lambda b: (b.font_size or 0), reverse=True)
        if cands and (cands[0].font_size or 0) > 0:
            title = cands[0].text.replace("\n", " ").strip()
    meta["title"] = title or re.sub(r"[_\-]+", " ", filename.rsplit(".", 1)[0]).strip()

    # Manufacturer.
    lowered = front_text.lower()
    manufacturer = None
    for name in sorted(KNOWN_MANUFACTURERS, key=len, reverse=True):
        if name.lower() in lowered:
            manufacturer = name
            break
    if not manufacturer:
        m = re.search(r"(?:manufactured by|made by|©\s*(?:\d{4})?\s*|copyright\s*(?:\d{4})?\s*)([A-Z][A-Za-z&\- ]{2,40}?)(?:\s+(?:Inc|LLC|Ltd|B\.?V\.?|GmbH|Corp|Co)\b|[\n.,])", front_text)
        if m:
            manufacturer = m.group(1).strip()
    meta["manufacturer"] = manufacturer

    # Document type.
    doc_type = None
    for label, pat in DOC_TYPE_PATTERNS:
        if pat.search(front_text) or pat.search(filename):
            doc_type = label
            break
    if not doc_type:
        if any(p.is_diagram for p in first_pages):
            doc_type = "Wiring Diagram"
        else:
            doc_type = "Technical Document"
    meta["document_type"] = doc_type

    # Model number (not meaningful for business documents).
    model = None
    m = MODEL_RE.search(front_text) if doc_type not in ("Invoice", "Receipt") else None
    if m and not re.fullmatch(r"\d+", m.group(1)):
        model = m.group(1).strip(".,")
    if not model and doc_type not in ("Invoice", "Receipt"):
        gm = GENERIC_MODEL_RE.findall(front_text)
        if gm:
            model = max(gm, key=lambda s: (len(s), gm.count(s)))
    meta["model_number"] = model

    # Product name: title minus manufacturer/doc type words.
    product = meta["title"]
    if manufacturer:
        product = re.sub(re.escape(manufacturer), "", product, flags=re.I)
    product = re.sub(r"\b(installation|owner'?s|user|service|operation|operating)?\s*(manual|guide|instructions|datasheet)\b", "", product, flags=re.I)
    meta["product"] = product.strip(" -–:|") or None

    rm = REVISION_RE.search(front_text)
    meta["revision"] = (rm.group(1) or rm.group(2)) if rm else None
    dm = DATE_RE.search(front_text) or DATE_RE.search(all_text)
    meta["publication_date"] = dm.group(1) if dm else None

    equipment = []
    counts = {}
    for label, pat in EQUIPMENT_KEYWORDS.items():
        n = len(pat.findall(all_text))
        if n:
            counts[label] = n
    # Order by frequency, keep those with meaningful presence.
    for label, n in sorted(counts.items(), key=lambda kv: kv[1], reverse=True):
        if n >= 2 or label in ("inverter/charger", "bms", "solar controller"):
            equipment.append(label)
    meta["equipment_types"] = equipment[:8]
    return meta
