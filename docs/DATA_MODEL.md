# Data Model

Storage is split by pipeline layer so each store can be replaced independently. Everything below is created by `backend/app/db.py::init_db()` from `backend/app/models.py`. Companion: [SPEC.md](SPEC.md), [API.md](API.md).

## Filesystem (`MDI_DATA_DIR`)

```
data/
  index.db                      SQLite (WAL mode, foreign keys on)
  originals/<document_id>/original.<ext>
  pages/<document_id>/page-0001.png …   150 DPI renders (images: ≤2200 px longest side)
```

Deleting a document removes its rows (cascade), its FTS and embedding rows (`remove_document_index`) and both directories.

## Identifiers and units

- All primary keys are 32-character hex UUIDs generated in Python (`models.new_id`) so links can be built before flush.
- Page numbers are 1-based.
- Bounding boxes are `x0, y0, x1, y1` in **page units**: PDF points for PDFs, source-image pixels for images (`pages.width/height` give the page size in the same units).
- Timestamps are timezone-aware UTC.

## Tables

### documents

| Column | Type | Notes |
|---|---|---|
| id | str(32) PK | |
| filename, title | str | title from metadata detection, else filename |
| file_type | str | `pdf` \| `image` |
| mime_type, size_bytes, sha256, storage_path | | sha256 of the upload; path of the stored original |
| status | str | `queued` \| `processing` \| `ready` \| `failed` |
| progress | str | last pipeline stage message (SPEC §6.1) |
| error | text | `ExceptionType: message` when failed |
| page_count, ocr_pages, embedded_text_pages | int | |
| manufacturer, product, model_number, document_type, revision, publication_date | str | metadata (SPEC §7.4) |
| equipment_types | JSON list | e.g. `["inverter", "battery"]` |
| structure | JSON | `{sections: [{title, level, page, bbox}], warnings: [{page, text, section, bbox}], figures: [{page, caption, section, bbox}], tables: [{page, section, rows, bbox, header}], diagram_pages: [int]}` |
| stats | JSON | `{entities: {type: count}, qc_flags, critical_flags, chunks, blocks, avg_ocr_confidence}` |
| uploaded_at, processed_at | datetime | |

### pages

| Column | Notes |
|---|---|
| id PK, document_id FK(cascade) | |
| page_number | 1-based |
| width, height | page units |
| text_source | `embedded` \| `ocr` \| `none` |
| ocr_confidence | mean OCR block confidence 0–1, null for embedded |
| is_diagram, diagram_score | SPEC §7.3 |
| image_path | render PNG |
| text | page text (blocks joined by blank lines) |
| char_count | |
| page_label | printed page number if detected |

### blocks

| Column | Notes |
|---|---|
| id PK, document_id FK, page_number, order_index | reading order within the page |
| block_type | `paragraph, heading, list, table, caption, warning, note, label, header, footer, page_number` |
| text | lines joined with `\n`; tables as `cell \| cell` rows |
| x0, y0, x1, y1 | bbox |
| section, section_level | enclosing heading title and level (0 = none) |
| source | `embedded` \| `ocr` |
| confidence | 1.0 embedded; mean word confidence for OCR |
| words | JSON `[{"t": "300", "c": 0.96, "bbox": [x0, y0, x1, y1], "line"?: int}]` or null |
| table | JSON `{"rows": [[cell, …], …]}` for table blocks |

### chunks

| Column | Notes |
|---|---|
| id PK, document_id FK, page_number | |
| section | |
| block_ids | JSON list of block ids in the chunk |
| text | retrieval text (`## ` heading prefix, `[WARNING] ` prefix) |
| x0, y0, x1, y1 | union bbox of the blocks |
| confidence | mean block confidence |

### chunks_fts (FTS5 virtual table, created by raw DDL)

```
chunks_fts(chunk_id UNINDEXED, document_id UNINDEXED, page_number UNINDEXED, section, body)
tokenize = 'unicode61 remove_diacritics 2'
```

Queried with `bm25(chunks_fts, 0, 0, 0, 2.0, 1.0)`. Rows are inserted by `index_chunks` and deleted by `remove_document_index`; there is no trigger link to `chunks`.

### embeddings

| Column | Notes |
|---|---|
| chunk_id PK FK(cascade) | |
| document_id | for bulk delete |
| provider | provider name, e.g. `local-hashed-tfidf`, `voyage:voyage-3-lite`; queries only use vectors from the active provider |
| dim | vector length |
| vector | little-endian float32 bytes, `dim × 4` |

### entities

| Column | Notes |
|---|---|
| id PK, document_id FK, page_number, block_id | block_id links to `blocks.id` (nullable) |
| entity_type | SPEC §8.1 |
| value | float or null (AWG: order number, 4/0 = −3) |
| unit | display unit or null |
| value_text | normalised display form (`4/0 AWG`, `230 VAC`, `-20 to 50 °C`) |
| raw_text | text exactly as matched |
| qualifier | SPEC §3 or null |
| application, circuit, equipment, equipment_model, device_type | context (SPEC §8.3) |
| section | |
| snippet | context sentence/row (≤400 chars) |
| char_start, char_end | offsets in the block text |
| x0, y0, x1, y1 | word-level bbox (block bbox fallback) |
| confidence | 0–1 (SPEC §8.6) |
| ocr_confidence | min word confidence or null |
| is_critical | bool |
| flags | JSON `[{"type", "severity", "message"}]` mirrored from qc_flags |
| extra | JSON, keys listed in API.md → Entity |

### qc_flags

| Column | Notes |
|---|---|
| id PK, document_id FK, entity_id (nullable), page_number | |
| severity | `critical` \| `warning` \| `info` |
| flag_type | SPEC §9 |
| message | user-facing text |
| details | JSON, e.g. `{"ocr_confidence": 0.62, "alternatives": ["800 A"]}` or `{"reference": "300 A", "reference_pages": [3, 5]}` |
| resolved | bool, toggled from the UI |

### invoices

| Column | Notes |
|---|---|
| id PK, document_id FK | one per invoice document |
| vendor, invoice_number, invoice_date, currency | strings as printed |
| subtotal, tax, total | floats |
| line_items | JSON `[{"description", "quantity", "unit", "unit_price", "total", "page", "bbox", "confidence"}]` |
| confidence | 0.5–0.95 |

### diagram_analyses

| Column | Notes |
|---|---|
| id PK, document_id FK, page_number | one row per page (replaced on `force`) |
| engine | `claude-vision` \| `heuristic` |
| result | JSON: `DiagramOut` fields plus `confidence_legend` (API.md → DiagramAnalysis) |
| created_at | |

## Write path and idempotency

`pipeline._persist` runs under a process lock and, in one transaction: deletes the document's FTS/embedding rows and all rows in pages, blocks, chunks, entities, qc_flags, invoices, diagram_analyses; inserts pages and blocks (ids pre-generated so entity/chunk links resolve); inserts entities, then flags (linking `entity_id` by index); builds and inserts chunks; inserts FTS rows and embeddings; stores invoice data; updates document metadata, `structure`, `stats`, `processed_at`, clears `error`.

Re-processing therefore yields fresh ids for pages, blocks, chunks and entities; deep links that embed `page` and `bbox` survive re-processing, links that embed entity or chunk ids do not.

## Sessions and concurrency

- SQLAlchemy 2 `sessionmaker` with `expire_on_commit=False`; FastAPI routes use the `get_db` dependency (one session per request, commit on success, rollback on error).
- SQLite is opened with `check_same_thread=False`; WAL mode allows readers during the single writer's transaction.
- `MDI_DATABASE_URL` may point at another database, but `chunks_fts` DDL and the `bm25()` ranking function are SQLite-specific (SPEC §17).
