# HANDOFF

## Current State — 2026-09-30 (value-core engine workstream)

**Where I stopped:** From-scratch trade engine ([D-195](DECISIONS.md)) built and integrated on `feat/value-core-engine`
(worktree `.claude/worktrees/value-core-engine`), not pushed, flag `trade.value_core` off. Full local suite green
(TEST_LEDGER 2026-09-30); flag-off output identical to `3bb981ed`.

**In flight:** package worktrees `value-core-wp1..wp5` (branches `feat/value-core-wp1..5`) are merged into the
integration branch but NOT into `origin/main` — keep them until the branch lands, then sweep via the recovery ledger.

**Blocked on:** operator — push/CI approval, PRD Q1–Q6, the per-asset guardrail definition, the fairness-band question
raised by the recall baseline, and running `freeze` on the five bench leagues (prod read).

**Don't repeat:** don't change `vc_band` without the operator; don't count the e2e "≤3 appearances" as achievable —
see the cap-feasibility note in `backend/tests/test_value_core_e2e.py`.

## Current State — 2026-09-23

**Where I stopped:** Owner authorized plan/build/deploy and all-user linked-team preparation, then explicitly approved the chunked storage/leases/deletion subsystem. Production remains2cff90c7/Bilateral2; cache0 verified02:03:21UTC. PR306 canary failed InvalidArtifact, causeUNKNOWN,0artifacts. [Status](../docs/plans/prepared-trade-inventory/status.md).

**In flight:** PR307 attached, isolated /private/tmp/fleeced-prepared-offers-20260922.uTMpm2, codex/prepared-artifact-validation-20260922. Prior570778f2 CI35811257235:7402pass1skip5fail874s, other3gatesgreen. Legacy projection seam repaired23pass; immediately-stale synthetic session reproduced401, fixture repair12pass. No auth weakening. R4 flag parity fixed19pass. FinalPG59pass; private cluster stopped. Full13728 parity703.75s, first30published2.502s/RSS1.434GB;936active-switch repeats1.175–3.282s. Not a reliable/device3sec pass.

**Blocked on:** No approval blocker. Final local/hosted retry, merge/exact Renderdeploy, freshcanary thenall-user sweep remain. V2 branch pushed, not merged/deployed. Freshdryrun02:43UTC:7resolvedtargets/6eligibleactors,18knownleagues, explicit provider/binding gaps; no all-team coverage claim.

**Don't repeat:** Preserve dirty canonical/legacy and unrelated evaluator414faade/b17cc379. No raw identity exports, fake production actions, model/offer caps. Ops /private/tmp/prepared-release-20260922.S7GrYs; freshsweepkeys. V2 rollback is flagoff; olderbinary needs private-table purge/deletionbridge. See release.md; source edits invalidate running model-hash benchmarks.
