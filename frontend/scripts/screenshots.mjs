#!/usr/bin/env node
/**
 * Photograph every screen at phone, tablet and desktop width.
 *
 * The point is to review what the application *looks like*. Reading CSS tells
 * you what was intended; the 360px column of these images tells you what
 * actually happens, which is where this UI has broken before.
 *
 * Self-contained: it starts a backend on a scratch data directory, feeds it
 * the sample documents, waits for them to be read, then drives a headless
 * browser over every route. Nothing touches your real library.
 *
 *   npm run ui:shots                 build the UI first, then shoot
 *   npm run ui:shots -- --base=URL   shoot a server that is already running
 *   npm run ui:shots -- --keep       leave the scratch server up afterwards
 *
 * Playwright is deliberately NOT in package.json: it would add a browser
 * download to every CI job and to the packaged app's build. Install it when
 * you need pictures:  npm i --no-save playwright
 */
import { spawn } from "node:child_process";
import { existsSync, mkdirSync, mkdtempSync, readdirSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const FRONTEND = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const REPO = resolve(FRONTEND, "..");
const OUT = join(FRONTEND, ".ui-shots");

const arg = (name, fallback) => {
  const hit = process.argv.find((a) => a.startsWith(`--${name}=`));
  return hit ? hit.slice(name.length + 3) : fallback;
};
const KEEP = process.argv.includes("--keep");
const PORT = Number(arg("port", 8791));

/** docs/UI.md §7. 360 is the width that finds the bugs. */
const WIDTHS = [
  { name: "360-phone", width: 360, height: 780 },
  { name: "768-tablet", width: 768, height: 1024 },
  { name: "1440-desktop", width: 1440, height: 900 },
];

/** `doc` is replaced with the id of the processed sample document. */
const ROUTES = [
  ["library", "/library"],
  ["document-assistant", "/documents/{doc}?tab=assistant"],
  ["document-data", "/documents/{doc}?tab=data"],
  ["document-fill", "/documents/{doc}?tab=fill"],
  ["document-structure", "/documents/{doc}?tab=structure"],
  ["document-qc", "/documents/{doc}?tab=qc"],
  ["search", "/search"],
  ["calculators", "/calculators"],
  ["compare", "/compare"],
  ["invoices", "/invoices"],
  ["convert", "/convert"],
  ["phone", "/phone"],
  ["diagnostics", "/diagnostics"],
];

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/** A Chromium already on this machine, whatever build Playwright expects. */
function findChromium() {
  const base = process.env.PLAYWRIGHT_BROWSERS_PATH;
  if (!base || !existsSync(base)) return null;
  const dirs = readdirSync(base).filter((d) => d.startsWith("chromium")).sort().reverse();
  for (const dir of dirs) {
    for (const exe of ["chrome-linux/chrome", "chrome-linux/headless_shell", "chrome-mac/Chromium.app/Contents/MacOS/Chromium", "chrome-win/chrome.exe"]) {
      const path = join(base, dir, exe);
      if (existsSync(path)) return path;
    }
  }
  return null;
}

async function waitFor(url, seconds = 90) {
  const deadline = Date.now() + seconds * 1000;
  while (Date.now() < deadline) {
    try {
      if ((await fetch(url)).ok) return true;
    } catch {
      /* not up yet */
    }
    await sleep(500);
  }
  return false;
}

/** Start a backend on a scratch data directory and feed it the samples. */
async function startFixture() {
  const dataDir = mkdtempSync(join(tmpdir(), "mdi-shots-"));
  const samples = join(dataDir, "samples");
  mkdirSync(samples, { recursive: true });
  console.log(`fixture: data in ${dataDir}`);

  await new Promise((done, fail) => {
    const p = spawn("python", [join(REPO, "scripts", "make_samples.py"), samples], { cwd: REPO, stdio: "inherit" });
    p.on("exit", (code) => (code === 0 ? done() : fail(new Error(`make_samples.py exited ${code}`))));
  });

  const server = spawn("python", ["-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", String(PORT)], {
    cwd: join(REPO, "backend"),
    stdio: "inherit",
    env: {
      ...process.env,
      MDI_DATA_DIR: dataDir,
      MDI_FRONTEND_DIST: join(FRONTEND, "dist"),
      MDI_INBOX_WATCHER: "false",
      MDI_AI_ENABLED: "false",
      MDI_LAN: "false",
    },
  });
  const base = `http://127.0.0.1:${PORT}`;
  if (!(await waitFor(`${base}/api/status`))) throw new Error("the backend did not start");

  // Upload the samples the way the UI does, so the screens have real content.
  const body = new FormData();
  for (const name of readdirSync(samples)) {
    body.append("files", new Blob([readFileSync(join(samples, name))]), name);
  }
  const created = await (await fetch(`${base}/api/documents`, { method: "POST", body })).json();
  console.log(`fixture: uploaded ${created.length} document(s), waiting for them to be read`);

  const deadline = Date.now() + 300000;
  let docs = [];
  while (Date.now() < deadline) {
    docs = await (await fetch(`${base}/api/documents`)).json();
    if (docs.every((d) => d.status === "ready" || d.status === "failed")) break;
    await sleep(2000);
  }
  const ready = docs.filter((d) => d.status === "ready");
  console.log(`fixture: ${ready.length}/${docs.length} ready`);
  // The one with the most values to look at makes the best screenshots.
  const best = ready.sort((a, b) => (b.page_count || 0) - (a.page_count || 0))[0];
  return { base, docId: best?.id, server, dataDir };
}

async function shoot(base, docId) {
  let chromium;
  try {
    ({ chromium } = await import("playwright"));
  } catch {
    console.error(
      "\nPlaywright is not installed (deliberately: it would add a browser download to every CI job).\n" +
        "  cd frontend && npm i --no-save playwright\n" +
        "The browsers themselves are already on this machine (PLAYWRIGHT_BROWSERS_PATH).\n",
    );
    process.exit(2);
  }
  rmSync(OUT, { recursive: true, force: true });
  mkdirSync(OUT, { recursive: true });

  // Use whatever Chromium is already on the machine when the installed
  // Playwright wants a build that is not there, rather than downloading one.
  const launch = {};
  const executablePath = arg("chromium", process.env.MDI_CHROMIUM || findChromium());
  if (executablePath) launch.executablePath = executablePath;
  const browser = await chromium.launch(launch);
  const problems = [];
  for (const size of WIDTHS) {
    const context = await browser.newContext({ viewport: { width: size.width, height: size.height }, deviceScaleFactor: 1 });
    const page = await context.newPage();
    for (const [name, route] of ROUTES) {
      if (route.includes("{doc}") && !docId) continue;
      const url = base + route.replace("{doc}", docId);
      await page.goto(url, { waitUntil: "networkidle" }).catch(() => {});
      await sleep(600); // let the first fetches paint
      const file = join(OUT, `${name}.${size.name}.png`);
      await page.screenshot({ path: file, fullPage: true });

      // The one thing worth failing on automatically: the page body must not
      // scroll sideways (docs/UI.md §7).
      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
      );
      if (overflow > 1) problems.push(`${name} @ ${size.width}px overflows by ${overflow}px`);
      console.log(`${overflow > 1 ? "OVERFLOW" : "ok      "} ${name} @ ${size.name}`);
    }
    await context.close();
  }
  await browser.close();
  return problems;
}

const externalBase = arg("base", null);
let fixture = null;
try {
  fixture = externalBase ? { base: externalBase, docId: arg("doc", null) } : await startFixture();
  const problems = await shoot(fixture.base, fixture.docId);
  console.log(`\nshots in ${OUT}`);
  if (problems.length) {
    console.log(`\n${problems.length} screen(s) scroll sideways - docs/UI.md §7 says the body never does:`);
    problems.forEach((p) => console.log(`  ${p}`));
    process.exitCode = 1;
  }
} finally {
  if (fixture?.server && !KEEP) {
    fixture.server.kill();
    rmSync(fixture.dataDir, { recursive: true, force: true });
  } else if (fixture?.server) {
    console.log(`\nleft running at ${fixture.base} (data in ${fixture.dataDir})`);
  }
}
