import { api, setSessionToken } from './client';
import { getLeagueRosters, getLeagueUsers, warmPlayerCache, resetWarmedFlag } from './sleeper';
import type {
  DemoSessionResponse,
  LeagueSummary,
  PublicProfile,
  SmartStartResolution,
} from '../shared/types';
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

// Backend response shape from /api/session/init.
// `token` is what we care about: when the request goes out without an
// X-Session-Token header (e.g. after a 401-driven clearSessionToken), the
// backend creates a brand-new session and returns its token here. Without
// saving it, every subsequent API call would 401 in a loop.
export interface SessionInitResponse {
  ok: boolean;
  token: string;
  player_count?: number;
  pick_count?: number;
  user_roster?: unknown[];
  league_id?: string;
  opponents?: number;
}

export async function sessionInit(body: SessionInitBody): Promise<SessionInitResponse> {
  const res = await api.post<SessionInitResponse>('/api/session/init', body);
  // Persist the returned token so the next request carries it. Critical
  // when recovering from a session-expired state — the user goes through
  // the league picker without a stored token, sessionInit mints a new
  // one, and we MUST save it or the very next API call 401s again.
  // Idempotent when the backend echoes back the existing token.
  if (res?.token) {
    await setSessionToken(res.token);
  }
  return res;
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
  // Warm the backend's Sleeper player-DB cache in parallel with the
  // roster/users fetches. session_init below errors with
  //   "Player database not cached — call GET /api/sleeper/players first"
  // when this hasn't been called for the current backend process (e.g.
  // right after a Render free-tier dyno cold-start, or a redeploy).
  // The web client warms it from its boot flow; mobile previously didn't,
  // which surfaced as a hard error on first league-pick after any cold
  // start. Warm result is discarded (server-side cache is the value);
  // the call is ~5MB on a cold cache and ~50ms on a warm one.
  //
  // This warm is now deduped per launch (INIT-12 FR-5/6): warmPlayerCache()
  // short-circuits with no round-trip if App.tsx already warmed at boot.
  // If the backend's cache was lost *after* boot, the warmedThisLaunch flag
  // wouldn't know — so the session_init "not cached" recovery below resets
  // the flag and re-warms once.
  const [rosters, leagueUsers] = await Promise.all([
    getLeagueRosters(lg.league_id),
    getLeagueUsers(lg.league_id),
    warmPlayerCache().catch(() => {
      // Best-effort. If the warm call itself fails we still try
      // sessionInit; if the cache is also empty it errors with the
      // same message and the recovery path below re-warms once.
    }),
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

  // Pull (and clear) any in-memory referral attribution captured from a
  // deep link. Backend stores invited_by on the users row only on insert,
  // so it's safe to forward on every session_init — repeat calls are no-ops.
  // Loaded inline to avoid a circular import (useSession → auth.ts).
  let invitedBy: string | null = null;
  try {
    const { useSession } = require('../state/useSession');
    invitedBy = useSession.getState().consumeInvitedBy();
  } catch {
    /* require may fail in test contexts; non-fatal */
  }

  const initBody: SessionInitBody = {
    user_id:           user.user_id,
    username:          user.username,
    display_name:      user.display_name,
    avatar:            user.avatar_id,
    league_id:         lg.league_id,
    league_name:       lg.name,
    user_player_ids:   myPlayerIds,
    opponent_rosters:  opponentRosters,
    invited_by:        invitedBy ?? undefined,
  };

  try {
    await sessionInit(initBody);
  } catch (e: any) {
    // Cold-restart recovery (INIT-12 FR-7 / AC-6): if the backend process lost
    // its player cache *after* this launch warmed once, warmedThisLaunch is
    // stale-true and the warm above was a no-op, so session_init fails with
    // "Player database not cached". Reset the flag, re-warm for real, and retry
    // session_init exactly once. Any other failure bubbles unchanged.
    if (_isPlayerCacheMissing(e)) {
      resetWarmedFlag();
      await warmPlayerCache();
      await sessionInit(initBody);
    } else {
      throw e;
    }
  }
}

// Recognises the backend's "Player database not cached" 400 (server.py:4476).
// The wrapper folds the backend `error`/`message` into ApiError.message.
function _isPlayerCacheMissing(e: any): boolean {
  const msg = typeof e?.message === 'string' ? e.message : '';
  return /player database not cached/i.test(msg);
}

// ── Bundle 8: Growth loop helpers ─────────────────────────────────────────

// Heuristic: anything containing "://" or starting with a domain-shaped
// prefix is treated as a URL; otherwise we assume the user typed a bare
// Sleeper username. Mirrors the web's `smart-start` panel behavior — the
// URL path goes through /api/league/parse-url, the username path goes
// through the existing sign-in flow.
function _looksLikeUrl(input: string): boolean {
  const trimmed = input.trim();
  if (!trimmed) return false;
  if (/^https?:\/\//i.test(trimmed)) return true;
  if (/^[a-z0-9-]+\.[a-z]{2,}\//i.test(trimmed)) return true;   // sleeper.com/league/...
  return false;
}

interface ParseUrlResponse {
  platform?: 'sleeper' | 'espn' | 'mfl';
  league_id?: string;
  name?: string | null;
  supported?: boolean;
  error?: string;
  message?: string;
}

/** Smart-start resolver. Accepts either a Sleeper username or a league URL.
 *  Returns a discriminated result the caller can branch on. Never throws —
 *  parsing failures come back as kind='invalid' with a human message so the
 *  UI can surface inline error text. */
export async function resolveSmartStart(input: string): Promise<SmartStartResolution> {
  const raw = (input || '').trim();
  if (!raw) {
    return { kind: 'invalid', message: 'Enter a Sleeper username or league URL.' };
  }
  if (!_looksLikeUrl(raw)) {
    return { kind: 'username', username: raw.toLowerCase() };
  }
  try {
    const body = await api.post<ParseUrlResponse>(
      '/api/league/parse-url',
      { url: raw },
      { skipAuth: true },
    );
    if (!body || !body.platform || !body.league_id) {
      return {
        kind: 'invalid',
        message: body?.message || "Couldn't recognize that URL.",
      };
    }
    return {
      kind:        'league_url',
      platform:    body.platform,
      league_id:   body.league_id,
      league_name: body.name ?? undefined,
      supported:   body.supported === true,
    };
  } catch (e: any) {
    return {
      kind:    'invalid',
      message: e?.message || 'Could not parse that URL.',
    };
  }
}

/** Start a seeded demo session. The backend builds a complete league with
 *  ranking + trade services attached to the returned token; mobile just
 *  stores the token in SecureStore and treats the session as "demo". */
export async function startDemoSession(): Promise<DemoSessionResponse> {
  const res = await api.post<DemoSessionResponse>('/api/session/demo', undefined, {
    skipAuth: true,
  });
  if (res?.token) {
    await setSessionToken(res.token);
  }
  return res;
}

/** Public profile JSON — read-only snapshot of a user's tier overrides +
 *  contrarian takes. Backend gates this on the `profiles.public_pages` flag;
 *  a 404 there bubbles up as an ApiError, which the screen renders as a
 *  "Profile not found" state. */
export async function getPublicProfile(username: string): Promise<PublicProfile> {
  const uname = encodeURIComponent((username || '').trim().toLowerCase());
  return api.get<PublicProfile>(`/api/profile/${uname}`, { skipAuth: true });
}
