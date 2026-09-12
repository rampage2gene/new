# Marine Electrical Document Intelligence

An offline desktop application that reads marine electrical documentation,
extracts every technical value with its source, checks each one, and never
guesses. Python/FastAPI backend, React/Vite UI, packaged with PyInstaller and
released through GitHub Actions.

```
backend/app/     ingest → ocr → structure → extraction → qc → search → api
frontend/src/    pages/ and components/, one stylesheet (styles.css)
desktop/         launcher.py, PyInstaller spec, build.py, smoke.py
docs/            SPEC.md (contracts), API.md (endpoints), UI.md (interface)
packages/e11-calc  the ABYC E-11 circuit engine as a dependency-free TypeScript
                 library; backend/app/reference is its Python twin, both held to
                 packages/e11-calc/tests/test-vectors.json
```

**No value from ABYC E-11 is ever typed into the code.** The tables come from
the owner's own copy, imported from a page and confirmed by them in the app;
a case the tables do not cover is a blank with an ask, never an extrapolation.
Unit conversions and industry lists (fuse sizes, metric sizes, load profiles)
are labelled as such.

## The rule the product rests on

**A value the machine is unsure of is left blank, never guessed**, and a
machine reading is never presented as confidently as a human confirmation.
Two OCR engines read every scanned page; agreement is 100%, a tie-break third
read is 95%, no majority means the value is blanked and queued in the
document's *To fill in* tab. Nothing in the code or the interface may erode
this — not for speed, not for a tidier screen, not for a shorter flow.

## Working here

- **Tests:** `cd backend && python -m pytest` (181 tests, one skipped until
  the owner's tables exist) and `cd packages/e11-calc && npm test` (58). They
  must pass before a commit.
- **UI build:** `cd frontend && npm run build`.
- **The built app:** `python desktop/build.py`, then
  `python desktop/smoke.py dist/MarineDocIntelligence/MarineDocIntelligence`.
- **Releases:** tag pushes are refused by the proxy, so dispatch
  `desktop-build.yml` on the branch with the `release_tag` input. The
  `/release` skill does the whole sequence.
- Develop on `claude/marine-electrical-doc-intelligence-qr5xfx`, push with
  `git push -u origin <branch>`.

## Any change under `frontend/` runs `/design-pass` before it is committed

`docs/UI.md` is the interface contract — tokens, the spacing scale, the
component table, the four states every view needs, table rules, the
confidence ladder, the 860 px breakpoint, accessibility and the copy voice.
Read it before writing UI code, not after.

`/design-pass` runs the mechanical checks (`npm run ui:check`,
`npm run ui:shots`) and three reviewers — **ui-critic** (what it looks like),
**flow-critic** (how many steps it costs), **method-critic** (Lean, Theory of
Constraints, poka-yoke, jidoka, GTD, Kanban, 5S applied to this interface).

Its findings are handled two ways, decided with the user:

- **Mechanical and reversible → fixed without asking.** Tokens, spacing,
  missing labels, unwrapped tables, missing empty states, contrast, wording
  that breaks the voice.
- **Judgement → proposed first.** Anything that moves a layout, changes a
  workflow or the number of screens in it, renames a concept the user has
  learned, or adds a screen.

Review the screenshots, not only the diff. The 360 px column is where this UI
has broken before.

## Writing

Comments and documentation explain **why**, in plain words, for someone who
does not already know the code. No jargon from the codebase in anything the
user reads: not "entity", "ingest", "QC flag", "pipeline" — say value, add,
check. Errors name the file and the likely cause and end with what to try.
