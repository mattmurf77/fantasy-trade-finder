import { api } from './client';
import type { DraftOrder } from './leagueProjections';
import { draftOrderRequest, type DraftOrderAnswer } from '../utils/maxPfMoves';

// Max PF moves' once-per-league draft-order answer (contract §7.2):
// `POST /api/leagues/<league_id>/draft-order-rule` with `{rule}`. 404 while
// flag `league.max_pf_moves` is off. Kept OUT of `leagueProjections.ts` on
// purpose: that client only reads (pinned by check-league-projections.js and
// check-standings-table.js B6d), and this is the feature's one write.
export const setDraftOrderRule = (leagueId: string, rule: DraftOrderAnswer) => {
  const { path, body } = draftOrderRequest(leagueId, rule);
  return api.post<{ draft_order: DraftOrder }>(path, body);
};
