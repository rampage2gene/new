import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, readReportCalcs, writeReportCalcs } from "../api";
import ReferencePane from "../components/ReferencePane";
import { readPrefill, writePrefill } from "../components/SendToCalculator";
import type { CalcAsk, CalcInputValue, CalcResult, CalculatorSpec, DocumentSummary, Entity, InputSpec } from "../types";

type FormState = Record<string, CalcInputValue>;

/** The reference sheet lives in the calculator list, not in the sidebar: it
 *  is the calculator's own source, and one screen fewer to learn. */
const REFERENCE_ID = "reference";

// Which blank each ask answers: the input goes under that row and no other,
// so two open asks (say the drop and the ampacity) never land on one line.
const ASK_FOR_ROW: Record<string, string> = {
  cm_required: "conductor.voltage_drop.cm_required",
  voltage_drop_size: "conductor.voltage_drop.size_awg",
  ampacity_size: "conductor.ampacity.size_awg",
  size_awg: "conductor.size_awg",
  fuse_a: "protection.fuse_a",
  interrupting: "protection.interrupting.required_a",
  cable_od: "fittings.cable_od",
  heat_shrink: "fittings.heat_shrink.size",
  lug: "fittings.lug.part",
  crimp_die: "fittings.lug.crimp_die",
};

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
  const [reportCalcs, setReportCalcs] = useState<CalcResult[]>(() => readReportCalcs());
  const [exportMsg, setExportMsg] = useState<string | null>(null);
  const [answers, setAnswers] = useState<Record<string, string>>({});

  const payloadFromForm = (f: FormState = form) => {
    const payload: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(f)) {
      if (v.value === "" || v.value == null) continue;
      payload[k] = v.source ? { value: v.value, unit: v.unit, source: v.source } : v.value;
    }
    return payload;
  };

  const openInExcel = async () => {
    if (!spec) return;
    setExportMsg(null);
    try {
      const name = await api.exportCalculator(spec.id, payloadFromForm());
      setExportMsg(`Saved ${name}: inputs are editable cells, results are formulas.`);
    } catch (e: any) {
      setExportMsg(e.message);
    }
  };

  const addToReport = () => {
    if (!result) return;
    const next = [...reportCalcs, result];
    setReportCalcs(next);
    writeReportCalcs(next);
  };

  const clearReport = () => { setReportCalcs([]); writeReportCalcs([]); };

  const downloadReport = async () => {
    setExportMsg(null);
    try {
      const docIds = Array.from(new Set(reportCalcs.flatMap((c) => c.sources.map((s) => s.document_id).filter(Boolean) as string[])));
      await api.exportReport({ document_ids: docIds, sections: ["spec_extraction"], calculations: reportCalcs, title: "Electrical calculations report" });
    } catch (e: any) {
      setExportMsg(e.message);
    }
  };

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
    setAnswers({});
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

  const run = async (f: FormState = form) => {
    if (!spec) return;
    setBusy(true);
    setError(null);
    try {
      setResult(await api.runCalculator(spec.id, payloadFromForm(f)));
      writePrefill(null);
    } catch (e: any) {
      setError(e.message);
      setResult(null);
    } finally {
      setBusy(false);
    }
  };

  /** A blank result's box: the value the person typed goes into the input
   *  that answers it, and the calculation runs again at once. */
  const answer = (ask: CalcAsk) => {
    const v = answers[ask.field]?.trim();
    if (!ask.input_key || !v) return;
    const next: FormState = { ...form, [ask.input_key]: { value: v, unit: ask.unit, origin: "user" } };
    setForm(next);
    run(next);
  };

  /** Inputs that only make sense once something else was chosen, or once a
   *  result asked for them, stay out of the way until then. */
  const visible = (inp: InputSpec) => {
    if (inp.answers) return Boolean(result?.asks?.some((a) => a.input_key === inp.key)) || (form[inp.key]?.value !== "" && form[inp.key]?.value != null);
    if (inp.key === "max_drop_other") return String(form.max_drop_percent?.value) === "other";
    if (inp.key === "bundled_conductors") return String(form.bundled?.value) === "yes";
    return true;
  };

  const groups = useMemo(() => {
    if (!result) return [];
    const order: string[] = [];
    const by = new Map<string, CalcResult["results"]>();
    for (const r of result.results) {
      const g = r.group || "";
      if (!by.has(g)) { by.set(g, []); order.push(g); }
      by.get(g)!.push(r);
    }
    return order.map((g) => ({ name: g, items: by.get(g)! }));
  }, [result]);

  const isReference = calcId === REFERENCE_ID;

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
          <div className={`item${isReference ? " active" : ""}`} onClick={() => navigate(`/calculators/${REFERENCE_ID}`)}>
            <div className="cat">Reference</div>
            <b>ABYC E-11 reference</b>
            <div className="small muted">The tables the circuit calculator computes with, and the installation reminders</div>
          </div>
        </div>
        {isReference && <ReferencePane />}
        {spec && !isReference && (
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
            {spec.inputs.filter(visible).map((inp) => {
              const v = form[inp.key];
              const sugg = suggestions[inp.key] || [];
              return (
                <label className="field" key={inp.key}>
                  <span className="lbl">{inp.label}{inp.unit ? ` (${inp.unit})` : ""}{inp.required ? "" : " · optional"}{v?.source ? <> · <SourceTag src={v.source} /></> : null}{inp.answers && v?.value !== "" && v?.value != null ? <> · <span className="tag ok">you</span></> : null}</span>
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
            <div className="row">
              <button className="btn primary" onClick={() => run()} disabled={busy}>{busy ? "Calculating…" : "Calculate"}</button>
              <button className="btn" onClick={openInExcel} title="Excel workbook: these inputs as editable cells, results as live formulas">Open in Excel</button>
            </div>
            {exportMsg && <div className="small muted" style={{ marginTop: 6 }}>{exportMsg}</div>}
            {reportCalcs.length > 0 && (
              <div className="report-bar small">
                <span><b>{reportCalcs.length}</b> calculation{reportCalcs.length === 1 ? "" : "s"} collected for a report</span>
                <button className="btn sm" onClick={downloadReport}>Download report (.pdf)</button>
                <button className="btn sm" onClick={clearReport}>Clear</button>
              </div>
            )}
          </div>
        )}
        {result && !isReference && (
          <div className="calc-result card">
            <div className="row" style={{ justifyContent: "space-between" }}>
              <h2 style={{ margin: 0 }}>{result.calculator_name}</h2>
              <button className="btn sm" onClick={addToReport} title="Collect this result; download all collected results as one PDF report">+ Add to report</button>
            </div>
            <div className="mono small muted" style={{ marginBottom: 8 }}>{result.formula}</div>
            {groups.map((g) => (
              <div key={g.name}>
                {g.name && <h4 style={{ marginTop: 10 }}>{g.name}</h4>}
                {g.items.map((r) => {
                  const ask = result.asks?.find((a) => a.field === ASK_FOR_ROW[r.key] || (r.key === "size_awg" && a.field === "reference"));
                  return (
                    <div key={r.key} style={{ marginBottom: 10 }}>
                      <div className={`classification ${r.classification}`}>{r.classification.replace(/_/g, " ")}</div>
                      {r.value == null ? (
                        // A blank is a request, never an empty cell: what is missing, and the box that answers it.
                        <div>
                          <span className="muted">—</span> <span className="muted">{r.label}</span>
                          {r.note && <div className="small">{r.note}</div>}
                          {ask?.input_key && (
                            <div className="row" style={{ flexWrap: "nowrap", marginTop: 4 }}>
                              <input type={ask.kind === "text" ? "text" : "number"} step="any" value={answers[ask.field] ?? ""} placeholder={ask.unit ? `value in ${ask.unit}` : ask.kind === "text" ? "catalog name" : "value from the page"} aria-label={ask.prompt} onChange={(e) => setAnswers((a) => ({ ...a, [ask.field]: e.target.value }))} onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); answer(ask); } }} style={{ width: 150 }} />
                              <button className="btn primary" disabled={busy || !answers[ask.field]?.trim()} onClick={() => answer(ask)}>Use this value</button>
                            </div>
                          )}
                          {ask && !ask.input_key && <div className="small" style={{ marginTop: 4 }}><Link to={`/calculators/${REFERENCE_ID}`}>Open the ABYC E-11 reference</Link></div>}
                          {ask?.input_key && ask.field.startsWith("fittings.") && ask.field !== "fittings.lug.part" && <div className="small muted" style={{ marginTop: 4 }}>Or type the whole table once under <Link to={`/calculators/${REFERENCE_ID}`}>ABYC E-11 reference</Link>, so the next circuit finds it.</div>}
                          {ask?.input_key === "own_lug_part" && <div className="small muted" style={{ marginTop: 4 }}>Or add the row to your lugs table under <Link to={`/calculators/${REFERENCE_ID}`}>ABYC E-11 reference</Link>, so the next circuit finds it.</div>}
                        </div>
                      ) : (
                        <div><span className={typeof r.value === "number" ? "result-value" : ""}>{typeof r.value === "number" ? r.value.toLocaleString(undefined, { maximumFractionDigits: 3 }) : String(r.value)}</span> {r.unit && <b>{r.unit}</b>} <span className="muted">{typeof r.value === "number" ? r.label : `— ${r.label}`}</span></div>
                      )}
                      {r.value != null && r.note && <div className="small muted">{r.note}</div>}
                    </div>
                  );
                })}
              </div>
            ))}
            {(result.reminders?.length ?? 0) > 0 && (
              <>
                <h4 style={{ marginTop: 10 }}>Reminders from the standard</h4>
                <ul className="plain small">
                  {result.reminders!.map((e, i) => <li key={i}><b>{e.topic}:</b> {e.rule} <span className="muted">{e.clause} · p. {e.page}{e.status === "draft" ? " · not yet checked against the page" : ""}</span></li>)}
                </ul>
              </>
            )}
            {result.warnings.length > 0 && <div className="alert warn"><b>Warnings</b><ul className="plain">{result.warnings.map((w, i) => <li key={i}>{w}</li>)}</ul></div>}
            <h4>Inputs</h4>
            <div className="table-scroll">
              <table className="small">
                <tbody>
                  {Object.entries(result.inputs).filter(([, v]) => v.value != null && v.value !== "").map(([k, v]) => (
                    <tr key={k}><td className="muted">{spec?.inputs.find((i) => i.key === k)?.label || k}</td><td><b>{spec?.inputs.find((i) => i.key === k)?.options?.find((o) => o.value === String(v.value))?.label ?? String(v.value)}</b> {v.unit}</td><td>{v.source ? <SourceTag src={v.source} /> : <span className="muted">{v.origin === "default" ? "default" : spec?.inputs.find((i) => i.key === k)?.answers ? "typed by you" : "entered by user"}</span>}</td></tr>
                  ))}
                </tbody>
              </table>
            </div>
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
