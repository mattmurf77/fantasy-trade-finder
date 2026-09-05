# Owner contracts — GitHub and TestFlight release

**Date:** 2026-09-05. **Status:** publication and iOS distribution authorized; execution in progress.

The owner explicitly requested “Push to github and testflight” after being informed that `mattmurf77/fantasy-trade-finder` is public. This resolves the previous publication approval block. Publish only the reviewed implementation, tests and focused engineering notes; keep the five raw interview/source documents local.

## Authorized scope

- Push `codex/owner-contracts-20260905` and open a draft PR; run hosted CI against the published head.
- Build iOS with the existing EAS production profile and submit that exact build ID to App Store Connect / TestFlight after CI passes.
- Preserve the app's configured production API URL, bundle ID, EAS project and signing identity. Existing version is 1.17.0; remote auto-increment supplies a unique build number (previous completed build 147).
- Main merge and Render deployment have been asked about separately and are not assumed. Until separately authorized, backend changes remain unmerged and the mobile build talks to the existing production backend. The client changes forward existing API fields; server-side tier bounds, personal intent and privacy fixes are not live merely because the binary is uploaded.
- No experiment flags, allocation, profiles, thresholds or stud-tax preferences change. The first-wave limitations in [review.md](review.md) remain.

## Packaging safety

The installed EAS CLI 19.0.5 uses `.easignore` instead of `.gitignore` when the former exists. Its local archive path can include untracked files. Read-only inspection confirmed the five raw source documents in the integration worktree would be eligible for upload. None has been uploaded.

Build only from a new clean, tracked-only detached worktree at the release commit. Use `eas build:inspect --platform ios --profile production --stage archive --output <new temporary directory>` and verify the resulting archive excludes raw source documents, credentials and local databases while retaining every required mobile screen, native file and asset. Do not use `--force` or upload from the dirty original/integration checkout.

## Verification gates

The implementation's final local evidence is **5,455 backend tests passed / 1 skipped**, **93 mobile guards**, TypeScript, test-ID lint and **190 web checks**. See [test ledger](../../../living-memory/TEST_LEDGER.md). Fresh `origin/main` remains `5cf34182`; no concurrent code integration is required at this checkpoint.

Hosted CI, exact build/source identity, EAS completion and submission outcome will be recorded here. Apple processing, tester availability and physical-device installation are distinct from a successful upload. The [manual TestFlight checklist](mobile-testflight.md) remains unrun.
