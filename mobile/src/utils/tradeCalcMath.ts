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
