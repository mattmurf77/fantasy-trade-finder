"""ADR-011 — roster/board history capture (#46 Wrapped P0).

Build spec: docs/plans/dynasty-year-in-review/review-data-architect-final.md.
Systems design: review-eng-architect-final.md. Scope: scope.md (same folder).

What is pinned here, and why each failure mode is silent:

  (a) period_key uses the ISO week-numbering YEAR — a %Y-keyed label makes
      2026-12-31 sort AFTER 2027-01-01's week and dedupe against the wrong
      bucket, corrupting exactly the season boundary a yearly recap reads.
  (b) PRECEDENCE, NOT RECENCY on upsert — 'weekly' rows are server-fetched
      with orphan teams included; 'sync' rows are client-posted with
      ownerless rosters already dropped. Last-write-wins would let a
      Friday app-open silently delete the week's orphan teams (YR-6).
  (c) The hash suppresses EXTRA sync writes only — a hash-suppressed
      weekly grid puts holes in the quiet weeks, the opposite of YR-2.
  (d) team_value is NULL, never 0, when nothing prices — a zero renders
      as a roster wipe and is indistinguishable from a real one.
  (e) The platform on-sync hook must never raise — it runs beside a
      committed membership write, and the whole design exists because a
      failure inside that transaction would leave a league with zero
      members.
  (f) The ESPN reconnect nudge fires once per credential-expiry episode.
  (g) The sweep is identity-aware (#321 R9): a stored credential that
      conclusively doesn't own the bound team gets the honest
      wrong-account nudge, and the sync CONTINUES — league rosters are
      league truth regardless of whose credential read them. Silent
      failure mode: a mislabeled "stopped working" nudge months later.

Harness pattern follows test_notif_inbox_growth.py: isolated file-backed
SQLite engine patched into backend.database.
"""
import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, insert, select

import backend.database as db_module
import backend.roster_history as rh
from backend.database import (
    league_board_history_table,
    league_roster_history_table,
    metadata,
    notifications_table,
)

LEAGUE = "77001"


def _engine(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path / 'rh.db'}",
                        connect_args={"check_same_thread": False})
    metadata.create_all(eng)
    return eng


def _rows(eng, table=league_roster_history_table):
    with eng.connect() as conn:
        return [dict(r._mapping) for r in conn.execute(
            select(table).order_by(table.c.id)).fetchall()]


def _base_row(**over) -> dict:
    row = {
        "league_id": LEAGUE, "team_key": f"sleeper:{LEAGUE}.r1",
        "team_key_quality": "strong", "platform": "sleeper",
        "owner_user_id": "u1", "scoring_format": "1qb_ppr",
        "period_key": "2026-W33", "period_kind": "week",
        "snapshot_date": "2026-08-14",
        "snapshot_at": "2026-08-14T12:00:00+00:00",
        "player_ids": json.dumps(["p1", "p2"]),
        "starter_ids": None, "pick_ids": None, "pick_ids_excluded": None,
        "pick_source": None, "roster_hash": rh.roster_hash(["p1", "p2"]),
        "changed_from_prev": None, "player_count": 2,
        "valued_player_count": 2, "team_value": 100.0,
        "team_value_picks": None, "value_basis_date": "2026-08-14",
        "in_season": None, "source": "sync",
    }
    row.update(over)
    return row


# ---------------------------------------------------------------------------
# (a) period_key — ISO week-numbering year
# ---------------------------------------------------------------------------

def test_period_key_uses_iso_week_numbering_year():
    assert rh.iso_period_key(datetime(2026, 8, 14, tzinfo=timezone.utc)) == "2026-W33"
    # THE boundary. (The review docs' example — "2026-12-31 is 2027-W01" —
    # is factually wrong: 2026 is a 53-week ISO year and 2026-12-31 is
    # 2026-W53. The PRINCIPLE they argued is still right, and the real
    # crossing shows it: 2025-12-29 belongs to ISO 2026-W01, so a '%Y'
    # label would file that Monday under '2025-W01' — sorting before every
    # real 2025 week and deduping against the wrong bucket.)
    assert rh.iso_period_key(datetime(2025, 12, 29, tzinfo=timezone.utc)) == "2026-W01"
    assert rh.iso_period_key(datetime(2026, 12, 31, tzinfo=timezone.utc)) == "2026-W53"
    # Zero-padded weeks keep lexicographic order == chronological order,
    # including through a 53-week year ('2026-W53' < '2027-W01').
    assert rh.iso_period_key(datetime(2026, 1, 8, tzinfo=timezone.utc)) == "2026-W02"
    assert "2026-W53" < "2027-W01"


def test_roster_hash_is_set_semantics():
    assert rh.roster_hash(["b", "a"]) == rh.roster_hash(["a", "b"])
    assert rh.roster_hash(["a"]) != rh.roster_hash(["a", "b"])
    assert len(rh.roster_hash(["a"])) == 16


def test_real_owner_or_none_rejects_synthetic_ids():
    assert rh.real_owner_or_none("12345") == "12345"
    for synth in ("espn:{abc}", "mfl:1.f0001", "flea:9.t3",
                  "fleaflicker:9.t3", "sleeper:1.r4", "", None):
        assert rh.real_owner_or_none(synth) is None


# ---------------------------------------------------------------------------
# (b)+(c) upsert precedence
# ---------------------------------------------------------------------------

def test_sync_then_identical_sync_is_suppressed(tmp_path):
    eng = _engine(tmp_path)
    with patch.object(db_module, "engine", eng):
        assert db_module.upsert_roster_snapshots([_base_row()])["inserted"] == 1
        stats = db_module.upsert_roster_snapshots([_base_row()])
    assert stats["skipped_unchanged"] == 1
    assert len(_rows(eng)) == 1


def test_sync_then_changed_sync_updates_in_place(tmp_path):
    eng = _engine(tmp_path)
    changed = _base_row(player_ids=json.dumps(["p1", "p3"]),
                        roster_hash=rh.roster_hash(["p1", "p3"]))
    with patch.object(db_module, "engine", eng):
        db_module.upsert_roster_snapshots([_base_row()])
        stats = db_module.upsert_roster_snapshots([changed])
    assert stats["updated"] == 1
    rows = _rows(eng)
    assert len(rows) == 1
    assert json.loads(rows[0]["player_ids"]) == ["p1", "p3"]


def test_weekly_overwrites_sync_and_is_never_hash_suppressed(tmp_path):
    """Same roster, same hash — the weekly write must still land (YR-2:
    team_value moves weekly even when the roster does not)."""
    eng = _engine(tmp_path)
    weekly = _base_row(source="weekly", team_value=88.8)
    with patch.object(db_module, "engine", eng):
        db_module.upsert_roster_snapshots([_base_row()])
        stats = db_module.upsert_roster_snapshots([weekly])
    assert stats["updated"] == 1
    rows = _rows(eng)
    assert rows[0]["source"] == "weekly"
    assert rows[0]["team_value"] == 88.8


def test_sync_never_overwrites_a_weekly_row(tmp_path):
    """THE YR-6 protection. The weekly row is server-fetched and carries
    orphan teams; the sync row is client-posted and has already dropped
    them. Recency would delete the week's orphans silently."""
    eng = _engine(tmp_path)
    weekly = _base_row(source="weekly", team_value=88.8)
    later_sync = _base_row(player_ids=json.dumps(["p9"]),
                           roster_hash=rh.roster_hash(["p9"]),
                           team_value=1.0)
    with patch.object(db_module, "engine", eng):
        db_module.upsert_roster_snapshots([weekly])
        stats = db_module.upsert_roster_snapshots([later_sync])
    assert stats["skipped_precedence"] == 1
    rows = _rows(eng)
    assert rows[0]["source"] == "weekly"
    assert rows[0]["team_value"] == 88.8, "the Friday app-open must lose"


def test_weekly_rerun_is_idempotent_one_row(tmp_path):
    eng = _engine(tmp_path)
    weekly = _base_row(source="weekly")
    with patch.object(db_module, "engine", eng):
        db_module.upsert_roster_snapshots([weekly])
        db_module.upsert_roster_snapshots([weekly])
    assert len(_rows(eng)) == 1


def test_backfill_never_overwrites_any_observation(tmp_path):
    eng = _engine(tmp_path)
    backfill = _base_row(source="backfill", team_value=5.0)
    with patch.object(db_module, "engine", eng):
        db_module.upsert_roster_snapshots([_base_row()])
        stats = db_module.upsert_roster_snapshots([backfill])
    assert stats["skipped_precedence"] == 1
    assert _rows(eng)[0]["source"] == "sync"


def test_different_periods_are_different_rows(tmp_path):
    eng = _engine(tmp_path)
    w34 = _base_row(period_key="2026-W34")
    with patch.object(db_module, "engine", eng):
        db_module.upsert_roster_snapshots([_base_row()])
        db_module.upsert_roster_snapshots([w34])
    assert len(_rows(eng)) == 2


# ---------------------------------------------------------------------------
# (d) row building — NULL-not-zero, changed_from_prev, synthetic owners
# ---------------------------------------------------------------------------

def _players_meta(*pids):
    return {p: SimpleNamespace(id=p, position="RB", name=p, team="FA", age=25)
            for p in pids}


def test_team_value_is_null_never_zero_when_nothing_prices(tmp_path):
    eng = _engine(tmp_path)
    teams = [{"team_key": f"sleeper:{LEAGUE}.r1", "team_key_quality": "strong",
              "member_user_id": "u1", "player_ids": ["kicker1", "dst2"],
              "starter_ids": None}]
    with patch.object(db_module, "engine", eng):
        rows = rh.build_roster_snapshot_rows(
            LEAGUE, "sleeper", "1qb_ppr", teams, "sync",
            seed={}, players_meta={},   # nothing in the pool prices
            now=datetime(2026, 8, 14, tzinfo=timezone.utc))
    assert rows[0]["team_value"] is None, "a zero renders as a roster wipe"
    assert rows[0]["valued_player_count"] == 0
    assert rows[0]["player_count"] == 2


def test_priced_roster_carries_power_rankings_total_and_coverage(tmp_path):
    eng = _engine(tmp_path)
    teams = [{"team_key": f"sleeper:{LEAGUE}.r1", "team_key_quality": "strong",
              "member_user_id": "u1", "player_ids": ["p1", "kicker1"],
              "starter_ids": ["p1"]}]
    with patch.object(db_module, "engine", eng):
        rows = rh.build_roster_snapshot_rows(
            LEAGUE, "sleeper", "1qb_ppr", teams, "sync",
            seed={"p1": 1600.0}, players_meta=_players_meta("p1", "kicker1"),
            now=datetime(2026, 8, 14, tzinfo=timezone.utc))
    r = rows[0]
    assert r["team_value"] is not None and r["team_value"] > 0
    assert r["valued_player_count"] == 1      # kicker1 has no seed
    assert r["player_count"] == 2
    assert json.loads(r["starter_ids"]) == ["p1"]
    assert r["period_key"] == "2026-W33"


def test_changed_from_prev_null_then_tracks_hash(tmp_path):
    eng = _engine(tmp_path)
    def teams(ids):
        return [{"team_key": f"sleeper:{LEAGUE}.r1", "team_key_quality": "strong",
                 "member_user_id": "u1", "player_ids": ids, "starter_ids": None}]
    with patch.object(db_module, "engine", eng):
        w33 = rh.build_roster_snapshot_rows(
            LEAGUE, "sleeper", "1qb_ppr", teams(["p1"]), "sync",
            seed={}, players_meta={},
            now=datetime(2026, 8, 14, tzinfo=timezone.utc))
        assert w33[0]["changed_from_prev"] is None, "first observation"
        db_module.upsert_roster_snapshots(w33)

        w34_same = rh.build_roster_snapshot_rows(
            LEAGUE, "sleeper", "1qb_ppr", teams(["p1"]), "sync",
            seed={}, players_meta={},
            now=datetime(2026, 8, 21, tzinfo=timezone.utc))
        assert w34_same[0]["changed_from_prev"] == 0
        db_module.upsert_roster_snapshots(w34_same)

        w35_changed = rh.build_roster_snapshot_rows(
            LEAGUE, "sleeper", "1qb_ppr", teams(["p1", "p2"]), "sync",
            seed={}, players_meta={},
            now=datetime(2026, 8, 28, tzinfo=timezone.utc))
        assert w35_changed[0]["changed_from_prev"] == 1


def test_synthetic_member_ids_never_become_owner_user_id(tmp_path):
    eng = _engine(tmp_path)
    teams = [
        {"team_key": f"espn:{LEAGUE}.t1", "team_key_quality": "strong",
         "member_user_id": "real_ftf_uid", "player_ids": ["p1"], "starter_ids": None},
        {"team_key": f"espn:{LEAGUE}.t2", "team_key_quality": "strong",
         "member_user_id": "espn:{8D2-ROT}", "player_ids": ["p2"], "starter_ids": None},
    ]
    with patch.object(db_module, "engine", eng):
        rows = rh.build_roster_snapshot_rows(
            LEAGUE, "espn", "1qb_ppr", teams, "sync",
            seed={}, players_meta={},
            now=datetime(2026, 8, 14, tzinfo=timezone.utc))
    assert rows[0]["owner_user_id"] == "real_ftf_uid"
    assert rows[1]["owner_user_id"] is None


def test_owner_restamp_updates_history_not_the_fact(tmp_path):
    eng = _engine(tmp_path)
    with patch.object(db_module, "engine", eng):
        db_module.upsert_roster_snapshots([
            _base_row(team_key=f"espn:{LEAGUE}.t2", owner_user_id=None,
                      platform="espn"),
            _base_row(team_key=f"espn:{LEAGUE}.t2", owner_user_id=None,
                      platform="espn", period_key="2026-W34"),
        ])
        n = db_module.restamp_roster_history_owner(
            LEAGUE, f"espn:{LEAGUE}.t2", "late_joiner")
    assert n == 2
    rows = _rows(eng)
    assert all(r["owner_user_id"] == "late_joiner" for r in rows)
    assert all(json.loads(r["player_ids"]) == ["p1", "p2"] for r in rows), \
        "the roster fact itself is untouched"


# ---------------------------------------------------------------------------
# (e) the platform on-sync hook never raises
# ---------------------------------------------------------------------------

def test_platform_hook_swallows_snapshot_failures(tmp_path):
    """The hook runs beside a COMMITTED membership write. If a snapshot bug
    could propagate, the fix would be to move it inside the membership
    transaction — which is the exact zero-members failure this design
    exists to prevent. So: it must never raise, full stop."""
    import backend.server as server
    with patch.object(server, "is_enabled", lambda k: True), \
         patch.object(server, "_do_league_history_snapshot",
                      side_effect=RuntimeError("boom")):
        # Must not raise:
        server._platform_roster_history_on_sync(
            LEAGUE, "espn",
            [{"user_id": "u1", "player_ids": ["p1"],
              "team_key": f"espn:{LEAGUE}.t1"}],
            my_user_id="u1", my_team_key=f"espn:{LEAGUE}.t1")


def test_sweep_kickoff_gates_and_env_lever():
    import backend.server as server
    with patch.object(server, "is_enabled", lambda k: True):
        # Monday (weekday 0) with default gate 1 => gated.
        mon = datetime(2026, 8, 10, tzinfo=timezone.utc)
        assert server._kickoff_roster_snapshot_sweep(mon).get("gated") is True
        # FTF_ROSTER_SNAPSHOT_WEEKDAY=7 can never pass — the sweep-only
        # kill lever (on-sync capture unaffected).
        with patch.dict("os.environ", {"FTF_ROSTER_SNAPSHOT_WEEKDAY": "7"}):
            sun = datetime(2026, 8, 16, tzinfo=timezone.utc)
            assert server._kickoff_roster_snapshot_sweep(sun).get("gated") is True
    with patch.object(server, "is_enabled", lambda k: False):
        assert server._kickoff_roster_snapshot_sweep().get("disabled") is True


# ---------------------------------------------------------------------------
# (f) boards — C5/C6
# ---------------------------------------------------------------------------

def _seed_member_rankings(eng, user_id, league_id, elos, updated_at, fmt="1qb_ppr"):
    with eng.begin() as conn:
        for pid, elo in elos.items():
            conn.execute(insert(db_module.member_rankings_table).values(
                user_id=user_id, league_id=league_id, player_id=pid,
                elo=elo, updated_at=updated_at, scoring_format=fmt))


def test_board_snapshot_is_complete_and_idempotent(tmp_path):
    eng = _engine(tmp_path)
    with patch.object(db_module, "engine", eng):
        _seed_member_rankings(eng, "u1", LEAGUE,
                              {"p1": 1500.0, "p2": 1622.34}, "2026-08-10T00:00:00")
        now = datetime(2026, 8, 14, tzinfo=timezone.utc)
        rh.snapshot_league_boards(LEAGUE, "sync", now=now)
        rh.snapshot_league_boards(LEAGUE, "sync", now=now)   # double run
    rows = _rows(eng, league_board_history_table)
    assert len(rows) == 1, "a double run must not double the board"
    r = rows[0]
    assert json.loads(r["elos"]) == {"p1": 1500.0, "p2": 1622.3}
    assert r["player_count"] == 2
    # board_updated_at is member_rankings.updated_at — what stops one
    # observation re-snapshotted five times reading as five observations.
    assert r["board_updated_at"] == "2026-08-10T00:00:00"
    assert r["period_key"] == "2026-W33"


def test_board_snapshot_separates_users_and_formats(tmp_path):
    eng = _engine(tmp_path)
    with patch.object(db_module, "engine", eng):
        _seed_member_rankings(eng, "u1", LEAGUE, {"p1": 1500.0}, "2026-08-10T00:00:00")
        _seed_member_rankings(eng, "u2", LEAGUE, {"p1": 1400.0}, "2026-08-11T00:00:00")
        _seed_member_rankings(eng, "u1", LEAGUE, {"p1": 1450.0}, "2026-08-12T00:00:00",
                              fmt="sf_tep")
        rh.snapshot_league_boards(LEAGUE, "weekly",
                                  now=datetime(2026, 8, 14, tzinfo=timezone.utc))
    rows = _rows(eng, league_board_history_table)
    assert len(rows) == 3
    keys = {(r["user_id"], r["scoring_format"]) for r in rows}
    assert keys == {("u1", "1qb_ppr"), ("u2", "1qb_ppr"), ("u1", "sf_tep")}


# ---------------------------------------------------------------------------
# (g) pick fold-in — contested slots are skipped AND counted
# ---------------------------------------------------------------------------

def test_pick_fold_records_exclusions_per_owner():
    clean = [
        {"pick_id": "L_2027_1_1", "owner_user_id": "u1", "source": "platform"},
    ]
    raw = clean + [
        {"pick_id": "L_2027_1_2", "owner_user_id": "u1", "source": "user"},
        {"pick_id": "L_2027_2_1", "owner_user_id": "u2", "source": "user"},
    ]
    with patch.object(rh, "load_draft_picks",
                      side_effect=lambda **kw: (raw if kw.get("include_contested")
                                                else clean)), \
         patch.object(rh, "contested_pick_ids",
                      return_value=frozenset({"L_2027_1_2"})), \
         patch.object(rh, "orphaned_pick_ids",
                      return_value=frozenset({"L_2027_2_1"})):
        fold = rh.pick_fold_for_league("L", "any")
    assert fold["u1"]["pick_ids"] == ["L_2027_1_1"]
    # The honest record: u1 asserted this slot; we decline to state it as
    # fact. Non-empty => the recap suppresses pick flow for the league.
    assert fold["u1"]["pick_ids_excluded"] == ["L_2027_1_2"]
    assert fold["u2"]["pick_ids"] == []
    assert fold["u2"]["pick_ids_excluded"] == ["L_2027_2_1"]
    assert fold["u1"]["pick_source"] == "platform"


# ---------------------------------------------------------------------------
# sweep support
# ---------------------------------------------------------------------------

def test_sweep_worklist_is_stalest_first(tmp_path):
    eng = _engine(tmp_path)
    with eng.begin() as conn:
        for lid, platform in (("100", "sleeper"), ("200", "espn"), ("300", None)):
            conn.execute(insert(db_module.leagues_table).values(
                sleeper_league_id=lid, user_id="u1", name=f"L{lid}",
                platform=platform))
        conn.execute(insert(league_roster_history_table).values(
            **_base_row(league_id="100", source="weekly")))
    with patch.object(db_module, "engine", eng):
        out = db_module.load_history_sweep_leagues("2026-W33")
    assert [o["league_id"] for o in out] == ["200", "300", "100"], \
        "leagues missing the current weekly row come first"
    assert out[-1]["has_current_weekly"] is True
    assert out[1]["platform"] == "sleeper", "NULL platform reads as sleeper"


# ---------------------------------------------------------------------------
# (f) ESPN reconnect nudge — once per expiry episode
# ---------------------------------------------------------------------------

def test_espn_reconnect_nudge_once_per_episode(tmp_path):
    import backend.server as server
    eng = _engine(tmp_path)
    lg = {"league_id": "555", "user_id": "u1"}
    cred_v1 = {"verified_at": "2026-07-01T00:00:00", "updated_at": "x",
               "swid": "{S}", "espn_s2_encrypted": "enc"}
    cred_v2 = {**cred_v1, "verified_at": "2026-09-01T00:00:00"}
    with patch.object(db_module, "engine", eng):
        with patch.object(db_module, "get_espn_credential", return_value=cred_v1):
            server._espn_reconnect_nudge(lg, reason="expired")
            server._espn_reconnect_nudge(lg, reason="expired")   # same episode
        with patch.object(db_module, "get_espn_credential", return_value=cred_v2):
            server._espn_reconnect_nudge(lg, reason="expired")   # NEW episode
    with eng.connect() as conn:
        rows = conn.execute(select(notifications_table)).fetchall()
    assert len(rows) == 2, "one nudge per expiry episode, re-armed on re-verify"
    assert all(r.type == "espn_reconnect" for r in rows)
    assert all(r.user_id == "u1" for r in rows)


# ---------------------------------------------------------------------------
# (g) #321 R9 — identity-aware ESPN sweep: wrong-account nudge (QA F-1)
# ---------------------------------------------------------------------------

def _espn_sweep(eng, *, stored_swid, bound_owner_swid):
    """Run _sweep_fetch_teams for a cookie-auth ESPN league whose bound team
    (espn_my_team_id) is owned by `bound_owner_swid` while the stored
    credential carries `stored_swid`. Returns ((teams, skip), inbox rows)."""
    import backend.server as server
    lg = {"league_id": "777", "user_id": "u1", "platform": "espn",
          "espn_auth": "cookie", "espn_my_team_id": 3, "espn_season": 2026}
    cred = {"verified_at": "2026-07-01T00:00:00", "updated_at": "x",
            "swid": stored_swid, "espn_s2_encrypted": "enc"}
    league = {"teams": [
        SimpleNamespace(team_id=3, owner_swid=bound_owner_swid),
        SimpleNamespace(team_id=4,
                        owner_swid="{CCCCCCCC-0000-0000-0000-0000000000CC}"),
    ]}
    mapped = {"rosters": {3: ["p1"], 4: ["p2"]}}
    with patch.object(db_module, "engine", eng), \
         patch.object(db_module, "get_espn_credential", return_value=cred), \
         patch.object(server._sleeper_write, "decrypt_token",
                      return_value="s2cookie"), \
         patch.object(server, "_espn_import_payload",
                      return_value=(league, mapped)):
        out = server._sweep_fetch_teams(lg)
    with eng.connect() as conn:
        rows = conn.execute(select(notifications_table)).fetchall()
    return out, rows


def test_sweep_wrong_account_nudges_and_sync_continues(tmp_path):
    """A stored SWID that conclusively does NOT own the bound team gets the
    honest wrong-account nudge — same `espn_reconnect` type (the web inbox
    allowlists types), meta.reason == "wrong_account" — AND the sync itself
    CONTINUES: league rosters are league truth regardless of whose
    credential read them. Proven RED by neutering the sweep's mismatch
    comparison (canonical-SWID `!=` → `==` at the server.py R9 hook)."""
    import json as _json
    (teams, skip), rows = _espn_sweep(
        _engine(tmp_path),
        stored_swid="{AAAAAAAA-0000-0000-0000-000000000001}",
        bound_owner_swid="{BBBBBBBB-0000-0000-0000-000000000002}")
    assert skip is None and teams is not None and len(teams) == 2, \
        "the sweep must CONTINUE on a wrong-account credential"
    assert len(rows) == 1, "exactly one nudge row"
    assert rows[0].type == "espn_reconnect"
    meta = _json.loads(rows[0].metadata_json)
    assert meta["reason"] == "wrong_account"
    assert meta["league_id"] == "777"


def test_sweep_matching_swid_no_nudge(tmp_path):
    """R9 control — the same account's credential (case-different SWID:
    the comparison is canonical + case-folded) syncs with NO nudge row."""
    (teams, skip), rows = _espn_sweep(
        _engine(tmp_path),
        stored_swid="{aaaaaaaa-0000-0000-0000-000000000001}",
        bound_owner_swid="{AAAAAAAA-0000-0000-0000-000000000001}")
    assert skip is None and teams is not None and len(teams) == 2
    assert rows == [], "no mismatch, no nudge"
