# Changelog

## v0.1.2 - 2026-09-06

- Fixed: an upload that failed because Windows could not read the file reported
  only "Failed to fetch". Files are now checked before the upload starts, and
  the message names the file and the usual causes (stored online-only in
  OneDrive, inside a zip or an email preview, still downloading, or open in
  another program).
- Added: a **Diagnostics** page — app version, data folder, log location, OCR
  engine, upload limit and document counts, with the application log and
  buttons to copy either to the clipboard.
- Added: `GET /api/diagnostics` and `GET /api/logs`, and `max_upload_mb` on
  `GET /api/status` so oversized files are caught before they are uploaded.
- Added: every upload is logged server-side, so a failure can be told apart —
  no log line means the file never left the browser.
- Added: upload progress, and a message when a drop carries no file at all.
- Changed: the portable download now keeps its data and log in a `data` folder
  beside the executable instead of a per-user folder, so it is self-contained.
  Installed copies are unaffected.

## v0.1.1 - 2026-09-06

- Fixed: the Windows app closed immediately on launch. A windowed build has no
  console streams and the built-in server's logging setup crashed on them.
- Added: a log file at `<data dir>/logs/app.log` (Windows:
  `%LOCALAPPDATA%\Marine Electrical Document Intelligence\logs\app.log`), an
  error dialog naming the log when the app cannot start, and a way to stop the
  app when it falls back to the browser.
- Added: CI launches every built app (Windows, macOS, Linux) and waits for its
  API before packaging, so a launch regression cannot ship.
- The Windows installer now carries the app version instead of a fixed default.

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
