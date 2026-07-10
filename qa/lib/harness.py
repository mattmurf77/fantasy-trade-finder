"""
Shared QA harness — boot a local Flask server against a scratch copy of the
live DB and talk to it over HTTP. Used by qa/sec, qa/eng, etc.

The live DB (data/trade_finder.db) is NEVER written: every boot runs against a
fresh copy under qa/<area>/scratch/. Env overrides (CRON_SECRET, feature-flag
file, DATABASE_URL) are passed per-boot so a single test can sweep configs.
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
LIVE_DB = ROOT / "data" / "trade_finder.db"


def make_scratch_db(scratch_dir: Path, name: str = "qa_scratch.db") -> Path:
    scratch_dir.mkdir(parents=True, exist_ok=True)
    db_path = scratch_dir / name
    for suffix in ("", "-wal", "-shm"):
        p = Path(str(db_path) + suffix)
        if p.exists():
            p.unlink()
    shutil.copy2(LIVE_DB, db_path)
    return db_path


def boot_server(db_path: Path, port: int, log_path: Path,
                env_overrides: dict | None = None, ready_timeout: float = 90.0):
    """Start backend.server on `port` with DATABASE_URL→db_path. Returns the
    Popen once GET /api/feature-flags answers 200. Raises on boot failure."""
    env = dict(os.environ)
    env["DATABASE_URL"] = f"sqlite:///{db_path}"
    env["PYTHONPATH"] = str(ROOT)
    env.pop("CRON_SECRET", None)            # start clean; override below
    for k, v in (env_overrides or {}).items():
        if v is None:
            env.pop(k, None)
        else:
            env[k] = str(v)
    bootstrap = (
        "from backend.server import app, _load_sleeper_cache, _maybe_sync_players; "
        "_load_sleeper_cache(); _maybe_sync_players(); "
        f"app.run(host='127.0.0.1', port={port}, debug=False)"
    )
    log_fh = open(log_path, "w")
    proc = subprocess.Popen([sys.executable, "-c", bootstrap], cwd=ROOT, env=env,
                            stdout=log_fh, stderr=subprocess.STDOUT)
    base = f"http://127.0.0.1:{port}"
    t0 = time.monotonic()
    while time.monotonic() - t0 < ready_timeout:
        if proc.poll() is not None:
            raise RuntimeError(f"server died on boot — see {log_path}")
        try:
            if requests.get(f"{base}/api/feature-flags", timeout=2).status_code == 200:
                return proc, base
        except requests.RequestException:
            pass
        time.sleep(0.5)
    proc.kill()
    raise RuntimeError(f"server not ready within {ready_timeout}s — see {log_path}")


def stop_server(proc) -> None:
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()


class Api:
    """Minimal HTTP client; attaches X-Session-Token / X-Cron-Secret if set."""

    def __init__(self, base: str, token: str | None = None, cron_secret: str | None = None):
        self.base = base
        self.token = token
        self.cron_secret = cron_secret

    def call(self, method: str, path: str, headers: dict | None = None, **kw):
        h = dict(headers or {})
        if self.token:
            h.setdefault("X-Session-Token", self.token)
        if self.cron_secret is not None:
            h.setdefault("X-Cron-Secret", self.cron_secret)
        return requests.request(method, self.base + path, headers=h, timeout=30, **kw)

    def get(self, path, **kw):
        return self.call("GET", path, **kw)

    def post(self, path, body=None, **kw):
        return self.call("POST", path, json=body or {}, **kw)

    def put(self, path, body=None, **kw):
        return self.call("PUT", path, json=body or {}, **kw)


def db_query(db_path: Path, sql: str, args: tuple = ()) -> list[tuple]:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        return conn.execute(sql, args).fetchall()
    finally:
        conn.close()


def db_scalar(db_path: Path, sql: str, args: tuple = ()):
    rows = db_query(db_path, sql, args)
    return rows[0][0] if rows else None


class CheckRecorder:
    """Collects pass/fail checks and prints them as they run."""

    def __init__(self):
        self.checks: list[dict] = []

    def check(self, cid: str, ok: bool, detail: str) -> bool:
        self.checks.append({"id": cid, "ok": bool(ok), "detail": detail})
        print(f"  [{'PASS' if ok else 'FAIL'}] {cid}: {detail}")
        return ok

    def info(self, msg: str) -> None:
        print(f"  .. {msg}")

    def summary(self, out_path: Path | None = None, meta: dict | None = None) -> int:
        passed = sum(1 for c in self.checks if c["ok"])
        failed = [c for c in self.checks if not c["ok"]]
        print(f"\n{'=' * 60}\nRESULT: {passed}/{len(self.checks)} checks passed")
        for c in failed:
            print(f"  ✗ {c['id']}: {c['detail']}")
        if out_path:
            out_path.write_text(json.dumps(
                {**(meta or {}), "passed": passed, "total": len(self.checks),
                 "checks": self.checks}, indent=2))
            print(f"\nreport: {out_path}")
        return 0 if not failed else 1
