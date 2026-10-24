// Time to trade suggestion (#339 §4.6, AC-L1) — the pure parts of the
// search trace: the R1 source vocabulary and the values R2/R2b carry.
// Contract: docs/business/analytics/2026-10-20-time-to-suggestion-events.md
// (addendum v2 @ 255dd832, analytics-lead ruling 30). Props, classes and
// source values are exactly as listed there.
//
// Pure and dependency-free BY CONTRACT: no React, no I/O, no module state and
// no runtime imports. tests/check-trade-first-card-events.js transpiles this
// file and runs it under plain node; a runtime import added here breaks it.

/** R1 `source` values (addendum "R1 source values"). Absent = the deck's own
 *  Find a Trade button (start-only since D13). */
export type R1Source =
  | 'deck_error_retry'
  | 'prefs_changed_strip'
  | 'deck_summary_unpin'
  | 'deck_search_all'
  | 'calculator'
  | 'league_offer'
  | 'league_target'
  | 'usage_trends'
  | 'deep_link'
  | 'end_card_adjust';

export type SearchType = 'organic' | 'pinned' | 'fair_sweep';
export type ServeSource = 'device' | 'page' | 'cached' | 'joined' | 'fresh';
/** R2b `reason`. `timeout` = FIRST_CARD_TIMEOUT_MS from the tap, no card. */
export type FirstCardFailure = 'empty' | 'error' | 'abandoned' | 'timeout';
export const FIRST_CARD_TIMEOUT_MS = 10_000;
/** T1: the card must be at least this much on screen. */
export const FIRST_CARD_MIN_VISIBLE = 0.5;
export type LaunchState = 'cold_launch' | 'first_tap' | 'repeat_tap';
export type NetworkType = 'wifi' | 'cellular' | 'offline' | 'unknown';

/** `search_type`: a fair sweep is its own kind; a model search is `organic`
 *  only with no pinned asset, no partner and no shape intent (the default
 *  deck the page store serves, P1's "organic body"); otherwise `pinned`. */
export function searchTypeOf(s: {
  fair?: boolean;
  giveIds?: readonly string[];
  receiveIds?: readonly string[];
  opponentId?: string | null;
  intent?: string | null;
}): SearchType {
  if (s.fair) return 'fair_sweep';
  const targeted = (s.giveIds?.length ?? 0) > 0
    || (s.receiveIds?.length ?? 0) > 0
    || !!s.opponentId
    || !!s.intent;
  return targeted ? 'pinned' : 'organic';
}

/** `launch_state` (T3): a tap before this process's session-init completed
 *  is `cold_launch`; after it, the process's first search is `first_tap` and
 *  every later one `repeat_tap`. */
export function launchStateFor(s: { sessionInitDone: boolean; priorSearches: number }): LaunchState {
  if (!s.sessionInitDone) return 'cold_launch';
  return s.priorSearches === 0 ? 'first_tap' : 'repeat_tap';
}

/** `network_type` from NetInfo's state: its `type`, with a known-dead
 *  connection reported as `offline` (AC-L1's cells drop offline/unknown). */
export function networkTypeOf(s: { type?: string | null; isConnected?: boolean | null } | null | undefined): NetworkType {
  if (!s) return 'unknown';
  if (s.isConnected === false || s.type === 'none') return 'offline';
  if (s.type === 'wifi') return 'wifi';
  if (s.type === 'cellular') return 'cellular';
  return 'unknown';
}

/** `serve_source`: the server's own value when it sends one (P1 `page`);
 *  else inferred from the search's FIRST response — complete on arrival ⇒
 *  `cached`, still running but already holding cards ⇒ `joined` (an
 *  in-flight job), otherwise `fresh`. (`device` arrives with pass C.) */
export function inferServeSource(first: {
  serve_source?: string;
  status: 'running' | 'complete' | 'error';
  cardCount: number;
}): string {
  if (first.serve_source) return first.serve_source;
  if (first.status === 'complete') return 'cached';
  if (first.status === 'running' && first.cardCount > 0) return 'joined';
  return 'fresh';
}

/** Share of a laid-out card inside the viewport [viewTop, viewBottom]. */
export function visibleFraction(top: number, height: number, viewTop: number, viewBottom: number): number {
  if (!(height > 0)) return 0;
  const shown = Math.min(top + height, viewBottom) - Math.max(top, viewTop);
  return Math.max(0, Math.min(1, shown / height));
}

/** The deck `mode` (#298) a hand-off will land on, decided at the tap the
 *  way TradesScreen derives `deckMode` (one pin, targeting and asset ideas
 *  on, not the first run ⇒ the single-pin featured surface). */
export function deckModeForPins(s: {
  pinCount: number;
  targeting: boolean;
  assetIdeas: boolean;
  firstRun: boolean;
}): 'single_pin' | 'deck' {
  return s.pinCount === 1 && s.targeting && s.assetIdeas && !s.firstRun ? 'single_pin' : 'deck';
}
