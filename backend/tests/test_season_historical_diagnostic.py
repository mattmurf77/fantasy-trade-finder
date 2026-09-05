"""Revised-input diagnostic: completed-prefix standings, roster timing, metadata isolation."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from scripts.run_season_historical_diagnostic import build_league, diagnostic_feed


def fixture():
    return {'league_id': '123', 'season': 2025,
        'settings': {'playoff_week_start': 3, 'playoff_teams': 4, 'league_average_match': 1},
        'roster_positions': ['QB', 'BN'], 'scoring_settings': {'pass_td': 4},
        'matchups': {str(w): [{'roster_id': i, 'matchup_id': (i + 1) // 2,
            'points': points, 'custom_points': None, 'players': [f'{w}-{i}'], 'starters': [f'{w}-{i}']}
            for i, points in enumerate([10, 10, 20, 0], 1)] for w in (1, 2)}}


def test_replay_uses_completed_roster_and_excludes_all_future_scores():
    season = fixture()
    baseline = build_league(season, 1)
    for row in season['matchups']['2']:
        row.update(points=99999, custom_points=77777, players=['future'], starters=['future'])
    season['outcomes'] = {'teams': [{'wins': 9999, 'champion': True}]}
    assert build_league(season, 1) == baseline
    assert [t['player_ids'] for t in baseline['teams']] == [['1-1'], ['1-2'], ['1-3'], ['1-4']]


def test_custom_zero_and_median_are_reconstructed_in_matching_units():
    season = fixture()
    season['matchups']['1'][0]['custom_points'] = 0
    teams = build_league(season, 1)['teams']
    assert [(t['wins'], t['losses'], t['ties'], t['points_for']) for t in teams] == [
        (0, 2, 0, 0), (2, 0, 0, 10), (2, 0, 0, 20), (0, 2, 0, 0)]


@pytest.mark.parametrize('name', ['lakeview-2024', 'lakeview-2025'])
def test_full_reconstruction_agrees_with_independent_outcome_collector(name):
    from backend.season_history import derive_outcomes
    raw = json.loads((Path(__file__).parent / 'fixtures/outlook-calibration' / (name + '.json')).read_text())
    season = {**raw['league'], 'matchups': raw['matchups'], 'winners_bracket': raw['winners_bracket']}
    actual = {t['roster_id']: t for t in derive_outcomes(season)['teams']}
    for team in build_league(season, 14)['teams']:
        for field in ('wins', 'losses', 'ties', 'points_for'):
            assert team[field] == pytest.approx(actual[team['roster_id']][field])


def test_current_metadata_removed_without_inventing_historical_teams_or_mutating_source():
    rows = [{'team': None, 'player': {'team': 'BUF', 'injury_status': 'Out', 'position': 'QB'}},
            {'team': 'LAR', 'player': {'team': 'BUF', 'injury_status': 'Out', 'position': 'WR'}}]
    before = deepcopy(rows)
    cleaned = diagnostic_feed(rows)
    assert rows == before
    assert cleaned[0]['team'] is None and 'team' not in cleaned[0]['player']
    assert cleaned[1]['team'] == 'LAR'
    assert all('injury_status' not in r['player'] for r in cleaned)
