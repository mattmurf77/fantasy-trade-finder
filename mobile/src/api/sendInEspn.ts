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

import { api, apiRequest } from './client';

export interface EspnLinkStatus {
  /** True only for a credential that PASSED a live authenticated ESPN read
   *  at store time (credential-honesty fix, 2026-08-12) — a stored-but-
   *  never-proven pair reads false, routing the user through the sign-in
   *  flow (which verifies before storing) instead of a doomed send. */
  connected: boolean;
  /** Stored expiry hint — usually null (ESPN stamps no cookie expiry). */
  expires_at?: string | null;
  expired?: boolean;
  /** When the stored pair last proved itself against ESPN (ISO UTC);
   *  present only when connected. */
  verified_at?: string | null;
}

// GET — is an ESPN account credential (espn_s2 + SWID) stored for this user?
// Mirrors getSleeperLinkStatus: the send button checks this UP FRONT and
// routes to EspnConnectScreen (reason: 'send') when unlinked, instead of
// letting the propose 409 into a dead end. Never returns the cookies.
export async function getEspnLinkStatus(): Promise<EspnLinkStatus> {
  return api.get<EspnLinkStatus>('/api/espn/link');
}

// DELETE — disconnect: remove the stored espn_s2 + SWID pair server-side.
// Mirrors unlinkSleeper. Idempotent (a no-credential delete is a clean
// {connected:false}), scoped server-side to the caller's own row. Added
// after the 2026-08-12 incident: cookies captured from someone else's ESPN
// sign-in had no user-facing removal path. There is no device-side copy to
// clear — the pair only ever lives server-side (encrypted) — and
// EspnConnectScreen clears the WebView's ESPN/Disney session on every
// mount, so after this resolves the user can immediately sign in as a
// different ESPN account.
export async function unlinkEspn(): Promise<{ connected: boolean }> {
  return apiRequest<{ connected: boolean }>('/api/espn/link', { method: 'DELETE' });
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
