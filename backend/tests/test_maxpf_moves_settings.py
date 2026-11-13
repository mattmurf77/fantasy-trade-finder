"""Max PF moves: flag registration and settings (contract §8, scope §2).

- test_flag_registered_default_off_everywhere: `league.max_pf_moves` is in
  FLAG_KEYS, defaults False, is false in config/features.json (with its
  comment) and in the three flag fixtures. Sabotage: drop it from one fixture.
- test_settings_from_config: the committed values are the operator's
  (5,000 / 8 / 5 / 0.1 / 0.02 / 60).
- test_settings_reject_missing_unknown_and_out_of_range. Sabotage: accept 0
  simulations.
- test_batch_settings_and_view_ignore_the_new_key: batch.settings() still
  validates and the forecast view's served settings keys are unchanged.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend import feature_flags
from backend.league_projections import batch, maxpf_moves

REPO = Path(__file__).resolve().parents[2]
KEY = "league.max_pf_moves"


def test_flag_registered_code_default_off_shipped_on():
    """D-259 (operator, 2026-11-12): the flag ships ON. The code default stays
    off, so a missing or unreadable features.json still means off; the three
    flag fixtures mirror the shipped value."""
    assert KEY in feature_flags.FLAG_KEYS
    assert feature_flags.DEFAULT_FLAGS[KEY] is False
    features = json.loads((REPO / "config/features.json").read_text())
    assert features[KEY] is True and "_comment_league_max_pf_moves" in features
    for name in ("release", "onboarding-v2", "profiles-on"):
        fixture = json.loads((REPO / f"backend/tests/fixtures/flags/{name}.json").read_text())
        assert fixture[KEY] is True, name


def test_settings_from_config():
    assert maxpf_moves.settings() == {"simulations_per_candidate": 5000, "candidates": 8, "min_drop_points": 5,
                                      "min_pick_change": 0.1, "min_top3_change": 0.02, "time_budget_seconds": 60}


GOOD = {"simulations_per_candidate": 5000, "candidates": 8, "min_drop_points": 5,
        "min_pick_change": 0.1, "min_top3_change": 0.02, "time_budget_seconds": 60}


@pytest.mark.parametrize("change", [
    {"simulations_per_candidate": 0}, {"simulations_per_candidate": 5000.5}, {"candidates": 0},
    {"candidates": True}, {"min_drop_points": -1}, {"min_top3_change": 2}, {"time_budget_seconds": 0},
    {"min_pick_change": "0.1"}, {"extra": 1},
])
def test_settings_reject_missing_unknown_and_out_of_range(change):
    with pytest.raises(ValueError):
        maxpf_moves.parse_settings({**GOOD, **change})
    with pytest.raises(ValueError):
        maxpf_moves.parse_settings({k: v for k, v in GOOD.items() if k != "candidates"})
    with pytest.raises(ValueError):
        maxpf_moves.parse_settings(None)
    assert maxpf_moves.parse_settings(dict(GOOD)) == GOOD


def test_batch_settings_and_view_ignore_the_new_key(monkeypatch):
    values = batch.settings()
    assert "max_pf_moves" in values  # the file carries it; nothing in batch reads it
    monkeypatch.setattr(batch, "target", lambda u, l: None)
    view = batch.view("u1", "1")
    assert set(view) == {"state", "reason", "run", "attempt", "next_attempt_not_before", "schedule_timezone",
                         "cadence", "schedule", "retention_days", "scenario_defaults", "live_weeks_supported",
                         "schedule_note"}
    assert view["scenario_defaults"] == values["model"]
