"""D1 free-agent moves: the three SERVER events and the server's error codes
(scope §1, granted by analytics-lead 2026-11-01 with C1–C6; consent.md §6
F1–F5), plus the `sleeper.send_add_drop` flag parity (scope §2).

The four client events (`fa_move_connect_shown`, `_consent_shown`,
`_write_attempted`, `_write_failed`) are registered by the client PR with
their emitters, and pinned there; this file covers only what the server owns.
"""
from __future__ import annotations

import ast
import inspect
import json
import pathlib
import textwrap

import backend.server as server
from backend import analytics_queries, analytics_taxonomy, feature_flags
from backend.tests.test_fa_move_route import (  # noqa: F401  (h is a fixture)
    SUCCEEDED_PROPS, TOKEN, h,
)

REPO = pathlib.Path(__file__).resolve().parents[2]
SERVER_EVENTS = {
    # `surface` only when the request carried a known one (G2: absent, never null).
    "fa_move_consent_recorded": {"surface", "copy_version", "league_platform"},
    "fa_move_consent_withdrawn": {"via", "league_platform"},
    "fa_move_write_succeeded": SUCCEEDED_PROPS,
}
# C3: the closed set of `error_code` values, 21 forever.
C3 = {"feature_disabled", "bad_request", "verification_required", "not_linked", "expired",
      "unconfigured", "consent_required", "roster_full_drop_required", "asset_not_owned",
      "player_unavailable", "waiver_bid_over_budget", "waiver_claim_unsupported",
      "move_kind_changed", "rejected", "write_failed", "outcome_unknown", "move_in_progress",
      "internal_error", "network", "timeout", "unknown"}
CLIENT_ONLY = {"network", "timeout", "unknown"}       # the client's own causes (C4)


def test_registered_server_side_only():
    for name in SERVER_EVENTS:
        assert name in analytics_taxonomy.SERVER_FIRED_EVENTS, name
        assert name not in analytics_taxonomy.ALLOWED_CLIENT_EVENTS, name


def test_class_split():
    non_intent = analytics_queries.NON_INTENT_EVENTS
    assert "fa_move_consent_recorded" in non_intent
    assert "fa_move_consent_withdrawn" in non_intent
    assert "fa_move_write_succeeded" not in non_intent
    assert "fa_move_write_succeeded" in analytics_queries.INTENT_EVENTS


def _drive_every_emitter(h):
    """A grant + a completed move, a Settings withdrawal, then a disconnect."""
    assert h.post().status_code == 200
    h.client.delete("/api/platform-write-consent?platform=sleeper",
                    headers={"X-Session-Token": TOKEN})
    h.post(add_player_id="7777", drop_player_id="1111")       # a fresh grant
    h.client.delete("/api/sleeper/link", headers={"X-Session-Token": TOKEN})


def test_emitted_props_are_exactly_the_granted_ones(h):
    _drive_every_emitter(h)
    seen = {name for _, name, _ in h.events}
    assert seen == set(SERVER_EVENTS)
    for _, name, kw in h.events:
        props = kw["props"]
        expected = SERVER_EVENTS[name]
        if name == "fa_move_consent_recorded" and "surface" not in props:
            expected = expected - {"surface"}
        assert set(props) == expected, (name, props)
        assert "platform" not in props                         # the device column, never a prop
        assert props["league_platform"] in ("sleeper", "mfl", "espn")   # C1: never null
        assert kw.get("source") == "api"
        if name == "fa_move_consent_recorded" and "surface" in props:
            assert props["surface"] in ("free_agents", "usage_trends")      # never None
        if name == "fa_move_consent_withdrawn":
            assert props["via"] in ("settings", "disconnect", "credential_expired",
                                    "credential_rejected")
        if name == "fa_move_write_succeeded":
            assert props["result"] in ("accepted", "partial")          # F4
            assert props["move_kind"] in ("add", "claim")              # C5
            assert isinstance(props["has_bid"], bool) and isinstance(props["has_drop"], bool)


def test_succeeded_never_fires_on_a_failure(h):
    for mode in ("refused", "read_timeout", "connect_refused", "auth", "http_500"):
        h.platform.mode = mode
        h.post()
    assert h.events_named("fa_move_write_succeeded") == []


def _route_codes() -> set[str]:
    """Every code the D1 routes can answer: the first argument of each
    `_fa_move_error(...)` call, `{platform}_` stripped (C2: by suffix)."""
    codes = set()
    for fn in (server._fa_move_core, server._fa_move_write_failure,
               server._fa_move_consent_step, server._fa_move_consent_required,
               server.league_free_agents_move_route,
               server.platform_write_consent_route):
        tree = ast.parse(textwrap.dedent(inspect.getsource(fn)))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and getattr(node.func, "id", None) == "_fa_move_error"
                    and node.args):
                arg = node.args[0]
                if isinstance(arg, ast.Constant):
                    codes.add(arg.value)
                elif isinstance(arg, ast.JoinedStr):
                    tail = arg.values[-1]
                    assert isinstance(tail, ast.Constant) and tail.value.startswith("_")
                    codes.add(tail.value[1:])
    return codes


def test_c3_pinned_against_the_routes_codes():
    assert len(C3) == 21
    assert _route_codes() == C3 - CLIENT_ONLY


# ---------------------------------------------------------------------------
# Flag parity (scope §2): default false, server-only
# ---------------------------------------------------------------------------

def test_send_add_drop_flag_registered_default_off_and_server_only():
    key = "sleeper.send_add_drop"
    assert key in feature_flags.FLAG_KEYS
    assert feature_flags.DEFAULT_FLAGS[key] is False
    features = json.loads((REPO / "config/features.json").read_text())
    release = json.loads((REPO / "backend/tests/fixtures/flags/release.json").read_text())
    assert features[key] is False and release[key] is False
    assert "_comment_sleeper_send_add_drop" in features
    # Never in LAUNCHED_FLAG_DEFAULTS, and no client code reads it (or the
    # never-shipped sleeper.fa_write).
    for path in (REPO / "mobile/src").rglob("*.ts*"):
        text = path.read_text(encoding="utf-8")
        assert "send_add_drop" not in text and "fa_write" not in text, path
