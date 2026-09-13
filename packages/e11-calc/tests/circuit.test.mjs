import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { conditionOptions, presentCircuit, sizeCircuit } from "../dist/index.js";
import { HERE, assertSubset, fixtureSheet, fixtureTables, getPath } from "./helpers.mjs";

const vectors = JSON.parse(readFileSync(join(HERE, "test-vectors.json"), "utf8"));

for (const c of vectors.cases) {
  test(`vector: ${c.name}`, () => {
    const tables = fixtureTables(c.omit || []);
    const inputs = { ...vectors.defaults, ...c.inputs };
    const result = sizeCircuit(inputs, tables, c.own || {}, fixtureSheet());
    assertSubset(result, c.expect || {});
    for (const b of c.blanks || []) {
      const hit = result.blanks.find((x) => x.field === b.field);
      assert.ok(hit, `blank ${b.field} missing; blanks: ${JSON.stringify(result.blanks)}`);
      if (b.reason_contains) assert.ok(hit.reason.includes(b.reason_contains), `blank ${b.field} reason "${hit.reason}" lacks "${b.reason_contains}"`);
      if (b.ask_field) assert.equal(hit.ask?.field, b.ask_field, `blank ${b.field} ask`);
    }
    if (c.blanks_count != null) assert.equal(result.blanks.length, c.blanks_count, `blanks: ${JSON.stringify(result.blanks)}`);
    if (c.reminders_count != null) assert.equal(result.reminders.length, c.reminders_count, `reminders: ${JSON.stringify(result.reminders.map((r) => r.clause))}`);
    for (const [path, text] of Object.entries(c.reason_contains || {})) {
      const v = getPath(result, path);
      assert.ok(typeof v === "string" && v.includes(text), `${path} = ${JSON.stringify(v)} lacks "${text}"`);
    }
    for (const text of c.steps_contain || []) assert.ok(result.steps.some((s) => s.includes(text)), `no step contains "${text}": ${JSON.stringify(result.steps)}`);
    // The words a person reads come from the same two engines as the numbers,
    // so a label or a sentence changed in one and not the other fails here.
    if (c.present) {
      const view = presentCircuit(inputs, result, { unit: c.present.unit || "awg", own: c.own || {} });
      for (const [key, want] of Object.entries(c.present.rows || {})) {
        const row = view.rows.find((r) => r.key === key);
        assert.ok(row, `no presented row "${key}"; rows: ${view.rows.map((r) => r.key).join(", ")}`);
        for (const [field, value] of Object.entries(want)) {
          if (field === "note_contains") assert.ok(typeof row.note === "string" && row.note.includes(value), `${key} note ${JSON.stringify(row.note)} lacks "${value}"`);
          else assert.deepEqual(row[field], value, `${key}.${field}`);
        }
      }
      if (c.present.groups) assert.deepEqual([...new Set(view.rows.map((r) => r.group))], c.present.groups);
      if (c.present.condition_options) {
        const offered = conditionOptions(tables);
        for (const [key, labels] of Object.entries(c.present.condition_options)) {
          assert.ok(offered[key], `no options generated for "${key}"`);
          assert.deepEqual(offered[key].map((o) => o.label), labels, `options for ${key}`);
        }
      }
    }
    // Every blank names its field, and every ask its own.* field.
    for (const b of result.blanks) {
      assert.ok(b.field && b.reason, JSON.stringify(b));
      if (b.ask) assert.match(b.ask.field, /^own\./);
    }
  });
}

test("a draft table is loaded but unusable, and the result says so", () => {
  const files = { ...fixtureFilesWithDraft() };
  const tables = fixtureTablesFrom(files);
  const r = sizeCircuit(vectors.defaults, tables, {}, null);
  assert.equal(r.conductor.ampacity.size_awg, null);
  assert.ok(r.blanks.some((b) => b.field === "conductor.ampacity.size_awg" && b.reason.includes("not confirmed")));
});

function fixtureFilesWithDraft() {
  const files = {};
  for (const [name, raw] of Object.entries(fixtureFilesRaw())) {
    files[name] = raw.id === "ampacity_outside_engine_space" ? { ...raw, status: "draft" } : raw;
  }
  return files;
}

import { fixtureFiles as fixtureFilesRaw } from "./helpers.mjs";
import { loadTables } from "../dist/index.js";
function fixtureTablesFrom(files) {
  return loadTables(files, { allowFixture: true });
}
