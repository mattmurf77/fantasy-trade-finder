import { api } from './client';
import type { TradeCard, TradeMatch } from '../shared/types';

export interface GenerateBody {
  league_id: string;
  fairness_threshold?: number;      // 0.5 – 1.0
  pinned_give_players?: string[];
}

// POST /api/trades/generate — kicks off trade discovery for the active league.
export async function generateTrades(body: GenerateBody) {
  return api.post<{ trades: TradeCard[] }>('/api/trades/generate', body);
}

// GET /api/trades?league_id=X — cached most-recent generated trades
export async function getRecentTrades(leagueId: string) {
  return api.get<{ trades: TradeCard[] }>(
    `/api/trades?league_id=${encodeURIComponent(leagueId)}`,
  );
}

// POST /api/trades/swipe  body: { trade_id, decision: 'like' | 'pass' }
export async function swipeTrade(
  tradeId: string,
  decision: 'like' | 'pass',
) {
  return api.post<any>('/api/trades/swipe', { trade_id: tradeId, decision });
}

// GET /api/trades/matches  — the user's mutual-match inbox
export async function getMatches() {
  return api.get<{ matches: TradeMatch[] }>('/api/trades/matches');
}

// POST /api/trades/matches/:id/disposition  body: { disposition: 'accepted' | 'declined' }
export async function setMatchDisposition(
  matchId: string,
  disposition: 'accepted' | 'declined',
) {
  return api.post<any>(`/api/trades/matches/${matchId}/disposition`, {
    disposition,
  });
}

// GET /api/trades/liked — liked trades + badge count
export async function getLikedTrades() {
  return api.get<{ liked_count: number }>('/api/trades/liked');
}
