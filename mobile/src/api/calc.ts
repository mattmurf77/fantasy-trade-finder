// Manual Trade Calculator — open consensus endpoints (no session required).
// Server side: backend/server.py trade_calc_values_route / trade_evaluate_route,
// which reuse the trade engine's universal pool + elo_to_value + _fairness_v3
// so calculator numbers always match the finder's.

import { apiRequest } from './client';
import type { PickSource } from './pickAssignment';
import type { ScoringFormat, StarterImpactSlot, Tier } from '../shared/types';

export interface CalcValueRow {
  id: string;
  name: string;
  position: string;
  team: string | null;
  age: number | null;
  /** Consensus dynasty value (elo_to_value over the pool's seed Elo). */
  value: number;
  /** #263 — pick-value ladder tier (docs/cross-client-invariants.md) the
   *  player's RAW seed Elo lands in, via the backend's canonical
   *  RankingService.tier_for_elo. NOT derived from `value` above — `value`
   *  is elo_to_value-transformed and on a different scale than the tier
   *  bands. Reuse this field for tier display; never re-derive a tier from
   *  `value` client-side. */
  tier: Tier;
}

export type CalcVerdict = 'even' | 'fair' | 'unfair';

// #215 — the user-level stud-tax setting (see api/accountPrefs.ts for the
// GET/PUT endpoints; evaluate echoes the mode it priced with).
export type StudTaxMode = 'market' | 'heavy' | 'off';

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

// One-tap evener assets (DynastyGM teardown 2026-07-26): concrete assets the
// WINNING side can add to what they give to balance an uneven trade. Mode B
// draws them from that side's real roster + owned picks (window around the
// gap, closest first, ≤3 singles + at most one 2-piece package); Mode A falls
// back to the single generic pick nearest the gap. Absent when the trade is
// even/one-sided (and on old servers).
export interface CalcEvener {
  id: string;
  name: string; // pick assets carry their pick label ("2027 1st")
  position: string; // 'PICK' for picks, 'PKG' for a 2-piece package
  team: string | null;
  value: number;
  is_pick: boolean;
  /** 2-piece combo row — `ids` are the pieces; the + button adds both. */
  is_package?: boolean;
  ids?: string[];
  /** draft-extensions W3 M-C (D17): provenance for an owned-pick evener.
   *  `source === 'user'` means a leaguemate asserted this pick's ownership
   *  on the ESPN grid — the evener chip and the swap sheet must say so and
   *  offer the correction. Absent on players, packages, platform-owned
   *  picks and any pre-M-C server. `id` IS the `pick_id` for a single-pick
   *  evener; `pick_id` is carried anyway so a package row could name the
   *  asserted piece without the client parsing `<a>+<b>`. */
  source?: PickSource | null;
  pick_id?: string | null;
  season?: number | null;
}

// Itemized value adjustments (DynastyDealer teardown 2026-07-26): why a
// side's displayed package value differs from the naive sum of its asset
// values. Only adjustments the evaluate path actually applies appear —
// package_depth (lesser assets count below face value) and consolidation
// (crown premium for the outnumbered side). Consensus-based in both modes;
// naive_totals[side] + Σ amounts == the displayed side value.
export interface CalcAdjustment {
  key: string; // 'package_depth' | 'consolidation'
  label: string;
  /** Signed value effect vs the side's naive sum (same units as totals). */
  amount: number;
  /** One plain-language sentence of rationale. */
  why: string;
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
  /** Present on an uneven two-sided read; also on a one-sided Mode B read
   *  when the caller opted into `one_sided_eveners` (#264). See CalcEvener. */
  eveners?: CalcEvener[];
  /** Present only when at least one adjustment moved a side's value
   *  (absent on old servers); see CalcAdjustment. */
  adjustments?: { give: CalcAdjustment[]; receive: CalcAdjustment[] };
  /** Naive per-side sums ("sum of parts") — rides along with adjustments. */
  naive_totals?: { give: number; receive: number };
  /** #215 — which stud-tax mode priced this read ('market' default |
   *  'heavy' legacy | 'off' = no adjustments). Absent on old servers. */
  stud_tax_mode?: StudTaxMode;
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
  // #215: the session token rides along when present (no longer skipAuth)
  // so the server can apply the caller's stored stud_tax_mode; the
  // endpoint itself stays public — signed-out calls work unchanged.
  return apiRequest('/api/trade/evaluate', {
    method: 'POST',
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
  // #191 — additive derived-board markers (absent on old servers): true
  // when that side's board was value-mapped at read time from the OTHER
  // scoring format because this format has no explicit rankings.
  opponent_board_derived?: boolean;
  opponent_board_derived_from?: string | null;
  your_board_derived?: boolean;
  your_board_derived_from?: string | null;
  your_give_value: number;
  your_receive_value: number;
  their_give_value: number;
  their_receive_value: number;
  your_value_delta: number; // by YOUR board (positive = you gain)
  their_value_delta: number; // by THEIR board (positive = they gain)
  mutual_gain: boolean;
  /** Starter impact (DTF teardown 2026-07-27, Mode B only — absent on old
   *  servers and when the league's lineup-slot template is unknown):
   *  optimal-lineup value delta before vs after the trade, per side
   *  (positive = that side's STARTING lineup gets stronger; consensus
   *  values, derived value-optimal lineup — no per-week lineup data),
   *  plus one plain-language caller-centric sentence. #238 adds `slots` —
   *  the CALLER's per-slot before/after breakdown (template order; absent
   *  on pre-#238 servers, so the client falls back to the sentence). */
  starter_impact?: {
    your_delta: number;
    their_delta: number;
    note: string;
    slots?: StarterImpactSlot[];
  };
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

// Deck swap-suggestions (2026-07-27 player-changer): evaluate a card's trade
// MINUS one asset to get replacement candidates (`eveners`) for it. Same Mode
// B call as evaluateTradeInLeague plus `one_sided_eveners: true` — when the
// removal empties a side (a 1-for-1 card) the server builds eveners for the
// emptied side anyway, sized against the other side's package value. Old
// servers ignore the extra key and simply return no eveners on one-sided
// reads (the client degrades to its honest empty state).
export async function evaluateForSwapSuggestions(
  givePlayerIds: string[],
  receivePlayerIds: string[],
  format: ScoringFormat,
  leagueId: string,
  opponentUserId: string,
  signal?: AbortSignal,
): Promise<CalcEvaluationInLeague> {
  return apiRequest('/api/trade/evaluate', {
    method: 'POST',
    signal,
    body: {
      give_player_ids: givePlayerIds,
      receive_player_ids: receivePlayerIds,
      scoring_format: format,
      league_id: leagueId,
      opponent_user_id: opponentUserId,
      one_sided_eveners: true,
    },
  });
}

export async function evaluateTradeInLeague(
  givePlayerIds: string[],
  receivePlayerIds: string[],
  format: ScoringFormat,
  leagueId: string,
  opponentUserId: string,
  signal?: AbortSignal,
  // #264 — opt into the server's one-sided evener build (same key
  // evaluateForSwapSuggestions sends): with exactly one side filled, the
  // response carries candidate assets for the EMPTY side from its owner's
  // roster + owned picks, sized against the filled side's package value.
  // Two-sided reads are unaffected (server branch is gated on
  // `bool(give) != bool(recv)`); old servers ignore the key.
  oneSidedEveners?: boolean,
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
      ...(oneSidedEveners ? { one_sided_eveners: true } : {}),
    },
  });
}
