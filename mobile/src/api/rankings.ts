import { api } from './client';
import type { Trio, RankingProgress, Position } from '../shared/types';

// GET /api/trio?position=QB — next trio for the user's active format.
export async function getNextTrio(position?: Position | null) {
  const qs = position ? `?position=${position}` : '';
  return api.get<Trio>(`/api/trio${qs}`);
}

// POST /api/rank3  body: { ranked: [pid_first, pid_second, pid_third] }
export async function submitTrioRanking(rankedIds: [string, string, string]) {
  return api.post<any>('/api/rank3', { ranked: rankedIds });
}

// POST /api/trio/skip  body: { player_id }
// Persistently removes a player from future trios for the user+format.
export async function skipPlayer(playerId: string) {
  return api.post<any>('/api/trio/skip', { player_id: playerId });
}

// GET /api/rankings/progress
export async function getProgress() {
  return api.get<RankingProgress>('/api/rankings/progress');
}

// GET /api/rankings?position=QB — full ranked list. Used by the Tiers screen
// as the source of truth for per-position ordering.
export async function getRankings(position?: Position | null) {
  const qs = position ? `?position=${position}` : '';
  return api.get<{ position: string | null; rankings: any[] }>(`/api/rankings${qs}`);
}

// POST /api/tiers/save — save a tier assignment for a position.
// Body shape matches the web's save_tiers_route expectation:
//   { position: 'RB', tiers: { elite: [id,...], starter: [...], ... } }
export async function saveTiers(
  position: Position,
  tiers: Record<string, string[]>,
) {
  return api.post<any>('/api/tiers/save', { position, tiers });
}

// GET /api/tiers/status — per-position saved-state map
export async function getTiersStatus() {
  return api.get<{ saved: string[]; scoring_format?: string }>('/api/tiers/status');
}

// POST /api/tiers/dismiss — dismiss a player from the unassigned pool
export async function dismissPlayer(playerId: string) {
  return api.post<any>('/api/tiers/dismiss', { player_id: playerId });
}

// POST /api/ranking-method — record the user's chosen method (trio/manual/tiers)
export async function setRankingMethod(method: 'trio' | 'manual' | 'tiers') {
  return api.post<any>('/api/ranking-method', { method });
}
