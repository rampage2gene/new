import { test } from "node:test";
import assert from "node:assert/strict";
import { cableOutsideDiameter, heatShrinkFor, lugFor, normalizeStud, sizeCircuit, loadTables, toMm } from "../dist/index.js";
import { fixtureFiles, fixtureTables } from "./helpers.mjs";

test("stud names compare without quotes, spaces or 'in'", () => {
  for (const s of ['5/16"', " 5/16 ", "5/16 in", "5/16in"]) assert.equal(normalizeStud(s), "5/16");
  assert.equal(normalizeStud("M8"), "m8");
  assert.equal(normalizeStud(null), "");
});

test("inch tables are compared in mm", () => {
  assert.equal(toMm(1, "in"), 25.4);
  const files = fixtureFiles();
  const inches = { ...files["cable_dimensions.json"], diameter_unit: "in", rows: [{ size_awg: "12", outside_diameter: 0.25 }] };
  const t = loadTables({ ...files, "cable_dimensions.json": inches }, { allowFixture: true });
  const od = cableOutsideDiameter("12", t);
  assert.equal(od.value, 0.25);
  assert.equal(od.unit, "in");
  assert.equal(od.mm, 6.35);
  assert.equal(od.source.document, inches.source.document);
});

test("tubing must slide over the larger of cable and barrel, and shrink below the cable", () => {
  const t = fixtureTables();
  assert.equal(heatShrinkFor(2, null, t).size, "S3");
  assert.equal(heatShrinkFor(2, 5, t).size, "S6");
  const none = heatShrinkFor(0.5, null, t);
  assert.equal(none.value, null);
  assert.match(none.reason, /shrinks below/);
  assert.equal(none.ask.kind, "text");
});

test("a lug row needs the size and the stud; the die comes from the row or the person", () => {
  const t = fixtureTables();
  const l = lugFor("12", '5/16"', t);
  assert.deepEqual([l.part, l.crimp_die, l.barrel_od_mm], ["L12-516", "D12", 7]);
  const noDie = lugFor("12", "M8", t);
  assert.equal(noDie.crimp_die, null);
  assert.equal(noDie.die_ask.field, "own.crimp_die");
  const ownDie = lugFor("12", "M8", t, { crimp_die: "DX" });
  assert.deepEqual([ownDie.crimp_die, ownDie.die_source], ["DX", { by: "you" }]);
  const missing = lugFor("10", "5/16", t);
  assert.match(missing.reason, /no 10 AWG row/);
});

test("a page that defines L one way takes half the loop", () => {
  const files = fixtureFiles();
  const oneWay = { ...files["constants.json"], length_definition: "one_way" };
  const t = loadTables({ ...files, "constants.json": oneWay }, { allowFixture: true });
  const base = { system_voltage: 24, current: 10, length_unit: "m", max_drop_percent: 3, insulation_rating_c: 105, engine_space: false, bundled_conductors: 2, load_type: "resistive", stud_size: "5/16" };
  const loop = sizeCircuit({ ...base, length: 10, length_basis: "loop" }, t);
  const one = sizeCircuit({ ...base, length: 5 }, t);
  assert.equal(loop.conductor.voltage_drop.cm_required, one.conductor.voltage_drop.cm_required);
  // K × I × L / E with L one way: 10 × 10 × 16.4 ft / 0.72 V.
  assert.equal(one.conductor.voltage_drop.cm_required, 2278.4);
  assert.ok(loop.steps[0].includes("there and back"));
});
