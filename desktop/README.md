# Desktop application

The desktop build wraps the FastAPI backend and the built React UI into a single
program with its own icon. Double-click it and a native window opens; nothing
else needs to be installed except Tesseract for OCR (bundled on Windows).

```
desktop/
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
computer. Tagging a commit `v0.1.0` publishes the same files on a GitHub Release.

| Platform | File | Run |
|---|---|---|
| Windows 10/11 | `MarineDocIntelligence-windows.zip` | unzip, open `MarineDocIntelligence.exe`. Tesseract is included. SmartScreen will warn once because the build is unsigned: choose *More info → Run anyway*. |
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
until Ctrl+C.
