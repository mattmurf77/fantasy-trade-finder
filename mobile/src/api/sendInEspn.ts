// "Send in ESPN" — propose a built trade directly into ESPN via the FTF
// backend (flag `espn.send`, OFF and deliberately absent from
// config/features.json until the server-side auth probe clears — see
// docs/plans/espn-send-live-capture-2026-08-11.md + D-026). Rides ESPN's
// undocumented lm-api-writes transactions endpoint with the espn_s2 + SWID
// cookies the ESPN link flow already stores — the mobile client never touches
// ESPN directly. Errors surface as ApiError; callers branch on
// `(err.body as any)?.error`:
//   espn_not_connected | espn_auth_expired → prompt ESPN re-connect
//   espn_not_linked | espn_team_unknown    → league needs (re-)linking
//   espn_pick_unsupported                  → hard block: picks can't be sent
//   espn_asset_unmapped                    → hard block, nothing was sent
//   verification_required | feature_disabled | espn_write_failed | bad_request

import { api } from './client';

export interface EspnLinkStatus {
  connected: boolean;
  /** Stored expiry hint — usually null (ESPN stamps no cookie expiry). */
  expires_at?: string | null;
  expired?: boolean;
}

// GET — is an ESPN account credential (espn_s2 + SWID) stored for this user?
// Mirrors getSleeperLinkStatus: the send button checks this UP FRONT and
// routes to EspnConnectScreen (reason: 'send') when unlinked, instead of
// letting the propose 409 into a dead end. Never returns the cookies.
export async function getEspnLinkStatus(): Promise<EspnLinkStatus> {
  return api.get<EspnLinkStatus>('/api/espn/link');
}

export interface ProposeEspnTradePayload {
  league_id: string;
  /** The counterparty's member id as FTF stores it for ESPN leagues — the
   *  synthetic `espn:{SWID}` (or `espn:{league_id}.t{team_id}`) id every
   *  non-linking member carries. The server resolves BOTH team ids against a
   *  live league read; the client never asserts a team id. */
  their_user_id: string;
  /** PLAYER ids only (FTF/Sleeper-space), exactly as trade surfaces carry
   *  them. Unlike MFL, ESPN pick assets are UNVERIFIED — any pick id in
   *  these arrays HARD-BLOCKS the whole send (422 espn_pick_unsupported);
   *  nothing is ever silently dropped. Players reverse-map through the
   *  crosswalk server-side; any miss hard-blocks (422 espn_asset_unmapped). */
  give_player_ids: string[];
  receive_player_ids: string[];
  comments?: string;
  // F1 signal spine (flag deck.signal_v2) — same contract as the other sends.
  impression_id?: string;
}

export interface ProposeEspnTradeResult {
  status: string;           // "proposed" on success
  transaction_id?: string;  // ESPN's proposal id (cancel/poll handle)
  espn_status?: string;     // ESPN's own status echo ("PENDING")
}

// POST — propose the trade in ESPN. Server resolves both team ids against a
// live pre-flight league read, reverse-maps every player, and refuses (422)
// rather than silently dropping anything it can't place — picks always block.
export async function proposeTradeToEspn(
  payload: ProposeEspnTradePayload,
): Promise<ProposeEspnTradeResult> {
  return api.post<ProposeEspnTradeResult>('/api/trades/propose-espn', payload);
}
