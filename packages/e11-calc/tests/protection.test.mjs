import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { DEVICE_PROFILES, STANDARD_FUSE_SIZES_A, STANDARD_BREAKER_SIZES_A, fuseForConductor, interruptingCheck, isBlank, CIRCUIT_TYPES } from "../dist/index.js";
import { HERE, fixtureTables } from "./helpers.mjs";

const T = fixtureTables();

test("the TypeScript profiles equal profiles/device_profiles.json, the contract shared with the app", () => {
  const json = JSON.parse(readFileSync(join(HERE, "..", "profiles", "device_profiles.json"), "utf8"));
  assert.deepEqual(DEVICE_PROFILES, json.device_profiles);
  assert.deepEqual(STANDARD_FUSE_SIZES_A, json.standard_fuse_sizes_a);
  assert.deepEqual(STANDARD_BREAKER_SIZES_A, json.standard_breaker_sizes_a);
  assert.deepEqual(CIRCUIT_TYPES, json.circuit_types);
  for (const c of Object.values(CIRCUIT_TYPES)) assert.ok(DEVICE_PROFILES[c.load_type], `${c.label}: load profile ${c.load_type}`);
});

test("a fuse is at least the load times its factor and never above the conductor", () => {
  const f = fuseForConductor(10, "resistive", 60);
  assert.deepEqual([f.min_a, f.fuse_a, f.fits_conductor, f.max_for_conductor_a], [12.5, 15, true, 60]);
  assert.match(f.guidance, /industry guidance/);
  const g = fuseForConductor(30, "motor", 30);
  assert.deepEqual([g.min_a, g.fuse_a, g.fits_conductor], [45, null, false]);
  assert.match(g.reason, /would exceed the conductor's 30 A/);
  const m = fuseForConductor(10, "electronics", 60, 20);
  assert.deepEqual([m.min_a, m.fuse_a, m.manufacturer_a], [20, 20, 20]);
  const u = fuseForConductor(10, "unknown_load", 60);
  assert.equal(u.min_a, 12.5);
});

test("interrupting capacity needs the source's short-circuit current, then lists the classes that qualify", () => {
  const b = interruptingCheck(null, "inverter", T);
  assert.ok(isBlank(b) && b.ask.field === "own.short_circuit_a");
  const r = interruptingCheck(3000, "inverter", T);
  assert.deepEqual(r.classes.map((c) => [c.class, c.suits_load]), [["Class X", true]]);
  const none = interruptingCheck(50000, "inverter", T);
  assert.match(none.reason, /No entered fuse class/);
  const own = interruptingCheck(null, "resistive", T, 1500);
  assert.deepEqual(own.source, { by: "you" });
  assert.deepEqual(own.classes.map((c) => c.class), ["Class Y", "Class X"]);
  const empty = interruptingCheck(3000, "inverter", { byId: {}, fixture: false });
  assert.ok(isBlank(empty) && /No fuse classes have been entered/.test(empty.reason) && !empty.ask);
});
