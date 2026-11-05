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
//
// R2 `trade_first_card_shown` / R2b `trade_first_card_failed`: EXACTLY ONE
// per search_id (`settled`). R2 is reported by the deck at T1 (TradesScreen
// measures the card); R2b comes from the deck (empty, error, abandoned on
// blur/unmount) or from here (`timeout` 10 s after the tap; `abandoned` when
// the app leaves `active` before a card, T4, or a newer tap supersedes it).
import { AppState } from 'react-native';
import NetInfo from '@react-native-community/netinfo';
import { track } from '../api/events';
import { uuidv4 } from '../api/_queue';
import { sessionInitCompletedThisProcess } from '../api/auth';
import { useFeatureFlags, onboardingEnabled } from './useFeatureFlags';
import { useOnboardingState } from './useOnboardingState';
import { recordTapTiming } from '../utils/tapTiming';
import {
  deckModeForPins,
  FIRST_CARD_TIMEOUT_MS,
  inferServeSource,
  launchStateFor,
  networkTypeOf,
  type FirstCardFailure,
  type LaunchState,
  type NetworkType,
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
  /** The tap's network (the AC-L1 cell it belongs to). */
  networkType: NetworkType;
  /** From the search's first response (noteFirstResponse). */
  serveSource?: string;
  freshnessState?: string;
  jobId?: string;
  /** R2 or R2b sent: nothing more is ever sent for this id. */
  settled: boolean;
  /** performance.now() at R2. */
  firstCardAt?: number;
  timer: ReturnType<typeof setTimeout> | null;
}

// NetInfo's latest state, cached so the tap reads it synchronously. The
// listener is registered once at module scope (module lifetime, no leak).
let netState: { type?: string | null; isConnected?: boolean | null } | null = null;
try {
  NetInfo.addEventListener((s) => { netState = s; });
} catch {
  /* no NetInfo: network_type reads `unknown` */
}
export function currentNetworkType(): NetworkType {
  return networkTypeOf(netState);
}

/** Monotonic milliseconds (Hermes always provides `performance.now`). */
export function monotonicNow(): number {
  return (globalThis as { performance: { now: () => number } }).performance.now();
}

const traces = new Map<string, TradeSearchTrace>();
let pending: TradeSearchTrace | null = null;
let searchesThisProcess = 0;

// Bounded for the life of the process: each new tap drops the OLDEST settled
// traces beyond the MAX_SETTLED_TRACES most recent (Map insertion order is
// tap order), with their deck_buffer_empty marks. An unsettled trace is never
// dropped: its R2/R2b is still owed.
const MAX_SETTLED_TRACES = 20;
function pruneSettledTraces(): void {
  let excess = -MAX_SETTLED_TRACES;
  for (const t of traces.values()) if (t.settled) excess += 1;
  if (excess <= 0) return;
  for (const [id, t] of traces) {
    if (excess <= 0) break;
    if (!t.settled) continue;
    traces.delete(id);
    bufferEmptyReported.delete(id);
    excess -= 1;
  }
}

/** R1 — call AT THE TAP of a search-starting control. Mints the search id,
 *  stamps the tap, emits `find_trades_tapped {source, mode, search_id}` and
 *  parks the search for the deck that will dispatch it. Returns the id. */
export function beginTradeSearch(o: {
  source?: R1Source;
  mode: 'single_pin' | 'deck';
  searchType: SearchType;
  screen: string;
}): string {
  pruneSettledTraces();
  // A newer tap supersedes every search still waiting for its first card.
  for (const t of traces.values()) {
    if (!t.settled) failFirstCard(t.searchId, 'abandoned');
  }
  const trace: TradeSearchTrace = {
    searchId: uuidv4(),
    tapAt: monotonicNow(),
    entryPoint: o.source,
    searchType: o.searchType,
    launchState: launchStateFor({
      sessionInitDone: sessionInitCompletedThisProcess(),
      priorSearches: searchesThisProcess,
    }),
    networkType: currentNetworkType(),
    settled: false,
    timer: null,
  };
  searchesThisProcess += 1;
  traces.set(trace.searchId, trace);
  pending = trace;
  trace.timer = setTimeout(() => failFirstCard(trace.searchId, 'timeout'), FIRST_CARD_TIMEOUT_MS);
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
 *  before it ran): it ends as `abandoned`. */
export function dropPendingSearch(searchId: string): void {
  if (pending?.searchId === searchId) pending = null;
  failFirstCard(searchId, 'abandoned');
}

/** The search still waiting for its first card, if any (a newer tap
 *  abandons every older one, so there is at most one). The paywall router's
 *  gate listener settles it with R2b `paywall` / `verify` (#393 M2). */
export function openSearchId(): string | null {
  let open: string | null = null;
  for (const t of traces.values()) if (!t.settled) open = t.searchId;
  return open;
}

export function isSearchOpen(searchId: string | null | undefined): boolean {
  const t = searchId ? traces.get(searchId) : undefined;
  return !!t && !t.settled;
}

/** The search's FIRST response (generate, an adopted page, a fair sweep):
 *  what R2/R2b report as serve_source, freshness_state and job_id. First
 *  wins, except `replace`: the automatic re-search's answer (#525) replaces
 *  it while the trace is still open, so R2 names the job and source that
 *  produced the first card, not the revoked one (analytics-lead). A settled
 *  trace never changes. */
export function noteFirstResponse(searchId: string | null | undefined, first: {
  serve_source?: string;
  freshness_state?: string;
  status: 'running' | 'complete' | 'error';
  cardCount: number;
  job_id?: string;
}, opts?: { replace?: boolean }): void {
  const t = searchId ? traces.get(searchId) : undefined;
  if (!t) return;
  if (t.serveSource !== undefined && !(opts?.replace && !t.settled)) return;
  t.serveSource = inferServeSource(first);
  t.freshnessState = first.freshness_state;
  t.jobId = first.job_id || undefined;
}

function settle(t: TradeSearchTrace): number {
  t.settled = true;
  if (t.timer) clearTimeout(t.timer);
  t.timer = null;
  if (pending === t) pending = null;
  return Math.round(monotonicNow() - t.tapAt);
}

/** R2 — T1, reported by the deck at the first frame its real card is
 *  ≥ 50% visible with Like and Pass enabled. Once per search_id. */
export function reportFirstCardShown(searchId: string, o: { cardIndex: number }): void {
  const t = traces.get(searchId);
  if (!t || t.settled) return;
  const ms = settle(t);
  t.firstCardAt = monotonicNow();
  // The Testing readout's last value (in memory only; ruling 11).
  recordTapTiming({
    msFromTap: ms, networkType: t.networkType, launchState: t.launchState, serveSource: t.serveSource,
  });
  track('trade_first_card_shown', {
    search_id: t.searchId,
    ms_from_tap: ms,
    entry_point: t.entryPoint,
    search_type: t.searchType,
    launch_state: t.launchState,
    network_type: t.networkType,
    serve_source: t.serveSource,
    freshness_state: t.freshnessState,
    job_id: t.jobId,
    card_index: o.cardIndex,
  }, 'Trades');
}

/** R2b — instead of R2: empty | error | abandoned | timeout | paywall |
 *  verify. Once per search_id, and never after an R2. */
export function failFirstCard(searchId: string, reason: FirstCardFailure): void {
  const t = traces.get(searchId);
  if (!t || t.settled) return;
  const ms = settle(t);
  track('trade_first_card_failed', {
    search_id: t.searchId,
    ms_from_tap: ms,
    reason,
    entry_point: t.entryPoint,
    search_type: t.searchType,
    launch_state: t.launchState,
    network_type: t.networkType,
    serve_source: t.serveSource,
  }, 'Trades');
}

// `deck_buffer_empty` (granted, ruling 30): the user reached the last ready
// card while the deck is still building and no next page is local — an
// AC-L4 failure. At most once per search_id.
const bufferEmptyReported = new Set<string>();
export function reportDeckBufferEmpty(searchId: string, o: { deckId?: string; cardsSeen: number }): void {
  if (!searchId || bufferEmptyReported.has(searchId)) return;
  bufferEmptyReported.add(searchId);
  const t = traces.get(searchId);
  track('deck_buffer_empty', {
    search_id: searchId,
    deck_id: o.deckId,
    cards_seen: o.cardsSeen,
    ms_since_first_card: t?.firstCardAt !== undefined ? Math.round(monotonicNow() - t.firstCardAt) : undefined,
    network_type: currentNetworkType(),
  }, 'Trades');
}

// T4 — leaving `active` (background, or iOS's inactive app switcher) before
// a card ends every open search as `abandoned`, never a long R2.
try {
  AppState.addEventListener('change', (state) => {
    if (state === 'active') return;
    for (const t of traces.values()) {
      if (!t.settled) failFirstCard(t.searchId, 'abandoned');
    }
  });
} catch {
  /* no AppState (tests): nothing to listen to */
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
