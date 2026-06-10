"""Tests for trade-engine Tier 2 work items 2.1 + 2.2
(docs/plans/trade-engine-tier2-models.md).

Covers:
  - replacement_levels(): next-best-at-position-outside-starters, superflex
    QB bump, waiver baseline when a position is thin
  - marginal_value(): over-replacement + bench credit, raw passthrough for
    positions outside QB/RB/WR/TE
  - flag trade.marginal_value: a 3rd starting-caliber QB in a 1QB league is
    gated (~0 marginal gain); the same QB to a QB-needy roster passes; a
    need-filling trade outranks an equal-raw-value depth-stacking trade
  - flag trade.outlook_blend: the same young-WR-for-aging-RB trade ranks
    higher for a rebuilder than a championship roster; α map; age curves
  - both flags OFF → v2 output identical to Tier 1 (outlook kwarg inert)

All fixtures are tiny and deterministic — no RNG. Flag + config mutations
are snapshot/restored by an autouse fixture (same style as
test_trade_engine_v2.py).
"""

from dataclasses import dataclass
from typing import Optional

import pytest

import backend.feature_flags as ff
import backend.trade_service as ts
from backend.trade_service import (
    League,
    LeagueMember,
    TradeCard,
    TradeService,
    age_future_mult,
    age_now_mult,
    elo_to_value,
    marginal_value,
    outlook_alpha,
    outlook_blend_mult,
    replacement_levels,
)


# ---------------------------------------------------------------------------
# Shared helpers / fixtures
# ---------------------------------------------------------------------------

@dataclass
class _Player:
    id: str
    name: str
    position: str = "RB"
    team: str = "TST"
    age: int = 24
    ktc_value: Optional[int] = None


@pytest.fixture(autouse=True)
def _isolate_flags_and_cfg():
    """Pin flags to all-off defaults and _cfg to code defaults for every test,
    then restore whatever was there before."""
    old_flags = ff._flags_cache
    old_cfg = dict(ts._cfg)
    ff._flags_cache = dict(ff.DEFAULT_FLAGS)          # everything OFF
    ts._cfg.clear()
    ts._cfg.update(ts._DEFAULT_CFG)                   # pristine config
    try:
        yield
    finally:
        ff._flags_cache = old_flags
        ts._cfg.clear()
        ts._cfg.update(old_cfg)


def _set_flags(*extra: str) -> None:
    """Enable trade_engine.v2 plus any extra dotted flag keys."""
    cache = dict(ff.DEFAULT_FLAGS)
    cache["trade_engine.v2"] = True
    for key in extra:
        assert key in cache, f"unknown flag key {key!r}"
        cache[key] = True
    ff._flags_cache = cache


def _member(user_id: str, roster: list[str], elo: dict[str, float],
            has_rankings: bool = True) -> LeagueMember:
    return LeagueMember(user_id=user_id, username=user_id, roster=roster,
                        elo_ratings=elo, has_rankings=has_rankings)


def _build(players: dict, opponents: list[LeagueMember]) -> TradeService:
    svc = TradeService(players=players)
    svc.add_league(League(league_id="L1", name="Tier2 League",
                          platform="demo", members=opponents))
    return svc


def _gen(svc: TradeService, user_elo: dict[str, float], user_roster: list[str],
         seed_elo: dict[str, float], **kw) -> list[TradeCard]:
    return svc.generate_trades(
        user_id="user",
        user_elo=user_elo,
        user_roster=user_roster,
        league_id="L1",
        seed_elo=seed_elo,
        **kw,
    )


def _key(c: TradeCard) -> tuple:
    """Stable identity for a card (trade_id is a fresh uuid every run)."""
    return (
        c.target_user_id,
        tuple(sorted(c.give_player_ids)),
        tuple(sorted(c.receive_player_ids)),
        round(c.mismatch_score, 3),
        round(c.fairness_score, 3),
        round(c.composite_score, 3),
        c.basis,
    )


def _find(cards: list[TradeCard], give: list[str],
          recv: list[str]) -> TradeCard | None:
    for c in cards:
        if (sorted(c.give_player_ids) == sorted(give)
                and sorted(c.receive_player_ids) == sorted(recv)):
            return c
    return None


def _players_of(spec: dict[str, tuple[str, int]]) -> dict:
    """spec: pid → (position, age)."""
    return {
        pid: _Player(id=pid, name=f"Player {pid}", position=pos, age=age)
        for pid, (pos, age) in spec.items()
    }


# ---------------------------------------------------------------------------
# 1. replacement_levels unit behaviour
# ---------------------------------------------------------------------------

def test_replacement_levels_next_best_and_waiver():
    players = _players_of({
        "q1": ("QB", 25), "q2": ("QB", 25), "q3": ("QB", 25),
        "w1": ("WR", 25),
        "r1": ("RB", 25), "r2": ("RB", 25), "r3": ("RB", 25), "r4": ("RB", 25),
    })
    vals = {"q1": 3000.0, "q2": 2000.0, "q3": 800.0,
            "w1": 1500.0,
            "r1": 2500.0, "r2": 2200.0, "r3": 1100.0, "r4": 900.0}
    roster = list(vals)

    levels = replacement_levels(roster, vals.__getitem__, players, "1qb_ppr")

    # QB in 1QB: 1 starter -> replacement is the 2nd-best QB.
    assert levels["QB"] == pytest.approx(2000.0)
    # RB starts 2 -> replacement is the 3rd-best RB.
    assert levels["RB"] == pytest.approx(1100.0)
    # WR starts 2 but only 1 rostered (< starters+1) -> waiver baseline.
    assert levels["WR"] == pytest.approx(ts._cfg["waiver_baseline_value"])
    # TE empty -> waiver baseline.
    assert levels["TE"] == pytest.approx(ts._cfg["waiver_baseline_value"])

    # Superflex bumps QB starters to 2 -> replacement is the 3rd-best QB.
    levels_sf = replacement_levels(roster, vals.__getitem__, players, "sf_tep")
    assert levels_sf["QB"] == pytest.approx(800.0)
    assert levels_sf["RB"] == pytest.approx(1100.0)


def test_marginal_value_units():
    players = _players_of({"q1": ("QB", 25), "q2": ("QB", 25),
                           "pk": ("PICK", 0)})
    vals = {"q1": 3000.0, "q2": 2000.0, "pk": 1200.0}
    levels = {"QB": 2000.0, "RB": 250.0, "WR": 250.0, "TE": 250.0}
    rate = ts._cfg["bench_credit_rate"]

    # Over-replacement + bench credit.
    assert marginal_value("q1", vals.__getitem__, levels, players) == \
        pytest.approx(1000.0 + rate * 3000.0)
    # At replacement: only the bench credit remains (~0 marginal gain).
    assert marginal_value("q2", vals.__getitem__, levels, players) == \
        pytest.approx(rate * 2000.0)
    # No replacement concept (PICK) -> raw value untouched.
    assert marginal_value("pk", vals.__getitem__, levels, players) == \
        pytest.approx(1200.0)


# ---------------------------------------------------------------------------
# 2. Marginal flag: 3rd QB in a 1QB league is gated; QB-needy roster passes
# ---------------------------------------------------------------------------

# Opponent owns QB3 and covets the user's RB "G" (opp Elo 1800 vs user 1640).
# The user values QB3 (1650) above the opponent (1500) — a strong raw
# divergence trade [G] -> [QB3] that v2-without-marginal happily surfaces.
_QB_PLAYERS = {
    "QB1": ("QB", 26), "QB2": ("QB", 26), "QB3": ("QB", 26),
    "RB1": ("RB", 24), "RB2": ("RB", 24), "G": ("RB", 24),
}
_QB_USER_ELO = {"QB1": 1750, "QB2": 1700, "RB1": 1700, "RB2": 1690,
                "G": 1640, "QB3": 1650}
_QB_OPP_ELO = {"QB3": 1500, "G": 1800, "QB1": 1500, "QB2": 1500,
               "RB1": 1450, "RB2": 1450}
_QB_SEEDS = {pid: 1500.0 for pid in _QB_PLAYERS}


def _qb_fixture(user_roster: list[str]) -> tuple[TradeService, dict, dict]:
    opp = _member("opp", ["QB3"], dict(_QB_OPP_ELO))
    svc = _build(_players_of(_QB_PLAYERS), [opp])
    return svc, dict(_QB_USER_ELO), dict(_QB_SEEDS)


_QB_STACKED_ROSTER = ["QB1", "QB2", "RB1", "RB2", "G"]   # 2 starting-cal QBs
_QB_NEEDY_ROSTER = ["RB1", "RB2", "G"]                   # no QB at all


def test_third_qb_gated_with_marginal_on():
    """User already starts QB1/QB2 in a 1QB league: receiving QB3 is worth
    only its bench credit, so the marginal user surplus (~34 value units)
    sits below min_side_surplus_marginal and the trade is gated."""
    _set_flags("trade.marginal_value")
    svc, user_elo, seeds = _qb_fixture(_QB_STACKED_ROSTER)
    cards = _gen(svc, user_elo, list(_QB_STACKED_ROSTER), seeds,
                 confidence=None)
    assert cards == [], (
        f"3rd-QB depth-stack should be marginal-gated, got "
        f"{[_key(c) for c in cards]}"
    )

    # Sanity: WITHOUT the marginal flag the same raw-divergence trade
    # surfaces — the gate above is doing the work, not the fixture.
    _set_flags()
    svc2, user_elo2, seeds2 = _qb_fixture(_QB_STACKED_ROSTER)
    raw_cards = _gen(svc2, user_elo2, list(_QB_STACKED_ROSTER), seeds2,
                     confidence=None)
    assert _find(raw_cards, ["G"], ["QB3"]) is not None, (
        "fixture broken: raw v2 should surface [G] -> [QB3]"
    )


def test_same_qb_passes_for_needy_roster():
    """Identical trade, but the user has NO quarterback: replacement falls
    to the waiver baseline, QB3's marginal value is nearly his full raw
    value, and the card surfaces."""
    _set_flags("trade.marginal_value")
    svc, user_elo, seeds = _qb_fixture(_QB_NEEDY_ROSTER)
    cards = _gen(svc, user_elo, list(_QB_NEEDY_ROSTER), seeds,
                 confidence=None)
    assert _find(cards, ["G"], ["QB3"]) is not None, (
        f"QB-needy roster should land [G] -> [QB3], got "
        f"{[_key(c) for c in cards]}"
    )


# ---------------------------------------------------------------------------
# 3. Marginal flag: need-filler outranks equal-raw-value depth-stacker
# ---------------------------------------------------------------------------

def test_need_filling_outranks_depth_stacking():
    """Opponent offers W (WR) and B (RB) at IDENTICAL user Elo (=> identical
    raw value). The user is WR-empty but three deep at RB, so receiving W
    must outscore receiving B under marginal valuation."""
    _set_flags("trade.marginal_value")
    players = _players_of({
        "RB1": ("RB", 24), "RB2": ("RB", 24), "G": ("RB", 24),
        "W": ("WR", 24), "B": ("RB", 24),
    })
    user_elo = {"RB1": 1700, "RB2": 1690, "G": 1640, "W": 1650, "B": 1650}
    opp_elo = {"W": 1500, "B": 1500, "G": 1800, "RB1": 1450, "RB2": 1450}
    seeds = {pid: 1500.0 for pid in players}

    opp = _member("opp", ["W", "B"], opp_elo)
    svc = _build(players, [opp])
    cards = _gen(svc, user_elo, ["RB1", "RB2", "G"], seeds, confidence=None)

    need_filler = _find(cards, ["G"], ["W"])
    depth_stack = _find(cards, ["G"], ["B"])
    assert need_filler is not None, "need-filling [G] -> [W] card missing"
    assert depth_stack is not None, "depth-stacking [G] -> [B] card missing"
    # Equal raw value by construction (same user Elo) — only roster context
    # separates them.
    assert elo_to_value(user_elo["W"]) == elo_to_value(user_elo["B"])
    assert need_filler.composite_score > depth_stack.composite_score
    assert cards[0] is need_filler, "need-filler should top the deck"


# ---------------------------------------------------------------------------
# 4. Outlook blend: rebuilder ranks youth-for-vet higher than championship
# ---------------------------------------------------------------------------

_OUT_PLAYERS = {"WRY": ("WR", 22), "RBO": ("RB", 29)}
_OUT_USER_ELO = {"WRY": 1600, "RBO": 1480}
_OUT_OPP_ELO = {"WRY": 1480, "RBO": 1600}
_OUT_SEEDS = {"WRY": 1500.0, "RBO": 1500.0}


def _outlook_run(outlook: str | None) -> list[TradeCard]:
    opp = _member("opp", ["WRY"], dict(_OUT_OPP_ELO))
    svc = _build(_players_of(_OUT_PLAYERS), [opp])
    return _gen(svc, dict(_OUT_USER_ELO), ["RBO"], dict(_OUT_SEEDS),
                confidence=None, outlook=outlook)


def test_outlook_rebuilder_outranks_championship():
    """User receives a 22-year-old WR for a 29-year-old RB. The rebuilder
    blend (α=0.25, future-weighted) values that swap more than the
    championship blend (α=1.0, pure now)."""
    _set_flags("trade.outlook_blend")
    champ = _find(_outlook_run("championship"), ["RBO"], ["WRY"])
    rebuild = _find(_outlook_run("rebuilder"), ["RBO"], ["WRY"])
    assert champ is not None, "championship run lost the engineered card"
    assert rebuild is not None, "rebuilder run lost the engineered card"
    assert rebuild.composite_score > champ.composite_score
    assert rebuild.mismatch_score > champ.mismatch_score   # bigger user surplus


def test_outlook_flag_off_is_inert():
    """With trade.outlook_blend OFF, the outlook kwarg must not move a
    single byte of v2 output (Tier 1 behavior preserved)."""
    _set_flags()                                   # v2 only, blend OFF
    base = [_key(c) for c in _outlook_run(None)]
    for outlook in ("championship", "contender", "not_sure",
                    "rebuilder", "jets"):
        assert [_key(c) for c in _outlook_run(outlook)] == base, (
            f"outlook={outlook!r} changed output with the blend flag OFF"
        )


def test_outlook_alpha_map():
    assert outlook_alpha("championship") == pytest.approx(1.0)
    assert outlook_alpha("contender") == pytest.approx(0.75)
    assert outlook_alpha("not_sure") == pytest.approx(0.5)
    assert outlook_alpha(None) == pytest.approx(0.5)
    assert outlook_alpha("rebuilder") == pytest.approx(0.25)
    assert outlook_alpha("jets") == pytest.approx(0.1)
    assert outlook_alpha("nonsense") == pytest.approx(0.5)   # unknown -> 50/50


# ---------------------------------------------------------------------------
# 5. Age curves
# ---------------------------------------------------------------------------

def test_age_curves_rb_cliff_and_youth():
    # now_mult: RB peaks 23-26, then declines monotonically toward the floor.
    assert age_now_mult("RB", 26) == pytest.approx(1.05)
    decline = [age_now_mult("RB", a) for a in range(26, 30)]
    assert all(b < a for a, b in zip(decline, decline[1:])), (
        "RB now-curve should strictly decline after 26 (until the floor)"
    )
    assert age_now_mult("RB", 40) == pytest.approx(0.60)     # floor holds

    # future_mult: a 22-year-old RB beats a 27-year-old.
    assert age_future_mult("RB", 22) > age_future_mult("RB", 27)

    # QB ~flat into the 30s on the now-curve.
    assert age_now_mult("QB", 33) == pytest.approx(1.0)

    # Unknown age / unknown position -> exactly 1.0 from both curves.
    for fn in (age_now_mult, age_future_mult):
        assert fn("RB", None) == 1.0
        assert fn("RB", 0) == 1.0
        assert fn("PICK", 27) == 1.0
        assert fn(None, 27) == 1.0
    # ... and therefore from the blend at any alpha.
    assert outlook_blend_mult("WR", None, 0.25) == 1.0


# ---------------------------------------------------------------------------
# 6. Both Tier 2 flags off -> v2 output identical to Tier 1
# ---------------------------------------------------------------------------

# Mutual-divergence fixture that yields multiple v2 cards (mirrors the
# harmonic-ranking fixture in test_trade_engine_v2.py). RB positions with
# default age 24 — the outlook blend WOULD move these values if it leaked,
# since the RB curves are not 1.0 at 24.
_PAR_IDS = ["A", "B", "C", "D"]
_PAR_USER_ELO = {"A": 1500, "C": 1500, "B": 1540, "D": 1575}
_PAR_OPP_ELO = {"A": 1540, "C": 1520, "B": 1500, "D": 1500}
_PAR_SEEDS = {pid: 1500.0 for pid in _PAR_IDS}


def _parity_run(**kw) -> list[TradeCard]:
    opp = _member("opp", ["B", "D"], dict(_PAR_OPP_ELO))
    svc = _build(_players_of({pid: ("RB", 24) for pid in _PAR_IDS}), [opp])
    return _gen(svc, dict(_PAR_USER_ELO), ["A", "C"],
                dict(_PAR_SEEDS), confidence=None, **kw)


def test_tier2_flags_off_v2_byte_identical():
    """trade.marginal_value and trade.outlook_blend OFF: the v2 deck is
    byte-identical whether or not the new outlook kwarg is supplied —
    i.e. Tier 1 output is fully preserved by default."""
    _set_flags()                                   # v2 only
    baseline = [_key(c) for c in _parity_run()]
    assert baseline, "parity fixture produced no v2 cards"
    assert [_key(c) for c in _parity_run()] == baseline          # deterministic
    assert [_key(c) for c in _parity_run(outlook="jets")] == baseline
    assert [_key(c) for c in _parity_run(outlook="championship")] == baseline
