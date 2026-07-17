// Manual Trade Calculator — open consensus endpoints (no session required).
// Server side: backend/server.py trade_calc_values_route / trade_evaluate_route,
// which reuse the trade engine's universal pool + elo_to_value + _fairness_v3
// so calculator numbers always match the finder's.

import { apiRequest } from './client';
import type { ScoringFormat } from '../shared/types';

export interface CalcValueRow {
  id: string;
  name: string;
  position: string;
  team: string | null;
  age: number | null;
  /** Consensus dynasty value (elo_to_value over the pool's seed Elo). */
  value: number;
}

export type CalcVerdict = 'even' | 'fair' | 'unfair';

// Pick-denominated gap read: the package-value difference expressed as
// generic-pick equivalents so the delta is an actionable counteroffer
// ("add ≈ a Mid 2nd") instead of an abstract number.
export interface CalcGapPick {
  pick_id: string;
  label: string; // e.g. "Mid 2nd Round Pick" — matches the pool's naming
  value: number;
}
export interface CalcGap {
  value: number;
  /** The LIGHTER side — the one that needs the sweetener. Null when 0. */
  add_to: 'give' | 'receive' | null;
  /** Gap in units of a generic Mid 1st (the "base first"). */
  firsts: number;
  /** Nearest single generic pick — null when negligible or too big. */
  pick_equivalent: CalcGapPick | null;
}

export interface CalcEvaluation {
  scoring_format: ScoringFormat;
  give_value: number;
  receive_value: number;
  /** min/max package ratio, 0–1. Null until both sides have a valued asset. */
  point_ratio: number | null;
  /** Fairness when the gate passes, null when it fails (or one-sided). */
  fairness: number | null;
  verdict: CalcVerdict | null;
  favors: 'give' | 'receive' | 'even' | null;
  /** Null until both sides have a valued asset. */
  gap: CalcGap | null;
  per_player: { player_id: string; side: 'give' | 'receive'; value: number }[];
  dropped_player_ids: string[];
}

export async function getTradeValues(
  format: ScoringFormat,
  signal?: AbortSignal,
): Promise<{ scoring_format: ScoringFormat; players: CalcValueRow[] }> {
  return apiRequest(`/api/trade/values?scoring_format=${format}`, {
    skipAuth: true,
    signal,
  });
}

export async function evaluateTrade(
  givePlayerIds: string[],
  receivePlayerIds: string[],
  format: ScoringFormat,
  signal?: AbortSignal,
): Promise<CalcEvaluation> {
  return apiRequest('/api/trade/evaluate', {
    method: 'POST',
    skipAuth: true,
    signal,
    body: {
      give_player_ids: givePlayerIds,
      receive_player_ids: receivePlayerIds,
      scoring_format: format,
    },
  });
}

// ── Mode B — in-league, both owners' boards ──────────────────────────────
// Same endpoint, but WITH a session + {league_id, opponent_user_id}. The
// server prices each side by the caller's AND the opponent's real rankings
// (member_rankings) and returns per-board deltas + mutual_gain + basis. An
// unranked opponent degrades to a consensus read (basis='consensus').
export interface CalcEvaluationInLeague extends CalcEvaluation {
  basis: 'divergence' | 'consensus';
  opponent_user_id?: string;
  opponent_username?: string | null;
  opponent_has_rankings: boolean;
  your_give_value: number;
  your_receive_value: number;
  their_give_value: number;
  their_receive_value: number;
  your_value_delta: number; // by YOUR board (positive = you gain)
  their_value_delta: number; // by THEIR board (positive = they gain)
  mutual_gain: boolean;
}

// ── Suggestion confirmation (#78) ────────────────────────────────────────
// Suggestions are pre-ranked client-side by a mirror of the server math, but
// every candidate shown next to a server verdict is CONFIRMED through the
// same /api/trade/evaluate endpoint first, so a suggestion can never
// disagree with the evaluator. Chunked to keep the request burst small; a
// failed probe resolves to null (that candidate is simply dropped).

const EVAL_CHUNK = 4;

export interface TradeProbe {
  give: string[];
  receive: string[];
}

async function chunked<T>(
  probes: TradeProbe[],
  run: (p: TradeProbe) => Promise<T>,
): Promise<(T | null)[]> {
  const out: (T | null)[] = [];
  for (let i = 0; i < probes.length; i += EVAL_CHUNK) {
    const results = await Promise.all(
      probes.slice(i, i + EVAL_CHUNK).map((p) => run(p).catch(() => null)),
    );
    out.push(...results);
  }
  return out;
}

/** Mode A confirmation: evaluate several hand-built trades on consensus. */
export function evaluateTrades(
  probes: TradeProbe[],
  format: ScoringFormat,
  signal?: AbortSignal,
): Promise<(CalcEvaluation | null)[]> {
  return chunked(probes, (p) => evaluateTrade(p.give, p.receive, format, signal));
}

/** Mode B confirmation: same, priced by both owners' real boards. */
export function evaluateTradesInLeague(
  probes: TradeProbe[],
  format: ScoringFormat,
  leagueId: string,
  opponentUserId: string,
  signal?: AbortSignal,
): Promise<(CalcEvaluationInLeague | null)[]> {
  return chunked(probes, (p) =>
    evaluateTradeInLeague(p.give, p.receive, format, leagueId, opponentUserId, signal),
  );
}

export async function evaluateTradeInLeague(
  givePlayerIds: string[],
  receivePlayerIds: string[],
  format: ScoringFormat,
  leagueId: string,
  opponentUserId: string,
  signal?: AbortSignal,
): Promise<CalcEvaluationInLeague> {
  return apiRequest('/api/trade/evaluate', {
    method: 'POST',
    signal, // authed — Mode B needs the session to read the caller's rankings
    body: {
      give_player_ids: givePlayerIds,
      receive_player_ids: receivePlayerIds,
      scoring_format: format,
      league_id: leagueId,
      opponent_user_id: opponentUserId,
    },
  });
}
