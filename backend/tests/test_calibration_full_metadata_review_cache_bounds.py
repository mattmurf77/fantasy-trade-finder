"""Independent synthetic review regressions, copied with reviewer authorization."""
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from threading import Event,Lock
import json
import pytest
from backend import calibration_roster_metadata as meta
from backend.blind_grading import GradingError

@pytest.fixture
def path(monkeypatch,tmp_path):
 monkeypatch.setattr(meta,'CACHE_PATH',tmp_path/'snapshot.json')
 return meta.CACHE_PATH

def test_concurrent_capture_coalesces_and_readers_cannot_mutate_cached_snapshot(path):
 entered=Event();release=Event();lock=Lock();calls=[]
 raw={'k':{'player_id':'k','position':'K','fantasy_positions':['K'],'active':True,'private_unused':{'huge':'ignored'}}}
 def fetch(_):
  with lock:calls.append(1)
  entered.set();assert release.wait(3)
  return deepcopy(raw)
 with ThreadPoolExecutor(max_workers=2) as pool:
  first=pool.submit(meta.capture,fetch);assert entered.wait(3)
  second=pool.submit(meta.capture,fetch);release.set();a=first.result();b=second.result()
 assert len(calls)==1 and a==b
 assert set(a['rows']['k'])==set(meta.FIELDS)
 a['rows']['k']['fantasy_positions'].append('WR')
 assert meta.peek()['rows']['k']['fantasy_positions']==['K']
 assert 'private_unused' not in path.read_text()

@pytest.mark.parametrize('raw',[{},[],{'a':None},{1:{}}])
def test_bad_source_does_not_publish_complete_snapshot(path,raw):
 with pytest.raises(GradingError):meta.capture(lambda _:raw)
 assert not path.exists()

def test_row_and_byte_bounds_fail_without_partial_publication(path,monkeypatch):
 monkeypatch.setattr(meta,'MAX_ROWS',1)
 with pytest.raises(GradingError):meta.capture(lambda _:{'a':{},'b':{}})
 assert not path.exists()
 monkeypatch.setattr(meta,'MAX_ROWS',10);monkeypatch.setattr(meta,'MAX_BYTES',100)
 with pytest.raises(GradingError):meta.capture(lambda _:{'a':{'injury_status':'x'*200}})
 assert not path.exists()
