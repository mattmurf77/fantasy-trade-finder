// Trade Calculator math — client-side stand-in for the FTF engine's package
// valuation + fairness gate, ported from mockups/trade-calc/src/logic/tradeMath.ts.
// Pure functions only. Dual-perspective: every trade is scored on BOTH owners'
// boards, and a trade only reads as agreeable when neither side is clearly
// down on their own board.
//
// Swap path: replaced by `/api/trade/evaluate` when the server-authoritative
// version ships (docs/plans/manual-trade-calculator-plan.md).

import { CalcPlayer } from '../data/tradeCalcMock';

/**
 * Consolidation premium: the best player counts full, extra pieces are
 * discounted — three depth guys don't buy a stud.
 */
const PKG_WEIGHTS = [1, 0.88, 0.78, 0.7, 0.64, 0.6];

export function packageValue(playerIds: string[], board: Record<string, number>): number {
  const values = playerIds.map((id) => board[id] ?? 0).sort((a, b) => b - a);
  return Math.round(values.reduce((sum, v, i) => sum + v * (PKG_WEIGHTS[i] ?? 0.6), 0));
}

export type CalcVerdict = 'WIN_WIN' | 'FAIR' | 'THEY_DECLINE' | 'YOU_LOSE' | 'UNEVEN';

export const CALC_VERDICT_LABEL: Record<CalcVerdict, string> = {
  WIN_WIN: 'Win–win',
  FAIR: 'Fair trade',
  THEY_DECLINE: 'You win big — they likely decline',
  YOU_LOSE: "You're overpaying",
  UNEVEN: 'Uneven',
};

export interface CalcTradeEval {
  /** Your board's view of what you send / receive. */
  myGive: number;
  myGet: number;
  myDeltaPct: number;
  /** Their board's view of the same trade (they receive what you send). */
  theirGive: number;
  theirGet: number;
  theirDeltaPct: number;
  verdict: CalcVerdict;
}

function pct(get: number, give: number): number {
  if (give <= 0) return get > 0 ? 1 : 0;
  return (get - give) / give;
}

export function evaluateTrade(
  sendIds: string[],
  receiveIds: string[],
  myBoard: Record<string, number>,
  theirBoard: Record<string, number>,
): CalcTradeEval {
  const myGive = packageValue(sendIds, myBoard);
  const myGet = packageValue(receiveIds, myBoard);
  const theirGive = packageValue(receiveIds, theirBoard);
  const theirGet = packageValue(sendIds, theirBoard);
  const myDeltaPct = pct(myGet, myGive);
  const theirDeltaPct = pct(theirGet, theirGive);

  let verdict: CalcVerdict;
  if (myDeltaPct >= 0.02 && theirDeltaPct >= 0.02) verdict = 'WIN_WIN';
  else if (myDeltaPct >= -0.04 && theirDeltaPct >= -0.04) verdict = 'FAIR';
  else if (myDeltaPct > 0.04 && theirDeltaPct < -0.04) verdict = 'THEY_DECLINE';
  else if (theirDeltaPct > 0.04 && myDeltaPct < -0.04) verdict = 'YOU_LOSE';
  else verdict = 'UNEVEN';

  return { myGive, myGet, myDeltaPct, theirGive, theirGet, theirDeltaPct, verdict };
}

export interface CalcSuggestion {
  players: CalcPlayer[];
  evaluation: CalcTradeEval;
  score: number;
}

/** All combos of size 1..maxSize (≤3) from a candidate pool. */
function combos(ids: string[], maxSize = 3): string[][] {
  const out: string[][] = [];
  for (let i = 0; i < ids.length; i++) {
    out.push([ids[i]]);
    if (maxSize < 2) continue;
    for (let j = i + 1; j < ids.length; j++) {
      out.push([ids[i], ids[j]]);
      if (maxSize < 3) continue;
      for (let k = j + 1; k < ids.length; k++) {
        out.push([ids[i], ids[j], ids[k]]);
      }
    }
  }
  return out;
}

/** Shared scoring: maximize the worse side's gain, penalize lopsidedness. */
function scoreSuggestion(evaluation: CalcTradeEval): number {
  const worse = Math.min(evaluation.myDeltaPct, evaluation.theirDeltaPct);
  const gap = Math.abs(evaluation.myDeltaPct - evaluation.theirDeltaPct);
  return worse - gap * 0.5;
}

const AGREEABLE: CalcVerdict[] = ['WIN_WIN', 'FAIR'];

/**
 * Suggest fair packages for the open side of the trade.
 * - If you've picked players to send, suggests what to ask for from their roster.
 * - If you've only picked players to receive, suggests what to offer from yours.
 * Scored to maximize the worse side's gain (mutual benefit) while penalizing lopsidedness.
 */
export function suggestPackages(
  sendIds: string[],
  receiveIds: string[],
  myRosterIds: string[],
  theirRosterIds: string[],
  myBoard: Record<string, number>,
  theirBoard: Record<string, number>,
  playerById: Record<string, CalcPlayer>,
  limit = 4,
): { forSide: 'receive' | 'send'; suggestions: CalcSuggestion[] } | null {
  const forSide: 'receive' | 'send' | null =
    sendIds.length > 0 ? 'receive' : receiveIds.length > 0 ? 'send' : null;
  if (!forSide) return null;

  const pool = forSide === 'receive' ? theirRosterIds : myRosterIds;
  const suggestions = combos(pool)
    .map((combo) => {
      const evaluation =
        forSide === 'receive'
          ? evaluateTrade(sendIds, combo, myBoard, theirBoard)
          : evaluateTrade(combo, receiveIds, myBoard, theirBoard);
      return {
        players: combo.map((id) => playerById[id]).filter(Boolean),
        evaluation,
        score: scoreSuggestion(evaluation),
      };
    })
    .filter((s) => AGREEABLE.includes(s.evaluation.verdict))
    .sort((a, b) => b.score - a.score)
    .slice(0, limit);

  return { forSide, suggestions };
}

/**
 * Balance an already-built trade that neither board likes yet: propose 1–2
 * asset add-ons appended to the under-paying side (drawn from that side's
 * owner roster) that pull the whole trade into Fair / Win–win territory.
 * Returns null when the trade is incomplete or already agreeable.
 */
export function suggestAddOns(
  sendIds: string[],
  receiveIds: string[],
  myRosterIds: string[],
  theirRosterIds: string[],
  myBoard: Record<string, number>,
  theirBoard: Record<string, number>,
  playerById: Record<string, CalcPlayer>,
  limit = 3,
): { forSide: 'send' | 'receive'; suggestions: CalcSuggestion[] } | null {
  if (sendIds.length === 0 || receiveIds.length === 0) return null;
  const current = evaluateTrade(sendIds, receiveIds, myBoard, theirBoard);
  if (AGREEABLE.includes(current.verdict)) return null;

  // Whoever is worse off on their own board needs more coming their way:
  // they're down → sweeten what I send; I'm down → they add to what I receive.
  const forSide: 'send' | 'receive' =
    current.theirDeltaPct < current.myDeltaPct ? 'send' : 'receive';
  const pool = (forSide === 'send' ? myRosterIds : theirRosterIds).filter(
    (id) => !sendIds.includes(id) && !receiveIds.includes(id),
  );

  const suggestions = combos(pool, 2)
    .map((combo) => {
      const evaluation =
        forSide === 'send'
          ? evaluateTrade([...sendIds, ...combo], receiveIds, myBoard, theirBoard)
          : evaluateTrade(sendIds, [...receiveIds, ...combo], myBoard, theirBoard);
      return {
        players: combo.map((id) => playerById[id]).filter(Boolean),
        evaluation,
        score: scoreSuggestion(evaluation),
      };
    })
    .filter((s) => AGREEABLE.includes(s.evaluation.verdict))
    .sort((a, b) => b.score - a.score)
    .slice(0, limit);

  return { forSide, suggestions };
}

export function formatDelta(deltaPct: number): string {
  const sign = deltaPct > 0 ? '+' : '';
  return `${sign}${Math.round(deltaPct * 100)}%`;
}

// ─────────────────────────────────────────────────────────────────────────────
// Server-math mirror (#78). The live/in-league evaluator is the backend's v2
// engine (trade_service.package_value_v2): each asset contributes
// v * (0.15 + 0.85 * (v / v_max)^gamma) with v_max the best single asset in
// the WHOLE trade — so lesser pieces are discounted nonlinearly, nothing like
// the flat PKG_WEIGHTS sums above. gamma (package_adj_gamma) and the
// crown-asset premium are server-config/flag tunable, so this mirror is a
// candidate-ranking HEURISTIC only: every suggestion shown against a server
// verdict must be confirmed via POST /api/trade/evaluate before display.
// ─────────────────────────────────────────────────────────────────────────────

const V2_GAMMA = 1.5; // backend default package_adj_gamma

/** Mirror of backend package_value_v2 (crown premium omitted — flag-gated). */
export function packageValueV2(values: number[], vMax: number): number {
  if (values.length === 0) return 0;
  const m = Math.max(vMax, 1e-9);
  return values.reduce((s, v) => s + v * (0.15 + 0.85 * Math.pow(v / m, V2_GAMMA)), 0);
}

/** min/max package ratio under the v2 mirror — the server's point_ratio. */
export function consensusRatio(giveVals: number[], recvVals: number[]): number | null {
  if (giveVals.length === 0 || recvVals.length === 0) return null;
  const vMax = Math.max(...giveVals, ...recvVals);
  const gv = packageValueV2(giveVals, vMax);
  const rv = packageValueV2(recvVals, vMax);
  if (gv <= 0 || rv <= 0) return null;
  return Math.min(gv, rv) / Math.max(gv, rv);
}

export interface RankedCandidate {
  ids: string[];
  /** Post-change point ratio predicted by the v2 mirror. */
  predictedRatio: number;
}

const vals = (ids: string[], board: Record<string, number>) => ids.map((id) => board[id] ?? 0);

/**
 * Shortlist 1–2-piece add-ons for one side of an unbalanced trade, ranked by
 * the v2-mirror point ratio AFTER the add. Only combos the mirror predicts
 * strictly improve the current ratio survive — the server confirmation pass
 * then re-checks each survivor with the real evaluator.
 */
export function rankAddOnCandidates(
  sendIds: string[],
  receiveIds: string[],
  addTo: 'send' | 'receive',
  poolIds: string[],
  board: Record<string, number>,
  take = 8,
): RankedCandidate[] {
  const current = consensusRatio(vals(sendIds, board), vals(receiveIds, board));
  if (current === null) return [];
  return combos(poolIds, 2)
    .map((ids) => {
      const send = addTo === 'send' ? [...sendIds, ...ids] : sendIds;
      const recv = addTo === 'receive' ? [...receiveIds, ...ids] : receiveIds;
      return { ids, predictedRatio: consensusRatio(vals(send, board), vals(recv, board)) ?? 0 };
    })
    .filter((c) => c.predictedRatio > current)
    .sort((a, b) => b.predictedRatio - a.predictedRatio)
    .slice(0, take);
}

/**
 * Shortlist full packages (1–3 pieces) for the open side of a trade, ranked
 * by the v2-mirror point ratio of the resulting trade.
 */
export function rankPackageCandidates(
  fixedIds: string[],
  forSide: 'send' | 'receive',
  poolIds: string[],
  board: Record<string, number>,
  take = 8,
): RankedCandidate[] {
  if (fixedIds.length === 0) return [];
  const fixedVals = vals(fixedIds, board);
  return combos(poolIds, 3)
    .map((ids) => {
      const comboVals = vals(ids, board);
      const ratio =
        forSide === 'receive'
          ? consensusRatio(fixedVals, comboVals)
          : consensusRatio(comboVals, fixedVals);
      return { ids, predictedRatio: ratio ?? 0 };
    })
    .filter((c) => c.predictedRatio >= 0.7) // just below the server's 0.75 fair line
    .sort((a, b) => b.predictedRatio - a.predictedRatio)
    .slice(0, take);
}

/**
 * Shortlist add-ons whose raw consensus sum sits closest to a known value
 * deficit. Used for the in-league (Mode B) divergence basis, where the gap to
 * close lives on a member's personal board that the client can't see — the
 * consensus sum is the best available proxy, and the Mode B evaluate call
 * confirms every survivor against the real boards.
 */
export function rankGapCandidates(
  poolIds: string[],
  board: Record<string, number>,
  deficit: number,
  take = 8,
): string[][] {
  if (deficit <= 0) return [];
  return combos(poolIds, 2)
    .map((ids) => ({ ids, miss: Math.abs(vals(ids, board).reduce((a, b) => a + b, 0) - deficit) }))
    .sort((a, b) => a.miss - b.miss)
    .slice(0, take)
    .map((c) => c.ids);
}

// ── Display adapters: server evaluations → the CalcTradeEval shape that
//    SuggestionCard renders. Only fair/even (Mode A) or improving (Mode B)
//    evaluations are ever displayed, so the verdict mapping stays coarse. ──

interface ConsensusEvalLike {
  give_value: number;
  receive_value: number;
}
interface BoardsEvalLike extends ConsensusEvalLike {
  your_give_value: number;
  your_receive_value: number;
  their_give_value: number;
  their_receive_value: number;
  mutual_gain: boolean;
}

/** Mode A (single consensus board): both perspectives are mirror images. */
export function evalFromConsensus(e: ConsensusEvalLike): CalcTradeEval {
  return {
    myGive: Math.round(e.give_value),
    myGet: Math.round(e.receive_value),
    myDeltaPct: pct(e.receive_value, e.give_value),
    theirGive: Math.round(e.receive_value),
    theirGet: Math.round(e.give_value),
    theirDeltaPct: pct(e.give_value, e.receive_value),
    verdict: 'FAIR',
  };
}

/** Mode B (two real boards): each owner's delta by their own rankings. */
export function evalFromBoards(e: BoardsEvalLike): CalcTradeEval {
  return {
    myGive: Math.round(e.your_give_value),
    myGet: Math.round(e.your_receive_value),
    myDeltaPct: pct(e.your_receive_value, e.your_give_value),
    theirGive: Math.round(e.their_receive_value),
    theirGet: Math.round(e.their_give_value),
    theirDeltaPct: pct(e.their_give_value, e.their_receive_value),
    verdict: e.mutual_gain ? 'WIN_WIN' : 'FAIR',
  };
}
