import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import type { CheatSheetEntry, DetectedTable, DocumentSummary, ReferenceStatus, ReferenceTable, ReferenceTableId, ReferenceTableRow } from "../types";

/** The owner's ABYC E-11 reference: the tables the circuit calculator
 *  computes with, and the installation reminders.
 *
 *  Every table is imported from the owner's own copy of the standard
 *  (a table the app detected on a page), corrected cell by cell against that
 *  page, and confirmed by the person - the app never confirms a table on its
 *  own, and never fills a cell it could not read. A cell the import left
 *  blank is highlighted with a one-line ask. Nothing here is typed from
 *  memory: what is not on the page stays blank. */
export default function ReferencePane() {
  const navigate = useNavigate();
  // Set by the open table editor while it holds edits nobody has saved, so
  // opening another table asks before those edits are thrown away.
  const unsaved = useRef<string | null>(null);
  const leaveOk = () => !unsaved.current || confirm(`Leave "${unsaved.current}" without saving? The cells you typed will be lost.`);
  const [status, setStatus] = useState<ReferenceStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState<ReferenceTableId | null>(null);
  const [sheetOpen, setSheetOpen] = useState(false);

  const load = useCallback(() => api.referenceE11().then((s) => { setStatus(s); setError(null); }).catch((e) => setError(e?.message ?? String(e))), []);
  useEffect(() => { load(); }, [load]);

  if (error && !status) return <div className="calc-form card"><div className="alert crit">{error} Try again; if it keeps failing, open Diagnostics in the sidebar.</div></div>;
  if (!status) return <div className="calc-form card"><span className="spinner" /> Loading the reference tables…</div>;

  const badge = (s: ReferenceTableRow["status"]) => s === "confirmed" ? <span className="badge ok">confirmed</span> : s === "draft" ? <span className="badge warn">draft, not yet confirmed</span> : s === "fixture" ? <span className="badge warn">test data</span> : <span className="badge crit">missing</span>;
  // What is left to do comes first; a settled table is not the day's work.
  const rank = (s: ReferenceTableRow["status"]) => (s === "missing" ? 0 : s === "draft" ? 1 : s === "fixture" ? 2 : 3);
  const tables = [...status.tables].sort((a, b) => rank(a.status) - rank(b.status));
  const done = status.confirmed.length;

  return (
    <div className="calc-form card" style={{ flex: 2.2 }}>
      <h2>ABYC E-11 reference</h2>
      <p className="small muted">
        The circuit calculator computes only from these tables, copied from your own copy of the standard and confirmed by you against the page. A table that is missing or still a draft makes the calculator leave its part blank and ask you for the value instead. Nothing here is typed in by the app.
      </p>
      {status.fixture && <div className="alert warn">These are the synthetic test tables, with made-up numbers. Import your own from the standard before relying on a result.</div>}
      {!status.installed && (
        <div className="empty">
          No E-11 tables yet. Open the document that holds the standard, then use <b>Import from a document</b> on each table below: the app copies the cells it can read from the page and leaves the rest for you to type. Your tables are saved in <span className="mono">{status.folders.yours}</span>.
        </div>
      )}
      <p className="small" style={{ margin: "6px 0" }}><b>{done} of {status.tables.length}</b> tables confirmed{done < status.tables.length ? `; ${status.tables.length - done} still to import, check or confirm` : "."}</p>
      <div className="table-scroll">
        <table>
          <thead><tr><th>Table</th><th className="hide-sm">Page</th><th>Status</th><th></th></tr></thead>
          <tbody>
            {tables.map((t) => (
              <tr key={t.id} className="clickable" onClick={() => { if (t.id !== open && leaveOk()) { setOpen(t.id); setSheetOpen(false); } }}>
                <td>{t.layout.title}{t.origin === "yours" ? <span className="small muted"> · yours</span> : null}</td>
                <td className="hide-sm small">{t.page ? `p. ${t.page}` : "—"}</td>
                <td>{badge(t.status)}</td>
                <td><button className="btn sm" onClick={(e) => { e.stopPropagation(); if (t.id !== open && leaveOk()) { setOpen(t.id); setSheetOpen(false); } }}>{t.status === "missing" ? "Add" : "Open"}</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="row" style={{ marginTop: 10 }}>
        <button className="btn" onClick={() => { if (!leaveOk()) return; setSheetOpen((o) => !o); setOpen(null); }}>{sheetOpen ? "Hide" : "Edit"} the reminders ({status.cheatsheet.entries})</button>
        <a className="btn" href={api.referenceDownloadUrl()} title="The confirmed tables and the reminders, zipped in the layout the e11-calc library reads">Download for the web app (.zip)</a>
      </div>
      {open && <TableEditor id={open} onChanged={load} onClose={() => { if (leaveOk()) setOpen(null); }} onDirty={(title) => { unsaved.current = title; }} onOpenPage={(docId, page) => navigate(`/documents/${docId}?page=${page}`)} />}
      {sheetOpen && <CheatSheetEditor onChanged={load} />}
    </div>
  );
}

// ------------------------------------------------------------------- one table

type Row = Record<string, any>;

function TableEditor({ id, onChanged, onClose, onDirty, onOpenPage }: { id: ReferenceTableId; onChanged: () => void; onClose: () => void; onDirty: (title: string | null) => void; onOpenPage: (docId: string, page: number) => void }) {
  const [table, setTable] = useState<ReferenceTable | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState<string | null>(null);
  const [docs, setDocs] = useState<DocumentSummary[]>([]);
  const [docId, setDocId] = useState("");
  const [detected, setDetected] = useState<DetectedTable[]>([]);
  const [pick, setPick] = useState("");

  const [dirty, setDirty] = useState(false);
  useEffect(() => {
    setTable(null); setError(null); setSaved(null); setDirty(false);
    setDocId(""); setPick("");
    api.referenceTable(id).then((t) => setTable(t.status === "missing" ? blankTable(t) : t)).catch((e) => setError(e?.message ?? String(e)));
    api.listDocuments().then((d) => setDocs(d.filter((x) => x.status === "ready"))).catch(() => {});
  }, [id]);
  useEffect(() => {
    if (!docId) { setDetected([]); return; }
    api.detectedTables(docId).then(setDetected).catch(() => setDetected([]));
  }, [docId]);

  // Tell the pane while edits are unsaved (before the early returns: hooks
  // must run on every render).
  const title = table?.layout.title;
  useEffect(() => { onDirty(dirty && title ? title : null); return () => onDirty(null); }, [dirty, title]);

  if (error && !table) return <div className="alert crit" style={{ marginTop: 10 }}>{error}</div>;
  if (!table) return <div style={{ marginTop: 10 }}><span className="spinner" /> Loading the table…</div>;

  const set = (patch: Partial<ReferenceTable>) => { setDirty(true); setTable((t) => t && { ...t, ...patch }); };
  const setSource = (patch: Record<string, unknown>) => set({ source: { document: "", ...(table.source || {}), ...patch } as ReferenceTable["source"] });
  const setRows = (rows: Row[]) => set({ rows });
  const needed = (key: string) => table.edits?.[key] === "needed" || table.edits?.[key] === "check";

  // Cells nobody has typed: the highlighted ones. Confirm is refused while
  // any remain, because "confirmed" must mean every cell was checked against
  // the page - an unread cell that slipped through would be a guess the
  // calculator then treats as the standard.
  const unread = missingCells(table);
  // Where the values come from: a page of the standard, or the owner's catalog.
  const catalog = isCatalog(table.kind);
  const fromWhere = catalog ? "from the catalog" : "from the page";
  const save = async (status: "draft" | "confirmed") => {
    if (status === "confirmed" && unread.length) {
      setError(`${unread.length} cell${unread.length === 1 ? " is" : "s are"} still empty or unchecked (${unread.slice(0, 4).join(", ")}${unread.length > 4 ? "…" : ""}). Type them ${fromWhere}, or save as a draft for now.`);
      return;
    }
    setBusy(true); setError(null); setSaved(null);
    try {
      const body = { ...table, status };
      delete (body as any).origin; delete (body as any).layout;
      const t = await api.saveReferenceTable(id, body);
      setTable(t); setDirty(false);
      setSaved(status === "confirmed" ? "Confirmed. The calculator now uses this table." : "Saved as a draft. The calculator will not use it until you confirm it against the page.");
      onChanged();
    } catch (e: any) {
      setError(e?.message ?? String(e));
    } finally {
      setBusy(false);
    }
  };
  const remove = async () => {
    const cells = table.rows.length;
    if (!confirm(`Delete your copy of "${table.layout.title}"?${cells ? ` The ${cells} row${cells === 1 ? "" : "s"} you typed or confirmed will be lost` : ""} and the calculator will fall back to the bundled copy, or leave a blank if there is none.`)) return;
    setBusy(true); setError(null);
    try { const t = await api.deleteReferenceTable(id); setTable(t.status === "missing" ? blankTable(t) : t); onChanged(); }
    catch (e: any) { setError(e?.message ?? String(e)); }
    finally { setBusy(false); }
  };
  const doImport = async () => {
    const d = detected[Number(pick)];
    if (!d || !docId) return;
    setBusy(true); setError(null); setSaved(null);
    try {
      const t = await api.importReferenceTable(id, { document_id: docId, page: d.page, table_index: d.table_index });
      setTable(t); setDirty(false);
      setSaved(`Copied what could be read from page ${d.page}. Check every cell against the page, type the ones left blank, then press Confirm.`);
      onChanged();
    } catch (e: any) {
      setError(e?.message ?? String(e));
    } finally {
      setBusy(false);
    }
  };

  const page = table.source?.page;
  const docLink = table.source?.document_id;
  return (
    <div className="card tight" style={{ marginTop: 12 }}>
      <div className="row">
        <h4 style={{ margin: 0 }}>{table.layout.title}</h4>
        <span className="grow" />
        <button className="btn" onClick={onClose}>Close</button>
      </div>
      <p className="small muted" style={{ marginTop: 4 }}>
        {table.status === "confirmed" ? "Confirmed by you. " : table.status === "draft" ? "A draft: not used by the calculator until you confirm it. " : table.status === "fixture" ? "Synthetic test data, not the standard. " : "Not added yet. "}
        {isCatalog(table.kind) ? "Typed from a datasheet or catalog, named below; a highlighted cell still needs a value. " : "Every value must come from the page; a highlighted cell is one the app could not read and needs you to type."}
      </p>
      {!isCatalog(table.kind) && (
        <div className="row" style={{ marginBottom: 8 }}>
          <label className="field" style={{ margin: 0, minWidth: 220 }}>
            <span className="lbl">Import from a document</span>
            <select value={docId} onChange={(e) => { setDocId(e.target.value); setPick(""); }}>
              <option value="">— choose the document —</option>
              {docs.map((d) => <option key={d.id} value={d.id}>{d.title}</option>)}
            </select>
          </label>
          {docId && (
            <label className="field" style={{ margin: 0, minWidth: 220 }}>
              <span className="lbl">Table found on a page</span>
              <select value={pick} onChange={(e) => setPick(e.target.value)}>
                <option value="">{detected.length ? "— choose the table —" : "no tables were detected in this document"}</option>
                {detected.map((d, i) => <option key={i} value={i}>p. {d.page}: {d.header.slice(0, 4).join(" | ").slice(0, 60)} ({d.rows} rows)</option>)}
              </select>
            </label>
          )}
          <button className="btn" disabled={busy || !pick} onClick={doImport}>Copy from that page</button>
        </div>
      )}
      <div className="row" style={{ marginBottom: 8 }}>
        <Field label={catalog ? "Catalog or datasheet" : "Document"} value={table.source?.document || ""} onChange={(v) => setSourceField(setSource, "document", v)} needed={!table.source?.document} />
        {/* A catalog table has no table number or page of the standard; each row names its own catalog page. */}
        {!catalog && <Field label="Table, as printed" value={table.source?.table || ""} onChange={(v) => setSourceField(setSource, "table", v)} />}
        {!catalog && <Field label="Page" type="number" value={page ?? ""} onChange={(v) => setSourceField(setSource, "page", v === "" ? undefined : Number(v))} />}
        {docLink && page ? <a href="#" className="small" onClick={(e) => { e.preventDefault(); onOpenPage(docLink, page); }}>Open page {page}</a> : null}
      </div>

      {table.kind === "constants" && (
        <div className="row">
          <Field label="K for copper" type="number" value={table.values?.K_copper?.value ?? ""} needed={needed("K_copper/value")} onChange={(v) => set({ values: { K_copper: { value: v === "" ? 0 : Number(v), page: table.values?.K_copper?.page ?? page ?? 0 } }, edits: without(table.edits, "K_copper/value") })} />
          <Field label="On page" type="number" value={table.values?.K_copper?.page ?? ""} onChange={(v) => set({ values: { K_copper: { value: table.values?.K_copper?.value ?? 0, page: Number(v) } } })} />
          <Field label="Formula, as printed" value={table.formula_as_printed || ""} onChange={(v) => set({ formula_as_printed: v })} />
          <label className="field" style={{ margin: 0 }}>
            <span className="lbl">L in the formula is{needed("length_definition") ? " · check the page" : ""}</span>
            <select value={table.length_definition || "round_trip"} onChange={(e) => set({ length_definition: e.target.value, edits: without(table.edits, "length_definition") })} className={needed("length_definition") ? "ref-needed" : undefined}>
              <option value="round_trip">the round trip (source to load and back)</option>
              <option value="one_way">one way</option>
            </select>
          </label>
        </div>
      )}

      {table.kind === "circular_mils" && (
        <Grid
          columns={[{ key: "size_awg", label: "Size (AWG)", required: true }, { key: "circular_mils", label: "Circular mils", type: "number", required: true }, { key: "mm2", label: "mm²", type: "number" }, { key: "page", label: "Page", type: "number", required: true }]}
          rows={table.rows || []} onRows={setRows} needed={(r, k) => needed(`${r.size_awg}/${k}`)} blank={{ size_awg: "", circular_mils: null, mm2: null, page: page ?? null }}
        />
      )}

      {table.kind === "ampacity" && (
        <>
          <Field label="Insulation ratings (°C), comma-separated" value={Object.keys(table.columns || {}).join(", ")} onChange={(v) => {
            const cols: Record<string, string> = {};
            v.split(",").map((s) => s.trim()).filter(Boolean).forEach((c) => { cols[c] = "A"; });
            set({ columns: cols, rows: (table.rows || []).map((r: Row) => ({ ...r, values: Object.fromEntries(Object.keys(cols).map((c) => [c, r.values?.[c] ?? null])) })) });
          }} />
          <Grid
            columns={[{ key: "size_awg", label: "Size (AWG)", required: true }, ...Object.keys(table.columns || {}).map((c) => ({ key: `values.${c}`, label: `${c} °C (A)`, type: "number" as const })), { key: "page", label: "Page", type: "number", required: true }]}
            rows={table.rows || []} onRows={setRows} needed={(r, k) => needed(`${r.size_awg}/${k.replace("values.", "")}`)} blank={{ size_awg: "", values: Object.fromEntries(Object.keys(table.columns || {}).map((c) => [c, null])), page: page ?? null }}
          />
        </>
      )}

      {table.kind === "bundling" && (
        <Grid
          columns={[{ key: "min_conductors", label: "From (conductors)", type: "number", required: true }, { key: "max_conductors", label: "To (blank = and above)", type: "number" }, { key: "factor", label: "Factor", type: "number", required: true }, { key: "page", label: "Page", type: "number", required: true }]}
          rows={table.rows || []} onRows={setRows} needed={() => false} blank={{ min_conductors: null, max_conductors: null, factor: null, page: page ?? null }}
        />
      )}

      {table.kind === "voltage_drop_grid" && (
        <>
          <div className="row" style={{ marginBottom: 6 }}>
            <Field label="Nominal voltage" type="number" value={table.nominal_voltage ?? ""} needed={needed("nominal_voltage")} onChange={(v) => set({ nominal_voltage: Number(v), edits: without(table.edits, "nominal_voltage") })} />
            <label className="field" style={{ margin: 0 }}>
              <span className="lbl">Length unit{needed("length_unit") ? " · check the page" : ""}</span>
              <select value={table.length_unit || "ft"} onChange={(e) => set({ length_unit: e.target.value, edits: without(table.edits, "length_unit") })} className={needed("length_unit") ? "ref-needed" : undefined}>
                <option value="ft">feet</option><option value="m">metres</option>
              </select>
            </label>
            <label className="field" style={{ margin: 0 }}>
              <span className="lbl">The lengths are{needed("length_definition") ? " · check the page" : ""}</span>
              <select value={table.length_definition || "round_trip"} onChange={(e) => set({ length_definition: e.target.value, edits: without(table.edits, "length_definition") })} className={needed("length_definition") ? "ref-needed" : undefined}>
                <option value="round_trip">the round trip (source to load and back)</option>
                <option value="one_way">one way</option>
              </select>
            </label>
            <Field label="Lengths (columns), comma-separated" value={(table.lengths || []).join(", ")} onChange={(v) => {
              const lengths = v.split(",").map((s) => Number(s.trim())).filter((n) => !Number.isNaN(n) && s(n));
              set({ lengths, rows: (table.rows || []).map((r: Row) => ({ ...r, sizes: Object.fromEntries(lengths.map((l) => [String(l), r.sizes?.[String(l)] ?? null])) })) });
            }} />
          </div>
          <Grid
            columns={[{ key: "current", label: "Current (A)", type: "number", required: true }, ...(table.lengths || []).map((l: number) => ({ key: `sizes.${l}`, label: `${l} ${table.length_unit || "ft"} (AWG)` })), { key: "page", label: "Page", type: "number", required: true }]}
            rows={table.rows || []} onRows={setRows} needed={() => false} blank={{ current: null, sizes: Object.fromEntries((table.lengths || []).map((l: number) => [String(l), null])), page: page ?? null }}
          />
        </>
      )}

      {table.kind === "fuse_classes" && (
        <>
          <p className="small muted">Typed from each fuse maker's datasheet, which is the document and page each row cites. Load types are the calculator's: inverter, battery_main, motor, resistive, electronics…</p>
          <Grid
            columns={[{ key: "class", label: "Class", required: true }, { key: "interrupting_rating_a", label: "Interrupting rating (A)", type: "number", required: true }, { key: "voltage_rating_v", label: "Voltage rating (V)", type: "number" }, { key: "suits", label: "Suits (load types, comma-separated)", type: "list" }, { key: "source.document", label: "Datasheet", required: true }, { key: "source.page", label: "Page", type: "number", required: true }]}
            rows={table.rows || []} onRows={setRows} needed={() => false} blank={{ class: "", interrupting_rating_a: null, voltage_rating_v: null, suits: [], source: { document: "", page: null } }}
          />
        </>
      )}

      {(table.kind === "cable_dimensions" || table.kind === "heat_shrink" || table.kind === "lugs") && (
        <label className="field" style={{ margin: "0 0 6px", maxWidth: 220 }}>
          <span className="lbl">Diameters in</span>
          <select value={table.diameter_unit || "mm"} onChange={(e) => set({ diameter_unit: e.target.value })}>
            <option value="mm">millimetres</option><option value="in">inches</option>
          </select>
        </label>
      )}

      {table.kind === "cable_dimensions" && (
        <>
          <p className="small muted">Typed from the cable maker's catalog: the outside diameter of each size you use, so the calculator can pick the heat shrink that fits.</p>
          <Grid
            columns={[{ key: "size_awg", label: "Size (AWG)", required: true }, { key: "outside_diameter", label: `Outside diameter (${table.diameter_unit || "mm"})`, type: "number", required: true }, { key: "page", label: "Catalog page", type: "number" }]}
            rows={table.rows || []} onRows={setRows} needed={() => false} blank={{ size_awg: "", outside_diameter: null, page: null }} catalog
          />
        </>
      )}

      {table.kind === "heat_shrink" && (
        <>
          <p className="small muted">Typed from the tubing maker's catalog: each size's inside diameter as supplied and after it has fully shrunk. The calculator picks the smallest size that slides over the cable and its lug and shrinks below the cable.</p>
          <Grid
            columns={[{ key: "size", label: "Size, as the catalog names it", required: true }, { key: "supplied_id", label: `Inside diameter as supplied (${table.diameter_unit || "mm"})`, type: "number", required: true }, { key: "recovered_id", label: `After shrinking (${table.diameter_unit || "mm"})`, type: "number", required: true }, { key: "adhesive", label: "Adhesive-lined", type: "bool" }, { key: "page", label: "Catalog page", type: "number" }]}
            rows={table.rows || []} onRows={setRows} needed={() => false} blank={{ size: "", supplied_id: null, recovered_id: null, adhesive: false, page: null }} catalog
          />
        </>
      )}

      {table.kind === "lugs" && (
        <>
          <p className="small muted">Typed from the lug maker's catalog and your crimper's chart: one row per cable size and stud. The barrel diameter lets the heat shrink be sized over the lug; the crimp die is the setting for that lug and cable.</p>
          <Grid
            columns={[{ key: "size_awg", label: "Size (AWG)", required: true }, { key: "stud", label: "Stud (5/16, 3/8, M8…)", required: true }, { key: "part", label: "Part", required: true }, { key: "barrel_od", label: `Barrel outside diameter (${table.diameter_unit || "mm"})`, type: "number" }, { key: "crimp_die", label: "Crimp die or setting" }, { key: "page", label: "Catalog page", type: "number" }]}
            rows={table.rows || []} onRows={setRows} needed={() => false} blank={{ size_awg: "", stud: "", part: "", barrel_od: null, crimp_die: "", page: null }} catalog
          />
        </>
      )}

      {error && <div className="alert crit">{error}</div>}
      {saved && <div className="alert ok">{saved}</div>}
      <div className="row" style={{ marginTop: 8 }}>
        <button className="btn" disabled={busy} onClick={() => save("draft")}>Save as draft</button>
        <button className="btn primary" disabled={busy || unread.length > 0} onClick={() => save("confirmed")} title={unread.length ? `${unread.length} highlighted cell(s) still need a value ${fromWhere}` : `Press only when every cell matches the ${catalog ? "catalog" : "page"}`}>Confirm this table</button>
        {unread.length > 0 && <span className="small muted">{unread.length} cell{unread.length === 1 ? "" : "s"} still need{unread.length === 1 ? "s" : ""} a value {fromWhere} before this table can be confirmed.</span>}
      </div>
      {/* Deleting is not part of confirming, so it does not sit beside Confirm. */}
      {table.origin === "yours" && <div className="row" style={{ marginTop: 8, justifyContent: "flex-end" }}><button className="btn danger" disabled={busy} onClick={remove}>Delete my copy</button></div>}
    </div>
  );
}

const empty = (v: unknown) => v == null || v === "" || (typeof v === "number" && Number.isNaN(v));

/** Tables typed from datasheets and catalogs: no page of the standard, nothing to import. */
const CATALOG_KINDS = ["fuse_classes", "cable_dimensions", "heat_shrink", "lugs"];
const isCatalog = (kind: string) => CATALOG_KINDS.includes(kind);

/** The cells that still need a person: marked by the import, or required and
 *  never typed (an added row's cells start empty, never with a value). Cells
 *  the page may legitimately leave blank (an ampacity column, a grid cell,
 *  mm², "to" of the last bundling row, a voltage rating) are not counted. */
function missingCells(t: ReferenceTable): string[] {
  const out: string[] = [];
  for (const [key, mark] of Object.entries(t.edits || {})) if (mark === "needed" || mark === "check") out.push(key);
  const page = t.source?.page;
  if (!isCatalog(t.kind) && (empty(page) || page === 0)) out.push("page");
  if (!t.source?.document) out.push("document");
  const rows: Row[] = Array.isArray(t.rows) ? t.rows : [];
  rows.forEach((r, i) => {
    const n = `row ${i + 1}`;
    const need = (cond: boolean, what: string) => { if (cond) out.push(`${n} ${what}`); };
    switch (t.kind) {
      case "circular_mils": need(!r.size_awg, "size"); need(empty(r.circular_mils) || r.circular_mils === 0, "circular mils"); need(empty(r.page) || r.page === 0, "page"); break;
      case "ampacity": need(!r.size_awg, "size"); need(empty(r.page) || r.page === 0, "page"); break;
      case "bundling": need(empty(r.min_conductors), "from"); need(empty(r.factor), "factor"); need(empty(r.page) || r.page === 0, "page"); break;
      case "voltage_drop_grid": need(empty(r.current) || r.current === 0, "current"); need(empty(r.page) || r.page === 0, "page"); break;
      case "fuse_classes": need(!r.class, "class"); need(empty(r.interrupting_rating_a) || r.interrupting_rating_a === 0, "interrupting rating"); need(!r.source?.document, "datasheet"); need(empty(r.source?.page) || r.source?.page === 0, "datasheet page"); break;
      case "cable_dimensions": need(!r.size_awg, "size"); need(empty(r.outside_diameter) || r.outside_diameter === 0, "outside diameter"); break;
      case "heat_shrink": need(!r.size, "size"); need(empty(r.supplied_id) || r.supplied_id === 0, "supplied diameter"); need(empty(r.recovered_id) || r.recovered_id === 0, "shrunk diameter"); break;
      case "lugs": need(!r.size_awg, "size"); need(!r.stud, "stud"); need(!r.part, "part"); break;
    }
  });
  if (t.kind === "constants" && (empty(t.values?.K_copper?.value) || t.values?.K_copper?.value === 0)) out.push("K");
  if (t.kind === "voltage_drop_grid" && !(t.lengths || []).length) out.push("lengths");
  return Array.from(new Set(out));
}

function s(n: number): boolean { return Number.isFinite(n); }

function without(edits: Record<string, string> | undefined, key: string): Record<string, string> {
  const n = { ...(edits || {}) };
  delete n[key];
  return n;
}

function setSourceField(setSource: (p: Record<string, unknown>) => void, key: string, value: unknown) {
  setSource({ [key]: value });
}

/** What an empty table of this kind looks like, so the grid can be typed into before anything is imported. */
function blankTable(t: ReferenceTable): ReferenceTable {
  const base: ReferenceTable = { ...t, title: t.layout.title, status: "draft", source: { document: isCatalog(t.kind) ? "" : "ABYC E-11", page: undefined }, edits: {} };
  switch (t.kind) {
    case "cable_dimensions": case "heat_shrink": case "lugs": return { ...base, diameter_unit: "mm", rows: [] };
    case "constants": return { ...base, values: { K_copper: { value: 0, page: 0 } }, formula_as_printed: "", length_definition: "round_trip", edits: { "K_copper/value": "needed", length_definition: "check" } };
    case "ampacity": return { ...base, columns: { "105": "A" }, rows: [] };
    case "voltage_drop_grid": return { ...base, nominal_voltage: 12, drop_percent: t.id === "voltage_drop_3pct" ? 3 : 10, length_unit: "ft", length_definition: "round_trip", lengths: [], rows: [], edits: { nominal_voltage: "check", length_unit: "check", length_definition: "check" } };
    default: return { ...base, rows: [] };
  }
}

function Field({ label, value, onChange, type = "text", needed }: { label: string; value: string | number; onChange: (v: string) => void; type?: "text" | "number"; needed?: boolean }) {
  return (
    <label className="field" style={{ margin: 0 }}>
      <span className="lbl">{label}{needed ? " · type it from the page" : ""}</span>
      <input type={type} step="any" value={value} onChange={(e) => onChange(e.target.value)} className={needed ? "ref-needed" : undefined} />
    </label>
  );
}

interface Col { key: string; label: string; type?: "text" | "number" | "list" | "bool"; /** The page always prints this cell: empty means "not yet typed", never "nothing there". */ required?: boolean }

/** An editable grid. A cell is a plain string or number; a dotted key
 *  ("values.105") reaches into a nested object. Empty means "the page
 *  prints nothing here" and is saved as null - never as a number. */
function Grid({ columns, rows, onRows, needed, blank, catalog = false }: { columns: Col[]; rows: Row[]; onRows: (rows: Row[]) => void; needed: (row: Row, key: string) => boolean; blank: Row; /** Typed from a catalog: no page to copy from. */ catalog?: boolean }) {
  const get = (r: Row, key: string): any => key.split(".").reduce<any>((o, k) => (o == null ? undefined : o[k]), r);
  const setDeep = (r: Row, key: string, v: unknown): Row => {
    const [head, ...rest] = key.split(".");
    if (!rest.length) return { ...r, [head]: v };
    return { ...r, [head]: setDeep(r[head] || {}, rest.join("."), v) };
  };
  const update = (i: number, key: string, raw: string, type: Col["type"]) => {
    let v: unknown = raw;
    if (type === "number") v = raw.trim() === "" ? null : Number(raw);
    if (type === "list") v = raw.split(",").map((x) => x.trim()).filter(Boolean);
    if (type === "bool") v = raw === "yes";
    if (type === "text" || !type) v = raw === "" && key.startsWith("sizes.") ? null : raw;
    onRows(rows.map((r, j) => (j === i ? setDeep(r, key, v) : r)));
  };
  const show = (v: unknown, type: Col["type"]) => (v == null ? "" : type === "list" && Array.isArray(v) ? v.join(", ") : String(v));
  return (
    <div className="ref-grid">
      <div className="table-scroll">
        <table className="small">
          <thead><tr>{columns.map((c) => <th key={c.key}>{c.label}</th>)}<th></th></tr></thead>
          <tbody>
            {rows.length === 0 && <tr><td colSpan={columns.length + 1} className="muted">{catalog ? "No rows yet. Add a row for each size you use and type it from the catalog." : "No rows yet. Copy the table from a page, or add rows and type them from the page."}</td></tr>}
            {rows.map((r, i) => (
              <tr key={i}>
                {columns.map((c) => {
                  const v = get(r, c.key);
                  // Highlighted: marked by the import, a required cell never typed, or a
                  // number the import could not read (it writes 0 and marks it).
                  const ask = needed(r, c.key) || (c.required && (v == null || v === "")) || (c.type === "number" && v === 0 && c.key !== "min_conductors");
                  if (c.type === "bool") return <td key={c.key}><label className="small"><input type="checkbox" checked={Boolean(v)} aria-label={c.label} onChange={(e) => update(i, c.key, e.target.checked ? "yes" : "no", c.type)} /> yes</label></td>;
                  return <td key={c.key}><input type={c.type === "number" ? "number" : "text"} step="any" value={show(v, c.type)} placeholder={ask ? (catalog ? "from the catalog" : "from the page") : ""} aria-label={c.label} className={ask ? "ref-needed" : undefined} onChange={(e) => update(i, c.key, e.target.value, c.type)} /></td>;
                })}
                <td><button className="btn sm" title="Remove this row" aria-label="Remove this row" onClick={() => onRows(rows.filter((_, j) => j !== i))}>×</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <button className="btn" style={{ marginTop: 6 }} onClick={() => onRows([...rows, JSON.parse(JSON.stringify(blank))])}>+ Add a row</button>
    </div>
  );
}

// -------------------------------------------------------------- the reminders

function CheatSheetEditor({ onChanged }: { onChanged: () => void }) {
  const [entries, setEntries] = useState<CheatSheetEntry[] | null>(null);
  const [doc, setDoc] = useState("ABYC E-11");
  const [edition, setEdition] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.referenceCheatSheet().then((s) => { setEntries(s.entries); if (s.source) { setDoc(s.source.document); setEdition(s.source.edition || ""); } }).catch((e) => setError(e?.message ?? String(e)));
  }, []);
  if (error && !entries) return <div className="alert crit" style={{ marginTop: 10 }}>{error}</div>;
  if (!entries) return <div style={{ marginTop: 10 }}><span className="spinner" /> Loading the reminders…</div>;

  const update = (i: number, patch: Partial<CheatSheetEntry>) => setEntries((es) => es!.map((e, j) => (j === i ? { ...e, ...patch } : e)));
  const save = async () => {
    setBusy(true); setError(null); setSaved(null);
    try {
      const s = await api.saveCheatSheet({ source: { document: doc, ...(edition ? { edition } : {}) }, entries });
      setEntries(s.entries);
      setSaved("Saved. The reminders that fit a calculation now ride along with its result.");
      onChanged();
    } catch (e: any) {
      setError(e?.message ?? String(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="card tight" style={{ marginTop: 12 }}>
      <h4 style={{ margin: 0 }}>Installation reminders</h4>
      <p className="small muted" style={{ marginTop: 4 }}>One line per rule, in your words, with the clause and page as printed in your copy. Tags say when a reminder rides along with a calculation: <span className="mono">always</span>, <span className="mono">engine_space</span>, <span className="mono">bundled</span>, <span className="mono">parallel</span>, a load such as <span className="mono">inverter</span>, or what the circuit feeds: <span className="mono">battery_main</span>, <span className="mono">charger</span>, <span className="mono">alternator</span>, <span className="mono">dc_dc</span>, <span className="mono">solar</span>, <span className="mono">windlass</span>, <span className="mono">starter</span>, <span className="mono">bilge_pump</span>, <span className="mono">lights</span>, <span className="mono">electronics</span>.</p>
      <div className="row" style={{ marginBottom: 8 }}>
        <Field label="Standard" value={doc} onChange={setDoc} />
        <Field label="Edition" value={edition} onChange={setEdition} />
      </div>
      {entries.length === 0 && <div className="empty">No reminders yet. Add one, or wait for the draft made from your export of the standard.</div>}
      <div className="table-scroll">
        <table className="small">
          <thead><tr><th>Topic</th><th>Rule</th><th>Clause</th><th>Page</th><th>Tags</th><th>Checked</th><th></th></tr></thead>
          <tbody>
            {entries.map((e, i) => (
              <tr key={i}>
                <td><input type="text" value={e.topic} aria-label="Topic" onChange={(ev) => update(i, { topic: ev.target.value })} /></td>
                <td><input type="text" value={e.rule} aria-label="Rule" style={{ minWidth: 260 }} onChange={(ev) => update(i, { rule: ev.target.value })} /></td>
                <td><input type="text" value={e.clause} aria-label="Clause" placeholder="as printed" className={e.clause ? undefined : "ref-needed"} onChange={(ev) => update(i, { clause: ev.target.value })} /></td>
                <td><input type="number" value={e.page || ""} aria-label="Page" placeholder="page" className={e.page ? undefined : "ref-needed"} onChange={(ev) => update(i, { page: Number(ev.target.value) })} /></td>
                <td><input type="text" value={e.applies_to.join(", ")} aria-label="Tags" onChange={(ev) => update(i, { applies_to: ev.target.value.split(",").map((x) => x.trim()).filter(Boolean) })} /></td>
                <td><label className="small" title="Tick when you have read this rule on the page"><input type="checkbox" checked={e.status === "confirmed"} onChange={(ev) => update(i, { status: ev.target.checked ? "confirmed" : "draft" })} /> checked</label></td>
                <td><button className="btn sm" title="Remove this reminder" aria-label="Remove this reminder" onClick={() => setEntries((es) => es!.filter((_, j) => j !== i))}>×</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {error && <div className="alert crit">{error}</div>}
      {saved && <div className="alert ok">{saved}</div>}
      <div className="row" style={{ marginTop: 8 }}>
        <button className="btn" onClick={() => setEntries((es) => [...es!, { topic: "", rule: "", clause: "", page: 0, applies_to: ["always"], status: "draft" }])}>+ Add a reminder</button>
        <button className="btn primary" disabled={busy} onClick={save}>Save the reminders</button>
      </div>
    </div>
  );
}
