"""#258 — MFL team names showing HTML entities on TradesHome.
#282 (reopens #258) — the actual junk was franchise name color/formatting
markup MFL owners can apply, not HTML entities.

Root cause: #210 added `mfl_service._clean_text` so every MFL *ingest* path
entity-decodes names — but leagues linked BEFORE #210 had already stored the
raw strings ('Fish &amp; Chips', '&#201;ire Rebels') in `league_members`,
`leagues.name`, and the denormalized `draft_picks` username snapshots, and
MFL leagues have no automatic re-import to refresh them. Every surface that
reads the stored rows (trade deck counterparty names, matches, power
rankings, pick labels) kept serving the entities. #282: the operator
confirmed entities weren't the real complaint — MFL lets owners style their
franchise name, so the raw name string can carry markup like
'<font color = Green>...'. #282 extended `_clean_text` to also strip that
markup; because the backfill's `_cleaned()` helper compares `_clean_text`
output against the stored value, the improved cleaner alone is enough to
re-clean rows that only had markup (no entities) on the next boot.

Fix under test: `database._backfill_mfl_name_entities()` — an idempotent
startup pass (called from `_migrate_db`) that runs `mfl_service._clean_text`
over the stored MFL rows in place, scoped strictly to platform='mfl' so
Sleeper's user-typed names are never rewritten.
"""
import json
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, insert, select

import backend.database as db
from backend.database import (
    metadata,
    leagues_table,
    league_members_table,
    draft_picks_table,
)

MFL_LEAGUE = "10005"
SLEEPER_LEAGUE = "99887766"


@pytest.fixture()
def mem_engine():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    metadata.create_all(engine)
    with patch.object(db, "engine", engine):
        yield engine


def _seed(engine):
    """A pre-#210 MFL league with entity-bearing names everywhere a name is
    stored, plus a Sleeper league whose literal '&amp;' must survive."""
    with engine.begin() as conn:
        conn.execute(insert(leagues_table), [
            {"sleeper_league_id": MFL_LEAGUE,
             "name": "The Dependables &amp; Friends",
             "user_id": "u1", "season": "2026", "platform": "mfl",
             "roster_data": "[]", "opponent_data": "[]"},
            {"sleeper_league_id": SLEEPER_LEAGUE,
             "name": "Sleeper &amp; Sons",       # user-typed on Sleeper — keep
             "user_id": "u1", "season": "2026", "platform": None,
             "roster_data": "[]", "opponent_data": "[]"},
        ])
        conn.execute(insert(league_members_table), [
            {"league_id": MFL_LEAGUE, "user_id": "u1",
             "username": "&#201;ire  Rebels", "display_name": "&#201;ire  Rebels",
             "roster_data": "[]"},
            {"league_id": MFL_LEAGUE, "user_id": f"mfl:{MFL_LEAGUE}.f0002",
             "username": "Fish &amp; Chips", "display_name": "Fish &amp; Chips",
             "roster_data": "[]"},
            {"league_id": MFL_LEAGUE, "user_id": f"mfl:{MFL_LEAGUE}.f0003",
             "username": "Plain Team", "display_name": "Plain Team",
             "roster_data": "[]"},
            # #282 — real dirty row captured from prod league 62846
            # (franchise f0012): color/formatting markup, no entities at all.
            {"league_id": MFL_LEAGUE, "user_id": f"mfl:{MFL_LEAGUE}.f0012",
             "username": "<b><font color= Green>North London Rams</b>",
             "display_name": "<b><font color= Green>North London Rams</b>",
             "roster_data": "[]"},
            {"league_id": SLEEPER_LEAGUE, "user_id": "u9",
             "username": "Sleeper &amp; Co", "display_name": "Sleeper &amp; Co",
             "roster_data": "[]"},
        ])
        conn.execute(insert(draft_picks_table), [
            {"pick_id": f"{MFL_LEAGUE}-2027-1-0002", "league_id": MFL_LEAGUE,
             "season": 2027, "round": 1,
             "owner_user_id": f"mfl:{MFL_LEAGUE}.f0002",
             "owner_username": "Fish &amp; Chips",
             "original_roster_id": "0002",
             "original_user_id": f"mfl:{MFL_LEAGUE}.f0002",
             "original_username": "Fish &amp; Chips",
             "is_traded": 0, "platform": "mfl"},
            {"pick_id": f"{SLEEPER_LEAGUE}-2027-1-3", "league_id": SLEEPER_LEAGUE,
             "season": 2027, "round": 1,
             "owner_user_id": "u9", "owner_username": "Sleeper &amp; Co",
             "original_roster_id": "3", "original_user_id": "u9",
             "original_username": "Sleeper &amp; Co",
             "is_traded": 0, "platform": "sleeper"},
        ])


def _members(league_id):
    return {m["user_id"]: m for m in db.load_league_members(league_id)}


def test_backfill_decodes_stored_mfl_names(mem_engine):
    _seed(mem_engine)
    db._backfill_mfl_name_entities()

    members = _members(MFL_LEAGUE)
    assert members[f"mfl:{MFL_LEAGUE}.f0002"]["username"] == "Fish & Chips"
    assert members[f"mfl:{MFL_LEAGUE}.f0002"]["display_name"] == "Fish & Chips"
    # numeric entity + whitespace run, same normalization as _clean_text
    assert members["u1"]["username"] == "Éire Rebels"
    assert members["u1"]["display_name"] == "Éire Rebels"
    # clean rows untouched
    assert members[f"mfl:{MFL_LEAGUE}.f0003"]["username"] == "Plain Team"
    # #282 — markup-only dirty row (no entities) also gets cleaned, because
    # the improved _clean_text output differs from the stored value
    assert members[f"mfl:{MFL_LEAGUE}.f0012"]["username"] == "North London Rams"
    assert members[f"mfl:{MFL_LEAGUE}.f0012"]["display_name"] == "North London Rams"

    with mem_engine.connect() as conn:
        lg_name = conn.execute(
            select(leagues_table.c.name)
            .where(leagues_table.c.sleeper_league_id == MFL_LEAGUE)
        ).scalar_one()
        assert lg_name == "The Dependables & Friends"

        pick = conn.execute(
            select(draft_picks_table.c.owner_username,
                   draft_picks_table.c.original_username)
            .where(draft_picks_table.c.league_id == MFL_LEAGUE)
        ).one()
        assert pick.owner_username == "Fish & Chips"
        assert pick.original_username == "Fish & Chips"


def test_backfill_never_touches_sleeper_rows(mem_engine):
    """Sleeper names are user-typed and rendered verbatim by Sleeper itself —
    a literal '&amp;' there is (pathological but) intended display."""
    _seed(mem_engine)
    db._backfill_mfl_name_entities()

    assert _members(SLEEPER_LEAGUE)["u9"]["username"] == "Sleeper &amp; Co"
    with mem_engine.connect() as conn:
        lg_name = conn.execute(
            select(leagues_table.c.name)
            .where(leagues_table.c.sleeper_league_id == SLEEPER_LEAGUE)
        ).scalar_one()
        assert lg_name == "Sleeper &amp; Sons"
        pick = conn.execute(
            select(draft_picks_table.c.owner_username)
            .where(draft_picks_table.c.league_id == SLEEPER_LEAGUE)
        ).scalar_one()
        assert pick == "Sleeper &amp; Co"


def test_backfill_is_idempotent_and_safe_on_empty_db(mem_engine):
    # empty DB: no MFL leagues → early return, no error
    db._backfill_mfl_name_entities()

    _seed(mem_engine)
    db._backfill_mfl_name_entities()
    first = _members(MFL_LEAGUE)
    db._backfill_mfl_name_entities()   # second pass writes nothing new
    assert _members(MFL_LEAGUE) == first
    assert first[f"mfl:{MFL_LEAGUE}.f0002"]["username"] == "Fish & Chips"


def test_migrate_db_runs_the_backfill(mem_engine):
    """The fix only helps if startup actually runs it — pin the _migrate_db
    call so the backfill can't be silently dropped from the boot path."""
    _seed(mem_engine)
    db._migrate_db()
    assert _members(MFL_LEAGUE)[f"mfl:{MFL_LEAGUE}.f0002"]["username"] == "Fish & Chips"
