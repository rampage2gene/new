import { useCallback, useEffect, useState } from "react";
import { api, formatBytes } from "../api";
import type { DiagnosticsInfo } from "../types";

/** Everything needed to explain a failure, in one place with a copy button.
 *  The desktop app has no console, so without this the log is buried in a
 *  folder most people never open. */
export default function DiagnosticsPage() {
  const [info, setInfo] = useState<DiagnosticsInfo | null>(null);
  const [log, setLog] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState<string | null>(null);

  const refresh = useCallback(() => {
    setError(null);
    api.diagnostics().then(setInfo).catch((e) => setError(e.message));
    api.logs(800).then(setLog).catch(() => setLog(""));
  }, []);
  useEffect(() => { refresh(); }, [refresh]);

  const copy = async (what: string, text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(what);
      setTimeout(() => setCopied(null), 2500);
    } catch {
      setError("Could not copy automatically — select the text below and press Ctrl+C.");
    }
  };

  const rows: [string, string][] = info
    ? [
        ["App version", info.version],
        ["System", `${info.platform} (${info.machine})`],
        ["Python", `${info.python}${info.frozen ? ", packaged build" : ", development"}`],
        ["Data folder", info.data_dir],
        ["Log file", info.log_exists ? `${info.log_path} (${formatBytes(info.log_size)})` : `${info.log_path} — not created yet`],
        ["OCR engine", info.ocr_engine === "tesseract" ? `Tesseract — ${info.tesseract_version || "version unknown"}` : "none — scanned pages cannot be read"],
        ["Tesseract path", info.tesseract_path || "not found"],
        ["AI reasoning", info.ai_available ? (info.ai_model ?? "available") : "not configured (answers fall back to quoting the document)"],
        ["Embeddings", info.embedding_provider],
        ["Upload limit", `${info.max_upload_mb} MB per file`],
        ["Documents", `${info.documents.total} total · ${info.documents.ready} ready · ${info.documents.failed} failed`],
      ]
    : [];

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1>Diagnostics</h1>
          <p>What this copy of the app is, where it keeps its files, and what it last did. If something goes wrong, copy this and the log below into your bug report.</p>
        </div>
        <div className="row">
          <button className="btn" onClick={refresh}>Refresh</button>
          <button className="btn" disabled={!info} onClick={() => copy("diagnostics", rows.map(([k, v]) => `${k}: ${v}`).join("\n"))}>
            {copied === "diagnostics" ? "Copied ✓" : "Copy diagnostics"}
          </button>
          <button className="btn primary" disabled={!log} onClick={() => copy("log", log)}>
            {copied === "log" ? "Copied ✓" : "Copy log"}
          </button>
        </div>
      </div>

      {error && <div className="alert crit">{error}</div>}

      <div className="card">
        {info ? (
          <table className="doc-table">
            <tbody>
              {rows.map(([k, v]) => (
                <tr key={k}><th style={{ width: 180, textAlign: "left" }}>{k}</th><td className="small">{v}</td></tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div className="empty">Reading diagnostics…</div>
        )}
      </div>

      <div className="card" style={{ marginTop: 14 }}>
        <h2 style={{ marginTop: 0 }}>Application log</h2>
        {log ? (
          <pre className="log-view">{log}</pre>
        ) : (
          <div className="empty">
            No log file yet. The packaged desktop app writes one; a development server logs to its console instead.
          </div>
        )}
      </div>
    </div>
  );
}
