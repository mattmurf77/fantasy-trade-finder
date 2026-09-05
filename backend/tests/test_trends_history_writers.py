"""#164 — Trends screen empty despite rankings.

Root cause: elo_history (the data source for /api/trends/risers-fallers)
was written ONLY by the trio-swipe route (/api/rank3). Users who built
their board exclusively through Quick Set (/api/tiers/save), Quick Rank /
manual reorder (/api/rankings/reorder), or Pick Anchor (/api/anchor/save)
never populated it, so Trends showed the "Keep ranking to see trends here"
empty state forever.

These tests pin the fix: each of the three non-trio ranking writers appends
elo_history rows for the players it changed, and the trends route then
reports history for a Quick-Set-only user.

Harness pattern follows test_analytics_p0.py: isolated SQLite engine
patched into backend.database, Flask test client, flags forced off.
"""
import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, select

import backend.database as db_module
import backend.server as server
from backend.database import metadata, elo_history_table

USER = "user_trends_writers"
TOKEN = "trends-writers-token"
LEAGUE = "L_trends"


class _FakeService:
    """Minimal RankingService stand-in: a mutable {pid: (elo, position)}
    map behind the few methods the tiers/anchor/reorder routes touch."""

    def __init__(self, elos):
        self._elos = dict(elos)
        self._elo_overrides = {}

    def apply_tiers(self, **kw):
        pass

    def apply_reorder(self, **kw):
        pass

    def apply_anchor(self, player_id, target_elo):
        if player_id not in self._elos:
            return None
        _, pos = self._elos[player_id]
        self._elos[player_id] = (float(target_elo), pos)
        return SimpleNamespace(id=player_id, position=pos)

    def tier_for_elo(self, elo, position, fmt):
        return "first_1"

    def get_rankings(self, position=None):
        rankings = [
            SimpleNamespace(
                player=SimpleNamespace(id=pid, name=pid, position=pos, team=None),
                elo=elo,
            )
            for pid, (elo, pos) in self._elos.items()
        ]
        return SimpleNamespace(rankings=rankings)

    def comparison_counts(self):
        return {}


class _FalseFlags:
    def __getattr__(self, name):
        return False

    def __getitem__(self, key):
        return False


@pytest.fixture()
def harness(tmp_path):
    path = tmp_path / "trends.db"
    eng = create_engine(f"sqlite:///{path}",
                        connect_args={"check_same_thread": False})
    metadata.create_all(eng)
    with patch.object(db_module, "engine", eng), \
         patch.object(db_module, "DATABASE_URL", "sqlite:///trends"):
        svc = _FakeService({
            "p1": (1600.0, "RB"),
            "p2": (1500.0, "RB"),
            "p3": (1400.0, "WR"),
        })
        players = [
            SimpleNamespace(id=pid, name=pid, position=pos, team=None)
            for pid, (elo, pos) in svc._elos.items()
        ]
        sess = {"verified": True,
            "user_id": USER,
            "league": SimpleNamespace(league_id=LEAGUE, members=[]),
            "players": players,
            "user_roster": ["p1"],
            "service": svc,
            "trade_svc": SimpleNamespace(),
            "last_active": 0.0,
        }
        server.app.config["TESTING"] = True
        client = server.app.test_client()
        with patch.object(server, "is_enabled", lambda k: False), \
             patch.object(server, "FLAGS", _FalseFlags()):
            with server._sessions_lock:
                server._sessions[TOKEN] = sess
            try:
                yield client, eng, svc
            finally:
                with server._sessions_lock:
                    server._sessions.pop(TOKEN, None)


def _history_rows(eng):
    with eng.connect() as conn:
        rows = conn.execute(
            select(elo_history_table).order_by(elo_history_table.c.id)
        ).fetchall()
    return [dict(r._mapping) for r in rows]


def _post(client, url, body):
    return client.post(
        url,
        headers={"X-Session-Token": TOKEN, "Content-Type": "application/json"},
        data=json.dumps(body),
    )


def test_tiers_save_writes_elo_history(harness):
    client, eng, _ = harness
    r = _post(client, "/api/tiers/save",
              {"position": "RB", "tiers": {"first_1": ["p1", "p2"]}})
    assert r.status_code == 200
    rows = _history_rows(eng)
    assert {row["player_id"] for row in rows} == {"p1", "p2"}
    for row in rows:
        assert row["user_id"] == USER
        assert row["league_id"] == LEAGUE
        assert row["scoring_format"] == "1qb_ppr"


def test_tiers_save_records_cleared_pids(harness):
    client, eng, _ = harness
    # p3 removed from all tiers — its ELO reverted, so it belongs in history.
    r = _post(client, "/api/tiers/save",
              {"position": "RB", "tiers": {"first_1": ["p1"]},
               "cleared_pids": ["p3"]})
    assert r.status_code == 200
    assert {row["player_id"] for row in _history_rows(eng)} == {"p1", "p3"}


def test_reorder_writes_elo_history(harness):
    client, eng, _ = harness
    r = _post(client, "/api/rankings/reorder",
              {"position": "RB", "ordered_ids": ["p2", "p1"]})
    assert r.status_code == 200
    assert {row["player_id"] for row in _history_rows(eng)} == {"p1", "p2"}


def test_anchor_save_writes_elo_history(harness):
    client, eng, svc = harness
    r = _post(client, "/api/anchor/save",
              {"player_id": "p1", "anchor": "2_firsts"})
    assert r.status_code == 200
    rows = _history_rows(eng)
    assert [row["player_id"] for row in rows] == ["p1"]
    # The snapshot carries the post-anchor ELO, not the stale one.
    assert rows[0]["elo"] == pytest.approx(svc._elos["p1"][0])


def test_trends_populates_for_quickset_only_user(harness):
    """End-to-end regression for the tester report: a user who only ever
    saved tiers (never trio-swiped) must see has_history + risers."""
    client, eng, svc = harness
    r = _post(client, "/api/tiers/save",
              {"position": "RB", "tiers": {"first_1": ["p1", "p2"]},
               "via": "quickset"})
    assert r.status_code == 200

    # The user's board moves later (any flow) — p1 rises.
    svc._elos["p1"] = (1700.0, "RB")

    r = client.get("/api/trends/risers-fallers?window_days=30&top_n=5",
                   headers={"X-Session-Token": TOKEN})
    assert r.status_code == 200
    data = r.get_json()
    assert data["has_history"] is True
    riser_ids = [row["player_id"] for row in data["risers"]["ALL"]]
    assert "p1" in riser_ids


def test_snapshot_failure_never_blocks_save(harness):
    client, eng, _ = harness
    with patch.object(server, "record_elo_snapshot",
                      side_effect=RuntimeError("db down")):
        r = _post(client, "/api/tiers/save",
                  {"position": "RB", "tiers": {"first_1": ["p1"]}})
    assert r.status_code == 200
    assert _history_rows(eng) == []
