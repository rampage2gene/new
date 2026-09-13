# Desktop application

The desktop build wraps the FastAPI backend and the built React UI into a single
program with its own icon. Double-click it and a native window opens; nothing
else needs to be installed except Tesseract for OCR (bundled on Windows).

```
desktop/
  windows/installer.iss          Inno Setup script (Start menu, desktop shortcut, uninstaller)
  launcher.py                    starts the API on a free localhost port, opens a native window
  make_icon.py                   generates icons/ (PNG 16-1024, .ico, .icns, .svg)
  marine_doc_intelligence.spec   PyInstaller recipe
  build.py                       one-command build for the current OS
  linux/                         .desktop entry + installer script for the app menu
  requirements.txt               backend deps + pywebview + pyinstaller
```

## Get a ready-made build

Every push builds the app for Windows, macOS (Intel and Apple Silicon) and Linux
in GitHub Actions (`.github/workflows/desktop-build.yml`). Open the **Actions**
tab, pick the latest "Desktop builds" run and download the artifact for your
computer. Tagging a commit `v0.1.1` publishes the same files on a GitHub Release.

| Platform | File | Run |
|---|---|---|
| Windows 10/11 | `MarineDocIntelligence-windows-Setup.exe` (installer) or `MarineDocIntelligence-windows.zip` (portable) | Run the installer: it installs per-user (no admin prompt) into `%LOCALAPPDATA%\Programs`, adds a Start menu entry, an optional desktop shortcut and an uninstaller. Tesseract is included. SmartScreen will warn once because the build is unsigned: choose *More info → Run anyway*. The zip is the same app without installation. |
| macOS 12+ | `MarineDocIntelligence-macos-*.zip` | unzip, drag the `.app` to Applications. First launch: right-click → Open (unsigned). Install Tesseract with `brew install tesseract`. |
| Linux | `MarineDocIntelligence-linux.tar.gz` | extract, run `./install-desktop-entry.sh` to add it to the app menu, or run `./MarineDocIntelligence`. Needs `tesseract-ocr` and GTK/WebKit (`gir1.2-webkit2-4.1`); without WebKit the UI opens in your browser instead. |

## Cutting a release

In a Claude Code session on this repo, run `/release` (optionally `/release 0.2.0`).
The skill in `.claude/skills/release/` verifies tests and a local build, bumps the
version in every file that carries it, adds a changelog entry, tags `vX.Y.Z`,
waits for the four CI jobs, and reports the Release URL and download files.

## Build it yourself

```bash
pip install -r desktop/requirements.txt      # backend deps + pywebview + pyinstaller
python desktop/build.py                      # builds the frontend, icons and the app
# output: dist/MarineDocIntelligence/ (Windows, Linux) or dist/Marine Electrical Document Intelligence.app
```

`python desktop/build.py --skip-frontend` reuses an existing `frontend/dist`.
Builds are per-platform: run it on Windows to get the Windows app, and so on.
The CI workflow is the easy way to get all three.

Run from source without packaging:

```bash
cd frontend && npm run build && cd ..
python desktop/launcher.py
```

## Portable use (no installer)

`MarineDocIntelligence-windows.zip` is the same Windows app without setup:
unzip it anywhere (a USB stick works), open the folder and double-click
`MarineDocIntelligence.exe`.

A portable copy is self-contained: documents, the search index, settings and
`data\logs\app.log` all live in a `data` folder created beside the executable,
so the app and its library travel together and the log is easy to find. That is
switched on by the `portable.txt` file shipped inside the archive — delete it
and the copy behaves like an installed one, using the per-user directory below.
If the folder cannot be written to (unzipped into `Program Files`, or read-only
media), the app falls back to the per-user directory rather than failing. To
remove a portable copy, delete the folder.

## Adding documents

Four ways, all ending in the same processing:

1. **Upload documents** button - in the desktop app this opens the ordinary
   Windows/macOS Open dialog; the app then reads the files straight off the
   disk. (In a plain browser it is the browser's file picker.)
2. **Drag and drop** onto the window. In the desktop app the window itself
   receives the drop and hands the app the files' paths, so this takes the
   same route as the Open dialog and never pushes the bytes through the web
   view. (Clicking the drop zone opens the Open dialog too.)
3. **The phone camera.** On a phone connected to the app (see "Use on your
   phone" below), **Scan with the camera** in the library photographs the
   pages one at a time and turns the set into a single document.
4. **The inbox folder.** Copy PDFs or images into `<data dir>\inbox` - for a
   portable copy that is the `data\inbox` folder next to the executable - and
   the app picks them up within a couple of seconds. When processing finishes
   the original moves to `inbox\done\` next to the same six files described
   under "What comes out" below. Anything that could not be processed moves
   to `inbox\failed\` with a `.error.txt` saying why. Nothing to click.

## What comes out

Every processed document gets its own folder, `<data dir>\exports\<name>\`
(`data\exports\<name>\` beside a portable copy), reachable with the **Open
folder** button in the library:

| File | What it is for |
|---|---|
| `<name>.ocr.pdf` | the scan with a searchable text layer: select and search text in any PDF viewer |
| `<name>.clean.pdf` | **the one to give an AI**: text only - a table of every value with its status, then the full text of every page with corrections applied and blanks marked `[TO FILL IN]` |
| `<name>.xlsx` | the workbook: *Technical Data* with `Verified` and `Notes` columns, a *To fill in* sheet with an empty column to complete, tables, calculators, invoices |
| `<name>.values.csv` | every value, one row each; blanks stay blank and the notes say why |
| `<name>.json` | pages, blocks and values with their verification, for your own database |
| `<name>.txt` | plain text |

The folder is written when processing finishes and rewritten a few seconds
after every value you fill in or confirm, so it always holds the corrected
versions.

## How reading and checking works

Scanned pages are read by **two OCR engines**, RapidOCR and Tesseract, both
bundled and both offline. The more confident reading becomes the page text;
the other is the second reader. Every value found on a scanned page is then
checked:

| Shown as | Meaning |
|---|---|
| **✓ 100%** *2 readers* | both engines read the same value at the same spot |
| **95%** *3 reads* / *corrected* | the readers disagreed; a sharp re-read of that line broke the tie (and may have corrected the first reading - the original is kept in the notes) |
| **—** *to fill in* | no majority: the value is left blank rather than guessed, with the readings beside it |
| **85%** or lower *1 reader* | nobody else could read that spot; a single reading |
| **✓ 100%** *you* | you filled it in or ticked it as verified |

RapidOCR runs in a process of its own. If it crashes or stops answering on a
page, that page is read by Tesseract alone, the document still finishes, and
the **Verification** tab names the page ("The RapidOCR reader stopped while
reading page N…") with a link to it - its values then rest on one reading
until you check them or process the document again. The reader's own log is
`<data dir>\logs\ocr-worker.log`; a crash leaves its trace there.

Blanks and single readings are collected in the document's **To fill in** tab:
open the page, read the value, type it (or click a reading) and press Enter;
or *Confirm as is* when the page agrees. Entries survive a re-run (↻). Optional:
with `MDI_ANTHROPIC_API_KEY=...` in `settings.env` the remaining blanks are
shown to the model with the page image; without a key nothing leaves the
machine. `MDI_OCR_ENGINE=tesseract` or `rapid` in `settings.env` forces a
single reader; Diagnostics shows which readers this copy has.

## Use on your phone

The desktop app also answers on your Wi-Fi, so a phone on the same network can
open the same UI. The computer keeps doing everything; the phone is a screen
and a camera. Open **Use on your phone** in the sidebar:

1. Put the phone on the same Wi-Fi as the computer.
2. Point the phone camera at the QR code and tap the link.
3. In the phone browser's menu choose **Add to Home Screen** for an icon of its own.

On the phone you can read documents, search, fill in values from the **To fill
in** tab with the paper page in your hand, and photograph pages with **Scan
with the camera** in the library: one shot per page, then *Process N pages*
binds them into a single document that is read like any other scan.

| Point | Detail |
|---|---|
| The computer must stay on | It runs the app; the phone only shows it. |
| Windows asks once | The first launch after updating shows a firewall prompt. Allow it on **private networks** or the phone cannot connect. |
| Nothing leaves the network | Pages, values and exports stay on the computer, as before. |
| One scan pairs the phone | The QR code carries a pairing key kept in `<data dir>\phone-key.txt`. Requests from the network without it are refused, and importing files by path is refused to everything but the computer itself. Delete that file and restart to hand out a new key, which un-pairs every phone. |
| Turning it off | `MDI_LAN=false` in `settings.env` goes back to the computer only. |

Over plain HTTP a phone makes a home-screen shortcut rather than an installed
app; it opens full-screen either way.

## Troubleshooting

- **Copying a bug report.** When an upload or import fails, the red error box
  has a "Details for a bug report" section: the version, the folders in use and
  the last 40 log lines, with a Copy button. Paste that wherever you are asking
  for help.
- **Diagnostics page.** The sidebar's **Diagnostics** entry shows the version,
  the data folder, the OCR engine and the application log, with buttons to copy
  the log or the summary to the clipboard. Start here for anything below.
- **"The app could not read *file*" when uploading.** The file exists but
  Windows would not hand its contents over. Usual causes: it is stored
  online-only in OneDrive/SharePoint (right-click → *Always keep on this
  device*), it is being read from inside a zip or an email preview, it is still
  downloading, or another program has it open. Copy it to a normal folder such
  as the Desktop and try again.
- **Log file.** Every launch appends to `logs/app.log` in the data directory —
  `data\logs\app.log` beside the executable for a portable copy, otherwise
  `%LOCALAPPDATA%\Marine Electrical Document Intelligence\logs\app.log`.
  When something fails, that file says why; paste its last lines into an issue
  or a Claude Code session. Every upload is logged, so an upload that leaves no
  line here never reached the app.
- **"could not start" dialog.** The launcher shows the error and the log path
  when the server cannot start or a bundled file is missing. Reinstall from a
  fresh download if it mentions missing interface files.
- **The UI opened in the browser instead of its own window.** The native window
  needs Microsoft Edge WebView2 on Windows (part of Windows 10/11; otherwise
  install the "WebView2 Runtime" from Microsoft) or WebKitGTK on Linux. The
  browser fallback is fully functional; a dialog offers a button to stop the app.
- **Scanned pages are not OCR'd.** The footer status line shows the active OCR
  readers; see "Tesseract discovery" below. If Diagnostics says RapidOCR is
  not available, the app still works with Tesseract alone but cannot
  cross-check values (everything shows as *1 reader*).
- **Windows SmartScreen.** The build is unsigned: *More info → Run anyway*.

## Where the data goes

The app never writes inside its own folder. Documents, page renders, the search
index and settings live in a per-user directory:

| OS | Directory |
|---|---|
| Windows | `%LOCALAPPDATA%\Marine Electrical Document Intelligence\` |
| macOS | `~/Library/Application Support/Marine Electrical Document Intelligence/` |
| Linux | `~/.local/share/marine-doc-intelligence/` |

`settings.env` in that directory holds configuration, one `KEY=value` per line.
It is created on first launch with commented examples. To enable AI answers and
diagram analysis, add your key and restart the app:

```
MDI_ANTHROPIC_API_KEY=sk-ant-...
```

Any `MDI_*` setting from the main README works there. `MDI_DATA_DIR` and
`MDI_PORT` can also be set as environment variables to override the defaults.

## Tesseract discovery

The launcher looks, in order, at `MDI_TESSERACT_CMD`, a `tesseract/` folder next
to the executable (what the Windows build ships), the standard install locations
for each OS, and finally `PATH`. The status line in the app footer shows which
OCR engine is active; scanned pages are skipped when none is found.

## How it works

`launcher.py` picks a free localhost port, runs uvicorn in a background thread
with `MDI_FRONTEND_DIST` pointing at the bundled UI, waits for `/api/status`, and
opens the URL in a pywebview window (Edge WebView2 on Windows, WKWebView on
macOS, WebKitGTK on Linux). Closing the window stops the server. If no native
web view is available the default browser is used and the process stays alive
until Ctrl+C (or, in the windowed Windows build, until the "stop" dialog is
confirmed). Setting `MDI_HEADLESS=1` skips the window entirely; CI uses this
with `desktop/smoke.py` to launch each built app and check `/api/status`.
