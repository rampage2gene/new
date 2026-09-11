/**
 * Node-only helpers: read the tables and the cheat sheet from a folder. The
 * core never touches the file system, so a browser app imports or fetches
 * the JSON and calls loadTables itself.
 */
import { readdirSync, readFileSync, existsSync } from "node:fs";
import { join } from "node:path";
import { loadTables, type LoadOptions } from "./loader.js";
import { loadCheatSheet } from "./cheatsheet.js";
import type { CheatSheet, E11Tables } from "./schema.js";

/** Every *.json in the folder is a table; other files are ignored. */
export function loadTablesFromDir(dir: string, opts: LoadOptions = {}): E11Tables {
  const files: Record<string, unknown> = {};
  if (existsSync(dir)) {
    for (const name of readdirSync(dir).sort()) {
      if (!name.endsWith(".json")) continue;
      files[name] = JSON.parse(readFileSync(join(dir, name), "utf8"));
    }
  }
  return loadTables(files, opts);
}

export function loadCheatSheetFromFile(path: string): CheatSheet | null {
  if (!existsSync(path)) return null;
  return loadCheatSheet(JSON.parse(readFileSync(path, "utf8")));
}
