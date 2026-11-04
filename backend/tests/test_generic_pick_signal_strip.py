"""A2: generic pick rungs never take a trade Elo signal.

Plan: docs/plans/generic-pick-signal-strip.md (models-eng finding A2,
head-eng ruling: strip at the signal layer, not per route).

The 12 `generic_pick_{1..4}_{early,mid,late}` rungs are in every user's
RankingService pool, so a client-echoed card carrying one used to move that
user's generic-pick Elo, live and on replay. The strip lives in ONE helper,
`pick_values.strip_generic_pick_pair`, applied in `record_trade_signal`,
`record_disposition_signal` and `save_trade_swipes`.

Every route test runs the same request twice, in two fresh harnesses: once
with the helper replaced by a pass-through (the pre-fix behavior) and once
with the real helper. That pins three things at once:

  * the response (status and body) is IDENTICAL, so no client sees a change;
  * the fix removes exactly the generic pairs (live `_trade_swipes` and
    persisted `swipe_decisions`), keeps every ordinary pair at the same K,
    and leaves `trade_decisions` (the card record) untouched;
  * the pre-fix run really did leak the generic signal, so no test passes
    vacuously.

Replay is forward-only (models-lead 5b(i)): historical generic rows keep
replaying exactly as before. The last test pins that.

Harness follows test_calc_trade_queue.py / test_decline_reasons.py /
test_disposition_route.py: Flask test client, a real in-memory session,
an isolated in-memory SQLite, and `save_trade_swipes` REAL so rows can be
counted. Feature flags are pinned to DEFAULT_FLAGS (bake-off off, so the
trade-K freeze is off and K is the full configured value).
"""

import json
from contextlib import ExitStack, contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, insert, select

import backend.database as db_module
import backend.feature_flags as ff
import backend.pick_values as pick_values
import backend.ranking_service as rs_module
import backend.server as server
from backend.database import (
    metadata,
    swipe_decisions_table,
    trade_decisions_table,
    trade_matches_table,
    trade_pass_reasons_table,
)
from backend.ranking_service import Player, RankingService
from backend.trade_service import League, LeagueMember, TradeService

ME = "user_me"
OPP = "user_opp"
LEAGUE = "league_a2"
TOKEN = "test-token-a2"
GP = "generic_pick_1_mid"
GP2 = "generic_pick_2_early"
GENERICS = (GP, GP2)
PLAYERS = ("g1", "g2", "r1", "r2")

# (give, receive) from the caller's side.
ORDINARY = (["g1"], ["r1"])
MIXED = (["g1", GP], ["r1", GP2])        # each side keeps one player
GENERIC_ONLY = ([GP], ["r1"])            # give side empties -> skip the pair


def _unstripped(winner_ids, loser_ids, *, site=""):
    """The pre-fix behavior: every id passes through."""
    return list(winner_ids), list(loser_ids)


def _pool():
    players = [Player(id=pid, name=pid.upper(), position="RB", team="AAA", age=25)
               for pid in PLAYERS]
    players += [Player(id=gid, name=gid, position="RB", team="PICK", age=0,
                       pick_value=75.0) for gid in GENERICS]
    return players


def _has_generic(*ids) -> bool:
    return any(pick_values.parse_generic_pick_id(i) is not None for i in ids)


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------

@contextmanager
def _harness(*, strip: bool):
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False})
    metadata.create_all(engine)

    pool = _pool()
    service = RankingService(players=list(pool))
    trade_svc = TradeService(players={p.id: p for p in pool})
    league = League(
        league_id=LEAGUE, name="A2 League", platform="sleeper",
        members=[
            LeagueMember(user_id=ME, username="me", roster=["g1", "g2"], elo_ratings={}),
            LeagueMember(user_id=OPP, username="opp", roster=["r1", "r2"], elo_ratings={}),
        ],
    )
    trade_svc.add_league(league)
    sess = {
        "verified":      True,
        "user_id":       ME,
        "username":      "me",
        "league":        league,
        "players":       pool,
        "user_roster":   ["g1", "g2"],
        "services":      {"1qb_ppr": service},
        "service":       service,
        "trade_svcs":    {"1qb_ppr": trade_svc},
        "trade_svc":     trade_svc,
        "active_format": "1qb_ppr",
        "last_active":   0.0,
    }

    server.app.config["TESTING"] = True
    old_flags = ff._flags_cache
    ff._flags_cache = {**ff.DEFAULT_FLAGS, "calc.merged_layout": True}
    with ExitStack() as stack:
        stack.enter_context(patch.object(db_module, "engine", engine))
        for name in ("record_event", "create_notification", "_send_typed_push"):
            stack.enter_context(patch.object(server, name, MagicMock()))
        stack.enter_context(patch.object(server, "load_matches",
                                         MagicMock(return_value=[])))
        stack.enter_context(patch.object(server, "_decline_reasons_enabled",
                                         lambda: True))
        if not strip:
            stack.enter_context(patch.object(pick_values, "strip_generic_pick_pair",
                                             _unstripped))
        with server._sessions_lock:
            server._sessions[TOKEN] = sess
        try:
            yield SimpleNamespace(client=server.app.test_client(),
                                  engine=engine, service=service)
        finally:
            with server._sessions_lock:
                server._sessions.pop(TOKEN, None)
            ff._flags_cache = old_flags


def _post(h, path, body):
    return h.client.post(path, data=json.dumps(body),
                         content_type="application/json",
                         headers={"X-Session-Token": TOKEN})


# ---------------------------------------------------------------------------
# The four routes, each driven with client-sent give / receive ids
# ---------------------------------------------------------------------------

def _queue(h, give, recv):
    """The calculator's check cell: a like, built from client ids."""
    return _post(h, "/api/trades/queue", {
        "league_id": LEAGUE, "opponent_user_id": OPP,
        "give_player_ids": give, "receive_player_ids": recv,
    })


def _swipe(h, give, recv):
    """A pass on a card the server lost: the FB-46 rebuild from client ids."""
    return _post(h, "/api/trades/swipe", {
        "trade_id": "swipe_a2", "decision": "pass", "league_id": LEAGUE,
        "give_player_ids": give, "receive_player_ids": recv,
        "target_user_id": OPP, "target_username": "opp",
    })


def _pass_reason(h, give, recv):
    """A value_giving reason on a lost card: the FB-46 fallback, then the
    `_apply_reasoned_pass_elo_only` write (save_trade_swipes with a key)."""
    return _post(h, "/api/trades/pass-reason", {
        "trade_id": "reason_a2", "detail": "value_giving", "league_id": LEAGUE,
        "give_player_ids": give, "receive_player_ids": recv,
        "target_user_id": OPP,
    })


def _disposition(h, give, recv):
    """The partner (user_a) already accepted the mirror; my accept decides
    the match, so both users' disposition signals fire."""
    with h.engine.begin() as conn:
        match_id = conn.execute(insert(trade_matches_table).values(
            league_id=LEAGUE, user_a_id=OPP, user_b_id=ME,
            user_a_give=json.dumps(recv), user_a_receive=json.dumps(give),
            matched_at="2026-10-01T00:00:00", status="pending",
            user_a_decision="accept",
        )).inserted_primary_key[0]
    return _post(h, f"/api/trades/matches/{match_id}/disposition",
                 {"decision": "accept"})


ROUTES = {
    "queue":       (_queue, "trade_k_like"),
    "swipe":       (_swipe, "trade_k_pass"),
    "pass_reason": (_pass_reason, "trade_k_pass"),
    "disposition": (_disposition, None),       # db_module._K_ACCEPT()
}


def _run(route, give, recv, *, strip):
    driver, k_key = ROUTES[route]
    with _harness(strip=strip) as h:
        res = driver(h, give, recv)
        expected_k = (rs_module._c(k_key) if k_key else db_module._K_ACCEPT())
        with h.engine.connect() as conn:
            rows = [(r.user_id, r.winner_player_id, r.loser_player_id,
                     r.decision_type, r.k_factor)
                    for r in conn.execute(select(swipe_decisions_table)
                                          .order_by(swipe_decisions_table.c.id))]
            decisions = [(r.user_id, r.trade_id, r.decision,
                          r.give_player_ids, r.receive_player_ids)
                         for r in conn.execute(select(trade_decisions_table))]
            claims = [r.elo_signal_at is not None
                      for r in conn.execute(select(trade_pass_reasons_table))]
        live = [(s.winner_id, s.loser_id, k) for s, k in h.service._trade_swipes]
        board = h.service._compute_elo(h.service._pool(None))
        body = res.get_json()
        if isinstance(body, dict) and "expires_at" in body:
            # The swipe response's card stamp is wall-clock (card build time),
            # so two runs can never match on it. Present in both, compared out.
            body["expires_at"] = "<wall-clock>"
        return SimpleNamespace(status=res.status_code, body=body,
                               live=live, rows=rows, decisions=decisions,
                               claims=claims, board=board, k=expected_k)


def _assert_same_response_and_untouched_records(before, after):
    assert before.status == after.status == 200, (before.body, after.body)
    assert after.body == before.body
    # Cards / save_trade_decision rows and the pass-reason claim are unchanged.
    assert after.decisions == before.decisions
    assert after.claims == before.claims


def _assert_no_generic_signal(after):
    assert not any(_has_generic(w, l) for w, l, _k in after.live)
    assert not any(_has_generic(w, l) for _u, w, l, _t, _k in after.rows)
    for gid in GENERICS:
        assert after.board[gid] == RankingService.ELO_INITIAL


# ---------------------------------------------------------------------------
# Route level
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("route", ROUTES)
def test_generic_ids_are_stripped_and_the_response_is_identical(route):
    """Mixed sides: the generic pairs go, the player pair stays at the same K."""
    before = _run(route, *MIXED, strip=False)
    after = _run(route, *MIXED, strip=True)

    _assert_same_response_and_untouched_records(before, after)
    # The pre-fix path really leaked the rung, live and persisted.
    assert any(_has_generic(w, l) for w, l, _k in before.live)
    assert any(_has_generic(w, l) for _u, w, l, _t, _k in before.rows)

    _assert_no_generic_signal(after)
    assert after.live == [x for x in before.live if not _has_generic(x[0], x[1])]
    assert after.rows == [x for x in before.rows if not _has_generic(x[1], x[2])]
    assert after.live and after.rows
    assert {k for *_ids, k in after.live} == {after.k}
    assert {r[-1] for r in after.rows} == {after.k}


@pytest.mark.parametrize("route", ROUTES)
def test_ordinary_pairs_still_record_and_persist_at_unchanged_k(route):
    before = _run(route, *ORDINARY, strip=False)
    after = _run(route, *ORDINARY, strip=True)

    _assert_same_response_and_untouched_records(before, after)
    assert after.live == before.live and after.live
    assert after.rows == before.rows and after.rows
    assert {k for *_ids, k in after.live} == {after.k}
    assert {r[-1] for r in after.rows} == {after.k}
    assert after.board == before.board


@pytest.mark.parametrize("route", ROUTES)
def test_a_generic_only_side_records_nothing(route):
    """[generic] for [player]: the stripped side is empty, so the pair is
    skipped whole. Never a one-sided signal, never a row."""
    before = _run(route, *GENERIC_ONLY, strip=False)
    after = _run(route, *GENERIC_ONLY, strip=True)

    _assert_same_response_and_untouched_records(before, after)
    assert before.live and before.rows                 # it used to leak
    assert after.live == [] and after.rows == []
    _assert_no_generic_signal(after)


def test_pass_reason_still_claims_and_reports_elo_written_when_the_pair_is_skipped():
    """The save_trade_swipes return-value choice, pinned on its one reader:
    `_apply_reasoned_pass_elo_only` does `if wrote:` / `return bool(wrote)`.
    A skipped pair still claims the reason and returns True, so
    `elo_written` reads exactly as it did before the fix."""
    before = _run("pass_reason", *GENERIC_ONLY, strip=False)
    after = _run("pass_reason", *GENERIC_ONLY, strip=True)
    assert before.body["elo_written"] is True
    assert after.body["elo_written"] is True
    assert after.claims == before.claims == [True]


# ---------------------------------------------------------------------------
# The helper and save_trade_swipes directly
# ---------------------------------------------------------------------------

def test_helper_keeps_players_and_skips_an_emptied_pair():
    strip = pick_values.strip_generic_pick_pair
    assert strip(["r1", GP2], ["g1", GP]) == (["r1"], ["g1"])
    assert strip(["r1"], [GP]) == ([], [])
    assert strip([GP, GP2], ["g1"]) == ([], [])
    assert strip(["r1", "r2"], ["g1"]) == (["r1", "r2"], ["g1"])
    # Only ids parse_generic_pick_id accepts are generic; lookalikes are not.
    assert strip(["generic_pick_9_early"], ["generic_pick_x"]) == (
        ["generic_pick_9_early"], ["generic_pick_x"])


def test_helper_counts_and_logs_only_when_it_drops(caplog):
    site = "test_site_a2"
    pick_values.GENERIC_PICK_STRIP_COUNTS.pop(site, None)
    with caplog.at_level("INFO", logger=pick_values.__name__):
        pick_values.strip_generic_pick_pair(["r1"], ["g1"], site=site)
        assert site not in pick_values.GENERIC_PICK_STRIP_COUNTS
        pick_values.strip_generic_pick_pair(["r1"], [GP], site=site)
    assert pick_values.GENERIC_PICK_STRIP_COUNTS[site] == 1
    assert [r for r in caplog.records if site in r.getMessage()]


def test_save_trade_swipes_ordinary_return_is_unchanged_for_a_skipped_pair():
    """No pass_reason_key: None, whether rows were written or not (as before)."""
    engine = create_engine("sqlite:///:memory:")
    metadata.create_all(engine)
    with patch.object(db_module, "engine", engine):
        assert db_module.save_trade_swipes(ME, ["r1"], [GP], 8.0) is None
        assert db_module.save_trade_swipes(ME, ["r1"], ["g1"], 8.0) is None
        with engine.connect() as conn:
            rows = conn.execute(select(swipe_decisions_table)).fetchall()
    assert [(r.winner_player_id, r.loser_player_id) for r in rows] == [("r1", "g1")]


# ---------------------------------------------------------------------------
# Replay is forward-only (models-lead 5b(i)); correcting it is BL-003
# ---------------------------------------------------------------------------

def test_replay_is_forward_only_a_historical_generic_row_still_moves_the_board():
    """A generic trade row persisted BEFORE this fix still replays exactly as
    it did: counted, and moving the rung and its partner by the plain Elo
    update. The fix touches the write paths, never `replay_from_db`."""
    seeds = {"g1": 1600.0, "g2": 1550.0, "r1": 1500.0, "r2": 1450.0,
             GP: 1560.0, GP2: 1540.0}
    k = rs_module._c("trade_k_like")
    history = [{"winner_player_id": GP, "loser_player_id": "r1",
                "decision_type": "trade", "k_factor": k,
                "created_at": "2026-08-01T00:00:00+00:00"}]

    svc = RankingService(players=_pool(), seed_ratings=dict(seeds))
    assert svc.replay_from_db(history) == 1
    board = svc._compute_elo(svc._pool(None))

    ea = 1.0 / (1.0 + 10 ** ((seeds["r1"] - seeds[GP]) / 400.0))
    assert board[GP] == pytest.approx(seeds[GP] + k * (1.0 - ea))
    assert board["r1"] == pytest.approx(seeds["r1"] - k * (1.0 - ea))
    assert board[GP] != seeds[GP] and board["r1"] != seeds["r1"]
