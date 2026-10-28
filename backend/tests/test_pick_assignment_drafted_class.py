"""C5 — once the league's rookie draft is past, the ESPN pick-assignment grid
starts at the next class.

Scope: `docs/plans/draft-extensions/scope-espn-grid-drafted-class.md`.

The signal is the CACHED verdict on the leagues row, written here through the
real setter `set_league_draft_status` (the one `_refresh_league_draft_status`
persists through) and read by `server._assignment_first_season` through the
shared `_current_season_picks_visible` predicate. Only `drafted` moves the
grid. Every other verdict is byte-identical to before (the #228 fail-safe).

The spent class is HIDDEN, never deleted, and seeded prices stay relative to
the league season.

Real routes, in-memory SQLite (the live DB is never opened). Harness mirrors
`test_pick_assignment.py`.
"""
import json
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, delete

import backend.database as db
import backend.feature_flags as ff
import backend.server as server
from backend.database import metadata, leagues_table, league_members_table
from backend.pick_values import pick_pool_value

LEAGUE = "1099887766554433221"          # numeric — an ESPN-shaped league id
ME = "u1"
MEMBERS = ["u1", "u2", "u3", "u4"]
NAMES = {u: f"Team {u}" for u in MEMBERS}
SEASON = 2026
ROUNDS = 4
FMT = "1qb_ppr"
TOKEN = "test-token-c5-drafted-class"
TOTAL = ROUNDS * len(MEMBERS) * 4       # progress.total: 4 classes, unchanged


# ---------------------------------------------------------------------------
# harness — in-memory SQLite throughout; data/trade_finder.db is never opened
# ---------------------------------------------------------------------------

@pytest.fixture()
def mem_db(monkeypatch):
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False})
    metadata.create_all(engine)
    monkeypatch.setattr(db, "engine", engine)
    with engine.begin() as conn:
        conn.execute(leagues_table.insert().values(
            sleeper_league_id=LEAGUE, user_id=ME, name="Sunday Sickos",
            season=str(SEASON), platform="espn", total_rosters=len(MEMBERS)))
        for uid in MEMBERS:
            conn.execute(league_members_table.insert().values(
                league_id=LEAGUE, user_id=uid, username=NAMES[uid],
                display_name=NAMES[uid], roster_data="[]"))
    db.invalidate_pick_assignment_cache(LEAGUE)
    server._invalidate_draft_context_cache()
    yield engine
    db.invalidate_pick_assignment_cache(LEAGUE)
    server._invalidate_draft_context_cache()


class _League:
    league_id = LEAGUE
    platform = "espn"
    members = ()


@pytest.fixture()
def client(mem_db):
    server.app.config["TESTING"] = True
    sess = {"verified": True,
        "user_id": ME, "league": _League(), "players": [],
        "services": {FMT: MagicMock()}, "service": MagicMock(),
        "trade_svc": MagicMock(), "active_format": FMT,
        "last_active": 0.0,
    }
    with server._sessions_lock:
        server._sessions[TOKEN] = sess
    try:
        yield server.app.test_client()
    finally:
        with server._sessions_lock:
            server._sessions.pop(TOKEN, None)


@pytest.fixture()
def flag_on():
    saved = ff._flags_cache
    ff._flags_cache = {**ff.DEFAULT_FLAGS, "picks.assign": True,
                       "draft.room": True}
    try:
        yield
    finally:
        ff._flags_cache = saved


def _hdr():
    return {"X-Session-Token": TOKEN, "Content-Type": "application/json"}


def _seed(client, **body):
    return client.post("/api/league/pick-assignments/order", headers=_hdr(),
                       data=json.dumps({"league_id": LEAGUE, **body}))


def _get(client):
    r = client.get(f"/api/league/pick-assignments?league_id={LEAGUE}",
                   headers=_hdr())
    assert r.status_code == 200, r.get_json()
    return r.get_json()


def _put(client, pick_id, **body):
    return client.put(f"/api/league/pick-assignments/{pick_id}", headers=_hdr(),
                      data=json.dumps({"league_id": LEAGUE, **body}))


def _verdict(status, confidence):
    """The real setter — what `_refresh_league_draft_status` persists through."""
    db.set_league_draft_status(LEAGUE, status, confidence)


def _seasons(body):
    return [s["season"] for s in body["seasons"]]


def _slots(body, season=None):
    return {s["pick_id"]: s for yr in body["seasons"] for s in yr["slots"]
            if season is None or s["season"] == season}


def _rows(season=None):
    """Every stored user row (contested included), minus the surrogate `id`."""
    rows = db.load_draft_picks(league_id=LEAGUE, source=db.PICK_SOURCE_USER,
                               include_contested=True)
    return {r["pick_id"]: {k: v for k, v in r.items() if k != "id"}
            for r in rows if season is None or int(r["season"]) == season}


def _reassign(client, pick_id, owner):
    slot = _slots(_get(client))[pick_id]
    r = _put(client, pick_id, owner_user_id=owner,
             if_assigned_at=slot["assigned_at"])
    assert r.status_code == 200, r.get_json()


PICK_2026 = db.make_pick_id(LEAGUE, SEASON, 1, "1")
PICK_2027 = db.make_pick_id(LEAGUE, SEASON + 1, 2, "2")


# ---------------------------------------------------------------------------
# D1–D3 — every non-drafted verdict leaves the grid byte-identical
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("status, confidence", [
    pytest.param("not_drafted", "high", id="D1-not_drafted"),
    pytest.param("unknown", "low", id="D2-unknown"),
    pytest.param(None, None, id="D3-never-checked"),
    pytest.param("not_drafted", "low", id="D3-low-confidence"),
])
def test_d1_d3_non_drafted_verdicts_keep_the_current_season(
        client, flag_on, mem_db, status, confidence):
    assert _seed(client, rounds=ROUNDS).status_code == 200
    baseline = _get(client)                         # NULL verdict = today
    _verdict(status, confidence)
    body = _get(client)

    assert _seasons(body) == [SEASON + i for i in range(4)]
    assert body["current_season"] == SEASON
    assert body == baseline
    assert body["progress"]["assigned"] == body["progress"]["total"] == TOTAL


def test_d3_no_leagues_row_keeps_the_current_season(client, flag_on, mem_db):
    """No leagues row: the session league answers, and no verdict exists."""
    assert _seed(client, rounds=ROUNDS).status_code == 200
    baseline = _get(client)
    with db.engine.begin() as conn:
        conn.execute(delete(leagues_table)
                     .where(leagues_table.c.sleeper_league_id == LEAGUE))
    assert db.get_league_draft_context(LEAGUE) is None
    body = _get(client)
    assert _seasons(body) == [SEASON + i for i in range(4)]
    assert body["current_season"] == SEASON
    assert body == baseline


def test_helper_fail_safes(mem_db):
    """The helper itself: only a drafted verdict for THIS season moves it."""
    assert server._assignment_first_season(LEAGUE, SEASON) == SEASON
    _verdict("drafted", "medium")
    assert server._assignment_first_season(LEAGUE, SEASON) == SEASON + 1
    # a verdict row for another season never moves this one
    assert server._assignment_first_season(LEAGUE, SEASON - 1) == SEASON - 1
    # a DB error is the fail-safe, never a 5xx
    with patch.object(server, "get_league_draft_context",
                      side_effect=RuntimeError("db down")):
        assert server._assignment_first_season(LEAGUE, SEASON) == SEASON


# ---------------------------------------------------------------------------
# D4 — drafted: the GET hides the spent class
# ---------------------------------------------------------------------------

def test_d4_drafted_get_hides_the_spent_class(client, flag_on, mem_db):
    assert _seed(client, rounds=ROUNDS).status_code == 200
    baseline = _get(client)
    _verdict("drafted", "medium")                   # ESPN rosters heuristic
    body = _get(client)

    assert _seasons(body) == [SEASON + 1, SEASON + 2, SEASON + 3]
    assert body["current_season"] == SEASON
    assert body["progress"]["total"] == baseline["progress"]["total"] == TOTAL
    assert body["progress"]["assigned"] == TOTAL - ROUNDS * len(MEMBERS)
    # the visible classes are served exactly as before
    for yr in (SEASON + 1, SEASON + 2, SEASON + 3):
        assert _slots(body, yr) == _slots(baseline, yr)
    # hidden, not deleted
    assert len(_rows(SEASON)) == ROUNDS * len(MEMBERS)


# ---------------------------------------------------------------------------
# D5 — drafted, re-save the order: next class seeded, spent class KEPT
# ---------------------------------------------------------------------------

def _d5_flow(client):
    """Seed 2026–2029, edit one 2026 and one 2027 slot, flip to drafted,
    re-save the order without reseed. Returns the pre-flip row snapshot."""
    assert _seed(client, rounds=ROUNDS).status_code == 200
    _reassign(client, PICK_2026, "u3")
    _reassign(client, PICK_2027, "u4")
    before = _rows()
    _verdict("drafted", "medium")
    r = _seed(client, rounds=ROUNDS)
    assert r.status_code == 200, r.get_json()
    return before, r.get_json()


def test_d5_drafted_resave_seeds_next_class_and_keeps_the_spent_one(
        client, flag_on, mem_db):
    before, resp = _d5_flow(client)
    body = _get(client)
    assert _seasons(body) == [SEASON + 1, SEASON + 2, SEASON + 3, SEASON + 4]
    assert resp["progress"]["assigned"] == resp["progress"]["total"] == TOTAL

    # 2027–2029 rows are byte-identical, edit included
    for yr in (SEASON + 1, SEASON + 2, SEASON + 3):
        assert _rows(yr) == {k: v for k, v in before.items()
                             if v["season"] == yr}
    assert _rows(SEASON + 1)[PICK_2027]["owner_user_id"] == "u4"

    # the 2026 rows still exist, verbatim (edit included)
    spent = _rows(SEASON)
    assert len(spent) == ROUNDS * len(MEMBERS)
    assert spent == {k: v for k, v in before.items() if v["season"] == SEASON}
    assert spent[PICK_2026]["owner_user_id"] == "u3"


def test_d5_new_class_is_priced_relative_to_the_league_season(
        client, flag_on, mem_db):
    # The price assert can only catch a shifted base when the decay is real.
    assert pick_pool_value(2, 4, FMT) != pick_pool_value(2, 3, FMT)
    _d5_flow(client)
    new = _rows(SEASON + 4)
    assert len(new) == ROUNDS * len(MEMBERS)
    for row in new.values():
        rnd = int(row["round"])
        assert row["pool_value"] == pick_pool_value(rnd, 4, FMT)
        assert row["pick_value"] == db.compute_pick_value(
            rnd, SEASON + 4, SEASON, len(MEMBERS))


# ---------------------------------------------------------------------------
# D6 — drafted, fresh league: the first seed starts at the next class
# ---------------------------------------------------------------------------

def test_d6_drafted_fresh_league_seeds_next_class_priced_from_league_season(
        client, flag_on, mem_db):
    assert pick_pool_value(2, 1, FMT) != pick_pool_value(2, 0, FMT)
    _verdict("drafted", "medium")
    r = _seed(client, rounds=ROUNDS)
    assert r.status_code == 200, r.get_json()

    rows = _rows()
    assert sorted({int(v["season"]) for v in rows.values()}) == [
        SEASON + 1, SEASON + 2, SEASON + 3, SEASON + 4]
    assert len(rows) == TOTAL
    for row in rows.values():
        rnd, yr = int(row["round"]), int(row["season"])
        assert row["pool_value"] == pick_pool_value(rnd, yr - SEASON, FMT)
        assert row["pick_value"] == db.compute_pick_value(
            rnd, yr, SEASON, len(MEMBERS))
    body = _get(client)
    assert _seasons(body) == [SEASON + 1, SEASON + 2, SEASON + 3, SEASON + 4]
    assert body["current_season"] == SEASON


# ---------------------------------------------------------------------------
# D7 — drafted: a PUT on the spent class is refused, the next class is not
# ---------------------------------------------------------------------------

def test_d7_drafted_put_refuses_the_spent_class(client, flag_on, mem_db):
    assert _seed(client, rounds=ROUNDS).status_code == 200
    token_2026 = _rows(SEASON)[PICK_2026]["assigned_at"]
    before = _rows(SEASON)[PICK_2026]
    _verdict("drafted", "medium")

    with patch.object(server, "record_event") as rec:
        r = _put(client, PICK_2026, owner_user_id="u2",
                 if_assigned_at=token_2026)
    assert r.status_code == 404
    assert r.get_json() == {"error": "pick_not_found"}
    assert _rows(SEASON)[PICK_2026] == before
    rec.assert_not_called()

    slot = _slots(_get(client))[PICK_2027]
    r = _put(client, PICK_2027, owner_user_id="u3",
             if_assigned_at=slot["assigned_at"])
    assert r.status_code == 200, r.get_json()
    assert r.get_json()["slot"]["owner_user_id"] == "u3"
    assert _rows(SEASON + 1)[PICK_2027]["owner_user_id"] == "u3"


# ---------------------------------------------------------------------------
# Seeder — kept rows and new rows in ONE write (D5's re-save depends on it)
# ---------------------------------------------------------------------------

def test_seeder_writes_kept_and_new_rows_together(client, flag_on, mem_db):
    """Kept rows come back from the DB with their surrogate `id`; new rows
    have none. One bulk INSERT must take both. Before C5 this failed on any
    re-save that added rows (more rounds, a new member) without `reseed`."""
    assert _seed(client, rounds=2).status_code == 200
    _reassign(client, PICK_2026, "u3")
    kept = _rows()
    r = _seed(client, rounds=ROUNDS)
    assert r.status_code == 200, r.get_json()
    after = _rows()
    assert len(after) == TOTAL
    assert {k: after[k] for k in kept} == kept


# ---------------------------------------------------------------------------
# D8 — the verdict flips back: the hidden class reappears
# ---------------------------------------------------------------------------

def test_d8_verdict_flip_back_restores_the_spent_class(client, flag_on, mem_db):
    before, _resp = _d5_flow(client)
    _verdict("not_drafted", "high")
    body = _get(client)

    assert _seasons(body) == [SEASON + i for i in range(5)]
    assert body["current_season"] == SEASON
    shown = _slots(body, SEASON)
    assert len(shown) == ROUNDS * len(MEMBERS)
    assert shown[PICK_2026]["owner_user_id"] == "u3"
    assert shown[PICK_2026]["assigned_at"] == before[PICK_2026]["assigned_at"]
