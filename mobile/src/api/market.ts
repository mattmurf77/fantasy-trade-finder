import { api } from './client';
import type { ScoringFormat } from '../shared/types';

// ── Market movers (#243 "Market pulse" strip; flag `market.movers`) ──────
// GET /api/market/movers — top risers/fallers by trailing-window % change
// of FTF community value (player_value_history consensus snapshots). Open
// read (universal consensus data, no board/league content); the route 404s
// while the flag is off — callers treat any error as "no data".

export interface MarketMover {
  player_id: string;
  name: string;
  position: string;
  team: string | null;
  /** Signed % change over the window (named for the default 30d window). */
  pct_30d: number;
  value_now: number;
}

export interface MarketMovers {
  risers: MarketMover[];
  fallers: MarketMover[];
  /** Latest snapshot date (YYYY-MM-DD, UTC); null while no history exists. */
  as_of: string | null;
  window_days: number;
  source: 'ftf_community_value';
}

export async function getMarketMovers(format: ScoringFormat) {
  return api.get<MarketMovers>(
    `/api/market/movers?scoring_format=${encodeURIComponent(format)}`,
  );
}
