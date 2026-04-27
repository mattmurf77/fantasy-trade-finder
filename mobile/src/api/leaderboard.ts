import { api } from './client';

export type LeaderboardScope  = 'league' | 'universal';
export type LeaderboardMetric = 'streak' | 'ranks';
export type LeaderboardWindow = 'week' | 'month' | 'season' | 'all';

export interface LeaderboardRow {
  rank:         number;
  user_id:      string;
  username:     string | null;
  display_name: string;
  avatar:       string | null;
  value:        number;
  is_self:      boolean;
}

export interface Leaderboard {
  metric:    LeaderboardMetric;
  window:    LeaderboardWindow | null;
  scope:     LeaderboardScope;
  league_id: string | null;
  rows:      LeaderboardRow[];
  self_row:  LeaderboardRow | null;
}

export interface GetLeaderboardOpts {
  scope:    LeaderboardScope;
  metric:   LeaderboardMetric;
  window?:  LeaderboardWindow;       // required when metric === 'ranks'
  leagueId?: string;                 // required when scope === 'league'
}

// GET /api/leaderboard — top 50 + optional sticky self-row.
//
// Backend caches universal queries for 5 min; per-user is_self tags are
// applied outside the cache, so callers don't need to do that work.
export async function getLeaderboard(opts: GetLeaderboardOpts) {
  const params = new URLSearchParams({
    scope:  opts.scope,
    metric: opts.metric,
  });
  if (opts.window)   params.set('window', opts.window);
  if (opts.leagueId) params.set('league_id', opts.leagueId);
  return api.get<Leaderboard>(`/api/leaderboard?${params.toString()}`);
}
