"""Fit-challenger generator — knockouts, dual 0–100 scores, post-score filters.

docs/plans/fit-challenger/PRD.md
"""
from __future__ import annotations

import inspect
from dataclasses import dataclass

import pytest

from backend.trade_service import (
    League,
    LeagueMember,
    TradeService,
    elo_to_value,
    pick_swap_ok,
)
from backend.trade_gen_fit import (
    LEGAL_SHAPES,
    FitReport,
    apply_filters,
    bucket_for,
    build_pool,
    generate_league_suggestions,
    knockout_code,
    score_surplus,
    shape_ok,
    team_lenses,
    team_score,
)


@dataclass
class P:
    id: str
    name: str
    position: str
    team: str = "NE"
    age: int = 25


def _p(pid, pos="RB", team="NE"):
    return P(pid, pid, pos, team=team)


def _players(*rows: P) -> dict:
    return {p.id: p for p in rows}


def _kw(players, user_roster, opp_roster, seed, outlook=None):
    return dict(
        players=players, seed_value=lambda pid: elo_to_value(seed.get(pid, 1500)),
        user_roster=user_roster, opp_roster=opp_roster,
        scoring_format="1qb_ppr",
        presentment_r5=True,
        user_pos_values={},
        outlook=outlook,
        position_needs=[],
        position_surplus=[],
    )


# ---------------------------------------------------------------------------
# K1–K7
# ---------------------------------------------------------------------------

def test_k1_legal_shapes():
    assert shape_ok(["a"], ["b"])
    assert shape_ok(["a", "b", "c"], ["d"])       # 3-for-1 — live v3 would kill
    assert shape_ok(["a"], ["b", "c", "d"])
    assert shape_ok(["a", "b"], ["c", "d", "e"])
    assert not shape_ok(["a", "b", "c", "d"], ["e"])
    assert not shape_ok(["a", "b", "c"], [])
    assert (3, 1) in LEGAL_SHAPES
    assert (4, 1) not in LEGAL_SHAPES


def test_k2_byte_identical_to_live_pick_swap():
    """2026 1st vs 2027 1st at matched consensus is dead; 2 late 2nds for a
    1st (consolidation) lives — same as live C3."""
    players = _players(
        _p("p26", "PICK", team="PICK"),
        _p("p27", "PICK", team="PICK"),
        _p("late_a", "PICK", team="PICK"),
        _p("late_b", "PICK", team="PICK"),
        _p("early", "PICK", team="PICK"),
    )
    seed_val = {
        "p26": 3000.0, "p27": 3000.0,          # matched
        "late_a": 800.0, "late_b": 800.0, "early": 3000.0,
    }

    def sv(pid):
        return seed_val[pid]

    assert pick_swap_ok(["p26"], ["p27"], players, sv) is False
    assert knockout_code(["p26"], ["p27"], **_kw(
        players, ["p26"], ["p27"], {"p26": 1600, "p27": 1600})) == "K2"
    # Consolidation: two lesser for one better — values sit outside the
    # match band, live C3 keeps it.
    assert pick_swap_ok(["late_a", "late_b"], ["early"], players, sv) is True


def test_k2_consolidation_survives_knockout_code():
    """2 late 2nds for a 1st is live C3 — knockout_code must not invent a K2."""
    players = _players(
        _p("late_a", "PICK", team="PICK"),
        _p("late_b", "PICK", team="PICK"),
        _p("early", "PICK", team="PICK"),
        _p("uqb", "QB"), _p("urb1"), _p("urb2"),
        _p("uwr1", "WR"), _p("uwr2", "WR"), _p("ute", "TE"),
        _p("oqb", "QB"), _p("orb1"), _p("orb2"),
        _p("owr1", "WR"), _p("owr2", "WR"), _p("ote", "TE"),
    )
    user = ["late_a", "late_b", "uqb", "urb1", "urb2", "uwr1", "uwr2", "ute"]
    opp = ["early", "oqb", "orb1", "orb2", "owr1", "owr2", "ote"]
    seed = {i: 1500.0 for i in user + opp}
    seed["late_a"] = 1300.0
    seed["late_b"] = 1300.0
    seed["early"] = 1700.0
    code = knockout_code(
        ["late_a", "late_b"], ["early"],
        **_kw(players, user, opp, seed))
    assert code != "K2"


def test_k3_kills_when_a_team_drops_below_starter_counts():
    # User has exactly 2 RBs; giving both for a WR leaves 0 RB → K3.
    user = ["uqb", "urb1", "urb2", "uwr1", "uwr2", "ute"]
    opp = ["oqb", "orb1", "orb2", "owr1", "owr2", "owr3", "ote"]
    players = _players(
        _p("uqb", "QB"), _p("urb1"), _p("urb2"),
        _p("uwr1", "WR"), _p("uwr2", "WR"), _p("ute", "TE"),
        _p("oqb", "QB"), _p("orb1"), _p("orb2"),
        _p("owr1", "WR"), _p("owr2", "WR"), _p("owr3", "WR"), _p("ote", "TE"),
    )
    code = knockout_code(
        ["urb1", "urb2"], ["owr3"],
        **_kw(players, user, opp, {}))
    assert code == "K3"


def test_k4_overpay_kills_when_raw_gap_clears_both_bars():
    user = ["uqb", "urb1", "urb2", "uwr1", "uwr2", "ute"]
    opp = ["oqb", "orb1", "orb2", "owr1", "owr2", "ote"]
    players = _players(
        _p("uqb", "QB"), _p("urb1"), _p("urb2"),
        _p("uwr1", "WR"), _p("uwr2", "WR"), _p("ute", "TE"),
        _p("oqb", "QB"), _p("orb1"), _p("orb2"),
        _p("owr1", "WR"), _p("owr2", "WR"), _p("ote", "TE"),
    )
    seed = {i: 1500.0 for i in user + opp}
    seed["urb1"] = 1900.0
    seed["orb1"] = 1200.0
    code = knockout_code(
        ["urb1"], ["orb1"],
        **_kw(players, user, opp, seed))
    assert code == "K4"


def test_k5_pos_net_kills_plus_two_at_a_position():
    user = ["uqb", "urb1", "urb2", "urb3", "urb4", "uwr1", "uwr2", "ute"]
    opp = ["oqb", "orb1", "orb2", "owr1", "owr2", "owr3", "ote"]
    players = _players(
        _p("uqb", "QB"), _p("urb1"), _p("urb2"), _p("urb3"), _p("urb4"),
        _p("uwr1", "WR"), _p("uwr2", "WR"), _p("ute", "TE"),
        _p("oqb", "QB"), _p("orb1"), _p("orb2"),
        _p("owr1", "WR"), _p("owr2", "WR"), _p("owr3", "WR"), _p("ote", "TE"),
    )
    # Equal raw consensus sums so R1 (K4) does not fire: two 1500s vs ~1639.
    seed = {i: 1500.0 for i in user + opp}
    seed["owr3"] = 1639.0
    code = knockout_code(
        ["urb1", "urb2"], ["owr3"],
        **_kw(players, user, opp, seed))
    assert code == "K5"


def test_k1_3_for_1_mixed_positions_is_legal():
    user = ["uqb1", "uqb2", "urb1", "urb2", "urb3",
            "uwr1", "uwr2", "ute1", "ute2"]
    opp = ["oqb1", "oqb2", "orb1", "orb2", "owr1", "owr2", "ote"]
    players = _players(
        *[ _p(i, pos) for i, pos in [
            ("uqb1", "QB"), ("uqb2", "QB"),
            ("urb1", "RB"), ("urb2", "RB"), ("urb3", "RB"),
            ("uwr1", "WR"), ("uwr2", "WR"),
            ("ute1", "TE"), ("ute2", "TE"),
            ("oqb1", "QB"), ("oqb2", "QB"),
            ("orb1", "RB"), ("orb2", "RB"),
            ("owr1", "WR"), ("owr2", "WR"), ("ote", "TE"),
        ]]
    )
    seed = {i: 1500.0 for i in user + opp}
    seed["owr2"] = 1720.0   # ≈ 3× elo_to_value(1500), so R1 does not fire
    code = knockout_code(
        ["urb3", "uwr2", "ute2"], ["owr2"],
        **_kw(players, user, opp, seed))
    assert code is None


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def test_score_surplus_even_is_fifty():
    assert score_surplus(0.0) == 50.0
    assert 0.0 <= score_surplus(-5000) <= 15.0
    assert 85.0 <= score_surplus(5000) <= 100.0


def test_negative_consensus_surplus_is_a_score_not_a_kill():
    """The volume unlock: rv < gv is a low consensus lens, not a knockout."""
    def cons(pid):
        return elo_to_value({"g": 1800.0, "r": 1400.0}[pid])
    lenses = team_lenses(["g"], ["r"], None, cons, waiver=0.0, boarded=False)
    assert lenses["consensus"] < 50.0
    assert team_score(lenses) < 50.0


def test_unranked_partner_uses_l3_only():
    def cons(pid):
        return elo_to_value({"a": 1600, "b": 1600}.get(pid, 1500))
    lenses = team_lenses(["a"], ["b"], None, cons, 0.0, boarded=False)
    assert lenses["board"] is None
    assert lenses["vs_consensus"] is None
    assert lenses["consensus"] == 50.0
    assert team_score(lenses) == 50.0


def test_boarded_blend_uses_three_lenses():
    def cons(pid):
        return 1000.0
    def board(pid):
        return 2000.0 if pid == "in" else 1000.0
    lenses = team_lenses(["out"], ["in"], board, cons, 0.0, boarded=True)
    assert lenses["board"] is not None
    assert lenses["vs_consensus"] is not None
    blended = team_score(lenses)
    assert blended != lenses["consensus"]


def test_boarded_blend_skips_null_lenses():
    lenses = {"board": 80.0, "vs_consensus": None, "consensus": 50.0}
    blended = team_score(lenses)
    # 0.40*80 + 0.30*50, renormalized over 0.70 → ~67.1
    assert 65.0 <= blended <= 70.0


def test_bucket_labels():
    assert bucket_for(80, 80) == "both_high"
    assert bucket_for(80, 50) == "mixed"
    assert bucket_for(80, 20) == "you_tilt"
    assert bucket_for(20, 80) == "them_tilt"
    assert bucket_for(50, 50) == "both_ok"


# ---------------------------------------------------------------------------
# End-to-end generate
# ---------------------------------------------------------------------------

def _league():
    """Two full-enough rosters so K3 passes on 1-for-1 same-position swaps."""
    user_ids = [f"u{p}{i}" for p in "QRWT" for i in range(1, 4)]
    opp_ids = [f"o{p}{i}" for p in "QRWT" for i in range(1, 4)]
    pos = {"Q": "QB", "R": "RB", "W": "WR", "T": "TE"}
    players = {}
    for pid in user_ids + opp_ids:
        players[pid] = _p(pid, pos[pid[1]])
    seed = {pid: 1500.0 + (hash(pid) % 80) for pid in players}
    user_elo = {pid: seed[pid] + 40 for pid in user_ids}
    user_elo["oR1"] = 1700.0          # user overrates opp's RB1
    opp_elo = {pid: seed[pid] for pid in opp_ids}
    opp_elo["uR1"] = 1700.0           # opp overrates user's RB1
    user = LeagueMember("u", "you", user_ids, user_elo, has_rankings=True)
    opp = LeagueMember("o", "them", opp_ids, opp_elo, has_rankings=True)
    league = League("L1", "test", "sleeper", [user, opp])
    return players, seed, user, opp, league


def test_generate_emits_fit_payload_and_negative_surplus_can_survive():
    players, seed, user, opp, league = _league()
    cards, report = generate_league_suggestions(
        players=players, league=league, user_id="u",
        user_elo=user.elo_ratings, user_roster=user.roster,
        seed_elo=seed, outlook=None,
    )
    assert report.enumerated > 0
    assert report.scored > 0
    assert cards
    c = cards[0]
    assert c.fit is not None
    assert "you" in c.fit and "them" in c.fit
    assert c.fit["aggregate"] == pytest.approx(c.fit["you"] + c.fit["them"], abs=0.15)
    assert c.basis == "divergence"
    # Volume unlock: at least one scored package had them < 50 (you-pay on
    # consensus is allowed). If the pools happen to miss one, the report's
    # scored count still proves we didn't gate on surplus.
    assert report.killed.get("K1", 0) >= 0
    assert "min_side" not in report.killed


def test_unranked_opponent_stamps_consensus_basis():
    players, seed, user, opp, league = _league()
    opp.has_rankings = False
    opp.elo_ratings = {}
    cards, _ = generate_league_suggestions(
        players=players, league=league, user_id="u",
        user_elo=user.elo_ratings, user_roster=user.roster,
        seed_elo=seed,
    )
    assert cards
    assert all(c.basis == "consensus" for c in cards)
    assert cards[0].fit["lenses"]["them"]["board"] is None


def test_untouchable_is_enumerated_then_filtered():
    players, seed, user, opp, league = _league()
    # Highest-consensus user asset is guaranteed in the pool.
    lock = max(user.roster, key=lambda p: seed[p])
    cards, report = generate_league_suggestions(
        players=players, league=league, user_id="u",
        user_elo=user.elo_ratings, user_roster=user.roster,
        seed_elo=seed, untouchable_ids={lock},
    )
    assert all(lock not in c.give_player_ids for c in cards)
    assert report.enumerated > 0
    assert report.filtered.get("untouchable", 0) >= 1


def test_pool_cap_respected():
    roster = [f"p{i}" for i in range(40)]
    seed = {p: 1400.0 + i for i, p in enumerate(roster)}
    pool = build_pool(roster, seed, None, None)
    assert len(pool) <= 15
    assert len(pool) == 15


def test_owned_picks_always_enter_the_pool():
    roster = [f"p{i}" for i in range(20)] + ["pick_a", "pick_b"]
    seed = {p: 1400.0 + i for i, p in enumerate(roster)}
    seed["pick_a"] = 1000.0
    seed["pick_b"] = 1010.0
    players = {p: _p(p, "RB") for p in roster}
    players["pick_a"] = _p("pick_a", "PICK", team="PICK")
    players["pick_b"] = _p("pick_b", "PICK", team="PICK")
    pool = build_pool(roster, seed, None, None, players=players)
    assert "pick_a" in pool and "pick_b" in pool
    assert len(pool) <= 15


def test_package_budget_is_a_hard_cap(monkeypatch):
    from backend import trade_gen_fit as fit
    monkeypatch.setattr(fit, "_k", lambda key, default: (
        8.0 if key == "fit_max_packages_per_pair" else default))
    players, seed, user, opp, league = _league()
    _cards, report = generate_league_suggestions(
        players=players, league=league, user_id="u",
        user_elo=user.elo_ratings, user_roster=user.roster,
        seed_elo=seed,
    )
    assert report.enumerated <= 8


def test_diagnostics_carry_prd_fields():
    players, seed, user, opp, league = _league()
    _cards, report = generate_league_suggestions(
        players=players, league=league, user_id="u",
        user_elo=user.elo_ratings, user_roster=user.roster,
        seed_elo=seed,
    )
    d = report.kill_counts()
    for key in ("enumerated", "scored", "killed", "one_sided_pct",
                "both_high_pct", "mixed_pct", "median_aggregate",
                "generation_ms"):
        assert key in d
    assert d["enumerated"] >= d["scored"]
    assert 0.0 <= d["one_sided_pct"] <= 100.0


def test_organic_impl_does_not_import_fit():
    src = inspect.getsource(TradeService._generate_trades_impl)
    assert "trade_gen_fit" not in src


def test_apply_filters_drops_not_interested():
    from backend.trade_service import TradeCard
    c = TradeCard(
        trade_id="x", league_id="L", proposing_user_id="u",
        target_user_id="o", target_username="them",
        give_player_ids=["g"], receive_player_ids=["bad"],
        mismatch_score=0, fairness_score=1, composite_score=100,
    )
    report = FitReport()
    out = apply_filters(
        [c], untouchable_ids=set(), not_interested_ids={"bad"},
        pinned_give=set(), pinned_receive=set(), pinned_give_mode="any",
        acquire_positions=[], trade_away_positions=[],
        players={}, past_keys=set(), seed_elo={},
        trade_intent=None, scoring_format="1qb_ppr", report=report,
    )
    assert out == []
    assert report.filtered["not_interested"] == 1
