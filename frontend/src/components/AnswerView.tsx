import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Answer, Citation, Entity } from "../types";
import SendToCalculator from "./SendToCalculator";

interface Props {
  answer: Answer;
  onCitation?: (c: Citation) => void;
  onEntity?: (e: Entity) => void;
  showDocumentNames?: boolean;
}

const STATUS_BADGE: Record<string, { cls: string; label: string }> = {
  found: { cls: "ok", label: "Documented" },
  partial: { cls: "warn", label: "Partial" },
  not_found: { cls: "crit", label: "Not found in documents" },
  unverified: { cls: "crit", label: "Unverified" },
};

export default function AnswerView({ answer, onCitation, onEntity, showDocumentNames = true }: Props) {
  const st = STATUS_BADGE[answer.status] || { cls: "", label: answer.status };
  return (
    <div>
      <div className="status-line">
        <span className={`badge ${st.cls}`}>{st.label}</span>
        <span className="badge">{answer.answer_kind.replace(/_/g, " ")}</span>
        <span className="badge">{answer.mode === "ai" ? "AI analysis" : answer.mode === "extractive" ? "extractive (no AI key)" : "no results"}</span>
      </div>
      <div className="md">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{answer.answer}</ReactMarkdown>
      </div>
      {answer.conflicts?.length > 0 && (
        <div className="alert crit">
          <b>Conflicting sources</b>
          <ul className="plain">{answer.conflicts.map((c, i) => <li key={i}>{c}</li>)}</ul>
        </div>
      )}
      {answer.verification_warnings?.length > 0 && (
        <div className="alert warn">
          <b>⚠ Verify against the original page</b>
          <ul className="plain">{answer.verification_warnings.map((w, i) => <li key={i}>{w}</li>)}</ul>
        </div>
      )}
      {answer.citations?.length > 0 && (
        <div className="cite-list">
          {answer.citations.map((c, i) => (
            <button key={i} className={`chip${c.verified ? "" : " unverified"}`} title={c.quote} onClick={() => onCitation?.(c)}>
              {showDocumentNames && <span className="muted">{c.document_name} ·</span>} Page {c.page}
              {c.section ? ` · ${c.section}` : ""}
              {!c.verified && " (quote not verified)"}
            </button>
          ))}
        </div>
      )}
      {answer.entities?.length > 0 && (
        <details style={{ marginTop: 8 }}>
          <summary className="small muted">Documented values used ({answer.entities.length})</summary>
          <table className="small">
            <thead><tr><th>Type</th><th>Value</th><th>Qualifier</th><th>Application</th><th>Source</th><th></th></tr></thead>
            <tbody>
              {answer.entities.slice(0, 20).map((e) => (
                <tr key={e.id} className="clickable" onClick={() => onEntity?.(e)}>
                  <td>{e.entity_type.replace(/_/g, " ")}</td>
                  <td><b>{e.value_text}</b>{e.flags?.some((f) => f.severity === "critical") && <span className="badge crit" style={{ marginLeft: 4 }}>verify</span>}</td>
                  <td>{e.qualifier || "—"}</td>
                  <td>{e.application || "—"}</td>
                  <td>{showDocumentNames && e.document_name ? `${e.document_name}, ` : ""}p.{e.page}</td>
                  <td onClick={(ev) => ev.stopPropagation()}><SendToCalculator entity={e} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      )}
    </div>
  );
}
