"""Fork safety: DB pools and background threads under gunicorn 26.x.

gunicorn 26.x imports the app in the MASTER before forking the worker.
Release-lead saw this in the 2026-10-27 prod deploy watch: "Database
initialised" is logged before "Booting worker". That broke two things:
  * the worker inherited the master's pooled SSL connections ("decryption
    failed or bad record mac");
  * the import-time `_cleanup_loop` thread ran only in the master, and
    threads do not survive fork, so the serving worker never ran it.
docs/runbook.md § "DB connections and background threads across fork".

  T-fork  test_forked_child_starts_with_empty_pools — after os.fork() the
          child's engine pool holds 0 checked-in connections, while the
          parent's still holds its 1.
  T-threads
    (i)   test_no_thread_is_started_at_import — server.py has no module-level
          `.start()` call.
    (ii)  test_background_threads_start_once_per_pid — one start per pid,
          and another after a pid change.
    (iii) test_first_request_starts_the_background_threads — the
          before_request hook starts it in the serving process.
  T-pool  test_postgres_engine_kwargs — pool_recycle=280 and libpq
          keepalives, ro_engine keeps its read-only options, and libpq
          (psycopg2) accepts every key.
  T-pin   test_gunicorn_is_pinned_to_prod — requirements pins gunicorn==26.2.0.

Sabotage record (each applied, observed red, reverted green): see
docs/plans scope / the PR body; summarized in the fix-2 report.
"""
import ast
import os
import threading
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

import backend.database as db
import backend.server as server

REPO = Path(__file__).resolve().parents[2]


@pytest.mark.skipif(not hasattr(os, "fork"), reason="needs os.fork")
@pytest.mark.filterwarnings("ignore::DeprecationWarning")   # 3.12+: fork with threads
def test_forked_child_starts_with_empty_pools(tmp_path, monkeypatch):
    eng = create_engine("sqlite:///" + str(tmp_path / "fork.sqlite3"),
                        connect_args={"check_same_thread": False})
    monkeypatch.setattr(db, "engine", eng)
    with db.engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    assert db.engine.pool.checkedin() == 1

    read_fd, write_fd = os.pipe()
    pid = os.fork()
    if pid == 0:                                 # child: report, never return
        try:
            os.close(read_fd)
            os.write(write_fd, str(db.engine.pool.checkedin()).encode())
        finally:
            os._exit(0)
    os.close(write_fd)
    seen = os.read(read_fd, 32)
    os.close(read_fd)
    os.waitpid(pid, 0)
    assert seen == b"0"                          # child: inherited pool dropped
    assert db.engine.pool.checkedin() == 1       # parent: untouched
    eng.dispose()


def test_no_thread_is_started_at_import():
    tree = ast.parse((REPO / "backend" / "server.py").read_text())
    starts = []

    def visit(node):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
                continue
            if (isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute)
                    and child.func.attr == "start"):
                starts.append(child.lineno)
            visit(child)

    visit(tree)
    assert starts == [], f"module-level .start() at server.py lines {starts}"


class _RecordingThread:
    started: list = []

    def __init__(self, *, target, name=None, daemon=None, **_):
        self.target, self.name = target, name

    def start(self):
        _RecordingThread.started.append((self.target, self.name))


def test_background_threads_start_once_per_pid(monkeypatch):
    monkeypatch.delenv("FTF_DISABLE_CLEANUP_LOOP", raising=False)
    monkeypatch.setattr(server, "_bg_threads_pid", None)
    monkeypatch.setattr(server.threading, "Thread", _RecordingThread)
    monkeypatch.setattr(_RecordingThread, "started", [])
    pid = {"value": 1000}
    monkeypatch.setattr(server.os, "getpid", lambda: pid["value"])

    for _ in range(3):
        server._ensure_background_threads()
    assert _RecordingThread.started == [(server._cleanup_loop, "cleanup-loop")]

    pid["value"] = 2000                           # a forked child
    server._ensure_background_threads()
    server._ensure_background_threads()
    assert len(_RecordingThread.started) == 2

    monkeypatch.setenv("FTF_DISABLE_CLEANUP_LOOP", "1")
    pid["value"] = 3000
    server._ensure_background_threads()
    assert len(_RecordingThread.started) == 2     # the opt-out still holds


def test_first_request_starts_the_background_threads(monkeypatch):
    monkeypatch.delenv("FTF_DISABLE_CLEANUP_LOOP", raising=False)
    monkeypatch.setattr(server, "_bg_threads_pid", None)
    ran = threading.Event()
    monkeypatch.setattr(server, "_cleanup_loop", ran.set)    # no-op body
    server.app.config["TESTING"] = True
    server.app.test_client().get("/api/tier-config")
    assert ran.wait(timeout=5), "first request did not start the cleanup loop"
    assert server._bg_threads_pid == os.getpid()


def test_postgres_engine_kwargs():
    kwargs = db._pg_engine_kwargs()
    assert kwargs["pool_recycle"] == 280
    assert kwargs["connect_args"] == {"keepalives": 1, "keepalives_idle": 30,
                                      "keepalives_interval": 10, "keepalives_count": 5}
    assert "pool_pre_ping" not in kwargs

    ro = db._pg_engine_kwargs(options=db._PG_RO_OPTIONS)
    assert ro["connect_args"]["options"] == (
        "-c default_transaction_read_only=on -c statement_timeout=5s")
    assert ro["connect_args"]["keepalives_idle"] == 30
    source = (REPO / "backend" / "database.py").read_text()
    assert "**_pg_engine_kwargs(options=_PG_RO_OPTIONS)" in source      # ro_engine wiring
    assert "else _pg_engine_kwargs()" in source                           # product engine wiring

    # libpq itself accepts every key (psycopg2 is the shipped driver, G-073).
    psycopg2 = pytest.importorskip("psycopg2")
    from psycopg2.extensions import make_dsn, parse_dsn
    pg = create_engine("postgresql://u@localhost/db", **ro)   # no connection is opened
    assert pg.pool._recycle == 280
    _, cparams = pg.dialect.create_connect_args(pg.url)
    parsed = parse_dsn(make_dsn(**{**cparams, **ro["connect_args"]}))
    assert parsed["keepalives_count"] == "5" and "default_transaction_read_only" in parsed["options"]
    assert psycopg2 is not None


def test_gunicorn_is_pinned_to_prod():
    lines = [line.split("#", 1)[0].strip()
             for line in (REPO / "requirements.txt").read_text().splitlines()]
    assert [line for line in lines if line.startswith("gunicorn")] == ["gunicorn==26.2.0"]
