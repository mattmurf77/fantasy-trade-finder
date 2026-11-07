"""Real owner v2/v3 engines, final evaluators, roster/significance/presentment/quality.
Synthetic frozen inputs; intentionally separate from provider-capture tests.
"""
import copy
import json
import os
from pathlib import Path
import pytest
from backend import server, trade_service as ts, bakeoff_runner as bakeoff, deck_quality
from backend import trade_bilateral_presentment as present
from backend.outlook_calibration_adapter import CapturedComparison, VERSIONS
from backend.trade_roster_adapter import build_context
from backend.blind_grading import Catalog
from backend.trade_input_evidence import request_evidence
from backend.trade_gen_outlook_evidence import INPUT_VERSION
from backend.tests.test_owner_generator_routes import harness, owner_harness
from backend.tests.test_owner_only_routes import exclusive, large_exclusive, ME

@pytest.fixture
def captured(large_exclusive):
    _,_,sess,svc,league=large_exclusive
    players=svc._players
    ranking=sess['service']
    seed=dict(ranking._seed)
    cfg=dict(ts._cfg)
    cfg.update(owner_bilateral_enabled=1.,owner_bilateral_revision_enabled=1.,owner_outlook_evidence_enabled=1.)
    context=server._owner_generation_context(sess=sess,service=ranking,league=league,players=players,
        seed_map=seed,user_elo={r.player.id:r.elo for r in ranking.get_rankings().rankings},
        user_roster=sess['user_roster'],scoring_format='1qb_ppr',fairness_threshold=.75,captured_config=cfg)
    for pref in context['manager_preferences'].values():
        pref.update(starter_slots=['WR'],lineup_source='observed',roster_capacity=16)
    context['input_evidence']=request_evidence(context)
    context['input_evidence'].update(schema_version=INPUT_VERSION,used_in_model=True,
                                     age_use='diagnostic_only_not_production_fit')
    raw=[{'owner_id':m.user_id,'players':list(m.roster),'reserve':[],'taxi':[]} for m in league.members]
    roster=build_context(viewer_id=ME,league=context['league'],players=context['players'],
        consensus_value=ts.make_consensus_value_fn(seed,players),startable=lambda *a:True,
        slots=['WR'],platform='sleeper',raw_rosters=raw,capacity=16,availability_fresh=True,
        viewer_roster=sess['user_roster'])
    catalog=Catalog({}, {}, {})
    return CapturedComparison(context,catalog,{'synthetic':True},roster,
                              (0,server._trade_significance.VERSION,'second',True),True)

def fingerprint(cards):
    return [(c.target_user_id,tuple(c.give_player_ids),tuple(c.receive_player_ids),c.owner_evaluation.as_dict())
            for c in cards]

@pytest.mark.parametrize('version',VERSIONS)
def test_actual_adapter_matches_independent_same_gate_reconstruction(captured,version,monkeypatch):
    # No loader may run after capture; captures must not lazily reread live state.
    for name in ('load_member_rankings','load_league_preferences_bulk','load_asset_preferences',
                 'load_draft_picks','_load_trade_disposition_keys','_load_presentment_exclusions'):
        monkeypatch.setattr(server,name,lambda *a,**k:pytest.fail('postcapture database read'))
    before=copy.deepcopy(captured.owner_context)
    actual,diag=captured.run_arm(version)
    assert diag['native_count']>0
    assert diag['validated_count']==diag['native_count']
    assert diag['roster_count']>0
    assert actual
    assert {c.owner_evaluation.model_identity[1] for c in actual}=={version}
    assert all(c.owner_evaluation.matches(c) for c in actual)
    context=copy.deepcopy(before)
    context['config']['owner_outlook_evidence_enabled']=float(version==VERSIONS[1])
    if version==VERSIONS[0]:context.pop('input_evidence',None)
    with ts._cfg_override(context['config']):
        native,report=bakeoff.owner_generator(context['config'])(**context)
        valid=server._owner_cards_valid(native,context)
        retained,_,_=server._evaluate_deck_rosters(valid,copy.deepcopy(captured.roster_context),enforce=True,require_mutual=False)
        kept={id(c) for c in retained}
        retained=[c for c in valid if id(c) in kept]
        retained,_,_=server._evaluate_trade_significance(retained,capture=captured.significance,
            players=context['players'],user_elo=context['user_elo'],seed_elo=context['seed_elo'],
            scoring_format=context['scoring_format'],user_sources=context['user_sources'])
        retained,_=present.present(retained,generator_version=version)
        rosters={m.user_id:list(m.roster) for m in context['league'].members}
        rosters[context['user_id']]=list(context['user_roster'])
        expected,_=deck_quality.filter_deck(retained,viewer_id=context['user_id'],
            market=lambda pid:ts.elo_to_value(context['seed_elo'][pid]) if pid in context['seed_elo'] else None,
            position=lambda pid:getattr(context['players'].get(pid),'position',None),
            rosters=rosters,lineup_slots=list(captured.roster_context.rules.slots))
    assert fingerprint(actual)==fingerprint(expected)
    # Both calls must leave the common captured input/version selector untouched.
    assert captured.owner_context['config']==before['config']
    assert captured.owner_context['manager_preferences']==before['manager_preferences']
    if os.environ.get('CALIBRATION_PROOF_OUT'):
        out=Path(os.environ['CALIBRATION_PROOF_OUT']);out.mkdir(parents=True,exist_ok=True)
        (out/(version+'.json')).write_text(json.dumps({'version':version,'synthetic':True,
            'cards':fingerprint(actual),'diagnostics':diag},sort_keys=True,indent=2)+'\n')

@pytest.mark.parametrize('version',VERSIONS)
def test_unknown_roster_coverage_rejects_in_both_actual_arms(captured,version):
    from dataclasses import replace
    captured.roster_context.teams={uid:replace(team,availability_known=False)
                                   for uid,team in captured.roster_context.teams.items()}
    cards,diag=captured.run_arm(version)
    assert diag['native_count']>0 and diag['roster_count']==0 and cards==[]

def test_repeated_arm_order_preserves_full_proofs(captured):
    first={v:fingerprint(captured.run_arm(v)[0]) for v in VERSIONS}
    second={v:fingerprint(captured.run_arm(v)[0]) for v in reversed(VERSIONS)}
    assert first==second

@pytest.mark.parametrize('version',VERSIONS)
def test_captured_fatigue_and_pass_filters_do_not_read_or_consume_live_grants(captured,version,monkeypatch):
    from datetime import datetime, timezone
    cards,_=captured.run_arm(version)
    assert cards
    first=cards[0]
    captured.source.update(account_user_id=ME,league_id=captured.owner_context['league'].league_id,
        suppression={'rows':[{'id':7,'centerpiece_id':server._fatigue_centerpiece(
            first.give_player_ids,first.receive_player_ids,captured.owner_context['seed_elo']),
            'shape_bucket':server._card_shape(first),'package_value':None,
            'declined_at':'2026-01-01T00:00:00+00:00','expires_at':'2026-01-02T00:00:00+00:00',
            'retested_at':None,'retest_trade_hash':None}],
            'passed_at':{},'band':.1,'window_days':30,'now':datetime.now(timezone.utc).isoformat()},
        pass_keys=[(list(first.give_player_ids),list(first.receive_player_ids))])
    before=copy.deepcopy(captured.source)
    for name in ('load_deck_suppressions','load_deck_pass_after','mark_deck_suppression_retested',
                 'resuppress_deck_suppression'):
        monkeypatch.setattr(server,name,lambda *a,**k:pytest.fail('live suppression read/write'))
    filtered,diag=captured.run_arm(version)
    assert all((set(c.give_player_ids),set(c.receive_player_ids)) !=
               (set(first.give_player_ids),set(first.receive_player_ids)) for c in filtered)
    assert captured.source==before

@pytest.mark.parametrize('version',VERSIONS)
def test_actual_budget_exhaustion_remains_explicit_in_diagnostics(captured,version):
    captured.owner_context['config']['owner_total_budget']=1.
    cards,diag=captured.run_arm(version)
    assert diag['generator']['budget_exhausted'] is True
    assert diag['generator']['evaluated']==1
    assert diag['final_count']==len(cards)
    assert diag['native_count']<=1
