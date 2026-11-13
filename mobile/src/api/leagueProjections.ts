import { api } from './client';

export interface ProjectionFreeAgentFill {slot_index: number; slot: string; player_id: string; name: string; points: string; estimate_status: string}
export interface ProjectionWeek {
  week: number; opponent_roster_id: number; win_probability: number; loss_probability: number;
  maxpf_floor?: { input_mean: number; simulated_pre_floor_mean: number | null; simulated_mean: number; mean_uplift: number; frequency: number; policy?: string; target_mean?: number; latent_maxpf_mean?: number | null; simulated_mean_standard_error?: number; rounding_mean_error_bound?: number; configured_latent_maxpf_variance?: number; analytic_realized_variance?: number | null; configured_residual_correlation?: number; simulated_correlation?: number | null };
  projection_coverage?: {estimated: boolean; unpriced_players: {player_id: string; name?: string; reason: string}[]; partial_players: {player_id: string; name?: string; missing_keys: string[]; missing_negative_keys: string[]}[]; priced_actual_pool: number; priced_maxpf_pool: number; complete?: boolean; missing_actual_slots?: string[]; idp_replacement_unavailable: boolean;
    /** Model v6: open slots filled by the best projected free agent, and open slots with none (scored 0). */
    free_agent_fills?: ProjectionFreeAgentFill[]; maxpf_free_agent_fills?: ProjectionFreeAgentFill[]; zero_filled_slots?: string[]; maxpf_zero_filled_slots?: string[]; completed_actual_players?: number; locked_starter_count?: number; missing_locked_actuals?: {slot_index: number; player_id: string; name?: string; reason: string}[]};
  actual_score_observed?: boolean; actual_observation_basis?: string | null; maxpf_score_observed?: boolean;
  observed_mean_conditioning?: {unconditioned_maxpf_mean: number; known_maxpf_floor: number | null; target_adjustment: number};
  modeled_actual_projection?: string; modeled_maxpf_projection?: string;
  tie_probability: number; win_equivalent_probability: number; modeled_score_mean: number; modeled_score_sd: number;
  actual: {points: string; gaps: number[]; lineup: {slot: string; unpriced_locked_player?: {player_id: string; name?: string}; player: null | {name?: string; player_id: string; points: string; hypothetical?: boolean}}[]};
  maxpf: {points: string}; exclusions: {player_id: string; reason: string}[];
}
export interface ProjectionTeam {
  roster_id: number; name: string; current_record: number[]; current_points_for: number; current_ppg: number | null;
  final_record_distribution: {record: number[]; probability: number}[];
  expected_record: number[]; modal_record: number[]; playoff_probability: number; bye_probability: number;
  current_maxpf: number; maxpf_per_completed_week: number | null; maxpf_mean: number;
  maxpf_quantiles: Record<string, number>; nonplayoff_probability: number; pick_owner_roster_id: number;
  pick_probabilities: number[]; conditional_expected_pick: number | null; nonplayoff_samples: number;
  owner_expected_nonplayoff_picks: number; owner_probability_at_least_one: number; weeks: ProjectionWeek[];
}
export interface ProjectionResult {
  league_name: string; completed_weeks: number; playoff_spots: number; playoff_byes: number; scoring: Record<string, number>;
  model_version: string; captured_at: string; verified_at: string; source: string; iterations: number;
  coverage?: {estimated?: boolean; unpriced_player_weeks?: number; partial_player_weeks?: number; estimate_status?: 'complete' | 'incomplete'; incomplete_team_weeks?: number; missing_lineup_slots?: number; fa_filled_slots?: number; zero_filled_slots?: number; maxpf_fa_filled_slots?: number; maxpf_zero_filled_slots?: number; weekly_feed_states?: Record<string, string>};
  viewer_roster_id?: number | null; score_sd?: number;
  provisional: boolean; config: Record<string, string | number>; warnings: string[]; teams: ProjectionTeam[];
}
/** The four outlooks a playoff chance can recommend (never `not_sure`). */
export type ProjectionOutlook = 'jets' | 'rebuilder' | 'contender' | 'championship';
/** Server-classified from the unrounded probability. `suggestion` and
 *  `explanation` are server-written copy: render them as given, and never
 *  re-derive the bands on the client. */
export interface OutlookRecommendation {
  status: 'available' | 'unavailable'; reason: string | null; playoff_probability: number | null;
  recommended_outlook: ProjectionOutlook | null; current_outlook: string | null; differs: boolean;
  suggestion: string | null; explanation: string; captured_at: string | null;
}
// ── Max PF moves (flag `league.max_pf_moves`; contract:
// docs/plans/league-projections/max-pf-trade-away/contract.md §3). The app
// reads every number here and never re-computes one (utils/maxPfMoves.ts).
export type MaxPfMovesState =
  | 'unavailable' | 'season_over' | 'after_trade_deadline' | 'draft_order_not_maxpf'
  | 'no_miss' | 'no_moves' | 'ready';
export type DraftOrderRule = 'maxpf_lowest_first' | 'reverse_standings' | 'lottery_or_other';
export interface DraftOrder {rule: DraftOrderRule | null; set_at: string | null}
export interface PickOwner {owns_own_pick: boolean; owner_roster_id: number; owner_name: string}
export interface MaxPfBaseline {
  weeks_remaining: number; first_week: number; last_week: number; weeks_excluded_played: number;
  playoff_probability: number; playoff_band: ProjectionOutlook; pick_if_miss: number | null;
  top3_probability: number; label: string | null; label_slot: number | null;
  pick_value: number | null; pick_value_status: 'priced' | 'not_priced';
}
export interface MaxPfReplacement {player_id: string | null; name: string | null; short_name: string | null; free_agent: boolean; weeks: number}
export interface MaxPfMoveWeek {
  week: number; status: 'changed' | 'no_change' | 'bye' | 'played' | 'not_projected';
  maxpf_change: number; lineup_change: number; replaced_by: Omit<MaxPfReplacement, 'weeks'>[];
}
export interface NowAfter {now: number; after: number}
export interface MaxPfMoveRow {
  rank: number; player_id: string; name: string; short_name: string; position: string;
  maxpf_change: number; maxpf_change_exact: string; lineup_change: number; lineup_change_exact: string;
  weeks_affected: number; replacements: MaxPfReplacement[]; replacements_more: number; weeks: MaxPfMoveWeek[];
  playoff_probability: NowAfter; pick_if_miss: {now: number | null; after: number | null};
  top3_probability: NowAfter; label: {now: string | null; after: string | null};
  label_slot: {now: number | null; after: number | null};
  pick_value: {now: number; after: number; change: number} | null;
  keep: boolean; passes_threshold: boolean;
}
export interface MaxPfMoves {
  version: number; state: MaxPfMovesState; reason: string | null;
  viewer_roster_id: number | null; captured_at: string | null;
  draft_season: number | null; draft_round: number | null; draft_order: DraftOrder;
  saved_outlook: 'championship' | 'contender' | 'rebuilder' | 'jets' | 'not_sure' | null;
  pick_owner: PickOwner | null; baseline: MaxPfBaseline | null; roster_player_ids: string[];
  rows: MaxPfMoveRow[]; candidates_total: number;
}
export interface ProjectionRun {run_id: string; status: string; reason: string | null; result: ProjectionResult | null}
export interface ProjectionView {
  state: string; reason: string | null; run: ProjectionRun | null; attempt: ProjectionRun | null;
  next_attempt_not_before: string | null; cadence: 'weekly'; schedule_timezone: string;
  scenario_defaults: Record<string, string | number>; schedule_note: string;
  /** False when the saved run came from an older model: show it as last
   *  saved, never as current. Absent on an older server, which means true. */
  model_current?: boolean;
  /** Absent while flag `league.projection_outlook` is off. */
  outlook_recommendation?: OutlookRecommendation;
  /** Absent while flag `league.max_pf_moves` is off (or on an older server). */
  max_pf_moves?: MaxPfMoves;
}
export const getLeagueProjectionBatch = (leagueId: string) =>
  api.get<ProjectionView>(`/api/leagues/${encodeURIComponent(leagueId)}/projection-runs/latest`);
