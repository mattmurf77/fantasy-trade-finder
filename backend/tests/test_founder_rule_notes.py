"""Founder notes on the rule catalog (founder review, use case 2; rule-waterfall-design.md §5).

- A save adds a row; the newest is the current note, every earlier version stays (history);
  an empty save clears the current note without losing the question it replaces.
- Text is trimmed and capped at FOUNDER_NOTE_MAX_CHARS; an unknown rule key is rejected
  against ``rule_catalog``; nothing is written when a save is rejected.
- The accessor returns rule key, rule name, current text and an author marker ("you" for the
  viewer, "founder" otherwise and for the operator read with no viewer), in catalog order;
  no account id leaves.
- The table is additive (created by create_all on an existing database without touching other
  tables' rows) and is deleted and exported with its author's account.
"""
import json

import pytest
from sqlalchemy import create_engine, insert, select

from backend import accounts, database as db, rule_catalog as rc

FOUNDER, OTHER = "acct:founder-1", "acct:founder-2"


@pytest.fixture
def engine(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    db.metadata.create_all(engine)
    monkeypatch.setattr(db, "engine", engine)
    yield engine
    engine.dispose()


def rows(engine):
    with engine.connect() as conn:
        return [dict(r._mapping) for r in conn.execute(select(db.founder_rule_notes_table))]


def test_an_edit_adds_a_version_and_the_newest_is_current(engine):
    db.save_founder_rule_note("filler", "Why 450?", FOUNDER, now="2026-11-11T10:00:00+00:00")
    note = db.save_founder_rule_note("filler", "  Why 450 and not 300?  ", FOUNDER,
                                     now="2026-11-11T11:00:00+00:00")
    assert note == {"rule_key": "filler", "rule_name": rc.BY_KEY["filler"].name,
                    "body": "Why 450 and not 300?", "author": "you",
                    "updated_at": "2026-11-11T11:00:00+00:00", "created_at": "2026-11-11T10:00:00+00:00",
                    "versions": 2}
    assert [r["body"] for r in rows(engine)] == ["Why 450?", "Why 450 and not 300?"]
    history = db.load_founder_rule_note_history("filler", viewer_id=OTHER)
    assert [h["body"] for h in history] == ["Why 450?", "Why 450 and not 300?"]
    assert {h["author"] for h in history} == {"founder"}


def test_clearing_keeps_the_history(engine):
    db.save_founder_rule_note("breakup", "Too strict?", FOUNDER)
    db.save_founder_rule_note("breakup", "", FOUNDER)
    assert db.load_founder_rule_notes(viewer_id=FOUNDER) == []
    (cleared,) = [n for n in db.load_founder_rule_notes(include_empty=True) if n["rule_key"] == "breakup"]
    assert cleared["body"] == "" and cleared["versions"] == 2
    assert [h["body"] for h in db.load_founder_rule_note_history("breakup")] == ["Too strict?", ""]


def test_cap_and_unknown_key_are_rejected_without_a_write(engine):
    db.save_founder_rule_note("significance", "x" * db.FOUNDER_NOTE_MAX_CHARS, FOUNDER)
    with pytest.raises(db.FounderNoteError) as long_error:
        db.save_founder_rule_note("significance", "x" * (db.FOUNDER_NOTE_MAX_CHARS + 1), FOUNDER)
    assert long_error.value.code == "too_long"
    for key in ("not_a_rule", "", None, "deck_rules"):
        with pytest.raises(db.FounderNoteError) as unknown:
            db.save_founder_rule_note(key, "?", FOUNDER)
        assert unknown.value.code == "unknown_rule"
    with pytest.raises(db.FounderNoteError):
        db.load_founder_rule_note_history("not_a_rule")
    with pytest.raises(db.FounderNoteError):
        db.save_founder_rule_note("filler", None, FOUNDER)
    assert len(rows(engine)) == 1


def test_accessor_shape_order_and_author_marker(engine):
    db.save_founder_rule_note("redundant", "Question B", OTHER)
    db.save_founder_rule_note("market_floor", "Question A", FOUNDER)
    mine = db.load_founder_rule_notes(viewer_id=FOUNDER)
    order = [r.key for r in rc.RULES]
    assert [n["rule_key"] for n in mine] == sorted(["market_floor", "redundant"], key=order.index)
    assert {n["rule_key"]: n["author"] for n in mine} == {"market_floor": "you", "redundant": "founder"}
    operator = db.load_founder_rule_notes()             # the cron-secret admin read: no viewer
    assert {n["author"] for n in operator} == {"founder"}
    text = json.dumps([mine, operator, db.load_founder_rule_note_history("redundant", viewer_id=FOUNDER)])
    assert FOUNDER not in text and OTHER not in text
    assert len(db.load_founder_rule_notes(include_empty=True)) == len(rc.RULES)


def test_the_table_is_additive(tmp_path, monkeypatch):
    """An existing database gains the table without any other table's rows changing."""
    engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    tables = [t for t in db.metadata.sorted_tables if t.name != "founder_rule_notes"]
    db.metadata.create_all(engine, tables=tables)
    with engine.begin() as conn:
        conn.execute(insert(db.users_table).values(sleeper_user_id="u1"))
    db.metadata.create_all(engine)
    with engine.connect() as conn:
        assert [r.sleeper_user_id for r in conn.execute(select(db.users_table))] == ["u1"]
        assert conn.execute(select(db.founder_rule_notes_table)).fetchall() == []


def test_deleted_and_exported_with_the_account():
    assert "founder_rule_notes" in accounts._ADDITIONAL_PRIVATE_TABLES
    assert any(entry[0] == "founder_rule_notes" for entry in accounts._EXPORT_TABLES)
