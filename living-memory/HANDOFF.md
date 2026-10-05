# HANDOFF

## Current State — 2026-10-02 (Calibration / blind grading — stopped on usage limit)

**Operator instruction:** "push live once done" — merge value-core (PR #308, flag off) then Calibration to main, turn
`grading.blind` on for testers via the `calibration_rollout` overlay (prod write; runbook § Gate 2), EAS → TestFlight.
`draft.tab` → false ships for everyone with the merge (operator-approved; Draft Room stays under League).

**Where I stopped:** specs + lead change (background session build, §3.3) committed on `feat/blind-grading`
(`.claude/worktrees/blind-grading`). Fable 5.1 builders: **P3 mobile DONE** (`feat/blind-grading-p3` 73a384d7, tsc/testid-lint/
100 guards green, lead-reviewed OK); **P4 docs DONE** (`feat/blind-grading-p4` ef0a7f98); **P1 service and P2 routes were
still running** their own full-suite checks — read their branches `feat/blind-grading-p1` / `-p2` (worktrees
`../blind-grading-p1`/`-p2`), review, then merge P1→P2→P3→P4 into `feat/blind-grading`, run specs §6 checklist.
`origin/main` has NOT moved since 3bb981ed (no conflicts expected).

**Also owed:** re-freeze the bench leagues after P1's `_freeze_league` picks fix (Oct-1 real-league numbers excluded
picks) and re-run the value-core bench; record TEST_LEDGER/CHANGELOG on ship; sweep worktrees via the recovery ledger.

## Current State — 2026-10-01 (value-core engine workstream)

**Where I stopped:** From-scratch trade engine ([D-196](DECISIONS.md)) built on `feat/value-core-engine`
(worktree `.claude/worktrees/value-core-engine`), pushed; **draft PR #308 for CI only**, flag `trade.value_core` off.
Since 09-30: deck variety rules (one card per trade idea, acquisitions in rounds, partner cap), logged legacy fallback,
default band ±20%. Full local suite 7528 passed / 1 skipped; flag-off output identical to `3bb981ed`.

**In flight:** CI on PR #308. Package worktrees `value-core-wp1..wp5` (branches `feat/value-core-wp1..5`) are merged into the
integration branch but NOT into `origin/main` — keep them until the branch lands, then sweep via the recovery ledger.

**Blocked on:** nothing technical. Next is the operator's blind grading (NEXT.md). Since 10-01: asymmetric band
(pay 20% / take 10%), throw-in rule, real-league bench run (TEST_LEDGER 2026-10-01/02).

**Don't repeat:** don't make the band symmetric at ±20% (real-league insults 5.6%); don't trust synthetic insult numbers
over the frozen real leagues; throw-ins must keep the evidence rule (unpriced/unranked players flood decks); the e2e cap
invariant must include the partner cap; don't merge PR #308 before the bench + blind grades.

## Current State — 2026-09-23

**Where I stopped:** Owner authorized plan/build/deploy and all-user linked-team preparation, then explicitly approved the chunked storage/leases/deletion subsystem. Production remains2cff90c7/Bilateral2; cache0 verified02:03:21UTC. PR306 canary failed InvalidArtifact, causeUNKNOWN,0artifacts. [Status](../docs/plans/prepared-trade-inventory/status.md).

**In flight:** PR307 attached, isolated /private/tmp/fleeced-prepared-offers-20260922.uTMpm2, codex/prepared-artifact-validation-20260922. Prior570778f2 CI35811257235:7402pass1skip5fail874s, other3gatesgreen. Legacy projection seam repaired23pass; immediately-stale synthetic session reproduced401, fixture repair12pass. No auth weakening. R4 flag parity fixed19pass. FinalPG59pass; private cluster stopped. Full13728 parity703.75s, first30published2.502s/RSS1.434GB;936active-switch repeats1.175–3.282s. Not a reliable/device3sec pass.

**Blocked on:** No approval blocker. Final local/hosted retry, merge/exact Renderdeploy, freshcanary thenall-user sweep remain. V2 branch pushed, not merged/deployed. Freshdryrun02:43UTC:7resolvedtargets/6eligibleactors,18knownleagues, explicit provider/binding gaps; no all-team coverage claim.

**Don't repeat:** Preserve dirty canonical/legacy and unrelated evaluator414faade/b17cc379. No raw identity exports, fake production actions, model/offer caps. Ops /private/tmp/prepared-release-20260922.S7GrYs; freshsweepkeys. V2 rollback is flagoff; olderbinary needs private-table purge/deletionbridge. See release.md; source edits invalidate running model-hash benchmarks.
