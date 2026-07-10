"""Tests for the FB4-61 consensus tile stats: consensus positional rank +
30-day trend.

Two layers under test:

  1. trends_service.compute_consensus_pos_ranks — pure rank/delta math over
     the universal-pool consensus seed vs. a dated baseline snapshot.
  2. database.load_value_snapshot_baseline — picks the OLDEST prior-day
     player_value_history snapshot within the trailing window, per format.

Conventions pinned here: rank is 1-based within position (ties break on
player_id), delta = previous_rank - current_rank so positive = moved UP
toward #1 (mirrors compute_risers_fallers / the You-side trend), and a
missing baseline yields NO delta (clients omit the glyph) rather than 0.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine

import backend.database as db_module
from backend.database import (
    load_value_snapshot_baseline,
    record_value_snapshots,
    metadata,
)
from backend.trends_service import compute_consensus_pos_ranks


# ---------------------------------------------------------------------------
# 1. Pure computation
# ---------------------------------------------------------------------------

PLAYERS = {
    "qb1": {"position": "QB"},
    "qb2": {"position": "QB"},
    "rb1": {"position": "RB"},
    "rb2": {"position": "RB"},
    "rb3": {"position": "RB"},
}


def test_pos_rank_is_per_position():
    seed = {"qb1": 1700, "qb2": 1600, "rb1": 1800, "rb2": 1500, "rb3": 1400}
    out = compute_consensus_pos_ranks(seed, {}, PLAYERS)
    # Each position group ranks independently from #1.
    assert out["pos_rank"] == {"qb1": 1, "qb2": 2, "rb1": 1, "rb2": 2, "rb3": 3}


def test_pos_rank_ties_break_on_player_id():
    seed = {"rb1": 1500, "rb2": 1500, "rb3": 1500}
    out = compute_consensus_pos_ranks(seed, {}, PLAYERS)
    assert out["pos_rank"] == {"rb1": 1, "rb2": 2, "rb3": 3}


def test_unknown_position_omitted():
    out = compute_consensus_pos_ranks({"x": 1500}, {}, {"x": {}})
    assert out["pos_rank"] == {}
    assert out["pos_rank_delta"] == {}


def test_empty_baseline_yields_ranks_but_no_deltas():
    seed = {"rb1": 1700, "rb2": 1600}
    out = compute_consensus_pos_ranks(seed, {}, PLAYERS)
    assert out["pos_rank"] == {"rb1": 1, "rb2": 2}
    assert out["pos_rank_delta"] == {}


def test_delta_sign_matches_rank_movement():
    # 30d ago: rb2 was the consensus RB1 (rb2 > rb1 > rb3).
    # Today:   rb1 overtook (rb1 > rb2 > rb3).
    current  = {"rb1": 1800.0, "rb2": 1700.0, "rb3": 1500.0}
    baseline = {"rb1": 1650.0, "rb2": 1750.0, "rb3": 1500.0}
    out = compute_consensus_pos_ranks(current, baseline, PLAYERS)
    assert out["pos_rank"] == {"rb1": 1, "rb2": 2, "rb3": 3}
    assert out["pos_rank_delta"]["rb1"] == 1    # #2 → #1, moved up
    assert out["pos_rank_delta"]["rb2"] == -1   # #1 → #2, dropped
    assert out["pos_rank_delta"]["rb3"] == 0    # held #3


def test_player_missing_from_baseline_gets_no_delta_but_keeps_ranking_complete():
    # rb3 (e.g. a rookie added after the baseline snapshot) has no history —
    # no delta for them, and their presence must not distort rb1/rb2's prior
    # ranks (they fall back to current elo in the reconstructed snapshot).
    current  = {"rb1": 1800.0, "rb2": 1700.0, "rb3": 1750.0}
    baseline = {"rb1": 1650.0, "rb2": 1750.0}
    out = compute_consensus_pos_ranks(current, baseline, PLAYERS)
    assert "rb3" not in out["pos_rank_delta"]
    assert out["pos_rank"]["rb3"] == 2          # ranked today regardless
    # Prev reconstructed: rb2=1750, rb3(fallback)=1750, rb1=1650 →
    # tie breaks on id → rb2 #1, rb3 #2, rb1 #3. Today rb1 is #1: +2.
    assert out["pos_rank_delta"]["rb1"] == 2
    assert out["pos_rank_delta"]["rb2"] == -2


# ---------------------------------------------------------------------------
# 2. Baseline snapshot accessor (isolated in-memory engine, same pattern as
#    test_db_hygiene)
# ---------------------------------------------------------------------------

@pytest.fixture()
def mem_engine():
    eng = create_engine("sqlite:///:memory:",
                        connect_args={"check_same_thread": False})
    metadata.create_all(eng)
    with patch.object(db_module, "engine", eng):
        yield eng


def _date(days_ago: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)
            ).strftime("%Y-%m-%d")


def _snap(pid: str, fmt: str, elo: float, days_ago: int) -> dict:
    return {
        "player_id":       pid,
        "scoring_format":  fmt,
        "consensus_elo":   elo,
        "consensus_value": None,
        "search_rank":     None,
        "adp":             None,
        "snapshot_date":   _date(days_ago),
    }


def test_baseline_picks_oldest_in_window(mem_engine):
    record_value_snapshots([
        _snap("rb1", "1qb_ppr", 1650.0, 29),   # oldest in window → baseline
        _snap("rb1", "1qb_ppr", 1700.0, 10),
        _snap("rb1", "1qb_ppr", 1800.0, 0),
    ])
    baseline = load_value_snapshot_baseline("1qb_ppr", days=30)
    assert baseline == {"rb1": 1650.0}


def test_baseline_excludes_snapshots_outside_window(mem_engine):
    record_value_snapshots([
        _snap("rb1", "1qb_ppr", 1400.0, 45),   # too old — outside 30d window
        _snap("rb1", "1qb_ppr", 1650.0, 20),
    ])
    baseline = load_value_snapshot_baseline("1qb_ppr", days=30)
    assert baseline == {"rb1": 1650.0}


def test_single_same_day_snapshot_yields_no_baseline(mem_engine):
    # Day one of capture: only today's snapshot exists. A same-day snapshot
    # is no trend baseline → {} → delta null → clients omit the glyph.
    record_value_snapshots([_snap("rb1", "1qb_ppr", 1800.0, 0)])
    assert load_value_snapshot_baseline("1qb_ppr", days=30) == {}


def test_no_snapshots_at_all_yields_empty(mem_engine):
    assert load_value_snapshot_baseline("1qb_ppr", days=30) == {}


def test_baseline_is_scoped_per_format(mem_engine):
    record_value_snapshots([
        _snap("rb1", "1qb_ppr", 1650.0, 25),
        _snap("rb1", "sf_tep",  1720.0, 25),
    ])
    assert load_value_snapshot_baseline("1qb_ppr", days=30) == {"rb1": 1650.0}
    assert load_value_snapshot_baseline("sf_tep",  days=30) == {"rb1": 1720.0}


# ---------------------------------------------------------------------------
# 3. End-to-end delta math: two snapshots 30d apart → correct signed delta;
#    single (same-day) snapshot → no delta.
# ---------------------------------------------------------------------------

def test_two_snapshots_thirty_days_apart_produce_signed_delta(mem_engine):
    fmt = "1qb_ppr"
    record_value_snapshots([
        # 30 days ago: rb2 was RB1.
        _snap("rb1", fmt, 1650.0, 30),
        _snap("rb2", fmt, 1750.0, 30),
        # Today's snapshot (ignored as baseline — same-day).
        _snap("rb1", fmt, 1800.0, 0),
        _snap("rb2", fmt, 1700.0, 0),
    ])
    current = {"rb1": 1800.0, "rb2": 1700.0}
    baseline = load_value_snapshot_baseline(fmt, days=30)
    out = compute_consensus_pos_ranks(current, baseline, PLAYERS)
    assert out["pos_rank"] == {"rb1": 1, "rb2": 2}
    assert out["pos_rank_delta"] == {"rb1": 1, "rb2": -1}


def test_single_snapshot_end_to_end_gives_null_delta(mem_engine):
    fmt = "1qb_ppr"
    record_value_snapshots([
        _snap("rb1", fmt, 1800.0, 0),
        _snap("rb2", fmt, 1700.0, 0),
    ])
    current = {"rb1": 1800.0, "rb2": 1700.0}
    baseline = load_value_snapshot_baseline(fmt, days=30)
    out = compute_consensus_pos_ranks(current, baseline, PLAYERS)
    assert out["pos_rank"] == {"rb1": 1, "rb2": 2}   # rank still served
    assert out["pos_rank_delta"] == {}               # trend omitted
