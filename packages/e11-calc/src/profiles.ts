/**
 * How loads behave and what protects them: industry guidance, not E-11 table
 * values, and labelled as such in every result. profiles/device_profiles.json
 * is the contract; a test asserts this copy equals it, and the desktop app's
 * Python copy is tested against the same file.
 */
export interface DeviceProfile {
  label: string;
  /** Multiply the continuous load by this to get the minimum fuse rating. */
  factor: number;
  surge_note: string;
  /** The fuse or breaker characteristic that suits this load. */
  char: string;
}

export const GUIDANCE_LABEL = "industry guidance, verify with the maker";

export const STANDARD_FUSE_SIZES_A: number[] = [1, 2, 3, 5, 7.5, 10, 15, 20, 25, 30, 35, 40, 50, 60, 70, 80, 90, 100, 110, 125, 150, 175, 200, 225, 250, 300, 350, 400, 450, 500, 600, 700, 800];
export const STANDARD_BREAKER_SIZES_A: number[] = [5, 10, 15, 16, 20, 25, 30, 32, 40, 50, 60, 63, 70, 80, 100, 125, 150, 175, 200, 225, 250, 300, 400];

export const DEVICE_PROFILES: Record<string, DeviceProfile> = {
  inverter: { label: "Inverter / inverter-charger", factor: 1.25, surge_note: "Inverters draw large surge currents on motor/compressor start-up; use a time-delay / high-interrupt fuse (e.g. Class T or MRBF for large banks).", char: "time-delay, high interrupt capacity (Class T recommended for banks able to deliver >5 kA fault current)" },
  battery_main: { label: "Battery bank main / positive feed", factor: 1.0, surge_note: "The main fuse protects the conductor, not the load; it is sized to the cable ampacity.", char: "high interrupt capacity matched to the bank's prospective short-circuit current (Class T for lithium/large AGM banks; ANL/MEGA only where the AIC is adequate)" },
  battery_charger: { label: "Battery charger output", factor: 1.25, surge_note: "Charger output current is limited by the charger; size at 125 % of rated output.", char: "standard blade/ANL/MRBF per manufacturer" },
  alternator: { label: "Alternator output", factor: 1.25, surge_note: "Never open an alternator output circuit while running (load-dump destroys diodes). ABYC requires overcurrent protection within 7\" (178 mm) unless self-limiting; some manufacturers advise against fusing the B+ lead - follow their documentation.", char: "MRBF/ANL/MEGA sized ≥125 % of rated output, or per manufacturer" },
  dc_dc: { label: "DC-DC charger / converter", factor: 1.25, surge_note: "Protect both input and output leads; input current exceeds output current when stepping voltage up.", char: "per manufacturer, typically blade/MIDI" },
  solar: { label: "Solar controller (PV or battery side)", factor: 1.25, surge_note: "PV side: 1.25 × Isc × 1.25 (irradiance); battery side: 1.25 × controller rated output.", char: "DC-rated fuse or breaker" },
  motor: { label: "Motor (windlass, thruster, pump)", factor: 1.5, surge_note: "Locked-rotor / inrush current is 3–6× running current; use a slow-blow fuse or thermal breaker per the motor manufacturer's rating. Windlass/thruster breakers are usually specified by the manufacturer.", char: "slow-blow / thermal breaker; manufacturer's rating takes precedence" },
  capacitive: { label: "Capacitive / electronic load", factor: 1.25, surge_note: "Input capacitors cause a brief inrush; use time-delay characteristics.", char: "time-delay" },
  resistive: { label: "Resistive load (heater, lights)", factor: 1.25, surge_note: "No significant inrush.", char: "fast-acting or standard" },
  electronics: { label: "Electronics / instruments", factor: 1.25, surge_note: "Follow the equipment manufacturer's fuse rating; small fuses protect the wire.", char: "fast-acting (blade/glass) per manufacturer" },
};

export function nextStandard(value: number, sizes: number[] = STANDARD_FUSE_SIZES_A): number | null {
  for (const s of sizes) if (s >= value - 1e-9) return s;
  return null;
}

export function prevStandard(value: number, sizes: number[] = STANDARD_FUSE_SIZES_A): number | null {
  let best: number | null = null;
  for (const s of sizes) if (s <= value + 1e-9) best = s;
  return best;
}
