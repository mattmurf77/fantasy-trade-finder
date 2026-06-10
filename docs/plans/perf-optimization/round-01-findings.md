---
round: 01
direction: subagent->primary
thread: perf-optimization
date: 2026-06-07
author: research+audit agents
status: answered
surface: cross-client
references:
  - round-01-task.md
---

## Summary
- 5 research docs + 6 codebase audits (**38 RICE-P-scored findings**) produced
  in `docs/code-audit/perf-optimization/`.
- **Reframing:** the 4.84 MB player payload is a WEB concern, not mobile —
  mobile uses the 25-byte `/warm` ping and RN auto-gzips. (Down-ranked
  OBS-API-02's apparent 12.0 to a measured ~0 mobile no-op.)
- 38 findings consolidated into **16 initiatives**, sequenced into 3 waves.
- Top mobile wins: INIT-01 splash decouple (RICE-P 16.0), INIT-02 cold-cache
  (9.6), INIT-03 ELO memo (6.4), INIT-04 prefetch (6.4).
- Irreducible floor: Render free-tier cold start (30–60 s, `--workers 1`).

## Findings
### Tasks 1–4 (research, audit, synthesis, design)
All deliverables are in `docs/code-audit/perf-optimization/` (branch
`audit/perf-optimization`). Key artifacts:
- `plan/optimization-plan.md` §1 — the reframing + the four real latency drivers.
- `plan/priority-matrix.md` — all 38 findings scored & routed to initiatives,
  by wave.
- `design/requirements/init-01..16-*.md` — per-initiative ACs + invariants.

Per-agent observation highlights (full detail in `observations/agent-0X-*/findings.md`):
- **agent-01 api-client:** measured `/api/sleeper/players` 4.84 MB/7.48 s
  uncompressed vs 676 KB/1.03 s gzipped; no `Accept-Encoding`; double warm; no
  timeout; fixed 1.5 s poll.
- **agent-02 data-fetch/cache:** no persisted query cache; player-data keys omit
  league/format (stale on switch); prefetch Trios-only; dead focusManager.
- **agent-03 backend-routes:** players route ships 53 fields; no ETag/Cache-Control;
  `before_request` blocking `UPDATE users` every authed req; `session_init`
  full dual-format rebuild.
- **agent-04 backend-data/DB:** ELO recomputed 3–4×/request; trade-gen
  combinatorial (~690k iters/opponent, truncates on 1 s deadline); missing
  `players.position` index; cold-cache serial dual-CSV.
- **agent-05 rn-rendering:** TiersScreen renders whole pool unvirtualized;
  non-memoized cards; StrengthBar 24 slivers/card. (Cleared: no avatar lists;
  all FlatLists have keyExtractor.)
- **agent-06 network/cold-start:** compression already at edge; mobile uses
  `/warm` so on-wire bytes ≈ non-issue for mobile; cold dyno re-fetches 5 MB
  upstream (no baked cache, ephemeral disk); splash gated on warm ping (16.0).

## Proposed Changes
See `plan/priority-matrix.md` for the full 16-initiative roll-up routed to 3
waves. (Implemented in round 02 for Wave 1.)

## Answers to Questions
n/a (round 01 had no questions)

## Open Questions
1. Infra cold-start mitigation (warm-ping cron / paid dyno / `--workers`) is a
   user cost/account decision — surfaced to primary. → see
   `artifacts/questions-for-user.md`.

## Evidence
- `../../code-audit/perf-optimization/` — the full research + audit + plan + design tree.
