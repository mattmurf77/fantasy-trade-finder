"""Decision 8 (operator, 2026-11-11): keep weekly BASELINE forecast runs past
the 7-day history window so the season's slot odds can be scored against the
final draft order (docs/plans/pick-value-projected-slot/design.md §10, §12).

`config/league_projections.json` `baseline_retention_days` extends
`store.maintenance`'s delete for complete runs whose `input_json.kind` is
`baseline`; such a run keeps its `result_json` and drops its `snapshot_json`.
Scenario runs, failed runs and anything past the extended window still go at
`retention_days`; the key absent is today's behaviour.
"""
from datetime import datetime, timedelta, timezone
import json

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.pool import StaticPool

from backend import database as db
from backend.league_projections import batch, store


@pytest.fixture
def runs(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    db.metadata.create_all(engine, tables=[db.league_projection_runs_table,
                                           db.league_projection_targets_table])
    monkeypatch.setattr(db, "engine", engine)
    now = datetime.now(timezone.utc)

    def add(run_id, *, days, kind="baseline", status="complete"):
        stamp = (now - timedelta(days=days)).isoformat()
        with engine.begin() as conn:
            conn.execute(db.league_projection_runs_table.insert().values(
                run_id=run_id, user_id="u", league_id="1", status=status, created_at=stamp,
                updated_at=stamp, expires_at=(now + timedelta(days=1)).isoformat(),
                request_hash="h", input_json=json.dumps({"kind": kind}),
                snapshot_json='{"big": true}', result_json='{"teams": []}'))

    def rows():
        t = db.league_projection_runs_table
        with engine.connect() as conn:
            return {r.run_id: r.snapshot_json for r in
                    conn.execute(select(t.c.run_id, t.c.snapshot_json)).all()}

    def settings(**extra):
        monkeypatch.setattr(batch, "settings", lambda: {"retention_days": 7, **extra})

    add("weekly-old", days=30)
    add("weekly-recent", days=3)
    add("scenario-old", days=30, kind="scenario")
    add("failed-old", days=30, status="failed")
    add("weekly-ancient", days=120)
    yield add, rows, settings
    engine.dispose()


def test_absent_key_is_todays_retention(runs):
    _add, rows, settings = runs
    settings()
    store.maintenance()
    assert rows() == {"weekly-recent": '{"big": true}'}


def test_baseline_runs_are_kept_for_the_scoring_window(runs):
    """Sabotage: drop `t.c.run_id.not_in(kept)` from the delete → weekly-old goes."""
    _add, rows, settings = runs
    settings(baseline_retention_days=90)
    store.maintenance()
    assert rows() == {"weekly-recent": '{"big": true}', "weekly-old": None}


def test_kept_runs_keep_their_result_but_drop_the_snapshot(runs):
    """Sabotage: skip the snapshot update → weekly-old keeps its capture."""
    _add, _rows, settings = runs
    settings(baseline_retention_days=90)
    store.maintenance()
    t = db.league_projection_runs_table
    with db.engine.connect() as conn:
        row = conn.execute(select(t).where(t.c.run_id == "weekly-old")).mappings().one()
    assert row["result_json"] == '{"teams": []}' and row["snapshot_json"] is None


def test_scenarios_and_failures_are_never_kept(runs):
    """Sabotage: drop the `kind == baseline` filter → the scenario survives."""
    _add, rows, settings = runs
    settings(baseline_retention_days=400)
    store.maintenance()
    assert "scenario-old" not in rows() and "failed-old" not in rows()
    assert "weekly-ancient" in rows()


def test_malformed_input_json_is_not_a_baseline():
    assert store._is_baseline("not json") is False
    assert store._is_baseline(None) is False
    assert store._is_baseline('["baseline"]') is False
    assert store._is_baseline('{"kind": "baseline"}') is True


def test_settings_validate_the_window(monkeypatch, tmp_path):
    real = json.loads(batch.CONFIG_PATH.read_text())
    assert batch.settings()["baseline_retention_days"] == real["baseline_retention_days"]
    for bad in (3, 401):
        path = tmp_path / f"cfg{bad}.json"
        path.write_text(json.dumps({**real, "baseline_retention_days": bad}))
        monkeypatch.setattr(batch, "CONFIG_PATH", path)
        with pytest.raises(ValueError):
            batch.settings()
