"""E1 (gthread readiness) — RankingService is safe to share across threads.

Plan: docs/plans/e1-concurrency/scope.md; findings F1a/F1b in
docs/plans/org-bringup/e1-concurrency-audit.md. One RankingService is shared by
a session's request threads and its trade-job threads, so every public method
runs under the instance RLock (`_lock`) and the Elo/stats memo is stamped with
the version read at compute START.

  T1 test_concurrent_mutations_and_reads — 8 writers x 200 mixed
     record_ranking / record_trade_signal plus 4 readers looping
     get_rankings(None), get_rankings("QB") and comparison_counts(), all
     released by one Barrier. No exception, no lost `_version` /
     `_interactions` increment, and the final board equals a fresh service fed
     the shared service's own swipe logs in log order (Elo is order-dependent).
  T2 test_reader_cannot_stamp_half_applied_tiers — deterministic: a reader is
     parked inside _compute_elo (patched _pin_bounds) while a writer thread
     runs apply_tiers. The reader must never stamp the post-save version onto
     pre-save ratings, and the next read must show the tier save.

Sabotage record (run 2026-10-22, each applied, observed red, reverted green):
  T1  lock -> contextlib.nullcontext() in RankingService.__init__  -> RED in
      18 of 20 rounds (lost `_interactions` increments), so 5 rounds are red
      on every run observed (5/5).
  T2  lock -> nullcontext AND store-time stamp in _compute_elo     -> RED 3/3
      (cache stamped post-save holding the pre-save q1 Elo).
  T2  lock -> nullcontext only (start-stamp kept)                  -> green:
      the start stamp alone closes F1b, as designed. Store-time stamp with
      the lock kept is green too (the writer waits for the reader).
Race fixture: sys.setswitchinterval(1e-6), restored afterwards. Hermetic: no
DB, no network, no server import.
"""
import random
import sys
import threading

import pytest

from backend.ranking_service import Player, RankingService

QBS = [f"q{i}" for i in range(1, 7)]
RBS = [f"r{i}" for i in range(1, 7)]
# Mid-band consensus seeds (tier_config.json, 1qb_ppr: second 1370-1575,
# first_1 1580-1785), so trade feedback has room to move every player.
SEED = {pid: 1420.0 + 23.0 * i for i, pid in enumerate(QBS + RBS)}

WRITERS, OPS_PER_WRITER, READERS = 8, 200, 4
# One round goes red under the nullcontext sabotage only ~60% of the time
# (lost `+=` increments need an unlucky switch), so the race repeats.
ROUNDS = 5
JOIN_S = 60


@pytest.fixture
def fast_switch():
    old = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)
    try:
        yield
    finally:
        sys.setswitchinterval(old)


def _pool():
    return ([Player(id=p, name=p.upper(), position="QB", team="AAA", age=25) for p in QBS]
            + [Player(id=p, name=p.upper(), position="RB", team="BBB", age=24) for p in RBS])


def _svc():
    svc = RankingService(players=_pool(), seed_ratings=dict(SEED))
    svc._scoring_format = "1qb_ppr"
    return svc


def _board(svc, position=None):
    return {rp.player.id: rp.elo for rp in svc.get_rankings(position=position).rankings}


@pytest.mark.parametrize("round_no", range(ROUNDS))
def test_concurrent_mutations_and_reads(fast_switch, round_no):
    svc = _svc()
    v0 = svc._version
    start = threading.Barrier(WRITERS + READERS)
    writers_done = threading.Event()
    errors: list = []
    rank_calls = [0] * WRITERS

    def writer(w):
        rng = random.Random(round_no * 100 + w)
        try:
            start.wait(timeout=10)
            for _ in range(OPS_PER_WRITER):
                if rng.random() < 0.5:
                    svc.record_ranking(rng.sample(rng.choice((QBS, RBS)), 3))
                    rank_calls[w] += 1
                else:
                    svc.record_trade_signal(
                        winner_ids=rng.sample(QBS + RBS, rng.randint(1, 2)),
                        loser_ids=rng.sample(QBS + RBS, rng.randint(1, 2)),
                        decision=rng.choice(("like", "pass")))
        except BaseException as exc:          # noqa: BLE001 — surfaced below
            errors.append(("writer", w, repr(exc)))

    def reader(r):
        try:
            start.wait(timeout=10)
            while not writers_done.is_set():
                _board(svc)
                _board(svc, "QB")
                svc.comparison_counts()
        except BaseException as exc:          # noqa: BLE001
            errors.append(("reader", r, repr(exc)))

    ws = [threading.Thread(target=writer, args=(i,)) for i in range(WRITERS)]
    rs = [threading.Thread(target=reader, args=(i,)) for i in range(READERS)]
    for t in ws + rs:
        t.start()
    for t in ws:
        t.join(timeout=JOIN_S)
    writers_done.set()
    for t in rs:
        t.join(timeout=JOIN_S)
    assert not any(t.is_alive() for t in ws + rs), "thread did not finish"

    assert errors == []
    assert svc._version == v0 + WRITERS * OPS_PER_WRITER
    assert svc._interactions[None] == sum(rank_calls)
    assert len(svc._swipes) == 3 * sum(rank_calls)

    # Replay the shared service's OWN logs, in log order, into a fresh service.
    fresh = _svc()
    fresh._swipes = list(svc._swipes)
    fresh._trade_swipes = list(svc._trade_swipes)
    assert _board(svc) == _board(fresh)


def test_reader_cannot_stamp_half_applied_tiers():
    svc = _svc()
    tiers = {"firsts_2": ["q1"], "third": ["q6"]}        # pins 1864 / 1365
    in_compute, release = threading.Event(), threading.Event()
    writer_started = threading.Event()
    errors: list = []
    reader_ident: dict = {}
    original = svc._pin_bounds

    def parked_pin_bounds(pool_ids, released):
        # Ratings are already seeded from the (pre-save) overrides when
        # _compute_elo reaches this call; park the reader right here once.
        if threading.get_ident() == reader_ident.get("id") and not in_compute.is_set():
            in_compute.set()
            if not release.wait(timeout=10):
                raise AssertionError("reader was never released")
        return original(pool_ids, released)

    svc._pin_bounds = parked_pin_bounds

    def reader():
        reader_ident["id"] = threading.get_ident()
        try:
            svc.get_rankings(position="QB")
        except BaseException as exc:          # noqa: BLE001
            errors.append(("reader", repr(exc)))

    def writer():
        writer_started.set()
        try:
            svc.apply_tiers(position="QB", tiers=tiers, scoring_format="1qb_ppr")
        except BaseException as exc:          # noqa: BLE001
            errors.append(("writer", repr(exc)))

    rt = threading.Thread(target=reader)
    wt = threading.Thread(target=writer)
    rt.start()
    assert in_compute.wait(timeout=10), "reader never reached _compute_elo"
    wt.start()
    assert writer_started.wait(timeout=10)
    # With the lock the writer stays blocked behind the parked reader; without
    # it, this window lets apply_tiers finish mid-compute (the F1b race).
    wt.join(timeout=0.3)
    release.set()
    rt.join(timeout=10)
    wt.join(timeout=10)
    assert not rt.is_alive() and not wt.is_alive(), "thread did not finish"
    assert errors == []

    # Never the post-save version over pre-save data.
    if svc._elo_cache_version == svc._version:
        assert svc._elo_cache["q1"] == svc._elo_overrides["q1"]
        assert svc._elo_cache["q6"] == svc._elo_overrides["q6"]
    board = _board(svc, "QB")
    assert board["q1"] == 1864.0 and board["q6"] == 1365.0
