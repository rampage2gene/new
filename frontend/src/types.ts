export type BBox = [number, number, number, number];

export interface DocumentSummary {
  id: string;
  filename: string;
  title: string;
  file_type: string;
  mime_type: string;
  size_bytes: number;
  status: "queued" | "processing" | "ready" | "failed";
  progress?: string | null;
  error?: string | null;
  page_count: number;
  ocr_pages: number;
  embedded_text_pages: number;
  manufacturer?: string | null;
  product?: string | null;
  model_number?: string | null;
  document_type?: string | null;
  revision?: string | null;
  publication_date?: string | null;
  equipment_types: string[];
  stats: {
    entities?: Record<string, number>;
    qc_flags?: number;
    critical_flags?: number;
    chunks?: number;
    avg_ocr_confidence?: number | null;
    ocr_engines?: string[];
    verification?: VerificationReport | null;
    to_fill?: number;
    verified_by_user?: number;
    export_dir?: string;
    export_files?: string[];
  };
  uploaded_at?: string | null;
  processed_at?: string | null;
}

export interface SectionOutline { title: string; level: number; page: number; bbox: BBox }
export interface DocumentStructure {
  sections?: SectionOutline[];
  warnings?: { page: number; text: string; section?: string | null; bbox?: BBox }[];
  figures?: { page: number; caption: string; section?: string | null; bbox?: BBox }[];
  tables?: { page: number; section?: string | null; rows: string[][]; bbox: BBox; header: string[] }[];
  diagram_pages?: number[];
}

export interface PageSummary {
  page_number: number;
  width: number;
  height: number;
  text_source: "embedded" | "ocr" | "none";
  ocr_confidence?: number | null;
  is_diagram: boolean;
  diagram_score: number;
  page_label?: string | null;
  char_count: number;
}

export interface DocumentDetail extends DocumentSummary { structure: DocumentStructure; pages: PageSummary[] }

export interface Block {
  id: string;
  page_number: number;
  order_index: number;
  block_type: string;
  text: string;
  bbox: BBox;
  section?: string | null;
  section_level: number;
  source: string;
  confidence: number;
  table?: { rows: string[][] } | null;
  words?: { t: string; c: number; bbox: BBox }[] | null;
}

export interface PageData extends PageSummary { document_id: string; text: string; blocks: Block[] }

export interface EntityFlag { type: string; severity?: string; message: string }

/** How a value was checked: the verification ladder's verdict. */
export type VerificationStatus =
  | "confirmed" | "corrected" | "ai_confirmed" | "ai_corrected" | "user" | "to_fill" | "unverified" | "single" | "embedded";
export interface Verification {
  status: VerificationStatus;
  note?: string;
  readings?: Record<string, string | null>;
  original?: string | null;
  at?: string;
}
export interface VerificationReport {
  checked: number;
  confirmed: number;
  corrected: number;
  to_fill: number;
  unverified: number;
  reader1?: string | null;
  reader2?: string | null;
  ai?: string | null;
}

export interface Entity {
  id: string;
  document_id: string;
  document_name?: string | null;
  entity_type: string;
  value: number | null;
  unit: string | null;
  value_text: string;
  raw_text?: string;
  qualifier: string | null;
  application: string | null;
  circuit: string | null;
  equipment: string | null;
  equipment_model: string | null;
  device_type: string | null;
  page: number;
  section: string | null;
  snippet: string;
  block_id?: string | null;
  bbox: BBox;
  confidence: number;
  ocr_confidence: number | null;
  is_critical: boolean;
  verified: boolean;
  verification: Verification;
  flags: EntityFlag[];
  extra: Record<string, unknown>;
}

export interface SpecGroup { key: string; label: string; count: number; items: any[] }
export interface SpecExtraction { document: { id: string; name: string; manufacturer?: string | null; model_number?: string | null; document_type?: string | null }; groups: SpecGroup[]; critical_flags: number }

export interface QCFlag { id: string; document_id: string; entity_id?: string | null; page?: number | null; severity: "critical" | "warning" | "info"; flag_type: string; message: string; details: Record<string, unknown>; resolved: boolean }

export interface SearchHit {
  chunk_id: string;
  document_id: string;
  document_name: string;
  page_number: number;
  section: string | null;
  text: string;
  bbox: BBox;
  score: number;
  sources: string[];
  highlights: string[];
  source_scores?: Record<string, unknown>;
  strong?: boolean;
}
export interface SearchResponse { query: { raw: string; entity_types: string[]; value: number | null; unit: string | null; expansions: Record<string, string[]> }; hits: SearchHit[] }

export interface Citation { passage: number; document_id: string; document_name: string; page: number; section: string | null; chunk_id: string; quote: string; note?: string | null; bbox: BBox; verified: boolean }
export interface Passage { passage: number; chunk_id: string; document_id: string; document_name: string; page: number; section: string | null; text: string; bbox: BBox; score: number; sources: string[]; highlights: string[] }
export interface Answer {
  mode: "ai" | "extractive" | "no_results";
  answer: string;
  status: "found" | "partial" | "not_found" | "unverified";
  answer_kind: string;
  citations: Citation[];
  conflicts: string[];
  verification_warnings: string[];
  follow_up_questions?: string[];
  entities: Entity[];
  passages: Passage[];
  ai_error?: string;
}

/** `answers`: an input a person fills in when a result came back blank; names the blank it answers and is shown only then. */
export interface InputSpec { key: string; label: string; unit: string | null; kind: "number" | "select" | "text"; required: boolean; default: any; options: { value: string; label: string }[] | null; help: string | null; entity_types: string[]; qualifiers: string[]; answers?: string | null }
export interface CalculatorSpec { id: string; name: string; category: string; description: string; formula: string; inputs: InputSpec[]; outputs: { key: string; label: string; unit?: string }[]; notes: string[] }
export interface SourceRef { document_id?: string | null; document_name?: string | null; page?: number | null; section?: string | null; entity_id?: string | null; snippet?: string | null; confidence?: number | null }
export interface CalcInputValue { value: any; unit?: string | null; source?: SourceRef | null; origin?: string }
export interface CalcResultValue { key: string; label: string; value: any; unit: string | null; classification: string; note?: string | null; group?: string | null }
/** A blank result is a request: which result, why, and the input that answers it (null when the fix is elsewhere, e.g. the reference tables). */
export interface CalcAsk { field: string; reason: string; input_key: string | null; unit: string | null; prompt: string; kind?: "number" | "text" | null }
export interface CheatSheetEntry { topic: string; rule: string; clause: string; page: number; applies_to: string[]; status?: "draft" | "confirmed" }
export interface CalcResult { calculator_id: string; calculator_name: string; formula: string; inputs: Record<string, CalcInputValue>; steps: string[]; results: CalcResultValue[]; assumptions: string[]; warnings: string[]; sources: SourceRef[]; asks?: CalcAsk[]; reminders?: CheatSheetEntry[]; classification: string; disclaimer: string }

/** The owner's ABYC E-11 reference tables, as the app sees them. */
export type ReferenceTableId = "constants" | "circular_mils" | "ampacity_outside_engine_space" | "ampacity_inside_engine_space" | "bundling_factors" | "voltage_drop_3pct" | "voltage_drop_10pct" | "fuse_classes" | "cable_dimensions" | "heat_shrink" | "lugs";
export interface ReferenceTableRow { id: ReferenceTableId; kind: string; title: string | null; page: number | null; status: "missing" | "draft" | "confirmed" | "fixture"; rows: number; origin: "yours" | "bundled" | null; document_id?: string | null; layout: { title: string; columns?: string[] } }
export interface ReferenceStatus { installed: boolean; confirmed: string[]; missing: string[]; fixture: boolean; folders: { yours: string; bundled: string }; tables: ReferenceTableRow[]; cheatsheet: { entries: number; origin: string | null } }
/** One table file; the shape depends on `kind` (see packages/e11-calc/schema). */
export interface ReferenceTable { id: ReferenceTableId; kind: string; title?: string; status: "missing" | "draft" | "confirmed" | "fixture"; source?: { document: string; edition?: string; table?: string; page?: number; document_id?: string }; edits?: Record<string, string>; origin?: string | null; layout: { title: string; columns?: string[] }; [key: string]: any }
export interface DetectedTable { page: number; table_index: number; header: string[]; rows: number; section?: string | null }
export interface CheatSheetResponse { source: { document: string; edition?: string } | null; entries: CheatSheetEntry[]; markdown: string; origin: string | null }

export interface DiagramComponent { id: string; type: string; label: string; rating?: string | null; confidence: "confirmed" | "high" | "possible" | "unknown"; bbox_pct?: number[] | null }
export interface DiagramConnection { from_id: string; to_id: string; polarity: string; circuit: string; direction: string; protection: { type: string; rating?: string | null; confidence: string }[]; confidence: string; note?: string | null }
export interface DiagramAnalysis { id: string; document_id: string; page: number; engine: string; diagram_type: string; title?: string | null; system_voltage?: string | null; components: DiagramComponent[]; connections: DiagramConnection[]; unreadable_regions: string[]; notes: string[]; confidence_legend: Record<string, string> }

export interface CompareResult {
  documents: { id: string; name: string; manufacturer?: string | null; model?: string | null; document_type?: string | null; equipment_types: string[] }[];
  table: { key: string; label: string; unit: string | null; cells: { document_id: string; values: Entity[] }[] }[];
  conflicts: { type: string; severity: string; message: string; classification: string; sources: { document_id: string; document_name: string; page: number; section?: string | null; value_text: string; entity_id: string; bbox: BBox }[] }[];
  note: string;
  answer?: Answer;
}

export interface InvoiceLine { description: string; quantity: number | null; unit: string | null; unit_price: number | null; total: number | null; page: number; bbox: BBox; confidence: number }
export interface Invoice { id: string; document_id: string; document_name: string; vendor: string | null; invoice_number: string | null; invoice_date: string | null; currency: string | null; subtotal: number | null; tax: number | null; total: number | null; line_items: InvoiceLine[]; confidence: number }

export interface Status { ocr_engine: string; ocr_readers?: string[]; ai_available: boolean; ai_model: string | null; embedding_provider: string; version: string; max_upload_mb?: number }

export interface OcrEngines { configured: string; tesseract: boolean; rapidocr: boolean; rapidocr_version: string | null; rapidocr_error: string | null; readers: string[] }

export interface DiagnosticsInfo {
  version: string;
  platform: string;
  machine: string;
  python: string;
  frozen: boolean;
  data_dir: string;
  log_path: string;
  log_exists: boolean;
  log_size: number;
  ocr_engine: string;
  ocr_engines?: OcrEngines;
  exports_dir?: string;
  tesseract_path: string | null;
  tesseract_version: string | null;
  ai_available: boolean;
  ai_model: string | null;
  embedding_provider: string;
  max_upload_mb: number;
  /** What the inbox folder holds: files waiting, and files it could not read. */
  inbox?: { folder: string; waiting: number; failed: { name: string; reason: string }[] };
  phone_access?: boolean;
  phone_key_required?: boolean;
  documents: { total: number; ready: number; failed: number };
}

/** What a phone on the same Wi-Fi needs in order to reach this computer. */
export interface LanInfo {
  enabled: boolean;
  protected: boolean;
  computer: string;
  port: number;
  urls: string[];
}

export interface Highlight { bbox: BBox; kind: "primary" | "secondary" | "entity" | "component"; label?: string; confidence?: string }

export interface CalculatorPrefill { calculatorId: string; inputs: Record<string, CalcInputValue> }
