import { useEffect, useState } from "react";
import { api } from "../api";
import type { DocumentDetail, Entity, QCFlag } from "../types";
import type { Jump } from "../pages/DocumentPage";
import { ask, flagLabel, flagTodo } from "../verification";
import { ConfidenceCell, ValueCell } from "./EntityRow";

/** Every place a reading or a value looked wrong, each with what to do about
 *  it. The app changes nothing here on its own: a doubtful reading is left
 *  blank for the person, and a note stays until they have checked it. */
export default function QCTab({ doc, jump }: { doc: DocumentDetail; jump: Jump }) {
  const [flags, setFlags] = useState<QCFlag[] | null>(null);
  const [entities, setEntities] = useState<Record<string, Entity>>({});
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api.qcFlags(doc.id).then(setFlags).catch((e) => setError(e?.message ?? String(e)));
    api.documentEntities(doc.id).then((es) => setEntities(Object.fromEntries(es.map((e) => [e.id, e])))).catch(() => {});
  }, [doc.id]);
  if (error && !flags) return <div className="alert crit">{error}</div>;
  if (!flags) return <span className="spinner" />;

  const attempt = async (work: () => Promise<void>) => {
    setError(null);
    try {
      await work();
    } catch (e: any) {
      setError(e?.message ?? String(e));
    }
  };
  /** A value was typed or confirmed: keep it, and ask the server for the
   *  notes again, because it resolves the reading notes itself. */
  const updated = async (u: Entity) => {
    setEntities((es) => ({ ...es, [u.id]: u }));
    setFlags(await api.qcFlags(doc.id));
  };
  /** Set a note aside. Only for notes about the document rather than one
   *  value - it changes nothing about any number. */
  const toggle = (f: QCFlag) => attempt(async () => {
    const u = await api.resolveFlag(doc.id, f.id, !f.resolved);
    setFlags((fs) => fs!.map((x) => (x.id === u.id ? u : x)));
  });
  /** Confirm the value this note is about, having read it on the page.
   *
   *  This used to resolve the flag and nothing else, which left the value
   *  itself unconfirmed at its machine confidence - so a button labelled
   *  "Mark verified", in the tab called Verification, produced an unverified
   *  number in every export. It now does what the same act does in the
   *  To fill in tab: the value becomes yours, at 100%, and the server
   *  resolves the reading flag itself. A blank cannot be confirmed - it has
   *  no value yet - so a blank gets the box to type in instead. */
  const confirmValue = (entity: Entity) => attempt(async () => updated(await api.setVerified(entity.id, true)));
  const v = doc.stats?.verification;
  return (
    <div>
      <p className="small muted">
        These are the places where a reading or a value looked wrong. Nothing here was changed by the app; each one says what to check.
      </p>
      {v && (
        <div className="alert info">
          {v.checked} values from scanned pages: {v.confirmed} agreed by two readers, {v.corrected} settled by a third reading,{" "}
          {doc.stats.to_fill ?? v.to_fill} left blank for you to type, {v.unverified} on one reading for you to confirm.
          {" "}Blanks and one-reader values are listed in the <b>To fill in</b> tab.
        </div>
      )}
      {error && <div className="alert crit">{error}</div>}
      {flags.length === 0 && <div className="alert ok">Nothing to check. Every value was read clearly and none looked wrong.</div>}
      {flags.map((f) => {
        const e = f.entity_id ? entities[f.entity_id] : undefined;
        const a = e ? ask(e) : null;
        return (
          <div key={f.id} className={`alert ${f.severity === "critical" ? "crit" : f.severity === "warning" ? "warn" : "info"}`} style={{ opacity: f.resolved ? 0.55 : 1 }}>
            <div className="row">
              <span className={`badge ${f.severity === "critical" ? "crit" : f.severity === "warning" ? "warn" : ""}`}>{f.severity === "critical" ? "check first" : f.severity === "warning" ? "check" : "note"}</span>
              <b>{flagLabel(f.flag_type)}</b>
              {f.page && <a href="#" className="small" onClick={(ev) => { ev.preventDefault(); jump(f.page!, e?.bbox, "primary", e?.value_text); }}>Open page {f.page}</a>}
              {e && <ConfidenceCell entity={e} />}
              <span className="grow" />
              {e && !e.verified && a?.kind !== "blank" ? (
                <button className="btn sm primary" onClick={() => confirmValue(e)} title={`Press only if the page shows exactly “${e.value_text}”: the value becomes yours, at 100%, in every export`}>
                  Confirm “{e.value_text}”
                </button>
              ) : e?.verified ? (
                <span className="tag ok" title="You confirmed this value">✓ confirmed by you</span>
              ) : !e ? (
                <button className="btn sm" onClick={() => toggle(f)} title="Set this note aside; it is about the document, not one value">
                  {f.resolved ? "Reopen" : "I've checked this"}
                </button>
              ) : null}
            </div>
            <div style={{ marginTop: 4 }}>{f.message}</div>
            {e && <div className="small muted" style={{ marginTop: 4 }}>“{e.snippet}”</div>}
            {e && a?.kind === "blank" && <div style={{ marginTop: 4 }} onClick={() => jump(e.page, e.bbox, "primary")}><ValueCell entity={e} onChange={(u) => attempt(() => updated(u))} /></div>}
            {!f.resolved && !(e?.verified) && <div className="small" style={{ marginTop: 4 }}><b>What to do:</b> {flagTodo(f, e)}</div>}
          </div>
        );
      })}
    </div>
  );
}
