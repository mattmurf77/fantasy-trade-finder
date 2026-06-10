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
the pool prune itself.

The objective is intentionally IDENTICAL to the v2 scorer
(trade_service._generate_for_pair_v2): same value space, same marginal
valuation, same surplus gates, fairness gate and composite blend. v3
changes how candidates are constructed and selected, not what "good"
means. Several small private helpers from trade_service are replicated
here (marked with TODO refactor comments) because they are closures /
methods that cannot be imported without touching trade_service.py.

Config keys (all read live via trade_service._cfg with inline defaults —
nothing added to trade_service._DEFAULT_CFG):

    v3_pool_size          12     per-side candidate pool size (3.1 prune)
    sweetener_band        0.15   how far below fairness_threshold a
                                 near-miss may sit and still be sweetened
    sweetener_max_cards   2      max sweetened cards emitted per pair
    cycle_edge_min_gain   100.0  min single-asset transfer gain for a
                                 directed edge in the cycle graph
    cycle_min_net         200.0  min per-team net surplus for a 3-cycle
    cycle_max_results     3      max cycles returned
"""

from __future__ import annotations

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
    elo_to_value,
    marginal_value,
    package_value_v2,
    replacement_levels,
)

__all__ = ["generate_pair_trades_v3", "find_three_team_cycles"]


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
    return package_value_v2(gvals, v_max), package_value_v2(rvals, v_max)


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
    gv = package_value_v2(gvals, v_max)
    rv = package_value_v2(rvals, v_max)
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
    pinned_give_players: list[str] | None = None,
    players: dict,
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

    MARGINAL = FLAGS.trade_marginal_value
    MIN_SIDE = (_c("min_side_surplus_marginal") if MARGINAL
                else _c("min_side_surplus"))
    GAIN_CAP = max(_c("mutual_gain_cap"), 1.0)
    WAIVER   = _c("waiver_slot_cost")
    MAX_GAP  = _c("trade_elo_gap_max")
    W_MIS    = _c("mismatch_weight")
    W_FAIR   = _c("fairness_weight")
    POOL_P   = int(_ts._cfg.get("v3_pool_size", 12))
    SW_BAND  = float(_ts._cfg.get("sweetener_band", 0.15))
    SW_MAX   = int(_ts._cfg.get("sweetener_max_cards", 2))

    # --- per-player value accessors (cached), same spaces as v2 ----------
    _def_uval = elo_to_value(1500.0)

    def _uv(pid: str) -> float:
        return user_value.get(pid, _def_uval)

    _vo_cache: dict[str, float] = {}

    def _vo(pid: str) -> float:
        v = _vo_cache.get(pid)
        if v is None:
            v = elo_to_value(opp_elo.get(pid, 1500.0))
            _vo_cache[pid] = v
        return v

    _sv_cache: dict[str, float] = {}

    def _sv(pid: str) -> float:
        v = _sv_cache.get(pid)
        if v is None:
            v = elo_to_value(seed_elo.get(pid, 1500.0))
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
                v = marginal_value(pid, _uv, user_repl, players)
                _mu_cache[pid] = v
            return v

        _mo_cache: dict[str, float] = {}

        def _opp_val(pid: str) -> float:
            v = _mo_cache.get(pid)
            if v is None:
                v = marginal_value(pid, _vo, opp_repl, players)
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
                  if p in shrunk_user_elo and p in opp_elo]
    known_opp = [p for p in opponent.roster
                 if p in shrunk_user_elo and p in opp_elo]
    give_pool = sorted(known_user, key=lambda p: _vo(p) - _uv(p),
                       reverse=True)[:POOL_P]
    if pinned_set:
        for pid in user_roster:
            if pid in pinned_set and pid not in give_pool:
                give_pool.append(pid)
    recv_pool = sorted(known_opp, key=lambda p: _uv(p) - _vo(p),
                       reverse=True)[:POOL_P]
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
        give_val_user = package_value_v2(uvals_give, u_max)
        recv_val_user = package_value_v2(uvals_recv, u_max)

        ovals_give = [_opp_val(p) for p in give_ids]
        ovals_recv = [_opp_val(p) for p in recv_ids]
        o_max = max(ovals_give + ovals_recv)
        give_val_opp = package_value_v2(ovals_give, o_max)   # opp receives
        recv_val_opp = package_value_v2(ovals_recv, o_max)   # opp gives

        # Waiver-slot cost (A3) on the side receiving MORE players.
        extra = len(recv_ids) - len(give_ids)
        if extra > 0:
            recv_val_user -= WAIVER * extra
        elif extra < 0:
            give_val_opp -= WAIVER * (-extra)

        return recv_val_user - give_val_user, give_val_opp - recv_val_opp

    def _composite(hm: float, fairness: float, all_ids) -> float:
        comp = W_MIS * min(hm, GAIN_CAP) / GAIN_CAP + W_FAIR * fairness
        return comp * _tier_mult(shrunk_user_elo, all_ids)

    # --- exact enumeration -------------------------------------------------
    give_subsets = [list(c) for size in (1, 2, 3)
                    for c in combinations(give_pool, size)]
    recv_subsets = [list(c) for size in (1, 2, 3)
                    for c in combinations(recv_pool, size)]

    scored: list[tuple] = []        # (composite, order, hm, fairness, g, r)
    near_misses: list[tuple] = []   # (hm, ratio, give, recv) — 3.4 input
    order = 0

    for give_ids in give_subsets:
        if pinned_set and not (set(give_ids) & pinned_set):
            continue
        for recv_ids in recv_subsets:
            if abs(len(give_ids) - len(recv_ids)) > 1:
                continue
            if not _positions_ok(give_ids, recv_ids):
                continue
            if not _gap_ok(give_ids, recv_ids):
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
            scored.append((_composite(hm, fairness, give_ids + recv_ids),
                           order, hm, fairness, give_ids, recv_ids))

    scored.sort(key=lambda e: (e[0], e[1]), reverse=True)

    def _card(composite, hm, fairness, give_ids, recv_ids) -> TradeCard:
        return TradeCard(
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
        )

    cards = [_card(comp, hm, fair, g, r)
             for comp, _o, hm, fair, g, r in scored[:max_cards]]

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
            )
            if sweet is None:
                continue
            s_pid, side, new_give, new_recv, user_s, opp_s, ratio = sweet
            key = (frozenset(new_give), frozenset(new_recv))
            if key in organic_keys:
                continue
            hm = _harmonic_mean(user_s, opp_s)
            comp = _composite(hm, ratio, new_give + new_recv)
            card = _card(comp, hm, ratio, new_give, new_recv)
            card.sweetener = {"player_id": s_pid, "side": side}
            cards.append(card)
            organic_keys.add(key)
            budget -= 1

    return cards


def _try_sweeten(give_ids, recv_ids, *, user_roster, opp_roster, seed_value,
                 fairness_threshold, min_side, surpluses, gap_ok,
                 both_feasible, players):
    """3.4 — close a near-miss by adding ONE cheap player from the
    under-paying side's roster.

    The under-paying side is the one whose consensus package value is
    lower. Candidates are that roster's players outside the trade, tried
    cheapest-consensus-value first; the first one whose addition (a) lifts
    the consensus point ratio to >= fairness_threshold, (b) keeps BOTH
    surpluses >= the gate, and (c) keeps both lineups feasible, wins.
    Sweeteners are players only — picks/FAAB are not roster assets here.

    Returns (sweetener_pid, side, new_give, new_recv, user_surplus,
    opp_surplus, point_ratio) or None.
    """
    gv, rv = _consensus_packages(give_ids, recv_ids, seed_value)
    in_trade = set(give_ids) | set(recv_ids)
    if gv < rv:
        side, roster = "give", user_roster
    else:
        side, roster = "receive", opp_roster

    candidates = sorted((p for p in roster if p not in in_trade),
                        key=seed_value)
    for s_pid in candidates:
        if side == "give":
            new_give, new_recv = give_ids + [s_pid], recv_ids
        else:
            new_give, new_recv = give_ids, recv_ids + [s_pid]
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
            return marginal_value(pid, value_of[uid], repl[uid], players)
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
