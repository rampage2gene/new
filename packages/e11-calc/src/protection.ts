/**
 * Overcurrent protection for the conductor the sizing step chose.
 *
 * A fuse protects the conductor, so it may never exceed the conductor's
 * derated ampacity; it must also be at least the load times its load-type
 * factor, rounded up to a standard size. Its interrupting rating must exceed
 * the source's prospective short-circuit current, which comes from the
 * battery datasheet - typed by the person, never estimated here.
 */
import type { Ask, Blank, E11Tables, FuseClassesTable } from "./schema.js";
import { usable } from "./loader.js";
import { DEVICE_PROFILES, GUIDANCE_LABEL, STANDARD_FUSE_SIZES_A, nextStandard, prevStandard, type DeviceProfile } from "./profiles.js";
import { round } from "./sizing.js";

export interface FusePick {
  min_a: number;
  fuse_a: number | null;
  fits_conductor: boolean;
  conductor_ampacity_a: number;
  /** The largest standard size the conductor allows. */
  max_for_conductor_a: number | null;
  characteristic: string;
  surge_note: string;
  guidance: string;
  /** Set when the maker's stated rating was used as the minimum. */
  manufacturer_a: number | null;
  reason?: string;
}

const DEFAULT_PROFILE: DeviceProfile = { label: "Load", factor: 1.25, surge_note: "No load type given; 125 % of the continuous load is used.", char: "per the equipment maker" };

export function fuseForConductor(loadA: number, loadType: string, conductorAmpacityA: number, manufacturerFuseA?: number | null, profiles: Record<string, DeviceProfile> = DEVICE_PROFILES, sizes: number[] = STANDARD_FUSE_SIZES_A): FusePick {
  const profile = profiles[loadType] ?? DEFAULT_PROFILE;
  const min = manufacturerFuseA != null && manufacturerFuseA > 0 ? manufacturerFuseA : round(loadA * profile.factor, 2);
  const standard = nextStandard(min, sizes);
  const maxFor = prevStandard(conductorAmpacityA, sizes);
  const fits = standard != null && standard <= conductorAmpacityA + 1e-9;
  const pick: FusePick = {
    min_a: min, fuse_a: fits ? standard : null, fits_conductor: fits, conductor_ampacity_a: conductorAmpacityA, max_for_conductor_a: maxFor,
    characteristic: profile.char, surge_note: profile.surge_note, guidance: GUIDANCE_LABEL,
    manufacturer_a: manufacturerFuseA != null && manufacturerFuseA > 0 ? manufacturerFuseA : null,
  };
  if (!fits) {
    pick.reason = standard == null
      ? `${min} A is above the largest standard fuse size (${sizes[sizes.length - 1]} A).`
      : `A ${standard} A fuse (the next standard size above ${min} A) would exceed the conductor's ${conductorAmpacityA} A after derating; the largest size this conductor allows is ${maxFor ?? "none"} A, below the load's minimum. Use a larger conductor.`;
  }
  return pick;
}

export interface InterruptingCheck {
  required_a: number;
  source: { by: "you" } | { given: true };
  classes: { class: string; interrupting_rating_a: number; voltage_rating_v: number | null; suits_load: boolean; source: { document: string; page: number } }[];
  reason?: string;
}

export function interruptingCheck(shortCircuitA: number | null | undefined, loadType: string, tables: E11Tables, own?: number | null): InterruptingCheck | Blank {
  const sc = own ?? shortCircuitA ?? null;
  const ask: Ask = { field: "own.short_circuit_a", unit: "A", prompt: "Type the prospective short-circuit current of the source (the battery bank) from its datasheet, in A. The fuse's interrupting rating must be above it." };
  if (sc == null || sc <= 0) return { value: null, reason: "The source's short-circuit current was not given, so no fuse class can be checked for interrupting capacity.", ask };
  const table = usable<FuseClassesTable>(tables, "fuse_classes");
  if (!table || table.rows.length === 0) return { value: null, reason: "No fuse classes have been entered yet. Add each class you use, with its interrupting rating from the datasheet, under Reference." };
  const classes = table.rows
    .filter((r) => r.interrupting_rating_a >= sc - 1e-9)
    .map((r) => ({ class: r.class, interrupting_rating_a: r.interrupting_rating_a, voltage_rating_v: r.voltage_rating_v ?? null, suits_load: r.suits.includes(loadType), source: r.source }))
    .sort((a, b) => Number(b.suits_load) - Number(a.suits_load) || a.interrupting_rating_a - b.interrupting_rating_a);
  const out: InterruptingCheck = { required_a: sc, source: own != null ? { by: "you" } : { given: true }, classes };
  if (classes.length === 0) out.reason = `No entered fuse class has an interrupting rating of at least ${sc} A.`;
  return out;
}
