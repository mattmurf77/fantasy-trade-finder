import { create } from 'zustand';

// presentationDismissed — the in-session dismissed set for the
// presentation-v2 surface (flag `trades.presentation_v2`).
//
// WHY A STORE AND NOT SCREEN STATE. TodaysTrade and TradeBrowseAll are two
// screens over ONE ranked deck. A row dismissed in browse must be gone from
// the Featured tier when the user navigates back, and the hero must not
// re-endorse a card the user just dismissed. Screen-local state would let the
// two views disagree about the same card, which is the kind of drift that
// makes users stop trusting the dismiss control.
//
// WHY IT IS NOT PERSISTED. The durable record of a dismiss is the SERVER's:
// the swipe POST writes the disposition and the decline reason writes the
// row, and the next generation's fatigue/suppression logic is what actually
// keeps the idea from coming back. This set exists only so the current
// screenful stays coherent between the two views — persisting it locally
// would create a second, drifting source of truth for something the backend
// already owns.
//
// The Undo path is why `restore` exists at all: an accidental dismiss must be
// reversible in the UI within the same session (the acknowledgement line's
// "Undo"). It does not un-write the server-side signal, and the copy never
// claims it does — it says "we'll rank ideas like this lower", which stays
// true.

interface DismissedState {
  /** trade_ids dismissed in this session, per league. */
  byLeague: Record<string, string[]>;
  dismiss: (leagueId: string, tradeId: string) => void;
  restore: (leagueId: string, tradeId: string) => void;
  /** Clear when the deck is regenerated — new cards, new ids, clean slate. */
  reset: (leagueId: string) => void;
}

export const usePresentationDismissed = create<DismissedState>((set) => ({
  byLeague: {},
  dismiss: (leagueId, tradeId) =>
    set((s) => {
      const cur = s.byLeague[leagueId] ?? [];
      if (cur.includes(tradeId)) return s;
      return { byLeague: { ...s.byLeague, [leagueId]: [...cur, tradeId] } };
    }),
  restore: (leagueId, tradeId) =>
    set((s) => {
      const cur = s.byLeague[leagueId] ?? [];
      if (!cur.includes(tradeId)) return s;
      return {
        byLeague: { ...s.byLeague, [leagueId]: cur.filter((id) => id !== tradeId) },
      };
    }),
  reset: (leagueId) =>
    set((s) => {
      if (!s.byLeague[leagueId]) return s;
      const next = { ...s.byLeague };
      delete next[leagueId];
      return { byLeague: next };
    }),
}));

/** Selector helper: the dismissed set for one league, as a Set for O(1) reads
 *  in `partitionDeck`. */
export function dismissedSet(byLeague: Record<string, string[]>, leagueId: string | null | undefined): Set<string> {
  return new Set(leagueId ? byLeague[leagueId] ?? [] : []);
}
