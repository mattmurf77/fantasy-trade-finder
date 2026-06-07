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

// Warmed-once-per-launch guard (INIT-12 Wave 1, FR-5). Set true after the first
// successful warm; lets redundant warm calls within the same launch short-
// circuit. Reset via resetWarmedFlag() when the backend signals its player
// cache was lost (e.g. a dyno restart after boot) so the next league pick
// re-warms before session_init.
let warmedThisLaunch = false;

/** True once warmPlayerCache() has succeeded in this app launch. */
export function isWarmedThisLaunch(): boolean {
  return warmedThisLaunch;
}

/** Clear the warmed-once flag so the next warmPlayerCache() hits the network
 *  again. Called when a session_init reports the player DB is not cached. */
export function resetWarmedFlag(): void {
  warmedThisLaunch = false;
}

// GET /api/sleeper/players/warm — triggers the same server-side cache
// hydration as /api/sleeper/players but returns only {ok, count}. The full
// route serializes ~4.8MB of player JSON the mobile client never reads;
// this variant keeps the response body to a few hundred bytes.
//
// Idempotent within a launch: the first success sets warmedThisLaunch and
// later calls return a synthetic ok without a round-trip (FR-5). App boot and
// initLeagueSession therefore warm the cache exactly once between them.
export async function warmPlayerCache(): Promise<{ ok: boolean; count?: number }> {
  if (warmedThisLaunch) {
    return { ok: true };
  }
  const res = await api.get<{ ok: boolean; count?: number }>('/api/sleeper/players/warm');
  warmedThisLaunch = true;
  return res;
}
