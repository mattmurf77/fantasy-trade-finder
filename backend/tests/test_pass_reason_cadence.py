"""Pass-reason cadence (flag trade.pass_reason_cadence) — backend half.

Scope: docs/plans/offer-learnings/scope-pass-reason-cadence.md (offer-learnings
WS3, R9). The app keeps the plain ✕ and asks why only after N consecutive
passes, then stays quiet for M. The server's part:

  • N AND M ARE SERVED — `pass_reason_cadence: {ask_after, quiet_for}` on
    GET /api/feature-flags from the `pass_reason_ask_after` /
    `pass_reason_quiet_for` knobs, clamped to sane integers. Flag OFF ⇒ the
    key is absent (payload byte-identical to before the flag).
  • THE ROUTE OPENS ON EITHER FLAG — POST /api/trades/pass-reason works with
    the cadence on and `feedback.decline_reasons` off; with both off it 404s
    exactly as before.
  • TWO NEW CODES, GATED — `other_picks_keep` / `other_waiting` are accepted
    only while the cadence flag is on; flag off they 400 like any unknown code.
  • ELO — a chip write is ONE request carrying reason + detail. Its Elo is the
    existing code's (only `value_giving` writes); both new codes write none.
  • ANALYTICS — the prompt pair is registered, props exact, NON_INTENT.

Harness: test_decline_reasons.py's (in-memory DB, injected session, card).
"""

import re
from pathlib import Path
from unittest.mock import patch

import pytest

import backend.database as db_module
import backend.feature_flags as ff
import backend.server as server
from backend.analytics_queries import NON_INTENT_EVENTS
from backend.analytics_taxonomy import (
    ALLOWED_CLIENT_EVENTS,
    CLIENT_EVENT_PROPS,
    SERVER_FIRED_EVENTS,
)
from backend.ranking_service import PASS_REASON_ELO_KEEP
from backend.tests.test_decline_reasons import (  # noqa: F401 — fixtures
    IMP,
    _decision_rows,
    _knob,
    _post,
    _reason,
    _row_count,
    _swipe_rows,
    harness,
    load_trade_pass_reason,
    mem_engine,
)

REPO = Path(__file__).resolve().parents[2]
# The REAL gate, captured before the harness patches it to `lambda: True`.
_REAL_GATE = server._decline_reasons_enabled


@pytest.fixture()
def flags():
    """Set the live flag map for one test and restore it after."""
    saved = ff._flags_cache

    def _set(**on):
        m = dict(ff.DEFAULT_FLAGS)
        for k, v in on.items():
            m[k.replace("__", ".")] = v
        ff._flags_cache = m
    yield _set
    ff._flags_cache = saved


def _cadence_on(on: bool = True):
    return patch.object(server, "_pass_reason_cadence_enabled", lambda: on)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def test_flag_registered_default_off_everywhere():
    assert "trade.pass_reason_cadence" in ff.FLAG_KEYS
    assert ff.DEFAULT_FLAGS["trade.pass_reason_cadence"] is False
    import json
    for p in ("config/features.json",
              "backend/tests/fixtures/flags/release.json",
              "backend/tests/fixtures/flags/onboarding-v2.json",
              "backend/tests/fixtures/flags/profiles-on.json"):
        assert json.loads((REPO / p).read_text())["trade.pass_reason_cadence"] is False, p


def test_knobs_seeded_with_the_starting_values():
    seeded = {k: v for k, v, _ in db_module._MODEL_CONFIG_DEFAULTS}
    assert seeded["pass_reason_ask_after"] == 3
    assert seeded["pass_reason_quiet_for"] == 5


# ---------------------------------------------------------------------------
# N and M on GET /api/feature-flags
# ---------------------------------------------------------------------------

def _served(client):
    return client.get("/api/feature-flags").get_json()


def test_flag_off_payload_has_no_cadence_key(flags):
    flags()   # every flag at its default (off)
    body = _served(server.app.test_client())
    assert "pass_reason_cadence" not in body
    assert body["flags"]["trade.pass_reason_cadence"] is False


def test_flag_on_serves_the_knobs(flags, monkeypatch):
    flags(**{"trade__pass_reason_cadence": True})
    monkeypatch.setattr(server, "get_config",
                        lambda: {"pass_reason_ask_after": 4.0, "pass_reason_quiet_for": 0.0})
    assert _served(server.app.test_client())["pass_reason_cadence"] == \
        {"ask_after": 4, "quiet_for": 0}


def test_flag_on_missing_rows_serve_the_starting_values(flags, monkeypatch):
    flags(**{"trade__pass_reason_cadence": True})
    monkeypatch.setattr(server, "get_config", lambda: {})
    assert _served(server.app.test_client())["pass_reason_cadence"] == \
        {"ask_after": 3, "quiet_for": 5}


@pytest.mark.parametrize("ask,quiet", [
    (0, -1), (2.5, 1.5), (float("nan"), float("inf")), ("x", None), (-3, -0.5),
])
def test_bad_knob_values_serve_the_starting_values(flags, monkeypatch, ask, quiet):
    flags(**{"trade__pass_reason_cadence": True})
    monkeypatch.setattr(server, "get_config",
                        lambda: {"pass_reason_ask_after": ask, "pass_reason_quiet_for": quiet})
    assert _served(server.app.test_client())["pass_reason_cadence"] == \
        {"ask_after": 3, "quiet_for": 5}


def test_config_read_error_still_serves_defaults(flags, monkeypatch):
    flags(**{"trade__pass_reason_cadence": True})

    def boom():
        raise RuntimeError("db down")
    monkeypatch.setattr(server, "get_config", boom)
    assert _served(server.app.test_client())["pass_reason_cadence"] == \
        {"ask_after": 3, "quiet_for": 5}


# ---------------------------------------------------------------------------
# The route gate
# ---------------------------------------------------------------------------

def test_both_flags_off_route_404s_as_before(harness, flags):
    client, _service, _svc, eng = harness
    flags()
    with patch.object(server, "_decline_reasons_enabled", _REAL_GATE):
        r = _post(client, _reason({"reason": "value"}))
    assert r.status_code == 404 and r.get_json()["error"] == "feature_disabled"
    assert _row_count(eng) == 0


def test_cadence_alone_opens_the_route(harness, flags):
    client, _service, _svc, eng = harness
    flags(**{"trade__pass_reason_cadence": True})
    with patch.object(server, "_decline_reasons_enabled", _REAL_GATE):
        r = _post(client, _reason({"reason": "other", "detail": "other_waiting", "layer": 1}))
    assert r.status_code == 200, r.get_json()
    assert r.get_json()["passed"] is True
    assert _row_count(eng) == 1


# ---------------------------------------------------------------------------
# The two new codes
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("detail", ["other_picks_keep", "other_waiting"])
def test_cadence_codes_refused_while_the_flag_is_off(harness, detail):
    client, _service, _svc, eng = harness
    with _cadence_on(False):
        r = _post(client, _reason({"reason": "other", "detail": detail}))
    assert r.status_code == 400
    assert r.get_json() == {"error": "invalid_detail", "field": "detail"}
    assert _row_count(eng) == 0
    assert _decision_rows(eng) == []


# (detail, parent, writes Elo) — the chip table, cadence on, suppression on.
_CHIPS = [
    ("other_player_keep",  "other", False),   # "Not moving that player" (existing)
    ("other_picks_keep",   "other", False),   # "Keeping my picks" (NEW)
    ("fit_outlook",        "fit",   False),   # "Wrong direction for my team" (existing)
    ("other_player_avoid", "other", False),   # "Don't rate what I'd get" (existing)
    ("other_waiting",      "other", False),   # "Waiting on something" (NEW)
    ("value_giving",       "value", True),    # "Value too low" (existing)
]


@pytest.mark.parametrize("detail,parent,writes", _CHIPS)
def test_one_tap_chip_write(harness, detail, parent, writes):
    """A chip is ONE request with reason + detail: the pass commits, the row
    carries both codes, and Elo follows the existing per-code rule."""
    client, service, _svc, eng = harness
    with _cadence_on(), _knob(1.0):
        r = _post(client, _reason({"reason": parent, "detail": detail, "layer": 1}))
    assert r.status_code == 200, r.get_json()
    body = r.get_json()
    assert body["passed"] is True and body["elo_written"] is writes
    row = load_trade_pass_reason(IMP)
    assert (row["reason"], row["detail"]) == (parent, detail)
    assert len(_decision_rows(eng)) == 1
    assert bool(_swipe_rows(eng)) is writes
    assert bool(service._trade_swipes) is writes


def test_new_codes_do_not_join_the_elo_allow_list():
    assert PASS_REASON_ELO_KEEP == frozenset({"value_giving"})
    assert db_module.PASS_REASON_PARENT["other_picks_keep"] == "other"
    assert db_module.PASS_REASON_PARENT["other_waiting"] == "other"


def test_mobile_chips_map_onto_codes_the_route_accepts():
    """Cross-client: every chip in utils/passReasonCadence.ts names a code in
    PASS_REASON_LAYER2 under the parent it sends."""
    src = (REPO / "mobile/src/utils/passReasonCadence.ts").read_text()
    chips = re.findall(r"reason: '(\w+)', detail: '(\w+)'", src)
    assert len(chips) == 6
    for parent, detail in chips:
        assert detail in db_module.PASS_REASON_LAYER2[parent], (parent, detail)


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------

def test_prompt_events_registered_non_intent_with_exact_props():
    assert CLIENT_EVENT_PROPS["pass_reason_prompt_shown"] == \
        frozenset({"trade_id", "consecutive_passes"})
    assert CLIENT_EVENT_PROPS["pass_reason_prompt_dismissed"] == frozenset({"trade_id"})
    for name in ("pass_reason_prompt_shown", "pass_reason_prompt_dismissed"):
        assert name in ALLOWED_CLIENT_EVENTS
        assert name in NON_INTENT_EVENTS
        assert name not in SERVER_FIRED_EVENTS
