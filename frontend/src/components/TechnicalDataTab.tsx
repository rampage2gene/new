import { useEffect, useState } from "react";
import { api } from "../api";
import type { DocumentDetail, Entity, SpecExtraction } from "../types";
import EntityRow from "./EntityRow";
import type { Jump } from "../pages/DocumentPage";

export default function TechnicalDataTab({ doc, jump }: { doc: DocumentDetail; jump: Jump }) {
  const [spec, setSpec] = useState<SpecExtraction | null>(null);
  const [open, setOpen] = useState<Record<string, boolean>>({});
  const [filter, setFilter] = useState("");

  useEffect(() => {
    api.specExtraction(doc.id).then((s) => {
      setSpec(s);
      const o: Record<string, boolean> = {};
      s.groups.forEach((g) => (o[g.key] = g.count > 0 && g.count <= 40));
      setOpen(o);
    });
  }, [doc.id]);

  if (!spec) return <span className="spinner" />;
  const f = filter.toLowerCase();
  const matches = (e: Entity) => !f || [e.value_text, e.application, e.qualifier, e.section, e.snippet, e.equipment, e.equipment_model].some((x) => x && x.toLowerCase().includes(f));
  /** A row was ticked or filled in: swap it in place, no reload. */
  const replace = (updated: Entity) =>
    setSpec((s) => s && { ...s, groups: s.groups.map((g) => ({ ...g, items: g.items.map((it: any) => (it.id === updated.id ? updated : it)) })) });

  return (
    <div>
      <div className="row" style={{ marginBottom: 10 }}>
        <input type="text" placeholder="Filter values, applications, sections…" value={filter} onChange={(e) => setFilter(e.target.value)} />
        <a className="btn sm" href={api.exportEntitiesUrl("csv", [doc.id])}>CSV</a>
        <a className="btn sm" href={api.exportWorkbookUrl([doc.id])} title="Excel workbook: values with page links, tables, and calculator sheets with live formulas">Workbook</a>
      </div>
      <p className="small muted">
        Every value keeps its page, section and location. On scanned pages each value is read by two independent OCR engines; where they disagree a third read of that line decides, and with no majority the value is left blank rather than guessed (see the <b>To fill in</b> tab).
        <b> ✓ 100%</b> means two readers agreed or you confirmed it; 95% a majority of three or the PDF's own text; lower is a single reading. Dots mark verification flags.
      </p>
      {spec.groups.map((g) => {
        const items = g.key === "warnings" ? g.items : (g.items as Entity[]).filter(matches);
        return (
          <div className="group" key={g.key}>
            <div className="group-head" onClick={() => setOpen((o) => ({ ...o, [g.key]: !o[g.key] }))}>
              <span>{open[g.key] ? "▾" : "▸"} {g.label}</span>
              <span className="badge">{items.length}</span>
            </div>
            {open[g.key] && items.length > 0 && (
              g.key === "warnings" ? (
                <table>
                  <tbody>
                    {items.map((w: any, i: number) => (
                      <tr key={i} className="clickable" onClick={() => jump(w.page, w.bbox)}>
                        <td style={{ width: 60 }} className="small">p.{w.page}</td>
                        <td>{w.text}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <table>
                  <thead>
                    <tr>{g.key === "electrical_ratings" || g.key === "installation_requirements" ? <th>Type</th> : null}<th>Value</th><th>Qualifier</th><th>Application / Equipment</th><th>Source</th><th>Conf.</th><th>Checked</th><th></th></tr>
                  </thead>
                  <tbody>
                    {(items as Entity[]).map((e) => (
                      <EntityRow key={e.id} entity={e} showType={g.key === "electrical_ratings" || g.key === "installation_requirements"} onJump={(x) => jump(x.page, x.bbox, "primary", x.value_text)} onChange={replace} />
                    ))}
                  </tbody>
                </table>
              )
            )}
          </div>
        );
      })}
    </div>
  );
}
