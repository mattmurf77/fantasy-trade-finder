"""First-deck eval (MOD-M1 task 1): a brand-new user's first deck through the
live routes, on an isolated scratch database. Driven by scripts/deck_eval.py.

For each team of a connected Sleeper league this runs what the app runs on
that manager's first open, through unmodified server code:

  1. POST /api/session/init with the body a new client sends (an unset
     fairness preference is OFF, so trade_fairness_threshold 0.5:
     mobile/src/api/tradePregen.ts). The route reads Sleeper membership,
     builds the ranking and trade services and kicks off the pregen job.
  2. That job's worker (`_kickoff_trade_job`'s leased runner: `_run_trade_job`,
     the deferred evidence, the first-page store), run on this thread once the
     route has returned, as its worker thread would run it.
  3. POST /api/trades/generate with the client's first-page body (fairness
     0.5, page 1). It joins the finished pregen job; its `cards` are the
     client's first page (the first `trade_page_size` = 30 published).

So the engine, the bake-off roster and serve knobs, owner presentment, the
D-207 deck_quality filters, ghost withholding and the first-30 publication are
whatever the configuration says. Configuration comes from `apply_overrides`.

Deliberate differences from a live first open (eval-scoped patches; nothing in
backend/ changes):
  - The session-init daemon (league row, members, owned picks, draft status,
    trade block, captured trades) runs once per league, inline, from its first
    team's init, whose pregen job is discarded. The database is snapshotted
    there and every team's run starts from that snapshot with its own daemon
    skipped: the state of a league that is already connected, and no team's
    impressions reach the next team's league-wide diversity read.
  - Opponents have no personal boards. Nothing is read from prod, so every
    league-mate is on consensus (the owner engine's consensus fallback).
  - `_deck_rng_seed` ignores the job id, so a re-run reproduces the decks.
  - Sleeper GETs are memoized per run (read-only public data). Pushes are
    no-ops (none fire in this flow). Deferred-evidence writes run inline.

Writes go only to the scratch SQLite file: `require_scratch_db` refuses any
other engine before anything runs.
"""
import copy
import os
import re
import sqlite3
import threading
import time
from contextlib import ExitStack, closing, contextmanager
from pathlib import Path
from unittest.mock import patch

from backend import database as db, feature_flags as ff
from backend import ranking_service as _ranking_service_mod
from backend import server as srv
from backend import trade_service as _trade_service_mod
from backend.eval.insult_rule import insult_verdict

SLEEPER = "https://api.sleeper.app/v1"
FIRST_DECK_FAIRNESS = 0.5   # mobile FAIRNESS_OFF_THRESHOLD: a new user's unset preference
FIRST_FIVE = 5              # D-055 scores every first-5 card
BARS = {"empty_deck_rate_pct": 5.0, "insult_rate_pct": 3.0}   # D-055, strict <
_DAEMON = "session-init-bg-writes"
_JOB_ID = re.compile(r"^[0-9a-f]{32}")   # _kickoff_trade_job mints uuid4().hex


# ---------------------------------------------------------------------------
# Isolation and configuration
# ---------------------------------------------------------------------------

def require_scratch_db(expected: str | None = None) -> str:
    """Return the scratch SQLite path, or raise unless every backend engine
    is that one file, it is not the repo's data/trade_finder.db, and (when
    given) it is `expected`."""
    url = db.engine.url
    path = url.database
    if url.get_backend_name() != "sqlite" or not path or path == ":memory:":
        raise RuntimeError(f"deck eval needs a scratch SQLite file, not {url!r}")
    if os.path.realpath(path) == os.path.realpath(db._DB_PATH):
        raise RuntimeError("deck eval refuses the repo database (data/trade_finder.db)")
    if expected is not None and os.path.realpath(path) != os.path.realpath(expected):
        raise RuntimeError(f"backend engine is {path}, expected the scratch file {expected}")
    for other in (db.ingest_engine, getattr(db, "ro_engine", None)):
        if other is not None and other is not db.engine and path not in str(other.url):
            raise RuntimeError(f"a second backend engine points elsewhere: {other.url!r}")
    return path


def apply_overrides(overrides: dict) -> dict:
    """Apply prod's values: {"flags": {key: bool}, "model_config": {key: number}}.

    Flags merge over config/features.json in the flag cache that FLAGS and
    is_enabled read. model_config keys are written to the scratch database and
    reloaded the way PUT /api/admin/config does. Unknown keys and wrong types
    are errors, and every override is read back from where the server reads
    it, so none can be silently ignored. Returns the applied values.
    """
    extra = sorted(set(overrides) - {"flags", "model_config"})
    flags, config = overrides.get("flags") or {}, overrides.get("model_config") or {}
    if extra or not isinstance(flags, dict) or not isinstance(config, dict):
        raise ValueError('overrides must be {"flags": {...}, "model_config": {...}}'
                         + (f"; unexpected keys {extra}" if extra else ""))
    bad = sorted(k for k, v in flags.items() if k not in ff.DEFAULT_FLAGS or not isinstance(v, bool))
    if bad:
        raise ValueError(f"unknown flag keys or non-boolean values: {bad}")
    known = {row["key"] for row in db.list_config()}
    bad = sorted(k for k, v in config.items() if k not in known
                 or isinstance(v, bool) or not isinstance(v, (int, float)))
    if bad:
        raise ValueError(f"model_config keys unknown at this checkout, or non-numeric: {bad}")
    ff._flags_cache = {**ff.flags_dict(), **flags}
    for key, value in sorted(config.items()):
        db.set_config(key, float(value), source="deck_eval")
    _trade_service_mod.reload_config()
    _ranking_service_mod.reload_config()
    missed = sorted([k for k, v in flags.items() if ff.is_enabled(k) != v]
                    + [k for k, v in config.items() if _trade_service_mod._cfg.get(k) != float(v)])
    if missed:
        raise RuntimeError(f"overrides not in effect after reload: {missed}")
    return {"flags": dict(sorted(flags.items())),
            "model_config": {k: float(v) for k, v in sorted(config.items())}}


@contextmanager
def stable_rng_seed(seed: int = 0):
    """The deck RNG seed with the job id replaced by `seed`, so the ordering
    draws are the same on every run (and in a test's live-flow comparison)."""
    real = srv._deck_rng_seed

    def seeded(user_id, league_id, job_id):
        return real(user_id, league_id, _JOB_ID.sub(f"deck-eval-{seed}", str(job_id), count=1))

    with patch.object(srv, "_deck_rng_seed", seeded):
        yield


def league_format(meta: dict, scoring_format: str) -> dict:
    """1QB/SF, TEP and team count, by `_detect_scoring_format_from_meta`'s rules."""
    positions = list((meta or {}).get("roster_positions") or [])
    try:
        te_bonus = float(((meta or {}).get("scoring_settings") or {}).get("bonus_rec_te") or 0)
    except (TypeError, ValueError):
        te_bonus = 0.0
    superflex = "SUPER_FLEX" in positions or positions.count("QB") >= 2
    return {"qb": "SF" if superflex else "1QB", "tep": te_bonus > 0, "te_bonus": te_bonus,
            "teams": (meta or {}).get("total_rosters"), "scoring_format": scoring_format}


# ---------------------------------------------------------------------------
# Scratch database snapshots
# ---------------------------------------------------------------------------

def _copy_sqlite(src: str, dst: str) -> None:
    """Replace `dst`'s contents with `src`'s through SQLite's backup API, with
    every pooled backend connection closed first (the scratch DB runs in WAL)."""
    for engine in {db.engine, db.ingest_engine, getattr(db, "ro_engine", db.engine)}:
        engine.dispose()
    with closing(sqlite3.connect(src)) as source, closing(sqlite3.connect(dst)) as target:
        source.backup(target)


# ---------------------------------------------------------------------------
# The run
# ---------------------------------------------------------------------------

class FirstDeckEval:
    """Installs the eval seams for a run; `run_league` evaluates one league."""

    def __init__(self, workdir, *, seed: int = 0):
        self.workdir = Path(workdir)
        self.seed = seed
        self.client = srv.app.test_client()
        self.daemon = "inline"        # the session-init daemon: "inline" | "skip"
        self.kickoffs: list = []      # worker starts captured from the routes
        self.injected_seed = None     # the job's seed map after owned-pick injection
        self.pushes = 0
        self._stack = None

    def __enter__(self):
        self.scratch = require_scratch_db()
        self._baseline = str(self.workdir / "baseline.sqlite3")
        self._connected = str(self.workdir / "connected-league.sqlite3")
        _copy_sqlite(self.scratch, self._baseline)
        evaluation, real_thread = self, threading.Thread
        real_get, real_inject, cache = srv._sleeper_get, srv._inject_owned_picks, {}

        class _Thread(real_thread):
            def start(self):
                if self.name != _DAEMON:
                    return super().start()
                if evaluation.daemon == "inline":
                    self.run()

        def memo_get(url, timeout=15):
            if url not in cache:
                cache[url] = real_get(url, timeout)
            return copy.deepcopy(cache[url])

        def observe_inject(*args, **kwargs):
            result = real_inject(*args, **kwargs)
            evaluation.injected_seed = result[0]
            return result

        def no_push(*_args, **_kwargs):
            evaluation.pushes += 1

        self._stack = ExitStack()
        for target, name, value in (
                (srv.threading, "Thread", _Thread),
                (srv, "_sleeper_get", memo_get),
                (srv, "_start_trade_job_thread", lambda **kw: self.kickoffs.append(kw)),
                (srv, "_start_deck_evidence_thread", lambda *, target, args: target(*args)),
                (srv, "_inject_owned_picks", observe_inject),
                (srv, "_send_typed_push", no_push),
                (srv, "push_notification", no_push)):
            self._stack.enter_context(patch.object(target, name, value))
        self._stack.enter_context(stable_rng_seed(self.seed))
        return self

    def __exit__(self, *exc):
        self._stack.close()

    def run_league(self, league_id: str, max_teams: int = 0) -> dict:
        """Every team's first deck in one league (each seat from the same
        connected-league snapshot)."""
        league_id = str(league_id)
        _copy_sqlite(self._baseline, self.scratch)
        out = {"league_id": league_id, "name": league_id, "format": None,
               "teams_total": 0, "teams_skipped": 0, "error": None, "seats": []}
        try:
            meta = srv._sleeper_get(f"{SLEEPER}/league/{league_id}")
            rosters = srv._sleeper_get(f"{SLEEPER}/league/{league_id}/rosters")
            users = srv._sleeper_get(f"{SLEEPER}/league/{league_id}/users") or []
        except Exception as err:
            out["error"] = f"sleeper_unavailable: {err}"
            return out
        if not isinstance(meta, dict) or not isinstance(rosters, list):
            out["error"] = "sleeper_unavailable"
            return out
        names = {str(u["user_id"]): u.get("display_name") or u.get("username") or str(u["user_id"])
                 for u in users if u.get("user_id")}
        rostered = sorted((r for r in rosters if r.get("owner_id") and any(r.get("players") or [])),
                          key=lambda r: r.get("roster_id") or 0)
        sizes = {str(r["owner_id"]): sum(1 for p in r["players"] if p) for r in rostered}
        seats = list(sizes)
        out.update(name=meta.get("name") or league_id, teams_total=len(rosters),
                   teams_skipped=len(rosters) - len(seats))
        if not seats:
            out["error"] = "no rostered teams"
            return out

        # The league's connection: its first team's init, daemon inline.
        self.daemon = "inline"
        token = f"deck-eval-connect-{seats[0]}"
        response = self._init(token, seats[0], league_id)
        self.kickoffs.clear()            # that member's own pregen job is not under test
        self._forget(token, seats[0], league_id)
        if response.status_code != 200:
            out["error"] = f"connect_failed: {response.status_code} {_error_of(response)}"
            return out
        _copy_sqlite(self.scratch, self._connected)
        fmt = league_format(meta, db.get_league_scoring(league_id) or db.DEFAULT_SCORING)
        out["format"] = fmt

        self.daemon = "skip"
        for uid in seats[:max_teams or None]:
            _copy_sqlite(self._connected, self.scratch)
            out["seats"].append(self._seat(uid, names.get(uid, uid), sizes[uid], league_id, fmt))
        return out

    def _init(self, token, user_id, league_id):
        with srv._sessions_lock:
            srv._sessions[token] = {"user_id": user_id, "verified": True}
        return self.client.post("/api/session/init", headers={"X-Session-Token": token}, json={
            "user_id": user_id, "league_id": league_id,
            "trade_fairness_threshold": FIRST_DECK_FAIRNESS})

    def _generate(self, token, league_id):
        return self.client.post("/api/trades/generate", headers={"X-Session-Token": token}, json={
            "league_id": league_id, "fairness_threshold": FIRST_DECK_FAIRNESS,
            "page": 1, "search_id": "deck-eval"})

    def _run_worker(self):
        kick = self.kickoffs.pop(0)
        kick["target"](*kick["args"], **kick["kwargs"])
        return kick["args"][0]

    def _forget(self, token, user_id, league_id):
        """Drop the run's session and jobs from server memory."""
        with srv._sessions_lock:
            srv._sessions.pop(token, None)
        with srv._trade_jobs_lock:
            for key in [k for k in srv._trade_jobs_by_key if tuple(k[:2]) == (user_id, league_id)]:
                srv._trade_jobs_by_key.pop(key, None)
            for job_id in [j for j, job in srv._trade_jobs.items()
                           if tuple((job.get("key") or ())[:2]) == (user_id, league_id)]:
                srv._trade_jobs.pop(job_id, None)

    def _seat(self, user_id, username, roster_size, league_id, fmt) -> dict:
        """One team's first deck: init, the pregen worker, the first page."""
        token = f"deck-eval-{user_id}"
        seat = {"user_id": user_id, "username": username, "roster_size": roster_size,
                "status": None, "error": None, "outlook": None, "init_ms": None,
                "job_ms": None, "page_ms": None, "deck_size": 0, "first_page_size": 0,
                "regenerated": False, "cards": [], "first_page": []}
        self.kickoffs.clear()
        self.injected_seed = None
        try:
            started = time.perf_counter()
            response = self._init(token, user_id, league_id)
            seat["init_ms"] = round((time.perf_counter() - started) * 1000, 1)
            if response.status_code != 200 or len(self.kickoffs) != 1:
                seat.update(status="error", error=f"session_init: {response.status_code} "
                            f"{_error_of(response)} (pregen jobs: {len(self.kickoffs)})")
                return seat
            started = time.perf_counter()
            job_id = self._run_worker()
            seat["job_ms"] = round((time.perf_counter() - started) * 1000, 1)
            started = time.perf_counter()
            response = self._generate(token, league_id)
            if response.status_code == 200 and self.kickoffs:
                # The route did not join the pregen job: run the job it started, ask again.
                seat["regenerated"] = True
                job_id = self._run_worker()
                response = self._generate(token, league_id)
            seat["page_ms"] = round((time.perf_counter() - started) * 1000, 1)
            if response.status_code != 200:
                seat.update(status="error", error=f"generate: {response.status_code} {_error_of(response)}")
                return seat
            page = response.get_json()
            with srv._sessions_lock:
                sess = srv._sessions.get(token) or {}
            with srv._trade_jobs_lock:
                job = dict(srv._trade_jobs.get(job_id) or {})
            seed_map = self.injected_seed or getattr(
                (sess.get("services") or {}).get(sess.get("active_format")), "_seed", None) or {}
            cards = list(page.get("cards") or [])
            seat.update(status=page.get("status"), error=page.get("error") or page.get("wait_reason"),
                         outlook=job.get("outlook_value"), deck_size=len(job.get("cards") or []),
                         first_page_size=len(cards), first_page=cards,
                         cards=[card_record(c, n, seed_map, fmt)
                                for n, c in enumerate(cards[:FIRST_FIVE], 1)])
            return seat
        except Exception as err:          # one team's failure never ends the run
            seat.update(status="error", error=f"{type(err).__name__}: {err}")
            return seat
        finally:
            self.kickoffs.clear()
            self._forget(token, user_id, league_id)


def _error_of(response) -> str:
    body = response.get_json(silent=True) or {}
    return str(body.get("error") or "")


# ---------------------------------------------------------------------------
# Records and metrics
# ---------------------------------------------------------------------------

def card_record(card: dict, deck_position: int, seed_map: dict, fmt: dict) -> dict:
    """One served card with what the gate and the blind audit sheet need:
    each side's assets with position, age and consensus value, the side
    totals, Δ, the haircut, the I1/I2 verdicts and the league format."""
    unpriced = []

    def side(rows):
        out = []
        for row in rows or []:
            pid = str(row.get("id"))
            elo = seed_map.get(pid)
            if elo is None:
                unpriced.append(pid)
            out.append({"id": pid, "name": row.get("name"), "position": row.get("position"),
                        "age": row.get("age"),
                        "value": round(_trade_service_mod.elo_to_value(elo)) if elo is not None else 0})
        return out

    give, receive = side(card.get("give")), side(card.get("receive"))
    verdict = insult_verdict([a["value"] for a in give], [a["value"] for a in receive])
    return {
        "deck_position": deck_position,
        "trade_hash": srv._deck_trade_hash([a["id"] for a in give], [a["id"] for a in receive],
                                           card.get("target_user_id")),
        "partner": card.get("target_username"),
        "partner_user_id": card.get("target_user_id"),
        "model_arm": card.get("model_arm"),
        "generator_version": card.get("generator_version"),
        "give": give,
        "receive": receive,
        **verdict,
        "haircut": round(verdict["haircut"], 4),
        "displayed_give_value": card.get("give_value"),
        "displayed_receive_value": card.get("receive_value"),
        "unpriced": unpriced,
        "league_format": dict(fmt or {}),
    }


def pctl(values: list, p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[max(0, min(len(ordered) - 1, round(p / 100 * (len(ordered) - 1))))]


def _latency(values: list) -> dict:
    values = [v for v in values if v is not None]
    if not values:
        return {"n": 0}
    return {"n": len(values), "mean": round(sum(values) / len(values), 1),
            "p50": pctl(values, 50), "p95": pctl(values, 95), "max": max(values)}


def summarize(leagues: list) -> dict:
    """The gate metrics: empty-deck rate, the rule-based insult rate over every
    first-5 card, latency, and per-format-cell coverage."""
    seats = [s for lg in leagues for s in lg["seats"]]
    cards = [c for s in seats for c in s["cards"]]
    empty = [s for s in seats if not s["first_page_size"]]
    insults = [c for c in cards if c["insult"]]
    empty_rate = round(100 * len(empty) / len(seats), 2) if seats else None
    insult_rate = round(100 * len(insults) / len(cards), 2) if cards else None
    cells: dict = {}
    for lg in leagues:
        if not lg.get("format"):
            continue
        f = lg["format"]
        key = f"{f['qb']} / {'TEP' if f['tep'] else 'no TEP'} / {f['teams']} teams"
        cell = cells.setdefault(key, {"leagues": 0, "seats": 0, "empty_decks": 0,
                                      "first5_cards": 0, "insult_cards": 0})
        cell["leagues"] += 1
        for s in lg["seats"]:
            cell["seats"] += 1
            cell["empty_decks"] += not s["first_page_size"]
            cell["first5_cards"] += len(s["cards"])
            cell["insult_cards"] += sum(c["insult"] for c in s["cards"])
    sizes = [s["first_page_size"] for s in seats]
    return {
        "leagues": len(leagues),
        "leagues_failed": sum(1 for lg in leagues if lg.get("error")),
        "seats": len(seats),
        "seat_errors": sum(1 for s in seats if s["status"] == "error"),
        "empty_decks": len(empty),
        "empty_deck_rate_pct": empty_rate,
        "first5_cards": len(cards),
        "insult_cards": len(insults),
        "i1_cards": sum(c["i1"] for c in cards),
        "i2_cards": sum(c["i2"] for c in cards),
        "insult_rate_pct": insult_rate,
        # An asset outside the consensus seed is scored at value 0 (card_record),
        # which can make a card an insult: counted so a reader can check them.
        "unpriced_cards": sum(1 for c in cards if c.get("unpriced")),
        "unpriced_insult_cards": sum(1 for c in insults if c.get("unpriced")),
        "bars": dict(BARS),
        "pass": {"empty_deck": empty_rate is not None and empty_rate < BARS["empty_deck_rate_pct"],
                 "insult": insult_rate is not None and insult_rate < BARS["insult_rate_pct"]},
        "latency_ms": {"session_init": _latency([s["init_ms"] for s in seats]),
                       "deck_build": _latency([s["job_ms"] for s in seats]),
                       "first_page": _latency([s["page_ms"] for s in seats])},
        "first_page_size": {"min": min(sizes, default=0), "max": max(sizes, default=0),
                            "mean": round(sum(sizes) / len(sizes), 1) if sizes else 0},
        "regenerated_seats": sum(1 for s in seats if s["regenerated"]),
        "cells": dict(sorted(cells.items())),
    }
