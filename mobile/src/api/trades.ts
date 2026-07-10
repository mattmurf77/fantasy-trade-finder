import { api } from './client';
import type { TradeCard, TradeJobSnapshot, TradeMatch, AwaitingTrade, Player } from '../shared/types';

export interface GenerateBody {
  league_id: string;
  fairness_threshold?: number;      // 0.5 – 1.0
  pinned_give_players?: string[];
  // FB-47 finder targeting: specific players the user wants to ACQUIRE.
  // Honored by the backend only when flag trade.finder_targeting is on;
  // every returned card's receive side then includes at least one of them.
  pinned_receive_players?: string[];
}

// NOTE: backend returns BARE ARRAYS for the trade endpoints — not
// `{trades: [...]}` / `{matches: [...]}` envelopes. The wrappers below
// normalize either shape so a future backend cleanup that adds an envelope
// won't break us either.

function asArray<T>(res: any): T[] {
  if (Array.isArray(res)) return res as T[];
  if (Array.isArray(res?.trades)) return res.trades as T[];
  if (Array.isArray(res?.matches)) return res.matches as T[];
  return [];
}

// ── Trade-card normalizer ────────────────────────────────────────────
// Backend (server.py:trade_card_to_dict) returns:
//   { trade_id, league_id, target_username, give[], receive[],
//     mismatch_score, fairness_score, composite_score, basis,
//     decision, expires_at, likes_you?, sweetener?, reasons? }
// Frontend (shared/types#TradeCard) wants:
//   { trade_id, league_id, give_player_ids[], receive_player_ids[],
//     give_players[], receive_players[], opponent_user_id,
//     opponent_username, match_score, fairness, reasons? }
// This adapter bridges the two so screen code never has to know about
// the legacy field names.
function normalizeTradeCard(raw: any): TradeCard {
  const give: Player[]    = Array.isArray(raw?.give_players) ? raw.give_players
                          : Array.isArray(raw?.give)         ? raw.give
                          : [];
  const receive: Player[] = Array.isArray(raw?.receive_players) ? raw.receive_players
                          : Array.isArray(raw?.receive)         ? raw.receive
                          : [];
  // Backend's `mismatch_score` is the human-facing "deal compellingness"
  // value — same field the legacy web reads. `match_score` was the type
  // we picked when scaffolding; keep that name internal.
  //
  // The web renders the raw mismatch as a number (e.g. "Match score 247"),
  // but the mobile UI treats `match_score` as a 0–100 percentage and feeds
  // it to a clamped StrengthBar. Without scaling, anything with a raw
  // mismatch ≥ 100 (i.e. essentially every surfaced trade — threshold is
  // 40 and good deals are 100–300+) renders as a maxed-out 100% bar.
  // Scale by /300 to match the same ceiling the backend's composite-score
  // math already uses (trade_service.py: `min(mismatch, 300) / 300`).
  const matchScore =
    typeof raw?.match_score    === 'number' ? raw.match_score
  : typeof raw?.mismatch_score === 'number' ? Math.min(100, Math.max(0, (raw.mismatch_score / 300) * 100))
  : 0;
  // `fairness_score` (0–1) is always serialized by the v2 backend; keep
  // the defensive fallback so cached/legacy snapshots without it still
  // render (UI hides the row when undefined).
  const fairness =
    typeof raw?.fairness       === 'number' ? raw.fairness
  : typeof raw?.fairness_score === 'number' ? raw.fairness_score
  : undefined as unknown as number;
  // v2 sweetener marker — { player_id, side } identifying a low-value
  // player (already present in give/receive) added to balance the deal.
  // Strictly validated so a malformed payload degrades to "no callout".
  const rawSweetener = raw?.sweetener;
  const sweetener =
    rawSweetener
    && typeof rawSweetener.player_id === 'string'
    && (rawSweetener.side === 'give' || rawSweetener.side === 'receive')
      ? { playerId: rawSweetener.player_id, side: rawSweetener.side as 'give' | 'receive' }
      : undefined;
  // FB-47 — counterparty positional fit (0–1). Backend serializes it only
  // when trade.finder_targeting is on AND the user expressed targets;
  // undefined hides the fit line entirely.
  const partnerFit =
    typeof raw?.partner_fit === 'number' ? raw.partner_fit : undefined;
  // Structured match context — only the string-array fields the fit-line
  // copy reads are kept; a malformed payload degrades to undefined.
  const rawCtx = raw?.match_context;
  const matchContext =
    rawCtx && typeof rawCtx === 'object'
      ? {
          user_needs: Array.isArray(rawCtx.user_needs)
            ? rawCtx.user_needs.filter((x: unknown) => typeof x === 'string')
            : undefined,
          opponent_surplus: Array.isArray(rawCtx.opponent_surplus)
            ? rawCtx.opponent_surplus.filter((x: unknown) => typeof x === 'string')
            : undefined,
        }
      : undefined;

  return {
    trade_id:           String(raw?.trade_id ?? ''),
    league_id:          String(raw?.league_id ?? ''),
    give_players:       give,
    receive_players:    receive,
    give_player_ids:    give.map((p) => p.id),
    receive_player_ids: receive.map((p) => p.id),
    opponent_user_id:   String(raw?.opponent_user_id ?? raw?.target_user_id ?? ''),
    opponent_username:  String(raw?.opponent_username ?? raw?.target_username ?? ''),
    match_score:        matchScore,
    fairness:           fairness,
    reasons:            Array.isArray(raw?.reasons) ? raw.reasons : undefined,
    // Backend injects `real_opponent` on streaming snapshots (generate +
    // status). Coerce to a strict boolean if present; leave undefined so
    // the card can distinguish "unknown" from a real "false" in legacy
    // response shapes that don't include the field.
    real_opponent:      typeof raw?.real_opponent === 'boolean' ? raw.real_opponent : undefined,
    // v2 fields — all defensively defaulted so legacy payloads behave
    // exactly as before:
    //   basis     — 'consensus' only when explicitly sent; anything else
    //               (missing, typo, legacy) is 'divergence'.
    //   likesYou  — backend serializes `likes_you` only when true.
    //   sweetener — validated above; undefined when absent/malformed.
    basis:              raw?.basis === 'consensus' ? 'consensus' : 'divergence',
    likesYou:           raw?.likes_you === true,
    sweetener,
    partner_fit:        partnerFit,
    match_context:      matchContext,
  };
}

// Backend returns a TradeJobSnapshot for both /api/trades/generate and
// /api/trades/status. Both run cards through the same normalizer so
// downstream code keeps using the unified TradeCard shape.
function normalizeJobSnapshot(raw: any): TradeJobSnapshot {
  const cards = Array.isArray(raw?.cards) ? raw.cards.map(normalizeTradeCard) : [];
  return {
    job_id:          String(raw?.job_id ?? ''),
    status:          raw?.status === 'complete' ? 'complete'
                   : raw?.status === 'error'    ? 'error'
                   : 'running',
    cards,
    opponents_done:  Number(raw?.opponents_done ?? 0)  || 0,
    opponents_total: Number(raw?.opponents_total ?? 0) || 0,
    error:           raw?.error ?? null,
  };
}

// POST /api/trades/generate — kicks off trade discovery for the active league.
// Returns a job snapshot; if status==='running', poll getTradeStatus(job_id).
export async function generateTrades(body: GenerateBody): Promise<TradeJobSnapshot> {
  const res = await api.post<any>('/api/trades/generate', body);
  return normalizeJobSnapshot(res);
}

// GET /api/trades/status?job_id=X — cheap dict lookup; the request thread
// just reads the in-memory job state and returns the current cards.
export async function getTradeStatus(jobId: string): Promise<TradeJobSnapshot> {
  const res = await api.get<any>(
    `/api/trades/status?job_id=${encodeURIComponent(jobId)}`,
  );
  return normalizeJobSnapshot(res);
}

// GET /api/trades?league_id=X — cached most-recent generated trades.
// Separate from the streaming job snapshots; this is the long-tail "show
// me undecided cards" view used outside the Find-a-Trade flow.
export async function getRecentTrades(leagueId: string): Promise<TradeCard[]> {
  const res = await api.get<any>(
    `/api/trades?league_id=${encodeURIComponent(leagueId)}`,
  );
  return asArray<any>(res).map(normalizeTradeCard);
}

// POST /api/trades/swipe  body: { trade_id, decision: 'like' | 'pass' }
export async function swipeTrade(
  card: TradeCard,
  decision: 'like' | 'pass',
) {
  // FB-46: echo the card context so the server can reconstruct the card
  // when its in-memory deck was lost (Render deploy / session re-init)
  // instead of failing every swipe with "Unknown trade_id".
  return api.post<any>('/api/trades/swipe', {
    trade_id:           card.trade_id,
    decision,
    league_id:          card.league_id || undefined,
    give_player_ids:    card.give_player_ids,
    receive_player_ids: card.receive_player_ids,
    target_user_id:     card.opponent_user_id || undefined,
    target_username:    card.opponent_username || undefined,
  });
}

// POST /api/trades/flag — "this is a bad trade" (feedback #85). Distinct
// from a pass: a flag means "the engine got this one wrong" and lands in a
// review table the owner uses to iterate on the trade logic. Server-side
// idempotent per (user, league, give set, receive set), so re-flagging the
// same package is safe. Card context + telemetry are echoed so the server
// can persist a reviewable snapshot even after its in-memory deck is gone.
export async function flagBadTrade(card: TradeCard, reason?: string) {
  return api.post<any>('/api/trades/flag', {
    trade_id:           card.trade_id,
    league_id:          card.league_id || undefined,
    give_player_ids:    card.give_player_ids,
    receive_player_ids: card.receive_player_ids,
    target_user_id:     card.opponent_user_id || undefined,
    target_username:    card.opponent_username || undefined,
    fairness_score:     typeof card.fairness === 'number' ? card.fairness : undefined,
    basis:              card.basis,
    reason:             reason || undefined,
  });
}

// ── Trade-match normalizer ───────────────────────────────────────────
// Backend (database.py:load_matches + server.py enrichment) returns:
//   { match_id (int), league_id, league_name?, partner_id, partner_name,
//     my_give[], my_receive[], my_give_names?[], my_receive_names?[],
//     matched_at, status, my_decision, my_decided_at,
//     their_decision, their_decided_at }
// Frontend (shared/types#TradeMatch) wants:
//   { match_id (string), league_id, league_name?, my_side_player_ids[],
//     their_side_player_ids[], my_side_player_names?[],
//     their_side_player_names?[], counterparty_user_id,
//     counterparty_username, created_at, my_disposition, their_disposition }
// Backend uses 'accept'/'decline'; frontend type uses 'accepted'/'declined'
// — we translate both ways here so each layer keeps its native vocabulary.
function normalizeTradeMatch(raw: any): TradeMatch {
  const decisionToDisposition = (
    d: unknown,
  ): 'pending' | 'accepted' | 'declined' | undefined => {
    if (d === 'accept'   || d === 'accepted') return 'accepted';
    if (d === 'decline'  || d === 'declined') return 'declined';
    if (d === 'pending')                      return 'pending';
    return undefined;
  };
  return {
    match_id:                    String(raw?.match_id ?? ''),
    league_id:                   String(raw?.league_id ?? ''),
    league_name:                 raw?.league_name || undefined,
    my_side_player_ids:          Array.isArray(raw?.my_give)    ? raw.my_give    : [],
    their_side_player_ids:       Array.isArray(raw?.my_receive) ? raw.my_receive : [],
    my_side_player_names:        Array.isArray(raw?.my_give_names)        ? raw.my_give_names        : undefined,
    their_side_player_names:     Array.isArray(raw?.my_receive_names)     ? raw.my_receive_names     : undefined,
    my_side_player_teams:        Array.isArray(raw?.my_give_teams)        ? raw.my_give_teams        : undefined,
    their_side_player_teams:     Array.isArray(raw?.my_receive_teams)     ? raw.my_receive_teams     : undefined,
    my_side_player_positions:    Array.isArray(raw?.my_give_positions)    ? raw.my_give_positions    : undefined,
    their_side_player_positions: Array.isArray(raw?.my_receive_positions) ? raw.my_receive_positions : undefined,
    counterparty_user_id:        String(raw?.partner_id ?? ''),
    counterparty_username:       String(raw?.partner_name ?? raw?.partner_id ?? ''),
    created_at:                  String(raw?.matched_at ?? raw?.created_at ?? ''),
    my_disposition:              decisionToDisposition(raw?.my_decision),
    their_disposition:           decisionToDisposition(raw?.their_decision),
  };
}

// GET /api/trades/matches/all — matches across EVERY league the user is in,
// enriched with league_name + player display names. Used by the mobile
// Matches tab; the legacy single-league /api/trades/matches still exists
// for the web app.
export async function getAllMatches(): Promise<TradeMatch[]> {
  const res = await api.get<any>('/api/trades/matches/all');
  return asArray<any>(res).map(normalizeTradeMatch);
}

// GET /api/trades/matches  — single-league mutual-match inbox (legacy).
export async function getMatches(): Promise<TradeMatch[]> {
  const res = await api.get<any>('/api/trades/matches');
  return asArray<any>(res).map(normalizeTradeMatch);
}

// POST /api/trades/matches/:id/disposition
// Backend body shape: { decision: 'accept' | 'decline' }
// Translate from the frontend's 'accepted'/'declined' vocabulary at the
// API edge so screen code keeps its existing wording.
export async function setMatchDisposition(
  matchId: string,
  disposition: 'accepted' | 'declined',
) {
  const decision = disposition === 'accepted' ? 'accept' : 'decline';
  return api.post<any>(`/api/trades/matches/${matchId}/disposition`, {
    decision,
  });
}

// POST /api/trades/matches/:id/dismiss
// Archives a mutual match from the caller's inbox — persisted, per-user, and
// ELO-neutral (NOT a decline). Powers the "Dismiss" CTA on the Matches tab.
export async function dismissMatch(matchId: string) {
  return api.post<any>(`/api/trades/matches/${matchId}/dismiss`, {});
}

// GET /api/trades/liked — liked trades. Backend returns a bare array of
// trade dicts; we expose both the count (what badges care about) and the
// raw list (so a future inbox screen can render them).
export async function getLikedTrades(): Promise<{ liked_count: number; trades: TradeCard[] }> {
  const res = await api.get<any>('/api/trades/liked');
  const trades = asArray<any>(res).map(normalizeTradeCard);
  return { liked_count: trades.length, trades };
}

// ── Awaiting-trade normalizer ────────────────────────────────────────
// Backend (server.py: /api/trades/awaiting) returns:
//   { trade_id, league_id, league_name?, partner_id, partner_name,
//     my_give[], my_receive[], my_give_names?[], my_receive_names?[],
//     liked_at }
// Frontend (shared/types#AwaitingTrade) uses the same vocabulary as
// TradeMatch so the same tile component can render either.
function normalizeAwaitingTrade(raw: any): AwaitingTrade {
  return {
    trade_id:                String(raw?.trade_id ?? ''),
    league_id:               String(raw?.league_id ?? ''),
    league_name:             raw?.league_name || undefined,
    my_side_player_ids:      Array.isArray(raw?.my_give)    ? raw.my_give    : [],
    their_side_player_ids:   Array.isArray(raw?.my_receive) ? raw.my_receive : [],
    my_side_player_names:    Array.isArray(raw?.my_give_names)    ? raw.my_give_names    : undefined,
    their_side_player_names: Array.isArray(raw?.my_receive_names) ? raw.my_receive_names : undefined,
    counterparty_user_id:    String(raw?.partner_id ?? ''),
    counterparty_username:   String(raw?.partner_name ?? raw?.partner_id ?? ''),
    liked_at:                String(raw?.liked_at ?? ''),
  };
}

// GET /api/trades/awaiting — trades the user liked that haven't matured
// into mutual matches yet. Used by the "Awaiting them" segment on the
// Matches tab so users can see their one-sided likes.
export async function getAwaitingTrades(): Promise<AwaitingTrade[]> {
  const res = await api.get<any>('/api/trades/awaiting');
  return asArray<any>(res).map(normalizeAwaitingTrade);
}
