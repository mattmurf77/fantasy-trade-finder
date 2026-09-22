"""Bounded read-only owner-request capture; private artifacts, aggregate stdout.

Does not import the server, generate offers, call provider write APIs or modify
production. Credentials come from an explicitly chosen local secrets file through
the established prod_analytics/set_knob readers, never command-line values.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import urllib.request

from backend.tools import prod_analytics


def owner_request(config):
    if not isinstance(config, dict):
        return None
    request = config.get("owner_request", config)
    if not isinstance(request, dict) or not isinstance(request.get("input"), dict):
        return None
    required = {"user_id", "user_roster", "members", "players", "seed_elo", "user_elo"}
    data = request["input"]
    if not required <= data.keys():
        return None
    types = {"user_id": str, "user_roster": list, "members": list,
             "players": dict, "seed_elo": dict, "user_elo": dict}
    if not all(isinstance(data[key], expected) for key, expected in types.items()):
        return None
    return request if all(isinstance(m, dict) for m in data["members"]) else None


def coverage_summary(rows, *, fetched_count, max_runs, missing):
    """Only aggregate evidence; an absent selected outlook is not inferred."""
    return {"run_rows_scanned": min(fetched_count, max_runs), "unique_requests": len(rows),
            "distinct_manager_leagues": len({(r["user_id"], r["league_id"]) for r in rows}),
            "leagues": len({r["league_id"] for r in rows}), "omitted": dict(missing),
            "query_truncated": fetched_count > max_runs,
            "outlooks": dict(Counter(r["owner_request"]["input"].get("outlook") or "unknown" for r in rows)),
            "counterparty_boards": sum(bool(m.get("elo")) for r in rows for m in r["owner_request"]["input"]["members"])}


def input_fingerprint(request):
    """A supplied request hash is not evidence of identical frozen inputs."""
    return hashlib.sha256(json.dumps(request["input"], sort_keys=True,
        separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def write_private(path, value):
    encoded = json.dumps(value, sort_keys=True, allow_nan=False).encode()
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(encoded)


def capture(*, secrets, output, days=14, max_runs=100):
    from sqlalchemy import text
    from scripts import set_knob
    if not 1 <= days <= 30 or not 1 <= max_runs <= 100:
        raise ValueError("bounded capture requires days 1..30 and max-runs 1..100")
    if output.exists():
        raise ValueError("output already exists")
    now = datetime.now(timezone.utc)
    prod_analytics.SECRETS = secrets
    set_knob.SECRETS = secrets
    base = set_knob._from_secrets("FTF_API_BASE").rstrip("/")
    secret = set_knob._from_secrets("CRON_SECRET")
    if not base.startswith("https://") or not secret:
        raise ValueError("HTTPS API base and configured admin credential required")
    def read_api(route):
        request = urllib.request.Request(base + route, headers={"X-Cron-Secret": secret})
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read(2_000_001)
        if len(body) > 2_000_000:
            raise ValueError("API capture exceeds bound")
        return json.loads(body)
    config = read_api("/api/admin/config")
    flags = read_api("/api/feature-flags")
    engine = prod_analytics._connect_readonly(prod_analytics._load_prod_url(), 15000)
    rows, missing, seen, byte_count = [], Counter(), set(), 0
    sql = """SELECT run_id, user_id, league_id, created_at, config_json
        FROM bakeoff_runs WHERE created_at >= :since
        AND config_json IS NOT NULL AND length(config_json) <= 3000000
        ORDER BY created_at DESC, run_id DESC LIMIT :limit"""
    try:
        with engine.connect() as connection:
            if connection.execute(text("SHOW transaction_read_only")).scalar() != "on":
                raise ValueError("read-only connection required")
            fetched = connection.execute(text(sql), {
                "since": (now - timedelta(days=days)).isoformat(), "limit": max_runs + 1}).mappings().all()
            for row in fetched[:max_runs]:
                byte_count += len(row["config_json"].encode())
                if byte_count > 64_000_000:
                    missing["byte_budget_exhausted"] += 1
                    break
                try:
                    raw = json.loads(row["config_json"])
                except (TypeError, ValueError):
                    missing["invalid_config_json"] += 1
                    continue
                request = owner_request(raw)
                if request is None:
                    missing["full_owner_request_absent"] += 1
                    continue
                key = row["user_id"], row["league_id"], input_fingerprint(request)
                if key in seen:
                    missing["repeated_frozen_input"] += 1
                    continue
                seen.add(key)
                created_at = row["created_at"]
                rows.append({"run_id": row["run_id"], "created_at": created_at.isoformat() if hasattr(created_at, "isoformat") else created_at,
                             "user_id": row["user_id"], "league_id": row["league_id"],
                             "owner_request": request, "captured_run_config": raw})
    finally:
        engine.dispose()
    summary = coverage_summary(rows, fetched_count=len(fetched), max_runs=max_runs, missing=missing)
    envelope = {"schema_version": 1, "captured_at": now.isoformat(), "read_only": True,
                "selection": {"days": days, "max_runs": max_runs, "sql": sql},
                "config": {"checked_at": now.isoformat(), "config": config, "flags": flags},
                "requests": rows, "summary": summary}
    write_private(output, envelope)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--secrets", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--days", type=int, default=14)
    parser.add_argument("--max-runs", type=int, default=100)
    args = parser.parse_args()
    try:
        result = capture(secrets=args.secrets, output=args.output, days=args.days, max_runs=args.max_runs)
    except Exception as exc:
        raise SystemExit("Read-only capture failed: " + type(exc).__name__) from None
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
