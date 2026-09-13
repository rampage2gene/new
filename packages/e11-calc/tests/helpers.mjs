import { readdirSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { loadTables, loadCheatSheet } from "../dist/index.js";

export const HERE = dirname(fileURLToPath(import.meta.url));
export const FIXTURE_TABLES = join(HERE, "fixtures", "tables");
export const FIXTURE_SHEET = join(HERE, "fixtures", "cheatsheet", "cheatsheet.json");

export function fixtureFiles(omit = []) {
  const files = {};
  for (const name of readdirSync(FIXTURE_TABLES).sort()) {
    if (!name.endsWith(".json")) continue;
    const raw = JSON.parse(readFileSync(join(FIXTURE_TABLES, name), "utf8"));
    if (omit.includes(raw.id)) continue;
    files[name] = raw;
  }
  return files;
}

export function fixtureTables(omit = []) {
  return loadTables(fixtureFiles(omit), { allowFixture: true });
}

export function fixtureSheet() {
  return loadCheatSheet(JSON.parse(readFileSync(FIXTURE_SHEET, "utf8")));
}

/** Every key in `expected` must be present in `actual` with the same value; arrays match element-wise as subsets. */
export function assertSubset(actual, expected, path = "") {
  if (Array.isArray(expected)) {
    if (!Array.isArray(actual)) throw new Error(`${path}: expected an array, got ${JSON.stringify(actual)}`);
    if (actual.length !== expected.length) throw new Error(`${path}: expected ${expected.length} items, got ${actual.length}: ${JSON.stringify(actual)}`);
    expected.forEach((e, i) => assertSubset(actual[i], e, `${path}[${i}]`));
    return;
  }
  if (expected !== null && typeof expected === "object") {
    if (actual === null || typeof actual !== "object") throw new Error(`${path}: expected an object, got ${JSON.stringify(actual)}`);
    for (const [k, v] of Object.entries(expected)) assertSubset(actual[k], v, path ? `${path}.${k}` : k);
    return;
  }
  if (actual !== expected) throw new Error(`${path}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
}

export function getPath(obj, path) {
  return path.split(".").reduce((o, k) => (o == null ? undefined : o[k]), obj);
}
