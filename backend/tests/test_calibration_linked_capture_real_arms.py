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

@pytest.mark.parametrize('platform,picks_enabled,race',[('espn',False,False),('espn',True,False),('mfl',False,False),('mfl',True,False),('mfl',True,True)])
def test_linked_capture_runs_both_models_from_same_raw_snapshot(large_exclusive,monkeypatch,platform,picks_enabled,race):
    _,engine,sess,_,league=large_exclusive
    with engine.begin() as conn:
        conn.execute(db.leagues_table.insert().values(sleeper_league_id=LEAGUE,
            platform=platform,user_id=ME,espn_my_team_id=1,espn_auth='public',platform_my_team='0001',platform_auth='public',platform_host='www1'))
        conn.execute(db.league_members_table.insert().values(league_id=LEAGUE,user_id=ME,roster_data=json.dumps(sess['user_roster'])))
    native={p.id:str(i) for i,p in enumerate(sess['players'],1)}
    native['raw-only-bench']='9999'
    cross=Crosswalk(by_name_pos={},by_espn_id={v:k for k,v in native.items()},by_mfl_sleeper={v:k for k,v in native.items()})
    teams=[(i,m) for i,m in enumerate(league.members,1)]
    if platform=='espn':
        raw={'id':int(LEAGUE),'seasonId':2026,'settings':{'size':len(teams),'rosterSettings':{'lineupSlotCounts':{'4':1,'20':20,'21':1}}},'teams':[]}
        for i,m in teams:
            holdings=list(m.roster)+(['raw-only-bench'] if i==1 else [])
            raw['teams'].append({'id':i,'roster':{'entries':[{'lineupSlotId':20,'playerPoolEntry':{'player':{'id':int(native[p]),'fullName':p,'defaultPositionId':3,'eligibleSlots':[4,5,7,20,21,23]}}} for p in holdings]}})
        monkeypatch.setattr(provider.espn,'fetch_league',lambda *a,**k:copy.deepcopy(raw))
        remap={m.user_id:f'espn:{LEAGUE}.t{i}' for i,m in teams if i!=1}
    else:
        raw={'league':{'league':{'id':LEAGUE,'rosterSize':'21','injuredReserve':'1','taxiSquad':'2','starters':{'count':'1','position':[{'name':'WR','limit':'1'}]},'franchises':{'count':str(len(teams)),'franchise':[{'id':f'{i:04}','name':m.user_id} for i,m in teams]}}},
             'rosters':{'rosters':{'franchise':[{'id':f'{i:04}','player':[{'id':native[p],'status':'ROSTER'} for p in list(m.roster)+(['raw-only-bench'] if i==1 else [])]} for i,m in teams]}},
             'players':{'players':{'player':[{'id':v,'name':p,'position':'WR'} for p,v in native.items()]}},
             'rules':{'rules':{'positionRules':{'positions':'WR|RB|TE','rule':{'event':'CC','points':'1'}}}},'futureDraftPicks':{'futureDraftPicks':{'franchise':[]}}}
        if picks_enabled:
            raw['futureDraftPicks']['futureDraftPicks']['franchise']=[{'id':'0002','futureDraftPick':[{'year':'2027','round':'1','originalPickFor':'0001'}]}]
        monkeypatch.setattr(provider.mfl,'fetch_league_bundle',lambda *a,**k:copy.deepcopy(raw))
        remap={m.user_id:f'mfl:{LEAGUE}.f{i:04}' for i,m in teams if i!=1}
    with engine.begin() as conn:
        existing=set(conn.execute(db.select(db.users_table.c.sleeper_user_id)).scalars())
        for uid in {ME,*remap.values()}-existing:
            conn.execute(db.users_table.insert().values(sleeper_user_id=uid,created_at='2026-11-01T00:00:00+00:00',verified_via='sleeper'))
    boards=server.load_member_rankings(LEAGUE)
    monkeypatch.setattr(server,'load_member_rankings',lambda *a,**k:{remap.get(uid,uid):board for uid,board in boards.items()})
    monkeypatch.setattr(server,'_shared_crosswalk',lambda:cross)
    monkeypatch.setattr(server,'_sleeper_get',lambda *a:pytest.fail('unexpected Sleeper league request'))
    monkeypatch.setattr(server,'_extension_ranking_services',lambda uid,**k:{'1qb_ppr':sess['service']} if uid==ME else pytest.fail('wrong account board'))
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
    captured=adapter.capture(user_id=ME,league_user_id=ME,league_id=LEAGUE)
    assert captured.source['platform']==platform
    assert set(captured.source['registered_participants'])=={ME,*remap.values()}
    assert set(captured.source['registered_participant_revisions'])=={ME,*remap.values()}
    assert captured.source['unpriced_occupancy']['raw-only-bench']['market_value'] is None
    assert captured.source['picks_included'] is (picks_enabled and platform=='mfl')
    if picks_enabled and platform=='mfl':
        rows=db.load_draft_picks(LEAGUE)
        assert len(rows)==1
        assert rows[0]['owner_user_id']==f'mfl:{LEAGUE}.f0002'
        assert rows[0]['original_user_id']==ME
        assert rows[0]['pick_id'] in captured.roster_context.teams[f'mfl:{LEAGUE}.f0002'].roster
        assert rows[0]['pick_id'] not in captured.roster_context.teams[ME].roster
    before=copy.deepcopy(captured.source)
    for name in ('load_member_rankings','load_league_preferences_bulk','load_asset_preferences','load_draft_picks'):
        monkeypatch.setattr(server,name,lambda *a,**k:pytest.fail('read after capture'))
    for version in adapter.VERSIONS:
        cards,diag=captured.run_arm(version)
        assert diag['native_count']>0 and cards
        assert all(c.owner_evaluation.matches(c) and c.owner_evaluation.model_identity[1]==version for c in cards)
        assert all('raw-only-bench' not in c.give_player_ids+c.receive_player_ids for c in cards)
        assert all(c.roster_evaluation['eligible'] for c in cards)
        if os.environ.get('PROVIDER_PROOF_OUT'):
            out=Path(os.environ['PROVIDER_PROOF_OUT']);out.mkdir(parents=True,exist_ok=True)
            (out/f'{platform}-picks{int(picks_enabled)}-{version}.json').write_text(json.dumps({'synthetic':True,'platform':platform,'version':version,'source':captured.source,'diagnostics':diag,'cards':[{'target':c.target_user_id,'give':c.give_player_ids,'receive':c.receive_player_ids,'owner_proof':c.owner_evaluation.as_dict(),'roster_proof':c.roster_evaluation} for c in cards]},sort_keys=True,indent=2,default=str)+'\n')
    assert captured.source==before
