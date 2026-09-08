---
name: design-pass
description: Review the UI against docs/UI.md with three agents (ui-critic, flow-critic, method-critic), fix the mechanical findings, and bring the judgement calls to the user. Use before committing any change under frontend/, when the user asks for a design or UX review, or when they say the UI has flaws.
---

# Design pass

The UI of this project grew one page at a time with CSS appended per version,
and nothing checked new work against anything. This is that check. It runs on
**every change under `frontend/`, before the commit**, and on the whole app
before a release.

Argument: `/design-pass` reviews what changed since the last release tag;
`/design-pass all` sweeps every screen.

## 1. Look at it

Never review from source alone.

```bash
cd frontend && npm run ui:check          # tokens, tables, a11y, states
cd frontend && npm run ui:shots          # 360/768/1440 shots of every screen
```

`ui:shots` needs Playwright, deliberately kept out of `package.json` so no CI
job downloads a browser: `cd frontend && npm i --no-save playwright`. It
starts its own scratch backend, feeds it the sample documents and shoots
every route into `frontend/.ui-shots/` (git-ignored). It exits non-zero if any
page scrolls sideways.

If `ui:shots` cannot run (no network for Playwright), say so plainly in the
report rather than reviewing blind.

## 2. Three agents, one message

Launch **ui-critic**, **flow-critic** and **method-critic** in a single
message so they run in parallel. Give each:

- the scope — `git diff --name-only $(git describe --tags --abbrev=0)..HEAD -- frontend/`,
  or all of `frontend/src` for a sweep;
- the `ui:check` output;
- the path `frontend/.ui-shots/` and the note that the images are to be read,
  not just listed;
- `docs/UI.md` as the standard.

Their briefs live in `.claude/agents/`; do not restate them.

## 3. Triage

**Fix silently** — mechanical and reversible:

- colour literals that should be tokens; spacing off the scale in rules you
  are already touching;
- missing `aria-label`/`title` on icon-only controls;
- tables not wrapped in `.table-scroll`; missing `hide-sm` on context columns;
- missing `.empty` states; blanks rendered as an empty cell instead of `—`;
- contrast fixes; wording that breaks the voice in `docs/UI.md` §9.

Then re-run `ui:check` and `ui:shots` and **confirm the fix in the picture**,
not in the diff.

**Ask first** — anything that moves or restructures a layout, changes a
workflow or the number of screens in it, renames a concept the user has
learned, or adds a screen. Use `AskUserQuestion` when there is a genuine
choice between approaches; otherwise put a numbered list in the reply.

Never apply a proposal that would present a machine reading as confidently as
a human confirmation, or fill a blank with a guess — whatever it saves.

## 4. Report

Short enough to read in two minutes:

1. One-paragraph verdict: is this shippable as it stands?
2. What was fixed — one line each.
3. Numbered proposals needing a decision, most valuable first, each with what
   it buys and what it costs.
4. Anything `docs/UI.md` should gain so this class of flaw cannot recur. Add
   it to the file in the same commit; a rule learned and not written down is
   a rule that will be broken again.

## 5. Before the commit

`npm run ui:check` clean, `npm run build` passing, and the 360 px screenshots
re-checked. Then commit the UI fixes together with any `docs/UI.md` update.
