/**
 * Reads the JSON tables and refuses anything that could pass a guess off as
 * the standard: a table without a page, a row without a page, a draft that
 * nobody has confirmed against the page, or the synthetic test fixture
 * outside a test.
 *
 * Takes parsed JSON, so it runs in a browser as well as in Node; the
 * directory reader lives in node.ts.
 */
import type { E11Table, E11Tables, TableId, TableStatus } from "./schema.js";
import { CATALOG_KINDS, TABLE_IDS } from "./schema.js";

export class TableError extends Error {
  constructor(public readonly file: string, message: string) {
    super(`${file}: ${message}`);
    this.name = "TableError";
  }
}

export interface LoadOptions {
  /** Only a test may load the synthetic fixture. */
  allowFixture?: boolean;
}

const STATUSES: TableStatus[] = ["draft", "confirmed", "fixture"];

function isRecord(x: unknown): x is Record<string, unknown> {
  return typeof x === "object" && x !== null && !Array.isArray(x);
}

function isPage(x: unknown): x is number {
  return typeof x === "number" && Number.isInteger(x) && x >= 1;
}

function need(file: string, ok: boolean, what: string): void {
  if (!ok) throw new TableError(file, what);
}

/** Check one table's shape. Cells may be null (not printed); pages may not. */
export function validateTable(file: string, raw: unknown): E11Table {
  need(file, isRecord(raw), "is not a JSON object");
  const t = raw as Record<string, unknown>;
  need(file, typeof t.id === "string" && t.id.length > 0, "has no id");
  need(file, typeof t.kind === "string", "has no kind");
  need(file, typeof t.title === "string", "has no title (the table's name as printed)");
  need(file, STATUSES.includes(t.status as TableStatus), `status must be one of ${STATUSES.join(", ")}`);
  need(file, isRecord(t.source) && typeof t.source.document === "string", "has no source.document");
  const source = t.source as Record<string, unknown>;
  if (!(CATALOG_KINDS as readonly string[]).includes(String(t.kind))) {
    need(file, isPage(source.page), "has no source.page - every table must say which page it was copied from");
  }
  const rows = t.rows;
  switch (t.kind) {
    case "constants": {
      const values = t.values;
      need(file, isRecord(values) && isRecord(values.K_copper), "constants needs values.K_copper");
      const k = (values as Record<string, Record<string, unknown>>).K_copper;
      need(file, typeof k.value === "number" && isPage(k.page), "K_copper needs a numeric value and its page");
      need(file, t.length_definition === "round_trip" || t.length_definition === "one_way", 'constants needs length_definition "round_trip" or "one_way", as the page words the formula');
      break;
    }
    case "circular_mils": {
      need(file, Array.isArray(rows) && rows.length > 0, "needs rows");
      for (const r of rows as unknown[]) {
        need(file, isRecord(r) && typeof r.size_awg === "string" && typeof r.circular_mils === "number" && isPage(r.page), "every circular_mils row needs size_awg, circular_mils and page");
      }
      break;
    }
    case "ampacity": {
      need(file, isRecord(t.columns) && Object.keys(t.columns).length > 0, "ampacity needs columns keyed by insulation rating");
      need(file, Array.isArray(rows) && rows.length > 0, "needs rows");
      for (const r of rows as unknown[]) {
        if (!isRecord(r) || typeof r.size_awg !== "string" || !isRecord(r.values) || !isPage(r.page)) throw new TableError(file, "every ampacity row needs size_awg, values and page");
        for (const [col, v] of Object.entries(r.values)) {
          need(file, v === null || typeof v === "number", `ampacity cell ${r.size_awg}/${col} must be a number or null`);
        }
      }
      break;
    }
    case "bundling": {
      need(file, Array.isArray(rows) && rows.length > 0, "needs rows");
      for (const r of rows as unknown[]) {
        need(file, isRecord(r) && typeof r.min_conductors === "number" && (r.max_conductors === null || typeof r.max_conductors === "number") && typeof r.factor === "number" && isPage(r.page), "every bundling row needs min_conductors, max_conductors (or null), factor and page");
      }
      break;
    }
    case "voltage_drop_grid": {
      need(file, typeof t.nominal_voltage === "number" && typeof t.drop_percent === "number", "voltage_drop_grid needs nominal_voltage and drop_percent");
      need(file, t.length_unit === "ft" || t.length_unit === "m", 'voltage_drop_grid needs length_unit "ft" or "m"');
      need(file, t.length_definition === "round_trip" || t.length_definition === "one_way", 'voltage_drop_grid needs length_definition "round_trip" or "one_way", as the page words the column heading');
      need(file, Array.isArray(t.lengths) && t.lengths.length > 0, "voltage_drop_grid needs lengths");
      need(file, Array.isArray(rows) && rows.length > 0, "needs rows");
      for (const r of rows as unknown[]) {
        need(file, isRecord(r) && typeof r.current === "number" && isRecord(r.sizes) && isPage(r.page), "every voltage_drop_grid row needs current, sizes and page");
      }
      break;
    }
    case "fuse_classes": {
      need(file, Array.isArray(rows), "needs rows");
      for (const r of rows as unknown[]) {
        if (!isRecord(r) || typeof r.class !== "string" || typeof r.interrupting_rating_a !== "number" || !Array.isArray(r.suits)) throw new TableError(file, "every fuse_classes row needs class, interrupting_rating_a and suits");
        if (!isRecord(r.source) || typeof r.source.document !== "string" || !isPage(r.source.page)) throw new TableError(file, `fuse class ${r.class} needs source.document and source.page (the datasheet it was read from)`);
      }
      break;
    }
    case "cable_dimensions": {
      need(file, t.diameter_unit === "mm" || t.diameter_unit === "in", 'cable_dimensions needs diameter_unit "mm" or "in"');
      need(file, Array.isArray(rows) && rows.length > 0, "needs rows");
      for (const r of rows as unknown[]) {
        need(file, isRecord(r) && typeof r.size_awg === "string" && typeof r.outside_diameter === "number" && r.outside_diameter > 0 && (r.page == null || isPage(r.page)), "every cable_dimensions row needs size_awg and an outside_diameter above zero");
      }
      break;
    }
    case "heat_shrink": {
      need(file, t.diameter_unit === "mm" || t.diameter_unit === "in", 'heat_shrink needs diameter_unit "mm" or "in"');
      need(file, Array.isArray(rows) && rows.length > 0, "needs rows");
      for (const r of rows as unknown[]) {
        need(file, isRecord(r) && typeof r.size === "string" && typeof r.supplied_id === "number" && typeof r.recovered_id === "number" && (r.page == null || isPage(r.page)), "every heat_shrink row needs size, supplied_id and recovered_id");
        const row = r as Record<string, number>;
        need(file, row.recovered_id > 0 && row.recovered_id < row.supplied_id, `heat shrink ${String((r as Record<string, unknown>).size)}: recovered_id must be above zero and below supplied_id (it shrinks)`);
      }
      break;
    }
    case "lugs": {
      need(file, t.diameter_unit == null || t.diameter_unit === "mm" || t.diameter_unit === "in", 'lugs diameter_unit must be "mm" or "in" when given');
      need(file, Array.isArray(rows) && rows.length > 0, "needs rows");
      for (const r of rows as unknown[]) {
        need(file, isRecord(r) && typeof r.size_awg === "string" && typeof r.stud === "string" && typeof r.part === "string" && (r.barrel_od == null || typeof r.barrel_od === "number") && (r.crimp_die == null || typeof r.crimp_die === "string") && (r.page == null || isPage(r.page)), "every lugs row needs size_awg, stud and part");
      }
      break;
    }
    default:
      throw new TableError(file, `unknown kind "${String(t.kind)}"`);
  }
  return t as unknown as E11Table;
}

/** Load a set of tables from parsed JSON, keyed by file name. */
export function loadTables(files: Record<string, unknown>, opts: LoadOptions = {}): E11Tables {
  const byId: Partial<Record<TableId, E11Table>> = {};
  let fixture = false;
  for (const [file, raw] of Object.entries(files)) {
    const t = validateTable(file, raw);
    if (t.status === "fixture") {
      if (!opts.allowFixture) throw new TableError(file, "is the synthetic test fixture, not a table from the standard; refused outside a test");
      fixture = true;
    }
    need(file, (TABLE_IDS as readonly string[]).includes(t.id), `unknown table id "${t.id}"; expected one of ${TABLE_IDS.join(", ")}`);
    byId[t.id as TableId] = t;
  }
  return { byId, fixture };
}

/** A table the engine may use: present and confirmed (a fixture counts in tests). A draft is loaded but unusable. */
export function usable<T extends E11Table>(tables: E11Tables, id: TableId): T | null {
  const t = tables.byId[id];
  if (!t || t.status === "draft") return null;
  return t as T;
}

export interface TableStatusRow {
  id: TableId;
  title: string | null;
  page: number | null;
  status: TableStatus | "missing";
  rows: number;
}

/** One line per expected table, for a status view. */
export function tablesStatus(tables: E11Tables): TableStatusRow[] {
  return TABLE_IDS.map((id) => {
    const t = tables.byId[id];
    if (!t) return { id, title: null, page: null, status: "missing", rows: 0 };
    const rows = "rows" in t && Array.isArray(t.rows) ? t.rows.length : 1;
    return { id, title: t.title, page: t.source.page ?? null, status: t.status, rows };
  });
}
