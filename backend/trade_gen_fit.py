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

#: K1 (PRD §3 + §12.6): the legal (n_give, n_recv) shapes — every 1–3 × 1–3
#: combination. The PRD's original list omitted 2-2 and 3-3; LLD §8 R-b pinned
#: that literally and flagged it, and the operator ruled it unintended
#: (2026-08-20): equal multi-asset swaps are legal.
_LEGAL_SHAPES: frozenset[tuple[int, int]] = frozenset(
    {(1, 1), (2, 1), (1, 2), (2, 2), (3, 1), (1, 3), (3, 2), (2, 3), (3, 3)})

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
# Entry point (LLD §1.3)
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
    payload; `lane`/`lane_shift`/intent/C4b are applied by gen_fit_cards.

    Behavioral spec: LLD §1.3 steps 1–5. Errors are NOT caught here — the
    per-arm try/except in `run_bakeoff` is the containment layer, same
    posture as `trade_gen_v2`."""
    t0 = time.monotonic()
    report = FitReport(league_id=league.league_id, user_id=user_id)
    past_decision_keys = past_decision_keys or set()   # F4 step 5 (R4/swiped)
    _ = (target_ids, on_opponent_done)   # kwarg parity; v1 unused / quiet arm

    # 1. Value accessors — RAW boards (T3, binding): cached dicts,
    #    elo_to_value fallback at Elo 1500. `_shrink_user_elo` never runs.
    _cv: dict[str, float] = {}

    def cval(pid: str) -> float:
        v = _cv.get(pid)
        if v is None:
            v = ts.elo_to_value(seed_elo.get(pid, 1500.0))
            _cv[pid] = v
        return v

    viewer_boarded = bool(user_elo)
    uval = None
    if viewer_boarded:
        _uv: dict[str, float] = {}

        def uval(pid: str) -> float:
            v = _uv.get(pid)
            if v is None:
                v = ts.elo_to_value(user_elo.get(pid, 1500.0))
                _uv[pid] = v
            return v

    # 2. Once-per-job viewer structures (LLD §1.3 step 2).
    user_profile = ts.analyze_roster_strengths(user_roster, players,
                                               scoring_format)
    user_pos_values: dict[str, list] = {}
    for pid in user_roster:                # players only, QB/RB/WR/TE only —
        p = players.get(pid)               # the ts.need_gate_ok shape
        if p is None or ts.is_pick_asset(p):
            continue
        pos = getattr(p, "position", None)
        if pos in ("QB", "RB", "WR", "TE"):
            user_pos_values.setdefault(pos, []).append((pid, cval(pid)))
    user_counts = topt._pos_counts(user_roster, players)

    # 3. Eligible opponents — EVERY opponent is a pair, boarded or not (the
    #    PRD's core difference from gen_v2). Parity narrowing with
    #    trade_gen_v2 when the job targets one opponent.
    eligible = [m for m in league.members
                if m.user_id != user_id and m.roster]
    if opponent_user_id:
        eligible = [m for m in eligible if m.user_id == opponent_user_id]
    report.opponents = len(eligible)

    cap = int(ts._c("fit_max_packages_per_pair"))
    expand_from = int(ts._c("fit_expand_from"))

    # 4. Per pair: pools → enumerate → kill → score.
    candidates: list[dict] = []
    for member in eligible:
        partner_boarded = bool(member.has_rankings and member.elo_ratings)
        oval = None
        if partner_boarded:
            report.boarded_opponents += 1
            _ov: dict[str, float] = {}
            _board = member.elo_ratings

            def oval(pid: str, _board=_board, _ov=_ov) -> float:
                v = _ov.get(pid)
                if v is None:
                    v = ts.elo_to_value(_board.get(pid, 1500.0))
                    _ov[pid] = v
                return v

        both = viewer_boarded and partner_boarded
        user_pool = _build_pool(roster=user_roster, players=players,
                                cval=cval, board_val=uval,
                                opp_board_val=oval if both else None)
        opp_pool = _build_pool(roster=member.roster, players=players,
                               cval=cval, board_val=oval,
                               opp_board_val=uval if both else None)

        opp_profile = ts.analyze_roster_strengths(member.roster, players,
                                                  scoring_format)
        ctx = _PairCtx(
            players=players, cval=cval, uval=uval, oval=oval,
            user_counts=user_counts,
            opp_counts=topt._pos_counts(member.roster, players),
            user_pos_values=user_pos_values, user_profile=user_profile,
            outlook=outlook, scoring_format=scoring_format,
            bypass_need_gate=bypass_need_gate,
            viewer_boarded=viewer_boarded, partner_boarded=partner_boarded)

        def kill(g: list, r: list, _ctx=ctx) -> str | None:
            # The enumerator-side closure owns the killed[] counting —
            # _kill itself is a pure verdict (its docstring's contract).
            code = _kill(g, r, _ctx)
            if code is not None:
                report.killed[code] += 1
            return code

        def score(g: list, r: list, _ctx=ctx, _m=member, _oval=oval,
                  _pb=partner_boarded, _opp_profile=opp_profile) -> dict:
            # ctx.r5_fail is per-candidate scratch set by the _kill call
            # immediately preceding this score call (same candidate).
            r5 = _ctx.r5_fail
            if r5:
                report.r5_fail_scored += 1
            cand = _score_candidate(
                g, r, cval=cval, uval=uval, oval=_oval,
                viewer_boarded=viewer_boarded, partner_boarded=_pb,
                seed_elo=seed_elo, r5_fail=r5)
            gv, rv = topt._consensus_packages(g, r, cval)
            fairness = (min(gv, rv) / max(gv, rv)
                        if gv > 0 and rv > 0 else 1.0)
            cand.update(give_ids=list(g), recv_ids=list(r), member=_m,
                        opp_profile=_opp_profile, fairness=fairness,
                        gv=gv, rv=rv)
            return cand

        candidates.extend(_enumerate_pair(user_pool, opp_pool, kill, score,
                                          report, cap, expand_from))

    # 5a. Rank (LLD §1.8): (aggregate, fairness, tiebreak). The aggregate
    # term is quantized at 1e-9 so the C7c unranked-pair plateau (mirrored
    # tanh sums, exactly 100 up to float noise ~1e-13) cannot let noise
    # outrank the fairness term; real score separations are ≥ orders of
    # magnitude larger. Ranking otherwise uses the unrounded floats.
    candidates.sort(key=lambda c: (
        -round(c["aggregate_raw"], 9), -c["fairness"],
        (c["member"].user_id, tuple(sorted(c["give_ids"])),
         tuple(sorted(c["recv_ids"])))))

    # 5b. Bucket/character metrics over the SCORED, RANKED, PRE-F4 set
    # (LLD §8 R-j — they describe the generator, not the viewer's prefs).
    n = len(candidates)
    if n:
        report.one_sided_pct = round(
            sum(1 for c in candidates if c["them_raw"] < 40.0) / n, 4)
        _bcount = {b: 0 for b in _BUCKETS}
        for c in candidates:
            _bcount[c["bucket"]] += 1
        report.both_high_pct = round(_bcount["both_high"] / n, 4)
        report.mixed_pct = round(_bcount["mixed"] / n, 4)
        report.you_tilt_pct = round(_bcount["you_tilt"] / n, 4)
        aggs = sorted(c["aggregate_raw"] for c in candidates)
        mid = n // 2
        report.median_aggregate = round(
            aggs[mid] if n % 2 else (aggs[mid - 1] + aggs[mid]) / 2.0, 4)
        # C5 — top quartile BY AGGREGATE of the same pre-F4 set.
        q = max(1, math.ceil(n / 4))
        top = candidates[:q]
        floor_abs = ts._c("asset_floor_abs")
        report.top_q_pick_share = round(sum(
            1 for c in top
            if any(ts.is_pick_asset(players.get(pid))
                   for pid in c["give_ids"] + c["recv_ids"])) / q, 4)
        report.top_q_junk_share = round(sum(
            1 for c in top
            if any(cval(pid) < floor_abs
                   for pid in c["give_ids"] + c["recv_ids"])) / q, 4)

    # 5c. Cards (LLD §1.10).
    cards: list[ts.TradeCard] = []
    for c in candidates:
        member = c["member"]
        payload = c["payload"]
        card = ts.TradeCard(
            trade_id=str(uuid.uuid4())[:8],
            league_id=league.league_id,
            proposing_user_id=user_id,
            target_user_id=member.user_id,
            target_username=member.username,
            give_player_ids=c["give_ids"],
            receive_player_ids=c["recv_ids"],
            # F-4 ruling: harmonic mean of the two 0–100 team scores —
            # 0 when either side scores 0, never used for ranking.
            mismatch_score=round(
                ts._harmonic_mean(payload["you"], payload["them"]), 1),
            # Live consensus ratio (PLAN.md note 5) — NOT a fit-lens number.
            fairness_score=c["fairness"],
            composite_score=round(c["aggregate_raw"], 4),
            basis="divergence" if c["boards"] == "both" else "consensus",
        )
        card.give_value = round(c["gv"], 1)
        card.receive_value = round(c["rv"], 1)
        card.fit = payload
        # STAMPED for telemetry, never multiplied (PRD §4).
        card.need_fit = ts.need_fit_score(
            user_profile, c["opp_profile"], c["give_ids"], c["recv_ids"],
            players, scoring_format)
        cards.append(card)

    # 5d. §1.9 post-score filters (F4, the module half) — applied HERE,
    # after the pre-F4 metrics above (LLD §8 R-j: those describe the
    # generator, these describe the viewer's prefs) and before emitted is
    # counted. `players` is passed beyond PR-F2's marked list because the
    # position-pin step must tell a non-pick player from a pick (LLD §1.9
    # step 4) and cards carry ids only — noted as a deviation in PR-F3.
    cards = _apply_post_filters(
        cards, report,
        untouchable_ids=untouchable_ids,
        not_interested_ids=not_interested_ids,
        acquire_positions=acquire_positions,
        trade_away_positions=trade_away_positions,
        past_decision_keys=past_decision_keys,
        seed_elo=seed_elo, players=players,
        max_per_opponent=max_per_opponent)

    report.emitted = len(cards)
    report.ms = int((time.monotonic() - t0) * 1000)
    return cards, report


def _build_pool(*, roster: list[str], players: dict, cval,
                board_val=None, opp_board_val=None) -> list[str]:
    """PRD §5 union pool for ONE roster within one pair. Deterministic.

    board_val    — that roster owner's OWN raw board accessor, None if unboarded
    opp_board_val — the pair's OTHER board accessor, None unless BOTH boarded

    Union of: top fit_pool_consensus by cval; top fit_pool_div_seed by
    |board − seed| (boarded only); top fit_pool_div_opp by |board − opp
    board| (both boarded only); every owned pick unconditionally. Capped
    at fit_pool_cap unique ids by max(consensus percentile, |div|
    percentile), max-tie-rank (1.0 = best) — picks compete under the cap
    like everything else (LLD §8 R-c). Returned in cap-rank order
    (descending) so phase-2 expansion draws best-first.
    """
    ids = list(dict.fromkeys(roster))
    n_a = max(int(ts._c("fit_pool_consensus")), 0)
    n_b = max(int(ts._c("fit_pool_div_seed")), 0)
    n_c = max(int(ts._c("fit_pool_div_opp")), 0)
    cap = max(int(ts._c("fit_pool_cap")), 0)

    union: set[str] = set()
    union.update(sorted(ids, key=lambda p: (-cval(p), p))[:n_a])
    if board_val is not None:
        union.update(sorted(
            ids, key=lambda p: (-abs(board_val(p) - cval(p)), p))[:n_b])
        if opp_board_val is not None:
            union.update(sorted(
                ids,
                key=lambda p: (-abs(board_val(p) - opp_board_val(p)), p))[:n_c])
    union.update(p for p in ids if ts.is_pick_asset(players.get(p)))

    members = sorted(union)
    n = len(members)
    if n == 0:
        return []

    def _pct(vals: dict[str, float]) -> dict[str, float]:
        """Fractional rank within the union, ties sharing the MAX
        percentile (1.0 = best)."""
        ordered = sorted(vals.values(), reverse=True)
        return {p: (n - sum(1 for x in ordered if x > v)) / n
                for p, v in vals.items()}

    cons_pct = _pct({p: cval(p) for p in members})
    if board_val is not None:
        def _div(p: str) -> float:
            d = abs(board_val(p) - cval(p))
            if opp_board_val is not None:
                d = max(d, abs(board_val(p) - opp_board_val(p)))
            return d
        div_pct = _pct({p: _div(p) for p in members})
    else:
        # No board ⇒ no divergence is defined for any asset: div
        # percentile pinned 0.0 so everything competes on consensus
        # percentile alone (the LLD's picks rationale, generalized).
        div_pct = {p: 0.0 for p in members}

    rank = {p: max(cons_pct[p], div_pct[p]) for p in members}
    ordered = sorted(members, key=lambda p: (-rank[p], p))
    return ordered[:cap] if n > cap else ordered


def _enumerate_pair(user_pool: list[str], opp_pool: list[str],
                    kill, score, report: FitReport,
                    cap: int, expand_from: int) -> list[dict]:
    """PRD §5 budget shape: full 1-for-1 cartesian, then 2-/3-asset shapes
    expanded around the top `expand_from` surviving 1-for-1 centerpieces.
    `kill(give, recv) -> str | None`; `score(give, recv) -> dict` (a scored
    candidate). Increments report.enumerated per candidate ENTERING the
    K-chain; hard stop when a pair's enumerated count reaches `cap`.

    Phase-2 shape order is pinned (deterministic budget attribution):
    legal shapes minus (1,1), sorted by (total assets, shape) —
    (1,2) (2,1) (1,3) (3,1) (2,3) (3,2). A dedupe hit is checked BEFORE
    the budget and costs nothing. If phase 1 yields zero survivors,
    phase 2 does not run for the pair. No randomness anywhere."""
    out: list[dict] = []
    survivors1: list[tuple[dict, str, str]] = []
    pair_count = 0
    capped = False

    def _visit(g_list: list, r_list: list) -> dict | None:
        nonlocal pair_count
        pair_count += 1
        report.enumerated += 1
        if kill(g_list, r_list) is None:
            cand = score(g_list, r_list)
            report.scored += 1
            out.append(cand)
            return cand
        return None

    # Phase 1 — full 1-for-1 cartesian, pool-rank order.
    for g in user_pool:
        for r in opp_pool:
            if pair_count >= cap:
                capped = True
                break
            cand = _visit([g], [r])
            if cand is not None:
                survivors1.append((cand, g, r))
        if capped:
            break

    # Phase 2 — 2-/3-asset expansion around the top phase-1 centerpieces.
    if not capped and survivors1:
        seeds = sorted(
            survivors1,
            key=lambda t: (-t[0]["aggregate_raw"], (t[1], t[2])),
        )[:max(expand_from, 0)]
        shapes = sorted(_LEGAL_SHAPES - {(1, 1)},
                        key=lambda s: (s[0] + s[1], s))
        seen: set[tuple[frozenset, frozenset]] = set()
        for _cand0, g0, r0 in seeds:
            if capped:
                break
            rest_g = [p for p in user_pool if p != g0]
            rest_r = [p for p in opp_pool if p != r0]
            for n_give, n_recv in shapes:
                if capped:
                    break
                for g_add in combinations(rest_g, n_give - 1):
                    if capped:
                        break
                    g_list = [g0, *g_add]
                    g_key = frozenset(g_list)
                    for r_add in combinations(rest_r, n_recv - 1):
                        r_list = [r0, *r_add]
                        key = (g_key, frozenset(r_list))
                        if key in seen:
                            continue        # dedupe hit — not budget
                        seen.add(key)
                        if pair_count >= cap:
                            capped = True
                            break
                        _visit(g_list, r_list)

    if capped:
        report.capped_pairs += 1
    return out


# ---------------------------------------------------------------------------
# Scorer (LLD §1.7)
# ---------------------------------------------------------------------------

def _score(surplus: float) -> float:
    """PRD §4 curve: clamp(even + 50·tanh(s / scale), 0, 100).
    even = _c("fit_score_even") (50), scale = _c("fit_score_scale") (400).
    Pinned by computed values (HLD F-5 — never hand-rounded):
        s=0      → 50.0
        s=+200   → 50 + 50·tanh(0.5) = 73.105857863…   (−200 → 26.894142137…)
        s=+400   → 50 + 50·tanh(1)   = 88.079707797…   (−400 → 11.920292202…)
        s=+800   → 50 + 50·tanh(2)   = 98.201379003…   (−800 → 1.798620996…)
        s=+1200  → 50 + 50·tanh(3)   = 99.752737684…   (−1200 → 0.247262315…)
    (The PLAN-v2 F3 note's "88.4/11.6" was itself rounded wrong; the test pins
    the computed values above with abs tolerance 1e-6.)"""
    scale = ts._c("fit_score_scale")
    return max(0.0, min(100.0,
        ts._c("fit_score_even") + 50.0 * math.tanh(surplus / scale)))


def _surplus(recv_ids: list[str], give_ids: list[str], value_of) -> float:
    """Directed surplus of ONE team in the live v2 value space: elo_to_value →
    package_value_v2 (trade-wide v_max, other_values crown credit) → waiver
    slot cost on the receiving-more side. Byte-parallel to the live formula at
    trade_service.py:4780–4806 so fit numbers are comparable to live ones."""
    rvals = [value_of(p) for p in recv_ids]
    gvals = [value_of(p) for p in give_ids]
    v_max = max(rvals + gvals)
    recvd = ts.package_value_v2(rvals, v_max, n_other=len(give_ids),
                                other_values=gvals)
    sent  = ts.package_value_v2(gvals, v_max, n_other=len(recv_ids),
                                other_values=rvals)
    extra = len(recv_ids) - len(give_ids)      # raw id counts, picks included —
    if extra > 0:                              # identical to live A3
        recvd -= ts._c("waiver_slot_cost") * extra
    return recvd - sent


def _bucket(you: float, them: float) -> str:
    """PRD §4 presentment buckets. Evaluation order is pinned — the first
    matching row wins (mixed requires the lower side ≥ 40)."""
    if you >= 70 and them >= 70:
        return "both_high"
    if (you >= 70 and 40 <= them < 70) or (them >= 70 and 40 <= you < 70):
        return "mixed"
    if you >= 70 and them < 40:
        return "you_tilt"
    if them >= 70 and you < 40:
        return "them_tilt"
    if 40 <= you < 70 and 40 <= them < 70:
        return "both_ok"
    return "weak"


def _combine(l1: float | None, l2: float | None, l3: float) -> float:
    """One team's lens combine (PRD §4): weights (fit_w_board, fit_w_div,
    fit_w_cons) over the FIRED lenses, renormalized to sum 1 (LLD §8 R-e).
    l1 is None ⇔ the team is unboarded ⇒ 1.0·L3; l2 may be independently
    None (all traded assets unseeded) ⇒ (w1·L1 + w3·L3)/(w1+w3)."""
    if l1 is None:
        return l3
    w1 = ts._c("fit_w_board")
    w3 = ts._c("fit_w_cons")
    num = w1 * l1 + w3 * l3
    den = w1 + w3
    if l2 is not None:
        w2 = ts._c("fit_w_div")
        num += w2 * l2
        den += w2
    return num / den if den > 0 else l3


def _r1(x: float | None) -> float | None:
    return None if x is None else round(x, 1)


def _score_candidate(give_ids: list[str], recv_ids: list[str], *,
                     cval, uval, oval, viewer_boarded: bool,
                     partner_boarded: bool, seed_elo: dict,
                     r5_fail: bool = False) -> dict:
    """Dual 0–100 scores for one candidate, viewer frame (LLD §1.7).

    Lens provenance (T3, binding): `uval`/`oval` are RAW-board accessors,
    `cval` the seed accessor — `_shrink_user_elo` is never in this path.
    L2 fires iff the team is boarded AND ≥1 traded asset has a real
    seed_elo row (LLD §8 R-e). Returns the internal candidate dict:
    unrounded you/them/aggregate for ranking + the §1.7 `fit` payload
    (all six lens keys always present, None where a lens did not fire —
    nulls DO serialize, §8 R-h)."""
    s_cons_you = _surplus(recv_ids, give_ids, cval)
    s_cons_them = _surplus(give_ids, recv_ids, cval)
    seeded = any(pid in seed_elo for pid in list(give_ids) + list(recv_ids))

    l1y = l2y = None
    if viewer_boarded:
        s_board_you = _surplus(recv_ids, give_ids, uval)
        l1y = _score(s_board_you)
        if seeded:
            l2y = _score(s_board_you - s_cons_you)
    l3y = _score(s_cons_you)

    l1t = l2t = None
    if partner_boarded:
        s_board_them = _surplus(give_ids, recv_ids, oval)
        l1t = _score(s_board_them)
        if seeded:
            l2t = _score(s_board_them - s_cons_them)
    l3t = _score(s_cons_them)

    you = _combine(l1y, l2y, l3y)
    them = _combine(l1t, l2t, l3t)
    bucket = _bucket(you, them)
    boards = ("both" if viewer_boarded and partner_boarded else
              "viewer" if viewer_boarded else
              "partner" if partner_boarded else "none")
    payload = {
        "you": round(you, 1), "them": round(them, 1),
        "aggregate": round(you + them, 1),          # 0–200
        "bucket": bucket, "boards": boards, "ver": SCORER_VERSION,
        "r5_fail": bool(r5_fail),
        "lenses": {
            "you":  {"board": _r1(l1y), "vs_consensus": _r1(l2y),
                     "consensus": round(l3y, 1)},
            "them": {"board": _r1(l1t), "vs_consensus": _r1(l2t),
                     "consensus": round(l3t, 1)},
        },
    }
    return {"you_raw": you, "them_raw": them, "aggregate_raw": you + them,
            "bucket": bucket, "boards": boards, "payload": payload}


# ---------------------------------------------------------------------------
# Post-score filters (LLD §1.9, F4 — the module half) — PR-F3
# ---------------------------------------------------------------------------

def _apply_post_filters(cards, report, *,
                        untouchable_ids=None, not_interested_ids=None,
                        acquire_positions=None, trade_away_positions=None,
                        past_decision_keys=None, seed_elo=None,
                        players=None, max_per_opponent=None):
    """§1.9 post-score filters over the RANKED list, order pinned (PRD §6):
    min_them/min_aggregate → untouchables → not-interested → position pins →
    R4/already-swiped → C4 centerpiece cap → max_per_opponent. Each drop
    counts into `report.post_filtered` (max_per_opponent excepted — the
    adapter always passes None, the gen_v2/operator no-truncation contract,
    §8 R-g, and the pinned counter key set does not name it). A preference
    hides a card AFTER scoring — it never shrinks the search
    (`test_untouchable_enumerated_then_filtered`)."""
    untouchable_ids = set(untouchable_ids or ())
    not_interested_ids = set(not_interested_ids or ())
    past_decision_keys = past_decision_keys or set()
    acquire = [p for p in (acquire_positions or ()) if p]
    away = [p for p in (trade_away_positions or ()) if p]
    players = players or {}
    min_them = ts._c("fit_min_them")
    min_aggregate = ts._c("fit_min_aggregate")

    def _has_pos(pids, wanted) -> bool:
        """≥1 NON-PICK player at a listed position (LLD §1.9 step 4)."""
        for pid in pids:
            p = players.get(pid)
            if p is None or ts.is_pick_asset(p):
                continue
            if getattr(p, "position", None) in wanted:
                return True
        return False

    kept: list = []
    for card in cards:
        give = card.give_player_ids
        recv = card.receive_player_ids
        fit = card.fit
        # 1. Presentment floors (both default 0 = off) — FIRST, so the later
        #    counters describe the visible universe (LLD §8 R-i).
        if min_them > 0 and fit["them"] < min_them:
            report.post_filtered["min_them"] += 1
            continue
        if min_aggregate > 0 and fit["aggregate"] < min_aggregate:
            report.post_filtered["min_aggregate"] += 1
            continue
        # 2. Untouchables — the viewer never sends one.
        if untouchable_ids and set(give) & untouchable_ids:
            report.post_filtered["untouchable"] += 1
            continue
        # 3. Not-interested — the viewer never receives one.
        if not_interested_ids and set(recv) & not_interested_ids:
            report.post_filtered["not_interested"] += 1
            continue
        # 4. Position pins — only when the user set them.
        if (acquire and not _has_pos(recv, acquire)) or \
                (away and not _has_pos(give, away)):
            report.post_filtered["position_prefs"] += 1
            continue
        # 5. G6 R4 + already-swiped — post-score by operator ruling
        #    (PRD §6.4): fit's `enumerated` includes these, unlike gen_v2.
        if (frozenset(give), frozenset(recv)) in past_decision_keys:
            report.post_filtered["r4_swiped"] += 1
            continue
        kept.append(card)

    # 6. C4 centerpiece cap — replicate the live loop
    #    (trade_service._dedup_and_sort's C4 block): keep-first in rank
    #    order; cap <= 0 or an empty seed map ⇒ no-op (no consensus ⇒
    #    "centerpiece" degenerates to "largest player id").
    cap = int(ts._c("deck_headliner_cap"))
    if cap > 0 and seed_elo:
        seen_heads: dict[str, int] = {}
        capped: list = []
        for c in kept:
            head = ts.deck_centerpiece(c.give_player_ids,
                                       c.receive_player_ids, seed_elo)
            if head is not None:
                if seen_heads.get(head, 0) >= cap:
                    report.post_filtered["c4_centerpiece"] += 1
                    continue
                seen_heads[head] = seen_heads.get(head, 0) + 1
            capped.append(c)
        kept = capped

    # 7. max_per_opponent — an int keeps the top N per target in rank
    #    order; None (the adapter's value) = full ranked list (§8 R-g).
    if max_per_opponent is not None:
        n = int(max_per_opponent)
        per: dict[str, int] = {}
        limited: list = []
        for c in kept:
            uid = c.target_user_id
            if per.get(uid, 0) >= n:
                continue
            per[uid] = per.get(uid, 0) + 1
            limited.append(c)
        kept = limited
    return kept


# ---------------------------------------------------------------------------
# M3 helper (LLD §1.11 — lives here so the scorer has one home)
# ---------------------------------------------------------------------------

def stamp_fit_diag(arm_lists: dict[str, list], *, players: dict,
                   league: ts.League, user_elo: dict[str, float],
                   seed_elo: dict[str, float]) -> None:
    """M3/R-11 — set `card.fit_diag = {"you", "them", "bucket", "ver",
    "lenses"}` on EVERY card of EVERY arm's ranked list (the `lenses` key is
    an additive coordinator extension of the LLD's 4-key shape: the readout's
    lens-calibration queries COALESCE fit.lenses onto fit_diag.lenses and
    must work across arms; SCORER_VERSION already covers the shape). Fit's
    own cards reuse `card.fit` (identical numbers by construction). Other
    arms' cards are scored fresh: resolve the partner via
    {m.user_id: m for m in league.members}, compute you/them per §1.7
    (weights and lenses included), bucket per _bucket.
    Per-card try/except: a card that cannot be scored (unknown partner,
    empty sides) gets `card.fit_diag = None` — the key must exist DOWNSTREAM
    (features_json writes it null), absence is impossible (M4 contract).
    Purely attribute-setting: no return, no reordering, no score mutation —
    inertness is enforced by test_fit_diag_inert."""
    members = {m.user_id: m for m in league.members}
    viewer_boarded = bool(user_elo)
    _cv: dict[str, float] = {}

    def cval(pid: str) -> float:
        v = _cv.get(pid)
        if v is None:
            v = ts.elo_to_value(seed_elo.get(pid, 1500.0))
            _cv[pid] = v
        return v

    uval = None
    if viewer_boarded:
        _uv: dict[str, float] = {}

        def uval(pid: str) -> float:
            v = _uv.get(pid)
            if v is None:
                v = ts.elo_to_value(user_elo.get(pid, 1500.0))
                _uv[pid] = v
            return v

    _ovals: dict[str, object] = {}   # partner uid → cached accessor

    def _oval_for(member) -> object:
        fn = _ovals.get(member.user_id)
        if fn is None:
            _ov: dict[str, float] = {}
            _board = member.elo_ratings

            def fn(pid: str, _board=_board, _ov=_ov) -> float:
                v = _ov.get(pid)
                if v is None:
                    v = ts.elo_to_value(_board.get(pid, 1500.0))
                    _ov[pid] = v
                return v
            _ovals[member.user_id] = fn
        return fn

    for cards in arm_lists.values():
        for card in cards or ():
            try:
                fit = getattr(card, "fit", None)
                if isinstance(fit, dict):
                    # Fit's own card — identical numbers by construction.
                    card.fit_diag = {
                        "you": fit["you"], "them": fit["them"],
                        "bucket": fit["bucket"], "ver": fit["ver"],
                        "lenses": fit["lenses"],
                    }
                    continue
                give = list(getattr(card, "give_player_ids", None) or ())
                recv = list(getattr(card, "receive_player_ids", None) or ())
                member = members.get(getattr(card, "target_user_id", None))
                if member is None or not give or not recv:
                    card.fit_diag = None
                    continue
                partner_boarded = bool(member.has_rankings
                                       and member.elo_ratings)
                cand = _score_candidate(
                    give, recv, cval=cval, uval=uval,
                    oval=_oval_for(member) if partner_boarded else None,
                    viewer_boarded=viewer_boarded,
                    partner_boarded=partner_boarded, seed_elo=seed_elo)
                p = cand["payload"]
                card.fit_diag = {
                    "you": p["you"], "them": p["them"],
                    "bucket": p["bucket"], "ver": p["ver"],
                    "lenses": p["lenses"],
                }
            except Exception:
                card.fit_diag = None
