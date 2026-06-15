#!/usr/bin/env python3
"""
TC-API-002 — Public-route auth-intent audit + abuse-surface checks.

TC-API-001 found 44 'none'-auth routes. Most are intentionally public; this
audits whether each DESERVES to be, with the spotlight on STATE-MUTATING public
routes (the real risk) and basic abuse hygiene.

  - Enumerate 'none'-auth routes; split read (GET) vs mutating (POST/PUT/DELETE).
  - Every mutating public route must be on the intentional-public allowlist;
    anything else is flagged for review.
  - Dynamic: mutating public routes survive empty/garbage bodies (robustness),
    and CORS posture is reported.

Usage:  python3 qa/api/tc_api_002.py
"""
from __future__ import annotations

import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import harness as H  # noqa: E402

SERVER_PY = H.ROOT / "backend" / "server.py"
SCRATCH = Path(__file__).resolve().parent / "scratch_api2"
rec = H.CheckRecorder()

# Routes that are public BY DESIGN and may mutate state. Each with a reason.
INTENTIONAL_PUBLIC_MUTATIONS = {
    "/api/session/init":      "creates the session itself (no token exists yet)",
    "/api/session/demo":      "demo bootstrap, creates a throwaway session",
    "/api/feedback":          "anonymous TestFlight feedback (optional session, idempotent on client_id)",
    "/api/extension/auth":    "issues the extension bearer token (pre-auth handshake)",
    "/api/league/parse-url":  "pure URL parsing, no persistent mutation",
}


def parse_none_auth_routes():
    src = SERVER_PY.read_text()
    lines = src.splitlines()
    routes = []
    for i, ln in enumerate(lines):
        m = re.search(r'@app\.route\("([^"]+)"(?:,\s*methods=\[([^\]]*)\])?\)', ln)
        if not m:
            continue
        path, methods = m.group(1), re.findall(r'"(\w+)"', m.group(2) or '"GET"') or ["GET"]
        body = "\n".join(lines[i + 1:i + 55])
        # Session gates: _require_session() and the stricter
        # _require_initialized_session() (added after TC-API-001).
        if ("_require_cron_auth()" in body or "_require_session()" in body
                or "_require_initialized_session()" in body):
            continue
        routes.append({"path": path, "methods": methods,
                       "mutating": any(x in methods for x in ("POST", "PUT", "DELETE", "PATCH"))})
    return routes


def audit_static():
    print("\nSTATIC — public-route classification")
    routes = parse_none_auth_routes()
    api = [r for r in routes if r["path"].startswith("/api/")]
    reads = [r for r in api if not r["mutating"]]
    muts = [r for r in api if r["mutating"]]
    rec.info(f"{len(api)} public /api routes: {len(reads)} read-only, {len(muts)} mutating")

    unexpected = [r["path"] for r in muts if r["path"] not in INTENTIONAL_PUBLIC_MUTATIONS]
    rec.check("public-mutations-allowlisted", not unexpected,
              "all public mutating routes are intentional"
              if not unexpected else f"UNREVIEWED public mutating routes: {unexpected}")
    for r in muts:
        if r["path"] in INTENTIONAL_PUBLIC_MUTATIONS:
            rec.info(f"  public mutation OK: {r['path']} — {INTENTIONAL_PUBLIC_MUTATIONS[r['path']]}")
    # Read-only public routes are low risk; list the non-passthrough ones for awareness.
    notable = [r["path"] for r in reads
               if not r["path"].startswith(("/api/sleeper/", "/api/feature-flags"))]
    rec.info(f"public read-only (non-passthrough): {notable}")
    return muts


def probe_dynamic(muts):
    print("\nDYNAMIC — robustness + CORS")
    db = H.make_scratch_db(SCRATCH, "qa_api2.db")
    proc, base = H.boot_server(db, 5181, SCRATCH / "server.log",
                               env_overrides={"CRON_SECRET": None})
    try:
        # Mutating public routes must not 500 on empty/garbage bodies.
        crashed = []
        for r in muts:
            path = r["path"]
            if "<" in path:           # skip parameterized for the generic probe
                continue
            resp = H.Api(base).post(path, {})        # empty body
            if resp.status_code >= 500:
                crashed.append((path, resp.status_code))
            resp2 = H.Api(base).call("POST", path, data="not json",
                                     headers={"Content-Type": "application/json"})
            if resp2.status_code >= 500:
                crashed.append((path + " (garbage)", resp2.status_code))
        rec.check("public-mutations-robust", not crashed,
                  "public mutating routes survive empty/garbage bodies"
                  if not crashed else f"5xx on: {crashed}")

        # CORS posture (recon said none — confirm and report).
        r = H.Api(base).get("/api/feature-flags",
                            headers={"Origin": "https://evil.example.com"})
        acao = r.headers.get("Access-Control-Allow-Origin")
        rec.check("cors-not-wildcard", acao != "*",
                  f"Access-Control-Allow-Origin={acao!r} "
                  f"({'no CORS headers — same-origin only, safe default' if acao is None else acao})")

        # session/init with a totally empty body must not crash (defaults applied).
        r = H.Api(base).post("/api/session/init", {})
        rec.check("session-init-empty-safe", r.status_code in (200, 400),
                  f"empty session_init -> {r.status_code} (graceful, not 5xx)")
    finally:
        H.stop_server(proc)


def main() -> int:
    print("TC-API-002 — public-route auth-intent audit")
    muts = audit_static()
    probe_dynamic(muts)
    return rec.summary(SCRATCH / "TC-API-002-run.json",
                       meta={"test_case": "TC-API-002", "executed_at": time.strftime("%Y-%m-%dT%H:%M:%S")})


if __name__ == "__main__":
    sys.exit(main())
