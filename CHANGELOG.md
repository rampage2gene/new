# Changelog

## v0.1.0 - 2026-09-06

First release, built from the PR #1 branch. Desktop installers for Windows, macOS and Linux.

- Excel workbooks with live formulas (`/api/export/workbook`, `/api/calculators/{id}/export`):
  technical data with page hyperlinks, detected tables, one sheet per calculator with
  editable inputs and formula results, reference lookup tables, invoice totals.
- PDF outputs: searchable PDF with OCR text layer, report PDF (specifications, QC,
  calculations, cited answers); text/Markdown/JSON document exports.
- Convert & Export page: images → PDF, PDF → text/Markdown/JSON/PNG, merge, split.

- Desktop application: native windowed launcher, project icon set, PyInstaller
  build, CI packaging for Windows, macOS and Linux, per-user data directory
  with `settings.env`.
- Engineering specification (`docs/SPEC.md`), API contract (`docs/API.md`) and
  data model (`docs/DATA_MODEL.md`).
- Initial platform: ingestion with embedded-text/OCR routing, layout and
  metadata detection, technical entity extraction with QC flags, hybrid search,
  cited Q&A with fallback, diagram analysis, multi-document comparison,
  calculator engine with fuse/protection classification, invoice extraction and
  exports, React UI.
