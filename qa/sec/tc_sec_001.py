#!/usr/bin/env python3
"""
TC-SEC-001 — Operator-endpoint auth enforcement (cron-secret gate) + session gate.

Refutes/confirms the recon claim that admin endpoints are unauthenticated.
Every operator route calls _require_cron_auth(); this test proves the gate
empirically across environment configs:

  Config A  sqlite + no CRON_SECRET  -> gate DISABLED (localhost dev posture)
  Config B  sqlite + CRON_SECRET set -> gate ENFORCED (401 without/with-wrong secret)
  In-proc   _require_cron_auth() prod branch -> fail-closed 503 when secret unset

Plus a session-gate control: a session-protected mutating route rejects a
tokenless call with 401.

Usage:  python3 qa/sec/tc_sec_001.py
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import harness as H  # noqa: E402

SCRATCH = Path(__file__).resolve().parent / "scratch"
USER_B = "test_user_fp_1"
TEST_LEAGUE = "test_league_lakeview"
CRON_SECRET = "qa-sec-001-secret"

# Operator routes that MUST be cron-gated. (method, path, body)
OPERATOR_ROUTES = [
    ("GET",  "/api/admin/config", None),
    ("PUT",  "/api/admin/config/min_side_surplus", {"value": "150"}),
    ("GET",  "/api/admin/engine-metrics", None),
    ("GET",  "/api/feedback/admin", None),
    ("PUT",  "/api/feedback/admin/1/status", {"status": "new"}),
    ("GET",  "/api/debug/log", None),
    ("POST", "/api/feature-flags/reload", {}),
    ("POST", "/api/cron/realtime-tick", {}),
]

rec = H.CheckRecorder()


def hit(base: str, method: str, path: str, body, secret: str | None):
    api = H.Api(base, cron_secret=secret)
    if method == "GET":
        return api.get(path)
    if method == "PUT":
        return api.put(path, body)
    return api.post(path, body)


def config_b_enforced(db_path: Path) -> None:
    """sqlite + CRON_SECRET set -> the real enforcement guarantee."""
    print("\nCONFIG B — sqlite + CRON_SECRET set (gate must ENFORCE)")
    proc, base = H.boot_server(db_path, 5101, SCRATCH / "server_b.log",
                               env_overrides={"CRON_SECRET": CRON_SECRET})
    try:
        for method, path, body in OPERATOR_ROUTES:
            tag = f"{method} {path}"
            r_none = hit(base, method, path, body, secret=None)        # no header
            r_wrong = hit(base, method, path, body, secret="not-the-secret")
            r_ok = hit(base, method, path, body, secret=CRON_SECRET)
            rec.check(f"B:noheader:{tag}", r_none.status_code == 401,
                      f"no X-Cron-Secret -> {r_none.status_code} (want 401)")
            rec.check(f"B:wrong:{tag}", r_wrong.status_code == 401,
                      f"wrong secret -> {r_wrong.status_code} (want 401)")
            rec.check(f"B:correct:{tag}", r_ok.status_code not in (401, 503),
                      f"correct secret -> {r_ok.status_code} (want non-401/503)")
        # Constant-time compare: a near-miss secret must still 401.
        r_near = hit(base, "GET", "/api/admin/config", None, secret=CRON_SECRET[:-1])
        rec.check("B:near-miss", r_near.status_code == 401,
                  f"truncated secret -> {r_near.status_code} (want 401)")
    finally:
        H.stop_server(proc)


def config_a_localhost_open(db_path: Path) -> None:
    """sqlite + no CRON_SECRET -> gate disabled (documented dev posture)."""
    print("\nCONFIG A — sqlite + no CRON_SECRET (localhost dev: gate OPEN by design)")
    proc, base = H.boot_server(db_path, 5102, SCRATCH / "server_a.log",
                               env_overrides={"CRON_SECRET": None})
    try:
        open_count = 0
        for method, path, body in OPERATOR_ROUTES:
            r = hit(base, method, path, body, secret=None)
            if r.status_code not in (401, 503):
                open_count += 1
        rec.check("A:dev-open", open_count == len(OPERATOR_ROUTES),
                  f"{open_count}/{len(OPERATOR_ROUTES)} operator routes reachable "
                  f"without secret on local sqlite (by design; localhost-only)")
        # This config is the one `python3 run.py` runs in — flag as observation,
        # not a vuln, since it never binds to a public iface in prod (Render=PG).
        rec.info("CONFIG A is the local `run.py` posture; prod on Render uses "
                 "Postgres -> Config-C fail-closed path applies there.")
    finally:
        H.stop_server(proc)


def inproc_prod_branch() -> None:
    """Exercise _require_cron_auth()'s prod branch without a real Postgres:
    import on sqlite, flip module globals, call inside a request context."""
    print("\nIN-PROC — _require_cron_auth() prod branch (fail-closed / enforced)")
    script = r'''
import json, sys
sys.path.insert(0, ".")
import backend.server as srv
from werkzeug.exceptions import HTTPException

def run(is_prod, secret, header):
    srv._IS_PROD_ENV = is_prod
    srv._CRON_SECRET = secret
    hdrs = {}
    if header is not None:
        hdrs["X-Cron-Secret"] = header
    with srv.app.test_request_context("/api/admin/config", headers=hdrs):
        try:
            srv._require_cron_auth()
            return "pass"
        except HTTPException as e:
            return e.code

out = {
    "prod_no_secret":        run(True,  "",       None),       # want 503
    "prod_secret_no_header": run(True,  "s3cr3t", None),       # want 401
    "prod_secret_wrong":     run(True,  "s3cr3t", "nope"),     # want 401
    "prod_secret_correct":   run(True,  "s3cr3t", "s3cr3t"),   # want "pass"
    "dev_no_secret":         run(False, "",       None),       # want "pass" (open)
}
print(json.dumps(out))
'''
    env = {"DATABASE_URL": f"sqlite:///{SCRATCH / 'qa_scratch.db'}",
           "PYTHONPATH": str(H.ROOT)}
    import os
    full_env = {**os.environ, **env}
    full_env.pop("CRON_SECRET", None)
    proc = subprocess.run([sys.executable, "-c", script], cwd=H.ROOT, env=full_env,
                          capture_output=True, text=True, timeout=120)
    line = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else "{}"
    try:
        import json
        res = json.loads(line)
    except Exception:
        rec.check("INPROC:parse", False, f"could not parse logic-test output: "
                  f"{proc.stdout[-300:]} / err={proc.stderr[-300:]}")
        return
    rec.check("INPROC:prod-fail-closed", res.get("prod_no_secret") == 503,
              f"prod + no secret -> abort {res.get('prod_no_secret')} (want 503)")
    rec.check("INPROC:prod-no-header", res.get("prod_secret_no_header") == 401,
              f"prod + secret, no header -> {res.get('prod_secret_no_header')} (want 401)")
    rec.check("INPROC:prod-wrong", res.get("prod_secret_wrong") == 401,
              f"prod + wrong header -> {res.get('prod_secret_wrong')} (want 401)")
    rec.check("INPROC:prod-correct", res.get("prod_secret_correct") == "pass",
              f"prod + correct header -> {res.get('prod_secret_correct')} (want pass)")
    rec.check("INPROC:dev-open", res.get("dev_no_secret") == "pass",
              f"dev + no secret -> {res.get('dev_no_secret')} (want pass/open)")


def session_gate_control(db_path: Path) -> None:
    """Control: a session-gated mutating route must 401 a tokenless call."""
    print("\nSESSION GATE — mutating routes reject tokenless calls")
    proc, base = H.boot_server(db_path, 5103, SCRATCH / "server_s.log",
                               env_overrides={"CRON_SECRET": None})
    try:
        api = H.Api(base)  # no token
        for path, body in [("/api/trades/swipe", {"trade_id": "x", "decision": "like"}),
                           ("/api/rank3", {"ranked": ["1", "2", "3"]}),
                           ("/api/league/preferences", {"team_outlook": "contender"})]:
            r = api.post(path, body)
            rec.check(f"SESS:{path}", r.status_code == 401,
                      f"tokenless POST {path} -> {r.status_code} (want 401)")
        # And a bogus token is rejected too.
        r = H.Api(base, token="bogus-token-xyz").post(
            "/api/trades/swipe", {"trade_id": "x", "decision": "like"})
        rec.check("SESS:bogus-token", r.status_code == 401,
                  f"bogus token -> {r.status_code} (want 401)")
    finally:
        H.stop_server(proc)


def main() -> int:
    print("TC-SEC-001 — operator-endpoint auth enforcement")
    db_path = H.make_scratch_db(SCRATCH)
    config_b_enforced(db_path)
    config_a_localhost_open(db_path)
    inproc_prod_branch()
    session_gate_control(db_path)
    return rec.summary(SCRATCH / "TC-SEC-001-run.json",
                       meta={"test_case": "TC-SEC-001",
                             "executed_at": time.strftime("%Y-%m-%dT%H:%M:%S")})


if __name__ == "__main__":
    sys.exit(main())
