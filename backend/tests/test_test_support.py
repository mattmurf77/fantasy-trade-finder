"""UI-test harness seams (docs/plans/mobile-testing/lld.md §4.3, prd.md R-05/R-10/R-11/R-12).

Two layers of tests:

1. Blueprint unit tests — backend/test_support.py mounted on a bare Flask app
   (no env games, fast): injection arming/consumption, the propose 2xx
   carve-out, reset semantics, whoami shape.

2. Subprocess tests — backend.server reads the FTF_* env vars at import time
   and other tests import it un-gated, so test-mode behavior and the startup
   abort rules run in a child interpreter with a scratch DATABASE_URL (never
   the real data/trade_finder.db). This is also what pins guardrail G5
   (inertness): with no env set, the running app must expose no /__test__
   routes and keep the default players-cache path.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
from flask import Flask

import backend.test_support as ts

_REPO = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# 1. Blueprint unit tests (bare Flask app)
# ---------------------------------------------------------------------------

@pytest.fixture()
def client():
    app = Flask(__name__)
    sessions: dict = {"tok": {"user_id": "u1"}}
    import threading
    ts.install(app, sessions=sessions, sessions_lock=threading.Lock())

    @app.route("/api/anything")
    def anything():
        return {"ok": True}

    @app.route("/api/trades/propose", methods=["POST"])
    def propose_stub():
        return {"error": "test_mode_propose_disabled"}, 599

    c = app.test_client()
    c._sessions = sessions
    yield c
    # isolate counters/injections between tests
    c.post("/__test__/reset", json={"counters": True})


def test_fail_next_arms_and_consumes(client):
    r = client.post("/__test__/fail_next",
                    json={"path": "/api/anything", "status": 503, "count": 1})
    assert r.status_code == 200
    assert client.get("/api/anything").status_code == 503
    # count exhausted → passes through
    assert client.get("/api/anything").status_code == 200


def test_fail_next_body_is_returned(client):
    client.post("/__test__/fail_next",
                json={"path": "/api/anything", "status": 400,
                      "body": {"error": "league_not_found"}})
    r = client.get("/api/anything")
    assert r.status_code == 400
    assert r.get_json() == {"error": "league_not_found"}


def test_fail_next_2xx_precondition_override_allowed(client):
    client.post("/__test__/fail_next",
                json={"path": "/api/sleeper/link", "status": 200,
                      "body": {"connected": True}})
    # No real route needed — the hook answers before routing.
    r = client.get("/api/sleeper/link")
    assert r.status_code == 200
    assert r.get_json() == {"connected": True}


def test_propose_2xx_override_refused(client):
    for pattern in ("/api/trades/propose", "/api/trades/*", "/api/*"):
        r = client.post("/__test__/fail_next",
                        json={"path": pattern, "status": 200, "body": {"status": "proposed"}})
        assert r.status_code == 400, pattern
        assert r.get_json()["error"] == "propose_2xx_refused"
    # error-status overrides on propose remain legal (TC-TRD-29)
    r = client.post("/__test__/fail_next",
                    json={"path": "/api/trades/propose", "status": 400,
                          "body": {"error": "sleeper_not_linked"}})
    assert r.status_code == 200


def test_propose_route_hits_counts_injected_and_fail_closed(client):
    base = ts.counters["propose_route_hits"]
    client.post("/api/trades/propose")                       # fail-closed stub (599)
    client.post("/__test__/fail_next",
                json={"path": "/api/trades/propose", "status": 400,
                      "body": {"error": "sleeper_not_linked"}})
    r = client.post("/api/trades/propose")                   # injected
    assert r.status_code == 400
    assert ts.counters["propose_route_hits"] == base + 2
    assert ts.counters["completed_proposes"] == 0


def test_reset_clears_injections_and_sessions(client):
    client.post("/__test__/fail_next", json={"path": "/api/anything", "status": 500})
    client.post("/__test__/latency", json={"path": "/api/anything", "ms": 0})
    assert client._sessions  # seeded in fixture
    r = client.post("/__test__/reset")
    assert r.get_json() == {"reset": True}
    assert client._sessions == {}
    who = client.get("/__test__/whoami").get_json()
    assert who["active_injections"] == []
    assert client.get("/api/anything").status_code == 200


def test_whoami_shape(client):
    who = client.get("/__test__/whoami").get_json()
    assert who["test_mode"] is True
    assert set(who["counters"]) == {"vcr_misses", "sleeper_live_egress_attempts",
                                    "propose_route_hits", "completed_proposes"}
    assert isinstance(who["active_injections"], list)


def test_bad_injection_specs_rejected(client):
    assert client.post("/__test__/fail_next", json={"path": "/x"}).status_code == 400
    assert client.post("/__test__/fail_next",
                       json={"path": "/x", "status": "500"}).status_code == 400
    assert client.post("/__test__/latency", json={"path": "/x", "ms": -1}).status_code == 400


# ---------------------------------------------------------------------------
# 2. Subprocess tests (import-time env behavior of backend.server)
# ---------------------------------------------------------------------------

def _run_child(code: str, env_extra: dict, tmp_path: Path) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    for k in ("FTF_TEST_MODE", "FTF_SLEEPER_FIXTURES_DIR", "FTF_SLEEPER_RECORD",
              "FTF_PLAYERS_CACHE_FILE", "FTF_DP_VALUES_FILE", "FTF_TEST_PROFILE",
              "DATABASE_URL"):
        env.pop(k, None)
    env["DATABASE_URL"] = f"sqlite:///{tmp_path / 'scratch.db'}"
    env.update(env_extra)
    return subprocess.run([sys.executable, "-c", textwrap.dedent(code)],
                          capture_output=True, text=True, cwd=_REPO, env=env, timeout=180)


def _fixtures_dir(tmp_path: Path) -> Path:
    d = tmp_path / "sleeper-fixtures"
    (d / "user").mkdir(parents=True, exist_ok=True)
    (d / "user" / "qa_standard.json").write_text(json.dumps(
        {"user_id": "900000000000000001", "display_name": "QA Standard", "avatar": None}))
    (d / "user" / "qa_missing.json").write_text(json.dumps({"__http_error__": 404}))
    return d


def _dp_file(tmp_path: Path) -> Path:
    f = tmp_path / "dp-values.csv"
    f.write_text("player,pos,value_1qb,value_2qb\n"
                 "Test Stud,WR,9000,9100\nTest Guy,QB,4000,8000\n")
    return f


def _test_env(tmp_path: Path) -> dict:
    """The full, valid test-mode env triple + DP file."""
    cache = tmp_path / "players-cache.json"
    if not cache.exists():
        cache.write_text("{}")
    return {"FTF_TEST_MODE": "1",
            "FTF_SLEEPER_FIXTURES_DIR": str(_fixtures_dir(tmp_path)),
            "FTF_PLAYERS_CACHE_FILE": str(cache),
            "FTF_DP_VALUES_FILE": str(_dp_file(tmp_path))}


def test_inertness_without_env(tmp_path):
    """G5: no FTF_* env ⇒ no /__test__ routes, default cache path, live seam untouched."""
    r = _run_child("""
        import json, backend.server as srv
        routes = [str(rule) for rule in srv.app.url_map.iter_rules()]
        print(json.dumps({
            "test_routes": [x for x in routes if x.startswith("/__test__")],
            "test_mode": srv._TEST_MODE,
            "cache": str(srv.PLAYERS_CACHE_FILE),
        }))
    """, {}, tmp_path)
    assert r.returncode == 0, r.stderr[-2000:]
    out = json.loads(r.stdout.strip().splitlines()[-1])
    assert out["test_routes"] == []
    assert out["test_mode"] is False
    assert out["cache"].endswith("data/.sleeper_players_cache.json")


@pytest.mark.parametrize("env,why", [
    ({"FTF_TEST_MODE": "1"}, "test mode without fixtures dir + cache override"),
    ({"FTF_TEST_MODE": "1", "FTF_SLEEPER_FIXTURES_DIR": "{fx}"}, "test mode without cache override"),
    ({"FTF_TEST_MODE": "1", "FTF_SLEEPER_FIXTURES_DIR": "{fx}",
      "FTF_PLAYERS_CACHE_FILE": "{cache}"}, "test mode without DP values file"),
    ({"FTF_TEST_MODE": "1", "FTF_SLEEPER_FIXTURES_DIR": "{fx}",
      "FTF_PLAYERS_CACHE_FILE": "{cache}", "FTF_DP_VALUES_FILE": "{dp}",
      "FTF_SLEEPER_RECORD": "1"}, "record under test mode"),
])
def test_startup_aborts(tmp_path, env, why):
    fx = _fixtures_dir(tmp_path)
    env = {k: v.format(fx=fx, cache=tmp_path / "cache.json", dp=_dp_file(tmp_path))
           for k, v in env.items()}
    r = _run_child("import backend.server", env, tmp_path)
    assert r.returncode != 0, why
    assert "FTF" in (r.stderr + r.stdout), why


def test_record_mode_refuses_existing_cassettes(tmp_path):
    fx = _fixtures_dir(tmp_path)  # already contains json files
    r = _run_child("import backend.server", {
        "FTF_SLEEPER_RECORD": "1", "FTF_SLEEPER_FIXTURES_DIR": str(fx)}, tmp_path)
    assert r.returncode != 0
    assert "overwrite" in (r.stderr + r.stdout)


def test_test_mode_seam_and_propose_fail_closed(tmp_path):
    """The load-bearing subprocess: fixtures served, misses 599 + counted,
    __http_error__ envelopes raised, propose fails closed 599 pre-auth,
    whoami reports it all, cache override respected."""
    env = _test_env(tmp_path)
    cache = Path(env["FTF_PLAYERS_CACHE_FILE"])
    r = _run_child("""
        import json, urllib.error
        import backend.server as srv

        out = {"cache": str(srv.PLAYERS_CACHE_FILE)}

        # fixture hit
        hit = srv._sleeper_get("https://api.sleeper.app/v1/user/qa_standard")
        out["hit_user_id"] = hit["user_id"]

        # fixture miss → 599, counted, never live
        try:
            srv._sleeper_get("https://api.sleeper.app/v1/user/nobody_here")
            out["miss"] = "NO-RAISE"
        except urllib.error.HTTPError as e:
            out["miss"] = e.code

        # __http_error__ envelope → raised with its code
        try:
            srv._sleeper_get("https://api.sleeper.app/v1/user/qa_missing")
            out["envelope"] = "NO-RAISE"
        except urllib.error.HTTPError as e:
            out["envelope"] = e.code

        c = srv.app.test_client()
        out["propose"] = c.post("/api/trades/propose", json={}).status_code
        who = c.get("/__test__/whoami").get_json()
        out["who"] = {"profile": who["profile"], "counters": who["counters"]}
        print(json.dumps(out))
    """, {**env, "FTF_TEST_PROFILE": "unit"}, tmp_path)
    assert r.returncode == 0, r.stderr[-2000:]
    out = json.loads(r.stdout.strip().splitlines()[-1])
    assert out["cache"] == str(cache)
    assert out["hit_user_id"] == "900000000000000001"
    assert out["miss"] == 599
    assert out["envelope"] == 404
    assert out["propose"] == 599
    assert out["who"]["profile"] == "unit"
    assert out["who"]["counters"]["vcr_misses"] == 1
    assert out["who"]["counters"]["propose_route_hits"] == 1
    assert out["who"]["counters"]["completed_proposes"] == 0
    assert out["who"]["counters"]["sleeper_live_egress_attempts"] == 0
