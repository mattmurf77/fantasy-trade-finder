"""Offline harness mechanics. Cache regressions now use the real server in
test_trade_job_admission.py; historical reproductions remain in research history.
"""
import ast
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from scripts.research_trade_pipeline import (
    ObservedJob, Timeline, configure_isolation, forbid_network, instrument_worker,
)


SERVER = Path(__file__).resolve().parents[1] / "server.py"


def test_all_current_worker_markers_are_unique():
    tree = ast.parse(SERVER.read_text())
    node = next(node for node in tree.body
                if isinstance(node, ast.FunctionDef) and node.name == "_run_trade_job")
    fn = instrument_worker(ast.unparse(node), {"_TradeExecutionContext": object}, lambda *_: None)
    assert callable(fn)


def test_instrumentation_preserves_function_result_and_rejects_drift():
    source = "def worker():\n    try:\n        value = 4\n        return value + 1\n    except Exception:\n        raise\n"
    visited = []
    worker = instrument_worker(source, {}, lambda name, _: visited.append(name),
                               stages=(("compute", "value = 4"),))
    assert worker() == 5
    assert visited == ["compute"]
    with pytest.raises(ValueError, match="matched 0"):
        instrument_worker(source, {}, lambda *_: None, stages=(("missing", "value = 3"),))


def test_timing_partition_and_durable_publication_observation():
    wall = iter([0.0, 1.0, 3.0, 4.0, 5.0])
    cpu = iter([0.0, 0.5, 1.5])
    timeline = Timeline(wall=lambda: next(wall), cpu=lambda: next(cpu))
    timeline.checkpoint("work")
    timeline.checkpoint("done")
    assert sum(row["wall_ms"] for row in timeline.stages) == 3000
    assert sum(row["cpu_ms"] for row in timeline.stages) == 1500
    job = ObservedJob(timeline, final_checks_pending=True)
    job["cards"] = [{"impression_id": "durable"}]
    assert job.first_actionable_ms is None
    job["final_checks_pending"] = False
    assert job.first_cards_ms == 4000
    assert job.first_actionable_ms == 5000


def test_isolation_refuses_preimported_database_and_existing_directory(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "backend.database", SimpleNamespace())
    with pytest.raises(RuntimeError, match="fresh Python process"):
        configure_isolation(tmp_path / "new")
    monkeypatch.delitem(sys.modules, "backend.database")
    monkeypatch.delitem(sys.modules, "backend.server", raising=False)
    with pytest.raises(FileExistsError):
        configure_isolation(tmp_path)
    with pytest.raises(RuntimeError, match="forbids network"):
        forbid_network("private address must never appear in the error")
