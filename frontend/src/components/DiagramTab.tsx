import { useEffect, useState } from "react";
import { api } from "../api";
import type { DiagramAnalysis, DocumentDetail, Highlight } from "../types";
import type { Jump } from "../pages/DocumentPage";

export default function DiagramTab({ doc, page, jump, setHighlights }: { doc: DocumentDetail; page: number; jump: Jump; setHighlights: (h: Highlight[]) => void }) {
  const [result, setResult] = useState<DiagramAnalysis | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const meta = doc.pages.find((p) => p.page_number === page);

  useEffect(() => {
    setResult(null);
    setError(null);
    api.getDiagram(doc.id, page).then((r) => { if (r) { setResult(r); overlay(r); } }).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [doc.id, page]);

  const overlay = (r: DiagramAnalysis) => {
    if (!meta) return;
    const hs: Highlight[] = [];
    for (const c of r.components) {
      if (c.bbox_pct && c.bbox_pct.length === 4) {
        const [x0, y0, x1, y1] = c.bbox_pct;
        hs.push({ bbox: [(x0 / 100) * meta.width, (y0 / 100) * meta.height, (x1 / 100) * meta.width, (y1 / 100) * meta.height], kind: "component", label: `${c.id} ${c.label}`, confidence: c.confidence });
      }
    }
    setHighlights(hs);
  };

  const run = async (force = false) => {
    setBusy(true);
    setError(null);
    try {
      const r = await api.analyseDiagram(doc.id, page, force);
      setResult(r);
      overlay(r);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <div className="row" style={{ marginBottom: 8 }}>
        <div>
          <b>Page {page}</b>{" "}
          {meta?.is_diagram ? <span className="badge accent">looks like a diagram (score {meta.diagram_score})</span> : <span className="badge">diagram score {meta?.diagram_score ?? 0}</span>}
        </div>
        <span className="grow" />
        <button className="btn primary sm" disabled={busy} onClick={() => run(!!result)}>{busy ? "Analysing…" : result ? "Re-analyse" : "Analyse this page"}</button>
      </div>
      {doc.structure?.diagram_pages?.length ? <p className="small muted">Diagram pages in this document: {doc.structure.diagram_pages.map((p) => <a key={p} href="#" onClick={(e) => { e.preventDefault(); jump(p); }} style={{ marginRight: 6 }}>p.{p}</a>)}</p> : null}
      {error && <div className="alert crit">{error}</div>}
      {!result && !busy && <p className="muted small">Visual analysis identifies components (batteries, inverters, chargers, fuses, breakers, busbars, switches…) and connections with a confidence level for each. Nothing is invented: uncertain items are marked “possible” and illegible regions are listed.</p>}
      {result && (
        <div>
          <div className="row small muted" style={{ marginBottom: 6 }}>
            <span className="badge">{result.engine}</span>
            <span>{result.diagram_type.replace(/_/g, " ")}</span>
            {result.system_voltage && <span>· system voltage {result.system_voltage}</span>}
          </div>
          <div className="legend">
            {Object.entries(result.confidence_legend || {}).map(([k, v]) => <span key={k} className={k} title={v}>{k}</span>)}
          </div>
          {result.notes?.map((n, i) => <div key={i} className="alert info">{n}</div>)}
          <h4>Components ({result.components.length})</h4>
          <table className="small">
            <thead><tr><th>Id</th><th>Type</th><th>Label</th><th>Rating (as printed)</th><th>Confidence</th></tr></thead>
            <tbody>
              {result.components.map((c) => (
                <tr key={c.id} className="clickable" onClick={() => { if (c.bbox_pct && meta) { const [x0, y0, x1, y1] = c.bbox_pct; jump(page, [(x0 / 100) * meta.width, (y0 / 100) * meta.height, (x1 / 100) * meta.width, (y1 / 100) * meta.height], "primary", c.label); } }}>
                  <td className="mono">{c.id}</td><td>{c.type.replace(/_/g, " ")}</td><td>{c.label}</td><td>{c.rating || "—"}</td><td className={`conf-${c.confidence}`}>{c.confidence}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <h4 style={{ marginTop: 10 }}>Connections ({result.connections.length})</h4>
          {result.connections.length === 0 ? <p className="small muted">No connections asserted{result.engine === "heuristic" ? " (visual engine not available)" : ""}.</p> : (
            <table className="small">
              <thead><tr><th>From</th><th>To</th><th>Polarity</th><th>Circuit</th><th>Flow</th><th>Protection</th><th>Confidence</th></tr></thead>
              <tbody>
                {result.connections.map((c, i) => (
                  <tr key={i}>
                    <td className="mono">{c.from_id}</td><td className="mono">{c.to_id}</td><td>{c.polarity.replace(/_/g, " ")}</td><td>{c.circuit}</td><td>{c.direction.replace(/_/g, " ")}</td>
                    <td>{c.protection.map((p, j) => <span key={j}>{p.type}{p.rating ? ` ${p.rating}` : ""} <span className={`conf-${p.confidence}`}>({p.confidence})</span>{j < c.protection.length - 1 ? ", " : ""}</span>) || "—"}</td>
                    <td className={`conf-${c.confidence}`}>{c.confidence}{c.note ? <div className="muted">{c.note}</div> : null}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {result.unreadable_regions?.length ? <div className="alert warn"><b>Unreadable / ambiguous:</b><ul className="plain">{result.unreadable_regions.map((u, i) => <li key={i}>{u}</li>)}</ul></div> : null}
        </div>
      )}
    </div>
  );
}
