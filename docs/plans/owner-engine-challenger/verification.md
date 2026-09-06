# Verification and release status

Current status: **backend live; shadow-only generation enabled; serving off**.
See the [release record](release.md) for current source, configuration and mobile
build state. The checkpoints below retain their original scope and timing.
Source baseline: `4c343a488644299901655bd932f67f52355f42bd`.
Isolated branch: `codex/owner-engine-challenger-20260906`.
No production database, user session, live preference or release switch was
changed during these implementation checks.

## Completed checkpoints

- Parent construction/independent acceptance/runner check: **74 passed in
  0.84 s**. Tests change actual candidate identity when personal rankings or
  outlook changes; unchanged exact packages retain their market pricing.
- Parent control/registry/profile check: **102 passed in 2.84 s**. Historical
  golden payloads and profiles remain unchanged; only new-key/arm inventories
  were expanded.
- Core batch-validation repair: **65 passed in 2.27 s**, including independent
  acceptance cases. Three new batch tests first failed against the pre-batch
  runtime, then passed; they verify one search context and equivalent evidence
  for valid, mutated, repeated and partial-selection occurrences.
- Parent web gate: **190/190 passed**. Parent mobile checkpoint: **all 97
  structural guard scripts and testID lint passed**; TypeScript passed before
  the final canvas-attribution addition. Final mobile rerun remains required.
- Parent broad backend checkpoint: **5,734 passed, 1 skipped, 9 failed in
  644.46 s**. Not a green final result. Eight source-inspection failures read
  incorrect function slices after the server file was edited during the run;
  these require a fresh frozen-source rerun, not weakened assertions. One
  legitimate pick-reader inventory guard requires sanctioning the new selected
  final-roster reader with its explicit source contract. Existing receipt-test
  background workers also logged missing-table diagnostics against scratch
  SQLite; these are not production diagnostics.

All Python runs use the isolated `/private/tmp/ftf-context-venv/bin/python`
3.12 runtime and scratch SQLite under the task worktree. No secret environment
or production URL is loaded. Mobile Node is 24.14.1; hosted CI's Node 20 remains
an independent gate. Mobile dependency lock matches fetched main and is unchanged.

## Final local validation

Final parent focused rerun on frozen backend: **235 passed in 11.25 s**,
including all nine previously failing tests, owner core/independent acceptance,
routes, pick ownership and disposition suites. No source-inspection assertion
was weakened. The route builder's final independent matrix is **369 passed in
11.02 s** (31 new route cases). Parent has read and approved the final runtime
diffs and the independent final mobile re-review is green.

Final mobile parent rerun: **TypeScript, all 97 guard scripts, and testID lint
passed**, including the completed edited-action repair. The new offer-signal
guard has **26** executable/structural checks and trial-order guard has **13**
executable checks. Independent review reproduced the edited classic-deck action
retaining the original impression, then independently verified its repair with
actual production functions and a real exposure clock. Edited terms/IDs remain
intact; original and legacy behavior is retained. No simulator or physical
device run occurred. Version 1.17.2 is prepared in app/native configuration;
both native plist/project syntax checks passed. No build/upload is implied.

**Full frozen backend: 5,754 passed, 1 skipped in 420.01 s**, exit 0. Command:

```sh
DATABASE_URL=sqlite:////private/tmp/ftf-owner-engine-5REUls/data/owner-final-regression.db \
PYTHONDONTWRITEBYTECODE=1 /private/tmp/ftf-context-venv/bin/python -m pytest \
backend/tests -q -p no:cacheprovider --tb=short
```

No backend source was edited during this final run. The earlier nine failures
are resolved; the known isolated receipt-worker diagnostics recur without test
failures. This is a local regression result, not hosted CI or production health.

## Release gate checkpoints and completion

Published checkpoint `13b941614a426d7a06a1dd2a737c9436a845cb09` passed all four
[hosted CI jobs](https://github.com/mattmurf77/fantasy-trade-finder/actions/runs/34058864206)
(backend **5,754 passed / 1 skipped in708.27s**). It is **not** the final release
head: the last rollout review found an in-flight owner-serving hot-flip race
and a related cached-signature mismatch. Eight new runner cases reproduced
the draft race RED, then passed after capturing permission before generators;
a real worker route regression also reproduced missing forwarding RED. The
repaired source requires fresh full validation and exact-head CI before merge.

Final rollout repair is independently reviewed GREEN: runner21 checks,
builder192 focused checks in6.55s and reviewer120 in2.80s. Worker forwarding,
shadow-cache drift and demo-cache compatibility each have RED/GREEN evidence;
the independent original hot-flip harness now rejects the stale shadow cache.
Parent reviewed the final diff and started a fresh frozen full backend/mobile
rerun; web190 passes. Runtime is frozen during those runs.

The prior clean archive is likewise superseded by this repair. Its independent
privacy/identity result was 2,673 files, 635/635 mobile files byte-identical,
one retained commit and no scratch DBs/credentials/dependency copies. Production
GET-only preflight20:46:20UTC found207flags/259existingsettings, all three
measurement prerequisites enabled, existing controls unchanged and no new owner
keys. No production mutation occurred.

1. Recorded published source revision and green exact-head hosted CI before
   any merge/deployment.
2. Separately verified backend deployment/config and new TestFlight build if
   released; actual Apple availability and device steps are not implied.

Final repaired source passed local **5,765/1skip in400.05s** and all four
[exact-head hosted CI jobs](https://github.com/mattmurf77/fantasy-trade-finder/actions/runs/34059989947),
backend **5,765/1skip in655.89s**. Final mobile TypeScript/all97 guards/testID
and web190 passed. Merged-tree equality and backend deployment are verified;
mobile delivery and serving are tracked separately in the release record.
Exact 1.17.2 (150) build and submission are FINISHED; Apple availability and
intended tester installation remain unverified. All 12 manual checks are UNRUN.

The new switches remain default-off in source; production include is now1 and
serve remains0. Prior releases and the older personal-market policy are not
evidence that the new constructor is being served.
Readout: [trial protocol](trial-protocol.md). Device supplement:
[12 unexecuted checks](manual-testflight.md). Review map: [code walk](code-walk.md).
