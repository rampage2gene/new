import { test } from "node:test";
import assert from "node:assert/strict";
import { join } from "node:path";
import { loadTablesFromDir, loadCheatSheetFromFile } from "../dist/node.js";
import { FIXTURE_SHEET, FIXTURE_TABLES, HERE } from "./helpers.mjs";

test("the directory reader loads every *.json as a table", () => {
  const t = loadTablesFromDir(FIXTURE_TABLES, { allowFixture: true });
  assert.equal(Object.keys(t.byId).length, 11);
  assert.equal(loadCheatSheetFromFile(FIXTURE_SHEET).entries.length, 4);
});

test("a missing folder is an empty set, not an error", () => {
  const t = loadTablesFromDir(join(HERE, "no-such-folder"));
  assert.deepEqual(t, { byId: {}, fixture: false });
  assert.equal(loadCheatSheetFromFile(join(HERE, "none.json")), null);
});

test("the shipped tables folder, when it has tables, holds no drafts and no fixture", () => {
  const t = loadTablesFromDir(join(HERE, "..", "tables"));
  for (const table of Object.values(t.byId)) assert.equal(table.status, "confirmed", `${table.id} is ${table.status}`);
});
