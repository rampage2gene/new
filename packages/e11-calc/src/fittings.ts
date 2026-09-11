/**
 * The fittings for the conductor the sizing step chose: the cable's outside
 * diameter, the heat-shrink tubing that fits it, the lug for the stud it
 * lands on with its crimp die, and the counts for the set.
 *
 * None of this is E-11: cable diameters, tubing sizes and lug parts differ by
 * maker, so they come from three catalog tables the owner types, or from the
 * person when a table does not cover the case. Nothing typical is carried
 * here: tubing that does not shrink or a lug that does not crimp is a fault
 * on a boat, not a rounding error.
 */
import type { Ask, Blank, CableDimensionsTable, E11Tables, FittingsResult, HeatShrinkTable, LugsTable, OwnValues, Source } from "./schema.js";
import { usable } from "./loader.js";
import { round } from "./sizing.js";

export const MM_PER_IN = 25.4;

export function toMm(value: number, unit: "mm" | "in"): number {
  return unit === "in" ? value * MM_PER_IN : value;
}

/** "5/16\"", " M8 ", "3/8 in" and "5/16" compare equal. */
export function normalizeStud(stud: string | null | undefined): string {
  return String(stud ?? "").toLowerCase().replace(/["”]/g, "").trim().replace(/\s*in(ch)?$/, "").replace(/\s+/g, "");
}

const catalogSource = (t: { id: string; title: string; source: { document: string } }, page?: number | null): Source => ({ table: t.id, title: t.title, document: t.source.document, ...(page != null ? { page } : {}) });

export interface CableOd { value: number; unit: "mm" | "in"; mm: number; source: Source }

export function cableOutsideDiameter(sizeAwg: string, tables: E11Tables, own?: number | null): CableOd | Blank {
  const ask: Ask = { field: "own.cable_od_mm", unit: "mm", prompt: `Type the outside diameter of ${sizeAwg} AWG cable from the cable maker's catalog, in mm.` };
  if (own != null && own > 0) return { value: own, unit: "mm", mm: own, source: { by: "you" } };
  const t = usable<CableDimensionsTable>(tables, "cable_dimensions");
  if (!t) return { value: null, reason: "No cable dimensions table is confirmed under Reference, so the cable's outside diameter is not known.", ask };
  const row = t.rows.find((r) => r.size_awg === sizeAwg);
  if (!row) return { value: null, reason: `The cable dimensions table has no ${sizeAwg} AWG row.`, ask };
  return { value: row.outside_diameter, unit: t.diameter_unit, mm: round(toMm(row.outside_diameter, t.diameter_unit), 3), source: catalogSource(t, row.page) };
}

export interface HeatShrinkPick { size: string; supplied_id: number | null; recovered_id: number | null; unit: "mm" | "in" | null; adhesive: boolean | null; source: Source }

/**
 * Tubing that slides over the cable (and the lug barrel, when its size is
 * known) and shrinks below the cable so it grips: the smallest such supplied
 * size, adhesive-lined preferred when both exist.
 */
export function heatShrinkFor(cableOdMm: number | null, barrelOdMm: number | null, tables: E11Tables, own?: string | null): HeatShrinkPick | Blank {
  const ask: Ask = { field: "own.heat_shrink_size", unit: null, prompt: "Type the heat-shrink size you use for this cable, from the tubing maker's catalog.", kind: "text" };
  if (own) return { size: own, supplied_id: null, recovered_id: null, unit: null, adhesive: null, source: { by: "you" } };
  const t = usable<HeatShrinkTable>(tables, "heat_shrink");
  if (!t) return { value: null, reason: "No heat-shrink table is confirmed under Reference, so no tubing size can be picked.", ask };
  if (cableOdMm == null) return { value: null, reason: "The cable's outside diameter is not known, so no tubing size can be picked.", ask };
  const over = Math.max(cableOdMm, barrelOdMm ?? 0);
  const fits = t.rows.filter((r) => toMm(r.supplied_id, t.diameter_unit) >= over - 1e-9 && toMm(r.recovered_id, t.diameter_unit) <= cableOdMm + 1e-9);
  if (!fits.length) {
    const listed = t.rows.map((r) => `${r.size} (${r.supplied_id}→${r.recovered_id} ${t.diameter_unit})`).join(", ");
    return { value: null, reason: `No tubing in the table both slides over ${round(over, 2)} mm and shrinks below the cable's ${round(cableOdMm, 2)} mm. Listed: ${listed}.`, ask };
  }
  fits.sort((a, b) => toMm(a.supplied_id, t.diameter_unit) - toMm(b.supplied_id, t.diameter_unit) || Number(!!b.adhesive) - Number(!!a.adhesive));
  const r = fits[0];
  return { size: r.size, supplied_id: r.supplied_id, recovered_id: r.recovered_id, unit: t.diameter_unit, adhesive: r.adhesive ?? null, source: catalogSource(t, r.page) };
}

export interface LugPick {
  part: string;
  stud: string;
  crimp_die: string | null;
  barrel_od_mm: number | null;
  source: Source;
  die_source?: Source;
  /** Set when no die is known, with the ask that fills it. */
  die_reason?: string;
  die_ask?: Ask;
}

export function lugFor(sizeAwg: string, stud: string | null | undefined, tables: E11Tables, own: OwnValues = {}): LugPick | Blank {
  const wanted = normalizeStud(stud ?? own.stud);
  const askPart: Ask = { field: "own.lug_part", unit: null, prompt: `Type the lug part for ${sizeAwg} AWG on a ${stud ?? own.stud ?? "?"} stud, from the lug maker's catalog.`, kind: "text" };
  const askDie: Ask = { field: "own.crimp_die", unit: null, prompt: "Type the crimp die or setting for this lug and cable, from your crimper's chart.", kind: "text" };
  if (own.lug_part) {
    const pick: LugPick = { part: own.lug_part, stud: stud ?? own.stud ?? "", crimp_die: own.crimp_die ?? null, barrel_od_mm: null, source: { by: "you" } };
    if (own.crimp_die) pick.die_source = { by: "you" };
    else { pick.die_reason = `No crimp die is known for ${own.lug_part}.`; pick.die_ask = askDie; }
    return pick;
  }
  if (!wanted) {
    return { value: null, reason: "No stud size was given, so no lug can be picked. Type the terminal stud the lug lands on (5/16, 3/8, M8, M10…).", ask: { field: "own.stud", unit: null, prompt: "Type the terminal stud size the lug lands on, as the lug catalog names it (5/16, 3/8, M8, M10…).", kind: "text" } };
  }
  const t = usable<LugsTable>(tables, "lugs");
  if (!t) return { value: null, reason: "No lugs table is confirmed under Reference, so no lug part can be picked.", ask: askPart };
  const rows = t.rows.filter((r) => r.size_awg === sizeAwg);
  if (!rows.length) return { value: null, reason: `The lugs table has no ${sizeAwg} AWG row.`, ask: askPart };
  const row = rows.find((r) => normalizeStud(r.stud) === wanted);
  if (!row) return { value: null, reason: `The lugs table lists ${sizeAwg} AWG only for studs ${rows.map((r) => r.stud).join(", ")}, not ${stud ?? own.stud}.`, ask: askPart };
  const unit = t.diameter_unit ?? "mm";
  const pick: LugPick = { part: row.part, stud: row.stud, crimp_die: own.crimp_die ?? row.crimp_die ?? null, barrel_od_mm: row.barrel_od != null ? round(toMm(row.barrel_od, unit), 3) : null, source: catalogSource(t, row.page) };
  if (own.crimp_die) pick.die_source = { by: "you" };
  else if (row.crimp_die) pick.die_source = pick.source;
  else { pick.die_reason = `The lugs table gives no crimp die for ${row.part}.`; pick.die_ask = askDie; }
  return pick;
}

export interface FittingsInput {
  size_awg: string | null;
  parallel: number;
  stud: string | null | undefined;
  /** The whole loop, in the input unit, for the cable to buy. */
  loop_length: number;
  length_unit: "m" | "ft";
}

/** The fittings block of a circuit result, plus the blanks it adds. */
export function fittingsFor(input: FittingsInput, tables: E11Tables, own: OwnValues = {}): { fittings: FittingsResult; blanks: { field: string; reason: string; ask?: Ask }[]; steps: string[] } {
  const blanks: { field: string; reason: string; ask?: Ask }[] = [];
  const steps: string[] = [];
  const empty: FittingsResult = {
    cable_od: { value: null, unit: null, mm: null },
    heat_shrink: { size: null, supplied_id: null, recovered_id: null, unit: null, adhesive: null },
    lug: { part: null, stud: null, crimp_die: null },
    quantities: null,
  };
  if (!input.size_awg) {
    const reason = "No conductor size was settled, so no fittings can be picked.";
    return { fittings: { ...empty, cable_od: { ...empty.cable_od, reason }, heat_shrink: { ...empty.heat_shrink, reason }, lug: { ...empty.lug, reason } }, blanks, steps };
  }
  const f: FittingsResult = { ...empty };

  const od = cableOutsideDiameter(input.size_awg, tables, own.cable_od_mm);
  let odMm: number | null = null;
  if ("value" in od && od.value === null) {
    f.cable_od = { value: null, unit: null, mm: null, reason: od.reason };
    blanks.push({ field: "fittings.cable_od", reason: od.reason, ask: od.ask });
  } else {
    const o = od as CableOd;
    odMm = o.mm;
    f.cable_od = { value: o.value, unit: o.unit, mm: o.mm, source: o.source };
  }

  const lug = lugFor(input.size_awg, input.stud, tables, own);
  let barrelMm: number | null = null;
  if ("value" in lug && lug.value === null) {
    f.lug = { part: null, stud: input.stud ?? own.stud ?? null, crimp_die: null, reason: lug.reason };
    blanks.push({ field: "fittings.lug.part", reason: lug.reason, ask: lug.ask });
  } else {
    const l = lug as LugPick;
    barrelMm = l.barrel_od_mm;
    f.lug = { part: l.part, stud: l.stud, crimp_die: l.crimp_die, source: l.source, ...(l.die_source ? { die_source: l.die_source } : {}), ...(l.die_reason ? { die_reason: l.die_reason } : {}) };
    if (l.die_ask) blanks.push({ field: "fittings.lug.crimp_die", reason: l.die_reason ?? "The crimp die is not known.", ask: l.die_ask });
  }

  const hs = heatShrinkFor(odMm, barrelMm, tables, own.heat_shrink_size);
  if ("value" in hs && hs.value === null) {
    f.heat_shrink = { size: null, supplied_id: null, recovered_id: null, unit: null, adhesive: null, reason: hs.reason };
    blanks.push({ field: "fittings.heat_shrink.size", reason: hs.reason, ask: hs.ask });
  } else {
    const h = hs as HeatShrinkPick;
    f.heat_shrink = { size: h.size, supplied_id: h.supplied_id ?? null, recovered_id: h.recovered_id ?? null, unit: h.unit ?? null, adhesive: h.adhesive, source: h.source };
  }

  const n = Math.max(1, input.parallel);
  f.quantities = { cables: n, lugs: 2 * n, heat_shrink_pieces: 2 * n, cable_length: round(n * input.loop_length, 2), length_unit: input.length_unit, note: "Counts for the set: two lugs and two pieces of tubing per cable; cable to buy is the loop length per cable, plus your own routing allowance." };
  steps.push(`Fittings for ${n > 1 ? `${n} × ` : ""}${input.size_awg} AWG: ${f.cable_od.mm != null ? `outside diameter ${f.cable_od.value} ${f.cable_od.unit}` : "outside diameter not known"}; ${f.heat_shrink.size ? `heat shrink ${f.heat_shrink.size}` : "no heat shrink picked"}; ${f.lug.part ? `lug ${f.lug.part}${f.lug.crimp_die ? `, die ${f.lug.crimp_die}` : ""}` : "no lug picked"}. ${n} cable${n > 1 ? "s" : ""} × ${input.loop_length} ${input.length_unit} = ${f.quantities.cable_length} ${input.length_unit} to buy, ${2 * n} lugs, ${2 * n} pieces of tubing.`);
  return { fittings: f, blanks, steps };
}
