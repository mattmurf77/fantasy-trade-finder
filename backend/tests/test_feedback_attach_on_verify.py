"""#360 QA P2-1 — a note sent before verify follows its session after verify.

An unverified POST /api/feedback is stored anonymously (user_id NULL, D-2(a)),
and /api/feedback/mine filters by user, so once the session verified, the
client's refreshStatuses saw a synced note missing from /mine and hid it.

head-eng's ruling: attach on verify, with proof that the note came from THIS
session, never by username. The proof is the session token (a bearer secret
that in-place verification keeps): the note stores sha256(token) as
app_feedback.session_key, and each in-place `sess["verified"] = True` calls
_attach_presession_feedback, which hashes the CURRENT request's token.

In-memory SQLite, injected sessions, oracle mocked; no network.
"""
import hashlib
import json
import pathlib
import re
import time
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, select

import backend.accounts as accounts
import backend.database as db_module
import backend.server as server
from backend.database import metadata, app_feedback_table

UID = "313560442465169408"
TOK_A = "tok-attach-session-a"      # unverified; sends the note, then verifies
TOK_B = "tok-attach-session-b"      # unverified, SAME user_id claim, other device
TOK_V = "tok-attach-verified"       # verified at post time


def _fake_jwt(claims):
    import base64

    def b64(d):
        return base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()
    return f"{b64({'alg': 'HS256'})}.{b64(claims)}.sig"


SLEEPER_JWT = _fake_jwt({"user_id": UID, "exp": int(time.time()) + 3600})


def _sha(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@pytest.fixture()
def harness(monkeypatch):
    from cryptography.fernet import Fernet
    monkeypatch.setenv("SLEEPER_TOKEN_KEY", Fernet.generate_key().decode())

    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False})
    metadata.create_all(engine)
    server.app.config["TESTING"] = True
    client = server.app.test_client()

    with patch.object(db_module, "engine", engine), \
         patch.object(server, "is_enabled", lambda k: k == "trade.send_in_sleeper"), \
         patch.object(server, "touch_user_activity", MagicMock()), \
         patch.object(server, "record_event", MagicMock()), \
         patch.object(server._sleeper_write, "verify_token_live",
                      MagicMock(return_value={"raw": {}})):
        with server._sessions_lock:
            for tok in (TOK_A, TOK_B):
                server._sessions[tok] = {"user_id": UID, "username": "me",
                                         "display_name": "Me",
                                         "active_format": "1qb_ppr", "last_active": 0.0}
            server._sessions[TOK_V] = {"verified": True, "user_id": UID, "username": "me",
                                       "display_name": "Me Verified",
                                       "active_format": "1qb_ppr", "last_active": 0.0}
        try:
            yield client, engine
        finally:
            with server._sessions_lock:
                for tok in (TOK_A, TOK_B, TOK_V):
                    server._sessions.pop(tok, None)


def _h(token=None):
    h = {"Content-Type": "application/json"}
    if token:
        h["X-Session-Token"] = token
    return h


def _post(client, token, client_id):
    return client.post("/api/feedback", headers=_h(token), data=json.dumps({
        "client_id": client_id, "screen": "Trades", "severity": "bug",
        "text": "note " + client_id, "client_created_at": "2026-10-26T12:00:00Z",
    }))


def _verify(client, token):
    return client.post("/api/sleeper/link", headers=_h(token),
                       data=json.dumps({"token": SLEEPER_JWT}))


def _rows(engine):
    with engine.connect() as conn:
        return {r.client_id: dict(r._mapping) for r in conn.execute(select(app_feedback_table))}


def _mine(client, token):
    r = client.get("/api/feedback/mine", headers=_h(token))
    return r.status_code, [i["client_id"] for i in (r.get_json() or {}).get("items", [])]


def test_1_unverified_post_stores_the_hash_never_the_raw_token(harness):
    client, engine = harness
    assert _post(client, TOK_A, "fb-a1").status_code == 201
    row = _rows(engine)["fb-a1"]
    assert row["user_id"] is None and row["username"] is None
    assert row["session_key"] == _sha(TOK_A)
    assert all(TOK_A not in str(v) for v in row.values()), row


def test_2_same_session_verifies_and_mine_lists_the_note(harness):
    client, engine = harness
    assert _post(client, TOK_A, "fb-a2").status_code == 201
    # Before verify: /mine is gated, so the client's refreshStatuses catch
    # keeps its persisted statuses rather than hiding the note.
    status, _ = _mine(client, TOK_A)
    assert status == 403

    r = _verify(client, TOK_A)
    assert r.status_code == 200 and r.get_json()["verified"] is True

    row = _rows(engine)["fb-a2"]
    assert row["user_id"] == UID and row["username"] == "Me"
    assert row["session_key"] is None
    status, ids = _mine(client, TOK_A)
    assert status == 200 and ids == ["fb-a2"]


def test_3_a_different_session_verifying_as_the_same_user_gets_nothing(harness):
    client, engine = harness
    assert _post(client, TOK_A, "fb-a3").status_code == 201
    r = _verify(client, TOK_B)            # same Sleeper user, other session
    assert r.status_code == 200 and r.get_json()["verified"] is True

    row = _rows(engine)["fb-a3"]
    assert row["user_id"] is None and row["session_key"] == _sha(TOK_A)
    status, ids = _mine(client, TOK_B)
    assert status == 200 and ids == []


def test_4_a_no_token_note_never_attaches(harness):
    client, engine = harness
    assert _post(client, None, "fb-anon").status_code == 201
    assert _rows(engine)["fb-anon"]["session_key"] is None
    assert _verify(client, TOK_A).status_code == 200
    row = _rows(engine)["fb-anon"]
    assert row["user_id"] is None and row["session_key"] is None


def test_5_a_verified_at_post_note_is_unchanged(harness):
    client, engine = harness
    assert _post(client, TOK_V, "fb-v").status_code == 201
    before = _rows(engine)["fb-v"]
    assert before["user_id"] == UID and before["username"] == "Me Verified"
    assert before["session_key"] is None
    assert _verify(client, TOK_A).status_code == 200
    assert _rows(engine)["fb-v"] == before


def test_6_an_attach_failure_never_fails_the_verify(harness, caplog):
    client, engine = harness
    assert _post(client, TOK_A, "fb-a6").status_code == 201
    with patch.object(server, "attach_session_feedback",
                      MagicMock(side_effect=RuntimeError("db down"))):
        r = _verify(client, TOK_A)
    assert r.status_code == 200 and r.get_json()["verified"] is True
    with server._sessions_lock:
        assert server._sessions[TOK_A]["verified"] is True
    assert accounts.get_user_verified_via(UID) == "sleeper"
    assert _rows(engine)["fb-a6"]["user_id"] is None       # not attached, not lost
    assert "attach on verify failed" in caplog.text


def test_7_reverifying_is_idempotent(harness):
    client, engine = harness
    assert _post(client, TOK_A, "fb-a7").status_code == 201
    assert _verify(client, TOK_A).status_code == 200
    first = _rows(engine)["fb-a7"]
    assert _verify(client, TOK_A).status_code == 200
    assert _rows(engine)["fb-a7"] == first
    assert db_module.attach_session_feedback(_sha(TOK_A), UID, "Me") == 0


def test_8_export_and_delete_cover_attached_notes(harness):
    client, engine = harness
    assert _post(client, TOK_A, "fb-a8").status_code == 201
    assert _verify(client, TOK_A).status_code == 200

    exported = accounts.export_user_data(UID)["tables"]["app_feedback"]
    assert [r["client_id"] for r in exported] == ["fb-a8"]
    assert all("session_key" not in r for r in exported)

    accounts.delete_user_data(UID)
    row = _rows(engine)["fb-a8"]
    assert row["user_id"] is None and row["username"] is None
    assert row["text"] == "[Removed following account deletion]"


def test_10_attach_never_moves_a_note_that_already_has_an_owner(harness):
    """The `user_id IS NULL` guard: no route path leaves a row with both an
    owner and a key (attach clears the key), so pin the DB contract itself."""
    client, engine = harness
    with engine.begin() as conn:
        conn.execute(app_feedback_table.insert().values(
            client_id="fb-owned", user_id="someone_else", username="Them",
            screen="Trades", severity="bug", text="theirs",
            created_at="2026-10-26T00:00:00Z", session_key=_sha(TOK_A)))
    assert db_module.attach_session_feedback(_sha(TOK_A), UID, "Me") == 0
    row = _rows(engine)["fb-owned"]
    assert row["user_id"] == "someone_else" and row["username"] == "Them"


def test_11_mfl_auth_link_never_attaches_for_an_unverified_session(harness):
    """release-lead delta QA D: the MFL hook is defensive. The route sits
    behind @_gate_unverified_write, so an unverified session is 403'd before
    its verify, even with the flag on and MFL accepting the login."""
    client, engine = harness
    assert _post(client, TOK_A, "fb-mfl-pre").status_code == 201
    from backend import mfl_service
    with patch.object(server, "is_enabled", lambda k: k in ("trade.send_in_sleeper", "mfl.auth_link")), \
         patch.object(mfl_service, "login", MagicMock(return_value={"cookie": "c"})), \
         patch.object(mfl_service, "fetch_my_leagues", MagicMock(return_value=[])):
        r = client.post("/api/mfl/auth-link", headers=_h(TOK_A),
                        data=json.dumps({"username": "u", "password": "p"}))
    assert r.status_code == 403 and r.get_json()["error"] == "verification_required"
    row = _rows(engine)["fb-mfl-pre"]
    assert row["user_id"] is None and row["session_key"] == _sha(TOK_A)


def test_9_every_in_place_verify_site_attaches():
    """Static pin: each in-place `sess["verified"] = True` in server.py is
    followed (within its block) by _attach_presession_feedback(sess). A new
    in-place verify site without the hook fails here. Sites that mint a NEW
    session (`payload["verified"] = True`) carry a new token, so no note can
    prove it came from them, and they are out of scope."""
    src = (pathlib.Path(server.__file__)).read_text(encoding="utf-8").split("\n")
    sites = [i for i, l in enumerate(src) if re.match(r'\s*sess\["verified"\]\s*=\s*True\s*$', l)]
    assert len(sites) == 4, [i + 1 for i in sites]
    missing = [i + 1 for i in sites
               if not any("_attach_presession_feedback(sess)" in l for l in src[i:i + 6])]
    assert missing == [], f"in-place verify without the attach hook at server.py:{missing}"
