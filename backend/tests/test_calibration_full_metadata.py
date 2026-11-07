"""Actual filtered-cache boundary and full metadata/currentness semantics."""
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace as N
import json
import pytest
from backend import calibration_roster_metadata as metadata, calibration_fixed_lineup as fixed
from backend import server, database as db
from backend.trade_roster import Asset,Context,Rules,Team
from backend.calibration_roster_coverage import add_unranked_occupancy
from backend.blind_grading import GradingError

@pytest.fixture
def cache(tmp_path,monkeypatch):
    monkeypatch.setattr(metadata,'CACHE_PATH',tmp_path/'public.json')
    return metadata.CACHE_PATH

def raw():
    return {'wr':{'player_id':'wr','position':'WR','full_name':'Synthetic','fantasy_positions':['WR'],'active':True},
            'k':{'player_id':'k','position':'K','full_name':'Synthetic','fantasy_positions':['K'],'active':True},
            'lb':{'player_id':'lb','position':'LB','full_name':'Synthetic','fantasy_positions':['LB'],'active':True},
            'def':{'player_id':'def','position':'DEF','full_name':'Synthetic','fantasy_positions':['DEF'],'active':True}}

def context():
    return Context('me',{'me':Team('me',('wr','k','lb','def'))},
        {'wr':Asset('wr',frozenset({'WR'}),100)},Rules(('WR','K','LB','DEF'),'observed',10))

def test_production_filtered_cache_omits_fixed_holdings_but_full_capture_resolves_without_pool_growth(cache):
    source=raw();filtered=server._filter_bulk_players(source)
    assert set(filtered)=={'wr'}
    ctx=context();proof=fixed.prepare(ctx,filtered);assert not proof['assets']
    calls=[]
    snap=metadata.capture(lambda url:(calls.append(url),deepcopy(source))[1])
    ctx=context();proof=fixed.prepare(ctx,snap['rows'])
    assert set(proof['assets'])=={'k','lb','def'}
    assert set(filtered)=={'wr'} and ctx.assets['wr'].value==100
    assert all(not ctx.assets[p].startable and not ctx.assets[p].positions for p in ('k','lb','def'))
    assert metadata.capture(lambda _:pytest.fail('fresh cache must coalesce'))==snap
    assert len(calls)==1
    assert 'full_name' not in next(iter(snap['rows'].values()))

@pytest.mark.parametrize('change',['position','fantasy_positions','active','injury_status','player_id','remove'])
def test_newer_known_held_changes_or_removal_invalidate_but_restart_does_not(cache,change):
    snap=metadata.capture(lambda _:raw());captured=metadata.observation(snap,['k'])
    before=metadata.held_identity(captured)
    cache.unlink();assert metadata.held_identity(captured)==before
    changed=deepcopy(snap);changed['observed_at']+=1
    if change=='remove':changed['rows'].pop('k')
    else:changed['rows']['k'][change]={'position':'LB','fantasy_positions':['LB'],'active':False,'injury_status':'OUT','player_id':'changed'}[change]
    changed['revision']=metadata._digest(changed['rows']);cache.write_text(json.dumps(changed))
    assert metadata.held_identity(captured)!=before
    assert metadata.held_identity(captured,captured_only=True)==before


def test_refresh_failure_keeps_previous_file_and_does_not_claim_freshness(cache,monkeypatch):
    snap=metadata.capture(lambda _:raw());before=cache.read_bytes()
    monkeypatch.setattr(metadata.time,'time',lambda:snap['observed_at']+metadata.TTL_SECONDS+1)
    def fail(_):raise TimeoutError('private URL omitted')
    with pytest.raises(GradingError,match='player_metadata_unavailable'):metadata.capture(fail)
    assert cache.read_bytes()==before


def test_pair_scope_never_turns_dual_asset_into_fixed_sentinel():
    ctx=context();ctx.rules=replace(ctx.rules,slots=('WR','DB'))
    ctx.teams['opponent']=Team('opponent',('dual',))
    ctx.assets['dual']=Asset('dual',frozenset({'WR','DB'}),200)
    rows=raw();rows['dual']={'fantasy_positions':['DB','WR'],'active':True}
    proof=fixed.prepare(ctx,rows,isolate_unsupported=True)
    assert set(proof['unsupported_teams'])=={'opponent'}
    assert proof['unsupported_teams']['opponent']['holdings']['dual']==['DB','WR']
    assert 'dual' not in proof['assets'] and ctx.assets['dual'].positions==frozenset({'WR','DB'})
    assert ctx.assets['dual'].value==200


def test_offense_only_projection_proves_unused_domain_and_retains_original_facts():
    rows={'dual':{'fantasy_positions':['DB','WR'],'active':True}}
    effective,proof=fixed.configured_metadata(rows,('WR','FLEX','DEF'),['dual'])
    assert effective['dual']['fantasy_positions']==['WR']
    assert rows['dual']['fantasy_positions']==['DB','WR']
    assert proof['dual']['original_positions']==['DB','WR']
    assert fixed.configured_metadata(rows,('WR','DB'),['dual'])[0]==rows


def test_failed_sparse_payload_cannot_replace_complete_metadata(cache):
    with pytest.raises(GradingError):metadata.capture(lambda _:[])
    assert not cache.exists()
