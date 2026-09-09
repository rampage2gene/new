import type { DocumentSummary, Entity } from "./types";

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
