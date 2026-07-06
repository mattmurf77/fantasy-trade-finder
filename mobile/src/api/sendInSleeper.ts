// "Send in Sleeper" — FTF backend routes that link a Sleeper account and
// propose trades directly (flagged beta; ToS-adverse — see
// docs/plans/sleeper-write-capture-runbook.md). All calls are session-authed
// by the shared client. Errors surface as ApiError; callers branch on
// `(err.body as any)?.error` (sleeper_not_linked | sleeper_expired |
// sleeper_write_failed | sleeper_unconfigured | feature_disabled).

import { api, apiRequest } from './client';

export interface SleeperLinkStatus {
  connected: boolean;
  sleeper_user_id?: string;
  expires_at?: string;
  expired?: boolean;
}

export interface ProposeTradePayload {
  league_id: string;
  their_user_id: string;          // opponent's Sleeper user_id (== FTF user_id)
  give_player_ids: string[];      // players I send
  receive_player_ids: string[];   // players I receive
}

export interface ProposeTradeResult {
  status: string;                 // "proposed" on success
  transaction_id?: string;
}

// GET — is a Sleeper account linked, and is the token still valid?
export async function getSleeperLinkStatus(): Promise<SleeperLinkStatus> {
  return api.get<SleeperLinkStatus>('/api/sleeper/link');
}

// POST — store a freshly captured Sleeper JWT (from the login webview).
export async function linkSleeperToken(token: string): Promise<SleeperLinkStatus> {
  return api.post<SleeperLinkStatus>('/api/sleeper/link', { token });
}

// DELETE — disconnect (drop the stored token).
export async function unlinkSleeper(): Promise<{ connected: boolean }> {
  return apiRequest<{ connected: boolean }>('/api/sleeper/link', { method: 'DELETE' });
}

// POST — propose the trade to Sleeper. Server resolves both roster_ids.
export async function proposeTradeToSleeper(
  payload: ProposeTradePayload,
): Promise<ProposeTradeResult> {
  return api.post<ProposeTradeResult>('/api/trades/propose', payload);
}
