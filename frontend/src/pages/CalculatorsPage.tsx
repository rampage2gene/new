import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import { readPrefill, writePrefill } from "../components/SendToCalculator";
import type { CalcInputValue, CalcResult, CalculatorSpec, DocumentSummary, Entity, InputSpec } from "../types";

type FormState = Record<string, CalcInputValue>;

function SourceTag({ src }: { src: CalcInputValue["source"] }) {
  if (!src) return null;
  const nav = useNavigate();
  return (
    <span className="source-tag">
      from <a href="#" onClick={(e) => { e.preventDefault(); if (src.document_id) nav(`/documents/${src.document_id}?page=${src.page}`); }}>{src.document_name || "document"}, p.{src.page}</a>
      {src.section ? ` · ${src.section}` : ""}
    </span>
  );
}

export default function CalculatorsPage() {
  const { calcId } = useParams();
  const navigate = useNavigate();
  const [specs, setSpecs] = useState<CalculatorSpec[]>([]);
  const [docs, setDocs] = useState<DocumentSummary[]>([]);
  const [docId, setDocId] = useState("");
  const [suggestions, setSuggestions] = useState<Record<string, Entity[]>>({});
  const [form, setForm] = useState<FormState>({});
  const [result, setResult] = useState<CalcResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.calculators().then((s) => { setSpecs(s); if (!calcId && s.length) navigate(`/calculators/${s[0].id}`, { replace: true }); });
    api.listDocuments().then((d) => setDocs(d.filter((x) => x.status === "ready")));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const spec = useMemo(() => specs.find((s) => s.id === calcId) || null, [specs, calcId]);

  useEffect(() => {
    if (!spec) return;
    const init: FormState = {};
    for (const inp of spec.inputs) init[inp.key] = { value: inp.default ?? "", unit: inp.unit, origin: "default" };
    const pre = readPrefill();
    if (pre && pre.calculatorId === spec.id) {
      Object.assign(init, pre.inputs);
      const firstDoc = Object.values(pre.inputs).find((v) => v.source?.document_id)?.source?.document_id;
      if (firstDoc) setDocId(firstDoc);
    }
    setForm(init);
    setResult(null);
    setError(null);
  }, [spec]);

  useEffect(() => {
    if (!spec || !docId) { setSuggestions({}); return; }
    api.suggestInputs(spec.id, docId).then((r) => setSuggestions(r.suggestions)).catch(() => setSuggestions({}));
  }, [spec, docId]);

  const setValue = (key: string, value: unknown) => setForm((f) => ({ ...f, [key]: { value, unit: f[key]?.unit, origin: "user" } }));
  const useEntity = (inp: InputSpec, e: Entity) => {
    const value = inp.kind === "text" ? e.value_text : e.value;
    setForm((f) => ({ ...f, [inp.key]: { value, unit: e.unit, origin: "document", source: { document_id: e.document_id, document_name: e.document_name || undefined, page: e.page, section: e.section, entity_id: e.id, snippet: e.snippet, confidence: e.confidence } } }));
  };

  const run = async () => {
    if (!spec) return;
    setBusy(true);
    setError(null);
    try {
      const payload: Record<string, unknown> = {};
      for (const [k, v] of Object.entries(form)) {
        if (v.value === "" || v.value == null) continue;
        payload[k] = v.source ? { value: v.value, unit: v.unit, source: v.source } : v.value;
      }
      setResult(await api.runCalculator(spec.id, payload));
      writePrefill(null);
    } catch (e: any) {
      setError(e.message);
      setResult(null);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1>Electrical Calculators</h1>
          <p>Inputs can be taken directly from extracted document values; every result shows the formula, inputs with sources, assumptions and whether a figure is a manufacturer value or an engineering estimate.</p>
        </div>
      </div>
      <div className="calc-layout">
        <div className="calc-list">
          {specs.map((s) => (
            <div key={s.id} className={`item${s.id === calcId ? " active" : ""}`} onClick={() => navigate(`/calculators/${s.id}`)}>
              <div className="cat">{s.category}</div>
              <b>{s.name}</b>
              <div className="small muted mono">{s.formula}</div>
            </div>
          ))}
        </div>
        {spec && (
          <div className="calc-form card">
            <h2>{spec.name}</h2>
            <p className="small muted">{spec.description}</p>
            {spec.notes.map((n, i) => <div key={i} className="alert info small">{n}</div>)}
            <label className="field">
              <span className="lbl">Fill inputs from document</span>
              <select value={docId} onChange={(e) => setDocId(e.target.value)}>
                <option value="">— choose a processed document —</option>
                {docs.map((d) => <option key={d.id} value={d.id}>{d.title}</option>)}
              </select>
            </label>
            {spec.inputs.map((inp) => {
              const v = form[inp.key];
              const sugg = suggestions[inp.key] || [];
              return (
                <label className="field" key={inp.key}>
                  <span className="lbl">{inp.label}{inp.unit ? ` (${inp.unit})` : ""}{inp.required ? "" : " · optional"}{v?.source ? <> · <SourceTag src={v.source} /></> : null}</span>
                  {inp.kind === "select" ? (
                    <select value={String(v?.value ?? "")} onChange={(e) => setValue(inp.key, e.target.value)}>
                      {(inp.options || []).map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                    </select>
                  ) : (
                    <input type={inp.kind === "number" ? "number" : "text"} step="any" value={v?.value ?? ""} placeholder={inp.help || ""} onChange={(e) => setValue(inp.key, e.target.value)} style={v?.source ? { borderColor: "var(--ok)" } : undefined} />
                  )}
                  {sugg.length > 0 && (
                    <div className="suggest">
                      {sugg.map((e) => (
                        <button key={e.id} type="button" className="chip" title={`${e.snippet}\n(page ${e.page}${e.section ? ", " + e.section : ""})`} onClick={() => useEntity(inp, e)}>
                          {e.value_text}{e.qualifier ? <span className="muted"> {e.qualifier}</span> : null} <span className="muted">p.{e.page}</span>
                        </button>
                      ))}
                    </div>
                  )}
                  {inp.help && !sugg.length && <div className="small muted">{inp.help}</div>}
                </label>
              );
            })}
            {error && <div className="alert crit">{error}</div>}
            <button className="btn primary" onClick={run} disabled={busy}>{busy ? "Calculating…" : "Calculate"}</button>
          </div>
        )}
        {result && (
          <div className="calc-result card">
            <h2>{result.calculator_name}</h2>
            <div className="mono small muted" style={{ marginBottom: 8 }}>{result.formula}</div>
            {result.results.map((r) => (
              <div key={r.key} style={{ marginBottom: 10 }}>
                <div className={`classification ${r.classification}`}>{r.classification.replace(/_/g, " ")}</div>
                <div><span className={typeof r.value === "number" ? "result-value" : ""}>{typeof r.value === "number" ? r.value.toLocaleString(undefined, { maximumFractionDigits: 3 }) : String(r.value)}</span> {r.unit && <b>{r.unit}</b>} <span className="muted">{typeof r.value === "number" ? r.label : `— ${r.label}`}</span></div>
                {r.note && <div className="small muted">{r.note}</div>}
              </div>
            ))}
            {result.warnings.length > 0 && <div className="alert warn"><b>Warnings</b><ul className="plain">{result.warnings.map((w, i) => <li key={i}>{w}</li>)}</ul></div>}
            <h4>Inputs</h4>
            <table className="small">
              <tbody>
                {Object.entries(result.inputs).filter(([, v]) => v.value != null && v.value !== "").map(([k, v]) => (
                  <tr key={k}><td className="muted">{spec?.inputs.find((i) => i.key === k)?.label || k}</td><td><b>{String(v.value)}</b> {v.unit}</td><td>{v.source ? <SourceTag src={v.source} /> : <span className="muted">{v.origin === "default" ? "default" : "entered by user"}</span>}</td></tr>
                ))}
              </tbody>
            </table>
            <h4 style={{ marginTop: 10 }}>Calculation</h4>
            <ol className="steps">{result.steps.map((s, i) => <li key={i}>{s}</li>)}</ol>
            <h4 style={{ marginTop: 10 }}>Assumptions</h4>
            <ul className="plain small">{result.assumptions.map((a, i) => <li key={i}>{a}</li>)}</ul>
            <p className="small muted" style={{ marginTop: 10 }}>{result.disclaimer}</p>
          </div>
        )}
      </div>
    </div>
  );
}
