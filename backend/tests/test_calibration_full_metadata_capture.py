"""Production-shaped filtered metadata, actual capture identity and pair scopes."""
from copy import deepcopy
import json
import pytest
from backend import server,outlook_calibration_adapter as adapter,calibration_roster_metadata as metadata
from backend.tests.test_owner_generator_routes import harness,owner_harness,ME
from backend.tests.test_calibration_round_provider_identity import provider_world
from backend.tests.test_calibration_full_metadata import cache
from backend.tests.test_calibration_round_fingerprint import roster
from backend.tests.test_outlook_calibration_persistence import engine

ACTUAL_INPUT_IDENTITY = adapter._input_identity


def setup_full(provider_world,monkeypatch,cache):
    state,calls,sess=provider_world
    old=server._sleeper_get
    raw={p.id:{'player_id':p.id,'position':p.position,'fantasy_positions':[p.position],'active':True,'full_name':p.name} for p in sess['players']}
    raw['fixed-k']={'player_id':'fixed-k','position':'K','fantasy_positions':['K'],'active':True,'full_name':'Synthetic K'}
    monkeypatch.setattr(server,'_load_sleeper_cache',lambda:server._filter_bulk_players(raw))
    def fetch(url):
        if url==metadata.URL:return deepcopy(raw)
        value=old(url)
        if url.endswith('/rosters'):value[0]['players'].append('fixed-k')
        if isinstance(value,dict) and 'roster_positions' in value:value['roster_positions']+=['K']
        return value
    monkeypatch.setattr(server,'_sleeper_get',fetch)
    return raw


def test_actual_capture_consumes_full_fixed_metadata_not_priced_pool(provider_world,monkeypatch,cache):
    raw=setup_full(provider_world,monkeypatch,cache)
    value=adapter.capture(user_id=ME,league_user_id=ME,league_id='12345')
    assert 'fixed-k' in value.source['fixed_lineup']['assets']
    assert 'fixed-k' not in value.owner_context['players']
    assert value.source['full_metadata_observation']['held']['fixed-k']['position']=='K'
    assert value.source['full_roster_metadata']['normal_ranking_pool_expanded'] is False
    assert all('K' not in p['starter_slots'] for p in value.owner_context['manager_preferences'].values())


def test_consumed_A_cannot_be_labeled_newer_B_before_first_identity(provider_world,monkeypatch,cache):
    setup_full(provider_world,monkeypatch,cache)
    original=metadata.capture
    def race(fetch):
        observed=original(fetch)
        changed=deepcopy(observed);changed['observed_at']+=1
        changed['rows']['fixed-k']['active']=False
        changed['revision']=metadata._digest(changed['rows']);cache.write_text(json.dumps(changed))
        return observed
    monkeypatch.setattr(metadata,'capture',race)
    # Replace fixture's constant identity seam with the actual production function.
    monkeypatch.setattr(adapter, "_input_identity", ACTUAL_INPUT_IDENTITY)
    with pytest.raises(adapter.GradingError,match='inputs_changed_during_capture'):
        adapter.capture(user_id=ME,league_user_id=ME,league_id='12345')


def test_real_is_current_keeps_frozen_asof_across_missing_cache_but_rejects_newer_removal(roster,monkeypatch,cache):
    from types import SimpleNamespace
    monkeypatch.setattr(server, 'g_universal_by_format', {'1qb_ppr': {'players':[SimpleNamespace(id='p1')], 'seed':{'p1':1000}}})
    source_rows={'k':{'player_id':'k','position':'K','fantasy_positions':['K'],'active':True}}
    snap=metadata.capture(lambda _:source_rows);obs=metadata.observation(snap,['k'])
    before=adapter._input_identity('a','L',['k'],obs,True)
    source={'account_user_id':'a','league_user_id':'a','league_id':'L','captured_at':'2026-11-07T00:00:00+00:00',
        'captured_metadata_ids':['k'],'full_metadata_observation':obs,'input_identity':before}
    assert adapter.is_current(source,user_id='a',league_user_id='a',league_id='L')
    cache.unlink()
    assert adapter.is_current(source,user_id='a',league_user_id='a',league_id='L')
    changed=deepcopy(snap);changed['observed_at']+=1;changed['rows'].pop('k');changed['revision']=metadata._digest(changed['rows']);cache.write_text(json.dumps(changed))
    assert not adapter.is_current(source,user_id='a',league_user_id='a',league_id='L')
