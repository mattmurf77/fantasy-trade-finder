"""Tests for POST /api/trades/validate (#180 — trade-send pre-flight).

Read-only advisory checks before a Sleeper send: league season closed,
traded players no longer on the expected rosters, post-trade roster counts
vs the league roster limit. The route never blocks — it reports findings and
`checked:false` when Sleeper data is unreachable. Sleeper HTTP is patched
(_fetch_sleeper_league_meta / _fetch_league_rosters) — no network.

#413: picks ride the same arrays as players. The pick ground truth
(`load_draft_picks` grid + `_fetch_sleeper_traded_picks` holder overlay) is
patched directly — this file never patches the DB engine, so the grid patch
is mandatory — and must not be reached by a pick-free trade (V-6).
"""
import json
from unittest.mock import MagicMock, patch

import pytest

import backend.server as server

USER = "313560442465169408"
OPP = "555000111222333444"

META = {
    "status": "in_season",
    # 6 lineup slots (incl. bench) + 1 IR + 1 taxi → max roster 8
    "roster_positions": ["QB", "RB", "WR", "TE", "FLEX", "BN"],
    "settings": {"reserve_slots": 1, "taxi_slots": 1},
}

ROSTERS = [
    {"roster_id": 1, "owner_id": USER,
     "players": ["100", "101", "102", "103", "104", "105"]},
    {"roster_id": 2, "owner_id": OPP,
     "players": ["200", "201", "202", "203", "204", "205"]},
]

LEAGUE = "987654321"
# #413 pick ground truth (lld-delta.md §7.2): my 2027 2nd (orig 1), roster 7's
# 2027 1st now held by me per traded_picks, their 2026 1st (orig 2).
GRID = [
    {"pick_id": f"{LEAGUE}_2027_2_1", "season": 2027, "round": 2, "original_roster_id": "1"},
    {"pick_id": f"{LEAGUE}_2027_1_7", "season": 2027, "round": 1, "original_roster_id": "7"},
    {"pick_id": f"{LEAGUE}_2026_1_2", "season": 2026, "round": 1, "original_roster_id": "2"},
]
TRADED = [{"season": "2027", "round": 1, "roster_id": 7, "owner_id": 1, "previous_owner_id": 7}]
MY_2027_2ND = f"{LEAGUE}_2027_2_1"
THEIR_2026_1ST = f"{LEAGUE}_2026_1_2"


def _h(token):
    return {"X-Session-Token": token, "Content-Type": "application/json"}


@pytest.fixture()
def client():
    token = "validate-sess-tok"
    sess = {"user_id": USER, "active_format": "1qb_ppr", "last_active": 0.0}
    server.app.config["TESTING"] = True
    c = server.app.test_client()
    with patch.object(server, "is_enabled",
                      lambda k: k == "trade.send_in_sleeper"), \
         patch.object(server, "get_sleeper_credential", lambda uid: None), \
         patch.object(server, "_fetch_sleeper_league_meta",
                      lambda lid: json.loads(json.dumps(META))), \
         patch.object(server, "_fetch_league_rosters",
                      lambda lid: json.loads(json.dumps(ROSTERS))), \
         patch.object(server, "load_draft_picks",
                      lambda lid, *a, **k: json.loads(json.dumps(GRID))), \
         patch.object(server, "_fetch_sleeper_traded_picks",
                      lambda lid: json.loads(json.dumps(TRADED))):
        with server._sessions_lock:
            server._sessions[token] = sess
        try:
            yield c, token
        finally:
            with server._sessions_lock:
                server._sessions.pop(token, None)


def _validate(c, token, **overrides):
    body = {"league_id": "987654321", "their_user_id": OPP,
            "give_player_ids": ["100"], "receive_player_ids": ["200"],
            **overrides}
    return c.post("/api/trades/validate", headers=_h(token),
                  data=json.dumps(body))


def _codes(resp):
    return [w["code"] for w in resp.get_json()["warnings"]]


def test_404_when_flag_off(client):
    c, token = client
    with patch.object(server, "is_enabled", lambda k: False):
        assert _validate(c, token).status_code == 404


def test_bad_request_400(client):
    c, token = client
    r = c.post("/api/trades/validate", headers=_h(token),
               data=json.dumps({"league_id": "not-numeric",
                                "their_user_id": OPP}))
    assert r.status_code == 400


def test_clean_trade_no_warnings(client):
    c, token = client
    r = _validate(c, token)
    assert r.status_code == 200, r.get_data(as_text=True)
    body = r.get_json()
    assert body["ok"] is True
    assert body["checked"] is True
    assert body["warnings"] == []


def test_unreachable_league_checked_false(client):
    c, token = client
    with patch.object(server, "_fetch_sleeper_league_meta", lambda lid: None):
        r = _validate(c, token)
    body = r.get_json()
    assert body["checked"] is False
    assert body["warnings"] == []


def test_archived_league_flagged(client):
    c, token = client
    meta = dict(META, status="complete")
    with patch.object(server, "_fetch_sleeper_league_meta", lambda lid: meta):
        r = _validate(c, token)
    assert "league_archived" in _codes(r)
    blocking = [w for w in r.get_json()["warnings"]
                if w["code"] == "league_archived"]
    assert blocking[0]["severity"] == "blocking"


def test_player_no_longer_on_roster_flagged(client):
    c, token = client
    # "999" was never on my roster; "201" is genuinely theirs
    r = _validate(c, token, give_player_ids=["999"], receive_player_ids=["201"])
    assert _codes(r) == ["player_moved"]
    # …and the receive side is checked against THEIR roster
    r2 = _validate(c, token, give_player_ids=["100"], receive_player_ids=["888"])
    assert _codes(r2) == ["player_moved"]


def test_roster_limit_overflow_warns(client):
    c, token = client
    # 2-for-1 my way: my roster 6 → 6 - 1 + 3 = 8 (at limit, OK), then 9 (over)
    ok = _validate(c, token, give_player_ids=["100"],
                   receive_player_ids=["200", "201", "202"])
    assert _codes(ok) == []
    over = _validate(c, token, give_player_ids=["100"],
                     receive_player_ids=["200", "201", "202", "203"])
    warns = over.get_json()["warnings"]
    assert [w["code"] for w in warns] == ["roster_limit"]
    assert warns[0]["severity"] == "warning"
    assert "9" in warns[0]["message"] and "8" in warns[0]["message"]


def test_counterparty_roster_limit_checked_too(client):
    c, token = client
    # 4-for-1 their way: their roster 6 → 6 - 1 + 4 = 9 > 8
    r = _validate(c, token,
                  give_player_ids=["100", "101", "102", "103"],
                  receive_player_ids=["200"])
    warns = r.get_json()["warnings"]
    assert [w["code"] for w in warns] == ["roster_limit"]
    assert warns[0]["message"].startswith("Their")


def test_their_roster_id_path(client):
    c, token = client
    r = _validate(c, token, their_user_id=None, their_roster_id=2)
    assert r.status_code == 200
    assert r.get_json()["warnings"] == []


def test_unknown_counterparty_flagged(client):
    c, token = client
    r = _validate(c, token, their_user_id="does-not-own-a-roster")
    assert _codes(r) == ["roster_not_found"]


# ── #413 — draft picks in the mixed arrays ────────────────────────────────

def test_owned_pick_not_flagged_as_player_moved(client):
    """V-1 — the #413 repro: my own pick on the give side is not a "moved
    player" (roster.players never holds a pick id)."""
    c, token = client
    r = _validate(c, token, give_player_ids=["100", MY_2027_2ND])
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()["warnings"] == []


def test_generic_pick_flags_asset_unmapped(client):
    """V-2 — a generic rung names no real pick: blocking asset_unmapped, with
    the count in the copy."""
    c, token = client
    r = _validate(c, token, give_player_ids=["generic_pick_1_early"])
    assert _codes(r) == ["asset_unmapped"]
    w = r.get_json()["warnings"][0]
    assert w["severity"] == "blocking"
    assert "1 draft pick " in w["message"]


def test_pick_owned_by_other_roster_flags_pick_moved(client):
    """V-3 — live traded_picks says my 2027 2nd is held by roster 9 now:
    blocking pick_moved."""
    c, token = client
    traded = [{"season": "2027", "round": 2, "roster_id": 1, "owner_id": 9,
               "previous_owner_id": 1}]
    with patch.object(server, "_fetch_sleeper_traded_picks", lambda lid: traded):
        r = _validate(c, token, give_player_ids=[MY_2027_2ND])
    assert _codes(r) == ["pick_moved"]
    assert r.get_json()["warnings"][0]["severity"] == "blocking"


def test_receive_side_pick_checks_their_roster(client):
    """V-4 — the receive side is judged against THEIR roster: their own 2026
    1st is clean; my 2027 2nd on the receive side is not theirs to give."""
    c, token = client
    r = _validate(c, token, receive_player_ids=[THEIR_2026_1ST])
    assert _codes(r) == []
    r2 = _validate(c, token, receive_player_ids=[MY_2027_2ND])
    assert _codes(r2) == ["pick_moved"]


def test_roster_limit_excludes_picks(client):
    """V-5 — picks are not roster slots: 6 - 1 + 3 players = 8 (at the
    limit) stays clean with a pick riding along."""
    c, token = client
    r = _validate(c, token, give_player_ids=["100"],
                  receive_player_ids=["200", "201", "202", THEIR_2026_1ST])
    assert _codes(r) == []


def test_pick_free_validate_makes_no_pick_fetch(client):
    """V-6 — a pick-free trade reaches neither the grid nor traded_picks."""
    c, token = client
    grid_mock, traded_mock = MagicMock(return_value=GRID), MagicMock(return_value=TRADED)
    with patch.object(server, "load_draft_picks", grid_mock), \
         patch.object(server, "_fetch_sleeper_traded_picks", traded_mock):
        r = _validate(c, token)
    assert r.get_json()["warnings"] == []
    grid_mock.assert_not_called()
    traded_mock.assert_not_called()
