# Feature Scope — Landing platform options (Sleeper · ESPN · MFL at entry)

**Date:** 2026-08-26
**Entry point:** direct ask — "update the app entry page for new users to offer ESPN and MFL alongside Sleeper as the platforms we offer support for"
**Builder:** Claude session (worktree `app-entry-platform-options-3e16ac`)
**Operator sign-off on waivers:** pending — one waiver (§1c) surfaced in the session summary

---

## What ships

The mobile entry page (`SignInScreen`, `onboarding.landing` layout) gains a
three-chip platform row — **Sleeper · ESPN · MFL** — above the sign-in form.

- **Sleeper selected (default):** today's layout, unchanged to the pixel.
- **ESPN or MFL selected:** the Sleeper username form is replaced by a short
  explainer + the official **Sign in with Apple** button. Apple sign-in is the
  only session mint that doesn't need a Sleeper username (`POST /api/espn/link`
  and `/api/mfl/link` both `_require_session` — verified at
  `backend/server.py:23359` / `:25955`), so the platform choice rides the
  Apple flow as an **intent** and lands on `LeaguePicker` with the matching
  link sheet auto-opened (the existing `espnLink: true` #130 machinery; a new
  symmetric `mflLink: true`).

No backend route changes. No schema changes. Reuses: account-first Apple
sign-in (`auth.accounts`, live), LeaguePicker companion state (P0-5), the
ESPN/MFL link sheets, and the #266 transition-settled sheet auto-open.

Out of scope: Fleaflicker (flag dark), the web landing page, the flags-off
(P2.6 Apple-first) layout — reverting `onboarding.landing` also withdraws the
chip row, which is acceptable because that layout's primary portal is already
Apple and platform-agnostic.

## 1. Analytics scope

- [x] **(b) Existing events cover it** — the pre-auth funnel is unchanged:
  `signin_attempted` / `signin_succeeded` / `signin_failed {method: 'apple'}`
  fire on the Apple flow exactly as today, and `league_selected {platform}`
  already distinguishes the platform on the far side. What they answer: how
  many entries route through Apple and which platform the session lands on.
- [x] **(c) partial WAIVER — no chip-selection event.** A per-chip
  `landing_platform_selected` event would need a new taxonomy entry, and
  `backend/analytics_taxonomy.py` marks new client events/props default-deny
  pending a tracking-plan addendum. Rather than widen the taxonomy inside an
  entry-page change (the NULL-`platform` incident lesson), selection-level
  analytics is deferred; if the operator wants it, it's a one-event follow-up
  with its own tracking-plan row. **Surfaced to operator in the ship summary.**

## 2. Schema & flag scope

- Tables/columns: **none**
- Feature flags: **`landing.platform_options`** (new, client-only gate — no
  backend route reads it) → added to `config/features.json` (with comment) and
  `backend/feature_flags.py` `FLAG_KEYS`; documented in
  `docs/config-reference.md`. **Ships TRUE** — the operator asked for the
  surface directly; the flag is the deploy-free revert lever. Effective only
  while `onboarding.landing` is on. Graduation: delete the flag once the
  chip row survives a TestFlight cycle without complaint.
- Env vars / `model_config`: **none**

## 3. Evidence scope

- [x] **Structural guard:** `mobile/tests/check-landing-platform-options.js`
      (+ `npm run test:landing-platform-options`) — pins:
      1. chip row gated on `onboarding.landing` AND `landing.platform_options`;
      2. ESPN/MFL chips individually gated on `espn.link` / `mfl.link`, with a
         fallback that resets a de-flagged selection to Sleeper;
      3. Apple success branches forward the platform intent to BOTH
         `onSignedIn` and `onAccountSignedIn`;
      4. selecting a non-Sleeper chip advances guide step `s0.2` (the Analyst
         spotlight targets the username field the chip hides);
      5. RootNav maps intent → `{espnLink}` / `{mflLink}` params for both
         callbacks;
      6. LeaguePicker's MFL auto-open mirrors the #266 transition-settled
         deferral and the league-autoskip guard blocks on `autoOpenMflLink`.
- [x] **Unit tests:** none added — no backend behavior changed (flag-registry
      addition only; existing `backend/tests` cover flag loading generically).
- [x] **Code-walk proof:** in this doc's companion `code-walk.md` (written at
      build end, file:line-cited).
- [x] **Manual TestFlight checklist** (runtime proof matters — sheet
      presentation over a fresh navigation stack is exactly the #266 class):
      1. Fresh install (or sign out) → entry page shows **Sleeper · ESPN · MFL**
         chips above the username field; Sleeper selected; form identical to
         current build.
      2. Tap **ESPN** → username field/hint/button replaced by explainer +
         Sign in with Apple; no Analyst spotlight left floating.
      3. Complete Apple sign-in → lands on the league list with the **ESPN
         link sheet already open** (not wedged, not absent — #266 regression
         check). Cancel the sheet → normal picker/companion state beneath.
      4. Back on entry (sign out), tap **MFL** → same flow, **MFL sheet** opens.
      5. Tap **Sleeper**, type a valid username → sign-in works exactly as
         the current build (no chip interference).
      6. With one Sleeper league on the account, run step 4 again → the MFL
         sheet must open **instead of** the single-league auto-skip.
- `testID`s added: `signin.platform-sleeper|espn|mfl` (template
  `signin.platform-${p}`), `signin.platform-panel`, `signin.platform-apple-btn`,
  `signin.platform-unavailable`. None referenced by retained flows → no
  allowlist entries needed; `testid-lint.sh` run before ship.

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a | no route added/changed |
| `living-memory/LLD.md` | n/a | no schema/route/invariant convention shifted — new nav param follows the existing #130 `espnLink` convention |
| `docs/architecture.md` | n/a | no module wiring change; SignIn → LeaguePicker edge already exists |
| `living-memory/HLD.md` | n/a | no architecture shift |
| `docs/cross-client-invariants.md` | n/a | no shared constants/enums/colors added; chip labels reuse existing platform names |
| `docs/glossary.md` | n/a | no new domain term |
| ADR or `DECISIONS.md` | updated | new D-entry: platform choice at entry rides Apple sign-in as an intent param (not a platform-native auth at entry) |
| `docs/config-reference.md` | updated | `landing.platform_options` flag row |

## 5. Ship gate declaration

- **CI green:** `pytest backend/tests` + `npx tsc --noEmit` + `testid-lint.sh`
  run locally before push; CI on the PR sha.
- **Evidence recorded:** `living-memory/TEST_LEDGER.md` entry at ship.
- **TestFlight verification:** checklist in §3 — operator runs it on the next
  build that carries this change; outcome logged in TEST_LEDGER.
- Express lane declared by the operator? **No** — full gates.
