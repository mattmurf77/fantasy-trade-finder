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

from backend.ranking_service import Player, RankingService
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
    assert (out_dir / "dp-values" / f"{name}.picks.csv").exists()
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
    # M6 — values.csv is a SECOND DynastyProcess egress and the backend now
    # startup-aborts in test mode without it pinned (T-M6-01).
    assert kv["FTF_DP_PICK_VALUES_FILE"] == str(
        out_dir.resolve() / "dp-values/standard.picks.csv")
    assert kv["FTF_TEST_MODE"] == "1"
    assert len(lines) == 8
    assert kv["FTF_TEST_PROFILE"] == "standard"
    flags = json.loads(kv["FTF_FLAGS"])
    assert flags == manifest["flags"]


# ---------------------------------------------------------------------------
# (h) draft + espn profiles — the capture matrix's C-block (fixture gaps)
#
# capture-matrix-signoff.md ruling C authorised two new profiles because five
# screens (draft-room, mock-draft, pick-assignment, record-picks, LeagueScreen's
# ESPN branch) had ZERO reachable state against the MVP five: every one of them
# serves `drafts: []` and no ESPN league exists anywhere in the fixture set.
# ---------------------------------------------------------------------------

C_BLOCK_PROFILES = ("draft", "espn")
DRAFT_LEAGUE_ID = "990000000000000001"
DRAFT_ID = "990000000000000002"          # league_id + 1 (seeder convention)
ESPN_LEAGUE_ID = "1189600"


@pytest.fixture(scope="module")
def cblock(tmp_path_factory):
    """{profile: (out_dir, manifest)} for the two C-block profiles."""
    out_dir = tmp_path_factory.mktemp("ui-test-cblock")
    return {name: (out_dir, seed_profile(name, out_dir=out_dir, seed=SEED,
                                         now=FIXED_NOW))
            for name in C_BLOCK_PROFILES}


def _cassette(out_dir: Path, profile: str, rel: str):
    return json.loads((out_dir / "sleeper" / profile / f"{rel}.json").read_text())


def test_cblock_profiles_are_registered():
    assert set(C_BLOCK_PROFILES) <= set(list_profiles())


@pytest.mark.parametrize("name", C_BLOCK_PROFILES)
def test_cblock_outputs_exist(cblock, name):
    out_dir, manifest = cblock[name]
    for rel in manifest["outputs"].values():
        assert (out_dir / rel).exists(), rel


# -- draft ------------------------------------------------------------------

def test_draft_profile_emits_one_rookie_shaped_drafting_draft(cblock):
    out_dir, _ = cblock["draft"]
    drafts = _cassette(out_dir, "draft", f"league/{DRAFT_LEAGUE_ID}/drafts")
    assert len(drafts) == 1
    d = drafts[0]
    assert d["draft_id"] == DRAFT_ID
    assert d["status"] == "drafting"
    assert d["type"] == "snake"
    assert d["settings"]["rounds"] == 4 and d["settings"]["teams"] == 12
    assert d["season"] == "2026"
    # THE order gate (draft_board_service D5): a non-null draft_order is what
    # makes order_confidence "assigned" — without it the Draft Room renders the
    # order-unknown board and every ordered row in the matrix is uncapturable.
    assert d["draft_order"] is not None
    assert len(d["draft_order"]) == 12
    assert sorted(d["draft_order"].values()) == list(range(1, 13))


def test_draft_detail_and_list_are_the_same_document(cblock):
    """Sleeper serves the same object at /league/<id>/drafts and /draft/<id>;
    two hand-authored files would drift, one builder cannot."""
    out_dir, _ = cblock["draft"]
    assert (_cassette(out_dir, "draft", f"league/{DRAFT_LEAGUE_ID}/drafts")[0]
            == _cassette(out_dir, "draft", f"draft/{DRAFT_ID}"))


def test_draft_slot_to_roster_id_is_not_the_identity_trap(cblock):
    """fixtures/draft/README.md §"two things not to tidy": the ffv3 corpus
    pins an identity slot_to_roster_id as a HAZARD. A generated fixture that
    reproduced the identity map would let a slot/roster confusion pass here
    while failing against every real league."""
    out_dir, _ = cblock["draft"]
    d = _cassette(out_dir, "draft", f"draft/{DRAFT_ID}")
    s2r = d["slot_to_roster_id"]
    assert len(s2r) == 12
    assert sorted(s2r.values()) == list(range(1, 13))
    assert any(int(k) != v for k, v in s2r.items())


def test_draft_picks_are_snake_ordered_and_complete(cblock):
    out_dir, _ = cblock["draft"]
    picks = _cassette(out_dir, "draft", f"draft/{DRAFT_ID}/picks")
    assert len(picks) == 18
    assert [p["pick_no"] for p in picks] == list(range(1, 19))
    assert [p["draft_id"] for p in picks] == [DRAFT_ID] * 18
    # Round 1 runs 1..12, round 2 runs 12..1 (snake).
    assert [p["draft_slot"] for p in picks[:12]] == list(range(1, 13))
    assert [p["draft_slot"] for p in picks[12:18]] == [12, 11, 10, 9, 8, 7]
    assert {p["round"] for p in picks[:12]} == {1}
    assert {p["round"] for p in picks[12:]} == {2}
    # A drafted player is only ever drafted once.
    assert len({p["player_id"] for p in picks}) == 18


def test_drafted_players_are_rookies_by_the_BACKENDS_predicate(cblock):
    """The seeder picks the draft class from the pool fixture; the Draft Room
    subtracts picks from `database.load_rookie_player_ids`. If those two ever
    disagree the board shows picks of players it does not consider rookies —
    the undrafted list would not shrink as picks land."""
    out_dir, _ = cblock["draft"]
    picks = _cassette(out_dir, "draft", f"draft/{DRAFT_ID}/picks")
    with _connect(out_dir, "draft") as con:
        rookie_ids = {r["player_id"] for r in con.execute(
            "SELECT player_id FROM players WHERE rookie_year = '2026' "
            "OR (rookie_year IS NULL AND years_exp = 0 "
            "    AND team IS NOT NULL AND team != '')"
        ).fetchall()}
    assert len(rookie_ids) >= 40, "the pool must hold a real rookie class"
    drafted = {p["player_id"] for p in picks}
    assert drafted <= rookie_ids
    assert len(rookie_ids - drafted) == len(rookie_ids) - 18   # still on the board


def test_draft_league_rosters_hold_made_picks_and_no_undrafted_rookies(cblock):
    """The board's undrafted list is `rookie_ids - drafted - ROSTERED`, so a
    rookie class seeded onto rosters empties the board while the fixture still
    looks healthy. The made picks, conversely, MUST be on their picker's
    roster — Sleeper places them the instant a pick lands, and #207's rosters
    heuristic reads exactly that signal."""
    out_dir, _ = cblock["draft"]
    picks = _cassette(out_dir, "draft", f"draft/{DRAFT_ID}/picks")
    rosters = _cassette(out_dir, "draft", f"league/{DRAFT_LEAGUE_ID}/rosters")
    by_owner = {r["owner_id"]: set(r["players"]) for r in rosters}
    rostered = set().union(*by_owner.values())
    with _connect(out_dir, "draft") as con:
        rookie_ids = {r["player_id"] for r in con.execute(
            "SELECT player_id FROM players WHERE rookie_year = '2026' "
            "OR (rookie_year IS NULL AND years_exp = 0 "
            "    AND team IS NOT NULL AND team != '')").fetchall()}
    for p in picks:
        assert p["player_id"] in by_owner[p["picked_by"]], p["pick_no"]
    drafted = {p["player_id"] for p in picks}
    assert rookie_ids & rostered == drafted, \
        "only DRAFTED rookies may sit on a mid-draft league's rosters"
    assert len(rookie_ids - drafted) == 38      # what the Draft Room renders


def test_draft_traded_picks_are_emitted_on_both_urls(cblock):
    out_dir, _ = cblock["draft"]
    league_level = _cassette(out_dir, "draft", f"league/{DRAFT_LEAGUE_ID}/traded_picks")
    draft_level = _cassette(out_dir, "draft", f"draft/{DRAFT_ID}/traded_picks")
    assert len(league_level) == 6 and len(draft_level) == 6
    # Sleeper's league-level rows carry NO draft_id; the draft-level ones do.
    assert all("draft_id" not in t for t in league_level)
    assert all(t["draft_id"] == int(DRAFT_ID) for t in draft_level)
    for t in league_level:
        assert t["owner_id"] != t["previous_owner_id"], "a self-trade is not a trade"
        assert t["season"] == "2026"


def test_other_profiles_still_serve_empty_drafts(seeded):
    """The draft block is opt-in: adding it must not have quietly given every
    profile a draft (which would flip #207's per-league verdict everywhere)."""
    out_dir, _ = seeded["standard"]
    assert _cassette(out_dir, "standard", f"league/{LEAGUE_ID}/drafts") == []
    assert _cassette(out_dir, "standard", f"league/{LEAGUE_ID}/traded_picks") == []


# -- espn -------------------------------------------------------------------

def test_espn_league_row_carries_the_platform_binding(cblock):
    out_dir, _ = cblock["espn"]
    with _connect(out_dir, "espn") as con:
        row = con.execute(
            "SELECT * FROM leagues WHERE sleeper_league_id = ?", (ESPN_LEAGUE_ID,)
        ).fetchone()
    assert row is not None
    assert row["platform"] == "espn"
    assert row["espn_season"] == 2026
    # 'public' is the ONLY auth mode a fixture may claim: 'cookie' would imply
    # an espn_credentials row, and R-11 makes credentials unrepresentable.
    assert row["espn_auth"] == "public"
    assert row["espn_my_team_id"] == 1
    assert row["total_rosters"] == 10


def test_espn_membership_uses_synthetic_ids_for_counterparties(cblock):
    out_dir, _ = cblock["espn"]
    with _connect(out_dir, "espn") as con:
        rows = con.execute(
            "SELECT user_id, roster_data FROM league_members WHERE league_id = ?",
            (ESPN_LEAGUE_ID,)
        ).fetchall()
    ids = sorted(r["user_id"] for r in rows)
    assert len(ids) == 10
    assert APP_UID in ids
    others = [i for i in ids if i != APP_UID]
    # server._espn_member_id's shape — an ESPN manager has no FTF identity.
    assert all(i.startswith(f"espn:{ESPN_LEAGUE_ID}.t") for i in others)
    assert all(json.loads(r["roster_data"]) for r in rows)


def test_espn_league_emits_no_sleeper_cassettes(cblock):
    """An ESPN league has no Sleeper URL space. A cassette nobody can
    legitimately request is as much a lie as a missing one — and it would
    make an ESPN league answer a Sleeper read in the harness."""
    out_dir, _ = cblock["espn"]
    sleeper_dir = out_dir / "sleeper" / "espn"
    paths = [str(p.relative_to(sleeper_dir))
             for p in sleeper_dir.rglob("*.json")]
    # The ONE permitted league/<id> path is the explicit 404 sentinel: ESPN
    # league ids are numeric and server._fetch_sleeper_league_meta gates only
    # on isdigit(), so session-init really does ask Sleeper for this id — and
    # Sleeper really does 404. Without the cassette every ESPN run books a
    # vcr_miss that is indistinguishable from a real fixture gap.
    assert paths.count(f"league/{ESPN_LEAGUE_ID}.json") == 1
    assert _cassette(out_dir, "espn", f"league/{ESPN_LEAGUE_ID}") == {"__http_error__": 404}
    assert not [p for p in paths
                if p.startswith("league/") and p != f"league/{ESPN_LEAGUE_ID}.json"]
    # …and the app user's Sleeper league list is honestly empty.
    assert _cassette(out_dir, "espn", f"user/{APP_UID}/leagues/nfl/2026") == []


def test_espn_pick_assignment_grid_is_seeded_with_a_stored_order(cblock):
    """A STORED order is what keeps `pick_assignments_route` out of
    `_espn_suggested_order` — the one code path on that screen that would
    reach live ESPN, which has no fixture seam."""
    out_dir, manifest = cblock["espn"]
    with _connect(out_dir, "espn") as con:
        blob = con.execute(
            "SELECT pick_assignment_settings FROM leagues WHERE sleeper_league_id = ?",
            (ESPN_LEAGUE_ID,)
        ).fetchone()[0]
        slots = con.execute(
            "SELECT COUNT(*) c FROM draft_picks WHERE league_id = ?",
            (ESPN_LEAGUE_ID,)
        ).fetchone()["c"]
        members = [r["user_id"] for r in con.execute(
            "SELECT user_id FROM league_members WHERE league_id = ?",
            (ESPN_LEAGUE_ID,)).fetchall()]
    settings = json.loads(blob)
    assert settings["rounds"] == 4
    assert settings["order_type"] == "linear"
    # An order that is not the FULL membership gets repaired at read time,
    # which would make the stored blob and the served grid disagree.
    assert sorted(settings["order"]) == sorted(members)
    assert slots == 4 * 10 * 4          # rounds x teams x (current + 3 seasons)
    assert manifest["counts"]["pick_assignment_slots"] == slots


def test_espn_recorded_picks_are_seeded_for_the_record_picks_screen(cblock):
    out_dir, manifest = cblock["espn"]
    with _connect(out_dir, "espn") as con:
        rows = con.execute(
            "SELECT overall, round, slot, player_id FROM recorded_picks "
            "WHERE league_id = ? ORDER BY overall", (ESPN_LEAGUE_ID,)
        ).fetchall()
    assert [r["overall"] for r in rows] == [1, 2, 3, 4, 5]
    assert {r["round"] for r in rows} == {1}
    assert manifest["counts"]["recorded_picks"] == 5


# -- profile-schema refusals -------------------------------------------------

def _mutated_profile(tmp_path: Path, name: str, mutate) -> str:
    doc = json.loads((POOL_FIXTURE.parent / "profiles" / f"{name}.json").read_text())
    mutate(doc)
    path = tmp_path / f"{name}-mutant.json"
    path.write_text(json.dumps(doc))
    return str(path)


@pytest.mark.parametrize("mutate,why", [
    (lambda d: d["leagues"][0]["draft"].update(picks_made=999), "picks_made overflow"),
    (lambda d: d["leagues"][0]["draft"].update(rounds=20), "startup-sized draft"),
    (lambda d: d["leagues"][0]["draft"].update(status="pre_draft"), "pre_draft with picks"),
    (lambda d: d["leagues"][0]["draft"].update(status="bogus"), "unknown status"),
    (lambda d: d["leagues"][0].update(platform="yahoo"), "unknown platform"),
])
def test_bad_draft_blocks_are_refused(tmp_path, mutate, why):
    with pytest.raises(SeederError) as e:
        seed_profile(_mutated_profile(tmp_path, "draft", mutate),
                     out_dir=tmp_path, seed=SEED, now=FIXED_NOW)
    assert e.value.code == EXIT_REFUSED, why


def test_draft_block_is_refused_on_a_non_sleeper_league(tmp_path):
    """An ESPN league has no readable draft object — that is precisely why
    pick-assignment exists. A profile claiming one would emit Sleeper draft
    cassettes for a league that never touches Sleeper."""
    def mutate(d):
        d["leagues"][0]["draft"] = {"rounds": 4, "status": "drafting",
                                    "picks_made": 4}
    with pytest.raises(SeederError) as e:
        seed_profile(_mutated_profile(tmp_path, "espn", mutate),
                     out_dir=tmp_path, seed=SEED, now=FIXED_NOW)
    assert e.value.code == EXIT_REFUSED


# -- determinism -------------------------------------------------------------

@pytest.mark.parametrize("name", C_BLOCK_PROFILES)
def test_cblock_seeding_is_deterministic(tmp_path, name):
    a = seed_profile(name, out_dir=tmp_path / "a", seed=SEED, now=FIXED_NOW)
    b = seed_profile(name, out_dir=tmp_path / "b", seed=SEED, now=FIXED_NOW)
    assert a["db_content_hash"] == b["db_content_hash"]
    assert a["counts"] == b["counts"]


# ---------------------------------------------------------------------------
# (i) flag fixtures
# ---------------------------------------------------------------------------

def _flags(name: str) -> dict:
    doc = json.loads((POOL_FIXTURE.parent / "flags" / f"{name}.json").read_text())
    return {k: v for k, v in doc.items() if not k.startswith("_")}


def test_onboarding_v2_flags_are_release_plus_the_onboarding_surface():
    """capture-matrix-signoff.md's operator directive: the Analyst onboarding
    experience IS captured, under a dedicated flag fixture.

    **Open-access Phase A (2026-08-15, docs/business/product/
    2026-08-14-open-access-onboarding.md §5) inverted this fixture's job.**
    The five onboarding-surface flags it used to force ON are now the RELEASE
    default, so the diff is no longer "release + the onboarding surface" — the
    only value this fixture still overrides is `onboarding.league_autoskip`,
    held OFF so onboarding capture scene S1.1 stays reachable. The assertion
    is kept (rather than deleted with the fixture) because it is what would
    catch a future revert of the Phase A flip silently un-capturing the flow."""
    release, onboarding = _flags("release"), _flags("onboarding-v2")
    assert set(release) == set(onboarding)
    differing = {k for k in release if release[k] != onboarding[k]}
    # The ONLY deliberate divergence post-Phase-A. FALSE on purpose: the
    # `fresh` profile has ONE league, and autoskip would jump the picker —
    # making onboarding scene S1.1 unreachable.
    assert differing == {"onboarding.league_autoskip"}
    assert onboarding["onboarding.league_autoskip"] is False
    assert release["onboarding.league_autoskip"] is True
    # Phase A: the onboarding surface is now on in BOTH files. Asserted on
    # `release` too, so a revert of the flip fails here loudly instead of
    # quietly reverting what this fixture captures.
    for k in ("onboarding.landing", "onboarding.trades_first",
              "onboarding.quickset_prompt", "onboarding.apple_save_moment"):
        assert release[k] is True and onboarding[k] is True, k
    # onboarding.v2 is the master kill-switch — a sub-feature is live iff BOTH
    # it and its own flag are on.
    assert onboarding["onboarding.v2"] is True
    # 2026-08-29 operator ruling: "Disable the guided onboarding" — the
    # Analyst guided-avatar experience is OFF (the tour, guide_v2, was
    # already off since the 2026-08-28 merge-lit ruling; the activation
    # prompts — apple_save_moment, quickset_prompt — stay ON by the
    # operator's explicit "activation moment: yes" and run their plain,
    # avatar-free arms). FALSE is the pinned contract; a flip back is a
    # deliberate revert and must change this line with it.
    assert onboarding["onboarding.guided_avatar"] is False
    # THE LAUNCH PAIRING IS OVER (2026-08-24, Wave A of
    # docs/plans/onboarding-tour-merge/plan.md §2 item 2). It used to read
    # `is True` here, on the reasoning that /api/session/demo 404s without the
    # flag and the landing's demo link is then a dead end — which is still
    # mechanically true, and is now the POINT: the operator asked for the demo
    # link off the landing surface, so the dead end is removed by not
    # rendering the link rather than by keeping the route alive.
    #
    # Restated rather than deleted, and asserted on BOTH files, because the
    # property that matters is unchanged: these two fixtures must agree about
    # this flag, and `onboarding.league_autoskip` must stay the only
    # divergence between them (asserted above). Flipping one file and not the
    # other is the drift this catches — it is what broke main CI on
    # 2026-08-23a.
    assert release["landing.try_before_sync"] is False
    assert onboarding["landing.try_before_sync"] is False


# ---------------------------------------------------------------------------
# (j) UX-audit capture requests (docs/business/product/2026-08-09-mobile-ux-audit/
#     08-capture-requests.md §2). Three states the audit's findings turn on,
#     none of which any existing profile could reach.
# ---------------------------------------------------------------------------

AUDIT_PROFILES = ("quickset-done", "draft-pre")


@pytest.fixture(scope="module")
def audit(tmp_path_factory):
    out_dir = tmp_path_factory.mktemp("ui-test-audit")
    return {name: (out_dir, seed_profile(name, out_dir=out_dir, seed=SEED,
                                         now=FIXED_NOW))
            for name in AUDIT_PROFILES}


def test_audit_profiles_are_registered():
    assert set(AUDIT_PROFILES) <= set(list_profiles())


# -- #8 / P0-1: the 4/4-but-locked ring --------------------------------------

def test_quickset_done_is_tier_saved_and_unlocked(audit):
    """THE fixture for audit P0-1, post-fix. LeagueScreen's ring counts a
    position ranked when `progress[p] >= threshold OR tiersSaved.includes(p)`,
    so four tier-saved positions read 4/4 — and now `/api/rankings/progress`
    agrees, because `ranking_method` is 'quickset' (written at the point of
    use, and backfilled at boot for pre-fix rows). The pre-seeded
    `unlocked_formats` floor is not cosmetic: it is the fan-out suppression
    (hld.md S-03) that stops a backfilled user's first poll from firing
    `ranking_complete_first_time` and the leaguemate push retroactively.
    Trio swipes stay at zero — unlocking without a single trio is the fix."""
    out_dir, _ = audit["quickset-done"]
    with _connect(out_dir, "quickset-done") as con:
        row = con.execute(
            "SELECT username, ranking_method, unlocked_formats, tiers_saved, "
            "       tier_overrides FROM users WHERE sleeper_user_id = ?",
            (APP_UID,)).fetchone()
        swipes = con.execute(
            "SELECT COUNT(*) c FROM swipe_decisions WHERE user_id = ?",
            (APP_UID,)).fetchone()["c"]

    assert row["username"] == "qa_quickset"
    # The one field the whole finding rests on.
    assert row["ranking_method"] == "quickset"
    # …and the floor that makes the first /progress poll a no-op fan-out.
    assert sorted(json.loads(row["unlocked_formats"] or "[]")) == ["1qb_ppr", "sf_tep"]
    assert swipes == 0

    saved = json.loads(row["tiers_saved"])
    for fmt in ("1qb_ppr", "sf_tep"):
        assert sorted(saved[fmt]) == ["QB", "RB", "TE", "WR"], fmt
    overrides = json.loads(row["tier_overrides"])
    for fmt in ("1qb_ppr", "sf_tep"):
        assert len(overrides[fmt]) == 48        # 4 positions x 12 players


def test_quickset_done_overrides_are_the_public_profile_source(audit):
    """`/api/profile/<username>` builds tiers_snapshot from
    `load_tier_overrides` — so this is also the only profile against which the
    flag-on profile page renders anything (capture request #11)."""
    out_dir, manifest = audit["quickset-done"]
    assert manifest["counts"]["quickset_tier_overrides"] == 96   # 48 x 2 formats
    assert manifest["counts"]["quickset_positions_saved"] == 8   # 4 x 2 formats
    with _connect(out_dir, "quickset-done") as con:
        overrides = json.loads(con.execute(
            "SELECT tier_overrides FROM users WHERE sleeper_user_id = ?",
            (APP_UID,)).fetchone()[0])["sf_tep"]
        known = {r["player_id"] for r in con.execute(
            "SELECT player_id FROM players").fetchall()}
    # Every override must name a real player or the snapshot silently drops it
    # (the route buckets by `player_positions.get(pid)` and skips misses).
    assert set(overrides) <= known
    assert all(isinstance(v, (int, float)) for v in overrides.values())


def test_quickset_all_four_with_unlocked_false_is_refused(tmp_path):
    """Post-P0-1 the incoherent profile is the LOCKED one: the server answers
    unlocked:true for a complete Quick Set board, and the startup backfill
    writes ranking_method='quickset' at boot regardless of what the profile
    says. Refused rather than allowed to rot."""
    with pytest.raises(SeederError) as e:
        seed_profile(
            _mutated_profile(tmp_path, "quickset-done",
                             lambda d: d["app_user"].update(unlocked=False)),
            out_dir=tmp_path, seed=SEED, now=FIXED_NOW)
    assert e.value.code == EXIT_REFUSED
    assert "unlocked:true" in str(e.value)


def test_quickset_done_may_leave_ranking_method_null(tmp_path):
    """The seeder does not require the method — the startup backfill writes it.
    Only the unlocked:false CLAIM is refused."""
    seed_profile(
        _mutated_profile(tmp_path, "quickset-done",
                         lambda d: d["app_user"].update(ranking_method=None)),
        out_dir=tmp_path, seed=SEED, now=FIXED_NOW)


def test_unknown_ranking_method_is_refused(tmp_path):
    with pytest.raises(SeederError) as e:
        seed_profile(
            _mutated_profile(tmp_path, "quickset-done",
                             lambda d: d["app_user"].update(ranking_method="vibes")),
            out_dir=tmp_path, seed=SEED, now=FIXED_NOW)
    assert e.value.code == EXIT_REFUSED


def test_existing_profiles_keep_their_trio_method(seeded):
    """`ranking_method` defaults to 'trio' when a rankings block is present,
    so adding the key changed nothing for the profiles that predate it."""
    out_dir, _ = seeded["standard"]
    with _connect(out_dir, "standard") as con:
        assert con.execute(
            "SELECT ranking_method FROM users WHERE sleeper_user_id = ?",
            (APP_UID,)).fetchone()[0] == "trio"


# -- #9 / P0-6: a trade match inside the ESPN league -------------------------

def test_espn_profile_seeds_a_match_in_the_espn_league(cblock):
    """audit P0-6 / capture request #9. `trade_matches` is league-scoped with
    no platform column and `load_matches` resolves both names from
    `league_members`, so an ESPN match rides the ordinary MatchesScreen path —
    which is the finding: SendInSleeperButton returns null for an ESPN league
    (#146), so the card offers Dismiss and never says why."""
    out_dir, manifest = cblock["espn"]
    with _connect(out_dir, "espn") as con:
        matches = con.execute(
            "SELECT * FROM trade_matches WHERE league_id = ?",
            (ESPN_LEAGUE_ID,)).fetchall()
        members = {r["user_id"] for r in con.execute(
            "SELECT user_id FROM league_members WHERE league_id = ?",
            (ESPN_LEAGUE_ID,)).fetchall()}
    assert len(matches) == 1
    m = matches[0]
    assert APP_UID in (m["user_a_id"], m["user_b_id"])
    # Both parties must be league members or load_matches renders a raw id
    # where the partner's name belongs.
    assert {m["user_a_id"], m["user_b_id"]} <= members
    assert json.loads(m["user_a_give"]) and json.loads(m["user_a_receive"])
    assert manifest["counts"]["trade_matches"] == 1
    assert manifest["counts"]["awaiting_likes"] == 1


# -- mock-draft reachability: the pre-draft twin -----------------------------

def test_draft_pre_is_upcoming_with_no_picks_and_a_real_order(audit):
    """DraftRoomScreen refuses the mock with `mock-entry.blocked.live` whenever
    `board.state === 'live'` — a client-side gate the server's own
    `capability.can_start` does not override. `draft` is status drafting, so
    only an upcoming board leaves `mock-entry.start` tappable."""
    out_dir, _ = audit["draft-pre"]
    drafts = _cassette(out_dir, "draft-pre", f"league/{DRAFT_LEAGUE_ID}/drafts")
    assert len(drafts) == 1
    d = drafts[0]
    assert d["status"] == "pre_draft"
    assert d["start_time"] is None
    assert d["last_picked"] is None
    # Order still ASSIGNED — the mock resolves a real order rather than
    # falling back to the seeded shuffle labelled `randomized`.
    assert d["draft_order"] is not None and len(d["draft_order"]) == 12
    assert _cassette(out_dir, "draft-pre", f"draft/{DRAFT_ID}/picks") == []
    # Rookie-shaped and big enough: the other two mock refusals.
    assert d["settings"]["rounds"] == 4
    assert d["settings"]["teams"] == 12


def test_draft_pre_leaves_the_whole_rookie_class_undrafted(audit):
    out_dir, _ = audit["draft-pre"]
    rosters = _cassette(out_dir, "draft-pre", f"league/{DRAFT_LEAGUE_ID}/rosters")
    rostered = set().union(*[set(r["players"]) for r in rosters])
    with _connect(out_dir, "draft-pre") as con:
        rookie_ids = {r["player_id"] for r in con.execute(
            "SELECT player_id FROM players WHERE rookie_year = '2026' "
            "OR (rookie_year IS NULL AND years_exp = 0 "
            "    AND team IS NOT NULL AND team != '')").fetchall()}
    # Nothing drafted ⇒ no rookie on any roster ⇒ the board shows all 56.
    assert rookie_ids & rostered == set()
    assert len(rookie_ids) == 56


@pytest.mark.parametrize("name", AUDIT_PROFILES)
def test_audit_profile_seeding_is_deterministic(tmp_path, name):
    a = seed_profile(name, out_dir=tmp_path / "a", seed=SEED, now=FIXED_NOW)
    b = seed_profile(name, out_dir=tmp_path / "b", seed=SEED, now=FIXED_NOW)
    assert a["db_content_hash"] == b["db_content_hash"]
    assert a["counts"] == b["counts"]


# -- #11: the profiles-on flag fixture ---------------------------------------

def test_profiles_on_flags_turn_on_public_pages_only():
    """capture request #11. `profiles.user_toggle` must stay FALSE: with it on,
    `server._profile_opt_in_denied` additionally requires the user's own
    `profile_public` marker, which no fixture sets — so both /u/<username> and
    /api/profile/<username> 404 and the screen renders its error state. Turning
    it on would BREAK this capture, not strengthen it."""
    release, profiles_on = _flags("release"), _flags("profiles-on")
    assert set(release) == set(profiles_on)
    differing = {k for k in release if release[k] != profiles_on[k]}
    assert differing == {"profiles.public_pages"}
    assert profiles_on["profiles.public_pages"] is True
    assert profiles_on["profiles.user_toggle"] is False


# ---------------------------------------------------------------------------
# (k) A-16 / P1-7 — the anchors-done profile
#     RL-9: the unlock the audit found unreachable, made provable without a
#     human. The ABSENCE of exactly this fixture is why the bug survived.
# ---------------------------------------------------------------------------

ANCHOR_UID = "900000000000000010"


@pytest.fixture(scope="module")
def anchors(tmp_path_factory):
    out_dir = tmp_path_factory.mktemp("ui-test-anchors")
    return out_dir, seed_profile("anchors-done", out_dir=out_dir, seed=SEED,
                                 now=FIXED_NOW)


def test_anchors_done_is_registered():
    assert "anchors-done" in list_profiles()


def test_anchors_done_seeds_a_board_and_nothing_else(anchors):
    """The anchor lane's whole footprint is Elo overrides. If this profile
    ever grew a tiers_saved row or a swipe, it would stop proving anything:
    the `or _tiers_rule()` clause and the trio rule would each answer
    unlocked:true without the 'anchor' branch being consulted."""
    out_dir, manifest = anchors
    with _connect(out_dir, "anchors-done") as con:
        row = con.execute(
            "SELECT username, ranking_method, unlocked_formats, tiers_saved, "
            "       tier_overrides FROM users WHERE sleeper_user_id = ?",
            (ANCHOR_UID,)).fetchone()
        swipes = con.execute(
            "SELECT COUNT(*) c FROM swipe_decisions WHERE user_id = ?",
            (ANCHOR_UID,)).fetchone()["c"]

    assert row["username"] == "qa_anchors"
    assert row["ranking_method"] == "anchor"
    assert swipes == 0
    assert json.loads(row["tiers_saved"] or "{}") in ({}, {"1qb_ppr": [], "sf_tep": []})

    overrides = json.loads(row["tier_overrides"])
    assert len(overrides["sf_tep"]) == RankingService.ANCHOR_UNLOCK_MIN
    assert manifest["counts"]["anchor_tier_overrides"] == \
        RankingService.ANCHOR_UNLOCK_MIN


def test_anchors_done_leaves_the_monotonic_floor_unseeded(anchors):
    """LLD-p1-7 correction X-2, pinned. `unlocked_formats` must be EMPTY:
    get_rankings_progress applies its monotonic floor before the per-method
    ladder, so a seeded row answers unlocked:true whether or not the 'anchor'
    branch works. A fixture that passes either way proves nothing."""
    out_dir, _ = anchors
    with _connect(out_dir, "anchors-done") as con:
        uf = con.execute(
            "SELECT unlocked_formats FROM users WHERE sleeper_user_id = ?",
            (ANCHOR_UID,)).fetchone()[0]
    assert json.loads(uf or "[]") == []


def test_anchors_done_overrides_name_real_players(anchors):
    out_dir, _ = anchors
    with _connect(out_dir, "anchors-done") as con:
        overrides = json.loads(con.execute(
            "SELECT tier_overrides FROM users WHERE sleeper_user_id = ?",
            (ANCHOR_UID,)).fetchone()[0])["sf_tep"]
        known = {r["player_id"] for r in con.execute(
            "SELECT player_id FROM players").fetchall()}
    assert set(overrides) <= known
    assert all(isinstance(v, (int, float)) for v in overrides.values())


def test_anchors_with_unlocked_true_is_refused(tmp_path):
    """The trap, refused at the seeder rather than left as a comment."""
    with pytest.raises(SeederError) as e:
        seed_profile(
            _mutated_profile(tmp_path, "anchors-done",
                             lambda d: d["app_user"].update(unlocked=True)),
            out_dir=tmp_path, seed=SEED, now=FIXED_NOW)
    assert e.value.code == EXIT_REFUSED
    assert "monotonic floor" in str(e.value)


def test_anchors_under_an_incompatible_method_is_refused(tmp_path):
    """An anchored board under ranking_method 'tiers' is not a state the app
    can produce — the wizard writes 'anchor' at the point of use, first-use
    wins."""
    with pytest.raises(SeederError) as e:
        seed_profile(
            _mutated_profile(tmp_path, "anchors-done",
                             lambda d: d["app_user"].update(ranking_method="tiers")),
            out_dir=tmp_path, seed=SEED, now=FIXED_NOW)
    assert e.value.code == EXIT_REFUSED


def test_anchors_done_actually_clears_the_unlock_bar(anchors):
    """RL-9's whole point: the fixture must reach the predicate, not merely
    look plausible next to it.

    Builds a REAL RankingService from the seeded board and the seeded player
    pool and asks it the question the 'anchor' branch of
    get_rankings_progress asks. If this passes while
    test_anchor_unlock.py::test_t2 passes, the fixture and the branch meet.
    """
    out_dir, _ = anchors
    with _connect(out_dir, "anchors-done") as con:
        overrides = json.loads(con.execute(
            "SELECT tier_overrides FROM users WHERE sleeper_user_id = ?",
            (ANCHOR_UID,)).fetchone()[0])["sf_tep"]
        players = [
            Player(id=r["player_id"], name=r["full_name"], position=r["position"],
                   team=r["team"], age=None, years_experience=r["years_exp"])
            for r in con.execute(
                "SELECT player_id, full_name, position, team, years_exp "
                "FROM players").fetchall()
        ]

    svc = RankingService(players=players)
    svc._elo_overrides = dict(overrides)

    # Every seeded override names a pool player, so the pool-restricted count
    # is the full board — and it clears the bar.
    assert svc.board_override_count() == len(overrides)
    assert svc.board_override_count() >= RankingService.ANCHOR_UNLOCK_MIN
    # …with none of the evidence the OTHER unlock rules read.
    assert svc._interactions == {}
