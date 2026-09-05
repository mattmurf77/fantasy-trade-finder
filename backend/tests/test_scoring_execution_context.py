"""Budget scalability milestone: preserve request/job ownership and scoring.

Pins overlapping request format reads, persistent session writes, delayed
worker start after same-token reinitialization, explicit pregen/cron format,
job-local member/pick mutations, and shared pending-card/decision behavior.
Fixture-only; no worker sleeps, external services, or production database.
"""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError
from threading import Barrier
from unittest.mock import Mock

import pytest
from sqlalchemy import create_engine

import backend.database as db
import backend.server as server
from backend.ranking_service import Player, RankingService
from backend.trade_service import League, LeagueMember, TradeCard, TradeService

TOKEN = 'context-test-token'
USER = 'context-user'
LEAGUE = 'context-league'
FORMATS = ('1qb_ppr', 'sf_tep')


@pytest.fixture
def world(monkeypatch):
    engine = create_engine('sqlite:///:memory:')
    db.metadata.create_all(engine)
    monkeypatch.setattr(db, 'engine', engine)
    monkeypatch.setattr(server, 'is_enabled', lambda key: False)
    # The engine and server both consult the same flag module in real runs;
    # this test exercises their default generation pipeline with extras off.
    import backend.feature_flags as flags
    monkeypatch.setattr(flags, '_flags_cache', {k: False for k in flags.DEFAULT_FLAGS})
    pool = [Player(id=p, name=p.upper(), position='RB', team='AAA', age=25)
            for p in ('give', 'receive')]
    league = League(LEAGUE, 'Context League', 'sleeper', [
        LeagueMember(USER, 'Me', ['give'], {}),
        LeagueMember('opponent', 'Original opponent', ['receive'], {})])
    services = {fmt: RankingService(pool, seed_ratings={p.id: 1500 + i * 100
                for p in pool}) for i, fmt in enumerate(FORMATS)}
    trades = {fmt: TradeService({p.id: p for p in pool}) for fmt in FORMATS}
    for svc in trades.values():
        svc.add_league(league)
    sess = dict(user_id=USER, league_user_id=USER, league=league,
                user_roster=['give'], players=pool, services=services,
                trade_svcs=trades, service=services[FORMATS[0]],
                trade_svc=trades[FORMATS[0]], active_format=FORMATS[0],
                last_active=0)
    monkeypatch.setitem(server._sessions, TOKEN, sess)
    monkeypatch.setattr(server, '_get_session', lambda token: sess if token == TOKEN else None)
    monkeypatch.setattr(server, 'load_member_rankings', Mock(return_value={}))
    monkeypatch.setattr(server, 'load_league_preference', Mock(return_value=None))
    monkeypatch.setattr(server, 'record_event', Mock())
    original_jobs = set(server._trade_jobs)
    yield sess
    for jid in set(server._trade_jobs) - original_jobs:
        job = server._trade_jobs.pop(jid)
        if server._trade_jobs_by_key.get(job['key']) == jid:
            server._trade_jobs_by_key.pop(job['key'])
    engine.dispose()


def test_overlapping_requests_keep_format_aliases_and_identity(world):
    barrier = Barrier(2)

    def read(fmt):
        with server.app.test_request_context(headers={
                'X-Session-Token': TOKEN, 'X-Scoring-Format': fmt}):
            sess = server._require_session()
            barrier.wait(timeout=5)
            assert server._require_session() is sess
            assert sess['user_id'] == USER
            assert sess['league'].league_id == LEAGUE
            assert server._active_format(sess) == fmt
            assert sess['service'] is world['services'][fmt]
            assert sess['trade_svc'] is world['trade_svcs'][fmt]

    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(read, FORMATS))
    assert world['active_format'] == FORMATS[0]
    assert world['service'] is world['services'][FORMATS[0]]
    assert '_effective_format' not in world


def test_view_writes_persist_and_rebound_identity_cannot_receive_old_auth(world):
    with server.app.test_request_context(headers={'X-Session-Token': TOKEN}):
        sess = server._require_session()
        with server._sessions_lock:  # legacy callers may already hold this lock
            sess['last_active'] = 123
            sess.update(verified=True, account_id='account-old')
            sess.setdefault('verified_via', 'fixture')
            assert sess.pop('verified_via') == 'fixture'
        assert world['last_active'] == 123
        assert world['verified'] is True
        assert world['account_id'] == 'account-old'
        assert 'verified_via' not in world
        world.update(user_id='another-user', account_id='another-account', verified=False)
        sess['verified'] = True
        sess['provider_cookie'] = 'old-identity-cookie'
        assert world['verified'] is False
        assert 'provider_cookie' not in world
        assert sess['user_id'] == USER


def test_switch_persists_but_existing_request_retains_selection(world):
    with server.app.test_request_context(headers={'X-Session-Token': TOKEN}):
        first = server._require_session()
        with server.app.app_context(), server.app.test_request_context(
                '/api/scoring/switch', method='POST', json={'format': FORMATS[1]},
                headers={'X-Session-Token': TOKEN}):
            response = server.switch_scoring_format.__wrapped__()
            assert response.get_json() == {'ok': True, 'active_format': FORMATS[1]}
        assert server._active_format(first) == FORMATS[0]
        assert first['service'] is world['services'][FORMATS[0]]
    # Stale historical scratch state is never the default for headless jobs.
    world['_effective_format'] = FORMATS[0]
    with server.app.test_request_context(headers={'X-Session-Token': TOKEN,
                                                 'X-Scoring-Format': 'invalid'}):
        assert server._active_format(server._require_session()) == FORMATS[1]
    assert server._active_format(world) == FORMATS[1]


@pytest.mark.parametrize('scoring_format', FORMATS)
def test_delayed_job_keeps_kickoff_context_and_options(world, monkeypatch, scoring_format):
    pending = []
    class DeferredThread:
        def __init__(self, *, target, args, kwargs, daemon):
            pending.append((target, args, kwargs))
        def start(self):
            pass
    monkeypatch.setattr(server.threading, 'Thread', DeferredThread)
    observed = []
    def generate(self, **kwargs):
        observed.append((self, kwargs))
        return []
    monkeypatch.setattr(TradeService, 'generate_trades', generate)
    pins = ['give']
    prefs = {'prefs': {'team_outlook': 'contend'}, 'seeded_outlook': None}
    old_service = world['services'][scoring_format]
    job_id = server._kickoff_trade_job(
        TOKEN, USER, LEAGUE, scoring_format, pinned_give=pins,
        pinned_give_mode='all', prefs_preload=prefs)
    pins.append('later-pin')
    prefs['prefs']['team_outlook'] = 'rebuild'
    world.update(user_id='different-user', league=League('different-league', 'New', 'sleeper', []),
                 services={}, trade_svcs={}, service=object(), trade_svc=object(),
                 active_format=FORMATS[1], _effective_format=FORMATS[1],
                 user_roster=['different-player'])
    target, args, kwargs = pending.pop()
    ctx = kwargs['execution_context']
    with pytest.raises(FrozenInstanceError):
        ctx.scoring_format = 'changed'
    assert ctx.service is old_service
    target(*args, **kwargs)
    assert server._trade_jobs[job_id]['status'] == 'complete', server._trade_jobs[job_id]['error']
    service, generated = observed[0]
    assert generated['user_id'] == USER
    assert generated['league_id'] == LEAGUE
    assert generated['scoring_format'] == scoring_format
    assert generated['user_roster'] == ['give']
    assert generated['pinned_give_players'] == ['give']
    assert generated['pinned_give_mode'] == 'all'
    assert generated['outlook'] == 'contend'
    assert generated['user_elo']['give'] == old_service._seed['give']
    assert service._leagues[LEAGUE] is ctx.league
    assert server.record_event.call_args.args[:2] == (USER, 'trades_generated')
    assert server.record_event.call_args.kwargs['league_id'] == LEAGUE


def test_job_member_and_pick_mutations_are_private_but_cards_and_decisions_live(world, monkeypatch):
    selected = world['trade_svcs'][FORMATS[1]]
    ctx = server._capture_trade_execution(world, USER, LEAGUE, FORMATS[1])
    other = server._capture_trade_execution(world, USER, LEAGUE, FORMATS[0])
    ctx.league.members[1].elo_ratings['receive'] = 1900
    ctx.league.members[1].username = 'Ranked opponent'
    ctx.league.members[1].has_rankings = True
    pick = Player(id=LEAGUE + '_pick', name='Pick', position='PICK', team='', age=0)
    monkeypatch.setattr(server, '_owned_pick_assets', lambda *a: {'opponent': [pick]})
    monkeypatch.setattr(server, '_pick_asset_elos', lambda *a: {pick.id: 1200})
    server._inject_owned_picks(league_id=LEAGUE, scoring_format=FORMATS[1],
        trade_service=ctx.trade_service, players_dict={}, seed_map={}, user_elo={},
        user_id=USER, user_roster=list(ctx.user_roster), league=ctx.league, picks=[])
    for league in (world['league'], other.league):
        assert league.members[1].roster == ['receive']
        assert league.members[1].elo_ratings == {}
        assert league.members[1].username == 'Original opponent'
        assert not league.members[1].has_rankings
    assert pick.id not in selected._players
    card = TradeCard('context-card', LEAGUE, USER, 'opponent', 'Opponent',
                     ['give'], ['receive'], 10, 1, 10)
    ctx.trade_service._trade_cards[card.trade_id] = card
    assert selected.get_pending_trades(USER) == [card]
    assert selected.record_decision(card.trade_id, 'like') is card
    key = (frozenset(['give']), frozenset(['receive']))
    selected._past_decision_keys.add(key)
    selected._dismissed_decision_keys.add(key)
    assert key in ctx.trade_service._past_decision_keys
    assert key in ctx.trade_service._dismissed_decision_keys
    assert world['trade_svcs'][FORMATS[0]].get_pending_trades(USER) == []


def test_request_view_reaches_kickoff_even_after_session_reinit(world, monkeypatch):
    with server.app.test_request_context(headers={'X-Session-Token': TOKEN,
                                                 'X-Scoring-Format': FORMATS[1]}):
        view = server._require_session()
        original = world['services'][FORMATS[1]]
        world.update(league=League('new-league', 'New', 'sleeper', []), services={})
        captured = Mock()
        monkeypatch.setattr(server, '_run_trade_job', captured)
        job_id = server._kickoff_trade_job(TOKEN, USER, LEAGUE, FORMATS[1],
                                          synchronous=True, session_context=view)
        assert captured.call_args.kwargs['execution_context'].service is original
        assert server._trade_jobs[job_id]['key'] == (USER, LEAGUE, FORMATS[1])


def test_overlapping_jobs_read_their_own_format_member_rankings(world, monkeypatch):
    barrier = Barrier(2)
    def ranked_members(*, league_id, exclude_user_id, scoring_format):
        return {'opponent': {'elo_ratings': {'receive': 1800 if scoring_format == FORMATS[0] else 2200},
                             'username': scoring_format}}
    monkeypatch.setattr(server, 'load_member_rankings', ranked_members)
    monkeypatch.setattr(server, 'log_trade_impressions', Mock())
    observed = {}
    def generate(self, **kwargs):
        barrier.wait(timeout=5)  # both jobs have already injected member rankings
        member = self._leagues[LEAGUE].members[1]
        observed[kwargs['scoring_format']] = (member.username, member.elo_ratings['receive'])
        return []
    monkeypatch.setattr(TradeService, 'generate_trades', generate)
    def run(fmt):
        return server._kickoff_trade_job(TOKEN, USER, LEAGUE, fmt, synchronous=True)
    with ThreadPoolExecutor(max_workers=2) as executor:
        jobs = list(executor.map(run, FORMATS))
    assert all(server._trade_jobs[jid]['status'] == 'complete' for jid in jobs)
    assert observed == {FORMATS[0]: (FORMATS[0], 1800), FORMATS[1]: (FORMATS[1], 2200)}
    assert world['league'].members[1].elo_ratings == {}
    assert world['league'].members[1].username == 'Original opponent'


def test_missing_session_still_returns_a_registered_error_job(world):
    job_id = server._kickoff_trade_job('expired-token', USER, LEAGUE, FORMATS[0])
    job = server._trade_jobs[job_id]
    assert job['key'] == (USER, LEAGUE, FORMATS[0])
    assert job['status'] == 'error'
    assert job['error'] == 'session expired before trade job started'
    assert server._trade_job_public_view(job)['job_id'] == job_id


def test_unregistered_league_override_keeps_existing_engine_error_job(world):
    job_id = server._kickoff_trade_job(TOKEN, USER, 'unregistered-league',
                                      FORMATS[0], synchronous=True)
    job = server._trade_jobs[job_id]
    assert job['status'] == 'error'
    assert job['error'] == "Unknown league: 'unregistered-league'"
    assert job['cards'] == []
