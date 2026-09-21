"""Time the actual worker, with a reconstructed frozen owner input, offline.

Run in a FRESH Python process: python -m scripts.research_trade_pipeline
  --snapshot PRIVATE_OWNER_REQUEST.json --config PRIVATE_CONFIG.json
  --output NEW_PRIVATE_DIRECTORY [--export-private-impressions]

This is not a production or complete end-to-end replay. The constructor input
is preserved, but provider metadata, history and DB state are unavailable.
Only aggregate measurements belong in review artifacts. The optional raw
impression/public-response exports and isolated database contain private input.
"""

import argparse
import ast
from collections import Counter
from contextlib import ExitStack
import copy
import hashlib
import inspect
import json
import logging
import os
from pathlib import Path
import platform
import random
import resource
import socket
import subprocess
import sys
import threading
import time
from types import SimpleNamespace
from unittest.mock import patch


# Match complete top-level statements in the worker's outer try block. Every
# marker must match exactly once: code drift fails rather than mistimes a span.
STAGES = (
    ("prepare_inputs", "if significance_capture is None:"),
    ("capture_owner_context", "owner_context = None"),
    ("construct", "if bakeoff_on:"),
    ("post_construction", "if owner_serve:\n    for card in final_cards:"),
    ("owner_revalidation", "pre_owner_policy = list(final_cards)"),
    ("roster_checks", "roster_results = None"),
    ("market_checks", "policy_results: dict = {}"),
    ("significance", "significance_candidates = final_cards"),
    ("presentation", "presentation = None"),
    ("breaker", "_bk_on = FLAGS.trade_breaker"),
    ("dispositions", "before_disposition = final_cards"),
    ("snapshot_and_legacy_impressions", "if owner_serve:\n    for card in served_final:"),
    ("durable_evidence_and_publish", "owner_impression_error = False"),
    ("run_ledger", "if significance_diag and (owner_impression_error or _job_superseded(job_id)):"),
    ("completion_and_analytics", "if owner_impression_error:"),
)


def instrument_worker(source, namespace, checkpoint, stages=STAGES):
    """Recompile unchanged worker statements with aggregate timing markers.

    AST verification proves deleting the injected calls recovers precisely the
    original function. No trace/profile hook enters hot evaluation loops.
    """
    tree = ast.parse(source)
    function = tree.body[0]
    outer = next(node for node in function.body if isinstance(node, ast.Try))
    original = ast.dump(tree, include_attributes=False)
    inserts = {}
    for label, prefix in stages:
        matches = [index for index, node in enumerate(outer.body)
                   if ast.unparse(node).startswith(prefix)]
        if len(matches) != 1:
            raise ValueError(f"stage marker {label} matched {len(matches)} statements")
        inserts[matches[0]] = label
    instrumented = []
    for index, statement in enumerate(outer.body):
        if index in inserts:
            marker = ast.parse(
                f"_pipeline_checkpoint({inserts[index]!r}, locals())").body[0]
            marker._pipeline_marker = True
            instrumented.append(ast.copy_location(marker, statement))
        instrumented.append(statement)
    outer.body = instrumented
    checked = copy.deepcopy(tree)
    checked_outer = next(node for node in checked.body[0].body if isinstance(node, ast.Try))
    checked_outer.body = [node for node in checked_outer.body
                          if not getattr(node, "_pipeline_marker", False)]
    if ast.dump(checked, include_attributes=False) != original:
        raise AssertionError("instrumentation changed original worker statements")
    env = dict(namespace, _pipeline_checkpoint=checkpoint)
    exec(compile(ast.fix_missing_locations(tree), "<offline-worker-timing>", "exec"), env)
    return env[function.name]


class Timeline:
    def __init__(self, wall=time.perf_counter, cpu=time.process_time):
        self.wall, self.cpu = wall, cpu
        self.started_wall, self.started_cpu = wall(), cpu()
        self.previous_wall, self.previous_cpu = self.started_wall, self.started_cpu
        self.current = "entry"
        self.stages = []
        self.card_counts = {}

    def checkpoint(self, name, state=None):
        now, cpu = self.wall(), self.cpu()
        self.stages.append({"stage": self.current,
            "wall_ms": (now - self.previous_wall) * 1000,
            "cpu_ms": (cpu - self.previous_cpu) * 1000})
        self.current, self.previous_wall, self.previous_cpu = name, now, cpu
        if state:
            self.card_counts[name] = {key: len(state[key]) for key in
                ("final_cards", "owner_cards", "served_final") if key in state}

    def elapsed_ms(self):
        return (self.wall() - self.started_wall) * 1000


class ObservedJob(dict):
    """Record actual publication mutation; never retain private card contents."""
    def __init__(self, timeline, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.timeline, self.first_cards_ms = timeline, None
        self.first_actionable_ms, self.complete_ms = None, None

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        if key == "cards" and value and self.first_cards_ms is None:
            self.first_cards_ms = self.timeline.elapsed_ms()
        if (self.first_actionable_ms is None and self.get("cards")
                and not self.get("final_checks_pending")
                and all(card.get("impression_id") for card in self["cards"])):
            self.first_actionable_ms = self.timeline.elapsed_ms()
        if key == "status" and value == "complete":
            self.complete_ms = self.timeline.elapsed_ms()


def forbid_network(*_args, **_kwargs):
    raise RuntimeError("offline pipeline replay forbids network")


def configure_isolation(output):
    """Fail closed if an imported backend could already hold a live engine."""
    if any(name == "backend.server" or name == "backend.database" for name in sys.modules):
        raise RuntimeError("run the replay in a fresh Python process")
    output = output.resolve()
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    os.chmod(output, 0o700)
    os.umask(0o077)
    os.environ["DATABASE_URL"] = "sqlite:///" + str(output / "isolated.sqlite3")
    os.environ["FTF_PLAYERS_CACHE_FILE"] = str(output / "absent-player-cache.json")
    fixture = Path(__file__).resolve().parents[1] / "backend/tests/fixtures"
    os.environ["FTF_DP_PICK_VALUES_FILE"] = str(fixture / "dp_values_picks_2026-08-06.csv")
    # server.py initializes its unrelated demo board on import. Give that
    # startup path a checked-in player curve; measured worker inputs below
    # come exclusively from the private frozen capture.
    os.environ["FTF_DP_VALUES_FILE"] = str(fixture / "outlook-hypotheses/dp-values-players-2026-08-09.csv")
    os.environ.pop("ANTHROPIC_API_KEY", None)
    os.environ.pop("FTF_TEST_MODE", None)
    os.environ.pop("FTF_SLEEPER_RECORD", None)
    return output


def reconstruct(raw, cfg, ts, Player):
    context = copy.deepcopy(raw["input"])
    context["players"] = {pid: Player(id=pid, name=pid, **attrs)
                           for pid, attrs in context["players"].items()}
    sources = context.get("opponent_sources") or {}
    members = [ts.LeagueMember(m["id"], m["id"], m["roster"], m["elo"], bool(m["elo"]),
                confidence_sources=sources.get(m["id"], {})) for m in context.pop("members")]
    # The fixture does not identify provider or full league settings. Unknown
    # is intentional; it must never masquerade as verified roster legality.
    context["league"] = ts.League("frozen-replay", "Offline research", "unknown", members)
    context["config"] = cfg
    for field in ("past_decision_keys", "exclusion_keys"):
        context[field] = {(frozenset(give), frozenset(receive))
                          for give, receive in context[field]}
    return context


def run(args):
    output = configure_isolation(args.output)
    logging.disable(logging.CRITICAL)  # Backend logs may include private IDs.
    random.seed(0)
    with ExitStack() as stack:
        for attribute in ("connect", "connect_ex"):
            stack.enter_context(patch.object(socket.socket, attribute, forbid_network))
        stack.enter_context(patch.object(socket, "create_connection", forbid_network))
        # server.py starts cleanup on import. No daemon or provider refresh
        # may run alongside a deterministic single-worker offline replay.
        stack.enter_context(patch.object(threading.Thread, "start", lambda self: None))
        from backend import server, database as db, feature_flags as ff, trade_service as ts
        from backend.ranking_service import Player, RankingService
        from sqlalchemy import event, func, select

        if db.engine.url.get_backend_name() != "sqlite" or Path(db.engine.url.database) != output / "isolated.sqlite3":
            raise RuntimeError("isolated SQLite engine was not established")
        snapshot = json.loads(args.snapshot.read_text())
        capture = json.loads(args.config.read_text())
        raw = snapshot["owner_request"]
        cfg = {row["key"]: row["value"] for row in capture["config"]}
        ts._cfg.clear()
        ts._cfg.update(ts._DEFAULT_CFG)
        ts._cfg.update(cfg)
        ff._flags_cache = capture["flags"]["flags"]
        context = reconstruct(raw, cfg, ts, Player)
        players, league, uid = context["players"], context["league"], context["user_id"]
        fmt = context["scoring_format"]
        service = RankingService(list(players.values()), seed_ratings=context["seed_elo"])
        service._scoring_format = fmt
        # The capture contains final board values, not raw vote/placement
        # history. Supply that board directly and preserve the frozen owner
        # context instead of inventing action provenance.
        rankings = SimpleNamespace(rankings=[SimpleNamespace(player=players[pid], elo=elo)
            for pid, elo in context["user_elo"].items() if pid in players])
        stack.enter_context(patch.object(service, "get_rankings", return_value=rankings))
        stack.enter_context(patch.object(server, "_owner_generation_context", return_value=context))
        stack.enter_context(patch.object(server, "_owned_picks_available", return_value=False))
        stack.enter_context(patch.object(server, "load_member_rankings", return_value={}))
        trade_service = ts.TradeService(players=players)
        trade_service.add_league(league)
        sess = {"user_id": uid, "league": league, "players": list(players.values()),
            "user_roster": context["user_roster"], "service": service, "trade_svc": trade_service,
            "services": {fmt: service}, "trade_svcs": {fmt: trade_service}, "active_format": fmt}
        own = context.get("manager_preferences", {}).get(uid, {})
        preload = {"prefs": own, "seeded_outlook": context.get("inferred_outlooks", {}).get(uid)}
        # Capture execution before starting measurement: no queue wait, route,
        # ranking restoration or provider synchronization is claimed here.
        execution = server._capture_trade_execution(sess, uid, league.league_id, fmt)
        presentation = server._capture_trade_presentation()
        significance = server._capture_trade_significance()
        source = inspect.getsource(server._run_trade_job)
        timeline = Timeline()
        job = ObservedJob(timeline, job_id="offline-pipeline", key=(uid, league.league_id, fmt),
            status="running", started_at=time.monotonic(), cards=[], opponents_done=0,
            opponents_total=len(league.members) - 1, fairness_threshold=context["fairness_threshold"],
            is_pinned=False, finished_at=None, error=None, presentation_capture=presentation,
            owner_model=server._bakeoff.owner_arm(cfg))
        sql = Counter()
        sql_wall = Counter()
        sql_started = []

        def before_sql(_conn, _cursor, statement, _params, _ctx, _many):
            operation = statement.lstrip().split(None, 1)[0].upper()
            sql[(timeline.current, operation)] += 1
            sql_started.append((timeline.current, time.perf_counter()))

        def after_sql(*_args):
            stage, started = sql_started.pop()
            sql_wall[stage] += (time.perf_counter() - started) * 1000

        event.listen(db.engine, "before_cursor_execute", before_sql)
        event.listen(db.engine, "after_cursor_execute", after_sql)
        private_rows = []
        original_save = server.save_deck_impressions

        def save_rows(rows):
            if args.export_private_impressions:
                private_rows.extend(rows)
            if args.fail_evidence_write:
                raise RuntimeError("injected offline evidence-write failure")
            return original_save(rows)

        stack.enter_context(patch.object(server, "save_deck_impressions", save_rows))
        worker = instrument_worker(source, server.__dict__, timeline.checkpoint)
        # Compilation/observer setup is excluded from worker timing.
        timeline = Timeline()
        job.timeline = timeline
        worker.__globals__["_pipeline_checkpoint"] = timeline.checkpoint
        job["started_at"] = time.monotonic()
        server._trade_jobs[job["job_id"]] = job
        worker(job["job_id"], "offline", league.league_id, context["fairness_threshold"],
            context.get("pinned_give_players") or [], context.get("pinned_receive_players") or [],
            context.get("opponent_user_id"), trade_intent=context.get("trade_intent"),
            prefs_preload=preload, execution_context=execution,
            presentation_capture=presentation, significance_capture=significance)
        timeline.checkpoint("worker_finished")
        worker_wall = sum(stage["wall_ms"] for stage in timeline.stages)
        worker_cpu = sum(stage["cpu_ms"] for stage in timeline.stages)
        start = time.perf_counter()
        public = server._trade_job_public_view(copy.deepcopy(dict(job)))
        public_view_ms = (time.perf_counter() - start) * 1000
        start = time.perf_counter()
        body = server.app.json.dumps(public)
        serialize_ms = (time.perf_counter() - start) * 1000
        event.remove(db.engine, "before_cursor_execute", before_sql)
        event.remove(db.engine, "after_cursor_execute", after_sql)
        with db.engine.connect() as connection:
            impressions = connection.execute(select(func.count()).select_from(db.deck_impressions_table)).scalar_one()
        if args.export_private_impressions:
            (output / "private-impressions.json").write_text(json.dumps(private_rows))
            (output / "private-public-snapshot.json").write_text(body)
        commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
        summary = {
            "kind": "reconstructed_offline_worker_not_production",
            "commit": commit, "python": platform.python_version(), "system": platform.system(),
            "machine": platform.machine(), "hash_seed": os.environ.get("PYTHONHASHSEED", "not_set"),
            "snapshot_sha256": hashlib.sha256(args.snapshot.read_bytes()).hexdigest(),
            "config_sha256": hashlib.sha256(args.config.read_bytes()).hexdigest(),
            "worker_source_sha256": hashlib.sha256(source.encode()).hexdigest(),
            "captured_at": raw.get("captured_at"), "configuration_checked_at": capture.get("checked_at"),
            "fixtures": {"players": len(players), "members": len(league.members),
                "user_roster": len(context["user_roster"]), "platform": "unknown"},
            "status": job["status"],
            "error": (job["error"] if job["error"] in (None, "owner_impression_unavailable")
                      else "unclassified_worker_error"),
            "cards": len(job["cards"]),
            "impressions": impressions, "injected_evidence_failure": args.fail_evidence_write,
            "worker_wall_ms": worker_wall, "worker_cpu_ms": worker_cpu,
            "first_cards_ms": job.first_cards_ms, "first_durable_cards_ms": job.first_actionable_ms,
            "complete_ms": job.complete_ms, "stages": timeline.stages,
            "card_counts_at_stage_entry": timeline.card_counts,
            "sql_calls_by_stage": {stage: {op: count for (label, op), count in sql.items() if label == stage}
                                    for stage in sorted({label for label, _op in sql})},
            "sql_execute_wall_ms_by_stage": dict(sql_wall),
            "public_snapshot_and_projection_ms": public_view_ms,
            "public_json_serialization_ms": serialize_ms, "public_json_utf8_bytes": len(body.encode()),
            "process_peak_rss_native_units": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            "peak_rss_unit": "bytes" if sys.platform == "darwin" else "KiB",
            "limitations": [
                "Single local worker; no request/queue/network/poll/parse/render timing or production SLA",
                "Use repository-pinned Python for comparable benchmarks; this manifest records the actual runtime",
                "Frozen constructor input replaces owner context capture; preparation timing is incomplete",
                "No raw ranking history, real provider, current availability or complete owned-pick ledger",
                "Empty isolated history/preferences database; downstream gates use missing metadata honestly",
                "SQLite timings exclude PostgreSQL latency, production contention and connection acquisition",
                "SQL execute times exclude commit and Python assembly; stages include both",
                "Import/initialization, execution-context copy and optional private export excluded",
                "No concurrent mutation, supersession, account deletion or process-restart simulation",
            ],
        }
        (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
        print(json.dumps({key: summary[key] for key in
            ("status", "cards", "impressions", "worker_wall_ms", "worker_cpu_ms", "first_durable_cards_ms")}))
        db.engine.dispose()
        return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--export-private-impressions", action="store_true",
                        help="also retain private impression rows and the public response in the private output directory")
    parser.add_argument("--fail-evidence-write", action="store_true")
    args = parser.parse_args()
    summary = run(args)
    expected = "error" if args.fail_evidence_write else "complete"
    if summary["status"] != expected:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
