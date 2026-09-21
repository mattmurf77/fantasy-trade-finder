"""Structured evidence retains exact JSON, scoped snapshots and atomic commits.

The streaming logger publishes callbacks only after durable batches, preserves
global indices and context, and never mutates captured shared evidence.
"""
import copy
from datetime import datetime, timezone
import json
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import IntegrityError

from backend import database as db, deck_diagnostics as codec


def structured_rows(count=12):
    shared = {f"setting_{i}": i / 13 for i in range(250)}
    generation = {"config": shared, "emitted": count, "slots": ["QB", "WR", "FLEX"]}
    return [dict(impression_id=f"imp-{i}", user_id="u", league_id="l", deck_job_id="j",
                 card_index=i, propensity=1., served_at="2026-09-21T00:00:00Z",
                 valuation_json=json.dumps({"exact_terms": [str(i)], "value": 12.3}),
                 features_json={"partner_user_id": "p", "give_value": 3.25,
                     "owner_request": {"input": {"config": shared, "asset": str(i)}},
                     "owner_generation": generation}) for i in range(count)]


def legacy_rows(rows):
    return [{**row, "features_json": json.dumps(row["features_json"], default=str)} for row in rows]


@pytest.fixture
def engine(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    db.metadata.create_all(engine)
    monkeypatch.setattr(db, "engine", engine)
    yield engine
    engine.dispose()


def test_structured_matches_legacy_exact_bytes_and_does_not_mutate(monkeypatch):
    rows = structured_rows()
    before = copy.deepcopy(rows)
    generation = rows[0]["features_json"]["owner_generation"]
    visits = []
    original = codec.dumps

    def counted(value):
        if value is generation:
            visits.append(value)
        return original(value)

    monkeypatch.setattr(codec, "dumps", counted)
    actual = codec.compact_rows(rows)
    assert actual == codec.compact_rows(legacy_rows(rows))
    assert len(visits) == 1  # actual object sharing, no content-interning setup
    assert rows == before
    mapping = {node["snapshot_id"]: node["payload_json"] for node in actual[1]}
    for source, compacted in zip(rows, actual[0]):
        assert codec.expand_features(json.loads(compacted["features_json"]), mapping) == json.loads(
            json.dumps(source["features_json"]))


def test_structured_plain_reference_and_default_str_roundtrip():
    for features in ({}, {"core": [1, 2]},
                     {"owner_request": {codec.REFERENCE_KEY: "existing"}},
                     {"owner_generation": {"captured_at": datetime(2026, 9, 21, tzinfo=timezone.utc)}},
                     {"owner_generation": {"slots": ("QB", "WR", "FLEX"), "large": ("x" * 2048,)}},
                     {"owner_request": {"ranks": {2: "second", 11: "eleventh", "1": "first"}}},
                     {"owner_request": {"aliases": {1: "old", "1": "last"}, None: "missing", False: "false"}}):
        rows = structured_rows(1)
        rows[0]["features_json"] = features
        assert codec.compact_rows(rows) == codec.compact_rows(legacy_rows(rows))


def test_structured_cycles_fail_before_storage(engine):
    rows = structured_rows(1)
    features = rows[0]["features_json"]
    features["cycle"] = features
    with pytest.raises(ValueError, match="Circular reference"):
        db.save_deck_impressions(rows)
    with engine.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(db.deck_impressions_table)) == 0


def test_structured_batch_database_parity_and_snapshot_immutability(engine, monkeypatch):
    monkeypatch.setattr(db, "DECK_IMPRESSION_INSERT_ROWS", 5)
    rows = structured_rows(12)
    expected = legacy_rows(rows)
    db.save_deck_impressions(rows)
    rows[0]["features_json"]["owner_generation"]["config"]["setting_0"] = "mutated after commit"
    with engine.connect() as conn:
        actual = list(conn.execute(select(db.deck_impressions_table).order_by(
            db.deck_impressions_table.c.card_index)).mappings())
    for old, saved in zip(expected, actual):
        assert db.load_deck_diagnostics(old["impression_id"], "u") == json.loads(old["features_json"])
        assert db.load_deck_diagnostics(old["impression_id"], "another-user") is None
        for key in old:
            if key != "features_json":
                assert old[key] == saved[key]


def test_structured_late_insert_failure_rolls_back_snapshots_and_impressions(engine, monkeypatch):
    monkeypatch.setattr(db, "DECK_IMPRESSION_INSERT_ROWS", 5)
    rows = structured_rows(12)
    rows[-1]["impression_id"] = rows[0]["impression_id"]
    with pytest.raises(IntegrityError):
        db.save_deck_impressions(rows)
    with engine.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(db.deck_impressions_table)) == 0
        assert conn.scalar(select(func.count()).select_from(db.deck_diagnostic_snapshots_table)) == 0


@pytest.fixture
def logger(monkeypatch, engine):
    from backend import server
    monkeypatch.setattr(server, "load_board_state", lambda *a: (2, None))
    monkeypatch.setattr(server, "_deck_fatigue_enabled", lambda: False)
    monkeypatch.setattr(server, "_deck_taste_enabled", lambda: False)
    monkeypatch.setattr(server, "FLAGS", SimpleNamespace(trade_breaker=False))
    monkeypatch.setattr(server, "save_deck_impressions", db.save_deck_impressions)
    return server


def cards(count):
    return [SimpleNamespace(give_player_ids=[f"give-{i}"], receive_player_ids=[f"receive-{i}"],
                            target_user_id="p", give_value=100., receive_value=100., fairness_score=1.,
                            composite_score=float(count - i)) for i in range(count)]


def log(server, cards, **kwargs):
    return server._log_deck_signal_impressions(user_id="u", league_id="l", job_id="j",
        cards=cards, players_dict={}, capture=None, scoring_format="1qb_ppr", **kwargs)


def test_logger_first30_then100_committed_callbacks_and_one_context(logger, engine, monkeypatch):
    deck = cards(135)
    board_reads = []
    monkeypatch.setattr(logger, "load_board_state", lambda *a: (board_reads.append(1) or 2, None))
    batches = []

    def committed(batch, mapping):
        with engine.connect() as conn:
            durable = set(conn.execute(select(db.deck_impressions_table.c.impression_id)).scalars())
        assert set(mapping.values()) <= durable
        assert set(mapping) == {id(card) for card in batch}
        batches.append(len(batch))

    result = log(logger, deck, structured_features=True, initial_publication_batch_size=30,
                 publication_batch_size=100, on_batch_committed=committed)
    assert batches == [30, 100, 5]
    assert len(board_reads) == 1
    assert set(result) == {id(card) for card in deck}
    with engine.connect() as conn:
        assert list(conn.execute(select(db.deck_impressions_table.c.card_index).order_by(
            db.deck_impressions_table.c.card_index)).scalars()) == list(range(135))


def test_logger_failure_has_no_uncommitted_callback(logger, engine, monkeypatch):
    calls = []
    original = db.save_deck_impressions

    def fail_second(rows):
        calls.append(len(rows))
        if len(calls) == 2:
            raise RuntimeError("injected evidence write failure")
        original(rows)

    monkeypatch.setattr(logger, "save_deck_impressions", fail_second)
    published = []
    with pytest.raises(RuntimeError, match="injected evidence"):
        log(logger, cards(8), structured_features=True, publication_batch_size=3,
            on_batch_committed=lambda batch, ids: published.append(len(batch)))
    assert published == [3]
    with engine.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(db.deck_impressions_table)) == 3


def test_logger_supersession_stops_following_batch(logger, engine):
    alive = [True]
    published = []

    def committed(batch, ids):
        published.append(len(batch))
        alive[0] = False

    with pytest.raises(RuntimeError, match="trade_job_not_live"):
        log(logger, cards(8), structured_features=True, publication_batch_size=3,
            on_batch_committed=committed, should_continue=lambda: alive[0])
    assert published == [3]
    with engine.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(db.deck_impressions_table)) == 3


def test_logger_liveness_checked_again_immediately_before_save(logger, engine, monkeypatch):
    alive = [True]

    def invalidate_during_assembly(value):
        alive[0] = False
        return 0

    monkeypatch.setattr(logger, "_signal_value_band", invalidate_during_assembly)
    with pytest.raises(RuntimeError, match="trade_job_not_live"):
        log(logger, cards(1), structured_features=True, publication_batch_size=1,
            should_continue=lambda: alive[0],
            on_batch_committed=lambda *args: pytest.fail("uncommitted publication"))
    with engine.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(db.deck_impressions_table)) == 0


def test_logger_ghost_only_batches_not_published(logger, engine):
    deck, ghosts = cards(2), cards(3)
    callbacks = []
    result = log(logger, deck, ghost_cards=list(enumerate(ghosts)), publication_batch_size=2,
                 structured_features=True, on_batch_committed=lambda batch, ids: callbacks.append(batch))
    assert callbacks == [deck]
    assert set(result) == {id(card) for card in deck}
    with engine.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(db.deck_impressions_table)) == 5
