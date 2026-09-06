import type { Answer, CalcResult, CalculatorSpec, CompareResult, DiagnosticsInfo as Diagnostics, DiagramAnalysis, DocumentDetail, DocumentSummary, Entity, Invoice, PageData, QCFlag, SearchResponse, SpecExtraction, Status } from "./types";

/** Why a file the user picked cannot be sent. Worth spelling out: the browser
 *  reports every one of these causes as the same bare "Failed to fetch". */
const UNREADABLE = (name: string) =>
  `The app could not read "${name}". That usually means the file is stored online-only (OneDrive/SharePoint), ` +
  `is inside a zip or an email preview, is still downloading, or is open in another program. ` +
  `Copy it to a normal folder such as your Desktop and try again.`;

const NETWORK_FAILED =
  "The app's built-in server did not answer. If this keeps happening, open Diagnostics in the sidebar to see the log.";

/** Sending a file has one failure the rest of the API does not: the file itself
 *  can stop being readable halfway through, which looks identical to a dead server. */
const UPLOAD_FAILED =
  "The upload did not finish. Either the file became unreadable while it was being sent (a file stored online-only, " +
  "in a zip, or open in another program), or the app's built-in server stopped answering. " +
  "Open Diagnostics in the sidebar to see the log.";

/** Read the first bytes of every file before sending any of them.
 *  A file that cannot be opened now will fail mid-upload with no useful error. */
async function checkReadable(files: File[]): Promise<void> {
  for (const f of files) {
    if (f.size === 0) throw new Error(`"${f.name}" is empty (0 bytes). ${UNREADABLE(f.name)}`);
    try {
      await f.slice(0, Math.min(65536, f.size)).arrayBuffer();
    } catch {
      throw new Error(UNREADABLE(f.name));
    }
  }
}

let uploadLimitMb: number | null = null;

/** Reject an oversized file here rather than after uploading it. */
async function checkSize(files: File[]): Promise<void> {
  if (uploadLimitMb == null) {
    try {
      uploadLimitMb = (await request<Status>("/api/status")).max_upload_mb ?? null;
    } catch {
      return; // the size check is a courtesy; the server enforces the limit anyway
    }
  }
  const limit = uploadLimitMb;
  if (!limit) return;
  for (const f of files) {
    if (f.size > limit * 1024 * 1024) {
      throw new Error(`"${f.name}" is ${(f.size / 1024 / 1024).toFixed(0)} MB; the limit is ${limit} MB.`);
    }
  }
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(url, init);
  } catch (e: any) {
    // A network-level failure ("Failed to fetch"): the request never completed.
    throw new Error(`${NETWORK_FAILED} (${e?.message ?? "network error"})`);
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ? (typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail)) : detail;
    } catch {
      /* ignore */
    }
    throw new Error(detail || `Request failed (${res.status})`);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

const json = (body: unknown): RequestInit => ({ method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

export type UploadProgress = (loaded: number, total: number) => void;

/** POST a multipart body with progress. `fetch` cannot report upload progress,
 *  so a big scan would otherwise sit at "Uploading…" with no sign of life. */
function xhrUpload<T>(url: string, fd: FormData, onProgress?: UploadProgress): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", url);
    if (onProgress) {
      xhr.upload.onprogress = (e) => { if (e.lengthComputable) onProgress(e.loaded, e.total); };
    }
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          resolve(xhr.responseText ? (JSON.parse(xhr.responseText) as T) : (undefined as T));
        } catch {
          reject(new Error("The server sent a reply the app could not read."));
        }
        return;
      }
      let detail = xhr.statusText;
      try {
        const body = JSON.parse(xhr.responseText);
        if (body.detail) detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
      } catch {
        /* ignore */
      }
      reject(new Error(detail || `Request failed (${xhr.status})`));
    };
    // status 0 means the request never completed: no response was ever received.
    xhr.onerror = () => reject(new Error(UPLOAD_FAILED));
    xhr.onabort = () => reject(new Error("The upload was cancelled."));
    xhr.send(fd);
  });
}

export const api = {
  status: () => request<Status>("/api/status"),
  diagnostics: () => request<Diagnostics>("/api/diagnostics"),
  logs: async (tail = 500): Promise<string> => {
    const res = await fetch(`/api/logs?tail=${tail}`);
    if (res.status === 404) return "";
    if (!res.ok) throw new Error(`Could not read the log (${res.status})`);
    return res.text();
  },
  listDocuments: () => request<DocumentSummary[]>("/api/documents"),
  /** Ingest files the server can read off the disk itself (paths from the native Open dialog). */
  importPaths: (paths: string[]) => request<DocumentSummary[]>("/api/documents/import", json({ paths })),
  /** Open the operating system's file dialog through the desktop app's bridge.
   *  Resolves to null outside the desktop app (plain browser, dev server), so
   *  callers fall back to the ordinary <input type=file>. */
  pickNativeFiles: async (): Promise<string[] | null> => {
    const bridge = (window as any).pywebview?.api;
    if (!bridge?.pick_files) return null;
    const paths = await bridge.pick_files();
    return Array.isArray(paths) ? paths : [];
  },
  getDocument: (id: string) => request<DocumentDetail>(`/api/documents/${id}`),
  deleteDocument: (id: string) => request<void>(`/api/documents/${id}`, { method: "DELETE" }),
  reprocessDocument: (id: string) => request<DocumentSummary>(`/api/documents/${id}/reprocess`, { method: "POST" }),
  /** Read the document again with every OCR reader and re-run the checks; user edits are kept. */
  verifyDocument: (id: string) => request<DocumentSummary>(`/api/documents/${id}/verify`, { method: "POST" }),
  /** Rewrite the document's exports folder now (it is also rewritten after every edit). */
  exportNow: (id: string) => request<{ folder: string | null; files: string[] }>(`/api/documents/${id}/export`, { method: "POST" }),
  /** The human rung of the verification ladder. */
  fillIn: (entityId: string, value_text: string) =>
    request<Entity>(`/api/entities/${entityId}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ value_text }) }),
  setVerified: (entityId: string, verified: boolean) =>
    request<Entity>(`/api/entities/${entityId}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ verified }) }),
  /** Show a folder in Explorer/Finder through the desktop bridge; false outside the app. */
  openFolder: async (path: string): Promise<boolean> => {
    const bridge = (window as any).pywebview?.api;
    if (!bridge?.open_folder) return false;
    try {
      return Boolean(await bridge.open_folder(path));
    } catch {
      return false;
    }
  },
  isDesktop: (): boolean => Boolean((window as any).pywebview?.api),
  upload: async (files: File[], onProgress?: UploadProgress) => {
    await checkReadable(files);
    await checkSize(files);
    const fd = new FormData();
    files.forEach((f) => fd.append("files", f));
    return xhrUpload<DocumentSummary[]>("/api/documents", fd, onProgress);
  },
  getPage: (id: string, page: number) => request<PageData>(`/api/documents/${id}/pages/${page}`),
  pageImageUrl: (id: string, page: number) => `/api/documents/${id}/pages/${page}/image`,
  originalUrl: (id: string) => `/api/documents/${id}/file`,
  documentEntities: (id: string, types?: string[]) => request<Entity[]>(`/api/documents/${id}/entities${types?.length ? "?" + types.map((t) => `entity_type=${t}`).join("&") : ""}`),
  specExtraction: (id: string) => request<SpecExtraction>(`/api/documents/${id}/spec-extraction`),
  qcFlags: (id: string) => request<QCFlag[]>(`/api/documents/${id}/qc`),
  resolveFlag: (docId: string, flagId: string, resolved: boolean) => request<QCFlag>(`/api/documents/${docId}/qc/${flagId}/resolve?resolved=${resolved}`, { method: "POST" }),
  search: (query: string, document_ids?: string[], limit = 15) => request<SearchResponse>("/api/search", json({ query, document_ids, limit })),
  ask: (question: string, document_ids?: string[], history?: { role: string; content: string }[]) => request<Answer>("/api/ask", json({ question, document_ids, history })),
  compare: (document_ids: string[], question?: string) => request<CompareResult>("/api/compare", json({ document_ids, question })),
  analyseDiagram: (id: string, page: number, force = false) => request<DiagramAnalysis>(`/api/documents/${id}/pages/${page}/diagram?force=${force}`, { method: "POST" }),
  getDiagram: (id: string, page: number) => request<DiagramAnalysis>(`/api/documents/${id}/pages/${page}/diagram`),
  calculators: () => request<CalculatorSpec[]>("/api/calculators"),
  runCalculator: (id: string, inputs: Record<string, unknown>) => request<CalcResult>(`/api/calculators/${id}/run`, json({ inputs })),
  suggestInputs: (id: string, documentId: string) => request<{ suggestions: Record<string, Entity[]> }>(`/api/calculators/${id}/suggest?document_id=${documentId}`),
  invoices: () => request<Invoice[]>("/api/invoices"),
  exportEntitiesUrl: (format: string, documentIds?: string[]) => `/api/export/entities?format=${format}${(documentIds || []).map((d) => `&document_ids=${d}`).join("")}`,
  exportInvoicesUrl: (format: string, report: string) => `/api/export/invoices?format=${format}&report=${report}`,
  // Excel workbook with live formulas (technical data, tables, calculators, invoices)
  exportWorkbookUrl: (documentIds?: string[], include?: string[]) =>
    `/api/export/workbook?${(documentIds || []).map((d) => `document_ids=${d}&`).join("")}${include?.length ? `include=${include.join(",")}` : ""}`,
  exportCalculator: (id: string, inputs: Record<string, unknown>) => downloadBlob(`/api/calculators/${id}/export`, json({ inputs }), `${id}.xlsx`),
  // PDF outputs and document conversions
  searchablePdfUrl: (id: string) => `/api/documents/${id}/export/searchable-pdf`,
  reportPdfUrl: (id: string, sections = "spec_extraction,qc") => `/api/documents/${id}/export/report.pdf?sections=${sections}`,
  documentExportUrl: (id: string, fmt: "txt" | "md" | "json") => `/api/documents/${id}/export/${fmt}`,
  exportReport: (body: { document_ids?: string[]; sections?: string[]; calculations?: CalcResult[]; answer?: Answer & { question?: string }; title?: string }) =>
    downloadBlob("/api/export/report.pdf", json(body), "report.pdf"),
  convert: async (files: File[], to: string, opts?: { ocr?: boolean; dpi?: number }) => {
    await checkReadable(files);
    await checkSize(files);
    const fd = new FormData();
    files.forEach((f) => fd.append("files", f));
    fd.append("to", to);
    if (opts?.ocr === false) fd.append("ocr", "false");
    if (opts?.dpi) fd.append("dpi", String(opts.dpi));
    return downloadBlob("/api/convert", { method: "POST", body: fd });
  },
  merge: async (files: File[]) => {
    await checkReadable(files);
    const fd = new FormData();
    files.forEach((f) => fd.append("files", f));
    return downloadBlob("/api/convert/merge", { method: "POST", body: fd }, "merged.pdf");
  },
  split: async (file: File, ranges?: string) => {
    await checkReadable([file]);
    const fd = new FormData();
    fd.append("file", file);
    if (ranges) fd.append("ranges", ranges);
    return downloadBlob("/api/convert/split", { method: "POST", body: fd });
  },
};

/** POST (or GET) a generated file and hand it to the browser as a download. */
export async function downloadBlob(url: string, init?: RequestInit, fallbackName?: string): Promise<string> {
  let res: Response;
  try {
    res = await fetch(url, init);
  } catch (e: any) {
    // Conversions send files through here too, and those can fail for the extra reason.
    const why = init?.body instanceof FormData ? UPLOAD_FAILED : NETWORK_FAILED;
    throw new Error(`${why} (${e?.message ?? "network error"})`);
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* ignore */
    }
    throw new Error(detail || `Request failed (${res.status})`);
  }
  const cd = res.headers.get("content-disposition") || "";
  const m = /filename="?([^";]+)"?/.exec(cd);
  const name = (m && m[1]) || fallbackName || "download";
  const blob = await res.blob();
  const href = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = href;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(href), 10000);
  return name;
}

export const REPORT_KEY = "mdi.report.calculations";

export function readReportCalcs(): CalcResult[] {
  try {
    const raw = sessionStorage.getItem(REPORT_KEY);
    return raw ? (JSON.parse(raw) as CalcResult[]) : [];
  } catch {
    return [];
  }
}

export function writeReportCalcs(list: CalcResult[]) {
  if (list.length) sessionStorage.setItem(REPORT_KEY, JSON.stringify(list));
  else sessionStorage.removeItem(REPORT_KEY);
}

export function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

export function pct(v: number | null | undefined): string {
  return v == null ? "—" : `${Math.round(v * 100)}%`;
}

export function typeLabel(t: string): string {
  return t.replace(/_/g, " ");
}

export const PREFILL_KEY = "mdi.calculator.prefill";
