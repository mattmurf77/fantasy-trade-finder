"""Sleeper trade universe crawler: the pilot report's numbers on a known world (research-plan §8.2).

Covers: trades per league-season, kept and skipped counts by reason,
requests per league-season (44), reconstruction match rates, trades by
method and forward/backward agreement, trade dates by leg, picks resolved,
lineage depth, transaction counts by type (an unknown type is visible), the
standings check, unplayed-week pairings, and the report command exit code /
leak-scan line. The expected values are counted from the simulator.
"""
from __future__ import annotations

from backend.sleeper_universe.report import build_report
from backend.tests.support.sleeper_universe_world import connect, run_cli, standard_world


def test_report_numbers_on_known_world(tmp_path):
    w = standard_world()
    assert run_cli(w, tmp_path, "run")[0] == 0
    rep = build_report(connect(tmp_path))
    per_ls = sorted(len(v) for v in w.truth_trades.values())
    assert per_ls == [1, 2, 2, 3, 4]
    assert rep["trades_total"] == 12 and rep["league_seasons_pulled"] == 5
    assert rep["trades_per_league_season"]["median"] == 2
    assert rep["trades_per_league_season"]["max"] == 4
    assert rep["leagues_kept"] == 5 and rep["lineages_kept"] == 3
    assert rep["leagues_skipped_by_reason"] == {"best_ball": 1, "not_dynasty": 2,
                                                "not_started": 1, "team_count": 1}
    assert rep["requests_per_league_season"]["min"] == rep["requests_per_league_season"]["max"] == 44
    assert rep["reconstruction_match"]["in_season"]["rate"] == 1.0
    assert rep["league_seasons_below_target"] == 0
    assert rep["trades_by_recon_method"] == {"forward": 3, "in_season": 9}
    assert rep["forward_backward_agreement"] == {"compared": 3, "agree": 3, "rate": 1.0}
    assert rep["trade_dates_by_leg"]["1"] == {"2025-07": 1, "2025-08": 1, "2026-07": 1}
    assert sum(sum(v.values()) for v in rep["trade_dates_by_leg"].values()) == 12
    assert rep["traded_picks"]["total"] == 6 and rep["traded_picks"]["drafted"] == 3
    assert rep["traded_picks"]["share_resolved_to_slot"] == 0.5
    assert rep["lineage_depth_seasons"] == {"1": 2, "3": 1}
    assert "other" in rep["transaction_types_seen"]   # an unknown type, visible as other
    assert rep["transactions_by_type_status"]["waiver/failed"] > 0
    assert rep["standings_vs_reported"]["league_seasons"] == 5
    assert rep["standings_vs_reported"]["agree"] == 3
    assert rep["standings_vs_reported"]["records_agree"] == 4
    assert rep["standings_vs_reported"]["points_agree"] == 4
    assert rep["standings_vs_reported"]["disagreement_kinds_rosters"] == {"points_for": 1, "wins": 1}
    assert rep["leg_time_inversions"] == 0
    assert rep["unplayed_weeks"]["without_pairing"] > 0
    assert rep["last_pull_leak_scan_ok"] is True


def test_report_command_prints_aggregates_and_leak_line(tmp_path):
    w = standard_world()
    assert run_cli(w, tmp_path, "run")[0] == 0
    code, lines = run_cli(w, tmp_path, "report", seeds=None)
    text = "\n".join(lines)
    assert code == 0 and "leak_scan: PASS" in text
    for uid in w.all_user_ids():
        assert uid not in text
