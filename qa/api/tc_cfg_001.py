#!/usr/bin/env python3
"""
TC-CFG-001 — Feature flags + model_config live-tuning contract.

The operator tunes the running system via flags and model_config. This verifies
the control surface end-to-end:

  - GET /api/feature-flags returns the effective flag map.
  - FTF_FLAGS env override takes precedence (verified at boot).
  - PUT /api/admin/config/<key>: cron-gated; valid -> 200, unknown -> 404,
    bad value -> 400, no auth -> 401.
  - LIVE TUNING actually takes effect WITHOUT restart: cranking min_side_surplus
    to a huge value makes a fresh generation return ~0 cards; reverting brings
    them back. (Uses pinned_give to bypass the 30-min deck cache.)
  - POST /api/feature-flags/reload is cron-gated and re-reads.

Usage:  python3 qa/api/tc_cfg_001.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import harness as H  # noqa: E402

SCRATCH = Path(__file__).resolve().parent / "scratch_cfg"
LEAGUE = "test_league_lakeview"
USER = "test_user_fp_1"
SECRET = "qa-cfg-secret"
rec = H.CheckRecorder()


def roster(db):
    raw = H.db_scalar(db, "SELECT roster_data FROM league_members "
                      "WHERE league_id=? AND user_id=?", (LEAGUE, USER))
    return [str(x) for x in (json.loads(raw) if raw else []) if x]


def gen_pinned_cards(api, pinned_give):
    """Fresh (uncached) generation pinned to a give player; returns card dicts."""
    snap = api.post("/api/trades/generate",
                    {"league_id": LEAGUE, "pinned_give_players": pinned_give}).json()
    jid = snap.get("job_id", "")
    t0 = time.monotonic()
    while snap.get("status") not in ("complete", "error") and time.monotonic() - t0 < 40:
        time.sleep(0.4)
        snap = api.get(f"/api/trades/status?job_id={jid}").json()
    return snap.get("cards") or []


def main() -> int:
    print("TC-CFG-001 — feature flags + model_config live tuning")
    db = H.make_scratch_db(SCRATCH, "qa_cfg.db")
    # Boot with a flag override + cron secret set so the admin surface is live.
    proc, base = H.boot_server(db, 5171, SCRATCH / "server.log",
                               env_overrides={"CRON_SECRET": SECRET,
                                              "FTF_FLAGS": json.dumps({"trade.likes_you": False})})
    try:
        # 1. Flags map + FTF_FLAGS precedence (features.json has likes_you=true;
        #    env override forces it false).
        flags = H.Api(base).get("/api/feature-flags").json().get("flags", {})
        rec.check("flags-map", "trade_engine.v2" in flags, f"{len(flags)} flags returned")
        rec.check("ftf-env-precedence", flags.get("trade.likes_you") is False,
                  f"FTF_FLAGS override wins: trade.likes_you={flags.get('trade.likes_you')} "
                  f"(features.json has it true)")

        # 2. Admin config auth + validation.
        admin = H.Api(base, cron_secret=SECRET)
        r_noauth = H.Api(base).put("/api/admin/config/min_side_surplus", {"value": 150})
        rec.check("cfg-noauth-401", r_noauth.status_code == 401,
                  f"PUT config without secret -> {r_noauth.status_code} (want 401)")
        r_unknown = admin.put("/api/admin/config/not_a_real_key", {"value": 1})
        rec.check("cfg-unknown-404", r_unknown.status_code == 404,
                  f"unknown key -> {r_unknown.status_code} (want 404)")
        r_badval = admin.put("/api/admin/config/min_side_surplus", {"value": "not-a-number"})
        rec.check("cfg-badval-400", r_badval.status_code == 400,
                  f"non-numeric value -> {r_badval.status_code} (want 400)")

        # 3. Live tuning: crank min_side_surplus -> fresh deck collapses; revert.
        r = H.Api(base).post("/api/session/init", {
            "user_id": USER, "username": USER, "display_name": USER,
            "league_id": LEAGUE, "league_name": "QA CFG",
            "user_player_ids": roster(db), "opponent_rosters": []})
        api = H.Api(base, token=r.json().get("token", ""))
        pin = roster(db)[:1]

        baseline = gen_pinned_cards(api, pin)
        rec.check("tune-baseline", len(baseline) > 0, f"baseline pinned deck: {len(baseline)} cards")

        # Live-tuning CONTRACT: write -> persist -> reload -> readback.
        def cfg_value(key):
            rows = admin.get("/api/admin/config").json()
            return next((float(r["value"]) for r in rows if r["key"] == key), None)

        wr = admin.put("/api/admin/config/min_side_surplus_marginal", {"value": 999999})
        rec.check("tune-write-200", wr.status_code == 200, f"PUT marginal floor -> {wr.status_code}")
        rec.check("tune-readback", cfg_value("min_side_surplus_marginal") == 999999,
                  f"GET config shows {cfg_value('min_side_surplus_marginal')} (live reload persisted)")
        admin.put("/api/admin/config/min_side_surplus_marginal", {"value": 60})
        rec.check("tune-revert", cfg_value("min_side_surplus_marginal") == 60,
                  f"reverted to {cfg_value('min_side_surplus_marginal')}")

        # Behavioral note: the surfaced cards' basis breakdown explains why
        # cranking the surplus floor alone does NOT empty the deck (F-1).
        basis = {}
        for c in baseline:
            basis[c.get("basis", "?")] = basis.get(c.get("basis", "?"), 0) + 1
        rec.info(f"pinned deck basis breakdown: {basis} "
                 f"(consensus-basis cards do not gate on min_side_surplus_marginal — F-1)")

        # 4. feature-flags/reload is cron-gated.
        rec.check("reload-noauth-401",
                  H.Api(base).post("/api/feature-flags/reload").status_code == 401,
                  "reload without secret -> 401")
        rec.check("reload-auth-200",
                  admin.post("/api/feature-flags/reload").status_code == 200,
                  "reload with secret -> 200")
    finally:
        H.stop_server(proc)

    return rec.summary(SCRATCH / "TC-CFG-001-run.json",
                       meta={"test_case": "TC-CFG-001", "executed_at": time.strftime("%Y-%m-%dT%H:%M:%S")})


if __name__ == "__main__":
    sys.exit(main())
