import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import type { Invoice } from "../types";

const money = (v: number | null | undefined, cur?: string | null) => (v == null ? "—" : `${cur === "USD" ? "$" : cur === "EUR" ? "€" : cur === "GBP" ? "£" : ""}${v.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`);

export default function InvoicesPage() {
  const [invoices, setInvoices] = useState<Invoice[] | null>(null);
  const navigate = useNavigate();
  useEffect(() => { api.invoices().then(setInvoices); }, []);
  const total = invoices?.reduce((a, i) => a + (i.total || 0), 0) || 0;
  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1>Invoices, Receipts & Parts</h1>
          <p>Vendor, invoice number, date, line items and totals extracted from uploaded invoices and receipts. Export to CSV / Excel / JSON, or build a project estimate and job-costing report.</p>
        </div>
        <div className="row">
          {["lines", "estimate", "costing"].map((r) => (
            <span key={r} className="row" style={{ gap: 4 }}>
              <span className="small muted" style={{ textTransform: "capitalize" }}>{r === "lines" ? "Line items" : r === "estimate" ? "Project estimate" : "Job costing"}:</span>
              {["csv", "xlsx", "json"].map((f) => <a key={f} className="btn sm" href={api.exportInvoicesUrl(f, r)}>{f.toUpperCase()}</a>)}
            </span>
          ))}
        </div>
      </div>
      {!invoices ? <span className="spinner" /> : invoices.length === 0 ? <div className="empty">No invoices yet. Upload an invoice or receipt PDF/photo in the Document Library; documents recognised as invoices are parsed automatically.</div> : (
        <>
          <div className="card tight row"><b>{invoices.length} invoice{invoices.length === 1 ? "" : "s"}</b><span className="muted">·</span><span>Total {money(total, invoices[0].currency)}</span></div>
          {invoices.map((inv) => (
            <div key={inv.id} className="card">
              <div className="row">
                <div className="grow">
                  <h3>{inv.vendor || "Unknown vendor"} <span className="muted">· {inv.invoice_number || "no number"}</span></h3>
                  <div className="small muted">{inv.invoice_date || "no date"} · {inv.currency || ""} · from <a href="#" onClick={(e) => { e.preventDefault(); navigate(`/documents/${inv.document_id}`); }}>{inv.document_name}</a> · extraction confidence {Math.round(inv.confidence * 100)}%</div>
                </div>
                <div style={{ textAlign: "right" }}>
                  <div className="small muted">Subtotal {money(inv.subtotal, inv.currency)} · Tax {money(inv.tax, inv.currency)}</div>
                  <div className="result-value">{money(inv.total, inv.currency)}</div>
                </div>
              </div>
              <div className="table-scroll">
                <table className="small" style={{ marginTop: 8 }}>
                  <thead><tr><th>Description</th><th>Qty</th><th>Unit</th><th>Unit price</th><th>Total</th><th>Conf.</th></tr></thead>
                  <tbody>
                    {inv.line_items.map((li, i) => (
                      <tr key={i} className="clickable" onClick={() => navigate(`/documents/${inv.document_id}?page=${li.page}&bbox=${li.bbox.map((n) => Math.round(n)).join(",")}`)}>
                        <td>{li.description}</td><td>{li.quantity ?? "—"}</td><td>{li.unit || ""}</td><td>{money(li.unit_price, inv.currency)}</td><td>{money(li.total, inv.currency)}</td><td><span className={`badge ${li.confidence >= 0.9 ? "ok" : li.confidence >= 0.7 ? "warn" : "crit"}`}>{Math.round(li.confidence * 100)}%</span></td>
                      </tr>
                    ))}
                    {inv.line_items.length === 0 && <tr><td colSpan={6} className="muted">No line items recognised.</td></tr>}
                  </tbody>
                </table>
              </div>
            </div>
          ))}
        </>
      )}
    </div>
  );
}
