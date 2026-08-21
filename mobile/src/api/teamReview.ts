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

/** #372 — why the starter-value term is or is not being counted. Never infer
 *  it from an `index` of 0: an exactly average starting lineup and a lineup we
 *  could not read both index at 0 and mean different things.
 *    observed        a lineup template was known and the league has priced
 *                    starter value — the term counts
 *    lineup_unknown  the platform exposes no roster_positions equivalent and
 *                    no template was found, so there is no "starting lineup"
 *                    to value. We did not look
 *    absent          a template existed but the league's total starter value
 *                    is zero (unsynced or demo league) */
export type StarterProvenance = 'observed' | 'lineup_unknown' | 'absent';

/** #372 — why the playoff-likelihood term is or is not being counted.
 *    observed          the band was admitted and scored
 *    preseason         a band exists and was deliberately NOT used —
 *                      `completed_weeks === 0` is the simulator's weakest
 *                      window (D-094) and preseason is when window-setting
 *                      matters most
 *    odds_unavailable  no band at all: non-Sleeper league, `outlook.odds` off,
 *                      or the simulator failed
 *    odds_disabled     `trades.window_from_odds` is off, so we never asked.
 *                      Distinct from `odds_unavailable` on purpose — "we did
 *                      not ask" is not "we asked and got nothing" */
export type PlayoffProvenance =
  | 'observed' | 'preseason' | 'odds_unavailable' | 'odds_disabled';

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
    /** #372 "we calculate starter dynasty value. Let's incorporate that."
     *  Present only while `trade.outlook_composite` is on. `index` is
     *  `share × num_teams − 1`: 0.0 is an exactly average starting lineup,
     *  +0.30 is 30 % above the league mean, clamped to
     *  ±`model.starter_index_cap`. */
    starters?: {
      starter_value: number;
      league_starter_value: number;
      /** Your starters' value as a fraction of the league's. */
      share: number;
      /** What ENTERED the score — `index_raw` clamped to
       *  ±`model.starter_index_cap`. */
      index: number;
      /** What was MEASURED, uncapped. Show this one; the cap binds on real
       *  rosters, so rendering `index` would understate a lopsided team. When
       *  the two differ, say the signal was capped. */
      index_raw: number;
      provenance: StarterProvenance;
      /** Whether the term entered `score` — AND, because starter value is the
       *  composite's anchor, whether the whole composite weight vector ran.
       *  `false` here means `model` still carries the LEGACY weights. */
      applied: boolean;
    };
    /** #372 "…and playoff likelihood". The same simulated band
     *  `trades.window_from_odds` reads, entering the score as a weighted term
     *  instead of overwriting the verdict. */
    playoff?: {
      playoff_pct: number | null;
      band: PlayoffBand | null;
      /** 2 × (playoff_pct − center): +0.30 at the `likely` boundary, −0.30 at
       *  `unlikely`, clamped to ±`model.playoff_index_cap`. */
      index: number;
      /** The neutral point — the midpoint of the `tossup` band. Read it; do
       *  not restate 0.5 in copy (D-101). */
      center: number;
      provenance: PlayoffProvenance;
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
    /** #372 — `true` when the COMPOSITE vector scored. The three weights above
     *  are then the composite's own (vet/youth at 0.40, not 1.00): they are
     *  RE-STATED by the backend rather than left at their legacy values, so
     *  reading them is always correct and hardcoding one never is. */
    composite?: boolean;
    /** Present only alongside `signals.starters.applied`. */
    w_starter_index?: number;
    starter_index_cap?: number;
    /** Present only alongside `signals.playoff.applied` — a weight is never
     *  rendered beside a term that did not score. */
    w_playoff_index?: number;
    playoff_center?: number;
    playoff_index_cap?: number;
  };
  /** #371 — which model produced `inferred`. Absent entirely while
   *  `trades.window_from_odds` is off, which is what keeps the flag-off payload
   *  identical to what build 122 already parses.
   *  #372 — `'composite'` means the playoff band was SCORED AS A TERM rather
   *  than used to overwrite the verdict, so `inferred === roster_inferred`. */
  source?: 'roster' | 'odds' | 'composite';
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
  /** #366 — `replacement` is the report's word for what the wire has always
   *  called `bench`, and it is an ALIAS: same count, emitted alongside `bench`
   *  rather than instead of it, so a build older than this one still parses.
   *  It is therefore OPTIONAL — it appears only when `trade.position_tiers`
   *  is on. Read it as `replacement ?? bench`, never `replacement` alone, or
   *  the flag-off payload renders a hole. `bench` stays required: no backend,
   *  at any flag setting, omits it. */
  tier_depth: Record<string, {
    elite: number; starter: number; bench: number; replacement?: number;
  }>;
  position_needs: string[];
  position_surplus: string[];
  weakest_slot: {
    slot: string; player_id: string; name: string; position: string;
  } | null;
  acquire_positions: string[];
  trade_away_positions: string[];
  /** #366 — which banding actually produced the counts above, per position.
   *  `absolute` means the pool was too thin to rank within a position and the
   *  legacy value cuts ran. Present only when `trade.position_tiers` is on. */
  tier_basis?: Record<string, 'position_relative' | 'absolute'>;
  /** #366 — how many of your RBs are the RB2 on their NFL depth chart
   *  (Sleeper's own `depth_chart_order`, not a value guess). Present only when
   *  `trade.rb_handcuff` is on. ABSENT and 0 are different claims — "we did
   *  not look" vs "you have none" — so render on presence, never `?? 0`. */
  handcuff_rb?: number;
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
  /** #367 / [D-100] — your BUY list: players you rate above the market whom you
   *  do NOT own, so you would pay less than you think they are worth. Sourced
   *  from `easiest_buys` (your board vs the OWNER's).
   *
   *  This comment previously read "you rate them ABOVE the market ⇒ your
   *  easiest SELLS … the copy must not reverse it", which asserted the exact
   *  inversion D-100 fixed and told the next reader to preserve it. A player
   *  you rate above the market is the one nobody overpays for. */
  higher_than_market: DivergenceRow[];
  /** #367 / [D-100] — your SELL list: players you OWN whom the market rates
   *  above your board, so someone pays you more than they are worth to you.
   *  Sourced from `easiest_sells` (your board vs the community mean).
   *  `gap` is a POSITIVE edge magnitude on BOTH lists — never infer the
   *  direction from the sign. See docs/cross-client-invariants.md. */
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
