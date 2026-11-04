"""paywall_gate_hit (C8 §B, analytics-lead 2026-10-27): the server event the
paywall gate's before_request hook records for each 402 it sends.

Covers:
  (1) registration: SERVER_FIRED_EVENTS and NON_INTENT_EVENTS, never a client
      event
  (2) a real gated 402 (mobile and web): exact props {gate, route_family,
      enforced} and envelope columns; `gate` is the 402 body's, verbatim, for
      all five reasons
  (3) route_family: every gated rule in ROUTES maps to a family other than
      `other`; the eight values are the closed set; the hook reports the
      matched rule, never the raw path
  (4) the cap: one row per (user_id, gate, route_family) per UTC day; bounded
      (date change clears, hard key cap evicts the oldest); thread-safe
  (5) non-touching: users.last_active_at / events_count unchanged
  (6) nothing written: a free rule, a dark server, a route's own 403
  (7) a raising record_event still returns the byte-identical 402

Sabotages recorded in living-memory/TEST_LEDGER.md (2026-10-28).
In-memory SQLite, no network.
"""

import json
import logging
import threading
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import select

import backend.analytics_queries as aq
import backend.analytics_taxonomy as tax
import backend.database as db_module
import backend.entitlements as entl
import backend.paywall_gate as pg
import backend.server as server
from backend.database import user_events_table, users_table
from backend.tests.test_paywall_gate import (  # noqa: F401 (fixtures)
    BOTH_FLAGS, ENFORCE_KNOB, MOBILE, TOKEN, UNVERIFIED_TOKEN, USER, _enforcing,
    _flags, _make_user, _set_config, client, eng, stubbed,
)

EVENT = "paywall_gate_hit"
FAMILIES = {"deck", "send", "matches", "calculator", "shop", "overhaul",
            "win_now", "other"}
WEB = {"X-Device": "web"}
GATED = sorted(k for k, v in pg.ROUTES.items() if v == pg.GATED)


@pytest.fixture(autouse=True)
def fresh_cap(monkeypatch):
    """Each test starts with an empty in-process cap."""
    monkeypatch.setattr(pg, "_gate_hits", {})
    monkeypatch.setattr(pg, "_gate_hits_day", None)


def _hits(engine):
    t = user_events_table
    with engine.begin() as conn:
        rows = conn.execute(select(t).where(t.c.event_type == EVENT).order_by(t.c.id))
        return [dict(r._mapping) for r in rows]


def _props(row):
    return json.loads(row["props"])


def _call(client, method, path, token=TOKEN, headers=MOBILE):
    return client.open(path, method=method,
                       headers={"X-Session-Token": token, **headers}, json={})


# ── (1) registration ───────────────────────────────────────────────────────

def test_registered_server_fired_and_non_intent_never_client():
    assert EVENT in tax.SERVER_FIRED_EVENTS
    assert EVENT in aq.NON_INTENT_EVENTS
    assert EVENT not in aq.INTENT_EVENTS
    assert EVENT not in tax.ALLOWED_CLIENT_EVENTS
    assert EVENT not in tax.CLIENT_EVENT_PROPS
    assert pg.GATE_HIT_EVENT == EVENT


# ── (2) props and envelope on a real 402 ───────────────────────────────────

@pytest.mark.parametrize("headers,envelope", [
    (MOBILE, {"device_type": "iphone", "os_version": "18.1",
              "app_version": "1.13.2", "source": "mobile"}),
    (WEB, {"device_type": "web", "os_version": None,
           "app_version": None, "source": "web"}),
], ids=["mobile", "web"])
def test_exact_props_and_envelope(eng, client, headers, envelope):
    with _enforcing(eng):
        r = _call(client, "POST", "/api/trades/propose", headers=headers)
    assert r.status_code == 402
    assert r.get_json() == {"error": "pro_required", "gate": "never_trialed"}
    [row] = _hits(eng)
    assert row["user_id"] == USER
    assert {k: row[k] for k in envelope} == envelope
    assert _props(row) == {"gate": "never_trialed", "route_family": "send",
                           "enforced": True}
    assert (row["league_id"], row["session_id"], row["event_id"]) == (None, None, None)


@pytest.mark.parametrize("state,token,method,path,gate,family", [
    ("never", TOKEN, "POST", "/api/trades/propose", "never_trialed", "send"),
    ("preview_spent", TOKEN, "POST", "/api/trades/generate", "preview_used", "deck"),
    ("trial_expired", TOKEN, "POST", "/api/overhauls", "trial_expired", "overhaul"),
    ("lapsed", TOKEN, "GET", "/api/win-now/jobs/j1", "lapsed", "win_now"),
    ("active_paid", UNVERIFIED_TOKEN, "POST", "/api/trades/propose", "verify_required", "send"),
])
def test_gate_prop_is_the_402_body_gate(eng, client, state, token, method, path, gate, family):
    if state == "preview_spent":
        pg.record_preview(USER, "job-spent", 1, ["t-1"])
    else:
        _make_user(state)
    with _enforcing(eng):
        if state == "preview_spent":
            _set_config(eng, paywall_preview_pages=1.0)
        r = _call(client, method, path, token=token)
    assert r.status_code == 402
    assert r.get_json()["gate"] == gate
    [row] = _hits(eng)
    assert _props(row) == {"gate": r.get_json()["gate"], "route_family": family,
                           "enforced": True}


# ── (3) route_family ───────────────────────────────────────────────────────

def test_route_families_are_the_closed_set():
    assert pg.ROUTE_FAMILIES == FAMILIES
    assert {pg.route_family(rule) for _m, rule in GATED} | {"other"} == FAMILIES


@pytest.mark.parametrize("method,rule", GATED)
def test_every_gated_rule_maps_off_other(method, rule):
    assert pg.route_family(rule) in pg.ROUTE_FAMILIES - {"other"}


def test_the_spec_mapping():
    expected = {
        **{rule: "deck" for _m, rule in pg.DECK_ROUTES},
        **dict.fromkeys(["/api/trades/propose", "/api/trades/propose-espn",
                         "/api/trades/propose-mfl", "/api/trades/queue",
                         "/api/trades/respond-mfl", "/api/trades/standing-offer"], "send"),
        "/api/trades/matches/<int:match_id>/disposition": "matches",
        "/api/trades/fair-packages": "calculator",
        "/api/trades/asset-ideas": "shop",
    }
    for _m, rule in GATED:
        want = expected.get(rule) or (
            "overhaul" if rule.startswith("/api/overhauls") else
            "win_now" if rule.startswith("/api/win-now/") else None)
        assert want is not None, rule
        assert pg.route_family(rule) == want, rule
    assert pg.route_family("/api/trades/some-new-gated-rule") == "other"


@pytest.mark.parametrize("path,family,raw", [
    ("/api/trades/matches/7/disposition", "matches", "7"),
    ("/api/overhauls/ov-secret-123/offers", "overhaul", "ov-secret-123"),
])
def test_hook_reports_the_matched_rule_never_the_path(eng, client, path, family, raw):
    method = "GET" if path.endswith("/offers") else "POST"
    with _enforcing(eng):
        assert _call(client, method, path).status_code == 402
    [row] = _hits(eng)
    assert _props(row)["route_family"] == family
    assert raw not in row["props"]


# ── (4) the cap ────────────────────────────────────────────────────────────

def test_cap_one_row_per_user_gate_family_per_utc_day(eng, client, monkeypatch):
    day = {"v": "2026-10-28"}
    monkeypatch.setattr(pg, "_utc_day", lambda: day["v"])
    with _enforcing(eng):
        for _ in range(2):
            assert _call(client, "POST", "/api/trades/propose").status_code == 402
        _call(client, "POST", "/api/trades/queue")                    # same gate, same family
        assert len(_hits(eng)) == 1
        _call(client, "GET", "/api/overhauls")                        # another family
        assert len(_hits(eng)) == 2
        _call(client, "POST", "/api/trades/propose", token=UNVERIFIED_TOKEN)   # another gate
        assert len(_hits(eng)) == 3
        day["v"] = "2026-10-29"                                       # the next UTC day
        _call(client, "POST", "/api/trades/propose")
        _call(client, "POST", "/api/trades/propose")
    rows = _hits(eng)
    assert [(_props(r)["gate"], _props(r)["route_family"]) for r in rows] == [
        ("never_trialed", "send"), ("never_trialed", "overhaul"),
        ("verify_required", "send"), ("never_trialed", "send")]


def test_cap_is_bounded(monkeypatch):
    day = {"v": "2026-10-28"}
    monkeypatch.setattr(pg, "_utc_day", lambda: day["v"])
    monkeypatch.setattr(pg, "GATE_HIT_MAX_KEYS", 2)
    a, b, c = ("u1", "g", "f"), ("u2", "g", "f"), ("u3", "g", "f")
    assert [pg._first_hit_today(k) for k in (a, b, a)] == [True, True, False]
    assert pg._first_hit_today(c) is True                  # evicts a, the oldest
    assert list(pg._gate_hits) == [b, c]
    assert pg._first_hit_today(a) is True                  # a again (over-count), evicts b
    assert len(pg._gate_hits) == 2
    day["v"] = "2026-10-29"
    assert pg._first_hit_today(c) is True                  # the new day starts empty
    assert list(pg._gate_hits) == [c]


def test_cap_is_thread_safe():
    barrier = threading.Barrier(16)
    results = []

    def hit():
        barrier.wait()
        results.append(pg._first_hit_today(("u1", "never_trialed", "send")))

    threads = [threading.Thread(target=hit) for _ in range(16)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(results) == [False] * 15 + [True]


# ── (5) non-touching ───────────────────────────────────────────────────────

def _user_row(engine):
    t = users_table
    with engine.begin() as conn:
        row = conn.execute(select(t.c.last_active_at, t.c.events_count,
                                  t.c.last_device_type, t.c.last_app_version)
                           .where(t.c.sleeper_user_id == USER)).one()
    return tuple(row)


def test_touch_user_false_leaves_the_user_row_alone(eng, client):
    before = _user_row(eng)
    with _enforcing(eng), patch.object(server, "touch_user_activity", MagicMock()):
        assert _call(client, "POST", "/api/trades/propose").status_code == 402
    assert len(_hits(eng)) == 1
    assert _user_row(eng) == before


# ── (6) nothing written ────────────────────────────────────────────────────

def test_free_rule_writes_nothing(eng, client, stubbed):
    with _enforcing(eng):
        assert _call(client, "POST", "/api/trade/evaluate").status_code == 200
    assert _hits(eng) == []


@pytest.mark.parametrize("flags,knob", [((), 1.0), (BOTH_FLAGS, 0.0)],
                         ids=["flags_off", "knob_zero"])
def test_dark_server_writes_nothing(eng, client, stubbed, flags, knob):
    _set_config(eng, **{ENFORCE_KNOB: knob, "paywall_web_enforce_enabled": 1.0,
                        "paywall_preview_pages": 0.0})
    with patch.object(entl, "is_enabled", _flags(*flags)):
        for method, path in (("POST", "/api/trades/propose"), ("POST", "/api/trades/generate"),
                             ("GET", "/api/overhauls")):
            assert _call(client, method, path).status_code == 200
    assert _hits(eng) == []


def test_unverified_verify_required_emits_and_a_routes_own_403_does_not(eng, client):
    _make_user("active_paid")
    with _enforcing(eng):
        own = _call(client, "POST", "/api/trades/generate", token=UNVERIFIED_TOKEN)
        assert own.status_code == 403
        assert own.get_json() == {"error": "verification_required"}
        assert _hits(eng) == []
        hook = _call(client, "POST", "/api/trades/propose", token=UNVERIFIED_TOKEN)
    assert hook.status_code == 402
    [row] = _hits(eng)
    assert _props(row) == {"gate": "verify_required", "route_family": "send",
                           "enforced": True}


# ── (7) analytics never changes the answer ─────────────────────────────────

def _shape(r):
    return (r.status_code, r.get_data(),
            sorted((k, v) for k, v in r.headers.items() if k != "Date"))


def test_raising_record_event_returns_the_byte_identical_402(eng, client, monkeypatch, caplog):
    with _enforcing(eng):
        normal = _shape(_call(client, "POST", "/api/trades/propose"))
        assert len(_hits(eng)) == 1
        monkeypatch.setattr(pg, "_gate_hits", {})
        calls = []

        def boom(*_a, **_kw):
            calls.append(1)
            raise RuntimeError("detail that must not be logged")
        with patch.object(db_module, "record_event", boom), \
                caplog.at_level(logging.WARNING, logger="trade_finder"):
            failed = _shape(_call(client, "POST", "/api/trades/propose"))
    assert calls == [1]
    assert failed == normal
    assert normal[0] == 402
    assert "paywall_gate_hit not recorded: RuntimeError" in caplog.text
    assert "detail that must not be logged" not in caplog.text
