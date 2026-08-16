# Research Plan — Onboarding Strategies & Feature Presentment for Complex Apps

> **Date:** 2026-08-15
> **Scope:** Research only. No code, no scope blocks, no implementation. Output is markdown research files in this folder.
> **Why:** FTF is a feature-dense app (Sleeper sign-in, matchup-based Elo rankings, tiers, trade finder, trade calculator, boards, send-in-platform, notification inbox, feedback loop). New users need to understand the core loop fast, and discover the deeper features progressively — without a wall-of-features onboarding. Related in-flight doc: `docs/business/product/2026-08-14-open-access-onboarding.md`.

---

## Structure

Two research areas, two rounds.

**Area A — Onboarding strategies** (first-session experience: how complex apps get users to first value and teach the core loop)

**Area B — Feature presentment / progressive discovery** (post-onboarding: how apps surface the rest of their feature depth as users mature)

### Round 1 — 10 Opus subagents, 5 per area

Each agent gets a distinct research lens to minimize overlap. Each writes its own findings file to `round-1/` and returns a summary.

| # | File | Lens |
|---|---|---|
| A1 | `round-1/a1-onboarding-pattern-taxonomy.md` | Taxonomy of onboarding patterns (tours, checklists, wizards, empty states, templates, interactive walkthroughs) — when each works, completion/retention evidence, anti-patterns |
| A2 | `round-1/a2-time-to-value-activation.md` | Time-to-value & activation science — aha-moment identification, activation metric design, step minimization, deferred signup/personalization |
| A3 | `round-1/a3-complex-app-case-studies.md` | Case studies: how feature-dense consumer apps onboard (Notion, Figma, Duolingo, Superhuman, Slack, Discord, sports/fantasy apps) |
| A4 | `round-1/a4-personalized-segmented-onboarding.md` | Personalized/segmented onboarding — intent surveys, adaptive paths, role-based flows, experimentation on onboarding |
| A5 | `round-1/a5-mobile-onboarding-constraints.md` | Mobile-specific onboarding — iOS conventions, permission priming (push/ATT), sign-in friction, App Store constraints, React Native/consumer sports app specifics |
| B1 | `round-1/b1-progressive-disclosure-theory.md` | Progressive disclosure theory & research — cognitive load, discoverability literature, Nielsen/NNG and academic findings, layered UI design |
| B2 | `round-1/b2-contextual-inapp-patterns.md` | Contextual in-app patterns — tooltips, hotspots, spotlights, badges, what's-new/changelogs, empty states as teachers; effectiveness evidence and annoyance thresholds |
| B3 | `round-1/b3-discovery-loops-lifecycle.md` | Feature-discovery loops beyond the UI — triggered nudges, lifecycle push/email, notification-driven discovery, streaks/gamification for depth adoption |
| B4 | `round-1/b4-depth-mastery-case-studies.md` | Case studies of mastery curves — how games tutorialize, how pro tools (Figma, Excel, Photoshop, Linear, Superhuman) reveal depth over time |
| B5 | `round-1/b5-measurement-and-tooling.md` | Measuring feature adoption — metrics (breadth/depth/frequency), instrumentation patterns, build-vs-buy (Pendo/Appcues-class tools), experiment design for discovery features |

### Consolidation

After round 1 completes:
- `CONSOLIDATED-A-onboarding.md` — synthesis of A1–A5
- `CONSOLIDATED-B-feature-presentment.md` — synthesis of B1–B5

Each consolidation names the highest-leverage themes and flags the 2–3 areas that most deserve deeper research given FTF's shape.

### Round 2 — 2 Opus subagents per drill-down area

Areas chosen from consolidated findings (not predetermined). Expected 2–3 areas → 4–6 agents. Files go to `round-2/`. Final output: `SYNTHESIS.md` tying both rounds together.

## Agent ground rules

- Deep web research with sources cited (URLs) for every substantive claim; prefer primary sources, published experiments, and practitioner post-mortems over listicles.
- Distinguish evidence-backed findings from received wisdom.
- Each file ends with an "Implications for FTF" section — hypotheses only, no implementation prescriptions.
- Research only; no code changes anywhere in the repo.
