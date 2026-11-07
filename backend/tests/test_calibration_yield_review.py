"""Independent advisory scheduler invariants; no real sleep/provider traffic."""
import pytest
from backend import outlook_calibration as oc

class Clock:
    def __init__(self): self.now=0.; self.sleeps=[]
    def __call__(self): return self.now
    def sleep(self,duration): self.sleeps.append(duration);self.now+=duration


def test_repeated_foreground_pressure_still_allows_work():
    clock=Clock();calls=[]
    step=oc._CooperativeYield(lambda:calls.append(clock.now) or True,clock=clock,sleep=clock.sleep)
    for block in range(4):
        step()
        after=len(clock.sleeps)
        for _ in range(200): step()
        assert len(clock.sleeps)==after==(block+1)*10
        clock.now+=.101
    assert all(s==.1 for s in clock.sleeps)


def test_release_is_seen_each_slice_and_checks_are_throttled_after_idle():
    clock=Clock();pressure=iter((True,False,False));calls=[]
    def signal():calls.append(1);return next(pressure)
    step=oc._CooperativeYield(signal,clock=clock,sleep=clock.sleep)
    step();assert clock.sleeps==[.1] and len(calls)==2
    for _ in range(100):step()
    assert len(calls)==2
    clock.now+=.101;step();assert len(calls)==3


@pytest.mark.parametrize('failure',['initial_clock','final_clock','sleep','pressure'])
def test_advisory_failures_cannot_escape_into_arm_failure(failure):
    clock=Clock();reads=[]
    def read():
        reads.append(1)
        if failure=='initial_clock' or (failure=='final_clock' and len(reads)>1):
            raise OSError('synthetic clock failure')
        return clock.now
    def signal():
        if failure=='pressure':raise RuntimeError('synthetic signal failure')
        return True
    def sleep(duration):
        if failure=='sleep':raise OSError('synthetic sleep failure')
        clock.sleep(duration)
    step=oc._CooperativeYield(signal,clock=read,sleep=sleep)
    step()
    assert len(clock.sleeps)<=10


def test_baseexception_shutdown_is_not_swallowed():
    def stop(_):raise KeyboardInterrupt()
    with pytest.raises(KeyboardInterrupt):
        oc._CooperativeYield(lambda:True,clock=lambda:0.,sleep=stop)()

from backend import database as db
from backend.tests.test_outlook_calibration_persistence import engine
from backend.tests.test_outlook_calibration_service import frozen_factory


def test_real_queue_reaches_both_arms_under_pressure_error(engine, monkeypatch):
    frozen,calls=frozen_factory();clock=Clock();checks=[]
    original=oc._CooperativeYield
    def factory(pressure):
        def signal():checks.append(1);raise RuntimeError('unavailable advisory signal')
        return original(signal,clock=clock,sleep=clock.sleep)
    monkeypatch.setattr(oc,'_CooperativeYield',factory)
    monkeypatch.setattr(oc,'build_enabled',lambda:True)
    sid=oc.start_session(user_id='account',league_user_id='seat',league_id='league')['session']['session_id']
    assert oc.drain_queue(capture=lambda **kw:frozen,max_jobs=1)['processed']==1
    assert db.load_grading_session(sid)['status']=='open'
    assert sorted(calls)==sorted(oc.MODEL_VERSIONS.values())
    assert len(checks)==10 and len(clock.sleeps)==10
    assert db.load_grading_cards(sid)


def test_lease_lost_at_yield_still_prevents_private_capture_publication(engine, monkeypatch):
    frozen,calls=frozen_factory();clock=Clock()
    original=oc._CooperativeYield
    def factory(pressure):
        def signal():
            with engine.begin() as conn:
                conn.execute(db.grading_build_leases_table.update().values(expires_at='2000-01-01T00:00:00+00:00'))
            return False
        return original(signal,clock=clock,sleep=clock.sleep)
    monkeypatch.setattr(oc,'_CooperativeYield',factory)
    monkeypatch.setattr(oc,'build_enabled',lambda:True)
    sid=oc.start_session(user_id='account',league_user_id='seat',league_id='league')['session']['session_id']
    oc.drain_queue(capture=lambda **kw:frozen,max_jobs=1)
    row=db.load_grading_session(sid)
    assert row['status']=='building'
    assert 'frozen-common-hash' not in row['source_json']
    assert not db.load_grading_cards(sid)
    assert calls==[]
