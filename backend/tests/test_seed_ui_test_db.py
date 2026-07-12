"""Tests for the UI-test fixture seeder (backend/tests/fixtures/seed_ui_test_db.py).

Covers the LLD §2.5/§3.1 contract: every MVP profile seeds cleanly; the
standard profile's DB state matches its spec; near-unlock sits at exactly
threshold−1; DB, Sleeper cassettes, players cache and DP-values CSV agree
(one generator, four outputs — the CSV round-trips through data_loader's
FTF_DP_VALUES_FILE seam); seeding is deterministic; token-like profile
fields are refused (exit 3); and --verify catches backend-schema drift
(exit 3).
"""

import json
import shlex
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import pytest

from backend.ranking_service import RankingService
from backend.tests.fixtures.seed_ui_test_db import (
    EXIT_REFUSED,
    EXIT_UNKNOWN_PROFILE,
    POOL_FIXTURE,
    SeederError,
    list_profiles,
    main,
    print_env,
    seed_profile,
)

MVP_PROFILES = ("standard", "fresh", "near-unlock", "two-leagues", "single-format")
APP_UID = "900000000000000001"
OPP_RANKED_UID = "900000000000000002"
OPP_UNRANKED_UID = "900000000000000003"
LEAGUE_ID = "990000000000000001"
SEED = 1337
FIXED_NOW = datetime(2026, 7, 11, 12, 0, 0, tzinfo=timezone.utc)
THRESHOLD = RankingService.POSITION_THRESHOLDS["QB"]
POSITIONS = ("QB", "RB", "WR", "TE")


# ---------------------------------------------------------------------------
# Shared seeding — all MVP profiles once, reused across tests
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def seeded(tmp_path_factory):
    """{profile: (out_dir, manifest)} — every MVP profile seeded once."""
    out_dir = tmp_path_factory.mktemp("ui-test")
    result = {}
    for name in MVP_PROFILES:
        manifest = seed_profile(name, out_dir=out_dir, seed=SEED, now=FIXED_NOW)
        result[name] = (out_dir, manifest)
    return result


@pytest.fixture(scope="module")
def pool_positions():
    """player_id → position from the static pool fixture."""
    doc = json.loads(POOL_FIXTURE.read_text())
    return {pid: rec["position"] for pid, rec in doc["players"].items()}


def _connect(out_dir: Path, profile: str) -> sqlite3.Connection:
    con = sqlite3.connect(out_dir / f"{profile}.db")
    con.row_factory = sqlite3.Row
    return con


def _rank_swipe_counts(con, pool_positions) -> Counter:
    """(position, scoring_format) → pairwise rank-swipe row count."""
    rows = con.execute(
        "SELECT winner_player_id, scoring_format FROM swipe_decisions "
        "WHERE user_id = ? AND decision_type = 'rank'", (APP_UID,)
    ).fetchall()
    return Counter((pool_positions[r["winner_player_id"]], r["scoring_format"])
                   for r in rows)


# ---------------------------------------------------------------------------
# (a) every profile seeds without error, all four artifacts land
# ---------------------------------------------------------------------------

def test_mvp_profiles_are_registered():
    assert set(MVP_PROFILES) <= set(list_profiles())


@pytest.mark.parametrize("name", MVP_PROFILES)
def test_profile_outputs_exist(seeded, name):
    out_dir, manifest = seeded[name]
    assert (out_dir / f"{name}.db").exists()
    assert (out_dir / f"{name}.manifest.json").exists()
    assert (out_dir / "sleeper" / name).is_dir()
    assert (out_dir / "players-cache" / f"{name}.json").exists()
    assert (out_dir / "dp-values" / f"{name}.csv").exists()
    assert manifest["profile"] == name
    assert manifest["seed"] == SEED
    assert manifest["season"] == 2026
    # Full explicit flag map, base = release
    assert manifest["flags"]["trade.send_in_sleeper"] is True
    assert manifest["flags"]["trades.queue_2k"] is False


def test_release_flags_mirror_features_json():
    """flags/release.json must stay an exact mirror of config/features.json."""
    repo = Path(__file__).resolve().parents[2]
    release = json.loads((repo / "backend/tests/fixtures/flags/release.json").read_text())
    features = json.loads((repo / "config/features.json").read_text())
    strip = lambda d: {k: v for k, v in d.items() if not k.startswith("_")}
    assert strip(release) == strip(features)


# ---------------------------------------------------------------------------
# (b) standard profile state
# ---------------------------------------------------------------------------

def test_standard_user_unlocked_both_formats(seeded):
    out_dir, _ = seeded["standard"]
    with _connect(out_dir, "standard") as con:
        row = con.execute(
            "SELECT username, ranking_method, unlocked_formats FROM users "
            "WHERE sleeper_user_id = ?", (APP_UID,)
        ).fetchone()
        assert row["username"] == "qa_standard"
        assert row["ranking_method"] == "trio"
        assert set(json.loads(row["unlocked_formats"])) == {"1qb_ppr", "sf_tep"}


def test_standard_swipe_counts_clear_threshold(seeded, pool_positions):
    out_dir, _ = seeded["standard"]
    with _connect(out_dir, "standard") as con:
        counts = _rank_swipe_counts(con, pool_positions)
    expected_rows = (THRESHOLD + 2) * 3  # trios_per_position = threshold+2
    for fmt in ("1qb_ppr", "sf_tep"):
        for pos in POSITIONS:
            assert counts[(pos, fmt)] == expected_rows, (pos, fmt)


def test_standard_row_counts_sane(seeded):
    out_dir, manifest = seeded["standard"]
    with _connect(out_dir, "standard") as con:
        n = lambda q, *a: con.execute(q, a).fetchone()[0]
        assert n("SELECT COUNT(*) FROM league_members WHERE league_id = ?",
                 LEAGUE_ID) == 12
        assert n("SELECT COUNT(*) FROM players") == manifest["counts"]["players"] > 250
        # every roster carries roster_size players from the cache
        rosters = con.execute(
            "SELECT roster_data FROM league_members WHERE league_id = ?",
            (LEAGUE_ID,)).fetchall()
        assert all(len(json.loads(r["roster_data"])) == 26 for r in rosters)
        lg = con.execute("SELECT default_scoring, total_rosters FROM leagues "
                         "WHERE sleeper_league_id = ?", (LEAGUE_ID,)).fetchone()
        assert lg["default_scoring"] == "sf_tep"
        assert lg["total_rosters"] == 12


def test_standard_opponent_rankings_split(seeded):
    out_dir, _ = seeded["standard"]
    with _connect(out_dir, "standard") as con:
        n = lambda uid, fmt: con.execute(
            "SELECT COUNT(*) FROM member_rankings WHERE user_id = ? "
            "AND league_id = ? AND scoring_format = ?",
            (uid, LEAGUE_ID, fmt)).fetchone()[0]
        for fmt in ("1qb_ppr", "sf_tep"):
            assert n(OPP_RANKED_UID, fmt) > 0, f"qa_opp_ranked missing {fmt}"
        assert con.execute(
            "SELECT COUNT(*) FROM member_rankings WHERE user_id = ?",
            (OPP_UNRANKED_UID,)).fetchone()[0] == 0


def test_standard_elo_history_spans_30_days(seeded):
    out_dir, _ = seeded["standard"]
    with _connect(out_dir, "standard") as con:
        for fmt in ("1qb_ppr", "sf_tep"):
            rows = con.execute(
                "SELECT MIN(snapshot_at) AS lo, MAX(snapshot_at) AS hi, "
                "COUNT(*) AS n FROM elo_history WHERE user_id = ? "
                "AND scoring_format = ?", (APP_UID, fmt)).fetchone()
            assert rows["n"] > 0
            lo = datetime.fromisoformat(rows["lo"])
            hi = datetime.fromisoformat(rows["hi"])
            span_days = (hi - lo).total_seconds() / 86400
            assert span_days >= 27, f"{fmt} history spans only {span_days:.1f}d"


def test_standard_matches_and_awaiting(seeded):
    out_dir, _ = seeded["standard"]
    with _connect(out_dir, "standard") as con:
        matches = con.execute(
            "SELECT user_a_id, user_b_id, user_a_give, user_a_receive, status "
            "FROM trade_matches WHERE league_id = ?", (LEAGUE_ID,)).fetchall()
        assert len(matches) == 2
        assert all(APP_UID in (m["user_a_id"], m["user_b_id"]) for m in matches)
        assert all(m["status"] == "pending" for m in matches)
        # both orientations covered (a-side and b-side perspectives)
        assert {m["user_a_id"] == APP_UID for m in matches} == {True, False}

        likes = con.execute(
            "SELECT give_player_ids, receive_player_ids FROM trade_decisions "
            "WHERE user_id = ? AND decision = 'like'", (APP_UID,)).fetchall()
        assert len(likes) == 1
        # the awaiting like must NOT collide with a matured match (it would be
        # filtered out of /api/trades/awaiting otherwise)
        matched_keys = set()
        for m in matches:
            give, recv = json.loads(m["user_a_give"]), json.loads(m["user_a_receive"])
            if m["user_a_id"] != APP_UID:
                give, recv = recv, give
            matched_keys.add((frozenset(give), frozenset(recv)))
        like_key = (frozenset(json.loads(likes[0]["give_player_ids"])),
                    frozenset(json.loads(likes[0]["receive_player_ids"])))
        assert like_key not in matched_keys

        # bell inbox has one notification per mutual match
        assert con.execute(
            "SELECT COUNT(*) FROM notifications WHERE user_id = ? "
            "AND type = 'trade_match'", (APP_UID,)).fetchone()[0] == 2


def test_standard_activity_and_feedback_seeds(seeded):
    out_dir, _ = seeded["standard"]
    with _connect(out_dir, "standard") as con:
        assert con.execute(
            "SELECT COUNT(*) FROM wrapped_events WHERE league_id = ?",
            (LEAGUE_ID,)).fetchone()[0] == 3
        fb = con.execute(
            "SELECT status, user_id FROM app_feedback").fetchall()
        assert len(fb) == 1
        assert fb[0]["status"] == "fixed"
        assert fb[0]["user_id"] == APP_UID


# ---------------------------------------------------------------------------
# (c) near-unlock: exactly threshold−1 per position, still locked
# ---------------------------------------------------------------------------

def test_near_unlock_is_exactly_threshold_minus_one(seeded, pool_positions):
    out_dir, _ = seeded["near-unlock"]
    with _connect(out_dir, "near-unlock") as con:
        counts = _rank_swipe_counts(con, pool_positions)
        for pos in POSITIONS:
            assert counts[(pos, "sf_tep")] == (THRESHOLD - 1) * 3, pos
            assert counts[(pos, "1qb_ppr")] == 0, pos
        row = con.execute("SELECT unlocked_formats FROM users "
                          "WHERE sleeper_user_id = ?", (APP_UID,)).fetchone()
        assert not json.loads(row["unlocked_formats"] or "[]")


# ---------------------------------------------------------------------------
# other profile states
# ---------------------------------------------------------------------------

def test_fresh_has_zero_rankings_and_no_leagues_user(seeded):
    out_dir, _ = seeded["fresh"]
    with _connect(out_dir, "fresh") as con:
        assert con.execute("SELECT COUNT(*) FROM swipe_decisions "
                           "WHERE user_id = ?", (APP_UID,)).fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM elo_history "
                           "WHERE user_id = ?", (APP_UID,)).fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM trade_matches").fetchone()[0] == 0
        row = con.execute("SELECT unlocked_formats, ranking_method FROM users "
                          "WHERE sleeper_user_id = ?", (APP_UID,)).fetchone()
        assert not json.loads(row["unlocked_formats"] or "[]")
        assert row["ranking_method"] is None
    # qa_no_leagues: user cassette exists with an EMPTY league list
    sdir = out_dir / "sleeper" / "fresh"
    user_doc = json.loads((sdir / "user/qa_no_leagues.json").read_text())
    assert user_doc["user_id"] == "900000000000000099"
    leagues = json.loads(
        (sdir / "user/900000000000000099/leagues/nfl/2026.json").read_text())
    assert leagues == []


def test_single_format_sets_up_format_gate(seeded):
    """League resolves sf_tep; user is unlocked ONLY in 1qb_ppr — exactly
    FormatGate's trigger (needed missing + other set)."""
    out_dir, _ = seeded["single-format"]
    with _connect(out_dir, "single-format") as con:
        lg = con.execute("SELECT default_scoring FROM leagues "
                         "WHERE sleeper_league_id = ?", (LEAGUE_ID,)).fetchone()
        assert lg["default_scoring"] == "sf_tep"
        row = con.execute("SELECT unlocked_formats FROM users "
                          "WHERE sleeper_user_id = ?", (APP_UID,)).fetchone()
        assert json.loads(row["unlocked_formats"]) == ["1qb_ppr"]
        assert con.execute(
            "SELECT COUNT(*) FROM swipe_decisions WHERE user_id = ? "
            "AND scoring_format = 'sf_tep'", (APP_UID,)).fetchone()[0] == 0
    # the league meta cassette must actually detect as sf_tep
    meta = json.loads((out_dir / "sleeper" / "single-format" /
                       f"league/{LEAGUE_ID}.json").read_text())
    assert "SUPER_FLEX" in meta["roster_positions"]
    assert meta["scoring_settings"]["bonus_rec_te"] > 0


def test_two_leagues_membership_and_matches(seeded):
    out_dir, _ = seeded["two-leagues"]
    with _connect(out_dir, "two-leagues") as con:
        lids = {r[0] for r in con.execute(
            "SELECT league_id FROM league_members WHERE user_id = ?",
            (APP_UID,)).fetchall()}
        assert lids == {LEAGUE_ID, "990000000000000002"}
        per_league = dict(con.execute(
            "SELECT league_id, COUNT(*) FROM trade_matches GROUP BY league_id"
        ).fetchall())
        assert per_league == {LEAGUE_ID: 2, "990000000000000002": 1}


# ---------------------------------------------------------------------------
# (d) DB ↔ fixture agreement — one generator, three outputs
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", MVP_PROFILES)
def test_db_fixture_agreement(seeded, name):
    out_dir, _ = seeded[name]
    sdir = out_dir / "sleeper" / name
    cache = json.loads((out_dir / "players-cache" / f"{name}.json").read_text())

    with _connect(out_dir, name) as con:
        league_ids = [r[0] for r in con.execute(
            "SELECT sleeper_league_id FROM leagues").fetchall()]
        members = con.execute(
            "SELECT league_id, user_id, username, roster_data "
            "FROM league_members").fetchall()
        user_ids = [r[0] for r in con.execute(
            "SELECT sleeper_user_id FROM users").fetchall()]
        db_players = {r[0] for r in con.execute(
            "SELECT player_id FROM players").fetchall()}

    # every league in the DB has meta + rosters + users cassettes
    for lid in league_ids:
        for rel in (f"league/{lid}.json", f"league/{lid}/rosters.json",
                    f"league/{lid}/users.json"):
            assert (sdir / rel).exists(), f"{name}: missing cassette {rel}"

    # every member (and every signed-up user) resolves through the seam
    for m in members:
        assert (sdir / f"user/{m['username']}.json").exists(), m["username"]
        assert (sdir / f"user/{m['user_id']}/leagues/nfl/2026.json").exists()
    for uid in user_ids:
        assert (sdir / f"user/{uid}/leagues/nfl/2026.json").exists(), uid

    # rosters agree across all three outputs: DB rows == cassette rosters,
    # and every rostered player exists in the warm cache AND the players table
    for lid in league_ids:
        cassette = json.loads((sdir / f"league/{lid}/rosters.json").read_text())
        by_owner = {r["owner_id"]: r["players"] for r in cassette}
        for m in members:
            if m["league_id"] != lid:
                continue
            db_roster = json.loads(m["roster_data"])
            assert db_roster == by_owner[m["user_id"]], (name, lid, m["user_id"])
            for pid in db_roster:
                assert pid in cache, f"{pid} missing from players cache"
                assert pid in db_players, f"{pid} missing from players table"

    # players cache and players table are the same set
    assert set(cache) == db_players


def test_dp_values_csv_feeds_the_data_loader_seam(seeded, monkeypatch):
    """The dp-values CSV must round-trip through data_loader's REAL parse
    path (FTF_DP_VALUES_FILE seam) and cover the whole pool in both
    scorings — the universal-pool membership rule (cache ∩ value>0) then
    keeps every cache player, hermetically."""
    from backend.data_loader import _fetch_dynasty_process, normalise_name

    out_dir, _ = seeded["standard"]
    monkeypatch.setenv("FTF_DP_VALUES_FILE",
                       str(out_dir / "dp-values" / "standard.csv"))
    cache = json.loads((out_dir / "players-cache" / "standard.json").read_text())
    cache_names = {normalise_name(p["full_name"]) for p in cache.values()}

    for scoring in ("1qb_ppr", "sf_tep"):
        elo_map, value_map, _pos_map = _fetch_dynasty_process(scoring=scoring)
        assert value_map, f"{scoring}: empty value map"
        assert set(value_map) == cache_names, f"{scoring}: pool/CSV name drift"
        assert all(v > 0 for v in value_map.values())
        # Seed range under the #117 value-affine map: DP 0 → 1200, DP 10000
        # (clamped) → the 4-firsts rung ≈ 1927.3.
        assert all(1200.0 <= e <= 1927.5 for e in elo_map.values())


# ---------------------------------------------------------------------------
# (e) determinism
# ---------------------------------------------------------------------------

def test_deterministic_given_seed_and_anchor(tmp_path):
    m1 = seed_profile("standard", out_dir=tmp_path / "a", seed=SEED, now=FIXED_NOW)
    m2 = seed_profile("standard", out_dir=tmp_path / "b", seed=SEED, now=FIXED_NOW)
    assert m1 == m2
    assert m1["db_content_hash"] == m2["db_content_hash"]
    # manifest files byte-identical
    b1 = (tmp_path / "a" / "standard.manifest.json").read_bytes()
    b2 = (tmp_path / "b" / "standard.manifest.json").read_bytes()
    assert b1 == b2


def test_different_seed_changes_content(tmp_path):
    m1 = seed_profile("standard", out_dir=tmp_path / "a", seed=SEED, now=FIXED_NOW)
    m2 = seed_profile("standard", out_dir=tmp_path / "b", seed=SEED + 1, now=FIXED_NOW)
    assert m1["db_content_hash"] != m2["db_content_hash"]


# ---------------------------------------------------------------------------
# (f) token refusal — exit 3
# ---------------------------------------------------------------------------

def test_token_field_in_profile_refused(tmp_path):
    profile = json.loads(
        (Path(__file__).parent / "fixtures/profiles/standard.json").read_text())
    profile["app_user"]["sleeper_write_token"] = "eyJhbGciOi..."
    bad = tmp_path / "bad-profile.json"
    bad.write_text(json.dumps(profile))
    assert main(["--profile", str(bad), "--out-dir", str(tmp_path / "out")]) == EXIT_REFUSED
    # nothing may have been written
    assert not (tmp_path / "out" / "standard.db").exists()


def test_nested_token_field_refused(tmp_path):
    profile = json.loads(
        (Path(__file__).parent / "fixtures/profiles/fresh.json").read_text())
    profile["leagues"][0]["members"][0]["api_key"] = "shhh"
    bad = tmp_path / "bad-nested.json"
    bad.write_text(json.dumps(profile))
    with pytest.raises(SeederError) as ei:
        seed_profile(str(bad), out_dir=tmp_path / "out", seed=SEED, now=FIXED_NOW)
    assert ei.value.code == EXIT_REFUSED


# ---------------------------------------------------------------------------
# (g) --verify schema-hash drift — exit 3
# ---------------------------------------------------------------------------

def test_verify_ok_then_catches_schema_drift(tmp_path):
    seed_profile("fresh", out_dir=tmp_path, seed=SEED, now=FIXED_NOW)
    assert main(["--profile", "fresh", "--out-dir", str(tmp_path), "--verify"]) == 0

    manifest_path = tmp_path / "fresh.manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["schema_hash"] = "0" * 64  # simulate a backend schema migration
    manifest_path.write_text(json.dumps(manifest))
    assert main(["--profile", "fresh", "--out-dir", str(tmp_path),
                 "--verify"]) == EXIT_REFUSED


# ---------------------------------------------------------------------------
# CLI odds and ends
# ---------------------------------------------------------------------------

def test_unknown_profile_exits_4(tmp_path):
    assert main(["--profile", "nope", "--out-dir", str(tmp_path)]) == EXIT_UNKNOWN_PROFILE


def test_print_env_block(seeded, capsys):
    out_dir, manifest = seeded["standard"]
    print_env("standard", out_dir, manifest=manifest)
    lines = capsys.readouterr().out.strip().splitlines()
    # print_env shlex-quotes values (the block is `source`d by sim-run.sh and
    # this repo's path contains spaces) — unquote before comparing.
    kv = {k: (shlex.split(v)[0] if v else v)
          for k, v in (line.split("=", 1) for line in lines)}
    assert kv["DATABASE_URL"] == f"sqlite:///{out_dir.resolve() / 'standard.db'}"
    assert kv["FTF_SLEEPER_FIXTURES_DIR"] == str(out_dir.resolve() / "sleeper/standard")
    assert kv["FTF_PLAYERS_CACHE_FILE"] == str(
        out_dir.resolve() / "players-cache/standard.json")
    assert kv["FTF_DP_VALUES_FILE"] == str(
        out_dir.resolve() / "dp-values/standard.csv")
    assert kv["FTF_TEST_MODE"] == "1"
    assert len(lines) == 7
    assert kv["FTF_TEST_PROFILE"] == "standard"
    flags = json.loads(kv["FTF_FLAGS"])
    assert flags == manifest["flags"]
