#!/usr/bin/env node
/**
 * Render cheatsheet/cheatsheet.json to cheatsheet.md and cheatsheet.html so
 * the library ships the reminders in a form anyone can read. A test asserts
 * the committed files match a fresh render; run `npm run cheatsheet` after
 * editing the JSON.
 */
import { readFileSync, writeFileSync, existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { loadCheatSheet, renderHtml, renderMarkdown } from "../dist/index.js";

const dir = join(dirname(fileURLToPath(import.meta.url)), "..", "cheatsheet");
const json = join(dir, "cheatsheet.json");
if (!existsSync(json)) {
  console.log(`no ${json}: nothing to render (the owner's reminders have not been added yet)`);
  process.exit(0);
}
const sheet = loadCheatSheet(JSON.parse(readFileSync(json, "utf8")));
writeFileSync(join(dir, "cheatsheet.md"), renderMarkdown(sheet));
writeFileSync(join(dir, "cheatsheet.html"), renderHtml(sheet));
console.log(`rendered ${sheet.entries.length} entries to cheatsheet.md and cheatsheet.html`);
