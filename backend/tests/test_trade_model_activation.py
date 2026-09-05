"""Final package integration for outlook utility and mutual-benefit rollout."""
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch
import json

import backend.server as server
from backend.trade_roster import Asset, Context, Rules, Team
from backend.tests.test_trade_policy_wiring import run_job


def context():
    specs = {'ar0': ('RB', 30), 'ar1': ('RB', 20), 'ar2': ('RB', 15),
             'aw0': ('WR', 10), 'aw1': ('WR', 5),
             'bw0': ('WR', 30), 'bw1': ('WR', 25), 'bw2': ('WR', 15),
             'br0': ('RB', 10), 'br1': ('RB', 5)}
    assets = {pid: Asset(pid, frozenset([pos]), 100) for pid, (pos, _) in specs.items()}
    ctx = Context('a', {'a': Team('a', tuple(p for p in specs if p.startswith('a'))),
                        'b': Team('b', tuple(p for p in specs if p.startswith('b')))},
                  assets, Rules(('RB', 'WR'), 'observed', 8))
    for uid in ctx.teams:
        ctx.utility_inputs[uid] = {'explicit_outlook': 'contender',
            'projections': {p: score for p, (_, score) in specs.items()},
            'projection_basis': 'synthetic_fixture', 'projection_unit': 'fantasy_points_per_game',
            'projections_fresh': True}
    return ctx


def card():
    return SimpleNamespace(target_user_id='b', give_player_ids=['ar1'], receive_player_ids=['bw1'])


def test_final_context_measures_both_complete_teams_and_rechecks_mutations():
    ctx, c = context(), card()
    result = ctx.card(c)
    assert result['eligible'] and result['mutual_benefit']['eligible']
    assert result['teams']['a']['outlook_utility']['components']['current_production']['delta'] == 15
    assert result['teams']['b']['outlook_utility']['components']['current_production']['delta'] == 10
    # A sweetener that consumes all remaining RB depth cannot be rescued by fit.
    c.give_player_ids += ['ar2']
    result = ctx.card(c)
    assert not result['eligible']
    assert 'backup_depth:RB' in result['teams']['a']['blockers']
    kept, _, _ = server._evaluate_deck_rosters([c], ctx, enforce=True, require_mutual=True)
    assert kept == []


def test_missing_point_data_stays_unknown_and_shadow_preserves_serving():
    ctx, c = context(), card()
    ctx.utility_inputs = {uid: {'explicit_outlook': 'contender'} for uid in ctx.teams}
    kept, results, diagnostics = server._evaluate_deck_rosters([c], ctx, enforce=False)
    assert kept == [c] and not hasattr(c, 'roster_evaluation')
    assert results[id(c)]['mutual_benefit']['status'] == 'unknown'
    assert diagnostics['mutual_benefit']['unknown'] == 1
    assert results[id(c)]['teams']['a']['outlook_utility']['basis'] == 'dynasty_only'
    assert json.loads(json.dumps(results[id(c)], allow_nan=False)) == results[id(c)]
    kept, _, _ = server._evaluate_deck_rosters([c], ctx, enforce=True, require_mutual=True)
    assert kept == []


def test_whole_team_benefit_precedes_personal_surplus_within_market_lane(monkeypatch):
    from backend.tests.test_trade_policy import _entry
    from backend.trade_mutual_benefit import evaluate_mutual_benefit
    import backend.trade_policy as tp
    better, a = _entry('better', tp.LANE_CORE, opportunity=.01)
    worse, b = _entry('worse', tp.LANE_CORE, opportunity=.5)
    for c, gains in ((better, (.04, .05)), (worse, (.01, .9))):
        c.give_player_ids, c.receive_player_ids = ['g'], ['r']
        benefits = [{'normalized_gain': n, 'confidence': .9, 'basis': 'projected_production_and_dynasty',
                     'ready_for_enforcement': True} for n in gains]
        c.roster_evaluation = {'mutual_benefit': evaluate_mutual_benefit(*benefits,
            viewer_preference_source='observed', partner_preference_source='observed')}
    monkeypatch.setattr(server, '_evaluate_card_policy', lambda c, *args, **kw: a if c is better else b)
    kwargs = dict(job_id='j', user_id='a', league_id='L', enforce=True, mutual_order=True)
    kept, _, _ = server._evaluate_deck_policy([worse, better], {}, **kwargs)
    assert kept == [better, worse]
    # Even the best whole-team fit cannot bypass a failed market check.
    a = replace(a, eligible=False)
    kept, _, _ = server._evaluate_deck_policy([worse, better], {}, **kwargs)
    assert kept == [worse]


def test_mutual_flag_alone_runs_final_checks_and_never_publishes_unknown_cards():
    original = server.FLAGS
    class Flags:
        def __getattr__(self, key):
            if key == 'trade_mutual_benefit_v1': return True
            return getattr(original, key)
    class Unknown:
        def card(self, c):
            return {'schema_version': 1, 'status': 'safe', 'eligible': True, 'teams': {},
                    'unknowns': [], 'mutual_benefit': {'status': 'unknown', 'eligible': False}}
    job, _, rows, _ = run_job(extra_patches=[patch.object(server, 'FLAGS', Flags()),
        patch.object(server, '_build_trade_roster_context', return_value=Unknown())])
    assert job['status'] == 'complete' and job['cards'] == [] and rows == []
    assert not job['final_checks_pending']
    assert job['roster_evaluation']['mutual_benefit']['unknown'] > 0
    assert 'mutual_benefit' in job['safety_policy']
