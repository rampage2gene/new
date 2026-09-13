#!/usr/bin/env node
/**
 * Mechanical half of the UI contract (docs/UI.md).
 *
 * Only the rules a machine can decide without an opinion. Everything that
 * needs judgement - hierarchy, wording, whether a flow is too long - belongs
 * to the /design-pass crew, not here.
 *
 * Node built-ins only: this runs on every UI change, so it must never add a
 * dependency or a download to the build.
 *
 *   node scripts/ui-check.mjs          errors fail the run, warnings do not
 *   node scripts/ui-check.mjs --strict warnings fail too
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const SRC = join(ROOT, "src");
const STYLES = join(SRC, "styles.css");
const STRICT = process.argv.includes("--strict");

/** docs/UI.md §2. Values outside this are a mistake, not a decision. */
const SPACING = new Set([0, 1, 2, 4, 6, 8, 10, 12, 14, 16, 20, 24]);
/** Rules are written one per line here, so find the property anywhere in it. */
const SPACING_PROPS = /(?:^|[{;]\s*)(?:padding|margin|gap|row-gap|column-gap)(?:-(?:top|right|bottom|left))?\s*:\s*([^;}]+)/g;
/** Translucent overlays on the page image: colour *is* the content there. */
const COLOUR_EXEMPT = /^\s*(?:--|\.hl\b|\.hl[.:]|@|\/\*)/;
const COLOUR = /#[0-9a-fA-F]{3,8}\b|\brgba?\(/;
/** A control whose whole label is one symbol says nothing to a screen reader. */
const ICON_ONLY = /<button\b([^>]*)>\s*([^\w\s<{]{1,2})\s*<\/button>/g;
/** §9 - words from the codebase that mean nothing to the person reading the
 *  screen (CLAUDE.md "Writing"). Checked in JSX text and in the attributes a
 *  person reads (title, placeholder, aria-label), never in identifiers. */
const JARGON = /\b(entity|entities|ingest(?:ed|ion|ing)?|qc flags?|pipeline|verification layer|plausibility)\b/i;
const READABLE = /(?:>([^<>{}\n]+)<)|(?:\b(?:title|placeholder|aria-label)=(?:"([^"]*)"|\{`([^`]*)`\})|(?:`([^`]*)`))/g;
/** `${…}` inside a template literal is code, not copy. */
const INTERPOLATION = /\$\{[^}]*\}/g;

const findings = [];
const add = (level, file, line, rule, message) => findings.push({ level, file, line, rule, message });

function walk(dir) {
  const out = [];
  for (const name of readdirSync(dir)) {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) out.push(...walk(path));
    else if (/\.(tsx|ts|css)$/.test(name)) out.push(path);
  }
  return out;
}

const rel = (p) => relative(ROOT, p).replace(/\\/g, "/");

// --------------------------------------------------------------- stylesheet
function checkStylesheet() {
  const lines = readFileSync(STYLES, "utf8").split("\n");
  let inRoot = false;
  lines.forEach((raw, i) => {
    const line = raw.trim();
    const at = i + 1;
    if (/^:root\s*\{/.test(line)) inRoot = true;
    else if (inRoot && line.startsWith("}")) inRoot = false;

    // §1 - colour lives in the tokens, nowhere else.
    if (!inRoot && COLOUR.test(line) && !COLOUR_EXEMPT.test(line)) {
      add("error", rel(STYLES), at, "token", `colour literal outside :root - use a var(--…): ${line.slice(0, 72)}`);
    }
    // §2 - one spacing scale.
    for (const prop of line.matchAll(SPACING_PROPS)) {
      for (const m of prop[1].matchAll(/(-?\d+(?:\.\d+)?)px/g)) {
        const v = Math.abs(parseFloat(m[1]));
        if (!SPACING.has(v)) {
          add("warn", rel(STYLES), at, "spacing", `${m[0]} is off the 2-24 scale in "${prop[0].trim().slice(0, 40)}"`);
        }
      }
    }
  });
}

// ------------------------------------------------------------------ sources
function checkSource(path) {
  const text = readFileSync(path, "utf8");
  const lines = text.split("\n");
  const file = rel(path);

  lines.forEach((raw, i) => {
    const at = i + 1;
    // §1 - inline colour in a component is the same mistake, one layer up.
    if (/style=\{\{/.test(raw) && COLOUR.test(raw)) {
      add("error", file, at, "token", `colour literal in an inline style - use a class or a var(--…)`);
    }
  });

  // §5 - a table must never widen the page.
  for (const m of text.matchAll(/<table\b/g)) {
    const at = text.slice(0, m.index).split("\n").length;
    const before = lines.slice(Math.max(0, at - 8), at).join(" ");
    if (!/table-scroll|className="group"|className={`group/.test(before)) {
      add("error", file, at, "table", "<table> is not inside .table-scroll (or .group) - it will widen the page on a phone");
    }
  }

  // §8 - an icon-only control needs a name.
  for (const m of text.matchAll(ICON_ONLY)) {
    const at = text.slice(0, m.index).split("\n").length;
    if (!/aria-label|title=/.test(m[1])) {
      add("error", file, at, "a11y", `icon-only button "${m[2]}" has no aria-label or title`);
    }
  }

  // §9 - the copy voice: no codebase words in what a person reads.
  if (file.endsWith(".tsx")) {
    for (const m of text.matchAll(READABLE)) {
      const readable = (m[1] ?? m[2] ?? m[3] ?? m[4] ?? "").replace(INTERPOLATION, " ");
      const hit = readable.match(JARGON);
      if (hit) {
        const at = text.slice(0, m.index).split("\n").length;
        add("error", file, at, "voice", `"${hit[0]}" is a codebase word - say value, add, check, note (CLAUDE.md "Writing")`);
      }
    }
  }

  // §4 - a list view needs something to say when it is empty.
  if (/\/pages\/\w+Page\.tsx$/.test(file) && /\.map\(/.test(text) && !/className="empty"/.test(text)) {
    add("warn", file, 1, "state", "page renders a list but has no .empty state (docs/UI.md §4)");
  }
}

// --------------------------------------------------------------------- main
checkStylesheet();
for (const path of walk(SRC)) {
  if (path.endsWith(".css")) continue;
  checkSource(path);
}

const errors = findings.filter((f) => f.level === "error");
const warns = findings.filter((f) => f.level === "warn");
const order = { error: 0, warn: 1 };
findings
  .sort((a, b) => order[a.level] - order[b.level] || a.file.localeCompare(b.file) || a.line - b.line)
  .forEach((f) => console.log(`${f.level === "error" ? "ERROR" : "warn "} ${f.file}:${f.line} [${f.rule}] ${f.message}`));

const counts = (list) =>
  Object.entries(list.reduce((acc, f) => ({ ...acc, [f.rule]: (acc[f.rule] || 0) + 1 }), {}))
    .map(([rule, n]) => `${rule} ${n}`)
    .join(", ") || "none";

console.log(`\nui-check: ${errors.length} error(s) [${counts(errors)}], ${warns.length} warning(s) [${counts(warns)}]`);
console.log("The standard is docs/UI.md. Judgement calls belong to /design-pass, not to this script.");
process.exit(errors.length || (STRICT && warns.length) ? 1 : 0);
