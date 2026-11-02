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

/**
 * R2 (action-banner ux-states §2) — the row a push / banner arrival names.
 * Index of the row whose `match_id` equals `matchId` in the array the
 * mutual FlatList renders, or -1 (not found: dismissed, expired, or not in
 * the loaded list — the caller then lands on the list quietly). Ids are
 * compared as strings: normalizeTradeMatch stringifies `match_id`, and the
 * screen stringifies the route param.
 */
export function indexForMatch(
  rows: readonly { match_id: string }[],
  matchId: string,
): number {
  return rows.findIndex((r) => r.match_id === matchId);
}

/**
 * R2 (ux-states §7 "When the match isn't there") — the not-found line, shown
 * when an arrival's match is missing after one refetch (dismissed, or gone
 * for any other reason; it never guesses why). Never on a failed or offline
 * fetch. The words are marketing's already-approved string, reused
 * (org-bringup leads/marketing-lead-copy.md:735; picked by head-bizops,
 * 2026-11-01) — the same line as the deck's withdrawn card
 * (components/TradeDeckStates.tsx WITHDRAWN_REASON). `null` would mean no line.
 */
export const MATCH_NOT_FOUND_LINE: string | null = 'This trade is no longer available.';

/** ~4 s, so a whole line can be read (§7). */
export const NOT_FOUND_HOLD_MS = 4000;

/**
 * The Toast for the not-found line, or null for no line. Neutral tone (the
 * Toast default), held NOT_FOUND_HOLD_MS. `null` in → nothing renders;
 * a string in → exactly that string.
 */
export function notFoundToast(
  line: string | null,
): { msg: string; holdMs: number } | null {
  return line ? { msg: line, holdMs: NOT_FOUND_HOLD_MS } : null;
}

/**
 * R2 — floor a scroll target at 0 and cap it at the content end
 * (`maxOffset` = content length − visible length; null when not yet known),
 * so an estimate never scrolls past either edge.
 */
export function clampOffset(offset: number, maxOffset: number | null): number {
  const floored = Math.max(0, offset);
  return maxOffset == null ? floored : Math.min(floored, Math.max(0, maxOffset));
}

/**
 * R2 — where onScrollToIndexFailed jumps before its retry: the row's
 * estimated top (the list's top padding + index × average cell length,
 * which already includes each separator) minus viewOffset, clamped. null
 * when nothing is measured yet (average 0, a fresh mount): no jump, and the
 * retry runs once the first cells have laid out. (VirtualizedList starts
 * highestMeasuredFrameIndex at 0, not -1, so a "step to the furthest
 * measured row" here was always scrollToIndex(0) — a no-op on a fresh
 * mount — and is gone.)
 */
export function scrollFailureJump(
  info: { index: number; averageItemLength: number },
  padTop: number,
  viewOffset: number,
  maxOffset: number | null,
): number | null {
  if (!(info.averageItemLength > 0)) return null;
  return clampOffset(padTop + info.averageItemLength * info.index - viewOffset, maxOffset);
}

/**
 * R2 — is the arrival row already in view with room for the mark's top
 * stroke, so it needn't scroll (§7 step 4)? `fullyVisible` holds the keys of
 * cells that are 100% on screen (a cell is the row plus the separator below
 * it). Row 0's top sits at the list's top padding, so it clears when
 * padTop − scrollY ≥ viewOffset. Any other row clears when the row above it
 * is fully visible too, which puts at least that row and a separator above
 * it. Otherwise it scrolls with viewOffset as usual.
 */
export function alreadyInView(
  index: number,
  rowKey: string,
  prevKey: string | null,
  fullyVisible: ReadonlySet<string>,
  scrollY: number,
  padTop: number,
  viewOffset: number,
): boolean {
  if (!fullyVisible.has(rowKey)) return false;
  if (index === 0) return padTop - scrollY >= viewOffset;
  return prevKey != null && fullyVisible.has(prevKey);
}

/**
 * R2 — VirtualizedList never clamps scrollToIndex, so a tail row's
 * viewPosition-0 target can ask for an offset past the content end. On iOS,
 * Fabric's scrollTo already clamps to the content bounds
 * (RCTScrollViewComponentView.mm `scrollTo:y:animated:`), so this never
 * fires there; it stays as a guard should the list ever allow overflow
 * (scrollToOverflowEnabled). Given a settled scroll, the end offset to pull
 * back to, or null when it's within bounds (1pt tolerance).
 */
export function endClamp(
  offsetY: number,
  contentLength: number,
  visibleLength: number,
): number | null {
  const max = Math.max(0, contentLength - visibleLength);
  return offsetY > max + 1 ? max : null;
}
