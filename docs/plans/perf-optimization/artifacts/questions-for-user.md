# Questions / decisions awaiting the user

These need YOUR input (cost, account access, or product preference). None block
autonomous Wave-2 work — each has a documented default/workaround so a new
session keeps moving. Answer at your convenience; the next session incorporates
your answers when given.

---

### Q1 — Render cold-start mitigation (the biggest remaining lever) 🔴
No code change removes a true Render free-tier cold start (30–60 s wake;
`--workers 1`). Three options, cheapest first:
- **(a) External warm-ping** — UptimeRobot (or a Render cron) hitting
  `/api/session/ping` every ~10 min. ≈$0, masks ~90% of sessions. Needs you to
  create the monitor, OR approve me adding a Render cron to `render.yaml`.
- **(b) `--workers 2`** — removes single-worker contention; risks free-tier OOM.
  Needs your OK (your Render account).
- **(c) Render Starter dyno ($7/mo, always-on)** — the only complete fix.
**Decision needed:** which of a/b/c? (I can do a-via-render.yaml and c-guidance;
b needs your risk acceptance; c is a billing action you take.)
**Default if unanswered:** none applied (code waves proceed; floor remains).

### Q2 — Merge the audit docs to `main`? 🟡
`docs/code-audit/perf-optimization/` (~38 files: research, plan, HLD/LLD/
requirements) is on branch `audit/perf-optimization`, deliberately kept off the
Wave-1 code PR. Merge it to `main` as reference, or leave on its branch?
**Default if unanswered:** leave on branch (no action).

### Q3 — Build / ship cadence 🟡
Wave-1 mobile changes are on `main` but NOT built to TestFlight yet. Do you want
an EAS build + TestFlight submit **after each wave**, or **batch** several waves
into one build? (Builds cost EAS minutes + your TestFlight processing time.)
**Default if unanswered:** hold builds; ship one TestFlight build after Wave 2
lands (so the cold-start + cache work is testable together).

### Q4 — Profiling auth token for the INIT-08 backend split 🟡
The `session_init` backend slim (defer trade-service build) should be preceded
by a profiling spike on a real authed `session_init` — which needs a session
token / your test account. Also note `#64` already parallelized session_init —
the remaining win may be small. Provide a test token / approve a profiling
harness, or skip the backend split?
**Default if unanswered:** do the INIT-08 **client** optimistic-shell half only;
leave the backend split until profiled.

### Q5 — Web player-payload work (INIT-10) priority 🟡
INIT-10 (rebind route → slim 53→17 fields → ETag/Cache-Control) is **web-only**
— it does NOT change mobile latency, but frees origin CPU on the shared single
worker (a second-order mobile benefit). Do it now, or deprioritize since your
pain is mobile?
**Default if unanswered:** deprioritize (skip in Wave 2; revisit if origin CPU
becomes a bottleneck).

### Q6 — Persisted-cache storage: AsyncStorage vs MMKV 🟢
INIT-07 needs a query-cache persister. Locked default is **AsyncStorage**
(already a dep, no native module). **MMKV** is faster (synchronous) but adds a
native dependency + an Expo prebuild/config-plugin step. Stay on AsyncStorage,
or upgrade to MMKV?
**Default if unanswered:** AsyncStorage (no new native dep) — INIT-07 proceeds
on this default; switching to MMKV later is a contained change.

---

## Items I will decide myself (NOT user inputs — listed for transparency)
- INIT-02 build.sh fetch-only refinement vs full-server-import bake — primary's
  call (default: leave as-is; it's non-fatal/harmless).
- Whether to parallelize Wave-2 agents — yes, on disjoint files, as in Wave 1.
- Test harness construction (top-K trade equivalence, key-scoping tests) — mine.
- `docs/data-dictionary.md` / `docs/runbook.md` / ADR updates — mine (per CLAUDE.md).
