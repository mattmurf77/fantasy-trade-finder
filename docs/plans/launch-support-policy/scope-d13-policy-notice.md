# Feature Scope — D-13: the in-app policy-change notice (the launch what's-new line)

**Date:** 2026-10-23
**Entry point:** D-13 (prd.md §9), decided by Product (`head-product`, 2026-10-23) on `legal-lead`'s R18; source `docs/plans/org-bringup/bizops-banner-use-cases.md` §0 item 1 and §B6, and `in-app-banner-product.md` (org-bringup worktree, untracked)
**Builder:** `onboarding-eng` (build, in the 11-06 binary, under `head-eng`). Spec by `launch-onboarding-pm-4` for `onboarding-pm`. Words: `legal-lead`, via `head-bizops`.
**Operator sign-off on waivers:** signed 2026-10-24 (operator, in head-product's session; quoted verbatim: "I sign off on #354's D-13 waivers (W-D13-1 to W-D13-3)."). Covers W-D13-1, W-D13-2 and W-D13-3.
**Gate 1 (head-product acceptance of this block):** accepted 2026-10-24 (P39) at 34479ab0.

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
- **D13-R2.** The headline is `legal-lead`'s final text (R26.1, `leads/legal-lead.md:1255` in the
  org-bringup worktree; legal's own wording, so "we" is allowed):
  `We've updated our Privacy Policy and Terms of Use. Tap to read them` (67 characters). The hook's contract is one line with no period
  (`useWhatsNew.ts:26`), so there is **no trailing period**; the inner ". " is legal's.
- **D13-R3.** Notice, not consent: never blocking, no Accept button, dismissible.
- **D13-R4.** The stale `'1.9.1'` placeholder (`useWhatsNew.ts:34-38`) is harmless, because it never
  matches the release version. Recommended: remove it in the same change.
- **D13-R5.** The release slot carries no feature note (Product's call).
- **D13-R6 (M-a).** The tip stays until it is tapped or dismissed, with no silent expiry. At
  `712dcbed` this already holds (prd.md §7.8.1); the build keeps it so.
- **D13-R7 (M-b).** The policy pages carry their new effective date (M7-R4, M7-AC3; today
  "July 19, 2026", `web/privacy.html:71`).
- **D13-R8 (M-c).** Two release-notes lines, both `legal-lead`'s (R26.1, `leads/legal-lead.md:1257-1258`):
  - **First App Store update's What's New:** `Updated Privacy Policy and Terms of Use. Read them any time in Settings › Help & about.` (87 characters). A first App Store release has
    no What's New field (`leads/app-manager-app-store-submission.md:268`, E3b, "[verify on screen]";
    Product's accepted call, prd.md §7.8.3), so this line goes in the first **update**, not in v1.
  - **TestFlight "What to Test" note** for the last TestFlight build (`app-manager` formats it):
    `The Privacy Policy and Terms of Use are updated. Check the League tab shows the notice once, and that tapping it opens Settings › Help & about with both links.`
  - **Flagged, not edited:** the tip renders on League home (`LeagueScreen`, the `LeagueHome`
    sub-route, `TabNav.tsx:575-592`), one tap below the League tab's root, so "the League tab" in
    legal's line is approximate. `legal-lead` / `app-manager` may adjust the tester wording.
- **Legal's placement ruling (R26.2, `leads/legal-lead.md:1264-1276`, 2026-10-23).** A once-per-version
  inline tip satisfies Privacy §9 and Terms §8, so League-home-only placement is fine. The **Home-hub
  option stays an option only**, not a requirement. Two **[PRO]** notes, neither blocking:
  - **(a)** League-only reach is a nice-to-have, not a requirement.
  - **(b)** Enforceability of the changed terms on existing users is review item #15; a click-through
    isn't required for launch.

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
  (Waiver **W-D13-2**, signed 2026-10-24.) **Decided (`head-product`, P39, 2026-10-24):** the existing
  `ux.whats_new` flag is the sequencing lever for `legal-lead`'s R26.1 timing requirement, with no new
  flag, so W-D13-2 stands. The two steps are in §5 and prd.md §7.8.4.
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
  3. Its `headline` is exactly equal to `We've updated our Privacy Policy and Terms of Use. Tap to read them` (strict equality against D13-R2's string), and it
     has no trailing period.
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
- [x] **Manual TestFlight checklist** (operator; log the result in `living-memory/TEST_LEDGER.md`).
  It can run only after flip (ii) in §5, because until then `ux.whats_new` holds the tip back
  (inference: the hook reads the flag at `useWhatsNew.ts:50`):
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
- **Flag sequencing** (`head-product`, P39, 2026-10-24). Use the existing `ux.whats_new` flag, with no
  new flag (W-D13-2 stands), so the tip never points to the old Privacy Policy and Terms text (legal's
  R26.1 condition, `leads/legal-lead.md:1259-1262`). Two steps:
  - **(i)** `ux.whats_new` **OFF in prod before the release build reaches TestFlight testers (~11-07).**
  - **(ii)** `ux.whats_new` **ON once the new Privacy Policy and Terms pages are live (~11-09),**
    ideally in the same deploy.

  Both flips happen on the operator's word, in `release-lead`'s session (Launch Desk OA-9). Legal's
  acceptable fallback, if (i) can't be sequenced: a gap of about two days for TestFlight testers only
  (a small group); public users can't see it early, because App Store users get the binary only on 11-18.
- **CI green:** `backend-tests` + `mobile-typecheck` (runs `tsc --noEmit` and every
  `mobile/tests/check-*.js`, including the new guard) + `web-structure` + `maestro-testid-lint`
  (testid-lint only), all passing on the pushed sha.
- **Evidence recorded:** a `living-memory/TEST_LEDGER.md` entry with the guard result, the code-walk
  and the TestFlight run. `githooks/pre-push` still checks the retired simulator marker; under D-056
  push with `FTF_SKIP_SIM_GATE=1` and name this evidence instead.
- **Still open:** nothing on legal's side (R26.1 text and R26.2 ruling are final; D13-R2, D13-R8). The
  tester wording of the TestFlight line is flagged in D13-R8 and may be adjusted by `legal-lead` /
  `app-manager`. The release version number is set at build.
- **Gates still owed:** none on this block. Gate 1 was accepted (P39) and W-D13-1 to W-D13-3 were
  signed on 2026-10-24 (see the header).
- Express lane declared by the operator? **No.** Full gates.
