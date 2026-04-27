"""Unit tests for league-size-aware compute_pick_value()."""
from backend.database import compute_pick_value


def test_baseline_12_team_unchanged():
    # 12-team R1 in current season → 67.5 (the documented baseline)
    assert compute_pick_value(1, 2026, 2026, league_size=12) == 67.5


def test_8_team_scales_down():
    # 8/12 = 0.667 → 67.5 * 0.667 = 45.0
    assert compute_pick_value(1, 2026, 2026, league_size=8) == 45.0


def test_14_team_scales_up():
    # 14/12 = 1.167 → 67.5 * 1.167 = ~78.75
    val = compute_pick_value(1, 2026, 2026, league_size=14)
    assert 78.0 < val < 79.0


def test_clamped_low():
    # 4-team would be 0.333 but is clamped to 0.5 → 33.75
    assert compute_pick_value(1, 2026, 2026, league_size=4) == 33.75


def test_clamped_high():
    # 24-team would be 2.0 but is clamped to 1.5 → 101.25
    assert compute_pick_value(1, 2026, 2026, league_size=24) == 101.25


def test_year_discount_still_applies():
    # 12-team R1 next season: 67.5 * 0.85 = 57.38
    assert compute_pick_value(1, 2027, 2026, league_size=12) == 57.38


def test_default_kwarg_is_12():
    # Existing callers without league_size keep current behavior
    assert compute_pick_value(1, 2026, 2026) == compute_pick_value(1, 2026, 2026, league_size=12)
