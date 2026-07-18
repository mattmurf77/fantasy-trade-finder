import { api } from './client';
import type { SessionInitBody } from './auth';
import type { SavedUser } from '../state/useSession';

// ── Generic multi-platform league linking (MFL + Fleaflicker) ────────────────
// Phase 1 read-only import, mirroring api/espn.ts but for the zero-auth
// platforms (no cookie paste). Each platform gates on its own flag
// (`mfl.link` / `fleaflicker.link`); routes 404 while the flag is off.
//   POST /api/{platform}/link    — preview (no team id) → choose team → import
//   GET  /api/{platform}/leagues — linked leagues + membership snapshot
//   POST /api/{platform}/import  — re-sync rosters
//   POST /api/fleaflicker/discover — list a user's leagues by email
// Rosters come back already crosswalked to Sleeper player ids. ESPN keeps its
// own module (api/espn.ts) because of the private-league cookie flow.

export type LinkPlatform = 'mfl' | 'fleaflicker';

export interface PlatformCrosswalkReport {
  pool_players: number;
  matched_by_id: number;
  matched_by_name: number;
  match_rate: number;              // 0..1
  out_of_pool: number;             // K/D-ST/IDP — not failures
  unmatched: Array<{ name: string; position: string }>;
}

export interface PlatformTeamPreview {
  team_id: string;                 // MFL franchise id ("0001") | Fleaflicker team id
  name: string;
  mapped_players: number;
}

export interface PlatformLinkPreview {
  status: 'choose_team';
  league: {
    league_id: string;
    name: string;
    season?: number;
    total_teams: number;
    host?: string;                 // MFL wwwNN host (echoed back for re-sync)
  };
  teams: PlatformTeamPreview[];
  report: PlatformCrosswalkReport;
}

export interface PlatformImportSummary {
  ok: boolean;
  league_id: string;
  name: string;
  platform: LinkPlatform;
  season?: number;
  auth: 'public';
  total_teams: number;
  teams_imported: number;
  my_team_id: string;
  my_roster: string[];             // Sleeper player ids
  future_picks_stored?: number;    // MFL only — stored raw, not engine-wired yet
  report: PlatformCrosswalkReport;
}

export interface PlatformLinkRequest {
  platform: LinkPlatform;
  /** MFL: league URL or numeric id. Fleaflicker: numeric league id. */
  leagueInput: string;
  /** MFL only. */
  year?: number;
  /** Set on the import (second) call — which team is the user's. */
  teamId?: string;
}

function normalizePreview(res: any): PlatformLinkPreview {
  const lg = res.league || {};
  return {
    status: 'choose_team',
    league: {
      league_id: String(lg.mfl_league_id ?? lg.fleaflicker_league_id ?? lg.league_id ?? ''),
      name: lg.name || '',
      season: lg.season,
      total_teams: lg.total_teams,
      host: lg.host,
    },
    teams: (res.teams || []).map((t: any) => ({
      team_id: String(t.team_id),
      name: t.name,
      mapped_players: t.mapped_players,
    })),
    report: res.report,
  };
}

export function isPlatformPreview(
  res: PlatformLinkPreview | PlatformImportSummary,
): res is PlatformLinkPreview {
  return (res as PlatformLinkPreview).status === 'choose_team';
}

export async function linkPlatformLeague(
  req: PlatformLinkRequest,
): Promise<PlatformLinkPreview | PlatformImportSummary> {
  const body: Record<string, unknown> = { team_id: req.teamId };
  if (req.platform === 'mfl') {
    // Send the raw input as both id and url — the backend parses either.
    body.mfl_league_url = req.leagueInput;
    body.mfl_league_id = req.leagueInput;
    body.year = req.year;
    // MFL binds the chosen team via franchise_id.
    if (req.teamId) body.franchise_id = req.teamId;
  } else {
    body.fleaflicker_league_id = req.leagueInput;
  }
  const res = await api.post<any>(`/api/${req.platform}/link`, body);
  if (res?.status === 'choose_team') return normalizePreview(res);
  return res as PlatformImportSummary;
}

export interface PlatformLeagueMember {
  user_id: string;                 // FTF user id for you; synthetic `mfl:`/`flea:` otherwise
  username: string;
  display_name: string;
  player_ids: string[];
}

export interface PlatformLeague {
  league_id: string;
  name: string;
  platform: LinkPlatform;
  season: number | null;
  my_team: string | null;
  total_rosters: number | null;
  members: PlatformLeagueMember[];
}

export async function getPlatformLeagues(platform: LinkPlatform): Promise<PlatformLeague[]> {
  const res = await api.get<{ leagues: PlatformLeague[] }>(`/api/${platform}/leagues`);
  return res?.leagues || [];
}

export async function importPlatformLeague(
  platform: LinkPlatform,
  leagueId: string,
): Promise<PlatformImportSummary> {
  return api.post<PlatformImportSummary>(`/api/${platform}/import`, { league_id: leagueId });
}

export interface FleaflickerDiscovered {
  league_id: string;
  name: string;
  size?: number;
}

export async function discoverFleaflickerLeagues(email: string): Promise<FleaflickerDiscovered[]> {
  const res = await api.post<{ leagues: FleaflickerDiscovered[] }>(
    '/api/fleaflicker/discover', { email },
  );
  return res?.leagues || [];
}

// ── Helpers ──────────────────────────────────────────────────────────────────

/** MFL: numeric league id, or a myfantasyleague.com URL (path or ?L=). */
export function parseMflLeagueInput(input: string): string | null {
  const raw = (input || '').trim();
  if (!raw) return null;
  if (/^\d{4,6}$/.test(raw)) return raw;
  let m = raw.match(/myfantasyleague\.com\/\d{4}\/(?:home|options|standings)\/(\d{4,6})/i);
  if (m) return m[1];
  m = raw.match(/[?&]L=(\d{4,6})/i);
  return m ? m[1] : null;
}

/** Fleaflicker: numeric league id, or a fleaflicker.com/nfl/leagues/<id> URL. */
export function parseFleaflickerLeagueInput(input: string): string | null {
  const raw = (input || '').trim();
  if (!raw) return null;
  if (/^\d+$/.test(raw)) return raw;
  const m = raw.match(/fleaflicker\.com\/.*\/leagues\/(\d+)/i);
  return m ? m[1] : null;
}

function isPlatformLeague(leagueId: string, platform: LinkPlatform): boolean {
  try {
    const { useSession } = require('../state/useSession');
    const leagues = useSession.getState().leagues || [];
    return leagues.some(
      (lg: { league_id: string; platform?: string }) =>
        lg.league_id === leagueId && lg.platform === platform,
    );
  } catch {
    return false;
  }
}

export const isMflLeague = (id: string) => isPlatformLeague(id, 'mfl');
export const isFleaflickerLeague = (id: string) => isPlatformLeague(id, 'fleaflicker');

/** Build a standard /api/session/init body for a linked MFL/Fleaflicker league
 *  from the backend's imported snapshot. Mirrors api/espn.buildEspnSessionInitBody. */
export async function buildPlatformSessionInitBody(
  platform: LinkPlatform,
  user: SavedUser,
  lg: { league_id: string; name: string },
): Promise<SessionInitBody> {
  const leagues = await getPlatformLeagues(platform);
  const target = leagues.find((l) => l.league_id === lg.league_id);
  if (!target) {
    throw new Error('League not linked — link it again from the league picker.');
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
