import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, formatBytes } from "../api";
import type { DocumentSummary } from "../types";

export default function LibraryPage() {
  const [docs, setDocs] = useState<DocumentSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState<number | null>(null);
  const [over, setOver] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const refresh = useCallback(() => api.listDocuments().then(setDocs).catch((e) => setError(e.message)), []);
  useEffect(() => { refresh(); }, [refresh]);
  const busy = docs.some((d) => d.status === "queued" || d.status === "processing");
  useEffect(() => {
    if (!busy) return;
    const t = setInterval(refresh, 1500);
    return () => clearInterval(t);
  }, [busy, refresh]);

  const upload = async (files: FileList | File[]) => {
    const list = Array.from(files);
    if (!list.length) {
      setError("That drop didn't contain a file. Drag it from File Explorer, or use the “Upload documents” button.");
      return;
    }
    setUploading(true);
    setProgress(null);
    setError(null);
    try {
      await api.upload(list, (loaded, total) => setProgress(total ? Math.round((loaded / total) * 100) : null));
      await refresh();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setUploading(false);
      setProgress(null);
    }
  };

  const remove = async (d: DocumentSummary) => {
    if (!confirm(`Delete "${d.title}" and all extracted data?`)) return;
    await api.deleteDocument(d.id);
    refresh();
  };

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1>Document Library</h1>
          <p>Upload manuals, datasheets, wiring diagrams, scans, photos, invoices and parts lists. Each file is read, OCR'd if needed, structured, indexed and checked.</p>
        </div>
        <div className="row">
          <a className="btn" href={api.exportWorkbookUrl()} title="One Excel file: every extracted value with a link to its page, detected tables, calculator sheets prefilled from the documents with live formulas, and invoice totals">Export workbook (.xlsx, formulas)</a>
          <a className="btn" href={api.exportEntitiesUrl("xlsx")}>Values only (.xlsx)</a>
          <Link className="btn" to="/convert">Convert files</Link>
          <button className="btn primary" onClick={() => fileRef.current?.click()} disabled={uploading}>{uploading ? (progress == null ? "Uploading…" : `Uploading… ${progress}%`) : "Upload documents"}</button>
          <input ref={fileRef} type="file" multiple accept=".pdf,image/*" style={{ display: "none" }} onChange={(e) => e.target.files && upload(e.target.files)} />
        </div>
      </div>
      <div
        className={`dropzone${over ? " over" : ""}`}
        onDragOver={(e) => { e.preventDefault(); setOver(true); }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => { e.preventDefault(); setOver(false); upload(e.dataTransfer.files); }}
        onClick={() => fileRef.current?.click()}
      >
        {uploading
          ? `Uploading…${progress == null ? "" : ` ${progress}%`}`
          : "Drop PDF or image files here, or click to choose. Scanned PDFs and photographs are OCR'd automatically."}
      </div>
      {error && <div className="alert crit">{error}</div>}
      <div className="card" style={{ marginTop: 14, padding: 0 }}>
        {docs.length === 0 ? (
          <div className="empty">No documents yet. Upload an installation manual to get started.</div>
        ) : (
          <table className="doc-table">
            <thead>
              <tr><th>Document</th><th>Manufacturer</th><th>Equipment</th><th>Type</th><th>Pages</th><th>Extracted</th><th>Uploaded</th><th>Status</th><th></th></tr>
            </thead>
            <tbody>
              {docs.map((d) => (
                <tr key={d.id}>
                  <td>
                    <div className="title">{d.status === "ready" ? <Link to={`/documents/${d.id}`}>{d.title}</Link> : d.title}</div>
                    <div className="small muted">{d.filename} · {formatBytes(d.size_bytes)}{d.model_number ? ` · model ${d.model_number}` : ""}{d.revision ? ` · rev ${d.revision}` : ""}</div>
                  </td>
                  <td>{d.manufacturer || <span className="muted">—</span>}</td>
                  <td className="small">{d.equipment_types.slice(0, 4).join(", ") || <span className="muted">—</span>}</td>
                  <td>{d.document_type || "—"}</td>
                  <td>{d.page_count || "—"}{d.ocr_pages ? <div className="small muted">{d.ocr_pages} OCR</div> : null}</td>
                  <td className="small">
                    {d.stats?.entities ? Object.values(d.stats.entities).reduce((a, b) => a + b, 0) + " values" : "—"}
                    {d.stats?.critical_flags ? <div><span className="badge crit">{d.stats.critical_flags} to verify</span></div> : null}
                  </td>
                  <td className="small muted">{d.uploaded_at ? new Date(d.uploaded_at).toLocaleString() : ""}</td>
                  <td>
                    {d.status === "ready" && <span className="badge ok">ready</span>}
                    {d.status === "failed" && <span className="badge crit" title={d.error || ""}>failed</span>}
                    {(d.status === "queued" || d.status === "processing") && <span className="progress-text"><span className="spinner" /> {d.progress || d.status}</span>}
                    {d.status === "failed" && <div className="small muted" style={{ maxWidth: 220 }}>{d.error}</div>}
                  </td>
                  <td className="row" style={{ flexWrap: "nowrap" }}>
                    {d.status === "ready" && <Link className="btn sm" to={`/documents/${d.id}`}>Open</Link>}
                    <button className="btn sm" onClick={() => api.reprocessDocument(d.id).then(refresh)} title="Re-run OCR and extraction">↻</button>
                    <button className="btn sm danger" onClick={() => remove(d)}>✕</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
