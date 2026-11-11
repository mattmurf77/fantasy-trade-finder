"""Outlook suggestion from the saved projection: bands, availability, precedence.

The suggestion is read from the saved weekly run only. It is made on the
unrounded probability, only for a current, complete, current-model forecast,
and it never writes the saved outlook.
"""
from datetime import datetime, timedelta, timezone
import json
import math

import pytest

from backend import database as db, team_review
from backend.league_projections import api, batch, recommendation, store, service
from backend.league_projections.core import VERSION
from backend.league_projections.recommendation import REBUILDING_MAX, build, classify, thresholds
from backend.tests.test_league_projection_routes import client, engine  # noqa: F401

CUTS = (.15, .75)
ABOVE = lambda value: math.nextafter(value, 1)  # noqa: E731


# ── Bands ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize('probability,outlook', [
    (0, 'jets'), (.15, 'jets'), (ABOVE(.15), 'rebuilder'),
    (.3, 'rebuilder'), (.45, 'rebuilder'), (ABOVE(.45), 'contender'),
    (.6, 'contender'), (.75, 'contender'), (ABOVE(.75), 'championship'), (1, 'championship'),
])
def test_every_band_boundary(probability, outlook):
    assert classify(probability, CUTS) == outlook


@pytest.mark.parametrize('made,outlook', [
    (37500, 'jets'), (37501, 'rebuilder'), (112500, 'rebuilder'), (112501, 'contender'),
    (187500, 'contender'), (187501, 'championship'),
])
def test_boundaries_as_the_simulator_reports_them(made, outlook):
    # The simulator's probability is a count over 250,000 seasons.
    assert classify(made / 250000, CUTS) == outlook


def test_classification_uses_the_unrounded_probability():
    # Both display as "45%"; only one is above the 45% cut.
    assert round(.4549 * 100) == round(.4501 * 100) == 45
    assert classify(.4501, CUTS) == 'contender' and classify(.4499, CUTS) == 'rebuilder'
    assert REBUILDING_MAX == .45


def test_only_the_outer_cuts_are_configuration():
    assert thresholds(batch.settings()) == CUTS
    for bad in ({'tanking_max': .45, 'contender_max': .75}, {'tanking_max': .15, 'contender_max': .45},
                {'tanking_max': .15}, {'tanking_max': .15, 'contender_max': .75, 'rebuilding_max': .5},
                {'tanking_max': True, 'contender_max': .75}):
        with pytest.raises(ValueError):
            thresholds({'outlook_recommendation': bad})
    # However the outer cuts move, exactly 45% is Rebuilding and just above is not.
    for cuts in ((0, .46), (.44, 1), (.2, .6)):
        assert classify(.45, cuts) == 'rebuilder'
        assert classify(ABOVE(.45), cuts) in ('contender', 'championship')


# ── Availability ───────────────────────────────────────────────────────────

def saved(probability=.6, **changes):
    result = {'model_version': VERSION, 'viewer_roster_id': 1, 'captured_at': '2026-11-10T15:00:00+00:00',
              'coverage': {'estimate_status': 'complete'},
              'teams': [{'roster_id': 1, 'playoff_probability': probability},
                        {'roster_id': 2, 'playoff_probability': .99}]}
    result.update(changes)
    return result


def test_available_suggestion_compares_with_the_saved_outlook():
    block = build('current', saved(), 'rebuilder', CUTS)
    assert block['status'] == 'available' and block['reason'] is None
    assert block['recommended_outlook'] == 'contender' and block['differs'] is True
    assert block['playoff_probability'] == .6 and block['current_outlook'] == 'rebuilder'
    assert 'starting lineup' in block['suggestion'] and '60.0%' in block['explanation']
    assert build('current', saved(), 'contender', CUTS)['differs'] is False
    assert build('current', saved(), None, CUTS)['differs'] is True
    assert build('current', saved(), 'not_sure', CUTS)['differs'] is True


def test_all_in_copy_says_it_is_not_a_guarantee():
    block = build('current', saved(.9), 'contender', CUTS)
    assert block['recommended_outlook'] == 'championship'
    assert 'suggestion, not a guarantee' in block['suggestion'] and 'title favorite' in block['suggestion']
    assert all('Consider' in text for text in recommendation.SUGGESTIONS.values())


@pytest.mark.parametrize('state,result,reason', [
    ('no_run', None, 'no_forecast'),
    ('queued', None, 'update_pending'),
    ('running', saved(), 'update_pending'),
    ('stale', saved(), 'stale'),
    ('refresh_failed', saved(), 'refresh_failed'),
    ('incomplete_projections', saved(), 'refresh_failed'),
    ('unsupported_policy', saved(), 'unsupported'),
    ('current', saved(model_version='joint-season-scenario-v4'), 'old_model'),
    ('current', saved(coverage={'estimate_status': 'incomplete'}), 'incomplete'),
    ('current', saved(coverage={}), 'incomplete'),
    ('current', saved(viewer_roster_id=None), 'team_not_found'),
    ('current', saved(viewer_roster_id=9), 'team_not_found'),
    ('current', saved(float('nan')), 'team_not_found'),
    ('current', saved(1.2), 'team_not_found'),
])
def test_no_confident_suggestion_without_a_current_complete_current_model_forecast(state, result, reason):
    block = build(state, result, 'rebuilder', CUTS)
    assert block['status'] == 'unavailable' and block['reason'] == reason
    assert block['recommended_outlook'] is None and block['playoff_probability'] is None
    assert block['differs'] is False and block['suggestion'] is None and block['explanation']
    assert block['current_outlook'] == 'rebuilder'


# ── The saved-run route ────────────────────────────────────────────────────

def seed(engine, result, *, age_days=0):
    now = datetime.now(timezone.utc)
    row = {'run_id': 'a' * 32, 'user_id': 'account', 'league_id': '123', 'status': 'complete',
           'created_at': (now - timedelta(days=age_days)).isoformat(), 'updated_at': now.isoformat(),
           'expires_at': now.isoformat(), 'request_hash': 'synthetic',
           'input_json': json.dumps({'expected_model_version': result['model_version']}),
           'result_json': json.dumps(result), 'input_hash': 'synthetic'}
    with engine.begin() as conn:
        conn.execute(db.league_projection_runs_table.insert().values(**row))
        conn.execute(db.league_projection_targets_table.insert().values(
            target_id='target', user_id='account', league_id='123', league_user_id='account', season=2026,
            created_at=now.isoformat(), next_due_at=(now + timedelta(days=7)).isoformat(),
            last_success_id='a' * 32, last_attempt_id='a' * 32))


def test_reading_the_suggestion_never_changes_the_saved_outlook(client, engine, monkeypatch):
    http, _ = client
    db.upsert_league_preference('account', '123', 'rebuilder')
    before = db.load_league_preference(user_id='account', league_id='123')
    seed(engine, saved())
    monkeypatch.setattr(db, 'upsert_league_preference',
                        lambda *a, **k: pytest.fail('a read wrote the saved outlook'))
    for _ in range(3):
        body = http.get('/api/leagues/123/projection-runs/latest').json
    block = body['outlook_recommendation']
    assert body['state'] == 'current' and body['model_current'] is True
    assert block['status'] == 'available' and block['recommended_outlook'] == 'contender'
    assert block['current_outlook'] == 'rebuilder' and block['differs'] is True
    assert db.load_league_preference(user_id='account', league_id='123') == before
    # The Team Review reader is the same pure read.
    assert recommendation.load('account', '123', 'rebuilder') == block
    assert db.load_league_preference(user_id='account', league_id='123') == before


def test_old_model_forecast_is_kept_dated_and_stale_and_suggests_nothing(client, engine):
    http, _ = client
    seed(engine, saved(model_version='joint-season-scenario-v4'))
    body = http.get('/api/leagues/123/projection-runs/latest').json
    assert body['model_current'] is False
    assert body['state'] == 'stale' and body['reason'] == 'projection_model_updated'
    # Still on record with its date, for the "last saved" display.
    assert body['run']['result']['captured_at'] == '2026-11-10T15:00:00+00:00'
    block = body['outlook_recommendation']
    assert block['status'] == 'unavailable' and block['reason'] == 'old_model'
    assert block['recommended_outlook'] is None


def test_week_old_forecast_is_stale_and_suggests_nothing(client, engine):
    http, _ = client
    seed(engine, saved(), age_days=8)
    body = http.get('/api/leagues/123/projection-runs/latest').json
    assert body['state'] == 'stale' and body['model_current'] is True
    assert body['outlook_recommendation']['reason'] == 'stale'


def test_flag_off_ships_no_block(client, engine, monkeypatch):
    http, _ = client
    seed(engine, saved())
    monkeypatch.setattr(api, 'is_enabled', lambda key: key != 'league.projection_outlook')
    body = http.get('/api/leagues/123/projection-runs/latest').json
    assert 'outlook_recommendation' not in body and body['model_current'] is True


def test_a_scenario_cannot_bring_its_own_sd(client, engine, monkeypatch):
    http, _ = client
    monkeypatch.setattr(store, 'create', lambda *a, **k: {'run_id': 'c' * 32, 'status': 'queued', 'created_at': 'x', 'updated_at': 'x'})
    model = batch.settings()['model']
    assert http.post('/api/leagues/123/projection-runs', json={'config': {**model, 'score_sd': 10}}).json == {'error': 'score_sd_is_app_wide'}
    assert http.post('/api/leagues/123/projection-runs', json={'config': {**model, 'historical_weight': .4}}).json == {'error': 'unknown_configuration'}
    assert http.post('/api/leagues/123/projection-runs', json={'config': model}).status_code == 202


# ── Fresh baselines after a model change, through the scheduled batch ──────

@pytest.fixture
def scheduled(engine, monkeypatch):
    monkeypatch.setattr(batch, 'is_enabled', lambda key: True)
    monkeypatch.setattr(service, 'wake', lambda *a, **kw: None)
    with engine.begin() as conn:
        conn.execute(db.leagues_table.insert().values(sleeper_league_id='123', user_id='account', platform='sleeper', season='2026'))
    return engine


def test_a_baseline_from_another_model_is_refreshed_once_by_the_next_scheduled_tick(scheduled):
    seed(scheduled, saved(model_version='joint-season-scenario-v4'))
    assert batch.dispatch(lambda *a: pytest.fail('enqueue only'))['queued'] == 1
    target = batch.target('account', '123')
    assert target['last_attempt_id'] != 'a' * 32 and target['last_success_id'] == 'a' * 32
    assert datetime.fromisoformat(target['next_due_at']) > datetime.now(timezone.utc)
    # The new attempt carries the current version, so nothing loops.
    with scheduled.begin() as conn:
        conn.execute(db.league_projection_runs_table.update().where(
            db.league_projection_runs_table.c.run_id == target['last_attempt_id']).values(status='failed'))
    assert batch.dispatch(lambda *a: pytest.fail('enqueue only'))['queued'] == 0
    # The old forecast is still what a view gets, labelled by the route as stale.
    assert batch.view('account', '123')['run']['run_id'] == 'a' * 32


def test_a_current_model_baseline_waits_for_its_weekly_slot(scheduled):
    seed(scheduled, saved())
    assert batch.dispatch(lambda *a: pytest.fail('enqueue only'))['queued'] == 0


# ── Team Review precedence ─────────────────────────────────────────────────

AVAILABLE = build('current', saved(.05), 'contender', CUTS)
UNAVAILABLE = build('stale', saved(), 'contender', CUTS)


@pytest.mark.parametrize('composite,odds_source,implied', [
    (True, 'odds', 'contender'), (False, 'odds', 'contender'), (False, 'roster', None), (False, None, None),
])
def test_available_projection_suggestion_outranks_every_roster_read(composite, odds_source, implied):
    assert team_review.resolve_window_precedence(composite, odds_source, implied, 'rebuilder', AVAILABLE) == ('projection', 'jets')


@pytest.mark.parametrize('projection', [None, UNAVAILABLE])
@pytest.mark.parametrize('composite,odds_source,implied', [
    (True, 'odds', 'contender'), (False, 'odds', 'contender'), (False, 'roster', None), (False, None, None),
])
def test_without_an_available_suggestion_the_old_precedence_is_untouched(projection, composite, odds_source, implied):
    old = team_review.resolve_window_precedence(composite, odds_source, implied, 'rebuilder')
    assert team_review.resolve_window_precedence(composite, odds_source, implied, 'rebuilder', projection) == old


def test_window_block_carries_the_suggestion_and_both_verdicts():
    plain = team_review._window('rebuilder', {}, 'contender', 12)
    assert 'projection' not in plain and 'source' not in plain
    window = team_review._window('jets', {}, 'contender', 12, source='projection',
                                 roster_inferred='rebuilder', projection=AVAILABLE)
    assert window['inferred'] == 'jets' and window['roster_inferred'] == 'rebuilder'
    assert window['declared'] == 'contender'  # the saved outlook is reported, never replaced
    assert window['source'] == 'projection' and window['projection'] == AVAILABLE
    quiet = team_review._window('rebuilder', {}, 'contender', 12, projection=UNAVAILABLE)
    assert quiet['projection']['status'] == 'unavailable' and 'source' not in quiet
    assert {k: v for k, v in quiet.items() if k != 'projection'} == plain


# ── Review fixes: say why there is no suggestion ───────────────────────────

MISSING = 'missing_weekly_projections'


@pytest.mark.parametrize('state,result,captured', [
    ('refresh_failed', saved(), '2026-11-10T15:00:00+00:00'),
    ('incomplete_projections', None, None),
])
def test_missing_projections_are_named_as_the_reason(state, result, captured):
    block = build(state, result, 'rebuilder', CUTS, failure_reason=MISSING)
    assert block['status'] == 'unavailable' and block['reason'] == 'missing_projections'
    assert block['explanation'] == recommendation.UNAVAILABLE['missing_projections']
    assert 'Past scoring is never used' in block['explanation']
    assert block['captured_at'] == captured and block['recommended_outlook'] is None


@pytest.mark.parametrize('state,result,reason', [
    ('current', saved(), None),                     # an older failure never hides a current run
    ('queued', saved(), 'update_pending'),
    ('running', None, 'update_pending'),
    ('unsupported_policy', saved(), 'unsupported'),
    ('refresh_failed', saved(model_version='joint-season-scenario-v4'), 'old_model'),
])
def test_missing_projections_keeps_the_existing_priorities(state, result, reason):
    assert build(state, result, 'rebuilder', CUTS, failure_reason=MISSING)['reason'] == reason


def test_read_failed_block_is_unavailable_and_explains_itself():
    block = recommendation.unavailable('read_failed', 'contender')
    assert block['status'] == 'unavailable' and block['reason'] == 'read_failed'
    assert block['explanation'] == 'The saved forecast could not be read just now, so no outlook is suggested.'
    assert block['current_outlook'] == 'contender' and block['recommended_outlook'] is None
    assert team_review.resolve_window_precedence(False, None, None, 'rebuilder', block) == (None, 'rebuilder')


def seed_runs(engine, success=None, attempt=None):
    """`success`: a saved result; `attempt`: (status, reason), newer than it."""
    now = datetime.now(timezone.utc)
    common = {'user_id': 'account', 'league_id': '123', 'updated_at': now.isoformat(), 'expires_at': now.isoformat(),
              'request_hash': 'synthetic', 'input_hash': 'synthetic'}
    with engine.begin() as conn:
        if success:
            conn.execute(db.league_projection_runs_table.insert().values(
                run_id='a' * 32, status='complete', created_at=now.isoformat(), result_json=json.dumps(success),
                input_json=json.dumps({'expected_model_version': success['model_version']}), **common))
        if attempt:
            conn.execute(db.league_projection_runs_table.insert().values(
                run_id='b' * 32, status=attempt[0], reason=attempt[1], created_at=(now + timedelta(seconds=1)).isoformat(),
                input_json=json.dumps({'expected_model_version': VERSION}), **common))
        conn.execute(db.league_projection_targets_table.insert().values(
            target_id='target', user_id='account', league_id='123', league_user_id='account', season=2026,
            created_at=now.isoformat(), next_due_at=(now + timedelta(days=7)).isoformat(),
            last_success_id='a' * 32 if success else None, last_attempt_id='b' * 32 if attempt else 'a' * 32))


def test_old_model_success_with_a_queued_attempt_is_queued_and_old_model(client, engine):
    http, _ = client
    seed_runs(engine, saved(model_version='joint-season-scenario-v4'), ('queued', None))
    body = http.get('/api/leagues/123/projection-runs/latest').json
    assert body['model_current'] is False and body['state'] == 'queued'
    assert body['outlook_recommendation']['reason'] == 'old_model'
    assert recommendation.load('account', '123', None) == {**body['outlook_recommendation'], 'current_outlook': None}


def test_failed_refresh_for_missing_projections_keeps_the_old_run_and_says_why(client, engine):
    http, _ = client
    seed_runs(engine, saved(), ('failed', MISSING))
    body = http.get('/api/leagues/123/projection-runs/latest').json
    assert body['state'] == 'refresh_failed' and body['reason'] == MISSING
    assert body['run']['result']['captured_at'] == '2026-11-10T15:00:00+00:00'
    block = body['outlook_recommendation']
    assert block['reason'] == 'missing_projections' and block['captured_at'] == '2026-11-10T15:00:00+00:00'
    assert recommendation.load('account', '123', None)['reason'] == 'missing_projections'


def test_first_run_stopped_for_missing_projections_says_why(client, engine):
    http, _ = client
    seed_runs(engine, None, ('incomplete_projections', MISSING))
    body = http.get('/api/leagues/123/projection-runs/latest').json
    assert body['state'] == 'incomplete_projections' and body['run'] is None
    block = body['outlook_recommendation']
    assert block['reason'] == 'missing_projections' and block['captured_at'] is None
    assert recommendation.load('account', '123', None)['reason'] == 'missing_projections'


# ── Team Review route: the suggestion wiring, end to end ───────────────────

@pytest.fixture
def review(engine, monkeypatch):
    """The real GET /api/league/team-review over the power-rankings world."""
    from unittest.mock import MagicMock
    import backend.server as server
    from backend.tests import test_power_rankings as pr
    flags = {'trades.team_review', 'league.projection_outlook', 'league.projections'}
    monkeypatch.setattr(server, 'is_enabled', lambda key: key in flags)
    monkeypatch.setattr(server, 'touch_user_activity', MagicMock())
    monkeypatch.setattr(server, 'load_league_members', pr._members_rows)
    monkeypatch.setattr(server, 'load_draft_picks', lambda league_id=None, **kw: pr._pick_rows(league_id))
    monkeypatch.setattr(server, '_get_universal_pool', pr._fake_pool)
    monkeypatch.setattr(server, 'get_league_draft_context', lambda league_id: {'platform': 'sleeper'})
    monkeypatch.setattr(server, '_league_lineup_slots', lambda league_id: None)

    def offline(*a, **k):
        raise RuntimeError('offline')
    monkeypatch.setattr(server, '_outlook_sleeper_fetch', lambda *a, **k: offline)
    for module in (server, db):
        monkeypatch.setattr(module, 'upsert_league_preference', lambda *a, **k: pytest.fail('a GET wrote the saved outlook'))
    with engine.begin() as conn:
        conn.execute(db.league_preferences_table.insert().values(
            user_id='u_a', league_id=pr.LEAGUE, team_outlook='contender', updated_at='2026-11-01T00:00:00+00:00'))
    server.app.config['TESTING'] = True
    with server._sessions_lock:
        server._sessions[pr.TOKEN] = pr._mk_sess()
    calls = []

    def get(load=None):
        if load is not None:
            def spy(*args):
                calls.append(args)
                return load(*args)
            monkeypatch.setattr(recommendation, 'load', spy)
        before = db.load_league_preference(user_id='u_a', league_id=pr.LEAGUE)
        response = server.app.test_client().get(f'/api/league/team-review?league_id={pr.LEAGUE}', headers=pr._h())
        assert response.status_code == 200, response.data
        assert db.load_league_preference(user_id='u_a', league_id=pr.LEAGUE) == before
        assert before['team_outlook'] == 'contender'
        return response.json['window']
    try:
        yield get, flags, calls
    finally:
        with server._sessions_lock:
            server._sessions.pop(pr.TOKEN, None)


def test_team_review_route_uses_an_available_suggestion_and_keeps_the_roster_verdict(review):
    get, flags, calls = review
    flags.discard('league.projection_outlook')
    baseline = get(lambda *a: pytest.fail('flag off must not read the saved run'))
    roster_verdict = baseline['inferred']
    assert 'projection' not in baseline and calls == []
    flags.add('league.projection_outlook')
    suggestion = 'jets' if roster_verdict != 'jets' else 'championship'
    available = {**AVAILABLE, 'recommended_outlook': suggestion, 'current_outlook': 'contender'}
    window = get(lambda *a: available)
    assert calls == [('u_a', 'league_pr_test', 'contender')]
    assert window['source'] == 'projection' and window['inferred'] == suggestion
    assert window['roster_inferred'] == roster_verdict and window['projection'] == available
    assert window['declared'] == 'contender'


def test_team_review_route_flag_off_window_is_identical_to_never_loading(review):
    get, flags, calls = review
    flags.discard('league.projection_outlook')
    off = get(lambda *a: pytest.fail('flag off must not read the saved run'))
    assert calls == []
    flags.add('league.projection_outlook')
    flags.discard('league.projections')
    never = get(lambda *a: pytest.fail('projections off must not read the saved run'))
    assert calls == []
    assert set(off) == set(never) and off == never
    assert 'projection' not in off


def test_team_review_route_ships_read_failed_instead_of_falling_back_silently(review):
    get, flags, calls = review
    flags.discard('league.projection_outlook')
    roster_verdict = get()['inferred']
    flags.add('league.projection_outlook')

    def broken(*a):
        raise RuntimeError('database unavailable')
    window = get(broken)
    assert len(calls) == 1
    assert window['projection']['status'] == 'unavailable' and window['projection']['reason'] == 'read_failed'
    assert window['projection']['current_outlook'] == 'contender'
    assert window['inferred'] == roster_verdict and window.get('source') != 'projection'
