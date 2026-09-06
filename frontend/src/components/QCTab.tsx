import { useEffect, useState } from "react";
import { api } from "../api";
import type { DocumentDetail, Entity, QCFlag } from "../types";
import type { Jump } from "../pages/DocumentPage";

export default function QCTab({ doc, jump }: { doc: DocumentDetail; jump: Jump }) {
  const [flags, setFlags] = useState<QCFlag[] | null>(null);
  const [entities, setEntities] = useState<Record<string, Entity>>({});
  useEffect(() => {
    api.qcFlags(doc.id).then(setFlags);
    api.documentEntities(doc.id).then((es) => setEntities(Object.fromEntries(es.map((e) => [e.id, e]))));
  }, [doc.id]);
  if (!flags) return <span className="spinner" />;
  const toggle = async (f: QCFlag) => {
    const u = await api.resolveFlag(doc.id, f.id, !f.resolved);
    setFlags((fs) => fs!.map((x) => (x.id === u.id ? u : x)));
  };
  return (
    <div>
      <p className="small muted">The verification layer checks critical values (voltage, current, fuse and breaker ratings, wire sizes, torque, temperature) using OCR confidence, digit-confusion analysis, plausibility ranges, repeated references and cross-references. Flags never change a value; they tell you what to check on the original page.</p>
      {flags.length === 0 && <div className="alert ok">No verification flags. All critical values were read with high confidence and no discrepancies were found.</div>}
      {flags.map((f) => {
        const e = f.entity_id ? entities[f.entity_id] : undefined;
        return (
          <div key={f.id} className={`alert ${f.severity === "critical" ? "crit" : f.severity === "warning" ? "warn" : "info"}`} style={{ opacity: f.resolved ? 0.55 : 1 }}>
            <div className="row">
              <span className={`badge ${f.severity === "critical" ? "crit" : f.severity === "warning" ? "warn" : ""}`}>{f.severity}</span>
              <span className="badge">{f.flag_type.replace(/_/g, " ")}</span>
              {f.page && <a href="#" className="small" onClick={(ev) => { ev.preventDefault(); jump(f.page!, e?.bbox, "primary", e?.value_text); }}>Open page {f.page}</a>}
              <span className="grow" />
              <button className="btn sm" onClick={() => toggle(f)}>{f.resolved ? "Reopen" : "Mark verified"}</button>
            </div>
            <div style={{ marginTop: 4 }}>{f.message}</div>
            {e && <div className="small muted" style={{ marginTop: 4 }}>“{e.snippet}”</div>}
          </div>
        );
      })}
    </div>
  );
}
