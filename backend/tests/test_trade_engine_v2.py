"""Tests for the trade-engine v2 (flag: trade_engine.v2).

Covers the v2 scoring path in backend/trade_service.py:
  - elo_to_value / package_value_v2 / _harmonic_mean unit behaviour
  - confidence shrinkage (_shrink_user_elo) and range-overlap fairness (A4)
  - true-mutual-gain gate (both surpluses >= min_side_surplus)
  - harmonic-mean ranking of candidates (A1)
  - waiver-slot cost on the side receiving more players (A3)
  - bounded top-K heap (true top-N regardless of enumeration order)
  - consensus-basis cards for unranked opponents
  - legacy-path parity when the flag is OFF (incl. the new `confidence`
    kwarg being a no-op for legacy)
  - fairness_score field semantics in BOTH paths

All fixtures are tiny (1-7 players a side) and fully deterministic — no RNG.
Flag + config mutations are snapshot/restored by an autouse fixture.
"""

import math
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
    elo_to_value,
    package_value_v2,
    _harmonic_mean,
    _shrink_user_elo,
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
    then restore whatever was there before (other test modules may rely on
    the lazily-computed flag cache or a reload_config()'d _cfg)."""
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


def _set_v2(enabled: bool) -> None:
    """Turn the trade_engine.v2 flag on/off (all other flags stay False)."""
    cache = dict(ff.DEFAULT_FLAGS)
    cache["trade_engine.v2"] = enabled
    ff._flags_cache = cache


def _make_service(player_ids: list[str]) -> TradeService:
    players = {
        pid: _Player(id=pid, name=f"Player {pid}", position="RB")
        for pid in player_ids
    }
    return TradeService(players=players)


def _member(user_id: str, roster: list[str], elo: dict[str, float],
            has_rankings: bool = True) -> LeagueMember:
    return LeagueMember(user_id=user_id, username=user_id, roster=roster,
                        elo_ratings=elo, has_rankings=has_rankings)


def _build(player_ids: list[str], opponents: list[LeagueMember]) -> TradeService:
    svc = _make_service(player_ids)
    svc.add_league(League(league_id="L1", name="Test League",
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


def _is_multi(c: TradeCard) -> bool:
    return len(c.give_player_ids) > 1 or len(c.receive_player_ids) > 1


# ---------------------------------------------------------------------------
# Fixture data
# ---------------------------------------------------------------------------

# Legacy-parity fixture: 7v7 with clear divergence (mirrors fixture A of
# test_trade_gen_prune.py). Yields several 1-for-1 cards in the legacy path;
# multi-player shapes are gated by the legacy KTC package-weight fairness
# (all stub players share the fallback dynasty value, so a 2-pack/1-pack
# ratio is 1.75/1.0 -> 0.571 < 0.75).
_IDS_PARITY = [f"u{i}" for i in range(1, 8)] + [f"o{i}" for i in range(1, 8)]
_USER_ELO_PARITY = {
    "u1": 1720, "u2": 1680, "u3": 1560, "u4": 1490, "u5": 1430, "u6": 1380, "u7": 1300,
    "o1": 1420, "o2": 1390, "o3": 1530, "o4": 1480, "o5": 1420, "o6": 1370, "o7": 1290,
}
_OPP_ELO_PARITY = {
    "u1": 1800, "u2": 1760, "u3": 1540, "u4": 1470, "u5": 1420, "u6": 1360, "u7": 1290,
    "o1": 1710, "o2": 1690, "o3": 1540, "o4": 1480, "o5": 1430, "o6": 1370, "o7": 1300,
}
_SEED_PARITY = {pid: 1500.0 for pid in _IDS_PARITY}


def _parity_setup():
    opp = _member("opp", [f"o{i}" for i in range(1, 8)], dict(_OPP_ELO_PARITY))
    svc = _build(_IDS_PARITY, [opp])
    return svc, dict(_USER_ELO_PARITY), [f"u{i}" for i in range(1, 8)], dict(_SEED_PARITY)


# Multi-player fixture: user owns two mid players M1/M2 the opponent covets
# (opp 1650 vs user 1620 each); opponent owns elite E the user covets
# (user 1850 vs opp 1600). Seeds (M=1650, E=1700) make ONLY the 2-for-1
# consensus-fair in v2 value space (single M vs E is 0.572 < 0.75; the
# 2-pack vs E is 0.874 >= 0.75). The legacy path gates the 2-for-1 both on
# KTC package weights and on its recv_user > combined_give*0.95 rule.
_IDS_MULTI = ["M1", "M2", "E"]
_USER_ELO_MULTI = {"M1": 1620, "M2": 1620, "E": 1850}
_OPP_ELO_MULTI = {"M1": 1650, "M2": 1650, "E": 1600}
_SEED_MULTI = {"M1": 1650, "M2": 1650, "E": 1700}


def _multi_setup():
    opp = _member("opp", ["E"], dict(_OPP_ELO_MULTI))
    svc = _build(_IDS_MULTI, [opp])
    return svc, dict(_USER_ELO_MULTI), ["M1", "M2"], dict(_SEED_MULTI)


# ---------------------------------------------------------------------------
# 1. Flag-off parity (legacy path untouched, confidence kwarg is a no-op)
# ---------------------------------------------------------------------------

def test_flag_off_parity():
    _set_v2(False)

    svc1, user_elo, roster, seeds = _parity_setup()
    cards_none = _gen(svc1, user_elo, roster, seeds, confidence=None)

    svc2, user_elo2, roster2, seeds2 = _parity_setup()
    confidence = {pid: 25 for pid in _IDS_PARITY}
    cards_conf = _gen(svc2, user_elo2, roster2, seeds2, confidence=confidence)

    assert cards_none, "legacy path returned no cards — fixture broken"

    # Legacy characteristics on this fixture: only 1-for-1 shapes survive
    # (multi-player shapes are KTC-gated), and v2-only attrs sit at defaults.
    for c in cards_none:
        assert len(c.give_player_ids) == 1
        assert len(c.receive_player_ids) == 1
        assert c.basis == "divergence"          # dataclass default, untouched
        assert c.mismatch_score > 0

    # confidence=... must not alter legacy output in any way.
    assert [_key(c) for c in cards_none] == [_key(c) for c in cards_conf], (
        "confidence kwarg changed legacy-path output"
    )


# ---------------------------------------------------------------------------
# 2. Multi-player trades become reachable under v2
# ---------------------------------------------------------------------------

def test_multi_player_reachable_v2():
    _set_v2(True)
    svc, user_elo, roster, seeds = _multi_setup()
    v2_cards = _gen(svc, user_elo, roster, seeds, confidence=None)

    multi = [c for c in v2_cards if _is_multi(c)]
    assert multi, "v2 produced no 2-for-1 / 1-for-2 cards on a fixture built for them"
    assert any(
        sorted(c.give_player_ids) == ["M1", "M2"]
        and c.receive_player_ids == ["E"]
        for c in multi
    ), f"expected the engineered [M1, M2] -> [E] card, got {[_key(c) for c in v2_cards]}"

    _set_v2(False)
    svc2, user_elo2, roster2, seeds2 = _multi_setup()
    legacy_cards = _gen(svc2, user_elo2, roster2, seeds2)
    assert not any(_is_multi(c) for c in legacy_cards), (
        "legacy path unexpectedly produced a multi-player card"
    )


# ---------------------------------------------------------------------------
# 3. One-sided trades never surface in v2
# ---------------------------------------------------------------------------

def test_no_one_sided_trades_v2():
    """user_surplus is hugely negative while opp_surplus is huge — the
    both-sides gate (min_side_surplus) must keep the trade dark."""
    _set_v2(True)
    # User gives G (values it 1700) for R (values it 1550) -> user loses big.
    # Opponent values G at 1900 vs R at 1500 -> opponent gains big.
    # Seeds equal so consensus fairness passes; Elo gap 150 <= 250 passes.
    # The ONLY thing standing in the way is the user-surplus gate.
    user_elo = {"G": 1700, "R": 1550}
    opp_elo = {"G": 1900, "R": 1500}
    seeds = {"G": 1500, "R": 1500}
    opp = _member("opp", ["R"], opp_elo)
    svc = _build(["G", "R"], [opp])

    cards = _gen(svc, user_elo, ["G"], seeds, confidence=None)
    assert cards == [], (
        f"one-sided trade surfaced despite negative user surplus: "
        f"{[_key(c) for c in cards]}"
    )


# ---------------------------------------------------------------------------
# 4. Harmonic-mean ranking prefers balanced mutual gain
# ---------------------------------------------------------------------------

def test_harmonic_ranking():
    """Balanced (~+440 / +440 value units) must outrank lopsided
    (~+820 / +220) even though the lopsided trade has the larger total."""
    _set_v2(True)
    # All four players sit in the same user-Elo tier band (solid, 1460-1579)
    # so the tier multiplier is identical; seeds all equal so fairness is
    # 1.0 for every candidate — ranking is purely the harmonic mean.
    user_elo = {"A": 1500, "C": 1500, "B": 1540, "D": 1575}
    opp_elo = {"A": 1540, "C": 1520, "B": 1500, "D": 1500}
    seeds = {p: 1500 for p in ("A", "B", "C", "D")}
    opp = _member("opp", ["B", "D"], opp_elo)
    svc = _build(["A", "B", "C", "D"], [opp])

    cards = _gen(svc, user_elo, ["A", "C"], seeds, confidence=None)

    def _find(give, recv):
        for c in cards:
            if c.give_player_ids == [give] and c.receive_player_ids == [recv]:
                return c
        return None

    balanced = _find("A", "B")
    lopsided = _find("C", "D")
    assert balanced is not None, "balanced candidate missing from v2 output"
    assert lopsided is not None, "lopsided candidate missing from v2 output"
    assert balanced.composite_score > lopsided.composite_score, (
        f"balanced trade (hm={balanced.mismatch_score}) should outrank "
        f"lopsided (hm={lopsided.mismatch_score})"
    )
    # mismatch_score carries the harmonic mean in v2 — sanity-check direction.
    assert balanced.mismatch_score > lopsided.mismatch_score


# ---------------------------------------------------------------------------
# 5. elo_to_value monotonicity + package_value_v2 algebra
# ---------------------------------------------------------------------------

def test_elo_to_value_monotone_and_package_v2():
    sweep = [elo_to_value(e) for e in range(1000, 2001, 25)]
    assert all(b > a for a, b in zip(sweep, sweep[1:])), (
        "elo_to_value is not strictly increasing"
    )
    # Reference point from the docstring: elo 1500 -> elo_value_base.
    assert elo_to_value(1500.0) == pytest.approx(1000.0)

    # Two-asset package: lesser asset is discounted, so total < plain sum.
    for a, b in ((3000.0, 1000.0), (1500.0, 600.0), (425.0, 100.0)):
        assert package_value_v2([a, b], max(a, b)) < a + b

    # Single asset valued at the trade max contributes exactly itself
    # (0.15 + 0.85 * 1**gamma == 1).
    for v in (100.0, 1000.0, 4262.5):
        assert package_value_v2([v], v) == pytest.approx(v, abs=0.05)

    # Harmonic mean basics (A1): zero when either side is non-positive.
    assert _harmonic_mean(300.0, 300.0) == pytest.approx(300.0)
    assert _harmonic_mean(800.0, 50.0) == pytest.approx(2 * 800 * 50 / 850)
    assert _harmonic_mean(-1.0, 500.0) == 0.0
    assert _harmonic_mean(0.0, 500.0) == 0.0


# ---------------------------------------------------------------------------
# 6. Waiver-slot cost charges the side receiving extra players
# ---------------------------------------------------------------------------

def test_waiver_slot_cost():
    """The same 1-for-2 candidate passes with waiver_slot_cost=0 and is
    gated with a huge cost — only the multi-receive shape is affected, the
    1-for-1 sibling survives. Mirror direction (opponent receives more)
    is checked on the 2-for-1 fixture."""
    _set_v2(True)
    user_elo = {"G": 1500, "R1": 1560, "R2": 1520}
    opp_elo = {"G": 1650, "R1": 1520, "R2": 1450}
    # Seeds chosen so BOTH the 1-for-1 (G<->R1, fairness ~0.80) and the
    # 1-for-2 (G<->R1+R2, fairness ~0.83) clear the 0.75 consensus gate.
    seeds = {"G": 1600, "R1": 1580, "R2": 1520}

    def _run():
        opp = _member("opp", ["R1", "R2"], dict(opp_elo))
        svc = _build(["G", "R1", "R2"], [opp])
        return _gen(svc, dict(user_elo), ["G"], dict(seeds), confidence=None)

    # User receives 2 for 1: with no waiver cost the 1-for-2 surfaces.
    ts._cfg["waiver_slot_cost"] = 0.0
    cards_free = _run()
    assert any(len(c.receive_player_ids) == 2 for c in cards_free), (
        "1-for-2 candidate missing even with waiver_slot_cost=0"
    )

    # With a prohibitive cost, the user-side received package is charged
    # below the surplus gate — the 1-for-2 vanishes, the 1-for-1 stays.
    ts._cfg["waiver_slot_cost"] = 10_000.0
    cards_taxed = _run()
    assert not any(len(c.receive_player_ids) == 2 for c in cards_taxed), (
        "1-for-2 survived a prohibitive waiver cost — receiving side not charged"
    )
    assert any(len(c.give_player_ids) == 1 and len(c.receive_player_ids) == 1
               for c in cards_taxed), (
        "1-for-1 sibling should be unaffected by the waiver cost"
    )

    # Mirror direction: in the 2-for-1 fixture the OPPONENT receives the
    # extra player, so a prohibitive cost kills that side's surplus too.
    svc, m_user_elo, m_roster, m_seeds = _multi_setup()
    cards_multi_taxed = _gen(svc, m_user_elo, m_roster, m_seeds, confidence=None)
    assert not any(len(c.give_player_ids) == 2 for c in cards_multi_taxed), (
        "2-for-1 survived a prohibitive waiver cost — giving side's opponent not charged"
    )


# ---------------------------------------------------------------------------
# 7. Confidence shrinkage
# ---------------------------------------------------------------------------

def test_confidence_shrinkage():
    user = {"p": 1800.0}
    seed = {"p": 1500.0}

    # confidence=None -> no information -> personal Elo untouched.
    assert _shrink_user_elo(user, seed, None) == {"p": 1800.0}

    # n=0 -> w=0 -> exactly the consensus seed.
    assert _shrink_user_elo(user, seed, {"p": 0})["p"] == pytest.approx(1500.0)

    # n=100 with pseudocount 4 -> w=100/104 -> ~personal (within ~12 Elo).
    near_personal = _shrink_user_elo(user, seed, {"p": 100})["p"]
    assert near_personal == pytest.approx(1800.0, abs=15.0)
    assert near_personal == pytest.approx(1800.0 * 100 / 104 + 1500.0 * 4 / 104)

    # Strictly monotone in n: more comparisons -> closer to personal.
    outs = [_shrink_user_elo(user, seed, {"p": n})["p"]
            for n in (0, 1, 2, 4, 8, 16, 64, 256)]
    assert all(b > a for a, b in zip(outs, outs[1:]))

    # Player missing from confidence dict counts as n=0.
    assert _shrink_user_elo(user, seed, {})["p"] == pytest.approx(1500.0)


# ---------------------------------------------------------------------------
# 8. Range-overlap fairness gate (A4)
# ---------------------------------------------------------------------------

def test_range_overlap_fairness():
    """Consensus point ratio ~0.713 sits just below the 0.75 threshold.
    With n=1 comparisons the value ranges (±0.35/sqrt(2) ≈ ±24.7%) overlap
    and the trade surfaces; with enormous n the ranges collapse to points
    and the same trade is gated out.

    User personal Elo == seed Elo so confidence-driven SHRINKAGE is a no-op
    in both runs — only the fairness gate differs between them."""
    _set_v2(True)
    # Pin the divergence floor so the 0.75 threshold governs — the
    # interview-2026-07-17 loosening (0.55) would pass this fixture's
    # 0.713 ratio even with point ranges, defeating the test's subject
    # (the range-overlap machinery).
    ts._cfg["fairness_floor_divergence"] = 1.0
    user_elo = {"G": 1500, "R": 1530}          # == seeds -> shrink no-op
    seeds = {"G": 1500, "R": 1530}
    opp_elo = {"G": 1650, "R": 1450}           # opp overvalues G, dumps R

    def _run(confidence):
        opp = _member("opp", ["R"], dict(opp_elo))
        svc = _build(["G", "R"], [opp])
        return _gen(svc, dict(user_elo), ["G"], dict(seeds),
                    confidence=confidence)

    loose = _run({"G": 1, "R": 1})
    assert len(loose) == 1, "wide uncertainty ranges should let the trade through"
    assert loose[0].fairness_score < 0.75, (
        "fixture broken: point fairness should sit below the threshold"
    )

    tight = _run({"G": 1_000_000, "R": 1_000_000})
    assert tight == [], (
        "tight ranges (huge comparison counts) should gate the same trade out"
    )


# ---------------------------------------------------------------------------
# 9. Bounded top-K heap returns the TRUE best, not the first-found
# ---------------------------------------------------------------------------

def _expected_v2_composite_1for1(g: str, r: str,
                                 user_elo: dict, opp_elo: dict) -> float | None:
    """Brute-force replica of the v2 1-for-1 composite for fixtures whose
    seeds are all equal (fairness == 1.0 and the overlap gate trivially
    passes) and whose Elo gaps are within trade_elo_gap_max."""
    vu_g, vu_r = elo_to_value(user_elo[g]), elo_to_value(user_elo[r])
    u_max = max(vu_g, vu_r)
    user_surplus = package_value_v2([vu_r], u_max) - package_value_v2([vu_g], u_max)

    vo_g, vo_r = elo_to_value(opp_elo[g]), elo_to_value(opp_elo[r])
    o_max = max(vo_g, vo_r)
    opp_surplus = package_value_v2([vo_g], o_max) - package_value_v2([vo_r], o_max)

    min_side = ts._cfg["min_side_surplus"]
    if user_surplus < min_side or opp_surplus < min_side:
        return None
    cap = ts._cfg["mutual_gain_cap"]
    hm = _harmonic_mean(user_surplus, opp_surplus)
    composite = (ts._cfg["mismatch_weight"] * min(hm, cap) / cap
                 + ts._cfg["fairness_weight"] * 1.0)
    # Tier multiplier on the user's Elo (no confidence -> no shrinkage).
    band = ts._cfg["tier_mult_bench"]
    for e in (user_elo[g], user_elo[r]):
        if e >= 1700:
            m = ts._cfg["tier_mult_elite"]
        elif e >= 1580:
            m = ts._cfg["tier_mult_starter"]
        elif e >= 1460:
            m = ts._cfg["tier_mult_solid"]
        elif e >= 1350:
            m = ts._cfg["tier_mult_depth"]
        else:
            m = ts._cfg["tier_mult_bench"]
        band = max(band, m)
    return composite * band


def test_top_k_true_best():
    """max_per_opponent=2 -> heap K=8, while 15 candidates pass the gates.
    The four best candidates all receive `rstar`, whose divergence
    (user_value - opp_value) is the SMALLEST on the opponent roster, so the
    anchor-first sort enumerates it LAST — a first-K engine would miss it.
    The bounded heap must still return it, sorted descending, matching the
    brute-force best."""
    _set_v2(True)
    gives = ["g1", "g2", "g3", "g4"]
    recvs = ["r1", "r2", "r3", "rstar"]
    user_elo = {"g1": 1520, "g2": 1530, "g3": 1540, "g4": 1550,
                "r1": 1560, "r2": 1570, "r3": 1565, "rstar": 1750}
    opp_elo = {"g1": 1800, "g2": 1790, "g3": 1780, "g4": 1770,
               "r1": 1400, "r2": 1410, "r3": 1405, "rstar": 1740}
    # Equal seeds: every 1-for-1 has fairness 1.0; every multi-player shape
    # is consensus-gated (2-pack vs 1 at equal seeds -> ratio 0.5 < 0.75),
    # so the candidate space is exactly the 4x4 1-for-1 grid.
    seeds = {p: 1500 for p in gives + recvs}

    # Fixture self-check: rstar must be the LAST recv in anchor order.
    div = {r: elo_to_value(user_elo[r]) - elo_to_value(opp_elo[r]) for r in recvs}
    assert min(div, key=div.get) == "rstar"

    opp = _member("opp", recvs, opp_elo)
    svc = _build(gives + recvs, [opp])
    cards = _gen(svc, dict(user_elo), gives, dict(seeds),
                 max_per_opponent=2, confidence=None)

    # Brute-force expectation over the full 1-for-1 grid.
    expected = {}
    for g in gives:
        for r in recvs:
            comp = _expected_v2_composite_1for1(g, r, user_elo, opp_elo)
            if comp is not None:
                expected[(g, r)] = comp
    assert len(expected) > 8, "fixture broken: need more passing candidates than K"
    best_composite = max(expected.values())

    assert len(cards) == 2
    composites = [c.composite_score for c in cards]
    assert composites == sorted(composites, reverse=True), "cards not sorted desc"
    for c in cards:
        assert c.receive_player_ids == ["rstar"], (
            f"top-K missed the late-enumerated best candidate: {_key(c)}"
        )
        assert c.composite_score == pytest.approx(best_composite, abs=1e-3)


# ---------------------------------------------------------------------------
# 10. Consensus-basis cards for unranked opponents
# ---------------------------------------------------------------------------

def test_consensus_basis_for_unranked():
    _set_v2(True)
    ids = ["u1", "u2", "a1", "b1", "b2"]
    user_roster = ["u1", "u2"]
    user_elo = {"u1": 1500, "u2": 1500, "a1": 1540}
    seeds = {"u1": 1500, "u2": 1500, "a1": 1500, "b1": 1500, "b2": 1480}
    ranked_elo = {"u1": 1540, "a1": 1500}      # mutual divergence with u1<->a1

    def _run(fabricated: dict[str, float]) -> list[TradeCard]:
        ranked = _member("ranked", ["a1"], dict(ranked_elo), has_rankings=True)
        unranked = _member("unranked", ["b1", "b2"], dict(fabricated),
                           has_rankings=False)
        svc = _build(ids, [ranked, unranked])
        return _gen(svc, dict(user_elo), list(user_roster), dict(seeds),
                    confidence=None)

    cards = _run({"b1": 1900, "b2": 1850})

    ranked_cards = [c for c in cards if c.target_user_id == "ranked"]
    unranked_cards = [c for c in cards if c.target_user_id == "unranked"]
    assert ranked_cards, "no divergence cards against the ranked opponent"
    assert unranked_cards, "no consensus cards against the unranked opponent"

    for c in ranked_cards:
        assert c.basis == "divergence"
    for c in unranked_cards:
        assert c.basis == "consensus"
        assert c.mismatch_score == 0.0
        assert c.fairness_score >= 0.75       # within the fairness threshold
        assert 0.0 <= c.fairness_score <= 1.0

    # Fabricated elo_ratings on an unranked member must NOT influence output:
    # wildly different fake elos -> byte-identical card set.
    cards_alt = _run({"b1": 1200, "b2": 1210})
    assert sorted(_key(c) for c in cards) == sorted(_key(c) for c in cards_alt), (
        "unranked opponent's fabricated elo_ratings leaked into the results"
    )


# ---------------------------------------------------------------------------
# 11. fairness_score field semantics in both paths
# ---------------------------------------------------------------------------

def test_fairness_score_field():
    # --- Legacy path: fairness in [0,1] even when tier multiplier != 1. ---
    _set_v2(False)
    # u1 elite in the user's eyes (1720 -> x1.6 tier mult), mismatch maxes
    # the 300-cap: composite = (0.7*1 + 0.3*1.0) * 1.6 = 1.6 > 1.
    user_elo = {"u1": 1720, "o1": 1700}
    opp_elo = {"u1": 1800, "o1": 1480}
    seeds = {"u1": 1500, "o1": 1500}
    opp = _member("opp", ["o1"], opp_elo)
    svc = _build(["u1", "o1"], [opp])
    legacy_cards = _gen(svc, user_elo, ["u1"], seeds)

    assert legacy_cards, "legacy fixture produced no cards"
    for c in legacy_cards:
        assert 0.0 <= c.fairness_score <= 1.0
    boosted = [c for c in legacy_cards if c.composite_score > 1.0]
    assert boosted, "expected a tier-boosted (>1.0) composite in legacy path"
    for c in boosted:
        # The old bug stored the composite in fairness_score; with tier
        # multiplier != 1 the two can never coincide if the fix holds.
        assert c.fairness_score != c.composite_score

    # --- v2 path: same invariants. ---
    _set_v2(True)
    svc2, m_user_elo, m_roster, m_seeds = _multi_setup()
    v2_cards = _gen(svc2, m_user_elo, m_roster, m_seeds, confidence=None)
    assert v2_cards, "v2 fixture produced no cards"
    for c in v2_cards:
        assert 0.0 <= c.fairness_score <= 1.0
    v2_boosted = [c for c in v2_cards if c.composite_score > 1.0]
    assert v2_boosted, "expected a tier-boosted (>1.0) composite in v2 path"
    for c in v2_boosted:
        assert c.fairness_score != c.composite_score
