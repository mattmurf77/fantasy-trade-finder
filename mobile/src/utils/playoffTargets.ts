// Playoff targets — the section's pure decisions (flag
// `league.playoff_targets`; contract:
// docs/plans/league-projections/playoff-targets/contract.md). The mirror of
// Max PF moves (utils/maxPfMoves.ts), whose formatting helpers it reuses.
// The app reads every number from the server's `playoff_targets` block and
// never re-computes one: which teams are selling is decided on the server
// (contract §2), never here. This module only decides what shows (§7),
// formats (§11) and fills the copy (§10, utils/playoffTargetsCopy.ts).
// No React, no I/O; tests/check-playoff-targets.js transpiles and executes it.
import type {
  PlayoffTargets, PlayoffTargetRow, PlayoffTargetsState, PlayoffTargetReplaced,
} from '../api/leagueProjections';
import { TARGETS_COPY as C } from './playoffTargetsCopy';
import { fill, formatPoints, DEFAULT_OPEN_MAX_PLAYOFF } from './maxPfMoves';
import { playoffOddsText } from './playoffOdds';

export const TARGETS_VERSION = 1;
export const ROWS_BEFORE_SHOW_ALL = 5;
export const SCREEN = 'Standings';

const KNOWN_STATES: readonly PlayoffTargetsState[] = [
  'unavailable', 'season_over', 'after_trade_deadline', 'clinched', 'eliminated', 'near_certain',
  'no_sellers', 'no_targets', 'ready',
];
const KNOWN_REASONS = [
  'no_forecast', 'update_pending', 'refresh_failed', 'stale', 'old_model', 'incomplete', 'team_not_found',
  'unsupported', 'missing_projections', 'read_failed', 'not_computed',
];

// ── Analytics (contract §9) ─────────────────────────────────────────────
export const TARGETS_EVENTS = {
  viewed: 'playoff_targets_viewed',
  expanded: 'playoff_target_expanded',
  pinned: 'finder_target_pinned',
} as const;

/** A live Sleeper roster, as the page's ['league-rosters', leagueId] query returns it. */
export interface LiveRoster {
  roster_id: number;
  owner_id: string | null;
  players: string[] | null;
}

// ── Mount rule (contract §7, §8) ────────────────────────────────────────
export interface MountInputs {
  block: PlayoffTargets | null | undefined;
  flagOn: boolean;
  isSleeper: boolean;
  /** `team.roster_id === result.viewer_roster_id`. */
  ownCard: boolean;
}
export function sectionMounts({ block, flagOn, isSleeper, ownCard }: MountInputs): boolean {
  return !!block && flagOn && isSleeper && ownCard && block.version === TARGETS_VERSION
    && KNOWN_STATES.includes(block.state);
}

// ── Derived state (contract §7) ─────────────────────────────────────────
const isListState = (s: PlayoffTargetsState) => s === 'ready' || s === 'no_targets';

/** §7.1: the complement of Max PF moves' default-open rule, so on a card
 *  with both sections one starts open and the other closed. */
export function startsOpen(block: PlayoffTargets): boolean {
  const p = block.baseline?.playoff_probability;
  return isListState(block.state) && p != null && p > DEFAULT_OPEN_MAX_PLAYOFF
    && block.saved_outlook !== 'rebuilder' && block.saved_outlook !== 'jets';
}
/** The live roster the row's player is on: the roster when he is still
 *  there, null when he has left it (or the roster is gone), undefined when
 *  the live rosters have not loaded (no check, §7.2). */
export function liveSeller(row: PlayoffTargetRow, rosters: LiveRoster[] | null | undefined): LiveRoster | null | undefined {
  if (!rosters) return undefined;
  const roster = rosters.find((r) => r.roster_id === row.seller.roster_id);
  return roster && (roster.players ?? []).includes(row.player_id) ? roster : null;
}
/** Every served row in rank order (§7.3), minus players no longer on their
 *  team's live roster (§7.2). */
export function listedRows(block: PlayoffTargets, rosters: LiveRoster[] | null | undefined) {
  if (!isListState(block.state)) return { rows: [] as PlayoffTargetRow[], dropped: 0 };
  const sorted = [...block.rows].sort((a, b) => a.rank - b.rank);
  const rows = sorted.filter((r) => liveSeller(r, rosters) !== null);
  return { rows, dropped: sorted.length - rows.length };
}
export function visibleRows(listed: PlayoffTargetRow[], showAll: boolean) {
  return {
    rows: showAll ? listed : listed.slice(0, ROWS_BEFORE_SHOW_ALL),
    showAllButton: !showAll && listed.length > ROWS_BEFORE_SHOW_ALL,
  };
}

// ── Lines ───────────────────────────────────────────────────────────────
/** The viewer's playoff chance: whole percent under the D-262 rule. */
const mine = (p: number, block: PlayoffTargets) => playoffOddsText(p, block.baseline, 1);

export function unavailableLine(reason: string | null): string {
  const key = `C-U-${reason}` as keyof typeof C;
  return reason && KNOWN_REASONS.includes(reason) && key in C ? C[key] : C['C-U-other'];
}
/** The one line a non-list state shows; null for ready / no_targets. */
export function stateLine(block: PlayoffTargets): string | null {
  switch (block.state) {
    case 'unavailable': return unavailableLine(block.reason);
    case 'season_over': return C['C-SEASON-OVER'];
    case 'after_trade_deadline': return C['C-DEADLINE'];
    case 'clinched': return C['C-CLINCHED'];
    case 'eliminated': return C['C-ELIMINATED'];
    case 'near_certain':
      return fill(C['C-NEAR-CERTAIN'], { playoff: mine(block.baseline?.playoff_probability ?? 1, block) });
    case 'no_sellers': return C['C-NO-SELLERS'];
    default: return null;
  }
}
export function baselineLine(block: PlayoffTargets): string | null {
  const b = block.baseline;
  if (!b || !isListState(block.state)) return null;
  return fill(C['C-BASE'], { playoff: mine(b.playoff_probability, block) });
}
export function headLine(block: PlayoffTargets): string | null {
  const n = block.baseline?.weeks_remaining;
  if (n == null) return null;
  if (n === 1) return C['C-HEAD'].replace('over the remaining {n} weeks', C['C-HEAD.final']);
  return fill(C['C-HEAD'], { n });
}

// ── Rows (contract §10 C-ROW-*, C-OPEN-*, C-REPL-*) ─────────────────────
export function rowLine1Parts(row: PlayoffTargetRow) {
  return { name: row.short_name, position: row.position, gain: formatPoints(row.lineup_gain) };
}
export function rowLine1(row: PlayoffTargetRow): string {
  const p = rowLine1Parts(row);
  return fill(C['C-ROW-1'], { short_name: p.name, position: p.position, lineup_gain: p.gain });
}
/** "Playoff chance 62% → 71%": the viewer's chance, read from the row. */
export function rowLine2(row: PlayoffTargetRow, block: PlayoffTargets): string {
  return fill(C['C-ROW-2'], {
    now: mine(row.playoff_probability.now, block), after: mine(row.playoff_probability.after, block),
  });
}
/** The team he is on and its playoff chance in this forecast (its own proof). */
export function rowLine3(row: PlayoffTargetRow): string {
  return fill(C['C-ROW-3'], {
    team: row.seller.name, playoff: playoffOddsText(row.seller.playoff_probability, row.seller, 1),
  });
}
const weeksText = (w: number) => (w === 1 ? C['C-REPL-N.one'] : `${w} weeks`);
const replacedName = (r: PlayoffTargetReplaced) => (r.free_agent ? fill(C['C-REPL-FA'], { name: r.name ?? '' }) : r.name ?? '');

/** Who he starts over. Entries with no player (an open slot) are `openSpotLine`'s. */
export function replacesLine(row: PlayoffTargetRow): string | null {
  const reps = row.replaces.filter((r) => r.player_id != null);
  if (reps.length === 0) return null;
  if (reps.length === 1 && row.replaces.length === 1 && row.replaces_more === 0 && reps[0].weeks === row.weeks_affected) {
    return fill(C['C-REPL-1'], { name: replacedName(reps[0]) });
  }
  const tmpl = C['C-REPL-N'];
  const cut = tmpl.indexOf(', ');
  const head = tmpl.slice(0, cut);              // "Starts over {name1} ({w1} weeks)"
  const tail = tmpl.slice(cut + 2, -1);         // "{name2} ({w2} weeks)"
  const parts = reps.map((r, i) => (i === 0
    ? head.replace('{w1} weeks', weeksText(r.weeks)).replace('{name1}', () => replacedName(r))
    : tail.replace('{w2} weeks', weeksText(r.weeks)).replace('{name2}', () => replacedName(r))));
  const body = parts.join(', ');
  return row.replaces_more > 0 ? body + fill(C['C-REPL-N.more'], { k: row.replaces_more }) : `${body}.`;
}
export function openSpotLine(row: PlayoffTargetRow): string | null {
  const weeks = row.replaces.filter((r) => r.player_id == null).reduce((n, r) => n + r.weeks, 0);
  return weeks > 0 ? C['C-OPEN-SPOT'].replace('{w} weeks', weeksText(weeks)) : null;
}
export function weeksLine(row: PlayoffTargetRow, block: PlayoffTargets): string | null {
  const n = block.baseline?.weeks_remaining;
  if (n == null) return null;
  return n === 1 ? C['C-OPEN-WEEKS.final'] : fill(C['C-OPEN-WEEKS'], { k: row.weeks_affected, n });
}
export interface RowDetail {
  weeks: string | null;
  replaces: string | null;
  openSpot: string | null;
  /** Find trades button label; null when his team's owner cannot be resolved (§12). */
  button: string | null;
}
export function rowDetail(row: PlayoffTargetRow, block: PlayoffTargets, opponentId: string | null): RowDetail {
  return {
    weeks: weeksLine(row, block),
    replaces: replacesLine(row),
    openSpot: openSpotLine(row),
    button: opponentId ? fill(C['C-BUTTON'], { short_name: row.short_name }) : null,
  };
}

// ── The whole section ───────────────────────────────────────────────────
export interface SectionModel {
  state: PlayoffTargetsState;
  isList: boolean;
  line: string | null;
  initialOpen: boolean;
  baseline: string | null;
  head: string | null;
  changedLine: string | null;
  rosterLine: string | null;
  listed: PlayoffTargetRow[];
  /** rank → the live owner of the row's team (the canvas partner), or null. */
  opponents: Record<number, string | null>;
  noneAloneLine: string | null;
  noTargetsLine: string | null;
  foot: string | null;
  eligible: string | null;
}
export function deriveSection(block: PlayoffTargets, rosters: LiveRoster[] | null | undefined): SectionModel {
  const list = isListState(block.state);
  const { rows: listed, dropped } = listedRows(block, rosters);
  const opponents: Record<number, string | null> = {};
  for (const row of listed) opponents[row.rank] = liveSeller(row, rosters)?.owner_id || null;
  return {
    state: block.state,
    isList: list,
    line: stateLine(block),
    initialOpen: startsOpen(block),
    baseline: baselineLine(block),
    head: listed.length > 0 ? headLine(block) : null,
    changedLine: list && block.sellers_changed ? C['C-CHANGED'] : null,
    rosterLine: dropped > 0 ? C['C-ROSTER'] : null,
    listed,
    opponents,
    noneAloneLine: listed.length > 0 && !listed.some((r) => r.passes_threshold) ? C['C-NONE-ALONE'] : null,
    // No rows served ⇒ C-NO-TARGETS; every row dropped by the roster check ⇒ C-ROSTER only.
    noTargetsLine: list && listed.length === 0 && dropped === 0 ? C['C-NO-TARGETS'] : null,
    foot: listed.length > 0 ? C['C-FOOT'] : null,
    eligible: list ? C['C-ELIGIBLE'] : null,
  };
}

// ── Event properties (contract §9; never a player id or name) ───────────
export function viewedProps(block: PlayoffTargets, model: SectionModel) {
  return {
    state: block.state,
    n_listed: model.listed.length,
    any_pass: model.listed.some((r) => r.passes_threshold),
    n_sellers: block.eligible_teams,
    band: block.baseline?.playoff_band ?? 'none',
  };
}
export const expandedProps = (row: PlayoffTargetRow) => ({ position: row.position, rank: row.rank });
export const PINNED_PROPS = { side: 'receive', source: 'playoff_targets' } as const;

// ── The Find trades hand-off (contract §12) ─────────────────────────────
/** The params for `navigation.popTo('Main', …)`: Trades tab → TradesHome,
 *  with the existing `canvasPrefill` route param (the MatchesScreen bridge,
 *  consumed once, keyed on `canvasPrefillSeq`): the player on the RECEIVE
 *  side and his team as the canvas partner. `pop: true` as Max PF moves
 *  (G-056). No auto-run. */
export function finderNavParams(row: PlayoffTargetRow, opponentId: string, seq: number) {
  return {
    screen: 'Trades',
    params: {
      screen: 'TradesHome',
      params: { canvasPrefill: { opponentId, give: [] as string[], receive: [row.player_id] }, canvasPrefillSeq: seq },
      pop: true,
    },
  };
}
export interface HandOffDeps {
  setSide: (side: 'give' | 'receive', players: { id: string; name: string; position: string }[]) => void;
  track: (event: string, props: Record<string, unknown>, screen: string) => void;
  navigate: (params: ReturnType<typeof finderNavParams>) => void;
  now: () => number;
  /** The screen the event is logged under: an Improve page's route name on
   *  the page (direction-pages spec §9); Standings when absent. */
  screen?: string;
}
/** Pins the row's player on the receive side, clears give, logs, then opens
 *  Find a Trade with him prefilled on the canvas against his team. Does
 *  nothing without that team's owner. */
export function handOffToFinder(row: PlayoffTargetRow, opponentId: string | null, deps: HandOffDeps): boolean {
  if (!opponentId) return false;
  deps.setSide('receive', [{ id: row.player_id, name: row.name, position: row.position }]);
  deps.setSide('give', []);
  deps.track(TARGETS_EVENTS.pinned, { ...PINNED_PROPS }, deps.screen ?? SCREEN);
  deps.navigate(finderNavParams(row, opponentId, deps.now()));
  return true;
}
