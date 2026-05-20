import { api } from './client';
import type { PortfolioRow, PortfolioTier } from '../shared/types';

// ── League preferences (team outlook + positional prefs) ─────────
// Mirrors the web app's saveOutlookAndPreferences flow.
// The backend stores these on the session + league_preferences table.
//
// CONTRACT: backend uses `team_outlook` as the field name (see
// backend/server.py:set_league_preferences). Earlier code used
// `outlook_value` here which produced a 400 from the server.

export type Outlook =
  | 'championship'
  | 'contender'
  | 'rebuilder'
  | 'jets'
  | 'not_sure'
  | null;

export interface LeaguePreferences {
  team_outlook: Outlook;
  acquire_positions: string[];
  trade_away_positions: string[];
}

export async function getLeaguePreferences(leagueId: string) {
  return api.get<LeaguePreferences>(
    `/api/league/preferences?league_id=${encodeURIComponent(leagueId)}`,
  );
}

export async function saveLeaguePreferences(leagueId: string, prefs: LeaguePreferences) {
  return api.post<any>('/api/league/preferences', {
    league_id: leagueId,
    ...prefs,
  });
}

export interface LeagueCoverage {
  league_id: string;
  total_opponents: number;
  ranked_opponents: number;
}
export async function getLeagueCoverage(leagueId: string) {
  return api.get<LeagueCoverage>(
    `/api/league/coverage?league_id=${encodeURIComponent(leagueId)}`,
  );
}

// ── League summary ────────────────────────────────────────────────
// Roll-up shown on the League tab. Backend: GET /api/league/summary
//
// NB: deliberately named LeagueSummaryRollup, not LeagueSummary, to
// avoid colliding with the LeagueSummary in shared/types.ts (which
// describes a Sleeper league as the picker sees it — totally different
// shape). IDE auto-import + grep both stay unambiguous this way.
export interface LeagueSummaryRollup {
  league_id: string;
  league_name?: string;
  default_scoring?: string | null;
  matches_pending?: number;
  matches_accepted?: number;
  leaguemates_total?: number;
  leaguemates_joined?: number;
  leaguemates_unlocked_1qb?: number;
  leaguemates_unlocked_sf?: number;
  // Optional richer fields the backend may already return
  members?: Array<{
    user_id: string;
    username?: string;
    display_name?: string;
    avatar?: string | null;
    joined?: boolean;
    unlocked_1qb?: boolean;
    unlocked_sf?: boolean;
  }>;
}
export async function getLeagueSummary(leagueId: string) {
  return api.get<LeagueSummaryRollup>(
    `/api/league/summary?league_id=${encodeURIComponent(leagueId)}`,
  );
}

// ── Leaguemate roster ──────────────────────────────────────────────
// Backend: GET /api/league/members. Powers the "Leaguemates" roster
// list on the League tab (joined ✓ / not-joined). Sorted joined first
// alpha, then not-joined alpha.
export interface LeagueMember {
  user_id: string;
  username: string;
  display_name: string;
  avatar: string | null;
  joined: boolean;
}
export async function getLeagueMembers(leagueId: string) {
  return api.get<{ members: LeagueMember[] }>(
    `/api/league/members?league_id=${encodeURIComponent(leagueId)}`,
  );
}

// ── Portfolio (cross-league exposure) ─────────────────────────────
// Backend: GET /api/portfolio.
// Server returns rows shaped like:
//   { player_id, name, pos, exposure (int), total_leagues, league_names: [..] }
// We adapt to the richer PortfolioRow shape the mobile UI expects.
// The backend doesn't currently emit per-league tier info, so each
// exposure entry is marked 'pool' — the UI shows a neutral chip.
//
// NB: league_id isn't returned (only league_names). We fall back to using
// the league_name as the id for keying since names are unique within a
// user's account in practice. If/when the backend adds league_ids we can
// drop the fallback.
export interface PortfolioApiRow {
  player_id: string;
  name: string;
  pos: string;
  exposure: number;
  total_leagues: number;
  league_names: string[];
}
export async function getPortfolio(): Promise<{ players: PortfolioRow[] }> {
  const raw = await api.get<{ players: PortfolioApiRow[] }>('/api/portfolio');
  const players: PortfolioRow[] = (raw?.players || []).map((r) => ({
    player: {
      id: r.player_id,
      name: r.name || r.player_id,
      position: r.pos || '',
    },
    exposure: (r.league_names || []).map((nm) => ({
      league_id: nm,
      league_name: nm,
      tier: 'pool' as PortfolioTier,
    })),
    total_leagues: r.total_leagues || (r.league_names || []).length,
  }));
  return { players };
}

// ── Connect another league (paste a Sleeper URL) ──────────────────
// Backend: POST /api/league/parse-url. Returns
//   { platform, league_id, name, supported }
// We surface the same data shape callers expect: { ok, league_id, league_name }.
// Non-Sleeper platforms (supported=false) are reported as a soft error so
// the caller can render a friendly "Sleeper-only for now" toast.
export interface ConnectLeagueResult {
  ok: boolean;
  league_id: string;
  league_name: string;
  /** Sleeper / espn / mfl — set by the backend's URL parser. */
  platform: 'sleeper' | 'espn' | 'mfl' | string;
  /** When false, backend recognized the URL but full sync isn't wired up
   *  yet (ESPN / MFL today). UI should keep the user where they are. */
  supported: boolean;
}
export async function connectLeague(sleeperUrl: string): Promise<ConnectLeagueResult> {
  const res = await api.post<{
    platform: string;
    league_id: string;
    name?: string | null;
    supported: boolean;
  }>('/api/league/parse-url', { url: sleeperUrl });
  return {
    ok: !!res?.supported && !!res?.league_id,
    league_id: res?.league_id || '',
    league_name: res?.name || (res?.league_id ? `League ${res.league_id}` : ''),
    platform: res?.platform || '',
    supported: !!res?.supported,
  };
}
