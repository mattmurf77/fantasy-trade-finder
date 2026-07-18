"""Analytics platform P0 — server truth (docs/plans/analytics-platform/lld.md).

Covers:
  (a) WAL boot assertion true on file-backed SQLite (T-22 boot half)
  (b) T-1 — full unique event_id index, NULLS DISTINCT: 2×NULL + 2×same-id
      → 3 rows
  (c) migration idempotence (T-15): _migrate_db() twice = identical schema;
      composite indexes present, old single-column indexes dropped
  (d) wrapped_events cutover (T-16 shape): the five flipped writers land in
      user_events, wrapped_events receives ZERO writes, the cutover key is
      seeded once, and load_league_activity unions both eras
  (e) the four new FR-20 server-fired events (quickset_completed,
      quickrank_completed, trades_generated, calc_trade_evaluated) fire with
      the LLD §6.4b props
  (f) taxonomy namespace assertion trips on a client/server collision
  (g) /api/admin/analytics/health returns counters + boot status

Harness pattern follows test_events_api.py: isolated SQLite engine patched
into backend.database, Flask test client, flags forced via patched
`is_enabled`.
"""
import json
import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, event as sa_event, insert, select, text

import backend.database as db_module
import backend.server as server
from backend.database import (
    metadata, user_events_table, wrapped_events_table, model_config_table,
)

USER = "user_analytics_p0"
TOKEN = "analytics-p0-token"
LEAGUE = "L_p0"


# ---------------------------------------------------------------------------
# Engine helpers
# ---------------------------------------------------------------------------

def _file_engine(tmp_path, with_wal_listener=False):
    """File-backed SQLite engine (in-memory can't do WAL) with schema."""
    path = tmp_path / "p0.db"
    eng = create_engine(f"sqlite:///{path}",
                        connect_args={"check_same_thread": False})
    if with_wal_listener:
        # Reuse the production on-connect listener verbatim.
        sa_event.listen(eng, "connect", db_module._sqlite_on_connect)
    metadata.create_all(eng)
    return eng


def _sqlite_indexes(engine, table):
    with engine.connect() as conn:
        rows = conn.exec_driver_sql(
            f"PRAGMA index_list('{table}')").fetchall()
    return {r[1] for r in rows}


def _schema_dump(engine):
    with engine.connect() as conn:
        rows = conn.exec_driver_sql(
            "SELECT type, name, tbl_name, sql FROM sqlite_master "
            "ORDER BY type, name").fetchall()
    return [tuple(r) for r in rows]


# ---------------------------------------------------------------------------
# (a) WAL boot assertion (T-22, sqlite half)
# ---------------------------------------------------------------------------

def test_wal_boot_assertion_true_on_sqlite(tmp_path):
    eng = _file_engine(tmp_path, with_wal_listener=True)
    with patch.object(db_module, "engine", eng):
        status = db_module.analytics_boot_status()
    assert status["wal"] is True
    assert status["event_id_index_present"] is True
    assert db_module.wal_file_bytes() is not None  # sqlite → int, never None


def test_boot_status_never_raises_without_wal(tmp_path):
    # No listener → journal_mode stays 'delete'; boot check reports, never raises.
    eng = _file_engine(tmp_path, with_wal_listener=False)
    with patch.object(db_module, "engine", eng):
        status = db_module.analytics_boot_status()
    assert status["wal"] is False
    assert status["event_id_index_present"] is True


# ---------------------------------------------------------------------------
# T-23b — the ingest engine's 150 ms lock budget must NOT be clobbered by the
# product listener's busy_timeout=5000 (LLD §3.3 listener-precedence trap).
# ---------------------------------------------------------------------------

def test_ingest_busy_timeout_is_150_not_5000(tmp_path):
    prod = create_engine(f"sqlite:///{tmp_path / 'prod.db'}",
                         connect_args={"check_same_thread": False})
    sa_event.listen(prod, "connect", db_module._sqlite_on_connect)
    ingest = create_engine(f"sqlite:///{tmp_path / 'prod.db'}",
                           connect_args={"check_same_thread": False,
                                         "timeout": 0.15})
    sa_event.listen(ingest, "connect", db_module._sqlite_on_connect_ingest)
    with prod.connect() as c:
        assert c.exec_driver_sql("PRAGMA busy_timeout").scalar() == 5000
    with ingest.connect() as c:
        # If the product listener were attached to the ingest engine, its
        # busy_timeout=5000 PRAGMA would run post-connect and win → 5000.
        assert c.exec_driver_sql("PRAGMA busy_timeout").scalar() == 150


# ---------------------------------------------------------------------------
# (b) T-1 — full unique index, NULLS DISTINCT
# ---------------------------------------------------------------------------

def test_full_unique_event_id_index_nulls_distinct(tmp_path):
    eng = _file_engine(tmp_path)
    base = dict(user_id=USER, event_type="app_open",
                occurred_at="2026-07-17T00:00:00+00:00")
    with eng.begin() as conn:
        conn.execute(insert(user_events_table).values(**base, event_id=None))
        conn.execute(insert(user_events_table).values(**base, event_id=None))
        conn.execute(insert(user_events_table).values(**base, event_id="evt-1"))
    with pytest.raises(Exception):        # unique violation on the repeat
        with eng.begin() as conn:
            conn.execute(insert(user_events_table).values(**base, event_id="evt-1"))
    with eng.connect() as conn:
        n = conn.execute(
            select(db_module.func.count()).select_from(user_events_table)
        ).scalar()
    assert n == 3  # 2×NULL + 1×'evt-1' — NULLs never collide (I-1)


# ---------------------------------------------------------------------------
# (c) T-15 — migration idempotence + index deltas
# ---------------------------------------------------------------------------

def test_migrate_db_twice_identical_schema_and_index_deltas(tmp_path):
    eng = _file_engine(tmp_path)
    # Pre-create the OLD single-column indexes so the drop path is exercised
    # (fresh create_all no longer declares them).
    with eng.begin() as conn:
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_user_events_device_id "
            "ON user_events (device_id)"))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_identity_links_device "
            "ON identity_links (device_id)"))
    with patch.object(db_module, "engine", eng), \
         patch.object(db_module, "DATABASE_URL", "sqlite:///p0"):
        db_module._migrate_db()
        dump1 = _schema_dump(eng)
        db_module._migrate_db()
        dump2 = _schema_dump(eng)

    assert dump1 == dump2, "second _migrate_db() run changed the schema"

    ue_idx = _sqlite_indexes(eng, "user_events")
    il_idx = _sqlite_indexes(eng, "identity_links")
    assert "ix_user_events_event_id" in ue_idx
    assert "ix_user_events_device_occurred" in ue_idx
    assert "ix_user_events_device_id" not in ue_idx           # dropped
    assert "ix_identity_links_device_linked" in il_idx
    assert "ix_identity_links_user" in il_idx
    assert "ix_identity_links_device" not in il_idx           # dropped


def test_cutover_key_seeded_once(tmp_path):
    eng = _file_engine(tmp_path)
    with patch.object(db_module, "engine", eng), \
         patch.object(db_module, "DATABASE_URL", "sqlite:///p0"):
        db_module._migrate_db()
        first = db_module.get_wrapped_cutover_iso()
        assert first, "cutover key missing after migration"
        datetime.fromisoformat(first)  # parseable ISO
        time.sleep(0.01)
        db_module._migrate_db()        # INSERT-or-ignore: must not move
        assert db_module.get_wrapped_cutover_iso() == first


# ---------------------------------------------------------------------------
# (d) T-16 shape — cutover: writers land in user_events, wrapped stays frozen
# ---------------------------------------------------------------------------

@pytest.fixture()
def cutover_db(tmp_path):
    eng = _file_engine(tmp_path)
    with patch.object(db_module, "engine", eng), \
         patch.object(db_module, "DATABASE_URL", "sqlite:///p0"):
        db_module._migrate_db()
        yield eng


def _count(eng, table):
    with eng.connect() as conn:
        return conn.execute(
            select(db_module.func.count()).select_from(table)).scalar()


def _ue_rows(eng, event_type=None):
    stmt = select(user_events_table).order_by(user_events_table.c.id)
    if event_type:
        stmt = stmt.where(user_events_table.c.event_type == event_type)
    with eng.connect() as conn:
        return [r._mapping for r in conn.execute(stmt).fetchall()]


def test_flipped_writers_zero_wrapped_writes(cutover_db):
    eng = cutover_db
    db_module.save_tiers_position(USER, "RB")                      # ex-wrapped tier_save
    db_module.save_ranking_swipes(USER, ["a", "b", "c"])           # ex-wrapped swipe
    db_module.create_trade_match(LEAGUE, USER, "partner_1",
                                 ["p1"], ["p2"])                   # ex-wrapped trade_match
    db_module.upsert_league(LEAGUE, USER, "Test League", "2026",
                            [], [])                                # ex-wrapped league_sync

    assert _count(eng, wrapped_events_table) == 0, \
        "wrapped_events must receive ZERO writes post-cutover (FR-4)"

    swipe = _ue_rows(eng, "swipe")
    assert len(swipe) == 1
    assert json.loads(swipe[0]["props"]) == {
        "count": 3, "scoring_format": "1qb_ppr"}
    assert swipe[0]["event_id"] is None                            # server-fired (I-1)

    tm = _ue_rows(eng, "trade_match")
    assert len(tm) == 1
    assert tm[0]["league_id"] == LEAGUE
    tm_props = json.loads(tm[0]["props"])
    assert tm_props["partner_id"] == "partner_1"
    assert tm_props["match_id"] is not None


def test_tier_save_joined_rank_streak_events():
    assert "tier_save" in db_module._RANK_STREAK_EVENTS


def test_narrative_union_renders_both_eras(cutover_db):
    eng = cutover_db
    cutover = db_module.get_wrapped_cutover_iso()
    # Legacy row strictly before the cutover instant.
    legacy_ts = (datetime.fromisoformat(cutover)
                 - timedelta(hours=2)).isoformat()
    with eng.begin() as conn:
        conn.execute(insert(wrapped_events_table).values(
            user_id=USER, league_id=LEAGUE, season=2026,
            event_type="tier_save",
            payload_json=json.dumps({"position": "WR",
                                     "scoring_format": "1qb_ppr"}),
            created_at=legacy_ts,
        ))
    # New-era row via the flipped writer (occurred_at = now ≥ cutover).
    db_module.create_trade_match(LEAGUE, USER, "partner_1", ["p1"], ["p2"])

    feed = db_module.load_league_activity(LEAGUE, limit=10)
    types = [e["event_type"] for e in feed]
    assert "tier_save" in types, "legacy wrapped era missing from the union"
    assert "trade_match" in types, "user_events era missing from the union"
    # Union count-consistency: every feed row comes from exactly one side.
    assert len(feed) == 2


def test_narrative_league_synced_renders_as_league_sync(cutover_db):
    eng = cutover_db
    db_module.record_event(USER, "league_synced", league_id=LEAGUE,
                           source="api", props={"platform": "sleeper"})
    feed = db_module.load_league_activity(LEAGUE, limit=10)
    assert [e["event_type"] for e in feed] == ["league_sync"]  # legacy name kept


# ---------------------------------------------------------------------------
# (e) FR-20 — the four new server-fired events
# ---------------------------------------------------------------------------

class _FakeRankings:
    rankings: list = []


class _FakeService:
    _elo_overrides: dict = {}
    _seed: dict = {}

    def apply_tiers(self, **kw):
        pass

    def apply_reorder(self, **kw):
        pass

    def get_rankings(self, position=None):
        return _FakeRankings()

    def comparison_counts(self):
        return {}


class _FalseFlags:
    def __getattr__(self, name):
        return False

    def __getitem__(self, key):
        return False


@pytest.fixture()
def route_harness(tmp_path):
    eng = _file_engine(tmp_path)
    with patch.object(db_module, "engine", eng), \
         patch.object(db_module, "DATABASE_URL", "sqlite:///p0"):
        db_module._migrate_db()
        svc = _FakeService()
        sess = {
            "user_id": USER,
            "league": SimpleNamespace(league_id=LEAGUE, members=[]),
            "players": [SimpleNamespace(id="p1")],
            "user_roster": ["p1"],
            "service": svc,
            "trade_svc": SimpleNamespace(),
            "last_active": 0.0,
        }
        server.app.config["TESTING"] = True
        client = server.app.test_client()
        with patch.object(server, "is_enabled", lambda k: False), \
             patch.object(server, "FLAGS", _FalseFlags()):
            with server._sessions_lock:
                server._sessions[TOKEN] = sess
            try:
                yield client, eng, sess
            finally:
                with server._sessions_lock:
                    server._sessions.pop(TOKEN, None)


def test_quickset_completed_fires_with_props(route_harness):
    client, eng, _ = route_harness
    r = client.post("/api/tiers/save",
                    headers={"X-Session-Token": TOKEN,
                             "Content-Type": "application/json"},
                    data=json.dumps({"position": "RB",
                                     "tiers": {"first_1": ["a", "b"]},
                                     "via": "quickset",
                                     "duration_ms": 4200,
                                     "skipped": False}))
    assert r.status_code == 200
    ts = _ue_rows(eng, "tier_save")
    assert len(ts) == 1
    ts_props = json.loads(ts[0]["props"])
    assert ts_props["via"] == "quickset"
    assert ts_props["scoring_format"] == "1qb_ppr"
    qs = _ue_rows(eng, "quickset_completed")
    assert len(qs) == 1
    assert json.loads(qs[0]["props"]) == {
        "position": "RB", "players_placed": 2,
        "duration_ms": 4200, "skipped": False}


def test_quickset_event_absent_for_plain_tier_save(route_harness):
    client, eng, _ = route_harness
    r = client.post("/api/tiers/save",
                    headers={"X-Session-Token": TOKEN,
                             "Content-Type": "application/json"},
                    data=json.dumps({"position": "WR",
                                     "tiers": {"first_1": ["a"]}}))
    assert r.status_code == 200
    assert _ue_rows(eng, "quickset_completed") == []
    assert len(_ue_rows(eng, "tier_save")) == 1


def test_quickrank_completed_fires_with_props(route_harness):
    client, eng, _ = route_harness
    r = client.post("/api/rankings/reorder",
                    headers={"X-Session-Token": TOKEN,
                             "Content-Type": "application/json"},
                    data=json.dumps({"position": "WR",
                                     "ordered_ids": ["a", "b", "c"],
                                     "via": "quickrank",
                                     "duration_ms": 900,
                                     "skipped": True}))
    assert r.status_code == 200
    assert len(_ue_rows(eng, "ranking_reorder")) == 1
    qr = _ue_rows(eng, "quickrank_completed")
    assert len(qr) == 1
    assert json.loads(qr[0]["props"]) == {
        "position": "WR", "players_ranked": 3,
        "duration_ms": 900, "skipped": True}


def test_trades_generated_fires_post_engine(route_harness):
    client, eng, sess = route_harness
    sess["trade_svc"] = SimpleNamespace(
        generate_trades=lambda **kw: [])
    job_id = "job-analytics-p0"
    with server._trade_jobs_lock:
        server._trade_jobs[job_id] = {
            "job_id": job_id, "key": (USER, LEAGUE, "1qb_ppr"),
            "status": "running", "started_at": time.monotonic(),
            "finished_at": None, "opponents_done": 0, "opponents_total": 0,
            "cards": [], "error": None, "fairness_threshold": 0.75,
            "outlook_value": None, "is_pinned": False,
        }
    try:
        server._run_trade_job(job_id, TOKEN, LEAGUE, 0.75, [], [])
        with server._trade_jobs_lock:
            assert server._trade_jobs[job_id]["status"] == "complete", \
                server._trade_jobs[job_id].get("error")
        rows = _ue_rows(eng, "trades_generated")
        assert len(rows) == 1
        props = json.loads(rows[0]["props"])
        assert props["count"] == 0
        assert props["engine_version"] == "v1"   # all engine flags off
        assert props["lanes"] == {}
        assert isinstance(props["gen_ms"], int) and props["gen_ms"] >= 0
        assert rows[0]["league_id"] == LEAGUE
    finally:
        with server._trade_jobs_lock:
            server._trade_jobs.pop(job_id, None)


def test_calc_trade_evaluated_fires_for_device_identity(route_harness):
    client, eng, _ = route_harness
    r = client.post("/api/trade/evaluate",
                    headers={"Content-Type": "application/json",
                             "X-Device-Id": "dev_calc_test"},
                    data=json.dumps({"give_player_ids": ["nope-1"],
                                     "receive_player_ids": ["nope-2"]}))
    assert r.status_code == 200
    rows = _ue_rows(eng, "calc_trade_evaluated")
    assert len(rows) == 1
    assert rows[0]["user_id"] == "device:dev_calc_test"   # pre-auth lineage
    props = json.loads(rows[0]["props"])
    assert props["mode"] == "consensus"
    assert props["asset_count"] == 0                      # unknown ids dropped
    assert "verdict" in props


# ---------------------------------------------------------------------------
# (f) taxonomy namespace assertion
# ---------------------------------------------------------------------------

def test_namespace_assertion_trips_on_collision():
    from backend.analytics_taxonomy import _assert_namespaces_disjoint
    with pytest.raises(ValueError, match="tier_save"):
        _assert_namespaces_disjoint(frozenset({"tier_save", "app_opened"}),
                                    frozenset({"tier_save"}))
    # Disjoint sets pass silently.
    _assert_namespaces_disjoint(frozenset({"app_opened"}),
                                frozenset({"tier_save"}))


def test_live_taxonomy_is_disjoint():
    import backend.analytics_taxonomy as tax
    import backend.analytics_ingest as ingest
    assert not (tax.ALLOWED_CLIENT_EVENTS & tax._SERVER_AUTHORITATIVE)
    # The moved allowlist kept every v0 name (incl. onboarding-conversion).
    assert {"app_opened", "signin_attempted", "quickset_prompt_shown",
            "trade_card_shared", "deck_exhausted_viewed"} <= tax.ALLOWED_CLIENT_EVENTS
    # P1: the ingest pipeline (not server.py) owns the allowlist import.
    assert ingest.ALLOWED_CLIENT_EVENTS is tax.ALLOWED_CLIENT_EVENTS


# ---------------------------------------------------------------------------
# (g) health route
# ---------------------------------------------------------------------------

def test_analytics_health_route(tmp_path):
    import backend.analytics_ingest as ingest
    eng = _file_engine(tmp_path, with_wal_listener=True)
    server.app.config["TESTING"] = True
    client = server.app.test_client()
    with patch.object(db_module, "engine", eng), \
         patch.object(db_module, "ingest_engine", eng), \
         patch.object(ingest, "is_enabled", lambda k: k == "analytics.ingest"), \
         patch.object(server, "_CRON_SECRET", ""), \
         patch.object(server, "_IS_PROD_ENV", False):
        with ingest._rate_lock:
            ingest._events_rate.clear()
        before = client.get("/api/admin/analytics/health").get_json()
        # One accepted event + one unknown-type drop (P1 envelopes: 8+ char
        # event_id/session_id + seq).
        r = client.post("/api/events",
                        headers={"Content-Type": "application/json",
                                 "X-Device-Id": "dev_health"},
                        data=json.dumps({"events": [
                            {"event_id": "health-01", "event_type": "app_opened",
                             "session_id": "sess-health-1", "seq": 1},
                            {"event_id": "health-02", "event_type": "not_a_thing",
                             "session_id": "sess-health-1", "seq": 2},
                        ]}))
        assert r.status_code == 200
        after = client.get("/api/admin/analytics/health").get_json()

    assert after["since"] == "deploy"
    assert after["wal"] is True
    assert after["event_id_index_present"] is True
    assert after["wal_file_bytes"] is not None
    c0, c1 = before["counters"], after["counters"]
    # accepted counts the inserted app_opened AND the accepted-and-dropped unknown.
    assert c1["accepted"] == c0["accepted"] + 2
    assert c1["dropped_unknown_type"] == c0["dropped_unknown_type"] + 1
    for key in ("dropped_rate_limited", "rejected", "txn_failed", "deduped"):
        assert key in c1
