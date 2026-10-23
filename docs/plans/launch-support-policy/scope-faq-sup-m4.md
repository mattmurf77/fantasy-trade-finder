# Feature Scope — SUP-M4: the FAQ rewrite for launch

**Date:** 2026-10-23
**Entry point:** SUP-M4 / marketing-lead launch copy batch / P36
**Builder:** `onboarding-eng` (build, under `head-eng`). Spec by `launch-onboarding-pm-3` for `onboarding-pm`.
**Operator sign-off on waivers:** **pending.** W-FAQ-1 to W-FAQ-3 are listed in [prd.md §9](prd.md#9-decisions-needed). The 2026-10-22 sign-off covers only the seven waivers it names, not these.
**Gate 1 (`head-product` acceptance of this block):** pending.

Requirements, ship order and acceptance criteria: [prd.md §7b](prd.md#7b-faq-sup-m4). The text to
paste, verbatim, with marketing's build notes: [faq-copy.md](faq-copy.md). Words: `marketing-lead`,
except Q16 and Q17, which are `legal-lead`'s (R10 wording). The meaning changes are pending operator
§6 (block I).

---

## 1. Analytics scope

- [ ] **(a) New events specced:** none.
- [ ] **(b) Existing events cover it:** —
- [x] **(c) WAIVED — no analytics needed because:** `web/faq.html` is a static page that loads no
  script at `712dcbed`, so it has no events SDK, and the rewrite adds no user action worth measuring.
  (Waiver **W-FAQ-1**.)

## 2. Schema & flag scope

- New/changed tables or columns: **none.** → `docs/data-dictionary.md` n/a.
- New/changed feature flags: **none** (Waiver **W-FAQ-2**), **unless `head-eng` picks a flag for the
  11-18 flip.** Q3's App Store line ships on 11-13 as a pre-launch variant and flips on 11-18
  (prd.md FAQ-R3). The mechanism is `head-eng`'s: a manual deploy on 11-18, a flag, or the same
  switch as #348's `IOS_INSTALL_URL` (not on `main` at `712dcbed`). **If it uses a flag or an env
  var, this section must be amended before build** to name it, with its default, the flip date and
  the rollback, and `docs/config-reference.md` gains the row. W-FAQ-2 then lapses.
- New env vars / `model_config` keys: **none** (same exception).
- **Copy is legal-adjacent, not legal text:** Q16 and Q17 carry `legal-lead`'s R10 wording. The page
  ships unflagged under ADR-008's exception for doc/legal copy
  (`docs/adr/adr-008-teardown-remediation-wave.md:21-23`).

## 3. Evidence scope

- [x] **Structural guard (web):** new `FAQ-*` assertions in `qa/web/check_web_structure.py` (CI job
  `web-structure`, `.github/workflows/ci.yml:50-62`), beside the `HYG-*` checks (`:280-305`),
  sharing P28's `SUPPORT_EMAIL` constant. `faq.html` is already in the checker's
  `PAGES` list (`:29`), so its SEO and a11y checks keep applying.
  - `FAQ-mailto`: every `fleecedapp@gmail.com` in `faq.html` sits inside
    `<a href="mailto:fleecedapp@gmail.com">`, written with an ASCII `@`; no U+FF20 anywhere on the
    page.
  - `FAQ-no-review-tags`: no `[APP STORE URL]` placeholder and no bracketed review tag in the
    published page. The R22 revision's tags are listed in [faq-copy.md](faq-copy.md)'s header
    (`[new]`, `[R10 …]`, `[R22.1 edit …]`, `[R22.3 / R22.4 timing]`, `[goes live only at release …]`);
    for example the regex `\[(?:new|APP STORE URL|goes live[^\]]*|R\d[^\]]*)\]`.
  - `FAQ-no-testflight` (active from the 11-18 flip): no "TestFlight" on the page. Before the flip it
    depends on the pre-launch variant, which is still a copy gap; the assertion turns on with the
    flip.
  - `FAQ-extension-link`: the extension link's `href` in `faq.html` equals the release link in
    `index.html` (today
    `https://github.com/mattmurf77/fantasy-trade-finder/releases/tag/extension-v0.1.1`,
    `web/index.html:170`). The checker reads both pages, so a new release forces both to move.
  - `FAQ-no-speed`: the "I AM SPEED" question is gone.
- [ ] **Mobile structural guard:** WAIVED, see below.
- [ ] **Unit tests:** WAIVED, see below.
- [ ] **Code-walk proof:** not used; there is no behavior to trace. The answers' factual claims carry
  `marketing-lead`'s own claims audit (§5c of the untracked source, not copied here). Two claims stay
  open until confirmed: Q9's K-factors (pending `model_config` confirmation, FAQ-R6) and the
  extension release (eng confirms at build, FAQ-R5).
- [x] **Manual read-through** (operator or `onboarding-eng`, after each deploy to Render, on desktop
  Safari and iOS Safari):
  1. **11-13, before the flip.** Open `/faq.html`. Expected: the new questions, in order; the first
     item is open; Q3 shows the pre-launch variant, with no "App Store" claim; no bracketed tag or
     placeholder anywhere.
  2. Tap each `fleecedapp@gmail.com` (Q17, Q18, footer). Expected: Mail opens addressed to
     `fleecedapp@gmail.com`.
  3. Tap "Privacy Policy" and "Terms of Use" in the text and the footer. Expected: the **new** M7
     pages load (they deploy with or before the FAQ).
  4. Tap Q3's extension link. Expected: the GitHub release page that `index.html`'s "Install the
     extension" link opens.
  5. In the app, Settings → Help & about → Help & FAQ. Expected: the new page opens
     (`mobile/src/screens/settings/sections/AboutSection.tsx:64-67`).
  6. **11-18, after the flip.** Reload. Expected: Q3 reads "On iPhone: the Fleeced app on the App
     Store", the link opens the App Store listing, and the page has no "TestFlight".
- [ ] **Manual TestFlight checklist:** WAIVED, see below.
- [x] **WAIVED because** (Waiver **W-FAQ-3**): web-only text on one static page. There is no mobile
  code, so no `mobile/tests/check-*.js` guard and no TestFlight checklist; the app's Help & FAQ row
  only opens the web URL, which step 5 covers. There is no backend code, so no pytest.
- `testID`s added/renamed: **none.**

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` (any route added/renamed/removed/contract-changed) | n/a | No route change. |
| `docs/data-dictionary.md` | n/a | No schema change. |
| `living-memory/LLD.md` (schema/route/invariant *conventions* shifted) | n/a | No convention change. |
| `docs/architecture.md` (module wiring / data flow changed) | n/a | No module or data-flow change. |
| `living-memory/HLD.md` (architecture genuinely shifted) | n/a | No architecture change. |
| `docs/cross-client-invariants.md` (shared constants/enums/colors) | **shared row** | The "Support contact address" section added by P28/BL-10 lists the web pages the checker holds to `SUPPORT_EMAIL`; `faq.html` joins them. |
| `docs/glossary.md` (new domain term) | n/a | No new term. |
| ADR or `DECISIONS.md` entry (non-obvious choice made) | n/a | The ship order and launch-day variant are product calls (P36), recorded in [prd.md §9](prd.md#9-decisions-needed). |
| `docs/config-reference.md` | **only if** | Only if `head-eng`'s flip mechanism uses a flag or env var (§2). |
| `docs/runbook.md` | **only if** | Only if the 11-18 flip is a manual step: who flips it, when, how to verify (step 6) and how to roll back. |
| `web/CLAUDE.md` | n/a | The `faq.html` row (`:17`, "FAQ") stays accurate. |

## 5. Ship gate declaration

- **Live by Fri 2026-11-13,** in the same deploy as the new privacy and terms pages (M7) or after
  them, never before (FAQ-R2, per P36). **Q3 flips on Wed 2026-11-18** (FAQ-R3). Marketing's R22
  revision says the FAQ goes live only at release (R22.5); that conflict is flagged for
  `head-product` (prd.md §9). If R22.5's order is chosen, the 11-13 read-through (step 1) and the
  pre-launch Q3 gap drop out.
- **CI green:** `backend-tests` + `mobile-typecheck` + `web-structure` (with the `FAQ-*` assertions)
  + `maestro-testid-lint` (testid-lint only), all passing on the pushed sha.
- **Evidence recorded:** a `living-memory/TEST_LEDGER.md` entry naming the checker run (pass count
  before and after) and both read-throughs (11-13 and 11-18). Push with `FTF_SKIP_SIM_GATE=1` (D-056
  standing posture) and name that evidence.
- **Copy gates, before 11-13:** the operator has approved marketing §6 block I; `legal-lead` has
  approved Q16 and Q17; Q9's K-factors are confirmed; `marketing-lead` has supplied the pre-launch
  Q3 variant (only under P36's order) and placed the pricing line; eng has confirmed the extension
  release; `head-eng` has confirmed Q15's contrarian-score scope (FAQ-R10).
- **Gates still owed:** `head-product`'s gate-1 acceptance of this block; the operator's sign-off on
  W-FAQ-1 to W-FAQ-3.
- Express lane declared by the operator? **No.** Full gates.
