// Playoff-forecast coverage copy (model v6) and the open team's Remaining
// schedule rows. Pure, zero runtime imports, so
// tests/check-league-projections.js transpiles and executes it under node.
// web/js/league-projections.js carries the same "(free agent)" lineup marker.
import type {ProjectionTeam, ProjectionWeek} from '../api/leagueProjections';

export const SCHEDULE_COPY = {
  title: 'Remaining schedule',
  week: 'Wk', opponent: 'Opponent', own: 'Proj.', opp: 'Opp.', win: 'Win %', edge: 'Edge',
  none: 'No regular-season games left.',
  freeAgent: '(free agent)', noEstimate: 'no estimate',
  empty: 'Empty slot', hypothetical: 'Hypothetical bye replacement', locked: 'Locked starter',
} as const;
const DASH = '—';
/** Projections closer than this read "Even" in the fallback column. */
export const EVEN_POINTS = 3.0;
// Sleeper slot keys too long for the 44pt slot column.
const SLOT_SHORT: Record<string, string> = {SUPER_FLEX: 'SF', IDP_FLEX: 'IDP', REC_FLEX: 'W/T', WRRB_FLEX: 'W/R'};

export const slotLabel = (slot: string) => SLOT_SHORT[slot] ?? slot;

/** A remaining week: its score is not recorded yet. */
export const remainingWeeks = (weeks: ProjectionWeek[]) => weeks.filter(w => w.actual_score_observed !== true);

/** Whole-percent win chance; never "100%" or "0%". */
export function winText(p: number): string {
  const s = (p * 100).toFixed(0);
  return s === '100' ? '>99%' : s === '0' ? '<1%' : `${s}%`;
}

/** Fallback when there is no win chance: which projection is higher. */
export function edgeText(own: number, opp: number): string {
  const d = own - opp;
  return Math.abs(d) < EVEN_POINTS ? 'Even' : d > 0 ? 'W' : 'L';
}

const finite = (n: unknown): n is number => typeof n === 'number' && Number.isFinite(n);

export interface ScheduleRow {week: number; opponent: string; own: string; opp: string; last: string}

/** The Remaining schedule table for one team. `fallback` (any remaining week
 *  without a finite win chance) turns the whole last column into Edge. */
export function scheduleRows(team: ProjectionTeam, teams: ProjectionTeam[]): {fallback: boolean; rows: ScheduleRow[]} {
  const weeks = remainingWeeks(team.weeks);
  const fallback = weeks.some(w => !finite(w.win_probability));
  const rows = weeks.map(w => {
    const opponent = teams.find(t => t.roster_id === w.opponent_roster_id);
    const oppMean = opponent?.weeks.find(x => x.week === w.week)?.modeled_score_mean;
    const ownMean = w.modeled_score_mean;
    const last = !fallback ? winText(w.win_probability)
      : finite(ownMean) && finite(oppMean) ? edgeText(ownMean, oppMean) : DASH;
    return {week: w.week, opponent: opponent?.name ?? `Team ${w.opponent_roster_id}`,
      own: finite(ownMean) ? ownMean.toFixed(1) : DASH, opp: finite(oppMean) ? oppMean.toFixed(1) : DASH, last};
  });
  return {fallback, rows};
}

type LineupRow = {slot: string; unpriced_locked_player?: {player_id: string; name?: string}; player: null | {name?: string; player_id: string; points: string; hypothetical?: boolean}};

/** One projected-lineup row as parts: slot label, name, the free-agent
 *  marker (a slot listed in `projection_coverage.free_agent_fills`) and
 *  points to one decimal ("—" when the slot has no score). */
export function lineupRowParts(row: LineupRow, index: number, fills?: {slot_index: number}[]): {slot: string; name: string; freeAgent: boolean; points: string} {
  const slot = slotLabel(row.slot);
  const p = row.player;
  if (p) {
    const points = Number(p.points);
    return {slot, name: p.hypothetical ? SCHEDULE_COPY.hypothetical : p.name || p.player_id,
      freeAgent: (fills ?? []).some(f => f.slot_index === index), points: Number.isFinite(points) ? points.toFixed(1) : DASH};
  }
  if (row.unpriced_locked_player) {
    return {slot, name: `${SCHEDULE_COPY.locked} ${row.unpriced_locked_player.name || row.unpriced_locked_player.player_id}`, freeAgent: false, points: DASH};
  }
  return {slot, name: SCHEDULE_COPY.empty, freeAgent: false, points: DASH};
}
