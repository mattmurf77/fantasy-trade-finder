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

/** #365 — why the net-first-round term is or is not being counted. NEVER infer
 *  this from a zero `net`: `none_traded` and a genuine net of 0 look identical
 *  in the numbers and mean completely different things.
 *    observed     at least one first in this league is recorded under an owner
 *                 other than its original — the ledger is real, the term counts
 *    none_traded  rows exist but nothing is recorded as having moved: either
 *                 nobody has traded a first, or the history predates capture.
 *                 Not counted, and the card must say so
 *    absent       no round-1 rows for this league at all (ESPN without asserted
 *                 picks, MFL crosswalk gap, demo, unsynced). Not counted */
export type FirstsProvenance = 'observed' | 'none_traded' | 'absent';

export interface TeamReviewWindow {
  /** Only ever contender | rebuilder | not_sure — inference never claims an
   *  extreme. `options` still offers all five, because a user may DECLARE one.
   *  Under `trades.window_from_odds` this is the verdict the beat ACTS ON,
   *  which may have come from the playoff band rather than the roster — read
   *  `source` to know which, and `roster_inferred` for the heuristic's answer. */
  inferred: OutlookOption;
  declared: OutlookOption | null;
  signals: {
    vet_share: number;
    youth_share: number;
    pick_share: number;
    equal_pick_share: number;
    score: number;
    /** #365 "number of 1sts owned vs traded away". Present only while
     *  `trade.outlook_net_firsts` is on, so the whole ledger card is
     *  conditional on this object rather than on any flag the client holds. */
    firsts?: {
      held: number;
      own_total: number;
      traded_away: number;
      acquired: number;
      /** acquired − traded_away. */
      net: number;
      /** net / own_total, clamped to ±`model.net_firsts_cap`. */
      net_share: number;
      provenance: FirstsProvenance;
      /** Whether the term actually entered `score`. Read this — do not derive
       *  it from `provenance`, and never from `net_share === 0`. */
      applied: boolean;
    };
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
    /** Present only alongside `signals.firsts` — the same flag ships both, so
     *  the beat can never render a ledger without the weight that scored it. */
    w_net_firsts?: number;
    net_firsts_cap?: number;
  };
  /** #371 — which model produced `inferred`. Absent entirely while
   *  `trades.window_from_odds` is off, which is what keeps the flag-off payload
   *  identical to what build 122 already parses. */
  source?: 'roster' | 'odds';
  /** The roster heuristic's own verdict, ALWAYS — even when the odds drove.
   *  Both definitions of "contender" ship together rather than one silently
   *  replacing the other. */
  roster_inferred?: OutlookOption;
  /** The simulated band and what it implies. Present when the sim produced a
   *  band, even in preseason — when it is shown but deliberately not obeyed. */
  odds?: {
    band: PlayoffBand;
    playoff_pct: number;
    implied: OutlookOption | null;
  } | null;
  /** Why the odds did NOT drive, when they did not. `preseason` means the band
   *  exists and was refused (completed_weeks === 0 is the sim's weakest
   *  window); `odds_unavailable` means there was no band to read — the league
   *  is not Sleeper, `outlook.odds` is off, or the sim failed. */
  odds_reason?: 'odds_unavailable' | 'preseason' | null;
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
