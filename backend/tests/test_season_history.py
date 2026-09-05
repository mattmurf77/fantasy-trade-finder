"""Win Now historical scope: outcome integrity, privacy, bounded chains and failure closure."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from backend.season_history import collect_history, derive_outcomes, model_support


def record():
    return {'status': 'complete', 'settings': {'num_teams': 4, 'playoff_week_start': 3, 'playoff_teams': 2},
            'scoring_settings': {'rec': 1}, 'roster_positions': ['QB', 'WR', 'BN'],
            'matchups': {str(w): [dict(roster_id=i, matchup_id=(i + 1) // 2, points=p,
                                      custom_points=None, players=['1'], starters=['1'])
                                 for i, p in enumerate([10, 10, 20, 0], 1)] for w in (1, 2)},
            'winners_bracket': [dict(m=1, r=1, p=1, t1=1, t2=3, w=3, l=1)]}


def test_ties_custom_zero_and_median():
    data = record()
    data['settings']['league_average_match'] = 1
    data['matchups']['1'][0]['custom_points'] = 0
    out = derive_outcomes(data)
    assert out['status'] == 'valid'
    assert [(r['wins'], r['losses'], r['ties'], r['points_for']) for r in out['teams']] == [
        (0, 2, 2, 10), (2, 0, 2, 20), (4, 0, 0, 40), (0, 4, 0, 0)]
    assert [r['roster_id'] for r in out['teams'] if r['champion']] == [3]


@pytest.mark.parametrize('mutation', [
    lambda d: d.update(status='in_season'),
    lambda d: d['matchups'].pop('2'),
    lambda d: d['matchups']['1'][0].update(points=None),
    lambda d: d['matchups']['1'][0].update(points=float('nan')),
    lambda d: d['matchups']['1'][0].update(roster_id=2),
    lambda d: d['matchups']['1'][0].update(matchup_id=None),
    lambda d: d['winners_bracket'][0].update(w=2),
    lambda d: d['winners_bracket'][0].pop('p'),
    lambda d: d['winners_bracket'].append(deepcopy(d['winners_bracket'][0])),
    lambda d: d['settings'].update(playoff_teams=4),
])
def test_malformed_inputs_fail_closed(mutation):
    data = record()
    mutation(data)
    out = derive_outcomes(data)
    assert out['status'] == 'excluded' and out['reasons'] and not out['teams']


def test_champion_comes_from_p1_not_last_round_row():
    data = record()
    data['settings']['playoff_teams'] = 4
    data['winners_bracket'].append(dict(m=2, r=1, p=3, t1=2, t2=4, w=2, l=4))
    teams = derive_outcomes(data)['teams']
    assert [r['roster_id'] for r in teams if r['champion']] == [3]


def fixture_fetch():
    data = record()
    metadata = dict(sport='nfl', season_type='regular', league_id='20', season='2025', previous_league_id='10', name='PRIVATE',
                    owner_id='PRIVATE', **{k: data[k] for k in ('status', 'settings', 'scoring_settings', 'roster_positions')})
    responses = {'league/20': metadata, 'league/10': dict(metadata, league_id='10', season='2024', previous_league_id=None)}
    for lid in ('20', '10'):
        for w in range(1, 19):
            responses[f'league/{lid}/matchups/{w}'] = data['matchups'].get(str(w), [])
        responses[f'league/{lid}/winners_bracket'] = data['winners_bracket']
    return responses


def test_capture_dedup_privacy_and_bounds():
    responses, calls = fixture_fetch(), []
    def fetch(path):
        calls.append(path)
        return responses[path]
    result = collect_history(['20', '10', '20'], [2024, 2025], fetch, captured_at='2026-09-04T00:00:00Z')
    assert len(result['seasons']) == 2
    assert len({r['lineage_id'] for r in result['seasons']}) == 1
    assert len(calls) == len(set(calls)) == 40
    assert 'PRIVATE' not in json.dumps(result)
    assert all(s['roster_evidence'] == 'end_of_week_not_kickoff' for s in result['seasons'])
    limited = collect_history(['20'], [2024, 2025], fetch, max_chain=1)
    assert limited['exclusions'][0]['reason'] == 'chain_limit'
    limited = collect_history(['20'], [2024, 2025], fetch, max_seasons=1)
    assert limited['exclusions'][0]['reason'] == 'season_limit'


def test_cycle_and_failed_fetch_are_visible():
    responses = fixture_fetch()
    responses['league/10']['previous_league_id'] = '20'
    result = collect_history(['20'], [2024, 2025], responses.__getitem__)
    assert result['exclusions'][0]['reason'] == 'chain_cycle'
    responses.pop('league/20/matchups/2')
    result = collect_history(['20'], [2025], responses.__getitem__)
    assert result['seasons'][0]['outcomes']['status'] == 'excluded'


def test_unsupported_scoring_and_slots_preserve_outcomes():
    data = record()
    data['scoring_settings']['fgm'] = 3
    assert not model_support(data)['supported']
    assert derive_outcomes(data)['status'] == 'valid'
    data['roster_positions'].append('LB')
    assert 'unsupported_roster_slots' in model_support(data)['reasons']


def test_existing_real_seasons_outcomes():
    fixtures = Path(__file__).parent / 'fixtures/outlook-calibration'
    checked = 0
    for path in fixtures.glob('*.json'):
        raw = json.loads(path.read_text())
        if 'winners_bracket' not in raw or int(raw['season']) == 2026:
            continue
        data = {**raw['league'], 'matchups': raw['matchups'], 'winners_bracket': raw['winners_bracket']}
        out = derive_outcomes(data)
        assert out['status'] == 'valid', (path.name, out)
        assert sum(t['champion'] for t in out['teams']) == 1
        assert sum(t['playoff'] for t in out['teams']) == data['settings']['playoff_teams']
        checked += 1
    assert checked == 6


def test_missing_requested_seasons_and_non_nfl_are_excluded():
    responses = fixture_fetch()
    result = collect_history(['20'], [2023, 2025], responses.__getitem__)
    assert any(e.get('season') == 2023 and e['reason'] == 'requested_season_not_found' for e in result['exclusions'])
    responses['league/20']['sport'] = 'nba'
    result = collect_history(['20'], [2025], responses.__getitem__)
    assert not result['seasons'] and result['exclusions'][0]['reason'] == 'invalid_league_metadata'


@pytest.mark.parametrize('settings, reason', [({'divisions': 2}, 'unsupported_division_seeding'),
    ({'best_ball': 1}, 'best_ball_unsupported'), ({'playoff_round_type': 1}, 'unsupported_playoff_rounds')])
def test_model_format_support(settings, reason):
    data = record()
    data['settings'].update(settings)
    assert reason in model_support(data)['reasons']
    assert derive_outcomes(data)['status'] == 'valid'


def test_bad_settings_metadata_and_excess_playoff_horizon():
    responses = fixture_fetch()
    responses['league/20']['settings'] = ['invalid']
    result = collect_history(['20'], [2025], responses.__getitem__)
    assert not result['seasons']
    assert result['exclusions'][0]['reason'] == 'invalid_settings'
    data = record()
    data['settings'].update(playoff_week_start=17, playoff_teams=6)
    assert 'playoffs_exceed_nfl_horizon' in model_support(data)['reasons']
