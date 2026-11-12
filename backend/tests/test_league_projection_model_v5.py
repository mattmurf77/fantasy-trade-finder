"""Model v5/v6 acceptance: projected lineup totals only, one app-wide score SD.

Future means come from the projected lineup and nothing else; completed
results stay facts; a missing projection is reported, never replaced by what a
team has scored so far.

Model v6 (operator rule 2026-11-11): an open starting slot takes the best
projected free agent for it, else scores 0, and is no longer unknown:
- test_only_a_week_with_no_projection_anywhere_stops_the_run: an empty feed
  still stops (`missing_weekly_projections`); a populated feed fills an
  entirely unprojected roster instead.
- test_an_empty_slot_an_unprojected_player_could_fill_takes_the_best_free_agent:
  complete, and the outlook suggestion is no longer withheld.
- test_capture_never_uses_a_rostered_player_as_a_free_agent (any team, taxi,
  reserve), even if a feed offers one.
- IDP: test_idp_slot_takes_a_projected_free_agent_first,
  test_idp_slot_without_a_free_agent_takes_the_replacement_mean,
  test_an_empty_idp_slot_with_no_free_agent_or_replacement_mean_scores_zero.
- free_agent_fill unit: ties break by player id; skipped (locked) slots stay
  empty.
"""
from copy import deepcopy
from decimal import Decimal
import json
import math

import pytest

from backend.league_projections import batch
from backend.league_projections.core import Unavailable, VERSION, free_agent_fill, optimize
from backend.league_projections.provider import API, capture
from backend.league_projections.scoring import BEST_AVAILABLE
from backend.league_projections.simulation import config, simulate
from backend.tests.test_league_projection_provider import world

SD = 12.0


def cfg(**extra):
    base = dict(seeding='record_pf_higher_pa_random', draft_tie='random_exact_ties', ir_maxpf='include',
                reserve_activation='exclude_current_reserve', empty_slots='fill_available',
                iterations=4000, seed=730, score_sd=SD, residual_correlation=0)
    base.update(extra)
    return base


def snapshot():
    """Four 1-1 teams, two unplayed weeks; team i projects 4i points, Max PF 6i."""
    return {'playoff_spots': 2, 'playoff_byes': 1, 'completed_weeks': 2, 'source': 'synthetic',
            'captured_at': '2026-11-01T00:00:00+00:00',
            'teams': [{'roster_id': i, 'name': f'Team{i}', 'wins': 1, 'losses': 1, 'ties': 0, 'points_for': '30',
                       'points_against': '30', 'maxpf': '50', 'actual_history': ['10', '20'], 'maxpf_history': []}
                      for i in range(1, 5)],
            'weeks': [{'week': week, 'games': pairs,
                       'teams': {str(i): {'actual': {'points': str(i * 4)}, 'maxpf': {'points': str(i * 6)},
                                          'maxpf_dominates_actual': True} for i in range(1, 5)}}
                      for week, pairs in [(3, [[1, 2], [3, 4]]), (4, [[1, 3], [2, 4]])]],
            'pick_ownership': []}


def weekly(result, *keys):
    return [[tuple(week[k] for k in keys) for week in team['weeks']] for team in result['teams']]


# ── Historical scoring cannot set a future mean ────────────────────────────

def test_changing_historical_points_cannot_move_future_score_means():
    base = snapshot()
    changed = snapshot()
    # Same records and same projections; only what the teams have scored so
    # far differs, by a factor of ten for one team and wildly for another.
    changed['teams'][0].update(points_for='300', maxpf='500', actual_history=['100', '200'])
    changed['teams'][1].update(points_for='30', actual_history=['0', '30'])
    a, b = simulate(base, cfg()), simulate(changed, cfg())
    fields = ('modeled_score_mean', 'modeled_score_sd', 'win_probability', 'tie_probability', 'loss_probability')
    assert weekly(a, *fields) == weekly(b, *fields)
    assert [[w['maxpf_floor']['input_mean'] for w in t['weeks']] for t in a['teams']] == \
           [[w['maxpf_floor']['input_mean'] for w in t['weeks']] for t in b['teams']]
    assert [[w['maxpf_floor']['simulated_actual_mean'] for w in t['weeks']] for t in a['teams']] == \
           [[w['maxpf_floor']['simulated_actual_mean'] for w in t['weeks']] for t in b['teams']]
    for team in a['teams']:
        for week in team['weeks']:
            assert week['modeled_score_mean'] == team['roster_id'] * 4
            assert week['maxpf_floor']['input_mean'] == team['roster_id'] * 6
    # The facts themselves are kept.
    assert b['teams'][0]['current_points_for'] == 300 and b['teams'][0]['current_maxpf'] == 500


def test_result_has_no_history_term():
    result = simulate(snapshot(), cfg())
    assert result['model_version'] == VERSION == 'projected-lineup-universal-sd-v6'
    assert 'historical_weight' not in result['config'] and 'persistent_sd' not in result['config']
    assert result['score_sd'] == SD and result['score_model']['sd_status'] == 'provisional_not_calibrated'
    for team in result['teams']:
        for week in team['weeks']:
            assert 'historical_component' not in week and 'projection_component' not in week


# ── One SD for every team; completed games carry none ──────────────────────

def test_every_team_gets_the_same_sd_and_simulated_averages_converge_to_projections():
    source = snapshot()
    # Histories with very different spread must not give teams different SDs.
    source['teams'][0].update(actual_history=['0', '30'])
    source['teams'][1].update(actual_history=['15', '15'])
    iterations = 20000
    result = simulate(source, cfg(iterations=iterations))
    for team in result['teams']:
        for week in team['weeks']:
            assert week['modeled_score_sd'] == SD
            moments = week['maxpf_floor']
            assert abs(moments['simulated_actual_mean'] - team['roster_id'] * 4) < 5 * SD / math.sqrt(iterations)
            assert abs(math.sqrt(moments['simulated_actual_variance']) - SD) < .35


def test_completed_games_have_no_noise():
    source = snapshot()
    for i, detail in source['weeks'][0]['teams'].items():
        detail.update(actual_score_observed=True, modeled_actual_projection=str(10 + int(i)),
                      modeled_maxpf_projection=str(20 + int(i)))
    result = simulate(source, cfg())
    for team in result['teams']:
        played, upcoming = team['weeks']
        assert played['modeled_score_sd'] == 0 and played['score_distribution'] == 'observed_completed_lineup'
        assert played['modeled_score_mean'] == 10 + team['roster_id']
        assert played['maxpf_floor']['simulated_actual_variance'] == 0
        assert played['maxpf_floor']['simulated_actual_mean'] == 10 + team['roster_id']
        assert played['win_probability'] in (0, 1) and played['tie_probability'] == 0
        assert upcoming['modeled_score_sd'] == SD and 0 < upcoming['win_probability'] < 1


def test_zero_sd_is_deterministic_and_seed_is_fixed():
    result = simulate(snapshot(), cfg(score_sd=0, iterations=200))
    for team in result['teams']:
        assert [w['win_probability'] for w in team['weeks']] in ([0, 0], [0, 1], [1, 0], [1, 1])
    assert simulate(snapshot(), cfg()) == simulate(snapshot(), cfg())
    assert simulate(snapshot(), cfg())['teams'] != simulate(snapshot(), cfg(seed=731))['teams']


# ── Configuration ──────────────────────────────────────────────────────────

@pytest.mark.parametrize('obsolete', ['historical_weight', 'persistent_sd', 'maxpf_variance'])
def test_obsolete_options_are_rejected_not_reinterpreted(obsolete):
    with pytest.raises(ValueError, match='unknown_configuration'):
        config({**cfg(), obsolete: .6})


def test_score_sd_is_required_bounded_and_configured_once():
    missing = cfg()
    del missing['score_sd']
    with pytest.raises(ValueError, match='score_sd_required'):
        config(missing)
    for bad in (-1, 100.5):
        with pytest.raises(ValueError, match='invalid_score_sd'):
            config(cfg(score_sd=bad))
    shipped = json.loads(batch.CONFIG_PATH.read_text())['model']
    assert shipped['score_sd'] == 25.0
    assert not {'historical_weight', 'persistent_sd', 'maxpf_variance'} & set(shipped)
    assert batch.settings()['model']['score_sd'] == 25.0


# ── Completed standings stay facts: tiebreakers ────────────────────────────

def finished(rows):
    teams = [{'roster_id': i, 'name': f'Team{i}', 'wins': w, 'losses': l, 'ties': 0, 'points_for': str(pf),
              'points_against': str(pa), 'maxpf': str(pf + 10), 'actual_history': [str(pf - 20), '20'], 'maxpf_history': []}
             for i, (w, l, pf, pa) in enumerate(rows, 1)]
    return {'playoff_spots': 2, 'playoff_byes': 0, 'completed_weeks': 2, 'source': 'synthetic',
            'captured_at': '2026-11-01T00:00:00+00:00', 'teams': teams, 'weeks': [], 'pick_ownership': []}


def test_points_for_then_points_against_break_record_ties():
    by_pf = simulate(finished([(2, 0, 50, 40), (1, 1, 40, 45), (1, 1, 45, 45), (0, 2, 30, 35)]), cfg(iterations=200))
    assert [t['playoff_probability'] for t in by_pf['teams']] == [1, 0, 1, 0]
    by_pa = simulate(finished([(2, 0, 50, 40), (1, 1, 40, 41), (1, 1, 40, 49), (0, 2, 30, 30)]), cfg(iterations=200))
    assert [t['playoff_probability'] for t in by_pa['teams']] == [1, 0, 1, 0]


# ── Max PF is its own eligible-roster number ───────────────────────────────

def test_maxpf_uses_its_own_projection_and_keeps_an_observed_floor():
    source = snapshot()
    source['weeks'][0]['teams']['1'].update(observed_maxpf_floor='40')
    iterations = 20000
    result = simulate(source, cfg(iterations=iterations))
    for team in result['teams'][1:]:
        expected = 50 + 2 * team['roster_id'] * 6
        assert abs(team['maxpf_mean'] - expected) < 6 * SD / math.sqrt(iterations) * 2
        for week in team['weeks']:
            assert week['maxpf_floor']['target_mean'] == team['roster_id'] * 6 != week['modeled_score_mean']
    floored = result['teams'][0]['weeks'][0]['maxpf_floor']
    assert floored['observed_floor'] == 40 and floored['simulated_mean'] >= 40
    assert result['teams'][0]['maxpf_quantiles']['0.1'] >= 50 + 40 - 6 * SD


# ── Missing projections: reported, never replaced by team history ──────────

def capture_cfg():
    return cfg(scoring_contract=BEST_AVAILABLE, availability_scenario='conditional_provider_forecast')


def run(source, feed):
    return capture('123', 'me', capture_cfg(), lambda url: deepcopy(source[url]), feed=feed,
                   captured_at='2026-11-01T00:00:00+00:00', clock=lambda: '2026-11-01T00:00:01+00:00')


def feed_without(feed, *missing, extra=None):
    class Feed:
        def weeks(self, season, weeks, player_ids):
            result = feed.weeks(season, weeks, player_ids)
            rows = result['weeks']['2']
            for pid in missing:
                rows.pop(pid)
            rows.update(extra or {})
            return result
    return Feed()


def scale_history(source, factor):
    """Every completed score, and the standings built from them, times `factor`."""
    for row in source[f'{API}/league/123/matchups/1']:
        row.update(points=row['points'] * factor, starters_points=[v * factor for v in row['starters_points']])
    for roster in source[f'{API}/league/123/rosters']:
        for key in ('fpts', 'fpts_against', 'ppts'):
            roster['settings'][key] *= factor


def test_capture_projects_the_same_lineups_whatever_teams_scored_before():
    source, feed = world()
    base = run(source, feed)
    scale_history(source, 7)
    changed = run(source, feed)
    assert changed['teams'][0]['points_for'] == '70' != base['teams'][0]['points_for']
    for rid, projected in (('1', 10), ('2', 5)):
        for snap in (base, changed):
            detail = snap['weeks'][0]['teams'][rid]
            assert Decimal(detail['modeled_actual_projection']) == Decimal(detail['modeled_maxpf_projection']) == projected
    assert base['viewer_roster_id'] == 1 and base['coverage']['estimate_status'] == 'complete'
    assert 'history_fallback_team_weeks' not in base['coverage']


def test_only_a_week_with_no_projection_anywhere_stops_the_run():
    source, feed = world()
    # The feed is populated (p1), so team 2's unprojected roster is filled:
    # no free agent here, so a known zero. History is never consulted.
    snap = run(source, feed_without(feed, 'p2'))
    detail = snap['weeks'][0]['teams']['2']
    assert Decimal(detail['modeled_actual_projection']) == 0 and detail['projection_coverage']['zero_filled_slots'] == ['WR']
    assert snap['coverage']['estimate_status'] == 'complete'
    # No usable projection for anyone this week: the run stops as before.
    with pytest.raises(Unavailable) as err:
        run(source, feed_without(feed, 'p1', 'p2'))
    assert err.value.reason == 'missing_weekly_projections' and err.value.state == 'incomplete_projections'
    assert err.value.details == {'week': 2, 'lanes': ['actual', 'maxpf']}
    # Before the first completed week the answer is the same: there never was
    # a history to fall back on, and now none is consulted either way.
    source[f'{API}/state/nfl']['week'] = 1
    source[f'{API}/league/123']['settings']['playoff_week_start'] = 2
    source[f'{API}/league/123/matchups/1'] = [{'roster_id': i, 'matchup_id': 1} for i in (1, 2)]
    for roster in source[f'{API}/league/123/rosters']:
        roster['settings'].update(wins=0, losses=0, fpts=0, fpts_against=0, ppts=0)

    class WeekOne:
        def weeks(self, season, weeks, player_ids):
            rows = feed.weeks(season, weeks, player_ids)['weeks']['2']
            rows.pop('p1'), rows.pop('p2')
            return {'source': 'synthetic', 'captured_at': '2026-11-01T00:00:00+00:00', 'weeks': {'1': rows}}
    with pytest.raises(Unavailable) as early:
        run(source, WeekOne())
    assert early.value.reason == 'missing_weekly_projections'


KICK = '2026-11-08T18:00:00+00:00'


def fa_row(points, key='rec', **extra):
    return {'phase': 'pregame', 'kickoff_at': KICK, 'availability': 1, 'stats': {key: points}, 'supported_keys': [key], **extra}


def with_free_agents(feed, rows):
    """`feed`, plus week-2 free-agent rows as the real adapter would supply."""
    class Feed:
        def weeks(self, season, weeks, player_ids):
            return {**feed.weeks(season, weeks, player_ids), 'free_agents': {'2': deepcopy(rows)}}
    return Feed()


def test_an_empty_slot_an_unprojected_player_could_fill_takes_the_best_free_agent():
    from backend.league_projections.recommendation import build
    source, feed = world()
    source[f'{API}/league/123']['roster_positions'] = ['WR', 'WR']
    source[f'{API}/league/123/rosters'][1]['players'] = ['p2', 'p3']
    source[f'{API}/players/nfl'].update(p3={'fantasy_positions': ['WR']}, f1={'fantasy_positions': ['WR']},
                                        f2={'fantasy_positions': ['WR']})
    snap = run(source, with_free_agents(feed, {'f1': fa_row(3), 'f2': fa_row(4)}))
    mine, theirs = (snap['weeks'][0]['teams'][rid] for rid in ('1', '2'))
    # Team 2's second receiver has no projection; his slot takes the best
    # free agent: known, not unknown, and not their scoring average either.
    assert theirs['projection_coverage']['complete'] is True and theirs['projection_coverage']['missing_actual_slots'] == []
    assert [(f['slot'], f['player_id'], f['points']) for f in theirs['projection_coverage']['free_agent_fills']] == [('WR', 'f2', '4')]
    assert Decimal(theirs['modeled_actual_projection']) == 9
    # Team 1 has one receiver: its second slot takes the same free agent.
    assert Decimal(mine['modeled_actual_projection']) == 14
    assert snap['coverage']['estimate_status'] == 'complete'
    assert snap['coverage']['incomplete_team_weeks'] == 0 and snap['coverage']['missing_lineup_slots'] == 0
    assert snap['coverage']['incomplete_weeks'] == [] and snap['coverage']['fa_filled_slots'] == 2
    result = simulate(snap, capture_cfg())
    assert result['coverage']['estimate_status'] == 'complete'
    assert result['teams'][1]['weeks'][0]['modeled_score_mean'] == 9
    assert build('current', result, None, (.15, .75))['status'] == 'available'


def test_capture_never_uses_a_rostered_player_as_a_free_agent():
    source, feed = world()
    source[f'{API}/league/123']['roster_positions'] = ['WR', 'WR']
    rosters = source[f'{API}/league/123/rosters']
    rosters[0].update(taxi=['tx'], reserve=['rs'])
    rosters[1]['players'] = ['p2', 'b2']
    for pid in ('tx', 'rs', 'b2', 'f1'):
        source[f'{API}/players/nfl'][pid] = {'fantasy_positions': ['WR']}
    # A feed that wrongly offers rostered players: capture still refuses them.
    offered = {'tx': fa_row(50), 'rs': fa_row(60), 'b2': fa_row(70), 'f1': fa_row(1)}
    snap = run(source, with_free_agents(feed_without(feed, extra={'b2': fa_row(0)}), offered))
    for detail in snap['weeks'][0]['teams'].values():
        coverage = detail['projection_coverage']
        assert {f['player_id'] for f in coverage['free_agent_fills'] + coverage['maxpf_free_agent_fills']} <= {'f1'}
    assert [f['player_id'] for f in snap['weeks'][0]['teams']['1']['projection_coverage']['free_agent_fills']] == ['f1']


def test_a_verified_bye_is_a_known_zero_not_missing_data():
    source, feed = world()
    bye = {'p2': {'bye': True, 'bye_evidence': 'schedule', 'availability': 0, 'stats': {}, 'supported_keys': []}}
    snap = run(source, feed_without(feed, 'p2', extra=bye))
    detail = snap['weeks'][0]['teams']['2']
    assert Decimal(detail['modeled_actual_projection']) == 0
    assert detail['projection_coverage']['complete'] is True
    assert {'player_id': 'p2', 'reason': 'bye'} in detail['exclusions']
    assert snap['coverage']['estimate_status'] == 'complete'


# ── Review fixes: unknown slots are never reported as complete ─────────────

def idp_world(dl_history=False):
    source, _ = world()
    source[f'{API}/league/123'].update(roster_positions=['DL', 'WR'], scoring_settings={'rec': 1, 'idp_tkl': 1})
    source[f'{API}/players/nfl'] = {pid: {'fantasy_positions': [pos]} for pid, pos in
                                    (('p1', 'WR'), ('p2', 'WR'), ('d1', 'DL'), ('d2', 'DL'))}
    for roster in source[f'{API}/league/123/rosters']:
        roster['players'] = [f"p{roster['roster_id']}", f"d{roster['roster_id']}"]
    if dl_history:
        # Week 1 starters in both slots: DL starts of 4 and 6, a mean of 5.
        for row in source[f'{API}/league/123/matchups/1']:
            row.update(starters=[f"d{row['roster_id']}", f"p{row['roster_id']}"],
                       starters_points=[4 if row['roster_id'] == 1 else 6, row['points']])
    # Otherwise the one-slot history cannot give a DL replacement mean.

    class Feed:
        def weeks(self, season, weeks, player_ids):
            kick = '2026-11-08T18:00:00+00:00'
            rows = {f'p{i}': {'kickoff_at': kick, 'availability': 1, 'stats': {'rec': 10 if i == 1 else 5}, 'supported_keys': ['rec']} for i in (1, 2)}
            rows['d1'] = {'kickoff_at': kick, 'availability': 1, 'stats': {'idp_tkl': 6}, 'supported_keys': ['idp_tkl']}
            rows['d2'] = {'bye': True, 'bye_evidence': 'schedule', 'availability': 0, 'stats': {}, 'supported_keys': []}
            return {'source': 'synthetic', 'captured_at': '2026-11-01T00:00:00+00:00', 'weeks': {'2': rows}}
    return source, Feed()


def test_an_empty_idp_slot_with_no_free_agent_or_replacement_mean_scores_zero():
    snap = run(*idp_world())
    detail = snap['weeks'][0]['teams']['2']
    coverage = detail['projection_coverage']
    # v5 called this slot unknown; v6 scores it zero and the team-week is known.
    assert coverage['idp_replacement_unavailable'] is True and coverage['actual_lineup_gaps'] == 1
    assert coverage['complete'] is True and coverage['missing_actual_slots'] == [] and coverage['zero_filled_slots'] == ['DL']
    assert Decimal(detail['modeled_actual_projection']) == 5
    assert snap['coverage']['estimate_status'] == 'complete'
    assert snap['weeks'][0]['teams']['1']['projection_coverage']['complete'] is True


def test_idp_slot_without_a_free_agent_takes_the_replacement_mean():
    snap = run(*idp_world(dl_history=True))
    detail = snap['weeks'][0]['teams']['2']
    # The existing rule, unchanged: a DL on bye, no free agent, mean 5.
    assert detail['replacement_means'] == {'DL': '5'}
    dl = detail['actual']['lineup'][0]['player']
    assert dl['hypothetical'] and dl['points'] == '5' and detail['projection_coverage']['free_agent_fills'] == []
    assert Decimal(detail['modeled_actual_projection']) == 10 and detail['projection_coverage']['complete'] is True


def test_idp_slot_takes_a_projected_free_agent_first():
    source, feed = idp_world(dl_history=True)
    source[f'{API}/players/nfl']['fdl'] = {'fantasy_positions': ['DL']}
    snap = run(source, with_free_agents(feed, {'fdl': fa_row(7, key='idp_tkl')}))
    detail = snap['weeks'][0]['teams']['2']
    assert [(f['slot'], f['player_id']) for f in detail['projection_coverage']['free_agent_fills']] == [('DL', 'fdl')]
    assert not any(r['player'].get('hypothetical') for r in detail['actual']['lineup'] if r['player'])
    assert Decimal(detail['modeled_actual_projection']) == 12


# ── free_agent_fill: ties and skipped slots ────────────────────────────────

def test_free_agent_ties_break_by_player_id_and_skipped_slots_stay_empty():
    built = optimize(['WR', 'WR', 'WR'], [], empty_policy='fill_available')
    agents = [{'player_id': pid, 'positions': ['WR'], 'points': '4'} for pid in ('fc', 'fa', 'fb')]
    filled = free_agent_fill(['WR', 'WR', 'WR'], built, agents, empty_policy='fill_available', skip={0: None})
    assert [r['player'] and r['player']['player_id'] for r in filled['lineup']] == [None, 'fa', 'fb']
    assert filled['gaps'] == [0] and filled['points'] == '8'
    # Two slot types: the tied receivers both reach the solver; the lower id wins.
    mixed = optimize(['RB', 'WR'], [], empty_policy='fill_available')
    pool = [{'player_id': 'zr', 'positions': ['RB'], 'points': '5'}] + [
        {'player_id': pid, 'positions': ['WR'], 'points': '4'} for pid in ('wb', 'wa')]
    assert [r['player']['player_id'] for r in free_agent_fill(['RB', 'WR'], mixed, pool, empty_policy='fill_available')['lineup']] == ['zr', 'wa']
    single = optimize(['WR'], [], empty_policy='fill_available')
    assert free_agent_fill(['WR'], single, list(reversed(agents)), empty_policy='fill_available')['lineup'][0]['player']['player_id'] == 'fa'



def test_players_who_can_never_fill_the_slot_do_not_make_it_unknown():
    # No position metadata (an offensive lineman): cannot start anywhere.
    source, feed = world()
    source[f'{API}/league/123']['roster_positions'] = ['WR', 'K']
    source[f'{API}/league/123/rosters'][1]['players'] = ['p2', 'x9']
    source[f'{API}/players/nfl']['x9'] = {'full_name': 'Some Lineman', 'position': 'OT', 'fantasy_positions': None}
    snap = run(source, feed)
    coverage = snap['weeks'][0]['teams']['2']['projection_coverage']
    assert [p['player_id'] for p in coverage['unpriced_players']] == ['x9']
    assert coverage['complete'] is True and coverage['missing_actual_slots'] == []
    assert snap['coverage']['estimate_status'] == 'complete'


def test_a_player_with_no_nfl_team_is_a_known_zero_for_the_slot():
    from backend.tests.test_league_projection_best_available import add_priced_teammate, run as native_run, world as native
    source, native_cfg = native()
    source[f'{API}/players/nfl']['p2']['team'] = None
    add_priced_teammate(source)
    source[f'{API}/league/123']['roster_positions'] = ['WR', 'TE']
    snap = native_run(source, native_cfg)
    detail = snap['weeks'][0]['teams']['2']
    assert detail['projection_coverage']['unpriced_players'][0]['reason'] == 'unknown_nfl_team'
    assert detail['actual']['gaps'] == [1]
    assert detail['projection_coverage']['missing_actual_slots'] == []
    assert snap['coverage']['estimate_status'] == 'complete'


def test_a_played_starter_with_no_recorded_score_leaves_its_slot_unknown():
    from backend.league_projections import provider
    from backend.tests.test_league_projection_best_available import completed_world
    from backend.tests.test_league_projection_native_capture import run as native_run
    source, native_cfg = completed_world()
    source[f'{provider.API}/league/123']['roster_positions'] = ['SUPER_FLEX', 'SUPER_FLEX']
    rows = source[f'{provider.API}/league/123/matchups/3']
    rows[0]['starters'] = ['p1', 'p4']
    rows[1]['starters'] = ['p2', '0']
    rows[0]['players_points'].pop('p1')
    snap = native_run(source, native_cfg)
    detail = snap['weeks'][0]['teams']['1']
    assert detail['actual_score_observed'] is False
    assert detail['projection_coverage']['missing_locked_actuals'][0]['reason'] == 'missing_completed_actual'
    assert detail['projection_coverage']['missing_actual_slots'] == ['SUPER_FLEX']
    assert snap['coverage']['estimate_status'] == 'incomplete'


def test_a_forced_negative_maxpf_fill_is_raised_to_the_lineup_total():
    source, _ = world()
    source[f'{API}/league/123'].update(roster_positions=['WR', 'K'], scoring_settings={'rec': 1, 'fgmiss': -1, 'fgm': 3})
    source[f'{API}/players/nfl'] = {pid: {'fantasy_positions': [pos]} for pid, pos in
                                    (('p1', 'WR'), ('p2', 'WR'), ('k1', 'K'), ('k2', 'K'))}
    for roster in source[f'{API}/league/123/rosters']:
        roster['players'] = [f"p{roster['roster_id']}"] + (['k1'] if roster['roster_id'] == 1 else [])
        if roster['roster_id'] == 2:
            roster['taxi'] = ['k2']

    class Feed:
        def weeks(self, season, weeks, player_ids):
            kick = '2026-11-08T18:00:00+00:00'
            rows = {f'p{i}': {'kickoff_at': kick, 'availability': 1, 'stats': {'rec': 10 if i == 1 else 5}, 'supported_keys': ['rec']} for i in (1, 2)}
            rows['k1'] = {'kickoff_at': kick, 'availability': 1, 'stats': {'fgm': 2, 'fgmiss': .5}, 'supported_keys': ['fgm', 'fgmiss']}
            # The taxi kicker projects only a miss: forcing him into K is negative.
            rows['k2'] = {'kickoff_at': kick, 'availability': 1, 'stats': {'fgmiss': .3}, 'supported_keys': ['fgmiss']}
            return {'source': 'synthetic', 'captured_at': '2026-11-01T00:00:00+00:00', 'weeks': {'2': rows}}
    options = cfg(scoring_contract=BEST_AVAILABLE, availability_scenario='conditional_provider_forecast', ir_maxpf='exclude', iterations=200)
    snap = capture('123', 'me', options, lambda url: deepcopy(source[url]), feed=Feed(),
                   captured_at='2026-11-01T00:00:00+00:00', clock=lambda: '2026-11-01T00:00:01+00:00')
    detail = snap['weeks'][0]['teams']['2']
    assert Decimal(detail['modeled_maxpf_projection']) < Decimal(detail['modeled_actual_projection']) == 5
    result = simulate(snap, options)
    week = result['teams'][1]['weeks'][0]
    assert week['maxpf_floor']['target_mean'] == 5 == week['modeled_score_mean']
    assert week['observed_mean_conditioning']['projection_raised_to_lineup_total'] == pytest.approx(.3)
    assert week['observed_mean_conditioning']['unconditioned_maxpf_mean'] == 5
    # Nothing to raise for the other team: the key reports zero.
    assert result['teams'][0]['weeks'][0]['observed_mean_conditioning']['projection_raised_to_lineup_total'] == 0
