// "Send in MFL" — propose a built trade directly into MyFantasyLeague via the
// FTF backend (flag `trade.send_in_mfl`). Unlike the Sleeper path this rides
// MFL's DOCUMENTED import API using the MFL sign-in #177 already stores — the
// mobile client never touches MFL directly. Errors surface as ApiError;
// callers branch on `(err.body as any)?.error`:
//   mfl_not_connected | mfl_auth_expired  → prompt MFL re-sign-in
//   mfl_not_linked | mfl_franchise_unknown → league needs (re-)linking
//   mfl_asset_unmapped                     → hard block, nothing was sent
//   verification_required | feature_disabled | mfl_write_failed | bad_request
//
// Pre-flight validation reuses sendInSleeper's validateTradeSend — the shared
// POST /api/trades/validate branches to a fresh MFL rosters export
// server-side for MFL-linked leagues.

import { api } from './client';

export interface ProposeMflTradePayload {
  league_id: string;
  /** The counterparty's member id as FTF stores it for MFL leagues — the
   *  synthetic `mfl:{league_id}.f{franchise_id}` id every non-linking member
   *  carries. The server parses + verifies the franchise id from it. */
  their_user_id: string;
  give_player_ids: string[];     // FTF (Sleeper-space) ids — server reverse-maps
  receive_player_ids: string[];  // and HARD-BLOCKS if any asset fails to map
  comments?: string;
  // F1 signal spine (flag deck.signal_v2) — same contract as the Sleeper send.
  impression_id?: string;
}

export interface ProposeMflTradeResult {
  status: string;        // "proposed" on success
  mfl_status?: string;   // MFL's own import status echo ("OK")
}

// POST — propose the trade in MFL. Server resolves both franchise ids,
// reverse-maps every asset, and refuses (422 mfl_asset_unmapped) rather than
// silently dropping anything the crosswalk can't place.
export async function proposeTradeToMfl(
  payload: ProposeMflTradePayload,
): Promise<ProposeMflTradeResult> {
  return api.post<ProposeMflTradeResult>('/api/trades/propose-mfl', payload);
}
