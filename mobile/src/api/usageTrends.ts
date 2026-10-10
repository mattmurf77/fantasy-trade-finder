import { api } from './client';

// Usage Trends (flag `usage_trends.enabled`, docs/plans/usage-trends/scope.md)
// — GET /api/usage-trends. Wire contract: docs/api-reference.md. The server
// does all the math (team share, played-weeks averages, signals) and the
// display order (`rank`); clients render and filter, never re-derive or
// re-sort. Pure readers over this payload live in utils/usageTrends.ts.

export type UsageMetric = 'snaps' | 'carries' | 'targets';
export type UsageWeekStatus = 'played' | 'out' | 'bye';
export type UsageSignalKind = 'spike' | 'return' | 'new' | 'out' | 'rising' | 'falling';

/** One headline per metric. Fields by kind: spike/return carry week, count,
 *  share, prev_share, delta, delta_share, missed; new carries week, count,
 *  share, missed; out carries week; rising/falling carry from_share,
 *  to_share, per_week. Shares are % of the team (0–100). */
export interface UsageSignal {
  kind: UsageSignalKind;
  week?: number;
  count?: number;
  share?: number | null;
  prev_share?: number | null;
  delta?: number | null;
  delta_share?: number | null;
  missed?: number;
  from_share?: number;
  to_share?: number;
  per_week?: number;
}

export interface UsageMetricBlock {
  /** Aligned with `weeks`; null on a week the player did not play. */
  counts: (number | null)[];
  /** % of the team that week, aligned with `weeks`; null when not played. */
  shares: (number | null)[];
  /** Played weeks only — byes and missed games are left out. */
  avg: number | null;
  avg_share: number | null;
  signal: UsageSignal | null;
  /** Server display order for this metric; 1 shows first. */
  rank: number;
}

export interface UsagePlayer {
  player_id: string;
  name: string;
  position: 'RB' | 'WR' | 'TE';
  team: string;
  status: UsageWeekStatus[];
  snaps: UsageMetricBlock;
  carries: UsageMetricBlock;
  targets: UsageMetricBlock;
}

/** Roster context for one of the caller's leagues. `rosters` maps a listed
 *  player to an owner key; absent = free agent there. `ok: false` = unknown
 *  (no roster source, or not the caller's league). */
export interface UsageLeague {
  league_id: string;
  ok: boolean;
  me: string | null;
  owners: Record<string, string>;
  rosters: Record<string, string>;
}

export interface UsageTrendsResponse {
  season: number | null;
  /** The selection this payload covers (ascending). */
  weeks: number[];
  /** Every completed week this season — what the week picker offers. */
  available_weeks: number[];
  in_season: boolean;
  league_id: string;
  players: UsagePlayer[];
  /** [0] is the focused league, then the requested others in order. */
  leagues: UsageLeague[];
}

/** `weeks` null/absent = the server's default (the last four completed). */
export async function getUsageTrends(
  leagueId: string,
  otherLeagueIds: string[],
  weeks?: number[] | null,
) {
  const others = otherLeagueIds.filter((id) => id && id !== leagueId);
  const qs =
    `league_id=${encodeURIComponent(leagueId)}` +
    (others.length ? `&league_ids=${others.map(encodeURIComponent).join(',')}` : '') +
    (weeks && weeks.length ? `&weeks=${weeks.join(',')}` : '');
  return api.get<UsageTrendsResponse>(`/api/usage-trends?${qs}`);
}
