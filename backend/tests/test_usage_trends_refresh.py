"""Usage Trends weekly data update — usage_trends_refresh + the usage_* store.

Spec: docs/plans/usage-trends/weekly-update.md. Covers:
  * completed_weeks: regular season = weeks before the one in progress;
    post season = all 18; pre/off season = nothing;
  * plan_weeks: backfill every missing completed week; re-fetch a stored week
    for stat corrections only while it is under 7 days old AND its last fetch
    is 20+ hours old; older weeks are frozen;
  * refresh_usage_weeks: stores normalized weeks; an identical re-fetch only
    touches fetched_at; a stat correction replaces the week and moves
    changed_at but not first_fetched_at; a partial week (< 24 teams), a
    failed fetch or a bad state read is reported and never stored; dry_run
    writes nothing; `weeks` + `force` re-fetch on demand;
  * the store round-trips: compute over stored weeks == compute over the live
    feed (real 2026 NYJ+PHI capture);
  * the route reads each stored week without calling Sleeper's stats feed
    and fetches live only the weeks the store lacks;
  * the cron route (auth, body validation) and the daily-tick step (flag off
    = disabled, so the tick payload is unchanged); single-flight.
"""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine

import backend.database as db_module
import backend.server as server
from backend import usage_trends as ut
from backend import usage_trends_refresh as ur
from backend.database import metadata

REPO = Path(__file__).resolve().parents[2]
FIXTURE = REPO / "backend/tests/fixtures/usage_trends/sleeper_stats_2026_w1-4_nyj_phi.json"
T0 = datetime(2026, 10, 7, 14, 0, tzinfo=timezone.utc)   # a Wednesday
TEAMS = [f"T{i:02d}" for i in range(26)]


@pytest.fixture()
def mem_db():
    eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    metadata.create_all(eng)
    with patch.object(db_module, "engine", eng):
        yield eng


def _week_rows(week: int, bump: int = 0, teams=TEAMS):
    rows = []
    for t in teams:
        rows.append({"player_id": f"qb_{t}", "team": t, "player": {"position": "QB"},
                     "stats": {"gp": 1, "off_snp": 60, "tm_off_snp": 60, "rush_att": 3}})
        rows.append({"player_id": f"wr_{t}", "team": t,
                     "player": {"position": "WR", "first_name": "W", "last_name": t},
                     "stats": {"gp": 1, "off_snp": 40 + week + bump, "tm_off_snp": 60,
                               "rec_tgt": 5}})
    return rows


class Feed:
    def __init__(self, week=5, season_type="regular", bump=None, fail=(), teams=None):
        self.state = {"season": "2026", "week": week, "season_type": season_type}
        self.bump = bump or {}
        self.fail = set(fail)
        self.teams = teams or {}
        self.calls = []

    def __call__(self, url):
        self.calls.append(url)
        if url.endswith("/state/nfl"):
            return self.state
        w = int(url.split("/stats/nfl/2026/")[1].split("?")[0])
        if w in self.fail:
            raise OSError("down")
        return _week_rows(w, self.bump.get(w, 0), self.teams.get(w, TEAMS))


# ── calendar ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("state, expected", [
    ({"season": "2026", "week": 5, "season_type": "regular"}, (2026, [1, 2, 3, 4])),
    ({"season": "2026", "week": 1, "season_type": "regular"}, (2026, [])),
    ({"season": "2026", "week": 2, "season_type": "post"}, (2026, list(range(1, 19)))),
    ({"season": "2026", "week": 0, "season_type": "pre"}, (2026, [])),
    ({"season": "2026", "week": 0, "season_type": "off"}, (2026, [])),
])
def test_completed_weeks(state, expected):
    assert ur.completed_weeks(state) == expected


def test_plan_backfills_missing_then_corrects_only_young_stale_weeks():
    iso = lambda dt: dt.isoformat()
    loads = {
        1: {"first_fetched_at": iso(T0 - timedelta(days=20)), "fetched_at": iso(T0 - timedelta(days=13))},
        3: {"first_fetched_at": iso(T0 - timedelta(days=2)), "fetched_at": iso(T0 - timedelta(hours=21))},
        4: {"first_fetched_at": iso(T0 - timedelta(hours=5)), "fetched_at": iso(T0 - timedelta(hours=5))},
    }
    # 2 missing (backfill), 3 young + stale (correction), 1 frozen, 4 fresh.
    assert ur.plan_weeks([1, 2, 3, 4], loads, T0) == [2, 3]


# ── refresh ─────────────────────────────────────────────────────────────────

def test_first_run_stores_every_completed_week(mem_db):
    out = ur.refresh_usage_weeks(Feed(), now=T0)
    assert out["season"] == 2026 and out["stored"] == [1, 2, 3, 4] and not out["skipped"]
    loads = db_module.load_usage_week_loads(2026)
    assert sorted(loads) == [1, 2, 3, 4]
    assert loads[4]["team_count"] == 26 and loads[4]["player_count"] == 26
    teams, players = db_module.load_usage_weeks(2026, [4])[4]
    assert teams["T00"] == {"snaps": 60, "carries": 3, "targets": 5}
    assert players["wr_T00"] == {"name": "W T00", "position": "WR", "team": "T00",
                                 "played": True, "snaps": 44, "carries": 0, "targets": 5}


def test_identical_refetch_only_touches_and_correction_replaces(mem_db):
    ur.refresh_usage_weeks(Feed(), now=T0)
    before = db_module.load_usage_week_loads(2026)
    out = ur.refresh_usage_weeks(Feed(), now=T0 + timedelta(days=1))
    assert out["unchanged"] == [1, 2, 3, 4] and out["stored"] == []
    out = ur.refresh_usage_weeks(Feed(bump={4: 3}), now=T0 + timedelta(days=2))
    assert out["changed"] == [4] and out["stored"] == [4]
    after = db_module.load_usage_week_loads(2026)
    assert after[4]["first_fetched_at"] == before[4]["first_fetched_at"]
    assert after[4]["changed_at"] != before[4]["changed_at"]
    assert after[3]["changed_at"] == before[3]["changed_at"]
    assert db_module.load_usage_weeks(2026, [4])[4][1]["wr_T00"]["snaps"] == 47


def test_weeks_freeze_after_the_correction_window(mem_db):
    ur.refresh_usage_weeks(Feed(), now=T0)
    feed = Feed(bump={1: 9})
    out = ur.refresh_usage_weeks(feed, now=T0 + timedelta(days=8))
    assert out["planned"] == [] and not any("/stats/" in u for u in feed.calls)


def test_partial_week_failed_fetch_and_bad_state_are_reported_not_stored(mem_db):
    out = ur.refresh_usage_weeks(Feed(fail={2}, teams={3: TEAMS[:10]}), now=T0)
    assert out["stored"] == [1, 4]
    assert out["skipped"][2].startswith("fetch_failed") and out["skipped"][3] == "incomplete: 10 teams"
    assert sorted(db_module.load_usage_week_loads(2026)) == [1, 4]
    def bad_state(url):
        raise OSError("sleeper down")
    out = ur.refresh_usage_weeks(bad_state, now=T0)
    assert out["error"].startswith("state_unavailable")


def test_dry_run_writes_nothing_and_force_refetches_named_weeks(mem_db):
    out = ur.refresh_usage_weeks(Feed(), now=T0, dry_run=True)
    assert out["stored"] == [1, 2, 3, 4] and db_module.load_usage_week_loads(2026) == {}
    ur.refresh_usage_weeks(Feed(), now=T0)
    feed = Feed(bump={2: 1})
    out = ur.refresh_usage_weeks(feed, now=T0, weeks=[2], force=True)
    assert out["planned"] == [2] and out["changed"] == [2]


def test_stored_weeks_compute_exactly_like_the_live_feed(mem_db):
    doc = json.loads(FIXTURE.read_text())
    raw = {int(w): rows for w, rows in doc["weeks"].items()}
    for w, rows in raw.items():
        teams, players = ut.normalize_week(rows)
        db_module.replace_usage_week(2026, w, teams, players,
                                     content_hash=ur.content_hash(teams, players))
    stored = db_module.load_usage_weeks(2026, [1, 2, 3, 4])
    assert ut.compute_normalized(stored, [1, 2, 3, 4]) == ut.compute(raw, [1, 2, 3, 4])


# ── route + cron wiring ─────────────────────────────────────────────────────

def test_route_weeks_come_from_the_store_and_only_missing_weeks_go_live(mem_db):
    ur.refresh_usage_weeks(Feed(), now=T0)            # stores weeks 1-4
    server._usage_cache.clear()
    def no_stats(url, timeout=15):
        raise AssertionError(f"stats fetched for a stored week: {url}")
    with patch.object(server, "_sleeper_get", no_stats):
        stored = [server._usage_week(2026, w) for w in (1, 2, 3, 4)]
    assert all(teams and players for teams, players in stored)
    feed = Feed(week=6)
    with patch.object(server, "_sleeper_get", lambda url, timeout=15: feed(url)):
        server._usage_week(2026, 4)                   # cached: no call
        server._usage_week(2026, 5)                   # not stored: one live call
    assert [u for u in feed.calls if "/stats/" in u] == [ut.stats_url(2026, 5)]
    server._usage_cache.clear()


@pytest.fixture()
def client(monkeypatch):
    server.app.config["TESTING"] = True
    monkeypatch.setattr(server, "_CRON_SECRET", "s3cret")
    return server.app.test_client()


def test_cron_route_auth_validation_and_args(client):
    assert client.post("/api/cron/usage-trends-refresh").status_code == 401
    hdr = {"X-Cron-Secret": "s3cret"}
    assert client.post("/api/cron/usage-trends-refresh", json={"weeks": "1-4"},
                       headers=hdr).status_code == 400
    seen = {}
    with patch.object(server, "_start_usage_refresh",
                      lambda source, **kw: seen.update(source=source, **kw) or True):
        r = client.post("/api/cron/usage-trends-refresh",
                        json={"weeks": [3, 4], "force": True}, headers=hdr)
    assert r.get_json() == {"ok": True, "started": True, "busy": False}
    assert seen == {"source": "cron_route", "weeks": [3, 4], "force": True, "dry_run": False}


def test_daily_tick_step_is_off_with_the_flag_and_single_flight(monkeypatch):
    monkeypatch.setattr(server, "is_enabled", lambda k: False)
    assert server._kickoff_usage_refresh(T0) == {"disabled": True}
    monkeypatch.setattr(server, "is_enabled", lambda k: k == "usage_trends.enabled")
    with patch.object(server, "_start_usage_refresh", lambda source, **kw: True):
        assert server._kickoff_usage_refresh(T0) == {"started": True}
    assert server._usage_refresh_lock.acquire(blocking=False)
    try:
        assert server._start_usage_refresh("test") is False
    finally:
        server._usage_refresh_lock.release()
