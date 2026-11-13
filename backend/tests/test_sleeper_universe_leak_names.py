"""Sleeper trade universe crawler: leak-scan name rules after the live smoke run (commit D).

A two-league live run failed the scan on a player named "J.J.": its words
("J", "J") met two one-letter words in the SQLite file's raw bytes.
Covers, each both ways:
- a name made only of stored-scalar words ("J.J.", "QB 1", "2025") is
  ambiguous: skipped and counted; a real name still hits;
- the raw-bytes pass checks only names of RAW_MIN_CHARS+ word characters (a
  long name in a freed page still fails; a short one there is counted as
  excluded); decoded cells check every name (a short real name in a cell
  fails);
- the schema is checked against every name (a short username as a column);
- every hit reports a location (file:table.column, a JSON key path, a page)
  plus the name's source field and shape, and never the name;
- stored vocabulary comes from what the crawler writes;
- harvest records each name's source field.
"""
from __future__ import annotations

import gzip
import json
import shutil
import sqlite3

import pytest

from backend.sleeper_universe import identity
from backend.sleeper_universe.report import (
    RAW_MIN_CHARS, _NameIndex, is_stored_scalar, leak_scan)
from backend.tests.support.sleeper_universe_world import TEST_KEY, run_cli, standard_world

RING = identity.KeyRing(TEST_KEY.encode())
LONG = "Secret Team Name Number 004"          # 23 word characters
SHORT = "Zed Quoxa"                           # 8 word characters, not vocabulary


@pytest.fixture(scope="module")
def clean(tmp_path_factory):
    d = tmp_path_factory.mktemp("leaknames") / "data"
    assert run_cli(standard_world(), d, "run")[0] == 0
    return d


def _copy(clean, tmp_path):
    d = tmp_path / "data"
    shutil.copytree(clean, d)
    return d


def _sql(d, q, *a):
    c = sqlite3.connect(str(d / "universe.sqlite"))   # no secure_delete: freed pages keep data
    c.execute(q, a)
    c.commit()
    c.close()


NAMES = {LONG: {"league.users.team_name"}, SHORT: {"league.users.display_name"},
         "J.J.": {"draft.picks.first_name"}, "QB 1": {"league.users.team_name"},
         "2025": {"league.users.team_name"}}


def _no_names(res):
    text = json.dumps(res)
    return all(n not in text for n in (LONG, SHORT, "Quoxa", "Number 004"))


def test_names_made_only_of_stored_words_are_ambiguous(clean, tmp_path):
    idx = _NameIndex(NAMES)
    assert idx.ambiguous == 3 and len(idx) == 2
    d = _copy(clean, tmp_path)
    _sql(d, "UPDATE leagues SET status=? WHERE rowid=1", "J J QB 1 2025")
    res = leak_scan(d, RING, names=NAMES)
    assert res["ok"] and res["ambiguous_names_skipped"] == 3


def test_real_multiword_name_in_a_cell_fails_with_location(clean, tmp_path):
    d = _copy(clean, tmp_path)
    _sql(d, "UPDATE leagues SET status=? WHERE rowid=1", "by " + LONG)
    res = leak_scan(d, RING, names=NAMES)
    assert not res["ok"]
    loc = [h for h in res["name_hit_locations"] if h["where"] == "universe.sqlite:leagues.status"]
    assert loc and loc[0]["sources"] == ["league.users.team_name"]
    assert (loc[0]["words"], loc[0]["chars"]) == (5, 23)
    assert _no_names(res)


def test_short_real_name_in_a_cell_still_fails(clean, tmp_path):
    d = _copy(clean, tmp_path)
    _sql(d, "UPDATE leagues SET status=? WHERE rowid=1", SHORT)
    res = leak_scan(d, RING, names=NAMES)
    assert not res["ok"] and _no_names(res)


def test_real_name_in_a_raw_file_reports_the_key_path(clean, tmp_path):
    d = _copy(clean, tmp_path)
    (d / "raw" / "x.json.gz").write_bytes(gzip.compress(json.dumps(
        {"users": [{"user_key": "k", LONG: 1, "team": LONG}]}).encode()))
    res = leak_scan(d, RING, names=NAMES)
    assert not res["ok"]
    where = {h["where"] for h in res["name_hit_locations"]}
    assert "raw/x.json.gz:$.users[].<key>" in where
    assert _no_names(res)


def test_freed_page_long_name_fails_short_name_is_excluded(clean, tmp_path):
    d = _copy(clean, tmp_path)
    _sql(d, "CREATE TABLE junk(v TEXT)")
    _sql(d, "INSERT INTO junk VALUES (?)", LONG + " | " + SHORT)
    _sql(d, "DELETE FROM junk")
    _sql(d, "DROP TABLE junk")
    res = leak_scan(d, RING, names=NAMES)
    assert not res["ok"]
    pages = [h for h in res["name_hit_locations"] if "@page" in h["where"]]
    assert pages and all(h["chars"] >= RAW_MIN_CHARS for h in pages)
    assert res["names_excluded_from_raw_bytes_pass"] == 1           # the short one
    assert _no_names(res)


def test_short_name_in_raw_bytes_only_is_not_a_hit(clean, tmp_path):
    d = _copy(clean, tmp_path)
    _sql(d, "CREATE TABLE junk(v TEXT)")
    _sql(d, "INSERT INTO junk VALUES (?)", SHORT)
    _sql(d, "DELETE FROM junk")
    _sql(d, "DROP TABLE junk")
    res = leak_scan(d, RING, names=NAMES)
    assert res["ok"] and res["names_excluded_from_raw_bytes_pass"] == 1


def test_short_username_as_a_column_name_fails_via_the_schema(clean, tmp_path):
    d = _copy(clean, tmp_path)
    _sql(d, "CREATE TABLE z (Quoxa TEXT, Zed TEXT)")
    res = leak_scan(d, RING, names={"Zed Quoxa": {"x"}, "Quoxa": {"league.users.username"}})
    assert not res["ok"]
    assert any(h["where"] == "universe.sqlite:schema" for h in res["name_hit_locations"])


def test_stored_vocabulary_comes_from_what_the_crawler_writes():
    for w in ("consolation", "season_in_progress", "reversed_within_day", "points_original",
              "winners_bracket", "player_kickoff", "regular_season_rank", "TAXI"):
        assert is_stored_scalar(w), w
    for w in ("Zorblaxian", "Quoxa", "Secret"):
        assert not is_stored_scalar(w), w


def test_harvest_records_each_names_source_field():
    col = identity.Collector()
    identity.harvest([{"metadata": {"first_name": "Ada", "position": "WR"}}], col, "draft.picks")
    identity.harvest({"metadata": {"team_name": "Bob", "p_nick_12": "C"}}, col, "league.rosters")
    assert col.name_sources["Ada"] == {"draft.picks.first_name"}
    assert col.name_sources["Bob"] == {"league.rosters.team_name"}
    assert col.name_sources["C"] == {"league.rosters.p_nick_*"}


def test_a_player_named_jj_does_not_fail_a_run(tmp_path):
    w = standard_world()
    for path, picks in list(w.routes.items()):
        if path.endswith("/picks") and isinstance(picks, list):
            for p in picks[:3]:
                p["metadata"]["first_name"] = "J.J."
    code, lines = run_cli(w, tmp_path / "data", "run")
    assert code == 0, lines
    c = sqlite3.connect(str(tmp_path / "data" / "universe.sqlite"))
    leak = json.loads(c.execute("SELECT leak_scan_json FROM runs ORDER BY run_id DESC").fetchone()[0])
    assert leak["ok"] and leak["ambiguous_names_skipped"] == 1   # J.J., and only it
