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
  stats: { entities?: Record<string, number>; qc_flags?: number; critical_flags?: number; chunks?: number; avg_ocr_confidence?: number | null };
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

export interface InputSpec { key: string; label: string; unit: string | null; kind: "number" | "select" | "text"; required: boolean; default: any; options: { value: string; label: string }[] | null; help: string | null; entity_types: string[]; qualifiers: string[] }
export interface CalculatorSpec { id: string; name: string; category: string; description: string; formula: string; inputs: InputSpec[]; outputs: { key: string; label: string; unit?: string }[]; notes: string[] }
export interface SourceRef { document_id?: string | null; document_name?: string | null; page?: number | null; section?: string | null; entity_id?: string | null; snippet?: string | null; confidence?: number | null }
export interface CalcInputValue { value: any; unit?: string | null; source?: SourceRef | null; origin?: string }
export interface CalcResultValue { key: string; label: string; value: any; unit: string | null; classification: string; note?: string | null }
export interface CalcResult { calculator_id: string; calculator_name: string; formula: string; inputs: Record<string, CalcInputValue>; steps: string[]; results: CalcResultValue[]; assumptions: string[]; warnings: string[]; sources: SourceRef[]; classification: string; disclaimer: string }

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

export interface Status { ocr_engine: string; ai_available: boolean; ai_model: string | null; embedding_provider: string; version: string }

export interface Highlight { bbox: BBox; kind: "primary" | "secondary" | "entity" | "component"; label?: string; confidence?: string }

export interface CalculatorPrefill { calculatorId: string; inputs: Record<string, CalcInputValue> }
