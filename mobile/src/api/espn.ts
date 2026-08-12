import { api, ApiError } from './client';
import type { SessionInitBody } from './auth';
import type { SavedUser } from '../state/useSession';

// ── ESPN league linking (flag `espn.link`; Phase 1 read-only import) ─────
// Backend routes (docs/api-reference.md):
//   POST /api/espn/link    — preview (no team_id) → choose team → import
//   GET  /api/espn/leagues — linked leagues + membership snapshot (rosters
//                            already crosswalked to Sleeper player ids)
//   POST /api/espn/import  — re-sync rosters for a linked league
// All routes 404 while the flag is off — callers gate on useFlag('espn.link').
//
// ESPN leagues are READ-ONLY imports: rankings/tiers/trios fully work;
// trade features arrive with plan Phase 2. Copy in EspnLinkSheet sets that
// expectation — don't promise trades from here.

export interface EspnCrosswalkReport {
  pool_players: number;
  matched_by_id: number;
  matched_by_name: number;
  match_rate: number;              // 0..1
  out_of_pool: number;             // K/D-ST — not failures
  unmatched: Array<{ name: string; position: string }>;
}

export interface EspnTeamPreview {
  team_id: number;
  name: string;
  owner_display: string;
  mapped_players: number;
}

export interface EspnLinkPreview {
  status: 'choose_team';
  league: {
    espn_league_id: string;
    name: string;
    season: number;
    total_teams: number;
  };
  teams: EspnTeamPreview[];
  report: EspnCrosswalkReport;
}

export interface EspnImportSummary {
  ok: boolean;
  league_id: string;
  name: string;
  platform: 'espn';
  season: number;
  auth: 'public' | 'cookie';
  total_teams: number;
  teams_imported: number;
  my_team_id: number;
  my_roster: string[];             // Sleeper player ids
  report: EspnCrosswalkReport;
}

export interface EspnLinkRequest {
  espnLeagueId: string;
  season?: number;
  teamId?: number;
  /** Private-league cookies — both or neither (backend 400s otherwise). */
  espnS2?: string;
  swid?: string;
}

export async function linkEspnLeague(
  req: EspnLinkRequest,
): Promise<EspnLinkPreview | EspnImportSummary> {
  return api.post<EspnLinkPreview | EspnImportSummary>('/api/espn/link', {
    espn_league_id: req.espnLeagueId,
    season: req.season,
    team_id: req.teamId,
    espn_s2: req.espnS2 || undefined,
    swid: req.swid || undefined,
  });
}

export function isEspnPreview(
  res: EspnLinkPreview | EspnImportSummary,
): res is EspnLinkPreview {
  return (res as EspnLinkPreview).status === 'choose_team';
}

/** Credential-only store (send-auth lazy flow, 2026-08-11): persist a
 *  captured espn_s2 + SWID pair WITHOUT linking a league — the same POST
 *  /api/espn/link, minus espn_league_id. Used by EspnConnectScreen when
 *  entered from the trade-send path: the league is already imported, only
 *  the account credential is missing.
 *
 *  Credential-honesty fix (2026-08-12): the server now VERIFIES the pair
 *  with one live authenticated ESPN read before storing — a success here
 *  means the sign-in actually works. Failures throw ApiError:
 *    403 espn_bad_credentials — ESPN rejected the pair; nothing stored.
 *      Narrow with espnCredentialsRejected(); the fix is a fresh sign-in.
 *    502 espn_unavailable — ESPN unreachable; NOT a credential verdict,
 *      nothing stored; retry the same pair. */
export async function storeEspnCredentials(
  espnS2: string,
  swid: string,
): Promise<{ connected: boolean; verified?: boolean }> {
  return api.post<{ connected: boolean; verified?: boolean }>('/api/espn/link', {
    espn_s2: espnS2,
    swid,
  });
}

/** True when a storeEspnCredentials failure is ESPN's verdict on the pair
 *  itself (403 espn_bad_credentials — sign in again), as opposed to a
 *  transport/outage failure where the same pair may well be fine (retry). */
export function espnCredentialsRejected(err: unknown): boolean {
  return (
    err instanceof ApiError &&
    err.status === 403 &&
    typeof err.body === 'object' &&
    err.body !== null &&
    (err.body as { error?: string }).error === 'espn_bad_credentials'
  );
}

export interface EspnLeagueMember {
  user_id: string;                 // FTF user id for you; synthetic `espn:` otherwise
  username: string;
  display_name: string;
  player_ids: string[];            // Sleeper player ids
}

export interface EspnLeague {
  league_id: string;
  name: string;
  platform: 'espn';
  season: number | null;
  espn_auth: 'public' | 'cookie' | null;
  my_team_id: number | null;
  total_rosters: number | null;
  members: EspnLeagueMember[];
}

export async function getEspnLeagues(): Promise<EspnLeague[]> {
  const res = await api.get<{ leagues: EspnLeague[] }>('/api/espn/leagues');
  return res?.leagues || [];
}

// ── League picker (flag `espn.league_picker`, 2026-08-09) ────────────────
// Discovery, not linking: lists the ESPN fantasy football leagues the
// session user's STORED espn_credentials cookies belong to (WebView capture
// or a prior paste that was already sent through /api/espn/link), so
// EspnLinkSheet can offer a SELECTION list instead of a bare league-id text
// field. Manual entry stays the fallback — this call is allowed to fail
// (403 espn_auth_required with no stored cookies yet is the common case for
// a brand-new capture that hasn't linked anything yet) and callers should
// treat any rejection as "no picker available", not an error to surface.

export interface EspnMyLeague {
  league_id: string;
  league_name: string;
  season: number | null;
  team_name: string | null;
}

export async function getMyEspnLeagues(): Promise<EspnMyLeague[]> {
  const res = await api.get<{ leagues: EspnMyLeague[] }>('/api/espn/my-leagues');
  return res?.leagues || [];
}

export async function importEspnLeague(leagueId: string): Promise<EspnImportSummary> {
  return api.post<EspnImportSummary>('/api/espn/import', { league_id: leagueId });
}

// ── Helpers ───────────────────────────────────────────────────────────────

/** Accepts a bare numeric ESPN league id or a fantasy.espn.com URL with a
 *  leagueId query param. Returns the id, or null when unrecognizable. */
export function parseEspnLeagueInput(input: string): string | null {
  const raw = (input || '').trim();
  if (!raw) return null;
  if (/^\d+$/.test(raw)) return raw;
  const m = raw.match(/fantasy\.espn\.com\/.*[?&]leagueId=(\d+)/i);
  return m ? m[1] : null;
}

/** True when the cached league list marks this id as an ESPN import. Used
 *  by api/auth's session-init builders to route ESPN leagues through the
 *  backend snapshot instead of Sleeper's roster endpoints (which would 404
 *  on a numeric non-Sleeper id). Relies on the AsyncStorage-persisted
 *  league cache, which useSession hydrates at boot. */
export function isEspnLeague(leagueId: string): boolean {
  try {
    const { useSession } = require('../state/useSession');
    const leagues = useSession.getState().leagues || [];
    return leagues.some(
      (lg: { league_id: string; platform?: string }) =>
        lg.league_id === leagueId && lg.platform === 'espn',
    );
  } catch {
    return false;
  }
}

/** Build a standard /api/session/init body for an ESPN league from the
 *  backend's imported snapshot (GET /api/espn/leagues). Mirrors
 *  api/auth.buildSessionInitBody's Sleeper flow — opponents keep their
 *  synthetic `espn:` user ids. */
export async function buildEspnSessionInitBody(
  user: SavedUser,
  lg: { league_id: string; name: string },
): Promise<SessionInitBody> {
  const leagues = await getEspnLeagues();
  const target = leagues.find((l) => l.league_id === lg.league_id);
  if (!target) {
    throw new Error('ESPN league not linked — link it again from the league picker.');
  }
  const mine = target.members.find((m) => m.user_id === user.user_id);
  const opponentRosters = target.members
    .filter((m) => m.user_id !== user.user_id)
    .map((m) => ({
      user_id: m.user_id,
      username: m.display_name || m.username || m.user_id,
      player_ids: (m.player_ids || []).filter(Boolean),
    }))
    .filter((m) => m.player_ids.length > 0);
  return {
    user_id: user.user_id,
    username: user.username,
    display_name: user.display_name,
    avatar: user.avatar_id,
    league_id: lg.league_id,
    league_name: target.name || lg.name,
    user_player_ids: (mine?.player_ids || []).filter(Boolean),
    opponent_rosters: opponentRosters,
  };
}
