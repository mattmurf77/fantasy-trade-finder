"""League-summary total team count (TestFlight feedback #41).

The League hero tile must show the league's TOTAL team count, caller
included. Deriving it client-side as leaguemates_total + 1 regressed in the
wild because league_members is a per-login snapshot of OWNED rosters:

  - ownerless rosters (a manager left the league) are filtered out of
    opponent_rosters by the clients, so a 12-team league with one orphan
    roster stored 11 members and the tile showed 11 (prod league
    "Fantasy Football Version 3");
  - members who leave the league are never pruned, so a 12-team league
    could also show 13 (prod league "La Resistance").

The fix: session_init persists Sleeper's total_rosters onto the leagues row
(set_league_total_rosters) and get_league_summary returns it as
`total_teams`, falling back to leaguemates_total + 1 for local leagues and
rows that pre-date the column.

Runs against an isolated in-memory SQLite engine patched into
backend.database (same pattern as test_league_summary_buckets.py).
"""

import json
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, select

import backend.database as db_module
from backend.database import (
    get_league_summary,
    league_members_table,
    leagues_table,
    metadata,
    set_league_total_rosters,
)

LEAGUE = "league_total_teams"
CALLER = "user_caller"


@pytest.fixture()
def mem_engine():
    eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    metadata.create_all(eng)
    with patch.object(db_module, "engine", eng):
        yield eng


def _insert_league(eng, total_rosters=None):
    with eng.begin() as conn:
        conn.execute(leagues_table.insert().values(
            sleeper_league_id=LEAGUE,
            user_id=CALLER,
            name="Total Teams League",
            total_rosters=total_rosters,
        ))


def _insert_members(eng, n_opponents, include_caller=True):
    rows = []
    if include_caller:
        rows.append({"league_id": LEAGUE, "user_id": CALLER,
                     "username": "caller", "roster_data": json.dumps([])})
    rows += [
        {"league_id": LEAGUE, "user_id": f"opp_{i}",
         "username": f"opp_{i}", "roster_data": json.dumps([])}
        for i in range(n_opponents)
    ]
    with eng.begin() as conn:
        conn.execute(league_members_table.insert(), rows)


def test_total_teams_uses_stored_total_rosters(mem_engine):
    """12-team league with one ownerless roster: only 11 members ever reach
    league_members (caller + 10 opponents), but the tile must say 12."""
    _insert_league(mem_engine, total_rosters=12)
    _insert_members(mem_engine, n_opponents=10)

    summary = get_league_summary(LEAGUE, CALLER)
    assert summary["total_teams"] == 12          # NOT 11
    assert summary["leaguemates_total"] == 10    # unchanged: joined-chip source


def test_total_teams_falls_back_to_members_plus_caller(mem_engine):
    """No stored total_rosters (local league / pre-migration row): fall back
    to leaguemates_total + 1, i.e. the caller is always counted."""
    _insert_league(mem_engine, total_rosters=None)
    _insert_members(mem_engine, n_opponents=11)

    summary = get_league_summary(LEAGUE, CALLER)
    assert summary["total_teams"] == 12


def test_total_teams_present_on_empty_league_early_return(mem_engine):
    """The leaguemates_total == 0 early-return path must still carry the
    stored count so a fresh solo import shows the real league size."""
    _insert_league(mem_engine, total_rosters=12)
    _insert_members(mem_engine, n_opponents=0)   # caller only

    summary = get_league_summary(LEAGUE, CALLER)
    assert summary["leaguemates_total"] == 0
    assert summary["total_teams"] == 12


def test_set_league_total_rosters_writes_and_validates(mem_engine):
    _insert_league(mem_engine)

    def stored():
        with mem_engine.connect() as conn:
            return conn.execute(
                select(leagues_table.c.total_rosters)
                .where(leagues_table.c.sleeper_league_id == LEAGUE)
            ).scalar()

    set_league_total_rosters(LEAGUE, 12)
    assert stored() == 12

    # Garbage from a flaky Sleeper payload must never clobber a good value.
    set_league_total_rosters(LEAGUE, 0)
    set_league_total_rosters(LEAGUE, -3)
    set_league_total_rosters(LEAGUE, None)  # type: ignore[arg-type]
    assert stored() == 12
