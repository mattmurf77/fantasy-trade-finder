"""2026-08-21 gap auto-sweetener (`sweetener_gap_threshold`) — behaviour pins.

Operator-commissioned companion to the cross-package benchmark fix: the
fairness ratio gate is scale-blind, so a "fair" 0.80 card on a five-figure
package still leaves more than a late 1st (1539 value units) of absolute
consensus gap on the table (living-memory/CHANGELOG.md 2026-08-21 — 15% of
served cards carried gap > a late 1st). At generation time, per arm, each
path now tries to close such gaps by ADDING the smallest sufficient
equalizer asset from the RICHER side's roster; a card it cannot close is
kept unsweetened (the pass narrows gaps, never shrinks the deck).

Covered here:
  * helper unit (trade_optimizer.close_value_gap): direction, smallest-
    sufficient selection, untouchable/not-interested exclusion, band and
    feasibility re-checks, None when unclosable;
  * consensus path (_generate_consensus_for_pair): a big-gap card is
    emitted sweetened — attribute + gap_after ≤ threshold — and the
    SABOTAGE half: knob at 0 ⇒ the same card reappears unsweetened with
    its full gap (the deploy-free disable, and arm A's pin);
  * v3 optimizer path: same on/off contract through
    generate_pair_trades_v3;
  * TradeCard default: gap_sweetener is None on untouched cards.

All fixtures are literals (golden hygiene); flags/_cfg snapshot-restored.
"""

import math
from dataclasses import dataclass
from typing import Optional

import pytest

import backend.feature_flags as ff
import backend.trade_service as ts
from backend.trade_optimizer import close_value_gap, generate_pair_trades_v3
from backend.trade_service import (
    League,
    LeagueMember,
    TradeService,
    elo_to_value,
)


@dataclass
class _Player:
    id: str
    name: str
    position: str = "WR"
    team: str = "TST"
    age: int = 25
    ktc_value: Optional[int] = None


@pytest.fixture(autouse=True)
def _isolate():
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


def _set_flags(**kw):
    cache = dict(ff.DEFAULT_FLAGS)
    cache.update(kw)
    ff._flags_cache = cache


def _elo_for_value(value: float) -> float:
    """Inverse of elo_to_value at the default curve (k=0.005, ref 1500)."""
    return 1500.0 + math.log(value / 1000.0) / 0.005


# A lineup-feasible base: 1 QB, 2 RB, 2 WR, 1 TE (1qb starter needs), at a
# value low enough (200) to never be selected as an equalizer over the
# purpose-built candidates, but the fill bodies are also EXCLUDED from
# equalizer duty by the #141 floors, so they never muddy the selection.
_BASE_POS = {"q0": "QB", "b1": "RB", "b2": "RB",
             "w1": "WR", "w2": "WR", "t0": "TE"}


def _bodies(prefix):
    return {f"{prefix}_{k}": pos for k, pos in _BASE_POS.items()}


# ── helper unit ────────────────────────────────────────────────────────────

def _mini_league():
    """User gives G (5400) for opponent's R (7000): fairness 0.771 (in the
    0.75 band), gap 1600 > 1539. User is the richer side. Equalizers on the
    user's roster: X1 (1500, sufficient), X2 (600, too small to close), and
    the fill bodies (200, below the #141 absolute floor)."""
    values = {"G": 5400.0, "R": 7000.0, "X1": 1500.0, "X2": 600.0}
    spec = {pid: "WR" for pid in values}
    for pid, pos in {**_bodies("u"), **_bodies("o")}.items():
        spec[pid] = pos
        values[pid] = 200.0
    players = {pid: _Player(id=pid, name=pid, position=pos)
               for pid, pos in spec.items()}
    user_roster = ["G", "X1", "X2"] + list(_bodies("u"))
    opp_roster = ["R"] + list(_bodies("o"))
    seed_value = lambda pid: values[pid]                     # noqa: E731
    return players, user_roster, opp_roster, seed_value, values


def test_helper_adds_smallest_sufficient_equalizer_from_richer_side():
    players, user_roster, opp_roster, sv, values = _mini_league()
    out = close_value_gap(["G"], ["R"], seed_value=sv, gap_threshold=1539.0,
                          fairness_threshold=0.75, user_roster=user_roster,
                          opp_roster=opp_roster, players=players)
    assert out is not None
    s_pid, side, new_give, new_recv, gv, rv, ratio, partial = out
    assert partial is False               # a full close, not best-effort
    # User receives more (7000 > 5400) → the USER pays the equalizer.
    assert side == "give"
    # X2 (600) is tried first (cheapest) but cannot close a 1600 gap under
    # the depth discount; X1 is the smallest sufficient one.
    assert s_pid == "X1"
    assert sorted(new_give) == ["G", "X1"] and new_recv == ["R"]
    assert abs(gv - rv) <= 1539.0
    assert ratio >= 0.75


def test_helper_direction_flips_with_the_gap():
    players, user_roster, opp_roster, sv, values = _mini_league()
    # Mirror the trade: user gives R, receives G — now the OPPONENT is the
    # richer side and the equalizer must come off their roster. Give them
    # a sufficient piece first.
    values["Y1"] = 1500.0
    players["Y1"] = _Player(id="Y1", name="Y1", position="WR")
    out = close_value_gap(["R"], ["G"], seed_value=sv, gap_threshold=1539.0,
                          fairness_threshold=0.75, user_roster=opp_roster,
                          opp_roster=user_roster + ["Y1"], players=players)
    assert out is not None
    s_pid, side, new_give, new_recv, gv, rv, _ratio, _partial = out
    assert side == "receive"
    assert s_pid in ("X1", "Y1")          # cheapest sufficient wins
    assert abs(gv - rv) <= 1539.0


def test_helper_returns_none_below_threshold_and_when_unclosable():
    players, user_roster, opp_roster, sv, values = _mini_league()
    # Below threshold: nothing to do.
    values2 = dict(values, G=6500.0)      # gap 500
    sv2 = lambda pid: values2[pid]                            # noqa: E731
    assert close_value_gap(["G"], ["R"], seed_value=sv2, gap_threshold=1539.0,
                           fairness_threshold=0.75, user_roster=user_roster,
                           opp_roster=opp_roster, players=players) is None
    # Unclosable: no sufficient equalizer on the richer roster.
    assert close_value_gap(["G"], ["R"], seed_value=sv, gap_threshold=1539.0,
                           fairness_threshold=0.75,
                           user_roster=["G", "X2"] + list(_bodies("u")),
                           opp_roster=opp_roster, players=players) is None


def test_helper_never_sweetens_with_an_untouchable():
    players, user_roster, opp_roster, sv, _values = _mini_league()
    out = close_value_gap(["G"], ["R"], seed_value=sv, gap_threshold=1539.0,
                          fairness_threshold=0.75, user_roster=user_roster,
                          opp_roster=opp_roster, players=players,
                          untouchable_ids={"X1"})
    assert out is None                    # X1 was the only sufficient piece


def test_helper_respects_extra_gates():
    players, user_roster, opp_roster, sv, _values = _mini_league()
    out = close_value_gap(["G"], ["R"], seed_value=sv, gap_threshold=1539.0,
                          fairness_threshold=0.75, user_roster=user_roster,
                          opp_roster=opp_roster, players=players,
                          extra_ok_fn=lambda g, r: False)
    assert out is None


def test_tradecard_default_is_unsweetened():
    from backend.trade_service import TradeCard
    card = TradeCard(trade_id="t", league_id="L", proposing_user_id="u",
                     target_user_id="o", target_username="o",
                     give_player_ids=["a"], receive_player_ids=["b"],
                     mismatch_score=0.0, fairness_score=1.0,
                     composite_score=1.0)
    assert card.gap_sweetener is None


# ── consensus path: sweeten on, sabotage off ──────────────────────────────

def _consensus_league():
    """Opponent with NO rankings → consensus path. Elos chosen so the
    1-for-1 G→R card passes the 0.75 band with gap > 1539, and the user's
    X1 clears the #141 filler bars as an equalizer (X1 ≥ 0.25 × G's value
    and ≥ asset_floor_abs)."""
    elos = {
        "G":  _elo_for_value(5400.0),
        "R":  _elo_for_value(7000.0),
        "X1": _elo_for_value(1500.0),
        "X2": _elo_for_value(600.0),
    }
    spec = {pid: "WR" for pid in elos}
    for pid, pos in {**_bodies("u"), **_bodies("o")}.items():
        spec[pid] = pos
        elos[pid] = _elo_for_value(200.0)
    players = {pid: _Player(id=pid, name=pid, position=pos)
               for pid, pos in spec.items()}
    user_roster = ["G", "X1", "X2"] + list(_bodies("u"))
    opp_roster = ["R"] + list(_bodies("o"))
    opp = LeagueMember(user_id="opp", username="opp", roster=opp_roster,
                       elo_ratings={}, has_rankings=False)
    svc = TradeService(players=players)
    svc.add_league(League(league_id="L1", name="T", platform="demo",
                          members=[opp]))
    return svc, elos, user_roster


def _consensus_cards(svc, elos, user_roster):
    _set_flags(**{"trade_engine.v2": True})
    return svc.generate_trades(
        user_id="user", user_elo=dict(elos), user_roster=user_roster,
        league_id="L1", seed_elo=dict(elos), fairness_threshold=0.75,
        max_per_opponent=10)


def _card_for(cards, recv):
    return [c for c in cards if c.receive_player_ids == [recv]]


def test_consensus_gap_card_is_sweetened_at_default():
    svc, elos, user_roster = _consensus_league()
    cards = _card_for(_consensus_cards(svc, elos, user_roster), "R")
    assert cards, "fixture no longer yields the G→R consensus card"
    sweet = [c for c in cards if c.gap_sweetener]
    assert sweet, "big-gap card was not sweetened"
    c = sweet[0]
    assert c.gap_sweetener["side"] == "give"
    assert c.gap_sweetener["player_id"] in c.give_player_ids
    assert c.gap_sweetener["gap_before"] > 1539.0
    assert c.gap_sweetener["gap_after"] <= 1539.0
    assert abs(c.give_value - c.receive_value) <= 1539.0
    assert c.fairness_score >= 0.75


def test_consensus_sabotage_disable_brings_gap_cards_back():
    """THE sabotage check: knob at 0 ⇒ the exact gap card the sweetener
    was fixing reappears, unsweetened, with its full gap. This is the
    deploy-free rollback lever and arm A's pin, proven live."""
    ts._cfg["sweetener_gap_threshold"] = 0.0
    svc, elos, user_roster = _consensus_league()
    cards = _card_for(_consensus_cards(svc, elos, user_roster), "R")
    assert cards
    gap_cards = [c for c in cards
                 if abs(c.give_value - c.receive_value) > 1539.0]
    assert gap_cards, "expected the unsweetened gap card to reappear"
    assert all(c.gap_sweetener is None for c in cards)


# ── v3 optimizer path ─────────────────────────────────────────────────────

def _v3_league():
    """Boarded pair with divergence so v3 emits. Sized so the ORGANIC
    winner for R is the 2-for-1 [G1, G2] → [R], fair by ratio (0.64) but
    carrying a consensus gap ≈ 2900 > 1539 — and v3's own enumeration
    cannot self-heal it, because the equalizer (X1) would be a THIRD give
    piece on a 3-for-1 that never beats the 2-for-1 organically at
    max_cards=1. The gap pass is what reaches it. The opponent's lean on
    the G's is bigger (+80) and their R lean negative (−100) because the
    A3 waiver-slot cost (425/extra) lands on their receiving side and
    must not eat the whole min_side_surplus; the fill bodies (200) sit
    under the #141 floors so they can never serve as equalizers."""
    seed = {
        "G1": _elo_for_value(3500.0),
        "G2": _elo_for_value(3000.0),
        "R":  _elo_for_value(8000.0),
        "X1": _elo_for_value(2200.0),
    }
    spec = {pid: "WR" for pid in seed}
    for pid, pos in {**_bodies("u"), **_bodies("o")}.items():
        spec[pid] = pos
        seed[pid] = _elo_for_value(200.0)
    players = {pid: _Player(id=pid, name=pid, position=pos)
               for pid, pos in spec.items()}
    user_roster = ["G1", "G2", "X1"] + list(_bodies("u"))
    opp_roster = ["R"] + list(_bodies("o"))
    user_elo = dict(seed, R=seed["R"] + 40.0,
                    G1=seed["G1"] - 40.0, G2=seed["G2"] - 40.0)
    opp_elo = dict(seed, R=seed["R"] - 100.0,
                   G1=seed["G1"] + 80.0, G2=seed["G2"] + 80.0)
    opp = LeagueMember(user_id="opp", username="opp", roster=opp_roster,
                       elo_ratings=opp_elo, has_rankings=True)
    svc = TradeService(players=players)
    svc.add_league(League(league_id="L1", name="T", platform="demo",
                          members=[opp]))
    return svc, players, user_roster, opp, seed, user_elo


def _v3_cards():
    _svc, players, user_roster, opp, seed, user_elo = _v3_league()
    _set_flags(**{"trade_engine.v2": True})
    # The stud-for-3-mids shape this fixture needs sits just past the
    # default 250-Elo headliner gap guard (~2800 vs 9000 ≈ 313 Elo).
    # Disable the guard — this file tests the gap sweetener, and the
    # guard has its own knife-edge test in test_engine_gates_config.py.
    ts._cfg["trade_elo_gap_max"] = 0.0
    return generate_pair_trades_v3(
        user_id="user",
        shrunk_user_elo=user_elo,
        user_value={pid: elo_to_value(e) for pid, e in user_elo.items()},
        user_roster=user_roster,
        opponent=opp,
        league_id="L1",
        seed_elo=seed,
        confidence=None,
        # 1, deliberately: with headroom the 3.4 fairness-band sweetener
        # would rescue a near-miss into the same [G1, G2, X1] combo the
        # gap pass builds, and the collision guard would then skip the
        # gap sweetening this test exists to prove.
        max_cards=1,
        fairness_threshold=0.75,
        players=players,
        raw_user_elo=user_elo,
    )


def test_v3_gap_card_is_sweetened_at_default():
    cards = [c for c in _v3_cards() if c.receive_player_ids == ["R"]]
    assert cards, "fixture no longer yields v3 cards for R"
    sweet = [c for c in cards if c.gap_sweetener]
    assert sweet, "v3 big-gap card was not sweetened"
    c = sweet[0]
    assert c.gap_sweetener["gap_after"] <= 1539.0
    assert c.gap_sweetener["gap_before"] > 1539.0
    assert c.gap_sweetener["side"] == "give"
    assert c.gap_sweetener["player_id"] in c.give_player_ids
    assert sorted(c.give_player_ids) == ["G1", "G2", "X1"]
    assert abs(c.give_value - c.receive_value) <= 1539.0


def test_v3_sabotage_disable_brings_gap_cards_back():
    ts._cfg["sweetener_gap_threshold"] = 0.0
    cards = [c for c in _v3_cards() if c.receive_player_ids == ["R"]]
    assert cards
    assert all(c.gap_sweetener is None for c in cards)
    assert any(abs(c.give_value - c.receive_value) > 1539.0 for c in cards)


# ── v2 divergence path (trade_engine.v2, v3 off) ──────────────────────────

def _v2_cards(max_per_opponent=3):
    svc, _players, user_roster, _opp, seed, user_elo = _v3_league()
    _set_flags(**{"trade_engine.v2": True})     # trade_engine.v3 stays OFF
    ts._cfg["trade_elo_gap_max"] = 0.0          # same reason as _v3_cards
    return svc.generate_trades(
        user_id="user", user_elo=dict(user_elo), user_roster=user_roster,
        league_id="L1", seed_elo=dict(seed), fairness_threshold=0.75,
        max_per_opponent=max_per_opponent)


def test_v2_divergence_gap_card_is_sweetened_at_default():
    """Same fixture through the heap-based v2 pair generator: the selected
    [G1, G2] → [R] card carries gap ≈ 2900 and the final-loop gap pass
    closes it with X1 (a 3-for-1, a shape v2 never enumerates)."""
    cards = [c for c in _v2_cards() if c.receive_player_ids == ["R"]
             and c.basis == "divergence"]
    assert cards, "fixture no longer yields v2 divergence cards for R"
    sweet = [c for c in cards if c.gap_sweetener]
    assert sweet, "v2 big-gap card was not sweetened"
    c = sweet[0]
    assert c.gap_sweetener["side"] == "give"
    assert c.gap_sweetener["player_id"] in c.give_player_ids
    assert c.gap_sweetener["gap_after"] <= 1539.0
    assert abs(c.give_value - c.receive_value) <= 1539.0
    assert c.fairness_score >= 0.55       # the divergence-path band floor


def test_v2_divergence_sabotage_disable_brings_gap_cards_back():
    ts._cfg["sweetener_gap_threshold"] = 0.0
    cards = [c for c in _v2_cards() if c.receive_player_ids == ["R"]
             and c.basis == "divergence"]
    assert cards
    assert all(c.gap_sweetener is None for c in cards)
    assert any(abs(c.give_value - c.receive_value) > 1539.0 for c in cards)


# ── round-2 adversarial review, 2026-08-21 ────────────────────────────────
# Two defects the first build shipped; each test below FAILS on the
# pre-review code (verified by reverting the fix, not by assertion).


def test_helper_candidate_pools_narrow_the_equalizer_universe():
    """`give_candidates`/`recv_candidates` restrict WHICH assets may be the
    equalizer without touching the rosters the 3.2 feasibility counts are
    built from. Omitted ⇒ the full roster, exactly as before."""
    players, user_roster, opp_roster, sv, _values = _mini_league()
    kw = dict(seed_value=sv, gap_threshold=1539.0, fairness_threshold=0.75,
              user_roster=user_roster, opp_roster=opp_roster,
              players=players)
    # Full roster: X1 is reachable.
    assert close_value_gap(["G"], ["R"], **kw)[0] == "X1"
    # Pool without X1: unclosable, even though X1 is still on the roster
    # (so feasibility still sees the real team).
    assert close_value_gap(["G"], ["R"], give_candidates=["X2"], **kw) is None


def _pinned_consensus_cards(svc, elos, user_roster, **kw):
    _set_flags(**{"trade_engine.v2": True})
    return svc.generate_trades(
        user_id="user", user_elo=dict(elos), user_roster=user_roster,
        league_id="L1", seed_elo=dict(elos), fairness_threshold=0.75,
        max_per_opponent=10, **kw)


def test_consensus_sweetener_never_adds_an_unpinned_give_player():
    """#174 package mode: the consensus generator PRUNES its give pool to
    the pinned players instead of gating per combo, so a sweetener drawn
    from the raw roster smuggles an asset the user never offered into a
    'trade away exactly G' job. Pre-review this emitted [G, X1] → [R]."""
    svc, elos, user_roster = _consensus_league()
    cards = _card_for(
        _pinned_consensus_cards(svc, elos, user_roster,
                                pinned_give_players=["G"]), "R")
    assert cards, "fixture no longer yields the pinned G→R card"
    for c in cards:
        assert set(c.give_player_ids) == {"G"}, (
            f"pinned job shipped unpinned give assets: {c.give_player_ids}")
        assert c.gap_sweetener is None
    # Non-vacuity: the same fixture WITHOUT the pin is still sweetened, so
    # this test pins the pool restriction, not a dead sweetener.
    free = _card_for(_pinned_consensus_cards(svc, elos, user_roster), "R")
    assert any(c.gap_sweetener for c in free)


def _acquire_league():
    """User gives G (consensus 7000, WR) for R (5400, RB) — their OWN board
    loves R, so the #108 gate passes while consensus says the OPPONENT is
    the richer side, which puts the equalizer on the RECEIVE side. The
    opponent also rosters Z (2400, RB). `consensus_both_ways` is arm D's
    overlay and is what lets a give-heavy consensus card exist at all."""
    ts._cfg["consensus_both_ways"] = 1.0
    elos = {"G": _elo_for_value(7000.0), "R": _elo_for_value(5400.0),
            "Z": _elo_for_value(2400.0)}
    spec = {"G": "WR", "R": "WR", "Z": "RB"}
    for pid, pos in {**_bodies("u"), **_bodies("o")}.items():
        spec[pid] = pos
        elos[pid] = _elo_for_value(200.0)
    players = {pid: _Player(id=pid, name=pid, position=pos)
               for pid, pos in spec.items()}
    user_roster = ["G"] + list(_bodies("u"))
    opp_roster = ["R", "Z"] + list(_bodies("o"))
    opp = LeagueMember(user_id="opp", username="opp", roster=opp_roster,
                       elo_ratings={}, has_rankings=False)
    svc = TradeService(players=players)
    svc.add_league(League(league_id="L1", name="T", platform="demo",
                          members=[opp]))
    user_elo = dict(elos, R=_elo_for_value(7600.0))
    return svc, elos, user_elo, user_roster


def test_consensus_sweetener_respects_the_acquire_position_filter():
    """FB-47 / need-positions: the consensus receive pool is pruned to the
    positions the user asked for, so an off-need equalizer would hand back
    an asset the job excluded. WR-only ⇒ the RB equalizer is unreachable;
    allowing RB ⇒ the same card IS sweetened (non-vacuity in one pair)."""
    svc, elos, user_elo, user_roster = _acquire_league()
    _set_flags(**{"trade_engine.v2": True})

    def _run(acq):
        cards = svc.generate_trades(
            user_id="user", user_elo=dict(user_elo), user_roster=user_roster,
            league_id="L1", seed_elo=dict(elos), fairness_threshold=0.75,
            max_per_opponent=10, acquire_positions=acq)
        return [c for c in cards if c.give_player_ids == ["G"]]

    wr_only = _run(["WR"])
    assert wr_only, "fixture no longer yields the G→R card"
    for c in wr_only:
        assert "Z" not in c.receive_player_ids, (
            "an off-need RB was swept into a WR-only acquire job")
        assert c.gap_sweetener is None
    both = _run(["WR", "RB"])
    assert any(c.gap_sweetener and "Z" in c.receive_player_ids
               for c in both), "fixture no longer sweetens when RB is allowed"


def _fit_premium_v3_cards(gap_threshold):
    """A v3 pair whose organic winner is a fit-premium 1-for-1 (the user
    pays 200 of raw-board value for a need fill) that ALSO carries a
    consensus gap of 1600. Z is deliberately absent from the opponent's
    Elo map, so v3 never enumerates [G] → [R, Z] organically — only the
    gap pass can build it."""
    ts._cfg["trade_elo_gap_max"] = 0.0
    ts._cfg["sweetener_gap_threshold"] = gap_threshold
    seed = {"G": _elo_for_value(7000.0), "R": _elo_for_value(5400.0),
            "Z": _elo_for_value(2400.0)}
    spec = {"G": "WR", "R": "RB", "Z": "RB"}
    for pid, pos in {**_bodies("u"), **_bodies("o")}.items():
        spec[pid] = pos
        seed[pid] = _elo_for_value(200.0)
    players = {pid: _Player(id=pid, name=pid, position=pos)
               for pid, pos in spec.items()}
    shrunk = dict(seed, R=_elo_for_value(7300.0))
    raw = dict(seed, R=_elo_for_value(6800.0))       # loss 200 ≤ 300 cap
    opp_elo = dict(seed, G=_elo_for_value(7400.0), R=_elo_for_value(5000.0))
    del opp_elo["Z"]
    opp = LeagueMember(user_id="opp", username="opp",
                       roster=["R", "Z"] + list(_bodies("o")),
                       elo_ratings=opp_elo, has_rankings=True)
    return generate_pair_trades_v3(
        user_id="user", shrunk_user_elo=shrunk,
        user_value={pid: elo_to_value(e) for pid, e in shrunk.items()},
        user_roster=["G"] + list(_bodies("u")), opponent=opp,
        league_id="L1", seed_elo=seed, confidence=None, max_cards=1,
        fairness_threshold=0.75, players=players, raw_user_elo=raw,
        user_needs={"RB"})


def test_v3_gap_sweetener_clears_the_stale_fit_premium():
    """`fit_premium` prices a 1-for-1 the user knowingly loses a little on
    (`fit_premium_1for1` can only fire on a 1x1). A gap-sweetened card is
    no longer that shape, so the price must not ride along — the v2
    divergence path already nulls its `fit_paid`. Pre-review, v3 shipped
    the stale badge on the 1-for-2."""
    _set_flags(**{"trade_engine.v2": True, "trade.fit_premium": True})
    # Non-vacuity first: at the kill value the organic winner IS the
    # fit-premium 1-for-1 this test needs the sweetener to consume.
    off = _fit_premium_v3_cards(0.0)
    assert off and off[0].receive_player_ids == ["R"]
    assert off[0].fit_premium and off[0].fit_premium["value_paid"] == 200.0
    assert abs(off[0].give_value - off[0].receive_value) > 1539.0

    on = _fit_premium_v3_cards(1539.0)
    assert on and sorted(on[0].receive_player_ids) == ["R", "Z"]
    assert on[0].gap_sweetener and on[0].gap_sweetener["side"] == "receive"
    assert on[0].fit_premium is None, (
        "sweetened card kept a 1-for-1 fit-premium price")
