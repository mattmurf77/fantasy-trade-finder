"""Rookie-draft M0 — the player-cache refresh lifecycle.

Test matrix T-M0-01..09 from docs/plans/rookie-draft/lld.md §7.

What M0 fixes: the player pipeline had NO refresh path (the only bulk fetch
was on a disk-cache miss, and the 24 h sync gate re-synced from that same
stale file), and `_ensure_universal_pools` froze the pool per-process. So a
new rookie class could not appear without a redeploy.

Everything here is offline: `_fetch_players_bulk` and `_load_dp_maps` are the
two seams, the players cache is redirected to a tmp file, and the DB is
in-memory SQLite. The real `data/.sleeper_players_cache.json` and
`data/trade_finder.db` are never touched.
"""
import json
import os
import threading
import time
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.pool import StaticPool

import backend.database as db_module
import backend.draft_status as ds
import backend.server as server
from backend.data_loader import normalise_name
from backend.database import metadata, players_table


# ── fixture payloads ───────────────────────────────────────────────────────

def _sleeper_row(name, pos="RB", team="AAA", years_exp=0, rookie_year="2026"):
    row = {"full_name": name, "first_name": name.split()[0],
           "last_name": name.split()[-1], "position": pos, "team": team,
           "years_exp": years_exp, "status": "Active", "age": 23}
    if rookie_year is not None:
        row["metadata"] = {"rookie_year": rookie_year}
    return row


OLD_PAYLOAD = {"p1": _sleeper_row("Alpha Back")}
NEW_PAYLOAD = {"p1": _sleeper_row("Alpha Back"),
               "p2": _sleeper_row("Bravo Wideout", pos="WR", team="BBB")}

_DP_ELO = {normalise_name("Alpha Back"): 1700.0,
           normalise_name("Bravo Wideout"): 1600.0}
_DP_VALS = {normalise_name("Alpha Back"): 5000.0,
            normalise_name("Bravo Wideout"): 4000.0}
_DP_POS = {normalise_name("Alpha Back"): "RB",
           normalise_name("Bravo Wideout"): "WR"}


@pytest.fixture()
def m0(monkeypatch, tmp_path):
    """Isolated M0 world: tmp cache file, in-memory DB, empty pool globals."""
    # StaticPool: session_init builds its ranking services on worker threads,
    # and SQLite's default per-thread pool would hand each of them a FRESH,
    # empty :memory: database.
    engine = create_engine("sqlite:///:memory:", poolclass=StaticPool,
                           connect_args={"check_same_thread": False})
    metadata.create_all(engine)
    monkeypatch.setattr(db_module, "engine", engine)

    cache_file = tmp_path / ".sleeper_players_cache.json"
    monkeypatch.setattr(server, "PLAYERS_CACHE_FILE", cache_file)
    monkeypatch.setattr(server, "_sleeper_cache", None)

    monkeypatch.setattr(server, "g_universal_by_format", {})
    monkeypatch.setattr(server, "dp_values_by_format", {})
    monkeypatch.setattr(server, "dp_elo_by_format", {})
    monkeypatch.setattr(server, "dp_pos_by_format", {})
    monkeypatch.setattr(server, "_dp_fetch_retry_at", {})
    monkeypatch.setattr(server, "g_universal_players", [])
    monkeypatch.setattr(server, "g_universal_seed", {})
    monkeypatch.setattr(server, "dp_values", {})
    monkeypatch.setattr(server, "_pool_generation", 0)
    monkeypatch.setattr(server, "_players_refresh_active", False)
    monkeypatch.setattr(server, "_last_refresh_status", {})
    monkeypatch.setattr(server, "_PLAYERS_REFRESH_ENABLED", True)
    monkeypatch.setattr(server, "_fetch_sleeper_adp", lambda: {})
    server._invalidate_rookie_ids_memo()

    def _stub_dp(fmts):
        for fmt in fmts:
            server.dp_values_by_format.setdefault(fmt, dict(_DP_VALS))
            server.dp_elo_by_format.setdefault(fmt, dict(_DP_ELO))
            server.dp_pos_by_format.setdefault(fmt, dict(_DP_POS))

    monkeypatch.setattr(server, "_load_dp_maps", _stub_dp)
    yield cache_file, engine
    server._invalidate_rookie_ids_memo()


def _pool_ids(fmt="1qb_ppr"):
    return {p.id for p in server.g_universal_by_format.get(fmt, {}).get("players", [])}


# ---------------------------------------------------------------------------
# T-M0-01 — atomic write: a reader sees old-or-new, never partial
# ---------------------------------------------------------------------------

def test_atomic_write_never_exposes_a_partial_file(m0):
    cache_file, _ = m0
    old = {f"o{i}": _sleeper_row(f"Old Guy{i}") for i in range(400)}
    new = {f"n{i}": _sleeper_row(f"New Guy{i}") for i in range(4000)}
    cache_file.write_text(json.dumps(old))

    seen: list[int] = []
    errors: list[Exception] = []
    stop = threading.Event()

    def reader():
        while not stop.is_set():
            try:
                seen.append(len(json.loads(cache_file.read_text())))
            except Exception as e:            # a partial file would land here
                errors.append(e)

    t = threading.Thread(target=reader, daemon=True)
    t.start()
    try:
        for _ in range(15):
            server._atomic_write_players_cache(new)
            server._atomic_write_players_cache(old)
    finally:
        stop.set()
        t.join(timeout=5)

    assert errors == [], f"reader observed a torn file: {errors[:3]}"
    assert seen, "reader never got a read in — test is not exercising the race"
    assert set(seen) <= {len(old), len(new)}
    # No temp files left behind.
    assert [p.name for p in cache_file.parent.iterdir()] == [cache_file.name]


def test_atomic_write_temp_file_lives_in_the_target_directory(m0, monkeypatch):
    """os.replace is only atomic WITHIN a filesystem — a /tmp staging file
    would silently degrade to a copy. Pin that the temp file is a sibling."""
    cache_file, _ = m0
    seen_dirs: list[str] = []
    real_ntf = server.tempfile.NamedTemporaryFile

    def spy(*a, **kw):
        seen_dirs.append(kw.get("dir"))
        return real_ntf(*a, **kw)

    monkeypatch.setattr(server.tempfile, "NamedTemporaryFile", spy)
    server._atomic_write_players_cache(OLD_PAYLOAD)
    assert seen_dirs == [str(cache_file.parent)]


# ---------------------------------------------------------------------------
# T-M0-02 — the ordered invalidation reaches every stage
# ---------------------------------------------------------------------------

def test_forced_refresh_propagates_to_disk_memory_db_and_pool(m0, monkeypatch):
    cache_file, engine = m0
    cache_file.write_text(json.dumps(OLD_PAYLOAD))
    server._load_sleeper_cache()
    server._ensure_universal_pools()
    assert _pool_ids() >= {"p1"} and "p2" not in _pool_ids()
    gen_before = server.pool_generation()

    monkeypatch.setattr(server, "_fetch_players_bulk", lambda: dict(NEW_PAYLOAD))
    server._players_refresh_worker()

    # 1. disk
    assert set(json.loads(cache_file.read_text())) == {"p1", "p2"}
    # 2. in-memory cache global
    assert set(server._sleeper_cache) == {"p1", "p2"}
    # 3. players table (sync_players called directly, past the 24 h gate)
    with engine.connect() as conn:
        rows = conn.execute(select(players_table.c.player_id,
                                   players_table.c.last_synced)).fetchall()
    assert {r.player_id for r in rows} == {"p1", "p2"}
    assert all(r.last_synced for r in rows)
    # 5. pool membership
    assert {"p1", "p2"} <= _pool_ids()
    assert {"p1", "p2"} <= _pool_ids("sf_tep")
    # 6. generation bumped AFTER the rebind
    assert server.pool_generation() == gen_before + 1
    assert server._last_refresh_status["ok"] is True
    assert server._last_refresh_status["players"] == 2
    # legacy aliases rebound, not left pointing at the old world
    assert {p.id for p in server.g_universal_players} == _pool_ids()


def test_refresh_routes_the_bulk_fetch_through_the_fixture_seam(m0, monkeypatch):
    """[RV-3] — the legacy cold-start fetch uses raw urllib, which the fixture
    seam cannot intercept. M0's fetch must go through `_sleeper_get`."""
    calls: list[tuple] = []
    monkeypatch.setattr(server, "_sleeper_get",
                        lambda url, timeout=15: (calls.append((url, timeout))
                                                 or dict(NEW_PAYLOAD)))
    out = server._fetch_players_bulk()
    assert calls == [("https://api.sleeper.app/v1/players/nfl", 45)]
    assert set(out) == {"p1", "p2"}


def test_bulk_fetch_filter_matches_the_legacy_cold_start_filter(m0):
    raw = {"a": _sleeper_row("Keep Me", pos="RB"),
           "b": _sleeper_row("Drop Me", pos="K"),
           "c": {"position": "WR"}}                     # no full_name
    assert set(server._filter_bulk_players(raw)) == {"a"}


# ---------------------------------------------------------------------------
# T-M0-03 — the refresh never parks a request worker
# ---------------------------------------------------------------------------

def test_request_path_is_not_blocked_while_a_refresh_runs(m0, monkeypatch):
    cache_file, _ = m0
    cache_file.write_text(json.dumps(OLD_PAYLOAD))
    server._load_sleeper_cache()
    server._ensure_universal_pools()          # warm: the fast path is lock-free

    slow = threading.Event()

    def _slow_dp(fmts):
        slow.set()
        time.sleep(0.4)                       # holds _pool_build_lock throughout
        for fmt in fmts:
            server.dp_values_by_format.setdefault(fmt, dict(_DP_VALS))
            server.dp_elo_by_format.setdefault(fmt, dict(_DP_ELO))
            server.dp_pos_by_format.setdefault(fmt, dict(_DP_POS))

    monkeypatch.setattr(server, "_load_dp_maps", _slow_dp)
    monkeypatch.setattr(server, "_fetch_players_bulk", lambda: dict(NEW_PAYLOAD))

    worker = threading.Thread(target=server._players_refresh_worker, daemon=True)
    worker.start()
    assert slow.wait(timeout=5)

    timings = []
    for _ in range(200):
        t0 = time.perf_counter()
        server._get_universal_pool("1qb_ppr")
        server.pool_generation()
        timings.append(time.perf_counter() - t0)
    worker.join(timeout=10)

    assert max(timings) < 0.05, (
        f"request path stalled behind the refresh (max {max(timings):.3f}s) — "
        "a lock on the read path would reintroduce the D1 latency regression")


# ---------------------------------------------------------------------------
# T-M0-04 (VFF) — membership-only bump, rule G-SEED
# ---------------------------------------------------------------------------

UID = "313560442465169408"


@pytest.fixture()
def init_client(monkeypatch, m0):
    """Minimum session_init world (mirrors test_verified_sessions.init_client)."""
    _, engine = m0
    from backend.ranking_service import Player

    server.app.config["TESTING"] = True
    c = server.app.test_client()

    pool_v1 = [Player("qb_1", "QB One", "QB", "AAA", 25, 3),
               Player("rb_1", "RB One", "RB", "BBB", 24, 2)]
    seed_v1 = {"qb_1": 1500.0, "rb_1": 1400.0}
    pools = {"1qb_ppr": {"players": list(pool_v1), "seed": dict(seed_v1)},
             "sf_tep":  {"players": list(pool_v1), "seed": dict(seed_v1)}}

    monkeypatch.setattr(server, "_load_sleeper_cache", lambda: {})
    monkeypatch.setattr(server, "_ensure_universal_pools", lambda: None)
    monkeypatch.setattr(server, "g_universal_by_format", pools)
    monkeypatch.setattr(server, "g_universal_players", list(pool_v1))
    monkeypatch.setattr(server, "_kickoff_trade_job", MagicMock())
    monkeypatch.setattr(server, "_fetch_sleeper_league_meta", lambda lid: None)
    # Init resolves membership from this imported snapshot, not request JSON.
    with engine.begin() as conn:
        conn.execute(db_module.leagues_table.insert().values(
            sleeper_league_id="league_m0", user_id=UID, name="M0 League", platform="mfl"))
    db_module.upsert_league_members("league_m0", [
        {"user_id": UID, "username": "Owner", "player_ids": ["qb_1"]},
        {"user_id": "opp_1", "username": "Opp", "player_ids": ["rb_1"]},
    ])
    with server._sessions_lock:
        server._sessions["m0-verified-token"] = {"user_id": UID, "verified": True}

    real_thread = server.threading.Thread

    class _SelectiveThread(real_thread):
        def start(self):
            if self.name == "session-init-bg-writes":
                return
            super().start()

    monkeypatch.setattr(server.threading, "Thread", _SelectiveThread)

    with patch.object(server, "touch_user_activity", MagicMock()):
        yield c, pools, Player
    with server._sessions_lock:
        for tok in [t for t, s in server._sessions.items()
                    if s.get("user_id") == UID]:
            server._sessions.pop(tok, None)


def _init(c, token="m0-verified-token"):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-Session-Token"] = token
    r = c.post("/api/session/init", headers=headers, data=json.dumps({
        "user_id": UID, "league_id": "league_m0", "league_name": "M0 League",
        "user_player_ids": ["qb_1"],
        "opponent_rosters": [{"user_id": "opp_1", "username": "Opp",
                              "player_ids": ["rb_1"]}],
    }))
    assert r.status_code == 200, r.get_data(as_text=True)
    return r.get_json()["token"]


def test_generation_bump_changes_membership_only_and_carries_seeds(init_client):
    """VFF — rule G-SEED (D1, I-6).

    A generation bump must change pool MEMBERSHIP only: every pid present
    before AND after keeps its prior seed Elo, and only new members get the
    fresh consensus seed. Without the carry, a mid-season DynastyProcess drift
    would silently re-seed everyone's board on the next app open.
    """
    c, pools, Player = init_client

    token = _init(c)
    with server._sessions_lock:
        sess = server._sessions[token]
    svc_before = sess["services"]["1qb_ppr"]
    assert sess["pool_generation"] == server.pool_generation()
    assert svc_before._seed["qb_1"] == 1500.0

    # New world: qb_1's consensus seed moved, and wr_9 joined the pool.
    new_players = [Player("qb_1", "QB One", "QB", "AAA", 25, 3),
                   Player("rb_1", "RB One", "RB", "BBB", 24, 2),
                   Player("wr_9", "WR Nine", "WR", "CCC", 22, 0)]
    new_seed = {"qb_1": 1800.0, "rb_1": 1400.0, "wr_9": 1650.0}
    for fmt in ("1qb_ppr", "sf_tep"):
        pools[fmt] = {"players": list(new_players), "seed": dict(new_seed)}
    server._bump_pool_generation()

    token2 = _init(c, token)
    with server._sessions_lock:
        sess2 = server._sessions[token2]
    svc_after = sess2["services"]["1qb_ppr"]

    assert svc_after is not svc_before, "generation bump must force a rebuild"
    assert sess2["pool_generation"] == server.pool_generation()
    # membership grew…
    assert set(svc_after._players) >= {"qb_1", "rb_1", "wr_9"}
    assert "wr_9" not in svc_before._players
    # …but existing members carried their seed forward, byte-identical
    assert svc_after._seed["qb_1"] == 1500.0
    assert svc_after._seed["rb_1"] == 1400.0
    # …and only the NEW member took the fresh consensus seed
    assert svc_after._seed["wr_9"] == 1650.0


def test_same_generation_reuses_services(init_client):
    c, _pools, _Player = init_client
    token = _init(c)
    with server._sessions_lock:
        svc = server._sessions[token]["services"]["1qb_ppr"]
    token2 = _init(c, token)
    with server._sessions_lock:
        assert server._sessions[token2]["services"]["1qb_ppr"] is svc


# ---------------------------------------------------------------------------
# T-M0-05 — single-flight on _ensure_universal_pools
# ---------------------------------------------------------------------------

def test_concurrent_pool_builds_fan_out_exactly_once(m0, monkeypatch):
    cache_file, _ = m0
    cache_file.write_text(json.dumps(NEW_PAYLOAD))
    server._load_sleeper_cache()

    calls = []
    lock = threading.Lock()

    def _counting_dp(fmts):
        with lock:
            calls.append(tuple(fmts))
        time.sleep(0.05)
        for fmt in fmts:
            server.dp_values_by_format.setdefault(fmt, dict(_DP_VALS))
            server.dp_elo_by_format.setdefault(fmt, dict(_DP_ELO))
            server.dp_pos_by_format.setdefault(fmt, dict(_DP_POS))

    monkeypatch.setattr(server, "_load_dp_maps", _counting_dp)

    threads = [threading.Thread(target=server._ensure_universal_pools)
               for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert len(calls) == 1, (
        f"{len(calls)} DynastyProcess fan-outs for one cold pool — "
        "_player_sync_lock guards syncs, not pool builds")
    assert {"p1", "p2"} <= _pool_ids()


# ---------------------------------------------------------------------------
# T-M0-06 — a failed upstream leaves the previous world intact
# ---------------------------------------------------------------------------

def test_failed_fetch_leaves_cache_pool_and_generation_untouched(m0, monkeypatch):
    cache_file, _ = m0
    cache_file.write_text(json.dumps(OLD_PAYLOAD))
    server._load_sleeper_cache()
    server._ensure_universal_pools()
    before_ids, before_gen = _pool_ids(), server.pool_generation()
    before_disk = cache_file.read_text()

    def _boom():
        raise OSError("sleeper is down")

    monkeypatch.setattr(server, "_fetch_players_bulk", _boom)
    server._players_refresh_worker()           # must not raise

    assert cache_file.read_text() == before_disk
    assert _pool_ids() == before_ids
    assert server.pool_generation() == before_gen
    assert server._last_refresh_status["ok"] is False
    assert "sleeper is down" in server._last_refresh_status["error"]
    assert server._players_refresh_active is False


def test_failed_dp_rebuild_never_empties_the_pool(m0, monkeypatch):
    """A DP outage during the rebuild must keep the PREVIOUS pool, never
    publish an empty one (a cleared pool hands session_init a blank board)."""
    cache_file, _ = m0
    cache_file.write_text(json.dumps(OLD_PAYLOAD))
    server._load_sleeper_cache()
    server._ensure_universal_pools()
    before_ids, before_gen = _pool_ids(), server.pool_generation()
    assert before_ids

    monkeypatch.setattr(server, "_load_dp_maps", lambda fmts: None)   # DP down
    monkeypatch.setattr(server, "_fetch_players_bulk", lambda: dict(NEW_PAYLOAD))
    server._players_refresh_worker()

    assert _pool_ids() == before_ids
    assert server.pool_generation() == before_gen, \
        "generation must not move when no new pool was published"


# ---------------------------------------------------------------------------
# T-M0-07 — one refresh at a time; the cron route always 202s
# ---------------------------------------------------------------------------

def test_second_concurrent_refresh_is_refused(m0, monkeypatch):
    release = threading.Event()
    entered = threading.Event()

    def _blocking_worker():
        entered.set()
        release.wait(timeout=5)
        with server._players_refresh_lock:
            server._players_refresh_active = False

    monkeypatch.setattr(server, "_players_refresh_worker", _blocking_worker)
    assert server._refresh_players_cache_async(force=True) is True
    assert entered.wait(timeout=5)
    assert server._refresh_players_cache_async(force=True) is False
    release.set()
    time.sleep(0.1)


def test_cron_route_returns_202_and_never_blocks(m0, monkeypatch):
    cache_file, _ = m0
    cache_file.write_text(json.dumps(OLD_PAYLOAD))
    started = []
    monkeypatch.setattr(server, "_refresh_players_cache_async",
                        lambda force=False: (started.append(force) or True))
    server.app.config["TESTING"] = True
    c = server.app.test_client()

    r = c.post("/api/cron/players-refresh?force=1", headers={"X-Cron-Secret": "x"})
    assert r.status_code == 202
    body = r.get_json()
    assert body["ok"] is True and body["started"] is True
    assert body["generation"] == server.pool_generation()
    assert isinstance(body["cache_age_s"], float)
    assert started == [True]


def test_refresh_skips_a_fresh_cache_but_force_overrides(m0, monkeypatch):
    cache_file, _ = m0
    cache_file.write_text(json.dumps(OLD_PAYLOAD))       # mtime = now
    ran = []
    monkeypatch.setattr(server, "_players_refresh_worker",
                        lambda: ran.append(1))
    assert server._refresh_players_cache_async() is False
    assert ran == []
    assert server._refresh_players_cache_async(force=True) is True
    time.sleep(0.1)
    assert ran == [1]


def test_kill_switch_makes_the_refresh_a_no_op(m0, monkeypatch):
    monkeypatch.setattr(server, "_PLAYERS_REFRESH_ENABLED", False)
    ran = []
    monkeypatch.setattr(server, "_players_refresh_worker", lambda: ran.append(1))
    assert server._refresh_players_cache_async(force=True) is False
    assert ran == []
    assert server._players_refresh_active is False


# ---------------------------------------------------------------------------
# T-M0-08 — dev cache-age guard
# ---------------------------------------------------------------------------

def test_stale_cache_refuses_rookie_scope_outside_prod(m0, monkeypatch):
    cache_file, _ = m0
    cache_file.write_text(json.dumps(OLD_PAYLOAD))
    stale = time.time() - 30 * 86_400
    os.utime(cache_file, (stale, stale))

    monkeypatch.setattr(server, "_IS_PROD_ENV", False)
    monkeypatch.setattr(server, "_TEST_MODE", False)
    assert server._rookie_scope_allowed() == (False, "stale_player_cache")

    # FTF_TEST_MODE is exempt — the Maestro harness runs a pinned cache file.
    monkeypatch.setattr(server, "_TEST_MODE", True)
    assert server._rookie_scope_allowed() == (True, None)

    # Prod is exempt — the daily tick keeps it fresh and refusing there would
    # be the worse failure.
    monkeypatch.setattr(server, "_TEST_MODE", False)
    monkeypatch.setattr(server, "_IS_PROD_ENV", True)
    assert server._rookie_scope_allowed() == (True, None)


def test_fresh_cache_allows_rookie_scope(m0, monkeypatch):
    cache_file, _ = m0
    cache_file.write_text(json.dumps(OLD_PAYLOAD))
    monkeypatch.setattr(server, "_IS_PROD_ENV", False)
    monkeypatch.setattr(server, "_TEST_MODE", False)
    assert server._rookie_scope_allowed() == (True, None)
    cache_file.unlink()                       # no file ⇒ no age ⇒ no refusal
    assert server._rookie_scope_allowed() == (True, None)


# ---------------------------------------------------------------------------
# T-M0-09 — THE rookie predicate: SQL mirror agrees with is_rookie_row
# ---------------------------------------------------------------------------

# (player_id, rookie_year, years_exp, team) — the full matrix the plan names.
_PREDICATE_MATRIX = [
    ("exact_hit",        "2026", 0,    "ARI"),
    ("exact_hit_vet_yr", "2026", 3,    "ARI"),   # class year beats years_exp
    ("exact_miss",       "2025", 0,    "ARI"),
    ("proxy_hit",        None,   0,    "ARI"),
    ("proxy_no_team",    None,   0,    None),    # teamless pre-draft tail
    ("proxy_blank_team", None,   0,    ""),
    ("proxy_yr1",        None,   1,    "ARI"),
    ("proxy_null_exp",   None,   None, "ARI"),
]


def test_load_rookie_player_ids_mirrors_is_rookie_row(m0):
    _, engine = m0
    with engine.begin() as conn:
        for pid, ry, ye, team in _PREDICATE_MATRIX:
            conn.execute(players_table.insert().values(
                player_id=pid, full_name=pid, position="RB",
                rookie_year=ry, years_exp=ye, team=team))

    expected = {pid for pid, ry, ye, team in _PREDICATE_MATRIX
                if ds.is_rookie_row(ry, ye, team, 2026)}
    assert expected == {"exact_hit", "exact_hit_vet_yr", "proxy_hit"}
    assert db_module.load_rookie_player_ids(2026) == expected


def test_load_rookies_is_rebased_onto_the_pinned_predicate(m0):
    """The legacy `years_exp == 0 OR years_exp IS NULL` rule was a THIRD,
    looser definition that swept in the whole teamless prospect tail."""
    _, engine = m0
    with engine.begin() as conn:
        for pid, ry, ye, team in _PREDICATE_MATRIX:
            conn.execute(players_table.insert().values(
                player_id=pid, full_name=pid, position="RB",
                rookie_year=ry, years_exp=ye, team=team,
                search_rank={"exact_hit": 5, "proxy_hit": 1}.get(pid)))

    rows = db_module.load_rookies(2026)
    assert {r["player_id"] for r in rows} == {"exact_hit", "exact_hit_vet_yr",
                                             "proxy_hit"}
    # search_rank ascending, NULLs last
    assert [r["player_id"] for r in rows] == ["proxy_hit", "exact_hit",
                                             "exact_hit_vet_yr"]
    # A far-future season keeps only the PROXY rows: `years_exp == 0 AND team`
    # carries no year, so it matches any season by construction. That is why
    # the class-load monitor uses the exact-only `count_rookie_class_rows`
    # rather than this predicate.
    assert {r["player_id"] for r in db_module.load_rookies(2099)} == {"proxy_hit"}


def test_rookie_ids_memo_is_keyed_on_the_pool_generation(m0, monkeypatch):
    _, engine = m0
    with engine.begin() as conn:
        conn.execute(players_table.insert().values(
            player_id="r1", full_name="R One", position="RB",
            rookie_year="2026", years_exp=0, team="ARI"))

    calls = []
    real = db_module.load_rookie_player_ids
    monkeypatch.setattr(server, "load_rookie_player_ids",
                        lambda s: (calls.append(s) or real(s)))

    assert server._rookie_player_ids(2026) == {"r1"}
    assert server._rookie_player_ids(2026) == {"r1"}
    assert calls == [2026], "second read should be memoised"

    server._bump_pool_generation()
    assert server._rookie_player_ids(2026) == {"r1"}
    assert calls == [2026, 2026], "a generation bump must invalidate the memo"


# ---------------------------------------------------------------------------
# Class-load monitor (plan §M0)
# ---------------------------------------------------------------------------

def test_class_load_monitor_fires_once_when_the_next_class_appears(m0, monkeypatch):
    _, engine = m0
    monkeypatch.setattr(server, "_class_load_seen", set())

    assert server._check_rookie_class_load(2027) is False
    # The years_exp proxy must NOT count — it is season-independent and would
    # make the monitor fire on day one.
    with engine.begin() as conn:
        conn.execute(players_table.insert().values(
            player_id="cur", full_name="Cur Rookie", position="RB",
            rookie_year=None, years_exp=0, team="ARI"))
    assert server._check_rookie_class_load(2027) is False

    with engine.begin() as conn:
        conn.execute(players_table.insert().values(
            player_id="nxt", full_name="Next Rookie", position="WR",
            rookie_year="2027", years_exp=0, team="BUF"))
    assert server._check_rookie_class_load(2027) is True
    assert server._check_rookie_class_load(2027) is False   # one-shot
    assert db_module.count_rookie_class_rows(2027) == 1
