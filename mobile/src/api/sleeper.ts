import { api } from './client';
import type { LeagueSummary } from '../shared/types';

// Sleeper-backed endpoints the backend proxies (so we don't hit api.sleeper.app
// directly from the client — the Flask server caches responses). Matches the
// shape of the web app's calls in app.js.

// GET /api/sleeper/leagues/<user_id> — user's NFL 2026 leagues + any
// locally-created leagues tied to that user.
export async function getLeagues(userId: string): Promise<LeagueSummary[]> {
  const data = await api.get<any[]>(`/api/sleeper/leagues/${userId}`);
  return (data || []).map((lg) => ({
    league_id: String(lg.league_id),
    name: lg.name || 'League',
    avatar: lg.avatar ?? null,
    total_rosters: lg.total_rosters ?? undefined,
    platform: lg.platform ?? 'sleeper',
  }));
}

// GET /api/sleeper/rosters/<league_id>
export interface RosterRow {
  owner_id: string;
  roster_id: number;
  players: string[] | null;
  starters?: string[] | null;
}
export async function getLeagueRosters(leagueId: string) {
  return api.get<RosterRow[]>(`/api/sleeper/rosters/${leagueId}`);
}

// GET /api/sleeper/league_users/<league_id>
export interface LeagueUser {
  user_id: string;
  username: string;
  display_name?: string;
  avatar?: string | null;
}
export async function getLeagueUsers(leagueId: string) {
  return api.get<LeagueUser[]>(`/api/sleeper/league_users/${leagueId}`);
}

// GET /api/sleeper/players — warms the 5MB player cache. Don't call from
// a tight loop; we call it once during session init and then rely on the
// backend's server-side cache.
export async function warmPlayerCache() {
  return api.get<Record<string, any>>('/api/sleeper/players');
}
