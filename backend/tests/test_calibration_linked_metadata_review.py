"""Independent linked metadata integration regressions; copied with permission."""
import copy,json
import pytest
from backend import server,database as db,outlook_calibration_adapter as adapter
from backend import calibration_provider_capture as provider,calibration_roster_metadata as meta
from backend.tests.test_outlook_calibration_adapter import captured
from backend.tests.test_owner_generator_routes import harness,owner_harness,ME,LEAGUE
REAL_IDENTITY=adapter._input_identity
REAL_LOAD=server._load_sleeper_cache

@pytest.fixture
def world(captured,monkeypatch,tmp_path):
 context=captured.owner_context
 rosters=[{'owner_id':ME,'players':list(context['user_roster']),'reserve':[],'taxi':[]}]+[{'owner_id':m.user_id,'players':list(m.roster),'reserve':[],'taxi':[]} for m in context['league'].members if m.user_id!=ME]
 rosters[0]['players'].append('mapped-db')
 positions={pid:p.position for pid,p in context['players'].items()};positions['mapped-db']='WR'
 fixed={}
 for n,r in enumerate(rosters):
  pid=f'espn-fixed:fixture:{n}';r['players'].append(pid)
  fixed[pid]={'player_id':pid,'position':'DB','fantasy_positions':['DB'],'active':True,'injury_status':'ACTIVE','native_eligible_slots':[14,20]}
 resolved={'platform':'espn','league_user_id':ME,'user_player_ids':rosters[0]['players'],'opponent_rosters':[{'user_id':r['owner_id'],'username':'','player_ids':r['players']} for r in rosters[1:]]}
 linked=provider.LinkedSnapshot('espn',resolved,rosters,['RB','DB'],100,positions,{'rules':{},'binding':None},fixed_metadata=fixed)
 full={pid:{'player_id':pid,'position':p.position,'fantasy_positions':[p.position],'active':True,'injury_status':None,'full_name':pid} for pid,p in context['players'].items()}
 full['mapped-db']={'player_id':'mapped-db','position':'DB','fantasy_positions':['DB'],'active':True,'injury_status':None,'full_name':'Synthetic'}
 monkeypatch.setattr(db,'is_linked_platform_league',lambda _:True)
 monkeypatch.setattr(provider,'capture_linked',lambda **kw:linked)
 monkeypatch.setattr(provider,'binding_identity',lambda *a:None)
 monkeypatch.setattr(server,'_sleeper_cache',server._filter_bulk_players(full));monkeypatch.setattr(server,'_load_sleeper_cache',REAL_LOAD)
 assert 'mapped-db' not in server._load_sleeper_cache()
 monkeypatch.setattr(meta,'CACHE_PATH',tmp_path/'full.json')
 monkeypatch.setattr(adapter,'_input_identity',REAL_IDENTITY)
 monkeypatch.setattr(server,'g_universal_by_format',{'1qb_ppr':{'players':list(context['players'].values()),'seed':dict(context['seed_elo'])}})
 calls=[]
 def fetch(url,*a,**k):assert url==meta.URL;calls.append(url);return copy.deepcopy(full)
 monkeypatch.setattr(server,'_sleeper_get',fetch)
 return linked,full,calls

def run():return adapter.capture(user_id=ME,league_user_id=ME,league_id=LEAGUE)

def test_native_position_fixed_ids_and_market_preserved(world):
 linked,full,calls=world;result=run()
 assert len(calls)==1 and result.roster_context.assets['mapped-db'].positions==frozenset({'WR'})
 assert 'mapped-db' not in result.owner_context['players']
 assert set(result.source['full_metadata_observation']['held'])==set(linked.positions)
 assert not set(linked.fixed_metadata)&set(result.source['full_metadata_observation']['held'])
 assert set(linked.fixed_metadata)<=set(result.source['fixed_lineup']['assets'])
 assert adapter.is_current(result.source,user_id=ME,league_user_id=ME,league_id=LEAGUE)
 assert len(calls)==1

def test_coupled_viewer_still_refuses_after_availability_resolves(world):
 world[0].provenance['unsupported_native_eligibility']={'mapped-db':{'original_native_eligible_slots':[4,14,20]}}
 with pytest.raises(adapter.GradingError,match='provider_cross_domain_eligibility'):run()
 assert len(world[2])==1

def test_missing_full_row_refuses_instead_of_fabricating(world):
 world[1].pop('mapped-db')
 with pytest.raises(adapter.GradingError,match='provider_player_availability_unavailable'):run()

def test_swap_before_first_fingerprint_refuses(world,monkeypatch):
 original=meta.capture
 def swap(fetch):
  snapshot=original(fetch);changed=copy.deepcopy(snapshot);changed['rows']['mapped-db']['active']=False;changed['observed_at']+=1;changed['revision']=meta._digest(changed['rows']);meta.CACHE_PATH.write_text(json.dumps(changed));return snapshot
 monkeypatch.setattr(meta,'capture',swap)
 with pytest.raises(adapter.GradingError,match='inputs_changed_during_capture'):run()

def test_cold_deployment_uses_asof_without_network(world,monkeypatch,tmp_path):
 result=run();source=json.loads(json.dumps(result.source));saved=copy.deepcopy(server.g_universal_by_format)
 meta.CACHE_PATH.unlink();monkeypatch.setattr(meta,'CACHE_PATH',tmp_path/'cold'/'missing.json');monkeypatch.setattr(server,'g_universal_by_format',{})
 def warm(fmt):server.g_universal_by_format.update(copy.deepcopy(saved));return saved[fmt]['players'],saved[fmt]['seed']
 monkeypatch.setattr(server,'_get_universal_pool',warm);monkeypatch.setattr(server,'_sleeper_get',lambda *a:pytest.fail('provider fetch on open'))
 assert adapter.is_current(source,user_id=ME,league_user_id=ME,league_id=LEAGUE)

@pytest.mark.parametrize('change',['remove','injury'])
def test_newer_held_change_invalidates(world,change):
 result=run();updated=meta.peek()
 if change=='remove':updated['rows'].pop('mapped-db')
 else:updated['rows']['mapped-db']['injury_status']='OUT'
 updated['observed_at']+=1;updated['revision']=meta._digest(updated['rows']);meta.CACHE_PATH.write_text(json.dumps(updated))
 assert not adapter.is_current(result.source,user_id=ME,league_user_id=ME,league_id=LEAGUE)
