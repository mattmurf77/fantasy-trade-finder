"""Independent synthetic review regressions, copied with reviewer authorization."""
from copy import deepcopy
from pathlib import Path
import json,time
import pytest
from backend import server,session_input,outlook_calibration_adapter as adapter
from backend import calibration_roster_metadata as meta
from backend.tests.test_outlook_calibration_adapter import captured
from backend.tests.test_owner_generator_routes import harness,owner_harness,ME,LEAGUE
REAL_IDENTITY=adapter._input_identity
REAL_LOAD=server._load_sleeper_cache

@pytest.fixture
def full_world(captured,monkeypatch,tmp_path):
 original=session_input.resolve_session_input
 full={pid:{'player_id':pid,'position':p.position,'fantasy_positions':[p.position],'active':True,'injury_status':None,'full_name':pid} for pid,p in captured.owner_context['players'].items()}
 for pid,pos in [('fixed-k','K'),('fixed-idp','LB'),('NFL','DEF')]:
  full[pid]={'player_id':pid,'position':pos,'fantasy_positions':[pos],'active':True,'injury_status':None}
 def resolve(sess,body,fetch,raw):
  value=original(sess,body,fetch,raw)
  raw['meta']['roster_positions'].extend(['K','LB','DEF'])
  for row in raw['rosters']:
   if row['owner_id']==ME:row['players'].extend(['fixed-k','fixed-idp','NFL'])
  value['user_player_ids'].extend(['fixed-k','fixed-idp','NFL'])
  return value
 monkeypatch.setattr(session_input,'resolve_session_input',resolve)
 monkeypatch.setattr(server,'_sleeper_cache',server._filter_bulk_players(full))
 monkeypatch.setattr(server,'_load_sleeper_cache',REAL_LOAD)
 assert 'fixed-k' not in server._load_sleeper_cache()
 monkeypatch.setattr(meta,'CACHE_PATH',tmp_path/'full.json')
 monkeypatch.setattr(adapter,'_input_identity',REAL_IDENTITY)
 calls=[]
 def fetch(url,*a,**kw):
  assert url==meta.URL;calls.append(url);return deepcopy(full)
 monkeypatch.setattr(server,'_sleeper_get',fetch)
 fmt=server.get_league_scoring(LEAGUE)
 monkeypatch.setattr(server,'g_universal_by_format',{fmt:{'players':list(captured.owner_context['players'].values()),'seed':dict(captured.owner_context['seed_elo'])}})
 return full,calls

def run():return adapter.capture(user_id=ME,league_user_id=ME,league_id=LEAGUE)

def test_actual_filtered_boundary_captures_fixed_without_expanding_market(full_world):
 result=run()
 assert {'fixed-k','fixed-idp','NFL'}<=result.source['fixed_lineup']['assets'].keys()
 assert 'fixed-k' not in result.owner_context['players']
 assert 'fixed-k' not in server._load_sleeper_cache()
 assert len(full_world[1])==1
 assert adapter.is_current(result.source,user_id=ME,league_user_id=ME,league_id=LEAGUE)
 assert len(full_world[1])==1

def test_consumed_snapshot_cannot_bind_newer_file_before_first_fingerprint(full_world,monkeypatch):
 original=meta.capture
 def swap(fetch):
  snapshot=original(fetch)
  changed=deepcopy(snapshot);changed['rows']['fixed-k']['active']=False
  changed['observed_at']+=1;changed['revision']=meta._digest(changed['rows'])
  meta.CACHE_PATH.write_text(json.dumps(changed))
  return snapshot
 monkeypatch.setattr(meta,'capture',swap)
 with pytest.raises(adapter.GradingError,match='inputs_changed_during_capture'):run()

def test_deployment_cache_loss_and_cold_pool_preserve_asof_without_network(full_world,monkeypatch,tmp_path):
 import importlib
 result=run();source=json.loads(json.dumps(result.source))
 saved=server.g_universal_by_format.copy()
 meta.CACHE_PATH.unlink()
 importlib.reload(meta)
 monkeypatch.setattr(meta,'CACHE_PATH',tmp_path/'new-deployment'/'missing.json')
 monkeypatch.setattr(server,'g_universal_by_format',{})
 def warm(fmt):
  server.g_universal_by_format[fmt]=deepcopy(saved[fmt])
  return server.g_universal_by_format[fmt]['players'],server.g_universal_by_format[fmt]['seed']
 monkeypatch.setattr(server,'_get_universal_pool',warm)
 monkeypatch.setattr(server,'_sleeper_get',lambda *a,**k:pytest.fail('network on open after deploy'))
 assert adapter.is_current(source,user_id=ME,league_user_id=ME,league_id=LEAGUE)
 assert not meta.CACHE_PATH.exists()

@pytest.mark.parametrize('kind',['injury','remove','eligibility'])
def test_newer_held_observation_invalidates_but_older_does_not(full_world,kind):
 result=run();saved=meta.peek();changed=deepcopy(saved)
 if kind=='injury':changed['rows']['fixed-k']['injury_status']='IR'
 if kind=='remove':changed['rows'].pop('fixed-k')
 if kind=='eligibility':changed['rows']['fixed-k']['fantasy_positions']=['LB']
 changed['revision']=meta._digest(changed['rows'])
 changed['observed_at']=saved['observed_at']-1;meta.CACHE_PATH.write_text(json.dumps(changed))
 assert adapter.is_current(result.source,user_id=ME,league_user_id=ME,league_id=LEAGUE)
 changed['observed_at']=saved['observed_at']+1;meta.CACHE_PATH.write_text(json.dumps(changed))
 assert not adapter.is_current(result.source,user_id=ME,league_user_id=ME,league_id=LEAGUE)

def test_catalog_not_stored_and_unrelated_row_change_not_semantic(full_world):
 full_world[0]['not-held']={'player_id':'not-held','position':'LB','fantasy_positions':['LB'],'active':True}
 result=run();saved=meta.peek()
 assert 'not-held' not in json.dumps(result.source['full_metadata_observation'])
 assert set(result.source['full_metadata_observation']['held'])==set(result.source['captured_metadata_ids'])
 saved['rows']['not-held']['active']=False;saved['observed_at']+=1;saved['revision']=meta._digest(saved['rows'])
 meta.CACHE_PATH.write_text(json.dumps(saved))
 assert adapter.is_current(result.source,user_id=ME,league_user_id=ME,league_id=LEAGUE)

def test_full_cache_uses_own_age_and_preserves_old_file_on_outage(full_world,monkeypatch):
 run();old=meta.peek();old['observed_at']=time.time()-meta.TTL_SECONDS-1
 meta.CACHE_PATH.write_text(json.dumps(old));previous=meta.CACHE_PATH.read_bytes()
 def fail(*a,**k):raise TimeoutError('source unavailable')
 with pytest.raises(adapter.GradingError,match='player_metadata_unavailable'):meta.capture(fail)
 assert meta.CACHE_PATH.read_bytes()==previous
 # Fresh filtered skill cache does not waive full-catalog refresh.
 assert server._players_cache_age_seconds()==0
 meta.capture(lambda _:deepcopy(full_world[0]))
 assert meta.peek()['observed_at']>old['observed_at']

def test_captured_offensive_slots_shared_by_both_arms_without_format_fallback(full_world):
 result=run()
 assert result.roster_context.rules.slots==('RB',)
 for pref in result.owner_context['manager_preferences'].values():
  assert pref['starter_slots']==['RB']
  assert pref['lineup_source']=='observed'
 from backend import trade_gen_bilateral_candidate as old,trade_gen_outlook_evidence as new
 from copy import deepcopy
 for module in (old,new):
  context=deepcopy(result.owner_context)
  if module is old:context.pop('input_evidence',None)
  search=module._Search(**context)
  assert all(t['slots']==('RB',) and not t['unsupported_slots'] and t['lineup_source']=='observed' for t in search.teams.values())
 assert 'starter_slots' in json.dumps(result.source['input'])

def test_viewer_cross_domain_stays_explicit_unsupported(full_world,monkeypatch):
 mine=next(pid for pid in full_world[0] if pid.startswith('a') and full_world[0][pid]['position']=='RB')
 full_world[0][mine]['fantasy_positions']=['RB','DB']
 original=session_input.resolve_session_input
 def resolve(*args,**kwargs):
  value=original(*args,**kwargs);kwargs['raw']['meta']['roster_positions'].append('DB');return value
 monkeypatch.setattr(session_input,'resolve_session_input',resolve)
 with pytest.raises(adapter.GradingError,match='provider_cross_domain_eligibility'):run()

def test_generator_proxy_preserves_same_captured_inactive_players(full_world,monkeypatch):
 original=session_input.resolve_session_input
 inactive=next(pid for pid in full_world[0] if pid.startswith('a') and full_world[0][pid]['position']=='RB')
 def resolve(*args,**kwargs):
  value=original(*args,**kwargs)
  for row in kwargs['raw']['rosters']:
   if row['owner_id']==ME:row['reserve']=[inactive]
  return value
 monkeypatch.setattr(session_input,'resolve_session_input',resolve)
 result=run()
 assert inactive in result.roster_context.teams[ME].inactive
 assert inactive in result.owner_context['manager_preferences'][ME].get('inactive_ids',[])
