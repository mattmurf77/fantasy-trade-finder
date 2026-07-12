import AsyncStorage from '@react-native-async-storage/async-storage';
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

// Active scoring format (1qb_ppr / sf_tep). Stored locally — mirrors web's
// localStorage `ftf_active_format` key — and surfaced as the X-Scoring-Format
// header on per-call API requests that the backend's `_active_format` reads.
// Persisted lazily; reads cache in-memory after the first AsyncStorage hit
// so request paths don't have to await on every call.
const LS_ACTIVE_FORMAT_KEY = 'ftf_active_format';
let _activeFormatCache: ScoringFormat | null = null;

/** Synchronous read of the in-memory format cache. Returns null when
 *  the format hasn't been loaded yet (before the first async read or
 *  before the user has ever set a format). Safe to call from non-async
 *  contexts such as query-key builders in component render. */
export function getActiveFormatSync(): ScoringFormat | null {
  return _activeFormatCache;
}

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

// POST /api/scoring/switch — flip the SERVER session's active scoring
// format. Mirrors the web's user-scope toggle (web/js/app.js
// onScoringToggleClick). Callers must update the local mirrors AFTER this
// resolves (setActiveScoringFormat + useSession.setActiveFormat) — see
// hooks/useScoringFormat.ts, which owns that ordering.
export async function switchScoringFormat(fmt: ScoringFormat) {
  return api.post<{ ok: true; active_format: ScoringFormat }>(
    '/api/scoring/switch',
    { format: fmt },
  );
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
//   { position: 'RB', tiers: { firsts_4plus: [id,...], first_1: [...], ... },
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

// ── Pick-anchor wizard ─────────────────────────────────────────────────
// Anchor keys are a cross-client enum shared with the backend
// (VALID_ANCHORS in backend/server.py — see docs/cross-client-invariants.md).
export type AnchorKey =
  | '4_firsts'
  | '3_firsts'
  | '2_firsts'
  | '1_first'
  | '1_second'
  | '1_third'
  | '1_fourth'
  | 'no_value';

export interface AnchorSaveResponse {
  ok: true;
  player_id: string;
  anchor: AnchorKey;
  elo: number;
  value: number;
  /** Tier the pinned Elo lands in — null = below every band (no value). */
  tier: string | null;
  scoring_format: string;
  /** Pick-value scale applied to this save (#111). 4 = consensus default
   *  (re-derived for the #117 8-tier ladder — top asset = 4 firsts). */
  top_tier_firsts: number;
}

// GET /api/rankings for the anchor wizard's queue snapshot. Unlike the
// plain getRankings (Tiers screen), this sends X-Scoring-Format so the
// queue is ordered by the SAME format's Elo board the wizard's saves
// write to (#112) — without it, session/local format drift could order
// candidates by the wrong format (e.g. 1QB order in an SF league,
// pushing QBs into the depth end of the queue).
export async function getAnchorPool() {
  return api.get<{ position: string | null; rankings: any[] }>(
    '/api/rankings',
    { headers: await formatHeader() },
  );
}

// ── Pick-value scale (#111) ────────────────────────────────────────────
// "A top-tier dynasty asset is worth N firsts." Persisted per user +
// scoring format; recalibrates only the wizard's multi-first anchors
// (backend _anchor_target_elo). 4 = the consensus default since the #117
// seed recalibration (the top consensus asset sits at the 4-firsts rung).
export type TopTierFirsts = 2 | 3 | 4;

export interface AnchorScaleResponse {
  top_tier_firsts: number;
  scoring_format: string;
}

export async function getAnchorScale() {
  return api.get<AnchorScaleResponse>('/api/anchor/scale', {
    headers: await formatHeader(),
  });
}

export async function setAnchorScale(topTierFirsts: TopTierFirsts) {
  return api.post<AnchorScaleResponse & { ok: true }>(
    '/api/anchor/scale',
    { top_tier_firsts: topTierFirsts },
    { headers: await formatHeader() },
  );
}

// POST /api/anchor/save — pin a player's value to a pick-denominated
// statement ("worth 2 firsts"). The value is position-uniform by design
// (the pick ladder drives uniform valuation across position groups); the
// tier falls out of the pinned Elo via the server's band walk. Sends
// X-Scoring-Format so the override lands on the format the wizard shows.
export async function saveAnchor(playerId: string, anchor: AnchorKey) {
  return api.post<AnchorSaveResponse>(
    '/api/anchor/save',
    { player_id: playerId, anchor },
    { headers: await formatHeader() },
  );
}

// GET /api/tier-config — shared tier-band table, single source of truth
// across backend (apply_tiers / tier_for_elo) and frontend buckets. The
// mobile app fetches this once at boot and caches it via the module-level
// store in utils/tierBands so tier_for_elo / autoBucket can stay in sync
// with the backend without baking thresholds into the bundle.
export interface TierBand { min: number; max: number; }
export interface TierConfigResponse {
  /** Display order: ['firsts_4plus','firsts_3','firsts_2','first_1',
   *  'second','third','fourth','waivers'] */
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

// POST /api/ranking-method — record the user's chosen method. Mirrors the
// RankMethodPref union in state/useSession.ts (device-local routing pref);
// the backend copy is analytics + leaguemate visibility (has_ranking_method).
export async function setRankingMethod(method: 'trio' | 'manual' | 'tiers' | 'anchor' | 'quickset') {
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
