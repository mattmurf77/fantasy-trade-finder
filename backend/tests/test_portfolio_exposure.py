"""FB-48 — portfolio exposure must scope to the caller's league list.

Sleeper mints a NEW league_id every season, so league_members accumulates
last season's instance of each league alongside the current one. Unscoped,
every carried-over player counts twice ("players and leagues are being
double counted" — feedback id 48). Clients now pass their current-season
league list via ?league_ids=; this covers the database-layer filter.
"""
import json
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, insert

import backend.database as db_module
from backend.database import (
    load_user_cross_league_exposure,
    league_members_table,
    leagues_table,
    metadata,
)

USER = "u1"
OLD_LEAGUE = "111"   # last season's instance of "Lakeview"
NEW_LEAGUE = "222"   # current season's instance of "Lakeview"


@pytest.fixture()
def mem_engine():
    eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    metadata.create_all(eng)
    with eng.begin() as conn:
        for lid in (OLD_LEAGUE, NEW_LEAGUE):
            conn.execute(insert(leagues_table).values(
                sleeper_league_id=lid, user_id=USER, name="Lakeview", season="2026",
            ))
            conn.execute(insert(league_members_table).values(
                league_id=lid, user_id=USER, username="me",
                roster_data=json.dumps(["p1", "p2"]),   # carried-over roster
            ))
    with patch.object(db_module, "engine", eng):
        yield eng


def test_unscoped_double_counts_carried_over_players(mem_engine):
    rows = load_user_cross_league_exposure(USER)
    by_pid = {r["player_id"]: r for r in rows}
    # Documents the legacy behavior the filter exists to avoid.
    assert by_pid["p1"]["exposure"] == 2
    assert by_pid["p1"]["total_leagues"] == 2


def test_league_ids_filter_scopes_to_current_season(mem_engine):
    rows = load_user_cross_league_exposure(USER, league_ids=[NEW_LEAGUE])
    by_pid = {r["player_id"]: r for r in rows}
    assert by_pid["p1"]["exposure"] == 1
    assert by_pid["p1"]["total_leagues"] == 1
    assert by_pid["p1"]["leagues"] == [
        {"league_id": NEW_LEAGUE, "league_name": "Lakeview"}
    ]


def test_filter_with_no_matching_leagues_returns_empty(mem_engine):
    assert load_user_cross_league_exposure(USER, league_ids=["zzz"]) == []
