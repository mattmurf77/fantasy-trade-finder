// #322/#325 — the mock-draft ticker's window, as a pure function.
//
// The "Just picked / Since your last pick" section renders the last `depth`
// picks ASCENDING by pick_no: the earliest of the window at the top, the
// newest at the bottom — 1.01 is literally the top row from the first pick
// on, the section grows one fixed-height row per pick until it holds
// `depth`, and from then on each new pick appears at the bottom while the
// earliest visible row falls off the top.
//
// The ascending sort inside is DEFENSIVE, not decorative (PRD R-1 / NB-2):
// `picks[]` arrives in pick order today by construction (`next_pick` walks
// slots sequentially), but nothing pins that server-side — sorting here
// makes the window's ordering a LOCAL guarantee instead of an unpinned
// assumption.
//
// `firstNewIndex` is the highlight boundary (PRD R-4): in ascending order
// the "new since your last pick" rows sit at the BOTTOM, so row `i` is
// tinted iff (not mine and) `i >= firstNewIndex`, where
// `firstNewIndex = rows.length - min(newest, rows.length)`. `newest === 0`
// ⇒ `firstNewIndex === rows.length` ⇒ no row tinted. The off-by-one lives
// here, in one tested place — never inline in the screen.
//
// Pure by design, zero runtime imports — mobile/tests/check-mock-g2-ui.js
// transpiles and CALLS it under plain node.

export interface TickerWindowResult<T> {
  /** The visible rows, ascending by `pick_no`, at most `depth` of them. */
  rows: T[];
  /** First tint-eligible index; `rows.length` when nothing is new. */
  firstNewIndex: number;
}

export function tickerWindow<T extends { pick_no: number }>(
  picks: readonly T[],
  depth: number,
  newest: number,
): TickerWindowResult<T> {
  const rows = [...picks].sort((a, b) => a.pick_no - b.pick_no).slice(-depth);
  const bounded = Math.min(Math.max(newest, 0), rows.length);
  return { rows, firstNewIndex: rows.length - bounded };
}
