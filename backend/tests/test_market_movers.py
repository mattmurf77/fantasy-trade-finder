"""GET /api/market/movers (#243 — League-home "Market pulse" strip).

Top risers/fallers by trailing-window % change of FTF community value
(player_value_history consensus_value snapshots, daily cron #57). Covers:

  1. Flag gating — `market.movers` off ⇒ 404, on ⇒ 200.
  2. Route shape — risers desc / fallers asc by pct_30d, row keys
     {player_id, name, position, team, pct_30d, value_now}, `as_of` +
     `window_days` + `source: "ftf_community_value"` envelope.
  3. Noise guards — junk-value baselines, flat movers, players missing
     from the universal pool, and single-day players are all excluded.
  4. Cap — never more than 10 per direction regardless of top_n.
  5. Thin history — zero or one accrued snapshot day ⇒ 200 with empty
     lists (empty-safe), never an error.

Harness: test_market_data_readiness.py's isolated in-memory SQLite +
patched server universal pools.
"""

import types
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine

import backend.database as db_module
import backend.feature_flags as ff
import backend.server as server
from backend.database import metadata, record_value_snapshots

FMT = "1qb_ppr"
TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")
BASE_DAY = (datetime.now(timezone.utc) - timedelta(days=20)).strftime("%Y-%m-%d")


def _snap(pid: str, day: str, value: float) -> dict:
    return {
        "player_id": pid, "scoring_format": FMT, "consensus_elo": 1500.0,
        "consensus_value": value, "search_rank": None, "adp": None,
        "snapshot_date": day,
    }


def _player(pid: str, name: str, pos: str = "RB", team: str = "FA"):
    return types.SimpleNamespace(id=pid, name=name, position=pos, team=team)


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------

@pytest.fixture()
def client():
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False})
    metadata.create_all(engine)

    server.app.config["TESTING"] = True
    c = server.app.test_client()

    saved_flags = ff._flags_cache
    ff._flags_cache = {**ff.DEFAULT_FLAGS, "market.movers": True}
    try:
        with patch.object(db_module, "engine", engine):
            yield c, engine
    finally:
        ff._flags_cache = saved_flags


def _pool(players):
    pools = {FMT: {"players": list(players), "seed": {}}}
    return (patch.object(server, "_ensure_universal_pools", lambda: None),
            patch.object(server, "g_universal_by_format", pools))


# ---------------------------------------------------------------------------
# Flag gating
# ---------------------------------------------------------------------------

def test_flag_off_404(client):
    c, _ = client
    ff._flags_cache = dict(ff.DEFAULT_FLAGS)          # market.movers off
    r = c.get("/api/market/movers")
    assert r.status_code == 404


def test_flag_on_200_even_with_no_history(client):
    c, _ = client
    p1, p2 = _pool([])
    with p1, p2:
        r = c.get("/api/market/movers")
    assert r.status_code == 200
    body = r.get_json()
    assert body["risers"] == [] and body["fallers"] == []
    assert body["as_of"] is None
    assert body["source"] == "ftf_community_value"


# ---------------------------------------------------------------------------
# Route shape
# ---------------------------------------------------------------------------

def test_shape_ordering_and_noise_guards(client):
    c, _ = client
    record_value_snapshots([
        # Risers: +21% and +12%.
        _snap("p_up",   BASE_DAY, 1000.0), _snap("p_up",   TODAY, 1210.0),
        _snap("p_up2",  BASE_DAY, 2000.0), _snap("p_up2",  TODAY, 2240.0),
        # Fallers: −14% and −7% (fallers sort most-negative first).
        _snap("p_dn",   BASE_DAY, 1000.0), _snap("p_dn",   TODAY,  860.0),
        _snap("p_dn2",  BASE_DAY, 2000.0), _snap("p_dn2",  TODAY, 1860.0),
        # Flat — no move, excluded from both lists.
        _snap("p_flat", BASE_DAY, 1500.0), _snap("p_flat", TODAY, 1500.0),
        # Junk-value baseline (< the 100-point floor) — +60% of nothing is
        # noise, excluded.
        _snap("p_junk", BASE_DAY,   50.0), _snap("p_junk", TODAY,   80.0),
        # Not in the universal pool (retired/unknown) — excluded.
        _snap("p_gone", BASE_DAY, 1000.0), _snap("p_gone", TODAY, 1400.0),
        # Only today's snapshot (no baseline) — excluded, never a fake 0%.
        _snap("p_new",  TODAY, 3000.0),
    ])
    pool = [
        _player("p_up",   "Ashton Jeanty", "RB", "LV"),
        _player("p_up2",  "Tyler Warren",  "TE", "IND"),
        _player("p_dn",   "Christian McCaffrey", "RB", "SF"),
        _player("p_dn2",  "Sam LaPorta",   "TE", "DET"),
        _player("p_flat", "Flat Guy"),
        _player("p_junk", "Junk Stash"),
        _player("p_new",  "New Snapshot"),
    ]
    p1, p2 = _pool(pool)
    with p1, p2:
        r = c.get("/api/market/movers")
    assert r.status_code == 200
    body = r.get_json()

    assert body["as_of"] == TODAY
    assert body["window_days"] == 30
    assert body["source"] == "ftf_community_value"

    assert [m["player_id"] for m in body["risers"]] == ["p_up", "p_up2"]
    assert [m["player_id"] for m in body["fallers"]] == ["p_dn", "p_dn2"]

    top = body["risers"][0]
    assert set(top) == {"player_id", "name", "position", "team",
                        "pct_30d", "value_now"}
    assert top["name"] == "Ashton Jeanty"
    assert top["position"] == "RB"
    assert top["team"] == "LV"
    assert top["pct_30d"] == 21.0
    assert top["value_now"] == 1210.0
    assert body["fallers"][0]["pct_30d"] == -14.0


def test_top_n_param_and_hard_cap_10(client):
    c, _ = client
    rows, pool = [], []
    for i in range(12):                       # 12 risers → capped at 10
        pid = f"r{i}"
        rows += [_snap(pid, BASE_DAY, 1000.0),
                 _snap(pid, TODAY, 1000.0 + 10 * (i + 1))]
        pool.append(_player(pid, f"Riser {i}"))
    record_value_snapshots(rows)
    p1, p2 = _pool(pool)
    with p1, p2:
        r_default = c.get("/api/market/movers")
        r_one     = c.get("/api/market/movers?top_n=1")
        r_greedy  = c.get("/api/market/movers?top_n=50")
    assert len(r_default.get_json()["risers"]) == 10
    assert len(r_one.get_json()["risers"]) == 1
    # Biggest % gain first.
    assert r_one.get_json()["risers"][0]["player_id"] == "r11"
    assert len(r_greedy.get_json()["risers"]) == 10   # cap holds


# ---------------------------------------------------------------------------
# Thin history — empty-safe
# ---------------------------------------------------------------------------

def test_single_day_history_is_empty_safe(client):
    c, _ = client
    record_value_snapshots([_snap("p_up", TODAY, 1210.0)])
    p1, p2 = _pool([_player("p_up", "Ashton Jeanty", "RB", "LV")])
    with p1, p2:
        r = c.get("/api/market/movers")
    assert r.status_code == 200
    body = r.get_json()
    assert body["risers"] == [] and body["fallers"] == []
    assert body["as_of"] == TODAY                     # honest: history exists,
                                                      # baseline doesn't yet
