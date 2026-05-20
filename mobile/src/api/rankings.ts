import { api } from './client';
import type {
  Trio,
  RankingProgress,
  Position,
  Player,
  ScoringFormat,
  TrendRow,
  ContrarianGapEntry,
} from '../shared/types';

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

// GET /api/rookies — rookie / pre-draft prospect players for the dynasty
// rookie draft board. Backend groups them by position and returns a total
// count. Rookie rows may include `college` on top of the standard Player
// fields; not all Player fields are populated.
export interface RookiePlayer extends Player {
  college?: string | null;
}
export interface RookiesResponse {
  grouped: Record<Position, RookiePlayer[]>;
  total: number;
}
export async function getRookies(_opts?: { season?: string }) {
  // The backend doesn't currently consume a season param — accepted in the
  // function signature for future-proofing and parity with the plan doc.
  return api.get<RookiesResponse>('/api/rookies');
}

// ── Trends (Bundle 2) ───────────────────────────────────────────────────
// All three endpoints share the same session/format resolution path on the
// backend (see _require_session in backend/server.py). Passing
// `scoringFormat` adds the X-Scoring-Format header so the caller can peek
// at a non-active format without flipping the session; omit it to use the
// user's active format.

export interface RisersFallersResponse {
  risers:  Record<'QB' | 'RB' | 'WR' | 'TE' | 'ALL', TrendRow[]>;
  fallers: Record<'QB' | 'RB' | 'WR' | 'TE' | 'ALL', TrendRow[]>;
  window_days: number;
  sample_size: number;
  has_history: boolean;
}

// GET /api/trends/risers-fallers?window_days=30&top_n=10
// Returns biggest ELO movers over the window, grouped by position. Position
// filtering is client-side — pre-segmented in the response.
export async function getRisersAndFallers(opts?: {
  position?: Position | null;       // accepted for API symmetry — currently unused server-side
  days?: number;                    // window in days (default 30)
  topN?: number;                    // per-side, per-position cap (default 5)
  scoringFormat?: ScoringFormat;
}) {
  const days = opts?.days ?? 30;
  const topN = opts?.topN ?? 10;
  const headers: Record<string, string> = {};
  if (opts?.scoringFormat) headers['X-Scoring-Format'] = opts.scoringFormat;
  return api.get<RisersFallersResponse>(
    `/api/trends/risers-fallers?window_days=${days}&top_n=${topN}`,
    { headers },
  );
}

export interface ConsensusGapResponse {
  has_baseline: boolean;
  baseline_user_count: number;
  easiest_sells: ContrarianGapEntry[];
  easiest_buys:  ContrarianGapEntry[];
  reason?: string;
}

// GET /api/trends/consensus-gap?league_id=...&top_n=5
// "Easiest sells" = roster players you over-value vs market.
// "Easiest buys"  = non-roster players you over-value vs that owner.
export async function getContrarianGap(opts: {
  leagueId: string;
  position?: Position | null;       // accepted for symmetry; backend is league-wide
  topN?: number;
  scoringFormat?: ScoringFormat;
}) {
  const topN = opts.topN ?? 5;
  const headers: Record<string, string> = {};
  if (opts.scoringFormat) headers['X-Scoring-Format'] = opts.scoringFormat;
  const qs = `?league_id=${encodeURIComponent(opts.leagueId)}&top_n=${topN}`;
  return api.get<ConsensusGapResponse>(`/api/trends/consensus-gap${qs}`, { headers });
}
