"""Regression tests for upsert_league (TC-E2E-001 finding F-1).

The `leagues` table is keyed on `sleeper_league_id` ALONE. The old upsert
keyed its SELECT/INSERT on (sleeper_league_id, user_id), so when a SECOND
member of an already-imported league called session_init the SELECT missed
(different user_id), the INSERT fired, and SQLite raised
`UNIQUE constraint failed: leagues.sleeper_league_id`. The caller swallowed
it, so the second member's league row never persisted.

These tests pin the fixed behaviour: one row per league, owned by the first
importer, and a second member's upsert refreshes league-level metadata
instead of crashing.
"""

import json
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, select

import backend.database as db_module
from backend.database import upsert_league, leagues_table, metadata

LEAGUE = "987654321012345678"   # 18-digit Sleeper-style id


@pytest.fixture()
def mem_engine():
    """Fresh in-memory SQLite engine with the full schema, patched in as the
    module-level engine so all database.py functions use it."""
    eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    metadata.create_all(eng)
    with patch.object(db_module, "engine", eng), \
            patch.object(db_module, "DATABASE_URL", "sqlite://"):
        yield eng


def _rows(eng):
    with eng.connect() as conn:
        return conn.execute(
            select(leagues_table).where(leagues_table.c.sleeper_league_id == LEAGUE)
        ).fetchall()


def test_second_member_upsert_does_not_raise(mem_engine):
    """Two users importing the same league must not hit a UNIQUE violation."""
    upsert_league(LEAGUE, "user_a", "Lakeview Dynasty", "2026", ["p1", "p2"], [])
    # Previously raised IntegrityError: UNIQUE constraint failed.
    upsert_league(LEAGUE, "user_b", "Lakeview Dynasty", "2026", ["p3", "p4"], [])

    rows = _rows(mem_engine)
    assert len(rows) == 1, "exactly one row per league (PK = sleeper_league_id)"


def test_importer_owner_row_is_preserved(mem_engine):
    """The first importer owns the row; a later member does not clobber its
    user_id / roster snapshot — only league-level metadata is refreshed."""
    upsert_league(LEAGUE, "user_a", "Lakeview", "2026", ["p1", "p2"],
                  [{"user_id": "user_b", "username": "b", "player_ids": ["p3"]}])
    upsert_league(LEAGUE, "user_b", "Lakeview (renamed)", "2026", ["p3", "p4"], [])

    (row,) = _rows(mem_engine)
    assert row.user_id == "user_a", "importer-owner is not overwritten"
    assert json.loads(row.roster_data) == ["p1", "p2"], "owner's snapshot preserved"
    assert json.loads(row.opponent_data) == [
        {"user_id": "user_b", "username": "b", "player_ids": ["p3"]}
    ], "owner's opponent snapshot preserved"
    assert row.name == "Lakeview (renamed)", "league-level name IS refreshed"


def test_owner_reimport_refreshes_updated_at(mem_engine):
    """The owner re-importing updates the row in place (no duplicate, no crash)."""
    with patch.object(db_module, "_now", return_value="2026-06-13T00:00:00"):
        upsert_league(LEAGUE, "user_a", "Lakeview", "2026", ["p1"], [])
    with patch.object(db_module, "_now", return_value="2026-06-14T00:00:00"):
        upsert_league(LEAGUE, "user_a", "Lakeview", "2026", ["p1", "p2"], [])

    (row,) = _rows(mem_engine)
    assert row.created_at == "2026-06-13T00:00:00", "created_at is not bumped"
    assert row.updated_at == "2026-06-14T00:00:00", "updated_at is refreshed"
