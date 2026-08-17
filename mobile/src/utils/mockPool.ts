// #326/#327 — the mock-draft undrafted pool's filter + search composition,
// as a pure function (PRD R-11/R-13, reconciliation NB-3).
//
// COMPOSITION ORDER IS THE CONTRACT (operator decision): position filter
// first, then search — the search scopes to the currently active position
// subset, so a QB-only name under an RB filter finds NOTHING (switching to
// All finds it). Owning the order here keeps it in tested code instead of
// inline screen JSX.
//
// A player whose position is outside the four (edge case) appears only
// under All. Search is a case-insensitive substring match on the player's
// name (falling back to the id only when the name is empty — a row must
// stay findable by whatever string it renders); empty/whitespace query ⇒
// the filter subset unchanged. No debounce anywhere: the list is in-memory.
//
// Pure by design, zero runtime imports — mobile/tests/check-mock-g2-ui.js
// transpiles and CALLS it under plain node.

export const POOL_POSITIONS = ['QB', 'RB', 'WR', 'TE'] as const;

export type PoolPosition = (typeof POOL_POSITIONS)[number];
export type PoolPositionFilter = 'ALL' | PoolPosition;

export function filterPool<T extends { position: string; name: string; player_id: string }>(
  rows: readonly T[],
  position: PoolPositionFilter,
  query: string,
): T[] {
  const subset =
    position === 'ALL' ? [...rows] : rows.filter((r) => r.position === position);
  const q = query.trim().toLowerCase();
  if (!q) return subset;
  return subset.filter((r) => (r.name || r.player_id).toLowerCase().includes(q));
}
