"""Teardown S7 PRD-01 follow-up (W3B task 3) — share landing for arbitrary
packages, flag `growth.share_landing`.

POST /api/share/package (session-authed, rate-limited) stores a compact
give/receive snapshot → /s/p/<short_id> public landing + /og/p/<id>.png
card. All three surfaces 404 while the flag is dark.
"""
import json
import time
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine

import backend.database as db_module
import backend.server as server
from backend.database import metadata

USER = "888888888800000001"
TOKEN = "sess-share-pkg-test"


def _flags(*enabled):
    on = set(enabled)
    return lambda k: k in on


def _h():
    return {"X-Session-Token": TOKEN, "Content-Type": "application/json"}


def _post(c, body):
    return c.post("/api/share/package", headers=_h(), data=json.dumps(body))


GOOD_BODY = {"give_player_ids": ["4034", "6786"],
             "receive_player_ids": ["7564"]}


@pytest.fixture()
def env():
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False})
    metadata.create_all(engine)
    server.app.config["TESTING"] = True
    c = server.app.test_client()
    db_patch = patch.object(db_module, "engine", engine)
    db_patch.start()
    with server._sessions_lock:
        server._sessions[TOKEN] = {
            "user_id": USER, "active_format": "1qb_ppr",
            "last_active": time.time(),
        }
    try:
        yield c
    finally:
        with server._sessions_lock:
            server._sessions.pop(TOKEN, None)
        db_patch.stop()


def test_all_three_surfaces_404_while_dark(env):
    with patch.object(server, "is_enabled", _flags()):
        assert _post(env, GOOD_BODY).status_code == 404
        assert env.get("/s/p/abc123").status_code == 404
        assert env.get("/og/p/abc123.png").status_code == 404


def test_post_requires_session(env):
    with patch.object(server, "is_enabled", _flags("growth.share_landing")):
        r = env.post("/api/share/package",
                     data=json.dumps(GOOD_BODY),
                     content_type="application/json")
    assert r.status_code == 401


def test_demo_session_refused(env):
    with server._sessions_lock:
        server._sessions[TOKEN]["is_demo"] = True
    try:
        with patch.object(server, "is_enabled",
                          _flags("growth.share_landing")):
            r = _post(env, GOOD_BODY)
        assert r.status_code == 400
        assert r.get_json()["error"] == "demo_session"
    finally:
        with server._sessions_lock:
            server._sessions[TOKEN].pop("is_demo", None)


def test_happy_path_creates_row_and_serves_landing(env):
    with patch.object(server, "is_enabled", _flags("growth.share_landing")):
        r = _post(env, GOOD_BODY)
        assert r.status_code == 200, r.get_data(as_text=True)
        out = r.get_json()
        assert out["ok"] is True
        sid = out["short_id"]
        assert out["url"] == f"/s/p/{sid}"
        assert out["og_image"] == f"/og/p/{sid}.png"

        row = db_module.load_shared_package(sid)
        assert row["user_id"] == USER
        assert row["give_ids"] == ["4034", "6786"]
        assert row["receive_ids"] == ["7564"]
        assert row["created_at"]

        page = env.get(f"/s/p/{sid}")
        assert page.status_code == 200
        html = page.get_data(as_text=True)
        assert f"/og/p/{sid}.png" in html
        assert "Trade Package" in html
        # Sharer identity never rendered on the public page.
        assert USER not in html


def test_landing_404_for_unknown_id(env):
    with patch.object(server, "is_enabled", _flags("growth.share_landing")):
        assert env.get("/s/p/doesnotexist").status_code == 404


@pytest.mark.parametrize("body", [
    {},                                                       # both missing
    {"give_player_ids": [], "receive_player_ids": []},        # both empty
    {"give_player_ids": "4034"},                              # not a list
    {"give_player_ids": ["4034"] * 6},                        # side too big
    {"give_player_ids": ["<script>"]},                        # bad id chars
    {"give_player_ids": ["x" * 41]},                          # id too long
])
def test_bad_packages_400(env, body):
    with patch.object(server, "is_enabled", _flags("growth.share_landing")):
        r = _post(env, body)
    assert r.status_code == 400
    assert r.get_json()["error"] == "bad_package"


def test_rate_limit_429(env):
    with patch.object(server, "is_enabled", _flags("growth.share_landing")), \
         patch.object(server, "_SHARE_PACKAGE_HOURLY_LIMIT", 2):
        assert _post(env, GOOD_BODY).status_code == 200
        assert _post(env, GOOD_BODY).status_code == 200
        r = _post(env, GOOD_BODY)
        assert r.status_code == 429
        assert r.get_json()["error"] == "rate_limited"


def test_og_card_renders_png(env):
    pytest.importorskip("PIL")
    with patch.object(server, "is_enabled", _flags("growth.share_landing")):
        sid = _post(env, GOOD_BODY).get_json()["short_id"]
        r = env.get(f"/og/p/{sid}.png")
    assert r.status_code == 200
    assert r.headers["Content-Type"] == "image/png"
    assert r.data[:8] == b"\x89PNG\r\n\x1a\n"


def test_og_card_404_for_unknown_id(env):
    pytest.importorskip("PIL")
    with patch.object(server, "is_enabled", _flags("growth.share_landing")):
        r = env.get("/og/p/doesnotexist.png")
    assert r.status_code == 404
    assert r.data[:8] == b"\x89PNG\r\n\x1a\n"   # placeholder card, still an image
