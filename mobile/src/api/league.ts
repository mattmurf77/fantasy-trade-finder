import { api } from './client';
import type { ScoringFormat } from '../shared/types';

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

// ── Copy tiers from one scoring format to the other ───────────────────
// POST /api/tiers/copy-from-format
//
// Copies the user's tier assignments (tier label + within-tier rank) from
// `fromFormat` into `toFormat`. Backend handles the per-format band
// translation: a player at QB1 Elite in 1QB PPR stays at QB1 Elite in SF
// TEP, with new ELO values appropriate to SF TEP's bands.
//
// Sends X-Scoring-Format: toFormat so the backend's `_active_format`
// resolves to the target format explicitly — without this, a user who
// landed on Tiers already on SF TEP without ever toggling the format in
// this session would have sess['active_format'] still set to the
// session_init default (1qb_ppr), the endpoint would see from==to and
// error. Mirrors the web `onCopyTiersFromOtherFormat` belt-and-suspenders
// pattern (header AND body to_format).
//
// Destructive: replaces the target format's existing tier overrides
// wholesale. Caller should confirm before invoking.
export interface CopyTiersResponse {
  ok: boolean;
  from_format?: ScoringFormat;
  to_format?: ScoringFormat;
  position_counts?: Record<string, number>;
  total?: number;
  error?: string;
}
export async function copyTiersFromFormat(
  fromFormat: ScoringFormat,
  toFormat: ScoringFormat,
): Promise<CopyTiersResponse> {
  return api.post<CopyTiersResponse>(
    '/api/tiers/copy-from-format',
    { from_format: fromFormat, to_format: toFormat },
    { headers: { 'X-Scoring-Format': toFormat } },
  );
}
