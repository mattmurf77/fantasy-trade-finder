# Execution and reporting

The coordinator sets priorities and acceptance criteria for the three department
heads. Department heads turn them into assignments for their leads. Leads turn
those into worker briefs with exact files, resources and dependencies. Workers do
the querying, building and testing; every manager above them stays accountable for
judgment and synthesis.

## A feature, end to end

1. **Spec.** The area's product lead writes the scope block and PRD, folding in
   `ux-lead`'s and `design-lead`'s specs (same department, through `head-product`)
   and `models-lead`'s quality bars where they apply (from `head-bizops`).
   `head-product` accepts it once the required reviews are attached or waived.
2. **Handoff.** `head-product` sends the accepted PRD to `head-eng`, which updates
   the wave's file-ownership map (who gets which cross-area files and contract docs)
   and assigns the area's eng lead. Backend contract work lands before client
   workers start.
3. **Build.** The area's eng lead briefs workers and accepts their diffs against the
   PRD. `head-eng` accepts cross-area consistency: shared contracts agree, doc rows
   are filled, no file was touched by two workers.
4. **Review.** `head-eng` sends UI and flow diffs to `head-product` for
   `design-lead` and `ux-lead`, and model-behavior changes to `head-bizops` for
   `models-lead`'s sign-off.
5. **Ship.** `release-lead` runs the independent QA pass, confirms CI and the
   TEST_LEDGER entry, and brings the ship summary up the chain for the operator's
   go/no-go. Only then does it merge, deploy, or submit.

Strategy work (a model roadmap, a growth plan, a UX audit, a marketing plan)
follows the same shape without the build steps: the lead's deliverable goes to its
department head for acceptance. A model change runs through all three departments:
`models-lead` specs it (Business Ops), `models-eng` builds it (Eng), and the area
leads whose surfaces show it update their PRDs (Product).

## Worker brief

- **Task ID:** `<slug>-<role-key>-<n>`; manager; worker identity (agent id or
  `local_…` session)
- **Skill to load:** one implementing role skill, e.g. `/eng-backend`
- **Objective, deliverable, success criteria:**
- **Inputs:** PRD or scope-block path; the `origin/main` sha to build on; relevant
  D-/G- IDs (e.g. G-028 for backend tests)
- **Allowed actions; excluded actions:** excluded unless the brief cites an operator
  grant — push to `main`, EAS, prod writes, flag flips, outbound messages, new
  sessions, `Workflow`, schedules
- **Files owned:** exact paths, from the area's allocation and `head-eng`'s wave
  map. Shared docs: the named owner writes; everyone else puts proposed edits in
  their report — this overrides a role skill's own doc-sync step (e.g.
  `eng-backend` step 5) whenever another worker owns the doc
- **Worktree:** cut from freshly fetched `origin/main`; report the base sha.
  Worktrees have no `mobile/node_modules` (G-022)
- **Standards:** `docs/coding-guidelines.md`; for any UI, the Chalkline rules in
  `docs/design/design-system.md` + `components.md`
- **Evidence required (D-056):** which `check-*.js` suite or unit tests, a file:line
  code-walk proof, or a manual TestFlight checklist
- **Budget and stop rule:** an upper bound, not a quota (e.g. two fix attempts on a
  red test, then report). Commit partial work to the branch before stopping
- **Report:** path and format (below)

Never weaken acceptance criteria to fit a budget, and never fabricate a result.
Independent research and review can overlap; writes to the same files and dependent
tasks are serialized.

## Action boundaries

Routine, reversible work inside the brief proceeds without asking: commits on the
worker's own branch, local tests, drafting docs and deliverables. Anything on the
approval list in SKILL.md waits for the operator — the responsible lead prepares a
concrete, reviewable result first, it travels up the chain to the coordinator, the
coordinator brings it to the operator with the decision stated, and nobody re-asks
for consent already recorded.

If an action is refused (by the operator, a hook, CI, or a permission prompt),
record the real reason, keep the partial work, stop only that action, and carry on
with independent work. Reading a saved report when a send is unavailable is a
legitimate fallback; routing around a blocked action is not.

## Resource handoff

A transfer is an explicit acknowledgment naming: holder, exact scope (files, branch,
flag, doc, `main`), current sha or value, grant window or atomic stage, and how it
is released. Include coupled destinations — e.g. a `backend/analytics_taxonomy.py`
grant includes `analytics_queries.NON_INTENT_EVENTS`; a merge to `main` includes the
Render deploy it triggers. Cross-area files are granted by `head-eng`; area files by
the area's eng lead; engine files by `models-eng`.

If the holder retains the resource, others send it validated proposals and label
them unapplied. If granted, the worker re-checks the current sha or value, records
what it did, and releases only its own grant. Before retrying an uncertain
consequential action (a push, an EAS submit, a prod write), reconcile what actually
happened. A ledger entry is a record, not a lock.

## Worker report

- **Task / worker / manager; state; time observed:**
- **Done:** outputs with paths; branch + commit sha; base sha
- **What changed, why, and how it was verified:**
- **Results vs proposals;** coverage limits; contradictions with the brief or docs
- **Evidence:** test output, code-walk proof path, checklist path
- **Resources:** retained / released; pending writes or actions
- **Blockers vs dependency waits vs operator decisions:**
- **Proposed living-memory entries** (D-/G-/M-/Q-, TEST_LEDGER) — for the scribe to
  write, not the worker
- **Next safe action and its owner:**

Prepared, attempted, delivered and confirmed are four different states.

## What counts as done

| Domain | Done means |
|---|---|
| Code on a branch | Commit sha on the branch, its base sha, CI green there, D-056 evidence path |
| Shipped | Content verified on `origin/main` (squash merges — compare content, not ahead counts), Render deploy observed, CHANGELOG entry |
| TestFlight | EAS build number + marketing version; the manual checklist handed to the operator |
| Docs | Path + commit sha; the scope block's docs table filled row by row |
| Model change | Eval or backtest output against `models-lead`'s bars, plus its sign-off |
| Business deliverable | File under `docs/business/<dept>/` ending in **Decisions needed** + **Handoffs** |
| Data answer | Query text, source (local SQLite or prod Postgres), timestamp, row counts |
| Prod state change | The observed after-state (flag value, feedback status) — not the request that was sent |

## Acceptance up the chain

Each manager reads its reports against what it asked for and accepts, partially
accepts, or rejects them — then reports one level up. Resolve overlap by exact
identity (path, sha, feedback ID, event name), not by titles.

- **Lead → department head:** accepted / partial / rejected outputs,
  dependencies, resource state, reviews still owed.
- **Department head → coordinator:** department status across areas, cross-area
  conflicts, what needs another department, what needs the operator.
- **Coordinator → operator:** a few lines — what moved, what was accepted, what
  needs their decision, and what the evidence does not cover. No transcript dumps.

Prefer event-driven updates; recurring check-ins only if the operator asks.

Record states: planned · dispatched · running · awaiting dependency · awaiting
review · awaiting operator · under review · accepted · failed/stopped — each with a
time and next owner. A session being open or idle is not a task state.
