"""Server error alerts through Sentry (GNG-1) and the feedback_received alert
(SUP-M7): backend/error_alerts.py and its server.py wiring.

docs/plans/server-error-alerts/scope.md §3 (and its legal R28.23 table).
Nothing leaves the process: a case that turns Sentry on uses a fake DSN and a
recording transport (the `sentry` fixture), whose teardown closes the client
and resets the SDK's global client, so no other test runs with Sentry active
(the autouse guard asserts it before and after every test here). Counts are
of events captured on the test's own thread, so a stray daemon thread left by
another test can't change them; the leak checks read every envelope. The
fixture also records each event as the SDK built it, before scrub_event
(`sentry.pre`), to pin what is never collected at all.

  (a) no SENTRY_DSN: init is False, no client, notify and the 5xx hook send
      nothing, and the SDK is never imported; a malformed DSN doesn't fail boot
  (b) a raising route: exactly one event, with the stack, without its text
  (c) a handled 503: one http_5xx (route/status/method tags, fingerprint);
      a 404: none; a handled 500 after log.exception: one
  (d) one _cleanup_loop pass with a step raising: one event, the guard's template
  (e) a daily_tick step raising: one event
  (f) the allowlist: legal R28.23's condition-7 request (no planted value in the
      envelope bytes, request.url the route pattern, no breadcrumbs collected),
      credentials, the event shape, the pattern layer, fail closed
  (g) POST /api/feedback: one feedback_received carrying exactly feedback_id
      and kind, nothing of the note; a duplicate: none
  (h) a thread started in a request: its event carries no request
  (i) the structural guard: every error-level log template in backend/ is a
      constant (the template-only rule depends on it)

Sabotage record (each applied, observed red, restored green):
  2026-10-31
  no-DSN guard removed in init_error_alerts       -> (a) RED (at setup: importing
                                                     backend.server turned Sentry on)
  report_5xx's last-event-id check removed        -> (b), (c) handled 500 RED (2 events)
  after_request `>= 500` changed to `>= 400`      -> (c) RED (the 404 reports)
  before_send=scrub_event removed                 -> (f) RED
  scrub_event returns the event on error          -> (f) fail-closed unit + e2e RED
  notify on sentry_sdk.new_scope() (a fork)       -> (g) RED (request, transaction)
  the feedback route's duplicate guard removed    -> (g) RED (a second event)
  ThreadingIntegration(propagate_scope=True)      -> (h) RED (the request collected)
  the 24+ run rule back to "any run"              -> (f) patterns RED (identifiers)
  2026-10-31, legal R28.23 revision
  request.url the real path                       -> (f) condition 7 RED
  request.url keeps the query                     -> (f) condition 7 RED
  exception `value` kept                          -> (f) condition 7, shape RED
  raw log params kept                             -> (f) condition 7, shape RED
  request headers kept                            -> (f) condition 7 (X-Session-Token), credentials RED
  logging breadcrumbs re-enabled (level=INFO and  -> (f) condition 7 (collected), init, breadcrumb RED
    before_breadcrumb returning the crumb)
  one f-string log.error added to server.py       -> (i) RED
"""
import ast
import copy
import json
import logging
import os
import subprocess
import sys
import threading
from pathlib import Path

import pytest

sentry_sdk = pytest.importorskip("sentry_sdk")

from flask import jsonify  # noqa: E402
from sentry_sdk.transport import Transport  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402

import backend.database as db_module  # noqa: E402
import backend.server as server  # noqa: E402
from backend import daily_tick, error_alerts  # noqa: E402
from backend.database import metadata  # noqa: E402
from backend.tests.test_fork_safe_db_and_threads import loop_pass  # noqa: E402,F401 (fixture)

REPO = Path(__file__).resolve().parents[2]
FAKE_DSN = "https://public@example.invalid/1"
BOOM = "admin_experiment_transition_route"        # POST /api/admin/experiments/<key>/transition
UNAVAILABLE = "admin_experiment_decide_route"     # POST /api/admin/experiments/<key>/decide
LOOKUP = "sleeper_user"                           # GET /api/sleeper/user/<path:username>

# Planted values live up here, out of the source context (5 lines either side)
# the SDK attaches to a raising test frame.
JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ1c2VyIn0.c2lnbmF0dXJlLXNlY3JldA"
ESPN_S2 = "AEBxyz" + "Q2xvdWQ%2FS2V5%3D" * 8
SWID = "{1A2B3C4D-1111-2222-3333-444455556666}"
LEAGUE = "123456789012345678"
EMAIL = "owner@example.com"
QUERY_TOKEN = "qwerty123456789012345678"
BODY_SECRET = "SECRET-BODY-123"
CRON_HEADER_SECRET = "cron-abc"
# Legal R28.23 condition 7.
L_USER_ID = "987654321098765432"
L_USERNAME = "smurf-legal-test"
L_SHARE = "tok9Qx2LmPz"
L_EMAIL = "legal-test@example.com"
L_IP = "203.0.113.7"
L_COOKIE = "ck-legal-77Zq"
L_AUTH = "az-legal-88Yw"
L_SESSION = "sess-legal-66Xv"


class _Recorder(Transport):
    """Stores envelopes, with the thread that captured each."""

    def __init__(self, options=None):
        super().__init__(options)
        self.items = []
        self.pre = []          # (thread, event as the SDK built it, before scrub_event)

    def capture_envelope(self, envelope):
        self.items.append((threading.get_ident(), envelope))

    def events(self, thread=None):
        thread = threading.get_ident() if thread is None else thread
        return [env.get_event() for ident, env in self.items
                if ident == thread and env.get_event() is not None]

    def pre_events(self, thread=None):
        thread = threading.get_ident() if thread is None else thread
        return [event for ident, event in self.pre if ident == thread]

    def raw(self):
        return b"".join(env.serialize() for _, env in self.items)


def _fresh_scopes():
    sentry_sdk.get_isolation_scope().clear()
    sentry_sdk.get_current_scope().clear()


@pytest.fixture(autouse=True)
def _sentry_off_around():
    assert not sentry_sdk.get_client().is_active()
    yield
    assert not sentry_sdk.get_client().is_active()


@pytest.fixture
def sentry(monkeypatch):
    """Sentry on with a recording transport; off again in teardown."""
    real_init = sentry_sdk.init
    monkeypatch.setattr(sentry_sdk, "init",
                        lambda **kwargs: real_init(transport=_Recorder, **kwargs))
    monkeypatch.setattr(error_alerts, "_initialized", False)
    monkeypatch.setenv("SENTRY_DSN", FAKE_DSN)
    # No background-thread start (win-now-resume) from a first request mid-test.
    monkeypatch.setattr(server, "_bg_threads_pid", os.getpid())
    _fresh_scopes()
    assert error_alerts.init_error_alerts() is True
    client = sentry_sdk.get_client()
    recorder, scrub = client.transport, client.options["before_send"]

    def before_send(event, hint):
        recorder.pre.append((threading.get_ident(), copy.deepcopy(event)))
        return scrub(event, hint)
    client.options["before_send"] = before_send
    try:
        yield recorder
    finally:
        sentry_sdk.get_client().close()
        sentry_sdk.get_global_scope().set_client(None)
        _fresh_scopes()


@pytest.fixture
def client():
    return server.app.test_client()


# ── (a) dark without a DSN ─────────────────────────────────────────────────

def test_no_dsn_means_no_client_and_nothing_sent(monkeypatch, client):
    calls = []
    monkeypatch.setattr(sentry_sdk, "init", lambda **kw: calls.append("init"))
    monkeypatch.setattr(sentry_sdk, "capture_message", lambda *a, **kw: calls.append("message"))
    monkeypatch.setattr(sentry_sdk, "capture_event", lambda *a, **kw: calls.append("event"))
    monkeypatch.setattr(error_alerts, "_initialized", False)
    monkeypatch.setitem(server.app.view_functions, UNAVAILABLE,
                        lambda **_: (jsonify({"error": "unavailable"}), 503))
    for value in (None, "", "   "):
        if value is None:
            monkeypatch.delenv("SENTRY_DSN", raising=False)
        else:
            monkeypatch.setenv("SENTRY_DSN", value)
        assert error_alerts.init_error_alerts() is False
    assert not sentry_sdk.get_client().is_active()
    error_alerts.notify("feedback_received", feedback_id=1, kind="bug")
    assert client.post("/api/admin/experiments/x/decide").status_code == 503
    assert calls == []


def test_no_dsn_never_imports_the_sdk():
    env = {k: v for k, v in os.environ.items() if k != "SENTRY_DSN"}
    code = ("import sys; from backend import error_alerts as ea; "
            "assert ea.init_error_alerts() is False; ea.request_started(); "
            "ea.report_5xx(503); ea.notify('x', kind='bug'); "
            "print('sentry_sdk' in sys.modules)")
    out = subprocess.run([sys.executable, "-c", code], cwd=REPO, env=env,
                         capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "False"


def test_init_options(monkeypatch):
    seen = []
    monkeypatch.setattr(sentry_sdk, "init", lambda **kw: seen.append(kw))
    monkeypatch.setattr(error_alerts, "_initialized", False)
    monkeypatch.setenv("SENTRY_DSN", FAKE_DSN)
    monkeypatch.setenv("RENDER_GIT_COMMIT", "0123abcd")
    monkeypatch.delenv("SENTRY_ENVIRONMENT", raising=False)
    assert error_alerts.init_error_alerts() is True
    assert error_alerts.init_error_alerts() is True      # idempotent
    [kw] = seen
    assert (kw["dsn"], kw["environment"], kw["release"]) == (FAKE_DSN, "production", "0123abcd")
    assert kw["send_default_pii"] is False and kw["include_local_variables"] is False
    assert kw["max_request_body_size"] == "never"
    assert "traces_sample_rate" not in kw and "profiles_sample_rate" not in kw
    assert "enable_logs" not in kw
    assert kw["auto_enabling_integrations"] is False and kw["trace_propagation_targets"] == []
    assert kw["before_send"] is error_alerts.scrub_event
    assert kw["before_breadcrumb"] is error_alerts.scrub_breadcrumb
    by_name = {type(i).__name__: i for i in kw["integrations"]}
    assert sorted(by_name) == ["FlaskIntegration", "LoggingIntegration", "ThreadingIntegration"]
    logging_i = by_name["LoggingIntegration"]
    assert logging_i._handler is not None                 # ERROR+ records become events
    assert logging_i._breadcrumb_handler is None          # no breadcrumbs (legal R28.23)
    assert logging_i._sentry_logs_handler is None


def test_a_malformed_dsn_leaves_alerts_off(monkeypatch):
    monkeypatch.setattr(error_alerts, "_initialized", False)
    monkeypatch.setenv("SENTRY_DSN", "not-a-dsn")
    assert error_alerts.init_error_alerts() is False
    assert not sentry_sdk.get_client().is_active()


# ── (b) route exceptions ───────────────────────────────────────────────────

def _boom(**_kw):
    raise RuntimeError("synthetic route failure")


def test_a_raising_route_is_one_event_with_its_stack(sentry, monkeypatch, client):
    monkeypatch.setitem(server.app.view_functions, BOOM, _boom)
    res = client.post("/api/admin/experiments/x/transition")
    assert res.status_code == 500 and res.get_json()["error"] == "internal_error"
    [event] = sentry.events()                    # no http_5xx on top of it
    assert event["level"] == "error"
    assert event["logentry"]["message"] == "Unhandled error on %s %s"
    assert event["logentry"]["formatted"] == "Unhandled error on [Filtered] [Filtered]"
    assert event["request"] == {"method": "POST", "url": "/api/admin/experiments/<key>/transition"}
    [exc] = event["exception"]["values"]
    assert exc["type"] == "RuntimeError" and "value" not in exc
    assert "_boom" in [f["function"] for f in exc["stacktrace"]["frames"]]


# ── (c) handled 5xx ────────────────────────────────────────────────────────

def test_a_handled_503_is_one_http_5xx_and_a_404_none(sentry, monkeypatch, client):
    monkeypatch.setitem(server.app.view_functions, UNAVAILABLE,
                        lambda **_: (jsonify({"error": "unavailable"}), 503))
    assert client.post("/api/admin/experiments/x/decide").status_code == 503
    [event] = sentry.events()
    route = "/api/admin/experiments/<key>/decide"
    assert (event["message"], event["level"]) == ("http_5xx", "error")
    assert event["tags"] == {"route": route, "status": "503", "method": "POST"}
    assert event["fingerprint"] == ["http_5xx", route, "503"]
    assert event["request"] == {"method": "POST", "url": route}
    assert client.get("/api/no-such-route").status_code == 404
    assert len(sentry.events()) == 1


@pytest.fixture
def feedback_db(monkeypatch):
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    metadata.create_all(engine)
    monkeypatch.setattr(db_module, "engine", engine)
    monkeypatch.setattr(server, "record_event", lambda *a, **kw: None)


def test_a_handled_500_after_an_error_log_is_one_event(sentry, feedback_db, monkeypatch, client):
    def broken(**_kw):
        raise RuntimeError("synthetic save failure")
    monkeypatch.setattr(server, "save_feedback", broken)
    res = client.post("/api/feedback", json=_note("fb-alerts-500"))
    assert res.status_code == 500
    [event] = sentry.events()                    # the log.exception; no http_5xx
    assert event["logentry"]["message"] == "save_feedback failed: %s"


# ── (d) the cleanup loop, (e) the daily tick ───────────────────────────────

def test_a_failing_cleanup_step_is_one_event(sentry, monkeypatch, loop_pass):
    def fail():
        raise RuntimeError("synthetic retention failure")
    monkeypatch.setattr(server, "_prune_deck_evidence", fail)
    assert loop_pass() == 2
    [event] = sentry.events()
    assert event["logentry"]["message"] == "deck-evidence retention failed"
    assert event["exception"]["values"][0]["type"] == "RuntimeError"
    assert "request" not in event


def test_a_raising_daily_tick_step_is_one_event(sentry):
    def boom(_now):
        raise ValueError("kaput")
    [result] = daily_tick.run([daily_tick.Step("boom", boom)], object(), log=server.log)
    assert result.outcome == "error"
    [event] = sentry.events()                    # the WARNING step line is not an event
    assert event["logentry"] == {"message": "daily-tick: step %s raised",
                                 "params": ["[Filtered]"],
                                 "formatted": "daily-tick: step [Filtered] raised"}
    assert event["exception"]["values"][0]["type"] == "ValueError"


# ── (f) the allowlist ──────────────────────────────────────────────────────

def _lookup(username):
    """Legal R28.23 condition 7: the path's tail carries the planted values."""
    user_id, name, share, email, ip = username.split("/")
    held = {"user_id": user_id, "username": name, "share": share, "email": email, "ip": ip}
    server.log.info("resolving %s", name)            # would be a breadcrumb
    try:
        raise LookupError(f"no user row for {held}")
    except LookupError:
        server.log.exception("lookup failed for %s %s %s", name, email, ip)
    raise RuntimeError(f"lookup failed for {name} {email} {ip} {user_id} {share}")


def test_legal_condition_7_no_planted_value_leaves(sentry, monkeypatch, client, caplog):
    caplog.set_level(logging.INFO, logger=server.log.name)   # basicConfig's DEBUG, as in prod
    monkeypatch.setitem(server.app.view_functions, LOOKUP, _lookup)
    res = client.get(
        f"/api/sleeper/user/{L_USER_ID}/{L_USERNAME}/{L_SHARE}/{L_EMAIL}/{L_IP}"
        f"?ref={L_USERNAME}&token={L_SHARE}",
        headers={"X-Forwarded-For": L_IP, "X-Real-IP": L_IP,
                 "Cookie": f"session={L_COOKIE}", "Authorization": f"Bearer {L_AUTH}",
                 "X-Session-Token": L_SESSION})
    assert res.status_code == 500
    events = sentry.events()
    # The route's log.exception, then the generic handler's.
    assert [e["logentry"]["message"] for e in events] == [
        "lookup failed for %s %s %s", "Unhandled error on %s %s"]
    for event in events:
        assert event["request"] == {"method": "GET", "url": "/api/sleeper/user/<path:username>"}
        assert {"user", "extra", "breadcrumbs"}.isdisjoint(event)
        assert all("value" not in exc for exc in event["exception"]["values"])
    assert events[0]["logentry"]["formatted"] == "lookup failed for [Filtered] [Filtered] [Filtered]"
    # Not vacuous: the SDK did collect them (path, query, log params, exception
    # text), and collected no breadcrumbs at all.
    pre = json.dumps(sentry.pre_events(), default=str)
    for planted in (L_USER_ID, L_USERNAME, L_SHARE, L_EMAIL, L_IP):
        assert planted in pre, planted
    assert all(not (e.get("breadcrumbs") or {}).get("values") for e in sentry.pre_events())
    sentry_sdk.flush()
    raw = sentry.raw()
    for planted in (L_USER_ID, L_USERNAME, L_SHARE, L_EMAIL, L_IP, L_COOKIE, L_AUTH, L_SESSION):
        assert planted.encode() not in raw, planted


def test_no_credential_reaches_the_envelope(sentry, monkeypatch, client):
    def boom(key):
        raise RuntimeError(f"lookup failed for {EMAIL} in league {key}")
    monkeypatch.setitem(server.app.view_functions, BOOM, boom)
    res = client.post(
        f"/api/admin/experiments/{LEAGUE}/transition?token={QUERY_TOKEN}",
        json={"note": BODY_SECRET},
        headers={"Cookie": f"espn_s2={ESPN_S2}; SWID={SWID}",
                 "Authorization": f"Bearer {JWT}", "X-Cron-Secret": CRON_HEADER_SECRET})
    assert res.status_code == 500
    [event] = sentry.events()
    assert event["request"] == {"method": "POST", "url": "/api/admin/experiments/<key>/transition"}
    sentry_sdk.flush()
    raw = sentry.raw()
    for secret in (BODY_SECRET, ESPN_S2, SWID[1:-1], JWT, CRON_HEADER_SECRET, QUERY_TOKEN,
                   LEAGUE, EMAIL):
        assert secret.encode() not in raw, secret


@pytest.mark.parametrize("text, expected", [
    (f"Cookie: espn_s2={ESPN_S2}; SWID={SWID}", "Cookie: [Filtered]; SWID=[Filtered]"),
    (f"auth failed: Bearer {JWT}", "auth failed: [Filtered]"),
    (f"jwt {JWT}", "jwt [Filtered]"),
    ("X-Cron-Secret: cron-abc", "X-Cron-Secret: [Filtered]"),
    ("MFL_USER_ID=ahBv1sGSvuWrx0OmPQ%3D%3D", "MFL_USER_ID=[Filtered]"),
    ("APIKEY=abc", "APIKEY=[Filtered]"),
    ('{"password": "two words", "n": 1}', '{"password": [Filtered], "n": 1}'),
    (f"?token={QUERY_TOKEN}&page=2", "?token=[Filtered]&page=2"),
    (f"mail {EMAIL} now", "mail [Filtered] now"),
    ("id 0f8fad5b-d9cb-469f-a165-70867728950e", "id [Filtered]"),
    (f"swid {SWID}", "swid [Filtered]"),
    ("s2 " + ESPN_S2.replace("%2F", "/").replace("%3D", "="), "s2 [Filtered]"),
    # 24+ runs: a token has a digit or both cases; a snake_case identifier survives
    ('relation "prepared_trade_inventories" does not exist',
     'relation "prepared_trade_inventories" does not exist'),
    ("_drop_stale_deck_evidence failed", "_drop_stale_deck_evidence failed"),
    ("tok QwErTyUiOpAsDfGhJkLzXcVbNmQwErTy", "tok [Filtered]"),           # 32, mixed case
    ("key 5f4dcc3b5aa765d61d8327deb882cf99", "key [Filtered]"),           # 32, hex
    ("fernet gAAAAABnK3xYq1_9vTzR2c-ZpLm8wQe4sHjN0bVfXy7UaDiOgPkEtWrS5MhC6lAnJ3uIo",
     "fernet [Filtered]"),
    (f"league {LEAGUE} user 123456789", "league [Filtered] user [Filtered]"),
    ("week 12345678 of 2026", "week 12345678 of 2026"),
    ("Unhandled error on POST /api/feedback", "Unhandled error on POST /api/feedback"),
])
def test_scrub_patterns(text, expected):
    """The pattern layer, which runs over every log template."""
    assert error_alerts._scrub_str(text) == expected


def _shape_event():
    return {
        "event_id": "a" * 32, "release": "f" * 40, "level": "error", "logger": "trade_finder",
        "transaction": "admin_experiment_transition_route",
        "message": f"user {EMAIL} league {LEAGUE}",
        "logentry": {"message": "failed %s %s n=%d t=%.1f", "params": [LEAGUE, "bob", 42, 3.5],
                     "formatted": f"failed {LEAGUE} bob n=42 t=3.5"},
        "exception": {"values": [{
            "type": "RuntimeError", "module": None, "value": f"user bob SWID={SWID}",
            "mechanism": {"type": "logging", "handled": True},
            "stacktrace": {"frames": [{"function": "_attach_presession_feedback",
                                       "filename": "backend/server.py", "lineno": 3,
                                       "vars": {"note": "MY-PRIVATE-FEEDBACK"}}]}}]},
        "extra": {"sys.argv": ["gunicorn"], "user_id": "u1"},
        "contexts": {"trace": {"trace_id": "b" * 32, "span_id": "c" * 16},
                     "runtime": {"name": "CPython", "version": "3.12.7"},
                     "custom": {"text": "bob"}},
        "tags": {"route": "/api/league/<league_id>", "feedback_id": "12", "kind": "bug",
                 "other": "bob"},
        "user": {"id": "u1", "ip_address": L_IP},
        "request": {"method": "GET", "url": "https://h/api/sleeper/user/bob?ref=bob",
                    "query_string": "ref=bob", "headers": {"X-Session-Token": "t"},
                    "cookies": {"s": "1"}, "data": "body", "env": {"REMOTE_ADDR": L_IP}},
        "breadcrumbs": {"values": [{"message": "hi bob", "data": {"username": "bob"}}]},
        "spans": [{"description": "SELECT bob"}], "surprise": "bob",
    }


def test_scrub_event_is_an_allowlist():
    event = _shape_event()
    with server.app.test_request_context("/api/sleeper/user/bob?ref=bob"):
        out = error_alerts.scrub_event(copy.deepcopy(event), {})
    assert sorted(out) == ["contexts", "event_id", "exception", "level", "logentry", "logger",
                           "message", "release", "request", "tags", "transaction"]
    for key in ("event_id", "release", "level", "logger", "transaction"):
        assert out[key] == event[key]
    assert out["request"] == {"method": "GET", "url": "/api/sleeper/user/<path:username>"}
    assert out["message"] == "[Filtered]"            # not one of our constants
    assert out["logentry"] == {"message": "failed %s %s n=%d t=%.1f",
                               "params": ["[Filtered]", "[Filtered]", 42, 3.5],
                               "formatted": "failed [Filtered] [Filtered] n=42 t=3.5"}
    assert out["exception"] == {"values": [{
        "type": "RuntimeError", "module": None, "mechanism": {"type": "logging", "handled": True},
        "stacktrace": {"frames": [{"function": "_attach_presession_feedback",
                                   "filename": "backend/server.py", "lineno": 3}]}}]}
    assert out["contexts"] == {"trace": event["contexts"]["trace"],
                               "runtime": event["contexts"]["runtime"]}
    assert out["tags"] == {"route": "/api/league/<league_id>", "feedback_id": "12", "kind": "bug"}
    assert "bob" not in json.dumps(out) and L_IP not in json.dumps(out)


def test_scrub_event_request_and_message_edges():
    event = {"message": "http_5xx", "request": {"method": "POST", "url": "https://h/x/bob"}}
    with server.app.test_request_context("/x/bob", method="POST"):
        assert error_alerts.scrub_event(copy.deepcopy(event), {}) == {
            "message": "http_5xx", "request": {"method": "POST", "url": "<unmatched>"}}
    assert error_alerts.scrub_event(copy.deepcopy(event), {}) == {"message": "http_5xx"}
    with server.app.test_request_context("/api/feedback", method="POST"):
        assert error_alerts.scrub_event({"message": "feedback_received"}, {}) == {
            "message": "feedback_received"}          # no request unless the SDK attached one
    assert error_alerts.scrub_event(
        {"logentry": {"message": "%d%% of %s", "params": [12, 123456789]}}, {}) == {
            "logentry": {"message": "%d%% of %s", "params": [12, "[Filtered]"],
                         "formatted": "12% of [Filtered]"}}
    # A %d given [Filtered] doesn't format: formatted is dropped, not guessed.
    assert error_alerts.scrub_event(
        {"logentry": {"message": "id %d", "params": [123456789012]}}, {}) == {
            "logentry": {"message": "id %d", "params": ["[Filtered]"]}}


def test_breadcrumbs_are_off():
    for crumb in ({"type": "http", "category": "httplib",
                   "data": {"url": "https://api.sleeper.app/v1/user/x"}},
                  {"type": "log", "category": "trade_finder", "message": "hi", "data": {}}):
        assert error_alerts.scrub_breadcrumb(crumb, {}) is None


def _raising(*_a, **_kw):
    raise RuntimeError("scrubber bug")


def test_a_scrubber_exception_drops_the_event(monkeypatch):
    monkeypatch.setattr(error_alerts, "_allowlisted", _raising)
    assert error_alerts.scrub_event({"message": "http_5xx"}, {}) is None


def test_a_scrubber_exception_sends_nothing_unsafe(sentry, monkeypatch, client):
    def boom(key):
        raise RuntimeError(f"lookup failed for {EMAIL}")
    monkeypatch.setattr(error_alerts, "_scrub_str", _raising)
    monkeypatch.setitem(server.app.view_functions, BOOM, boom)
    assert client.post(f"/api/admin/experiments/{LEAGUE}/transition").status_code == 500
    # The log event fails to build and isn't sent; with no event for the
    # request, the 5xx is reported from constants alone.
    assert [e.get("message") for e in sentry.events()] == ["http_5xx"]
    assert EMAIL.encode() not in sentry.raw() and LEAGUE.encode() not in sentry.raw()


# ── (g) the feedback_received alert ────────────────────────────────────────

ME = "user_alerts_fb"
TOKEN = "tok-alerts-verified-session"
CLIENT_ID = "fb-alerts-client-id-1"


def _note(client_id=CLIENT_ID):
    return {"client_id": client_id, "screen": "TradesScreen", "severity": "bug",
            "text": "MY-PRIVATE-FEEDBACK", "client_created_at": "2026-10-31T12:00:00Z"}


def test_new_feedback_is_one_tag_only_alert_and_a_duplicate_none(sentry, feedback_db,
                                                                   monkeypatch, client):
    monkeypatch.setitem(server._sessions, TOKEN, {
        "verified": True, "user_id": ME, "username": "me-username",
        "display_name": "Me Display", "last_active": 0.0})
    headers = {"X-Session-Token": TOKEN, "X-Device-Id": "device-alerts-1"}
    res = client.post("/api/feedback", json=_note(), headers=headers)
    assert res.status_code == 201, res.get_json()
    server_id = res.get_json()["server_id"]
    [event] = sentry.events()
    assert (event["message"], event["level"]) == ("feedback_received", "info")
    assert event["tags"] == {"feedback_id": str(server_id), "kind": "bug"}
    assert "request" not in event and "user" not in event and "transaction" not in event
    assert not (event.get("breadcrumbs") or {}).get("values")
    raw = sentry.raw()
    for value in ("MY-PRIVATE-FEEDBACK", "TradesScreen", CLIENT_ID, TOKEN, ME,
                  "me-username", "Me Display", "device-alerts-1"):
        assert value.encode() not in raw, value

    res = client.post("/api/feedback", json=_note(), headers=headers)
    assert res.status_code == 200 and res.get_json()["duplicate"] is True
    assert len(sentry.events()) == 1


# ── (h) threads carry no request ───────────────────────────────────────────

def test_a_thread_started_in_a_request_carries_no_request(sentry, monkeypatch, client):
    ident = []

    def spawn(**_kw):
        worker = threading.Thread(target=lambda: server.log.error("synthetic background failure"))
        worker.start()
        worker.join()
        ident.append(worker.ident)
        return jsonify({"ok": True})
    monkeypatch.setitem(server.app.view_functions, BOOM, spawn)
    assert client.post("/api/admin/experiments/x/transition").status_code == 200
    [pre] = [e for e in sentry.pre_events(thread=ident[0])
             if e["logentry"]["message"] == "synthetic background failure"]
    assert "request" not in pre                   # never collected (propagate_scope=False)
    [event] = sentry.events(thread=ident[0])
    assert "request" not in event


# ── (i) every error-level log template is a constant ───────────────────────

_ERROR_METHODS = {"error", "exception", "critical"}


def _bound_once_to_a_str(scope, name, parents):
    """Whether `name` is bound exactly once in `scope` (any store: assignment,
    loop, with, unpacking), by `name = "<str constant>"`, and isn't a parameter."""
    if not isinstance(scope, ast.Module) and name in {a.arg for a in ast.walk(scope.args)
                                                      if isinstance(a, ast.arg)}:
        return False
    stores = [n for n in ast.walk(scope)
              if isinstance(n, ast.Name) and n.id == name and isinstance(n.ctx, ast.Store)]
    if len(stores) != 1:
        return False
    assign = parents.get(stores[0])
    return (isinstance(assign, ast.Assign) and len(assign.targets) == 1
            and assign.targets[0] is stores[0] and isinstance(assign.value, ast.Constant)
            and isinstance(assign.value.value, str))


def _template_violations(source):
    """(scanned, [(line, call)]): every log.error/exception/critical call, and
    every log.log(level, …) call, on any receiver named like a logger, whose
    template is not a str constant, or a name bound once, in its function,
    to one."""
    tree = ast.parse(source)
    parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
    scanned, bad = 0, []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        recv = node.func.value
        recv_name = recv.id if isinstance(recv, ast.Name) else getattr(recv, "attr", "")
        if "log" not in recv_name.lower():
            continue
        if node.func.attr in _ERROR_METHODS:
            index = 0
        elif node.func.attr == "log":
            index = 1
        else:
            continue
        scanned += 1
        arg = node.args[index] if len(node.args) > index else None
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            continue
        if isinstance(arg, ast.Name):
            scope = parents.get(node)
            while scope is not None and not isinstance(
                    scope, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Module)):
                scope = parents.get(scope)
            if scope is not None and _bound_once_to_a_str(scope, arg.id, parents):
                continue
        bad.append((node.lineno, ast.unparse(node)[:120]))
    return scanned, bad


@pytest.mark.parametrize("source, ok", [
    ('log.error("x %s", a)', True),
    ('log.exception("a " "b %s", a)', True),            # implicit concatenation: a constant
    ('def f(a):\n    t = ("a %s "\n         "b")\n    log.error(t, a)', True),
    ('log.log(logging.ERROR, "x %s", a)', True),
    ('log.error(f"x {a}")', False),
    ('logger.exception("x %s" % a)', False),
    ('self.log.critical("x {}".format(a))', False),
    ('logging.error("x " + a)', False),
    ('log.error(str(e))', False),
    ('log.log(level, f"x {a}")', False),
    ('def f(a, b):\n    t = "x"\n    if b:\n        t = a\n    log.error(t)', False),
    ('def f(rows):\n    t = "x"\n    for t in rows:\n        log.error(t)', False),
    ('def f(t):\n    log.error(t)', False),
])
def test_template_guard_detector(source, ok):
    scanned, bad = _template_violations(source)
    assert scanned == 1 and (bad == []) is ok


def test_every_error_log_template_in_backend_is_a_constant():
    scanned, bad = 0, []
    for path in sorted((REPO / "backend").rglob("*.py")):
        if "tests" in path.relative_to(REPO / "backend").parts:
            continue
        n, violations = _template_violations(path.read_text())
        scanned += n
        bad += [f"{path.relative_to(REPO)}:{line} {call}" for line, call in violations]
    assert scanned >= 170, scanned                       # the scan sees the call sites
    assert bad == [], "error-level log templates must be constants:\n" + "\n".join(bad)
