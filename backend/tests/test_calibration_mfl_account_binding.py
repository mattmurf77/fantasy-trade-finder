"""Caller authentication and private identity never rewrite canonical ownership."""
import pytest
from backend import database as db,server
from backend import calibration_provider_capture as capture
from backend.blind_grading import GradingError
from backend.tests.test_outlook_calibration_persistence import engine
from backend.tests.test_calibration_provider_parsers import mfl_raw,xwalk
from backend.tests.test_calibration_provider_credentials import league

@pytest.mark.parametrize('franchise,seat',[('0001','account'),('0002','mfl:123.f0002')])
def test_own_second_account_resolves_seat_without_importer_credential_or_global_rewrite(engine,monkeypatch,xwalk,franchise,seat):
    league(engine,'mfl',platform_auth='cookie',platform_my_team='0001',platform_host='www1')
    reads=[]
    def credential(uid):
        reads.append(uid);assert uid=='second';return {'cookie_encrypted':'synthetic-own','updated_at':'revision1'}
    monkeypatch.setattr(db,'get_mfl_credential',credential)
    monkeypatch.setattr(server._sleeper_write,'decrypt_token',lambda raw:'own-cookie' if raw=='synthetic-own' else pytest.fail('borrowed'))
    monkeypatch.setattr(capture.mfl,'fetch_my_leagues',lambda cookie,year:[{'league_id':'123','franchise_id':franchise}] if cookie=='own-cookie' else pytest.fail('borrowed cookie'))
    monkeypatch.setattr(capture.mfl,'fetch_league_bundle',lambda *a,**kw:mfl_raw() if kw['cookie']=='own-cookie' else pytest.fail('borrowed cookie'))
    monkeypatch.setattr(server,'_shared_crosswalk',lambda:xwalk)
    snapshot=capture.capture_linked(user_id='second',league_id='123')
    assert snapshot.resolved['league_user_id']==seat
    assert snapshot.provenance['account_user_id']=='second'
    assert snapshot.provenance['canonical_owner_map']=={'0001':'account','0002':'mfl:123.f0002'}
    assert 'own-cookie' not in str(snapshot.provenance)
    assert set(reads)=={'second'}
    with engine.connect() as conn:assert conn.execute(db.select(db.leagues_table.c.user_id)).scalar()=='account'

@pytest.mark.parametrize('owned',[[],[{'league_id':'different','franchise_id':'0001'}],
    [{'league_id':'123','franchise_id':'0001'},{'league_id':'123','franchise_id':'0002'}]])
def test_ambiguous_or_missing_fresh_owned_seat_fails_before_bundle(engine,monkeypatch,owned):
    league(engine,'mfl',platform_auth='cookie',platform_my_team='0001')
    monkeypatch.setattr(db,'get_mfl_credential',lambda uid:{'cookie_encrypted':'own'})
    monkeypatch.setattr(server._sleeper_write,'decrypt_token',lambda raw:'own')
    monkeypatch.setattr(capture.mfl,'fetch_my_leagues',lambda *a:owned)
    monkeypatch.setattr(capture.mfl,'fetch_league_bundle',lambda *a,**k:pytest.fail('invalid seat fetched'))
    with pytest.raises(GradingError,match='league_seat_changed'):capture.capture_linked(user_id='second',league_id='123')


def test_missing_canonical_importer_franchise_cannot_rekey_all_owned_picks(engine,monkeypatch,xwalk):
    league(engine,'mfl',platform_auth='cookie',platform_my_team='absent-franchise',platform_host='www1')
    monkeypatch.setattr(db,'get_mfl_credential',lambda uid:{'cookie_encrypted':'own'})
    monkeypatch.setattr(server._sleeper_write,'decrypt_token',lambda raw:'own')
    monkeypatch.setattr(capture.mfl,'fetch_my_leagues',lambda *a:[{'league_id':'123','franchise_id':'0002'}])
    monkeypatch.setattr(capture.mfl,'fetch_league_bundle',lambda *a,**kw:mfl_raw())
    monkeypatch.setattr(server,'_shared_crosswalk',lambda:xwalk)
    with pytest.raises(GradingError,match='league_seat_changed'):capture.capture_linked(user_id='second',league_id='123')
