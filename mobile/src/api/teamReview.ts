import { apiRequest } from './client';

// #357 / #358 / #359 — Team Review, the six-beat guided read of your own team.
// Backend: GET /api/league/team-review (flag `trades.team_review`; 404s while
// off, so callers gate on the flag before requesting).
//
// Contract: docs/feedback/items/357-team-review/lld-delta.md §2.
//
// `meta.beats_skipped` is AUTHORITATIVE. Render `beats` minus `beats_skipped`,
// in `beats` order. The client must never decide for itself that a beat is
// empty — the analytics `beat` property and the step indices both bind to the
// server's list, so a client-side skip would desynchronise the funnel.

export type BeatId =
  | 'standing' | 'window' | 'depth' | 'divergence' | 'partners' | 'plan';

export type OutlookOption =
  | 'championship' | 'contender' | 'rebuilder' | 'jets' | 'not_sure';

export type PlayoffBand = 'likely' | 'tossup' | 'unlikely';

export interface TeamReviewMeta {
  num_teams: number;
  scoring_format: string;
  completed_weeks: number;
  beats: BeatId[];
  beats_skipped: BeatId[];
  scoring_available: boolean;
  /** Why the PPG card has no data. Named, never hidden — a user on ESPN or in
   *  preseason gets a reason, not a blank. */
  scoring_unavailable_reason: 'preseason' | 'platform_unsupported' | null;
}

export interface TeamReviewStanding {
  value_rank: number | null;
  value_total: number;
  roster_value: number;
  position_value: {
    position: string; value: number; share: number; rank: number | null;
  }[];
  /** REAL points already scored — never a projection. null in preseason and
   *  on non-Sleeper leagues; see meta.scoring_unavailable_reason. */
  scoring: {
    ppg: number;
    ppg_rank: number;
    record: { w: number; l: number; t: number } | null;
  } | null;
  /** #169 playoff band. Present only when `outlook.odds` is on AND the league
   *  is Sleeper AND the sim succeeded — absent, never null-filled, otherwise.
   *  `playoff_pct` is for the VoiceOver label only; the visible surface is the
   *  band. There is deliberately no title_pct. */
  outlook?: {
    band: PlayoffBand;
    playoff_pct: number;
    projected_seed: number | null;
    beta: boolean;
    is_preseason: boolean;
    priced_slot_coverage: {
      fraction: number;
      total_slots: number;
      priced_slots: number;
      unpriced_slots: string[];
      affects_strength: boolean;
    } | null;
  };
}

export interface TeamReviewWindow {
  /** Only ever contender | rebuilder | not_sure — inference never claims an
   *  extreme. `options` still offers all five, because a user may DECLARE one. */
  inferred: OutlookOption;
  declared: OutlookOption | null;
  signals: {
    vet_share: number;
    youth_share: number;
    pick_share: number;
    equal_pick_share: number;
    score: number;
  };
  /** #365 — every input the inference actually used. Read these rather than
   *  hardcoding a threshold in copy: the screen shipped saying "age 23 and
   *  under" while `youth_age` was 26. Optional so an older payload (or a
   *  backend rolled back below this change) degrades to hiding the rows
   *  instead of rendering `undefined`. */
  model?: {
    vet_age: number;
    youth_age: number;
    w_vet_share: number;
    w_youth_share: number;
    w_pick_share: number;
    contender_cut: number;
    rebuilder_cut: number;
  };
  options: OutlookOption[];
}

export interface TeamReviewDepth {
  tier_depth: Record<string, { elite: number; starter: number; bench: number }>;
  position_needs: string[];
  position_surplus: string[];
  weakest_slot: {
    slot: string; player_id: string; name: string; position: string;
  } | null;
  acquire_positions: string[];
  trade_away_positions: string[];
}

export interface DivergenceRow {
  player_id: string;
  name: string;
  position: string;
  user_elo: number;
  comparison_elo: number;
  gap: number;
  pos_rank: number | null;
  on_roster: boolean;
}

export interface TeamReviewDivergence {
  source: 'league_community' | 'consensus_seed' | null;
  baseline_user_count: number;
  /** Players the user has actually COMPARED (wins+losses > 0) — not the size
   *  of the Elo map, which covers the whole pool regardless. */
  board_judged_players: number;
  board_interactions: number;
  /** You rate them ABOVE the market ⇒ your easiest SELLS. The inversion is the
   *  point of the beat and the copy must not reverse it. */
  higher_than_market: DivergenceRow[];
  lower_than_market: DivergenceRow[];
}

export interface TeamReviewPartners {
  opposed_window: {
    user_id: string; username: string; value_rank: number | null;
    inferred_outlook: string; pick_capital_share: number;
    first_round_picks: number;
  }[];
  fills_your_need: {
    user_id: string; username: string; position: string; startable_count: number;
  }[];
}

export interface TeamReviewResponse {
  league_id: string;
  platform: string;
  basis: string;
  meta: TeamReviewMeta;
  standing: TeamReviewStanding;
  window: TeamReviewWindow;
  depth: TeamReviewDepth;
  divergence: TeamReviewDivergence;
  partners: TeamReviewPartners;
}

export async function getTeamReview(
  leagueId: string,
  basis: 'consensus' | 'personal' = 'consensus',
  signal?: AbortSignal,
): Promise<TeamReviewResponse> {
  return apiRequest(
    `/api/league/team-review?league_id=${encodeURIComponent(leagueId)}&basis=${basis}`,
    { signal },
  );
}
