"""Value-core end-to-end tests with the REAL engine (specs.md section 5.4, WP4).

INTEGRATION-ONLY: these fail until WP1 (core), WP2 (windows/ranking/deck) and
WP3 (pipeline/adapter/server branch) have all merged, and are excluded from
WP4's isolated run. Nothing here touches the network or production.
"""
import json
import time
from unittest.mock import patch

import pytest

from backend.eval import value_core_bench
from backend.value_core.types import CoreConfig, Request


def _strip_timing(value):
    """Wall-clock fields are the only legitimately non-deterministic outputs."""
    if isinstance(value, dict):
        return {k: _strip_timing(v) for k, v in value.items() if k != "elapsed_ms"}
    if isinstance(value, list):
        return [_strip_timing(v) for v in value]
    return value


def test_pipeline_on_synthetic_league():
    frozen = value_core_bench.synthetic_league(7)
    started = time.monotonic()
    first = value_core_bench.run(frozen, variants={"default": {}})
    second = value_core_bench.run(frozen, variants={"default": {}})
    elapsed = time.monotonic() - started

    assert _strip_timing(first) == _strip_timing(second)
    seats = first["variants"]["default"]["seats"]
    assert len(seats) == 12
    varied = [s for s in seats if s["pool"] >= 90]
    assert varied, "the synthetic league should give some seat a fair pool of >= 90 cards"
    for seat in varied:
        assert seat["max_asset_appearances"] <= 3, seat["team"]
    assert elapsed < 20.0


def test_run_trade_job_flag_on_real_engine():
    import backend.server as server
    import backend.trade_service as trade_service_mod
    from backend.tests.support import bakeoff_harness as H

    patches = [
        patch.object(server, "_value_core_enabled", lambda: True),
        patch.dict(trade_service_mod._cfg, {"vc_testers_only": 0.0}),
        patch.object(server, "_league_lineup_slots", lambda *a, **k: ["QB"]),
        patch.object(server, "_sleeper_roster_limit", lambda *a, **k: None),
        patch.object(server, "_value_core_standings", lambda *a, **k: ({}, 0)),
    ]
    capture, job, _engine = H.run_capture(extra_patches=patches)

    assert capture["status"] == "complete", capture["error"]
    cards = job["cards"]
    assert len(cards) >= 1
    assert all(card["trade_id"].startswith("vc_") for card in cards)
    shapes = {(tuple(sorted(a["id"] for a in card["give"])),
               tuple(sorted(a["id"] for a in card["receive"]))) for card in cards}
    assert (("rb1",), ("rb3", "wr3")) in shapes          # the harness's fair 1-for-2
    rows = capture["impressions"]
    assert rows
    for row in rows:
        assert row["model_arm"] == "value_core"
        evidence = json.loads(row["valuation_json"])
        assert "scores" in evidence and "weights" in evidence


def test_evaluate_trade_matches_pool_on_synthetic():
    from backend.value_core import core

    league = value_core_bench.synthetic_league(7)["leagues"][0]
    seat = league["teams"][0]["team_id"]
    snapshot, board = value_core_bench.snapshot_for_seat(
        league, seat, standings_weight=value_core_bench.DEFAULT_STANDINGS_WEIGHT)
    request = Request(viewer_team_id=seat, board=board)
    cfg = CoreConfig()
    trades, _diag = core.find_fair_trades(snapshot, request, cfg)
    assert len(trades) >= 50
    step = len(trades) // 50
    for trade in trades[::step][:50]:
        verdict = core.evaluate_trade(snapshot, request, cfg, partner_team_id=trade.partner_team_id,
                                      give=trade.give, receive=trade.receive)
        assert verdict.ok, (trade.key, verdict.reason)
        assert verdict.trade.adjusted_ratio == pytest.approx(trade.adjusted_ratio, rel=1e-12)
