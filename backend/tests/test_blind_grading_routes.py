"""Calibration (in-app blind grading) — the ROUTE layer of value-core Gate 2.

docs/plans/blind-grading/specs.md §5.2 (package P2). The service is stubbed on
`backend.blind_grading` throughout: these tests pin the gate, the flag
plumbing, the ServerInputs hand-off and the GradingError → JSON mapping, never
the arithmetic (P1's test_blind_grading_service.py owns that). The full flow
against the real service is test_blind_grading_e2e.py (integration-only).

Covered:
  (a) flags — grading.blind registered, false and mirrored; draft.tab off in
      config/features.json and the five fixtures that carry it, still true in
      the draft-room QA profiles;
  (b) the gate — 404 without the flag for the caller, 404 off the allowlist,
      the account overlay, the device overlay needs X-Device-Id, 404 precedes
      the verified-session 403, no session ⇒ 404, _calibration_allowed is the
      ONE audience predicate;
  (c) create — body / active-league validation, resume short-circuits every
      network helper (building and open resume; failed does not), 202 +
      background build hands ServerInputs to build_session (specs §3.3; the
      thread start is patched to run inline);
  (d) GradingError → JSON, the raw body reaches answer_card, the cron-secret
      report is reachable with the flag off and nobody allowlisted.
"""
from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

import backend.blind_grading as bg
import backend.experiments as experiments
import backend.server as server
from backend.feature_flags import DEFAULT_FLAGS, FLAG_KEYS

REPO = Path(__file__).resolve().parents[2]
FLAG_DIR = REPO / "backend/tests/fixtures/flags"

TOKEN = "grading-routes-sess-tok"
USER = "u1"
LEAGUE = "L1"
SID = "418273645512093847"
CID = "907112334455667788"
AUTH = {"X-Session-Token": TOKEN}

SESSIONS = "/api/grading/sessions"
CURRENT = f"/api/grading/sessions/current?league_id={LEAGUE}"
NEXT = f"/api/grading/sessions/{SID}/next"
CARD = f"/api/grading/cards/{CID}"
RESULTS = f"/api/grading/sessions/{SID}/results"
REPORT = "/api/admin/grading/report"

OVERLAY = ({"calibration_rollout": "treatment"},
           {"calibration_rollout": {"flags": {"grading.blind": True}}})
NO_OVERLAY = ({}, {})


def _view(status: str, **over) -> dict:
    view = {"session_id": SID, "league_id": LEAGUE, "status": status,
            "created_at": "2026-10-02T12:00:00+00:00", "completed_at": None,
            "progress": {"answered": 0, "total": 0 if status in ("building", "failed") else 37},
            "error": None}
    view.update(over)
    return view


def _json(path: Path) -> dict:
    return json.loads(path.read_text())


# ---------------------------------------------------------------------------
# harness (pattern 2: Flask client + injected session)
# ---------------------------------------------------------------------------

def _session(**over) -> dict:
    """What _require_initialized_session checks: league / players / trade_svc."""
    sess = {"user_id": USER, "league_user_id": USER, "verified": True,
            "league": SimpleNamespace(league_id=LEAGUE, platform="sleeper"),
            "players": [], "trade_svc": object(), "last_active": 0.0}
    sess.update(over)
    return sess


@contextmanager
def _injected(sess: dict):
    with server._sessions_lock:
        server._sessions[TOKEN] = sess
    try:
        yield
    finally:
        with server._sessions_lock:
            server._sessions.pop(TOKEN, None)


def _hit_all(c, headers: dict) -> list:
    """One call per user route, in the §3.2 order."""
    return [
        c.post(SESSIONS, json={"league_id": LEAGUE}, headers=headers),
        c.get(CURRENT, headers=headers),
        c.get(NEXT, headers=headers),
        c.post(CARD, json={"grade": 4}, headers=headers),
        c.get(RESULTS, headers=headers),
    ]


@pytest.fixture
def client():
    server.app.config["TESTING"] = True
    return server.app.test_client()


def _set_global_flag(monkeypatch, value: bool) -> None:
    real = server.is_enabled
    monkeypatch.setattr(server, "is_enabled",
                        lambda k: value if k == "grading.blind" else real(k))


@pytest.fixture
def flag_on(monkeypatch):
    _set_global_flag(monkeypatch, True)


@pytest.fixture
def flag_off(monkeypatch):
    """Global off AND no overlay for anyone — the shipped posture."""
    _set_global_flag(monkeypatch, False)
    monkeypatch.setattr(experiments, "resolve_for_unit", lambda unit, attrs=None: NO_OVERLAY)


@pytest.fixture
def allowlisted(monkeypatch):
    monkeypatch.setattr(server, "_load_tester_allowlist", lambda: {USER})


@pytest.fixture
def nobody_allowed(monkeypatch):
    monkeypatch.setattr(server, "_load_tester_allowlist", lambda: set())


@pytest.fixture
def service_unreachable(monkeypatch):
    """Every user-facing service function fails the test if a call gets past the gate."""
    for name in ("start_session", "build_session", "current_session",
                 "next_card", "answer_card", "results"):
        monkeypatch.setattr(
            bg, name,
            lambda *a, _n=name, **k: pytest.fail(f"blind_grading.{_n} reached past the gate"))


@pytest.fixture
def inline_build_thread(monkeypatch):
    """specs §3.3: the route starts threading.Thread(name='grading-build'); run it
    inline so the test sees build_session's arguments. Every other thread is untouched."""
    real_thread = server.threading.Thread
    seen: list = []

    class _InlineThread(real_thread):
        def start(self):
            if self.name == "grading-build":
                seen.append(self.daemon)
                self.run()
            else:
                super().start()

    monkeypatch.setattr(server.threading, "Thread", _InlineThread)
    return seen


# ---------------------------------------------------------------------------
# (a) flags
# ---------------------------------------------------------------------------

def test_flag_registered_default_off_and_shipped_on_mirrored():
    """Code default stays False (new code ships dark); config turns it on for every app user
    (operator 2026-10-05) and the fixtures mirror that."""
    assert "grading.blind" in FLAG_KEYS
    assert DEFAULT_FLAGS["grading.blind"] is False
    assert _json(REPO / "config/features.json")["grading.blind"] is True
    for name in ("release", "profiles-on", "onboarding-v2"):
        assert _json(FLAG_DIR / f"{name}.json")["grading.blind"] is True, name
    # These carry no trade.value_core either; they get no grading.blind.
    for name in ("all-on", "release-300", "release-espn-send-off"):
        assert "grading.blind" not in _json(FLAG_DIR / f"{name}.json"), name


def test_draft_tab_off_wherever_it_is_set():
    """Operator 2026-10-02: Calibration takes the third slot; Draft leaves the bar."""
    assert _json(REPO / "config/features.json")["draft.tab"] is False
    for name in ("release", "profiles-on", "onboarding-v2",
                 "release-300", "release-espn-send-off"):
        assert _json(FLAG_DIR / f"{name}.json")["draft.tab"] is False, name
    # The draft-room QA worlds keep their tab: they exist to capture it.
    for name in ("draft", "draft-pre"):
        profile = _json(REPO / "backend/tests/fixtures/profiles" / f"{name}.json")
        assert profile["flag_overrides"]["draft.tab"] is True, name


# ---------------------------------------------------------------------------
# (b) the gate
# ---------------------------------------------------------------------------

def test_routes_404_without_flag_for_caller(client, flag_off, allowlisted, service_unreachable):
    """Allowlisted, but grading.blind resolves false (global off, no overlay)."""
    with _injected(_session()):
        for r in _hit_all(client, AUTH):
            assert (r.status_code, r.get_json()) == (404, {"error": "not_found"})


def test_open_to_every_app_user(client, monkeypatch, flag_on, nobody_allowed):
    """Operator 2026-10-05: Calibration is open to every app user. With grading.blind on,
    a caller on no allowlist reaches the routes."""
    monkeypatch.setattr(bg, "current_session", lambda **kw: {"session": None})
    with _injected(_session()):
        r = client.get(CURRENT, headers=AUTH)
    assert (r.status_code, r.get_json()) == (200, {"session": None})


def test_account_overlay_resolves_flag_for_caller(client, monkeypatch, allowlisted):
    """Global off; the calibration_rollout overlay is resolved for the session's
    account unit exactly as /api/feature-flags would resolve it."""
    _set_global_flag(monkeypatch, False)
    units: list = []

    def resolve(unit, attrs=None):
        units.append(unit)
        return OVERLAY if unit == USER else NO_OVERLAY

    monkeypatch.setattr(experiments, "resolve_for_unit", resolve)
    monkeypatch.setattr(bg, "current_session", lambda **kw: {"session": None})
    with _injected(_session()):
        r = client.get(CURRENT, headers=AUTH)
    assert (r.status_code, r.get_json()) == (200, {"session": None})
    assert USER in units
    # A different account's overlay opens nothing for this caller.
    monkeypatch.setattr(experiments, "resolve_for_unit",
                        lambda unit, attrs=None: OVERLAY if unit == "u9" else NO_OVERLAY)
    with _injected(_session()):
        assert client.get(CURRENT, headers=AUTH).status_code == 404


def test_device_overlay_needs_x_device_id(client, monkeypatch, allowlisted):
    """A device-unit overlay resolves only when the client sends X-Device-Id
    (mobile/src/api/grading.ts sends it on every call)."""
    _set_global_flag(monkeypatch, False)
    monkeypatch.setattr(experiments, "resolve_for_unit",
                        lambda unit, attrs=None: OVERLAY if unit == "device:abc" else NO_OVERLAY)
    monkeypatch.setattr(bg, "current_session", lambda **kw: {"session": None})
    with _injected(_session()):
        assert client.get(CURRENT, headers={**AUTH, "X-Device-Id": "abc"}).status_code == 200
        assert client.get(CURRENT, headers={**AUTH, "X-Device-Id": "xyz"}).status_code == 404
        assert client.get(CURRENT, headers=AUTH).status_code == 404


def test_gate_404_precedes_verification_403(client, monkeypatch, allowlisted, service_unreachable):
    """Decorator order is load-bearing: _grading_gate is outermost, so a caller the
    gate refuses sees 404 even with an unverified session; once the gate passes,
    the existing _gate_unverified_{read,write} answer 403."""
    unverified = _session(verified=False)        # not a demo identity either
    monkeypatch.setattr(experiments, "resolve_for_unit", lambda unit, attrs=None: NO_OVERLAY)

    _set_global_flag(monkeypatch, False)
    with _injected(unverified):
        for r in (client.get(CURRENT, headers=AUTH),
                  client.post(SESSIONS, json={"league_id": LEAGUE}, headers=AUTH)):
            assert (r.status_code, r.get_json()) == (404, {"error": "not_found"})

    _set_global_flag(monkeypatch, True)
    with _injected(unverified):
        for r in (client.get(CURRENT, headers=AUTH),
                  client.post(SESSIONS, json={"league_id": LEAGUE}, headers=AUTH)):
            assert (r.status_code, r.get_json()) == (403, {"error": "verification_required"})


def test_no_session_404(client, flag_on, allowlisted, service_unreachable):
    """No token (and an unknown token) ⇒ 404, never 401: no existence signal."""
    for r in _hit_all(client, {}) + _hit_all(client, {"X-Session-Token": "nope"}):
        assert (r.status_code, r.get_json()) == (404, {"error": "not_found"})


def test_calibration_allowed_is_the_single_audience_predicate(client, monkeypatch, flag_on,
                                                              nobody_allowed):
    """_calibration_allowed is the one audience switch: it is open (True) today, and
    making it refuse closes every grading route (prd.md FR-2)."""
    monkeypatch.setattr(bg, "current_session", lambda **kw: {"session": None})
    with _injected(_session()):
        assert client.get(CURRENT, headers=AUTH).status_code == 200
    monkeypatch.setattr(server, "_calibration_allowed", lambda sess: False)
    with _injected(_session()):
        assert client.get(CURRENT, headers=AUTH).status_code == 404


# ---------------------------------------------------------------------------
# (c) create
# ---------------------------------------------------------------------------

def test_create_validates_body_and_active_league(client, flag_on, allowlisted, service_unreachable):
    with _injected(_session()):
        for r in (client.post(SESSIONS, json={}, headers=AUTH),
                  client.post(SESSIONS, json={"league_id": "  "}, headers=AUTH),
                  client.post(SESSIONS, data="not json", content_type="text/plain", headers=AUTH)):
            assert (r.status_code, r.get_json()) == (
                400, {"error": "invalid_body", "message": "league_id is required"})
        r = client.post(SESSIONS, json={"league_id": "L2"}, headers=AUTH)
        assert (r.status_code, r.get_json()) == (400, {"error": "league_not_active"})


def test_create_requires_an_initialized_session(client, flag_on, allowlisted, service_unreachable):
    """A valid-but-bare session (INIT-08 window) gets the structured 409, not a 500."""
    bare = {"user_id": USER, "verified": True, "last_active": 0.0}
    with _injected(bare):
        r = client.post(SESSIONS, json={"league_id": LEAGUE}, headers=AUTH)
    assert r.status_code == 409
    assert r.get_json()["error"] == "session_not_initialized"


def test_create_resumes_open_session_without_building(client, monkeypatch, flag_on, allowlisted,
                                                       inline_build_thread):
    """An open session is returned as-is: no Sleeper read, no build thread."""
    existing = _view("open", progress={"answered": 3, "total": 37})
    monkeypatch.setattr(bg, "start_session",
                        lambda **kw: {"session": existing, "resumed": True, "needs_build": False})
    for name in ("_value_core_standings", "_league_lineup_slots", "_sleeper_roster_limit"):
        monkeypatch.setattr(server, name,
                            lambda *a, _n=name, **k: pytest.fail(f"{_n} called on resume"))
    monkeypatch.setattr(bg, "build_session", lambda **kw: pytest.fail("build_session on resume"))
    with _injected(_session()):
        r = client.post(SESSIONS, json={"league_id": LEAGUE}, headers=AUTH)
    assert r.status_code == 200
    assert r.get_json() == {"session": existing, "resumed": True}
    assert inline_build_thread == []


def test_create_rekicks_an_orphaned_building_session(client, monkeypatch, flag_on, allowlisted,
                                                     inline_build_thread):
    """Lead fix 2026-10-02: a session left 'building' by a restart or deploy is resumed AND
    its build re-kicked (start_session says needs_build), so it can never stay stuck."""
    building = _view("building")
    monkeypatch.setattr(bg, "start_session",
                        lambda **kw: {"session": building, "resumed": True, "needs_build": True})
    built: list = []
    monkeypatch.setattr(bg, "build_session", lambda **kw: built.append(kw["session_id"]))
    monkeypatch.setattr(server, "_value_core_standings", lambda league_id, platform: ({}, 0))
    monkeypatch.setattr(server, "_league_lineup_slots", lambda league_id: None)
    monkeypatch.setattr(server, "_sleeper_roster_limit", lambda league_id: None)
    monkeypatch.setattr(server, "FLAGS", SimpleNamespace(trade_preference_lists=False))
    with _injected(_session()):
        r = client.post(SESSIONS, json={"league_id": LEAGUE}, headers=AUTH)
    assert r.status_code == 200
    assert r.get_json() == {"session": building, "resumed": True}
    assert built == [SID]


def test_build_thread_survives_server_inputs_failure(monkeypatch):
    """Lead fix 2026-10-02: if gathering ServerInputs raises, the build still runs on empty
    league facts, so the session ends open or failed, never stuck 'building'."""
    def boom(sess, league_id):
        raise RuntimeError("sleeper down")
    monkeypatch.setattr(server, "_grading_server_inputs", boom)
    built: list = []
    monkeypatch.setattr(bg, "build_session", lambda **kw: built.append(kw))
    server._build_grading_session({"user_id": USER}, LEAGUE, SID)
    assert len(built) == 1 and built[0]["session_id"] == SID
    assert built[0]["server"] == bg.ServerInputs(lineup_slots=None, max_players=None,
                                                 standings={}, completed_weeks=0)


def test_create_does_not_resume_a_failed_session(client, monkeypatch, flag_on, allowlisted,
                                                 inline_build_thread):
    """§3.2: a failed session is never resumed; POST starts a fresh one."""
    failed = _view("failed", error={"code": "value_core_failed"})
    fresh = _view("building", session_id="500000000000000001")
    monkeypatch.setattr(bg, "start_session",
                        lambda **kw: {"session": fresh, "resumed": False, "needs_build": True})
    built: list = []
    monkeypatch.setattr(bg, "build_session", lambda **kw: built.append(kw["session_id"]))
    monkeypatch.setattr(server, "_value_core_standings", lambda league_id, platform: ({}, 0))
    monkeypatch.setattr(server, "_league_lineup_slots", lambda league_id: None)
    monkeypatch.setattr(server, "_sleeper_roster_limit", lambda league_id: None)
    monkeypatch.setattr(server, "FLAGS", SimpleNamespace(trade_preference_lists=False))
    with _injected(_session()):
        r = client.post(SESSIONS, json={"league_id": LEAGUE}, headers=AUTH)
    assert r.status_code == 202
    assert r.get_json() == {"session": fresh, "resumed": False}
    assert built == ["500000000000000001"]


def test_create_returns_202_and_builds_in_background(client, monkeypatch, flag_on, allowlisted,
                                                     inline_build_thread):
    """specs §3.3. The request thread does start_session only; the thread gathers
    ServerInputs (standings, slots, roster limit, preference lists) and hands them
    to build_session. The route answers 202 with the building SessionView."""
    from backend.value_core.types import Standing

    building = _view("building")
    started: list = []

    def start_session(**kw):
        started.append(kw)
        return {"session": building, "resumed": False, "needs_build": True}

    built: list = []
    monkeypatch.setattr(bg, "start_session", start_session)
    monkeypatch.setattr(bg, "build_session", lambda **kw: built.append(kw))

    standings = {"u2": Standing(3, 1, 0, 412.5), "u3": Standing(1, 3, 0, 350.0)}
    monkeypatch.setattr(server, "_value_core_standings", lambda league_id, platform: (standings, 4))
    monkeypatch.setattr(server, "_league_lineup_slots",
                        lambda league_id: ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX"])
    monkeypatch.setattr(server, "_sleeper_roster_limit", lambda league_id: 30)
    prefs_calls: list = []

    def load_prefs(*, user_id, league_id):
        prefs_calls.append((user_id, league_id))
        return {"untouchables": ["4046"], "targets": ["1"], "not_interested": ["9509", 9509]}

    monkeypatch.setattr(server, "load_asset_preferences", load_prefs)
    monkeypatch.setattr(server, "FLAGS", SimpleNamespace(trade_preference_lists=True))

    with _injected(_session()):
        r = client.post(SESSIONS, json={"league_id": LEAGUE}, headers=AUTH)

    assert r.status_code == 202
    assert r.get_json() == {"session": building, "resumed": False}
    assert started == [{"user_id": USER, "league_user_id": USER, "league_id": LEAGUE}]
    assert inline_build_thread == [True]                 # one daemon thread, started once
    assert len(built) == 1
    assert built[0]["session_id"] == SID
    assert built[0]["server"] == bg.ServerInputs(
        lineup_slots=("QB", "RB", "RB", "WR", "WR", "TE", "FLEX"), max_players=30,
        standings=standings, completed_weeks=4,
        untouchable_ids=frozenset({"4046"}), not_interested_ids=frozenset({"9509"}))
    assert prefs_calls == [(USER, LEAGUE)]


def test_create_without_needs_build_starts_no_thread(client, monkeypatch, flag_on, allowlisted,
                                                     inline_build_thread):
    """start_session resumed a session the current_session read missed (a race):
    200, and no build thread."""
    monkeypatch.setattr(bg, "current_session", lambda **kw: {"session": None})
    existing = _view("open")
    monkeypatch.setattr(bg, "start_session",
                        lambda **kw: {"session": existing, "resumed": True, "needs_build": False})
    monkeypatch.setattr(bg, "build_session", lambda **kw: pytest.fail("build_session called"))
    with _injected(_session()):
        r = client.post(SESSIONS, json={"league_id": LEAGUE}, headers=AUTH)
    assert (r.status_code, r.get_json()) == (200, {"session": existing, "resumed": True})
    assert inline_build_thread == []


# ---------------------------------------------------------------------------
# (d) error mapping, raw body, the admin report
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("fn, call, err, status, body", [
    ("start_session", lambda c: c.post(SESSIONS, json={"league_id": LEAGUE}, headers=AUTH),
     bg.GradingError("needs_fresh_deck", 409, reason="stale", usable=0, min_cards=10, max_age_days=7),
     409, {"error": "needs_fresh_deck", "reason": "stale", "usable": 0, "min_cards": 10,
           "max_age_days": 7}),
    ("start_session", lambda c: c.post(SESSIONS, json={"league_id": LEAGUE}, headers=AUTH),
     bg.GradingError("league_not_synced", 409), 409, {"error": "league_not_synced"}),
    ("next_card", lambda c: c.get(NEXT, headers=AUTH),
     bg.GradingError("not_found", 404), 404, {"error": "not_found"}),
    ("answer_card", lambda c: c.post(CARD, json={"grade": 4}, headers=AUTH),
     bg.GradingError("session_completed", 409), 409, {"error": "session_completed"}),
    ("answer_card", lambda c: c.post(CARD, json={"grade": 9}, headers=AUTH),
     bg.GradingError("invalid_body", 400, message="grade must be 1..5"),
     400, {"error": "invalid_body", "message": "grade must be 1..5"}),
    ("results", lambda c: c.get(RESULTS, headers=AUTH),
     bg.GradingError("session_incomplete", 409, progress={"answered": 12, "total": 37}),
     409, {"error": "session_incomplete", "progress": {"answered": 12, "total": 37}}),
    ("start_session", lambda c: c.post(SESSIONS, json={"league_id": LEAGUE}, headers=AUTH),
     bg.GradingError("value_core_failed", 503), 503, {"error": "value_core_failed"}),
], ids=lambda v: v if isinstance(v, str) else "")
def test_grading_errors_map_to_json(client, monkeypatch, flag_on, allowlisted,
                                    fn, call, err, status, body):
    monkeypatch.setattr(bg, "current_session", lambda **kw: {"session": None})

    def raise_it(**kw):
        raise err

    monkeypatch.setattr(bg, fn, raise_it)
    with _injected(_session()):
        r = call(client)
    assert (r.status_code, r.get_json()) == (status, body)


def test_answer_passes_raw_body(client, monkeypatch, flag_on, allowlisted):
    """The route validates nothing: answer_card gets the parsed JSON verbatim, and
    None when the body is not JSON (validate_answer owns the 400)."""
    seen: list = []

    def answer_card(**kw):
        seen.append(kw)
        return {"card_id": kw["card_id"], "session_id": SID, "session_status": "open",
                "progress": {"answered": 12, "total": 37}}

    monkeypatch.setattr(bg, "answer_card", answer_card)
    with _injected(_session()):
        r = client.post(CARD, json={"grade": 4, "tags": ["overpay", "overpay"], "extra": 1},
                        headers=AUTH)
        assert r.status_code == 200
        assert r.get_json() == {"card_id": CID, "session_id": SID, "session_status": "open",
                                "progress": {"answered": 12, "total": 37}}
        client.post(CARD, json=[1, 2], headers=AUTH)
        client.post(CARD, data="not json", content_type="text/plain", headers=AUTH)
    assert seen[0] == {"user_id": USER, "card_id": CID,
                       "body": {"grade": 4, "tags": ["overpay", "overpay"], "extra": 1}}
    assert seen[1]["body"] == [1, 2]
    assert seen[2]["body"] is None


def test_admin_report_cron_secret_and_ungated(client, monkeypatch, flag_off, nobody_allowed):
    """X-Cron-Secret only (prd.md D4): no flag, no allowlist, no session."""
    monkeypatch.setattr(server, "_CRON_SECRET", "s3cr3t")
    calls: list = []

    def report(*, since=None, include_open=False):
        calls.append((since, include_open))
        if since == "bad":
            raise bg.GradingError("invalid_since", 400)
        return {"version": bg.VERSION, "filters": {"since": since, "include_open": include_open}}

    monkeypatch.setattr(bg, "report", report)
    assert client.get(REPORT).status_code == 401
    assert client.get(REPORT, headers={"X-Cron-Secret": "wrong"}).status_code == 401
    assert calls == []
    r = client.get(REPORT, headers={"X-Cron-Secret": "s3cr3t"})
    assert (r.status_code, r.get_json()) == (
        200, {"version": bg.VERSION, "filters": {"since": None, "include_open": False}})
    r = client.get(f"{REPORT}?since=2026-10-01&include_open=1", headers={"X-Cron-Secret": "s3cr3t"})
    assert r.get_json()["filters"] == {"since": "2026-10-01", "include_open": True}
    r = client.get(f"{REPORT}?since=bad", headers={"X-Cron-Secret": "s3cr3t"})
    assert (r.status_code, r.get_json()) == (400, {"error": "invalid_since"})


def test_admin_pregenerate_builds_every_candidate_in_one_background_thread(
        client, monkeypatch, flag_off, nobody_allowed):
    """Operator 2026-10-05: generate a Calibration deck for every app user. Cron-secret only;
    the fast half answers 202 with counts, and ONE thread builds the sessions in order."""
    monkeypatch.setattr(server, "_CRON_SECRET", "s3cr3t")
    jobs = [{"session_id": "1", "user_id": "u1", "league_id": "L1", "platform": "sleeper"},
            {"session_id": "2", "user_id": "u2", "league_id": "L2", "platform": "espn"}]
    monkeypatch.setattr(bg, "pregenerate", lambda: {"candidates": 3, "to_build": jobs,
                                                    "resumed_open": 1, "skipped": {}})
    built: list = []
    monkeypatch.setattr(server, "_build_grading_session",
                        lambda sess, league_id, session_id: built.append(
                            (sess["user_id"], sess["league"].platform, league_id, session_id)))
    real_thread = server.threading.Thread
    names: list = []

    class _Inline(real_thread):
        def start(self):
            if self.name == "grading-pregenerate":
                names.append(self.name)
                self.run()
            else:
                super().start()

    monkeypatch.setattr(server.threading, "Thread", _Inline)
    assert client.post("/api/admin/grading/pregenerate").status_code == 401
    r = client.post("/api/admin/grading/pregenerate", headers={"X-Cron-Secret": "s3cr3t"})
    assert (r.status_code, r.get_json()) == (
        202, {"candidates": 3, "building": 2, "already_open": 1, "skipped": {}})
    assert names == ["grading-pregenerate"]
    assert built == [("u1", "sleeper", "L1", "1"), ("u2", "espn", "L2", "2")]


def test_admin_pregenerate_targets_refresh_then_build_each_pair(
        client, monkeypatch, flag_off, nobody_allowed):
    """Operator 2026-10-07: decks for named users whose Acquire deck is stale or missing.
    Body {"targets": [...]} skips the candidate scan; ONE thread, per pair in order,
    refreshes the deck (_replenish_deck_for) and only then starts + builds the session.
    A failed refresh skips that pair's session; a resumed open session is not rebuilt."""
    monkeypatch.setattr(server, "_CRON_SECRET", "s3cr3t")
    monkeypatch.setattr(bg, "pregenerate", lambda: pytest.fail("targets must not scan"))
    calls: list = []

    def replenish(user_id, league_id):
        calls.append(("refresh", user_id, league_id))
        return None if user_id == "u_fail" else (30, 0)

    def start_session(*, user_id, league_user_id, league_id):
        calls.append(("start", user_id, league_user_id, league_id))
        return {"session": {"session_id": f"s-{user_id}"}, "resumed": user_id == "u_open",
                "needs_build": user_id != "u_open"}

    monkeypatch.setattr(server, "_replenish_deck_for", replenish)
    monkeypatch.setattr(bg, "start_session", start_session)
    monkeypatch.setattr(server, "get_league_draft_context",
                        lambda league_id: {"platform": "mfl" if league_id == "L2" else None})
    monkeypatch.setattr(server, "_build_grading_session",
                        lambda sess, league_id, session_id: calls.append(
                            ("build", sess["user_id"], sess["league"].platform, league_id,
                             session_id)))
    real_thread = server.threading.Thread
    names: list = []

    class _Inline(real_thread):
        def start(self):
            if self.name.startswith("grading-pregenerate"):
                names.append(self.name)
                self.run()
            else:
                super().start()

    monkeypatch.setattr(server.threading, "Thread", _Inline)
    url, hdr = "/api/admin/grading/pregenerate", {"X-Cron-Secret": "s3cr3t"}
    targets = [{"user_id": "u1", "league_id": "L1"}, {"user_id": "u_fail", "league_id": "L1"},
               {"user_id": "u_open", "league_id": "L1"}, {"user_id": "u2", "league_id": "L2"}]
    assert client.post(url, json={"targets": targets}).status_code == 401
    for bad in ([], "u1", [{"user_id": "u1"}], [{"user_id": "u1", "league_id": "L1"}, "x"]):
        r = client.post(url, json={"targets": bad}, headers=hdr)
        assert (r.status_code, r.get_json()["error"]) == (400, "invalid_body")
    assert calls == [] and names == []
    r = client.post(url, json={"targets": targets}, headers=hdr)
    assert (r.status_code, r.get_json()) == (202, {"targets": 4, "rebuild": False,
                                                    "refresh_rosters": False})
    assert names == ["grading-pregenerate-targets"]
    assert calls == [
        ("refresh", "u1", "L1"), ("start", "u1", "u1", "L1"),
        ("build", "u1", None, "L1", "s-u1"),
        ("refresh", "u_fail", "L1"),
        ("refresh", "u_open", "L1"), ("start", "u_open", "u_open", "L1"),
        ("refresh", "u2", "L2"), ("start", "u2", "u2", "L2"),
        ("build", "u2", "mfl", "L2", "s-u2"),
    ]


def test_admin_pregenerate_targets_rebuild_retires_before_start(client, monkeypatch, flag_off,
                                                                nobody_allowed):
    """Operator 2026-10-09 (value-core-2): "rebuild": true retires the pair's unanswered
    session after the deck refresh and before start_session, so the rebuild is on the new engine."""
    monkeypatch.setattr(server, "_CRON_SECRET", "s3cr3t")
    calls: list = []
    monkeypatch.setattr(server, "_replenish_deck_for", lambda u, l: calls.append("refresh") or (30, 0))
    monkeypatch.setattr(bg, "retire_unanswered",
                        lambda *, user_id, league_id: calls.append(("retire", user_id, league_id)) or "old")
    monkeypatch.setattr(bg, "start_session", lambda **kw: calls.append("start") or {
        "session": {"session_id": "new"}, "resumed": False, "needs_build": False})
    real_thread = server.threading.Thread

    class _Inline(real_thread):
        def start(self):
            self.run() if self.name == "grading-pregenerate-targets" else super().start()

    monkeypatch.setattr(server.threading, "Thread", _Inline)
    body = {"targets": [{"user_id": "u1", "league_id": "L1"}], "rebuild": True}
    r = client.post("/api/admin/grading/pregenerate", json=body, headers={"X-Cron-Secret": "s3cr3t"})
    assert (r.status_code, r.get_json()) == (202, {"targets": 1, "rebuild": True,
                                                    "refresh_rosters": False})
    assert calls == ["refresh", ("retire", "u1", "L1"), "start"]


def test_admin_add_fit_arms_route(client, monkeypatch, flag_off, nobody_allowed):
    """Operator 2026-10-09: cron-secret only; folds the fit arms into every OPEN session (or the
    targets given) on one daemon thread, projections fetched once per scoring format."""
    import backend.database as database
    import backend.fit_engine as fe

    monkeypatch.setattr(server, "_CRON_SECRET", "s3cr3t")
    rows = [{"session_id": "s1", "user_id": "u1", "league_id": "L1",
             "source_json": json.dumps({"scoring_format": "1qb_ppr"})},
            {"session_id": "s2", "user_id": "u2", "league_id": "L2",
             "source_json": json.dumps({"scoring_format": "1qb_ppr"})}]
    monkeypatch.setattr(database, "list_open_grading_sessions", lambda: list(rows))
    fetched: list = []
    monkeypatch.setattr(fe, "fetch_ros_points",
                        lambda fetch, fmt, **kw: fetched.append(fmt) or {"weeks": 13, "points": {"p": 1.0}})
    monkeypatch.setattr(server, "get_league_draft_context", lambda league_id: {"platform": None})
    monkeypatch.setattr(server, "_grading_server_inputs", lambda sess, league_id: "SERVER")
    calls: list = []
    monkeypatch.setattr(bg, "add_fit_arms", lambda **kw: calls.append(kw) or {"status": "added"})
    real_thread = server.threading.Thread

    class _Inline(real_thread):
        def start(self):
            self.run() if self.name == "grading-fit-arms" else super().start()

    monkeypatch.setattr(server.threading, "Thread", _Inline)
    url, hdr = "/api/admin/grading/add-fit-arms", {"X-Cron-Secret": "s3cr3t"}
    assert client.post(url).status_code == 401
    r = client.post(url, json={"targets": []}, headers=hdr)
    assert (r.status_code, r.get_json()["error"]) == (400, "invalid_body")
    assert calls == []
    r = client.post(url, headers=hdr)
    assert (r.status_code, r.get_json()) == (202, {"sessions": 2})
    assert [c["session_id"] for c in calls] == ["s1", "s2"] and fetched == ["1qb_ppr"]
    assert calls[0]["server"] == "SERVER" and calls[0]["ros_points"] == {"p": 1.0}
    assert calls[0]["ros_meta"] == {"weeks": 13}
    calls.clear()
    r = client.post(url, json={"targets": [{"user_id": "u2", "league_id": "L2"}]}, headers=hdr)
    assert r.get_json() == {"sessions": 1} and [c["session_id"] for c in calls] == ["s2"]


def test_admin_pregenerate_targets_refresh_rosters_once_per_sleeper_league(client, monkeypatch,
                                                                         flag_off, nobody_allowed):
    """Operator 2026-10-09: "refresh_rosters": true re-reads each Sleeper league's rosters from
    Sleeper before the deck refresh, once per league; other platforms are left alone."""
    monkeypatch.setattr(server, "_CRON_SECRET", "s3cr3t")
    calls: list = []
    monkeypatch.setattr(server, "get_league_draft_context",
                        lambda lid: {"platform": "mfl" if lid == "M1" else None})
    monkeypatch.setattr(server, "_refresh_sleeper_members", lambda lid: calls.append(("roster", lid)) or 12)
    monkeypatch.setattr(server, "_replenish_deck_for", lambda u, l: calls.append(("refresh", u, l)) or (30, 0))
    monkeypatch.setattr(bg, "start_session", lambda **kw: {"session": {"session_id": "s"},
                                                           "resumed": True, "needs_build": False})
    real_thread = server.threading.Thread

    class _Inline(real_thread):
        def start(self):
            self.run() if self.name == "grading-pregenerate-targets" else super().start()

    monkeypatch.setattr(server.threading, "Thread", _Inline)
    body = {"targets": [{"user_id": "u1", "league_id": "L1"}, {"user_id": "u2", "league_id": "L1"},
                        {"user_id": "u3", "league_id": "M1"}], "refresh_rosters": True}
    r = client.post("/api/admin/grading/pregenerate", json=body, headers={"X-Cron-Secret": "s3cr3t"})
    assert r.get_json() == {"targets": 3, "rebuild": False, "refresh_rosters": True}
    assert calls == [("roster", "L1"), ("refresh", "u1", "L1"), ("refresh", "u2", "L1"),
                     ("refresh", "u3", "M1")]


def test_refresh_sleeper_members_upserts_owner_rosters(monkeypatch):
    """Rosters + users from Sleeper become league_members rows keyed by owner_id; an empty
    response writes nothing."""
    feeds = {"/rosters": [{"owner_id": "o1", "players": [1, "2"]}, {"owner_id": None, "players": ["3"]},
                          {"owner_id": "o2", "players": None}],
             "/users": [{"user_id": "o1", "display_name": "Ann"}, {"user_id": "o2", "username": "bo"}]}
    monkeypatch.setattr(server, "_sleeper_get", lambda url, timeout=15: feeds["/" + url.rsplit("/", 1)[1]])
    written: list = []
    monkeypatch.setattr(server, "upsert_league_members", lambda league_id, members: written.append((league_id, members)))
    monkeypatch.setattr(server, "_invalidate_league_members_cache", lambda lid: written.append(("inv", lid)))
    assert server._refresh_sleeper_members("L9") == 2
    assert written[0] == ("L9", [{"user_id": "o1", "username": "Ann", "display_name": "Ann", "player_ids": ["1", "2"]},
                                 {"user_id": "o2", "username": "bo", "display_name": "bo", "player_ids": []}])
    assert written[1] == ("inv", "L9")
    feeds["/rosters"] = []
    written.clear()
    assert server._refresh_sleeper_members("L9") == 0 and written == []
