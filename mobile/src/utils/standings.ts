// Current standings from Sleeper rosters (Home hub, flag `nav.home_hub`;
// docs/plans/home-engagement/scope.md). ZERO runtime imports, so
// tests/check-standings-order.js can transpile and execute it under plain node.
//
// SOURCE: each Sleeper roster's `settings.{wins, losses, ties, fpts,
// fpts_decimal}`. `/api/sleeper/rosters/<id>` passes Sleeper's raw rosters
// through (backend/server.py sleeper_rosters), and session init already seeds
// them into `['league-rosters', leagueId]` (state/queryClient.ts
// seedLeagueSessionCaches), so current standings cost no request. The backend
// outlook pipeline reads the same fields the same way
// (backend/outlook/league_state.py: fpts + fpts_decimal / 100).
//
// ACTUAL results, never projections: the Season-outlook "no records in weeks
// 0-5" rule (LeagueSummaryScreen.tsx header) governs PROJECTED records only
// and does not apply here.
//
// ORDER: Sleeper exposes no standings rank, so the place is COMPUTED — win %
// (a tie counts half a win), then points for, then roster_id for a stable
// order. A league's own tiebreakers or divisions may differ; every surface
// that shows a place says so. ESPN/MFL leagues have no `settings` on their
// roster rows (DB snapshot) and are out of scope for v1; callers show the
// honest "not available" state instead of calling this.

export interface SleeperRosterSettings {
  wins?: number | null;
  losses?: number | null;
  ties?: number | null;
  fpts?: number | null;
  fpts_decimal?: number | null;
}

/** Structural subset of api/sleeper.ts RosterRow plus Sleeper's `settings`. */
export interface StandingsRosterInput {
  roster_id: number;
  owner_id: string | null;
  settings?: SleeperRosterSettings | null;
}

/** Structural subset of a Sleeper league user. */
export interface StandingsUserInput {
  user_id: string;
  display_name?: string | null;
  username?: string | null;
}

export interface StandingsRow {
  rosterId: number;
  ownerId: string | null;
  name: string;
  wins: number;
  losses: number;
  ties: number;
  games: number;
  winPct: number;
  pointsFor: number;
  /** 1-based computed place; unique (ties broken by points for, then roster_id). */
  place: number;
  isYou: boolean;
}

export interface CurrentStandings {
  rows: StandingsRow[];
  teamCount: number;
  /** False before any team has played: every record is 0-0. */
  gamesPlayed: boolean;
  /** Is any roster carrying `settings` at all? False ⇒ not a Sleeper payload. */
  hasRecords: boolean;
  you: StandingsRow | null;
}

function num(v: number | null | undefined): number {
  return typeof v === 'number' && Number.isFinite(v) ? v : 0;
}

/** Points for, to 2 dp, from Sleeper's integer + hundredths split. */
export function pointsFor(s: SleeperRosterSettings | null | undefined): number {
  if (!s) return 0;
  return Math.round((num(s.fpts) + num(s.fpts_decimal) / 100) * 100) / 100;
}

/** Win percentage with a tie as half a win; 0 when no games. */
export function winPct(wins: number, losses: number, ties: number): number {
  const games = wins + losses + ties;
  return games > 0 ? (wins + ties / 2) / games : 0;
}

/** "5–1", or "5–1–1" with ties. En dash, matching the app's record copy. */
export function formatRecord(wins: number, losses: number, ties: number): string {
  const base = `${wins}–${losses}`;
  return ties > 0 ? `${base}–${ties}` : base;
}

/** Sleeper rosters + users → current standings in computed place order.
 *  `myRosterId` comes from the caller (api/sleeper.ts findMyRoster, which
 *  owns the co-owner rule); null ⇒ no row is marked as you. */
export function currentStandings(
  rosters: readonly StandingsRosterInput[],
  users: readonly StandingsUserInput[],
  myRosterId: number | null,
): CurrentStandings {
  const nameOf = new Map<string, string>();
  for (const u of users) {
    nameOf.set(u.user_id, u.display_name || u.username || u.user_id);
  }
  const unplaced = rosters.map((r) => {
    const s = r.settings ?? null;
    const wins = num(s?.wins);
    const losses = num(s?.losses);
    const ties = num(s?.ties);
    return {
      rosterId: r.roster_id,
      ownerId: r.owner_id,
      name: (r.owner_id && nameOf.get(r.owner_id)) || `Team ${r.roster_id}`,
      wins,
      losses,
      ties,
      games: wins + losses + ties,
      winPct: winPct(wins, losses, ties),
      pointsFor: pointsFor(s),
      isYou: myRosterId != null && r.roster_id === myRosterId,
    };
  });
  unplaced.sort(
    (a, b) =>
      b.winPct - a.winPct || b.pointsFor - a.pointsFor || a.rosterId - b.rosterId,
  );
  const rows: StandingsRow[] = unplaced.map((r, i) => ({ ...r, place: i + 1 }));
  return {
    rows,
    teamCount: rows.length,
    gamesPlayed: rows.some((r) => r.games > 0),
    hasRecords: rosters.some((r) => r.settings != null),
    you: rows.find((r) => r.isYou) ?? null,
  };
}

/** What Home's Standings row says. `place` is a number; format it with
 *  utils/positionSplit `ordinal` ("2nd of 12"). */
export type StandingsSummary =
  | { kind: 'record'; record: string; place: number; teamCount: number }
  | { kind: 'no_games' }
  | { kind: 'unavailable' };

export function standingsSummary(st: CurrentStandings): StandingsSummary {
  if (!st.hasRecords || !st.you) return { kind: 'unavailable' };
  if (!st.gamesPlayed) return { kind: 'no_games' };
  return {
    kind: 'record',
    record: formatRecord(st.you.wins, st.you.losses, st.you.ties),
    place: st.you.place,
    teamCount: st.teamCount,
  };
}
