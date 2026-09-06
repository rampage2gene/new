# Marine Electrical Document Intelligence

An AI-powered OCR and document-intelligence application for marine electrical and
technical documentation. It ingests installation manuals, datasheets, wiring
diagrams, battery/BMS/inverter/alternator/charger documentation, scans,
photographs, invoices and parts lists, and turns them into a **structured,
searchable, traceable knowledge base** that can answer technical questions,
extract specifications, compare equipment and feed real manufacturer data into
electrical calculators.

Every answer, extracted value and calculator input keeps its source: document,
page, section, the exact text, and a bounding box that is highlighted in the
viewer. Nothing is presented as a manufacturer fact without a source.

## What it does

| Capability | Where |
|---|---|
| PDF upload (embedded text or scanned) and photos/scans of pages | Document Library |
| Embedded-text extraction with word boxes; Tesseract OCR with word-level confidence for scans | ingestion pipeline |
| OCR post-processing for technical notation (`4 / 0 AWG` → `4/0 AWG`, `3O0 A` → `300 A`, `mm2` → `mm²`, digit-confusion candidates) | `app/ocr/postprocess.py` |
| Document structure: title, manufacturer, model, revision, date, document type, headings/sections, tables, warnings, captions, diagram pages | `app/structure/` |
| Technical entity extraction: wire sizes (AWG/mm²/kcmil), fuses (with class), breakers (with type), voltage, current (continuous/peak/surge/…), power, frequency, capacity, torque, temperature, clearances, terminal sizes, equipment + model numbers | `app/extraction/` |
| Quality control: OCR confidence, digit ambiguity (300 A vs 800 A), plausibility ranges, repeated-reference discrepancies, 4 AWG vs 4/0 AWG cross-references | `app/qc/validate.py` |
| Hybrid search: FTS5 keywords + marine-electrical synonyms, technical value search ("every mention of 48 volts"), entity search, section-aware boosts, local semantic vectors (pluggable embedding provider) | Search tab |
| Cited question answering (Claude via the Anthropic SDK) with citation verification, conflict detection and verification warnings; extractive fallback with sources when no API key is configured | AI Assistant panel |
| Electrical Specification Extraction report (wire sizes, circuit protection, equipment, ratings, torque, clearances, warnings) with per-item sources; CSV/XLSX/JSON export | Technical Data tab |
| Diagram/schematic analysis with mandatory confidence tiers (confirmed / high / possible / unknown) and no invented connections | Diagram tab |
| Multi-document comparison table and rule-based conflict detection (voltage mismatch, BMS discharge limit vs inverter current, charger vs battery charge limits, conflicting fuse recommendations) | Compare Documents |
| Calculators fed from document values: DC current, inverter DC current, voltage drop, battery runtime, alternator charging, AC load, and a device-aware fuse & circuit-protection analysis that separates *manufacturer-required* from *calculated estimate* and *recommended pending verification* | Calculators |
| Invoice/receipt extraction (vendor, number, date, line items, tax, total) with line-item, project-estimate and job-costing exports | Invoices & Parts |

## Architecture

```
Frontend (React + Vite, served by the API)
    ↓
API layer (FastAPI, backend/app/api)
    ↓
Document processing service (backend/app/ingest/pipeline.py)
    ├─ File identification (magic bytes)          app/ingest/identify.py
    ├─ PDF reader / page renderer (PyMuPDF)       app/ingest/pdf.py
    ├─ OCR engine abstraction (Tesseract)         app/ocr/
    ├─ Layout analysis + metadata                 app/structure/
    ├─ Entity extraction                          app/extraction/
    ├─ Quality control                            app/qc/
    └─ Chunking + indexing                        app/search/index.py
Storage (all separate, all swappable)
    ├─ Originals            data/originals/<doc>/
    ├─ Page renders         data/pages/<doc>/
    ├─ Extracted text       blocks table (bbox, section, OCR words + confidence)
    ├─ Structured data      entities / qc_flags / invoices / diagram_analyses tables
    └─ Search index         chunks_fts (FTS5) + embeddings table
AI reasoning layer (app/ai): cited QA, diagram vision, comparison
Calculator engine (app/calculators): registry of modules with sourced inputs
```

Every stage exchanges plain data structures (`RawPage`/`RawBlock`, `ExtractedEntity`,
`QCFlagData`), so the OCR engine, embedding provider, extractor or AI model can be
replaced independently. OCR engines implement `OCREngine` (`app/ocr/base.py`);
embedding providers implement `EmbeddingProvider` (`app/search/semantic.py`);
calculators register in `app/calculators/modules.py`.

### Data model of an extracted value

```json
{
  "entity_type": "fuse", "value": 300, "unit": "A", "value_text": "300 A",
  "qualifier": "required", "device_type": "Class T", "application": "Battery cable",
  "circuit": "dc", "equipment": "inverter", "equipment_model": "XYZ-5000",
  "document_id": "…", "page": 3, "section": "2 DC Battery Connection",
  "snippet": "Install a 300 A Class T fuse within 180 mm of the battery positive terminal.",
  "bbox": [87.3, 99.1, 113.0, 113.4], "confidence": 0.95, "ocr_confidence": null,
  "is_critical": true, "flags": []
}
```

## AI response rules

Implemented in `app/ai/prompts.py` and enforced in `app/ai/qa.py`:

1. Uploaded manufacturer documentation is preferred over general knowledge.
2. Every statement is classified: documented fact, calculation, assumption or engineering interpretation.
3. Specifications are never fabricated; missing information is reported as
   *"I could not find this specification in the uploaded documentation."*
4. Conflicts between documents are stated explicitly with both sources.
5. Every critical recommendation carries a citation; quotes are verified against the
   passage text and unverified answers are downgraded to **Unverified**.
6. Low OCR confidence on an important number produces a verification warning
   (e.g. *"The document may read 300 A or 800 A. Please verify the original page."*).
7. Calculator results are labelled as estimates and never as manufacturer requirements.

Without an Anthropic API key the assistant runs in **extractive mode**: it returns the
documented values and the most relevant passages with citations, and says so.

## Getting started

Requirements: Python 3.11+, Node 20+, Tesseract OCR (`apt-get install tesseract-ocr`).

```bash
# Backend
cd backend
pip install -r requirements-dev.txt
cp .env.example .env            # optional: add MDI_ANTHROPIC_API_KEY for AI answers
python -m pytest                # 34 tests incl. OCR of a synthetic scanned PDF

# Frontend
cd ../frontend
npm install
npm run build                   # output served by the API at http://localhost:8000/

# Run
cd ../backend
uvicorn app.main:app --port 8000
```

For development with hot reload run `scripts/dev.sh` (API on 8000, Vite on 5173).
Generate demo documents with `python scripts/make_samples.py samples/` and upload them
in the library.

### Docker

```bash
docker build -t marine-doc-intelligence .
docker run -p 8000:8000 -v mdi-data:/data -e MDI_ANTHROPIC_API_KEY=sk-ant-... marine-doc-intelligence
```

## API overview

| Endpoint | Purpose |
|---|---|
| `POST /api/documents` (multipart) | Upload one or more PDFs/images; processing runs in the background |
| `GET /api/documents`, `GET /api/documents/{id}` | Library and document detail (metadata, structure, pages) |
| `GET /api/documents/{id}/pages/{n}` · `/image` · `/file` | Page blocks with boxes, rendered page image, original file |
| `GET /api/documents/{id}/spec-extraction` | Electrical Specification Extraction report |
| `GET /api/documents/{id}/entities`, `GET /api/entities` | Structured technical data (filterable) |
| `GET /api/documents/{id}/qc` | Verification flags |
| `POST /api/search` | Hybrid search across documents |
| `POST /api/ask` | Cited question answering (`document_ids`, optional `history`) |
| `POST /api/compare` | Cross-document comparison, conflicts, optional question |
| `POST /api/documents/{id}/pages/{n}/diagram` | Diagram analysis with confidence tiers |
| `GET /api/calculators`, `POST /api/calculators/{id}/run`, `GET /api/calculators/{id}/suggest` | Calculator specs, execution, document-to-calculator suggestions |
| `GET /api/invoices`, `GET /api/export/invoices`, `GET /api/export/entities` | Invoice data and CSV/XLSX/JSON exports |

Interactive docs: `http://localhost:8000/docs`.

## Configuration

All settings are environment variables prefixed `MDI_` (see `backend/.env.example`):
data directory, OCR engine/DPI/languages, low-confidence threshold, Anthropic API key
and model, optional Voyage embedding key, worker count and upload limit.

## Limitations and roadmap

* Table detection relies on ruling lines in vector PDFs; OCR'd tables are read row by row.
* Diagram connection tracing requires the vision model; the heuristic engine only lists
  labelled components as *possible*.
* The default semantic index is a local hashed TF-IDF model; configure Voyage or add a
  local transformer provider for stronger semantic recall.
* Ampacity and resistance tables are typical published values and must be verified
  against the applicable standard and the wire's actual rating.

Planned: system-level analysis, cable sizing and protection design, wiring-diagram
generation, battery bank and charging system design, automated bills of materials and
job estimates - the modules above are the foundation for a marine electrical AI copilot.
