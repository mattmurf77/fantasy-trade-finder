# Landing page release — 2026-09-16

## Scope and authorization

Operator requested: “Push the landing page changes live to the site.” Web only: compact interactive ranking/comparison/trade illustrations above sign-in, production-style market fairness bar, rookie draft pick value copy, and flag-aware Sleeper/ESPN/MFL platform choices. ESPN/MFL continue into mobile verification; legacy browser claims stay disabled. Separate logo export and unapproved copy suggestions are excluded.

## Pre-flight evidence

- [Initiative scope and browser evidence](../../plans/landing-ranking-graphic/scope.md); canonical [Auth screen component](../../design/components.md).
- Independent diff review: no release-blocking findings; flags and mobile handoff restrictions preserved.
- Local gates: 195/195 web structural checks, JavaScript syntax, and diff whitespace; keyboard/viewport and delayed-flags regression checks.
- Current-head GitHub CI is required before merge; record the run and final checks with release delivery evidence.
- No new secrets, environment settings, migrations, flags, data collection or mobile binary. Existing Render configuration is retained.
- No production credentials or account state are used by smoke checks.

## Ship plan

1. Integrate fetched main, preserving unrelated checkout changes.
2. Commit/push scoped branch, open PR and require all four current CI jobs green.
3. Merge reviewed head to main to trigger Render.
4. Confirm Render live commit, compare served asset bytes, and inspect public desktop/mobile landing and platform choices. Production sign-in is not exercised.
5. Record actual delivery evidence here and in the standing release log.

## Rollback

Previous main at release preparation: `82c5f118`. If static assets fail to load, platform choices expose legacy claims, or sign-in/step layout regresses, redeploy the previously live Render commit and revert the landing merge through a checked PR. Confirm the previously live SHA from Render immediately before merging. No database or flag rollback is required for this release.

## Delivery status

Authorized; CI and deployment verification pending. A successful push alone is not evidence of live delivery.

## Decisions needed

None. The operator has authorized release.

## Handoffs

No mobile build is part of this release. Native ESPN/MFL verification remains the existing app flow.
