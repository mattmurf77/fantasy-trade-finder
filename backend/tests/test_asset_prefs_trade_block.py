"""Roster-first setup (D-212) — `trade_block` asset-pref persistence.

docs/plans/roster-first-trade-setup/ (scope §3, prd §4.2, AC-0). Pins:
  1. `trade_block` round-trips through POST/GET /api/league/asset-prefs.
  2. PERSISTENCE IS NOT GATED: the route accepts and returns `trade_block`
     with `trades.roster_setup` OFF as well as ON (the #360 kill-switch rule).
  3. Single membership spans all four list types: Move (trade_block) <->
     Keep (untouchable) <-> none needs no client reconciliation.
  4. The bulk loader returns a `trade_block` key in the same per-user shape
     as the single loader.
  5. The existing server event carries `list_type='trade_block'`.

Harness: test_fair_packages (Flask test client, in-memory session, isolated
in-memory SQLite, `record_event` mocked).
"""

import pytest

import backend.database as db
import backend.feature_flags as ff
from backend.tests.test_fair_packages import harness, LEAGUE, ME, OPP, TOKEN  # noqa: F401

HDR = {"X-Session-Token": TOKEN}


def _flag(on):
    ff._flags_cache = {**ff._flags_cache, "trades.roster_setup": on}


def _post(client, player_id, list_type):
    return client.post("/api/league/asset-prefs", headers=HDR,
                       json={"league_id": LEAGUE, "player_id": player_id, "list": list_type})


def _get(client):
    res = client.get(f"/api/league/asset-prefs?league_id={LEAGUE}", headers=HDR)
    assert res.status_code == 200
    return res.get_json()


@pytest.mark.parametrize("flag_on", [False, True])
def test_trade_block_round_trips_in_both_flag_states(harness, flag_on):
    client, *_ = harness
    _flag(flag_on)
    assert "trade_block" in db.ASSET_PREF_LISTS

    res = _post(client, "a1", "trade_block")
    assert res.status_code == 200
    body = res.get_json()
    assert body["ok"] is True and body["trade_block"] == ["a1"]

    assert _get(client) == {"untouchables": [], "targets": [], "not_interested": [],
                            "trade_block": ["a1"]}

    assert _post(client, "a1", "none").get_json()["trade_block"] == []
    assert _get(client)["trade_block"] == []


def test_single_membership_spans_trade_block_and_untouchable(harness):
    client, *_ = harness
    _flag(False)
    _post(client, "a1", "trade_block")
    after_keep = _post(client, "a1", "untouchable").get_json()
    assert after_keep["untouchables"] == ["a1"] and after_keep["trade_block"] == []

    after_move = _post(client, "a1", "trade_block").get_json()
    assert after_move["trade_block"] == ["a1"] and after_move["untouchables"] == []

    # A stale target tag on one of your own players is replaced, not doubled.
    _post(client, "a2", "target")
    replaced = _post(client, "a2", "trade_block").get_json()
    assert replaced["targets"] == [] and set(replaced["trade_block"]) == {"a1", "a2"}

    _, engine, *_ = harness
    with engine.connect() as conn:
        rows = conn.execute(db.asset_preferences_table.select()).fetchall()
    assert sorted((r.player_id, r.list_type) for r in rows) == [
        ("a1", "trade_block"), ("a2", "trade_block")]


def test_unknown_list_still_rejected_and_names_trade_block(harness):
    client, *_ = harness
    res = _post(client, "a1", "bogus")
    assert res.status_code == 400
    assert "trade_block" in res.get_json()["error"]


def test_bulk_loader_returns_trade_block_key(harness):
    _flag(False)
    db.set_asset_preference(ME, LEAGUE, "a1", "trade_block")
    db.set_asset_preference(ME, LEAGUE, "a2", "untouchable")
    db.set_asset_preference(OPP, LEAGUE, "b1", "untouchable")

    bulk = db.load_asset_preferences_bulk([ME, OPP, "nobody"], LEAGUE)
    assert bulk[ME] == {"untouchables": ["a2"], "targets": [], "not_interested": [],
                        "trade_block": ["a1"]}
    # A user with no trade_block rows still gets the key (same shape as the
    # single loader), and absent users stay absent.
    assert bulk[OPP]["trade_block"] == [] and "nobody" not in bulk
    assert bulk[ME] == db.load_asset_preferences(ME, LEAGUE)


def test_server_event_carries_trade_block_list_type(harness):
    import backend.server as server
    client, *_ = harness
    _post(client, "a1", "trade_block")
    calls = [c for c in server.record_event.call_args_list
             if c.args[1:2] == ("asset_pref_added",)]
    assert calls and calls[-1].kwargs["props"] == {"player_id": "a1", "list_type": "trade_block"}
