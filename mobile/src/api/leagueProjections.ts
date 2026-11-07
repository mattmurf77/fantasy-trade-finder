import { api } from './client';

export interface ProjectionWeek {
  week: number; opponent_roster_id: number; win_probability: number; loss_probability: number;
  maxpf_floor?: { input_mean: number; simulated_pre_floor_mean: number | null; simulated_mean: number; mean_uplift: number; frequency: number; policy?: string; target_mean?: number; latent_maxpf_mean?: number | null; simulated_mean_standard_error?: number; rounding_mean_error_bound?: number; configured_latent_maxpf_variance?: number; analytic_realized_variance?: number; configured_residual_correlation?: number; simulated_correlation?: number | null };
  tie_probability: number; win_equivalent_probability: number; modeled_score_mean: number; modeled_score_sd: number;
  actual: {points: string; gaps: number[]; lineup: {slot: string; player: null | {name?: string; player_id: string; points: string; hypothetical?: boolean}}[]};
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
  provisional: boolean; config: Record<string, string | number>; warnings: string[]; teams: ProjectionTeam[];
}
export interface ProjectionRun {run_id: string; status: string; reason: string | null; result: ProjectionResult | null}
export interface ProjectionView {
  state: string; reason: string | null; run: ProjectionRun | null; attempt: ProjectionRun | null;
  next_attempt_not_before: string | null; cadence: 'weekly'; schedule_timezone: string;
  scenario_defaults: Record<string, string | number>; schedule_note: string;
}
export const getLeagueProjectionBatch = (leagueId: string) =>
  api.get<ProjectionView>(`/api/leagues/${encodeURIComponent(leagueId)}/projection-runs/latest`);
export const queueLeagueProjectionScenario = (leagueId: string, config: Record<string, string | number>, baselineRunId: string) =>
  api.post<ProjectionRun>(`/api/leagues/${encodeURIComponent(leagueId)}/projection-runs`, {config, baseline_run_id: baselineRunId});
export const getLeagueProjectionRun = (runId: string) => api.get<ProjectionRun>(`/api/projection-runs/${runId}`);
