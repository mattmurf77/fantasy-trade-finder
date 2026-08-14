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

// ── Leaderboards / contrarian fold line (#308) ───────────────────────────
// The /api/league/contrarian gate counts users with stored rankings in the
// ACTIVE scoring format, caller INCLUDED — a different population AND a
// different threshold from MATCH_UNLOCK_MATES above. Don't conflate them.
export const CONTRARIAN_UNLOCK_USERS = 3; // /api/league/contrarian gate, caller INCLUDED, active format only

const FOLD_FORMAT_LABEL: Record<string, string> = {
  '1qb_ppr': '1QB',
  sf_tep: 'SF TEP',
}; // mirrors TopBar's FORMAT_TILE_LABEL (TopBar.tsx) — pinned in docs/cross-client-invariants.md

/** Fold-line sentence for the leaderboards/contrarian unlock.
 *  needed/format come from the contrarian insufficient payload; both
 *  nullable because placeholderData can briefly serve a stale shape. */
export function contrarianFoldLine(
  needed: number | null | undefined,
  format: string | null | undefined,
): string {
  const label = format ? FOLD_FORMAT_LABEL[format] : undefined;
  const where = label ? ` in ${label}` : '';
  if (needed == null || needed <= 0) {
    return `Leaderboards and contrarian ranks appear once ${CONTRARIAN_UNLOCK_USERS} members have ranked${where}.`;
  }
  return (
    `Leaderboards and contrarian ranks appear once ${CONTRARIAN_UNLOCK_USERS} members ` +
    `have ranked${where} — ${needed} more to go.`
  );
}
