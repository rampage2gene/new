import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, existsSync } from "node:fs";
import { join } from "node:path";
import { loadCheatSheet, remindersFor, renderHtml, renderMarkdown, CheatSheetError } from "../dist/index.js";
import { HERE, fixtureSheet } from "./helpers.mjs";

test("an entry without a clause or a page is refused", () => {
  assert.throws(() => loadCheatSheet({ source: { document: "d" }, entries: [{ topic: "t", rule: "r", page: 1 }] }), (e) => e instanceof CheatSheetError && /entry 1 has no clause/.test(e.message));
  assert.throws(() => loadCheatSheet({ source: { document: "d" }, entries: [{ topic: "t", rule: "r", clause: "c" }] }), /entry 1 .* has no page/);
  assert.throws(() => loadCheatSheet({ entries: [] }), /no source\.document/);
});

test("reminders are picked by tag, with 'always' always in", () => {
  const s = fixtureSheet();
  assert.deepEqual(remindersFor(s, ["dc"]).map((e) => e.clause), ["F.1"]);
  assert.deepEqual(remindersFor(s, ["parallel", "engine_space"]).map((e) => e.clause), ["F.1", "F.2", "F.3"]);
});

test("the Markdown render is byte-identical to the shared expectation (the Python copy is held to the same file)", () => {
  const expected = readFileSync(join(HERE, "cheatsheet-expected.md"), "utf8");
  assert.equal(renderMarkdown(fixtureSheet()), expected);
});

test("the HTML render escapes and marks drafts", () => {
  const html = renderHtml(fixtureSheet());
  assert.match(html, /<title>Installation reminders from SYNTHETIC TEST FIXTURE - not ABYC E-11 \(fixture\)<\/title>/);
  assert.match(html, /<em class="draft">\(draft\)<\/em>/);
  assert.ok(!html.includes("<script"));
});

test("the committed cheat sheet, when present, matches a fresh render", () => {
  const dir = join(HERE, "..", "cheatsheet");
  const json = join(dir, "cheatsheet.json");
  if (!existsSync(json)) return;
  const sheet = loadCheatSheet(JSON.parse(readFileSync(json, "utf8")));
  assert.equal(readFileSync(join(dir, "cheatsheet.md"), "utf8"), renderMarkdown(sheet));
  assert.equal(readFileSync(join(dir, "cheatsheet.html"), "utf8"), renderHtml(sheet));
});
