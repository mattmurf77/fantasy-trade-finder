"""Calibration for tester-allowlisted accounts only (owner launch ruling 2026-11-25).

grading.blind is false in config/features.json. An allowlisted account gets it from a
running `calibration_rollout` experiment (docs/plans/blind-grading/lld.md §8.2), and
server._calibration_allowed checks the tester allowlist again. Founders' review lives
inside the Calibration tab, so a founder who is also allowlisted must keep the tab
(the merged flag map from GET /api/feature-flags), the /api/grading/* routes and the
/api/founder/* routes; a normal user gets none of the Calibration surface.

Nothing about the audience is mocked here: the experiment is created and launched
through the real admin routes (the same JSON body the runbook hands the owner), the
overlay is resolved by backend.experiments against an in-memory SQLite, and the
allowlist is read from a file by experiments.load_tester_allowlist. Only the blind
grading service call behind the gate is stubbed.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine

import backend.blind_grading as bg
import backend.database as db
import backend.experiments as experiments
import backend.feature_flags as ff
import backend.outlook_calibration as oc
import backend.server as server

CRON = "synthetic-cron-secret"
FOUNDER = "910000000000000001"      # allowlisted tester and founder
MEMBER = "910000000000000002"       # an ordinary app user
LEAGUE = "L1"
TOKENS = {FOUNDER: "overlay-founder-tok", MEMBER: "overlay-member-tok"}
CURRENT = f"/api/grading/sessions/current?league_id={LEAGUE}"

# The experiment the owner submits (runbook, Gate 2; lld.md §8.2).
CALIBRATION_ROLLOUT = {
    "key": "calibration_rollout",
    "layer": "ranking",
    "unit_type": "account",
    "bucket_start": 0,
    "bucket_end": 10000,
    "targeting": {"is_tester_allowlist": True},
    "variants": [
        {"name": "control", "weight_bp": 0},
        {"name": "treatment", "weight_bp": 10000,
         "client_config": {"flags": {"grading.blind": True}}},
    ],
    "primary_metric": "activation_rate",
    "exposure_surface": "calibration_tab",
    "hypothesis": "Allowlist rollout of Calibration for testers; not a powered test.",
    "override_underpowered": True,
}


@pytest.fixture
def world(monkeypatch, tmp_path):
    eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    db.metadata.create_all(eng)
    allow = tmp_path / "tester_allowlist.json"
    allow.write_text(json.dumps([FOUNDER]))
    monkeypatch.setattr(experiments, "_ALLOWLIST_FILE", str(allow))
    monkeypatch.delenv("FTF_TESTER_ALLOWLIST", raising=False)
    monkeypatch.setenv("FOUNDER_ACCOUNTS", FOUNDER)
    monkeypatch.setattr(ff, "_flags_cache", {
        **ff.flags_dict(), "grading.blind": False, "experiments.engine": True,
        "founder.review": True, "grading.outlook_round": False})
    monkeypatch.setattr(server, "_CRON_SECRET", CRON)
    monkeypatch.setattr(oc, "r4_round_enabled", lambda: False)
    monkeypatch.setattr(bg, "current_session", lambda **kw: {"session": None})
    server.app.config["TESTING"] = True
    client = server.app.test_client()
    with patch.object(db, "engine", eng), patch.object(db, "ro_engine", eng):
        db._seed_experiment_layers()
        experiments.invalidate_cache()
        with server._sessions_lock:
            for uid, tok in TOKENS.items():
                server._sessions[tok] = {
                    "user_id": uid, "league_user_id": uid, "verified": True,
                    "league": SimpleNamespace(league_id=LEAGUE, platform="sleeper"),
                    "players": [], "trade_svc": object(), "last_active": 0.0}
        try:
            yield client
        finally:
            with server._sessions_lock:
                for tok in TOKENS.values():
                    server._sessions.pop(tok, None)
            experiments.invalidate_cache()


def _launch(client) -> None:
    cron = {"X-Cron-Secret": CRON}
    r = client.post("/api/admin/experiments", json=CALIBRATION_ROLLOUT, headers=cron)
    assert r.status_code == 201, r.get_json()
    assert r.get_json() == {"key": "calibration_rollout", "version": 1, "status": "draft"}
    r = client.post("/api/admin/experiments/calibration_rollout/transition", headers=cron,
                    json={"version": 1, "to": "running", "override_underpowered": True,
                          "reason": "allowlist rollout for Gate 2 grading, not a powered test"})
    assert r.status_code == 200 and r.get_json()["status"] == "running", r.get_json()


def _as(uid: str) -> dict:
    return {"X-Session-Token": TOKENS[uid]}


def test_shipped_config_has_calibration_off():
    """The posture this file protects starts from grading.blind false in the shipped map."""
    features = json.loads((Path(__file__).resolve().parents[2]
                           / "config/features.json").read_text())
    assert features["grading.blind"] is False
    assert features["experiments.engine"] is True
    assert features["founder.review"] is True


def test_allowlisted_founder_keeps_calibration_and_founders_review(world):
    _launch(world)

    flags = world.get("/api/feature-flags", headers=_as(FOUNDER)).get_json()
    assert flags["flags"]["grading.blind"] is False                     # global map stays off
    assert flags["experiments"]["calibration_rollout"] == "treatment"
    assert flags["configs"]["calibration_rollout"]["flags"]["grading.blind"] is True

    r = world.get(CURRENT, headers=_as(FOUNDER))
    assert (r.status_code, r.get_json()) == (200, {"session": None})

    r = world.get("/api/founder/capability", headers=_as(FOUNDER))
    assert (r.status_code, r.get_json()) == (200, {"founder_review": True})


def test_normal_user_gets_no_calibration(world):
    _launch(world)

    flags = world.get("/api/feature-flags", headers=_as(MEMBER)).get_json()
    assert flags["flags"]["grading.blind"] is False
    assert "calibration_rollout" not in flags["experiments"]
    assert "calibration_rollout" not in flags["configs"]

    r = world.get(CURRENT, headers=_as(MEMBER))
    assert (r.status_code, r.get_json()) == (404, {"error": "not_found"})
    assert world.get("/api/founder/capability", headers=_as(MEMBER)).status_code == 404


def test_without_the_overlay_nobody_gets_calibration(world):
    """Before the owner launches the experiment (or after he stops it) the allowlisted
    founder has no grading.blind either: the global flag is off. Founders' review routes
    do not read grading.blind, but the app shows them only inside the Calibration tab."""
    flags = world.get("/api/feature-flags", headers=_as(FOUNDER)).get_json()
    assert "calibration_rollout" not in flags["configs"]
    assert world.get(CURRENT, headers=_as(FOUNDER)).status_code == 404

    _launch(world)
    assert world.get(CURRENT, headers=_as(FOUNDER)).status_code == 200
    r = world.post("/api/admin/experiments/calibration_rollout/transition",
                   headers={"X-Cron-Secret": CRON}, json={"version": 1, "to": "stopped"})
    assert r.status_code == 200
    assert world.get(CURRENT, headers=_as(FOUNDER)).status_code == 404
    assert world.get("/api/founder/capability", headers=_as(FOUNDER)).status_code == 200


def test_overlay_alone_is_not_enough_off_the_allowlist(world, monkeypatch):
    """The two server checks are independent: an overlay that somehow reached a
    non-allowlisted account (here, targeting widened to everyone) still fails
    _calibration_allowed and 404s."""
    monkeypatch.setitem(CALIBRATION_ROLLOUT, "targeting", {})
    _launch(world)
    flags = world.get("/api/feature-flags", headers=_as(MEMBER)).get_json()
    assert flags["configs"]["calibration_rollout"]["flags"]["grading.blind"] is True
    assert world.get(CURRENT, headers=_as(MEMBER)).status_code == 404
