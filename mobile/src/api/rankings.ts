import AsyncStorage from '@react-native-async-storage/async-storage';
import { api, ApiError } from './client';
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

// ── Rookie scope (rookie-draft M2, flag `ranks.rookie_subset`) ─────────
// `?scope=rookie` is a POST-Elo VIEW FILTER on the server (see the header
// comment in backend/server.py above `_apply_rookie_scope`): the pool, the
// Elo computation and every write stay on the FULL position pool, and the
// subset is applied to the already-computed response. So a rookie's value
// is the same number scoped or unscoped — one board, one Elo space.
//
// The flag is server-delivered: with it off the backend never even parses
// the parameter, and the client never sends one (rookieScopeParam() returns
// undefined) — the two halves fail closed independently.
export type RankScopeParam = 'rookie';

/** The typed empty response. A thin or unloaded rookie class is a real,
 *  expected state of this feature (a class does not exist upstream until
 *  ~late April), so the scoped path returns 200 with a reason the UI can
 *  render — never the bare 400 the unscoped path returns for a <3 pool. */
export interface ScopedEmpty {
  empty: true;
  reason: 'thin_pool' | 'class_not_loaded' | 'stale_player_cache' | string;
  position: string | null;
  scope: RankScopeParam;
  count: number;
}

export function isScopedEmpty(d: unknown): d is ScopedEmpty {
  return !!d && typeof d === 'object' && (d as ScopedEmpty).empty === true;
}

export interface RankingsResponse {
  position: string | null;
  rankings: any[];
  interaction_count?: number;
  threshold?: number;
  threshold_met?: boolean;
  version?: number;
}

/** Split a possibly-scoped rankings payload into rows + empty state, so a
 *  screen never has to narrow the union inline. `rows` is `[]` on the empty
 *  branch, which is exactly what every list already renders. */
export function splitRankings(
  d: RankingsResponse | ScopedEmpty | undefined,
): { rows: any[]; empty: ScopedEmpty | null } {
  if (isScopedEmpty(d)) return { rows: [], empty: d };
  return { rows: d?.rankings ?? [], empty: null };
}

const scopeQuery = (scope?: RankScopeParam) => (scope ? `scope=${scope}` : '');

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
// `scope: 'rookie'` narrows CANDIDATE SELECTION to the rookie subset; the
// Elo updates the user's picks produce are unchanged full-board updates.
// The scoped path can answer `{empty:true, reason:'thin_pool'}` (200).
export async function getNextTrio(
  position?: Position | null,
  opts?: { scope?: RankScopeParam },
) {
  const parts = [position ? `position=${position}` : '', scopeQuery(opts?.scope)]
    .filter(Boolean);
  const qs = parts.length ? `?${parts.join('&')}` : '';
  return api.get<Trio | ScopedEmpty>(`/api/trio${qs}`);
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
// as the source of truth for per-position ordering. Omit `position` for the
// cross-position board (also what the consolidated rookie view reads).
// `scope: 'rookie'` filters the response to the rookie subset with `rank`
// renumbered 1..n; every other field (elo, tier meters, consensus rank)
// is passed through untouched.
export async function getRankings(
  position?: Position | null,
  opts?: { scope?: RankScopeParam },
) {
  const parts = [position ? `position=${position}` : '', scopeQuery(opts?.scope)]
    .filter(Boolean);
  const qs = parts.length ? `?${parts.join('&')}` : '';
  return api.get<RankingsResponse | ScopedEmpty>(`/api/rankings${qs}`);
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
  // `quickrank` marks Quick Rank saves so the backend fires
  // quickrank_completed (analytics FR-20, server.py). `rookie_ranks` is the
  // forensic tag on the consolidated rookie board's drags — request-only
  // today (the route branches on `quickrank` alone and ignores every other
  // value, so the response is byte-identical), but it keeps a scoped edit
  // identifiable in request logs and matches the `via:'rookie_*'` vocabulary
  // the tiers lane already uses.
  via?: 'quickrank' | 'rookie_ranks',
) {
  return api.post<{ ok: true; count: number; scoring_format: string }>(
    '/api/rankings/reorder',
    { position, ordered_ids: orderedIds, ...(via ? { via } : {}) },
    { headers: await formatHeader() },
  );
}

// ── Rankings import (#232 follow-on, flag `ranks.import`) ──────────────
// Paste-first import v1: the client sends the pasted table's lines; the
// backend's tolerant parser + fuzzy matcher (backend/rankings_import.py)
// resolves each against the universal pool for the active format.

export interface ImportPlayer {
  id: string;
  name: string;
  team: string | null;
  position: string | null;
}

export interface ImportMatchRow {
  /** The original pasted line (trimmed). */
  input: string;
  /** The name the parser extracted from the line. */
  name: string;
  status: 'matched' | 'ambiguous' | 'unmatched';
  player: ImportPlayer | null;
  /** ≤3 candidates for ambiguous rows, consensus-best first. */
  candidates: ImportPlayer[];
}

export interface ImportMatchResponse {
  rows: ImportMatchRow[];
  counts: { matched: number; ambiguous: number; unmatched: number };
  scoring_format: string;
}

/** Optional structured rows for the preset intake (Connected Rankings
 *  addendum §3.2). EXACTLY three fields by contract — a premium CSV's
 *  Value/Trend/PPG columns are never read, so they can never land here
 *  (risk R14: values never enter FTF; the import is order-only). */
export interface ImportRowHint {
  name: string;
  team: string | null;
  pos: string | null;
}

/** A 400 from the rows-bearing request means this backend predates the
 *  optional `rows` field (the two halves of this feature ship from separate
 *  worktrees). Anything else — auth, 5xx, timeout — is a real failure and
 *  must surface, not be silently retried into a lossier path. */
function isRowsUnsupported(e: unknown): boolean {
  return e instanceof ApiError && e.status === 400;
}

// POST /api/rankings/import-match — resolve pasted lines against the pool.
// Read-only (no board writes). Header scopes the format like reorder.
//
// `rows` (optional) is the preset path's ordered [{name, team, pos}] list;
// the backend takes it in precedence over `names` and uses the team/position
// hints to disambiguate same-name players. `names` is sent alongside as the
// same order in plain text, so a backend that ignores `rows` still parses an
// identical order — and a backend that REJECTS the field (400) is retried
// once on the pure text path below.
export async function importMatchRankings(
  names: string[],
  rows?: ImportRowHint[] | null,
) {
  const headers = await formatHeader();
  if (rows && rows.length) {
    try {
      return await api.post<ImportMatchResponse>(
        '/api/rankings/import-match',
        { names, rows },
        { headers },
      );
    } catch (e) {
      if (!isRowsUnsupported(e)) throw e;
      // fall through to the text-only path
    }
  }
  return api.post<ImportMatchResponse>(
    '/api/rankings/import-match',
    { names },
    { headers },
  );
}

// POST /api/rankings/import-apply — apply the reviewed order as the user's
// board. Backend semantics (docs/api-reference.md): imported ids land on
// top in imported order; every unlisted player keeps its relative current
// (consensus) order below, via the reorder permutation machinery.
export async function importApplyRankings(orderedPlayerIds: string[]) {
  return api.post<{
    ok: true;
    imported_count: number;
    board_count: number;
    scoring_format: string;
  }>(
    '/api/rankings/import-apply',
    { ordered_player_ids: orderedPlayerIds },
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
  demotedPids: string[] = [],
  // rookie-draft M2: a SCOPED save writes only part of the board. The
  // server answers it with the merged-band rule (merge the scoped pids into
  // the band's current full order, spread over the FULL merged list,
  // persist the scoped pids only) so a rookies-only save values each rookie
  // exactly as the equivalent full-band save would — and never respreads
  // the vets around them. It also does NOT mark the position complete:
  // `tiers_saved`/`all_done` are completeness markers feeding LeagueScreen's
  // ranked count, quicksetProgress's cache and #244 launch routing, and a
  // rookies-only pass has not completed a position. `via` is the forensic
  // tag the board-restore procedure keys off.
  //
  // `via:'quickset'` (2026-08-24) is the UNSCOPED Quick Set walk's tag. The
  // server has branched on it since analytics P0 (FR-20 `quickset_completed`,
  // `_note_ranking_method` → 'quickset') but no client ever sent it, so both
  // reads were dark for every mobile Quick Set save. It rides the same
  // whitelist as the rookie tags; an old server ignores unknown values by
  // falling back to 'tiers', so this is safe against any deploy skew.
  opts?: {
    scope?: RankScopeParam;
    via?: 'quickset' | 'rookie_tiers' | 'rookie_quickset' | 'rookie_anchors';
  },
) {
  // demoted_pids (#161): players the user explicitly passed over during a
  // Quick Set tier save — the backend pins them below every tier band
  // (unranked) instead of letting them silently keep their old tier. Under
  // scope this is bounded to the VISIBLE subset (operator decision O4): an
  // unshown vet is never demoted, because it was never on screen to pass over.
  return api.post<any>('/api/tiers/save', {
    position,
    tiers,
    cleared_pids: clearedPids,
    demoted_pids: demotedPids,
    ...(opts?.scope ? { scope: opts.scope } : {}),
    ...(opts?.via ? { via: opts.via } : {}),
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
export async function getAnchorPool(opts?: { scope?: RankScopeParam }) {
  const qs = opts?.scope ? `?${scopeQuery(opts.scope)}` : '';
  return api.get<RankingsResponse | ScopedEmpty>(
    `/api/rankings${qs}`,
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
//
// `via` (draft-extensions W1) names the SURFACE that asked, so a value set
// on the fly in the Draft Room is separable from a wizard pass. It is
// REQUEST-ONLY — the server whitelists it into `anchor_answered`'s props
// and the response is byte-unchanged. Omitting it sends today's exact
// body, so the wizard's call site is untouched.
export type AnchorVia = 'anchors' | 'draft_room';

export async function saveAnchor(
  playerId: string,
  anchor: AnchorKey,
  via?: AnchorVia,
) {
  return api.post<AnchorSaveResponse>(
    '/api/anchor/save',
    via ? { player_id: playerId, anchor, via } : { player_id: playerId, anchor },
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
