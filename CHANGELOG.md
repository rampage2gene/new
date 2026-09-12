# Changelog

## v0.2.2 - 2026-09-12

The circuit calculator answers with the cable size first, and getting your
copy of ABYC E-11 into the app is now one press per document instead of one
per table. Nothing is confirmed on your behalf: the app copies what it can
read, highlights what it could not, and waits for you to check each table
against its page.

- Added: **Copy every table from this document**. Choose your copy of the
  standard under ABYC E-11 reference and press once: every table the app
  recognises on a page is copied as a draft for you to check. It says
  plainly what it could not do - a table no page matched, a table two pages
  matched (open it and choose the page), a page that would not read as that
  table, and the tables you already have, which are never overwritten. The
  formula constants are never found this way, because K and the formula are
  printed as text and not as a table: type K from the page.
- Changed: **the answer comes first.** The result opens with *Cable size* -
  the size to use, and one plain sentence saying what decided it (the drop
  limit, the current after derating, the printed table, or conductors in
  parallel) - and *How it was decided* follows with the working.
- Added: **Show cable sizes in AWG or mm².** The standard lists AWG, so mm²
  is shown as what it is: the nearest standard metric size, with the exact
  area of the AWG size beside it. The bill of materials follows your choice.
- Changed: **the bundle is picked from your own table.** Instead of a yes/no
  and a typed count, the calculator lists the rows of your confirmed
  bundling table with their factors and pages ("3 to 6 conductors bundled
  (× 0.7, page 14)"). Until that table is confirmed you type the count and
  the factor from the page, as before.
- Changed: when the printed voltage-drop table stops short of the current or
  the length, the step now says the circular-mils formula and table are used
  instead, rather than that "the formula result stands".

## v0.2.1 - 2026-09-11

The circuit calculator plans the whole cable run: the length is typed as
you measure it, there and back; you say what the circuit feeds; and the
result goes on past the conductor to the fittings for each cable and a
bill of materials. The fittings come from your own catalogs, never from a
typical list: a wrong tubing size or lug is a fault on a boat.

- Changed: **the length is the whole run, there and back**, typed once.
  The calculation shows the halving and says whether the page's formula
  counts the loop or one way.
- Added: **What the circuit feeds** (battery to main switch, inverter,
  charger, alternator, DC-DC, solar, windlass or thruster, engine starter,
  bilge pump, lights, electronics, other). It sets how the load behaves for
  the fuse and which of your reminders come along - so the fuse positions
  and the specialty fuses for that kind of circuit show when you have
  written those rules from your pages, tagged with the circuit's name.
- Added: **Fittings** for the chosen cable: its outside diameter, the heat
  shrink that slides over the cable and its lug and shrinks below the
  cable, the lug for the stud you name, and the crimp die. These come from
  three new tables under ABYC E-11 reference - cable outside diameters,
  heat-shrink sizes, lugs and dies - that you type from your cable, tubing
  and lug catalogs (in millimetres or inches). A missing row is a blank
  with a box, like every other blank: type the catalog name or the number
  and it is marked as yours.
- Added: **Bill of materials** for the set: cable to buy (cables times the
  loop length, no allowance added), lugs, heat-shrink pieces, the fuse.
- Fixed: the library tests pass on Windows (line endings).

## v0.2.0 - 2026-09-11

A circuit calculator built on your own copy of ABYC E-11, and the same
engine as a library you can put in another web app. Nothing from the
standard is typed into the app: the tables come from your copy, checked and
confirmed by you, and what they do not cover comes back as a blank you fill in.

- Added: **Circuit: conductor and protection (ABYC E-11)** in Calculators.
  From current, one-way length and any nominal voltage it gives the
  conductor size for the voltage drop (the formula for any voltage, the
  printed 12 V table where it applies), the size for the current it must
  carry with engine-space and bundling derating, the larger of the two, and
  conductors in parallel when one is not enough - AWG and mm² side by side,
  every number with its page. Then the fuse for that conductor (never above
  what the conductor can carry, at least the load times its factor), which
  fuse classes have enough interrupting capacity for your battery bank, and
  the reminders from the standard that apply (fuse placement, engine rooms,
  paralleling).
- Added: **a blank you can answer.** Where a table does not cover the case -
  a current past the table, an insulation rating it has no column for, a
  bundle count it has no row for - the result says so, cites the page the
  table stops at, and shows a box for the value from the page. What you type
  is marked as yours, and the calculation runs again at once.
- Added: **ABYC E-11 reference**, at the end of the Calculators list. Import
  each table from a page of your copy of the standard (the app copies the
  cells it can read and highlights the ones it could not), correct them, and
  press *Confirm this table*. Only you can confirm; a draft is never used.
  Your reminders live there too, each with its clause and page. *Download
  for the web app* hands the confirmed set to the library.
- Added: `packages/e11-calc`, a dependency-free JavaScript/TypeScript library
  with the same engine, held to the same test cases as the app, for another
  web app of yours. The tables are for your private use: the standard is a
  paid document.
- Changed: **Fuse & Circuit Protection** uses your confirmed E-11 ampacity
  for a conductor size when there is one, and says so; otherwise the typical
  figure with its old note. **Voltage Drop** adds the size the E-11 formula
  asks for at 3 % and 10 %.
- Settings: `MDI_REFERENCE_DIR` (the bundled reference; what you confirm in
  the app is saved under the data folder and wins over it).

## v0.1.9 - 2026-09-11

The app left values blank and waited for you, but did not say what it was
waiting for. Now every unsettled value says, in one line, what happened and
what to do - and you can answer it where you see it.

- Changed: the **To fill in** tab is two short lists whose headings are the
  ask: *Type these from the page* (the two readers disagreed, nothing was
  kept) and *Confirm these, or correct them* (only one reader could see the
  spot). Each row says what the readers saw, and the line under the box you
  are typing in says what to do. Columns are named for what they hold: what
  it is, page, what the readers saw, what the page says.
- Added: in **Technical data**, a blank value has its own box: type what the
  page says, press Enter, and the value is yours. A one-reader value shows a
  *Confirm* tick with the same one-line ask. No more tooltip pointing at
  another tab.
- Changed: **Verification** names each note in plain words ("two readings
  disagree", "reader stopped on this page", "unusual wire size") and ends it
  with a *What to do* line. "Mark reviewed" is now "I've checked this".
- Changed: the wording in the three tabs no longer uses the app's internal
  words; the UI check now refuses them in anything a person reads.
- Nothing about how values are read or checked has changed: the machine
  still never guesses, and only you can make a blank into a value.

## v0.1.8 - 2026-09-10

A crash in the OCR reader used to take the whole app with it - window,
server, every document being read - with nothing on screen to say so. Now it
costs one page's second reading.

- Changed: the **RapidOCR reader runs in a process of its own.** If it
  crashes or stops answering on a page, that page is read by Tesseract alone,
  the document still finishes, and the reader is started again for the next
  page. A reader that stops three times in one document sits out the rest of
  it rather than being restarted for every page.
- Added: the **Verification tab names the page** - "The RapidOCR reader
  stopped while reading page 37, so only Tesseract read it and its values
  rest on a single reading" - with a link to the page. Nothing is guessed:
  the values from that page carry the single-reading mark until you check
  them or process the document again.
- Added: the reader keeps its own log, `<data dir>\logs\ocr-worker.log`,
  with a traceback written even for a crash in native code. That is the file
  to send when a document keeps stopping the reader.
- Added: Diagnostics shows the reader's process and how often it has stopped.
- The launch check in CI now crashes the reader on purpose on the first page
  and requires the document to come back ready, the page to be named, and
  the reader to be back for the next document - on Windows, macOS and Linux.
- Settings: `MDI_OCR_ISOLATE`, `MDI_OCR_PAGE_TIMEOUT` (180 s),
  `MDI_OCR_MAX_STOPS_PER_DOCUMENT` (3).

## v0.1.7 - 2026-09-10

When the app cannot open its own window it runs in a browser tab, and that
mode had a trap in it. This release removes the trap and makes the app say
plainly when it is gone.

- Fixed: on Windows, the small dialog shown when the app runs in a browser tab
  had one button, **OK**, and OK **stopped the app**. Clicking it - or finding
  it behind the browser later and clicking it then - made every request fail
  at once with "Failed to fetch". OK now only closes the dialog.
- Added: **Stop the app** at the bottom of the sidebar, shown only when the app
  is running in a browser tab on the computer itself. It asks first. A phone
  cannot stop the computer's app (`POST /api/quit` is refused from the network).
- Changed: when a request never completes, the app now checks whether its
  server still answers before choosing what to say. "The app is no longer
  running - start it again; its log is at …" (the path is remembered from the
  last time Diagnostics answered, so it can be named after the server is gone),
  "the phone could not reach the computer - check the Wi-Fi and that the PC is
  awake", or, when the server is fine, that the file itself stopped being
  readable while it was being sent. The old message guessed at OneDrive and zip
  files and pointed at a Diagnostics page that could not answer either.
- Added: the launcher notices when its built-in server stops while the app is
  open, and says so in a dialog that names the log, instead of leaving a page
  that silently fails.
- Added: the Windows installer checks for the Microsoft WebView2 runtime the
  app's window needs and installs it when it is missing (needs an Internet
  connection at that moment; nearly every Windows 10/11 machine already has
  it). Without it the app can only open in a browser tab.
- The launch check that runs in CI on every platform now also stops the app
  through **Stop the app** and requires a clean exit within ten seconds.

## v0.1.6 - 2026-09-09

Settling the values the readers could not agree on stops being a chase around
the screen, and the app finally says how much work is actually left.

- Changed: in **To fill in**, the page image follows whatever row you touch —
  typing in it, tabbing to it, moving the mouse onto it, clicking one of its
  readings or confirming it as it stands — with the value highlighted, and
  Enter carries both the caret and the page to the next row. The trip to the
  page link and back, once per value, is gone: on a document with a dozen
  values that is roughly a third of the actions, and the page you are
  confirming is always the one in front of you.
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
