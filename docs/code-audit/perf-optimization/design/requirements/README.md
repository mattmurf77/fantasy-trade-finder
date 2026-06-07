# Feature Requirements — Index & Format

One requirements file per optimization initiative (the "features"). Each is
derived from [`../lld.md`](../lld.md), [`../../plan/optimization-plan.md`](../../plan/optimization-plan.md),
and the source observations in [`../../observations/`](../../observations/).

## Files

| File | Initiative | Wave | Scope |
|------|-----------|:----:|:-----:|
| `init-01-splash-decouple.md` | Decouple splash from network boot legs | 1 | [M] |
| `init-02-coldstart-cache.md` | Bake + parallelize the Sleeper player cache | 1 | [B] |
| `init-03-elo-memoization.md` | Memoize ELO/stats recompute | 1 | [B] |
| `init-04-nav-prefetch.md` | Extend navigation prefetch beyond Trios | 1 | [M] |
| `init-05-focus-online-manager.md` | Wire focusManager + onlineManager | 1 | [M] |
| `init-06-touch-activity-throttle.md` | Throttle `touch_user_activity` | 1 | [B] |
| `init-07-persisted-cache-keys.md` | Persisted query cache + key scoping | 2 | [M] |
| `init-08-session-init-optimistic.md` | session_init slim + optimistic shell | 2–3 | [M]+[B] |
| `init-09-trade-gen-prune.md` | Prune trade-generation candidates | 2 | [B] |
| `init-10-web-player-payload.md` | Web player payload (rebind+slim+cache) | 2 | [W] |
| `init-11-render-memo-virtualization.md` | Render memo + Tiers virtualization | 2–3 | [M] |
| `init-12-api-client-resilience.md` | Timeout + GET retry + warm dedup | 1–2 | [M] |
| `init-13-poll-backoff.md` | Trade-status poll backoff | 2 | [M] |
| `init-14-db-hygiene.md` | Index, bulk upsert, match narrow, Trends SQL | 1–2 | [B] |
| `init-15-compression-docs.md` | Compression/encoding documentation | 3 | [M]/[B] |
| `init-16-league-activity-dedup.md` | League activity double-fetch | defer | [M] |

## Required structure for every file

```
# REQ — INIT-XX: <Title>

- **Initiative / Wave / Scope:** INIT-XX · Wave N · [M]/[W]/[B]/[X]
- **Source observations:** OBS-…
- **Peak RICE-P:** N

## Problem statement
One or two sentences: the user-facing or system symptom.

## User stories
- As a <role>, I want <capability>, so that <benefit>.   (1–4 stories)
  Roles: "dynasty manager" (end user / tester), "operator", "developer".

## Functional requirements
- FR-1 … (numbered, testable, implementation-level "what")

## Acceptance criteria
- [ ] AC-1 — Given/When/Then where it helps; each must be objectively checkable.

## Related components
file:line references (pull from the LLD/observations).

## Prerequisite components / dependencies
What must land first (other INITs, a test harness, an infra change). "None" is valid.

## Non-functional requirements & invariants
Perf target, cross-client invariants (ELO math, tier bands, per-format
independence — `docs/cross-client-invariants.md`), risk/rollback.

## Out of scope
Explicit exclusions.
```

## Conventions

- Keep acceptance criteria **measurable** (a tester or a CI check can verify).
- Tie every requirement back to a `file:line` from the observations.
- Where an initiative spans waves (e.g. INIT-08, INIT-11), split FRs/ACs by wave.
- Flag any cross-client invariant explicitly in Non-functional.
