import type { DocumentDetail } from "../types";
import type { Jump } from "../pages/DocumentPage";

export default function StructureTab({ doc, jump }: { doc: DocumentDetail; jump: Jump }) {
  const s = doc.structure || {};
  return (
    <div>
      <div className="card tight">
        <h4>Document</h4>
        <table className="small">
          <tbody>
            <tr><td className="muted">Title</td><td>{doc.title}</td></tr>
            <tr><td className="muted">Manufacturer</td><td>{doc.manufacturer || "—"}</td></tr>
            <tr><td className="muted">Product</td><td>{doc.product || "—"}</td></tr>
            <tr><td className="muted">Model</td><td>{doc.model_number || "—"}</td></tr>
            <tr><td className="muted">Type</td><td>{doc.document_type || "—"}</td></tr>
            <tr><td className="muted">Revision / date</td><td>{[doc.revision, doc.publication_date].filter(Boolean).join(" · ") || "—"}</td></tr>
            <tr><td className="muted">Equipment</td><td>{doc.equipment_types.join(", ") || "—"}</td></tr>
            <tr><td className="muted">Pages</td><td>{doc.page_count} ({doc.embedded_text_pages} embedded text, {doc.ocr_pages} OCR{doc.stats?.avg_ocr_confidence != null ? `, avg OCR confidence ${Math.round(doc.stats.avg_ocr_confidence * 100)}%` : ""})</td></tr>
          </tbody>
        </table>
      </div>
      <h4>Outline</h4>
      {s.sections?.length ? (
        <ul className="plain" style={{ listStyle: "none", paddingLeft: 0 }}>
          {s.sections.map((sec, i) => (
            <li key={i} style={{ paddingLeft: (sec.level - 1) * 14, marginBottom: 2 }}>
              <a href="#" onClick={(e) => { e.preventDefault(); jump(sec.page, sec.bbox, "secondary"); }}>{sec.title}</a> <span className="muted small">p.{sec.page}</span>
            </li>
          ))}
        </ul>
      ) : <p className="muted small">No headings detected.</p>}
      {s.warnings?.length ? (
        <>
          <h4>Warnings & notices</h4>
          {s.warnings.map((w, i) => (
            <div key={i} className="alert warn" style={{ cursor: "pointer" }} onClick={() => jump(w.page, w.bbox)}>
              <span className="small muted">p.{w.page}</span> {w.text}
            </div>
          ))}
        </>
      ) : null}
      {s.tables?.length ? (
        <>
          <h4>Tables</h4>
          {s.tables.map((t, i) => (
            <div key={i} className="card tight" style={{ cursor: "pointer" }} onClick={() => jump(t.page, t.bbox, "secondary")}>
              <div className="small muted">Page {t.page}{t.section ? ` · ${t.section}` : ""}</div>
              <div style={{ overflowX: "auto" }}>
                <table className="small">
                  <tbody>{t.rows.slice(0, 12).map((r, ri) => <tr key={ri}>{r.map((c, ci) => ri === 0 ? <th key={ci}>{c}</th> : <td key={ci}>{c}</td>)}</tr>)}</tbody>
                </table>
                {t.rows.length > 12 && <div className="small muted">… {t.rows.length - 12} more rows</div>}
              </div>
            </div>
          ))}
        </>
      ) : null}
      {s.figures?.length ? (
        <>
          <h4>Figures</h4>
          <ul className="plain">{s.figures.map((f, i) => <li key={i}><a href="#" onClick={(e) => { e.preventDefault(); jump(f.page, f.bbox, "secondary"); }}>{f.caption}</a> <span className="muted small">p.{f.page}</span></li>)}</ul>
        </>
      ) : null}
      {s.diagram_pages?.length ? <p className="small">Diagram pages: {s.diagram_pages.map((p) => <a key={p} href="#" onClick={(e) => { e.preventDefault(); jump(p); }} style={{ marginRight: 6 }}>p.{p}</a>)}</p> : null}
    </div>
  );
}
