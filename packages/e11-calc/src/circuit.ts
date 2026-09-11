/**
 * The whole procedure for one circuit: conductor size, then the protection
 * for that conductor, then the reminders that apply.
 *
 * Order, on engineering grounds: the conductor must satisfy two independent
 * requirements and the larger size wins - carry the current without
 * overheating (ampacity, derated for engine space and bundling) and deliver
 * the voltage (the drop limit, from the printed grid where it applies or the
 * circular-mil formula for any voltage). When no single listed size meets
 * both, conductors are paralleled. The fuse is then sized to the conductor.
 * Every step either cites a page, says "you", or is a blank with an ask.
 */
import type { Ask, CheatSheet, CircuitInputs, CircuitResult, E11Tables, OwnValues, Source } from "./schema.js";
import { remindersFor } from "./cheatsheet.js";
import { fittingsFor } from "./fittings.js";
import { CIRCUIT_TYPES } from "./profiles.js";
import { fuseForConductor, interruptingCheck } from "./protection.js";
import {
  ampacityOf, bundlingFactor, circularMilsOf, compareSizes, isBlank, lengthFt, nearestMetric, parallelConductors,
  requiredCircularMils, round, sizeForAmpacity, sizeForCircularMils, sizeFromPrintedGrid, toMm2,
} from "./sizing.js";

const cite = (s: Source | undefined): string => (!s ? "" : "by" in s ? " (entered by you)" : ` (${s.title ?? s.table}, page ${s.page})`);

export function sizeCircuit(inputs: CircuitInputs, tables: E11Tables, own: OwnValues = {}, sheet?: CheatSheet | null): CircuitResult {
  const steps: string[] = [];
  const blanks: CircuitResult["blanks"] = [];
  const blank = (field: string, reason: string, ask?: Ask) => { blanks.push(ask ? { field, reason, ask } : { field, reason }); };

  // The length as typed is the whole loop or one way; the tables' own
  // definition of L (round trip or one way, as each page words it) is applied
  // downstream, so here it is brought to one way.
  const loop = inputs.length_basis === "loop";
  const oneWay = loop ? inputs.length / 2 : inputs.length;
  const lFt = lengthFt(oneWay, inputs.length_unit);
  if (loop) steps.push(`Length: ${inputs.length} ${inputs.length_unit} there and back, ${round(oneWay, 2)} ${inputs.length_unit} each way.`);
  const rating = inputs.insulation_rating_c;
  const bundled = Math.max(2, Math.floor(inputs.bundled_conductors || 2));

  // 1. Voltage drop: the circular-mil formula, for any voltage.
  const cm = requiredCircularMils(inputs.system_voltage, inputs.current, lFt, inputs.max_drop_percent, tables, own.k);
  let vdSize: string | null = null;
  let vdSource: Source | undefined;
  let vdReason: string | undefined;
  let cmExceeded = false;
  let cmRequired: number | null = null;
  if (isBlank(cm)) {
    blank("conductor.voltage_drop.cm_required", cm.reason, cm.ask);
    vdReason = cm.reason;
  } else {
    cmRequired = cm.value;
    const eDrop = round(inputs.system_voltage * inputs.max_drop_percent / 100, 3);
    steps.push(`Voltage drop: allowed ${eDrop} V (${inputs.max_drop_percent} % of ${inputs.system_voltage} V). CM = K × I × L / E = ${cm.k} × ${inputs.current} × ${round(cm.round_trip ? 2 * lFt : lFt, 1)} ft${cm.round_trip ? " (round trip)" : ""} / ${eDrop} = ${cm.value} circular mils${cite(cm.source)}.${cm.source && "by" in cm.source ? " L taken as the round trip until the constants table is confirmed." : ""}`);
    const pick = sizeForCircularMils(cm.value, tables);
    if (isBlank(pick)) {
      if (pick.reason.includes("parallel")) { cmExceeded = true; vdReason = pick.reason; }
      else { blank("conductor.voltage_drop.size_awg", pick.reason); vdReason = pick.reason; }
      steps.push(pick.reason);
    } else {
      vdSize = pick.size_awg;
      vdSource = pick.source;
      steps.push(`Smallest listed size with at least ${cm.value} circular mils: ${pick.size_awg} AWG (${pick.circular_mils} circular mils)${cite(pick.source)}.`);
    }
  }

  // 2. The printed grid, where it applies.
  const grid = sizeFromPrintedGrid(inputs.system_voltage, inputs.current, lFt, inputs.max_drop_percent, tables);
  let printedSize: string | null = null;
  let printedSource: Source | undefined;
  let printedReason: string | undefined;
  if ("applicable" in grid) printedReason = grid.reason;
  else if (isBlank(grid)) { printedReason = grid.reason; steps.push(grid.reason); }
  else {
    printedSize = grid.size_awg;
    printedSource = grid.source;
    steps.push(`Printed ${inputs.max_drop_percent} % table at ${inputs.system_voltage} V: ${grid.printed_current} A row, ${grid.printed_length} column gives ${grid.size_awg} AWG${cite(grid.source)}.`);
  }

  // 3. Ampacity with derating.
  const amp = sizeForAmpacity(inputs.current, rating, inputs.engine_space, bundled, tables, own);
  let ampSize: string | null = null;
  let ampA: number | null = null;
  let factor: number | null = null;
  let ampSource: Source | undefined;
  let ampReason: string | undefined;
  let ampExceeded = false;
  let deratedA: number | null = null;
  if (isBlank(amp)) {
    factor = null;
    const f = bundlingFactor(bundled, tables, own.bundling_factor);
    if (!isBlank(f)) factor = f.factor;
    if (amp.ask?.field === "own.ampacity_a" && own.ampacity_a != null && vdSize && factor != null) {
      // The person read the page for the size the drop requires.
      ampA = own.ampacity_a;
      deratedA = round(ampA * factor, 1);
      ampSource = { by: "you" };
      if (deratedA >= inputs.current - 1e-9) {
        ampSize = vdSize;
        steps.push(`Ampacity: ${vdSize} AWG carries ${ampA} A × ${factor} = ${deratedA} A after derating (entered by you), enough for ${inputs.current} A.`);
      } else {
        ampReason = `${vdSize} AWG carries only ${deratedA} A after derating (entered by you), less than ${inputs.current} A; a larger conductor is needed - type its allowable current.`;
        blank("conductor.ampacity.size_awg", ampReason, amp.ask);
        steps.push(ampReason);
      }
    } else {
      ampReason = amp.reason;
      blank("conductor.ampacity.size_awg", amp.reason, amp.ask);
      steps.push(amp.reason);
    }
  } else if ("exceeded" in amp) {
    ampExceeded = true;
    factor = amp.bundling_factor;
    ampReason = amp.reason;
    steps.push(`Bundling factor ${factor} for ${bundled} conductors${cite(amp.factor_source)}. ${amp.reason}`);
  } else {
    ampSize = amp.size_awg;
    ampA = amp.ampacity_a;
    deratedA = amp.derated_a;
    factor = amp.bundling_factor;
    ampSource = amp.source;
    steps.push(`Ampacity at ${rating} °C ${inputs.engine_space ? "inside" : "outside"} an engine space, bundling factor ${factor} for ${bundled} conductors${cite(amp.factor_source)}: smallest size carrying ${inputs.current} A is ${amp.size_awg} AWG (${amp.ampacity_a} A × ${factor} = ${amp.derated_a} A)${cite(amp.source)}.`);
  }

  // 4. The larger requirement wins; parallel conductors when a single size cannot.
  let size: string | null = null;
  let parallel = 1;
  let governed: CircuitResult["conductor"]["governed_by"] = null;
  let conductorAmpacityA: number | null = null;
  const requiredParts = !isBlank(cm) && !cmExceeded ? [vdSize] : [];
  const needParallel = cmExceeded || ampExceeded;
  if (needParallel && factor != null) {
    const p = parallelConductors(cmExceeded ? cmRequired : null, inputs.current, factor, rating, inputs.engine_space, tables);
    if (isBlank(p)) {
      blank("conductor.size_awg", p.reason);
      steps.push(p.reason);
    } else {
      size = p.size_awg;
      parallel = p.count;
      governed = cmExceeded ? "voltage_drop" : "ampacity";
      conductorAmpacityA = p.derated_total_a;
      if (cmExceeded) vdSource = p.source;
      steps.push(`${p.count} × ${p.size_awg} AWG in parallel: ${p.count} × ${p.circular_mils_each} circular mils${p.derated_total_a != null ? `, ${p.derated_total_a} A after derating` : ""}${cite(p.source)}.`);
    }
  } else if (vdSize && ampSize) {
    const candidates: { size: string; by: NonNullable<CircuitResult["conductor"]["governed_by"]> }[] = [
      { size: vdSize, by: "voltage_drop" },
      { size: ampSize, by: "ampacity" },
    ];
    if (printedSize) candidates.push({ size: printedSize, by: "printed_table" });
    let best = candidates[0];
    for (const c of candidates.slice(1)) {
      const cmp = compareSizes(c.size, best.size, tables);
      if (cmp != null && cmp > 0) best = c;
    }
    size = best.size;
    governed = best.by;
    if (printedSize && vdSize && printedSize !== vdSize) steps.push(`The printed table gives ${printedSize} AWG and the formula ${vdSize} AWG; the larger is used.`);
    steps.push(`Larger of the two requirements: ${size} AWG (governed by ${governed.replace(/_/g, " ")}).`);
    const a = ampacityOf(size, rating, inputs.engine_space, tables);
    if (!isBlank(a) && factor != null) conductorAmpacityA = round(a.ampacity_a * factor, 1);
    else if (size === vdSize && deratedA != null) conductorAmpacityA = deratedA;
  } else {
    void requiredParts;
  }

  // 5. The size in both units, and the drop at that size.
  let mm2: number | null = null;
  let metric: number | null = null;
  let dropV: number | null = null;
  let dropPct: number | null = null;
  let dropReason: string | undefined;
  if (size) {
    const area = circularMilsOf(size, tables);
    if (area) {
      mm2 = area.mm2 ?? toMm2(area.circular_mils);
      metric = nearestMetric(mm2);
      if (!isBlank(cm)) {
        const totalCm = parallel * area.circular_mils;
        const l = cm.round_trip ? 2 * lFt : lFt;
        dropV = round(cm.k * inputs.current * l / totalCm, 2);
        dropPct = round(cm.k * inputs.current * l / totalCm / inputs.system_voltage * 100, 1);
        steps.push(`Drop at ${parallel > 1 ? `${parallel} × ` : ""}${size} AWG: ${cm.k} × ${inputs.current} × ${round(l, 1)} / ${totalCm} = ${dropV} V, ${dropPct} % of ${inputs.system_voltage} V.`);
      } else dropReason = "The drop at this size needs K from the constants table.";
    }
  }

  // 6. Protection for that conductor.
  const protection: CircuitResult["protection"] = {
    min_a: null, fuse_a: null, fits_conductor: null, conductor_ampacity_a: conductorAmpacityA, characteristic: null, guidance: "industry guidance, verify with the maker",
    interrupting: { required_a: null, classes: [] },
  };
  if (size && conductorAmpacityA != null) {
    const f = fuseForConductor(inputs.current, inputs.load_type, conductorAmpacityA, inputs.manufacturer_fuse_a);
    protection.min_a = f.min_a;
    protection.fuse_a = f.fuse_a;
    protection.fits_conductor = f.fits_conductor;
    protection.characteristic = f.characteristic;
    if (f.reason) { protection.reason = f.reason; blank("protection.fuse_a", f.reason); }
    steps.push(f.fits_conductor
      ? `Fuse: at least ${f.min_a} A (${f.manufacturer_a != null ? "the maker's stated rating" : `${inputs.current} A × the ${inputs.load_type.replace(/_/g, " ")} factor`}), next standard size ${f.fuse_a} A, within the conductor's ${conductorAmpacityA} A. Characteristic: ${f.characteristic} (${f.guidance}).`
      : `Fuse: ${f.reason}`);
  } else {
    protection.reason = size ? "The conductor's allowable current is not known, so no fuse can be sized to it." : "No conductor size was settled, so no fuse can be sized.";
    blank("protection.fuse_a", protection.reason);
  }
  const ic = interruptingCheck(inputs.short_circuit_a, inputs.load_type, tables, own.short_circuit_a);
  if (isBlank(ic)) {
    protection.interrupting = { required_a: null, classes: [], reason: ic.reason, ...(ic.ask ? { ask: ic.ask } : {}) };
    blank("protection.interrupting.required_a", ic.reason, ic.ask);
  } else {
    protection.interrupting = { required_a: ic.required_a, classes: ic.classes, ...(ic.reason ? { reason: ic.reason } : {}) };
    steps.push(ic.classes.length
      ? `Interrupting capacity: the source can deliver ${ic.required_a} A${"by" in ic.source ? " (entered by you)" : ""}; fuse classes rated at least that: ${ic.classes.map((c) => `${c.class} (${c.interrupting_rating_a} A${c.suits_load ? ", suits this load" : ""})`).join(", ")}.`
      : `Interrupting capacity: ${ic.reason}`);
  }

  // 7. The fittings for that conductor, from the owner's catalog tables.
  const loopLength = loop ? inputs.length : 2 * inputs.length;
  const fit = fittingsFor({ size_awg: size, parallel, stud: inputs.stud_size, loop_length: loopLength, length_unit: inputs.length_unit }, tables, own);
  blanks.push(...fit.blanks);
  steps.push(...fit.steps);

  // 8. Reminders that apply.
  const tags = ["dc", inputs.load_type];
  if (inputs.circuit_type) tags.push(inputs.circuit_type, ...(CIRCUIT_TYPES[inputs.circuit_type]?.tags ?? []));
  if (inputs.engine_space) tags.push("engine_space");
  if (bundled >= 3) tags.push("bundled");
  if (parallel > 1) tags.push("parallel");
  const reminders = sheet ? remindersFor(sheet, tags) : [];

  return {
    conductor: {
      size_awg: size, size_mm2: mm2, metric_standard_mm2: metric, parallel, governed_by: governed,
      voltage_drop: { cm_required: cmRequired, size_awg: vdSize, ...(vdReason ? { reason: vdReason } : {}), ...(vdSource ? { source: vdSource } : {}) },
      printed_table: { size_awg: printedSize, ...(printedReason ? { reason: printedReason } : {}), ...(printedSource ? { source: printedSource } : {}) },
      ampacity: { size_awg: ampSize, ampacity_a: ampA, bundling_factor: factor, ...(ampReason ? { reason: ampReason } : {}), ...(ampSource ? { source: ampSource } : {}) },
      drop_at_size: { volts: dropV, percent: dropPct, ...(dropReason ? { reason: dropReason } : {}) },
    },
    protection,
    fittings: fit.fittings,
    reminders,
    blanks,
    steps,
    fixture: tables.fixture,
  };
}
