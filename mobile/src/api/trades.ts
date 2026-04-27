import { api } from './client';
import type { TradeCard, TradeJobSnapshot, TradeMatch, Player } from '../shared/types';

export interface GenerateBody {
  league_id: string;
  fairness_threshold?: number;      // 0.5 – 1.0
  pinned_give_players?: string[];
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
//     mismatch_score, composite_score, decision, expires_at, reasons? }
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
  const matchScore =
    typeof raw?.match_score    === 'number' ? raw.match_score
  : typeof raw?.mismatch_score === 'number' ? raw.mismatch_score
  : 0;
  // `fairness` may not be present (backend doesn't expose fairness_score
  // today). Pass through whatever we get; UI hides the row when undefined.
  const fairness =
    typeof raw?.fairness       === 'number' ? raw.fairness
  : typeof raw?.fairness_score === 'number' ? raw.fairness_score
  : undefined as unknown as number;

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
  tradeId: string,
  decision: 'like' | 'pass',
) {
  return api.post<any>('/api/trades/swipe', { trade_id: tradeId, decision });
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
    match_id:                String(raw?.match_id ?? ''),
    league_id:               String(raw?.league_id ?? ''),
    league_name:             raw?.league_name || undefined,
    my_side_player_ids:      Array.isArray(raw?.my_give)    ? raw.my_give    : [],
    their_side_player_ids:   Array.isArray(raw?.my_receive) ? raw.my_receive : [],
    my_side_player_names:    Array.isArray(raw?.my_give_names)    ? raw.my_give_names    : undefined,
    their_side_player_names: Array.isArray(raw?.my_receive_names) ? raw.my_receive_names : undefined,
    counterparty_user_id:    String(raw?.partner_id ?? ''),
    counterparty_username:   String(raw?.partner_name ?? raw?.partner_id ?? ''),
    created_at:              String(raw?.matched_at ?? raw?.created_at ?? ''),
    my_disposition:          decisionToDisposition(raw?.my_decision),
    their_disposition:       decisionToDisposition(raw?.their_decision),
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

// GET /api/trades/liked — liked trades. Backend returns a bare array of
// trade dicts; we expose both the count (what badges care about) and the
// raw list (so a future inbox screen can render them).
export async function getLikedTrades(): Promise<{ liked_count: number; trades: TradeCard[] }> {
  const res = await api.get<any>('/api/trades/liked');
  const trades = asArray<any>(res).map(normalizeTradeCard);
  return { liked_count: trades.length, trades };
}
