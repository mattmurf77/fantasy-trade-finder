# Feature Scope — No "beta" in the shipping binary (App Review 2.2)

**Date:** 2026-10-31
**Entry point:** direct ask. head-eng, on the operator's "assign out pending backlog work for launch now" (2026-10-31): launch tracker backlog rank 4. Apple guideline 2.2 says betas belong on TestFlight, and reviewers flag "beta" in an App Store binary. Due in release-lead's queue by 11-03 for the 11-06 binary; otherwise it moves to update 1.
**Builder:** eng-mobile worker for league-eng, branch `build/no-beta-labels` (from `origin/main` @ `63e373e2`)
**Operator sign-off on waivers:** pending, via head-eng. One waiver, §1 (c).

## Contents

- [What ships](#what-ships)
- [1. Analytics scope](#1-analytics-scope)
- [2. Schema & flag scope](#2-schema--flag-scope)
- [3. Evidence scope](#3-evidence-scope)
- [4. Docs scope](#4-docs-scope-mandatory--hld--lld--api)
- [5. Ship gate declaration](#5-ship-gate-declaration)
- [Inventory](#inventory)
- [Reviews](#reviews)
- [Evidence](#evidence)

---

## What ships

The word "beta" is removed from every user-visible string in the iOS binary. The `beta` data fields stay, and so does every behaviour they drive. Only the shown text changes. It's a removal, so there's no new copy. Marketing's launch batch already bans "beta" in user copy.

| File | Change |
|---|---|
| `mobile/src/components/CardImpactBlock.tsx` | The trade card's playoff-impact ribbon (`${testID}.odds.ribbon`) reads `PROJECTED` whatever `impact.beta` is (was `PROJECTED · BETA` when `impact.beta`). |
| `mobile/src/screens/TeamReviewScreen.tsx` | The Playoff outlook card's ribbon reads `PROJECTED` whatever `o.beta` is (was `PROJECTED · BETA`). |
| `mobile/src/screens/LeagueSummaryScreen.tsx` | `betaRibbonLabel` no longer appends `beta`. The Season outlook ribbon reads `Projected · preseason` before week 1 and `Projected` otherwise (was `Projected · preseason · beta` / `Projected · beta` through week 5). `meta.beta` still hides win-loss records through week 5 (`showRecords = !meta.beta`), which is the load-bearing honesty rule (`docs/cross-client-invariants.md` § Playoff outlook bands), unchanged. The header comment is updated. Identifiers (`betaRibbonLabel`, `styles.betaRibbon`) and the testID `league-summary.odds.beta-ribbon` keep their names: none of them is shown. |
| `mobile/tests/check-no-beta-copy.js` (new) + `npm run test:no-beta-copy` | Guard (§3). |
| `mobile/tests/README.md` | Row for the new guard. |

Not in scope:
- **Web** (`web/terms.html`, `web/privacy.html` "beta" lines): #373 (onboarding-eng) covers them, per head-eng.
- **Backend:** no user-facing backend string contains "beta". Every hit in `backend/*.py` is a comment, a statistics term (the Beta distribution) or admin analytics copy.
- **Win Now** shows "Uncalibrated estimate" (`utils/winNow.ts:22`), not "beta".

## 1. Analytics scope

- [ ] **(a) New events specced:** none.
- [ ] **(b) Existing events cover it:** none. No event fires on these ribbons.
- [x] **(c) WAIVED, no analytics needed:** a label-text removal on three ribbons. No behaviour, flow or data changes, so there's nothing new to measure.

## 2. Schema & flag scope

- New/changed tables or columns: **none**. The `beta` fields in `api/calc.ts`, `api/league.ts`, `api/teamReview.ts` and `shared/types.ts` are unchanged.
- New/changed feature flags: **none**. Rollback is revert + EAS build.
- New env vars / `model_config` keys: **none**.

## 3. Evidence scope

- [x] **Structural guard:** `mobile/tests/check-no-beta-copy.js` (AST, `typescript` from `mobile/node_modules` like its neighbours; G-035: it proves the source holds no such string, not what renders).
  - Scans every `.ts` / `.tsx` / `.js` / `.jsx` under `mobile/src`, plus `mobile/App.tsx`. A string literal, template literal part or JSX text matching `/\bbeta\b/i` fails, except:
    - the value of a `testID` / `nativeID` JSX attribute (never shown);
    - import / export module specifiers;
    - string-literal types;
    - quoted property names.
  - Also scans every string value in `mobile/app.json` (display name, permission strings).
  - One explicit allowlist entry, with its reason: `UpdateGateScreen.tsx` `TESTFLIGHT_URL = 'itms-beta://'`, a URL scheme that is never rendered. Each allowlist entry must match exactly once, so stale entries fail.
  - A positive control: the scan must visit at least 100 files and find the three ribbons' `PROJECTED` / `Projected` strings, so it can't pass vacuously.
- [x] **Unit tests:** no backend change, so none.
- [x] **Code-walk proof** (file:line at the branch tip):
  - **Trade card:** `CardImpactBlock.tsx:182-183`. `<Text style={styles.ribbon} testID={`${testID}.odds.ribbon`}>` renders the literal `PROJECTED`. The file no longer reads `impact.beta`. The `beta` field stays in `api/calc.ts:230` / `shared/types.ts:590`.
  - **Team review:** `TeamReviewScreen.tsx:442-443`. `<ChalkText style={styles.ribbon}>` renders the literal `PROJECTED`. The file no longer reads `o.beta`; the field stays in `api/teamReview.ts:56`.
  - **Season outlook:** `LeagueSummaryScreen.tsx:2775` `betaRibbonLabel` returns `'Projected'`, plus `' · preseason'` when `meta.is_preseason`. It's rendered at `:3087` inside `league-summary.odds.beta-ribbon` (`:3084`). `:3071` `showRecords = !meta.beta` is unchanged, so win-loss records stay hidden through week 5.
- [x] **Manual TestFlight checklist** (operator, on the build that carries this branch):

  | # | Steps | Expected |
  |---|---|---|
  | 1 | League → Season outlook section | The ribbon beside "Season outlook" reads **PROJECTED** (or **PROJECTED · PRESEASON** before week 1), never "BETA". The source says `'Projected'`, but `type.label` renders it uppercase, as on rows 2 and 3 (design-lead, 2026-10-31). In a league with fewer than 6 completed weeks, win-loss records stay hidden, as before. |
  | 2 | Trades → a trade card that shows the "Playoff outlook" block | The ribbon reads **PROJECTED**, never "BETA". |
  | 3 | League → a team → Team review → "Playoff outlook" card | The ribbon reads **PROJECTED**, never "BETA". |

  On 2026-10-31 most leagues have 6+ completed weeks, so `beta` is already false and these rows show no visible change. The guard is the evidence for the early-season case. Rows 1–3 confirm nothing else moved.
- `testID`s added/renamed: none. `bash scripts/testid-lint.sh` must stay OK.

**Commands to run** (from `mobile/`; this worktree has no `node_modules` (G-022), so guards run with `NODE_PATH` set to another checkout's `node_modules`, and tsc runs on a deps-linked scratch copy): the new guard, every `tests/check-*.js` that reads one of the three files (21, listed by `git grep -l -E "CardImpactBlock|TeamReviewScreen|LeagueSummaryScreen" -- mobile/tests`), `testid-lint`, `tsc --noEmit`. The results and sabotage runs go in [Evidence](#evidence) below.

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a | No route or contract change. The `beta` fields are still served. |
| `living-memory/LLD.md` | n/a | No new convention. The guard is listed in `mobile/tests/README.md`. |
| `docs/architecture.md` | n/a | No module or data-flow change. |
| `living-memory/HLD.md` | n/a | No new module, client or major flow. |
| `docs/cross-client-invariants.md` | n/a | The ribbon wording isn't registered. The registered rule, `meta.beta` as the two-state switch (no win-loss numbers in weeks 0–5), is unchanged. |
| `docs/glossary.md` | n/a | No new term. |
| ADR or `DECISIONS.md` | n/a | No non-obvious choice: the operator's launch tracker plus Apple 2.2. |

## 5. Ship gate declaration

- **CI green:** `backend-tests` + `mobile-typecheck` (runs `check-*.js`) + `maestro-testid-lint` on the pushed sha.
- **Evidence recorded:** this file. A `living-memory/TEST_LEDGER.md` entry at merge goes to release-lead's scribe.
- **TestFlight verification:** §3 checklist, run by the operator, with the outcome in TEST_LEDGER.
- Express lane declared by the operator? **No.** Full gates.

## Inventory

`git grep -n -i "beta" origin/main -- mobile/src` @ `63e373e2`. Every user-visible hit:

| Where | String | Fate |
|---|---|---|
| `components/CardImpactBlock.tsx:183` | `'PROJECTED · BETA'` | removed |
| `screens/TeamReviewScreen.tsx:443` | `'PROJECTED · BETA'` | removed |
| `screens/LeagueSummaryScreen.tsx:2776` | `parts.push('beta')` → "Projected · … · beta" | removed |

The rest are not shown to users and stay:
- identifiers: `beta` fields, `betaRibbonLabel`, `styles.betaRibbon`;
- the testID `league-summary.odds.beta-ribbon`;
- comments, `CLAUDE.md` notes and the version-parser comment in `utils/appVersion.ts`;
- `UpdateGateScreen.tsx:44` `TESTFLIGHT_URL = 'itms-beta://'`, a URL scheme. It is allowlisted in the guard and flagged separately to head-eng: an App Store binary's update gate pointing at TestFlight is a distribution question, not a label.

`mobile/app.json`, `mobile/ios`: no "beta".

## Reviews

- **models-lead** (outlook behaviour): the ribbon loses its early-season "beta" cue. The honesty rule that matters (no win-loss numbers while `meta.beta`) is untouched, and so are bands and order.
- **design-lead** (UI): text-only change on three existing ribbons, with no token or layout change. **Approved 2026-10-31** at `390ab9ee`, with no code change. All three ribbons render uppercase through `type.label` (`CardImpactBlock.tsx:244`, `TeamReviewScreen.tsx:1343`, `LeagueSummaryScreen.tsx:3640`), so the source casing makes no difference. "PROJECTED" alone still reads as the caveat tag. The one fix was the casing in TestFlight row 1, now applied.

## Evidence

At the branch tip, from `mobile/` with `NODE_PATH` at another checkout's `node_modules` (same lock file, G-022):

| Command | Result |
|---|---|
| `node tests/check-no-beta-copy.js`, with the three code edits reverted (main's content) | exit 1. s1 FAIL with exactly the three inventory hits (`CardImpactBlock.tsx:183`, `LeagueSummaryScreen.tsx:2776`, `TeamReviewScreen.tsx:443`); 6 PASS |
| `node tests/check-no-beta-copy.js` | exit 0, 7 PASS (s1 0 hits; s2 31 `app.json` values; a1 allowlist; p1 335 files; p2–p4 the three ribbons) |
| The 21 guards that read the three files (`analytics-297-302`, `analytics-300`, `card-impact-order`, `guide-spotlight-tracking`, `home-destinations`, `home-hub`, `league-candidates-300`, `league-drill-in`, `mascot-ram`, `member-entered-marker`, `offer-prefill-330`, `outlook-bands`, `outlook-row-source`, `picks-subset-invariance`, `position-split-parity`, `team-review-depth`, `team-review`, `trade-first-card-events`, `win-now`, `window-composite`, `window-signals`) | all exit 0, 0 FAIL |
| `bash scripts/testid-lint.sh` | `testid-lint OK` |
| `tsc --noEmit`, on a scratch copy of `mobile/` with a borrowed `node_modules` | exit 0 |

**Sabotage** (applied, guard run, restored byte for byte):

| # | Sabotage | Red |
|---|---|---|
| 1 | CardImpactBlock's `'PROJECTED · BETA'` conditional back | s1 (only) |
| 2 | TeamReviewScreen's back | s1 (only) |
| 3 | `parts.push('beta')` back | s1 (only) |
| 4 | JSX text `Beta` in a `<Text>` (StandingsScreen) | s1 (only) |
| 5 | `` `${x} beta` `` in `utils/winNow.ts` | s1 (only) |
| 6 | `accessibilityLabel="Projected (beta)"` | s1 (only) |
| 7 | `app.json` `expo.name` "Fleeced Beta" | s2 (only) |
| 8 | `TESTFLIGHT_URL = 'itms-apps://'` | a1, the allowlist entry gone stale (only) |
| 9 | `testID="x.beta"` (negative control) | none: green, as intended |

p2–p4 prove the scan reaches each ribbon. They don't pin its exact copy: in runs 1 and 2 the put-back conditional still holds a `'PROJECTED'` literal. s1 is what catches the word.
