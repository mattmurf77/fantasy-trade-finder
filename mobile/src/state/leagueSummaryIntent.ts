import { create } from 'zustand';
import { useSession } from './useSession';
import type { SplitPos, SplitSide } from '../utils/positionSplit';

// Home hub (flag `nav.home_hub`; docs/plans/home-engagement/scope.md) — the
// one-shot arrival intent for League rankings (LeagueSummaryScreen, League
// tab root `LeagueRankings`).
//
// WHY A STORE AND NOT ROUTE PARAMS: same contract as useFinderTargets'
// handoff (#330). League rankings is a tab-stack ROOT that stays mounted
// across tab switches and keeps its own filter/basis/drill-in state, so the
// arrival has to be consumed by the screen on focus, exactly once, and a
// repeat tap on the same Home tile must still re-fire. `seq` is the per-
// intent nonce that makes it re-fire; it is store-internal and monotonic.
//
// TWO KINDS:
//   * 'split' — a Home position tile's Buy or Sell. The consumer resets to
//     basis Consensus, subset All, filter {position}, closes any drill-in
//     (scope W2), shows the pinned Buy/Sell banner, and scrolls: 'buy' to the
//     TOP OF THE LIST (deepest first), 'sell' to the END (shortest last).
//   * 'all' — Home's Overall rank row. Same reset with NO position filter,
//     no banner, scrolled to the top: "5th of 12" is a consensus/All number,
//     so the list it opens on must be that list.
//
// Lifecycle: set only by HomeScreen; taken (and nulled) only by
// LeagueSummaryScreen's tab-root registration. A take for a different league
// discards it. A league switch clears it (subscription below). Never
// persisted — an arrival must not replay on a cold start.

export type LeagueSummaryIntent =
  | { kind: 'split'; leagueId: string; position: SplitPos; side: SplitSide; seq: number }
  | { kind: 'all'; leagueId: string; seq: number };

export type LeagueSummaryIntentInput =
  | { kind: 'split'; leagueId: string; position: SplitPos; side: SplitSide }
  | { kind: 'all'; leagueId: string };

interface LeagueSummaryIntentState {
  pending: LeagueSummaryIntent | null;
  /** Stamps `seq` internally — callers never supply it. */
  set: (i: LeagueSummaryIntentInput) => void;
  /** One-shot consume. Returns the pending intent iff it is for `leagueId`,
   *  and clears it either way (a stale intent for another league is dropped). */
  take: (leagueId: string | null | undefined) => LeagueSummaryIntent | null;
  clear: () => void;
}

// Module-level so it survives clear(): "seq changed" always means "a new intent".
let _intentSeq = 0;

export const useLeagueSummaryIntent = create<LeagueSummaryIntentState>((set, get) => ({
  pending: null,
  set: (i) => set({ pending: { ...i, seq: ++_intentSeq } as LeagueSummaryIntent }),
  take: (leagueId) => {
    const p = get().pending;
    if (!p) return null;
    set({ pending: null });
    return leagueId && p.leagueId === leagueId ? p : null;
  },
  clear: () => set({ pending: null }),
}));

/** Home's Buy/Sell buttons. */
export function requestLeagueSummarySplit(
  leagueId: string,
  position: SplitPos,
  side: SplitSide,
): void {
  useLeagueSummaryIntent.getState().set({ kind: 'split', leagueId, position, side });
}

/** Home's Overall rank row. */
export function requestLeagueSummaryAll(leagueId: string): void {
  useLeagueSummaryIntent.getState().set({ kind: 'all', leagueId });
}

/** Non-hook consume for effects. */
export function takeLeagueSummaryIntent(
  leagueId: string | null | undefined,
): LeagueSummaryIntent | null {
  return useLeagueSummaryIntent.getState().take(leagueId);
}

// League switch (or sign-out) invalidates any pending arrival.
let _prevLeagueId: string | null | undefined;
useSession.subscribe((s) => {
  const id = s.league?.league_id ?? null;
  if (_prevLeagueId === undefined) {
    _prevLeagueId = id;
    return;
  }
  if (id !== _prevLeagueId) {
    _prevLeagueId = id;
    useLeagueSummaryIntent.getState().clear();
  }
});
