"""Fit-congruence signal weighting (D-060) — swipe Elo weighted by surprise.

A deck pass is not purely a valuation statement. A rebuilder who passes a
fairly-priced vet is stating a WINDOW preference, and the flat trade_k_pass
discount was the only acknowledgment that "don't want" ≠ "don't value".
This weights the swipe's K by how surprising it is given the user's window:

  fit-EXPLAINED (like on a window-congruent card, pass on an anti-window
                 one)  → K *= fit_k_explained_mult (0.4)
  fit-DEFYING   (pass on a window-congruent card, like on an anti-window
                 one)  → K *= fit_k_defying_mult (1.0, full baseline)
  neutral       (no window / not_sure, |shift| < lane_shift_frac, or a card
                 with no stamped shift) → 1.0, byte-identical to pre-D-060.

Covers: signed_lane_shift() — the signed quantity the machinery rests on — the congruence
matrix itself, the record_trade_signal fit_mult (including multi-player
pairwise decomposition), generation-time stamping of card.lane_shift, the
POST /api/trades/swipe wiring (in-memory Elo AND the persisted k_factor —
_compute_elo replays the DB rows, so they must agree), and the knob-only
kill switch.

Fixtures deliberately use PICK assets (_now_lean is exactly -0.25 for a
pick) against age-less players (_now_lean exactly 0.0) so the shift is a
hand-computable constant instead of a hostage to the age curves.
"""
import json
from unittest.mock import patch, MagicMock

import pytest
from sqlalchemy import create_engine

import backend.database as db_module
import backend.feature_flags as ff
import backend.ranking_service as rs
import backend.server as server
import backend.trade_service as ts
from backend.database import metadata
from backend.ranking_service import RankingService, Player
from backend.trade_service import (
    League, LeagueMember, TradeCard, TradeService, classify_lane,
    fit_congruence_mult, signed_lane_shift,
)

INIT = RankingService.ELO_INITIAL      # 1500.0


@pytest.fixture(autouse=True)
def _isolate():
    """Snapshot/restore both config surfaces + flags (same pattern as the
    other trade-engine modules): fit_congruence_mult reads trade_service
    _cfg, record_trade_signal reads ranking_service _cfg."""
    old_flags = ff._flags_cache
    old_ts_cfg = dict(ts._cfg)
    old_rs_cfg = dict(rs._cfg)
    ff._flags_cache = dict(ff.DEFAULT_FLAGS)
    ts._cfg.clear()
    ts._cfg.update(ts._DEFAULT_CFG)
    rs._cfg.clear()
    rs._cfg.update(rs._DEFAULT_CFG)
    try:
        yield
    finally:
        ff._flags_cache = old_flags
        ts._cfg.clear()
        ts._cfg.update(old_ts_cfg)
        rs._cfg.clear()
        rs._cfg.update(old_rs_cfg)


class _P:
    """Minimal player stand-in for the lane machinery (position + age)."""

    def __init__(self, pid, position="RB", age=0):
        self.id = pid
        self.name = pid
        self.position = position
        self.age = age
        self.team = "TST"
        self.search_rank = 50
        self.pick_value = 67.5 if position == "PICK" else None


# PLR = age-less player (_now_lean 0.0); PK = pick (_now_lean -0.25).
_LANE_PLAYERS = {"PLR": _P("PLR", "RB", 0), "PK": _P("PK", "PICK", 0)}
_EQUAL = lambda pid: 1000.0                                      # noqa: E731

# give PLR / receive PK  → shift −0.125 before the window sign
# give PK  / receive PLR → shift +0.125 before the window sign
_TO_FUTURE = (["PLR"], ["PK"])       # user acquires the pick
_TO_NOW    = (["PK"], ["PLR"])       # user acquires the win-now body


# ────────────────────── signed_lane_shift: both directions ──────────────────────

def test_lane_shift_is_signed_by_the_users_window():
    give, recv = _TO_NOW
    # A rebuilder buying win-now is moving AWAY from their window.
    assert signed_lane_shift(give, recv, _LANE_PLAYERS, "rebuilder", _EQUAL) == \
        pytest.approx(-0.125)
    # The identical card is TOWARD a contender's window.
    assert signed_lane_shift(give, recv, _LANE_PLAYERS, "contender", _EQUAL) == \
        pytest.approx(0.125)
    # …and mirrors when the card is flipped.
    give, recv = _TO_FUTURE
    assert signed_lane_shift(give, recv, _LANE_PLAYERS, "rebuilder", _EQUAL) == \
        pytest.approx(0.125)
    assert signed_lane_shift(give, recv, _LANE_PLAYERS, "contender", _EQUAL) == \
        pytest.approx(-0.125)


def test_lane_shift_none_without_a_window_direction():
    give, recv = _TO_NOW
    assert signed_lane_shift(give, recv, _LANE_PLAYERS, None, _EQUAL) is None
    assert signed_lane_shift(give, recv, _LANE_PLAYERS, "not_sure", _EQUAL) is None
    # No value on the table → no mean to take.
    assert signed_lane_shift(give, recv, _LANE_PLAYERS, "rebuilder",
                      lambda pid: 0.0) is None


def test_classify_lane_still_collapses_neutral_and_anti_window():
    """The reason the signed shift is persisted at all: `lane` cannot tell
    a window-NEUTRAL card from a strongly ANTI-window one."""
    anti = classify_lane(*_TO_NOW, _LANE_PLAYERS, "rebuilder", _EQUAL)
    neutral = classify_lane(["PLR"], ["PLR2"],
                            {**_LANE_PLAYERS, "PLR2": _P("PLR2", "WR", 0)},
                            "rebuilder", _EQUAL)
    assert anti == neutral == "value"        # indistinguishable via `lane`
    assert signed_lane_shift(*_TO_NOW, _LANE_PLAYERS, "rebuilder", _EQUAL) < 0


def test_classify_lane_unchanged_for_no_value_cards():
    """Refactoring classify_lane onto signed_lane_shift must not move the
    total<=0 corner: it still labels "value", not None."""
    assert classify_lane(*_TO_NOW, _LANE_PLAYERS, "rebuilder",
                         lambda pid: 0.0) == "value"


# ───────────────────────── the congruence matrix ─────────────────────────

_EXPLAINED = 0.4      # fit_k_explained_mult default
_DEFYING = 1.0        # fit_k_defying_mult default


@pytest.mark.parametrize("shift,decision,expected", [
    # Rebuild side, card acquires win-now (shift −0.125 = anti-window).
    (-0.125, "pass", _EXPLAINED),   # the window already explains the pass
    (-0.125, "like", _DEFYING),     # rebuilder wants the vet ANYWAY — full K
    # Rebuild side, card acquires future capital (+0.125 = congruent).
    (+0.125, "like", _EXPLAINED),   # of course they liked it
    (+0.125, "pass", _DEFYING),     # rejected their own window → real value call
])
def test_congruence_matrix(shift, decision, expected):
    assert fit_congruence_mult(shift, decision) == expected


def test_contend_side_is_the_exact_mirror():
    """Same card, opposite window ⇒ opposite congruence. Built from real
    signed_lane_shift() values rather than literals so the sign convention is
    exercised end to end."""
    give, recv = _TO_NOW
    reb = signed_lane_shift(give, recv, _LANE_PLAYERS, "rebuilder", _EQUAL)
    con = signed_lane_shift(give, recv, _LANE_PLAYERS, "contender", _EQUAL)
    assert fit_congruence_mult(reb, "pass") == _EXPLAINED
    assert fit_congruence_mult(con, "pass") == _DEFYING
    assert fit_congruence_mult(reb, "like") == _DEFYING
    assert fit_congruence_mult(con, "like") == _EXPLAINED


def test_no_window_and_sub_threshold_are_neutral():
    # not_sure / no window → the shift is None → 1.0.
    assert fit_congruence_mult(None, "like") == 1.0
    assert fit_congruence_mult(None, "pass") == 1.0
    # |shift| below lane_shift_frac → 1.0, on both sides of zero.
    thr = ts._c("lane_shift_frac")
    for s in (0.0, thr - 1e-9, -(thr - 1e-9)):
        assert fit_congruence_mult(s, "like") == 1.0
        assert fit_congruence_mult(s, "pass") == 1.0
    # Exactly at the threshold counts as congruent (matches classify_lane's
    # >= lane_shift_frac window test).
    assert fit_congruence_mult(thr, "like") == _EXPLAINED


def test_threshold_follows_the_lane_knob():
    ts._cfg["lane_shift_frac"] = 0.50
    assert fit_congruence_mult(0.125, "like") == 1.0     # now sub-threshold
    ts._cfg["lane_shift_frac"] = 0.05
    assert fit_congruence_mult(0.125, "like") == _EXPLAINED


# ───────────────────── record_trade_signal(fit_mult=…) ─────────────────────

def _svc(ids, position="RB"):
    return RankingService(players=[
        Player(id=i, name=f"P{i}", position=position, team="T", age=24)
        for i in ids])


def _elo(svc, position="RB"):
    return {r.player.id: r.elo for r in svc.get_rankings(position=position).rankings}


def test_fit_mult_scales_k_linearly():
    """Both seed 1500 ⇒ expected score 0.5 ⇒ winner gains K/2."""
    base = _svc(["a", "b"])
    base.record_trade_signal(winner_ids=["a"], loser_ids=["b"], decision="pass")
    full = _elo(base)["a"] - INIT                    # K=4 → +2.0

    disc = _svc(["a", "b"])
    disc.record_trade_signal(winner_ids=["a"], loser_ids=["b"],
                             decision="pass", fit_mult=0.4)
    assert _elo(disc)["a"] - INIT == pytest.approx(full * 0.4)


def test_fit_mult_default_is_unchanged_behavior():
    explicit = _svc(["a", "b"])
    explicit.record_trade_signal(winner_ids=["a"], loser_ids=["b"],
                                 decision="like", fit_mult=1.0)
    implicit = _svc(["a", "b"])
    implicit.record_trade_signal(winner_ids=["a"], loser_ids=["b"],
                                 decision="like")
    assert _elo(explicit) == _elo(implicit)


def test_multi_player_sides_still_decompose_pairwise_with_the_mult():
    svc = _svc(["r1", "r2", "g1"])
    svc.record_trade_signal(winner_ids=["r1", "r2"], loser_ids=["g1"],
                            decision="like", fit_mult=0.4)
    # 2×1 = 2 pairwise swipes, each carrying the multiplied K.
    assert len(svc._trade_swipes) == 2
    ks = [k for _s, k in svc._trade_swipes]
    assert ks == pytest.approx([rs._c("trade_k_like") * 0.4] * 2)
    assert {(s.winner_id, s.loser_id) for s, _k in svc._trade_swipes} == \
        {("r1", "g1"), ("r2", "g1")}


def test_defying_swipe_keeps_full_k():
    """The rebuilder who LIKES the win-now vet moves Elo exactly as much as
    the pre-D-060 engine did — the defying lane is not boosted either."""
    shift = signed_lane_shift(*_TO_NOW, _LANE_PLAYERS, "rebuilder", _EQUAL)
    control = _svc(["a", "b"])
    control.record_trade_signal(winner_ids=["a"], loser_ids=["b"],
                                decision="like")
    defying = _svc(["a", "b"])
    defying.record_trade_signal(winner_ids=["a"], loser_ids=["b"],
                                decision="like",
                                fit_mult=fit_congruence_mult(shift, "like"))
    assert _elo(defying) == _elo(control)


# ─────────────────────────── the kill switch ───────────────────────────

def test_explained_knob_at_one_reproduces_the_control_trajectory():
    """fit_k_explained_mult = 1.0 (defying already 1.0) ⇒ byte-identical Elo
    over a mixed sequence of congruent/anti-window likes and passes."""
    seq = [
        (_TO_NOW,    "pass"), (_TO_NOW,    "like"),
        (_TO_FUTURE, "like"), (_TO_FUTURE, "pass"),
        (_TO_NOW,    "pass"), (_TO_FUTURE, "like"),
    ]

    def _run(apply_mult: bool):
        svc = _svc(["a", "b"])
        for (give, recv), decision in seq:
            shift = signed_lane_shift(give, recv, _LANE_PLAYERS, "rebuilder", _EQUAL)
            kw = {"fit_mult": fit_congruence_mult(shift, decision)} \
                if apply_mult else {}
            if decision == "like":
                svc.record_trade_signal(winner_ids=["a"], loser_ids=["b"],
                                        decision="like", **kw)
            else:
                svc.record_trade_signal(winner_ids=["b"], loser_ids=["a"],
                                        decision="pass", **kw)
        return _elo(svc)

    control = _run(apply_mult=False)
    ts._cfg["fit_k_explained_mult"] = 1.0
    assert _run(apply_mult=True) == control       # exact, not approx

    # Sanity: at the shipped default the trajectory genuinely differs, so
    # the assertion above is not vacuous.
    ts._cfg["fit_k_explained_mult"] = 0.4
    assert _run(apply_mult=True) != control


def test_knobs_are_seeded_in_both_config_surfaces():
    """The model_config seed is what makes PUT /api/admin/config work."""
    seeded = {k: v for k, v, _d in db_module._MODEL_CONFIG_DEFAULTS}
    for key, default in (("fit_k_explained_mult", 0.4),
                         ("fit_k_defying_mult", 1.0)):
        assert ts._DEFAULT_CFG[key] == default
        assert seeded[key] == default


# ───────────────────── generation stamps card.lane_shift ─────────────────────

def _generated_cards(outlook):
    """1-for-1 divergence fixture: the user gives a body and receives a
    pick, i.e. the classic rebuild-congruent / contend-incongruent card."""
    ff._flags_cache = {**ff.DEFAULT_FLAGS, "trade_engine.v2": True}
    players = {"G": _P("G", "RB", 25), "R": _P("R", "PICK", 0)}
    opp = LeagueMember(user_id="opp", username="opp", roster=["R"],
                       elo_ratings={"G": 1700, "R": 1500}, has_rankings=True)
    svc = TradeService(players=players)
    svc.add_league(League(league_id="L1", name="T", platform="demo",
                          members=[opp]))
    return svc.generate_trades(
        user_id="user", user_elo={"G": 1500, "R": 1700}, user_roster=["G"],
        league_id="L1", seed_elo={"G": 1540, "R": 1500},
        fairness_threshold=0.05, outlook=outlook)


def test_generation_stamps_signed_shift_without_the_lanes_flag():
    """trade.lanes is OFF here — fit-congruence has no feature flag and must
    not inherit one."""
    cards = _generated_cards("rebuilder")
    assert cards, "fixture should surface a card"
    assert all(c.lane is None for c in cards)          # lanes flag off
    assert all(c.lane_shift is not None and c.lane_shift > 0 for c in cards)
    # Same deck for a contender is the mirror image.
    for c in _generated_cards("contender"):
        assert c.lane_shift is not None and c.lane_shift < 0


def test_generation_leaves_shift_none_without_a_window():
    for c in _generated_cards(None):
        assert c.lane_shift is None
    for c in _generated_cards("not_sure"):
        assert c.lane_shift is None


# ───────────────────── POST /api/trades/swipe wiring ─────────────────────

ME, PARTNER, LEAGUE = "user_me", "user_partner", "league_fit_test"
GIVE, RECEIVE = ["g1"], ["r1"]


@pytest.fixture()
def harness():
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False})
    metadata.create_all(engine)

    players = [Player(id=pid, name=pid.upper(), position="RB", team="AAA",
                      age=25) for pid in GIVE + RECEIVE]
    service = RankingService(players=players)
    trade_svc = TradeService(players={p.id: p for p in players})
    league = League(league_id=LEAGUE, name="Fit Test League", platform="sleeper",
                    members=[
                        LeagueMember(user_id=ME, username="me", roster=[],
                                     elo_ratings={}),
                        LeagueMember(user_id=PARTNER, username="partner",
                                     roster=[], elo_ratings={}),
                    ])
    token = "test-token-fit-congruence"
    sess = {
        "user_id":       ME,
        "league":        league,
        "players":       players,
        "services":      {"1qb_ppr": service},
        "service":       service,
        "trade_svcs":    {"1qb_ppr": trade_svc},
        "trade_svc":     trade_svc,
        "active_format": "1qb_ppr",
        "last_active":   0.0,
    }
    server.app.config["TESTING"] = True
    client = server.app.test_client()
    saved = MagicMock()
    with patch.object(db_module, "engine", engine), \
         patch.object(server, "save_trade_swipes", saved), \
         patch.object(server, "record_event", MagicMock()), \
         patch.object(server, "create_notification", MagicMock()):
        with server._sessions_lock:
            server._sessions[token] = sess
        try:
            yield client, token, trade_svc, service, saved
        finally:
            with server._sessions_lock:
                server._sessions.pop(token, None)


def _register(trade_svc, trade_id, lane_shift_value):
    card = TradeCard(
        trade_id=trade_id, league_id=LEAGUE, proposing_user_id=ME,
        target_user_id=PARTNER, target_username="partner",
        give_player_ids=list(GIVE), receive_player_ids=list(RECEIVE),
        mismatch_score=0.0, fairness_score=0.0, composite_score=0.0,
        lane_shift=lane_shift_value,
    )
    trade_svc._trade_cards[trade_id] = card
    return card


def _swipe(client, token, trade_id, decision, extra=None):
    body = {"trade_id": trade_id, "decision": decision, **(extra or {})}
    return client.post("/api/trades/swipe", data=json.dumps(body),
                       content_type="application/json",
                       headers={"X-Session-Token": token})


@pytest.mark.parametrize("shift,decision,mult", [
    (-0.125, "pass", _EXPLAINED),   # rebuilder passes the win-now vet
    (-0.125, "like", _DEFYING),     # …and the one who likes it anyway
    (+0.125, "like", _EXPLAINED),
    (+0.125, "pass", _DEFYING),
    (None,   "pass", 1.0),          # no window stamped
    (0.01,   "like", 1.0),          # sub-threshold
])
def test_route_applies_the_mult_to_memory_and_to_the_persisted_k(
        harness, shift, decision, mult):
    client, token, trade_svc, service, saved = harness
    _register(trade_svc, "t_route", shift)

    assert _swipe(client, token, "t_route", decision).status_code == 200

    base = rs._c("trade_k_like") if decision == "like" else rs._c("trade_k_pass")
    # In-memory signal.
    assert [k for _s, k in service._trade_swipes] == \
        [pytest.approx(base * mult)]
    # Persisted k_factor — _compute_elo replays these rows, so a mismatch
    # here would make a restart silently rewrite the user's board.
    assert saved.call_args.kwargs["k_factor"] == pytest.approx(base * mult)


def test_reconstructed_card_is_neutral(harness):
    """FB-46 client-echo rebuilds carry no shift — full baseline K, never a
    guessed one."""
    client, token, trade_svc, service, saved = harness
    res = _swipe(client, token, "stale_fit", "pass", extra={
        "give_player_ids": GIVE, "receive_player_ids": RECEIVE,
        "target_user_id": PARTNER, "target_username": "partner",
        "league_id": LEAGUE,
    })
    assert res.status_code == 200
    assert trade_svc._trade_cards["stale_fit"].lane_shift is None
    assert saved.call_args.kwargs["k_factor"] == \
        pytest.approx(rs._c("trade_k_pass"))
