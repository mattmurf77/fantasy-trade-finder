// Client-side stand-in for the FTF engine's package valuation + fairness gate.
// Dual-perspective: every trade is scored on BOTH owners' boards, and a trade
// only reads as agreeable when neither side is clearly down on their own board.

import { Owner, Player, PLAYER_BY_ID } from '../data/mock';

/**
 * Consolidation premium: the best player counts full, extra pieces are
 * discounted — three depth guys don't buy a stud.
 */
const PKG_WEIGHTS = [1, 0.88, 0.78, 0.7, 0.64, 0.6];

export function packageValue(playerIds: string[], board: Record<string, number>): number {
  const values = playerIds.map((id) => board[id] ?? 0).sort((a, b) => b - a);
  return Math.round(values.reduce((sum, v, i) => sum + v * (PKG_WEIGHTS[i] ?? 0.6), 0));
}

export type Verdict = 'WIN_WIN' | 'FAIR' | 'THEY_DECLINE' | 'YOU_LOSE' | 'UNEVEN';

export const VERDICT_LABEL: Record<Verdict, string> = {
  WIN_WIN: 'Win–win',
  FAIR: 'Fair trade',
  THEY_DECLINE: 'You win big — they likely decline',
  YOU_LOSE: "You're overpaying",
  UNEVEN: 'Uneven',
};

export interface TradeEval {
  /** Your board's view of what you send / receive. */
  myGive: number;
  myGet: number;
  myDeltaPct: number;
  /** Their board's view of the same trade (they receive what you send). */
  theirGive: number;
  theirGet: number;
  theirDeltaPct: number;
  verdict: Verdict;
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
): TradeEval {
  const myGive = packageValue(sendIds, myBoard);
  const myGet = packageValue(receiveIds, myBoard);
  const theirGive = packageValue(receiveIds, theirBoard);
  const theirGet = packageValue(sendIds, theirBoard);
  const myDeltaPct = pct(myGet, myGive);
  const theirDeltaPct = pct(theirGet, theirGive);

  let verdict: Verdict;
  if (myDeltaPct >= 0.02 && theirDeltaPct >= 0.02) verdict = 'WIN_WIN';
  else if (myDeltaPct >= -0.04 && theirDeltaPct >= -0.04) verdict = 'FAIR';
  else if (myDeltaPct > 0.04 && theirDeltaPct < -0.04) verdict = 'THEY_DECLINE';
  else if (theirDeltaPct > 0.04 && myDeltaPct < -0.04) verdict = 'YOU_LOSE';
  else verdict = 'UNEVEN';

  return { myGive, myGet, myDeltaPct, theirGive, theirGet, theirDeltaPct, verdict };
}

export interface Suggestion {
  players: Player[];
  evaluation: TradeEval;
  score: number;
}

/** All combos of size 1..3 from a candidate pool. */
function combos(ids: string[]): string[][] {
  const out: string[][] = [];
  for (let i = 0; i < ids.length; i++) {
    out.push([ids[i]]);
    for (let j = i + 1; j < ids.length; j++) {
      out.push([ids[i], ids[j]]);
      for (let k = j + 1; k < ids.length; k++) {
        out.push([ids[i], ids[j], ids[k]]);
      }
    }
  }
  return out;
}

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
  limit = 4,
): { forSide: 'receive' | 'send'; suggestions: Suggestion[] } | null {
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
      const worse = Math.min(evaluation.myDeltaPct, evaluation.theirDeltaPct);
      const gap = Math.abs(evaluation.myDeltaPct - evaluation.theirDeltaPct);
      return {
        players: combo.map((id) => PLAYER_BY_ID[id]),
        evaluation,
        score: worse - gap * 0.5,
      };
    })
    .filter((s) => s.evaluation.verdict === 'WIN_WIN' || s.evaluation.verdict === 'FAIR')
    .sort((a, b) => b.score - a.score)
    .slice(0, limit);

  return { forSide, suggestions };
}

export function formatDelta(deltaPct: number): string {
  const sign = deltaPct > 0 ? '+' : '';
  return `${sign}${Math.round(deltaPct * 100)}%`;
}
