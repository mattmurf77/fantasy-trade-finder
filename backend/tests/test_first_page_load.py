"""Load-test tool smoke test (docs/plans/realtime-trade-engine/scale.md).

Covers `backend/eval/first_page_load.run`: every scheduled arrival is completed
and reported once, for a burst and for a timed arrival window, on a tiny league
in one spawned worker process. No server, database or network. It pins the
report's shape, not any timing.
"""

import pytest

from backend.eval import first_page_load


def test_percentile_is_nearest_rank_and_safe_on_empty():
    assert first_page_load._percentile([], .5) is None
    assert first_page_load._percentile([1, 2, 3, 4], .5) == 3
    assert first_page_load._percentile([1, 2, 3, 4], 1.0) == 4


@pytest.mark.parametrize("load", [{"burst": 5}, {"rate": 20.0, "duration": .3}])
def test_every_arrival_is_completed_and_reported(load):
    report = first_page_load.run(processes=1, threads=2, leagues=2, teams=4, k=5, **load)
    assert report["arrivals"] >= 1
    assert report["throughput_per_s"] > 0
    assert set(report["latency_ms"]) == {"p50", "p95", "p99", "max"}
    assert report["latency_ms"]["p50"] <= report["latency_ms"]["max"]
    assert 0 <= report["share_within_200ms"] <= 1
    assert report["peak_rss_mb_per_process"] > 0
    assert report["burst"] == load.get("burst") and report["offered_per_s"] == load.get("rate")
