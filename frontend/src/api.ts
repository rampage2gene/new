import type { Answer, CalcResult, CalculatorSpec, CompareResult, DiagramAnalysis, DocumentDetail, DocumentSummary, Entity, Invoice, PageData, QCFlag, SearchResponse, SpecExtraction, Status } from "./types";

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
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

export const api = {
  status: () => request<Status>("/api/status"),
  listDocuments: () => request<DocumentSummary[]>("/api/documents"),
  getDocument: (id: string) => request<DocumentDetail>(`/api/documents/${id}`),
  deleteDocument: (id: string) => request<void>(`/api/documents/${id}`, { method: "DELETE" }),
  reprocessDocument: (id: string) => request<DocumentSummary>(`/api/documents/${id}/reprocess`, { method: "POST" }),
  upload: (files: File[]) => {
    const fd = new FormData();
    files.forEach((f) => fd.append("files", f));
    return request<DocumentSummary[]>("/api/documents", { method: "POST", body: fd });
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
  convert: (files: File[], to: string, opts?: { ocr?: boolean; dpi?: number }) => {
    const fd = new FormData();
    files.forEach((f) => fd.append("files", f));
    fd.append("to", to);
    if (opts?.ocr === false) fd.append("ocr", "false");
    if (opts?.dpi) fd.append("dpi", String(opts.dpi));
    return downloadBlob("/api/convert", { method: "POST", body: fd });
  },
  merge: (files: File[]) => {
    const fd = new FormData();
    files.forEach((f) => fd.append("files", f));
    return downloadBlob("/api/convert/merge", { method: "POST", body: fd }, "merged.pdf");
  },
  split: (file: File, ranges?: string) => {
    const fd = new FormData();
    fd.append("file", file);
    if (ranges) fd.append("ranges", ranges);
    return downloadBlob("/api/convert/split", { method: "POST", body: fd });
  },
};

/** POST (or GET) a generated file and hand it to the browser as a download. */
export async function downloadBlob(url: string, init?: RequestInit, fallbackName?: string): Promise<string> {
  const res = await fetch(url, init);
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
