"""deck_i1_check: the S0 C-a readout's data path (analytics-lead's pre-grant,
2026-10-26 §2 (a); models-lead's R2.4 addendum (ii) and (iv)).

Pins: one server-fired NON_INTENT row per job serve page that ran the I-1
check, deduped across repeat polls; none at trade_i1_mode 0; the exact prop
keys, with no league id or raw job id; the give/receive x player/pick split
with a both-sides card counted once in `dropped_cards`; the write is
non-touching, owned by the viewer, and never on the request thread; the
lenient label. Harness: a hand-built complete job served through
/api/trades/status over a file-backed SQLite DB (the event is written on a
background thread, and an in-memory SQLite DB is per thread).
"""
import hashlib
import json
import threading

import pytest
from sqlalchemy import create_engine, delete, insert, select

import backend.database as db_module
import backend.server as server
from backend import analytics_queries, analytics_taxonomy
from backend import trade_service as ts
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
    with server._i1_events_lock:
        server._i1_events_seen.clear()
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
        with server._i1_events_lock:
            server._i1_events_seen.clear()


def _drain():
    for thread in threading.enumerate():
        if thread.name == "deck-i1-check":
            thread.join(5)


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


def test_one_event_per_job_page_across_repeat_polls(env, monkeypatch):
    engine, _ = env
    monkeypatch.setitem(ts._cfg, "trade_page_size", 4.0)
    for _ in range(3):
        _status("&cursor=0")
    for _ in range(2):
        _status("&cursor=4")
    for _ in range(3):
        _status()                                  # the legacy cumulative body
    pages = [json.loads(r["props"])["cards"] for r in _events(engine)]
    assert pages == [4, 3, 7]                      # page 0, page 4, the legacy deck once


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
