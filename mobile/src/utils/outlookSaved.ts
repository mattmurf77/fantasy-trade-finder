import type { QueryClient } from '@tanstack/react-query';

/**
 * Call after every save that can change `team_outlook` (any POST to
 * /api/league/preferences). Refreshes the saved preferences AND the saved
 * forecast read, whose `outlook_recommendation.differs` the server works out
 * from the saved outlook at read time. Without the second, Home's "Consider
 * <outlook>" prompt, League rankings' tile, Standings and the direction pages
 * kept the pre-save answer while the tab stayed mounted.
 *
 * The forecast key is ['league-projection-batch', userId, leagueId]; every
 * user's copy for this league is refreshed. A refresh is a stored read: it
 * never starts a simulation.
 */
export function refreshAfterOutlookSave(queryClient: QueryClient, leagueId: string | null | undefined) {
  queryClient.invalidateQueries({ queryKey: ['league-prefs', leagueId] });
  queryClient.invalidateQueries({
    queryKey: ['league-projection-batch'],
    predicate: (query) => query.queryKey[2] === leagueId,
  });
}
