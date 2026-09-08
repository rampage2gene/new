import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, typeLabel } from "../api";
import type { DocumentDetail, Entity } from "../types";
import type { Jump } from "../pages/DocumentPage";
import { ConfidenceCell } from "./EntityRow";

/** Everything the readers did not settle: blanks first, then values that
 *  rest on a single reading, then anything below 100%. The user fills in
 *  or confirms each one from the page; every edit is saved at once and the
 *  exports folder is rewritten a few seconds later. */
export default function FillInTab({ doc, jump, onChanged }: { doc: DocumentDetail; jump: Jump; onChanged?: () => void }) {
  const [entities, setEntities] = useState<Entity[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [showDone, setShowDone] = useState(false);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const inputs = useRef<Record<string, HTMLInputElement | null>>({});

  const load = useCallback(() => api.documentEntities(doc.id).then(setEntities).catch((e) => setError(e.message)), [doc.id]);
  useEffect(() => { load(); }, [load]);

  const rank = (e: Entity) => {
    if (e.verified) return 9;
    switch (e.verification?.status) {
      case "to_fill": return 0;
      case "unverified": case "single": return 1;
      case "corrected": case "ai_corrected": return 2;
      case "confirmed": return e.confidence >= 0.995 ? 8 : 3;
      case "ai_confirmed": return 8;
      case "embedded": return 8;
      default: return 4;
    }
  };
  const open = useMemo(() => (entities || []).filter((e) => rank(e) < 8).sort((a, b) => rank(a) - rank(b) || a.page - b.page), [entities]);
  const done = useMemo(() => (entities || []).filter((e) => rank(e) >= 8), [entities]);
  const blanks = open.filter((e) => e.verification?.status === "to_fill").length;

  const replace = (u: Entity) => {
    setEntities((es) => es?.map((x) => (x.id === u.id ? u : x)) ?? es);
    setDrafts((d) => { const n = { ...d }; delete n[u.id]; return n; });
    onChanged?.();
  };
  const run = async (id: string, work: () => Promise<Entity>) => {
    setBusy(id);
    setError(null);
    try {
      replace(await work());
    } catch (e: any) {
      setError(e?.message ?? String(e));
    } finally {
      setBusy(null);
    }
  };
  const save = (e: Entity, text: string) => run(e.id, () => api.fillIn(e.id, text));
  const confirm = (e: Entity) => run(e.id, () => api.setVerified(e.id, true));
  const focusNext = (id: string) => {
    const ids = open.map((e) => e.id);
    const next = ids[ids.indexOf(id) + 1];
    if (next) inputs.current[next]?.focus();
  };

  const reverify = async () => {
    try {
      await api.verifyDocument(doc.id);
      onChanged?.();
    } catch (e: any) {
      setError(e?.message ?? String(e));
    }
  };

  if (error && !entities) return <div className="alert crit">{error}</div>;
  if (!entities) return <span className="spinner" />;
  const v = doc.stats?.verification;

  return (
    <div>
      <div className="row" style={{ marginBottom: 8 }}>
        <div className="small muted grow">
          {v ? (
            <>
              {v.checked} values read from scanned pages: <b>{v.confirmed}</b> confirmed by two readers, <b>{v.corrected}</b> corrected,{" "}
              <b>{blanks}</b> left blank, <b>{open.length - blanks}</b> waiting for your confirmation.
              {v.reader2 ? <> Readers: {v.reader1}, {v.reader2}.</> : <> Only one OCR reader is installed; see Diagnostics.</>}
              {v.ai && v.ai !== "off" ? <> AI check: {v.ai}.</> : null}
            </>
          ) : (
            "This document's text came from the PDF itself; nothing was read by OCR."
          )}
        </div>
        <button className="btn sm" onClick={reverify} title="Read the document again with every OCR reader and re-run the checks. Your own entries are kept.">Re-verify</button>
      </div>
      {error && <div className="alert crit">{error}</div>}
      {open.length === 0 ? (
        <div className="alert ok">Nothing to fill in. Every value was confirmed by two readers or by you.</div>
      ) : (
        <>
          <p className="small muted">
            Open the page, read the value, type it and press Enter (or click a reading to use it). Blank rows are values the readers disagreed on;
            the app does not guess them. Confirm a row as it is when the page agrees with what was read.
          </p>
          <table>
            <thead>
              <tr><th>Type</th><th>Page</th><th>Read as</th><th style={{ width: 170 }}>Value</th><th>Now</th><th></th></tr>
            </thead>
            <tbody>
              {open.map((e) => {
                const readings = Array.from(new Set(Object.values(e.verification?.readings || {}).filter(Boolean) as string[]));
                const blank = e.verification?.status === "to_fill";
                // Never seed the box with what the machine read. A pre-filled
                // input turns "press Enter" into recording a machine reading
                // as the user's own confirmation, which is the one thing this
                // application must not do. The reading stays offered as a
                // click in "Read as", where using it is a deliberate act.
                const draft = drafts[e.id] ?? "";
                return (
                  <tr key={e.id} className={blank ? "fill-blank" : undefined}>
                    <td>{typeLabel(e.entity_type)}{e.application ? <div className="small muted">{e.application}</div> : null}</td>
                    <td className="small">
                      <a href="#" onClick={(ev) => { ev.preventDefault(); jump(e.page, e.bbox, "primary", e.value_text || e.raw_text); }}>p.{e.page}</a>
                      {e.section ? <div className="muted">{e.section}</div> : null}
                    </td>
                    <td className="small">
                      {readings.length ? readings.map((r) => (
                        <button key={r} className="btn sm" style={{ marginRight: 4, marginBottom: 2 }} onClick={() => save(e, r)} disabled={busy === e.id} title="Use this reading">{r}</button>
                      )) : <span className="muted">—</span>}
                      {e.snippet ? <div className="muted" style={{ maxWidth: 260 }}>“{e.snippet.slice(0, 120)}{e.snippet.length > 120 ? "…" : ""}”</div> : null}
                    </td>
                    <td>
                      <input
                        ref={(el) => { inputs.current[e.id] = el; }}
                        type="text"
                        value={draft}
                        placeholder={blank ? "type the value from the page" : `type it, or confirm “${e.value_text}”`}
                        onChange={(ev) => setDrafts((d) => ({ ...d, [e.id]: ev.target.value }))}
                        onKeyDown={(ev) => {
                          if (ev.key === "Enter") {
                            ev.preventDefault();
                            if (draft.trim()) save(e, draft).then(() => focusNext(e.id));
                            else if (!blank) confirm(e).then(() => focusNext(e.id));
                          }
                        }}
                        disabled={busy === e.id}
                      />
                    </td>
                    <td><ConfidenceCell entity={e} /></td>
                    <td>
                      {/* display:flex on a <td> takes the cell out of the row's
                          layout; the buttons need their own box. */}
                      <div className="row" style={{ flexWrap: "nowrap" }}>
                        <button className="btn sm primary" disabled={busy === e.id || !draft.trim()} onClick={() => save(e, draft)}>Save</button>
                        {!blank && <button className="btn sm" disabled={busy === e.id} onClick={() => confirm(e)} title="The page shows exactly this">Confirm as is</button>}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </>
      )}
      {done.length > 0 && (
        <div style={{ marginTop: 12 }}>
          <button className="btn sm" onClick={() => setShowDone((s) => !s)}>{showDone ? "Hide" : "Show"} {done.length} settled values</button>
          {showDone && (
            <table style={{ marginTop: 8 }}>
              <thead><tr><th>Type</th><th>Page</th><th>Value</th><th>Checked</th><th></th></tr></thead>
              <tbody>
                {done.map((e) => (
                  <tr key={e.id}>
                    <td>{typeLabel(e.entity_type)}</td>
                    <td className="small"><a href="#" onClick={(ev) => { ev.preventDefault(); jump(e.page, e.bbox, "primary", e.value_text); }}>p.{e.page}</a></td>
                    <td><b>{e.value_text}</b>{e.verification?.original && e.verification.original !== e.value_text ? <span className="small muted"> (was {e.verification.original})</span> : null}</td>
                    <td><ConfidenceCell entity={e} /></td>
                    <td>{e.verified && <button className="btn sm" onClick={() => run(e.id, () => api.setVerified(e.id, false))}>Untick</button>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
}
