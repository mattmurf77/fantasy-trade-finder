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

Initial release LIVE: [PR #295](https://github.com/mattmurf77/fantasy-trade-finder/pull/295) merged as `3789bb3639691057f79bd0444b2e580982c634bb` at 05:00:42 UTC. [Current-head CI](https://github.com/mattmurf77/fantasy-trade-finder/actions/runs/35056911335) passed all four jobs on `9a91b7d1`; backend: **5953 passed, 1 skipped**.

Render deployment `dep-dal24v15efls73fmir7g` became live at **05:02:32 UTC**. Public landing HTML, stylesheet, app script and step script returned 200 and matched the release byte-for-byte. Public flags returned 200 with all three platform-choice flags true. Live browser verification confirmed the production-style fairness bar, ESPN/MFL mobile handoffs, hidden legacy forms, and return to Sleeper. No credentials or authenticated account operations were exercised. Preflight confirmed existing CRON_SECRET is present without recording its value.

### Narrow embedded-browser correction

Live 320×640 verification exposed persistent root and overlay scrollbars, consuming 30px of content width and moving the trade-panel sign-in bottom to y=679.46. The fixed landing already owns scrolling. A scoped root/body lock now applies only while `#auth-screen` lacks `.hidden`; it releases automatically for the signed-in application. The landing retains `overflow:auto`. The changed stylesheet URL is versioned again.

Independent review found no blocker. Actual in-app browser keyboard/layout checks passed for all panels at 320×640, 390×844 and 1366×768. At 320px, sign-in bottoms are y=586.30 / 573.01 / 634.69 for steps 1/2/3; at desktop all three are y=619.96. Web structure remains **195/195**. Correction CI and deployment are required before this follow-up is marked live. The correction PR's delivery entry records its final deployed commit and public checks.

## Decisions needed

None. The operator has authorized release.

## Handoffs

No mobile build is part of this release. Native ESPN/MFL verification remains the existing app flow.
