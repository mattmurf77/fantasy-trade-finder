"""Sleeper trade universe crawler: hardening before the full pull (review findings B1-B4).

B1 leak scan: the reviewer's planting cases (names exact, embedded and glued;
ids in .gz, INTEGER and REAL cells, key columns, free pages, overflow
cells, .tmp files, log files, a subfolder seeds.txt); only the two exact
top-level operator files are excluded; the run's scan sees what finish_run
wrote; secure_delete is on; report mode says what it cannot check.
B2 allow-list: the reviewer's hostile payloads reach no byte on disk, and
discovery writes nothing raw.
B3 correctness: a first-round bye is 'playoff' in its bye week; a 5th-place
game is playoff; custom_points (a commissioner override) is the score;
simulator faults (error body, HTML, empty body, null on rosters, 403) take
their documented paths; outcomes of a season in progress record nothing;
legs going backwards in time order are counted.
B4: a failing league goes to the back of the queue and is dropped after 3
attempts (a deleted league at once; --retry-failed requeues); the seed rule;
no walk-back request is spent once the cap is full.
"""
from __future__ import annotations

import gzip
import json
import shutil
import sqlite3
from pathlib import Path

import pytest

from backend.sleeper_universe import client as cl, store as store_mod
from backend.sleeper_universe.discover import Discoverer
from backend.sleeper_universe.identity import Collector, KeyRing
from backend.sleeper_universe.report import build_report, leak_scan
from backend.sleeper_universe.store import Store
from backend.tests.support.sleeper_universe_world import (
    TEST_KEY, FakeClock, L, U, connect, run_cli, standard_world)

RING = KeyRing(TEST_KEY.encode())


def independent_scan(d: Path, needles) -> dict:
    """Not the crawler's scanner: raw bytes, gunzipped bytes, and every
    SQLite cell compared as text and as number."""
    found = {}
    for p in sorted(d.rglob("*")):
        if not p.is_file():
            continue
        raw = p.read_bytes()
        blobs = [raw] + ([gzip.decompress(raw)] if raw[:2] == b"\x1f\x8b" else [])
        cells = []
        if raw[:16] == b"SQLite format 3\x00":
            c = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
            for (t,) in c.execute("SELECT name FROM sqlite_master WHERE type='table'"):
                cells += [str(r[1]) for r in c.execute(f"PRAGMA table_info('{t}')")]
                for row in c.execute(f"SELECT * FROM '{t}'"):
                    cells += [str(int(v)) if isinstance(v, float) and v.is_integer() else str(v)
                              for v in row if v is not None]
            c.close()
        for n in needles:
            if any(str(n).encode() in b for b in blobs) or any(str(n) in x for x in cells):
                found.setdefault(n, []).append(str(p.relative_to(d)))
    return found


@pytest.fixture(scope="module")
def clean(tmp_path_factory):
    d = tmp_path_factory.mktemp("clean") / "data"
    w = standard_world()
    assert run_cli(w, d, "run")[0] == 0
    return w, d


def _copy(clean, tmp_path):
    d = tmp_path / "data"
    shutil.copytree(clean[1], d)
    return d


def _sql(d, q, *a):
    c = sqlite3.connect(str(d / "universe.sqlite"))
    c.execute(q, a)
    c.commit()
    c.close()


NAME, NAME_LONG, UID = "secretusername004", "Secret Team Name Number 004", U(4)

PLANTS = {
    "name exact in a TEXT cell": lambda d: _sql(d, "UPDATE leagues SET status=? WHERE rowid=1", NAME),
    "name inside a longer string": lambda d: _sql(d, "UPDATE leagues SET status=? WHERE rowid=1", "owner " + NAME),
    "multi-word team name": lambda d: _sql(d, "UPDATE leagues SET status=? WHERE rowid=1", NAME_LONG),
    "name glued to other text in a -wal file": lambda d: (d / "universe.sqlite-wal").write_bytes(b"\x00junk" + NAME.encode()),
    "name embedded in a .gz": lambda d: (d / "raw" / "x.json.gz").write_bytes(gzip.compress(json.dumps({"x": "by " + NAME}).encode())),
    "name in a plain-text log": lambda d: (d / "run.log").write_text(f"resolved seed {NAME}\n"),
    "username as a column name": lambda d: _sql(d, f"CREATE TABLE z ({NAME} TEXT)"),
    "name in a free page": lambda d: (_sql(d, "CREATE TABLE junk(v TEXT)"), _sql(d, "INSERT INTO junk VALUES (?)", NAME), _sql(d, "DELETE FROM junk")),
    "name and id in a gz .tmp": lambda d: (d / "raw" / "x.json.tmp").write_bytes(gzip.compress(json.dumps({"n": NAME, "u": UID}).encode())),
}
ID_PLANTS = {
    "id in a .gz": lambda d: (d / "raw" / "x.json.gz").write_bytes(gzip.compress(json.dumps({"x": UID}).encode())),
    "id as INTEGER": lambda d: _sql(d, "UPDATE rosters SET division=? WHERE rowid=1", int(UID)),
    "id as REAL": lambda d: _sql(d, "UPDATE rosters SET fpts=? WHERE rowid=1", float(UID)),
    "id whole in league_members.user_key": lambda d: _sql(d, "UPDATE league_members SET user_key=? WHERE rowid=1", UID),
    "id whole in rosters.owner_key": lambda d: _sql(d, "UPDATE rosters SET owner_key=? WHERE rowid=1", UID),
    "id whole in draft_picks.picked_by_key": lambda d: _sql(d, "UPDATE draft_picks SET picked_by_key=? WHERE rowid=1", UID),
    "id in a free page": lambda d: (_sql(d, "CREATE TABLE junk(v TEXT)"), _sql(d, "INSERT INTO junk VALUES (?)", UID), _sql(d, "DELETE FROM junk")),
    "id in a long overflow cell": lambda d: _sql(d, "UPDATE leagues SET settings_json=? WHERE rowid=1", "z" * 4093 + UID + "z" * 9000),
    "id in a subfolder seeds.txt": lambda d: (d / "raw" / "seeds.txt").write_text(UID),
    "id in a subfolder hmac.key": lambda d: (d / "raw" / "hmac.key").write_text(UID),
}


def test_clean_store_passes_both_modes(clean):
    w, d = clean
    assert leak_scan(d, RING, names=w.all_names(), raw_ids=w.all_user_ids())["ok"]
    rep = leak_scan(d, RING, report_mode=True)
    assert rep["ok"] and rep["not_checked"]


@pytest.mark.parametrize("plant", sorted(PLANTS))
def test_run_scan_catches_names(clean, tmp_path, plant):
    w, _ = clean
    d = _copy(clean, tmp_path)
    PLANTS[plant](d)
    assert not leak_scan(d, RING, names=w.all_names(), raw_ids=w.all_user_ids())["ok"]


@pytest.mark.parametrize("plant", sorted(ID_PLANTS))
def test_both_modes_catch_member_ids(clean, tmp_path, plant):
    w, _ = clean
    d = _copy(clean, tmp_path)
    ID_PLANTS[plant](d)
    assert not leak_scan(d, RING, names=w.all_names(), raw_ids=w.all_user_ids())["ok"]
    assert not leak_scan(d, RING, report_mode=True)["ok"]


def test_only_the_two_top_level_operator_files_are_skipped(clean, tmp_path):
    d = _copy(clean, tmp_path)
    (d / "seeds.txt").write_text(f"{NAME}\n{UID}\n")
    res = leak_scan(d, RING, names={NAME}, raw_ids={UID})
    assert res["ok"] and res["excluded"] == ["hmac.key", "seeds.txt"]


def test_run_scan_sees_what_finish_run_writes(tmp_path, monkeypatch):
    real = Store.finish_run

    def finish_run(self, run_id, *a, **k):
        real(self, run_id, *a, **k)
        self.conn.execute("UPDATE runs SET summary_json=? WHERE run_id=?",
                          (json.dumps({"x": U(3)}), run_id))
    monkeypatch.setattr(Store, "finish_run", finish_run)
    code, _ = run_cli(standard_world(), tmp_path, "discover")
    assert code == 4


def test_secure_delete_is_on(tmp_path):
    st = Store(tmp_path)
    assert st.conn.execute("PRAGMA secure_delete").fetchone()[0] == 1


# -- B2 -----------------------------------------------------------------------------

def _hostile_world():
    w = standard_world()
    lg = w.routes[f"league/{L(103)}"]
    lg["sport"] = "secretusername002"
    lg["draft_id"] = "secretusername021"
    lg["settings"][U(4)] = 1
    lg["settings"]["commish"] = int(U(5))
    lg["settings"]["stranger"] = 733459678624915456
    lg["scoring_settings"]["secretusername006"] = 1.0
    w.routes[f"league/{L(103)}/rosters"][0]["settings"]["ownerid"] = int(U(7))
    w.routes[f"league/{L(103)}/rosters"][2]["keepers"] = ["Bo7", "secretusername022"]
    w.routes[f"league/{L(103)}/rosters"][3]["players"].append("733459678624915456")
    w.routes[f"league/{L(103)}/matchups/1"][0]["players_points"][U(8)] = 1.0
    t = w.routes[f"league/{L(103)}/transactions/1"][0]
    t["adds"] = dict(t.get("adds") or {}, secretusername010=1)
    w.routes[f"league/{L(103)}/transactions/2"][0]["transaction_id"] = "secretusername011"
    w.routes[f"league/{L(103)}/transactions/3"][0]["type"] = "x.secretusername016"
    d0 = w.routes[f"league/{L(103)}/drafts"][0]
    d0["settings"]["Zorblaxian"] = 1
    d0["slot_to_roster_id"]["9"] = int(U(14))
    w.routes[f"draft/{d0['draft_id']}/picks"][0]["metadata"]["position"] = "secretusername013"
    w.routes[f"league/{L(102)}/winners_bracket"][0]["t1"] = int(U(12))
    w.nfl_state["season_start_date"] = "secretusername015"
    w.listed_only(506, 2026, [1], status="Commish Dave's League")
    w.listed_only(507, 2026, [1], type_=0, prev="secretusername020")
    needles = ["secretusername002", "secretusername021", U(4), U(5), "733459678624915456",
               "secretusername006", U(7), "Bo7", "secretusername022", U(8), "secretusername010",
               "secretusername011", "secretusername016", "Zorblaxian", U(14), "secretusername013",
               U(12), "secretusername015", "Commish Dave", "secretusername020"]
    return w, needles


def test_hostile_payloads_reach_no_byte_on_disk(tmp_path):
    w, needles = _hostile_world()
    code, lines = run_cli(w, tmp_path, "run")
    assert code == 0, lines
    assert independent_scan(tmp_path, needles) == {}


# -- B3 -----------------------------------------------------------------------------

@pytest.fixture(scope="module")
def full(tmp_path_factory):
    d = tmp_path_factory.mktemp("b3") / "data"
    w = standard_world()
    assert run_cli(w, d, "run")[0] == 0
    c = connect(d)
    yield w, c
    c.close()


def test_bye_seeds_are_playoff_in_their_bye_week(full):
    w, c = full
    ph = {(r["week"], r["roster_id"]): r["phase"] for r in c.execute(
        "SELECT week, roster_id, phase FROM matchups WHERE league_id=?", (L(301),))}
    assert ph[(4, 1)] == ph[(4, 2)] == "playoff"            # byes, first playoff week
    assert ph[(4, 3)] == ph[(4, 6)] == "playoff"
    assert ph[(5, 5)] == ph[(5, 6)] == "playoff"            # 5th-place game
    assert ph[(6, 5)] == "consolation" and ph[(6, 1)] == "playoff"
    assert {ph[(wk, r)] for wk in (4, 5, 6) for r in (7, 8)} == {"consolation"}
    o = {r["roster_id"]: dict(r) for r in c.execute("SELECT * FROM outcomes WHERE league_id=?",
                                                     (L(301),))}
    assert o[1]["champion"] == 1 and o[5]["final_place"] == 5 and o[7]["final_place"] == 7


def test_custom_points_are_the_score(full):
    w, c = full
    m = c.execute("SELECT * FROM matchups WHERE league_id=? AND week=2 AND roster_id=5",
                  (L(301),)).fetchone()
    assert m["points"] == 0.5 and m["custom"] == 1 and m["points_original"] != 0.5
    s = c.execute("SELECT week_result FROM standings_weeks WHERE league_id=? AND week=2 AND"
                  " roster_id=5", (L(301),)).fetchone()
    assert s[0] == "L"


def test_season_in_progress_records_no_outcome(full):
    w, c = full
    rows = c.execute("SELECT made_playoffs, seed, champion, finish_basis FROM outcomes"
                     " WHERE league_id=?", (L(103),)).fetchall()
    assert rows and all(tuple(r) == (None, None, None, "season_in_progress") for r in rows)


def test_leg_time_inversions_are_counted(full, tmp_path):
    w, c = full
    assert build_report(c)["leg_time_inversions"] == 0
    d = tmp_path / "copy.sqlite"
    shutil.copy(c.execute("PRAGMA database_list").fetchone()[2], d)
    c2 = sqlite3.connect(str(d))
    c2.row_factory = sqlite3.Row
    last = c2.execute("SELECT transaction_id FROM transactions WHERE league_id=? AND"
                      " status='complete' ORDER BY status_updated DESC LIMIT 1", (L(101),)).fetchone()[0]
    c2.execute("UPDATE transactions SET leg=0 WHERE transaction_id=?", (last,))
    assert build_report(c2)["leg_time_inversions"] == 1


@pytest.mark.parametrize("path, status, body, expect", [
    (f"league/{L(102)}", 200, b'{"error": "internal"}', "league_id_mismatch"),
    (f"league/{L(102)}/drafts", 200, b"", "league.drafts:empty_body"),
    (f"league/{L(102)}/rosters", 200, b"null", "league.rosters:not_a_list"),
    (f"league/{L(102)}/users", 200, b"<html>oops</html>", cl.BadResponseStop.exit_code),
    (f"league/{L(102)}/traded_picks", 403, b"", cl.BlockedStop.exit_code),
])
def test_simulated_faults_take_their_paths(tmp_path, path, status, body, expect):
    w = standard_world()
    w.faults[path] = (status, body)
    code, _ = run_cli(w, tmp_path, "run")
    c = connect(tmp_path)
    assert c.execute("SELECT COUNT(*) FROM pull_checkpoints WHERE league_id=?",
                     (L(102),)).fetchone()[0] == 0
    if isinstance(expect, int):
        assert code == expect
    else:
        assert c.execute("SELECT kind FROM pull_failures WHERE league_id=?",
                         (L(102),)).fetchone()[0] == expect


# -- B4 -----------------------------------------------------------------------------

def test_failing_league_goes_last_and_is_dropped_after_three(tmp_path):
    w = standard_world()
    w.faults[f"league/{L(101)}/users"] = (400, b"")
    assert run_cli(w, tmp_path, "discover")[0] == 0
    run_cli(w, tmp_path, "pull", "--limit", "1")          # L(101) first in order: fails
    run_cli(w, tmp_path, "pull", "--limit", "1")          # pulls another league instead
    c = connect(tmp_path)
    assert c.execute("SELECT COUNT(*) FROM pull_checkpoints").fetchone()[0] == 1
    assert c.execute("SELECT attempts FROM pull_failures WHERE league_id=?",
                     (L(101),)).fetchone()[0] == 1
    c.close()
    st = Store(tmp_path)
    for _ in range(2):
        st.record_failure(L(101), 2024, 9, "league.users:400")
    assert L(101) not in [r[0] for r in st.leagues_to_pull([2024, 2025, 2026])]
    st.record_failure(L(102), 2025, 9, "not_found", permanent=True)
    assert L(102) not in [r[0] for r in st.leagues_to_pull([2024, 2025, 2026])]
    st.close()
    code, lines = run_cli(standard_world(), tmp_path, "pull", "--retry-failed", "--limit", "1")
    assert any(x.startswith("retry-failed: 2") for x in lines)


class _Rec:
    def __init__(self):
        self.paths = []

    def get(self, path, expect=None, null_ok=False):
        self.paths.append(path)
        return {"user_id": "9100000000000000077"}


@pytest.mark.parametrize("line, want, requested", [
    ("id:12345", "12345", False),
    ("9100000000000000077", "9100000000000000077", False),
    ("user:1234567", "9100000000000000077", True),
    ("12345678901234", "9100000000000000077", True),     # 14 digits: a username
    ("someone", "9100000000000000077", True),
])
def test_seed_rule(tmp_path, line, want, requested):
    rec = _Rec()
    d = Discoverer(Store(tmp_path), rec, RING, Collector(), seasons=[2026], log=lambda *a: None)
    assert d._resolve_seed(line, 1) == want
    assert bool(rec.paths) == requested


def test_no_walk_back_request_once_the_cap_is_full(tmp_path):
    w = standard_world()
    w.listing_add(U(1), 2026, w.routes[f"league/{L(201)}"])   # B26 points back to 2023
    run_cli(w, tmp_path, "discover", "--cap", "1", "--seasons", "2023", "2024", "2025", "2026")
    assert f"league/{L(200)}" not in w.calls
    c = connect(tmp_path)
    assert c.execute("SELECT skip_reason FROM league_index WHERE league_id=?",
                     (L(201),)).fetchone()[0] == "cap_reached"
