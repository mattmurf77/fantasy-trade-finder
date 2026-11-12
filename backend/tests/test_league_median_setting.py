"""`leagues.median_game` — the Sleeper league-median setting stored on link and sync.

Scope: docs/plans/league-projections/median-leagues-scope.md (Part B).

What this pins:
  * `_migrate_db` adds the column to a database created without it, and the
    migration entry exists (SQLite create_all alone would hide a missing one);
  * `league_median_setting` reads `settings.league_average_match` as 1 / 0
    and returns None, never 0, when the payload or key is missing or odd;
  * `upsert_league` writes it on first link, refreshes it on later syncs
    (both the upsert and the update-only path), fills a NULL row on the next
    sync, and never clobbers a known value with an unknown one;
  * session init stores it from the league payload it already fetched (no
    extra Sleeper call), on the first link and on a re-sync; a platform
    (MFL) league keeps NULL.
"""
import inspect
import re

import pytest
from sqlalchemy import create_engine, inspect as sa_inspect, select, text
from unittest.mock import patch

import backend.database as db
from backend.database import leagues_table, league_median_setting, upsert_league
from backend.tests.test_session_init_sleeper_calls import (  # noqa: F401
    LEAGUE_ID, LEAGUE_META, NUMERIC_MFL_LEAGUE, _init, harness)

pytestmark = pytest.mark.usefixtures("no_real_network")

LEAGUE = "987654321012345679"


@pytest.fixture()
def mem_engine():
    eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    db.metadata.create_all(eng)
    with patch.object(db, "engine", eng), patch.object(db, "DATABASE_URL", "sqlite://"):
        yield eng


def _median(eng, league_id=LEAGUE):
    with eng.connect() as conn:
        return conn.execute(select(leagues_table.c.median_game)
                            .where(leagues_table.c.sleeper_league_id == league_id)).scalar_one()


# ── Schema ──────────────────────────────────────────────────────────────────

def test_migrate_db_adds_the_column_to_an_existing_database(tmp_path, monkeypatch):
    eng = create_engine(f"sqlite:///{tmp_path / 'old.db'}", connect_args={"check_same_thread": False})
    db.metadata.create_all(eng)
    with eng.begin() as conn:
        conn.execute(text("ALTER TABLE leagues DROP COLUMN median_game"))
    assert "median_game" not in {c["name"] for c in sa_inspect(eng).get_columns("leagues")}
    monkeypatch.setattr(db, "engine", eng)
    monkeypatch.setattr(db, "DATABASE_URL", f"sqlite:///{tmp_path / 'old.db'}")
    db._migrate_db()
    assert "median_game" in {c["name"] for c in sa_inspect(eng).get_columns("leagues")}
    src = inspect.getsource(db._migrate_db)
    entries = re.findall(r'\(\s*"([^"]+)",\s*"([^"]+)",\s*"([^"]+)"\s*\)', src)
    assert ("leagues", "median_game", "INTEGER") in entries


# ── Reading the platform payload ───────────────────────────────────────────

@pytest.mark.parametrize("meta,expected", [
    ({"settings": {"league_average_match": 1}}, 1),
    ({"settings": {"league_average_match": 0}}, 0),
    ({"settings": {}}, None),                       # missing key: unknown, not 0
    ({"settings": {"league_average_match": None}}, None),
    ({"settings": {"league_average_match": 2}}, None),
    ({"settings": {"league_average_match": "1"}}, None),
    ({"settings": {"league_average_match": True}}, None),
    ({}, None), (None, None), ({"settings": None}, None),
])
def test_league_median_setting_never_guesses(meta, expected):
    """Sabotage: coerce a missing setting to 0."""
    assert league_median_setting(meta) == expected


# ── upsert_league ───────────────────────────────────────────────────────────

def test_first_link_stores_the_setting_and_a_resync_refreshes_it(mem_engine):
    """Sabotage: only write the column on insert."""
    upsert_league(LEAGUE, "user_a", "L", "2026", [], [], platform="sleeper", median_game=1)
    assert _median(mem_engine) == 1
    upsert_league(LEAGUE, "user_b", "L", "2026", [], [], platform="sleeper", median_game=0)
    assert _median(mem_engine) == 0
    # The daemon's update-only path (row existed at its start) refreshes too.
    upsert_league(LEAGUE, "user_a", "L", "2026", [], [], platform="sleeper", only_if_exists=True, median_game=1)
    assert _median(mem_engine) == 1


def test_a_null_row_is_filled_on_the_next_sync_and_unknown_never_clobbers(mem_engine):
    upsert_league(LEAGUE, "user_a", "L", "2026", [], [])
    assert _median(mem_engine) is None
    upsert_league(LEAGUE, "user_a", "L", "2026", [], [], only_if_exists=True, median_game=0)
    assert _median(mem_engine) == 0
    upsert_league(LEAGUE, "user_a", "L", "2026", [], [], median_game=None)
    upsert_league(LEAGUE, "user_a", "L", "2026", [], [], only_if_exists=True)
    assert _median(mem_engine) == 0


def test_non_sleeper_league_rows_store_null(mem_engine):
    db.upsert_espn_league("4242", "user_a", "ESPN L", 2026, "public", 3, 10)
    assert _median(mem_engine, "4242") is None


# ── Session init ────────────────────────────────────────────────────────────

def test_session_init_stores_the_setting_on_link_and_refreshes_it_on_resync(harness, monkeypatch):  # noqa: F811
    """No new Sleeper call: the setting comes from the payload S0 fetched."""
    client, calls = harness
    monkeypatch.setitem(LEAGUE_META, "settings", {"draft_rounds": 3, "league_average_match": 1})
    assert _init(client, LEAGUE_ID).status_code == 200
    assert calls.get("meta") == 1, calls
    assert _median(db.engine, LEAGUE_ID) == 1
    # The commissioner turns the median off between seasons.
    monkeypatch.setitem(LEAGUE_META, "settings", {"draft_rounds": 3, "league_average_match": 0})
    assert _init(client, LEAGUE_ID).status_code == 200
    assert calls.get("meta") == 2, calls
    assert _median(db.engine, LEAGUE_ID) == 0


def test_session_init_for_a_platform_league_leaves_null(harness):  # noqa: F811
    client, calls = harness
    assert _init(client, NUMERIC_MFL_LEAGUE).status_code == 200
    assert calls == {}, calls
    assert _median(db.engine, NUMERIC_MFL_LEAGUE) is None
