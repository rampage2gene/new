# Marine Electrical Document Intelligence — Engineering Specification

| | |
|---|---|
| Spec version | 0.1.0 (matches application version reported by `GET /api/status`) |
| Status | As-built for sections 1–17; section 18 is the roadmap (all items **Planned**) |
| Companion documents | [API.md](API.md) (endpoint contracts), [DATA_MODEL.md](DATA_MODEL.md) (storage and JSON shapes), [README](../README.md) (setup) |
| Source of truth | The code under `backend/app` and `frontend/src`. Where this document and the code disagree, the code is right and this document has a bug; fix both in the same PR. |

## 1. Purpose and scope

The application turns marine electrical and technical documentation (installation manuals, datasheets, wiring diagrams, battery/BMS/inverter/charger/alternator documentation, scans, photographs, invoices and parts lists) into a structured, searchable, traceable knowledge base. It answers technical questions from the uploaded documents, extracts specifications into structured tables, compares equipment across documents, and feeds documented values into electrical calculators.

This specification describes the behaviour and contracts of the system as delivered on the `claude/marine-electrical-doc-intelligence-qr5xfx` branch (PR #1), and the phased roadmap toward a marine electrical AI copilot. Setup and operation are in the README.

## 2. Goals, non-goals and guiding principles

### Goals

- G1 Ingest PDFs with embedded text, scanned PDFs, and photographs/scans of pages, with no manual choice of path.
- G2 Recognise technical electrical notation accurately, in particular never confusing `4 AWG` with `4/0 AWG`, `48 V` with `480 V`, or `A` with `AWG`/`AC`/`Ah`.
- G3 Represent document structure (title, manufacturer, model, revision, sections, tables, warnings, figures, diagram pages) rather than treating pages as flat text.
- G4 Extract technical entities (wire sizes, fuses, breakers, voltage, current, power, torque, temperature, equipment) with full source traceability: document, page, section, snippet and bounding box.
- G5 Validate critical values and flag anything that needs checking against the original page.
- G6 Answer technical questions with verified citations, saying "not found" rather than guessing.
- G7 Keep manufacturer-documented values visibly distinct from calculations, assumptions and interpretation everywhere (answers, comparisons, calculators).
- G8 Let each pipeline component be replaced independently (OCR engine, embedding provider, AI model, calculators).

### Non-goals (this version)

- Multi-user accounts, authentication, or per-project workspaces.
- Editing documents or writing annotations back into PDFs.
- Generating wiring diagrams or full system designs (roadmap, §18).
- Guaranteeing standards compliance: reference tables are typical published values and are labelled as such.

### Principles enforced in code

| Principle | Enforcement |
|---|---|
| Every technical statement is traceable | `Entity` rows carry page/section/bbox/snippet; answers carry citations verified against passage text (§11.3). |
| Never fabricate | The AI prompt forbids it and the extractive fallback only returns documented passages (§11.4). Missing data yields the literal phrase "I could not find this specification in the uploaded documentation." |
| Documented ≠ calculated | Calculator results carry a `classification` (§12.2); comparison conflicts are labelled `engineering_analysis`; answers carry `answer_kind`. |
| Uncertainty is visible | Entity `confidence` and `ocr_confidence`, QC flags, diagram confidence tiers, search `strong` flag, answer status `unverified`. |
| Modularity | Protocols `OCREngine` (`app/ocr/base.py`), `EmbeddingProvider` (`app/search/semantic.py`), calculator registry (`app/calculators/modules.py`), single AI client wrapper (`app/ai/client.py`). |

## 3. Glossary

| Term | Meaning |
|---|---|
| Document | One uploaded file (PDF or image). Identified by a 32-hex id. |
| Page | One page of a document; images are single-page documents. Geometry is in **page units**: PDF points (1/72 in) for PDFs, source-image pixels for images. |
| Block | A unit of extracted text with a bounding box, a `block_type` (§7.1), a section, a source (`embedded` or `ocr`) and a confidence. Word boxes are attached when available. |
| Chunk | The retrieval unit for search: consecutive blocks on one page within one section, capped at 700 characters; tables and warnings are standalone chunks. |
| Entity | A structured technical value extracted from a block (§8), e.g. `fuse 300 A, Class T, application "Battery cable", page 3`. |
| Qualifier | A word near a value that scopes it: `continuous`, `peak`, `surge`, `maximum`, `minimum`, `nominal`, `recommended`, `required`, `input`, `output`, `charging`, `idle`, `short_circuit`, `cutoff`, `operating`, `storage`, `derating`. |
| Application | What the value applies to, e.g. `Battery cable`, `AC input`, or a table row label. |
| Circuit | `dc`, `ac`, `ac/dc`, `control` or null, inferred from context. |
| Confidence | Entity-level 0–1 score combining pattern certainty with OCR word confidence (§8.6). |
| OCR confidence | Minimum Tesseract word confidence (0–1) over the words that form a value; null for embedded text. |
| QC flag | A verification item produced by the quality-control layer (§9). Flags never change a value. |
| Citation | A reference from an answer to a passage: document, page, section, chunk id, verbatim quote, bbox, and whether the quote was verified. |
| Classification | Provenance label on a calculator output: `manufacturer_required`, `documented_value`, `calculated_estimate`, `recommended_pending_verification` (§12.2). |
| Strong hit | A search hit backed by a keyword match on at least half of the query groups, an entity match, or a semantic similarity ≥ 0.12 (§10.5). |

## 4. Requirements (as built)

Status: **I** implemented, **P** partial, **R** roadmap. "Test" names the pytest file/function or UI check that exercises the requirement.

### 4.1 Ingestion (ING)

| ID | Requirement | Status | Test / evidence |
|---|---|---|---|
| ING-1 | Accept one or more files per upload (PDF, PNG, JPEG, TIFF, BMP, GIF, WEBP), identified by magic bytes with extension fallback; reject other types with HTTP 415 and oversized files (default 200 MB) with HTTP 413. | I | `test_pipeline_api.py::test_text_pdf_is_understood`, `test_photo_is_ocrd` |
| ING-2 | Process uploads asynchronously in a worker pool and expose `status` (`queued`/`processing`/`ready`/`failed`) and a human-readable `progress` string. | I | Library page polling; `pipeline.py` |
| ING-3 | Per page, use embedded text when it is usable, otherwise render and OCR the page (§6.2). | I | `test_scanned_pdf_is_ocrd` (4 OCR pages, 0 embedded) |
| ING-4 | Render every page to PNG for the viewer and record page geometry. | I | `test_pages_blocks_and_images` |
| ING-5 | Support re-processing a document in place, replacing all derived data. | I | `POST /documents/{id}/reprocess` |
| ING-6 | Store originals, page renders and the index separately (§5.3). | I | `storage/files.py`, `config.py` |

### 4.2 OCR (OCR)

| ID | Requirement | Status | Test / evidence |
|---|---|---|---|
| OCR-1 | OCR engine is pluggable behind `OCREngine`; Tesseract is the default and `none` is a valid setting. | I | `ocr/engine.py` |
| OCR-2 | Word-level bounding boxes and confidences are preserved and converted to page units. | I | `test_scanned_pdf_is_ocrd` (OCR bbox within 15 pt of embedded bbox) |
| OCR-3 | Technical notation is normalised without losing the original text (§6.3). | I | `test_ocr_postprocess.py` |
| OCR-4 | Ambiguous readings (`4 0 AWG`, letter O in numbers, 3/8, 1/7, 0/6/9, 5/6) are detected and surfaced, not silently resolved. | I | `test_ocr_postprocess.py::test_awg_ambiguity_only_for_ambiguous_forms`, `test_qc.py` |
| OCR-5 | Only one OCR run executes at a time and Tesseract is limited to one OpenMP thread. | I | `ocr/tesseract.py` |

### 4.3 Document understanding (DOC)

| ID | Requirement | Status | Test / evidence |
|---|---|---|---|
| DOC-1 | Classify blocks as heading, paragraph, list, table, caption, warning, note, label, header, footer, page_number. | I | `test_pages_blocks_and_images` |
| DOC-2 | Assign every block to its enclosing section using a heading stack with numbered-heading levels. | I | `test_text_pdf_is_understood` (outline contains `2.1 Battery Bank`) |
| DOC-3 | Detect tables in vector PDFs and expose rows; use row labels and column headers as entity context. | I | `test_extraction.py::test_table_rows_provide_application_and_qualifier` |
| DOC-4 | Detect title, manufacturer, product, model number, document type, revision, publication date and equipment types. | P (manufacturer relies on a known-name list; see §17) | `test_text_pdf_is_understood` |
| DOC-5 | Score pages as diagrams from drawing count, label density, text density, keywords and image coverage. | I | `structure/layout.py::score_diagram_pages` |
| DOC-6 | Split headings that PDF extraction merged into neighbouring paragraphs. | I | `structure/layout.py::split_heading_lines` |

### 4.4 Entity extraction (EXT)

| ID | Requirement | Status | Test / evidence |
|---|---|---|---|
| EXT-1 | Extract wire sizes (AWG incl. `N/0` and `0000` forms, mm², kcmil), currents, voltages (with DC/AC), power, frequency, capacity, torque, resistance, temperature (incl. ranges), terminal sizes, clearances, equipment with model numbers. | I | `test_extraction.py` |
| EXT-2 | `4 AWG` and `4/0 AWG` are distinct; `48 V` is never read inside `480 V`; `A` is never read inside `AWG`, `AC`, `Ah`; units never span a line break. | I | `test_awg_never_confuses_4_and_4_0`, `test_voltage_never_reads_48_from_480`, `test_current_ignores_awg_ac_ah`, `test_units_do_not_cross_line_breaks` |
| EXT-3 | Currents are classified as `fuse`, `breaker` or `current` from sentence context; fuse class and breaker type are captured. | I | `test_fuse_breaker_current_classification_and_qualifiers` |
| EXT-4 | Qualifiers are chosen clause-aware and proximity-weighted (§8.3). | I | same |
| EXT-5 | Application, circuit, equipment and model are inferred from the sentence or table row. | I | `test_wire_sizes_with_application_and_source` |
| EXT-6 | Every entity keeps page, section, snippet, char offsets, word-level bbox, confidence and OCR confidence. | I | `test_spec_extraction_report` |
| EXT-7 | The Electrical Specification Extraction report groups entities into Equipment, Electrical ratings, Wire sizes, Fuse ratings, Breaker ratings, Installation requirements, Torque specifications, Temperature limits, Warnings. | I | `test_spec_extraction_report` |

### 4.5 Quality control (QC)

| ID | Requirement | Status | Test / evidence |
|---|---|---|---|
| QC-1 | Critical types are voltage, current, fuse, breaker, wire_size, torque, temperature. | I | `patterns.SAFETY_CRITICAL_TYPES` |
| QC-2 | OCR word confidence below the threshold (default 0.80) on a critical value raises a flag naming the alternative readings. | I | `test_qc.py::test_low_ocr_confidence_flags_alternatives` |
| QC-3 | Plausibility ranges per type raise `unit_out_of_range` / `nonstandard_*` flags. | I | `test_out_of_range_voltage` |
| QC-4 | A value that disagrees with a value repeated ≥2 times for the same application is flagged as a `discrepancy`; differing qualifiers are not discrepancies. | I | `test_discrepancy_against_repeated_value`, `test_different_qualifiers_are_not_discrepancies` |
| QC-5 | `N AWG` and `N/0 AWG` for the same application raise `awg_cross_reference`. | I | `test_awg_cross_reference`, `test_qc_flags_awg_cross_reference` |
| QC-6 | Flags can be marked verified/reopened from the UI. | I | `POST /documents/{id}/qc/{flag}/resolve` |

### 4.6 Search (SRCH)

| ID | Requirement | Status | Test / evidence |
|---|---|---|---|
| SRCH-1 | Keyword search over chunks with FTS5, with light stemming and prefix matching. | I | `test_search_keyword_semantic_entity` |
| SRCH-2 | Marine-electrical synonym expansion (e.g. `battery charger` → charger, charging system, shore power charger…). | I | same (`charging source` expansion) |
| SRCH-3 | Value queries ("every mention of 48 volts") match entities by value and unit. | I | same |
| SRCH-4 | Entity-type queries ("find all breaker ratings") match entities by type. | I | same |
| SRCH-5 | Section-aware boost when query terms appear in the section title. | I | `search/query.py::search` |
| SRCH-6 | Semantic ranking via a pluggable embedding provider; local hashed TF-IDF by default, Voyage AI when configured. | P (local provider is lexical) | `search/semantic.py` |
| SRCH-7 | Results are fused (reciprocal rank fusion) and each hit lists its evidence sources and a `strong` flag. | I | `search/query.py` |
| SRCH-8 | Every hit carries document, page, section, bbox and highlight terms so it can be opened and highlighted. | I | UI search → viewer deep link |

### 4.7 Question answering (QA)

| ID | Requirement | Status | Test / evidence |
|---|---|---|---|
| QA-1 | Answers are generated only from retrieved passages of the selected documents, with the seven response rules (§11.1). | I | `ai/prompts.py`, `ai/qa.py` |
| QA-2 | Structured output: answer, status, answer_kind, citations (passage number + verbatim quote), conflicts, verification warnings, follow-ups. | I | `qa.AnswerOut` |
| QA-3 | Citations are verified against passage text; a `found` answer with no verified citation is downgraded to `unverified` with a warning. | I | `qa._finalise_ai_answer` (not exercised in CI, see §17) |
| QA-4 | QC flags on entities used in the answer become verification warnings. | I | `test_ask_extractive_fallback_has_citations` (warnings path) |
| QA-5 | Without an API key (or on API failure) an extractive answer is returned: matching entity table + top passages with citations, clearly labelled. | I | `test_ask_extractive_fallback_has_citations` |
| QA-6 | When no strong hit exists the answer is `not_found` with the mandated phrase. | I | `test_ask_not_found` |
| QA-7 | Conversation history is passed for context but citations always come from the current retrieval. | I | `qa._history_text` |

### 4.8 Diagram understanding (DIA)

| ID | Requirement | Status | Test / evidence |
|---|---|---|---|
| DIA-1 | Per-page analysis returns components and connections, each with a confidence tier `confirmed`/`high`/`possible`/`unknown`, plus unreadable regions. | I (vision engine) | `ai/diagrams.py::DiagramOut` |
| DIA-2 | Without the vision engine, a heuristic engine lists labelled components as `possible` and asserts no connections. | I | `test_diagram_heuristic` |
| DIA-3 | Components with boxes are overlaid on the page with tier-specific styling. | I | Diagram tab |
| DIA-4 | Analyses are persisted per page and re-runnable. | I | `diagram_analyses` table |
| DIA-5 | Automatic analysis of all diagram pages at ingest; cross-check of diagram ratings against text entities. | R | §18 |

### 4.9 Comparison (CMP)

| ID | Requirement | Status | Test / evidence |
|---|---|---|---|
| CMP-1 | Comparison table of 13 specification rows across 2–8 documents, each cell listing sourced values. | I | `test_compare_documents` |
| CMP-2 | Rule-based conflicts: `voltage_mismatch`, `discharge_limit`, `charge_current`, `charge_voltage`, `fuse_recommendation`, each with severity, sources and `classification: engineering_analysis`. | I | `test_compare_conflicts.py` |
| CMP-3 | Free-text questions over the selected documents use the QA engine. | I | `POST /compare` with `question` |

### 4.10 Calculators (CALC)

| ID | Requirement | Status | Test / evidence |
|---|---|---|---|
| CALC-1 | Registry of calculators, each declaring inputs (unit, kind, default, accepted entity types and preferred qualifiers). | I | `GET /calculators` |
| CALC-2 | Results include formula, echoed inputs with sources, steps, results with classification, assumptions, warnings, disclaimer. | I | `test_calculator_suggestions_and_run` |
| CALC-3 | Modules: `dc_current`, `inverter_dc_current`, `voltage_drop`, `battery_runtime`, `alternator_charging`, `ac_load`, `fuse_protection`. | I | `test_voltage_drop`, `test_fuse_calculator_distinguishes_manufacturer_from_estimate` |
| CALC-4 | Fuse/protection analysis is device-aware, never sizes by cable alone, and separates manufacturer-required from calculated estimate and recommended-pending-verification, capping by conductor ampacity. | I | same |
| CALC-5 | Document-to-calculator: suggestions per input from a document's entities ranked by qualifier match and confidence; UI "Send to calculator" prefill. | I | `test_calculator_suggestions_and_run`; UI walkthrough |

### 4.11 Invoices and exports (INV)

| ID | Requirement | Status | Test / evidence |
|---|---|---|---|
| INV-1 | Documents typed Invoice/Receipt are parsed for vendor, number, date, currency, line items (description, qty, unit, unit price, total), subtotal, tax, total. | I | `test_invoice_extraction_and_exports` |
| INV-2 | Exports: entities and invoices as CSV, XLSX, JSON; invoice reports `lines`, `estimate` (aggregated by description), `costing` (per invoice with totals). | I | same |

### 4.12 User interface (UI)

| ID | Requirement | Status | Test / evidence |
|---|---|---|---|
| UI-1 | Library: upload (button and drag-drop), status polling, metadata columns, delete, re-process, export. | I | Playwright walkthrough (§16.3) |
| UI-2 | Split-screen viewer: rendered page with zoom, page navigation, text-block outline toggle, highlight overlays scaled from page units. | I | walkthrough steps 2–5 |
| UI-3 | Assistant panel with suggested questions, cited answers, clickable citations that jump and highlight, status/kind badges, warnings, conflicts, "documented values used". | I | walkthrough |
| UI-4 | Technical Data tab = specification extraction with filter, jump-to-source rows, confidence badges, flag dots, Send-to-calculator. | I | walkthrough |
| UI-5 | Structure, Verification (flags with resolve), Diagram tabs. | I | walkthrough |
| UI-6 | Search page, Calculators page (document prefill and suggestions), Compare page, Invoices page. | I | walkthrough |
| UI-7 | Deep links `/documents/{id}?page=N&bbox=x0,y0,x1,y1` open a page with a highlight. | I | walkthrough (search → viewer) |

## 5. System architecture

### 5.1 Layers

```
Frontend (React 18 + Vite + TypeScript; served from frontend/dist by the API)
    │  JSON over /api
API layer (FastAPI, backend/app/api/*.py)
    │
Document processing service (backend/app/ingest/pipeline.py, thread pool)
    ├─ identify.py          magic-byte file identification
    ├─ pdf.py / images.py   page reading, rendering, OCR dispatch
    ├─ ocr/                 OCREngine protocol, Tesseract, post-processing
    ├─ structure/           layout analysis, metadata
    ├─ extraction/          entities, invoices
    ├─ qc/                  validation
    └─ search/index.py      chunking, FTS5, embeddings
AI reasoning layer (backend/app/ai): qa.py, diagrams.py, compare.py over client.py
Calculator engine (backend/app/calculators): base.py contract, modules.py registry, tables.py
Storage: SQLite (SQLAlchemy 2, WAL) + filesystem under MDI_DATA_DIR
```

### 5.2 Extension points

| Component | Contract | Default | Swap by |
|---|---|---|---|
| OCR engine | `OCREngine.recognize(PIL.Image) -> list[OCRBlock]` (`app/ocr/base.py`), words in image pixels with 0–1 confidence | `TesseractEngine` | implement the protocol, select in `get_ocr_engine()` |
| Embedding provider | `EmbeddingProvider.embed(texts) -> ndarray`, `embed_query(text)`, `name`, `dim` (`app/search/semantic.py`) | `HashedTfidfProvider` (4096-d) | `VoyageProvider` when `MDI_VOYAGE_API_KEY` is set; vectors are stored per provider name |
| AI model | `structured_call(system, content, pydantic_schema)` (`app/ai/client.py`) using `client.messages.parse` | `claude-opus-5` | `MDI_AI_MODEL` |
| Calculators | `Calculator(spec, fn)` registered in `REGISTRY` (`app/calculators/modules.py`) | 7 modules | add a module and register it; the UI is generated from `CalculatorSpec` |
| Database | SQLAlchemy URL | SQLite at `MDI_DATA_DIR/index.db` | `MDI_DATABASE_URL` (FTS5 query in `search/query.py` is SQLite-specific, see §17) |

### 5.3 Storage separation

| Store | Location | Contents |
|---|---|---|
| Originals | `MDI_DATA_DIR/originals/<doc_id>/original.<ext>` | uploaded bytes |
| Page renders | `MDI_DATA_DIR/pages/<doc_id>/page-NNNN.png` | 150 DPI renders (images: original downscaled to ≤2200 px) |
| Extracted text | `blocks` table | text, bbox, type, section, OCR words |
| Structured data | `entities`, `qc_flags`, `invoices`, `diagram_analyses` tables | traceable values |
| Search index | `chunks`, `chunks_fts` (FTS5), `embeddings` tables | retrieval units and vectors |

Details in [DATA_MODEL.md](DATA_MODEL.md).

### 5.4 Processing model

- Uploads are written to the originals store, a `Document` row is created with `status=queued`, and the id is submitted to a `ThreadPoolExecutor` (`MDI_INGEST_WORKERS`, default 2).
- With `MDI_BACKGROUND_PROCESSING=false` the pipeline runs inline inside the upload request (used by the test suite).
- OCR runs under a process-wide lock and `OMP_THREAD_LIMIT=1` (two concurrent Tesseract runs on a small container were measured to oversubscribe the CPU by more than an order of magnitude).
- Persistence of one document's results runs under a lock; all derived rows for the document are deleted and rewritten (idempotent re-processing).
- Failures set `status=failed`, `error="<ExceptionType>: message"`, `progress="Failed"`; the original file is kept.

## 6. Processing pipeline

### 6.1 Stages and progress strings

| Stage | Module | `progress` value | Output |
|---|---|---|---|
| Identify | `ingest/identify.py` | `Identifying file` | `file_type` (`pdf`/`image`), `mime_type` |
| Read pages | `ingest/pdf.py`, `ingest/images.py` | `Reading page i/n`, `Reading image`, `Running OCR` | `RawPage[]` with `RawBlock[]` |
| Structure | `structure/layout.py`, `structure/metadata.py` | `Analysing document structure` | block types, sections, outline, warnings, figures, tables, diagram pages, metadata |
| Extract | `extraction/entities.py` (+ `invoices.py` for Invoice/Receipt) | `Extracting technical entities` | `ExtractedEntity[]`, `InvoiceData` |
| Validate | `qc/validate.py` | `Validating critical values` | `QCFlagData[]`, entity `flags` |
| Index + persist | `search/index.py`, `ingest/pipeline.py::_persist` | `Indexing` | pages, blocks, entities, flags, chunks, FTS rows, embeddings, invoice, document metadata/stats |
| Done | | `Ready` (status `ready`) | |

### 6.2 Embedded text vs OCR decision (per page)

A page's embedded text is used when both hold:

1. stripped length ≥ `MDI_MIN_EMBEDDED_CHARS_PER_PAGE` (default 40), and
2. text quality > 0.9, where quality = 1 − (characters outside printable ASCII/Latin/common technical symbols ÷ total).

Otherwise the page is rendered at `MDI_OCR_DPI` (default 300) and OCR'd. `Page.text_source` records `embedded`, `ocr` or `none`.

Embedded pages additionally get vector table detection (PyMuPDF `find_tables`); text blocks that are ≥60 % covered by a table box are replaced by one `table` block with `rows`.

### 6.3 Coordinate systems

- PDF pages: page units are PDF points; OCR word boxes are divided by `zoom = OCR_DPI / 72`.
- Images: page units are source pixels; the display PNG may be downscaled, the viewer rescales overlays from `Page.width/height`.
- Tesseract preprocessing upscales images whose longest side is < 1500 px by 2×; word boxes are divided back before leaving `run_ocr`.
- The viewer positions overlays as percentages: `left = x0 / page.width`, `top = y0 / page.height`, etc.

### 6.4 OCR post-processing (`ocr/postprocess.py`)

Applied per line to OCR output only. Every change is recorded as a normalisation `{original, normalised, rule}` on the block.

| Rule | Example |
|---|---|
| `letter_digit` | `3O0 A` → `300 A`, `l2 V` → `12 V` (only in numeric tokens followed by a unit) |
| `awg_slash` | `4 / 0 AWG`, `4-0 AWG` → `4/0 AWG` |
| `awg_zeros` | `0000 AWG` → `4/0 AWG`, `000` → `3/0`, `00` → `2/0` |
| `awg_hash` | `# 4` → `#4` |
| `mm2` | `mm2`, `mm^2` → `mm²` |
| `v_dc_space`, `vdc_case`, `vac_case` | `48 V DC` → `48 VDC`, `Vdc` → `VDC` |
| `thousands` | `12, 000` → `12,000` |
| `degree_space`, `deg_word` | `50 ° C`, `50 deg C` → `50 °C` |
| `ohm_word` | `0.5 ohm` → `0.5 Ω` |
| `newton_metre`, `nm` | `12 N m`, `12 Nm` → `12 N·m` |

Ambiguity helpers: `digit_alternatives("300") → ["800", "360", "390", "380"]` using the confusion map 3↔8, 1↔7, 0→6/9/8, 6→0/5/8, 9→0, 5→6; `awg_ambiguity` reports `4 0 AWG` / `4O AWG` (not `10 AWG`, not `4/0 AWG`).

## 7. Document understanding

### 7.1 Block classification (`structure/layout.py::classify_blocks`)

Order of tests per block (first match wins):

1. `table` if the block carries table rows.
2. `page_number` if the text is a page-number pattern and the block sits in the bottom 10 % or top 8 % of the page.
3. `footer` / `header` if short (≤80 chars, one line), in the bottom 6 % / top 5 %, not numbered, and **not** large type (≥1.25× body size).
4. `warning` if it starts with WARNING, DANGER, CAUTION, NOTICE, IMPORTANT, ATTENTION, AVERTISSEMENT.
5. `note` if it starts with NOTE/NOTES/TIP/HINT.
6. `caption` if it starts with Figure/Fig./Table/Diagram/Drawing/Illustration/Photo + number.
7. `heading` (level) if: numbered `N`, `N.N`, `N.N.N` (level = depth); Appendix/Section/Chapter (1); font ratio ≥1.5 (1); ≥1.2 (2); bold ≤10 words (3); ALL-CAPS 2–8 words (2). Lines ending in `.`/`,`/`;` or containing a value+unit are never headings.
8. `list` if it starts with a bullet or `1.`/`a)` marker.
9. `label` if ≤3 words and <30 chars.
10. `paragraph` otherwise.

Body font size = median span size over blocks longer than 40 chars; OCR blocks use median line height as the size proxy.

Before classification, `split_heading_lines` splits a multi-line block at any line that is a numbered heading or whose line size is ≥1.2× the block's smallest line size (≤12 words, ≤90 chars), assigning word boxes by vertical position.

### 7.2 Sections

`assign_sections` walks blocks in reading order with a heading stack; a heading of level L pops all headings of level ≥ L. Every block's `section` is the innermost heading title; the outline records `{title, level, page, bbox}`.

### 7.3 Diagram score

`score = min(1, drawings>150: +0.35 | drawings>40: +0.2 ; label_ratio>0.6 & ≥6 blocks: +0.3 ; text density<1.5 chars/1000 pt²: +0.15 ; diagram keyword: +0.3 ; image area>50 % & density<2: +0.2)`; `is_diagram = score ≥ 0.5`.

### 7.4 Metadata (`structure/metadata.py`)

| Field | Method | Limit |
|---|---|---|
| title | largest-font heading/paragraph/label on page 1, else filename | |
| manufacturer | first known name (list of ~120 marine brands) in the first 3 pages, else "manufactured by / ©" phrase | unknown brands → null |
| document_type | first pattern match in order: Invoice, Receipt, Bill of Materials, Parts List, Load Schedule, Wiring Diagram, Installation Manual, Service Manual, Owner's Manual, User Manual, Datasheet, Quick Start Guide, Manual; else Wiring Diagram if page 1–3 is a diagram, else Technical Document | |
| model_number | `Model/Type/Part No: X` phrase, else most frequent/longest `AA-1234`-style token; skipped for Invoice/Receipt | |
| product | title minus manufacturer and document-type words | |
| revision | `Rev/Revision/Version/Ver/Issue X` or `vN.N` | |
| publication_date | first date in the first 3 pages, else first in the first 40 | |
| equipment_types | keyword families with ≥2 hits (or any hit for inverter/charger, bms, solar controller), top 8 by frequency | |

## 8. Technical entity extraction

### 8.1 Taxonomy

| `entity_type` | `unit` | `value` | Critical | Notes |
|---|---|---|---|---|
| `wire_size` | `AWG`, `mm²`, `kcmil` | AWG order number (4/0 = −3, 3/0 = −2, 2/0 = −1, 1/0 = 0, else N); mm²/kcmil numeric | yes | `extra.awg`, `extra.mm2_equivalent` |
| `current` | `A` | amperes (mA/kA converted) | yes | `extra.range` for `10–15 A` |
| `fuse` | `A` | amperes | yes | `device_type` = fuse class (Class T, ANL, MRBF, MEGA, MIDI, …) |
| `breaker` | `A` | amperes | yes | `device_type` = breaker type (double-pole, thermal-magnetic, ELCI, …) |
| `voltage` | `V` | volts (kV/mV converted) | yes | `value_text` keeps `VDC`/`VAC`; `circuit` set from suffix |
| `power` | `W`, `kW`, `VA`, `kVA`, `hp`, `BTU/h` | numeric | no | `extra.watts_equivalent` for BTU/h |
| `frequency` | `Hz`, `kHz` | numeric | no | |
| `capacity` | `Ah`, `Wh`, `kWh` | numeric | no | |
| `torque` | `N·m`, `in-lb`, `ft-lb`, `kgf·cm` | numeric | yes | `extra.nm_equivalent`, `extra.terminal` (M8, 5/16") |
| `resistance` | `Ω`, `mΩ`, `kΩ` | numeric | no | |
| `temperature` | `°C`, `°F` | upper bound for ranges | yes | `extra.range` |
| `terminal_size` | null | null | no | `value_text` e.g. `M8`; requires terminal/stud/bolt context |
| `clearance` | `mm`, `cm`, `m`, `in`, `ft` | numeric | no | requires clearance/ventilation/spacing context |
| `equipment` | null | null | no | `equipment` family + `equipment_model`; requires a model number or a rating in the sentence; deduplicated per document by (family, model) |

### 8.2 Pattern guarantees (`extraction/patterns.py`)

- Numbers: `\d{1,3}(,\d{3})+(\.\d+)?` or `\d+(\.\d+)?`, optional sign for voltage/current/temperature; ranges `lo–hi`, `lo to hi`, `lo ~ hi`.
- Whitespace between number and unit is `[ \t]*` only (no line breaks).
- Units must not continue into a letter, digit or `²` (`(?![A-Za-z0-9²])`), so `V` does not match in `VA`, `A` not in `AWG`/`Ah`/`AC`, `48 V` not inside `480 V` (a preceding word character or digit is also excluded).
- AWG forms: `4/0 AWG`, `4 / 0 AWG`, `0000 AWG`, `#4 AWG`, `16AWG`, `AWG 10`, `10 ga.`; normalised to `N` (1–40) or `N/0` (1–4).
- Matches are consumed in order wire → current → voltage → simple types → temperature → terminal/clearance → equipment; a later pattern never overlaps an earlier match.

### 8.3 Context and qualifiers (`extraction/entities.py`)

- **Context window**: the sentence containing the match (boundaries: `.;!?` followed by whitespace and capital/bullet/digit, list bullets, `.:;` at line end); wrapped lines are joined. For table blocks the row is the context, and the column header is prepended.
- **Qualifier selection**: candidates are the 17 qualifier keywords. Those inside the value's clause (delimited by `; ( ) [ ] ,` and sentence ends) win over those outside. Within the clause, score = `generic_penalty × 10 + distance` with generic penalties nominal 6, required 4, recommended 4, operating 2 (so `rated 5000 W continuous` → `continuous`). Outside the clause, score = penalty + distance within 70 chars, and keywords after the value carry +3. The first candidate allowed for the entity type is used; none → null. Wire sizes accept only minimum/recommended/required.
- **Fuse/breaker/current**: `fuse` if the sentence mentions fuse(s)/fusing and not breaker; `breaker` for breaker/CB/MCB/RCBO/RCD/ELCI/GFCI; both → the nearer term (`extra.protection_ambiguous`); generic "overcurrent protection" → `extra.protection_generic`.
- **Application**: table row label; else first matching application phrase (18 phrases: Battery cable, DC input/output, AC input/output, Inverter connection, Charger output, Alternator output, Solar / PV input, Grounding / bonding, Remote / control, Temperature sensor, Voltage sense, Bus bar, Shore power, Generator, Windlass / thruster, Starter); else the noun phrase before `:`/`=`/`–` on the same line.
- **Circuit**: `dc` / `ac` / `ac/dc` / `control` from keyword families; `VDC`/`VAC` suffix overrides for voltages.
- **Equipment**: first matching equipment family (22 families, most specific first); protection devices are not assigned as equipment to non-protection entities; model = first `AA-1234`-style token in the context.
- `extra.in_warning = true` when the block is a warning or the context contains WARNING/DANGER/CAUTION/NOTICE.

### 8.4 Word location and bbox

`_locate_words` finds the run of block words matching the value's tokens (exact, or substring for tokens with digits / ≥4 letters), preferring the run nearest the value's relative position in the block. The entity bbox is the union of those word boxes; if no run is found the block bbox is used. OCR confidence = minimum word confidence in the run.

### 8.5 Table handling

Rows are `cell | cell | …` lines; the row label is the first non-numeric cell; the column header (row 0) of the value's column is prepended to the context, so a `Max fuse` column yields qualifier `maximum`.

### 8.6 Confidence

`confidence = 0.95` for embedded text, `0.85` for OCR, further limited to `0.5 + 0.5 × ocr_confidence` when word confidence is known; equipment mentions ×0.9 with a model, ×0.6 without. Low-confidence (<0.9) OCR currents and voltages carry `extra.alternatives` (digit-confusion readings).

### 8.7 Dedupe

Exact duplicates (same page, block, type, text, offset) are dropped; equipment is unique per document by (family, model). Repeated values in different places are kept because each is a distinct source.

## 9. Quality control (`qc/validate.py`)

Runs over critical entities only (QC-1). Flags are stored in `qc_flags` and mirrored into `Entity.flags`.

| `flag_type` | Severity | Trigger | Message template |
|---|---|---|---|
| `low_ocr_confidence` | critical for fuse/breaker/wire_size/voltage, warning otherwise | `ocr_confidence < MDI_LOW_CONFIDENCE_THRESHOLD` (0.80) | "OCR uncertainty detected for fuse '300 A' on page N (confidence 62%). The document may read 300 A or 800 A / 360 A. Please verify the original page." |
| `awg_ambiguity` | critical | extractor detected `4 0 AWG` / `4O AWG` | "'4 0 AWG' could be 40 AWG or 4/0 AWG - verify against the page" |
| `unit_out_of_range` | warning | voltage ∉ (0, 1500]; current/fuse/breaker ∉ (0, 10000]; non-standard AWG; torque ∉ [0.05, 500] N·m; temperature ∉ [−80, 250] °C | |
| `nonstandard_size` | info | mm² not in the standard metric series | |
| `nonstandard_value` | info | frequency not 50/60/400 Hz and outside 40–70 Hz | |
| `discrepancy` | critical if OCR confidence < 0.95, else warning | within a group (type, application, equipment, circuit) for fuse/breaker/wire_size/torque, a value different from the most repeated value (which appears ≥2 times); skipped when qualifiers differ and the value is high confidence | "Possible discrepancy: fuse '800 A' on page 9 differs from '300 A' which appears 2 times for the same application (battery cable)…" |
| `awg_cross_reference` | warning | both `N AWG` and `N/0 AWG` appear for the same application; entities inside warnings are exempt | "Both 4 AWG and 4/0 AWG are referenced for 'battery cable'…" |

## 10. Search (`search/`)

### 10.1 Chunking (`index.py`)

Per page, consecutive non-header/footer blocks in the same section are concatenated (`## ` prefix for headings, `[WARNING] ` for warnings) up to 700 characters; a new heading, section change or size overflow starts a new chunk; tables and warnings are always standalone chunks. Chunks carry `block_ids`, section, union bbox and mean block confidence.

### 10.2 Index

FTS5 virtual table `chunks_fts(chunk_id, document_id, page_number, section, body)` with the `unicode61 remove_diacritics 2` tokenizer; bm25 weights section 2.0, body 1.0. Embeddings are stored as float32 blobs keyed by chunk and provider name.

### 10.3 Query parsing (`query.py::parse_query`)

- Entity types from term lists (fuse, breaker, wire size/AWG/mm², voltage/volts, current/amps, torque, temperature, power/watts, capacity/Ah/kWh, clearance/ventilation, equipment/model, terminal).
- A `number + unit` in the query becomes `value`/`unit` (V, A, W, kW, AWG, Hz, Ah, N·m, °C/°F, mm²).
- Synonym expansion over 33 groups (plural-tolerant, longest phrase first).

### 10.4 Retrieval channels

| Channel | Method | Score |
|---|---|---|
| Keyword | FTS5 `MATCH` OR-ing every alternative (stemmed prefix `"term"*` for alphabetic terms ≥3 chars); each hit rescored as `matched_groups × 3 + min(3, bm25)`; strong when matched groups ≥ ⌈groups/2⌉, else `keyword_partial` | |
| Semantic | cosine over stored vectors of the active provider; strong when ≥ 0.12 (`SEMANTIC_STRONG`), else `semantic_weak`; hits < 0.02 dropped | |
| Entity | entities filtered by parsed types (current implies fuse/breaker) and value ±0.1 %, unit-restricted; mapped to their chunk | |

### 10.5 Fusion

Reciprocal rank fusion with k = 60 and weights keyword 1.0 (partial 0.35), semantic 0.8 (weak 0.25), entity 1.2; ×1.15 when a query term appears in the section title. `SearchHit.strong = sources ∩ {keyword, semantic, entity} ≠ ∅`. `highlights` are query terms/synonyms (stem-matched) and the queried value present in the chunk.

## 11. AI reasoning layer (`ai/`)

### 11.1 Response rules and enforcement

| Rule | Enforcement |
|---|---|
| 1 Prefer uploaded documentation | System prompt (`prompts.QA_SYSTEM`); only retrieved passages are supplied. |
| 2 Distinguish documented fact / calculation / assumption / interpretation | `answer_kind` enum in `AnswerOut`; shown as a badge. |
| 3 Never fabricate; say "I could not find this specification in the uploaded documentation." | Prompt; `not_found` path returns the phrase verbatim; extractive fallback returns only passages. |
| 4 State conflicts explicitly | `conflicts[]` in `AnswerOut`; comparison conflict rules (§11.6). |
| 5 Cite every critical statement | `citations[]` with verbatim quotes; §11.3 verification. |
| 6 Flag low OCR confidence | QC flags on entities in the retrieved chunks are appended to `verification_warnings`; the prompt marks flagged values with ⚠. |
| 7 Safety-critical values need source verification | `found` without a verified citation → `unverified`; calculators label estimates. |

### 11.2 QA flow (`qa.answer_question`)

1. Hybrid search over the selected documents (`MDI_SEARCH_TOP_K`, default 12); keep only strong hits.
2. Load entities whose block lies in a retrieved chunk (excluding equipment) and their QC flags.
3. No strong hits → `{mode: "no_results", status: "not_found"}`.
4. If AI is available: build the context (numbered passages with document/page/section, then the structured values with page and ⚠ notes), prepend up to 6 history turns, call `structured_call(QA_SYSTEM, user, AnswerOut)` with `MDI_AI_MODEL`, `max_tokens = MDI_AI_MAX_TOKENS`; on any exception fall back to extractive with `ai_error`.
5. Otherwise return the extractive answer (§11.4).

AI availability: `MDI_AI_ENABLED` and (`MDI_ANTHROPIC_API_KEY`, or `ANTHROPIC_API_KEY`/`ANTHROPIC_AUTH_TOKEN`, or an `ant auth login` profile under `~/.config/anthropic`).

### 11.3 Citation verification

For each citation: passage index must exist; the quote is normalised (lower-case, non-alphanumerics collapsed) and must be a substring of the normalised passage, or for quotes of ≥3 tokens, ≥80 % of tokens must appear in the passage. Result is `verified: true/false`; unverified chips are drawn dashed and labelled. Status `found` with zero verified citations becomes `unverified` and a leading warning is added.

### 11.4 Extractive fallback

`mode: "extractive"`, `status: "partial"`: a Markdown table of entities in the retrieved chunks matching the parsed entity types (type, value, qualifier, application, source), the top 4 passages quoted with document/page/section, a note that AI reasoning is not configured, and citations for those passages (`verified: true`).

### 11.5 Diagram analysis (`diagrams.py`)

Input: the page PNG (base64) plus the page's OCR text. Output schema `DiagramOut`: `diagram_type`, `title`, `system_voltage`, `components[{id, type, label, rating, confidence, bbox_pct}]`, `connections[{from_id, to_id, polarity, circuit, direction, protection[{type, rating, confidence}], confidence, note}]`, `unreadable_regions[]`, `notes[]`; `confidence_legend` is attached. Confidence tiers: `confirmed` (explicitly labelled), `high` (clear symbols, partly legible), `possible` (plausible, uncertain), `unknown`. Engine `claude-vision` when available, else `heuristic` (component words in short blocks, all `possible`, no connections, explanatory note). One analysis is stored per page; `force=true` replaces it.

### 11.6 Comparison (`compare.py`)

Rows (entity type, preferred qualifiers, fallback to unqualified values allowed?): nominal_voltage (voltage; nominal; yes — AC voltages excluded when DC exist), max_continuous_current (current; continuous/maximum; yes), peak_current (peak/surge; no), charge_current (charging; no), charge_voltage (voltage; charging; no), cutoff_voltage (cutoff; no), fuse (yes), breaker (yes), wire_size (yes), capacity (yes), power (continuous/maximum/nominal; yes), temperature (operating; yes), torque (yes). Fallback excludes charging/cutoff/idle/short_circuit/surge/peak/storage/derating values. Up to 4 distinct values per cell, most frequent first.

Conflict rules (all `classification: engineering_analysis`, each with sources):

| Type | Severity | Rule |
|---|---|---|
| `voltage_mismatch` | critical | different rounded DC nominal voltages (≤60 V) across documents |
| `discharge_limit` | critical | battery/BMS document's continuous current < inverter document's max continuous current |
| `charge_current` | warning | charging-source charge current > battery's max charge current |
| `charge_voltage` | critical | charging-source charge voltage > battery charge voltage + 0.05 V |
| `fuse_recommendation` | warning | different fuse ratings for the same application in different documents |

Document roles come from `equipment_types` and titles; any non-battery document with a charge-current value counts as a charging source.

## 12. Calculator engine (`calculators/`)

### 12.1 Contracts

- `InputSpec{key, label, unit, kind: number|select|text, required, default, options, help, entity_types, qualifiers}`.
- Inputs may be plain values or `{value, unit, source}`; a source (document, page, entity) marks `origin: "document"`. Missing required inputs raise 422; numbers are parsed with thousands separators.
- `CalcResult{calculator_id, formula, inputs (echoed with origin/source), steps[], results[{key, label, value, unit, classification, note}], assumptions[], warnings[], sources[], classification, disclaimer}`.

### 12.2 Classification semantics

| Classification | Meaning |
|---|---|
| `manufacturer_required` | Value entered with a document source stating it (e.g. a documented fuse rating). |
| `documented_value` | Value entered as the manufacturer's without an attached source. |
| `calculated_estimate` | Derived by formula from inputs. |
| `recommended_pending_verification` | The engine's recommendation, with rationale, awaiting verification against documentation and standards. |

### 12.3 Modules

| id | Formula | Inputs (entity feeds) | Outputs | Key assumptions / warnings |
|---|---|---|---|---|
| `dc_current` | I = P ÷ V | power (power: continuous/nominal/maximum), voltage (voltage: nominal) | current | steady-state, no losses |
| `inverter_dc_current` | I = P ÷ V ÷ η | power, voltage (nominal/input), efficiency % (default 90), optional low_voltage (voltage: cutoff/minimum) | current, current_low_voltage | size conductors/fuses at low battery voltage |
| `voltage_drop` | V = I × R/m × 2L | voltage, current (current/fuse/breaker), length + unit (m/ft), size (wire_size text), material | voltage_drop, percent, voltage_at_load, resistance | 20 °C resistance (NEC Ch.9 Tbl 8 AWG; ρ 0.01724 Cu / 0.0282 Al Ω·mm²/m); warn >3 % (critical circuits) and >10 % |
| `battery_runtime` | t = (C × V × DoD) ÷ (P ÷ η) | capacity, voltage, load (power), efficiency % (90), dod % (80) | runtime_hours, usable_energy, dc_current | no Peukert/temperature derating |
| `alternator_charging` | t = (C × ΔSoC) ÷ (I × η) | alternator_output (current), derate % (70), capacity, optional max_charge_current (charging/maximum), soc_start (50), soc_end (90), charge_efficiency (95) | charge_current (limited by alternator or battery), hours, ah_needed | warn when alternator exceeds battery limit or rate > 0.5C |
| `ac_load` | W = V × A × PF; VA = V × A | voltage (120), current or power, power_factor (1.0) | watts, va, amps | single-phase |
| `fuse_protection` | I_fuse ≥ I_cont × k → next standard size, ≤ conductor ampacity | device_type (10 profiles), continuous_current, surge_current, surge_duration, system_voltage, manufacturer_fuse (fuse/breaker: recommended/required), manufacturer_max_fuse (maximum), conductor_size (wire_size), engine_space | manufacturer_required, manufacturer_maximum, calculated_estimate, conductor_ampacity, recommended, characteristic | see §12.4 |

### 12.4 Fuse / circuit protection logic

1. Device profile sets the load factor k and characteristic text: inverter 1.25, battery_main 1.0 (protects the conductor), battery_charger 1.25, alternator 1.25 (warn about opening the B+ lead), dc_dc 1.25, solar 1.25, motor 1.5, capacitive 1.25, resistive 1.25, electronics 1.25.
2. `manufacturer_fuse` (with source) → `manufacturer_required` result; without source → `documented_value`.
3. `continuous_current × k` → next value in the standard fuse series (1 … 800 A) → `calculated_estimate`. Surge ratio > 2 adds a time-current-curve assumption; > 4 warns of nuisance tripping.
4. Conductor ampacity from typical 105 °C tables (AWG 18–4/0, mm² 1–150; ×0.85 in engine spaces) → `conductor_ampacity`; warn if continuous current exceeds it.
5. Recommendation: manufacturer value if given (rationale notes any difference from the estimate), else the estimate; capped to the largest standard size ≤ ampacity with a warning, and to `manufacturer_max_fuse`. Always `recommended_pending_verification`.
6. Assumptions always include the 125 % continuous-load rule, standard sizes, interrupt-rating (AIC) requirement, and DC voltage rating at ≥48 V for inverter/battery circuits.

### 12.5 Document-to-calculator suggestions

`GET /calculators/{id}/suggest?document_id=` returns up to 6 entities per input whose `entity_types` match, ranked: preferred qualifier match first, then confidence, then page; AC voltages are demoted for `voltage` inputs; `manufacturer_fuse` excludes `maximum`-qualified values and `manufacturer_max_fuse` requires them. The UI's "Send to calculator" writes `{calculatorId, inputs}` to `sessionStorage["mdi.calculator.prefill"]` and navigates; the page merges it into the form and marks sourced inputs.

## 13. Invoices and exports

- Triggered when `document_type` is Invoice or Receipt. Fields: vendor (largest-font non-"invoice" block on page 1), invoice_number (first `Invoice/Receipt/Order/Ref No: X` containing a digit), invoice_date, currency (word or symbol), subtotal, tax, total (preferring "grand total / amount due / balance due" labels), line items from patterns `desc qty[unit] unit_price total`, `qty desc unit_price total`, `desc total`; a line whose qty × unit price equals the total gets confidence 0.95.
- Exports (`api/exports.py`): entities (17 columns incl. flags) and invoices (`lines` 11 columns, `estimate` aggregated by description with a PROJECT TOTAL row, `costing` per invoice with a TOTAL row) as CSV, XLSX (openpyxl) or JSON.

## 14. User interface (`frontend/src`)

| Screen | Route | Key behaviour |
|---|---|---|
| Library | `/library` | upload button and drop zone; polls every 1.5 s while any document is queued/processing; columns: title/filename/size/model/rev, manufacturer, equipment, type, pages (+OCR count), extracted count and critical-flag badge, uploaded, status; open, re-process, delete; export all technical data |
| Document | `/documents/:id?page=N&bbox=…` | left: `PageViewer` (page image, prev/next, page input, zoom 40–250 %, text-block outline toggle, OCR/embedded badge, original download); overlays: `primary` (pulsing yellow), `secondary` (blue), `entity` (green), `component` (tier-coloured with tag). Right tabs: AI Assistant, Technical Data, Structure, Verification, Diagram |
| Assistant | tab | suggested questions; `POST /ask` with history; answer badges (status, kind, mode); conflicts (red), warnings (yellow); citation chips jump to page + primary highlight (first citation auto-highlighted as secondary); entities table with Send-to-calculator; follow-ups |
| Technical Data | tab | `GET /spec-extraction`; collapsible groups; text filter; row click jumps and highlights the value's word box; confidence badge (≥90 green, ≥75 amber, else red); flag dots |
| Structure | tab | metadata table, outline (indent by level), warnings, tables (first 12 rows), figures, diagram pages |
| Verification | tab | flags sorted critical → warning → info, open page (highlights the entity), mark verified / reopen |
| Diagram | tab | analyse / re-analyse current page; legend; components (click → highlight), connections, unreadable regions; component boxes overlaid from `bbox_pct` |
| Search | `/search?q=` | document filter checkboxes; shows parsed entity types, value, expansions; hits with source badges and `<mark>` highlights; click → deep link |
| Calculators | `/calculators/:calcId` | list; form generated from `InputSpec`; "Fill inputs from document" loads suggestions as chips; sourced inputs outlined green; results with classification labels, inputs with source links, steps, assumptions, warnings, disclaimer |
| Compare | `/compare` | pick ≥2 documents; conflicts as alerts with source chips; specification table; ask across documents with `AnswerView` |
| Invoices | `/invoices` | totals, per-invoice card with line items (click → page/bbox), export buttons for lines/estimate/costing × csv/xlsx/json |

Overlay geometry: `left = bbox.x0 / page.width × 100 %`, `top = bbox.y0 / page.height × 100 %`, width/height likewise; the page canvas keeps `aspect-ratio: width / height`, so overlays remain correct at any zoom or display resolution.

## 15. Configuration (`backend/app/config.py`, prefix `MDI_`)

| Setting | Default | Meaning |
|---|---|---|
| `DATA_DIR` | `<repo>/data` | originals, page renders, `index.db` |
| `DATABASE_URL` | null (SQLite in DATA_DIR) | SQLAlchemy URL |
| `RENDER_DPI` | 150 | viewer page renders |
| `OCR_DPI` | 300 | OCR render resolution |
| `OCR_ENGINE` | `auto` | `auto` / `tesseract` / `none` |
| `OCR_LANGUAGES` | `eng` | Tesseract language string |
| `MIN_EMBEDDED_CHARS_PER_PAGE` | 40 | below → page treated as scan |
| `LOW_CONFIDENCE_THRESHOLD` | 0.80 | QC-2 threshold |
| `ANTHROPIC_API_KEY` | null | AI reasoning key (falls back to SDK env/profile) |
| `AI_MODEL` | `claude-opus-5` | model id |
| `AI_MAX_TOKENS` | 8000 | per answer |
| `AI_EFFORT` | `medium` | reserved (not passed to the API in this version) |
| `AI_ENABLED` | true | master switch |
| `VOYAGE_API_KEY` / `VOYAGE_MODEL` | null / `voyage-3-lite` | hosted embeddings |
| `SEARCH_TOP_K` | 12 | passages retrieved for QA |
| `BACKGROUND_PROCESSING` | true | false = process inside the upload request |
| `INGEST_WORKERS` | 2 | thread-pool size |
| `FRONTEND_DIST` | `<repo>/frontend/dist` | static UI location |
| `MAX_UPLOAD_MB` | 200 | per file |

## 16. Testing and acceptance

### 16.1 Fixtures (`backend/tests/fixtures.py`)

Generated with PyMuPDF at test time: a 4-page inverter installation manual (title page with model/revision/date/warning; specification table; DC battery connection with fuse, wire sizes, torque, warning, sub-heading; AC wiring with breaker, mm²/AWG, control cable, clearance, figure caption); the same manual rasterised to an image-only PDF (200 DPI); an invoice with 4 line items, subtotal, tax, total; a JPEG "photo" of page 3. `scripts/make_samples.py` writes the same set for demos.

### 16.2 Test files

| File | Covers |
|---|---|
| `test_ocr_postprocess.py` | normalisation rules, zero-AWG forms, digit alternatives, AWG ambiguity |
| `test_extraction.py` | pattern guarantees, fuse/breaker/current classification and qualifiers, wire-size applications and traceability, torque/temperature/equipment, table rows |
| `test_qc.py` | low-confidence flags, discrepancies, qualifier exemption, range checks, AWG cross-reference |
| `test_pipeline_api.py` | upload→process for text PDF, scanned PDF (OCR bbox agreement), photo; pages/blocks/images; spec extraction; QC; search channels; extractive QA; not-found; calculators and suggestions; fuse classification; voltage drop; invoice and exports; comparison; diagram heuristic and 204; delete |
| `test_compare_conflicts.py` | all five conflict rules on synthetic inverter + battery manuals |

Run: `cd backend && python -m pytest -q` (34 tests, ~7 s; requires Tesseract). Tests run with `MDI_AI_ENABLED=false` and `MDI_BACKGROUND_PROCESSING=false` in an isolated data dir.

### 16.3 UI acceptance walkthrough

With the app running and the sample documents uploaded, a Playwright script (kept outside the repo during development) verifies: library rows; opening a document; asking the suggested fuse question and receiving an answer that moves the viewer to page 3 with a highlight; clicking a citation; Technical Data groups; jumping to the fuse row (word-level highlight on `300 A`); Send-to-calculator → fuse calculator prefilled with `300` and a source; suggestions for continuous current and conductor; result classifications; Verification, Structure and Diagram tabs on the scanned copy; search deep link; comparison table; invoice card; zero browser console errors. Adding this script as `frontend/e2e/` is a roadmap item (§18, Phase 2).

## 17. Known gaps and limitations

| Area | Gap |
|---|---|
| Tables | Detection needs ruling lines in vector PDFs; OCR'd tables are read row by row as text, so column headers are not available as context. |
| Metadata | Manufacturer detection depends on a fixed brand list plus "manufactured by/©" phrases; unknown brands are null. Model detection can pick an unrelated code on cluttered title pages. |
| Extraction | Regex-based; unusual phrasings, multi-column layouts read out of order, or values split across cells can be missed or mis-scoped. Qualifier inference is heuristic. |
| Diagrams | Connection tracing needs the vision model; heuristic engine lists labels only. Vision results are not cross-checked against text entities. |
| Semantic search | Default provider is lexical (hashed TF-IDF); recall for paraphrases is limited without Voyage or a local transformer. |
| AI path | The live Claude request/response path (structured output, citation verification on real answers) is not exercised in CI; only the fallback is. `MDI_AI_EFFORT` is read but not sent. |
| Comparison | Document roles are inferred from equipment keywords/titles; unusual documents may be mis-roled and skip conflict checks. |
| Calculators | Ampacity and resistance tables are typical published values, not a standards implementation; no temperature correction in voltage drop; standard fuse series is generic. |
| Platform | SQLite single-node; FTS5 query is SQLite-specific so `MDI_DATABASE_URL` pointing elsewhere would need an FTS replacement; no authentication or multi-tenancy; CORS is `*`. |
| UI | No PDF text layer (renders are images); no annotation persistence; e2e script not in repo. |

## 18. Roadmap

All items **Planned**. IDs continue the numbering of §4.

### Phase 2 — Diagram understanding and verification loop

| ID | Item |
|---|---|
| DIA-5 | Run vision analysis on every `is_diagram` page at ingest (configurable), persist components/connections as first-class rows. |
| DIA-6 | Cross-check diagram ratings (fuse, breaker, wire size, voltage) against text entities; raise QC flags on mismatch. |
| DIA-7 | Overlay editing: confirm/correct components and connections in the viewer; corrections feed QA context. |
| QC-7 | Human verification state persisted per entity (verified value, reviewer note) and surfaced in answers. |
| UI-8 | Commit the Playwright e2e walkthrough under `frontend/e2e/` and run it in CI against a fixture data dir. |

### Phase 3 — Multi-document system reasoning

| ID | Item |
|---|---|
| CMP-4 | System model: documents → equipment instances (model, role, ratings) → a named system; comparison works on instances, not files. |
| CMP-5 | Additional conflict rules: cable ampacity vs fuse vs load; charger profile vs battery chemistry; temperature derating vs ambient; BMS charge/discharge vs charger/inverter. |
| CMP-6 | AI-authored comparison narratives with per-cell citations using the QA engine over the comparison table. |
| SRCH-9 | Local transformer embedding provider option; hybrid weights tuned on an evaluation set. |
| QA-8 | Evaluation set of question/answer/citation triples over the fixtures; CI gate on citation precision when an API key is present. |

### Phase 4 — Advanced electrical calculations

| ID | Item |
|---|---|
| CALC-6 | Cable sizing: ampacity (insulation rating, bundling, engine space) + voltage drop → recommended size per circuit, with sources for load values. |
| CALC-7 | Protection coordination: fuse/breaker series checks, interrupt rating vs bank short-circuit current, time-current curve data. |
| CALC-8 | Load schedule builder: AC and DC load tables with duty cycles, peak/continuous totals, export. |
| CALC-9 | Battery bank and charging design: capacity from load schedule, charge sources vs acceptance, alternator integration (external regulator, DC-DC). |
| CALC-10 | Calculation traceability: persist calculations with input sources and link them from documents. |

### Phase 5 — Marine electrical copilot and business features

| ID | Item |
|---|---|
| COP-1 | Bill of materials generated from extracted equipment, wire sizes and protection devices, with quantities from calculations. |
| COP-2 | Job estimates: BOM priced from invoice/parts history; labour tracking; costing reports. |
| COP-3 | Wiring diagram generation from the system model (single-line first). |
| COP-4 | Projects/workspaces, authentication and roles; Postgres option with pgvector for embeddings. |
| COP-5 | Guided installation planning (inverter, battery bank, charging) that produces a cited, verifiable checklist. |

## 19. Change control

- Spec version tracks the application version in `GET /api/status` and `backend/app/main.py`.
- A behaviour change (threshold, rule, endpoint, schema) updates the relevant section, the requirement table status, and [API.md](API.md)/[DATA_MODEL.md](DATA_MODEL.md) in the same PR, and adds or adjusts a test.
- Roadmap items move into §4 with status I/P when delivered.
