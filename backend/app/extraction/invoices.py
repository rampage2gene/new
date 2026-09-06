"""Invoice / receipt extraction: vendor, number, date, line items, totals."""
from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict

from ..ingest.types import RawPage
from ..structure.metadata import DATE_RE

MONEY = r"(?P<cur>[$€£]|USD|EUR|GBP|CAD|AUD)?\s*(?P<amt>-?\d{1,3}(?:,\d{3})*(?:\.\d{2})|-?\d+\.\d{2})"
MONEY_RE = re.compile(MONEY)
INVOICE_NO_RE = re.compile(r"\b(?:invoice|inv\.?|receipt|order|ref(?:erence)?|document)\s*(?:no\.?|number|#|id)?\s*[:#]?\s*(?=[A-Z0-9\-/]*\d)([A-Z0-9][A-Z0-9\-/]{2,24})\b", re.I)
TOTAL_RE = re.compile(r"\b(?P<label>grand total|total due|amount due|balance due|total amount|invoice total|total)\b\s*[:]?\s*" + MONEY, re.I)
SUBTOTAL_RE = re.compile(r"\b(?:sub\s*-?total|net(?: total)?|merchandise)\b\s*[:]?\s*" + MONEY, re.I)
TAX_RE = re.compile(r"\b(?:tax|vat|gst|hst|pst|sales tax)\b(?:\s*\(?\d+(?:\.\d+)?\s*%\)?)?\s*[:]?\s*" + MONEY, re.I)
CURRENCY_WORD = re.compile(r"\b(USD|EUR|GBP|CAD|AUD|NZD|CHF)\b")
QTY_UNIT = r"(?P<qty>\d+(?:\.\d+)?)\s*(?P<uom>ft|feet|foot|m|pcs?|pc|ea|each|units?|x|rolls?|m²|lbs?|kg|hrs?|hours?)?"
# "Marine Wire 4 AWG  20 ft  $3.96  $79.20"  or "2 x Fuse 300A @ 12.50 = 25.00"
LINE_RE = re.compile(
    rf"^(?P<desc>[A-Za-z][^\n$€£]{{2,90}}?)\s+{QTY_UNIT}\s*(?:@|x|×)?\s*(?:[$€£]\s*)?(?P<unit_price>\d+(?:,\d{{3}})*\.\d{{2,4}})(?:\s*(?:/|per)\s*(?:ft|foot|m|ea|each|unit|pc))?\s+(?:[$€£]\s*)?(?P<total>\d+(?:,\d{{3}})*\.\d{{2}})\s*$",
    re.I,
)
LINE_QTY_FIRST_RE = re.compile(
    rf"^(?P<qty>\d+(?:\.\d+)?)\s*(?P<uom>ft|pcs?|ea|each|x|units?)?\s+(?P<desc>[A-Za-z][^\n$€£]{{2,90}}?)\s+(?:[$€£]\s*)?(?P<unit_price>\d+(?:,\d{{3}})*\.\d{{2,4}})\s+(?:[$€£]\s*)?(?P<total>\d+(?:,\d{{3}})*\.\d{{2}})\s*$",
    re.I,
)
LINE_SIMPLE_RE = re.compile(r"^(?P<desc>[A-Za-z][^\n$€£]{2,90}?)\s+(?:[$€£]\s*)?(?P<total>\d+(?:,\d{3})*\.\d{2})\s*$")
SKIP_LINE = re.compile(r"\b(total|subtotal|tax|vat|balance|amount due|payment|paid|change|tendered|discount|shipping|freight)\b", re.I)


def _money(s: str) -> float | None:
    try:
        return float(s.replace(",", ""))
    except ValueError:
        return None


@dataclass
class LineItem:
    description: str
    quantity: float | None
    unit: str | None
    unit_price: float | None
    total: float | None
    page: int
    bbox: list[float]
    confidence: float = 0.7


@dataclass
class InvoiceData:
    vendor: str | None = None
    invoice_number: str | None = None
    invoice_date: str | None = None
    currency: str | None = None
    subtotal: float | None = None
    tax: float | None = None
    total: float | None = None
    line_items: list[LineItem] = field(default_factory=list)
    confidence: float = 0.5

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


def extract_invoice(pages: list[RawPage], manufacturer_hint: str | None = None) -> InvoiceData:
    inv = InvoiceData()
    text = "\n".join(p.text for p in pages)
    # Vendor: first prominent block on page 1 (largest font) that isn't the word invoice.
    if pages:
        cands = [b for b in pages[0].blocks if b.text.strip() and len(b.text) < 80 and not re.search(r"\binvoice|receipt|tax\b", b.text, re.I)]
        cands.sort(key=lambda b: (b.font_size or 0), reverse=True)
        if cands:
            inv.vendor = cands[0].text.replace("\n", " ").strip()
    if manufacturer_hint and (not inv.vendor or len(inv.vendor) < 3):
        inv.vendor = manufacturer_hint
    for m in INVOICE_NO_RE.finditer(text):
        if re.search(r"\d", m.group(1)):
            inv.invoice_number = m.group(1)
            break
    d = DATE_RE.search(text)
    if d:
        inv.invoice_date = d.group(1)
    cm = CURRENCY_WORD.search(text)
    if cm:
        inv.currency = cm.group(1)
    else:
        sym = re.search(r"[$€£]", text)
        inv.currency = {"$": "USD", "€": "EUR", "£": "GBP"}.get(sym.group(0)) if sym else None

    totals = list(TOTAL_RE.finditer(text))
    if totals:
        # Prefer explicit grand/amount-due labels; else the last "total".
        pref = [t for t in totals if t.group("label").lower() != "total"]
        chosen = (pref or totals)[-1]
        inv.total = _money(chosen.group("amt"))
    sm = SUBTOTAL_RE.search(text)
    if sm:
        inv.subtotal = _money(sm.group("amt"))
    tm = TAX_RE.search(text)
    if tm:
        inv.tax = _money(tm.group("amt"))

    for page in pages:
        for b in page.blocks:
            if b.block_type in ("header", "footer", "page_number"):
                continue
            rows: list[str]
            if b.table:
                rows = ["  ".join(c for c in r if c) for r in b.table.get("rows", [])]
            else:
                rows = b.lines or b.text.split("\n")
            for ln in rows:
                s = ln.strip()
                if not s or SKIP_LINE.search(s):
                    continue
                for pat, conf in ((LINE_RE, 0.85), (LINE_QTY_FIRST_RE, 0.85), (LINE_SIMPLE_RE, 0.55)):
                    mm = pat.match(s)
                    if not mm:
                        continue
                    gd = mm.groupdict()
                    qty = float(gd["qty"]) if gd.get("qty") else None
                    unit_price = _money(gd["unit_price"]) if gd.get("unit_price") else None
                    total = _money(gd["total"]) if gd.get("total") else None
                    if conf < 0.8 and total is not None and (inv.total is not None and total >= inv.total * 0.999):
                        break  # this is the total line
                    if qty and unit_price and total and abs(qty * unit_price - total) < max(0.05, 0.02 * total):
                        conf = 0.95
                    inv.line_items.append(
                        LineItem(
                            description=gd["desc"].strip(" -:"),
                            quantity=qty,
                            unit=(gd.get("uom") or None),
                            unit_price=unit_price,
                            total=total,
                            page=page.page_number,
                            bbox=list(b.bbox),
                            confidence=conf,
                        )
                    )
                    break
    if inv.line_items:
        s = sum(li.total or 0 for li in inv.line_items)
        if inv.subtotal is None and inv.total is not None and abs(s - inv.total) < 0.05:
            inv.subtotal = s
        inv.confidence = min(0.95, 0.5 + 0.1 * len(inv.line_items)) if inv.total else 0.6
    return inv
