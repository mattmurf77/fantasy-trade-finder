"""Sleeper trade universe crawler: safety before any live request (review findings A1-A6).

Covers:
A1 one crawler process per machine: a second real process is refused while
   the first holds the lock; the lock path is fixed, not per data folder.
A2 blocks and outages stop the run: a 403, a Cloudflare block page, a 200
   that is not JSON, interleaved 429s, an outage (consecutive failed
   responses) and three failed leagues in a row are hard stops with their own
   exit codes, in discovery and pull alike, leaving checkpoints to resume
   from; --max-429 is capped; a clock stepping backwards costs no wait.
A3 a 200 with an error object on /league/<id> is a failed league: nothing is
   saved or checkpointed under a value taken from the response.
A4 a dict, null or empty body where a list is expected is a failed request
   and the league-season is not checkpointed.
A5 the key: never in the data folder; a group/world-readable key file, a
   short, low-entropy or empty env key, and an env key differing from the key
   file are refused; --allow-new-key records the new fingerprint.
A6 the run prints its planned request budget.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from backend.sleeper_universe import cli, client as cl, identity
from backend.tests.support.sleeper_universe_world import (
    OTHER_KEY, TEST_KEY, FakeClock, L, U, connect, run_cli, standard_world)

REPO = Path(__file__).resolve().parents[2]


# -- A1 -------------------------------------------------------------------------

CHILD = r'''
import sys, time
from pathlib import Path
sys.path.insert(0, {repo!r})
from backend.tests.support.sleeper_universe_world import standard_world, run_cli
w = standard_world()
ready, release = Path({ready!r}), Path({release!r})
base = w.transport
def transport(url, headers, timeout):
    ready.touch()
    t0 = time.time()
    while not release.exists() and time.time() - t0 < 60:
        time.sleep(0.05)
    return base(url, headers, timeout)
w.transport = transport
code, lines = run_cli(w, Path({data!r}), "discover", lock_path=Path({lock!r}))
print("CODE", code, "|", " ".join(lines))
'''


def _child(tmp, name, data, lock, ready, release):
    src = CHILD.format(repo=str(REPO), ready=str(ready), release=str(release),
                       data=str(data), lock=str(lock))
    return subprocess.Popen([sys.executable, "-c", src], stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, cwd=str(tmp))


def test_second_process_refused_machine_wide(tmp_path):
    lock = tmp_path / "crawler.lock"
    ready, release = tmp_path / "ready", tmp_path / "release"
    p1 = _child(tmp_path, "a", tmp_path / "data-a", lock, ready, release)
    t0 = time.time()
    while not ready.exists() and time.time() - t0 < 30:
        time.sleep(0.05)
    assert ready.exists(), p1.communicate()[1][-2000:]
    # a different data folder, same machine: refused
    p2 = _child(tmp_path, "b", tmp_path / "data-b", lock, tmp_path / "ready-b", release)
    out2, err2 = p2.communicate(timeout=60)
    release.touch()
    out1, err1 = p1.communicate(timeout=120)
    assert f"CODE {cli.LOCK_HELD_EXIT}" in out2 and "another Sleeper crawler" in out2, err2[-2000:]
    assert "CODE 0" in out1, err1[-2000:]
    assert not (tmp_path / "ready-b").exists()        # the refused one made no request
    fd = cli.acquire_lock(lock)                        # released when the first exited
    cli.release_lock(fd)


def test_lock_path_is_fixed_not_per_data_folder(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(cli, "acquire_lock", lambda path=cli.LOCK_PATH: seen.append(path) or 0)
    monkeypatch.setattr(cli, "release_lock", lambda fd: None)
    for name in ("one", "two"):
        with pytest.raises(SystemExit):     # no seed file: fails after taking the lock
            cli.main(["discover", "--data-dir", str(tmp_path / name), "--key-file",
                      str(tmp_path / "k" / "hmac.key"), "--seeds", str(tmp_path / "none.txt")],
                     transport=standard_world().transport,
                     env={"SLEEPER_UNIVERSE_HMAC_KEY": TEST_KEY}, log=lambda *a: None)
    assert seen == [cli.LOCK_PATH, cli.LOCK_PATH]
    assert cli.LOCK_PATH.is_absolute() and "sleeper-universe" in cli.LOCK_PATH.name


# -- A2 -------------------------------------------------------------------------

def _client(statuses, **kw):
    clock = FakeClock()
    seq = list(statuses)

    def tr(url, h, t):
        st = seq.pop(0) if seq else 200
        if isinstance(st, tuple):
            return st
        return st, {}, (b"[]" if st == 200 else b"")
    return cl.SleeperClient(tr, clock=clock, sleep=clock.sleep, **kw), clock


@pytest.mark.parametrize("answer, stop", [
    (403, cl.BlockedStop),
    ((503, {}, b"error code: 1010"), cl.BlockedStop),
    ((200, {}, b"<html><title>Just a moment...</title></html>"), cl.BlockedStop),
    ((200, {}, b"<html>Service error</html>"), cl.BadResponseStop),
])
def test_blocks_and_non_json_are_hard_stops(answer, stop):
    c, _ = _client([answer])
    with pytest.raises(stop):
        c.get("/league/1", expect=None)


def test_interleaved_429s_trip_the_window():
    c, _ = _client(([429] * 4 + [200]) * 10)
    with pytest.raises(cl.RateLimitStop, match="of the last"):
        for i in range(50):
            c.get(f"/league/{i}", expect=list)


def test_outage_opens_the_circuit():
    c, _ = _client([500] * 100)
    with pytest.raises(cl.RequestFailed):
        c.get("/league/1", expect=list)       # one request may fail outright
    with pytest.raises(cl.CircuitOpen):
        c.get("/league/2", expect=list)       # the next in a row is an outage


def test_max_429_is_capped():
    with pytest.raises(ValueError):
        cl.SleeperClient(lambda *a: (200, {}, b"[]"), max_consecutive_429=cl.MAX_429 + 1)
    with pytest.raises(SystemExit, match="max-429"):
        cli.main(["pull", "--data-dir", "/nonexistent-never-created", "--max-429", "1000"])


def test_clock_stepping_back_costs_no_wait():
    clock = FakeClock()
    b = cl.TokenBucket(4, clock=clock, sleep=clock.sleep)
    b.acquire()
    clock.t -= 3600
    t0 = clock.t
    b.acquire()
    assert clock.t - t0 <= 0.25 + 1e-9


def _world_with(mode):
    w = standard_world()
    base = w.transport

    def tr(url, h, t):
        path = url.split("/v1/", 1)[1]
        if path == "state/nfl" or (mode.startswith("pull") and path.startswith("user")):
            return base(url, h, t)
        w.calls.append(path)
        if mode == "pull403" or (mode.startswith("disc403:") and mode[8:] in path):
            return 403, {}, b"error code: 1010"
        if mode == "pull400":
            if path.endswith("/users"):
                return 400, {}, b""
        return base(url, h, t)
    w.transport = tr
    return w


def test_cli_block_during_pull_stops_and_keeps_checkpoints(tmp_path):
    assert run_cli(standard_world(), tmp_path, "run", "--limit", "2")[0] == 0
    code, lines = run_cli(_world_with("pull403"), tmp_path, "pull")
    assert code == cl.BlockedStop.exit_code and any("refused" in x for x in lines)
    c = connect(tmp_path)
    assert c.execute("SELECT COUNT(*) FROM pull_checkpoints").fetchone()[0] == 2
    assert c.execute("SELECT status FROM runs ORDER BY run_id DESC").fetchone()[0] == "stopped_blocked"
    c.close()
    assert run_cli(standard_world(), tmp_path, "run")[0] == 0     # resumes
    c = connect(tmp_path)
    assert c.execute("SELECT COUNT(*) FROM pull_checkpoints").fetchone()[0] == 5


@pytest.mark.parametrize("where", ["user/secretusername", "/leagues/nfl/", "/rosters"])
def test_cli_block_during_discovery_is_a_clean_stop(tmp_path, where):
    code, _ = run_cli(_world_with("disc403:" + where), tmp_path, "discover")
    assert code == cl.BlockedStop.exit_code


def test_three_failed_leagues_in_a_row_open_the_circuit(tmp_path):
    assert run_cli(standard_world(), tmp_path, "discover")[0] == 0
    code, _ = run_cli(_world_with("pull400"), tmp_path, "pull")
    assert code == cl.CircuitOpen.exit_code
    c = connect(tmp_path)
    assert c.execute("SELECT COUNT(*) FROM pull_failures").fetchone()[0] == 3
    assert c.execute("SELECT COUNT(*) FROM pull_checkpoints").fetchone()[0] == 0


# -- A3, A4 -----------------------------------------------------------------------

def _patched(path_suffix, body):
    w = standard_world()
    base = w.transport

    def tr(url, h, t):
        if url.endswith(path_suffix):
            w.calls.append(url)
            return 200, {}, body
        return base(url, h, t)
    w.transport = tr
    return w


def test_error_object_on_league_is_a_failed_league(tmp_path):
    w = _patched(f"/league/{L(102)}", b'{"error": "internal"}')
    code, _ = run_cli(w, tmp_path, "run")
    c = connect(tmp_path)
    assert c.execute("SELECT kind FROM pull_failures WHERE league_id=?",
                     (L(102),)).fetchone()[0] == "league_id_mismatch"
    ids = {r[0] for r in c.execute("SELECT league_id FROM leagues")}
    assert L(102) not in ids and "None" not in ids and None not in ids
    assert {r[0] for r in c.execute("SELECT league_id FROM pull_checkpoints")} == ids
    assert not list(tmp_path.rglob("None*"))
    assert len(list((tmp_path / "raw").rglob("*.json.gz"))) == len(ids) == 4


@pytest.mark.parametrize("body", [b'{"error": "upstream timeout"}', b"", b"null"])
def test_non_list_on_a_list_endpoint_is_not_checkpointed(tmp_path, body):
    w = _patched(f"/league/{L(102)}/matchups/2", body)
    run_cli(w, tmp_path, "run")
    c = connect(tmp_path)
    assert c.execute("SELECT COUNT(*) FROM pull_checkpoints WHERE league_id=?",
                     (L(102),)).fetchone()[0] == 0
    assert c.execute("SELECT kind FROM pull_failures WHERE league_id=?",
                     (L(102),)).fetchone()[0] == "league.matchups:not_a_list"
    c.close()
    assert run_cli(standard_world(), tmp_path, "run")[0] == 0     # a later run fills it
    c = connect(tmp_path)
    assert c.execute("SELECT COUNT(*) FROM roster_weeks WHERE league_id=? AND week=2",
                     (L(102),)).fetchone()[0] == 8


# -- A5 -------------------------------------------------------------------------

def test_key_never_in_the_data_folder(tmp_path):
    data = tmp_path / "data"
    with pytest.raises(SystemExit, match="outside the data folder"):
        identity.KeyRing.load(data / "keys" / "hmac.key", env={}, data_dir=data)
    data.mkdir()
    (data / "hmac.key").write_text("x" * 64)
    with pytest.raises(SystemExit, match="sits in the data folder"):
        identity.KeyRing.load(tmp_path / "k" / "hmac.key", env={}, data_dir=data)


def test_readable_key_file_is_refused_not_fixed(tmp_path):
    kp = tmp_path / "k" / "hmac.key"
    identity.KeyRing.load(kp, env={})
    os.chmod(kp, 0o644)
    with pytest.raises(SystemExit, match="readable by group or others"):
        identity.KeyRing.load(kp, env={})
    assert kp.stat().st_mode & 0o777 == 0o644


@pytest.mark.parametrize("val, msg", [
    ("", "shorter than"), ("short-key", "shorter than"),
    ("a" * 40, "distinct characters"), ("12" * 20, "distinct characters")])
def test_weak_env_keys_refused(tmp_path, val, msg):
    with pytest.raises(SystemExit, match=msg):
        identity.KeyRing.load(tmp_path / "k" / "hmac.key", env={identity.KEY_ENV: val})


def test_env_and_file_keys_that_differ_are_refused(tmp_path):
    kp = tmp_path / "k" / "hmac.key"
    file_ring = identity.KeyRing.load(kp, env={})
    with pytest.raises(SystemExit, match="both exist and differ"):
        identity.KeyRing.load(kp, env={identity.KEY_ENV: TEST_KEY})
    same = identity.KeyRing.load(kp, env={identity.KEY_ENV: kp.read_text().strip()})
    assert same.user_key("7") == file_ring.user_key("7")


def test_allow_new_key_records_the_new_fingerprint(tmp_path):
    assert run_cli(standard_world(), tmp_path, "run", "--limit", "1")[0] == 0
    assert run_cli(standard_world(), tmp_path, "pull", "--allow-new-key", key=OTHER_KEY)[0] == 0
    c = connect(tmp_path)
    assert c.execute("SELECT value FROM meta WHERE key='key_fingerprint'").fetchone()[0] == \
        identity.KeyRing(OTHER_KEY.encode()).fingerprint()
    c.close()
    assert run_cli(standard_world(), tmp_path, "pull", key=OTHER_KEY)[0] == 0


# -- A6 -------------------------------------------------------------------------

def test_run_prints_planned_budget(tmp_path):
    code, lines = run_cli(standard_world(), tmp_path, "run", "--cap", "150")
    assert code == 0
    line = next(x for x in lines if x.startswith("planned budget"))
    assert "150 lineages x 3 seasons x 44 = 19800 pull requests" in line
    assert "about 1200 for discovery" in line
    assert any(x.startswith("pull plan: 5 league-seasons") for x in lines)
