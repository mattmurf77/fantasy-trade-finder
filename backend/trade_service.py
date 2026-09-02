"""
trade_service.py — Fantasy Trade Finder
=========================================
Generates trade cards by comparing ranking sets across league members.

Core algorithm:
  For every pair of players (p1 in user_roster, p2 in opponent_roster):
    - If the user values p1 LESS than the opponent does       (user undervalues p1)
    - AND the opponent values p2 LESS than the user does      (opponent undervalues p2)
    → There's a perceived mutual gain: user trades p1 for p2

  Value mismatch score = (opp_elo[p1] - user_elo[p1])   # what user gives up = opponent gains
                       + (user_elo[p2] - opp_elo[p2])   # what user receives = more than opponent thinks

  Fairness score: trade is filtered out if consensus values are too lopsided
  (prevents surfacing wildly imbalanced trades that nobody would accept)
"""

import hashlib
import heapq
import math
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from itertools import combinations
from typing import Optional

from .feature_flags import FLAGS
from .trade_narrative import build_narrative
# trade.negmem — MODULE import, attribute calls only (T1, LLD §6.2). A value
# import (`from .negmem import effective_mult`) would freeze the binding and
# is exactly the form §10 N-11 sabotages. negmem is a LEAF (it imports only
# database + feature_flags), so this cannot cycle.
from . import negmem as _negmem


# ---------------------------------------------------------------------------
# Runtime config — loaded from model_config DB table at startup and on
# demand.  Falls back to the defaults below if the DB hasn't been seeded yet.
# ---------------------------------------------------------------------------

_DEFAULT_CFG: dict[str, float] = {
    # Team Outlook age thresholds
    "vet_age":               27,
    "youth_age":             26,
    "jets_age":              25,
    # Team Outlook score multipliers
    "boost_strong":          1.50,
    "boost_moderate":        1.25,
    "neutral":               1.00,
    "penalty_soft":          0.75,
    "penalty_mod":           0.60,
    "penalty_heavy":         0.30,
    # KTC dynasty value curve
    "ktc_k":                 0.0126,
    "ktc_max":           10000.0,
    "ktc_fallback_rank":   300.0,
    # Package diminishing-returns weights
    "package_weight_1":      1.00,
    "package_weight_2":      0.75,
    "package_weight_3":      0.55,
    "package_weight_4":      0.40,
    "package_weight_5":      0.28,
    # Backlog #10 — crown-asset consolidation premium (flag: trade.crown_asset).
    # The top asset of the SMALLER-count side gains value ramping from 0 at
    # share<=floor to crown_rate at share=1.0. See package_value_v2.
    "crown_rate":            0.12,
    "crown_share_floor":     0.50,
    # Interview 2026-07-17 ("depends on stud") — the consolidation premium
    # scales with the crown asset's ABSOLUTE value: a true tier-1 stud
    # (value >= crown_elite_value) earns the full crown_rate, a mid-tier
    # headliner earns proportionally less. <= 0 disables the scaling
    # (flat crown_rate for any crown asset).
    "crown_elite_value":  6000.0,
    # ------------------------------------------------------------------
    # #214 stud-tax retune — "market" mode shapes (default mode; the
    # pre-#214 constants above still drive the "heavy" legacy mode via the
    # #215 stud_tax_mode user setting). Fit against the T1–T6 competitor
    # matrix (docs/feedback/items/214-stud-tax/build-status.md).
    # ------------------------------------------------------------------
    # Crown premium phases out as the naive gap widens: scale by
    # max(0, 1 − |naive_skew| / skew_phaseout). <= 0 disables the
    # phase-out (full premium at any skew).
    "skew_phaseout":             0.5,
    # Per-elite-piece crown rate (BOTH sides, count-independent) — lower
    # than the single-crown heavy rate because every qualifying piece earns.
    "crown_rate_market":         0.08,
    # Market-mode depth discount: contribution floor + exponent, applied
    # against the package's OWN best asset (not the whole trade's), with
    # the side's total discount capped at package_discount_cap × naive sum.
    # Fit 2026-08-05 (build-status.md): floor 0.70 / γ 0.5 landed 4/6
    # matrix trades within ±15pp of the competitor median (T1/T4 misses
    # are naive-value-curve gaps no adjustment retune can close).
    "package_floor_market":      0.70,
    "package_adj_gamma_market":  0.5,
    "package_discount_cap":      0.35,
    # 2026-08-21 cross-package benchmark fix (operator-approved; evidence
    # docs/reviews/2026-08-21-market-curve-comparison.md §3b: the own-max
    # benchmark let 4 mids buy a stud at ~5% haircut — the served
    # Rice+Etienne+Swift+Corum → Nacua card scored 0.939/fair vs
    # FantasyCalc 1.362 / KTC 2.260). > 0 ⇒ a multi-asset side that does
    # NOT hold the trade's best asset is depth-benchmarked against the
    # TRADE's best asset (v_max) at package_floor_cross; ≤ 0 ⇒ the
    # pre-fix own-max math, byte-identical (arm A's pin).
    "package_bench_trade_wide":  1.0,
    # Contribution floor used ONLY on the cross-benchmarked side above —
    # lower than package_floor_market because the whole point is that
    # pieces small relative to the stud being bought stop holding ≥ 70%
    # of face. 0.40 prices the Nacua 4-for-1 at 0.709, between
    # FantasyCalc (0.734) and the pre-#214 heavy shape (0.692). Inert
    # while package_bench_trade_wide ≤ 0.
    "package_floor_cross":       0.40,
    # Positional preference multipliers
    "pos_acquire_bonus":     0.20,
    "pos_tradeaway_bonus":   0.15,
    "pos_conflict_penalty":  0.15,
    "pos_multiplier_cap":    2.00,
    # Backlog #2 — per-player target multiplier (flag: trade.preference_lists).
    # +N per received TARGET player, capped by pos_multiplier_cap. Mirrors the
    # (dormant) pos_acquire_bonus pattern at player granularity.
    "target_acquire_bonus":  0.20,
    # TradeService scoring thresholds
    "min_mismatch_score":   40.0,
    "max_value_ratio":       2.5,
    "mismatch_weight":       0.70,
    "fairness_weight":       0.30,
    # Per-opponent candidate ceiling. Was 500 (which never bit, since
    # max_per_opponent filters down to 5 anyway), so 1-for-1 / 2-for-1 /
    # 1-for-2 enumeration ran to the 3s deadline on every opponent
    # instead of short-circuiting once "enough" candidates were found.
    # 30 is comfortably above the 5-card-per-opponent target while still
    # bailing the inner loops early.
    "max_candidates":       30.0,
    # Trade ELO gap filter
    "trade_elo_gap_max":   250.0,
    # Agent A8 — trade-math adjustments (all behind feature flags)
    "qb_tax_rate":               0.075,  # 7.5% penalty when a side gets a premium QB
    "star_tax_per_tier_gap":     0.10,   # 10% penalty per tier gap beyond 1
    "star_tax_elite_multiplier": 1.5,    # extra multiplier when a Tier-1 star is traded away
    "roster_spot_penalty":       0.05,   # 5% penalty per extra roster spot used
    "roster_clogger_penalty":    0.10,   # 10% ADDITIONAL penalty per player beyond 2 in a 3+ one-way
    "roster_clogger_threshold":  3.0,    # 3+ players one-way triggers "clogger"
    # Tier-priority multipliers — applied to composite_score based on the
    # highest tier across both sides of the trade. Without this, the engine
    # gravitates to depth-vs-bench trades because mismatch math favors
    # players with high valuation variance (and depth tiers have more
    # variance than elites). User feedback: trade suggestions over-index
    # on depth tier; we want elite/starter players to dominate the deck.
    "tier_mult_elite":      1.60,
    "tier_mult_starter":    1.25,
    "tier_mult_solid":      1.00,
    "tier_mult_depth":      0.55,
    "tier_mult_bench":      0.35,
    # ------------------------------------------------------------------
    # Trade engine v2 (flag: trade_engine.v2) — Tier 1 plan + amendments
    # ------------------------------------------------------------------
    # Single value space (Change 1): elo_to_value() exponential transform
    "elo_value_k":           0.0050,  # steepness of Elo→value curve
    "elo_value_ref":      1500.0,     # Elo that maps to the reference value
    "elo_value_base":     1000.0,     # value at the reference Elo
    # KTC-style package adjustment exponent (amendment A2)
    "package_adj_gamma":     1.5,
    # True mutual gain (Change 3 + amendment A1)
    "min_side_surplus":    150.0,     # min per-side value gain to surface a trade
    "mutual_gain_cap":    1500.0,     # normalization ceiling for the harmonic mean
    # Interview 2026-07-17 ("loosen it") — for DIVERGENCE cards (both
    # members have real boards) the consensus fairness check is only an
    # extreme-case veto: the both-sides surplus gate already proves mutual
    # gain on the boards that matter. Effective divergence gate =
    # min(fairness_threshold, this). Consensus-basis cards keep the full
    # fairness_threshold (consensus IS the board there).
    "fairness_floor_divergence":  0.55,
    # ------------------------------------------------------------------
    # #189 — relaxed fallback for targeted jobs (pinned players and/or
    # acquire / trade-away positions) that produce ZERO cards under the
    # normal gates. Behavior only activates on otherwise-empty targeted
    # results (no flag needed); cards from a relaxed pass carry
    # relaxed=True + relaxed_reason so clients can label them honestly.
    # Stage 1 widens the fairness band to relaxed_fairness_threshold
    # (never tightening below the caller's request); stage 2 additionally
    # drops the both-sides surplus minimums to relaxed_surplus_floor
    # (0 still requires NON-NEGATIVE surplus on both boards). The #108
    # user-board epsilon gate and untouchables are NEVER relaxed.
    # ------------------------------------------------------------------
    "relaxed_fairness_threshold": 0.55,
    "relaxed_surplus_floor":       0.0,
    # ------------------------------------------------------------------
    # #172/#189 follow-up — asset-centric Upgrade / Lateral / Downgrade
    # ideas (flag: trade.asset_ideas; TradeService.generate_asset_ideas).
    # A counterpart asset within ±asset_ideas_lateral_band of the pinned
    # asset's consensus value classifies as a Lateral 1-for-1; above the
    # band it's an Upgrade target, below it a Downgrade piece. #198:
    # Upgrade/Lateral counterparts are additionally constrained to the
    # pin's POSITION (PICK pins keep pure value bands). Each of the three
    # groups is capped at asset_ideas_group_cap ideas, ordered by
    # |difference| (closest deals first; Downgrade puts same-position
    # headliners first).
    # ------------------------------------------------------------------
    "asset_ideas_lateral_band":   0.10,
    "asset_ideas_group_cap":      6.0,
    # ------------------------------------------------------------------
    # #384 W6-B — fairness-only packages around a fixed give-side anchor
    # (flag: calc.merged_layout; TradeService.generate_fair_packages).
    # ONE flat, swipeable list rather than three groups, so it gets one cap.
    # ------------------------------------------------------------------
    "fair_packages_cap":         20.0,
    # Waiver/roster-slot cost (amendment A3, FantasyCalc-derived ≈ rank-300 value)
    "waiver_slot_cost":    425.0,     # value cost per extra player received
    # Confidence shrinkage + range-overlap fairness (Change 4 + amendment A4)
    "shrink_pseudocount":    4.0,     # n0 in w = n/(n+n0) shrinkage toward seed
    "range_base":            0.35,    # value half-width FRACTION at n=0 comparisons
    # ------------------------------------------------------------------
    # Tier 2 — work item 2.1: marginal (over-replacement) valuation
    # (flag: trade.marginal_value — docs/plans/trade-engine-tier2-models.md)
    # ------------------------------------------------------------------
    "bench_credit_rate":         0.15,   # fallback fraction of raw value depth keeps
    # Interview 2026-07-17 — the depth discount is position- and
    # format-dependent: RB/WR depth is precious in 1QB (injuries/byes make
    # it near-startable), QB/TE depth is fungible there; superflex makes
    # QB depth startable capital and TE-premium does the same for TE.
    # marginal_value picks the per-position rate, with the _sf/_tep
    # overrides replacing the base rate in those formats.
    "bench_credit_qb":           0.10,
    "bench_credit_rb":           0.30,
    "bench_credit_wr":           0.30,
    "bench_credit_te":           0.10,
    "bench_credit_qb_sf":        0.35,
    "bench_credit_te_tep":       0.25,
    "waiver_baseline_value":   250.0,    # replacement floor when a position is thin
    # min_side_surplus replacement when the marginal flag is ON: marginal
    # values are systematically smaller than raw values (a package collapses
    # to over-replacement deltas + a 15% bench credit), so the raw-value
    # 150 bar would gate out nearly every legitimate marginal-gain trade.
    "min_side_surplus_marginal": 60.0,
    # #108 — user-board gain gate. Minimum value-space gain the USER must
    # see before a card surfaces, judged on the board the card is built
    # from: for 1-for-1 player swaps (any basis) the user's OWN raw board
    # (pre-shrinkage, pre-blend — "never send a player you rank above the
    # player you receive"); for consensus-basis cards additionally the
    # consensus package delta (receive − give), since consensus IS the
    # user's board there. 0.0 = receive must be at least as valuable as
    # give. Multi-asset divergence packages are exempt from the raw-board
    # check (the aggregate surplus gate is the compensation test).
    "user_gain_epsilon":         0.0,
    # #141 — junk-filler gate. In any multi-asset side, every piece beyond
    # the side's headliner (its best asset) must be worth at least this
    # FRACTION of that headliner, where each player is priced at the MAX
    # of the two boards (user's and opponent's raw value) — a filler one
    # side genuinely values is a legitimate piece; junk BOTH boards value
    # low never pads a suggestion. 0.25 ≈ a 277-Elo window below the
    # headliner (DP snapshot 2026-06-13: a Chase-headlined side [≈8470]
    # only accepts pieces ≥ ~2100 ≈ a mid 1st; a rank-100-headlined side
    # [≈1000] accepts ≥ ~250 ≈ rank 250, so depth-for-depth trades are
    # untouched). 0 disables (pre-#141 behavior). Applies to v2 pair,
    # v3 optimizer (incl. sweeteners) and consensus paths.
    "filler_min_frac":           0.25,
    # Interview 2026-07-17 ("both floors") — absolute companion to the
    # relative filler gate: every non-headliner piece must ALSO clear this
    # value-space floor on the same max-of-boards metric. ~450 = bottom of
    # the depth tier (Elo 1350); pure roster-clogger bodies below it never
    # pad a package. 0 disables. Headliners are exempt (deep-league 1-for-1
    # swaps of cheap players stay legal).
    "asset_floor_abs":         450.0,
    # Deck-eval 2026-07-17 — consolidation raw-delta sanity gate
    # (consensus path). The package_adj_gamma depth discount vaporizes a
    # VALUABLE second give asset (a 2940 WR contributes ~1181) while the
    # crown premium inflates the received stud, so a consensus-lopsided
    # 2-for-1 (Daniels + Odunze → Hurts, raw consensus Δ −2748) scored
    # fairness 0.99 and passed the #108 adjusted-delta gate. On a
    # user-give-side consolidation (more assets given than received) the
    # RAW consensus loss may not exceed this fraction of the raw give
    # total — the market's consolidation premium tops out around ~15%;
    # anything past it is an insult card. 0 disables (pre-fix behavior).
    "consolidation_raw_loss_frac": 0.15,
    # ------------------------------------------------------------------
    # Tier 2 — work item 2.2: outlook as now/future valuation blend
    # (flag: trade.outlook_blend). α = weight on NOW value; 1−α on FUTURE.
    # Age-curve breakpoints/slopes live as a code constant table
    # (_AGE_NOW_CURVE / _AGE_FUTURE_CURVE below) — see comment there.
    # ------------------------------------------------------------------
    "outlook_alpha_championship": 1.00,
    "outlook_alpha_contender":    0.75,
    "outlook_alpha_not_sure":     0.50,   # also used for outlook=None/unknown
    "outlook_alpha_rebuilder":    0.25,
    "outlook_alpha_jets":         0.10,
    # ------------------------------------------------------------------
    # Age-preference consensus multiplier — 2026-08-29 (operator decision,
    # evidence docs/business/analytics/2026-08-29-trade-disposition-review.md:
    # give-u23 cards ran a 9% like rate, receive-30plus 14%, while the
    # mirror shapes were the deck's best performers). Applied inside the
    # three consensus accessors (_vs here, trade_optimizer._sv,
    # trade_gen_v2.cval) via age_pref_value() below — cards are RE-PRICED,
    # never filtered. Band cut points mirror taste_service._age_band
    # (u23 = age<23, 30plus = age>=30) so tuning maps onto the same buckets
    # the evidence is measured in. Both mults at 1.0 = byte-identical
    # accessors (the helper short-circuits) — the deploy-free kill; arm A
    # pins them there in MODEL_A_PROFILE (the pre-wave engine had no age
    # preference). The cap bounds only INCREASES (operator: "a maximum
    # value increase"), is unread while both mults are 1.0, and <= 0
    # disables it.
    # ------------------------------------------------------------------
    "age_pref_mult_u23":          1.10,
    "age_pref_mult_30plus":       0.90,
    "age_pref_boost_cap":         500.0,
    # Backlog #1 — opponent outlook inference (flag: trade.outlook_infer).
    # Weights on the three contend↔rebuild signals + the score cutoffs that
    # bucket into contender / not_sure / rebuilder. See infer_team_outlook.
    "infer_w_vet_share":          1.00,
    "infer_w_youth_share":        1.00,
    "infer_w_pick_share":         2.00,
    "infer_contender_cut":        0.08,
    "infer_rebuilder_cut":       -0.08,
    # #365 — net first-round-pick capital (flag: trade.outlook_net_firsts).
    # Weight on clamp((firsts acquired − firsts traded away) / firsts
    # originally yours). Calibrated on the only real pick corpus available
    # (docs/feedback/items/365-window-signals/scope.md §7.1): across 24
    # member-league pairs |net_share| <= 0.75, so at 0.10 the observed
    # contribution range is ±0.075 against a not_sure band ±0.08 wide — the
    # term can move an extreme team ONE bucket and can never move any team
    # two. Set to 0 to keep the card showing the ledger while it stops
    # scoring it. The cap binds only a team that shipped more firsts than it
    # originally owned in the horizon.
    "infer_w_net_firsts":         0.10,
    "infer_net_firsts_cap":       1.00,
    # #372 — the COMPOSITE weight vector (flag: trade.outlook_composite).
    # Operator, 2026-08-20: "age distribution alone is not a strong enough of
    # a signal. We calculate starter dynasty value. Let's incorporate that and
    # playoff likelihood. The age distribution can stay but make it a lighter
    # driver."
    #
    # These are a SEPARATE NAMESPACE from the five `infer_w_*` keys above on
    # purpose: the legacy vector is what every engine caller still scores
    # with, and reusing its keys would mean the composite could not be tuned
    # without moving the engine. Set `infer_composite_w_starter` and
    # `infer_composite_w_playoff` to 0 and the composite degenerates to a
    # down-weighted age model — a knob-only rollback below the flag.
    #
    # Calibration, on 12 real prod leagues / 156 teams
    # (docs/feedback/items/372-window-composite/scope.md §7):
    #   legacy    101 rebuilder / 26 not_sure /  29 contender  (65 % rebuilder)
    #   composite  62 rebuilder / 40 not_sure /  54 contender
    # The legacy vector's rebuilder skew is the whole of what #365/#371/#372
    # keep reporting. The cuts (±0.08) are UNMOVED — see D-140.
    "infer_composite_w_vet":      0.40,   # was 1.00 — "lighter driver"
    "infer_composite_w_youth":    0.40,   # was 1.00
    "infer_composite_w_pick":     2.00,   # unchanged; pick capital is not age
    # Starter-value index = (your starters' value / the league's mean) − 1, so
    # 0 is an average starting lineup and +0.50 is 50 % above it. Capped
    # because one absurd roster must not swamp every other term: at 0.60 the
    # capped contribution is ±0.30, roughly four times the not_sure band.
    "infer_composite_w_starter":  0.60,
    "infer_composite_starter_cap": 0.50,
    # Playoff index = (playoff_pct − centre) / centre-half-width, i.e.
    # 2·(pct − 0.50). 0.50 is NOT invented here: it is the midpoint of the
    # `tossup` band (`outlook.trade_delta.playoff_band`: likely >= 0.65,
    # unlikely < 0.35), so the neutral point of this term is the neutral point
    # of the band map every client already renders. At the `likely` edge the
    # contribution is 0.40·0.30 = 0.12, which on its own clears the 0.08
    # contender cut — a genuinely likely playoff team should be called one.
    "infer_composite_w_playoff":  0.40,
    "infer_composite_playoff_center": 0.50,
    "infer_composite_playoff_cap": 1.00,
    # ------------------------------------------------------------------
    # Tier 2 amendment A6 — league-wide deck diversification
    # (flag: trade.deck_diversity — consumed by server._order_deck)
    # ------------------------------------------------------------------
    "diversity_window_days":      7.0,   # lookback for league impression counts
    "diversity_user_cap":         3.0,   # >= this many OTHER members shown a target → penalize
    "diversity_penalty":          0.6,   # ordering-key multiplier for saturated targets
    "deck_max_per_target":        3.0,   # intra-deck cap: cards per top receive asset
    # ------------------------------------------------------------------
    # F2 — Thompson v2 bandit hygiene (flag: deck.thompson_v2 —
    # consumed by server's v2 sampler inside _order_deck)
    # ------------------------------------------------------------------
    "thompson_prior_base_rate":   0.59,  # p̂ fallback when the trailing-30d global like rate is too thin (all-time global rate 13/22 as of 2026-07-26)
    "thompson_decay_gamma":       0.995, # per-day posterior decay γ, applied lazily at read time
    # ------------------------------------------------------------------
    # F3 — fatigue & durable suppression (flag: deck.fatigue — consumed
    # by server's fatigue/suppression layer around _order_deck).
    # Multiplier (LinkedIn impression-discounting form, viewed rows only):
    #   fatigue = w1·exp(−a·impCount) + w2·exp(−b·daysSinceLastSeen)
    # clamped to [fatigue_floor, 1.0] and applied only to items with ≥1
    # viewed impression inside fatigue_lookback_days — full recovery comes
    # from impressions aging out of the window; the w2 term is a small
    # recency credit (a just-seen item keeps continuity; the impression
    # count is the fatigue driver). Archetype accrual reuses the same form
    # with the weaker fatigue_arch_a. Never boosts (≤ 1.0 by construction).
    # ------------------------------------------------------------------
    "fatigue_w1":                 0.85,
    "fatigue_w2":                 0.15,
    "fatigue_a":                  0.18,  # per-impression decay, item level (trade_hash / centerpiece)
    "fatigue_b":                  0.10,  # per-day decay of the recency credit
    "fatigue_arch_a":             0.05,  # weaker per-impression decay at archetype level
    "fatigue_floor":              0.25,  # multiplier never drops below this
    "fatigue_lookback_days":     30.0,   # viewed impressions older than this stop counting
    "fatigue_session_hours":      8.0,   # deck-session window for the 2+-pass demotion
    "fatigue_session_demotion":   0.2,   # multiplier for 2+ passes on one centerpiece in a session
    "fatigue_decline_suppress_days": 30.0,  # hard near-duplicate window after a decline
    "fatigue_decline_value_band": 0.10,  # near-duplicate ⇔ package value within ±this fraction
    "fatigue_retest_mult":        0.5,   # low-exposure multiplier for the ONE post-window retest card
    # Dismiss cooldown (D-067, docs/plans/pass-cooldown/plan.md). The UI's
    # "dismiss" is decision='pass'. Unlike the fatigue_* knobs above this is a
    # HARD exclusion window, not a multiplier — soft demotion (floored at
    # fatigue_floor) is what let dismissed cards resurface. 7.0 restores the
    # pre-fix behavior; likes keep their own separate 7-day window.
    "pass_cooldown_days":        14.0,
    # Legacy-dismiss amnesty (D-067, operator 2026-08-17). Dismisses recorded
    # BEFORE this instant are exempt from the cooldown — they carry no reason
    # (decline-reason capture, D-066, landed 2026-08-17T22:22:56Z), so
    # suppressing on them would apply the avoidance rule to taps the user was
    # never given a chance to explain. Unix epoch seconds; 0 disables the
    # amnesty (every dismiss counts, whatever its age).
    "pass_cooldown_start_epoch": 1787005800.0,   # 2026-08-17T22:30:00Z
    # ------------------------------------------------------------------
    # F5 — trade-taste vectors (flag: deck.taste_vectors — consumed by
    # backend/taste_service.py + server's taste layer around _order_deck).
    #   final = base × clamp((1 + η_l·prefMatch_long)·(1 + η_s·prefMatch_short),
    #                        taste_clamp_lo, taste_clamp_hi)
    # prefMatch = normalized cosine of the decayed taste vector against the
    # card's attribute set — 0 for a zero-history user, so the multiplier
    # is exactly 1.0 (flag-off-identical ordering). Applied AFTER all
    # generation gates: reorders acceptable trades, never rescues gated ones.
    # ------------------------------------------------------------------
    "taste_eta_long":             0.2,   # long-τ prefMatch weight (η_l)
    "taste_eta_short":            0.3,   # short-τ prefMatch weight (η_s)
    "taste_clamp_lo":             0.7,   # final taste multiplier floor
    "taste_clamp_hi":             1.4,   # final taste multiplier ceiling
    "taste_tau_short_days":      21.0,   # short-interest decay τ
    "taste_tau_long_days":      180.0,   # long-interest decay τ
    "taste_dwell_ms":          8000.0,   # dwell_ms ≥ this ⇒ long-dwell bonus applies
    "taste_dwell_bonus":          0.3,   # reward added on a long dwell
    "taste_epsilon":             0.05,   # GC floor — rows with both |w| below vanish on read/update
    "taste_prior_scale":         10.0,   # board-prior ceiling ≈ this many likes of weight
    "taste_prior_shrink":        20.0,   # per-attr ranked-count shrinkage n/(n+this)
    "taste_prior_ref_delta":     0.25,   # |board-vs-consensus| rel delta treated as "strong"
    # ------------------------------------------------------------------
    # F7 — exploration slots & archetype audition (flag: deck.exploration
    # — consumed by server's exploration layer after _order_deck).
    # One wildcard per deck of ≥ exploration_min_deck cards, inserted at
    # the fixed slot position, drawn uniformly from gate-passing
    # candidates OUTSIDE the served deck (bottom prefMatch tercile /
    # low-data F2 arms / uniform fallback, plus auditioning archetypes).
    # exploration_rate feeds ONLY the logged propensity
    # (rate × 1/|eligible pool|) — slot frequency is 1 per eligible deck.
    # ------------------------------------------------------------------
    "exploration_rate":           0.125, # propensity numerator (PRD ≈ 1-in-8 slot share)
    "exploration_slot_position":  5.0,   # 1-indexed served slot, clamped to [4, 6]
    "exploration_min_deck":       8.0,   # decks below this get no wildcard
    "exploration_overgen":        3.0,   # extra per-opponent candidates generated for the draw pool
    # Per-opponent keep — the base the over-generation is added to and the
    # width `server._split_exploration_pool` trims back to. Was the hardcoded
    # module constant `server._EXPLORATION_BASE_PER_OPP = 5`, which is what
    # made a `max_per_opponent` change a no-op on the served deck
    # (docs/plans/full-sweep/plan.md §3.3). 5.0 reproduces that constant
    # exactly, so this is behaviour-neutral at the default.
    "exploration_base_per_opp":   5.0,   # served cards kept per opponent
    # trade.full_sweep wall-clock safety rail (docs/plans/full-sweep/plan.md
    # §3.5). Removing the `global_target` exit removes the only practical
    # ceiling on a job: the CONSENSUS per-pair path carries a 1.0s deadline,
    # but `trade_optimizer.generate_pair_trades_v3` explicitly has none
    # ("No deadline, no iteration budget", trade_optimizer.py:231), so a slow
    # league would otherwise run to `server._JOB_HARD_TIMEOUT` (60s). Checked
    # per opponent, so the budget bounds when the sweep STOPS starting new
    # pairs, not the pair already in flight. <= 0 disables the rail.
    # Read only when the flag is on — flag-off never evaluates it.
    "full_sweep_budget_s":       30.0,   # seconds of opponent sweep before stop
    "audition_min_views":        30.0,   # viewed impressions before an audition verdict
    "audition_like_rate_frac":    0.5,   # graduate at like-rate ≥ this × global base rate
    "audition_retire_days":      30.0,   # retirement window before a failed archetype re-auditions
    # ------------------------------------------------------------------
    # F9 — first-session win engineering (flag: deck.first_session —
    # consumed by server's first-deck layer after the F7 wildcard slot).
    # Confidence bar (per card, _first_session_confidence_ok): simple
    # shape (per side ≤ first_session_max_side_assets AND total assets ≤
    # first_session_max_total_assets ⇒ 1x1 / 2x1 / 1x2 at defaults), every
    # asset consensus-seeded at ≥ first_session_min_seed_elo (the high-data
    # check — the seed map is the consensus signal the generation path
    # already computes; a user's own comparison counts are ~0 on a first
    # deck by definition), and strong margin: divergence cards need
    # mismatch_score ≥ first_session_min_margin; consensus-basis cards
    # (mismatch 0 by construction) need fairness_score ≥
    # first_session_min_fairness instead.
    # ------------------------------------------------------------------
    "first_session_top_k":            5.0,   # confidence-weighted top region (unlocked slots)
    "first_session_min_margin":      40.0,   # divergence-card mismatch_score bar
    "first_session_min_fairness":     0.85,  # consensus-card fairness_score bar
    "first_session_min_seed_elo":  1250.0,   # every asset must be consensus-seeded ≥ this
    "first_session_max_side_assets":  2.0,   # per-side asset cap for "simple shape"
    "first_session_max_total_assets": 3.0,   # total asset cap for "simple shape"
    "first_session_deck_max":        10.0,   # first decks clamp to ≤ this many cards
    "first_session_deck_min":         8.0,   # documented target floor (no padding — max clamps only)
    # ------------------------------------------------------------------
    # F10 — weekly deck replenishment (flag: deck.replenishment —
    # consumed by server._run_weekly_replenishment inside daily-tick)
    # ------------------------------------------------------------------
    "replenish_weekday":          2.0,   # Python weekday the weekly run unlocks (2 = Wednesday, post-waivers)
    # ------------------------------------------------------------------
    # Tier 3 — trade_optimizer.py (flags: trade_engine.v3, trade.three_team)
    # ------------------------------------------------------------------
    "v3_pool_size":              12.0,   # per-side candidate pool for exact enumeration
    "sweetener_band":             0.15,  # fairness shortfall band eligible for a sweetener
    "sweetener_max_cards":        2.0,   # max sweetened cards per opponent pair
    # 2026-08-21 gap auto-sweetener (operator-commissioned; the ratio gate
    # is scale-blind, so a "fair" 0.85 on a big package can still be a
    # late-1st of absolute consensus gap — CHANGELOG 2026-08-21: 15% of
    # served cards carried gap > a late 1st). When a candidate card's
    # |give_value − receive_value| exceeds this threshold (value units;
    # 1539 = one late 1st, the operator's agreed line), generation tries
    # to close it by ADDING the smallest sufficient asset from the richer
    # side's roster (trade_optimizer.close_value_gap). Runs at generation
    # time per-arm, never post-draft. ≤ 0 disables the pass entirely
    # (arm A's pin — the pre-wave engine had no sweetener).
    "sweetener_gap_threshold": 1539.0,
    "cycle_edge_min_gain":      100.0,   # min per-transfer marginal gain for a cycle edge
    "cycle_min_net":            200.0,   # min net gain per team for a 3-team cycle
    "cycle_max_results":          3.0,   # max 3-team cycles returned per league
    # Tier 2 (2.3b) — fuzzy mirror matching tolerance (consumed by server)
    "fuzzy_match_tau":            0.8,   # Jaccard threshold per side
    # Tier 2 (2.3a) — likes-you user-gain floor (D-055, consumed by server).
    # Minimum net consensus value (receive − give, summed player values in
    # v2 value space) the VIEWER must clear for a leaguemate's liked trade
    # to be mirrored into their deck. -500 = the ratified deck-eval
    # materiality floor: a like the viewer loses more than 500 of consensus
    # value on is an insult, not an opportunity. Set very negative to
    # restore pre-D-055 behavior (no floor).
    "likes_you_min_user_delta": -500.0,
    # D-096 (2026-08-19) — the likes-you quality ladder, read by
    # server._likes_you_gate_level. 0 = pre-D-096 behaviour EXACTLY (the
    # raw-sum floor above, no presentment gates); 1 = the floor moves to
    # `likes_you_min_user_gain` on PACKAGE-ADJUSTED values (the numbers the
    # TradeValueBar renders); 2 = level 1 plus directional R1 (overpay_ok)
    # and filler_ok. `likes_you_gate_level = 0` is the one-value deploy-free
    # revert; `likes_you_min_user_delta` above is deliberately unchanged so
    # that revert is exact.
    "likes_you_gate_level":        2.0,
    # The floor at gate level >= 1, in package-adjusted v2 value space.
    # 0.0 == `user_gain_epsilon`: the identical rule the gated generators
    # already apply to the consensus package delta, so the likes-you
    # surface now obeys the same user-gain rule as the rest of the deck.
    "likes_you_min_user_gain":     0.0,
    # Deck composition (verified against real data 2026-06-09)
    "v3_diversity_max_overlap":   0.4,   # max asset Jaccard between two cards of one pair
    "consensus_score_scale":      0.3,   # consensus fallback cards rank below divergence finds
    # FB-47 finder targeting (flag trade.finder_targeting) — counterparty
    # positional-fit blend: composite *= 1 + w * (fit - 0.5), fit ∈ [0,1].
    # Consensus cards lean on fit hard (no divergence signal to compete
    # with); divergence cards keep it at tiebreak strength.
    "fit_consensus_weight":       0.5,
    "fit_divergence_weight":      0.15,
    # FB-96 (flag trade.need_fit) — automatic positional-need fit:
    # composite *= 1 + w * (need_fit - 0.5), need_fit ∈ [0,1]. Bounded
    # multiplier applied AFTER all gates — reorders acceptable trades,
    # never rescues gated ones. 0 disables the reordering entirely.
    # 0.30 → 0.15 per interview 2026-07-17: need counting (bodies vs
    # slots) is right but should stay a LIGHT multiplier (±7.5%).
    "need_fit_weight":            0.15,
    # FB-147 engine hook (flag trade.block_boost) — SOFT, acquire-side
    # trade-block boost: a card whose ACQUIRE side holds ≥1 player the
    # counterparty flagged "on the block" gets composite *= 1 + this weight.
    # Bounded multiplier applied AFTER all gates — reorders acceptable trades,
    # never rescues a gated one, exactly like need_fit_weight. 0 = no-op
    # (composite byte-identical, no stamp). ±15% at the default, matching the
    # light-multiplier calibration the interview set for need_fit.
    "block_boost_weight":         0.15,
    # ------------------------------------------------------------------
    # Interview phase 2 (docs/plans/trade-logic-interview-2026-07-17.md)
    # ------------------------------------------------------------------
    # trade.lanes — a card is a "window" move when the value-weighted mean
    # now/future lean of what changes hands, signed by the user's window
    # direction, clears this fraction. Below it (or with no window) the
    # card is a "value" move.
    "lane_shift_frac":            0.10,
    # trade.fit_premium — max raw-board value the user may PAY on a
    # flagged 1-for-1 that fills a positional need from a non-need spot.
    "fit_premium_max_loss":     300.0,
    # trade.aggression_ab — composite reweight strength for the
    # light/fair/generous opening-offer buckets (± at full ±45% tilt).
    "aggression_weight":          0.20,
    # ------------------------------------------------------------------
    # Feedback #175 — directional outlook weighting
    # (flag: trade.outlook_direction — see outlook_direction_mult)
    # ------------------------------------------------------------------
    # Rebuild-side (rebuilder/jets), on the card's value-weighted now-lean
    # shift from the USER's perspective (received − given, classify_lane's
    # exact shift): positive shift (acquiring win-now production) ⇒
    # composite *= max(0.05, 1 − penalty·shift); negative shift (acquiring
    # future capital: younger players, picks) ⇒ *= 1 + boost·(−shift).
    "outlook_dir_penalty":        3.0,
    "outlook_dir_boost":          1.0,
    # Contend-side (championship/contender) mild symmetric mirror:
    # composite *= 1 + w·shift. No age-gap rule (contenders buy vets).
    "outlook_dir_contend_weight": 0.5,
    # The ~1-year-gap rule (rebuild-side only): when the primary give is a
    # player and the primary return is an OLDER player past this tolerance
    # (years), with no comparable-value pick / younger-player component in
    # the return, the card is near-excluded: composite *= age_gap_mult.
    # A component "comparable" ⇔ its consensus value ≥ rescue_frac × the
    # primary give's consensus value.
    "outlook_dir_age_tolerance":  1.0,
    "outlook_dir_age_gap_mult":   0.15,
    "outlook_dir_rescue_frac":    0.5,
    # ------------------------------------------------------------------
    # Fit-congruence signal weighting (the fit-congruence decision, D-060
    # — see fit_congruence_mult). Deck swipes feed Elo through
    # RankingService.record_trade_signal at trade_k_like / trade_k_pass;
    # these scale that K by how surprising the action is given the user's
    # window, using the SAME signed lane shift (signed_lane_shift, threshold
    # lane_shift_frac) the deck already computes at generation.
    # ------------------------------------------------------------------
    # Fit-EXPLAINED — the window already predicted the action (like on a
    # window-congruent card, pass on an anti-window one). Discounted: it is
    # a weaker valuation statement than it looks.
    "fit_k_explained_mult":       0.4,
    # Fit-DEFYING — the action contradicts the window (pass on a
    # window-congruent card, like on an anti-window one). Full K; NOT
    # boosted above baseline without data to justify it.
    "fit_k_defying_mult":         1.0,

    # ------------------------------------------------------------------
    # suggestion.telemetry (matchmaking research item 1; scope block
    # docs/plans/matchmaking-engine/telemetry-scope.md; read via
    # suggestion_telemetry._cfg — the _deck_cfg pattern).
    # ------------------------------------------------------------------
    # Ghost holdout: withhold ~1-in-N organic deck cards from display
    # (logged with is_ghost=1). ≤0 disables ghosting without touching the
    # flag — the deploy-free rollback lever.
    # OPERATOR RULING 2026-08-21 (batch-wide, living-memory/CHANGELOG.md
    # 2026-08-21): "I still am against the ghost cards" — ghosts are ruled
    # out entirely, not merely paused. Ghost accumulation was also the
    # amplifier behind the 6-card-repeat deck (a ghost can never be
    # decided, so it never leaves the FFV3 pool; one hash ghost-served
    # 35x). The prod model_config row is already 0; this default makes the
    # code agree with the ruling instead of relying on a live DB row.
    "ghost_holdout_one_in":        0,
    # Executed-trade matcher: only suggestions served within this many days
    # BEFORE the trade executed are match candidates.
    "suggestion_match_lookback_days": 14,
    # Partial-match floor: matched-token share of the larger asset set.
    "suggestion_match_min_overlap":   0.5,

    # ------------------------------------------------------------------
    # trade.bakeoff — three-model bake-off (docs/plans/three-model-bakeoff/
    # PLAN.md; read via bakeoff_runner._cfg — the _deck_cfg pattern). Both
    # keys are inert while the flag is off.
    # ------------------------------------------------------------------
    # Serving mode: 0 = Phase-4 DARK validation (all three arms generate and
    # log, only arm `current` is served, presentation stack untouched);
    # 1 = Phase-5 interleaved serving (team-draft deck, post-generation
    # re-rankers bypassed per PLAN.md §3.4 Channel 2).
    "bakeoff_serve_interleaved":   0.0,
    # Max cards in the served bake-off deck. Default 30 = the three-group
    # composition (3 groups x bakeoff_group_size). 0 = uncapped, which with
    # bakeoff_group_size = 0 restores Phase 3's plain drain-every-arm draft.
    "bakeoff_deck_limit":         30.0,
    # ---- deck composition (operator decision 2026-08-18; scope block
    # docs/plans/three-model-bakeoff/scope-composition.md) ----------------
    # Cards per GROUP. A group is (arm, basis): the engine arms contribute a
    # divergence group and a consensus group each, arm gen_v2 one group (it
    # is divergence by nature). 0 = kill the whole composition layer and fall
    # back to Phase 3's plain per-ARM team draft.
    "bakeoff_group_size":         10.0,
    # Value-lane slots inside each group. The outlook-lane ("window") slots
    # are the remainder, bakeoff_group_size - this, so the two can never sum
    # to something other than the group size.
    "bakeoff_group_value_slots":   5.0,
    # Residual-slot fill policy when a lane cannot fill its quota (expected:
    # `window` is ~19% of divergence supply, so the divergence groups will
    # under-fill their outlook slots routinely). 0 = LEAVE SHORT — the group
    # serves fewer cards and the shortfall is recorded per (group, lane);
    # 1 = backfill from the same group's other lane / unlabelled remainder,
    # every substituted card flagged deck_impressions.lane_slot = 'fill'.
    "bakeoff_fill_policy":         0.0,
    # Lane reallocation (D-086, 2026-08-19). 1 = DEFAULT: a lane that met its
    # quota may extend into slots the OTHER lane could not fill, drawing only
    # from its own bucket, so no card ever occupies the other lane's slot and
    # `lane_slot` stays literally true. Orthogonal to bakeoff_fill_policy,
    # which substitutes ACROSS lanes and flags the substitute. `short` is
    # still computed against the nominal quota before reallocation and the
    # spill is recorded in groups_json[key].realloc, so the under-fill finding
    # D-078 protects is fully preserved — the deck just stops shrinking to
    # restate it. 0 restores the pre-D-086 composition exactly.
    "bakeoff_lane_reallocate":     1.0,
    # Arm roster. 0 (default, operator decision 2026-08-18) = arm `baseline`
    # is NOT in the served rotation and is not generated at all; Phase 2's
    # MODEL_A_PROFILE / model_a() / golden / knob-inventory guard all stay
    # live and passing, so flipping this to 1 restores arm A as a first-class
    # arm (and its two groups) with no deploy.
    "bakeoff_include_baseline":    0.0,

    # ------------------------------------------------------------------
    # trade_gen.v2 — divergence-driven staged pipeline (backend/
    # trade_gen_v2.py; matchmaking research item 2, flag default OFF).
    # All knobs documented in docs/config-reference.md § trade_gen.v2.
    # ------------------------------------------------------------------
    # Dual-board ε-gain: min own-board gain PER SIDE (value space, on
    # consolidation-discounted packages). Extends the #108 user_gain_epsilon
    # convention to both sides of every generated package; 100 ≈ 5% of a
    # generic mid-1st, between the existing marginal (60) and raw (150)
    # surplus floors — big enough to beat board noise, small enough to
    # keep genuinely mutual depth trades alive.
    "gen2_epsilon":             100.0,
    # Consensus fairness band half-width: discounted consensus package
    # values must satisfy min/max ≥ 1 − band (±15% — the research's
    # defensibility band, round-2/02 BP 5).
    "gen2_band":                  0.15,
    # Consolidation discount curve (see trade_gen_v2.consolidated_value):
    # contribution(v) = v·(floor + (1−floor)·(v/v_best_own)^γ). Junk
    # contributes ≈ floor·v, so packages can't be stuffed to fairness.
    "gen2_consol_gamma":          1.5,
    "gen2_consol_floor":          0.15,
    # Stage-1/2 pool sizes: centerpieces per opponent, user-side return
    # pool, receive-side balancing extras. NOTE: gen2_centerpiece_top_k
    # bounds SEARCH BREADTH (which opponent assets anchor a package
    # search), never output length — the engine returns every gate
    # survivor (operator decision 2026-08-16: no engine truncation).
    # Raised 3 → 5 with that decision: at 3, deep divergent rosters
    # starved the browse tier of centerpiece variety; 5 keeps worst-case
    # enumeration ≈ 9.6k combos/pair, well under the safety budget.
    "gen2_centerpiece_top_k":     5.0,
    "gen2_give_pool":            10.0,
    "gen2_recv_extra_pool":       4.0,
    # Minimum own-board divergence (value space) for a centerpiece.
    "gen2_min_divergence":        0.0,
    # Exposure shaping (round-1/03 BP 1-2): per-counterparty appearance cap
    # per batch + guaranteed floor for every counterparty with ≥1 viable
    # suggestion.
    "gen2_exposure_cap":          3.0,
    "gen2_exposure_floor":        1.0,
    # Batch dedup: Jaccard overlap of combined asset sets (same
    # counterparty) at-or-above this is a near-duplicate.
    "gen2_dedup_jaccard":         0.6,
    # MESO variants: recipient-board equivalence band (±fraction of the
    # base return package's opp-board value) and max variants per top card.
    "gen2_meso_band":             0.05,
    "gen2_meso_max_variants":     3.0,
    # Completion-probability hook: empirical-Bayes shrinkage strength
    # (pseudo-observations) and the global acceptance prior fallback.
    "gen2_accept_prior_strength": 10.0,
    "gen2_accept_global_prior":   0.5,
    # Youth-heavy MESO shape: value-weighted mean age at or below this.
    "gen2_youth_age":            25.0,
    # Tier metadata (operator decision 2026-08-16 — scarcity lives in the
    # tier field, not in list length): cards after the single "endorsed"
    # pick that rank inside this count are "featured"; the rest of the
    # full ranked survivor set is "browse".
    "gen2_featured_count":        4.0,
    # G6 presentment-rule parity (ported 2026-08-16, operator directive —
    # ahead of the G6 wave's own v1-path merge; rules + reconciliation
    # note in trade_gen_v2.py § G6 parity, addendum in docs/plans/
    # matchmaking-engine/trade-gen-v2-scope.md). PROVISIONAL: at G6-merge
    # reconciliation these alias/align to G6's calibrated v1 knobs
    # (pos_net_cap / pick_gap_frac / pick_gap_min_value) — one source of
    # truth. [G6 merged 2026-08-16: values verified aligned (cap 1.0,
    # frac 0.8, min 300 via module constant); true aliasing deferred to
    # the gen-v2 lighting checklist per the G6 scope amendment.]
    # #341 net-position cap: |count(recv at P) − count(give at P)| ≤ cap
    # for each P in {QB, RB, WR, TE}; picks uncounted. 1 = rule on with
    # cap 1; ≤ 0 disables (per-rule kill switch).
    # #339 pick-not-the-gap two-sided band: for a raw-consensus gap ≥ 300,
    # kill when a heavier-side pick sits inside [frac×gap, gap/frac].
    # 0 disables. 0.8 mirrors the G6 spec default — unmeasured pending the
    # pick-league replay (G6 prd R-12).

    # ------------------------------------------------------------------
    # trade.presentment_rules — G6 2026-08-16 feedback wave
    # (#304 #336 #339 #340 #341; docs/feedback/items/304-positional-need-
    # filter/). Construction rules R1/R2/R3 + need gate R5 run inside the
    # v1 generators (v3 loop, v2 _consider, consensus _emit, sweetener
    # re-validation); R4 (windowless awaiting/matched exclusion) has no
    # knob — the flag is its revert. Each rule dies live via its knob's
    # disable value (PUT /api/admin/config/<key>), the whole group via the
    # flag. Units: raw summed consensus value (seed_value per side) — the
    # D-055 Δ currency.
    # ------------------------------------------------------------------
    # R1 #340 — absolute overpay ceiling, BOTH sides, independent of
    # fairness_threshold (the client fairness toggle can never relax it).
    # KILL when gap >= max_overpay_min_value AND gap/max(g,r) >=
    # max_overpay_frac. frac <= 0 disables; the floor is D-055 materiality.
    "max_overpay_frac":           0.25,
    "max_overpay_min_value":    500.0,
    # R2 #341 — per-position signed net cap over {QB,RB,WR,TE}:
    # |count(recv at P) − count(give at P)| <= cap. Picks uncounted (a
    # pick is not a positional body). 0 disables (filler_min_frac
    # convention).
    "pos_net_cap":                1.0,
    # R3 #339 — "the pick IS the gap": for gap >= pick_gap_min_value, kill
    # when a pick on the heavier side sits inside the two-sided band
    # [frac × gap, gap / frac]. A pick far larger than the gap (stud-scaled
    # centerpiece consolidation) passes. frac 0 disables; DEFAULTS ARE
    # UNMEASURED (0 pick cards in the D-055 corpus) — tuning is the R-12
    # build-phase replay task, this knob is the named lever.
    "pick_gap_frac":              0.8,
    "pick_gap_min_value":       300.0,
    # R5 #304 — window-scaled need gate on the primary received player of
    # UNTARGETED discovery decks (targeted jobs bypass, R-5b). Sub-floor
    # receives always pass; need_gate_min_value <= 0 disables the gate.
    # upgrade_margin 0 = any strict upgrade over the post-give incumbent
    # passes.
    "need_gate_min_value":      500.0,
    "need_gate_upgrade_margin":   0.0,

    # ------------------------------------------------------------------
    # Knockout refine — 2026-08-23 (docs/plans/knockout-refine/plan.md §3;
    # verdict + evidence docs/reviews/2026-08-22-knockout-rules-judged.html
    # §03). Four refinements to the G6 knockouts above, each with its own
    # kill knob whose 0 restores the predicate byte-identically and is a
    # deploy-free revert (PUT /api/admin/config/<key>). Same five-
    # registration discipline as the fit/breaker/negmem blocks below: this
    # dict, database._MODEL_CONFIG_DEFAULTS, _PINNED_KNOBS in
    # test_bakeoff_arm_a_golden.py, the scope-phase2.md disposition
    # sentence, and the config-reference row.
    # ------------------------------------------------------------------
    # C1 — R5 two-sided. 1.0 (default, LIT at merge): `need_gate_ok` judges
    # EVERY non-pick received asset for the hole/upgrade tests, and gains a
    # dual-need rescue (user sheds surplus at a position the partner is
    # short at, read off the per-member `opp_ctx`). 0 = the primary-only
    # one-sided kill. Measured one-sidedness 96.3% → 88.7%.
    "need_gate_dual_rescue":      1.0,
    # C2 — R1 in the currency the card shows. 1.0 (default, LIT): price
    # both sides with `package_value_v2` on the consensus emit path's
    # argument convention before taking the gap. 0 = raw consensus sums.
    # `max_overpay_frac` / `max_overpay_min_value` are unchanged by this;
    # a 1-for-1 is identity under `package_value_v2`, so only multi-asset
    # packages can move.
    "overpay_adjusted":           1.0,
    # C3 — R2 quality-aware. 1.0 (default, LIT): an over-cap position may
    # survive when the shedding side was strictly above starter need there
    # before and BOTH rosters stay at/above it after, counted in startable
    # bodies. 0 = today's flat |net| <= pos_net_cap kill. Needs the
    # per-member `opp_ctx`; without one the flat kill stands.
    "pos_net_starter_relief":     1.0,
    # C4 — the v3 optimizer's package-shape rule, previously the literal
    # `abs(len(give) - len(recv)) > 1`. 1.0 (default) IS that rule, byte-
    # identical. Read by trade_optimizer via the module object (D-098). 2
    # is the post-merge prod-bundle flip that unlocks 3-for-1 / 1-for-3 —
    # the operator's own stated trade style, and 0.5% of served cards
    # today. Registered here (not with an inline literal default) so `_c`
    # resolves it, `_cfg_override` reaches it, and the bake-off arms can
    # pin it; the sole consumer lives in trade_optimizer.py.
    "v3_shape_max_delta":         1.0,

    # ------------------------------------------------------------------
    # Engine quality — 2026-08-18 field wave (docs/plans/engine-quality/
    # scope.md). Five independent ranking/gating fixes for the two
    # defects diagnosed from the live corpus: picks buying fairness for
    # free (A) and one high-divergence asset flooding a whole deck (B).
    # Same per-rule kill-switch convention as the G6 knobs above: each
    # key's disable value restores byte-identical prior behaviour and is
    # a deploy-free revert (PUT /api/admin/config/<key>). Defaults are ON
    # because today's behaviour IS the bug.
    # ------------------------------------------------------------------
    # C1 — divergence-gated RANKING fairness. An asset enters the "signal
    # core" (the sub-package the ranking fairness term is priced on) only
    # when the two boards disagree about it by at least this FRACTION of
    # its own value. Picks sit at exactly 0 by construction, so they can
    # never move the ranking fairness ratio. The fairness GATE and the
    # card's stamped fairness_score still price the REAL package.
    # 0 disables (ranking fairness = full-package fairness, as before).
    "rank_div_min_frac":          0.02,
    # C2 — minimal-package preference in the pinned/targeted asset-ideas
    # ranker. Variants whose |receive − give| gaps fall in the same band
    # (width = frac × the pinned asset's consensus value) are treated as
    # equivalent, and the one with FEWER pieces wins. Outside the band
    # the closer deal still wins, so a genuinely needed sweetener is
    # never dropped. Units are FAIRNESS, measured from the best variant
    # of the same search: a variant within 0.10 fairness of the best is
    # near-equivalent, so a bare deal at 0.79 beats its sweetened sibling
    # at 0.85 (the sweetener is not buying enough to justify the extra
    # asset), while a bare deal at 0.57 still loses to a sibling at 0.70.
    # 0 disables (closest-gap-wins, as before).
    "min_package_band":           0.10,
    # C3 — matched-pick-pair strip in pick_swap_ok. Picks are paired
    # across the two sides best-first; a pair whose min/max consensus
    # value ratio is at or above this frac is "matched" — zero divergence
    # both ways, contributing nothing — and is stripped before the churn
    # gate judges the trade. Emptying either side means the real content
    # WAS the pick swap: killed. Consolidation (2 lesser picks for 1
    # better) survives because those values sit outside the band.
    # 0 disables (the literal 1-for-1 ban only, as before).
    "pick_pair_strip_frac":       0.85,
    # C4 — headliner diversity cap at deck assembly: at most this many
    # cards in one served deck may share the same centerpiece (the
    # package's highest-consensus asset — the SAME definition as
    # deck_impressions.centerpiece_id, so the metric and the cap agree).
    # Applied after the composite sort, so each headliner keeps its best
    # cards. 0 disables (uncapped, as before).
    "deck_headliner_cap":         2.0,
    # C4b (2026-08-19, docs/plans/deck-give-headliner-cap/scope.md) — GIVE-side
    # headliner cap: at most this many cards in one served deck may ask the
    # user to send the same headliner (the highest-consensus PLAYER on the
    # give side). Sits alongside deck_headliner_cap, not in place of it:
    # `deck_centerpiece` maxes over give+receive, so a card that gives a
    # player for a draft pick is keyed on the PICK, every card offers a
    # different pick slot, and the centerpiece cap never fires — one live deck
    # had 22 cards with 20 distinct centerpieces while three players supplied
    # 17 of the 22 give sides. 0 disables (uncapped, byte-identical to pre-C4b).
    "deck_give_headliner_cap":    3.0,
    # C5 — confidence damping of the RANKING mismatch term: the term is
    # scaled by max(0, 1 − damp × unc), where unc is the package's
    # value-weighted mean _value_uncertainty (range_base / sqrt(1+n)).
    # A large apparent divergence resting on a player almost nobody has
    # ranked is treated as the artifact it probably is. The surplus GATES
    # are untouched. 0 disables (undamped, as before); confidence=None
    # (no comparison counts) is also a no-op at any value.
    "mismatch_confidence_damp":   1.0,

    # ------------------------------------------------------------------
    # D-085 (2026-08-19) — placement tier clamp.
    #
    # Confidence shrinkage blends a personal Elo toward consensus with
    # w = n/(n+shrink_pseudocount), and `n` counts COMPARISONS only. A tier
    # save / drag-reorder is an ASSERTION, not a sample, so a deliberately
    # placed player the user never voted on (n=0 ⇒ w=0) was priced at pure
    # consensus — a full tier away from where the user put him, then offered
    # for assets of that other tier.
    #
    # At 1.0 the shrunk Elo of a PLACED player is clamped to the band of the
    # tier he was placed in (RankingService.placement_bands, i.e.
    # tier_config.json): consensus still re-prices him INSIDE his tier, never
    # out of it. This is `pin_tier_bounded` — the operator's own rule for how
    # votes move a placement — applied to how the engine PRICES the result.
    # Unplaced players are never clamped (that would freeze the board at
    # consensus), and neither are pins below the lowest band, which have no
    # tier at all.
    #
    # Personal-valuation path ONLY. Every fairness/surplus GATE keeps pricing
    # the real package on real consensus values (see the ranking-vs-gate
    # separation note below), and `_value_uncertainty` is deliberately
    # untouched. 0 disables — byte-identical to the pre-D-085 blend, and the
    # value this knob carries in MODEL_A_PROFILE.
    # ------------------------------------------------------------------
    "placement_tier_clamp":       1.0,

    # ------------------------------------------------------------------
    # D-079 (2026-08-19) — per-round draft-pick year decay. Read ONLY
    # through pick_values.year_decay(round); trade_service itself never
    # uses them. They live here because _c() is the live-config accessor
    # reload_config() refreshes, so a PUT /api/admin/config reprices picks
    # with no deploy. All four at 0.85 = the pre-D-079 uniform behaviour.
    # ------------------------------------------------------------------
    "pick_year_decay_r1":         1.00,
    "pick_year_decay_r2":         0.85,
    "pick_year_decay_r3":         0.85,
    "pick_year_decay_r4":         0.85,

    # ------------------------------------------------------------------
    # D-161 (2026-08-24) — the round-1 YoY FLOOR under `market_slots`.
    # Read ONLY through pick_values.market_r1_yoy_floor(); trade_service
    # itself never uses it. Same home and same reason as the four rates
    # above: _c() is what reload_config() refreshes, so a PUT to
    # /api/admin/config reprices every future first with no deploy.
    #
    # A future-season ROUND-1 pick may not price below this fraction of
    # the CURRENT class's round-1 market price. 1.0 = the D-079 ruling
    # ("firsts should hold similar value YOY"), re-asserted over DP's own
    # in-window year discount after the 2026-08-24 operator re-ruling.
    # 0 = pure market — byte-identical to the pre-D-161 waterfall, and the
    # deploy-free revert. Rounds 2-4 are untouched at every setting.
    # ------------------------------------------------------------------
    "market_r1_yoy_floor":        1.00,

    # ------------------------------------------------------------------
    # D-095 (2026-08-19) — LANDABILITY CHALLENGER (bake-off arm D,
    # docs/plans/landability-challenger/PRD.md §4). Three knobs, every one
    # defaulting to the **live identity**, so the live engine — arm B, what
    # users actually see — is byte-identical whether or not these exist.
    # The challenger is an OVERLAY: `bakeoff_profiles.MODEL_CHALLENGER_
    # PROFILE` turns them on inside `model_challenger()` and nowhere else.
    #
    # The arm asks a different question of the same engine: show trades two
    # sides could BOTH take, rather than only the side where the viewer
    # wins. Measured on the live engine: 84.5% of cards never see a partner
    # board, 96.3% of 1-for-1s exist in only one direction, and on the
    # consensus path the user receives more than they give on 86.3% of them.
    #
    # These keys are deliberately **excluded from `MODEL_A_PROFILE`** — see
    # docs/plans/three-model-bakeoff/scope-phase2.md § Excluded. Their
    # DEFAULTS are the pre-challenger engine, so pinning a kill value would
    # make historical arm A skip shrinkage and emit both directions, which
    # the pre-wave engine never did. They are pinned in `_PINNED_KNOBS`
    # (backend/tests/test_bakeoff_arm_a_golden.py) like every other knob.
    # ------------------------------------------------------------------
    # Confidence shrinkage of the USER's board toward the consensus seed
    # (`_shrink_user_elo`). 1.0 = live: blend by comparison count. 0.0 = the
    # challenger's shrink-NEITHER stance — price the user's board raw, as the
    # partner's `elo_ratings` already are. That asymmetry (shrunk user vs raw
    # partner) is what makes 86.9% of boarded-pair cards one-directional.
    # A switch, not a dial: only 0.0 and 1.0 are meaningful, and
    # `shrink_pseudocount = 0` is NOT a substitute — n/(n+0) is NaN at n=0.
    # Shrink-BOTH is out of scope: `LeagueMember` carries no confidence map,
    # so the partner's counts do not exist to plumb (PRD N8).
    "user_elo_shrink":            1.0,
    # Consensus-path direction (`_generate_consensus_for_pair._emit`).
    # 0.0 = live: the hard `rv - gv >= user_gain_epsilon` sign test, i.e.
    # the user's side must come out ahead, which is the viewer-wins identity.
    # >= 1 = the challenger: drop the sign test so BOTH directions of an even
    # trade can emit, and enumerate 1-for-2 as the sibling of 2-for-1 so
    # partner-favourable consolidation is representable at all (production
    # holds 6,635 `1x1` and 459 `2x1` packages and exactly zero `1x2`).
    # Only safe alongside a real fairness floor — see the next knob.
    "consensus_both_ways":        0.0,
    # Consensus-path fairness FLOOR. 0.0 = live: whatever threshold the
    # caller passed (often 0.50 from the client toggle). > 0 raises it via
    # `max(requested, floor)`, so it can only ever tighten. The challenger
    # sets 0.75: opening both directions on a 0.50 floor is a 2:1 user-pays
    # flood, and at 0.75 the worst either side can be out is exactly
    # 1 - 0.75 = 25%. Consensus path only — the divergence path has
    # `fairness_floor_divergence` and a real dual-surplus gate.
    "consensus_fairness_floor":   0.0,
    # Consensus-path roster-fit SORT KEY (2026-09-02, docs/plans/
    # consensus-fit-sort-key/). The consensus generator emits the first
    # `max_cards` combos that clear its gates, in pool order — so the pool
    # SORT is the ranking, and today that sort is pure `seed_value`. Both
    # sides are priced by the same consensus functional, so the partner's
    # gain is the exact negative of the user's and the only modelled reason
    # a counterparty would accept is roster fit — which was not in the sort
    # at all. w > 0 blends it in: each pool sorts on
    # `seed_value * (1 + w * fit_norm)`, where fit is the marginal-value
    # asymmetry (worth to the partner's lineup minus worth to ours, on the
    # shared consensus prices; negated on the receive side) normalised to
    # [-1, 1] by the pool's max |fit|. So w = 0.5 makes a perfect-fit asset
    # sort as if 50% more valuable. Picks have no lineup slot and get fit 0.
    # Reorders only — every gate (sign test, fairness, filler, #108) is
    # untouched, so the user still wins on consensus on every card. 0.0 =
    # live: the multiplier is exactly 1 and the sort is byte-identical.
    "consensus_fit_weight":       0.0,
    # ------------------------------------------------------------------
    # Bake-off arm roster (read by bakeoff_runner.arm_roster()).
    # ------------------------------------------------------------------
    # 1 (default) = arm `challenger` is generated, logged and drafted. 0
    # restores the exact pre-challenger roster with no deploy — the kill
    # switch for the extra `generate_trades` per organic job.
    "bakeoff_include_challenger": 1.0,
    # 1 (default) = arm `gen_v2` stays in the roster. 0 drops arm C so the
    # head-to-head is `current` vs `challenger` (composition only — it does
    # NOT change backend/trade_gen_v2.py, which is out of the arm's scope).
    "bakeoff_include_gen_v2":     1.0,

    # ------------------------------------------------------------------
    # Fit challenger — bake-off arm `fit` K-chain knobs (PR-F1,
    # docs/plans/fit-challenger/LLD.md §1.6 + §4). Consumed ONLY by
    # backend/trade_gen_fit.py, a module arm A never imports and
    # trade_service never calls. They live here because _c() is the
    # accessor the fit K-chain reads (thread-local overrides and
    # reload_config() both work) and snapshot_config() must capture them
    # per run. Five registrations per key, same commit as the consumer
    # (LLD §4): this dict, database._MODEL_CONFIG_DEFAULTS, _PINNED_KNOBS
    # in test_bakeoff_arm_a_golden.py, the scope-phase2.md disposition
    # sentence, and the config-reference row.
    # ------------------------------------------------------------------
    # K7 (G6 R5 need gate) mode inside the fit K-chain. 1.0 (default) =
    # the live predicate kills exactly as written (PRD §3 K7). 0.0 = the
    # predicate still RUNS but a failure does not kill: the candidate is
    # tagged `r5_fail` and counted `r5_fail_scored`, with NO score change
    # in v1 (LLD §8 R-d). Flipping to 0 is F7's pre-registered iterate
    # action at the S4 verdict, never a build-time default.
    "fit_r5_mode":                1.0,
    # Junk-filler kill inside the fit K-chain. 0.0 (default) = no junk
    # knockout — this arm deliberately lets junk score badly instead
    # (PRD §3 "explicitly not knockouts"). >= 1.0 arms the live
    # filler_ok predicate (kills count under "junk"), each side's value
    # accessor being that team's raw board when boarded, else consensus.
    "fit_junk_floor":             0.0,

    # ------------------------------------------------------------------
    # Fit challenger — pool / scorer / enumerator knobs (PR-F2, LLD §1.4,
    # §1.5, §1.7, §1.9 + §4). Same five-registration discipline and the
    # same "consumed ONLY by backend/trade_gen_fit.py" posture as the
    # PR-F1 block above.
    # ------------------------------------------------------------------
    # Scorer curve (LLD §1.7): score = clamp(even + 50·tanh(s / scale),
    # 0, 100). scale 400 ⇒ a +400 surplus scores ≈ 88.1; even is the
    # zero-surplus midpoint.
    "fit_score_scale":          400.0,
    "fit_score_even":            50.0,
    # Per-side lens weights (L1 own-board, L2 board-vs-consensus, L3
    # consensus), renormalized to sum 1 over the lenses that fired.
    "fit_w_board":                0.40,
    "fit_w_div":                  0.30,
    "fit_w_cons":                 0.30,
    # Pool builder (LLD §1.4): per-roster sub-pool sizes and the hard cap
    # on unique asset ids (picks always enter the union but compete under
    # the cap — LLD §8 R-c).
    "fit_pool_consensus":         8.0,
    "fit_pool_div_seed":          8.0,
    "fit_pool_div_opp":           8.0,
    "fit_pool_cap":              15.0,
    # Enumerator budget (LLD §1.5): hard per-pair enumeration ceiling and
    # the number of top 1-for-1 survivors used as multi-asset expansion
    # centerpieces.
    "fit_max_packages_per_pair": 20000.0,
    "fit_expand_from":           25.0,
    # Post-score presentment filters (LLD §1.9 step 1) — defaults 0 = off
    # (PRD §4: defaulting fit_min_them on would recreate rv ≥ gv).
    "fit_min_them":               0.0,
    "fit_min_aggregate":          0.0,

    # ------------------------------------------------------------------
    # Fit challenger — roster + serve bits (PR-F3, LLD §2.1 + §4).
    # Disposition B: arm roster / serving bits, not generation — read only
    # by bakeoff_runner before or after any arm runs; an arm cannot
    # observe them. Same five-registration discipline as the fit_* keys.
    # ------------------------------------------------------------------
    # 0 (default) = arm `fit` is not rostered: never generated, never
    # drafted, never logged. 1 = fit generates + logs on every organic
    # bake-off job (W3's dark-roster flip — an operator set_knob write).
    "bakeoff_include_fit":        0.0,
    # 0 (default) = a rostered fit generates, logs to arms_json, and is M3-
    # stamped, but is EXCLUDED from the draft participants on BOTH draft
    # paths (HLD F-6) — no fit card can reach a served deck. 1 = fit
    # drafts like any arm (W4's serving flip). Fit-only bit by design
    # (PLAN-v2 F5b): generalize on the second consumer, not the first.
    "bakeoff_serve_fit":          0.0,

    # ------------------------------------------------------------------
    # Counterparty breaker — 25 evaluation-layer knobs
    # (docs/plans/counterparty-breaker/LLD.md §4). Consumed ONLY by
    # backend/trade_breaker.py, a module no generator or ranker imports:
    # it runs AFTER the deck-mutation stack completes and mutates only a
    # new card attribute, so none of these can move a generated deck.
    # They live here because _c() is the accessor the breaker's per-job
    # config snapshot (§3.0) reads — thread-local overrides and
    # reload_config() both work, and snapshot_config() captures them per
    # run. Five registrations per key, same logical change as the
    # consumer (see the fit block above): this dict,
    # database._MODEL_CONFIG_DEFAULTS, _PINNED_KNOBS in
    # test_bakeoff_arm_a_golden.py, the scope-phase2.md disposition
    # sentence, and the config-reference row. `waiver_slot_cost` is
    # REUSED by the breaker (_SHARED_ENGINE_KNOB_KEYS, §1.1) and is an
    # existing engine registration — it is not part of the 25.
    # ------------------------------------------------------------------
    # Budget + degradation (LLD §3.9, §5.1).
    "breaker_ms_budget":                    250.0,
    "breaker_budget_checkpoint_frac":         0.6,
    "breaker_degraded_share_max":            0.05,
    # Narration policy bars (LLD §3.8).
    "breaker_min_severity":                  0.60,
    "breaker_max_repeat_frac":               0.34,
    # Viewer-seat shadow evaluation (operator decision 5, LLD §2.5).
    "breaker_shadow_run":                     1.0,
    # fit_outlook window handling (LLD §3.3, D-8).
    "breaker_outlook_haircut_legacy":        0.70,
    "breaker_outlook_narrate_margin":        0.06,
    # Board-authenticity thresholds (LLD §3.4 F-3). SEMANTICS are
    # BREAKER_VERSION-pinned: a threshold change worth making is a
    # `ver`-bump conversation first (LLD §4).
    "breaker_board_div_min":                 25.0,
    "breaker_board_min_divergent":           10.0,
    # Severity curve scales (LLD §3.4, §3.5).
    "breaker_value_scale":                  400.0,
    "breaker_crunch_scale":                 850.0,
    # Per-class top-selection floors. Floors shape the stamp
    # distribution, never narration policy (D-6). `value_giving` is split
    # by basis because the consensus basis is a near-tautology at the
    # board floor (D-7: 86.3%).
    "breaker_floor_fit_outlook":             0.35,
    "breaker_floor_fit_new_weakness":        0.30,
    "breaker_floor_fit_duplicate":           0.30,
    "breaker_floor_value_giving":            0.30,
    "breaker_floor_value_giving_consensus":  0.75,
    "breaker_floor_other_player_keep":       0.50,
    "breaker_floor_roster_crunch":           0.40,
    # Per-class narration switches — ALL default 0 (D-6 maturity ladder).
    # Graduation is an operator `scripts/set_knob.py` flip, logged in
    # `model_config_changes`; it is never a build-time default.
    "breaker_narrate_fit_outlook":            0.0,
    "breaker_narrate_fit_new_weakness":       0.0,
    "breaker_narrate_fit_duplicate":          0.0,
    "breaker_narrate_value_giving":           0.0,
    "breaker_narrate_other_player_keep":      0.0,
    "breaker_narrate_roster_crunch":          0.0,

    # ------------------------------------------------------------------
    # Negative-results memory — 6 knobs (flag `trade.negmem`, default OFF;
    # docs/plans/negative-results-memory/LLD.md §3.4). Consumed ONLY by
    # backend/negmem.py, a leaf module that imports no engine module: it
    # derives a per-(partner × reason-family) soft prior on read, once per
    # job, and the engines consult it through a pure multiplier. They live
    # here because `_c()` is the accessor for BOTH read paths — the seam
    # reads `negmem_strength` / `negmem_floor` inside the arm's overlay
    # (D-6/D-10), and `server._run_trade_job` reads the four build knobs
    # off the job thread before the arm fan-out and passes plain floats
    # into `build_map` (DE-3), which is what keeps negmem literal-free.
    # Thread-local overrides and reload_config() both work, and
    # snapshot_config() captures all six per run (D-8). Five registrations
    # per key, same logical change as the consumer (see the fit block
    # above): this dict, database._MODEL_CONFIG_DEFAULTS, _PINNED_KNOBS in
    # test_bakeoff_arm_a_golden.py, the scope-phase2.md disposition
    # sentence, and the config-reference row. M2's strength is NOT here —
    # it is governed by the existing `gen2_accept_prior_strength` /
    # `gen2_accept_global_prior` above, whose 0 is M2's kill.
    # ------------------------------------------------------------------
    # M1 lever, read at the seam. 0.0 = byte-identical M1 disable (deck
    # content, scores and order); M1-ONLY, it does not govern M2.
    "negmem_strength":            1.0,
    # Double role (LLD §4.4): the clamp floor for the effective multiplier
    # AND the build-time evidence-curve asymptote `floor_b`.
    "negmem_floor":               0.6,
    # Shrinkage threshold — cells with decayed evidence below this are
    # identity (multiplier exactly 1.0).
    "negmem_min_evidence":        3.0,
    # Exponential-decay half-life in days; also sets the read horizon (x4).
    "negmem_halflife_days":      45.0,
    # Saturation pseudo-count of the evidence curve
    # (mult = 1 - (1 - floor) * n_eff / (n_eff + k)) — the deploy-free
    # flap lever for the shrinkage-gate discontinuity (OQ-4b).
    "negmem_sat_k":               3.0,
    # Evidence mass one admitted viewed like nets against every
    # (partner, *) cell, folded chronologically with a clamp at zero
    # after every step (DE-2).
    "negmem_like_net":            1.0,
}

# Live config — updated by reload_config().  Starts as a copy of defaults.
_cfg: dict[str, float] = dict(_DEFAULT_CFG)


def reload_config() -> None:
    """
    Pull the latest values from model_config and update the module-level
    _cfg dict in-place.  Call this at server startup and after any PUT to
    /api/admin/config.
    """
    global _cfg
    try:
        from .database import get_config as _db_get_config
        fresh = _db_get_config()
        if fresh:
            _cfg.update(fresh)
    except Exception:
        pass  # DB unavailable — keep existing values


# #189 — per-thread config overlay for the relaxed fallback pass. A relaxed
# re-run must loosen gate knobs (fairness floor, surplus minimums) WITHOUT
# touching the process-global _cfg: trade jobs run concurrently on daemon
# threads, so a global mutation would leak relaxed gates into normal jobs.
# Overrides apply only to _c() reads on the thread that entered the context
# (trade_optimizer imports _c from here, so v3 reads them too).
_cfg_local = threading.local()


@contextmanager
def _cfg_override(overrides: dict):
    prev = getattr(_cfg_local, "map", None)
    _cfg_local.map = {**(prev or {}), **overrides}
    try:
        yield
    finally:
        _cfg_local.map = prev


def _c(key: str) -> float:
    """Convenience accessor: return live config value with default fallback.
    Thread-local overrides (#189 relaxed pass) win over both."""
    ov = getattr(_cfg_local, "map", None)
    if ov is not None and key in ov:
        return ov[key]
    return _cfg.get(key, _DEFAULT_CFG[key])


# ---------------------------------------------------------------------------
# Bake-off arm A — per-thread R4 bypass (docs/plans/three-model-bakeoff/
# PLAN.md §3.3; profile in backend/bakeoff_profiles.py)
# ---------------------------------------------------------------------------
# G6's R1/R2/R3/R5 each have a kill knob, so arm A ("the engine as it behaved
# before the 2026-08-16 wave") disables them through _cfg_override. R4 — the
# windowless awaiting/matched exclusion — has NO knob: the
# trade.presentment_rules flag is its only switch, and flipping that flag
# would disable R4 for arms B and C and for every other user of the process.
# Hence this: same shape and same discipline as _cfg_override above
# (threading.local + contextmanager), so concurrent trade jobs on sibling
# daemon threads are untouched.
#
# Applied at every site that consults the R4 exclusion set:
#   • TradeService._dedup_and_sort (the v1 path, streaming snapshots included)
#   • the trade_gen.v2 hand-off in _generate_trades_impl
#   • server._inject_likes_you_cards_impl (the likes-you injector)
# Never bypasses _past_decision_keys — a trade the user already swiped on
# stays gone for every arm.
_r4_bypass_local = threading.local()


@contextmanager
def r4_bypass():
    """Ignore the G6 R4 exclusion set for the duration, on this thread only."""
    prev = getattr(_r4_bypass_local, "on", False)
    _r4_bypass_local.on = True
    try:
        yield
    finally:
        _r4_bypass_local.on = prev


def r4_bypassed() -> bool:
    """True when the calling thread is inside an `r4_bypass()` context."""
    return bool(getattr(_r4_bypass_local, "on", False))


# ---------------------------------------------------------------------------
# #214/#215 — stud-tax mode (per-user setting `stud_tax_mode`)
# ---------------------------------------------------------------------------
# 'market' (default) — the #214 retuned shapes: depth discount vs the
#     package's OWN best asset (capped), crown credit per elite asset on
#     EITHER side, phased out as the naive gap widens.
# 'heavy'  — the pre-#214 legacy math, byte-identical (trade-wide v_max
#     benchmark, uncapped gamma discount, single-crown outnumbered-side
#     premium at crown_rate).
# 'off'    — no crown premium, no depth discount: naive sums stand.
#
# The mode rides a thread-local (same pattern as the #189 _cfg_override):
# entry points that know the user (generate_trades, generate_asset_ideas,
# /api/trade/evaluate, the likes-you injector) pin it for the duration of
# their math; everything package_value_v2 touches inherits it.

STUD_TAX_MODES = ("market", "heavy", "off")
STUD_TAX_DEFAULT = "market"

_stud_tax_local = threading.local()


def current_stud_tax_mode() -> str:
    m = getattr(_stud_tax_local, "mode", None)
    return m if m in STUD_TAX_MODES else STUD_TAX_DEFAULT


def pinned_stud_tax_mode() -> str | None:
    """The explicitly pinned thread-local mode, or None when nothing is
    pinned. Entry points (generate_trades, /api/trade/evaluate, …) keep an
    already-active outer pin instead of re-resolving the user's stored
    setting — production never nests entry points, and it lets tests pin a
    mode around a whole route/service call."""
    m = getattr(_stud_tax_local, "mode", None)
    return m if m in STUD_TAX_MODES else None


@contextmanager
def stud_tax_override(mode: str | None):
    """Pin the stud-tax mode for package_value_v2 calls on this thread."""
    prev = getattr(_stud_tax_local, "mode", None)
    _stud_tax_local.mode = mode if mode in STUD_TAX_MODES else STUD_TAX_DEFAULT
    try:
        yield
    finally:
        _stud_tax_local.mode = prev


def stud_tax_mode_for_user(user_id: str | None) -> str:
    """The stored per-user mode ('market' default; DB-unavailable safe)."""
    if not user_id:
        return STUD_TAX_DEFAULT
    try:
        from .database import get_stud_tax_mode
        return get_stud_tax_mode(user_id)
    except Exception:
        return STUD_TAX_DEFAULT


# ---------------------------------------------------------------------------
# Draft-pick pricing — MARKET SLOTS, UNCONDITIONALLY (2026-08-21, D-144)
# ---------------------------------------------------------------------------
# OPERATOR RULING, 2026-08-21, verbatim:
#     "Market slots should be default and not an opt-in or even an option to
#      flip. Aligned that future picks stay default for now."
#
# That retires the M6b opt-in wholesale and closes the implementation half of
# Q-023. There is no per-user pricing mode any more, no flag read and no DB
# read: EVERY owned pick, for EVERY user, prices off DynastyProcess's
# published market curve for its absolute season+round
# (`pick_values.market_pick_pool_value`).
#
# READ THE SCOPE OF "market slots" CAREFULLY — it is a ROUND-level curve, not
# a per-slot one. An owned 2026 1st prices at the value-space mean of slots
# 1.05–1.08 (`pick_values.UNKNOWN_SLOT_BASIS`, the market analogue of the
# ladder's Mid rung), NOT at its own resolved slot. D-090 resolves the real
# slot and it drives the LABEL only. True-slot pricing — a 1.01 above a 1.12 —
# is the remaining, unbuilt half of Q-023; see docs/plans/
# slot-pricing-unconditional/scope.md §"What this does NOT do".
#
# WHAT DID NOT CHANGE, and is load-bearing:
#   * FUTURE-YEAR picks price off DP's generic/Mid rung for that season — the
#     operator's "future picks stay default for now". `market_slots` always
#     keyed off the ABSOLUTE season, so this is the shipped path unmodified.
#   * UNKNOWN DRAFT ORDER is not a special case and never was: the round-level
#     basis applies to every pick regardless of whether an order exists.
#   * DP unreachable / no published price ⇒ `priced_pool_value` still
#     fail-softs to the stored ladder `pool_value`. Unconditional pricing
#     makes that the ONLY safety net, so it stays and is now load-bearing.
#   * `GENERIC_PICK_SEEDS`, the tier ladder and the ABSOLUTE tier bands are
#     byte-unchanged, exactly as they were in both M6b modes. Pick tier
#     BADGES do move, because a badge reflects the SERVED value (D-320-2) and
#     the served value moved. That is a consequence, not a second decision.
#   * `draft_picks.pool_value` is still never rewritten; pricing is read-time.
#
# The two-mode vocabulary survives ONLY as an internal harness/test axis:
# `pick_pricing_override('tier_ladder')` still pins the legacy ladder so the
# bake-off harnesses and the M6b regression tests can price both curves side
# by side in one process. Nothing user-facing can reach it — no route, no
# setting, no flag. `users.pick_pricing_mode` is dead data, kept under the
# additive-schema rule (never drop a column).

PICK_PRICING_MODES = ("tier_ladder", "market_slots")
PICK_PRICING_DEFAULT = "market_slots"       # the shipped, only-reachable price

_pick_pricing_local = threading.local()


def current_pick_pricing_mode() -> str:
    m = getattr(_pick_pricing_local, "mode", None)
    return m if m in PICK_PRICING_MODES else PICK_PRICING_DEFAULT


def pinned_pick_pricing_mode() -> str | None:
    """The explicitly pinned thread-local mode, or None. Mirrors
    `pinned_stud_tax_mode` — entry points keep an active outer pin instead of
    re-resolving, which is also what lets a test (or the bake-off/deck
    harnesses) pin the legacy ladder around a whole job."""
    m = getattr(_pick_pricing_local, "mode", None)
    return m if m in PICK_PRICING_MODES else None


@contextmanager
def pick_pricing_override(mode: str | None):
    """Pin the pick-pricing mode for `priced_pool_value` calls on this thread.

    HARNESS/TEST SEAM since the 2026-08-21 ruling — production entry points
    pin `PICK_PRICING_DEFAULT`, which is also what an unpinned thread
    resolves to, so an outer pin can only ever narrow to the legacy ladder."""
    prev = getattr(_pick_pricing_local, "mode", None)
    _pick_pricing_local.mode = (mode if mode in PICK_PRICING_MODES
                                else PICK_PRICING_DEFAULT)
    try:
        yield
    finally:
        _pick_pricing_local.mode = prev


def pick_pricing_mode_for_user(user_id: str | None) -> str:
    """`market_slots`. Always, for everybody. (Operator ruling 2026-08-21.)

    Kept as a named function rather than inlined at the call sites so the
    ruling has exactly one home, and so a future per-user axis — if one is
    ever authorised again — has one place to come back to. It reads no flag,
    no session and no DB row: `user_id` is accepted and ignored, and
    `users.pick_pricing_mode` is dead data.
    """
    return PICK_PRICING_DEFAULT


# ---------------------------------------------------------------------------
# KTC-style Dynasty Value
# ---------------------------------------------------------------------------
# Exponential decay: rank 1 ≈ 9875, rank 200 ≈ 806, rank 500 ≈ ~66
# All constants are now live-loaded from _cfg (seeded from model_config table).


def dynasty_value(player, rank_override: int | None = None) -> float:
    """
    KTC-style exponential dynasty value for a single player/pick.

    For draft picks (position == "PICK"): player.pick_value is on the
    0-100 round-tier scale (compute_pick_value in database.py; mid-1st =
    67.5 — NOT 0-10000). Bridge it into the shared value space via the
    same calibration the universal pool's generic picks use, where
    pick_value = (seed_elo - 1200) / 6 (see build_universal_pool in
    server.py): elo = 1200 + 6*pick_value, then elo_to_value(elo). A
    league mid-1st therefore prices identically to its generic-pick twin
    instead of at ~67 (near-zero next to players in the thousands).

    NOTE (#185): this PICK branch serves the LEGACY engine path and any
    caller that prices a pick pseudo-Player directly. The v2/v3 engine
    prices assets through Elo maps (seed_elo + per-board), NOT through
    dynasty_value — injected picks must be primed into those maps
    (server._pick_asset_elos / _inject_owned_picks) or they silently
    default to Elo 1500. Two scales coexist on draft_picks rows:
    `pick_value` (legacy 0-100 round-tier) and `pool_value` (engine value
    space) — see docs/cross-client-invariants.md.

    For regular players: uses player.search_rank (1-based, lower = better).
    Falls back to ktc_fallback_rank config if no rank is stored.

    rank_override lets callers supply a rank directly (used in tests / calcs
    where we want to bypass the player object).
    """
    ktc_k   = _c("ktc_k")
    ktc_max = _c("ktc_max")

    if rank_override is not None:
        rank = max(rank_override, 1)
        return round(ktc_max * math.exp(-ktc_k * (rank - 1)), 1)

    if getattr(player, "position", None) == "PICK":
        pv = getattr(player, "pick_value", None)
        if not pv:
            # Unknown pick value → neutral mid-asset value, same number the
            # old fallback returned (= elo_to_value at the reference Elo).
            return 1000.0
        return round(elo_to_value(1200.0 + 6.0 * float(pv)), 1)

    fallback = int(_c("ktc_fallback_rank"))
    rank = getattr(player, "search_rank", None) or fallback
    rank = max(int(rank), 1)
    return round(ktc_max * math.exp(-ktc_k * (rank - 1)), 1)


def package_value(individual_values: list[float]) -> float:
    """
    Aggregate dynasty value for a trade package with diminishing returns.

    The best player is weighted 1.0, second 0.75, third 0.55, etc.
    This mirrors how real dynasty managers value multi-player packages.
    Weights are loaded from _cfg (package_weight_1 … package_weight_5).
    """
    if not individual_values:
        return 0.0
    weights = [
        _c("package_weight_1"),
        _c("package_weight_2"),
        _c("package_weight_3"),
        _c("package_weight_4"),
        _c("package_weight_5"),
    ]
    sorted_vals = sorted(individual_values, reverse=True)
    total = sum(v * w for v, w in zip(sorted_vals, weights))
    return round(total, 1)


# ---------------------------------------------------------------------------
# Trade engine v2 — single value space + package math
# (flag: trade_engine.v2 — see docs/plans/trade-engine-tier1-fixes.md and
#  docs/reviews/trade-engine-external-research.md §6 amendments A1–A4)
# ---------------------------------------------------------------------------


def elo_to_value(elo: float) -> float:
    """
    Map a personal/seed Elo rating onto the dynasty-value scale used for
    ALL v2 trade math. Monotone increasing. Since the #117 seed
    recalibration (data_loader.seed_elo_for_value) the top consensus asset
    seeds at ~Elo 1927 ≈ 4 × value(Mid 1st); a replacement-level Elo
    (~1300) ≈ a low-end bench value.

        value = elo_value_base * exp(elo_value_k * (elo - elo_value_ref))

    With base=1000, ref=1500, k=0.0050: elo 1790 → ~4263, elo 1500 → 1000,
    elo 1300 → ~368. All constants are config-tunable (model_config).
    """
    return _c("elo_value_base") * math.exp(
        _c("elo_value_k") * (elo - _c("elo_value_ref"))
    )


def value_to_elo(value: float) -> float:
    """
    Inverse of elo_to_value: map a dynasty value back onto the Elo scale.

    Used by the pick-anchor wizard, where a user statement like "worth
    2 firsts" is a VALUE statement (2 × value of a generic mid-1st) that
    must be pinned as an Elo override. Clamps at a tiny positive value so
    a zero/negative input can't blow up the log.
    """
    v = max(float(value), 1e-9)
    return _c("elo_value_ref") + math.log(v / _c("elo_value_base")) / _c("elo_value_k")


def package_value_v2(values: list[float], v_max: float,
                     n_other: int | None = None,
                     other_values: list[float] | None = None) -> float:
    """
    KTC-style package value for the v2 engine (amendment A2).

    #214/#215: behavior branches on the thread-local stud-tax mode (see
    stud_tax_override / current_stud_tax_mode above):

    'off' — no adjustments; returns the naive sum of `values`.

    'market' (default) — the #214 retuned shapes; see
    _package_value_market. ``other_values`` (the OTHER side's raw values,
    same value space) enables the both-sides elite crown credit + the
    naive-skew phase-out; callers that omit it get the depth math only.
    ``n_other`` is ignored in this mode (crown eligibility is
    count-independent). ``v_max`` — the best single-asset value in the
    WHOLE trade — feeds the 2026-08-21 cross-package depth benchmark
    (knob `package_bench_trade_wide`; see _package_value_market): a
    multi-asset side that does NOT hold the trade's best asset is
    discounted against that asset, not against its own headliner. At
    `package_bench_trade_wide` ≤ 0 the pre-fix own-max benchmark applies
    byte-identically and ``v_max`` is ignored as before.

    'heavy' — the pre-#214 legacy math, byte-identical:

    Inspired by KeepTradeCut's reverse-engineered "raw adjustment": each
    asset in a trade contributes only a fraction of its raw value, and the
    fraction shrinks exponentially as the asset's value falls relative to
    the best asset in the trade ("four quarters ≠ a dollar"). KTC's full
    formula is p·[0.29(p/v)^8 + 0.28(p/t)^1.3 + 0.07(p/(v+2000))^1.28];
    we use the single-term simplification

        contribution(v) = v * (0.15 + 0.85 * (v / v_max) ** package_adj_gamma)

    where v_max is the best single-asset value in the WHOLE trade (in the
    same value space as `values`) and package_adj_gamma (default 1.5) is
    config-tunable. The best asset contributes 100% of its value; lesser
    assets bottom out at 15%. The legacy `package_value` (fixed diminishing
    weights) is retained untouched for the legacy path.

    Backlog #10 — crown-asset premium (flag trade.crown_asset). When
    ``n_other`` (the OTHER side's asset count) is supplied AND this side has
    fewer assets than the other side, the top asset gets a consolidation
    premium scaled by its share of this side's raw total — the market's
    "don't split a dollar into 100 pennies" adjustment (FPTrack Crown Asset /
    Dynasty Daddy Value Adjustment). The cross-side count guard makes the
    premium exactly 0 on equal-count trades (1-for-1, 2-for-2), so flag-off
    and symmetric trades are byte-identical. Callers that omit ``n_other``
    (legacy/unmigrated) are likewise unaffected.
    """
    if not values:
        return 0.0
    mode = current_stud_tax_mode()
    if mode == "off":
        return round(sum(values), 1)
    if mode == "market":
        return _package_value_market(values, other_values, v_max)

    # ── 'heavy' — pre-#214 legacy math, byte-identical ──────────────────
    v_max = max(v_max, 1e-9)
    gamma = _c("package_adj_gamma")
    total = sum(v * (0.15 + 0.85 * (v / v_max) ** gamma) for v in values)

    if (FLAGS.trade_crown_asset and n_other is not None
            and len(values) < n_other):
        side_sum = sum(values)
        if side_sum > 0:
            v_top = max(values)
            share = v_top / side_sum
            floor = _c("crown_share_floor")
            if share > floor:
                premium = _c("crown_rate") * (share - floor) / max(1.0 - floor, 1e-9)
                # Interview 2026-07-17 ("depends on stud"): scale the
                # premium by the crown asset's absolute value — a true
                # tier-1 commands the full rate, a mid-tier headliner
                # earns proportionally less.
                elite_ref = _c("crown_elite_value")
                if elite_ref > 0:
                    premium *= min(1.0, v_top / elite_ref)
                top_contrib = v_top * (0.15 + 0.85 * (v_top / v_max) ** gamma)
                total += premium * top_contrib
    return round(total, 1)


def _package_value_market(values: list[float],
                          other_values: list[float] | None,
                          v_max: float | None = None) -> float:
    """#214 'market' stud-tax shapes (tuning-proposal.md §1–3), amended
    2026-08-21 by the cross-package benchmark fix (shape 1a below).

    1. Depth discount — contribution(v) = v · (floor + (1−floor) ·
       (v/bench)^γ) with γ = package_adj_gamma_market, and the side's
       TOTAL discount capped at package_discount_cap × the naive sum.
       A single-asset side is never depth-discounted.
    1a. THE BENCHMARK (2026-08-21 fix, operator-approved; evidence
       docs/reviews/2026-08-21-market-curve-comparison.md §3b). The
       original #214 shape benchmarked every piece against the package's
       OWN best asset, so four similar mid-tier players took a ~5%
       haircut while buying a stud — the served Rice+Etienne+Swift+Corum
       → Nacua card scored 0.939 (fair) against FantasyCalc 1.362 / KTC
       2.260. With `package_bench_trade_wide` > 0 (the default) a
       multi-asset side that does NOT hold the trade's best asset is
       benchmarked against ``v_max`` — the best asset in the WHOLE trade,
       KTC's own published shape — with the floor switched to
       `package_floor_cross` (the own-side floor 0.70 would leave four
       quarters worth ≥ 70¢ of a dollar regardless of benchmark). A side
       that holds the trade's best asset, a single-asset side, and every
       call at `package_bench_trade_wide` ≤ 0 (arm A's pin) keep the
       original own-max math byte-for-byte.
    2. Crown credit per elite asset (value ≥ crown_elite_value) on EITHER
       side, count-independent, at crown_rate_market per piece (flag
       trade.crown_asset still the kill-switch; needs `other_values` to
       know the trade's naive skew).
    3. The crown credit phases out as the naive gap widens: scaled by
       max(0, 1 − |naive_skew| / skew_phaseout), where naive_skew is the
       sides' naive-sum gap over the SMALLER side's sum (symmetric; equals
       results.md's stud-side-denominated skew in the stud-vs-package
       case). An already-lopsided trade earns no consolidation credit —
       KTC's observed shape.
    """
    naive = sum(values)
    if naive <= 0:
        return round(naive, 1)
    own_max = max(values)
    gamma = _c("package_adj_gamma_market")
    floor = _c("package_floor_market")
    bench = own_max
    if (len(values) > 1 and v_max is not None and v_max > own_max
            and _c("package_bench_trade_wide") > 0):
        bench = v_max
        floor = _c("package_floor_cross")
    contrib = sum(v * (floor + (1.0 - floor) * (v / bench) ** gamma)
                  for v in values)
    cap = _c("package_discount_cap")
    total = max(contrib, naive * (1.0 - cap))

    if FLAGS.trade_crown_asset and other_values:
        other_naive = sum(other_values)
        denom = min(naive, other_naive)
        if denom > 0:
            skew = abs(naive - other_naive) / denom
            phaseout = _c("skew_phaseout")
            phase = 1.0 if phaseout <= 0 else max(0.0, 1.0 - skew / phaseout)
            if phase > 0:
                elite_ref = _c("crown_elite_value")
                if elite_ref > 0:
                    rate = _c("crown_rate_market")
                    total += sum(v for v in values if v >= elite_ref) * rate * phase
    return round(total, 1)


def _harmonic_mean(a: float, b: float) -> float:
    """Harmonic mean of two surpluses (amendment A1). 0 if either ≤ 0."""
    if a <= 0 or b <= 0:
        return 0.0
    return 2.0 * a * b / (a + b)


def _shrink_user_elo(
    user_elo: dict[str, float],
    seed_elo: dict[str, float],
    confidence: dict[str, int] | None,
    placements: dict[str, tuple[float, float]] | None = None,
) -> dict[str, float]:
    """
    Confidence shrinkage (Change 4): shrink each personal Elo toward the
    consensus seed by how well-sampled the player is —
    w = n / (n + shrink_pseudocount). A player the user never compared
    sits at consensus (no fake divergence); a heavily-ranked player keeps
    full personal value. confidence=None → no information → no shrinkage.

    `placements` (D-085, knob `placement_tier_clamp`) — {pid: (lo, hi)} from
    `RankingService.placement_bands()`: the Elo band of the tier the user
    explicitly PLACED that player in. The blend above is direction-blind and
    sample-count-driven, and a placement is not a sample — it is the strongest
    statement of value the product accepts. So for a placed player the blend is
    clamped to his band: consensus may still re-price him *inside* the tier the
    user chose, and may never carry him out of it. The clamp is applied AFTER
    the blend rather than replacing it, which is what keeps a mis-placement
    correctable — a user who keeps voting a placed player down still moves him
    within the band, and re-placing him is the way to leave it.

    Nothing else changes: only pids present in `placements` are touched, so an
    unplaced player is priced exactly as before (clamping those would freeze
    the whole board). Players placed BELOW the lowest band — the #161 demotion
    Elo and the anchor "no value" answer — carry no band and are absent from
    the map by construction; see `RankingService.placement_bands`.

    placements=None, an empty map, or `placement_tier_clamp` at 0 ⇒ the
    pre-D-085 blend, byte for byte.

    D-095 — `user_elo_shrink` (landability challenger, bake-off arm D). At 0
    this whole function is skipped: the user's board is returned RAW, exactly
    as the partner's `elo_ratings` already are. The shrink is user-only, and
    that asymmetry — shrunk user vs raw partner — is what makes 86.9% of
    boarded-pair cards exist in only one direction. The challenger's stance is
    shrink-NEITHER; shrink-both would need `comparison_counts` on
    `member_rankings`, which do not exist (PRD N8). At the live default of 1.0
    nothing below changes, byte for byte.

    Deliberately an early return rather than `w = 1`: at 0 the challenger
    prices the raw board, so the D-085 placement clamp — a bound on the BLEND
    — has nothing left to bound. A raw personal Elo already is the user's own
    stated number; clamping it to the band of the tier they placed him in
    would be re-deriving their opinion from their opinion.
    """
    if confidence is None or _c("user_elo_shrink") <= 0:
        return dict(user_elo)
    n0 = _c("shrink_pseudocount")
    bands = placements if (placements and _c("placement_tier_clamp") > 0) else None
    out: dict[str, float] = {}
    for pid, elo in user_elo.items():
        n = max(confidence.get(pid, 0), 0)
        w = n / (n + n0)
        blended = w * elo + (1.0 - w) * seed_elo.get(pid, 1500.0)
        if bands is not None:
            band = bands.get(pid)
            if band is not None:
                blended = min(max(blended, band[0]), band[1])
        out[pid] = blended
    return out


def _value_uncertainty(pid: str, confidence: dict[str, int] | None) -> float:
    """
    Per-player value half-width as a FRACTION of value (amendment A4):
    unc = range_base / sqrt(1 + n). confidence=None → 0 (point values),
    which degrades the range-overlap fairness gate to the point gate.

    Deliberately NOT placement-aware (D-085). Two reasons, decided rather than
    defaulted. (1) This half-width is read by a GATE — the range-overlap
    fairness check prices `g_unc`/`r_unc` from it — and gates judge the real
    package, so narrowing the range for placed players would silently change
    what the gate lets through. That is the one thing the ranking-vs-gate
    separation below forbids without an operator call. (2) A placement bounds
    WHERE the point estimate may sit; it says nothing about how precisely the
    user knows the value inside that tier — the bands run 45-205 Elo wide,
    which is exactly the room a placement leaves undetermined. `comparison_
    counts` still feeds both consumers off one map (`pin_exclude_comparisons`
    remains the single knob for that); D-085 adds a bound on the blend, not a
    second confidence source.
    """
    if confidence is None:
        return 0.0
    n = max(confidence.get(pid, 0), 0)
    return _c("range_base") / math.sqrt(1.0 + n)


# ---------------------------------------------------------------------------
# Engine quality C1/C5 — ranking-vs-gate separation (2026-08-18)
# docs/plans/engine-quality/scope.md §5.
#
# A GATE judges the real package: a pick genuinely transfers value and can
# genuinely make an unfair trade fair, so every gate keeps pricing the whole
# thing on real consensus values. A RANKING term may judge only the
# divergence-bearing content, because the composite is supposed to score
# MUTUAL GAIN, and an asset both boards price identically carries no
# information about mutual gain at all.
# ---------------------------------------------------------------------------


def board_divergence(pid: str, user_val, opp_val) -> float:
    """How much the two boards disagree about ``pid``, as a fraction of the
    larger of the two valuations. 0 = the boards agree exactly, which is what
    every draft pick scores by construction (all boards are primed with the
    same bridged Elo — see pick_swap_ok). user_val / opp_val are RAW board
    accessors (pid → value), never marginal values: this asks "do the two
    managers price him differently?", not "does he fit this roster?"."""
    u, o = user_val(pid), opp_val(pid)
    hi = max(abs(u), abs(o))
    if hi <= 0:
        return 0.0
    return abs(u - o) / hi


def signal_core(ids, user_val, opp_val) -> list[str]:
    """The sub-list of ``ids`` whose board divergence clears
    rank_div_min_frac — the assets that carry mutual-gain information."""
    frac = _c("rank_div_min_frac")
    return [p for p in ids if board_divergence(p, user_val, opp_val) >= frac]


def rank_fairness(fairness: float, give_ids: list[str], recv_ids: list[str],
                  seed_value, user_val, opp_val) -> float:
    """C1 — the fairness term used for RANKING only (Defect A).

    Prices the consensus fairness ratio on the SIGNAL CORE of each side
    instead of the full package, so an asset with ~zero board divergence
    cannot raise it. Because zero-divergence assets are dropped outright
    (not zero-weighted), the invariance is exact in every stud-tax mode:
    adding such an asset to either side leaves this value bit-for-bit
    unchanged, for any base package, fair or not. (Zero-WEIGHTING would not
    do it — package_value_v2's 'heavy' crown premium branches on
    len(values) < n_other, so a zero-valued asset still changes the count.)

    Degenerate cores fall back to the passed-in full-package ``fairness``:
      • one side is entirely zero-divergence — the legitimate "buy a player
        with a pick" shape. Scoring it 0 would systematically demote every
        pick-for-player trade, which is a new defect, not the one being fixed.
      • consensus-basis cards, where nothing diverges by definition.

    rank_div_min_frac <= 0 ⇒ returns ``fairness`` unchanged (kill value:
    byte-identical pre-C1 behaviour).
    """
    if _c("rank_div_min_frac") <= 0:
        return fairness
    core_give = signal_core(give_ids, user_val, opp_val)
    core_recv = signal_core(recv_ids, user_val, opp_val)
    if not core_give or not core_recv:
        return fairness
    gvals = [seed_value(p) for p in core_give]
    rvals = [seed_value(p) for p in core_recv]
    v_max = max(gvals + rvals)
    gv = package_value_v2(gvals, v_max, n_other=len(core_recv),
                          other_values=rvals)
    rv = package_value_v2(rvals, v_max, n_other=len(core_give),
                          other_values=gvals)
    if gv <= 0 or rv <= 0:
        return fairness
    return round(min(gv, rv) / max(gv, rv), 3)


def mismatch_damp(ids, seed_value, confidence: dict[str, int] | None) -> float:
    """C5 — multiplier on the RANKING mismatch term.

    _value_uncertainty already shrinks with comparison count, but it fed only
    the fairness GATE's range overlap, never the ranking. A package whose
    apparent divergence rests on players almost nobody has ranked should not
    outrank one built on well-sampled disagreement, so scale the mismatch
    contribution by max(0, 1 − damp × unc) where unc is the package's
    value-weighted mean per-asset uncertainty.

    The surplus gates are untouched — this only reorders cards that already
    cleared them. confidence=None (no counts available) ⇒ unc is 0 ⇒ 1.0, and
    mismatch_confidence_damp <= 0 ⇒ 1.0 (kill value: byte-identical pre-C5).
    """
    k = _c("mismatch_confidence_damp")
    if k <= 0 or confidence is None:
        return 1.0
    vals = [seed_value(p) for p in ids]
    total = sum(vals)
    if total <= 0:
        return 1.0
    unc = sum(v * _value_uncertainty(p, confidence)
              for v, p in zip(vals, ids)) / total
    return max(0.0, 1.0 - k * unc)


def deck_centerpiece(give_ids, recv_ids, seed_elo: dict) -> str | None:
    """C4 — a package's centerpiece: its highest-consensus asset.

    THE single definition, shared with `deck_impressions.centerpiece_id`
    (server._fatigue_centerpiece delegates here) so the headliner cap and the
    metric that measured the flooding agree by construction. Deterministic
    tie-break by player id, so serve-time and decline-time derivations agree
    even on a cold seed map.
    """
    pids = [str(p) for p in list(give_ids or []) + list(recv_ids or [])]
    if not pids:
        return None
    return max(pids, key=lambda p: (float(seed_elo.get(p, 1500.0)), p))


def deck_give_headliner(give_ids, seed_elo: dict,
                        players: dict | None = None) -> str | None:
    """C4b — the GIVE side's headliner: the asset this card asks the user to
    send that a user would name the trade after.

    Deliberately NOT `deck_centerpiece(give, [], ...)`, and deliberately a
    SECOND function rather than a change to `deck_centerpiece`: that one is
    THE shared definition behind `deck_impressions.centerpiece_id` and the
    decline-time fatigue key (`server._fatigue_centerpiece` delegates to it),
    so re-keying it would silently re-key fatigue matching against every row
    already written. Two questions, two functions.

    Two differences from `deck_centerpiece`:

      * give side only — "what am I being asked to trade away" is the
        repetition the user actually feels;
      * players outrank picks. A pick only headlines an all-pick give side.
        Unknown assets default to 1500.0 and D-079 lifted every 1st to ~1650,
        so a pick routinely out-Elos the player it is being traded for; since
        each card offers a DIFFERENT pick slot, letting a pick headline is
        exactly what made the centerpiece cap inert here.

    Deterministic id tie-break, same as `deck_centerpiece`, so serve-time and
    any later re-derivation agree even on a cold seed map.
    """
    pids = [str(p) for p in list(give_ids or [])]
    if not pids:
        return None
    if players is not None:
        real = [p for p in pids if not is_pick_asset(players.get(p))]
        if real:
            pids = real
    return max(pids, key=lambda p: (float(seed_elo.get(p, 1500.0)), p))


def cap_give_headliners(cards: list, seed_elo: dict, players: dict | None,
                        cap: int) -> list:
    """C4b — keep at most `cap` cards per give-side headliner, in the order
    given. The caller sorts first, so each headliner keeps its BEST cards.

    LEAVE-SHORT, never backfill: a dropped card is not replaced, exactly like
    `compose_group`'s lane quotas (bakeoff_runner). A thinner deck of distinct
    asks is the product decision; silently topping it back up with more of the
    same headliner would restore the defect and hide it from the group
    shortfall accounting.

    `cap <= 0` or an empty seed map ⇒ the input list unchanged (an empty seed
    map carries no consensus, so every asset ties at 1500 and "headliner"
    degenerates to "largest player id" — capping on that drops cards for no
    reason). Same inertness rule as the centerpiece cap.
    """
    if cap <= 0 or not seed_elo:
        return cards
    seen: dict[str, int] = {}
    kept: list = []
    for c in cards:
        head = deck_give_headliner(c.give_player_ids, seed_elo, players)
        if head is not None:
            if seen.get(head, 0) >= cap:
                continue
            seen[head] = seen.get(head, 0) + 1
        kept.append(c)
    return kept


def user_gain_ok_1for1(
    give_ids: list[str],
    recv_ids: list[str],
    raw_user_elo: dict[str, float] | None,
) -> bool:
    """
    #108 — 1-for-1 user-board gate. A 1-for-1 player swap must never ask
    the user to send a player they rank ABOVE the player they receive on
    their OWN raw board (user_elo as saved, pre-shrinkage/pre-blend).
    Shrinkage exists to damp overstated divergence, but it can also pull a
    lightly-sampled player toward a consensus that inverts the user's own
    ordering — the surplus gate then runs on a board the user never saw.

    Multi-asset packages pass unconditionally: there the aggregate surplus
    gate is the compensation test. Players absent from the raw board carry
    no signal and pass. Threshold: user_gain_epsilon (value space).
    """
    if len(give_ids) != 1 or len(recv_ids) != 1 or not raw_user_elo:
        return True
    give_e = raw_user_elo.get(give_ids[0])
    recv_e = raw_user_elo.get(recv_ids[0])
    if give_e is None or recv_e is None:
        return True
    return (elo_to_value(recv_e) - elo_to_value(give_e)
            >= _c("user_gain_epsilon"))


def filler_ok(give_ids: list[str], recv_ids: list[str],
              user_val, opp_val) -> bool:
    """
    #141 — junk-filler gate ("suggestions add low-value players to both
    sides"). For each side with 2+ assets, every piece except the
    headliner (the side's best asset) must be worth at least
    filler_min_frac of that headliner. Per-player metric:
    max(user_val(pid), opp_val(pid)) — a filler EITHER board values
    highly survives; only a player both boards agree is junk is gated.
    Single-asset sides (the 1-for-1 core) pass untouched;
    filler_min_frac <= 0 disables the gate entirely (pre-#141 behavior).

    user_val / opp_val are RAW board-value accessors (pid → value), never
    marginal values — marginal valuation deliberately collapses depth
    pieces, but "does this look like junk?" is a board-value judgment.

    Interview 2026-07-17 ("both floors"): non-headliner pieces must clear
    BOTH the relative bar and the absolute asset_floor_abs — a stud deal
    can't include lottery scratchers (relative) and no deal includes pure
    roster-clogger bodies (absolute), even when the relative bar is tiny.
    """
    frac = _c("filler_min_frac")
    if frac <= 0:          # master kill-switch: pre-#141 behavior exactly
        return True
    abs_floor = _c("asset_floor_abs")
    for side in (give_ids, recv_ids):
        if len(side) < 2:
            continue
        vals = sorted((max(user_val(p), opp_val(p)) for p in side),
                      reverse=True)
        bar = max(vals[0] * frac, abs_floor)
        if any(v < bar for v in vals[1:]):
            return False
    return True


def price_consensus_package(
    give_ids: list[str],
    recv_ids: list[str],
    *,
    value_of,
):
    """The PRICING half of `eval_consensus_package`, gate-free:
    `package_value_v2` on both sides in the shared value space, nothing
    else. Returns `(fairness, gv, rv)`, or None when a side prices
    non-positive.

    Split out of `eval_consensus_package` on 2026-08-28 (#402 rev-3 §3) so
    the tier-scope lateral path — whose membership rule is tier equality,
    with the ±band, the #108 gain gates and the fairness floor deliberately
    removed — still prices ideas through the SAME math as every gated
    surface instead of re-stating it. `eval_consensus_package` calls this
    first, so the two can never drift (the one-gate-function guard in
    test_fair_packages.py is the enforcement)."""
    gvals = [value_of(p) for p in give_ids]
    rvals = [value_of(p) for p in recv_ids]
    v_max = max(gvals + rvals)
    gv = package_value_v2(gvals, v_max, n_other=len(recv_ids),
                          other_values=rvals)
    rv = package_value_v2(rvals, v_max, n_other=len(give_ids),
                          other_values=gvals)
    if gv <= 0 or rv <= 0:
        return None
    return min(gv, rv) / max(gv, rv), gv, rv


def eval_consensus_package(
    give_ids: list[str],
    recv_ids: list[str],
    *,
    value_of,
    raw_value_of,
    raw_user_elo: dict[str, float] | None,
    relaxed_thr: float,
):
    """The consensus-basis package gate set, in ONE place.

    Prices both sides with `package_value_v2` in the shared value space and
    applies every non-fairness gate the consensus generator applies, then the
    WIDENED fairness band. Returns `(fairness, gv, rv)`, or None when any gate
    refuses.

    Extracted from `_generate_asset_ideas_impl._eval` on 2026-08-22 (#384 W6-B)
    so the fair-package search (`_generate_fair_packages_impl`) rides the same
    gates instead of re-stating them — a second copy is how two surfaces that
    are supposed to price identically start disagreeing. Behaviour is
    unchanged from the closure it replaces; asset-ideas is byte-identical.

    `value_of` is the CONSENSUS accessor (pid → value); `raw_value_of` is the
    #141 max-of-boards accessor. `relaxed_thr` is already
    min(caller threshold, relaxed_fairness_threshold) — the caller decides
    afterwards whether a pass was strict or relaxed, because that split is a
    presentation convention (#189), not a gate.
    """
    priced = price_consensus_package(give_ids, recv_ids, value_of=value_of)
    if priced is None:
        return None
    fairness, gv, rv = priced
    # #108 — consensus IS the user's board here (never relaxed).
    if rv - gv < _c("user_gain_epsilon"):
        return None
    frac = _c("consolidation_raw_loss_frac")
    if frac > 0 and len(give_ids) > len(recv_ids):
        raw_give = sum(value_of(p) for p in give_ids)
        if raw_give - sum(value_of(p) for p in recv_ids) > frac * raw_give:
            return None
    if not user_gain_ok_1for1(give_ids, recv_ids, raw_user_elo):
        return None
    if not filler_ok(give_ids, recv_ids, raw_value_of, value_of):
        return None
    if fairness < relaxed_thr:
        return None
    return fairness, gv, rv


def is_pick_asset(p) -> bool:
    """True for any draft-pick asset in the player maps: owned-pick
    pseudo-players (position == "PICK", injected by
    server._owned_pick_assets) and the universal pool's generic picks
    (which carry a REAL position so they mix into the trio tabs, but are
    always team == "PICK"). None → False."""
    return bool(p is not None and (
        getattr(p, "position", None) == "PICK"
        or getattr(p, "team", None) == "PICK"))


def _pos_for_avoid(p) -> "str | None":
    """Position key used by the #360 receive-side avoid filter.

    Pick-ness is resolved FIRST, via the canonical is_pick_asset: the generic
    pick rungs carry a deliberately FAKE player position (_PICK_POS in
    server.build_universal_pool, {1:"RB",2:"WR",3:"TE",4:"QB"}) so they
    distribute across the trio tabs. Reading p.position raw here would let
    "avoid QB" delete every 4th-round pick from the receive pool, which is a
    defect, not consistency. Avoiding "PICK" — one of the five DNA chips — is
    the only way to exclude pick assets.

    Deliberately STRICTER AND MORE CORRECT than the neighbouring
    _positions_ok (trade_optimizer.py / trade_service.py), which reads raw
    ``position``. Fixing those two is a behavior change to shipped features
    that nobody asked for; the asymmetry is recorded in
    docs/cross-client-invariants.md and docs/glossary.md.
    """
    if p is None:
        return None
    if is_pick_asset(p):
        return "PICK"
    return getattr(p, "position", None)


def avoid_ok(pid: str, players: dict, avoid) -> bool:
    """#360 — True when player/asset ``pid`` may enter a RECEIVE pool.

    Unknown ids pass (they cannot be scored anyway and the surrounding pool
    builders already filter on membership). ``avoid`` is any container of
    uppercase position strings; falsy ⇒ everything passes.
    """
    if not avoid:
        return True
    return _pos_for_avoid(players.get(pid)) not in avoid


def strip_matched_pick_pairs(give_ids: list[str], recv_ids: list[str],
                             players: dict, seed_value,
                             frac: float) -> tuple[list[str], list[str]]:
    """C3 helper — remove matched/near-matched pick PAIRS from the two sides.

    Picks are collected per side, sorted by consensus value (best first) and
    paired across the sides index-wise. A pair whose min/max value ratio is at
    or above ``frac`` is "matched": the same asset class at the same price on
    both boards, contributing zero divergence in BOTH directions, so it tells
    us nothing about the trade. Both members are dropped.

    Pairing best-against-best is what preserves CONSOLIDATION: two lesser
    picks for one better pick pair the better one against the larger lesser
    one, their ratio falls outside the band, nothing strips, and the shape
    survives — which is right, because changing pick shape has real utility
    even at equal total value. Returns the surviving (give, recv) lists with
    the original order otherwise intact; deterministic for a fixed input.
    """
    g_picks = sorted((p for p in give_ids if is_pick_asset(players.get(p))),
                     key=lambda p: (-seed_value(p), p))
    r_picks = sorted((p for p in recv_ids if is_pick_asset(players.get(p))),
                     key=lambda p: (-seed_value(p), p))
    drop: set[str] = set()
    for gp, rp in zip(g_picks, r_picks):
        gv, rv = seed_value(gp), seed_value(rp)
        hi = max(gv, rv)
        if hi <= 0:
            continue
        if min(gv, rv) / hi >= frac:
            drop.add(gp)
            drop.add(rp)
    if not drop:
        return list(give_ids), list(recv_ids)
    return ([p for p in give_ids if p not in drop],
            [p for p in recv_ids if p not in drop])


def pick_swap_ok(give_ids: list[str], recv_ids: list[str],
                 players: dict, seed_value=None) -> bool:
    """#227 — degenerate pick-churn gate: a card whose real content is a
    pick-for-pick swap is never a suggestion. Picks carry zero divergence by
    construction (every board is primed with the same bridged Elo), so a
    pick-for-pick swap the fairness gate passes is ~equal-value churn with
    no mutual-gain basis.

    Originally this banned only the LITERAL 1-for-1 both-sides-pick shape,
    and said so: pick-for-pick INSIDE a package passed by design. That let a
    1st-for-1st ride along inside a bigger deal contributing nothing in
    either direction — the operator saw exactly this, and a tester
    free-texted "another example of a random 1st swap. Shouldn't happen".

    C3 (2026-08-18, docs/plans/engine-quality/scope.md) closes it: matched
    pick pairs are STRIPPED from both sides first, so the underlying trade is
    judged on its real content. If stripping empties a side, the real content
    WAS the pick swap — that shape is churn and is killed.

    The documented legitimate cases are preserved:
      • picks as sweeteners / headline compensation — only one side holds
        picks, so nothing pairs and nothing strips;
      • pick CONSOLIDATION (2 lesser picks for 1 better) — the values sit
        outside the match band, so nothing strips and the shape survives;
      • player-for-pick and pick-for-player 1-for-1s — unchanged.

    ``seed_value`` (pid → consensus value) is what makes the strip possible;
    callers that omit it, and ``pick_pair_strip_frac`` <= 0, both fall back to
    the pre-C3 literal-1-for-1 rule, byte-identical. Shared by the v2 pair
    path, the v3 optimizer and the consensus fallback.
    """
    frac = _c("pick_pair_strip_frac")
    if frac > 0 and seed_value is not None:
        give_ids, recv_ids = strip_matched_pick_pairs(
            give_ids, recv_ids, players, seed_value, frac)
        if not give_ids or not recv_ids:
            return False
    if len(give_ids) != 1 or len(recv_ids) != 1:
        return True
    return not (is_pick_asset(players.get(give_ids[0]))
                and is_pick_asset(players.get(recv_ids[0])))


# ---------------------------------------------------------------------------
# Presentment rules (flag trade.presentment_rules) — G6 #340/#341/#339/#304
# docs/feedback/items/304-positional-need-filter/lld-delta.md §3.
# One module-level predicate per rule, alongside filler_ok/pick_swap_ok so
# trade_optimizer can consume them the same way. All values are raw summed
# consensus (`seed_value` per side) — the D-055 Δ currency. Each returns
# True = the package may be presented, False = KILL.
# ---------------------------------------------------------------------------

# Positions the R2 net cap and the R5 need gate count. K/DEF/IDP (exotic
# leagues) and PICK pseudo-assets are uncounted by design.
_PRESENTMENT_POSITIONS = ("QB", "RB", "WR", "TE")


def overpay_ok(give_ids, recv_ids, seed_value) -> bool:
    """R1 #340 — absolute overpay ceiling, BOTH sides.

    KILL when gap >= max_overpay_min_value AND gap / max(g, r) >=
    max_overpay_frac, where g/r are raw consensus sums (players AND picks).
    Deliberately NEVER reads fairness_threshold — the mobile fairness
    toggle cannot relax it; this is the operative absolute bound on both
    settings. A *small* relative gap is simply fair — no upper-bound
    counterpart exists (round-1 B1 re-audit). frac <= 0 disables.

    **C2, 2026-08-23** (docs/plans/knockout-refine/plan.md §3) — knob
    `overpay_adjusted`. At >= 1.0 (the default) each side is priced with
    `package_value_v2` under the SAME argument convention the consensus
    emit path uses (`_consensus_package_gates`: trade-wide `v_max`,
    `n_other` = the other side's asset count, `other_values` = the other
    side's raw values), so the gap is measured in the currency the
    fairness bar and the card already show instead of in raw sums. Same
    0.25 frac, same `max_overpay_min_value` floor, still `abs()`
    two-sided. R1's 0.25 was calibrated on a 78%-one-for-one corpus,
    where the two currencies coincide — a single-asset side is identity
    under `package_value_v2` — so this knob can only move MULTI-asset
    packages. Knob 0 restores the raw-sum body, byte-identical.
    """
    frac = _c("max_overpay_frac")
    if frac <= 0:
        return True
    if _c("overpay_adjusted") >= 1.0:
        gvals = [seed_value(p) for p in give_ids]
        rvals = [seed_value(p) for p in recv_ids]
        both = gvals + rvals
        if not both:
            return True
        v_max = max(both)
        g = package_value_v2(gvals, v_max, n_other=len(recv_ids),
                             other_values=rvals)
        r = package_value_v2(rvals, v_max, n_other=len(give_ids),
                             other_values=gvals)
    else:
        g = sum(seed_value(p) for p in give_ids)
        r = sum(seed_value(p) for p in recv_ids)
    big = max(g, r)
    if big <= 0:
        return True
    gap = abs(g - r)
    return not (gap >= _c("max_overpay_min_value") and gap / big >= frac)


def pos_net_ok(give_ids, recv_ids, players, *, opp_ctx=None) -> bool:
    """R2 #341 — per-position signed net cap.

    For each P in {QB, RB, WR, TE}: net_P = count(recv at P) − count(give
    at P) — ONE signed quantity per position, not a per-side count, so
    2RB→2RB is net 0 and passes. KILL when any |net_P| > pos_net_cap.
    Players only: pick assets are excluded (a pick is not a positional
    body; picks are R3's domain). Positions outside the four are uncounted
    by design. cap <= 0 disables (filler_min_frac convention).

    **C3, 2026-08-23** (docs/plans/knockout-refine/plan.md §3) — knob
    `pos_net_starter_relief`, plus `opp_ctx` (`_presentment_ctx`, threaded
    per league-mate by the job closure). The COUNT rule was only ever a
    proxy for the operator's #341 intent — "don't ship me two starting RBs
    and send none back". At >= 1.0, with a ctx present, an over-cap
    position P survives only when the depth story holds:

      * the SHEDDING side (the user when net_P < 0, the opponent when
        net_P > 0) was STRICTLY ABOVE its starter need at P before, and
      * BOTH rosters are still at/above starter need at P after.

    Bodies are counted in `analyze_roster_strengths`' own startable
    definition (elite|starter bin — `_startable_ok_fn`), so RB4 + RB5 out
    of an RB-rich roster passes while RB1 + RB2 out of a three-deep one
    dies. Starter need is `_starters_at` (`_STARTER_NEED`, QB→2 in
    superflex). Picks stay excluded exactly as today. Knob 0, or no ctx
    (the fit K-chain, unit callers), ⇒ today's flat kill, byte-identical.
    """
    cap = _c("pos_net_cap")
    if cap <= 0:
        return True
    net: dict[str, int] = {}
    for ids, sign in ((recv_ids, 1), (give_ids, -1)):
        for pid in ids:
            p = players.get(pid)
            if p is None or is_pick_asset(p):
                continue
            pos = getattr(p, "position", None)
            if pos in _PRESENTMENT_POSITIONS:
                net[pos] = net.get(pos, 0) + sign
    over = {pos: n for pos, n in net.items() if abs(n) > cap}
    if not over:
        return True
    if opp_ctx is None or _c("pos_net_starter_relief") < 1.0:
        return False
    startable_ok = opp_ctx["startable_ok"]
    user_startable = opp_ctx["user_startable"]
    opp_startable = opp_ctx["startable"]
    scoring_format = opp_ctx["scoring_format"]

    def _moved(ids, pos) -> int:
        """Startable bodies at `pos` inside one side of the package."""
        n = 0
        for pid in ids:
            p = players.get(pid)
            if p is not None and getattr(p, "position", None) == pos \
                    and startable_ok(pid, p):
                n += 1
        return n

    for pos, n in over.items():
        need = _starters_at(pos, scoring_format)
        out_of_user = _moved(give_ids, pos)
        out_of_opp = _moved(recv_ids, pos)
        u_before = user_startable.get(pos, 0)
        o_before = opp_startable.get(pos, 0)
        u_after = u_before - out_of_user + out_of_opp
        o_after = o_before - out_of_opp + out_of_user
        shed_before = u_before if n < 0 else o_before
        if not (shed_before > need and u_after >= need and o_after >= need):
            return False
    return True


def pick_gap_ok(give_ids, recv_ids, seed_value, players) -> bool:
    """R3 #339 — "the pick IS the gap" (two-sided band).

    Only evaluated when the package contains >= 1 pick. H = heavier side
    by raw consensus sum. KILL when gap >= pick_gap_min_value AND some
    pick p in H has pick_gap_frac × gap <= seed_value(p) <= gap /
    pick_gap_frac — the overpaying side is shipping a pick that
    single-handedly explains its excess. Two-sided on purpose (round-1
    B1): a pick far LARGER than the gap is a stud-scaled centerpiece
    consolidation and passes; the enumerators generate the pick-less
    sibling shape independently, so the kill loses nothing. frac 0
    disables; same knob mirrored forms the upper bound (no second key).
    """
    frac = _c("pick_gap_frac")
    if frac <= 0:
        return True
    if not any(is_pick_asset(players.get(p))
               for p in list(give_ids) + list(recv_ids)):
        return True
    g = sum(seed_value(p) for p in give_ids)
    r = sum(seed_value(p) for p in recv_ids)
    gap = abs(g - r)
    if gap < _c("pick_gap_min_value"):
        return True
    heavy = give_ids if g >= r else recv_ids
    lo, hi = frac * gap, gap / frac
    for pid in heavy:
        if is_pick_asset(players.get(pid)):
            v = seed_value(pid)
            if lo <= v <= hi:
                return False
    return True


def need_gate_ok(give_ids, recv_ids, *, seed_value, players, user_pos_values,
                 outlook, position_needs, position_surplus,
                 scoring_format, opp_ctx=None) -> bool:
    """R5 #304 — window-scaled need gate, UNTARGETED discovery decks only
    (the caller skips this predicate entirely when the job is targeted —
    R-5b bypass, derived server-side in _run_trade_job).

    Judged on the PRIMARY received asset only (highest consensus value,
    players only; pick-primary cards exempt — secondary pieces are #141's
    domain), on the CONSENSUS board (recorded decision — the user-board
    variant is a named follow-up). user_pos_values maps position →
    [(pid, consensus value)] over the user's FULL pre-trade roster; the
    incumbent is computed on the post-give roster (roster − give_ids,
    round-1 B2) so a tier-down that sends the very starter away survives.

        PASS  v < need_gate_min_value                    (sub-floor churn)
        PASS  P fills a starting hole (post-give bodies at P < S)
        PASS  v > incumbent × (1 + need_gate_upgrade_margin)
        else, by resolved window:
          championship | contender      → KILL
          not_sure                      → KILL only if P in surplus
          rebuilder | jets | unresolved → PASS (gate off — deliberate
                                          fail-open, recorded decision)

    **C1, 2026-08-23** (docs/plans/knockout-refine/plan.md §3) — knob
    `need_gate_dual_rescue`, two edits, both no-ops at knob 0:

      (a) *any-asset*: the hole/upgrade tests judge EVERY non-pick
          received asset at its own position, not only the primary. A
          2-for-1 whose second piece is the one that fills the hole is a
          real need trade and used to die on the headliner alone.
      (b) *dual-need rescue*, checked just before the contender kill: pass
          when the give side ships >= 1 non-pick asset at a position where
          the USER is in `position_surplus` AND the OPPONENT sits below
          his starter need (`opp_ctx`, threaded per league-mate). R5 was
          a one-sided kill with no partner-need term at all; this is the
          two-sided form the 2026-08-22 replay measured at one-sidedness
          96.3% → 88.7%.

    The originating #304 complaint is unchanged by both: a received asset
    that fills no hole and upgrades nobody, with no dual-need fact on the
    give side, still dies for a contender.
    """
    floor = _c("need_gate_min_value")
    if floor <= 0:
        return True
    if outlook in ("rebuilder", "jets") or not outlook:
        return True                       # window exempt / unresolved
    primary_pos, primary_val = None, -1.0
    for pid in recv_ids:
        p = players.get(pid)
        if p is None or is_pick_asset(p):
            continue
        v = seed_value(pid)
        if v > primary_val:
            primary_val = v
            primary_pos = getattr(p, "position", None)
    if primary_pos not in _PRESENTMENT_POSITIONS:
        return True                       # pick-primary / unknown — exempt
    if primary_val < floor:
        return True                       # sub-floor churn
    # NOTE: position_needs is threaded alongside position_surplus (the
    # resolved analyze_roster_strengths outputs — no second resolution
    # path, D-060), but the hole check below is deliberately the POST-GIVE
    # consensus body count vs starter slots (lld §3 pseudo), not the
    # value-tiered needs profile — the two disagree exactly when the
    # roster holds sub-starter bodies at P, and the incumbent/upgrade
    # branch already prices that case.
    _ = position_needs
    give_set = set(give_ids)

    def _clears(pos: str, val: float) -> bool:
        """Today's two PASS tests, for one received asset at `pos`."""
        vals = sorted((v for pid, v in user_pos_values.get(pos, ())
                       if pid not in give_set), reverse=True)
        starters = _starters_at(pos, scoring_format)
        if len(vals) < starters:
            return True                   # fills a starting hole
        incumbent = vals[starters - 1]
        return val > incumbent * (1.0 + _c("need_gate_upgrade_margin"))

    if _clears(primary_pos, primary_val):
        return True                       # hole filled / starter upgrade
    if _c("need_gate_dual_rescue") >= 1.0:
        # (a) any-asset — the primary is not the only piece that can be
        # the point of the trade.
        for pid in recv_ids:
            p = players.get(pid)
            if p is None or is_pick_asset(p):
                continue
            pos = getattr(p, "position", None)
            if pos in _PRESENTMENT_POSITIONS and _clears(pos, seed_value(pid)):
                return True
        # (b) dual-need rescue — the user sheds surplus at a position the
        # partner is short at. Needs the per-member ctx; without it (unit
        # callers, the fit K-chain) this branch cannot fire.
        if opp_ctx is not None:
            surplus = set(position_surplus or ())
            opp_startable = opp_ctx["startable"]
            for pid in give_ids:
                p = players.get(pid)
                if p is None or is_pick_asset(p):
                    continue
                pos = getattr(p, "position", None)
                if pos in surplus and pos in _PRESENTMENT_POSITIONS \
                        and opp_startable.get(pos, 0) < _starters_at(
                            pos, scoring_format):
                    return True
    if outlook in ("championship", "contender"):
        return False
    if outlook == "not_sure":
        return primary_pos not in (position_surplus or ())
    return True


# ---------------------------------------------------------------------------
# Roster strength analysis (Feature 2: roster-aware match context)
# ---------------------------------------------------------------------------

# Dynasty-value tier thresholds (KTC-scale, ktc_max=10000).
# Tuned so a typical 12-team starter hits ~1500+, an elite player ~4000+.
_TIER_ELITE   = 4000.0
_TIER_STARTER = 1500.0
_TIER_BENCH   = 500.0

# Per-position starter-depth thresholds. Superflex bumps QB to require 2.
_STARTER_NEED = {"QB": 1, "RB": 2, "WR": 2, "TE": 1}
_SURPLUS_AT   = {"QB": 2, "RB": 4, "WR": 4, "TE": 2}


def _bin_player(value: float) -> str | None:
    if value >= _TIER_ELITE:
        return "elite"
    if value >= _TIER_STARTER:
        return "starter"
    if value >= _TIER_BENCH:
        return "bench"
    return None


# ---------------------------------------------------------------------------
# #366 — position-relative tier bands (flag: trade.position_tiers, default OFF)
# Scope block: docs/feedback/items/366-tier-ladder/scope.md
# ---------------------------------------------------------------------------
#
# WHY THE ABSOLUTE CUTS ABOVE ARE WRONG, IN ONE PARAGRAPH.
# `dynasty_value(p) = ktc_max · e^(−ktc_k·(search_rank−1))` is a pure monotone
# function of Sleeper's OVERALL `search_rank`, so `_TIER_ELITE = 4000` is not a
# value judgement at all — it is the disguised statement "overall rank <= 73".
# Against the live pool that admits 33 elite RBs, 33 elite WRs, 17 elite QBs
# and SEVEN elite TEs. The word means something different at every position
# while presenting as one word, which is exactly what feedback #366 reported.
#
# THE FIX LEAVES VALUE SPACE ENTIRELY. Bands are cut in rank-WITHIN-POSITION,
# so "elite QB" and "elite TE" mean the same thing by construction and no
# constant needs recalibrating when the value curve moves. That second property
# is not hypothetical: #117 retuned ktc_k/ktc_max and moved every one of the
# absolute bins at once (docs/runbook.md § Trade-engine side effects).
#
# NOTE for anyone reading plan-remaining.md §2: it blames "board-wide value
# inflation". That is not the mechanism — search_rank is an ordinal and cannot
# inflate. The drift vector is a model_config retune. Same fix, different cause.
#
# The cuts, in positional rank, derived from what a league actually starts
# (1 QB, 2 RB, 2 WR, 1 TE; superflex starts 2 QB), for a 12-team league:
#   Elite       — top HALF of the league's starting demand: a positional edge
#   Starter     — inside 1.5x the demand: a genuinely startable body
#   Replacement — inside 2.5x: above the waiver pool, below a starter
# `analyze_roster_strengths` is not passed league size and this change does not
# add a parameter to a signature six call sites depend on, so 12 is assumed.
_POS_TIER_CUTS: dict[str, tuple[int, int, int]] = {
    "QB": (6, 18, 32),
    "RB": (12, 36, 60),
    "WR": (12, 36, 60),
    "TE": (6, 18, 32),
}
# Superflex starts two quarterbacks, so QB scarcity matches RB/WR scarcity.
_POS_TIER_CUTS_SF_QB: tuple[int, int, int] = (12, 36, 60)

# Positional rank is only meaningful over a real pool. Below this many ranked
# players at a position, `players` is a hand-built fixture or a synthetic demo
# session, not the universal pool, and that position falls back to the absolute
# cuts. Real Sleeper pools carry 313 QB / 568 RB / 1134 WR / 516 TE. The mode is
# REPORTED (`tier_basis`), never silent — a hidden mode switch on pool size is
# how a fixture quietly starts proving something other than production.
_POS_TIER_MIN_POOL = 40

# Ordered bin names, low index = better. Index i of a _POS_TIER_CUTS tuple.
_POS_TIER_BINS: tuple[str, str, str] = ("elite", "starter", "bench")

# Memo for the positional-rank map, keyed on the IDENTITY of the `players`
# dict. Two slots is enough: the engine reuses one pool object across a whole
# generation run (trade_service `self._players`, trade_gen_v2's `players`), and
# the routes build one `players_meta` per request. Building the map over the
# real 2684-player pool measures 1.31 ms, so the memo exists to keep the
# engine's per-member loops (13 calls per deck) from paying it thirteen times,
# not because a single build is expensive.
#
# The STRONG reference to the pool dict is load-bearing: `id()` is only unique
# among live objects, so caching on `id(players)` without pinning the object
# would let a freed pool's address be recycled by a different dict and serve
# its ranks. Holding the reference makes that impossible.
_POS_RANK_CACHE: list[tuple[int, dict, dict[str, int]]] = []


def _positional_rank_map(players: dict) -> dict[str, int]:
    """{player_id: 1-based rank among players at the SAME position}.

    Ordered by Sleeper `search_rank` ascending (lower = better), ties broken on
    player_id so the map is deterministic. Players with no `search_rank` sort
    last — they are unranked, not rank-1, and `dynasty_value` already treats a
    missing rank as `ktc_fallback_rank` for the same reason.
    """
    key = id(players)
    for k, _pool, cached in _POS_RANK_CACHE:
        if k == key:
            return cached

    buckets: dict[str, list[tuple[int, str]]] = {}
    for pid, p in players.items():
        pos = getattr(p, "position", None)
        if pos not in _POS_TIER_CUTS:
            continue
        sr = getattr(p, "search_rank", None)
        try:
            sr_i = int(sr) if sr is not None else None
        except (TypeError, ValueError):
            sr_i = None
        # Unranked sorts after every ranked player.
        buckets.setdefault(pos, []).append(
            (sr_i if sr_i is not None and sr_i > 0 else 10 ** 9, str(pid)))

    out: dict[str, int] = {}
    for pos, lst in buckets.items():
        lst.sort()
        for i, (_sr, pid) in enumerate(lst, 1):
            out[pid] = i

    _POS_RANK_CACHE.append((key, players, out))
    if len(_POS_RANK_CACHE) > 2:
        _POS_RANK_CACHE.pop(0)
    return out


def _pool_depth_by_position(players: dict) -> dict[str, int]:
    """How many players at each core position carry a usable `search_rank`.
    Feeds the `_POS_TIER_MIN_POOL` guard."""
    depth: dict[str, int] = {pos: 0 for pos in _POS_TIER_CUTS}
    for p in players.values():
        pos = getattr(p, "position", None)
        if pos not in depth:
            continue
        sr = getattr(p, "search_rank", None)
        try:
            if sr is not None and int(sr) > 0:
                depth[pos] += 1
        except (TypeError, ValueError):
            continue
    return depth


def _bin_player_relative(pos_rank: int | None, pos: str,
                         is_superflex: bool) -> str | None:
    """Band a player by his rank within his own position. `None` = unranked or
    outside the Replacement cut, matching `_bin_player`'s "not worth counting"."""
    if pos_rank is None:
        return None
    cuts = (_POS_TIER_CUTS_SF_QB
            if (pos == "QB" and is_superflex) else _POS_TIER_CUTS.get(pos))
    if cuts is None:
        return None
    for name, cut in zip(_POS_TIER_BINS, cuts):
        if pos_rank <= cut:
            return name
    return None


def _is_handcuff(player) -> bool:
    """The RB2 on an NFL depth chart — feedback #366, in the operator's words.

    This is Sleeper's OWN depth chart, not an approximation. FTF has ingested
    it all along and this is simply its first reader:
      players.depth_chart_position / .depth_chart_order  database.py:970-971
      written on every sync                              database.py:8769-8770
      re-synced whenever older than 24h                  database.py:8652
      carried on the Player model                        ranking_service.py:262
      hydrated onto every pooled Player                  server.py:1580-1581

    plan-remaining.md §2 asserted no such feed existed and recommended
    approximating with "second-highest-valued RB on the same NFL team". That
    assertion is wrong, and the approximation would have been wrong in exactly
    the committee backfields where the label matters — see D-121.

    What this is NOT: a usage model. In a true committee the order-2 back may
    be a co-starter. The client renders the FACT ("RB2 on his NFL depth chart")
    and never a value or workload claim. Coverage is partial by design — only
    ~149 of 603 RBs sit on a chart at all; the rest are camp bodies and free
    agents, who are correctly nobody's handcuff.
    """
    if getattr(player, "position", None) != "RB":
        return False
    dcp = getattr(player, "depth_chart_position", None)
    if not dcp or str(dcp).strip().upper() != "RB":
        return False
    try:
        return int(getattr(player, "depth_chart_order", None)) == 2
    except (TypeError, ValueError):
        return False


def analyze_roster_strengths(
    roster_player_ids: list[str],
    players: dict,
    scoring_format: str = "1qb_ppr",
) -> dict:
    """
    Profile a roster's positional depth.

    Returns:
        {
          "tier_depth":      {pos: {"elite": n, "starter": n, "bench": n}},
          "position_needs":  [pos, ...],     # below starter threshold
          "position_surplus":[pos, ...],     # at-or-above surplus threshold
        }

    `tier_depth[pos]` is a DISJOINT PARTITION — every counted player lands in
    exactly one bin. Nothing non-disjoint may be added to it (the #366 handcuff
    overlay is a separate top-level key for precisely this reason).

    Two flags extend the return, both default OFF, both independently
    reversible (scope: docs/feedback/items/366-tier-ladder/scope.md):

    `trade.position_tiers` ON
        Bands are cut in rank-within-position instead of absolute dynasty
        value (see _POS_TIER_CUTS above). Adds `tier_basis` and mirrors each
        `bench` count onto a `replacement` key — the report's word — while
        KEEPING `bench`, so a client built before this change still parses the
        payload. OFF, this function returns a dict byte-identical to the one it
        returned before #366; that identity is pinned by
        backend/tests/test_position_tiers.py and it matters because
        `position_needs`/`position_surplus` feed EVERY deck (trade_gen_v2:930,
        :980; trade_service:3413, :3440, :4096, :4172, :4259).

    `trade.rb_handcuff` ON
        Adds `handcuff_rb`: how many of this roster's RBs are the RB2 on their
        NFL depth chart. Purely additive — no engine path reads it. OFF, the
        key is ABSENT (never 0, never null) and no depth_chart_* attribute is
        read at all.
    """
    from .feature_flags import is_enabled
    relative = is_enabled("trade.position_tiers")
    want_handcuff = is_enabled("trade.rb_handcuff")

    tier_depth: dict[str, dict[str, int]] = {
        pos: {"elite": 0, "starter": 0, "bench": 0}
        for pos in ("QB", "RB", "WR", "TE")
    }
    starter_count: dict[str, int] = {pos: 0 for pos in tier_depth}
    is_superflex = scoring_format.startswith("sf")

    pos_rank: dict[str, int] = {}
    # Per position: True = banded by positional rank, False = absolute cuts.
    basis: dict[str, bool] = {pos: False for pos in tier_depth}
    if relative:
        depth = _pool_depth_by_position(players)
        basis = {pos: depth.get(pos, 0) >= _POS_TIER_MIN_POOL for pos in tier_depth}
        if any(basis.values()):
            pos_rank = _positional_rank_map(players)

    handcuff_rb = 0
    for pid in roster_player_ids:
        player = players.get(pid)
        if player is None or getattr(player, "position", None) not in tier_depth:
            continue
        pos = player.position
        if relative and basis.get(pos):
            bin_ = _bin_player_relative(pos_rank.get(str(pid)), pos, is_superflex)
        else:
            bin_ = _bin_player(dynasty_value(player))
        if want_handcuff and _is_handcuff(player):
            handcuff_rb += 1
        if bin_ is None:
            continue
        tier_depth[pos][bin_] += 1
        if bin_ in ("elite", "starter"):
            starter_count[pos] += 1

    needs: list[str] = []
    surplus: list[str] = []
    for pos in tier_depth:
        threshold = _STARTER_NEED[pos]
        if pos == "QB" and is_superflex:
            threshold = 2
        if starter_count[pos] < threshold:
            needs.append(pos)
        if starter_count[pos] >= _SURPLUS_AT[pos]:
            surplus.append(pos)

    out = {
        "tier_depth":       tier_depth,
        "position_needs":   needs,
        "position_surplus": surplus,
    }
    if relative:
        # `replacement` is an ALIAS, not a fourth bin: same count as `bench`,
        # emitted so clients can adopt the report's vocabulary without the wire
        # key changing under a shipped build. `bench` is retained on purpose —
        # dropping it would break every client older than this commit.
        for pos, bins in tier_depth.items():
            bins["replacement"] = bins["bench"]
        out["tier_basis"] = {
            pos: ("position_relative" if ok else "absolute")
            for pos, ok in basis.items()
        }
    if want_handcuff:
        out["handcuff_rb"] = handcuff_rb
    return out


# ---------------------------------------------------------------------------
# Knockout refine — per-member presentment context (2026-08-23)
# docs/plans/knockout-refine/plan.md §2. The G6 predicates were written as a
# JOB-level closure with no counterparty in scope, which is exactly why R5
# was a one-sided kill and R2 a blind count. `opp_profile` already exists at
# the top of the member loop; these two helpers are all it takes to get it
# into the gates.
# ---------------------------------------------------------------------------


def _startable_ok_fn(players: dict, scoring_format: str):
    """Build `(pid, player) -> bool`: is this a STARTABLE body at his position?

    The definition is `analyze_roster_strengths`' OWN — a player whose tier
    bin is `elite` or `starter`, i.e. the two bins that feed its
    `starter_count` and therefore `position_needs` / `position_surplus`. No
    second threshold is invented here: both banding modes are mirrored (the
    `trade.position_tiers` rank-within-position cuts when the flag is on and
    the pool is deep enough, the absolute `_TIER_STARTER` cut otherwise), so
    a count built with this predicate always equals
    `tier_depth[pos]["elite"] + tier_depth[pos]["starter"]` from a profile
    over the same roster. That equality is pinned, under BOTH flag settings,
    by test_knockout_refine.py::test_startable_matches_analyze_roster.

    Built ONCE per job (the flag read and the pool scan are not per-candidate
    work); the returned callable is what the gates call.
    """
    from .feature_flags import is_enabled
    relative = is_enabled("trade.position_tiers")
    is_superflex = scoring_format.startswith("sf")
    pos_rank: dict[str, int] = {}
    basis: dict[str, bool] = {}
    if relative:
        depth = _pool_depth_by_position(players)
        basis = {pos: depth.get(pos, 0) >= _POS_TIER_MIN_POOL
                 for pos in _POS_TIER_CUTS}
        if any(basis.values()):
            pos_rank = _positional_rank_map(players)

    def _ok(pid, player) -> bool:
        pos = getattr(player, "position", None) if player is not None else None
        if pos not in _PRESENTMENT_POSITIONS:
            return False
        if relative and basis.get(pos):
            bin_ = _bin_player_relative(pos_rank.get(str(pid)), pos,
                                        is_superflex)
        else:
            bin_ = _bin_player(dynasty_value(player))
        return bin_ in ("elite", "starter")

    return _ok


def _presentment_ctx(opp_profile: dict, user_startable: dict,
                     startable_ok, scoring_format: str) -> dict:
    """The per-league-mate context R5's rescue and R2's relief read.

    `startable` is the OPPONENT's startable count per position, taken
    straight off the `analyze_roster_strengths` profile the member loop has
    already computed — no second roster pass, no second definition.
    `user_startable` is the job-level twin (built once from
    `_user_pos_values`). Passing `opp_ctx=None` anywhere downstream skips
    every branch that reads this, which is what keeps the knobs' 0 settings
    byte-identical for callers that hold no counterparty.
    """
    td = opp_profile.get("tier_depth", {})
    return {
        "startable": {pos: bins.get("elite", 0) + bins.get("starter", 0)
                      for pos, bins in td.items()},
        "user_startable": user_startable,
        "startable_ok": startable_ok,
        "scoring_format": scoring_format,
    }


# ---------------------------------------------------------------------------
# FB-47 — finder targeting (flag: trade.finder_targeting)
# docs/plans/trade-finder-targeting.md
# ---------------------------------------------------------------------------


def _position_strength(profile: dict, pos: str) -> float:
    """0..1 — how loaded a roster is at `pos`, from an
    analyze_roster_strengths profile. 1.0 = at/above the surplus threshold,
    0.0 = no startable players at the position."""
    td = profile.get("tier_depth", {}).get(pos, {})
    starters = td.get("elite", 0) + td.get("starter", 0)
    return min(1.0, starters / max(_SURPLUS_AT.get(pos, 2), 1))


def partner_fit_score(
    opp_profile: dict,
    acquire_targets: list[str],
    sell_targets: list[str],
) -> Optional[float]:
    """Counterparty positional fit for the user's stated targets, 0..1.

    Acquiring at P → opponents LOADED at P score high (they can spare one).
    Selling at P   → opponents THIN at P score high (they want yours).
    Multiple targets average. None when the user expressed no targets —
    callers must treat None as "targeting inactive", not as fit 0.
    """
    parts: list[float] = []
    for pos in acquire_targets:
        if pos in _SURPLUS_AT:
            parts.append(_position_strength(opp_profile, pos))
    for pos in sell_targets:
        if pos in _SURPLUS_AT:
            parts.append(1.0 - _position_strength(opp_profile, pos))
    if not parts:
        return None
    return round(sum(parts) / len(parts), 3)


# ---------------------------------------------------------------------------
# FB-96 — automatic positional-need fit (flag: trade.need_fit)
# Feedback #96: "you're weak in RB but strong in WR — here's another team
# that needs the swap with you." Unlike FB-47's partner_fit (which needs
# user-stated targets), this scores EVERY card from the two rosters'
# positional profiles alone.
# ---------------------------------------------------------------------------


def need_fit_score(
    user_profile: dict,
    opp_profile: dict,
    give_ids: list[str],
    recv_ids: list[str],
    players: dict,
    scoring_format: str = "1qb_ppr",
) -> Optional[float]:
    """Per-card positional-need fit, 0..1 (0.5 = neutral).

    Each traded QB/RB/WR/TE contributes one term:
      given player at P    → high when the USER is loaded at P (surplus to
                             spend) and the OPPONENT is thin at P (fills
                             their need)
      received player at P → high when the USER is thin at P (fills the
                             user's need) and the OPPONENT is loaded at P
                             (they can spare one)
    Terms average. Strength is _position_strength over the PRE-trade
    profiles (same Tier-2 approximation the marginal path uses), except QB
    in superflex needs one extra startable body to count as "loaded"
    (starting 2 QBs means 2 startable QBs is zero surplus).

    Returns None when no traded asset has a positional profile (e.g. a
    picks-only side) — callers must treat None as "no signal", not 0.
    """
    def _strength(profile: dict, pos: str) -> float:
        td = profile.get("tier_depth", {}).get(pos, {})
        starters = td.get("elite", 0) + td.get("starter", 0)
        denom = _SURPLUS_AT.get(pos, 2)
        if pos == "QB" and scoring_format.startswith("sf"):
            denom += 1
        return min(1.0, starters / max(denom, 1))

    parts: list[float] = []
    for pid in give_ids:
        p = players.get(pid)
        pos = getattr(p, "position", None) if p else None
        if pos in _SURPLUS_AT:
            parts.append(0.5 * _strength(user_profile, pos)
                         + 0.5 * (1.0 - _strength(opp_profile, pos)))
    for pid in recv_ids:
        p = players.get(pid)
        pos = getattr(p, "position", None) if p else None
        if pos in _SURPLUS_AT:
            parts.append(0.5 * (1.0 - _strength(user_profile, pos))
                         + 0.5 * _strength(opp_profile, pos))
    if not parts:
        return None
    return round(sum(parts) / len(parts), 3)


# ---------------------------------------------------------------------------
# FB-147 engine hook — acquire-side trade-block boost (flag: trade.block_boost)
# The trade block (backend/trade_block_service.py) records which players each
# manager flagged "on the block" in Sleeper's Trade Center. A card that would
# have the user ACQUIRE such a player from the manager who flagged it is a more
# landable deal, so it earns a bounded post-gate composite bump. Loaded once
# per generation like the untouchable set; give-side / the user's own flagged
# players are out of scope (operator-approved acquire-side-only).
# ---------------------------------------------------------------------------


def _load_on_block_by_uid(league_id: str) -> dict[str, frozenset]:
    """League trade-block snapshot → {flagging_owner_user_id: frozenset(pids)}.

    Reads database.load_trade_block(league_id) and groups the flagged player
    ids by the manager who flagged them, so each card's acquire side is judged
    against the COUNTERPARTY's own block. Ownership was validated at sync time
    (stale flags dropped — see trade_block_service.parse_trade_block), so every
    id here is genuinely on that owner's block. Any read failure ⇒ empty map,
    so the boost silently no-ops rather than breaking generation.
    """
    try:
        from .database import load_trade_block
        rows = load_trade_block(league_id)
    except Exception:
        return {}
    by_uid: dict[str, set] = {}
    for r in rows:
        uid = str(r.get("user_id") or "")
        pid = str(r.get("player_id") or "")
        if uid and pid:
            by_uid.setdefault(uid, set()).add(pid)
    return {uid: frozenset(pids) for uid, pids in by_uid.items()}


# ---------------------------------------------------------------------------
# Tier 2 — work item 2.1: marginal (over-replacement) valuation
# (flag: trade.marginal_value — docs/plans/trade-engine-tier2-models.md)
# ---------------------------------------------------------------------------


def _starters_at(pos: str, scoring_format: str) -> int:
    """Starter slots for a position — _STARTER_NEED, QB bumped to 2 in SF."""
    n = _STARTER_NEED.get(pos, 0)
    if pos == "QB" and scoring_format.startswith("sf"):
        n = 2
    return n


def replacement_levels(
    roster_player_ids: list[str],
    value_of,                            # callable pid → value (one side's space)
    players: dict,
    scoring_format: str = "1qb_ppr",
) -> dict[str, float]:
    """
    Per-position replacement level for a roster:

        replacement(R, pos) = value of R's best player at pos NOT in the
                              starting lineup (the player who would start
                              if a starter left)

    Starters per position come from _STARTER_NEED (QB → 2 in superflex).
    If the position has fewer than starters+1 players the replacement is
    the waiver baseline (config waiver_baseline_value) — losing anyone
    there means dipping into waivers.

    Computed from the PRE-trade roster (Tier 2 approximation; exact
    post-trade lineup re-optimization is a Tier 3 ILP feature). Only
    QB/RB/WR/TE have a replacement concept — other positions are absent
    from the returned dict.
    """
    waiver = _c("waiver_baseline_value")
    by_pos: dict[str, list[float]] = {pos: [] for pos in _STARTER_NEED}
    for pid in roster_player_ids:
        p = players.get(pid)
        pos = getattr(p, "position", None) if p else None
        if pos in by_pos:
            by_pos[pos].append(value_of(pid))
    levels: dict[str, float] = {}
    for pos, vals in by_pos.items():
        starters = _starters_at(pos, scoring_format)
        if len(vals) < starters + 1:
            levels[pos] = waiver
        else:
            vals.sort(reverse=True)
            levels[pos] = vals[starters]
    return levels


def bench_credit_rate(pos: str | None, scoring_format: str = "1qb_ppr") -> float:
    """
    Position/format-aware bench credit (interview 2026-07-17): how much of
    a depth player's raw value survives the over-replacement collapse.

    RB/WR depth is near-startable insurance in every format (high rate);
    QB/TE depth is fungible in 1QB (low rate) but becomes startable
    capital in superflex (QB) / TE-premium (TE), where the override rates
    apply. Unknown positions fall back to the flat bench_credit_rate.
    """
    if pos == "QB":
        return _c("bench_credit_qb_sf") if scoring_format.startswith("sf") \
            else _c("bench_credit_qb")
    if pos == "TE":
        return _c("bench_credit_te_tep") if "tep" in scoring_format \
            else _c("bench_credit_te")
    if pos == "RB":
        return _c("bench_credit_rb")
    if pos == "WR":
        return _c("bench_credit_wr")
    return _c("bench_credit_rate")


def marginal_value(
    pid: str,
    value_of,                            # callable pid → value (same space)
    repl_levels: dict[str, float],       # from replacement_levels()
    players: dict,
    scoring_format: str = "1qb_ppr",
) -> float:
    """
    Value of a player OVER the roster's replacement at his position, plus
    a bench credit so depth keeps some worth (byes, injuries):

        marginal(p, R) = max(0, value(p) - replacement(R, pos(p)))
                         + bench_credit_rate(pos, format) * value(p)

    The bench credit is position/format-aware (see bench_credit_rate).
    Positions without a replacement concept (picks, unknown, anything
    outside QB/RB/WR/TE) keep their raw value.
    """
    v = value_of(pid)
    p = players.get(pid)
    pos = getattr(p, "position", None) if p else None
    if pos not in repl_levels:
        return v
    return (max(0.0, v - repl_levels[pos])
            + bench_credit_rate(pos, scoring_format) * v)


# ---------------------------------------------------------------------------
# Tier 2 — work item 2.2: outlook as now/future valuation blend
# (flag: trade.outlook_blend — replaces the deleted, never-wired
#  team_outlook_multiplier post-hoc multiplier)
# ---------------------------------------------------------------------------
# DESIGN CHOICE: the per-position age curves live here as a code constant
# table rather than ~30 model_config keys. The breakpoints and slopes were
# calibrated together as a set (DynastyProcess pattern: RB cliff ~26, WR
# plateau into ~29, QB ~flat into the 30s, TE late peak) and only make
# sense moving together; exposing each number individually would explode
# the config surface for no tuning benefit. The outlook → α map IS
# config-tunable (outlook_alpha_* keys) since it's a genuine product knob.
#
# Each entry maps age → multiplier, piecewise-linear with a floor.

_AGE_NOW_CURVE = {
    # win-now weight: peak-age production favored
    "QB": lambda a: 0.95 if a < 23 else 1.0,
    "RB": lambda a: (0.95 if a < 23 else
                     1.05 if a <= 26 else
                     max(0.60, 1.05 - 0.12 * (a - 26))),
    "WR": lambda a: (0.92 if a < 23 else
                     1.0 if a <= 29 else
                     max(0.65, 1.00 - 0.10 * (a - 29))),
    "TE": lambda a: (0.90 if a < 24 else
                     1.0 if a <= 31 else
                     max(0.70, 1.00 - 0.10 * (a - 31))),
}

_AGE_FUTURE_CURVE = {
    # youth-weighted mirror: long-horizon value favored
    "QB": lambda a: 1.05 if a <= 25 else max(0.70, 1.05 - 0.05 * (a - 25)),
    "RB": lambda a: 1.10 if a <= 23 else max(0.40, 1.10 - 0.12 * (a - 23)),
    "WR": lambda a: 1.10 if a <= 24 else max(0.50, 1.10 - 0.09 * (a - 24)),
    "TE": lambda a: 1.05 if a <= 25 else max(0.55, 1.05 - 0.08 * (a - 25)),
}


def age_now_mult(pos: str | None, age) -> float:
    """Win-now age multiplier. Unknown position or missing age → 1.0."""
    if not age or age <= 0:
        return 1.0
    fn = _AGE_NOW_CURVE.get(pos)
    return fn(age) if fn else 1.0


def age_future_mult(pos: str | None, age) -> float:
    """Future-value age multiplier. Unknown position or missing age → 1.0."""
    if not age or age <= 0:
        return 1.0
    fn = _AGE_FUTURE_CURVE.get(pos)
    return fn(age) if fn else 1.0


def age_pref_value(value: float, player) -> float:
    """Age-preference adjustment on a CONSENSUS value (2026-08-29 —
    see the _DEFAULT_CFG block for the evidence and knob semantics).

    u23 (age < 23) rides `age_pref_mult_u23` with the INCREASE capped at
    `age_pref_boost_cap` value points; 30plus (age >= 30) rides
    `age_pref_mult_30plus` uncapped (only increases are capped — the knob
    is "a maximum value increase", so a future >1.0 setting on either band
    is capped too). Ages 23–29, picks, and anything without a positive
    `age` attribute pass through untouched. A mult of exactly 1.0 returns
    the input unchanged (byte-identical — the arm-A pin relies on this).
    """
    age = getattr(player, "age", None) if player is not None else None
    if not age or age <= 0:
        return value
    if age < 23:
        mult = _c("age_pref_mult_u23")
    elif age >= 30:
        mult = _c("age_pref_mult_30plus")
    else:
        return value
    if mult == 1.0:
        return value
    adj = value * mult
    if adj > value:
        cap = _c("age_pref_boost_cap")
        if cap > 0:
            adj = min(adj, value + cap)
    return adj


_OUTLOOK_ALPHA_CFG_KEY = {
    "championship": "outlook_alpha_championship",
    "contender":    "outlook_alpha_contender",
    "not_sure":     "outlook_alpha_not_sure",
    "rebuilder":    "outlook_alpha_rebuilder",
    "jets":         "outlook_alpha_jets",
}


def outlook_alpha(outlook: str | None) -> float:
    """Blend weight α (1.0 = pure now-value, 0.0 = pure future-value).
    None / unknown outlooks fall back to the not_sure 50/50 blend."""
    key = _OUTLOOK_ALPHA_CFG_KEY.get(outlook or "not_sure",
                                     "outlook_alpha_not_sure")
    return _c(key)


def outlook_blend_mult(pos: str | None, age, alpha: float) -> float:
    """Combined now/future multiplier: α·now_mult + (1−α)·future_mult.
    Players with no age data get exactly 1.0 from both curves."""
    return (alpha * age_now_mult(pos, age)
            + (1.0 - alpha) * age_future_mult(pos, age))


# ---------------------------------------------------------------------------
# Interview phase 2 — two-lane deck (flag: trade.lanes)
# Window/age steer LABELS, not values ("age = tiebreak"): the classifier
# reuses the now/future age curves purely to describe what a trade does to
# roster composition, on consensus values, and never touches scoring.
# ---------------------------------------------------------------------------

_LANE_SIGN = {"championship": 1.0, "contender": 1.0,
              "rebuilder": -1.0, "jets": -1.0}


def _now_lean(pos: str | None, age) -> float:
    """How win-now an asset is, in [-,+]: positive = present production,
    negative = future capital. Picks are pure future capital; players with
    no age data are neutral."""
    if pos == "PICK":
        return -0.25
    if not age or age <= 0:
        return 0.0
    return age_now_mult(pos, age) - age_future_mult(pos, age)


def signed_lane_shift(give_ids: list[str], recv_ids: list[str], players: dict,
                      outlook: str | None, value_of) -> float | None:
    """The SIGNED lane shift: the value-weighted mean now-lean of what
    changes hands (received counts +, given counts −), signed by the user's
    window direction (contending: acquiring now-value = toward their window;
    rebuilding: acquiring future capital = toward their window).

    Positive = the card moves the roster TOWARD the user's window;
    negative = AWAY from it (the vet a rebuilder would be buying). The
    magnitude is comparable to lane_shift_frac in both directions.

    None when the shift is undefined: no declared/inferred window (None or
    not_sure), or no value on the table (nothing to take a mean over).

    value_of: pid → CONSENSUS value — the trade's shape, not either
    member's private board.
    """
    sign = _LANE_SIGN.get(outlook or "")
    if sign is None:
        return None
    shift = 0.0
    total = 0.0
    for direction, ids in ((1.0, recv_ids), (-1.0, give_ids)):
        for pid in ids:
            p = players.get(pid)
            v = value_of(pid)
            total += v
            shift += direction * v * _now_lean(
                getattr(p, "position", None) if p else None,
                getattr(p, "age", None) if p else None)
    if total <= 0:
        return None
    return sign * shift / total


def classify_lane(give_ids: list[str], recv_ids: list[str], players: dict,
                  outlook: str | None, value_of) -> str | None:
    """Label a card "window" or "value" for the two-lane deck.

    The lane shift is signed_lane_shift() above — the value-weighted mean now-lean
    of what changes hands, signed by the user's window direction. Clears
    lane_shift_frac → "window"; otherwise "value". No declared/inferred
    window (None or not_sure) → None: the deck has no lanes to show.

    Note the collapse this label makes, which fit-congruence weighting
    deliberately does NOT: "value" covers both window-NEUTRAL cards and
    strongly ANTI-window ones. Consumers that need that distinction read
    signed_lane_shift() directly (stamped as TradeCard.lane_shift).

    value_of: pid → CONSENSUS value — lanes describe the trade's shape,
    not either member's private board.
    """
    if _LANE_SIGN.get(outlook or "") is None:
        return None
    shift = signed_lane_shift(give_ids, recv_ids, players, outlook, value_of)
    if shift is None:               # no value on the table → nothing leaning
        return "value"
    return "window" if shift >= _c("lane_shift_frac") else "value"


def fit_congruence_mult(shift: float | None, decision: str) -> float:
    """K-factor multiplier for a deck swipe, weighted by how SURPRISING the
    action is given the user's window (the fit-congruence decision, D-060).

    A pass is not only a valuation statement. A rebuilder passing a
    fairly-priced vet is passing for a WINDOW reason, and the flat
    trade_k_pass discount is today's only acknowledgment that "don't want"
    ≠ "don't value". So: discount the action the window already explains,
    and keep full K on the action that defies it.

      shift ≥ +lane_shift_frac (card moves toward the user's window):
          like → fit-explained (they wanted their window) → explained mult
          pass → fit-DEFYING  (rejected a window-congruent card, so it is
                               a genuine value statement) → defying mult
      shift ≤ −lane_shift_frac (card moves away — the anti-window card):
          pass → fit-explained (the window predicted the pass) → explained
          like → fit-DEFYING  (the rebuilder who wants the vet ANYWAY —
                               the strongest board signal we get) → defying
      |shift| below the threshold, or shift is None (no window / not_sure
      / no value on the table) → exactly 1.0, byte-identical to pre-D-060.

    Kill switch: fit_k_explained_mult = 1.0 (with defying at its 1.0
    default) restores the old behavior exactly, deploy-free, via
    PUT /api/admin/config. There is no feature flag.
    """
    if shift is None:
        return 1.0
    if abs(shift) < _c("lane_shift_frac"):
        return 1.0
    congruent = shift > 0
    explained = (decision == "like") if congruent else (decision == "pass")
    return _c("fit_k_explained_mult") if explained else _c("fit_k_defying_mult")


# ---------------------------------------------------------------------------
# Feedback #175 — directional outlook weighting (flag: trade.outlook_direction)
# "A rebuilder should get back a younger player or a pick for the player
# they give away; rarely an older player (outside ~a 1-year gap)."
# ---------------------------------------------------------------------------

def _primary_asset(ids: list[str], players: dict, value_of):
    """(pid, player, consensus value) of the highest-value asset on a side.

    "Primary" is defined pragmatically as the single most valuable asset on
    the side — the piece the trade is ABOUT from that side's perspective.
    (Ties keep the first-listed asset; good enough for a steering heuristic.)
    """
    best_pid, best_v = None, float("-inf")
    for pid in ids:
        v = value_of(pid)
        if v > best_v:
            best_pid, best_v = pid, v
    return best_pid, players.get(best_pid), best_v


def outlook_direction_mult(give_ids: list[str], recv_ids: list[str],
                           players: dict, outlook: str | None,
                           value_of) -> float:
    """#175 — directional composite multiplier from the user's resolved
    outlook. Reuses the lane machinery: the shift is classify_lane's exact
    value-weighted mean now-lean of what changes hands (received +, given −),
    on CONSENSUS values (the card's shape, not either private board).

    Rebuild-side (rebuilder/jets):
      * shift > 0 (user acquiring win-now/older production) → strong
        penalty: max(0.05, 1 − outlook_dir_penalty·shift)
      * shift < 0 (acquiring future capital — younger players, picks; a
        PICK's now-lean is negative, so #170 pool picks compose naturally)
        → boost: 1 + outlook_dir_boost·(−shift)
      * the ~1-year-gap rule: primary give is a player, primary return is
        an OLDER player beyond outlook_dir_age_tolerance years, and no
        other return component is a pick or tolerance-younger player worth
        ≥ outlook_dir_rescue_frac of the primary give → composite further
        *= outlook_dir_age_gap_mult. Implemented as a large PENALTY, not a
        hard filter, so a genuinely lopsided-value win can still surface.

    Contend-side (championship/contender): ONLY the mild symmetric mirror
    1 + outlook_dir_contend_weight·shift — no age-gap rule (contenders
    legitimately buy older players).

    not_sure / None outlook → exactly 1.0 (no directional effect).
    """
    sign = _LANE_SIGN.get(outlook or "")
    if sign is None:
        return 1.0
    shift = 0.0
    total = 0.0
    for direction, ids in ((1.0, recv_ids), (-1.0, give_ids)):
        for pid in ids:
            p = players.get(pid)
            v = value_of(pid)
            total += v
            shift += direction * v * _now_lean(
                getattr(p, "position", None) if p else None,
                getattr(p, "age", None) if p else None)
    if total <= 0:
        return 1.0
    shift /= total

    if sign > 0:    # contend side — mild mirror only
        return max(0.0, 1.0 + _c("outlook_dir_contend_weight") * shift)

    # Rebuild side — directional scoring term…
    if shift > 0:
        mult = max(0.05, 1.0 - _c("outlook_dir_penalty") * shift)
    else:
        mult = 1.0 - _c("outlook_dir_boost") * shift

    # …plus the ~1-year-gap rule. Ages unknown on either primary, or a
    # pick primary on either side, ⇒ the rule can't judge and stays out.
    g_pid, g_p, g_v = _primary_asset(give_ids, players, value_of)
    r_pid, r_p, _r_v = _primary_asset(recv_ids, players, value_of)
    g_pos = getattr(g_p, "position", None) if g_p else None
    r_pos = getattr(r_p, "position", None) if r_p else None
    g_age = getattr(g_p, "age", None) if g_p else None
    r_age = getattr(r_p, "age", None) if r_p else None
    tol = _c("outlook_dir_age_tolerance")
    if (g_pos and g_pos != "PICK" and r_pos and r_pos != "PICK"
            and g_age and r_age and r_age > g_age + tol):
        rescue_floor = _c("outlook_dir_rescue_frac") * g_v
        rescued = False
        for pid in recv_ids:
            if pid == r_pid:
                continue    # the older primary can't rescue itself
            if value_of(pid) < rescue_floor:
                continue
            p = players.get(pid)
            pos = getattr(p, "position", None) if p else None
            age = getattr(p, "age", None) if p else None
            if pos == "PICK" or (age and age <= g_age + tol):
                rescued = True
                break
        if not rescued:
            mult *= _c("outlook_dir_age_gap_mult")
    return mult


def aggression_variant(user_id: str) -> str:
    """Interview phase 2 (flag trade.aggression_ab) — stable opening-offer
    bucket per user: "light" (open a touch light, room to add), "fair"
    (balanced offers lead), "generous" (optimize acceptance rate). MD5 so
    the bucket is deterministic across processes and restarts."""
    h = int(hashlib.md5(user_id.encode("utf-8")).hexdigest(), 16)
    return ("light", "fair", "generous")[h % 3]


def fit_premium_1for1(
    give_ids: list[str],
    recv_ids: list[str],
    raw_user_elo: dict[str, float] | None,
    players: dict,
    user_needs: set | None,
) -> tuple[bool, float | None]:
    """Interview phase 2 (flag trade.fit_premium) — the honest exception
    to the #108 raw-board gate: a 1-for-1 the user LOSES a little raw
    value on is allowed when it fills a positional need from a non-need
    spot, and the card is flagged with the price paid.

    Returns (allowed, value_paid): (True, None) when the plain #108 gate
    passes (no premium), (True, loss) for a flagged fit-premium card,
    (False, None) when the combo stays blocked. Never rescues losses
    beyond fit_premium_max_loss — "a little value" only.
    """
    if user_gain_ok_1for1(give_ids, recv_ids, raw_user_elo):
        return True, None
    if not FLAGS.trade_fit_premium or not user_needs:
        return False, None
    # The #108 gate only fails on known 1-for-1s, so shapes are 1x1 here.
    give_p = players.get(give_ids[0])
    recv_p = players.get(recv_ids[0])
    give_pos = getattr(give_p, "position", None) if give_p else None
    recv_pos = getattr(recv_p, "position", None) if recv_p else None
    if recv_pos not in user_needs or give_pos in user_needs:
        return False, None
    loss = (elo_to_value(raw_user_elo[give_ids[0]])
            - elo_to_value(raw_user_elo[recv_ids[0]]))
    if loss > _c("fit_premium_max_loss"):
        return False, None
    return True, round(loss, 1)


def first_round_signal(ledger: dict | None) -> dict:
    """#365 — turn a raw first-round-pick ledger into the scoring term's
    inputs. Pure, and ALWAYS fully shaped: every key is present in every
    branch, so no client ever has to distinguish "missing" from "zero".

    `ledger` is the four counts a caller derived from `draft_picks` for ONE
    member, plus one league-wide fact:

        held         round-1 picks this member currently owns
        own_total    round-1 picks ORIGINALLY this member's (the baseline)
        traded_away  originally theirs, now someone else's
        acquired     theirs now, originally someone else's
        league_any_traded  any round-1 pick ANYWHERE in the league whose
                     current owner differs from its original owner

    `net = acquired − traded_away` is exactly the operator's ask — *"number of
    1sts owned vs traded away"* — because `held − own_total` reduces to it:
    both sides share the "own firsts retained" count, which cancels.

    THE LAST INPUT IS THE HONESTY GATE, and it is why this is not a one-liner.
    A league whose pick history predates capture shows `original_user_id ==
    owner_user_id` on every row and therefore reads as "nobody has traded
    anything" — indistinguishable, from inside this function, from a league
    where nobody has. So `league_any_traded` gates the term: when nothing in
    the league is recorded as having moved we refuse to score the member's
    zero, and `provenance` says which of the three worlds we are in
    (`observed` / `none_traded` / `absent`) so the card can state it rather
    than render a confident 0. Operator ruling, 2026-08-20: degrade honestly
    and say so on the card.
    """
    out = {
        "held": 0, "own_total": 0, "traded_away": 0, "acquired": 0,
        "net": 0, "net_share": 0.0,
        "provenance": "absent", "applied": False,
    }
    if not ledger:
        return out
    out["held"]        = int(ledger.get("held") or 0)
    out["own_total"]   = int(ledger.get("own_total") or 0)
    out["traded_away"] = int(ledger.get("traded_away") or 0)
    out["acquired"]    = int(ledger.get("acquired") or 0)
    out["net"]         = out["acquired"] - out["traded_away"]

    if out["own_total"] <= 0 and out["held"] <= 0:
        return out                                  # provenance stays "absent"
    if not ledger.get("league_any_traded"):
        out["provenance"] = "none_traded"
        return out

    out["provenance"] = "observed"
    cap = abs(_c("infer_net_firsts_cap"))
    raw = out["net"] / max(out["own_total"], 1)
    out["net_share"] = round(max(-cap, min(cap, raw)), 4)
    out["applied"] = bool(FLAGS.trade_outlook_net_firsts)
    return out


def starter_value_signal(
    starter_value: float | None,
    league_starter_value: float | None,
    num_teams: int,
) -> dict:
    """#372 — "we calculate starter dynasty value. Let's incorporate that."

    Turns the caller's value-optimal STARTING lineup into a league-relative
    index. Pure: the caller sums the values (they come straight off
    `power_rankings.compute_power_rankings`, whose `starters` list is the
    value-optimal fill and whose `roster` rows carry the per-player value),
    this function only relates them and reports its own confidence.

        share = your starters' value / the league's starters' value
        index = share · num_teams − 1

    `index` is `share − 1/num_teams` rescaled by `num_teams`, which is the
    same centring convention `pick_share` uses — but expressed so that the
    number does NOT depend on league size. 0.0 is an exactly average starting
    lineup; +0.30 is 30 % above the league mean. That independence is why the
    weight can be one constant instead of one per league shape.

    WHY STARTERS AND NOT ROSTER VALUE. Total roster value is already the
    standing beat's number and it rewards hoarding: a rebuilder sitting on
    nine young WR4s can out-total a contender. A team is strong WHERE IT
    STARTS, which is precisely the axis the age model cannot see — and #372 is
    a report that the age model called an all-in roster a rebuild.

    DEGRADES BY NAMING THE REASON (same rule as `first_round_signal`, D-110):

      observed        a lineup template was known and the league has priced
                      starter value — the term counts
      lineup_unknown  `starters` is None: the platform exposes no
                      roster_positions equivalent and the meta fetch found no
                      template (`server._league_lineup_slots` returns None
                      rather than guess one). We did not look
      absent          a template existed but the league's total starter value
                      is zero — an unsynced or demo league. Nothing to relate

    `applied` is the ONLY correct test of whether the term entered the score.
    Never derive it from `index == 0`: a perfectly average team and a team we
    could not read both index at 0 and they are different claims.
    """
    out = {
        "starter_value": 0.0, "league_starter_value": 0.0,
        "share": 0.0, "index": 0.0, "index_raw": 0.0,
        "provenance": "lineup_unknown", "applied": False,
    }
    if starter_value is None or league_starter_value is None:
        return out
    lg = float(league_starter_value)
    out["starter_value"] = round(float(starter_value), 1)
    out["league_starter_value"] = round(lg, 1)
    if lg <= 0:
        out["provenance"] = "absent"
        return out
    out["provenance"] = "observed"
    share = float(starter_value) / lg
    cap = abs(_c("infer_composite_starter_cap"))
    raw = share * max(int(num_teams), 1) - 1.0
    out["share"] = round(share, 4)
    # BOTH the scored value and the measured one. The cap binds on real
    # rosters — the FFV3 caller in the report measures +0.82 and is scored at
    # +0.50 — and a card that printed only `index` would tell him his starters
    # are 50 % above average when they are 82 % above. `index` is what entered
    # the score and `index_raw` is what was observed; the card shows the
    # measurement and names the cap when the two differ.
    out["index_raw"] = round(raw, 4)
    out["index"] = round(max(-cap, min(cap, raw)), 4)
    out["applied"] = bool(FLAGS.trade_outlook_composite)
    return out


def playoff_odds_signal(odds: dict | None, refusal: str | None) -> dict:
    """#372 — "incorporate … playoff likelihood", as a TERM rather than as the
    replacement `trades.window_from_odds` (#371/D-111) makes it.

    `odds` is the band block `team_review.resolve_window_from_odds` returns —
    `{band, playoff_pct, implied}` — and `refusal` is that function's own
    reason string, or None when it admitted the odds. This function does not
    re-derive the admission rule, it INHERITS it: the odds engine is
    Sleeper-only (`backend/outlook/league_state.py` stubs every other
    platform) and is refused in preseason (D-094: `completed_weeks == 0` is
    its weakest window), and those two rulings must not exist twice.

        index = clamp(2 · (playoff_pct − centre), ± cap)

    with `centre` the midpoint of the `tossup` band. +0.30 at the `likely`
    boundary, −0.30 at the `unlikely` boundary, ±1.00 at certainty.

    Provenance is the refusal string when there is one, so the card can say
    "your odds read likely, but nobody has played a game" rather than showing
    a term worth nothing:

      observed          the band was admitted — the term counts
      preseason         a band exists and was deliberately not used
      odds_unavailable  no band: non-Sleeper, `outlook.odds` off, or the
                        simulator failed
      odds_disabled     `trades.window_from_odds` is off, so we never asked

    A refused term is ABSENT FROM THE SCORE, never a zero standing in for
    "neutral" — the operator's degrade-honestly ruling (D-110).
    """
    out = {
        "playoff_pct": None, "band": None, "index": 0.0,
        "center": _c("infer_composite_playoff_center"),
        "provenance": refusal or "odds_unavailable", "applied": False,
    }
    if not odds:
        return out
    out["band"] = odds.get("band")
    pct = odds.get("playoff_pct")
    if pct is not None:
        out["playoff_pct"] = round(float(pct), 4)
    if refusal is not None or pct is None:
        return out
    centre = float(out["center"])
    cap = abs(_c("infer_composite_playoff_cap"))
    # ×2 so the index reaches ±1.00 at 0 % / 100 %, which makes `cap` a
    # meaningful knob rather than a bound the data can never approach.
    raw = 2.0 * (float(pct) - centre)
    out["index"] = round(max(-cap, min(cap, raw)), 4)
    out["provenance"] = "observed"
    out["applied"] = bool(FLAGS.trade_outlook_composite)
    return out


def infer_team_outlook(
    roster_ids: list[str],
    players: dict,
    pick_share: float = 0.0,
    num_teams: int = 12,
    first_round_ledger: dict | None = None,
    starter_signal: dict | None = None,
    odds_signal: dict | None = None,
) -> tuple[str, float, dict]:
    """Infer a team's contend↔rebuild window from observable roster shape
    (backlog #1). Pure function: no DB, no I/O — feeds the same
    `outlook_alpha` blend the user side already uses.

    Signals (all consensus-based via `dynasty_value`, so stable across users):
      • vet value share   — fraction of roster value held by players aged ≥ vet_age
      • youth value share — fraction held by players aged ≤ youth_age
      • pick capital share — this team's draft-pick value / league total, centred
                             on an equal split (1/num_teams) so an average pick
                             holder contributes 0
      • net first-round capital (#365, flag `trade.outlook_net_firsts`) —
        firsts acquired minus firsts traded away, over the firsts originally
        yours. Only present when a caller supplies `first_round_ledger`.
      • starter-value index + playoff index (#372, flag
        `trade.outlook_composite`) — see below. Only present when a caller
        supplies `starter_signal`.

    Score (higher = more contending)
        = w_vet·vet − w_youth·youth − w_pick·(pick − equal) − w_firsts·net_share.
    Buckets into contender / not_sure / rebuilder. The extreme labels
    (championship / jets) are deliberately NOT inferred — inference confidence
    rarely justifies α = 1.00 / 0.10; those stay reserved for self-declaration.

    #365 — TWO INVARIANTS THIS FUNCTION OWES THE REST OF THE APP.
    Its verdict is not a Team Review number: it feeds `outlook_alpha`, which
    the engine (`trade_gen_v2.py:986`, `trade_service.py:4250`), the mock draft
    (`server.py:14013`) and the outlook seed (`server.py:5320`) all consume.
    Changing the score changes every deck for every user. So:

      INV-365   flag OFF ⇒ `first_round_ledger` is accepted and IGNORED. The
                returned tuple — outlook, score, and every key of `signals` —
                equals what this function returned before #365, for every
                caller, even one that passes a ledger. That is why the two new
                `model` keys are added INSIDE the flag branch: `model` is
                rendered on screen, so an unconditional key would advertise a
                term that is not being applied.
      INV-365b  flag ON but no ledger ⇒ the score is STILL unchanged. Only the
                Team Review route builds a ledger today, so lighting the flag
                moves the window beat and not one deck. Wiring the other three
                callers is a separate change with its own evidence.

    #372 — THE COMPOSITE (flag `trade.outlook_composite`). Operator, third
    report on this surface: "The logic is still too simple… age distribution
    alone is not a strong enough of a signal. We calculate starter dynasty
    value. Let's incorporate that and playoff likelihood. The age distribution
    can stay but make it a lighter driver."

    This is ONE RE-WEIGHTED SCORE, not a fourth bolt-on term. When the
    composite is live the whole vector changes at once:

        vet      1.00 → 0.40      the "lighter driver"
        youth    1.00 → 0.40
        pick     2.00 → 2.00      unchanged; pick capital is not age
        starter    —  → 0.60      NEW, capped ±0.50
        playoff    —  → 0.40      NEW, capped ±1.00, absent in preseason
        firsts   0.10 → 0.10      unchanged, still its own flag

    The two age terms stay ADJACENT-THRESHOLD siblings (vet_age 27,
    youth_age 26 — every aged player is one or the other), which is exactly
    why halving both rather than dropping one is the honest edit: they are
    close to one rescaled quantity, so the pair's total influence is what
    #372 asked to reduce, and it drops by 60 %.

    THE SAME TWO INVARIANTS, EXTENDED — and they are what keep every deck
    where it is:

      INV-372   flag OFF ⇒ `starter_signal` / `odds_signal` are accepted and
                IGNORED, and neither the score nor any key of `signals`
                moves. Byte-identical to origin/main for every caller.
      INV-372b  flag ON but no APPLIED starter signal ⇒ the LEGACY vector
                still scores. The composite's anchor is starter value, and a
                re-weighting that halves age without putting anything in its
                place is not a model, it is a quieter model. So the engine,
                the mock draft and the outlook seed — none of which pass a
                starter signal — are untouched even with the flag lit. Only
                GET /api/league/team-review supplies one.

    DEGRADES PER SIGNAL, NOT ALL-OR-NOTHING. `odds_signal` may be refused
    (preseason, non-Sleeper, `trades.window_from_odds` off) while the starter
    term still scores; both signal blocks ride `signals` with their
    provenance either way, so the card names what is missing instead of
    scoring an absent term as a neutral zero.

    Returns (outlook, score, signals).
    """
    vet_age   = _c("vet_age")
    youth_age = _c("youth_age")
    total = 0.0
    vet_val = 0.0
    youth_val = 0.0
    for pid in roster_ids:
        p = players.get(pid)
        if p is None:
            continue
        v = dynasty_value(p)
        total += v
        age = getattr(p, "age", None)
        if age is None:
            continue
        if age >= vet_age:
            vet_val += v
        elif age <= youth_age:
            youth_val += v

    # #365 — SHIP THE MODEL, NOT JUST ITS OUTPUT. The Team Review window beat
    # renders every input this function reads, and a client that hardcodes one
    # of them drifts silently the day a knob moves: the shipped screen read
    # "Value age 23 and under" while `youth_age` has been 26, so the threshold
    # the user was shown was never the threshold the inference applied. Same
    # rule as `equal_pick_share` in team_review._window — a client reads an
    # encoding, it never restates one. Additive: existing callers that only
    # read the share keys are untouched.
    model = {
        "vet_age":       vet_age,
        "youth_age":     youth_age,
        "w_vet_share":   _c("infer_w_vet_share"),
        "w_youth_share": _c("infer_w_youth_share"),
        "w_pick_share":  _c("infer_w_pick_share"),
        "contender_cut": _c("infer_contender_cut"),
        "rebuilder_cut": _c("infer_rebuilder_cut"),
    }
    signals = {"vet_share": 0.0, "youth_share": 0.0, "pick_share": pick_share,
               "model": model}

    # #365 — the net-firsts term. Gated on the flag AND on a ledger actually
    # being supplied (INV-365 / INV-365b above). `firsts` and the two extra
    # `model` keys ride the payload ONLY inside this branch, so a flag-off
    # caller's `signals` dict is key-for-key what it was before #365.
    firsts = None
    if FLAGS.trade_outlook_net_firsts and first_round_ledger is not None:
        firsts = first_round_signal(first_round_ledger)
        signals["firsts"] = firsts
        model["w_net_firsts"]   = _c("infer_w_net_firsts")
        model["net_firsts_cap"] = _c("infer_net_firsts_cap")

    # #372 — the composite's two signal blocks. Gated on the flag AND on the
    # caller supplying a starter signal, exactly as #365 gated on a ledger
    # (INV-372 / INV-372b above). `composite` decides which WEIGHT VECTOR the
    # score below uses, so it is resolved before the score and not after.
    starters_sig = None
    playoff_sig = None
    composite = False
    if FLAGS.trade_outlook_composite and starter_signal is not None:
        starters_sig = dict(starter_signal)
        signals["starters"] = starters_sig
        composite = bool(starters_sig.get("applied"))
        if odds_signal is not None:
            playoff_sig = dict(odds_signal)
            signals["playoff"] = playoff_sig
        if composite:
            # D-101 — SHIP THE MODEL YOU ACTUALLY RAN. These two keys already
            # exist and are RE-STATED at their composite values, because the
            # card renders `w_vet_share × vet_share` as an arithmetic row: a
            # model block still reading 1.00 while the score used 0.40 is the
            # same defect as "age 23 and under" against a youth_age of 26.
            model["w_vet_share"]   = _c("infer_composite_w_vet")
            model["w_youth_share"] = _c("infer_composite_w_youth")
            model["w_pick_share"]  = _c("infer_composite_w_pick")
            model["w_starter_index"]  = _c("infer_composite_w_starter")
            model["starter_index_cap"] = _c("infer_composite_starter_cap")
            model["composite"] = True
            # The playoff weight rides ONLY when the term actually scores, so
            # the card can never print a weight beside a refused signal.
            if playoff_sig is not None and playoff_sig.get("applied"):
                model["w_playoff_index"]   = _c("infer_composite_w_playoff")
                model["playoff_center"]    = _c("infer_composite_playoff_center")
                model["playoff_index_cap"] = _c("infer_composite_playoff_cap")

    # No roster value to read ⇒ no opinion. Guard before the pick-centering
    # term, which would otherwise read "owns zero picks" as a contend signal.
    # The firsts term is suppressed here too: a team with no readable roster
    # has no window, and half a model is not an opinion. Same for the two
    # composite terms — a team whose roster we cannot price has no starting
    # lineup worth relating to the league's either.
    if total <= 0:
        if firsts is not None:
            firsts["applied"] = False
        if starters_sig is not None:
            starters_sig["applied"] = False
        if playoff_sig is not None:
            playoff_sig["applied"] = False
        signals["score"] = 0.0
        return "not_sure", 0.0, signals
    signals["vet_share"]   = vet_val / total
    signals["youth_share"] = youth_val / total

    equal_share = 1.0 / max(num_teams, 1)
    if composite:
        # #372 — ONE re-weighted score. Age keeps both signals at 40 % of the
        # weight it had; starter value and (when the season has started and
        # the league is Sleeper) playoff likelihood carry the difference.
        score = (
            _c("infer_composite_w_vet")     * signals["vet_share"]
            - _c("infer_composite_w_youth") * signals["youth_share"]
            - _c("infer_composite_w_pick")  * (pick_share - equal_share)
            + _c("infer_composite_w_starter") * float(starters_sig["index"])
        )
        # Sign convention differs from the pick terms deliberately: a BETTER
        # starting lineup and BETTER playoff odds both read as contending, so
        # both ADD, while accumulating pick capital reads as rebuilding and
        # subtracts.
        if playoff_sig is not None and playoff_sig.get("applied"):
            score += _c("infer_composite_w_playoff") * float(playoff_sig["index"])
    else:
        score = (
            _c("infer_w_vet_share")   * signals["vet_share"]
            - _c("infer_w_youth_share") * signals["youth_share"]
            - _c("infer_w_pick_share")  * (pick_share - equal_share)
        )
    # Same sign convention as the pick-capital term above: ACCUMULATING pick
    # capital reads as rebuilding, so a positive net (more firsts acquired
    # than shipped) subtracts, and a manager who has sold his firsts gains.
    if firsts is not None and firsts["applied"]:
        score -= _c("infer_w_net_firsts") * firsts["net_share"]
    signals["score"] = score

    if score >= _c("infer_contender_cut"):
        outlook = "contender"
    elif score <= _c("infer_rebuilder_cut"):
        outlook = "rebuilder"
    else:
        outlook = "not_sure"
    return outlook, score, signals


def build_match_context(
    user_profile: dict,
    opponent_profile: dict,
    scoring_format: str,
    is_dynasty: bool = False,
) -> dict:
    """
    Produce the structured 'why this match' object that ships on each
    TradeCard. Pure function; deterministic.
    """
    user_needs       = user_profile.get("position_needs", [])
    opp_surplus      = opponent_profile.get("position_surplus", [])
    overlap          = [p for p in user_needs if p in opp_surplus]

    if overlap:
        rationale = f"You're thin at {overlap[0]}; opponent is {overlap[0]}-heavy."
    elif user_needs:
        rationale = f"You're thin at {user_needs[0]} — see if any reach across."
    else:
        rationale = "Roster profiles align without a single standout gap."

    # Both supported formats (1qb_ppr, sf_tep) are PPR. Treat anything not
    # explicitly marked standard/std as PPR by default.
    fmt_lower = scoring_format.lower()
    is_standard = "standard" in fmt_lower or "_std" in fmt_lower or fmt_lower == "std"
    return {
        "user_needs":       user_needs,
        "opponent_surplus": opp_surplus,
        "league_settings":  {
            "scoring":     "standard" if is_standard else "ppr",
            "superflex":   fmt_lower.startswith("sf"),
            "te_premium":  "tep" in fmt_lower,
            "dynasty":     is_dynasty,
        },
        "positional_rationale": rationale,
    }


# ---------------------------------------------------------------------------
# Agent A8 — trade-math adjustments (behind feature flags)
# ---------------------------------------------------------------------------
# These functions compute multiplicative adjustments to the composite score
# and, when the human_explanations flag is on, append a plain-English reason
# to the supplied `reasons` list.  All adjustments are ADDITIVE — each flag
# that is on contributes independently and stacks multiplicatively.
#
# Signatures follow a consistent pattern:
#   (give_ids, recv_ids, *context, reasons: list[str]) -> float multiplier
# where 1.0 means "no adjustment".
#
# The caller passes the same `reasons` list to each function.  If
# human_explanations is off the caller simply drops the list at the end
# rather than paying per-function branches.
# ---------------------------------------------------------------------------

# "Premium QB" ELO lower bound per the QB Tax spec: any QB at or above
# 1600 qualifies (an engine threshold, independent of the user-facing
# pick-value tier ladder; 1600 sits inside the first_1 band).
_QB_PREMIUM_ELO = 1600.0


def _position_of(pid: str, player_db: dict) -> Optional[str]:
    p = player_db.get(pid)
    if not p:
        return None
    return getattr(p, "position", None)


def _seed_of(pid: str, seed_elo: dict[str, float]) -> float:
    return seed_elo.get(pid, 1500.0)


def qb_tax_adjustment(
    give_ids: list[str],
    recv_ids: list[str],
    seed_elo: dict[str, float],
    player_db: dict,
    reasons: list[str],
) -> float:
    """
    Feature: trade_math.qb_tax.

    When one side of the trade RECEIVES a premium QB (seed ELO >=
    _QB_PREMIUM_ELO) without GIVING one back, apply a penalty to that
    side — i.e. the side that is handing over a premium QB is effectively
    getting short-changed, so the composite score drops.

    The penalty symmetrically models both directions:
      * If user receives a premium QB and opponent does not → user's
        side is advantaged; we actually want to discount the composite
        because the opp would likely refuse. So the composite drops.
      * If user gives a premium QB without getting one back → user is
        disadvantaged; composite drops.
    Either direction shaves the configured rate off the composite.

    Returns a multiplier in (0, 1].
    """
    if not FLAGS.trade_math_qb_tax:
        return 1.0

    rate = _c("qb_tax_rate")

    def _premium_qbs(ids: list[str]) -> list[str]:
        out = []
        for pid in ids:
            if _position_of(pid, player_db) != "QB":
                continue
            if _seed_of(pid, seed_elo) >= _QB_PREMIUM_ELO:
                out.append(pid)
        return out

    user_recv_qbs = _premium_qbs(recv_ids)   # user receives these
    user_give_qbs = _premium_qbs(give_ids)   # user gives these

    multiplier = 1.0
    # Team 1 (user) receives a premium QB without giving one back.
    if user_recv_qbs and not user_give_qbs:
        multiplier *= (1.0 - rate)
        if FLAGS.trade_math_human_explanations:
            reasons.append(
                f"⚠️ QB tax: Team 1 receives a premium QB without giving one back (−{rate*100:.1f}%)"
            )
    # Team 2 (opponent) receives a premium QB without giving one back
    # (from user's perspective: user gives a QB without getting one).
    if user_give_qbs and not user_recv_qbs:
        multiplier *= (1.0 - rate)
        if FLAGS.trade_math_human_explanations:
            reasons.append(
                f"⚠️ QB tax: Team 2 receives a premium QB without giving one back (−{rate*100:.1f}%)"
            )
    return multiplier


def star_tax_adjustment(
    give_ids: list[str],
    recv_ids: list[str],
    seed_elo: dict[str, float],
    player_db: dict,
    scoring_format: str,
    reasons: list[str],
) -> float:
    """
    Feature: trade_math.star_tax.

    Compare the TOP asset on each side (highest seed ELO).  If they sit
    more than one tier apart, apply `star_tax_per_tier_gap` per extra
    tier step to the side RECEIVING the lower-tier package.  When the
    higher-tier star is Tier 1 (top of the ladder), multiply the penalty
    by `star_tax_elite_multiplier` — trading away a top-shelf star is
    extra costly.

    Tiers from RankingService.tier_for_elo, ordered by ORDERED_TIERS
    (pick-value ladder, top→bottom):
      firsts_4plus (0) → firsts_3 (1) → firsts_2 (2) → first_1 (3) →
      second (4) → third (5) → fourth (6) → waivers (7) → unranked (8)
    Gap = |give_tier_idx - recv_tier_idx|. (The 8-tier ladder, #117, has
    finer rungs than the pre-2026-07-12 six — the same value distance now
    spans more tier steps, so star-tax penalties bite sooner.)
    """
    if not FLAGS.trade_math_star_tax:
        return 1.0

    try:
        from .ranking_service import ORDERED_TIERS, RankingService
    except Exception:
        return 1.0

    tier_order = ORDERED_TIERS

    def _top_tier_idx(ids: list[str]) -> tuple[int, Optional[str], Optional[str]]:
        """Return (tier_index, tier_name, pid) of the highest-ELO asset."""
        best_idx = 99
        best_name: Optional[str] = None
        best_pid: Optional[str] = None
        for pid in ids:
            elo = _seed_of(pid, seed_elo)
            pos = _position_of(pid, player_db)
            tier = RankingService.tier_for_elo(elo, pos, scoring_format)
            if tier is None:
                idx = len(tier_order)  # unranked sinks below bench
            else:
                idx = tier_order.index(tier)
            if idx < best_idx:
                best_idx = idx
                best_name = tier
                best_pid = pid
        return best_idx, best_name, best_pid

    give_idx, give_tier, _give_pid = _top_tier_idx(give_ids)
    recv_idx, recv_tier, _recv_pid = _top_tier_idx(recv_ids)

    gap = abs(give_idx - recv_idx)
    if gap <= 1:
        return 1.0

    per_gap  = _c("star_tax_per_tier_gap")
    elite_m  = _c("star_tax_elite_multiplier")
    extra    = gap - 1  # only count gaps BEYOND 1

    # Side receiving the lower tier (higher idx) eats the penalty.
    # Equivalently: the side trading away the higher tier is over-paying.
    # We apply the penalty to the composite (which represents user utility
    # regardless of side). Elite bump applies when the HIGHER-tier side
    # is Tier 1.
    higher_is_elite = (min(give_idx, recv_idx) == 0)
    penalty = per_gap * extra
    if higher_is_elite:
        penalty *= elite_m

    multiplier = max(0.0, 1.0 - penalty)

    if FLAGS.trade_math_human_explanations:
        if give_idx < recv_idx:
            # User trades away the better star
            side_label = "Team 1 trades away"
            tier_label = give_tier or "unranked"
        else:
            side_label = "Team 2 trades away"
            tier_label = recv_tier or "unranked"
        _tier_display = {
            "firsts_4plus": "4+ 1sts", "firsts_3": "3 1sts",
            "firsts_2": "2 1sts", "first_1": "1 1st", "second": "2nd",
            "third": "3rd", "fourth": "4th", "waivers": "FA",
        }
        tier_tag = ("Tier 1" if higher_is_elite
                    else _tier_display.get(tier_label, tier_label.capitalize()))
        reasons.append(
            f"⭐ Star tax: {side_label} a {tier_tag} star (−{penalty*100:.1f}%)"
        )
    return multiplier


def roster_clogger_adjustment(
    give_ids: list[str],
    recv_ids: list[str],
    reasons: list[str],
) -> float:
    """
    Feature: trade_math.roster_clogger.

    Penalise asymmetric-size trades.
    * roster_spot_penalty per extra roster spot used
    * Plus an ADDITIONAL roster_clogger_penalty per player beyond 2 for
      a "clogger" trade (>= roster_clogger_threshold players one-way).
    """
    if not FLAGS.trade_math_roster_clogger:
        return 1.0

    n_give = len(give_ids)
    n_recv = len(recv_ids)
    diff   = abs(n_give - n_recv)
    if diff <= 0:
        return 1.0

    spot_rate    = _c("roster_spot_penalty")
    clogger_rate = _c("roster_clogger_penalty")
    threshold    = int(_c("roster_clogger_threshold"))

    multiplier = 1.0
    penalty_total = spot_rate * diff

    # Clogger: the bigger side has >= threshold players.
    bigger = max(n_give, n_recv)
    if bigger >= threshold:
        # Each player beyond 2 in the bigger side adds clogger_rate
        extra_players = bigger - 2
        penalty_total += clogger_rate * extra_players

    multiplier = max(0.0, 1.0 - penalty_total)

    if FLAGS.trade_math_human_explanations:
        # Label the side doing the "clogging" — the side giving up more
        # players. From user POV: n_give > n_recv means user gives more.
        if n_give > n_recv:
            side_label = "Team 1 gives up"
            count_label = f"{n_give} players for {n_recv}"
        else:
            side_label = "Team 2 gives up"
            count_label = f"{n_recv} players for {n_give}"
        if bigger >= threshold:
            reasons.append(
                f"📦 Roster clogger: {side_label} {count_label} (−{penalty_total*100:.1f}%)"
            )
        else:
            reasons.append(
                f"📦 Roster spots: {side_label} {count_label} (−{penalty_total*100:.1f}%)"
            )
    return multiplier


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

@dataclass
class LeagueMember:
    user_id: str
    username: str
    roster: list[str]                   # list of player IDs on this user's team
    elo_ratings: dict[str, float]       # { player_id: personal_elo }
    # True only when this member has REAL saved rankings (member_rankings rows).
    # The v2 engine refuses to run divergence math against fabricated/seeded
    # elo_ratings — unranked members get consensus-basis cards instead.
    has_rankings: bool = False


@dataclass
class TradeCard:
    trade_id: str
    league_id: str
    proposing_user_id: str              # the logged-in user
    target_user_id: str                 # the other party
    target_username: str
    give_player_ids: list[str]          # what the logged-in user gives
    receive_player_ids: list[str]       # what the logged-in user receives
    mismatch_score: float               # higher = more compelling trade
    fairness_score: float               # 0–1, higher = more balanced
    composite_score: float              # final sort key
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    expires_at: str = field(default_factory=lambda: (
        datetime.now(timezone.utc) + timedelta(days=7)).isoformat())
    decision: Optional[str] = None      # None | "like" | "pass"
    # Agent A8 — human-readable trade adjustment explanations.
    # Populated only when trade-math flags are on. Empty list means no
    # adjustment-level reasons for this trade. The server view converts
    # an empty list to an omitted JSON key when human_explanations is off.
    reasons: list[str] = field(default_factory=list)
    # Feature 2 — structured roster-aware match context, computed from
    # analyze_roster_strengths() / build_match_context(). None when not yet wired.
    match_context: Optional[dict] = None
    # Feature 1 — templated, deterministic plain-English narrative (≤2 sentences).
    narrative: Optional[str] = None
    # Trade engine v2 — how this card was generated:
    #   "divergence"  — built on real valuation disagreement between the two
    #                   members' personal rankings (the core product signal)
    #   "consensus"   — fallback card vs an opponent with no rankings; built
    #                   purely from consensus (seed) values + roster fit
    basis: str = "divergence"
    # Tier 2 (2.3a) — True when the counterparty already liked the mirror of
    # this trade (flag trade.likes_you). Serialized only when true.
    likes_you: bool = False
    # Tier 3 (3.4) — when a low-value player was added to balance an
    # otherwise-unfair trade: {"player_id": str, "side": "give"|"receive"}.
    # The player is already included in that side's id list. None otherwise.
    sweetener: Optional[dict] = None
    # 2026-08-21 gap auto-sweetener (`sweetener_gap_threshold`) — set when a
    # card's absolute consensus gap exceeded the threshold and an equalizer
    # asset from the richer side's roster closed it: {"player_id": str,
    # "side": "give"|"receive", "gap_before": float, "gap_after": float}.
    # The player is already included in that side's id list. Distinct from
    # `sweetener` (the 3.4 fairness-band rescue) so measurement can split
    # them; also stamped into features_json on EVERY impression row (null
    # when absent). None otherwise.
    gap_sweetener: Optional[dict] = None
    # FB-47 (flag trade.finder_targeting) — counterparty positional fit for
    # the user's stated targets, 0..1 (1 = ideal partner). None when the
    # flag is off or the user expressed no targets. Serialized when set.
    partner_fit: Optional[float] = None
    # FB-96 (flag trade.need_fit) — automatic positional-need fit, 0..1
    # (1 = gives from the user's surplus into the opponent's need AND
    # receives at the user's need from the opponent's surplus). None when
    # the flag is off or no traded asset has a positional profile.
    # Serialized when set.
    need_fit: Optional[float] = None
    # Consensus roster-fit sort key (`consensus_fit_weight`, 2026-09-02) —
    # mean normalised fit of the card's traded assets, -1..1 (+ = every
    # asset moves to the lineup where it is worth more). Stamped by
    # `_generate_consensus_for_pair` ONLY while the knob is > 0, so the
    # knob-0 card is byte-identical. In-process/QA record only: never
    # serialized to clients and not yet in features_json (follow-up).
    consensus_fit: Optional[float] = None
    # FB-147 engine hook (flag trade.block_boost) — True when this card's
    # ACQUIRE side holds a player the counterparty flagged "on the block",
    # earning the bounded post-gate composite bump. In-process/QA record only;
    # client inspectability rides the existing per-player `on_block` receive-row
    # flag (#147), so no separate serialization is added (never duplicated).
    block_boosted: bool = False
    # #175 (flag trade.outlook_direction) — the directional composite
    # multiplier this card received from the user's resolved outlook
    # (rebuild-side: future-capital returns boosted, win-now returns
    # penalized, unrescued older-primary returns near-excluded; contend-side
    # mild mirror). In-process/QA record only, never serialized. None when
    # the flag is off, the outlook has no direction (not_sure/None), or the
    # multiplier came out exactly 1.0.
    outlook_dir: Optional[float] = None
    # Interview phase 2 (flag trade.lanes) — "window" | "value" | None:
    # which deck lane the card belongs to, from the user's resolved
    # window (declared or seeded). None = user has no window → no lanes.
    lane: Optional[str] = None
    # Fit-congruence (D-060) — the SIGNED lane shift (signed_lane_shift()) from the
    # user's resolved window: + = toward their window, − = away from it.
    # Stamped at construction, unconditionally (no flag), because the swipe
    # site cannot recompute it: it has no resolved outlook and no consensus
    # value fn. `lane` cannot stand in — its "value" bucket collapses
    # window-NEUTRAL and strongly ANTI-window cards, and the anti-window
    # swipe is exactly the signal fit-congruence weights hardest.
    # In-process/QA record only, never serialized to clients. None when the
    # user has no window direction (not_sure/None), no value was on the
    # table, or the card was rebuilt from client echo (FB-46) — all of
    # which weight at exactly 1.0.
    lane_shift: Optional[float] = None
    # Interview phase 2 (flag trade.fit_premium) — set on a 1-for-1 that
    # fills a positional need at a small raw-board value loss:
    # {"value_paid": float, "position": str}. Honest flag, never silent.
    fit_premium: Optional[dict] = None
    # Interview phase 2 (flag trade.aggression_ab) — the user's stable
    # opening-offer bucket ("light" | "fair" | "generous") that reweighted
    # this deck. Serialized for event joins; not user-facing copy.
    aggression_variant: Optional[str] = None
    # Consensus package values (value space, elo_to_value over the seed) for
    # the give / receive sides — the SAME numbers the manual calculator shows.
    # Populated at construction from each path's consensus value fn; drive the
    # pick-denominated TradeValueBar on the deck cards (trade_card_to_dict
    # builds favors/gap from these via _value_verdict_payload). None on cards
    # reconstructed from client echo (no package math available) — the client
    # gates the bar on their presence.
    give_value: Optional[float] = None
    receive_value: Optional[float] = None
    # #189 — set on cards produced by the relaxed fallback pass (a targeted
    # job that yielded zero cards under normal gates). Additive: normal cards
    # never carry these; clients label relaxed cards ("Stretch idea — outside
    # your usual fairness band"). relaxed_reason ∈
    # {"fairness_band", "fairness_band+surplus_floor"} — which stage emitted.
    relaxed: bool = False
    relaxed_reason: Optional[str] = None
    # trade_gen.v2 (backend/trade_gen_v2.py) — additive fields only that
    # pipeline stamps; every other path leaves them None so flag-off
    # payloads stay byte-identical.
    #   rationale     — structured two-sided rationale: {"user": {...},
    #                   "counterparty": {...}} — each side's gain in its
    #                   OWN board's terms + why the counterparty plausibly
    #                   says yes. Never a single winner score.
    #   meso_variants — up to 3 return-package variants for the pair's top
    #                   card, ≈equivalent on the RECIPIENT's board,
    #                   different in shape: [{shape, give_player_ids,
    #                   recipient_value_delta_pct}].
    #   health        — per-suggestion health metrics (joint_gain,
    #                   split_ratio, IR margins, band_position, …).
    #                   In-process/log record only, never serialized.
    #   tier          — "endorsed" (the cycle's single best mutual pick,
    #                   at most 1) | "featured" (next gen2_featured_count
    #                   by rank) | "browse" (every remaining survivor,
    #                   still ranked). Scarcity lives HERE, not in list
    #                   length (operator decision 2026-08-16).
    rationale: Optional[dict] = None
    meso_variants: Optional[list] = None
    health: Optional[dict] = None
    tier: Optional[str] = None
    # #362 (flag trade.standing_offers) — "Why you're seeing this" line for a
    # card produced by a league-mate's standing offer. Server-composed;
    # serialized only when set. Carries NO team ids and NO counts (R-19).
    standing_offer_reason: Optional[str] = None
    # #362 — {"round": int, "seasons": [int]} when one of the DECK OWNER's own
    # live standing offers covers this card. Display only; never reorders,
    # never boosts, never filters.
    standing_offer_mine: Optional[dict] = None


@dataclass
class League:
    league_id: str
    name: str
    platform: str                       # "sleeper" | "espn" | "yahoo" | "demo"
    members: list[LeagueMember]


# ---------------------------------------------------------------------------
# #172 — trade intent modes (flag trades.intent_modes)
# ---------------------------------------------------------------------------
# The user declares the SHAPE of trade they want off the deck and the finder
# respects it. Semantics are grounded in the pick-value tier ladder
# (RankingService.tier_for_elo / ORDERED_TIERS, best→worst) via each side's
# BEST (highest-tier) asset — the same "top asset per side" comparison
# star_tax_adjustment already makes.
#
#   consolidate — user sends MORE pieces than they receive, AND the best
#                 incoming asset is a genuine quality upgrade (strictly
#                 better tier than the best outgoing asset).
#   tier_up     — best incoming asset's tier is strictly better than the
#                 best outgoing asset's tier. Piece counts don't matter.
#   tier_down   — inverse of consolidate: user receives MORE pieces than
#                 they send (trading their best piece away for a package),
#                 AND the best outgoing asset is strictly better tier than
#                 the best incoming asset.
#
# None/unknown intent is a no-op (every card kept) — the historical,
# byte-identical default.

def _best_tier_idx(
    ids: list[str],
    seed_elo: dict[str, float],
    player_db: dict,
    scoring_format: str,
) -> int:
    """Index into ORDERED_TIERS of the BEST (lowest-index) tier among
    `ids`, via each asset's seed ELO. Unranked/empty sinks to
    len(ORDERED_TIERS) — below every real tier — mirroring
    star_tax_adjustment's _top_tier_idx."""
    from .ranking_service import ORDERED_TIERS, RankingService
    best = len(ORDERED_TIERS)
    for pid in ids:
        elo = _seed_of(pid, seed_elo)
        pos = _position_of(pid, player_db)
        t = RankingService.tier_for_elo(elo, pos, scoring_format)
        idx = ORDERED_TIERS.index(t) if t is not None else len(ORDERED_TIERS)
        if idx < best:
            best = idx
    return best


def _filter_by_trade_intent(
    cards: list[TradeCard],
    intent: str | None,
    seed_elo: dict[str, float],
    player_db: dict,
    scoring_format: str,
) -> list[TradeCard]:
    """#172 post-generation filter over an already-generated card list.
    `intent` must already be flag-resolved by the caller (None when the
    flag `trades.intent_modes` is off) — this function trusts it, so it
    stays a pure filter with no flag lookups of its own."""
    if not intent:
        return cards

    def _keep(c: TradeCard) -> bool:
        give_idx = _best_tier_idx(c.give_player_ids, seed_elo, player_db, scoring_format)
        recv_idx = _best_tier_idx(c.receive_player_ids, seed_elo, player_db, scoring_format)
        upgrade   = recv_idx < give_idx   # lower ORDERED_TIERS index = better tier
        downgrade = give_idx < recv_idx
        n_give = len(c.give_player_ids)
        n_recv = len(c.receive_player_ids)
        if intent == "consolidate":
            return n_give > n_recv and upgrade
        if intent == "tier_up":
            return upgrade
        if intent == "tier_down":
            return n_recv > n_give and downgrade
        return True   # unknown value — no-op, never a silent empty deck

    return [c for c in cards if _keep(c)]


# ---------------------------------------------------------------------------
# Trade Service
# ---------------------------------------------------------------------------

class TradeService:
    """
    Generates and manages trade cards for a user across their leagues.

    In production, league + member data comes from the League Service
    (Sleeper API etc.). For the demo, leagues are simulated.
    """

    def __init__(self, players: dict, past_decision_keys: set | None = None,
                 dismissed_keys: set | None = None):
        """
        players: { player_id: Player } — full player pool
        past_decision_keys: set of (frozenset(give_ids), frozenset(receive_ids))
            from past trade decisions — used to filter out already-swiped trades.
        dismissed_keys: the DISMISS ("pass") subset of past_decision_keys,
            same key derivation, D-067 windowed (pass_cooldown_days) — the
            only decisions that exclude on the asset-ideas sweep (#402 rev-3
            QA-B F2: a like is a queued proposal, never a suppression there).
            The caller shares ONE set object across formats so the swipe
            route's in-memory bind reaches every service.
        """
        self._players     = players
        self._trade_cards: dict[str, TradeCard] = {}    # trade_id → TradeCard
        self._leagues:     dict[str, League]    = {}    # league_id → League
        self._past_decision_keys = past_decision_keys or set()
        self._dismissed_decision_keys = (dismissed_keys
                                         if dismissed_keys is not None else set())
        # G6 presentment rules (flag trade.presentment_rules) — per-job
        # state, reset by every _generate_trades_impl call:
        #   _exclusion_keys — R4 #336 windowless awaiting/matched exclusion
        #     set, OVERWRITTEN per call (league-scoped per job; the service
        #     serves multiple leagues, so carry-over would false-exclude
        #     identical asset sets cross-league — round-1 N3).
        #   _presentment_kills — per-rule candidate-kill counters (R-9).
        #   _r4_excluded_keys — distinct keys R4 actually filtered (dedup
        #     across streaming-snapshot re-filters + the likes-you injector).
        self._exclusion_keys: set = set()
        self._presentment_kills: dict[str, int] = {
            "R1": 0, "R2": 0, "R3": 0, "R5": 0}
        self._r4_excluded_keys: set = set()
        #   _standing_offer_cap_drops / _organic_like_cap_drops — #362 R-15:
        #     likes-you candidates dropped for want of a cap slot. COUNTERS,
        #     never analytics events — one event per dropped card in a chatty
        #     league is high-cardinality server noise for a question a
        #     counter answers. Reset per job alongside _r4_excluded_keys.
        self._standing_offer_cap_drops: int = 0
        self._organic_like_cap_drops: int = 0
        #   _job_seed_elo — the consensus Elo map of the CURRENT job, so
        #     _dedup_and_sort can derive each card's centerpiece for the C4
        #     headliner cap. Overwritten per call like _exclusion_keys; while
        #     it is empty the cap is inert, because with no consensus values
        #     every asset ties and "centerpiece" would mean nothing.
        self._job_seed_elo: dict = {}

    # ------------------------------------------------------------------
    # League management
    # ------------------------------------------------------------------

    def add_league(self, league: League):
        self._leagues[league.league_id] = league

    # ------------------------------------------------------------------
    # Trade generation
    # ------------------------------------------------------------------

    def generate_trades(self, *args, **kwargs):
        """#215 — resolve the requesting user's stud-tax mode once per job
        and pin it (thread-local) for every package_value_v2 call this
        generation makes, then delegate to _generate_trades_impl. An
        already-pinned mode (tests) wins over the stored setting."""
        user_id = kwargs.get("user_id", args[0] if args else None)
        mode = pinned_stud_tax_mode() or stud_tax_mode_for_user(user_id)
        with stud_tax_override(mode):
            return self._generate_trades_impl(*args, **kwargs)

    def _generate_trades_impl(
        self,
        user_id: str,
        user_elo: dict[str, float],          # { player_id: elo } — logged-in user
        user_roster: list[str],              # player IDs on user's team
        league_id: str,
        seed_elo: dict[str, float],          # consensus elo for fairness checks
        max_per_opponent: int = 5,
        fairness_threshold: float = 0.75,    # min package_value ratio (0.5–1.0)
        acquire_positions: list[str] | None = None,    # positions user wants to receive
        trade_away_positions: list[str] | None = None, # positions user wants to give
        avoid_positions: list[str] | None = None,      # #360: never receive these
                                                       # positions — receive-pool
                                                       # exclusion, never relaxed
        pinned_give_players: list[str] | None = None,  # specific players user wants to trade away
        pinned_receive_players: list[str] | None = None,  # specific players user wants to acquire
                                                          # (FB-47; v2-only, legacy ignores it)
        pinned_give_mode: str = "any",       # #174: "any" (historical, give side
                                             # must include ≥1 pinned) or "all"
                                             # (give side must include EVERY
                                             # pinned player — "trade this
                                             # package away"). v2-only, legacy
                                             # ignores it like pinned_receive.
        opponent_user_id: str | None = None,  # #156 Specific Team: scope the
                                              # sweep to this one league-mate
        scoring_format: str = "1qb_ppr",
        is_dynasty: bool = False,
        on_opponent_done = None,             # callback(idx_done, total, sorted_cards_so_far)
        confidence: dict[str, int] | None = None,  # pid → comparison count for the
                                                   # requesting user (v2 shrinkage; A4 ranges)
        placements: dict[str, tuple[float, float]] | None = None,
                                             # D-085: pid → (lo, hi) Elo band of
                                             # the tier the user PLACED him in
                                             # (RankingService.placement_bands).
                                             # Clamps the shrunk personal Elo;
                                             # every gate is untouched.
        outlook: str | None = None,          # championship | contender | not_sure |
                                             # rebuilder | jets | None — Tier 2 (2.2)
                                             # now/future blend; v2-only, legacy ignores it
        opponent_outlooks: dict[str, str] | None = None,    # uid → declared outlook (#1)
        opponent_pick_shares: dict[str, float] | None = None,  # uid → pick-capital share (#1)
        untouchable_ids: set | None = None,    # never trade these away (#2)
        target_ids: set | None = None,         # bias toward acquiring these (#2)
        not_interested_ids: set | None = None, # never offer these TO the user (#163)
        trade_intent: str | None = None,       # #172 (flag trades.intent_modes):
                                                # "consolidate" | "tier_up" |
                                                # "tier_down" | None — post-
                                                # generation shape filter
        bypass_need_gate: bool = False,        # G6 R-5b: True on TARGETED jobs
                                               # (pinned give/receive, opponent
                                               # scope, explicit acquire) —
                                               # derived SERVER-SIDE in
                                               # _run_trade_job, never from the
                                               # request body. Skips R5 only;
                                               # R1/R2/R3/R4 always apply.
        exclusion_keys: set | None = None,     # G6 R4 #336: windowless
                                               # awaiting/matched (frozenset
                                               # give, frozenset receive) keys
                                               # for THIS league. Overwrites the
                                               # stored set every call; None ⇒
                                               # empty set, never keep-previous.
        negmem=None,                           # trade.negmem — the job's
                                               # negmem.NegmemMap (LLD §2.1).
                                               # Travels ONLY as this kwarg:
                                               # deliberately NO self._negmem
                                               # slot, so a concurrent
                                               # same-session job has nothing
                                               # to overwrite (H-4; stronger
                                               # than the _exclusion_keys
                                               # overwrite-per-call precedent
                                               # it was modelled on). None (the
                                               # default, and the value on every
                                               # flag-off / non-allowlisted job)
                                               # ⇒ every seam short-circuits
                                               # before any arithmetic and the
                                               # deck is byte-identical (C1).
    ) -> list[TradeCard]:
        """
        Generate trade cards for the user against all league members
        who have established rankings.

        fairness_threshold: minimum ratio of lesser/greater KTC package value.
          0.75 (default) = packages must be within 25% of each other.
          1.00 = perfectly balanced packages only.
          0.50 = allow up to 2× imbalance.

        acquire_positions / trade_away_positions: soft multipliers applied after
          scoring — trades that match these preferences bubble up in the list.

        pinned_give_players: when set, only generate trades where the user's
          give side includes at least one of these player IDs.  This lets
          users say "I want to trade away X" and see what comes back.

        Returns new cards (not already in trade_cards).
        """
        league = self._leagues.get(league_id)
        if not league:
            raise ValueError(f"Unknown league: {league_id!r}")

        # G6 R4 — overwrite-per-call semantics (round-1 N3): the kwarg
        # REPLACES the stored set on every call; None ⇒ empty set, never
        # "keep previous". Kill counters reset per job alongside it.
        self._exclusion_keys = set(exclusion_keys) if exclusion_keys else set()
        # trade.negmem — read the kwarg ONCE into a call-local (LLD §6.2).
        # Same overwrite-per-call semantics as _exclusion_keys above, except
        # there is no instance slot at all: `_nm` dies with this call, so no
        # later call can inherit a previous job's map. Every downstream site
        # reads `_nm`, never the kwarg name, so there is exactly one read.
        _nm = negmem
        self._job_seed_elo = seed_elo or {}      # C4 centerpiece derivation
        self._presentment_kills = {"R1": 0, "R2": 0, "R3": 0, "R5": 0}
        self._r4_excluded_keys = set()
        self._standing_offer_cap_drops = 0        # #362 R-15
        self._organic_like_cap_drops = 0          # #362 R-15

        # #172 — resolve the flag once so both paths below share one check;
        # off ⇒ trade_intent is never read, so flag-off responses stay
        # byte-identical to today regardless of what the caller passed.
        _intent = trade_intent if FLAGS.trades_intent_modes else None

        # trade_gen.v2 — matchmaking-research staged pipeline (backend/
        # trade_gen_v2.py). Ships DARK alongside the v2/v3 engine: flag off
        # (the default) ⇒ this branch is never taken, the module is never
        # imported, and every existing path below is byte-identical.
        # Divergence-only by design — unranked opponents are served by the
        # flag-off engine's consensus path, not by this one.
        if FLAGS.trade_gen_v2:
            from .trade_gen_v2 import generate_league_suggestions
            cards, _gen2_report = generate_league_suggestions(
                players=self._players,
                league=league,
                user_id=user_id,
                user_elo=user_elo,
                user_roster=user_roster,
                seed_elo=seed_elo,
                confidence=confidence,
                placements=placements,
                # Operator decision 2026-08-16 — no engine truncation: the
                # pipeline returns the FULL ranked survivor set; scarcity
                # rides the per-card `tier` field, and any deck-size
                # limits are downstream presentation concerns
                # (_order_deck / _cap_per_target), never engine defaults.
                # The route's max_per_opponent is deliberately NOT
                # forwarded.
                max_per_opponent=None,
                scoring_format=scoring_format,
                untouchable_ids=untouchable_ids,
                target_ids=target_ids,
                not_interested_ids=not_interested_ids,
                opponent_user_id=opponent_user_id,
                opponent_outlooks=opponent_outlooks,
                opponent_pick_shares=opponent_pick_shares,
                # G6 R4 rides the shared past_decision_keys kwarg (lld §1
                # generator-scope amendment): gen-v2 gets the windowless
                # #336 exclusion automatically; the R1/R2/R3/R5 hooks are
                # v1-path only — gen-v2 carries its own gate stack.
                past_decision_keys=(
                    self._past_decision_keys if r4_bypassed()
                    else self._past_decision_keys | self._exclusion_keys),
                # trade.negmem (LLD §6.3) — M1 map + the M2 feed. Which one
                # is conditional matters: `negmem_map` is passed
                # UNCONDITIONALLY (a plain kwarg carrying None when negmem is
                # off; the seam guards on `is not None`, never on the kwarg's
                # presence), while `acceptance_stats` is added ONLY when a map
                # exists — that splat is what keeps the flag-off call
                # byte-identical (C1). Do not tidy the two into one form.
                # m2_feed() returns {} on a degraded map and {} when
                # gen2_accept_prior_strength ≤ 0 (the sanctioned M2 kill).
                negmem_map=_nm,
                **({"acceptance_stats": _nm.m2_feed()}
                   if _nm is not None else {}),
                on_opponent_done=on_opponent_done,
            )
            cards = _filter_by_trade_intent(cards, _intent, seed_elo,
                                            self._players, scoring_format)
            # C4b — this branch returns WITHOUT calling _dedup_and_sort, so it
            # would otherwise be the one serving path with no give-side cap.
            # gen-v2 returns its own ranked survivor set, so the list is
            # already best-first and the cap keeps each headliner's best cards
            # exactly as it does on the v1/v3 path. (Arm C of the bake-off
            # bypasses this method entirely — bakeoff_runner.gen_v2_cards
            # applies the same call for the same reason.)
            cards = cap_give_headliners(cards, seed_elo, self._players,
                                        int(_c("deck_give_headliner_cap")))
            for card in cards:
                self._trade_cards[card.trade_id] = card
            return cards

        # Trade engine v2 — entirely separate scoring path so the legacy
        # branch below stays byte-for-byte identical when the flag is off.
        if FLAGS.trade_engine_v2:
            _v2_kwargs = dict(
                user_id              = user_id,
                user_elo             = user_elo,
                user_roster          = user_roster,
                league               = league,
                league_id            = league_id,
                seed_elo             = seed_elo,
                max_per_opponent     = max_per_opponent,
                fairness_threshold   = fairness_threshold,
                acquire_positions    = acquire_positions,
                trade_away_positions = trade_away_positions,
                avoid_positions      = avoid_positions,          # #360
                pinned_give_players  = pinned_give_players,
                pinned_receive_players = pinned_receive_players,
                pinned_give_mode     = pinned_give_mode,
                opponent_user_id     = opponent_user_id,
                scoring_format       = scoring_format,
                is_dynasty           = is_dynasty,
                on_opponent_done     = on_opponent_done,
                confidence           = confidence,
                placements           = placements,
                outlook              = outlook,
                opponent_outlooks    = opponent_outlooks,
                opponent_pick_shares = opponent_pick_shares,
                untouchable_ids      = untouchable_ids,
                target_ids           = target_ids,
                not_interested_ids   = not_interested_ids,
                bypass_need_gate     = bypass_need_gate,
                # trade.negmem — ONE key, in the ONE dict (LLD §6.2). This
                # dict is both splatted into _generate_trades_v2 below and
                # handed whole to _relaxed_targeted_pass, so the relaxed
                # re-run consults the SAME map at the same _c-read strength
                # with zero special-casing — and there is no duplicate-keyword
                # hazard because there is only ever one assignment.
                negmem_map           = _nm,
            )
            cards = self._generate_trades_v2(**_v2_kwargs)
            # #189 — a targeted job (pinned players and/or acquire /
            # trade-away positions) should always present SOMETHING when
            # anything defensible exists: rerun with staged, labeled gate
            # relaxation only when the normal pass came up empty. Normal
            # jobs and non-empty results are byte-identical.
            targeted = bool(pinned_give_players or pinned_receive_players
                            or acquire_positions or trade_away_positions
                            or avoid_positions)
            if targeted and not cards:
                cards = self._relaxed_targeted_pass(_v2_kwargs)
            # #172 — pure post-generation filter, applied last so it never
            # interferes with the #189 relaxed retry above.
            cards = _filter_by_trade_intent(cards, _intent, seed_elo, self._players, scoring_format)
            return cards

        new_cards: list[TradeCard] = []

        # Pre-compute the user's roster profile once.
        user_profile = analyze_roster_strengths(user_roster, self._players, scoring_format)

        # Build the list of eligible opponents up-front so the callback can
        # report a stable "X of N" without surprises when members get filtered.
        eligible = [
            m for m in league.members
            if m.user_id != user_id and m.elo_ratings
        ]
        # #156 Specific Team — scope to a single league-mate when requested.
        if opponent_user_id:
            eligible = [m for m in eligible if m.user_id == opponent_user_id]
        total = len(eligible)

        # Once we've collected enough cards across all opponents, further
        # scanning rarely surfaces a card good enough to crack the top of
        # the deck. The cap has to be loose enough that productive leagues
        # don't truncate too early — we saw 7-of-10 opponents yielding 6
        # cards trip the cap when set to 15, leaving 4 opponents unsampled.
        # Bumping to 30 lets the typical 11-opponent league complete its
        # full sweep in nearly all real cases (since the per-opponent yield
        # is usually 1-2 cards) while still bounding pathological cases.
        # Cold leagues (returning 0 cards across 11 opponents) still
        # complete in one full pass — the cap never trips, but the
        # per-opponent deadline reduction is what saves them.
        global_target = max(30, max_per_opponent * 6)
        # trade.full_sweep — the wall-clock rail's origin. Taken here in both
        # paths so the flag-off branch below is unchanged in every other way;
        # one `monotonic()` per job, never read unless the flag is on.
        _sweep_t0 = time.monotonic()

        for idx, member in enumerate(eligible):
            opp_profile = analyze_roster_strengths(member.roster, self._players, scoring_format)
            match_ctx = build_match_context(user_profile, opp_profile, scoring_format, is_dynasty)

            cards = self._generate_for_pair(
                user_id              = user_id,
                user_elo             = user_elo,
                user_roster          = user_roster,
                opponent             = member,
                league_id            = league_id,
                seed_elo             = seed_elo,
                max_cards            = max_per_opponent,
                fairness_threshold   = fairness_threshold,
                acquire_positions    = acquire_positions or [],
                trade_away_positions = trade_away_positions or [],
                pinned_give_players  = pinned_give_players,
            )
            for c in cards:
                c.match_context = match_ctx
                c.narrative = build_narrative(c, match_ctx, self._players)
            new_cards.extend(cards)

            # Streaming hook — let callers (e.g. /api/trades/generate's
            # background worker) snapshot a sorted, dedup-aware view as
            # cards land. The list is sorted descending by composite_score
            # so the snapshot already represents "best so far". Errors from
            # the callback are isolated; we never let a UI bug crash the
            # generator.
            if on_opponent_done is not None:
                try:
                    snapshot = self._dedup_and_sort(new_cards)
                    on_opponent_done(idx + 1, total, snapshot)
                except Exception:
                    pass  # callback issues must not derail the loop

            # Global early exit: enough cards collected, stop scanning more
            # opponents. Always lets the LAST opponent's results land first
            # (the "snapshot" above already includes them).
            #
            # trade.full_sweep (docs/plans/full-sweep/plan.md §3.2) — ON, the
            # card-count exit is skipped so every eligible leaguemate is
            # scored and `_dedup_and_sort` below ranks the whole league;
            # `global_target` is still computed, and OFF the first branch is
            # today's behaviour exactly (the second short-circuits away).
            _over_target = len(new_cards) >= global_target
            if not FLAGS.trade_full_sweep and _over_target:
                break
            # …and ON, the count no longer bounds the job, so a wall-clock
            # rail does instead (§3.5): the v3 pair path has no deadline of
            # its own, and `_JOB_HARD_TIMEOUT` at 60s is not a ceiling anyone
            # should be relying on. Checked between opponents; <= 0 disables.
            if FLAGS.trade_full_sweep and _c("full_sweep_budget_s") > 0 \
                    and time.monotonic() - _sweep_t0 > _c("full_sweep_budget_s"):
                break

        # Filter out trades the user has already swiped on (within memory window)
        # and dedup, then sort by composite score
        new_cards = self._dedup_and_sort(new_cards)

        # #172 — pure post-generation filter (see the flag-off note at the
        # top of this method). Applied before storage: a filtered-out card
        # was never surfaced to this job's caller.
        new_cards = _filter_by_trade_intent(new_cards, _intent, seed_elo, self._players, scoring_format)

        # Store
        for card in new_cards:
            self._trade_cards[card.trade_id] = card

        return new_cards

    def _dedup_and_sort(self, cards: list[TradeCard]) -> list[TradeCard]:
        """Apply past-decision filter (skip trades the user already swiped on)
        and the G6 R4 #336 windowless awaiting/matched exclusion, then return
        cards sorted by composite_score descending. Pulled out of the main
        loop so it can be called both incrementally (snapshot for progress
        callback — which is what makes R4 bind on streaming snapshots too)
        and at the end of generation."""
        # Bake-off arm A runs with R4 off (no knob exists — see r4_bypass()).
        # Thread-local, so arms B/C and every other job still enforce it.
        _r4_keys = frozenset() if r4_bypassed() else self._exclusion_keys
        if self._past_decision_keys or _r4_keys:
            kept: list[TradeCard] = []
            for c in cards:
                key = (frozenset(c.give_player_ids),
                       frozenset(c.receive_player_ids))
                if key in self._past_decision_keys:
                    continue
                if key in _r4_keys:
                    # Distinct-key accounting: snapshots re-filter the same
                    # accumulating list, so a set (not a counter) keeps the
                    # R4 kill count honest.
                    self._r4_excluded_keys.add(key)
                    continue
                kept.append(c)
            cards = kept
        cards = sorted(cards, key=lambda c: c.composite_score, reverse=True)
        # C4 (2026-08-18, docs/plans/engine-quality/scope.md) — headliner
        # diversity. Dedup here is EXACT-KEY only, and `mismatch` is largest
        # for whichever asset diverges most between the two boards, so that
        # one asset generates many distinct high-scoring packages and every
        # one of them survives: Colston Loveland appeared in 18 of 18 cards of
        # one live deck. That makes a single valuation error catastrophic
        # instead of survivable — mismatch is LARGEST exactly where a
        # valuation is most wrong. Cap how many cards may share a centerpiece.
        #
        # Applied AFTER the composite sort, so each headliner keeps its BEST
        # cards, and at deck assembly rather than inside one opponent's
        # enumeration, so it constrains the FINAL served set (streaming
        # snapshots re-derive it from the same accumulating list, exactly like
        # the R4 exclusion above). 0 disables — byte-identical to pre-C4.
        # An empty job seed map carries no consensus information, so every
        # asset ties at the 1500 default and `centerpiece` degenerates to
        # "largest player id" — a cap on that would drop cards for no reason.
        # No seed map ⇒ no cap. (The real entry point always sets one.)
        cap = int(_c("deck_headliner_cap"))
        if cap > 0 and self._job_seed_elo:
            seen_heads: dict[str, int] = {}
            capped: list[TradeCard] = []
            for c in cards:
                head = deck_centerpiece(c.give_player_ids,
                                        c.receive_player_ids,
                                        self._job_seed_elo)
                if head is not None:
                    if seen_heads.get(head, 0) >= cap:
                        continue
                    seen_heads[head] = seen_heads.get(head, 0) + 1
                capped.append(c)
            cards = capped
        # C4b (2026-08-19) — GIVE-side headliner cap, alongside C4 rather than
        # instead of it. C4 keys on `deck_centerpiece`, which maxes over give
        # AND receive; a card that gives one player for one draft pick is
        # therefore keyed on the PICK, and since every such card offers a
        # different pick slot every card gets a unique key and C4 never fires.
        # Measured on the live deck that prompted this (job 2740a7fc, 22
        # cards): 20 distinct centerpieces, C4 dropped nothing, and three
        # players supplied 17 of the 22 GIVE sides — 6/6/5. D-079's per-round
        # pick decay made it worse by lifting every 1st to ~1650, so picks now
        # out-Elo more players and headline more often.
        #
        # Same placement discipline as C4: after the composite sort (each
        # headliner keeps its best cards) and at deck assembly (bounds the
        # FINAL served set; streaming snapshots re-derive it from the same
        # accumulating list). Leave-short — a dropped card is never backfilled.
        # 0 disables, byte-identical to pre-C4b.
        cards = cap_give_headliners(cards, self._job_seed_elo, self._players,
                                    int(_c("deck_give_headliner_cap")))
        return cards

    def presentment_kill_counts(self) -> dict[str, int]:
        """G6 R-9 — per-rule kill counters for the current/most recent job.
        R1/R2/R3/R5 count candidate kills at the construction hooks; R4 is
        the count of DISTINCT excluded keys actually filtered (dedup sites
        + the likes-you injector, which appends to _r4_excluded_keys)."""
        counts = dict(self._presentment_kills)
        counts["R4"] = len(self._r4_excluded_keys)
        return counts

    # ------------------------------------------------------------------
    # #189 — relaxed fallback for empty targeted sweeps
    # ------------------------------------------------------------------

    def _relaxed_targeted_pass(self, v2_kwargs: dict) -> list[TradeCard]:
        """Staged re-run of the v2 path after a targeted job yielded zero
        cards. Stages, in order (first stage that yields cards wins):

          1. "fairness_band" — widen the consensus fairness band: the
             effective threshold drops to relaxed_fairness_threshold (both
             the caller's threshold and the divergence floor), never
             TIGHTENING below what the caller asked for.
          2. "fairness_band+surplus_floor" — additionally drop the weakest
             non-safety gate: the both-sides surplus minimums fall to
             relaxed_surplus_floor (default 0.0 — mutual gain must still be
             non-negative on both boards).

        NEVER relaxed: the #108 user-board gates (user_gain_epsilon,
        fit_premium_1for1 / user_gain_ok_1for1), untouchable_ids,
        avoid_positions (#360 — structurally un-relaxable: the exclusion
        lives in receive-POOL CONSTRUCTION, not in a gate, and this pass
        re-runs _generate_trades_v2 with the SAME kwargs, so there is
        nothing here that could relax it. Do not move the filter into a
        gate — that is what would silently break the guarantee), and the
        G6 presentment rules — construction rules R1 #340 / R2 #341 /
        R3 #339 AND the R5 #304 need gate — those are safety properties,
        not taste (a "relaxed" horrid trade is still horrid; targeted jobs
        bypass R5 upstream via R-5b, so R5 is a no-op here anyway). The R4
        #336 awaiting/matched exclusion and past-decision dedup also still
        apply, so already-swiped/liked/matched trades never resurface as
        "relaxed".

        Overrides ride the thread-local _cfg overlay (_cfg_override), so
        concurrent normal jobs on other threads are untouched. The relaxed
        pass never streams progress (on_opponent_done=None) — the caller's
        progress bar already completed during the normal pass.

        Every returned card is stamped relaxed=True + relaxed_reason so
        clients can label it (e.g. "Stretch idea — outside your usual
        fairness band").
        """
        relaxed_thr = min(float(v2_kwargs["fairness_threshold"]),
                          _c("relaxed_fairness_threshold"))
        floor = _c("relaxed_surplus_floor")
        stages = [
            ("fairness_band",
             {"fairness_floor_divergence": relaxed_thr}),
            ("fairness_band+surplus_floor",
             {"fairness_floor_divergence": relaxed_thr,
              "min_side_surplus":          floor,
              "min_side_surplus_marginal": floor}),
        ]
        for reason, overrides in stages:
            kwargs = dict(v2_kwargs)
            kwargs["fairness_threshold"] = relaxed_thr
            kwargs["on_opponent_done"] = None
            with _cfg_override(overrides):
                cards = self._generate_trades_v2(**kwargs)
            if cards:
                for c in cards:
                    c.relaxed = True
                    c.relaxed_reason = reason
                return cards
        return []

    # ------------------------------------------------------------------
    # #172/#189 follow-up — asset-centric Upgrade / Lateral / Downgrade
    # ideas (flag: trade.asset_ideas; route POST /api/trades/asset-ideas)
    # ------------------------------------------------------------------

    def generate_asset_ideas(self, *, user_id: str, **kwargs):
        """#215 — same stud-tax mode pinning as generate_trades."""
        mode = pinned_stud_tax_mode() or stud_tax_mode_for_user(user_id)
        with stud_tax_override(mode):
            return self._generate_asset_ideas_impl(user_id=user_id, **kwargs)

    def _generate_asset_ideas_impl(
        self,
        *,
        user_id: str,
        user_roster: list[str],
        league_id: str,
        seed_elo: dict[str, float],
        asset_id: str,
        direction: str = "give",             # "give" (trade away) | "receive" (acquire)
        fairness_threshold: float = 0.50,
        raw_user_elo: dict[str, float] | None = None,
        untouchable_ids: set | None = None,
        not_interested_ids: set | None = None,
        avoid_positions: list[str] | None = None,   # #360 — receive-side
                                                    # positional exclusion
        swap_positions: list[str] | None = None,    # #403 W2 / #402 rev-3 §2 —
                                                    # replaces the #198 same-
                                                    # position predicate; scope
                                                    # depends on lateral_scope
                                                    # presence (QA-B F1, below)
        lateral_scope: str | None = None,    # #402 rev-3 §3 — None (absent
                                             # from the request: pre-rev-3
                                             # caller — band semantics AND the
                                             # lateral-only swap rule) |
                                             # "band" | "tier" (lateral =
                                             # tier-mates)
        scoring_format: str = "1qb_ppr",     # #402 rev-3 §3 — tier bucketing
                                             # format for lateral_scope="tier"
        opponent_user_id: str | None = None,  # #250 Specific Team: scope the
                                              # sweep to this one league-mate
    ) -> dict[str, list[dict]]:
        """Grouped trade ideas for ONE pinned asset (player or pick), the
        Dynasty-Trade-Factory "Smart Trade Finder" presentation: sweep every
        league-mate's roster (owned picks included when the caller injected
        them) and return candidate deals grouped Upgrade / Lateral /
        Downgrade around the pinned asset's CONSENSUS value.

        POSITION-CENTRIC semantics (#198): upgrading means upgrading the
        PINNED ASSET'S POSITION. For a player pin at position P, the
        Upgrade and Lateral groups are constrained to counterpart players
        at P — a cross-position return is never an "upgrade at P", however
        valuable. The Downgrade group stays value-based (a spread-out
        return is inherently multi-positional) but PREFERS same-position
        headliners when available. The position constraint is a semantic,
        not a gate knob: it is NEVER relaxed (the #189 refill widens only
        the fairness band, within the same position). For a PICK pin
        "same position" doesn't apply — all three groups fall back to pure
        value bands (better picks/value up, band swaps across).

        #403 W2, widened by #402 rev-3 §2, forked by rev-3 QA-B F1 —
        `swap_positions` (optional, validated by the route): when
        non-empty it REPLACES the #198 same-position predicate — but its
        REACH is keyed on the request shape. `lateral_scope` present
        (any valid value — the rev-3 client always sends it): the set
        constrains EVERY group's incoming headline piece (supersedes W2's
        lateral-only rule / PRD R-11): the upgrade counterpart, the
        lateral swap, and the downgrade package's headliner (`combo[0]`;
        the receive-direction mirror constrains the user's variable give
        piece `g` in all three groups) must play a position in the set —
        the pin's own position included only if selected. `lateral_scope`
        absent/None (every pre-rev-3 caller — the shipped v1.16.9 inline
        strip whose picker promised Same-value-only): the set filters the
        LATERAL group only; upgrade/downgrade keep #198 byte-identical to
        the v1.16.9 deploy. Absent/empty `swap_positions` is
        byte-identical to #198 for all three groups under either shape.
        PICK pins ignore it (pos_constrained is False — pure value bands
        already).

        #402 rev-3 QA-B F2 — D-067 dismiss cooldown: ideas whose
        (frozenset(give), frozenset(receive)) key has a live dismiss
        cooldown for this user (`self._dismissed_decision_keys` — the
        "pass" subset of the deck path's `_past_decision_keys`, same key
        derivation, `pass_cooldown_days` window) are excluded from every
        group, both directions, both lateral scopes. A LIKE never
        excludes here: it is a queued proposal, and its deck-side
        exclusion (#336 R4 / the 7-day like window) stays deck-only.
        Deliberate consequence: the single-pin panel stops re-serving
        shop-dismissed packages too — that is D-067 compliance ("the
        cooldown binds every live service immediately"), not a
        regression.

        #402 rev-3 §3 — `lateral_scope` (optional, validated by the
        route): absent/None or `"band"` keeps today's ±band lateral pool
        (they differ only in the swap_positions reach above);
        `"tier"` replaces the ±asset_ideas_lateral_band membership AND the
        #108 gain gates AND the fairness floor for the LATERAL group only
        with tier equality per `ranking_service.tier_for_elo` — every
        counterpart on the pin's rung of the 8-tier pick-valuation ladder
        is returned (still position-filtered, still capped/deduped/
        ordered, still subject to untouchables / not-interested / #360
        avoids at pool build). Upgrade and downgrade keep band math
        byte-identical under either scope. Tier-scope laterals are never
        labeled `relaxed` — membership is the rule; the card's verdict
        prices each idea.

        direction="give" (pinned asset leaves the user's roster — "what can
        I get for X?"): ideas enumerate the RETURN. A same-position
        counterpart above the ±asset_ideas_lateral_band band is an Upgrade
        target (the user adds own-roster sweeteners — any position, picks
        included — when a straight 1-for-1 can't close the gap); inside
        the band it's a same-position Lateral 1-for-1; below it, 2-3
        lesser pieces (any position) are packaged back as a Downgrade,
        same-position headliners first.

        direction="receive" (pinned asset is acquired from its owner —
        "what would X cost me?"): the mirror. Ideas enumerate what the USER
        GIVES — a lesser own asset AT THE PIN'S POSITION headlines the
        tier-up into the pin (Upgrade; the optional second own piece may be
        any position), a band-value same-position own asset swaps straight
        across (Lateral), and a single better own asset (any position,
        same-position ordered first) comes back as the pin plus owner
        sweetener(s) (Downgrade).

        Valuation and gates are the consensus-basis reuse set from
        _generate_consensus_for_pair — package_value_v2 (crown premium via
        n_other), the min/max fairness ratio, the #108 user-gain gates
        (user_gain_epsilon on the consensus package delta +
        user_gain_ok_1for1 on the raw board), #141 filler_ok and the
        consolidation raw-loss cap. No new valuation math.

        Coverage relaxation (#189 convention): candidates are evaluated
        against min(fairness_threshold, relaxed_fairness_threshold); a
        group that would otherwise be EMPTY refills from candidates that
        passed only the widened band, labeled relaxed=True +
        relaxed_reason="fairness_band". The #108 gates, untouchables and
        not-interested exclusions are NEVER relaxed.

        Each idea dict: counterparty ids, give/receive player-id lists,
        adjusted package values (give_value / receive_value — same value
        space as the calculator), signed difference (receive − give; + =
        user ahead on consensus), fairness. Groups are capped at
        asset_ideas_group_cap, ordered by |difference| ascending (the
        Downgrade group orders same-position headliners first, then
        |difference|). Deterministic for a fixed league snapshot.
        """
        empty: dict[str, list[dict]] = {"upgrade": [], "lateral": [], "downgrade": []}
        league = self._leagues.get(league_id)
        players = self._players
        _avoid = set(avoid_positions or ())      # #360
        if not league or asset_id not in players:
            return empty
        if direction not in ("give", "receive"):
            return empty

        _vs_cache: dict[str, float] = {}

        def _v(pid: str) -> float:
            val = _vs_cache.get(pid)
            if val is None:
                val = elo_to_value(seed_elo.get(pid, 1500.0))
                _vs_cache[pid] = val
            return val

        def _uval_raw(pid: str) -> float:
            # #141 max-of-boards arm: user raw board where known, else
            # consensus (mirrors the consensus generator).
            e = raw_user_elo.get(pid) if raw_user_elo else None
            return elo_to_value(e) if e is not None else _v(pid)

        v_pin = _v(asset_id)
        band = _c("asset_ideas_lateral_band")
        lo, hi = v_pin * (1.0 - band), v_pin * (1.0 + band)
        cap = max(1, int(_c("asset_ideas_group_cap")))
        relaxed_thr = min(fairness_threshold, _c("relaxed_fairness_threshold"))

        # #198 — the pin's position drives the Upgrade/Lateral constraint.
        # PICK pins (and metadata-less pins) have no position to upgrade:
        # they keep pure value-band semantics.
        pin_pos = getattr(players[asset_id], "position", None)
        pos_constrained = pin_pos not in (None, "PICK")

        def _same_pos(pid: str) -> bool:
            return getattr(players.get(pid), "position", None) == pin_pos

        # #403 W2 / #402 rev-3 §2 — which counterparts may headline a group.
        _swap = {str(p).upper() for p in (swap_positions or ())}

        # #402/#403 rev-3 QA-B F1 — the rev-3 client always sends
        # lateral_scope; its absence identifies a v1.16.9-era request whose
        # picker UI promised lateral-only. So the rev-3 §2 all-groups
        # widening is keyed on the request signature: swap_positions
        # constrains upgrade/downgrade ONLY when lateral_scope was present
        # in the request (any valid value — the route passes None when the
        # body omitted it); absent, the set filters the LATERAL group only,
        # byte-identical to the v1.16.9 deploy, so shipping this backend
        # cannot silently change Tier up/down for a fielded client holding
        # a selection.
        _swap_all_groups = bool(_swap) and lateral_scope is not None

        def _pos_ok(pid: str) -> bool:
            """Empty selection ⇒ #198 verbatim (the pin's own position).
            Non-empty ⇒ the user's set REPLACES it — always for lateral
            (that IS the v1.16.9 behavior); for upgrade/downgrade only
            under the rev-3 request signature (_swap_all_groups — see the
            QA-B F1 comment above; upgrade/downgrade call _head_ok).
            Never a filter over _same_pos's results: upgrade/lateral are
            otherwise hard-locked to the pin's position, so intersecting
            the two is empty for every position but the pin's — a control
            that always shows "nothing found"."""
            if not _swap:
                return _same_pos(pid)
            return getattr(players.get(pid), "position", None) in _swap

        def _head_ok(pid: str) -> bool:
            """Upgrade-headliner predicate — the QA-B F1 fork: the user's
            set replaces #198 only on a rev-3-shaped request; an old-shape
            request keeps the pin's own position, byte-identical."""
            return _pos_ok(pid) if _swap_all_groups else _same_pos(pid)

        # #402 rev-3 §3 — lateral_scope="tier": the lateral pool is TIER
        # membership on the 8-tier pick-valuation ladder, not the ±band.
        _tier_scope = lateral_scope == "tier"
        if _tier_scope:
            # Local import, same pattern as the intent filter above —
            # ranking_service is import-safe here but trade_service loads
            # before it in some entry paths.
            from .ranking_service import RankingService

            def _tier_of(pid: str):
                # #402 rev-3 QA-B F3 — an asset with NO real seed has NO
                # tier. The 1500.0 default that band math prices at is a
                # placeholder, not a ranking: bucketing it would land every
                # seed-missing asset on the 'second' rung and tier scope
                # would surface default-priced assets the band + #108 gates
                # used to hide. The spec's own "unranked never matches"
                # line, extended to seed-missing: None never equals a rung,
                # so these assets never tier-match (the pin included) while
                # staying band-eligible exactly as today via _v's default.
                e = seed_elo.get(pid)
                if e is None:
                    return None
                return RankingService.tier_for_elo(
                    e,
                    getattr(players.get(pid), "position", None),
                    scoring_format)

            # #402 rev-3 §3 — THE EXACT COMPARISON SHIPPED: tier-NAME
            # equality on the shared ORDERED_TIERS ladder ('firsts_4plus'
            # … 'waivers'), each asset bucketed by tier_for_elo against
            # ITS OWN position's bands in the league's scoring format.
            # The names ARE the spec's tier indices 1..8 — one ordered
            # ladder shared by every (scoring_format, position) block.
            # This is sound cross-position because tier_config.json's
            # bands are pick-value-anchored and byte-identical across all
            # 8 (format, position) blocks by design ("pick value is
            # position-uniform by design" — tier_config.json _calibration
            # + docs/cross-client-invariants.md; verified identical in
            # the current config on 2026-08-28). And if the bands ever
            # diverged per position, rung-name equality would STILL be
            # the honest comparison — the rung of the shared
            # pick-valuation ladder is what the operator called "the same
            # tier", not raw ELO overlap. An unranked asset (tier_for_elo
            # → None, below the waivers floor) has no rung: None never
            # matches, so an unranked pin has zero tier-mates rather than
            # "every other unranked asset".
            _pin_tier = _tier_of(asset_id)

        def _lateral_hit(pid: str, val: float) -> bool:
            """Lateral-group membership. Band scope = today's ±band on
            the pin's consensus value; tier scope (#402 rev-3 §3) = same
            ladder rung as the pin."""
            if _tier_scope:
                return _pin_tier is not None and _tier_of(pid) == _pin_tier
            return lo <= val <= hi

        def _price(give_ids: list[str], recv_ids: list[str]):
            """#402 rev-3 §3 — pricing WITHOUT the gate set, for
            tier-scope laterals only: membership (tier equality) is the
            rule, so the ±band, the #108 gain gates, and the fairness
            floor do not apply. Rides `price_consensus_package` — the
            pricing half of the one gate function — so the card's verdict
            prices these ideas exactly like every gated idea."""
            return price_consensus_package(give_ids, recv_ids, value_of=_v)

        def _eval(give_ids: list[str], recv_ids: list[str]):
            """All non-fairness gates + the WIDENED fairness band. Returns
            (fairness, gv, rv) or None when hard-gated. The body lives in
            `eval_consensus_package` so the #384 fair-package search shares
            these gates rather than copying them."""
            return eval_consensus_package(
                give_ids, recv_ids,
                value_of      = _v,
                raw_value_of  = _uval_raw,
                raw_user_elo  = raw_user_elo,
                relaxed_thr   = relaxed_thr,
            )

        # #402 rev-3 QA-B F2 — D-067: the dismiss cooldown binds this sweep
        # too. Same key derivation as the deck path's _past_decision_keys /
        # the swipe route's in-memory bind (frozenset(give), frozenset(recv)
        # in USER orientation — the service instance already scopes user +
        # league); consulted for every group, both directions, both lateral
        # scopes — a correctness rule, not a tier feature. Only DISMISSES
        # ("pass", pass_cooldown_days-windowed at load) live in
        # _dismissed_decision_keys: a like is a queued proposal and never
        # suppresses an idea here. Deliberate consequence: the single-pin
        # panel stops re-serving shop-dismissed packages too — D-067
        # compliance, not a regression.
        def _dismissed(give_ids, recv_ids) -> bool:
            return ((frozenset(give_ids), frozenset(recv_ids))
                    in self._dismissed_decision_keys)

        strict: dict[str, list[dict]] = {"upgrade": [], "lateral": [], "downgrade": []}
        relaxed: dict[str, list[dict]] = {"upgrade": [], "lateral": [], "downgrade": []}
        seen: set[tuple] = set()

        def _emit(member, give_ids, recv_ids, res, group, gated=True) -> None:
            # QA-B F2 backstop — every idea funnels through here; the
            # _emit_best variant filter and the downgrade combo skip above
            # exist so a dismissed variant yields its slot to the next-best
            # instead of silently consuming it.
            if _dismissed(give_ids, recv_ids):
                return
            # Dedupe is GROUP-scoped (#402 rev-3 §3): under band scope the
            # groups partition the value axis, so adding `group` to the key
            # is byte-identical; under tier scope a tier-mate above the
            # band is honestly BOTH an upgrade (band math untouched) and a
            # lateral tier-mate, and neither group may lose its idea to
            # the other's earlier emission.
            key = (frozenset(give_ids), frozenset(recv_ids),
                   member.user_id, group)
            if key in seen:
                return
            seen.add(key)
            fairness, gv, rv = res
            idea = {
                "counterparty_user_id":  member.user_id,
                "counterparty_username": member.username,
                "give_player_ids":       list(give_ids),
                "receive_player_ids":    list(recv_ids),
                "give_value":            round(gv, 1),
                "receive_value":         round(rv, 1),
                "difference":            round(rv - gv, 1),
                "fairness":              round(fairness, 3),
            }
            # #402 rev-3 §3 — gated=False is the tier-scope lateral path:
            # membership (tier equality) is the rule, not fairness, so the
            # idea is never labeled or suppressed as `relaxed` — the
            # card's verdict prices it instead.
            if not gated or fairness >= fairness_threshold:
                strict[group].append(idea)
            else:
                idea["relaxed"] = True
                idea["relaxed_reason"] = "fairness_band"
                relaxed[group].append(idea)

        # C2 (2026-08-18, docs/plans/engine-quality/scope.md) — minimal-package
        # tolerance band, in FAIRNESS units, measured from the BEST variant of
        # this search. Variants no worse than `band` below the best fairness
        # are near-equivalent deals, and among them the one with FEWER pieces
        # wins. A variant further out than the band still loses, so a
        # genuinely needed sweetener is never dropped. 0 disables
        # (closest-gap-wins, byte-identical to pre-C2).
        _min_pkg_band = _c("min_package_band")

        def _emit_best(member, variants, group) -> None:
            """variants: [(give_ids, recv_ids, res)]. Emit the best deal —
            strict-band passes over relaxed, then (C2) the fewest pieces among
            near-equivalent fairness, then closest to even."""
            # QA-B F2 — a dismissed variant is out of the running entirely,
            # so the next-best variant wins the slot rather than the whole
            # opponent's idea vanishing with it.
            variants = [v for v in variants if not _dismissed(v[0], v[1])]
            if not variants:
                return
            if _min_pkg_band <= 0:
                def _rank(v):
                    fairness, gv, rv = v[2]
                    return (fairness < fairness_threshold, abs(rv - gv),
                            tuple(v[0]), tuple(v[1]))
            else:
                # Ranking on |difference| alone made a bare 1-for-1 at a
                # 200-point gap LOSE to the same trade plus a 180-point pick
                # that shaved the gap to 20 — the pick bought the slot for
                # free even though the bare deal was already fair.
                _best_f = max(v[2][0] for v in variants)
                def _rank(v):
                    fairness, gv, rv = v[2]
                    return (fairness < fairness_threshold,
                            int((_best_f - fairness) / _min_pkg_band),
                            len(v[0]) + len(v[1]),
                            abs(rv - gv), tuple(v[0]), tuple(v[1]))
            _emit(member, *min(variants, key=_rank), group)

        # Bound the piece pool for 2/3-asset package enumeration.
        _POOL = 12

        def _asset_sort(ids) -> list[str]:
            return sorted(ids, key=lambda p: (-_v(p), p))

        if direction == "give":
            if asset_id not in user_roster:
                return empty
            if untouchable_ids and asset_id in untouchable_ids:
                return empty     # untouchables are never given away (never relaxed)
            sweeteners = _asset_sort(
                p for p in set(user_roster)
                if p != asset_id and p in players
                and not (untouchable_ids and p in untouchable_ids))
            opponents = sorted(
                (m for m in league.members if m.user_id != user_id and m.roster),
                key=lambda m: m.user_id)
            # #250 Specific Team — only the targeted league-mate's roster
            # may supply the return side.
            if opponent_user_id:
                opponents = [m for m in opponents
                             if m.user_id == opponent_user_id]
            for member in opponents:
                pool = _asset_sort(
                    p for p in set(member.roster)
                    if p in players and p != asset_id
                    and not (not_interested_ids and p in not_interested_ids)
                    # #360 — the return side IS the user's receive side.
                    and avoid_ok(p, players, _avoid))
                for c in pool:
                    vc = _v(c)
                    # #198 — Upgrade/Lateral counterparts must play the
                    # pin's position (semantic constraint, never relaxed).
                    # #402 rev-3 §2 + QA-B F1 — when swap_positions is
                    # present the set REPLACES that predicate: for lateral
                    # always (_pos_ok — v1.16.9 behavior); for upgrade/
                    # downgrade only on a rev-3-shaped request (_head_ok /
                    # _swap_all_groups — lateral_scope present in the
                    # body). Absent keeps #198 verbatim, so old requests
                    # stay byte-identical.
                    # #402 rev-3 §3 — lateral membership is _lateral_hit
                    # (band, or tier equality under lateral_scope="tier").
                    # Under tier scope a tier-mate above the band is BOTH
                    # a lateral and an upgrade candidate, so these are two
                    # independent ifs, not the old if/elif band partition
                    # (disjoint again under band scope — byte-identical).
                    if _lateral_hit(c, vc) and \
                            (not pos_constrained or _pos_ok(c)):
                        res = (_price([asset_id], [c]) if _tier_scope
                               else _eval([asset_id], [c]))
                        if res:
                            _emit(member, [asset_id], [c], res, "lateral",
                                  gated=not _tier_scope)
                    if vc > hi and \
                            not (pos_constrained and not _head_ok(c)):
                        variants = []
                        res = _eval([asset_id], [c])
                        if res:
                            variants.append(([asset_id], [c], res))
                        for s in sweeteners:
                            res = _eval([asset_id, s], [c])
                            if res:
                                variants.append(([asset_id, s], [c], res))
                        # #286 — a single sweetener is a blunt instrument: the
                        # window between "still underpaying" (fails fairness)
                        # and "now overpaying" (fails the #108 gain gate) can
                        # be narrower than any one available piece. Two
                        # SMALLER pieces can land inside it where one big one
                        # overshoots — the same combinatorial breadth the
                        # Downgrade search below already gets. Bounded to the
                        # top _POOL sweeteners (value-sorted) to cap cost.
                        for s1, s2 in combinations(sweeteners[:_POOL], 2):
                            res = _eval([asset_id, s1, s2], [c])
                            if res:
                                variants.append(([asset_id, s1, s2], [c], res))
                        _emit_best(member, variants, "upgrade")
                # Downgrade: 2-3 lesser pieces back for the pin. Best 2
                # combos per opponent with DISTINCT headliners (recombining
                # the same top piece is a near-duplicate, not variety).
                # #198 — value-based (a spread-out return is inherently
                # multi-positional) but same-position headliners are
                # preferred when available (after the strict-band split,
                # before deal closeness).
                down = [p for p in pool if _v(p) < lo][:_POOL]
                combos = []
                for r in (2, 3):
                    for combo in combinations(down, r):
                        # #402 rev-3 §2 + QA-B F1 — downgrade's incoming
                        # headline piece (combo[0]; `down` is value-sorted
                        # desc) must play a selected position when the
                        # filter is present ON A REV-3-SHAPED REQUEST
                        # (_swap_all_groups). Old-shape requests (and an
                        # absent filter) keep #198's any-position-with-
                        # same-position-preference, byte-identical.
                        if _swap_all_groups and pos_constrained \
                                and not _pos_ok(combo[0]):
                            continue
                        # QA-B F2 — a dismissed combo never consumes one of
                        # the two headliner slots below.
                        if _dismissed([asset_id], combo):
                            continue
                        res = _eval([asset_id], list(combo))
                        if res:
                            combos.append((list(combo), res))
                combos.sort(key=lambda cr: (cr[1][0] < fairness_threshold,
                                            pos_constrained and not _same_pos(cr[0][0]),
                                            abs(cr[1][2] - cr[1][1]),
                                            tuple(cr[0])))
                kept_headliners: set[str] = set()
                for combo, res in combos:
                    if len(kept_headliners) >= 2:
                        break
                    head = combo[0]          # pools are value-sorted desc
                    if head in kept_headliners:
                        continue
                    kept_headliners.add(head)
                    _emit(member, [asset_id], combo, res, "downgrade")
        else:   # direction == "receive"
            if not_interested_ids and asset_id in not_interested_ids:
                return empty     # user said never offer this to them
            # #360 — same rule at position granularity: an exclusion beats a
            # pin (PRD R-6.2 / D-360-3(b)), mirroring the #163 guard above.
            if not avoid_ok(asset_id, players, _avoid):
                return empty
            owner = next(
                (m for m in sorted(league.members, key=lambda m: m.user_id)
                 if m.user_id != user_id and asset_id in (m.roster or [])),
                None)
            if owner is None:
                return empty
            # #250 Specific Team — a pin owned by anyone other than the
            # targeted league-mate has no on-team acquire ideas.
            if opponent_user_id and owner.user_id != opponent_user_id:
                return empty
            give_pool = _asset_sort(
                p for p in set(user_roster)
                if p != asset_id and p in players
                and not (untouchable_ids and p in untouchable_ids))
            extras = _asset_sort(
                p for p in set(owner.roster)
                if p in players and p != asset_id
                and not (not_interested_ids and p in not_interested_ids)
                and avoid_ok(p, players, _avoid))[:_POOL]      # #360
            for g in give_pool:
                vg = _v(g)
                # #198 mirror — the Upgrade headliner and the Lateral swap
                # must play the pin's position (upgrading/swapping AT that
                # position); the Downgrade give may be any position.
                # #402 rev-3 §2 mirror + QA-B F1 — the user's variable give
                # piece `g` is what the position set constrains in this
                # direction (the incoming pin is fixed): when the set is
                # present, _pos_ok replaces the #198 predicate on lateral
                # always (v1.16.9 behavior) and _head_ok/_swap_all_groups
                # extends it to upgrade and the downgrade give below only
                # on a rev-3-shaped request (lateral_scope present). Absent
                # keeps #198 verbatim — byte-identical.
                # #402 rev-3 §3 mirror — lateral membership via
                # _lateral_hit; two independent ifs for the same
                # dual-membership reason as the give direction.
                if _lateral_hit(g, vg) and \
                        (not pos_constrained or _pos_ok(g)):
                    res = (_price([g], [asset_id]) if _tier_scope
                           else _eval([g], [asset_id]))
                    if res:
                        _emit(owner, [g], [asset_id], res, "lateral",
                              gated=not _tier_scope)
                if lo <= vg <= hi:
                    pass          # lateral band handled above
                elif vg < lo:
                    if pos_constrained and not _head_ok(g):
                        continue  # upgrade headliner — #198 / rev-3 §2 + F1
                    # Tier UP into the pin: this asset headlines, optionally
                    # plus one more own piece (any position) to close the gap.
                    variants = []
                    res = _eval([g], [asset_id])
                    if res:
                        variants.append(([g], [asset_id], res))
                    for s in give_pool:
                        if s == g:
                            continue
                        res = _eval([g, s], [asset_id])
                        if res:
                            variants.append(([g, s], [asset_id], res))
                    # #286 mirror of the give-direction widening above: two
                    # smaller own pieces can land inside the accept window a
                    # single piece overshoots. Bounded pool caps cost.
                    pool2 = [p for p in give_pool[:_POOL] if p != g]
                    for s1, s2 in combinations(pool2, 2):
                        res = _eval([g, s1, s2], [asset_id])
                        if res:
                            variants.append(([g, s1, s2], [asset_id], res))
                    _emit_best(owner, variants, "upgrade")
                else:
                    # Tier DOWN: give the better own asset, receive the pin
                    # plus 1-2 owner sweeteners (a bare 1-for-1 down always
                    # fails the #108 epsilon, so extras are required).
                    # #402 rev-3 §2 mirror + QA-B F1 — when the position
                    # set is present ON A REV-3-SHAPED REQUEST, the
                    # variable give piece must play a selected position;
                    # old-shape / absent keeps any-position, byte-identical.
                    if _swap_all_groups and pos_constrained \
                            and not _pos_ok(g):
                        continue
                    variants = []
                    for e in extras:
                        res = _eval([g], [asset_id, e])
                        if res:
                            variants.append(([g], [asset_id, e], res))
                    for e1, e2 in combinations(extras, 2):
                        res = _eval([g], [asset_id, e1, e2])
                        if res:
                            variants.append(([g], [asset_id, e1, e2], res))
                    _emit_best(owner, variants, "downgrade")

        out: dict[str, list[dict]] = {}
        order_key = lambda i: (abs(i["difference"]), i["counterparty_user_id"],
                               tuple(i["give_player_ids"]),
                               tuple(i["receive_player_ids"]))

        # #198 — downgrade ordering: same-position headliners first (the
        # counterpart side's top piece plays the pin's position), then deal
        # closeness. Upgrade/Lateral are position-constrained already, so
        # their pure |difference| ordering is unchanged.
        def _down_key(i):
            side = (i["receive_player_ids"] if direction == "give"
                    else i["give_player_ids"])
            cross = pos_constrained and not (side and _same_pos(side[0]))
            return (cross,) + order_key(i)

        for group in ("upgrade", "lateral", "downgrade"):
            # #189 convention: relaxed-band ideas surface ONLY when the
            # group would otherwise be empty, and stay labeled.
            chosen = strict[group] or relaxed[group]
            key = _down_key if group == "downgrade" else order_key
            out[group] = sorted(chosen, key=key)[:cap]
        return out

    # ------------------------------------------------------------------
    # #384 W6-B — fairness-only packages around a FIXED give-side anchor
    # (flag calc.merged_layout; route POST /api/trades/fair-packages)
    # ------------------------------------------------------------------

    def generate_fair_packages(self, *, user_id: str, **kwargs):
        """#215 — same stud-tax mode pinning as generate_trades."""
        mode = pinned_stud_tax_mode() or stud_tax_mode_for_user(user_id)
        with stud_tax_override(mode):
            return self._generate_fair_packages_impl(user_id=user_id, **kwargs)

    def _generate_fair_packages_impl(
        self,
        *,
        user_id: str,
        user_roster: list[str],
        league_id: str,
        seed_elo: dict[str, float],
        give_player_ids: list[str],
        receive_player_ids: list[str] | None = None,
        fairness_threshold: float = 0.50,
        raw_user_elo: dict[str, float] | None = None,
        untouchable_ids: set | None = None,
        not_interested_ids: set | None = None,
        opponent_user_id: str | None = None,
    ) -> dict:
        """What can this EXACT package fetch? — the operator's #384 W6-B ask,
        verbatim: *"a much simpler set of cards solving for fairness only.
        Similar to how we determine the consolidate and downgrade suggestions
        already."*

        The give side is an ANCHOR, not a seed: every idea returned gives away
        exactly `give_player_ids` and nothing else. The search is over the
        RETURN — 1–3 assets from one league-mate's roster (or from every
        league-mate's, when no partner is named). No model, no job, no
        divergence, no position semantics: `asset-ideas`' gate set applied to a
        fixed left-hand side, which is precisely the Downgrade group's shape
        generalised from one pinned asset to a package of N.

        Pricing and gating are `eval_consensus_package` — the same function
        `_generate_asset_ideas_impl` calls, so a fair package and an asset idea
        can never price the same trade differently.

        RECEIVE-SIDE PREFERENCE, not constraint (this is what retires the
        second half of Q-029). Assets the user put on the receive side of the
        canvas are a statement of interest, so ideas containing ALL of them
        sort first — but an idea that cannot include them is still shown rather
        than the user being handed an empty deck with a misleading message. A
        canvas pick outside `picks_pool_cap` therefore costs nothing here: the
        anchor is priced from `seed_elo`, never re-derived from `user_roster`.

        Returns `{"ideas": [...], "relaxed": bool, "reason": str | None}`.
        `reason` is set only when the search refused before enumerating:
        `give_untouchable` (an anchor asset is on the caller's own untouchable
        list — their rule, so the honest answer is zero ideas and why),
        `unknown_asset`, or `no_partner` (the named partner is not a
        league-mate with a roster).

        Ideas carry the AssetIdea shape (counterparty, both id lists, both
        package values, signed difference, fairness, and the #189 `relaxed`
        labels), as ONE flat list capped at `fair_packages_cap` — the deck is
        a swipe stack, not three groups. Deterministic for a fixed league
        snapshot.
        """
        empty = {"ideas": [], "relaxed": False, "reason": None}
        league = self._leagues.get(league_id)
        players = self._players
        if not league:
            return dict(empty, reason="unknown_league")

        give_anchor = list(dict.fromkeys(str(p) for p in (give_player_ids or [])))
        if not give_anchor:
            return dict(empty, reason="unknown_asset")
        if any(p not in players for p in give_anchor):
            return dict(empty, reason="unknown_asset")
        # The caller's OWN rule, so it is a refusal with a name rather than a
        # silent filter: an untouchable on the give side means the canvas
        # contradicts the preference list the user set.
        if untouchable_ids and any(p in untouchable_ids for p in give_anchor):
            return dict(empty, reason="give_untouchable")

        anchor_set = set(give_anchor)
        want_recv = [str(p) for p in (receive_player_ids or [])
                     if p in players and p not in anchor_set]
        want_set = set(want_recv)

        _vs_cache: dict[str, float] = {}

        def _v(pid: str) -> float:
            val = _vs_cache.get(pid)
            if val is None:
                val = elo_to_value(seed_elo.get(pid, 1500.0))
                _vs_cache[pid] = val
            return val

        def _uval_raw(pid: str) -> float:
            e = raw_user_elo.get(pid) if raw_user_elo else None
            return elo_to_value(e) if e is not None else _v(pid)

        relaxed_thr = min(fairness_threshold, _c("relaxed_fairness_threshold"))

        def _eval(recv_ids: list[str]):
            return eval_consensus_package(
                give_anchor, recv_ids,
                value_of     = _v,
                raw_value_of = _uval_raw,
                raw_user_elo = raw_user_elo,
                relaxed_thr  = relaxed_thr,
            )

        opponents = sorted(
            (m for m in league.members if m.user_id != user_id and m.roster),
            key=lambda m: m.user_id)
        if opponent_user_id:
            opponents = [m for m in opponents if m.user_id == opponent_user_id]
            if not opponents:
                return dict(empty, reason="no_partner")

        strict: list[dict] = []
        relaxed: list[dict] = []
        seen: set[tuple] = set()

        def _emit(member, recv_ids: list[str], res) -> None:
            key = (member.user_id, frozenset(recv_ids))
            if key in seen:
                return
            seen.add(key)
            fairness, gv, rv = res
            idea = {
                "counterparty_user_id":  member.user_id,
                "counterparty_username": member.username,
                "give_player_ids":       list(give_anchor),
                "receive_player_ids":    list(recv_ids),
                "give_value":            round(gv, 1),
                "receive_value":         round(rv, 1),
                "difference":            round(rv - gv, 1),
                "fairness":              round(fairness, 3),
            }
            if fairness >= fairness_threshold:
                strict.append(idea)
            else:
                idea["relaxed"] = True
                idea["relaxed_reason"] = "fairness_band"
                relaxed.append(idea)

        # Same bound as the asset-ideas package search: 2- and 3-asset returns
        # are enumerated over the top-_POOL assets by value, which keeps the
        # sweep at ~300 evaluations per league-mate.
        _POOL = 12

        for member in opponents:
            avail = [p for p in sorted(set(member.roster))
                     if p in players and p not in anchor_set
                     and not (not_interested_ids and p in not_interested_ids)]
            avail.sort(key=lambda p: (-_v(p), p))
            # Canvas receive assets are held at the HEAD of the combination
            # pool so a value-based truncation can never drop the very assets
            # the user asked for.
            wanted_here = [p for p in avail if p in want_set]
            rest = [p for p in avail if p not in want_set]
            pool = wanted_here + rest[:max(0, _POOL - len(wanted_here))]

            for c in avail:                       # 1-for-N: the whole roster
                res = _eval([c])
                if res:
                    _emit(member, [c], res)
            for r in (2, 3):
                for combo in combinations(pool, r):
                    res = _eval(list(combo))
                    if res:
                        _emit(member, list(combo), res)

        # #189 convention: the widened band surfaces ONLY when the strict band
        # produced nothing at all, and stays labelled when it does.
        chosen = strict or relaxed
        was_relaxed = not strict and bool(relaxed)

        def _key(i):
            recv = i["receive_player_ids"]
            # Preference, not constraint: ideas carrying the whole canvas
            # receive side lead, then the closest deal to even.
            covers_all = bool(want_set) and want_set.issubset(recv)
            return (not covers_all, abs(i["difference"]),
                    i["counterparty_user_id"], tuple(recv))

        cap = max(1, int(_c("fair_packages_cap")))
        return {
            "ideas":   sorted(chosen, key=_key)[:cap],
            "relaxed": was_relaxed,
            "reason":  None,
        }

    # ------------------------------------------------------------------
    # Trade engine v2 (flag: trade_engine.v2)
    # Tier 1 plan (docs/plans/trade-engine-tier1-fixes.md) with research
    # amendments A1–A4 (docs/reviews/trade-engine-external-research.md §6):
    #   - single value space via elo_to_value()           (Change 1)
    #   - KTC-style package_value_v2 in each side's space  (Change 2 + A2)
    #   - both-sides surplus gate, harmonic-mean ranking   (Change 3 + A1)
    #   - waiver-slot cost on the side receiving more      (A3)
    #   - confidence shrinkage + range-overlap fairness    (Change 4 + A4)
    #   - bounded top-K heap, anchor-first candidate order (Change 5)
    #   - consensus-basis cards for unranked opponents
    # ------------------------------------------------------------------

    def _tier_mult_v2(self, elo_map: dict[str, float], pids) -> float:
        """Tier-priority multiplier (same bands as the legacy closure),
        computed from the supplied Elo map (v2 uses the shrunk user Elo)."""
        best = _c("tier_mult_bench")
        for pid in pids:
            e = elo_map.get(pid, 1500)
            if   e >= 1700: m = _c("tier_mult_elite")
            elif e >= 1580: m = _c("tier_mult_starter")
            elif e >= 1460: m = _c("tier_mult_solid")
            elif e >= 1350: m = _c("tier_mult_depth")
            else:           m = _c("tier_mult_bench")
            if m > best:
                best = m
        return best

    def _generate_trades_v2(
        self,
        *,
        user_id: str,
        user_elo: dict[str, float],
        user_roster: list[str],
        league: League,
        league_id: str,
        seed_elo: dict[str, float],
        max_per_opponent: int,
        fairness_threshold: float,
        acquire_positions: list[str] | None,
        trade_away_positions: list[str] | None,
        avoid_positions: list[str] | None = None,      # #360
        pinned_give_players: list[str] | None,
        pinned_receive_players: list[str] | None = None,
        pinned_give_mode: str = "any",
        opponent_user_id: str | None = None,
        scoring_format: str = "1qb_ppr",
        is_dynasty: bool = False,
        on_opponent_done = None,
        confidence: dict[str, int] | None = None,
        placements: dict[str, tuple[float, float]] | None = None,
        outlook: str | None = None,
        opponent_outlooks: dict[str, str] | None = None,
        opponent_pick_shares: dict[str, float] | None = None,
        untouchable_ids: set | None = None,
        target_ids: set | None = None,
        not_interested_ids: set | None = None,
        bypass_need_gate: bool = False,
        negmem_map=None,                # trade.negmem — the job's NegmemMap
                                        # (LLD §6.2). None ⇒ the seam below is
                                        # never entered.
    ) -> list[TradeCard]:
        """v2 orchestration: mirrors the legacy loop structure (profiles,
        narrative, streaming callback, global target, dedup) but routes each
        opponent to divergence-based or consensus-based generation."""
        new_cards: list[TradeCard] = []
        user_profile = analyze_roster_strengths(user_roster, self._players, scoring_format)

        # FB-47 finder targeting — derive position targets from explicit
        # prefs + the positions of pinned players. Player-level acquires
        # (pinned receive) restrict cards to the rosters holding those
        # players via the generators; position-level targets drive the
        # counterparty fit ranking below.
        _targeting = FLAGS.trade_finder_targeting
        # FB-96 — automatic positional-need fit (no user input required).
        _need_fit_on = FLAGS.trade_need_fit
        # FB-147 — acquire-side trade-block boost. Load the league's on-block
        # snapshot once (like the untouchable set), keyed by the flagging owner
        # so each card is judged against the COUNTERPARTY's flagged players.
        # Knob 0 ⇒ skip entirely (composite byte-identical, no stamp).
        _block_boost_w = _c("block_boost_weight") if FLAGS.trade_block_boost else 0.0
        _on_block_by_uid = _load_on_block_by_uid(league_id) if _block_boost_w else {}
        # #175 — directional outlook weighting (see outlook_direction_mult).
        _outlook_dir_on = FLAGS.trade_outlook_direction
        acquire_targets: list[str] = []
        sell_targets: list[str] = []
        if _targeting:
            acquire_targets = list(acquire_positions or [])
            sell_targets = list(trade_away_positions or [])
            for pid in (pinned_give_players or []):
                p = self._players.get(pid)
                pos = getattr(p, "position", None) if p else None
                if pos and pos not in sell_targets:
                    sell_targets.append(pos)

        # Confidence shrinkage BEFORE the value transform (Change 4), then
        # the D-085 placement clamp — a player the user PLACED is priced
        # inside the tier he was placed in, never out of it.
        shrunk_elo = _shrink_user_elo(user_elo, seed_elo, confidence,
                                      placements)
        user_value = {pid: elo_to_value(e) for pid, e in shrunk_elo.items()}

        # Tier 2 (2.2) — outlook blend applied to the USER's value map only:
        # the α blend encodes the USER's contender↔rebuilder stance; we don't
        # know the opponent's outlook here (future: read their stored league
        # preference). Because the blend is an INPUT to surplus math it
        # composes with the fairness gate, unlike the old post-hoc multiplier.
        # Flag OFF → values untouched (exactly the Tier 1 output).
        if FLAGS.trade_outlook_blend:
            alpha = outlook_alpha(outlook)
            for pid in user_value:
                p = self._players.get(pid)
                user_value[pid] *= outlook_blend_mult(
                    getattr(p, "position", None) if p else None,
                    getattr(p, "age", None) if p else None,
                    alpha,
                )

        _vs_cache: dict[str, float] = {}
        def _vs(pid: str) -> float:
            """Consensus (seed) value of a player in the v2 value space.
            Age-preference adjusted (2026-08-29) — both mults at 1.0 make
            age_pref_value the identity, restoring the pre-feature value."""
            v = _vs_cache.get(pid)
            if v is None:
                v = age_pref_value(elo_to_value(seed_elo.get(pid, 1500.0)),
                                   self._players.get(pid))
                _vs_cache[pid] = v
            return v

        # v2 eligibility: every other member with a roster. Members without
        # real rankings are NOT compared in divergence space (their
        # elo_ratings are fabricated noise) — they get consensus cards.
        eligible = [m for m in league.members if m.user_id != user_id and m.roster]
        # #156 Specific Team — scope the sweep to a single league-mate. Applied
        # before fit-sort/global-target so the whole budget goes to this pair.
        if opponent_user_id:
            eligible = [m for m in eligible if m.user_id == opponent_user_id]
        # FB-47 — counterparty fit per opponent (None ⇒ targeting inactive
        # or no targets expressed). Profiles are recomputed inside the loop
        # for match_ctx; this pre-pass is cheap (rosters are small) and lets
        # the visit order put high-fit opponents first within each group.
        _fit_by_uid: dict[str, float] = {}
        if _targeting and (acquire_targets or sell_targets):
            for m in eligible:
                prof = analyze_roster_strengths(m.roster, self._players, scoring_format)
                fit = partner_fit_score(prof, acquire_targets, sell_targets)
                if fit is not None:
                    _fit_by_uid[m.user_id] = fit
        # Ranked opponents FIRST: divergence cards are the core product
        # signal and must never be crowded out of the global card budget by
        # consensus fallback cards (a league with many unranked members would
        # otherwise hit global_target before any ranked opponent is visited).
        # Within each group, best-fit first when targeting is active;
        # stable sort keeps roster order otherwise.
        eligible.sort(key=lambda m: (
            not (m.has_rankings and m.elo_ratings),
            -_fit_by_uid.get(m.user_id, 0.5),
        ))
        total = len(eligible)
        global_target = max(30, max_per_opponent * 6)
        # trade.full_sweep — see the twin in `_generate_trades_impl`.
        _sweep_t0 = time.monotonic()

        # Backlog #1 — opponent outlook resolution, decoupled (phase 2) into
        # LABEL vs VALUE roles. The label (declared league preference →
        # inferred from roster shape → not_sure) is resolved whenever the
        # infer flag is on and feeds match_context / narrative framing /
        # lanes — "their team story". The VALUE blend (alpha_opp) additionally
        # requires trade.outlook_blend, which the 2026-07-17 interview turned
        # off ("age = tiebreak"): labels stay, value edits don't.
        _infer_outlook = FLAGS.trade_outlook_infer
        _blend_values = FLAGS.trade_outlook_blend
        _declared = opponent_outlooks or {}
        _pick_shares = opponent_pick_shares or {}
        _num_teams = len(league.members)
        # Interview phase 2 — fit-premium cards need the user's positional
        # needs at gate time (both divergence generators).
        _user_needs = (set(user_profile.get("position_needs", []))
                       if FLAGS.trade_fit_premium else None)

        # ------------------------------------------------------------------
        # G6 presentment rules (flag trade.presentment_rules) — construction
        # rules R1 #340 / R2 #341 / R3 #339 + the R5 #304 need gate, run
        # INSIDE every generator at construction time (R-6) so killed
        # candidates refill from the enumeration. One bound predicate is
        # threaded to all three generators + the v3 sweetener re-validation.
        # R5's inputs are computed here from user_profile whenever the
        # presentment flag is on — deliberately NOT coupled to
        # trade.fit_premium's _user_needs above (U-R5-9). Targeted jobs
        # bypass R5 only (R-5b, bypass_need_gate derived server-side).
        # Flag OFF ⇒ _presentment_ok stays None and every generator runs
        # byte-identically (R-8).
        # ------------------------------------------------------------------
        _presentment_ok = None
        if FLAGS.trade_presentment_rules:
            _r5_active = not bypass_need_gate
            _r5_needs = list(user_profile.get("position_needs", []))
            _r5_surplus = list(user_profile.get("position_surplus", []))
            _user_pos_values: dict[str, list] = {}
            # 2026-08-23 (plan §3 C3): built whenever the presentment flag is
            # on, not only when R5 is active. It is now R2's roster source as
            # well, and R2 does NOT bypass on targeted jobs — gating this on
            # `_r5_active` would silently hand targeted decks a strictly
            # harsher R2 than untargeted ones. No verdict moves for R5: the
            # only reader of `_user_pos_values` under `_r5_active` False was,
            # and remains, nothing.
            for _pid in user_roster:
                _p = self._players.get(_pid)
                if _p is None or is_pick_asset(_p):
                    continue
                _pos = getattr(_p, "position", None)
                if _pos in _PRESENTMENT_POSITIONS:
                    _user_pos_values.setdefault(_pos, []).append(
                        (_pid, _vs(_pid)))
            _kills = self._presentment_kills
            _players_map = self._players
            # Startable predicate + the user's startable counts, once per job
            # (plan §2). Same definition analyze_roster_strengths uses, so
            # these counts equal user_profile's elite+starter by construction.
            _startable_ok = _startable_ok_fn(_players_map, scoring_format)
            _user_startable = {
                _pos: sum(1 for _pid, _v in _lst
                          if _startable_ok(_pid, _players_map.get(_pid)))
                for _pos, _lst in _user_pos_values.items()
            }

            def _presentment_ok(give_ids, recv_ids, opp_ctx=None):
                if not overpay_ok(give_ids, recv_ids, _vs):
                    _kills["R1"] += 1
                    return False
                if not pos_net_ok(give_ids, recv_ids, _players_map,
                                  opp_ctx=opp_ctx):
                    _kills["R2"] += 1
                    return False
                if not pick_gap_ok(give_ids, recv_ids, _vs, _players_map):
                    _kills["R3"] += 1
                    return False
                if _r5_active and not need_gate_ok(
                        give_ids, recv_ids,
                        seed_value=_vs, players=_players_map,
                        user_pos_values=_user_pos_values, outlook=outlook,
                        position_needs=_r5_needs,
                        position_surplus=_r5_surplus,
                        scoring_format=scoring_format,
                        opp_ctx=opp_ctx):
                    _kills["R5"] += 1
                    return False
                return True

        for idx, member in enumerate(eligible):
            opp_profile = analyze_roster_strengths(member.roster, self._players, scoring_format)
            match_ctx = build_match_context(user_profile, opp_profile, scoring_format, is_dynasty)
            # Plan §2 — bind THIS league-mate's context onto the job-level
            # predicate. The generators keep calling `presentment_ok_fn(g, r)`;
            # the ctx rides the default argument. Flag off ⇒ still None.
            _member_presentment = _presentment_ok
            if _presentment_ok is not None:
                _member_presentment = (
                    lambda _g, _r, _ctx=_presentment_ctx(
                        opp_profile, _user_startable, _startable_ok,
                        scoring_format): _presentment_ok(_g, _r, _ctx))

            alpha_opp = None
            if _infer_outlook:
                declared = _declared.get(member.user_id)
                if declared:
                    resolved, source = declared, "declared"
                else:
                    resolved, _, _ = infer_team_outlook(
                        member.roster, self._players,
                        _pick_shares.get(member.user_id, 0.0), _num_teams)
                    source = "inferred"
                if _blend_values:
                    alpha_opp = outlook_alpha(resolved)
                match_ctx["opponent_outlook"] = {"value": resolved, "source": source}

            # Consensus-basis arguments, shared by the never-ranked path
            # below and the zero-divergence fallback inside the boarded path.
            _consensus_kw = dict(
                user_id              = user_id,
                opponent             = member,
                league_id            = league_id,
                seed_value           = _vs,
                shrunk_user_elo      = shrunk_elo,
                user_roster          = user_roster,
                max_cards            = max_per_opponent,
                fairness_threshold   = fairness_threshold,
                user_profile         = user_profile,
                opp_profile          = opp_profile,
                acquire_positions    = acquire_positions or [],
                trade_away_positions = trade_away_positions or [],
                avoid_positions      = avoid_positions or [],     # #360
                pinned_give_players  = pinned_give_players,
                pinned_receive_players = pinned_receive_players,
                pinned_give_mode     = pinned_give_mode,
                untouchable_ids      = untouchable_ids,
                target_ids           = target_ids,
                not_interested_ids   = not_interested_ids,
                raw_user_elo         = user_elo,
                presentment_ok_fn    = _member_presentment,
                scoring_format       = scoring_format,
            )

            if member.has_rankings and member.elo_ratings:
                if FLAGS.trade_engine_v3:
                    # Tier 3 — exact top-K package construction within pruned
                    # candidate pools (trade_optimizer). Same objective as
                    # _generate_for_pair_v2; adds 2x2/2x3/3x3 shapes, lineup
                    # feasibility, and sweeteners. Lazy import: the optimizer
                    # imports this module, so a top-level import would cycle.
                    from .trade_optimizer import generate_pair_trades_v3
                    cards = generate_pair_trades_v3(
                        user_id              = user_id,
                        shrunk_user_elo      = shrunk_elo,
                        user_value           = user_value,
                        user_roster          = user_roster,
                        opponent             = member,
                        league_id            = league_id,
                        seed_elo             = seed_elo,
                        confidence           = confidence,
                        max_cards            = max_per_opponent,
                        fairness_threshold   = fairness_threshold,
                        scoring_format       = scoring_format,
                        acquire_positions    = acquire_positions or [],
                        trade_away_positions = trade_away_positions or [],
                        avoid_positions      = avoid_positions or [],     # #360
                        pinned_give_players  = pinned_give_players,
                        pinned_receive_players = pinned_receive_players,
                        pinned_give_mode     = pinned_give_mode,
                        players              = self._players,
                        alpha_opp            = alpha_opp,
                        untouchable_ids      = untouchable_ids,
                        target_ids           = target_ids,
                        not_interested_ids   = not_interested_ids,
                        raw_user_elo         = user_elo,
                        user_needs           = _user_needs,
                        presentment_ok_fn    = _member_presentment,
                    )
                else:
                    cards = self._generate_for_pair_v2(
                        user_id              = user_id,
                        shrunk_user_elo      = shrunk_elo,
                        user_value           = user_value,
                        user_roster          = user_roster,
                        opponent             = member,
                        league_id            = league_id,
                        seed_value           = _vs,
                        max_cards            = max_per_opponent,
                        fairness_threshold   = fairness_threshold,
                        acquire_positions    = acquire_positions or [],
                        trade_away_positions = trade_away_positions or [],
                        avoid_positions      = avoid_positions or [],     # #360
                        pinned_give_players  = pinned_give_players,
                        pinned_receive_players = pinned_receive_players,
                        pinned_give_mode     = pinned_give_mode,
                        confidence           = confidence,
                        scoring_format       = scoring_format,
                        alpha_opp            = alpha_opp,
                        untouchable_ids      = untouchable_ids,
                        target_ids           = target_ids,
                        not_interested_ids   = not_interested_ids,
                        raw_user_elo         = user_elo,
                        user_needs           = _user_needs,
                        presentment_ok_fn    = _member_presentment,
                    )
                # 2026-08-15 field bug (docs/plans/compressed-board-pool/) —
                # a boarded member whose divergence path yields nothing used
                # to fall off the deck entirely, because this branch was an
                # if/else with no fall-through. That made a leaguemate who
                # ranked a little a WORSE trade partner than one who never
                # ranked at all. Fall back to the same consensus generator
                # the never-ranked path uses; cards stay labeled
                # basis="consensus" so the client can tell them apart. Only
                # fires when the divergence path returned zero cards, so a
                # member who already produces cards is untouched.
                if not cards and FLAGS.trade_divergence_fallback:
                    cards = self._generate_consensus_for_pair(**_consensus_kw)
            else:
                cards = self._generate_consensus_for_pair(**_consensus_kw)
            # FB-47 — stamp partner fit and blend it into the composite:
            # strongly on consensus cards (no divergence signal there),
            # tiebreak-strength on divergence cards. Flag off / no targets
            # ⇒ _fit_by_uid is empty and this is a no-op.
            _fit = _fit_by_uid.get(member.user_id)
            if _fit is not None:
                for c in cards:
                    c.partner_fit = _fit
                    w = (_c("fit_consensus_weight") if c.basis == "consensus"
                         else _c("fit_divergence_weight"))
                    c.composite_score = round(
                        c.composite_score * (1.0 + w * (_fit - 0.5)), 3)
            # FB-96 — per-card positional-need fit: boost swaps that give
            # from the user's surplus into the opponent's need and receive
            # at the user's need from the opponent's surplus. Bounded
            # composite multiplier applied AFTER all gates (fairness /
            # mutual gain are already settled) — it reorders acceptable
            # trades, never rescues gated ones. Flag off ⇒ no-op.
            if _need_fit_on:
                w_nf = _c("need_fit_weight")
                for c in cards:
                    nf = need_fit_score(
                        user_profile, opp_profile,
                        c.give_player_ids, c.receive_player_ids,
                        self._players, scoring_format)
                    if nf is not None:
                        c.need_fit = nf
                        c.composite_score = round(
                            c.composite_score * (1.0 + w_nf * (nf - 0.5)), 3)
            # FB-147 — acquire-side trade-block boost: a card whose ACQUIRE
            # side holds ≥1 player THIS counterparty flagged "on the block"
            # gets a flat bounded composite bump. Applied AFTER all gates
            # (fairness / user-gain / surplus are already settled) — it only
            # reorders acceptable trades, never rescues a gated one, exactly
            # like need_fit. Give-side / the user's own flagged players are out
            # of scope. Flag off or knob 0 ⇒ _block_boost_w is 0 and this is a
            # no-op (composite byte-identical, no stamp).
            if _block_boost_w:
                _blk = _on_block_by_uid.get(member.user_id)
                if _blk:
                    for c in cards:
                        if _blk.intersection(c.receive_player_ids):
                            c.block_boosted = True
                            c.composite_score = round(
                                c.composite_score * (1.0 + _block_boost_w), 3)
            # #175 — directional outlook weighting (flag
            # trade.outlook_direction): steer the deck by the USER's resolved
            # window. Rebuild-side outlooks strongly penalize cards acquiring
            # win-now/older production, boost cards returning future capital
            # (younger players, picks), and near-exclude unrescued
            # older-primary returns past ~1 year; contend-side gets only the
            # mild mirror. Computed on CONSENSUS values like classify_lane
            # (the card's shape, not either private board). Bounded
            # multiplier applied AFTER all gates (fairness / user-gain /
            # surplus are settled) — it reorders acceptable trades and, by
            # design, penalizes rather than filters, so a genuinely
            # lopsided-value win can still surface. Applies uniformly to
            # divergence (v2/v3) and consensus cards since all flow through
            # this loop. Flag off / directionless outlook ⇒ no-op
            # (composite byte-identical, nothing stamped).
            if _outlook_dir_on:
                for c in cards:
                    _m = outlook_direction_mult(
                        c.give_player_ids, c.receive_player_ids,
                        self._players, outlook, _vs)
                    if _m != 1.0:
                        c.outlook_dir = round(_m, 4)
                        c.composite_score = round(c.composite_score * _m, 3)
            # Fit-congruence (D-060) — stamp the SIGNED lane shift on every
            # card so the swipe route can weight its Elo K by how surprising
            # the swipe is given the user's window. Unconditional (the
            # feature has no flag — its kill switch is fit_k_explained_mult
            # = 1.0) and computed here because this is the only place that
            # holds both the resolved outlook and the consensus value fn.
            # Pure stamp on consensus values; never touches gates/scores.
            for c in cards:
                c.lane_shift = signed_lane_shift(
                    c.give_player_ids, c.receive_player_ids,
                    self._players, outlook, _vs)
            # Interview phase 2 — two-lane labels (flag trade.lanes): stamp
            # each card "window" / "value" from the user's resolved window.
            # Pure label on consensus values; never touches gates/scores.
            if FLAGS.trade_lanes:
                for c in cards:
                    c.lane = classify_lane(
                        c.give_player_ids, c.receive_player_ids,
                        self._players, outlook, _vs)
            # Interview phase 2 — aggression A/B (flag trade.aggression_ab):
            # the user's stable bucket nudges which acceptable offers lead
            # the deck. tilt > 0 = consensus favors the user (they open
            # light); "light" boosts those, "generous" the reverse, "fair"
            # prefers balance. Bounded reorder AFTER all gates — the
            # fairness veto still bounds |tilt| at 1 − floor.
            if FLAGS.trade_aggression_ab:
                # Aggression migration (analytics-platform P3, LLD §6.5): when
                # the experiment engine is on AND a `trade.aggression` experiment
                # is running AND this user is assigned, the EXPERIMENT drives the
                # bucket (sha256, versioned) and can override aggression_weight
                # via its variant model_overlay. Otherwise fall back to the
                # legacy MD5 bucket — zero behaviour change until #1 launches.
                _variant, _overlay = None, {}
                try:
                    from . import experiments as _X
                    _variant, _overlay = _X.variant_overlay(user_id, "trade.aggression")
                except Exception:
                    pass
                if _variant is None:
                    _variant = aggression_variant(user_id)   # MD5 bridge
                # A malformed model_overlay from a running experiment must NEVER
                # break trade generation (fail-open, LLD §6.5): a non-numeric or
                # non-dict overlay falls back to the config default. (Bad overlays
                # are also rejected at launch — defense in depth in experiments.py.)
                try:
                    _ow = _overlay.get("aggression_weight") if isinstance(_overlay, dict) else None
                    w_ab = float(_ow) if _ow is not None else _c("aggression_weight")
                except (TypeError, ValueError):
                    w_ab = _c("aggression_weight")
                for c in cards:
                    gvals = [_vs(p) for p in c.give_player_ids]
                    rvals = [_vs(p) for p in c.receive_player_ids]
                    v_max = max(gvals + rvals)
                    gv = package_value_v2(gvals, v_max,
                                          n_other=len(rvals),
                                          other_values=rvals)
                    rv = package_value_v2(rvals, v_max,
                                          n_other=len(gvals),
                                          other_values=gvals)
                    tilt = ((rv - gv) / max(gv, rv)) if max(gv, rv) > 0 else 0.0
                    if _variant == "light":
                        mult = 1.0 + w_ab * tilt
                    elif _variant == "generous":
                        mult = 1.0 - w_ab * tilt
                    else:   # fair — prefer balanced offers
                        mult = 1.0 - w_ab * abs(tilt)
                    c.aggression_variant = _variant
                    c.composite_score = round(
                        c.composite_score * max(mult, 0.0), 3)
            # trade.negmem (D-4/D-10, LLD §6.2) — partner-constant soft prior
            # from the viewer's OWN past reasoned rejections of this
            # counterparty. LAST in the per-member multiplier stack and, like
            # every multiplier above it, applied AFTER all gates: it reorders
            # acceptable trades and never rescues or removes one (NG1 is
            # structural here — the seam cannot change membership, so it can
            # never trigger the #189 `not cards` relaxed rerun either).
            # Covers v2-pair, v3 and consensus-fallback cards uniformly, since
            # all three flow through this loop. The seam owns the eff != 1.0
            # skip (the `_m != 1.0` idiom of the outlook block above): at
            # identity there is no multiply and no round, which is what makes
            # negmem_strength = 0 a byte-identical M1 disable (C1).
            # `member.user_id` is league_members.user_id — the canonical
            # roster-owner id (ADR-012), the same space the map is keyed in
            # and the same id the evidence side wrote as
            # features_json.partner_user_id, so no aliasing happens here.
            # The stamp rides the CARD (B2): the features assembly copies it
            # and never recomputes, because by logging time this arm's
            # _cfg_override has exited.
            if negmem_map is not None:
                _eff = _negmem.effective_mult(negmem_map, member.user_id,
                                              strength=_c("negmem_strength"),
                                              floor=_c("negmem_floor"))
                if _eff != 1.0:
                    _stamp = _negmem.stamp_payload(negmem_map, member.user_id,
                                                   _eff)
                    for c in cards:
                        c.negmem_stamp = _stamp
                        c.composite_score = round(c.composite_score * _eff, 3)
            for c in cards:
                c.match_context = match_ctx
                c.narrative = build_narrative(c, match_ctx, self._players)
            new_cards.extend(cards)

            if on_opponent_done is not None:
                try:
                    snapshot = self._dedup_and_sort(new_cards)
                    on_opponent_done(idx + 1, total, snapshot)
                except Exception:
                    pass  # callback issues must not derail the loop

            # trade.full_sweep (docs/plans/full-sweep/plan.md §3.2/§3.5) —
            # see the twin site in `_generate_trades_impl`. ON ⇒ no card-count
            # exit, so the sweep is complete and `_dedup_and_sort` ranks
            # globally, bounded instead by the wall-clock rail; OFF ⇒ the
            # first branch is today's behaviour and the second never runs.
            _over_target = len(new_cards) >= global_target
            if not FLAGS.trade_full_sweep and _over_target:
                break
            if FLAGS.trade_full_sweep and _c("full_sweep_budget_s") > 0 \
                    and time.monotonic() - _sweep_t0 > _c("full_sweep_budget_s"):
                break

        new_cards = self._dedup_and_sort(new_cards)
        for card in new_cards:
            self._trade_cards[card.trade_id] = card
        return new_cards

    def _generate_for_pair_v2(
        self,
        *,
        user_id: str,
        shrunk_user_elo: dict[str, float],
        user_value: dict[str, float],
        user_roster: list[str],
        opponent: LeagueMember,
        league_id: str,
        seed_value,                          # callable pid → consensus value
        max_cards: int,
        fairness_threshold: float,
        acquire_positions: list[str],
        trade_away_positions: list[str],
        avoid_positions: list[str] | None = None,      # #360
        pinned_give_players: list[str] | None,
        pinned_receive_players: list[str] | None = None,
        pinned_give_mode: str = "any",
        confidence: dict[str, int] | None = None,
        scoring_format: str = "1qb_ppr",
        alpha_opp: float | None = None,
        untouchable_ids: set | None = None,
        target_ids: set | None = None,
        not_interested_ids: set | None = None,
        raw_user_elo: dict[str, float] | None = None,
        user_needs: set | None = None,
        presentment_ok_fn=None,              # G6 rules R1/R2/R3/R5; None = off
    ) -> list[TradeCard]:
        """Divergence-based v2 generation for one (user, opponent) pair.

        All math happens in value units (elo_to_value). Packages are valued
        KTC-style per side (package_value_v2 with the trade-wide best asset
        in that side's own value space as the reference). A trade surfaces
        only when BOTH sides clear min_side_surplus; candidates are ranked
        by the harmonic mean of the two surpluses, blended with consensus
        fairness and the existing tier multiplier, kept in a bounded
        min-heap (true top-K instead of first-K).
        """
        opp_elo    = opponent.elo_ratings
        players    = self._players
        pinned_set = set(pinned_give_players) if pinned_give_players else None
        # #174 — "all" ⇒ the give side must include EVERY pinned player
        # (trade-as-one-package); "any" keeps the historical ≥1 semantics.
        pinned_all = pinned_set is not None and pinned_give_mode == "all"
        # FB-47 — pinned ACQUIRE targets: cards must receive at least one.
        pinned_recv_set = (set(pinned_receive_players)
                           if pinned_receive_players else None)

        _deadline    = time.monotonic() + 1.0
        _iter_budget = 200_000
        _iters       = 0

        # Tier 2 (2.1) — when the marginal flag is on, surpluses are computed
        # on over-replacement values, which run much smaller than raw values,
        # so the per-side gate switches to min_side_surplus_marginal (see the
        # _DEFAULT_CFG comment for the rationale).
        MARGINAL = FLAGS.trade_marginal_value
        MIN_SIDE = (_c("min_side_surplus_marginal") if MARGINAL
                    else _c("min_side_surplus"))
        GAIN_CAP = max(_c("mutual_gain_cap"), 1.0)
        WAIVER   = _c("waiver_slot_cost")
        MAX_GAP  = _c("trade_elo_gap_max")
        W_MIS    = _c("mismatch_weight")
        W_FAIR   = _c("fairness_weight")
        TARGET_BONUS = _c("target_acquire_bonus")   # #2 per-target composite reward
        MULT_CAP     = _c("pos_multiplier_cap")

        # Interview 2026-07-17 ("loosen it") — both members have real
        # boards here and the both-sides surplus gate already proves
        # mutual gain, so the consensus fairness check is only an
        # extreme-case veto. Consensus-basis cards keep the full bar.
        fairness_threshold = min(fairness_threshold,
                                 _c("fairness_floor_divergence"))

        _vo_cache: dict[str, float] = {}
        def _vo(pid: str) -> float:
            v = _vo_cache.get(pid)
            if v is None:
                v = elo_to_value(opp_elo.get(pid, 1500.0))
                # Backlog #1 — opponent outlook blend (mirrors the user-side
                # blend on user_value). alpha_opp None ⇒ flag off ⇒ raw value
                # (byte-identical to pre-change). Blending here propagates to
                # _mo / opp_repl too, since both read through _vo.
                if alpha_opp is not None:
                    p = players.get(pid)
                    v *= outlook_blend_mult(
                        getattr(p, "position", None) if p else None,
                        getattr(p, "age", None) if p else None,
                        alpha_opp,
                    )
                _vo_cache[pid] = v
            return v

        # Raw user-board value accessor — used by the marginal setup below
        # and by the #141 junk-filler gate (which judges on raw boards even
        # when the surplus math runs marginal).
        _def_uval = elo_to_value(1500.0)
        def _uv(pid: str) -> float:
            return user_value.get(pid, _def_uval)

        if MARGINAL:
            # Replacement levels computed ONCE per pair from the PRE-trade
            # rosters, in each side's own value space — the two (roster,
            # value-map) combos the surplus formulas need: the acquiring
            # side values an incoming player at his marginal over THEIR
            # roster, and the shedding side's loss is his marginal on their
            # own roster. (Exact post-trade re-optimization is Tier 3.)
            user_repl = replacement_levels(
                user_roster, _uv, players, scoring_format)
            opp_repl = replacement_levels(
                opponent.roster, _vo, players, scoring_format)

            _mu_cache: dict[str, float] = {}
            def _mu(pid: str) -> float:
                """Marginal value of pid on the USER's roster, user's space."""
                v = _mu_cache.get(pid)
                if v is None:
                    v = marginal_value(pid, _uv, user_repl, players,
                                       scoring_format)
                    _mu_cache[pid] = v
                return v

            _mo_cache: dict[str, float] = {}
            def _mo(pid: str) -> float:
                """Marginal value of pid on the OPPONENT's roster, opp space."""
                v = _mo_cache.get(pid)
                if v is None:
                    v = marginal_value(pid, _vo, opp_repl, players,
                                       scoring_format)
                    _mo_cache[pid] = v
                return v

        def _gap_ok(give_ids: list[str], recv_ids: list[str]) -> bool:
            """Same guard as legacy _elo_gap_ok, on the shrunk user Elo."""
            if MAX_GAP <= 0:
                return True
            max_give = max(shrunk_user_elo.get(p, 1500) for p in give_ids)
            max_recv = max(shrunk_user_elo.get(p, 1500) for p in recv_ids)
            return abs(max_recv - max_give) <= MAX_GAP

        _acq  = acquire_positions
        _away = trade_away_positions
        def _positions_ok(give_ids: list[str], recv_ids: list[str]) -> bool:
            """Positional preference hard filter (same semantics as legacy)."""
            if _acq:
                recv_pos = [players[p].position for p in recv_ids
                            if p in players and getattr(players[p], "position", None)]
                if not any(p in _acq for p in recv_pos):
                    return False
            if _away:
                give_pos = [players[p].position for p in give_ids
                            if p in players and getattr(players[p], "position", None)]
                if not any(p in _away for p in give_pos):
                    return False
            return True

        def _fairness(give_ids: list[str], recv_ids: list[str]) -> float | None:
            """
            Consensus fairness with range overlap (amendment A4).

            fairness = lesser/greater point ratio of consensus package
            values (value space, NOT summed seed Elo). The GATE passes when
            the two sides' value intervals [v·(1−unc), v·(1+unc)] overlap —
            unc per package is the value-weighted mean of member
            uncertainties — OR the point ratio clears fairness_threshold.
            Returns the fairness score, or None when gated out.
            """
            gvals = [seed_value(p) for p in give_ids]
            rvals = [seed_value(p) for p in recv_ids]
            v_max = max(gvals + rvals)
            gv = package_value_v2(gvals, v_max, n_other=len(recv_ids),
                                  other_values=rvals)
            rv = package_value_v2(rvals, v_max, n_other=len(give_ids),
                                  other_values=gvals)
            if gv <= 0 or rv <= 0:
                return 1.0
            fairness = min(gv, rv) / max(gv, rv)
            g_unc = (sum(v * _value_uncertainty(p, confidence)
                         for v, p in zip(gvals, give_ids)) / sum(gvals))
            r_unc = (sum(v * _value_uncertainty(p, confidence)
                         for v, p in zip(rvals, recv_ids)) / sum(rvals))
            overlap = (gv * (1 + g_unc) >= rv * (1 - r_unc)
                       and rv * (1 + r_unc) >= gv * (1 - g_unc))
            if not overlap and fairness < fairness_threshold:
                return None
            return round(fairness, 3)

        # Bounded top-K heap (Change 5). K gives max_cards headroom so the
        # final cut is a true top-N regardless of enumeration order.
        K = max(int(max_cards) * 4, 1)
        heap: list[tuple] = []
        _tb = 0
        # C1 tie-break (2026-08-18) — pricing the ranking fairness on the
        # signal core makes a package and the same package PADDED with
        # zero-divergence assets score IDENTICALLY (that is the invariance).
        # The pre-existing tie-break here is `_tb` descending, i.e. the
        # LATER-enumerated candidate wins; enumeration runs 1-for-1 first,
        # so without this the bare deal loses every tie it now makes and
        # gets evicted by its own padded siblings. On a tie, fewer pieces
        # wins. Knob 0 ⇒ this slot is a constant and the ordering is
        # byte-identical to pre-C1.
        _min_pref = _c("rank_div_min_frac") > 0
        def _offer(composite, hm, fairness, give_ids, recv_ids,
                   fit_paid=None):
            nonlocal _tb
            _tb += 1
            _size = -(len(give_ids) + len(recv_ids)) if _min_pref else 0
            entry = (composite, _size, _tb, hm, fairness, give_ids, recv_ids,
                     fit_paid)
            if len(heap) < K:
                heapq.heappush(heap, entry)
            elif composite > heap[0][0]:
                heapq.heapreplace(heap, entry)

        def _pair_surpluses(give_ids: list[str],
                            recv_ids: list[str]) -> tuple[float, float]:
            """(user_surplus, opp_surplus) — extracted 2026-08-21 from
            `_consider` (byte-identical math; `_uv(p)` == the former
            `user_value[p]` for every pid `_consider` can reach) so the gap
            auto-sweetener can re-gate sweetened combos through the exact
            same formulas.

            Package values in EACH side's own value space (Change 2).
            Tier 2 (2.1): with the marginal flag on, each side's packages
            are built from over-replacement values against THAT side's own
            pre-trade roster — clogger packages collapse, need-fillers
            keep their value. Same package_value_v2 + waiver math after."""
            if MARGINAL:
                uvals_give = [_mu(p) for p in give_ids]
                uvals_recv = [_mu(p) for p in recv_ids]
            else:
                uvals_give = [_uv(p) for p in give_ids]
                uvals_recv = [_uv(p) for p in recv_ids]
            u_max = max(uvals_give + uvals_recv)
            give_val_user = package_value_v2(uvals_give, u_max, n_other=len(recv_ids),
                                             other_values=uvals_recv)
            recv_val_user = package_value_v2(uvals_recv, u_max, n_other=len(give_ids),
                                             other_values=uvals_give)

            if MARGINAL:
                ovals_give = [_mo(p) for p in give_ids]
                ovals_recv = [_mo(p) for p in recv_ids]
            else:
                ovals_give = [_vo(p) for p in give_ids]
                ovals_recv = [_vo(p) for p in recv_ids]
            o_max = max(ovals_give + ovals_recv)
            give_val_opp = package_value_v2(ovals_give, o_max, n_other=len(recv_ids),
                                            other_values=ovals_recv)  # opp receives
            recv_val_opp = package_value_v2(ovals_recv, o_max, n_other=len(give_ids),
                                            other_values=ovals_give)  # opp gives

            # Waiver-slot cost (A3): the side receiving MORE players drops a
            # waiver-level player per extra slot — subtract from that side's
            # received package value. Replaces the clogger tax in v2.
            extra = len(recv_ids) - len(give_ids)
            if extra > 0:        # user receives more players
                recv_val_user -= WAIVER * extra
            elif extra < 0:      # opponent receives more players
                give_val_opp -= WAIVER * (-extra)

            return (recv_val_user - give_val_user,
                    give_val_opp - recv_val_opp)

        def _composite_v2(hm: float, fairness: float, give_ids: list[str],
                          recv_ids: list[str]) -> float:
            """Extracted 2026-08-21 from `_consider`, byte-identical.
            C1/C5 (2026-08-18) — the RANKING terms only. The card still
            stamps the real full-package `fairness`, and every gate ran on
            the real package."""
            composite = (W_MIS * min(hm, GAIN_CAP) / GAIN_CAP
                         * mismatch_damp(give_ids + recv_ids, seed_value,
                                         confidence)
                         + W_FAIR * rank_fairness(fairness, give_ids, recv_ids,
                                                  seed_value, _uv, _vo))
            composite *= self._tier_mult_v2(shrunk_user_elo, give_ids + recv_ids)
            # Backlog #2 — reward cards that LAND a target on the receive side.
            # Applied after the mutual-gain gates (a target never rescues a
            # non-mutual-gain trade), capped by pos_multiplier_cap.
            if target_ids:
                n_t = len(set(recv_ids) & target_ids)
                if n_t:
                    composite *= min(1.0 + TARGET_BONUS * n_t, MULT_CAP)
            return composite

        def _consider(give_ids: list[str], recv_ids: list[str]) -> None:
            if pinned_set:
                if pinned_all:
                    if not pinned_set <= set(give_ids):
                        return
                elif not (set(give_ids) & pinned_set):
                    return
            if pinned_recv_set and not (set(recv_ids) & pinned_recv_set):
                return
            if not _positions_ok(give_ids, recv_ids):
                return
            if not _gap_ok(give_ids, recv_ids):
                return
            # #108 — never offer a 1-for-1 that sends a player the user
            # ranks above the received player on their own raw board (the
            # shrunk surplus below can be inverted by consensus pull).
            # Phase 2 exception (flag trade.fit_premium): a small raw-board
            # loss that fills a positional need survives, flagged with the
            # price paid.
            _allowed, _fit_paid = fit_premium_1for1(
                give_ids, recv_ids, raw_user_elo, players, user_needs)
            if not _allowed:
                return
            # #227 — a 1-for-1 pick-for-pick swap is pointless churn
            # (picks carry zero divergence by construction).
            if not pick_swap_ok(give_ids, recv_ids, players, seed_value):
                return
            # #141 — junk-filler gate: any piece beyond a side's headliner
            # must clear filler_min_frac of that headliner on the MAX of
            # the two raw boards. Junk both sides value low never pads a
            # package; headliners are exempt (1-for-1 shapes untouched).
            if not filler_ok(give_ids, recv_ids, _uv, _vo):
                return
            # G6 presentment rules (R1 #340 / R2 #341 / R3 #339 / R5 #304)
            # — construction-time kill so the heap refills with sane
            # candidates. Same slot as v3 (after filler_ok, before the
            # surplus/fairness math). None ⇒ flag off, byte-identical.
            if presentment_ok_fn is not None \
                    and not presentment_ok_fn(give_ids, recv_ids):
                return

            user_surplus, opp_surplus = _pair_surpluses(give_ids, recv_ids)
            # True mutual gain (Change 3): BOTH sides must clear the bar.
            if user_surplus < MIN_SIDE or opp_surplus < MIN_SIDE:
                return

            fairness = _fairness(give_ids, recv_ids)
            if fairness is None:
                return

            hm = _harmonic_mean(user_surplus, opp_surplus)   # A1 ranking
            composite = _composite_v2(hm, fairness, give_ids, recv_ids)
            _offer(composite, hm, fairness, give_ids, recv_ids, _fit_paid)

        # ------------------------------------------------------------------
        # Candidate pools — same prune idea as legacy but in value space and
        # direction-correct: gives the opponent over-values, receives the
        # user over-values. Anchor-first pre-sort (Change 5) visits the
        # highest-divergence players first so the deadline loses little.
        # ------------------------------------------------------------------
        # Backlog #2 — untouchables never leave the user's roster: drop them
        # from the give pool at the source, so they can't appear in any single
        # or multi-give combo.
        _known_user = [p for p in user_roster
                       if p in shrunk_user_elo and p in opp_elo
                       and not (untouchable_ids and p in untouchable_ids)]
        # #163 — not-interested players never enter the receive pool (dropped
        # at the source, so no combo — nor the pinned/target re-adds below,
        # which iterate this filtered list — can offer them to the user).
        # #360 — avoided POSITIONS are dropped at the same source, so an
        # exclusion always wins over a pin (PRD R-8 / D-360-3(b)).
        _avoid = set(avoid_positions or ())
        _known_opp  = [p for p in opponent.roster
                       if p in shrunk_user_elo and p in opp_elo
                       and not (not_interested_ids and p in not_interested_ids)
                       and avoid_ok(p, self._players, _avoid)]
        _PRUNE_MIN_SIZE = 5
        _give = [p for p in _known_user if _vo(p) >= user_value[p] * 0.97]
        _recv = [p for p in _known_opp if user_value[p] >= _vo(p) * 0.97]
        give_candidates = _give if len(_give) >= _PRUNE_MIN_SIZE else list(_known_user)
        recv_candidates = _recv if len(_recv) >= _PRUNE_MIN_SIZE else list(_known_opp)
        # FB-47 — pinned acquire targets must survive the divergence prune,
        # mirroring how pinned give players are always kept in the optimizer.
        if pinned_recv_set:
            for pid in _known_opp:
                if pid in pinned_recv_set and pid not in recv_candidates:
                    recv_candidates.append(pid)
        # Backlog #2 — targets the opponent rosters survive the prune too, so a
        # coveted player is always offered when this opponent holds him.
        if target_ids:
            for pid in _known_opp:
                if pid in target_ids and pid not in recv_candidates:
                    recv_candidates.append(pid)
        # #174 — package mode: every pinned give player must be a candidate
        # or no combo can contain them all. Mirrors the optimizer's
        # always-keep rule; gated to 'all' so default-mode decks stay
        # byte-identical to the pre-#174 prune.
        if pinned_all:
            for pid in _known_user:
                if pid in pinned_set and pid not in give_candidates:
                    give_candidates.append(pid)
        give_candidates.sort(key=lambda p: _vo(p) - user_value[p], reverse=True)
        recv_candidates.sort(key=lambda p: user_value[p] - _vo(p), reverse=True)

        # 1-for-1
        for give_id in give_candidates:
            if time.monotonic() > _deadline:
                break
            for recv_id in recv_candidates:
                _iters += 1
                _consider([give_id], [recv_id])

        # 2-for-1 (user gives 2, receives 1)
        _budget_exceeded = _iters > _iter_budget
        if not _budget_exceeded:
            for recv_id in recv_candidates:
                if _budget_exceeded or time.monotonic() > _deadline:
                    break
                for g1, g2 in combinations(give_candidates, 2):
                    _iters += 1
                    if _iters > _iter_budget:
                        _budget_exceeded = True
                        break
                    _consider([g1, g2], [recv_id])

        # 1-for-2 (user gives 1, receives 2)
        if not _budget_exceeded:
            for give_id in give_candidates:
                if _budget_exceeded or time.monotonic() > _deadline:
                    break
                for r1, r2 in combinations(recv_candidates, 2):
                    _iters += 1
                    if _iters > _iter_budget:
                        _budget_exceeded = True
                        break
                    _consider([give_id], [r1, r2])

        # 3-for-2 (user gives 3, receives 2)
        if not _budget_exceeded:
            for r1, r2 in combinations(recv_candidates, 2):
                if _budget_exceeded or time.monotonic() > _deadline:
                    break
                for g1, g2, g3 in combinations(give_candidates, 3):
                    _iters += 1
                    if _iters > _iter_budget:
                        _budget_exceeded = True
                        break
                    _consider([g1, g2, g3], [r1, r2])

        # NOTE: no qb_tax / star_tax / roster_clogger in the v2 path — the
        # clogger phenomenon is handled by package_value_v2 diminishing
        # returns + the waiver-slot cost; QB/star reconciliation is Tier 2.
        ranked = sorted(heap, key=lambda e: (e[0], e[1], e[2]), reverse=True)
        # Consensus package values for the TradeValueBar — same fn + value
        # space the manual calculator uses, so a deck card and the calculator
        # show identical numbers for the same players. Lazy import: the
        # optimizer imports this module (top-level would cycle).
        from .trade_optimizer import _consensus_packages, close_value_gap

        # 2026-08-21 gap auto-sweetener (sweetener_gap_threshold): a selected
        # card whose absolute consensus gap exceeds the threshold is
        # re-balanced by adding the smallest sufficient equalizer from the
        # richer side's roster — re-earning this path's own gates via
        # `_gap_extra_ok` (junk filler, pick swap, presentment, Elo-gap
        # guard, both-sides surplus) plus lineup feasibility inside the
        # helper. An unclosable card is kept unsweetened: this pass narrows
        # gaps, it never shrinks the deck. ≤ 0 disables (arm A's pin).
        _GAP_THR = _c("sweetener_gap_threshold")

        def _gap_extra_ok(g: list[str], r: list[str]) -> bool:
            if not filler_ok(g, r, _uv, _vo):
                return False
            if not pick_swap_ok(g, r, players, seed_value):
                return False
            if presentment_ok_fn is not None \
                    and not presentment_ok_fn(g, r):
                return False
            if not _gap_ok(g, r):
                return False
            u_s, o_s = _pair_surpluses(g, r)
            return u_s >= MIN_SIDE and o_s >= MIN_SIDE

        cards: list[TradeCard] = []
        _picked_keys = {(frozenset(e[5]), frozenset(e[6]))
                        for e in ranked[:max_cards]}
        for composite, _sz, _t, hm, fairness, give_ids, recv_ids, fit_paid \
                in ranked[:max_cards]:
            _gap_info = None
            if _GAP_THR > 0:
                closed = close_value_gap(
                    give_ids, recv_ids, seed_value=seed_value,
                    gap_threshold=_GAP_THR,
                    fairness_threshold=fairness_threshold,
                    user_roster=user_roster, opp_roster=opponent.roster,
                    players=players, scoring_format=scoring_format,
                    untouchable_ids=untouchable_ids,
                    not_interested_ids=not_interested_ids,
                    extra_ok_fn=_gap_extra_ok)
                if closed is not None:
                    s_pid, side, new_give, new_recv, _ngv, _nrv, n_ratio \
                        = closed
                    new_key = (frozenset(new_give), frozenset(new_recv))
                    if new_key not in _picked_keys:
                        _gv0, _rv0 = _consensus_packages(
                            give_ids, recv_ids, seed_value)
                        _gap_info = {
                            "player_id": s_pid, "side": side,
                            "gap_before": round(abs(_gv0 - _rv0), 1),
                            "gap_after": round(abs(_ngv - _nrv), 1),
                        }
                        _picked_keys.discard(
                            (frozenset(give_ids), frozenset(recv_ids)))
                        _picked_keys.add(new_key)
                        give_ids, recv_ids = new_give, new_recv
                        fairness = n_ratio
                        u_s, o_s = _pair_surpluses(give_ids, recv_ids)
                        hm = _harmonic_mean(u_s, o_s)
                        composite = _composite_v2(hm, fairness, give_ids,
                                                  recv_ids)
                        if fit_paid is not None:
                            fit_paid = None   # no longer a 1-for-1 shape
            _gv, _rv = _consensus_packages(give_ids, recv_ids, seed_value)
            card = TradeCard(
                trade_id          = str(uuid.uuid4())[:8],
                league_id         = league_id,
                proposing_user_id = user_id,
                target_user_id    = opponent.user_id,
                target_username   = opponent.username,
                give_player_ids   = give_ids,
                receive_player_ids= recv_ids,
                mismatch_score    = round(hm, 1),
                fairness_score    = round(fairness, 3),
                composite_score   = round(composite, 3),
                basis             = "divergence",
                give_value        = round(_gv, 1),
                receive_value     = round(_rv, 1),
            )
            if fit_paid is not None:
                p = players.get(recv_ids[0])
                card.fit_premium = {
                    "value_paid": fit_paid,
                    "position": getattr(p, "position", None) if p else None,
                }
            if _gap_info is not None:
                card.gap_sweetener = _gap_info
            cards.append(card)
        return cards

    def _generate_consensus_for_pair(
        self,
        *,
        user_id: str,
        opponent: LeagueMember,
        league_id: str,
        seed_value,                          # callable pid → consensus value
        shrunk_user_elo: dict[str, float],
        user_roster: list[str],
        max_cards: int,
        fairness_threshold: float,
        user_profile: dict,
        opp_profile: dict,
        acquire_positions: list[str],
        trade_away_positions: list[str],
        avoid_positions: list[str] | None = None,      # #360
        pinned_give_players: list[str] | None,
        pinned_receive_players: list[str] | None = None,
        pinned_give_mode: str = "any",
        untouchable_ids: set | None = None,
        target_ids: set | None = None,
        not_interested_ids: set | None = None,
        raw_user_elo: dict[str, float] | None = None,
        presentment_ok_fn=None,              # G6 rules R1/R2/R3/R5; None = off
        scoring_format: str = "1qb_ppr",     # gap-sweetener lineup feasibility
    ) -> list[TradeCard]:
        """Consensus-basis fallback cards for an opponent with NO rankings.

        Divergence math against fabricated elo_ratings is meaningless noise,
        so instead surface simple, fair-by-consensus 1-for-1 / 2-for-1 ideas
        oriented around roster fit: the user receives a needed position and
        gives from positions the opponent needs where possible. Scored by
        fairness × tier multiplier only (no divergence term) and labeled
        basis="consensus". A deliberately simple, labeled fallback.
        """
        players    = self._players
        pinned_set = set(pinned_give_players) if pinned_give_players else None
        # #174 — "all" ⇒ every pinned give player must be in the give side.
        pinned_all = pinned_set is not None and pinned_give_mode == "all"
        # D-095 — the landability challenger's two consensus knobs. This path
        # is 84.5% of served cards and the only one that never sees a partner
        # board, so it is where the viewer-wins identity actually lives.
        #
        # `consensus_both_ways` drops the one-way sign test below and opens
        # 1-for-2; `consensus_fairness_floor` raises the bar via max(), so it
        # can only tighten. They travel together on purpose: opening both
        # directions at the live 0.50 floor is a 2:1 user-pays flood, while at
        # 0.75 the worst either side can be out is exactly 1 - 0.75 = 25%.
        # Both at their live defaults (0.0) ⇒ this generator is byte-identical.
        _both_ways = _c("consensus_both_ways") >= 1.0
        _floor = _c("consensus_fairness_floor")
        _thr = max(fairness_threshold, _floor) if _floor > 0 \
            else fairness_threshold

        def _pos(pid: str) -> Optional[str]:
            p = players.get(pid)
            return getattr(p, "position", None) if p else None

        def _uval_raw(pid: str) -> float:
            """#141 — user raw-board value where the board knows the
            player, else consensus (the opponent has no board here, so
            consensus stands in for their arm of the max rule too)."""
            e = raw_user_elo.get(pid) if raw_user_elo else None
            return elo_to_value(e) if e is not None else seed_value(pid)

        # Explicit user preferences win; otherwise fall back to the roster
        # profiles already computed by generate_trades.
        need_positions = list(acquire_positions) or list(user_profile.get("position_needs", []))
        shed_positions = list(trade_away_positions) or list(opp_profile.get("position_needs", []))

        # #163 — not-interested players never enter the receive pool (filtered
        # at the source; the target re-add below iterates this filtered list
        # too, so an exclusion always wins).
        # #360 — avoided POSITIONS ride the same rule, at the same source.
        _avoid = set(avoid_positions or ())
        _opp_pool = [p for p in opponent.roster
                     if not (not_interested_ids and p in not_interested_ids)
                     and avoid_ok(p, players, _avoid)]
        recv_pool = list(_opp_pool)
        # FB-47 — player-level acquire targets dominate: restrict the receive
        # pool to the pinned players this opponent actually rosters. (When
        # they roster none, no cards — correct: the pin names specific
        # players, not a position.)
        pinned_recv_set = (set(pinned_receive_players)
                           if pinned_receive_players else None)
        if pinned_recv_set:
            recv_pool = [p for p in recv_pool if p in pinned_recv_set]
        elif need_positions:
            recv_pool = [p for p in recv_pool if _pos(p) in need_positions]
        # Backlog #2 — targets the opponent rosters survive the need-position
        # filter, so a coveted player is offered even off-need.
        if target_ids:
            for pid in _opp_pool:
                if pid in target_ids and pid not in recv_pool:
                    recv_pool.append(pid)

        # 2026-09-02 roster-fit SORT KEY (`consensus_fit_weight`, see the
        # _DEFAULT_CFG block). The emit loops below take pool order as the
        # ranking, so this is where fit enters — as a blend on the value
        # key, never as a prune or a gate. Read via `_c` at CALL time
        # (D-098 / G-058 cause 3; the `_cfg_override` overlay is how arm A's
        # pin and the #189 relaxed pass reach it). No partner board exists
        # on this path, so BOTH replacement levels come from the rosters at
        # consensus prices. At w = 0 the factory hands back `seed_value`
        # itself, so the sort keys are the historical ones, byte-identical.
        _w_fit = _c("consensus_fit_weight")
        _fit_norm: dict[str, float] = {}

        def _fit_sort_key(pool: list[str], sign: float):
            if _w_fit <= 0:
                return seed_value
            u_repl = replacement_levels(user_roster, seed_value, players,
                                        scoring_format)
            o_repl = replacement_levels(opponent.roster, seed_value, players,
                                        scoring_format)
            raw: dict[str, float] = {}
            for p in pool:
                # Picks have no lineup slot: neutral, so their order among
                # themselves is unchanged.
                if is_pick_asset(players.get(p)):
                    raw[p] = 0.0
                    continue
                # + = worth more in the partner's lineup than in ours
                # (give side); `sign` = -1 flips it for the receive side.
                raw[p] = sign * (
                    marginal_value(p, seed_value, o_repl, players,
                                   scoring_format)
                    - marginal_value(p, seed_value, u_repl, players,
                                     scoring_format))
            m = max((abs(v) for v in raw.values()), default=0.0)
            for p, v in raw.items():
                _fit_norm[p] = (v / m) if m > 0 else 0.0
            return lambda p: seed_value(p) * (1.0 + _w_fit * _fit_norm[p])

        recv_pool.sort(key=_fit_sort_key(recv_pool, -1.0), reverse=True)

        give_pool = list(user_roster)
        # Backlog #2 — untouchables are never given away, consensus path too.
        if untouchable_ids:
            give_pool = [p for p in give_pool if p not in untouchable_ids]
        if pinned_set:
            give_pool = [p for p in give_pool if p in pinned_set]
        # "Where possible": positions the opponent needs first, best value first.
        _give_key = _fit_sort_key(give_pool, +1.0)
        give_pool.sort(key=lambda p: (_pos(p) in shed_positions, _give_key(p)),
                       reverse=True)

        cards: list[TradeCard] = []
        seen: set[tuple] = set()

        # 2026-08-21 gap auto-sweetener (sweetener_gap_threshold). Lazy
        # import — the optimizer imports this module (top-level would
        # cycle). `_gap_gates_ok` re-earns THIS path's gate stack for a
        # sweetened combo; the helper itself checks gap, fairness band and
        # lineup feasibility. ≤ 0 disables (arm A's pin).
        _GAP_THR = _c("sweetener_gap_threshold")
        from .trade_optimizer import close_value_gap as _close_gap

        def _gap_gates_ok(g: list[str], r: list[str]) -> bool:
            gvals2 = [seed_value(p) for p in g]
            rvals2 = [seed_value(p) for p in r]
            v_max2 = max(gvals2 + rvals2)
            gv2 = package_value_v2(gvals2, v_max2, n_other=len(r),
                                   other_values=rvals2)
            rv2 = package_value_v2(rvals2, v_max2, n_other=len(g),
                                   other_values=gvals2)
            if gv2 <= 0 or rv2 <= 0:
                return False
            if not _both_ways and rv2 - gv2 < _c("user_gain_epsilon"):
                return False
            _f2 = _c("consolidation_raw_loss_frac")
            if _f2 > 0 and len(g) > len(r):
                raw_g = sum(gvals2)
                if raw_g - sum(rvals2) > _f2 * raw_g:
                    return False
            if not user_gain_ok_1for1(g, r, raw_user_elo):
                return False
            if not pick_swap_ok(g, r, players, seed_value):
                return False
            if not filler_ok(g, r, _uval_raw, seed_value):
                return False
            if presentment_ok_fn is not None and not presentment_ok_fn(g, r):
                return False
            return True

        def _emit(give_ids: list[str], recv_ids: list[str]) -> None:
            # #174 package mode — the give pool is already restricted to
            # pinned players; 'all' additionally requires the FULL set in
            # every card (so 1-for-1 shapes drop out when 2+ are pinned).
            if pinned_all and not pinned_set <= set(give_ids):
                return
            key = (frozenset(give_ids), frozenset(recv_ids))
            if key in seen:
                return
            gvals = [seed_value(p) for p in give_ids]
            rvals = [seed_value(p) for p in recv_ids]
            v_max = max(gvals + rvals)
            gv = package_value_v2(gvals, v_max, n_other=len(recv_ids),
                                  other_values=rvals)
            rv = package_value_v2(rvals, v_max, n_other=len(give_ids),
                                  other_values=gvals)
            if gv <= 0 or rv <= 0:
                return
            # #108 — on a consensus card the user's board IS consensus:
            # the user's side must come out ahead (receive − give ≥ ε).
            # Fairness alone allowed the user to be the side paying up to
            # (1 − threshold) more consensus value (TC-CFG-001 gap).
            #
            # D-095 — this single line IS the viewer-wins identity on 84.5%
            # of the deck, and `consensus_both_ways` is what removes it. With
            # it off the card must favour the user; with it on the card need
            # only be FAIR, in either direction, and `_thr` (>= 0.75 under the
            # challenger profile) is what stops that becoming a fleece in the
            # other direction. Note the two sides are priced by the same
            # `seed_value` functional, so user surplus and partner surplus are
            # exact negatives — a symmetric epsilon > 0 is unsatisfiable and
            # is deliberately NOT what this does.
            if not _both_ways and rv - gv < _c("user_gain_epsilon"):
                return
            # Deck-eval 2026-07-17 — the adjusted delta above can flip
            # positive on a consensus-lopsided consolidation (gamma depth
            # discount guts the second give asset, crown premium inflates
            # the received stud), so user-give-side consolidations must
            # ALSO keep their RAW consensus loss within
            # consolidation_raw_loss_frac of the raw give total.
            _frac = _c("consolidation_raw_loss_frac")
            if _frac > 0 and len(give_ids) > len(recv_ids):
                raw_give = sum(gvals)
                if raw_give - sum(rvals) > _frac * raw_give:
                    return
            # #108 — and when the user DOES have both players on their own
            # raw board, a 1-for-1 must respect that ordering too.
            if not user_gain_ok_1for1(give_ids, recv_ids, raw_user_elo):
                return
            # #227 — a 1-for-1 pick-for-pick swap is pointless churn.
            if not pick_swap_ok(give_ids, recv_ids, players, seed_value):
                return
            # #141 — junk-filler gate (2-for-1 shape): the added give piece
            # must clear filler_min_frac of the side's headliner on
            # max(user raw board, consensus).
            if not filler_ok(give_ids, recv_ids, _uval_raw, seed_value):
                return
            # G6 presentment rules — same construction-time slot as the
            # divergence paths (with the #108/#227/#141 gate block).
            if presentment_ok_fn is not None \
                    and not presentment_ok_fn(give_ids, recv_ids):
                return
            fairness = min(gv, rv) / max(gv, rv)
            if fairness < _thr:
                return
            seen.add(key)
            # 2026-08-21 gap auto-sweetener: this card passed every gate,
            # but the ratio gate is scale-blind — close an absolute gap
            # above the threshold by adding the smallest sufficient
            # equalizer from the richer side's roster. An unclosable card
            # is emitted as-is (the pass narrows gaps, never shrinks the
            # deck).
            _gap_info = None
            if _GAP_THR > 0 and abs(gv - rv) > _GAP_THR:
                closed = _close_gap(
                    give_ids, recv_ids, seed_value=seed_value,
                    gap_threshold=_GAP_THR, fairness_threshold=_thr,
                    user_roster=user_roster,
                    opp_roster=opponent.roster,
                    players=players, scoring_format=scoring_format,
                    untouchable_ids=untouchable_ids,
                    not_interested_ids=not_interested_ids,
                    # Round-2 review 2026-08-21: this path PRUNES its pools
                    # (#174 pinned give players, FB-47 pinned acquire
                    # targets, need-position receive filter) instead of
                    # gating per combo, so the equalizer must come from the
                    # SAME pools — otherwise a pinned "trade away G" job
                    # could hand the user a card that also ships an
                    # unpinned player, and an "acquire RB" job could hand
                    # back an off-need receive asset. The full rosters
                    # above still drive the 3.2 feasibility counts.
                    give_candidates=give_pool,
                    recv_candidates=recv_pool,
                    extra_ok_fn=_gap_gates_ok)
                if closed is not None:
                    s_pid, side, n_give, n_recv, n_gv, n_rv, n_ratio = closed
                    n_key = (frozenset(n_give), frozenset(n_recv))
                    if n_key not in seen:
                        _gap_info = {
                            "player_id": s_pid, "side": side,
                            "gap_before": round(abs(gv - rv), 1),
                            "gap_after": round(abs(n_gv - n_rv), 1),
                        }
                        seen.add(n_key)
                        give_ids, recv_ids = n_give, n_recv
                        gv, rv, fairness = n_gv, n_rv, n_ratio
            # consensus_score_scale keeps fallback cards (no divergence
            # signal, mismatch 0) from outranking genuine divergence finds —
            # the two composites would otherwise live on different scales
            # (fairness×tier ≈ 1.6 vs surplus-blend ≈ 0.3–0.7).
            composite = (fairness * self._tier_mult_v2(shrunk_user_elo, give_ids + recv_ids)
                         * _c("consensus_score_scale"))
            card = TradeCard(
                trade_id          = str(uuid.uuid4())[:8],
                league_id         = league_id,
                proposing_user_id = user_id,
                target_user_id    = opponent.user_id,
                target_username   = opponent.username,
                give_player_ids   = give_ids,
                receive_player_ids= recv_ids,
                mismatch_score    = 0.0,     # no divergence signal by construction
                fairness_score    = round(fairness, 3),
                composite_score   = round(composite, 3),
                basis             = "consensus",
                # gv/rv above are the consensus package values (same fn +
                # value space as the calculator) — drive the TradeValueBar.
                give_value        = round(gv, 1),
                receive_value     = round(rv, 1),
            )
            if _gap_info is not None:
                card.gap_sweetener = _gap_info
            # Roster-fit stamp — ONLY while the knob is live, so the knob-0
            # card is byte-identical. `.get` because a gap-sweetener
            # equalizer is drawn from the same pools and so is always
            # present; the default is belt-and-braces, not a code path.
            if _w_fit > 0:
                _fits = [_fit_norm.get(p, 0.0) for p in give_ids + recv_ids]
                card.consensus_fit = round(sum(_fits) / len(_fits), 3)
            cards.append(card)

        # 1-for-1 first (most acceptable shape), then 2-for-1.
        for recv_id in recv_pool:
            if len(cards) >= max_cards:
                break
            for give_id in give_pool:
                if len(cards) >= max_cards:
                    break
                _emit([give_id], [recv_id])
        if len(cards) < max_cards:
            for recv_id in recv_pool:
                if len(cards) >= max_cards:
                    break
                for g1, g2 in combinations(give_pool, 2):
                    if len(cards) >= max_cards:
                        break
                    _emit([g1, g2], [recv_id])
        # D-095 — 1-for-2, the mirror of the 2-for-1 above. Only reachable
        # under `consensus_both_ways`: the shape the user RECEIVES two for one
        # is a consolidation in the PARTNER's favour, so every one of them
        # died on the `rv >= gv` sign test that the knob removes. Production
        # holds 6,635 `1x1` and 459 `2x1` packages and exactly zero `1x2` —
        # partner-favourable consolidation is currently unrepresentable, not
        # merely rare. Enumerated last so it can only use budget the existing
        # shapes left, which keeps the shape mix stable when the deck is full.
        if _both_ways and len(cards) < max_cards:
            for give_id in give_pool:
                if len(cards) >= max_cards:
                    break
                for r1, r2 in combinations(recv_pool, 2):
                    if len(cards) >= max_cards:
                        break
                    _emit([give_id], [r1, r2])
        return cards

    def get_pending_trades(self, user_id: str, league_id: Optional[str] = None) -> list[TradeCard]:
        """Return undecided trade cards for a user, newest first."""
        cards = [
            c for c in self._trade_cards.values()
            if c.proposing_user_id == user_id
            and c.decision is None
            and (league_id is None or c.league_id == league_id)
            and (frozenset(c.give_player_ids), frozenset(c.receive_player_ids))
                not in self._past_decision_keys
        ]
        return sorted(cards, key=lambda c: c.composite_score, reverse=True)

    def record_decision(self, trade_id: str, decision: str) -> TradeCard:
        """Record 'like' or 'pass' on a trade card."""
        if trade_id not in self._trade_cards:
            raise ValueError(f"Unknown trade_id: {trade_id!r}")
        if decision not in ("like", "pass"):
            raise ValueError("decision must be 'like' or 'pass'")
        self._trade_cards[trade_id].decision = decision
        return self._trade_cards[trade_id]

    def get_liked_trades(self, user_id: str) -> list[TradeCard]:
        return [
            c for c in self._trade_cards.values()
            if c.proposing_user_id == user_id and c.decision == "like"
        ]

    # ------------------------------------------------------------------
    # Core algorithm
    # ------------------------------------------------------------------

    def _generate_for_pair(
        self,
        user_id: str,
        user_elo: dict[str, float],
        user_roster: list[str],
        opponent: LeagueMember,
        league_id: str,
        seed_elo: dict[str, float],
        max_cards: int,
        fairness_threshold: float = 0.75,
        acquire_positions: list[str] | None = None,
        trade_away_positions: list[str] | None = None,
        pinned_give_players: list[str] | None = None,
        prune_candidates: bool = True,
    ) -> list[TradeCard]:

        opp_elo    = opponent.elo_ratings
        opp_roster = opponent.roster
        players    = self._players
        pinned_set = set(pinned_give_players) if pinned_give_players else None

        # Time budget: bail out of expensive combination loops after 1s
        # per opponent. Was 3s; combined with max_candidates=30 (was 500),
        # opponents that won't yield candidates exit much faster. 11
        # opponents × 1s worst case ≈ 11s total wall clock, vs the 33s
        # we were burning before — pre-gen now actually beats the user
        # to the Trades page in the common cold-cache flow.
        _deadline  = time.monotonic() + 1.0
        _iter_budget = 200_000  # max iterations across multi-player sections
        _iters     = 0

        # ------------------------------------------------------------------
        # Helpers
        # ------------------------------------------------------------------

        # Memoize per-pair _dv lookups. Without this, dynasty_value(p) is
        # recomputed for every (give, recv) combination — same player IDs
        # appear in tens of thousands of combinations per opponent. The
        # cache is local to each opponent so it doesn't outlive the call.
        _dv_cache: dict[str, float] = {}
        _ktc_fallback_dv = dynasty_value(None, rank_override=int(_c("ktc_fallback_rank")))

        def _dv(pid: str) -> float:
            """Dynasty value for a player by ID (KTC-style)."""
            v = _dv_cache.get(pid)
            if v is not None:
                return v
            p = players.get(pid)
            v = _ktc_fallback_dv if p is None else dynasty_value(p)
            _dv_cache[pid] = v
            return v

        # Tier-priority multiplier. Applied to composite_score so trades
        # involving higher-tier players (Elite, Starter) outrank trades
        # composed of Depth/Bench scraps — even when the depth-vs-depth
        # mismatch math is "better" on paper. Tiers are derived from the
        # USER's personal ELO (so it reflects how the user values the
        # players, not the consensus). Thresholds mirror the uniform
        # tier bands in backend/ranking_service.py:bucket_for. Picks the
        # MAX tier across both sides — if a trade involves any one
        # Elite-tier player, the whole trade gets the Elite multiplier.
        _MULT_ELITE   = _c("tier_mult_elite")
        _MULT_STARTER = _c("tier_mult_starter")
        _MULT_SOLID   = _c("tier_mult_solid")
        _MULT_DEPTH   = _c("tier_mult_depth")
        _MULT_BENCH   = _c("tier_mult_bench")
        def _tier_mult_for_pids(pids):
            best = _MULT_BENCH
            for pid in pids:
                e = user_elo.get(pid, 1500)
                if   e >= 1700: m = _MULT_ELITE
                elif e >= 1580: m = _MULT_STARTER
                elif e >= 1460: m = _MULT_SOLID
                elif e >= 1350: m = _MULT_DEPTH
                else:           m = _MULT_BENCH
                if m > best: best = m
            return best

        def _ktc_ok(give_ids: list[str], recv_ids: list[str]) -> bool:
            """
            Return True if the KTC package values satisfy fairness_threshold.
            i.e. lesser_package / greater_package >= fairness_threshold
            """
            give_val = package_value([_dv(pid) for pid in give_ids])
            recv_val = package_value([_dv(pid) for pid in recv_ids])
            if give_val == 0 and recv_val == 0:
                return True
            greater = max(give_val, recv_val)
            lesser  = min(give_val, recv_val)
            return (lesser / greater) >= fairness_threshold

        def _elo_gap_ok(give_ids: list[str], recv_ids: list[str]) -> bool:
            """
            Return True if the user's personal ELO gap between the best player
            on each side is within the configured max.  Catches ridiculous trades
            where consensus values are similar but the user's rankings diverge
            (e.g. Charbonnet 1289 for Jeanty 1665).
            """
            max_gap = _c("trade_elo_gap_max")
            if max_gap <= 0:
                return True  # disabled
            give_elos = [user_elo.get(pid, 1500) for pid in give_ids]
            recv_elos = [user_elo.get(pid, 1500) for pid in recv_ids]
            max_give = max(give_elos) if give_elos else 1500
            max_recv = max(recv_elos) if recv_elos else 1500
            return abs(max_recv - max_give) <= max_gap

        # (composite, mismatch, fairness, give_ids, recv_ids)
        candidates: list[tuple[float, float, float, list[str], list[str]]] = []

        # ------------------------------------------------------------------
        # Pre-prune: restrict iteration space to players whose ELO divergence
        # creates a give-side surplus for the opponent (give_candidates) or a
        # receive-side surplus for the user (recv_candidates).  This mirrors
        # the condition _mismatch_score must see > 0.
        #
        # Threshold 0.97 (slightly below 1.0) ensures equal-ELO boundary
        # players are INCLUDED rather than dropped (AC-4).
        #
        # Fallback: if either pruned set is too small (< 5 players) we use the
        # full roster for that side so new users with all-ELO-at-1500 still get
        # trade cards (AC-5).
        # ------------------------------------------------------------------
        _PRUNE_THRESHOLD = 0.97
        _PRUNE_MIN_SIZE  = 5

        if prune_candidates:
            _give_cands = [
                pid for pid in user_roster
                if pid in user_elo and pid in opp_elo
                and opp_elo[pid] >= user_elo[pid] * _PRUNE_THRESHOLD
            ]
            _recv_cands = [
                pid for pid in opp_roster
                if pid in user_elo and pid in opp_elo
                and opp_elo[pid] >= user_elo[pid] * _PRUNE_THRESHOLD
            ]
            # Fallback: if the pruned set is too thin (e.g. all-1500 new user)
            # use the full roster so we still surface trade cards.
            give_candidates = (
                _give_cands if len(_give_cands) >= _PRUNE_MIN_SIZE else user_roster
            )
            recv_candidates = (
                _recv_cands if len(_recv_cands) >= _PRUNE_MIN_SIZE else opp_roster
            )
        else:
            give_candidates = user_roster
            recv_candidates = opp_roster

        # ------------------------------------------------------------------
        # 1-for-1 trades
        # ------------------------------------------------------------------
        for give_id in give_candidates:
            if give_id not in user_elo or give_id not in opp_elo:
                continue
            # When pinned players specified, only consider those as give candidates
            if pinned_set and give_id not in pinned_set:
                continue
            for recv_id in recv_candidates:
                if recv_id not in user_elo or recv_id not in opp_elo:
                    continue

                # KTC fairness gate (replaces old MAX_VALUE_RATIO check)
                if not _ktc_ok([give_id], [recv_id]):
                    continue
                # User-ELO gap gate — catches ridiculous trades where consensus
                # is similar but user's personal rankings strongly diverge
                if not _elo_gap_ok([give_id], [recv_id]):
                    continue

                mismatch = self._mismatch_score(give_id, recv_id, user_elo, opp_elo)
                if mismatch <= 0:
                    continue

                fairness = self._fairness_score([give_id], [recv_id], seed_elo)
                composite = (_c("mismatch_weight") * min(mismatch, 300) / 300 +
                             _c("fairness_weight") * fairness)
                composite *= _tier_mult_for_pids([give_id, recv_id])
                candidates.append((composite, mismatch, fairness, [give_id], [recv_id]))

                if len(candidates) >= int(_c("max_candidates")):
                    break
            if len(candidates) >= int(_c("max_candidates")):
                break

        # ------------------------------------------------------------------
        # 2-for-1 trades (user gives 2, receives 1 elite player)
        # ------------------------------------------------------------------
        _budget_exceeded = False
        if len(candidates) < int(_c("max_candidates")):
            for recv_id in recv_candidates:
                if _budget_exceeded or time.monotonic() > _deadline:
                    break
                if recv_id not in user_elo or recv_id not in opp_elo:
                    continue
                recv_dv = _dv(recv_id)

                for give_id_1, give_id_2 in combinations(give_candidates, 2):
                    _iters += 1
                    if _iters > _iter_budget:
                        _budget_exceeded = True
                        break
                    if give_id_1 not in user_elo or give_id_2 not in user_elo:
                        continue
                    # At least one of the give players must be pinned
                    if pinned_set and not ({give_id_1, give_id_2} & pinned_set):
                        continue

                    # Quick KTC pre-filter before expensive ELO math
                    if not _ktc_ok([give_id_1, give_id_2], [recv_id]):
                        continue
                    if not _elo_gap_ok([give_id_1, give_id_2], [recv_id]):
                        continue

                    combined_give_user = user_elo.get(give_id_1, 1500) + user_elo.get(give_id_2, 1500)
                    combined_give_opp  = opp_elo.get(give_id_1, 1500) + opp_elo.get(give_id_2, 1500)
                    recv_user = user_elo.get(recv_id, 1500)
                    recv_opp  = opp_elo.get(recv_id, 1500)

                    # User values the single player more than the combined pair
                    if recv_user <= combined_give_user * 0.95:
                        continue
                    # Opponent values the pair more than the single player
                    if combined_give_opp <= recv_opp * 0.95:
                        continue

                    mismatch = (recv_user - combined_give_user) + (combined_give_opp - recv_opp)
                    if mismatch <= 0:
                        continue

                    fairness = self._fairness_score([give_id_1, give_id_2], [recv_id], seed_elo)
                    composite = (_c("mismatch_weight") * min(mismatch, 400) / 400 +
                                 _c("fairness_weight") * fairness)
                    composite *= _tier_mult_for_pids([give_id_1, give_id_2, recv_id])
                    candidates.append((composite, mismatch, fairness, [give_id_1, give_id_2], [recv_id]))

                    if len(candidates) >= int(_c("max_candidates")):
                        break
                if len(candidates) >= int(_c("max_candidates")):
                    break

        # ------------------------------------------------------------------
        # 1-for-2 trades (user gives 1 elite, receives 2)
        # ------------------------------------------------------------------
        if len(candidates) < int(_c("max_candidates")) and not _budget_exceeded:
            for give_id in give_candidates:
                if _budget_exceeded or time.monotonic() > _deadline:
                    break
                if give_id not in user_elo or give_id not in opp_elo:
                    continue
                if pinned_set and give_id not in pinned_set:
                    continue

                for recv_id_1, recv_id_2 in combinations(recv_candidates, 2):
                    _iters += 1
                    if _iters > _iter_budget:
                        _budget_exceeded = True
                        break
                    if recv_id_1 not in user_elo or recv_id_2 not in user_elo:
                        continue

                    # Quick KTC pre-filter
                    if not _ktc_ok([give_id], [recv_id_1, recv_id_2]):
                        continue
                    if not _elo_gap_ok([give_id], [recv_id_1, recv_id_2]):
                        continue

                    give_user = user_elo.get(give_id, 1500)
                    give_opp  = opp_elo.get(give_id, 1500)
                    combined_recv_user = user_elo.get(recv_id_1, 1500) + user_elo.get(recv_id_2, 1500)
                    combined_recv_opp  = opp_elo.get(recv_id_1, 1500) + opp_elo.get(recv_id_2, 1500)

                    # User values the pair more than the single player they give
                    if combined_recv_user <= give_user * 0.95:
                        continue
                    # Opponent values the single player more than the pair
                    if give_opp <= combined_recv_opp * 0.95:
                        continue

                    mismatch = (combined_recv_user - give_user) + (give_opp - combined_recv_opp)
                    if mismatch <= 0:
                        continue

                    fairness = self._fairness_score([give_id], [recv_id_1, recv_id_2], seed_elo)
                    composite = (_c("mismatch_weight") * min(mismatch, 400) / 400 +
                                 _c("fairness_weight") * fairness)
                    composite *= _tier_mult_for_pids([give_id, recv_id_1, recv_id_2])
                    candidates.append((composite, mismatch, fairness, [give_id], [recv_id_1, recv_id_2]))

                    if len(candidates) >= int(_c("max_candidates")):
                        break
                if len(candidates) >= int(_c("max_candidates")):
                    break

        # ------------------------------------------------------------------
        # 3-for-2 trades (user gives 3, receives 2)
        # ------------------------------------------------------------------
        if len(candidates) < int(_c("max_candidates")) and not _budget_exceeded:
            for recv_id_1, recv_id_2 in combinations(recv_candidates, 2):
                if _budget_exceeded or time.monotonic() > _deadline:
                    break
                if recv_id_1 not in user_elo or recv_id_2 not in user_elo:
                    continue
                recv_dv_1 = _dv(recv_id_1)
                recv_dv_2 = _dv(recv_id_2)
                recv_pkg_dv = package_value([recv_dv_1, recv_dv_2])

                for give_id_1, give_id_2, give_id_3 in combinations(give_candidates, 3):
                    _iters += 1
                    if _iters > _iter_budget:
                        _budget_exceeded = True
                        break
                    if (give_id_1 not in user_elo or give_id_2 not in user_elo
                            or give_id_3 not in user_elo):
                        continue
                    # At least one give player must be pinned
                    if pinned_set and not ({give_id_1, give_id_2, give_id_3} & pinned_set):
                        continue

                    # Quick KTC pre-filter (cheap — avoids ELO math on bad pairs)
                    give_ids_3 = [give_id_1, give_id_2, give_id_3]
                    recv_ids_2 = [recv_id_1, recv_id_2]
                    give_pkg_dv = package_value([_dv(g) for g in give_ids_3])
                    if give_pkg_dv == 0 and recv_pkg_dv == 0:
                        pass  # both zero — let ELO decide
                    else:
                        greater = max(give_pkg_dv, recv_pkg_dv)
                        lesser  = min(give_pkg_dv, recv_pkg_dv)
                        if greater > 0 and (lesser / greater) < fairness_threshold:
                            continue
                    if not _elo_gap_ok(give_ids_3, recv_ids_2):
                        continue

                    combined_give_user = sum(user_elo.get(g, 1500) for g in give_ids_3)
                    combined_give_opp  = sum(opp_elo.get(g, 1500) for g in give_ids_3)
                    combined_recv_user = user_elo.get(recv_id_1, 1500) + user_elo.get(recv_id_2, 1500)
                    combined_recv_opp  = opp_elo.get(recv_id_1, 1500) + opp_elo.get(recv_id_2, 1500)

                    # User values the 2-pack more than the 3-pack they give
                    if combined_recv_user <= combined_give_user * 0.95:
                        continue
                    # Opponent values the 3-pack more than the 2-pack they give
                    if combined_give_opp <= combined_recv_opp * 0.95:
                        continue

                    mismatch = (combined_recv_user - combined_give_user) + (combined_give_opp - combined_recv_opp)
                    if mismatch <= 0:
                        continue

                    fairness = self._fairness_score(
                        [give_id_1, give_id_2, give_id_3], [recv_id_1, recv_id_2], seed_elo)
                    composite = (_c("mismatch_weight") * min(mismatch, 500) / 500 +
                                 _c("fairness_weight") * fairness)
                    candidates.append((
                        composite, mismatch, fairness,
                        [give_id_1, give_id_2, give_id_3],
                        [recv_id_1, recv_id_2],
                    ))

                    if len(candidates) >= int(_c("max_candidates")):
                        break
                if len(candidates) >= int(_c("max_candidates")):
                    break

        # ------------------------------------------------------------------
        # ------------------------------------------------------------------
        # Apply positional preference hard filter (not a score multiplier)
        # ------------------------------------------------------------------
        _acq  = acquire_positions    or []
        _away = trade_away_positions or []
        if _acq or _away:
            filtered: list[tuple[float, float, float, list[str], list[str]]] = []
            for composite, mismatch, fairness, give_ids, recv_ids in candidates:
                # If acquire_positions set, at least one received player must match
                if _acq:
                    recv_positions = [
                        players[pid].position for pid in recv_ids
                        if pid in players and players[pid].position
                    ]
                    if not any(p in _acq for p in recv_positions):
                        continue
                # If trade_away_positions set, at least one given player must match
                if _away:
                    give_positions = [
                        players[pid].position for pid in give_ids
                        if pid in players and players[pid].position
                    ]
                    if not any(p in _away for p in give_positions):
                        continue
                filtered.append((composite, mismatch, fairness, give_ids, recv_ids))
            candidates = filtered

        # ------------------------------------------------------------------
        # Agent A8 — apply trade-math adjustments (flag-gated).
        # Each candidate's composite score is multiplied by the product
        # of all enabled adjustments. Adjustments are ADDITIVE — each
        # enabled flag contributes independently and compounds.
        # When ALL flags are off this loop is a no-op (each function
        # short-circuits to 1.0 and leaves reasons untouched), so the
        # final candidate list is IDENTICAL to the legacy behaviour.
        # ------------------------------------------------------------------
        # Determine active scoring format once (for star-tax tier lookup).
        # We don't have explicit access here, so fall back to "1qb_ppr".
        _scoring_format = getattr(self, "_scoring_format", "1qb_ppr")
        _adjusted: list[tuple[float, float, float, list[str], list[str], list[str]]] = []
        for composite, mismatch, fairness, give_ids, recv_ids in candidates:
            reasons: list[str] = []
            adj = 1.0
            adj *= qb_tax_adjustment(
                give_ids, recv_ids, seed_elo, players, reasons,
            )
            adj *= star_tax_adjustment(
                give_ids, recv_ids, seed_elo, players, _scoring_format, reasons,
            )
            adj *= roster_clogger_adjustment(give_ids, recv_ids, reasons)
            new_composite = composite * adj
            _adjusted.append((new_composite, mismatch, fairness, give_ids, recv_ids, reasons))

        # Sort and take top N
        # ------------------------------------------------------------------
        _adjusted.sort(key=lambda x: x[0], reverse=True)
        # Consensus package values for the TradeValueBar — value space
        # (elo_to_value over the seed), same fn the calculator uses. This
        # legacy path prices fairness off raw-Elo sums, but the value bar
        # always speaks consensus dynasty value, so derive it here. Lazy
        # import: the optimizer imports this module (top-level would cycle).
        from .trade_optimizer import _consensus_packages
        def _seed_val(pid: str) -> float:
            return elo_to_value(seed_elo.get(pid, 1500.0))
        cards = []
        for composite, mismatch, fairness, give_ids, recv_ids, reasons in _adjusted[:max_cards]:
            _gv, _rv = _consensus_packages(give_ids, recv_ids, _seed_val)
            card = TradeCard(
                trade_id          = str(uuid.uuid4())[:8],
                league_id         = league_id,
                proposing_user_id = user_id,
                target_user_id    = opponent.user_id,
                target_username   = opponent.username,
                give_player_ids   = give_ids,
                receive_player_ids= recv_ids,
                mismatch_score    = round(mismatch, 1),
                fairness_score    = round(fairness, 3),
                composite_score   = round(composite, 3),
                reasons           = reasons if FLAGS.trade_math_human_explanations else [],
                give_value        = round(_gv, 1),
                receive_value     = round(_rv, 1),
            )
            cards.append(card)
        return cards

    # ------------------------------------------------------------------
    # Scoring helpers
    # ------------------------------------------------------------------

    def _mismatch_score(
        self,
        give_id: str,
        recv_id: str,
        user_elo: dict[str, float],
        opp_elo: dict[str, float],
    ) -> float:
        """
        How much perceived mutual gain exists in this 1-for-1 trade.
        Positive = both parties think they're winning.
        """
        user_gives_up   = user_elo.get(give_id, 1500)
        opp_values_give = opp_elo.get(give_id, 1500)
        user_gains      = user_elo.get(recv_id, 1500)
        opp_gives_up    = opp_elo.get(recv_id, 1500)

        # Opponent values what user gives MORE than user does
        opp_surplus = opp_values_give - user_gives_up
        # User values what they receive MORE than opponent does
        user_surplus = user_gains - opp_gives_up

        return opp_surplus + user_surplus

    def _fairness_score(
        self,
        give_ids: list[str],
        recv_ids: list[str],
        seed_elo: dict[str, float],
    ) -> float:
        """
        How balanced the trade is in consensus value (0–1).
        1.0 = perfectly balanced. Drops toward 0 as imbalance grows.
        """
        give_val = sum(seed_elo.get(pid, 1500) for pid in give_ids)
        recv_val = sum(seed_elo.get(pid, 1500) for pid in recv_ids)
        if give_val == 0 and recv_val == 0:
            return 1.0
        ratio = max(give_val, recv_val) / max(min(give_val, recv_val), 1)
        return round(1.0 / ratio, 3)
