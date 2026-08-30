"""Trade engine v3 — exact per-pair package optimizer + 3-team cycles.

Tier 3 rebuild (docs/plans/trade-engine-tier3-rebuild.md), work items
3.1 (exact package construction), 3.2 (lineup-feasibility hard constraint),
3.3 (3-team cycle trades) and 3.4 (sweeteners). Work item 3.5 (fitted
consensus values) is out of scope here.

Pure Python, no new dependencies — this is the spec's "Approach B"
no-dependency path realized as exhaustive enumeration over pruned pools
(the OR-Tools ILP of Approach A was explicitly rejected as a dependency).

GUARANTEE: generate_pair_trades_v3 returns the EXACT top-K packages by the
v2 composite objective **within the pruned candidate pools** (top
``v3_pool_size`` players per side by valuation divergence, plus any pinned
give players). Every give-subset (size 1-3) x receive-subset (size 1-3)
with |give| - |receive| <= 1 inside those pools is evaluated — no time
budget, no enumeration-order truncation. The only approximation left is
the pool prune itself. Under flag ``trade.pool_calibration`` that prune
ranks on a board-scale-calibrated divergence so a compressed opponent
board cannot push the user's studs out of the pool (see the prune block).

The objective is intentionally IDENTICAL to the v2 scorer
(trade_service._generate_for_pair_v2): same value space, same marginal
valuation, same surplus gates, fairness gate and composite blend. v3
changes how candidates are constructed and selected, not what "good"
means. Several small private helpers from trade_service are replicated
here (marked with TODO refactor comments) because they are closures /
methods that cannot be imported without touching trade_service.py.

Config keys read live via trade_service._cfg with inline defaults (nothing
added to trade_service._DEFAULT_CFG for these):

    v3_pool_size          12     per-side candidate pool size (3.1 prune)
    sweetener_band        0.15   how far below fairness_threshold a
                                 near-miss may sit and still be sweetened
    sweetener_max_cards   2      max sweetened cards emitted per pair
    cycle_edge_min_gain   100.0  min single-asset transfer gain for a
                                 directed edge in the cycle graph
    cycle_min_net         200.0  min per-team net surplus for a 3-cycle
    cycle_max_results     3      max cycles returned

Every other knob this module reads — including C4's ``v3_shape_max_delta``
(max |len(give) - len(receive)| a package shape may carry; 1 = the
historical rule, 2 unlocks the 3-for-1 / 1-for-3 subsets the enumeration
already builds) — goes through ``trade_service._c``, which consults the
``_cfg_override`` thread-local before the live map.
"""

from __future__ import annotations

import math
import uuid
from itertools import combinations

from .feature_flags import FLAGS
from . import trade_service as _ts
from .trade_service import (
    LeagueMember,
    TradeCard,
    _STARTER_NEED,
    _c,
    _harmonic_mean,
    _starters_at,
    _value_uncertainty,
    mismatch_damp,
    rank_fairness,
    age_pref_value,
    elo_to_value,
    avoid_ok,
    filler_ok,
    fit_premium_1for1,
    pick_swap_ok,
    marginal_value,
    outlook_blend_mult,
    package_value_v2,
    replacement_levels,
)

__all__ = ["generate_pair_trades_v3", "find_three_team_cycles",
           "close_value_gap"]


# ---------------------------------------------------------------------------
# Replicated helpers (small, stable; shared refactor is a follow-up)
# ---------------------------------------------------------------------------


def _tier_mult(elo_map: dict[str, float], pids) -> float:
    """Tier-priority multiplier from the best player across both sides.

    Replicates TradeService._tier_mult_v2 (a method, so not importable
    standalone) — same Elo bands, same tier_mult_* config keys.
    TODO refactor shared helper in trade_service.
    """
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


def _consensus_packages(give_ids, recv_ids, seed_value):
    """Consensus package values for both sides (v2 value space, trade-wide
    v_max). Returns (give_pkg, recv_pkg)."""
    gvals = [seed_value(p) for p in give_ids]
    rvals = [seed_value(p) for p in recv_ids]
    v_max = max(gvals + rvals)
    return (package_value_v2(gvals, v_max, n_other=len(recv_ids),
                             other_values=rvals),
            package_value_v2(rvals, v_max, n_other=len(give_ids),
                             other_values=gvals))


def _fairness_v3(give_ids, recv_ids, seed_value, confidence,
                 fairness_threshold):
    """Consensus fairness with the range-overlap gate.

    Mirrors trade_service._generate_for_pair_v2._fairness — TODO refactor
    shared helper. Extended to also return the raw point ratio and the
    consensus package values so the sweetener pass (3.4) can classify
    near-misses and find the under-paying side.

    Returns (fairness_or_None, point_ratio, give_pkg, recv_pkg):
    fairness is None when the gate fails (no range overlap AND point ratio
    below fairness_threshold).
    """
    gvals = [seed_value(p) for p in give_ids]
    rvals = [seed_value(p) for p in recv_ids]
    v_max = max(gvals + rvals)
    gv = package_value_v2(gvals, v_max, n_other=len(recv_ids),
                          other_values=rvals)
    rv = package_value_v2(rvals, v_max, n_other=len(give_ids),
                          other_values=gvals)
    if gv <= 0 or rv <= 0:
        return 1.0, 1.0, gv, rv
    ratio = min(gv, rv) / max(gv, rv)
    g_unc = (sum(v * _value_uncertainty(p, confidence)
                 for v, p in zip(gvals, give_ids)) / sum(gvals))
    r_unc = (sum(v * _value_uncertainty(p, confidence)
                 for v, p in zip(rvals, recv_ids)) / sum(rvals))
    overlap = (gv * (1 + g_unc) >= rv * (1 - r_unc)
               and rv * (1 + r_unc) >= gv * (1 - g_unc))
    if not overlap and ratio < fairness_threshold:
        return None, round(ratio, 3), gv, rv
    return round(ratio, 3), round(ratio, 3), gv, rv


# ---------------------------------------------------------------------------
# 3.2 — lineup feasibility (hard constraint)
# ---------------------------------------------------------------------------


def _pos_counts(roster_ids, players) -> dict[str, int]:
    """Count QB/RB/WR/TE bodies on a roster (other positions ignored)."""
    counts = {pos: 0 for pos in _STARTER_NEED}
    for pid in roster_ids:
        p = players.get(pid)
        pos = getattr(p, "position", None) if p else None
        if pos in counts:
            counts[pos] += 1
    return counts


def _feasible_after(base_counts: dict[str, int], out_delta: dict[str, int],
                    in_delta: dict[str, int], scoring_format: str) -> bool:
    """True when a roster still fields a legal starting lineup post-trade.

    Hard constraint (3.2): after the trade the roster must keep at least
    _STARTER_NEED[pos] players at every position (QB requirement bumped to
    2 when scoring_format starts with "sf" — superflex). FLEX slots are
    deliberately IGNORED: we only enforce the dedicated positional slots,
    since any QB/RB/WR/TE body can cover FLEX and bench size is not
    modeled here. A roster already below need at a position yields no
    trades unless the trade itself fills that deficit.
    """
    for pos, base in base_counts.items():
        need = _starters_at(pos, scoring_format)
        if base - out_delta.get(pos, 0) + in_delta.get(pos, 0) < need:
            return False
    return True


def _subset_pos_delta(ids, players) -> dict[str, int]:
    delta: dict[str, int] = {}
    for pid in ids:
        p = players.get(pid)
        pos = getattr(p, "position", None) if p else None
        if pos in _STARTER_NEED:
            delta[pos] = delta.get(pos, 0) + 1
    return delta


# ---------------------------------------------------------------------------
# 3.1 + 3.2 + 3.4 — exact per-pair package construction
# ---------------------------------------------------------------------------


def generate_pair_trades_v3(
    *,
    user_id: str,
    shrunk_user_elo: dict[str, float],
    user_value: dict[str, float],
    user_roster: list[str],
    opponent: LeagueMember,
    league_id: str,
    seed_elo: dict[str, float],
    confidence: dict[str, int] | None,
    max_cards: int,
    fairness_threshold: float,
    scoring_format: str = "1qb_ppr",
    acquire_positions: list[str] | None = None,
    trade_away_positions: list[str] | None = None,
    avoid_positions: list[str] | None = None,   # #360 — receive-side exclusion
    pinned_give_players: list[str] | None = None,
    pinned_receive_players: list[str] | None = None,
    pinned_give_mode: str = "any",
    players: dict,
    alpha_opp: float | None = None,
    untouchable_ids: set | None = None,
    target_ids: set | None = None,
    not_interested_ids: set | None = None,
    raw_user_elo: dict[str, float] | None = None,
    user_needs: set | None = None,
    presentment_ok_fn=None,     # G6 rules R1/R2/R3/R5 (trade.presentment_rules)
                                # — bound predicate from _generate_trades_v2;
                                # None = flag off, byte-identical path.
) -> list[TradeCard]:
    """Exact v3 generation for one (user, opponent) pair.

    GUARANTEE: exact top-K (K = max_cards) by the v2 composite objective
    within the pruned candidate pools — every give-subset (1-3) x
    receive-subset (1-3) with |give|-|receive| <= 1 over the top
    ``v3_pool_size`` players per side (by valuation divergence; pinned
    give players always included) is scored. No deadline, no iteration
    budget, no enumeration-order bias.

    Objective is byte-for-byte the v2 semantics from
    trade_service._generate_for_pair_v2: marginal (over-replacement)
    values when FLAGS.trade_marginal_value, package_value_v2 per side with
    the trade-wide best asset in that side's own space, waiver-slot cost
    on the side receiving more players, both-sides surplus gate, consensus
    range-overlap fairness, composite = mismatch_weight * min(hm, cap)/cap
    + fairness_weight * fairness, times the tier multiplier. Plus the new
    3.2 hard constraint: post-trade lineup feasibility for BOTH rosters.

    3.4: when fewer than max_cards organic cards clear the gates, up to
    ``sweetener_max_cards`` near-miss combos (fairness just below the
    band) are rescued by adding the cheapest consensus-value player from
    the under-paying side's roster. Sweeteners are PLAYERS ONLY: draft
    picks are not on LeagueMember.roster in this code path, so a pick can
    never be selected (FAAB likewise has no asset representation yet).
    Sweetened cards carry a ``sweetener`` attribute:
    {"player_id": pid, "side": "give"|"receive"}.
    """
    opp_elo    = opponent.elo_ratings
    pinned_set = set(pinned_give_players) if pinned_give_players else None
    # #174 — "all" ⇒ the give side must include EVERY pinned player
    # (trade-as-one-package); "any" keeps the historical ≥1 semantics.
    pinned_all = pinned_set is not None and pinned_give_mode == "all"
    # FB-47 — pinned ACQUIRE targets: cards must receive at least one.
    pinned_recv_set = (set(pinned_receive_players)
                       if pinned_receive_players else None)

    MARGINAL = FLAGS.trade_marginal_value
    MIN_SIDE = (_c("min_side_surplus_marginal") if MARGINAL
                else _c("min_side_surplus"))
    GAIN_CAP = max(_c("mutual_gain_cap"), 1.0)
    WAIVER   = _c("waiver_slot_cost")
    MAX_GAP  = _c("trade_elo_gap_max")
    W_MIS    = _c("mismatch_weight")
    W_FAIR   = _c("fairness_weight")
    POOL_P   = int(_ts._cfg.get("v3_pool_size", 12))
    # C4 (docs/plans/knockout-refine/plan.md §3) — the package-shape rule is
    # a knob, not a literal. Read at CALL time, never bound at import
    # (D-098 / G-058 cause 3), and through `_c` rather than `_ts._cfg.get`:
    # the key lives in `trade_service._DEFAULT_CFG`, so `_c` is what the
    # sibling knobs above use, and it is the only reader that honours the
    # `_cfg_override` thread-local. That overlay is not a detail — it is how
    # the #189 relaxed pass and bake-off arm A's `MODEL_A_PROFILE` pin of
    # this knob to 1.0 are applied, and `_ts._cfg.get` cannot see it, so an
    # arm-A pin would silently no-op the moment prod flips the row to 2.
    # Default 1 is the historical `> 1` rule, byte-identical.
    SHAPE_D  = int(_c("v3_shape_max_delta"))
    SW_BAND  = float(_ts._cfg.get("sweetener_band", 0.15))
    SW_MAX   = int(_ts._cfg.get("sweetener_max_cards", 2))
    TARGET_BONUS = _c("target_acquire_bonus")   # #2 per-target reward
    MULT_CAP     = _c("pos_multiplier_cap")
    _targets     = target_ids or set()

    # Interview 2026-07-17 ("loosen it") — divergence cards are already
    # gated by both-sides surplus on the members' REAL boards, so the
    # consensus fairness check here is only an extreme-case veto. All
    # downstream uses (gate, sweetener band, sweetener target) inherit
    # the loosened bar. Consensus-basis cards (other generator) keep the
    # caller's full threshold.
    fairness_threshold = min(fairness_threshold,
                             _c("fairness_floor_divergence"))

    # --- per-player value accessors (cached), same spaces as v2 ----------
    _def_uval = elo_to_value(1500.0)

    def _uv(pid: str) -> float:
        return user_value.get(pid, _def_uval)

    _vo_cache: dict[str, float] = {}

    def _vo(pid: str) -> float:
        v = _vo_cache.get(pid)
        if v is None:
            v = elo_to_value(opp_elo.get(pid, 1500.0))
            # Backlog #1 — opponent outlook blend (mirrors v2 _vo). None ⇒
            # flag off ⇒ raw value. Propagates to marginal/replacement paths.
            if alpha_opp is not None:
                p = players.get(pid)
                v *= outlook_blend_mult(
                    getattr(p, "position", None) if p else None,
                    getattr(p, "age", None) if p else None,
                    alpha_opp,
                )
            _vo_cache[pid] = v
        return v

    _sv_cache: dict[str, float] = {}

    def _sv(pid: str) -> float:
        v = _sv_cache.get(pid)
        if v is None:
            # Age-preference adjusted (2026-08-29) — mirrors v2's _vs so the
            # two engines cannot price an age band differently.
            v = age_pref_value(elo_to_value(seed_elo.get(pid, 1500.0)),
                               players.get(pid))
            _sv_cache[pid] = v
        return v

    # Tier 2 marginal valuation — replacement levels once per pair, from
    # the PRE-trade rosters, in each side's own value space (reused from
    # trade_service; identical to the v2 setup).
    if MARGINAL:
        user_repl = replacement_levels(user_roster, _uv, players,
                                       scoring_format)
        opp_repl = replacement_levels(opponent.roster, _vo, players,
                                      scoring_format)

        _mu_cache: dict[str, float] = {}

        def _user_val(pid: str) -> float:
            v = _mu_cache.get(pid)
            if v is None:
                v = marginal_value(pid, _uv, user_repl, players,
                                   scoring_format)
                _mu_cache[pid] = v
            return v

        _mo_cache: dict[str, float] = {}

        def _opp_val(pid: str) -> float:
            v = _mo_cache.get(pid)
            if v is None:
                v = marginal_value(pid, _vo, opp_repl, players,
                                   scoring_format)
                _mo_cache[pid] = v
            return v
    else:
        _user_val = _uv
        _opp_val = _vo

    # --- candidate pools (3.1 prune) --------------------------------------
    # Top-P per side by valuation DIVERGENCE: gives the opponent over-values
    # relative to the user, receives the user over-values relative to the
    # opponent. Pinned give players are ALWAYS in the give pool, regardless
    # of divergence rank.
    known_user = [p for p in user_roster
                  if p in shrunk_user_elo and p in opp_elo
                  and not (untouchable_ids and p in untouchable_ids)]  # #2
    # #163 — not-interested players never enter the receive pool (dropped at
    # the source; the pinned/target re-adds below iterate this filtered list).
    # #360 — avoided POSITIONS are dropped at the same source, for the same
    # reason: an exclusion always wins over a pin (PRD R-8 / D-360-3(b)).
    _avoid = set(avoid_positions or ())
    known_opp = [p for p in opponent.roster
                 if p in shrunk_user_elo and p in opp_elo
                 and not (not_interested_ids and p in not_interested_ids)
                 and avoid_ok(p, players, _avoid)]
    # Board-scale calibration for the prune ONLY (flag trade.pool_calibration
    # — field bug 2026-08-15, docs/plans/compressed-board-pool/scope.md).
    # The raw key ``_vo - _uv`` is not invariant to a board-wide scale
    # difference: elo_to_value is exponential, so an opponent board sitting
    # uniformly lower than the user's (a floor-pinned, barely-started board)
    # deflates high-Elo players far more than low-Elo ones. Every tradeable
    # stud then sorts BELOW the user's worthless bench, the top-POOL_P fills
    # with junk, and the pair yields no cards at all. That deflation says
    # nothing about WHICH player either side prefers, so remove it: rescale
    # the opponent's value space by the geometric-mean ratio over the assets
    # in play — the same players priced on both boards, so no roster-strength
    # confound. Equivalent to shifting the opponent's board onto the user
    # board's mean Elo. Ordering becomes exactly invariant to a board offset
    # and is unchanged when the two boards already share a mean.
    #
    # Computed from the _uv/_vo accessors (not the raw Elo dicts) so it stays
    # consistent with whatever those actually return, including the #1
    # outlook blend baked into _vo. Prune ordering only: every surplus,
    # fairness and composite number below still uses each side's own raw
    # value space, untouched.
    _pool_scale = 1.0
    if FLAGS.trade_pool_calibration:
        _logs = [(math.log(u), math.log(o)) for u, o in
                 ((_uv(p), _vo(p)) for p in sorted(set(known_user) | set(known_opp)))
                 if u > 0.0 and o > 0.0]
        if _logs:
            _pool_scale = math.exp(
                (sum(lu for lu, _ in _logs) - sum(lo for _, lo in _logs))
                / len(_logs))

    def _div(pid: str) -> float:
        """Give-side prune key: how much more the opponent values ``pid``
        than the user does, on a calibrated board scale. Receive side is the
        exact negation. Flag off ⇒ _pool_scale is 1.0 and this is the
        historical ``_vo - _uv``."""
        return _vo(pid) * _pool_scale - _uv(pid)

    give_pool = sorted(known_user, key=_div, reverse=True)[:POOL_P]
    if pinned_set:
        for pid in user_roster:
            if pid in pinned_set and pid not in give_pool:
                give_pool.append(pid)
    recv_pool = sorted(known_opp, key=lambda p: -_div(p), reverse=True)[:POOL_P]
    # FB-47 — pinned acquire targets always survive the prune, mirroring
    # the pinned-give rule above.
    if pinned_recv_set:
        for pid in known_opp:
            if pid in pinned_recv_set and pid not in recv_pool:
                recv_pool.append(pid)
    # Backlog #2 — targets the opponent rosters survive the prune too.
    if target_ids:
        for pid in known_opp:
            if pid in target_ids and pid not in recv_pool:
                recv_pool.append(pid)
    if not give_pool or not recv_pool:
        return []

    # --- per-combo filters (identical semantics to v2) ---------------------
    _acq = acquire_positions or []
    _away = trade_away_positions or []

    def _positions_ok(give_ids, recv_ids) -> bool:
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

    def _gap_ok(give_ids, recv_ids) -> bool:
        """User-Elo gap guard on the shrunk Elo (same as v2)."""
        if MAX_GAP <= 0:
            return True
        max_give = max(shrunk_user_elo.get(p, 1500) for p in give_ids)
        max_recv = max(shrunk_user_elo.get(p, 1500) for p in recv_ids)
        return abs(max_recv - max_give) <= MAX_GAP

    # 3.2 — feasibility on the FULL rosters (not just the known-Elo pools).
    user_counts = _pos_counts(user_roster, players)
    opp_counts = _pos_counts(opponent.roster, players)

    def _both_feasible(give_ids, recv_ids) -> bool:
        g_delta = _subset_pos_delta(give_ids, players)
        r_delta = _subset_pos_delta(recv_ids, players)
        return (_feasible_after(user_counts, g_delta, r_delta, scoring_format)
                and _feasible_after(opp_counts, r_delta, g_delta,
                                    scoring_format))

    def _surpluses(give_ids, recv_ids):
        """Both sides' package surpluses — exactly the v2 _consider math."""
        uvals_give = [_user_val(p) for p in give_ids]
        uvals_recv = [_user_val(p) for p in recv_ids]
        u_max = max(uvals_give + uvals_recv)
        give_val_user = package_value_v2(uvals_give, u_max, n_other=len(recv_ids),
                                         other_values=uvals_recv)
        recv_val_user = package_value_v2(uvals_recv, u_max, n_other=len(give_ids),
                                         other_values=uvals_give)

        ovals_give = [_opp_val(p) for p in give_ids]
        ovals_recv = [_opp_val(p) for p in recv_ids]
        o_max = max(ovals_give + ovals_recv)
        give_val_opp = package_value_v2(ovals_give, o_max, n_other=len(recv_ids),
                                        other_values=ovals_recv)   # opp receives
        recv_val_opp = package_value_v2(ovals_recv, o_max, n_other=len(give_ids),
                                        other_values=ovals_give)   # opp gives

        # Waiver-slot cost (A3) on the side receiving MORE players.
        extra = len(recv_ids) - len(give_ids)
        if extra > 0:
            recv_val_user -= WAIVER * extra
        elif extra < 0:
            give_val_opp -= WAIVER * (-extra)

        return recv_val_user - give_val_user, give_val_opp - recv_val_opp

    def _composite(hm: float, fairness: float, all_ids, recv_ids=None,
                   give_ids=None) -> float:
        # C1/C5 (2026-08-18, docs/plans/engine-quality/scope.md) — RANKING
        # terms only; the card stamps the real full-package fairness and
        # every gate above already ran on the real package. give_ids=None
        # (no split available) skips C1 only, never C5.
        _fair_rank = fairness
        if give_ids is not None and recv_ids is not None:
            _fair_rank = rank_fairness(fairness, give_ids, recv_ids,
                                       _sv, _uv, _vo)
        comp = (W_MIS * min(hm, GAIN_CAP) / GAIN_CAP
                * mismatch_damp(all_ids, _sv, confidence)
                + W_FAIR * _fair_rank)
        comp *= _tier_mult(shrunk_user_elo, all_ids)
        # Backlog #2 — per-target reward, after the mutual-gain gates, capped.
        if _targets and recv_ids:
            n_t = len(set(recv_ids) & _targets)
            if n_t:
                comp *= min(1.0 + TARGET_BONUS * n_t, MULT_CAP)
        return comp

    # --- exact enumeration -------------------------------------------------
    give_subsets = [list(c) for size in (1, 2, 3)
                    for c in combinations(give_pool, size)]
    recv_subsets = [list(c) for size in (1, 2, 3)
                    for c in combinations(recv_pool, size)]

    scored: list[tuple] = []        # (composite, order, hm, fairness, g, r)
    near_misses: list[tuple] = []   # (hm, ratio, give, recv) — 3.4 input
    order = 0

    for give_ids in give_subsets:
        if pinned_set:
            if pinned_all:
                if not pinned_set <= set(give_ids):
                    continue
            elif not (set(give_ids) & pinned_set):
                continue
        for recv_ids in recv_subsets:
            if pinned_recv_set and not (set(recv_ids) & pinned_recv_set):
                continue
            if abs(len(give_ids) - len(recv_ids)) > SHAPE_D:
                continue
            if not _positions_ok(give_ids, recv_ids):
                continue
            if not _gap_ok(give_ids, recv_ids):
                continue
            # #108 — never offer a 1-for-1 that sends a player the user
            # ranks above the received player on their own raw board
            # (mirrors the v2 _consider gate; the shrunk surplus below can
            # be inverted by consensus pull on lightly-sampled players).
            # Phase 2 exception (flag trade.fit_premium): a small raw-board
            # loss that fills a positional need survives, flagged.
            _allowed, _fit_paid = fit_premium_1for1(
                give_ids, recv_ids, raw_user_elo, players, user_needs)
            if not _allowed:
                continue
            # #227 — a 1-for-1 pick-for-pick swap is pointless churn
            # (mirrors the v2 _consider gate; gated before the near-miss
            # collection below so the 3.4 sweetener pass can't rescue it).
            if not pick_swap_ok(give_ids, recv_ids, players, _sv):
                continue
            # #141 — junk-filler gate: any piece beyond a side's headliner
            # must clear filler_min_frac of that headliner on the MAX of
            # the two raw boards (mirrors the v2 _consider gate).
            if not filler_ok(give_ids, recv_ids, _uv, _vo):
                continue
            # G6 presentment rules (R1 #340 / R2 #341 / R3 #339 / R5 #304)
            # — BEFORE _both_feasible/surplus/fairness so a killed shape can
            # never reach the near-miss collection below and be
            # sweetener-rescued (mirrors the #227 placement note above).
            if presentment_ok_fn is not None \
                    and not presentment_ok_fn(give_ids, recv_ids):
                continue
            if not _both_feasible(give_ids, recv_ids):    # 3.2 hard gate
                continue

            user_surplus, opp_surplus = _surpluses(give_ids, recv_ids)
            if user_surplus < MIN_SIDE or opp_surplus < MIN_SIDE:
                continue

            fairness, ratio, _gv, _rv = _fairness_v3(
                give_ids, recv_ids, _sv, confidence, fairness_threshold)
            if fairness is None:
                # 3.4 — remember near-misses inside the sweetener band.
                if fairness_threshold - SW_BAND <= ratio < fairness_threshold:
                    hm = _harmonic_mean(user_surplus, opp_surplus)
                    near_misses.append((hm, ratio, give_ids, recv_ids))
                continue

            hm = _harmonic_mean(user_surplus, opp_surplus)
            order -= 1   # earlier combos win composite ties (desc sort)
            scored.append((_composite(hm, fairness, give_ids + recv_ids,
                                      recv_ids, give_ids),
                           order, hm, fairness, give_ids, recv_ids,
                           _fit_paid))

    scored.sort(key=lambda e: (e[0], e[1]), reverse=True)

    def _card(composite, hm, fairness, give_ids, recv_ids,
              fit_paid=None) -> TradeCard:
        # Consensus package values for the TradeValueBar — _sv is the same
        # value-space consensus fn (elo_to_value over the seed) the calculator
        # uses and fairness was priced on, so a deck card and the calculator
        # show identical numbers for the same players.
        _gv, _rv = _consensus_packages(give_ids, recv_ids, _sv)
        card = TradeCard(
            trade_id           = str(uuid.uuid4())[:8],
            league_id          = league_id,
            proposing_user_id  = user_id,
            target_user_id     = opponent.user_id,
            target_username    = opponent.username,
            give_player_ids    = list(give_ids),
            receive_player_ids = list(recv_ids),
            mismatch_score     = round(hm, 1),
            fairness_score     = round(fairness, 3),
            composite_score    = round(composite, 3),
            basis              = "divergence",
            give_value         = round(_gv, 1),
            receive_value      = round(_rv, 1),
        )
        if fit_paid is not None:
            p = players.get(recv_ids[0])
            card.fit_premium = {
                "value_paid": fit_paid,
                "position": getattr(p, "position", None) if p else None,
            }
        return card

    # Diverse top-K (greedy): exact enumeration surfaces every sibling of a
    # strong core (same trade ± one bench throw-in), so a plain scored[:K]
    # returns K near-duplicates. Walk the ranked list and skip combos whose
    # asset set overlaps an already-picked card by more than
    # v3_diversity_max_overlap (Jaccard over give ∪ receive). The best
    # variant of each core survives; the siblings make room for the next
    # genuinely different trade idea.
    _MAX_OVERLAP = float(_ts._cfg.get("v3_diversity_max_overlap", 0.4))
    picked: list = []
    for entry in scored:
        if len(picked) >= max_cards:
            break
        assets = set(entry[4]) | set(entry[5])
        if all(
            len(assets & (set(p[4]) | set(p[5])))
            / len(assets | (set(p[4]) | set(p[5]))) <= _MAX_OVERLAP
            for p in picked
        ):
            picked.append(entry)
    cards = [_card(comp, hm, fair, g, r, fp)
             for comp, _o, hm, fair, g, r, fp in picked]

    # --- 3.4 sweetener pass -------------------------------------------------
    if len(cards) < max_cards and near_misses and SW_MAX > 0:
        organic_keys = {(frozenset(c.give_player_ids),
                         frozenset(c.receive_player_ids)) for c in cards}
        budget = min(SW_MAX, max_cards - len(cards))
        near_misses.sort(key=lambda e: e[0], reverse=True)   # best hm first
        for _hm0, _ratio0, give_ids, recv_ids in near_misses:
            if budget <= 0:
                break
            sweet = _try_sweeten(
                give_ids, recv_ids,
                user_roster=user_roster, opp_roster=opponent.roster,
                seed_value=_sv, fairness_threshold=fairness_threshold,
                min_side=MIN_SIDE, surpluses=_surpluses, gap_ok=_gap_ok,
                both_feasible=_both_feasible, players=players,
                untouchable_ids=untouchable_ids,
                not_interested_ids=not_interested_ids,               # #163
                avoid_positions=_avoid,                              # #360
                filler_ok_fn=lambda g, r: filler_ok(g, r, _uv, _vo),  # #141
                presentment_ok_fn=presentment_ok_fn,   # G6 — re-validate the
            )                                          # SWEETENED combo (R-6)
            if sweet is None:
                continue
            s_pid, side, new_give, new_recv, user_s, opp_s, ratio = sweet
            # C3 — re-validate the SWEETENED combo: the sweetener can itself
            # be a pick, and adding one to a side that faces a same-value pick
            # turns the deal into the matched-pair churn the gate now catches.
            # (Same re-validation slot the G6 rules already use.)
            if not pick_swap_ok(new_give, new_recv, players, _sv):
                continue
            key = (frozenset(new_give), frozenset(new_recv))
            if key in organic_keys:
                continue
            hm = _harmonic_mean(user_s, opp_s)
            comp = _composite(hm, ratio, new_give + new_recv, new_recv,
                              new_give)
            card = _card(comp, hm, ratio, new_give, new_recv)
            card.sweetener = {"player_id": s_pid, "side": side}
            cards.append(card)
            organic_keys.add(key)
            budget -= 1

    # --- 2026-08-21 gap auto-sweetener (sweetener_gap_threshold) ----------
    # Runs at generation time on this pair's finished cards (never
    # post-draft): a card whose absolute consensus gap exceeds the
    # threshold is re-balanced in place by adding the smallest sufficient
    # equalizer from the richer side's roster, re-earning every gate. A
    # card the pass cannot close is kept unsweetened — the pass narrows
    # gaps, it does not shrink the deck. ≤ 0 disables (arm A's pin).
    GAP_THR = _c("sweetener_gap_threshold")
    if GAP_THR > 0 and cards:
        card_keys = {(frozenset(c.give_player_ids),
                      frozenset(c.receive_player_ids)) for c in cards}

        def _gap_extra_ok(g, r):
            if not filler_ok(g, r, _uv, _vo):
                return False
            if not pick_swap_ok(g, r, players, _sv):
                return False
            if presentment_ok_fn is not None and not presentment_ok_fn(g, r):
                return False
            if not _gap_ok(g, r):
                return False
            u_s, o_s = _surpluses(g, r)
            return u_s >= MIN_SIDE and o_s >= MIN_SIDE

        for card in cards:
            closed = close_value_gap(
                card.give_player_ids, card.receive_player_ids,
                seed_value=_sv, gap_threshold=GAP_THR,
                fairness_threshold=fairness_threshold,
                user_roster=user_roster, opp_roster=opponent.roster,
                players=players, scoring_format=scoring_format,
                untouchable_ids=untouchable_ids,
                not_interested_ids=not_interested_ids,
                extra_ok_fn=_gap_extra_ok)
            if closed is None:
                continue
            s_pid, side, new_give, new_recv, n_gv, n_rv, ratio = closed
            new_key = (frozenset(new_give), frozenset(new_recv))
            if new_key in card_keys:      # would collide with a sibling card
                continue
            gap_before = abs((card.give_value or 0.0)
                             - (card.receive_value or 0.0))
            user_s, opp_s = _surpluses(new_give, new_recv)
            hm = _harmonic_mean(user_s, opp_s)
            card_keys.discard((frozenset(card.give_player_ids),
                               frozenset(card.receive_player_ids)))
            card.give_player_ids = new_give
            card.receive_player_ids = new_recv
            card.mismatch_score = round(hm, 1)
            card.fairness_score = ratio
            card.composite_score = round(
                _composite(hm, ratio, new_give + new_recv, new_recv,
                           new_give), 3)
            card.give_value = round(n_gv, 1)
            card.receive_value = round(n_rv, 1)
            # Round-2 review 2026-08-21: `fit_premium` is a 1-for-1-only
            # annotation (fit_premium_1for1 returns a price only when the
            # #108 raw-board gate fails, which it can only do on a 1x1).
            # A sweetened card is no longer that shape, so the stale price
            # must not ride along on the payload — the v2 divergence path
            # already nulls its `fit_paid` for the same reason.
            card.fit_premium = None
            card.gap_sweetener = {
                "player_id": s_pid, "side": side,
                "gap_before": round(gap_before, 1),
                "gap_after": round(abs(n_gv - n_rv), 1),
            }
            card_keys.add(new_key)

    return cards


def _try_sweeten(give_ids, recv_ids, *, user_roster, opp_roster, seed_value,
                 fairness_threshold, min_side, surpluses, gap_ok,
                 both_feasible, players, untouchable_ids=None,
                 not_interested_ids=None, avoid_positions=None,
                 filler_ok_fn=None, presentment_ok_fn=None):
    """3.4 — close a near-miss by adding ONE cheap player from the
    under-paying side's roster.

    The under-paying side is the one whose consensus package value is
    lower. Candidates are that roster's players outside the trade, tried
    cheapest-consensus-value first; the first one whose addition (a) lifts
    the consensus point ratio to >= fairness_threshold, (b) keeps BOTH
    surpluses >= the gate, (c) keeps both lineups feasible, and (d) clears
    the #141 junk-filler bar (filler_ok_fn — a sweetener is by definition
    an added piece, so it must be a meaningful asset, not roster junk),
    wins. Sweeteners are players only — picks/FAAB are not roster assets
    here.

    Returns (sweetener_pid, side, new_give, new_recv, user_surplus,
    opp_surplus, point_ratio) or None.
    """
    gv, rv = _consensus_packages(give_ids, recv_ids, seed_value)
    in_trade = set(give_ids) | set(recv_ids)
    if gv < rv:
        side, roster = "give", user_roster
    else:
        side, roster = "receive", opp_roster

    candidates = sorted((p for p in roster if p not in in_trade
                         and not (side == "give" and untouchable_ids
                                  and p in untouchable_ids)     # #2 never sweeten with an untouchable
                         and not (side == "receive" and not_interested_ids
                                  and p in not_interested_ids)   # #163 never sweeten INTO the user
                         and not (side == "receive"
                                  and not avoid_ok(p, players, avoid_positions))),  # #360
                        key=seed_value)
    for s_pid in candidates:
        if side == "give":
            new_give, new_recv = give_ids + [s_pid], recv_ids
        else:
            new_give, new_recv = give_ids, recv_ids + [s_pid]
        if filler_ok_fn is not None and not filler_ok_fn(new_give, new_recv):
            continue                                     # #141 junk sweetener
        # G6 — a sweetener changes both net_P and the gap, so the SWEETENED
        # combo must re-clear the presentment rules (R-6; prd U-R2-5).
        if presentment_ok_fn is not None \
                and not presentment_ok_fn(new_give, new_recv):
            continue
        n_gv, n_rv = _consensus_packages(new_give, new_recv, seed_value)
        if n_gv <= 0 or n_rv <= 0:
            continue
        ratio = min(n_gv, n_rv) / max(n_gv, n_rv)
        if ratio < fairness_threshold:
            continue
        if not gap_ok(new_give, new_recv):
            continue
        if not both_feasible(new_give, new_recv):
            continue
        user_s, opp_s = surpluses(new_give, new_recv)
        if user_s < min_side or opp_s < min_side:
            continue
        return s_pid, side, new_give, new_recv, user_s, opp_s, round(ratio, 3)
    return None


def close_value_gap(give_ids, recv_ids, *, seed_value, gap_threshold,
                    fairness_threshold, user_roster, opp_roster, players,
                    scoring_format="1qb_ppr", untouchable_ids=None,
                    not_interested_ids=None, extra_ok_fn=None,
                    give_candidates=None, recv_candidates=None):
    """2026-08-21 gap auto-sweetener (`sweetener_gap_threshold`) — close an
    ABSOLUTE consensus gap on a card that already passed its path's gates.

    The ratio gate is scale-blind: fairness 0.85 on a five-figure package
    still leaves more than a late 1st of consensus value on the table
    (CHANGELOG 2026-08-21 — 15% of served cards carried gap > a late 1st).
    This pass generalizes `_try_sweeten` (the 3.4 fairness-band rescue)
    from "lift the ratio into the band" to "bring |gv − rv| under
    ``gap_threshold``": the RICHER side — the one receiving more consensus
    value — adds the smallest asset from its roster that

      (a) brings the recomputed gap ≤ ``gap_threshold``,
      (b) keeps the consensus point ratio ≥ ``fairness_threshold``,
      (c) keeps BOTH post-trade lineups feasible (3.2 rule), and
      (d) clears ``extra_ok_fn`` — the calling path's own gate stack
          (junk-filler, presentment, pick-swap, surplus gates, …), so a
          sweetened combo re-earns every gate the organic combo passed.

    Candidates are tried cheapest-consensus-value first, so the first hit
    is the smallest sufficient equalizer. They are drawn from the richer
    side's ROSTER by default, never untouchables (give side) and never
    not-interested players (receive side).

    ``give_candidates`` / ``recv_candidates`` (2026-08-21 round-2 review)
    narrow that universe when the CALLING path restricted its own pools
    rather than gating per-combo: the consensus generator prunes
    `give_pool` to the #174 pinned give players and `recv_pool` to the
    FB-47 pinned acquire targets / needed positions, so an equalizer
    drawn from the raw roster would put an asset in the card that the
    path itself would never have enumerated. Paths whose pinned/position
    rules are per-combo and monotone under addition (v2 divergence, v3)
    pass nothing and keep the full-roster universe, matching
    `_try_sweeten`. ``user_roster``/``opp_roster`` are still the FULL
    rosters — the 3.2 lineup-feasibility counts are computed from them.

    Picks: when `trade.picks_in_pool` is on, owned picks are injected as
    PICK pseudo-assets INTO the rosters, so a pick can be the equalizer.
    `pick_swap_ok` re-runs inside every caller's `extra_ok_fn` (#227/C3),
    which is the guard that keeps a pick-for-pick churn shape out.

    Returns (sweetener_pid, side, new_give, new_recv, gv, rv, point_ratio)
    or None. ``side`` is the side the asset was ADDED to: "give" when the
    USER was the richer party (they pay the equalizer), "receive" when the
    opponent was.
    """
    gv, rv = _consensus_packages(give_ids, recv_ids, seed_value)
    if abs(gv - rv) <= gap_threshold:
        return None
    in_trade = set(give_ids) | set(recv_ids)
    if rv > gv:            # user receives more — user adds to the give side
        side = "give"
        roster = user_roster if give_candidates is None else give_candidates
    else:                  # opponent receives more — they add (user receives)
        side = "receive"
        roster = opp_roster if recv_candidates is None else recv_candidates

    user_counts = _pos_counts(user_roster, players)
    opp_counts = _pos_counts(opp_roster, players)

    candidates = sorted((p for p in roster if p not in in_trade
                         and not (side == "give" and untouchable_ids
                                  and p in untouchable_ids)
                         and not (side == "receive" and not_interested_ids
                                  and p in not_interested_ids)),
                        key=seed_value)
    for s_pid in candidates:
        if side == "give":
            new_give, new_recv = list(give_ids) + [s_pid], list(recv_ids)
        else:
            new_give, new_recv = list(give_ids), list(recv_ids) + [s_pid]
        n_gv, n_rv = _consensus_packages(new_give, new_recv, seed_value)
        if n_gv <= 0 or n_rv <= 0:
            continue
        if abs(n_gv - n_rv) > gap_threshold:      # too small to close it
            continue
        ratio = min(n_gv, n_rv) / max(n_gv, n_rv)
        if ratio < fairness_threshold:            # fell out of the band
            continue
        g_delta = _subset_pos_delta(new_give, players)
        r_delta = _subset_pos_delta(new_recv, players)
        if not (_feasible_after(user_counts, g_delta, r_delta, scoring_format)
                and _feasible_after(opp_counts, r_delta, g_delta,
                                    scoring_format)):
            continue
        if extra_ok_fn is not None and not extra_ok_fn(new_give, new_recv):
            continue
        return s_pid, side, new_give, new_recv, n_gv, n_rv, round(ratio, 3)
    return None


# ---------------------------------------------------------------------------
# 3.3 — 3-team cycle trades (kidney-exchange-style clearing)
# ---------------------------------------------------------------------------


def find_three_team_cycles(
    *,
    league,
    member_values: dict[str, dict[str, float]],
    seed_elo: dict[str, float],
    scoring_format: str = "1qb_ppr",
    players: dict,
) -> list[dict]:
    """Find Pareto-improving 3-team single-asset cycles.

    Kidney-exchange-style clearing after Abraham, Blum & Sandholm,
    "Clearing Algorithms for Barter Exchange Markets" (EC '07): model
    beneficial directed handoffs as edges, then clear short cycles. We cap
    cycle length at 3 — mirroring kidney exchange's simultaneity
    constraint and the practical reality that >3-team fantasy trades
    essentially never execute. 2-cycles are excluded: those are ordinary
    two-team trades and belong to the pairwise generator.

    member_values: {user_id: {pid: value}} in each member's OWN value
    space, for members with real rankings (has_rankings). Members absent
    from the dict are skipped. Missing pids fall back to the consensus
    seed value (elo_to_value of seed_elo).

    Mechanism:
      * Directed edge A->B = the single asset p on A's roster maximizing
        (B's marginal value of p − A's marginal value of p), kept when the
        gain >= cfg "cycle_edge_min_gain". Marginals via
        replacement_levels/marginal_value in each member's own value map
        (raw values when FLAGS.trade_marginal_value is off).
      * Every directed 3-cycle over those edges is scored: each team's net
        = value received − value given (own values, marginal when the flag
        is on). A cycle survives when min net >= cfg "cycle_min_net" AND
        all three post-transfer lineups stay feasible (3.2 rule).
      * Score = min net; top cfg "cycle_max_results" returned. League
        scale (<= 12 nodes) makes exhaustive cycle enumeration trivial —
        no ILP needed for vertex-disjoint selection at this size.

    Returns [{"teams": [ids], "transfers": [{"from","to","player_id"}],
    "nets": {uid: net}, "min_net": float}, ...] sorted by min_net desc.
    """
    EDGE_MIN = float(_ts._cfg.get("cycle_edge_min_gain", 100.0))
    NET_MIN = float(_ts._cfg.get("cycle_min_net", 200.0))
    MAX_OUT = int(_ts._cfg.get("cycle_max_results", 3))
    MARGINAL = FLAGS.trade_marginal_value

    members = [m for m in league.members
               if m.user_id in member_values and m.roster]
    if len(members) < 3:
        return []

    # Per-member valuation in their OWN space, seed fallback for unknowns.
    def _value_fn(uid: str):
        vals = member_values[uid]

        def _v(pid: str) -> float:
            v = vals.get(pid)
            if v is None:
                v = elo_to_value(seed_elo.get(pid, 1500.0))
            return v
        return _v

    value_of = {m.user_id: _value_fn(m.user_id) for m in members}

    if MARGINAL:
        repl = {m.user_id: replacement_levels(m.roster, value_of[m.user_id],
                                              players, scoring_format)
                for m in members}

        def _marg(uid: str, pid: str) -> float:
            """Marginal value of pid on uid's roster, in uid's own space."""
            return marginal_value(pid, value_of[uid], repl[uid], players,
                                  scoring_format)
    else:
        def _marg(uid: str, pid: str) -> float:
            return value_of[uid](pid)

    # Directed edges: best single-asset transfer per ordered pair.
    edges: dict[tuple[str, str], tuple[str, float, float]] = {}
    # (from_uid, to_uid) -> (player_id, giver_loss, receiver_gain)
    for a in members:
        for b in members:
            if a.user_id == b.user_id:
                continue
            best = None
            for pid in a.roster:
                loss = _marg(a.user_id, pid)
                gain = _marg(b.user_id, pid)
                delta = gain - loss
                if best is None or delta > best[3]:
                    best = (pid, loss, gain, delta)
            if best is not None and best[3] >= EDGE_MIN:
                edges[(a.user_id, b.user_id)] = best[:3]

    # All directed 3-cycles (each unordered triple yields two orientations).
    counts = {m.user_id: _pos_counts(m.roster, players) for m in members}
    pos_of = {}

    def _pos(pid: str):
        if pid not in pos_of:
            p = players.get(pid)
            pos_of[pid] = getattr(p, "position", None) if p else None
        return pos_of[pid]

    def _post_feasible(uid: str, pid_out: str, pid_in: str) -> bool:
        out_d, in_d = {}, {}
        if _pos(pid_out) in _STARTER_NEED:
            out_d[_pos(pid_out)] = 1
        if _pos(pid_in) in _STARTER_NEED:
            in_d[_pos(pid_in)] = 1
        return _feasible_after(counts[uid], out_d, in_d, scoring_format)

    results: list[dict] = []
    ids = [m.user_id for m in members]
    for trio in combinations(ids, 3):
        for cycle in (trio, (trio[0], trio[2], trio[1])):   # both orientations
            legs = [(cycle[0], cycle[1]), (cycle[1], cycle[2]),
                    (cycle[2], cycle[0])]
            if not all(leg in edges for leg in legs):
                continue
            transfers = [{"from": frm, "to": to,
                          "player_id": edges[(frm, to)][0]}
                         for frm, to in legs]
            gives = {t["from"]: t["player_id"] for t in transfers}
            gets = {t["to"]: t["player_id"] for t in transfers}
            nets = {uid: round(_marg(uid, gets[uid]) - _marg(uid, gives[uid]), 1)
                    for uid in cycle}
            min_net = min(nets.values())
            if min_net < NET_MIN:
                continue
            if not all(_post_feasible(uid, gives[uid], gets[uid])
                       for uid in cycle):
                continue
            results.append({
                "teams": list(cycle),
                "transfers": transfers,
                "nets": nets,
                "min_net": float(min_net),
            })

    results.sort(key=lambda r: r["min_net"], reverse=True)
    return results[:MAX_OUT]
