#!/usr/bin/env python3
"""Fail-closed Find a Trade acceptance, from sanitized aggregate evidence.

No app/backend import, credentials in argv, raw user/device/search export, or writes
to a database. --production reads aggregate rows in a server-enforced read-only
Postgres transaction. See qa/instant-trade-acceptance.md for the input contract.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
import json
import math
import os
from pathlib import Path
import sys

DIMENSIONS = ("platform", "entry_point", "search_type", "network_type", "launch_state", "scenario")
GATES = {"paywall", "verify"}
RESULTS = {"shown", "empty", "error", "abandoned", "timeout", "paywall", "verify",
           "missing_outcome", "invalid_outcome", "duplicate_outcome", "offline"}
MOBILE_ENTRIES = ("deck", "calculator", "deck_error_retry", "prefs_changed_strip",
                  "deck_summary_unpin", "deck_search_all", "league_offer", "league_target",
                  "usage_trends", "deep_link", "end_card_adjust", "team_review")
SCENARIOS = ("warm", "genuinely_cold", "after_rank_change", "after_preferences_change",
             "after_format_switch", "after_league_switch", "after_account_switch",
             "pinned_give", "pinned_receive", "targeted_opponent", "shape_intent", "fair_sweep",
             "offline_cached", "free_preview")


def nearest_rank(histogram, q):
    """Weighted nearest-rank quantile; None represents +infinity, never zero."""
    n = sum(count for _, count in histogram)
    if not n:
        return None
    rank = math.ceil(q * n)
    seen = 0
    for value, count in sorted(histogram, key=lambda x: math.inf if x[0] is None else x[0]):
        seen += count
        if seen >= rank:
            return value
    raise AssertionError("histogram rank")


def binomial_quantile(n, p, probability):
    # log PMF avoids underflow around n=40 and above; no scipy dependency.
    cdf = 0.0
    for k in range(n + 1):
        log_pmf = (math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1)
                   + k * math.log(p) + (n - k) * math.log1p(-p))
        cdf += math.exp(log_pmf)
        if cdf >= probability:
            return k
    return n


def quantile_ci(histogram):
    """Central >=90% distribution-free CI for population p95 (T6).

    Rank 0 is the nonnegative-clock floor; rank n+1 is unbounded. A small
    sample of fast successes can pass p95 while its upper CI stays unbounded.
    """
    n = sum(count for _, count in histogram)
    if not n:
        return {"lower_ms": None, "upper_ms": None}
    lo = binomial_quantile(n, .95, .05)
    hi = binomial_quantile(n, .95, .95) + 1
    return {"lower_ms": nearest_rank(histogram, lo / n) if lo else 0,
            "upper_ms": nearest_rank(histogram, hi / n) if hi <= n else None}


def validate(payload):
    if not isinstance(payload, dict) or payload.get("schema") != 1:
        raise ValueError("expected aggregate schema=1")
    if payload.get("evidence_kind") not in {"measured", "synthetic"}:
        raise ValueError("evidence_kind must be measured or synthetic")
    rows = payload.get("cohorts")
    if not isinstance(rows, list):
        raise ValueError("cohorts must be an array")
    if type(payload.get("untraced_taps", 0)) is not int or payload.get("untraced_taps", 0) < 0:
        raise ValueError("untraced_taps must be a nonnegative integer")
    if type(payload.get("immediate_change_max_ms", 5000)) is not int or payload.get("immediate_change_max_ms", 5000) < 0:
        raise ValueError("immediate_change_max_ms must be nonnegative")
    seen = set()
    for row in rows:
        # Refuse accidental input of user/search IDs, receipts or arbitrary fields.
        if set(row) - set(DIMENSIONS) - {"devices", "devices_all", "histogram", "duplicate_taps",
                                       "input_age_ms_min", "input_age_ms_max"}:
            raise ValueError("unknown cohort field; provide sanitized aggregates only")
        if any(not isinstance(row.get(d), str) or not row[d] for d in DIMENSIONS):
            raise ValueError("each cohort needs all six string dimensions")
        key = tuple(row[d] for d in DIMENSIONS)
        if key in seen:
            raise ValueError("cohort dimensions must be unique; do not double-count input files")
        seen.add(key)
        for field in ("input_age_ms_min", "input_age_ms_max"):
            value = row.get(field)
            if value is not None and (type(value) is not int or value < 0):
                raise ValueError("input age bounds must be nonnegative integers or null")
        if type(row.get("devices")) is not int or row["devices"] < 0:
            raise ValueError("devices must be a nonnegative integer")
        if type(row.get("devices_all", row["devices"])) is not int:
            raise ValueError("devices_all must be a nonnegative integer")
        if type(row.get("duplicate_taps", 0)) is not int or row.get("duplicate_taps", 0) < 0:
            raise ValueError("duplicate_taps must be a nonnegative integer")
        if not isinstance(row.get("histogram"), list) or not row["histogram"]:
            raise ValueError("histogram must contain every tap outcome")
        total = 0
        for point in row["histogram"]:
            if set(point) != {"result", "ms", "count"} or point["result"] not in RESULTS:
                raise ValueError("invalid histogram fields/result")
            ms, count = point["ms"], point["count"]
            if type(count) is not int or count <= 0:
                raise ValueError("histogram counts must be positive integers")
            if ms is not None and (isinstance(ms, bool) or not isinstance(ms, (int, float))
                                   or not math.isfinite(ms) or ms < 0):
                raise ValueError("latency must be finite nonnegative or null")
            if point["result"] == "shown" and ms is None:
                raise ValueError("shown needs measured latency")
            total += count
        if not row["devices"] <= row.get("devices_all", row["devices"]) <= total:
            raise ValueError("devices cannot exceed taps")
        if row.get("input_age_ms_min") is not None and row.get("input_age_ms_max") is not None:
            if row["input_age_ms_min"] > row["input_age_ms_max"]:
                raise ValueError("input age bounds are reversed")
    return rows


def summarize(rows, limit, legacy=False):
    counts = Counter()
    latency = []
    devices = 0
    devices_all = 0
    for row in rows:
        if legacy and row["entry_point"] == "prefs_changed_strip":
            continue
        # Each row has exact distinct eligible-device count. max is a safe
        # LOWER BOUND on the union, not a sum that double-counts devices.
        devices = max(devices, row["devices"])
        devices_all = max(devices_all, row.get("devices_all", row["devices"]))
        for p in row["histogram"]:
            counts[p["result"]] += p["count"]
            if p["result"] in GATES:
                continue
            # This negative control is explicitly ineligible for a real card:
            # no network and no retained page. Its honest Offline state is
            # checked separately, never silently counted as a fast card.
            if row["scenario"] == "offline_empty" and p["result"] == "offline":
                continue
            value = p["ms"] if p["result"] == "shown" else None
            # All failures are +infinity, including fast abandonment/empty.
            # Their small ms timestamp must never improve latency percentiles.
            latency.append((value, p["count"]))
    p95 = nearest_rank(latency, .95)
    ci = quantile_ci(latency)
    eligible = sum(n for _, n in latency)
    return {"taps": sum(counts.values()), "eligible": eligible,
            "outcomes": dict(sorted(counts.items())), "devices_lower_bound": devices,
            "devices_all_lower_bound": devices_all,
            "p95_ms": p95, "ci90": ci,
            "p50_ms": nearest_rank(latency, .50), "p90_ms": nearest_rank(latency, .90),
            "p99_ms": nearest_rank(latency, .99),
            "within_limit": sum(n for ms, n in latency if ms is not None and ms <= limit),
            "within_limit_fraction": sum(n for ms, n in latency if ms is not None and ms <= limit) / eligible if eligible else None,
            "failed_or_missing": sum(n for ms, n in latency if ms is None)}


def requirements(profile):
    reqs = []
    for network in ("wifi", "cellular"):
        for launch in ("first_tap", "repeat_tap"):
            reqs.append((f"mobile:{network}:{launch}",
                         {"platform": "mobile", "search_type": "organic", "network_type": network,
                          "launch_state": launch}, "latency"))
    if profile == "ac-l1":
        return reqs
    for platform, search_types in (("mobile", ("organic", "pinned", "fair_sweep")),
                                   ("web", ("organic", "pinned"))):
        for search in search_types:
            reqs.append((f"{platform}:scope:{search}", {"platform": platform, "search_type": search}, "latency"))
        reqs.append((f"{platform}:cold_launch", {"platform": platform, "launch_state": "cold_launch"}, "latency"))
        for scenario in SCENARIOS:
            # Web currently has no fair-sweep or shape-intent control.
            if platform == "web" and scenario in {"fair_sweep", "shape_intent"}:
                continue
            reqs.append((f"{platform}:scenario:{scenario}",
                         {"platform": platform, "scenario": scenario}, "latency"))
        for scenario, expected in (("offline_empty", "offline"),
                                   ("preview_exhausted", "paywall"), ("unverified", "verify")):
            reqs.append((f"{platform}:state:{scenario}",
                         {"platform": platform, "scenario": scenario}, expected))
    for entry in MOBILE_ENTRIES:
        reqs.append((f"mobile:entry:{entry}", {"platform": "mobile", "entry_point": entry}, "latency"))
    reqs.append(("web:entry:web_finder", {"platform": "web", "entry_point": "web_finder"}, "latency"))
    return reqs


def report(payload, profile="all-entry", limit=200, min_samples=40, min_devices=2):
    rows = validate(payload)
    checks = []
    for name, selectors, expected in requirements(profile):
        selected = [r for r in rows if all(r[k] == v for k, v in selectors.items())]
        stats = summarize(selected, limit, legacy=profile == "ac-l1")
        reasons = []
        if selectors.get("scenario", "").startswith("after_") and any(
            r.get("input_age_ms_min") is None or r.get("input_age_ms_max") is None
            or r["input_age_ms_max"] > payload.get("immediate_change_max_ms", 5000) for r in selected
        ):
            reasons.append("immediate_change_age_missing_or_above_limit")
        count = stats["eligible"] if expected == "latency" else stats["taps"]
        if count < min_samples:
            reasons.append(f"insufficient_samples:{count}<{min_samples}")
        device_count = stats["devices_lower_bound"] if expected == "latency" else stats["devices_all_lower_bound"]
        if device_count < min_devices:
            reasons.append("insufficient_distinct_device_evidence")
        if expected == "latency":
            if count and (stats["p95_ms"] is None or stats["p95_ms"] > limit):
                reasons.append("p95_above_limit_or_unbounded")
        elif stats["outcomes"].get(expected, 0) != stats["taps"]:
            reasons.append(f"expected_only:{expected}")
        status = "FAIL" if reasons else "PASS"
        if not reasons and expected == "latency" and (stats["ci90"]["upper_ms"] is None
                                                     or stats["ci90"]["upper_ms"] > limit):
            status = "PASS_NOT_ROBUST"
        checks.append({"id": name, "selectors": selectors, "expected": expected,
                       "status": status, "reasons": reasons, **stats})
    global_reasons = []
    if payload["evidence_kind"] != "measured":
        global_reasons.append("synthetic_data_is_not_release_evidence")
    if payload.get("finalized") is not True:
        global_reasons.append("unfinalized_observation_window")
    if payload.get("untraced_taps", 0):
        global_reasons.append("taps_without_search_id")
    if sum(r.get("duplicate_taps", 0) for r in rows):
        global_reasons.append("duplicate_R1_search_ids")
    untraced = payload.get("untraced_taps", 0)
    # Missing UUID is still a tap/miss, including in overall quantiles and
    # fast-card share. Its unknown cell must not be guessed from other taps.
    untraced_rows = [dict(scenario="untraced", devices=0,
                         histogram=[dict(result="missing_outcome", ms=None, count=untraced)])] if untraced else []
    totals = summarize(rows + untraced_rows, limit)
    totals["uncorrelated_taps"] = untraced
    totals["correlated_unique_taps"] = totals["taps"] - untraced
    totals["raw_R1_events"] = totals["taps"] + sum(r.get("duplicate_taps", 0) for r in rows)
    if any(totals["outcomes"].get(k) for k in ("duplicate_outcome", "invalid_outcome", "missing_outcome")):
        global_reasons.append("incomplete_or_ambiguous_R1_terminal_join")
    if any(c["status"] == "FAIL" for c in checks):
        global_reasons.append("required_cohorts_failed_or_missing")
    return {"schema": 1, "profile": profile, "evidence_kind": payload["evidence_kind"],
            "window": payload.get("window"), "app_version": payload.get("app_version"),
            "client_build": payload.get("client_build"), "immediate_change_max_ms": payload.get("immediate_change_max_ms", 5000),
            "limit_ms": limit, "minimum_samples": min_samples, "minimum_devices": min_devices,
            "status": "FAIL" if global_reasons else ("PASS_NOT_ROBUST" if any(
                c["status"] == "PASS_NOT_ROBUST" for c in checks) else "PASS"),
            "reasons": global_reasons, "untraced_taps": payload.get("untraced_taps", 0),
            "totals_including_cold_offline_preferences": totals, "checks": checks,
            "observed_cohorts": [{**{d: r[d] for d in DIMENSIONS},
                                  "input_age_ms_min": r.get("input_age_ms_min"),
                                  "input_age_ms_max": r.get("input_age_ms_max"),
                                  **summarize([r], limit)} for r in rows],
            "notes": ["null p95/CI upper means unbounded or absent, never zero ms",
                      "failures count as +infinity; explicit paywall/verify are reported product gates",
                      "distinct device union uses a conservative lower bound, never sum of cohort counts",
                      "ac-l1 is legacy comparison only; all-entry requires preferences/cold/offline/scoped contexts",
                      "existing telemetry lacks lifecycle scenario tags; no scenario is inferred from a cache hit"]}


# Group inside Postgres. No user_id/search_id/device_id or raw event props are
# returned to Python. R1 is authoritative; companion calc_find... is NOT a tap.
PRODUCTION_SQL = """
WITH tap_rows AS (
 SELECT user_id, device_id, COALESCE(NULLIF(props::jsonb->>'search_id',''),'') sid,
 CASE WHEN props::jsonb->>'scenario' IN
 ('after_league_switch','after_preferences_change','after_format_switch','after_account_switch',
 'after_rank_change','warm','genuinely_cold','pinned_give','pinned_receive','targeted_opponent',
 'shape_intent','fair_sweep','offline_cached','free_preview','offline_empty','preview_exhausted','unverified')
 THEN props::jsonb->>'scenario' ELSE 'unclassified' END r1_scenario,
 CASE WHEN props::jsonb->>'input_age_ms' ~ '^[0-9]{1,12}$'
 THEN (props::jsonb->>'input_age_ms')::bigint END input_age_ms,
 CASE WHEN COALESCE(NULLIF(props::jsonb->>'source',''),'deck') IN
 ('deck','calculator','deck_error_retry','prefs_changed_strip','deck_summary_unpin',
 'deck_search_all','league_offer','league_target','usage_trends','deep_link','end_card_adjust',
 'team_review','web_finder') THEN COALESCE(NULLIF(props::jsonb->>'source',''),'deck')
 ELSE 'unknown' END entry_point,
 CASE WHEN source='web' OR platform='web' OR device_type='web' THEN 'web'
      WHEN source='mobile' OR platform='ios' OR device_type IN ('iphone','ipad','macos','android')
      THEN 'mobile' ELSE 'unknown' END platform
 FROM user_events WHERE event_type='find_trades_tapped'
 AND occurred_at >= :start AND occurred_at < :end AND app_version=:version
 AND (CAST(:build AS text) IS NULL OR props::jsonb->>'client_build'=CAST(:build AS text))
), taps AS (
 SELECT user_id,sid,MIN(entry_point) entry_point,MIN(platform) platform,
 MIN(device_id) device_id,MIN(r1_scenario) r1_scenario,MIN(input_age_ms) input_age_ms,
 COUNT(*) tap_count FROM tap_rows WHERE sid<>'' GROUP BY user_id,sid
), terminals AS (
 SELECT user_id,props::jsonb->>'search_id' sid,COUNT(*) terminal_count,
 MIN(event_type) event_type,MIN(props::jsonb->>'reason') reason,
 MIN(CASE WHEN props::jsonb->>'search_type' IN ('organic','pinned','fair_sweep')
     THEN props::jsonb->>'search_type' ELSE 'unknown' END) search_type,
 MIN(CASE WHEN props::jsonb->>'network_type' IN ('wifi','cellular','offline')
     THEN props::jsonb->>'network_type' ELSE 'unknown' END) network_type,
 MIN(CASE WHEN props::jsonb->>'launch_state' IN ('cold_launch','first_tap','repeat_tap')
     THEN props::jsonb->>'launch_state' ELSE 'unknown' END) launch_state,
 MIN(CASE WHEN props::jsonb->>'ms_from_tap' ~ '^[0-9]{1,12}$'
     THEN (props::jsonb->>'ms_from_tap')::bigint END) ms
 FROM user_events WHERE event_type IN ('trade_first_card_shown','trade_first_card_failed')
 AND occurred_at >= :start AND occurred_at < :outcome_end AND app_version=:version
 GROUP BY user_id,props::jsonb->>'search_id'
), joined AS (
 SELECT t.*,COALESCE(o.search_type,'unknown') search_type,
 COALESCE(o.network_type,'unknown') network_type,COALESCE(o.launch_state,'unknown') launch_state,
 CASE WHEN LEFT(t.r1_scenario,6)='after_' THEN
   CASE WHEN t.input_age_ms<=:immediate_ms THEN t.r1_scenario
        ELSE 'delayed_or_unknown_input_age' END
   WHEN t.entry_point='prefs_changed_strip' AND t.r1_scenario='unclassified'
        THEN 'delayed_or_unknown_input_age'
   ELSE t.r1_scenario END scenario,
 CASE WHEN o.terminal_count IS NULL THEN 'missing_outcome'
      WHEN o.terminal_count<>1 THEN 'duplicate_outcome'
      WHEN o.ms IS NULL THEN 'invalid_outcome'
      WHEN o.event_type='trade_first_card_shown' THEN 'shown'
      WHEN o.reason IN ('empty','error','abandoned','timeout','paywall','verify') THEN o.reason
      ELSE 'invalid_outcome' END result, o.ms
 FROM taps t LEFT JOIN terminals o ON o.user_id=t.user_id AND o.sid=t.sid
), histogram AS (
 SELECT platform,entry_point,search_type,network_type,launch_state,scenario,result,ms,COUNT(*) n
 FROM joined GROUP BY platform,entry_point,search_type,network_type,launch_state,scenario,result,ms
), cohort_devices AS (
 SELECT platform,entry_point,search_type,network_type,launch_state,scenario,
 COUNT(DISTINCT device_id) FILTER (WHERE result NOT IN ('paywall','verify')) devices,
 COUNT(DISTINCT device_id) devices_all,
 MIN(input_age_ms) input_age_ms_min,MAX(input_age_ms) input_age_ms_max,
 SUM(tap_count-1) duplicate_taps FROM joined
 GROUP BY platform,entry_point,search_type,network_type,launch_state,scenario
)
SELECT jsonb_build_object('schema',1,'evidence_kind','measured','finalized',true,
 'untraced_taps',(SELECT COUNT(*) FROM tap_rows WHERE sid=''),
 'cohorts',COALESCE((SELECT jsonb_agg(x.row) FROM (
 SELECT jsonb_build_object('platform',h.platform,'entry_point',h.entry_point,
 'search_type',h.search_type,'network_type',h.network_type,'launch_state',h.launch_state,
 'scenario',h.scenario,'devices',d.devices,'devices_all',d.devices_all,'duplicate_taps',d.duplicate_taps,
 'input_age_ms_min',d.input_age_ms_min,'input_age_ms_max',d.input_age_ms_max,
 'histogram',jsonb_agg(jsonb_build_object('result',h.result,'ms',h.ms,'count',h.n))) row
 FROM histogram h JOIN cohort_devices d USING
 (platform,entry_point,search_type,network_type,launch_state,scenario)
 GROUP BY h.platform,h.entry_point,h.search_type,h.network_type,h.launch_state,h.scenario,
 d.devices,d.devices_all,d.duplicate_taps,d.input_age_ms_min,d.input_age_ms_max) x),'[]'::jsonb))
"""


def production_snapshot(version, hours=24, settle_seconds=300, build=None, immediate_ms=5000):
    if not version or hours <= 0 or settle_seconds < 60:
        raise ValueError("production requires one version, positive hours, settle >=60s")
    # SQLAlchemy is imported only for the explicit production mode.
    from sqlalchemy import create_engine, text
    url = os.environ.get("DATABASE_URL_PROD", "")
    if not url.startswith(("postgres://", "postgresql://", "postgresql+psycopg2://")):
        raise ValueError("DATABASE_URL_PROD must identify Postgres")
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    now = datetime.now(timezone.utc)
    end = now - timedelta(seconds=settle_seconds)
    start = end - timedelta(hours=hours)
    fmt = lambda dt: dt.isoformat().replace("+00:00", "Z")
    params = {"start": fmt(start), "end": fmt(end), "outcome_end": fmt(now), "version": version,
              "build": build, "immediate_ms": immediate_ms}
    engine = create_engine(url, connect_args={"options":
        "-c default_transaction_read_only=on -c statement_timeout=15000"})
    try:
        with engine.connect() as conn:
            if conn.execute(text("SHOW transaction_read_only")).scalar() != "on":
                raise ValueError("server did not enforce read-only transaction")
            payload = conn.execute(text(PRODUCTION_SQL), params).scalar_one()
            conn.rollback()
    finally:
        engine.dispose()
    if isinstance(payload, str):
        payload = json.loads(payload)
    payload.update(window={"start": params["start"], "end": params["end"],
                           "outcomes_through": params["outcome_end"], "settle_seconds": settle_seconds},
                   app_version=version, client_build=build, immediate_change_max_ms=immediate_ms)
    return payload


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    source = ap.add_mutually_exclusive_group(required=True)
    source.add_argument("--input", type=Path, help="sanitized aggregate JSON")
    source.add_argument("--production", action="store_true", help="read-only aggregate query; URL from env only")
    ap.add_argument("--app-version", help="required for production; avoids pooling binaries")
    ap.add_argument("--client-build", help="exact R1 native build filter (e.g. 172); missing build is excluded")
    ap.add_argument("--immediate-change-ms", type=int, default=5000,
                    help="only change-to-tap ages at or below this qualify for immediate cohorts")
    ap.add_argument("--hours", type=float, default=24)
    ap.add_argument("--settle-seconds", type=int, default=300)
    ap.add_argument("--profile", choices=("all-entry", "ac-l1"), default="all-entry")
    ap.add_argument("--limit-ms", type=float, default=200)
    ap.add_argument("--min-samples", type=int, default=40)
    ap.add_argument("--min-devices", type=int, default=2)
    ap.add_argument("--snapshot-only", action="store_true", help="emit sanitized aggregate input, not a verdict")
    args = ap.parse_args(argv)
    try:
        if args.min_samples < 1 or args.min_devices < 1 or not math.isfinite(args.limit_ms) or args.limit_ms < 0 or args.immediate_change_ms < 0:
            raise ValueError("positive samples/devices and finite nonnegative latency limit required")
        payload = production_snapshot(args.app_version, args.hours, args.settle_seconds,
                                      args.client_build, args.immediate_change_ms) if args.production else json.loads(args.input.read_text())
        validate(payload)
        result = payload if args.snapshot_only else report(payload, args.profile, args.limit_ms, args.min_samples, args.min_devices)
    except Exception as error:
        # DB exception strings may contain connection details. Print only type.
        print(json.dumps({"status": "ERROR", "error_type": type(error).__name__,
                          "message": "No acceptance verdict: invalid input or unavailable read-only evidence."}))
        return 2
    print(json.dumps(result, indent=2, allow_nan=False))
    return 0 if args.snapshot_only or result["status"] in {"PASS", "PASS_NOT_ROBUST"} else 1


if __name__ == "__main__":
    sys.exit(main())
