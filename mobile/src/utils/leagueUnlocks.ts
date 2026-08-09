// League progress unlock math (#265). Extracted from LeagueProgressModule
// so mobile/tests/check-league-unlocks.js can transpile + run it under
// plain node (see utils/feedbackBadge.ts for the same idiom). Zero runtime
// imports — keep it that way.
//
// Mutual matches "unlock" once MATCH_UNLOCK_MATES leaguemates (excluding
// the viewing user) have stored rankings. #265: this was 2, borrowed from
// the (unrelated) contrarian/leaderboards threshold — but trade generation
// (backend/trade_service.py generate_trades: `eligible = [m for m in
// league.members if m.user_id != user_id and m.elo_ratings]`) only needs
// ONE other ranked opponent to produce mutual-gain matches, so the correct
// threshold is 1.
export const MATCH_UNLOCK_MATES = 1;

/** How many more ranked leaguemates are needed before mutual matches
 *  unlock. 0 once the threshold is met (matches are available). */
export function matchesUnlockRemaining(rankedMates: number): number {
  return Math.max(0, MATCH_UNLOCK_MATES - rankedMates);
}
