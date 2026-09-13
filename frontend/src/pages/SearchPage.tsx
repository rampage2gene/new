import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api";
import type { DocumentSummary, SearchResponse } from "../types";

function Highlighted({ text, terms }: { text: string; terms: string[] }) {
  if (!terms.length) return <>{text}</>;
  const esc = terms.filter(Boolean).map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  const re = new RegExp(`(${esc.join("|")})`, "gi");
  const parts = text.split(re);
  return <>{parts.map((p, i) => (re.test(p) && terms.some((t) => t.toLowerCase() === p.toLowerCase()) ? <mark key={i}>{p}</mark> : <span key={i}>{p}</span>))}</>;
}

export default function SearchPage() {
  const [params, setParams] = useSearchParams();
  const [q, setQ] = useState(params.get("q") || "");
  const [docs, setDocs] = useState<DocumentSummary[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [res, setRes] = useState<SearchResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();

  useEffect(() => { api.listDocuments().then((d) => setDocs(d.filter((x) => x.status === "ready"))); }, []);
  useEffect(() => { if (params.get("q")) run(params.get("q")!); /* eslint-disable-line react-hooks/exhaustive-deps */ }, []);

  const run = async (query: string) => {
    if (!query.trim()) return;
    setBusy(true);
    setParams({ q: query });
    try {
      setRes(await api.search(query, selected.length ? selected : undefined, 25));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1>Search</h1>
          <p>Exact keywords, marine-electrical synonyms, technical values (“48 volts”, “300 A”) and section titles across every uploaded document.</p>
        </div>
      </div>
      <div className="card">
        <div className="row">
          <input type="text" className="grow" placeholder="e.g. What wire size is required for the DC connection?  ·  battery charger  ·  every mention of 48 volts" value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === "Enter" && run(q)} />
          <button className="btn primary" onClick={() => run(q)} disabled={busy}>{busy ? "Searching…" : "Search"}</button>
        </div>
        {docs.length > 1 && (
          <div className="doc-pick" style={{ marginTop: 10 }}>
            {docs.map((d) => (
              <label key={d.id} className="small"><input type="checkbox" checked={selected.includes(d.id)} onChange={(e) => setSelected((s) => (e.target.checked ? [...s, d.id] : s.filter((x) => x !== d.id)))} /> {d.title}</label>
            ))}
            <span className="small muted" style={{ alignSelf: "center" }}>{selected.length ? `${selected.length} selected` : "all documents"}</span>
          </div>
        )}
      </div>
      {res && (
        <>
          <div className="small muted" style={{ marginBottom: 8 }}>
            {res.hits.length} results
            {res.query.entity_types.length ? <> · looking for <b>{res.query.entity_types.join(", ").replace(/_/g, " ")}</b> values</> : null}
            {res.query.value != null ? <> · value <b>{res.query.value} {res.query.unit}</b></> : null}
            {Object.keys(res.query.expansions).length ? <> · also matching: {Object.entries(res.query.expansions).map(([k, v]) => `${k} → ${v.slice(0, 5).join(", ")}${v.length > 5 ? "…" : ""}`).join("; ")}</> : null}
          </div>
          {res.hits.length === 0 && <div className="empty">Nothing matched. Try a different term or check that documents have finished processing.</div>}
          {res.hits.map((h) => (
            <div key={h.chunk_id} className="hit" onClick={() => navigate(`/documents/${h.document_id}?page=${h.page_number}&bbox=${h.bbox.map((n) => Math.round(n)).join(",")}`)}>
              <div className="meta">
                <b>{h.document_name}</b> · Page {h.page_number}{h.section ? ` · ${h.section}` : ""}
                {h.sources.map((s) => <span key={s} className={`badge ${s === "entity" ? "ok" : s === "keyword" ? "accent" : s.endsWith("weak") || s.endsWith("partial") ? "" : "navy"}`}>{s === "entity" ? "value" : s.replace("_", " ")}</span>)}
              </div>
              <div className="snippet"><Highlighted text={h.text.length > 600 ? h.text.slice(0, 600) + "…" : h.text} terms={h.highlights} /></div>
            </div>
          ))}
        </>
      )}
    </div>
  );
}
