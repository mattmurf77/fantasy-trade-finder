"""draft-extensions W3 M-D — live offline pick recording.

Plan `docs/plans/draft-extensions/plan.md` §6.5 M-D + the operator's task
brief (2026-08-08, "Build W3 milestone M-D"); LLD §2.6/§3.2/§4.6; the
delivered M-A/M-C contracts in `docs/plans/draft-extensions/build-w3-ma-mb.md`
/ `build-w3-mc.md`.

M-A/M-B/M-C shipped ownership assignment; the only thing missing was
recording WHAT HAPPENED during a real off-platform draft. This wave adds a
new table, `recorded_picks`, and everything it can break is pinned here:

  * **D18 / INV-6.** `overall` never reaches `draft_picks` — no write path
    into `draft_picks` carries an `overall` key, and neither
    `record_draft_picks` nor `void_recorded_pick` can reach `draft_picks`,
    `sync_draft_picks`, `replace_draft_picks` or `leagues.draft_status*` at
    all (AST).
  * **Idempotency (plan §6.5).** `(league_id, season, overall)` is the
    offline-queue idempotency key. A replayed batch produces `deduped`,
    never a duplicate row and never a 4xx — replaying twice is byte-identical
    to replaying once.
  * **Non-destructive undo.** `voided_at`, never a DELETE. Re-recording an
    already-voided slot revives it in place — never a second row.
  * **Board wiring.** Recorded picks feed `GET /api/draft/board`'s ESPN
    branch `picks[]` (and subtract from `undrafted[]`) through the SAME
    `assigned_board` renderer every other platform's board goes through.
  * **Flag off ⇒ byte-identical.** Both routes 404 before any session work;
    the board reads ZERO rows from `recorded_picks` regardless of what the
    table holds.
"""
import ast
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine, select

import backend.database as db
import backend.draft_board_service as dbs
import backend.feature_flags as ff
import backend.server as server
from backend.database import (
    metadata, leagues_table, league_members_table, players_table,
    recorded_picks_table,
)

REPO = Path(__file__).resolve().parents[2]
DATABASE_PATH = REPO / "backend" / "database.py"

LEAGUE = "1099887766554433221"          # numeric — an ESPN-shaped league id
ME = "u1"
MEMBERS = ["u1", "u2", "u3", "u4"]
NAMES = {u: f"Team {u}" for u in MEMBERS}
SEASON = 2026
TOKEN = "test-token-w3-md"
OUTSIDER_TOKEN = "test-token-w3-md-outsider"


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
        # p1..p6 — six rookies. p1-p4 get recorded; p5-p6 stay undrafted.
        for i in range(1, 7):
            pid = f"p{i}"
            conn.execute(players_table.insert().values(
                player_id=pid, full_name=f"Rookie {i}", first_name="Rookie",
                last_name=str(i), position="WR", team="ARI",
                rookie_year=str(SEASON), years_exp=0, status="Active"))
    db.invalidate_pick_assignment_cache(LEAGUE)
    server._invalidate_draft_context_cache()
    server._invalidate_rookie_ids_memo()
    yield engine
    db.invalidate_pick_assignment_cache(LEAGUE)
    server._invalidate_draft_context_cache()
    server._invalidate_rookie_ids_memo()


class _League:
    league_id = LEAGUE
    platform = "espn"
    members = ()


def _make_session(user_id: str) -> dict:
    return {
        "user_id": user_id, "league": _League(), "players": [],
        "services": {"1qb_ppr": MagicMock()}, "service": MagicMock(),
        "trade_svc": MagicMock(), "active_format": "1qb_ppr",
        "last_active": 0.0,
    }


@pytest.fixture()
def client(mem_db, monkeypatch):
    server.app.config["TESTING"] = True
    # The board route builds a universal consensus pool for `basis=consensus`
    # — stubbed so the route never depends on the process-wide pool build
    # (the `test_mc_01b` precedent in test_pick_assignment_tradeable.py).
    monkeypatch.setattr(server, "_ensure_universal_pools", lambda: None)
    monkeypatch.setitem(server.g_universal_by_format, "1qb_ppr",
                        {"players": [], "seed": {}})
    with server._sessions_lock:
        server._sessions[TOKEN] = _make_session(ME)
        server._sessions[OUTSIDER_TOKEN] = _make_session("not-a-member")
    try:
        yield server.app.test_client()
    finally:
        with server._sessions_lock:
            server._sessions.pop(TOKEN, None)
            server._sessions.pop(OUTSIDER_TOKEN, None)


@pytest.fixture()
def flags():
    """Pin the flag map; `set(**kw)` re-pins mid-test."""
    saved = ff._flags_cache

    def _set(**kw):
        ff._flags_cache = {**ff.DEFAULT_FLAGS, "draft.room": True,
                           "picks.assign": True, "draft.manual_picks": True,
                           **kw}
        return ff._flags_cache

    _set()
    try:
        yield _set
    finally:
        ff._flags_cache = saved


def _hdr(token=TOKEN):
    return {"X-Session-Token": token, "Content-Type": "application/json"}


def _seed_grid(client, rounds=1, **body):
    return client.post("/api/league/pick-assignments/order", headers=_hdr(),
                       data=json.dumps({"league_id": LEAGUE, "rounds": rounds,
                                        **body}))


def _record(client, picks, season=SEASON, token=TOKEN, **body):
    return client.post("/api/league/recorded-picks", headers=_hdr(token),
                       data=json.dumps({"league_id": LEAGUE, "season": season,
                                        "picks": picks, **body}))


def _void(client, overall, season=SEASON, token=TOKEN):
    return client.post("/api/league/recorded-picks/void", headers=_hdr(token),
                       data=json.dumps({"league_id": LEAGUE, "season": season,
                                        "overall": overall}))


def _board(client):
    return client.get(f"/api/draft/board?league_id={LEAGUE}", headers=_hdr())


def _pick(overall, player_id, team=None, event_id=None):
    team = team or f"u{overall}"
    return {"event_id": event_id or f"evt-{overall}-{player_id}",
            "overall": overall, "round": 1, "slot": overall,
            "picking_team_id": team, "player_id": player_id,
            "client_ts": "2026-08-08T18:02:07.113Z"}


_FULL_BATCH = [_pick(1, "p1"), _pick(2, "p2"), _pick(3, "p3"), _pick(4, "p4")]


def _raw_rows(engine):
    with engine.connect() as conn:
        rows = conn.execute(select(recorded_picks_table)
                            .where(recorded_picks_table.c.league_id == LEAGUE)
                            .order_by(recorded_picks_table.c.overall)).fetchall()
    return [dict(r._mapping) for r in rows]


# ---------------------------------------------------------------------------
# Flag off — byte-identical, zero writes, no entry point
# ---------------------------------------------------------------------------

def test_flag_off_both_routes_404_before_any_session_work(client, flags, mem_db):
    flags(**{"draft.manual_picks": False})
    r1 = _record(client, _FULL_BATCH)
    assert r1.status_code == 404
    assert r1.get_json() == {"error": "feature_disabled"}
    r2 = _void(client, 1)
    assert r2.status_code == 404
    assert r2.get_json() == {"error": "feature_disabled"}
    assert _raw_rows(mem_db) == []


def test_flag_off_board_is_byte_identical_even_with_rows_in_the_table(
        client, flags, mem_db):
    """Zero tolerance: the READ is gated too, not just the write routes — a
    row sitting in `recorded_picks` (e.g. from a flag that was flipped on and
    back off) must not leak into a flag-off board."""
    flags(**{"draft.manual_picks": False})
    _seed_grid(client, rounds=1)
    before = _board(client).get_json()

    # Insert directly, bypassing the (correctly) 404'd route.
    db.record_draft_picks(LEAGUE, SEASON, _FULL_BATCH, recorded_by=ME)
    assert _raw_rows(mem_db)                       # really is in the table

    after = _board(client).get_json()
    before.pop("as_of"), after.pop("as_of")
    assert after == before
    assert after["picks"] == []


# ---------------------------------------------------------------------------
# Recording — accept, project into the board, subtract from undrafted
# ---------------------------------------------------------------------------

def test_record_batch_accepts_and_projects_into_the_board(client, flags):
    _seed_grid(client, rounds=1)
    r = _record(client, _FULL_BATCH[:2])
    assert r.status_code == 200
    body = r.get_json()
    assert body == {"accepted": 2, "deduped": 0, "rejected": []}

    board = _board(client).get_json()
    assert board["state"] == "live"
    picks_by_pid = {p["player_id"]: p for p in board["picks"]}
    assert set(picks_by_pid) == {"p1", "p2"}
    p1 = picks_by_pid["p1"]
    assert p1["round"] == 1 and p1["pick_no"] == 1 and p1["slot"] == 1
    assert p1["picked_by_user_id"] == "u1"
    assert p1["name"] == "Rookie 1" and p1["position"] == "WR"
    undrafted_ids = {r["player_id"] for r in board["undrafted"]}
    assert "p1" not in undrafted_ids and "p2" not in undrafted_ids
    assert {"p3", "p4", "p5", "p6"} <= undrafted_ids


def test_recording_every_slot_completes_the_board(client, flags):
    _seed_grid(client, rounds=1)
    r = _record(client, _FULL_BATCH)
    assert r.get_json() == {"accepted": 4, "deduped": 0, "rejected": []}
    board = _board(client).get_json()
    assert board["state"] == "complete"
    assert len(board["picks"]) == 4 == len(board["order"])
    assert board["undrafted"] and all(
        p["player_id"] not in {"p1", "p2", "p3", "p4"}
        for p in board["undrafted"])


# ---------------------------------------------------------------------------
# Idempotency — the offline queue's whole contract (INV-12, plan §6.5)
# ---------------------------------------------------------------------------

def test_replay_is_idempotent_twice_with_zero_duplicates(client, flags, mem_db):
    """A full airplane-mode draft, replayed on reconnect TWICE, must land on
    identical server state with zero duplicate rows — the wave's zero-
    tolerance bar."""
    _seed_grid(client, rounds=1)
    first = _record(client, _FULL_BATCH).get_json()
    assert first == {"accepted": 4, "deduped": 0, "rejected": []}
    board_after_first = _board(client).get_json()

    second = _record(client, _FULL_BATCH).get_json()
    assert second == {"accepted": 0, "deduped": 4, "rejected": []}
    third = _record(client, _FULL_BATCH).get_json()
    assert third == {"accepted": 0, "deduped": 4, "rejected": []}

    assert len(_raw_rows(mem_db)) == 4             # never a duplicate row
    board_after_replay = _board(client).get_json()
    board_after_first.pop("as_of"), board_after_replay.pop("as_of")
    assert board_after_replay == board_after_first


def test_two_devices_recording_the_same_pick_dedupe_on_overall_not_event_id(
        client, flags, mem_db):
    """RC-6 — different devices never share a client uuid, so the SERVER key
    is (league, season, overall), never event_id."""
    _seed_grid(client, rounds=1)
    device_a = [_pick(1, "p1", event_id="device-a-uuid")]
    device_b = [_pick(1, "p1", event_id="device-b-uuid")]
    assert _record(client, device_a).get_json()["accepted"] == 1
    assert _record(client, device_b).get_json() == {
        "accepted": 0, "deduped": 1, "rejected": []}
    assert len(_raw_rows(mem_db)) == 1


# ---------------------------------------------------------------------------
# Correction — a different player at an already-recorded overall
# ---------------------------------------------------------------------------

def test_correction_updates_in_place_never_a_second_row(client, flags, mem_db):
    _seed_grid(client, rounds=1)
    _record(client, [_pick(1, "p1")])
    result = _record(client, [_pick(1, "p5")])       # the grid was wrong
    assert result.get_json() == {"accepted": 1, "deduped": 0, "rejected": []}

    rows = _raw_rows(mem_db)
    assert len(rows) == 1                            # UPDATE in place
    assert rows[0]["player_id"] == "p5"

    board = _board(client).get_json()
    pids = {p["player_id"] for p in board["picks"]}
    assert pids == {"p5"}
    assert "p1" in {r["player_id"] for r in board["undrafted"]}


# ---------------------------------------------------------------------------
# Void — non-destructive, and reversible by re-recording (undo the undo)
# ---------------------------------------------------------------------------

def test_void_is_non_destructive_and_re_recording_revives_it(
        client, flags, mem_db):
    _seed_grid(client, rounds=1)
    _record(client, [_pick(1, "p1")])

    v = _void(client, 1)
    assert v.status_code == 200
    assert v.get_json()["ok"] is True

    raw = _raw_rows(mem_db)
    assert len(raw) == 1                             # never a DELETE
    assert raw[0]["voided_at"] is not None
    assert db.load_recorded_picks(LEAGUE, SEASON) == []  # excluded when live

    board = _board(client).get_json()
    assert board["picks"] == []
    assert "p1" in {r["player_id"] for r in board["undrafted"]}

    # Undo the undo: re-recording the SAME pick revives the row in place.
    revive = _record(client, [_pick(1, "p1")])
    assert revive.get_json() == {"accepted": 1, "deduped": 0, "rejected": []}
    raw2 = _raw_rows(mem_db)
    assert len(raw2) == 1                            # still one row
    assert raw2[0]["voided_at"] is None
    board2 = _board(client).get_json()
    assert {p["player_id"] for p in board2["picks"]} == {"p1"}


def test_void_of_a_never_recorded_slot_is_pick_not_found(client, flags):
    _seed_grid(client, rounds=1)
    r = _void(client, 1)
    assert r.status_code == 404
    assert r.get_json() == {"error": "pick_not_found"}


# ---------------------------------------------------------------------------
# Validation — rejected reasons, never a partial write
# ---------------------------------------------------------------------------

def test_unknown_player_is_rejected(client, flags, mem_db):
    _seed_grid(client, rounds=1)
    r = _record(client, [_pick(1, "ghost-player")])
    assert r.get_json() == {
        "accepted": 0, "deduped": 0,
        "rejected": [{"index": 0, "reason": "unknown_player"}]}
    assert _raw_rows(mem_db) == []


def test_picking_team_not_in_league_is_rejected(client, flags, mem_db):
    _seed_grid(client, rounds=1)
    r = _record(client, [_pick(1, "p1", team="ghost-team")])
    assert r.get_json() == {
        "accepted": 0, "deduped": 0,
        "rejected": [{"index": 0, "reason": "not_in_league"}]}
    assert _raw_rows(mem_db) == []


def test_slot_out_of_range_is_rejected(client, flags, mem_db):
    _seed_grid(client, rounds=1)          # the grid has exactly 1 round
    bad_round = {**_pick(5, "p1"), "round": 5, "slot": 1, "overall": 5}
    r = _record(client, [bad_round])
    assert r.get_json() == {
        "accepted": 0, "deduped": 0,
        "rejected": [{"index": 0, "reason": "slot_out_of_range"}]}
    assert _raw_rows(mem_db) == []


def test_non_positive_overall_is_rejected(client, flags, mem_db):
    _seed_grid(client, rounds=1)
    bad = {**_pick(1, "p1"), "overall": 0}
    r = _record(client, [bad])
    assert r.get_json()["rejected"] == [{"index": 0, "reason": "slot_out_of_range"}]


def test_a_batch_never_partially_corrupts_valid_and_invalid_rows_together(
        client, flags, mem_db):
    _seed_grid(client, rounds=1)
    batch = [_pick(1, "p1"), _pick(2, "ghost-player"), _pick(3, "p3")]
    r = _record(client, batch)
    body = r.get_json()
    assert body["accepted"] == 2 and body["deduped"] == 0
    assert body["rejected"] == [{"index": 1, "reason": "unknown_player"}]
    assert {row["player_id"] for row in _raw_rows(mem_db)} == {"p1", "p3"}


def test_batch_too_large_is_refused_with_zero_writes(client, flags, mem_db):
    _seed_grid(client, rounds=8)
    oversized = [_pick(i, "p1", team="u1") for i in range(1, 52)]
    r = _record(client, oversized)
    assert r.status_code == 400
    assert r.get_json()["error"] == "batch_too_large"
    assert _raw_rows(mem_db) == []


# ---------------------------------------------------------------------------
# Membership
# ---------------------------------------------------------------------------

def test_a_non_member_cannot_record_or_void(client, flags, mem_db):
    _seed_grid(client, rounds=1)
    r = _record(client, [_pick(1, "p1")], token=OUTSIDER_TOKEN)
    assert r.status_code == 403
    assert r.get_json() == {"error": "not_in_league"}
    _record(client, [_pick(1, "p1")])               # a real member records it
    v = _void(client, 1, token=OUTSIDER_TOKEN)
    assert v.status_code == 403


def test_any_member_may_record_no_designated_recorder(client, flags):
    """Plan §6.5: 'One recorder for all 48 picks, any linked user.'"""
    _seed_grid(client, rounds=1)
    session2 = "test-token-w3-md-member2"
    with server._sessions_lock:
        server._sessions[session2] = _make_session("u2")
    try:
        r = client.post("/api/league/recorded-picks", headers=_hdr(session2),
                        data=json.dumps({"league_id": LEAGUE, "season": SEASON,
                                         "picks": [_pick(1, "p1")]}))
        assert r.status_code == 200
        assert r.get_json()["accepted"] == 1
    finally:
        with server._sessions_lock:
            server._sessions.pop(session2, None)


# ---------------------------------------------------------------------------
# D18 / INV-6 — `overall` never reaches `draft_picks`; O9 survives
# ---------------------------------------------------------------------------

def _function_source_calls(tree: ast.AST, fn_name: str) -> set[str]:
    """Every dotted/bare call name reachable inside function `fn_name`."""
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == fn_name:
            calls = set()
            names = set()
            for sub in ast.walk(node):
                if isinstance(sub, ast.Call):
                    f = sub.func
                    if isinstance(f, ast.Name):
                        calls.add(f.id)
                    elif isinstance(f, ast.Attribute):
                        calls.add(f.attr)
                if isinstance(sub, ast.Name):
                    names.add(sub.id)
                if isinstance(sub, ast.Attribute):
                    names.add(sub.attr)
            return calls | names
    raise AssertionError(f"{fn_name} not found in database.py")


_FORBIDDEN_SYMBOLS = frozenset({
    "draft_picks_table", "replace_draft_picks", "sync_draft_picks",
    "leagues_table", "set_league_draft_status",
})


def test_d18_recording_never_touches_draft_picks_or_draft_status():
    """AST containment — the same discipline as `test_m3_07`/D12's
    `test_w3_02`. `record_draft_picks` and `void_recorded_pick` are the
    entire write surface for W3 M-D; neither may reference `draft_picks_table`,
    `leagues_table`, or the platform-writer functions that touch them."""
    tree = ast.parse(DATABASE_PATH.read_text())
    for fn in ("record_draft_picks", "void_recorded_pick"):
        symbols = _function_source_calls(tree, fn)
        hit = symbols & _FORBIDDEN_SYMBOLS
        assert not hit, f"{fn} references forbidden symbol(s): {sorted(hit)}"


def test_d18_runtime_no_draft_picks_row_gains_an_overall_key(client, flags, mem_db):
    """Behavioral pin, not just source-text: recording a full batch must not
    add or change any `draft_picks` row, and `draft_picks` has no `overall`
    column at all."""
    from backend.database import draft_picks_table
    assert "overall" not in draft_picks_table.c
    _seed_grid(client, rounds=1)
    with mem_db.connect() as conn:
        before = conn.execute(select(draft_picks_table)
                              .where(draft_picks_table.c.league_id == LEAGUE)
                              ).fetchall()
    _record(client, _FULL_BATCH)
    with mem_db.connect() as conn:
        after = conn.execute(select(draft_picks_table)
                             .where(draft_picks_table.c.league_id == LEAGUE)
                             ).fetchall()
    assert [dict(r._mapping) for r in before] == [dict(r._mapping) for r in after]


def test_o9_survives_recording_never_writes_draft_status(client, flags, mem_db):
    _seed_grid(client, rounds=1)
    with mem_db.connect() as conn:
        before = conn.execute(
            select(leagues_table.c.draft_status,
                  leagues_table.c.draft_status_confidence,
                  leagues_table.c.draft_status_checked_at)
            .where(leagues_table.c.sleeper_league_id == LEAGUE)).fetchone()
    _record(client, _FULL_BATCH)
    _void(client, 1)
    with mem_db.connect() as conn:
        after = conn.execute(
            select(leagues_table.c.draft_status,
                  leagues_table.c.draft_status_confidence,
                  leagues_table.c.draft_status_checked_at)
            .where(leagues_table.c.sleeper_league_id == LEAGUE)).fetchone()
    assert tuple(before) == tuple(after)


# ---------------------------------------------------------------------------
# Unit-level board wiring (no Flask) — mirrors test_draft_board.py's W3 M-B
# pattern for `assigned_board`
# ---------------------------------------------------------------------------

class _Fetchers:
    def __init__(self, rookie_ids, player_rows):
        self._ids = set(rookie_ids)
        self._rows = player_rows

    def rookie_ids(self, season):
        return set(self._ids)

    def players(self, ids):
        return {pid: self._rows[pid] for pid in ids if pid in self._rows}


def _grid(rounds=1, teams=4):
    slots = []
    for rnd in range(1, rounds + 1):
        for slot in range(1, teams + 1):
            slots.append({
                "round": rnd, "slot": slot,
                "owner_user_id": f"u{slot}", "owner_username": f"Team u{slot}",
                "original_user_id": f"u{slot}", "original_username": f"Team u{slot}",
                "is_traded": False,
            })
    return dbs.AssignmentGrid(rounds=rounds, teams=teams, order_type="linear",
                              slots=tuple(slots))


def test_recorded_picks_projection_shape_matches_the_shipped_pick_schema():
    fetchers = _Fetchers({"p1"}, {
        "p1": {"full_name": "Rookie One", "position": "wr", "team": "ARI"}})
    recorded = [{"round": 1, "slot": 1, "overall": 1, "player_id": "p1",
                "picking_team_id": "u1", "recorded_at": "2026-08-08T00:00:00+00:00"}]
    out = dbs.assigned_board(
        dbs.BoardRequest(league_id=LEAGUE, platform="espn", season=2026),
        grid=_grid(), fetchers=fetchers, recorded=recorded)
    assert len(out["picks"]) == 1
    p = out["picks"][0]
    assert set(p) == {"round", "pick_no", "slot", "player_id", "name",
                      "position", "team", "picked_by_user_id", "picked_at"}
    assert p["pick_no"] == 1 and p["name"] == "Rookie One" and p["position"] == "WR"
    assert p["picked_by_user_id"] == "u1"


def test_empty_recorded_is_the_exact_m_b_payload():
    """`recorded=()` (the default) must render exactly what M-B shipped."""
    fetchers = _Fetchers(set(), {})
    with_default = dbs.assigned_board(
        dbs.BoardRequest(league_id=LEAGUE, platform="espn", season=2026),
        grid=_grid(), fetchers=fetchers)
    with_empty = dbs.assigned_board(
        dbs.BoardRequest(league_id=LEAGUE, platform="espn", season=2026),
        grid=_grid(), fetchers=fetchers, recorded=[])
    with_default.pop("as_of"), with_empty.pop("as_of")
    assert with_default == with_empty
    assert with_default["picks"] == []
    assert with_default["state"] == "upcoming"


# ---------------------------------------------------------------------------
# The flag itself — 4-touch, lands OFF
# ---------------------------------------------------------------------------

def test_manual_picks_flag_is_registered_lands_off_and_is_mirrored():
    assert "draft.manual_picks" in ff.FLAG_KEYS
    assert ff.DEFAULT_FLAGS["draft.manual_picks"] is False
    features = json.loads((REPO / "config/features.json").read_text())
    release = json.loads(
        (REPO / "backend/tests/fixtures/flags/release.json").read_text())
    assert "draft.manual_picks" in features
    assert "draft.manual_picks" in release
    assert features["draft.manual_picks"] == release["draft.manual_picks"]
    assert features["draft.manual_picks"] is False
