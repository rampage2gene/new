import { useState } from "react";
import { api } from "../api";
import type { Answer, DocumentDetail } from "../types";
import AnswerView from "./AnswerView";
import type { Jump } from "../pages/DocumentPage";

interface Msg { role: "user" | "assistant"; content: string; answer?: Answer }

const SUGGESTIONS = [
  "What size fuse does this equipment require?",
  "What wire size is required for the DC connection?",
  "Find all breaker ratings.",
  "What torque should be used on the battery terminals?",
  "Where are the installation clearances specified?",
  "What is the maximum input current?",
];

export default function AssistantPanel({ doc, jump }: { doc: DocumentDetail; jump: Jump }) {
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);

  const ask = async (question: string) => {
    if (!question.trim() || busy) return;
    setQ("");
    const history = msgs.map((m) => ({ role: m.role, content: m.content }));
    setMsgs((m) => [...m, { role: "user", content: question }]);
    setBusy(true);
    try {
      const a = await api.ask(question, [doc.id], history);
      setMsgs((m) => [...m, { role: "assistant", content: a.answer, answer: a }]);
      const first = a.citations?.[0];
      if (first && a.status !== "not_found") jump(first.page, first.bbox, "secondary");
    } catch (e: any) {
      setMsgs((m) => [...m, { role: "assistant", content: `Error: ${e.message}` }]);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="chat">
      <div className="chat-log">
        {msgs.length === 0 && (
          <div>
            <p className="muted small">Ask about this document. Every technical answer is tied to the page and section it came from; click a citation to open and highlight the source. If the document does not contain the information, the assistant says so instead of guessing.</p>
            <div className="suggestions">{SUGGESTIONS.map((s) => <button key={s} className="chip" onClick={() => ask(s)}>{s}</button>)}</div>
          </div>
        )}
        {msgs.map((m, i) => (
          <div key={i} className={`msg ${m.role}`}>
            <div className="bubble">
              {m.answer ? (
                <AnswerView answer={m.answer} showDocumentNames={false} onCitation={(c) => jump(c.page, c.bbox, "primary")} onEntity={(e) => jump(e.page, e.bbox, "primary", e.value_text)} />
              ) : (
                m.content
              )}
              {m.answer?.follow_up_questions?.length ? <div className="suggestions">{m.answer.follow_up_questions.map((s) => <button key={s} className="chip" onClick={() => ask(s)}>{s}</button>)}</div> : null}
            </div>
          </div>
        ))}
        {busy && <div className="muted small"><span className="spinner" /> Searching the document and composing a cited answer…</div>}
      </div>
      <div className="chat-input">
        <textarea value={q} placeholder="Ask a technical question about this document…" onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); ask(q); } }} />
        <button className="btn primary" disabled={busy || !q.trim()} onClick={() => ask(q)}>Ask</button>
      </div>
    </div>
  );
}
