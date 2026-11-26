// The Standings page's single table (docs/plans/home-engagement/
// scope-standings-table.md). Its one runtime import is the zero-import
// playoff-odds rule (./playoffOdds, D-262), so tests/check-standings-table.js
// can transpile and execute both under plain node.
import { playoffOddsText, playoffSortKey, type PlayoffProof } from './playoffOdds';
//
// One row per team: the current standings (utils/standings.ts, from the
// session-seeded Sleeper rosters) joined by roster id to the SAVED weekly
// forecast when there is one. Two views of the same rows behind a pill:
//   Record — W–L · Proj. W–L · Playoffs · SoS
//   Points — PF · Max PF · Proj. Max PF
// Every heading sorts. A forecast-only column shows a dash when there is no
// forecast for the team, and dashes sort last in both directions.

export type StandingsView = 'record' | 'points';
export type StandingsColumn = 'team' | 'wl' | 'projWl' | 'playoffs' | 'sos' | 'pf' | 'maxPf' | 'projMaxPf';
/** 'desc' = biggest first (best record, most points); for Team, 'asc' = A–Z. */
export type SortDir = 'asc' | 'desc';
export interface StandingsSort { column: StandingsColumn; dir: SortDir }

export const VIEW_COLUMNS: Record<StandingsView, readonly StandingsColumn[]> = {
  record: ['wl', 'projWl', 'playoffs', 'sos'],
  points: ['pf', 'maxPf', 'projMaxPf'],
};

/** Record opens on W–L (best first), Points on PF (most first). */
export const DEFAULT_SORT: Record<StandingsView, StandingsSort> = {
  record: { column: 'wl', dir: 'desc' },
  points: { column: 'pf', dir: 'desc' },
};

export const DASH = '—';

/** The forecast week fields the SoS column reads (a structural subset of api/leagueProjections ProjectionWeek). */
export interface ForecastWeekInput {
  week: number;
  opponent_roster_id: number;
  modeled_score_mean: number;
  actual_score_observed?: boolean;
}

/** Forecast fields the table reads (a structural subset of api/leagueProjections ProjectionTeam).
 *  `playoff_clinched` / `playoff_eliminated` (D-262) are absent on a run saved before them. */
export interface ForecastTeamInput extends PlayoffProof {
  roster_id: number;
  modal_record: number[];
  expected_record: number[];
  playoff_probability: number;
  bye_probability: number;
  maxpf_mean: number;
  current_maxpf: number;
  weeks: readonly ForecastWeekInput[];
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
  /** Strength of schedule: rank 1 = toughest remaining schedule; null = a dash. */
  sos: SosCell | null;
}

/** A team's remaining-schedule rank. `band` marks the toughest third ("hard") and the easiest third ("easy"). */
export interface SosCell { mean: number; rank: number; band: 'hard' | 'easy' | null }

/**
 * The average, over a team's remaining weeks (`actual_score_observed !== true`),
 * of each opponent's projected score that same week (the opponent's
 * `modeled_score_mean` for the week). Null without remaining weeks, or when an
 * opponent or its week is missing from the forecast.
 */
export function remainingScheduleMean(team: ForecastTeamInput, byRoster: ReadonlyMap<number, ForecastTeamInput>): number | null {
  const remaining = team.weeks.filter((w) => w.actual_score_observed !== true);
  if (remaining.length === 0) return null;
  let sum = 0;
  for (const w of remaining) {
    const opp = byRoster.get(w.opponent_roster_id)?.weeks.find((o) => o.week === w.week);
    if (!opp || !Number.isFinite(opp.modeled_score_mean)) return null;
    sum += opp.modeled_score_mean;
  }
  return sum / remaining.length;
}

/** 1st, 2nd, 3rd, 4th … 11th, 12th, 13th, 21st. */
export function ordinal(n: number): string {
  const tens = n % 100;
  const suffix = tens >= 11 && tens <= 13 ? 'th' : ({ 1: 'st', 2: 'nd', 3: 'rd' } as Record<number, string>)[n % 10] ?? 'th';
  return `${n}${suffix}`;
}

/** Join the standings rows to the forecast teams by roster id (standings order kept). */
export function buildTableRows<F extends ForecastTeamInput>(
  rows: readonly StandingsRowInput[],
  forecastTeams: readonly F[] | null,
): TableRow<F>[] {
  const byRoster = new Map<number, F>();
  for (const t of forecastTeams ?? []) byRoster.set(t.roster_id, t);
  // SoS ranks (the review build's compute.py): highest mean = 1; an exact tie
  // goes to the lower roster id; thirds of the league's team count.
  const means = rows
    .map((r) => {
      const f = byRoster.get(r.rosterId);
      return { rosterId: r.rosterId, mean: f ? remainingScheduleMean(f, byRoster) : null };
    })
    .filter((m): m is { rosterId: number; mean: number } => m.mean != null)
    .sort((a, b) => b.mean - a.mean || a.rosterId - b.rosterId);
  const sosByRoster = new Map<number, SosCell>();
  means.forEach((m, i) => {
    const rank = i + 1;
    const band = rank <= rows.length / 3 ? 'hard' : rank > (2 * rows.length) / 3 ? 'easy' : null;
    sosByRoster.set(m.rosterId, { mean: m.mean, rank, band });
  });
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
      sos: sosByRoster.get(r.rosterId) ?? null,
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
    // Proof breaks an equal probability: a proven 100% above ">99%", a proven 0% below "<1%".
    case 'playoffs': return f ? playoffSortKey(f.playoff_probability, f) : null;
    // 'desc' (the first tap) puts rank 1, the toughest schedule, first.
    case 'sos': return row.sos ? [-row.sos.rank] : null;
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

/** Playoff odds as a whole percent (D-262): "100%" only when clinched is
 *  proven and "0%" only when elimination is, else ">99%" / "<1%". */
export function oddsText(probability: number, proof: PlayoffProof | null | undefined): string {
  return playoffOddsText(probability, proof, 1);
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
    case 'playoffs': return f ? oddsText(f.playoff_probability, f) : DASH;
    case 'sos': return row.sos ? ordinal(row.sos.rank) : DASH;
    case 'pf': return pointsText(row.pointsFor);
    case 'maxPf': return row.maxPf == null ? DASH : pointsText(row.maxPf);
    case 'projMaxPf': return f ? pointsText(f.maxpf_mean) : DASH;
    default: return DASH;
  }
}

/** Heading text. "Proj. Max PF" breaks after "Proj." and "Playoffs" after "Play" to leave room for
 *  team names. "SoS" keeps its lowercase o (the screen exempts it from the label style's uppercase). */
export const COLUMN_LABEL: Record<StandingsColumn, string> = {
  team: 'Team',
  wl: 'W–L',
  projWl: 'Proj. W–L',
  playoffs: 'Play\noffs',
  sos: 'SoS',
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
  sos: 'strength of schedule',
  pf: 'points for',
  maxPf: 'Max PF',
  projMaxPf: 'projected Max PF',
};

/**
 * The open team's stat rows: what the current view leaves out of the row,
 * then the forecast's exact average record and, where the league has byes,
 * the bye odds. Rows without a value are left out.
 */
export function openTeamStats(view: StandingsView, row: TableRow, playoffByes: number): { label: string; value: string }[] {
  const f = row.forecast;
  const stats: ({ label: string; value: string } | null)[] = view === 'record'
    ? [
      { label: 'Points for', value: row.pointsFor.toFixed(1) },
      row.maxPf == null ? null : { label: 'Max PF', value: pointsText(row.maxPf) },
      f ? { label: 'Projected Max PF', value: pointsText(f.maxpf_mean) } : null,
    ]
    : [
      { label: 'Record', value: recordText([row.wins, row.losses, row.ties]) },
      f ? { label: 'Projected', value: recordText(f.modal_record) } : null,
      f ? { label: 'Playoff odds', value: oddsText(f.playoff_probability, f) } : null,
    ];
  if (f) {
    stats.push({ label: 'Average final record', value: averageRecordText(f.expected_record) });
    if (playoffByes > 0) stats.push({ label: 'Bye odds', value: `${(f.bye_probability * 100).toFixed(1)}%` });
  }
  return stats.filter((x): x is { label: string; value: string } => x != null);
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
