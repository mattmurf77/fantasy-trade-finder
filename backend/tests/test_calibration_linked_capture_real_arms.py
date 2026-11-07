"""Actual linked membership/capture/parser/gates with synthetic provider transport."""
import copy
import json
import os
from pathlib import Path
import pytest
from backend import database as db,server,feature_flags as ff
from backend import outlook_calibration_adapter as adapter,calibration_provider_capture as provider
from backend.espn_service import Crosswalk
from backend.tests.test_owner_generator_routes import harness,owner_harness,ME
from backend.tests.test_owner_only_routes import exclusive,large_exclusive
LEAGUE='12345'

@pytest.mark.parametrize('platform,picks_enabled,race,fixed_groups',[('espn',False,False,False),('espn',True,False,False),('mfl',False,False,False),('mfl',True,False,False),('mfl',True,True,False),('espn',False,False,True),('mfl',True,False,'native'),('mfl',True,False,'second-account'),('espn',False,False,'coupled-opponent'),('espn',False,False,'coupled-viewer')])
def test_linked_capture_runs_both_models_from_same_raw_snapshot(large_exclusive,monkeypatch,platform,picks_enabled,race,fixed_groups):
    _,engine,sess,_,league=large_exclusive
    with engine.begin() as conn:
        conn.execute(db.leagues_table.insert().values(sleeper_league_id=LEAGUE,
            platform=platform,user_id=ME,espn_my_team_id=1,espn_auth='public',platform_my_team='0001',platform_auth='public',platform_host='www1'))
        # Own flat member row is deliberately absent: validated provider
        # account binding and fresh native seat are authoritative here.
    account = 'second-account' if fixed_groups=='second-account' else ME
    native={p.id:str(i) for i,p in enumerate(sess['players'],1)}
    native['raw-only-bench']='9999'
    cross=Crosswalk(by_name_pos={},by_espn_id={v:k for k,v in native.items()},by_mfl_sleeper={v:k for k,v in native.items()})
    teams=[(i,m) for i,m in enumerate(league.members,1)]
    if platform=='espn':
        raw={'id':int(LEAGUE),'seasonId':2026,'settings':{'size':len(teams),'rosterSettings':{'lineupSlotCounts':{'4':1,'20':20,'21':1}}},'teams':[]}
        for i,m in teams:
            holdings=list(m.roster)+(['raw-only-bench'] if i==1 else [])
            raw['teams'].append({'id':i,'roster':{'entries':[{'lineupSlotId':20,'playerPoolEntry':{'player':{'id':int(native[p]),'fullName':p,'defaultPositionId':3,'eligibleSlots':[4,5,7,20,21,23]}}} for p in holdings]}})
        if fixed_groups:
            raw['settings']['rosterSettings']['lineupSlotCounts'].update({'10':2,'11':2,'14':2,'15':1,'17':1})
            for team in raw['teams']:
                for offset,(position,eligible) in enumerate([(5,[17]),(9,[11,15]),(10,[11,15]),(11,[10,15]),(12,[14,15]),(13,[14,15])]):
                    team['roster']['entries'].append({'lineupSlotId':20,'playerPoolEntry':{'player':{
                        'id':90000+team['id']*10+offset,'defaultPositionId':position,
                        'eligibleSlots':eligible+[20,21],'injuryStatus':'ACTIVE'}}})
        if fixed_groups in ('coupled-opponent','coupled-viewer'):
            team=raw['teams'][1 if fixed_groups=='coupled-opponent' else 0]
            team['roster']['entries'][0]['playerPoolEntry']['player']['eligibleSlots'] += [14,15]
        monkeypatch.setattr(provider.espn,'fetch_league',lambda *a,**k:copy.deepcopy(raw))
        remap={m.user_id:f'espn:{LEAGUE}.t{i}' for i,m in teams if i!=1}
    else:
        raw={'league':{'league':{'id':LEAGUE,'rosterSize':'21','injuredReserve':'1','taxiSquad':'2','starters':{'count':'1','position':[{'name':'WR','limit':'1'}]},'franchises':{'count':str(len(teams)),'franchise':[{'id':f'{i:04}','name':m.user_id} for i,m in teams]}}},
             'rosters':{'rosters':{'franchise':[{'id':f'{i:04}','player':[{'id':native[p],'status':'ROSTER'} for p in list(m.roster)+(['raw-only-bench'] if i==1 else [])]} for i,m in teams]}},
             'players':{'players':{'player':[{'id':v,'name':p,'position':'WR'} for p,v in native.items()]}},
             'rules':{'rules':{'positionRules':{'positions':'WR|RB|TE','rule':{'event':'CC','points':'1'}}}},'futureDraftPicks':{'futureDraftPicks':{'franchise':[]}}}
        if fixed_groups in ('native','second-account'):
            raw['league']['league']['starters']={'count':'2','iop_starters':'1','idp_starters':'1',
                'position':[{'name':'WR','limit':'1-2'},{'name':'DT','limit':'0-1'},{'name':'DE','limit':'0-1'}]}
            for i,team in enumerate(raw['rosters']['rosters']['franchise']):
                pid=str(90000+i)
                team['player'].append({'id':pid,'status':'ROSTER'})
                raw['players']['players']['player'].append({'id':pid,'name':'Synthetic DT','position':'DT'})
            if account!=ME:
                monkeypatch.setattr(db,'get_mfl_credential',lambda uid:{'cookie_encrypted':'own-cookie','updated_at':'synthetic'} if uid==account else pytest.fail('borrowed credentials'))
                monkeypatch.setattr(server._sleeper_write,'decrypt_token',lambda _: 'own-token')
                monkeypatch.setattr(provider.mfl,'fetch_my_leagues',lambda cookie,year:[{'league_id':LEAGUE,'franchise_id':'0001'}] if cookie=='own-token' else pytest.fail('wrong credential'))
        if picks_enabled:
            raw['futureDraftPicks']['futureDraftPicks']['franchise']=[{'id':'0002','futureDraftPick':[{'year':'2027','round':'1','originalPickFor':'0001'}]}]
        monkeypatch.setattr(provider.mfl,'fetch_league_bundle',lambda *a,**k:copy.deepcopy(raw))
        remap={m.user_id:f'mfl:{LEAGUE}.f{i:04}' for i,m in teams if i!=1}
    with engine.begin() as conn:
        existing=set(conn.execute(db.select(db.users_table.c.sleeper_user_id)).scalars())
        for uid in {ME,account,*remap.values()}-existing:
            conn.execute(db.users_table.insert().values(sleeper_user_id=uid,created_at='2026-11-01T00:00:00+00:00',verified_via='sleeper'))
    boards=server.load_member_rankings(LEAGUE)
    monkeypatch.setattr(server,'load_member_rankings',lambda *a,**k:{remap.get(uid,uid):board for uid,board in boards.items()})
    monkeypatch.setattr(server,'_shared_crosswalk',lambda:cross)
    monkeypatch.setattr(server,'_sleeper_get',lambda *a:pytest.fail('unexpected Sleeper league request'))
    monkeypatch.setattr(server,'_extension_ranking_services',lambda uid,**k:{'1qb_ppr':sess['service']} if uid==account else pytest.fail('wrong account board'))
    monkeypatch.setattr(server,'_get_universal_pool',lambda fmt:(sess['players'],sess['service']._seed))
    monkeypatch.setattr(server,'_load_sleeper_cache',lambda:{p:{'position':'WR','fantasy_positions':['WR'],'active':True} for p in native})
    monkeypatch.setattr(server,'_players_cache_age_seconds',lambda:0)
    monkeypatch.setattr(server,'_league_slot_order',lambda lid:{})
    ff._flags_cache.update({'trade.picks_in_pool':picks_enabled,'deck.quality_filters':True})
    if race:
        original_sync=server._sync_mfl_owned_picks
        def concurrent_sync(*a,**k):
            result=original_sync(*a,**k)
            with engine.begin() as conn:
                conn.execute(db.draft_picks_table.update().where(db.draft_picks_table.c.league_id==LEAGUE).values(owner_user_id=ME))
            return result
        monkeypatch.setattr(server,'_sync_mfl_owned_picks',concurrent_sync)
        with pytest.raises(adapter.GradingError):
            adapter.capture(user_id=ME,league_user_id=ME,league_id=LEAGUE)
        return
    if fixed_groups=='coupled-viewer':
        with pytest.raises(adapter.GradingError,match='provider_cross_domain_eligibility'):
            adapter.capture(user_id=account,league_user_id=ME,league_id=LEAGUE)
        return
    captured=adapter.capture(user_id=account,league_user_id=ME,league_id=LEAGUE)
    assert captured.source['platform']==platform
    assert set(captured.source['registered_participants'])=={ME,account,*remap.values()}
    assert set(captured.source['registered_participant_revisions'])=={ME,account,*remap.values()}
    assert captured.source['unpriced_occupancy']['raw-only-bench']['market_value'] is None
    assert captured.source['picks_included'] is (picks_enabled and platform=='mfl')
    if picks_enabled and platform=='mfl':
        rows=db.load_draft_picks(LEAGUE)
        assert len(rows)==1
        assert rows[0]['owner_user_id']==f'mfl:{LEAGUE}.f0002'
        assert rows[0]['original_user_id']==ME
        assert rows[0]['pick_id'] in captured.roster_context.teams[f'mfl:{LEAGUE}.f0002'].roster
        assert rows[0]['pick_id'] not in captured.roster_context.teams[ME].roster
    if fixed_groups is True:
        assert captured.source['fixed_lineup']['fixed_slots']==['LB','LB','DL','DL','DB','DB','IDP_FLEX','K']
        assert captured.source['fixed_lineup']['assets']
        assert not set(captured.source['fixed_lineup']['assets']) & captured.owner_context['players'].keys()
    if fixed_groups in ('native','second-account'):
        assert captured.roster_context.rules.native_bounds
        assert captured.source['fixed_lineup']['native_fixed_bounds']
        assert captured.source['account_user_id']==account
        assert captured.source['league_user_id']==ME
        assert captured.owner_context['user_id']==ME
        assert all(captured.owner_context['user_elo'][r.player.id]==r.elo for r in sess['service'].get_rankings().rankings)
    before=copy.deepcopy(captured.source)
    for name in ('load_member_rankings','load_league_preferences_bulk','load_asset_preferences','load_draft_picks'):
        monkeypatch.setattr(server,name,lambda *a,**k:pytest.fail('read after capture'))
    for version in adapter.VERSIONS:
        cards,diag=captured.run_arm(version)
        assert diag['native_count']>0 and cards
        if fixed_groups=='coupled-opponent':
            assert diag['unsupported_participant_count']==1 and diag['unsupported_pair_cards']>0
            assert all(c.target_user_id!='espn:'+LEAGUE+'.t2' for c in cards)
            assert captured.source['fixed_lineup']['unsupported_teams']
            assert captured.source['provider_provenance']['unsupported_native_eligibility']
        assert all(c.owner_evaluation.matches(c) and c.owner_evaluation.model_identity[1]==version for c in cards)
        assert all('raw-only-bench' not in c.give_player_ids+c.receive_player_ids for c in cards)
        assert all(c.roster_evaluation['eligible'] for c in cards)
        if os.environ.get('PROVIDER_PROOF_OUT'):
            out=Path(os.environ['PROVIDER_PROOF_OUT']);out.mkdir(parents=True,exist_ok=True)
            (out/f'{platform}-picks{int(picks_enabled)}-{version}.json').write_text(json.dumps({'synthetic':True,'platform':platform,'version':version,'source':captured.source,'diagnostics':diag,'cards':[{'target':c.target_user_id,'give':c.give_player_ids,'receive':c.receive_player_ids,'owner_proof':c.owner_evaluation.as_dict(),'roster_proof':c.roster_evaluation} for c in cards]},sort_keys=True,indent=2,default=str)+'\n')
    assert captured.source==before
