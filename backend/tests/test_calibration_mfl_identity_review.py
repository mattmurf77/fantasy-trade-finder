"""Independent reviewer acceptance cases, copied with permission; synthetic only."""
from copy import deepcopy
import json
import pytest
from backend import database as db,server
from backend import calibration_provider_capture as capture
from backend.blind_grading import GradingError
from backend.tests.test_outlook_calibration_persistence import engine
from backend.tests.test_calibration_provider_parsers import mfl_raw,xwalk

@pytest.fixture
def setup(engine,monkeypatch,xwalk):
 with engine.begin() as conn:
  conn.execute(db.leagues_table.insert().values(sleeper_league_id='123',user_id='account',platform='mfl',platform_auth='cookie',platform_my_team='0001',platform_host='www1',platform_season=2026,default_scoring='ppr'))
 raw=mfl_raw();seen=[]
 def cred(uid):
  seen.append(uid);assert uid=='account-1','Borrowed importer credential'
  return {'cookie_encrypted':'own-encrypted','created_at':'first','updated_at':'now'}
 monkeypatch.setattr(db,'get_mfl_credential',cred)
 monkeypatch.setattr(server._sleeper_write,'decrypt_token',lambda text:'own-token' if text=='own-encrypted' else pytest.fail('foreignsecret'))
 monkeypatch.setattr(capture.mfl,'fetch_my_leagues',lambda cookie,year:[{'league_id':'123','franchise_id':'0002'}] if cookie=='own-token' else pytest.fail('foreigncookie'))
 monkeypatch.setattr(capture.mfl,'fetch_league_bundle',lambda *a,**k:deepcopy(raw) if k.get('cookie')=='own-token' else pytest.fail('borrowed'))
 monkeypatch.setattr(server,'_shared_crosswalk',lambda:xwalk)
 return raw,seen

def test_own_cookie_canonical_seat_no_importer_mutation(setup,engine):
 result=capture.capture_linked(user_id='account-1',league_id='123')
 assert result.resolved['league_user_id']=='mfl:123.f0002'
 assert result.resolved['user_player_ids']==['b']
 assert result.resolved['opponent_rosters'][0]['user_id']=='account'
 assert result.provenance['account_user_id']=='account-1'
 assert result.provenance['canonical_owner_map']=={'0001':'account','0002':'mfl:123.f0002'}
 assert 'own-token' not in json.dumps(result.provenance)
 assert set(setup[1])=={'account-1'}
 with engine.connect() as conn:
  row=conn.execute(db.select(db.leagues_table)).mappings().one()
  assert row['user_id']=='account' and row['platform_my_team']=='0001'

@pytest.mark.parametrize('seats',[[],['0001','0002'],['9999']])
def test_no_or_ambiguous_or_unknown_current_seat_refuses(setup,monkeypatch,seats):
 monkeypatch.setattr(capture.mfl,'fetch_my_leagues',lambda *a:[{'league_id':'123','franchise_id':s} for s in seats])
 with pytest.raises(GradingError,match='league_seat_changed'):
  capture.capture_linked(user_id='account-1',league_id='123')

def test_nonimporter_without_own_cookie_never_uses_public_or_importer(setup,monkeypatch):
 monkeypatch.setattr(db,'get_mfl_credential',lambda uid:None if uid=='account-1' else pytest.fail('foreign'))
 monkeypatch.setattr(capture.mfl,'fetch_my_leagues',lambda *a:pytest.fail('network'))
 monkeypatch.setattr(capture.mfl,'fetch_league_bundle',lambda *a,**k:pytest.fail('network'))
 with pytest.raises(GradingError,match='mfl_credentials_unavailable'):
  capture.capture_linked(user_id='account-1',league_id='123')

def test_canonical_pick_ownership_is_not_rewritten_to_private_account(setup):
 raw=setup[0]
 raw['futureDraftPicks']['futureDraftPicks']['franchise']=[{'id':'0002','futureDraftPick':{'year':'2027','round':'1','originalPickFor':'0001'}}]
 result=capture.capture_linked(user_id='account-1',league_id='123')
 pid=server.make_pick_id('123',2027,1,'0001')
 picks=[dict(pick_id=pid,owner_user_id='mfl:123.f0002',original_user_id='account',season=2027,round=1)]
 result.validate_owned_picks(picks)
 picks[0]['owner_user_id']='account-1'
 with pytest.raises(GradingError,match='provider_pick_ownership_changed'):result.validate_owned_picks(picks)
