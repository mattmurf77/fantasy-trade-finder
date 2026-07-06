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
