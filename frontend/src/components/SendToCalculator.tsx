import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, PREFILL_KEY } from "../api";
import type { CalculatorPrefill, CalculatorSpec, Entity } from "../types";

let cache: CalculatorSpec[] | null = null;

export function readPrefill(): CalculatorPrefill | null {
  try {
    const raw = sessionStorage.getItem(PREFILL_KEY);
    return raw ? (JSON.parse(raw) as CalculatorPrefill) : null;
  } catch {
    return null;
  }
}

export function writePrefill(p: CalculatorPrefill | null) {
  if (p) sessionStorage.setItem(PREFILL_KEY, JSON.stringify(p));
  else sessionStorage.removeItem(PREFILL_KEY);
}

/** Document-to-calculator workflow: pick a calculator input that accepts this entity. */
export default function SendToCalculator({ entity, label = "→ Calc" }: { entity: Entity; label?: string }) {
  const [specs, setSpecs] = useState<CalculatorSpec[] | null>(cache);
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLSpanElement>(null);
  const navigate = useNavigate();

  useEffect(() => {
    if (!specs) api.calculators().then((s) => { cache = s; setSpecs(s); }).catch(() => setSpecs([]));
  }, [specs]);
  useEffect(() => {
    if (!open) return;
    const h = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, [open]);

  const options: { calc: CalculatorSpec; inputKey: string; inputLabel: string; preferred: boolean }[] = [];
  for (const c of specs || []) {
    for (const inp of c.inputs) {
      if (inp.entity_types.includes(entity.entity_type)) {
        options.push({ calc: c, inputKey: inp.key, inputLabel: inp.label, preferred: !inp.qualifiers.length || (entity.qualifier != null && inp.qualifiers.includes(entity.qualifier)) });
      }
    }
  }
  options.sort((a, b) => Number(b.preferred) - Number(a.preferred));
  if (!options.length) return null;

  const send = (o: (typeof options)[number]) => {
    const existing = readPrefill();
    const inputs = existing && existing.calculatorId === o.calc.id ? { ...existing.inputs } : {};
    let value: unknown = entity.value;
    if (entity.entity_type === "wire_size") value = entity.value_text;
    inputs[o.inputKey] = {
      value,
      unit: entity.unit,
      source: { document_id: entity.document_id, document_name: entity.document_name || undefined, page: entity.page, section: entity.section, entity_id: entity.id, snippet: entity.snippet, confidence: entity.confidence },
      origin: "document",
    };
    writePrefill({ calculatorId: o.calc.id, inputs });
    setOpen(false);
    navigate(`/calculators/${o.calc.id}`);
  };

  return (
    <span ref={ref} style={{ position: "relative", display: "inline-block" }}>
      <button className="btn sm" onClick={() => setOpen((v) => !v)} title="Send this value to a calculator">{label}</button>
      {open && (
        <div style={{ position: "absolute", right: 0, top: "110%", zIndex: 20, background: "#fff", border: "1px solid var(--border)", borderRadius: 6, boxShadow: "0 4px 14px rgba(0,0,0,0.12)", minWidth: 260, padding: 4 }}>
          <div className="small muted" style={{ padding: "4px 8px" }}>Send <b>{entity.value_text}</b> to…</div>
          {options.map((o, i) => (
            <div key={i} style={{ padding: "6px 8px", cursor: "pointer", borderRadius: 4 }} className="menu-item" onMouseDown={() => send(o)} onMouseOver={(e) => (e.currentTarget.style.background = "var(--accent-soft)")} onMouseOut={(e) => (e.currentTarget.style.background = "")}>
              <b>{o.calc.name}</b> <span className="muted">· {o.inputLabel}</span>{o.preferred && <span className="badge ok" style={{ marginLeft: 6 }}>match</span>}
            </div>
          ))}
        </div>
      )}
    </span>
  );
}
