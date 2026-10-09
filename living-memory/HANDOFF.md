# HANDOFF

## Current State — 2026-10-07 (Calibration + value-core shipped to the backend; app build blocked)

**Where I stopped:** PR #312 merged (`295cd951`) and deployed (`dep-db38m460tbcc7380tufg`, API-triggered — Render
auto-deploy is off). Calibration is live server-side for every app user; 7 decks pre-generated. `trade.value_core`
stays off.

**Blocked on (operator):** the iOS distribution certificate is revoked/expired, so EAS build 1.18.0 (158) failed.
Renew it with `cd mobile && eas credentials` (iOS → production → Distribution Certificate; needs an Apple sign-in),
then rerun `eas build --platform ios --profile production --auto-submit`. Until then no phone shows the tab.

**Also:** the local clone in the iCloud-synced Documents folder is corrupted (G-074) — work from a fresh clone
outside iCloud. Package/ship worktrees from the old path are gone with the move; branches `feat/value-core-*`,
`feat/blind-grading*` are merged by content into `295cd951` and can be ledgered and deleted on origin.

**Don't repeat:** don't assume a merge deploys (auto-deploy is off); don't rely on time-relative test dates.

## Current State — 2026-09-23

**Where I stopped:** Owner authorized plan/build/deploy and all-user linked-team preparation, then explicitly approved the chunked storage/leases/deletion subsystem. Production remains2cff90c7/Bilateral2; cache0 verified02:03:21UTC. PR306 canary failed InvalidArtifact, causeUNKNOWN,0artifacts. [Status](../docs/plans/prepared-trade-inventory/status.md).

**In flight:** PR307 attached, isolated /private/tmp/fleeced-prepared-offers-20260922.uTMpm2, codex/prepared-artifact-validation-20260922. Prior570778f2 CI35811257235:7402pass1skip5fail874s, other3gatesgreen. Legacy projection seam repaired23pass; immediately-stale synthetic session reproduced401, fixture repair12pass. No auth weakening. R4 flag parity fixed19pass. FinalPG59pass; private cluster stopped. Full13728 parity703.75s, first30published2.502s/RSS1.434GB;936active-switch repeats1.175–3.282s. Not a reliable/device3sec pass.

**Blocked on:** No approval blocker. Final local/hosted retry, merge/exact Renderdeploy, freshcanary thenall-user sweep remain. V2 branch pushed, not merged/deployed. Freshdryrun02:43UTC:7resolvedtargets/6eligibleactors,18knownleagues, explicit provider/binding gaps; no all-team coverage claim.

**Don't repeat:** Preserve dirty canonical/legacy and unrelated evaluator414faade/b17cc379. No raw identity exports, fake production actions, model/offer caps. Ops /private/tmp/prepared-release-20260922.S7GrYs; freshsweepkeys. V2 rollback is flagoff; olderbinary needs private-table purge/deletionbridge. See release.md; source edits invalidate running model-hash benchmarks.

## Home tab — shipped 2026-10-08

**Where I stopped:** Home tab merged to `main` as `dd08c7c2` (PR #309, D-198); Render redeploys; iOS 1.19.0 EAS build started with `--auto-submit`. See [CHANGELOG](CHANGELOG.md) 2026-10-08 for build numbers and deploy evidence.

**Next (operator):** run the 8-step TestFlight checklist in [scope.md](../docs/plans/home-tab/scope.md) §3 on 1.19.0 — the six-tab bar (Calibration is the longest label) is the one thing only a phone can prove. Two cold launches may be needed before the Home tab appears (flags are cached; tabs are fixed at mount).

**Watch:** "returning user" = first swipe done on this install, so a never-swiped or reinstalled user still lands on Trades; `app/home` is silently dropped with the flag off.

## Also in flight — 2026-10-09: Dynasty Trade Lab competitor teardown

**Where I stopped:** teardown complete on branch `docs/dtl-teardown` (clean scratchpad clone, PR open): [docs/business/product/2026-10-09-dynastytradelab-teardown/](../docs/business/product/2026-10-09-dynastytradelab-teardown/) — teardown.md, public-research.md, 8 evidence files, 16 screenshots; standing `competitor-matrix.md` created (DTL + Fleeced columns only). League confirmed 1QB by the operator, so no mis-pricing claim. Not merged.

**Next:** operator reads teardown §7 (recommendations by owner) — the two worth acting on are the manager-level "who needs what / who to call" surface and a free-text trade prompt; merge the PR (docs only); enter the older teardowns (DynastyGM, DynastyDealer, RosterAudit, web-tools sweep) as matrix columns next pm-competitor run.

**Watch:** DTL's League Analyzer has no entry point today (dark); 3-team mode untested (0 credits). G-075: subagents don't run from the iCloud clone — re-clone outside iCloud before the next agent-heavy session.
