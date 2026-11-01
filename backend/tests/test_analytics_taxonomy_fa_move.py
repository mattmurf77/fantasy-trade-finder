"""D1 free-agent moves (2026-11-01) — taxonomy registration, client half.

Scope: docs/plans/sleeper-fa-write/scope.md §1 on plan/fa-moves-launch,
granted by analytics-lead with conditions C1–C6. Addendum:
docs/business/analytics/2026-11-01-fa-move-events.md.

The four client-fired names, registered in the SAME commit as their emitters
(mobile/src/api/faMove.ts). The ingest allowlist is default-deny behind a 200:
an unregistered name is counted and dropped, and an unregistered prop is
stripped while the response still reports dropped == 0. The three
server-fired siblings (fa_move_consent_recorded / _consent_withdrawn /
_write_succeeded) arrive with the server PR and its own test rows.

Pinned here:
  * the names, and each prop row EXACTLY (C1's league_platform included);
  * no prop named `platform` (the device-platform column);
  * the class split: two NON_INTENT exposures, two INTENT writes; none WAT;
  * C3's closed 21-value `error_code` set, against the client's own list —
    the taxonomy constrains keys, not values, so the set lives in the client
    and the addendum, and this test keeps the two from drifting;
  * C6: `kind` rides only on write_failed;
  * the rows survive POST /api/events with every prop, `attempt_id`
    unscrubbed (it is the per-tap join key, like `search_id`).
"""
import json
import re
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, select

import backend.analytics_ingest as ingest
import backend.database as db_module
import backend.server as server
from backend.database import metadata, user_events_table

REPO = Path(__file__).resolve().parents[2]
FA_MOVE_TS = REPO / "mobile/src/api/faMove.ts"

# A uuid4 with a 16+ digit run, which the ingest's numeric-run rule would
# scrub unless `attempt_id` is an exempt id key (analytics_ingest._HEX_ID_PROPS).
_ATTEMPT = "6f1c2d3e-0000-4000-8000-000000000000"

_PROPS: dict[str, dict] = {
    "fa_move_connect_shown": {"surface": "free_agents", "reason": "not_linked",
                              "league_platform": "sleeper"},
    "fa_move_consent_shown": {"surface": "usage_trends", "reason": "first",
                              "league_platform": "sleeper"},
    "fa_move_write_attempted": {"surface": "free_agents", "has_drop": True,
                                "has_bid": False, "consent_ticked": True,
                                "attempt_id": _ATTEMPT,
                                "league_platform": "sleeper"},
    "fa_move_write_failed": {"surface": "free_agents", "error_code": "write_failed",
                             "status": 502, "attempt_id": _ATTEMPT,
                             "league_platform": "sleeper", "kind": "network"},
}

_NON_INTENT = {"fa_move_connect_shown", "fa_move_consent_shown"}
_INTENT = {"fa_move_write_attempted", "fa_move_write_failed"}

# C3, as granted (scope.md §1). Hand-written on purpose.
_ERROR_CODES = {
    "feature_disabled", "bad_request", "verification_required", "not_linked",
    "expired", "unconfigured", "consent_required",
    "roster_full_drop_required", "asset_not_owned", "player_unavailable",
    "waiver_bid_over_budget", "waiver_claim_unsupported", "move_kind_changed",
    "rejected", "write_failed", "outcome_unknown", "move_in_progress",
    "internal_error",
    "network", "timeout", "unknown",
}


def test_fa_move_names_are_allowlisted():
    import backend.analytics_taxonomy as tax
    assert set(_PROPS) <= tax.ALLOWED_CLIENT_EVENTS
    assert not (set(_PROPS) & tax._SERVER_AUTHORITATIVE)


def test_fa_move_prop_rows_are_exact():
    """EQUAL, not <=: an extra key is unspecced, a missing one is stripped."""
    import backend.analytics_taxonomy as tax
    for name, props in _PROPS.items():
        assert tax.CLIENT_EVENT_PROPS[name] == frozenset(props), name


def test_fa_move_rows_carry_league_platform_never_platform():
    import backend.analytics_taxonomy as tax
    for name in _PROPS:
        assert "league_platform" in tax.CLIENT_EVENT_PROPS[name], name
        assert "platform" not in tax.CLIENT_EVENT_PROPS[name], name


def test_fa_move_kind_rides_only_on_write_failed():
    import backend.analytics_taxonomy as tax
    assert [n for n in _PROPS if "kind" in tax.CLIENT_EVENT_PROPS[n]] == [
        "fa_move_write_failed"]


def test_fa_move_class_split():
    import backend.analytics_queries as q
    assert len(_NON_INTENT) == 2 and len(_INTENT) == 2
    for name in _NON_INTENT:
        assert name in q.NON_INTENT_EVENTS, name
        assert name not in q.INTENT_EVENTS, name
    for name in _INTENT:
        assert name not in q.NON_INTENT_EVENTS, name
        assert name in q.INTENT_EVENTS, name
    assert not (set(_PROPS) & q.WAT_EVENTS)


def test_fa_move_error_code_set_is_c3():
    """21 values, platform-free (C2): no `sleeper_` / `mfl_` / `espn_` code
    may reach analytics, since the platform lives in league_platform."""
    assert len(_ERROR_CODES) == 21
    assert not any(c.startswith(("sleeper_", "mfl_", "espn_")) for c in _ERROR_CODES)


def test_fa_move_error_code_set_matches_the_client():
    """The client's FA_MOVE_ERROR_CODES is the only place `error_code` is
    produced (mobile/src/api/faMove.ts classifyMoveError)."""
    src = FA_MOVE_TS.read_text()
    m = re.search(r"export const FA_MOVE_ERROR_CODES = \[(.*?)\] as const;", src, re.S)
    assert m, "FA_MOVE_ERROR_CODES not found in mobile/src/api/faMove.ts"
    client = re.findall(r"'([a-z_]+)'", m.group(1))
    assert len(client) == len(set(client)) == 21
    assert set(client) == _ERROR_CODES


# ---------------------------------------------------------------------------
# Ingest — the names and props actually survive POST /api/events.
# Harness mirrors test_analytics_taxonomy_home_hub.py.
# ---------------------------------------------------------------------------

USER = "taxonomy_fa_move_test"
TOKEN = "tax-fa-move-token"
DEVICE = "dev_famove01"


def _envelope(i, event_type, props, screen):
    return {
        "event_id": f"evtfm-{i:04d}",
        "event_type": event_type,
        "client_ts": "2026-11-01T12:00:00Z",
        "screen": screen,
        "props": props,
        "session_id": "sess-fm-0001",
        "seq": i + 1,
    }


@pytest.fixture()
def harness():
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False})
    metadata.create_all(engine)
    server.app.config["TESTING"] = True
    client = server.app.test_client()
    with patch.object(db_module, "engine", engine), \
         patch.object(db_module, "ingest_engine", engine), \
         patch.object(ingest, "is_enabled",
                      lambda k: k == "analytics.ingest"):
        with server._sessions_lock:
            server._sessions[TOKEN] = {"user_id": USER, "last_active": 0.0}
        with ingest._rate_lock:
            ingest._events_rate.clear()
        try:
            yield client, engine
        finally:
            with server._sessions_lock:
                server._sessions.pop(TOKEN, None)
            with ingest._rate_lock:
                ingest._events_rate.clear()


def test_fa_move_events_land_with_every_prop(harness):
    client, engine = harness
    body = client.post(
        "/api/events",
        headers={"Content-Type": "application/json", "X-Device-Id": DEVICE},
        data=json.dumps({"events": [
            _envelope(i, name, props, "FreeAgents")
            for i, (name, props) in enumerate(_PROPS.items())
        ]}),
    ).get_json()
    assert body["accepted"] == len(_PROPS) and body["dropped"] == 0

    with engine.begin() as conn:
        rows = conn.execute(
            select(user_events_table).order_by(user_events_table.c.id)
        ).fetchall()
    by_type = {r._mapping["event_type"]: r._mapping for r in rows}
    assert set(by_type) == set(_PROPS)
    for name, props in _PROPS.items():
        landed = {k: v for k, v in json.loads(by_type[name]["props"]).items()
                  if k not in {"seq", "ts_suspect"}}
        assert landed == props, name
