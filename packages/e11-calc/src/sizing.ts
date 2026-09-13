/**
 * Conductor sizing from the tables, one requirement at a time.
 *
 * A conductor must satisfy two independent requirements and the larger size
 * wins: carry the current without overheating (the ampacity table, derated
 * for engine space and bundling) and deliver the voltage (the drop limit,
 * from the printed grid where it applies or the circular-mil formula for any
 * voltage). Each function answers with a size and its page, or a blank that
 * says what the table does not cover and what a person can supply instead.
 */
import type { AmpacityTable, Ask, Blank, BundlingTable, CircularMilsTable, ConstantsTable, E11Tables, Source, VoltageDropGrid } from "./schema.js";
import { usable } from "./loader.js";

export const FT_PER_M = 1 / 0.3048;
/** One circular mil in square millimetres: (0.0254 mm)² × π / 4. A unit conversion, not a table value. */
export const MM2_PER_CIRCULAR_MIL = 0.0005067;
/** Standard metric conductor sizes (IEC 60228), for the "nearest metric size" column. An industry standard, not E-11 data. */
export const METRIC_STANDARD_MM2 = [0.5, 0.75, 1, 1.5, 2.5, 4, 6, 10, 16, 25, 35, 50, 70, 95, 120, 150, 185, 240, 300];

export function lengthFt(length: number, unit: "m" | "ft"): number {
  return unit === "m" ? length * FT_PER_M : length;
}

export function toMm2(circularMils: number): number {
  return round(circularMils * MM2_PER_CIRCULAR_MIL, 2);
}

/** The smallest standard metric size at least as large, or null past the list. */
export function nearestMetric(mm2: number): number | null {
  for (const s of METRIC_STANDARD_MM2) if (s >= mm2 - 1e-9) return s;
  return null;
}

/** Half up, spelled out so the Python copy rounds the same way (Python's round() is half-even). */
export function round(v: number, digits = 1): number {
  const f = 10 ** digits;
  return Math.floor(v * f + 0.5) / f;
}

export function isBlank<T>(x: T | Blank): x is Blank {
  return (x as Blank).value === null && typeof (x as Blank).reason === "string";
}

const src = (t: { id: string; title: string }, page: number): Source => ({ table: t.id, title: t.title, page });

export interface CmRequired {
  value: number;
  k: number;
  round_trip: boolean;
  source: Source;
}

/** CM = K × I × L / E, with L as the page defines it (round trip or one way). */
export function requiredCircularMils(voltage: number, current: number, lengthFt: number, dropPercent: number, tables: E11Tables, ownK?: number | null): CmRequired | Blank {
  const constants = usable<ConstantsTable>(tables, "constants");
  const ask: Ask = { field: "own.k", unit: null, prompt: "The constants table (K and the formula) is not confirmed under Reference. Type K for copper from the page." };
  let k: number;
  let roundTrip = true;
  let source: Source;
  if (ownK != null) {
    k = ownK;
    roundTrip = constants ? constants.length_definition === "round_trip" : true;
    source = { by: "you" };
  } else if (constants) {
    k = constants.values.K_copper.value;
    roundTrip = constants.length_definition === "round_trip";
    source = src(constants, constants.values.K_copper.page);
  } else {
    return { value: null, reason: "The constants table (K and the formula) is not confirmed, so the required circular mils cannot be computed.", ask };
  }
  if (voltage <= 0 || current <= 0 || lengthFt <= 0 || dropPercent <= 0) {
    return { value: null, reason: "Voltage, current, length and the drop limit must all be above zero." };
  }
  const eDrop = voltage * dropPercent / 100;
  const l = roundTrip ? 2 * lengthFt : lengthFt;
  return { value: round(k * current * l / eDrop, 1), k, round_trip: roundTrip, source };
}

export interface CmPick {
  size_awg: string;
  circular_mils: number;
  source: Source;
}

/** The smallest listed size whose area is at least the required circular mils. */
export function sizeForCircularMils(cm: number, tables: E11Tables): CmPick | Blank {
  const table = usable<CircularMilsTable>(tables, "circular_mils");
  if (!table) return { value: null, reason: "The circular-mils table is not confirmed under Reference, so no size can be read for the required area." };
  const rows = [...table.rows].sort((a, b) => a.circular_mils - b.circular_mils);
  for (const r of rows) if (r.circular_mils >= cm - 1e-9) return { size_awg: r.size_awg, circular_mils: r.circular_mils, source: src(table, r.page) };
  const largest = rows[rows.length - 1];
  return { value: null, reason: `${cm} circular mils is more than the largest listed size, ${largest.size_awg} AWG at ${largest.circular_mils} circular mils (page ${largest.page}); conductors in parallel are needed.` };
}

export interface GridPick {
  size_awg: string;
  source: Source;
  printed_current: number;
  printed_length: number;
}

export interface GridNotApplicable {
  size_awg: null;
  reason: string;
  applicable: false;
}

/** The printed voltage-drop grid, only at its own nominal voltage. */
export function sizeFromPrintedGrid(voltage: number, current: number, lengthFt: number, dropPercent: number, tables: E11Tables): GridPick | Blank | GridNotApplicable {
  const id = dropPercent === 3 ? "voltage_drop_3pct" : dropPercent === 10 ? "voltage_drop_10pct" : null;
  if (!id) return { size_awg: null, applicable: false, reason: `No printed table for a ${dropPercent} % limit, so the circular-mils formula and table are used instead.` };
  const grid = usable<VoltageDropGrid>(tables, id);
  if (!grid) return { size_awg: null, applicable: false, reason: `The printed ${dropPercent} % table is not confirmed under Reference, so the circular-mils formula and table are used instead.` };
  if (Math.abs(grid.nominal_voltage - voltage) > 1e-9) return { size_awg: null, applicable: false, reason: `No printed table for ${voltage} V (the ${dropPercent} % table is for ${grid.nominal_voltage} V), so the circular-mils formula and table are used instead.` };
  let l = grid.length_unit === "m" ? lengthFt / FT_PER_M : lengthFt;
  if (grid.length_definition === "round_trip") l *= 2;
  const rows = [...grid.rows].sort((a, b) => a.current - b.current);
  const row = rows.find((r) => r.current >= current - 1e-9);
  if (!row) return { value: null, reason: `The printed ${dropPercent} % table on page ${grid.source.page} stops at ${rows[rows.length - 1].current} A, so the circular-mils formula and table are used instead.` };
  const lengths = [...grid.lengths].sort((a, b) => a - b);
  const len = lengths.find((x) => x >= l - 1e-9);
  if (len == null) return { value: null, reason: `The printed ${dropPercent} % table on page ${row.page} stops at ${lengths[lengths.length - 1]} ${grid.length_unit}, so the circular-mils formula and table are used instead.` };
  const size = row.sizes[String(len)];
  if (!size) return { value: null, reason: `The printed ${dropPercent} % table on page ${row.page} has no size for ${row.current} A at ${len} ${grid.length_unit}, so the circular-mils formula and table are used instead.` };
  return { size_awg: size, source: src(grid, row.page), printed_current: row.current, printed_length: len };
}

export interface FactorPick {
  factor: number;
  source: Source;
}

/** The bundling correction factor for this many current-carrying conductors. */
export function bundlingFactor(count: number, tables: E11Tables, own?: number | null): FactorPick | Blank {
  const ask: Ask = { field: "own.bundling_factor", unit: null, prompt: `Type the correction factor for ${count} bundled conductors from the page (1 if the page applies none).` };
  if (own != null) return { factor: own, source: { by: "you" } };
  const table = usable<BundlingTable>(tables, "bundling_factors");
  if (!table) return { value: null, reason: "The bundling table is not confirmed under Reference.", ask };
  for (const r of table.rows) {
    if (count >= r.min_conductors && (r.max_conductors === null || count <= r.max_conductors)) return { factor: r.factor, source: src(table, r.page) };
  }
  return { value: null, reason: `The bundling table on page ${table.source.page} has no row for ${count} conductors.`, ask };
}

export interface AmpacityPick {
  size_awg: string;
  ampacity_a: number;
  derated_a: number;
  bundling_factor: number;
  source: Source;
  factor_source: Source;
}

export interface AmpacityExceeded {
  size_awg: null;
  reason: string;
  exceeded: true;
  bundling_factor: number;
  largest: { size_awg: string; ampacity_a: number; derated_a: number };
  source: Source;
  factor_source: Source;
}

function ampacityTable(engineSpace: boolean, tables: E11Tables): AmpacityTable | null {
  return usable<AmpacityTable>(tables, engineSpace ? "ampacity_inside_engine_space" : "ampacity_outside_engine_space");
}

function ampacityAsk(ratingC: number, engineSpace: boolean): Ask {
  return { field: "own.ampacity_a", unit: "A", prompt: `Type the allowable current for that size at ${ratingC} °C ${engineSpace ? "inside" : "outside"} an engine space, from the page.` };
}

/** Rows in order of area, so "smallest size that carries the current" means what it says. */
function byArea(rows: { size_awg: string }[], tables: E11Tables): { size_awg: string }[] | null {
  const cmTable = usable<CircularMilsTable>(tables, "circular_mils");
  if (!cmTable) return null;
  const area = new Map(cmTable.rows.map((r) => [r.size_awg, r.circular_mils]));
  if (rows.some((r) => !area.has(r.size_awg))) return null;
  return [...rows].sort((a, b) => area.get(a.size_awg)! - area.get(b.size_awg)!);
}

/** The smallest size whose derated ampacity carries the current. */
export function sizeForAmpacity(current: number, ratingC: number, engineSpace: boolean, bundled: number, tables: E11Tables, own?: { bundling_factor?: number | null }): AmpacityPick | AmpacityExceeded | Blank {
  const factor = bundlingFactor(bundled, tables, own?.bundling_factor);
  if (isBlank(factor)) return factor;
  const table = ampacityTable(engineSpace, tables);
  const ask = ampacityAsk(ratingC, engineSpace);
  if (!table) return { value: null, reason: `The ampacity table for ${engineSpace ? "inside" : "outside"} engine spaces is not confirmed under Reference.`, ask };
  const col = String(ratingC);
  if (!(col in table.columns)) return { value: null, reason: `The ampacity table on page ${table.source.page} has no ${ratingC} °C column (it has ${Object.keys(table.columns).join(", ")} °C).`, ask };
  const rows = byArea(table.rows, tables) as AmpacityTable["rows"] | null;
  if (!rows) return { value: null, reason: "The circular-mils table is needed to order sizes by area and is not confirmed under Reference." };
  let largest: AmpacityPick | null = null;
  for (const r of rows) {
    const a = r.values[col];
    if (a == null) continue;
    const pick: AmpacityPick = { size_awg: r.size_awg, ampacity_a: a, derated_a: round(a * factor.factor, 1), bundling_factor: factor.factor, source: src(table, r.page), factor_source: factor.source };
    if (pick.derated_a >= current - 1e-9) return pick;
    largest = pick;
  }
  if (!largest) return { value: null, reason: `The ${ratingC} °C column on page ${table.source.page} has no values.`, ask };
  return {
    size_awg: null, exceeded: true, bundling_factor: factor.factor, source: largest.source, factor_source: factor.source,
    largest: { size_awg: largest.size_awg, ampacity_a: largest.ampacity_a, derated_a: largest.derated_a },
    reason: `The largest listed size, ${largest.size_awg} AWG, carries ${largest.derated_a} A after derating (page ${largest.source && "page" in largest.source ? largest.source.page : "?"}), less than ${current} A; conductors in parallel are needed.`,
  };
}

/** The allowable current of one named size, for checking a size chosen by another step. */
export function ampacityOf(sizeAwg: string, ratingC: number, engineSpace: boolean, tables: E11Tables): { ampacity_a: number; source: Source } | Blank {
  const table = ampacityTable(engineSpace, tables);
  const ask = ampacityAsk(ratingC, engineSpace);
  if (!table) return { value: null, reason: `The ampacity table for ${engineSpace ? "inside" : "outside"} engine spaces is not confirmed under Reference.`, ask };
  const col = String(ratingC);
  if (!(col in table.columns)) return { value: null, reason: `The ampacity table on page ${table.source.page} has no ${ratingC} °C column.`, ask };
  const row = table.rows.find((r) => r.size_awg === sizeAwg);
  const a = row?.values[col];
  if (row == null || a == null) return { value: null, reason: `The ampacity table on page ${table.source.page} has no ${ratingC} °C value for ${sizeAwg} AWG.`, ask };
  return { ampacity_a: a, source: src(table, row.page) };
}

export interface ParallelPick {
  count: number;
  size_awg: string;
  circular_mils_each: number;
  ampacity_each_a: number | null;
  derated_total_a: number | null;
  source: Source;
}

/** The fewest conductors, then the smallest listed size, that together meet the area and the current. */
export function parallelConductors(requiredCm: number | null, requiredA: number, factor: number, ratingC: number, engineSpace: boolean, tables: E11Tables, maxCount = 4): ParallelPick | Blank {
  const cmTable = usable<CircularMilsTable>(tables, "circular_mils");
  if (!cmTable) return { value: null, reason: "The circular-mils table is not confirmed under Reference." };
  const amp = ampacityTable(engineSpace, tables);
  const col = String(ratingC);
  const rows = [...cmTable.rows].sort((a, b) => a.circular_mils - b.circular_mils);
  for (let n = 2; n <= maxCount; n++) {
    for (const r of rows) {
      const cmOk = requiredCm == null || n * r.circular_mils >= requiredCm - 1e-9;
      const a = amp?.rows.find((x) => x.size_awg === r.size_awg)?.values[col] ?? null;
      const derated = a == null ? null : round(n * a * factor, 1);
      const ampOk = derated != null && derated >= requiredA - 1e-9;
      if (cmOk && ampOk) return { count: n, size_awg: r.size_awg, circular_mils_each: r.circular_mils, ampacity_each_a: a, derated_total_a: derated, source: src(cmTable, r.page) };
    }
  }
  return { value: null, reason: `Even ${maxCount} conductors of the largest listed size in parallel do not meet ${requiredA} A${requiredCm != null ? ` and ${requiredCm} circular mils` : ""}.` };
}

/** Compare two listed sizes by area: negative when a is smaller. */
export function compareSizes(a: string, b: string, tables: E11Tables): number | null {
  const cmTable = usable<CircularMilsTable>(tables, "circular_mils");
  if (!cmTable) return null;
  const area = (s: string) => cmTable.rows.find((r) => r.size_awg === s)?.circular_mils;
  const x = area(a), y = area(b);
  if (x == null || y == null) return null;
  return x - y;
}

/** Circular mils of a listed size, for the drop at the chosen size. */
export function circularMilsOf(sizeAwg: string, tables: E11Tables): { circular_mils: number; mm2: number | null; source: Source } | null {
  const cmTable = usable<CircularMilsTable>(tables, "circular_mils");
  const row = cmTable?.rows.find((r) => r.size_awg === sizeAwg);
  if (!cmTable || !row) return null;
  return { circular_mils: row.circular_mils, mm2: row.mm2 ?? null, source: src(cmTable, row.page) };
}
