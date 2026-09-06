"""Visual analysis of wiring diagrams and schematics.

Claude vision produces components + connections with mandatory confidence
tiers. Without an API key a heuristic engine lists labelled components found
by OCR as *possible* and makes no connection claims.
"""
from __future__ import annotations

import base64
import logging
import re
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..extraction import patterns as P
from ..models import Block, DiagramAnalysis, Document, Page
from .client import ai_available, structured_call
from .prompts import DIAGRAM_SYSTEM

log = logging.getLogger(__name__)

Confidence = Literal["confirmed", "high", "possible", "unknown"]


class ComponentOut(BaseModel):
    id: str = Field(description="Short unique id, e.g. C1")
    type: str = Field(description="battery | inverter | inverter_charger | charger | alternator | generator | fuse | breaker | busbar | switch | contactor | relay | shunt | solar_controller | dc_dc | panel | load | other")
    label: str = Field(description="Label as printed on the drawing, or a descriptive name")
    rating: str | None = Field(default=None, description="Rating exactly as printed (e.g. '300 A Class T', '48 V 200 Ah')")
    confidence: Confidence
    bbox_pct: list[float] | None = Field(default=None, description="[x0, y0, x1, y1] as percent of image size")


class ProtectionOut(BaseModel):
    type: str
    rating: str | None = None
    confidence: Confidence


class ConnectionOut(BaseModel):
    from_id: str
    to_id: str
    polarity: Literal["positive", "negative", "ac_line", "ac_neutral", "ground", "data", "unknown"]
    circuit: Literal["dc", "ac", "unknown"]
    direction: Literal["from_to", "to_from", "bidirectional", "unknown"]
    protection: list[ProtectionOut] = Field(default_factory=list, description="Protection devices in this connection")
    confidence: Confidence
    note: str | None = None


class DiagramOut(BaseModel):
    diagram_type: str = Field(description="wiring_diagram | schematic | single_line | block_diagram | installation_drawing | not_a_diagram")
    title: str | None = None
    system_voltage: str | None = Field(default=None, description="As printed, if shown")
    components: list[ComponentOut]
    connections: list[ConnectionOut]
    unreadable_regions: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


def analyse_page(session: Session, document_id: str, page_number: int, force: bool = False) -> dict:
    existing = session.execute(
        select(DiagramAnalysis).where(DiagramAnalysis.document_id == document_id, DiagramAnalysis.page_number == page_number)
    ).scalar_one_or_none()
    if existing and not force:
        return _out(existing)
    page = session.execute(select(Page).where(Page.document_id == document_id, Page.page_number == page_number)).scalar_one_or_none()
    if page is None:
        raise ValueError("Page not found")
    result: dict
    engine: str
    if ai_available() and page.image_path:
        try:
            result = _claude_analysis(page)
            engine = "claude-vision"
        except Exception as exc:  # noqa: BLE001
            log.warning("Vision analysis failed, using heuristic: %s", exc)
            result = _heuristic_analysis(session, page)
            result["notes"].append(f"Visual AI analysis failed ({exc}); heuristic result shown.")
            engine = "heuristic"
    else:
        result = _heuristic_analysis(session, page)
        engine = "heuristic"
    if existing:
        session.delete(existing)
        session.flush()
    rec = DiagramAnalysis(document_id=document_id, page_number=page_number, engine=engine, result=result)
    session.add(rec)
    session.flush()
    return _out(rec)


def _out(rec: DiagramAnalysis) -> dict:
    return {"id": rec.id, "document_id": rec.document_id, "page": rec.page_number, "engine": rec.engine, "created_at": rec.created_at.isoformat() if rec.created_at else None, **rec.result}


def _claude_analysis(page: Page) -> dict:
    with open(page.image_path, "rb") as f:
        data = base64.standard_b64encode(f.read()).decode("ascii")
    content = [
        {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": data}},
        {
            "type": "text",
            "text": (
                f"This is page {page.page_number} of a marine electrical document"
                + (f" (OCR text on the page: {page.text[:1500]})" if page.text else "")
                + ". Identify the components and connections with confidence levels. Do not invent connections you cannot see."
            ),
        },
    ]
    out: DiagramOut = structured_call(DIAGRAM_SYSTEM, content, DiagramOut)
    d = out.model_dump()
    d["confidence_legend"] = _legend()
    return d


_COMPONENT_WORDS = [
    ("battery", re.compile(r"\bbatter(?:y|ies)\b|\bBAT\b", re.I)),
    ("inverter_charger", re.compile(r"\binverter[/ -]charger\b|\bmultiplus\b|\bquattro\b", re.I)),
    ("inverter", re.compile(r"\binverter\b", re.I)),
    ("charger", re.compile(r"\bcharger\b", re.I)),
    ("alternator", re.compile(r"\balternator\b|\bALT\b", re.I)),
    ("generator", re.compile(r"\bgenerator\b|\bgenset\b|\bGEN\b", re.I)),
    ("fuse", re.compile(r"\bfuse\b|\bF\d+\b|\bANL\b|\bMRBF\b|\bClass T\b", re.I)),
    ("breaker", re.compile(r"\bbreaker\b|\bCB\d*\b|\bMCB\b", re.I)),
    ("busbar", re.compile(r"\bbus ?bar\b|\bbus\b", re.I)),
    ("switch", re.compile(r"\bswitch\b|\bisolator\b", re.I)),
    ("contactor", re.compile(r"\bcontactor\b|\bsolenoid\b", re.I)),
    ("relay", re.compile(r"\brelay\b|\bVSR\b|\bACR\b", re.I)),
    ("shunt", re.compile(r"\bshunt\b", re.I)),
    ("solar_controller", re.compile(r"\bMPPT\b|\bsolar\b|\bPV\b", re.I)),
    ("dc_dc", re.compile(r"\bDC[- /]?DC\b|\borion\b", re.I)),
    ("panel", re.compile(r"\bpanel\b|\bdistribution\b", re.I)),
    ("load", re.compile(r"\bload\b|\bpump\b|\blights?\b|\bwindlass\b|\bthruster\b", re.I)),
]


def _heuristic_analysis(session: Session, page: Page) -> dict:
    blocks = session.execute(select(Block).where(Block.document_id == page.document_id, Block.page_number == page.page_number)).scalars().all()
    comps = []
    n = 0
    for b in blocks:
        if b.block_type in ("header", "footer", "page_number") or len(b.text) > 120:
            continue
        for ctype, pat in _COMPONENT_WORDS:
            if pat.search(b.text):
                n += 1
                rating = None
                for rp in (P.CURRENT_RE, P.VOLTAGE_RE, P.POWER_RE, P.CAPACITY_RE):
                    m = rp.search(b.text)
                    if m:
                        rating = m.group(0).strip()
                        break
                w, h = page.width or 1, page.height or 1
                comps.append(
                    {
                        "id": f"C{n}",
                        "type": ctype,
                        "label": b.text.strip().replace("\n", " ")[:80],
                        "rating": rating,
                        "confidence": "possible",
                        "bbox_pct": [round(b.x0 / w * 100, 1), round(b.y0 / h * 100, 1), round(b.x1 / w * 100, 1), round(b.y1 / h * 100, 1)],
                    }
                )
                break
    return {
        "diagram_type": "wiring_diagram" if page.is_diagram else "unknown",
        "title": None,
        "system_voltage": None,
        "components": comps,
        "connections": [],
        "unreadable_regions": [],
        "notes": [
            "Heuristic analysis: components were identified from text labels only (confidence 'possible'). "
            "Connections require the visual AI engine; configure MDI_ANTHROPIC_API_KEY to enable it.",
        ],
        "confidence_legend": _legend(),
    }


def _legend() -> dict:
    return {
        "confirmed": "Explicitly labelled and unambiguous on the drawing",
        "high": "Clearly drawn; relies on standard symbols or partly legible labels",
        "possible": "Plausible interpretation with real uncertainty - verify",
        "unknown": "Cannot be determined from the drawing",
    }
