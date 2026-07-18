# Phases 3 & 4 — QA and the resolution loop

## Environment prep (orchestrator, once per batch)

Maestro needs a booted iOS simulator with the merged build installed:

```bash
export JAVA_HOME=/opt/homebrew/opt/openjdk/libexec/openjdk.jdk/Contents/Home
export PATH=$JAVA_HOME/bin:$PATH
cd mobile && LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8 npx expo run:ios   # build + install merged branch
```

Full setup details: `mobile/.maestro/README.md`. The testing-system design
(fixtures, reset scopes, testID registry) lives in `docs/plans/mobile-testing/`
— consult it when a flow needs seeded state. If the simulator build fails,
that's a Phase 2 defect — send it back before spawning QA.

## Phase 3 — QA (two agents, same tasks, independent)

Spawn **two QA agents in parallel with identical prompts**. Redundancy is the
point: a flake one agent hits and the other doesn't is signal about test
brittleness, not noise — never collapse this to one agent to save time.

Each QA agent prompt includes:

- The PRD path(s) — run **every** test in the test plan, plus the standing
  smoke suite `mobile/.maestro/01…06` (regression).
- How to run: `cd mobile && maestro test .maestro/<flow>.yaml` (JAVA_HOME as
  above); screenshots land in `mobile/.maestro/screenshots/`.
- Rules: report what you observe, not what should happen. A test you couldn't
  run is `BLOCKED` with the reason — never silently skipped. Do not fix
  anything, not even the test YAML; brittle-selector suspicions go in the
  report.
- Web-touching groups: also verify the PRD's web test section against the
  local Flask server (`python run.py`, port 5000).
- Output: findings file (format below) at
  `docs/feedback/items/<id>-<slug>/qa-round-<R>-agent-<A|B>.md` (the group's
  lowest-ID item folder).

### Findings file format

```markdown
# QA round <R> — agent <A|B> — <date>
## Summary: PASS | FAIL (<n> findings)
## Environment: sim device/OS, app version, branch+commit, maestro version
## Results
| Test | Verdict | Evidence |
|---|---|---|
| R-1 sticky header | PASS | screenshot path |
| R-2 quick move | FAIL → F-1 | ... |
| smoke 01-launch | PASS | |
## Findings
### F-1: <one-line defect>
- Severity: blocker | major | minor
- Repro: exact steps
- Expected (PRD ref R-n) vs actual
- Evidence: screenshot/log path
```

### Orchestrator adjudication

Diff the two reports. Both agents saw it → confirmed. One agent only →
reproduce the discriminating test yourself (or rerun it) to break the tie;
also classify: app bug vs. brittle test vs. environment issue. Only **app
bugs and wrong tests** enter Phase 4; environment issues you fix and rerun.
Both agents PASS everything → skip Phase 4, go to Phase 5.

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
   plan + smoke, round number incremented. Regressions hide behind
   fixed-only re-testing; never re-run just the failed cases.
4. Loop 3→4 until a round is fully green from both agents. If the same
   finding survives 3 rounds, stop and escalate to the operator with the
   history — looping in perpetuity is for convergence, not for banging heads.
5. Append flaky-selector / environment lessons to the skill's `lessons.md` —
   QA is where most reusable lessons come from.
