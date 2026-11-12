"""Sleeper trade universe crawler: pull checkpoints and identity (research-plan §5.2-5.4, decision 2).

Covers: a kill in the middle of a league-season, then a restart, gives the
same final store as an uninterrupted run; --limit; no name and no raw user
id in any written byte after a full fixture run (scanned independently of
the crawler's own leak scan, raw SQLite bytes and every decompressed raw
file); the same user in two leagues gets the same key; a different HMAC key
gives different keys and is refused on an existing store; the crawler's leak
scan passes on clean output and fails on a planted name, id or name field;
/league/<id>/users is never stored raw.
"""
from __future__ import annotations

import gzip
import json
import sqlite3

import pytest

from backend.sleeper_universe import identity, report
from backend.tests.support.sleeper_universe_world import (
    OTHER_KEY, TEST_KEY, L, U, WorldKilled, connect, run_cli, standard_world)

CONTENT_TABLES = ("leagues", "league_members", "rosters", "roster_weeks", "matchups",
                  "transactions", "drafts", "draft_picks", "traded_picks", "brackets",
                  "trades", "trade_assets", "trade_rosters", "standings_weeks", "outcomes",
                  "standings_checks", "reconstruction_checks", "league_index",
                  "skipped_leagues", "user_keys", "discovery_users")


def _digest(d):
    c = connect(d)
    out = {t: sorted(tuple(r) for r in c.execute(f"SELECT * FROM {t}")) for t in CONTENT_TABLES}
    out["checkpoints"] = sorted((r[0], r[1]) for r in c.execute(
        "SELECT league_id, raw_path FROM pull_checkpoints"))
    c.close()
    out["raw"] = {p.name: gzip.decompress(p.read_bytes())
                  for p in sorted((d / "raw").rglob("*.gz"))}
    return out


def test_kill_mid_league_then_resume_gives_same_store(tmp_path):
    clean = tmp_path / "clean"
    assert run_cli(standard_world(), clean, "run")[0] == 0
    killed = tmp_path / "killed"
    w = standard_world()
    assert run_cli(w, killed, "discover")[0] == 0
    w.kill_after = len(w.calls) + 1 + 44 + 20     # state + one league + part of the next
    with pytest.raises(WorldKilled):
        run_cli(w, killed, "pull")
    c = connect(killed)
    assert c.execute("SELECT COUNT(*) FROM pull_checkpoints").fetchone()[0] == 1
    assert c.execute("SELECT status FROM runs ORDER BY run_id DESC").fetchone()[0] == "error"
    c.close()
    assert run_cli(standard_world(), killed, "run")[0] == 0
    assert _digest(killed) == _digest(clean)


def test_limit_pulls_n_league_seasons(tmp_path):
    w = standard_world()
    assert run_cli(w, tmp_path, "run", "--limit", "2")[0] == 0
    c = connect(tmp_path)
    assert c.execute("SELECT COUNT(*) FROM pull_checkpoints").fetchone()[0] == 2


def _all_written(d):
    """Every byte written, raw and decoded: SQLite file bytes, each text
    cell, every decompressed raw file. The seed and key files excluded."""
    out = []
    for p in sorted(d.rglob("*")):
        if not p.is_file() or p.name in ("seeds.txt", "hmac.key"):
            continue
        b = p.read_bytes()
        out.append(gzip.decompress(b) if p.suffix == ".gz" else b)
        if p.name == "universe.sqlite":
            c = sqlite3.connect(str(p))
            for (t,) in c.execute("SELECT name FROM sqlite_master WHERE type='table'"):
                for row in c.execute(f"SELECT * FROM {t}"):
                    out.extend(str(v).encode() for v in row if v is not None)
            c.close()
    return out


def test_no_name_and_no_raw_user_id_in_any_written_byte(tmp_path):
    w = standard_world()
    assert run_cli(w, tmp_path, "run")[0] == 0
    blobs = _all_written(tmp_path)
    assert blobs
    names = w.all_names()
    assert len(names) > 40
    for needle in sorted(names) + sorted(w.all_user_ids()):
        nb = needle.encode()
        assert not any(nb in b for b in blobs), "leak found"
    for key in ("display_name", "username", "team_name", "avatar", "metadata", "p_nick_"):
        assert not any(f'"{key}'.encode() in b for b in blobs)


def test_same_user_same_key_across_leagues_and_key_dependence(tmp_path):
    assert run_cli(standard_world(), tmp_path / "a", "run")[0] == 0
    c = connect(tmp_path / "a")
    k_a = c.execute("SELECT owner_key FROM rosters WHERE league_id=? AND roster_id=3",
                    (L(103),)).fetchone()[0]
    k_b = c.execute("SELECT owner_key FROM rosters WHERE league_id=? AND roster_id=1",
                    (L(201),)).fetchone()[0]
    assert k_a == k_b == identity.KeyRing(TEST_KEY.encode()).user_key(U(3))
    other = identity.KeyRing(OTHER_KEY.encode())
    assert other.user_key(U(3)) != k_a
    assert run_cli(standard_world(), tmp_path / "b", "run",
                   key=OTHER_KEY)[0] == 0
    c2 = connect(tmp_path / "b")
    assert c2.execute("SELECT owner_key FROM rosters WHERE league_id=? AND roster_id=3",
                      (L(103),)).fetchone()[0] == other.user_key(U(3))
    with pytest.raises(SystemExit, match="HMAC key differs"):
        run_cli(standard_world(), tmp_path / "a", "pull", key=OTHER_KEY)


def test_key_file_created_owner_only(tmp_path):
    kp = tmp_path / "cfg" / "hmac.key"
    ring = identity.KeyRing.load(kp, env={})
    assert kp.stat().st_mode & 0o777 == 0o600
    assert kp.parent.stat().st_mode & 0o777 == 0o700
    assert identity.KeyRing.load(kp, env={}).user_key("1") == ring.user_key("1")


def test_users_payload_never_stored_raw(tmp_path):
    assert run_cli(standard_world(), tmp_path, "run")[0] == 0
    raw = json.loads(gzip.decompress((tmp_path / "raw" / "2026" / f"{L(103)}.json.gz").read_bytes()))
    assert raw["users"] and all(set(u) == {"user_key", "is_owner"} for u in raw["users"])
    assert all(set(r) >= {"owner_key"} and "owner_id" not in r for r in raw["rosters"])


def test_leak_scan_passes_clean_and_catches_plants(tmp_path):
    w = standard_world()
    assert run_cli(w, tmp_path, "run")[0] == 0
    ring = identity.KeyRing(TEST_KEY.encode())
    assert report.leak_scan(tmp_path, ring, names=w.all_names(),
                            raw_ids=w.all_user_ids())["ok"]
    planted = tmp_path / "raw" / "planted.json"
    planted.write_text(json.dumps({"x": U(5)}))
    res = report.leak_scan(tmp_path, ring)
    assert not res["ok"] and res["id_hits"]          # found by hash, no raw id needed
    planted.write_text(json.dumps({"display_name": "z"}))
    assert report.leak_scan(tmp_path, ring)["field_hits"]
    planted.write_text(json.dumps(["Secret Display Person 004"]))
    res = report.leak_scan(tmp_path, ring, names=w.all_names())
    assert res["name_hits"] and "Secret" not in json.dumps(res)
