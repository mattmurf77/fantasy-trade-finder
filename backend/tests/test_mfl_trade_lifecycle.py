"""Trade-lifecycle tests for the "Send in MFL" surface in backend/server.py:

  POST /api/trades/respond-mfl   — accept/reject/revoke a pending MFL trade
  GET  /api/mfl/pending-trades   — owner-restricted pending-trades read

Plus the mfl_service pendingTrades adapter (fetch + parse). Flask test client
+ isolated in-memory SQLite, real injected session, real encryption key.
Mocked: `mfl_write.respond_trade` and `mfl_service.fetch_pending_trades` —
zero live network, mirroring test_mfl_propose_route.py. Both routes ride the
SAME `trade.send_in_mfl` flag as propose (one send surface, one knob).
"""
import json
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine

import backend.database as db_module
import backend.mfl_service as mfl_service
import backend.mfl_write as mfl_write
import backend.server as server
from backend.database import metadata
from backend.mfl_service import MflAuthError, MflError
from backend.mfl_write import MflWriteAuthError, MflWriteError

USER = "313560442465169408"
LEAGUE = "62846"
MY_FID, THEIR_FID = "0001", "0005"
TRADE_ID = "44"


def _h(token):
    return {"X-Session-Token": token, "Content-Type": "application/json"}


def _respond_body(**over):
    body = {"league_id": LEAGUE, "trade_id": TRADE_ID, "response": "revoke"}
    body.update(over)
    return json.dumps(body)


@pytest.fixture()
def client(monkeypatch):
    from cryptography.fernet import Fernet
    monkeypatch.setenv("SLEEPER_TOKEN_KEY", Fernet.generate_key().decode())

    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False})
    metadata.create_all(engine)

    token = "sess-tok-mfl-lifecycle"
    sess = {"user_id": USER, "active_format": "1qb_ppr", "last_active": 0.0,
            "verified": True}

    server.app.config["TESTING"] = True
    c = server.app.test_client()

    with patch.object(db_module, "engine", engine), \
         patch.object(server, "is_enabled", lambda k: k == "trade.send_in_mfl"), \
         patch.object(server, "touch_user_activity", MagicMock()):
        db_module.upsert_platform_league(
            league_id=LEAGUE, user_id=USER, name="QA MFL League",
            platform="mfl", season=2026, auth="cookie", my_team=MY_FID,
            total_rosters=12, host="www76.myfantasyleague.com")
        db_module.upsert_mfl_credential(
            USER, "qa_mfl_user",
            server._sleeper_write.encrypt_token("MFL_USER_ID=abc123"), 2026)
        with server._sessions_lock:
            server._sessions[token] = sess
        try:
            yield c, token
        finally:
            with server._sessions_lock:
                server._sessions.pop(token, None)


# ---------------------------------------------------------------------------
# POST /api/trades/respond-mfl
# ---------------------------------------------------------------------------

def test_respond_happy_path_revoke(client):
    c, token = client
    fake = MagicMock(return_value={"status": "OK", "raw": "<status>OK</status>"})
    with patch.object(mfl_write, "respond_trade", fake):
        r = c.post("/api/trades/respond-mfl", headers=_h(token),
                   data=_respond_body())
    assert r.status_code == 200, r.get_data(as_text=True)
    body = r.get_json()
    assert body["status"] == "responded" and body["response"] == "revoke"
    (cookie, host, year, league_id, trade_id, response), kwargs = fake.call_args
    assert cookie == "MFL_USER_ID=abc123"
    assert host == "www76.myfantasyleague.com" and year == 2026
    assert league_id == LEAGUE and trade_id == TRADE_ID and response == "revoke"
    assert kwargs.get("comments") is None


def test_respond_accept_and_reject_pass_through(client):
    c, token = client
    for resp in ("accept", "reject"):
        fake = MagicMock(return_value={"status": "OK", "raw": ""})
        with patch.object(mfl_write, "respond_trade", fake):
            r = c.post("/api/trades/respond-mfl", headers=_h(token),
                       data=_respond_body(response=resp, comments="  hi  "))
        assert r.status_code == 200, r.get_data(as_text=True)
        (_, _, _, _, _, response), kwargs = fake.call_args
        assert response == resp and kwargs.get("comments") == "hi"


def test_respond_rejects_bad_input(client):
    c, token = client
    fake = MagicMock()
    with patch.object(mfl_write, "respond_trade", fake):
        # bad response verb
        r = c.post("/api/trades/respond-mfl", headers=_h(token),
                   data=_respond_body(response="counter"))
        assert r.status_code == 400 and r.get_json()["error"] == "bad_request"
        # missing trade id
        r = c.post("/api/trades/respond-mfl", headers=_h(token),
                   data=_respond_body(trade_id=""))
        assert r.status_code == 400
        # non-numeric league id
        r = c.post("/api/trades/respond-mfl", headers=_h(token),
                   data=_respond_body(league_id="not-a-league"))
        assert r.status_code == 400
    fake.assert_not_called()


def test_respond_requires_verified_session(client):
    c, token = client
    with server._sessions_lock:
        server._sessions[token]["verified"] = False
    r = c.post("/api/trades/respond-mfl", headers=_h(token), data=_respond_body())
    assert r.status_code == 403
    assert r.get_json()["error"] == "verification_required"


def test_respond_feature_off_returns_404(client):
    c, token = client
    with patch.object(server, "is_enabled", lambda k: False):
        r = c.post("/api/trades/respond-mfl", headers=_h(token),
                   data=_respond_body())
    assert r.status_code == 404 and r.get_json()["error"] == "feature_disabled"


def test_respond_unlinked_league_returns_404(client):
    c, token = client
    r = c.post("/api/trades/respond-mfl", headers=_h(token),
               data=_respond_body(league_id="99999"))
    assert r.status_code == 404 and r.get_json()["error"] == "mfl_not_linked"


def test_respond_no_cookie_returns_409_not_connected(client):
    c, token = client
    db_module.delete_mfl_credential(USER)
    r = c.post("/api/trades/respond-mfl", headers=_h(token), data=_respond_body())
    assert r.status_code == 409 and r.get_json()["error"] == "mfl_not_connected"


def test_respond_expired_cookie_drops_credential_returns_409(client):
    c, token = client
    with patch.object(mfl_write, "respond_trade",
                      MagicMock(side_effect=MflWriteAuthError(detail="HTTP 403"))):
        r = c.post("/api/trades/respond-mfl", headers=_h(token),
                   data=_respond_body())
    assert r.status_code == 409 and r.get_json()["error"] == "mfl_auth_expired"
    assert db_module.get_mfl_credential(USER) is None


def test_respond_write_failure_returns_502(client):
    c, token = client
    with patch.object(mfl_write, "respond_trade",
                      MagicMock(side_effect=MflWriteError("boom", kind="network"))):
        r = c.post("/api/trades/respond-mfl", headers=_h(token),
                   data=_respond_body())
    assert r.status_code == 502 and r.get_json()["error"] == "mfl_write_failed"


# ---------------------------------------------------------------------------
# trade_responded analytics — confirmed success only, platform non-null
# ---------------------------------------------------------------------------

def _trade_responded_rows():
    from sqlalchemy import select
    with db_module.engine.connect() as conn:
        rows = conn.execute(
            select(db_module.user_events_table)
            .where(db_module.user_events_table.c.event_type == "trade_responded")
        ).fetchall()
    return [dict(r._mapping) for r in rows]


def test_respond_success_fires_trade_responded(client):
    c, token = client
    with patch.object(mfl_write, "respond_trade",
                      MagicMock(return_value={"status": "OK", "raw": ""})):
        r = c.post("/api/trades/respond-mfl", headers=_h(token),
                   data=_respond_body(response="accept"))
    assert r.status_code == 200, r.get_data(as_text=True)
    rows = _trade_responded_rows()
    assert len(rows) == 1
    assert rows[0]["user_id"] == USER and rows[0]["league_id"] == LEAGUE
    props = json.loads(rows[0]["props"])
    assert props["platform"] == "mfl"                 # mandatory, non-null
    assert props["response"] == "accept"
    assert props["outcome"] == "accepted"
    assert "trade_id" not in props                    # no MFL identifiers in props


def test_respond_failure_fires_no_trade_responded(client):
    c, token = client
    with patch.object(mfl_write, "respond_trade",
                      MagicMock(side_effect=MflWriteError("nope"))):
        r = c.post("/api/trades/respond-mfl", headers=_h(token),
                   data=_respond_body())
    assert r.status_code == 502
    assert _trade_responded_rows() == []


def test_trade_responded_is_registered_server_fired():
    from backend.analytics_taxonomy import (ALLOWED_CLIENT_EVENTS,
                                            SERVER_FIRED_EVENTS)
    assert "trade_responded" in SERVER_FIRED_EVENTS
    assert "trade_responded" not in ALLOWED_CLIENT_EVENTS   # never client-forgeable


# ---------------------------------------------------------------------------
# mfl_service pendingTrades adapter (fetch + parse) — fixtures, zero network
# ---------------------------------------------------------------------------

_PENDING_EXPORT = {"pendingTrades": {"pendingTrade": [
    {"trade_id": TRADE_ID, "offeringteam": MY_FID, "offeredto": THEIR_FID,
     "will_give_up": "13130,FP_0005_2027_1,", "will_receive": "14085,",
     "comments": "from FTF", "expires": "1760000000"},
]}}


def test_fetch_pending_trades_requires_cookie():
    with pytest.raises(MflAuthError):
        mfl_service.fetch_pending_trades(LEAGUE, 2026,
                                         "www76.myfantasyleague.com", "")


def test_fetch_pending_trades_rejects_bad_league_id():
    with pytest.raises(MflError):
        mfl_service.fetch_pending_trades("not-numeric", 2026,
                                         "www76.myfantasyleague.com",
                                         "MFL_USER_ID=x")


def test_fetch_pending_trades_hits_pendingtrades_export_with_cookie():
    seen = {}

    def opener(req, timeout=None):
        seen["url"] = req.full_url
        seen["cookie"] = req.headers.get("Cookie")

        class _Resp:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return json.dumps(_PENDING_EXPORT).encode()

        return _Resp()

    out = mfl_service.fetch_pending_trades(
        LEAGUE, 2026, "www76.myfantasyleague.com", "MFL_USER_ID=abc123",
        _opener=opener)
    assert "TYPE=pendingTrades" in seen["url"]
    assert seen["url"].startswith("https://www76.myfantasyleague.com/2026/export")
    assert seen["cookie"] == "MFL_USER_ID=abc123"
    assert out == _PENDING_EXPORT


def test_parse_pending_trades_splits_assets_and_trailing_commas():
    trades = mfl_service.parse_pending_trades(_PENDING_EXPORT)
    assert len(trades) == 1
    t = trades[0]
    assert t["trade_id"] == TRADE_ID
    assert t["offering_team"] == MY_FID and t["offered_to"] == THEIR_FID
    assert t["will_give_up"] == ["13130", "FP_0005_2027_1"]
    assert t["will_receive"] == ["14085"]
    assert t["comments"] == "from FTF"
    assert t["expires"] == 1760000000


def test_parse_pending_trades_single_dict_collapse_and_junk():
    # MFL collapses single-member collections to a bare dict; junk rows and
    # rows without a trade_id are skipped.
    raw = {"pendingTrades": {"pendingTrade": {
        "trade_id": "7", "offeringteam": THEIR_FID, "offeredto": MY_FID,
        "will_give_up": "", "will_receive": "14085"}}}
    trades = mfl_service.parse_pending_trades(raw)
    assert len(trades) == 1
    assert trades[0]["will_give_up"] == []
    assert trades[0]["expires"] is None
    assert mfl_service.parse_pending_trades({}) == []
    assert mfl_service.parse_pending_trades(
        {"pendingTrades": {"pendingTrade": [{"offeringteam": "0002"}]}}) == []


# ---------------------------------------------------------------------------
# GET /api/mfl/pending-trades
# ---------------------------------------------------------------------------

def test_pending_trades_route_happy_path(client):
    c, token = client
    with patch.object(mfl_service, "fetch_pending_trades",
                      MagicMock(return_value=_PENDING_EXPORT)) as fake:
        r = c.get(f"/api/mfl/pending-trades?league_id={LEAGUE}",
                  headers=_h(token))
    assert r.status_code == 200, r.get_data(as_text=True)
    body = r.get_json()
    assert body["my_franchise_id"] == MY_FID
    assert len(body["trades"]) == 1
    assert body["trades"][0]["trade_id"] == TRADE_ID
    args, _ = fake.call_args
    assert args[0] == LEAGUE and args[2] == "www76.myfantasyleague.com"
    assert args[3] == "MFL_USER_ID=abc123"          # cookie rode the fetch


def test_pending_trades_route_feature_off_returns_404(client):
    c, token = client
    with patch.object(server, "is_enabled", lambda k: False):
        r = c.get(f"/api/mfl/pending-trades?league_id={LEAGUE}",
                  headers=_h(token))
    assert r.status_code == 404 and r.get_json()["error"] == "feature_disabled"


def test_pending_trades_route_unlinked_returns_404(client):
    c, token = client
    r = c.get("/api/mfl/pending-trades?league_id=99999", headers=_h(token))
    assert r.status_code == 404 and r.get_json()["error"] == "mfl_not_linked"


def test_pending_trades_route_no_cookie_returns_409(client):
    c, token = client
    db_module.delete_mfl_credential(USER)
    r = c.get(f"/api/mfl/pending-trades?league_id={LEAGUE}", headers=_h(token))
    assert r.status_code == 409 and r.get_json()["error"] == "mfl_not_connected"


def test_pending_trades_route_auth_expired_drops_credential(client):
    c, token = client
    with patch.object(mfl_service, "fetch_pending_trades",
                      MagicMock(side_effect=MflAuthError())):
        r = c.get(f"/api/mfl/pending-trades?league_id={LEAGUE}",
                  headers=_h(token))
    assert r.status_code == 409 and r.get_json()["error"] == "mfl_auth_expired"
    assert db_module.get_mfl_credential(USER) is None
