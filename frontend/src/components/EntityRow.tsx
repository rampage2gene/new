import { useState } from "react";
import { api } from "../api";
import type { Entity } from "../types";
import { ask, readingsOf } from "../verification";
import SendToCalculator from "./SendToCalculator";

export function FlagDots({ entity }: { entity: Entity }) {
  if (!entity.flags?.length) return null;
  const worst = entity.flags.some((f) => f.severity === "critical") ? "critical" : entity.flags.some((f) => f.severity === "warning") ? "warning" : "info";
  return <span className={`flag-dot ${worst}`} title={entity.flags.map((f) => f.message).join("\n")} />;
}

/** What the verification ladder concluded, in two words; the tooltip says
 *  what happened and what to do, in the words `verification.ask` uses on
 *  every screen. */
export function verificationTag(e: Entity): { label: string; cls: string; title: string } | null {
  const v = e.verification;
  const a = ask(e);
  const readings = v?.readings ? Object.entries(v.readings).filter(([, r]) => r).map(([k, r]) => `${k}: ${r}`).join("\n") : "";
  if (e.verified) return { label: "you", cls: "ok", title: `Confirmed by you${v?.original && v.original !== e.value_text ? ` (was ${v.original})` : ""}` };
  switch (v?.status) {
    case "confirmed": return { label: v.note === "2 readers" ? "2 readers" : "3 reads", cls: "ok", title: `${a.what}\n${readings}` };
    case "ai_confirmed": return { label: "AI", cls: "ok", title: `${a.what}\n${readings}` };
    case "corrected":
    case "ai_corrected": return { label: "corrected", cls: "warn", title: `${a.what}\n${readings}` };
    // Waiting for the person is the normal day's work, so it wears --warn;
    // --crit is kept for what is actually wrong (docs/UI.md §6).
    case "to_fill": return { label: "to fill in", cls: "warn", title: `${a.what} ${a.todo}` };
    // A value only one reader could see is the least certain thing on the
    // screen; it may not wear the neutral tag (docs/UI.md §6).
    case "unverified":
    case "single": return { label: "1 reader", cls: "warn", title: `${a.what} ${a.todo}` };
    case "embedded": return null;
    default: return null;
  }
}

export function ConfidenceCell({ entity }: { entity: Entity }) {
  const status = entity.verification?.status;
  if (status === "to_fill" && !entity.verified) {
    const a = ask(entity);
    return <span className="badge warn" title={`${a.what} ${a.todo}`}>—</span>;
  }
  const c = entity.confidence;
  const cls = c >= 0.95 ? "ok" : c >= 0.75 ? "warn" : "crit";
  const tag = verificationTag(entity);
  return (
    <span className="conf-cell">
      <span className={`badge ${cls}`} title={entity.ocr_confidence != null ? `OCR word confidence ${Math.round(entity.ocr_confidence * 100)}%` : "Embedded text"}>
        {c >= 0.995 ? "✓ 100%" : `${Math.round(c * 100)}%`}
      </span>
      {tag && <span className={`tag ${tag.cls}`} title={tag.title}>{tag.label}</span>}
      {entity.ocr_confidence != null && c < 0.95 && <span className="small muted">OCR {Math.round(entity.ocr_confidence * 100)}%</span>}
    </span>
  );
}

/** The value as printed, or the blank, what the readers saw, and - where the
 *  row can be edited - a box to type the value in.
 *
 *  A blank used to say "to fill in" and leave the typing to another tab,
 *  reachable through a tooltip. The ask is answered where it is seen: the
 *  box sits in the blank, saves on Enter, and the value becomes yours. */
export function ValueCell({ entity, onChange }: { entity: Entity; onChange?: (e: Entity) => void }) {
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const v = entity.verification;
  if (v?.status === "to_fill" && !entity.verified) {
    const seen = readingsOf(entity);
    const save = async () => {
      if (!draft.trim()) return;
      setBusy(true);
      setError(null);
      try {
        onChange?.(await api.fillIn(entity.id, draft.trim()));
      } catch (e: any) {
        setError(e?.message ?? String(e));
      } finally {
        setBusy(false);
      }
    };
    return (
      <span>
        <FlagDots entity={entity} />
        <b className="muted">— blank</b>
        {seen.length > 0 && <span className="small muted"> read as {seen.join(" / ")}</span>}
        {onChange && (
          // Clicking into the box bubbles to the row, which brings the page
          // up - wanted. Only Save stops there, so saving is not also a jump.
          <div className="row" style={{ flexWrap: "nowrap", marginTop: 4 }}>
            <input
              type="text"
              value={draft}
              placeholder={`type what page ${entity.page} says`}
              aria-label={`Value from page ${entity.page}`}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); save(); } }}
              disabled={busy}
              style={{ width: 150 }}
            />
            <button className="btn sm primary" disabled={busy || !draft.trim()} onClick={(e) => { e.stopPropagation(); save(); }}>Save</button>
          </div>
        )}
        {onChange && <div className="small muted">{ask(entity).todo}</div>}
        {error && <div className="small"><span className="tag crit">{error}</span></div>}
      </span>
    );
  }
  return (
    <span title={v?.original && v.original !== entity.value_text ? `was ${v.original}` : undefined}>
      <FlagDots entity={entity} />
      <b>{entity.value_text}</b>
      {entity.device_type ? <span className="muted"> {entity.device_type}</span> : null}
    </span>
  );
}

/** The tick that makes a value yours. On a one-reader row it is labelled
 *  "Confirm", because that is the ask; elsewhere "verified". A blank row
 *  cannot be ticked - there is nothing to confirm until a value is typed. */
export function VerifiedBox({ entity, onChange }: { entity: Entity; onChange?: (e: Entity) => void }) {
  const [busy, setBusy] = useState(false);
  const a = ask(entity);
  const blank = a.kind === "blank";
  const toggle = async () => {
    setBusy(true);
    try {
      const updated = await api.setVerified(entity.id, !entity.verified);
      onChange?.(updated);
    } catch (e: any) {
      alert(e?.message ?? String(e));
    } finally {
      setBusy(false);
    }
  };
  const title = blank
    ? "Type the value first; then it is yours."
    : entity.verified
      ? "Untick to go back to what the machine read"
      : a.kind === "confirm"
        ? a.todo
        : "Tick when you have checked this value on the page";
  return (
    <label className="small" title={title} style={{ whiteSpace: "nowrap" }}>
      <input type="checkbox" checked={entity.verified} disabled={busy || blank} onChange={toggle} /> {entity.verified ? "checked by you" : a.kind === "confirm" ? "Confirm" : "checked"}
    </label>
  );
}

export default function EntityRow({ entity, onJump, showType, showDoc, onChange }: { entity: Entity; onJump: (e: Entity) => void; showType?: boolean; showDoc?: boolean; onChange?: (e: Entity) => void }) {
  return (
    <tr className="clickable" onClick={() => onJump(entity)}>
      {showType && <td>{entity.entity_type.replace(/_/g, " ")}</td>}
      <td><ValueCell entity={entity} onChange={onChange} /></td>
      <td>{entity.qualifier || "—"}</td>
      <td>{entity.application || (entity.equipment ? `${entity.equipment}${entity.equipment_model ? " " + entity.equipment_model : ""}` : "—")}</td>
      <td className="small">{showDoc && entity.document_name ? <><span className="muted">{entity.document_name}</span><br /></> : null}p.{entity.page}{entity.section ? <span className="muted"> · {entity.section}</span> : null}</td>
      <td><ConfidenceCell entity={entity} /></td>
      <td onClick={(e) => e.stopPropagation()}><VerifiedBox entity={entity} onChange={onChange} /></td>
      <td onClick={(e) => e.stopPropagation()}><SendToCalculator entity={entity} /></td>
    </tr>
  );
}
