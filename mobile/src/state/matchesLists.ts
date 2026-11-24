import { queryClient } from './queryClient';

// ── Refresh the Matches lists after the user's likes change ───────────────
//
// MatchesScreen's "Awaiting them" segment (`['awaiting-trades']`), the
// mutual list (`['matches', 'all']`) and the deck's liked count
// (`['liked-trades', leagueId]`) are all read from the user's live `like`
// rows. Their queries stay mounted in the tab navigator, and with
// `refetchOnWindowFocus: false` nothing refetches them when the user returns
// to the tab, so any action that creates or removes a like must invalidate
// them. Sim pass 2026-11-22: a deck like that did not complete a match left
// Awaiting at its old count until a manual pull-to-refresh, because only the
// matched branch invalidated it.
//
// One helper, so every like/unlike path refreshes the same three lists.
// `['liked-trades']` is a prefix: it covers every league's count. Invalidation
// refetches only the queries that are mounted; the rest are marked stale and
// fetch on their next mount. No polling.

export const MATCHES_LIST_KEYS = [
  ['awaiting-trades'],
  ['liked-trades'],
  ['matches', 'all'],
] as const;

export function refreshMatchesLists(): Promise<void> {
  return Promise.all(
    MATCHES_LIST_KEYS.map((queryKey) => queryClient.invalidateQueries({ queryKey: [...queryKey] })),
  ).then(() => undefined);
}
