"""Launch QA — regression tests for the Phase 4 fix batch (2026-06-11).

Each test pins a confirmed pre-launch finding so it can't silently regress:

  P0  admin config routes require X-Cron-Secret               (test_admin_*)
  P1  /api/debug/log requires X-Cron-Secret                   (test_debug_log_*)
  P1  league-backed routes 409 (not 500) before session/init  (test_session_not_init_*)
  P1  notifications reject a mismatched user_id (IDOR)         (test_notifications_*)
  P2  test_user_fp_* login bypass disabled in production       (test_test_user_bypass_*)
  P2  engine-metrics / feature-flags-reload require auth       (test_engine_metrics_*, test_flags_reload_*)
  P2  Sleeper 5xx → 503 (not a "User not found" dead end)      (test_sleeper_user_*)

Routing/auth is exercised through Flask's test client; handler side-effects
(DB, config writes, Sleeper calls) are mocked so each test stays on its target.
"""
import json
import urllib.error
from unittest.mock import patch, MagicMock

import pytest

import backend.server as server
from backend.ranking_service import RankingService, Player
from backend.trade_service import League, LeagueMember


ME = "user_me"
OTHER = "user_other"
SECRET = "unit-test-cron-secret"


@pytest.fixture()
def client():
    server.app.config["TESTING"] = True
    return server.app.test_client()


def _put_session(token, sess):
    with server._sessions_lock:
        server._sessions[token] = sess


def _drop_session(token):
    with server._sessions_lock:
        server._sessions.pop(token, None)


# ---------------------------------------------------------------------------
# Helpers to build sessions
# ---------------------------------------------------------------------------

def _bare_session():
    """What /api/extension/auth mints before /api/session/init runs:
    a valid session with NO league / players / trade services."""
    svc = RankingService(players=[Player(id="p1", name="P1", position="RB",
                                         team="AAA", age=25)])
    return {
        "user_id":       ME,
        "services":      {"1qb_ppr": svc},
        "service":       svc,
        "active_format": "1qb_ppr",
        "last_active":   0.0,
    }


def _initialized_session():
    sess = _bare_session()
    league = League(league_id="L1", name="L1", platform="sleeper",
                    members=[LeagueMember(user_id=ME, username="me",
                                          roster=[], elo_ratings={})])
    sess["league"]     = league
    sess["players"]    = [Player(id="p1", name="P1", position="RB",
                                 team="AAA", age=25)]
    sess["trade_svcs"] = {"1qb_ppr": MagicMock()}
    return sess


# ===========================================================================
# P0 — admin config routes require X-Cron-Secret
# ===========================================================================

def test_admin_config_get_unauthenticated_is_401(client):
    with patch.object(server, "_CRON_SECRET", SECRET), \
         patch.object(server, "_IS_PROD_ENV", True):
        resp = client.get("/api/admin/config")
    assert resp.status_code == 401


def test_admin_config_put_unauthenticated_is_401(client):
    """The launch blocker: rewriting model_config must require auth."""
    set_config = MagicMock()
    with patch.object(server, "_CRON_SECRET", SECRET), \
         patch.object(server, "_IS_PROD_ENV", True), \
         patch.object(server, "set_config", set_config):
        resp = client.put("/api/admin/config/elo_k",
                          data=json.dumps({"value": 999}),
                          content_type="application/json")
    assert resp.status_code == 401
    # Critically, the unauthenticated request never reached the mutator.
    set_config.assert_not_called()


def test_admin_config_put_with_secret_passes_auth(client):
    set_config = MagicMock(return_value={"key": "elo_k", "value": 30.0})
    with patch.object(server, "_CRON_SECRET", SECRET), \
         patch.object(server, "_IS_PROD_ENV", True), \
         patch.object(server, "set_config", set_config), \
         patch.object(server._trade_service_mod, "reload_config", MagicMock()), \
         patch.object(server._ranking_service_mod, "reload_config", MagicMock()):
        resp = client.put("/api/admin/config/elo_k",
                          headers={"X-Cron-Secret": SECRET},
                          data=json.dumps({"value": 30}),
                          content_type="application/json")
    assert resp.status_code == 200
    set_config.assert_called_once()


def test_admin_config_wrong_secret_is_401(client):
    with patch.object(server, "_CRON_SECRET", SECRET), \
         patch.object(server, "_IS_PROD_ENV", True):
        resp = client.get("/api/admin/config",
                          headers={"X-Cron-Secret": "wrong"})
    assert resp.status_code == 401


def test_admin_config_prod_without_secret_fails_closed(client):
    """Misconfig (prod env, secret unset) must reject, not allow."""
    with patch.object(server, "_CRON_SECRET", ""), \
         patch.object(server, "_IS_PROD_ENV", True):
        resp = client.get("/api/admin/config")
    assert resp.status_code == 503


# ===========================================================================
# P1 — /api/debug/log requires X-Cron-Secret
# ===========================================================================

def test_debug_log_unauthenticated_is_401(client):
    with patch.object(server, "_CRON_SECRET", SECRET), \
         patch.object(server, "_IS_PROD_ENV", True):
        resp = client.get("/api/debug/log")
    assert resp.status_code == 401


def test_debug_log_with_secret_ok(client):
    with patch.object(server, "_CRON_SECRET", SECRET), \
         patch.object(server, "_IS_PROD_ENV", True):
        resp = client.get("/api/debug/log",
                          headers={"X-Cron-Secret": SECRET})
    assert resp.status_code == 200
    assert "entries" in resp.get_json()


# ===========================================================================
# P2 — engine-metrics + feature-flags/reload require auth
# ===========================================================================

def test_engine_metrics_unauthenticated_is_401(client):
    with patch.object(server, "_CRON_SECRET", SECRET), \
         patch.object(server, "_IS_PROD_ENV", True):
        resp = client.get("/api/admin/engine-metrics")
    assert resp.status_code == 401


def test_flags_reload_unauthenticated_is_401(client):
    reload_flags = MagicMock(return_value={})
    with patch.object(server, "_CRON_SECRET", SECRET), \
         patch.object(server, "_IS_PROD_ENV", True), \
         patch.object(server, "reload_flags", reload_flags):
        resp = client.post("/api/feature-flags/reload")
    assert resp.status_code == 401
    reload_flags.assert_not_called()


# ===========================================================================
# P1 — league-backed routes return 409 (not 500) before /api/session/init
# ===========================================================================

def test_require_initialized_session_raises_for_bare_session(client):
    token = "qa-bare"
    _put_session(token, _bare_session())
    try:
        with server.app.test_request_context(
                headers={"X-Session-Token": token}):
            with pytest.raises(server._SessionNotInitialized):
                server._require_initialized_session()
    finally:
        _drop_session(token)


def test_require_initialized_session_passes_for_complete_session(client):
    token = "qa-init"
    _put_session(token, _initialized_session())
    try:
        with server.app.test_request_context(
                headers={"X-Session-Token": token}):
            sess = server._require_initialized_session()
            assert sess["user_id"] == ME
    finally:
        _drop_session(token)


def test_league_route_returns_409_before_init(client):
    """A real route, end to end: bare session → structured 409, not a 500."""
    token = "qa-bare-route"
    _put_session(token, _bare_session())
    try:
        resp = client.get("/api/league/summary",
                          headers={"X-Session-Token": token})
    finally:
        _drop_session(token)
    assert resp.status_code == 409
    assert resp.get_json()["error"] == "session_not_initialized"


def test_missing_session_still_401(client):
    """The init gate must not mask the expired/missing-session 401."""
    resp = client.get("/api/league/summary",
                      headers={"X-Session-Token": "nonexistent"})
    assert resp.status_code == 401
    assert resp.get_json()["error"] == "session_expired"


# ===========================================================================
# P1 — notifications reject a mismatched user_id (IDOR)
# ===========================================================================

def test_notifications_reject_other_users_id(client):
    token = "qa-notif"
    _put_session(token, _bare_session())
    get_notifs = MagicMock(return_value=[])
    try:
        with patch.object(server, "get_notifications", get_notifs):
            resp = client.get(f"/api/notifications?user_id={OTHER}",
                              headers={"X-Session-Token": token})
    finally:
        _drop_session(token)
    assert resp.status_code == 403
    # Never fetched the victim's notifications.
    get_notifs.assert_not_called()


def test_notifications_allow_own_id(client):
    token = "qa-notif-own"
    _put_session(token, _bare_session())
    get_notifs = MagicMock(return_value=[])
    try:
        with patch.object(server, "get_notifications", get_notifs):
            resp = client.get(f"/api/notifications?user_id={ME}",
                              headers={"X-Session-Token": token})
    finally:
        _drop_session(token)
    assert resp.status_code == 200
    get_notifs.assert_called_once_with(ME)


def test_notifications_read_rejects_other_users_id(client):
    token = "qa-notif-read"
    _put_session(token, _bare_session())
    mark = MagicMock(return_value=0)
    try:
        with patch.object(server, "mark_notifications_read", mark):
            resp = client.post("/api/notifications/read",
                               headers={"X-Session-Token": token},
                               data=json.dumps({"user_id": OTHER, "ids": [1]}),
                               content_type="application/json")
    finally:
        _drop_session(token)
    assert resp.status_code == 403
    mark.assert_not_called()


# ===========================================================================
# P2 — test_user_fp_* login bypass disabled in production
# ===========================================================================

def test_test_user_bypass_blocked_in_prod(client):
    with patch.object(server, "_IS_PROD_ENV", True):
        resp = client.get("/api/sleeper/user/test_user_fp_1")
    assert resp.status_code == 404


def test_test_user_bypass_works_in_dev(client):
    with patch.object(server, "_IS_PROD_ENV", False):
        resp = client.get("/api/sleeper/user/test_user_fp_1")
    assert resp.status_code == 200
    assert resp.get_json()["user_id"] == "test_user_fp_1"


# ===========================================================================
# P2 — Sleeper 5xx → 503 (not a misleading "User not found")
# ===========================================================================

def _http_error(code):
    return urllib.error.HTTPError(
        url="https://api.sleeper.app", code=code, msg="boom", hdrs=None, fp=None)


def test_sleeper_user_5xx_maps_to_503(client):
    with patch.object(server, "_IS_PROD_ENV", False), \
         patch.object(server, "_sleeper_get",
                      MagicMock(side_effect=_http_error(503))):
        resp = client.get("/api/sleeper/user/somebody")
    assert resp.status_code == 503
    assert resp.get_json()["error"] == "sleeper_unavailable"


def test_sleeper_user_4xx_still_404(client):
    with patch.object(server, "_IS_PROD_ENV", False), \
         patch.object(server, "_sleeper_get",
                      MagicMock(side_effect=_http_error(404))):
        resp = client.get("/api/sleeper/user/nosuchuser")
    assert resp.status_code == 404
    assert resp.get_json()["error"] == "User not found"


def test_sleeper_leagues_outage_maps_to_503(client):
    with patch.object(server, "_sleeper_get",
                      MagicMock(side_effect=_http_error(502))), \
         patch.object(server, "load_local_leagues_for_user",
                      MagicMock(return_value=[])):
        resp = client.get("/api/sleeper/leagues/12345")
    assert resp.status_code == 503
    assert resp.get_json()["error"] == "sleeper_unavailable"


# ===========================================================================
# Phase 3 — input-validation 500s found by the live smoke tester (R7)
# ===========================================================================

def test_rosters_sleeper_404_maps_to_404_no_leak(client):
    """A digit league_id that Sleeper 404s must be a clean 404, not a 500
    that leaks the raw upstream error string."""
    with patch.object(server, "_sleeper_get",
                      MagicMock(side_effect=_http_error(404))):
        resp = client.get("/api/sleeper/rosters/99999999")
    assert resp.status_code == 404
    body = resp.get_json()
    assert body["error"] == "league_not_found"
    assert "HTTP Error" not in json.dumps(body)  # no upstream leak


def test_rosters_sleeper_5xx_maps_to_503(client):
    with patch.object(server, "_sleeper_get",
                      MagicMock(side_effect=_http_error(503))):
        resp = client.get("/api/sleeper/rosters/12345")
    assert resp.status_code == 503
    assert resp.get_json()["error"] == "sleeper_unavailable"


def test_notifications_read_non_list_ids_is_400(client):
    """A non-list 'ids' must be rejected before reaching the DB layer."""
    token = "qa-notif-badids"
    _put_session(token, _bare_session())
    mark = MagicMock(return_value=0)
    try:
        with patch.object(server, "mark_notifications_read", mark):
            resp = client.post("/api/notifications/read",
                               headers={"X-Session-Token": token},
                               data=json.dumps({"ids": "not-a-list"}),
                               content_type="application/json")
    finally:
        _drop_session(token)
    assert resp.status_code == 400
    mark.assert_not_called()


def test_notifications_read_non_int_ids_is_400(client):
    token = "qa-notif-badids2"
    _put_session(token, _bare_session())
    mark = MagicMock(return_value=0)
    try:
        with patch.object(server, "mark_notifications_read", mark):
            resp = client.post("/api/notifications/read",
                               headers={"X-Session-Token": token},
                               data=json.dumps({"ids": ["abc"]}),
                               content_type="application/json")
    finally:
        _drop_session(token)
    assert resp.status_code == 400
    mark.assert_not_called()


def test_debug_log_bad_n_is_400(client):
    with patch.object(server, "_CRON_SECRET", SECRET), \
         patch.object(server, "_IS_PROD_ENV", True):
        resp = client.get("/api/debug/log?n=abc",
                          headers={"X-Cron-Secret": SECRET})
    assert resp.status_code == 400
