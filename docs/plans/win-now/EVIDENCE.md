# Win Now evidence and remaining verification

2026-09-04 evidence checkpoint; updated 2026-09-05 for explicit experimental beta-release authorization. Historical test counts and raw exploratory artifacts below are preserved. Authorization permits season/Win Now/championship before calibration; it does not certify probability accuracy or successful deployment. [2026-09-05 release record](../../business/ops/2026-09-05-win-now.md) records final CI, live Render verification and successful iOS 1.17.0 (147) upload; tester availability and physical QA remain unverified.

## Security integration update — 2026-09-05

Backend/web is live at `c28ec6d8` after PR #280 merged on 2026-09-05 at 05:06:23 UTC. All four final CI checks passed for `abb1af118d3fe39f32292e99cecc64cebff1d2f3` (run `33945722395`). Render deployment `dep-dadq6k97lnhs73e8o970` is LIVE since 05:07:28.48285 UTC with all three beta flags verified true. iOS **1.17.0 (147)** finished building and uploaded successfully; Apple processing and tester availability are separate, with tester availability still unverified. Forecast/title calibration and physical-device QA remain unproven.

See the [release record](../../business/ops/2026-09-05-win-now.md) and [production smoke artifact](production-smoke.json).

## Initial implementation checkpoint — completed client checks

| Check | Observed result |
|---|---|
| `mobile/node_modules/.bin/tsc --noEmit -p mobile/tsconfig.json` | Pass, no TypeScript errors |
| `node mobile/tests/check-win-now.js` | 24 checks pass; includes executable mobile formatters and shipped web module with a DOM/deferred-response harness |
| `node --check web/js/app.js` and `node --check web/js/win-now.js` | Pass |
| `python3 qa/web/check_web_structure.py` | 185/185 pass |
| `bash mobile/scripts/testid-lint.sh` | Pass |
| `git diff --check` | Pass at frontend handoff |

These are local branch results, not hosted CI, native runtime proof or evidence of forecast calibration. Parent reran TypeScript, all 24 feature checks, web structural/syntax checks and test-ID lint after integration.

## Code-walk proof

- Entry: `mobile/src/screens/TradesScreen.tsx:6371` and `LeagueSummaryScreen.tsx:1518` push the unconditional root `WinNow` registration in `mobile/src/navigation/RootNav.tsx`; its screen owns the single root-push FeedbackFAB. `web/index.html` has gated Trade Finder and League entries to the additive SPA view.
- Identity/cancellation: `mobile/src/screens/WinNowScreen.tsx:50` keys screen state by user and league; its baseline and parameter effects abort old work. `web/js/win-now.js:54` checks active view, request epoch, league and user before applying responses. Mode exit, changed limits/objective/protection, refresh and expiry invalidate work.
- Search: `mobile/src/api/winNow.ts:5` uses the authenticated client. Both screens POST dedicated search settings, poll only that job with a bounded wait, and retain the returned trade order. The executable harness delays an old league response and an old objective's queued result, then proves neither can apply or start late polling.
- Evaluation/feedback: edited asset IDs use `/api/win-now/evaluate`; like/pass uses `/api/win-now/scenarios/<id>/decision`. The 24-check suite pins absence of legacy swipe/queue calls, the 3-asset editor bound, 0–10% budget / 75–100% balance controls, explicit rejection messages and HTTP-200 unavailable decision explanations.
- Display: `mobile/src/utils/winNow.ts:4` formats `100 * (after-before)` as percentage points, preserving zero and missing values. Both clients sort a copy of standings by expected seed and label it Avg finish (two decimals), while leaving trades in server order. Receipts explicitly state uncalibrated beta and exclude model/projection uncertainty; cards show the selected objective's paired sampling range, independent-run change and conservative search gain, never labeling these a forecast confidence interval. Both clients require the championship flag plus new snapshot capability and remove expired recommendations; no legacy title estimate is read.

Line numbers describe this build checkpoint and may shift during parent corrections; symbols and the executable suite are the durable lookup points.

## Integrated review and checks

Parent reviewed the forecast provider, complete simulator and optimizer, mobile/web implementations, their tests and documentation. Corrections include serving/evaluation contracts, paired confirmation evidence, package-sensitive lineups, candidate coverage, ranking provenance, source-wide cutoffs/capture-age expiry, current pick/preference/valuation revalidation and deleted-account persistence guards. No statistical calibration result was produced.

- First full backend run: **4,812 passed, 1 skipped, 1 failed** in 359.90 seconds. The failure was release flag mirror drift; the three new false flags were added to the release fixture. Further account/freshness regressions were then added.
- Final API/storage run: **54 passed** in 0.99 seconds, including real route→worker→optimizer→simulator→storage→poll flow, decision isolation, cutoff expiry, deletion and retention.
- Final broad run excluding those two independently executed files: **4,790 passed, 1 skipped, 2 failed** in 354.35 seconds. Both failures were derivative flag-fixture key parity (onboarding/profiles); both fixtures now include the same three false flags.
- After those corrections and the explicit platform-only pick-source declaration, the affected seed/flag, pick-containment, service, API and storage suites were rerun together: **200 passed**. The broad run plus the separately executed API/storage cases covers **4,846 passing backend cases and one skip**; the recorded commands above distinguish the corrected/rerun failures from a single all-green invocation.
- Local runtime is Python 3.14; deployment uses Python 3.12. No new dependency was added; hosted Python 3.12 CI was still a merge gate at this historical checkpoint; the final release result appears below.
- Synthetic performance: 12 teams × 25 players, 9 slots, 14 forecast weeks, 1,000 draws; baseline 1.14s, exact-lineup search plus 8 paired/independent-confirmation finalists 46.11s; 11,990 screened, one frontier result. Source/persistence alone mocked. This is a latency sample, not a production SLA or calibration.

## Parent browser inspection

The parent ran a loopback-only synthetic fixture using the actual shipped `web/js/win-now.js`, tokens, styles and Win Now CSS. Verified sorted Avg finish standings, disabled championship, 3%/90% defaults, search result, both-side evidence, edit controls and visible edited-trade result. Inspected screenshots at the default wide viewport and 390×844: card text wrapped and controls remained usable. Temporary viewport was reset and the preview server/tab closed. The fixture used simulated players and mocked HTTP responses; it does not prove real authentication/source availability or native behavior. Machine model/snapshot IDs remain in API evidence and were removed from the user receipt after review.

## Manual TestFlight and browser checklist

1. All flags off: existing Trade Finder and League behavior remains; stale Win Now deep link shows unavailable with a working Back control. Season flag only: standings entry works while trade search is unavailable. Test full-screen Back/edge swipe and the one FeedbackFAB.
2. On a supported fixture league, inspect source/timestamp/coverage, final records and distributions. Verify championship control and numbers stay absent with either its flag or snapshot capability false; a mechanically supported fixture with both true may show experimental, uncalibrated numbers. Confirm the beta disclaimer and any exact scoring-omission warning remain visible.
3. Search with wins then playoffs. Set budget to 0, 5 and 10%; reject 11%. Check 75/80/100% market balance and reject 70%. Protect a buyer asset and confirm no offered package contains it. A lower requested fairness must never override the server floor.
4. While requests run, change objective/limits/protection, switch league, leave the view and return. Old cards and late queued jobs must not replace the new state. Exercise Cancel and the bounded-wait message; retry must be explicit.
5. Open Edit & evaluate on a returned card; verify buyer/partner ownership, three-assets-per-side controls, disabled unavailable assets, rejected-package reasons, and both teams' before/after numbers. A 20% → 25% change must read +5.0 pp. Changed assets must clear the old evaluation.
6. Force empty results, a network/HTTP error, HTTP-200 unavailable and an expired snapshot. Verify honest copy, no endless spinner, enabled manual recovery, removal of expired cards and no request against expired evidence. Check likes/passes are isolated season decisions with visible save failures.
7. On a physical supported iPhone and in narrow/wide browsers, inspect long player/pick/league names, keyboard access, focus, VoiceOver/Dynamic Type, asset chooser scrolling and primary actions. Review console/network failures in the real web app; the DOM test harness is not this check.

No simulator, Maestro flow, native build, deployment or production flag changes were performed as the historical client validation above. The separately authorized 2026-09-05 release is now verified live, with final CI and iOS upload recorded below.

## Historical outcome follow-up — 2026-09-04

Parent-reviewed Astra collection/evaluator/audit work: 119 affected backend tests pass; real Sleeper pull recovered 6 seasons / 72 team-seasons / 1,008 regular-season team scores / 6 champions, and the offline report correctly shows zero eligible archived predictions. Post-game source revisions and cohort scoring coverage are explicit limitations. [Protocol, artifacts, commands and code walk](HISTORICAL-VALIDATION.md). No calibration success, production/model change or UI change claimed.

## Authorized exploratory evaluation — 2026-09-04

Actual revised-source simulation/evaluation completed: Lakeview 2024, after weeks 3/6/9/12, 10,000 draws each. Lakeview 2025 lacked full lineup forecast coverage; FFv3 active K/IDP formats excluded. Parent reviewed the opt-in evaluator changes/replay adapter; **144 affected tests passed in 0.62s**, cached rerun and direct evaluator metrics identical, strict-mode control rejects all four cohorts. [Numeric results and exact assumptions](EXPLORATORY-RESULTS.md). No production flag, model or UI changes.

## Final release verification — 2026-09-05

Final Python 3.12 backend suite: **5,353 passed, 1 skipped in 732.08 seconds**. Parent merged focused run: **220 passed in 15.25 seconds**. Client verification: all **92** structural guards, TypeScript and testID lint passed; **190** web structure checks, **23** auth checks and actual isolated Chromium/MV3 runtime passed. All four hosted CI checks succeeded on tested head `abb1af118d3fe39f32292e99cecc64cebff1d2f3`, run `33945722395`; PR #280 squash-merged as `c28ec6d802463e048d59a97967e9bb5bb9fdc6f9`.

Production smoke verified HTTP 200 for root and flags, all three serving flags true, exact deployed bytes for `app.js`, `win-now.js` and Win Now CSS, and HTTP 401 from four new unauthenticated endpoints. The live in-app-browser landing rendered with no error/warning logs. This does not establish an authenticated production forecast or a physical TestFlight pass. The real-source Lakeview check still refused `unknown_starter_availability:1:1`; no forecast was fabricated.

EAS build `69b53400-1d8d-42ec-ad7a-5d0e3c756059` for iOS **1.17.0 (147)** finished. It compiled `77824c02`; runtime code was byte-identical to tested head `abb1af11` and released main. Submission `6184a831-a685-497b-8e97-734ed30fa4b9` uploaded successfully and entered Apple processing; tester availability and physical installation remain unverified. The first optional `--what-to-test` attempt was rejected as Enterprise-only before submission; retrying without that field uploaded the same binary successfully. Superseded build 146 was canceled and was not submitted.

[Production smoke artifact](production-smoke.json) and [real-source refusal](release-source-smoke.json). The [manual checklist](#manual-testflight-and-browser-checklist) remains unperformed on a physical iPhone. Exploratory evidence does not establish calibration.
