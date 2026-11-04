"""D1 double-move block on Postgres (release-lead QA of #578, P2-1).

Two taps for the same player with different attempt_ids, on real threads,
against a real Postgres. The case that broke the old lower-id re-read: X takes
the LOWER id but commits AFTER Y (a trigger sleeps inside X's INSERT, after
nextval), so Y's re-read can't see X and X's re-read ignores Y's higher id.
`database.claim_platform_write_move` holds a transaction-scoped advisory lock
on (user, league, add player) around the block check and the insert, so Y
waits for X's commit, sees X's row and never sends. Exactly one platform call.

Opt-in, like test_prepared_trade_store_v2's Postgres run: set
FTF_FA_MOVE_TEST_POSTGRES_URL to a disposable, socket-only local Postgres,
e.g. postgresql+psycopg2://postgres@/postgres?host=/private/tmp/famovepg&port=55491
Skipped otherwise. Each test runs in its own schema, dropped afterwards. No
network: the Sleeper write is the shipped transport with the harness's
injected opener (test_fa_move_route).
"""
from __future__ import annotations

import json
import os
import threading
import time
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.schema import CreateSchema, DropSchema

import backend.database as db_module
import backend.server as server
from backend.tests.test_fa_move_route import TOKEN, _harness

PG_URL = os.environ.get("FTF_FA_MOVE_TEST_POSTGRES_URL")


@pytest.fixture()
def hpg(monkeypatch):
    if not PG_URL:
        pytest.skip("FTF_FA_MOVE_TEST_POSTGRES_URL not set (disposable local Postgres)")
    url = make_url(PG_URL)
    # Only a disposable socket-only Postgres under /private/tmp: never a network host.
    assert url.drivername == "postgresql+psycopg2" and not url.host
    assert str(url.query.get("host", "")).startswith("/private/tmp/")
    schema = "famove_" + uuid.uuid4().hex[:12]
    controller = create_engine(url)
    with controller.begin() as conn:
        conn.execute(CreateSchema(schema))
    engine = create_engine(url, connect_args={"options": "-csearch_path=" + schema})
    # The credential / member upserts pick their SQL by DATABASE_URL.
    monkeypatch.setattr(db_module, "DATABASE_URL", "postgresql://famove-test")
    gen = _harness(monkeypatch, engine)
    h = next(gen)
    h.schema = schema
    try:
        yield h
    finally:
        try:
            next(gen)
        except StopIteration:
            pass
        with controller.begin() as conn:
            conn.execute(DropSchema(schema, cascade=True))
        controller.dispose()


def _post(h, attempt, results):
    client = server.app.test_client()
    r = client.post("/api/league/free-agents/move",
                    headers={"X-Session-Token": TOKEN, "Content-Type": "application/json"},
                    data=json.dumps(h.body(attempt_id=attempt)))
    results[attempt] = r.status_code


def _run(threads):
    for t in threads:
        t.start()
    for t in threads:
        t.join(60)
        assert not t.is_alive()


def test_commit_order_inversion_sends_once(hpg, monkeypatch):
    """X holds the lower id and commits last; Y must still not send."""
    h = hpg
    with h.engine.begin() as conn:
        conn.execute(text("""
            CREATE OR REPLACE FUNCTION famove_slow() RETURNS trigger AS $$
            BEGIN
              IF NEW.phase = 'sent' AND NEW.attempt_id LIKE 'slow-%' THEN
                PERFORM pg_sleep(1.5);
              END IF;
              RETURN NEW;
            END; $$ LANGUAGE plpgsql;"""))
        conn.execute(text("CREATE TRIGGER famove_slow_t AFTER INSERT ON platform_write_moves "
                          "FOR EACH ROW EXECUTE FUNCTION famove_slow();"))
    barrier = threading.Barrier(2, timeout=20)
    x_in_claim = threading.Event()
    real_fetch = server._fetch_league_rosters
    monkeypatch.setattr(server, "_fetch_league_rosters",
                        lambda lid: (barrier.wait(), real_fetch(lid))[1])
    real_claim = db_module.claim_platform_write_move

    def _claim(row, blocked, *, since):
        if row["attempt_id"].startswith("slow-"):
            def _x_blocked(rows):
                x_in_claim.set()              # X is inside its transaction now
                return blocked(rows)
            return real_claim(row, _x_blocked, since=since)
        x_in_claim.wait(10)
        time.sleep(0.3)                       # X is inserting (nextval taken), uncommitted
        return real_claim(row, blocked, since=since)
    monkeypatch.setattr(db_module, "claim_platform_write_move", _claim)
    results = {}
    _run([threading.Thread(target=_post, args=(h, "slow-x-famove", results), name="X"),
          threading.Thread(target=_post, args=(h, "fast-y-famove", results), name="Y")])
    assert len(h.platform.calls) == 1, results
    assert sorted(results.values()) == [200, 409], results
    sent = [m["attempt_id"] for m in h.moves() if m["phase"] == "sent"]
    assert sent == ["slow-x-famove"]          # Y wrote nothing: refused under the lock


def test_two_taps_racing_the_preflight_send_once(hpg, monkeypatch):
    h = hpg
    barrier = threading.Barrier(2, timeout=20)
    real_fetch = server._fetch_league_rosters
    monkeypatch.setattr(server, "_fetch_league_rosters",
                        lambda lid: (barrier.wait(), real_fetch(lid))[1])
    results = {}
    _run([threading.Thread(target=_post, args=(h, f"race-{i}-famove", results)) for i in (1, 2)])
    assert len(h.platform.calls) == 1, results
    assert sorted(results.values()) == [200, 409], results
