// Type definitions that mirror the backend's response shapes.
// Source of truth: backend/server.py routes + backend/database.py models.
// These types are deliberately loose-ish — extend as real responses reveal
// more fields. Intent is a tight enough safety net to catch typos; not
// a legal contract.

export type ScoringFormat = '1qb_ppr' | 'sf_tep';
export type Position = 'QB' | 'RB' | 'WR' | 'TE';
export type Tier = 'elite' | 'starter' | 'solid' | 'depth' | 'bench';

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
}

export interface LeagueSummary {
  league_id: string;
  name: string;
  avatar?: string | null;
  total_rosters?: number;
  platform?: string;
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
// measures movement as an ELO delta, not a rank delta — the screen renders
// the magnitude with a direction arrow.
export interface TrendRow {
  player_id: string;
  name?: string;
  position?: Position | string;
  team?: string | null;
  current_elo: number;
  previous_elo: number;
  delta: number; // positive = riser, negative = faller
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
  platform?: 'sleeper' | 'espn' | 'mfl';
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
