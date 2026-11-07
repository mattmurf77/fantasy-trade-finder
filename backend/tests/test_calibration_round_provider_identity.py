"""Real provider identity resolver; only HTTP transport is synthetic.
Account-owned rankings/preferences never become the primary owner's board.
"""
import pytest
from backend import outlook_calibration_adapter as adapter, server, trade_service as ts, feature_flags as ff
from backend.tests.test_owner_generator_routes import harness, owner_harness, ME, OPP

@pytest.fixture
def provider_world(owner_harness,monkeypatch):
    _,_,sess,_,league=owner_harness
    calls=[]
    state={'owner':ME}
    def fetch(url):
        calls.append(url)
        if url.endswith('/rosters'):
            return [{'owner_id':state['owner'],'co_owners':[ME] if state['owner']!=ME else [],
                     'players':list(sess['user_roster'])},
                    *[{'owner_id':m.user_id,'players':list(m.roster)} for m in league.members if m.user_id!=ME]]
        if url.endswith('/users'):
            return [{'user_id':u,'display_name':u} for u in {ME,state['owner'],OPP}]
        return {'roster_positions':['RB','BN','BN','BN','BN'],'name':'Synthetic'}
    monkeypatch.setattr(server,'_sleeper_get',fetch)
    monkeypatch.setattr(server,'_extension_ranking_services',lambda user_id,**k:{'1qb_ppr':sess['service']} if user_id==ME else pytest.fail('read primary owner board'))
    monkeypatch.setattr(server,'_get_universal_pool',lambda fmt:(sess['players'],sess['service']._seed))
    monkeypatch.setattr(server,'_players_cache_age_seconds',lambda:0)
    monkeypatch.setattr(server,'_load_sleeper_cache',lambda:{p.id:{'fantasy_positions':[p.position]} for p in sess['players']})
    monkeypatch.setattr(server,'_league_slot_order',lambda lid:{})
    monkeypatch.setattr(server,'load_league_preference',lambda user_id,**k:{'team_outlook':'contender','acquire_positions':['WR']} if user_id==ME else {'team_outlook':'jets'})
    monkeypatch.setattr(server,'load_asset_preferences',lambda user_id,**k:{'targets':['b1']} if user_id==ME else {'untouchables':['b1']})
    monkeypatch.setattr(adapter,'_input_identity',lambda *a:'unchanged')
    ff._flags_cache.update({'trade.picks_in_pool':False,'deck.quality_filters':False,'trade.preference_lists':True})
    ts._cfg.update(owner_bilateral_enabled=1.,owner_bilateral_revision_enabled=1.,owner_outlook_evidence_enabled=0.)
    return state,calls,sess

@pytest.mark.parametrize('coowner',[False,True])
def test_real_provider_resolves_canonical_roster_but_keeps_account_preferences(provider_world,coowner):
    state,calls,sess=provider_world
    if coowner:state['owner']='primary-owner'
    captured=adapter.capture(user_id=ME,league_user_id=state['owner'],league_id='12345')
    ctx=captured.owner_context
    assert len(calls)==3
    assert ctx['user_id']==state['owner']
    assert captured.source['account_user_id']==ME
    assert captured.source['league_user_id']==state['owner']
    assert ctx['user_roster']==sess['user_roster']
    assert ctx['manager_preferences'][state['owner']]['team_outlook']=='contender'
    assert ctx['manager_preferences'][state['owner']]['targets']==['b1']
    assert state['owner'] not in {m.user_id for m in ctx['league'].members}
    assert ctx['user_elo']=={r.player.id:r.elo for r in sess['service'].get_rankings().rankings}

def test_provider_rejects_spoofed_canonical_seat(provider_world):
    from backend.blind_grading import GradingError
    with pytest.raises(GradingError) as err:
        adapter.capture(user_id=ME,league_user_id='some-other-person',league_id='12345')
    assert err.value.code=='league_seat_changed'

def test_new_coowner_without_saved_seat_resolves_in_capture(provider_world):
    state,_,_=provider_world
    state['owner']='primary-owner'
    captured=adapter.capture(user_id=ME,league_user_id=None,league_id='12345')
    assert captured.source['league_user_id']=='primary-owner'
