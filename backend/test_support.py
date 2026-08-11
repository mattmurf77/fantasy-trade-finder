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
        Clear all injections, all pins and all in-memory sessions (sessions
        are a dict, not a table). Pass {"counters": true} to also zero
        counters (pytest isolation only — the runner never does).
    GET  /__test__/whoami
        {profile, test_mode, fixtures, active_injections, counters, pins}.

Determinism pins (screen-library capture matrix, D-rows). Three surfaces are
reachable in the app but not reproducible in a flow, because the value that
gates them is chosen by the engine at request time. Each pin below removes
exactly one of those choices and nothing else; all three are inert until
armed, and `/__test__/reset` clears them:

    POST /__test__/pin/deck_size {n, path="/api/trades*"}
        Truncate the `cards` array of matching JSON responses to `n`. The
        deck's length is a function of the generator's yield across N
        opponents — there is no single knob to turn, and the trade job runs
        on a worker thread — so the pin lands on the RESPONSE, the one place
        the number is unambiguous. Makes "swipe the whole deck out" (matrix
        row 85) and "exhausted" (row 86) authorable with a known N. `n: 0`
        serves an empty deck.
    POST /__test__/pin/qc_trio {armed, rng_seed=null}
        Force the next GET /api/trio to serve a QC (consensus-check) trio.
        server.py throttles QC trios to one per QC_TRIO_INTERVAL rankings via
        a PER-SESSION counter, so the pin primes that counter on every live
        session immediately before the request is routed — no server change,
        and the throttle itself is untouched. `rng_seed` additionally seeds
        the `random` module, which is what `smart_matchup_generator.
        find_qc_trio` samples from, so the same three players come back every
        run. Unlocks matrix row 150 (`toast--qc-compliment`).
    POST /__test__/pin/streak {current, longest=null, last_rank_local_date=null,
                               user_id=null}
        Write the ranking-streak columns on `users`. The streak toast (matrix
        row 44) only fires when `streak.current > 0`, and no profile seeds a
        streak because the counter is derived from rank-event history, not
        stored intent. `last_rank_local_date` defaults to YESTERDAY (UTC) so
        the next rank event advances the streak rather than being a same-day
        no-op. Unlike the other two, this pin writes the SEEDED DB, so
        `/__test__/reset` does not undo it — re-seed the profile.

Blast-radius rule: no module outside this file and the seams in server.py
may read FTF_TEST_MODE.
"""

from __future__ import annotations

import fnmatch
import os
import random
import threading
import time
from datetime import datetime, timedelta, timezone

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

# Determinism pins. None = not armed; every one is cleared by /reset.
_deck_size_pin: dict | None = None    # {n, pattern}
_qc_trio_pin: dict | None = None      # {rng_seed}

# The path whose response the QC pin primes for. Matched exactly (not as a
# glob) so priming can never be triggered by an unrelated rankings read.
_TRIO_PATH = "/api/trio"
# Default deck-size glob. No trailing slash before the `*`: the deck is served
# by /api/trades/generate, /api/trades/status AND the bare /api/trades
# (pending cards), and `/api/trades/*` silently misses the last one. Breadth is
# safe because the rewrite additionally requires a dict body with a `cards`
# LIST — the deck payload's shape and nothing else's.
_DECK_PATH_GLOB = "/api/trades*"
# Fallback only — the real value is read from server.QC_TRIO_INTERVAL, which
# is the number the throttle actually compares against.
_QC_TRIO_INTERVAL_FALLBACK = 100

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
    app.after_request(_after_request_hook)


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

    if path == _TRIO_PATH:
        _prime_qc_trio()

    with _lock:
        for inj in _fail_injections:
            if inj["count"] > 0 and fnmatch.fnmatch(path, inj["pattern"]):
                inj["count"] -= 1
                body = inj["body"] if inj["body"] is not None else {"error": "ftf_injected"}
                return jsonify(body), inj["status"]
    return None


def _qc_trio_interval() -> int:
    """server.QC_TRIO_INTERVAL, or the fallback when server isn't importable
    (the blueprint unit tests mount this module on a bare Flask app)."""
    try:
        from .server import QC_TRIO_INTERVAL
        return int(QC_TRIO_INTERVAL)
    except Exception:
        return _QC_TRIO_INTERVAL_FALLBACK


def _prime_qc_trio() -> None:
    """Satisfy server.py's per-session QC throttle for every live session.

    The counter is `sess["_qc_counters"][position]`, where the key is the
    `position` query param or "" for cross-position. Every key present is
    raised to the interval, and both the bare "" key and the four positions
    are seeded, so the pin holds whichever way the flow enters the screen.
    """
    with _lock:
        armed = _qc_trio_pin is not None
        seed = (_qc_trio_pin or {}).get("rng_seed")
    if not armed or _sessions is None or _sessions_lock is None:
        return
    if seed is not None:
        # find_qc_trio() samples the `random` module directly, so this is the
        # only place the CHOSEN players can be made reproducible.
        random.seed(int(seed))
    interval = _qc_trio_interval()
    with _sessions_lock:
        for sess in _sessions.values():
            if not isinstance(sess, dict):
                continue
            counters_map = sess.setdefault("_qc_counters", {})
            for key in ("", "QB", "RB", "WR", "TE", *list(counters_map)):
                counters_map[key] = interval


def _after_request_hook(response):
    """Deck-size pin — the only response rewriting this module does."""
    path = request.path
    if path.startswith("/__test__"):
        return response
    with _lock:
        pin = dict(_deck_size_pin) if _deck_size_pin else None
    if not pin or not fnmatch.fnmatch(path, pin["pattern"]):
        return response
    if not response.is_json:
        return response
    body = response.get_json(silent=True)
    if not isinstance(body, dict) or not isinstance(body.get("cards"), list):
        return response
    if len(body["cards"]) <= pin["n"]:
        return response
    body["cards"] = body["cards"][: pin["n"]]
    response.set_data(jsonify(body).get_data())
    return response


@bp.route("/pin/deck_size", methods=["POST"])
def pin_deck_size():
    global _deck_size_pin
    spec = request.get_json(force=True) or {}
    n = spec.get("n")
    pattern = spec.get("path") or _DECK_PATH_GLOB
    if not isinstance(n, int) or isinstance(n, bool) or n < 0:
        return jsonify({"error": "bad_pin", "need": "n(int)>=0, optional path"}), 400
    with _lock:
        _deck_size_pin = {"n": n, "pattern": pattern}
    return jsonify({"pinned": True, "pins": _active_pins()})


@bp.route("/pin/qc_trio", methods=["POST"])
def pin_qc_trio():
    global _qc_trio_pin
    spec = request.get_json(force=True) or {}
    armed = spec.get("armed", True)
    seed = spec.get("rng_seed")
    if seed is not None and (not isinstance(seed, int) or isinstance(seed, bool)):
        return jsonify({"error": "bad_pin", "need": "armed(bool), rng_seed(int|null)"}), 400
    with _lock:
        _qc_trio_pin = {"rng_seed": seed} if armed else None
    return jsonify({"pinned": bool(armed), "pins": _active_pins()})


@bp.route("/pin/streak", methods=["POST"])
def pin_streak():
    """Write users.current_streak / longest_streak / last_rank_local_date.

    A DB write rather than a response rewrite: the streak is read back by
    /api/me/streak, the leaderboard and the post-rank response, and a pin
    that only patched one of them would make the three disagree on screen.
    """
    spec = request.get_json(force=True) or {}
    current = spec.get("current")
    if not isinstance(current, int) or isinstance(current, bool) or current < 0:
        return jsonify({"error": "bad_pin",
                        "need": "current(int)>=0, optional longest/"
                                "last_rank_local_date/user_id"}), 400
    longest = spec.get("longest")
    if longest is None:
        longest = current
    if not isinstance(longest, int) or isinstance(longest, bool) or longest < current:
        return jsonify({"error": "bad_pin", "need": "longest(int) >= current"}), 400
    last_date = spec.get("last_rank_local_date")
    if last_date is None:
        # Yesterday IN UTC — not the host's local day. `last_rank_tz` is left
        # NULL, and both the read-side decay (`_streak_lapsed`) and the
        # write-side transition then frame the day in UTC; a host running at
        # UTC-7 late in the evening would otherwise write a date two UTC days
        # back, which reads as LAPSED and displays `current: 0` — the exact
        # state the pin exists to avoid. "Yesterday" is also what makes the
        # next rank event ADVANCE the streak instead of being a same-day
        # no-op. A client sending its own X-User-TZ can still shift the
        # displayed number by one; it can never make it zero.
        last_date = (datetime.now(timezone.utc).date()
                     - timedelta(days=1)).isoformat()

    user_id = spec.get("user_id")
    from sqlalchemy import select as _select, update as _update

    from . import database as db
    if not user_id:
        with db.engine.connect() as conn:
            row = conn.execute(
                _select(db.users_table.c.sleeper_user_id)
                .order_by(db.users_table.c.sleeper_user_id).limit(1)
            ).fetchone()
        if row is None:
            return jsonify({"error": "no_user",
                            "detail": "pass user_id — no users row to default to"}), 400
        user_id = row[0]
    with db.engine.begin() as conn:
        result = conn.execute(
            _update(db.users_table)
            .where(db.users_table.c.sleeper_user_id == str(user_id))
            .values(current_streak=current, longest_streak=longest,
                    last_rank_local_date=last_date)
        )
    if result.rowcount == 0:
        return jsonify({"error": "unknown_user", "user_id": str(user_id)}), 404
    return jsonify({"pinned": True, "user_id": str(user_id), "current": current,
                    "longest": longest, "last_rank_local_date": last_date})


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
    global _deck_size_pin, _qc_trio_pin
    spec = request.get_json(silent=True) or {}
    with _lock:
        _fail_injections.clear()
        _latency_injections.clear()
        # Pins are injections by another name — same reset semantics, so a
        # flow can never inherit the previous flow's pinned deck.
        _deck_size_pin = None
        _qc_trio_pin = None
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
        # pid lets the runner verify it reached the Flask it just started —
        # a STALE instance on the same port answers the handshake identically
        # otherwise (bit us 2026-07-12: smoke ran against yesterday's Flask).
        "pid": os.getpid(),
        "profile": os.environ.get("FTF_TEST_PROFILE"),
        "test_mode": True,
        "fixtures": bool(os.environ.get("FTF_SLEEPER_FIXTURES_DIR")),
        "active_injections": _active_injections(),
        "pins": _active_pins(),
        "counters": dict(counters),
    })


def _active_pins() -> dict:
    """Armed determinism pins. The streak pin is absent by design: it is a DB
    write, not process state, so there is nothing here that could go stale
    against it — re-seed the profile to undo one."""
    with _lock:
        out: dict = {}
        if _deck_size_pin is not None:
            out["deck_size"] = dict(_deck_size_pin)
        if _qc_trio_pin is not None:
            out["qc_trio"] = dict(_qc_trio_pin)
    return out


def _active_injections() -> list[dict]:
    with _lock:
        fails = [{"kind": "fail_next", **{k: v for k, v in inj.items() if k != "body"}}
                 for inj in _fail_injections if inj["count"] > 0]
        lats = [{"kind": "latency", **inj} for inj in _latency_injections]
    return fails + lats
