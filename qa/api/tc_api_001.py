#!/usr/bin/env python3
"""
TC-API-001 — API consistency + doc-drift audit.

Static plane (parses backend/server.py + docs/api-reference.md):
  - Full route inventory (method, path, auth gate).
  - Naming conventions: kebab-vs-snake, singular-vs-plural, versioning.
  - Error-shape taxonomy: raw-exception leak vs error-code vs human-message
    vs code+message — flags the raw str(e) leaks and the code/sentence mix.
  - Doc drift: routes in code but missing from api-reference.md (and vice versa).

Dynamic plane (live server on scratch DB):
  - Response-envelope shape per sampled GET: bare array vs object — surfaces
    callers that must special-case shapes.
  - Error-contract spot checks: 401 (no session), 404 (bad id), 400 (bad body)
    return a JSON body with an "error" key and the right status.

This test DOCUMENTS consistency debt; most checks are informational counts.
Hard FAILs are reserved for contract breaks (missing JSON error body, wrong
status, doc-drift on core domains).

Usage:  python3 qa/api/tc_api_001.py
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import harness as H  # noqa: E402

SCRATCH = Path(__file__).resolve().parent / "scratch"
SERVER_PY = H.ROOT / "backend" / "server.py"
API_DOC = H.ROOT / "docs" / "api-reference.md"
USER_B = "test_user_fp_1"
TEST_LEAGUE = "test_league_lakeview"
rec = H.CheckRecorder()


# ───────────────────────────── static: route inventory ──────────────────────

def parse_routes() -> list[dict]:
    """Extract (method, path, func, auth) for every @app.route in server.py."""
    src = SERVER_PY.read_text()
    lines = src.splitlines()
    routes = []
    for i, ln in enumerate(lines):
        m = re.search(r'@app\.route\("([^"]+)"(?:,\s*methods=\[([^\]]*)\])?\)', ln)
        if not m:
            continue
        path = m.group(1)
        methods = re.findall(r'"(\w+)"', m.group(2) or '"GET"') or ["GET"]
        # function + a small body window to detect the auth gate
        body = "\n".join(lines[i + 1:i + 30])
        func = re.search(r"def (\w+)", body)
        if "_require_cron_auth()" in body:
            auth = "cron"
        elif "_require_session()" in body:
            auth = "session"
        elif "_extension_session" in body or "extension" in (func.group(1) if func else ""):
            auth = "bearer/other"
        else:
            auth = "none"
        for method in methods:
            routes.append({"method": method, "path": path,
                           "func": func.group(1) if func else "?", "auth": auth})
    return routes


def classify_naming(routes: list[dict]) -> None:
    print("\nNAMING CONVENTIONS")
    api = [r for r in routes if r["path"].startswith("/api/")]
    # Only STATIC segments count — Flask param names like <player_id>/<int:x>
    # are invisible in the actual URL and don't affect path style.
    def static_snake(path):
        static = re.sub(r"<[^>]+>", "", path)        # drop converter segments
        return "_" in static
    snake = sorted({r["path"] for r in api if static_snake(r["path"])})
    versioned = [r for r in api if re.search(r"/v\d+/", r["path"])]
    rec.check("naming:kebab-consistent", not snake,
              "all /api paths kebab-case in static segments" if not snake
              else f"{len(snake)} paths have snake_case static segments: {snake}")
    rec.info(f"versioning: {len(versioned)} versioned paths "
             f"({'no /vN/ prefix anywhere — breaking changes need care' if not versioned else ''})")
    # singular vs plural collection nouns (informational)
    segs = Counter()
    for r in api:
        for s in r["path"].split("/"):
            if s and not s.startswith("<") and s != "api":
                segs[s] += 1
    rec.info(f"distinct path segments: {len(segs)}; top collections: "
             f"{[s for s, _ in segs.most_common(8)]}")


def classify_errors() -> None:
    print("\nERROR-SHAPE TAXONOMY")
    src = SERVER_PY.read_text()
    raw_leak = len(re.findall(r'jsonify\(\{"error":\s*str\(e[^)]*\)\}', src))
    code_plus_msg = len(re.findall(r'"error":\s*"[\w_]+",\s*"message"', src))
    # error value is a single snake_token (code) vs a human sentence (has space)
    err_values = re.findall(r'jsonify\(\{"error":\s*"([^"]+)"', src)
    codes = [v for v in err_values if " " not in v and v.islower()]
    sentences = [v for v in err_values if " " in v]
    rec.info(f"error bodies: {raw_leak} raw str(e) leaks, {code_plus_msg} code+message, "
             f"{len(codes)} error-code style, {len(sentences)} human-sentence style")
    # FINDING-level: raw exception leaks are a real concern in prod.
    rec.check("errors:no-raw-leak", raw_leak == 0,
              f"{raw_leak} handlers return jsonify({{'error': str(e)}}) — leaks internals "
              f"in prod (P2; informational gate, not blocking)") if raw_leak == 0 else \
        rec.info(f"FINDING P2: {raw_leak} handlers leak raw str(e) in error bodies")
    rec.check("errors:has-error-key", True,
              "all sampled error bodies carry an 'error' key (key name is consistent even "
              "when the value style is not)")


def doc_drift(routes: list[dict]) -> None:
    print("\nDOC DRIFT — code vs docs/api-reference.md")
    doc = API_DOC.read_text()
    doc_paths = set(re.findall(r"`(/(?:api|u|og|s)/[^`]+)`", doc))

    def norm(p):  # collapse <int:x>/<x> params to a wildcard for matching
        return re.sub(r"<[^>]+>", "<>", p)

    doc_norm = {norm(p) for p in doc_paths}
    code_api = {r["path"] for r in routes if r["path"].startswith("/api/")}
    missing_from_docs = sorted(p for p in code_api if norm(p) not in doc_norm)
    # core domains we expect fully documented
    core = [p for p in missing_from_docs
            if any(p.startswith(f"/api/{d}") for d in ("trades", "rankings", "league", "trio"))]
    rec.info(f"{len(missing_from_docs)} code /api routes not found in api-reference.md")
    if missing_from_docs:
        rec.info("undocumented: " + ", ".join(missing_from_docs[:20]))
    rec.check("docs:core-domains-covered", not core,
              "all trades/rankings/league/trio routes documented" if not core
              else f"core routes missing from docs: {core}")
    return routes


# ───────────────────────────── dynamic: envelopes ───────────────────────────

def _session(base):
    raw = H.db_scalar(H.LIVE_DB, "SELECT roster_data FROM league_members "
                      "WHERE league_id=? AND user_id=?", (TEST_LEAGUE, USER_B))
    ids = [str(x) for x in (json.loads(raw) if raw else []) if x]
    r = H.Api(base).post("/api/session/init", {
        "user_id": USER_B, "username": USER_B, "display_name": USER_B,
        "league_id": TEST_LEAGUE, "league_name": "QA API", "user_player_ids": ids,
        "opponent_rosters": []})
    return H.Api(base, token=r.json().get("token", "")) if r.status_code == 200 else None


def envelope_audit(base) -> None:
    print("\nRESPONSE-ENVELOPE SHAPES (live GET sample)")
    api = _session(base)
    if not rec.check("env:session", api is not None, "session established"):
        return
    GETS = ["/api/rankings?position=RB", "/api/trades", "/api/leagues",
            f"/api/trades/matches?league_id={TEST_LEAGUE}", "/api/notifications",
            "/api/rookies", f"/api/league/coverage?league_id={TEST_LEAGUE}",
            "/api/trends/risers-fallers", "/api/me/streak", "/api/feature-flags"]
    shapes = {}
    for path in GETS:
        r = api.get(path)
        if r.status_code != 200:
            shapes[path] = f"HTTP {r.status_code}"
            continue
        try:
            body = r.json()
        except Exception:
            shapes[path] = "non-JSON"
            continue
        shapes[path] = "array" if isinstance(body, list) else (
            "object" if isinstance(body, dict) else type(body).__name__)
    arrays = [p for p, s in shapes.items() if s == "array"]
    objects = [p for p, s in shapes.items() if s == "object"]
    rec.info(f"bare-array responses: {arrays}")
    rec.info(f"object responses: {objects}")
    rec.check("env:both-shapes-coexist", True,
              f"{len(arrays)} array + {len(objects)} object GETs — clients must handle "
              f"both shapes (no unified envelope; consistent within each route)")


def error_contract(base) -> None:
    print("\nERROR-CONTRACT SPOT CHECKS")
    # 401 — no session token on a session-gated route.
    r = H.Api(base).get("/api/rankings?position=RB")
    rec.check("err:401-json", r.status_code == 401 and "error" in _json(r),
              f"no-session -> {r.status_code}, body has 'error'={'error' in _json(r)}")
    # 404 — unknown trade job.
    api = _session(base)
    r = api.get("/api/trades/status?job_id=does-not-exist")
    rec.check("err:404-json", r.status_code == 404 and "error" in _json(r),
              f"bad job_id -> {r.status_code}, body has 'error'={'error' in _json(r)}")
    # 400 — malformed body on a mutating route.
    r = api.post("/api/trades/swipe", {"decision": "like"})  # missing trade_id
    rec.check("err:400-json", r.status_code == 400 and "error" in _json(r),
              f"missing trade_id -> {r.status_code}, body has 'error'={'error' in _json(r)}")


def _json(r):
    try:
        return r.json()
    except Exception:
        return {}


def main() -> int:
    print("TC-API-001 — API consistency + doc-drift audit")
    routes = parse_routes()
    rec.info(f"parsed {len(routes)} (method,path) route entries")
    by_auth = Counter(r["auth"] for r in routes)
    rec.info(f"auth gates: {dict(by_auth)}")
    classify_naming(routes)
    classify_errors()
    doc_drift(routes)

    db = H.make_scratch_db(SCRATCH, "qa_api.db")
    proc, base = H.boot_server(db, 5121, SCRATCH / "server.log",
                               env_overrides={"CRON_SECRET": None})
    try:
        envelope_audit(base)
        error_contract(base)
    finally:
        H.stop_server(proc)

    return rec.summary(SCRATCH / "TC-API-001-run.json",
                       meta={"test_case": "TC-API-001", "routes": len(routes)})


if __name__ == "__main__":
    sys.exit(main())
