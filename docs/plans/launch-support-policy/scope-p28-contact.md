# Feature Scope — P28: support address on the contact page

**Date:** 2026-10-20
**Entry point:** direct ask: `head-product` App Store launch-readiness review (2026-10-20), item P28; operator decisions BL-2 and P28
**Builder:** `launch-onboarding-pm-1` for `onboarding-pm` (spec only; build later by `onboarding-eng` under `head-eng`)
**Operator sign-off on waivers:** signed 2026-10-22 (operator, in head-product's session; quoted verbatim: "I sign off on #354's waivers."). Covers W-P28-1, W-P28-2, W-BL10-1, W-BL10-2, W-M7-1, W-M7-2 and W-ALL-1 ([prd.md §9](prd.md#9-decisions-needed)). **W-BL10-2 has lapsed:** head-eng confirmed D-2's 403 and Product chose D-2(a), so a pytest is required.

Requirements, copy inventory and acceptance criteria: [prd.md §5](prd.md#5-p28-contact-page).
**Copy (2026-10-23):** `marketing-lead`'s c1–c8 are recorded verbatim in the adopted table under
[prd.md §5.4](prd.md#54-copy-inventory-copy-marketing-lead-data-request-lines-reviewed-by-legal-lead).
All eight are pending operator §6. P36 said c2–c5 and c8 also need `legal-lead`'s review; marketing's
R22 revision marks them approved or edited per R22 (c3, c4 and c8 are legal's exact text), flagged for
`head-product` to confirm (prd.md §9). P28
goes live on **Fri 2026-11-13**, with the privacy and terms pages and the FAQ (prd.md §8).
Ownership: `onboarding-pm` owns the product side of `web/contact.html` (P11) and the data-request
lifecycle (P12). Words: `marketing-lead` via `head-product` → `head-bizops`; `legal-lead` reviews the
data-request lines. Visuals: `design-lead`.

---

## 1. Analytics scope

- [ ] **(a) New events specced:** none.
- [ ] **(b) Existing events cover it:** —
- [x] **(c) WAIVED — no analytics needed because:** the form keeps posting through
  `POST /api/feedback` (`web/contact.html:158`), which already fires the server-side
  `feedback_submitted` (`backend/analytics_taxonomy.py:839`, emitted at
  `backend/server.py:11150-11158`) for a signed-in sender, unchanged. No mailto-tap event is added:
  the operator's P28 decision minimizes collection on the support page, and a tap on a `mailto:`
  link says nothing about whether an email was sent. (Waiver **W-P28-1**.)

## 2. Schema & flag scope

- New/changed tables or columns: **none.** → `docs/data-dictionary.md` n/a.
- New/changed feature flags: **none.** This is support and data-request copy plus a one-line defect
  fix on a static page. Copy corrections ship unflagged per ADR-008's exception for doc/legal copy
  (`docs/adr/adr-008-teardown-remediation-wave.md:21-23`), and a "keep Send disabled" switch has no
  value as a rollback state.
- New env vars / `model_config` keys: **none.**
- **No new form field of any kind** (operator P28): no `<input type="email">`, no reply-address
  field. The `/api/feedback` body is unchanged.

## 3. Evidence scope

- [x] **Structural guard (web):** new assertions in `qa/web/check_web_structure.py`, the web CI gate
  (`.github/workflows/ci.yml:50-62`; 195/195 checks pass at `678834ab`). They go beside the existing
  `HYG-*` checks (`qa/web/check_web_structure.py:280-305`), using its `r.check(...)` pattern:
  - `SUPPORT-mailto[contact.html]`: `href="mailto:fleecedapp@gmail.com"` occurs **at least twice**,
    with at least one occurrence before `<form` and one after the Data requests `<h2>`. The expected
    address is one constant in the checker (e.g. `SUPPORT_EMAIL`), shared with the M7 assertions.
  - `SUPPORT-no-fullwidth-at[contact|privacy|terms]`: no U+FF20 (`＠`) in the three pages.
  - `CONTACT-no-email-input`: no `<input` with `type="email"` (any quoting) in `contact.html`.
  - `CONTACT-send-reenabled`: the success path re-enables the button (a `btn.disabled = false`
    inside the `.then` success handler, or in a shared `.finally`). **Honest label:** this is a
    textual check on the source, not a behavioral one; the manual check below proves behavior.
  - Optional, crude: `CONTACT-no-reply-promise`: `contact.html` contains none of
    `follow up` / `get back to you` / `we'll reply` (case-insensitive). Only if `marketing-lead`'s
    final copy makes this list stable; otherwise drop it rather than pin wording.
- [ ] **Mobile structural guard:** WAIVED, see below.
- [ ] **Unit tests:** WAIVED, see below.
- [x] **Code-walk proof** (file:line at `678834ab`; the builder re-walks it against the built file):
  1. Submit handler disables Send: `web/contact.html:148`.
  2. Success branch `:159-168` sets status, resets the form, zeroes the counter, hides the hint, and
     **never** touches `btn.disabled`; only the `.catch` re-enables it (`:172`). So after one
     successful send, the button stays disabled until reload. The fix adds the re-enable on success.
  3. The page sends `X-Session-Token` when `localStorage.fumble_session_token` exists (`:152-156`),
     so a signed-in web visitor's note is attributed (`backend/server.py:11112-11122`); without a
     token it is anonymous. The P28 change doesn't alter this. Note the open candidate D-2 in
     [prd.md §6.2](prd.md#62-new-finding-unverified-sessions-cant-send-feedback-candidate-head-eng-confirms):
     an unverified web session may get `403` and see the error text.
  4. Data requests post as `severity: "bug"`, `screen: "web-contact-data-request"`, text prefixed
     `[DATA REQUEST] ` (`:136-146`). Unchanged, unless D-8 removes the topic.
- [x] **Manual web check** (operator or `onboarding-eng`, after deploy to Render; on desktop Safari
  and iOS Safari):
  1. Open `https://fantasy-trade-finder.onrender.com/contact.html`. Expected: the address is visible
     near the top, written `fleecedapp@gmail.com` with an ordinary `@`.
  2. Tap the top address. Expected: Mail opens a new message addressed to `fleecedapp@gmail.com`.
  3. Scroll to Data requests and tap the address there. Expected: same as step 2.
  4. Pick "Something is broken", type a message, Send. Expected: success text with no promise of a
     reply; Send is enabled again.
  5. Without reloading, type a second message and Send. Expected: the second send succeeds.
  6. Pick the data-request topic (if D-8 keeps it). Expected: the hint and success text match
     `legal-lead`'s approved wording and promise no follow-up through the form.
  7. Confirm the page has no email input field anywhere.
- [ ] **Manual TestFlight checklist:** WAIVED, see below.
- [x] **WAIVED because** (Waiver **W-P28-2**): this is a web-only change to one static page; there is
  no mobile code (so no `mobile/tests/check-*.js` guard and no TestFlight checklist) and no backend
  code (so no pytest). Mobile reaches this page only through the support link in the App Store
  listing, which the manual web check covers.
- `testID`s added/renamed: **none** (web page; `mobile/scripts/testid-lint.sh` unaffected).

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` (any route added/renamed/removed/contract-changed) | n/a | No route or contract change; the page keeps posting the same `/api/feedback` body. |
| `docs/data-dictionary.md` | n/a | No schema change. |
| `living-memory/LLD.md` (schema/route/invariant *conventions* shifted) | n/a | No convention change. |
| `docs/architecture.md` (module wiring / data flow changed) | n/a | No module or data-flow change. |
| `living-memory/HLD.md` (architecture genuinely shifted) | n/a | No architecture change. |
| `docs/cross-client-invariants.md` (shared constants/enums/colors) | **update at build** | New section "Support contact address": value `fleecedapp@gmail.com` (ASCII `@`), its three homes (web pages, held by `qa/web/check_web_structure.py`; the mobile constant; App Store Connect), and the rule "never a full-width `＠`". Owner `head-eng`. Added once, by whichever of P28/BL-10 lands first. |
| `docs/glossary.md` (new domain term) | n/a | No new term. |
| ADR or `DECISIONS.md` entry (non-obvious choice made) | **update at build** | Record that BL-2/P28 (2026-10-20) supersede web-parity waiver W2 "No support email" (`docs/plans/web-parity/scope.md:122`), and that the form stays one-way with no reply field by operator choice. Next ID = max `D-` + 1 at build time (D-208 is the max at `678834ab`). |
| `web/CLAUDE.md` (page map) | **update at build** | The `contact.html` row (`web/CLAUDE.md:19`) says the form is "the only route a web visitor has to a deletion/access request"; after P28 the email is a second route. |
| `docs/runbook.md` | **update at build** | Support-inbox operations: who reads `fleecedapp@gmail.com`, the response target, and the identity-verification step for emailed data requests (D-9, D-10). Response targets per D-10 (`head-bizops`): general replies within 2 business days; data requests acknowledged within 2 business days and completed within 30 days (the 30 days pending `legal-lead`'s confirmation). Owner `head-bizops`. |
| `docs/plans/web-parity/scope.md` | n/a | Historical; W2's supersession is recorded in DECISIONS, not by editing the old plan. |

## 5. Ship gate declaration

- **CI green:** `backend-tests` + `mobile-typecheck` (which also runs every `mobile/tests/check-*.js`,
  `.github/workflows/ci.yml:42-48`) + `web-structure` (with the new assertions) +
  `maestro-testid-lint` (the job name D-056 kept; it runs testid-lint only), all passing on the
  pushed sha.
- **Evidence recorded:** a `living-memory/TEST_LEDGER.md` entry naming the checker run (pass count
  before and after), the manual web check results (both browsers), and the code-walk.
  `githooks/pre-push` still checks the retired simulator marker; under D-056 push with
  `FTF_SKIP_SIM_GATE=1` and name the evidence above instead.
- **TestFlight verification:** none (web-only; waived in §3).
- **Copy gate:** `marketing-lead`'s copy in place; `legal-lead` has approved the data-request lines
  (C3-C5 in [prd.md §5.4](prd.md#54-copy-inventory-copy-marketing-lead-data-request-lines-reviewed-by-legal-lead)).
- **Ops gate:** someone owns the inbox before the address is published (D-10). **Satisfied:** the operator monitors `fleecedapp@gmail.com` (D-10, `head-bizops`).
- Express lane declared by the operator? **No.** Full gates apply. P28 touches no schema, API
  contract, flag or analytics event, so the operator could declare express; no agent may.
