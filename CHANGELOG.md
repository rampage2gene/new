# Changelog

## v0.1.6 - 2026-09-09

Settling the values the readers could not agree on stops being a chase around
the screen, and the app finally says how much work is actually left.

- Changed: in **To fill in**, the page image follows whatever row you touch —
  typing in it, tabbing to it, clicking one of its readings or confirming it
  as it stands — with the value highlighted, and Enter carries both the caret
  and the page to the next row. The trip to the page link and back, once per
  value, is gone: on a document with a dozen values that is roughly a third of
  the actions, and the page you are confirming is always the one in front of
  you.
- Fixed: the value box **no longer arrives pre-filled with what the machine
  read**. Holding Enter used to walk the list stamping unconfirmed readings as
  confirmed by you. The reading is still one click away under *Read as*, where
  using it is a deliberate act.
- Fixed: **"Mark verified" in the Verification tab now verifies the value.**
  It used to tick the note and leave the value at its machine confidence, so
  the button in the tab named Verification put an unverified number into every
  export under your name.
- Fixed: the **"to fill in" count now counts down to zero** and *all values
  checked* can appear. The figure was written once when the document was read
  and never recomputed, so it never moved however much you did.
- Fixed: a **dropped file, or one taken from the inbox folder, now appears in
  the library**. It was imported and read correctly, and the screen never said
  so — indistinguishable from a drop that failed.
- Added: **one queue across every document** on the library — "8 values to
  fill in across 2 documents", each with its count and a way straight into it.
  One definition of that number now feeds every badge, list and total; the tab
  used to say 6 while its own table listed 11.
- Added: files the **inbox folder could not read are named on the library**
  with the reason. They used to move to `inbox\failed\` and vanish.
- Added: **Folders** on Diagnostics — the data, exports and inbox folders with
  a button to open each, instead of paths to copy out by hand.
- Fixed: wide tables were **clipped instead of scrolled** above 860 px, so the
  Checked column and its tickboxes were off-screen on a desktop. Every table
  now scrolls inside its own box.
- Fixed: the tab strip shows that it scrolls and brings the active tab into
  view — the Diagram tab was invisible at every width.
- Changed: the library's first screen is shorter (one-line drop zone, exports
  behind one menu), *to fill in* is amber rather than red because it is normal
  work rather than a fault, and a value only one reader saw is marked amber
  instead of neutral grey.

## v0.1.5 - 2026-09-07

Use the app from your phone. The computer keeps doing all the work; the phone
is a screen and a camera on the same Wi-Fi.

- Added: **Use on your phone** in the sidebar - a QR code. Scan it with the
  phone camera while both are on the same Wi-Fi and the app opens on the
  phone; the browser's *Add to Home Screen* gives it an icon of its own.
- Added: the desktop app now serves the UI on the local network as well as on
  the computer itself. Everything - documents, reading, checking, exports -
  stays on the PC; nothing leaves the network and the PC has to be on.
  Switch it off with `MDI_LAN=false` in `settings.env`.
- Added: a **pairing key**, generated once and kept in
  `<data dir>/phone-key.txt`. Any request from the network that does not carry
  it is refused; the QR code carries it, so one scan pairs the phone for good.
  Delete the file and restart to hand out a new one. Importing files by path is
  refused to everything but the computer itself.
- Added: **Scan with the camera** in the library on a phone: photograph the
  pages one at a time, review the strip, and *Process N pages* turns them into
  one document that is read exactly like any other scan
  (`POST /api/documents/scan`).
- Added: a phone-sized layout - the sidebar becomes a top bar, the document
  viewer stacks the page above the tabs, wide tables scroll, and buttons and
  inputs are big enough for a thumb. **To fill in** works from the phone, so a
  value can be typed in with the original page in your hand.
- Note: Windows asks once whether to let the app onto the network. Allow it for
  **private networks**, or the phone cannot connect.
- The addresses to give the phone come from the routing table only. Looking up
  this machine's own hostname is the usual way to enumerate them and blocks for
  as long as the resolver takes when that name has no DNS entry, which made the
  page hang on a machine with no entry for itself.

## v0.1.4 - 2026-09-07

A better OCR, and every value it reads is checked by a second reader. What
the readers cannot settle is left blank for you to fill in, never guessed.

- Added: a second OCR engine, **RapidOCR** (PP-OCR models bundled in the app,
  CPU only, no Internet). Every scanned page is read by RapidOCR and Tesseract;
  the more confident reading becomes the page text, the other is the second
  reader. Tesseract re-reads a page in black-and-white when it was unsure.
- Added: **verification of every value from a scanned page.** Two readers
  agreeing on a value is ✓ 100%. When they disagree, a sharp crop of that line
  is read a third time; two of three settle it at 95% (and can correct the
  first reading). No majority means the value is **left blank** with the
  readings kept beside it. Values nobody else could read stay at their single
  reading (≤ 85%).
- Added: a **To fill in** tab on every document listing blanks and single
  readings: open the page, type the value or click a reading, press Enter.
  Confirm a value as it is with the *verified* tick (Technical Data table).
  Your entries are kept when the document is processed again.
- Added: an **exports folder** for every processed document
  (`<data dir>/exports/<name>/`, `data\exports` for a portable copy): the OCR'd
  PDF, a **clean text PDF** for an AI (values table + full text with
  corrections applied and `[TO FILL IN]` marks), an Excel workbook (Verified
  and Notes columns, a *To fill in* sheet), a values CSV, JSON and plain text.
  Rewritten after every edit. **Open folder** button in the library; the inbox
  writes the same set into `inbox\done\`.
- Added: optional AI check of the remaining blanks when an Anthropic key is in
  `settings.env` (off otherwise; nothing leaves the machine).
- Fixed: **drag-and-drop onto the desktop window** now imports the dropped
  files by path, the same route as the Open dialog, instead of pushing the
  bytes through the web view.
- Changed: Diagnostics lists both OCR readers and the exports folder; the
  library shows *N to fill in* / *all values checked* per document.
- The installer and portable archive grow by roughly 60 MB for the second
  reader's models and runtime.

## v0.1.3 - 2026-09-06

Two ways to get a document in that never pass through the browser upload, for
the machines where that upload fails without saying why.

- Added: the **Upload documents** button in the desktop app now opens the
  operating system's own Open dialog and hands the chosen paths to the app,
  which reads the files straight off the disk (`POST /api/documents/import`).
  Drag-and-drop still works as before.
- Added: an **inbox folder** (`<data dir>/inbox`, next to the executable for a
  portable copy). Any PDF or image copied there is processed automatically and
  comes back as `inbox/done/<name>.ocr.pdf` with a searchable text layer;
  anything that cannot be processed moves to `inbox/failed/` with an
  `.error.txt` explaining why. No clicking involved.
- Added: an **OCR'd PDF** button on every processed document in the library.
- Added: when an upload or import fails, the error now includes a
  "Details for a bug report" block - version, folders, and the last 40 lines
  of the log - with a Copy button.
- Added: the app version is shown in the sidebar.

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
