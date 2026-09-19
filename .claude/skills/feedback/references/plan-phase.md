# Phase 1 — Plan (dual-agent doc loop, per group)

Goal: a PRD (plus HLD/LLD deltas on the Feature path) precise enough that two
build agents working blind on different platforms produce compatible code.
The doc suite in `docs/plans/mobile-testing/` is the quality bar and format
precedent (it came out of the same dual-agent process).

## Outputs (in `docs/feedback/items/<id>-<slug>/`, the group's lowest feedback ID; other items in the group get a `status.md` linking here)

| Path | File | Contents |
|---|---|---|
| Feature | `hld-delta.md` | What changes in the architecture: components touched, data flow, decisions + alternatives rejected. Written as a **delta against `docs/architecture.md`**, not a rewrite. |
| Feature | `lld-delta.md` | Exact interfaces: endpoint signatures (method, path, request/response JSON with field types and error shapes), DB schema changes, client state changes, function-level touch points with file paths. |
| All | `prd.md` | Requirements (numbered R-1…), success criteria, out-of-scope, guardrails, **and the test plan** (below). |
| All | `scope.md` | Copy of `docs/templates/feature-scope.md`, filled: analytics events (specced / covered / **written** waiver — silence is not a waiver), schema+flags, the §3 evidence scope (structural `mobile/tests/check-*.js` guards, unit tests, code-walk proof, TestFlight checklist — **not** a Maestro delta, retired by D-056), the row-by-row docs table (api-reference / LLD / architecture / HLD / invariants / glossary / ADR), and the §5 ship-gate declaration (CI green + TEST_LEDGER entry — there is no sim-gate tier). Waivers surface to the operator before build. Per CLAUDE.md §Conventions "Feature gates". |
| All | `reconciliation-log.md` | Each review round: objections raised, resolution, anything orchestrator-arbitrated. |

### PRD test plan requirements

**(Rewritten 2026-08-16 per D-056 — Maestro/simulator retired entirely. No
flow authoring, no sim runs, in any pipeline.)**

- Automated evidence: unit tests (pytest / mobile test runner) plus structural
  `mobile/tests/check-*.js` AST suites for UI wiring. Every new behavioral
  test must be **proven to fail on a deliberately sabotaged build** before it
  counts (2026-08-10 lesson); distributional bars must be two-sided.
- Behavior that would previously have earned a sim capture gets a **written
  code-walk proof**: a file:line-cited commit-sequence trace.
- Runtime proof: a **concrete manual TestFlight checklist for the operator**,
  per group — specific enough to catch the regression it guards (screen,
  steps, expected result). This is the only runtime net; write it like a
  regression suite, because it is.
- Per requirement R-n: at least one pass criterion QA can verify mechanically
  (test name, check-suite assertion, or TestFlight checklist step).
- Web-touching groups: a web test section (URLs, user actions, expected DOM
  text).
- **UI-touching items name their captures.** List the affected
  `screens/mobile/<screen>/` captures as explicit PRD inputs — they are the exact
  ground truth for "current". Every mockup round starts from them, never from
  memory or from reading source alone (`screens/CLAUDE.md`, `mockups/CLAUDE.md`).
  If `mobile/scripts/screen-freshness.sh` flags one stale, request the re-capture
  before the design round, not after. The scope block's **capture delta** row (§3)
  then names which screens get re-captured at ship.

## The loop

1. **Planner agent** (subagent 1): give it the feedback items' full text
   (`--json` output), group scope, work-type path, and pointers to
   `docs/architecture.md`, `docs/api-reference.md`, `docs/coding-guidelines.md`,
   relevant screens. It returns `plan.md` for the group: problem statement,
   approach, platforms touched, risks, file-ownership proposal, spike needs.
2. **Author agent** (subagent 2): receives Planner's plan + the same pointers.
   Writes the HLD/LLD deltas (Feature path) and the PRD. Instruct it to
   *verify claims against the code* (endpoints it cites must exist or be
   explicitly marked NEW).
3. **Planner reviews** the Author's docs: hunt for contract ambiguity (could
   two engineers read this differently?), missing error cases, test-plan gaps,
   violations of repo invariants (`docs/cross-client-invariants.md`).
   Objections must be concrete and blocking-or-not labeled.
4. **Author incorporates** what it agrees with; rebuts what it doesn't, with
   reasons. Log every objection + outcome in `reconciliation-log.md`.
5. Still-blocking disagreements → one more round (max 3 total). After that,
   **you arbitrate**: read both positions, decide, record the decision and
   rationale in the log.

Run each round's two agents sequentially (they consume each other's output),
but run **different groups' loops in parallel**.

## Orchestrator exit checklist (per group)

- [ ] Every endpoint in the PRD has a full request/response contract in the
      LLD delta (or PRD itself on lighter paths).
- [ ] Every feedback item in the group maps to ≥1 requirement; every
      requirement maps to ≥1 test.
- [ ] File-ownership table exists and is disjoint across the batch's groups
      (needed for parallel worktrees in Phase 2).
- [ ] Reconciliation log shows zero unresolved blocking objections.
- [ ] Fast-track bugs: mini-PRD names the suspected root cause *file:line*
      or explicitly says investigation is part of the build task.
