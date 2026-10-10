# HANDOFF

## Usage Trends — built 2026-10-10, held for the home redesign (branch `feat/usage-trends`, worktree `.claude/worktrees/usage-trends`)

**Where I stopped:**
- **The feature is built:**
  - backend `GET /api/usage-trends` (flag `usage_trends.enabled`, off);
  - mobile `UsageTrendsScreen` with **two views behind a Simple | Raw stats pill**. Version A is the approved draft A as drawn; Version B is a per-week table + Total with icon actions. This was the operator's direction mid-session;
  - shared `ClaimSheet`;
  - Home row + Free Agents link;
  - Quick Set `positionSeq`.
- Evidence: 24 backend tests and 6 sabotages; `check-usage-trends.js` and 6 sabotages; tsc clean; every `check-*.js` green. Details in [scope](../docs/plans/usage-trends/scope.md) §3 and [code-walk](../docs/plans/usage-trends/code-walk.md).
- A preview of Version B was drawn on the [canvas](https://claude.ai/artifact/WUZmSymvTASsQvdjeK8yjo).

**Blocked on (operator):** **do not merge or deploy until the home-engagement redesign (`design/home-engagement`, flag `nav.home_hub`) is live** (operator, 2026-10-10). Then:
- rebase onto `origin/main`;
- re-home the Home entry as a hub tile and keep the flag-off text row;
- reconcile `check-home-tab.js` with what that branch expects (it wants the file unmodified; this branch added assertion 4i);
- exact-head CI, merge, deploy flag-off, TestFlight build, and the 12-step checklist in scope §3.

**Don't:** sort the list client-side (`check-usage-trends.js` §2e); write finder pins before a league switch (§2h).

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
