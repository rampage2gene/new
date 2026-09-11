# API Contract

Base path `/api`. All bodies are JSON unless noted. Interactive schema: `GET /docs`, `GET /openapi.json`. Companion: [SPEC.md](SPEC.md), [DATA_MODEL.md](DATA_MODEL.md). Field names match `frontend/src/types.ts`.

Errors use FastAPI's `{"detail": "..."}` shape. Status codes beyond 200: 201 upload, 204 delete / no diagram analysis, 404 unknown id, 413 upload too large, 415 unsupported file, 422 validation or calculator error.

## Shared shapes

### DocumentSummary

```json
{
  "id": "1b3750c2…", "filename": "manual.pdf", "title": "XYZ-5000 Inverter/Charger",
  "file_type": "pdf", "mime_type": "application/pdf", "size_bytes": 13260,
  "status": "ready", "progress": "Ready", "error": null,
  "page_count": 4, "ocr_pages": 0, "embedded_text_pages": 4,
  "manufacturer": null, "product": "XYZ-5000 Inverter/Charger", "model_number": "XYZ-5000",
  "document_type": "Installation Manual", "revision": "2.1", "publication_date": "March 2024",
  "equipment_types": ["battery", "inverter", "fuse", "inverter/charger", "battery charger", "bms"],
  "stats": {"entities": {"fuse": 2, "wire_size": 6}, "qc_flags": 1, "critical_flags": 0, "chunks": 9, "blocks": 25, "avg_ocr_confidence": null,
            "ocr_engines": ["rapidocr"], "verification": {"checked": 34, "confirmed": 28, "corrected": 0, "to_fill": 0, "unverified": 6, "reader1": "rapidocr", "reader2": "tesseract", "ai": null},
            "to_fill": 0, "verified_by_user": 0, "export_dir": "…/exports/XYZ-5000 Installation Manual", "export_files": ["….ocr.pdf", "….clean.pdf", "….xlsx", "….values.csv", "….json", "….txt"]},
  "uploaded_at": "2026-09-06T04:46:53+00:00", "processed_at": "2026-09-06T04:46:54+00:00"
}
```

`status` ∈ `queued | processing | ready | failed`. `file_type` ∈ `pdf | image`.

### DocumentDetail

`DocumentSummary` plus `structure` and `pages`:

```json
{
  "structure": {
    "sections": [{"title": "2 DC Battery Connection", "level": 1, "page": 3, "bbox": [50, 36, 260, 60]}],
    "warnings": [{"page": 3, "text": "WARNING: Never use 4 AWG…", "section": "2 DC Battery Connection", "bbox": [50, 153, 520, 167]}],
    "figures": [{"page": 4, "caption": "Figure 3: AC wiring diagram", "section": "3 AC Wiring", "bbox": [50, 150, 200, 162]}],
    "tables": [{"page": 2, "section": "1 Specifications", "rows": [["Parameter", "Value"], ["Continuous output power", "5000 W"]], "bbox": [50, 92, 430, 308], "header": ["Parameter", "Value"]}],
    "diagram_pages": [4]
  },
  "pages": [PageSummary]
}
```

### PageSummary

```json
{"page_number": 3, "width": 595.0, "height": 842.0, "text_source": "embedded", "ocr_confidence": null,
 "is_diagram": false, "diagram_score": 0.15, "page_label": "3", "char_count": 612}
```

`text_source` ∈ `embedded | ocr | none`. `width`/`height` are page units (PDF points; pixels for images).

### Block

```json
{"id": "…", "page_number": 3, "order_index": 2, "block_type": "paragraph", "text": "Install a 300 A Class T fuse…",
 "bbox": [50, 99, 520, 131], "section": "2 DC Battery Connection", "section_level": 1,
 "source": "embedded", "confidence": 1.0, "table": null,
 "words": [{"t": "300", "c": 1.0, "bbox": [87.3, 99.1, 103.4, 113.4]}]}
```

`block_type` ∈ `paragraph | heading | list | table | caption | warning | note | label | header | footer | page_number`. `words` only when requested (`?words=true`). `table` = `{"rows": [[…]]}` for table blocks.

### Entity

```json
{
  "id": "…", "document_id": "…", "document_name": "XYZ-5000 Inverter/Charger",
  "entity_type": "fuse", "value": 300.0, "unit": "A", "value_text": "300 A", "raw_text": "300 A",
  "qualifier": "required", "application": "Battery cable", "circuit": "dc",
  "equipment": "inverter", "equipment_model": null, "device_type": "Class T",
  "page": 3, "section": "2 DC Battery Connection",
  "snippet": "Install a 300 A Class T fuse within 180 mm of the battery positive terminal.",
  "block_id": "…", "bbox": [87.3, 99.1, 113.0, 113.4],
  "confidence": 0.95, "ocr_confidence": null, "is_critical": true,
  "verified": false,
  "verification": {"status": "embedded"},
  "flags": [{"type": "awg_cross_reference", "severity": "warning", "message": "…"}],
  "extra": {"qualifiers": ["required"], "in_warning": false}
}
```

`entity_type` ∈ `wire_size | current | fuse | breaker | voltage | power | frequency | capacity | torque | resistance | temperature | terminal_size | clearance | equipment`. `qualifier` ∈ the 17 values in SPEC §3 or null. `circuit` ∈ `dc | ac | ac/dc | control | null`. Known `extra` keys: `qualifiers`, `column`, `in_warning`, `range`, `alternatives`, `awg`, `mm2_equivalent`, `nm_equivalent`, `terminal`, `watts_equivalent`, `protection_ambiguous`, `protection_generic`, `rating`, `voltage`, `verification`.

**Verification.** Every value read from a scanned page is checked against an independent second OCR reading of the same spot (RapidOCR and Tesseract both read every scanned page; the more confident reading becomes the page text, the other is the second reader). `verification.status`:

| status | confidence | meaning |
|---|---|---|
| `confirmed` | 1.0 (`note: "2 readers"`) or 0.95 (`note: "majority of 3"`) | both readers, or two of three including a targeted re-read of the line, read the same value |
| `corrected` | 0.95 | reader 1 was outvoted; the value was replaced, the original is in `verification.original` |
| `to_fill` | 0.0 | the readings disagree with no majority: `value` is `null`, `value_text` is `""`, the candidates are in `verification.readings`, and a `reading_conflict` flag asks the user to fill it in |
| `unverified` | ≤ 0.85 | nobody else could read that spot; a single reading, flagged `reading_unverified` |
| `ai_confirmed` / `ai_corrected` | 1.0 / 0.95 | only with an Anthropic key: the model read the page image and settled a blank |
| `user` | 1.0 | filled in or confirmed through `PATCH /entities/{id}`; `verified` is `true` |
| `single` / `embedded` | unchanged | no second reading was attempted (verification off / text came from the PDF itself) |

`verification.readings` maps `reader1`, `reader2`, `reread` (and `ai`) to what each read, e.g. `{"reader1": "300 A", "reader2": "800 A", "reread": "300 A"}`. A blank is exported as a blank everywhere (CSV, workbook, JSON, clean PDF `[TO FILL IN]`).

### QCFlag

```json
{"id": "…", "document_id": "…", "entity_id": "…", "page": 3, "severity": "warning",
 "flag_type": "awg_cross_reference", "message": "Both 4 AWG and 4/0 AWG are referenced for 'battery cable'…",
 "details": {"reference": "300 A", "reference_pages": [3, 5]}, "resolved": false}
```

`severity` ∈ `critical | warning | info`; `flag_type` ∈ `low_ocr_confidence | awg_ambiguity | unit_out_of_range | nonstandard_size | nonstandard_value | discrepancy | awg_cross_reference | reading_conflict | reading_corrected | reading_unverified`. The three `reading_*` types come from the verification pass and are resolved automatically when the user fills in or confirms the value.

### SearchHit

```json
{"chunk_id": "…", "document_id": "…", "document_name": "…", "page_number": 3, "section": "2 DC Battery Connection",
 "text": "## 2 DC Battery Connection\nConnect the inverter…", "bbox": [50, 36, 520, 167], "score": 0.03,
 "sources": ["entity", "keyword", "semantic"], "highlights": ["fuse", "inverter"],
 "source_scores": {"keyword": {"matched_groups": 2, "total_groups": 2, "score": 8.2}, "semantic": 0.31, "entity": "fuse"},
 "strong": true}
```

`sources` values: `keyword`, `keyword_partial`, `semantic`, `semantic_weak`, `entity`.

### Answer

```json
{
  "mode": "ai", "answer": "Markdown…", "status": "found", "answer_kind": "documented_fact",
  "citations": [{"passage": 1, "document_id": "…", "document_name": "…", "page": 3, "section": "…", "chunk_id": "…",
                 "quote": "Install a 300 A Class T fuse", "note": "fuse rating", "bbox": [50, 36, 520, 167], "verified": true}],
  "conflicts": ["…"], "verification_warnings": ["…"], "follow_up_questions": ["…"],
  "entities": [Entity], "passages": [{"passage": 1, "chunk_id": "…", "document_id": "…", "document_name": "…", "page": 3, "section": "…", "text": "…", "bbox": [], "score": 0.03, "sources": [], "highlights": []}],
  "query": {"entity_types": ["fuse"], "value": null, "unit": null, "expansions": {"fuse": ["fuses", "fusing", "…"]}},
  "ai_error": "optional, present when the AI call failed and extractive mode was used"
}
```

`mode` ∈ `ai | extractive | no_results`; `status` ∈ `found | partial | not_found | unverified`; `answer_kind` ∈ `documented_fact | calculation | assumption | engineering_interpretation | mixed`.

### CalculatorSpec / CalcResult

```json
{"id": "fuse_protection", "name": "Fuse & Circuit Protection", "category": "Protection", "description": "…",
 "formula": "I_fuse ≥ I_continuous × k; next standard size; ≤ conductor ampacity",
 "inputs": [{"key": "continuous_current", "label": "Maximum continuous current", "unit": "A", "kind": "number", "required": false,
             "default": null, "options": null, "help": null, "entity_types": ["current"], "qualifiers": ["continuous", "maximum", "input"]}],
 "outputs": [{"key": "recommended", "label": "Recommended protection", "unit": "A"}], "notes": ["…"]}
```

```json
{"calculator_id": "fuse_protection", "calculator_name": "…", "formula": "…",
 "inputs": {"continuous_current": {"value": 125.0, "unit": "A", "source": {"document_id": "…", "document_name": "…", "page": 3, "section": "…", "entity_id": "…", "snippet": "…", "confidence": 0.95}, "origin": "document"}},
 "steps": ["Manufacturer specifies 300 A (source: …, page 3).", "Calculated minimum = 125 A × 1.25 (Inverter / inverter-charger) = 156.2 A"],
 "results": [{"key": "manufacturer_required", "label": "Manufacturer-specified fuse", "value": 300.0, "unit": "A", "classification": "manufacturer_required", "note": "…"},
             {"key": "calculated_estimate", "label": "…", "value": 175, "unit": "A", "classification": "calculated_estimate", "note": "Next standard size ≥ 156.2 A"},
             {"key": "recommended", "label": "…", "value": 300.0, "unit": "A", "classification": "recommended_pending_verification", "note": "manufacturer-specified value takes precedence; …"}],
 "assumptions": ["…"], "warnings": ["…"], "sources": [SourceRef], "classification": "recommended_pending_verification", "disclaimer": "…"}
```

`origin` ∈ `user | document | default`. Input `kind` ∈ `number | select | text`. An input with `answers` (the `field` of an ask) is one a person fills in when a result came back blank.

A result's `value` may be `null`: a blank, never a guess. Its `note` says why and `CalcResult.asks` lists `{field, reason, input_key, unit, prompt}` for each blank, `input_key` naming the input that answers it (`null` when the fix is elsewhere, such as the reference tables). Results may carry a `group` ("Conductor", "Protection") and the result a `reminders` list of `{topic, rule, clause, page, applies_to, status}` from the owner's E-11 cheat sheet.

### DiagramAnalysis

```json
{"id": "…", "document_id": "…", "page": 4, "engine": "claude-vision", "created_at": "…",
 "diagram_type": "wiring_diagram", "title": null, "system_voltage": "48 V",
 "components": [{"id": "C1", "type": "fuse", "label": "F1 300 A Class T", "rating": "300 A", "confidence": "confirmed", "bbox_pct": [12.0, 30.5, 18.0, 34.0]}],
 "connections": [{"from_id": "C2", "to_id": "C1", "polarity": "positive", "circuit": "dc", "direction": "from_to",
                  "protection": [{"type": "fuse", "rating": "300 A", "confidence": "confirmed"}], "confidence": "high", "note": null}],
 "unreadable_regions": ["label near the busbar"], "notes": [],
 "confidence_legend": {"confirmed": "…", "high": "…", "possible": "…", "unknown": "…"}}
```

`engine` ∈ `claude-vision | heuristic`. Confidence ∈ `confirmed | high | possible | unknown`. `polarity` ∈ `positive | negative | ac_line | ac_neutral | ground | data | unknown`; `circuit` ∈ `dc | ac | unknown`; `direction` ∈ `from_to | to_from | bidirectional | unknown`. `bbox_pct` is `[x0, y0, x1, y1]` in percent of the page image.

### CompareResult

```json
{"documents": [{"id": "…", "name": "…", "manufacturer": null, "model": "XYZ-5000", "document_type": "Installation Manual", "equipment_types": []}],
 "table": [{"key": "nominal_voltage", "label": "Nominal / system voltage", "unit": "V",
            "cells": [{"document_id": "…", "values": [Entity]}]}],
 "conflicts": [{"type": "voltage_mismatch", "severity": "critical", "message": "…", "classification": "engineering_analysis",
                "sources": [{"document_id": "…", "document_name": "…", "page": 1, "section": null, "value_text": "24 VDC", "entity_id": "…", "bbox": []}]}],
 "note": "…", "answer": "Answer (only when a question was sent)"}
```

Row keys: `nominal_voltage, max_continuous_current, peak_current, charge_current, charge_voltage, cutoff_voltage, fuse, breaker, wire_size, capacity, power, temperature, torque` (rows with no values in any document are omitted). Conflict types: `voltage_mismatch, discharge_limit, charge_current, charge_voltage, fuse_recommendation`.

### Invoice

```json
{"id": "…", "document_id": "…", "document_name": "Harbor Marine Supply", "vendor": "Harbor Marine Supply",
 "invoice_number": "HMS-10442", "invoice_date": "March 12, 2024", "currency": "USD",
 "subtotal": 184.7, "tax": 14.78, "total": 199.48, "confidence": 0.9,
 "line_items": [{"description": "Marine Wire 4 AWG red", "quantity": 20.0, "unit": "ft", "unit_price": 3.96, "total": 79.2, "page": 1, "bbox": [50, 179, 500, 191], "confidence": 0.95}]}
```

## Endpoints

### Documents

| Method & path | Request | Response |
|---|---|---|
| `POST /documents` | multipart form, field `files` repeated (PDF or image) | 201 `[DocumentSummary]` with `status: "queued"`; processing starts in the background (inline when `MDI_BACKGROUND_PROCESSING=false`). 413 over `MDI_MAX_UPLOAD_MB`; 415 unknown type. |
| `POST /documents/import` | `{"paths": [str]}` - local file paths (the desktop app's Open dialog; the server reads the files itself, nothing is uploaded) | 201 `[DocumentSummary]` as for upload. 400 when a path is not a file; 415 unknown type; **403 unless the caller is the computer running the app** - it names files on that computer's disk. |
| `POST /documents/scan` | multipart form, field `pages` repeated (photographs of the pages of one document, in order) + optional `name` | 201 `DocumentSummary` (one document): the photos are bound into one PDF and processed as a scan. 415 when anything sent is not an image; 413 over `MDI_MAX_UPLOAD_MB` in total. Without `name` the document is called `Scan <date time>.pdf`. |
| `GET /documents` | — | `[DocumentSummary]`, newest first |
| `GET /documents/{id}` | — | `DocumentDetail` |
| `DELETE /documents/{id}` | — | 204; removes rows, index entries and files |
| `POST /documents/{id}/reprocess` | — | `DocumentSummary` (`queued`); all derived data is rebuilt. Values the user filled in or confirmed are kept (matched by type, page and position). |
| `POST /documents/{id}/verify` | — | Same as reprocess: every reader reads the document again and the verification ladder re-runs (use after adding an API key). |
| `POST /documents/{id}/export` | — | `{"folder": str, "files": [str]}` — writes the exports folder now. 409 while processing. The folder is also written when processing finishes and ~5 s after every edit (`MDI_AUTO_EXPORT`). |
| `GET /documents/{id}/file` | — | original bytes with the stored MIME type and filename |
| `GET /documents/{id}/pages` | — | `[PageSummary]` |
| `GET /documents/{id}/pages/{n}` | `?words=true` to include word boxes | `PageSummary` + `document_id`, `text`, `blocks: [Block]` |
| `GET /documents/{id}/pages/{n}/image` | — | `image/png` render (`Cache-Control: private, max-age=86400`) |
| `GET /documents/{id}/qc` | — | `[QCFlag]` ordered critical → warning → info, then page |
| `POST /documents/{id}/qc/{flag_id}/resolve` | `?resolved=true|false` | `QCFlag` |

### Technical data

| Method & path | Request | Response |
|---|---|---|
| `GET /entities` | `document_ids[]`, `entity_type[]`, `q` (substring over snippet/value/application), `critical_only`, `limit` (500) | `[Entity]` ordered by document, page, offset |
| `PATCH /entities/{id}` | `{"value_text": "125 A"}` fills in (parsed like an extraction: value, unit, normalised text; `""` clears the value back to *to fill in*); `{"verified": true\|false}` confirms as is / unticks (untick restores the machine reading) | `Entity` with `verified`, `confidence: 1.0`, `verification.status: "user"`; reading flags on it are resolved; the document's `stats.to_fill` / `stats.verified_by_user` are refreshed and its exports folder is rewritten. 404 unknown; 400 confirming a blank. |
| `GET /documents/{id}/entities` | `entity_type[]` | `[Entity]` |
| `GET /documents/{id}/spec-extraction` | — | `{"document": {id, name, manufacturer, model_number, document_type}, "groups": [{"key", "label", "count", "items"}], "critical_flags": n}`; group keys `equipment, electrical_ratings, wire_sizes, fuse_ratings, breaker_ratings, installation_requirements, torque_specifications, temperature_limits, warnings` (warning items are `{page, text, section, bbox}`) |

### Search, answers, comparison, diagrams, status

| Method & path | Request | Response |
|---|---|---|
| `POST /search` | `{"query": str (1–500), "document_ids": [str] \| null, "limit": 1–50 (12)}` | `{"query": {raw, entity_types, value, unit, expansions}, "hits": [SearchHit]}` |
| `POST /ask` | `{"question": str (1–2000), "document_ids": [str] \| null, "history": [{"role": "user"\|"assistant", "content": str}] \| null}` | `Answer` |
| `POST /compare` | `{"document_ids": [2–8 ids], "question": str \| null}` | `CompareResult` |
| `POST /documents/{id}/pages/{n}/diagram` | `?force=true` to re-run | `DiagramAnalysis` (404 unknown page) |
| `GET /documents/{id}/pages/{n}/diagram` | — | `DiagramAnalysis`, or 204 when the page has not been analysed |
| `GET /status` | — | `{"ocr_engine": "tesseract"\|"none", "ai_available": bool, "ai_model": str\|null, "embedding_provider": str, "version": "0.1.3", "max_upload_mb": int}` |

### Phone access

The desktop app serves the UI on the local network (`MDI_LAN`, default on) so a phone on the same Wi-Fi can use it. When a pairing key is configured (`MDI_ACCESS_KEY`; the launcher writes one to `<data dir>/phone-key.txt`), **every `/api/` request from a non-loopback client must carry it** as an `X-MDI-Key` header or the `mdi_key` cookie, or it is refused with 401 and a message telling the user to scan the QR code. Exempt: loopback clients, `POST /pair`, and everything outside `/api/` — the page and its assets have to load before a phone can pair. With no key configured the API is open, as it is for the development server and the Docker image.

| Method & path | Request | Response |
|---|---|---|
| `GET /lan` | — | `{enabled, protected, computer, port, urls: [str]}` — `urls` are `http://<private IPv4>:<port>/?key=<pairing key>`, the address the phone opens. **403 from anything but the computer itself**: the key must not be readable from the network it protects. |
| `GET /lan/qr.png` | — | `image/png` QR code of the first URL. 403 as above; 404 when the computer has no private IPv4 address; 503 when the `qrcode` package is missing. |
| `POST /pair` | `{"key": str}` | `{"paired": true, "protected": bool}` and sets the `mdi_key` cookie (HttpOnly, 30 days) so plain links and downloads work. 401 for a wrong key. Never guarded, from anywhere. |

### Diagnostics

Support surface for the desktop app, which has no console. Backs the UI's Diagnostics page.

| Method & path | Request | Response |
|---|---|---|
| `GET /diagnostics` | — | `{version, platform, machine, python, frozen, data_dir, exports_dir, log_path, log_exists, log_size, ocr_engine, ocr_engines: {configured, tesseract, rapidocr, rapidocr_version, rapidocr_error, readers}, tesseract_path, tesseract_version, ai_available, ai_model, embedding_provider, max_upload_mb, phone_access, phone_key_required, documents: {total, ready, failed}}` |
| `POST /quit` | — | 204; stops the desktop app. Refused with 403 unless the request comes from the computer running the app, and 404 when the server was not started by the desktop launcher (development server, tests). This is what **Stop the app** in the sidebar calls when the app runs in a browser tab. |
| `GET /logs` | `?tail=1–5000 (500)` | `text/plain` — the last `tail` lines of `<data dir>/logs/app.log`. 404 when no log file exists (a development server logs to its console instead). |

Every upload is logged by the `app.api.documents` logger, so an upload failure that leaves no line in the log never reached the server.

### Calculators

| Method & path | Request | Response |
|---|---|---|
| `GET /calculators` | — | `[CalculatorSpec]` |
| `POST /calculators/{calc_id}/run` | `{"inputs": {key: value \| {"value", "unit", "source": SourceRef}}}` | `CalcResult`; 422 with the validation message (missing required input, non-numeric, unknown conductor size, unknown calculator) |
| `GET /calculators/{calc_id}/suggest` | `document_id` | `{"calculator": id, "document": {id, name}, "suggestions": {input_key: [Entity ≤6]}}` (only inputs with `entity_types`) |
| `POST /calculators/{calc_id}/export` | same body as `run` | attachment `<calc_id>.xlsx`: the calculator as a sheet whose inputs are editable cells and whose results are Excel formulas (plus a `Reference` sheet of lookup tables); 422 when the app cannot run the calculation with the given inputs. `circuit_e11` has no formulas: its sheet holds the app-computed values |

`circuit_e11` ("Circuit: conductor and protection (ABYC E-11)") computes only from the owner's confirmed reference tables (below). Its results come in two groups plus `reminders`; a blank (`value: null`) carries an ask whose `input_key` is one of `own_ampacity_a`, `own_bundling_factor`, `own_k`, `own_short_circuit_a` - send that input with the person's value and run again; the answered part is then noted "entered by you". With no confirmed table at all it returns one blank whose ask has `"field": "reference"`.

### The ABYC E-11 reference

The tables the circuit calculator computes with, copied from the owner's own copy of the standard and confirmed by them; shape in `packages/e11-calc/schema/e11-table.schema.json`. The owner's saved copy (under the data folder) wins over the copy bundled with the app. Only a `PUT` with `"status": "confirmed"` makes a table usable.

| Method & path | Request | Response |
|---|---|---|
| `GET /reference/e11` | — | `{installed, confirmed: [ids], missing: [ids], fixture, folders: {yours, bundled}, tables: [{id, kind, title, page, status: missing\|draft\|confirmed\|fixture, rows, origin: yours\|bundled, document_id, layout: {title}}], cheatsheet: {entries, origin}}` |
| `GET /reference/e11/tables/{id}` | — | the table file plus `origin` and `layout`; `{status: "missing", layout}` when there is none |
| `PUT /reference/e11/tables/{id}` | the table file with `status` `draft` or `confirmed` | the saved table; 422 with the loader's reason (no page, a row without a page, a fixture, a fuse class without its datasheet); 404 for an unknown id |
| `DELETE /reference/e11/tables/{id}` | — | the table as it now is (the bundled copy, or missing) |
| `POST /reference/e11/tables/{id}/import` | `{"document_id", "page", "table_index": 0}` | a draft copied from the table the app detected there: cells whose row label and column header fit the layout are copied, the rest stay blank and `edits` marks what to check; 404 when no table was detected on that page; 422 for `fuse_classes` (typed from datasheets) |
| `GET /reference/e11/documents/{document_id}/tables` | — | `[{page, table_index, header, rows, section}]`, the tables the app detected in the document |
| `GET /reference/e11/cheatsheet` | — | `{source, entries: [{topic, rule, clause, page, applies_to, status}], markdown, origin}` |
| `PUT /reference/e11/cheatsheet` | `{source: {document, edition}, entries: [...]}` | the saved sheet; 422 for an entry without a clause or a page |
| `GET /reference/e11/download` | — | attachment `e11-reference.zip`: `tables/*.json` (confirmed only), `cheatsheet/cheatsheet.{json,md,html}`, `README.txt` - the layout `packages/e11-calc` reads |

### Invoices and exports

| Method & path | Request | Response |
|---|---|---|
| `GET /invoices` | — | `[Invoice]` |
| `GET /documents/{id}/invoice` | — | `Invoice` (404 when the document is not an invoice) |
| `GET /export/entities` | `format=csv\|xlsx\|json`, `document_ids[]`, `entity_type[]` | attachment `technical-data.<ext>`; columns `document_name, entity_type, value_text, value, unit, qualifier, application, circuit, equipment, equipment_model, device_type, page, section, confidence, ocr_confidence, verified, verification_status, notes, snippet, flags`; a *to fill in* value has empty `value_text`/`value`/`confidence` and the readings in `notes` |
| `GET /export/invoices` | `format`, `document_ids[]`, `report=lines\|estimate\|costing` | attachment `invoice-lines` (`vendor, invoice_number, invoice_date, currency, description, quantity, unit, unit_price, total, page, document_name`), `project-estimate` (`description, quantity, unit, unit_price, total, vendors` + `PROJECT TOTAL` row) or `job-costing` (`vendor, invoice_number, invoice_date, currency, line_items, subtotal, tax, total, document_name` + `TOTAL` row) |

### Workbook export (live formulas)

| Method & path | Request | Response |
|---|---|---|
| `GET /export/workbook` | `document_ids[]` (default: all ready documents), `include=data,tables,calculators,invoices`, `calculators[]` (calculator ids, default all) | attachment `marine-electrical-workbook.xlsx`. Sheets: `README` (documents, legend, disclaimer); `Technical Data` (Excel table, numeric `Value` column, `Source` column of `HYPERLINK` formulas to `<base>/documents/{id}?page=N&bbox=…`); `Tables` (detected tables, numeric strings as numbers); `Reference` (AWG/mm² ampacity and resistance, standard fuse and breaker sizes, device load factors; named ranges `AwgTable`, `Mm2Table`, `FuseSizes`, `DeviceTable`); one sheet per calculator with inputs prefilled from the first document that has suggestions, results as formulas (see SPEC §12.6) and an "As computed by app" column; `Invoices` (line totals `=qty*price`, per-invoice `SUMIF`, job total, estimate-by-item `SUMIF`) |

### PDF outputs and document exports

| Method & path | Request | Response |
|---|---|---|
| `GET /documents/{id}/export/searchable-pdf` | — | attachment `<name>_searchable.pdf`: the original file with an invisible text layer (each OCR word at its bbox) on OCR'd pages; images are wrapped in a one-page PDF first. 409 while the document is not `ready`, 404 if the original is missing |
| `GET /documents/{id}/export/report.pdf` | `sections=spec_extraction,qc` | attachment `<name>_report.pdf` (A4, footer with generation time and page numbers) |
| `POST /export/report.pdf` | `{"document_ids": [], "sections": ["spec_extraction","qc"], "calculations": [CalcResult…], "answer": Answer & {"question"}, "title"}` | attachment `report.pdf` combining the chosen sections per document, calculator results (inputs with sources, formula, steps, classification badges, warnings, assumptions) and a cited answer; 422 when nothing was requested |
| `GET /documents/{id}/export/{txt\|md\|json}` | `words=false` (json: include OCR word boxes) | attachment: page-separated text; Markdown with headings (`#` × level), pipe tables, `> **WARNING**` quotes; or `DocumentDetail` + `pages[].blocks[]`. Unknown format → 404 |

### Conversions (stateless, nothing stored)

| Method & path | Request | Response |
|---|---|---|
| `POST /convert` | multipart `files[]`, `to=pdf\|txt\|md\|json\|png`, `ocr=true`, `dpi` | `pdf`: all files (images and PDFs) as one PDF, one page per image; other targets take exactly one PDF (an image is wrapped first): text/Markdown/JSON as above but read on the fly with OCR for pages lacking a text layer (`ocr=false` skips OCR), `png`: zip of `page-NNNN.png` at `dpi` (default `MDI_RENDER_DPI`). 415 for unreadable files, 422 for a wrong file count |
| `POST /convert/merge` | multipart `files[]` (≥2 PDFs/images) | attachment `merged.pdf` in upload order |
| `POST /convert/split` | multipart `file`, `ranges` e.g. `1-3,5,7-` (default one file per page) | attachment `<name>_split.zip` of `<name>_p<range>.pdf`; 422 for an empty or malformed range |

### Static UI

Any other `GET` path serves `frontend/dist` (SPA fallback to `index.html`) when a build exists; otherwise `/` returns a JSON pointer to `/docs`.
