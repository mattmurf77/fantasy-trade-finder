"""Value-core serving plumbing: flag, knobs, the branch in _run_trade_job,
impressions evidence and the kill switch.

Spec: docs/plans/value-core-engine/lld.md §3, §9 (server/flag/knob/prepared
edits); acceptance + test list in specs.md §5.3.

These are PLUMBING tests. The `vc_stubs` fixture replaces pipeline.run (the
WP1/WP2 engine) and windows.infer_windows with deterministic stubs, and keeps
doing so after integration, so a change in the engine's choices never moves
them. Every flag-on run patches the three network touches
(_value_core_standings, _league_lineup_slots, _sleeper_roster_limit).

Covered:
  • registration: flag default-off and mirrored; 12 vc_* knobs seeded and
    absent from trade_service._DEFAULT_CFG;
  • flag OFF never imports backend.value_core;
  • flag ON (tester or vc_testers_only=0) serves value-core cards with a
    deck_impressions row + evidence per card; testers-only gate; intent,
    demo and preparation jobs stay legacy;
  • prepared inventory unsupported while ON; safety-signature entry;
  • owner request hash ignores vc_* keys;
  • standings fail-soft; a pipeline error fails the job with no fallback;
  • trades_generated carries engine_version="value_core".
"""
import importlib
import json
import os
import subprocess
import sys
import types as _t
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import backend.bakeoff_runner as bo
import backend.feature_flags as ff
import backend.prepared_trade_runtime as prepared_runtime
import backend.server as server
import backend.trade_service as ts
from backend.database import _MODEL_CONFIG_DEFAULTS
from backend.ranking_service import Player
from backend.tests.support import bakeoff_harness as H
from backend.trade_service import LeagueMember

REPO = Path(__file__).resolve().parents[2]

VC_DEFAULTS = {
    "vc_band": 0.20, "vc_stud_premium": 0.15, "vc_untouchable_min_ratio": 1.08,
    "vc_max_assets_per_side": 14.0, "vc_max_per_partner": 200.0, "vc_w_value": 1.0,
    "vc_w_outlook": 1.0, "vc_w_rank": 1.0, "vc_repeat_penalty": 0.15, "vc_player_cap": 3.0,
    "vc_standings_weight": 0.30, "vc_testers_only": 1.0,
}


@pytest.fixture
def vc_stubs(monkeypatch):
    """Stub WP1/WP2 so the serving plumbing is testable on its own. Returns the
    list of (snapshot, request, core_cfg, rank_cfg) the stubbed engine saw."""
    try:
        win = importlib.import_module("backend.value_core.windows")
    except ImportError:
        win = _t.ModuleType("backend.value_core.windows")
        monkeypatch.setitem(sys.modules, "backend.value_core.windows", win)
    monkeypatch.setattr(win, "infer_windows", lambda **kw: {}, raising=False)
    from backend.value_core import pipeline
    calls = []

    def fake_run(snapshot, request, core_cfg, rank_cfg, **kw):
        # one entry: viewer gives its highest-market asset for the first partner's highest one
        from backend.value_core.types import (
            CoreDiagnostics, DeckEntry, FairTrade, PipelineResult, Scores, ScoredTrade)
        calls.append((snapshot, request, core_cfg, rank_cfg))
        viewer = request.viewer_team_id
        partner = request.partner_team_id or sorted(t for t in snapshot.teams if t != viewer)[0]

        def top(team_id):
            return max(snapshot.teams[team_id].asset_ids,
                       key=lambda a: (snapshot.assets[a].market, a))

        give, recv = top(viewer), top(partner)
        gm, rm = snapshot.assets[give].market, snapshot.assets[recv].market
        trade = FairTrade(partner, (give,), (recv,), gm, rm, rm / gm, 0.0, None, False, (0, 0))
        scores = Scores(0.6, 0.5, 0.5, round(1.6 / 3, 6))
        detail = {
            "value": {"delta_ln": 0.0, "s_delta": 0.5, "best_in_id": recv, "best_in_market": rm,
                      "best_in_starter": True, "s_piece": 1.0},
            "outlook": {"scale": 1000.0,
                        "viewer": {"window": "middle", "lineup_gain": 0.0, "future_gain": 0.0, "score": 0.5},
                        "partner": {"window": "middle", "lineup_gain": 0.0, "future_gain": 0.0, "score": 0.5}},
            "rank": {"has_board": False, "gap_rel": 0.0, "top_asset": None, "top_side": None,
                     "rank_delta": None},
        }
        entry = DeckEntry(0, ScoredTrade(trade, scores, detail), scores.priority, ("Fair on value",))
        return PipelineResult([entry], CoreDiagnostics(partners=1, packages_viewer=1,
                                                      pairs_checked=1, fair=1), 1)

    monkeypatch.setattr(pipeline, "run", fake_run)
    return calls


def _vc_on(*, testers_only=0.0):
    """Flag ON + the three network touches neutralised (specs.md §5.3)."""
    return [
        patch.object(server, "_value_core_enabled", lambda: True),
        patch.dict(ts._cfg, {"vc_testers_only": testers_only}),
        patch.object(server, "_value_core_standings", lambda *a, **k: ({}, 0)),
        patch.object(server, "_league_lineup_slots", lambda *a, **k: None),
        patch.object(server, "_sleeper_roster_limit", lambda *a, **k: None),
    ]


def _vc_card_ids(job):
    return [c["trade_id"] for c in job.get("cards") or [] if c["trade_id"].startswith("vc_")]


# ── registration ────────────────────────────────────────────────────────────

def test_flag_registered_default_off_and_mirrored():
    assert "trade.value_core" in ff.FLAG_KEYS
    assert ff.DEFAULT_FLAGS["trade.value_core"] is False
    for rel in ("config/features.json", "backend/tests/fixtures/flags/release.json"):
        assert json.loads((REPO / rel).read_text())["trade.value_core"] is False, rel


def test_model_config_defaults_seeded_not_in_default_cfg():
    seeded = {k: v for k, v, _d in _MODEL_CONFIG_DEFAULTS if k.startswith("vc_")}
    assert seeded == pytest.approx(VC_DEFAULTS)
    assert len(seeded) == 12
    assert not [k for k in ts._DEFAULT_CFG if k.startswith("vc_")]


# ── flag off ────────────────────────────────────────────────────────────────

def test_flag_off_never_imports_value_core(monkeypatch, tmp_path):
    for name in [m for m in sys.modules if m.startswith("backend.value_core")]:
        monkeypatch.delitem(sys.modules, name)       # restored at teardown
    with patch.object(bo, "bakeoff_enabled", lambda: False):
        capture, job, _eng = H.run_capture()
    assert not [m for m in sys.modules if m.startswith("backend.value_core")]
    assert capture["status"] == "complete"
    assert not _vc_card_ids(job)
    assert "value_core" not in job
    # Importing the server itself must not pull the package in either; that
    # can only be observed in a fresh interpreter (this one imported it above).
    env = {k: v for k, v in os.environ.items()
           if k not in ("FTF_TEST_MODE", "FTF_SLEEPER_RECORD", "DATABASE_URL")}
    env["DATABASE_URL"] = f"sqlite:///{tmp_path / 'scratch.db'}"
    child = subprocess.run(
        [sys.executable, "-c", "import sys, backend.server; "
         "print(sorted(m for m in sys.modules if m.startswith('backend.value_core')))"],
        capture_output=True, text=True, cwd=REPO, env=env, timeout=180)
    assert child.returncode == 0, child.stderr[-2000:]
    assert child.stdout.strip().splitlines()[-1] == "[]"


# ── flag on ─────────────────────────────────────────────────────────────────

def test_flag_on_serves_value_core(vc_stubs):
    capture, job, _eng = H.run_capture(extra_patches=_vc_on())
    assert capture["status"] == "complete", capture["error"]
    assert len(vc_stubs) == 1
    snapshot, request, _core, _rank = vc_stubs[0]
    assert request.viewer_team_id == H.ME and request.partner_team_id is None
    assert request.fairness_threshold == 0.75
    assert set(snapshot.teams) == {H.ME, H.OPP, H.OPP2}

    cards = job["cards"]
    assert cards and len(_vc_card_ids(job)) == len(cards)
    assert all(c["preserve_server_order"] is True and c["basis"] == "consensus" for c in cards)
    assert [c["give"][0]["id"] for c in cards] == ["qb1"]
    assert [c["receive"][0]["id"] for c in cards] == ["wr1"]
    assert job["final_checks_pending"] is False
    assert job["value_core"]["served"] == len(cards)

    rows = capture["impressions"]
    assert len(rows) == len(cards)
    for pos, row in enumerate(rows):
        assert row["model_arm"] == "value_core" and row["policy_variant"] == "value_core"
        assert row["policy_version"] == "value-core-1" and row["arm_rank"] == pos
        assert row["fairness_threshold"] == pytest.approx(1 / 1.1, abs=1e-4)
        assert row["trade_concept_id"]
        ev = json.loads(row["valuation_json"])
        assert ev["generator"] == "value_core" and ev["deck_position"] == pos
        assert row["final_score"] == pytest.approx(ev["effective"])
        assert json.loads(row["assets_json"]) == {"give": ["qb1"], "receive": ["wr1"]}
    assert cards[0]["impression_id"]


def test_testers_only_gate(vc_stubs):
    patches = _vc_on(testers_only=1.0)
    with patch.object(server, "_load_tester_allowlist", lambda: set()):
        _capture, job, _eng = H.run_capture(extra_patches=patches)
    assert vc_stubs == [] and not _vc_card_ids(job)
    with patch.object(server, "_load_tester_allowlist", lambda: {"user_me"}):
        _capture, job, _eng = H.run_capture(extra_patches=patches)
    assert len(vc_stubs) == 1 and job["cards"] and len(_vc_card_ids(job)) == len(job["cards"])


def test_trade_intent_stays_legacy(vc_stubs):
    capture, job, _eng = H.run_capture(extra_patches=_vc_on(), trade_intent="consolidate")
    assert capture["status"] == "complete"
    assert vc_stubs == [] and not _vc_card_ids(job)
    assert all(r["model_arm"] != "value_core" for r in capture["impressions"])


def test_live_predicate_excludes_demo_and_preparation(monkeypatch):
    monkeypatch.setattr(server, "_value_core_enabled", lambda: True)
    monkeypatch.setitem(ts._cfg, "vc_testers_only", 0.0)
    live = dict(league_id="L", user_id="u", league_user_id="u", trade_intent=None, preparation=False)
    assert server._value_core_live(**live) is True
    assert server._value_core_live(**{**live, "league_id": "league_demo"}) is False
    assert server._value_core_live(**{**live, "preparation": True}) is False
    assert server._value_core_live(**{**live, "trade_intent": "tier_up"}) is False
    # The allowlist may match the league identity as well as the account.
    monkeypatch.setitem(ts._cfg, "vc_testers_only", 1.0)
    monkeypatch.setattr(server, "_load_tester_allowlist", lambda: {"owner_1"})
    assert server._value_core_live(**{**live, "league_user_id": "owner_1"}) is True
    monkeypatch.setattr(server, "_value_core_enabled", lambda: False)
    assert server._value_core_live(**{**live, "league_user_id": "owner_1"}) is False


def test_prepared_inventory_unsupported_when_on(monkeypatch):
    monkeypatch.setattr(prepared_runtime, "enabled", lambda _server: True)
    monkeypatch.setattr(server, "_owner_enabled", lambda _lid: True)
    monkeypatch.setattr(bo, "owner_only", lambda: True)
    monkeypatch.setattr(bo, "serve_owner", lambda: True)
    monkeypatch.setattr(bo, "owner_revision_enabled", lambda *_a: True)
    monkeypatch.setattr(server, "_value_core_enabled", lambda: False)
    assert prepared_runtime.supported(server, "L") is True
    monkeypatch.setattr(server, "_value_core_enabled", lambda: True)
    assert prepared_runtime.supported(server, "L") is False


def test_safety_signature_entry(monkeypatch):
    monkeypatch.setattr(server, "_value_core_enabled", lambda: False)
    off = server._trade_safety_signature()
    assert "value_core" not in off
    monkeypatch.setattr(server, "_value_core_enabled", lambda: True)
    on = server._trade_safety_signature()
    assert "value_core" in on and [k for k in on if k != "value_core"] == off


def test_owner_request_hash_ignores_vc_keys():
    players = {"a1": Player(id="a1", name="A", position="WR", team="AAA", age=25),
               "b1": Player(id="b1", name="B", position="RB", team="BBB", age=23)}
    members = [LeagueMember(user_id="me", username="me", roster=["a1"], elo_ratings={"a1": 1600.0}),
               LeagueMember(user_id="opp", username="opp", roster=["b1"], elo_ratings={"b1": 1650.0})]

    def context(extra):
        return {"players": players, "league": SimpleNamespace(members=members),
                "config": {**ts._DEFAULT_CFG, **extra}, "manager_preferences": {},
                "user_roster": ["a1"], "user_elo": {"a1": 1610.0}}

    base = server._owner_selected_assignment(context({}), "fair_packages", serve=True)["request_hash"]
    with_vc = server._owner_selected_assignment(context(VC_DEFAULTS), "fair_packages",
                                                serve=True)["request_hash"]
    assert with_vc == base
    # Non-vacuity: an ordinary knob still moves the hash.
    moved = server._owner_selected_assignment(context({"asset_floor_abs": 999.0}), "fair_packages",
                                              serve=True)["request_hash"]
    assert moved != base


def test_standings_failure_non_fatal(monkeypatch, caplog):
    import backend.outlook as outlook_pkg

    def boom(*a, **k):
        raise RuntimeError("sleeper down")

    monkeypatch.setattr(outlook_pkg, "build_league_state", boom)
    with caplog.at_level("WARNING", logger="trade_finder"):
        assert server._value_core_standings("L", "sleeper") == ({}, 0)
    assert any("standings unavailable" in r.getMessage() for r in caplog.records)
    # Non-Sleeper leagues never try.
    assert server._value_core_standings("L", "espn") == ({}, 0)
    # A good state maps league identity -> Standing.
    state = SimpleNamespace(completed_weeks=4, teams=[
        SimpleNamespace(user_id="u1", wins=3, losses=1, ties=0, points_for=512.4),
        SimpleNamespace(user_id="", wins=0, losses=0, ties=0, points_for=0.0)])
    monkeypatch.setattr(outlook_pkg, "build_league_state", lambda *a, **k: state)
    standings, weeks = server._value_core_standings("L", None)
    assert weeks == 4 and set(standings) == {"u1"}
    assert (standings["u1"].wins, standings["u1"].points_for) == (3, 512.4)


def test_pipeline_error_falls_back_to_legacy(vc_stubs, monkeypatch, caplog):
    """PRD Q1 (operator 2026-10-01): a value-core failure before anything is served is logged
    and the same job is finished by the legacy engine."""
    from backend.value_core import pipeline

    def broken(*a, **k):
        raise RuntimeError("value core exploded")

    monkeypatch.setattr(pipeline, "run", broken)
    with caplog.at_level("ERROR"):
        capture, job, _eng = H.run_capture(extra_patches=_vc_on())
    assert job["status"] == "complete" and not job.get("error")
    assert job["cards"] and not any(c["trade_id"].startswith("vc_") for c in job["cards"])
    assert "value_core" not in job
    assert all(r.get("model_arm") != "value_core" for r in capture["impressions"])
    assert any("falling back to the legacy engine" in r.getMessage() for r in caplog.records)


def test_fallback_matches_flag_off_output(vc_stubs, monkeypatch):
    """The fallback runs the untouched legacy path: the same canonical capture as flag off,
    except that the job records the value_core flag in its safety signature."""
    from backend.value_core import pipeline

    def broken(*a, **k):
        raise RuntimeError("x")

    monkeypatch.setattr(pipeline, "run", broken)
    fell_back, _job, _ = H.run_capture(extra_patches=_vc_on())
    flag_off, _job2, _ = H.run_capture()
    assert set(fell_back["job_keys"]) - set(flag_off["job_keys"]) == {"safety_policy"}
    strip = lambda c: {k: v for k, v in c.items() if k != "job_keys"}
    assert strip(fell_back) == strip(flag_off)


def test_trades_generated_engine_version(vc_stubs):
    rec = MagicMock()
    H.run_capture(extra_patches=_vc_on() + [patch.object(server, "record_event", rec)])
    generated = [c for c in rec.call_args_list if c.args[1] == "trades_generated"]
    assert len(generated) == 1
    props = generated[0].kwargs["props"]
    assert props["engine_version"] == "value_core" and props["count"] == 1
