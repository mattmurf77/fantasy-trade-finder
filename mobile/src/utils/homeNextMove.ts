// Home's next move — the row's pure decisions (flag `league.next_move`;
// scope docs/plans/home-next-move/scope.md, D-278).
//
// THE SERVER DECIDES. Which direction, which player, buy or sell, and every
// figure arrive in the forecast read's `next_move` block; nothing here ranks,
// classifies or computes. This module only decides whether to honour the
// block (flag, version, shape), makes the ONE check the server cannot make —
// the live roster, exactly as the lists make it (utils/maxPfMoves
// `rosterChanged`, utils/playoffTargets `liveSeller`) — words the line with
// the lists' formatters, and runs the tap through the list row's own
// "Find trades" hand-off (same pins, same event, same destination).
// No React, no I/O; tests/check-home-next-move.js transpiles and executes it.
import type { MaxPfMoveRow, NextMove, PlayoffTargetRow, ProjectionView } from '../api/leagueProjections';
import { NEXT_MOVE_COPY as C } from './homeNextMoveCopy';
import { fill, formatPct, handOffToFinder as sellHandOff } from './maxPfMoves';
import { handOffToFinder as buyHandOff, liveSeller, type LiveRoster } from './playoffTargets';
import { playoffOddsText } from './playoffOdds';

export const NEXT_MOVE_FLAG = 'league.next_move';
export const NEXT_MOVE_VERSION = 1;
/** `home_tile_tapped.tile` for the row (taxonomy: backend/analytics_taxonomy.py). */
export const NEXT_MOVE_TILE = 'next_move' as const;
/** The screen the hand-off's `finder_target_pinned` is logged under. */
export const SCREEN = 'Home';

export interface NextMoveView {
  action: 'buy' | 'sell';
  label: string;
  line: string;
  actionLabel: string;
  accessibilityLabel: string;
  move: NextMove;
  /** Buy: the live owner of the player's team (the canvas partner). Sell: null. */
  opponentId: string | null;
}

const isStr = (v: unknown): v is string => typeof v === 'string' && v.length > 0;
const isProb = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v) && v >= 0 && v <= 1;

/** A version-1 `ready` block in the shape this build knows, or null. */
export function honouredBlock(data: ProjectionView | undefined, flagOn: boolean): NextMove | null {
  const b = data?.next_move;
  if (!flagOn || !b || typeof b !== 'object' || b.version !== NEXT_MOVE_VERSION || b.state !== 'ready') return null;
  if (b.action !== 'buy' && b.action !== 'sell') return null;
  const p = b.player;
  if (!p || !isStr(p.player_id) || !isStr(p.name) || !isStr(p.short_name) || !isStr(p.position)) return null;
  if (!b.playoff_probability || !isProb(b.playoff_probability.now) || !isProb(b.playoff_probability.after)) return null;
  if (b.action === 'sell' && !Array.isArray(b.roster_player_ids)) return null;
  if (b.action === 'buy' && (!b.seller || typeof b.seller.roster_id !== 'number' || !isStr(b.seller.name))) return null;
  return b;
}

/** Max PF moves' roster check (utils/maxPfMoves `rosterChanged`), made
 *  strict: the live roster must be loaded and the same set of players as the
 *  forecast's. Any change hides the sell, since the list then flags its
 *  figures as out of date. */
export function sellRosterHolds(move: NextMove, liveIds: string[] | null | undefined): boolean {
  if (!liveIds || !move.roster_player_ids || !move.player) return false;
  const live = new Set(liveIds);
  const saved = new Set(move.roster_player_ids);
  if (live.size !== saved.size) return false;
  for (const id of live) if (!saved.has(id)) return false;
  return live.has(move.player.player_id);
}

/** Playoff targets' check (utils/playoffTargets `liveSeller`): the player is
 *  still on that team's live roster, and the team has a live owner to trade
 *  with (the list row has no Find trades button without one). */
export function buyOpponent(move: NextMove, rosters: LiveRoster[] | null | undefined): string | null {
  if (!rosters || !move.player || !move.seller) return null;
  const row = { player_id: move.player.player_id, seller: { roster_id: move.seller.roster_id } } as PlayoffTargetRow;
  return liveSeller(row, rosters)?.owner_id || null;
}

const proofOf = (move: NextMove) => move.playoff_proof ?? null;
const playoff = (p: number, move: NextMove) => playoffOddsText(p, proofOf(move), 1);

/** The one line. A sell names the projected pick when it moves, else the
 *  top-3 pick chance when that moves, else the playoff chance. */
export function moveLine(move: NextMove): string {
  const p = move.player!;
  const base = { short_name: p.short_name, position: p.position };
  const chance = move.playoff_probability!;
  if (move.action === 'buy') {
    return fill(C['NM-BUY'], { ...base, team: move.seller!.name,
      now: playoff(chance.now, move), after: playoff(chance.after, move) });
  }
  const pick = move.pick;
  if (pick && isStr(pick.now) && isStr(pick.after) && pick.now !== pick.after) {
    return fill(C['NM-SELL.pick'], { ...base, now: pick.now, after: pick.after });
  }
  const top3 = move.top3_probability;
  if (top3 && isProb(top3.now) && isProb(top3.after) && formatPct(top3.now) !== formatPct(top3.after)) {
    return fill(C['NM-SELL.top3'], { ...base, now: formatPct(top3.now), after: formatPct(top3.after) });
  }
  return fill(C['NM-SELL.playoff'], { ...base, now: playoff(chance.now, move), after: playoff(chance.after, move) });
}

/**
 * The row, or null for nothing at all (no placeholder, no error text):
 * flag off, no block or a `none` block, an unknown version or shape, the
 * live rosters not loaded, or the move failing the live-roster check.
 *
 * rosters  the shared ['league-rosters', leagueId] query's data
 * liveIds  the viewer's own live roster (`findMyRoster(rosters, userId)?.players`)
 */
export function nextMoveView(
  data: ProjectionView | undefined,
  flagOn: boolean,
  rosters: LiveRoster[] | null | undefined,
  liveIds: string[] | null | undefined,
): NextMoveView | null {
  const move = honouredBlock(data, flagOn);
  if (!move) return null;
  let opponentId: string | null = null;
  if (move.action === 'sell') {
    if (!sellRosterHolds(move, liveIds)) return null;
  } else {
    opponentId = buyOpponent(move, rosters);
    if (!opponentId) return null;
  }
  const line = moveLine(move);
  return {
    action: move.action!, label: C['NM-LABEL'], line, actionLabel: C['NM-ACTION'],
    accessibilityLabel: fill(C['NM-A11Y'], { line, short_name: move.player!.short_name }),
    move, opponentId,
  };
}

// ── The tap: the list row's own "Find trades" ──────────────────────────
/** Find a Trade's route params, as the two lists' `finderNavParams` build them. */
export interface FinderNav { screen: string; params: unknown }
export interface TapDeps {
  setSide: (side: 'give' | 'receive', players: { id: string; name: string; position: string }[]) => void;
  track: (event: string, props: Record<string, unknown>, screen: string) => void;
  navigate: (params: FinderNav) => void;
  now: () => number;
}
/** Runs the row's hand-off: a sell pins the player on the give side
 *  (utils/maxPfMoves), a buy on the receive side with his team as the
 *  partner (utils/playoffTargets); each logs `finder_target_pinned` under
 *  Home and opens Find a Trade with the player on the canvas. */
export function nextMoveTap(view: NextMoveView, deps: TapDeps): boolean {
  const p = view.move.player!;
  const handOff = { ...deps, screen: SCREEN };
  if (view.action === 'sell') {
    return sellHandOff({ keep: false, player_id: p.player_id, name: p.name, position: p.position } as MaxPfMoveRow, handOff);
  }
  return buyHandOff({ player_id: p.player_id, name: p.name, position: p.position } as PlayoffTargetRow,
    view.opponentId, handOff);
}
