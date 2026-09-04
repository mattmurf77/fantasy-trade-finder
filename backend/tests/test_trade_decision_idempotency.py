"""G-049 — `save_trade_decision` must not record a replayed swipe twice.

D-068 re-armed the mobile swipe guard so a card whose POST failed can be
re-swiped. That deliberately opened a path to a duplicate write: a swipe
that succeeded server-side but lost its response is re-sent, and the old
plain-INSERT recorded a second `trade_decisions` row, a second set of
`trade_swipes` rows, and replayed `trade_k_pass` **twice** through
`_compute_elo`.

The fix is a *windowed* idempotency guard in `save_trade_decision`, not a
unique constraint, because duplicate `(user_id, league_id, trade_id)` rows
are legitimate in two ways that a constraint would destroy:

  * the **#318 revive path** — like -> retract -> re-like writes a fresh
    row with `retracted_at` NULL, and both rows must survive;
  * a **genuine re-decision** of a re-served card (prod: 23 of them, none
    closer together than 147.7 s, against 40 true double-writes none wider
    apart than 0.200 s).

`save_trade_decision` now returns True/False so the caller can skip the Elo
write on a replay — `swipe_decisions` carries no trade/league identity, so
this is the only point in the write path where a replay is recognisable.

Covers: the suppressed duplicate, the preserved revive path, the preserved
genuine re-decision, single-counted Elo under the corrected caller
sequence, migration idempotency across two boots, and safety on a table
pre-loaded with the duplicates prod already contains.
"""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, select, text

import backend.database as db_module
from backend.database import (
    load_awaiting_trades,
    load_swipe_decisions,
    load_trade_decisions,
    metadata,
    retract_awaiting_likes,
    save_trade_decision,
    save_trade_swipes,
    trade_decisions_table,
)
from backend.ranking_service import Player, RankingService

LEAGUE = "league_idem"
ME = "user_me"
PARTNER = "user_partner"

GIVE = ["p_give_1"]
RECEIVE = ["p_recv_1"]
TRADE = "card_abc123"

TRADE_K_PASS = 4.0


@pytest.fixture()
def eng():
    e = create_engine("sqlite:///:memory:",
                      connect_args={"check_same_thread": False})
    metadata.create_all(e)
    with patch.object(db_module, "engine", e):
        yield e


def _save(decision="pass", *, trade_id=TRADE, give=GIVE, receive=RECEIVE,
          league_id=LEAGUE, user_id=ME):
    return save_trade_decision(
        user_id=user_id, league_id=league_id, trade_id=trade_id,
        give_player_ids=list(give), receive_player_ids=list(receive),
        decision=decision,
    )


def _rows(eng, **where):
    q = select(trade_decisions_table)
    with eng.connect() as conn:
        return [dict(r._mapping) for r in conn.execute(q).fetchall()]


def _age_all_rows(eng, seconds):
    """Backdate every trade_decisions row so the next write falls OUTSIDE
    the dedupe window without the test having to sleep."""
    old = (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat()
    with eng.begin() as conn:
        conn.execute(text("UPDATE trade_decisions SET created_at = :c"),
                     {"c": old})


# ---------------------------------------------------------------------------
# The bug itself
# ---------------------------------------------------------------------------

def test_replayed_pass_writes_one_row_and_reports_duplicate(eng):
    """The G-049 path: the same pass POSTed twice in quick succession."""
    assert _save("pass") is True
    assert _save("pass") is False, "replay must report itself as a duplicate"

    rows = _rows(eng)
    assert len(rows) == 1, f"expected one row, got {len(rows)}"
    assert rows[0]["decision"] == "pass"


def test_replayed_like_is_suppressed_too(eng):
    """Not pass-specific — a doubled like double-injects the partner's deck
    via load_recent_league_likes, which does not dedupe."""
    assert _save("like") is True
    assert _save("like") is False
    assert len(_rows(eng)) == 1


def test_elo_is_single_counted_under_the_corrected_caller_sequence(eng):
    """The harm G-049 actually names: `trade_k_pass` applied twice.

    Models what the route must do — apply the Elo signal only when
    `save_trade_decision` reports it wrote a row. Asserts on replayed Elo,
    not just row counts, so a regression in either layer is caught.
    """
    def swipe_once():
        """One POST of the same pass card, corrected-caller order."""
        wrote = _save("pass")
        if wrote:
            save_trade_swipes(
                user_id=ME, winner_ids=list(GIVE), loser_ids=list(RECEIVE),
                k_factor=TRADE_K_PASS, scoring_format="1qb_ppr",
            )
        return wrote

    assert swipe_once() is True
    assert swipe_once() is False, "second POST is a replay"

    swipes = load_swipe_decisions(user_id=ME, scoring_format="1qb_ppr")
    assert len(swipes) == 1, (
        f"replay leaked an Elo row: {len(swipes)} swipe_decisions rows")

    players = [
        Player(id=GIVE[0], name="Give", position="RB", team="AAA", age=25),
        Player(id=RECEIVE[0], name="Recv", position="RB", team="BBB", age=25),
    ]
    svc = RankingService(players=players)
    svc.replay_from_db(swipes)
    elo = svc._compute_elo(players)

    # Both seed at 1500 -> expected score 0.5 -> winner gains exactly k/2.
    single = 1500.0 + TRADE_K_PASS * 0.5
    assert elo[GIVE[0]] == pytest.approx(single), (
        f"expected one application of trade_k_pass ({single}), "
        f"got {elo[GIVE[0]]} — a doubled signal lands at "
        f"{1500.0 + TRADE_K_PASS}")


# ---------------------------------------------------------------------------
# The landmine: legitimate duplicates must survive
# ---------------------------------------------------------------------------

def test_revive_path_still_writes_two_rows_and_revives(eng):
    """#318 like -> retract -> re-like. THE regression this fix could ship.

    The retracted row must not suppress the re-like, both rows must remain,
    and the trade must come back on the Awaiting list.
    """
    with eng.begin() as conn:
        for uid, roster in ((ME, GIVE), (PARTNER, RECEIVE)):
            conn.execute(text(
                "INSERT INTO league_members "
                "(league_id, user_id, username, roster_data, updated_at) "
                "VALUES (:l, :u, :u, :r, :t)"
            ), {"l": LEAGUE, "u": uid, "r": json.dumps(list(roster)),
                "t": "2026-08-18T00:00:00"})

    assert _save("like") is True
    assert len(load_awaiting_trades(ME)) == 1

    assert retract_awaiting_likes(ME, LEAGUE, list(GIVE), list(RECEIVE)) == 1
    assert load_awaiting_trades(ME) == [], "retract should empty Awaiting"

    # The re-like happens immediately — INSIDE the dedupe window — so this
    # pins that the guard keys on `retracted_at IS NULL` and not on time
    # alone.
    assert _save("like") is True, "revive must not be suppressed as a replay"

    rows = _rows(eng)
    assert len(rows) == 2, f"revive path must keep both rows, got {len(rows)}"
    assert [r["retracted_at"] is None for r in rows] == [False, True]
    assert len(load_awaiting_trades(ME)) == 1, "re-like must revive Awaiting"


def test_genuine_redecision_outside_the_window_is_written(eng):
    """Prod's 23 legitimate re-decisions sat 147.7 s+ apart. A card re-served
    by a deck regeneration and passed again is a real decision."""
    assert _save("pass") is True
    _age_all_rows(eng, seconds=300)
    assert _save("pass") is True, "a re-decision past the window must persist"
    assert len(_rows(eng)) == 2


def test_flipping_the_decision_is_never_suppressed(eng):
    """like -> pass on the same card is a change of mind, not a replay,
    even back to back."""
    assert _save("like") is True
    assert _save("pass") is True
    assert {r["decision"] for r in _rows(eng)} == {"like", "pass"}


def test_same_trade_id_with_a_different_payload_is_written(eng):
    """An FB-46 client-echo reconstruction can reuse a trade_id with a
    different card; the payload check keeps that a distinct decision."""
    assert _save("pass") is True
    assert _save("pass", receive=["p_recv_2"]) is True
    assert len(_rows(eng)) == 2


def test_other_users_and_leagues_are_not_cross_suppressed(eng):
    assert _save("pass") is True
    assert _save("pass", user_id="user_other") is True
    assert _save("pass", league_id="league_other") is True
    assert _save("pass", trade_id="card_other") is True
    assert len(_rows(eng)) == 4


def test_guard_fails_open_on_an_unparseable_timestamp(eng):
    """Losing a real decision is strictly worse than keeping a duplicate."""
    assert _save("pass") is True
    with eng.begin() as conn:
        conn.execute(text("UPDATE trade_decisions SET created_at = 'garbage'"))
    assert _save("pass") is True, "unparseable created_at must not suppress"
    assert len(_rows(eng)) == 2


def test_naive_legacy_timestamp_is_still_deduped(eng):
    """Older rows were written without an offset; those must not slip
    through the guard as 'unparseable'."""
    assert _save("pass") is True
    naive = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    with eng.begin() as conn:
        conn.execute(text("UPDATE trade_decisions SET created_at = :c"),
                     {"c": naive})
    assert _save("pass") is False
    assert len(_rows(eng)) == 1


# ---------------------------------------------------------------------------
# Safety on the live table + migration
# ---------------------------------------------------------------------------

def _preload_prod_shaped_duplicates(eng):
    """The 63 duplicate rows prod already carries, in miniature: a
    sub-second double-write plus a legitimate re-decision, all live."""
    now = datetime.now(timezone.utc)
    stamps = [now - timedelta(seconds=s) for s in (400.0, 399.8, 200.0)]
    with eng.begin() as conn:
        for ts in stamps:
            conn.execute(text(
                "INSERT INTO trade_decisions "
                "(user_id, league_id, trade_id, give_player_ids, "
                " receive_player_ids, decision, created_at, retracted_at) "
                "VALUES (:u, :l, :t, :g, :r, 'pass', :c, NULL)"
            ), {"u": ME, "l": LEAGUE, "t": TRADE, "g": json.dumps(GIVE),
                "r": json.dumps(RECEIVE), "c": ts.isoformat()})


def test_existing_duplicates_are_left_alone_and_do_not_block_new_writes(eng):
    """No backfill, no constraint: pre-existing duplicates stay readable and
    the next legitimate decision still lands. A unique index could not even
    be created against this table."""
    _preload_prod_shaped_duplicates(eng)
    assert len(_rows(eng)) == 3

    # Aged out of the window -> a fresh decision is not mistaken for a replay.
    assert _save("pass") is True
    assert len(_rows(eng)) == 4
    assert len(load_trade_decisions(ME, league_id=LEAGUE)) == 4

    # ...and the guard now suppresses the replay of THAT write.
    assert _save("pass") is False
    assert len(_rows(eng)) == 4


def test_migrate_db_is_idempotent_across_two_boots_with_duplicates_present(eng):
    """`_migrate_db()` runs on every boot. This fix adds no DDL, so the
    contract to pin is that boot stays clean and non-destructive against a
    table that holds the duplicates prod has."""
    _preload_prod_shaped_duplicates(eng)
    before = _rows(eng)

    db_module._migrate_db()
    first = _rows(eng)
    db_module._migrate_db()
    second = _rows(eng)

    assert first == before, "first boot must not rewrite or drop rows"
    assert second == first, "second boot must be a no-op"

    # Boot did not install anything that rejects the duplicates.
    _age_all_rows(eng, seconds=300)
    assert _save("pass") is True
    assert len(_rows(eng)) == len(before) + 1


# ---------------------------------------------------------------------------
# Route pins — the contract above is only worth anything if server.py obeys it
# ---------------------------------------------------------------------------
# The Elo test above defines its own `swipe_once()` and so proves the CONTRACT,
# not the call sites. Without these two pins, deleting the `wrote_decision`
# gate in server.py reintroduces the doubled `trade_k_pass` with every test
# still green — verified by sabotage during review. Same `inspect.getsource`
# idiom as test_pass_cooldown.py::test_route_gates_the_bind_on_pass_only.

def _swipe_gate_src(fn) -> str:
    import inspect
    return inspect.getsource(fn)


def test_swipe_trade_route_gates_the_elo_write_on_the_decision_write():
    """`swipe_trade` must skip save_trade_swipes when the decision was a
    replay — that swipe row is the one `_compute_elo` replays."""
    import backend.server as server
    src = _swipe_gate_src(server.swipe_trade)
    assert "wrote_decision = save_trade_decision(" in src, \
        "the route must capture save_trade_decision's replay verdict"
    gate = src.split("wrote_decision = save_trade_decision(", 1)[1]
    assert "if wrote_decision:" in gate.split("save_trade_swipes(", 1)[0], \
        "save_trade_swipes must sit under the `if wrote_decision:` gate"


def test_reasoned_pass_route_gates_the_elo_write_on_the_decision_write():
    """Same pin for the decline-reason pass path (`_apply_reasoned_pass`),
    which has its own save_trade_decision → save_trade_swipes pair."""
    import backend.server as server
    src = _swipe_gate_src(server._apply_reasoned_pass)
    assert "wrote_decision = save_trade_decision(" in src, \
        "the reasoned-pass path must capture the replay verdict too"
    assert "if elo and wrote_decision:" in src, \
        "its Elo write must require BOTH the elo flag and a real decision write"


def test_check_for_match_is_not_gated_on_the_replay_verdict():
    """A replayed LIKE must still be able to surface a mutual match — the
    dedupe suppresses a redundant write, never match detection.

    The route now calls `find_mirror_like` rather than `check_for_match`
    (personal-market policy, 2026-09-04): same matching logic, but it returns
    the counterparty's row so the match can record both like times and both
    impressions instead of pretending the two likes were simultaneous.
    `check_for_match` is a thin bool wrapper over it, so there is still one
    implementation. Only the name this test watches moved; the guarantee is
    unchanged."""
    import backend.server as server
    src = _swipe_gate_src(server.swipe_trade)
    assert "find_mirror_like" in src, "sanity: the route still checks for a match"
    for line in src.splitlines():
        if "find_mirror_like" in line and "def " not in line:
            assert "wrote_decision" not in line, \
                "mirror detection must not be gated on the replay verdict"


# ---------------------------------------------------------------------------
# Route level — the real POST, twice, against a real database
# ---------------------------------------------------------------------------
# The pins above match source text and the Elo test defines its own caller.
# Neither actually POSTs. This section drives `/api/trades/swipe` through the
# Flask test client with the REAL `save_trade_swipes` (only the notification
# side effects are stubbed), so the thing being counted is rows the route
# genuinely wrote — the same rows `_compute_elo` replays.

ROUTE_LEAGUE = "league_idem_route"
ROUTE_TRADE  = "card_route_replay"


@pytest.fixture()
def route():
    """Flask test client with one session wired to an in-memory DB.

    `save_trade_swipes` is deliberately NOT mocked — the assertion is on
    `swipe_decisions` rows, and mocking the writer would only re-test the
    call count the source pins already cover.
    """
    from unittest.mock import MagicMock

    import backend.server as server
    from backend.trade_service import League, LeagueMember, TradeCard, TradeService

    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False})
    metadata.create_all(engine)

    players = [
        Player(id=GIVE[0], name="Give", position="RB", team="AAA", age=25),
        Player(id=RECEIVE[0], name="Recv", position="RB", team="BBB", age=25),
    ]
    service   = RankingService(players=players)
    trade_svc = TradeService(players={p.id: p for p in players})
    trade_svc._trade_cards[ROUTE_TRADE] = TradeCard(
        trade_id           = ROUTE_TRADE,
        league_id          = ROUTE_LEAGUE,
        proposing_user_id  = ME,
        target_user_id     = PARTNER,
        target_username    = "partner",
        give_player_ids    = list(GIVE),
        receive_player_ids = list(RECEIVE),
        mismatch_score     = 0.0,
        fairness_score     = 0.0,
        composite_score    = 0.0,
    )

    token = "test-token-g049-route"
    sess = {
        "user_id":       ME,
        "league":        League(league_id=ROUTE_LEAGUE, name="Idem Route",
                                platform="sleeper", members=[
                                    LeagueMember(user_id=ME, username="me",
                                                 roster=[], elo_ratings={}),
                                    LeagueMember(user_id=PARTNER, username="partner",
                                                 roster=[], elo_ratings={}),
                                ]),
        "players":       players,
        "services":      {"1qb_ppr": service},
        "service":       service,
        "trade_svcs":    {"1qb_ppr": trade_svc},
        "trade_svc":     trade_svc,
        "active_format": "1qb_ppr",
        "last_active":   0.0,
    }
    server.app.config["TESTING"] = True
    client  = server.app.test_client()
    # `find_mirror_like` returns the counterparty's row or None (see
    # test_check_for_match_is_not_gated_on_the_replay_verdict) — None is the
    # "no mirror" answer the old bool False used to be.
    matcher = MagicMock(return_value=None)

    with patch.object(db_module, "engine", engine), \
         patch.object(server, "record_event", MagicMock()), \
         patch.object(server, "create_notification", MagicMock()), \
         patch.object(server, "find_mirror_like", matcher):
        with server._sessions_lock:
            server._sessions[token] = sess
        try:
            yield client, token, service, matcher
        finally:
            with server._sessions_lock:
                server._sessions.pop(token, None)


def _post_swipe(client, token, decision, trade_id=ROUTE_TRADE):
    return client.post(
        "/api/trades/swipe",
        data=json.dumps({"trade_id": trade_id, "decision": decision}),
        content_type="application/json",
        headers={"X-Session-Token": token},
    )


def test_re_posted_swipe_writes_exactly_one_set_of_swipe_decisions(route):
    """THE regression test for G-049: the same pass POSTed twice.

    One give x one receive = exactly one `swipe_decisions` row per accepted
    swipe, so "one set" is countable: two rows here means `trade_k_pass`
    lands twice on the next `replay_from_db`.
    """
    client, token, _service, _matcher = route

    # The bake-off's Elo freeze (`elo_freeze_mult` -> 0.0 while
    # `trade.bakeoff` is live) zeroes the stored k_factor, which is the very
    # quantity this test measures a double-write with. Pin it off so the
    # instrument reads.
    import backend.bakeoff_runner as _bo
    with patch.object(_bo, "bakeoff_enabled", lambda: False):
        assert _post_swipe(client, token, "pass").status_code == 200
        assert _post_swipe(client, token, "pass").status_code == 200

    swipes = load_swipe_decisions(user_id=ME, scoring_format="1qb_ppr")
    assert len(swipes) == 1, (
        f"the replayed POST leaked an Elo row: {len(swipes)} swipe_decisions "
        f"rows for one card")
    assert len(load_trade_decisions(user_id=ME, league_id=ROUTE_LEAGUE)) == 1

    # And the persisted state a restart would reload is single-counted.
    svc = RankingService(players=[
        Player(id=GIVE[0], name="Give", position="RB", team="AAA", age=25),
        Player(id=RECEIVE[0], name="Recv", position="RB", team="BBB", age=25),
    ])
    svc.replay_from_db(swipes)
    elo = svc._compute_elo(svc._pool(None))
    assert elo[GIVE[0]] == pytest.approx(1500.0 + TRADE_K_PASS * 0.5), \
        "restart replay should show one application of trade_k_pass"


def test_route_replay_leaves_the_in_session_signal_doubled(route):
    """D-073's accepted residual, pinned so it is a decision and not a leak.

    `record_trade_signal` fires BEFORE the DB write and is deliberately not
    gated on the replay verdict: the in-memory list is derived state,
    rebuilt from `swipe_decisions` by `replay_from_db` at every
    session_init, while gating it would make an in-session board movement
    depend on the DB being reachable. If this ever changes to 1, the
    residual documented in D-073 / G-049 is gone and both should be updated.
    """
    client, token, service, _matcher = route

    _post_swipe(client, token, "pass")
    _post_swipe(client, token, "pass")

    assert len(service._trade_swipes) == 2, (
        "in-memory signal is expected to double on a replay; see D-073")


def test_route_replayed_like_still_runs_match_detection(route):
    """Suppressing match detection on a re-sent like would be a worse bug
    than the doubled Elo. Both POSTs must reach mirror detection."""
    client, token, _service, matcher = route

    assert _post_swipe(client, token, "like").status_code == 200
    assert _post_swipe(client, token, "like").status_code == 200

    assert len(load_swipe_decisions(user_id=ME, scoring_format="1qb_ppr")) == 1
    assert matcher.call_count == 2, (
        "mirror detection must run on the replay too — the guard suppresses a "
        "redundant write, never match detection")
