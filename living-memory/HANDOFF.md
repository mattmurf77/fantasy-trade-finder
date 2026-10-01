# HANDOFF

## Current State — 2026-10-01 (value-core engine workstream)

**Where I stopped:** From-scratch trade engine ([D-195](DECISIONS.md)) built on `feat/value-core-engine`
(worktree `.claude/worktrees/value-core-engine`), pushed; **draft PR #308 for CI only**, flag `trade.value_core` off.
Since 09-30: deck variety rules (one card per trade idea, acquisitions in rounds, partner cap), logged legacy fallback,
default band ±20%. Full local suite 7528 passed / 1 skipped; flag-off output identical to `3bb981ed`.

**In flight:** CI on PR #308. Package worktrees `value-core-wp1..wp5` (branches `feat/value-core-wp1..5`) are merged into the
integration branch but NOT into `origin/main` — keep them until the branch lands, then sweep via the recovery ledger.

**Blocked on:** the real-league freeze — operator approved it, but production reads were denied by the session's permission
classifier after one lookup (league ids found; command in NEXT.md). Needs the operator to run it or allow prod reads.

**Don't repeat:** don't widen `vc_band` past 0.25 without new evidence (synthetic insults jump to 29% at 0.30); the e2e cap
invariant must include the partner cap; don't merge PR #308 before the bench + blind grades.

## Current State — 2026-09-23

**Where I stopped:** Owner authorized plan/build/deploy and all-user linked-team preparation, then explicitly approved the chunked storage/leases/deletion subsystem. Production remains2cff90c7/Bilateral2; cache0 verified02:03:21UTC. PR306 canary failed InvalidArtifact, causeUNKNOWN,0artifacts. [Status](../docs/plans/prepared-trade-inventory/status.md).

**In flight:** PR307 attached, isolated /private/tmp/fleeced-prepared-offers-20260922.uTMpm2, codex/prepared-artifact-validation-20260922. Prior570778f2 CI35811257235:7402pass1skip5fail874s, other3gatesgreen. Legacy projection seam repaired23pass; immediately-stale synthetic session reproduced401, fixture repair12pass. No auth weakening. R4 flag parity fixed19pass. FinalPG59pass; private cluster stopped. Full13728 parity703.75s, first30published2.502s/RSS1.434GB;936active-switch repeats1.175–3.282s. Not a reliable/device3sec pass.

**Blocked on:** No approval blocker. Final local/hosted retry, merge/exact Renderdeploy, freshcanary thenall-user sweep remain. V2 branch pushed, not merged/deployed. Freshdryrun02:43UTC:7resolvedtargets/6eligibleactors,18knownleagues, explicit provider/binding gaps; no all-team coverage claim.

**Don't repeat:** Preserve dirty canonical/legacy and unrelated evaluator414faade/b17cc379. No raw identity exports, fake production actions, model/offer caps. Ops /private/tmp/prepared-release-20260922.S7GrYs; freshsweepkeys. V2 rollback is flagoff; olderbinary needs private-table purge/deletionbridge. See release.md; source edits invalidate running model-hash benchmarks.
