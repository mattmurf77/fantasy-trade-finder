"""Free-agent finder logic (feedback #143) — backend/free_agent_service.py.

Pins the four rules the route relies on:

  1. FA exclusion — a player rostered by ANY league member (caller included)
     never appears; PICK pseudo-players never appear.
  2. Personal-value ranking — order follows the caller's board where they
     have an Elo, consensus seed for everyone else (fallback, never dropped).
  3. Drop suggestion — only the caller's LOWEST-valued same-position
     rostered player, and only when strictly below the FA's value; the
     delta is fa_value - drop_value.
  4. Position filter — filters rows without renumbering pos_rank (an FA is
     "RB3" under every filter).

Pure-function tests: no Flask, no DB (the route is a thin wrapper whose
gate/session plumbing is covered by test_verified_reads.py).
"""

import pytest

from backend.free_agent_service import (
    DEFAULT_LIMIT,
    board_is_personalized,
    board_value,
    compute_free_agents,
)
from backend.ranking_service import Player
from backend.trade_service import elo_to_value


def _p(pid, position, name=None, team="FA"):
    return Player(id=pid, name=name or pid, position=position, team=team, age=25)


# Consensus board: qb1 > qb2 > rb1 > rb2 > rb3 > wr1 > te1, picks excluded.
POOL = [
    _p("qb1", "QB"), _p("qb2", "QB"),
    _p("rb1", "RB"), _p("rb2", "RB"), _p("rb3", "RB"),
    _p("wr1", "WR"),
    _p("te1", "TE"),
    _p("pick1", "PICK", name="2027 Mid 1st"),
]
SEED = {
    "qb1": 1900.0, "qb2": 1800.0,
    "rb1": 1750.0, "rb2": 1700.0, "rb3": 1600.0,
    "wr1": 1550.0,
    "te1": 1500.0,
    "pick1": 1650.0,
}


def _ids(rows):
    return [r["player_id"] for r in rows]


def _row(rows, pid):
    return next(r for r in rows if r["player_id"] == pid)


# ── 1. FA exclusion ──────────────────────────────────────────────────────

def test_rostered_players_never_appear():
    """Every roster in the league — leaguemates' AND the caller's — is
    excluded from the FA pool."""
    rows = compute_free_agents(
        pool_players=POOL, seed_elo=SEED, user_elo={},
        rostered_ids={"qb1", "rb1"},          # leaguemates' rosters
        user_roster=["rb2"],                  # caller's roster
    )
    assert set(_ids(rows)) == {"qb2", "rb3", "wr1", "te1"}


def test_pick_pseudo_players_are_not_free_agents():
    rows = compute_free_agents(
        pool_players=POOL, seed_elo=SEED, user_elo={},
        rostered_ids=set(), user_roster=[],
    )
    assert "pick1" not in _ids(rows)


def test_empty_league_surfaces_whole_pool():
    """No rosters at all (e.g. league_members not yet synced) → every
    non-PICK pool player is a free agent."""
    rows = compute_free_agents(
        pool_players=POOL, seed_elo=SEED, user_elo={},
        rostered_ids=set(), user_roster=[],
    )
    assert len(rows) == len(POOL) - 1  # pick1 excluded


# ── 2. Personal-value ranking with consensus fallback ────────────────────

def test_ranked_by_callers_board_not_consensus():
    """The caller loves rb3 (Elo 1950 > everyone) → rb3 tops their FA list
    even though consensus has him 5th."""
    rows = compute_free_agents(
        pool_players=POOL, seed_elo=SEED, user_elo={"rb3": 1950.0},
        rostered_ids=set(), user_roster=[],
    )
    assert _ids(rows)[0] == "rb3"
    assert _row(rows, "rb3")["value"] == round(elo_to_value(1950.0), 1)


def test_unranked_players_fall_back_to_consensus_not_dropped():
    """Players absent from the caller's board are priced at consensus seed
    and still listed — the fallback is per-player, not all-or-nothing."""
    rows = compute_free_agents(
        pool_players=POOL, seed_elo=SEED, user_elo={"rb3": 1950.0},
        rostered_ids=set(), user_roster=[],
    )
    # qb1 has no personal Elo → consensus seed value, still 2nd overall.
    assert _row(rows, "qb1")["value"] == round(elo_to_value(1900.0), 1)
    assert _ids(rows)[1] == "qb1"


def test_board_value_defaults_to_1500_when_absent_everywhere():
    assert board_value("ghost", {}, {}) == round(elo_to_value(1500.0), 1)


def test_pos_rank_is_within_position_over_the_fa_pool():
    rows = compute_free_agents(
        pool_players=POOL, seed_elo=SEED, user_elo={},
        rostered_ids={"rb1"}, user_roster=[],
    )
    # rb1 rostered → rb2 is the best available RB.
    assert _row(rows, "rb2")["pos_rank"] == 1
    assert _row(rows, "rb3")["pos_rank"] == 2
    assert _row(rows, "qb2")["pos_rank"] == 2  # behind qb1


# ── 3. Drop-suggestion rule ──────────────────────────────────────────────

def test_drop_suggests_lowest_valued_same_position_player_below_fa():
    """Caller rosters rb1 (high) + rb3 (low); FA rb2 sits between them →
    suggest dropping rb3 (the LOWEST same-position player below the FA),
    never rb1."""
    rows = compute_free_agents(
        pool_players=POOL, seed_elo=SEED, user_elo={},
        rostered_ids=set(), user_roster=["rb1", "rb3"],
    )
    drop = _row(rows, "rb2")["drop_suggestion"]
    assert drop is not None
    assert drop["player_id"] == "rb3"
    fa_v, drop_v = _row(rows, "rb2")["value"], drop["value"]
    assert drop["delta"] == round(fa_v - drop_v, 1)
    assert drop["delta"] > 0


def test_no_drop_when_every_same_position_player_is_better():
    """Caller's only QB (qb1) outvalues FA qb2 → no suggestion (dropping a
    better player for a worse one is never suggested)."""
    rows = compute_free_agents(
        pool_players=POOL, seed_elo=SEED, user_elo={},
        rostered_ids=set(), user_roster=["qb1"],
    )
    assert _row(rows, "qb2")["drop_suggestion"] is None


def test_no_cross_position_drop_suggestions():
    """Caller rosters only a weak TE; a strong FA RB still gets NO
    suggestion — drops are same-position only."""
    rows = compute_free_agents(
        pool_players=POOL, seed_elo=SEED, user_elo={},
        rostered_ids=set(), user_roster=["te1"],
    )
    assert _row(rows, "rb1")["drop_suggestion"] is None


def test_drop_rule_uses_the_callers_board_values():
    """Caller tanks rb1 on their board (Elo 1400 < FA rb2's 1700) → their
    'best' consensus RB becomes the drop suggestion under THEIR values."""
    rows = compute_free_agents(
        pool_players=POOL, seed_elo=SEED, user_elo={"rb1": 1400.0},
        rostered_ids=set(), user_roster=["rb1"],
    )
    drop = _row(rows, "rb2")["drop_suggestion"]
    assert drop is not None and drop["player_id"] == "rb1"
    assert drop["value"] == round(elo_to_value(1400.0), 1)


def test_equal_value_is_not_below():
    """Strictly-below rule: a same-position rostered player exactly equal in
    value to the FA yields no suggestion."""
    # RB/RB tie: roster rb2, lift FA rb3 to the same Elo on the caller's board.
    rows = compute_free_agents(
        pool_players=POOL, seed_elo=SEED, user_elo={"rb3": SEED["rb2"]},
        rostered_ids=set(), user_roster=["rb2"],
    )
    assert _row(rows, "rb3")["drop_suggestion"] is None


def test_unpriceable_roster_entries_are_skipped():
    """A rostered id outside the universal pool (no value on any board)
    can't be a drop candidate — the pool RB is used instead."""
    rows = compute_free_agents(
        pool_players=POOL, seed_elo=SEED, user_elo={},
        rostered_ids=set(), user_roster=["rb3", "offpool_guy"],
    )
    drop = _row(rows, "rb2")["drop_suggestion"]
    assert drop is not None and drop["player_id"] == "rb3"


# ── 4. Position filter + limit ───────────────────────────────────────────

def test_position_filter_returns_only_that_position():
    rows = compute_free_agents(
        pool_players=POOL, seed_elo=SEED, user_elo={},
        rostered_ids=set(), user_roster=[], position="RB",
    )
    assert _ids(rows) == ["rb1", "rb2", "rb3"]


def test_position_filter_keeps_global_pos_rank():
    """pos_rank is computed over the whole FA pool, so filtering doesn't
    renumber anyone."""
    all_rows = compute_free_agents(
        pool_players=POOL, seed_elo=SEED, user_elo={},
        rostered_ids={"rb1"}, user_roster=[],
    )
    rb_rows = compute_free_agents(
        pool_players=POOL, seed_elo=SEED, user_elo={},
        rostered_ids={"rb1"}, user_roster=[], position="RB",
    )
    assert {r["player_id"]: r["pos_rank"] for r in rb_rows} == {
        r["player_id"]: r["pos_rank"] for r in all_rows if r["position"] == "RB"
    }


def test_limit_applies_after_position_filter():
    rows = compute_free_agents(
        pool_players=POOL, seed_elo=SEED, user_elo={},
        rostered_ids=set(), user_roster=[], position="RB", limit=2,
    )
    assert _ids(rows) == ["rb1", "rb2"]
    assert DEFAULT_LIMIT == 50


# ── board_is_personalized (unranked empty-state signal) ──────────────────

def test_board_is_personalized_false_for_pure_consensus():
    assert board_is_personalized(dict(SEED), SEED) is False
    assert board_is_personalized({}, SEED) is False


def test_board_is_personalized_true_after_any_divergence():
    diverged = dict(SEED)
    diverged["rb3"] = 1601.0
    assert board_is_personalized(diverged, SEED) is True
