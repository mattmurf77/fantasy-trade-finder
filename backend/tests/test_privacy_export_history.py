"""Launch privacy follow-ups: mixed-owner export payloads and held board writes.

Synthetic SQLite by default; FTF_PRIVACY_HISTORY_PG_URL opts into fresh private
schemas of an explicitly disposable PostgreSQL instance. No provider calls.
"""
import json
import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import pytest
from sqlalchemy import Float, Integer, create_engine, insert, select, text

from backend import accounts, database as db, roster_history as rh
from backend.tests.test_account_deletion_coverage import seed

ME, OTHER, LEAGUE = "export-history-viewer", "export-history-partner", "privacy-league"
PRIVATE = "SYNTHETIC_PARTNER_BOARD_NEVER_EXPORT"


@pytest.fixture
def engine(tmp_path, monkeypatch):
    url = os.environ.get("FTF_PRIVACY_HISTORY_PG_URL")
    schema = None
    if url:
        base = create_engine(url)
        schema = "privacy_history_" + uuid.uuid4().hex
        with base.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        eng = base.execution_options(schema_translate_map={None: schema})
    else:
        base = eng = create_engine(f"sqlite:///{tmp_path}/privacy.db",
                                  connect_args={"check_same_thread": False})
    db.metadata.create_all(eng)
    monkeypatch.setattr(db, "engine", eng)
    with eng.begin() as conn:
        conn.execute(insert(db.users_table), [{"sleeper_user_id": ME}, {"sleeper_user_id": OTHER}])
    try:
        yield eng
    finally:
        if schema:
            with base.begin() as conn:
                conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        base.dispose()


def _board(eng, owner=OTHER, value=1550.0):
    with eng.begin() as conn:
        conn.execute(insert(db.member_rankings_table).values(
            user_id=owner, league_id=LEAGUE, player_id="p1", elo=value,
            scoring_format="1qb_ppr", updated_at="2026-11-04T00:00:00+00:00"))


def _held_board():
    return dict(user_id=OTHER, league_id=LEAGUE, scoring_format="1qb_ppr",
                period_key="2026-W45", snapshot_date="2026-11-04",
                snapshot_at="2026-11-04T00:00:00+00:00", source="sync",
                elos=json.dumps({"p1": 1550.0}), player_count=1,
                board_updated_at="2026-11-04T00:00:00+00:00")


def _history(eng):
    with eng.connect() as conn:
        return conn.execute(select(db.league_board_history_table)).mappings().all()


def test_other_members_deletion_between_board_read_and_write_never_revives_history(engine, monkeypatch):
    _board(engine)
    real = rh.load_member_boards_for_league
    def read_then_delete(league):
        boards = real(league)
        accounts.delete_user_data(OTHER)
        return boards
    monkeypatch.setattr(rh, "load_member_boards_for_league", read_then_delete)
    result = rh.snapshot_league_boards(LEAGUE, "sync", live_user=ME)
    assert result["inserted"] == 0 and result["skipped"] == 1
    assert not _history(engine)


def test_held_board_cannot_be_written_under_a_recreated_owner(engine):
    _board(engine)
    held = _held_board()
    accounts.delete_user_data(OTHER)
    db.upsert_user(OTHER)
    _board(engine, value=1700.0)
    assert db.upsert_board_snapshots([held], live_user=ME)["skipped"] == 1
    assert not _history(engine)


def test_live_owner_keeps_snapshot_and_precedence(engine):
    _board(engine)
    assert db.upsert_board_snapshots([_held_board()], live_user=ME)["inserted"] == 1
    assert db.upsert_board_snapshots([{**_held_board(), "source": "backfill"}], live_user=ME)["skipped"] == 1
    assert db.upsert_board_snapshots([{**_held_board(), "source": "weekly"}], live_user=ME)["updated"] == 1
    assert len(_history(engine)) == 1


def test_export_withholds_mixed_owner_internal_payloads_and_preserves_owned_history(engine):
    features = {"shape": "1x1", "give_value": 1200, "partner_user_id": OTHER,
                "owner_request": {"input": {"members": [{"id": OTHER, "elo": {"p1": PRIVATE}}]}},
                "owner_experiment": {"private": PRIVATE}, "owner_generation": {"private": PRIVATE},
                "roster_evaluation": {"teams": {OTHER: PRIVATE}}, "prepared_runtime": PRIVATE,
                "fit": {"them": PRIVATE}, "fit_diag": {"them": PRIVATE},
                "match_context": {"counterparty_preference": PRIVATE}, "breaker_shadow": PRIVATE,
                "likes_you": True, "surplus_margin": 1.5}
    valuation = {"viewer_board": {"own": 1234}, "partner_board": PRIVATE,
                 "assets": [{"viewer_value": 1, "partner_raw_value": PRIVATE}],
                 "counterparty": PRIVATE, "bilateral": PRIVATE}
    with engine.begin() as conn:
        seed(conn, db.deck_impressions_table, "own-card", user_id=ME,
             features_json=json.dumps(features), valuation_json=json.dumps(valuation))
        seed(conn, db.trade_proposals_table, "own-send", user_id=ME,
             valuation_json=json.dumps(valuation))
        seed(conn, db.trade_matches_table, "own-match", user_a_id=ME, user_b_id=OTHER,
             match_valuation_json=json.dumps({"viewer_board": PRIVATE}))
        for name, payloads in accounts._EXPORT_INTERNAL_PAYLOADS.items():
            table = getattr(db, name + "_table")
            values = {col: (1234 if isinstance(table.c[col].type, (Float, Integer)) else PRIVATE.encode() if col.endswith("_packed") or col == "cards_blob"
                            else {"private": PRIVATE} if col.endswith("_blob") else PRIVATE)
                      for col in payloads if col in table.c}
            seed(conn, table, name + "-private", user_id=ME, **values)
    before = json.dumps(features)
    archive = accounts.export_user_data(ME)
    assert PRIVATE not in json.dumps(archive)
    row = archive["tables"]["deck_impressions"][0]
    assert json.loads(row["features_json"])["shape"] == "1x1"
    assert json.loads(row["valuation_json"])["viewer_board"] == {"own": 1234}
    assert archive["tables"]["trade_matches"][0]["match_valuation_json"] is None
    for name, omitted in accounts._EXPORT_INTERNAL_PAYLOADS.items():
        assert len(archive["tables"][name]) == 1
        assert not set(omitted).intersection(archive["tables"][name][0])
    with engine.connect() as conn:
        assert conn.execute(select(db.deck_impressions_table.c.features_json)).scalar_one() == before


@pytest.mark.parametrize("raw", ["{broken", '["not", "object"]', '"private string"', "null"])
def test_malformed_private_json_is_withheld(raw):
    assert accounts._export_deck_features(raw) is None
    assert accounts._export_valuation(raw) is None


@pytest.mark.parametrize("live_user", [ME, None])
def test_pg_board_owner_fence_spans_history_write_and_concurrent_deletion(engine, live_user):
    if engine.dialect.name != "postgresql":
        pytest.skip("PG row-lock interleaving; SQLite uses BEGIN IMMEDIATE")
    from sqlalchemy import event
    _board(engine)
    entered, release, deleting = threading.Event(), threading.Event(), threading.Event()
    role = threading.local()
    delete_pid = []

    def observe(conn, cursor, statement, parameters, context, executemany):
        if getattr(role, "value", None) == "write" and "insert into" in statement.lower() and "league_board_history" in statement:
            entered.set()
            assert release.wait(10)
        if getattr(role, "value", None) == "delete" and not delete_pid:
            delete_pid.append(conn.connection.driver_connection.get_backend_pid())
            deleting.set()

    def write():
        role.value = "write"
        return db.upsert_board_snapshots([_held_board()], live_user=live_user)

    def delete():
        role.value = "delete"
        return accounts.delete_user_data(OTHER)

    event.listen(engine, "before_cursor_execute", observe)
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            writer = executor.submit(write)
            assert entered.wait(10)
            deletion = executor.submit(delete)
            try:
                assert deleting.wait(10)
                # Inspect PostgreSQL's lock state, not an elapsed-time guess:
                # deletion must be waiting on the owner lock until write commits.
                waiting = False
                for _ in range(500):
                    with engine.connect() as conn:
                        waiting = conn.execute(text("SELECT wait_event_type = 'Lock' FROM pg_stat_activity WHERE pid = :pid"),
                                               {"pid": delete_pid[0]}).scalar()
                    if waiting:
                        break
                    threading.Event().wait(0.01)
                assert waiting and not deletion.done()
            finally:
                release.set()
            assert writer.result(timeout=10)["inserted"] == 1
            deletion.result(timeout=10)
        assert not _history(engine)
    finally:
        release.set()
        event.remove(engine, "before_cursor_execute", observe)
