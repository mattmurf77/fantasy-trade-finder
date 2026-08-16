"""Tests for the trade_gen.v2 staged generation pipeline
(backend/trade_gen_v2.py; matchmaking research item 2).

Covers, per the build spec:
  - flag gating: flag OFF never touches the new module; ON routes to it
  - stage 1: divergence-driven centerpiece selection + want/accept boards
  - gate a: roster feasibility (both sides)
  - gate b: dual-board ε-gain on each side's OWN board, with the
    consolidation discount catching a junk-stuffed package
  - gate c: consensus fairness band (width configurable)
  - completion-probability hook: EB shrinkage math + ordering effect
  - exposure shaping: per-counterparty cap + viable-suggestion floor
  - batch dedup rule
  - MESO variants: recipient-board equivalence + distinct shapes
  - two-sided rationale + per-suggestion health metrics
  - end-to-end fixture league (~12 teams) with a contender/rebuilder pair:
    the window-complementarity trade IS found; a dual-board-tempting but
    consensus-lopsided trade is NOT emitted

All fixtures deterministic, no RNG, no DB. Flags + config are snapshot /
restored per test (same pattern as test_trade_engine_v2.py).
"""

import math
from dataclasses import dataclass
from typing import Optional

import pytest

import backend.feature_flags as ff
import backend.trade_gen_v2 as gen2
import backend.trade_service as ts
from backend.trade_gen_v2 import (
    _Candidate,
    _dedup_batch,
    acceptance_prior,
    classify_package_shape,
    consolidated_value,
    generate_league_suggestions,
)
from backend.trade_service import (
    League,
    LeagueMember,
    TradeService,
    elo_to_value,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

@dataclass
class _Player:
    id: str
    name: str
    position: str = "RB"
    team: str = "TST"
    age: Optional[int] = 25
    ktc_value: Optional[int] = None


@pytest.fixture(autouse=True)
def _isolate_flags_and_cfg():
    old_flags = ff._flags_cache
    old_cfg = dict(ts._cfg)
    ff._flags_cache = dict(ff.DEFAULT_FLAGS)          # everything OFF
    ts._cfg.clear()
    ts._cfg.update(ts._DEFAULT_CFG)
    try:
        yield
    finally:
        ff._flags_cache = old_flags
        ts._cfg.clear()
        ts._cfg.update(old_cfg)


def _set_flags(**dotted):
    cache = dict(ff.DEFAULT_FLAGS)
    for key, val in dotted.items():
        cache[key.replace("__", ".")] = val
    ff._flags_cache = cache


def _gen2_on():
    _set_flags(**{"trade_gen__v2": True})


def _member(user_id, roster, elo, has_rankings=True):
    return LeagueMember(user_id=user_id, username=user_id, roster=roster,
                        elo_ratings=elo, has_rankings=has_rankings)


def _service(players, members):
    svc = TradeService(players=players)
    svc.add_league(League(league_id="L1", name="Test League",
                          platform="demo", members=members))
    return svc


def _base_positions(prefix):
    """A feasible 8-man skeleton: QB, RB×3, WR×3, TE."""
    return {
        f"{prefix}_qb": "QB",
        f"{prefix}_rb1": "RB", f"{prefix}_rb2": "RB", f"{prefix}_rb3": "RB",
        f"{prefix}_wr1": "WR", f"{prefix}_wr2": "WR", f"{prefix}_wr3": "WR",
        f"{prefix}_te": "TE",
    }


def _base_pair(user_extra_elo=None, opp_extra_elo=None, seed_extra=None):
    """The canonical divergence pair:

    user values opp's o_wr1 (elo 1700 vs opp's 1500); opp values user's
    u_rb1 (elo 1700 vs user's 1500); consensus rates both at 1600 →
    the clean 1-for-1 passes every gate.
    """
    pos = {**_base_positions("u"), **_base_positions("o")}
    players = {pid: _Player(id=pid, name=pid, position=p)
               for pid, p in pos.items()}
    user_roster = [p for p in pos if p.startswith("u_")]
    opp_roster = [p for p in pos if p.startswith("o_")]

    seed = {pid: 1500.0 for pid in pos}
    seed["o_wr1"] = 1600.0
    seed["u_rb1"] = 1600.0
    seed.update(seed_extra or {})

    user_elo = dict(seed)
    user_elo["o_wr1"] = 1700.0
    user_elo["u_rb1"] = 1500.0
    user_elo.update(user_extra_elo or {})

    opp_elo = dict(seed)
    opp_elo["u_rb1"] = 1700.0
    opp_elo["o_wr1"] = 1500.0
    opp_elo.update(opp_extra_elo or {})

    return players, user_roster, opp_roster, seed, user_elo, opp_elo


def _run(players, league_members, user_elo, user_roster, seed, **kw):
    return generate_league_suggestions(
        players=players,
        league=League(league_id="L1", name="T", platform="demo",
                      members=league_members),
        user_id="user",
        user_elo=user_elo,
        user_roster=user_roster,
        seed_elo=seed,
        confidence=None,
        **kw,
    )


# ---------------------------------------------------------------------------
# Unit math
# ---------------------------------------------------------------------------

def test_consolidated_value_discount_curve():
    # Single asset: raw value, never discounted.
    assert consolidated_value([3000.0]) == pytest.approx(3000.0)
    # Junk contributes ≈ floor·v (plus a tiny power term) — a stuffed
    # package moves far less than its naive sum.
    stuffed = consolidated_value([3000.0, 300.0, 300.0])
    assert stuffed < 3200.0                     # naive sum is 3600
    junk_contrib = stuffed - 3000.0
    assert junk_contrib < 2 * 300.0 * 0.25      # ≲ floor-ish contribution
    # Equal-value assets are not discounted against each other.
    assert consolidated_value([1000.0, 1000.0]) == pytest.approx(2000.0)
    # floor = 1.0 restores naive additivity (kill switch).
    ts._cfg["gen2_consol_floor"] = 1.0
    assert consolidated_value([3000.0, 300.0, 300.0]) == pytest.approx(3600.0)


def test_acceptance_prior_eb_shrinkage():
    # No data → exactly the global prior.
    assert acceptance_prior("u", None) == pytest.approx(0.5)
    assert acceptance_prior("u", {}) == pytest.approx(0.5)
    # (9 accepts / 10 responses) with m=10, p0=0.5 → (9+5)/(10+10) = 0.7
    assert acceptance_prior("u", {"u": (9, 10)}) == pytest.approx(0.7)
    # Thin data barely moves the prior.
    p = acceptance_prior("u", {"u": (1, 1)})
    assert 0.5 < p < 0.6
    # A serial decliner sinks below the prior but never to zero.
    p = acceptance_prior("u", {"u": (0, 10)})
    assert 0.0 < p < 0.5
    # accepts clamped to responses; malformed data can't exceed 1.0.
    assert acceptance_prior("u", {"u": (99, 10)}) <= 1.0


def test_classify_package_shape():
    players = {
        "pick1": _Player(id="pick1", name="2027 1st", position="PICK", age=None),
        "pick2": _Player(id="pick2", name="2028 1st", position="PICK", age=None),
        "young1": _Player(id="young1", name="y1", position="WR", age=22),
        "young2": _Player(id="young2", name="y2", position="WR", age=23),
        "vet": _Player(id="vet", name="v", position="RB", age=29),
    }
    val = lambda pid: 1000.0
    assert classify_package_shape(["vet"], players, val) == "consolidation"
    assert classify_package_shape(["pick1", "pick2"], players, val) == "pick_heavy"
    assert classify_package_shape(["young1", "young2"], players, val) == "youth_heavy"
    assert classify_package_shape(["vet", "young1"], players, val) == "balanced"


def test_dedup_batch_rule():
    def cand(score, cp, give, recv, opp="opp"):
        return _Candidate(
            opponent_id=opp, centerpiece=cp, give_ids=list(give),
            recv_ids=list(recv), user_gain=1.0, opp_gain=1.0, joint_gain=2.0,
            symmetry=1.0, split_ratio=0.5, fairness_ratio=1.0,
            band_position=0.0, accept_prior=0.5, score=score,
            give_val_opp=1000.0)
    c1 = cand(10.0, "X", ["a"], ["X"])
    c2 = cand(9.0, "X", ["b"], ["X"])          # same (opp, X, 1x1) bucket
    c3 = cand(8.0, "X", ["c", "d"], ["X"])     # 2x1 bucket, Jaccard 1/4 < 0.6
    c4 = cand(7.0, "Y", ["a"], ["Y"])          # different centerpiece
    c5 = cand(6.0, "X", ["a"], ["X"], opp="other")  # other counterparty OK
    c6 = cand(5.0, "X", ["a", "c"], ["X"])     # Jaccard vs c1 = 2/3 ≥ 0.6
    kept = _dedup_batch([c1, c2, c3, c4, c5, c6])
    assert c1 in kept and c3 in kept and c4 in kept and c5 in kept
    assert c2 not in kept
    assert c6 not in kept


# ---------------------------------------------------------------------------
# Flag gating
# ---------------------------------------------------------------------------

def test_flag_off_never_touches_new_module(monkeypatch):
    players, user_roster, _, seed, user_elo, opp_elo = _base_pair()
    opp = _member("opp", [p for p in players if p.startswith("o_")], opp_elo)
    svc = _service(players, [opp])

    def _boom(**kw):
        raise AssertionError("trade_gen_v2 called with flag OFF")
    monkeypatch.setattr(gen2, "generate_league_suggestions", _boom)

    _set_flags(**{"trade_engine__v2": True})   # ordinary v2 path
    cards = svc.generate_trades(
        user_id="user", user_elo=user_elo, user_roster=user_roster,
        league_id="L1", seed_elo=seed)
    assert all(getattr(c, "rationale", None) is None for c in cards)


def test_flag_on_routes_to_pipeline():
    players, user_roster, _, seed, user_elo, opp_elo = _base_pair()
    opp = _member("opp", [p for p in players if p.startswith("o_")], opp_elo)
    svc = _service(players, [opp])
    _gen2_on()
    cards = svc.generate_trades(
        user_id="user", user_elo=user_elo, user_roster=user_roster,
        league_id="L1", seed_elo=seed)
    assert cards, "pipeline should find the canonical divergence trade"
    assert all(c.basis == "divergence" for c in cards)
    assert all(c.rationale is not None for c in cards)


# ---------------------------------------------------------------------------
# Stage 1 — centerpiece selection + want/accept boards
# ---------------------------------------------------------------------------

def test_centerpiece_is_max_divergence_asset():
    players, user_roster, opp_roster, seed, user_elo, opp_elo = _base_pair()
    opp = _member("opp", opp_roster, opp_elo)
    cards, report = _run(players, [opp], user_elo, user_roster, seed)
    assert cards
    top = cards[0]
    assert "o_wr1" in top.receive_player_ids
    assert top.give_player_ids == ["u_rb1"]
    assert report.viable_by_opponent["opp"] >= 1


def test_not_interested_blocks_centerpiece():
    players, user_roster, opp_roster, seed, user_elo, opp_elo = _base_pair()
    opp = _member("opp", opp_roster, opp_elo)
    cards, _ = _run(players, [opp], user_elo, user_roster, seed,
                    not_interested_ids={"o_wr1"})
    assert all("o_wr1" not in c.receive_player_ids for c in cards)
    # o_wr1 was the only divergent asset → nothing left to suggest.
    assert cards == []


def test_untouchable_never_leaves_roster():
    players, user_roster, opp_roster, seed, user_elo, opp_elo = _base_pair()
    opp = _member("opp", opp_roster, opp_elo)
    cards, _ = _run(players, [opp], user_elo, user_roster, seed,
                    untouchable_ids={"u_rb1"})
    assert all("u_rb1" not in c.give_player_ids for c in cards)


def test_unranked_opponent_skipped():
    players, user_roster, opp_roster, seed, user_elo, opp_elo = _base_pair()
    opp = _member("opp", opp_roster, opp_elo, has_rankings=False)
    cards, report = _run(players, [opp], user_elo, user_roster, seed)
    assert cards == []
    assert report.unranked_opponents == ["opp"]


# ---------------------------------------------------------------------------
# Gate a — roster feasibility
# ---------------------------------------------------------------------------

def test_feasibility_gate_blocks_lineup_breaking_trades():
    # User has exactly 2 RBs (the minimum) — sending u_rb1 for a WR must
    # be vetoed even though the boards love the swap.
    players, user_roster, opp_roster, seed, user_elo, opp_elo = _base_pair()
    user_roster = [p for p in user_roster if p != "u_rb3"]
    del players["u_rb3"]
    opp = _member("opp", opp_roster, opp_elo)
    cards, report = _run(players, [opp], user_elo, user_roster, seed)
    for c in cards:
        gives_rb = any(players[p].position == "RB" for p in c.give_player_ids)
        gets_rb = any(players[p].position == "RB"
                      for p in c.receive_player_ids)
        assert not (gives_rb and not gets_rb), \
            "emitted a trade that leaves the user unable to start 2 RBs"
    assert report.feasibility_rejects > 0


# ---------------------------------------------------------------------------
# Gate b — dual-board ε-gain
# ---------------------------------------------------------------------------

def test_dual_board_epsilon_requires_both_sides_gain():
    # Opponent's board does NOT prefer what they'd receive → no card, even
    # though the user's side gains plenty.
    players, user_roster, opp_roster, seed, user_elo, opp_elo = _base_pair(
        opp_extra_elo={"u_rb1": 1500.0})       # opp indifferent now
    opp = _member("opp", opp_roster, opp_elo)
    cards, report = _run(players, [opp], user_elo, user_roster, seed)
    assert cards == []
    assert report.ir_rejects > 0


def test_epsilon_is_tunable():
    players, user_roster, opp_roster, seed, user_elo, opp_elo = _base_pair()
    opp = _member("opp", opp_roster, opp_elo)
    # The canonical trade's per-side gain is ≈ 1718 value units; an ε above
    # that must gate it out.
    ts._cfg["gen2_epsilon"] = 2000.0
    cards, _ = _run(players, [opp], user_elo, user_roster, seed)
    assert cards == []


def test_consolidation_discount_blocks_junk_stuffing():
    """A stud priced at ~3400 consensus cannot be bought with mid+junk+junk
    whose NAIVE sum is ~3400 — the discount collapses the junk, the band
    rejects. Restoring additivity (floor=1.0) lets the junk package
    through, proving the discount is what catches it."""
    pos = {**_base_positions("u"), **_base_positions("o")}
    players = {pid: _Player(id=pid, name=pid, position=p)
               for pid, p in pos.items()}
    user_roster = [p for p in pos if p.startswith("u_")]
    opp_roster = [p for p in pos if p.startswith("o_")]

    stud, mid, j1, j2 = "o_wr1", "u_wr1", "u_wr2", "u_wr3"
    # Consensus: stud ≈ 3403, mid ≈ 2600, junk ≈ 400 each → naive sum of
    # the give side ≈ 3400 ("fair" if packages were additive).
    seed = {pid: 1500.0 for pid in pos}
    seed[stud] = 1745.0
    seed[mid] = 1691.0
    seed[j1] = seed[j2] = 1317.0

    user_elo = dict(seed)
    user_elo[stud] = 1780.0     # user covets the stud
    user_elo[mid] = 1600.0
    user_elo[j1] = user_elo[j2] = 1200.0

    opp_elo = dict(seed)
    opp_elo[stud] = 1500.0      # opp is out on their own stud
    opp_elo[mid] = 1650.0       # and likes the user's pieces
    opp_elo[j1] = opp_elo[j2] = 1400.0

    # User needs 3+ WRs to legally send three – pad the roster.
    for extra in ("u_wr4", "u_wr5", "u_wr6"):
        players[extra] = _Player(id=extra, name=extra, position="WR")
        user_roster.append(extra)
        seed[extra] = 1400.0
        user_elo[extra] = 1400.0
        opp_elo[extra] = 1400.0

    opp = _member("opp", opp_roster, opp_elo)

    def _stuffed(card):
        # The exploit shape: BOTH junk bodies padding the give side so the
        # naive sum reaches the stud's price.
        return j1 in card.give_player_ids and j2 in card.give_player_ids

    cards, report = _run(players, [opp], user_elo, user_roster, seed)
    assert all(not _stuffed(c) for c in cards), \
        "junk-stuffed package leaked through"
    assert report.band_rejects > 0

    # Kill the discount (floor = 1.0 restores naive additivity) → the
    # junk-stuffed package's naive sum ≈ the stud's consensus price, so it
    # becomes "fair" and surfaces. This is the exploit the curve closes.
    ts._cfg["gen2_consol_floor"] = 1.0
    cards2, _ = _run(players, [opp], user_elo, user_roster, seed)
    assert any(_stuffed(c) for c in cards2)


# ---------------------------------------------------------------------------
# Gate c — consensus fairness band
# ---------------------------------------------------------------------------

def test_fairness_band_rejects_lopsided_consensus():
    # Boards both love the swap, but consensus says the user receives ~2x
    # what they give → defensibility veto.
    players, user_roster, opp_roster, seed, user_elo, opp_elo = _base_pair(
        seed_extra={"o_wr1": 1740.0, "u_rb1": 1600.0})
    # keep the boards divergent enough that gate b still passes
    user_elo["o_wr1"] = 1840.0
    opp_elo["o_wr1"] = 1600.0
    cards, report = _run(players,
                         [_member("opp", opp_roster, opp_elo)],
                         user_elo, user_roster, seed)
    assert all(not (c.give_player_ids == ["u_rb1"]
                    and c.receive_player_ids == ["o_wr1"]) for c in cards)
    assert report.band_rejects > 0

    # Widening the band (config) admits the same trade.
    ts._cfg["gen2_band"] = 0.60
    cards2, _ = _run(players,
                     [_member("opp", opp_roster, opp_elo)],
                     user_elo, user_roster, seed)
    assert any("o_wr1" in c.receive_player_ids for c in cards2)


# ---------------------------------------------------------------------------
# Completion-probability hook
# ---------------------------------------------------------------------------

def test_acceptance_prior_reorders_identical_opponents():
    players_a, user_roster, opp_roster_a, seed_a, user_elo_a, opp_elo_a = \
        _base_pair()
    # Clone the opponent under a second id with an identical board/roster.
    players = dict(players_a)
    for pid, pos in _base_positions("p").items():
        players[pid] = _Player(id=pid, name=pid, position=pos)
    opp_b_roster = [p for p in players if p.startswith("p_")]
    seed = dict(seed_a)
    user_elo = dict(user_elo_a)
    opp_b_elo = {}
    for pid in list(players):
        seed.setdefault(pid, 1500.0)
    seed["p_wr1"] = 1600.0
    user_elo["p_wr1"] = 1700.0
    for pid in players:
        opp_b_elo[pid] = seed[pid]
    opp_b_elo["u_rb1"] = 1700.0
    opp_b_elo["p_wr1"] = 1500.0
    opp_a_elo = {pid: seed[pid] for pid in players}
    opp_a_elo["u_rb1"] = 1700.0
    opp_a_elo["o_wr1"] = 1500.0
    user_elo.setdefault("o_wr1", 1700.0)

    opp_a = _member("oppA", opp_roster_a, opp_a_elo)
    opp_b = _member("oppB", opp_b_roster, opp_b_elo)

    # oppB is a serial non-responder → their (identical-gain) card must
    # rank below oppA's.
    cards, _ = _run(players, [opp_a, opp_b], user_elo, user_roster, seed,
                    acceptance_stats={"oppB": (0, 10)})
    assert cards
    assert cards[0].target_user_id == "oppA"
    b_health = [c.health for c in cards if c.target_user_id == "oppB"]
    assert b_health and b_health[0]["accept_prior"] < 0.5


# ---------------------------------------------------------------------------
# Exposure shaping
# ---------------------------------------------------------------------------

def _three_opponent_league():
    """User + three opponents, each with the canonical divergence trade
    available; opponent gain magnitudes A > B > C."""
    players = {pid: _Player(id=pid, name=pid, position=p)
               for pid, p in _base_positions("u").items()}
    user_roster = list(players)
    seed = {pid: 1500.0 for pid in players}
    user_elo = dict(seed)
    members = []
    # give the user three divergent RBs so each pair has its own give
    for rb, (tag, opp_elo_bump) in zip(
            ("u_rb1", "u_rb2", "u_rb3"),
            (("A", 1700.0), ("B", 1680.0), ("C", 1660.0))):
        prefix = f"t{tag}"
        for pid, pos in _base_positions(prefix).items():
            players[pid] = _Player(id=pid, name=pid, position=pos)
            seed[pid] = 1500.0
        cp = f"{prefix}_wr1"
        seed[cp] = 1600.0
        seed[rb] = 1600.0
        user_elo[cp] = 1700.0
        user_elo.setdefault(rb, 1500.0)
        roster = [p for p in players if p.startswith(prefix + "_")]
        opp_elo = {pid: seed.get(pid, 1500.0) for pid in players}
        opp_elo[rb] = opp_elo_bump
        opp_elo[cp] = 1500.0
        members.append(_member(f"opp{tag}", roster, opp_elo))
    # seed entries for late-added players
    for pid in players:
        seed.setdefault(pid, 1500.0)
        user_elo.setdefault(pid, seed[pid])
    return players, user_roster, seed, user_elo, members


def test_exposure_cap_and_floor_shape_the_head_without_truncation():
    """Operator decision 2026-08-16: the cap/floor pass ORDERS (who gets
    the head of the list), it never drops. Full survivor set ships."""
    players, user_roster, seed, user_elo, members = _three_opponent_league()
    ts._cfg["gen2_exposure_cap"] = 1.0
    cards, report = _run(players, members, user_elo, user_roster, seed)

    # No truncation: every post-dedup survivor is emitted.
    assert len(cards) == sum(report.viable_by_opponent.values())

    # Head shaping: with cap=1 the shaped head is one card per viable
    # counterparty, so the first N cards have N distinct counterparties.
    n_viable = sum(1 for v in report.viable_by_opponent.values() if v)
    head_targets = [c.target_user_id for c in cards[:n_viable]]
    assert len(set(head_targets)) == n_viable
    assert all(n <= 1 for n in report.shaped_head_by_opponent.values())

    # Floor: every opponent with a viable suggestion appears in the head.
    for uid, viable in report.viable_by_opponent.items():
        if viable:
            assert report.shaped_head_by_opponent.get(uid, 0) >= 1, \
                f"{uid} starved despite viable"

    # Full-emission exposure counts are logged too.
    per_opp = {}
    for c in cards:
        per_opp[c.target_user_id] = per_opp.get(c.target_user_id, 0) + 1
    assert report.exposure_by_opponent == per_opp


def test_uncapped_default_returns_all_survivors():
    """max_per_opponent defaults to None ⇒ the engine emits the FULL
    ranked survivor set; an int is a caller-passed presentation limit."""
    # Base pair extended with a SECOND divergent centerpiece + return, so
    # the pair has multiple post-dedup survivors.
    players, user_roster, opp_roster, seed, user_elo, opp_elo = _base_pair(
        seed_extra={"o_wr2": 1600.0, "u_rb2": 1600.0},
        user_extra_elo={"o_wr2": 1690.0, "u_rb2": 1500.0},
        opp_extra_elo={"o_wr2": 1500.0, "u_rb2": 1690.0})
    opp = _member("opp", opp_roster, opp_elo)

    cards, report = _run(players, [opp], user_elo, user_roster, seed)
    assert len(cards) == report.viable_by_opponent["opp"]
    assert len(cards) >= 2          # more than one survivor actually ships
    centerpieces = {c.receive_player_ids[0] for c in cards}
    assert {"o_wr1", "o_wr2"} <= centerpieces

    # A caller-passed limit still truncates per pair (presentation only).
    capped, _ = _run(players, [opp], user_elo, user_roster, seed,
                     max_per_opponent=1)
    assert len(capped) == 1

    # And across a league, uncapped output equals total viable survivors.
    players3, user_roster3, seed3, user_elo3, members3 = \
        _three_opponent_league()
    cards3, report3 = _run(players3, members3, user_elo3, user_roster3,
                           seed3)
    assert len(cards3) == sum(report3.viable_by_opponent.values())


def test_tier_metadata():
    players, user_roster, seed, user_elo, members = _three_opponent_league()
    cards, _ = _run(players, members, user_elo, user_roster, seed)
    assert cards
    featured_n = int(ts._c("gen2_featured_count"))

    # Exactly one endorsed per generation cycle, and it is the top card.
    assert cards[0].tier == "endorsed"
    assert sum(1 for c in cards if c.tier == "endorsed") == 1

    # Featured = the next gen2_featured_count by final rank; browse = rest.
    for i, c in enumerate(cards):
        expected = ("endorsed" if i == 0
                    else "featured" if i <= featured_n
                    else "browse")
        assert c.tier == expected, (i, c.tier)

    # Tier ordering is consistent with rank: never a featured after a
    # browse, never an endorsed after anything.
    order = {"endorsed": 0, "featured": 1, "browse": 2}
    ranks = [order[c.tier] for c in cards]
    assert ranks == sorted(ranks)


def test_exposure_counts_logged_in_report():
    players, user_roster, seed, user_elo, members = _three_opponent_league()
    cards, report = _run(players, members, user_elo, user_roster, seed)
    assert set(report.exposure_by_opponent) <= {"oppA", "oppB", "oppC"}
    assert sum(report.exposure_by_opponent.values()) == len(cards)
    assert sum(report.shaped_head_by_opponent.values()) <= len(cards)
    assert 0.0 <= report.ir_rate <= 1.0


# ---------------------------------------------------------------------------
# MESO variants
# ---------------------------------------------------------------------------

def test_meso_variants_equivalent_on_recipient_board():
    pos = {**_base_positions("u"), **_base_positions("o")}
    players = {pid: _Player(id=pid, name=pid, position=p, age=27)
               for pid, p in pos.items()}
    user_roster = [p for p in pos if p.startswith("u_")]
    opp_roster = [p for p in pos if p.startswith("o_")]

    # Extra user assets: two young WRs, two picks — plus u_rb1 as the
    # consolidation piece.
    for pid, p, age in (("u_y1", "WR", 22), ("u_y2", "WR", 22),
                        ("u_pk1", "PICK", None), ("u_pk2", "PICK", None)):
        players[pid] = _Player(id=pid, name=pid, position=p, age=age)
        user_roster.append(pid)

    X, C, Y1, Y2, P1, P2 = "o_wr1", "u_rb1", "u_y1", "u_y2", "u_pk1", "u_pk2"

    seed = {pid: 1500.0 for pid in players}
    seed[X] = 1650.0                    # cval ≈ 2117
    seed[C] = 1650.0                    # consensus-equal 1-for-1
    for pid in (Y1, Y2, P1, P2):
        seed[pid] = 1512.0              # duo cval ≈ 2124 → inside the band

    user_elo = dict(seed)
    user_elo[X] = 1750.0                # user covets X (uval ≈ 3490)
    user_elo[C] = 1580.0
    for pid in (Y1, Y2, P1, P2):
        user_elo[pid] = 1450.0

    opp_elo = dict(seed)
    opp_elo[X] = 1500.0                 # oval(X) = 1000
    opp_elo[C] = 1700.0                 # oval ≈ 2718
    for pid in (Y1, Y2, P1, P2):
        opp_elo[pid] = 1560.0           # duo oval ≈ 2700 → within ±5% of C

    opp = _member("opp", opp_roster, opp_elo)
    cards, _ = _run(players, [opp], user_elo, user_roster, seed)
    assert cards
    top = cards[0]
    assert top.receive_player_ids == [X]
    assert top.meso_variants, "top card should carry MESO variants"
    assert len(top.meso_variants) <= 3
    shapes = [v["shape"] for v in top.meso_variants]
    assert len(shapes) == len(set(shapes)), "variant shapes must differ"
    assert {"youth_heavy", "pick_heavy"} & set(shapes)
    meso_band_pct = ts._c("gen2_meso_band") * 100.0
    for v in top.meso_variants:
        assert abs(v["recipient_value_delta_pct"]) <= meso_band_pct + 1e-6
        assert v["give_player_ids"] != top.give_player_ids
    # Non-top cards never carry variants.
    assert all(c.meso_variants is None for c in cards[1:])


# ---------------------------------------------------------------------------
# Rationale + health
# ---------------------------------------------------------------------------

def test_two_sided_rationale_and_health():
    players, user_roster, opp_roster, seed, user_elo, opp_elo = _base_pair()
    opp = _member("opp", opp_roster, opp_elo)
    cards, _ = _run(players, [opp], user_elo, user_roster, seed)
    assert cards
    r = cards[0].rationale
    # Both sides present, each in its OWN board's terms — no winner score.
    assert set(r) == {"user", "counterparty"}
    assert r["user"]["own_board_gain"] > 0
    assert r["counterparty"]["own_board_gain"] > 0
    assert r["user"]["board"] == "personal"
    assert r["user"]["centerpiece"]["id"] == "o_wr1"
    assert "why_yes" in r["counterparty"]
    assert r["counterparty"]["why_yes"]["values_return_above_cost"] is True
    assert r["counterparty"]["timeline"]["value"] is not None

    h = cards[0].health
    eps = ts._c("gen2_epsilon")
    assert h["joint_gain"] > 0
    assert 0.0 < h["split_ratio"] < 1.0
    assert h["ir_margin_user"] >= 0 and h["ir_margin_opp"] >= 0
    assert -1.0 <= h["band_position"] <= 1.0
    assert 0.0 < h["symmetry"] <= 1.0
    assert h["ir_margin_user"] == pytest.approx(
        h["joint_gain"] * h["split_ratio"] - eps, abs=1.0)


# ---------------------------------------------------------------------------
# End-to-end fixture league (contender / rebuilder)
# ---------------------------------------------------------------------------

def _fixture_league():
    """12 teams. Team 0 = the user, a CONTENDER whose board pays up for a
    proven vet RB. Team 1 = a REBUILDER whose board pays up for youth.
    Teams 2-11 have flat (consensus) boards. Team 2 additionally sets a
    dual-board TRAP: it wildly overvalues one of the user's bench bodies,
    which would make a consensus-lopsided trade look board-positive for
    both sides — the fairness band must refuse it."""
    players: dict = {}
    seed: dict = {}
    rosters: dict[int, list[str]] = {}
    for t in range(12):
        prefix = f"t{t}"
        roster = []
        for pid, pos in _base_positions(prefix).items():
            age = 22 + (hash(pid) % 8)          # deterministic per name
            players[pid] = _Player(id=pid, name=pid, position=pos, age=age)
            seed[pid] = 1450.0 + (t % 4) * 25.0
            roster.append(pid)
        rosters[t] = roster

    user_roster = rosters[0]

    # The window-complementarity pair: the user's young stud WR vs the
    # rebuilder's proven vet RB — same consensus value, opposite boards.
    young = "t0_wr1"; vet = "t1_rb1"
    players[young] = _Player(id=young, name="Young Stud", position="WR", age=22)
    players[vet] = _Player(id=vet, name="Proven Vet", position="RB", age=28)
    seed[young] = 1700.0
    seed[vet] = 1700.0

    # Trap assets for team 2.
    bench = "t0_te"                              # user's TE body
    t2_asset = "t2_wr1"
    seed[t2_asset] = 1750.0                      # a genuinely premium asset

    # User board: full consensus + contender lean.
    user_elo = dict(seed)
    user_elo[vet] = 1780.0                       # pays up for proven now
    user_elo[young] = 1620.0                     # will move the young piece
    user_elo[t2_asset] = 1800.0                  # covets the trap asset too

    members = []
    for t in range(1, 12):
        elo = dict(seed)
        if t == 1:                               # the rebuilder
            elo[young] = 1780.0
            elo[vet] = 1620.0
        if t == 2:                               # the trap
            elo[bench] = 1800.0                  # irrationally loves a body
            elo[t2_asset] = 1500.0               # cold on their own stud
        members.append(_member(f"team{t}", rosters[t], elo))
    return players, user_roster, seed, user_elo, members, young, vet, \
        bench, t2_asset


def test_fixture_league_finds_window_trade_and_refuses_lopsided():
    (players, user_roster, seed, user_elo, members,
     young, vet, bench, t2_asset) = _fixture_league()
    cards, report = _run(players, members, user_elo, user_roster, seed)
    assert cards, "the fixture league has an obvious mutual-gain trade"

    # 1. The contender/rebuilder window trade IS found.
    window = [c for c in cards
              if c.target_user_id == "team1"
              and young in c.give_player_ids
              and vet in c.receive_player_ids]
    assert window, "engine missed the window-complementarity trade"

    # 2. The consensus-lopsided trap trade is NOT emitted, even though both
    #    boards would call it a win (bench body ≈ 779 consensus for a
    #    ≈ 3490-consensus stud).
    assert all(not (bench in c.give_player_ids
                    and t2_asset in c.receive_player_ids) for c in cards), \
        "emitted a league-indefensible (lopsided-consensus) trade"

    # 3. Nothing lopsided anywhere: every card clears both IR margins and
    #    sits inside the consensus band.
    band = ts._c("gen2_band")
    for c in cards:
        assert c.health["ir_margin_user"] >= 0
        assert c.health["ir_margin_opp"] >= 0
        assert c.health["fairness_ratio"] >= 1.0 - band - 1e-9
        assert -1.0 <= c.health["band_position"] <= 1.0

    # 4. Rationale is two-sided on every card.
    for c in cards:
        assert c.rationale["user"]["own_board_gain"] > 0
        assert c.rationale["counterparty"]["own_board_gain"] > 0

    # 5. Exposure telemetry is complete, and nothing was truncated.
    assert sum(report.exposure_by_opponent.values()) == len(cards)
    assert len(cards) == sum(report.viable_by_opponent.values())

    # 6. Tier metadata on every card, exactly one endorsed.
    assert all(c.tier in ("endorsed", "featured", "browse") for c in cards)
    assert sum(1 for c in cards if c.tier == "endorsed") == 1
    assert cards[0].tier == "endorsed"


def test_fixture_league_through_trade_service_flag_on():
    """Same fixture, driven through TradeService.generate_trades with the
    flag ON — proves the integration branch wires every kwarg through."""
    (players, user_roster, seed, user_elo, members,
     young, vet, bench, t2_asset) = _fixture_league()
    svc = _service(players, members)
    _gen2_on()
    cards = svc.generate_trades(
        user_id="user", user_elo=user_elo, user_roster=user_roster,
        league_id="L1", seed_elo=seed)
    assert cards
    assert any(c.target_user_id == "team1" and vet in c.receive_player_ids
               for c in cards)
    assert all(not (bench in c.give_player_ids
                    and t2_asset in c.receive_player_ids) for c in cards)
    # Tier metadata survives the TradeService integration path.
    assert cards[0].tier == "endorsed"
    assert sum(1 for c in cards if c.tier == "endorsed") == 1
    # Cards are stored for later decision recording, like every other path.
    assert all(svc._trade_cards.get(c.trade_id) is c for c in cards)
