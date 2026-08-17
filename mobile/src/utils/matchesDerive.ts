// #334/#335 (G9) — pure derivations for MatchesScreen's render-layer
// pending-dismiss suppression and segment/chip counts.
//
// PURE BY DESIGN — zero runtime imports. mobile/tests/check-matches-counts.js
// transpiles this module and executes it under plain node (the
// check-trade-text.js idiom), so gaining a runtime import breaks the suite
// on purpose.
//
// Why visibility lives here and not in the query cache (#334, PRD R-1):
// a dismissed tile is removed from the TanStack cache optimistically, but
// six independent paths (mount refetch, pull-to-refresh, reconnect,
// league-switch invalidation, tab-press prefetch, TradesScreen's guide-v2
// fetchQuery) can rewrite that cache with a pre-dismiss server payload
// while the delayed dismiss POST is still pending. Filtering hidden keys at
// render time makes the tile's disappearance independent of cache contents:
// whatever a refetch writes, a hidden row cannot render.

/** Set of hidden-row keys held as MatchesScreen component state. */
export type HiddenKeys = ReadonlySet<string>;

// Key shapes are PREFIXED forms of the two FlatLists' keyExtractors so a
// match key can never collide with an awaiting key in the shared set.
export const matchHiddenKey = (matchId: string) => `match:${matchId}`;
export const awaitingHiddenKey = (leagueId: string, tradeId: string) =>
  `awaiting:${leagueId}:${tradeId}`;

// Row-level adapters for the filter call sites.
export const matchRowKey = (m: { match_id: string }) => matchHiddenKey(m.match_id);
export const awaitingRowKey = (a: { league_id: string; trade_id: string }) =>
  awaitingHiddenKey(a.league_id, a.trade_id);

/**
 * The single visibility predicate (R-1 + R-9): a row renders iff its key is
 * not hidden AND it passes the league filter ('all' = every league). Both
 * the rendered lists and every count derive through this — there is no
 * second source of truth for "what is visible".
 */
export function filterVisible<T extends { league_id: string }>(
  rows: readonly T[],
  leagueFilter: string,
  hiddenKeys: HiddenKeys,
  keyFn: (row: T) => string,
): T[] {
  return rows.filter(
    (r) =>
      !hiddenKeys.has(keyFn(r))
      && (leagueFilter === 'all' || r.league_id === leagueFilter),
  );
}

/**
 * Per-league counts of an ALREADY hidden-aware array (feed it filterVisible
 * output, never raw query data — R-8's single-source rule).
 *
 * R-10 — never fabricate: `undefined` input means the list's first fetch has
 * not resolved, and the answer is `null` ("render no count"), never a zero.
 * A resolved-but-empty list is a real `{}` whose lookups honestly read 0.
 */
export function countsByLeague<T extends { league_id: string }>(
  rows: readonly T[] | undefined,
): Record<string, number> | null {
  if (rows === undefined) return null;
  const out: Record<string, number> = {};
  for (const r of rows) out[r.league_id] = (out[r.league_id] || 0) + 1;
  return out;
}
