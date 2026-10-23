# PRD — Launch support contact, public in-app feedback, policy pages (P28 · BL-10 · M7)

**Date:** 2026-10-20
**Status:** spec, awaiting acceptance by `head-product`. Specs only: no product code is written here.
**Author:** `launch-onboarding-pm-1`, for `onboarding-pm` (product lead, Onboarding & accounts)
**Source:** `head-product`'s App Store launch-readiness review (2026-10-20), items **P28**, **BL-10**, **M7**
**Base:** every `file:line` below was read at `origin/main` `678834ab`. Re-verify before building.
**Scope blocks:** [P28 contact page](scope-p28-contact.md) · [BL-10 public feedback](scope-bl10-feedback.md) · [M7 policy pages](scope-m7-policy-pages.md)

---

## Contents

1. [Problem](#1-problem)
2. [Operator decisions this spec implements](#2-operator-decisions-this-spec-implements)
3. [Ownership](#3-ownership)
4. [Scope and non-scope](#4-scope-and-non-scope)
5. [P28: contact page](#5-p28-contact-page)
6. [BL-10: in-app feedback for the public](#6-bl-10-in-app-feedback-for-the-public)
7. [M7: privacy and terms pages](#7-m7-privacy-and-terms-pages)
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

### 6.4 Open items for `ux-lead`

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
  for a `testing.stage_users` device.
- **BL10-AC8.** `POST /api/feedback` bodies still carry `severity` ∈ {`bug`,`polish`,`idea`}.
- **BL10-AC9.** CI green: `pytest backend/tests`, `tsc --noEmit`, every `mobile/tests/check-*.js`
  (the `mobile-typecheck` job runs them all, `.github/workflows/ci.yml:42-48`), testid-lint.

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

## 8. Sequencing and dependencies

| Item | Can start now | Blocks on | Must land before |
|---|---|---|---|
| **P28 code** (mailto markup, Send re-enable, checker assertions) | Yes: independent of copy | Nothing (placeholder text is fine on a branch) | App Store submission (Support URL must be live) |
| **P28 copy** | — | `marketing-lead` copy; `legal-lead` reviews C3-C5; D-8, D-9 | App Store submission |
| **BL-10** | Guard and constant can be built first | `marketing-lead` copy (§6.7); `design-lead` visuals; `ux-lead` row review (P10); D-1, D-2, D-6 | The first App Store build |
| **M7** | Checklist work now | `legal-lead` wording; `analytics-lead` inventory (7.3, 7.4); D-11, D-12, D-13 | **App Privacy label submission** (M6(b)) and App Store submission |

All three are App Store launch MUST or support items. P28 and BL-10 should share one review pass for
the address, since both put it in front of users. M7-R3 should land after P28's address is live, or
in the same deploy.

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

**Decisions recorded (as of 2026-10-23)**

- **Gate 1:** `head-product` accepted this PRD and all three scope blocks at `f9762d77` on 2026-10-20 (P35).
- **Operator waiver sign-off, 2026-10-22,** given in `head-product`'s session, verbatim: "I sign off on #354's waivers." It covers W-P28-1, W-P28-2, W-BL10-1, W-BL10-2, W-M7-1, W-M7-2 and W-ALL-1.
- **D-1 (b)** (one `retrySync()` after the FAB's `hydrate()`): chosen by `head-product`, agreed by `head-eng`.
- **D-2 (a)** (exempt `POST /api/feedback` from `@_gate_unverified_write`; attribute verified sessions, take the rest anonymously): `head-eng` confirmed the 403; `head-product` chose (a). **W-BL10-2 has lapsed**, so a pytest is required, and so are the `docs/api-reference.md` rows named in D-2 (`:146`, `:984`). It is an API contract change, so full gates apply.
- **D-3:** the inbox row goes to Settings → Help & about, decided by `onboarding-pm`; pending `ux-lead`'s review.
- **D-4:** unflagged, chosen by `head-product`.
- **D-5** (retire the FAB's App Store build exclusion): chosen by `head-product`, agreed by `head-eng`.
- **D-10,** decided by `head-bizops`: the operator monitors fleecedapp@gmail.com; general replies go out within 2 business days; data requests are acknowledged within 2 business days and completed within 30 days (the 30 days is pending `legal-lead`'s confirmation). **Gap SUP-M7:** there is no alert for in-app feedback.
- **Still open:** D-6 and D-7 with `ux-lead`; D-8, D-9, D-11, D-12 and D-13 with `legal-lead` via `head-bizops`; D-14 with `app-manager`.

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

## 10. Handoffs

| To | What |
|---|---|
| `head-product` | Accept or amend this PRD, the three scope blocks, D-1 to D-14 and the waivers. |
| `marketing-lead` (via head-product → head-bizops) | Copy inventories §5.4 (C1-C8) and §6.7 (F1-F18). |
| `legal-lead` (via head-bizops) | §7.2 requirements, the wording inventory §7.5, terms topics §7.6, D-8, D-9, D-11, D-12, D-13; review of P28 C3-C5; App Privacy labels M6(b) reconciled with the final policy. |
| `analytics-lead` | Confirm or correct every candidate in §7.3 and §7.4; publish the data inventory (P12/P18) the policy is reconciled against. |
| `design-lead` | Mailto link styling on `contact.html` and the policy pages; the sheet's support-address line; the About row; the pill. Chalkline only. |
| `ux-lead` | Review the row move (§6.3 BL10-R5, D-3); D-6, D-7; the inbox modal's missing close control (§6.4). |
| `head-eng` → `onboarding-eng` | Build P28 code, BL-10 code and guard, checker assertions; retire the FAB exclusion plan (D-5); the support-address constant and the `cross-client-invariants.md` row; confirm D-1 and D-2. |
| `app-manager` / `release-lead` | Support URL and support email in App Store Connect (D-14); App Privacy submission after M7 (M7-AC6); a build number for the BL-10 TestFlight checklist. |
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
