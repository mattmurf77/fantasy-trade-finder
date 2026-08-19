# Phases 3 & 4 — QA and the resolution loop

> **Rewritten 2026-08-18 per [D-056](../../../../living-memory/DECISIONS.md)**
> (2026-08-15, operator, Active): Maestro and the simulator are retired
> **entirely** — no flow authoring, no flow execution, no captures, in any
> pipeline. QA here is static + code-walk + an operator TestFlight checklist.

## Environment prep (orchestrator, once per batch)

No simulator, no Maestro, no JAVA_HOME. What QA agents need is a checked-out
merged branch that builds and a local Flask server for web-touching groups:

```bash
cd mobile && npm ci && npx tsc --noEmit    # NEVER symlink node_modules (2026-08-10 lesson)
for f in mobile/tests/check-*.js; do node "$f" || echo "FAIL $f"; done
python3 -m pytest backend/tests/
python run.py                              # port 5000, only for web-touching groups
```

Guard conventions and the authoring rules live in `mobile/tests/README.md`. If
`tsc` or an existing guard fails on the merged branch, that's a Phase 2 defect —
send it back before spawning QA.

## Phase 3 — QA (two agents, same tasks, independent)

Spawn **two QA agents in parallel with identical prompts**. Redundancy is the
point: a divergence between two independent reads of the same diff is signal —
one of them misread the code — never collapse this to one agent to save time.

Each QA agent prompt includes:

- The PRD path(s) — execute **every** test in the test plan, plus the full
  `mobile/tests/check-*.js` set and `pytest backend/tests/` (regression).
- How to run: `cd mobile && npx tsc --noEmit`, `node tests/check-<name>.js`,
  `python3 -m pytest backend/tests/<file>`. **Never** a simulator build, a
  Maestro run, or a capture (D-056).
- For every requirement no test can mechanically check: a **code-walk proof** —
  a file:line-cited trace through the merged diff showing the code path that
  produces the required behavior, including the conditions under which it does
  *not* fire. "I read it and it looks right" is not a proof; cite lines.
- Every new behavioral test must be **proven to fail on a deliberately
  sabotaged build** before it counts (apply sabotage → RED → revert → green),
  with the evidence in the report. A test that passes on the defect it names is
  the failure mode this rule exists for.
- Rules: report what you observe, not what should happen. A test you couldn't
  run is `BLOCKED` with the reason — never silently skipped. Do not fix
  anything, not even a guard; suspicions that a guard is wrong go in the report.
- Web-touching groups: also verify the PRD's web test section against the
  local Flask server (`python run.py`, port 5000).
- **TestFlight checklist:** each agent drafts the operator-facing runtime
  checklist for its group (numbered steps, exact screen, expected result). This
  is the batch's only runtime evidence — write it like a regression suite.
- Output: findings file (format below) at
  `docs/feedback/items/<id>-<slug>/qa-round-<R>-agent-<A|B>.md` (the group's
  lowest-ID item folder).

### Findings file format

```markdown
# QA round <R> — agent <A|B> — <date>
## Summary: PASS | FAIL (<n> findings)
## Environment: branch+commit, node/python versions, flags pinned
## Results
| Test | Verdict | Evidence |
|---|---|---|
| R-1 sticky header | PASS | `check-trades-banner-region.js` green; sabotage → RED |
| R-2 quick move | FAIL → F-1 | code-walk: `TradesScreen.tsx:214-231` |
| pytest backend/tests/test_routes.py | PASS | |
## Findings
### F-1: <one-line defect>
- Severity: blocker | major | minor
- Repro: exact steps (or the code path that makes it inevitable)
- Expected (PRD ref R-n) vs actual
- Evidence: file:line cite, failing test name, or log path
## TestFlight checklist (operator-run)
1. <screen> → <action> → expect <result>
```

### Orchestrator adjudication

Diff the two reports. Both agents saw it → confirmed. One agent only →
re-run the discriminating test or re-walk the cited lines yourself to break the
tie; also classify: app bug vs. wrong test vs. environment issue. Only **app
bugs and wrong tests** enter Phase 4; environment issues you fix and rerun.
Two code-walk proofs that disagree about what a code path does are always worth
resolving to the line — one agent misread, and which one matters.
Both agents PASS everything → skip Phase 4, go to Phase 5.

### Evidence record (on the batch's final fully-green round)

There is no simulator gate to satisfy: it was retired by D-056 and
`githooks/pre-push` is now a deliberate no-op (read its header). Do **not** write
`qa/sim-runs/last-sim-run.json` — nothing consumes it. `docs/runbook.md`
§ Pre-ship simulator gate is banner-marked historical; the live contract is
`docs/templates/feature-scope.md` §3 and §5.

What Phase 5 actually needs:

1. **CI green on the pushed sha** — `backend-tests`, `mobile-typecheck` (which
   globs and runs every `mobile/tests/check-*.js`), `maestro-testid-lint` (the
   job keeps its historical name; the lint outlived the flows).
2. **A `living-memory/TEST_LEDGER.md` entry** naming what ran and what it
   proved — guards executed, pytest scope, code-walk proofs written, sha.
3. **The consolidated operator TestFlight checklist** for the batch, filed in
   the lowest-ID item folder and repeated in the Phase 5 ship summary. Its
   outcome gets logged back to TEST_LEDGER once the operator runs it.

## Phase 4 — QA resolution (loop until clean)

1. Group confirmed findings by owning platform; spawn resolution agents with
   the same worktree/ownership rules as Phase 2. Each gets the findings file
   entries, the PRD, and the offending diff. Fixing a test is allowed **only**
   when the adjudication says the test was wrong, and the PRD gets a matching
   correction.
2. A finding that traces to PRD ambiguity or a missing requirement goes back
   through a **Phase 1 mini-round** (Planner + Author update the PRD; log it)
   before anyone writes code — otherwise the two platforms drift again.
3. After fixes merge: **full new QA round** — two fresh agents, entire test
   plan + the full guard set + pytest, round number incremented. Regressions
   hide behind fixed-only re-testing; never re-run just the failed cases.
4. Loop 3→4 until a round is fully green from both agents. If the same
   finding survives 3 rounds, stop and escalate to the operator with the
   history — looping in perpetuity is for convergence, not for banging heads.
5. Append lessons to the skill's `lessons.md` — weak guards, self-satisfying
   sabotage mappings, code-walk proofs that missed a branch. QA is where most
   reusable lessons come from.
