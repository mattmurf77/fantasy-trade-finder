// Time to trade suggestion (#339 §4.6, AC-L1) — the per-search trace.
//
// One search = one client `search_id`, minted AT THE TAP on a search-starting
// control (#339 table A) together with the tap's monotonic timestamp. The
// same id rides `/api/trades/generate` (`search_id`, E2) and every event of
// that search, so a tap, its server job and its first card join on one key.
// Contract: docs/business/analytics/2026-10-20-time-to-suggestion-events.md
// (addendum v2 @ 255dd832). R1 = `find_trades_tapped` (+ `search_id`).
//
// Why a module and not screen state: the tap and the deck that answers it
// are usually different screen instances — the canvas Find a Trade taps on
// the landing and the pushed TradeDeck shows the card; a League Summary or
// Usage Trends hand-off taps on another tab. The tap begins the trace here;
// the deck that dispatches the search CLAIMS it (claimPendingSearch), so the
// request carries the tap's id.
//
// Clock: `performance.now()` only — monotonic, immune to wall-clock jumps.
// Never Date.now(), and never api/client.ts `_clockMs()`, whose fallback is
// Date (AC-L1 needs a monotonic delta).
import { track } from '../api/events';
import { uuidv4 } from '../api/_queue';
import { sessionInitCompletedThisProcess } from '../api/auth';
import { useFeatureFlags, onboardingEnabled } from './useFeatureFlags';
import { useOnboardingState } from './useOnboardingState';
import {
  deckModeForPins,
  launchStateFor,
  type LaunchState,
  type R1Source,
  type SearchType,
} from '../utils/firstCardEvent';

export interface TradeSearchTrace {
  searchId: string;
  /** performance.now() at the tap. */
  tapAt: number;
  entryPoint?: R1Source;
  searchType: SearchType;
  launchState: LaunchState;
}

/** Monotonic milliseconds (Hermes always provides `performance.now`). */
export function monotonicNow(): number {
  return (globalThis as { performance: { now: () => number } }).performance.now();
}

const traces = new Map<string, TradeSearchTrace>();
let pending: TradeSearchTrace | null = null;
let searchesThisProcess = 0;

/** R1 — call AT THE TAP of a search-starting control. Mints the search id,
 *  stamps the tap, emits `find_trades_tapped {source, mode, search_id}` and
 *  parks the search for the deck that will dispatch it. Returns the id. */
export function beginTradeSearch(o: {
  source?: R1Source;
  mode: 'single_pin' | 'deck';
  searchType: SearchType;
  screen: string;
}): string {
  const trace: TradeSearchTrace = {
    searchId: uuidv4(),
    tapAt: monotonicNow(),
    entryPoint: o.source,
    searchType: o.searchType,
    launchState: launchStateFor({
      sessionInitDone: sessionInitCompletedThisProcess(),
      priorSearches: searchesThisProcess,
    }),
  };
  searchesThisProcess += 1;
  traces.set(trace.searchId, trace);
  pending = trace;
  // `source` is absent for the deck's own Find a Trade (JSON drops undefined).
  track('find_trades_tapped', { source: o.source, mode: o.mode, search_id: trace.searchId }, o.screen);
  return trace.searchId;
}

/** The search a dispatch should carry: the tap that is waiting for one, or
 *  null when nothing was tapped (a regeneration, a first-run auto-start). */
export function claimPendingSearch(): string | null {
  const p = pending;
  pending = null;
  return p ? p.searchId : null;
}

/** A dispatch already made with this id (the landing's page-1 request that
 *  the pushed deck adopted): it is no longer waiting for one. */
export function claimSearch(searchId: string | undefined | null): void {
  if (searchId && pending?.searchId === searchId) pending = null;
}

/** The tap's search will never be dispatched (the user left the screen
 *  before it ran). */
export function dropPendingSearch(searchId: string): void {
  if (pending?.searchId === searchId) pending = null;
}

export function traceFor(searchId: string | null | undefined): TradeSearchTrace | undefined {
  return searchId ? traces.get(searchId) : undefined;
}

/** R1 `mode` for a hand-off tap: the deck surface it lands on, decided the
 *  way TradesScreen's `deckMode` is (one pin + targeting + asset ideas, not
 *  the first run ⇒ single_pin). Read imperatively; no hook. */
export function handoffDeckMode(pinCount: number): 'single_pin' | 'deck' {
  const flags = useFeatureFlags.getState().flags;
  const ob = useOnboardingState.getState();
  return deckModeForPins({
    pinCount,
    targeting: !!flags['trade.finder_targeting'],
    assetIdeas: !!flags['trade.asset_ideas'],
    firstRun: onboardingEnabled('onboarding.trades_first') && ob.hydrated && !ob.ob.firstSwipeDone,
  });
}
