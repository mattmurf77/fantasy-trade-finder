"""#270/#272 — `trades_home_inline` experiment (strip + canvas variants).
docs/feedback/items/270-inline-trades-home/status.md.

Mirrors the `aggregate_tier_labels` precedent (test_power_rankings.py's
"#279" section) and the `onboarding_v2_rollout` precedent it's built on: an
account-unit experiment targeted via `is_tester_allowlist`, resolved through
the generic `/api/feature-flags` route (backend/server.py
`feature_flags_route`) — NOT a bespoke payload field, since this is a
UI-flow toggle (client_config.flags overlay), the same idiom the onboarding
rollout uses. No server.py route change was needed for this item; these
tests exercise the pre-existing generic experiment-resolution path against
the new experiment key.

Binding shape (task brief): variants `control` / `strip` / `canvas`,
layer `trades_ui`, unit_type `account`, targeting `is_tester_allowlist`.
The operator's allowlisted account starts on `strip` (weights
control=0/strip=10000/canvas=0); moving to `canvas` later is a pure
`/revise` weight change (control=0/strip=0/canvas=10000) — no new build,
no code change. `_mk_trades_home_inline_experiment`'s `strip_bp`/`canvas_bp`
params let a single helper seed either state, exercising the switch
mechanism directly.
"""
import json
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, insert

import backend.database as db
import backend.experiments as ex
import backend.server as server
from backend.database import metadata

TOKEN = "sess-thi-test"


def _h(token=TOKEN):
    return {"X-Session-Token": token}


def _mk_sess(user_id="u_operator"):
    return {
        "user_id": user_id,
        "active_format": "1qb_ppr",
        "last_active": 0.0,
    }


def _install_sess(sess):
    with server._sessions_lock:
        server._sessions[TOKEN] = sess


def _get(c, path):
    r = c.get(path, headers=_h())
    return r.status_code, json.loads(r.data)


@pytest.fixture()
def client():
    server.app.config["TESTING"] = True
    c = server.app.test_client()
    try:
        yield c
    finally:
        with server._sessions_lock:
            server._sessions.pop(TOKEN, None)


@pytest.fixture()
def exp_engine():
    """Isolated in-memory experiments DB — patches db.engine/ro_engine
    (shared module object, so backend.experiments sees the same patch),
    same pattern as test_power_rankings.py's #279 fixture."""
    eng = create_engine("sqlite:///:memory:",
                        connect_args={"check_same_thread": False})
    metadata.create_all(eng)
    with patch.object(db, "engine", eng), patch.object(db, "ro_engine", eng):
        db._seed_experiment_layers()
        ex.invalidate_cache()
        yield eng
    ex.invalidate_cache()


def _mk_trades_home_inline_experiment(engine, *, strip_bp=10000, canvas_bp=0):
    """Seed a running `trades_home_inline` experiment on the exact shape the
    operator launches in prod. Default weights (strip=10000/canvas=0) put
    an allowlisted unit on `strip` for certain (day-1 assignment); pass
    strip_bp=0, canvas_bp=10000 to simulate the documented switch-to-canvas
    `/revise` call — same key, weights only, no code/build change."""
    control_bp = 10000 - strip_bp - canvas_bp
    assert control_bp >= 0
    with engine.begin() as c:
        c.execute(insert(db.experiments_table).values(
            key="trades_home_inline", version=1, layer="trades_ui",
            status="running", unit_type="account",
            bucket_start=0, bucket_end=10000,
            targeting_json=json.dumps({"is_tester_allowlist": True}),
            variants_json=json.dumps([
                {"name": "control", "weight_bp": control_bp},
                {"name": "strip", "weight_bp": strip_bp,
                 "client_config": {"flags": {"trades_home_inline.strip": True}}},
                {"name": "canvas", "weight_bp": canvas_bp,
                 "client_config": {"flags": {"trades_home_inline.canvas": True}}},
            ]),
            primary_metric="wat", guardrails_json="[]",
            exposure_surface="trades_home", scope_json="{}",
            created_at="2026-08-09T00:00:00+00:00"))


# ── assignment ────────────────────────────────────────────────────────────

def test_assignment_is_operator_only_and_starts_on_strip(exp_engine, monkeypatch):
    monkeypatch.setenv("FTF_TESTER_ALLOWLIST", "u_operator")
    _mk_trades_home_inline_experiment(exp_engine)
    ex.invalidate_cache()
    # Allowlisted account unit → always `strip` (0bp control/canvas makes it
    # certain); a non-listed unit is excluded by TARGETING, not bucketing.
    assert ex.variant_for("u_operator", "trades_home_inline") == "strip"
    assert ex.variant_for("u_stranger", "trades_home_inline") is None


def test_switch_to_canvas_is_a_pure_weight_revise(exp_engine, monkeypatch):
    """The documented A→B switch: same experiment key, weights moved from
    strip=10000 to canvas=10000. No code change, no new build — proven by
    seeding the post-/revise shape directly and re-resolving."""
    monkeypatch.setenv("FTF_TESTER_ALLOWLIST", "u_operator")
    _mk_trades_home_inline_experiment(exp_engine, strip_bp=0, canvas_bp=10000)
    ex.invalidate_cache()
    assert ex.variant_for("u_operator", "trades_home_inline") == "canvas"
    assert ex.variant_for("u_stranger", "trades_home_inline") is None


# ── /api/feature-flags route ─────────────────────────────────────────────

def test_route_overlay_present_for_allowlisted_caller_only(client, exp_engine, monkeypatch):
    monkeypatch.setenv("FTF_TESTER_ALLOWLIST", "u_operator")
    _mk_trades_home_inline_experiment(exp_engine)
    ex.invalidate_cache()
    _install_sess(_mk_sess(user_id="u_operator"))
    code, body = _get(client, "/api/feature-flags")
    assert code == 200
    assert body["experiments"].get("trades_home_inline") == "strip"
    assert body["configs"]["trades_home_inline"]["flags"] == {
        "trades_home_inline.strip": True
    }


def test_route_byte_identical_for_non_allowlisted_caller(client, exp_engine, monkeypatch):
    """A non-allowlisted caller reading under a RUNNING experiment gets no
    new experiment/config keys — same binding guarantee #279 established
    for its own experiment, applied here."""
    monkeypatch.setenv("FTF_TESTER_ALLOWLIST", "u_operator")   # u_other NOT listed
    _mk_trades_home_inline_experiment(exp_engine)
    ex.invalidate_cache()
    _install_sess(_mk_sess(user_id="u_other"))
    code, body = _get(client, "/api/feature-flags")
    assert code == 200
    assert "trades_home_inline" not in body["experiments"]
    assert "trades_home_inline" not in body["configs"]

    # Baseline: identical request, fresh empty experiments DB (no row at
    # all) — proves the experiments/configs maps are identical either way
    # (the global `flags` map is untouched by this experiment either path,
    # so it's excluded from the comparison — it reflects config/features.json,
    # not this test's concern).
    eng2 = create_engine("sqlite:///:memory:",
                         connect_args={"check_same_thread": False})
    metadata.create_all(eng2)
    with patch.object(db, "engine", eng2), patch.object(db, "ro_engine", eng2):
        db._seed_experiment_layers()
        ex.invalidate_cache()
        _install_sess(_mk_sess(user_id="u_other"))
        code_base, body_base = _get(client, "/api/feature-flags")
    ex.invalidate_cache()
    assert code_base == 200
    assert body_base["experiments"] == {}
    assert body_base["configs"] == {}
    assert body["experiments"] == body_base["experiments"]
    assert body["configs"] == body_base["configs"]
