from copy import deepcopy
from types import SimpleNamespace as N
import pytest
from backend.calibration_provider_capture import parse_espn,parse_mfl,_mfl_slots
from backend.espn_service import Crosswalk
from backend.blind_grading import GradingError

@pytest.fixture
def xwalk():
    return Crosswalk(by_name_pos={},by_espn_id={'1':'a','2':'b'},by_mfl_sleeper={'1':'a','2':'b'})

def espn_raw():
    return {'id':123,'seasonId':2026,'settings':{'size':2,'rosterSettings':{'lineupSlotCounts':{'4':1,'20':2,'21':1},'positionLimits':{}}},
            'teams':[{'id':i,'primaryOwner':'{OWNER-'+str(i)+'}','owners':[],'roster':{'entries':[{'lineupSlotId':4 if i==1 else 21,
            'playerPoolEntry':{'player':{'id':i,'fullName':'Player '+str(i),'defaultPositionId':3,'eligibleSlots':[4,5,7,20,21,23]}}}]}} for i in (1,2)]}

def mfl_raw():
    return {'league':{'league':{'id':'123','rosterSize':'3','injuredReserve':'1','taxiSquad':'2',
            'starters':{'count':'1','position':[{'name':'WR','limit':'1'}]},
            'franchises':{'count':'2','franchise':[{'id':'0001','name':'One'},{'id':'0002','name':'Two'}]}}},
            'rosters':{'rosters':{'franchise':[{'id':'0001','player':[{'id':'1','status':'ROSTER'}]},
                {'id':'0002','player':[{'id':'2','status':'TAXI_SQUAD'}]}]}},
            'players':{'players':{'player':[{'id':'1','name':'First, Player','position':'WR'},{'id':'2','name':'Second, Player','position':'WR'}]}},
            'rules':{'rules':{'positionRules':[{'positions':'RB|WR|TE','rule':{'event':'CC','points':'1','range':'0-100'}}]}},'futureDraftPicks':{'futureDraftPicks':{'franchise':[]}}}

def ep(raw,xwalk):return parse_espn(raw,league_id='123',user_id='me',team_id=1,xwalk=xwalk)
def mp(raw,xwalk):return parse_mfl(raw,league_id='123',user_id='me',franchise_id='0001',xwalk=xwalk)

def test_supported_espn_retains_ir_and_capacity(xwalk):
    snap=ep(espn_raw(),xwalk)
    assert snap.slots==['WR'] and snap.capacity==3
    assert snap.rosters[1]['reserve']==['b'] and snap.rosters[1]['players']==['b']

def test_supported_mfl_retains_taxi(xwalk):
    snap=mp(mfl_raw(),xwalk)
    assert snap.slots==['WR'] and snap.capacity==3
    assert snap.rosters[1]['taxi']==['b']

@pytest.mark.parametrize('provider', ['espn','mfl'])
def test_unknown_native_assets_fail_instead_of_disappear(xwalk,provider):
    xwalk.by_espn_id.clear();xwalk.by_mfl_sleeper.clear()
    with pytest.raises(GradingError):
        (ep if provider=='espn' else mp)((espn_raw if provider=='espn' else mfl_raw)(),xwalk)

@pytest.mark.parametrize('slot',[8,9,12,13,99])
def test_espn_unsupported_slots_fail(xwalk,slot):
    raw=espn_raw();raw['settings']['rosterSettings']['lineupSlotCounts'][str(slot)]=1
    with pytest.raises(GradingError):ep(raw,xwalk)

def test_mfl_range_with_per_position_cap_not_representable_rejected():
    with pytest.raises(GradingError):_mfl_slots({'starters':{'count':'5','position':[{'name':'WR','limit':'2-3'},{'name':'RB','limit':'1-3'}]}})

def test_mfl_exact_flex_range_preserved():
    slots=_mfl_slots({'starters':{'count':'5','position':[{'name':'WR','limit':'2-4'},{'name':'RB','limit':'1-3'}]}})
    assert slots==['WR','WR','RB','WRRB_FLEX','WRRB_FLEX']

@pytest.mark.parametrize('provider',['espn','mfl'])
def test_declared_team_count_cannot_exceed_observed_teams(xwalk,provider):
    raw=(espn_raw if provider=='espn' else mfl_raw)()
    if provider=='espn':raw['settings']['size']=3
    else:raw['league']['league']['franchises']['count']='3'
    with pytest.raises(GradingError): (ep if provider=='espn' else mp)(raw,xwalk)

def test_native_eligibility_not_overridden_by_sleeper_position(xwalk):
    snap=ep(espn_raw(),xwalk)
    league=N(members=[N(user_id=snap.rosters[1]['owner_id'],roster=['b'])])
    # This player is native WR-only but the cross-provider metadata says TE.
    ctx=snap.roster_context(viewer_id='me',league=league,
        players={'a':N(position='TE'),'b':N(position='WR')},
        consensus_value=lambda p:100,startable=lambda *a:True,
        player_metadata={'a':{'fantasy_positions':['TE']}},availability_fresh=True,viewer_roster=['a'])
    assert ctx.assets['a'].positions==frozenset(['WR'])

@pytest.mark.parametrize('provider', ['espn', 'mfl'])
def test_native_positions_apply_to_unranked_occupancy_too(xwalk, provider):
    from backend.calibration_roster_coverage import add_unranked_occupancy
    snapshot = (ep if provider == 'espn' else mp)((espn_raw if provider == 'espn' else mfl_raw)(), xwalk)
    metadata = snapshot.normalized_metadata({}, {'a': {'active':True, 'fantasy_positions':['TE']},
                                                  'b': {'active':True, 'fantasy_positions':['TE']}})
    ctx = snapshot.roster_context(viewer_id='me', league=N(members=[]), players={},
        consensus_value=lambda _: 0, startable=lambda *_: False,
        player_metadata=metadata, availability_fresh=True, viewer_roster=['a'])
    facts = add_unranked_occupancy(ctx, metadata)
    assert ctx.assets['a'].positions == frozenset({'WR'})
    assert facts['a']['market_value'] is None


def test_ranked_native_position_conflict_is_not_silently_repriced(xwalk):
    with pytest.raises(GradingError, match='provider_player_position_conflict'):
        ep(espn_raw(), xwalk).normalized_metadata({'a': N(position='TE')}, {'a': {'active':True}})


@pytest.mark.parametrize('key', ['rules','players'])
def test_mfl_fail_soft_exports_are_not_complete_capture(xwalk, key):
    raw = mfl_raw()
    raw[key] = {}
    with pytest.raises(GradingError, match='provider_rules_or_players_unavailable'):
        mp(raw, xwalk)


def test_mfl_future_picks_preserve_actual_current_owner_and_original(xwalk):
    raw = mfl_raw()
    raw['futureDraftPicks']['futureDraftPicks']['franchise'] = {
        'id':'0002', 'futureDraftPick': {'year':'2027','round':'1','originalPickFor':'0001'}}
    assert mp(raw, xwalk).future_picks == [{'franchise_id':'0002','year':'2027',
                                          'round':'1','original_owner':'0001'}]


@pytest.mark.parametrize('picks', [{}, {'franchise':['broken']}, {'franchise':[
    {'id':'0002','futureDraftPick':[{'year':'2027','round':'1','originalPickFor':'0001'}]*2}]}])
def test_unknown_or_duplicate_mfl_picks_refuse(xwalk, picks):
    raw = mfl_raw()
    raw['futureDraftPicks'] = {'futureDraftPicks': picks}
    with pytest.raises(GradingError, match='pick_ownership_unavailable'):
        mp(raw, xwalk)


@pytest.mark.parametrize('provider', ['espn','mfl'])
def test_unrepresented_roster_positions_not_dropped(xwalk, provider):
    raw = (espn_raw if provider == 'espn' else mfl_raw)()
    if provider == 'espn':
        raw['teams'][0]['roster']['entries'][0]['playerPoolEntry']['player']['defaultPositionId'] = 5
    else:
        raw['players']['players']['player'][0]['position'] = 'PK'
    with pytest.raises(GradingError, match='provider_player_eligibility_unsupported' if provider == 'espn' else 'provider_roster_position_unsupported'):
        (ep if provider == 'espn' else mp)(raw, xwalk)


def test_espn_known_position_limits_not_treated_as_unrestricted(xwalk):
    raw = espn_raw()
    raw['settings']['rosterSettings']['positionLimits'] = {'3': 1}
    with pytest.raises(GradingError, match='provider_position_limits_unsupported'):
        ep(raw, xwalk)

@pytest.mark.parametrize('field,value', [('year','0'), ('round','0'), ('year','not-year'), ('round','-1')])
def test_mfl_invalid_pick_coordinates_never_reach_persistence(xwalk, field, value):
    raw = mfl_raw()
    pick = {'year':'2027','round':'1','originalPickFor':'0001', field:value}
    raw['futureDraftPicks']['futureDraftPicks']['franchise'] = {'id':'0002', 'futureDraftPick':pick}
    with pytest.raises(GradingError, match='pick_ownership_unavailable'):
        mp(raw, xwalk)


@pytest.mark.parametrize('native,position,eligible', [
    (5,'K',[17]),(9,'DL',[11,15]),(10,'DL',[11,15]),
    (11,'LB',[10,15]),(12,'DB',[14,15]),(13,'DB',[14,15]),(16,'DEF',[16])])
def test_espn_fixed_group_holding_needs_no_priced_crosswalk(xwalk,native,position,eligible):
    raw=espn_raw()
    raw['settings']['rosterSettings']['lineupSlotCounts'].update({str(s):1 for s in [10,11,14,15,16,17]})
    raw['settings']['rosterSettings']['positionLimits']={'5':3}
    raw['teams'][0]['roster']['entries'].append({'lineupSlotId':20,
        'playerPoolEntry':{'player':{'id':999,'defaultPositionId':native,
          'eligibleSlots':eligible+[20,21],'injuryStatus':'ACTIVE'}}})
    snapshot=ep(raw,xwalk)
    pid='espn-fixed:123:999'
    assert pid in snapshot.rosters[0]['players']
    assert snapshot.positions[pid]==position
    metadata=snapshot.normalized_metadata({}, {'a':{'active':True},'b':{'active':True}})
    assert metadata[pid]['fantasy_positions']==[position]
    assert snapshot.capacity==9


def test_espn_defender_with_offense_eligibility_refuses_partition(xwalk):
    raw=espn_raw()
    raw['settings']['rosterSettings']['lineupSlotCounts']['14']=1
    raw['teams'][0]['roster']['entries'].append({'lineupSlotId':20,
        'playerPoolEntry':{'player':{'id':999,'defaultPositionId':12,'eligibleSlots':[4,14,20,21]}}})
    with pytest.raises(GradingError,match='provider_player_eligibility_unsupported'):ep(raw,xwalk)


@pytest.mark.parametrize('value',[True, [], {}, 1.5, float('nan'), float('inf'), 'NaN', '1.5'])
def test_fixed_native_identity_requires_canonical_integer(xwalk,value):
    raw=espn_raw();raw['settings']['rosterSettings']['lineupSlotCounts']['17']=1
    raw['teams'][0]['roster']['entries'].append({'lineupSlotId':20,
        'playerPoolEntry':{'player':{'id':value,'defaultPositionId':5,'eligibleSlots':[17,20,21]}}})
    with pytest.raises(GradingError,match='provider_roster_asset_unmapped'):ep(raw,xwalk)


def test_fixed_native_negative_def_identity_is_preserved(xwalk):
    raw=espn_raw();raw['settings']['rosterSettings']['lineupSlotCounts']['16']=1
    raw['teams'][0]['roster']['entries'].append({'lineupSlotId':20,
        'playerPoolEntry':{'player':{'id':'-0123','defaultPositionId':16,'eligibleSlots':[16,20,21]}}})
    assert 'espn-fixed:123:-123' in ep(raw,xwalk).rosters[0]['players']


@pytest.mark.parametrize('field,value,code',[('defaultPositionId',True,'provider_roster_position_unsupported'),
    ('defaultPositionId',5.0,'provider_roster_position_unsupported'),
    ('eligibleSlots',[17,False,20],'provider_player_eligibility_unsupported')])
def test_fixed_native_enums_cannot_use_boolean_numeric_aliases(xwalk,field,value,code):
    raw=espn_raw();raw['settings']['rosterSettings']['lineupSlotCounts']['17']=1
    player={'id':999,'defaultPositionId':5,'eligibleSlots':[17,20,21],field:value}
    raw['teams'][0]['roster']['entries'].append({'lineupSlotId':20,'playerPoolEntry':{'player':player}})
    with pytest.raises(GradingError,match=code):ep(raw,xwalk)
