/**
 * The shapes of the reference tables and of a sizing result.
 *
 * Every table is one printed table from the owner's own copy of ABYC E-11,
 * copied into JSON with the page it came from. The engine never carries a
 * value of its own: what is not in a confirmed table is a blank, and a blank
 * names the value a person can supply instead.
 */

/** Where a number came from: a table and its page, or the person. */
export type Source = { table: string; title?: string; page: number } | { by: "you" };

export type TableStatus = "draft" | "confirmed" | "fixture";

export interface TableSource {
  document: string;
  edition?: string;
  table?: string;
  page: number;
  /** The document's id inside the desktop app, when it was imported there. */
  document_id?: string;
}

interface TableBase {
  id: string;
  title: string;
  status: TableStatus;
  source: TableSource;
  /** Cells a person typed rather than copied: "row/column" -> "you". */
  edits?: Record<string, string>;
}

export interface ConstantsTable extends TableBase {
  kind: "constants";
  values: { K_copper: { value: number; page: number } };
  formula_as_printed?: string;
  /** Whether the printed formula's L is the round trip or one way. */
  length_definition: "round_trip" | "one_way";
}

export interface CircularMilsTable extends TableBase {
  kind: "circular_mils";
  rows: { size_awg: string; circular_mils: number; mm2?: number | null; page: number }[];
}

export interface AmpacityTable extends TableBase {
  kind: "ampacity";
  /** Insulation temperature rating (°C) -> unit, e.g. {"105": "A"}. */
  columns: Record<string, string>;
  rows: { size_awg: string; values: Record<string, number | null>; page: number }[];
}

export interface BundlingTable extends TableBase {
  kind: "bundling";
  rows: { min_conductors: number; max_conductors: number | null; factor: number; page: number }[];
}

export interface VoltageDropGrid extends TableBase {
  kind: "voltage_drop_grid";
  nominal_voltage: number;
  drop_percent: number;
  length_unit: "ft" | "m";
  length_definition: "round_trip" | "one_way";
  lengths: number[];
  rows: { current: number; page: number; sizes: Record<string, string | null> }[];
}

export interface FuseClassesTable extends TableBase {
  kind: "fuse_classes";
  rows: { class: string; interrupting_rating_a: number; voltage_rating_v?: number | null; suits: string[]; source: { document: string; page: number } }[];
}

export type E11Table = ConstantsTable | CircularMilsTable | AmpacityTable | BundlingTable | VoltageDropGrid | FuseClassesTable;

/** The ids the engine looks for. A missing one is a blank, not an error. */
export const TABLE_IDS = [
  "constants",
  "circular_mils",
  "ampacity_outside_engine_space",
  "ampacity_inside_engine_space",
  "bundling_factors",
  "voltage_drop_3pct",
  "voltage_drop_10pct",
  "fuse_classes",
] as const;
export type TableId = (typeof TABLE_IDS)[number];

export interface E11Tables {
  byId: Partial<Record<TableId, E11Table>>;
  /** True when any loaded table is the synthetic fixture. */
  fixture: boolean;
}

/** What a person can supply when a table does not cover the case. */
export interface Ask {
  /** The `own` field that answers this blank, e.g. "own.ampacity_a". */
  field: string;
  unit: string | null;
  prompt: string;
}

export interface Blank {
  value: null;
  reason: string;
  ask?: Ask;
}

export interface CircuitInputs {
  system_voltage: number;
  current: number;
  /** One-way length from the source to the load. */
  length: number;
  length_unit: "m" | "ft";
  max_drop_percent: number;
  insulation_rating_c: number;
  engine_space: boolean;
  /** Current-carrying conductors bundled together, this circuit's two included. */
  bundled_conductors: number;
  /** A key of DEVICE_PROFILES. */
  load_type: string;
  /** Prospective short-circuit current of the source, from its datasheet. */
  short_circuit_a?: number | null;
  /** The maker's own fuse rating for the device, if it states one. */
  manufacturer_fuse_a?: number | null;
}

/** Values a person typed in answer to a blank. Each one is reported as "you". */
export interface OwnValues {
  /** Allowable current, from the page, of the size the voltage-drop step chose. */
  ampacity_a?: number | null;
  bundling_factor?: number | null;
  k?: number | null;
  short_circuit_a?: number | null;
}

export interface SizePick {
  size_awg: string | null;
  reason?: string;
  source?: Source;
}

export interface CircuitResult {
  conductor: {
    size_awg: string | null;
    size_mm2: number | null;
    metric_standard_mm2: number | null;
    parallel: number;
    governed_by: "voltage_drop" | "ampacity" | "printed_table" | null;
    voltage_drop: { cm_required: number | null; size_awg: string | null; reason?: string; source?: Source };
    printed_table: { size_awg: string | null; reason?: string; source?: Source };
    ampacity: { size_awg: string | null; ampacity_a: number | null; bundling_factor: number | null; reason?: string; source?: Source };
    drop_at_size: { volts: number | null; percent: number | null; reason?: string };
  };
  protection: {
    min_a: number | null;
    fuse_a: number | null;
    fits_conductor: boolean | null;
    conductor_ampacity_a: number | null;
    characteristic: string | null;
    guidance: string;
    reason?: string;
    interrupting: { required_a: number | null; classes: { class: string; interrupting_rating_a: number; suits_load: boolean; source: { document: string; page: number } }[]; reason?: string; ask?: Ask };
  };
  reminders: CheatSheetEntry[];
  blanks: { field: string; reason: string; ask?: Ask }[];
  steps: string[];
  fixture: boolean;
}

export interface CheatSheetEntry {
  topic: string;
  rule: string;
  clause: string;
  page: number;
  applies_to: string[];
  status?: "draft" | "confirmed";
}

export interface CheatSheet {
  source: { document: string; edition?: string };
  entries: CheatSheetEntry[];
}
