"""E1 (gthread readiness) — shared module/service dicts survive concurrent use.

Plan: docs/plans/e1-concurrency/scope.md; findings F2/F6/F7 in
docs/plans/org-bringup/e1-concurrency-audit.md. Each guarded site used to
iterate a live dict in Python while another thread inserted into it (or two
threads deleted the same key), which raises under real threads.

  T5a _rookie_player_ids across _bump_pool_generation()    (F6: list + pop)
  T5b _league_members_cached vs _invalidate_league_members_cache (F7: list)
  T5c TradeService.get_pending_trades / get_liked_trades while other threads
      insert into _trade_cards                              (F2: list(values))

Each case asserts no exception from any thread. The DB loaders are replaced by
in-memory fakes, so nothing touches a database or the network.

Sabotage record (run 2026-10-22; each one-liner reverted to its pre-E1 text,
observed red, restored green):
  F6 -> T5a RED 4/4, F7 -> T5b RED 4/4, F2 -> T5c RED 3/3 (each run raised
  RuntimeError: dictionary changed size during iteration).
Race fixture: sys.setswitchinterval(1e-6), restored afterwards.
"""
import sys
import threading

import pytest

import backend.server as server
from backend.trade_service import TradeCard, TradeService

THREADS, LOOPS, JOIN_S = 6, 400, 60


@pytest.fixture
def fast_switch():
    old = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)
    try:
        yield
    finally:
        sys.setswitchinterval(old)


def _race(*targets):
    """Run each target in its own thread behind one Barrier; return errors."""
    start = threading.Barrier(len(targets))
    errors: list = []

    def run(fn):
        try:
            start.wait(timeout=10)
            fn()
        except BaseException as exc:          # noqa: BLE001 — surfaced below
            errors.append(repr(exc))

    threads = [threading.Thread(target=run, args=(fn,)) for fn in targets]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=JOIN_S)
    assert not any(t.is_alive() for t in threads), "thread did not finish"
    return errors


def test_rookie_ids_memo_survives_generation_bumps(fast_switch, monkeypatch):
    monkeypatch.setattr(server, "_rookie_ids_memo", {})
    monkeypatch.setattr(server, "_pool_generation", server._pool_generation)
    monkeypatch.setattr(server, "load_rookie_player_ids", lambda season: {f"rk{season}"})

    def reader(offset):
        def go():
            for i in range(LOOPS):
                assert server._rookie_player_ids(2000 + (offset + i) % 150) == \
                    {f"rk{2000 + (offset + i) % 150}"}
        return go

    def bumper():
        for _ in range(LOOPS // 4):
            server._bump_pool_generation()

    assert _race(*[reader(k * 25) for k in range(THREADS)], bumper) == []


def test_league_members_cache_survives_invalidation(fast_switch, monkeypatch):
    monkeypatch.setattr(server, "_LEAGUE_MEMBERS_CACHE", {})
    monkeypatch.setattr(server, "load_league_member_unlock_states",
                        lambda league_id, exclude_user_id=None: [{"user_id": exclude_user_id}])

    def filler(k):
        def go():
            for i in range(LOOPS):
                server._league_members_cached("lg", f"u{k}-{i}")
        return go

    def invalidator():
        for _ in range(LOOPS):
            server._invalidate_league_members_cache("lg")

    assert _race(*[filler(k) for k in range(THREADS)], invalidator, invalidator) == []


def test_trade_card_reads_survive_concurrent_inserts(fast_switch):
    svc = TradeService({})

    def card(trade_id, decision=None):
        c = TradeCard(trade_id=trade_id, league_id="lg", proposing_user_id="me",
                      target_user_id="them", target_username="them",
                      give_player_ids=[f"g{trade_id}"], receive_player_ids=[f"r{trade_id}"],
                      mismatch_score=0.0, fairness_score=0.0, composite_score=0.0)
        c.decision = decision
        return c

    for i in range(200):
        svc._trade_cards[f"seed{i}"] = card(f"seed{i}", "like" if i % 2 else None)

    def inserter(k):
        def go():
            for i in range(LOOPS):
                svc._trade_cards[f"w{k}-{i}"] = card(f"w{k}-{i}", "like" if i % 2 else None)
        return go

    def reader():
        for _ in range(LOOPS // 4):
            svc.get_pending_trades("me")
            svc.get_liked_trades("me")

    assert _race(*[inserter(k) for k in range(3)], reader, reader, reader) == []
