"""database.py blind-grading schema + helpers (docs/plans/blind-grading/lld.md §3–§4, specs §5.1).

Covers: both tables' columns, nullability, the unique constraint and the two indexes;
load_grading_legacy_deck's job choice and the six qualifying predicates; insert / load /
next-card round trip (next never carries arms_json); the §3.3 build helpers
(finish_grading_session_build guards on 'building', fail_grading_session likewise);
answer_grading_card ownership, completion and rejection; report row filters; and account
deletion + export through accounts._ADDITIONAL_PRIVATE_TABLES. In-memory SQLite only.
"""
import json
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, insert, select

from backend import accounts, database as db

UID, OTHER = "acct-grader", "acct-other"
NOW = "2026-10-02T12:00:00+00:00"


@pytest.fixture
def engine():
    eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    db.metadata.create_all(eng)
    with patch.object(db, "engine", eng):
        yield eng
    eng.dispose()


def session_row(sid, user_id=UID, league_id="L1", status="open", created_at=NOW, **over):
    row = {"session_id": sid, "user_id": user_id, "league_id": league_id, "status": status,
           "seed": "123", "created_at": created_at, "completed_at": None,
           "counts_json": "{}", "source_json": "{}", "error_json": None}
    row.update(over)
    return row


def card_row(cid, sid, position, user_id=UID, arms=("current",), **over):
    row = {"card_id": cid, "session_id": sid, "user_id": user_id, "position": position,
           "arms_json": json.dumps({a: {} for a in arms}),
           "trade_json": json.dumps({"partner_name": "P", "give": [], "receive": []}),
           "grade": None, "skipped": 0, "tags_json": "[]", "graded_at": None}
    row.update(over)
    return row


def impression(job, idx, served_at, **over):
    # Every row carries the same keys: an executemany takes its columns from the FIRST
    # row and silently drops keys the later rows add.
    row = {"impression_id": f"{job}-{idx}", "user_id": UID, "league_id": "L1", "deck_job_id": job,
           "card_index": idx, "propensity": 1.0, "served_at": served_at, "model_arm": "current",
           "assets_json": json.dumps({"give": [f"g{idx}"], "receive": [f"r{idx}"]}),
           "features_json": json.dumps({"partner_user_id": "u2"}),
           "is_ghost": None, "source_like_impression_id": None, "trade_intent": None}
    row.update(over)
    return row


def rows(table):
    with db.engine.connect() as conn:
        return conn.execute(select(table)).mappings().all()


def test_tables_created_with_expected_columns(engine):
    from sqlalchemy import inspect
    insp = inspect(engine)
    assert "grading_sessions" in insp.get_table_names()
    assert "grading_cards" in insp.get_table_names()
    sessions = {c["name"]: c for c in insp.get_columns("grading_sessions")}
    assert list(sessions) == ["session_id", "user_id", "league_id", "status", "seed", "created_at",
                              "completed_at", "counts_json", "source_json", "error_json"]
    assert {n for n, c in sessions.items() if c["nullable"]} == {"completed_at", "error_json"}
    cards = {c["name"]: c for c in insp.get_columns("grading_cards")}
    assert list(cards) == ["card_id", "session_id", "user_id", "position", "arms_json",
                           "trade_json", "grade", "skipped", "tags_json", "graded_at"]
    assert {n for n, c in cards.items() if c["nullable"]} == {"grade", "graded_at"}
    assert cards["skipped"]["default"] == "'0'" and cards["tags_json"]["default"] == "'[]'"
    uniques = {u["name"]: u["column_names"] for u in insp.get_unique_constraints("grading_cards")}
    assert uniques["uq_grading_card_position"] == ["session_id", "position"]
    idx_sessions = {i["name"]: i["column_names"] for i in insp.get_indexes("grading_sessions")}
    assert idx_sessions["ix_grading_sessions_user_league"] == ["user_id", "league_id", "status"]
    idx_cards = {i["name"]: i["column_names"] for i in insp.get_indexes("grading_cards")}
    assert idx_cards["ix_grading_cards_session"] == ["session_id"]
    # server defaults apply when the writer omits the columns
    with engine.begin() as conn:
        conn.execute(insert(db.grading_cards_table).values(
            card_id="c", session_id="s", user_id=UID, position=1, arms_json="{}", trade_json="{}"))
    (card,) = rows(db.grading_cards_table)
    assert card["skipped"] == 0 and card["tags_json"] == "[]" and card["grade"] is None
    # the unique constraint holds
    from sqlalchemy.exc import IntegrityError
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(insert(db.grading_cards_table).values(
            card_id="c2", session_id="s", user_id=UID, position=1, arms_json="{}", trade_json="{}"))


def test_load_grading_legacy_deck_picks_newest_qualifying_job(engine):
    with engine.begin() as conn:
        conn.execute(insert(db.deck_impressions_table), [
            # Job A (older) — qualifying rows out of card_index order on purpose
            impression("A", 2, "2026-10-01T10:00:00+00:00"),
            impression("A", 0, "2026-10-01T10:00:00+00:00"),
            impression("A", 1, "2026-10-01T10:00:00+00:00", model_arm="gen_v2",
                       features_json=json.dumps({"partner_user_id": "u3"})),
            # one of each disqualifier, all in A
            impression("A", 3, "2026-10-01T10:00:00+00:00", is_ghost=1),
            impression("A", 4, "2026-10-01T10:00:00+00:00", model_arm="value_core"),
            impression("A", 5, "2026-10-01T10:00:00+00:00", source_like_impression_id="x"),
            impression("A", 6, "2026-10-01T10:00:00+00:00", trade_intent="consolidate"),
            impression("A", 7, "2026-10-01T10:00:00+00:00", assets_json=None),
            impression("A", 8, "2026-10-01T10:00:00+00:00", model_arm=None),
            # Job B (newer) — only model_arm IS NULL rows: never qualifies
            impression("B", 0, "2026-10-02T10:00:00+00:00", model_arm=None),
            impression("B", 1, "2026-10-02T10:00:00+00:00", model_arm=None),
            # Another user / another league with newer qualifying rows: not the caller's
            impression("C", 0, "2026-10-02T11:00:00+00:00", user_id=OTHER),
            impression("D", 0, "2026-10-02T11:00:00+00:00", league_id="L2"),
        ])
    job, served_at, got = db.load_grading_legacy_deck(UID, "L1")
    assert job == "A" and served_at == "2026-10-01T10:00:00+00:00"
    assert [r["card_index"] for r in got] == [0, 1, 2]
    assert set(got[0]) == {"impression_id", "card_index", "model_arm", "assets_json", "features_json"}
    assert got[1]["model_arm"] == "gen_v2"
    assert json.loads(got[2]["assets_json"]) == {"give": ["g2"], "receive": ["r2"]}
    # ghost default: is_ghost NULL reads as 0 (COALESCE) — row 0/2 have NULL and qualified
    assert db.load_grading_legacy_deck(UID, "L9") == (None, None, [])
    assert db.load_grading_legacy_deck("nobody", "L1") == (None, None, [])


def test_insert_load_round_trip_and_next_card_never_returns_arms(engine):
    cards = [card_row("c3", "s1", 3, arms=("current", "value_core")),
             card_row("c1", "s1", 1), card_row("c2", "s1", 2, arms=("value_core",))]
    db.insert_grading_session(session_row("s1"), cards)
    assert db.load_grading_session("s1", UID)["status"] == "open"
    assert db.load_grading_session("s1", OTHER) is None
    assert db.load_grading_session("s1")["user_id"] == UID            # any owner
    assert db.load_grading_session("nope") is None
    assert db.load_open_grading_session(UID, "L1")["session_id"] == "s1"
    assert db.load_open_grading_session(UID, "L2") is None
    assert db.load_open_grading_session(OTHER, "L1") is None
    assert db.grading_progress("s1") == {"answered": 0, "total": 3}
    nxt = db.load_next_grading_card("s1")
    assert set(nxt) == {"card_id", "position", "trade_json"}
    assert nxt["card_id"] == "c1" and nxt["position"] == 1
    loaded = db.load_grading_cards("s1")
    assert [c["card_id"] for c in loaded] == ["c1", "c2", "c3"]
    assert set(loaded[0]) == set(card_row("x", "s1", 9))
    assert json.loads(loaded[2]["arms_json"]) == {"current": {}, "value_core": {}}
    # newest resumable session wins; statuses filter
    db.insert_grading_session(session_row("s2", status="building",
                                          created_at="2026-10-03T00:00:00+00:00"), [])
    assert db.load_open_grading_session(UID, "L1")["session_id"] == "s2"
    db.insert_grading_session(session_row("s3", status="failed", error_json='{"code":"x"}',
                                          created_at="2026-10-04T00:00:00+00:00"), [])
    assert db.load_open_grading_session(UID, "L1")["session_id"] == "s2"
    assert db.load_open_grading_session(UID, "L1", statuses=("building", "open", "failed")
                                        )["session_id"] == "s3"
    db.insert_grading_session(session_row("s4", status="completed",
                                          created_at="2026-10-05T00:00:00+00:00"), [])
    assert db.load_open_grading_session(UID, "L1", statuses=("building", "open", "failed")
                                        )["session_id"] == "s3"


def test_finish_and_fail_build_only_touch_building_sessions(engine):
    db.insert_grading_session(session_row("b1", status="building"), [])
    assert db.load_next_grading_card("b1") is None
    cards = [card_row("c1", "b1", 1), card_row("c2", "b1", 2)]
    assert db.finish_grading_session_build("b1", cards, counts_json='{"total": 2}',
                                           source_json='{"v": 1}') is True
    row = db.load_grading_session("b1")
    assert row["status"] == "open" and row["counts_json"] == '{"total": 2}'
    assert row["source_json"] == '{"v": 1}' and row["error_json"] is None
    assert db.grading_progress("b1") == {"answered": 0, "total": 2}
    # a second finish (or a fail) on an open session writes nothing
    assert db.finish_grading_session_build("b1", [card_row("c9", "b1", 9)], counts_json="{}",
                                           source_json="{}") is False
    assert db.fail_grading_session("b1", '{"code": "value_core_failed"}') is False
    assert db.grading_progress("b1") == {"answered": 0, "total": 2}
    assert db.load_grading_session("b1")["status"] == "open"
    # fail flips a building session and records the error
    db.insert_grading_session(session_row("b2", status="building"), [])
    assert db.fail_grading_session("b2", '{"code": "value_core_too_few", "usable": 3}') is True
    row = db.load_grading_session("b2")
    assert row["status"] == "failed" and json.loads(row["error_json"]) == {
        "code": "value_core_too_few", "usable": 3}
    assert db.finish_grading_session_build("b2", cards, counts_json="{}", source_json="{}") is False
    assert db.fail_grading_session("missing", "{}") is False
    # an insert failure inside finish rolls the status flip back (one transaction)
    db.insert_grading_session(session_row("b3", status="building"), [])
    from sqlalchemy.exc import IntegrityError
    dup = [card_row("d1", "b3", 1), card_row("d2", "b3", 1)]               # same position
    with pytest.raises(IntegrityError):
        db.finish_grading_session_build("b3", dup, counts_json="{}", source_json="{}")
    assert db.load_grading_session("b3")["status"] == "building"
    assert db.grading_progress("b3") == {"answered": 0, "total": 0}


def test_answer_grading_card_foreign_user_returns_none(engine):
    db.insert_grading_session(session_row("s1"), [card_row("c1", "s1", 1), card_row("c2", "s1", 2)])
    assert db.answer_grading_card("c1", OTHER, grade=4, skipped=False, tags_json='["overpay"]',
                                  now=NOW) is None
    assert db.answer_grading_card("nope", UID, grade=4, skipped=False, tags_json="[]",
                                  now=NOW) is None
    (c1, _) = db.load_grading_cards("s1")
    assert (c1["grade"], c1["skipped"], c1["tags_json"], c1["graded_at"]) == (None, 0, "[]", None)
    # a card whose session belongs to someone else is foreign even if the card row says UID
    db.insert_grading_session(session_row("s9", user_id=OTHER), [card_row("c9", "s9", 1, user_id=UID)])
    assert db.answer_grading_card("c9", UID, grade=4, skipped=False, tags_json="[]", now=NOW) is None
    # the happy path: answer, then complete on the last card, then reject
    res = db.answer_grading_card("c1", UID, grade=4, skipped=False, tags_json='["overpay"]', now=NOW)
    assert res == {"session_id": "s1", "status": "open", "rejected": False, "answered": 1, "total": 2}
    res = db.answer_grading_card("c2", UID, grade=None, skipped=True, tags_json="[]", now=NOW)
    assert res == {"session_id": "s1", "status": "completed", "rejected": False, "answered": 2,
                   "total": 2}
    row = db.load_grading_session("s1")
    assert row["status"] == "completed" and row["completed_at"] == NOW
    res = db.answer_grading_card("c1", UID, grade=1, skipped=False, tags_json="[]", now=NOW)
    assert res == {"session_id": "s1", "status": "completed", "rejected": True, "answered": 2,
                   "total": 2}
    (c1, c2) = db.load_grading_cards("s1")
    assert c1["grade"] == 4 and c2["skipped"] == 1 and c2["grade"] is None
    assert db.load_next_grading_card("s1") is None


def test_report_rows_since_and_include_open(engine):
    db.insert_grading_session(session_row("s1", status="completed", created_at="2026-09-30T10:00:00+00:00"),
                              [card_row("c1", "s1", 1)])
    db.insert_grading_session(session_row("s2", status="open", created_at="2026-10-01T10:00:00+00:00"),
                              [card_row("c2", "s2", 1), card_row("c3", "s2", 2)])
    db.insert_grading_session(session_row("s3", status="completed", user_id=OTHER,
                                          created_at="2026-10-02T10:00:00+00:00"),
                              [card_row("c4", "s3", 1, user_id=OTHER)])
    db.insert_grading_session(session_row("s4", status="failed", created_at="2026-10-03T10:00:00+00:00"), [])
    sessions, cards = db.load_grading_report_rows(None, False)
    assert [s["session_id"] for s in sessions] == ["s1", "s3"]
    assert [c["card_id"] for c in cards] == ["c1", "c4"]
    sessions, cards = db.load_grading_report_rows(None, True)
    assert [s["session_id"] for s in sessions] == ["s1", "s2", "s3", "s4"]
    assert [c["card_id"] for c in cards] == ["c1", "c2", "c3", "c4"]
    sessions, cards = db.load_grading_report_rows("2026-10-01", False)
    assert [s["session_id"] for s in sessions] == ["s3"] and [c["card_id"] for c in cards] == ["c4"]
    sessions, cards = db.load_grading_report_rows("2026-10-01", True)
    assert [s["session_id"] for s in sessions] == ["s2", "s3", "s4"]
    assert db.load_grading_report_rows("2027-01-01", True) == ([], [])


def test_account_deletion_removes_grading_rows(engine):
    with engine.begin() as conn:
        for uid in (UID, OTHER):
            conn.execute(insert(db.users_table).values(sleeper_user_id=uid))
    db.insert_grading_session(session_row("s1"), [card_row("c1", "s1", 1), card_row("c2", "s1", 2)])
    db.insert_grading_session(session_row("s2", user_id=OTHER),
                              [card_row("c3", "s2", 1, user_id=OTHER)])
    assert "grading_sessions" in accounts._ADDITIONAL_PRIVATE_TABLES
    assert "grading_cards" in accounts._ADDITIONAL_PRIVATE_TABLES
    archive = accounts.export_user_data(UID)
    assert [r["session_id"] for r in archive["tables"]["grading_sessions"]] == ["s1"]
    assert sorted(r["card_id"] for r in archive["tables"]["grading_cards"]) == ["c1", "c2"]
    counts = accounts.delete_user_data(UID)
    assert counts["grading_sessions_deleted"] == 1 and counts["grading_cards_deleted"] == 2
    assert [r["user_id"] for r in rows(db.grading_sessions_table)] == [OTHER]
    assert [r["user_id"] for r in rows(db.grading_cards_table)] == [OTHER]
