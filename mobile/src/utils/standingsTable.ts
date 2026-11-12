// The Standings page's single table (docs/plans/home-engagement/
// scope-standings-table.md). ZERO runtime imports, so
// tests/check-standings-table.js can transpile and execute it under plain node.
//
// One row per team: the current standings (utils/standings.ts, from the
// session-seeded Sleeper rosters) joined by roster id to the SAVED weekly
// forecast when there is one. Two views of the same rows behind a pill:
//   Record — W–L · Proj. W–L · Playoffs
//   Points — PF · Max PF · Proj. Max PF
// Every heading sorts. A forecast-only column shows a dash when there is no
// forecast for the team, and dashes sort last in both directions.

export type StandingsView = 'record' | 'points';
export type StandingsColumn = 'team' | 'wl' | 'projWl' | 'playoffs' | 'pf' | 'maxPf' | 'projMaxPf';
/** 'desc' = biggest first (best record, most points); for Team, 'asc' = A–Z. */
export type SortDir = 'asc' | 'desc';
export interface StandingsSort { column: StandingsColumn; dir: SortDir }

export const VIEW_COLUMNS: Record<StandingsView, readonly [StandingsColumn, StandingsColumn, StandingsColumn]> = {
  record: ['wl', 'projWl', 'playoffs'],
  points: ['pf', 'maxPf', 'projMaxPf'],
};

/** Record opens on W–L (best first), Points on PF (most first). */
export const DEFAULT_SORT: Record<StandingsView, StandingsSort> = {
  record: { column: 'wl', dir: 'desc' },
  points: { column: 'pf', dir: 'desc' },
};

export const DASH = '—';

/** Forecast fields the table reads (a structural subset of api/leagueProjections ProjectionTeam). */
export interface ForecastTeamInput {
  roster_id: number;
  modal_record: number[];
  expected_record: number[];
  playoff_probability: number;
  bye_probability: number;
  maxpf_mean: number;
  current_maxpf: number;
}

/** Current-standings fields the table reads (a structural subset of utils/standings StandingsRow). */
export interface StandingsRowInput {
  rosterId: number;
  name: string;
  isYou: boolean;
  place: number;
  wins: number;
  losses: number;
  ties: number;
  winPct: number;
  pointsFor: number;
  maxPf: number | null;
}

export interface TableRow<F extends ForecastTeamInput = ForecastTeamInput> {
  rosterId: number;
  name: string;
  isYou: boolean;
  /** Standings place (W–L, then points for, then roster id): the tiebreak for every sort. */
  place: number;
  wins: number;
  losses: number;
  ties: number;
  winPct: number;
  pointsFor: number;
  /** Sleeper's season-to-date Max PF; the saved forecast's when Sleeper sent none; else null. */
  maxPf: number | null;
  forecast: F | null;
}

/** Join the standings rows to the forecast teams by roster id (standings order kept). */
export function buildTableRows<F extends ForecastTeamInput>(
  rows: readonly StandingsRowInput[],
  forecastTeams: readonly F[] | null,
): TableRow<F>[] {
  const byRoster = new Map<number, F>();
  for (const t of forecastTeams ?? []) byRoster.set(t.roster_id, t);
  return rows.map((r) => {
    const forecast = byRoster.get(r.rosterId) ?? null;
    const fallbackMax = forecast && Number.isFinite(forecast.current_maxpf) ? forecast.current_maxpf : null;
    return {
      rosterId: r.rosterId,
      name: r.name,
      isYou: r.isYou,
      place: r.place,
      wins: r.wins,
      losses: r.losses,
      ties: r.ties,
      winPct: r.winPct,
      pointsFor: r.pointsFor,
      maxPf: r.maxPf ?? fallbackMax,
      forecast,
    };
  });
}

function recordPct(rec: readonly number[]): number {
  const w = rec[0] ?? 0;
  const l = rec[1] ?? 0;
  const t = rec[2] ?? 0;
  const g = w + l + t;
  return g > 0 ? (w + t / 2) / g : 0;
}

/** Ascending comparison values for a column; null = no value (a dash). */
function sortValue(row: TableRow, column: StandingsColumn): number[] | null {
  const f = row.forecast;
  switch (column) {
    case 'wl': return [row.winPct, row.pointsFor];
    case 'projWl': return f ? [recordPct(f.modal_record), recordPct(f.expected_record)] : null;
    case 'playoffs': return f ? [f.playoff_probability] : null;
    case 'pf': return [row.pointsFor];
    case 'maxPf': return row.maxPf == null ? null : [row.maxPf];
    case 'projMaxPf': return f ? [f.maxpf_mean] : null;
    default: return null;
  }
}

/** A sorted copy. Ties keep standings order; dashes go last either way. */
export function sortRows<R extends TableRow>(rows: readonly R[], sort: StandingsSort): R[] {
  const sign = sort.dir === 'asc' ? 1 : -1;
  return [...rows].sort((a, b) => {
    let c = 0;
    if (sort.column === 'team') {
      c = sign * a.name.localeCompare(b.name, undefined, { sensitivity: 'base' });
    } else {
      const va = sortValue(a, sort.column);
      const vb = sortValue(b, sort.column);
      if (va == null || vb == null) {
        c = va == null && vb == null ? 0 : va == null ? 1 : -1;
      } else {
        for (let i = 0; i < va.length && c === 0; i += 1) c = sign * (va[i] - vb[i]);
      }
    }
    return c || a.place - b.place;
  });
}

/** Tapping a heading: the active one reverses; a new one starts best first (Team: A–Z). */
export function nextSort(current: StandingsSort, column: StandingsColumn): StandingsSort {
  if (current.column === column) return { column, dir: current.dir === 'asc' ? 'desc' : 'asc' };
  return { column, dir: column === 'team' ? 'asc' : 'desc' };
}

/** "8–6", or "8–5–1" with a tie. En dash, matching utils/standings formatRecord. */
export function recordText(rec: readonly number[]): string {
  const base = `${rec[0] ?? 0}–${rec[1] ?? 0}`;
  return (rec[2] ?? 0) > 0 ? `${base}–${rec[2]}` : base;
}

/** Playoff odds as a whole percent: under 0.5% "<1%", 99.95% and over "100%". */
export function oddsText(probability: number): string {
  const p = probability * 100;
  if (p < 0.5) return '<1%';
  if (p >= 99.95) return '100%';
  return `${Math.min(99, Math.max(1, Math.round(p)))}%`;
}

/** Whole points with thousands commas ("1,498"). No toLocaleString: Hermes' is locale-dependent. */
export function pointsText(n: number): string {
  return String(Math.round(n)).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
}

/** Average final record to one decimal ("8.3–5.7"; a tie column only when it rounds above 0). */
export function averageRecordText(rec: readonly number[]): string {
  const base = `${(rec[0] ?? 0).toFixed(1)}–${(rec[1] ?? 0).toFixed(1)}`;
  return (rec[2] ?? 0) >= 0.05 ? `${base}–${(rec[2] ?? 0).toFixed(1)}` : base;
}

/** One table cell. Forecast columns without a forecast, and an unknown Max PF, are a dash. */
export function cellText(row: TableRow, column: StandingsColumn): string {
  const f = row.forecast;
  switch (column) {
    case 'team': return row.name;
    case 'wl': return recordText([row.wins, row.losses, row.ties]);
    case 'projWl': return f ? recordText(f.modal_record) : DASH;
    case 'playoffs': return f ? oddsText(f.playoff_probability) : DASH;
    case 'pf': return pointsText(row.pointsFor);
    case 'maxPf': return row.maxPf == null ? DASH : pointsText(row.maxPf);
    case 'projMaxPf': return f ? pointsText(f.maxpf_mean) : DASH;
    default: return DASH;
  }
}

/** Heading text. "Proj. Max PF" breaks after "Proj." to leave room for team names. */
export const COLUMN_LABEL: Record<StandingsColumn, string> = {
  team: 'Team',
  wl: 'W–L',
  projWl: 'Proj. W–L',
  playoffs: 'Playoffs',
  pf: 'PF',
  maxPf: 'Max PF',
  projMaxPf: 'Proj.\nMax PF',
};

/** VoiceOver names for the headings. */
export const COLUMN_SPOKEN: Record<StandingsColumn, string> = {
  team: 'team name',
  wl: 'record',
  projWl: 'projected record',
  playoffs: 'playoff odds',
  pf: 'points for',
  maxPf: 'Max PF',
  projMaxPf: 'projected Max PF',
};

/**
 * The open team's two summary lines. `leftOut` holds what the current view
 * leaves out of the row; `average` is the forecast's exact average record
 * (with bye odds where the league has byes), or null without a forecast.
 */
export function openTeamLines(
  view: StandingsView,
  row: TableRow,
  playoffByes: number,
): { leftOut: string; average: string | null } {
  const f = row.forecast;
  const leftOut = view === 'record'
    ? [
      `Points for ${row.pointsFor.toFixed(1)}`,
      row.maxPf == null ? null : `Max PF ${pointsText(row.maxPf)}`,
      f ? `Projected Max PF ${pointsText(f.maxpf_mean)}` : null,
    ].filter(Boolean).join(' · ')
    : [
      `Record ${recordText([row.wins, row.losses, row.ties])}`,
      f ? `Projected ${recordText(f.modal_record)}` : null,
      f ? `Playoff odds ${oddsText(f.playoff_probability)}` : null,
    ].filter(Boolean).join(' · ');
  const average = f
    ? `Average final record: ${averageRecordText(f.expected_record)}${playoffByes > 0 ? ` · Bye odds: ${(f.bye_probability * 100).toFixed(1)}%` : ''}`
    : null;
  return { leftOut, average };
}

/** The saved forecast's state words (moved verbatim from the old Projected section). */
export const FORECAST_STATUS: Record<string, string> = {
  no_run: 'Waiting for the first weekly forecast.',
  queued: 'Weekly update queued.', running: 'Weekly update in progress.',
  current: '', stale: 'Weekly update due.',
  refresh_failed: 'Latest update failed.',
  incomplete_projections: 'Missing player or scoring data.',
  unsupported_policy: 'This league’s rules aren’t supported yet.',
  failed: 'Weekly update failed.',
};

export const NO_FORECAST_LINE = 'Projections aren’t available for this league yet.';

/** The status sentence for the forecast read, as the old Projected section worded it. */
export function forecastStatusText(q: { isLoading: boolean; isError: boolean; state: string | null | undefined }): string {
  if (q.isLoading) return 'Loading projections…';
  if (q.isError) return 'Couldn’t check for an update.';
  return FORECAST_STATUS[q.state || 'no_run'] ?? 'Projection unavailable.';
}

/**
 * The one line under the table when there is no forecast to show. `enabled`
 * is false when the forecast read is off (flag `league.projections`), which
 * has no state of its own to name.
 */
export function noForecastLine(q: { enabled: boolean; isLoading: boolean; isError: boolean; state: string | null | undefined }): string {
  if (!q.enabled) return NO_FORECAST_LINE;
  if (q.isLoading) return 'Loading projections…';
  const status = forecastStatusText(q);
  return status ? `${NO_FORECAST_LINE} ${status}` : NO_FORECAST_LINE;
}
