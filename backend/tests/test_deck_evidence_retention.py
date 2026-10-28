"""Deck-evidence retention (head-eng 2026-10-28; dark until a bound is set).

purge_deck_evidence deletes, one bounded batch per cleanup tick, the evidence
of decks first delivered more than `deck_evidence_retention_days` ago: the
pack, the deck_impressions rows, the withdrawals and the candidate set, each
deck in its own transaction. Outcomes stay. It does nothing at 0 (the
default), under the 56-day floor, or before the date floor
(`deck_evidence_keep_until_epoch`, 2027-01-01 by default).

Covers: off by default; the floor and the date floor; packed and pack-less
decks deleted across every evidence table, a recent deck and every outcome
kept; the batch bound; a deck whose delete fails left for the next tick; the
loop step's knobs; the index (declared, and created on an existing DB).
"""
import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, func, insert, select, text

import backend.database as db_module
import backend.server as server
from backend.database import (
    deck_candidate_sets_table, deck_card_withdrawals_table, deck_evidence_packs_table,
    deck_impressions_table, deck_outcomes_table, metadata)
from backend.tests.test_eval_pack_reader import _card, _row

NOW = datetime(2027, 3, 1, tzinfo=timezone.utc)


def iso(days_ago):
    return (NOW - timedelta(days=days_ago)).isoformat()


@pytest.fixture()
def db(monkeypatch):
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    metadata.create_all(engine)
    monkeypatch.setattr(db_module, "engine", engine)
    return engine


def deck(engine, job, days_ago, *, packed=True, n=3, user="u1", league="lg"):
    """A deck first delivered `days_ago` days before NOW: n full rows, a ghost
    row, a withdrawal, a candidate set, an outcome and (packed) a pack row."""
    served = iso(days_ago)
    rows = [_row({**_card(job, i, served_at=served, user=user), "league_id": league})
            for i in range(n)]
    rows.append(_row({**_card(job, n, served_at=served, user=user), "league_id": league},
                     ghost=True))
    with engine.begin() as conn:
        conn.execute(insert(deck_impressions_table), rows)
        conn.execute(insert(deck_card_withdrawals_table).values(
            deck_job_id=job, card_index=n + 1, user_id=user, league_id=league,
            reason="disposition_cut", first_withdrawn_at=served, served_before=0,
            impression_id=f"{job}:{n + 1}"))
        conn.execute(insert(deck_candidate_sets_table).values(
            candidate_set_id=f"cs-{job}", deck_job_id=job, user_id=user, league_id=league,
            size=n, set_hash="h" * 16, candidates_json="[]", created_at=served))
        conn.execute(insert(deck_outcomes_table).values(
            impression_id=rows[0]["impression_id"], action="viewed", acted_at=served))
        if packed:
            conn.execute(insert(deck_evidence_packs_table).values(
                run_id=job, user_id=user, league_id=league, served_at=served, pack_version=1,
                header_json=json.dumps({"run": {}}), cards_blob=b"x", checksum="c" * 64,
                card_count=n, created_at=served))


def counts(engine, job):
    with engine.connect() as conn:
        return {
            "imp": conn.execute(select(func.count()).select_from(deck_impressions_table)
                                .where(deck_impressions_table.c.deck_job_id == job)).scalar(),
            "wd": conn.execute(select(func.count()).select_from(deck_card_withdrawals_table)
                               .where(deck_card_withdrawals_table.c.deck_job_id == job)).scalar(),
            "cs": conn.execute(select(func.count()).select_from(deck_candidate_sets_table)
                               .where(deck_candidate_sets_table.c.deck_job_id == job)).scalar(),
            "pack": conn.execute(select(func.count()).select_from(deck_evidence_packs_table)
                                 .where(deck_evidence_packs_table.c.run_id == job)).scalar(),
        }


def outcomes(engine):
    with engine.connect() as conn:
        return conn.execute(select(func.count()).select_from(deck_outcomes_table)).scalar()


GONE = {"imp": 0, "wd": 0, "cs": 0, "pack": 0}


def purge(**kw):
    return db_module.purge_deck_evidence(now=NOW, **{"keep_until_epoch": 0.0, **kw})


@pytest.mark.parametrize("days", [0, 0.0, None])
def test_off_deletes_nothing(db, days):
    deck(db, "old", 400)
    assert purge(days=days) == {} and counts(db, "old")["imp"] == 4


def test_a_bound_under_the_floor_is_refused_and_logged(db, caplog):
    deck(db, "old", 400)
    with caplog.at_level("WARNING"):
        assert purge(days=30) == {}
    assert counts(db, "old")["imp"] == 4
    assert any("under the 56-day floor" in r.getMessage() for r in caplog.records)


def test_nothing_is_deleted_before_the_date_floor(db):
    deck(db, "old", 400)
    assert purge(days=90, keep_until_epoch=NOW.timestamp() + 1) == {}
    assert counts(db, "old")["imp"] == 4


def test_old_decks_go_from_every_evidence_table_and_recent_ones_and_outcomes_stay(db):
    deck(db, "packed", 120)
    deck(db, "rows-only", 100, packed=False)
    deck(db, "recent", 30)
    got = purge(days=90)
    assert counts(db, "packed") == counts(db, "rows-only") == GONE
    assert counts(db, "recent") == {"imp": 4, "wd": 1, "cs": 1, "pack": 1}
    assert outcomes(db) == 3                                   # the user's own actions stay
    assert got == {"deck_impressions": 8, "deck_card_withdrawals": 2,
                   "deck_candidate_sets": 2, "deck_evidence_packs": 1, "decks": 2}


def test_the_bound_is_the_first_delivery(db):
    """A deck exactly at the bound stays; one a day past it goes."""
    deck(db, "at", 90)
    deck(db, "past", 91)
    purge(days=90.5)
    assert counts(db, "at")["imp"] == 4 and counts(db, "past") == GONE


def test_one_bounded_batch_per_call(db):
    for k in range(3):
        deck(db, f"d{k}", 200 + k, packed=k != 1)
    assert purge(days=90, batch_decks=2)["decks"] == 2
    left = [j for j in ("d0", "d1", "d2") if counts(db, j)["imp"]]
    assert len(left) == 1
    assert purge(days=90, batch_decks=2)["decks"] == 1
    assert purge(days=90, batch_decks=2) == {}


def test_a_deck_whose_delete_fails_is_left_whole_for_the_next_tick(db, monkeypatch, caplog):
    """Each deck is its own transaction: one failing never takes another with
    it, and never leaves a deck half deleted."""
    deck(db, "bad", 200)
    deck(db, "good", 210)
    real_begin = db.begin
    state = {"n": 0}

    class Boom:
        def __enter__(self):
            raise RuntimeError("db down")

        def __exit__(self, *exc):
            return False

    def begin():
        state["n"] += 1
        return Boom() if state["n"] == 1 else real_begin()
    monkeypatch.setattr(db, "begin", begin)
    with caplog.at_level("WARNING"):
        got = purge(days=90)
    assert got["decks"] == 2 and got["deck_impressions"] == 4
    whole = [j for j in ("bad", "good") if counts(db, j) == {"imp": 4, "wd": 1, "cs": 1, "pack": 1}]
    gone = [j for j in ("bad", "good") if counts(db, j) == GONE]
    assert len(whole) == len(gone) == 1
    assert any("retried next tick" in r.getMessage() for r in caplog.records)


def test_the_loop_step_reads_both_knobs(monkeypatch):
    seen = {}
    monkeypatch.setattr(db_module, "purge_deck_evidence",
                        lambda **kw: seen.update(kw) or {"decks": 1})
    monkeypatch.setitem(server._trade_service_mod._cfg, "deck_evidence_retention_days", 90.0)
    monkeypatch.setitem(server._trade_service_mod._cfg, "deck_evidence_keep_until_epoch", 5.0)
    assert server._prune_deck_evidence() == {"decks": 1}
    assert seen == {"days": 90.0, "keep_until_epoch": 5.0}


def test_the_loop_step_defaults_off_and_to_the_2027_floor(monkeypatch):
    seen = {}
    monkeypatch.setattr(db_module, "purge_deck_evidence", lambda **kw: seen.update(kw) or {})
    for key in ("deck_evidence_retention_days", "deck_evidence_keep_until_epoch"):
        monkeypatch.delitem(server._trade_service_mod._cfg, key, raising=False)
    server._prune_deck_evidence()
    assert seen == {"days": 0.0, "keep_until_epoch": 1798761600.0}
    assert datetime.fromtimestamp(1798761600, tz=timezone.utc).isoformat() == \
        "2027-01-01T00:00:00+00:00"
    defaults = {k: v for k, v, _d in db_module._MODEL_CONFIG_DEFAULTS}
    assert defaults["deck_evidence_retention_days"] == 0.0
    assert defaults["deck_evidence_keep_until_epoch"] == 1798761600.0


def test_the_loop_step_never_raises(monkeypatch, caplog):
    monkeypatch.setattr(db_module, "purge_deck_evidence",
                        lambda **kw: (_ for _ in ()).throw(RuntimeError("db")))
    with caplog.at_level("ERROR"):
        assert server._prune_deck_evidence() == {}
    assert any("deck-evidence retention failed" in r.getMessage() for r in caplog.records)


def test_the_cleanup_loop_runs_the_step():
    import inspect
    assert "_prune_deck_evidence()" in inspect.getsource(server._cleanup_loop)


def test_pack_less_decks_wait_for_the_index_and_packed_ones_never_do(db, monkeypatch, caplog):
    """The index is built off the boot path: until it exists the pack-less scan
    would read the whole table, so those decks wait (logged once)."""
    monkeypatch.setattr(db_module, "_served_index_ready", False)
    monkeypatch.setattr(db_module, "_served_index_warned", False)
    with db.begin() as conn:
        conn.execute(text("DROP INDEX ix_deck_impressions_served"))
    deck(db, "packed", 120)
    deck(db, "rows-only", 100, packed=False)
    with caplog.at_level("WARNING"):
        purge(days=90)
        purge(days=90)
    assert counts(db, "packed") == GONE and counts(db, "rows-only")["imp"] == 4
    assert sum("wait for ix_deck_impressions_served" in r.getMessage()
               for r in caplog.records) == 1
    with db.begin() as conn:
        conn.execute(text("CREATE INDEX ix_deck_impressions_served ON deck_impressions (served_at)"))
    purge(days=90)
    assert counts(db, "rows-only") == GONE


def test_the_index_is_declared_and_never_built_at_boot(tmp_path, monkeypatch):
    """A fresh DB gets it from the declaration; init_db never builds it on an
    existing table (prod: a plain CREATE INDEX there blocks writes for a full
    scan and can outlast the boot timeout)."""
    assert "ix_deck_impressions_served" in {ix.name for ix in deck_impressions_table.indexes}
    engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    deck_impressions_table.create(engine)                 # the table as it is today ...
    with engine.begin() as conn:                          # ... from before the index
        conn.execute(text("DROP INDEX ix_deck_impressions_served"))
    monkeypatch.setattr(db_module, "engine", engine)
    db_module.init_db()
    with engine.connect() as conn:
        got = [r[1] for r in conn.execute(text("PRAGMA index_list('deck_impressions')"))]
    assert "ix_deck_impressions_served" not in got


def test_the_script_builds_it_on_an_existing_table_and_check_writes_nothing(tmp_path, monkeypatch):
    import importlib.util
    from pathlib import Path
    path = Path(__file__).resolve().parents[2] / "scripts/create_evidence_retention_index.py"
    spec = importlib.util.spec_from_file_location("create_evidence_retention_index", path)
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    deck_impressions_table.create(engine)                 # the table as it is today ...
    with engine.begin() as conn:                          # ... from before the index
        conn.execute(text("DROP INDEX ix_deck_impressions_served"))
    monkeypatch.setattr(db_module, "engine", engine)
    assert script.main(["--check"]) == 0 and script.state(engine) == "missing"
    assert script.main([]) == 0 and script.state(engine) == "valid"
    assert script.build(engine) == "valid"                # idempotent
