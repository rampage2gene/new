/**
 * e11-calc: conductor sizing and overcurrent protection for small-craft DC
 * circuits, from ABYC E-11 tables that you supply as JSON.
 *
 *   import { loadTables, sizeCircuit } from "e11-calc";
 *   const tables = loadTables({ "constants.json": constants, ... });
 *   const result = sizeCircuit({ system_voltage: 24, current: 30, length: 6, length_unit: "m",
 *     max_drop_percent: 3, insulation_rating_c: 105, engine_space: false, bundled_conductors: 2,
 *     load_type: "inverter" }, tables);
 *
 * Nothing here carries a table value of its own. A table that is not
 * confirmed against its page is unusable; a case the tables do not cover is
 * a blank that names the value you can type instead, and your value is
 * reported as yours.
 */
export * from "./schema.js";
export { loadTables, validateTable, usable, tablesStatus, TableError } from "./loader.js";
export type { LoadOptions, TableStatusRow } from "./loader.js";
export * from "./sizing.js";
export * from "./protection.js";
export * from "./profiles.js";
export { loadCheatSheet, remindersFor, renderMarkdown, renderHtml, CheatSheetError } from "./cheatsheet.js";
export * from "./fittings.js";
export { sizeCircuit } from "./circuit.js";
