"""Unranked occupancy must never become candidate value or usable depth."""
import copy
from types import SimpleNamespace

import pytest

from backend.calibration_roster_coverage import add_unranked_occupancy, annotate_coverage
from backend.trade_roster import Asset, Context, Rules, Team, evaluate


def world(inactive=()):
    return Context('me', {
        'me': Team('me', ('sell', 'held'), frozenset(inactive)),
        'them': Team('them', ('buy', 'backup'))}, {
        'sell': Asset('sell', frozenset({'RB'}), 100),
        'buy': Asset('buy', frozenset({'RB'}), 100),
        'backup': Asset('backup', frozenset({'RB'}), 50)}, Rules(('RB',), 'observed', 2))


def meta(**changes):
    return {'held': {'player_id': 'held', 'fantasy_positions': ['RB'],
                     'active': True, **changes}}


def test_held_only_and_unknown_price_are_explicit():
    ctx = world()
    facts = add_unranked_occupancy(ctx, {**meta(), 'not-held': meta()['held']})
    assert set(facts) == {'held'}
    assert facts['held']['market_value'] is None
    assert not facts['held']['generator_candidate']
    assert ctx.assets['held'].value == 0 and not ctx.assets['held'].startable
    assert ctx.assets['held'].available
    card = SimpleNamespace(target_user_id='them', roster_evaluation={})
    annotate_coverage([card], facts, ctx)
    assert card.roster_evaluation['unpriced_occupancy_ids'] == ['held']
    assert card.roster_evaluation['value_basis'] == 'priced_assets_only_with_unpriced_occupancy'


@pytest.mark.parametrize('row', [{}, {'fantasy_positions': ['K']},
    {'fantasy_positions': ['DL']}, {'fantasy_positions': ['RB'], 'player_id': 'other'}])
def test_unknown_or_unsupported_metadata_remains_unresolved(row):
    ctx = world()
    assert not add_unranked_occupancy(ctx, {'held': row})
    assert 'held' not in ctx.assets
    result = evaluate(viewer=ctx.teams['me'], partner=ctx.teams['them'],
                      give=['sell'], receive=['buy'], assets=ctx.assets, rules=ctx.rules)
    assert not result['eligible']
    assert 'unresolved_roster_asset' in result['teams']['me']['unknowns']


@pytest.mark.parametrize('changes', [{'active': False}, {'active': None}, {'injury_status': 'IR'}])
def test_missing_active_or_injured_is_conservatively_unavailable(changes):
    ctx = world()
    add_unranked_occupancy(ctx, meta(**changes))
    assert not ctx.assets['held'].available


def test_active_occupancy_preserves_capacity_and_never_fills_usable_depth():
    ctx = world()
    add_unranked_occupancy(ctx, meta())
    ctx.assets['wr'] = Asset('wr', frozenset({'WR'}), 100)
    ctx.teams['them'] = Team('them', ('buy', 'backup', 'wr'))
    result = evaluate(viewer=ctx.teams['me'], partner=ctx.teams['them'],
        give=['sell'], receive=['wr'], assets=ctx.assets, rules=ctx.rules)
    assert 'deficits:RB' in result['teams']['me']['blockers']
    result = evaluate(viewer=ctx.teams['me'], partner=ctx.teams['them'],
        give=['sell'], receive=['buy', 'wr'], assets=ctx.assets, rules=ctx.rules)
    assert 'cuts_required' in result['teams']['me']['blockers']
    ctx.teams['me'] = Team('me', ('sell', 'held'), frozenset({'held'}))
    result = evaluate(viewer=ctx.teams['me'], partner=ctx.teams['them'],
        give=['sell'], receive=['buy', 'wr'], assets=ctx.assets, rules=ctx.rules)
    assert 'cuts_required' not in result['teams']['me']['blockers']


# Real generation, isolated provider capture: the extra holding never enters
# model inputs, but both complete engines now get a resolvable safety roster.
from backend.tests.test_outlook_calibration_adapter import captured
from backend.tests.test_owner_generator_routes import harness, owner_harness, ME, LEAGUE


def test_full_pair_metadata_occupancy_never_changes_generator_pool(captured, monkeypatch):
    from backend import outlook_calibration_adapter as adapter, session_input, server
    old_resolve = session_input.resolve_session_input
    metadata = copy.deepcopy(server._load_sleeper_cache())
    metadata.update(meta())
    def resolve(*args, **kwargs):
        result = old_resolve(*args, **kwargs)
        for row in kwargs['raw']['rosters']:
            if row['owner_id'] == ME:
                row['players'].append('held')
        result['user_player_ids'].append('held')
        return result
    monkeypatch.setattr(session_input, 'resolve_session_input', resolve)
    monkeypatch.setattr(server, '_load_sleeper_cache', lambda: metadata)
    result = adapter.capture(user_id=ME, league_user_id=ME, league_id=LEAGUE)
    assert 'held' not in result.owner_context['players']
    assert result.source['unpriced_occupancy']['held']['market_value'] is None
    assert result.catalog.assets['held']['value'] is None
    for version in adapter.VERSIONS:
        cards, _ = result.run_arm(version)
        assert cards
        for card in cards:
            assert 'held' not in card.give_player_ids + card.receive_player_ids
            assert card.roster_evaluation['eligible']
            assert 'held' in card.roster_evaluation['unpriced_occupancy_ids']
