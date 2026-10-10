// Position split (Home hub, flag `nav.home_hub`; docs/plans/home-engagement/scope.md).
//
// The buyers/sellers arithmetic League Summary draws under ONE core-position
// filter (#300), as a pure module so Home can say "you're 2nd at RB · Seller"
// with the SAME numbers the user then sees on League rankings. ZERO runtime
// imports (type-only imports erase), so tests/check-position-split-parity.js
// can transpile and execute it under plain node.
//
// THIS IS A DELIBERATE DUPLICATE (scope.md W4, operator-approved). The
// originals stay inline in LeagueSummaryScreen.tsx because
// tests/check-league-candidates-300.js pins their source text. The parity
// guard extracts those inline expressions, runs them beside this module over
// randomised leagues, and fails on any divergence. Change one, change both.
//
// Mirrors, line for line:
//   ordering  LeagueSummaryScreen.tsx `ranked`  — value desc, user_id asc
//   value     computeSubset('all')              — positions[P].value ?? 0
//   cut       `cutAfter`                        — count(value >= median), null at 0 or n
//   band size `bandSize`                        — cutAfter == null ? 0 : round(n * 0.33)
//   band      `bandFor`                         — top bandSize Seller, bottom bandSize Buyer
//   gate      `n5ContentGatesPass`              — >= 3 teams and a median at >= 1 core position

export type SplitPos = 'QB' | 'RB' | 'WR' | 'TE';
export const SPLIT_POSITIONS: readonly SplitPos[] = ['QB', 'RB', 'WR', 'TE'];

export type Band = 'Seller' | 'Buyer';
export type SplitSide = 'buy' | 'sell';

/** Fewer valued rosters than this ⇒ no buyers and sellers to split (N5 gate). */
export const MIN_SPLIT_TEAMS = 3;

/** Structural subset of api/league.ts PowerRankedTeam — only what the split reads. */
export interface SplitTeamInput {
  user_id: string;
  username?: string;
  display_name?: string;
  is_you: boolean;
  positions?: Partial<Record<SplitPos, { value: number; value_label?: string }>>;
}

/** Structural subset of api/league.ts PowerRankingsResponse. */
export interface SplitPayloadInput {
  teams: readonly SplitTeamInput[];
  medians?: Partial<Record<SplitPos, { value: number; value_label?: string }>>;
}

export interface SplitRow {
  userId: string;
  name: string;
  value: number;
  valueLabel?: string;
  isYou: boolean;
  /** 1-based on-screen rank under this position's ordering. */
  rank: number;
  band: Band | null;
  /** Side of the median line; null when no line is drawn. */
  aboveLine: boolean | null;
}

/** Same three outcomes the #300 exposure event reports as `divider`. */
export type SplitState = 'shown' | 'no_median' | 'no_split';

export interface PositionSplit {
  position: SplitPos;
  state: SplitState;
  teamCount: number;
  median: { value: number; valueLabel?: string } | null;
  /** Rows above the line; null = no line (no median, or every team on one side). */
  cutAfter: number | null;
  bandSize: number;
  rows: SplitRow[];
  you: SplitRow | null;
}

/** LeagueSummaryScreen TeamRow's display name rule. */
export function teamName(t: SplitTeamInput): string {
  return t.display_name || t.username || t.user_id;
}

/** computeSubset(team, 'all').posValues[pos]. */
export function positionValue(t: SplitTeamInput, pos: SplitPos): number {
  return t.positions?.[pos]?.value ?? 0;
}

/** LeagueSummaryScreen `ranked` under a single core-position filter. */
export function rankByPosition<T extends SplitTeamInput>(teams: readonly T[], pos: SplitPos): T[] {
  const rows = teams.map((team) => ({ team, active: positionValue(team, pos) }));
  rows.sort((a, b) => b.active - a.active || (a.team.user_id < b.team.user_id ? -1 : 1));
  return rows.map((r) => r.team);
}

/** LeagueSummaryScreen `cutAfter`: rows above the line, or null when the
 *  line would sit above rank 1 or below rank N. */
export function cutAfterFor(values: readonly number[], median: number): number | null {
  let n = 0;
  for (const v of values) {
    if (v >= median) n += 1;
  }
  return n > 0 && n < values.length ? n : null;
}

/** LeagueSummaryScreen `bandSize`. */
export function bandSizeFor(teamCount: number, cutAfter: number | null): number {
  return cutAfter == null ? 0 : Math.round(teamCount * 0.33);
}

/** LeagueSummaryScreen `bandFor`. Labels only: the LINE is the direction rule. */
export function bandAt(idx: number, teamCount: number, bandSize: number): Band | null {
  if (bandSize <= 0 || bandSize * 2 > teamCount) return null;
  if (idx < bandSize) return 'Seller';
  if (idx >= teamCount - bandSize) return 'Buyer';
  return null;
}

/** The whole split for one position, exactly as League rankings draws it. */
export function positionSplit(payload: SplitPayloadInput, pos: SplitPos): PositionSplit {
  const ranked = rankByPosition(payload.teams, pos);
  const teamCount = ranked.length;
  const m = payload.medians?.[pos] ?? null;
  const median = m ? { value: m.value, valueLabel: m.value_label } : null;
  const cutAfter = median ? cutAfterFor(ranked.map((t) => positionValue(t, pos)), median.value) : null;
  const bandSize = bandSizeFor(teamCount, cutAfter);
  const rows: SplitRow[] = ranked.map((t, idx) => ({
    userId: t.user_id,
    name: teamName(t),
    value: positionValue(t, pos),
    valueLabel: t.positions?.[pos]?.value_label,
    isYou: t.is_you,
    rank: idx + 1,
    band: bandAt(idx, teamCount, bandSize),
    aboveLine: cutAfter == null ? null : idx < cutAfter,
  }));
  const state: SplitState = !median ? 'no_median' : cutAfter == null ? 'no_split' : 'shown';
  return {
    position: pos,
    state,
    teamCount,
    median,
    cutAfter,
    bandSize,
    rows,
    you: rows.find((r) => r.isYou) ?? null,
  };
}

/** All four positions, in QB/RB/WR/TE order. */
export function positionSplits(payload: SplitPayloadInput): PositionSplit[] {
  return SPLIT_POSITIONS.map((p) => positionSplit(payload, p));
}

/** LeagueSummaryScreen `n5ContentGatesPass` minus the flag and fetch clauses. */
export function canSplit(payload: SplitPayloadInput): boolean {
  return (
    payload.teams.length >= MIN_SPLIT_TEAMS &&
    SPLIT_POSITIONS.some((p) => payload.medians?.[p] != null)
  );
}

/** The Buy/Sell side the user's band implies (Home's ice emphasis). Changes no behaviour. */
export function suggestedSide(band: Band | null): SplitSide | null {
  if (band === 'Seller') return 'sell';
  if (band === 'Buyer') return 'buy';
  return null;
}

/** Meter fill for a rank: 1st of 12 ⇒ 1, 12th of 12 ⇒ 1/12. */
export function rankPercentile(rank: number, teamCount: number): number {
  if (teamCount <= 0 || rank <= 0) return 0;
  return Math.max(0, Math.min(1, (teamCount - rank + 1) / teamCount));
}

/** 1st, 2nd, 3rd, 4th … 11th, 12th, 13th … 21st (LeagueSummaryScreen's ordinal). */
export function ordinal(n: number): string {
  const mod100 = n % 100;
  if (mod100 >= 11 && mod100 <= 13) return `${n}th`;
  switch (n % 10) {
    case 1:
      return `${n}st`;
    case 2:
      return `${n}nd`;
    case 3:
      return `${n}rd`;
    default:
      return `${n}th`;
  }
}
