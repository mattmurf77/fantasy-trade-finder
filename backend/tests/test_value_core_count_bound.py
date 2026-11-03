"""The value core is count-bounded, never clock-bounded (G-065).

Same inputs -> same trades, same order and same diagnostics (bar elapsed_ms) whatever the
machine load. The CI gate SIMULATES contention: the core's `time.perf_counter` is stubbed to
advance quickly, never real parallel load (models-lead R3.2 condition 5). Real busy threads
are a local stress check only (FTF_STRESS=1). The ceiling's own mechanics are tested in
test_value_core_core.py (test_safety_ceiling_marks_pathology).
Scope: docs/plans/trade-time-to-suggestion/scope-eng-count-bounded.md.
"""
import dataclasses
import os
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


def _stub_clock(monkeypatch, step_s):
    """Simulated contention: every read of the core's clock costs `step_s` seconds."""
    now = [0.0]

    def perf_counter():
        now[0] += step_s
        return now[0]
    monkeypatch.setattr(core, "time", SimpleNamespace(perf_counter=perf_counter))


def test_same_deck_when_the_clock_runs_past_the_old_budget(league, monkeypatch):
    snapshot, request = league
    baseline, base_diag = core.find_fair_trades(snapshot, request, CFG)
    assert baseline and not base_diag.safety_ceiling_hit and not base_diag.budget_exhausted
    partners = sorted(t for t in snapshot.teams if t != SEAT)
    assert {t.partner_team_id for t in baseline} == set(partners)
    # Partner k's loop check (0-based) reads at least k + 1 simulated seconds after the start,
    # so the old 8 s budget would have cut every partner from the 9th on.
    assert len(partners) > 8

    _stub_clock(monkeypatch, 1.0)
    loaded, loaded_diag = core.find_fair_trades(snapshot, request, CFG, safety_ceiling_s=1e9)

    assert set(loaded) == set(baseline)    # same pool
    assert loaded == baseline              # same order
    assert _without_elapsed(loaded_diag) == _without_elapsed(base_diag)
    assert loaded[-1].partner_team_id == partners[-1]


# step 1.0: about 29 simulated s, past the old 8 s budget and under the 30 s ceiling.
# step >= 2.0: the default ceiling fires partway through the partners.
@pytest.mark.parametrize("step_s, ceiling_fires", [(0.0, False), (0.5, False), (1.0, False),
                                                   (2.0, True), (5.0, True), (31.0, True)])
def test_safety_ceiling_is_the_only_clock_driven_stop(league, monkeypatch, step_s, ceiling_fires):
    """With the default ceiling and a stubbed fast clock, a run either is the full unpressured
    deck or was stopped by the safety ceiling. budget_exhausted never appears without
    safety_ceiling_hit: no other clock-driven partial stop exists."""
    snapshot, request = league
    baseline, base_diag = core.find_fair_trades(snapshot, request, CFG)
    _stub_clock(monkeypatch, step_s)
    trades, diag = core.find_fair_trades(snapshot, request, CFG)

    assert diag.safety_ceiling_hit is ceiling_fires
    assert diag.budget_exhausted is diag.safety_ceiling_hit   # budget_exhausted <=> the ceiling
    if not ceiling_fires:
        assert trades == baseline and _without_elapsed(diag) == _without_elapsed(base_diag)
    else:
        assert len(trades) < len(baseline)


@pytest.mark.skipif(os.environ.get("FTF_STRESS") != "1",
                    reason="local stress check, not a CI gate: real parallel load is flaky by "
                           "construction (models-lead R3.2 condition 5). Set FTF_STRESS=1 to run.")
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
