import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, typeLabel } from "../api";
import type { DocumentDetail, Entity } from "../types";
import type { Jump } from "../pages/DocumentPage";
import { ask, isOpen, openFirst, readingsOf } from "../verification";
import { ConfidenceCell } from "./EntityRow";

/** Everything the readers did not settle, in two lists whose headings are
 *  the ask: values to type from the page, and values to confirm or correct
 *  (`verification.isOpen`, the same rule every badge counts). The page
 *  viewer follows the row under the caret. Every edit saves at once and the
 *  exports folder is rewritten a few seconds later.
 *
 *  It used to be one list under a line of seven numbers and a sentence that
 *  covered both situations at once; the user did not know what was being
 *  asked. Now each section says what happened and what to do, in the words
 *  `verification.ask` uses everywhere. */
export default function FillInTab({ doc, jump, page, onChanged }: { doc: DocumentDetail; jump: Jump; page: number; onChanged?: () => void }) {
  const [entities, setEntities] = useState<Entity[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  // A failed save is shown under the row it belongs to, not in a banner
  // above six rows that leaves the person guessing which one failed.
  const [rowErrors, setRowErrors] = useState<Record<string, string>>({});
  const [showDone, setShowDone] = useState(false);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [focused, setFocused] = useState<string | null>(null);
  const inputs = useRef<Record<string, HTMLInputElement | null>>({});

  const load = useCallback(() => api.documentEntities(doc.id).then(setEntities).catch((e) => setError(e.message)), [doc.id]);
  useEffect(() => { load(); }, [load]);

  const open = useMemo(() => (entities || []).filter(isOpen).sort(openFirst), [entities]);
  const done = useMemo(() => (entities || []).filter((e) => !isOpen(e)), [entities]);
  const toType = open.filter((e) => ask(e).kind === "blank");
  const toConfirm = open.filter((e) => ask(e).kind === "confirm");

  const replace = (u: Entity) => {
    setEntities((es) => es?.map((x) => (x.id === u.id ? u : x)) ?? es);
    setDrafts((d) => { const n = { ...d }; delete n[u.id]; return n; });
    onChanged?.();
  };
  const run = async (id: string, work: () => Promise<Entity>) => {
    setBusy(id);
    setRowErrors((r) => { const n = { ...r }; delete n[id]; return n; });
    try {
      replace(await work());
    } catch (e: any) {
      setRowErrors((r) => ({ ...r, [id]: e?.message ?? String(e) }));
    } finally {
      setBusy(null);
    }
  };
  const save = (e: Entity, text: string) => run(e.id, () => api.fillIn(e.id, text));
  const confirm = (e: Entity) => run(e.id, () => api.setVerified(e.id, true));
  const focusNext = (id: string) => {
    const ids = open.map((e) => e.id);
    const next = ids[ids.indexOf(id) + 1];
    if (next) inputs.current[next]?.focus();  // focusing brings its page up; see showOnPage
  };

  /** Bring up the page this value came from, so working the list and looking
   *  at the page are the same gesture. Settling a value used to cost a trip to
   *  the page link, a hunt, and a trip back, for every row.
   *
   *  Every way of touching a row calls this - typing in it, tabbing to it,
   *  reaching it with the mouse, clicking one of its readings, confirming it
   *  as it stands - so the page on screen is always the page the row came
   *  from. It cannot force anyone to read it; what it can do is make reading
   *  cost nothing. */
  const showOnPage = (e: Entity) => jump(e.page, e.bbox, "primary", e.value_text || e.raw_text);

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

  const row = (e: Entity) => {
    const a = ask(e);
    const readings = readingsOf(e);
    const blank = a.kind === "blank";
    // Never seed the box with what the machine read. A pre-filled input
    // turns "press Enter" into recording a machine reading as the user's
    // own confirmation, which is the one thing this application must not
    // do. The reading stays offered as a click in "What the readers saw",
    // where using it is a deliberate act.
    const draft = drafts[e.id] ?? "";
    return (
      // Both handlers sit on the row rather than on each control. Focus
      // bubbles, so one is enough to cover the box and every button beside
      // it. Reaching the row with a mouse shows its page too, so the page is
      // up before a reading is accepted rather than after - once per row,
      // not once per button passed on the way.
      <tr
        key={e.id}
        className={blank ? "fill-blank" : undefined}
        onFocus={() => { setFocused(e.id); showOnPage(e); }}
        onBlur={() => setFocused((f) => (f === e.id ? null : f))}
        onMouseEnter={() => showOnPage(e)}
      >
        <td>{typeLabel(e.entity_type)}{e.application ? <div className="small muted">{e.application}</div> : null}</td>
        <td className="small">
          <a href="#" onClick={(ev) => { ev.preventDefault(); showOnPage(e); }}>p.{e.page}{e.page === page ? " ✓" : ""}</a>
          {e.section ? <div className="muted">{e.section}</div> : null}
        </td>
        <td className="small">
          {/* On a blank row each reading is a click, because there are two to
              choose between. On a one-reader row the only reading is what
              Confirm accepts, so a second control for the same act would be
              one decision too many; it is shown as text. */}
          {readings.length === 0 ? <span className="muted">—</span> : blank ? readings.map((r) => (
            <button key={r} className="btn sm" style={{ marginRight: 4, marginBottom: 2 }} onClick={() => { showOnPage(e); save(e, r); }} disabled={busy === e.id} title="Use this reading as the value">{r}</button>
          )) : <b>{readings.join(" / ")}</b>}
          {e.snippet ? <div className="muted" style={{ maxWidth: 260 }}>“{e.snippet.slice(0, 120)}{e.snippet.length > 120 ? "…" : ""}”</div> : null}
        </td>
        <td>
          <input
            ref={(el) => { inputs.current[e.id] = el; }}
            type="text"
            value={draft}
            placeholder={blank ? `what page ${e.page} says` : "type the right value"}
            aria-label={blank ? `Value from page ${e.page}` : `Correction for ${e.value_text}`}
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
          {focused === e.id && <div className="small muted" style={{ marginTop: 2 }}>{a.todo}</div>}
          {rowErrors[e.id] && <div className="small" style={{ marginTop: 2 }}><span className="tag crit">{rowErrors[e.id]}</span></div>}
        </td>
        <td><ConfidenceCell entity={e} /></td>
        <td>
          {/* display:flex on a <td> takes the cell out of the row's
              layout; the buttons need their own box. */}
          <div className="row" style={{ flexWrap: "nowrap" }}>
            <button className="btn sm primary" disabled={busy === e.id || !draft.trim()} onClick={() => save(e, draft)}>Save</button>
            {!blank && <button className="btn sm" disabled={busy === e.id} onClick={() => { showOnPage(e); confirm(e); }} title={`The page shows exactly “${e.value_text}”`}>Confirm</button>}
          </div>
        </td>
      </tr>
    );
  };

  const section = (title: string, what: string, rows: Entity[]) => rows.length === 0 ? null : (
    <div style={{ marginBottom: 12 }}>
      <h4 style={{ marginBottom: 2 }}>{title} <span className="badge warn">{rows.length}</span></h4>
      <p className="small muted" style={{ marginTop: 0 }}>{what}</p>
      <div className="table-scroll">
        <table>
          <thead>
            <tr><th>What it is</th><th>Page</th><th>Readers saw</th><th style={{ width: 190 }}>Type here</th><th>Status</th><th></th></tr>
          </thead>
          <tbody>{rows.map(row)}</tbody>
        </table>
      </div>
    </div>
  );

  return (
    <div>
      <div className="row" style={{ marginBottom: 8 }}>
        <div className="grow">
          {open.length > 0 ? (
            <div><b>{open.length}</b> value{open.length === 1 ? "" : "s"} need{open.length === 1 ? "s" : ""} you on this document. The page follows the row you are on.</div>
          ) : null}
          <div className="small muted">
            {v ? (
              <>
                {v.checked} values read from scanned pages: {v.confirmed} agreed by two readers, {v.corrected} settled by a third reading.
                {v.reader2 ? <> Readers: {v.reader1}, {v.reader2}.</> : <> Only one OCR reader is installed; see Diagnostics.</>}
                {v.ai && v.ai !== "off" ? <> AI check: {v.ai}.</> : null}
              </>
            ) : (
              "This document's text came from the PDF itself; nothing was read by OCR."
            )}
          </div>
        </div>
        <button className="btn sm" onClick={reverify} title="Read the document again with every OCR reader and re-run the checks. Your own entries are kept.">Re-verify</button>
      </div>
      {error && <div className="alert crit">{error}</div>}
      {open.length === 0 ? (
        <div className="alert ok">Nothing to fill in. Every value was confirmed by two readers or by you.</div>
      ) : (
        <>
          {section("Type these from the page", "The two readers disagreed, so nothing was kept: type what the page says, or click the reading that matches it.", toType)}
          {section("Confirm these, or correct them", "Only one reader saw these: press Confirm if the page agrees, or type the right value.", toConfirm)}
        </>
      )}
      {done.length > 0 && (
        <div style={{ marginTop: 12 }}>
          <button className="btn sm" onClick={() => setShowDone((s) => !s)}>{showDone ? "Hide" : "Show"} {done.length} settled values</button>
          {showDone && (
            <div className="table-scroll">
              <table style={{ marginTop: 8 }}>
                <thead><tr><th>What it is</th><th>Page</th><th>Value</th><th>Status</th><th></th></tr></thead>
                <tbody>
                  {done.map((e) => (
                    <tr key={e.id}>
                      <td>{typeLabel(e.entity_type)}</td>
                      <td className="small"><a href="#" onClick={(ev) => { ev.preventDefault(); jump(e.page, e.bbox, "primary", e.value_text); }}>p.{e.page}</a></td>
                      <td><b>{e.value_text}</b>{e.verification?.original && e.verification.original !== e.value_text ? <span className="small muted"> (was {e.verification.original})</span> : null}</td>
                      <td><ConfidenceCell entity={e} /></td>
                      <td>{e.verified && <button className="btn sm" onClick={() => run(e.id, () => api.setVerified(e.id, false))} title="Go back to what the machine read">Untick</button>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
