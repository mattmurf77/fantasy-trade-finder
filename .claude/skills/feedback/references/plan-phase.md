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
| All | `reconciliation-log.md` | Each review round: objections raised, resolution, anything orchestrator-arbitrated. |

### PRD test plan requirements

- Concrete Maestro flows: new/updated YAML under `mobile/.maestro/`, following
  the existing numbered-file convention and `mobile/.maestro/README.md` setup.
- Selectors: prefer `testID` (have the build agent add them — see the testID
  registry in `docs/plans/mobile-testing/lld.md`); text matchers only as
  fallback, and note the exact copy they depend on.
- Per requirement R-n: at least one pass criterion QA can verify mechanically
  (screenshot checkpoint, visible text, absence of crash).
- Web-touching groups: a web test section (URLs, user actions, expected DOM
  text) since Maestro only covers the app.

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
