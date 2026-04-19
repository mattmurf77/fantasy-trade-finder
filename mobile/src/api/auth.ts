import { api, setSessionToken } from './client';
import type { LeagueSummary } from '../shared/types';

// POST /api/extension/auth — the lightweight, one-shot username auth endpoint.
// Shipped earlier for the Chrome extension; perfect for mobile too.
// Returns: session_token + user_id + display_name + avatar + [leagues]
export interface AuthResponse {
  stage: 'connected';
  session_token: string;
  expires_at: number;
  user_id: string;
  username: string;
  display_name: string;
  avatar: string | null;
  leagues?: LeagueSummary[];
}

export async function signIn(username: string): Promise<AuthResponse> {
  const res = await api.post<AuthResponse>(
    '/api/extension/auth',
    { username: username.trim().toLowerCase() },
    { skipAuth: true },
  );
  if (res?.session_token) {
    await setSessionToken(res.session_token);
  }
  return res;
}

// POST /api/session/init — full app session. Called after the user picks
// a league so the backend builds a RankingService + TradeService tied to
// that league. Same payload shape the web app sends from initSession().
export interface SessionInitBody {
  user_id: string;
  username?: string;
  display_name?: string;
  avatar?: string | null;
  league_id: string;
  league_name: string;
  user_player_ids: string[];
  opponent_rosters: Array<{
    user_id: string;
    username: string;
    player_ids: string[];
  }>;
  invited_by?: string | null;
  active_format?: '1qb_ppr' | 'sf_tep';
}

export async function sessionInit(body: SessionInitBody) {
  return api.post<any>('/api/session/init', body);
}

// GET /api/session/ping — session liveness check. 401 → token expired.
export async function sessionPing(): Promise<{ ok: true }> {
  return api.get('/api/session/ping');
}
