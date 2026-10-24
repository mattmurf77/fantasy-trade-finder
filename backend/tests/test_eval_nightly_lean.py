"""Lean nightly (the eval pass runs last in the daily tick: OOM risk).

  - run_all decides what is due before loading anything, and returns
    without touching load_decks when nothing is.
  - load_decks selects only eval's columns (+ features_compact and
    evidence_tier when the table has them).
  - project_features=True trims each features dict to contract keys, and
    nothing downstream moves: nightly estimates and a value-model fit are
    identical with and without it.
"""

from datetime import datetime, timezone

import pytest
from sqlalchemy import Column, MetaData, Text, create_engine, event, insert

import backend.database as db_module
import backend.value_model as vm
from backend.database import deck_impressions_table, deck_outcomes_table, metadata, user_taste_table
from backend.eval import contract as C
from backend.eval import nightly
from backend.eval.data import EVAL_COLUMNS, load_decks
from backend.eval.persistence import append_run, load_runs
from backend.eval.scorers import registered_names
from backend.eval.synth import build_synthetic_db


def _candidates():
    return [n for n in registered_names() if n not in nightly._SKIP and n != "production"]


def test_run_all_returns_early_when_nothing_is_due(tmp_path, monkeypatch):
    monkeypatch.setenv("EVAL_RUNS_DIR", str(tmp_path / "runs"))
    today = datetime.now(timezone.utc).date().isoformat()
    for name in _candidates():
        append_run({"schema_version": 1, "run_date": today, "scorer": name,
                    "window_days": 30})

    def boom(*a, **kw):
        raise AssertionError("load_decks must not run when nothing is due")

    monkeypatch.setattr(nightly, "load_decks", boom)
    monkeypatch.setattr(nightly, "evaluate", boom)
    stats = nightly.run_all(window_days=30)
    assert stats["ran"] == 0 and stats["errors"] == 0
    assert stats["skipped"] == len(_candidates())
    assert "nothing due" in stats["summary"]
    assert len(load_runs()) == len(_candidates())   # no baseline record either


def test_run_all_loads_projected_decks_when_due(tmp_path, monkeypatch):
    monkeypatch.setenv("EVAL_RUNS_DIR", str(tmp_path / "runs"))
    calls = []
    monkeypatch.setattr(nightly, "load_decks", lambda **kw: calls.append(kw) or [])
    nightly.run_all(window_days=30)
    assert len(calls) == 1 and calls[0]["project_features"] is True


def _selected_columns(engine, fn):
    """Run fn() and return the column names of the deck_impressions SELECT."""
    seen = []

    def capture(conn, cursor, statement, params, context, executemany):
        if "FROM deck_impressions" in statement:
            seen.append(statement)

    event.listen(engine, "before_cursor_execute", capture)
    try:
        fn()
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    (sql,) = seen
    head = sql.split("FROM deck_impressions")[0].replace("SELECT", "", 1)
    return {c.strip().split(".")[-1] for c in head.split(",")}


def test_load_decks_selects_only_eval_columns():
    eng = create_engine("sqlite:///:memory:")
    metadata.create_all(eng, tables=[deck_impressions_table, deck_outcomes_table])
    cols = _selected_columns(eng, lambda: load_decks(engine=eng))
    assert cols == set(EVAL_COLUMNS)
    assert not cols & {"valuation_json", "assets_json"}


def test_load_decks_adds_optional_columns_when_the_table_has_them(monkeypatch):
    import backend.eval.data as data_mod
    md = MetaData()
    imp = deck_impressions_table.to_metadata(md)
    imp.append_column(Column("features_compact", Text))
    imp.append_column(Column("evidence_tier", Text))
    deck_outcomes_table.to_metadata(md)
    eng = create_engine("sqlite:///:memory:")
    md.create_all(eng)
    monkeypatch.setattr(data_mod, "deck_impressions_table", imp)
    cols = _selected_columns(eng, lambda: load_decks(engine=eng))
    assert cols == set(EVAL_COLUMNS) | {"features_compact", "evidence_tier"}


def test_projection_keeps_every_contract_key():
    assert C.FROZEN_INPUT_KEYS | C.IDENTITY_KEYS <= C.PROJECTION_KEYS
    for name in registered_names():
        assert C.allowed_keys(name) <= C.PROJECTION_KEYS


# ---------------------------------------------------------------------------
# Nothing downstream moves under projection
# ---------------------------------------------------------------------------

@pytest.fixture()
def synth(tmp_path, monkeypatch):
    """A synthetic window, a taste DB so prefMatch is live, and a value model
    trained on the unprojected decks and persisted for the scorer."""
    db_url = f"sqlite:///{tmp_path / 'synth.db'}"
    build_synthetic_db(db_url, n_decks=20, seed=4, days_span=20)
    taste = create_engine("sqlite:///:memory:",
                          connect_args={"check_same_thread": False})
    metadata.create_all(taste)
    # "prior:" rows: taste_service never time-decays them, so two fits a
    # moment apart see bit-identical prefMatch (swipe-learned rows decay
    # with the wall clock and would differ in the last bits).
    with taste.begin() as conn:
        conn.execute(insert(user_taste_table), [
            {"user_id": f"user{u}", "attr": f"prior:{a}", "w_short": 0.0,
             "w_long": 1.0 + u, "updated_at": "2026-10-01T00:00:00+00:00"}
            for u in range(6) for a in ("partner:opp1", "givepos:RB", "shape:2x1")
        ])
    monkeypatch.setattr(db_module, "engine", taste)
    monkeypatch.setenv("VALUE_MODEL_DIR", str(tmp_path / "vm"))
    monkeypatch.setattr(vm, "_model_cache", None)
    return db_url


def test_projection_drops_wide_keys(synth):
    full = load_decks(db_url=synth)[0].cards[0].features
    lean = load_decks(db_url=synth, project_features=True)[0].cards[0].features
    assert "give_value_band" in full and "give_value_band" not in lean
    assert set(lean) == set(full) & C.PROJECTION_KEYS


def test_value_model_fit_identical_on_projected_decks(synth):
    fixed = datetime(2026, 10, 22, tzinfo=timezone.utc)
    full = vm.train_model(load_decks(db_url=synth), as_of=fixed)
    lean = vm.train_model(load_decks(db_url=synth, project_features=True), as_of=fixed)
    assert full is not None and lean is not None
    assert full.to_dict() == lean.to_dict()


def test_nightly_estimates_identical_with_and_without_projection(synth, tmp_path, monkeypatch):
    vm.append_model(vm.train_model(load_decks(db_url=synth),
                                   as_of=datetime(2026, 10, 22, tzinfo=timezone.utc)))
    vm._model_cache = None
    real = nightly.load_decks

    def records(runs_dir, project):
        monkeypatch.setenv("EVAL_RUNS_DIR", str(tmp_path / runs_dir))
        monkeypatch.setattr(nightly, "load_decks",
                            lambda **kw: real(**{**kw, "project_features": project}))
        stats = nightly.run_all(window_days=30, db_url=synth, ess_min=1,
                                bootstrap=100, seed=3)
        assert stats["errors"] == 0
        keep = ("scorer", "n_total", "n_included", "excluded", "metrics",
                "missing_inputs_decks", "partial_run_decks", "tilt_clipped")
        return {r["scorer"]: {k: r[k] for k in keep} for r in load_runs()}

    full, lean = records("full", False), records("lean", True)
    assert full == lean
    assert set(full) == set(_candidates()) | {"production"}
    assert full["value_model"]["n_included"] > 0    # graded, not scorer_error
