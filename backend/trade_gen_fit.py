"""Fit challenger — thin knockouts, dual 0–100 team scores.

Bake-off arm ``fit`` (docs/plans/fit-challenger/PRD.md). Called DIRECTLY by
``bakeoff_runner.gen_fit_cards``. Never imported from
``TradeService._generate_trades_impl`` — organic serving stays live Arm B.

Knockouts (construction): K1 shape, K2 live pick-swap C3, K3 both lineups
startable, K4–K7 live G6 R1/R2/R3/R5. Surplus, rv≥gv, #108, filler, Elo
gap, and divergence prune are NOT kills.

Scoring: each team 0–100 from board / vs-consensus / consensus; rank by sum.
Preferences (untouchables, not-interested, pins, intent) filter AFTER scoring.
"""

from __future__ import annotations

import logging
import math
import statistics
import time
import uuid
from dataclasses import dataclass, field
from itertools import combinations

from .feature_flags import FLAGS
from .trade_optimizer import (
    _feasible_after,
    _pos_counts,
    _subset_pos_delta,
)
from .trade_service import (
    League,
    TradeCard,
    _c,
    _filter_by_trade_intent,
    analyze_roster_strengths,
    cap_give_headliners,
    deck_centerpiece,
    elo_to_value,
    is_pick_asset,
    need_gate_ok,
    overpay_ok,
    package_value_v2,
    pick_gap_ok,
    pick_swap_ok,
    pos_net_ok,
)

logger = logging.getLogger(__name__)

# K1 — legal (give_n, recv_n). Wider than live v3 (|n-m|≤1).
LEGAL_SHAPES: frozenset[tuple[int, int]] = frozenset({
    (1, 1), (2, 1), (1, 2), (3, 1), (1, 3), (3, 2), (2, 3),
})

_BUCKETS = (
    ("both_high", lambda y, t: y >= 70 and t >= 70),
    ("mixed",     lambda y, t: (y >= 70 and 40 <= t < 70)
                              or (t >= 70 and 40 <= y < 70)),
    ("you_tilt",  lambda y, t: y >= 70 and t < 40),
    ("them_tilt", lambda y, t: t >= 70 and y < 40),
    ("both_ok",   lambda y, t: 40 <= y < 70 and 40 <= t < 70),
)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def _k(key: str, default: float) -> float:
    try:
        v = _c(key)
        return float(v) if v is not None else default
    except Exception:
        return default


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------

@dataclass
class FitReport:
    enumerated: int = 0
    scored: int = 0
    killed: dict[str, int] = field(default_factory=lambda: {
        "K1": 0, "K2": 0, "K3": 0, "K4": 0, "K5": 0, "K6": 0, "K7": 0,
    })
    filtered: dict[str, int] = field(default_factory=dict)
    one_sided: int = 0
    both_high: int = 0
    mixed: int = 0
    pairs: int = 0
    aggregates: list[float] = field(default_factory=list)
    generation_ms: int = 0

    def note_kill(self, code: str) -> None:
        self.killed[code] = self.killed.get(code, 0) + 1

    def kill_counts(self) -> dict:
        scored = self.scored
        median = (round(float(statistics.median(self.aggregates)), 1)
                  if self.aggregates else 0.0)
        return {
            "enumerated": self.enumerated,
            "scored": self.scored,
            "killed": dict(self.killed),
            "filtered": dict(self.filtered),
            "one_sided": self.one_sided,
            "both_high": self.both_high,
            "mixed": self.mixed,
            "pairs": self.pairs,
            "one_sided_pct": (round(100.0 * self.one_sided / scored, 1)
                              if scored else 0.0),
            "both_high_pct": (round(100.0 * self.both_high / scored, 1)
                              if scored else 0.0),
            "mixed_pct": (round(100.0 * self.mixed / scored, 1)
                          if scored else 0.0),
            "median_aggregate": median,
            "generation_ms": self.generation_ms,
        }


# ---------------------------------------------------------------------------
# K1–K7
# ---------------------------------------------------------------------------

def shape_ok(give_ids: list[str], recv_ids: list[str]) -> bool:
    """K1 — 1–3 assets per side; legal shapes only."""
    return (len(give_ids), len(recv_ids)) in LEGAL_SHAPES


def both_startable(give_ids, recv_ids, user_roster, opp_roster,
                   players, scoring_format) -> bool:
    """K3 — live ``_feasible_after`` on BOTH rosters, every path."""
    user_counts = _pos_counts(user_roster, players)
    opp_counts = _pos_counts(opp_roster, players)
    g_delta = _subset_pos_delta(give_ids, players)
    r_delta = _subset_pos_delta(recv_ids, players)
    return (
        _feasible_after(user_counts, g_delta, r_delta, scoring_format)
        and _feasible_after(opp_counts, r_delta, g_delta, scoring_format)
    )


def knockout_code(
    give_ids, recv_ids, *,
    players, seed_value, user_roster, opp_roster, scoring_format,
    presentment_r5, user_pos_values, outlook, position_needs,
    position_surplus,
) -> str | None:
    """Return the first kill code (K1–K7) or None if the package survives."""
    if not shape_ok(give_ids, recv_ids):
        return "K1"
    if not pick_swap_ok(give_ids, recv_ids, players, seed_value):
        return "K2"
    if not both_startable(give_ids, recv_ids, user_roster, opp_roster,
                          players, scoring_format):
        return "K3"
    if not overpay_ok(give_ids, recv_ids, seed_value):
        return "K4"
    if not pos_net_ok(give_ids, recv_ids, players):
        return "K5"
    if not pick_gap_ok(give_ids, recv_ids, seed_value, players):
        return "K6"
    if presentment_r5 and not need_gate_ok(
            give_ids, recv_ids,
            seed_value=seed_value, players=players,
            user_pos_values=user_pos_values, outlook=outlook,
            position_needs=position_needs,
            position_surplus=position_surplus,
            scoring_format=scoring_format):
        return "K7"
    return None


# ---------------------------------------------------------------------------
# Surplus + 0–100 score
# ---------------------------------------------------------------------------

def surplus(out_ids: list[str], in_ids: list[str], value_of,
            waiver: float) -> float:
    """T sends ``out_ids``, receives ``in_ids``, on ``value_of``'s board.

    Waiver hits T only when T receives more bodies (same as live user-side
    waiver). ``package_value_v2`` is the live package math.
    """
    ovals = [float(value_of(p) or 0.0) for p in out_ids]
    ivals = [float(value_of(p) or 0.0) for p in in_ids]
    both = ovals + ivals
    if not both:
        return 0.0
    v_max = max(both)
    out_pkg = package_value_v2(ovals, v_max, n_other=len(in_ids),
                               other_values=ivals)
    in_pkg = package_value_v2(ivals, v_max, n_other=len(out_ids),
                              other_values=ovals)
    extra = len(in_ids) - len(out_ids)
    if extra > 0:
        in_pkg -= waiver * extra
    return in_pkg - out_pkg


def score_surplus(s: float) -> float:
    """Signed surplus → 0–100. Even (0) → fit_score_even (50). Continuous."""
    scale = max(_k("fit_score_scale", 400.0), 1e-6)
    even = _k("fit_score_even", 50.0)
    raw = even + 50.0 * math.tanh(s / scale)
    return round(min(100.0, max(0.0, raw)), 1)


def _blend(parts: list[tuple[float, float]]) -> float:
    """Weighted mean of (weight, value); renormalize if some lenses omitted."""
    wsum = sum(w for w, _ in parts if w > 0)
    if wsum <= 0:
        return 50.0
    return sum(w * v for w, v in parts if w > 0) / wsum


def team_lenses(out_ids, in_ids, board_of, cons_of, waiver: float,
                boarded: bool) -> dict:
    """L1 board / L2 vs-consensus / L3 consensus. Null lenses omitted."""
    s_cons = surplus(out_ids, in_ids, cons_of, waiver)
    l3 = score_surplus(s_cons)
    out = {"board": None, "vs_consensus": None, "consensus": l3}
    if not boarded or board_of is None:
        return out
    s_board = surplus(out_ids, in_ids, board_of, waiver)
    out["board"] = score_surplus(s_board)
    out["vs_consensus"] = score_surplus(s_board - s_cons)
    return out


def team_score(lenses: dict) -> float:
    w_board = _k("fit_w_board", 0.40)
    w_div = _k("fit_w_div", 0.30)
    w_cons = _k("fit_w_cons", 0.30)
    parts: list[tuple[float, float]] = []
    if lenses.get("board") is not None:
        parts.append((w_board, lenses["board"]))
    if lenses.get("vs_consensus") is not None:
        parts.append((w_div, lenses["vs_consensus"]))
    if lenses.get("consensus") is not None:
        parts.append((w_cons, lenses["consensus"]))
    return round(_blend(parts), 1)


def bucket_for(you: float, them: float) -> str:
    for name, pred in _BUCKETS:
        if pred(you, them):
            return name
    return "weak"


# ---------------------------------------------------------------------------
# Pool + enumeration
# ---------------------------------------------------------------------------

def _val(pid: str, elo_map: dict[str, float] | None, seed: dict[str, float]) -> float:
    if elo_map and pid in elo_map:
        return elo_to_value(elo_map[pid])
    return elo_to_value(seed.get(pid, 1500.0))


def _pct_rank(vals: list[float], v: float) -> float:
    if not vals:
        return 0.0
    return sum(1 for x in vals if x <= v) / len(vals)


def build_pool(
    roster: list[str],
    seed: dict[str, float],
    board: dict[str, float] | None,
    other_board: dict[str, float] | None,
    players: dict | None = None,
) -> list[str]:
    """Union of top consensus / |board−seed| / |board−other| plus owned picks.

    Cap unique ids. No direction prune: bargains and you-pay assets can enter.
    Owned picks always try to enter (PRD §5); if the union exceeds the cap,
    keep picks first then highest ``max(consensus pct, |div| pct)``.
    """
    cap = max(int(_k("fit_pool_cap", 15.0)), 1)
    k_cons = max(int(_k("fit_pool_consensus", 8.0)), 0)
    k_div = max(int(_k("fit_pool_div_seed", 8.0)), 0)
    k_opp = max(int(_k("fit_pool_div_opp", 8.0)), 0)
    ids = [p for p in roster if p]
    if not ids:
        return []

    def cons(p):
        return elo_to_value(seed.get(p, 1500.0))

    ranked: list[str] = []

    def take(seq, n):
        for p in seq[:n]:
            if p not in ranked:
                ranked.append(p)

    take(sorted(ids, key=lambda p: (-cons(p), p)), k_cons)
    if board:
        take(sorted(ids, key=lambda p: (-abs(_val(p, board, seed) - cons(p)), p)),
             k_div)
    if board and other_board:
        take(sorted(ids, key=lambda p: (
            -abs(_val(p, board, seed) - _val(p, other_board, seed)), p)), k_opp)

    picks = [p for p in ids
             if players is not None and is_pick_asset(players.get(p))]
    for p in picks:
        if p not in ranked:
            ranked.append(p)

    if len(ranked) > cap:
        cons_vals = [cons(p) for p in ranked]
        div_vals = [
            abs(_val(p, board, seed) - cons(p)) if board else 0.0
            for p in ranked
        ]
        pick_set = set(picks)

        def rank_key(p):
            pct = max(
                _pct_rank(cons_vals, cons(p)),
                _pct_rank(div_vals, abs(_val(p, board, seed) - cons(p)) if board else 0.0),
            )
            return (0 if p in pick_set else 1, -pct, p)

        ranked.sort(key=rank_key)
        return ranked[:cap]

    take(sorted(ids, key=lambda p: (-cons(p), p)), cap)
    return ranked[:cap]


def _subsets(pool: list[str], sizes: tuple[int, ...]) -> list[list[str]]:
    out: list[list[str]] = []
    n = len(pool)
    for k in sizes:
        if k > n:
            continue
        out.extend(list(c) for c in combinations(pool, k))
    return out


def enumerate_pair(
    *,
    give_pool: list[str],
    recv_pool: list[str],
    knockout_kw: dict,
    score_fn,
    report: FitReport,
) -> list[tuple]:
    """1-for-1 cartesian first, then expand around top-N into 2-/3-asset shapes.

    Returns list of (aggregate, you, them, give, recv, fit_obj) sorted desc.
    Honours ``fit_max_packages_per_pair``. Illegal K1 shapes (2-for-2, 3-for-3)
    are skipped without spending the pair budget.
    """
    budget = max(int(_k("fit_max_packages_per_pair", 20000.0)), 1)
    expand_from = max(int(_k("fit_expand_from", 25.0)), 1)
    survivors: list[tuple] = []
    seen: set[tuple] = set()

    def consider(give_ids: list[str], recv_ids: list[str]) -> None:
        if report.enumerated >= budget:
            return
        if not shape_ok(give_ids, recv_ids):
            # 2-for-2 / 3-for-3 fall out of K1; do not spend the pair budget
            # on shapes we will never score.
            return
        key = (frozenset(give_ids), frozenset(recv_ids))
        if key in seen:
            return
        seen.add(key)
        report.enumerated += 1
        code = knockout_code(give_ids, recv_ids, **knockout_kw)
        if code:
            report.note_kill(code)
            return
        you, them, fit_obj = score_fn(give_ids, recv_ids)
        report.scored += 1
        report.aggregates.append(you + them)
        if them < 40:
            report.one_sided += 1
        b = fit_obj["bucket"]
        if b == "both_high":
            report.both_high += 1
        elif b == "mixed":
            report.mixed += 1
        survivors.append((you + them, you, them, list(give_ids), list(recv_ids),
                          fit_obj))

    # Stage 1 — every 1-for-1 in the pools.
    for g in give_pool:
        if report.enumerated >= budget:
            break
        for r in recv_pool:
            if report.enumerated >= budget:
                break
            consider([g], [r])

    survivors.sort(key=lambda t: (-t[0], t[3], t[4]))
    seeds = survivors[:expand_from]

    # Stage 2 — 2- and 3-asset around the best 1-for-1s.
    give_set = set(give_pool)
    recv_set = set(recv_pool)
    extras_g = _subsets(give_pool, (1, 2))
    extras_r = _subsets(recv_pool, (1, 2))
    for _agg, _y, _t, g0, r0, _f in seeds:
        if report.enumerated >= budget:
            break
        g0s, r0s = set(g0), set(r0)
        for extra in extras_g:
            if report.enumerated >= budget:
                break
            if g0s & set(extra):
                continue
            give = g0 + extra
            if not all(p in give_set for p in give):
                continue
            consider(give, r0)
            for extra_r in extras_r:
                if report.enumerated >= budget:
                    break
                if r0s & set(extra_r):
                    continue
                recv = r0 + extra_r
                if not all(p in recv_set for p in recv):
                    continue
                consider(give, recv)
        for extra_r in extras_r:
            if report.enumerated >= budget:
                break
            if r0s & set(extra_r):
                continue
            recv = r0 + extra_r
            if not all(p in recv_set for p in recv):
                continue
            consider(g0, recv)

    survivors.sort(key=lambda t: (-t[0], t[3], t[4]))
    return survivors


# ---------------------------------------------------------------------------
# Post-score filters (do not shrink search)
# ---------------------------------------------------------------------------

def apply_filters(
    cards: list[TradeCard],
    *,
    untouchable_ids: set,
    not_interested_ids: set,
    pinned_give: set,
    pinned_receive: set,
    pinned_give_mode: str,
    acquire_positions: list[str],
    trade_away_positions: list[str],
    players: dict,
    past_keys: set,
    seed_elo: dict,
    trade_intent: str | None,
    scoring_format: str,
    report: FitReport,
) -> list[TradeCard]:
    def drop(reason: str, n: int = 1) -> None:
        report.filtered[reason] = report.filtered.get(reason, 0) + n

    kept: list[TradeCard] = []
    for c in cards:
        give, recv = c.give_player_ids, c.receive_player_ids
        if untouchable_ids and set(give) & untouchable_ids:
            drop("untouchable")
            continue
        if not_interested_ids and set(recv) & not_interested_ids:
            drop("not_interested")
            continue
        if pinned_give:
            gs = set(give)
            if pinned_give_mode == "all":
                if not pinned_give <= gs:
                    drop("pinned_give")
                    continue
            elif not (gs & pinned_give):
                    drop("pinned_give")
                    continue
        if pinned_receive and not (set(recv) & pinned_receive):
            drop("pinned_receive")
            continue
        if acquire_positions:
            recv_pos = {getattr(players.get(p), "position", None) for p in recv}
            if not any(p in acquire_positions for p in recv_pos):
                drop("acquire_positions")
                continue
        if trade_away_positions:
            give_pos = {getattr(players.get(p), "position", None) for p in give}
            if not any(p in trade_away_positions for p in give_pos):
                drop("trade_away_positions")
                continue
        key = (frozenset(give), frozenset(recv))
        if key in past_keys:
            drop("already_swiped_or_r4")
            continue
        kept.append(c)

    before = len(kept)
    kept = _filter_by_trade_intent(
        kept, trade_intent, seed_elo, players, scoring_format)
    if len(kept) < before:
        drop("intent", before - len(kept))

    # C4 + C4b — same caps as live deck assembly.
    cap = int(_k("deck_headliner_cap", 2.0))
    if cap > 0 and seed_elo:
        seen: dict[str, int] = {}
        capped: list[TradeCard] = []
        n_drop = 0
        for c in kept:
            head = deck_centerpiece(c.give_player_ids, c.receive_player_ids,
                                    seed_elo)
            if head is not None:
                if seen.get(head, 0) >= cap:
                    n_drop += 1
                    continue
                seen[head] = seen.get(head, 0) + 1
            capped.append(c)
        if n_drop:
            drop("c4", n_drop)
        kept = capped
    before = len(kept)
    kept = cap_give_headliners(kept, seed_elo, players,
                               int(_k("deck_give_headliner_cap", 3.0)))
    if len(kept) < before:
        drop("c4b", before - len(kept))
    return kept


# ---------------------------------------------------------------------------
# Public entry
# ---------------------------------------------------------------------------

def generate_league_suggestions(
    *,
    players: dict,
    league: League,
    user_id: str,
    user_elo: dict[str, float],
    user_roster: list[str],
    seed_elo: dict[str, float],
    confidence: dict[str, int] | None = None,  # accepted, unused (no shrink)
    placements: dict[str, tuple[float, float]] | None = None,
    max_per_opponent: int | None = None,
    scoring_format: str = "1qb_ppr",
    untouchable_ids: set | None = None,
    target_ids: set | None = None,          # ranking only in live; ignored here
    not_interested_ids: set | None = None,
    opponent_user_id: str | None = None,
    opponent_outlooks: dict[str, str] | None = None,
    opponent_pick_shares: dict[str, float] | None = None,
    past_decision_keys: set | None = None,
    on_opponent_done=None,
    outlook: str | None = None,
    acquire_positions: list[str] | None = None,
    trade_away_positions: list[str] | None = None,
    pinned_give_players: list[str] | None = None,
    pinned_receive_players: list[str] | None = None,
    pinned_give_mode: str = "any",
    trade_intent: str | None = None,
    bypass_need_gate: bool = False,
    exclusion_keys: set | None = None,
) -> tuple[list[TradeCard], FitReport]:
    """Generate fit-arm cards for one user against one league.

    Preferences are applied after scoring (PRD §6). ``max_per_opponent``
    truncates the ranked list per partner AFTER filters — presentation, not
    search.
    """
    t0 = time.monotonic()
    report = FitReport()
    if league is None:
        return [], report

    untouchable_ids = set(untouchable_ids or ())
    not_interested_ids = set(not_interested_ids or ())
    pinned_give = set(pinned_give_players or ())
    pinned_receive = set(pinned_receive_players or ())
    acquire_positions = list(acquire_positions or ())
    trade_away_positions = list(trade_away_positions or ())
    past_keys = set(past_decision_keys or ()) | set(exclusion_keys or ())
    seed_elo = seed_elo or {}
    user_elo = user_elo or {}
    waiver = float(_c("waiver_slot_cost") or 425.0)

    def cons_of(pid: str) -> float:
        return elo_to_value(seed_elo.get(pid, 1500.0))

    def user_board(pid: str) -> float:
        if pid in user_elo:
            return elo_to_value(user_elo[pid])
        return cons_of(pid)

    user_boarded = bool(user_elo)
    user_profile = analyze_roster_strengths(user_roster, players, scoring_format)
    user_pos_values: dict[str, list] = {}
    for pid in user_roster:
        p = players.get(pid)
        pos = getattr(p, "position", None) if p else None
        if pos in ("QB", "RB", "WR", "TE"):
            user_pos_values.setdefault(pos, []).append((pid, cons_of(pid)))

    presentment_r5 = (
        FLAGS.trade_presentment_rules
        and not bypass_need_gate
    )

    members = [m for m in league.members
               if m.user_id != user_id and m.roster]
    if opponent_user_id:
        members = [m for m in members if m.user_id == opponent_user_id]

    all_cards: list[TradeCard] = []

    for idx, opp in enumerate(members):
        report.pairs += 1
        opp_boarded = bool(getattr(opp, "has_rankings", False)
                           and opp.elo_ratings)
        opp_elo = opp.elo_ratings if opp_boarded else {}

        def opp_board(pid: str, _elo=opp_elo) -> float:
            if pid in _elo:
                return elo_to_value(_elo[pid])
            return cons_of(pid)

        give_pool = build_pool(
            user_roster, seed_elo,
            user_elo if user_boarded else None,
            opp_elo if opp_boarded else None,
            players=players,
        )
        recv_pool = build_pool(
            opp.roster, seed_elo,
            opp_elo if opp_boarded else None,
            user_elo if user_boarded else None,
            players=players,
        )

        knockout_kw = dict(
            players=players, seed_value=cons_of,
            user_roster=user_roster, opp_roster=opp.roster,
            scoring_format=scoring_format,
            presentment_r5=presentment_r5,
            user_pos_values=user_pos_values,
            outlook=outlook,
            position_needs=list(user_profile.get("position_needs") or []),
            position_surplus=list(user_profile.get("position_surplus") or []),
        )

        def score_fn(give_ids, recv_ids, _opp_board=opp_board,
                     _opp_boarded=opp_boarded):
            you_l = team_lenses(give_ids, recv_ids, user_board, cons_of,
                                waiver, user_boarded)
            them_l = team_lenses(recv_ids, give_ids, _opp_board, cons_of,
                                 waiver, _opp_boarded)
            you = team_score(you_l)
            them = team_score(them_l)
            gvals = [cons_of(p) for p in give_ids]
            rvals = [cons_of(p) for p in recv_ids]
            v_max = max(gvals + rvals) if (gvals + rvals) else 1.0
            gv = package_value_v2(gvals, v_max, n_other=len(recv_ids),
                                  other_values=rvals)
            rv = package_value_v2(rvals, v_max, n_other=len(give_ids),
                                  other_values=gvals)
            fair = (min(gv, rv) / max(gv, rv)) if max(gv, rv) > 0 else 1.0
            fit_obj = {
                "you": you,
                "them": them,
                "aggregate": round(you + them, 1),
                "bucket": bucket_for(you, them),
                "lenses": {"you": you_l, "them": them_l},
            }
            return you, them, fit_obj, gv, rv, fair

        def score_wrapper(give_ids, recv_ids):
            you, them, fit_obj, _gv, _rv, _fair = score_fn(give_ids, recv_ids)
            return you, them, fit_obj

        rows = enumerate_pair(
            give_pool=give_pool, recv_pool=recv_pool,
            knockout_kw=knockout_kw, score_fn=score_wrapper, report=report,
        )
        basis = "divergence" if (user_boarded and opp_boarded) else "consensus"
        pair_cards: list[TradeCard] = []
        for agg, you, them, give_ids, recv_ids, fit_obj in rows:
            _y, _t, _f, gv, rv, fair = score_fn(give_ids, recv_ids)
            card = TradeCard(
                trade_id=str(uuid.uuid4())[:8],
                league_id=league.league_id if hasattr(league, "league_id")
                else getattr(league, "id", "") or "",
                proposing_user_id=user_id,
                target_user_id=opp.user_id,
                target_username=getattr(opp, "username", "") or "",
                give_player_ids=give_ids,
                receive_player_ids=recv_ids,
                mismatch_score=round(you - 50.0, 3),
                fairness_score=round(fair, 3),
                composite_score=round(agg, 3),
                basis=basis,
                give_value=round(gv, 1) if gv is not None else None,
                receive_value=round(rv, 1) if rv is not None else None,
            )
            card.fit = fit_obj
            pair_cards.append(card)
        pair_cards.sort(key=lambda c: c.composite_score, reverse=True)
        all_cards.extend(pair_cards)
        if on_opponent_done is not None:
            try:
                on_opponent_done(idx + 1, len(members), list(all_cards))
            except Exception:
                pass

    all_cards.sort(key=lambda c: c.composite_score, reverse=True)
    all_cards = apply_filters(
        all_cards,
        untouchable_ids=untouchable_ids,
        not_interested_ids=not_interested_ids,
        pinned_give=pinned_give,
        pinned_receive=pinned_receive,
        pinned_give_mode=pinned_give_mode or "any",
        acquire_positions=acquire_positions,
        trade_away_positions=trade_away_positions,
        players=players,
        past_keys=past_keys,
        seed_elo=seed_elo,
        trade_intent=trade_intent if FLAGS.trades_intent_modes else None,
        scoring_format=scoring_format,
        report=report,
    )
    min_them = _k("fit_min_them", 0.0)
    min_agg = _k("fit_min_aggregate", 0.0)
    if min_them > 0 or min_agg > 0:
        before = len(all_cards)
        all_cards = [
            c for c in all_cards
            if (getattr(c, "fit", None) or {}).get("them", 0) >= min_them
            and c.composite_score >= min_agg
        ]
        if len(all_cards) < before:
            report.filtered["score_floor"] = before - len(all_cards)

    per_opp_cap = int(max_per_opponent) if max_per_opponent else 0
    if per_opp_cap > 0:
        counts: dict[str, int] = {}
        capped: list[TradeCard] = []
        n_drop = 0
        for c in all_cards:
            k = c.target_user_id
            if counts.get(k, 0) >= per_opp_cap:
                n_drop += 1
                continue
            counts[k] = counts.get(k, 0) + 1
            capped.append(c)
        if n_drop:
            report.filtered["max_per_opponent"] = n_drop
        all_cards = capped

    report.generation_ms = int((time.monotonic() - t0) * 1000)
    logger.info("trade_gen_fit %s", report.kill_counts())
    return all_cards, report
