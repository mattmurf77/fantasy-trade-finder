"""Account deletion serializes durable restoration and rejects stale heartbeats."""
import threading
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine

from backend import accounts, database as db, server

UID = "synthetic-deletion-race-owner"
TOKEN = "synthetic-deletion-caller"
RESTORE = "synthetic-paused-restore"


@pytest.fixture
def env(tmp_path, monkeypatch):
    engine = create_engine("sqlite:///" + str(tmp_path / "race.db"),
                           connect_args={"check_same_thread": False})
    db.metadata.create_all(engine)
    monkeypatch.setattr(db, "engine", engine)
    monkeypatch.setattr(server, "is_enabled", lambda key: key == "auth.persistent_sessions")
    monkeypatch.setattr(accounts, "has_apple_identity", lambda *args, **kw: False)
    sess = {"user_id": UID, "verified": True, "verified_via": "sleeper",
            "last_active": 0.0}
    with server._sessions_lock:
        server._sessions[TOKEN] = sess
    db.persist_session(TOKEN, user_id=UID, verified_via="sleeper")
    db.persist_session(RESTORE, user_id=UID, verified_via="sleeper")
    yield server.app.test_client(), sess
    with server._sessions_lock:
        server._sessions.pop(TOKEN, None)
        server._sessions.pop(RESTORE, None)
    engine.dispose()


def test_paused_restore_cannot_resurrect_after_deletion(env):
    client, _ = env
    read = threading.Event()
    resume = threading.Event()
    original = db.load_persisted_session
    calls = []
    result = []

    def paused_load(token):
        row = original(token)
        if token == RESTORE and not calls:
            calls.append(token)
            read.set()
            assert resume.wait(5)
        return row

    with patch.object(server, "load_persisted_session", paused_load), \
         patch.object(server, "_extension_build_session") as builder:
        thread = threading.Thread(target=lambda: result.append(server._get_session(RESTORE)))
        thread.start()
        try:
            assert read.wait(5)
            response = client.delete("/api/account", headers={"X-Session-Token": TOKEN})
            assert response.status_code == 200
        finally:
            resume.set()
            thread.join(5)
        assert not thread.is_alive()
        assert result == [None]
        builder.assert_not_called()
        assert db.load_persisted_session(RESTORE) is None
        assert RESTORE not in server._sessions


def test_reference_retained_by_inflight_request_cannot_repersist_deleted_session(env):
    client, stale_sess = env
    response = client.delete("/api/account", headers={"X-Session-Token": TOKEN})
    assert response.status_code == 200
    assert stale_sess["_revoked"] is True
    server._persist_session_if_eligible(TOKEN, stale_sess)
    assert db.load_persisted_session(TOKEN) is None
