import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import AnswerView from "../components/AnswerView";
import type { Answer, CompareResult, DocumentSummary, Entity } from "../types";

const QUESTIONS = [
  "Is this inverter compatible with this battery voltage?",
  "Does the BMS current rating support the inverter?",
  "Compare the battery charging limits with the charger settings.",
  "Find conflicts between these installation manuals.",
  "Compare recommended cable sizes across documents.",
];

export default function ComparePage() {
  const [docs, setDocs] = useState<DocumentSummary[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [res, setRes] = useState<CompareResult | null>(null);
  const [q, setQ] = useState("");
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();

  useEffect(() => { api.listDocuments().then((d) => setDocs(d.filter((x) => x.status === "ready"))); }, []);

  const run = async () => {
    setBusy(true);
    try { setRes(await api.compare(selected)); setAnswer(null); } finally { setBusy(false); }
  };
  const ask = async (question: string) => {
    if (!question.trim()) return;
    setBusy(true);
    try { setAnswer(await api.ask(question, selected)); } finally { setBusy(false); }
  };
  const open = (e: Entity) => navigate(`/documents/${e.document_id}?page=${e.page}&bbox=${e.bbox.map((n) => Math.round(n)).join(",")}`);

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1>Compare Documents</h1>
          <p>Cross-reference specifications from several manuals (inverter, battery, BMS, alternator…). The table shows manufacturer-documented values; conflict checks are labelled engineering analysis.</p>
        </div>
      </div>
      <div className="card">
        <div className="doc-pick">
          {docs.map((d) => (
            <label key={d.id}><input type="checkbox" checked={selected.includes(d.id)} onChange={(e) => setSelected((s) => (e.target.checked ? [...s, d.id] : s.filter((x) => x !== d.id)))} /> <span>{d.title}<div className="small muted">{[d.manufacturer, d.document_type].filter(Boolean).join(" · ")}</div></span></label>
          ))}
        </div>
        <div className="row" style={{ marginTop: 10 }}>
          <button className="btn primary" disabled={selected.length < 2 || busy} onClick={run}>Compare {selected.length >= 2 ? `${selected.length} documents` : "(select at least 2)"}</button>
        </div>
      </div>
      {res && (
        <>
          {res.conflicts.length === 0 ? <div className="alert ok">No conflicts detected by the rule-based checks (voltage mismatch, discharge limits, charge current/voltage, fuse recommendations).</div> : res.conflicts.map((c, i) => (
            <div key={i} className={`alert ${c.severity === "critical" ? "crit" : "warn"}`}>
              <span className="badge">{c.classification.replace(/_/g, " ")}</span> <b>{c.type.replace(/_/g, " ")}</b>: {c.message}
              <div className="cite-list">{c.sources.map((s, j) => <button key={j} className="chip" onClick={() => navigate(`/documents/${s.document_id}?page=${s.page}&bbox=${s.bbox.map((n) => Math.round(n)).join(",")}`)}>{s.document_name} · p.{s.page} · {s.value_text}</button>)}</div>
            </div>
          ))}
          <div className="card" style={{ overflowX: "auto" }}>
            <div className="table-scroll">
              <table className="compare-table">
                <thead><tr><th>Specification</th>{res.documents.map((d) => <th key={d.id}>{d.name}<div className="muted" style={{ textTransform: "none", fontWeight: 400 }}>{[d.manufacturer, d.model].filter(Boolean).join(" ")}</div></th>)}</tr></thead>
                <tbody>
                  {res.table.map((row) => (
                    <tr key={row.key}>
                      <td><b>{row.label}</b></td>
                      {row.cells.map((c) => (
                        <td key={c.document_id} className="cell">
                          {c.values.length === 0 ? <span className="muted">not found</span> : c.values.map((e) => (
                            <a key={e.id} href="#" className="val" onClick={(ev) => { ev.preventDefault(); open(e); }} title={e.snippet}>
                              <b>{e.value_text}</b>{e.qualifier ? <span className="muted"> {e.qualifier}</span> : null}{e.application ? <span className="muted"> · {e.application}</span> : null} <span className="muted">p.{e.page}</span>
                            </a>
                          ))}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="small muted" style={{ marginTop: 8 }}>{res.note}</p>
          </div>
          <div className="card">
            <h3>Ask across the selected documents</h3>
            <div className="suggestions">{QUESTIONS.map((s) => <button key={s} className="chip" onClick={() => { setQ(s); ask(s); }}>{s}</button>)}</div>
            <div className="row">
              <input type="text" className="grow" value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === "Enter" && ask(q)} placeholder="Question about the selected documents…" />
              <button className="btn primary" disabled={busy} onClick={() => ask(q)}>Ask</button>
            </div>
            {busy && <div className="small muted" style={{ marginTop: 8 }}><span className="spinner" /> Working…</div>}
            {answer && <div style={{ marginTop: 12 }}><AnswerView answer={answer} onCitation={(c) => navigate(`/documents/${c.document_id}?page=${c.page}&bbox=${c.bbox.map((n) => Math.round(n)).join(",")}`)} onEntity={open} /></div>}
          </div>
        </>
      )}
    </div>
  );
}
