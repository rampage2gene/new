import { test } from "node:test";
import assert from "node:assert/strict";
import { loadTables, tablesStatus, usable, TableError } from "../dist/index.js";
import { fixtureFiles, fixtureTables } from "./helpers.mjs";

test("the fixture loads only when a test says so", () => {
  assert.throws(() => loadTables(fixtureFiles()), (e) => e instanceof TableError && /fixture/.test(e.message));
  const t = fixtureTables();
  assert.equal(t.fixture, true);
  assert.equal(Object.keys(t.byId).length, 11);
});

test("a table without a page is refused, naming the file and the field", () => {
  const files = fixtureFiles();
  const bad = { ...files["circular_mils.json"], source: { document: "x" } };
  assert.throws(() => loadTables({ "circular_mils.json": bad }, { allowFixture: true }), /circular_mils\.json: has no source\.page/);
});

test("a row without a page is refused", () => {
  const files = fixtureFiles();
  const t = files["ampacity_outside_engine_space.json"];
  const bad = { ...t, rows: [{ size_awg: "10", values: { "105": 60 } }] };
  assert.throws(() => loadTables({ "a.json": bad }, { allowFixture: true }), /a\.json: every ampacity row needs size_awg, values and page/);
});

test("a fuse class without its datasheet is refused", () => {
  const files = fixtureFiles();
  const t = files["fuse_classes.json"];
  const bad = { ...t, rows: [{ class: "Z", interrupting_rating_a: 100, suits: [] }] };
  assert.throws(() => loadTables({ "f.json": bad }, { allowFixture: true }), /fuse class Z needs source\.document and source\.page/);
});

test("a draft loads, is reported, and is not usable", () => {
  const files = fixtureFiles();
  files["constants.json"] = { ...files["constants.json"], status: "draft" };
  const t = loadTables(files, { allowFixture: true });
  assert.equal(usable(t, "constants"), null);
  const row = tablesStatus(t).find((r) => r.id === "constants");
  assert.equal(row.status, "draft");
  assert.equal(tablesStatus({ byId: {}, fixture: false }).every((r) => r.status === "missing"), true);
});

test("an unknown id or kind is refused", () => {
  const files = fixtureFiles();
  assert.throws(() => loadTables({ "x.json": { ...files["constants.json"], id: "mystery" } }, { allowFixture: true }), /unknown table id "mystery"/);
  assert.throws(() => loadTables({ "x.json": { ...files["constants.json"], kind: "mystery" } }, { allowFixture: true }), /unknown kind "mystery"/);
});
