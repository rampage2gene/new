/**
 * The shapes of the reference tables and of a sizing result.
 *
 * Every table is one printed table from the owner's own copy of ABYC E-11,
 * copied into JSON with the page it came from. The engine never carries a
 * value of its own: what is not in a confirmed table is a blank, and a blank
 * names the value a person can supply instead.
 */

/** Where a number came from: a table and its page, or the person. */
export type Source = { table: string; title?: string; page: number } | { table: string; title?: string; document: string; page?: number | null } | { by: "you" };

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

/**
 * The three catalog tables are not from E-11: the owner types them from the
 * cable maker's, the tubing maker's and the lug maker's catalogs. A page is
 * optional on them; the source document is not.
 */
export interface CableDimensionsTable extends TableBase {
  kind: "cable_dimensions";
  diameter_unit: "mm" | "in";
  rows: { size_awg: string; outside_diameter: number; page?: number | null }[];
}

export interface HeatShrinkTable extends TableBase {
  kind: "heat_shrink";
  diameter_unit: "mm" | "in";
  /** supplied_id: inside diameter as supplied; recovered_id: after full shrink. */
  rows: { size: string; supplied_id: number; recovered_id: number; adhesive?: boolean; page?: number | null }[];
}

export interface LugsTable extends TableBase {
  kind: "lugs";
  /** Unit of barrel_od; mm when absent. */
  diameter_unit?: "mm" | "in";
  rows: { size_awg: string; stud: string; part: string; barrel_od?: number | null; crimp_die?: string | null; page?: number | null }[];
}

export type E11Table = ConstantsTable | CircularMilsTable | AmpacityTable | BundlingTable | VoltageDropGrid | FuseClassesTable | CableDimensionsTable | HeatShrinkTable | LugsTable;

/** Tables whose rows cite a datasheet or catalog rather than a page of the standard. */
export const CATALOG_KINDS = ["fuse_classes", "cable_dimensions", "heat_shrink", "lugs"] as const;

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
  "cable_dimensions",
  "heat_shrink",
  "lugs",
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
  /** What the box takes; a number when absent. */
  kind?: "number" | "text";
}

export interface Blank {
  value: null;
  reason: string;
  ask?: Ask;
}

export interface CircuitInputs {
  system_voltage: number;
  current: number;
  /** The length, one way (the default) or the whole loop, per length_basis. */
  length: number;
  length_unit: "m" | "ft";
  /** "loop": length is the whole run, source to load and back; "one_way" when absent. */
  length_basis?: "loop" | "one_way";
  max_drop_percent: number;
  insulation_rating_c: number;
  engine_space: boolean;
  /** Current-carrying conductors bundled together, this circuit's two included. */
  bundled_conductors: number;
  /** A key of DEVICE_PROFILES. */
  load_type: string;
  /** A key of CIRCUIT_TYPES; adds its reminder tags. */
  circuit_type?: string | null;
  /** The terminal stud the lugs land on, as the lug catalog names it (5/16, M8...). */
  stud_size?: string | null;
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
  /** The cable's outside diameter, from its maker, in mm. */
  cable_od_mm?: number | null;
  heat_shrink_size?: string | null;
  lug_part?: string | null;
  crimp_die?: string | null;
  /** The stud size, when it was not given as an input. */
  stud?: string | null;
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
  fittings: FittingsResult;
  reminders: CheatSheetEntry[];
  blanks: { field: string; reason: string; ask?: Ask }[];
  steps: string[];
  fixture: boolean;
}

/** The fittings for the chosen conductor, each from the owner's catalog tables or the person. */
export interface FittingsResult {
  cable_od: { value: number | null; unit: "mm" | "in" | null; mm: number | null; reason?: string; source?: Source };
  heat_shrink: { size: string | null; supplied_id: number | null; recovered_id: number | null; unit: "mm" | "in" | null; adhesive: boolean | null; reason?: string; source?: Source };
  lug: { part: string | null; stud: string | null; crimp_die: string | null; reason?: string; die_reason?: string; source?: Source; die_source?: Source };
  /** Counts for the set, arithmetic from the parallel count and the loop length. */
  quantities: { cables: number; lugs: number; heat_shrink_pieces: number; cable_length: number; length_unit: "m" | "ft"; note: string } | null;
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
