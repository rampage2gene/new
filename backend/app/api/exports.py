"""Invoices and exports (CSV / XLSX / JSON)."""
from __future__ import annotations

import csv
import io
import json

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Document, Entity, Invoice
from .serializers import entity_dict

router = APIRouter(prefix="/api", tags=["exports"])

ENTITY_COLUMNS = ["document_name", "entity_type", "value_text", "value", "unit", "qualifier", "application", "circuit", "equipment", "equipment_model", "device_type", "page", "section", "confidence", "ocr_confidence", "snippet", "flags"]
LINE_COLUMNS = ["vendor", "invoice_number", "invoice_date", "currency", "description", "quantity", "unit", "unit_price", "total", "page", "document_name"]


def _invoice_dict(inv: Invoice, doc: Document) -> dict:
    return {
        "id": inv.id,
        "document_id": inv.document_id,
        "document_name": doc.title or doc.filename,
        "vendor": inv.vendor,
        "invoice_number": inv.invoice_number,
        "invoice_date": inv.invoice_date,
        "currency": inv.currency,
        "subtotal": inv.subtotal,
        "tax": inv.tax,
        "total": inv.total,
        "line_items": inv.line_items or [],
        "confidence": inv.confidence,
    }


@router.get("/invoices")
def list_invoices(db: Session = Depends(get_db)) -> list[dict]:
    rows = db.execute(select(Invoice, Document).join(Document, Invoice.document_id == Document.id)).all()
    return [_invoice_dict(inv, doc) for inv, doc in rows]


@router.get("/documents/{document_id}/invoice")
def get_invoice(document_id: str, db: Session = Depends(get_db)) -> dict:
    row = db.execute(select(Invoice, Document).join(Document, Invoice.document_id == Document.id).where(Invoice.document_id == document_id)).first()
    if not row:
        raise HTTPException(404, "No invoice data for this document")
    return _invoice_dict(*row)


def _tabular_response(rows: list[dict], columns: list[str], fmt: str, filename: str) -> Response:
    if fmt == "json":
        return Response(json.dumps(rows, indent=2, default=str), media_type="application/json", headers={"Content-Disposition": f'attachment; filename="{filename}.json"'})
    if fmt == "xlsx":
        from openpyxl import Workbook

        wb = Workbook()
        ws = wb.active
        ws.title = filename[:30]
        ws.append(columns)
        for r in rows:
            ws.append([_cell(r.get(c)) for c in columns])
        buf = io.BytesIO()
        wb.save(buf)
        return Response(buf.getvalue(), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": f'attachment; filename="{filename}.xlsx"'})
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=columns, extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow({c: _cell(r.get(c)) for c in columns})
    return Response(buf.getvalue(), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{filename}.csv"'})


def _cell(v):
    if isinstance(v, (list, dict)):
        return json.dumps(v, default=str) if v else ""
    return v


@router.get("/export/entities")
def export_entities(format: str = Query(default="csv", pattern="^(csv|xlsx|json)$"), document_ids: list[str] | None = Query(default=None), entity_type: list[str] | None = Query(default=None), db: Session = Depends(get_db)) -> Response:
    stmt = select(Entity, Document).join(Document, Entity.document_id == Document.id)
    if document_ids:
        stmt = stmt.where(Entity.document_id.in_(document_ids))
    if entity_type:
        stmt = stmt.where(Entity.entity_type.in_(entity_type))
    rows = [entity_dict(e, d.title or d.filename) for e, d in db.execute(stmt.order_by(Entity.document_id, Entity.page_number)).all()]
    for r in rows:
        r["flags"] = "; ".join(f.get("message", "") for f in r.get("flags", []))
    return _tabular_response(rows, ENTITY_COLUMNS, format, "technical-data")


@router.get("/export/invoices")
def export_invoices(format: str = Query(default="csv", pattern="^(csv|xlsx|json)$"), document_ids: list[str] | None = Query(default=None), report: str = Query(default="lines", pattern="^(lines|estimate|costing)$"), db: Session = Depends(get_db)) -> Response:
    stmt = select(Invoice, Document).join(Document, Invoice.document_id == Document.id)
    if document_ids:
        stmt = stmt.where(Invoice.document_id.in_(document_ids))
    invoices = db.execute(stmt).all()
    if report == "lines":
        rows = []
        for inv, doc in invoices:
            for li in inv.line_items or []:
                rows.append({"vendor": inv.vendor, "invoice_number": inv.invoice_number, "invoice_date": inv.invoice_date, "currency": inv.currency, **{k: li.get(k) for k in ("description", "quantity", "unit", "unit_price", "total", "page")}, "document_name": doc.title or doc.filename})
        return _tabular_response(rows, LINE_COLUMNS, format, "invoice-lines")
    if report == "estimate":
        # Project estimate: line items aggregated by description.
        agg: dict[str, dict] = {}
        for inv, _ in invoices:
            for li in inv.line_items or []:
                key = (li.get("description") or "").strip().lower()
                a = agg.setdefault(key, {"description": li.get("description"), "quantity": 0.0, "unit": li.get("unit"), "unit_price": li.get("unit_price"), "total": 0.0, "vendors": set()})
                a["quantity"] += li.get("quantity") or 0
                a["total"] += li.get("total") or 0
                if inv.vendor:
                    a["vendors"].add(inv.vendor)
        rows = [{**a, "vendors": ", ".join(sorted(a["vendors"])), "quantity": round(a["quantity"], 3), "total": round(a["total"], 2)} for a in agg.values()]
        rows.sort(key=lambda r: -(r["total"] or 0))
        rows.append({"description": "PROJECT TOTAL", "total": round(sum(r["total"] or 0 for r in rows), 2)})
        return _tabular_response(rows, ["description", "quantity", "unit", "unit_price", "total", "vendors"], format, "project-estimate")
    # costing: one row per invoice.
    rows = [{"vendor": inv.vendor, "invoice_number": inv.invoice_number, "invoice_date": inv.invoice_date, "currency": inv.currency, "line_items": len(inv.line_items or []), "subtotal": inv.subtotal, "tax": inv.tax, "total": inv.total, "document_name": doc.title or doc.filename} for inv, doc in invoices]
    rows.append({"vendor": "TOTAL", "subtotal": round(sum(r["subtotal"] or 0 for r in rows), 2), "tax": round(sum(r["tax"] or 0 for r in rows), 2), "total": round(sum(r["total"] or 0 for r in rows), 2)})
    return _tabular_response(rows, ["vendor", "invoice_number", "invoice_date", "currency", "line_items", "subtotal", "tax", "total", "document_name"], format, "job-costing")
