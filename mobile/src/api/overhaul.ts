// Team overhaul (flag `overhaul.enabled`) — the durable multi-trade plan:
// outlook → eligible pool → like/pass review → compatible roadmaps → per-package
// priority tiers → one confirmed send batch → resume as responses arrive.
//
// Contract: docs/plans/team-overhaul/BUILD-CONTRACT.md (§5 shapes, §7 routes).
// This module is the ONE definition of the wire types; screens import from
// here and never re-declare them. Plain async functions + exported types, no
// React and no react-query hooks (the screen owns the query), per api/README.
//
// Isolation rules pinned by tests/check-team-overhaul.js: nothing in the
// overhaul surface writes league preferences, player tiers, or swipe/taste
// learning. Likes here are assembly input, not Elo signal.

import { apiRequest } from './client';
import { normalizeTradeCard } from './trades';
import type { TradeCard } from '../shared/types';

export type OverhaulOutlook = 'push_all_in' | 'blow_it_up';

export type OverhaulStatus =
  | 'setup'
  | 'reviewing'
  | 'assembled'
  | 'executing'
  | 'complete'
  | 'archived';

export type RebuildReturn = 'picks' | 'young_players' | 'mixed';

export interface PickBudget {
  max_picks: number;
  max_round: number;
  seasons: number[];
}

export interface OverhaulSettings {
  outlook: OverhaulOutlook | null;
  /** Mixed asset ids: player ids and FTF pick ids, same convention as give_player_ids. */
  eligible_asset_ids: string[];
  preferred_positions: string[];
  rebuild_return: RebuildReturn | null;
  pick_budget: PickBudget | null;
  target_package_count: 4 | 5;
}

export type RecoveryState =
  | 'owned'
  | 'missing_with_known_holder'
  | 'unknown'
  | 'unsupported'
  | 'not_yet_available';

export interface RecoveryRequirement {
  applicable: boolean;
  season: number | null;
  state: RecoveryState;
  pick_id: string | null;
  holder_user_id: string | null;
  holder_username: string | null;
  resolved: boolean;
  draft_order_rule: 'unknown' | string;
}

export type ShortfallReason =
  | 'insufficient_likes'
  | 'overlapping_sells'
  | 'competing_incoming'
  | 'no_return_supply'
  | 'recovery_unresolved'
  | 'roster_limitation'
  | 'stale_ownership'
  | 'budget_restriction'
  | 'search_exhausted';

export interface GenerationSummary {
  state: 'idle' | 'completed' | 'failed';
  revision: number;
  new_offers: number;
  total_offers: number;
  pool_rejections: number;
  shortfall_reason: ShortfallReason | null;
  budget_exhausted: boolean;
}

export type OfferDecision = 'like' | 'pass' | 'undecided';

export interface Offer {
  offer_id: string;
  is_recovery: boolean;
  decision: OfferDecision;
  availability: 'fresh' | 'stale';
  counterparty_user_id: string;
  counterparty_username: string;
  give_ids: string[];
  receive_ids: string[];
  /** The public trade-card dict exactly as the deck emits it; render with TradeCard. */
  card: TradeCard;
}

export interface PriorityTier {
  tier: number;
  offer_ids: string[];
}

export type PackageStatus = 'open' | 'pending' | 'complete' | 'blocked';

export interface Package {
  package_id: string;
  give_ids: string[];
  reason: 'outlook_move' | 'recover_own_first';
  /** 1 only for recover_own_first ("Priority 1: Recover your first"), else 0. Advisory. */
  advisory_rank: number;
  tiers: PriorityTier[];
  status: PackageStatus;
}

export type ValidationCode =
  | 'give_overlap'
  | 'receive_overlap'
  | 'asset_not_owned'
  | 'counterparty_asset_not_owned'
  | 'pool_violation'
  | 'capacity_exceeded'
  | 'lineup_illegal'
  | 'offer_stale'
  | 'offer_not_liked'
  | 'recovery_unresolved'
  | 'tier_duplicate_counterparty'
  | 'asset_reserved'
  | 'depth_reduced'
  | 'pick_unsupported_on_platform'
  | 'reconnect_required';

export interface ValidationItem {
  code: ValidationCode | string;
  package_id?: string;
  offer_id?: string;
  message: string;
}

export interface ValidationReceipt {
  ok: boolean;
  checked_at: string;
  blockers: ValidationItem[];
  warnings: ValidationItem[];
  unknowns: string[];
  outgoing_ids: string[];
  incoming_ids: string[];
}

export interface RoadmapSummary {
  outgoing_ids: string[];
  incoming_ids: string[];
  counterparties: string[];
  unused_eligible_ids: string[];
  score: number;
  diversity_key: string;
}

export interface RoadmapView {
  roadmap_id: string;
  version: number;
  packages: Package[];
  compat: ValidationReceipt;
  summary: RoadmapSummary;
  rank: number;
  offers: Record<string, Offer>;
}

export type AttemptState =
  | 'queued'
  | 'sending'
  | 'proposed'
  | 'send_failed'
  | 'outcome_unknown'
  | 'accepted'
  | 'declined'
  | 'expired'
  | 'withdrawn'
  | 'invalidated'
  | 'resolved_elsewhere'
  | 'stale';

export const LIVE_ATTEMPT_STATES: ReadonlySet<AttemptState> = new Set<AttemptState>([
  'queued',
  'sending',
  'proposed',
  'outcome_unknown',
]);

export type AttemptStateSource = 'server' | 'provider' | 'ownership_refresh' | 'user_reported';

export interface AttemptView {
  attempt_id: string;
  batch_id: string;
  package_id: string;
  tier: number;
  offer_id: string;
  state: AttemptState;
  state_source: AttemptStateSource;
  provider_transaction_id?: string | null;
  error?: { code: string; message?: string } | null;
  created_at: string;
  updated_at: string;
  observed_at?: string | null;
}

export interface Capabilities {
  platform: string;
  can_propose: boolean;
  /** False on ESPN: its trade API takes players only, so an offer with a pick is a blocker. */
  can_propose_picks: boolean;
  can_read_terminal_status: false;
  can_withdraw: false;
  supports_conflicting_offer_race: 'unverified' | 'supported' | 'unsupported';
  auth_state: 'linked' | 'unlinked' | 'expired' | 'unverified' | 'n/a';
  checked_at: string;
}

export interface AssetView {
  id: string;
  kind: 'player' | 'pick';
  name: string;
  position: string;
  team?: string | null;
  age?: number | null;
  value: number;
  /** Pick label such as "2027 1st"; absent for players. */
  label?: string;
  recommended: boolean;
  reason?: string | null;
}

export interface ReviewProgress {
  decided: number;
  total: number;
  liked: number;
}

export interface OverhaulView {
  overhaul_id: string;
  league_id: string;
  platform: string;
  status: OverhaulStatus;
  revision: number;
  settings: OverhaulSettings;
  snapshot: { captured_at: string; season: number | null; picks_supported: boolean };
  recovery: RecoveryRequirement;
  generation: GenerationSummary;
  selected_roadmap_id: string | null;
  roadmaps: RoadmapView[];
  progress: ReviewProgress;
  attempts: AttemptView[];
  capabilities: Capabilities;
  eligible_assets: AssetView[];
}

export interface PrepareView {
  prepare_token: string;
  expires_at: string;
  summary_hash: string;
  receipt: ValidationReceipt;
  counts: { offers: number; packages: number; max_accepted: number };
  races: { package_id: string; offer_ids: string[]; counterparties: string[] }[];
  capabilities: Capabilities;
  handoff: { mode: 'send' | 'copy'; text?: string };
}

export interface SendResult {
  batch_id: string;
  attempts: AttemptView[];
}

const BASE = '/api/overhauls';
const enc = encodeURIComponent;

// ── Wire normalization ───────────────────────────────────────────────
// The server's `Offer.card` is the RAW `trade_card_to_dict` dict
// (backend/server.py): players under `give` / `receive`, the opponent under
// `target_user_id` / `target_username`, fairness under `fairness_score`
// (0–1) and match strength under `mismatch_score`. The client `TradeCard`
// type wants `give_players` / `receive_players` / `opponent_*` / `fairness` /
// `match_score`. The deck already bridges exactly that dict with
// `normalizeTradeCard`, so every fetcher below runs its offers through it
// HERE, at the fetch boundary — screens then read a real TradeCard and never
// see the legacy keys (TestFlight 1.17.2: empty chips + `undefined.map`
// render crashes on roadmaps/priorities came from reading the raw dict).

function normalizeOffer(raw: any): Offer {
  const card = normalizeTradeCard(raw?.card);
  const giveIds: string[] = Array.isArray(raw?.give_ids) ? raw.give_ids : [];
  const receiveIds: string[] = Array.isArray(raw?.receive_ids) ? raw.receive_ids : [];
  return {
    ...(raw as Offer),
    give_ids: giveIds,
    receive_ids: receiveIds,
    card: {
      ...card,
      // The deck's normalizer blanks ids it can't derive; the offer row
      // itself carries them, so keep those so nothing keyed on the card
      // breaks when a player list is missing.
      trade_id: card.trade_id || String(raw?.offer_id ?? ''),
      give_player_ids: card.give_players.length ? card.give_player_ids : giveIds,
      receive_player_ids: card.receive_players.length ? card.receive_player_ids : receiveIds,
      opponent_user_id: card.opponent_user_id || String(raw?.counterparty_user_id ?? ''),
      opponent_username: card.opponent_username || String(raw?.counterparty_username ?? ''),
    },
  };
}

function normalizeRoadmap(raw: any): RoadmapView {
  const offers: Record<string, Offer> = {};
  const src = raw?.offers && typeof raw.offers === 'object' ? raw.offers : {};
  for (const [id, o] of Object.entries(src)) offers[id] = normalizeOffer(o);
  return { ...(raw as RoadmapView), offers };
}

function normalizeOverhaulView(raw: any): OverhaulView {
  const roadmaps = Array.isArray(raw?.roadmaps) ? raw.roadmaps.map(normalizeRoadmap) : [];
  return { ...(raw as OverhaulView), roadmaps };
}

export async function getActiveOverhaul(
  leagueId: string,
  signal?: AbortSignal,
): Promise<{ active: OverhaulView | null }> {
  const res: any = await apiRequest(`${BASE}?league_id=${enc(leagueId)}`, { signal });
  return { ...res, active: res?.active ? normalizeOverhaulView(res.active) : null };
}

export async function getOverhaul(overhaulId: string, signal?: AbortSignal): Promise<OverhaulView> {
  return normalizeOverhaulView(await apiRequest(`${BASE}/${enc(overhaulId)}`, { signal }));
}

export async function createOverhaul(body: {
  league_id: string;
  client_key: string;
}): Promise<OverhaulView> {
  return normalizeOverhaulView(await apiRequest(BASE, { method: 'POST', body }));
}

export async function updateOverhaulSettings(
  overhaulId: string,
  body: { revision: number; settings: Partial<OverhaulSettings> },
): Promise<OverhaulView> {
  return normalizeOverhaulView(
    await apiRequest(`${BASE}/${enc(overhaulId)}/settings`, { method: 'PUT', body }),
  );
}

export async function generateOffers(
  overhaulId: string,
  body: { revision: number },
): Promise<{ generation: GenerationSummary; offers: Offer[] }> {
  const res: any = await apiRequest(`${BASE}/${enc(overhaulId)}/generate`, { method: 'POST', body });
  return { ...res, offers: Array.isArray(res?.offers) ? res.offers.map(normalizeOffer) : [] };
}

export async function getOffers(
  overhaulId: string,
  decision: OfferDecision | 'all' = 'undecided',
  signal?: AbortSignal,
): Promise<{ offers: Offer[]; progress: ReviewProgress }> {
  const res: any = await apiRequest(`${BASE}/${enc(overhaulId)}/offers?decision=${decision}`, { signal });
  return { ...res, offers: Array.isArray(res?.offers) ? res.offers.map(normalizeOffer) : [] };
}

export async function postDecisions(
  overhaulId: string,
  body: {
    revision: number;
    decisions: { offer_id: string; decision: OfferDecision; client_key: string }[];
  },
): Promise<{ progress: ReviewProgress }> {
  return apiRequest(`${BASE}/${enc(overhaulId)}/decisions`, { method: 'POST', body });
}

export async function assembleRoadmaps(
  overhaulId: string,
  body: { revision: number },
): Promise<{ roadmaps: RoadmapView[]; shortfall: { reason: ShortfallReason; detail?: string } | null }> {
  const res: any = await apiRequest(`${BASE}/${enc(overhaulId)}/assemble`, { method: 'POST', body });
  return { ...res, roadmaps: Array.isArray(res?.roadmaps) ? res.roadmaps.map(normalizeRoadmap) : [] };
}

export async function selectRoadmap(
  overhaulId: string,
  roadmapId: string,
  body: { version: number },
): Promise<OverhaulView> {
  return normalizeOverhaulView(
    await apiRequest(`${BASE}/${enc(overhaulId)}/roadmaps/${enc(roadmapId)}/select`, {
      method: 'PUT',
      body,
    }),
  );
}

export async function savePriorities(
  overhaulId: string,
  roadmapId: string,
  body: { version: number; package_id: string; tiers: PriorityTier[] },
): Promise<RoadmapView> {
  return normalizeRoadmap(
    await apiRequest(`${BASE}/${enc(overhaulId)}/roadmaps/${enc(roadmapId)}/priorities`, {
      method: 'PUT',
      body,
    }),
  );
}

export async function prepareSend(
  overhaulId: string,
  roadmapId: string,
  body: { version: number; offer_ids: string[] },
): Promise<PrepareView> {
  return apiRequest(`${BASE}/${enc(overhaulId)}/roadmaps/${enc(roadmapId)}/prepare-send`, {
    method: 'POST',
    body,
  });
}

export async function sendBatch(
  overhaulId: string,
  body: { prepare_token: string; summary_hash: string; version: number; idempotency_key: string },
): Promise<SendResult> {
  return apiRequest(`${BASE}/${enc(overhaulId)}/send`, { method: 'POST', body });
}

// Throttled server-side to one call per 15 s per overhaul: a second call inside the window is 429 `rate_limited`.
export async function refreshOverhaul(overhaulId: string): Promise<OverhaulView> {
  return normalizeOverhaulView(
    await apiRequest(`${BASE}/${enc(overhaulId)}/refresh`, { method: 'POST', body: {} }),
  );
}

export async function assertAttemptStatus(
  overhaulId: string,
  attemptId: string,
  body: { state: 'declined' | 'withdrawn' | 'expired'; note?: string },
): Promise<AttemptView> {
  return apiRequest(`${BASE}/${enc(overhaulId)}/attempts/${enc(attemptId)}/status`, {
    method: 'POST',
    body,
  });
}

/** Human label for an attempt state; the plan screen must cover every member. */
export const ATTEMPT_STATE_LABEL: Record<AttemptState, string> = {
  queued: 'Queued',
  sending: 'Sending',
  proposed: 'Sent, awaiting reply',
  send_failed: 'Send failed',
  outcome_unknown: 'Send status unknown',
  accepted: 'Accepted',
  declined: 'Declined',
  expired: 'Expired',
  withdrawn: 'Withdrawn',
  invalidated: 'No longer valid',
  resolved_elsewhere: 'Resolved in the platform',
  stale: 'Needs refresh',
};
