// Type definitions that mirror the backend's response shapes.
// Source of truth: backend/server.py routes + backend/database.py models.
// These types are deliberately loose-ish — extend as real responses reveal
// more fields. Intent is a tight enough safety net to catch typos; not
// a legal contract.

// CalcGap is the pick-denominated gap shape shared by the calculator
// (/api/trade/evaluate) and the deck cards' TradeValueBar. Type-only import
// (erased at build), so the calc.ts ↔ types.ts reference is compile-time only.
import type { CalcGap } from '../api/calc';

export type ScoringFormat = '1qb_ppr' | 'sf_tep';
export type Position = 'QB' | 'RB' | 'WR' | 'TE';
// Pick-value tier ladder (2026-07-12 8-tier ladder, #117) — tier keys read
// directly in draft-pick terms (docs/cross-client-invariants.md).
export type Tier =
  | 'firsts_4plus'
  | 'firsts_3'
  | 'firsts_2'
  | 'first_1'
  | 'second'
  | 'third'
  | 'fourth'
  | 'waivers';

export interface Player {
  id: string;
  name: string;
  position: Position | string;
  team?: string | null;
  age?: number | null;
  years_experience?: number | null;
  pick_value?: number | null;      // for draft picks
  injury_status?: string | null;
  search_rank?: number | null;
  adp?: number | null;
  // FB-147 — true when this player is on the Sleeper trade block in the
  // card's league (flag sleeper.trade_block). Backend omits when absent.
  on_block?: boolean;
}

export interface Trio {
  player_a: Player;
  player_b: Player;
  player_c: Player;
  position?: Position | null;
  reasoning?: string;
  // Optional fields emitted only when the corresponding flag is on
  community_signal?: {
    first_pick_pct?: number;        // % of rankers who pick the consensus #1
    second_pick_pct?: number;
  };
  is_qc_trio?: boolean;             // quality-control compliment trio
  qc_expected_order?: string[];     // [pid, pid, pid] — the "correct" consensus order
}

export interface RankedPlayer extends Player {
  elo: number;
  wins: number;
  losses: number;
  rank: number;
  // FB4-61 tile stats — market side, omitted by the backend when unknown.
  // consensus_pos_rank: 1-based rank within position by consensus seed value.
  // ..._delta_30d: 30d rank movement (positive = moved UP toward #1); absent
  // until a prior-day consensus snapshot exists in the 30d window.
  consensus_pos_rank?: number | null;
  consensus_pos_rank_delta_30d?: number | null;
  // TestFlight #71 tile meters — 0-1 scores from the Trends consensus-gap
  // math, omitted by the backend when unavailable (no real league, thin
  // community baseline, free agent). A player carries at most ONE of these:
  // tradeability when the user owns them in the selected league (your value
  // vs the market — high = profitable to trade away), acquirability when a
  // leaguemate owns them (your value vs that owner's — high = easy to buy).
  tradeability?: number | null;
  acquirability?: number | null;
}

export interface LeagueSummary {
  league_id: string;
  name: string;
  avatar?: string | null;
  total_rosters?: number;
  platform?: string;
  // Sleeper settings.type: 0 = redraft, 1 = keeper, 2 = dynasty. Optional —
  // local/ESPN leagues don't carry it. Onboarding item 10 (F12): redraft
  // leagues get a "Dynasty values shown" label and a segment tag in events.
  settings_type?: number;
}

export interface SessionInfo {
  token: string;
  user_id: string;
  username: string;
  display_name: string;
  avatar?: string | null;
  expires_at: number;
  leagues?: LeagueSummary[];
}

export interface RankingProgress {
  QB: number; RB: number; WR: number; TE: number;
  threshold: number;
  unlocked: boolean;
  total_required: number;
  total_completed: number;
  ranking_method?: 'trio' | 'manual' | 'tiers' | null;
  unlocked_formats?: ScoringFormat[];
  scoring_format?: ScoringFormat;
}

export interface TradeCard {
  trade_id: string;
  league_id: string;
  give_player_ids: string[];
  receive_player_ids: string[];
  give_players: Player[];
  receive_players: Player[];
  opponent_user_id: string;
  opponent_username: string;
  match_score: number;            // 0–100
  fairness: number;               // 0–1 ratio
  reasons?: string[];             // present only when trade_math.human_explanations flag is on
  // True when the opponent's ELOs came from their actual saved rankings
  // (a real FTF user); false / undefined when they were noise-randomized
  // off the consensus seed. Backend sets this on /api/trades/generate and
  // /api/trades/status snapshots (server.py:_make_progress_cb).
  real_opponent?: boolean;
  // v2 engine: how the card was built. 'divergence' = real ranking
  // disagreement between the two owners; 'consensus' = fair-value idea vs
  // an opponent who hasn't ranked players yet. Normalizer defaults missing
  // values to 'divergence' (the legacy behavior). Optional so the
  // MatchesScreen adapter shapes (which never carry it) still typecheck.
  basis?: 'divergence' | 'consensus';
  // True when the counterparty already liked the mirror of this trade.
  // Backend serializes `likes_you` only when true; normalizer defaults
  // to false.
  likesYou?: boolean;
  // Low-value player added by the engine to balance an otherwise-unfair
  // trade. The player is ALREADY in give_players/receive_players — this
  // just identifies which one, so the UI can call it out.
  sweetener?: { playerId: string; side: 'give' | 'receive' };
  // Player-swap (feedback #86): true when the user has replaced a player
  // on this card via the swap sheet. Set client-side only (TradesScreen);
  // the backend never returns it. Edited cards carry a derived trade_id
  // (`<original>::edited`) so a like/flag records the MODIFIED package via
  // the server's FB-46 context-reconstruction path instead of the original
  // in-memory card.
  edited?: boolean;
  // FB-47 finder targeting (flag trade.finder_targeting): counterparty
  // positional fit for the user's stated targets, 0–1. Serialized only
  // when the flag is on AND the user expressed targets; drives the fit
  // line on cards (deck order is already fit-aware server-side).
  partner_fit?: number;
  // Structured "why this match" context stamped on every v2 card
  // (server.py trade_card_to_dict → match_context). Only the fields the
  // client reads are typed; extend as needed.
  match_context?: {
    user_needs?: string[];
    opponent_surplus?: string[];
  };
  /** Phase-2 lane: 'window' = contention-window (win-now) move, 'value' =
   *  pure value-accumulation move. Backend serializes conditionally;
   *  absent on legacy cards. */
  lane?: 'window' | 'value';
  /** Phase-2: the user pays a consensus-value premium to land a positional
   *  fit. `value_paid` = value conceded; `position` = the fit position. */
  fitPremium?: { value_paid: number; position?: string };
  /** Phase-2: which engine aggression variant built this card. */
  aggressionVariant?: string;
  // Pick-denominated value verdict (feedback #157 value-bar) — the same
  // shape POST /api/trade/evaluate returns, now stamped on every generated
  // deck card so the card renders the universal TradeValueBar instead of a
  // 0–1 fairness meter. give_value/receive_value are consensus package values
  // (value space, matching the calculator); favors is who the value leans to;
  // gap is the pick-denominated delta (null on a one-sided/exactly-even read).
  // All optional: absent on cards rebuilt from client echo, and on swap the
  // client clears them until the re-price round-trip lands fresh numbers.
  give_value?: number;
  receive_value?: number;
  favors?: 'give' | 'receive' | 'even' | null;
  gap?: CalcGap | null;
}

export interface TradeMatch {
  match_id: string;
  league_id: string;
  /** Display name for the league this match belongs to. Populated by the
   *  backend's /api/trades/matches/all endpoint; absent on legacy single-
   *  league responses. */
  league_name?: string;
  my_side_player_ids: string[];
  their_side_player_ids: string[];
  /** Pre-resolved player display names, parallel arrays to *_player_ids.
   *  Populated by /all enrichment so we don't have to look players up in
   *  session state (which is league-scoped). */
  my_side_player_names?: string[];
  their_side_player_names?: string[];
  /** Pre-resolved player team abbreviations + positions, parallel arrays
   *  to *_player_ids. Populated by /all enrichment for the same reason as
   *  *_player_names — the active session's player pool only covers one
   *  league. Empty strings ("") mean unknown / free-agent. */
  my_side_player_teams?: string[];
  their_side_player_teams?: string[];
  my_side_player_positions?: string[];
  their_side_player_positions?: string[];
  counterparty_user_id: string;
  counterparty_username: string;
  created_at: string;
  my_disposition?: 'pending' | 'accepted' | 'declined';
  their_disposition?: 'pending' | 'accepted' | 'declined';
}

// Trades the user has liked that have NOT yet matured into a mutual
// match. Renders on MatchesScreen's "Awaiting them" segment. Shape is
// deliberately parallel to TradeMatch so the same tile component can
// render either with minor adaptation. Source: /api/trades/awaiting.
export interface AwaitingTrade {
  trade_id: string;
  league_id: string;
  league_name?: string;
  my_side_player_ids: string[];
  their_side_player_ids: string[];
  my_side_player_names?: string[];
  their_side_player_names?: string[];
  counterparty_user_id: string;
  counterparty_username: string;
  liked_at: string;
}

// Returned by /api/trades/generate and /api/trades/status. The actual
// generation runs in a background thread on the server; the client polls
// with the `job_id` to stream cards into the deck as they're produced.
export interface TradeJobSnapshot {
  job_id: string;
  status: 'running' | 'complete' | 'error';
  cards: TradeCard[];
  opponents_done: number;
  opponents_total: number;
  error?: string | null;
}

export interface NotificationItem {
  id: string | number;
  type: string;
  title?: string;
  body?: string;
  created_at: string;
  is_read?: boolean;
  metadata?: Record<string, unknown>;
}

// Trends (Bundle 2). Mirrors the rows returned by /api/trends/risers-fallers
// and /api/trends/consensus-gap (see backend/trends_service.py). The backend
// ships both the raw ELO delta and a derived RANK view (FB-04): rank is the
// player's position when the pool is sorted by ELO (highest = #1). Rank fields
// are nullable — null/undefined when historical rank can't be derived, so the
// screen renders "—" instead of crashing.
export interface TrendRow {
  player_id: string;
  name?: string;
  position?: Position | string;
  team?: string | null;
  current_elo: number;
  previous_elo: number;
  delta: number; // positive = riser, negative = faller
  // Rank view (FB-04). overall_rank = position in the whole pool; pos_rank =
  // position within the player's own position group. *_delta = previous_rank -
  // current_rank, so positive = moved UP toward #1.
  overall_rank?: number | null;
  overall_rank_delta?: number | null;
  pos_rank?: number | null;
  pos_rank_delta?: number | null;
}

export interface ContrarianGapEntry {
  player_id: string;
  name?: string;
  position?: Position | string;
  team?: string | null;
  user_elo: number;
  // "easiest sells" rows compare to community mean; "easiest buys" rows
  // compare to the specific owner's ELO. Only one of the two is set per row.
  community_elo?: number;
  owner_elo?: number;
  owner_username?: string;
  gap: number;   // user_elo - (community_elo | owner_elo)
  score: number; // 0-99 normalised magnitude for the bar
  // Rank view (FB-04). user_rank vs comparison_rank (community for sells, the
  // owner for buys); *_gap = comparison_rank - user_rank, so positive = you
  // rank them nearer #1 than the comparison. Nullable when not derivable.
  user_rank?: number | null;
  comparison_rank?: number | null;
  rank_gap?: number | null;
  user_pos_rank?: number | null;
  comparison_pos_rank?: number | null;
  pos_rank_gap?: number | null;
}

// Trade queue (Bundle 5 — flag `trades.queue_2k`). Lightweight snapshot of
// a generated trade that the user has stacked for later "Send All" via
// Sleeper deep-links. Persisted per-user in AsyncStorage; queue is scoped
// per-league inside the store.
export interface QueuedTrade {
  trade_id: string;
  league_id: string;
  match_id?: string;
  sleeper_url: string;
  give_summary: string;     // e.g. "RB Bijan Robinson"
  receive_summary: string;
  queued_at: string;
}

// B7 — League surfaces. ActivityEvent mirrors the per-row shape returned by
// /api/league/activity (see backend/database.py:load_league_activity).
// The backend ships an ISO `ts` + a pre-formatted `message`; we re-derive
// the relative time on the client via utils/relativeTime so the timestamp
// stays fresh as the list ages on screen.
export interface ActivityEvent {
  id: string;                 // synthesized client-side (`${ts}-${actor}-${i}`)
  occurred_at: string;        // ISO timestamp from `ts`
  user_id: string;            // from `actor_user_id`
  username: string;           // best-effort label extracted from `message`
  event_type:
    | 'trade_match'
    | 'trade_accepted'
    | 'trade_declined'
    | 'tier_save'
    | 'league_sync'
    | 'unlock'
    | string;                 // permissive — backend may add new types
  summary: string;            // backend-formatted human-readable message
  emoji?: string;
}

// Aggregated per-user divergence score across the 4 positions returned by
// /api/league/contrarian. Aggregation lives in api/league.ts so screens
// consume a flat sorted list.
export interface ContrarianRow {
  user_id: string;
  username: string;
  divergence_score: number;   // mean abs ELO deviation, averaged across positions
}

// "Newly unlocked" leaguemates — derived client-side from the activity feed
// (events with event_type === 'unlock'). The backend doesn't expose a
// dedicated endpoint; the activity-feed unlock entries are emitted whenever
// a tier_save flips a format from locked to unlocked.
export interface NewPartnerEntry {
  user_id: string;
  username: string;
  newly_unlocked_at: string;  // ISO timestamp
}

export type FlagMap = Record<string, boolean>;

// B3 — Cross-league portfolio row. The backend's /api/portfolio returns
// a per-player aggregate of which leagues the user owns this player in.
// Per-league tier info isn't part of the current backend response — the
// `tier` field is reserved and defaults to 'pool' (no tier known) so the
// UI can show a neutral chip per league. When the backend later starts
// emitting tier-per-league, this type already accepts it.
export type PortfolioTier = Tier | 'pool';
export interface PortfolioExposure {
  league_id: string;
  league_name: string;
  tier: PortfolioTier;
}
export interface PortfolioRow {
  player: Player;
  /** One entry per league this player appears on for the user. */
  exposure: PortfolioExposure[];
  /** Total leagues the user is in. Same value on every row — keeps the
   *  "N of M" badge stable. */
  total_leagues: number;
}

export interface NotificationPrefs {
  trade_matches: 0 | 1;
  weekly_digest: 0 | 1;
  reengagement: 0 | 1;
  quiet_hours_enabled: 0 | 1;
  tz: string;
}

// ── Growth loop (Bundle 8) ───────────────────────────────────────────────
// `landing.smart_start_cta` accepts either a bare Sleeper username or a full
// league URL (Sleeper / ESPN / MyFantasyLeague). The mobile client decides
// which path to take by inspecting the input first — if it looks like a URL
// we POST /api/league/parse-url and surface platform / league_id; otherwise
// we hand the raw string off to the existing username sign-in.
export type SmartStartKind = 'username' | 'league_url' | 'invalid';

export interface SmartStartResolution {
  kind: SmartStartKind;
  /** Lowercased Sleeper username when kind === 'username'. */
  username?: string;
  /** Detected platform when kind === 'league_url'. */
  platform?: 'sleeper' | 'espn' | 'mfl' | 'fleaflicker';
  league_id?: string;
  /** Resolved league name from /api/league/parse-url (Sleeper only). */
  league_name?: string;
  /** True when the platform is supported end-to-end today (Sleeper). */
  supported?: boolean;
  /** Human-readable failure reason for kind === 'invalid'. */
  message?: string;
}

// /api/profile/<username> — public, read-only snapshot of a user's ranking
// activity. Only includes data the user has created themselves; no private
// league info is exposed. Field shape matches backend/server.py:public_profile_data.
export interface PublicProfileContrarianEntry {
  player_id: string;
  name: string;
  user_elo: number;
  community_elo: number;
  delta: number;
  raters: number;
}

export interface PublicProfileTierEntry {
  player_id: string;
  name: string;
  elo: number;
}

export interface PublicProfile {
  username: string;
  display_name: string;
  avatar_url: string | null;
  leagues_count: number;
  scoring_format: ScoringFormat;
  /** Top contrarian takes per position (above/below community consensus). */
  contrarian_takes: Record<
    string,
    { above: PublicProfileContrarianEntry[]; below: PublicProfileContrarianEntry[] }
  >;
  /** {position: {tier: [{player_id, name, elo}]}} — only populated tiers. */
  tiers_snapshot: Record<string, Record<string, PublicProfileTierEntry[]>>;
}

// /api/session/demo — bootstraps a seeded demo session (no Sleeper auth).
// The backend returns a fresh session_token in `token`; mobile sets that as
// the X-Session-Token for subsequent calls just like the normal flow.
export interface DemoSessionResponse {
  ok: true;
  demo: true;
  token: string;
  user_id: string;
  display_name: string;
  league_id: string;
  league_name: string;
  player_count: number;
  user_roster: Player[];
  opponents: number;
}
