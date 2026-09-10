# UI contract

What every screen in this application must satisfy. It exists because the UI
grew a page at a time with CSS appended per version, and there was nothing to
check new work against. This is that thing. `frontend/scripts/ui-check.mjs`
enforces the mechanical half; the `/design-pass` crew judges the rest.

The rule of the app: **it says where every number came from, and it never
guesses.** The interface has to carry that. A value the machine is unsure of
must look different from one it is sure of, and neither may be mistaken for
something the user typed.

---

## 1. Tokens

Colour, type and radius come from the custom properties at the top of
`frontend/src/styles.css`. **No hex, `rgb()` or named colour may appear
outside that `:root` block** (highlight overlays in `.hl*` are the one listed
exception, because they are deliberately translucent).

| Purpose | Token |
|---|---|
| Page background / panel / border | `--bg` `--panel` `--border` |
| Text / secondary text | `--text` `--muted` |
| Action, and its tint | `--accent` `--accent-soft` |
| Chrome (sidebar) | `--navy` `--navy-2` |
| Confirmed, needs attention, wrong | `--ok` `--warn` `--crit` (+ `-soft` tints) |
| Body / monospace | `--font` `--mono` |

Monospace (`--mono`, `.mono`) is for machine text only: file paths, IDs,
settings keys, log output, addresses. Never for prose.

## 2. Spacing and size

One scale, in px: **2, 4, 6, 8, 10, 12, 14, 16, 20, 24**. Anything else is a
mistake. Radius: 6 px controls, 8 px containers, 10–14 px pills.

Interactive targets are **at least 32 px high on a desktop pointer and 40 px
on a touch screen or below 860 px wide**. `.btn.sm` is the smallest allowed
control and only inside a dense table row.

Nothing that carries meaning is set below **12 px**, and nothing at all below
11 px. `.tag` sat at 10 px while carrying the whole confidence ladder.

The stylesheet still holds around thirty spacing values off this scale,
inherited from before it was written. `ui-check` reports them as warnings, not
errors: they are normalised as each rule is next touched, not in one sweep
that would move every screen at once.

## 3. Components

Use what exists before inventing:

| Need | Use | Not |
|---|---|---|
| A block of related content | `.card` (`.card.tight` when dense) | a bare `<div>` with padding |
| An action | `.btn`, `.btn.primary` (one per view), `.btn.sm`, `.btn.danger` | a styled `<a>` |
| A state word | `.badge` + `.ok`/`.warn`/`.crit`/`.accent` | coloured text |
| A verification note | `.tag` + `.ok`/`.warn`/`.crit` | a `.badge` |
| A message about what just happened | `.alert` + `.info`/`.ok`/`.warn`/`.crit` | text in a card |
| A choice among values | `.chip` | a `<select>` of one |
| Nothing to show yet | `.empty` | a blank panel |

**One primary action per view.** If two things look equally primary, neither is.

## 4. Every view needs four states

A screen is not finished until all four exist. `ui-check.mjs` looks for the
first two; the crew judges the rest.

1. **Empty** — no documents, no results, no blanks left. Says what to do next,
   not just "nothing here".
2. **Loading** — `.spinner` plus what is happening ("Reading page 3 of 12"),
   never a frozen screen. Anything over ~1 s needs progress, not a spinner.
3. **Error** — what failed, in the user's words, and the next thing to try.
   Never a raw exception, never "Failed to fetch" alone. Where the cause could
   be the machine rather than the app, offer the bug-report block
   (`LibraryPage.gatherReport`).
4. **Success** — the result is visible without a reload, or an `.alert.ok`
   says what happened and where the output went.

## 5. Tables

Tables carry the technical data, so they get their own rules:

- Every table lives in `.table-scroll` (or `.group`, which scrolls on
  narrow screens). A table must never widen the page.
- Columns that are context rather than substance — Manufacturer, Type,
  Uploaded — carry `hide-sm` so a phone shows what matters.
- Numbers with a unit stay one unbreakable string: `300 A`, not `300` `A`.
- A row that needs the user's attention is marked by a class on the row
  (`tr.fill-blank`), not by colouring individual cells.
- A blank value renders as `—` with `.muted`, never as an empty cell.

**Anything that scrolls sideways must show that it does** — an edge fade, a
shadow, something. A clipped tab strip is indistinguishable from the end of
the list, which is how the Diagram tab spent a release being invisible.

## 6. Confidence, and never guessing

The whole product rests on this, so it is a UI rule, not a data rule:

- A value read by two engines that agreed: **✓ 100%** with `.tag.ok` *2 readers*.
- Settled by a third read: **95%** with the note *3 reads* / *corrected*.
- Unsettled: the value is **blank** — `— to fill in` — never a guess, with the
  disagreeing readings shown beside it.
- One reader only: its own number, `.tag.warn` *1 reader*.
- Typed or confirmed by the user: **✓ 100%** *you*.

Nothing in the interface may present a machine reading with the same weight as
a human confirmation, and no number may appear without a route to its page.

Two rules follow, both learned the hard way:

- **An input is never pre-filled with what the machine read.** A box already
  holding a reading turns "press Enter" into recording that reading as the
  user's own. Offer it as a click beside the box instead.
- **One queue, one definition.** How many values are still waiting is decided
  in exactly one place — `frontend/src/verification.ts` and, on the server,
  `_refresh_counts` — and every badge, list and total uses it. The tab once
  said 6 while its own table listed 11.

*to fill in* is `--warn`, not `--crit`: values waiting for you are the normal
day's work. `--crit` stays for what is actually wrong, or it stops meaning
anything.

## 7. Responsive

One breakpoint: **860 px**. Below it the sidebar becomes a top bar, the
document viewer stacks (page above tabs), the calculator columns stack,
controls grow to 40 px, and `hide-sm` columns disappear. The page body must
never scroll sideways at 360 px.

Test widths: **360** (phone), **768** (tablet), **1440** (desktop).

## 8. Accessibility, the parts that matter here

- Every icon-only control has `aria-label` or `title`. `✕`, `↻` and `▯` mean
  nothing to a screen reader.
- Colour is never the only signal: a red row also carries words.
- Text on a token background meets 4.5:1. `--muted` on `--panel` passes;
  `--muted` on `--accent-soft` does not — use `--text` there.
- Anything clickable is a `<button>` or an `<a>`, so it can be tabbed to. A
  clickable `<tr>` also needs a real link inside it.
- Inputs have a `<label class="field">` with `.lbl`, or an `aria-label`.

## 9. Words

- Say what happened to *their document*, not what the software did:
  "Two readers disagreed on this value" beats "verification conflict".
- No jargon from the codebase in the UI: no "entity", "ingest", "QC flag",
  "pipeline". Say value, add, check.
- Errors name the file and the likely cause, and end with what to do.
- An error never guesses between causes the app could tell apart. "Failed to
  fetch" has three honest readings - the app is gone, the phone lost the PC,
  the file stopped being readable - and one three-second question to the
  server separates them. Never send the user to a page that cannot answer
  either (Diagnostics, when the server is the thing that is missing): name the
  log's path instead, remembered from the last time it could be asked.
- A control that stops or destroys something asks first and says what stops.
  It is never the only control on screen, and never the default button of a
  dialog: a box whose one button reads "OK" must do nothing but close.
- Sentence case for buttons and headings. No exclamation marks.
- Units and technical notation exactly as the document writes them: `4/0 AWG`,
  `mm²`, `300 A Class T`.

## 10. What "done" means for a UI change

1. `npm run ui:check` passes.
2. Screenshots at 360 / 768 / 1440 show no overflow, no clipped text, no
   overlapping controls (`npm run ui:shots`).
3. All four states of §4 exist for anything new.
4. `/design-pass` has run and its mechanical findings are fixed; its judgement
   calls have been put to the user.
