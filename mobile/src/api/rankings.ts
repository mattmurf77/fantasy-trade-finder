import AsyncStorage from '@react-native-async-storage/async-storage';
import { api } from './client';
import type { Trio, RankingProgress, Position, ScoringFormat } from '../shared/types';

// Active scoring format (1qb_ppr / sf_tep). Stored locally — mirrors web's
// localStorage `ftf_active_format` key — and surfaced as the X-Scoring-Format
// header on per-call API requests that the backend's `_active_format` reads.
// Persisted lazily; reads cache in-memory after the first AsyncStorage hit
// so request paths don't have to await on every call.
const LS_ACTIVE_FORMAT_KEY = 'ftf_active_format';
let _activeFormatCache: ScoringFormat | null = null;

export async function getActiveScoringFormat(): Promise<ScoringFormat | null> {
  if (_activeFormatCache) return _activeFormatCache;
  try {
    const v = await AsyncStorage.getItem(LS_ACTIVE_FORMAT_KEY);
    if (v === '1qb_ppr' || v === 'sf_tep') {
      _activeFormatCache = v;
      return v;
    }
  } catch {
    /* AsyncStorage failure is non-fatal — backend uses session default. */
  }
  return null;
}

export async function setActiveScoringFormat(fmt: ScoringFormat): Promise<void> {
  _activeFormatCache = fmt;
  try {
    await AsyncStorage.setItem(LS_ACTIVE_FORMAT_KEY, fmt);
  } catch {
    /* non-fatal */
  }
}

/** Helper: build the `{ 'X-Scoring-Format': <fmt> }` header dict — or `{}`
 *  when no format has been stored locally yet (so the backend falls back
 *  to the session's active_format). Use as `headers: await formatHeader()`
 *  on any request that should honor the user's chosen per-call format. */
export async function formatHeader(): Promise<Record<string, string>> {
  const fmt = await getActiveScoringFormat();
  return fmt ? { 'X-Scoring-Format': fmt } : {};
}

export interface Streak {
  current: number;
  longest: number;
  last_rank_local_date: string | null;
}

// GET /api/me/streak — returns the user's current ranking streak.
export async function getStreak() {
  return api.get<Streak>('/api/me/streak');
}

// GET /api/trio?position=QB — next trio for the user's active format.
export async function getNextTrio(position?: Position | null) {
  const qs = position ? `?position=${position}` : '';
  return api.get<Trio>(`/api/trio${qs}`);
}

// POST /api/rank3  body: { ranked: [pid_first, pid_second, pid_third] }
// Response includes the post-rank streak snapshot so the UI can detect
// an increment without a follow-up GET /api/me/streak.
export async function submitTrioRanking(rankedIds: [string, string, string]) {
  return api.post<{
    interaction_count: number;
    threshold: number;
    threshold_met: boolean;
    percent: number;
    streak: Streak;
  }>('/api/rank3', { ranked: rankedIds });
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

// POST /api/rankings/reorder — apply a manual reorder to the user's rankings.
// The ordered_ids list represents the user's desired ranking from best
// (index 0) to worst. Backend overrides ELO values to match this order.
// Sends X-Scoring-Format so the reorder writes to the right per-format
// override dict — without it the backend's `_active_format` falls back to
// the session's active_format which may not match the user's current UI
// selection (see web's parallel comment on copy-from-format).
export async function reorderRankings(
  position: Position | null,
  orderedIds: string[],
) {
  return api.post<{ ok: true; count: number; scoring_format: string }>(
    '/api/rankings/reorder',
    { position, ordered_ids: orderedIds },
    { headers: await formatHeader() },
  );
}

// POST /api/tiers/save — save a tier assignment for a position.
// Body shape matches the web's save_tiers_route expectation:
//   { position: 'RB', tiers: { elite: [id,...], starter: [...], ... },
//     cleared_pids: ['12345', ...] }
//
// `clearedPids`: players the user dragged OUT of any tier (back to the
// pool) since the last save. Without this, the backend's
// tier_overrides table would keep the old override and the chip would
// reappear on next reload — the round-trip data-loss bug PR #25 fixed
// for web. Passing `[]` is fine; passing the real removed IDs lets the
// backend DELETE those override rows and respect the user's intent.
export async function saveTiers(
  position: Position,
  tiers: Record<string, string[]>,
  clearedPids: string[] = [],
) {
  return api.post<any>('/api/tiers/save', {
    position,
    tiers,
    cleared_pids: clearedPids,
  });
}

// GET /api/tier-config — shared tier-band table, single source of truth
// across backend (apply_tiers / tier_for_elo) and frontend buckets. The
// mobile app fetches this once at boot and caches it via the module-level
// store in utils/tierBands so tier_for_elo / autoBucket can stay in sync
// with the backend without baking thresholds into the bundle.
export interface TierBand { min: number; max: number; }
export interface TierConfigResponse {
  /** Display order: ['elite','starter','solid','depth','bench'] */
  tiers:  string[];
  /** Nested: scoring_format → position → tier → {min, max}. */
  config: Record<string, Record<string, Record<string, TierBand>>>;
}
export async function getTierConfig(): Promise<TierConfigResponse> {
  return api.get<TierConfigResponse>('/api/tier-config');
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
