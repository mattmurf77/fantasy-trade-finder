# Owner contracts — GitHub and TestFlight release

**Date:** 2026-09-05. **Status:** PR #281 merged; backend live at `4026ebc8` since 09:51:59 UTC. iOS 1.17.0 (148) uploaded to App Store Connect for TestFlight. Apple processing/tester availability and physical-device QA remain unverified. All three trading arms and existing runtime configuration are preserved.

The owner explicitly requested “Push to github and testflight” after being informed that `mattmurf77/fantasy-trade-finder` is public. This resolves the previous publication approval block. Publish only the reviewed implementation, tests and focused engineering notes; keep the five raw interview/source documents local.

## Authorized scope

- Push `codex/owner-contracts-20260905` and open a draft PR; run hosted CI against the published head.
- Build iOS with the existing EAS production profile and submit that exact build ID to App Store Connect / TestFlight after CI passes.
- Preserve the app's configured production API URL, bundle ID, EAS project and signing identity. Existing version is 1.17.0; remote auto-increment supplies a unique build number (previous completed build 147).
- The initial GitHub/TestFlight stage did not include backend activation. The owner subsequently said “Turn it on” after being told the backend was undeployed, authorizing main merge and Render release. The unflagged server-side tier bounds, personal intent and privacy fixes are now deployed. The separate personal-market experimental policy remains off.
- No experiment flags, allocation, profiles, thresholds or stud-tax preferences change. The first-wave limitations in [review.md](review.md) remain.

## Packaging safety

The installed EAS CLI 19.0.5 uses `.easignore` instead of `.gitignore` when the former exists. Its local archive path can include untracked files. Read-only inspection confirmed the five raw source documents in the integration worktree would be eligible for upload. None has been uploaded.

Build only from a new clean, tracked-only detached worktree at the release commit. Use `eas build:inspect --platform ios --profile production --stage archive --output <new temporary directory>` and verify the resulting archive excludes raw source documents, credentials and local databases while retaining every required mobile screen, native file and asset. Do not use `--force` or upload from the dirty original/integration checkout.

## Verification gates

The implementation's final local evidence is **5,455 backend tests passed / 1 skipped**, **93 mobile guards**, TypeScript, test-ID lint and **190 web checks**. See [test ledger](../../../living-memory/TEST_LEDGER.md). At the initial pre-merge checkpoint, refreshed `origin/main` was `5cf34182`; no concurrent code integration was required.

Hosted CI passed for the exact built source `0fc1b5390894f3a4e5c9ed8c1c480efd562a09e2`: **5,455 backend passed / 1 skipped in 621.36 s**, with all four jobs successful. Apple processing, tester availability and physical-device installation are distinct from a successful upload. The [manual TestFlight checklist](mobile-testflight.md) remains unrun.

## Verified execution

- GitHub publication succeeded: [draft PR #281](https://github.com/mattmurf77/fantasy-trade-finder/pull/281), source `0fc1b5390894f3a4e5c9ed8c1c480efd562a09e2`. [Hosted CI](https://github.com/mattmurf77/fantasy-trade-finder/actions/runs/33950667865) passed all four jobs, including mobile TypeScript/all 93 guards, web and test-ID lint. Final release-record changes are documentation only; they do not change the tested/built runtime tree. The CI link identifies the built source, not a later documentation-only SHA.
- Clean detached build checkout: `/private/tmp/ftf-owner-contracts-e8bWFV/testflight`. Archive inspection at `/private/tmp/ftf-owner-contracts-e8bWFV/archive-inspect-0fc1b539` verified **2,610 files**, including **all 627 tracked mobile files byte-for-byte**, with no raw interview/source documents, credential files, node_modules or local databases. Retained archive Git history also excludes the five raw source documents. Effective Expo config points at the production API, test mode is false, and app/project/owner identities match the existing release.
- iOS **1.17.0 (148)** [EAS build `3f0a5ae0-596d-4094-9e4b-539a395116ad`](https://expo.dev/accounts/mattmurf77/projects/dtf-dynasty-trade-finder/builds/3f0a5ae0-596d-4094-9e4b-539a395116ad) **FINISHED** at 06:53:20.750 UTC, exact source `0fc1b539`. Existing remote signing credentials were reused with `--freeze-credentials`; no simulator or native local build was run.
- After verifying exact-source hosted CI success, submitted **that build ID**, not `--latest`, using the existing production submit profile. [Submission `7cfac797-9707-457b-8243-c77c8fc9f660`](https://expo.dev/accounts/mattmurf77/projects/dtf-dynasty-trade-finder/submissions/7cfac797-9707-457b-8243-c77c8fc9f660) completed successfully; EAS confirmed upload to App Store Connect and Apple processing. App `6771488431`, bundle `com.fantasytradefinder.app`. No App Store review/release, tester-group change or public listing change was performed.
- EAS reported included monthly build credits exhausted and pay-as-you-go billing for additional usage. The owner was informed; no plan purchase or billing setting change was made.
- Independent Astra release review found no client compatibility blocker against backend baseline `5cf34182`; the client's changed flow uses existing endpoints and fields. This is not a claim that backend-only fixes are live.

## Next / recovery

Check Apple processing and tester availability in [App Store Connect](https://appstoreconnect.apple.com/apps/6771488431/testflight/ios), then execute the manual checklist. Leave experiment flags unchanged. Prior iOS 1.17.0 (147) build/submission records are preserved in the Win Now release record. No existing build, branch or worktree was deleted. The original dirty checkout and five raw source documents remain intact; this release uses the isolated source and archive paths above.

## Backend activation — 2026-09-05

- Final PR head `f88afabb669aa946de65a3a4a20d8b85b9256724` passed [all four CI jobs](https://github.com/mattmurf77/fantasy-trade-finder/actions/runs/33951522857), including **5,455 backend passed / 1 skipped in 624.31 s**. Refreshed main was still `5cf34182`; the merge gate checked the exact head, base, mergeability and required successes.
- PR #281 squash-merged at **09:50:55 UTC** as `4026ebc81eaae50b345b42421641125c5b8d413e`. After fetch, the squash tree compared byte-identical to tested head `f88afabb`; mobile runtime remains identical to build 148's source `0fc1b539`.
- Render service `srv-d7g37ftckfvc73a32gvg`, configured for main auto-deploy, one instance and one Gunicorn worker, deployed automatically. Deployment `dep-daduc0bm8hqs73ckbifg` became **live at 09:51:59.126135 UTC**, reporting exact commit `4026ebc8`. No duplicate manual deploy or environment/config edit was made.
- [Production smoke](production-smoke.json): root/tier-config/flags and read-only operator health/config/experiment summaries return 200; root HTML matches reviewed bytes. Unauthenticated trade/admin-config reads return 401. PostgreSQL health reports the event-ID index present and zero ingest transaction failures.
- Before/after canonical hashes match for **all 207 flags, 258 model values, tier definitions and experiment summaries**. Live `trade.bakeoff`, valuation telemetry and roster evaluation remain **true**; personal-market policy and roster protection remain **false**. This live baseline differs from some checked-in dark defaults; no flag was flipped by this release. Win Now's existing three beta flags stay true.
- No new schema, bulk backfill or destructive data change is part of this patch. Existing trade feedback is replayed under the new tier bounds after restart, so effective current values can change while stored ranking/trade history remains intact. Read-only smoke does not prove a real user's personalized trade result; focused tests and the unrun manual checklist cover that boundary.

Rollback is a code deployment, not a new policy flag: prior live source was `c28ec6d802463e048d59a97967e9bb5bb9fdc6f9` (deployment `dep-dadq6k97lnhs73e8o970`). Existing schema is compatible, but already-published confidence values would not be undone automatically. A full revert would also restore the known counterparty-value exposure; prefer a narrowly corrective release retaining privacy redaction when feasible. No rollback was performed. Deployment-record commits change documentation only; preserve `[skip render]` in the evidence PR's squash commit to avoid an unnecessary service restart, then verify the existing deployment remains live.
