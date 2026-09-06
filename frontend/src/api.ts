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
};

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
