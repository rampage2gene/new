---
name: release
description: Cut a desktop release of Marine Electrical Document Intelligence — verify, bump the version, tag, and hand the user the download links. Use when the user says "cut a release", "release vX.Y.Z", "publish the app", or invokes /release.
---

# Release procedure

Releases are produced by the "Desktop builds" workflow (`.github/workflows/desktop-build.yml`).
Pushing a tag `vX.Y.Z` builds Windows, macOS (x64 + arm64) and Linux packages and
attaches them to a GitHub Release. Your job is everything around that tag.

Arguments: an optional version (`/release 0.2.0`). Without one, bump the patch
number of the latest `v*` tag (or start at 0.1.0 if none exist).

## 1. Preconditions (stop and report if any fails)

```bash
git status --short                      # must be clean
git fetch origin && git log --oneline -1 origin/main
```

- Work from the branch the user wants released (normally `main`; confirm if they are on a feature branch).
- `cd backend && python -m pytest -q` passes.
- `cd frontend && npm run build` passes (typecheck + bundle).
- `python desktop/build.py --skip-frontend` succeeds on this machine, and the
  smoke run in `docs/SPEC.md` §16.4 passes: start `dist/MarineDocIntelligence/MarineDocIntelligence`
  (or the `.app`) with `MDI_DATA_DIR` set to a scratch directory and `MDI_PORT=8767`,
  then check `/api/status` returns 200 and an upload reaches `ready`.

## 2. Bump the version (one commit)

Update all of these to the new version string; they must agree:

| File | What |
|---|---|
| `backend/app/main.py` | `FastAPI(... version="X.Y.Z")` |
| `frontend/package.json` | `"version"` |
| `desktop/marine_doc_intelligence.spec` | `CFBundleShortVersionString` |
| `desktop/windows/installer.iss` | `#define AppVersion` default |
| `docs/SPEC.md` | spec version line in the header and §19 if it changed |
| `README.md` / `desktop/README.md` | any literal example tag (`v0.1.0`) |

Add a short changelog entry at the top of `CHANGELOG.md` (create it if missing)
summarising user-visible changes since the previous tag:
`git log --oneline <prev-tag>..HEAD`.

Commit: `Release vX.Y.Z` (with the session's required commit trailers).

## 3. Tag and push

```bash
git tag -a vX.Y.Z -m "vX.Y.Z"
git push -u origin <branch>
git push origin vX.Y.Z
```

Never force-push and never move an existing tag. A mistaken tag gets a new
patch release, not a rewrite.

## 4. Watch the build

Use the GitHub Actions tools (`actions_list` with `list_workflow_runs` on
`desktop-build.yml`, then `list_workflow_jobs`) until all four jobs finish.
Typical duration is 10–15 minutes. If a job fails:

- read its log (`get_job_logs`), fix the cause in the workflow or build files,
  run the affected local check, commit, and push to the branch;
- delete nothing; re-tag as the next patch version once the branch is green.

Known-good environment notes are in `desktop/README.md` (pygobject pin on
Ubuntu 22.04, Tesseract via Chocolatey on Windows, Homebrew on macOS).

## 5. Hand over

When the `release` job has published, report to the user:

- the Release URL: `https://github.com/<owner>/<repo>/releases/tag/vX.Y.Z`
- the files: `MarineDocIntelligence-windows-Setup.exe` (installer), `MarineDocIntelligence-windows.zip` (portable), `MarineDocIntelligence-macos-arm64.zip`,
  `MarineDocIntelligence-macos-x64.zip`, `MarineDocIntelligence-linux.tar.gz`
- first-launch notes: builds are unsigned (SmartScreen "More info → Run anyway";
  macOS right-click → Open); macOS/Linux need Tesseract installed; the AI key
  goes in `settings.env` in the per-user data folder.

## Rules

- Do not create a pull request or merge anything as part of a release unless asked.
- Do not change application behaviour in the release commit; only versions and changelog.
- Every step's output goes in the final message: tests, build, tag, run URL, release URL.
