"""#537: the diagnostics drain, ported from release-lead's QA (qa537 tools,
2026-10-29; QA also ran the correctness half on Postgres 18 in 3 collations).

Exact deletion at the cutoff, the 20 x 500 ceiling oldest-first, a short batch
ending the call, one transaction per batch, and one real cleanup-loop tick.
"""
import logging
import time as _time
import types
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, event, func, insert, select
from sqlalchemy.exc import IntegrityError

from backend import database as db

D = db.deck_diagnostic_snapshots_table
NOW = datetime(2026, 10, 29, 12, 0, 0, 123456, tzinfo=timezone.utc)
CUTOFF = NOW - timedelta(days=14)          # 2026-10-15T12:00:00.123456+00:00


class _Frozen(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW if tz is not None else NOW.replace(tzinfo=None)


@pytest.fixture
def eng(monkeypatch, tmp_path):
    e = create_engine(f"sqlite:///{tmp_path}/qa.db")
    db.metadata.create_all(e, tables=[D])
    monkeypatch.setattr(db, "engine", e)
    monkeypatch.setattr(db, "datetime", _Frozen)
    yield e
    e.dispose()


def put(e, stamps, prefix="s", payload="{}"):
    rows = [dict(snapshot_id=f"{prefix}{i:07d}", user_id="u", deck_job_id="j",
                 created_at=s, payload_json=payload) for i, s in enumerate(stamps)]
    with e.begin() as c:
        for k in range(0, len(rows), 1000):
            c.execute(insert(D), rows[k:k + 1000])
    return [r["snapshot_id"] for r in rows]


def left(e):
    with e.connect() as c:
        return dict(c.execute(select(D.c.snapshot_id, D.c.created_at)).all())


def iso(dt):
    return dt.isoformat()


def _counting(e):
    """(reads, deletes) lists that fill as the purge runs."""
    reads, deletes = [], []

    def cur(conn, cursor, stmt, *a):
        s = stmt.lstrip().upper()
        if "DECK_DIAGNOSTIC_SNAPSHOTS" in s:
            (reads if s.startswith("SELECT") else deletes if s.startswith("DELETE") else []).append(1)
    event.listen(e, "before_cursor_execute", cur)
    return reads, deletes, lambda: event.remove(e, "before_cursor_execute", cur)


def test_boundary_exact(eng):
    us = timedelta(microseconds=1)
    cases = {  # snapshot -> (created_at, should_delete)
        "older_by_1us": (iso(CUTOFF - us), True),
        "equal": (iso(CUTOFF), False),
        "younger_by_1us": (iso(CUTOFF + us), False),
        "older_1d": (iso(CUTOFF - timedelta(days=1)), True),
        "13d": (iso(NOW - timedelta(days=13)), False),
        "fresh": (iso(NOW), False),
        "future_1d": (iso(NOW + timedelta(days=1)), False),
        "future_10y": (iso(NOW + timedelta(days=3650)), False),
        "old_1y": (iso(NOW - timedelta(days=365)), True),
        # no-fraction isoformat (microsecond == 0) on both sides of the cutoff
        "nofrac_older": (iso((CUTOFF - timedelta(seconds=1)).replace(microsecond=0)), True),
        "nofrac_same_second": (iso(CUTOFF.replace(microsecond=0)), True),   # 12:00:00 < .123456
        "nofrac_younger": (iso((CUTOFF + timedelta(seconds=1)).replace(microsecond=0)), False),
        # Z suffix
        "z_older_1h": ((CUTOFF - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ"), True),
        "z_younger_1h": ((CUTOFF + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ"), False),
        # naive 'T' (no offset)
        "naiveT_older_1h": ((CUTOFF - timedelta(hours=1)).replace(tzinfo=None).isoformat(), True),
        "naiveT_younger_1h": ((CUTOFF + timedelta(hours=1)).replace(tzinfo=None).isoformat(), False),
        # naive space-separated (str(datetime) / SQL CURRENT_TIMESTAMP shape)
        "space_older_1d": (str((CUTOFF - timedelta(days=1)).replace(tzinfo=None)), True),
        "space_younger_1d": (str((CUTOFF + timedelta(days=1)).replace(tzinfo=None)), False),
    }
    with eng.begin() as c:
        for name, (stamp, _) in cases.items():
            c.execute(insert(D).values(snapshot_id=name, user_id="u", deck_job_id="j",
                                       created_at=stamp, payload_json="{}"))
    n = db.purge_deck_diagnostics(days=14, batch_size=500, max_batches=20)
    remaining = left(eng)
    assert not {k: v for k, v in cases.items() if (k in remaining) == v[1]}
    assert n == sum(1 for v in cases.values() if v[1])


def test_null_created_at_is_rejected_by_schema(eng):
    with pytest.raises(IntegrityError):
        with eng.begin() as c:
            c.execute(insert(D).values(snapshot_id="n", user_id="u", deck_job_id="j",
                                       created_at=None, payload_json="{}"))


def test_ceiling_20x500_oldest_first_and_fresh_untouched(eng):
    # 12,500 expired, spread over 20 days past the cutoff; 3,000 fresh
    exp_ids = put(eng, [iso(CUTOFF - timedelta(seconds=1 + i * 137)) for i in range(12500)], "e")
    fresh_ids = put(eng, [iso(CUTOFF + timedelta(seconds=1 + i * 97)) for i in range(3000)], "f",
                    payload='{"keep": true}')
    with eng.connect() as c:
        before_fresh = c.execute(select(D).where(D.c.snapshot_id.like("f%"))
                                 .order_by(D.c.snapshot_id)).all()
    commits = []
    event.listen(eng, "commit", lambda conn: commits.append(1))
    reads, deletes, stop = _counting(eng)
    assert db.purge_deck_diagnostics(days=14, batch_size=500, max_batches=20) == 10000
    stop()
    assert (len(reads), len(deletes), len(commits)) == (20, 20, 20)
    # i grows -> older, so the survivors are the 2,500 youngest expired (i < 2500)
    assert {k for k in left(eng) if k.startswith("e")} == set(exp_ids[:2500])
    # second call: 5 full batches, then a short (empty) read
    reads, deletes, stop = _counting(eng)
    assert db.purge_deck_diagnostics(days=14, batch_size=500, max_batches=20) == 2500
    stop()
    assert (len(reads), len(deletes)) == (6, 5)
    # third call: nothing, one read
    reads, deletes, stop = _counting(eng)
    assert db.purge_deck_diagnostics(days=14, batch_size=500, max_batches=20) == 0
    stop()
    assert (len(reads), len(deletes)) == (1, 0)
    with eng.connect() as c:
        after_fresh = c.execute(select(D).where(D.c.snapshot_id.like("f%"))
                                .order_by(D.c.snapshot_id)).all()
    assert after_fresh == before_fresh and len(after_fresh) == 3000
    assert set(left(eng)) == set(fresh_ids)


def test_a_short_batch_stops_the_call(eng):
    put(eng, [iso(CUTOFF - timedelta(minutes=i + 1)) for i in range(1250)])
    reads, _deletes, stop = _counting(eng)
    assert db.purge_deck_diagnostics(days=14, batch_size=500, max_batches=20) == 1250
    stop()
    assert len(reads) == 3   # 500, 500, 250 (short): stop, never a 4th read


def test_each_batch_is_its_own_transaction_and_a_failure_logs_what_went(eng, caplog):
    """A failure in batch 3 leaves batches 1-2 committed, and says so."""
    put(eng, [iso(CUTOFF - timedelta(minutes=i + 1)) for i in range(2000)])
    seen = []

    def cur(conn, cursor, stmt, *a):
        if stmt.lstrip().upper().startswith("DELETE") and "deck_diagnostic_snapshots" in stmt:
            seen.append(1)
            if len(seen) == 3:
                raise RuntimeError("qa537: batch 3 fails")
    event.listen(eng, "before_cursor_execute", cur)
    with caplog.at_level(logging.WARNING), pytest.raises(RuntimeError, match="batch 3 fails"):
        db.purge_deck_diagnostics(days=14, batch_size=500, max_batches=20)
    event.remove(eng, "before_cursor_execute", cur)
    assert len(left(eng)) == 1000
    assert [r.getMessage() for r in caplog.records if "deck diagnostics purge" in r.getMessage()] \
        == ["deck diagnostics purge: 1000 expired snapshots deleted before a batch failed"]


def test_default_is_one_batch(eng):
    put(eng, [iso(CUTOFF - timedelta(minutes=i + 1)) for i in range(1200)])
    assert db.purge_deck_diagnostics(days=14) == 500
    assert db.purge_deck_diagnostics(days=14, batch_size=5000, max_batches=1) == 700  # capped at 1000


def test_degenerate_args(eng):
    put(eng, [iso(CUTOFF - timedelta(minutes=i + 1)) for i in range(30)])
    assert db.purge_deck_diagnostics(days=0, max_batches=20) == 0
    assert db.purge_deck_diagnostics(days=-1, max_batches=20) == 0
    assert db.purge_deck_diagnostics(days=14, batch_size=10, max_batches=0) == 10   # max(1, 0)
    assert db.purge_deck_diagnostics(days=14, batch_size=0, max_batches=3) == 3     # size max(1, 0)
    assert len(left(eng)) == 17


# ── One real _cleanup_loop tick (the suite's conftest disables the thread) ──

class _Stop(BaseException):
    pass


@pytest.fixture
def loop_eng(monkeypatch, tmp_path):
    e = create_engine(f"sqlite:///{tmp_path}/loop.db")
    db.metadata.create_all(e)
    monkeypatch.setattr(db, "engine", e)
    yield e
    e.dispose()


def _seed_now(e, n_expired, n_fresh):
    now = datetime.now(timezone.utc)
    put(e, [(now - timedelta(days=15, seconds=i)).isoformat() for i in range(n_expired)], "e")
    put(e, [(now - timedelta(days=13, seconds=i)).isoformat() for i in range(n_fresh)], "f")


def _quiet(server, monkeypatch):
    from backend import prepared_trade_runtime
    monkeypatch.setattr(prepared_trade_runtime, "tick", lambda *a, **k: None)
    monkeypatch.setattr(server, "_evict_trade_page_store", lambda *a, **k: None)
    monkeypatch.setattr(server, "_drop_stale_deck_evidence", lambda *a, **k: None)
    monkeypatch.setattr(server, "purge_stale_persisted_sessions", lambda *a, **k: 0)
    monkeypatch.setattr(server._api_obs, "purge_observability_events", lambda *a, **k: 0)
    monkeypatch.delenv("FTF_DECK_DIAGNOSTIC_RETENTION_DAYS", raising=False)


def _tick(server, monkeypatch, ticks):
    calls = {"n": 0}

    def sleep(_s):
        calls["n"] += 1
        if calls["n"] > ticks:
            raise _Stop()
    monkeypatch.setattr(server, "time", types.SimpleNamespace(
        sleep=sleep, time=_time.time, monotonic=_time.monotonic))
    with pytest.raises(_Stop):
        server._cleanup_loop()


def _diag_lines(caplog):
    return [r.getMessage() for r in caplog.records if "deck diagnostic" in r.getMessage()]


def test_one_tick_drains_10000_and_logs_the_ceiling(loop_eng, monkeypatch, caplog):
    import backend.server as server
    _quiet(server, monkeypatch)
    monkeypatch.setattr(server, "_retire_deck_evidence", lambda *a, **k: None)
    _seed_now(loop_eng, 12500, 700)
    caplog.set_level(logging.INFO, logger="trade_finder")
    _tick(server, monkeypatch, 1)
    assert _diag_lines(caplog) == [
        "Purged 10000 expired deck diagnostic snapshots (the tick's ceiling: more may remain)"]
    caplog.clear()
    _tick(server, monkeypatch, 1)
    assert _diag_lines(caplog) == ["Purged 2500 expired deck diagnostic snapshots"]
    caplog.clear()
    _tick(server, monkeypatch, 1)
    assert _diag_lines(caplog) == []
    with loop_eng.connect() as c:
        assert c.scalar(select(func.count()).select_from(D)) == 700


def test_exactly_the_ceiling_says_more_may_remain_not_that_it_does(loop_eng, monkeypatch, caplog):
    """release-lead's #537 P3-3: exactly 10,000 expired rows fill the ceiling
    with nothing left, so the line can't claim a backlog."""
    import backend.server as server
    _quiet(server, monkeypatch)
    monkeypatch.setattr(server, "_retire_deck_evidence", lambda *a, **k: None)
    _seed_now(loop_eng, 10000, 0)
    caplog.set_level(logging.INFO, logger="trade_finder")
    _tick(server, monkeypatch, 1)
    assert _diag_lines(caplog) == [
        "Purged 10000 expired deck diagnostic snapshots (the tick's ceiling: more may remain)"]
    with loop_eng.connect() as c:
        assert c.scalar(select(func.count()).select_from(D)) == 0


def test_a_failing_purge_never_stops_the_loop(loop_eng, monkeypatch, caplog):
    import backend.server as server
    _quiet(server, monkeypatch)
    retired = []
    monkeypatch.setattr(server, "_retire_deck_evidence", lambda *a, **k: retired.append(1))

    def boom(**k):
        raise RuntimeError("qa537 purge down")
    monkeypatch.setattr(db, "purge_deck_diagnostics", boom)
    caplog.set_level(logging.INFO, logger="trade_finder")
    _tick(server, monkeypatch, 2)
    assert sum("deck-diagnostic retention failed" in r.getMessage() for r in caplog.records) == 2
    assert retired == [1, 1]   # the rest of each tick still ran
