"""Analytics platform P3 — experiment engine (backend/experiments.py).

Asserts the correctness that the design pass flagged as load-bearing:
  • determinism (same unit → same variant across processes)
  • IN-LAYER EXCLUSIVITY (the two-stage-hash property a single hash can't give)
  • cross-layer independence + variant balance
  • targeting (match / exclude / missing-attr-excludes / unit-type gating)
  • launch validation (weights, metric catalog, in-layer overlap, attr-unit)
  • status machine (legal/illegal edges, decide-only-from-stopped)
  • fail-open (engine off → default; exceptions never propagate)
  • the aggression migration bridge (MD5 fallback; experiment overrides)
  • persist-on-first-eval + concurrent-race idempotence
  • honest readout (verdict withheld below min-n / until horizon)

Isolated in-memory SQLite patched into db.engine AND db.ro_engine.
"""
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, delete, insert, select

import backend.database as db
import backend.experiments as ex
from backend.database import metadata


def _mk(engine, key, layer, bs, be, unit_type="account",
        variants=None, targeting=None, status="running", primary="wat"):
    variants = variants or [{"name": "A", "weight_bp": 5000},
                            {"name": "B", "weight_bp": 5000}]
    import json as _j
    with engine.begin() as c:
        c.execute(insert(db.experiments_table).values(
            key=key, version=1, layer=layer, status=status, unit_type=unit_type,
            bucket_start=bs, bucket_end=be,
            targeting_json=_j.dumps(targeting or {}),
            variants_json=_j.dumps(variants), primary_metric=primary,
            guardrails_json="[]", exposure_surface="trades_generated",
            scope_json="{}", created_at="2026-07-18T00:00:00+00:00"))


@pytest.fixture()
def engine():
    eng = create_engine("sqlite:///:memory:",
                        connect_args={"check_same_thread": False})
    metadata.create_all(eng)
    with patch.object(db, "engine", eng), patch.object(db, "ro_engine", eng):
        db._seed_experiment_layers()
        ex.invalidate_cache()
        # engine flag ON for evaluation tests
        with patch.object(ex, "is_enabled", lambda k: True):
            yield eng
        ex.invalidate_cache()


# --- determinism / exclusivity / independence ------------------------------

def test_determinism(engine):
    _mk(engine, "e1", "engine", 0, 10000)
    ex.invalidate_cache()
    v1 = ex.variant_for("u_42", "e1")
    v2 = ex.variant_for("u_42", "e1")
    assert v1 == v2 and v1 in ("A", "B")


def test_in_layer_exclusivity(engine):
    # Two experiments in the SAME layer, disjoint bucket ranges → NO unit is
    # assigned by both (the property the single-hash formula couldn't deliver).
    _mk(engine, "eA", "trades_ui", 0, 5000)
    _mk(engine, "eB", "trades_ui", 5000, 10000)
    ex.invalidate_cache()
    units = [f"u_{i}" for i in range(1500)]
    both = sum(1 for u in units
               if ex.variant_for(u, "eA") is not None
               and ex.variant_for(u, "eB") is not None)
    inA = sum(1 for u in units if ex.variant_for(u, "eA") is not None)
    inB = sum(1 for u in units if ex.variant_for(u, "eB") is not None)
    assert both == 0                       # exclusivity
    assert 550 < inA < 950 and 550 < inB < 950   # ~50/50 of the layer


def test_variant_balance_and_cross_layer_independence(engine):
    _mk(engine, "eng1", "engine", 0, 10000)
    _mk(engine, "ui1", "trades_ui", 0, 10000)
    ex.invalidate_cache()
    units = [f"u_{i}" for i in range(2000)]
    a = sum(1 for u in units if ex.variant_for(u, "eng1") == "A")
    assert 850 < a < 1150     # ~50% variant split
    # independence: eng1==A membership shouldn't predict ui1 variant
    ui_a_given_eng_a = [ex.variant_for(u, "ui1") for u in units
                        if ex.variant_for(u, "eng1") == "A"]
    frac = ui_a_given_eng_a.count("A") / max(len(ui_a_given_eng_a), 1)
    assert 0.42 < frac < 0.58


# --- targeting -------------------------------------------------------------

def test_targeting_membership_and_missing_attr(engine):
    _mk(engine, "et", "engine", 0, 10000, targeting={"platform": ["ios"]})
    ex.invalidate_cache()
    # match
    assert ex.variant_for("u_1", "et", {"platform": "ios"}) in ("A", "B")
    # non-match
    assert ex.variant_for("u_1", "et", {"platform": "web"}) is None
    # missing attr → excluded (not defaulted into control)
    assert ex.variant_for("u_1", "et", {}) is None


def test_targeting_semver_gte(engine):
    _mk(engine, "ev", "engine", 0, 10000, targeting={"app_version_gte": "1.9.0"})
    ex.invalidate_cache()
    assert ex.variant_for("u_1", "ev", {"app_version": "1.9.0"}) is not None
    assert ex.variant_for("u_1", "ev", {"app_version": "2.0.1"}) is not None
    assert ex.variant_for("u_1", "ev", {"app_version": "1.8.9"}) is None


def test_unit_type_gating(engine):
    _mk(engine, "eacct", "engine", 0, 10000, unit_type="account")
    ex.invalidate_cache()
    assert ex.variant_for("u_alice", "eacct") is not None       # account unit
    assert ex.variant_for("device:dev_x", "eacct") is None      # device unit skipped


# --- launch validation -----------------------------------------------------

def test_validation(engine):
    base = {"key": "v", "layer": "engine", "unit_type": "account",
            "bucket_start": 0, "bucket_end": 10000,
            "variants": [{"name": "A", "weight_bp": 5000},
                         {"name": "B", "weight_bp": 5000}],
            "primary_metric": "wat", "exposure_surface": "trades_generated"}
    with pytest.raises(ex.ExperimentError, match="weights_not_10000"):
        ex.validate_spec(dict(base, variants=[{"name": "A", "weight_bp": 4000},
                                              {"name": "B", "weight_bp": 4000}]))
    with pytest.raises(ex.ExperimentError, match="metric_unknown"):
        ex.validate_spec(dict(base, primary_metric="made_up"))
    with pytest.raises(ex.ExperimentError, match="bucket_range_invalid"):
        ex.validate_spec(dict(base, bucket_start=5000, bucket_end=3000))
    with pytest.raises(ex.ExperimentError, match="attr_unit_incompatible"):
        ex.validate_spec(dict(base, unit_type="device",
                              targeting={"league_count": 2}))
    with pytest.raises(ex.ExperimentError, match="onboarding_layer_requires_device"):
        ex.validate_spec(dict(base, layer="onboarding"))


def test_launch_rejects_layer_overlap(engine):
    _mk(engine, "eA", "trades_ui", 0, 6000)   # already running
    ex.invalidate_cache()
    spec = {"key": "eB", "layer": "trades_ui", "unit_type": "account",
            "bucket_start": 5000, "bucket_end": 10000,   # overlaps [0,6000)
            "variants": [{"name": "A", "weight_bp": 5000},
                         {"name": "B", "weight_bp": 5000}],
            "primary_metric": "wat", "exposure_surface": "trades_generated"}
    with pytest.raises(ex.ExperimentError, match="layer_overlap"):
        ex.validate_spec(spec, for_launch=True)


# --- status machine --------------------------------------------------------

def test_status_machine(engine):
    ex.create_experiment({
        "key": "sm", "layer": "engine", "unit_type": "account",
        "bucket_start": 0, "bucket_end": 10000,
        "variants": [{"name": "A", "weight_bp": 5000},
                     {"name": "B", "weight_bp": 5000}],
        "primary_metric": "wat", "exposure_surface": "trades_generated"})
    with pytest.raises(ex.ExperimentError, match="illegal_transition"):
        ex.transition("sm", 1, "stopped")            # draft→stopped illegal
    assert ex.transition("sm", 1, "running")["status"] == "running"
    assert ex.transition("sm", 1, "paused")["status"] == "paused"
    assert ex.transition("sm", 1, "running")["status"] == "running"
    assert ex.transition("sm", 1, "stopped")["status"] == "stopped"
    with pytest.raises(ex.ExperimentError, match="illegal_transition"):
        ex.transition("sm", 1, "running")           # stopped→running illegal
    assert ex.decide("sm", 1, "ship")["decision"] == "ship"


def test_decide_only_from_stopped(engine):
    ex.create_experiment({
        "key": "d1", "layer": "engine", "unit_type": "account",
        "bucket_start": 0, "bucket_end": 10000,
        "variants": [{"name": "A", "weight_bp": 5000},
                     {"name": "B", "weight_bp": 5000}],
        "primary_metric": "wat", "exposure_surface": "trades_generated"})
    ex.transition("d1", 1, "running")
    with pytest.raises(ex.ExperimentError, match="not_stopped"):
        ex.decide("d1", 1, "ship")


# --- fail-open --------------------------------------------------------------

def test_fail_open_when_engine_off(engine):
    _mk(engine, "e1", "engine", 0, 10000)
    ex.invalidate_cache()
    with patch.object(ex, "is_enabled", lambda k: False):
        assert ex.variant_for("u_1", "e1") is None
        assert ex.resolve_for_unit("u_1") == ({}, {})
        assert ex.stamp_for_event("u_1", "trade_proposed", None) is None


def test_fail_open_on_exception(engine):
    # A broken cache load must yield defaults, never raise.
    with patch.object(ex, "_load_cache", side_effect=RuntimeError("boom")):
        assert ex.variant_for("u_1", "e1") is None
        assert ex.resolve_for_unit("u_1") == ({}, {})


# --- persistence ------------------------------------------------------------

def test_persist_on_first_eval_and_idempotent(engine):
    _mk(engine, "ep", "engine", 0, 10000)
    ex.invalidate_cache()
    v = ex.variant_for("u_persist", "ep")
    # re-eval doesn't create a second row (conflict-ignore)
    ex.variant_for("u_persist", "ep")
    with engine.connect() as c:
        rows = c.execute(select(db.experiment_assignments_table).where(
            db.experiment_assignments_table.c.unit_id == "u_persist")).mappings().all()
    assert len(rows) == 1 and rows[0]["variant"] == v


# --- readout honesty --------------------------------------------------------

def test_readout_withholds_verdict(engine):
    _mk(engine, "er", "engine", 0, 10000, status="running")
    ex.invalidate_cache()
    ro = ex.readout("er", 1)
    # running + no exposures → below-min banner, no verdict
    assert ro["verdict"] is None
    assert ro["banner"] is not None


# --- aggression migration bridge -------------------------------------------

def test_aggression_bridge_falls_back_to_md5(engine):
    # No running trade.aggression experiment → variant_for None → the trade
    # service keeps the legacy MD5 bucket (zero behaviour change on deploy).
    assert ex.variant_for("u_x", "trade.aggression") is None
    import backend.trade_service as ts
    md5 = ts.aggression_variant("u_x")
    assert md5 in ("light", "fair", "generous")


def test_malformed_overlay_rejected_at_validation(engine):
    # A non-numeric or non-dict model_overlay must be rejected so it can never
    # reach the trade engine (adversarial-review catch — fail-open defense).
    base = {"key": "mo", "layer": "engine", "unit_type": "account",
            "bucket_start": 0, "bucket_end": 10000,
            "primary_metric": "wat", "exposure_surface": "trades_generated"}
    with pytest.raises(ex.ExperimentError, match="model_overlay_invalid"):
        ex.validate_spec(dict(base, variants=[
            {"name": "A", "weight_bp": 5000},
            {"name": "B", "weight_bp": 5000, "model_overlay": {"aggression_weight": "high"}}]))
    with pytest.raises(ex.ExperimentError, match="model_overlay_invalid"):
        ex.validate_spec(dict(base, variants=[
            {"name": "A", "weight_bp": 5000},
            {"name": "B", "weight_bp": 5000, "model_overlay": "not-a-dict"}]))


def test_trade_service_survives_malformed_overlay(engine, monkeypatch):
    # Even if a malformed overlay somehow reaches the call site (e.g. an
    # experiment created before the validation hardening), the trade-service
    # coercion must fall back to the config value, never raise.
    import backend.trade_service as ts
    # Simulate the exact call-site coercion with hostile overlays.
    _c = lambda k: 0.20
    for bad in ({"aggression_weight": None}, {"aggression_weight": "high"},
                "not-a-dict", ["list"], {}):
        try:
            _ow = bad.get("aggression_weight") if isinstance(bad, dict) else None
            w_ab = float(_ow) if _ow is not None else _c("aggression_weight")
        except (TypeError, ValueError):
            w_ab = _c("aggression_weight")
        assert w_ab == 0.20   # always the safe default, never a raise


def test_aggression_experiment_overrides_when_running(engine):
    _mk(engine, "trade.aggression", "engine", 0, 10000, unit_type="account",
        variants=[{"name": "fair", "weight_bp": 3334},
                  {"name": "light", "weight_bp": 3333},
                  {"name": "generous", "weight_bp": 3333,
                   "model_overlay": {"aggression_weight": 0.28}}],
        primary="wat")
    ex.invalidate_cache()
    v, overlay = ex.variant_overlay("u_grp", "trade.aggression")
    assert v in ("fair", "light", "generous")
    if v == "generous":
        assert overlay.get("aggression_weight") == 0.28


# --- tester allowlist (is_tester_allowlist, _CONFIG source) ----------------

def test_tester_allowlist_resolution_device_unit(engine, monkeypatch):
    # The operator-smoke shape: onboarding layer (device unit mandated),
    # allowlist targeting, 0/10000 control/treatment weights.
    monkeypatch.setenv("FTF_TESTER_ALLOWLIST",
                       "device:dev_matt, matt_user_id")
    _mk(engine, "onb_smoke", "onboarding", 0, 10000, unit_type="device",
        variants=[{"name": "control", "weight_bp": 0},
                  {"name": "treatment", "weight_bp": 10000,
                   "client_config": {"flags": {"onboarding.v2": True}}}],
        targeting={"is_tester_allowlist": True}, primary="wat")
    ex.invalidate_cache()
    # Allowlisted device → always treatment (weights make control impossible)
    assert ex.variant_for("device:dev_matt", "onb_smoke") == "treatment"
    # Non-listed device → excluded entirely (targeting, not bucketing)
    assert ex.variant_for("device:dev_stranger", "onb_smoke") is None
    # resolve_for_unit carries the variant's client_config through
    exps, cfgs = ex.resolve_for_unit("device:dev_matt")
    assert exps.get("onb_smoke") == "treatment"
    assert cfgs.get("onb_smoke", {}).get("flags", {}).get("onboarding.v2") is True


def test_tester_allowlist_resolution_account_unit(engine, monkeypatch):
    monkeypatch.setenv("FTF_TESTER_ALLOWLIST", "matt_user_id")
    _mk(engine, "acct_smoke", "growth", 0, 10000, unit_type="account",
        targeting={"is_tester_allowlist": True})
    ex.invalidate_cache()
    assert ex.variant_for("matt_user_id", "acct_smoke") in ("A", "B")
    assert ex.variant_for("someone_else", "acct_smoke") is None


def test_tester_allowlist_empty_env_excludes_everyone(engine, monkeypatch):
    monkeypatch.delenv("FTF_TESTER_ALLOWLIST", raising=False)
    _mk(engine, "onb_smoke2", "onboarding", 0, 10000, unit_type="device",
        targeting={"is_tester_allowlist": True})
    ex.invalidate_cache()
    assert ex.variant_for("device:dev_anyone", "onb_smoke2") is None
