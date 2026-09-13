import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { DocumentDetail } from "../types";

/** Dropdown of everything that can be produced from one document. */
export default function ExportMenu({ doc }: { doc: DocumentDetail }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    if (!open) return;
    const h = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, [open]);

  const groups: { title: string; items: { label: string; href: string; hint?: string }[] }[] = [
    {
      title: "Spreadsheets",
      items: [
        { label: "Workbook with live formulas (.xlsx)", href: api.exportWorkbookUrl([doc.id]), hint: "values, tables, calculators prefilled from this document, invoices" },
        { label: "Technical data, values only (.xlsx)", href: api.exportEntitiesUrl("xlsx", [doc.id]) },
        { label: "Technical data (.csv)", href: api.exportEntitiesUrl("csv", [doc.id]) },
      ],
    },
    {
      title: "PDF",
      items: [
        { label: "Report (.pdf)", href: api.reportPdfUrl(doc.id), hint: "specification extraction and verification flags" },
        ...(doc.ocr_pages ? [{ label: "Searchable copy (.pdf)", href: api.searchablePdfUrl(doc.id), hint: "original pages with an OCR text layer" }] : []),
        { label: "Original file", href: api.originalUrl(doc.id) },
      ],
    },
    {
      title: "Text",
      items: [
        { label: "Markdown (.md)", href: api.documentExportUrl(doc.id, "md"), hint: "headings, tables and warnings" },
        { label: "Plain text (.txt)", href: api.documentExportUrl(doc.id, "txt") },
        { label: "Structured JSON (.json)", href: api.documentExportUrl(doc.id, "json") },
        { label: "Technical data (.json)", href: api.exportEntitiesUrl("json", [doc.id]) },
      ],
    },
  ];

  return (
    <span ref={ref} style={{ position: "relative" }}>
      <button className="btn sm" onClick={() => setOpen((o) => !o)}>Export ▾</button>
      {open && (
        <div className="menu" style={{ minWidth: 300 }}>
          {groups.map((g) => (
            <div key={g.title}>
              <div className="menu-title">{g.title}</div>
              {g.items.map((it) => (
                <a key={it.label} className="menu-item" href={it.href} onClick={() => setOpen(false)}>
                  <span>{it.label}</span>
                  {it.hint && <span className="small muted">{it.hint}</span>}
                </a>
              ))}
            </div>
          ))}
        </div>
      )}
    </span>
  );
}
