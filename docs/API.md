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
  "stats": {"entities": {"fuse": 2, "wire_size": 6}, "qc_flags": 1, "critical_flags": 0, "chunks": 9, "blocks": 25, "avg_ocr_confidence": null},
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
  "flags": [{"type": "awg_cross_reference", "severity": "warning", "message": "…"}],
  "extra": {"qualifiers": ["required"], "in_warning": false}
}
```

`entity_type` ∈ `wire_size | current | fuse | breaker | voltage | power | frequency | capacity | torque | resistance | temperature | terminal_size | clearance | equipment`. `qualifier` ∈ the 17 values in SPEC §3 or null. `circuit` ∈ `dc | ac | ac/dc | control | null`. Known `extra` keys: `qualifiers`, `column`, `in_warning`, `range`, `alternatives`, `awg`, `mm2_equivalent`, `nm_equivalent`, `terminal`, `watts_equivalent`, `protection_ambiguous`, `protection_generic`, `rating`, `voltage`.

### QCFlag

```json
{"id": "…", "document_id": "…", "entity_id": "…", "page": 3, "severity": "warning",
 "flag_type": "awg_cross_reference", "message": "Both 4 AWG and 4/0 AWG are referenced for 'battery cable'…",
 "details": {"reference": "300 A", "reference_pages": [3, 5]}, "resolved": false}
```

`severity` ∈ `critical | warning | info`; `flag_type` ∈ `low_ocr_confidence | awg_ambiguity | unit_out_of_range | nonstandard_size | nonstandard_value | discrepancy | awg_cross_reference`.

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

`origin` ∈ `user | document | default`. Input `kind` ∈ `number | select | text`.

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
| `GET /documents` | — | `[DocumentSummary]`, newest first |
| `GET /documents/{id}` | — | `DocumentDetail` |
| `DELETE /documents/{id}` | — | 204; removes rows, index entries and files |
| `POST /documents/{id}/reprocess` | — | `DocumentSummary` (`queued`); all derived data is rebuilt |
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
| `GET /status` | — | `{"ocr_engine": "tesseract"\|"none", "ai_available": bool, "ai_model": str\|null, "embedding_provider": str, "version": "0.1.0"}` |

### Calculators

| Method & path | Request | Response |
|---|---|---|
| `GET /calculators` | — | `[CalculatorSpec]` |
| `POST /calculators/{calc_id}/run` | `{"inputs": {key: value \| {"value", "unit", "source": SourceRef}}}` | `CalcResult`; 422 with the validation message (missing required input, non-numeric, unknown conductor size, unknown calculator) |
| `GET /calculators/{calc_id}/suggest` | `document_id` | `{"calculator": id, "document": {id, name}, "suggestions": {input_key: [Entity ≤6]}}` (only inputs with `entity_types`) |

### Invoices and exports

| Method & path | Request | Response |
|---|---|---|
| `GET /invoices` | — | `[Invoice]` |
| `GET /documents/{id}/invoice` | — | `Invoice` (404 when the document is not an invoice) |
| `GET /export/entities` | `format=csv\|xlsx\|json`, `document_ids[]`, `entity_type[]` | attachment `technical-data.<ext>`; columns `document_name, entity_type, value_text, value, unit, qualifier, application, circuit, equipment, equipment_model, device_type, page, section, confidence, ocr_confidence, snippet, flags` |
| `GET /export/invoices` | `format`, `document_ids[]`, `report=lines\|estimate\|costing` | attachment `invoice-lines` (`vendor, invoice_number, invoice_date, currency, description, quantity, unit, unit_price, total, page, document_name`), `project-estimate` (`description, quantity, unit, unit_price, total, vendors` + `PROJECT TOTAL` row) or `job-costing` (`vendor, invoice_number, invoice_date, currency, line_items, subtotal, tax, total, document_name` + `TOTAL` row) |

### Static UI

Any other `GET` path serves `frontend/dist` (SPA fallback to `index.html`) when a build exists; otherwise `/` returns a JSON pointer to `/docs`.
