// Usage Trends — pure readers over the GET /api/usage-trends payload.
// ZERO runtime imports (type-only below) so tests/check-usage-trends.js can
// transpile and run this file under plain node. The server owns the math and
// the order; this file only answers "where does this player stand in a
// league", "what do we show in the list", and the plain-language headline.
import type {
  UsageLeague,
  UsageMetric,
  UsagePlayer,
  UsageSignal,
} from '../api/usageTrends';

export type LeagueStatus = 'mine' | 'rostered' | 'free_agent' | 'unknown';
export type OwnershipFilter = 'all' | 'rostered' | 'free_agents';

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
): UsagePlayer[] {
  return players
    .filter((p) => {
      if (ownership === 'all') return true;
      const s = statusIn(focus, p.player_id);
      return ownership === 'free_agents' ? s === 'free_agent' : s === 'mine' || s === 'rostered';
    })
    .sort((a, b) => a[metric].rank - b[metric].rank);
}

/** Cross-league summary for the availability button. */
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

const NOUN: Record<UsageMetric, string> = {
  snaps: 'of snaps',
  carries: 'of team carries',
  targets: 'of team targets',
};

const pct = (v: number | null | undefined) => `${Math.round(v ?? 0)}%`;

/** One plain-language line for a row — no jargon, no percentage points. */
export function headline(
  signal: UsageSignal | null,
  metric: UsageMetric,
  avgShare: number | null,
  gamesPlayed: number,
): string {
  const noun = NOUN[metric];
  const wk = signal?.week != null ? `Week ${signal.week}` : '';
  switch (signal?.kind) {
    case 'spike':
      return `Jumped to ${pct(signal.share)} ${noun} in ${wk}, up from ${pct(signal.prev_share)}`;
    case 'return': {
      const n = signal.missed ?? 0;
      const back = n > 0 ? `Back after missing ${n} ${n === 1 ? 'game' : 'games'}` : 'Back in the lineup';
      return `${back}: ${pct(signal.share)} ${noun} in ${wk}`;
    }
    case 'new':
      return `New role: ${pct(signal.share)} ${noun} in ${wk}`;
    case 'out':
      return `Didn't play in ${wk}`;
    case 'rising':
      return `Role growing: ${pct(signal.from_share)} → ${pct(signal.to_share)} ${noun}`;
    case 'falling':
      return `Role shrinking: ${pct(signal.from_share)} → ${pct(signal.to_share)} ${noun}`;
    default:
      return avgShare == null
        ? 'No usage yet'
        : `Steady: ${pct(avgShare)} ${noun} over ${gamesPlayed} ${gamesPlayed === 1 ? 'game' : 'games'}`;
  }
}

/** Short badge label for a signal (null = no badge). */
export function signalBadge(signal: UsageSignal | null): string | null {
  switch (signal?.kind) {
    case 'spike': return 'Spike';
    case 'return': return 'Back';
    case 'new': return 'New role';
    case 'rising': return 'Rising';
    case 'falling': return 'Falling';
    case 'out': return 'Out';
    default: return null;
  }
}
