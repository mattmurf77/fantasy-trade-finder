"""POST /api/session/init — Sleeper upstream call budget for the background
daemon.

The daemon re-fetched the SAME two public payloads once per consumer: the v1
rosters list was read by the trade-block sync, the owned-pick sync and the
executed-trade matcher's roster map, and `/league/<id>` was read by the
scoring auto-detect AND again by the owned-pick sync. Both are immutable for
the length of one init, so the daemon now fetches each at most once and hands
the payload to every consumer.

What this pins:
  • exactly ONE `/league/<id>/rosters` read per init for a Sleeper league
  • exactly ONE `/league/<id>` (league meta) read per init
  • `_sync_sleeper_owned_picks(rosters=…, meta=…)` makes neither call itself
  • non-Sleeper league ids still make ZERO Sleeper calls

Out of scope on purpose: `_refresh_league_draft_status` is stubbed here. It
carries its own asymmetric TTL cheap-skip (12 h once a league reads
`drafted`), so in production it makes no upstream call on the overwhelming
majority of inits; threading payloads through it would buy a first-init-only
saving for a wider change. See `_DRAFT_STATUS_TTL_SECONDS`.

Harness: test_market_data_readiness.py's isolated in-memory SQLite plus
test_co_owner_rosters.py's inline-daemon Thread subclass.
"""

import json
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine

import backend.database as db_module
import backend.server as server
import backend.sleeper_trades_service as trades_service
import backend.suggestion_telemetry as sugg_tel
import backend.trade_block_service as tb_service
from backend.database import metadata, record_sleeper_trades

LEAGUE_ID = "1338231586314780672"
NON_SLEEPER_LEAGUE = "demo_league"
USER_ID = "460238423161040896"
OPP_ID = "733459678624915456"

LEAGUE_META = {
    "league_id": LEAGUE_ID,
    "season": "2026",
    "total_rosters": 2,
    "roster_positions": ["QB", "RB", "WR", "TE", "FLEX", "BN"],
    "scoring_settings": {"rec": 1.0},
    "settings": {"draft_rounds": 3},
}
ROSTERS = [
    {"roster_id": 1, "owner_id": USER_ID, "co_owners": None,
     "players": ["p1"], "starters": ["p1"]},
    {"roster_id": 2, "owner_id": OPP_ID, "co_owners": None,
     "players": ["p2"], "starters": ["p2"]},
]
# One captured trade so the executed-trade matcher has real work to do —
# otherwise it returns before ever needing a roster map and the "no fourth
# rosters fetch" assertion would pass for the wrong reason.
CAPTURED_TRADE = {
    "transaction_id": "9998887776665554443",
    "league_id": LEAGUE_ID,
    "week": 1,
    "traded_at": "2026-09-15T00:00:00+00:00",
    "synced_at": "2026-09-15T00:00:00+00:00",
    "roster_ids": json.dumps([1, 2]),
    "adds": json.dumps({"p1": 2, "p2": 1}),
    "drops": json.dumps({"p1": 1, "p2": 2}),
    "draft_picks": json.dumps([]),
    "waiver_budget": json.dumps([]),
    "raw": json.dumps({"type": "trade", "status": "complete"}),
}


class _Counter(dict):
    """Per-endpoint upstream call tally."""

    def bump(self, key):
        self[key] = self.get(key, 0) + 1


@pytest.fixture()
def harness(monkeypatch):
    """session_init with an inline daemon and every Sleeper egress counted."""
    from backend.ranking_service import Player

    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False})
    metadata.create_all(engine)
    monkeypatch.setattr(db_module, "engine", engine)

    calls = _Counter()

    def _fake_sleeper_get(url, timeout=15):
        tail = url.split("/v1/league/")[-1]
        if tail == LEAGUE_ID:
            calls.bump("meta")
            return dict(LEAGUE_META)
        if tail == f"{LEAGUE_ID}/rosters":
            calls.bump("rosters")
            return [dict(r) for r in ROSTERS]
        if tail == f"{LEAGUE_ID}/traded_picks":
            calls.bump("traded_picks")
            return []
        if tail == f"{LEAGUE_ID}/drafts":
            calls.bump("drafts")
            return []
        raise AssertionError(f"unexpected Sleeper GET {url}")

    monkeypatch.setattr(server, "_sleeper_get", _fake_sleeper_get)

    # The three modules that bypass `_sleeper_get` and drive urllib directly.
    def _fake_tb_rosters(league_id, *, _opener=None, timeout=15):
        calls.bump("rosters")
        return [dict(r) for r in ROSTERS]

    monkeypatch.setattr(tb_service, "_fetch_rosters", _fake_tb_rosters)
    monkeypatch.setattr(tb_service, "fetch_league_players",
                        lambda league_id, *, _opener=None, timeout=15: [])
    monkeypatch.setattr(trades_service, "fetch_week_transactions",
                        lambda lid, week, *, _opener=None, timeout=15:
                        (calls.bump("transactions"), [])[1])

    def _fake_roster_map(league_id, *, _opener=None, timeout=15):
        calls.bump("rosters")
        return {str(r["roster_id"]): str(r["owner_id"]) for r in ROSTERS}

    monkeypatch.setattr(sugg_tel, "fetch_league_roster_map", _fake_roster_map)

    # TTL-gated in production (see module docstring) — held constant here.
    monkeypatch.setattr(server, "_refresh_league_draft_status",
                        lambda league_id, force=False: None)

    pool = [Player(f"p{i}", f"P{i}", "RB", "AAA", 25, 1) for i in (1, 2)]
    seed = {p.id: 1500.0 for p in pool}
    fake_pools = {"1qb_ppr": {"players": pool, "seed": seed},
                  "sf_tep":  {"players": pool, "seed": seed}}
    monkeypatch.setattr(server, "_load_sleeper_cache", lambda: {})
    monkeypatch.setattr(server, "_ensure_universal_pools", lambda: None)
    monkeypatch.setattr(server, "g_universal_by_format", fake_pools)
    monkeypatch.setattr(server, "g_universal_players", pool)
    monkeypatch.setattr(server, "_kickoff_trade_job", MagicMock())

    real_thread = server.threading.Thread

    class _InlineBgThread(real_thread):
        """Run the bg-writes daemon synchronously; leave pool workers alone."""

        def start(self):
            if self.name == "session-init-bg-writes":
                self.run()
                return
            super().start()

    monkeypatch.setattr(server.threading, "Thread", _InlineBgThread)

    server.app.config["TESTING"] = True
    return server.app.test_client(), calls


def _init(client, league_id):
    return client.post(
        "/api/session/init",
        content_type="application/json",
        data=json.dumps({
            "user_id": USER_ID,
            "league_id": league_id,
            "league_name": "Bush League",
            "user_player_ids": ["p1"],
            "opponent_rosters": [{"user_id": OPP_ID, "username": "Opp",
                                  "player_ids": ["p2"]}],
        }),
    )


# ---------------------------------------------------------------------------
# The budget
# ---------------------------------------------------------------------------

def test_daemon_makes_one_rosters_and_one_meta_call(harness):
    client, calls = harness
    record_sleeper_trades([dict(CAPTURED_TRADE)])

    assert _init(client, LEAGUE_ID).status_code == 200

    # Was 3 rosters reads (trade block, owned picks, matcher roster map) and
    # 2 league-meta reads (scoring auto-detect, owned picks).
    assert calls.get("rosters") == 1, calls
    assert calls.get("meta") == 1, calls
    # The rest of the daemon's Sleeper budget, pinned so a regression here is
    # visible: one traded-picks + one drafts read for the owned-pick sync.
    assert calls.get("traded_picks") == 1, calls
    assert calls.get("drafts") == 1, calls
    # The league already has a captured trade, so the sweep is incremental —
    # never the 18-leg backfill.
    assert calls.get("transactions", 0) <= 2, calls


def test_non_sleeper_league_makes_no_sleeper_calls(harness):
    client, calls = harness
    assert _init(client, NON_SLEEPER_LEAGUE).status_code == 200
    assert calls == {}, calls


# ---------------------------------------------------------------------------
# The seam itself
# ---------------------------------------------------------------------------

def test_owned_pick_sync_with_supplied_payloads_refetches_neither(harness):
    _client, calls = harness

    server._sync_sleeper_owned_picks(
        LEAGUE_ID, {USER_ID: "Me", OPP_ID: "Opp"}, "1qb_ppr",
        rosters=[dict(r) for r in ROSTERS], meta=dict(LEAGUE_META),
    )

    assert "rosters" not in calls, calls
    assert "meta" not in calls, calls
    assert calls.get("traded_picks") == 1, calls   # still its own two reads
    assert calls.get("drafts") == 1, calls


def test_owned_pick_sync_without_payloads_still_self_fetches(harness):
    _client, calls = harness

    server._sync_sleeper_owned_picks(
        LEAGUE_ID, {USER_ID: "Me", OPP_ID: "Opp"}, "1qb_ppr")

    assert calls.get("rosters") == 1, calls
    assert calls.get("meta") == 1, calls
