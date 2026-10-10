// Usage Trends — pure readers over the GET /api/usage-trends payload.
// ZERO runtime imports (type-only below) so tests/check-usage-trends.js can
// transpile and run this file under plain node. The server owns the math and
// the order; this file only answers "where does this player stand in a
// league", "what do we show in the list", and the words and numbers on it.
import type {
  UsageLeague,
  UsageMetric,
  UsagePlayer,
  UsageSignal,
} from '../api/usageTrends';

export type LeagueStatus = 'mine' | 'rostered' | 'free_agent' | 'unknown';
export type OwnershipFilter = 'all' | 'rostered' | 'free_agents';
export type UsageView = 'simple' | 'stats';
export type UsageUnit = 'count' | 'share';
export type PositionFilter = 'ALL' | 'RB' | 'WR' | 'TE';

/** A player's status in one league. */
export function statusIn(league: UsageLeague | undefined, playerId: string): LeagueStatus {
  if (!league || !league.ok) return 'unknown';
  const owner = league.rosters[playerId];
  if (owner == null) return 'free_agent';
  return owner === league.me ? 'mine' : 'rostered';
}

/** Manager name for a rostered player in a league, or null. */
export function ownerName(league: UsageLeague | undefined, playerId: string): string | null {
  const owner = league?.rosters[playerId];
  return owner != null ? league?.owners[owner] ?? null : null;
}

/** The list for one metric + ownership filter, in the server's order.
 *  "Rostered" means on ANY roster in the focused league (the caller's own
 *  included); "Free agents" means on none. Unknown status matches only All. */
export function visiblePlayers(
  players: UsagePlayer[],
  focus: UsageLeague | undefined,
  metric: UsageMetric,
  ownership: OwnershipFilter,
  position: PositionFilter = 'ALL',
): UsagePlayer[] {
  return players
    .filter((p) => {
      if (position !== 'ALL' && p.position !== position) return false;
      if (ownership === 'all') return true;
      const s = statusIn(focus, p.player_id);
      return ownership === 'free_agents' ? s === 'free_agent' : s === 'mine' || s === 'rostered';
    })
    .sort((a, b) => a[metric].rank - b[metric].rank);
}

/** Cross-league summary for the availability control. */
export function availabilitySummary(
  leagues: UsageLeague[],
  playerId: string,
): { known: number; freeAgent: number; mine: number } {
  let known = 0;
  let freeAgent = 0;
  let mine = 0;
  for (const lg of leagues) {
    const s = statusIn(lg, playerId);
    if (s === 'unknown') continue;
    known += 1;
    if (s === 'free_agent') freeAgent += 1;
    if (s === 'mine') mine += 1;
  }
  return { known, freeAgent, mine };
}

const TEAM_NAMES: Record<string, string> = {
  ARI: 'Cardinals', ATL: 'Falcons', BAL: 'Ravens', BUF: 'Bills', CAR: 'Panthers',
  CHI: 'Bears', CIN: 'Bengals', CLE: 'Browns', DAL: 'Cowboys', DEN: 'Broncos',
  DET: 'Lions', GB: 'Packers', HOU: 'Texans', IND: 'Colts', JAX: 'Jaguars',
  KC: 'Chiefs', LAC: 'Chargers', LAR: 'Rams', LV: 'Raiders', MIA: 'Dolphins',
  MIN: 'Vikings', NE: 'Patriots', NO: 'Saints', NYG: 'Giants', NYJ: 'Jets',
  PHI: 'Eagles', PIT: 'Steelers', SEA: 'Seahawks', SF: '49ers', TB: 'Buccaneers',
  TEN: 'Titans', WAS: 'Commanders',
};

const UNIT_NOUN: Record<UsageMetric, string> = {
  snaps: 'plays',
  carries: 'carries',
  targets: 'targets',
};

const COUNT_NOUN: Record<UsageMetric, [string, string]> = {
  snaps: ['snap', 'snaps'],
  carries: ['carry', 'carries'],
  targets: ['target', 'targets'],
};

/** "of Eagles plays" / "of Jets carries" — falls back to the abbreviation. */
export function ofTeam(team: string, metric: UsageMetric): string {
  return `of ${TEAM_NAMES[team] ?? team} ${UNIT_NOUN[metric]}`;
}

const pct = (v: number | null | undefined) => `${Math.round(v ?? 0)}%`;

/** "90% of Eagles plays" (share) or "55 snaps" (count). */
function amount(share: number | null | undefined, count: number | null | undefined,
                team: string, metric: UsageMetric, unit: UsageUnit): string {
  if (unit === 'count') {
    const n = Math.round(count ?? 0);
    return `${n} ${COUNT_NOUN[metric][n === 1 ? 0 : 1]}`;
  }
  return `${pct(share)} ${ofTeam(team, metric)}`;
}

/** The last played week's index, or -1. */
function lastPlayed(status: string[]): number {
  for (let i = status.length - 1; i >= 0; i--) if (status[i] === 'played') return i;
  return -1;
}

/** The one plain-language line on a card (Version A). No jargon, no
 *  percentage points; a jump in the newest week drops its week number. */
export function headline(
  player: Pick<UsagePlayer, 'team' | 'status'>,
  metric: UsageMetric,
  block: { counts: (number | null)[]; shares: (number | null)[]; avg: number | null;
           avg_share: number | null; signal: UsageSignal | null },
  latestWeek: number | null,
  unit: UsageUnit = 'share',
): string {
  const { signal } = block;
  const team = player.team;
  const inWeek = signal?.week != null && signal.week !== latestWeek ? ` in Week ${signal.week}` : '';
  const last = lastPlayed(player.status);
  switch (signal?.kind) {
    case 'spike':
      return `Jumped to ${amount(signal.share, signal.count, team, metric, unit)}${inWeek}`;
    case 'return':
      return `Back in the lineup: ${amount(signal.share, signal.count, team, metric, unit)}`;
    case 'new':
      return `New role: ${amount(signal.share, signal.count, team, metric, unit)}${inWeek}`;
    case 'out':
      return `Didn't play in Week ${signal.week}`;
    case 'rising':
      return `Up to ${amount(signal.to_share, last >= 0 ? block.counts[last] : null, team, metric, unit)}`;
    case 'falling':
      return `Down to ${amount(signal.to_share, last >= 0 ? block.counts[last] : null, team, metric, unit)}`;
    default:
      if (block.avg_share == null) return 'No usage yet';
      return unit === 'count'
        ? `Steady at about ${amount(null, block.avg, team, metric, unit)} a game`
        : `Steady at ${amount(block.avg_share, null, team, metric, unit)}`;
  }
}

/** True when the signal is news in the given week (the flare-highlighted week). */
export function isNewsWeek(signal: UsageSignal | null, week: number): boolean {
  return !!signal && signal.week === week
    && (signal.kind === 'spike' || signal.kind === 'return' || signal.kind === 'new');
}

/** Version A's two sections: news in the newest week first, then the rest.
 *  The split point follows the server's order (those players rank first). */
export function newsCount(
  visible: UsagePlayer[], metric: UsageMetric, latestWeek: number | null,
): number {
  let n = 0;
  for (const p of visible) {
    if (latestWeek != null && isNewsWeek(p[metric].signal, latestWeek)) n += 1;
    else break;
  }
  return n;
}

/** A stats-table cell for one week. */
export function weekCell(
  player: Pick<UsagePlayer, 'status'>,
  block: { counts: (number | null)[]; shares: (number | null)[] },
  i: number,
  unit: UsageUnit,
): string {
  const st = player.status[i];
  if (st === 'out') return 'OUT';
  if (st === 'bye') return 'BYE';
  const v = unit === 'count' ? block.counts[i] : block.shares[i];
  if (v == null) return '–';
  return unit === 'count' ? String(v) : pct(v);
}

/** The stats table's right-hand column: the window TOTAL for counts (the
 *  snap-count sheet's "total"), the played-weeks average for % of team
 *  (a sum of percentages means nothing). */
export function lastColumn(
  block: { counts: (number | null)[]; avg_share: number | null },
  unit: UsageUnit,
): string {
  if (unit === 'share') return block.avg_share == null ? '–' : pct(block.avg_share);
  return String(block.counts.reduce<number>((t, c) => t + (c ?? 0), 0));
}

/** "D. Cooper" for the dense table; single-word names pass through. */
export function shortName(name: string): string {
  const parts = name.trim().split(/\s+/);
  if (parts.length < 2) return name;
  return `${parts[0][0]}. ${parts.slice(1).join(' ')}`;
}

/** Availability control label: pips stop working past five leagues. */
export function availabilityLabel(summary: { known: number; freeAgent: number }): string {
  return summary.known > 5
    ? `FA in ${summary.freeAgent} of ${summary.known}`
    : `FA ${summary.freeAgent}/${summary.known}`;
}

/** "12-Team Dynasty" from what the league list carries; null when unknown. */
export function leagueFormatLine(lg: { total_rosters?: number; settings_type?: number } | undefined): string | null {
  if (!lg) return null;
  const kind = lg.settings_type === 2 ? 'Dynasty' : lg.settings_type === 1 ? 'Keeper'
    : lg.settings_type === 0 ? 'Redraft' : null;
  const size = lg.total_rosters ? `${lg.total_rosters}-Team` : null;
  const line = [size, kind].filter(Boolean).join(' ');
  return line || null;
}
