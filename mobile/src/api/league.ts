import { api } from './client';

// ── League preferences (team outlook + positional prefs) ─────────
// Mirrors the web app's saveOutlookAndPreferences flow.
// The backend stores these on the session + league_preferences table.

export type Outlook = 'championship' | 'contender' | 'rebuilder' | 'jets' | null;

export interface LeaguePreferences {
  outlook_value: Outlook;
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
