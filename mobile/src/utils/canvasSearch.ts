import { track } from '../api/events';
import type { CalcPlayer } from '../data/calcTypes';

// ── The canvas fork (D-153), owned in ONE place (D-158, Wave B0) ─────────
//
// "Find a Trade" on the merged calculator canvas forks on what the canvas
// holds: a give side is a fairness question about THAT package (the
// synchronous /api/trades/fair-packages sweep), an empty canvas is the
// model's question (the ordinary generate). A canvas holding only RECEIVE
// assets counts as EMPTY — the fair sweep prices a give side and there is
// nothing to price.
//
// Why this is a module and not a screen-local helper: as of D-158 the canvas
// has TWO hosts. `TradeCalculatorScreen` mounts it on the pushed page (flag
// `calc.inline_home` OFF) and hands off to the deck; `TradesScreen` mounts it
// inline on the guided landing (flag ON) and consumes it in place, without
// navigating. Both must reach the same verdict and report the same
// `calc_find_a_trade_tapped` row, so the decision and its analytics live here
// and each host calls this once. Duplicating it would let the two entry
// points price the same canvas differently — the exact class of drift D-153
// removed from the server side by sharing `eval_consensus_package`.
//
// NO NEW EVENT: `calc_find_a_trade_tapped` and its four registered props are
// unchanged; only the `screen` label differs between the hosts, which is why
// it is a parameter rather than a constant.

export interface CanvasSearchFork {
  /** The D-153 verdict, and the value reported as `path`. */
  path: 'fair' | 'model';
  giveIds: string[];
  receiveIds: string[];
  /** The canvas's Team-dropdown partner, passed straight through so callers
   *  scope the run without re-reading the component's state. */
  opponent: { userId: string; name: string } | null;
  /** The fair sweep's anchor — the give/receive ids, but only on the `fair`
   *  path. `null` on `model`, so a caller cannot accidentally anchor an
   *  empty canvas. */
  anchor: { giveIds: string[]; receiveIds: string[] } | null;
}

export function forkCanvasSearch(
  opts: {
    give: CalcPlayer[];
    receive: CalcPlayer[];
    opponent: { userId: string; name: string } | null;
  },
  screen: string,
): CanvasSearchFork {
  const giveIds = opts.give.map((p) => p.id);
  const receiveIds = opts.receive.map((p) => p.id);
  const fair = giveIds.length > 0;
  track(
    'calc_find_a_trade_tapped',
    {
      path: fair ? 'fair' : 'model',
      give_count: opts.give.length,
      receive_count: opts.receive.length,
      has_partner: !!opts.opponent,
    },
    screen,
  );
  return {
    path: fair ? 'fair' : 'model',
    giveIds,
    receiveIds,
    opponent: opts.opponent,
    anchor: fair ? { giveIds, receiveIds } : null,
  };
}

/** The filter receipt's headline assets (D-158): "Built around: <first> +N".
 *  Give side only — that is what the sweep anchors on; the receive side is a
 *  ranking preference, not a filter (D-153), so naming it here would claim a
 *  constraint the server does not apply. Returns null when there is nothing
 *  to name, which is the same condition as `path === 'model'`. */
export function anchorSummary(give: { name?: string | null }[]): string | null {
  if (give.length === 0) return null;
  const first = give[0]?.name || 'Asset';
  return give.length > 1 ? `${first} +${give.length - 1}` : first;
}
