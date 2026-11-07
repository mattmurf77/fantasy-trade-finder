"""Stored platform identity changes cannot reuse a prepared comparison."""
import pytest
from backend import database as db, outlook_calibration_adapter as adapter, server
from backend.tests.test_calibration_round_fingerprint import roster, engine


@pytest.mark.parametrize('platform,key,changed', [
    ('espn','espn_my_team_id',2), ('espn','espn_season',2027),
    ('espn','espn_auth','cookie'), ('mfl','platform_my_team','0002'),
    ('mfl','platform_host','www2'), ('mfl','platform_season',2027),
    ('mfl','platform_auth','cookie'), ('mfl','user_id','different'),
    ('espn','default_scoring','sf_tep'), ('mfl','default_scoring','sf_tep')])
def test_stored_binding_semantics_participate_in_source_identity(roster, engine, platform, key, changed):
    with engine.begin() as conn:
        conn.execute(db.leagues_table.update().values(platform=platform, espn_my_team_id=1,
            espn_season=2026, espn_auth='public', platform_my_team='0001',
            platform_host='www1', platform_season=2026, platform_auth='public'))
    before = adapter._input_identity('a','L')
    with engine.begin() as conn:
        conn.execute(db.leagues_table.update().values(**{key:changed}))
    assert adapter._input_identity('a','L') != before


@pytest.mark.parametrize('platform',['espn','mfl'])
def test_credential_revision_invalidation_never_serializes_secret(roster, engine, platform):
    from backend.calibration_provider_capture import binding_identity
    with engine.begin() as conn:
        conn.execute(db.leagues_table.update().values(platform=platform))
        table = db.espn_credentials_table if platform=='espn' else db.mfl_credentials_table
        values = {'espn_s2_encrypted':'never-output-cookie', 'swid':'private-owner'} if platform=='espn' else {'cookie_encrypted':'never-output-cookie'}
        conn.execute(table.insert().values(user_id='a',created_at='first',updated_at='first',**values))
    source = binding_identity('a','L')
    assert 'never-output-cookie' not in str(source) and 'private-owner' not in str(source)
    before = adapter._input_identity('a','L')
    with engine.begin() as conn:
        conn.execute(table.update().values(updated_at='next'))
    assert adapter._input_identity('a','L') != before
