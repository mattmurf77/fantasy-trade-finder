"""FB-328 — mock drafts use the league's REAL assigned/traded picks.

Spec: ``docs/feedback/items/328-mock-draft-pick-assignment/`` (prd.md §6.1,
lld-delta.md §2). QA regime D-056: pytest + structural checks; every
behavioral test below names its sabotage (SAB-A..SAB-H, prd §6.1) and was
proven-to-fail under it before the build landed.

  T-1   ESPN seeded grid: order = stored round-1 order ("assigned"),
        traded slots overlay via owner_of, ownership_source "user",
        settings_echo.type = grid order_type            [SAB-A, SAB-F]
  T-2   same fixture, manual mode: acquiring team on the clock  [SAB-A]
  T-3   MFL store: overlay anchored to the original owner's shuffled slot;
        seed→order determinism = the pre-#328 internal shuffle [SAB-D, SAB-F]
  T-4   identity guard: partial drop → "partial"; drop-all → "none";
        full match → "platform"                          [SAB-B]
  T-5   ESPN unseeded / picks.assign OFF → labeled slot-order fallback,
        zero platform egress                             [SAB-C]
  T-6   Fleaflicker/unknown platform → "none"            [SAB-C]
  T-7   Sleeper full-coverage board labels "platform" (regression half =
        the existing W2d/G1 tests, unchanged)            [SAB-F]
  T-8   pre-#328 persisted row echoes ownership_source KEY PRESENT and
        null; capability probe unchanged                 [SAB-E]
  T-9   zero traded picks with full coverage is a FACT: ESPN → "user",
        MFL → "platform", both with empty overlays       [SAB-F]
  T-10  analytics taxonomy admits mock_started.ownership_source   [—]
  T-11  structural: board route + _mock_real_draft share _assignment_grid [—]
  T-12  partial coverage labels "partial"; round-1 hole drops to "none"
        (the pinned asymmetry)                           [SAB-G, SAB-H]

Run: ``python3 -m pytest backend/tests/test_mock_pick_ownership.py``
"""

from __future__ import annotations

import json
import pathlib
import random

import pytest
from sqlalchemy import create_engine, update

import backend.database as db
import backend.draft_board_service as dbs
import backend.feature_flags as ff
import backend.mock_draft_service as mds
import backend.server as server
from backend.database import metadata, leagues_table, league_members_table
from backend.ranking_service import Player, RankingService
from backend.trade_service import League, LeagueMember

ROUTE = "/api/mock-draft"
TOKEN = "test-token-fb328"
CALLER = "u1"

LEAGUE_ESPN = "820000000000000001"
LEAGUE_MFL = "820000000000000002"

ESPN_MEMBERS = ["u1", "u2", "u3", "u4", "u5", "u6"]
#: The stored round-1 numbering order — deliberately NOT sorted and NOT the
#: owners order, so "order == stored order" can never pass by coincidence.
ESPN_ORDER = ["u3", "u1", "u2", "u5", "u6", "u4"]
ESPN_ROUNDS = 3

MFL_FIDS = ["0001", "0002", "0003", "0004", "0005", "0006"]
#: Franchise 0001 is the linking caller; the rest are synthetic member ids —
#: the same scheme `_mfl_member_id` mints and session members carry.
MFL_UID = {fid: (CALLER if fid == "0001" else f"mfl:{LEAGUE_MFL}.f{fid}")
           for fid in MFL_FIDS}
MFL_ROUNDS = 3

STANDARD_LINEUP = ["QB", "RB", "RB", "WR", "WR", "WR", "TE", "FLEX", "FLEX"]
_POOL_IDS = [f"p{i}" for i in range(1, 41)]


# ---------------------------------------------------------------------------
# Harness — in-memory SQLite; data/trade_finder.db is never opened
# ---------------------------------------------------------------------------

@pytest.fixture()
def mem_db(monkeypatch):
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False})
    metadata.create_all(engine)
    monkeypatch.setattr(db, "engine", engine)
    with engine.begin() as conn:
        conn.execute(leagues_table.insert().values(
            sleeper_league_id=LEAGUE_ESPN, user_id=CALLER, name="Newton-ish",
            season="2026", platform="espn", total_rosters=len(ESPN_MEMBERS)))
        for uid in ESPN_MEMBERS:
            conn.execute(league_members_table.insert().values(
                league_id=LEAGUE_ESPN, user_id=uid, username=f"Team {uid}",
                display_name=f"Team {uid}", roster_data="[]"))
        conn.execute(leagues_table.insert().values(
            sleeper_league_id=LEAGUE_MFL, user_id=CALLER, name="MFL-ish",
            season="2026", platform="mfl", total_rosters=len(MFL_FIDS)))
        for fid in MFL_FIDS:
            conn.execute(league_members_table.insert().values(
                league_id=LEAGUE_MFL, user_id=MFL_UID[fid],
                username=f"Franchise {fid}", display_name=f"Franchise {fid}",
                roster_data="[]"))
    for lid in (LEAGUE_ESPN, LEAGUE_MFL):
        db.invalidate_pick_assignment_cache(lid)
    yield engine
    for lid in (LEAGUE_ESPN, LEAGUE_MFL):
        db.invalidate_pick_assignment_cache(lid)


def _session_player_rows(requested):
    rows = {pid: {"full_name": f"Rookie {pid}",
                  "position": ("WR", "RB", "TE", "QB")[i % 4], "team": "ARI",
                  "rookie_year": "2026", "search_rank": i + 1}
            for i, pid in enumerate(_POOL_IDS)}
    return {pid: rows[pid] for pid in requested if pid in rows}


def _install_session(monkeypatch, tmp_path, *, platform, league_id, members):
    """The production-shape session (#295): caller-excluded members, the
    caller's roster on ``user_roster``. Hermetic — the Sleeper fixtures dir
    is EMPTY, so any Sleeper board read degrades instead of going live."""
    positions = ("WR", "RB", "TE", "QB")
    pool = [Player(id=pid, name=f"Rookie {pid}", position=positions[i % 4],
                   team="ARI", age=22)
            for i, pid in enumerate(_POOL_IDS)]
    elo = {pid: 2000.0 - i for i, pid in enumerate(_POOL_IDS)}
    service = RankingService(players=pool)
    opponents = [LeagueMember(user_id=str(u), username=f"Team {u}",
                              roster=[], elo_ratings={})
                 for u in members if str(u) != CALLER]
    league = League(league_id=league_id, name="L", platform=platform,
                    members=opponents)
    sess = {"verified": True, "user_id": CALLER, "league": league, "players": pool,
            "user_roster": [], "display_name": "QA Caller",
            "services": {"1qb_ppr": service}, "service": service,
            "trade_svc": object(), "active_format": "1qb_ppr",
            "last_active": 0.0}
    monkeypatch.setattr(server, "_get_universal_pool", lambda fmt: (pool, elo))
    monkeypatch.setattr(server, "_rookie_player_ids",
                        lambda season: set(_POOL_IDS))
    monkeypatch.setattr(server, "get_league_draft_context",
                        lambda lid: {"platform": platform, "season": 2026})
    monkeypatch.setattr(server, "_sleeper_lineup_slots",
                        lambda lid: STANDARD_LINEUP)
    monkeypatch.setattr(dbs, "database_players", _session_player_rows)
    empty = tmp_path / "no-sleeper-fixtures"
    empty.mkdir(exist_ok=True)
    monkeypatch.setattr(server, "_SLEEPER_FIXTURES_DIR", str(empty))
    monkeypatch.setattr(server, "_SLEEPER_RECORD", False)
    with server._sessions_lock:
        server._sessions[TOKEN] = sess
    return sess


@pytest.fixture()
def espn_session(mem_db, monkeypatch, tmp_path):
    sess = _install_session(monkeypatch, tmp_path, platform="espn",
                            league_id=LEAGUE_ESPN, members=ESPN_MEMBERS)
    try:
        yield sess
    finally:
        with server._sessions_lock:
            server._sessions.pop(TOKEN, None)


@pytest.fixture()
def mfl_session(mem_db, monkeypatch, tmp_path):
    sess = _install_session(monkeypatch, tmp_path, platform="mfl",
                            league_id=LEAGUE_MFL,
                            members=[MFL_UID[f] for f in MFL_FIDS])
    try:
        yield sess
    finally:
        with server._sessions_lock:
            server._sessions.pop(TOKEN, None)


@pytest.fixture()
def client():
    server.app.config["TESTING"] = True
    return server.app.test_client()


def _pin_flags(**overrides):
    saved = ff._flags_cache
    ff._flags_cache = {**ff.DEFAULT_FLAGS, **overrides}
    return saved


@pytest.fixture()
def flags_on():
    saved = _pin_flags(**{"draft.mock": True, "draft.room": True,
                          "picks.assign": True})
    try:
        yield
    finally:
        ff._flags_cache = saved


def _post(client, path=ROUTE, **body):
    return client.post(path, json=body, headers={"X-Session-Token": TOKEN})


def _get(client, league_id):
    return client.get(f"{ROUTE}?league_id={league_id}",
                      headers={"X-Session-Token": TOKEN})


def _abandon(user_id, league_id):
    row = db.load_current_mock_draft(user_id, league_id)
    while row:
        db.update_mock_draft(row["id"], user_id, status="abandoned")
        row = db.load_current_mock_draft(user_id, league_id)


# ---------------------------------------------------------------------------
# Fixture seeding
# ---------------------------------------------------------------------------

def _seed_espn_grid(*, rounds=ESPN_ROUNDS, order=ESPN_ORDER,
                    order_type="snake"):
    """Seed the assignment grid the way the routes do: settings + pristine
    grid rows (source='user'), current season only."""
    db.save_pick_assignment_settings(LEAGUE_ESPN, {
        "rounds": rounds, "order_type": order_type, "order": list(order)})
    db.seed_pick_grid(LEAGUE_ESPN, ESPN_MEMBERS,
                      {u: f"Team {u}" for u in ESPN_MEMBERS},
                      actor_user_id=CALLER, current_season=2026,
                      rounds=rounds, seasons_ahead=0)
    db.invalidate_pick_assignment_cache(LEAGUE_ESPN)


def _espn_trade(round_, original_uid, new_owner_uid):
    """User-asserted trade of one slot, via the same CAS write the PUT
    route uses."""
    rows = db.load_draft_picks(LEAGUE_ESPN, source=db.PICK_SOURCE_USER,
                               include_contested=True)
    row = next(r for r in rows
               if int(r["season"]) == 2026 and int(r["round"]) == int(round_)
               and str(r["original_user_id"]) == str(original_uid))
    outcome, _ = db.assign_draft_pick(
        LEAGUE_ESPN, row["pick_id"], new_owner_uid, f"Team {new_owner_uid}",
        actor_user_id=CALLER, if_assigned_at=row.get("assigned_at"))
    assert outcome == "ok", outcome
    db.invalidate_pick_assignment_cache(LEAGUE_ESPN)


def _espn_slot_of(uid, order=ESPN_ORDER):
    return order.index(uid) + 1


def _seed_mfl_store(*, rounds=MFL_ROUNDS, trades=(), season=2026):
    """A full-census MFL store: one row per franchise per round, NULL
    `source` (reads as platform), `trades` = {(round, fid): owner_uid}."""
    trades = dict(trades)
    rows = []
    for rnd in range(1, rounds + 1):
        for fid in MFL_FIDS:
            owner = trades.get((rnd, fid))
            rows.append({
                "pick_id": db.make_pick_id(LEAGUE_MFL, season, rnd, fid),
                "league_id": LEAGUE_MFL, "season": season, "round": rnd,
                "owner_user_id": owner or MFL_UID[fid],
                "owner_username": f"Owner {owner or fid}",
                "original_roster_id": fid,
                "original_user_id": MFL_UID[fid],
                "original_username": f"Franchise {fid}",
                "is_traded": int(owner is not None),
                "pick_value": 10.0, "pool_value": 100.0,
                "platform": "mfl", "synced_at": "2026-08-01T00:00:00+00:00",
            })
    db.replace_draft_picks(LEAGUE_MFL, rows)
    db.invalidate_pick_assignment_cache(LEAGUE_MFL)


def _mfl_owners():
    """`_mock_owner_ids`' answer for the MFL session: caller-excluded
    members in session order, caller appended."""
    return [MFL_UID[f] for f in MFL_FIDS if MFL_UID[f] != CALLER] + [CALLER]


def _expected_shuffle(seed):
    """EXACTLY build_settings' pre-#328 internal shuffle recipe."""
    order = [str(o) for o in _mfl_owners()]
    random.Random(seed).shuffle(order)
    return order


def _round1_owners(body):
    rows = sorted((r for r in body["order"] if r["round"] == 1),
                  key=lambda r: r["slot"])
    return [str(r["owner_user_id"]) for r in rows]


def _order_row(body, round_, slot):
    return next(r for r in body["order"]
                if r["round"] == round_ and r["slot"] == slot)


def _loaded_settings(league_id):
    row = db.load_current_mock_draft(CALLER, league_id)
    assert row is not None
    return mds.loads(row)["settings"]


# ---------------------------------------------------------------------------
# T-1 / T-2 — ESPN: the #328 report itself
# ---------------------------------------------------------------------------

def test_t1_espn_grid_drives_order_overlay_label_and_type(
        client, flags_on, espn_session):
    """T-1 (R-1, R-2, R-13). Sabotage: SAB-A (whole test), SAB-F (label)."""
    _seed_espn_grid()
    _espn_trade(1, "u3", "u6")          # slot 1's round-1 pick → u6
    _espn_trade(2, "u5", "u2")          # slot 4's round-2 pick → u2
    _abandon(CALLER, LEAGUE_ESPN)

    resp = _post(client, league_id=LEAGUE_ESPN, rounds=ESPN_ROUNDS, rng_seed=9)
    assert resp.status_code == 200
    body = resp.get_json()
    assert not body.get("empty"), body

    echo = body["settings_echo"]
    # R-1 — the grid's stored round-1 order, never a shuffle.
    assert echo["order_source"] == "assigned"
    assert _loaded_settings(LEAGUE_ESPN)["order"] == ESPN_ORDER
    # R-13 — the mock's numbering defaults to the grid's order_type.
    assert echo["type"] == "snake"
    # R-2 — the user-asserted overlay, labeled.
    assert echo["ownership_source"] == "user"
    settings = _loaded_settings(LEAGUE_ESPN)
    slots = {(r["round"], r["slot"]): r["pick_no"] for r in settings["slots"]}
    assert mds.owner_of(slots[(1, _espn_slot_of("u3"))], settings) == "u6"
    assert mds.owner_of(slots[(2, _espn_slot_of("u5"))], settings) == "u2"
    # …and the payload's order rows disclose the trade.
    assert _order_row(body, 1, _espn_slot_of("u3"))["is_traded"] is True
    assert _order_row(body, 2, _espn_slot_of("u5"))["owner_user_id"] == "u2"
    _abandon(CALLER, LEAGUE_ESPN)


def test_t2_manual_mode_reads_the_same_snapshot(
        client, flags_on, espn_session):
    """T-2 (R-3). Sabotage: SAB-A. No mode-specific resolution code exists —
    at the traded round-1 slot the ACQUIRER is on the clock with
    `is_user: true` (manual mode: the user picks for every team)."""
    _seed_espn_grid()
    _espn_trade(1, "u3", "u6")
    _abandon(CALLER, LEAGUE_ESPN)

    resp = _post(client, league_id=LEAGUE_ESPN, rounds=ESPN_ROUNDS,
                 rng_seed=9, mode="manual")
    assert resp.status_code == 200
    body = resp.get_json()
    assert not body.get("empty"), body
    assert body["settings_echo"]["mode"] == "manual"
    assert body["settings_echo"]["ownership_source"] == "user"
    clock = body["on_the_clock"]
    assert clock["pick_no"] == 1
    assert str(clock["roster_id"]) == "u6"      # the acquiring team
    assert clock["is_user"] is True             # the "picking for" chip
    _abandon(CALLER, LEAGUE_ESPN)


# ---------------------------------------------------------------------------
# T-3 / T-4 — MFL: overlay over a randomized order
# ---------------------------------------------------------------------------

#: Pinned seeds. The OBJ-4 precondition below asserts that for SEED_A each
#: traded franchise's correct shuffled slot differs from its SAB-D
#: franchise-ordinal slot, so a seed collision can never record a false
#: green under SAB-D.
SEED_A = 1234
SEED_B = 4321
#: The two traded rows: franchise 0003's round-2 pick → the caller;
#: franchise 0004's round-3 pick → franchise 0002's owner.
MFL_TRADES = {(2, "0003"): CALLER, (3, "0004"): MFL_UID["0002"]}


def test_t3_mfl_overlay_anchors_to_the_original_owners_shuffled_slot(
        client, flags_on, mfl_session):
    """T-3 (R-4, R-5). Sabotage: SAB-D (anchoring — also proves the route's
    MFL block is live), SAB-F (label half)."""
    _seed_mfl_store(trades=MFL_TRADES)
    _abandon(CALLER, LEAGUE_MFL)

    expected = _expected_shuffle(SEED_A)
    # OBJ-4 precondition: correct shuffled slot != SAB-D franchise ordinal.
    for (_rnd, fid) in MFL_TRADES:
        assert expected.index(MFL_UID[fid]) + 1 != int(fid.lstrip("0")), (
            f"pinned seed {SEED_A} collides with the SAB-D ordinal for "
            f"franchise {fid} — pick a different seed")

    resp = _post(client, league_id=LEAGUE_MFL, rounds=MFL_ROUNDS,
                 rng_seed=SEED_A)
    assert resp.status_code == 200
    body = resp.get_json()
    assert not body.get("empty"), body
    echo = body["settings_echo"]

    # R-4 — order is never invented (KD-6)…
    assert echo["order_source"] == "randomized"
    # …and equals the pre-#328 internal shuffle's permutation (R-5).
    assert _loaded_settings(LEAGUE_MFL)["order"] == expected
    # The overlay lands at the ORIGINAL owner's shuffled slot.
    for (rnd, fid), owner in MFL_TRADES.items():
        row = _order_row(body, rnd, expected.index(MFL_UID[fid]) + 1)
        assert str(row["owner_user_id"]) == owner
        assert row["is_traded"] is True
    assert echo["ownership_source"] == "platform"

    # Determinism: same seed → same order; different seed → different.
    _abandon(CALLER, LEAGUE_MFL)
    again = _post(client, league_id=LEAGUE_MFL, rounds=MFL_ROUNDS,
                  rng_seed=SEED_A).get_json()
    assert _round1_owners(again) == _round1_owners(body) == [
        u for u in expected]
    _abandon(CALLER, LEAGUE_MFL)
    other = _post(client, league_id=LEAGUE_MFL, rounds=MFL_ROUNDS,
                  rng_seed=SEED_B).get_json()
    assert _round1_owners(other) == _expected_shuffle(SEED_B)
    assert _round1_owners(other) != _round1_owners(body)
    _abandon(CALLER, LEAGUE_MFL)


def test_t4_identity_guard_drops_partial_all_and_none(
        client, flags_on, mfl_session):
    """T-4 (R-6). Sabotage: SAB-B (skip the identity-guard filter)."""
    # (a) ONE row's owner outside the resolved order → dropped, the rest
    #     applied, label "partial".
    _seed_mfl_store(trades={(2, "0003"): "mystery-owner",
                            (3, "0004"): MFL_UID["0002"]})
    _abandon(CALLER, LEAGUE_MFL)
    body = _post(client, league_id=LEAGUE_MFL, rounds=MFL_ROUNDS,
                 rng_seed=SEED_A).get_json()
    assert body["settings_echo"]["ownership_source"] == "partial"
    expected = _expected_shuffle(SEED_A)
    kept = _order_row(body, 3, expected.index(MFL_UID["0004"]) + 1)
    assert str(kept["owner_user_id"]) == MFL_UID["0002"]
    assert kept["is_traded"] is True
    dropped = _order_row(body, 2, expected.index(MFL_UID["0003"]) + 1)
    assert dropped["is_traded"] is False        # never misassigned
    _abandon(CALLER, LEAGUE_MFL)

    # (b) ALL traded rows unknown → "none", empty overlay, no crash.
    _seed_mfl_store(trades={(2, "0003"): "mystery-owner",
                            (3, "0004"): "another-stranger"})
    body = _post(client, league_id=LEAGUE_MFL, rounds=MFL_ROUNDS,
                 rng_seed=SEED_A).get_json()
    assert body["settings_echo"]["ownership_source"] == "none"
    assert _loaded_settings(LEAGUE_MFL)["ownership"] == {}
    _abandon(CALLER, LEAGUE_MFL)

    # (c) two-sided: a fully-matching row set must yield "platform" —
    #     never "partial"/"none".
    _seed_mfl_store(trades=MFL_TRADES)
    body = _post(client, league_id=LEAGUE_MFL, rounds=MFL_ROUNDS,
                 rng_seed=SEED_A).get_json()
    assert body["settings_echo"]["ownership_source"] == "platform"
    _abandon(CALLER, LEAGUE_MFL)


# ---------------------------------------------------------------------------
# T-5 / T-6 — honest, labeled fallback; zero egress
# ---------------------------------------------------------------------------

def _forbid_egress(monkeypatch):
    def _boom(*a, **k):                          # pragma: no cover - tripwire
        raise AssertionError("platform egress on the mock create path")
    monkeypatch.setattr(server, "_sleeper_get", _boom)
    monkeypatch.setattr(server, "_mfl_draft_opener", _boom)


def test_t5_espn_unseeded_and_flag_off_fall_back_labeled(
        client, flags_on, espn_session, monkeypatch):
    """T-5 (R-7). Sabotage: SAB-C (hardcode "platform" in build_settings)."""
    _forbid_egress(monkeypatch)

    # (a) `picks.assign` ON, but nothing seeded: the grid is empty.
    _abandon(CALLER, LEAGUE_ESPN)
    body = _post(client, league_id=LEAGUE_ESPN, rounds=3,
                 rng_seed=7).get_json()
    assert not body.get("empty"), body
    assert body["settings_echo"]["order_source"] == "randomized"
    assert body["settings_echo"]["ownership_source"] == "none"
    assert _loaded_settings(LEAGUE_ESPN)["ownership"] == {}
    _abandon(CALLER, LEAGUE_ESPN)

    # (b) `picks.assign` OFF entirely — even a seeded grid is not read.
    _seed_espn_grid()
    saved = _pin_flags(**{"draft.mock": True, "draft.room": True})
    try:
        body = _post(client, league_id=LEAGUE_ESPN, rounds=3,
                     rng_seed=7).get_json()
        assert not body.get("empty"), body
        assert body["settings_echo"]["ownership_source"] == "none"
        assert body["settings_echo"]["order_source"] == "randomized"
    finally:
        ff._flags_cache = saved
    _abandon(CALLER, LEAGUE_ESPN)


def test_t6_unknown_platform_stays_none(
        client, flags_on, mem_db, monkeypatch, tmp_path):
    """T-6 (R-7). Sabotage: SAB-C. Fleaflicker = 1.13.4's behavior, now
    labeled."""
    _install_session(monkeypatch, tmp_path, platform="fleaflicker",
                     league_id=LEAGUE_MFL,
                     members=[MFL_UID[f] for f in MFL_FIDS])
    try:
        _forbid_egress(monkeypatch)
        _seed_mfl_store(trades=MFL_TRADES)      # data exists; platform wrong
        _abandon(CALLER, LEAGUE_MFL)
        body = _post(client, league_id=LEAGUE_MFL, rounds=3,
                     rng_seed=7).get_json()
        assert not body.get("empty"), body
        assert body["settings_echo"]["ownership_source"] == "none"
        assert body["settings_echo"]["order_source"] == "randomized"
        assert _loaded_settings(LEAGUE_MFL)["ownership"] == {}
        _abandon(CALLER, LEAGUE_MFL)
    finally:
        with server._sessions_lock:
            server._sessions.pop(TOKEN, None)


# ---------------------------------------------------------------------------
# T-7 — Sleeper labels "platform" (the regression half is the unchanged
# W2d/G1 suite in test_mock_draft.py)
# ---------------------------------------------------------------------------

#: The recorded Lakeview league + the operator id its assigned order names —
#: same constants the W2d/G1 suite uses.
LAKEVIEW = "1312076055586050048"
OPERATOR = "313560442465169408"


def test_t7_sleeper_full_coverage_board_labels_platform(
        client, flags_on, mem_db, monkeypatch, tmp_path):
    """T-7 (R-9), label half — the regression half is the unchanged W2d/G1
    suite. Sabotage: SAB-F (the route-level echo assertion is what reaches
    build_settings' returned dict)."""
    from backend.tests.support.draft_replay import DraftReplay
    sess = _install_session(monkeypatch, tmp_path, platform="sleeper",
                            league_id=LAKEVIEW,
                            members=["a", "b", "c", "d", "e"])
    sess["user_id"] = OPERATOR      # slot 6 of the recorded assigned order
    sess["display_name"] = "Operator"
    dbs.reset_cache()
    DraftReplay("lakeview-complete", tmp_path).install(monkeypatch, server)
    try:
        real = server._mock_real_draft(sess, LAKEVIEW, 2026, 4)
        assert real["order_source"] == mds.ORDER_SOURCE_ASSIGNED
        assert real["order"] and len(real["order"]) == 12
        # 12 teams x 4 rounds, a row per slot ⇒ full coverage ⇒ "platform".
        assert real["ownership_source"] == mds.OWNERSHIP_SOURCE_PLATFORM
        # A mock DEEPER than the board's 4 recorded rounds is honest too.
        deeper = server._mock_real_draft(sess, LAKEVIEW, 2026, 6)
        assert deeper["ownership_source"] == mds.OWNERSHIP_SOURCE_PARTIAL
        # …and the label survives build_settings into the echo (SAB-F's red).
        _abandon(OPERATOR, LAKEVIEW)
        body = _post(client, league_id=LAKEVIEW, rounds=4,
                     rng_seed=7).get_json()
        assert not body.get("empty"), body
        assert body["settings_echo"]["ownership_source"] == "platform"
        _abandon(OPERATOR, LAKEVIEW)
    finally:
        dbs.reset_cache()
        with server._sessions_lock:
            server._sessions.pop(TOKEN, None)


# ---------------------------------------------------------------------------
# T-8 — pre-#328 rows: the key is PRESENT and null
# ---------------------------------------------------------------------------

def test_t8_pre_change_rows_echo_null_key_present(
        client, flags_on, espn_session):
    """T-8 (R-10). Sabotage: SAB-E (key absent, not null — the explicit
    presence assertion is what makes `.get()` unable to satisfy this)."""
    _seed_espn_grid()
    _abandon(CALLER, LEAGUE_ESPN)
    resp = _post(client, league_id=LEAGUE_ESPN, rounds=3, rng_seed=7)
    mock_id = resp.get_json()["mock_id"]

    # Surgically age the persisted row to the 1.13.4 shape: settings JSON
    # without the key (no other byte moves).
    row = db.load_current_mock_draft(CALLER, LEAGUE_ESPN)
    settings = json.loads(row["settings"])
    assert "ownership_source" in settings
    del settings["ownership_source"]
    with db.engine.begin() as conn:
        conn.execute(update(db.mock_drafts_table)
                     .where(db.mock_drafts_table.c.id == mock_id)
                     .values(settings=json.dumps(settings)))

    body = _get(client, LEAGUE_ESPN).get_json()
    echo = body["settings_echo"]
    assert "ownership_source" in echo           # the KEY is present…
    assert echo["ownership_source"] is None     # …and the value is null
    # The rest of the echo is untouched by the aging.
    assert echo["order_source"] == "assigned"
    assert echo["mode"] == "cpu"
    _abandon(CALLER, LEAGUE_ESPN)

    # The capability probe payload gains NOTHING (HD-6).
    probe = _get(client, LEAGUE_ESPN).get_json()
    assert probe.get("empty") is True
    assert "ownership_source" not in json.dumps(probe)


# ---------------------------------------------------------------------------
# T-9 — zero trades with full coverage is a fact, not a fallback
# ---------------------------------------------------------------------------

def test_t9_full_coverage_zero_trades_keeps_the_source_label(
        client, flags_on, espn_session):
    """T-9 (R-8), ESPN half. Sabotage: SAB-F."""
    _seed_espn_grid()                            # pristine — zero trades
    _abandon(CALLER, LEAGUE_ESPN)
    body = _post(client, league_id=LEAGUE_ESPN, rounds=ESPN_ROUNDS,
                 rng_seed=7).get_json()
    assert body["settings_echo"]["ownership_source"] == "user"
    assert _loaded_settings(LEAGUE_ESPN)["ownership"] == {}
    _abandon(CALLER, LEAGUE_ESPN)


def test_t9_mfl_full_census_zero_trades_labels_platform(
        client, flags_on, mfl_session):
    """T-9 (R-8), MFL half. Sabotage: SAB-F."""
    _seed_mfl_store(trades={})                   # full census, none traded
    _abandon(CALLER, LEAGUE_MFL)
    body = _post(client, league_id=LEAGUE_MFL, rounds=MFL_ROUNDS,
                 rng_seed=SEED_A).get_json()
    assert body["settings_echo"]["ownership_source"] == "platform"
    assert _loaded_settings(LEAGUE_MFL)["ownership"] == {}
    _abandon(CALLER, LEAGUE_MFL)


# ---------------------------------------------------------------------------
# T-10 / T-11 — structural pins
# ---------------------------------------------------------------------------

def test_t10_taxonomy_admits_ownership_source_on_mock_started():
    """T-10 (R-12) — prop-set membership (DEFAULT-DENY drops unregistered
    props silently)."""
    from backend.analytics_taxonomy import CLIENT_EVENT_PROPS
    assert "ownership_source" in CLIENT_EVENT_PROPS["mock_started"]


def test_t11_board_route_and_mock_share_the_assignment_grid():
    """T-11 — both surfaces call `_assignment_grid`; grid construction can
    never silently fork."""
    import inspect
    mock_src = inspect.getsource(server._mock_real_draft)
    assert "_assignment_grid(" in mock_src
    board_src = inspect.getsource(server.draft_board_route)
    assert "_assignment_grid(" in board_src


# ---------------------------------------------------------------------------
# T-12 — partial coverage is labeled, never silently full (R-14)
# ---------------------------------------------------------------------------

def test_t12a_round2_excluded_slot_labels_partial(
        client, flags_on, espn_session):
    """T-12(a). Sabotage: SAB-G. A round-2 orphaned slot (owner left the
    league) is grid-EXCLUDED: order intact, other trades applied,
    "partial"."""
    _seed_espn_grid()
    _espn_trade(2, "u5", "u2")                  # a kept trade
    _espn_trade(2, "u6", "ghost-user")          # orphaned → excluded
    _abandon(CALLER, LEAGUE_ESPN)
    body = _post(client, league_id=LEAGUE_ESPN, rounds=ESPN_ROUNDS,
                 rng_seed=7).get_json()
    echo = body["settings_echo"]
    assert echo["order_source"] == "assigned"   # order intact
    assert echo["ownership_source"] == "partial"
    row = _order_row(body, 2, _espn_slot_of("u5"))
    assert str(row["owner_user_id"]) == "u2"    # applied rows still apply
    assert row["is_traded"] is True
    _abandon(CALLER, LEAGUE_ESPN)


def test_t12b_mock_deeper_than_the_grid_labels_partial(
        client, flags_on, espn_session):
    """T-12(b). Sabotage: SAB-G. 4-round mock over a 3-round grid."""
    _seed_espn_grid(rounds=3)
    _abandon(CALLER, LEAGUE_ESPN)
    body = _post(client, league_id=LEAGUE_ESPN, rounds=4,
                 rng_seed=7).get_json()
    echo = body["settings_echo"]
    assert echo["order_source"] == "assigned"
    assert echo["ownership_source"] == "partial"
    _abandon(CALLER, LEAGUE_ESPN)


def test_t12c_mfl_store_shallower_than_the_mock_labels_partial(
        client, flags_on, mfl_session):
    """T-12(c). Sabotage: SAB-G. Store rounds 1-2, mock rounds 3."""
    _seed_mfl_store(rounds=2, trades={(2, "0003"): CALLER})
    _abandon(CALLER, LEAGUE_MFL)
    body = _post(client, league_id=LEAGUE_MFL, rounds=3,
                 rng_seed=SEED_A).get_json()
    echo = body["settings_echo"]
    assert echo["ownership_source"] == "partial"
    # The applied row still applies.
    expected = _expected_shuffle(SEED_A)
    row = _order_row(body, 2, expected.index(MFL_UID["0003"]) + 1)
    assert str(row["owner_user_id"]) == CALLER
    _abandon(CALLER, LEAGUE_MFL)


def test_t12d_round1_hole_drops_the_whole_resolution_to_none(
        client, flags_on, espn_session):
    """T-12(d) — the pinned asymmetry. Sabotage: SAB-H (delete the "a
    partial slot map is not an order" rule — the gapped map then builds a
    wrong order / KeyErrors, never an honest "none"). SAB-A/SAB-G also
    produce "none" here and are deliberately NOT this case's sabotage."""
    _seed_espn_grid()
    _espn_trade(2, "u5", "u2")                  # would-be overlay
    _espn_trade(1, "u2", "ghost-user")          # round-1 orphan → excluded
    _abandon(CALLER, LEAGUE_ESPN)
    body = _post(client, league_id=LEAGUE_ESPN, rounds=ESPN_ROUNDS,
                 rng_seed=7).get_json()
    echo = body["settings_echo"]
    assert not body.get("empty"), body
    assert echo["order_source"] == "randomized"     # whole resolution drops
    assert echo["ownership_source"] == "none"
    assert _loaded_settings(LEAGUE_ESPN)["ownership"] == {}
    _abandon(CALLER, LEAGUE_ESPN)
