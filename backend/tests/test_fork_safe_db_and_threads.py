"""Fork safety: DB pools and background threads under gunicorn --preload.

Render's default for Python services is
GUNICORN_CMD_ARGS="--preload --access-logfile - --bind=0.0.0.0:10000". It does
not appear in the service's env list. So prod has always imported the app in
the gunicorn MASTER and then forked the worker ("Database initialised" is
logged before "Booting worker"). That broke three things:
  * the worker inherited the master's pooled SSL connections ("decryption
    failed or bad record mac");
  * the import-time `_cleanup_loop` thread ran only in the master;
  * the import-time Win Now resume started `win-now-worker` in the master,
    and the forked worker inherited `_worker_running=True` with no thread,
    so `wake_worker` was a no-op until a restart.
Threads do not survive fork. The gunicorn==26.2.0 pin matches prod and is not
the cause. docs/runbook.md § "DB connections and background threads across fork".

  T-fork  test_forked_child_starts_with_empty_pools — after os.fork() the
          child's `engine`, `ro_engine` and `ingest_engine` pools hold 0
          checked-in connections; the parent's still hold theirs.
  T-threads
    (i)   test_no_thread_is_started_at_import — server.py has no module-level
          `.start()` and no module-level `start_worker_on_startup(...)`.
    (ii)  test_background_threads_start_once_per_pid — one cleanup-loop start
          and one Win Now resume per pid, and again after a pid change; the
          resume still runs when FTF_DISABLE_CLEANUP_LOOP=1 skips the loop.
    (iii) test_first_request_starts_the_background_threads — the
          before_request hook does it in the serving process.
    (iv)  test_concurrent_first_requests_start_once — 16 threads behind a
          Barrier: exactly one start.
  T-pool  test_postgres_engine_kwargs — pool_recycle=280 and libpq
          keepalives, ro_engine keeps its read-only options, and libpq
          (psycopg2) accepts every key.
  T-pin   test_gunicorn_is_pinned_to_prod — requirements pins gunicorn==26.2.0.

Sabotage record (2026-10-26; each applied, observed red, reverted green):
  register_at_fork line removed                       -> T-fork RED
  fork hook resets only `engine`                      -> T-fork RED (ro/ingest saw 1)
  module-level cleanup-loop .start() restored         -> T-threads (i) RED
  module-level start_worker_on_startup(...) restored  -> T-threads (i) RED
  @app.before_request removed from the hook           -> T-threads (iii) RED
  the lock in _ensure_background_threads removed      -> T-threads (iv) RED
  keepalives dropped from _pg_engine_kwargs            -> T-pool RED
  requirements back to gunicorn>=22.0.0               -> T-pin RED
"""
import ast
import os
import threading
import time
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

import backend.database as db
import backend.server as server
import backend.win_now_service as win_now_service

REPO = Path(__file__).resolve().parents[2]
_REAL_THREAD = threading.Thread     # before any test patches threading.Thread


@pytest.mark.skipif(not hasattr(os, "fork"), reason="needs os.fork")
@pytest.mark.filterwarnings("ignore::DeprecationWarning")   # 3.12+: fork with threads
def test_forked_child_starts_with_empty_pools(tmp_path, monkeypatch):
    # Tmp engines for all three names (the module's SQLite ro/ingest engines
    # point at data/trade_finder.db, which tests never touch).
    engines = {}
    for name in ("engine", "ro_engine", "ingest_engine"):
        eng = create_engine("sqlite:///" + str(tmp_path / f"{name}.sqlite3"),
                            connect_args={"check_same_thread": False})
        monkeypatch.setattr(db, name, eng)
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
        assert eng.pool.checkedin() == 1
        engines[name] = eng

    read_fd, write_fd = os.pipe()
    pid = os.fork()
    if pid == 0:                                 # child: report, never return
        try:
            os.close(read_fd)
            os.write(write_fd, ",".join(
                str(getattr(db, n).pool.checkedin()) for n in engines).encode())
        finally:
            os._exit(0)
    os.close(write_fd)
    seen = os.read(read_fd, 64)
    os.close(read_fd)
    os.waitpid(pid, 0)
    assert seen == b"0,0,0"                      # child: every inherited pool dropped
    assert [e.pool.checkedin() for e in engines.values()] == [1, 1, 1]   # parent: untouched
    for eng in engines.values():
        eng.dispose()


def _module_level_calls(tree):
    found = []

    def visit(node):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
                continue
            if isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute):
                found.append((child.lineno, child.func.attr))
            visit(child)

    visit(tree)
    return found


def test_no_thread_is_started_at_import():
    calls = _module_level_calls(ast.parse((REPO / "backend" / "server.py").read_text()))
    bad = [(line, attr) for line, attr in calls if attr in ("start", "start_worker_on_startup")]
    assert bad == [], f"import-time thread starts in server.py: {bad}"


class _RecordingThread:
    started: list = []
    delay = 0.0

    def __init__(self, *, target, name=None, daemon=None, **_):
        self.target, self.name = target, name

    def start(self):
        if _RecordingThread.delay:
            time.sleep(_RecordingThread.delay)          # widen any race window
        _RecordingThread.started.append((self.target, self.name))


@pytest.fixture
def recorders(monkeypatch):
    """threading.Thread and the Win Now resume replaced by recorders."""
    monkeypatch.delenv("FTF_DISABLE_CLEANUP_LOOP", raising=False)
    monkeypatch.setattr(server, "_bg_threads_pid", None)
    monkeypatch.setattr(server.threading, "Thread", _RecordingThread)
    monkeypatch.setattr(_RecordingThread, "started", [])
    monkeypatch.setattr(_RecordingThread, "delay", 0.0)
    resumes: list = []
    monkeypatch.setattr(win_now_service, "start_worker_on_startup", resumes.append)
    return resumes


def test_background_threads_start_once_per_pid(monkeypatch, recorders):
    pid = {"value": 1000}
    monkeypatch.setattr(server.os, "getpid", lambda: pid["value"])

    for _ in range(3):
        server._ensure_background_threads()
    assert _RecordingThread.started == [(server._cleanup_loop, "cleanup-loop")]
    assert recorders == [server._sleeper_get]

    pid["value"] = 2000                           # a forked child
    server._ensure_background_threads()
    server._ensure_background_threads()
    assert len(_RecordingThread.started) == 2 and len(recorders) == 2

    monkeypatch.setenv("FTF_DISABLE_CLEANUP_LOOP", "1")
    pid["value"] = 3000
    server._ensure_background_threads()
    assert len(_RecordingThread.started) == 2     # the opt-out skips the loop ...
    assert len(recorders) == 3                    # ... but not the Win Now resume


def test_first_request_starts_the_background_threads(monkeypatch):
    monkeypatch.delenv("FTF_DISABLE_CLEANUP_LOOP", raising=False)
    monkeypatch.setattr(server, "_bg_threads_pid", None)
    ran = threading.Event()
    monkeypatch.setattr(server, "_cleanup_loop", ran.set)    # no-op body
    resumes: list = []
    monkeypatch.setattr(win_now_service, "start_worker_on_startup", resumes.append)
    server.app.config["TESTING"] = True
    client = server.app.test_client()
    client.get("/api/tier-config")
    client.get("/api/tier-config")
    assert ran.wait(timeout=5), "first request did not start the cleanup loop"
    assert resumes == [server._sleeper_get]       # once per pid, not per request
    assert server._bg_threads_pid == os.getpid()


def test_concurrent_first_requests_start_once(recorders, monkeypatch):
    monkeypatch.setattr(_RecordingThread, "delay", 0.02)
    gate = threading.Barrier(16)
    errors: list = []

    def first_request():
        try:
            gate.wait(timeout=10)
            server._ensure_background_threads()
        except BaseException as exc:              # noqa: BLE001 — surfaced below
            errors.append(repr(exc))

    # server.threading IS threading, so threading.Thread is the recorder here.
    threads = [_REAL_THREAD(target=first_request) for _ in range(16)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert errors == [] and not any(t.is_alive() for t in threads)
    assert len(_RecordingThread.started) == 1
    assert len(recorders) == 1


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
