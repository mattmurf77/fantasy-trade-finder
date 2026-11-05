"""F5 taste writes under concurrent outcomes (head-eng 2026-10-27).

Two swipes in flight at once each read the user's taste rows, then write. The
old write deleted its rows and inserted them again, so the second write either
replaced the first (SQLite) or failed on user_taste_pkey (Postgres: a
UniqueViolation the update logs and drops). Either way one update was lost.
`merge_user_taste_rows` writes a row read unchanged as computed and merges a
row written since the read (its weights plus the second reward) with an
upsert on the primary key.

Each test makes both outcomes read before either writes (a barrier in the
read). They run on a SQLite file, and on Postgres too when
FTF_TEST_POSTGRES_URL names a throwaway database.
"""

import json
import math
import os
import threading
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, text

import backend.database as db_module
import backend.taste_service as taste
import backend.trade_service as ts
from backend.database import (
    deck_impressions_table,
    load_user_taste,
    replace_user_taste_rows,
    user_taste_table,
)

ME = "user_me"
ATTRS = ["cpos:RB", "partner:user_opp", "shape:1x1"]
TABLES = [user_taste_table, deck_impressions_table]


@pytest.fixture(params=["sqlite", "postgres"])
def eng(request, tmp_path):
    if request.param == "sqlite":
        engine = create_engine(f"sqlite:///{tmp_path / 'taste.db'}",
                               connect_args={"check_same_thread": False, "timeout": 5})
    else:
        url = os.environ.get("FTF_TEST_POSTGRES_URL")
        if not url:
            pytest.skip("FTF_TEST_POSTGRES_URL is not set")
        engine = create_engine(url)
    db_module.metadata.drop_all(engine, tables=TABLES)
    db_module.metadata.create_all(engine, tables=TABLES)
    try:
        with patch.object(db_module, "engine", engine):
            yield engine
    finally:
        db_module.metadata.drop_all(engine, tables=TABLES)
        engine.dispose()


@pytest.fixture(autouse=True)
def _cfg_defaults():
    old_cfg = dict(ts._cfg)
    ts._cfg.clear()
    ts._cfg.update(ts._DEFAULT_CFG)
    try:
        yield
    finally:
        ts._cfg.clear()
        ts._cfg.update(old_cfg)


def _iso_ago(days=0.0):
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def _impression(engine, attrs=ATTRS) -> str:
    iid = uuid.uuid4().hex
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO deck_impressions "
            "(impression_id, user_id, league_id, deck_job_id, card_index, "
            " features_json, propensity, shape_bucket, served_at) "
            "VALUES (:iid, :uid, 'league_x', 'job-x', 0, :feat, 1.0, '1x1', :served)"
        ), {"iid": iid, "uid": ME, "feat": json.dumps({"taste_attrs": attrs}),
            "served": _iso_ago()})
    return iid


def _concurrently(monkeypatch, engine, *actions, ordered=False):
    """One outcome per action, on its own thread; every outcome reads the
    user's rows before any of them writes. `ordered`: they then write one at
    a time, in the order given."""
    real_read = taste.load_user_taste
    barrier = threading.Barrier(len(actions), timeout=10)
    done = [threading.Event() for _ in actions]
    turn = threading.local()

    def read_then_wait(user_id):
        rows = real_read(user_id)
        barrier.wait()
        if ordered and turn.i:
            done[turn.i - 1].wait(timeout=10)
        return rows

    def outcome(i, iid, action):
        turn.i = i
        try:
            taste.update_taste_from_outcome(iid, action)
        finally:
            done[i].set()

    monkeypatch.setattr(taste, "load_user_taste", read_then_wait)
    iids = [_impression(engine) for _ in actions]
    threads = [threading.Thread(target=outcome, args=(i, iid, action))
               for i, (iid, action) in enumerate(zip(iids, actions))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert not any(thread.is_alive() for thread in threads)
    monkeypatch.setattr(taste, "load_user_taste", real_read)


def _weights():
    return {r["attr"]: (r["w_short"], r["w_long"]) for r in load_user_taste(ME)}


def test_two_first_swipes_both_count(eng, monkeypatch, caplog):
    """Neither outcome saw a row: both insert. The second merges."""
    _concurrently(monkeypatch, eng, "like", "like")
    assert "taste update failed" not in caplog.text
    assert _weights() == {a: (pytest.approx(2.0), pytest.approx(2.0)) for a in ATTRS}


def test_two_swipes_on_existing_rows_both_count(eng, monkeypatch, caplog):
    """Both outcomes read the same 10-day-old rows. The first writes them
    decayed plus its reward; the second adds its reward to that."""
    replace_user_taste_rows(ME, {a: (3.0, 3.0, _iso_ago(days=10)) for a in ATTRS})
    _concurrently(monkeypatch, eng, "like", "like")
    assert "taste update failed" not in caplog.text
    short = 3.0 * math.exp(-10 / 21.0) + 2.0
    long_ = 3.0 * math.exp(-10 / 180.0) + 2.0
    assert _weights() == {a: (pytest.approx(short, rel=1e-4), pytest.approx(long_, rel=1e-4))
                          for a in ATTRS}


@pytest.mark.parametrize("order", [("like", "pass"), ("pass", "like")])
def test_a_pass_that_empties_a_row_still_merges_with_a_concurrent_like(eng, monkeypatch,
                                                                       caplog, order):
    """The pass alone takes 0.5 to 0, so it deletes the rows (GC on update).
    With a like in flight the result is 0.5 + 1 - 0.5 in either write order,
    and the rows stay: written first, the like is merged into; written
    second, it finds its rows gone and inserts its reward alone."""
    replace_user_taste_rows(ME, {a: (0.5, 0.5, _iso_ago()) for a in ATTRS})
    _concurrently(monkeypatch, eng, *order, ordered=True)
    assert "taste update failed" not in caplog.text
    assert _weights() == {a: (pytest.approx(1.0, abs=1e-4), pytest.approx(1.0, abs=1e-4))
                          for a in ATTRS}


def test_one_swipe_writes_as_before(eng):
    """No concurrency: a new row takes the reward, a read row its decayed
    weight plus the reward, and a row the reward empties is deleted."""
    replace_user_taste_rows(ME, {"cpos:RB": (3.0, 3.0, _iso_ago(days=10)),
                                 "shape:1x1": (0.5, 0.5, _iso_ago())})
    taste.update_taste_from_outcome(_impression(eng), "like")
    w = _weights()
    assert w["partner:user_opp"] == (pytest.approx(1.0), pytest.approx(1.0))
    assert w["cpos:RB"] == (pytest.approx(3.0 * math.exp(-10 / 21.0) + 1.0, rel=1e-4),
                            pytest.approx(3.0 * math.exp(-10 / 180.0) + 1.0, rel=1e-4))
    taste.update_taste_from_outcome(_impression(eng, ["shape:1x1"]), "pass")
    taste.update_taste_from_outcome(_impression(eng, ["shape:1x1"]), "pass")
    taste.update_taste_from_outcome(_impression(eng, ["shape:1x1"]), "pass")
    assert "shape:1x1" not in _weights()                   # 0.5 + 1 - 1.5: deleted
