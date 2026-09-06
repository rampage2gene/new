import type { Entity } from "../types";
import SendToCalculator from "./SendToCalculator";

export function FlagDots({ entity }: { entity: Entity }) {
  if (!entity.flags?.length) return null;
  const worst = entity.flags.some((f) => f.severity === "critical") ? "critical" : entity.flags.some((f) => f.severity === "warning") ? "warning" : "info";
  return <span className={`flag-dot ${worst}`} title={entity.flags.map((f) => f.message).join("\n")} />;
}

export function ConfidenceCell({ entity }: { entity: Entity }) {
  const c = entity.confidence;
  const cls = c >= 0.9 ? "ok" : c >= 0.75 ? "warn" : "crit";
  return (
    <span className={`badge ${cls}`} title={entity.ocr_confidence != null ? `OCR word confidence ${Math.round(entity.ocr_confidence * 100)}%` : "Embedded text"}>
      {Math.round(c * 100)}%
    </span>
  );
}

export default function EntityRow({ entity, onJump, showType, showDoc }: { entity: Entity; onJump: (e: Entity) => void; showType?: boolean; showDoc?: boolean }) {
  return (
    <tr className="clickable" onClick={() => onJump(entity)}>
      {showType && <td>{entity.entity_type.replace(/_/g, " ")}</td>}
      <td><FlagDots entity={entity} /><b>{entity.value_text}</b>{entity.device_type ? <span className="muted"> {entity.device_type}</span> : null}</td>
      <td>{entity.qualifier || "—"}</td>
      <td>{entity.application || (entity.equipment ? `${entity.equipment}${entity.equipment_model ? " " + entity.equipment_model : ""}` : "—")}</td>
      <td className="small">{showDoc && entity.document_name ? <><span className="muted">{entity.document_name}</span><br /></> : null}p.{entity.page}{entity.section ? <span className="muted"> · {entity.section}</span> : null}</td>
      <td><ConfidenceCell entity={entity} /></td>
      <td onClick={(e) => e.stopPropagation()}><SendToCalculator entity={entity} /></td>
    </tr>
  );
}
