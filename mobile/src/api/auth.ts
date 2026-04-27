import { api, setSessionToken } from './client';
import { getLeagueRosters, getLeagueUsers } from './sleeper';
import type { LeagueSummary } from '../shared/types';
import type { SavedUser } from '../state/useSession';

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

// ── Helper: initialize a session for a specific league ─────────────────
// Shared between LeaguePickerScreen (initial league pick after sign-in)
// and useSession.switchLeague (in-app league switch). Fetches rosters +
// users from Sleeper, builds the opponent_rosters payload, and POSTs to
// /api/session/init. Caller is responsible for updating local session
// state (e.g. setLeague) after this resolves successfully.
//
// Throws on failure so callers can surface error UI. The Sleeper calls
// are short and synchronous; sessionInit is the slow leg (5–10s on
// Render's free tier when rebuilding rosters + members).
export interface LeagueLite { league_id: string; name: string }
export async function initLeagueSession(
  user: SavedUser,
  lg: LeagueLite,
): Promise<void> {
  const [rosters, leagueUsers] = await Promise.all([
    getLeagueRosters(lg.league_id),
    getLeagueUsers(lg.league_id),
  ]);
  const usernameMap: Record<string, string> = {};
  for (const u of leagueUsers || []) {
    usernameMap[u.user_id] = u.display_name || u.username || u.user_id;
  }
  const myRoster = (rosters || []).find((r) => r.owner_id === user.user_id);
  const myPlayerIds = (myRoster?.players || []).filter(Boolean);
  const opponentRosters = (rosters || [])
    .filter((r) => r.owner_id && r.owner_id !== user.user_id)
    .map((r) => ({
      user_id: r.owner_id,
      username: usernameMap[r.owner_id] || `Team ${r.roster_id}`,
      player_ids: (r.players || []).filter(Boolean),
    }))
    .filter((r) => r.player_ids.length > 0);

  await sessionInit({
    user_id:           user.user_id,
    username:          user.username,
    display_name:      user.display_name,
    avatar:            user.avatar_id,
    league_id:         lg.league_id,
    league_name:       lg.name,
    user_player_ids:   myPlayerIds,
    opponent_rosters:  opponentRosters,
  });
}
