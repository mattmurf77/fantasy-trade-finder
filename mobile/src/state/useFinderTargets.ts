import { create } from 'zustand';
import { useSession } from './useSession';
import type { Player } from '../shared/types';

// FB #156/#174 — finder target pins, lifted out of TradesScreen so the
// Trade-Finding Hub can show live pin counts on its Specific Player card
// while the deck screen (TradesScreen) keeps owning add/remove.
//
// Semantics preserved from the original TradesScreen useState pair:
//   - session-only, never persisted (pinned jobs bypass the server cache,
//     so a stale sticky pin would make every future tap slow + narrow
//     without the user remembering why);
//   - roster-specific, so pins clear on league switch. The subscription
//     below handles that centrally — including when the deck screen is
//     unmounted (hub-only navigation after a switch from the hub's
//     league pill).
//
// `packageMode` is the #174 "Trade as one package" toggle: with 2+ give
// pins and the toggle ON, generation runs pinned_give_mode='all' (every
// card's give side must carry EVERY pinned player). Defaults ON per the
// operator-approved spec; meaningless (and not sent) below 2 give pins.

// #330 — one-shot Offer/Target handoff from the league-rankings drill-in.
// `opponent` is exactly the shape TradesScreen's `sheetOpponent` state holds,
// so consumption is a plain `setSheetOpponent(handoff.opponent)`. `seq` is a
// store-internal monotonic counter stamped on every non-null setHandoff: the
// scoped opponent is a derived STRING downstream, so a repeat Offer to the
// SAME team changes no dep the deck's choke-point effect watches — the seq is
// the per-handoff nonce that makes it re-fire. Lifecycle is one-shot: set
// only by LeagueSummaryScreen's row action, consumed (and nulled) by
// TradesScreen on focus; an un-consumed handoff persists until consume,
// `clear()`, or the league-switch subscription below — no timeout.
export interface FinderHandoff {
  seq: number;
  opponent: { userId: string; name: string };
  autoRun: true;
}

interface FinderTargetsState {
  pinnedGive: Player[];
  pinnedReceive: Player[];
  packageMode: boolean;
  handoff: FinderHandoff | null;

  addGive: (p: Player) => void;
  addReceive: (p: Player) => void;
  removeGive: (id: string) => void;
  removeReceive: (id: string) => void;
  /** Replace one side wholesale (#186 "build around this side"). */
  setSide: (side: 'give' | 'receive', players: Player[]) => void;
  setPackageMode: (on: boolean) => void;
  /** Stamps `seq` internally — callers never supply it (#330). */
  setHandoff: (h: Omit<FinderHandoff, 'seq'> | null) => void;
  clear: () => void;
}

const dedupeAdd = (list: Player[], p: Player) =>
  list.some((x) => x.id === p.id) ? list : [...list, p];

// #330 — module-level so it survives every clear(): the counter is monotonic
// for the session, which is what lets the consumer treat "seq changed" as
// "a NEW handoff happened" with no reset ambiguity.
let _handoffSeq = 0;

export const useFinderTargets = create<FinderTargetsState>((set) => ({
  pinnedGive: [],
  pinnedReceive: [],
  packageMode: true,
  handoff: null,

  addGive: (p) => set((s) => ({ pinnedGive: dedupeAdd(s.pinnedGive, p) })),
  addReceive: (p) =>
    set((s) => ({ pinnedReceive: dedupeAdd(s.pinnedReceive, p) })),
  removeGive: (id) =>
    set((s) => ({ pinnedGive: s.pinnedGive.filter((p) => p.id !== id) })),
  removeReceive: (id) =>
    set((s) => ({ pinnedReceive: s.pinnedReceive.filter((p) => p.id !== id) })),
  setSide: (side, players) =>
    set(side === 'give' ? { pinnedGive: players } : { pinnedReceive: players }),
  setPackageMode: (on) => set({ packageMode: on }),
  setHandoff: (h) =>
    set({ handoff: h ? { ...h, seq: ++_handoffSeq } : null }),
  clear: () =>
    set({ pinnedGive: [], pinnedReceive: [], packageMode: true, handoff: null }),
}));

// League switch (or sign-out) invalidates player-id pins. Module-level
// subscription so the reset happens even when no pin-owning screen is
// mounted (e.g. switching leagues from the hub's league pill).
let _prevLeagueId: string | null | undefined;
useSession.subscribe((s) => {
  const id = s.league?.league_id ?? null;
  if (_prevLeagueId === undefined) {
    _prevLeagueId = id; // first observation — nothing to invalidate yet
    return;
  }
  if (id !== _prevLeagueId) {
    _prevLeagueId = id;
    useFinderTargets.getState().clear();
  }
});
