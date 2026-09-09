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

  /** Show a folder in Explorer/Finder. Outside the desktop app there is no
   *  file manager to ask, so say where it is instead of doing nothing. */
  const open = async (path: string) => {
    if (!(await api.openFolder(path))) setError(`This folder is on the computer running the app: ${path}`);
  };

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
        ["OCR readers", info.ocr_engines
          ? (info.ocr_engines.readers.length
              ? `${info.ocr_engines.readers.map((r) => (r === "rapidocr" ? `RapidOCR ${info.ocr_engines?.rapidocr_version || ""}`.trim() : r === "tesseract" ? `Tesseract ${info.tesseract_version || ""}`.trim() : r)).join(" + ")}`
                + (info.ocr_engines.readers.length > 1 ? " — every scanned value is checked against a second reading" : " — only one reader: values cannot be cross-checked")
              : "none — scanned pages cannot be read")
          : info.ocr_engine],
        ...(info.ocr_engines && !info.ocr_engines.rapidocr ? [["RapidOCR", `not available: ${info.ocr_engines.rapidocr_error || "unknown reason"}`] as [string, string]] : []),
        ["Tesseract path", info.tesseract_path || "not found"],
        ["Exports folder", info.exports_dir || "—"],
        ["AI reasoning", info.ai_available ? (info.ai_model ?? "available") : "not configured (answers fall back to quoting the document)"],
        ["Embeddings", info.embedding_provider],
        ["Upload limit", `${info.max_upload_mb} MB per file`],
        ["Phone access", info.phone_access === false
          ? "off (MDI_LAN=false) — the app answers on this computer only"
          : info.phone_key_required
            ? "on — a phone on this Wi-Fi can pair with the QR code on “Use on your phone”"
            : "on, with no pairing key — anything on this network can use the app"],
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

      {/* The folders the app uses, with a way to open them. They used to be
          plain text here and in the library's drop zone, so using one meant
          copying a path out by hand. */}
      {info && (
        <div className="card">
          <h2 style={{ marginTop: 0 }}>Folders</h2>
          <div className="table-scroll">
            <table className="doc-table">
              <tbody>
                {([
                  ["Documents and settings", info.data_dir],
                  ["Exported files", info.exports_dir || null],
                  ["Inbox — drop files here to have them read", info.inbox?.folder || null],
                ] as [string, string | null][]).filter(([, path]) => path).map(([label, path]) => (
                  <tr key={label}>
                    <th style={{ width: 260, textAlign: "left" }}>{label}</th>
                    <td className="small mono">{path}</td>
                    <td style={{ width: 90 }}>
                      <button className="btn sm" onClick={() => open(path!)}>Open</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {info.inbox && (info.inbox.waiting > 0 || info.inbox.failed.length > 0) && (
            <div className="small muted" style={{ marginTop: 6 }}>
              {info.inbox.waiting} file{info.inbox.waiting === 1 ? "" : "s"} waiting to be read
              {info.inbox.failed.length ? `, ${info.inbox.failed.length} could not be read (in the failed folder)` : ""}.
            </div>
          )}
        </div>
      )}

      <div className="card">
        {info ? (
          <div className="table-scroll">
            <table className="doc-table">
              <tbody>
                {rows.map(([k, v]) => (
                  <tr key={k}><th style={{ width: 180, textAlign: "left" }}>{k}</th><td className="small">{v}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
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
