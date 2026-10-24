"""The value core is count-bounded, never clock-bounded (G-065).

Same inputs -> same trades, same order and same diagnostics (bar elapsed_ms) whatever the
machine load. Load is simulated with a core clock that advances 1 s per read, which runs
far past the old 8 s budget, and then applied for real with busy threads. The safety
ceiling itself is tested in test_value_core_core.py (test_safety_ceiling_marks_pathology).
Scope: docs/plans/trade-time-to-suggestion/scope-eng-count-bounded.md.
"""
import dataclasses
import threading
from types import SimpleNamespace

import pytest

from backend.eval import value_core_bench as bench
from backend.value_core import core, pipeline
from backend.value_core.types import CoreConfig, RankConfig, Request

SEAT = "team00"
# 8 assets a side keeps a run fast (about 25k checks) while every partner still yields trades
# and most hit the per-partner keep cap, so caps and interleaving are exercised.
CFG = CoreConfig(max_assets_per_side=8)


@pytest.fixture(scope="module")
def league():
    """bench.synthetic_league: 12 teams, 11 partners, boards on two seats."""
    lg = bench.synthetic_league()["leagues"][0]
    snapshot, board = bench.snapshot_for_seat(lg, SEAT, standings_weight=bench.DEFAULT_STANDINGS_WEIGHT)
    return snapshot, Request(SEAT, board=board)


def _without_elapsed(diag):
    return dataclasses.replace(diag, elapsed_ms=0)


def test_same_deck_when_the_clock_runs_past_the_old_budget(league, monkeypatch):
    snapshot, request = league
    baseline, base_diag = core.find_fair_trades(snapshot, request, CFG)
    assert baseline and not base_diag.safety_ceiling_hit and not base_diag.budget_exhausted
    partners = sorted(t for t in snapshot.teams if t != SEAT)
    assert {t.partner_team_id for t in baseline} == set(partners)
    # Partner k's loop check (0-based) reads at least k + 1 simulated seconds after the start,
    # so the old 8 s budget would have cut every partner from the 9th on.
    assert len(partners) > 8

    now = [0.0]

    def perf_counter():            # every read costs 1 simulated second
        now[0] += 1.0
        return now[0]
    monkeypatch.setattr(core, "time", SimpleNamespace(perf_counter=perf_counter))
    loaded, loaded_diag = core.find_fair_trades(snapshot, request, CFG, safety_ceiling_s=1e9)

    assert loaded == baseline              # same trades, same order
    assert _without_elapsed(loaded_diag) == _without_elapsed(base_diag)
    assert loaded[-1].partner_team_id == partners[-1]


def test_same_deck_under_real_cpu_contention(league):
    snapshot, request = league
    baseline, base_diag = core.find_fair_trades(snapshot, request, CFG)
    stop = threading.Event()

    def spin():
        n = 0
        while not stop.is_set():
            n += 1
    threads = [threading.Thread(target=spin, daemon=True) for _ in range(2)]
    for t in threads:
        t.start()
    try:
        contended, contended_diag = core.find_fair_trades(snapshot, request, CFG)
    finally:
        stop.set()
        for t in threads:
            t.join()
    assert contended == baseline
    assert _without_elapsed(contended_diag) == _without_elapsed(base_diag)


def test_pipeline_passes_the_ceiling_through(league, monkeypatch):
    snapshot, request = league
    seen = []
    real = core.find_fair_trades

    def spy(*args, **kwargs):
        seen.append(kwargs.get("safety_ceiling_s"))
        return real(*args, **kwargs)
    monkeypatch.setattr(core, "find_fair_trades", spy)
    cfg = CoreConfig(max_assets_per_side=6)
    assert not pipeline.run(snapshot, request, cfg, RankConfig()).core.safety_ceiling_hit
    assert pipeline.run(snapshot, request, cfg, RankConfig(), safety_ceiling_s=0.0).core.safety_ceiling_hit
    assert seen == [core.SAFETY_CEILING_S, 0.0]
