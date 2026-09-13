import { test } from "node:test";
import assert from "node:assert/strict";
import { isBlank, nearestMetric, requiredCircularMils, sizeForAmpacity, sizeForCircularMils, sizeFromPrintedGrid, toMm2, parallelConductors, round } from "../dist/index.js";
import { fixtureTables } from "./helpers.mjs";

const T = fixtureTables();

test("round is half up, like the Python copy", () => {
  assert.equal(round(0.125, 2), 0.13);
  assert.equal(round(2.05, 1), 2.1);
  assert.equal(round(4556.7221, 1), 4556.7);
});

test("the circular-mil formula uses the page's length definition", () => {
  const cm = requiredCircularMils(24, 10, 16.4042, 3, T);
  assert.equal(isBlank(cm), false);
  assert.equal(cm.round_trip, true);
  assert.equal(cm.value, 4556.7);
  assert.deepEqual(cm.source, { table: "constants", title: "SYNTHETIC FIXTURE - formula constants", page: 1 });
  assert.ok(isBlank(requiredCircularMils(0, 10, 1, 3, T)));
});

test("the smallest listed size with enough area, or a blank that says parallel", () => {
  assert.equal(sizeForCircularMils(4000, T).size_awg, "14");
  assert.equal(sizeForCircularMils(4000.5, T).size_awg, "12");
  const over = sizeForCircularMils(9000, T);
  assert.ok(isBlank(over) && /parallel/.test(over.reason) && /page 1/.test(over.reason));
});

test("the printed grid answers only at its own voltage and inside its range", () => {
  assert.equal(sizeFromPrintedGrid(24, 10, 10, 3, T).applicable, false);
  assert.equal(sizeFromPrintedGrid(12, 10, 10, 3, T).size_awg, "12");
  assert.equal(sizeFromPrintedGrid(12, 10, 5, 3, T).size_awg, "14");
  assert.match(sizeFromPrintedGrid(12, 25, 5, 3, T).reason, /stops at 20 A, so the circular-mils formula and table are used instead/);
  assert.match(sizeFromPrintedGrid(12, 10, 25, 3, T).reason, /stops at 40 ft/);
  assert.match(sizeFromPrintedGrid(12, 10, 20, 3, T).reason, /no size for 10 A at 40 ft/);
  assert.match(sizeFromPrintedGrid(12, 10, 5, 5, T).reason, /No printed table for a 5 % limit/);
});

test("ampacity derates by the bundling factor and names the page", () => {
  const a = sizeForAmpacity(25, 105, false, 4, T);
  assert.equal(a.size_awg, "12");
  assert.equal(a.derated_a, 30);
  assert.equal(a.bundling_factor, 0.5);
  assert.equal(a.source.page, 2);
  const over = sizeForAmpacity(100, 105, false, 2, T);
  assert.equal(over.exceeded, true);
  assert.match(over.reason, /parallel/);
  const col = sizeForAmpacity(10, 75, false, 2, T);
  assert.ok(isBlank(col) && col.ask.field === "own.ampacity_a");
  const bundle = sizeForAmpacity(10, 105, false, 40, T);
  assert.ok(isBlank(bundle) && bundle.ask.field === "own.bundling_factor");
  assert.equal(sizeForAmpacity(10, 105, false, 40, T, { bundling_factor: 0.2 }).size_awg, "12");
  assert.equal(sizeForAmpacity(10, 105, false, 40, T, { bundling_factor: 0.1 }).exceeded, true);
});

test("parallel conductors: fewest, then smallest, meeting both requirements", () => {
  const p = parallelConductors(18226.9, 20, 1, 105, false, T);
  assert.deepEqual([p.count, p.size_awg, p.derated_total_a], [3, "12", 180]);
  const q = parallelConductors(null, 100, 1, 105, false, T);
  assert.deepEqual([q.count, q.size_awg], [2, "12"]);
  assert.ok(isBlank(parallelConductors(100000, 10, 1, 105, false, T)));
});

test("mm² is a unit conversion and the nearest metric size an industry list", () => {
  assert.equal(toMm2(8000), 4.05);
  assert.equal(nearestMetric(4.05), 6);
  assert.equal(nearestMetric(1000), null);
});
