"""backend/universe_values.py — dated DynastyProcess boards for the trade-universe
research store. Synthetic fixtures only: a tiny git repository built per test
stands in for a clone of dynastyprocess/data. No network (guarded below)."""

import csv
import datetime as dt
import os
import sqlite3
import subprocess

import pytest

from backend import dp_values_history as dvh
from backend import universe_values as uv

pytestmark = pytest.mark.usefixtures("no_real_network")

HEADER = ("player,pos,team,age,draft_year,ecr_1qb,ecr_2qb,ecr_pos,"
          "value_1qb,value_2qb,scrape_date,fp_id")

XWALK = """name,merge_name,position,team,sleeper_id,fantasypros_id,ktc_id,mfl_id
Alpha Back,alpha back,RB,AAA,1001,9001,501,13001
Bravo Receiver II,bravo receiver ii,WR,BBB,1002,NA,502,13002
Charlie Passer,charlie passer,QB,CCC,1003,9003,503,13003
Delta Tight,delta tight,TE,DDD,1004,NA,NA,NA
"""


def players_csv(alpha_1qb=5000, extra_rows=()):
    rows = [
        'Alpha Back,RB,AAA,24.1,2022,1,1,1,%d,4000,2024-01-04,9001' % alpha_1qb,
        'Bravo Receiver,WR,BBB,25.0,2021,2,2,1,4500,4200,2024-01-04,NA',
        'Charlie Passer,QB,CCC,27.3,2019,3,1,1,3000,8000,2024-01-04,9003',
        'Delta Tight,TE,DDD,26.0,2020,4,4,1,2000,1500,2024-01-04,7777',
        'Echo Unknown,WR,EEE,22.0,2024,5,5,2,1000,900,2024-01-04,9999',
        'Foxtrot Nofp,RB,FFF,23.0,2023,6,6,2,800,700,2024-01-04,NA',
    ]
    return "\n".join([HEADER, *rows, *extra_rows]) + "\n"


def combined_csv(labels=("2024 Pick 1.01", "2024 Early 1st", "2025 1st")):
    out = [HEADER, 'Alpha Back,RB,AAA,24.1,2022,1,1,1,5000,4000,2024-01-04,9001']
    for i, lab in enumerate(labels):
        out.append('%s,PICK,NA,NA,NA,1,1,NA,%d,%d,2024-01-04,NA' % (lab, 3000 - i * 100, 3500 - i * 100))
    return "\n".join(out) + "\n"


class FakeDP:
    """A git repository with the DynastyProcess file layout."""

    def __init__(self, root):
        self.root = str(root)
        os.makedirs(self.root, exist_ok=True)
        self.env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
        self.git("init", "-q", "-b", "main")
        self.shas = []

    def git(self, *args, env=None):
        return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t",
                               "-c", "commit.gpgsign=false", *args], cwd=self.root,
                              env=env or self.env, check=True, capture_output=True,
                              text=True).stdout

    def commit(self, when, files, remove=()):
        for path, text in files.items():
            full = os.path.join(self.root, path)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "w") as f:
                f.write(text)
            self.git("add", path)
        for path in remove:
            self.git("rm", "-q", path)
        env = dict(self.env, GIT_AUTHOR_DATE=when, GIT_COMMITTER_DATE=when)
        self.git("commit", "-q", "-m", when, env=env)
        sha = self.git("rev-parse", "HEAD").strip()
        self.shas.append(sha)
        return sha


def standard_repo(tmp_path):
    dp = FakeDP(tmp_path / "dp")
    dp.commit("2023-12-20T05:00:00Z", {uv.PLAYERS_PATH: players_csv(4900),
                                       uv.COMBINED_PATH: combined_csv(),
                                       uv.PLAYERIDS_PATH: XWALK})
    dp.commit("2024-01-05T04:00:00Z", {uv.PLAYERS_PATH: players_csv(5000)})
    dp.commit("2024-01-05T20:00:00Z", {uv.PLAYERS_PATH: players_csv(5100)})
    # Known-subset header (no age/fp_id/ecr), values.csv gone, values-picks.csv instead.
    dp.commit("2024-02-20T04:00:00Z", {
        uv.PLAYERS_PATH: "player,pos,team,value_1qb,value_2qb,scrape_date\n"
                         "Alpha Back,RB,AAA,5200,4100,2024-02-19\n",
        uv.PICKS_PATH: "player,pos,value_1qb,value_2qb,scrape_date\n"
                       "2024 Pick 1.01,PICK,3300,3700,2024-02-19\n"},
        remove=(uv.COMBINED_PATH,))
    dp.commit("2024-03-10T04:00:00Z", {"README.md": "not a values commit\n"})
    return dp


@pytest.fixture
def built(tmp_path):
    dp = standard_repo(tmp_path)
    db = str(tmp_path / "v.sqlite")
    summary = uv.build_dp(dp.root, db, start=dt.date(2024, 1, 1))
    return dp, db, summary


def boards(db):
    with sqlite3.connect(db) as c:
        return c.execute("SELECT format, board_date, commit_sha, header, picks_file, "
                         "published_at FROM value_boards WHERE source='dp' "
                         "ORDER BY format, board_date").fetchall()


# --- history selection ------------------------------------------------------

def test_one_board_per_commit_day_and_the_days_last_commit_wins(built):
    dp, db, _ = built
    b = [r for r in boards(db) if r[0] == "1qb"]
    assert [r[1] for r in b] == ["2023-12-20", "2024-01-05", "2024-02-20"]
    assert b[1][2] == dp.shas[2]            # the 20:00 commit, not the 04:00 one
    assert len([r for r in boards(db) if r[0] == "sf"]) == 3
    assert uv.value_on("2024-01-06", "1001", "1qb", db_path=db).value == 5100


def test_start_keeps_the_last_board_before_it(built):
    _, db, summary = built
    assert summary["first"] == "2023-12-20"
    lk = uv.value_on("2024-01-02", "1001", "1qb", db_path=db)
    assert (lk.value, lk.board_date, lk.age_days) == (4900, "2023-12-20", 13)


# --- lookups ----------------------------------------------------------------

def test_value_on_latest_board_at_or_before_with_age_and_format(built):
    _, db, _ = built
    lk = uv.value_on(dt.date(2024, 1, 31), "1003", "1qb", db_path=db)
    assert (lk.value, lk.board_date, lk.age_days) == (3000, "2024-01-05", 26)
    assert uv.value_on(dt.date(2024, 1, 31), "1003", "superflex", db_path=db).value == 8000
    # 1003 is absent from the 2024-02-20 board: the lookup says so via latest_board_date
    late = uv.value_on("2024-03-01", "1003", "sf", db_path=db)
    assert (late.board_date, late.latest_board_date, late.age_days) == ("2024-01-05", "2024-02-20", 56)
    assert not uv.value_on("2023-12-01", "1001", "1qb", db_path=db).found
    with pytest.raises(ValueError):
        uv.value_on("2024-01-31", "1001", "tep", db_path=db)


def test_datetime_lookup_uses_the_publish_instant(built):
    _, db, _ = built
    # 2024-01-05 03:00Z is before that day's first commit: the 2023-12-20 board.
    early = uv.value_on("2024-01-05T03:00:00Z", "1001", "1qb", db_path=db)
    assert early.board_date == "2023-12-20"
    # a plain date allows same-day boards
    assert uv.value_on("2024-01-05", "1001", "1qb", db_path=db).board_date == "2024-01-05"


# --- joins ------------------------------------------------------------------

def test_join_tiers_and_unmapped_listed_by_dp_id(built):
    _, db, _ = built
    with sqlite3.connect(db) as c:
        bid = c.execute("SELECT board_id FROM value_boards WHERE source='dp' AND "
                        "format='1qb' AND board_date='2024-01-05'").fetchone()[0]
        tiers = dict(c.execute('SELECT asset_key, match_tier FROM "values" WHERE '
                               "board_id=? AND asset_type='player'", (bid,)).fetchall())
        unm = sorted(r[0] for r in c.execute(
            "SELECT source_key FROM unmapped WHERE board_id=?", (bid,)))
        age = c.execute('SELECT age FROM "values" WHERE board_id=? AND asset_key=?',
                        (bid, "1003")).fetchone()[0]
    assert tiers == {"1001": "fp_id", "1002": "name_suffix", "1003": "fp_id", "1004": "name"}
    assert unm == ["9999", "name:Foxtrot Nofp|RB"]
    assert age == 27.3


def test_fp_id_must_agree_on_position():
    xw = uv.crosswalk_from_text(XWALK)
    # fp 9001 is an RB in the crosswalk; a TE row carrying it falls to the name tier
    assert uv.resolve_dp_row({"player": "Delta Tight", "pos": "TE", "fp_id": "9001"}, xw) == ("1004", "name")
    assert uv.resolve_dp_row({"player": "Nobody", "pos": "RB", "fp_id": "9001.0"}, xw) == ("1001", "fp_id")


def test_name_tiers_match_dp_values_history_on_a_committed_board():
    rows, _ = dvh.load_snapshot_rows("2024-09-05")
    from backend import espn_service
    with open(espn_service._SNAPSHOT_PATH) as f:
        xw = uv.crosswalk_from_text(f.read())
    oracle, report = dvh.build_value_map(rows, scoring="1qb", crosswalk=dvh.default_crosswalk())
    ours = {}
    for r in rows:
        sid, _ = uv.resolve_by_name(r["player"], r["pos"].strip().upper(), xw)
        if sid:
            ours.setdefault(sid, float(r["value_1qb"] or 0))
    assert ours == oracle
    assert report.matched > 400


# --- layouts ----------------------------------------------------------------

def test_unknown_header_fails_loudly_lists_the_commit_and_writes_nothing(tmp_path):
    dp = standard_repo(tmp_path)
    bad = dp.commit("2024-03-15T04:00:00Z", {
        uv.PLAYERS_PATH: "player,pos,value_1qb,value_2qb,value_sf\nAlpha Back,RB,1,2,3\n"})
    db = str(tmp_path / "v.sqlite")
    with pytest.raises(uv.LayoutError) as e:
        uv.build_dp(dp.root, db, start=dt.date(2024, 1, 1))
    assert bad in str(e.value) and "value_sf" in str(e.value)
    assert not os.path.exists(db) or not boards(db)


def test_known_subset_header_and_picks_file_fallback(built):
    dp, db, summary = built
    feb = [r for r in boards(db) if r[0] == "1qb" and r[1] == "2024-02-20"][0]
    assert feb[3] == "player,pos,team,value_1qb,value_2qb,scrape_date"
    assert feb[4] == "values-picks.csv"
    assert len(summary["headers"]) == 2
    with sqlite3.connect(db) as c:
        assert c.execute('SELECT age FROM "values" v JOIN value_boards b USING(board_id) '
                         "WHERE b.board_date='2024-02-20' AND asset_key='1001'").fetchone()[0] is None
    lk = uv.value_on("2024-02-21", "pick:2024:1:01", "sf", db_path=db)
    assert (lk.value, lk.board_date) == (3700, "2024-02-20")


def test_unknown_pick_label_fails_the_build(tmp_path):
    dp = standard_repo(tmp_path)
    bad = dp.commit("2024-03-15T04:00:00Z", {uv.PLAYERS_PATH: players_csv(),
                                             uv.COMBINED_PATH: combined_csv(("2024 Pick One",))})
    with pytest.raises(uv.LayoutError) as e:
        uv.build_dp(dp.root, str(tmp_path / "v.sqlite"), start=dt.date(2024, 1, 1))
    assert bad in str(e.value) and "2024 Pick One" in str(e.value)


# --- picks ------------------------------------------------------------------

def test_pick_labels_and_buckets():
    assert uv.parse_pick_label("2026 Pick 1.01") == "pick:2026:1:01"
    assert uv.parse_pick_label("2026 Pick 2.12") == "pick:2026:2:12"
    assert uv.parse_pick_label("2027 Early 1st") == "pick:2027:1:early"
    assert uv.parse_pick_label("2027  late 3rd") == "pick:2027:3:late"
    assert uv.parse_pick_label("2028 2nd") == "pick:2028:2"
    assert uv.parse_pick_label("pick:2028:2:mid") == "pick:2028:2:mid"
    for bad in ("2027 Early 1nd", "2027 Pick", "Early 1st", "2028 2st"):
        with pytest.raises(ValueError):
            uv.parse_pick_label(bad)
    assert [uv.slot_bucket(s) for s in (1, 4, 5, 8, 9, 12)] == ["early"] * 2 + ["mid"] * 2 + ["late"] * 2
    assert [uv.slot_bucket(s, 10) for s in (3, 4, 6, 7)] == ["early", "mid", "mid", "late"]


def test_pick_value_on_falls_back_slot_bucket_round(built):
    _, db, _ = built
    s = uv.ValueStore(db)
    try:
        when = "2024-01-10"
        assert s.pick_value_on(when, 2024, 1, "1qb", slot=1).resolution == "slot"
        b = s.pick_value_on(when, 2024, 1, "1qb", slot=2)
        assert (b.resolution, b.value) == ("bucket", 2900)       # no 1.02 row: Early 1st
        assert s.pick_value_on(when, 2024, 1, "1qb", slot=1, teams=10).resolution == "bucket"
        r = s.pick_value_on(when, 2025, 1, "1qb", bucket="late")
        assert (r.resolution, r.value) == ("round", 2800)
        assert not s.pick_value_on(when, 2026, 1, "1qb").found
    finally:
        s.close()


# --- store ------------------------------------------------------------------

def test_rebuild_is_idempotent(tmp_path):
    dp = standard_repo(tmp_path)
    db = str(tmp_path / "v.sqlite")
    uv.build_dp(dp.root, db, start=dt.date(2024, 1, 1))
    first = boards(db)
    uv.build_dp(dp.root, db, start=dt.date(2024, 1, 1))
    assert [r[1:] for r in boards(db)] == [r[1:] for r in first]


def test_coverage_report(built, tmp_path):
    _, db, _ = built
    lk = tmp_path / "lookups.csv"
    lk.write_text("asset_key,date\n1001,2024-01-10\n1001,2024-02-01\n1003,2024-03-30\n42,2024-01-10\n")
    rep = uv.coverage_report(db, lookups=uv.read_lookups(str(lk)), max_age=14)
    s = rep["sources"]["dp/1qb"]
    assert s["boards"] == 3
    assert s["boards_per_month"] == {"2023-12": 1, "2024-01": 1, "2024-02": 1}
    assert (s["longest_gap_days"], s["longest_gap"]) == (46, ["2024-01-05", "2024-02-20"])
    assert s["player_rows_unmapped"] == 4 and s["player_rows_mapped"] == 9
    assert rep["lookups"]["1qb"]["within_max_age"] == {"dp": 1}
    assert "longest gap 46 days" in uv.format_report(rep)


def test_load_dated_csv_maps_ids_and_picks(tmp_path):
    f = tmp_path / "ktc.csv"
    f.write_text("date,format,asset_type,asset_id,id_type,name,position,value\n"
                 "2024-01-02,sf,player,1001,sleeper,,RB,7000\n"
                 "2024-01-02,sf,player,502,ktc,,WR,6000\n"
                 "2024-01-02,sf,player,888,ktc,Charlie Passer,QB,9000\n"
                 "2024-01-02,sf,player,777,ktc,Nobody,WR,100\n"
                 "2024-01-02,sf,pick,2025 Mid 1st,,,,5000\n")
    db = str(tmp_path / "v.sqlite")
    out = uv.load_dated_csv(str(f), db, source="ktc", xw=uv.crosswalk_from_text(XWALK))
    assert out == {"boards": 1, "rows": 5}
    with sqlite3.connect(db) as c:
        got = dict(c.execute('SELECT asset_key, match_tier FROM "values"').fetchall())
        unm = [r[0] for r in c.execute("SELECT source_key FROM unmapped")]
    assert got == {"1001": "sleeper_id", "1002": "ktc_id", "1003": "name", "pick:2025:1:mid": None}
    assert unm == ["ktc:777"]
    bad = tmp_path / "bad.csv"
    bad.write_text("date,format,asset_type,asset_id,value,extra\n")
    with pytest.raises(uv.LayoutError):
        uv.load_dated_csv(str(bad), db, source="ktc")
