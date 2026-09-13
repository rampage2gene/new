/**
 * The words a person reads, from a circuit result: the groups, the row
 * labels, the sentence that says what decided the size, and the list of
 * bundle choices.
 *
 * This lives in the library, not in an application, so that the desktop app
 * and anything else built on this engine say the same thing. Its Python twin
 * is backend/app/reference/e11_present.py and the two are held equal by
 * tests/test-vectors.json. Nothing here decides anything: every number has
 * already been settled by sizeCircuit, and a value it left blank stays blank
 * here, with the reason it gave.
 */
import type { CircuitInputs, CircuitResult, E11Tables, OwnValues, Source, TableId } from "./schema.js";
import { CIRCUIT_TYPES, DEVICE_PROFILES } from "./profiles.js";
import { usable } from "./loader.js";

export type Classification = "documented_value" | "calculated_estimate" | "recommended_pending_verification";

export interface PresentedRow {
  key: string;
  label: string;
  value: string | number | null;
  unit: string | null;
  classification: Classification;
  note: string | null;
  group: string;
}

export interface PresentedAsk {
  /** The blank this answers, e.g. "conductor.ampacity.size_awg". */
  field: string;
  reason: string;
  /** The key under `own` that fills it, e.g. "ampacity_a"; null when nothing can. */
  own_field: string | null;
  unit: string | null;
  prompt: string;
  kind: string | null;
}

export interface PresentedSource {
  document_name: string;
  page: number;
}

export interface Presented {
  rows: PresentedRow[];
  asks: PresentedAsk[];
  warnings: string[];
  assumptions: string[];
  sources: PresentedSource[];
}

export interface PresentOptions {
  /** The unit the sizes are worded in. The working always quotes AWG, as the pages print it. */
  unit?: "awg" | "mm2";
  /** What the person typed, so a value of theirs is never reported as the table's. */
  own?: OwnValues;
}

export const GROUP_SIZE = "Cable size";
export const GROUP_HOW = "How it was decided";
export const GROUP_PROTECTION = "Protection";
export const GROUP_FITTINGS = "Fittings";
export const GROUP_BOM = "Bill of materials";

export const NO_TABLES =
  "The ABYC E-11 tables are not installed or not yet confirmed, so nothing was computed. " +
  "Open Calculators → ABYC E-11 reference, import each table from your copy of the standard, " +
  "check it against the page and press Confirm.";

/** Numbers as the person sees them: thousands grouped, trailing zeros dropped. */
export function fmt(v: number | null | undefined, digits = 2): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  if (Math.abs(v) >= 100) {
    const exact = Math.abs(v - Math.round(v)) < 1e-9;
    return groupThousands(v.toFixed(exact ? 0 : 1));
  }
  return v.toFixed(digits).replace(/0+$/, "").replace(/\.$/, "");
}

/** Python's `a or b`: the first value that is not empty, else the last one. */
function pick<T>(...vals: T[]): T {
  for (const v of vals.slice(0, -1)) if (v) return v;
  return vals[vals.length - 1];
}

function groupThousands(text: string): string {
  const neg = text.startsWith("-");
  const [whole, frac] = (neg ? text.slice(1) : text).split(".");
  const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  return (neg ? "-" : "") + grouped + (frac ? `.${frac}` : "");
}

/** Where a value came from, in a sentence: a page of the standard, one of the owner's catalogs, or the person. */
export function citeSource(src: Source | undefined | null): string {
  if (!src) return "";
  if ("by" in src) return "entered by you";
  if ("document" in src) return `From ${src.document}` + (src.page ? `, page ${src.page}` : "");
  return `ABYC E-11, ${src.title ?? src.table}, page ${src.page}`;
}

/**
 * What decided the cable size, in plain words. The standard's rule is that
 * the larger of the requirements wins; this says which one it was, and what
 * the other one would have allowed.
 */
export function sizeNote(result: CircuitResult, inputs: CircuitInputs): string {
  const c = result.conductor;
  const { voltage_drop: vd, printed_table: pt, ampacity: am } = c;
  const n = c.parallel;
  const size = c.size_awg;
  const current = fmt(inputs.current);
  const src = vd.source;
  const page = src && !("by" in src) && src.page ? ` (page ${src.page})` : "";
  if (n > 1) {
    const total = result.protection.conductor_ampacity_a;
    const carries = total !== null && total !== undefined ? ` carry ${fmt(total)} A after derating` : "";
    const need = c.governed_by === "voltage_drop" ? "the area the drop limit needs" : "the current";
    return `No single listed size meets ${need}: ${n} × ${size} AWG in parallel${carries}.`;
  }
  if (c.governed_by === "printed_table") {
    return `The printed ${fmt(inputs.max_drop_percent)} % table at ${fmt(inputs.system_voltage)} V asks for this size, ` +
      `more than the formula's ${vd.size_awg} AWG; the larger is used.`;
  }
  if (c.governed_by === "voltage_drop") {
    const also = am.size_awg ? `; it also carries ${current} A (${am.size_awg} AWG would)` : "";
    if (pt.reason && pt.reason.includes("stops at")) {
      return `${pt.reason.split(", so")[0]}, so the circular-mils formula and the circular-mils table${page} set this size${also}.`;
    }
    return `Set by the voltage-drop limit: ${fmt(vd.cm_required)} circular mils needed, ` +
      `and this is the smallest listed size with at least that${page}${also}.`;
  }
  if (c.governed_by === "ampacity") {
    const allow = vd.size_awg ? `; the drop limit alone would allow ${vd.size_awg} AWG` : "";
    return `Set by the current: ${current} A needs this size after derating${allow}.`;
  }
  return "The larger of the requirements is used.";
}

export interface BundleOption {
  value: string;
  label: string;
}

/**
 * The bundle choices: not bundled, then one row per row of the confirmed
 * bundling table, showing its factor and page, with the row's lowest count as
 * the value. Without that table there is nothing to list, so the count is
 * typed instead - and no factor is assumed for it.
 */
export function bundleOptions(tables: E11Tables): BundleOption[] {
  const options: BundleOption[] = [{ value: "2", label: "Not bundled (this circuit's two conductors)" }];
  const table = usable<any>(tables, "bundling_factors");
  if (!table) {
    options.push({ value: "count", label: "Bundled: type the count below" });
    return options;
  }
  // The synthetic test tables carry made-up numbers; the pick list says so
  // where the choice is made, not only on the reference screen.
  const mark = table.status === "fixture" ? ", test data" : "";
  const seen = new Set(["2"]);
  const rows = [...table.rows].sort((a: any, b: any) => a.min_conductors - b.min_conductors);
  for (const row of rows) {
    const hi = row.max_conductors ?? null;
    if (hi !== null && hi <= 2) continue; // the "not bundled" row, already offered
    const value = String(Math.max(Math.trunc(row.min_conductors), 3));
    if (seen.has(value)) continue;
    seen.add(value);
    const span = hi !== null ? `${row.min_conductors} to ${hi}` : `${row.min_conductors} or more`;
    options.push({ value, label: `${span} conductors bundled (× ${fmt(row.factor)}, page ${row.page}${mark})` });
  }
  return options;
}

/** The one row shown when no table has been confirmed yet: an ask, not an answer. */
export function presentNoTables(): Presented {
  return {
    rows: [{ key: "size_awg", label: "Cable size to use", value: null, unit: null, classification: "recommended_pending_verification", note: NO_TABLES, group: GROUP_SIZE }],
    asks: [{ field: "reference", reason: NO_TABLES, own_field: null, unit: null, prompt: NO_TABLES, kind: null }],
    warnings: [NO_TABLES],
    assumptions: [],
    sources: [],
  };
}

export const ASSUMPTIONS = [
  "A conductor must satisfy two requirements and the larger size wins: carry the current without overheating (the ampacity table, derated for engine space and bundling) and deliver the voltage (the drop limit). When no single listed size does both, conductors are paralleled.",
  "The fuse protects the conductor: never above its derated ampacity, at least the load times its load-type factor, rounded up to a standard size.",
  "Every table value comes from your confirmed copy of ABYC E-11 and cites its page; mm² and the standard size lists are conversions and industry lists; load behaviour is industry guidance.",
];
export const FIXTURE_ASSUMPTION = "These figures come from the synthetic test tables, not from the standard.";

/** The whole result as rows a person reads, in the order they read them. */
export function presentCircuit(inputs: CircuitInputs, result: CircuitResult, opts: PresentOptions = {}): Presented {
  const inMm2 = opts.unit === "mm2";
  const own = opts.own ?? {};
  const c = result.conductor;
  const p = result.protection;
  const ft = result.fittings;
  const rows: PresentedRow[] = [];

  // 1. The answer.
  const n = c.parallel;
  const awgText = c.size_awg ? (n > 1 ? `${n} × ${c.size_awg} AWG in parallel` : `${c.size_awg} AWG`) : null;
  const metric = c.metric_standard_mm2 ?? c.size_mm2;
  let metricText: string | null = null;
  if (c.size_awg && metric !== null && metric !== undefined) {
    metricText = n > 1
      ? `${n} × ${fmt(metric)} mm² in parallel (${n} × ${c.size_awg} AWG)`
      : `${fmt(metric)} mm² (${c.size_awg} AWG)`;
  }
  const sizeText = inMm2 ? (metricText ?? awgText) : awgText;
  const note = sizeText
    ? sizeNote(result, inputs)
    : (result.blanks.find((b) => b.field.startsWith("conductor."))?.reason ?? "No conductor size was settled.");
  rows.push({
    key: "size_awg", label: "Cable size to use", value: sizeText, unit: null,
    classification: sizeText ? "documented_value" : "recommended_pending_verification", note, group: GROUP_SIZE,
  });
  if (c.size_mm2 !== null && c.size_mm2 !== undefined) {
    const each = n > 1 ? " each" : "";
    const std = c.metric_standard_mm2
      ? `${fmt(c.metric_standard_mm2)} mm² is the smallest standard metric size (IEC 60228) at least as large.`
      : "Larger than the largest standard metric size (IEC 60228), 300 mm².";
    rows.push({
      key: "size_mm2", label: inMm2 ? "Exact area of that AWG size" : "Same area in mm²", value: c.size_mm2, unit: "mm²",
      classification: "calculated_estimate",
      note: `${c.size_awg} AWG is ${fmt(c.size_mm2)} mm²${each}. ${std} A conversion; the standard's sizes are AWG.`,
      group: GROUP_SIZE,
    });
  }

  // 2. The working, always quoting the pages in AWG as they print it.
  const vd = c.voltage_drop, pt = c.printed_table, am = c.ampacity;
  rows.push({ key: "cm_required", label: "Circular mils needed for the drop limit", value: vd.cm_required, unit: "CM", classification: "documented_value", note: pick(vd.reason ?? null, citeSource(vd.source)), group: GROUP_HOW });
  rows.push({ key: "printed_table_size", label: "Size from the printed table", value: pt.size_awg ? `${pt.size_awg} AWG` : null, unit: null, classification: "documented_value", note: pick(pt.reason ?? null, citeSource(pt.source)), group: GROUP_HOW });
  rows.push({ key: "voltage_drop_size", label: "Size for the voltage drop, from the formula", value: vd.size_awg ? `${vd.size_awg} AWG` : null, unit: null, classification: "documented_value", note: pick(vd.reason ?? null, citeSource(vd.source)), group: GROUP_HOW });
  // A factor typed from the page always wins over the table, so saying so
  // here is simply whether they gave one.
  const byYou = own.bundling_factor !== undefined && own.bundling_factor !== null ? " (factor entered by you)" : "";
  const ampNote = pick(am.reason ?? null, `${fmt(am.ampacity_a)} A × bundling factor ${fmt(am.bundling_factor)}${byYou} (${citeSource(am.source)})`);
  rows.push({ key: "ampacity_size", label: "Size for the current, derated", value: am.size_awg ? `${am.size_awg} AWG` : null, unit: null, classification: "documented_value", note: ampNote, group: GROUP_HOW });
  const d = c.drop_at_size;
  rows.push({
    key: "drop_at_size", label: "Drop at the chosen size", value: d.volts, unit: "V", classification: "calculated_estimate",
    note: pick(d.reason ?? null, d.percent !== null && d.percent !== undefined ? `${fmt(d.percent)} % of ${fmt(inputs.system_voltage)} V` : null), group: GROUP_HOW,
  });

  // 3. Protection.
  const fuseNote = pick(p.reason ?? null, p.fuse_a !== null && p.fuse_a !== undefined ? `At least ${fmt(p.min_a)} A for the load, within the conductor's ${fmt(p.conductor_ampacity_a)} A` : null);
  rows.push({ key: "fuse_a", label: "Fuse or breaker", value: p.fuse_a, unit: "A", classification: "recommended_pending_verification", note: fuseNote, group: GROUP_PROTECTION });
  if (p.characteristic) {
    rows.push({ key: "fuse_characteristic", label: "Characteristic", value: p.characteristic, unit: null, classification: "recommended_pending_verification", note: p.guidance, group: GROUP_PROTECTION });
  }
  const ic = p.interrupting;
  const classes = ic.classes.map((x) => `${x.class} (${fmt(x.interrupting_rating_a)} A${x.suits_load ? ", suits this load" : ""})`).join(", ") || null;
  rows.push({
    key: "interrupting", label: "Fuse classes with enough interrupting capacity", value: classes, unit: null,
    classification: "recommended_pending_verification",
    note: pick(ic.reason ?? null, classes ? `The source can deliver ${fmt(ic.required_a)} A; ratings from the makers' datasheets` : null), group: GROUP_PROTECTION,
  });
  const ctype = CIRCUIT_TYPES[inputs.circuit_type ?? "general_dc"] ?? CIRCUIT_TYPES["general_dc"];
  const profile = DEVICE_PROFILES[ctype.load_type];
  rows.push({
    key: "load_type", label: "Load type", value: profile.label, unit: null, classification: "recommended_pending_verification",
    note: `Industry guidance, from the circuit type "${ctype.label}": ${profile.surge_note}`, group: GROUP_PROTECTION,
  });

  // 4. Fittings: from the owner's catalog tables, or the person; never typical.
  const od = ft.cable_od, hs = ft.heat_shrink, lug = ft.lug;
  rows.push({ key: "cable_od", label: "Cable outside diameter", value: od.value, unit: od.unit, classification: "documented_value", note: pick(od.reason ?? null, citeSource(od.source)), group: GROUP_FITTINGS });
  let hsText: string | null = null;
  if (hs.size) {
    hsText = hs.size + (hs.supplied_id !== null && hs.supplied_id !== undefined
      ? ` (${fmt(hs.supplied_id)} → ${fmt(hs.recovered_id)} ${hs.unit}${hs.adhesive ? ", adhesive-lined" : ""})`
      : "");
  }
  rows.push({ key: "heat_shrink", label: "Heat-shrink tubing", value: hsText, unit: null, classification: "documented_value", note: pick(hs.reason ?? null, citeSource(hs.source)), group: GROUP_FITTINGS });
  rows.push({ key: "lug", label: "Lug or terminal", value: lug.part ? `${lug.part} for a ${lug.stud} stud` : null, unit: null, classification: "documented_value", note: pick(lug.reason ?? null, citeSource(lug.source)), group: GROUP_FITTINGS });
  rows.push({ key: "crimp_die", label: "Crimp die or setting", value: lug.crimp_die, unit: null, classification: "documented_value", note: pick(lug.die_reason ?? null, citeSource(lug.die_source), !lug.part ? "No lug, so no die." : null), group: GROUP_FITTINGS });

  // 5. What to buy: counts for the set, from the parallel count and the loop length.
  const q = ft.quantities;
  if (q && c.size_awg) {
    const sizeEach = inMm2 && metric !== null && metric !== undefined ? `${fmt(metric)} mm² (${c.size_awg} AWG)` : `${c.size_awg} AWG`;
    rows.push({
      key: "bom_cable", label: "Cable to buy", value: `${q.cables} × ${sizeEach}, ${fmt(q.cable_length)} ${q.length_unit}`, unit: null, classification: "calculated_estimate",
      note: `${fmt(inputs.length)} ${q.length_unit} there and back per cable, plus your own routing allowance; none is added here.`, group: GROUP_BOM,
    });
    rows.push({ key: "bom_lugs", label: "Lugs", value: lug.part ? `${q.lugs} × ${lug.part}` : `${q.lugs} lugs needed; part not chosen yet`, unit: null, classification: "calculated_estimate", note: "Two per cable.", group: GROUP_BOM });
    rows.push({ key: "bom_heat_shrink", label: "Heat shrink", value: hs.size ? `${q.heat_shrink_pieces} pieces of ${hs.size}` : `${q.heat_shrink_pieces} pieces needed; size not chosen yet`, unit: null, classification: "calculated_estimate", note: "Two per cable, one over each lug barrel.", group: GROUP_BOM });
    rows.push({
      key: "bom_fuse", label: "Fuse or breaker", value: p.fuse_a !== null && p.fuse_a !== undefined ? `1 × ${fmt(p.fuse_a)} A, ${p.characteristic}` : "1, rating not yet settled", unit: null,
      classification: "recommended_pending_verification", note: p.fuse_a !== null && p.fuse_a !== undefined ? p.guidance : (p.reason ?? null), group: GROUP_BOM,
    });
  }

  // The blanks, as things a person can answer.
  const asks: PresentedAsk[] = result.blanks.map((b) => ({
    field: b.field,
    reason: b.reason,
    own_field: b.ask ? b.ask.field.replace(/^own\./, "") : null,
    unit: b.ask?.unit ?? null,
    prompt: b.ask?.prompt ?? b.reason,
    kind: b.ask ? (b.ask.kind ?? "number") : null,
  }));

  const warnings = result.blanks.filter((b) => !b.ask).map((b) => b.reason);
  if (p.fits_conductor === false && p.reason) warnings.push(p.reason);
  // A typed fitting skips the fit checks a catalog row gets; say so.
  if (hs.source && "by" in hs.source) warnings.push(`The heat-shrink size you typed (${hs.size}) was not checked against the cable and lug diameters; a row in your heat-shrink table would be.`);
  if (lug.source && "by" in lug.source) warnings.push(`The lug part you typed (${lug.part}) was not checked against the stud size; a row in your lugs table would be.`);

  const sources: PresentedSource[] = [];
  const seen = new Set<string>();
  for (const src of [vd.source, pt.source, am.source]) {
    if (!src || "by" in src || !src.page) continue;
    const key = `${src.table}|${src.page}`;
    if (seen.has(key)) continue;
    seen.add(key);
    sources.push({ document_name: `ABYC E-11 (${src.title ?? src.table})`, page: src.page });
  }

  return {
    rows, asks, warnings, sources,
    assumptions: result.fixture ? [...ASSUMPTIONS, FIXTURE_ASSUMPTION] : [...ASSUMPTIONS],
  };
}

// --------------------------------------------------------------------------- the conditions, offered from the tables

const AMPACITY_IDS = ["ampacity_outside_engine_space", "ampacity_inside_engine_space"] as const;
const DROP_GRIDS: [string, TableId, string][] = [
  ["3", "voltage_drop_3pct", "3 % (critical circuits)"],
  ["10", "voltage_drop_10pct", "10 % (non-critical)"],
];

/** " (page 4)" or " (page 4, test data)": where a choice comes from. */
function fromPage(page: number | null | undefined, fixture: boolean): string {
  const mark = fixture ? ", test data" : "";
  if (page) return ` (page ${page}${mark})`;
  return fixture ? " (test data)" : "";
}

/**
 * The insulation ratings to offer: the temperature columns the confirmed
 * ampacity tables actually print, and no others. An empty list means no
 * ampacity table is confirmed yet, so the rating is typed instead of picked -
 * inventing a column here would be inventing a page.
 */
export function ratingOptions(tables: E11Tables): BundleOption[] {
  const seen = new Map<number, string>();
  for (const id of AMPACITY_IDS) {
    const t = usable<any>(tables, id);
    if (!t) continue;
    const cols = Object.keys(t.columns ?? {});
    const keys = cols.length ? cols : [...new Set(t.rows.flatMap((r: any) => Object.keys(r.values ?? {})))];
    for (const k of keys) {
      const n = Number(k);
      if (!Number.isFinite(n) || seen.has(n)) continue;
      seen.set(n, fromPage(t.source?.page, t.status === "fixture"));
    }
  }
  return [...seen.entries()].sort((a, b) => a[0] - b[0]).map(([n, where]) => ({ value: String(n), label: `${n} °C${where}` }));
}

/**
 * The drop limits. The formula honours any limit, so all three are always
 * offered; what the table adds is which of them has a printed grid behind it,
 * and at what voltage, so the choice is made knowing that.
 */
export function dropLimitOptions(tables: E11Tables): BundleOption[] {
  const options: BundleOption[] = DROP_GRIDS.map(([pct, id, base]) => {
    const t = usable<any>(tables, id);
    const printed = t ? ` — printed table at ${fmt(t.nominal_voltage)} V${fromPage(t.source?.page, t.status === "fixture")}` : "";
    return { value: pct, label: base + printed };
  });
  options.push({ value: "other", label: "other" });
  return options;
}

/** Inside or outside an engine space, saying when the table that answer needs is not confirmed. */
export function engineSpaceOptions(tables: E11Tables): BundleOption[] {
  const tail = (id: TableId) => (usable(tables, id) ? "" : " — that table is not confirmed yet");
  return [
    { value: "no", label: `No${tail("ampacity_outside_engine_space")}` },
    { value: "yes", label: `Yes${tail("ampacity_inside_engine_space")}` },
  ];
}

/** Every condition whose choices come from the tables, keyed by the input it fills. */
export function conditionOptions(tables: E11Tables): Record<string, BundleOption[]> {
  return {
    bundle: bundleOptions(tables),
    insulation_rating_c: ratingOptions(tables),
    max_drop_percent: dropLimitOptions(tables),
    engine_space: engineSpaceOptions(tables),
  };
}
