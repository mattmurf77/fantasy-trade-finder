"""FB-147 — Sleeper trade-block import + card tagging.

Covers the four contract points:
  1. fetch/parse: GraphQL `league_players` payload + v1 rosters → validated
     entries (stale flags dropped, pick pseudo-ids skipped, epoch-ms →
     ISO timestamps, ownerless rosters ignored).
  2. storage round-trip: replace_trade_block / load_trade_block snapshot
     semantics (re-sync replaces; empty snapshot clears).
  3. serializer: trade_card_to_dict stamps `on_block: true` only on
     involved players the block names — omit-when-absent.
  4. flag-off / absent-data parity: with the flag off (or no synced data)
     the card payload is byte-identical to the pre-147 shape.

No network: the GraphQL + REST fetches are exercised through the injected
`_opener` (same pattern as sleeper_write / espn_service tests).
"""
import io
import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine

import backend.database as db_module
import backend.server as server
from backend.database import metadata, replace_trade_block, load_trade_block
from backend.trade_block_service import (
    fetch_league_players,
    parse_trade_block,
    sync_league_trade_block,
)

LEAGUE = "1312076055586050048"

# Trimmed from the 2026-07-17 live probe of the operator's league — real
# shapes, minus ~540 unflagged rows.
GRAPHQL_FIXTURE = {
    "data": {
        "league_players": [
            # valid: roster 7 flagged a player it still owns (ms timestamp)
            {"player_id": "4943", "settings": {"otb": 7, "otb_added_at": 1777754069841}},
            # valid: roster 2, no otb_added_at (legacy-league shape)
            {"player_id": "6794", "settings": {"otb": 2}},
            # stale: roster 7 flagged 5045, but roster 10 owns it now
            {"player_id": "5045", "settings": {"otb": 7, "otb_added_at": 1777219949227}},
            # pick pseudo-id — skipped in v1 of the import
            {"player_id": "7,2026,1", "settings": {"otb": 7, "otb_added_at": 1777838549089}},
            # flagging roster has no owner (orphaned team) — dropped
            {"player_id": "8148", "settings": {"otb": 5}},
            # unflagged rows: settings null / other keys only
            {"player_id": "10236", "settings": None},
            {"player_id": "11584", "settings": {"waiver_clears_at": 1757630329}},
        ]
    }
}

ROSTERS_FIXTURE = [
    {"roster_id": 7,  "owner_id": "852254555294019584", "players": ["4943", "7553"]},
    {"roster_id": 2,  "owner_id": "313560442465169408", "players": ["6794", "8148"]},
    {"roster_id": 10, "owner_id": "974112322165735424", "players": ["5045"]},
    {"roster_id": 5,  "owner_id": None,                 "players": ["8148"]},
]


# ---------------------------------------------------------------------------
# 1. fetch + parse
# ---------------------------------------------------------------------------

class _FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def _fake_opener(request, timeout=None):
    url = getattr(request, "full_url", str(request))
    if "graphql" in url:
        assert request.get_header("X-sleeper-graphql-op") == "league_players"
        return _FakeResponse(json.dumps(GRAPHQL_FIXTURE).encode())
    if url.endswith("/rosters"):
        return _FakeResponse(json.dumps(ROSTERS_FIXTURE).encode())
    raise AssertionError(f"unexpected URL fetched: {url}")


def test_fetch_league_players_parses_graphql_rows():
    rows = fetch_league_players(LEAGUE, _opener=_fake_opener)
    assert len(rows) == 7
    assert rows[0] == {"player_id": "4943",
                       "settings": {"otb": 7, "otb_added_at": 1777754069841}}


def test_fetch_raises_on_graphql_errors():
    payload = {"errors": [{"message": "Cannot query field"}]}

    def opener(request, timeout=None):
        return _FakeResponse(json.dumps(payload).encode())

    with pytest.raises(RuntimeError):
        fetch_league_players(LEAGUE, _opener=opener)


def test_parse_validates_ownership_and_skips_picks():
    entries = parse_trade_block(
        GRAPHQL_FIXTURE["data"]["league_players"], ROSTERS_FIXTURE
    )
    by_pid = {e["player_id"]: e for e in entries}
    # Only the two owned-and-flagged players survive.
    assert set(by_pid) == {"4943", "6794"}
    assert by_pid["4943"]["user_id"] == "852254555294019584"
    assert by_pid["4943"]["roster_id"] == 7
    # 1777754069841 ms → 2026-05-02T07:14:29.841000+00:00 (UTC ISO)
    assert by_pid["4943"]["flagged_at"].startswith("2026-05-02T")
    assert by_pid["4943"]["flagged_at"].endswith("+00:00")
    # Legacy league: no otb_added_at → NULL flagged_at, row still kept.
    assert by_pid["6794"]["flagged_at"] is None


def test_parse_empty_inputs():
    assert parse_trade_block([], []) == []
    assert parse_trade_block(None, None) == []


# ---------------------------------------------------------------------------
# 2. storage round-trip (isolated in-memory DB)
# ---------------------------------------------------------------------------

@pytest.fixture()
def mem_db():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    metadata.create_all(engine)
    with patch.object(db_module, "engine", engine):
        yield engine


def test_storage_round_trip_and_resync_replaces(mem_db):
    replace_trade_block(LEAGUE, [
        {"player_id": "4943", "user_id": "u7", "roster_id": 7,
         "flagged_at": "2026-05-02T07:14:29+00:00"},
        {"player_id": "6794", "user_id": "u2", "roster_id": 2, "flagged_at": None},
    ])
    rows = load_trade_block(LEAGUE)
    assert {r["player_id"] for r in rows} == {"4943", "6794"}
    assert all(r["synced_at"] for r in rows)

    # Re-sync with a smaller snapshot → old rows gone (replace, not merge).
    replace_trade_block(LEAGUE, [
        {"player_id": "7553", "user_id": "u7", "roster_id": 7, "flagged_at": None},
    ])
    assert {r["player_id"] for r in load_trade_block(LEAGUE)} == {"7553"}

    # Empty snapshot is valid — clears the league.
    replace_trade_block(LEAGUE, [])
    assert load_trade_block(LEAGUE) == []

    # Other leagues are untouched by a replace.
    replace_trade_block("999", [
        {"player_id": "1", "user_id": "x", "roster_id": 1, "flagged_at": None},
    ])
    replace_trade_block(LEAGUE, [])
    assert len(load_trade_block("999")) == 1


def test_sync_league_trade_block_end_to_end(mem_db):
    n = sync_league_trade_block(LEAGUE, _opener=_fake_opener)
    assert n == 2
    assert {r["player_id"] for r in load_trade_block(LEAGUE)} == {"4943", "6794"}


def test_sync_noop_for_non_sleeper_league_ids(mem_db):
    def exploding_opener(request, timeout=None):  # pragma: no cover
        raise AssertionError("must not fetch for non-Sleeper league ids")

    assert sync_league_trade_block("espn_12345", _opener=exploding_opener) == 0
    assert sync_league_trade_block("league_demo", _opener=exploding_opener) == 0
    assert sync_league_trade_block("", _opener=exploding_opener) == 0


# ---------------------------------------------------------------------------
# 3 + 4. serializer tag / omit-when-absent / flag-off parity
# ---------------------------------------------------------------------------

def _player(pid, name):
    return SimpleNamespace(id=pid, name=name, position="RB", team="SF",
                           age=25, years_experience=3)


def _card():
    return SimpleNamespace(
        trade_id="t1", league_id=LEAGUE,
        target_user_id="opp", target_username="opponent",
        give_player_ids=["4943"], receive_player_ids=["5045"],
        mismatch_score=120.0, fairness_score=0.9, composite_score=0.5,
        basis="divergence", decision=None, expires_at=None,
    )


PLAYERS = {"4943": _player("4943", "A"), "5045": _player("5045", "B")}


@pytest.fixture(autouse=True)
def _clear_block_cache():
    with server._trade_block_cache_lock:
        server._trade_block_cache.clear()
    yield
    with server._trade_block_cache_lock:
        server._trade_block_cache.clear()


def test_serializer_tags_only_blocked_players():
    with patch.object(server, "is_enabled", lambda k: k == "sleeper.trade_block"), \
         patch.object(server, "load_trade_block",
                      lambda lid: [{"player_id": "5045"}] if lid == LEAGUE else []):
        out = server.trade_card_to_dict(_card(), PLAYERS)
    assert out["receive"][0]["on_block"] is True
    assert "on_block" not in out["give"][0]  # omit-when-absent, not False


def test_serializer_flag_off_and_no_data_parity():
    # Flag ON but league has no synced block data → identical payload.
    with patch.object(server, "is_enabled", lambda k: k == "sleeper.trade_block"), \
         patch.object(server, "load_trade_block", lambda lid: []):
        with_flag_no_data = server.trade_card_to_dict(_card(), PLAYERS)

    server._trade_block_cache.clear()

    # Flag OFF with data present → identical payload (and no DB read).
    def exploding_load(lid):  # pragma: no cover
        raise AssertionError("flag off must not read trade_block")

    with patch.object(server, "is_enabled", lambda k: False), \
         patch.object(server, "load_trade_block", exploding_load):
        flag_off = server.trade_card_to_dict(_card(), PLAYERS)

    assert with_flag_no_data == flag_off
    assert not any("on_block" in row
                   for row in flag_off["give"] + flag_off["receive"])


def test_serializer_cache_ttl_and_invalidation():
    calls = []

    def counting_load(lid):
        calls.append(lid)
        return [{"player_id": "4943"}]

    with patch.object(server, "is_enabled", lambda k: k == "sleeper.trade_block"), \
         patch.object(server, "load_trade_block", counting_load):
        server.trade_card_to_dict(_card(), PLAYERS)
        server.trade_card_to_dict(_card(), PLAYERS)
        assert len(calls) == 1  # second serve hits the TTL cache
        server._invalidate_trade_block_cache(LEAGUE)
        out = server.trade_card_to_dict(_card(), PLAYERS)
        assert len(calls) == 2  # post-sync invalidation forces a re-read
    assert out["give"][0]["on_block"] is True
