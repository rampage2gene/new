/**
 * The installation reminders: one entry per rule, each with the clause and
 * page of the owner's copy of the standard. Rendered to Markdown and HTML for
 * reading on their own, and filtered by tag to ride along with a calculation.
 */
import type { CheatSheet, CheatSheetEntry } from "./schema.js";

export class CheatSheetError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "CheatSheetError";
  }
}

function isRecord(x: unknown): x is Record<string, unknown> {
  return typeof x === "object" && x !== null && !Array.isArray(x);
}

/** Refuses an entry without a clause or a page: a reminder with no way back to the page is a guess. */
export function loadCheatSheet(raw: unknown): CheatSheet {
  if (!isRecord(raw)) throw new CheatSheetError("cheat sheet is not a JSON object");
  if (!isRecord(raw.source) || typeof raw.source.document !== "string") throw new CheatSheetError("cheat sheet has no source.document");
  if (!Array.isArray(raw.entries)) throw new CheatSheetError("cheat sheet has no entries");
  const entries: CheatSheetEntry[] = raw.entries.map((e, i) => {
    if (!isRecord(e)) throw new CheatSheetError(`entry ${i + 1} is not an object`);
    for (const key of ["topic", "rule", "clause"]) {
      if (typeof e[key] !== "string" || (e[key] as string).trim() === "") throw new CheatSheetError(`entry ${i + 1} has no ${key}`);
    }
    if (typeof e.page !== "number" || !Number.isInteger(e.page) || e.page < 1) throw new CheatSheetError(`entry ${i + 1} ("${String(e.rule).slice(0, 40)}") has no page`);
    const tags = Array.isArray(e.applies_to) && e.applies_to.length ? e.applies_to.map(String) : ["always"];
    const status = e.status === "confirmed" ? "confirmed" : "draft";
    return { topic: e.topic as string, rule: e.rule as string, clause: e.clause as string, page: e.page, applies_to: tags, status };
  });
  return { source: { document: raw.source.document, edition: typeof raw.source.edition === "string" ? raw.source.edition : undefined }, entries };
}

/** Entries whose tags meet the situation's tags ("always" is always met). */
export function remindersFor(sheet: CheatSheet, tags: string[]): CheatSheetEntry[] {
  const set = new Set(["always", ...tags]);
  return sheet.entries.filter((e) => e.applies_to.some((t) => set.has(t)));
}

function topics(sheet: CheatSheet): [string, CheatSheetEntry[]][] {
  const out = new Map<string, CheatSheetEntry[]>();
  for (const e of sheet.entries) {
    if (!out.has(e.topic)) out.set(e.topic, []);
    out.get(e.topic)!.push(e);
  }
  return [...out.entries()];
}

const mdCell = (s: string) => s.replace(/\|/g, "\\|").replace(/\r?\n/g, " ");

export function renderMarkdown(sheet: CheatSheet): string {
  const title = `${sheet.source.document}${sheet.source.edition ? ` (${sheet.source.edition})` : ""}`;
  const lines: string[] = [
    `# Installation reminders from ${title}`,
    "",
    "Every rule names the clause and page of the owner's own copy; a rule marked *draft* has not yet been checked against its page.",
    "",
  ];
  for (const [topic, entries] of topics(sheet)) {
    lines.push(`## ${topic}`, "", "| Rule | Clause | Page |", "|---|---|---|");
    for (const e of entries) lines.push(`| ${mdCell(e.rule)}${e.status === "draft" ? " *(draft)*" : ""} | ${mdCell(e.clause)} | p. ${e.page} |`);
    lines.push("");
  }
  return lines.join("\n");
}

const esc = (s: string) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

export function renderHtml(sheet: CheatSheet): string {
  const title = `${sheet.source.document}${sheet.source.edition ? ` (${sheet.source.edition})` : ""}`;
  const parts: string[] = [
    "<!doctype html>",
    '<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">',
    `<title>Installation reminders from ${esc(title)}</title>`,
    "<style>body{font:15px/1.5 system-ui,sans-serif;max-width:60rem;margin:2rem auto;padding:0 1rem;color:#1a1a1a;background:#fff}table{border-collapse:collapse;width:100%;margin-bottom:1.5rem}th,td{text-align:left;vertical-align:top;padding:.4rem .6rem;border-bottom:1px solid #ddd}th{font-size:.8rem;text-transform:uppercase;letter-spacing:.04em;color:#555}td.page{white-space:nowrap}em.draft{color:#8a5a00}</style>",
    "</head><body>",
    `<h1>Installation reminders from ${esc(title)}</h1>`,
    "<p>Every rule names the clause and page of the owner's own copy; a rule marked <em class=\"draft\">draft</em> has not yet been checked against its page.</p>",
  ];
  for (const [topic, entries] of topics(sheet)) {
    parts.push(`<h2>${esc(topic)}</h2>`, "<table><thead><tr><th>Rule</th><th>Clause</th><th>Page</th></tr></thead><tbody>");
    for (const e of entries) parts.push(`<tr><td>${esc(e.rule)}${e.status === "draft" ? ' <em class="draft">(draft)</em>' : ""}</td><td>${esc(e.clause)}</td><td class="page">p. ${e.page}</td></tr>`);
    parts.push("</tbody></table>");
  }
  parts.push("</body></html>", "");
  return parts.join("\n");
}
