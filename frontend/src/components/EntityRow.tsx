import { useState } from "react";
import { api } from "../api";
import type { Entity } from "../types";
import SendToCalculator from "./SendToCalculator";

export function FlagDots({ entity }: { entity: Entity }) {
  if (!entity.flags?.length) return null;
  const worst = entity.flags.some((f) => f.severity === "critical") ? "critical" : entity.flags.some((f) => f.severity === "warning") ? "warning" : "info";
  return <span className={`flag-dot ${worst}`} title={entity.flags.map((f) => f.message).join("\n")} />;
}

/** What the verification ladder concluded, in two words. */
export function verificationTag(e: Entity): { label: string; cls: string; title: string } | null {
  const v = e.verification;
  const readings = v?.readings ? Object.entries(v.readings).filter(([, r]) => r).map(([k, r]) => `${k}: ${r}`).join("\n") : "";
  if (e.verified) return { label: "you", cls: "ok", title: `Confirmed by you${v?.original && v.original !== e.value_text ? ` (was ${v.original})` : ""}` };
  switch (v?.status) {
    case "confirmed": return { label: v.note === "2 readers" ? "2 readers" : "3 reads", cls: "ok", title: `Read the same way by independent readers\n${readings}` };
    case "ai_confirmed": return { label: "AI", cls: "ok", title: `Confirmed by the AI reading the page\n${readings}` };
    case "corrected":
    case "ai_corrected": return { label: "corrected", cls: "warn", title: `Was ${v.original}; two other readings agreed on ${e.value_text}\n${readings}` };
    case "to_fill": return { label: "to fill in", cls: "crit", title: `Readings differ; left blank\n${readings}` };
    // A value only one reader could see is the least certain thing on the
    // screen; it may not wear the neutral tag (docs/UI.md §6).
    case "unverified":
    case "single": return { label: "1 reader", cls: "warn", title: "Only one reading of this spot could be made; confirm it on the page" };
    case "embedded": return null;
    default: return null;
  }
}

export function ConfidenceCell({ entity }: { entity: Entity }) {
  const status = entity.verification?.status;
  if (status === "to_fill" && !entity.verified) {
    return <span className="badge crit" title="Left blank: the readings disagree. Fill it in from the page.">—</span>;
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

/** The value as printed, or the blank and what the readers saw. */
export function ValueCell({ entity }: { entity: Entity }) {
  const v = entity.verification;
  if (v?.status === "to_fill" && !entity.verified) {
    const seen = v.readings ? Object.values(v.readings).filter(Boolean) : [];
    return (
      <span>
        <FlagDots entity={entity} />
        <b className="muted">— to fill in</b>
        {seen.length > 0 && <span className="small muted"> read as {Array.from(new Set(seen)).join(" / ")}</span>}
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

export function VerifiedBox({ entity, onChange }: { entity: Entity; onChange?: (e: Entity) => void }) {
  const [busy, setBusy] = useState(false);
  const blank = entity.verification?.status === "to_fill" && !entity.verified;
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
  return (
    <label className="small" title={blank ? "Fill in the value first (To fill in tab)" : entity.verified ? "Untick to go back to the machine reading" : "Tick when you have checked this value on the page"} style={{ whiteSpace: "nowrap" }}>
      <input type="checkbox" checked={entity.verified} disabled={busy || blank} onChange={toggle} /> verified
    </label>
  );
}

export default function EntityRow({ entity, onJump, showType, showDoc, onChange }: { entity: Entity; onJump: (e: Entity) => void; showType?: boolean; showDoc?: boolean; onChange?: (e: Entity) => void }) {
  return (
    <tr className="clickable" onClick={() => onJump(entity)}>
      {showType && <td>{entity.entity_type.replace(/_/g, " ")}</td>}
      <td><ValueCell entity={entity} /></td>
      <td>{entity.qualifier || "—"}</td>
      <td>{entity.application || (entity.equipment ? `${entity.equipment}${entity.equipment_model ? " " + entity.equipment_model : ""}` : "—")}</td>
      <td className="small">{showDoc && entity.document_name ? <><span className="muted">{entity.document_name}</span><br /></> : null}p.{entity.page}{entity.section ? <span className="muted"> · {entity.section}</span> : null}</td>
      <td><ConfidenceCell entity={entity} /></td>
      <td onClick={(e) => e.stopPropagation()}><VerifiedBox entity={entity} onChange={onChange} /></td>
      <td onClick={(e) => e.stopPropagation()}><SendToCalculator entity={entity} /></td>
    </tr>
  );
}
