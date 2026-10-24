# Feature Scope — Q6: the `n23` tour line ("We never see your password")

**Date:** 2026-10-23
**Entry point:** operator decision Q6 (2026-10-23) / legal-lead LEG-S15
**Builder:** `onboarding-eng` (build, under `head-eng`). Spec by `launch-onboarding-pm-3` for `onboarding-pm`.
**Operator sign-off on waivers:** signed 2026-10-23 (operator, in head-product's session; quoted verbatim: "I sign off on #354's new waivers (W-Q6-1 to W-Q6-4, W-FAQ-1 to W-FAQ-3).").
**Gate 1 (head-product acceptance of this block):** accepted 2026-10-23 (P37).

The decision, the facts and the two strings: [prd.md §6.8](prd.md#68-q6-tour-line). **Status:
approved (Q6, operator 2026-10-23).** The operator answered "Q6 tour line: Yes" on the 2026-10-23
form, relayed by `head-product`. `legal-lead` (LEG-S15) found "Passwords never leave your phone"
literally false and supplied the replacement.

| Field of beat `n23` | `mobile/src/components/analystScript.ts` at `712dcbed` | New |
|---|---|---|
| `line` | `:635` Sending goes straight to your league. Passwords never leave your phone. | Sending goes straight to your league. We never see your password. |
| `degradeLine` | `:636` Sending a trade goes straight to your league. Passwords stay on your phone. | Sending a trade goes straight to your league. We never see your password. |

The `line` is `legal-lead`'s exact text. The `degradeLine` applies the same operator-approved
substitution, as `legal-lead` specifies. `n23b`, the off-Sleeper sibling, makes no password claim
and is unchanged.

---

## 1. Analytics scope

- [ ] **(a) New events specced:** none.
- [ ] **(b) Existing events cover it:** —
- [x] **(c) WAIVED — no analytics needed because:** two strings change inside an existing beat, and
  no user action is added. The beat's `adoptionEvent` (`sleeper_send_attempted`,
  `analystScript.ts:639`) and the tour's existing events are unchanged. (Waiver **W-Q6-1**.)

## 2. Schema & flag scope

- New/changed tables or columns: **none.** → `docs/data-dictionary.md` n/a.
- New/changed feature flags: **none.** (Waiver **W-Q6-2**.) The beat already sits behind the tour's
  two flags, which this change doesn't touch: `startCalcTour` returns early unless both are on
  (`mobile/src/utils/calcTour.ts:472`), and both are `false` in `config/features.json` at `712dcbed`
  (`onboarding.guided_avatar` `:134`, `onboarding.guide_v2` `:137`). So the new line ships in the
  11-06 binary, but no user sees it until the tour is lit again.
- New env vars / `model_config` keys: **none.**

## 3. Evidence scope

D-056: no simulator, no Maestro, no screen captures.

- [x] **Structural guard:** extend `mobile/tests/check-guide-script.js` §9 ("the n23 pair",
  `:425-447`), which already executes the shipped builders. Add:
  - **9d.** `S.n23().line` and `S.n23().degradeLine` each contain `We never see your password`.
  - **9e.** Neither matches `/never leave your phone|stay on your phone/i`.
  - **9f.** `S.n23b().line` and `S.n23b().degradeLine` carry no password claim. Today 9b checks
    `line` only; this extends it to `degradeLine`.
  - The existing pins keep passing with the new text, and the build re-runs them: 9a needs
    `/password/i` in `n23`'s `line`; 2b and 2c cap a `cta` beat's `line` and `degradeLine` at 16 words
    (`:203`, `:214`, `:229`); the new strings run 11 and 13 words.
  - `npm run test:guide-script`; CI runs every `mobile/tests/check-*.js` in the `mobile-typecheck` job
    (`.github/workflows/ci.yml:42-48`).
- [ ] **Unit tests:** WAIVED, see below.
- [x] **Code-walk proof** (file:line at `712dcbed`; the builder re-walks it against the built files):
  1. **Beat.** `n23` is built at `analystScript.ts:632-640`: `advance: 'cta'`, target
     `trades.send-btn`, `line` `:635`, `degradeLine` `:636`. Its comment (`:626-631`) explains why the
     password sentence lives on the Sleeper beat only.
  2. **Sibling.** `n23b` (`:642-655`) has `line` `:646` and `degradeLine` `:647`, with no password
     claim. Unchanged.
  3. **Selection.** `beatIdFor` (`calcTour.ts:232-236`) returns `n23` only when
     `resolveSendPlatform(...) === 'sleeper'` (`:235`); MFL and ESPN leagues get `n23b`. So the new
     sentence only ever shows on a Sleeper league.
  4. **Render.** `AnalystGuide.tsx:284` shows `degradeLine` when the spotlight is degraded, otherwise
     `line`. `n23` has no `lineRam`, so the mascot flag doesn't change which string shows.
  5. **Gate.** `startCalcTour` returns `false` unless `guidedAvatarActive() && guideV2Active()`
     (`calcTour.ts:472`; readers at `mobile/src/state/useGuide.ts:198-209`), and both flags are
     `false` at `712dcbed`. The beat is unreachable in today's config.
  6. **No pinned copy.** Nothing pins the old sentence. It appears only in comments
     (`calcTour.ts:229`, `check-guide-script.js:427`) and in `mobile/src/utils/CLAUDE.md:37`, all
     updated at build (§4). `check-calc-tour.js` pins `n23`'s target and screen only (`:370-371`,
     `:422`). The historical review `docs/feedback/items/384-calc-finder-merge/review-2026-08-22-e2e.md:77`
     also quotes it; it is history and stays.
- [ ] **Manual TestFlight checklist:** WAIVED, see below.
- [x] **WAIVED because:**
  - **W-Q6-3 (TestFlight checklist):** the tour is dark (§2), so no build can put the beat on a
    tester's screen. Runtime proof isn't possible; the structural assertion and the code-walk are the
    evidence. **Lapses if either tour flag is lit.** A TestFlight step is then owed: on a Sleeper
    league, run the tour to the send beat; it reads "Sending goes straight to your league. We never
    see your password."
  - **W-Q6-4 (pytest):** no backend code.
- `testID`s added/renamed: **none.**

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` (any route added/renamed/removed/contract-changed) | n/a | No route or contract change. |
| `docs/data-dictionary.md` | n/a | No schema change. |
| `living-memory/LLD.md` (schema/route/invariant *conventions* shifted) | n/a | No convention change. |
| `docs/architecture.md` (module wiring / data flow changed) | n/a | No module or data-flow change. |
| `living-memory/HLD.md` (architecture genuinely shifted) | n/a | No architecture change. |
| `docs/cross-client-invariants.md` (shared constants/enums/colors) | n/a | The beat lives in one client. |
| `docs/glossary.md` (new domain term) | n/a | No new term. |
| ADR or `DECISIONS.md` entry (non-obvious choice made) | n/a | An operator copy decision on legal advice, recorded in [prd.md §9](prd.md#9-decisions-needed); no design choice. |
| `mobile/src/utils/CLAUDE.md` | **update at build** | `:37` quotes "Passwords never leave your phone" as the reason `beatIdFor` picks `n23b` off Sleeper; restate it with the new sentence. |
| Code comments (code, not docs) | **update at build** | `calcTour.ts:228-231` (quotes the old sentence); `check-guide-script.js:425-430` (the §9 header comment); re-read the `n23` comment at `analystScript.ts:626-631`. |

## 5. Ship gate declaration

- **Rides in the 11-06 binary** with BL-10 (prd.md §8).
- **CI green:** `backend-tests` + `mobile-typecheck` (runs `tsc --noEmit` and every
  `mobile/tests/check-*.js`, including the extended `check-guide-script.js`) + `web-structure` +
  `maestro-testid-lint` (testid-lint only), all passing on the pushed sha.
- **Evidence recorded:** a `living-memory/TEST_LEDGER.md` entry with the `check-guide-script.js`
  counts and the code-walk. `githooks/pre-push` still checks the retired simulator marker; under
  D-056 push with `FTF_SKIP_SIM_GATE=1` and name this evidence instead.
- **TestFlight verification:** none while the tour is dark (W-Q6-3).
- **Gates still owed:** none on this block. Gate 1 was accepted and W-Q6-1 to W-Q6-4 were signed on
  2026-10-23 (P37; see the header).
- Express lane declared by the operator? **No.** Full gates.
