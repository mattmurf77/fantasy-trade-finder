"""#207 — the plumbing around the detector: players.rookie_year, the roster
scan, the per-league verdict cache and its asymmetric cheap-skip TTLs.

`test_draft_status.py` owns the decision matrix (pure, payload-in/verdict-out);
this owns everything that touches the DB or the network fetchers. In-memory
SQLite throughout — the real `data/trade_finder.db` is never opened.
"""
import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, select

import backend.database as db_module
import backend.draft_status as ds
import backend.mfl_service as mfl_module
import backend.server as server
from backend.database import metadata, leagues_table, players_table

LEAGUE_ID = "1312076055586050048"


@pytest.fixture()
def mem_db(monkeypatch):
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False})
    metadata.create_all(engine)
    monkeypatch.setattr(db_module, "engine", engine)
    server._invalidate_draft_context_cache()
    yield engine
    server._invalidate_draft_context_cache()


def _sleeper_player(pid, name, years_exp=0, team="ARI", rookie_year="2026",
                    status="Active", pos="RB"):
    p = {"full_name": name, "first_name": name.split()[0],
         "last_name": name.split()[-1], "position": pos, "team": team,
         "years_exp": years_exp, "status": status}
    if rookie_year is not None:
        p["metadata"] = {"rookie_year": rookie_year}
    return pid, p


def _seed_league(season="2026", platform="sleeper", status=None,
                 confidence=None, checked_at=None, total_rosters=12):
    with db_module.engine.begin() as conn:
        conn.execute(leagues_table.delete())
        conn.execute(leagues_table.insert().values(
            sleeper_league_id=LEAGUE_ID, user_id="u1", name="Lakeview",
            season=season, platform=platform, total_rosters=total_rosters,
            draft_status=status, draft_status_confidence=confidence,
            draft_status_checked_at=checked_at,
        ))
    server._invalidate_draft_context_cache()


# ── players.rookie_year ────────────────────────────────────────────────────

def test_sync_players_persists_rookie_year(mem_db):
    db_module.sync_players(dict([
        _sleeper_player("1", "Jeremiyah Love", 0, "ARI", "2026"),
        _sleeper_player("2", "Cam Ward", 1, "TEN", "2025", pos="QB"),
    ]))
    with mem_db.connect() as conn:
        got = {r.player_id: r.rookie_year for r in conn.execute(
            select(players_table.c.player_id, players_table.c.rookie_year)
        ).fetchall()}
    assert got == {"1": "2026", "2": "2025"}


def test_sync_players_drops_bogus_and_missing_rookie_years(mem_db):
    db_module.sync_players(dict([
        _sleeper_player("1", "Camp Body", 0, "ARI", "0"),        # Sleeper's "0"
        _sleeper_player("2", "No Meta", 0, "SF", None),          # no metadata
        _sleeper_player("3", "Junk Year", 0, "SF", "twenty26"),  # non-numeric
    ]))
    with mem_db.connect() as conn:
        got = {r.player_id: r.rookie_year for r in conn.execute(
            select(players_table.c.player_id, players_table.c.rookie_year)
        ).fetchall()}
    assert got == {"1": None, "2": None, "3": None}


def test_load_rookie_player_ids_prefers_class_year_then_proxies(mem_db):
    db_module.sync_players(dict([
        _sleeper_player("exact", "Class Of 26", 0, "ARI", "2026"),
        # years_exp==1 but a 2026 class year (Sleeper's accrued-season skew)
        _sleeper_player("skewed", "Accrued One", 1, "BUF", "2026"),
        _sleeper_player("older", "Class Of 25", 1, "TEN", "2025", pos="QB"),
        _sleeper_player("proxy", "No Class Rookie", 0, "SF", None),
        # teamless prospect — the pre-NFL-draft tail the proxy must exclude
        _sleeper_player("teamless", "Draft Prospect", 0, None, None),
        _sleeper_player("vet", "Old Vet", 6, "KC", None, pos="WR"),
    ]))
    assert db_module.load_rookie_player_ids(2026) == {"exact", "skewed", "proxy"}
    assert db_module.load_rookie_player_ids(2025) == {"older", "proxy"}


def test_count_known_player_ids(mem_db):
    db_module.sync_players(dict([_sleeper_player("1", "A Player")]))
    assert db_module.count_known_player_ids(["1", "999", "998"]) == 1
    assert db_module.count_known_player_ids([]) == 0


# ── roster scan ────────────────────────────────────────────────────────────

def test_rosters_rookie_verdict_counts_distinct_ids_and_team_spread(mem_db):
    rookie_ids = [f"r{i}" for i in range(12)]
    db_module.sync_players(dict(
        [_sleeper_player(r, f"Rookie {r}") for r in rookie_ids]
        + [_sleeper_player("vet", "A Vet", 8, "KC", None)]
    ))
    # 12 rookies spread over 6 teams (the exact threshold).
    rosters = [[rookie_ids[i * 2], rookie_ids[i * 2 + 1], "vet"]
               for i in range(6)] + [["vet"]] * 6
    v = server._rosters_rookie_verdict(rosters, 2026, 12)
    assert (v.status, v.confidence) == (ds.DRAFTED, ds.MEDIUM)
    assert v.evidence["rookies_rostered"] == 12
    assert v.evidence["teams_with_rookie"] == 6


def test_rosters_rookie_verdict_no_rookies_is_not_drafted(mem_db):
    db_module.sync_players(dict([_sleeper_player("vet", "A Vet", 8, "KC", None)]))
    v = server._rosters_rookie_verdict([["vet"]] * 12, 2026, 12)
    assert v.status == ds.NOT_DRAFTED


def test_rosters_rookie_verdict_abstains_on_a_stale_player_table(mem_db):
    """Rosters full of ids we cannot classify ⇒ our snapshot is stale."""
    db_module.sync_players(dict([_sleeper_player("vet", "A Vet", 8, "KC", None)]))
    rosters = [[f"unknown{i}{j}" for j in range(3)] for i in range(12)]
    assert server._rosters_rookie_verdict(rosters, 2026, 12).status == ds.UNKNOWN


def test_rosters_rookie_verdict_abstains_without_rosters(mem_db):
    assert server._rosters_rookie_verdict([], 2026, 12) is None
    assert server._rosters_rookie_verdict(None, 2026, 12) is None


# ── cheap-skip TTLs ────────────────────────────────────────────────────────

def _ago(hours):
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()


#: A `leagues.updated_at` inside the active-league window. Both sweep
#: work-lists now skip leagues nobody has opened in
#: `ACTIVE_LEAGUE_WINDOW_DAYS` days, so a fixture league that is meant to be
#: swept has to look like one somebody still uses.
def _active():
    return _ago(1)


#: A UTC instant INSIDE the rookie-draft window. The `not_drafted` TTL is
#: season-gated (3 h in-window, 24 h outside — see test_cron_sweep_scope.py),
#: so these expectations only hold against a pinned clock; on the wall clock
#: the same rows would flip on September 16.
_IN_WINDOW = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize("status,hours,fresh", [
    # A drafted league never un-drafts inside a season → long TTL.
    ("drafted", 6, True),
    ("drafted", 13, False),
    # An undrafted league flips exactly once → re-check eagerly.
    ("not_drafted", 1, True),
    ("not_drafted", 4, False),
    # A flaked read backs off least.
    ("unknown", 0.5, True),
    ("unknown", 2, False),
])
def test_cheap_skip_ttls_are_asymmetric(status, hours, fresh):
    checked = (_IN_WINDOW - timedelta(hours=hours)).isoformat()
    ctx = {"status": status, "checked_at": checked}
    assert server._draft_status_is_fresh(ctx, now=_IN_WINDOW) is fresh


def test_never_checked_league_is_never_fresh():
    assert server._draft_status_is_fresh(None) is False
    assert server._draft_status_is_fresh({"status": "drafted",
                                          "checked_at": None}) is False
    assert server._draft_status_is_fresh({"status": None,
                                          "checked_at": _ago(0)}) is False
    assert server._draft_status_is_fresh({"status": "drafted",
                                          "checked_at": "not-a-date"}) is False


def test_not_drafted_is_rechecked_more_eagerly_than_drafted():
    assert (server._DRAFT_STATUS_TTL_SECONDS["not_drafted"]
            < server._DRAFT_STATUS_TTL_SECONDS["drafted"])


# ── end-to-end refresh ─────────────────────────────────────────────────────

def _patch_sleeper(monkeypatch, drafts, roster_player_ids):
    monkeypatch.setattr(server, "_fetch_sleeper_league_meta",
                        lambda lid: {"season": "2026", "total_rosters": 12,
                                     "settings": {"draft_rounds": 4}})
    monkeypatch.setattr(server, "_fetch_sleeper_drafts", lambda lid: drafts)
    monkeypatch.setattr(server, "_fetch_league_rosters",
                        lambda lid: [{"roster_id": i + 1, "players": r}
                                     for i, r in enumerate(roster_player_ids)])


def _stored():
    with db_module.engine.connect() as conn:
        row = conn.execute(
            select(leagues_table.c.draft_status,
                   leagues_table.c.draft_status_confidence,
                   leagues_table.c.draft_status_checked_at)
            .where(leagues_table.c.sleeper_league_id == LEAGUE_ID)
        ).fetchone()
    return row


def test_refresh_persists_a_high_confidence_sleeper_verdict(mem_db, monkeypatch):
    _seed_league()
    db_module.sync_players(dict([_sleeper_player("vet", "A Vet", 8, "KC", None)]))
    _patch_sleeper(monkeypatch,
                   [{"draft_id": "d1", "status": "complete", "season": "2026",
                     "last_picked": 1777947157960, "settings": {"rounds": 4}}],
                   [["vet"]] * 12)
    v = server._refresh_league_draft_status(LEAGUE_ID)
    assert v.status == ds.DRAFTED
    row = _stored()
    assert row.draft_status == "drafted"
    assert row.draft_status_checked_at


def test_refresh_records_the_roster_veto_over_a_pre_draft_status(mem_db,
                                                                 monkeypatch):
    """The off-platform-draft case: Sleeper still says pre_draft, but a full
    rookie class is rostered."""
    _seed_league()
    rookie_ids = [f"r{i}" for i in range(12)]
    db_module.sync_players(dict(
        [_sleeper_player(r, f"Rookie {r}") for r in rookie_ids]))
    _patch_sleeper(monkeypatch,
                   [{"draft_id": "d1", "status": "pre_draft", "season": "2026",
                     "last_picked": None, "settings": {"rounds": 4}}],
                   [[rookie_ids[i * 2], rookie_ids[i * 2 + 1]] for i in range(6)]
                   + [[]] * 6)
    v = server._refresh_league_draft_status(LEAGUE_ID)
    assert (v.status, v.source) == (ds.DRAFTED, ds.SRC_ROSTERS)
    assert _stored().draft_status_confidence == "medium"


def test_refresh_stamps_checked_at_even_for_unknown(mem_db, monkeypatch):
    """Otherwise a persistently broken league gets re-probed every tick."""
    _seed_league()
    _patch_sleeper(monkeypatch, [], [])
    v = server._refresh_league_draft_status(LEAGUE_ID)
    assert v.status == ds.UNKNOWN
    row = _stored()
    assert row.draft_status == "unknown" and row.draft_status_checked_at


def test_refresh_cheap_skips_a_fresh_verdict(mem_db, monkeypatch):
    _seed_league(status="drafted", confidence="high", checked_at=_ago(1))
    calls = []
    monkeypatch.setattr(server, "_fetch_sleeper_drafts",
                        lambda lid: calls.append(lid) or [])
    assert server._refresh_league_draft_status(LEAGUE_ID) is None
    assert calls == []
    # ...and force overrides the skip.
    _patch_sleeper(monkeypatch,
                   [{"draft_id": "d1", "status": "pre_draft", "season": "2026",
                     "settings": {"rounds": 4}}], [[]])
    assert server._refresh_league_draft_status(LEAGUE_ID, force=True) is not None


def test_refresh_is_a_no_op_for_an_unknown_league(mem_db):
    assert server._refresh_league_draft_status("nope") is None


def test_refresh_never_raises_when_a_fetcher_explodes(mem_db, monkeypatch):
    _seed_league()
    monkeypatch.setattr(server, "_fetch_sleeper_league_meta",
                        lambda lid: (_ for _ in ()).throw(RuntimeError("boom")))
    assert server._refresh_league_draft_status(LEAGUE_ID) is None


def test_refresh_uses_stored_members_for_a_platform_league(mem_db, monkeypatch):
    """ESPN/MFL/Fleaflicker rosters come from league_members (already
    crosswalked into Sleeper player-id space) — heuristic only for ESPN."""
    _seed_league(platform="espn")
    rookie_ids = [f"r{i}" for i in range(12)]
    db_module.sync_players(dict(
        [_sleeper_player(r, f"Rookie {r}") for r in rookie_ids]))
    db_module.upsert_league_members(league_id=LEAGUE_ID, members=[
        {"user_id": f"u{i}", "username": f"U{i}", "display_name": f"U{i}",
         "player_ids": [rookie_ids[i * 2], rookie_ids[i * 2 + 1]]}
        for i in range(6)
    ])
    v = server._refresh_league_draft_status(LEAGUE_ID)
    assert (v.status, v.source) == (ds.DRAFTED, ds.SRC_ROSTERS)


# ── refresh queue ──────────────────────────────────────────────────────────

def test_refresh_queue_puts_never_checked_leagues_first(mem_db):
    with db_module.engine.begin() as conn:
        conn.execute(leagues_table.insert(), [
            {"sleeper_league_id": "old", "user_id": "u",
             "updated_at": _active(), "draft_status_checked_at": _ago(48)},
            {"sleeper_league_id": "fresh", "user_id": "u",
             "updated_at": _active(), "draft_status_checked_at": _ago(1)},
            {"sleeper_league_id": "never", "user_id": "u",
             "updated_at": _active(), "draft_status_checked_at": None},
        ])
    assert db_module.load_league_ids_for_draft_status_refresh() == [
        "never", "old", "fresh"]


# ── hourly-tick sweep ──────────────────────────────────────────────────────

@pytest.fixture()
def cron_client(mem_db, monkeypatch):
    from unittest.mock import MagicMock
    server.app.config["TESTING"] = True
    monkeypatch.setattr(server, "load_all_signed_up_users",
                        MagicMock(return_value=[]))
    monkeypatch.setattr(server, "drain_due_queued_notifications",
                        MagicMock(return_value={}))
    monkeypatch.setattr(server, "_write_daily_value_snapshots",
                        MagicMock(return_value=(None, None)))
    return server.app.test_client()


def _tick(c):
    r = c.post("/api/cron/hourly-tick", headers={"X-Cron-Secret": "x"})
    assert r.status_code == 200, r.data
    return r.get_json()


def test_hourly_tick_refreshes_stale_leagues_and_skips_fresh_ones(
        cron_client, monkeypatch):
    with db_module.engine.begin() as conn:
        conn.execute(leagues_table.insert(), [
            {"sleeper_league_id": "111", "user_id": "u", "season": "2026",
             "total_rosters": 12, "draft_status": None,
             "updated_at": _active(), "draft_status_checked_at": None},
            {"sleeper_league_id": "222", "user_id": "u", "season": "2026",
             "total_rosters": 12, "draft_status": "drafted",
             "updated_at": _active(), "draft_status_checked_at": _ago(1)},
        ])
    server._invalidate_draft_context_cache()
    _patch_sleeper(monkeypatch,
                   [{"draft_id": "d1", "status": "complete", "season": "2026",
                     "last_picked": 1, "settings": {"rounds": 4}}], [[]])
    body = _tick(cron_client)
    assert body["draft_status_checked"] == 1       # 222 was cheap-skipped
    with db_module.engine.connect() as conn:
        rows = dict(conn.execute(
            select(leagues_table.c.sleeper_league_id,
                   leagues_table.c.draft_status)).fetchall())
    assert rows == {"111": "drafted", "222": "drafted"}


def test_hourly_tick_sweep_is_bounded_per_tick(cron_client, monkeypatch):
    n = server._DRAFT_STATUS_SWEEP_BUDGET + 5
    with db_module.engine.begin() as conn:
        conn.execute(leagues_table.insert(), [
            {"sleeper_league_id": str(i), "user_id": "u", "season": "2026",
             "total_rosters": 12, "updated_at": _active(),
             "draft_status_checked_at": None}
            for i in range(n)
        ])
    server._invalidate_draft_context_cache()
    _patch_sleeper(monkeypatch,
                   [{"draft_id": "d1", "status": "pre_draft", "season": "2026",
                     "settings": {"rounds": 4}}], [[]])
    assert _tick(cron_client)["draft_status_checked"] == \
        server._DRAFT_STATUS_SWEEP_BUDGET


def test_hourly_tick_survives_a_draft_status_sweep_failure(cron_client,
                                                           monkeypatch):
    monkeypatch.setattr(server, "load_league_ids_for_draft_status_refresh",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError()))
    body = _tick(cron_client)
    assert body["ok"] is True and body["draft_status_checked"] == 0


# ── #207/#228 MFL parity — futureDraftPicks snapshot refresh ───────────────
# The snapshot used to be captured once, at link/import, so an MFL league
# linked before its rookie draft kept that season's picks forever. It is now
# refreshed on the draft-status refresh cadence (no new cron), and the owned
# picks are re-normalized in the same pass so a verdict that just flipped to
# `drafted` takes effect immediately instead of at the next session init.

MFL_ID = "10005"


def _seed_mfl(future_picks, status=None, host="www48.myfantasyleague.com"):
    with db_module.engine.begin() as conn:
        conn.execute(leagues_table.delete())
    db_module.upsert_platform_league(
        league_id=MFL_ID, user_id="link_user", name="MFL League",
        platform="mfl", season=2026, auth="public", my_team="0001",
        total_rosters=12, host=host, future_picks=future_picks)
    db_module.set_league_draft_status(MFL_ID, status,
                                      "high" if status else None)
    server._invalidate_draft_context_cache()


def _stored_snapshot():
    with db_module.engine.connect() as conn:
        raw = conn.execute(
            select(leagues_table.c.platform_future_picks)
            .where(leagues_table.c.sleeper_league_id == MFL_ID)
        ).scalar()
    return json.loads(raw or "[]")


def _seed_mfl_members():
    db_module.upsert_league_members(league_id=MFL_ID, members=[
        {"user_id": "link_user", "username": "Me", "display_name": "Me",
         "player_ids": []}])


def _mfl_grid(made: int, total: int = 12):
    """A rookie-sized MFL draftResults grid with `made` of `total` picks in."""
    return {"draftResults": {"draftUnit": {"draftPick": [
        {"round": "1", "franchise": f"{i:04d}",
         "player": "17472" if i <= made else ""}
        for i in range(1, total + 1)]}}}


_STALE = [{"franchise_id": "0001", "year": "2026", "round": "1",
           "original_owner": "0001"},
          {"franchise_id": "0001", "year": "2027", "round": "1",
           "original_owner": "0001"}]

# What MFL actually returns post-draft: the drafted season is simply gone
# (verified live 2026-08-05 on public leagues 10005 and 60206).
_FRESH_EXPORT = {"futureDraftPicks": {"franchise": {
    "id": "0001",
    "futureDraftPick": [{"year": "2027", "round": "1",
                         "originalPickFor": "0001"},
                        {"year": "2028", "round": "1",
                         "originalPickFor": "0001"}]}}}


def test_snapshot_refresh_replaces_a_stale_link_time_capture(mem_db,
                                                             monkeypatch):
    _seed_mfl(_STALE)
    monkeypatch.setattr(mfl_module, "fetch_future_draft_picks",
                        lambda *a, **k: _FRESH_EXPORT)
    assert server._refresh_mfl_future_picks(MFL_ID) == 2
    assert sorted(p["year"] for p in _stored_snapshot()) == ["2027", "2028"]


def test_snapshot_refresh_uses_the_leagues_own_host_and_season(mem_db,
                                                               monkeypatch):
    _seed_mfl(_STALE, host="www46.myfantasyleague.com")
    seen = {}

    def _fake(league_id, year, host, **kw):
        seen.update(league_id=league_id, year=year, host=host)
        return _FRESH_EXPORT

    monkeypatch.setattr(mfl_module, "fetch_future_draft_picks", _fake)
    server._refresh_mfl_future_picks(MFL_ID)
    assert seen == {"league_id": MFL_ID, "year": 2026,
                    "host": "www46.myfantasyleague.com"}


def test_snapshot_refresh_never_wipes_when_mfl_is_unavailable(mem_db,
                                                              monkeypatch):
    """#220's lesson. `{}` means unavailable — MFL down, or (if the export
    ever turned out to be auth-gated) rejected without a cookie. Keep the
    stored snapshot rather than replace-syncing it to empty; the
    verdict-gated exclusion still covers the current season on its own."""
    _seed_mfl(_STALE)
    monkeypatch.setattr(mfl_module, "fetch_future_draft_picks",
                        lambda *a, **k: {})
    assert server._refresh_mfl_future_picks(MFL_ID) is None
    assert _stored_snapshot() == _STALE


def test_snapshot_refresh_writes_a_genuinely_empty_grid(mem_db, monkeypatch):
    """A present-but-empty export is real data (every future pick spent) and
    is distinguishable from a flake — so it IS written."""
    _seed_mfl(_STALE)
    monkeypatch.setattr(mfl_module, "fetch_future_draft_picks",
                        lambda *a, **k: {"futureDraftPicks": {}})
    assert server._refresh_mfl_future_picks(MFL_ID) == 0
    assert _stored_snapshot() == []


def test_snapshot_refresh_abstains_without_a_host(mem_db, monkeypatch):
    _seed_mfl(_STALE, host=None)
    monkeypatch.setattr(mfl_module, "fetch_future_draft_picks",
                        lambda *a, **k: pytest.fail("must not fetch"))
    assert server._refresh_mfl_future_picks(MFL_ID) is None


def test_snapshot_refresh_is_a_no_op_for_a_non_mfl_league(mem_db):
    _seed_league(platform="sleeper")
    assert server._refresh_mfl_future_picks(LEAGUE_ID) is None


def test_status_refresh_piggybacks_the_snapshot_and_renormalizes(mem_db,
                                                                 monkeypatch):
    """One pass, one cadence: verdict → snapshot → owned picks."""
    _seed_mfl(_STALE)
    _seed_mfl_members()
    monkeypatch.setattr(mfl_module, "fetch_future_draft_picks",
                        lambda *a, **k: _FRESH_EXPORT)
    monkeypatch.setattr(mfl_module, "fetch_draft_results",
                        lambda *a, **k: _mfl_grid(12))
    monkeypatch.setattr(server, "is_enabled", lambda flag: True)
    v = server._refresh_league_draft_status(MFL_ID)
    assert (v.status, v.source) == (ds.DRAFTED, ds.SRC_MFL)
    assert sorted(p["year"] for p in _stored_snapshot()) == ["2027", "2028"]
    seasons = sorted(p["season"] for p in db_module.load_draft_picks(MFL_ID))
    assert seasons == [2027, 2028]        # 2026 never reaches draft_picks


def test_status_refresh_renormalizes_even_when_the_snapshot_fetch_fails(
        mem_db, monkeypatch):
    """The exclusion-only fallback: with the export unavailable the verdict
    alone still drops the drafted season, which is the reported bug."""
    _seed_mfl(_STALE)
    _seed_mfl_members()
    monkeypatch.setattr(mfl_module, "fetch_future_draft_picks",
                        lambda *a, **k: {})
    monkeypatch.setattr(mfl_module, "fetch_draft_results",
                        lambda *a, **k: _mfl_grid(12))
    monkeypatch.setattr(server, "is_enabled", lambda flag: True)
    assert server._refresh_league_draft_status(MFL_ID).status == ds.DRAFTED
    assert _stored_snapshot() == _STALE          # snapshot untouched
    seasons = sorted(p["season"] for p in db_module.load_draft_picks(MFL_ID))
    assert seasons == [2027]                     # …but 2026 is excluded


def test_status_refresh_keeps_the_current_season_when_not_drafted(
        mem_db, monkeypatch):
    """Fail-safe end to end: an in-progress MFL draft keeps 2026 picks."""
    _seed_mfl(_STALE)
    _seed_mfl_members()
    monkeypatch.setattr(mfl_module, "fetch_future_draft_picks",
                        lambda *a, **k: {})
    monkeypatch.setattr(mfl_module, "fetch_draft_results",
                        lambda *a, **k: _mfl_grid(1))
    monkeypatch.setattr(server, "is_enabled", lambda flag: True)
    assert server._refresh_league_draft_status(MFL_ID).status == ds.NOT_DRAFTED
    seasons = sorted(p["season"] for p in db_module.load_draft_picks(MFL_ID))
    assert seasons == [2026, 2027]


def test_status_refresh_leaves_the_mfl_path_alone_for_a_sleeper_league(
        mem_db, monkeypatch):
    """No change for Sleeper leagues — the whole MFL branch is platform-gated
    (Sleeper's #228 exclusion still reads its own live drafts fetch)."""
    _seed_league()
    _patch_sleeper(monkeypatch,
                   [{"draft_id": "d1", "status": "complete", "season": "2026",
                     "last_picked": 1, "settings": {"rounds": 4}}], [[]])
    monkeypatch.setattr(server, "_refresh_mfl_future_picks",
                        lambda lid: pytest.fail("MFL path must not run"))
    monkeypatch.setattr(server, "_sync_mfl_owned_picks",
                        lambda lid: pytest.fail("MFL path must not run"))
    assert server._refresh_league_draft_status(LEAGUE_ID).status == ds.DRAFTED


# ── Inactive-with-team retention (G-008 class, 2026-08-16) ─────────────────
# Sleeper marks rostered-but-unavailable players (IR / suspended / NFI)
# "Inactive" while they still hold a team; the sync must keep them (they are
# real dynasty assets — Ricky Pearsall vanished this way). Only teamless
# non-Active veterans (retired / out of the league) are removed.

def test_sync_players_keeps_rostered_inactive_veteran(mem_db):
    db_module.sync_players(dict([
        _sleeper_player("p_ir", "Ricky Pearsall", 2, "SF", None,
                        status="Inactive", pos="WR"),
        _sleeper_player("p_ret", "Retired Guy", 8, None, None,
                        status="Inactive", pos="WR"),
        _sleeper_player("p_act", "Active Guy", 3, "KC", None,
                        status="Active", pos="WR"),
        _sleeper_player("p_rook", "Prospect Kid", None, None, None,
                        status="Inactive", pos="WR"),
    ]))
    with mem_db.connect() as conn:
        got = {r.player_id for r in conn.execute(
            select(players_table.c.player_id)).fetchall()}
    assert "p_ir" in got            # rostered Inactive: KEPT (the fix)
    assert "p_act" in got           # Active: kept
    assert "p_rook" in got          # years_exp None prospect: kept
    assert "p_ret" not in got       # teamless Inactive veteran: dropped
