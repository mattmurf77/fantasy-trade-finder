# HANDOFF

## Usage Trends — shipping 2026-10-10 with the flag ON (branch `feat/usage-trends`, PR #321)

**Where I stopped:** merging PR #321 and deploying with `usage_trends.enabled` **on** (operator, 2026-10-10: "I want it deployed with the flag on"). The Home entry is the hub's **Usage Rates** tile (a separate row from "Check trends", which stays the Elo movers screen).
- **Backend:** `GET /api/usage-trends` (`weeks` selection, `available_weeks`); weekly store (3 `usage_*` tables, `usage_trends_refresh`, `POST /api/cron/usage-trends-refresh`, `scripts/refresh_usage_trends.py`), refreshed by the daily tick.
- **Mobile (iOS 1.21.0):** Simple | Raw stats pill, sortable columns, Filters → Weeks / Position / Show as.

Specs: [scope](../docs/plans/usage-trends/scope.md), [weekly update](../docs/plans/usage-trends/weekly-update.md), [code-walk](../docs/plans/usage-trends/code-walk.md).

**After the ship:** backfill with `python3 scripts/refresh_usage_trends.py --remote`; EAS 1.21.0 → TestFlight; the operator runs the 12-step checklist in scope §3.

**Open design calls (offered, not decided):**
- a frozen player column / pinned actions for Raw stats past 4 weeks (today the whole table swipes);
- extra filters: My team only, Big jumps only, NFL team, minimum usage.

**Don't:**
- sort Version A, or sort anywhere but `sortStatsRows` (`check-usage-trends.js` §2e–2e2);
- write finder pins before a league switch (§2h);
- write the store from anywhere but `usage_trends_refresh`.

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

## Home hub — shipped 2026-10-10

**Where I stopped:** the Home hub (D-202, `nav.home_hub` ON) merged as `70740fea` (PR #319). Render ``dep-db57kdvlot8c73e0e640` (live 17:49 UTC)` is live, and `/api/feature-flags` serves `nav.home_hub: true`. The iOS 1.20.0 EAS build was started with `--auto-submit`.

**Next (operator):** the 15-step TestFlight checklist in [scope.md](../docs/plans/home-engagement/scope.md) §3 on 1.20.0.

**Watch:** the hub reads the flag ONCE per Home mount, so a kill switch takes effect on the next mount. Home's band equals League rankings' band only while `check-position-split-parity.js` passes; change both copies together. ESPN/MFL leagues show "Not available" for standings until F2.
