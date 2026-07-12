import { api, apiRequest, setSessionToken } from './client';
import { maybeReplaySleeperVerification } from './sendInSleeper';
import { getLeagueRosters, getLeagueUsers, warmPlayerCache, resetWarmedFlag } from './sleeper';
import { isEspnLeague, buildEspnSessionInitBody } from './espn';
import type {
  DemoSessionResponse,
  LeagueSummary,
  PublicProfile,
  SmartStartResolution,
} from '../shared/types';
import type { SavedUser, SessionVerification } from '../state/useSession';

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
    // #126 warm-up (fire-and-forget): the session just minted is fresh and
    // therefore unverified — start the silent verification replay now so it
    // usually completes during league pick, and sessionInit's awaited race
    // below resolves instantly off the single-flight promise. Safe: verified
    // state survives the same-user re-init sessionInit performs later.
    maybeReplaySleeperVerification(res.user_id).catch(() => {});
  }
  return res;
}

// ── Account auth (auth.accounts flag; account-auth plan P2/P2.6) ────────
//
// POST /api/auth/apple — verify a Sign in with Apple identity token.
// Backend behavior (see docs/api-reference.md):
//   * called WITH a live session → binds the session's Sleeper user to the
//     Apple account and verifies the session (linked=true)
//   * called with NO session, account already bound → device-loss restore:
//     returns a fresh session_token + the bound user's profile
//   * called with NO session, brand-new Apple account → ACCOUNT-FIRST
//     (P2.6): returns account_only=true + a session keyed to the synthetic
//     acct_<account_id> working key — the user ranks immediately and links
//     a Sleeper username later from Settings → Account.
export interface AccountAuthResponse {
  ok: boolean;
  provider: 'apple' | 'google';
  account_id: string;
  linked: boolean;
  conflict: boolean;
  sleeper_user_id: string | null;
  username?: string | null;
  display_name?: string | null;
  avatar?: string | null;
  session_token?: string;
  verified_via?: 'apple' | 'google';
  /** P2.6 account-first: session keyed to acct_<account_id>. */
  account_only?: boolean;
  user_id?: string;
  league_id?: string;
  league_name?: string;
}

export async function appleSignIn(
  identityToken: string,
  displayName?: string,
): Promise<AccountAuthResponse> {
  const res = await api.post<AccountAuthResponse>('/api/auth/apple', {
    identity_token: identityToken,
    // Apple sends the user's name only to the client, and only on first
    // authorization — forward it so the account-first users row has one.
    display_name: displayName || undefined,
  });
  if (res?.session_token) {
    await setSessionToken(res.session_token);
  }
  return res;
}

// POST /api/account/link-sleeper — link a Sleeper username as a source on
// the signed-in account (P2.6). 409 `merge_choice_required` carries both
// board summaries; re-call with strategy 'keep_sleeper' | 'keep_account'.
// 403 `sleeper_already_claimed` = that Sleeper id has a verified controller
// (first-verified-wins — no takeover). On success the backend mints a fresh
// session for the Sleeper user; the token is stored here and the caller
// must update SavedUser + re-run the league picker.
export interface BoardSummary {
  swipes: number;
  tiers_saved: boolean;
  tier_overrides: boolean;
  ranking_method: string | null;
  anchor_scale: boolean;
  any: boolean;
}

export interface LinkSleeperResponse {
  ok: boolean;
  sleeper_user_id: string;
  username: string;
  display_name: string;
  avatar: string | null;
  session_token: string;
  verified_via: string;
  merge: 'migrated' | 'adopted_sleeper' | 'kept_sleeper' | 'kept_account' | null;
}

export async function linkSleeperUsername(
  username: string,
  strategy?: 'keep_sleeper' | 'keep_account',
): Promise<LinkSleeperResponse> {
  const res = await api.post<LinkSleeperResponse>('/api/account/link-sleeper', {
    username: username.trim().toLowerCase(),
    strategy,
  });
  if (res?.session_token) {
    await setSessionToken(res.session_token);
  }
  return res;
}

// GET /api/account — current account: linked identities + bound Sleeper id.
// 404s while the auth.accounts flag is off.
export interface AccountInfo {
  ok: boolean;
  sleeper_user_id: string;
  verified_via: 'sleeper' | 'apple' | 'google' | null;
  account: {
    account_id: string;
    sleeper_user_id: string | null;
    created_at: string;
    identities: Array<{ provider: 'apple' | 'google'; linked_at: string }>;
  } | null;
  /** P2.6 — session is keyed to an account with no linked Sleeper source. */
  account_only?: boolean;
  /** Username of the bound Sleeper source, for the linked-sources list. */
  sleeper_username?: string | null;
}

export async function getAccount(): Promise<AccountInfo> {
  return api.get<AccountInfo>('/api/account');
}

// DELETE /api/account — in-app account deletion (App Store 5.1.1(v)).
// Always available (not flag-gated). Deletes the user's data per the
// privacy policy; the backend also invalidates every session server-side,
// so the caller must sign out locally on success.
export interface DeleteAccountResponse {
  ok: boolean;
  deleted: Record<string, number>;
}

export async function deleteAccount(): Promise<DeleteAccountResponse> {
  return apiRequest<DeleteAccountResponse>('/api/account', { method: 'DELETE' });
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
  /** Account-auth P1 (additive) — verified-session state. Feeds the
   *  "Verify your account" banner via useSession.verification. */
  verification?: SessionVerification;
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
  // Mirror the server's verified-session state into the store so the
  // verify banner reacts to every init/revalidate. Loaded inline to avoid
  // a circular import (same pattern as consumeInvitedBy below).
  //
  // #126 replay choke point: every session-establishment path (sign-in →
  // league pick, revalidateSession, switchLeague, ESPN init) funnels
  // through here. When the fresh session is unverified, race the
  // single-flight silent replay (persisted Sleeper JWT → the existing
  // hard-verified POST /api/sleeper/link) against a 4 s cap, and mirror
  // exactly once AFTER the race so the banner never flashes. acct_*
  // sessions are verified at mint (guard skips them); demo/no-token users
  // return 'none' with no network.
  if (res?.verification) {
    let verification = res.verification;
    if (!verification.session_verified) {
      const replay = maybeReplaySleeperVerification(body.user_id);
      const outcome = await Promise.race([
        replay,
        new Promise<'timeout'>((resolve) => setTimeout(() => resolve('timeout'), 4000)),
      ]);
      if (outcome === 'verified') {
        // The replay stamped the live server session — no re-init needed.
        // Full success-mirror shape (same as SleeperConnectScreen's).
        verification = {
          session_verified: true,
          user_verified: true,
          verified_via: 'sleeper',
          enforced: verification.enforced,
        };
      } else if (outcome === 'timeout') {
        // Cap elapsed — mirror the server's values now (truthful banner);
        // the in-flight replay keeps running and late-applies on a
        // 'verified', guarded so it never clobbers newer state or a
        // different signed-in user.
        replay
          .then((late) => {
            if (late !== 'verified') return;
            try {
              const { useSession } = require('../state/useSession');
              const state = useSession.getState();
              const cur = state.verification;
              if (
                cur &&
                !cur.session_verified &&
                state.user?.user_id === body.user_id
              ) {
                state.setVerification({
                  session_verified: true,
                  user_verified: true,
                  verified_via: 'sleeper',
                  enforced: cur.enforced,
                });
              }
            } catch {
              /* require may fail in test contexts; non-fatal */
            }
          })
          .catch(() => {});
      }
      // 'rejected' / 'inconclusive' / 'none' → mirror server values unchanged.
    }
    try {
      const { useSession } = require('../state/useSession');
      useSession.getState().setVerification(verification);
    } catch {
      /* require may fail in test contexts; non-fatal */
    }
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
// are short (~2-3s); sessionInit is the slow leg (5–10s on
// Render's free tier when rebuilding rosters + members).
//
// INIT-08-client: LeaguePickerScreen calls the two phases separately so
// the user can navigate to Main after phase-1 (Sleeper) completes, while
// phase-2 (sessionInit) runs in the background. switchLeague still uses
// the combined `initLeagueSession` path (inline league switch must be
// atomic — no backgrounding needed there).
export interface LeagueLite { league_id: string; name: string }
export async function initLeagueSession(
  user: SavedUser,
  lg: LeagueLite,
): Promise<void> {
  // ESPN-imported leagues (flag `espn.link`) have no Sleeper rosters — the
  // proxy routes would 404 on their numeric ids. Build the init body from
  // the backend's imported snapshot instead (api/espn.ts); the resulting
  // /api/session/init call is identical from here on. Detection reads the
  // cached league list's `platform` field (hydrated from AsyncStorage).
  if (isEspnLeague(lg.league_id)) {
    const espnBody = await buildEspnSessionInitBody(user, lg);
    await submitSessionInit(espnBody);
    return;
  }
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

// ── INIT-08-client: two-phase session init for optimistic navigation ───
//
// Phase 1 — fetch Sleeper data and build the session_init payload.
// Resolves in ~2-3s (Sleeper round-trips + player-cache warm). Throws on
// network failure so the caller can show a meaningful error before
// navigating away from LeaguePicker.
//
// Returns a `SessionInitBody` ready to pass to `submitSessionInit`.
export async function buildSessionInitBody(
  user: SavedUser,
  lg: LeagueLite,
): Promise<SessionInitBody> {
  // ESPN-imported leagues: roster source is the backend snapshot, not
  // Sleeper (see initLeagueSession's espn branch for the why).
  if (isEspnLeague(lg.league_id)) {
    await warmPlayerCache().catch(() => { /* best-effort */ });
    return buildEspnSessionInitBody(user, lg);
  }
  const [rosters, leagueUsers] = await Promise.all([
    getLeagueRosters(lg.league_id),
    getLeagueUsers(lg.league_id),
    warmPlayerCache().catch(() => { /* best-effort */ }),
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

  let invitedBy: string | null = null;
  try {
    const { useSession } = require('../state/useSession');
    invitedBy = useSession.getState().consumeInvitedBy();
  } catch {
    /* require may fail in test contexts; non-fatal */
  }

  return {
    user_id:          user.user_id,
    username:         user.username,
    display_name:     user.display_name,
    avatar:           user.avatar_id,
    league_id:        lg.league_id,
    league_name:      lg.name,
    user_player_ids:  myPlayerIds,
    opponent_rosters: opponentRosters,
    invited_by:       invitedBy ?? undefined,
  };
}

// Phase 2 — POST the built body to /api/session/init with cold-restart
// recovery. Call this AFTER navigating to Main so the ~5-10s backend
// processing doesn't block UI. Returns a promise the caller can attach
// error handling to. Does not throw on "player database not cached" —
// retries once automatically (same recovery path as initLeagueSession).
export async function submitSessionInit(body: SessionInitBody): Promise<void> {
  try {
    await sessionInit(body);
  } catch (e: any) {
    if (_isPlayerCacheMissing(e)) {
      resetWarmedFlag();
      await warmPlayerCache();
      await sessionInit(body);
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
