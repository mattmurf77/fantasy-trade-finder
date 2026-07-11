"""
Env-gated test-support blueprint for the mobile UI-testing harness.

Mounted ONLY when FTF_TEST_MODE=1 (see server.py, which also enforces that
test mode cannot start without FTF_SLEEPER_FIXTURES_DIR and
FTF_PLAYERS_CACHE_FILE — a test-mode backend that can reach live Sleeper or
clobber the real players cache is a rails hole). Every line here is dead in
normal operation; backend/tests/test_test_support.py asserts that (guardrail
G5 in docs/plans/mobile-testing/prd.md).

Endpoints (docs/plans/mobile-testing/lld.md §4.3c):
    POST /__test__/fail_next {path, status, count=1, body=null}
        Response override for the next `count` requests whose path matches
        the glob `path`. `status` may be ANY code including 2xx (precondition
        overrides, e.g. faking GET /api/sleeper/link → 200 {"connected": true}).
        Carve-out: /api/trades/propose refuses status < 400 — propose can
        never be overridden to success, so `completed_proposes` stays a
        meaningful guardrail.
    POST /__test__/latency {path, ms}
        Delay matching requests by `ms` until reset.
    POST /__test__/reset
        Clear all injections and all in-memory sessions (sessions are a
        dict, not a table). Pass {"counters": true} to also zero counters
        (pytest isolation only — the runner never does).
    GET  /__test__/whoami
        {profile, test_mode, fixtures, active_injections, counters}.

Blast-radius rule: no module outside this file and the seams in server.py
may read FTF_TEST_MODE.
"""

from __future__ import annotations

import fnmatch
import os
import threading
import time

from flask import Blueprint, jsonify, request

# Run-level guardrail counters. server.py increments the seam-side ones;
# the aggregator reads them via /__test__/whoami at run end.
counters: dict[str, int] = {
    "vcr_misses": 0,                    # fixture-seam misses (599s served)
    "sleeper_live_egress_attempts": 0,  # live Sleeper calls while test mode active (must stay 0)
    "propose_route_hits": 0,            # /api/trades/propose reached — expected, non-gating
    "completed_proposes": 0,            # real outbound sends — gating, structurally impossible
}

_lock = threading.Lock()
_fail_injections: list[dict] = []     # {pattern, status, count, body}
_latency_injections: list[dict] = []  # {pattern, ms}

bp = Blueprint("ftf_test_support", __name__, url_prefix="/__test__")

_sessions: dict | None = None
_sessions_lock: threading.Lock | None = None

_PROPOSE_PATH = "/api/trades/propose"


def install(app, sessions: dict, sessions_lock: threading.Lock) -> None:
    """Mount the blueprint + request hook. Called by server.py under FTF_TEST_MODE=1 only."""
    global _sessions, _sessions_lock
    _sessions = sessions
    _sessions_lock = sessions_lock
    app.register_blueprint(bp)
    app.before_request(_before_request_hook)


def _before_request_hook():
    path = request.path
    if path.startswith("/__test__"):
        return None

    with _lock:
        delays = [inj["ms"] for inj in _latency_injections
                  if fnmatch.fnmatch(path, inj["pattern"])]
    for ms in delays:
        time.sleep(ms / 1000.0)

    # Route-hit accounting happens here (not in the view) so injected and
    # fail-closed propose requests are counted identically.
    if path == _PROPOSE_PATH:
        with _lock:
            counters["propose_route_hits"] += 1

    with _lock:
        for inj in _fail_injections:
            if inj["count"] > 0 and fnmatch.fnmatch(path, inj["pattern"]):
                inj["count"] -= 1
                body = inj["body"] if inj["body"] is not None else {"error": "ftf_injected"}
                return jsonify(body), inj["status"]
    return None


@bp.route("/fail_next", methods=["POST"])
def fail_next():
    spec = request.get_json(force=True) or {}
    pattern = spec.get("path") or ""
    status = spec.get("status")
    count = int(spec.get("count", 1))
    body = spec.get("body")
    if not pattern or not isinstance(status, int) or count < 1:
        return jsonify({"error": "bad_injection", "need": "path, status(int), count>=1"}), 400
    # Normative carve-out: propose can never be overridden to success.
    if status < 400 and fnmatch.fnmatch(_PROPOSE_PATH, pattern):
        return jsonify({"error": "propose_2xx_refused",
                        "detail": "overrides matching /api/trades/propose must use status >= 400"}), 400
    with _lock:
        _fail_injections.append(
            {"pattern": pattern, "status": status, "count": count, "body": body})
    return jsonify({"armed": True, "active": _active_injections()})


@bp.route("/latency", methods=["POST"])
def latency():
    spec = request.get_json(force=True) or {}
    pattern = spec.get("path") or ""
    ms = spec.get("ms")
    if not pattern or not isinstance(ms, (int, float)) or ms < 0:
        return jsonify({"error": "bad_injection", "need": "path, ms>=0"}), 400
    with _lock:
        _latency_injections.append({"pattern": pattern, "ms": ms})
    return jsonify({"armed": True, "active": _active_injections()})


@bp.route("/reset", methods=["POST"])
def reset():
    spec = request.get_json(silent=True) or {}
    with _lock:
        _fail_injections.clear()
        _latency_injections.clear()
        if spec.get("counters"):
            for k in counters:
                counters[k] = 0
    if _sessions is not None and _sessions_lock is not None:
        with _sessions_lock:
            _sessions.clear()
    return jsonify({"reset": True})


@bp.route("/whoami", methods=["GET"])
def whoami():
    return jsonify({
        "profile": os.environ.get("FTF_TEST_PROFILE"),
        "test_mode": True,
        "fixtures": bool(os.environ.get("FTF_SLEEPER_FIXTURES_DIR")),
        "active_injections": _active_injections(),
        "counters": dict(counters),
    })


def _active_injections() -> list[dict]:
    with _lock:
        fails = [{"kind": "fail_next", **{k: v for k, v in inj.items() if k != "body"}}
                 for inj in _fail_injections if inj["count"] > 0]
        lats = [{"kind": "latency", **inj} for inj in _latency_injections]
    return fails + lats
