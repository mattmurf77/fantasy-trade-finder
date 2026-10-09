"""Value-only core of the value-core trade engine (docs/plans/value-core-engine/lld.md section 4).

Enumerates 1-3 x 1-3 packages between the viewer and each partner and keeps the
fair ones: a premium-adjusted consensus-market ratio inside the band, plus the
hard rules, applied in REJECT_CODES order. It sees market values, rosters,
roster rules, untouchables and pins; a board only for throw-ins and a team window
only for the picks_for_players rule. No logging, no I/O, no flag or config reads.
"""
from __future__ import annotations

import math
import time
from bisect import bisect_left, bisect_right
from itertools import combinations
from typing import Mapping, Sequence

from ..power_rankings import LINEUP_SLOT_ELIGIBILITY, optimal_starter_slots
from .types import (
    CORE_POSITIONS,
    Board,
    CoreConfig,
    CoreDiagnostics,
    FairTrade,
    LeagueSnapshot,
    Request,
    Team,
    TradeVerdict,
)

__all__ = [
    "TIME_BUDGET_S", "MAX_CHECKS_PER_PARTNER", "MAX_PACKAGE_SIZE", "MAX_THROWIN_OPTIONS",
    "PREMIUM_EXPONENT", "RATIO_TOL", "REJECT_CODES", "THROWIN_MIN_COMPARISONS", "effective_band",
    "stud_premium", "throwin_ok", "evaluate_trade", "find_fair_trades",
]

TIME_BUDGET_S = 8.0
MAX_CHECKS_PER_PARTNER = 40_000
MAX_PACKAGE_SIZE = 3
MAX_THROWIN_OPTIONS = 3   # qualifying throw-ins tried per side, per candidate pair (best recipient surplus first)
THROWIN_MIN_COMPARISONS = 3   # recipient evidence a throw-in needs: one matchup is not an opinion
PREMIUM_EXPONENT = 2.0
RATIO_TOL = 1e-9
REJECT_CODES = ("floor", "band", "filler", "breakup", "picks_for_players", "untouchable", "reducible",
                "roster_size", "lineup")


def throwin_ok(asset_id: str, recipient_board: Board | None, *,
               market: float, cfg: CoreConfig) -> bool:
    """Throw-in rule (operator, 2026-10-01): a piece too small for the junk rules may ride
    along only if its RECIPIENT values it at >= cfg.throwin_min_ratio x consensus market and
    at least the asset floor. Evidence is required on both sides: the piece has a consensus
    value (market > 0; an unpriced player has no "double" to clear) and the recipient really
    ranked him (comparisons >= THROWIN_MIN_COMPARISONS; a default Elo or a single matchup is
    not an opinion). Otherwise False."""
    if (recipient_board is None or market <= 0 or asset_id not in recipient_board.values
            or recipient_board.comparisons.get(asset_id, 0) < THROWIN_MIN_COMPARISONS):
        return False
    value = recipient_board.values[asset_id]
    return value >= cfg.throwin_min_ratio * market and value >= cfg.asset_floor_abs


def effective_band(band: float, fairness_threshold: float | None) -> float:
    """The band actually applied. The client's fairness preference may only TIGHTEN it:
    min(band, max(0.02, 1 - fairness_threshold)); None -> band unchanged."""
    if fairness_threshold is None:
        return band
    return min(band, max(0.02, 1.0 - fairness_threshold))


def stud_premium(headliner_market: float, elite_value: float, max_premium: float) -> float:
    """max_premium * min(1, headliner_market / elite_value) ** PREMIUM_EXPONENT.
    elite_value <= 0 or headliner_market <= 0 -> 0.0."""
    if elite_value <= 0 or headliner_market <= 0:
        return 0.0
    return max_premium * min(1.0, headliner_market / elite_value) ** PREMIUM_EXPONENT


class _Ctx:
    """Per-call constants shared by find_fair_trades and evaluate_trade."""

    def __init__(self, snapshot: LeagueSnapshot, request: Request, cfg: CoreConfig):
        self.assets = snapshot.assets
        self.slots = list(snapshot.rules.lineup_slots)
        self.max_players = snapshot.rules.max_players
        self.elite = snapshot.elite_value
        self.pmax = cfg.stud_premium
        self.floor = cfg.asset_floor_abs
        self.frac = cfg.filler_min_frac
        self.breakup = cfg.breakup_min_ratio
        self.keep_picks = cfg.rebuilders_keep_picks
        # Asymmetric band (operator, 2026-10-01): the viewer may overpay by up to `band` but
        # never take more than `gain_band` from the partner. Tolerance included.
        self.lo = 1.0 / (1.0 + effective_band(cfg.band, request.fairness_threshold)) - RATIO_TOL
        self.hi = 1.0 + effective_band(cfg.gain_band, request.fairness_threshold) + RATIO_TOL
        self.untouchable_min = cfg.untouchable_min_ratio - RATIO_TOL
        self.untouchables = request.untouchable_ids
        self.pins = request.pinned_give_ids | request.pinned_receive_ids
        enforced = [s for s in self.slots if s in LINEUP_SLOT_ELIGIBILITY]
        self.need = tuple(sum(p in LINEUP_SLOT_ELIGIBILITY[s] for s in enforced)
                          for p in CORE_POSITIONS)


class _Package:
    """One side of a candidate trade. `ids` must be sorted by (-market, id). `throwin`, when
    set, is one id in `ids` exempt from the junk rules (floor, filler, reducible): it counts
    toward value, piece counts, positions and roster size, never toward top/low."""
    __slots__ = ("ids", "total", "top", "low", "n", "n_core", "n_players", "n_picks", "n_sub", "pos",
                 "premium", "removable", "untouchable", "throwin")

    def __init__(self, ctx: _Ctx, ids: tuple[str, ...], throwin: str | None = None):
        items = [ctx.assets[a] for a in ids]
        core = [ctx.assets[a] for a in ids if a != throwin]
        self.ids = ids
        self.throwin = throwin
        self.total = sum(a.market for a in items)
        self.top = core[0].market
        self.low = core[-1].market
        self.n = len(ids)
        self.n_core = len(core)   # piece count for the stud premium: a throw-in is not a piece
        self.n_players = sum(a.kind == "player" for a in items)
        self.n_picks = self.n - self.n_players
        # sub-floor players leaving this side: they no longer count as the giver's droppable bench
        self.n_sub = sum(a.kind == "player" and a.market < ctx.floor for a in items)
        self.pos = tuple(sum(a.position == p for a in items) for p in CORE_POSITIONS)
        self.premium = stud_premium(self.top, ctx.elite, ctx.pmax)   # credited if this side holds H
        # markets of the pieces the "reducible" rule may remove: not the top, not pinned, not the throw-in
        self.removable = tuple(ctx.assets[a].market for a in ids[1:]
                               if a not in ctx.pins and a != throwin)
        self.untouchable = not ctx.untouchables.isdisjoint(ids)


class _TeamState:
    """Roster facts the roster-size and lineup rules need, computed once per team."""
    __slots__ = ("players", "droppable", "count", "rows", "unfilled_before", "rebuilding")

    def __init__(self, ctx: _Ctx, team: Team):
        players = [a for a in team.asset_ids if ctx.assets[a].kind == "player"]
        self.players = len(players) + team.other_players
        self.droppable = sum(ctx.assets[a].market < ctx.floor for a in players)
        self.count = tuple(sum(ctx.assets[a].position == p for a in players)
                           for p in CORE_POSITIONS)
        self.rows = [_row(ctx, a) for a in players]
        self.unfilled_before = _unfilled(self.rows, ctx.slots)
        self.rebuilding = ctx.keep_picks and team.window.window == "rebuilder"


def _row(ctx: _Ctx, asset_id: str) -> dict:
    a = ctx.assets[asset_id]
    return {"player_id": asset_id, "position": a.position, "value": a.market}


def _unfilled(rows: list[dict], slots: list[str]) -> int:
    return sum(s["player"] is None for s in optimal_starter_slots(rows, slots))


def _price(g_total: float, g_n: int, r_total: float, r_n: int,
           g: _Package, r: _Package) -> tuple[float, float, str | None]:
    """lld 4.2: (adjusted_ratio, premium, premium_side). The headliner H is the higher of
    the two package tops; a tie across sides means no premium. The side holding H is
    credited only when it has fewer pieces than the other side."""
    if g.top > r.top and g_n < r_n and g.premium > 0.0:
        return r_total / (g_total * (1.0 + g.premium)), g.premium, "give"
    if r.top > g.top and r_n < g_n and r.premium > 0.0:
        return r_total * (1.0 + r.premium) / g_total, r.premium, "receive"
    return r_total / g_total, 0.0, None


def _drops_needed(ctx: _Ctx, v: _TeamState, p: _TeamState,
                  g: _Package, r: _Package) -> tuple[int, int]:
    if ctx.max_players is None:
        return (0, 0)

    def drops(team: _TeamState, out: int, into: int) -> int:
        return max(0, team.players - out + into - max(ctx.max_players, team.players))

    return (drops(v, g.n_players, r.n_players), drops(p, r.n_players, g.n_players))


def _lineup_ok(ctx: _Ctx, team: _TeamState, out: _Package, into: _Package) -> bool:
    """lld 4.4: the trade may not leave more lineup slots unfillable than before."""
    for i in range(len(CORE_POSITIONS)):
        d = into.pos[i] - out.pos[i]
        if d < 0 and team.count[i] + d < ctx.need[i]:
            break
    else:
        return True   # fast accept: every position that dropped still covers its slots
    gone = set(out.ids)
    rows = [row for row in team.rows if row["player_id"] not in gone]
    rows += [_row(ctx, a) for a in into.ids if ctx.assets[a].kind == "player"]
    return _unfilled(rows, ctx.slots) <= team.unfilled_before


def _judge(ctx: _Ctx, v: _TeamState, p: _TeamState, g: _Package, r: _Package,
           ) -> tuple[str | None, float, float, str | None]:
    """The hard rules of lld 4.3 in REJECT_CODES order, viewer gives g and receives r.
    Returns (first failing code or None, adjusted_ratio, premium, premium_side)."""
    ratio, premium, side = _price(g.total, g.n_core, r.total, r.n_core, g, r)
    low = min(g.low, r.low)
    if low < ctx.floor:
        return "floor", ratio, premium, side
    if not ctx.lo <= ratio <= ctx.hi:
        return "band", ratio, premium, side
    if low < max(ctx.floor, ctx.frac * max(g.top, r.top)):
        return "filler", ratio, premium, side
    # Operator, 2026-10-09 (Calibration grades): the viewer never breaks up their best piece
    # for lesser ones — the best piece back must be worth >= breakup_min_ratio of it.
    if r.top < ctx.breakup * g.top - RATIO_TOL:
        return "breakup", ratio, premium, side
    # Operator, 2026-10-09: a rebuilding team (declared rebuilder / "blow it up", or
    # inferred) never trades picks for players — either side of the trade.
    if (v.rebuilding and g.n_picks and r.n_players) or (p.rebuilding and r.n_picks and g.n_players):
        return "picks_for_players", ratio, premium, side
    if g.untouchable and ratio < ctx.untouchable_min:
        return "untouchable", ratio, premium, side
    for x in g.removable:
        if ctx.lo <= _price(g.total - x, g.n_core - 1, r.total, r.n_core, g, r)[0] <= ctx.hi:
            return "reducible", ratio, premium, side
    for x in r.removable:
        if ctx.lo <= _price(g.total, g.n_core, r.total - x, r.n_core - 1, g, r)[0] <= ctx.hi:
            return "reducible", ratio, premium, side
    if ctx.max_players is not None:
        dv, dp = _drops_needed(ctx, v, p, g, r)
        if dv > v.droppable - g.n_sub or dp > p.droppable - r.n_sub:
            return "roster_size", ratio, premium, side
    if not (_lineup_ok(ctx, v, g, r) and _lineup_ok(ctx, p, r, g)):
        return "lineup", ratio, premium, side
    return None, ratio, premium, side


def _fair_trade(ctx: _Ctx, partner_team_id: str, v: _TeamState, p: _TeamState,
                g: _Package, r: _Package, ratio: float, premium: float,
                side: str | None) -> FairTrade:
    return FairTrade(partner_team_id, g.ids, r.ids, g.total, r.total, ratio, premium, side,
                     g.untouchable, _drops_needed(ctx, v, p, g, r), g.throwin or r.throwin)


def _is_junk(ctx: _Ctx, market: float, headliner: float) -> bool:
    """Too small for the junk rules in a trade headlined by `headliner`."""
    return market < max(ctx.floor, ctx.frac * headliner)


def _throwin_pool(ctx: _Ctx, giver: Team, board: Board | None,
                  cfg: CoreConfig, exclude: frozenset[str]) -> list[str]:
    """Every asset of `giver` the recipient's board qualifies as a throw-in, biggest recipient
    surplus (value - market) first. Not capped here: whether a piece is junk depends on the
    pair, so the MAX_THROWIN_OPTIONS cap is applied per pair after that check."""
    if board is None:
        return []
    pool = [a for a in giver.asset_ids
            if a not in exclude and a not in ctx.untouchables
            and throwin_ok(a, board, market=ctx.assets[a].market, cfg=cfg)]
    pool.sort(key=lambda a: (-(board.values[a] - ctx.assets[a].market), a))
    return pool


def _candidates(ctx: _Ctx, team: Team, exclude: frozenset[str], must: frozenset[str],
                max_n: int) -> list[str]:
    """Eligible assets sorted by (-market, id): the top max_n, then any pinned ones not kept.
    The result stays sorted, so every combination of it is sorted too."""
    eligible = sorted((a for a in team.asset_ids
                       if ctx.assets[a].market >= ctx.floor and a not in exclude),
                      key=lambda a: (-ctx.assets[a].market, a))
    return eligible[:max_n] + [a for a in eligible[max_n:] if a in must]


def _packages(ctx: _Ctx, cands: list[str]) -> list[_Package]:
    """Every 1..MAX_PACKAGE_SIZE combination whose smallest piece is at least
    filler_min_frac of its own top piece (the within-package pre-prune)."""
    out = []
    for k in range(1, MAX_PACKAGE_SIZE + 1):
        for ids in combinations(cands, k):
            if k == 1 or ctx.assets[ids[-1]].market >= ctx.frac * ctx.assets[ids[0]].market:
                out.append(_Package(ctx, ids))
    return out


def _interleave(items: list, group_key) -> list:
    """Round-robin over groups, keeping each group's own order: the first item of every
    group (groups in order of first appearance), then every second item, and so on.
    Spreads a capped budget across headliners instead of spending it on the biggest one;
    it uses no preference signal, so the core stays value-only."""
    seen: dict = {}
    ranked = []
    for pos, item in enumerate(items):
        k = group_key(item)
        n = seen.get(k, 0)
        seen[k] = n + 1
        ranked.append((n, pos, item))
    ranked.sort(key=lambda x: (x[0], x[1]))
    return [item for _, _, item in ranked]


def _explicit_throwin(ctx: _Ctx, snapshot: LeagueSnapshot, request: Request, cfg: CoreConfig,
                      partner_team_id: str, give: Sequence[str],
                      receive: Sequence[str]) -> str | None:
    """For an explicit package: the one piece treated as the throw-in, if any. A candidate is
    junk for this trade, not its side's only piece, and qualifies for its recipient (give ->
    the partner's board, receive -> the viewer's). Several candidates: biggest surplus wins."""
    market = lambda a: snapshot.assets[a].market
    headliner = max(market(a) for a in (*give, *receive))
    boards = ((give, snapshot.partner_boards.get(partner_team_id)), (receive, request.board))
    best: tuple | None = None
    for side, board in boards:
        if len(side) < 2 or board is None:
            continue
        for a in side:
            if _is_junk(ctx, market(a), headliner) and throwin_ok(a, board, market=market(a), cfg=cfg):
                key = (-(board.values[a] - market(a)), a)
                if best is None or key < best[0]:
                    best = (key, a)
    return best[1] if best else None


def evaluate_trade(snapshot: LeagueSnapshot, request: Request, cfg: CoreConfig, *,
                   partner_team_id: str, give: Sequence[str],
                   receive: Sequence[str]) -> TradeVerdict:
    """Judge ONE explicit package with the same rules find_fair_trades applies, in the
    order of REJECT_CODES, ignoring top-N truncation, pins and not-interested. `trade`
    is populated whenever both sides are non-empty and priced (even when ok is False),
    so callers can read adjusted_ratio for calibration. Package size is NOT limited here
    (real trades can have 4+ pieces a side; find_fair_trades never generates them).
    Raises ValueError when a give id is not on the viewer's team, a receive id is not on
    the partner's team, a side is empty, or an id is not in snapshot.assets."""
    teams = snapshot.teams
    if request.viewer_team_id not in teams:
        raise ValueError(f"unknown viewer team {request.viewer_team_id!r}")
    if partner_team_id not in teams:
        raise ValueError(f"unknown partner team {partner_team_id!r}")
    if not give or not receive:
        raise ValueError("both sides of the trade must be non-empty")
    for ids, team in ((give, teams[request.viewer_team_id]), (receive, teams[partner_team_id])):
        owned = set(team.asset_ids)
        for a in ids:
            if a not in snapshot.assets:
                raise ValueError(f"unknown asset id {a!r}")
            if a not in owned:
                raise ValueError(f"asset {a!r} is not on team {team.team_id!r}")

    def order(a: str) -> tuple:
        return (-snapshot.assets[a].market, a)

    ctx = _Ctx(snapshot, request, cfg)
    throwin = _explicit_throwin(ctx, snapshot, request, cfg, partner_team_id, give, receive)
    g = _Package(ctx, tuple(sorted(give, key=order)), throwin if throwin in give else None)
    r = _Package(ctx, tuple(sorted(receive, key=order)), throwin if throwin in receive else None)
    if g.total <= 0 or r.total <= 0:   # unpriceable: no ratio to report
        return TradeVerdict(False, "floor" if min(g.low, r.low) < ctx.floor else "band", None)
    v = _TeamState(ctx, teams[request.viewer_team_id])
    p = _TeamState(ctx, teams[partner_team_id])
    reason, ratio, premium, side = _judge(ctx, v, p, g, r)
    return TradeVerdict(reason is None, reason,
                        _fair_trade(ctx, partner_team_id, v, p, g, r, ratio, premium, side))


def find_fair_trades(snapshot: LeagueSnapshot, request: Request, cfg: CoreConfig, *,
                     time_budget_s: float = TIME_BUDGET_S,
                     max_checks_per_partner: int = MAX_CHECKS_PER_PARTNER,
                     ) -> tuple[list[FairTrade], CoreDiagnostics]:
    """The unranked fair pool for the viewer against every partner (or request.partner_team_id).
    Deterministic: same inputs -> same list, same order. Never raises for an empty result.
    Raises ValueError only when request.viewer_team_id is not in snapshot.teams."""
    started = time.perf_counter()
    viewer_id = request.viewer_team_id
    if viewer_id not in snapshot.teams:
        raise ValueError(f"unknown viewer team {viewer_id!r}")
    ctx = _Ctx(snapshot, request, cfg)
    diag = CoreDiagnostics(rejected={code: 0 for code in REJECT_CODES})
    assets = snapshot.assets

    if request.partner_team_id:
        partners = ([request.partner_team_id]
                    if request.partner_team_id in snapshot.teams and request.partner_team_id != viewer_id
                    else [])
    else:
        partners = sorted(t for t in snapshot.teams if t != viewer_id)

    v = _TeamState(ctx, snapshot.teams[viewer_id])
    pins = request.pinned_give_ids
    V = _packages(ctx, _candidates(ctx, snapshot.teams[viewer_id], frozenset(), pins,
                                   cfg.max_assets_per_side))
    if pins and request.pinned_give_mode == "all":
        V = [g for g in V if pins.issubset(g.ids)]
    elif pins:
        V = [g for g in V if not pins.isdisjoint(g.ids)]
    V.sort(key=lambda g: (-g.total, g.ids))
    V = _interleave(V, lambda g: g.ids[0])   # the check cap must not starve smaller headliners
    diag.packages_viewer = len(V)

    # widest raw receive/give window any premium allows (lld 4.5)
    lo_w = ctx.lo / (1.0 + ctx.pmax)
    hi_w = ctx.hi * (1.0 + ctx.pmax)

    def cap_key(t: FairTrade) -> tuple:
        headliner = max(assets[t.give[0]].market, assets[t.receive[0]].market)
        return (-headliner, len(t.give) + len(t.receive), abs(math.log(t.adjusted_ratio)),
                t.give, t.receive)

    out: list[FairTrade] = []
    for pid in partners:
        if time.perf_counter() - started > time_budget_s:
            diag.budget_exhausted = True
            break
        P = _packages(ctx, _candidates(ctx, snapshot.teams[pid], request.not_interested_ids,
                                       request.pinned_receive_ids, cfg.max_assets_per_side))
        if request.pinned_receive_ids:
            P = [r for r in P if not request.pinned_receive_ids.isdisjoint(r.ids)]
            if not P:
                continue
        diag.partners += 1
        P.sort(key=lambda r: (r.total, r.ids))
        totals = [r.total for r in P]
        p = _TeamState(ctx, snapshot.teams[pid])
        # Throw-ins (operator, 2026-10-01): the viewer's go to the partner, judged on the
        # partner's published board; the partner's come to the viewer, judged on the viewer's.
        partner_board = snapshot.partner_boards.get(pid)
        give_tis = _throwin_pool(ctx, snapshot.teams[viewer_id], partner_board, cfg, frozenset())
        recv_tis = _throwin_pool(ctx, snapshot.teams[pid], request.board, cfg,
                                 request.not_interested_ids)
        max_give_ti = max((assets[a].market for a in give_tis), default=0.0)
        max_recv_ti = max((assets[a].market for a in recv_tis), default=0.0)
        with_ti: dict[tuple, _Package] = {}

        def plus(pkg: _Package, ti: str) -> _Package:
            k = (pkg.ids, ti)
            if k not in with_ti:
                ids = tuple(sorted((*pkg.ids, ti), key=lambda a: (-assets[a].market, a)))
                with_ti[k] = _Package(ctx, ids, ti)
            return with_ti[k]

        # Base pairs and throw-in variants have separate check budgets, so variants (which
        # mostly re-dress an idea the deck keeps once) can never starve distinct base pairs.
        checks = {"base": 0, "throwin": 0}
        fair: list[FairTrade] = []
        truncated = stop = False
        for g in V:
            lo_raw, hi_raw = g.total * lo_w, g.total * hi_w
            for k in range(bisect_left(totals, lo_raw - max_recv_ti),
                           bisect_right(totals, (g.total + max_give_ti) * hi_w)):
                r = P[k]
                headliner = max(g.top, r.top)
                variants: list[tuple[str, _Package, _Package]] = []
                if lo_raw <= r.total <= hi_raw:
                    variants.append(("base", g, r))
                if g.n < MAX_PACKAGE_SIZE:
                    tried = 0
                    for ti in give_tis:
                        m = assets[ti].market
                        if tried >= MAX_THROWIN_OPTIONS:
                            break
                        if (ti not in g.ids and _is_junk(ctx, m, headliner)
                                and (g.total + m) * lo_w <= r.total <= (g.total + m) * hi_w):
                            variants.append(("throwin", plus(g, ti), r))
                            tried += 1
                if r.n < MAX_PACKAGE_SIZE:
                    tried = 0
                    for ti in recv_tis:
                        m = assets[ti].market
                        if tried >= MAX_THROWIN_OPTIONS:
                            break
                        if (ti not in r.ids and _is_junk(ctx, m, headliner)
                                and lo_raw <= r.total + m <= hi_raw):
                            variants.append(("throwin", g, plus(r, ti)))
                            tried += 1
                for kind, gg, rr in variants:
                    checks[kind] += 1
                    if checks[kind] > max_checks_per_partner:
                        truncated = True
                        if kind == "base":
                            stop = True
                            break
                        continue
                    if sum(checks.values()) % 1000 == 0 and time.perf_counter() - started > time_budget_s:
                        diag.budget_exhausted = stop = True
                        break
                    diag.pairs_checked += 1
                    reason, ratio, premium, side = _judge(ctx, v, p, gg, rr)
                    if reason is None:
                        fair.append(_fair_trade(ctx, pid, v, p, gg, rr, ratio, premium, side))
                    else:
                        diag.rejected[reason] += 1
                if stop:
                    break
            if stop:
                break
        diag.fair += len(fair)
        if len(fair) > cfg.max_per_partner:
            fair.sort(key=cap_key)
            fair = _interleave(fair, lambda t: (t.give[0], t.receive[0]))[:cfg.max_per_partner]
            truncated = True
        diag.truncated_partners += int(truncated)
        out.extend(fair)
        if diag.budget_exhausted:
            break

    out.sort(key=lambda t: (t.partner_team_id,) + cap_key(t))
    diag.elapsed_ms = int((time.perf_counter() - started) * 1000)
    return out, diag
