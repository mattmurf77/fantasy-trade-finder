# PRD — Launch support contact, public in-app feedback, policy pages (P28 · BL-10 · M7)

**Date:** 2026-10-20
**Status:** spec, awaiting acceptance by `head-product`. Specs only: no product code is written here.
**Author:** `launch-onboarding-pm-1`, for `onboarding-pm` (product lead, Onboarding & accounts)
**Source:** `head-product`'s App Store launch-readiness review (2026-10-20), items **P28**, **BL-10**, **M7**
**Base:** every `file:line` below was read at `origin/main` `678834ab`, except the 2026-10-23 additions (the adopted-copy tables in §5.4 and §6.7, §6.8, §6.9, §6.10, §7.8 and §7b), which were read at `origin/main` `712dcbed`. The contact, feedback and Settings files those tables cite are unchanged between the two shas. Re-verify before building.
**Scope blocks:** [P28 contact page](scope-p28-contact.md) · [BL-10 public feedback](scope-bl10-feedback.md) · [M7 policy pages](scope-m7-policy-pages.md) · [Q6 tour line](scope-q6-tour-line.md) · [FAQ, SUP-M4](scope-faq-sup-m4.md) (build input: [faq-copy.md](faq-copy.md)) · [M11 entry ownership](scope-m11-entry-ownership.md) · [D-13 policy notice](scope-d13-policy-notice.md)

---

## Contents

1. [Problem](#1-problem)
2. [Operator decisions this spec implements](#2-operator-decisions-this-spec-implements)
3. [Ownership](#3-ownership)
4. [Scope and non-scope](#4-scope-and-non-scope)
5. [P28: contact page](#5-p28-contact-page)
6. [BL-10: in-app feedback for the public](#6-bl-10-in-app-feedback-for-the-public)
7. [M7: privacy and terms pages](#7-m7-privacy-and-terms-pages)
   - [7b. FAQ (SUP-M4)](#7b-faq-sup-m4)
8. [Sequencing and dependencies](#8-sequencing-and-dependencies)
9. [Decisions needed](#9-decisions-needed)
10. [Handoffs](#10-handoffs)
11. [Facts in the brief that changed on verification](#11-facts-in-the-brief-that-changed-on-verification)

---

## 1. Problem

Fleeced is leaving TestFlight. Three surfaces still assume a tester audience and a product with no
support address:

- **There is no way to get a reply.** No support address exists in any client (`git grep` for
  address patterns in `web/`, `mobile/src/`, `extension/` and `mobile/app.json` matches only the
  Sentry DSN). `web/contact.html` posts to
  `POST /api/feedback`, which has no reply channel, yet its data-request success text promises one:
  "We'll action your data request and follow up" (`web/contact.html:163`). The 2026-08-26
  standing decision "No support email" (web-parity waiver W2,
  [`../web-parity/scope.md:122`](../web-parity/scope.md), `living-memory/CHANGELOG.md:341`) is
  superseded by the operator's BL-2 decision of 2026-10-20.
- **The in-app feedback surface talks to testers.** Its failure message sends people to
  "Settings → Testing → Test feedback" (`mobile/src/components/FeedbackSheet.tsx:63-64`), a section
  public users never see (`mobile/src/screens/settings/SettingsHubScreen.tsx:333`,
  `mobile/src/screens/SettingsScreen.tsx:1480`, both gated on `__DEV__ || testing.stage_users`,
  and `testing.stage_users` is `false` at `config/features.json:206`). The FAB's count pill counts
  notes a public user can't open (`mobile/src/components/FeedbackFAB.tsx:126`, `:152-156`).
- **The policy pages describe a hobby beta with a different name.** "Fantasy Trade Finder ... a
  small, independent hobby project" (`web/privacy.html:74-77`, `web/terms.html:66`, `:74-75`), a
  wrong feedback pointer (`web/privacy.html:280`), an effective date of July 19, 2026
  (`web/privacy.html:71`, `web/terms.html:63`) that predates a material edit on 2026-09-05
  (`a927e3a7`, #279), and data claims nobody has reconciled with the current data inventory or the
  App Store privacy labels.

All three are App Store launch MUST or support items.

## 2. Operator decisions this spec implements

Quoted as relayed by the coordinator, 2026-10-20:

- **BL-2:** the published support address is **fleecedapp@gmail.com**, written with an ASCII `@`
  (U+0040), never the full-width `＠` (U+FF20).
- **BL-10:** "in app feedback stays". It is rewritten for the public, the "Testing" pointers are
  removed, and it names fleecedapp@gmail.com for anything that needs a reply.
- **P28:** `web/contact.html` shows the address as a `mailto:` link. **The contact form gets NO
  new email field in v1**: we don't collect reply addresses we don't need, which keeps the privacy
  labels simple. Users who want a reply email us.

Consequence spelled out: **every in-product channel stays one-way.** The only two-way channel is
the email address. The specs below never add a reply-address input anywhere.

## 3. Ownership

Per decisions P10–P12:

| Area | Owner | Notes |
|---|---|---|
| Product side of `web/contact.html`, `web/privacy.html`, `web/terms.html` | `onboarding-pm` (P11) | Requirements, acceptance, sequencing |
| Privacy and data-lifecycle product side | `onboarding-pm` (P12) | Includes the email data-request path (§5.3) |
| IA of Settings rows | `onboarding-pm` signs off, `ux-lead` reviews (P10) | The feedback-inbox row move (§6.3 BL10-R5, D-3) |
| Words on the contact page and the feedback sheet, inbox and Settings row | `marketing-lead`, via `head-product` → `head-bizops` | Copy inventories in §5.4 and §6.7 |
| Privacy and terms wording | `legal-lead`, via `head-bizops` | Wording inventory in §7.5; also reviews the P28 data-request lines |
| Data inventory | `analytics-lead` | Confirms or corrects every "candidate" in §7.3 and §7.4 |
| Visuals | `design-lead` | Chalkline tokens only (`docs/design/design-system.md`) |
| Flow and nav review | `ux-lead` | §6.4, D-3, D-6, D-7 |
| `FeedbackFAB`, `RootNav` | `head-eng` | Shared surface; builds via `onboarding-eng` |
| App Store Connect Support URL, support email, App Privacy submission | `app-manager` (with `release-lead`) | §5.5, M7-R6, M7-AC6 |

This document writes requirements, constraints and acceptance criteria. Where words are needed it
gives a copy inventory (current string, `file:line`, what the new one must convey) and the owner
writes the words. Placeholders read **copy: marketing-lead** or **wording: legal-lead**.

## 4. Scope and non-scope

**In scope**

- P28: `web/contact.html` gets the mailto address twice, honest success and data-request text, and
  a fix for a Send button that never re-enables after a successful send.
- BL-10: the feedback sheet, FAB, inbox and their Settings entry are rewritten for public users and
  stay in App Store builds; the inbox row moves to a public Settings section.
- M7: requirements for the privacy and terms rewrite, a policy claims checklist for reconciliation
  with `analytics-lead`'s inventory and the App Privacy labels, and the terms topics `legal-lead`
  must cover for launch.
- One support-address constant per client, plus a `docs/cross-client-invariants.md` row.
- Evidence: added assertions in `qa/web/check_web_structure.py`, a new
  `mobile/tests/check-*.js` guard, a file:line code-walk, and manual web and TestFlight checklists.
- Added 2026-10-23 (P36): the Q6 tour line (§6.8) and the FAQ rewrite (§7b), each with its own
  scope block.
- Added 2026-10-23 (`head-product`'s new launch MUST M11): ESPN/MFL entry ownership proof, so that
  entry users can delete their account, download their data and import their league (§6.9), with
  its own scope block.
- Added 2026-10-23: `ux-lead`'s and `design-lead`'s reviews of #354 as build instructions (§6.10),
  including the credits row (BL10-R12), and D-13's in-app policy-change notice (§7.8), with its own
  scope block.

**Not in scope**

- An email input, a reply-address field, or any server-side reply mechanism (operator P28).
- New analytics events (each scope block's §1 waives them).
- New feature flags (see each scope block's §2 and D-4).
- Changing the `POST /api/feedback` contract, including the severity values `bug` / `polish` /
  `idea`, unless head-product accepts option (a) of D-2.
- Final marketing copy or legal wording.
- **Adjacent, mentioned only:** S4 (the old product name in mobile strings, P9) and S7 (the stale
  About build label). `useFeedback.ts:269`'s "DTF Mobile Feedback" share header is on the feedback
  surface, so BL-10's copy inventory lists it; every other old-name string stays with S4.

## 5. P28: contact page

### 5.1 Verified current state (`web/contact.html` at `678834ab`)

| Fact | Where | Verdict |
|---|---|---|
| The form posts to `POST /api/feedback` | `:158` | True. **Not always anonymous:** it attaches `X-Session-Token` from `localStorage` `fumble_session_token` when present (`:152-156`), so a signed-in web visitor's message is attributed (`backend/server.py:11112-11122`). |
| No email anywhere on the page | whole file | True. The only `@` characters are in the Google Fonts URL (`:17`) and a CSS `@media` rule (`:23`). |
| Data-request success says "We'll action your data request and follow up" | `:162-163` | True. No reply channel exists. The Data requests section repeats "we'll action it" (`:95-98`). |
| Send is disabled on submit and re-enabled only on the error path | `:148`, `:172` | True. The success branch (`:159-168`) resets the form but leaves `btn.disabled = true`, so a second message needs a reload. |
| Data requests ride as `severity: "bug"` with a `[DATA REQUEST] ` prefix and `screen: "web-contact-data-request"` | `:136-146` | Background. Unchanged by this spec. |

### 5.2 Requirements

- **P28-R1.** Show `fleecedapp@gmail.com` as a `mailto:fleecedapp@gmail.com` link **twice**: once
  near the top, framed as the way to get a reply, and once inside the Data requests section.
- **P28-R2.** Add **no** email input. The page keeps exactly the `topic` select and `message`
  textarea it has today (`:72-82`).
- **P28-R3.** No text on the page promises a reply the form can't deliver. That covers both
  success strings (`:162-164`), the Data requests section (`:94-99`) and the data hint (`:85-87`).
- **P28-R4.** Requests that need a reply (export or access) are directed to the email address,
  with the identifier we need to find the account (today "the Sleeper username"; see D-9).
- **P28-R5.** The in-app self-serve paths stay mentioned: export and delete under Settings →
  Account & data (`mobile/src/screens/settings/sections/AccountDataSection.tsx:211`, `:250`).
- **P28-R6.** `legal-lead` reviews the data-request wording before it ships.
- **P28-R7. Defect found during spec:** re-enable Send after a **successful** send. One line, same
  file (`btn.disabled = false` in the success branch, or a shared `finally`). The defect predates
  this spec; it is in scope because P28 already edits this handler.
- **P28-R8.** The address is written in one place per page and is identical everywhere it appears;
  `check_web_structure.py` holds the single expected value (see 5.6). The web has no build step,
  so a shared runtime constant isn't available; the checker is the single source of truth.
- **P28-R9.** Chalkline only: no new hue, no emoji (`docs/design/design-system.md` Prohibitions
  1, 6, 9). `contact.html` defines no `a` style except `.foot a` (`:63`); the policy pages already
  style links in ice (`web/privacy.html:57-58`, `web/terms.html:54-55`). `design-lead` specifies
  the inline link style for `contact.html`.

### 5.3 Data requests by email: the gap this opens

An email naming a Sleeper username doesn't prove the sender owns that account. The anonymous form
has the same weakness today. Before launch, `legal-lead` (wording) and `head-bizops` (operations)
must define how an emailed export, access or deletion request is verified before anyone acts on it
(D-9). The spec requirement: **no account data is sent by email to an unverified sender.** The
in-app export (`/api/account/export`, `backend/server.py:27945-27946`) already requires a verified
session (`_account_data_gates`, `:27931-27942`, applied at `:27959`), so it is the preferred route.

### 5.4 Copy inventory (copy: marketing-lead; data-request lines reviewed by legal-lead)

| # | Current string | `file:line` | The new one must convey |
|---|---|---|---|
| C1 | "Report a bug, suggest an idea, or make a request about your data. This goes straight to the people who build the app." | `web/contact.html:69` | The form is one-way. For a reply, email fleecedapp@gmail.com (mailto, P28-R1 first instance). |
| C2 | "Data request — access, export, or deletion" (option) | `:77` | Depends on D-8: kept for deletion-without-reply, or removed in favor of email. |
| C3 | "So we can find your records, include the Sleeper username you use with the app." | `:86` | Which identifier to include. "Sleeper username" doesn't fit Apple-only, ESPN or MFL accounts (legal-lead review). |
| C4 | "You can ask us for a copy of your data or ask us to delete it. Send a **Data request** above with the Sleeper username you use with the app, and we'll action it. In the mobile app you can also export or delete your account directly from Settings." | `:95-98` | Export and access need a reply, so email fleecedapp@gmail.com (mailto, P28-R1 second instance). In-app: Settings → Account & data. No "we'll action it" without saying how the requester learns the outcome. |
| C5 | "Sent. We’ll action your data request and follow up." | `:163` | No follow-up promise. What happens next, and the email for anything that needs a reply. |
| C6 | "Sent — thank you. We read every message." | `:164` | Can stay. Optionally: we can't reply to form messages, so email for a reply. |
| C7 | "Could not send. Please try again shortly." | `:171` | Optionally offers the email as a fallback. |
| C8 | Meta description / og:description | `:7`, `:12` | Only if D-8 removes the data-request topic. |

**Copy adopted (marketing-lead-copy.md §1b, at `712dcbed`).** `marketing-lead`'s launch copy batch
(2026-10-23, basis `712dcbed`), re-synced with the source as of 2026-10-23 18:17, which has
`legal-lead`'s R22 applied (its §0 item 11). It is recorded here because the source file isn't
tracked in git, so builders can't see it. Current text, new text, type and the "legal (R22)" column
are copied verbatim from marketing's table, including its bold and its bracketed review tags. The
tags are for review only and never ship. All eight C rows are `meaning` changes in marketing's §6
approval block F; c3, c4 and c8 are now `legal-lead`'s exact text. Status labels:

- **pending operator §6:** the operator approves the new text in marketing's §6.
- **pending operator §6; legal: (R22 value):** C2–C5 and C8, with `legal-lead`'s R22 verdict from
  marketing's column.

`head-product`'s 2026-10-23 relay (P36) said C2–C5 and C8 "still need legal-lead's review".
Marketing's R22 revision (its §0.11: "No row is pending") shows `legal-lead` has since reviewed them;
**flagged for `head-product` to confirm** (§9).

| key | PRD # | `file:line` (712dcbed) | current | new text (verbatim, marketing-lead) | type | legal (R22) | status |
|---|---|---|---|---|---|---|---|
| c1 | C1 | `web/contact.html:69` | Report a bug, suggest an idea, or make a request about your data. This goes straight to the people who build the app. | Report a bug or suggest an idea. This form goes straight to the people who build Fleeced, but it can't send a reply. For a reply, email fleecedapp@gmail.com. | meaning | approved (R22.1) | pending operator §6 |
| c2 | C2 | `:77` | Data request — access, export, or deletion | `Delete my data` (D-8(a); R22.1) | meaning | approved (R22.1) | pending operator §6; legal: approved (R22.1) |
| c3 | C3 | `:86` | So we can find your records, include the Sleeper username you use with the app. | `To find your account, say how you sign in (Apple, Sleeper, ESPN or MFL) and your username (for ESPN, the league ID and team name). Requests are acted on only when they can be verified, so send this while signed in, or email fleecedapp@gmail.com.` **[legal text, R22.1]** | meaning | **edited per R22** | pending operator §6; legal: edited per R22 |
| c4 | C4 | `:95-98` | You can ask us for a copy of your data or ask us to delete it. Send a **Data request** above … and we'll action it. In the mobile app you can also export or delete your account directly from Settings. | `Quickest route: in the app, open Settings › Account & data and choose Download my data or Delete account. If you can't use the app, email fleecedapp@gmail.com from the address you'd like the reply sent to, and say how you sign in and your username. You'll be asked to confirm the account is yours, and account data is never sent by email. Requests are acknowledged within 2 business days and completed within 30 days. You can also pick Delete my data above while signed in on this site. The form can't send a confirmation.` **[legal text, R22.3]** (design-lead may split it at "If you can't use the app"; the address is a `mailto:`) | meaning | **edited per R22** | pending operator §6; legal: edited per R22 |
| c5 | C5 | `:163` | Sent. We'll action your data request and follow up. | Sent. This form can't reply. To hear back about your request, email fleecedapp@gmail.com. **[legal-lead review]** | meaning | approved (R22.1) | pending operator §6; legal: approved (R22.1) |
| c6 | C6 | `:164` | Sent — thank you. We read every message. | Sent, thanks. Every message is read. For a reply, email fleecedapp@gmail.com. | meaning | approved (R22.1) | pending operator §6 |
| c7 | C7 | `:171` | Could not send. Please try again shortly. | Couldn't send. Try again in a minute, or email fleecedapp@gmail.com. | meaning | approved (R22.1) | pending operator §6 |
| c8 | C8 | `:7`, `:12` | Report a bug, suggest an idea, or make a data access or deletion request for your Fleeced account. | `Report a bug, suggest an idea, or see how to get a copy of your Fleeced data or delete it.` **[legal text, R22.1]** | meaning | **edited per R22** | pending operator §6; legal: edited per R22 |
| §3 note | — | `web/contact.html:68` | Contact us | `Contact` | not given | — (not in §1b) | untyped §3 suggestion, not in §6: `marketing-lead` to type it (§10) |
| §3 note | — | `:82` (textarea placeholder) | Tell us what happened, or what you'd like us to do. | `What happened, or what would you like changed?` | not given | — (not in §1b) | untyped §3 suggestion, not in §6: `marketing-lead` to type it (§10) |

Notes on the adopted contact copy:

- **c2 and c8 no longer branch on D-8.** Marketing's c2 is now `Delete my data` "(D-8(a); R22.1)",
  and c8 is one legal text. That reads as `legal-lead` choosing D-8(a), which §9 still lists as open;
  **flagged for `head-product` to confirm** (§9).
- **c4's length** (now about 522 characters) is `design-lead`'s call (P36). Marketing's cell now says
  `design-lead` may split it at "If you can't use the app".
- **c4 and FAQ Q18 state the D-10 timing:** data requests acknowledged within 2 business days and
  completed within 30 days.
- **The two "§3 note" rows** come from marketing's §3 ("Contact-page strings outside C1–C8"), which
  gives new text but no type, legal verdict or §6 entry. They are listed so builders see them; they
  don't ship until `marketing-lead` types them (§10).

### 5.5 Support URL

`https://fantasy-trade-finder.onrender.com/contact.html` (the canonical at `:8`) is the recommended
App Store **Support URL**. `app-manager` owns that App Store Connect setting and whether the
listing also shows the support email.

### 5.6 Acceptance criteria

- **P28-AC1.** `contact.html` contains `href="mailto:fleecedapp@gmail.com"` at least twice: one
  before the `<form>` and one inside the Data requests section.
- **P28-AC2.** `contact.html`, `privacy.html` and `terms.html` contain no U+FF20.
- **P28-AC3.** `contact.html` contains no `<input` with `type="email"`, and no new form field of
  any type.
- **P28-AC4.** After a successful send, Send is enabled again and a second message sends without a
  reload (manual check).
- **P28-AC5.** No string on the page promises a reply or follow-up through the form (copy review by
  `marketing-lead`, data-request lines by `legal-lead`).
- **P28-AC6.** Desktop Safari and iOS Safari: tapping either mailto opens Mail addressed to
  fleecedapp@gmail.com.
- **P28-AC7.** `python3 qa/web/check_web_structure.py` passes, including the new assertions (the
  `web-structure` job, `.github/workflows/ci.yml:50-62`; 195/195 checks pass at base).

## 6. BL-10: in-app feedback for the public

### 6.1 Verified current state

| Fact | Where | Verdict |
|---|---|---|
| `SAVE_FAILED_MESSAGE` points to "Settings → Testing → Test feedback" | `mobile/src/components/FeedbackSheet.tsx:63-64` | True |
| The Testing section renders only for `__DEV__ \|\| testing.stage_users` | `SettingsScreen.tsx:1480` (flat, `account.settings_v2` branch); `settings/SettingsHubScreen.tsx:333-340` (hub) | True. The row module is `settings/sections/TestingSection.tsx:53-65`. `testing.stage_users` is `false` (`config/features.json:206`). |
| Unsynced notes retry automatically on foreground | `mobile/App.tsx:199-207` | **Partly.** Retry runs on every AppState transition to `active` (`:202`, `:207`), which includes returning from background. It does **not** run on a cold launch: the listener only sees changes after it registers while the app is already active, and `hydrate()` (`mobile/src/state/useFeedback.ts:125-150`) never calls `retrySync()`. The inbox's "Retry sync" button is the other trigger (`FeedbackInboxScreen.tsx:77-85`). See D-1. |
| Sheet header "Capture feedback" / "Saved on this device. Share or export from Settings." | `FeedbackSheet.tsx:177-178` | True |
| Severity labels Bug / Polish / Idea; Screen placeholder "e.g. Trades / Tiers / Rank-Trios" | `FeedbackSheet.tsx:39-43`, `:213` | True. The same labels are repeated in `FeedbackInboxScreen.tsx:20-24` and `useFeedback.ts:275-277`. |
| Inbox title "Test feedback" | `FeedbackInboxScreen.tsx:123`; `navigation/RootNav.tsx:764-765` | True. Both render: the route header and the in-screen title. |
| The count pill counts open notes, but public users can't open the inbox | `FeedbackFAB.tsx:126`, `:152-156`; `utils/feedbackBadge.ts:30-36` | True. The pill excludes resolved statuses (`fixed`/`shipped`/`declined`) and closed notes. The inbox still lists `fixed` notes. |
| A production-build exclusion is planned | `FeedbackFAB.tsx:74-80`; `RootNav.tsx:628-632` | True. Planned, not implemented. RootNav's comment also says to remove "the matching Settings row" at public release. |
| `account.settings_hub` | `config/features.json:194` | `true`. `account.settings_v2` is also `true` (`:193`). The Settings route mounts the hub (`RootNav.tsx:272-275`); the flat list is reachable only if the hub flag is flipped off. |
| `feedback_submitted` is server-fired | `backend/analytics_taxonomy.py:839`; emitted at `backend/server.py:11150-11158` | True. Fires only for a signed-in, non-duplicate submission. |

### 6.2 New finding: unverified sessions can't send feedback (candidate, head-eng confirms)

`POST /api/feedback` carries `@_gate_unverified_write` (`backend/server.py:11066-11067`). That gate
returns `403 verification_required` for any session that isn't verified (`:2653-2660`, `:2663-2680`),
while the route itself accepts requests with **no** token anonymously (`:11112-11122`). The gate
is deliberate and documented: `docs/api-reference.md:146` lists `feedback` among the mutating
routes that run it. What this spec questions is its effect on a channel that accepts anonymous
writes anyway. A Sleeper-username-only session, which is the SignIn fallback, stays unverified
until the user runs SleeperConnect (`backend/server.py:2615-2627`). Apple sessions are verified
(`:27529`).

The likely effect: an unverified user's note is saved on the device, fails with 403 on every retry,
and never arrives. A "will send automatically" promise would be false for exactly those users. The
web contact form attaches the same token (`web/contact.html:152-156`), so an unverified web session
gets "Could not send". No backend test covers `/api/feedback` under the verified-write gate
(`backend/tests/test_verified_reads.py:61`, `:76` cover only `/mine`). See D-2.

### 6.3 Requirements

- **BL10-R1. The FAB stays in App Store builds.** The operator's BL-10 decision ("in app feedback
  stays") **supersedes** the planned production-build exclusion (`FeedbackFAB.tsx:74-80`, "S3
  PRD-01 item 3") and RootNav's removal note (`RootNav.tsx:628-632`). `head-eng` retires that
  comment and plan in the BL-10 build and records the supersession in `living-memory/DECISIONS.md`.
  The mount at `RootNav.tsx:633` stays unconditional: no build-profile env gate.
- **BL10-R2.** No user-visible "Testing", "Test feedback", "TestFlight" or "tester" string on the
  feedback surface: the sheet, the FAB's accessibility label, the inbox (route header and in-screen
  title), the inbox's share export, and the Settings row that opens it. Source comments may keep
  history.
- **BL10-R3. The "not sent" message** says the note is kept on the device and will send
  automatically, naming the trigger accurately from code. Today the trigger is the app returning
  to the foreground (`App.tsx:202-207`). If D-1(b) is accepted, a cold launch becomes a trigger too.
  The copy must not name a trigger the build doesn't implement.
- **BL10-R4.** The sheet names `fleecedapp@gmail.com` for anything that needs a reply and makes
  clear feedback is one-way. Shown as text the user can act on (a tappable `mailto:` is
  `design-lead`'s and `ux-lead`'s call).
- **BL10-R5. Inbox reachability (P10 IA decision, `onboarding-pm`; `ux-lead` reviews).** Move the
  feedback-inbox row out of the gated Testing section into a public section:
  - **Hub path (live):** Settings → **Help & about** (`SettingsAboutScreen`, reached from the hub's
    About group, `SettingsHubScreen.tsx:320-328`). The row goes in `AboutSection`
    (`settings/sections/AboutSection.tsx`). That module currently takes no navigation props
    (`:26-28`) and only opens external URLs, so the build gives it in-app navigation.
  - **Flat fallback:** the flat list's `aboutSection` (`SettingsScreen.tsx:1391`) gets the same row,
    because flipping `account.settings_hub` off is the documented rollback lever. Both flat branches
    then drop the row from `testingSection` (`:1018-1053`).
  - The row is retitled for the public (copy: marketing-lead) and carries a new `testID` (proposed
    `settings.feedback-inbox`; the current row has none).
  - **"Test stages" stays tester-only:** it keeps its `testing.stage_users` gate
    (`TestingSection.tsx:66-81`) and the hub's Testing row keeps `__DEV__ || testing.stage_users`.
  - The hub's About preview (`SettingsHubScreen.tsx:209-212`, "FAQ, privacy, terms") names the new
    row, because the hub's previews state only what is behind the row
    (`SettingsHubScreen.tsx:196-199`).
  - **Alternative considered and rejected:** hide the count pill for non-testers. It removes the
    symptom but also hides the only place a public user sees "Fixed — in next update"
    (`FeedbackInboxScreen.tsx:32`; `docs/cross-client-invariants.md:1131-1144`), which closes the
    loop between a report and a fix. Moving the row keeps that loop.
- **BL10-R6. Severity: words change, values don't.** Public labels and placeholders replace Bug /
  Polish / Idea and the Screen placeholder (copy: marketing-lead). The API values `bug` / `polish` /
  `idea` don't change: they are the `/api/feedback` contract (`backend/server.py:11101-11102`), the
  `/feedback` triage vocabulary, and the `testID` suffixes `feedback.severity.<value>`
  (`FeedbackSheet.tsx:188`). The three label copies (`FeedbackSheet.tsx:39-43`,
  `FeedbackInboxScreen.tsx:20-24`, `useFeedback.ts:275-277`) must agree.
- **BL10-R7. One support-address constant per client.** Mobile exports one constant (module
  location is `head-eng`'s call; `mobile/src/` has no constants module today). Every mobile use
  imports it, and the literal appears once in `mobile/src`. Web is held to one value by the checker
  (P28-R8). App Store Connect holds the third copy (`app-manager`). `docs/cross-client-invariants.md`
  gains a row naming all three locations (owner `head-eng`).
- **BL10-R8. No raw transport errors for the public.** The inbox's per-note state "Sync failed:
  HTTP 403 — …" (`FeedbackInboxScreen.tsx:171-174`) is tester vocabulary. Show plain-language state
  (copy: marketing-lead). The raw error can stay in the accessibility label only if `ux-lead` wants
  it there.
- **BL10-R9. Keep existing `testID`s.** `feedback.fab`, `feedback.severity.<value>`,
  `feedback.note-input`, `feedback.save-btn`, `feedback.save-error`, `feedback.char-count`,
  `feedback.note-error` and `settings.test-stages` stay. `mobile/scripts/testid-lint.sh` (kept by
  D-056) cross-checks IDs referenced by the historical flow files under `mobile/.maestro/`, which
  D-056 keeps but never runs, so a rename fails CI.
- **BL10-R10.** Chalkline only: no new hue, no emoji, radius ≤ 8px except specced pills, flare
  never on an action (`docs/design/design-system.md` Prohibitions 1-9). Visuals are `design-lead`'s.
- **BL10-R11 (OPTIONAL, not MUST; P36).** Sending again after a failed send duplicates the note:
  each Send calls `add()`, which mints a new id (`mobile/src/state/useFeedback.ts:152-158` at
  `712dcbed`). If `onboarding-eng` finds it cheap, a resend of the unsent note reuses that note's
  id instead of minting a new one. Launch doesn't depend on it: f1.alt ("…so no need to send it
  again") already steers users away from resending.
- **BL10-R12. Credits row (added 2026-10-23, design-lead's review).** `AboutSection` gets a
  non-pressable Credits block after Terms of Use and before Version, with `legal-lead`'s exact Part 3
  text. The construction and the text are in §6.10.2 (design-lead changes 1–2); the one exact string
  to settle is in §6.10.3. No events, no flags.
- **BL10-R13. Review-driven build list.** The full build list, guards and TestFlight steps from
  `ux-lead`'s and `design-lead`'s reviews are in §6.10. They govern for the build where they refine
  this section (§6.10.3).

### 6.4 Open items for `ux-lead`

**Answered (2026-10-23):** ux-lead's review (§6.10.1) gives the inbox a header close control (D-3;
the glyph is `design-lead`'s) and gates the `settings/testing` page body (D-7). The two items below
are kept as the record.

- The `FeedbackInbox` route is `presentation: 'modal'` (`RootNav.tsx:762`) without the header close
  control `docs/design/components.md:77` requires (#130). The settings-IA scope records it as an
  open gap. Making the inbox public makes the gap public.
- `SettingsTesting` is registered for everyone and deep-linkable (`mobile/src/utils/deepLinks.ts:112`,
  `settings/testing`). After the move, a non-tester who follows that link sees a page with a
  "Testing" banner and no rows. Accept it, or gate the page body (D-7).

### 6.5 Analytics

No new events. `feedback_submitted` stays server-fired and unchanged. Waived in the BL-10 scope §1.

### 6.6 Acceptance criteria

- **BL10-AC1.** In an App Store build, a fresh non-tester account sees the FAB on tab screens and
  on root-stack pushes.
- **BL10-AC2.** None of the BL10-R2 strings appear in user-visible text on the feedback surface or
  the Settings rows (structural guard + checklist).
- **BL10-AC3.** In airplane mode, Save shows the new "not sent" copy, the draft stays, and the note
  sends without user action on the BL10-R3 trigger.
- **BL10-AC4.** The sheet shows `fleecedapp@gmail.com`, sourced from the mobile constant.
- **BL10-AC5.** Settings → Help & about shows the feedback row for a non-tester; tapping it opens
  the inbox. The flat list (hub flag off) shows the same row under About.
- **BL10-AC6.** The FAB pill equals the inbox rows whose status chip is not "Fixed — in next
  update" (the pill excludes `fixed`; the inbox shows it).
- **BL10-AC7.** No Testing section or row is visible to a non-tester; "Test stages" still appears
  for a `testing.stage_users` device. "Tester" means ux-lead's `useTesterSurface()` predicate,
  `__DEV__ || testing.stage_users || testing.timing_readout` (§6.10.1 D-7); a non-tester who opens
  `settings/testing` sees the unavailable state.
- **BL10-AC8.** `POST /api/feedback` bodies still carry `severity` ∈ {`bug`,`polish`,`idea`}.
- **BL10-AC9.** CI green: `pytest backend/tests`, `tsc --noEmit`, every `mobile/tests/check-*.js`
  (the `mobile-typecheck` job runs them all, `.github/workflows/ci.yml:42-48`), testid-lint.
- **BL10-AC10.** Settings → Help & about shows a Credits block between Terms of Use and Version, and
  a structural assertion holds its text equal to `legal-lead`'s Part 3 text (BL10-R12).

### 6.7 Copy inventory (copy: marketing-lead)

| # | Current string | `file:line` | The new one must convey |
|---|---|---|---|
| F1 | "Saved on this device, but not sent yet. Nothing is lost — retry it from Settings → Testing → Test feedback." | `mobile/src/components/FeedbackSheet.tsx:63-64` | Kept on the device; sends automatically on the BL10-R3 trigger; no Settings pointer the public can't reach. |
| F2 | "Capture feedback" (sheet title) | `FeedbackSheet.tsx:177` | A public invitation to send feedback. |
| F3 | "Saved on this device. Share or export from Settings." | `FeedbackSheet.tsx:178` | One-way; for a reply, email fleecedapp@gmail.com; your notes live in Settings → Help & about → [row name]. |
| F4 | "Severity" (label) and "Bug" / "Polish" / "Idea" | `FeedbackSheet.tsx:181`, `:39-43`; a11y "Severity: X" at `:191` | Plain-language kinds of feedback. Values stay `bug`/`polish`/`idea`. |
| F5 | "Screen" (label), placeholder "e.g. Trades / Tiers / Rank-Trios" | `FeedbackSheet.tsx:207`, `:213` | Depends on D-6. The pre-filled value is an internal route name (`RootNav.tsx:307-311`; e.g. `SettingsAbout` at `SettingsAboutScreen.tsx:42`). |
| F6 | "What did you notice?" (note placeholder) | `FeedbackSheet.tsx:231` | Can stay. |
| F7 | "Capture feedback" / "Capture feedback, N open" (FAB a11y label) | `FeedbackFAB.tsx:145-149` | Matches F2; says how many notes are open. |
| F8 | "Test feedback" (route header) | `navigation/RootNav.tsx:764-765` | Public inbox name. One title, not two (see F9). |
| F9 | "Test feedback" (in-screen title) | `FeedbackInboxScreen.tsx:123` | Same as F8, or removed if the header carries it (`ux-lead`). |
| F10 | "N notes saved on this device" | `FeedbackInboxScreen.tsx:124-127` | Can stay. |
| F11 | "Retry sync" | `FeedbackInboxScreen.tsx:135` | A plain-language action that sends unsent notes now. |
| F12 | "Synced" / "Sync failed: <raw error>" / "Pending sync" | `FeedbackInboxScreen.tsx:171-174` | Sent / not sent yet, without HTTP codes (BL10-R8). |
| F13 | "No feedback yet" / "Tap the floating button on any screen to capture a note." | `FeedbackInboxScreen.tsx:153-155` | Public empty state. |
| F14 | "Clear all feedback?" / "This will delete N notes. Cannot be undone." | `FeedbackInboxScreen.tsx:99-100` | Clear that this clears the device copy only (the server keeps triage records, `web/privacy.html:219`). |
| F15 | Status chips: Received / Planned / In progress / Fixed — in next update / Shipped / Not planned | `FeedbackInboxScreen.tsx:28-35` | Cross-client invariant (`docs/cross-client-invariants.md:1131-1144`). Change only with that doc. |
| F16 | Share export header "# DTF Mobile Feedback — <date>" and labels Bug/Polish/Idea | `mobile/src/state/useFeedback.ts:269`, `:275-277` | Current product name; labels match F4. |
| F17 | Row "Test feedback" / "Review and share notes you captured with the floating button." | `settings/sections/TestingSection.tsx:59-61`; `SettingsScreen.tsx:1029-1032` | Public row title and subtitle in its new About home. |
| F18 | Hub About preview "FAQ, privacy, terms" / "Privacy, terms" | `settings/SettingsHubScreen.tsx:211` | Also names the feedback row (BL10-R5). |

**Copy adopted (marketing-lead-copy.md §1b, at `712dcbed`).** Same source, re-sync and rules as the
§5.4 table: current text, new text, type and "legal (R22)" are verbatim from marketing's table. No F
row's text or type changed in the R22 revision. Meaning changes are in marketing's §6 approval
block E. Status labels:

- **adopted:** `name`, `voice` and `keep` rows; no approval needed.
- **pending operator §6:** a meaning change; the operator approves the new text in marketing's §6.

BL-10 ships **f1.alt**, because D-1(b) is decided (P36). Marketing's `f1` (the foreground-only
wording) is **not used**, so it has no row.

| key | PRD # | `file:line` (712dcbed) | current | new text (verbatim, marketing-lead) | type | legal (R22) | status |
|---|---|---|---|---|---|---|---|
| f1.alt | F1 | `mobile/src/components/FeedbackSheet.tsx:63-64` | Saved on this device, but not sent yet. Nothing is lost — retry it from Settings → Testing → Test feedback. | Saved on this device but not sent yet. It retries the next time you open the app, so no need to send it again. | meaning | approved (R22.1) | pending operator §6 |
| f2 | F2 | `FeedbackSheet.tsx:177` | Capture feedback | Send feedback | voice | n/a (no legal or data claim; outside R22.1) | adopted |
| f3 | F3 | `FeedbackSheet.tsx:178` | Saved on this device. Share or export from Settings. | No replies here. Track each note in Settings › Help & about › Your feedback, or email fleecedapp@gmail.com for a reply. | meaning | approved (R22.1) | pending operator §6 |
| f4 | F4 | `FeedbackSheet.tsx:181` | Severity | What's this about? | voice | n/a (no legal or data claim; outside R22.1) | adopted |
| f4.bug | F4 | `FeedbackSheet.tsx:40` | Bug | Broken | voice | n/a (no legal or data claim; outside R22.1) | adopted |
| f4.polish | F4 | `:41` | Polish | Tweak | voice | n/a (no legal or data claim; outside R22.1) | adopted |
| f4.idea | F4 | `:42` | Idea | Idea (keep) | keep | n/a (no legal or data claim; outside R22.1) | adopted |
| f4.a11y | F4 | `:191` | Severity: {label} | Feedback type: {label} | voice | n/a (no legal or data claim; outside R22.1) | adopted |
| f5 | F5 | `:207`, `:211`, `:213` | Screen / e.g. Trades / Tiers / Rank-Trios | **Recommended:** hide the field and keep sending the value. If `ux-lead` keeps it: label `Screen`, placeholder `e.g. Home, Rank, Acquire` (the real tab labels, `TabNav.tsx:839`, `:878`) | meaning | n/a (no legal or data claim; outside R22.1) | pending operator §6 · D-6 decided: hide (`ux-lead` review owed) |
| f6 | F6 | `:231` | What did you notice? | keep | keep | n/a (no legal or data claim; outside R22.1) | adopted |
| f7 | F7 | `FeedbackFAB.tsx:145-149` | Capture feedback / Capture feedback, N open | Send feedback / Send feedback, {N} open | voice | n/a (no legal or data claim; outside R22.1) | adopted |
| f8 | F8 | `navigation/RootNav.tsx:764-765` | Test feedback | Your feedback | voice | n/a (no legal or data claim; outside R22.1) | adopted |
| f9 | F9 | `FeedbackInboxScreen.tsx:123` | Test feedback | Your feedback, or drop it if the header carries it (`ux-lead`) | voice | n/a (no legal or data claim; outside R22.1) | adopted |
| f10 | F10 | `FeedbackInboxScreen.tsx:124-127` | {N} notes saved on this device | keep | keep | n/a (no legal or data claim; outside R22.1) | adopted |
| f11 | F11 | `:135` | Retry sync | Send now | voice | n/a (no legal or data claim; outside R22.1) | adopted |
| f12.ok | F12 | `:171-174` | Synced | Sent | voice | n/a (no legal or data claim; outside R22.1) | adopted |
| f12.fail | F12 | `:173` | Sync failed: {raw error} | Not sent yet (the raw error goes to the a11y label only if `ux-lead` wants it) | meaning | n/a (no legal or data claim; outside R22.1) | pending operator §6 |
| f12.pending | F12 | `:174` | Pending sync | Waiting to send | voice | n/a (no legal or data claim; outside R22.1) | adopted |
| f13.title | F13 | `:153` | No feedback yet | keep | keep | n/a (no legal or data claim; outside R22.1) | adopted |
| f13.body | F13 | `:155` | Tap the floating button on any screen to capture a note. | Tap the flag button on any screen to send a note. | voice | n/a (no legal or data claim; outside R22.1) | adopted |
| f14.title | F14 | `:99` | Clear all feedback? | Clear notes from this device? | meaning | n/a (no legal or data claim; outside R22.1) | pending operator §6 |
| f14.body | F14 | `:100` | This will delete N notes. Cannot be undone. | Removes {N} note{s} from this device. It can't be undone. Notes already sent stay on file. | meaning | approved (R22.1) | pending operator §6 |
| f15 | F15 | `:28-35` | Received / Planned / In progress / Fixed — in next update / Shipped / Not planned | keep (cross-client invariant, `cross-client-invariants.md:1131-1144`) | keep | n/a (no legal or data claim; outside R22.1) | adopted |
| f16 | F16 | `mobile/src/state/useFeedback.ts:269`, `:275-277` | # DTF Mobile Feedback — {date}; Bug / Polish / Idea | # Fleeced feedback — {date}; Broken / Tweak / Idea (header matches copy-A) | name | n/a (no legal or data claim; outside R22.1) | adopted |
| f17.title | F17 | `settings/sections/TestingSection.tsx:59`; `SettingsScreen.tsx:1029` | Test feedback | Your feedback | voice | n/a (no legal or data claim; outside R22.1) | adopted |
| f17.sub | F17 | `TestingSection.tsx:61`; `SettingsScreen.tsx:1031` | Review and share notes you captured with the floating button. | Notes you've sent with the flag button, and where each one stands. | meaning | n/a (no legal or data claim; outside R22.1) | pending operator §6 |
| f18 | F18 | `settings/SettingsHubScreen.tsx:211` | FAQ, privacy, terms / Privacy, terms | FAQ, feedback, privacy, terms / Feedback, privacy, terms | meaning | n/a (no legal or data claim; outside R22.1) | pending operator §6 |
| fb.save | — | `FeedbackSheet.tsx:266` | Save | Send | meaning | n/a (no legal or data claim; outside R22.1) | pending operator §6 |
| fb.cancel | — | `FeedbackSheet.tsx:258` | Cancel | keep | keep | n/a (no legal or data claim; outside R22.1) | adopted |
| fb.close | — | `:169` | Close | keep | keep | n/a (no legal or data claim; outside R22.1) | adopted |
| fb.note | — | `:219`, `:229` | Note | keep | keep | n/a (no legal or data claim; outside R22.1) | adopted |
| fb.over | — | `:57` | Too long to send — trim {n} character{s}. Your text is still here. | keep: neutral, exact, already in voice | keep | n/a (no legal or data claim; outside R22.1) | adopted |
| fb.count | — | `:239` | {n} of {max} characters used | keep | keep | n/a (no legal or data claim; outside R22.1) | adopted |
| §3 note | — | `FeedbackInboxScreen.tsx:110` | Delete note? | `Remove this note from this device?` | not given | — (not in §1b) | untyped §3 suggestion, not in §6: `marketing-lead` to type it (§10) |

Notes on the adopted feedback copy:

- **f1.alt's trigger is true only with D-1(b).** "The next time you open the app" needs both the
  existing foreground-return retry (`mobile/App.tsx:207` at `712dcbed`) and D-1(b)'s cold-launch
  retry. They ship in the same binary (BL10-R3).
- **f3 keeps its email line** (P36). D-2(a) means unverified users' notes now arrive, but the
  in-app channel is still one-way, so email is the way to get a reply.
- **f3 and f17 name Settings › Help & about › Your feedback.** That is true only once BL10-R5's row
  move ships, in the same build.
- **f4's chips at 320pt** ("Broken / Tweak / Idea" in three flex-1 chips) are `design-lead`'s call
  (P36).
- **f5 / D-6: hide** the Screen field and keep sending the pre-filled value. The API still requires
  a non-empty `screen` (`backend/server.py:11097-11098`). If `ux-lead`'s review keeps the field,
  the fallback label and placeholder in the f5 cell apply. The inbox row still shows the stored
  value, an internal route name (`FeedbackInboxScreen.tsx:226`); `ux-lead`'s D-6 review covers that
  too.
- **Resend duplicates the note:** see BL10-R11 (optional).
- **The "§3 note" row** comes from marketing's §3, which suggests it because the per-note delete is
  device-only too (`useFeedback.ts:179-183`). Marketing gives no type, legal verdict or §6 entry; it
  doesn't ship until `marketing-lead` types it (§10).

### 6.8 Q6 tour line

**Status: approved (Q6, operator 2026-10-23).** The operator answered "Q6 tour line: Yes" on the
2026-10-23 form, relayed by `head-product`. `legal-lead` (LEG-S15) found the tour line "Passwords
never leave your phone" literally false and supplied the replacement. The change rides in the
11-06 binary with BL-10 but has its own scope block: [scope-q6-tour-line.md](scope-q6-tour-line.md).

| Fact (at `origin/main` `712dcbed`) | Where |
|---|---|
| `n23` is the Sleeper-only send beat. Its comment explains why the password sentence lives only on the Sleeper beat. | `mobile/src/components/analystScript.ts:632-640` (beat); `:626-631` (comment) |
| `n23b`, the off-Sleeper sibling, makes no password claim. It is unchanged. | `analystScript.ts:642-655` (`line` `:646`, `degradeLine` `:647`) |
| The runner picks `n23` only when the send platform resolves to Sleeper; otherwise `n23b`. | `mobile/src/utils/calcTour.ts:232-236` (`beatIdFor`). Its comment at `:228-231` quotes the old sentence. |
| `degradeLine` renders when the beat's spotlight fails. | `mobile/src/components/AnalystGuide.tsx:284` |
| The tour is dark. `startCalcTour` returns early unless `onboarding.guided_avatar` and `onboarding.guide_v2` are both on, and both are `false`. | `calcTour.ts:472`; `config/features.json:134`, `:137` |
| No check pins the old text. `check-guide-script.js` 9a requires `/password/i` in `n23`'s `line` (the new text passes), and 9b requires none in `n23b`'s. `cta` beats are capped at 16 words. `check-calc-tour.js` pins `n23`'s target and screen only. | `mobile/tests/check-guide-script.js:425-447` (§9), `:203` (caps), `:214`, `:229` (2b, 2c); `mobile/tests/check-calc-tour.js:370-371`, `:422` |

**The change.** `onboarding-eng` edits both strings in `n23`:

| Field | Current (`analystScript.ts`) | New |
|---|---|---|
| `line` (`:635`) | Sending goes straight to your league. Passwords never leave your phone. | Sending goes straight to your league. We never see your password. |
| `degradeLine` (`:636`) | Sending a trade goes straight to your league. Passwords stay on your phone. | Sending a trade goes straight to your league. We never see your password. |

The `line` is `legal-lead`'s exact text. The `degradeLine` applies the same operator-approved
substitution to the second line, as `legal-lead` specifies. They run 11 and 13 words, within the
16-word `cta` cap.

**Also at build:** update the places that quote the old sentence: the comment at `calcTour.ts:228-231`,
the §9 comment at `check-guide-script.js:425-430`, and `mobile/src/utils/CLAUDE.md:37`. Re-read the
`n23` comment (`analystScript.ts:626-631`) so it describes the new sentence.

**Evidence:** a structural assertion added to `check-guide-script.js` §9, plus a code-walk.
TestFlight is waived while the tour is dark (W-Q6-3). The detail is in the scope block.

### 6.9 M11: ESPN/MFL entry ownership proof: in-app deletion, data export and league import

**Status:** spec; gate 1 accepted (P38) and W-M11-1, W-M11-2 signed, 2026-10-23. **Decision: option
(e)** (`onboarding-pm`, 2026-10-23). Source: `head-product`'s
new launch MUST M11 (2026-10-23); `legal-lead` tracks it as LEG-M5. Apple guideline 5.1.1(v) requires
in-app deletion for every account the app creates. `legal-lead`'s D-9 email procedure is the support
fallback, not the fix. Scope block: [scope-m11-entry-ownership.md](scope-m11-entry-ownership.md).

Everything in 6.9.1 to 6.9.4 is **code-derived** at `origin/main` `712dcbed`. How many users it
affects needs an `analytics-lead` prod read (§10).

#### 6.9.1 The gates

| Fact | Where |
|---|---|
| Delete account and Download my data share one gate. A demo session gets 400 `demo_session`; any session without `sess["verified"]` gets 403 `verification_required`. | `backend/server.py:27931-27942`, applied at `:27959` (export) and `:27994` (delete) |
| The write and read gates check only **this session's** `verified` flag (or a synthetic demo session). There is no account-level check: an unverified session is denied whether or not the account was ever verified. | `:2653-2660`, `:2689-2696` |
| `users.verified_via` never authorizes anything. It feeds the account-binding conflict lookup, session_init's `verification` report and `GET /api/account`. | `:2632-2644`; `:23053-23080`; `:27731-27736` |
| `/api/profile/visibility`: the GET is read-gated, the PUT runs the write denial, and both 404 while `profiles.user_toggle` is off (it is `false`). Because the GET is gated, the toggle row never renders for an unverified session, so its step-up never fires today. | `:26745-26746`, `:26765`, `:26756`; `config/features.json:195`; `mobile/src/screens/settings/sections/AccountDataSection.tsx:196-197` |
| On a 403, Delete and Download show "Your account is verified, but this session isn't. Verify with your Sleeper login to …", and the only route offered is SleeperConnect. Delete shows the prompt only while `account.data_export` is on (it is `true`). | `AccountDataSection.tsx:87-100` (copy `:90-91`, route `:96`), `:129-130`, `:150`; `config/features.json:191` |

#### 6.9.2 How each entry gets `verified`

| Entry | Session verified? | Where |
|---|---|---|
| Sleeper username (`/api/extension/auth`) | No. The silent replay verifies it when this device holds a Sleeper JWT. | `server.py:25846-25871`; `mobile/src/api/auth.ts:57`, `:295-300` |
| Sleeper login (JWT captured in SleeperConnect) | Yes: `verified_via='sleeper'`, the users marker and a durable row. The JWT's user claim must equal the session's user_id. | `server.py:19307-19310`, `:19346-19371` |
| Apple, new (account-only `acct_*`) | Yes, at mint. | `:27529-27537` |
| Apple, returning | Yes, but as a **new** session: a restore session for the bound user, or a new account-only one. An unverified current session is discarded first. | `:27558-27559`, `:27600-27621` |
| ESPN entry (`entry:espn:<SWID>` or `entry:espn:<league>.t<team>`) | **No, and no route can verify it.** The import is write-gated; the credential-only store never touches `sess`. | mint `:26066-26069`, `:26110-26116`; `:28370`; `:28540-28553` |
| MFL entry (`entry:mfl:<league>.f<franchise>`; chip, league ID or "Sign in with MFL") | **No, and no route can verify it.** The entry login (`auth_leagues`) stores nothing. `POST /api/mfl/auth-link` would verify, but it is write-gated, so only an already-verified session reaches it. | mint `:26107`; `:25970-25998`; `/api/mfl/link` gated `:31336`; auth-link gated `:31680`, verifies at `:31784-31793`; `backend/tests/test_mfl_auth_link_route.py:192` |
| ESPN or MFL linked from Settings | Needs an already-verified session. MFL auth-link then re-stamps `users.verified_via='mfl_login'`, overwriting the earlier proof's marker. | `backend/accounts.py:435-442`; `server.py:31793` |
| Demo | Not mintable in prod (`landing.try_before_sync` is `false`); the section renders nothing for demo. | `server.py:26792-26793`; `config/features.json:27`; `AccountDataSection.tsx:232` |

Durable sessions come back verified (`server.py:2458-2459`), and only verified sessions are persisted
(`:2342-2349`).

#### 6.9.3 Who is stuck

| Entry / account state | Delete / Download | Step-up |
|---|---|---|
| Sleeper username, unverified session (account never verified, or verified via Sleeper, Apple or MFL) | 403, then the prompt | SleeperConnect works (the JWT claim matches). The user taps Delete again afterwards. |
| Sleeper JWT session or Apple session (verified) | succeeds | not needed |
| ESPN entry, never verified | 403, then the prompt | **Dead end.** SleeperConnect fails with `token_user_mismatch` and shows its error state (`mobile/src/screens/SleeperConnectScreen.tsx:44-47`, `:67-73`). There is no Apple path either (6.9.5). |
| MFL entry, never verified | 403, then the prompt | **Dead end**, as for ESPN. |
| MFL entry created before #279 and stamped `mfl_login` (inference) | works only while its durable 90-day session lives | **Dead end** once that session is lost: re-entry mints an unverified session, and auth-link is gated. |

- Entry users are stored with `account_only: true` (`mobile/src/screens/SignInScreen.tsx:148-156`), so
  Settings hides the "Verify account" row from them
  (`mobile/src/screens/settings/sections/AccountIdentitySection.tsx:280`). The Delete prompt still sends
  them to SleeperConnect.
- What a fresh entry leaves on the server: a users row named after the claimed team, written by
  `_extension_build_session` (`server.py:25735-25740`), and a device link (`:26121`).
- **Not traced:** whether a no-league entry user can reach Settings at all (`RootNav.tsx:453-455` sends
  them to LeaguePicker).

#### 6.9.4 New finding: entry can't import its league either

Since #279 (`a927e3a7`, 2026-09-05), a fresh ESPN or MFL entry session can't import its league. The
mint hands off to the canonical `/api/{espn,mfl}/link` import under the fresh token
(`mobile/src/api/platformEntry.ts:15`), and both routes are write-gated (`server.py:28370`, `:31336`).
`backend/tests/test_entry_platform_route.py:231-236` asserts the 403, and the tests reach the import
only by hand-setting `verified=True` (`:236`, `:484-486`). The user sees "Verify your account to link a
league." (`mobile/src/components/EspnLinkSheet.tsx:391-392`; `PlatformLinkSheet.tsx:277-278`) and has
no way to verify. The `/api/entry/platform` docstring (`server.py:25922-25926`) and
`docs/api-reference.md:128` still describe an "unverified-write grace" that #279 removed.

This is code-derived. How many `entry:*` users are stuck needs an `analytics-lead` prod read (§10).

#### 6.9.5 Proofs that exist today

| Proof | Built? | Does it verify the current session today? | What M11 needs |
|---|---|---|---|
| Apple re-auth | Yes: `AppleAuthentication.signInAsync` then `appleSignIn` (`AccountIdentitySection.tsx:108-115`, `SignInScreen.tsx:342-354`); the server verifies the token (`server.py:27684`). | **No.** An unverified session is discarded and a different session is minted or restored (`:27558-27559`); the client adopts its token silently (`mobile/src/api/auth.ts:108-110`). For an entry user with no Apple link that is a new, empty `acct_*` account: a Delete from it would delete the wrong account and report success. | A server change (M11-R2). |
| ESPN cookie re-capture | Yes: EspnConnect (`espn.webview_capture` true, `config/features.json:112`) and the verification oracle (`server.py:28158`). | **No.** The route is write-gated (`:28370`) and doesn't mark the session. The fallback `fan_profile` oracle is weak by its own docstring (`:28200-28207`), and SWIDs are readable from league data (`:26066`). | A server change; strong proof only (M11-R1). |
| MFL password | Yes (`:31743-31785`). | Only for an already-verified session (`:31680`). It doesn't check that the login owns the session's franchise. | A server change: ungated for an entry session, with franchise ownership required (M11-R1). |

#### 6.9.6 Requirements (decision: option (e))

- **M11-R1. Verified mint for proven entries.** An entry session is minted **verified** only when the
  entry carried real proof:
  - **MFL:** an MFL login whose myleagues contains the claimed franchise.
  - **ESPN:** a sign-in whose SWID owns the claimed team, proven by an authenticated, cookie-gated
    read. The weak `fan_profile` oracle is not enough.

  This fixes both import and deletion for proven entries. How the proof reaches the mint (sending the
  login with the mint call, or a short-lived proof from the discovery call) is `head-eng`'s; the MFL
  password stays transient, never stored or logged (`server.py:25984-25989`). If a public-league ESPN
  user has no cookie-gated read to prove with, that entry stays claim-only (M11-R5) until `head-eng`
  and `eng-security` name an equivalent proof.
- **M11-R2. Step-up by identity.** The Delete / Download (and profile-toggle) step-up re-runs the
  proof that matches the account's identity, chosen by the user-id prefix:
  - a numeric Sleeper id → SleeperConnect;
  - `acct_` (Apple) → an Apple re-auth that **verifies the current session's own account**. It
    never mints or adopts a different session: today's token swap (`mobile/src/api/auth.ts:108-110`)
    must not happen on this path. That is a server change (`server.py:27558-27559`);
  - `entry:mfl:` → the MFL login;
  - `entry:espn:` → the ESPN sign-in.

  It is never hard-coded to SleeperConnect. A successful step-up marks the session verified the way
  `/api/sleeper/link` does (`server.py:19346-19371`), so the user retries Delete or Download in place.
- **M11-R3. One rule for Delete and Download:** the single `_account_data_gates`
  (`server.py:27931-27942`). No second gate, and no route-specific exemption.
- **M11-R4. The protection stays:** an unverified session can't delete or export. Option (d) is
  rejected (6.9.7).
- **M11-R5. Unproven claims** (league-ID-only entries, ownerless ESPN teams) can't prove ownership.
  Product position:
  - an unverified claim creates no server account data beyond its session and device link. Today the
    mint writes a users row for every claim (`server.py:25735-25740`), so the build stops doing that
    for an unproven claim, or defers it until proof (`head-eng` decides how);
  - its "Delete" ends the session and removes this device's link (the `identity_links` row,
    `backend/database.py:2172-2190`, written at `server.py:26121`), without touching an account row
    that a real owner could hold. Sign-out already ends the session (`/api/session/signout`,
    `:28028-28052`); no route removes a device link today, so that part is a server change;
  - the entry flow steers users to the proven sign-in (MFL login, ESPN sign-in);
  - `legal-lead` confirms this meets 5.1.1(v). D-9 email remains the support fallback, not the fix.
- **M11-R6. The step-up copy names the right identity.** Today's "Your account is verified, but
  this session isn't" (`AccountDataSection.tsx:90-91`) is wrong for never-verified accounts, and
  "Verify with your Sleeper login" is wrong for every non-Sleeper account. Copy: marketing-lead.

#### 6.9.7 Rejected options

- **(a) Route the step-up by `verified_via`.** It is null for entry users, and every new proof
  overwrites it (`backend/accounts.py:435-442`; `server.py:31793`, `:27900`). M11-R2 routes by the
  user-id prefix instead.
- **(b) Apple re-auth for every account with Apple linked.** Entry users can't link Apple: linking
  needs a verified session (`server.py:27558`, `:27580-27586`). And today's Apple path swaps sessions
  (6.9.5), which is dangerous on a delete path.
- **(c) ESPN/MFL re-auth on its own** is folded into (e): it is M11-R2's `entry:*` routes, and on its
  own it leaves import broken.
- **(d) No step-up for never-verified accounts.** Entry ids are deterministic and built from public
  data (league and franchise ids; owner SWIDs read from the league), so anyone can mint a session for
  someone else's id (`server.py:26066-26069`, `:26107`). (d) would let them delete or export that
  user's data, reverse #279, and break `backend/tests/test_private_session_ownership.py:18-47`
  (`controller=None` asserts a 403 on `DELETE /api/account`).

#### 6.9.8 Acceptance criteria

- **M11-AC1.** A fresh MFL entry through "Sign in with MFL" gets a verified session. The import
  returns 200, and Delete and Download succeed without a further prompt.
- **M11-AC2.** A fresh ESPN entry through "Sign in to ESPN", with a cookie-gated read whose SWID owns
  the claimed team, gets the same result.
- **M11-AC3.** An unproven claim (league ID only, an ownerless ESPN team, or only the weak oracle)
  still gets 403 on import, Delete and Download. `test_private_session_ownership.py` stays green with
  `entry:*` ids added, and the claim writes no users row (M11-R5).
- **M11-AC4.** The Apple step-up verifies the current session's own account, or fails. It never
  returns or adopts a different session token.
- **M11-AC5.** The step-up routes by user-id prefix (M11-R2), and a structural guard fails if a
  hard-coded `navigate('SleeperConnect')` comes back.
- **M11-AC6.** The step-up copy names the account's own sign-in (M11-R6), from `marketing-lead`.
- **M11-AC7.** The TestFlight steps in the scope block pass on a fresh MFL-entry and a fresh
  ESPN-entry account.
- **M11-AC8.** CI green: `pytest backend/tests`, `tsc --noEmit`, every `mobile/tests/check-*.js`
  (`.github/workflows/ci.yml:42-48`) and testid-lint.

#### 6.9.9 Owners, size and risk

- **Build:** `onboarding-eng`. The client part rides in the 11-06 binary; the server part can deploy
  separately, and earlier.
- **`head-eng`** allocates the server files: `/api/espn/*` and `/api/mfl/*` are Platforms', and auth
  is cross-area.
- **Reviews:**
  - `platforms-pm` (P10: credential sheets and linking inside sign-in);
  - `eng-security`, on the identity proofs;
  - `legal-lead`: the proofs accepted for erasure and export, M11-R5, and the residual 5.1.1(v)
    exposure;
  - `ux-lead` (the step-up flow) and `design-lead` (the sheets).
- **`analytics-lead`:** a prod count of stuck `entry:*` users, and of `AUTH-DENY` log lines
  (`server.py:2657-2659`) on `/api/espn/link` and `/api/mfl/link`.
- **Size: M.** Server about 150–250 lines plus tests; client about 100–200 lines. **Tight for the
  11-06 binary** (flagged in §9).

#### 6.9.10 The fallback (operator decision; not taken)

If `head-eng` can't fit M11 into the 11-06 binary, Product's fallback is **option (b)** (`head-product`,
P39, 2026-10-24; Launch Desk OA-8), which replaces Product's earlier (c): hide the chips and also drop
ESPN/MFL from the listing. "(b)" and "(c)" are OA-8's labels, not §6.9.7's rejected options.
**If M11 misses 11-06, turn `landing.platform_options` off for launch.** Users sign in with Apple, then
connect ESPN or MFL from Settings, and the listing and FAQ keep ESPN/MFL with accurate wording.
`head-product` has asked `app-manager` to add the TestFlight step Apple → Settings → connect ESPN/MFL
→ import. It is still a fallback, not taken: **the decision point is 11-06**, and the flip is the
operator's call.

- **The lever exists.** `landing.platform_options` (`config/features.json:28`, comment `:29`) is the
  switch for the entry chips (`mobile/src/screens/SignInScreen.tsx:114`, `:126`), the web mirror
  (`web/js/app.js:1212`, `:1253`) and the sessionless `/api/entry/platform` route
  (`backend/server.py:25933-25934`). It needs no app build. On Render a flag change still needs a
  server deploy to reach the running process (`docs/config-reference.md:1703`). Flipping it is
  `release-lead`'s, on the operator's word.
- **Apple sign-in, then connect ESPN or MFL from Settings: yes in code, partly covered by tests, not
  checked at runtime.**
  - **Server.** An Apple account-only session is verified at mint (`server.py:27529-27537`), so the
    write gates on `/api/espn/link` (`:28370`), `/api/mfl/link` (`:31336`) and `/api/mfl/auth-link`
    (`:31680`) pass. None of the three routes checks for an `acct_` user id.
  - **Tests.** `backend/tests/test_account_only_harness.py:188-234` asserts an account-only session's
    `POST /api/espn/link` gets 200, not 401/403. It is the preview call, with no `team_id`. `:299-342`
    asserts that session_init keeps `verified` for an `acct_` user with an imported ESPN league. No
    test covers the ESPN team-claim import or any MFL link for an `acct_` user.
  - **Client.** Settings → Leagues shows "Link an ESPN league" and "Link an MFL league", gated only on
    `espn.link` / `mfl.link` (`mobile/src/screens/settings/sections/PlatformLinkSection.tsx:39-47`,
    `:58-70`). They open LeaguePicker, whose account-only empty state offers the link sheets
    (`mobile/src/screens/LeaguePickerScreen.tsx:118-129`) and lists imported platform leagues for
    account-only users (`:340-348`).
  - **Sign-in surface.** Under `onboarding.landing` the Apple path is a text link, "Already have an
    account? Sign in with Apple" (`SignInScreen.tsx:836-852`). A new Apple ID still mints an
    account-only session (`server.py:27634-27637`), but the link reads as being for returning users.
  - **So the fallback keeps "ESPN and MFL" in the listing and the FAQ**, with accurate wording
    such as "sign in with Apple, then connect ESPN or MFL" (copy: marketing-lead; `legal-lead`
    reviews the listing). The TestFlight step is `app-manager`'s, asked by `head-product`: Apple →
    Settings → connect ESPN/MFL → import (a fresh Apple account links an ESPN league and an MFL league
    from Settings, and the league opens).
- **What else the fallback touches:**
  - **FAQ:** Q2 and the meta description name all three platforms ([faq-copy.md](faq-copy.md)). Q3's
    "Sign in with Apple, Sleeper, ESPN or MFL" and Q5 and Q6 ("choose ESPN" / "choose MFL" in the
    app) describe the entry chips, so they change too.
  - **The landing page:** the chip row and the ESPN and MFL panels (`web/index.html:115-118`,
    `:189`, `:231`) hide with the flag. Its meta description ("Works with Sleeper, ESPN, and
    MyFantasyLeague", `:7`, `:12`) stays true only with the Apple-then-connect wording.
  - **The listing copy** (`app-manager` / `marketing-lead`; `legal-lead` reviews): ESPN and MFL stay,
    with the Apple-then-connect wording.
- **What the fallback doesn't fix:** entry accounts that already exist. It stops new entry accounts,
  but existing `entry:*` users still can't delete or export until M11 ships, so they stay on the D-9
  email fallback (inference; their number is `analytics-lead`'s read).

### 6.10 Review-driven build instructions (ux-lead + design-lead, accepted by Product 2026-10-23)

Two reviews of #354 at `3ca8383c`, both accepted by Product on 2026-10-23, are build instructions for
`onboarding-eng`. Their sources sit in the org-bringup worktree (`docs/plans/org-bringup/reports/`) and
aren't tracked in git, so the text is copied here **verbatim**, read 2026-10-23. Only the heading
levels changed, to fit this document; each reviewer's numbering is kept. Both reviews read code at
`origin/main` `712dcbed`. How they sit with the earlier BL-10 text is in 6.10.3.

#### 6.10.1 ux-lead: D-3, D-6, D-7 (verbatim, `reports/ux-lead.md:22-119`)

- **Input:** PR #354, `plan/launch-support-policy` @ `3ca8383c`: `prd.md` §6.1–§6.4 and §9.
- **Code:** read at `origin/main` `712dcbed`.
- **Constraint:** `head-eng`'s `timing-readout-delivery.md`, which puts the 200 ms readout on the Testing page behind `testing.timing_readout`, delivered by an allowlist experiment.
- **Date:** 2026-10-23. **Reviewer:** ux-lead, using `/ux-flow-review`.
- **Verdict:** **approve with changes.** D-3 is confirmed, D-6 is confirmed with one extension, and D-7 is specified so the readout stays reachable. The numbered list at the end is exactly what `onboarding-eng` builds.

##### D-3: the inbox row goes to Help & about — **confirmed**

- **Why:** Help & about already holds the help rows (Help & FAQ), and a person's own feedback history is help: it's where "Fixed — in next update" closes the loop (BL10-R5). A new hub group for one row would add a group for nothing.
- **Position:** directly **after Help & FAQ**, before Privacy and Terms. The order is help, feedback, legal, version.
- **The hub's About preview names the row,** e.g. "FAQ, feedback, privacy, terms" (copy: `marketing-lead`).
- **Required with the move (§6.4, item 1):** the `FeedbackInbox` route is a modal with no header close control (`navigation/RootNav.tsx:759-767`; `docs/design/components.md:77`, #130). Today only testers meet that. Once a public row opens it, every user does. Give it the close control in the header; its glyph is `design-lead`'s.
- **Recommended if cheap:** a "See your notes" link on the feedback sheet that opens the inbox.
  - The FAB's count pill counts open notes (`FeedbackFAB.tsx:126`), but tapping the FAB opens a *new note* sheet, so nothing near the pill leads to what it counts (E1).
  - If the 11-03 slot is too tight, skip it. The Help & about row alone still makes the inbox reachable.

##### D-6: hide the Screen field — **confirmed, and extended to where route names still leak**

- **Confirmed:** hide the field and keep sending the value.
  - The API needs a non-empty `screen` (`backend/server.py:11097-11098`). The sheet already falls back to `'Unknown'` (`components/FeedbackSheet.tsx:136`).
  - "Hidden" means **not rendered**: no label and no `TextInput`, so VoiceOver can't reach it either. It doesn't mean zero opacity.
- **Extension (required): route names reach the public in two other places,** so hiding the field alone doesn't do what D-6 intends:
  1. The inbox prints each note's `screen` on its row (`screens/FeedbackInboxScreen.tsx:226`). **Remove that line.**
  2. The share export groups notes under `## {screen}` headings (`state/useFeedback.ts:259-271`). **Remove the route-name grouping.** The export is a plain list of notes, newest first, with status.
- **Nothing is lost:** the server copy keeps `screen`, and that's what the `/feedback` triage reads.

##### D-7: gate the `settings/testing` page body — **specified, with the readout kept reachable**

**The predicate.** There's one tester-surface predicate, defined once and used in both places:
- `__DEV__ || testing.stage_users || testing.timing_readout`
- It's the same condition `head-eng`'s plan gives the hub row (`timing-readout-delivery.md`, step 2).
- Define it as a small exported hook, e.g. `useTesterSurface()`, next to `TestingSection`.

**Where it's used:**
- **The hub's Testing row** (`settings/SettingsHubScreen.tsx:333`) uses it. Today it reads `__DEV__ || stageUsersEnabled`.
- **The page body** (`settings/SettingsTestingScreen.tsx`):
  - **Predicate true:** render `TestingSection` as today, minus the moved inbox row. The "Test stages" row keeps its own `testing.stage_users` gate (`TestingSection.tsx:66-81`), and trades-eng's readout row keeps its own `testing.timing_readout` gate.
    - So on the operator's phone, with only `timing_readout` delivered, the page shows the readout row and nothing else, and it's never empty.
  - **Predicate false:** render an honest unavailable state, not an empty "Testing" banner. One line, e.g. "This page isn't available.", using the stale-link precedent of `RookieRanksScreen.tsx:84-86` and the state standard's *not applicable* row. The header Back stays. No other action. Copy: `marketing-lead`.

**Why the predicate must include `timing_readout`.** Gating the body on `__DEV__ || testing.stage_users` alone (the PRD's wording) would show the operator's phone the unavailable state, because `stage_users` is off there. That hides the readout, which `head-eng` ruled out.

**The flag key doesn't block the build.** `useFlag` takes any string (`state/useFeatureFlags.ts:210`), so the predicate compiles before trades-eng registers `testing.timing_readout`. The predicate stays false until the experiment delivers the key.

**File coordination (`head-eng`).** `SettingsHubScreen.tsx` and `SettingsTestingScreen.tsx` are in both onboarding-eng's D-7 and trades-eng's planned readout hunks. One owner per file per wave. I recommend:
- `onboarding-eng` lands the shared predicate and both gates.
- trades-eng's hunks then shrink to the readout row itself, which uses the hook.

##### What `onboarding-eng` builds (numbered)

1. **`AboutSection`:**
   - Add a feedback-inbox row after Help & FAQ: `testID="settings.feedback-inbox"`, title from `marketing-lead`, opening `FeedbackInbox`.
   - The section gets a `navigate` prop. Both hosts pass it: `SettingsAboutScreen`, and the flat `SettingsScreen` `aboutSection` (`:1391`).
2. **`TestingSection` and the flat `testingSection` (`SettingsScreen.tsx:1018-1053`):** remove the "Test feedback" row.
3. **The hub's About preview** (`SettingsHubScreen.tsx:211`) names the new row (copy: `marketing-lead`).
4. **`FeedbackInbox` route** (`RootNav.tsx:759-767`):
   - the public title (copy: `marketing-lead`; BL10-R2);
   - a header close control (`components.md:77`; glyph `design-lead`'s).
5. **D-6:**
   - `FeedbackSheet`: stop rendering the Screen label and input (`:207-212`), and keep sending `screen` (`:136`).
   - `FeedbackInboxScreen`: drop the per-note screen line (`:226`).
   - `useFeedback` share export: drop the `## {screen}` grouping (`:259-271`).
6. **D-7:**
   - Add `useTesterSurface()`, returning `__DEV__ || testing.stage_users || testing.timing_readout`.
   - The hub's Testing row uses it.
   - `SettingsTestingScreen` renders `TestingSection` only when it's true, and otherwise the honest unavailable state with the header Back.
7. **Guards:**
   - `mobile/tests/check-settings-ia.js`: the row table's `Test feedback` entry (`:116`) becomes the inbox row, owned by `AboutSection.tsx` with marker `settings.feedback-inbox`.
   - Add assertions that:
     - (a) `SettingsTestingScreen` and the hub row both use the one predicate, and that it includes `testing.timing_readout`;
     - (b) `FeedbackSheet` renders no Screen `TextInput` but still submits `screen`;
     - (c) no user-visible "Test feedback" string remains.
8. **Optional, if cheap:** a "See your notes" link on the feedback sheet that opens the inbox.

##### TestFlight steps

- **T1. [public account, no tester flags]** Settings → Help & about.
  - Expect: the feedback row sits after Help & FAQ and opens the inbox.
  - Expect: the inbox has a close control, and no "Test" wording or route names anywhere.
- **T2. [same]** Open the `settings/testing` link.
  - Expect: the unavailable state, and Back works. Fail if an empty "Testing" page shows.
- **T3. [the operator's phone, with `timing_readout_rollout` live]** Settings hub.
  - Expect: the Testing row shows, and the page shows the timing readout row.
  - "Test stages" shows only if `testing.stage_users` is on.
- **T4. [any]** FAB → the sheet has no Screen field. Send a note.
  - Expect: the server's copy carries a non-empty `screen` (an `/api/feedback/admin` read by the operator).

##### Decisions needed

1. **`head-eng`:** who owns `SettingsHubScreen.tsx` and `SettingsTestingScreen.tsx` this wave (I recommend `onboarding-eng` for the predicate and gates; trades-eng adds the readout row on top).
2. **`onboarding-pm`:** whether item 8 fits the 11-03 slot.

##### Handoffs (through `head-product`)

- **`onboarding-eng` via `head-eng`:** items 1–8.
- **`marketing-lead`:** the row title, the About preview, the inbox title, and the unavailable line.
- **`design-lead`:** the inbox's close control.
- **trades-eng via `head-eng`:** use `useTesterSurface()` for the readout page gate.

#### 6.10.2 design-lead: the credits row and the support/feedback copy presentation (verbatim, `reports/design-lead.md:5-82`)

**What:** [PR #354](https://github.com/mattmurf77/fantasy-trade-finder/pull/354) `plan/launch-support-policy` at `3ca8383c`: `prd.md` §5.4 (c1–c8), §6.3 BL10-R4/R5/R10, and §6.7 (f-rows), plus `leads/legal-lead-drafts.md` Part 3 (the credits row). Checked against `origin/main` `712dcbed`: `AboutSection.tsx`, `FeedbackSheet.tsx`, `TestingSection.tsx`, `web/contact.html`.

**Verdict: pass with 9 changes.** None changes approved words; all are presentation. For `onboarding-eng` (critical path, about 11-03).

##### Changes

1. **Credits text: use legal's exact wording.**
   - `AboutSection.tsx` gets legal Part 3's text verbatim:
     - "Consensus values from DynastyProcess and other published sources."
     - "Data by nflverse (https://github.com/nflverse/nfldata), CC-BY."
   - head-product's relay paraphrased the first as "other published consensus values". Legal's text governs, and KTC isn't named. Names no platforms, as legal requires.
2. **Credits row: placement and construction** (`AboutSection.tsx`, after the Terms of Use row (`:94`), before Version (`:99`)):
   - a **non-pressable** block in the existing row styles: `rowKey` "Credits", then the two sentences as two `rowSub` lines (chalk-dim, ≥4.5:1);
   - no chevron, since it isn't a navigation row;
   - the URL is shown in full as text, which satisfies the CC-BY attribution;
   - no partial-text link, which would make a tap target under 44pt;
   - one accessible element reading both lines;
   - Version stays the last row (F7 triage).
3. **Help & about row order** (`AboutSection.tsx`), matching the hub preview f18 "FAQ, feedback, privacy, terms":
   1. Help & FAQ
   2. **Your feedback** (new, BL10-R5)
   3. Privacy Policy
   4. Terms of Use
   5. Credits
   6. Version
4. **The "Your feedback" row** (moved from `TestingSection.tsx:53` onward, the "Test feedback" row):
   - the same `linkRow` construction: `rowKey` "Your feedback" (f17.title), `rowSub` f17.sub, `chevron-right` in chalk-dim;
   - in-app navigation to `FeedbackInbox`, so `AboutSection` gains a `navigate` prop;
   - testID `settings.feedback-inbox`, and `accessibilityRole="button"` (it navigates in-app; the external rows keep `link`);
   - if the open-count pill comes along, it stays the specced count pill (`--r-pill`, flare count emphasis is allowed) at the row's trailing edge, before the chevron.
   
   The same row goes in the flat `aboutSection` (`SettingsScreen.tsx:1391`) for rollback parity.
5. **FeedbackSheet support line (f3)** (`FeedbackSheet.tsx:178`):
   - the text stays `type.bodySm` chalk-dim;
   - **only `fleecedapp@gmail.com` is a tappable `mailto:`**, as nested `Text` in **chalk with an underline**, with `accessibilityRole="link"` and accessibility hint "Opens Mail";
   - not ice: the sheet's ice is already the Send button and the active kind chip, and a text link doesn't need the accent;
   - "Settings › Help & about › Your feedback" stays plain text. The sheet is a modal, so don't link the path.
   
   Import the address from BL10-R7's single constant.
6. **Hide the Screen field (f5, D-6)** (`FeedbackSheet.tsx:207-216`):
   - **remove** the "Screen" label and `TextInput` from the layout entirely (not disabled, not read-only); the pre-filled value is still sent;
   - the Note label keeps its `marginTop: space.md`, so there's no orphan gap.
   
   For `ux-lead` / D-6: the inbox row still prints the stored internal route name (`FeedbackInboxScreen.tsx:226`). Design asks that it be hidden too: an internal route name is tester vocabulary (BL10-R2's spirit).
7. **Sheet labels (f2, f4, fb.save):**
   - "Send feedback" (`:177`) keeps `type.heading`, which renders in condensed caps. Correct.
   - "What's this about?" (`:181`) is `type.label`, which renders in uppercase. Correct, keep the "?".
   - The three kind chips "Broken / Tweak / Idea" fit three `flex: 1` chips at 320pt (the longest is 6 characters at 14px Archivo 600, about 50pt in a ≈90pt chip). The chip construction stays unchanged.
   - Button "Send" (`:266`) stays primary.
8. **Contact page links need a Chalkline style** (`web/contact.html`):
   - today the body has **no `a` style** (only `.foot a`, `:63`), so the new mailto links would render in the browser's default blue or purple, a new hue (Prohibition 9);
   - add `main p a, .lede a { color: var(--chalk); text-decoration: underline; text-underline-offset: 2px; }`. The global `:focus-visible` ice ring (`:22`) covers focus;
   - **every** visible `fleecedapp@gmail.com` on the page is a `mailto:` (c1, c3, c4);
   - in the status lines c5–c7 (set from JS, `:163-171`), build the link with `createElement('a')` and `textContent`, never `innerHTML`. If that's too much for the slot, plain text is acceptable there, because c1 carries the link above.
9. **Split c4 into 3 paragraphs** (`web/contact.html:95-98`). It's about 522 characters now; head-product's ~390 predates R22.3. The words are unchanged; only paragraph breaks are added:
   - P1: "Quickest route: … Delete account."
   - P2: "If you can't use the app, email … completed within 30 days."
   - P3: "You can also pick Delete my data above while signed in on this site. The form can't send a confirmation."
   
   Wrap the in-app labels in `<strong>` (**Settings › Account & data**, **Download my data**, **Delete account**, **Delete my data**), as the page already does for its option name.

**Also fix while touching the page (SHOULD, existing debt):** the character counter `.counter` (`web/contact.html:51`) is content in `--chalk-faint` at 12px. Change it to `--chalk-dim` with `font-variant-numeric: tabular-nums` (data numerals). Chalk-faint is placeholders and disabled only.

##### What onboarding-eng builds (presentation only; words from the PRD tables, verbatim)
- **`AboutSection.tsx`**, plus the flat `aboutSection`: the row order in 3, the Your feedback row in 4, the Credits block in 1–2, and a `navigate` prop. Remove the inbox row from `TestingSection` and the flat `testingSection`. Update the hub preview f18.
- **`FeedbackSheet.tsx`:** f2, f4, f4.a11y and fb.save labels; f3 with the mailto as in 5; the Screen field removed as in 6; f1.alt in the notice slot (unchanged construction).
- **`web/contact.html`:**
  - c1–c8 verbatim;
  - the link style and mailtos in 8;
  - the c4 split in 9;
  - the counter fix;
  - the two "§3 note" strings only once marketing-lead types them.
- **Evidence (D-056):** `check_web_structure.py`; a code-walk of the hidden Screen field and the mailto targets; TestFlight steps covering:
  - Help & about shows the row order and Credits;
  - the f3 address opens Mail;
  - the sheet has no Screen field;
  - Your feedback opens the inbox.
- **Design review:** I give the `/design-review` verdict on the build diff.

#### 6.10.3 Reconciliation notes (`onboarding-pm`)

- **Agreement.** Both reviews give Help & about the same order: Help & FAQ → Your feedback → Privacy
  → Terms → Credits → Version (ux-lead D-3 "Position"; design-lead change 3). Both drop the inbox's
  route-name line (`mobile/src/screens/FeedbackInboxScreen.tsx:226`; ux-lead D-6 extension 1;
  design-lead change 6).
- **D-3, D-6 and D-7 are decided,** as recorded in §9: D-3 Help & about, after Help & FAQ; D-6 hide,
  extended per ux-lead; D-7 per ux-lead's `useTesterSurface()` = `__DEV__ || testing.stage_users ||
  testing.timing_readout`.
- **ux-lead item 8 (the "See your notes" link), `onboarding-pm`'s call:** optional and outside the
  launch ACs. `onboarding-eng` includes it only if it fits the 11-03 slot without risk; otherwise it
  goes after launch. This answers ux-lead's decision 2.
- **The credits row** (design-lead changes 1–2) enters #354 through design-lead's review and the
  launch plan, which names "the credits row" for `onboarding-eng` (`launch-plan-1118.md:19`, `:36`,
  org-bringup worktree). It uses `legal-lead`'s exact Part 3 text, as quoted in design-lead's change 1.
  It is recorded under BL-10's About-section work as BL10-R12 and BL10-AC10 (§6.3, §6.6), with its
  evidence: a structural assertion that the credits text equals legal's text, and a TestFlight step
  (Help & about shows Credits).
  - It adds no events and no flags, so BL-10's signed waivers W-BL10-1 and W-ALL-1 hold on their
    stated reasons. **Flagged for `head-product` to confirm** (§9), rather than opening new waivers.
  - **One exact string to settle.** Design-lead's change 1 ends the nflverse sentence with a period.
    Legal's Part 3 hand-off row (`leads/legal-lead-drafts.md:373`, org-bringup worktree) quotes it
    without one. The assertion needs one exact string: `legal-lead` confirms, via `head-bizops`.
- **Where the reviews change earlier text in this PRD.** For the build, the reviews govern:
  - **D-7's predicate.** §9 D-7 recommended gating on `__DEV__ || testing.stage_users`. ux-lead's
    predicate adds `testing.timing_readout`, so the operator's readout stays reachable. BL10-AC7 now
    reads with that predicate (§6.6).
  - **The inbox row's screen line.** The BL-10 TestFlight step 7 expected the inbox row to show the
    screen a note was sent from. Both reviews remove that line, so the step now checks the server copy
    instead ([scope-bl10-feedback.md](scope-bl10-feedback.md) §3).
  - **§6.4's two open items for `ux-lead`** (the inbox's close control, the `settings/testing` deep
    link) are answered by ux-lead's D-3 and D-7.
  - **The share export (f16).** ux-lead's D-6 extension 2 drops the `## {screen}` grouping. f16's
    header and labels don't change.
  - **Marketing copy already delivered.** ux-lead's handoff asks `marketing-lead` for the row title
    and the inbox title, but §6.7 already adopts "Your feedback" for both (f17.title, f8, f9), and the
    About preview is f18 (pending operator §6). What's new for `marketing-lead` is the D-7 unavailable
    line.
  - **Link color across the web pages.** Design-lead's change 8 styles `contact.html` links in chalk
    with an underline, while `privacy.html` and `terms.html` style links in ice
    (`web/privacy.html:57`, `web/terms.html:54`). Not a conflict with P28-R9, which leaves the style to
    `design-lead`; **flagged for `design-lead` to confirm the difference is intended.**
- **Open items:**
  - **`head-eng`:** file ownership of `SettingsHubScreen.tsx` and `SettingsTestingScreen.tsx` this
    wave (shared with trades-eng's readout). ux-lead recommends `onboarding-eng` for the predicate and
    gates, with trades-eng adding the readout row on top.
  - **`design-lead`:** the inbox close-control glyph.
  - **`marketing-lead`:** the row title, the About preview, the inbox title, the D-7 unavailable line,
    and the two "§3 note" contact strings (see the note above on what §6.7 already holds).

## 7. M7: privacy and terms pages

### 7.1 Verified current state

| Fact | Where | Verdict |
|---|---|---|
| "Fantasy Trade Finder" and "a small, independent hobby project" | `web/privacy.html:74-77`; `web/terms.html:66`, `:74-75` | True. Terms adds "currently in beta" and "operated by an individual, not a company with a support staff" (`:74-77`). The `<title>`/`og:` tags already say "Fleeced: Dynasty Trade Finder" (privacy `:15-21`, terms `:13-19`). |
| "a small beta service run as a hobby project" | `web/privacy.html:259-260` | True |
| §10 points to "Settings → feedback" | `web/privacy.html:279-280` | True and wrong: the button floats on every screen. |
| Terms §5 "Send in Sleeper (beta feature)"; §8 "Beta status and availability" | `web/terms.html:104`, `:128` | True |
| Effective date July 19, 2026 on both | `web/privacy.html:71`; `web/terms.html:63` | True. **Privacy was materially edited after that date** (#279, `a927e3a7`, 2026-09-05: verified sessions, email-when-enabled, ESPN/MFL tokens, purchases, deletion matrix) without a date change, although §9 promises one (`:273-274`). |
| Header comments suggest a plain support email | privacy `:2-10` (TODO at `:8-9`); terms `:2-8` (`:6-7`) | True. Terms `:4-5` and `:160-164` also carry the unresolved `[STATE]` governing-law TODO, a standing operator waiver (W1, `../web-parity/scope.md:121`). |

### 7.2 Requirements (all wording: legal-lead)

- **M7-R1.** Product name "Fleeced: Dynasty Trade Finder" (D-057) throughout the body of both pages.
- **M7-R2.** No hobby or beta characterization unless `legal-lead` keeps one deliberately and says
  so in writing (D-12). Covers privacy `:77`, `:259-260`; terms `:74-77`, `:104`, `:106`, `:128-133`.
- **M7-R3.** Contact sections (privacy §10 `:277-280`, §8 `:266-268` "contact us", §6 `:242-244`;
  terms §13 `:167-170`) name `fleecedapp@gmail.com` as a mailto link **and** the contact form. The
  feedback pointer becomes accurate (the floating button, plus the Settings → Help & about row once
  BL-10 ships).
- **M7-R4.** Effective date updated on both pages to the date the reconciled text ships.
- **M7-R5.** Header comments resolved: the "add a plain support email" TODOs are done or deleted;
  the "lawyer review" TODO is resolved or restated by `legal-lead`; `[STATE]` follows D-11.
- **M7-R6. Reconciliation.** The policy's data claims match `analytics-lead`'s data inventory
  (P12/P18). The App Store privacy labels (M6(b), answered by `legal-lead`, submitted by
  `app-manager` / `release-lead`) match the policy. The checklist in 7.3 is the working list.
- **M7-R7.** The policy covers the new support-email channel: what we receive (sender address,
  message, attachments), why, how long we keep it, and that Google processes it (Gmail). P28 and
  BL-10 create this channel, so this one is a requirement, not a candidate.
- **M7-R8.** `onboarding-eng` pastes `legal-lead`'s final text only. No agent drafts legal wording
  into the pages.

### 7.3 Policy claims checklist

Every "candidate" is `analytics-lead`'s to confirm or correct. Nothing in this table is a finding.
Line numbers are `web/privacy.html` unless stated.

| § | Current claim (short paraphrase, line) | Must be confirmed | Code evidence (candidate — analytics-lead confirms) |
|---|---|---|---|
| Intro | Operator is "Fantasy Trade Finder", a hobby project; covers website, app, extension (`:74-79`) | Legal entity/operator name for launch; extension still in scope | `extension/manifest.json`; D-057 |
| 1 | "You sign in with your Sleeper username only" (`:85-86`) | Stale: Apple sign-in is primary, ESPN/MFL leagues link too | `config/features.json:91` (`auth.accounts` true); `mobile/src/screens/CLAUDE.md` SignInScreen row; `/api/auth/apple` `backend/server.py:27670` |
| 1 | Apple/Google `sub` + SHA-256 email hash; plaintext email "when collection is enabled" (`:95-103`) | `auth.email_capture` stays off at launch; Google sign-in not offered in the app | `backend/accounts.py:236-240`, `:251`; `backend/database.py:2472`, `:2483`; `config/features.json:93` (false); `/api/auth/google` gated on `auth.accounts` (`backend/server.py:27691-27700`) |
| 1 | Rankings and activity, device snapshot (`:106-113`) | Covers imported rankings, Calibration grades, decline reasons | `backend/database.py:2141-2159` (`user_events`); `/api/rankings/import-apply` `backend/server.py:12426`; `/api/grading/sessions` `:27157`; `feedback.decline_reasons` false (`config/features.json:252`) |
| 1 | First-party usage analytics; random device ID "stored in your device's secure storage"; country code empty today (`:116-134`) | Web also mints a `dev_` ID, in browser `localStorage`, not secure storage | `mobile/src/api/client.ts:120-147`; `web/js/events.js:57-60`; `backend/database.py:2154`, `:2158-2159` |
| 1 | Feedback: text, screen, severity, device metadata; anonymous or attributed (`:137-141`) | Web contact form attributes when a web session exists; email channel is new (M7-R7) | `backend/server.py:11112-11158`; `web/contact.html:152-156` |
| 1 | Push token + platform + prefs incl. time zone (`:144-147`) | Time zone is sent on **every** request, not only with push | `backend/database.py:2297-2303`, `:2330`; `mobile/src/api/client.ts:54-61` (`X-User-TZ`) |
| 1 | Sleeper token encrypted; device secure storage; extension transient (`:150-164`) | Still accurate | `/api/sleeper/link` `backend/server.py:19245` |
| 1 | ESPN/MFL encrypted cookies/tokens; purchases "if enabled" (`:167-172`) | ESPN WebView cookie sign-in and ESPN identity binding covered; purchases dark at launch? | `backend/database.py:2413-2420`, `:2439-2445`, `:2547`, `:2578-2587`; `config/features.json:112`, `:141-148` |
| 1 | Sentry: device/OS/app version, pseudonymous Sleeper user ID tag (`:175-181`) | Still accurate | `mobile/src/observability/sentry.ts:96`, `:113` |
| 2 | No passwords stored; MFL password forwarded, token kept (`:187`) | Accurate | `/api/mfl/auth-link` `backend/server.py:31679`; `backend/database.py:2441-2442` |
| 2 | "No location ... data" (`:189`) | Whether App Privacy treats time zone or CDN country as location | `mobile/src/api/client.ts:61`; `backend/database.py:2159` |
| 2 | No third-party analytics; Sentry the only diagnostic third party (`:190`) | Still accurate | `config/features.json:121-122` (`analytics.*` first-party) |
| 3 | Anthropic receives player names + anonymous signals (`:198`) | Still in use in prod | `backend/smart_matchup_generator.py:23`, `:63`; `backend/api_observability.py:20-21` |
| 3 | Public profile "currently off" (`:199`) | Still off at launch | `config/features.json:24`, `:195` (both false) |
| 4 | Third parties: Sleeper, DynastyProcess, Render, Expo/APNs/FCM, Sentry, Anthropic, Google Fonts (`:205-211`) | Missing: ESPN and MFL (we write to them on your behalf), KeepTradeCut (value source), RevenueCat/Apple IAP (if purchases ship), Google (Gmail, M7-R7) | `config/features.json:52-53`, `:115`; `backend/data_loader.py:40-41`, `:151`; `/api/billing/revenuecat/webhook` `backend/server.py:31149` |
| 5 | "Server logs used for debugging are transient" (`:223`) | API observability keeps user-attributed request rows for 30 days | `backend/api_observability.py:33-36`, `:47-48`; `config/features.json:250` |
| 5 | Billing records retained (via §1 `:169-172`) | Raw provider payloads "never trimmed" | `backend/database.py:2587` |
| 6 | Delete at "Settings → Delete account" (`:228`) | Path is now Settings → Account & data → Delete account | `mobile/src/screens/settings/sections/AccountDataSection.tsx:250` |
| 6 | Deletion matrix (`:231-244`) | Matches `delete_user_data` | `backend/accounts.py:696` |
| 6 | Export from Settings (`:245-249`) | Accurate; verified session required | `backend/server.py:27931-27942`, `:27945-27959`; `config/features.json:191` |
| 7 | "small beta service run as a hobby project" (`:258-261`) | M7-R2 | — |
| 9 | Material changes "announced in the app" (`:273-274`) | How M7's changes get announced (D-13) | — |
| — | Browser storage not disclosed | Web keeps session token, user, league and device ID in `localStorage` | `web/js/app.js:140-142`, `:244-247`; `web/js/events.js:57-60` |

### 7.4 Collection surfaces since 2026-07-19 the policy may not cover

From `git log --since=2026-07-19` over auth, accounts, platform, analytics and observability code.
Each row is a **candidate** for `analytics-lead`; "appears covered" is a reading, not a verdict.

| Surface | Landed | Live? | Policy reading |
|---|---|---|---|
| ESPN in-app WebView cookie sign-in (`espn_s2` + `SWID`) | `b3642b33` 2026-08-08 | `espn.webview_capture` true (`config/features.json:112`) | Appears covered (`:167-169`); ESPN absent from §4 |
| ESPN identity binding (SWID ↔ user) | `1627d272` 2026-08-16 | with `espn.link` (`:110`) | Not mentioned |
| MFL sign-in (password forwarded, cookie stored) | `03e3e38c` 2026-07-25 | `mfl.auth_link` true (`:118`) | Appears covered (`:187`); MFL absent from §4 |
| ESPN and MFL trade send (writes on the user's behalf) | `cc2c1a12`, `88a29fd5` 2026-08-11 | `espn.send`, `trade.send_in_mfl` true (`:115`, `:53`) | Not mentioned; §4 describes Sleeper sending only |
| Credential vault + legacy migration | `930452c5` 2026-08-13 | yes | Appears covered (encryption claims) |
| API observability (user-attributed request rows, 30 days) | `13f5707b` 2026-08-09 | `obs.api_events` true (`:250`) | Conflicts with "transient" (`:223`) |
| Persistent sessions (DB-stored, username column) | `1580064c` 2026-07-20 | `auth.persistent_sessions` true (`:196`) | Appears covered (`:222`) |
| Paste and premium rankings import (S6; order-only, no cookies read) | `2e4ca17a` 2026-08-02; `40f7a3a9` 2026-08-16 | `ranks.import` true (`:158`); `ranks.source.dynasty_nerds` true (`:160`); DLF false (`:161`) | Not mentioned. Evidence: `backend/rankings_import.py:27-35`; `mobile/src/screens/PremiumRankingsBrowserScreen.tsx:23-24` |
| Decline reasons (two-layer pass reasons) | `c95a70aa` 2026-08-17 | `feedback.decline_reasons` false (`:252`); rows may exist | Not mentioned |
| Suggestion telemetry / ghost holdout | 2026-08-16 (flag comment `config/features.json:219`) | `suggestion.telemetry` true (`:220`) | Probably covered by "trade cards shown to you" (`:109`) and experiments (`:126-129`) |
| Calibration (blind grading) answers | `295cd951` 2026-10-07 | `grading.blind` true (`:278`) | Not mentioned |
| Purchases: RevenueCat webhook, entitlements, tip jar | `766d2261`, `b0782d80` 2026-08-28 | `monetize.*` false (`:141-148`) | Covered conditionally (`:169-172`); RevenueCat unnamed |
| Web analytics SDK device ID in `localStorage` | `877fc918` 2026-07-18 | `analytics.client_events` true (`:121`) | One day before the effective date; storage location misdescribed |
| KeepTradeCut value blend | `71e1a617` 2026-07-18 | yes | Not in §4 (no user data sent) |
| Account export | `794fb7e5` 2026-07-19 | `account.data_export` true (`:191`) | Covered (`:245-249`) |
| Apple email hash, push tokens, `X-User-TZ` | before 2026-07-19 | yes | Covered; the time-zone scope is a checklist item in 7.3 |
| **#351** Sleeper add/drop with a weekly consent record | not on `main` at `678834ab` (no reference in `git grep`) | pending | Must be covered when it lands: the consent record and the write |
| **Support email** (P28/BL-10) | this spec | at launch | Not covered: M7-R7 |

### 7.5 Wording inventory (wording: legal-lead)

| Page | Lines | What the new wording must handle |
|---|---|---|
| privacy | `:71`; terms `:63` | Effective date (M7-R4) |
| privacy | `:74-79` | Product name, operator, what the Service covers |
| privacy | `:85-92` | Sign-in methods as they are at launch |
| privacy | `:228`, `:242-244` | Accurate Settings path; deletion request by email and form |
| privacy | `:258-261` | Security statement without the hobby/beta framing (unless D-12 keeps it) |
| privacy | `:266-268`, `:277-280` | Contact: mailto + form; accurate feedback pointer |
| privacy | `:2-10`; terms `:2-8` | Header comments resolved (M7-R5) |
| privacy | new | Support email channel (M7-R7); browser storage; items `analytics-lead` confirms from 7.3/7.4 |
| terms | `:66`, `:74-78` | Product name; operator description; beta (D-12) |
| terms | `:84` | "sign-in is by Sleeper username" is stale |
| terms | `:104-109` | Platform writes, all platforms (7.6) |
| terms | `:128-133` | §8 availability; the "reset during beta" sentence |
| terms | `:160-164` | Governing law, D-11 |
| terms | `:167-170` | Contact: mailto + form |

### 7.6 Terms topics `legal-lead` must cover for launch

1. **Platform writes on the user's behalf**, every live platform: Sleeper send
   (`trade.send_in_sleeper` true, `config/features.json:52`), **ESPN send** (`espn.send` true,
   `:115`; its flag comment records an accepted residual ESPN terms/ban risk, `:114`), **MFL send**
   (`trade.send_in_mfl` true, `:53`). Terms §5 covers Sleeper only and calls it beta.
2. **#351 Sleeper add/drop with a weekly consent record**, when it lands (not on `main` at base).
3. **Third-party rankings import (S6):** users import rankings from their own paid subscriptions
   (Dynasty Nerds live, DLF dark); order only; the user's own compliance with that source's terms.
4. **Values are informational:** already §4 (`web/terms.html:97-101`); confirm it still covers
   Calibration and Usage Trends.
5. **Sign-in and eligibility:** §2 (`:83-85`) assumes a Sleeper account.
6. **Governing law** (`:160-164`): D-11.

### 7.7 Acceptance criteria

- **M7-AC1.** Neither page's body contains "Fantasy Trade Finder" or "hobby project".
- **M7-AC2.** Both pages contain `href="mailto:fleecedapp@gmail.com"` and a link to `/contact.html`;
  neither contains U+FF20.
- **M7-AC3.** Both effective dates are on or after the date the M7 text ships.
- **M7-AC4.** `privacy.html` no longer contains "Settings → feedback".
- **M7-AC5.** `analytics-lead` has marked every row of 7.3 and 7.4 confirmed or corrected, and the
  policy text matches the confirmed inventory.
- **M7-AC6.** `legal-lead` confirms the App Privacy label answers (M6(b)) match the published policy
  before `app-manager` submits them.
- **M7-AC7.** Manual read-through of both pages on desktop and mobile Safari; both mailto links open
  Mail; the Settings → Help & about Privacy and Terms rows in the app open the updated pages.

### 7.8 D-13: the in-app policy-change notice

**Status: decided by Product** (`head-product`, 2026-10-23); time-sensitive, it ships in the 11-06
binary. Spec: `onboarding-pm`. Build: `onboarding-eng`. Words: `legal-lead`, via `head-bizops`. Scope
block: [scope-d13-policy-notice.md](scope-d13-policy-notice.md) (gate 1 accepted, P39, and W-D13-1 to
W-D13-3 signed, 2026-10-24).

`legal-lead`'s R18 rules the policy change material, so it is announced in the app. Privacy §9
promises that (`web/privacy.html:273-274` at `712dcbed`). The banner ships after launch, so the launch
vehicle is the **existing what's-new tip**. That release's what's-new slot carries the policy notice,
not a feature note: the notice is required, and a first public release needs no feature note. Sources:
`bizops-banner-use-cases.md` §0 item 1 (`:44-51`) and §B6 (`:221-240`), and `in-app-banner-product.md`
(`:169-174`), all in the org-bringup worktree and untracked.

#### 7.8.1 Verified facts (at `origin/main` `712dcbed`)

| Fact | Where |
|---|---|
| The hook is `mobile/src/hooks/useWhatsNew.ts` (not `state/`). Its contract: one entry per release, keyed by the app version (`Constants.expoConfig.version`), added in the same change that bumps app.json's `version`. | `useWhatsNew.ts:8-23`, `:42` |
| The headline is one line with no period. `route` is optional; on tap the anchor navigates there and dismisses. | `:26`, `:28`; `:17-19` |
| The `WHATS_NEW` map holds one stale `'1.9.1'` placeholder, whose own headline ends in a period. The app is at `1.21.4`, so it never matches. | `useWhatsNew.ts:33-39`; `mobile/app.json:5` |
| It shows once per version: `dismiss()` stores the running version under `ftf_whats_new_seen_version`, and the entry shows only while the stored value differs. | `:41`, `:71-77`, `:79-85` |
| Flag `ux.whats_new` is `true`. | `config/features.json:175` |
| **Where it renders: only on League home, not on the League tab's landing screen.** The only consumer is `LeagueScreen`. Since #181 the League tab lands on `LeagueSummaryScreen` ("League rankings"), and `LeagueScreen` is the pushed `LeagueHome` sub-route, opened from the "League home" row or from Rank. | `LeagueScreen.tsx:115`, `:521-531`; `mobile/src/navigation/TabNav.tsx:575-592`; `LeagueSummaryScreen.tsx:1664`; `RankScreen.tsx:430` |
| The whole tip is one `Pressable` (the ✕ is an icon inside it, not a separate control). A tap logs `league_home_action_tapped` with `action: 'whats_new'`, dismisses, and navigates to `route`. | `mobile/src/components/CoachMark.tsx:18-32`; `LeagueScreen.tsx:525-529`, `:469-470` |
| **M-a holds today:** nothing dismisses the tip except that tap. `dismiss()` is called only from `LeagueScreen`'s `onDismiss`; `CoachMark` has no timer or effect; the hook has none. The tip lasts while the installed version equals the entry's key, so a later update without its own entry ends it. | `LeagueScreen.tsx:527`; `CoachMark.tsx:18-34`; `useWhatsNew.ts:49-88` |
| `SettingsAbout` ("Help & about") is a root-stack route holding the Privacy Policy and Terms rows. | `RootNav.tsx:698-701`; `AboutSection.tsx:82`, `:91` |
| `whats_new_shown` and `whats_new_tapped` are not registered anywhere (no `git grep` match). The tap's `league_home_action_tapped` is. | `backend/analytics_taxonomy.py:127`, `:1108` |

#### 7.8.2 Requirements

- **D13-R1.** One `WHATS_NEW` entry keyed to the **release binary's app.json `version`**, set in the
  same change that bumps the version, with `route: 'SettingsAbout'`. Tapping opens Settings › Help &
  about (where the policy rows live) and dismisses it. It shows once per version.
- **D13-R2.** The headline is `legal-lead`'s final text (R26.1, `leads/legal-lead.md:1255` in the
  org-bringup worktree; legal's own wording, so "we" is allowed):
  `We've updated our Privacy Policy and Terms of Use. Tap to read them` (67 characters). The hook's contract is one line with no period (`useWhatsNew.ts:26`), so
  there is **no trailing period**; the inner ". " is legal's.
- **D13-R3.** Notice, not consent: never blocking, no Accept button, dismissible.
- **D13-R4.** The stale `'1.9.1'` placeholder: remove it or leave it. It is harmless, since it never
  matches the release version. **Recommended:** remove it in the same change.
- **D13-R5.** The release slot carries no feature note (Product's call).
- **D13-R6 (M-a).** The tip stays until tapped or dismissed, with no silent expiry. This holds at
  `712dcbed` (7.8.1); the build keeps it so.
- **D13-R7 (M-b).** The policy pages carry their new effective date. M7 fixes the stale "July 19,
  2026" (`web/privacy.html:71`; M7-R4, M7-AC3).
- **D13-R8 (M-c).** Two release-notes lines, both `legal-lead`'s (R26.1, `leads/legal-lead.md:1257-1258`):
  - **First App Store update's What's New:** `Updated Privacy Policy and Terms of Use. Read them any time in Settings › Help & about.` (87 characters). A first App Store release has
    no What's New field (`leads/app-manager-app-store-submission.md:268`, E3b, "[verify on screen]";
    §7.8.3 call 2), so this line goes in the first **update**, not in v1.
  - **TestFlight "What to Test" note** for the last TestFlight build (`app-manager` formats it):
    `The Privacy Policy and Terms of Use are updated. Check the League tab shows the notice once, and that tapping it opens Settings › Help & about with both links.`
  - **Flagged, not edited:** the tip renders on League home (`LeagueScreen`, the `LeagueHome`
    sub-route, `TabNav.tsx:575-592`), one tap below the League tab's root, so "the League tab" in
    legal's line is approximate. `legal-lead` / `app-manager` may adjust the tester wording.
- **Placement (legal's R26.2, §7.8.3):** League-home-only is fine. The **Home-hub option stays an
  option only**, not a requirement.

#### 7.8.3 Product's calls on the limits (`head-product`, 2026-10-23)

1. **The tip shows only on League: accepted for v1, with the mitigations D13-R6 to D13-R8.** The
   notice is for **existing users**, today's TestFlight testers. New App Store users meet the new
   policy at sign-up, before they agree. **Correction found on verification:** the tip is on League
   home, one tap below the League tab's landing screen (7.8.1), so the surface is narrower than "the
   League tab". Legal's final TestFlight line (`leads/legal-lead.md:1258`) says "Check the League tab
   shows the notice once", which is approximate; flagged, not edited (D13-R8).
2. **No What's New field on a first App Store release: accepted.** `legal-lead`'s release-notes line
   goes in the first App Store update's What's New, and the TestFlight "What to Test" note (existing
   users) uses legal's separate TestFlight line (R26.1, D13-R8; updated 2026-10-24). The field's absence is `app-manager`'s note (`leads/app-manager-app-store-submission.md:268`,
   E3b, "[verify on screen]"), relayed to Product (`launch-readiness-product.md:146`); both in the
   org-bringup worktree.
3. **New installs see it too.** That's harmless: it's notice, not consent.

**Legal's ruling (R26.2, `leads/legal-lead.md:1264-1276`, 2026-10-23).** A once-per-version inline tip
satisfies Privacy §9 and Terms §8, so the League-home-only placement (call 1) is fine and the
**Home-hub option stays an option only**, not a requirement. Two **[PRO]** notes, neither blocking:

- **(a)** League-only reach is a nice-to-have, not a requirement.
- **(b)** Enforceability of the changed terms on existing users is review item #15; a click-through
  isn't required for launch.

Nothing about D-13 is waiting on `legal-lead`, apart from the optional tester-wording adjustment in D13-R8.

#### 7.8.4 Timing and flag sequencing (legal's R26.1; decided by Product, P39)

Legal's R26.1 (`leads/legal-lead.md:1259-1262`) requires that the tip **not appear before the new text
is live** (about 11-09), or it says "we've updated" while the links still open the old pages. The
11-06 binary reaches TestFlight testers about 11-07, and App Store users only on 11-18.

**Product's call (`head-product`, P39, 2026-10-24):** use the existing `ux.whats_new` flag, with no
new flag, so W-D13-2 stands. Two steps:

- **(i)** `ux.whats_new` **OFF in prod before the release build reaches TestFlight testers (~11-07).**
- **(ii)** `ux.whats_new` **ON once the new Privacy Policy and Terms pages are live (~11-09),**
  ideally in the same deploy.

Both flips happen on the operator's word, in `release-lead`'s session (Launch Desk OA-9). Legal's
acceptable fallback, if (i) can't be sequenced, is a gap of about two days for TestFlight testers
only (a small group); public users can't see it early.

**Consequence (inference):** until (ii), TestFlight testers don't see the tip, so the D-13 TestFlight
check (D13-AC3) and legal's tester line, which asks them to check for the notice, apply only after (ii).

#### 7.8.5 Acceptance criteria

- **D13-AC1.** A structural guard holds: `WHATS_NEW` has an entry whose key equals `mobile/app.json`
  `expo.version`, with `route === 'SettingsAbout'` and a headline exactly equal to
  `We've updated our Privacy Policy and Terms of Use. Tap to read them`, and no trailing period.
- **D13-AC2.** The code-walk in the scope block (hook → `LeagueScreen` render → tap → navigate →
  dismiss) is re-walked against the built files.
- **D13-AC3.** On an **updated** TestFlight install (after flip (ii), §7.8.4), League → League home shows the line once; a tap
  opens Settings › Help & about with the policy rows; after a relaunch it doesn't show again.
- **D13-AC4.** Nothing blocks: no Accept button, no modal.

## 7b. FAQ (SUP-M4)

`web/faq.html` is rewritten for launch with `marketing-lead`'s text (marketing-lead-copy.md §2,
2026-10-23, basis `712dcbed`). The build input, verbatim, is [faq-copy.md](faq-copy.md). The scope
block is [scope-faq-sup-m4.md](scope-faq-sup-m4.md). Build owner: `onboarding-eng`. Every word is
`marketing-lead`'s, except Q16 and Q17, which are `legal-lead`'s (R10 wording). The meaning changes
are in marketing's §6 approval block I: **pending operator §6**. Re-synced with the source as of
2026-10-23 18:17 (R22 applied): Q3 gained a release tag, Q8, Q15 and Q17 carry R22.1 edits, and Q18
gained the data-request timing.

### 7b.1 What changes (marketing §1c, summarized)

The full verdict table is copied verbatim in [faq-copy.md](faq-copy.md). Lines are `web/faq.html`
at `712dcbed`.

| Today | Line | Verdict | New item |
|---|---|---|---|
| `<title>`; meta and OG description | 6-7, 11-12 | Keep the title; rewrite the description | Head |
| H1 and sub | 126-127 | Keep | — |
| What is Fleeced? | 130-132 | Rewrite | Q1 |
| How does the ELO ranking system work? | 137-140 | Rewrite (light) | Q9 |
| 1QB PPR vs SF TEP | 145-149 | Keep | Q13 |
| Why two rank sets? | 154-156 | Keep (light) | Q14 |
| How do I sync my Sleeper league? | 161-164 | Rewrite | Q4 |
| My league is private | 169-171 | Rewrite | Q7 |
| Do you share my data? | 176-178 | Rewrite [R10] | Q15, Q16 |
| Can I use values from KTC / Dynasty Daddy? | 183-185 | Rewrite | Q10 |
| What's a "tier"? | 190-192 | Rewrite (light) | Q12 |
| What's the I AM SPEED button? | 197-199 | Cut | — |
| Is there a mobile app? | 204-206 | Rewrite | Q3 |
| Privacy policy summary | 211-213 | Rewrite [R10] | Q17 |
| Footer | 217-222 | Rewrite (adds `fleecedapp@gmail.com`) | Footer |
| — | — | New | Q2, Q5, Q6, Q8, Q11, Q18 |

### 7b.2 Requirements

- **FAQ-R1.** The builder pastes [faq-copy.md](faq-copy.md)'s §2 text and follows its build notes.
  No agent rewrites the wording. The bracketed review tags and `[APP STORE URL]` never ship.
- **FAQ-R2. Ship order (P37, `head-product`, 2026-10-23).** The FAQ goes live **with** the new
  privacy policy and terms (M7), by **Mon 2026-11-09**, before the **Tue 2026-11-10** App Store
  submission, and not before M7. Until then, today's FAQ stays. This supersedes P36's 11-13 date and
  marketing §2's original "only after the listing is live on 2026-11-06".
  - **Marketing's release-only order (R22.5) is declined.** Its §2 reads "only after the app is
    released on the App Store (planned 2026-11-18; R22.5)". But the live FAQ says the iOS app "is in
    TestFlight beta and not yet on the App Store" (`web/faq.html:206` at `712dcbed`), and an App
    Store reviewer can reach the page from the app (Settings → Help & about → Help & FAQ,
    `mobile/src/screens/settings/sections/AboutSection.tsx:64-67`).
  - `head-product` has asked `head-eng` to move the legal-pages milestone to 11-09.
- **FAQ-R3. Launch-day variants (P36, P37).** Q3's first line ("On iPhone: the Fleeced app on the
  App Store ([APP STORE URL]).") is the only "App Store" line in the text, and it is false before
  launch. It ships by 11-09 in **marketing's pre-launch variant**, which `head-bizops` is obtaining
  (copy: marketing-lead, in progress), and flips on **Wed 2026-11-18**, alongside `IOS_INSTALL_URL`
  and the `m4.348.*` rows (#348; `IOS_INSTALL_URL` isn't on `main` at `712dcbed`). At the flip,
  `[APP STORE URL]` becomes the listing's real URL.
  - Marketing's R22 revision tags the sentence "[goes live only at release, 2026-11-18, with the
    real URL; R22.1]", but gives no text for what Q3 says before release; that is the variant now
    being obtained.
  - The flip mechanism is `head-eng`'s. If it uses a flag, the FAQ scope block's §2 must name it.
- **FAQ-R4. Pricing line (P36, R21 #6).** The FAQ includes "Free to use today. Nothing in the app
  is for sale." `marketing-lead` places it (its §4 open question). It comes out the moment a
  purchase exists; `head-product` adds it to `monetization-pm`'s step-9 list.
- **FAQ-R5. Extension link (P36).** Q3's "release download" links the current GitHub release, if it
  is still `extension-v0.1.1`. Today `web/index.html:170` links
  `https://github.com/mattmurf77/fantasy-trade-finder/releases/tag/extension-v0.1.1`. Eng confirms at
  build.
- **FAQ-R6. K-factors: pending model_config confirmation.** Q9's second paragraph ("a K-factor of
  32", "8 for a like, 4 for a pass") matches the code defaults (`backend/ranking_service.py:57-59`,
  `_DEFAULT_CFG`), but prod reads `model_config`. `analytics-lead` reads prod `model_config` and
  `models-lead` confirms, via `head-bizops`. Q9 ships only once it is confirmed or corrected.
  Marketing also asks for prod `user_elo_shrink` and `placement_tier_clamp`, which Q11 describes;
  P36 doesn't cover them (open item 6 in [faq-copy.md](faq-copy.md)).
- **FAQ-R7. Legal-owned answers.** Q16 and Q17 are `legal-lead`'s (R10 wording). Q17 now carries an
  R22.1 edit. Marketing's §4 still offers Q16 a passive alternative and still lists Q17's C4
  rephrase for `legal-lead`'s OK (both in [faq-copy.md](faq-copy.md)).
- **FAQ-R8. Q18's reply promise: consistent with D-10.** Q18 now reads "Replies come within 2
  business days. Data requests are acknowledged within 2 business days and completed within 30
  days." Both match `head-bizops`'s D-10 targets. "Replies come within 2 business days." is the
  operator's own commitment. D-10's 30 days was pending `legal-lead`'s confirmation; marketing tags
  Q18's timing R22.3 / R22.4.
- **FAQ-R9. Support address.** Every `fleecedapp@gmail.com` is a `mailto:` link with an ASCII `@`,
  checked against the same `SUPPORT_EMAIL` constant as P28 and M7.
- **FAQ-R10. Q15's contrarian score.** Marketing's R22.1 edit says the score is "one number"; its
  tag asks `head-eng` to confirm the number's scope before Q15 ships.

### 7b.3 Acceptance criteria

- **FAQ-AC1.** `python3 qa/web/check_web_structure.py` passes, including the `FAQ-*` assertions in
  the scope block. `faq.html` is already in the checker's `PAGES` list, so its SEO and a11y checks
  apply to the new text.
- **FAQ-AC2.** The new FAQ is live on Render by 11-09, in the same deploy as M7 or after it.
- **FAQ-AC3.** From 11-18, the page has no "TestFlight", and the App Store link opens the listing.
- **FAQ-AC4.** The extension link equals the release link `web/index.html` uses.
- **FAQ-AC5.** No bracketed review tag and no `[APP STORE URL]` is published.
- **FAQ-AC6.** Manual read-through on desktop and iOS Safari, before and after the flip. In the
  app, Settings → Help & about → Help & FAQ opens the new page
  (`mobile/src/screens/settings/sections/AboutSection.tsx:64-67`).
- **FAQ-AC7.** Before 11-09: the operator has approved marketing §6 block I, `legal-lead` has
  approved Q16 and Q17, and Q9's K-factors are confirmed.

## 8. Sequencing and dependencies

| Item | Can start now | Blocks on | Must land before |
|---|---|---|---|
| **P28 code** (mailto markup, Send re-enable, checker assertions) | Yes: independent of copy | Nothing (placeholder text is fine on a branch) | App Store submission (Support URL must be live) |
| **P28 copy** | — | `marketing-lead` copy; `legal-lead` reviews C3-C5; D-8, D-9 | App Store submission |
| **BL-10** | Guard and constant can be built first | `marketing-lead` copy (§6.7); `design-lead` visuals; `ux-lead` row review (P10); D-1, D-2, D-6 | The first App Store build |
| **M7** | Checklist work now | `legal-lead` wording; `analytics-lead` inventory (7.3, 7.4); D-11, D-12, D-13 | **App Privacy label submission** (M6(b)) and App Store submission |
| **Q6 tour line** (§6.8) | Yes: approved, strings fixed | Nothing (operator-approved); gate-1 acceptance and waiver sign-off for its scope block | The 11-06 binary |
| **FAQ** (§7b) | `FAQ-*` assertions; the post-launch text | Operator §6 (I); `legal-lead` on Q16/Q17; Q9's `model_config` confirmation; marketing's pre-launch Q3 variant (via `head-bizops`, in progress); pricing-line placement; `head-eng`'s flip mechanism | Live by 11-09 with M7, before the 11-10 App Store submission (P37); Q3 flips 11-18 |
| **M11** (§6.9) | Server design and the `eng-security` review of the proofs (gate 1 and waivers done, P38) | `head-eng`'s server-file allocation; `platforms-pm` review; `legal-lead` on M11-R5 and the proofs; `marketing-lead` step-up copy (M11-R6) | Client: the 11-06 binary. Server: can deploy before it. Size M, tight (§9). Fallback: option (b), §6.9.10 (decision point 11-06; not taken) |
| **D-13 policy notice** (§7.8) | Yes: one map entry and its guard (legal's text is final, D13-R2) | The release version number (the entry's key). Gate 1, W-D13-1 to W-D13-3 and the flag sequencing are done (P39) | The 11-06 binary; the `ux.whats_new` flips bracket the TestFlight window (below) |

All three are App Store launch MUST or support items. P28 and BL-10 should share one review pass for
the address, since both put it in front of users. M7-R3 should land after P28's address is live, or
in the same deploy.

**Launch dates** (`head-product`, citing `launch-plan-1118.md`, 2026-10-23):

- **Launch: Wed 2026-11-18.**
- **Fri 2026-11-06: the binary is feature-complete.** Every in-app copy row lands by then: BL-10,
  including f1.alt and D-1(b), Q6, M11's client part (§6.9), the credits row (BL10-R12) and the
  D-13 what's-new line (§7.8).
- **By Mon 2026-11-09: the privacy and terms pages (M7) and the FAQ are live** (P37,
  `head-product`), before the App Store submission. The effective date is `legal-lead`'s; M7-AC3
  needs it on or after the date the text ships. `head-product` has asked `head-eng` to move the
  legal-pages milestone to 11-09; until `head-eng` moves it, `launch-plan-1118.md` still says 11-13.
- **Tue 2026-11-10: App Store submission** (P37).
- **Fri 2026-11-13: P28's contact page** goes live, per `launch-plan-1118.md`. The new privacy, terms
  and FAQ link to it and to the mailto, so this spec recommends P28 also be live by 11-09; flagged
  for `head-product` and `head-eng` (§9). The spec doesn't change P28's date.
- **2026-11-07 to 2026-11-09:** the operator runs the TestFlight checklists.
- **`ux.whats_new` flips (D-13, §7.8.4),** both on the operator's word, in `release-lead`'s session
  (Launch Desk OA-9):
  - **(i) OFF in prod before the release build reaches TestFlight testers (~2026-11-07).**
  - **(ii) ON once the new privacy and terms pages are live (~2026-11-09),** ideally in the same
    deploy.
- **M11 fallback decision point: 2026-11-06** (option (b), §6.9.10). If M11 isn't merged by then,
  `landing.platform_options` goes off for launch.
- **Launch-day flips follow 2026-11-18,** not marketing's older 2026-11-06. That covers the FAQ's
  App Store line (FAQ-R3), alongside `IOS_INSTALL_URL` and the `m4.348.*` rows.

## 9. Decisions needed

For `head-product`, with a recommendation each.

| ID | Decision | Options | Recommendation | Who |
|---|---|---|---|---|
| D-1 | **Retry trigger vs the "not sent" copy.** Code retries on return to foreground and from the inbox, not on cold launch (§6.1). | (a) The copy names only the foreground-return trigger; no code. (b) `head-eng` adds one `retrySync()` after the FAB's `hydrate()` (`FeedbackFAB.tsx:109-112`), so a cold launch also retries and the operator's "next time the app opens" holds. | **(b)**: one line, and it makes the operator's wording true. If rejected, (a). | head-product, head-eng |
| D-2 | **Unverified sessions can't send** (§6.2, candidate). | (a) Exempt `/api/feedback` from `@_gate_unverified_write`: attribute verified sessions, take others anonymously. Backend change + api-reference (`:146`, `:984`) + a pytest. (b) Client retries without the token on `verification_required`. (c) Accept; the copy hedges. | **(a)**, if head-eng confirms the 403. The route already accepts anonymous writes, so the gate protects nothing here. Touches an API contract, so it is not express-lane. | head-eng confirms; head-product decides |
| D-3 | **Inbox row placement** (P10). | Settings → Help & about (hub) + flat About; or a new "Feedback" group on the hub. | **Help & about**: it already holds help, FAQ and policy rows. `onboarding-pm` signs off; `ux-lead` reviews. | onboarding-pm, ux-lead |
| D-4 | **Flag for the row move?** | Flag it, or ship unflagged. | **Unflagged.** The flag-off state is the defect (a pill counting notes nobody can open), so a kill switch has no safe state to return to. Rollback is the next build. ADR-008's flag-everything rule was scoped to the 2026-07 remediation wave, and its doc/legal-copy exception (`docs/adr/adr-008-teardown-remediation-wave.md:21-23`) covers P28 and M7. | head-product |
| D-5 | **FAB production-build exclusion** (`FeedbackFAB.tsx:74-80`). | Retire, or keep for later. | **Retire** per operator BL-10; `head-eng` deletes the plan comments and logs a DECISIONS entry. | head-eng |
| D-6 | **Screen field for public users.** It pre-fills internal route names. | Keep editable with a public label; send silently; show read-only. | Keep sending the value (the API requires a non-empty `screen`, `backend/server.py:11097-11098`); don't ask the public to edit route names. `ux-lead` picks the presentation. | ux-lead, marketing-lead |
| D-7 | **`settings/testing` deep link** shows an empty Testing page to non-testers after the move. | Accept, or gate the page body on `__DEV__ \|\| testing.stage_users`. | Gate it, if it costs one condition; otherwise accept. | ux-lead |
| D-8 | **Keep the form's "Data request" topic?** | (a) Keep for deletion without a reply. (b) Remove; all data requests by email or in-app. | **(a)**: `privacy.html:242-244` relies on the form as the browser deletion route. `legal-lead` decides. | legal-lead |
| D-9 | **Verifying emailed data requests** (§5.3). | A written procedure before launch. | No account data emailed to an unverified sender; point requesters to the in-app verified export first. | legal-lead, head-bizops |
| D-10 | **Who monitors fleecedapp@gmail.com**, and the response target. | — | `head-bizops` names an owner; `docs/runbook.md` gets the entry. | head-bizops |
| D-11 | **Governing law `[STATE]`** (`web/terms.html:160-164`). The operator waived it on 2026-08-26 (W1). | Keep the waiver through App Store launch, or fill it. | Ask the operator again before launch; `legal-lead` advises. | operator via head-bizops |
| D-12 | **Beta/hobby wording.** | Remove all; keep some deliberately. | `legal-lead` decides. If any stays, the checker allow-lists it explicitly. | legal-lead |
| D-13 | **Announcing the policy change in the app** (privacy §9 promises it, `:273-274`). | In-app notice, what's-new, or none (if `legal-lead` deems changes non-material). | `legal-lead` rules; any in-app surface is a separate spec. | legal-lead, head-product |
| D-14 | **App Store Connect:** Support URL = `contact.html`; whether the listing also shows the address. | — | Support URL = contact page; address per `app-manager`. | app-manager |

**Decisions recorded (as of 2026-10-24)**

- **Gate 1:** `head-product` accepted this PRD and all three scope blocks at `f9762d77` on 2026-10-20 (P35).
- **Operator waiver sign-off, 2026-10-22,** given in `head-product`'s session, verbatim: "I sign off on #354's waivers." It covers W-P28-1, W-P28-2, W-BL10-1, W-BL10-2, W-M7-1, W-M7-2 and W-ALL-1.
- **Operator waiver sign-off, 2026-10-23,** given in `head-product`'s session, verbatim: "I sign off on #354's new waivers (W-Q6-1 to W-Q6-4, W-FAQ-1 to W-FAQ-3)." It covers those seven waivers. It does not cover W-M11-1 or W-M11-2, which were written after it.
- **P37,** `head-product`, 2026-10-23:
  - **Gate 1 accepted** for [scope-q6-tour-line.md](scope-q6-tour-line.md) and [scope-faq-sup-m4.md](scope-faq-sup-m4.md).
  - **FAQ go-live:** with the new privacy policy and terms, **by Mon 2026-11-09, before the Tue 2026-11-10 App Store submission** (FAQ-R2). This supersedes P36's 11-13.
  - **Marketing's release-only order (R22.5) is declined.** The live FAQ says "TestFlight beta" (`web/faq.html:206` at `712dcbed`), and a reviewer can reach it from the app.
  - **Q3 uses marketing's pre-launch variant** until the 11-18 flip. `head-bizops` is obtaining it (copy: marketing-lead, in progress).
  - `head-product` has asked `head-eng` to move the legal-pages milestone to 11-09.
- **M11, option (e),** decided by `onboarding-pm`, 2026-10-23 (§6.9, M11-R1 to M11-R6). Options (a), (b) and (d) are rejected; (c) is folded into (e).
- **Operator waiver sign-off (M11), 2026-10-23,** relayed by the coordinator, verbatim: "Decision 1: Agree to the waivers." It covers W-M11-1 and W-M11-2.
- **P38,** `head-product`, 2026-10-23: **gate 1 accepted** for [scope-m11-entry-ownership.md](scope-m11-entry-ownership.md). Option (e) fixes deletion under 5.1.1(v) and the broken ESPN/MFL import together.
- **M11 fallback: option (b)** (`head-product`, P39, 2026-10-24; Launch Desk OA-8; still a fallback, not taken). Product adopts (b) over its earlier (c); "(b)" and "(c)" are OA-8's labels, not §6.9.7's rejected options. If M11 misses 11-06, turn `landing.platform_options` off for launch. Users can sign in with Apple, then connect ESPN/MFL from Settings, and the listing and FAQ keep ESPN/MFL with accurate wording (§6.9.10). `head-product` has asked `app-manager` to add the TestFlight step Apple → Settings → connect ESPN/MFL → import. The decision point is 11-06.
- **ux-lead's and design-lead's #354 reviews accepted by Product** (2026-10-23) and folded in as build instructions (§6.10).
- **onboarding-pm on ux-lead item 8** (the "See your notes" link): optional and outside the launch ACs; included only if it fits the 11-03 slot without risk, otherwise after launch.
- **The credits row** joins BL-10's About-section work (BL10-R12, BL10-AC10), with `legal-lead`'s exact Part 3 text.
- **D-13 decided** (`head-product`, 2026-10-23): legal's R18 says the change is material, so it is announced in the app. The launch vehicle is the existing what's-new tip, and that release's slot carries the policy notice, not a feature note (§7.8). `legal-lead` writes the words via `head-bizops`; `onboarding-pm` owns the spec; `onboarding-eng` builds it in the 11-06 binary.
- **D-13's limits, Product's calls** (`head-product`, 2026-10-23; §7.8.3):
  - **The League-only tip is accepted for v1,** with mitigations: it stays until tapped or dismissed (M-a, verified to hold in code), the policy pages carry the new effective date (M-b, via M7), and the last TestFlight build's "What to Test" note carries legal's TestFlight line (M-c, `app-manager` formats it). Legal's R26.2 says this is enough, so the Home-hub option stays an option only.
  - **No What's New field on a first App Store release: accepted.** Legal's release-notes line goes in the first App Store update's What's New; the TestFlight "What to Test" note uses legal's separate TestFlight line (R26.1; updated 2026-10-24).
- **Operator waiver sign-off (D-13), 2026-10-24,** given in `head-product`'s session, verbatim: "I sign off on #354's D-13 waivers (W-D13-1 to W-D13-3)." It covers W-D13-1, W-D13-2 and W-D13-3.
- **P39,** `head-product`, 2026-10-24: **gate 1 accepted** for [scope-d13-policy-notice.md](scope-d13-policy-notice.md) at `34479ab0`.
  - **Flag sequencing:** use the existing `ux.whats_new` flag, with no new flag, so W-D13-2 stands (§7.8.4). **(i)** OFF in prod before the release build reaches TestFlight testers (~11-07); **(ii)** ON once the new Privacy Policy and Terms pages are live (~11-09), ideally in the same deploy. Both flips happen on the operator's word, in `release-lead`'s session (Launch Desk OA-9). Rationale: legal's R26.1 condition that the tip never points to the old text. Legal's acceptable fallback is a short gap for TestFlight testers only.
  - **M11 fallback:** option (b), recorded above.
- **Legal's final D-13 text and ruling** (`legal-lead`, R26.1 and R26.2, 2026-10-23; `leads/legal-lead.md:1252-1276` in the org-bringup worktree):
  - **Text:** the headline, the first-App-Store-update release-notes line and the TestFlight line are recorded verbatim in §7.8.2 (D13-R2, D13-R8). The TestFlight line's "League tab" is approximate (the tip is on League home); `legal-lead` / `app-manager` may adjust the tester wording.
  - **R26.2:** a once-per-version inline tip satisfies Privacy §9 and Terms §8, so League-home-only placement is fine. The Home-hub option stays an option only, not a requirement.
  - **[PRO] (a):** League-only reach is a nice-to-have, not a requirement.
  - **[PRO] (b):** enforceability of the changed terms on existing users is review item #15; a click-through isn't required for launch.
- **D-1 (b)** (one `retrySync()` after the FAB's `hydrate()`): chosen by `head-product`, agreed by `head-eng`.
- **D-2 (a)** (exempt `POST /api/feedback` from `@_gate_unverified_write`; attribute verified sessions, take the rest anonymously): `head-eng` confirmed the 403; `head-product` chose (a). **W-BL10-2 has lapsed**, so a pytest is required, and so are the `docs/api-reference.md` rows named in D-2 (`:146`, `:984`). It is an API contract change, so full gates apply.
- **D-3:** the inbox row goes to Settings → Help & about, directly after Help & FAQ, decided by `onboarding-pm` and confirmed by `ux-lead` (§6.10.1), with a header close control on the inbox.
- **D-4:** unflagged, chosen by `head-product`.
- **D-5** (retire the FAB's App Store build exclusion): chosen by `head-product`, agreed by `head-eng`.
- **D-10,** decided by `head-bizops`: the operator monitors fleecedapp@gmail.com; general replies go out within 2 business days; data requests are acknowledged within 2 business days and completed within 30 days (the 30 days is pending `legal-lead`'s confirmation). **Gap SUP-M7:** there is no alert for in-app feedback.
- **D-6 decided: hide** (`onboarding-pm`, matching marketing's f5): the Screen field is hidden and the sheet keeps sending the value, because the API still requires a non-empty `screen` (`backend/server.py:11097-11098`). **Extended per `ux-lead`** (§6.10.1): the inbox drops its per-note screen line, and the share export drops its route-name grouping.
- **D-7 decided, per `ux-lead`** (§6.10.1): one predicate, `useTesterSurface()` = `__DEV__ || testing.stage_users || testing.timing_readout`, used by the hub's Testing row and by the `settings/testing` page body; when it is false the page shows an honest unavailable state. This replaces the D-7 row's narrower `__DEV__ || testing.stage_users`.
- **Q6 approved** (operator, "Q6 tour line: Yes", form 2026-10-23, relayed by `head-product`): both `n23` strings become "…We never see your password." (§6.8, legal-lead LEG-S15).
- **P36,** `head-product`'s calls on `marketing-lead`'s launch copy batch (2026-10-23). The copy wording stays marketing's.
  - **f1.alt ships;** f1 is not used (D-1(b) is decided and agreed by `head-eng`).
  - **Keep f3's email line** as the way to get a reply. D-2's 403 is confirmed and the route exempted, so unverified users' notes now arrive.
  - **Resend id reuse is optional,** "if onboarding-eng finds it cheap" (BL10-R11). Each Send mints a new id (`useFeedback.ts:152-158`); f1.alt already steers users away from resending.
  - **FAQ ship order:** live with the new privacy and terms by 11-13, not before. This supersedes marketing §2's "only after the listing is live on 2026-11-06". Its App Store line gets a launch-day variant that flips on 11-18 alongside `IOS_INSTALL_URL`, like the `m4.348.*` rows. The pre-launch variant is a copy gap for `marketing-lead`. The flip mechanism is `head-eng`'s (FAQ-R3). **The 11-13 date is superseded by P37 (by 11-09), and the pre-launch variant is now being obtained.**
  - **Pricing line included:** "Free to use today. Nothing in the app is for sale." (R21 #6). `marketing-lead` places it. It comes out the moment a purchase exists; `head-product` adds it to `monetization-pm`'s step-9 list (FAQ-R4).
  - **Extension link:** the current GitHub release, if still `extension-v0.1.1`; it must match `web/index.html`'s link (FAQ-R5).
  - **Design-lead's calls:** c4's length (the split) and the f4 chips at 320pt.
  - **Legal review:** C2–C5 and C8 still need `legal-lead`'s review. FAQ Q16 and Q17 are `legal-lead`'s (R10 wording).
  - **K-factors:** the FAQ's Q9 is pending a prod `model_config` read by `analytics-lead` and `models-lead`'s confirmation, via `head-bizops` (FAQ-R6).
  - **Q18** ("Replies come within 2 business days.") is the operator's own commitment. It matches D-10.
- **Copy rows pending operator §6 (A–I), as labelled** in the §5.4 and §6.7 adopted tables and in [faq-copy.md](faq-copy.md) (block I). `name`, `typo`, `voice` and `keep` rows are adopted without approval.
- **Launch dates:** per `head-product` (`launch-plan-1118.md`), recorded in §8.
- **Scope-block gates.** [scope-q6-tour-line.md](scope-q6-tour-line.md) and [scope-faq-sup-m4.md](scope-faq-sup-m4.md): gate 1 accepted (P37) and waivers signed (2026-10-23). [scope-m11-entry-ownership.md](scope-m11-entry-ownership.md): gate 1 accepted (P38) and waivers signed (2026-10-23). [scope-d13-policy-notice.md](scope-d13-policy-notice.md): gate 1 accepted (P39) and waivers signed (2026-10-24).
- **Flags for `head-product` from marketing's R22 revision** (source as of 2026-10-23 18:17, R22 applied, its §0 item 11):
  - **C2–C5 and C8, legal review.** P36 said they "still need legal-lead's review". Marketing's R22 column now marks c2 and c5 "approved (R22.1)" and c3, c4 and c8 "edited per R22" (legal's exact text), and its §0.11 says "No row is pending". Confirm that legal-lead's review is done.
  - **D-8.** c2 now reads `Delete my data` "(D-8(a); R22.1)", and c8 no longer branches on D-8. That reads as legal-lead choosing D-8(a). Confirm, and D-8 leaves "Still open".
  - **FAQ ship order.** P36 says the FAQ goes live with the new privacy and terms by 11-13. Marketing's revised §2 (R22.5) says only after release (planned 11-18), with the policy and terms allowed to go first. **Resolved by P37:** live by 11-09, R22.5 declined (FAQ-R2, FAQ-R3).
  - **`r22.settings.rows` has no PRD home.** Marketing's new §1d row is a legal MUST (R22.2: LEG-M10 extended to MFL and Settings). It replaces "Read-only import: rankings, tiers, and trios work today." with legal's text, "Import a league to rank and find trades. Sending a trade needs that platform's sign-in.", at four sites: `mobile/src/screens/SettingsScreen.tsx:821`, `:846` and `mobile/src/screens/settings/sections/PlatformLinkSection.tsx:49`, `:74` (all verified at `712dcbed`). Marketing names `onboarding-eng` as the build owner. **Recommendation:** it rides in #354's 11-06 binary pass, with `platforms-pm`'s review, because `PlatformLinkSection` is Platforms' (P17). `head-product` decides; it is not folded into this spec's tables or scope blocks.
- **Flags for `head-product` (2026-10-23, P37 and M11):**
  - **P28's date.** `launch-plan-1118.md` still has P28's contact page live on 11-13, but the new privacy, terms and FAQ, live by 11-09, link to it and to the mailto, and the M7 block's ordering gate wants the address live on `contact.html` first or in the same deploy. **Recommendation:** P28 also goes live by 11-09. `head-product` and `head-eng` decide; this spec doesn't change P28's date.
  - **M11 (i): the import break is a launch MUST on its own.** Since #279 a fresh ESPN or MFL entry can't import its league (§6.9.4). The same change fixes it (M11-R1). `platforms-pm` should be told.
  - **M11 (ii): schedule risk.** Size M (server about 150–250 lines plus tests, client about 100–200), tight for the 11-06 binary. The server part can deploy separately.
  - **M11 (iii): M11-R5 needs `legal-lead`:** that a claim-only "Delete" (end the session, remove the device link, no account row) meets 5.1.1(v), which proofs are accepted for erasure and export, and the residual exposure for users who can't prove ownership.
- **Flags for `head-product` (2026-10-23, §6.10 and D-13):**
  - **Credits row waivers.** The credits row adds no events and no flags, so this spec treats BL-10's signed W-BL10-1 and W-ALL-1 as holding on their stated reasons. Confirm, rather than opening new waivers.
  - **D-13, the tip's surface.** It renders on League home, one tap below the League tab's landing screen (§7.8.1), not "on the League tab". Product's League-only call (§7.8.3) rests on that narrower surface; the Home-hub option may matter more. Legal's draft "What to Test" line also says "League tab". **Resolved:** legal's R26.2 rules League-home-only placement fine (the Home-hub option stays an option only), and the final TestFlight line's "League tab" is flagged in D13-R8, not edited.
  - **D-13, timing.** Legal's R26.1 asks that the tip not appear before the new pages are live, preferably by holding `ux.whats_new` false until the 11-09 pages deploy (§7.8.4). **Resolved by P39 (2026-10-24):** the existing `ux.whats_new` flag, OFF before ~11-07 and ON at ~11-09 (§7.8.4).
- **Still open:**
  - D-8, D-9, D-11 and D-12 with `legal-lead` via `head-bizops`; D-14 with `app-manager`.
  - **M11:** `legal-lead` confirms M11-R5 (via `head-bizops`); an `analytics-lead` count of affected `entry:*` users (`head-product` has requested it).
  - **§6.10 open items** (6.10.3): file ownership of `SettingsHubScreen.tsx` / `SettingsTestingScreen.tsx` (`head-eng`), the inbox close-control glyph (`design-lead`), the credits string's final period (`legal-lead`), and the marketing strings.

**Waivers** (surfaced here per the feature-scope rule; each is restated with its reason in its
scope block):

| Waiver | Scope | Reason |
|---|---|---|
| W-P28-1 | P28 §1 analytics | No new events. The form already posts through `/api/feedback`, which fires `feedback_submitted` for signed-in senders; mailto taps aren't tracked because the operator's P28 decision minimizes collection on this page. |
| W-P28-2 | P28 §3 mobile guard, pytest, TestFlight | Web-only change; no mobile or backend code. Evidence is the web checker + a manual web check. |
| W-BL10-1 | BL-10 §1 analytics | No new events; `feedback_submitted` is unchanged. |
| W-BL10-2 | BL-10 §3 pytest | No backend change, **unless D-2(a) is accepted**: then a pytest is required and this waiver lapses. **Lapsed (D-2(a) chosen; head-eng confirmed the 403).** |
| W-M7-1 | M7 §1 analytics | Static legal pages; no events. |
| W-M7-2 | M7 §3 mobile guard, pytest, TestFlight checklist | Web-only text; the in-app rows open the web URLs, which AC7's manual step covers. |
| W-ALL-1 | All §2 flags | None added. Doc/legal copy ships unflagged per ADR-008 (`:21-23`); the row move per D-4. |
| W-Q6-1 | Q6 §1 analytics | No new events: two strings change in an existing beat. `n23`'s `adoptionEvent` (`sleeper_send_attempted`, `analystScript.ts:639`) is unchanged. **Signed 2026-10-23.** |
| W-Q6-2 | Q6 §2 flags | None added. The beat already sits behind `onboarding.guided_avatar` and `onboarding.guide_v2` (both `false` at `712dcbed`), which this change doesn't touch. **Signed 2026-10-23.** |
| W-Q6-3 | Q6 §3 TestFlight checklist | The tour is dark (`calcTour.ts:472`), so no build can show the beat; the evidence is a structural assertion plus a code-walk. Lapses if either tour flag is lit: a TestFlight step is then owed. **Signed 2026-10-23.** |
| W-Q6-4 | Q6 §3 pytest | No backend code. **Signed 2026-10-23.** |
| W-FAQ-1 | FAQ §1 analytics | A static page: `web/faq.html` loads no script, so there is no events SDK and no new user action to measure. **Signed 2026-10-23.** |
| W-FAQ-2 | FAQ §2 flags | None added. Lapses if `head-eng`'s 11-18 flip uses a flag; the scope block's §2 then names it. **Signed 2026-10-23.** |
| W-FAQ-3 | FAQ §3 mobile guard, pytest, TestFlight checklist | Web-only text. The app's Help & FAQ row only opens the web URL, which the manual read-through covers. **Signed 2026-10-23.** |
| W-M11-1 | M11 §1 analytics | No new events. The re-auths reuse proof paths that already carry the `signin_*` funnel; that each step-up fires it is verified at build, and the waiver is reopened if one doesn't. **Signed 2026-10-23.** |
| W-M11-2 | M11 §2 flags | None added. The existing proof-path flags `mfl.auth_link` and `espn.webview_capture` act as kill switches: with one off, that entry stays claim-only. A recommendation; `head-eng` decides. **Signed 2026-10-23.** |
| W-D13-1 | D-13 §1 analytics | No new events. A tap already fires `league_home_action_tapped` (`whats_new`); `whats_new_shown` / `whats_new_tapped` are optional per bizops §10, and need `analytics-lead`'s grant if added later. **Signed 2026-10-24.** |
| W-D13-2 | D-13 §2 flags | None new; `ux.whats_new` is already on (`config/features.json:175`). Product's P39 sequencing only holds the existing flag off until the pages deploy (§7.8.4). **Signed 2026-10-24.** |
| W-D13-3 | D-13 §3 pytest | No backend code. **Signed 2026-10-24.** |

W-Q6-* and W-FAQ-* are covered by the 2026-10-23 sign-off, not the 2026-10-22 one. W-M11-* are
covered by the M11 sign-off of 2026-10-23 ("Decision 1: Agree to the waivers."). W-D13-* are
covered by the 2026-10-24 sign-off ("I sign off on #354's D-13 waivers (W-D13-1 to W-D13-3).").

## 10. Handoffs

| To | What |
|---|---|
| `head-product` | Accept or amend this PRD, the three scope blocks, D-1 to D-14 and the waivers. (Gate 1 is accepted for the Q6, FAQ, M11 and D-13 scope blocks: P37, P38, P39.) The R22 flags in §9: the C2–C5/C8 legal review, D-8 and a home for `r22.settings.rows` (the FAQ ship order is resolved by P37). The 2026-10-23 flags in §9: P28's date; M11 (i) to (iii); the credits-row waivers. D-13 is closed: P39 and legal's R26.2. |
| operator (via `head-product`) | Marketing §6 approval for every row labelled "pending operator §6"; the `ux.whats_new` flips (§7.8.4; W-D13-* were signed on 2026-10-24, W-Q6-*, W-FAQ-* and W-M11-* on 2026-10-23); the M11 fallback, if `head-eng` can't fit M11 by 11-06 (§6.9.10). |
| `marketing-lead` (via head-product → head-bizops) | Copy inventories §5.4 (C1-C8) and §6.7 (F1-F18): delivered 2026-10-23 and recorded in the adopted tables. Still owed for the FAQ (§7b): the **pre-launch variant** of Q3's App Store line (in progress via `head-bizops`; needed for the 11-09 go-live, P37), and where the **pricing line** goes. M11: the step-up copy that names the account's own sign-in (M11-R6). §6.10: the D-7 unavailable line (the row and inbox titles are already f17.title and f8/f9; the About preview is f18). If the M11 fallback is taken: the Apple-then-connect wording for the listing and FAQ (§6.9.10). **Copy: marketing-lead (not inventoried):** type the three "§3 note" rows (contact `:68` and `:82`, inbox `:110`; new text given in its §3, no type or §6 entry) and say whether they need operator §6. |
| `legal-lead` (via head-bizops) | §7.2 requirements, the wording inventory §7.5, terms topics §7.6, D-8, D-9, D-11, D-12; review of P28 C3-C5; App Privacy labels M6(b) reconciled with the final policy. P36: review of C2–C5 and C8 as adopted (§5.4; marketing's R22 column marks them reviewed, `head-product` to confirm); FAQ Q16 and Q17 (§7b). M11 (§6.9): which proofs are accepted for erasure and export, M11-R5, and the residual 5.1.1(v) exposure. §6.10.3: the credits text's exact final string. D-13 is done (R26.1 text and R26.2 ruling, recorded in §7.8); only an adjustment to the TestFlight line's "League tab" wording is open, with `app-manager` (D13-R8). |
| `analytics-lead` / `models-lead` (via head-bizops) | Read prod `model_config` and confirm or correct the FAQ's Q9 K-factors (32 / 8 / 4) before 11-09 (FAQ-R6). |
| `analytics-lead` | Confirm or correct every candidate in §7.3 and §7.4; publish the data inventory (P12/P18) the policy is reconciled against. M11: a prod count of stuck `entry:*` users, and of `AUTH-DENY` lines on `/api/espn/link` and `/api/mfl/link` (§6.9.9); `head-product` has requested it. |
| `design-lead` | Mailto link styling on `contact.html` and the policy pages; the sheet's support-address line; the About row; the pill. Chalkline only. P36: c4's length (the split) and the f4 chips at 320pt. M11: the step-up sheets. §6.10: the inbox close-control glyph; the `/design-review` verdict on the build diff; confirm the chalk link style on `contact.html` vs ice on the policy pages (§6.10.3). |
| `ux-lead` | Done 2026-10-23: the row move (D-3), D-6, D-7 and the inbox's close control (§6.10.1). M11: the step-up flow (M11-R2). |
| `platforms-pm` | M11 review (P10): the credential sheets and linking inside sign-in (§6.9). Also: ESPN and MFL entry can't import a league since #279 (§6.9.4). |
| `eng-security` | M11 review of the identity proofs (M11-R1, M11-R2), including what counts as a cookie-gated ESPN read. |
| `head-eng` → `onboarding-eng` | Build P28 code, BL-10 code and guard, checker assertions; retire the FAB exclusion plan (D-5); the support-address constant and the `cross-client-invariants.md` row; confirm D-1 and D-2. |
| `head-eng` → `onboarding-eng` (added 2026-10-23) | The Q6 strings and their assertion (§6.8); the FAQ build and the 11-18 flip mechanism (§7b); at build, **confirm the extension release is still `extension-v0.1.1`** and that the FAQ links the same release as `web/index.html`; BL10-R11 if cheap; confirm the scope of FAQ Q15's contrarian score (FAQ-R10). P37: move the legal-pages milestone to 11-09; decide P28's date with `head-product` (§9). M11 (§6.9): allocate the server files (`/api/espn/*` and `/api/mfl/*` are Platforms'; auth is cross-area); the client part in the 11-06 binary, the server part deployable earlier. §6.10: ux-lead's items 1–8 (item 8 optional) and design-lead's changes 1–9 plus the counter fix; decide who owns `SettingsHubScreen.tsx` and `SettingsTestingScreen.tsx` this wave (trades-eng's readout shares them). D-13 (§7.8): the `WHATS_NEW` entry and its guard in the version-bump change. |
| `app-manager` / `release-lead` | Support URL and support email in App Store Connect (D-14); App Privacy submission after M7 (M7-AC6); a build number for the BL-10 TestFlight checklist. D-13 (M-c): format legal's TestFlight line into the last TestFlight build's "What to Test" note, and legal's release-notes line into the first App Store update's What's New. If the M11 fallback is taken (`head-product` has asked): the TestFlight step Apple → Settings → connect ESPN/MFL → import. `release-lead`: the two `ux.whats_new` flips on the operator's word (§7.8.4; Launch Desk OA-9); the `landing.platform_options` flip, if the operator takes the M11 fallback (option (b), decision point 11-06, §6.9.10). |
| `head-bizops` | D-9, D-10, D-11 routing. |

## 11. Facts in the brief that changed on verification

1. **"The form posts anonymously"**: only without a web session. With one, it sends
   `X-Session-Token` (`web/contact.html:152-156`) and the note is attributed.
2. **"Unsynced notes retry automatically on app foreground"**: true for return to foreground; not
   for a cold launch (§6.1, D-1).
3. **New:** `POST /api/feedback` sits behind the verified-write gate, so unverified sessions likely
   can't send at all (§6.2, D-2; candidate).
4. **New:** privacy was materially edited on 2026-09-05 without changing its July 19 effective date
   (§7.1).
5. **New:** terms still carry the `[STATE]` governing-law placeholder under a standing waiver (D-11).
6. **New:** `mobile/tests/check-settings-ia.js:116` pins the "Test feedback" row to
   `TestingSection.tsx`, so the BL-10 build must move that migration-map row or CI fails.
7. **Root `CLAUDE.md` is stale on one point:** it says the `mobile/tests/check-*.js` suites "gate
   nothing yet", but `.github/workflows/ci.yml:42-48` runs every one of them in the
   `mobile-typecheck` job. A new guard is live in CI the moment the file exists.
8. **M11's "ESPN- and MFL-entry users may be unable to delete":** confirmed, and broader. No route
   can verify an entry session, so entry users can't import their league either (§6.9.4). The
   step-up prompt's "Your account is verified" is also wrong for accounts that were never verified
   (§6.9.1).
9. **Stale "unverified-write grace":** the `/api/entry/platform` docstring (`server.py:25922-25926`)
   and `docs/api-reference.md:128` still describe a grace path that #279 (`a927e3a7`) removed. So
   does the auth-link comment (`server.py:31780-31783`), and `docs/data-dictionary.md:254` lists
   `verified_via` values without `mfl_login`, which the code writes (`server.py:31785`). M11's docs
   row fixes all of them.
