import pytest
from types import SimpleNamespace as N
from datetime import datetime, timezone
from backend import server,outlook_calibration_adapter as adapter
from backend.tests.test_calibration_round_fingerprint import roster
from backend.tests.test_outlook_calibration_persistence import engine

@pytest.mark.parametrize('field,value',[('active',False),('position','QB'),('player_id','different'),('fantasy_positions',['QB']),('injury_status','IR')])
def test_raw_only_unranked_holding_binds_all_consumed_metadata(roster,monkeypatch,field,value):
    metadata={'raw-only':{'position':'RB','fantasy_positions':['RB'],'player_id':'raw-only','active':True,'injury_status':None}}
    monkeypatch.setattr(server,'_load_sleeper_cache',lambda:metadata)
    captured_ids=['raw-only']
    monkeypatch.setattr(server,'g_universal_by_format',{'1qb_ppr':{'players':[N(id='ranked')]}})
    before=adapter._input_identity('a','L',captured_ids)
    legacy=adapter._input_identity('a','L')
    source={'account_user_id':'a','league_user_id':'a','league_id':'L', 'captured_metadata_ids':captured_ids,'input_identity':before,'captured_at':datetime.now(timezone.utc).isoformat()}
    assert adapter.is_current(source,user_id='a',league_user_id='a',league_id='L')
    metadata['raw-only'][field]=value
    assert adapter._input_identity('a','L')==legacy  # Explicitly absent DB and pool.
    assert adapter._input_identity('a','L',captured_ids)!=before

    assert not adapter.is_current(source,user_id='a',league_user_id='a',league_id='L')
