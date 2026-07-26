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

interface FinderTargetsState {
  pinnedGive: Player[];
  pinnedReceive: Player[];
  packageMode: boolean;

  addGive: (p: Player) => void;
  addReceive: (p: Player) => void;
  removeGive: (id: string) => void;
  removeReceive: (id: string) => void;
  /** Replace one side wholesale (#186 "build around this side"). */
  setSide: (side: 'give' | 'receive', players: Player[]) => void;
  setPackageMode: (on: boolean) => void;
  clear: () => void;
}

const dedupeAdd = (list: Player[], p: Player) =>
  list.some((x) => x.id === p.id) ? list : [...list, p];

export const useFinderTargets = create<FinderTargetsState>((set) => ({
  pinnedGive: [],
  pinnedReceive: [],
  packageMode: true,

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
  clear: () => set({ pinnedGive: [], pinnedReceive: [], packageMode: true }),
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
