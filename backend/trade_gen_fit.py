"""trade_gen_fit.py — bake-off arm `fit`: thin knockouts, dual 0–100 scores.

Spec: docs/plans/fit-challenger/PRD.md (§3 knockouts CLOSED), PLAN-v2.md, LLD.md.

LENS PROVENANCE (T3 — binding): every lens reads RAW boards.
  * viewer lens map  = elo_to_value(user_elo[pid])          — the job's raw
    `elo_map_rt`, NEVER passed through `_shrink_user_elo`
  * partner lens map = elo_to_value(member.elo_ratings[pid]) — raw by
    construction (LeagueMember carries no confidence map)
  * consensus map    = elo_to_value(seed_elo[pid])
This module must never import or call `_shrink_user_elo`. Enforced by
`test_fit_lens_provenance_raw`.

RANKING / C7c (LLD §1.8): `composite_score = aggregate` (you + them, 0–200)
and the bake-off draft consumes list ORDER only — never compare it across
arms as a magnitude (C7b). Every unranked-pair card (`boards == "none"`)
mirrors both sides onto the same consensus surplus, so its aggregate ≈ 100
by construction; within that plateau the consensus-fairness ratio decides
order (sort key `(aggregate, fairness, tiebreak)`), and the same tie-break
harmlessly orders any other aggregate tie.

ORGANIC ISOLATION: imported by exactly one production caller,
`bakeoff_runner.gen_fit_cards`. `trade_service` must never import this module.
"""

from __future__ import annotations

import logging
import math
import time
import uuid
from dataclasses import dataclass, field
from itertools import combinations

from . import trade_service as ts        # T1 — MODULE import; call ts.overpay_ok(...)
from . import trade_optimizer as topt    # T1 — same discipline for _feasible_after

logger = logging.getLogger(__name__)

#: Pinned scorer version. Stamped into `fit.ver` and `fit_diag.ver`; the M2
#: readout refuses to bucket-match across versions (failure-mode row 11).
#: Bump on ANY change to _score, weights semantics, or bucket thresholds.
SCORER_VERSION = "fit-1"

#: K1 (PRD §3, operator-CLOSED): the legal (n_give, n_recv) shapes. Note the
#: closed list EXCLUDES 2-2 and 3-3 (equal multi-asset swaps) — see LLD §8 R-b.
_LEGAL_SHAPES: frozenset[tuple[int, int]] = frozenset(
    {(1, 1), (2, 1), (1, 2), (3, 1), (1, 3), (3, 2), (2, 3)})

#: Bucket names, pinned (also the M2 SQL vocabulary).
_BUCKETS = ("both_high", "mixed", "you_tilt", "them_tilt", "both_ok", "weak")


# ---------------------------------------------------------------------------
# Diagnostics (LLD §1.2 — draft B §2.6, adopted by PLAN-v2 §4)
# ---------------------------------------------------------------------------

@dataclass
class FitReport:
    """Per-batch diagnostics. `diagnostics()` is the flat dict that rides
    `bakeoff_runs.arms_json['fit'].diagnostics` — every key below is present
    on EVERY run (zero/None-valued, never absent)."""
    league_id: str
    user_id: str
    opponents: int = 0                 # opponents that reached the pair loop
    boarded_opponents: int = 0         # partner has_rankings AND elo_ratings
    enumerated: int = 0                # candidates that ENTERED the K-chain
    scored: int = 0                    # K-chain survivors handed to the scorer
    killed: dict = field(default_factory=lambda: {
        "K0": 0, "K1": 0, "K2": 0, "K3": 0, "K4": 0,
        "K5": 0, "K6": 0, "K7": 0, "junk": 0})
    r5_fail_scored: int = 0            # fit_r5_mode=0 only: K7 fails that scored
    capped_pairs: int = 0              # pairs that hit fit_max_packages_per_pair
    post_filtered: dict = field(default_factory=lambda: {
        "untouchable": 0, "not_interested": 0, "position_prefs": 0,
        "r4_swiped": 0, "c4_centerpiece": 0, "min_them": 0, "min_aggregate": 0})
    emitted: int = 0                   # cards returned to the adapter
    # Bucket/character metrics — computed over the SCORED, RANKED, PRE-F4 set
    # (they describe the generator; F4 filters describe the viewer's prefs).
    one_sided_pct: float | None = None     # share with them < 40
    both_high_pct: float | None = None
    mixed_pct: float | None = None
    you_tilt_pct: float | None = None
    median_aggregate: float | None = None
    # C5 — over the top quartile BY AGGREGATE of the same pre-F4 set:
    top_q_pick_share: float | None = None  # share of cards containing ≥1 pick
    top_q_junk_share: float | None = None  # share containing an asset with
                                           # consensus value < asset_floor_abs
    ms: int = 0                        # module-internal wall time

    def diagnostics(self) -> dict:
        """Flat dict for arms_json. Every §2.6 key, always."""
        return {
            "opponents": self.opponents,
            "boarded_opponents": self.boarded_opponents,
            "enumerated": self.enumerated,
            "scored": self.scored,
            "killed": dict(self.killed),
            "r5_fail_scored": self.r5_fail_scored,
            "capped_pairs": self.capped_pairs,
            "post_filtered": dict(self.post_filtered),
            "emitted": self.emitted,
            "one_sided_pct": self.one_sided_pct,
            "both_high_pct": self.both_high_pct,
            "mixed_pct": self.mixed_pct,
            "you_tilt_pct": self.you_tilt_pct,
            "median_aggregate": self.median_aggregate,
            "top_q_pick_share": self.top_q_pick_share,
            "top_q_junk_share": self.top_q_junk_share,
            "ms": self.ms,
        }


# ---------------------------------------------------------------------------
# Knockout chain (LLD §1.6) — cost order, K3 LAST
# ---------------------------------------------------------------------------

@dataclass
class _PairCtx:
    """Per-pair namespace threaded through the K-chain (LLD §1.6). Built once
    per (viewer, opponent) pair by the entry point; the fit test suite builds
    it directly. All value accessors are pid → value callables in the live v2
    value space. `r5_fail` is per-CANDIDATE scratch — `_kill` resets it on
    every call and sets it only under `fit_r5_mode = 0`."""
    players: dict
    cval: object            # pid → consensus value (elo_to_value ∘ seed_elo)
    uval: object            # pid → viewer RAW-board value; None when unboarded
    oval: object            # pid → partner RAW-board value; None when unboarded
    user_counts: dict       # topt._pos_counts(user_roster, players)
    opp_counts: dict        # topt._pos_counts(member.roster, players)
    user_pos_values: dict   # {pos: [(pid, cval)]} — ts.need_gate_ok's shape
    user_profile: dict      # ts.analyze_roster_strengths output
    outlook: str | None
    scoring_format: str
    bypass_need_gate: bool
    viewer_boarded: bool
    partner_boarded: bool
    r5_fail: bool = False

    @property
    def uval_or_cval(self):
        """Junk-metric accessor: the viewer's raw board when boarded, else
        consensus — the live max-of-boards metric, degraded honestly for
        unboarded teams (LLD §1.6 junk row)."""
        return self.uval if self.viewer_boarded else self.cval

    @property
    def oval_or_cval(self):
        return self.oval if self.partner_boarded else self.cval


def _k1_shape_ok(n_give: int, n_recv: int) -> bool:
    """K1 (PRD §3, operator-CLOSED) — legal package shapes only."""
    return (n_give, n_recv) in _LEGAL_SHAPES


def _kill(give_ids: list[str], recv_ids: list[str], ctx) -> str | None:
    """Returns the FIRST failing K-code, else None. Execution order is the
    COST order (HLD §5b), not the PRD's table order: K1 K2 K4 K5 K6 [junk]
    K7 K3. Counters stay attributable because the order is fixed
    (`test_k3_runs_last_in_kill_order` pins it).

    K0 is structural — the enumerator draws only from the two rosters'
    pools, so no K0 check exists here and `killed["K0"]` stays 0 (reported).

    This function is a pure verdict; the §1.5 enumerator closure owns the
    `report.killed[code]` increment on a non-None return. One scratch bit:
    under `fit_r5_mode = 0` a K7 failure does not kill — `ctx.r5_fail` is
    set instead so the scorer can tag the candidate `r5_fail` and count
    `report.r5_fail_scored`. No score change in v1 (LLD §8 R-d).

    Each predicate is reached as a MODULE attribute (`ts.<name>`) at call
    time — T1: a monkeypatch/knob rebind on `trade_service` propagates to
    fit (`test_fit_gate_binding_sabotage`). The predicates read their knobs
    through `ts._c` (thread-local overrides first), so fit's K2–K7 see the
    same live values arm B sees.
    """
    ctx.r5_fail = False
    # K1 — structurally guaranteed by the enumerator, kept as a guard.
    if not _k1_shape_ok(len(give_ids), len(recv_ids)):
        return "K1"
    # K2 — byte-identical to live C3: the 4th positional is `seed_value`;
    # passing cval activates the strip (`strip_matched_pick_pairs`,
    # `pick_pair_strip_frac`) exactly as live.
    if not ts.pick_swap_ok(give_ids, recv_ids, ctx.players, ctx.cval):
        return "K2"
    # K4 — G6 R1 absolute overpay ceiling, both directions.
    if not ts.overpay_ok(give_ids, recv_ids, ctx.cval):
        return "K4"
    # K5 — G6 R2 per-position signed net cap (picks uncounted).
    if not ts.pos_net_ok(give_ids, recv_ids, ctx.players):
        return "K5"
    # K6 — G6 R3 "the pick IS the gap".
    if not ts.pick_gap_ok(give_ids, recv_ids, ctx.cval, ctx.players):
        return "K6"
    # junk — OFF by default (PRD §3: filler is explicitly NOT a knockout in
    # this arm; junk scores badly instead). fit_junk_floor >= 1 arms the
    # live filler_ok metric; kills count under "junk" (C5 / PRD §10).
    if ts._c("fit_junk_floor") >= 1.0:
        if not ts.filler_ok(give_ids, recv_ids,
                            ctx.uval_or_cval, ctx.oval_or_cval):
            return "junk"
    # K7 — G6 R5 need gate, live-as-written, viewer roster only (PRD K7).
    # Skipped on targeted jobs (bypass_need_gate — unreachable on bake-off
    # decks, kept for correctness/parity).
    if not ctx.bypass_need_gate:
        r5_ok = ts.need_gate_ok(
            give_ids, recv_ids,
            seed_value=ctx.cval,
            players=ctx.players,
            user_pos_values=ctx.user_pos_values,
            outlook=ctx.outlook,
            position_needs=ctx.user_profile.get("position_needs"),
            position_surplus=ctx.user_profile.get("position_surplus"),
            scoring_format=ctx.scoring_format,
        )
        if not r5_ok:
            if ts._c("fit_r5_mode") >= 1.0:
                return "K7"
            ctx.r5_fail = True     # mode 0: predicate runs, tags, never kills
    # K3 LAST — both lineups startable, every path (HLD F-9).
    g = topt._subset_pos_delta(give_ids, ctx.players)
    r = topt._subset_pos_delta(recv_ids, ctx.players)
    if not (topt._feasible_after(ctx.user_counts, g, r, ctx.scoring_format)
            and topt._feasible_after(ctx.opp_counts, r, g,
                                     ctx.scoring_format)):
        return "K3"
    return None


# ---------------------------------------------------------------------------
# Entry point (LLD §1.3) — PR-F2
# ---------------------------------------------------------------------------

def generate_league_suggestions(
    *,
    players: dict,
    league: ts.League,
    user_id: str,
    user_elo: dict[str, float],
    user_roster: list[str],
    seed_elo: dict[str, float],
    scoring_format: str = "1qb_ppr",
    outlook: str | None = None,
    bypass_need_gate: bool = False,
    untouchable_ids: set | None = None,
    not_interested_ids: set | None = None,
    target_ids: set | None = None,          # accepted for kwarg parity; v1 unused
    acquire_positions: list[str] | None = None,
    trade_away_positions: list[str] | None = None,
    opponent_user_id: str | None = None,
    past_decision_keys: set | None = None,
    max_per_opponent: int | None = None,    # None = full ranked list (gen_v2 contract)
    on_opponent_done=None,                  # accepted, IGNORED (fit is a quiet arm)
) -> tuple[list[ts.TradeCard], FitReport]:
    """Fit arm: pool → enumerate → K-chain → dual scorer → rank → post filters.
    Returns (cards, report). Cards are ordinary TradeCards carrying the `fit`
    payload; `lane`/`lane_shift`/intent/C4b are applied by gen_fit_cards."""
    raise NotImplementedError("PR-F2 — LLD §1.3 pipeline")


def _build_pool(*, roster: list[str], players: dict, cval,
                board_val=None, opp_board_val=None) -> list[str]:
    """PRD §5 union pool for ONE roster within one pair. Deterministic.

    board_val    — that roster owner's OWN raw board accessor, None if unboarded
    opp_board_val — the pair's OTHER board accessor, None unless BOTH boarded
    """
    raise NotImplementedError("PR-F2 — LLD §1.4 pool builder")


def _enumerate_pair(user_pool: list[str], opp_pool: list[str],
                    kill, score, report: FitReport,
                    cap: int, expand_from: int) -> list[dict]:
    """PRD §5 budget shape: full 1-for-1 cartesian, then 2-/3-asset shapes
    expanded around the top `expand_from` surviving 1-for-1 centerpieces.
    `kill(give, recv) -> str | None`; `score(give, recv) -> dict` (a scored
    candidate). Increments report.enumerated per candidate ENTERING the
    K-chain; hard stop when a pair's enumerated count reaches `cap`."""
    raise NotImplementedError("PR-F2 — LLD §1.5 enumerator")


# ---------------------------------------------------------------------------
# Scorer (LLD §1.7) — PR-F2
# ---------------------------------------------------------------------------

def _score(surplus: float) -> float:
    """PRD §4 curve: clamp(even + 50·tanh(s / scale), 0, 100).
    even = _c("fit_score_even") (50), scale = _c("fit_score_scale") (400)."""
    raise NotImplementedError("PR-F2 — LLD §1.7 scorer (pin COMPUTED values, "
                              "never PLAN-v2's rounded 88.4 — HLD F-5)")


def _surplus(recv_ids: list[str], give_ids: list[str], value_of) -> float:
    """Directed surplus of ONE team in the live v2 value space: elo_to_value →
    package_value_v2 (trade-wide v_max, other_values crown credit) → waiver
    slot cost on the receiving-more side. Byte-parallel to the live formula at
    trade_service.py:4780–4806 so fit numbers are comparable to live ones."""
    raise NotImplementedError("PR-F2 — LLD §1.7 surplus")


def _bucket(you: float, them: float) -> str:
    """PRD §4 presentment buckets. Evaluation order is pinned — the first
    matching row wins (mixed requires the lower side ≥ 40)."""
    raise NotImplementedError("PR-F2 — LLD §1.7 buckets")


# ---------------------------------------------------------------------------
# Post-score filters (LLD §1.9, F4 — the module half) — PR-F3
# ---------------------------------------------------------------------------

def _apply_post_filters(cards, report, **job):
    """§1.9 post-score filters over the RANKED list, order pinned:
    min_them/min_aggregate → untouchables → not-interested → position pins →
    R4/already-swiped → C4 centerpiece cap → max_per_opponent. Each drop
    counts into `report.post_filtered`. A preference hides a card AFTER
    scoring — it never shrinks the search."""
    raise NotImplementedError("PR-F3 — LLD §1.9 post-score filters")


# ---------------------------------------------------------------------------
# M3 helper (LLD §1.11 — lives here so the scorer has one home) — PR-F2
# ---------------------------------------------------------------------------

def stamp_fit_diag(arm_lists: dict[str, list], *, players: dict,
                   league: ts.League, user_elo: dict[str, float],
                   seed_elo: dict[str, float]) -> None:
    """M3/R-11 — set `card.fit_diag = {"you", "them", "bucket", "ver"}` on
    EVERY card of EVERY arm's ranked list. Fit's own cards reuse `card.fit`
    (identical numbers by construction). Other arms' cards are scored fresh:
    resolve the partner via {m.user_id: m for m in league.members}, compute
    you/them per §1.7 (weights and lenses included), bucket per _bucket.
    Per-card try/except: a card that cannot be scored (unknown partner,
    empty sides) gets `card.fit_diag = None` — the key must exist DOWNSTREAM
    (features_json writes it null), absence is impossible (M4 contract).
    Purely attribute-setting: no return, no reordering, no score mutation —
    inertness is enforced by test_fit_diag_inert."""
    raise NotImplementedError("PR-F2 — LLD §1.11 fit_diag stamp")
