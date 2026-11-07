import pytest
from backend import database as db,server
from backend import calibration_provider_capture as capture
from backend.blind_grading import GradingError
from backend.tests.test_outlook_calibration_persistence import engine
from backend.tests.test_calibration_provider_parsers import espn_raw,xwalk


def league(engine,platform,**kwargs):
    with engine.begin() as conn:
        conn.execute(db.leagues_table.insert().values(sleeper_league_id='123',user_id='account',platform=platform,**kwargs))

@pytest.mark.parametrize('platform',['espn','mfl'])
def test_missing_own_credentials_never_borrows_other_account(engine,monkeypatch,platform):
    league(engine,platform,**({'espn_auth':'cookie','espn_my_team_id':1} if platform=='espn' else {'platform_auth':'cookie','platform_my_team':'0001'}))
    read=[]
    def credentials(uid):
        read.append(uid)
        assert uid=='account'
        return None
    monkeypatch.setattr(db,'get_'+platform+'_credential',credentials)
    monkeypatch.setattr(capture.espn,'fetch_league',lambda *a,**k:pytest.fail('provider called without required credentials'))
    monkeypatch.setattr(capture.mfl,'fetch_league_bundle',lambda *a,**k:pytest.fail('provider called without required credentials'))
    with pytest.raises(GradingError) as error:capture.capture_linked(user_id='account',league_id='123')
    assert error.value.code==platform+'_credentials_unavailable'
    assert read and set(read)=={'account'}

@pytest.mark.parametrize('platform',['espn','mfl'])
def test_stored_other_account_binding_does_not_allow_impersonation(engine,platform):
    league(engine,platform)
    with pytest.raises(GradingError) as error:capture.capture_linked(user_id='different-account',league_id='123')
    assert error.value.code=='provider_account_binding_unavailable'


def test_espn_owner_change_rejected_even_with_working_cookies(engine,monkeypatch):
    league(engine,'espn',espn_auth='cookie',espn_my_team_id=1)
    monkeypatch.setattr(db,'get_espn_credential',lambda uid:{'espn_s2_encrypted':'synthetic','swid':'{AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA}'})
    monkeypatch.setattr(server._sleeper_write,'decrypt_token',lambda text:'synthetic-token')
    monkeypatch.setattr(capture.espn,'fetch_league',lambda *a,**k:espn_raw())
    with pytest.raises(GradingError) as error:capture.capture_linked(user_id='account',league_id='123')
    assert error.value.code=='league_seat_changed'


def test_espn_current_coowner_uses_own_credential_without_rewriting_account(engine,monkeypatch,xwalk):
    league(engine,'espn',espn_auth='cookie',espn_my_team_id=1)
    swid='{AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA}'
    monkeypatch.setattr(db,'get_espn_credential',lambda uid:{'espn_s2_encrypted':'synthetic','swid':swid})
    monkeypatch.setattr(server._sleeper_write,'decrypt_token',lambda text:'synthetic-token')
    raw=espn_raw();raw['teams'][0]['owners']=[swid]
    monkeypatch.setattr(capture.espn,'fetch_league',lambda *a,**k:raw)
    monkeypatch.setattr(server,'_shared_crosswalk',lambda:xwalk)
    snapshot=capture.capture_linked(user_id='account',league_id='123')
    assert snapshot.resolved['league_user_id']=='account'
    assert snapshot.provenance['ownership_basis']=='current_provider_owner'
    assert 'synthetic-token' not in str(snapshot.provenance)
    assert 'AAAAAAAA' not in str(snapshot.provenance)

@pytest.mark.parametrize('platform',['espn','mfl'])
def test_expired_credentials_raise_explicit_reconnection_without_fallback(engine, monkeypatch, platform):
    from backend.tests.test_calibration_provider_parsers import mfl_raw
    league(engine, platform, **({'espn_auth':'cookie','espn_my_team_id':1} if platform=='espn'
                               else {'platform_auth':'cookie','platform_my_team':'0001'}))
    monkeypatch.setattr(db, 'get_'+platform+'_credential', lambda uid:{
        'espn_s2_encrypted':'fake','cookie_encrypted':'fake','swid':'{OWN}'})
    monkeypatch.setattr(server._sleeper_write, 'decrypt_token', lambda _: 'fake-token')
    def expired(*a, **k):
        raise capture.espn.EspnAuthError() if platform=='espn' else capture.mfl.MflAuthError()
    monkeypatch.setattr(capture.espn, 'fetch_league', expired)
    monkeypatch.setattr(capture.mfl, 'fetch_my_leagues', expired)
    with pytest.raises(GradingError, match=platform+'_auth_required'):
        capture.capture_linked(user_id='account', league_id='123')


@pytest.mark.parametrize('platform',['espn','mfl'])
def test_undecryptable_own_credentials_are_not_replaced_with_public_read(engine, monkeypatch, platform):
    league(engine, platform, **({'espn_auth':'cookie','espn_my_team_id':1} if platform=='espn'
                               else {'platform_auth':'cookie','platform_my_team':'0001'}))
    monkeypatch.setattr(db, 'get_'+platform+'_credential', lambda uid:{
        'espn_s2_encrypted':'fake','cookie_encrypted':'fake','swid':'{OWN}'})
    def bad(_): raise ValueError('sensitive simulated payload')
    monkeypatch.setattr(server._sleeper_write, 'decrypt_token', bad)
    with pytest.raises(GradingError) as error:
        capture.capture_linked(user_id='account', league_id='123')
    assert error.value.code == platform+'_credentials_unavailable'
    assert 'sensitive' not in str(error.value)


def test_espn_wrong_response_season_rejected(engine, monkeypatch):
    league(engine, 'espn', espn_auth='public', espn_my_team_id=1, espn_season=2026)
    raw = espn_raw(); raw['seasonId'] = 2025
    monkeypatch.setattr(capture.espn, 'fetch_league', lambda *a, **k:raw)
    with pytest.raises(GradingError, match='provider_season_mismatch'):
        capture.capture_linked(user_id='account', league_id='123')


def test_espn_observed_superflex_cannot_use_stale_1qb_valuation(engine, monkeypatch, xwalk):
    league(engine, 'espn', espn_auth='public', espn_my_team_id=1, espn_season=2026)
    raw = espn_raw(); raw['settings']['rosterSettings']['lineupSlotCounts']['7'] = 1
    monkeypatch.setattr(capture.espn, 'fetch_league', lambda *a, **k:raw)
    monkeypatch.setattr(server, '_shared_crosswalk', lambda:xwalk)
    with pytest.raises(GradingError, match='provider_scoring_format_changed'):
        capture.capture_linked(user_id='account', league_id='123')


def test_espn_manual_tep_basis_is_retained_without_claiming_native_verification(engine, monkeypatch, xwalk):
    league(engine, 'espn', espn_auth='public', espn_my_team_id=1, default_scoring='sf_tep')
    monkeypatch.setattr(capture.espn, 'fetch_league', lambda *a, **k:espn_raw())
    monkeypatch.setattr(server, '_shared_crosswalk', lambda:xwalk)
    result = capture.capture_linked(user_id='account', league_id='123')
    assert result.provenance['native_tep_verification'] == 'unknown'
    assert result.provenance['valuation_basis'] == 'stored_configured_format'


@pytest.mark.parametrize('mode', ['sf', 'tep'])
def test_mfl_canonical_fresh_format_mismatch_refuses(engine, monkeypatch, xwalk, mode):
    from backend.tests.test_calibration_provider_parsers import mfl_raw
    league(engine, 'mfl', platform_auth='public', platform_my_team='0001', platform_host='www1')
    raw = mfl_raw()
    if mode == 'sf':
        raw['league']['league']['starters'] = {'count':'3','position':[{'name':'QB','limit':'2'},{'name':'WR','limit':'1'}]}
    else:
        raw['rules']['rules']['positionRules'] = [
            {'positions':'WR', 'rule':{'event':'CC','points':'1'}},
            {'positions':'TE', 'rule':{'event':'CC','points':'2'}}]
    monkeypatch.setattr(capture.mfl, 'fetch_league_bundle', lambda *a, **k:raw)
    monkeypatch.setattr(server, '_shared_crosswalk', lambda:xwalk)
    with pytest.raises(GradingError, match='provider_scoring_format_changed'):
        capture.capture_linked(user_id='account', league_id='123')
