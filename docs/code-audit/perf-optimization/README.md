# Performance Optimization — Code Audit

Goal: make the FTF mobile app's **player and trade data fetch + load** feel
fast. This folder holds the full research → audit → plan → design pipeline.

User-reported pain (the trigger): "the mobile app takes too long to fetch
players & trade information."

## How this folder is organized

```
perf-optimization/
├── README.md                  ← you are here (index + status)
├── research/                  ← external best-practices (Phase 1)
│   ├── 00-research-methodology.md   (framework for research agents)
│   ├── 01-mobile-data-fetching.md
│   ├── 02-backend-api-performance.md
│   ├── 03-caching-strategies.md
│   ├── 04-rn-rendering-list-perf.md
│   └── 05-network-coldstart.md
├── templates/                 ← consistency scaffolding for the audit
│   ├── scoring-criteria.md          (RICE-P definition — READ FIRST)
│   ├── observation-template.md      (copy-per-finding block)
│   └── recommendation-example.md    (a model observation at target depth)
├── observations/              ← codebase audit output (Phase 2)
│   ├── agent-01-api-client/
│   ├── agent-02-data-fetching-cache/
│   ├── agent-03-backend-routes/
│   ├── agent-04-backend-data-db/
│   ├── agent-05-rn-rendering/
│   └── agent-06-network-coldstart/
├── plan/                      ← synthesis (Phase 3)
│   ├── optimization-plan.md
│   └── priority-matrix.md
└── design/                    ← updated design + requirements (Phase 4)
    ├── hld.md
    ├── lld.md
    └── requirements/                (feature-by-feature .md)
```

## Pipeline status

| Phase | Output | Status |
|-------|--------|--------|
| 0. Scaffolding | methodology, scoring, templates | ✅ done |
| 1. Research | 5 research docs | ✅ done |
| 2. Audit | 6 observation sets (38 scored findings) | ✅ done |
| 3. Synthesis | prioritized plan + matrix (16 initiatives) | ✅ done |
| 4. Design | HLD, LLD, 16 requirement files | ✅ done |

## Headline result (the reframing)

The user-reported pain — "mobile takes too long to fetch players & trades" — is
**not** caused by the 4.84 MB player payload that first looks guilty. The mobile
client fetches a 25-byte `/api/sleeper/players/warm` ping (not the full body),
and RN auto-negotiates gzip; the big payload is a **web-client** concern. The
real mobile latency is **boot sequencing, cold-start cache population, redundant
ELO recompute, and missing client cache/prefetch**. See
[`plan/optimization-plan.md` §1](./plan/optimization-plan.md).

**Top win** (RICE-P 16.0, all six agents' highest): INIT-01 — stop gating the
splash on a network warm-ping the first screen doesn't need.

## Where to start reading

1. [`plan/optimization-plan.md`](./plan/optimization-plan.md) — the narrative + waves + decisions.
2. [`plan/priority-matrix.md`](./plan/priority-matrix.md) — all 38 findings scored & routed.
3. [`design/hld.md`](./design/hld.md) → [`design/lld.md`](./design/lld.md) → [`design/requirements/`](./design/requirements/) — what to build.

## Ground rules

- **Audit is observation-only.** No code changes in this effort — it produces
  documentation, scores, and a plan. Implementation is a separate, later
  effort gated on the plan.
- **Everything is `.md`.** All outputs live in this tree.
- **RICE-P everywhere.** Every observation is scored on the one comparable
  scale defined in `templates/scoring-criteria.md`.

## Stack context (for readers)

RN 0.81 / Expo SDK 54 (new arch, Hermes, Reanimated 4) · TanStack Query ·
Zustand · Flask + SQLAlchemy Core · SQLite (dev) / Postgres (prod) ·
Render free-tier web dyno (sleeps after ~15 min idle → 30–60 s cold start).
