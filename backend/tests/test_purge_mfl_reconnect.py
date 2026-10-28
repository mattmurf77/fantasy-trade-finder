"""Legal R28.17 A1: after the purge's --delete-verified-credentials removes a
verified entry:mfl user's mfl_credentials row, the app degrades readably.

The user keeps their account and session. Pinned here, server side, with the
row gone:
  - GET /api/mfl/auth-link reports {connected: false}. Mobile's
    SendInMflButton reads it first and shows "Sign in with MFL to send trades".
  - GET /api/mfl/leagues still lists the league from the stored snapshot
    (mobile's league read), so there's no error to show.
  - POST /api/trades/propose-mfl answers 409 mfl_not_connected with its
    readable message, never a 500. Mobile maps that code to its "Sign in with
    MFL" alert, pinned by mobile/tests/check-send-button-platform.js.

Fixture modelled on test_mfl_propose_route.py, with the purge's real case: a
verified entry:mfl user (verified_via mfl_login) and a cookie-auth league.
"""
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, delete, insert, select

import backend.database as db_module
import backend.server as server
from backend.database import metadata
from backend.tests import test_mfl_propose_route as mfl_t

LEAGUE, MY_FID = mfl_t.LEAGUE, mfl_t.MY_FID
ENTRY_USER = f"entry:mfl:{LEAGUE}.f{MY_FID}"
FLAGS = {"trade.send_in_mfl", "mfl.link", "mfl.auth_link"}


@pytest.fixture()
def client(monkeypatch):
    from cryptography.fernet import Fernet
    monkeypatch.setenv("SLEEPER_TOKEN_KEY", Fernet.generate_key().decode())
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    metadata.create_all(engine)
    token = "sess-tok-entry-mfl"
    sess = {"user_id": ENTRY_USER, "active_format": "1qb_ppr", "last_active": 0.0,
            "verified": True, "verified_via": "mfl_login"}
    server.app.config["TESTING"] = True
    server._mfl_reverse_xwalk_cache = None
    c = server.app.test_client()
    import backend.mfl_service as mfl_service
    with patch.object(db_module, "engine", engine), \
         patch.object(server, "is_enabled", lambda k: k in FLAGS), \
         patch.object(server, "_shared_crosswalk", lambda: mfl_t._FAKE_XWALK), \
         patch.object(server, "touch_user_activity", MagicMock()), \
         patch.object(mfl_service, "fetch_rosters", MagicMock(return_value=mfl_t._ROSTERS_EXPORT)), \
         patch.object(mfl_service, "fetch_future_draft_picks",
                      MagicMock(return_value=mfl_t._FUTURE_PICKS_EXPORT)), \
         patch.object(mfl_service, "fetch_scoring_inputs", MagicMock(return_value={})):
        db_module.upsert_platform_league(
            league_id=LEAGUE, user_id=ENTRY_USER, name="QA MFL League", platform="mfl",
            season=2026, auth="cookie", my_team=MY_FID, total_rosters=12,
            host="www76.myfantasyleague.com", future_picks=mfl_t.FUTURE_PICKS)
        with engine.begin() as conn:      # the membership a real link writes
            conn.execute(insert(db_module.league_members_table).values(
                league_id=LEAGUE, user_id=ENTRY_USER, username="qa_mfl_user", roster_data="[]"))
        db_module.upsert_mfl_credential(
            ENTRY_USER, "qa_mfl_user",
            server._sleeper_write.encrypt_token("MFL_USER_ID=abc123"), 2026)
        with server._sessions_lock:
            server._sessions[token] = sess
        try:
            yield c, token, engine
        finally:
            with server._sessions_lock:
                server._sessions.pop(token, None)
            server._mfl_reverse_xwalk_cache = None


def test_with_the_credential_row_gone_the_next_read_and_send_read_as_sign_in_again(client):
    c, token, engine = client
    assert c.get("/api/mfl/auth-link", headers=mfl_t._h(token)).get_json()["connected"] is True
    # What --delete-verified-credentials does: that one row, nothing else.
    creds = db_module.mfl_credentials_table
    with engine.begin() as conn:
        conn.execute(delete(creds).where(creds.c.user_id == ENTRY_USER))
        assert conn.execute(select(creds)).all() == []

    status = c.get("/api/mfl/auth-link", headers=mfl_t._h(token))
    assert status.status_code == 200 and status.get_json()["connected"] is False

    leagues = c.get("/api/mfl/leagues", headers=mfl_t._h(token))
    assert leagues.status_code == 200
    assert [lg["league_id"] for lg in leagues.get_json()["leagues"]] == [LEAGUE]

    sent = c.post("/api/trades/propose-mfl", headers=mfl_t._h(token), data=mfl_t._propose_body())
    assert sent.status_code == 409
    body = sent.get_json()
    assert body["error"] == "mfl_not_connected"
    assert body["message"] == "Sign in with MFL first."
