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
}

export interface TradeMatch {
  match_id: string;
  league_id: string;
  my_side_player_ids: string[];
  their_side_player_ids: string[];
  counterparty_user_id: string;
  counterparty_username: string;
  created_at: string;
  my_disposition?: 'pending' | 'accepted' | 'declined';
  their_disposition?: 'pending' | 'accepted' | 'declined';
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

export type FlagMap = Record<string, boolean>;
