"""BL-001 — `bakeoff_freeze_trade_k` re-enables trade-swipe learning.

Packet: docs/plans/org-bringup/leads/models-lead-launch.md §BL-001-packet.
Scope: docs/plans/swipe-learning/scope.md.

`bakeoff_runner.elo_freeze_mult` returns 0 only while `trade.bakeoff` is on
AND the knob is > 0. Default 1 is the freeze, byte-identical to before the
knob. Covers the gate (a-c), the three defaults agreeing (G-064), the real
swipe route's persisted `swipe_decisions.k_factor` (d), and forward-only
replay: a board rebuilt from `swipe_decisions` uses each row's STORED K, so
rows frozen at K = 0 stay inert after the knob flips (5b i).
"""
import inspect
import re
from unittest.mock import patch

import pytest

import backend.bakeoff_runner as bo
import backend.database as db_module
import backend.ranking_service as rs
import backend.trade_service as ts
from backend.database import load_swipe_decisions
from backend.ranking_service import Player, RankingService
from backend.tests.test_trade_decision_idempotency import (  # noqa: F401 (fixture)
    GIVE, ME, RECEIVE, ROUTE_TRADE, _post_swipe, route)

KNOB = "bakeoff_freeze_trade_k"


def _bakeoff(on: bool):
    return patch.object(bo, "bakeoff_enabled", lambda: on)


def _knob(value):
    return patch.dict(ts._cfg, {KNOB: value})


# ---------------------------------------------------------------------------
# The gate
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("fit_mult", [1.0, 0.4, 0.35])
def test_a_bakeoff_on_knob_1_freezes_exactly_as_before(fit_mult):
    """Flag-off identity of the knob: at its default the freeze is today's."""
    with _bakeoff(True), _knob(1.0):
        assert bo.elo_freeze_mult(fit_mult) == 0.0


@pytest.mark.parametrize("fit_mult", [1.0, 0.4, 0.35])
def test_b_bakeoff_on_knob_0_passes_fit_mult_through(fit_mult):
    with _bakeoff(True), _knob(0.0):
        assert bo.elo_freeze_mult(fit_mult) == fit_mult


@pytest.mark.parametrize("knob", [0.0, 1.0, 2.0])
def test_c_bakeoff_off_ignores_the_knob(knob):
    with _bakeoff(False), _knob(knob):
        assert bo.elo_freeze_mult(0.4) == 0.4
        assert bo.elo_freeze_mult(1.0) == 1.0


@pytest.mark.parametrize("stray", [0.5, 2.0, 1e-9])
def test_any_positive_value_freezes(stray):
    """A stray value stays conservative: only exactly 0 (or below) learns."""
    with _bakeoff(True), _knob(stray):
        assert bo.elo_freeze_mult(1.0) == 0.0


def test_three_defaults_agree_and_freeze():
    """G-064: the seed, `_DEFAULT_CFG` and the inline fallback are all 1.0."""
    seeded = {k: v for k, v, _ in db_module._MODEL_CONFIG_DEFAULTS}
    assert seeded[KNOB] == 1.0
    assert ts._DEFAULT_CFG[KNOB] == 1.0
    src = inspect.getsource(bo.elo_freeze_mult)
    assert re.search(r'_cfg\("bakeoff_freeze_trade_k", 1\.0\)', src), src
    # And the fallback really is what a missing DB row resolves to.
    without = {k: v for k, v in ts._cfg.items() if k != KNOB}
    with _bakeoff(True), patch.object(ts, "_cfg", without):
        assert bo.elo_freeze_mult(1.0) == 0.0


# ---------------------------------------------------------------------------
# (d) The real swipe route: persisted k_factor
# ---------------------------------------------------------------------------

def _card(token):
    import backend.server as server
    return server._sessions[token]["trade_svc"]._trade_cards[ROUTE_TRADE]


def _expected_like_k(lane_shift):
    fit = ts.fit_congruence_mult(lane_shift, "like")
    return rs._c("trade_k_like") * fit, fit


def test_d_route_knob_0_persists_trade_k_like_times_fit(route):
    client, token, service, _matcher = route
    _card(token).lane_shift = 0.5          # window-congruent like: fit-explained
    expected, fit = _expected_like_k(0.5)
    assert fit != 1.0 and expected > 0, "non-vacuous: fit_mult must bite"

    with _bakeoff(True), _knob(0.0):
        assert _post_swipe(client, token, "like").status_code == 200

    rows = load_swipe_decisions(user_id=ME, scoring_format="1qb_ppr")
    assert [(r["decision_type"], r["k_factor"]) for r in rows] == [("trade", expected)]
    assert [k for _s, k in service._trade_swipes] == [expected]


def test_d_route_knob_1_persists_zero(route):
    client, token, service, _matcher = route
    _card(token).lane_shift = 0.5

    with _bakeoff(True), _knob(1.0):
        assert _post_swipe(client, token, "like").status_code == 200

    rows = load_swipe_decisions(user_id=ME, scoring_format="1qb_ppr")
    assert [(r["decision_type"], r["k_factor"]) for r in rows] == [("trade", 0.0)]
    assert [k for _s, k in service._trade_swipes] == [0.0]


# ---------------------------------------------------------------------------
# 5b (i) Forward-only: stored K is what replays
# ---------------------------------------------------------------------------

def _board(rows):
    svc = RankingService(players=[
        Player(id=GIVE[0], name="Give", position="RB", team="AAA", age=25),
        Player(id=RECEIVE[0], name="Recv", position="RB", team="BBB", age=25),
    ])
    svc.replay_from_db(rows)
    return svc._compute_elo(svc._pool(None))


def test_frozen_rows_stay_inert_after_the_knob_flips(route):
    """A like written under the freeze, then the knob flips and a pass is
    written. The frozen row keeps K = 0, the board before the re-enable is
    unchanged, and only the post-flip pass moves anything."""
    client, token, _service, _matcher = route
    with _bakeoff(True), _knob(1.0):
        assert _post_swipe(client, token, "like").status_code == 200
    frozen = load_swipe_decisions(user_id=ME, scoring_format="1qb_ppr")
    board_at_flip = _board(frozen)
    assert board_at_flip == {GIVE[0]: 1500.0, RECEIVE[0]: 1500.0}

    with _bakeoff(True), _knob(0.0):
        assert _post_swipe(client, token, "pass").status_code == 200
    rows = load_swipe_decisions(user_id=ME, scoring_format="1qb_ppr")

    assert len(rows) == 2
    assert rows[0] == frozen[0], "the frozen row is never rewritten"
    assert rows[1]["k_factor"] == rs._c("trade_k_pass")
    # The board up to the re-enable time is identical when rebuilt later...
    assert _board(rows[:1]) == board_at_flip
    # ...and the full rebuild is exactly the post-flip pass on its own.
    assert _board(rows) == _board(rows[1:]) != board_at_flip


def test_replay_uses_stored_k_not_the_current_knobs():
    """`replay_from_db` reads each row's `k_factor`, never `trade_k_*`: a
    K = 0 row is inert and a K = 5 row moves by 5, whatever the config says."""
    def row(k):
        return {"winner_player_id": RECEIVE[0], "loser_player_id": GIVE[0],
                "decision_type": "trade", "k_factor": k,
                "created_at": "2026-09-01T00:00:00+00:00"}

    with patch.dict(rs._cfg, {"trade_k_like": 8.0, "trade_k_pass": 4.0}):
        assert _board([row(0.0)]) == {GIVE[0]: 1500.0, RECEIVE[0]: 1500.0}
        moved = _board([row(5.0)])
    assert moved[RECEIVE[0]] == pytest.approx(1500.0 + 5.0 * 0.5)
    assert moved[GIVE[0]] == pytest.approx(1500.0 - 5.0 * 0.5)
