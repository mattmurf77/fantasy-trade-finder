"""Offline latency research; no application wiring, network or production DB.

Run with PYTHONHASHSEED=0. Only aggregate timings, counts and SHA256 digests are
written. The private captured request/config/optional impression rows stay local.
Experiment settings remain fixed; candidate budgets and evidence are unchanged.
"""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import contextmanager
import copy
import cProfile
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import pstats
import resource
import socket
import statistics
import sys
import time
from types import SimpleNamespace
from unittest.mock import patch


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


@contextmanager
def package_cache(owner):
    """Reuse exact package prices within each immutable search instance.

    Full ordered values on BOTH sides and first-round exemption masks form the
    key. Config and flags are fixed for these offline comparisons. The original
    pricing function computes every miss; no package-dependent term is additive.
    """
    original = owner._Search._package
    counts = Counter()

    def cached(search, give, receive, values):
        cache = getattr(search, "_research_package_cache", None)
        if cache is None:
            cache = search._research_package_cache = {}
        key = (tuple(values[p] for p in give), tuple(values[p] for p in receive),
               tuple(search.ts.first_round_pick_mask(give)),
               tuple(search.ts.first_round_pick_mask(receive)), search.ts.current_stud_tax_mode())
        if key in cache:
            counts["hits"] += 1
            return cache[key]
        counts["misses"] += 1
        result = original(search, give, receive, values)
        cache[key] = result
        if result is not None:
            cache[(key[1], key[0], key[3], key[2], key[4])] = (result[0], result[2], result[1])
        return result

    with patch.object(owner._Search, "_package", cached):
        yield counts


def profile_summary(profiler, count=20):
    stats = pstats.Stats(profiler)
    ordered = sorted(stats.stats.items(), key=lambda row: row[1][3], reverse=True)[:count]
    return [{"function": f"{Path(key[0]).name}:{key[1]}:{key[2]}",
             "primitive_calls": value[0], "calls": value[1],
             "self_seconds": value[2], "cumulative_seconds": value[3]}
            for key, value in ordered]


def load_inputs(snapshot, config, database):
    # Set the only database target and egress blocker BEFORE backend imports.
    if "backend.database" in sys.modules or "backend.server" in sys.modules:
        raise RuntimeError("Offline compute research requires a fresh process")
    os.environ["DATABASE_URL"] = "sqlite:///" + str(database.resolve())

    def no_network(*_args, **_kwargs):
        raise RuntimeError("Offline compute research forbids network")

    socket.socket.connect = no_network
    socket.socket.connect_ex = no_network
    socket.create_connection = no_network
    from backend import database as db, feature_flags as ff, trade_service as ts
    from backend.ranking_service import Player
    if db.engine.url.get_backend_name() != "sqlite" or Path(db.engine.url.database).resolve() != database.resolve():
        raise RuntimeError("Offline compute research requires its isolated SQLite database")
    db.metadata.create_all(db.engine)
    capture = json.loads(config.read_text())
    cfg = {r["key"]: r["value"] for r in capture["config"]}
    ts._cfg.clear()
    ts._cfg.update(ts._DEFAULT_CFG)
    ts._cfg.update(cfg)
    ff._flags_cache = capture["flags"]["flags"]
    raw = json.loads(snapshot.read_text())["owner_request"]
    inputs = copy.deepcopy(raw["input"])
    inputs["players"] = {pid: Player(id=pid, name=pid, **attrs)
                         for pid, attrs in inputs["players"].items()}
    sources = inputs.get("opponent_sources") or {}
    members = [ts.LeagueMember(m["id"], m["id"], m["roster"], m["elo"], bool(m["elo"]),
                              confidence_sources=sources.get(m["id"], {}))
               for m in inputs.pop("members")]
    inputs["league"] = ts.League("frozen-replay", "Private replay", "espn", members)
    inputs["config"] = cfg
    for key in ("past_decision_keys", "exclusion_keys"):
        inputs[key] = {(frozenset(a), frozenset(b)) for a, b in inputs[key]}
    return inputs


def compute_sample(inputs, experiment=False, profile=False):
    from backend import trade_gen_owner as owner, trade_gen_bilateral as bilateral, trade_service as ts
    original_evaluate = bilateral._Search.evaluate
    evaluated_hash = hashlib.sha256()
    calls = 0

    def record(search, card, **kwargs):
        nonlocal calls
        result = original_evaluate(search, card, **kwargs)
        evaluated_hash.update(canonical([card.target_user_id, card.give_player_ids,
                                        card.receive_player_ids]).encode())
        evaluated_hash.update(result.snapshot_json.encode())
        calls += 1
        return result

    @contextmanager
    def baseline():
        yield Counter()

    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 9, 21, tzinfo=timezone.utc).astimezone(tz)

    profiler = cProfile.Profile() if profile else None
    with (package_cache(owner) if experiment else baseline()) as counts, patch.object(ts, "datetime", FixedDatetime):
        with patch.object(bilateral._Search, "evaluate", record):
            if profiler:
                profiler.enable()
            start = time.perf_counter()
            cards, report = bilateral.generate_bilateral_trades(**inputs)
            generation_seconds = time.perf_counter() - start
            if profiler:
                profiler.disable()
            candidate_digest, candidate_calls = evaluated_hash.hexdigest(), calls
            start = time.perf_counter()
            proofs = bilateral.evaluate_bilateral_trades(cards, **inputs)
            validation_seconds = time.perf_counter() - start
    # Trade UUIDs are fresh on each generation; the clock above is fixed.
    # Compare all other card fields,
    # complete frozen proof values and emitted order (never just top-page count).
    inventory = [{"card": {k: v for k, v in vars(card).items()
                            if k not in ("trade_id", "owner_evaluation")},
                  "proof": card.owner_evaluation.as_dict()} for card in cards]
    info = report.as_dict()
    result = {"variant": "exact_package_cache" if experiment else "baseline",
              "generation_seconds": generation_seconds,
              "validation_seconds": validation_seconds,
              "cards": len(cards), "evaluated": info["evaluated"],
              "candidate_calls": candidate_calls, "candidate_proofs_sha256": candidate_digest,
              "inventory_and_order_sha256": digest(inventory), "report_sha256": digest(info),
              "validation_proofs_sha256": digest([proof.as_dict() for proof in proofs]),
              "validation_eligible": sum(proof.eligible for proof in proofs),
              "rejections": info["rejections"], "package_cache": dict(counts)}
    if profiler:
        result["profile"] = profile_summary(profiler)
    return result


def intern_features(rows):
    """Recover shared immutable objects discarded by the private JSON export.

    This is fixture setup, excluded from timing: the worker already attaches one
    shared generation report and request configuration to all cards. This broad
    interning is an upper bound on preserving those source identities, not a
    claim that every node is shared by today's worker.
    """
    known = {}

    def intern(value):
        if not isinstance(value, (dict, list)):
            return value
        key = canonical(value)
        if key not in known:
            known[key] = ({k: intern(v) for k, v in value.items()} if isinstance(value, dict)
                          else [intern(v) for v in value])
        return known[key]

    return [{**row, "features_json": intern(json.loads(row["features_json"]))} for row in rows]


def compact_structured_rows(rows):
    """Prototype existing compactor with detached structured feature roots.

    No alternate hash/packing algorithm: narrowly replace the module's JSON
    reader so both the original and structured-aware production compactors can
    consume in-memory features. Already-packed/plain roots retain this research
    adapter's canonical output contract; production's legacy JSON formatting is
    intentionally unchanged. Every output is a JSON string ready for storage.
    """
    from backend import deck_diagnostics as dd
    # The original compactor returned these dicts untouched, and this adapter
    # canonically serialized them below. The structured-aware compactor now
    # serializes them itself using legacy formatting. Supply the original
    # canonical representation up front to keep repeat runs byte-idempotent,
    # without adding a decode/encode round trip to unpacked diagnostic roots.
    rows = [
        {**row, "features_json": dd.dumps(row["features_json"])}
        if isinstance(row.get("features_json"), dict) and not any(
            isinstance(row["features_json"].get(key), (dict, list, tuple))
            and not dd.is_reference(row["features_json"][key])
            for key in dd.DIAGNOSTIC_KEYS)
        else row
        for row in rows
    ]
    adapter = SimpleNamespace(dumps=json.dumps, loads=lambda value:
                              dict(value) if isinstance(value, dict) else json.loads(value))
    with patch.object(dd, "json", adapter):
        compacted, snapshots = dd.compact_rows(rows)
    for row in compacted:
        if isinstance(row.get("features_json"), dict):
            row["features_json"] = dd.dumps(row["features_json"])
    return compacted, snapshots


def storage_sample(structured, *, experiment=False, page_size=100, profile=False):
    from backend import deck_diagnostics as dd
    profiler = cProfile.Profile() if profile else None
    if profiler:
        profiler.enable()
    start = time.perf_counter()
    rows = structured if experiment else [
        {**row, "features_json": json.dumps(row["features_json"], default=str)} for row in structured]
    freeze_seconds = time.perf_counter() - start
    compact, snapshots = [], []
    start = time.perf_counter()
    for offset in range(0, len(rows), page_size):
        page, nodes = (compact_structured_rows if experiment else dd.compact_rows)(rows[offset:offset + page_size])
        compact.extend(page)
        snapshots.extend(nodes)
    compact_seconds = time.perf_counter() - start
    if profiler:
        profiler.disable()
    mapping = {node["snapshot_id"]: node["payload_json"] for node in snapshots}
    # Verify every expanded value and every non-feature column, off the timer.
    for original, packed in zip(structured, compact):
        assert dd.expand_features(json.loads(packed["features_json"]), mapping) == original["features_json"]
        assert {k: v for k, v in packed.items() if k != "features_json"} == {
            k: v for k, v in original.items() if k != "features_json"}
    result = {"variant": "structured_before_freeze" if experiment else "baseline",
              "rows": len(rows), "page_size": page_size,
              "freeze_seconds": freeze_seconds, "compact_seconds": compact_seconds,
              "total_seconds": freeze_seconds + compact_seconds,
              "compacted_sha256": digest(compact), "snapshot_writes_sha256": digest(snapshots),
              "snapshot_write_rows": len(snapshots), "unique_snapshots": len(mapping),
              "inline_bytes": sum(len(row["features_json"].encode()) for row in compact),
              "unique_snapshot_bytes": sum(len(value.encode()) for value in mapping.values()),
              "expanded_parity": True}
    if profiler:
        result["profile"] = profile_summary(profiler)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--rows", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=2)
    parser.add_argument("--profile", action="store_true")
    args = parser.parse_args()
    if os.environ.get("PYTHONHASHSEED") != "0":
        parser.error("Set PYTHONHASHSEED=0 for deterministic set iteration")
    if args.samples < 1:
        parser.error("At least one sample per variant is required")
    args.output.mkdir(mode=0o700, parents=True, exist_ok=False)
    result = {"environment": {"python": platform.python_version(), "platform": platform.platform(),
               "machine": platform.machine(), "logical_cpus": os.cpu_count(),
               "hash_seed": "0", "samples_per_variant": args.samples},
              "measurements": [], "limitations": [
                  "Local frozen input; not production, route, network or client latency",
                  "Candidate proof hashing adds equal measurement work to both compute variants",
                  "Structured storage experiment assumes source immutable sharing; no DB timing"]}
    if args.rows:
        structured = intern_features(json.loads(args.rows.read_text()))
        for sample in range(args.samples):
            for experiment in ((False, True) if sample % 2 == 0 else (True, False)):
                result["measurements"].append(storage_sample(structured, experiment=experiment))
        if args.profile:
            result["profiled"] = storage_sample(structured, profile=True)
    else:
        if not args.snapshot or not args.config:
            parser.error("Compute requires --snapshot and --config")
        result["snapshot_sha256"] = hashlib.sha256(args.snapshot.read_bytes()).hexdigest()
        result["config_sha256"] = hashlib.sha256(args.config.read_bytes()).hexdigest()
        inputs = load_inputs(args.snapshot, args.config, args.output / "isolated.sqlite3")
        for sample in range(args.samples):
            for experiment in ((False, True) if sample % 2 == 0 else (True, False)):
                result["measurements"].append(compute_sample(inputs, experiment=experiment))
        if args.profile:
            result["profiled"] = compute_sample(inputs, profile=True)
    peak_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    result["environment"]["process_peak_rss_bytes"] = peak_rss * (1 if platform.system() == "Darwin" else 1024)
    # Keep sanitized measurements even if a parity gate exposes a new issue.
    (args.output / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
    for field in ("candidate_proofs_sha256", "inventory_and_order_sha256", "report_sha256",
                  "validation_proofs_sha256", "compacted_sha256", "snapshot_writes_sha256"):
        values = {row[field] for row in result["measurements"] if field in row}
        if values:
            assert len(values) == 1, f"Exact parity failed: {field}"
    result["all_parity_checks_passed"] = True
    (args.output / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
    for variant in sorted({row["variant"] for row in result["measurements"]}):
        rows = [row for row in result["measurements"] if row["variant"] == variant]
        fields = [key for key in rows[0] if key.endswith("_seconds")]
        print(json.dumps({"variant": variant, "samples": len(rows),
                          "median_seconds": {key: statistics.median(row[key] for row in rows) for key in fields},
                          "all_parity_checks_passed": True}), flush=True)


if __name__ == "__main__":
    main()
