"""deck_i1_check: the S0 C-a readout's data path (analytics-lead's pre-grant,
2026-10-26 §2 (a); models-lead's R2.4 addendum (ii) and (iv)).

Pins: one server-fired NON_INTENT row per serve with newly served cards that
ran the I-1 check, each card counted once per job (repeat polls record
nothing; a replace serve and a legacy body after pages record only their new
cards; #419 QA P3); none at trade_i1_mode 0; the exact prop keys, with no
league id or raw job id; the give/receive x player/pick split with a
both-sides card counted once in `dropped_cards`; the write is non-touching,
owned by the viewer, and never on the request thread, but on one worker with a
bounded queue; the page-store serve's emit; the drain; the lenient label.
Harness: a hand-built complete job served through /api/trades/status over a
file-backed SQLite DB (the event is written on a background thread, and an
in-memory SQLite DB is per thread).
"""
import collections
import contextlib
import types
import hashlib
import json
import queue
import threading
import time

import pytest
from sqlalchemy import create_engine, delete, insert, select

import backend.database as db_module
import backend.server as server
from backend import analytics_queries, analytics_taxonomy
from backend import trade_service as ts
from backend import user_data_lifecycle
from backend.database import (draft_picks_table, league_members_table, metadata,
                              user_events_table, users_table)

UID = "user_i1ev"
OPP = "user_i1ev_opp"
THIRD = "user_i1ev_third"
LEAGUE = "league_i1ev"          # not a Sleeper id: the floor kick is a no-op
TOKEN = "sess-i1ev-tok"
JOB = "job-i1ev"
KEY = (UID, LEAGUE, "1qb_ppr")
PK_MINE, PK_OPP = f"{LEAGUE}_2027_1_1", f"{LEAGUE}_2027_1_2"
PK_GONE_FROM_ME, PK_GONE_FROM_OPP = f"{LEAGUE}_2027_2_1", f"{LEAGUE}_2027_2_2"

# Stored truth: g1 moved to OPP, r1 to THIRD, one pick each from me and OPP to THIRD.
STORED_ROSTERS = {UID: ["g2"], OPP: ["r2", "g1"], THIRD: ["r1"]}
STORED_PICKS = {PK_MINE: UID, PK_OPP: OPP, PK_GONE_FROM_ME: THIRD, PK_GONE_FROM_OPP: THIRD}
CARDS = {
    "ok-players":        (["g2"], ["r2"]),
    "ok-picks":          ([PK_MINE], [PK_OPP]),
    "moved-give-player": (["g1"], ["r2"]),
    "moved-recv-player": (["g2"], ["r1"]),
    "moved-give-pick":   ([PK_GONE_FROM_ME], ["r2"]),
    "moved-recv-pick":   (["g2"], [PK_GONE_FROM_OPP]),
    "moved-both":        (["g1"], ["r1"]),
}
PROPS = {"job_key", "mode", "status", "outcome", "age_bucket", "cards", "kept",
         "dropped_cards", "dropped_give_player", "dropped_give_pick",
         "dropped_receive_player", "dropped_receive_pick",
         "unchecked_generic", "unchecked_pick_owner"}


def _card(trade_id, give, receive):
    return {"trade_id": trade_id, "league_id": LEAGUE, "target_user_id": OPP,
            "target_username": "opp", "give": [{"id": a} for a in give],
            "receive": [{"id": a} for a in receive], "decision": None,
            "preserve_server_order": True}


@pytest.fixture()
def env(monkeypatch, tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/i1ev.db",
                           connect_args={"check_same_thread": False})
    metadata.create_all(engine)
    monkeypatch.setattr(db_module, "engine", engine)
    monkeypatch.setitem(ts._cfg, "trade_i1_mode", 2.0)
    monkeypatch.setattr(server, "_i1_events_seen", collections.OrderedDict())
    monkeypatch.setattr(server, "_i1_events_counted", 0)
    with engine.begin() as conn:
        for uid, roster in STORED_ROSTERS.items():
            conn.execute(insert(league_members_table).values(
                league_id=LEAGUE, user_id=uid, roster_data=json.dumps(roster)))
        for pick_id, owner in STORED_PICKS.items():
            conn.execute(insert(draft_picks_table).values(
                pick_id=pick_id, league_id=LEAGUE, season=2027, round=1,
                owner_user_id=owner, original_roster_id="1"))
        conn.execute(insert(users_table).values(sleeper_user_id=UID, username="me",
                                                last_active_at="2026-01-01", events_count=7))
    job = {"job_id": JOB, "key": KEY, "status": "complete", "opponents_done": 2,
           "opponents_total": 2, "error": None, "league_user_id": UID,
           "cards": [_card(tid, give, recv) for tid, (give, recv) in CARDS.items()]}
    with server._trade_jobs_lock:
        server._trade_jobs[JOB] = job
    with server._sessions_lock:
        server._sessions[TOKEN] = {"user_id": UID, "verified": True, "last_active": 0.0}
    try:
        yield engine, job
    finally:
        _drain()
        with server._sessions_lock:
            server._sessions.pop(TOKEN, None)
        with server._trade_jobs_lock:
            server._trade_jobs.pop(JOB, None)


def _drain():
    assert server._drain_deck_i1_checks(5)


def _status(query=""):
    resp = server.app.test_client().get(f"/api/trades/status?job_id={JOB}{query}",
                                        headers={"X-Session-Token": TOKEN})
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()


def _events(engine):
    _drain()
    with engine.connect() as conn:
        rows = conn.execute(select(user_events_table).where(
            user_events_table.c.event_type == "deck_i1_check")
            .order_by(user_events_table.c.id)).fetchall()
    return [dict(r._mapping) for r in rows]


def test_props_are_exact_and_carry_no_league_or_job_id(env):
    engine, _ = env
    _status()
    (row,) = _events(engine)
    props = json.loads(row["props"])
    assert set(props) == PROPS
    assert props["job_key"] == hashlib.sha256(JOB.encode()).hexdigest()[:12]
    assert LEAGUE not in row["props"] and JOB not in row["props"]
    assert (row["user_id"], row["league_id"], row["source"]) == (UID, LEAGUE, "api")
    assert (props["mode"], props["status"], props["outcome"], props["age_bucket"]) == (
        "strict", "unknown", "served", "none")


def test_split_by_side_and_asset_type_counts_a_both_sides_card_once(env):
    engine, _ = env
    body = _status()
    assert {c["trade_id"] for c in body["cards"]} == {"ok-players", "ok-picks"}
    props = json.loads(_events(engine)[0]["props"])
    assert {k: props[k] for k in ("cards", "kept", "dropped_cards", "dropped_give_player",
                                  "dropped_give_pick", "dropped_receive_player",
                                  "dropped_receive_pick")} == {
        "cards": 7, "kept": 2, "dropped_cards": 5,           # moved-both counts once here
        "dropped_give_player": 2, "dropped_give_pick": 1,    # ...and once per side below
        "dropped_receive_player": 2, "dropped_receive_pick": 1}


def test_a_repeat_poll_of_a_page_emits_nothing(env, monkeypatch):
    """Each card is counted once per job: page 0 (4 cards) and page 4 (3)
    record once each across repeat polls, and the legacy body, whose cards the
    pages already counted, records nothing."""
    engine, _ = env
    monkeypatch.setitem(ts._cfg, "trade_page_size", 4.0)
    for _ in range(3):
        _status("&cursor=0")
    for _ in range(2):
        _status("&cursor=4")
    for _ in range(3):
        _status()                                  # the legacy cumulative body
    pages = [json.loads(r["props"])["cards"] for r in _events(engine)]
    assert sorted(pages) == [3, 4]


def totals(engine):
    """The rows' counts summed, as the readout sums a deck's rows by job_key."""
    rows = [json.loads(r["props"]) for r in _events(engine)]
    names = ("cards", "kept", "dropped_cards", "dropped_give_player", "dropped_give_pick",
             "dropped_receive_player", "dropped_receive_pick", "unchecked_generic",
             "unchecked_pick_owner")
    return len(rows), {n: sum(r[n] for r in rows) for n in names}


WHOLE_DECK = {"cards": 7, "kept": 2, "dropped_cards": 5, "dropped_give_player": 2,
              "dropped_give_pick": 1, "dropped_receive_player": 2, "dropped_receive_pick": 1,
              "unchecked_generic": 0, "unchecked_pick_owner": 0}


def test_a_replace_serve_counts_its_new_cards(env, monkeypatch):
    """#419 QA P3: a re-sorting deck's cursor>0 serve is a replace (the full
    list from index 0). Its cards past page 0 are counted, once: the rows sum
    to the whole deck, and a second replace serve records nothing."""
    engine, job = env
    monkeypatch.setitem(ts._cfg, "trade_page_size", 4.0)
    _status("&cursor=0")
    for card in job["cards"]:                      # the worker re-sorted: not append-only
        card.pop("preserve_server_order")
    assert _status("&cursor=4")["replace"] is True
    _status("&cursor=4")
    count, summed = totals(engine)
    assert (count, summed) == (2, WHOLE_DECK)


def test_cards_published_before_their_impression_ids_count_once(env, monkeypatch):
    """#468 QA P2-1 (probe D): the non-owner path publishes cards without
    impression_ids, then re-publishes them with ids. A card a paged client saw
    before the ids were stamped is not counted again by the next replace
    serve: the identity is the trade_id, so the rows sum to the whole deck."""
    engine, job = env
    monkeypatch.setitem(ts._cfg, "trade_page_size", 4.0)
    assert not any("impression_id" in card for card in job["cards"])
    _status("&cursor=0")
    job["cards"] = [dict(card, impression_id=f"imp-{card['trade_id']}")
                    for card in job["cards"]]
    for card in job["cards"]:                      # the re-publish re-sorted the deck
        card.pop("preserve_server_order")
    assert _status("&cursor=4")["replace"] is True
    _status("&cursor=4")
    assert totals(engine) == (2, WHOLE_DECK)


def test_the_identity_is_the_trade_id_first():
    card = _card("t-1", ["a"], ["b"])
    assert server._i1_card_identity(card) == "t-1"
    assert server._i1_card_identity(dict(card, impression_id="imp-1")) == "t-1"
    assert server._i1_card_identity({"impression_id": "imp-1"}) == "imp-1"


def test_legacy_and_paged_serves_of_one_job_count_each_card_once(env, monkeypatch):
    """#419 QA P3: a job served to a paged client (page 0) and a legacy one
    (the whole deck, complete) records page 0's 4 cards and the legacy body's
    3 others: the rows sum to the whole deck, never 4 + 7."""
    engine, _ = env
    monkeypatch.setitem(ts._cfg, "trade_page_size", 4.0)
    _status("&cursor=0")
    _status()
    _status()
    assert totals(engine) == (2, WHOLE_DECK)


def test_a_new_job_counts_its_cards_afresh(env):
    """The record is per job: the same cards served under another job count."""
    engine, job = env
    _status()
    with server._trade_jobs_lock:
        server._trade_jobs["job-i1ev-2"] = {**job, "job_id": "job-i1ev-2"}
    try:
        resp = server.app.test_client().get("/api/trades/status?job_id=job-i1ev-2",
                                            headers={"X-Session-Token": TOKEN})
        assert resp.status_code == 200
        assert [json.loads(r["props"])["cards"] for r in _events(engine)] == [7, 7]
    finally:
        with server._trade_jobs_lock:
            server._trade_jobs.pop("job-i1ev-2", None)


def test_a_running_legacy_deck_counts_once_complete(env):
    engine, job = env
    job["status"] = "running"
    _status()
    assert _events(engine) == []
    job["status"] = "complete"
    _status()
    _status()
    assert len(_events(engine)) == 1


def test_a_view_built_outside_a_request_emits_nothing(env):
    engine, job = env
    server._trade_job_public_view(dict(job))       # internal call, no HTTP response
    assert _events(engine) == []


def test_mode_0_emits_nothing(env, monkeypatch):
    engine, _ = env
    monkeypatch.setitem(ts._cfg, "trade_i1_mode", 0.0)
    _status()
    _status("&cursor=0")
    assert _events(engine) == []


def test_lenient_mode_logs_served_lenient_not_roster_check_unavailable(env, monkeypatch):
    """Addendum (iv): at trade_i1_mode 1 with no stored rosters, the outcome is
    the lenient label, in the [i1] line and the event alike."""
    engine, _ = env
    monkeypatch.setitem(ts._cfg, "trade_i1_mode", 1.0)
    with engine.begin() as conn:
        conn.execute(delete(league_members_table))
    body = _status()
    assert len(body["cards"]) == len(CARDS)
    props = json.loads(_events(engine)[0]["props"])
    assert (props["mode"], props["status"], props["outcome"]) == (
        "lenient", "missing", "served_lenient")


def test_the_write_is_off_the_request_thread_and_never_fails_the_serve(env, monkeypatch):
    engine, _ = env
    calls = []

    def recording(*args, **kwargs):
        calls.append((threading.current_thread().name, kwargs.get("touch_user"),
                      kwargs.get("bind") is engine))
        raise RuntimeError("analytics down")

    monkeypatch.setattr(server, "record_event", recording)
    body = _status()
    assert body["status"] == "complete" and len(body["cards"]) == 2   # the serve is unaffected
    _drain()
    # Written on the emitter thread, non-touching, through the serve's engine
    # (a thread outliving its request never writes through a later one).
    assert calls == [("deck-i1-check", False, True)]


def test_the_write_is_non_touching(env, monkeypatch):
    engine, _ = env
    # The request's own throttled activity touch (before_request) is not the event's.
    monkeypatch.setattr(server, "touch_user_activity", lambda *a, **kw: None)
    _status()
    _events(engine)
    with engine.connect() as conn:
        user = conn.execute(select(users_table.c.last_active_at, users_table.c.events_count)
                            .where(users_table.c.sleeper_user_id == UID)).first()
    assert tuple(user) == ("2026-01-01", 7)


def test_record_event_touch_user_false_writes_only_the_row(env):
    engine, _ = env
    db_module.record_event(UID, "deck_i1_check", league_id=LEAGUE, props={"cards": 1},
                           touch_user=False)
    db_module.record_event(UID, "trades_generated", league_id=LEAGUE, props={"count": 1})
    with engine.connect() as conn:
        count = conn.execute(select(users_table.c.events_count)
                             .where(users_table.c.sleeper_user_id == UID)).scalar()
    assert count == 8                       # only the touching write bumped it
    assert len(_events(engine)) == 1


def test_registered_server_fired_and_non_intent():
    assert "deck_i1_check" in analytics_taxonomy.SERVER_FIRED_EVENTS
    assert "deck_i1_check" not in analytics_taxonomy.ALLOWED_CLIENT_EVENTS
    assert "deck_i1_check" in analytics_queries.NON_INTENT_EVENTS
    assert "deck_i1_check" not in analytics_queries.INTENT_EVENTS


@pytest.mark.parametrize("age_s, bucket", [(None, "none"), (0, "under_5m"), (299, "under_5m"),
                                           (300, "5m_to_1h"), (3599, "5m_to_1h"),
                                           (3600, "1h_to_24h"), (86400, "over_24h")])
def test_age_buckets(age_s, bucket):
    assert server._i1_age_bucket(age_s) == bucket


# ── #419 QA P3: the page-store emit, the bounded queue, the drain ───────────

def test_a_stored_page_serve_emits_once_per_new_card_set(env, monkeypatch):
    """The page-store serve (_trade_page_view) records its page's new cards:
    page 0's 4 once across repeat serves, then page 4's 3."""
    engine, job = env
    monkeypatch.setitem(ts._cfg, "trade_page_size", 4.0)
    monkeypatch.setattr(server, "_deck_evidence_delivered_stored", lambda *a, **k: None)
    row = {"deck_job_id": "deck-i1ev-page", "user_id": UID, "league_id": LEAGUE, "card_count": 7,
           "pages_blob": {"v": 1, "opponents_total": 2, "cards": [
               {**c, "impression_id": f"deck-i1ev-page:{i}"} for i, c in enumerate(job["cards"])]}}
    for cursor in (0, 0, 4, 4):
        with server.app.test_request_context():
            out, _past = server._trade_page_view(row, cursor, user_id=UID, viewer_id=UID)
        assert out["serve_source"] == "page"
    rows = [json.loads(r["props"]) for r in _events(engine)]
    assert sorted(r["cards"] for r in rows) == [3, 4]
    assert {r["job_key"] for r in rows} == {hashlib.sha256(b"deck-i1ev-page").hexdigest()[:12]}


def _report(ident):
    return {"mode": "strict", "status": "fresh", "outcome": "served", "age_bucket": "under_5m",
            "cards": 1, "kept": 1, "dropped_cards": 0, "dropped_give_player": 0,
            "dropped_give_pick": 0, "dropped_receive_player": 0, "dropped_receive_pick": 0,
            "unchecked_generic": 0, "unchecked_pick_owner": 0,
            "_cards": [(ident, {"cards": 1, "kept": 1, "dropped_cards": 0,
                                "dropped_give_player": 0, "dropped_give_pick": 0,
                                "dropped_receive_player": 0, "dropped_receive_pick": 0,
                                "unchecked_generic": 0, "unchecked_pick_owner": 0})]}


def test_a_full_queue_drops_the_emit_with_a_warning_and_never_blocks(env, monkeypatch, caplog):
    """One worker, a bounded queue: with the worker held on one write and the
    queue (2 here) full, further emits are dropped at once, never blocking the
    serve, warned at most once a minute with the count."""
    small = queue.Queue(maxsize=2)
    monkeypatch.setattr(server, "_i1_event_queue", small)
    monkeypatch.setattr(server, "_i1_event_worker_for", None)
    monkeypatch.setattr(server, "_i1_event_dropped", 0)
    monkeypatch.setattr(server, "_i1_event_drop_warned_at", float("-inf"))
    started, release = threading.Event(), threading.Event()

    def held(lease, write):
        started.set()
        release.wait(10)
    monkeypatch.setattr(server, "_record_deck_i1_check", held)
    try:
        with caplog.at_level("WARNING"), server.app.test_request_context():
            server._emit_deck_i1_check(UID, LEAGUE, "job-q-0", _report("c"))
            assert started.wait(5)                 # the worker holds the first write
            began = time.monotonic()
            for i in range(1, 6):                  # 2 queued, 3 dropped
                server._emit_deck_i1_check(UID, LEAGUE, f"job-q-{i}", _report("c"))
            assert time.monotonic() - began < 1.0  # never blocked
        assert small.qsize() == 2
        lines = [r.getMessage() for r in caplog.records if "queue full" in r.getMessage()]
        assert lines == ["deck_i1_check queue full (2): dropped 1 emit since the last warning"]
        assert server._i1_event_dropped == 2       # counted for the next warning
    finally:
        release.set()
        small.join()


def test_the_drain_waits_for_queued_and_in_flight_writes(env, monkeypatch):
    engine, _ = env
    done = []

    def slow(lease, write):
        time.sleep(0.3)
        done.append(write)
    monkeypatch.setattr(server, "_record_deck_i1_check", slow)
    with server.app.test_request_context():
        server._emit_deck_i1_check(UID, LEAGUE, "job-d-0", _report("c"))
        server._emit_deck_i1_check(UID, LEAGUE, "job-d-1", _report("c"))
    assert server._drain_deck_i1_checks(5) is True and len(done) == 2


def test_the_drain_gives_up_at_its_timeout(env, monkeypatch):
    release = threading.Event()
    monkeypatch.setattr(server, "_record_deck_i1_check", lambda lease, write: release.wait(10))
    try:
        with server.app.test_request_context():
            server._emit_deck_i1_check(UID, LEAGUE, "job-t-0", _report("c"))
        started = time.monotonic()
        assert server._drain_deck_i1_checks(0.2) is False
        assert time.monotonic() - started < 2.0
    finally:
        release.set()
        assert server._drain_deck_i1_checks(5)


# conftest.py's drains: a test's queued writes finish as its call ends (inside
# the call's capture), and a write a fixture queues at teardown finishes at
# teardown. These pairs run in file order.
_LANDED = []
_LANDED_AT_TEARDOWN = []


def _slow_write(into):
    lease = server._user_data_lifecycle.capture(UID)
    server._i1_event_enqueue(lease, lambda: (time.sleep(1.0), into.append("written")))


@pytest.fixture()
def landed_before_teardown():
    yield
    assert _LANDED == ["written"]                  # the call-phase drain already finished it


def test_a_test_that_leaves_a_slow_write_queued(landed_before_teardown):
    _slow_write(_LANDED)


@pytest.fixture()
def queues_a_write_at_teardown():
    yield
    _slow_write(_LANDED_AT_TEARDOWN)


def test_a_fixture_that_queues_a_write_at_teardown(queues_a_write_at_teardown):
    assert _LANDED == ["written"]


def test_the_next_test_finds_both_written():
    assert _LANDED_AT_TEARDOWN == ["written"]


# ── #468 QA follow-ups: the worker, the lease, exit, the drop tail, gaps ─────

@pytest.fixture()
def fresh_queue(monkeypatch):
    """A private queue and worker, so a test's worker never serves another's."""
    q = queue.Queue(maxsize=10)
    monkeypatch.setattr(server, "_i1_event_queue", q)
    monkeypatch.setattr(server, "_i1_event_worker_for", None)
    monkeypatch.setattr(server, "_i1_event_worker_thread", None)
    monkeypatch.setattr(server, "_i1_event_dropped", 0)
    monkeypatch.setattr(server, "_i1_event_drop_warned_at", float("-inf"))
    return q


def _lease(*, active=True, deleting=False):
    @contextlib.contextmanager
    def _active():
        yield active
    return types.SimpleNamespace(active=_active, deleting=lambda: deleting)


def _landed(write_log, item, timeout=5.0):
    deadline = time.monotonic() + timeout
    while item not in write_log and time.monotonic() < deadline:
        time.sleep(0.01)
    return item in write_log


class _Die(BaseException):
    pass


def test_a_dead_worker_is_restarted_by_the_next_enqueue(fresh_queue, monkeypatch):
    """P3-1: a BaseException ends the worker; the next enqueue starts another."""
    monkeypatch.setattr(threading, "excepthook", lambda args: None)   # the death is expected
    written = []
    server._i1_event_enqueue(_lease(), lambda: (_ for _ in ()).throw(_Die()))
    first = server._i1_event_worker_thread
    first.join(5)
    assert not first.is_alive()
    server._i1_event_enqueue(_lease(), lambda: written.append("after"))
    assert _landed(written, "after")
    assert server._i1_event_worker_thread is not first


def test_an_exception_in_a_write_never_ends_the_worker(fresh_queue, monkeypatch):
    """The worker's own `except`: a raising record leaves the same worker
    running for the next write."""
    real = server._record_deck_i1_check
    calls = []

    def flaky(lease, write):
        calls.append(write)
        if len(calls) == 1:
            raise RuntimeError("boom")
        real(lease, write)
    monkeypatch.setattr(server, "_record_deck_i1_check", flaky)
    written = []
    server._i1_event_enqueue(_lease(), lambda: written.append("first"))
    worker = server._i1_event_worker_thread
    server._i1_event_enqueue(_lease(), lambda: written.append("second"))
    assert _landed(written, "second") and written == ["second"]
    assert server._i1_event_worker_thread is worker and worker.is_alive()


def test_a_deleting_user_s_write_never_holds_another_user_s(fresh_queue):
    """P3-2: while one user's deletion holds new work, their queued write is
    skipped, not waited on, and the next user's write lands at once."""
    gone, kept = "i1ev-deleting-user", "i1ev-other-user"
    lease_gone = user_data_lifecycle.capture(gone)
    lease_kept = user_data_lifecycle.capture(kept)
    written = []
    with user_data_lifecycle.hold([gone], timeout=5):
        assert lease_gone.deleting() and not lease_kept.deleting()
        server._i1_event_enqueue(lease_gone, lambda: written.append(gone))
        server._i1_event_enqueue(lease_kept, lambda: written.append(kept))
        assert _landed(written, kept, timeout=2.0)
    assert server._drain_deck_i1_checks(5)
    assert written == [kept]


def test_a_lease_that_refuses_writes_nothing(fresh_queue):
    written = []
    server._i1_event_enqueue(_lease(active=False), lambda: written.append("refused"))
    server._i1_event_enqueue(_lease(), lambda: written.append("admitted"))
    assert _landed(written, "admitted") and written == ["admitted"]


def test_the_exit_drain_lands_queued_writes_and_logs_pending_drops(fresh_queue, monkeypatch,
                                                                   caplog):
    """P3-3: registered with atexit; it waits for the queue, then warns the
    drops not yet warned whatever the minute says."""
    written = []
    monkeypatch.setattr(server, "_i1_event_dropped", 3)
    monkeypatch.setattr(server, "_i1_event_drop_warned_at", time.monotonic())
    server._i1_event_enqueue(_lease(), lambda: (time.sleep(0.2), written.append("queued")))
    with caplog.at_level("WARNING"):
        server._i1_event_exit_drain()
    assert written == ["queued"]
    assert [r.getMessage() for r in caplog.records if "queue full" in r.getMessage()] == \
        ["deck_i1_check queue full (10): dropped 3 emits since the last warning"]
    assert server._i1_event_dropped == 0


def test_the_exit_drain_is_registered_with_atexit():
    with open(server.__file__) as fh:
        assert "\natexit.register(_i1_event_exit_drain)\n" in fh.read()


def test_a_burst_s_tail_is_logged_once_the_drops_stop(fresh_queue, monkeypatch, caplog):
    """P3-5: drops counted after the last warning are logged by the worker's
    idle tick once the minute (0.2 s here) has passed, with no later drop.
    It waits on the record itself, never the counter: the worker zeroes the
    counter under the lock and logs after releasing it (#519 QA P3-2)."""
    monkeypatch.setattr(server, "_I1_EVENT_DROP_WARN_EVERY_S", 0.2)
    monkeypatch.setattr(server, "_i1_event_dropped", 2)
    monkeypatch.setattr(server, "_i1_event_drop_warned_at", time.monotonic())
    written = []

    def warned():
        return [r.getMessage() for r in caplog.records if "queue full" in r.getMessage()]
    with caplog.at_level("WARNING"):
        server._i1_event_enqueue(_lease(), lambda: written.append("w"))
        deadline = time.monotonic() + 3
        while not warned() and time.monotonic() < deadline:
            time.sleep(0.02)
        time.sleep(0.25)                  # past one more interval: still exactly one warning
    assert warned() == ["deck_i1_check queue full (10): dropped 2 emits since the last warning"]


def test_the_exit_drain_restarts_a_dead_worker_with_writes_behind_it(fresh_queue, monkeypatch):
    """#485 QA P3: the worker dies (a BaseException) with a write queued
    behind it; the exit drain starts a worker, so that write lands."""
    monkeypatch.setattr(threading, "excepthook", lambda args: None)   # the death is expected
    monkeypatch.setattr(server, "_I1_EVENT_EXIT_DRAIN_S", 2.0)
    go, written = threading.Event(), []

    def die():
        go.wait(5)
        raise _Die()
    server._i1_event_enqueue(_lease(), die)
    first = server._i1_event_worker_thread
    server._i1_event_enqueue(_lease(), lambda: written.append("stranded"))
    go.set()
    first.join(5)
    assert not first.is_alive() and written == []           # stranded behind the dead worker
    server._i1_event_exit_drain()
    assert written == ["stranded"] and server._i1_event_worker_thread is not first


def _strand_a_write(written):
    """The worker dies (a BaseException) with a write queued behind it."""
    go = threading.Event()

    def die():
        go.wait(5)
        raise _Die()
    server._i1_event_enqueue(_lease(), die)
    first = server._i1_event_worker_thread
    server._i1_event_enqueue(_lease(), lambda: written.append("stranded"))
    go.set()
    first.join(5)
    assert not first.is_alive() and written == []
    return first


def test_the_exit_drain_never_raises_when_a_thread_is_refused(fresh_queue, monkeypatch, caplog):
    """#519 QA: CPython 3.12 may refuse a new thread at interpreter shutdown.
    The exit drain then logs the stranded writes and returns at once, never
    raising and never waiting on a queue nothing serves."""
    monkeypatch.setattr(threading, "excepthook", lambda args: None)
    written = []
    _strand_a_write(written)

    def refuse(self):
        raise RuntimeError("can't create new thread at interpreter shutdown")
    monkeypatch.setattr(threading.Thread, "start", refuse)
    started = time.monotonic()
    with caplog.at_level("WARNING"):
        server._i1_event_exit_drain()
    assert time.monotonic() - started < 1 and written == []
    assert any("no worker at exit" in r.getMessage() and "1 queued writes" in r.getMessage()
               for r in caplog.records)


@pytest.mark.parametrize("how", ["normal", "sigterm"])
def test_a_real_exit_with_a_dead_worker_never_raises(tmp_path, how):
    """#519 QA, in a fresh interpreter (the CI's, 3.12): the worker dies with
    a write stranded behind it, then the process exits, normally or through a
    SIGTERM handler that exits, as gunicorn's worker does. atexit runs the
    drain: it exits 0 with no traceback, and the write either lands (a thread
    may start at shutdown) or is logged as not recorded (it may not)."""
    import os
    import subprocess
    import sys
    from pathlib import Path
    repo = Path(__file__).resolve().parents[2]
    out = tmp_path / "landed.txt"
    env = {k: v for k, v in os.environ.items()
           if k not in ("FTF_TEST_MODE", "FTF_SLEEPER_RECORD", "DATABASE_URL")}
    env["DATABASE_URL"] = f"sqlite:///{tmp_path / 'scratch.db'}"
    script = f"""
import contextlib, os, signal, sys, threading, time, types
import backend.server as s
threading.excepthook = lambda args: None
class Die(BaseException):
    pass
@contextlib.contextmanager
def active():
    yield True
lease = types.SimpleNamespace(active=active, deleting=lambda: False)
go = threading.Event()
def die():
    go.wait(5)
    raise Die()
s._i1_event_enqueue(lease, die)
first = s._i1_event_worker_thread
s._i1_event_enqueue(lease, lambda: open({str(out)!r}, "a").write("landed"))
go.set()
first.join(5)
assert not first.is_alive()
if {how!r} == "sigterm":
    signal.signal(signal.SIGTERM, lambda *a: sys.exit(0))
    os.kill(os.getpid(), signal.SIGTERM)
    time.sleep(5)
"""
    child = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True,
                           cwd=repo, env=env, timeout=180)
    assert child.returncode == 0, child.stderr[-2000:]
    assert "Traceback" not in child.stderr, child.stderr[-2000:]
    landed = out.exists() and out.read_text() == "landed"
    assert landed or "no worker at exit" in child.stderr, child.stderr[-2000:]


def test_the_drops_are_flushed_right_after_a_write(fresh_queue, monkeypatch):
    """#485 QA P3: the worker serving this queue calls the drop warning right
    after each write, so drops past the minute are logged then, not on the
    idle tick a minute later. Pinned by the call on this test's own queue:
    the drop counter is module-wide, and another test's idle worker may log
    it."""
    calls = []
    real = server._i1_event_drop_warning

    def spy(q, dropped=0, **kw):
        calls.append((q, dropped))
        return real(q, dropped, **kw)
    monkeypatch.setattr(server, "_i1_event_drop_warning", spy)
    written = []
    server._i1_event_enqueue(_lease(), lambda: written.append("w"))
    assert _landed(written, "w")
    deadline = time.monotonic() + 2
    while (fresh_queue, 0) not in calls and time.monotonic() < deadline:
        time.sleep(0.01)
    assert (fresh_queue, 0) in calls          # the idle tick is a minute away


def test_the_fallback_identity_keeps_the_partner():
    """A card with neither id is its assets AND its partner: the same trade
    with two opponents is two cards."""
    def bare(partner):
        return {"target_user_id": partner, "give": [{"id": "a"}], "receive": [{"id": "b"}]}
    assert server._i1_card_identity(bare("opp-1")) != server._i1_card_identity(bare("opp-2"))
    assert server._i1_card_identity(bare("opp-1")) == server._i1_card_identity(bare("opp-1"))


def test_the_dedupe_evicts_the_least_recently_served_job(env, monkeypatch):
    """The per-job record is an LRU: a job served again moves to the end
    (`move_to_end`), so the next eviction takes the job served longest ago and
    keeps the one just served."""
    monkeypatch.setattr(server, "_I1_EVENT_DEDUPE_MAX", 2)
    for job_id in ("lru-a", "lru-b"):
        assert server._i1_new_cards(job_id, _report("card")) is not None
    assert server._i1_new_cards("lru-a", _report("card")) is None     # a repeat, and A is now newest
    assert server._i1_new_cards("lru-c", _report("card")) is not None  # evicts B, not A
    assert list(server._i1_events_seen) == ["lru-a", "lru-c"]
    assert server._i1_new_cards("lru-a", _report("card")) is None
    assert server._i1_new_cards("lru-b", _report("card")) is not None  # B counts afresh
