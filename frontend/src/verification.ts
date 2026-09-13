import type { DocumentSummary, Entity, QCFlag } from "./types";

/** What counts as still waiting for the user, in one place.
 *
 *  There used to be two answers on the same screen: the tab badge added up the
 *  document's stored counts while the list below it used its own rule, so one
 *  document showed 6 in the badge and 11 rows in the table. A queue whose size
 *  the app cannot state consistently is not a queue anyone can trust.
 *
 *  The rule is the honest one: a value is still open only if nobody has
 *  settled it. Left blank because the readers disagreed, or resting on a
 *  single reading. A value two of three reads corrected is settled - it is
 *  shown with its "corrected" tag in the list below, not counted as work.
 */
const OPEN_STATUSES = new Set(["to_fill", "single", "unverified"]);

export function isOpen(e: Entity): boolean {
  return !e.verified && OPEN_STATUSES.has(e.verification?.status ?? "");
}

/** The same rule from a document's stored counts, for screens that hold
 *  summaries rather than values (the library). `_refresh_counts` in
 *  `backend/app/api/entities_edit.py` recomputes both after every edit with
 *  exactly this meaning, so the two agree and both fall to zero. */
export function openCount(doc: { stats?: DocumentSummary["stats"] }): number {
  return (doc.stats?.to_fill || 0) + (doc.stats?.verification?.unverified || 0);
}

/** Blanks first, then single readings, then by page: the order the user
 *  should work in. Blanks are the only values the app refuses to guess, so
 *  they are the ones that hold up an export. */
export function openFirst(a: Entity, b: Entity): number {
  const rank = (e: Entity) => (e.verification?.status === "to_fill" ? 0 : 1);
  return rank(a) - rank(b) || a.page - b.page;
}

/** The distinct things the readers saw, for "read as A / B". */
export function readingsOf(e: Entity): string[] {
  return Array.from(new Set(Object.values(e.verification?.readings || {}).filter(Boolean) as string[]));
}

export interface Ask { kind: "blank" | "confirm" | "settled"; what: string; todo: string }

/** What the app is asking of the person for this value, in the same words
 *  on every screen.
 *
 *  A row that just says "to fill in" or shows a 1-reader tag leaves the
 *  reader to work out what happened and what they are supposed to do; that
 *  is how a whole release went by with the user not knowing what was being
 *  asked. So every value carries two sentences: *what* happened to it and
 *  *what to do*, and every tab prints these rather than its own version. */
export function ask(e: Entity): Ask {
  const seen = readingsOf(e);
  const page = `page ${e.page}`;
  if (e.verified) return { kind: "settled", what: "Confirmed by you.", todo: "" };
  switch (e.verification?.status) {
    case "to_fill":
      return {
        kind: "blank",
        what: seen.length > 1
          ? `The two readers disagreed (${seen.join(" / ")}), so nothing was kept.`
          : "The readers could not agree on this value, so nothing was kept.",
        todo: `Look at ${page} and type what it says.`,
      };
    case "single":
    case "unverified":
      return {
        kind: "confirm",
        what: `Only one reader could see this spot; it read “${e.value_text}”.`,
        todo: `If ${page} shows “${e.value_text}”, press Confirm. If not, type the right value.`,
      };
    case "confirmed":
      return { kind: "settled", what: e.verification.note === "2 readers" ? "Two readers agreed." : "A majority of three readings agreed.", todo: "" };
    case "corrected":
    case "ai_corrected":
      return { kind: "settled", what: `Was ${e.verification.original}; two other readings agreed on ${e.value_text}.`, todo: "" };
    case "ai_confirmed":
      return { kind: "settled", what: "Confirmed by the AI reading the page.", todo: "" };
    default:
      return { kind: "settled", what: "Taken from the PDF's own text.", todo: "" };
  }
}

/** A verification flag's kind in plain words. The raw type names are for
 *  the log, not the screen. */
export function flagLabel(type: string): string {
  const names: Record<string, string> = {
    reader_stopped: "reader stopped on this page",
    unit_out_of_range: "value outside the usual range",
    nonstandard_size: "unusual wire size",
    nonstandard_value: "unusual value",
    awg_ambiguity: "AWG or metric?",
    awg_cross_reference: "two wire sizes for one cable",
    discrepancy: "two readings disagree",
    low_ocr_confidence: "low OCR confidence",
    reading_conflict: "two readings disagree",
    reading_unverified: "one reading only",
    reading_corrected: "reading was corrected",
  };
  return names[type] || type.replace(/_/g, " ");
}

/** What to do about a flag, in one line. `e` is the value the flag is about,
 *  when it is about one. */
export function flagTodo(f: QCFlag, e?: Entity): string {
  const page = f.page ? `page ${f.page}` : "the page";
  if (e) {
    if (e.verified) return "Nothing: you have already confirmed this value.";
    const a = ask(e);
    if (a.kind === "blank") return `Open ${page} and type what it says in the box below.`;
    return `Open ${page}. If it shows “${e.value_text}”, press Confirm; if not, type the right value in To fill in.`;
  }
  switch (f.flag_type) {
    case "reader_stopped":
      return `Open ${page} and check its values in Technical data; Re-verify (in To fill in) reads it with both readers again.`;
    default:
      return `Open ${page}, read the note, and press “I've checked this” when you have.`;
  }
}
