---
name: feedback
description: >
  Fetch open in-app feedback for Fantasy Trade Finder and run selected items
  through the full delivery pipeline: triage table → operator selection →
  dual-agent planning (HLD/LLD deltas + PRD with Maestro test plan) → parallel
  build agents (backend/mobile/web) → redundant Maestro QA → QA-resolution
  loop → ship to GitHub/Render/TestFlight. Use whenever the user says
  /feedback, "check the feedback", "any new feedback?", "work the feedback
  backlog", "address feedback #N", or wants tester bug reports / polish
  requests / feature ideas turned into shipped code. Also use for a single
  named feedback item, not just batches.
---

# Feedback pipeline — fetch, triage, plan, build, QA, ship

Turns open in-app feedback (TestFlight testers → `POST /api/feedback` → prod DB)
into shipped fixes/features through a phased, subagent-driven pipeline. You are
the **orchestrator**: you never write feature code yourself — you fetch, group,
spawn agents, review their work, gate phase transitions, and ship.

## Before anything: load lessons

Read `lessons.md` in this skill directory. It is the pipeline's memory — every
prior run appends what broke and what worked. Apply relevant lessons to this
run. **At the end of every phase**, append any new lesson (dated, one per
bullet, phase-tagged). If a lesson invalidates skill instructions, update this
skill's files too — the skill is expected to improve itself each run.

## Phase 0 — Fetch & triage

1. Fetch open feedback (paginates prod admin API, needs `CRON_SECRET` in
   `secrets.local.env`; blank secret → ask the operator to fill it in that
   file; a 401 means it doesn't match Render's env var):
   ```bash
   python3 .claude/skills/feedback/scripts/fetch_feedback.py list
   ```
2. Read the **full untruncated text** before classifying anything:
   `... list --json`. The table clips at ~110 chars and the actionable spec
   is often in the tail (exact tier lists, repro steps).
3. Check for duplicates: `... list --all` shows closed items too, and prior
   work is recorded in `docs/feedback/items/` and (historically)
   `docs/plans/feedback-batch-*/plan.md`. A dup of *shipped* work → propose
   `declined` (or "verify on current build, then `fixed`"). A dup of an
   *open* item → fold into the canonical item's group; both get status
   updates together from here on.
4. Present **one triage table**: the fetched columns plus **work type**
   (bug / polish / feature — start from `severity`, re-classify from the
   full text), **platforms** (mobile / web / backend), and **group**. Group
   items sharing a subsystem and comparable scope — a one-line cosmetic fix
   doesn't join a schema-change group just because it's on the same screen;
   split it out and note the shared-file ownership so Phase 2 serializes or
   single-owns those files. Below the table add: proposed groups with
   one-line rationale, items you propose *not* to build (`idea`-type product
   questions get a "discuss / park / decline" recommendation, not a build
   group), and any status anomalies (items already `in_progress` with no
   work folder — treat stored status as advisory, flag it, re-present it).
5. **Stop and wait** for the user to say which items to address. Do not
   proceed on your own — selection is the operator's call.
6. On selection: mark each chosen item `planned`
   (`fetch_feedback.py set <id> planned`), then create one work folder per
   item at `docs/feedback/items/<id>-<slug>/` (convention in the README
   there). The batch-level `plan.md` skeleton listing groups, owners, and
   paths goes in the **lowest selected item's** folder — mirror the format of
   `docs/plans/feedback-batch-4/plan.md` (historical format reference) — and
   every other item's `status.md` links to it. Scratch/temp work goes in
   gitignored `feedback-workspace/<id>/`, never in docs. Then append Phase 0
   lessons before entering Phase 1.

## Work-type paths

Not every item earns the full ceremony. Pick per **group** — a group takes
the heaviest path of its items, which is exactly why triage keeps light items
out of heavy groups:

| Path | When | Phase 1 output | Phase 2 | Phase 3 QA |
|---|---|---|---|---|
| **Fast-track bug** | Crash/wrong-behavior fix, no schema/API change, ≤2 files expected | Mini-PRD only (repro, root cause hypothesis, fix approach, Maestro regression flow) | 1 agent | 2 QA agents, repro flow + smoke |
| **Polish** | UX/copy/layout on existing feature | PRD only; HLD/LLD deltas only if data flow changes | 1 agent per platform | 2 QA agents, feature flows + smoke |
| **Feature** | New capability, new endpoint, or schema change | Full: HLD delta + LLD delta + PRD | backend → then mobile+web in parallel | 2 QA agents, full test plan |

If unsure, escalate to the heavier path — the cost of a thin PRD is two build
agents implementing different endpoint contracts.

## Phases 1–5 (read the reference for the phase you're entering)

Each group runs Phases 1–4 independently and in parallel where possible;
Phase 5 ships the batch as a whole. Read each reference **when you reach that
phase**, not all upfront:

- **Phase 1 — Plan** → `references/plan-phase.md`
  Two peer agents per group: Planner drafts the plan; Author turns it into
  HLD/LLD deltas + PRD (with Maestro test plan); Planner critiques; Author
  incorporates; loop max 3 rounds, orchestrator arbitrates leftovers. PRD must
  pin the exact API contracts both build agents will code against.
- **Phase 2 — Build** → `references/build-phase.md`
  Set items `in_progress`. One agent per platform in isolated worktrees with
  disjoint file ownership; backend agent (if any) finishes before client
  agents start. Orchestrator reviews all diffs for cross-platform consistency
  before merging to the group branch.
- **Phase 3 — QA** → `references/qa-phase.md`
  Two independent QA agents run the same PRD test plan via Maestro on the iOS
  simulator + smoke suite; findings land as structured `.md` files in the
  group's item folder under `docs/feedback/items/`. Web changes get a web QA
  pass too.
- **Phase 4 — QA resolution (loop)** → also in `references/qa-phase.md`
  Only if confirmed findings exist: resolution agents fix, then a **full new
  QA round** (not just the failed cases). Loop until both QA agents pass
  everything. If a finding traces to a PRD gap, route back through a Phase 1
  mini-round first.
- **Phase 5 — Ship** → `references/ship-phase.md`
  Orchestrator final pass (diff review, `tsc`, pytest, docs-sync per
  CLAUDE.md's table), then **explicit operator go/no-go with a ship summary**,
  then: merge → push (Render auto-deploys) → EAS build + submit (TestFlight)
  → set items `fixed` → update item folders + lessons.

## Hard rules

- **Two user gates, never skipped:** item selection (Phase 0) and ship
  go/no-go (Phase 5). Everything between runs autonomously.
- **The PRD is the contract.** Build agents receive the PRD path, not the
  feedback text. If a build agent asks a question the PRD can't answer, that's
  a Phase 1 defect — fix the PRD, then resume.
- **Coding guidelines apply to everyone** — every agent prompt points at
  `docs/coding-guidelines.md` and (for UI) the Chalkline rules in
  `docs/design/design-system.md` + `docs/design/components.md`.
- **Never commit secrets**; `secrets.local.env` stays local. Status updates
  hit prod — only the transitions listed here (`planned`, `in_progress`,
  `fixed`, `declined` for dupes). `shipped` is flipped later, once testers
  actually have the build, not by this pipeline.
- Keep `docs/feedback/items/<id>-<slug>/` current as phases complete — it is
  the audit trail the next run's agents will read. (Batches before item #64
  live in `docs/plans/feedback-batch-2..4/`; leave them as history.)
