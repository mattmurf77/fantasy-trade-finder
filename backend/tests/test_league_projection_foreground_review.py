import ast
import inspect
import json
import threading
import pytest
from backend import server, database as db
from backend.league_projections import service, store, provider
from backend.league_projections.core import Unavailable
from backend.tests.test_league_projection_capture_retry import job, read, engine

@pytest.mark.parametrize('change', ['cancel', 'token', 'delete', 'expiry', 'policy', 'flag'])
def test_control_change_while_sleeping_never_publishes(job, engine, monkeypatch, change):
    monkeypatch.setattr(provider, 'capture', lambda *a, **k: {'captured_at':'2026-11-07T00:00:00+00:00','source':'synthetic'})
    mutations=[]
    def sleep(_):
        if mutations:return
        mutations.append(change)
        if change=='policy':job[2]['policy_approved']=False
        elif change=='flag':job[1]['league.projections']=False
        elif change=='cancel':store.cancel(job[0]['run_id'],'account','123')
        else:
            t=db.league_projection_runs_table
            with engine.begin() as c:
                q=t.delete() if change=='delete' else t.update().values(**({'worker_token':'new-worker'} if change=='token' else {'expires_at':'2000-01-01T00:00:00+00:00'}))
                c.execute(q.where(t.c.run_id==job[0]['run_id']))
    monkeypatch.setattr(service.time,'sleep',sleep)
    # Isolate one claimed execution; ordinary recovery has separate existing tests.
    claim=store.claim; once=[]
    def claim_once():
        if once:return None
        once.append(True);return claim()
    monkeypatch.setattr(store,'claim',claim_once)
    def simulation(*a, cancelled, **k):
        assert cancelled()
        raise Unavailable('cancelled',state='cancelled')
    monkeypatch.setattr(service,'simulate',simulation)
    service._run(None, lambda:True)
    result=read(job)
    assert result is None or result['result_json'] is None
    assert mutations==[change]


def test_sleep_never_holds_registry_lock_and_reacts_to_completion(monkeypatch):
    lock=threading.Lock(); row={'status':'running'}; sleeps=[]
    monkeypatch.setattr(server,'_trade_jobs_lock',lock)
    monkeypatch.setattr(server,'_trade_jobs',{'x':row})
    def sleep(n):
        assert lock.acquire(False)
        row['status']='complete';lock.release();sleeps.append(n)
    monkeypatch.setattr(service.time,'sleep',sleep)
    assert service._checkpoint(lambda:False,server._projection_foreground_busy) is False
    assert sleeps==[.1]


def test_wake_threads_callback_without_running_under_scheduler_lock(monkeypatch):
    lock=threading.Lock(); observed=[]; callback=lambda:False
    monkeypatch.setattr(service,'_lock',lock)
    monkeypatch.setattr(service,'_worker',None)
    monkeypatch.setattr(service,'is_enabled',lambda _:True)
    class Thread:
        def __init__(self,**kw):observed.append(kw)
        def start(self):pass
        def is_alive(self):return True
    monkeypatch.setattr(service.threading,'Thread',Thread)
    service.wake('source',foreground_busy=callback)
    service.wake('unused',foreground_busy=callback)
    assert len(observed)==1 and observed[0]['args']==('source',callback)
    assert lock.acquire(False);lock.release()


def test_dedicated_route_callback_is_server_owned(monkeypatch):
    from backend.league_projections import batch
    seen=[]
    monkeypatch.setattr(server,'_require_cron_auth',lambda:None)
    monkeypatch.setattr(batch,'dispatch',lambda *a,**k: seen.append(k) or {'queued':0})
    client=server.app.test_client()
    assert client.post('/api/cron/league-projections',json={'initial':True,'limit':1}).status_code==200
    assert seen[0]['foreground_busy'] is server._projection_foreground_busy
    assert client.post('/api/cron/league-projections',json={'foreground_busy':False}).status_code==400
    assert len(seen)==1


def test_both_cron_entrypoints_supply_same_signal():
    for fn in [server.cron_realtime_tick,server.cron_league_projections]:
        tree=ast.parse(inspect.getsource(fn))
        calls=[n for n in ast.walk(tree) if isinstance(n,ast.Call) and any(k.arg=='foreground_busy' for k in n.keywords)]
        assert len(calls)==1
        assert next(k.value.id for k in calls[0].keywords if k.arg=='foreground_busy')=='_projection_foreground_busy'


def test_continuous_pressure_progresses_but_does_not_extend_deadline(monkeypatch):
    clock=[0.]; chunks=[]
    monkeypatch.setattr(service.time,'sleep',lambda seconds:clock.__setitem__(0,clock[0]+seconds))
    for i in range(600):
        if service._checkpoint(lambda:clock[0]>540, lambda:True):break
        chunks.append(i)
    assert 539<=len(chunks)<=540
    assert 540<clock[0]<542
