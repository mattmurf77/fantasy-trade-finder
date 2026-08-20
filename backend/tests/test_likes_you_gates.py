"""D-096 — quality gates on the likes-you injector.

Reverses D-055 sub-decision (5) / Q-G6-1 ("exactly R4 dedup, none of the
quality rules"). Prod measurement that motivated it, and the survivor counts
per option, are in docs/plans/likes-you-quality-gates/scope.md.

Three things are pinned here:

  1. **The floor's UNIT.** D-055's floor was measured on RAW summed values
     while the value bar the user reads is PACKAGE-ADJUSTED. A give side of
     one stud vs a receive side of three depth pieces is where the two
     diverge, and it is exactly the shape that shipped a -6,019 card behind
     a -500 floor. `test_floor_is_measured_in_bar_units` builds that shape
     and asserts the gate agrees with the card the user would see.

  2. **The level ladder**, including that `likes_you_gate_level = 0` restores
     pre-D-096 behaviour EXACTLY (the deploy-free revert).

  3. **Directional R1.** Blanket `overpay_ok` would delete the surface's best
     cards — a mirrored like the counterparty ALREADY liked in which the USER
     is massively overpaid. Measured: blanket R1 kills 58 of the 83 served
     cards that clear the floor, all 58 user-favourable. R1 is therefore
     honoured only when the VIEWER is the heavier side.

Same in-memory-SQLite pattern as test_trade_match_flow.py.
"""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, text

import backend.database as db_module
import backend.server as server
import backend.trade_service as ts_module
from backend.database import metadata
from backend.ranking_service import Player
from backend.trade_service import League, LeagueMember, TradeCard, TradeService

LEAGUE = "league_d096"
ME     = "user_me"
OPP    = "user_opp"


@pytest.fixture()
def mem_engine():
    eng = create_engine("sqlite:///:memory:",
                        connect_args={"check_same_thread": False})
    metadata.create_all(eng)
    with patch.object(db_module, "engine", eng):
        yield eng


@pytest.fixture()
def cfg():
    """Restore trade_service._cfg after any knob poke."""
    before = dict(ts_module._cfg)
    yield ts_module._cfg
    ts_module._cfg.clear()
    ts_module._cfg.update(before)


def _like(conn, give_ids, recv_ids, user_id=OPP):
    """A leaguemate's 'like'. give/recv are from THEIR perspective."""
    created = (datetime.now(timezone.utc).replace(tzinfo=None)
               - timedelta(days=1)).isoformat()
    conn.execute(text(
        "INSERT INTO trade_decisions "
        "(user_id, league_id, give_player_ids, receive_player_ids, decision, created_at) "
        "VALUES (:uid, :lid, :give, :recv, 'like', :created)"
    ), {"uid": user_id, "lid": LEAGUE,
        "give": json.dumps(give_ids), "recv": json.dumps(recv_ids),
        "created": created})


def _svc(pids):
    return TradeService(players={
        pid: Player(id=pid, name=pid.upper(), position="RB", team="AAA", age=25)
        for pid in pids})


def _league(mine, theirs):
    return League(
        league_id=LEAGUE, name="D096", platform="sleeper",
        members=[
            LeagueMember(user_id=ME,  username="me",  roster=list(mine),   elo_ratings={}),
            LeagueMember(user_id=OPP, username="opp", roster=list(theirs), elo_ratings={}),
        ])


def _inject(svc, mine, theirs, seed_map, cards=None):
    return server._inject_likes_you_cards(
        cards=list(cards or []), trade_service=svc, user_id=ME,
        league_id=LEAGUE, league=_league(mine, theirs),
        user_roster=list(mine), seed_map=seed_map)


def _ly(deck):
    return [c for c in deck if getattr(c, "likes_you", False)]


def _card(give, recv, composite=5.0):
    return TradeCard(
        trade_id="organic_" + "_".join(give + recv), league_id=LEAGUE,
        proposing_user_id=ME, target_user_id=OPP, target_username="opp",
        give_player_ids=list(give), receive_player_ids=list(recv),
        mismatch_score=1.0, fairness_score=0.9, composite_score=composite)


# ---------------------------------------------------------------------------
# The unit mismatch — the defect this change exists to fix
# ---------------------------------------------------------------------------
#
# THE_STUD is a single elite asset the user gives up. THREE depth pieces come
# back whose RAW sum slightly exceeds it, so the D-055 raw-sum floor is happy.
# The value bar, however, renders package-adjusted values: three lesser assets
# are depth-discounted against the package's own best, so the user is visibly
# down. That is the -6,019-behind-a--500-floor shape, in miniature.

# Tuned so the two metrics land on OPPOSITE sides of zero: the raw sums say
# the user gains ~+178, the value bar says the user is down ~-1,045 — past
# D-055's own |Delta| >= 500 materiality floor for "insult". This card clears
# the legacy -500 raw floor AND a naive raw floor at 0, and is exactly the
# shape prod is still serving (5 live cards clear the raw floor while showing
# a >= 500 loss on the bar).
STUD  = "stud"
DEPTH = ["d1", "d2", "d3", "d4"]
_LOPSIDED_SEED = dict({STUD: 2050.0}, **{d: 1775.0 for d in
                                         ["d1", "d2", "d3", "d4"]})


def _pkg_delta(give, recv, seed_map):
    with ts_module.stud_tax_override(
            ts_module.pinned_stud_tax_mode()
            or ts_module.stud_tax_mode_for_user(ME)):
        gv, rv, d = server._likes_you_package_delta(
            give, recv, server._likes_you_seed_value(seed_map))
    return gv, rv, d


def test_lopsided_fixture_really_does_split_the_two_metrics():
    """Guard on the fixture itself: raw says the user gains, the bar says the
    user loses. Without this split the rest of the file proves nothing."""
    # The injected direction: the user gives the stud, receives the depth.
    raw_give_stud = server._likes_you_user_delta([STUD], DEPTH, _LOPSIDED_SEED)
    _, _, pkg = _pkg_delta([STUD], DEPTH, _LOPSIDED_SEED)
    assert raw_give_stud > 0.0, "raw sums must favour the user"
    assert raw_give_stud >= server._likes_you_min_user_delta(), \
        "and must clear the legacy -500 raw floor"
    assert pkg < -500.0, \
        "while the value bar shows a loss past D-055's materiality floor"


def test_floor_is_measured_in_bar_units(mem_engine, cfg):
    """The card whose bar shows a loss is not injected, even though its raw
    sum clears both the old -500 floor and a raw floor of 0."""
    with mem_engine.begin() as conn:
        _like(conn, give_ids=DEPTH, recv_ids=[STUD])   # OPP gives depth, wants the stud
    deck = _inject(_svc([STUD] + DEPTH), mine=[STUD], theirs=DEPTH,
                   seed_map=_LOPSIDED_SEED)
    assert _ly(deck) == [], "a card the bar shows the user losing must not be injected"


def test_level_zero_is_byte_identical_to_legacy(mem_engine, cfg):
    """The documented deploy-free revert: ONE value, and the same card the
    pre-D-096 code shipped comes back."""
    with mem_engine.begin() as conn:
        _like(conn, give_ids=DEPTH, recv_ids=[STUD])
    cfg["likes_you_gate_level"] = 0.0
    deck = _inject(_svc([STUD] + DEPTH), mine=[STUD], theirs=DEPTH,
                   seed_map=_LOPSIDED_SEED)
    ly = _ly(deck)
    assert len(ly) == 1, "level 0 must restore the raw-sum floor's verdict"
    assert ly[0].give_player_ids == [STUD]
    assert ly[0].receive_player_ids == DEPTH
    # and it still carries the package-adjusted bar values
    gv, rv, _ = _pkg_delta([STUD], DEPTH, _LOPSIDED_SEED)
    assert ly[0].give_value == pytest.approx(round(gv, 1))
    assert ly[0].receive_value == pytest.approx(round(rv, 1))


def test_level_zero_still_honours_the_legacy_floor_value(mem_engine, cfg):
    """At level 0 the -500 raw floor is still the operative bar."""
    with mem_engine.begin() as conn:
        _like(conn, give_ids=["cheap"], recv_ids=["elite"])
    cfg["likes_you_gate_level"] = 0.0
    seed = {"elite": 1900.0, "cheap": 1200.0}   # user gives elite, gets cheap
    deck = _inject(_svc(["elite", "cheap"]), mine=["elite"], theirs=["cheap"],
                   seed_map=seed)
    assert _ly(deck) == []


def test_level_one_applies_the_floor_but_not_presentment(mem_engine, cfg):
    """Level 1 = package floor only. A card the user wins big on survives at
    both 1 and 2; blanket R1 (which level 2 deliberately does NOT run) would
    have killed it."""
    with mem_engine.begin() as conn:
        _like(conn, give_ids=["elite"], recv_ids=["cheap"])
    seed = {"elite": 1900.0, "cheap": 1200.0}   # user gives cheap, gets elite
    sv = server._likes_you_seed_value(seed)
    assert not ts_module.overpay_ok(["cheap"], ["elite"], sv), \
        "fixture must be a package blanket-R1 would kill"
    for level in (1.0, 2.0):
        cfg["likes_you_gate_level"] = level
        deck = _inject(_svc(["elite", "cheap"]), mine=["cheap"], theirs=["elite"],
                       seed_map=seed)
        assert len(_ly(deck)) == 1, f"user-favourable like must survive level {level}"


def test_directional_r1_kills_a_viewer_overpay(cfg):
    """R1 is honoured when the VIEWER is the heavier side."""
    seed = {"elite": 1900.0, "cheap": 1200.0}
    sv = server._likes_you_seed_value(seed)
    assert server._likes_you_presentment_ok(["elite"], ["cheap"], sv) is False


def test_directional_r1_spares_a_viewer_windfall(cfg):
    """...and is NOT honoured in the direction that would delete the surface's
    best cards. Same package, mirrored."""
    seed = {"elite": 1900.0, "cheap": 1200.0}
    sv = server._likes_you_seed_value(seed)
    assert ts_module.overpay_ok(["cheap"], ["elite"], sv) is False, \
        "blanket R1 kills this"
    assert server._likes_you_presentment_ok(["cheap"], ["elite"], sv) is True, \
        "directional R1 must spare it"


def test_presentment_runs_filler_ok(cfg):
    """A junk sweetener on a multi-asset side is rejected at level 2."""
    seed = {"head": 1800.0, "junk": 1000.0, "back": 1810.0}
    sv = server._likes_you_seed_value(seed)
    assert ts_module.filler_ok(["head", "junk"], ["back"], sv, sv) is False
    assert server._likes_you_presentment_ok(["head", "junk"], ["back"], sv) is False
    cfg["filler_min_frac"] = 0.0          # documented master kill-switch
    assert server._likes_you_presentment_ok(["head", "junk"], ["back"], sv) is True


def test_gate_failure_consumes_no_cap_slot(mem_engine, cfg):
    """D-055's no-slot-consumed semantics survive D-096: three good likes
    still land even when bad ones are interleaved ahead of them."""
    good = [(f"g{i}", f"r{i}") for i in range(1, 4)]
    seed = {}
    with mem_engine.begin() as conn:
        # Two insulting likes first (user would give the elite, get scraps).
        _like(conn, give_ids=["scrap1"], recv_ids=["elite1"])
        _like(conn, give_ids=["scrap2"], recv_ids=["elite2"])
        for g, r in good:
            _like(conn, give_ids=[r], recv_ids=[g])
    seed = {"elite1": 1900.0, "elite2": 1900.0, "scrap1": 1100.0, "scrap2": 1100.0}
    mine   = ["elite1", "elite2"] + [g for g, _ in good]
    theirs = ["scrap1", "scrap2"] + [r for _, r in good]
    deck = _inject(_svc(mine + theirs), mine=mine, theirs=theirs, seed_map=seed)
    ly = _ly(deck)
    assert len(ly) == server._LIKES_YOU_CAP == 3
    assert {c.give_player_ids[0] for c in ly} == {g for g, _ in good}


def test_gated_out_existing_card_keeps_its_organic_position(mem_engine, cfg):
    """An EXISTING generated card that fails the gates is not dropped from the
    deck — it only loses the likes_you flag and the position-1 boost."""
    with mem_engine.begin() as conn:
        _like(conn, give_ids=DEPTH, recv_ids=[STUD])
    organic  = _card(DEPTH, [STUD], composite=9.0)       # unrelated, ranks top
    mirrored = _card([STUD], DEPTH, composite=1.0)       # the likes-you twin
    deck = _inject(_svc([STUD] + DEPTH), mine=[STUD] + DEPTH, theirs=DEPTH + [STUD],
                   seed_map=_LOPSIDED_SEED, cards=[organic, mirrored])
    assert mirrored in deck, "gated card must stay in the deck"
    assert mirrored.likes_you is False
    assert mirrored.composite_score == pytest.approx(1.0), "no boost"
    assert deck[0] is organic


def test_synthesized_card_bar_matches_the_gated_number(mem_engine, cfg):
    """The gate and the bar can never disagree: the card ships the same
    package values the floor was measured on."""
    with mem_engine.begin() as conn:
        _like(conn, give_ids=["elite"], recv_ids=["cheap"])
    seed = {"elite": 1900.0, "cheap": 1200.0}
    deck = _inject(_svc(["elite", "cheap"]), mine=["cheap"], theirs=["elite"],
                   seed_map=seed)
    card = _ly(deck)[0]
    gv, rv, delta = _pkg_delta(["cheap"], ["elite"], seed)
    assert card.give_value == pytest.approx(round(gv, 1))
    assert card.receive_value == pytest.approx(round(rv, 1))
    assert card.receive_value - card.give_value >= 0.0
    assert delta >= server._likes_you_min_user_gain()


def test_floor_knob_is_live(mem_engine, cfg):
    """`likes_you_min_user_gain` moves the bar without a deploy."""
    with mem_engine.begin() as conn:
        _like(conn, give_ids=["b"], recv_ids=["a"])
    seed = {"a": 1600.0, "b": 1595.0}          # user gives a, gets b: tiny loss
    cfg["likes_you_min_user_gain"] = -1000.0
    assert len(_ly(_inject(_svc(["a", "b"]), ["a"], ["b"], seed))) == 1
    cfg["likes_you_min_user_gain"] = 0.0
    assert _ly(_inject(_svc(["a", "b"]), ["a"], ["b"], seed)) == []


def test_gate_level_clamps_garbage(cfg):
    for bad, expect in ((-7.0, 0), (99.0, 2), (2.9, 2)):
        cfg["likes_you_gate_level"] = bad
        assert server._likes_you_gate_level() == expect


def test_knob_defaults_are_the_shipped_values(cfg):
    """The shipped posture, asserted rather than assumed."""
    ts_module._cfg.pop("likes_you_gate_level", None)
    ts_module._cfg.pop("likes_you_min_user_gain", None)
    ts_module._cfg.pop("likes_you_min_user_delta", None)
    assert server._likes_you_gate_level() == 2
    assert server._likes_you_min_user_gain() == 0.0
    assert server._likes_you_min_user_delta() == -500.0
    assert ts_module._DEFAULT_CFG["likes_you_gate_level"] == 2.0
    assert ts_module._DEFAULT_CFG["likes_you_min_user_gain"] == 0.0
    assert ts_module._DEFAULT_CFG["likes_you_min_user_delta"] == -500.0


def test_floor_default_equals_user_gain_epsilon(cfg):
    """The floor is not an arbitrary 0: it is the gated path's own rule."""
    assert (ts_module._DEFAULT_CFG["likes_you_min_user_gain"]
            == ts_module._DEFAULT_CFG["user_gain_epsilon"])


def test_r2_r3_r5_are_deliberately_not_run(cfg):
    """Reasoned exclusions, pinned so a future 'run everything' sweep has to
    argue with a test. A 3-RB-for-1-RB mirror blows R2's per-position net cap
    and is still injectable."""
    seed = {f"rb{i}": 1500.0 for i in range(1, 5)}
    sv = server._likes_you_seed_value(seed)
    players = {pid: Player(id=pid, name=pid, position="RB", team="A", age=25)
               for pid in seed}
    assert ts_module.pos_net_ok(["rb1"], ["rb2", "rb3", "rb4"], players) is False
    assert server._likes_you_presentment_ok(["rb1"], ["rb2", "rb3", "rb4"], sv) is True
