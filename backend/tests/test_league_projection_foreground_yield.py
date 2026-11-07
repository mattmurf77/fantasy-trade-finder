"""Scheduling changes never change forecast samples, ownership or deadlines."""
import json
import pytest
from backend import server
from backend.league_projections import service, provider
from backend.tests.test_league_projection_capture_retry import job, read, engine
from backend.tests.test_league_projection_simulation import config, snapshot
from backend.league_projections.simulation import simulate


def test_idle_checkpoint_keeps_single_control_read_and_never_sleeps(monkeypatch):
    checks = []
    monkeypatch.setattr(service.time, 'sleep', lambda _: pytest.fail('idle work must not sleep'))
    assert service._checkpoint(lambda: checks.append(1) or False, lambda: False) is False
    assert checks == [1]


def test_already_cancelled_never_reads_pressure_or_sleeps(monkeypatch):
    monkeypatch.setattr(service.time, 'sleep', lambda _: pytest.fail('cancelled'))
    assert service._checkpoint(lambda: True, lambda: pytest.fail('cancelled')) is True


def test_release_during_wait_resumes_with_one_final_control_read(monkeypatch):
    busy = iter([True, True, False]); sleeps = []; reads = []
    monkeypatch.setattr(service.time, 'sleep', sleeps.append)
    assert service._checkpoint(lambda: reads.append(1) or False, lambda: next(busy)) is False
    assert sleeps == [.1, .1] and reads == [1, 1]


@pytest.mark.parametrize('broken', [False, True])
def test_sustained_or_unavailable_pressure_has_fixed_bound(monkeypatch, broken):
    sleeps = []; reads = []
    monkeypatch.setattr(service.time, 'sleep', sleeps.append)
    def pressure():
        if broken:
            raise RuntimeError('private diagnostic must never escape')
        return True
    assert service._checkpoint(lambda: reads.append(1) or False, pressure) is False
    assert sleeps == [.1] * 10 and reads == [1, 1]


def test_cancellation_during_pause_prevents_next_chunk(monkeypatch):
    reads = iter([False, True]); sleeps = []
    monkeypatch.setattr(service.time, 'sleep', sleeps.append)
    assert service._checkpoint(lambda: next(reads), lambda: True) is True
    assert len(sleeps) == 10


def test_simulation_keeps_exact_result_and_checkpoint_count(monkeypatch):
    counts = [0, 0]; waits = []
    monkeypatch.setattr(service.time, 'sleep', waits.append)
    def plain():
        counts[0] += 1
        return False
    def priority():
        counts[1] += 1
        return service._checkpoint(lambda: False, lambda: True)
    assert simulate(snapshot(), config(), cancelled=plain) == simulate(snapshot(), config(), cancelled=priority)
    assert counts == [2, 2] and len(waits) == 20


def test_worker_persists_full_result_after_priority_pause(job, monkeypatch):
    seen = []; sleeps = []
    monkeypatch.setattr(service.time, 'sleep', sleeps.append)
    monkeypatch.setattr(provider, 'capture', lambda *a, **kw: {'source': 'synthetic', 'captured_at': '2026-11-07T00:00:00+00:00'})
    def evaluate(source, cfg, *, cancelled):
        seen.append(cancelled())
        assert not seen[-1]
        return {'source': source['source'], 'all_draws_complete': True}
    monkeypatch.setattr(service, 'simulate', evaluate)
    service._run(None, lambda: True)
    result = read(job)
    assert result['status'] == 'complete'
    assert json.loads(result['result_json'])['all_draws_complete'] is True
    assert sleeps == [.1] * 10


def test_worker_policy_revoked_during_pause_cannot_publish(job, monkeypatch):
    monkeypatch.setattr(provider, 'capture', lambda *a, **kw: {'source': 'synthetic', 'captured_at': '2026-11-07T00:00:00+00:00'})
    monkeypatch.setattr(service.time, 'sleep', lambda _: job[1].update({'league.projections_provider_approved': False}))
    def evaluate(source, cfg, *, cancelled):
        from backend.league_projections.core import Unavailable
        assert cancelled()
        raise Unavailable('cancelled', state='cancelled')
    monkeypatch.setattr(service, 'simulate', evaluate)
    service._run(None, lambda: True)
    assert read(job)['status'] == 'cancelled' and read(job)['result_json'] is None


def test_worker_deadline_not_extended_by_yield(job, monkeypatch):
    clock = [0.]
    monkeypatch.setattr(service.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(provider, 'capture', lambda *a, **kw: {'source': 'synthetic', 'captured_at': '2026-11-07T00:00:00+00:00'})
    def sleep(_):
        clock[0] = 541.
    monkeypatch.setattr(service.time, 'sleep', sleep)
    def evaluate(source, cfg, *, cancelled):
        from backend.league_projections.core import Unavailable
        assert cancelled()
        raise Unavailable('cancelled', state='cancelled')
    monkeypatch.setattr(service, 'simulate', evaluate)
    service._run(None, lambda: True)
    assert read(job)['status'] == 'cancelled' and read(job)['result_json'] is None


@pytest.mark.parametrize('source,status,expected', [(None,'running',True),('prepared_inventory','running',False),('replenish','running',True),(None,'complete',False),(None,'error',False)])
def test_priority_signal_uses_live_jobs_and_releases_lock(monkeypatch, source, status, expected):
    import threading, time
    lock = threading.Lock()
    monkeypatch.setattr(server, '_trade_jobs_lock', lock)
    monkeypatch.setattr(server, '_trade_jobs', {'synthetic': {'status':status,'source':source,'started_at':time.monotonic()}})
    assert server._projection_foreground_busy() is expected
    assert lock.acquire(blocking=False)
    lock.release()
