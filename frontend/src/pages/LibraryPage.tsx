import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, formatBytes } from "../api";
import type { DiagnosticsInfo, DocumentSummary } from "../types";

export default function LibraryPage() {
  const [docs, setDocs] = useState<DocumentSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState<number | null>(null);
  const [over, setOver] = useState(false);
  const [report, setReport] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [info, setInfo] = useState<DiagnosticsInfo | null>(null);
  const [folderNote, setFolderNote] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  // A drop inside the desktop app is handled by the window (paths, not bytes):
  // hold the browser's File objects briefly and only upload them if no
  // `mdi:dropped` event follows, so a drop never silently vanishes.
  const heldDrop = useRef<{ files: File[]; timer: number } | null>(null);
  useEffect(() => { api.diagnostics().then(setInfo).catch(() => setInfo(null)); }, []);
  useEffect(() => {
    const cancelHold = () => {
      if (heldDrop.current) {
        window.clearTimeout(heldDrop.current.timer);
        heldDrop.current = null;
      }
      setUploading(false);
    };
    window.addEventListener("mdi:dropped", cancelHold);
    return () => window.removeEventListener("mdi:dropped", cancelHold);
  }, []);

  const refresh = useCallback(() => api.listDocuments().then(setDocs).catch((e) => setError(e.message)), []);
  useEffect(() => { refresh(); }, [refresh]);
  const busy = docs.some((d) => d.status === "queued" || d.status === "processing");
  useEffect(() => {
    if (!busy) return;
    const t = setInterval(refresh, 1500);
    return () => clearInterval(t);
  }, [busy, refresh]);

  /** Everything a bug report needs, gathered the moment something fails: the
   *  message, what was being sent, the build, and the tail of the log. */
  const gatherReport = async (message: string, what: string) => {
    const lines = [`Error: ${message}`, `While: ${what}`, `When: ${new Date().toISOString()}`];
    try {
      const d = await api.diagnostics();
      lines.push(`Version: ${d.version} (${d.platform}${d.frozen ? ", packaged" : ", dev"})`);
      lines.push(`Data folder: ${d.data_dir}`, `Log file: ${d.log_path}${d.log_exists ? "" : " (not created yet)"}`);
      lines.push(`OCR: ${d.ocr_engine}${d.tesseract_version ? ` (${d.tesseract_version})` : ""}`);
    } catch (e: any) {
      lines.push(`Diagnostics unavailable: ${e?.message ?? e}`);
    }
    try {
      const tail = await api.logs(40);
      lines.push("", "--- last 40 log lines ---", tail.trimEnd() || "(no log file)");
    } catch (e: any) {
      lines.push(`Log unavailable: ${e?.message ?? e}`);
    }
    setReport(lines.join("\n"));
  };

  const fail = (e: any, what: string) => {
    const message = e?.message ?? String(e);
    setError(message);
    gatherReport(message, what);
  };

  const upload = async (files: FileList | File[]) => {
    const list = Array.from(files);
    if (!list.length) {
      setError("That drop didn't contain a file. Drag it from File Explorer, or use the \u201cUpload documents\u201d button.");
      return;
    }
    setUploading(true);
    setProgress(null);
    setError(null);
    setReport(null);
    try {
      await api.upload(list, (loaded, total) => setProgress(total ? Math.round((loaded / total) * 100) : null));
      await refresh();
    } catch (e: any) {
      fail(e, `uploading ${list.map((f) => `${f.name} (${formatBytes(f.size)})`).join(", ")}`);
    } finally {
      setUploading(false);
      setProgress(null);
    }
  };

  /** The Upload button: the operating system's own Open dialog inside the
   *  desktop app (the server then reads the files off the disk), the browser's
   *  file picker everywhere else. */
  const chooseFiles = async () => {
    let paths: string[] | null = null;
    try {
      paths = await api.pickNativeFiles();
    } catch (e: any) {
      fail(e, "opening the file dialog");
      return;
    }
    if (paths === null) {
      fileRef.current?.click();
      return;
    }
    if (!paths.length) return; // dialog cancelled
    setUploading(true);
    setError(null);
    setReport(null);
    try {
      await api.importPaths(paths);
      await refresh();
    } catch (e: any) {
      fail(e, `importing ${paths.join(", ")}`);
    } finally {
      setUploading(false);
    }
  };

  const dropped = (files: FileList) => {
    const list = Array.from(files);
    if (!api.isDesktop() || !list.length) {
      upload(files);
      return;
    }
    if (heldDrop.current) window.clearTimeout(heldDrop.current.timer);
    setUploading(true);
    const timer = window.setTimeout(() => {
      heldDrop.current = null;
      upload(list);
    }, 1500);
    heldDrop.current = { files: list, timer };
  };

  const openFolder = async (d: DocumentSummary) => {
    const dir = d.stats?.export_dir;
    if (!dir) {
      setFolderNote("No exports folder yet for this document. Press ↻ to process it again.");
      return;
    }
    const ok = await api.openFolder(dir);
    setFolderNote(ok ? null : `The exports are in: ${dir}`);
  };

  const copyReport = async () => {
    if (!report) return;
    try {
      await navigator.clipboard.writeText(report);
      setCopied(true);
      setTimeout(() => setCopied(false), 2500);
    } catch {
      /* the text is on screen; the user can select it */
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
          <button className="btn primary" onClick={chooseFiles} disabled={uploading}>{uploading ? (progress == null ? "Uploading…" : `Uploading… ${progress}%`) : "Upload documents"}</button>
          <input ref={fileRef} type="file" multiple accept=".pdf,image/*" style={{ display: "none" }} onChange={(e) => e.target.files && upload(e.target.files)} />
        </div>
      </div>
      <div
        className={`dropzone${over ? " over" : ""}`}
        onDragOver={(e) => { e.preventDefault(); setOver(true); }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => { e.preventDefault(); setOver(false); dropped(e.dataTransfer.files); }}
        onClick={chooseFiles}
      >
        {uploading
          ? `Uploading…${progress == null ? "" : ` ${progress}%`}`
          : "Drop PDF or image files here, or click to choose. Scanned PDFs and photographs are OCR'd automatically."}
        {!uploading && info && (
          <div className="small muted" style={{ marginTop: 6 }}>
            Every processed document also gets a folder in <code>{info.exports_dir || `${info.data_dir.replace(/[\\/]$/, "")}${info.platform.toLowerCase().startsWith("windows") ? "\\" : "/"}exports`}</code> with the OCR'd PDF, a clean text PDF for an AI, an Excel workbook, CSV, JSON and text.
            No luck with drag-and-drop? Copy files into the inbox folder instead: <code>{info.data_dir.replace(/[\\/]$/, "")}{info.platform.toLowerCase().startsWith("windows") ? "\\" : "/"}inbox</code>; the same files appear in its <code>done</code> subfolder.
          </div>
        )}
      </div>
      {folderNote && <div className="alert info">{folderNote} <button className="btn sm" style={{ marginLeft: 8 }} onClick={() => setFolderNote(null)}>OK</button></div>}
      {error && (
        <div className="alert crit">
          <div>{error}</div>
          {report && (
            <details style={{ marginTop: 8 }}>
              <summary style={{ cursor: "pointer" }}>Details for a bug report</summary>
              <div className="row" style={{ margin: "8px 0" }}>
                <button className="btn sm" onClick={copyReport}>{copied ? "Copied \u2713" : "Copy report"}</button>
                <span className="small muted">Paste this where you are asking for help.</span>
              </div>
              <pre className="log-view">{report}</pre>
            </details>
          )}
        </div>
      )}
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
                    {d.status === "ready" && (d.stats?.to_fill || d.stats?.verification?.unverified) ? (
                      <div>
                        <Link to={`/documents/${d.id}?tab=fill`} className="badge crit" title="Values the readers could not settle: fill them in or confirm them from the page">
                          {(d.stats.to_fill || 0) + (d.stats.verification?.unverified || 0)} to fill in
                        </Link>
                      </div>
                    ) : null}
                    {d.status === "ready" && d.stats?.verification && !d.stats.to_fill && !d.stats.verification.unverified && d.stats.verification.checked > 0 ? (
                      <div><span className="badge ok" title="Every scanned value was read the same way by two readers or confirmed by you">all values checked</span></div>
                    ) : null}
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
                    {d.status === "ready" && d.ocr_pages ? <a className="btn sm" href={api.searchablePdfUrl(d.id)} title="This document with the OCR text layer added, so the text can be selected and searched in any PDF viewer">OCR'd PDF</a> : null}
                    {d.status === "ready" ? <button className="btn sm" onClick={() => openFolder(d)} title={d.stats?.export_dir ? `Open ${d.stats.export_dir}: OCR'd PDF, clean text PDF, workbook, CSV, JSON, text` : "The exports folder for this document"}>Open folder</button> : null}
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
