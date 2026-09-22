"""Adopted read fencing: local safety changes, never synthetic activity."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import json
import socket

import pytest
from sqlalchemy import create_engine, event, insert, update
from sqlalchemy.pool import StaticPool

from backend import database as db
from backend import prepared_trade_read_guard as guard
from backend.prepared_trade_store import InventoryScope
from backend.ranking_service import Player


NOW = datetime(2026, 9, 22, 15, tzinfo=timezone.utc)
SCOPE = InventoryScope("alice", "league", "alice", "1qb_ppr", "request")


@pytest.fixture
def setup(monkeypatch):
    engine = create_engine("sqlite://", poolclass=StaticPool)
    db.metadata.create_all(engine)
    monkeypatch.setattr(db, "engine", engine)
    with engine.begin() as conn:
        conn.execute(insert(db.leagues_table).values(sleeper_league_id="league", user_id="alice",
            roster_data='["a"]', opponent_data='[{"user_id":"bob","player_ids":["b"]}]',
            season="2026", platform="sleeper", default_scoring="1qb_ppr", updated_at="first"))
        conn.execute(insert(db.league_members_table), [dict(league_id="league", user_id=uid,
            roster_data=json.dumps([pid]), updated_at="first") for uid, pid in (("alice", "a"), ("bob", "b"))])
        conn.execute(insert(db.draft_picks_table).values(pick_id="pick", league_id="league", season=2027,
            round=1, owner_user_id="alice", pool_value=600., synced_at="first"))
    flags = {"trade.prepared_inventory": True}
    server = SimpleNamespace(
        _trade_service_mod=SimpleNamespace(_cfg={"prepared_trade_inventory_enabled": 1., "floor": .8}),
        _ranking_service_mod=SimpleNamespace(_cfg={"scale": 1.}),
        flags_dict=lambda: deepcopy(flags), is_enabled=lambda name: flags.get(name, False),
        _bakeoff=SimpleNamespace(owner_arm=lambda: "owner_v2_bilateral", owner_version=lambda: "owner-v2-bilateral-2"),
        g_universal_by_format={"1qb_ppr": {"players": [Player("a", "A", "WR", "X", 24),
            Player("b", "B", "QB", "Y", 27)], "seed": {"a": 1500., "b": 1550.}}},
        _sleeper_cache={"a": {"fantasy_positions": ["WR"], "injury_status": None},
                        "b": {"fantasy_positions": ["QB"], "injury_status": None}},
        _players_cache_age_seconds=lambda: 1.,
        _FA_LEAGUE_META_CACHE={"league": (123., {"roster_positions": ["QB", "WR", "BN"],
            "scoring_settings": {"rec": 1.}, "settings": {"taxi_slots": 2}})},
    )
    def forbidden(*a, **k):
        raise AssertionError("read guard must not fetch or mutate")
    server._sleeper_get = server._load_sleeper_cache = server.record_event = forbidden
    server._trade_job_preferences = server._get_universal_pool = forbidden
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    return server, engine, flags


def capture(server, **kwargs):
    return guard.capture(server, SCOPE, expires_at=NOW + timedelta(hours=24), now=NOW, **kwargs)


def test_strict_detached_json_and_original_bounded_expiry(setup):
    server, _, _ = setup
    value = capture(server)
    assert json.loads(json.dumps(value, allow_nan=False)) == value
    assert value["scope"] == SCOPE.as_dict()
    assert value["expires_at"] == (NOW + timedelta(minutes=30)).isoformat()
    assert guard.valid(server, value, scope=SCOPE, now=NOW + timedelta(minutes=29))
    assert not guard.valid(server, value, now=NOW + timedelta(minutes=30))
    shorter = guard.capture(server, SCOPE, expires_at=NOW + timedelta(seconds=10), now=NOW)
    assert not guard.valid(server, shorter, now=NOW + timedelta(seconds=10))


@pytest.mark.parametrize("change", [
    lambda s: s._trade_service_mod._cfg.update(floor=.9),
    lambda s: s._ranking_service_mod._cfg.update(scale=2.),
    lambda s: s.g_universal_by_format["1qb_ppr"]["seed"].update(a=1600.),
    lambda s: setattr(s.g_universal_by_format["1qb_ppr"]["players"][0], "age", 25),
    lambda s: s._sleeper_cache["a"].update(injury_status="Out"),
    lambda s: s._sleeper_cache["a"].update(fantasy_positions=["RB", "WR"]),
    lambda s: setattr(s, "_players_cache_age_seconds", lambda: 48 * 3600 + 1),
    lambda s: s._FA_LEAGUE_META_CACHE["league"][1].update(roster_positions=["QB", "SUPER_FLEX"]),
    lambda s: s._FA_LEAGUE_META_CACHE["league"][1]["scoring_settings"].update(rec=.5),
    lambda s: setattr(s._bakeoff, "owner_version", lambda: "different"),
])
def test_current_safety_inputs_revoke(setup, change):
    server, _, _ = setup
    before = capture(server)
    change(server)
    assert not guard.valid(server, before, now=NOW)


@pytest.mark.parametrize("table,values", [
    (db.draft_picks_table, {"owner_user_id": "bob"}),
    (db.draft_picks_table, {"pool_value": 650.}),
    (db.league_members_table, {"roster_data": '["changed"]'}),
    (db.leagues_table, {"default_scoring": "sf_tep"}),
    (db.leagues_table, {"draft_slot_order": '{"slots":{"1":2}}'}),
])
def test_sql_pick_roster_scoring_changes_revoke(setup, table, values):
    server, engine, _ = setup
    before = capture(server)
    with engine.begin() as conn:
        conn.execute(update(table).values(**values))
    assert not guard.valid(server, before, now=NOW)


def test_harmless_sync_json_formatting_and_unrelated_league_do_not_revoke(setup):
    server, engine, _ = setup
    before = capture(server)
    with engine.begin() as conn:
        conn.execute(update(db.draft_picks_table).values(id=40, synced_at="later"))
        conn.execute(update(db.league_members_table).values(updated_at="later"))
        conn.execute(update(db.leagues_table).values(updated_at="later", roster_data='[ "a" ]'))
        conn.execute(insert(db.leagues_table).values(sleeper_league_id="unrelated", user_id="other"))
    server._FA_LEAGUE_META_CACHE["league"] = (9999., server._FA_LEAGUE_META_CACHE["league"][1])
    assert guard.valid(server, before, now=NOW)


def test_ordinary_actions_and_training_do_not_invalidate_entire_inventory(setup):
    server, engine, _ = setup
    before = capture(server)
    with engine.begin() as conn:
        conn.execute(insert(db.swipe_decisions_table).values(user_id="alice", winner_player_id="a",
            loser_player_id="b", decision_type="trade", k_factor=3.))
        conn.execute(insert(db.trade_decisions_table).values(user_id="alice", league_id="league",
            give_player_ids='["a"]', receive_player_ids='["b"]', decision="like"))
        conn.execute(insert(db.member_rankings_table).values(league_id="league", user_id="alice",
            player_id="a", elo=2000.))
    assert guard.valid(server, before, now=NOW)


@pytest.mark.parametrize("mutation", [
    lambda s, f: f.update({"trade.prepared_inventory": False}),
    lambda s, f: s._trade_service_mod._cfg.update(prepared_trade_inventory_enabled=0.),
    lambda s, f: s.g_universal_by_format.clear(),
    lambda s, f: setattr(s, "_sleeper_cache", None),
    lambda s, f: s._FA_LEAGUE_META_CACHE.clear(),
    lambda s, f: s.g_universal_by_format["1qb_ppr"]["seed"].update(a=float("nan")),
])
def test_disabled_missing_or_malformed_inputs_fail_closed(setup, mutation):
    server, _, flags = setup
    before = capture(server)
    mutation(server, flags)
    assert not guard.valid(server, before, now=NOW)
    with pytest.raises(ValueError):
        capture(server)


@pytest.mark.parametrize("bad", [None, {}, {"schema": "future"}, []])
def test_malformed_guard_fails_closed_without_source_reads(setup, bad):
    assert not guard.valid(setup[0], bad, now=NOW)


def test_wrong_scope_and_mutated_guard_rejected(setup):
    server, _, _ = setup
    value = capture(server)
    assert not guard.valid(server, value, scope=InventoryScope("bob", "league", "alice", "1qb_ppr", "request"), now=NOW)
    value["scope"]["user_id"] = "bob"
    assert not guard.valid(server, value, now=NOW)
    value = capture(server)
    value["expires_at"] = (NOW + timedelta(days=1)).isoformat()
    assert not guard.valid(server, value, now=NOW)


def test_read_guard_only_performs_selects_and_never_repairs_or_fetches(setup):
    server, engine, _ = setup
    statements = []
    event.listen(engine, "before_cursor_execute", lambda c, cursor, sql, *a: statements.append(sql))
    value = capture(server)
    assert guard.valid(server, value, now=NOW)
    assert statements and all(s.lstrip().upper().startswith("SELECT") for s in statements)


def card(value=None, **kw):
    attrs = dict(proposing_user_id="alice", league_id="league", expires_at=(NOW + timedelta(hours=1)).isoformat())
    if value is not None:
        attrs["_prepared_guard"] = value
    return SimpleNamespace(**dict(attrs, **kw))


def test_card_filter_preserves_order_ordinary_cards_and_rejects_foreign_expired(setup, monkeypatch):
    server, _, _ = setup
    value = capture(server)
    ordinary, first, second = card(), card(value), card(deepcopy(value))
    foreign = card(value, proposing_user_id="bob")
    expired = card(value, expires_at=NOW.isoformat())
    malformed = card(); malformed._prepared_guard = None
    assert guard.filter_cards(server, [ordinary, first, foreign, second, expired, malformed], now=NOW) == [ordinary, first, second]
    server._trade_service_mod._cfg["floor"] = .9
    assert guard.filter_cards(server, [ordinary, first, second], now=NOW) == [ordinary]


def test_shared_guard_checked_once_per_filter_but_not_cached_between_calls(setup, monkeypatch):
    server, _, _ = setup
    value = capture(server)
    calls, original = [], guard.valid
    def count(*a, **k):
        calls.append(1)
        return original(*a, **k)
    monkeypatch.setattr(guard, "valid", count)
    cards = [card(deepcopy(value)) for _ in range(30)]
    assert guard.filter_cards(server, cards, now=NOW) == cards
    assert len(calls) == 1
    assert guard.filter_cards(server, cards, now=NOW) == cards
    assert len(calls) == 2
