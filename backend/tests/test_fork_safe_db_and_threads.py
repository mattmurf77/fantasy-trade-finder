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
  T-fork-close
          test_fork_hook_disposes_every_engine_once_without_closing — the hook
          disposes each distinct engine once with close=False, and no DBAPI
          connection's close() runs (it would close the parent's socket).
  T-threads
    (i)   test_no_thread_is_started_at_import — run.py, server.py and every
          backend module they import at module level, transitively (incl.
          win_now_service.py), make no import-time call that starts a thread:
          `.start()`, Thread/Timer, or any function that reaches one by name
          (start_worker_on_startup, the deck_i1_check worker, ...).
    (ii)  test_background_threads_start_once_per_pid — one cleanup-loop start
          and one win-now-resume thread per pid, and again after a pid change;
          the resume still runs when FTF_DISABLE_CLEANUP_LOOP=1 skips the loop,
          and its target logs a failure instead of raising.
    (iii) test_first_request_starts_the_background_threads — the
          before_request hook does it in the serving process.
    (iv)  test_concurrent_first_requests_start_once — 16 threads behind a
          Barrier: exactly one start of each.
  T-pool  test_postgres_engine_kwargs — pool_recycle=280 and libpq
          keepalives, ro_engine keeps its read-only options, and libpq
          (psycopg2) accepts every key.
  T-pool-built
          test_postgres_engines_as_built_never_pre_ping — database.py imported
          in a subprocess with a Postgres DATABASE_URL (no connection is ever
          opened): `engine`, `ingest_engine` and `ro_engine` as built have no
          pre-ping, recycle at 280 s and pass the keepalives to libpq.
  T-pin   test_gunicorn_is_pinned_to_prod — requirements pins gunicorn==26.2.0.
  T-timeout
          test_job_hard_timeout_spares_a_slow_pregen — a running job 75 s in
          is not stalled; one `_JOB_HARD_TIMEOUT` + 1 s in is.
  T-loop  test_a_failing_cleanup_step_does_not_end_the_loop — each of the
          trade-job sweep, `_evict_trade_page_store` and
          `_drop_stale_deck_evidence` raising: the steps after it still run and
          the loop sleeps again. test_a_timed_out_job_is_logged_with_its_cards
          — one WARNING line per timed-out job, with its id and card count.

Sabotage record (2026-10-26; each applied, observed red, reverted green):
  register_at_fork line removed                       -> T-fork RED
  fork hook resets only `engine`                      -> T-fork RED (ro/ingest saw 1)
  module-level cleanup-loop .start() restored         -> T-threads (i) RED
  module-level start_worker_on_startup(...) restored  -> T-threads (i) RED
  @app.before_request removed from the hook           -> T-threads (iii) RED
  the lock in _ensure_background_threads removed      -> T-threads (iv) RED
  keepalives dropped from _pg_engine_kwargs            -> T-pool RED
  requirements back to gunicorn>=22.0.0               -> T-pin RED
Sabotage record (2026-10-29, release-lead's #429 QA misses + this round):
  dispose(close=True) in _reset_pools_after_fork      -> T-fork-close RED
  pool_pre_ping=True on the `engine` create_engine    -> T-pool-built RED
  pool_pre_ping=True on the `ro_engine` create_engine -> T-pool-built RED
  module-level _i1_event_enqueue(...) in server.py    -> T-threads (i) RED
    (QA's literal `_i1_event_ensure_worker(_i1_event_queue)`, scanned on an
    origin/main a1a4d20e tree: flagged too)
  module-level Thread(...).start() in win_now_service -> T-threads (i) RED
  _JOB_HARD_TIMEOUT back to 60                        -> T-timeout RED
  the _evict_trade_page_store guard removed           -> T-loop RED
"""
import ast
import json
import logging
import os
import re
import sqlite3
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.pool import QueuePool

import backend.database as db
import backend.prepared_trade_runtime as prepared_trade_runtime
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


class _RecordingConn:
    """A DBAPI connection whose close() is recorded (for psycopg2, close()
    in the child would send Terminate over the parent's socket)."""
    opened: list = []
    closed: list = []

    def __init__(self, path):
        self._conn = sqlite3.connect(path, check_same_thread=False)
        _RecordingConn.opened.append(self)

    def close(self):
        _RecordingConn.closed.append(self)
        self._conn.close()

    def __getattr__(self, name):
        return getattr(self._conn, name)


@pytest.mark.parametrize("ingest_is_engine", [False, True], ids=["sqlite", "postgres-layout"])
def test_fork_hook_disposes_every_engine_once_without_closing(tmp_path, monkeypatch,
                                                              ingest_is_engine):
    monkeypatch.setattr(_RecordingConn, "opened", [])
    monkeypatch.setattr(_RecordingConn, "closed", [])
    disposed = []                                # (engine, effective close=)
    engines = {}
    for name in ("engine", "ro_engine", "ingest_engine"):
        if name == "ingest_engine" and ingest_is_engine:
            eng = engines["engine"]              # Postgres: ingest_engine IS engine
        else:
            path = str(tmp_path / f"{name}.sqlite3")
            eng = create_engine("sqlite://", creator=lambda path=path: _RecordingConn(path),
                                poolclass=QueuePool)
            with eng.connect() as conn:
                conn.execute(text("SELECT 1"))

            def dispose(*args, _eng=eng, _real=eng.dispose, **kwargs):
                disposed.append((_eng, kwargs.get("close", args[0] if args else True)))
                return _real(*args, **kwargs)
            monkeypatch.setattr(eng, "dispose", dispose)
        monkeypatch.setattr(db, name, eng)
        engines[name] = eng
    distinct = list({id(e): e for e in engines.values()}.values())

    db._reset_pools_after_fork()
    assert sorted(id(e) for e, _ in disposed) == sorted(id(e) for e in distinct)
    assert [close for _, close in disposed] == [False] * len(distinct)
    assert _RecordingConn.closed == []           # the parent's sockets stay open
    assert [e.pool.checkedin() for e in distinct] == [0] * len(distinct)
    for conn in _RecordingConn.opened:           # the dropped connections, closed here
        conn._conn.close()


def _import_time_nodes(tree):
    """AST nodes that run when the module (or, given a def, the function) is
    executed: bodies, class bodies, decorators and default args; not nested
    function or lambda bodies, and not an `if __name__ == "__main__":` block
    (gunicorn imports run:app)."""
    found = []

    def visit(node):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for expr in (child.decorator_list + child.args.defaults
                             + [d for d in child.args.kw_defaults if d is not None]):
                    found.extend(ast.walk(expr))
                continue
            if isinstance(child, ast.Lambda):
                continue
            if (isinstance(child, ast.If)
                    and ast.unparse(child.test).replace("'", '"') == '__name__ == "__main__"'):
                continue
            found.append(child)
            visit(child)

    visit(tree)
    return found


def _imported_backend_files(path, node, repo):
    """The backend .py files an import statement in `path` can load."""
    if isinstance(node, ast.ImportFrom):
        if node.level:
            base = path.parent
            for _ in range(node.level - 1):
                base = base.parent
        elif (node.module or "").split(".")[0] == "backend":
            base = repo
        else:
            return []
        target = base.joinpath(*node.module.split(".")) if node.module else base
        candidates = [target.with_suffix(".py"), target / "__init__.py"]
        for alias in node.names:                 # `from . import win_now_service`
            candidates += [target / f"{alias.name}.py", target / alias.name / "__init__.py"]
    else:
        candidates = []
        for alias in node.names:
            if alias.name.split(".")[0] == "backend":
                target = repo.joinpath(*alias.name.split("."))
                candidates += [target.with_suffix(".py"), target / "__init__.py"]
    return [c for c in candidates if c.is_file() and (repo / "backend") in c.parents]


def _import_closure(roots, repo=REPO):
    """{path: AST} for `roots` and every backend module they import at module
    level, transitively. Imports inside functions are lazy, so not followed."""
    trees, todo = {}, list(roots)
    while todo:
        path = todo.pop()
        if path in trees:
            continue
        trees[path] = tree = ast.parse(path.read_text())
        for node in _import_time_nodes(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                todo += _imported_backend_files(path, node, repo)
    return trees


def _call_name(call):
    func = call.func
    return func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)


def _thread_starters(trees):
    """Names that start a thread when called: Thread, Timer, `.start`, and any
    function (in these modules) whose own body calls one of them, by name,
    to a fixed point. By-name over-approximates; a false hit names its line."""
    calls_by_def: dict[str, list] = {}
    for tree in trees:
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                calls_by_def.setdefault(node.name, []).append(
                    {_call_name(c) for c in _import_time_nodes(node) if isinstance(c, ast.Call)})
    starters = {"Thread", "Timer", "start"}
    while True:
        more = {name for name, bodies in calls_by_def.items()
                if name not in starters and any(calls & starters for calls in bodies)}
        if not more:
            return starters
        starters |= more


def _import_time_thread_starts(repo=REPO):
    trees = _import_closure([repo / "run.py", repo / "backend" / "server.py"], repo)
    starters = _thread_starters(trees.values())
    bad = [f"{path.relative_to(repo)}:{node.lineno} {ast.unparse(node)[:80]}"
           for path, tree in trees.items() for node in _import_time_nodes(tree)
           if isinstance(node, ast.Call) and _call_name(node) in starters]
    return trees, starters, bad


def test_no_thread_is_started_at_import():
    trees, starters, bad = _import_time_thread_starts()
    assert REPO / "backend" / "win_now_service.py" in trees       # via win_now_api
    # The scan sees the worker starters, including the allowed per-process
    # start, which is reached only from the before_request hook.
    assert {"start_worker_on_startup", "wake_worker", "_ensure_background_threads"} <= starters
    assert bad == [], f"import-time thread starts: {bad}"


class _RecordingThread:
    started: list = []
    delay = 0.0

    def __init__(self, *, target, name=None, daemon=None, **_):
        self.target, self.name = target, name

    def start(self):
        if _RecordingThread.delay:
            time.sleep(_RecordingThread.delay)          # widen any race window
        _RecordingThread.started.append((self.target, self.name))


def _started_names():
    return [name for _, name in _RecordingThread.started]


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
    assert _RecordingThread.started[0] == (server._cleanup_loop, "cleanup-loop")
    assert _started_names() == ["cleanup-loop", "win-now-resume"]
    assert recorders == []                        # the resume runs on its thread, not inline

    pid["value"] = 2000                           # a forked child
    server._ensure_background_threads()
    server._ensure_background_threads()
    assert _started_names() == ["cleanup-loop", "win-now-resume"] * 2

    monkeypatch.setenv("FTF_DISABLE_CLEANUP_LOOP", "1")
    pid["value"] = 3000
    server._ensure_background_threads()
    assert _started_names()[4:] == ["win-now-resume"]   # the opt-out skips the loop, not the resume

    resume = _RecordingThread.started[-1][0]
    resume()
    assert recorders == [server._sleeper_get]

    def failing(_fetch):
        raise RuntimeError("synthetic resume failure")
    monkeypatch.setattr(win_now_service, "start_worker_on_startup", failing)
    resume()                                      # logged, never raised


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
    for thread in threading.enumerate():          # started before the request returned
        if thread.name == "win-now-resume":
            thread.join(timeout=5)
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
    assert sorted(_started_names()) == ["cleanup-loop", "win-now-resume"]
    assert recorders == []


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


# Run with DATABASE_URL set to a Postgres URL nobody listens on. Each engine's
# `do_connect` hook records the libpq params it would pass, then aborts, so no
# socket is opened.
_PG_PROBE = r'''
import json
from sqlalchemy import event
import backend.database as db

class Abort(Exception):
    pass

out = {}
for name in ("engine", "ingest_engine", "ro_engine"):
    eng, seen = getattr(db, name), {}
    def grab(dialect, rec, cargs, cparams, seen=seen):
        seen.update(cparams)
        raise Abort
    event.listen(eng, "do_connect", grab)
    try:
        eng.connect()
    except Abort:
        pass
    event.remove(eng, "do_connect", grab)    # ingest_engine may be the same engine
    out[name] = {"id": id(eng), "dialect": eng.dialect.name, "pre_ping": eng.pool._pre_ping,
                 "recycle": eng.pool._recycle,
                 "params": {k: v for k, v in seen.items() if k != "password"}}
print(json.dumps(out))
'''


def test_postgres_engines_as_built_never_pre_ping():
    pytest.importorskip("psycopg2")
    env = {**os.environ, "DATABASE_URL": "postgresql://probe@127.0.0.1:1/probe",
           "PYTHONDONTWRITEBYTECODE": "1"}
    proc = subprocess.run([sys.executable, "-c", _PG_PROBE], cwd=REPO, env=env,
                          capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr[-3000:]
    out = json.loads(proc.stdout.strip().splitlines()[-1])
    assert out["ingest_engine"]["id"] == out["engine"]["id"]       # Postgres: one engine
    keepalives = {"keepalives": 1, "keepalives_idle": 30, "keepalives_interval": 10,
                  "keepalives_count": 5}
    for name, eng in out.items():
        assert (eng["dialect"], eng["pre_ping"], eng["recycle"]) == ("postgresql", False, 280), name
        assert keepalives.items() <= eng["params"].items(), (name, eng["params"])
    assert out["ro_engine"]["params"]["options"] == (
        "-c default_transaction_read_only=on -c statement_timeout=5s")
    assert "options" not in out["engine"]["params"]


def test_gunicorn_is_pinned_to_prod():
    lines = [line.split("#", 1)[0].strip()
             for line in (REPO / "requirements.txt").read_text().splitlines()]
    assert [line for line in lines if line.startswith("gunicorn")] == ["gunicorn==26.2.0"]


def test_job_hard_timeout_spares_a_slow_pregen():
    # Prod pre-gens reach their first owner batch at 60-75 s; the timeout is a
    # stuck-job backstop measured from started_at.
    now = 10_000.
    assert not server._trade_job_stalled({"status": "running", "started_at": now - 75}, now)
    assert server._trade_job_stalled(
        {"status": "running", "started_at": now - server._JOB_HARD_TIMEOUT - 1}, now)


class _StopLoop(BaseException):
    """Raised by the loop's second sleep: one pass, then out."""


class _OnePassTime:
    """`server.time` for one `_cleanup_loop` pass: the first sleep returns at
    once, the second raises _StopLoop. Everything else is the real module."""

    def __init__(self):
        self.sleeps = 0

    def sleep(self, _seconds):
        self.sleeps += 1
        if self.sleeps > 1:
            raise _StopLoop

    def __getattr__(self, name):
        return getattr(time, name)


@pytest.fixture
def loop_pass(monkeypatch):
    """Runs one `_cleanup_loop` pass with its DB-backed steps stubbed and empty
    session/job maps; returns the number of sleeps (2 = it went round again)."""
    monkeypatch.setattr(server, "_sessions", {})
    monkeypatch.setattr(server, "purge_stale_persisted_sessions", lambda *_: 0)
    monkeypatch.setattr(server._api_obs, "purge_observability_events", lambda: 0)
    monkeypatch.setattr(db, "purge_deck_diagnostics", lambda **_: 0)
    monkeypatch.setattr(server, "_retire_deck_evidence", lambda: 0)
    monkeypatch.setattr(server, "_trade_jobs", {})
    monkeypatch.setattr(server, "_trade_jobs_by_key", {})
    monkeypatch.setattr(server, "_evict_trade_page_store", lambda: None)
    monkeypatch.setattr(server, "_drop_stale_deck_evidence", lambda: None)
    monkeypatch.setattr(prepared_trade_runtime, "tick", lambda _server: None)

    def run():
        clock = _OnePassTime()
        monkeypatch.setattr(server, "time", clock)
        with pytest.raises(_StopLoop):
            server._cleanup_loop()
        return clock.sleeps
    return run


@pytest.mark.parametrize("failing", ["session sweep", "_prune_deck_evidence", "trade-job sweep",
                                     "_evict_trade_page_store", "_drop_stale_deck_evidence"])
def test_a_failing_cleanup_step_does_not_end_the_loop(monkeypatch, loop_pass, failing):
    ran = []
    # QA's repro: a session with last_active=None makes the sweep's `<` raise TypeError.
    monkeypatch.setattr(server, "_sessions",
                        {"t": {"last_active": None}} if failing == "session sweep" else {})

    def step(name):
        def run(*_args, **_kwargs):
            ran.append(name)
            if name == failing:
                raise RuntimeError(f"synthetic {name} failure")
        return run
    monkeypatch.setattr(server, "_trade_jobs", {"j": {"status": "running",
                                                      "started_at": time.monotonic()}})
    monkeypatch.setattr(server, "_prune_deck_evidence", step("_prune_deck_evidence"))
    monkeypatch.setattr(server, "_trade_job_stalled", step("trade-job sweep"))
    monkeypatch.setattr(server, "_evict_trade_page_store", step("_evict_trade_page_store"))
    monkeypatch.setattr(server, "_drop_stale_deck_evidence", step("_drop_stale_deck_evidence"))
    monkeypatch.setattr(prepared_trade_runtime, "tick", step("tick"))
    assert loop_pass() == 2
    assert ran == ["_prune_deck_evidence", "trade-job sweep", "_evict_trade_page_store",
                   "_drop_stale_deck_evidence", "tick"]


def test_a_timed_out_job_is_logged_with_its_cards(monkeypatch, loop_pass, caplog):
    now = time.monotonic()
    jobs = {"j-stuck": {"status": "running", "started_at": now - server._JOB_HARD_TIMEOUT - 30,
                        "cards": [{}, {}, {}]},
            "j-slow": {"status": "running", "started_at": now - 75, "cards": [{}]}}
    monkeypatch.setattr(server, "_trade_jobs", jobs)
    with caplog.at_level(logging.INFO, logger=server.log.name):
        assert loop_pass() == 2
    lines = [r.getMessage() for r in caplog.records
             if r.levelno == logging.WARNING and r.getMessage().startswith("trade-job ")]
    assert len(lines) == 1, lines
    match = re.fullmatch(r"trade-job j-stuck timed out: (\d+)s since start, 3 cards published",
                         lines[0])
    assert match and int(match[1]) >= server._JOB_HARD_TIMEOUT + 30, lines[0]
    assert (jobs["j-stuck"]["status"], jobs["j-stuck"]["error"]) == ("error", "timeout")
    assert jobs["j-slow"]["status"] == "running"
    assert "Trade jobs swept: 0 evicted, 1 timed out" in caplog.messages
