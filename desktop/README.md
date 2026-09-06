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

## Troubleshooting

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
  engine; see "Tesseract discovery" below.
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
