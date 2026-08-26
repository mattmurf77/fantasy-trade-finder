import { api, setSessionToken } from './client';
import { track } from './events';
import type { EspnLinkPreview, EspnMyLeague } from './espn';
import { PlatformLinkPreview, normalizePreview } from './platformLink';
import type { MflAuthLeague } from './platformLink';

// ── Sessionless platform entry (landing platform options v2, D-164) ─────────
// POST /api/entry/platform — the platform twin of the Sleeper claim-a-username
// door. Two calls against one route, mirroring the link routes' split:
//   • preview (no team_id): the exact `choose_team` shape /api/{espn,mfl}/link
//     returns, so EspnLinkSheet / PlatformLinkSheet parse it unchanged.
//   • mint (team_id): validates the claim and mints a session for a
//     DETERMINISTIC entry:<platform>:… user id. The mint stores the token
//     here (like auth.signIn does); the sheet then runs the CANONICAL
//     /api/{espn,mfl}/link import under it — no import logic is duplicated.
// Route 404s while `landing.platform_options` or the platform flag is off.

export type EntryPlatform = 'espn' | 'mfl';

export interface EntryMintResponse {
  stage: 'connected';
  session_token: string;
  expires_at: number;
  user_id: string;          // entry:espn:<SWID> | entry:espn:<lg>.t<n> | entry:mfl:<lg>.f<id>
  username: string;         // always '' — entry users have no handle
  display_name: string;     // the claimed team's name
  avatar: string | null;
  platform: EntryPlatform;
  league_id: string;
  team_id: number | string;
}

/** Preview an ESPN league with no session. Same wire shape as the link
 *  route's preview, including the 403 espn_auth_required for private
 *  leagues (cookies come from the caller only — nothing is stored yet). */
export async function entryEspnPreview(args: {
  espnLeagueId: string;
  season?: number;
  espnS2?: string;
  swid?: string;
}): Promise<EspnLinkPreview> {
  return api.post<EspnLinkPreview>('/api/entry/platform', {
    platform: 'espn',
    espn_league_id: args.espnLeagueId,
    season: args.season,
    espn_s2: args.espnS2,
    swid: args.swid,
  }, { skipAuth: true });
}

/** Preview an MFL league with no session. Normalized like
 *  linkPlatformLeague's preview so PlatformLinkSheet renders it unchanged. */
export async function entryMflPreview(args: {
  leagueInput: string;
  year?: number;
}): Promise<PlatformLinkPreview> {
  const res = await api.post<any>('/api/entry/platform', {
    platform: 'mfl',
    mfl_league_id: args.leagueInput,
    year: args.year,
  }, { skipAuth: true });
  return normalizePreview(res);
}

// ── Account discovery (v2.1): "log in" instead of "know your league id" ─────
// Both are sessionless POSTs against the same /api/entry/platform route, with
// an `action` discriminator. Neither stores anything server-side — no
// credential row, no user, no session — and neither carries analytics: the
// signin funnel still fires exactly once, at the mint below.

/** ESPN: the fan-profile league list for a freshly captured cookie pair.
 *  Same wire shape as GET /api/espn/my-leagues (which reads the session
 *  user's STORED pair — nonexistent before the mint). 404 while
 *  `espn.league_picker` is off; 403 when ESPN rejects the pair. Callers
 *  treat any rejection as "no picker — type a league id instead". */
export async function entryEspnMyLeagues(args: {
  espnS2: string;
  swid: string;
}): Promise<EspnMyLeague[]> {
  const res = await api.post<{ leagues: EspnMyLeague[] }>(
    '/api/entry/platform',
    {
      platform: 'espn',
      action: 'my_leagues',
      espn_s2: args.espnS2,
      swid: args.swid,
    },
    { skipAuth: true },
  );
  return res?.leagues || [];
}

/** MFL: sign in and list the account's leagues, each with the user's own
 *  franchise_id — which is what lets the entry flow mint DIRECTLY (no
 *  team-claim step). Same per-league shape as POST /api/mfl/auth-link, but
 *  the backend stores NOTHING here: the password is used for the one MFL
 *  login call and never persisted, logged, or echoed. 404 while
 *  `mfl.auth_link` is off; 403 `mfl_bad_credentials` on a rejected login. */
export async function entryMflAuthLeagues(args: {
  username: string;
  password: string;
  year?: number;
}): Promise<MflAuthLeague[]> {
  const res = await api.post<{ year: number; leagues: MflAuthLeague[] }>(
    '/api/entry/platform',
    {
      platform: 'mfl',
      action: 'auth_leagues',
      username: args.username,
      password: args.password,
      year: args.year,
    },
    { skipAuth: true },
  );
  return res?.leagues || [];
}

// Pre-auth funnel analytics: the mint IS the sign-in attempt for a platform
// entry (the moment the user claims their team), so it carries the
// signin_* funnel with method 'espn'/'mfl' — value-only addition on the
// registered `method` prop (tracking-plan addendum 2026-08-26).
function entryErrorCode(err: any): string {
  if (typeof err?.code === 'string' && err.code) return err.code;
  if (err?.isTimeout) return 'timeout';
  if (typeof err?.status === 'number' && err.status > 0) return `http_${err.status}`;
  return 'unknown';
}

/** Claim a team: mint the entry session and store its token. The caller
 *  (sheet in entry mode) follows this with the canonical link import. */
export async function entryPlatformMint(
  args:
    | { platform: 'espn'; espnLeagueId: string; season?: number;
        teamId: number; espnS2?: string; swid?: string }
    | { platform: 'mfl'; leagueInput: string; year?: number; teamId: string },
): Promise<EntryMintResponse> {
  track('signin_attempted', { method: args.platform }, 'SignIn');
  try {
    const body =
      args.platform === 'espn'
        ? {
            platform: 'espn',
            espn_league_id: args.espnLeagueId,
            season: args.season,
            team_id: args.teamId,
            espn_s2: args.espnS2,
            swid: args.swid,
          }
        : {
            platform: 'mfl',
            mfl_league_id: args.leagueInput,
            year: args.year,
            franchise_id: args.teamId,
          };
    const res = await api.post<EntryMintResponse>('/api/entry/platform', body, {
      skipAuth: true,
    });
    await setSessionToken(res.session_token);
    track('signin_succeeded', { method: args.platform }, 'SignIn');
    return res;
  } catch (err) {
    track(
      'signin_failed',
      { method: args.platform, error_code: entryErrorCode(err) },
      'SignIn',
    );
    throw err;
  }
}
