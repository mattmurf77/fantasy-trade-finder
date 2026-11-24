// Position chip + team for one asset on a Matches tile (Mutual and Awaiting).
//
// The Matches payloads (`matches/all`, `awaiting`) ship parallel
// position/team arrays read from the `players` table, so a draft pick gets
// "" in both and the tile fell back to an "FLX" chip with team "FA". The
// deck labels a pick as position 'PICK' / team 'PICK' (the backend's pick
// pseudo-player shape); this gives Matches tiles the same label.
//
// A pick is recognised by its id, the same rule the server's
// `_pick_labels_by_id` and the deck's pick-offer pre-filter use: generic
// ladder rungs are `generic_pick_<round>_<tier>`, owned picks are
// `{league_id}_{season}_{round}_{original_roster_id}`. Real player ids never
// carry either prefix.
//
// No imports — tests/check-deck-labels.js runs this module under plain node.

export const PICK_LABEL = 'PICK';
// Legacy fallback when the server sent no position (older server).
export const POS_UNKNOWN = 'FLX';

export function isPickAssetId(id: string, leagueId: string | null | undefined): boolean {
  if (!id) return false;
  if (id.startsWith('generic_pick_')) return true;
  return !!leagueId && id.startsWith(`${leagueId}_`);
}

export function matchAssetLabel(
  id: string,
  leagueId: string | null | undefined,
  position: string | null | undefined,
  team: string | null | undefined,
): { position: string; team: string } {
  if (isPickAssetId(id, leagueId)) return { position: PICK_LABEL, team: PICK_LABEL };
  return { position: position || POS_UNKNOWN, team: team || '' };
}
