import pytest
from backend import server,database as db,feature_flags as ff,outlook_calibration_adapter as adapter
from backend.tests.test_calibration_round_provider_identity import provider_world
from backend.tests.test_owner_generator_routes import harness,owner_harness,ME

@pytest.mark.parametrize('race',[False,True])
def test_sleeper_same_provider_pick_rows_bound_before_capture_window(provider_world,monkeypatch,owner_harness,race):
    state,_,_=provider_world
    _,engine,_,_,_=owner_harness
    fetch=server._sleeper_get
    def raw_fetch(url):
        if url.endswith('/traded_picks'):return []
        if url.endswith('/drafts'):return [{'season':'2026','status':'complete','settings':{'rounds':1}}]
        value=fetch(url)
        if url.endswith('/rosters'):
            for i,row in enumerate(value,1):row['roster_id']=i
        elif not url.endswith('/users'):
            value.update(season='2026',settings={'draft_rounds':1},total_rosters=2)
        return value
    monkeypatch.setattr(server,'_sleeper_get',raw_fetch)
    ff._flags_cache['trade.picks_in_pool']=True
    original=server._sync_sleeper_owned_picks
    captured_rows=[]
    def sync(*a,**k):
        result=original(*a,**k)
        captured_rows.extend(result or [])
        if race:
            with engine.begin() as conn:
                conn.execute(db.draft_picks_table.update().where(db.draft_picks_table.c.league_id=='12345').values(owner_user_id='wrong-owner'))
        return result
    monkeypatch.setattr(server,'_sync_sleeper_owned_picks',sync)
    if race:
        with pytest.raises(adapter.GradingError):adapter.capture(user_id=ME,league_user_id=state['owner'],league_id='12345')
    else:
        result=adapter.capture(user_id=ME,league_user_id=state['owner'],league_id='12345')
        assert captured_rows
        assert result.source['picks_included'] is True
    assert captured_rows
