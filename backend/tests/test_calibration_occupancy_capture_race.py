import pytest
from backend import server,outlook_calibration_adapter as adapter
from backend.blind_grading import GradingError
from backend.tests.test_calibration_round_provider_identity import provider_world
from backend.tests.test_owner_generator_routes import harness,owner_harness,ME
REAL_IDENTITY=adapter._input_identity

def test_raw_only_unranked_metadata_change_during_capture_rejected(provider_world,monkeypatch):
    state,_,sess=provider_world
    fetch=server._sleeper_get
    def fresh_fetch(url):
        value=fetch(url)
        if url.endswith('/rosters'):value[0]['players'].append('raw-only-bench')
        return value
    metadata={p.id:{'fantasy_positions':[p.position]} for p in sess['players']}
    metadata['raw-only-bench']={'position':'RB','fantasy_positions':['RB'],'active':True}
    reads=[]
    def cache():
        reads.append(1)
        if len(reads)==2:metadata['raw-only-bench']['active']=False
        return metadata
    monkeypatch.setattr(server,'_sleeper_get',fresh_fetch)
    monkeypatch.setattr(server,'_load_sleeper_cache',cache)
    monkeypatch.setattr(adapter,'_input_identity',REAL_IDENTITY)
    with pytest.raises(GradingError) as error:
        adapter.capture(user_id=ME,league_user_id=state['owner'],league_id='12345')
    assert error.value.code=='inputs_changed_during_capture'
    assert len(reads)>=3
