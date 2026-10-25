# HANDOFF

## Usage Trends — live; order toggle shipped 2026-10-12 (PR #323 → `fc0f6149`)

**Where I stopped:** shipped and live.
- **#321** (2026-10-10) shipped the feature with the flag ON.
- **#323** (2026-10-12) added Simple's **Biggest jumps | Weekly share** toggle, "Jumped from X% to Y%" cards, the jumps / back or new / everyone else sections, and a volume floor on returns (D-205).
- Render `dep-db6mh67avr4c73cqn4h0` is live on `fc0f6149`.
- iOS 1.21.2 build 165 is on `--auto-submit` ([build](https://expo.dev/accounts/mattmurf77/projects/dtf-dynasty-trade-finder/builds/435def34-19c0-48ee-9558-ae0282c39b4e)).
- Both branches and worktrees are ledgered in `docs/recovery/` and removed.

**Next (operator):** on 1.21.2, run the 12-step checklist in [scope §3](../docs/plans/usage-trends/scope.md) and the 8-step one in [scope-order-toggle §3](../docs/plans/usage-trends/scope-order-toggle.md). **Weeks 5 and 6 were loaded by hand**: week 5 on 2026-10-15 (30 teams; byes CAR/KC), with the same run picking up stat corrections to weeks 1–4, and week 6 on 2026-10-21 (28 teams; byes CIN/DET/MIA/MIN). The default window is now weeks 3–6. **The daily tick has never refreshed the store:** it is killed by the 120 s worker timeout every day (runbook § Known outage, NEXT 2026-10-15; operator: report only). Until that's fixed, run `python3 scripts/refresh_usage_trends.py --remote` each week after Sleeper rolls over.

**Open design calls (offered, not decided):**
- a frozen player column / pinned actions for Raw stats past 4 weeks (today the whole table swipes);
- extra filters: My team only, Big jumps only, NFL team, minimum usage.

**Don't:**
- sort Version A anywhere but `sortByLatestWeek` (Weekly share), or Version B anywhere but `sortStatsRows` (`check-usage-trends.js` §2e–2e5);
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
