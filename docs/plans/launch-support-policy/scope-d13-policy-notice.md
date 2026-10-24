# Feature Scope — D-13: the in-app policy-change notice (the launch what's-new line)

**Date:** 2026-10-23
**Entry point:** D-13 (prd.md §9), decided by Product (`head-product`, 2026-10-23) on `legal-lead`'s R18; source `docs/plans/org-bringup/bizops-banner-use-cases.md` §0 item 1 and §B6, and `in-app-banner-product.md` (org-bringup worktree, untracked)
**Builder:** `onboarding-eng` (build, in the 11-06 binary, under `head-eng`). Spec by `launch-onboarding-pm-4` for `onboarding-pm`. Words: `legal-lead`, via `head-bizops`.
**Operator sign-off on waivers:** pending. W-D13-1 to W-D13-3 are listed in [prd.md §9](prd.md#9-decisions-needed); `head-product` takes them to the operator.
**Gate 1 (head-product acceptance of this block):** pending.

The decision, the verified facts and Product's calls on the limits:
[prd.md §7.8](prd.md#78-d-13-the-in-app-policy-change-notice). In short: `legal-lead`'s R18 rules the
policy change material, so it is announced in the app (privacy §9 promises it, `web/privacy.html:273-274`
at `712dcbed`). The banner ships after launch, so the launch vehicle is the **existing what's-new tip**
(`mobile/src/hooks/useWhatsNew.ts`). The release's what's-new slot carries the policy notice, not a
feature note.

**Requirements** (full text and facts in prd.md §7.8):

- **D13-R1.** One `WHATS_NEW` entry keyed to the **release binary's app.json `version`**, set in the
  same change that bumps the version, with `route: 'SettingsAbout'`. Tapping opens Settings › Help &
  about (where the policy rows live) and dismisses it. It shows once per version.
- **D13-R2.** The headline is `legal-lead`'s wording: **wording: legal-lead (in progress via
  head-bizops)**. The template from bizops B6 is "We've updated our Privacy Policy and Terms": one line,
  no period (`useWhatsNew.ts:26`).
- **D13-R3.** Notice, not consent: never blocking, no Accept button, dismissible.
- **D13-R4.** The stale `'1.9.1'` placeholder (`useWhatsNew.ts:34-38`) is harmless, because it never
  matches the release version. Recommended: remove it in the same change.
- **D13-R5.** The release slot carries no feature note (Product's call).
- **D13-R6 (M-a).** The tip stays until it is tapped or dismissed, with no silent expiry. At
  `712dcbed` this already holds (prd.md §7.8.1); the build keeps it so.
- **D13-R7 (M-b).** The policy pages carry their new effective date (M7-R4, M7-AC3; today
  "July 19, 2026", `web/privacy.html:71`).
- **D13-R8 (M-c).** The TestFlight "What to Test" note for the last TestFlight build carries
  `legal-lead`'s release-notes line; `app-manager` formats it. The first App Store **update**'s What's
  New carries it too (a first release has no What's New field).
- **Option, not the default:** if `legal-lead` says a League-only tip isn't enough notice, also show
  it on the Home hub.

---

## 1. Analytics scope

- [ ] **(a) New events specced:** none.
- [ ] **(b) Existing events cover it:** taps only. A tap already fires
  `league_home_action_tapped` with `action: 'whats_new'` (`mobile/src/screens/LeagueScreen.tsx:469-470`,
  `:526`), which is registered (`backend/analytics_taxonomy.py:127`, `:1108`). Nothing records that
  the tip was shown.
- [x] **(c) WAIVED — no new events because:** the notice is one line in an existing surface, and the
  tap is already measured (b). `whats_new_shown` and `whats_new_tapped` are not registered at
  `712dcbed` (no `git grep` match). They are optional per bizops §10 (`bizops-banner-use-cases.md:603`).
  If they are added later, they need `analytics-lead`'s grant, and they are registered in
  `backend/analytics_taxonomy.py` and classified in `analytics_queries.NON_INTENT_EVENTS` in the same
  commit as the emitter. (Waiver **W-D13-1**.)

## 2. Schema & flag scope

- New/changed tables or columns: **none.** → `docs/data-dictionary.md` n/a.
- New/changed feature flags: **none.** `ux.whats_new` is already `true` (`config/features.json:175`).
  (Waiver **W-D13-2**.) **Flagged:** `legal-lead`'s R26.1 asks that the tip not appear before the new
  text is live, preferably by holding `ux.whats_new` false until the 11-09 pages deploy (prd.md
  §7.8.4). That would use the existing flag as a sequencing lever, not add one; `head-product` decides.
- New env vars / `model_config` keys: **none.**
- **Storage:** the existing AsyncStorage key `ftf_whats_new_seen_version` (`useWhatsNew.ts:41`). No new
  key.

## 3. Evidence scope

D-056: no simulator, no Maestro, no screen captures.

- [x] **Structural guard:** a new `mobile/tests/check-whats-new.js` (with
  `"test:whats-new": "node tests/check-whats-new.js"` in `mobile/package.json`), or an existing
  `check-*.js` if `head-eng` prefers. CI runs every `mobile/tests/check-*.js`
  (`.github/workflows/ci.yml:42-48`). It pins:
  1. `WHATS_NEW` has an entry whose key equals `mobile/app.json` `expo.version` (`1.21.4` at
     `712dcbed`, `app.json:5`; the release bump moves both together).
  2. That entry's `route === 'SettingsAbout'`.
  3. Its `headline` equals `legal-lead`'s final text exactly, with no trailing period.
  4. If D13-R4 is taken: no other entry remains.
- [ ] **Unit tests:** WAIVED, see below.
- [x] **Code-walk proof** (file:line at `712dcbed`; the builder re-walks it against the built files):
  1. **Hook.** `useWhatsNew()` (`useWhatsNew.ts:49-88`) reads `ux.whats_new` (`:50`), loads
     `ftf_whats_new_seen_version` (`:55-69`), and returns `WHATS_NEW[APP_VERSION]` while the stored
     version differs from the running one (`:79-85`). `APP_VERSION` is `Constants.expoConfig.version`
     (`:42`).
  2. **Render.** `LeagueScreen` calls the hook (`LeagueScreen.tsx:115`) and renders a `CoachMark`
     with the headline (`:521-531`). `LeagueScreen` is the League stack's `LeagueHome` sub-route
     (`mobile/src/navigation/TabNav.tsx:586-592`), opened from the "League home" row on the tab's root
     (`LeagueSummaryScreen.tsx:1664`) or from Rank (`RankScreen.tsx:430`).
  3. **Tap.** The whole `CoachMark` is one `Pressable` whose `onPress` is `onDismiss`
     (`mobile/src/components/CoachMark.tsx:18-32`). It logs `league_home_action_tapped` (`whats_new`),
     calls `dismiss()`, then navigates to `route` (`LeagueScreen.tsx:525-529`).
  4. **Navigate.** `SettingsAbout` is a root-stack route (`RootNav.tsx:698-701`); the navigate from the
     tab stack reaches it through the parent navigator (verify at build). Its `AboutSection` holds the
     Privacy Policy and Terms rows (`AboutSection.tsx:82`, `:91`).
  5. **Dismiss.** `dismiss()` stores the running version (`useWhatsNew.ts:71-77`), so the tip doesn't
     return for that version. Nothing else calls it: no timer and no render-time dismiss (M-a).
- [x] **Manual TestFlight checklist** (operator; log the result in `living-memory/TEST_LEDGER.md`):
  1. Install the **previous** TestFlight build, then update to the release build (an updated install,
     not a fresh one).
  2. Open the League tab, then **League home**. Expected: the policy line shows, once, with legal's
     text. (It is on League home, not on the tab's landing screen; prd.md §7.8.1.)
  3. Tap it. Expected: Settings › Help & about opens, with the Privacy Policy and Terms rows.
  4. Go back to League home, then force-quit and relaunch. Expected: the line doesn't show again.
- [x] **WAIVED because:**
  - **W-D13-3 (pytest):** no backend code.
- `testID`s added/renamed: **none.** The tip keeps `league.whats-new` (`LeagueScreen.tsx:523`).

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` (any route added/renamed/removed/contract-changed) | n/a | No route or contract change. |
| `docs/data-dictionary.md` | n/a | No schema change. |
| `living-memory/LLD.md` (schema/route/invariant *conventions* shifted) | n/a | The hook's contract (`useWhatsNew.ts:8-23`) is unchanged. |
| `docs/architecture.md` (module wiring / data flow changed) | n/a | No module or data-flow change. |
| `living-memory/HLD.md` (architecture genuinely shifted) | n/a | No architecture change. |
| `docs/cross-client-invariants.md` (shared constants/enums/colors) | n/a | Mobile only. The web has no what's-new surface. |
| `docs/glossary.md` (new domain term) | n/a | No new term. |
| ADR or `DECISIONS.md` entry (non-obvious choice made) | **update at build** | Record that the launch policy notice rides the what's-new tip and that the release slot carries no feature note (Product's call), with the banner as the vehicle for later changes. Next ID = max `D-` + 1 at build time. |
| `mobile/src/hooks/CLAUDE.md` | **check at build** | The `useWhatsNew.ts` row (`:10`) says the anchor is "in LeagueScreen"; it stays accurate. Update it only if the Home-hub option is taken. |

## 5. Ship gate declaration

- **Rides in the 11-06 binary.** The entry's key is the release version, set in the version-bump
  change.
- **Timing:** see the R26.1 flag in §2. The tip should not say "We've updated" while the links still
  open the old pages (`head-product` decides how).
- **CI green:** `backend-tests` + `mobile-typecheck` (runs `tsc --noEmit` and every
  `mobile/tests/check-*.js`, including the new guard) + `web-structure` + `maestro-testid-lint`
  (testid-lint only), all passing on the pushed sha.
- **Evidence recorded:** a `living-memory/TEST_LEDGER.md` entry with the guard result, the code-walk
  and the TestFlight run. `githooks/pre-push` still checks the retired simulator marker; under D-056
  push with `FTF_SKIP_SIM_GATE=1` and name this evidence instead.
- **Still open:** `legal-lead` confirms Product's two calls on the limits (prd.md §7.8.3), via
  `head-bizops`, and supplies the final headline and release-notes line.
- **Gates still owed:** `head-product`'s gate-1 acceptance of this block; the operator's sign-off on
  W-D13-1 to W-D13-3.
- Express lane declared by the operator? **No.** Full gates.
