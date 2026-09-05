"""Analytics token disclosure: one-way correlation, targeted offline cleanup and dry-run safety."""
import hashlib
import sqlite3

import pytest
from sqlalchemy import create_engine, select

from backend import database as db
from scripts.remediate_analytics_tokens import remediate


@pytest.fixture
def event_db(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    db.metadata.create_all(engine)
    monkeypatch.setattr(db, "engine", engine)
    yield engine
    engine.dispose()


def test_record_event_never_stores_bearer(event_db):
    token = "synthetic-bearer-only-for-test"
    for kind in ("signup", "app_open", "league_synced"):
        db.record_event("tester", kind, session_id=token)
    with event_db.connect() as conn:
        ids = conn.execute(select(db.user_events_table.c.session_id)).scalars().all()
    assert len(ids) == 3
    assert set(ids) == {db.analytics_session_id(token)}
    assert token not in ids[0]
    assert ids[0] != db.session_token_hash(token)
    assert ids[0] != db.analytics_session_id("different-token")


def test_identifier_none_and_prefix_cannot_bypass_hashing():
    assert db.analytics_session_id(None) is None
    encoded = db.analytics_session_id("secret")
    assert db.analytics_session_id(encoded) != encoded


@pytest.fixture
def historical_db(tmp_path):
    path = tmp_path / "synthetic.db"
    with sqlite3.connect(path) as conn:
        conn.executescript("CREATE TABLE sessions(token_hash TEXT PRIMARY KEY); "
                           "CREATE TABLE user_events(session_id TEXT, source TEXT, event_type TEXT);")
        conn.executemany("INSERT INTO sessions VALUES (?)", [
            (hashlib.sha256(token.encode()).hexdigest(),) for token in ("exposed", "unexposed")
        ])
        conn.executemany("INSERT INTO user_events VALUES (?, ?, ?)", [
            ("exposed", "api", "signup"), ("exposed", "mobile", "screen_view"),
            ("expired", "api", "league_synced"), ("device-session", "mobile", "screen_view"),
            (db.analytics_session_id("new-token"), "api", "signup"),
        ])
    return path


def snapshot(path):
    with sqlite3.connect(path) as conn:
        return (conn.execute("SELECT * FROM user_events").fetchall(),
                conn.execute("SELECT * FROM sessions").fetchall())


def test_dry_run_does_not_modify_or_disclose(historical_db):
    before = snapshot(historical_db)
    result = remediate(historical_db)
    assert result == {"mode": "dry_run", "event_rows": 3, "distinct_identifiers": 2,
                      "durable_sessions_to_revoke": 1}
    assert snapshot(historical_db) == before
    assert "exposed" not in str(result)


def test_apply_scrubs_duplicates_revokes_only_exposed_and_is_idempotent(historical_db):
    result = remediate(historical_db, apply=True)
    assert result["durable_sessions_revoked"] == 1
    events, sessions = snapshot(historical_db)
    assert [r[0] for r in events[:3]] == [None, None, None]
    assert events[3][0] == "device-session"
    assert events[4][0].startswith("analytics_v1:")
    assert sessions == [(hashlib.sha256(b"unexposed").hexdigest(),)]
    assert remediate(historical_db, apply=True)["event_rows"] == 0


def test_missing_file_is_not_created(tmp_path):
    path = tmp_path / "missing.db"
    with pytest.raises(FileNotFoundError):
        remediate(path, apply=True)
    assert not path.exists()


def test_failure_rolls_back_scrub_and_revocation(historical_db):
    with sqlite3.connect(historical_db) as conn:
        conn.execute("CREATE TRIGGER deny_revoke BEFORE DELETE ON sessions "
                     "BEGIN SELECT RAISE(ABORT, 'synthetic failure'); END")
    before = snapshot(historical_db)
    with pytest.raises(Exception, match="synthetic failure"):
        remediate(historical_db, apply=True)
    assert snapshot(historical_db) == before


def test_explicit_url_and_no_credential_bearing_backup(historical_db):
    before_files = set(historical_db.parent.iterdir())
    assert remediate("sqlite:///" + str(historical_db))["event_rows"] == 3
    assert set(historical_db.parent.iterdir()) == before_files
