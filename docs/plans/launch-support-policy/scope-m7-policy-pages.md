# Feature Scope — M7: privacy and terms pages for launch

**Date:** 2026-10-20
**Entry point:** direct ask: `head-product` App Store launch-readiness review (2026-10-20), item M7; operator decision BL-2 (support address)
**Builder:** `launch-onboarding-pm-1` for `onboarding-pm` (spec only). Build later: `onboarding-eng` pastes `legal-lead`'s final text, nothing else.
**Operator sign-off on waivers:** **pending.** Waivers W-M7-1 and W-M7-2 are listed in [prd.md §9](prd.md#9-decisions-needed) for `head-product` to surface before build.

Requirements, the policy claims checklist, the collection-surface list, the wording inventory and
the terms topics: [prd.md §7](prd.md#7-m7-privacy-and-terms-pages). Ownership: `onboarding-pm` owns the
product side of `web/privacy.html` and `web/terms.html` (P11) and the data lifecycle (P12); every word
on both pages is `legal-lead`'s (via `head-bizops`); the data inventory the policy is reconciled
against is `analytics-lead`'s; the App Privacy labels (M6(b)) are answered by `legal-lead` and
submitted by `app-manager` / `release-lead`.

---

## 1. Analytics scope

- [ ] **(a) New events specced:** none.
- [ ] **(b) Existing events cover it:** —
- [x] **(c) WAIVED — no analytics needed because:** these are static legal pages. Neither page loads
  the web analytics SDK (`web/js/events.js` isn't referenced from either file), and the change adds no
  user action worth measuring. The policy's description of analytics is the subject of the change,
  not a new emitter. (Waiver **W-M7-1**.)

## 2. Schema & flag scope

- New/changed tables or columns: **none.** → `docs/data-dictionary.md` n/a. If reconciliation shows
  the policy is right and the data-dictionary wrong (or the reverse), `analytics-lead` raises it
  separately; this change edits only the two pages.
- New/changed feature flags: **none.** Legal copy ships unflagged: "a wrong document has no rollback
  value" (ADR-008's exception, `docs/adr/adr-008-teardown-remediation-wave.md:21-23`).
- New env vars / `model_config` keys: **none.**
- **Flags the wording depends on** (read, not changed; `legal-lead` writes for the state at launch,
  and a later flip of any of these re-opens the policy): `auth.email_capture` false
  (`config/features.json:93`), `monetize.*` false (`:141-148`), `profiles.public_pages` false
  (`:24`), `espn.send` true (`:115`), `trade.send_in_mfl` true (`:53`), `trade.send_in_sleeper` true
  (`:52`), `ranks.source.dynasty_nerds` true (`:160`), `obs.api_events` true (`:250`).

## 3. Evidence scope

- [x] **Structural guard (web):** new assertions in `qa/web/check_web_structure.py` (CI job
  `web-structure`, `.github/workflows/ci.yml:50-62`), added beside the `HYG-*` checks
  (`qa/web/check_web_structure.py:280-305`) and sharing P28's `SUPPORT_EMAIL` constant:
  - `POLICY-name[privacy.html|terms.html]`: the body, with HTML comments stripped (the checker's
    existing `strip_comments`), contains neither `Fantasy Trade Finder` nor `hobby project`. The
    domain `fantasy-trade-finder.onrender.com` is hyphenated and doesn't match.
  - `POLICY-mailto[privacy.html|terms.html]`: contains `href="mailto:fleecedapp@gmail.com"` and a
    link to `/contact.html`; no U+FF20 (shared with P28's check).
  - `POLICY-effective-date[privacy.html|terms.html]`: parses `Effective date: <Month> <D>, <YYYY>`
    and asserts it is on or after a `POLICY_MIN_EFFECTIVE` date set in the checker by the M7 build.
    Bumping that constant is part of every future policy edit; that is the point.
  - `POLICY-feedback-pointer[privacy.html]`: no `Settings → feedback` (with the arrow as `→` or
    `&rarr;`).
  - If `legal-lead` keeps any beta wording deliberately (D-12), the check allow-lists those exact
    strings with a comment naming the decision, rather than skipping the page.
- [ ] **Mobile structural guard:** WAIVED, see below.
- [ ] **Unit tests:** WAIVED, see below.
- [x] **Code-walk proof** (reconciliation, not behavior): the policy claims checklist in
  [prd.md §7.3](prd.md#73-policy-claims-checklist) and the collection-surface list in
  [§7.4](prd.md#74-collection-surfaces-since-2026-07-19-the-policy-may-not-cover) are the file:line
  trace. Each "candidate" row needs `analytics-lead`'s confirmed or corrected verdict before
  `legal-lead` finalizes the text. That signed-off table is the evidence for M7-AC5.
- [x] **Manual read-through** (operator or `legal-lead`, after deploy to Render):
  1. Open `/privacy` and `/terms` on desktop Safari and iOS Safari. Expected: product name
     "Fleeced: Dynasty Trade Finder" throughout; the effective date is the M7 ship date; no hobby or
     beta characterization except any `legal-lead` kept deliberately (D-12).
  2. Tap the support address in privacy §10 and terms §13. Expected: Mail opens addressed to
     `fleecedapp@gmail.com`.
  3. Follow the contact-form link from each page. Expected: `/contact.html` loads.
  4. Read privacy §10. Expected: the feedback pointer describes the floating button (and the
     Settings → Help & about row once BL-10 ships), not "Settings → feedback".
  5. In the app, Settings → Help & about → Privacy Policy, then Terms of Use. Expected: each opens
     the updated page in the browser (`mobile/src/screens/settings/sections/AboutSection.tsx:79-96`).
  6. `legal-lead` compares the final policy with the App Privacy label answers (M6(b)). Expected:
     every label maps to a policy statement and the reverse (M7-AC6).
- [ ] **Manual TestFlight checklist:** WAIVED, see below.
- [x] **WAIVED because** (Waiver **W-M7-2**): only two static web pages change. There is no mobile
  code, so no `mobile/tests/check-*.js` guard and no TestFlight checklist; the app's Privacy and
  Terms rows only open the web URLs, and step 5 of the read-through covers them. There is no
  backend code, so no pytest.
- `testID`s added/renamed: **none.**

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` (any route added/renamed/removed/contract-changed) | n/a | No route change. |
| `docs/data-dictionary.md` | n/a | No schema change (see §2 on reconciliation findings). |
| `living-memory/LLD.md` (schema/route/invariant *conventions* shifted) | n/a | No convention change. |
| `docs/architecture.md` (module wiring / data flow changed) | n/a | No module or data-flow change. |
| `living-memory/HLD.md` (architecture genuinely shifted) | n/a | No architecture change. |
| `docs/cross-client-invariants.md` (shared constants/enums/colors) | **shared row** | The "Support contact address" section added by P28/BL-10 also lists these two pages as homes of the address. |
| `docs/glossary.md` (new domain term) | n/a | No new term. |
| ADR or `DECISIONS.md` entry (non-obvious choice made) | **update at build, conditional** | Only if `legal-lead` keeps beta wording deliberately (D-12), or the operator re-confirms the `[STATE]` waiver W1 for App Store launch (D-11, `docs/plans/web-parity/scope.md:121`). Otherwise n/a: a policy rewrite to match the product is not a design choice. |
| `web/CLAUDE.md` | n/a | The `privacy.html` / `terms.html` row (`web/CLAUDE.md:21`) stays accurate. |
| `docs/runbook.md` | n/a | No operational change; the support inbox runbook entry belongs to P28. |
| `analytics-lead`'s data inventory (P12/P18) | **link at build** | The final policy cites the inventory version it was reconciled against, in the TEST_LEDGER entry. |

## 5. Ship gate declaration

- **CI green:** `backend-tests` + `mobile-typecheck` (with every `mobile/tests/check-*.js`) +
  `web-structure` (with the `POLICY-*` assertions) + `maestro-testid-lint` (the job name D-056 kept;
  it runs testid-lint only), all passing on the pushed sha.
- **Evidence recorded:** a `living-memory/TEST_LEDGER.md` entry naming the checker run, the manual
  read-through result, the inventory version, and `legal-lead`'s sign-off. Push with
  `FTF_SKIP_SIM_GATE=1` (D-056 standing posture) and name that evidence.
- **Ordering gate:** M7 is live on Render **before** `app-manager` submits the App Privacy labels,
  and the labels match the published text (M7-AC6). The address must already be live on
  `contact.html` (P28), or ship in the same deploy.
- **Sign-off gates:** `legal-lead` final wording; `analytics-lead` confirmed every row of prd.md
  §7.3 and §7.4; D-11, D-12 and D-13 decided.
- **TestFlight verification:** none (waived in §3).
- Express lane declared by the operator? **No.** Full gates. Legal text is never self-selected for
  express by an agent.
