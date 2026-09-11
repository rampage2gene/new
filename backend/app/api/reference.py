"""The owner's ABYC E-11 reference: the tables the circuit calculator computes
with, and the installation reminders.

Two copies, one view: what the person has imported, corrected and confirmed
in the app (saved under the data folder) wins over the copy bundled with the
app. Only a PUT with status "confirmed" makes a table usable - the app never
confirms a table on its own - and a download hands the confirmed set to the
e11-calc library for another web app.
"""
from __future__ import annotations

import io
import json
import re
import zipfile
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..models import Document
from ..reference import e11_cheatsheet, e11_tables
from ..reference.e11_tables import KIND_OF, TABLE_IDS, TableError

router = APIRouter(prefix="/api/reference/e11", tags=["reference"])

# The expected pages for a table are not known to the app; the person finds
# them. What the app knows is each table's layout, so the editor can draw the
# grid before a single value is in it.
LAYOUTS: dict[str, dict] = {
    "constants": {"title": "Formula constants (K for copper, and how the formula defines length)"},
    "circular_mils": {"title": "Conductor sizes and their area in circular mils", "columns": ["size_awg", "circular_mils", "mm2"]},
    "ampacity_outside_engine_space": {"title": "Allowable current, outside engine spaces (columns: insulation rating in °C)"},
    "ampacity_inside_engine_space": {"title": "Allowable current, inside engine spaces (columns: insulation rating in °C)"},
    "bundling_factors": {"title": "Correction factors for bundled conductors", "columns": ["min_conductors", "max_conductors", "factor"]},
    "voltage_drop_3pct": {"title": "Conductor sizes for a 3 % drop (rows: current; columns: length)"},
    "voltage_drop_10pct": {"title": "Conductor sizes for a 10 % drop (rows: current; columns: length)"},
    "fuse_classes": {"title": "Fuse classes and their interrupting ratings, from the makers' datasheets", "columns": ["class", "interrupting_rating_a", "voltage_rating_v", "suits"]},
}


@router.get("")
def status() -> dict:
    s = get_settings()
    tables = e11_tables.get_tables()
    rows = e11_tables.tables_status(tables)
    for r in rows:
        r["layout"] = LAYOUTS[r["id"]]
    sheet, sheet_origin = e11_cheatsheet.get_cheatsheet()
    confirmed = [r["id"] for r in rows if r["status"] == "confirmed"]
    return {
        "installed": any(r["status"] != "missing" for r in rows),
        "confirmed": confirmed,
        "missing": [r["id"] for r in rows if r["status"] == "missing"],
        "fixture": tables.fixture,
        "folders": {"yours": str(s.user_reference_dir), "bundled": str(s.reference_dir)},
        "tables": rows,
        "cheatsheet": {"entries": len(sheet["entries"]) if sheet else 0, "origin": sheet_origin},
    }


@router.get("/tables/{table_id}")
def get_table(table_id: str) -> dict:
    if table_id not in TABLE_IDS:
        raise HTTPException(404, f"No table called {table_id}")
    t = e11_tables.get_tables().by_id.get(table_id)
    if not t:
        return {"id": table_id, "kind": KIND_OF[table_id], "status": "missing", "layout": LAYOUTS[table_id]}
    return {**t, "origin": e11_tables.get_tables().origin.get(table_id), "layout": LAYOUTS[table_id]}


@router.put("/tables/{table_id}")
def put_table(table_id: str, body: dict[str, Any]) -> dict:
    """Save the person's copy of a table. `status` may be "draft" or
    "confirmed"; confirming is theirs to do, having checked the page."""
    if table_id not in TABLE_IDS:
        raise HTTPException(404, f"No table called {table_id}")
    body = {**body, "id": table_id, "kind": KIND_OF[table_id]}
    if body.get("status") not in ("draft", "confirmed"):
        raise HTTPException(422, 'status must be "draft" or "confirmed"')
    try:
        e11_tables.save_table(body)
    except TableError as exc:
        raise HTTPException(422, str(exc)) from exc
    return get_table(table_id)


@router.delete("/tables/{table_id}")
def delete_table(table_id: str) -> dict:
    if table_id not in TABLE_IDS:
        raise HTTPException(404, f"No table called {table_id}")
    e11_tables.delete_table(table_id)
    return get_table(table_id)


class ImportRequest(BaseModel):
    document_id: str
    page: int
    table_index: int = 0


_NUM = re.compile(r"[-+]?\d+(?:[.,]\d+)?")
_AWG = re.compile(r"^\s*(\d+/0|\d{1,2})\s*(?:awg)?\s*$", re.I)


def _num(cell: str) -> float | None:
    m = _NUM.search(cell or "")
    if not m:
        return None
    v = float(m.group(0).replace(",", "."))
    return int(v) if v.is_integer() else v


def _awg(cell: str) -> str | None:
    m = _AWG.match(cell or "")
    return m.group(1) if m else None


def _draft_from_rows(table_id: str, rows: list[list[str]], page: int, doc: Document) -> dict:
    """Copy what fits the table's known layout; leave the rest blank for the
    person to type. Nothing is corrected or guessed here: a cell that does
    not read as the number or size the layout expects stays empty."""
    kind = KIND_OF[table_id]
    header = [c.strip() for c in (rows[0] if rows else [])]
    body = rows[1:] if len(rows) > 1 else []
    source = {"document": doc.title or doc.filename, "table": header[0] if header else "", "page": page, "document_id": doc.id}
    base = {"id": table_id, "kind": kind, "title": LAYOUTS[table_id]["title"], "status": "draft", "source": source, "edits": {}}
    if kind == "circular_mils":
        out_rows = []
        for r in body:
            size = _awg(r[0]) if r else None
            if not size:
                continue
            out_rows.append({"size_awg": size, "circular_mils": _num(r[1]) if len(r) > 1 else None, "mm2": _num(r[2]) if len(r) > 2 else None, "page": page})
        # The loader needs a number in circular_mils; a cell that did not read is left for the person, marked.
        for r in out_rows:
            if r["circular_mils"] is None:
                r["circular_mils"] = 0
                base["edits"][f"{r['size_awg']}/circular_mils"] = "needed"
        return {**base, "rows": out_rows}
    if kind == "ampacity":
        cols = {}
        for c in header[1:]:
            n = _num(c)
            if n is not None:
                cols[str(int(n))] = "A"
        out_rows = []
        for r in body:
            size = _awg(r[0]) if r else None
            if not size:
                continue
            values = {}
            for i, col in enumerate(cols.keys(), start=1):
                values[col] = _num(r[i]) if i < len(r) else None
            out_rows.append({"size_awg": size, "values": values, "page": page})
        return {**base, "columns": cols or {"105": "A"}, "rows": out_rows}
    if kind == "bundling":
        out_rows = []
        for r in body:
            if len(r) < 2:
                continue
            nums = [_num(c) for c in r]
            rng = re.findall(r"\d+", r[0] or "")
            lo = int(rng[0]) if rng else None
            hi = int(rng[1]) if len(rng) > 1 else None
            factor = nums[-1]
            if lo is None or factor is None:
                continue
            out_rows.append({"min_conductors": lo, "max_conductors": hi, "factor": factor if factor <= 1 else factor / 100, "page": page})
        return {**base, "rows": out_rows}
    if kind == "voltage_drop_grid":
        lengths = [n for n in (_num(c) for c in header[1:]) if n is not None]
        out_rows = []
        for r in body:
            cur = _num(r[0]) if r else None
            if cur is None:
                continue
            sizes = {}
            for i, length in enumerate(lengths, start=1):
                cell = r[i] if i < len(r) else ""
                sizes[str(length)] = _awg(cell)
            out_rows.append({"current": cur, "page": page, "sizes": sizes})
        pct = 3 if table_id.endswith("3pct") else 10
        # The voltage, unit and length definition are not read from the page
        # here; they are marked for the person to check before confirming.
        edits = {"nominal_voltage": "check", "length_unit": "check", "length_definition": "check"}
        return {**base, "nominal_voltage": 12, "drop_percent": pct, "length_unit": "ft", "length_definition": "round_trip", "lengths": lengths, "rows": out_rows, "edits": edits}
    if kind == "constants":
        return {**base, "values": {"K_copper": {"value": 0, "page": page}}, "formula_as_printed": " ".join(header), "length_definition": "round_trip", "edits": {"K_copper/value": "needed", "length_definition": "check"}}
    raise HTTPException(422, "Fuse classes are typed from the makers' datasheets, not imported from a page.")


@router.post("/tables/{table_id}/import")
def import_table(table_id: str, req: ImportRequest, db: Session = Depends(get_db)) -> dict:
    """Draft a table from a table the app detected on a page of a document.
    Cells whose row label and column header fit the table's layout are
    copied; everything else stays blank for the person to type. The draft is
    saved as the person's copy, unusable until they confirm it."""
    if table_id not in TABLE_IDS:
        raise HTTPException(404, f"No table called {table_id}")
    doc = db.get(Document, req.document_id)
    if not doc:
        raise HTTPException(404, "Document not found")
    candidates = [t for t in (doc.structure or {}).get("tables", []) if t.get("page") == req.page]
    if not candidates:
        raise HTTPException(404, f"No table was detected on page {req.page} of {doc.title or doc.filename}. Open the page: if the table is there, the rows can still be typed in.")
    if req.table_index < 0 or req.table_index >= len(candidates):
        raise HTTPException(404, f"Page {req.page} has {len(candidates)} detected table(s); index {req.table_index} is out of range.")
    draft = _draft_from_rows(table_id, candidates[req.table_index].get("rows", []), req.page, doc)
    try:
        e11_tables.save_table(draft)
    except TableError as exc:
        raise HTTPException(422, f"The detected table does not fit this layout: {exc}") from exc
    return get_table(table_id)


@router.get("/documents/{document_id}/tables")
def detected_tables(document_id: str, db: Session = Depends(get_db)) -> list[dict]:
    """The tables the app detected in a document, page by page, for the import picker."""
    doc = db.get(Document, document_id)
    if not doc:
        raise HTTPException(404, "Document not found")
    out = []
    by_page: dict[int, int] = {}
    for t in (doc.structure or {}).get("tables", []):
        page = t.get("page")
        idx = by_page.get(page, 0)
        by_page[page] = idx + 1
        rows = t.get("rows", [])
        out.append({"page": page, "table_index": idx, "header": rows[0] if rows else [], "rows": len(rows), "section": t.get("section")})
    return out


@router.get("/cheatsheet")
def get_cheatsheet() -> dict:
    sheet, origin = e11_cheatsheet.get_cheatsheet()
    if not sheet:
        return {"source": None, "entries": [], "markdown": "", "origin": None}
    return {**sheet, "markdown": e11_cheatsheet.render_markdown(sheet), "origin": origin}


@router.put("/cheatsheet")
def put_cheatsheet(body: dict[str, Any]) -> dict:
    try:
        e11_cheatsheet.save_cheatsheet(body)
    except e11_cheatsheet.CheatSheetError as exc:
        raise HTTPException(422, str(exc)) from exc
    return get_cheatsheet()


@router.get("/download")
def download() -> Response:
    """The confirmed tables and the reminders, zipped in the layout the
    e11-calc library reads: tables/*.json, cheatsheet/cheatsheet.{json,md,html}."""
    tables = e11_tables.get_tables()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for tid, t in tables.by_id.items():
            if t["status"] == "confirmed":
                z.writestr(f"tables/{tid}.json", json.dumps(t, indent=2, ensure_ascii=False) + "\n")
        sheet, _ = e11_cheatsheet.get_cheatsheet()
        if sheet:
            z.writestr("cheatsheet/cheatsheet.json", json.dumps(sheet, indent=2, ensure_ascii=False) + "\n")
            z.writestr("cheatsheet/cheatsheet.md", e11_cheatsheet.render_markdown(sheet))
            z.writestr("cheatsheet/cheatsheet.html", e11_cheatsheet.render_html(sheet))
        z.writestr("README.txt", "Unzip into packages/e11-calc/ (or wherever the e11-calc library lives). Only confirmed tables are included; drafts stay in the app until you confirm them.\n")
    return Response(buf.getvalue(), media_type="application/zip", headers={"Content-Disposition": 'attachment; filename="e11-reference.zip"'})
