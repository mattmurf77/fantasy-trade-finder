"""Final worker publication and telemetry, using the real generator harness."""
import inspect
import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import backend.server as server
from backend.trade_roster import Asset, Context, Rules, Team
from backend.tests.test_trade_policy_wiring import run_job, JOB_ID


def test_progress_updates_counts_without_publishing_unchecked_cards(monkeypatch):
    job = {'status': 'running', 'cards': [], 'final_checks_pending': True}
    monkeypatch.setitem(server._trade_jobs, 'checked-job', job)
    monkeypatch.setattr(server, 'trade_card_to_dict', lambda c, p: {'trade_id': 'unsafe'})
    card = SimpleNamespace(target_user_id='them')
    callback = server._make_progress_cb('checked-job', {}, set(), None)
    callback(1, 2, [card])
    assert job['cards'] == []
    assert job['opponents_done'] == 1
    job['final_checks_pending'] = False
    callback(2, 2, [card])
    assert job['cards'][0]['trade_id'] == 'unsafe'


@pytest.mark.parametrize('failure', [None, RuntimeError('missing context')])
def test_enforced_market_failure_publishes_no_cards(failure):
    kwargs = {'side_effect': failure} if failure else {'return_value': None}
    job, _, rows, _ = run_job(policy=True, telemetry=True, extra_patches=[
        patch.object(server, '_policy_context', **kwargs)])
    assert job['status'] == 'complete'
    assert job['cards'] == []
    assert rows == []
    assert job['policy_error'] == 'evaluation_unavailable'
    assert not job['final_checks_pending']


def test_shadow_context_failure_preserves_deck():
    job, _, rows, _ = run_job(policy=False, telemetry=True, extra_patches=[
        patch.object(server, '_policy_context', side_effect=RuntimeError('offline'))])
    assert job['status'] == 'complete'
    assert job['cards'] and rows


class UnknownContext:
    def card(self, card):
        return {'schema_version': 1, 'status': 'unknown', 'eligible': False,
                'unknowns': ['lineup_settings_estimated'], 'teams': {}}


@pytest.mark.parametrize('enforce', [False, True])
def test_roster_gate_runs_on_worker_and_stamps_frozen_shadow(enforce):
    # Delegate all unrelated attributes, preserving the harness flag setup.
    class FlagProxy:
        def __getattr__(self, key):
            if key == 'trade_roster_protection': return enforce
            if key == 'trade_roster_evaluation': return True
            return getattr(original, key)
    original = server.FLAGS
    job, _, rows, _ = run_job(extra_patches=[
        patch.object(server, 'FLAGS', FlagProxy()),
        patch.object(server, '_build_trade_roster_context', return_value=UnknownContext())])
    assert job['status'] == 'complete'
    assert job['roster_evaluation']['unknown'] > 0
    if enforce:
        assert job['cards'] == [] and rows == []
        assert not job['final_checks_pending']
    else:
        assert job['cards'] and rows
        assert all(json.loads(r['features_json'])['roster_evaluation']['status'] == 'unknown' for r in rows)


def test_final_roster_gate_rechecks_the_mutated_package_and_keeps_shadow_order():
    ctx = Context('me', {'me': Team('me', ('r', 'r2')), 'them': Team('them', ('w',))},
        {'r': Asset('r', frozenset(('RB',)), 100),
         'r2': Asset('r2', frozenset(('RB',)), 80),
         'w': Asset('w', frozenset(('WR',)), 100)}, Rules(('RB',), 'observed', 5))
    card = SimpleNamespace(target_user_id='them', give_player_ids=['r2'], receive_player_ids=['w'])
    retained, results, diag = server._evaluate_deck_rosters([card], ctx, enforce=False)
    assert retained == [card] and diag['blocked'] == 1
    card.give_player_ids = ['r', 'r2']  # e.g. sweetener appended after generation
    retained, results, diag = server._evaluate_deck_rosters([card], ctx, enforce=True)
    assert retained == []
    assert results[id(card)]['teams']['me']['after']['filled_slots'] == 0


def test_all_pre_gate_worker_card_publications_are_suppressed():
    # Dynamic callback coverage above + guard every other mutation snapshot
    # in this unusually large worker. A new publication seam must opt in.
    import ast
    source = inspect.getsource(server._run_trade_job)
    tree = ast.parse(source)
    gate_line = next(n.lineno for n in ast.walk(tree) if isinstance(n, ast.Call)
                     and isinstance(n.func, ast.Name) and n.func.id == '_evaluate_deck_rosters')
    parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
    count = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or node.lineno >= gate_line:
            continue
        if not any(isinstance(t, ast.Subscript) and isinstance(t.slice, ast.Constant)
                   and t.slice.value == 'cards' for t in node.targets):
            continue
        ancestor = parents.get(node)
        while ancestor is not None:
            if isinstance(ancestor, ast.If) and 'final_checks_pending' in ast.unparse(ancestor.test):
                break
            ancestor = parents.get(ancestor)
        assert ancestor is not None, f'Unchecked publication at worker line {node.lineno}'
        count += 1
    assert count >= 5


def test_changing_safety_flags_invalidates_completed_cached_deck(monkeypatch):
    import time
    job = {'status': 'complete', 'finished_at': time.monotonic(),
           'fairness_threshold': .75, 'safety_policy': []}
    monkeypatch.setattr(server, '_trade_safety_signature', lambda: [])
    assert server._trade_job_is_fresh(job, .75, None)
    monkeypatch.setattr(server, '_trade_safety_signature', lambda: ['roster'])
    assert not server._trade_job_is_fresh(job, .75, None)


def test_impression_attribution_requires_same_league_and_same_swiped_package(monkeypatch):
    from datetime import datetime, timezone
    monkeypatch.setattr(server._trade_policy, 'telemetry_enabled', lambda: True)
    monkeypatch.setattr(server, 'load_deck_impression', lambda _: {
        'user_id': 'me', 'league_id': 'L', 'trade_hash': 'package-a',
        'served_at': datetime.now(timezone.utc).isoformat()})
    assert server._owned_impression_id('imp', 'me', league_id='other') is None
    assert server._owned_impression_id('imp', 'me', league_id='L', expected_trade_hash='package-b') is None
    assert server._owned_impression_id('imp', 'me', league_id='L', expected_trade_hash='package-a') == 'imp'


def test_legacy_prefilter_does_not_veto_existing_weakness_when_full_gate_enforces(monkeypatch):
    import backend.feature_flags as ff
    from backend.trade_optimizer import _feasible_after
    original = ff.is_enabled
    monkeypatch.setattr(ff, 'is_enabled', lambda k: k == 'trade.roster_protection' or original(k))
    assert _feasible_after({'QB': 0, 'RB': 2, 'WR': 2, 'TE': 1}, {'WR': 1}, {'WR': 1}, '1qb_ppr')
    assert not _feasible_after({'QB': 1, 'RB': 2, 'WR': 2, 'TE': 1}, {'RB': 1}, {}, '1qb_ppr')


def test_roster_utility_orders_equal_personal_opportunities_before_market_distance(monkeypatch):
    from dataclasses import replace
    from backend.tests.test_trade_policy import _entry
    import backend.trade_policy as tp
    better_fit, r1 = _entry('better-fit', tp.LANE_FALLBACK, opportunity=None)
    market_closer, r2 = _entry('closer-market', tp.LANE_FALLBACK, opportunity=None)
    better_fit.roster_evaluation = {'mutual_utility': .1}
    market_closer.roster_evaluation = {'mutual_utility': -.1}
    r1, r2 = replace(r1, market_ratio=.85), replace(r2, market_ratio=.99)
    monkeypatch.setattr(server, '_evaluate_card_policy', lambda c, ctx, **kw: r1 if c is better_fit else r2)
    cards, _, _ = server._evaluate_deck_policy([market_closer, better_fit], {}, job_id='j',
                                               user_id='u', league_id='L', enforce=True)
    assert cards == [better_fit, market_closer]


def test_provider_snapshot_includes_coowner_viewer_absent_from_members_and_prices_all_picks(monkeypatch):
    import backend.trade_service as ts
    from unittest.mock import Mock
    league = SimpleNamespace(league_id='123', platform='sleeper',
        members=[SimpleNamespace(user_id='them', roster=['b'])])
    players = {p: SimpleNamespace(position='RB', injury_status=None) for p in ('a', 'b')}
    monkeypatch.setattr(server, '_league_lineup_slots', lambda lid: ['RB'])
    monkeypatch.setitem(server._FA_LEAGUE_META_CACHE, '123', (0, {'roster_positions': ['RB', 'BN']}))
    fetch = Mock(return_value=[{'owner_id':'owner', 'players':['a', None], 'co_owners':['account']},
                               {'owner_id':'them', 'players':['b']}])
    monkeypatch.setattr(server, '_sleeper_get', fetch)
    monkeypatch.setattr(server, '_load_sleeper_cache', lambda: {})
    monkeypatch.setattr(server, '_players_cache_age_seconds', lambda: 1)
    monkeypatch.setattr(server, '_league_slot_order', lambda lid: {})
    monkeypatch.setattr(server, '_priced_pick_value', lambda *a: 375)
    monkeypatch.setattr(ts, 'make_consensus_value_fn', lambda *a: lambda pid: 100)
    monkeypatch.setattr(ts, '_startable_ok_fn', lambda *a: lambda *b: True)
    ctx = server._build_trade_roster_context(
        sess={'user_id':'account', 'league_user_id':'owner', 'user_roster':['stale']},
        league=league, players=players, seed_map={}, scoring_format='1qb_ppr',
        outlook='championship', opponent_outlooks={},
        picks=[{'pick_id':'owned-pick', 'owner_user_id':'owner'}])
    assert ctx.viewer_id == 'owner'
    assert ctx.teams['owner'].roster == ('a', 'owned-pick')
    assert ctx.assets['owned-pick'].value == 375
    result = ctx.card(SimpleNamespace(target_user_id='them', give_player_ids=['a'], receive_player_ids=['b']))
    assert result['eligible']
    assert result['teams']['owner']['outlook'] == 'contender'
    fetch.assert_called_once_with('https://api.sleeper.app/v1/league/123/rosters')
