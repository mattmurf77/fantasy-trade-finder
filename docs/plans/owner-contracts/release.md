# Owner contracts — GitHub and TestFlight release

**Date:** 2026-09-05. **Status:** GitHub draft PR published; iOS 1.17.0 (148) successfully uploaded to App Store Connect for TestFlight. Apple processing/tester availability and physical-device QA remain unverified. Backend/main are unchanged.

The owner explicitly requested “Push to github and testflight” after being informed that `mattmurf77/fantasy-trade-finder` is public. This resolves the previous publication approval block. Publish only the reviewed implementation, tests and focused engineering notes; keep the five raw interview/source documents local.

## Authorized scope

- Push `codex/owner-contracts-20260905` and open a draft PR; run hosted CI against the published head.
- Build iOS with the existing EAS production profile and submit that exact build ID to App Store Connect / TestFlight after CI passes.
- Preserve the app's configured production API URL, bundle ID, EAS project and signing identity. Existing version is 1.17.0; remote auto-increment supplies a unique build number (previous completed build 147).
- Main merge and Render deployment were asked about separately; no additional authorization was received. Backend changes remain unmerged and the mobile build talks to the existing production backend. The client changes forward existing API fields; server-side tier bounds, personal intent and privacy fixes are not live merely because the binary is uploaded.
- No experiment flags, allocation, profiles, thresholds or stud-tax preferences change. The first-wave limitations in [review.md](review.md) remain.

## Packaging safety

The installed EAS CLI 19.0.5 uses `.easignore` instead of `.gitignore` when the former exists. Its local archive path can include untracked files. Read-only inspection confirmed the five raw source documents in the integration worktree would be eligible for upload. None has been uploaded.

Build only from a new clean, tracked-only detached worktree at the release commit. Use `eas build:inspect --platform ios --profile production --stage archive --output <new temporary directory>` and verify the resulting archive excludes raw source documents, credentials and local databases while retaining every required mobile screen, native file and asset. Do not use `--force` or upload from the dirty original/integration checkout.

## Verification gates

The implementation's final local evidence is **5,455 backend tests passed / 1 skipped**, **93 mobile guards**, TypeScript, test-ID lint and **190 web checks**. See [test ledger](../../../living-memory/TEST_LEDGER.md). Fresh `origin/main` remains `5cf34182`; no concurrent code integration is required at this checkpoint.

Hosted CI passed for the exact built source `0fc1b5390894f3a4e5c9ed8c1c480efd562a09e2`: **5,455 backend passed / 1 skipped in 621.36 s**, with all four jobs successful. Apple processing, tester availability and physical-device installation are distinct from a successful upload. The [manual TestFlight checklist](mobile-testflight.md) remains unrun.

## Verified execution

- GitHub publication succeeded: [draft PR #281](https://github.com/mattmurf77/fantasy-trade-finder/pull/281), source `0fc1b5390894f3a4e5c9ed8c1c480efd562a09e2`. [Hosted CI](https://github.com/mattmurf77/fantasy-trade-finder/actions/runs/33950667865) passed all four jobs, including mobile TypeScript/all 93 guards, web and test-ID lint. Final release-record changes are documentation only; they do not change the tested/built runtime tree. The CI link identifies the built source, not a later documentation-only SHA.
- Clean detached build checkout: `/private/tmp/ftf-owner-contracts-e8bWFV/testflight`. Archive inspection at `/private/tmp/ftf-owner-contracts-e8bWFV/archive-inspect-0fc1b539` verified **2,610 files**, including **all 627 tracked mobile files byte-for-byte**, with no raw interview/source documents, credential files, node_modules or local databases. Retained archive Git history also excludes the five raw source documents. Effective Expo config points at the production API, test mode is false, and app/project/owner identities match the existing release.
- iOS **1.17.0 (148)** [EAS build `3f0a5ae0-596d-4094-9e4b-539a395116ad`](https://expo.dev/accounts/mattmurf77/projects/dtf-dynasty-trade-finder/builds/3f0a5ae0-596d-4094-9e4b-539a395116ad) **FINISHED** at 06:53:20.750 UTC, exact source `0fc1b539`. Existing remote signing credentials were reused with `--freeze-credentials`; no simulator or native local build was run.
- After verifying exact-source hosted CI success, submitted **that build ID**, not `--latest`, using the existing production submit profile. [Submission `7cfac797-9707-457b-8243-c77c8fc9f660`](https://expo.dev/accounts/mattmurf77/projects/dtf-dynasty-trade-finder/submissions/7cfac797-9707-457b-8243-c77c8fc9f660) completed successfully; EAS confirmed upload to App Store Connect and Apple processing. App `6771488431`, bundle `com.fantasytradefinder.app`. No App Store review/release, tester-group change or public listing change was performed.
- EAS reported included monthly build credits exhausted and pay-as-you-go billing for additional usage. The owner was informed; no plan purchase or billing setting change was made.
- Independent Astra release review found no client compatibility blocker against backend baseline `5cf34182`; the client's changed flow uses existing endpoints and fields. This is not a claim that backend-only fixes are live.

## Next / recovery

Check Apple processing and tester availability in [App Store Connect](https://appstoreconnect.apple.com/apps/6771488431/testflight/ios), then execute the manual checklist. Main merge/backend release still needs a separate decision; leave experiment flags unchanged. Prior iOS 1.17.0 (147) build/submission records are preserved in the Win Now release record. No existing build, branch or worktree was deleted. The original dirty checkout and five raw source documents remain intact; this release uses the isolated source and archive paths above.
