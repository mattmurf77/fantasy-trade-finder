# PRD — Referral loop v1: credited, measured league invites

> Requirements for making the league invite loop work end to end: an existing user's
> invite reaches a leaguemate, the leaguemate becomes an activated Fleeced user, the
> inviter is credited and told, and every hop is measured per inviter.
> **Status:** PRD drafted 2026-10-15; revised 2026-10-15 to fold `head-product` rulings P20
> (reward-free v1), P9 (old-name strings outside this PRD's own FRs go to P9's copy-defect
> batch) and P21 (the `docs/plans/README.md` row is approved); nothing else changes. Revised
> again 2026-10-15 to fold `design-lead`'s mockup lab (draft PR #343, §13) per `growth-pm`'s
> rulings: OG card variant (ii), no `dtf://` button in v1, desktop iOS line only with
> `IOS_INSTALL_URL`, banner Invite floors (AC-4b), web invite emphasis colour (AC-9b), open
> copy questions (D-14). Then revised to fold `marketing-lead`'s answers to those questions
> ([marketing-inputs.md, lab addendum](marketing-inputs.md#addendum-design-leads-lab-slots-and-growth-pms-four-questions-2026-10-15),
> re-copied; every string still proposed, pending the operator's approval of words): landing
> headline ladder, A2 note, OG lockup, "leaguemates", the stage-7 activation title, the
> landing value line, the desktop-extension risk, and an open wordmark item (D-15). Revised
> again 2026-10-15 to fold the operator's ruling on D-1 (option A) and D-3 (the operator
> creates the public TestFlight link); `head-product`'s first build slice for `head-eng`
> (FR-7, FR-8, FR-9, §8.2, `IOS_INSTALL_URL`, plus the `/s/*` CTA target pulled forward as
> FR-25; §12); `analytics-lead`'s P18 and baseline answers (§8.4, §10, D-11); `growth-pm`'s
> surface vocabulary (§10); and `head-product`'s proposed wordmark-period rule (D-15). A
> follow-up the same day records `growth-pm`'s `signup` attribution values (§10), accepts
> FR-25's gate (`growth.join_landing`), and closes D-15 (`design-lead`, PR #349). A second
> follow-up re-copies [marketing-inputs.md](marketing-inputs.md) after `marketing-lead`'s
> FR-25 addendum and gives FR-25 a label and help line per device branch (AC-25 asserts
> them; still proposed, D-5). Revised again 2026-10-15 to fold the gate-1 reviews, per
> `growth-pm`'s rulings: `ux-lead`'s flow review of PR #348 (approve with changes, R-F1…R-F8,
> and its TestFlight checklist steps), `analytics-lead`'s §1 review (conditions C1–C9 and the
> missing `share_link_opened` row) and its granted events addendum
> (`docs/business/analytics/2026-10-15-referral-loop-events.md`, cited below as **analytics
> addendum, PR #350**, with requests R1–R3). Revised again 2026-10-15 to close D-16:
> `design-lead` confirmed R-F3 with specs for the desktop QR block and R-F1's A1 step list
> (FR-7, AC-7c, new AC-7f: the QR is server-side inline SVG, never a third-party service);
> the `/s/*` QR and its Chalkline chrome fold into GB-02 (FR-25). Then revised to fold
> `marketing-lead`'s strings for the `ux-lead` changes (re-copied
> [marketing-inputs.md](marketing-inputs.md), lab addendum, "`ux-lead`'s review of PR
> #348"; all proposed, D-5): A1's step 1 / step 2, the desktop QR state's labels, the iPad
> link, the FR-19 activation body, the TestFlight "What to Test" line, the contingent
> installed-user line and the revised A2 note. Then revised to fold `design-lead`'s QR
> density rule (FR-7, AC-7f: EC M up to version 6, ≥200 CSS px, whole-pixel modules
> ≥4 CSS px; version 7+ grows, never shrinks), replacing "version ≤4 / ≥180 px".
> Revised 2026-10-23 per `growth-pm`'s calls, after the operator put the referral loop on the
> launch critical path ("Launch relies on invites: Yes, hold for it."): launch-day copy from
> the marketing-lead copy batch, 2026-10-23 (all proposed, D-5), with the iPhone install
> labels following the `IOS_INSTALL_URL` host, not a date (FR-7, AC-7g, FR-25); the Android
> note and `gp.join.og_desc`; AC-25's href is `head-eng`'s contract C5, `/?share=<kind>`;
> FR-8 stamps only a same-league row (F1's league rule); and §12's launch slice for the
> Wed 2026-11-18 launch.
> Revised again 2026-10-23 to fold `marketing-lead`'s referral approval package, vendored as
> [marketing-referral-approval.md](marketing-referral-approval.md), now **the launch-slice
> authority for referral wording** (`head-product`, 2026-10-23; `marketing-inputs.md` stays
> the drafting record): drift D4–D6 (the iPad store line, the QR's accessible name, one
> invite line with no league name), `gp.join.og_title`, `gp.join.valueprop`,
> `gp.join.page_title` and the FR-18 body; the operator's approval of its §2 (26 entries,
> D-5); and its §4 later-slice strings (§12).
> Revised again 2026-10-23 to fold `growth-pm`'s rulings on the package's open items (§6,
> U2–U4): FR-11 joins the 11-06 binary (U2); FR-18 is in the launch slice, server-side,
> target 11-16, and the `m3.push.joined` name fix lands by 11-16 even if FR-18 slips (U3);
> `release-lead` checks `IOS_INSTALL_URL`'s host on 11-18, and a store-era unset note is
> later slice (U4) (FR-11, FR-18, §12, §16).
> **Gate-1 inputs folded (ux-lead, analytics-lead, PR #350); design-review verdict comes on
> the build branch before ship.**
> Acceptance of the whole PRD (D-6) is still with `head-product`. Requirements only: **no
> source file is changed by this document.**
> **Owner:** `growth-pm`. **Base:** `origin/main` 678834ab. **Branch:** `plan/referral-loop`.
> **Evidence:** [loop-audit.md](loop-audit.md) (hop table H1–H8, re-verified at 678834ab).
> **Scope block:** [scope.md](scope.md). **Backlog row:** GB-01 in
> [`docs/business/product/growth-backlog.md`](../../business/product/growth-backlog.md).
>
> **Gate posture: FULL GATES.** This change adds a table's writer and columns, two API
> routes, an API contract change, flags and analytics events: four bright-line surfaces in
> root `CLAUDE.md` §Conventions. Express is not available and agents never self-select it.

**Operator ask (2026-10-15, verbatim, via `head-product`):** "Growth loops. Need to be built
and need to work. Referral growth loop is the primary one, but have the PM come up with
other ideas." Other ideas are ranked in the growth backlog (GB-02…GB-14).

**Operator ruling (2026-10-15, verbatim, via `head-product`):** "Ok. start building D1 and
D3". D-1 is resolved as option A; D-3 is resolved as: the operator creates the public
TestFlight link (§5, §15).

## Contents

- [1. Problem and evidence](#1-problem-and-evidence)
- [2. Goal and measured target](#2-goal-and-measured-target)
- [3. Non-goals](#3-non-goals)
- [4. User journeys](#4-user-journeys)
- [5. CTA target before the App Store listing (operator decision)](#5-cta-target-before-the-app-store-listing-operator-decision)
- [6. Requirements](#6-requirements)
- [7. Attribution design](#7-attribution-design)
- [8. API contracts](#8-api-contracts)
- [9. Schema deltas](#9-schema-deltas)
- [10. Events (proposals for analytics-lead)](#10-events-proposals-for-analytics-lead)
- [11. Flags and config](#11-flags-and-config)
- [12. Phasing and rollout](#12-phasing-and-rollout)
- [13. Seams and reviews](#13-seams-and-reviews)
- [14. Risks](#14-risks)
- [15. Decisions needed](#15-decisions-needed)
- [16. Handoffs](#16-handoffs)
- [17. Docs](#17-docs)

---

## 1. Problem and evidence

Every Fleeced user sits in a league with 9–11 other managers. The invite is league-scoped,
which makes it both the distribution channel and the fraud control. The loop exists in code
and is broken or blind at most hops ([loop-audit.md § Breaks, ranked](loop-audit.md#breaks-ranked)):

| # | Break (hop) | Evidence |
|---|---|---|
| 1 | **A phone invitee without the app dead-ends (H3a).** The join path 302s to the generic `/`; web sign-in needs the desktop Fleeced extension; there is no install link; an install loses the invite | `backend/server.py:12596-12624`; `web/js/browser-auth.js:1, :45`; `web/js/app.js:334, :1262-1266`; `living-memory/NEXT.md:145-148` |
| 2 | **Attribution is a username string, Sleeper-only, insert-only and spoofable (H2, H5).** ESPN/MFL/Fleaflicker session-init sends nothing; a crafted `?ref=` makes the inviter row fire at anyone; web writes `username = display_name`, so web-last inviters don't resolve | `mobile/src/api/auth.ts:442-456, :494-515, :590-608`; `web/js/app.js:801, :810`; `server.py:22649-22675`; `backend/database.py:462, :5122-5156, :12597-12617` |
| 3 | **The web leg is silent (H1g, H3a).** The 302 logs nothing; the web invite modal and landing fire no events | `server.py:12596-12624`; `web/js/app.js:5822-6136, :6390-6416` |
| 4 | **The inviter is told at signup, not first value; told twice; and nothing is evented (H6, H7)** | `server.py:22649-22720`; `database.py:12620-12634`; `mobile/src/components/TopBar.tsx:499-501` |
| 5 | **Measurement is dark and mislabelled (H8).** "k_factor" is a join count; "K-factor" already means the Elo update size | `server.py:26232-26307`; `docs/glossary.md:29` |
| 6 | **Legacy link + signed-in user doesn't route (H3b)** | `mobile/src/utils/deepLinks.ts:444` |
| 7 | **Impressions uneven (H1)** and **old brand strings** across the loop (D-057) | `InviteLeaguematesBanner.tsx:132, :151-153`; `server.py:22662` |

The `referrals` table (`backend/database.py:2595-2617`) was designed for exactly this ledger
(referrer, referred, league, token, `joined_at`, `activated_at`) and has never had a writer.

---

## 2. Goal and measured target

**"Works" means:** an existing user's invite reaches a leaguemate → the leaguemate becomes an
activated Fleeced user → the inviter is credited and told → every hop is measured per
inviter.

### 2.1 Instrumentation target (hard; verifiable at Phase 1 ship + 2 weeks)

1. **≥95%** of new users whose first session follows an invite open (same device via the
   invite intent, or same league via a recorded landing open in the prior 14 days) carry a
   `referrals` row in status `joined` or later.
2. Every hop H1–H8 has an event or a ledger timestamp; **zero GAP rows** remain in the hop
   table for Phase 1 surfaces.

Numerator and denominator come from §10's `signup.attribution` / `attribution_miss` props
and the ledger; the query is `analytics-lead`'s (§2.4).

### 2.2 Outcome target (**assumed**; recalibrate when `analytics-lead`'s W3 baseline lands)

**Loop coefficient `K_30`** = referrals reaching `activated` in a 30-day window ÷ users
active in that window. Target **K_30 ≥ 0.15 by 8 weeks after Phase 1 ships**, with
**joined → activated ≥ 40%**. "Active" uses `analytics-lead`'s active-user definition.

`K_30 = i × o × j × a`. Values below are **assumed** and chosen only so each can be
checked against the baseline:

| Term | Meaning | Assumed value | Source once live |
|---|---|---|---|
| `i` | invites shared per active user per 30 days | 0.5 | `invite_shared` (all surfaces, both clients) ÷ active users |
| `o` | opens per share | 1.5 (a group-chat share reaches several leaguemates, so this can exceed 1) | ledger `open_count` + `invite_link_opened` with `invite_id` |
| `j` | joins per open | 0.5 | ledger `joined` ÷ opens |
| `a` | activated per join: the invitee's first trade opinion (funnel stage 7, FR-17) within 14 days of `joined_at` | 0.4 | ledger `activated` ÷ `joined` |
| **K_30** | | **0.5 × 1.5 × 0.5 × 0.4 = 0.15** | |

Stage 7 is a stricter bar than the first-suggestions bar `a` was first assumed against, so
it may land below 0.4; the W3 baseline recalibrates it.

Two honest limits: a league caps `i` at the leaguemates not yet joined (~9–11 minus joined),
and spread past one league happens only when an invitee brings their other leagues. K below
1 still compounds: each acquired user brings `1/(1−K)` users in total (K = 0.15 → ×1.18).

### 2.3 Guardrails

- `invite_pin_failed` rate (by `reason`) does not rise versus the pre-ship baseline.
- Notification opt-outs (`notif_pref_changed` turning off the bucket that carries the
  inviter rows) do not rise.
- Invite spam ceiling: **≤10 invite links minted per inviter per league per UTC day**
  (**assumed**; enforced by FR-6).
- No change to the five core-loop guardrails
  (`docs/business/product/2026-07-17-pfo-measurement-spec.md` § Core-loop guardrail set).

### 2.4 Readout and experiment posture

- **Readout:** `analytics-lead` writes a per-inviter and program-level query over the ledger
  plus events (FR-22): links created, invites shared, landing opens, app opens, joined,
  activated, method split (token vs league_match), `K_30` numerator and denominator, and the
  §2.3 guardrails. Weekly while flags ramp.
- **No A/B in v1.** At beta scale an A/B on invite copy or landing is underpowered (the
  `PRD-p1-5.md:196` OG-10 deferral still holds). The plan is a **before/after read** with the
  §2.1 instrumentation target as the gate. If the operator wants a test, `analytics-lead` runs
  `/an-experiment`'s power preview first.

---

## 3. Non-goals

Each was considered and excluded; recorded so nobody reopens it mid-build.

1. **Attribution SDK / deferred deep link.** Still known-unsolvable inside our constraints
   (`docs/plans/audit-p0-remediation/prd-p0-3.md:194-201`). The re-tap step (FR-7) and
   league-match fallback (FR-14) substitute.
2. **Rewards.** v1 ships reward-free: status and recognition only (`head-product` P20,
   2026-10-15). Rewards are paid entitlement time, so they come later (Phase 3, §12), gated
   on the operator approving `monetization-pm`'s pricing memo: `monetization-pm` designs the
   reward economics; `growth-pm` defines "activated" (FR-17) and the mechanics.
   `growth.referral` stays reserved for that program.
3. **Re-engagement credit** for an existing user who opens an invite. Backlog GB-12.
4. **"Who invited you?" picker** ([marketing-inputs.md §C](marketing-inputs.md#c-utm--install-source-convention-mkt-seo) recovery iii). A new write route; not v1.
5. **Clipboard-based deferred linking.** iOS paste prompt; rejected in [marketing-inputs.md §C](marketing-inputs.md#c-utm--install-source-convention-mkt-seo).
6. **UTMs on invite links.** The ledger row records the surface at mint, so invite links need
   no UTMs and the join redirect's closed parameter contract (test T7,
   `backend/tests/test_invite_links.py:132-136`) is **not** reversed. First-touch UTMs for
   non-invite traffic are a separate proposal (FR-16, §8.4).
7. **`/s/*` share landings, apart from their CTA target and its per-device label.** Their
   `ref` forwarding, OG image and absolute `og:image`, and robots fixes stay in GB-02. The CTA
   target, with its label and help line per device, moved into Phase 1's first build slice
   (FR-25; `head-product`, 2026-10-15).
8. **`/s/trade` enumeration.** A security handoff to `head-eng`, not this build.
9. **Retiring legacy URL parsing.** D-028: `/?league=&ref=` is parsed forever. New links stop
   *emitting* `ref` (FR-2); nothing stops *reading* it.
10. **APNs referral push** and the inviter-facing **"Your invites" surface.** Phase 2.
11. **An Android app.** Android invitees get an honest note (§5).
12. **Copy A/B.** §2.4.
13. **A `dtf://` "Open in the app" button on the join landing.** Considered and rejected for
    v1 (`growth-pm`, 2026-10-15, on `design-lead`'s lab, §13): on an iPhone without the app,
    Safari shows an "address is invalid" alert, a bad first impression on the very screen
    meant to win the install.

---

## 4. User journeys

Words in quotes are `marketing-lead`'s strings, keys named. The launch-slice strings are
[marketing-referral-approval.md §2](marketing-referral-approval.md#2-operator-approval),
**approved by the operator 2026-10-23** (D-5); that file is the launch-slice authority for
referral wording. The later-slice strings
([§4](marketing-referral-approval.md#4-later-slice-not-in-the-11-06-binary-not-in-this-approval),
listed in §12; e.g. the activation row in step 5) are still **proposed**
([marketing-inputs.md §A](marketing-inputs.md#a-copy-table-mkt-writer)), pending the operator.

### J1 — Inviter

1. Taps Invite on League Home, the members overlay, Matches mutual-empty, the bell's empty
   state, the Trades cold-start banner, or the web invite modal.
2. The button shows a pending state for up to 2 s while the app mints an invite id (FR-1).
   If minting fails, the share proceeds with a league-only link (FR-1, FR-2). Repeat taps
   are ignored while the mint is pending: one tap, one mint, one share sheet (AC-1e).
3. The share sheet opens with "Join me on Fleeced to find trades we both like → {url}"
   (`gp.invite.msg`) and a link carrying `t=<invite_id>` and no username. **One invite line
   everywhere, with no league name, SMS included** ([package §5 D6](marketing-referral-approval.md#5-drift-marketings-file-vs-the-prd--91f1cc29-7)):
   the web modal's default (`h2.web.default`) and its SMS channel (`h2.web.sms`) reuse it;
   only the web X channel keeps its own line (FR-3). The league-name variant
   `gp.invite.msg_league` is parked (later slice, §12).
4. When a leaguemate joins: one bell row, "@{new_username} joined Fleeced via your invite"
   (`gp.push.joined_inbox_title`) with a distinct body line, "Once they rank, trades with
   them can use their board, not just consensus." (`gp.push.joined_inbox_body`, FR-18).
5. When that leaguemate first likes or passes a trade (funnel stage 7, FR-17): a second
   bell row, "@{new_username} weighed in on their first trade" (`gp.inbox.activated_title`;
   later slice, not in the operator's 2026-10-23 approval, §12).
   The tap opens Trades (FR-19), which lands on the hub home while `trades.finder_hub` is
   on, so the body (`gp.inbox.activated_body`) no longer promises the deck: "When they like
   a trade with you, it can show up with a "They're interested" tag." (proposed, FR-19;
   `ux-lead` R-F6; the earlier "If they like a trade with you, it can surface in your
   deck." is withdrawn).

### J2 — Invitee, app not installed

- **iPhone (option A):** taps the link in Messages or a league chat → Safari → join landing:
  "{display name} invited you to {league}" (FR-7's headline ladder), then one task in two
  numbered steps (`ux-lead` R-F1). Strings by `marketing-lead`, approved by the operator
  2026-10-23 ([package §2](marketing-referral-approval.md#2-operator-approval), D-5;
  drafted in [marketing-inputs.md, lab addendum](marketing-inputs.md#addendum-design-leads-lab-slots-and-growth-pms-four-questions-2026-10-15),
  "`ux-lead`'s review of PR #348"):
  - **Step 1**, headed "Install Fleeced" (`gp.join.step1`): "Get the iOS beta"
    (`gp.join.cta.A_ios`) to the public TestFlight link, with "Installs through Apple's
    TestFlight app." (`gp.join.cta.A_ios_help`); the button and help line are unchanged.
    Once `IOS_INSTALL_URL` is the App Store URL, the pair is "Get the iPhone app" / "Opens
    the App Store." (FR-7's host rule; marketing-lead copy batch, 2026-10-23).
  - **Step 2**, the re-tap: "Tap the invite again, or rescan its code, to join
    {leagueName}." (`gp.join.step2`, replacing `gp.join.retap` on A1; fallback "…to join
    your league."). It is neutral on purpose: an invitee who scanned the desktop QR has no
    chat to go back to, and the landing can't tell the two arrivals apart.
  - The step framing's words are `marketing-lead`'s; its layout is `design-lead`'s,
    confirmed 2026-10-15 (FR-7, D-16). TestFlight shows the build's "What to Test" text
    beside its Open button, so the operator pastes in `gp.testflight.what_to_test`: "Here
    from a league invite? After installing, go back and tap the invite again, or rescan its
    code. That opens the app on your invite." (D-2; no league name). No `dtf://` "Open in
    the app" button (§3 non-goal 13).
  - Re-tap after installing → universal link → J3 with the invite id → credited by **token**.
  - A re-tap inside an in-app browser (Sleeper's league chat, Discord, GroupMe) may reopen
    the landing instead of the app (`ux-lead` R-F2). Checklist step 4b tests it (scope §3).
    **Contingent:** if any in-app browser reopens the landing, A1 and A2 gain a line for
    installed users, "Have the app and still seeing this page? Open this link in Safari, or
    tap it in Messages." (`gp.join.iab_wayout`; approved with package §2, but it ships only
    if step 4b fails). On A2 it replaces the note's last
    sentence rather than adding a third. Step 4b tests both routes; if Safari doesn't hand
    off to the app, the line is cut to "…Tap the invite in Messages."
  - No re-tap → the app cold-opens without the link → the user signs in and picks the
    league → credited by **league match** if their landing open was recorded (FR-14).
  - **`IOS_INSTALL_URL` unset:** the honest note only, "The iPhone beta isn't open to the
    public yet. Already have it? Tap the invite again, or rescan its code.", with no button
    and no TestFlight-request link (FR-7).
- **Desktop** (and iPad, whose Safari presents a desktop user agent): web sign-in needs the
  sideloaded extension, so most desktop invitees can't finish on the web (§5, `ux-lead`
  R-F3).
  - **`IOS_INSTALL_URL` set** (R-F3, decided by `growth-pm`, P19): the primary action is
    "Join on your iPhone" (`gp.join.desktop.qr_title`, replacing the working label "Get it
    on your iPhone") with a **QR code of the same invite URL, `t` included** (FR-7) and
    "Scan with your iPhone camera. After installing, scan again to join."
    (`gp.join.desktop.qr_help`). Scanning it on an iPhone opens the landing there (the
    iPhone path above); scanning it again after installing *is* the re-tap, so the universal
    link opens the app and credits by **token** (that the Camera opens a universal link is
    **assumed** until checklist steps 11b and 15b run). The secondary is the line "Have the
    Fleeced extension for Chrome or Edge?" (`gp.join.desktop.ext_lead`) with the button
    "Open the web app" (`gp.join.cta.A_desktop`) → `/?league=&t=` → extension sign-in →
    invited league auto-selected → credited by token. An iPad can't scan its own screen, so
    the QR block keeps the iOS install link as a text link: "On an iPad? Get the iOS beta,
    then tap the invite again." (`gp.join.desktop.ipad`; on the App Store host, "On an iPad?
    Get the iPhone app, then tap the invite again.", adopted verbatim, package §5 D4; FR-7).
    The QR's accessible name is "QR code: opens this invite on your iPhone"
    (`gp.join.desktop.qr_a11y`, adopted verbatim, D5). Words `marketing-lead`, approved by the
    operator 2026-10-23 (D-5, package §2); layout confirmed by `design-lead` 2026-10-15 (D-16
    resolved; specs in FR-7).
  - **`IOS_INSTALL_URL` unset:** "Open the web app" (`gp.join.cta.A_desktop`) with "Sign-in
    uses the Fleeced extension for Chrome or Edge." (`gp.join.cta.A_desktop_help`) →
    `/?league=&t=` → extension sign-in → invited league auto-selected → credited by token.
    No QR and no iOS link (its click-through 404s, §8.2, so it would be a dead path).
- **Android or another phone:** landing → "Available on iPhone and desktop web for now."
  (`gp.join.android_note` = `m4.348.android_note`, marketing-lead copy batch, 2026-10-23:
  "Fleeced" is never the subject in system strings; it replaces "Fleeced runs on iPhone and
  desktop web for now."). **No web button**, because a phone can't sign in on the web. The
  open is still recorded.

### J3 — Invitee, app installed (universal link)

- **Signed out:** LeagueJoin → SignIn with the inviter named (display name from the invite id,
  FR-11) → sign in → picker auto-pins the league → first session carries the invite id →
  credited by token.
- **Account-only (Apple sign-in, no platform yet):** LeaguePicker companion state with the
  invite context → links Sleeper/ESPN/MFL → first league session carries the invite id →
  credited if they are in the invited league.
- **ESPN/MFL/Fleaflicker league:** as above once they link that platform; the session-init
  body for every platform carries the invite id (FR-12).

### J4 — Existing Fleeced user opens an invite

Pinned into the league if a member (today's behaviour). **No credit, no inviter
notification.** Re-engagement credit is backlog GB-12.
- **Member whose active league was another one (`ux-lead` R-F4):** the auto-pin switches the
  active league with no confirmation (`LeaguePickerScreen.tsx:234-254`). Checklist step 7b
  checks that the screen the user lands on shows the invited league's name. **Contingent:**
  if it doesn't, add a one-line inline confirmation (not a toast, not a modal; words
  `marketing-lead`), shared with `onboarding-pm`.
- **Not a member (R-F5, a pass):** the picker shows "You're not in that league yet — pick one
  below, or join it on your fantasy platform and open the invite again."
  (`LeaguePickerScreen.tsx:568-571`); the list stays usable. Checklist step 7c records it.

---

## 5. CTA target before the App Store listing (operator decision)

**Decided 2026-10-15: option A** (the operator, verbatim via `head-product`: "Ok. start
building D1 and D3"). The operator also creates the public TestFlight link (D-3); it becomes
the `IOS_INSTALL_URL` value (§11), and no link value is ever written in the repo.

Audit decision 4. The finding that frames it ([marketing-inputs.md §0.2](marketing-inputs.md#02-cta-target-lead-recommendation), re-verified): **web
sign-in requires the desktop Fleeced extension** (`web/js/browser-auth.js:1`, fails
`extension_unavailable` after 2 s at `:45`; called unconditionally at `web/js/app.js:334`), and
ESPN/MFL browser sign-in is "not available … yet" (`app.js:1262-1266`). On a phone, web `/`
dead-ends every invitee on every platform.

| Option | What the landing does | Pros | Cons |
|---|---|---|---|
| **A (chosen 2026-10-15, D-1): device-aware** | iOS → public TestFlight link + re-tap step, numbered step 1 / step 2 (no `dtf://` button, §3 non-goal 13); desktop (and iPad) → with `IOS_INSTALL_URL` set, "Join on your iPhone" with a QR code of the invite URL (`t` included) as the primary and the web app as the secondary ("Have the Fleeced extension for Chrome or Edge?" + "Open the web app"; `ux-lead` R-F3, `growth-pm` P19, confirmed by `design-lead` 2026-10-15, D-16); unset, the web app with the extension line; Android/other phones → an honest note, **never** a web button that can't sign them in | The loop gets an install step now; league-match attribution (FR-14) recovers credit through the install; the re-tap recovers it exactly | TestFlight is a two-app install; 10k external tester cap (**benchmarked**: Apple TestFlight limit, unverified this session); beta framing. **Needs a public TestFlight link**: none exists yet (`NEXT.md:145-148`); the operator creates it (D-3, ruled 2026-10-15) |
| **B: web `/` (status quo, D-173 Companion)** | "Open the web app" on every device | Zero new decisions | **Strands every phone invitee**: the web button can't sign a phone in. Only desktop users with the extension can complete. No install step |
| **C: B until the App Store listing** | B now; the store link later | Clean end state | **Strands every phone invitee with no end date**: launch has no date |

Killed: waitlist / email capture (reverted 2026-08-12 in `65c63479`; no email channel; adds
a step).

**The desktop path rarely completes in practice.** The extension is an unpacked Chrome/Edge
release, not a store listing (`extension/README.md:44`), so few desktop invitees will
sideload it. Option A's working install path is effectively iOS TestFlight (§14). That
strengthens D-1 (A) and D-3 (the public TestFlight link). It is also why, with
`IOS_INSTALL_URL` set, the desktop layout leads with the phone path and its QR code, and the
web app is the secondary action (`ux-lead` R-F3, `growth-pm` P19, `design-lead` D-16; FR-7).

**How the choice is applied without code.** The install link is configuration
(`IOS_INSTALL_URL`, §11). Set → option A, with the desktop QR-primary layout. Unset → iOS
invitees see the honest note instead of a dead button (B and C as they can work on a phone),
and the desktop layout keeps the web app as its primary with no QR and no iOS link, whose
click-through would 404 (§8.2). When the listing ships, set it to the App Store URL: C's end
state, no deploy of code. The iPhone labels flip with it, because they follow the URL's host
(FR-7).

---

## 6. Requirements

Numbered FR-n; each has acceptance criteria (AC). "Flag on" means `growth.referral_ledger`
on unless stated. `S` = `backend/server.py`.

### H1–H2 · Inviter side

**FR-1 — Mint a per-share invite id on tap.** `shareInvite` (`InviteLeaguematesBanner.tsx:119-140`)
and the web modal's `shareVia` (`web/js/app.js:6130`) call `POST /api/invite/token` (§8.1)
after `invite_cta_tapped` and before opening the share sheet, with a **2 s deadline**
(**assumed**; precedent: the share-package mint deadline is 6 s, `ShareTradeImage.tsx:56`).
Any non-201, timeout or offline result falls back to the league-only link; sharing never
breaks. Demo sessions don't call.
- AC-1a: flag off → no call is made and the emitted URL is byte-identical to today's.
- AC-1b: flag on, mint 201 → the URL carries `t=<invite_id>`; `invite_shared` carries
  `invite_id` and `mint_outcome: 'ok'`.
- AC-1c: flag on, mint fails/times out → the share sheet still opens within ~2 s with the
  league-only URL; `invite_shared.mint_outcome` ∈ `failed | timeout | rate_limited | disabled | demo`.
- AC-1d: event order is fixed: `invite_cta_tapped` → mint → `Share.share` → `invite_shared`
  (non-dismissed only). Pinned by the structural guard (scope §3).
- AC-1e: while the mint is pending, the Invite button ignores taps: one tap gives one mint and
  one share sheet, on every surface and on web (`ux-lead` R-F8). Pinned by the structural
  guard (scope §3).

**FR-2 — Link format: id in, username out.** With the flag on, new links carry `t` and
**never `ref`**: `/app/league/join/<league_id>?t=<invite_id>` when `growth.invite_join_link`
is on, else `/?league=<league_id>&t=<invite_id>`. Mint failure drops `t` and still omits
`ref`. Both clients keep **parsing** legacy `/?league=&ref=` and `/app/league/join/<id>?ref=`
forever (D-028).
- AC-2: the 2×2×2 matrix (ledger flag × join-link flag × id present/absent) produces exactly
  the URLs in §7.2; no flag-on URL contains `ref=`.

**FR-3 — Share text says Fleeced.** Mobile (`InviteLeaguematesBanner.tsx:132`) and web
(`web/js/app.js:5834`) invite messages use `gp.invite.msg`, "Join me on Fleeced to find
trades we both like → {url}" (49 characters + the URL, 133–141). **One invite line
everywhere, with no league name, SMS included** ([package §5 D6](marketing-referral-approval.md#5-drift-marketings-file-vs-the-prd--91f1cc29-7)):
the recipient is already in the league, and the landing names it. The web modal's default
(`h2.web.default`, `app.js:5834`) and its SMS channel (`h2.web.sms`, `app.js:6082`) reuse
`gp.invite.msg`. Only the web X channel (`h2.web.x`, `app.js:6086`) keeps its own line,
"Finding dynasty trades in {leagueName} on Fleeced. Join me → {url}", which drops the
unverified @FantasyTradeFinder handle. The league-name variant `gp.invite.msg_league` is
parked (later slice, §12). Words approved by the operator 2026-10-23
([package §2 H2](marketing-referral-approval.md#h2-link--share-text), D-5). Ships
with the flag off too (copy is not attribution). This PRD renames only the strings its own
FRs already touch: this invite share text, the inviter rows (FR-18, FR-19) and the join
landing (FR-7). Every other old-name string, including the `league_member_unlocked_trades`
body (`S:10542-10543`), is `head-product`'s P9 copy-defect batch (`onboarding-pm`, after
this wave). Words from `marketing-lead`. Spelling: **"leaguemates"**, one word, in every
proposed string (`marketing-lead`, the voice-spec form). The shipped banner's
"league-mates" (`InviteLeaguematesBanner.tsx:163, :167, :176`) is respelled "leaguemates"
**in this build** (`marketing-lead`'s `h1.banner.title` / `h1.banner.a11y`, and
`h1.banner.body` too, per [package §3](marketing-referral-approval.md#3-not-needing-approval-keys-only);
spelling only, no other banner words change): FR-3 and AC-4b already touch that file, and P9
covers only strings outside the files this PRD touches. The `h1.banner.body` rewrite is later
slice (package §5 D7; §12).
- AC-3: no invite share text contains "Dynasty Trade Finder" or "Fantasy Trade Finder"
  (structural guard).
- AC-3b: `InviteLeaguematesBanner.tsx` contains no "league-mates" in any rendered string or
  accessibility label.

**FR-4 — Even impressions.** `invite_cta_shown` fires on the Trades cold-start banner and the
members-overlay footer (H1b, H1e). The banner passes the league's real `platform` and real
`not_joined` / `total_mates` where `/api/league/summary` has them (null stays honest when it
doesn't; `InviteLeaguematesBanner.tsx:146-153`).
- AC-4: every invite surface fires `invite_cta_shown` once per mount; the banner no longer
  hard-codes `platform: 'unknown'` when the league platform is known.
- AC-4b: because this build already touches `InviteLeaguematesBanner.tsx`, the banner's
  Invite button (`:172-179`) meets the **44pt hit-target floor** (`hitSlop` allowed) and its
  border meets **3:1** non-text contrast against the surface it sits on. Today it is
  `minHeight: 36` with no `hitSlop` (`:213`) and the legacy `ink.lineStrong` `#3D4654`
  border (`:220`; 2.03:1 on ink-0 per `mobile/src/theme/chalkline.ts:28`) (`design-lead`
  finding F2). **The border's colour value is set by `design-lead`'s `/design-review`**,
  because existing tokens top out at 2.81:1 on the banner's `ink.ink2` surface (`:192`):
  even `ink.lineStrongA11y` `#59647A` measures 2.81:1 there (`chalkline.ts:29-34`), so a
  token swap alone does not pass.

Apart from AC-4b and FR-1's pending state (J1 step 2; the lab draws it with the chalkline
Button's loading treatment, §13), FR-3 and FR-4 are copy and events only: **no other visual
change** to the invite card or banner. `design-lead` reviews the diff (§13).

**FR-5 — Web invites are measured.** The web modal fires `invite_cta_shown`,
`invite_cta_tapped` and `invite_shared` via `FTFTrack` with `surface: 'web_invite'` (a new
value in the closed `InviteSurface` set and its taxonomy domain), and mints per FR-1.
- AC-5: a web share produces the same three events as a mobile share, with `web_invite`.

**FR-6 — Spam ceiling.** The mint endpoint caps at **10 links per inviter per league per UTC
day** (**assumed**); the 11th returns 429 and the client falls back (FR-1).
- AC-6: pytest proves the 11th mint in a day is 429 and the next UTC day resets.

### H3 · Non-user sees and opens

**FR-7 — A real join landing.** With `growth.join_landing` on, `GET /app/league/join/<league_id>`
renders a backend page (§8.2) instead of the 302. It shows the league name, the inviter's
display name (resolved server-side from `t`), absolute OG tags, the device-aware CTA from §5
and the re-tap step. No `dtf://` "Open in the app" button in v1 (§3 non-goal 13). Chalkline
styling per `docs/design/design-system.md` (rules below); it does **not** reuse the `/s/*` chrome, which is
off-Chalkline (999px pill, system/Roboto stack, 16px radius with shadow:
`S:25493-25501`; [marketing-inputs.md §0.3](marketing-inputs.md#03-loop-defects-found-for-the-prds-fix-list) defect 11). `<meta name="robots" content="noindex">`; the path
is **not** added to `robots.txt` (unfurlers that honour robots must still fetch it). Words:
`gp.join.*` as written in
[marketing-referral-approval.md §2](marketing-referral-approval.md#2-operator-approval), the
launch-slice authority for referral wording, approved by the operator 2026-10-23 (D-5);
`marketing-lead`'s lab answers
([addendum](marketing-inputs.md#addendum-design-leads-lab-slots-and-growth-pms-four-questions-2026-10-15))
are the drafting record:
- **Headline:** "{display name} invited you to {league}" (supersedes `gp.join.headline`). Only
  a valid `t` names the inviter (§8.2), so the name is server-verified, never URL-supplied.
  Fallbacks, in order: "{display name} invited you to their league" (league name unknown) →
  "A leaguemate invited you to {league}" (no valid inviter) → "A leaguemate invited you"
  (neither).
- **Value line:** `gp.join.valueprop`, "Rank your players, then see trades built to work for
  both sides in {leagueName}." (fallback "…in your league."; intent form, the league name
  last), not the lab's "Fleeced finds trades where both sides
  come out ahead." (`web/index.html:75`), which makes Fleeced the subject of an analysis verb
  (the name rule).
- **Page title:** `gp.join.page_title`, "{leagueName} on Fleeced: Dynasty Trade Finder"
  (fallback "Your league on Fleeced: Dynasty Trade Finder").
- **og:title:** `gp.join.og_title`, "{leagueName}: trades built for both sides" (fallback
  "Dynasty trades built for both sides"; intent form, to match the `og_desc` under it; ≤60
  characters, so names up to 31) ([package §2 H3a](marketing-referral-approval.md#h3a-og-card-and-page-head)).
- **og:description:** `gp.join.og_desc` is "Rank your players on Fleeced and see trades built
  to work for both sides. Works with Sleeper, ESPN and MFL." (= `m3.web.og_desc`,
  marketing-lead copy batch, 2026-10-23: outcome → intent; it replaces "…trades where both
  sides come out ahead…").
- **iPhone install labels follow the `IOS_INSTALL_URL` host, not a date** (`growth-pm`,
  2026-10-23; words from the marketing-lead copy batch, 2026-10-23, rows `m4.348.cta_ios` and
  `m4.348.cta_ios_help`). The host is read with the URL on each request:
  - `testflight.apple.com` → beta: "Get the iOS beta" / "Installs through Apple's TestFlight
    app.";
  - `apps.apple.com` → store: "Get the iPhone app" / "Opens the App Store.";
  - any other host, or a value that isn't `https://` → treated as **unset** everywhere (the
    honest notes, the desktop layout with no QR and no iOS link, `/go/ios` 404s, FR-25's
    unset branch), and logged once.

  So the labels flip with the config change on launch day (§12), with no deploy and no date
  in code; the batch's "from 2026-11-06" is replaced by this rule. In this PRD,
  "`IOS_INSTALL_URL` set" means an `https://` URL on one of those two hosts. The same rule
  picks FR-25's labels and the iPad line below.

All of these strings are approved by the operator 2026-10-23 as written (D-5;
[package §2](marketing-referral-approval.md#2-operator-approval)). The host-keyed install
labels (`m4.348.cta_ios`, `m4.348.cta_ios_help`) still flip only on 11-18, when
`IOS_INSTALL_URL` becomes the App Store URL.

With the flag off, the 302 is unchanged.

Design rules (`design-lead` review, accepted by `growth-pm`):
- **Tokens and type.** The page links `web/css/tokens.css` (served as `/css/tokens.css`, the
  single web token source) and loads Barlow Condensed / Archivo / IBM Plex Mono from Google
  Fonts per `docs/design/design-system.md`. None of the `/s/*` `_share_html` chrome
  (`S:25460`); fixing that chrome stays backlog GB-02.
- **One primary action per device state, in ice.**
  - iPhone with `IOS_INSTALL_URL` set: the install label ("Get the iOS beta", or "Get the
    iPhone app" on the App Store host) is the ice primary, then the help line and the re-tap
    step. The CTA and the re-tap line are numbered **step 1** and **step
    2** of one task, so the re-tap reads as part of joining, not a footnote (`ux-lead` R-F1;
    words `marketing-lead`). No second button. **Layout (lab frame A1; `design-lead`,
    2026-10-15; checked in `/design-review` on the build branch):**
    - A two-row step list. The step markers are IBM Plex Mono "1" and "2" in `--chalk-dim`,
      matching the shipped landing's 01/02/03 numerals (`web/index.html:78-80`); no ice on
      the markers.
    - Row 1 holds the step heading "Install Fleeced" (`gp.join.step1`) and the ice primary
      install label with its help line (beta or store, by host, above). Row 2 is the re-tap instruction, "Tap the
      invite again, or rescan its code, to join {leagueName}." (`gp.join.step2`, J2), as
      body text, not a button.
    - One `--line` hairline between the rows; never a card per step.
  - Desktop with `IOS_INSTALL_URL` set (`ux-lead` R-F3; decided by `growth-pm`, P19).
    **Confirmed by `design-lead` 2026-10-15 (D-16 resolved; checked in `/design-review` on
    the build branch).** It reverses the desktop rule `design-lead` had accepted.
    - **Order.** The QR block comes first and is the primary. Under it, the web app is the
      secondary: the line "Have the Fleeced extension for Chrome or Edge?"
      (`gp.join.desktop.ext_lead`) in `--chalk-dim`, the extension line's slot, and the
      button "Open the web app" (`gp.join.cta.A_desktop`, `/go/web`) as a Secondary button
      (outlined, 1px `--line-strong`, `docs/design/components.md:24`). The line names Chrome
      or Edge itself, so `gp.join.cta.A_desktop_help` isn't repeated in this state; whether
      the line sits above or below the button is checked in `/design-review`.
    - **Label and accent.** A TickLabel heads the QR block with "Join on your iPhone"
      (`gp.join.desktop.qr_title`, replacing the working label "Get it on your iPhone"; the
      TickLabel renders it in caps). Its ice tick is the state's accent: there is **no
      ice-filled button** in this state, so here the QR block, not an ice button, is the one
      primary. Under the code, "Scan with your iPhone camera. After installing, scan again
      to join." (`gp.join.desktop.qr_help`).
    - **Payload.** A QR code of the same invite URL, `t` included. Scanning it after
      installing is the re-tap: the universal link opens the app and credits by token. The QR
      encodes the join URL rebuilt from the closed contract (`/app/league/join/<id>` plus
      `t`, or the inbound legacy `ref` only when there is no `t`), never the raw request URL.
    - **The code.** `--ink-0` modules on a `--chalk` (#ECEFF4) panel; the standard 4-module
      quiet zone; `--r-xs` or `--r-sm` corners on the panel; no ice or flare tint, no centre
      logo; never inverted (light modules on dark aren't read by every scanner). The chalk
      panel is a sanctioned exception to the dark-only rule below: a functional graphic in
      its own box, like the mascot art. `design-lead` adds it to the exceptions register.
    - **Size and density (`design-lead`, 2026-10-15).** Error correction level M, QR up to
      version 6. Rendered at ≥200 CSS px, with modules ≥4 CSS px, counted with the 4-module
      quiet zone: the code is (modules + 8) × the module size. The SVG uses
      `shape-rendering="crispEdges"` and whole-pixel modules. If the encoder ever returns
      version 7 or higher (a longer league id), grow the code to (modules + 8) × 4 px;
      never shrink the modules. Worked values: version 5 (37 modules) and version 6 (41)
      need 5 px modules to reach 200 px (225 and 245 px); version 7 (45) is 212 px at 4 px.
      The builder reports the encoder's version in the build PR; `design-lead` checks it in
      `/design-review`.
    - **iPad.** The iOS install link (`/go/ios`) stays inside the QR block as a text (Ghost)
      link, "On an iPad? Get the iOS beta, then tap the invite again."
      (`gp.join.desktop.ipad`; it carries the iPad's step 2), with a 44px hit target,
      because an iPad gets this layout and can't scan its own screen. On the App Store host
      it reads "On an iPad? Get the iPhone app, then tap the invite again." (`growth-pm`'s
      placeholder, adopted verbatim by `marketing-lead`, package §5 D4; approved, D-5).
    - **Accessibility.** The QR's accessible name says what it does: "QR code: opens this
      invite on your iPhone" (`gp.join.desktop.qr_a11y`; the PRD's example, adopted verbatim
      by `marketing-lead`, package §5 D5; approved, D-5).
    - **Privacy: generated server-side, inline (`head-eng` / `engagement-eng`; AC-7f).** The
      landing's own response carries the QR as inline SVG. **Never call a third-party QR
      service**, from the server or the browser: the invite URL carries `t`, and `t` must not
      leave our server.
    - Build note: no QR generator exists in `requirements.txt` today. `head-eng` picks a
      server-side library that emits SVG, logged in `living-memory/DEPENDENCIES.md`.
    - Build note, URL length: at EC M, version 6 holds 106 bytes (byte mode).
      `https://fantasy-trade-finder.onrender.com/app/league/join/` is 58 bytes
      (`mobile/app.json:22` host), so a 19-digit Sleeper id plus `?t=` and the 12-character
      id (§7.1) is 92 bytes, version 6 (78 bytes, version 5, for a 5-digit MFL id): inside
      the cap, with 14 bytes of headroom. Past that, the version-7 rule above applies.
  - Desktop with `IOS_INSTALL_URL` unset: "Open the web app" is the ice primary; the extension
    help line in `--chalk-dim`; no QR and no iOS link (its click-through 404s, §8.2: a dead
    path).
  - **Contingent (`ux-lead` R-F2):** if checklist step 4b finds that an in-app browser
    reopens the landing on a re-tap, A1 and A2 gain a line for installed users: "Have the
    app and still seeing this page? Open this link in Safari, or tap it in Messages."
    (`gp.join.iab_wayout`; approved 2026-10-23 with package §2, contingent: it ships only if
    step 4b fails). On A2 it replaces the note's last sentence rather
    than adding a third. Step 4b tests both routes, including re-tapping from Safari; if
    Safari doesn't hand off to the app, the line is cut to "…Tap the invite in Messages."
  - Android, or iPhone with no `IOS_INSTALL_URL`: no button; the note in `--chalk` or
    `--chalk-dim`, never `--chalk-faint` (it's content).
  - iPhone with no `IOS_INSTALL_URL` (lab frame A2): the honest note only, "The iPhone beta
    isn't open to the public yet. Already have it? Tap the invite again, or rescan its
    code." (approved, D-5; revised by `marketing-lead` to match step 2; the Android note's "runs
    on iPhone" would be wrong on an iPhone). The re-tap is the invite link itself: a
    universal link that opens the installed app, not a `dtf://` button (§3 non-goal 13).
    This answers D-14's follow-up (the earlier "Open the invite in the app" named no
    action once the button was gone). **No "Request
    TestFlight access" link** (today's `/contact.html` link, `web/index.html:266`) in v1: it
    would depend on manual operator follow-up.
- **Expired or unknown link:** drop the inviter name; neutral headline; **not** `--neg` red (an
  expired invite isn't an error to the user).
- **No "already joined" state:** the landing has no auth and one link can credit several
  joiners (§7.6), so it can't know; that state lives in the in-app J4 path.
- **Floors:** 44pt hit targets, the ice focus ring, `prefers-reduced-motion` respected, dark
  only.
- **OG card (v1, static 1200×630).** `--ink-0` field, the FLEECED wordmark in Barlow
  Condensed caps, one Archivo line; no gradients, no glow; text ≥48px at 1200 wide so it
  reads at iMessage thumbnail size (~300px). Art direction is `design-lead`'s (P14). The
  `TRADE FINDER`-with-ice-tick wordmark in `docs/design/brand.md:42` is stale;
  `design-lead`'s fix is `docs/design/brand.md` on PR
  [#349](https://github.com/mattmurf77/fantasy-trade-finder/pull/349).
  - **Wordmark period: resolved (D-15, `design-lead`, 2026-10-15).** The OG card carries the
    logotype **"FLEECED."** with the ice period: Barlow Condensed Bold caps, in chalk, as the
    web header ships it (`web/index.html:54`, `web/css/styles.css:4991-4992`). The rule, in
    PR #349's `brand.md`: the ice period belongs to the logotype; it goes wherever the logo
    appears and nowhere else (not verdict cards, headings, badges or buttons). This matches
    `head-product`'s proposed rule (running copy never uses it). `marketing-lead`'s concern
    ("FLEECED." next to a trade reads as a verdict) is answered by the logo-only scope.
  - **v1 = lab variant (ii)** (`growth-pm`, 2026-10-15): the wordmark plus the ram (the app
    icon, `mobile/assets/mascot/ram/neutral@3x.png`) in its own box; the ram's own shading
    stays inside that box. PR #349's `brand.md` sanctions the invite OG link card as a ram
    placement. **Fallback: variant (i)**, wordmark only. Variant (iii), the league
    name as dynamic text, is Phase 2 (it needs a per-league render and inherits D-10).
  - **The Archivo line** (`marketing-lead`; the OG lockup, approved 2026-10-23, D-5): "Dynasty Trade Finder" may appear only
    locked up with the FLEECED wordmark, smaller than it, so the two read as D-057's full
    name; never standalone or on a line of its own (DLF has a product with that name). AC-3
    still bans the phrase in invite share text.

- AC-7a: flag off → tests T4–T7 in `test_invite_links.py` pass unmodified.
- AC-7b: flag on → 200 HTML; `og:image` is an absolute `https://` URL; `og:title` carries the
  league name when known; a `noindex` meta is present; no username from the query string is
  echoed into the page.
- AC-7c: one primary action per device state (lab frames A1–A4, §13): iPhone UA → install
  CTA and the re-tap line, numbered step 1 and step 2, when `IOS_INSTALL_URL` is set, as a
  two-row step list whose second row is text with no link or button; honest
  note, no button and no TestFlight-request link when unset; Android UA → honest note, no
  button; desktop UA with `IOS_INSTALL_URL` set → the QR block first, headed by the
  "Join on your iPhone" TickLabel, with a QR code whose payload is the join URL with `t`
  (built from the closed contract, no other query param), the scan line and the `/go/ios`
  iPad text link inside the block; then the line "Have the Fleeced extension for Chrome or
  Edge?" with "Open the web app" as a Secondary (outlined) button; no ice-filled button;
  desktop UA with it unset → web-app CTA + extension line, no QR and no iOS link. The
  test asserts the words the operator approved under D-5 (2026-10-23, package §2).
  No state renders a `dtf://` link. The visual specs (marker type and colour, hairline, QR
  panel, quiet zone) are checked in `design-lead`'s `/design-review` on the build branch.
- AC-7d: the brand on the page is "Fleeced" (D-057).
- AC-7e: the page links `/css/tokens.css` and carries none of the `_share_html` chrome; an
  unknown or expired `t` renders no inviter name.
- AC-7f (`head-eng` / `engagement-eng`; `design-lead`, 2026-10-15): with `IOS_INSTALL_URL`
  set, a desktop UA's response carries the QR as an inline `<svg>` generated server-side,
  with the accessible name "QR code: opens this invite on your iPhone"
  (`gp.join.desktop.qr_a11y`). The page
  requests no QR image or script from any host: no `<img>`, `<script>` or CSS URL for the QR,
  and the only third-party host the page references is Google Fonts. The encoder is called
  with error correction M and a 4-module border, and its payload is AC-7c's join URL. The
  SVG carries `shape-rendering="crispEdges"`; its size is (modules + 8) × a whole-pixel
  module of ≥4 CSS px and ≥200 CSS px overall, with dark modules on the light panel (never
  inverted); a version-7-or-higher payload (a sizing unit test with a long league id) grows
  to (modules + 8) × 4 px rather than shrinking its modules. Pytest asserts these at the
  encoder's input and in the HTML; the build PR reports the encoder's version for today's
  join URL, and `design-lead`'s `/design-review` checks the rendered code.
- AC-7g (install host; `growth-pm`, 2026-10-23): the label pair is chosen by the
  `IOS_INSTALL_URL` host. An `https://testflight.apple.com/…` value renders "Get the iOS
  beta" / "Installs through Apple's TestFlight app." and the iPad line's beta form; an
  `https://apps.apple.com/…` value renders "Get the iPhone app" / "Opens the App Store." and
  the iPad line's store form; any other host, or a non-`https://` value, renders exactly
  AC-7c's unset states on every user agent, `/go/ios` 404s, and one warning is logged per
  process, not per request. The same cases run on `/s/p` (FR-25, AC-25). The words are the
  operator-approved ones (D-5, 2026-10-23, package §2).

**FR-8 — Record the open server-side.** With the ledger flag on, **every** GET of the join
path (landing or 302) classifies the user agent, with or without `t`, so opens of mint-failed
and legacy links are measured too (analytics addendum, PR #350, request R1):
- human → server event `invite_landing_opened`; and, when the row is stampable (below),
  `opened_at` (first), `last_opened_at` and `open_count + 1` on that share's minted row;
- link-preview fetcher → `unfurled_at` (first) on a stampable row only, no event;
- HEAD → nothing.

**Which row is stamped** (F1's league rule; `growth-pm`, 2026-10-23, on `engagement-eng`'s
R2-4): only a row that the well-formed `t` names, whose `league_id` matches the route's
league, and whose status is `valid` or `expired`. A `t` naming a row in a different league
still records the event, with `invite_status = league_mismatch`, but stamps nothing.

"Human GET" is an explicit, tested filter (condition C4), shared with the `/go/<cta>`
click-through (§8.2):
- HEAD requests are excluded.
- Link-preview and unfurl fetchers are excluded by a user-agent list kept as a tested module
  constant: at least `facebookexternalhit`, `Twitterbot`, `Slackbot`, `Discordbot`,
  `WhatsApp`, `TelegramBot`, `Applebot`, `LinkedInBot`, and a generic
  `bot|crawler|spider|preview` pattern (together they cover iMessage, Slack, Discord, WhatsApp
  and X).
- Only the `device_class` bucket is stored, **never the user-agent string or the IP**.

The event's `invite_status` (renamed from `token_status`, C1) is `valid | expired | unknown |
league_mismatch`, or null when `t` is absent. Owner: the referrer of the row `t` names;
with no such row, the user a legacy `ref` resolves to; else `system:invite`.

Readout note for `analytics-lead` (FR-22): a desktop visitor who scans FR-7's QR code makes a
second human open of the same link from the phone (`device_class` `ios`), so `open_count`
and `o` can count one invitee twice.
- AC-8: pytest with a human UA increments `open_count`; each listed preview agent and the
  generic pattern set only `unfurled_at` and fire no event; HEAD changes nothing; a human GET
  with no `t` fires `invite_landing_opened` with `invite_status` null; a human GET whose `t`
  names a row in another league fires it with `invite_status` `league_mismatch` and changes
  no row (nor does a preview fetch of that link); an expired same-league row is stamped; no
  stored row carries a user agent or an IP.

**FR-9 — Desktop onward link and web capture.** The desktop web-app action (the primary
with `IOS_INSTALL_URL` unset, the secondary with it set, FR-7) goes through a recorded
click-through (§8.2) to `/?league=<id>&t=<id>` (closed contract: `league`, `t`, and the
inbound legacy `ref` only when there is no `t`). `captureReferralFromUrl`
(`web/js/app.js:6390-6403`) also stores `t` (`ftf_invite_id`), fires `invite_link_opened` with
`format: 'web'`, and the web session-init body sends `invite_id` (§8.4). `startOver` clears
it with the other invite keys (`app.js:278-279`). Web auto-select (`app.js:436-441`) fires
`invite_league_pinned{source:'web_autoselect'}`. Wherever the web landing shows invite
context (today's "Invited by @…" pill for legacy `ref` links, `showInvitedBanner`,
`app.js:6408-6417`, and any inviter line this build adds), informational emphasis uses flare
or chalk, **not the semantic `--pos` green**: the pill's `.invited-banner` is
`color: var(--green)` (`web/css/styles.css:2708`), and `--green` is `var(--pos)`
(`web/css/tokens.css:44`) (`design-lead` finding F3).
- AC-9: a desktop landing → web sign-in → auto-select run produces `invite_link_opened{format:'web'}`,
  `invite_league_pinned{web_autoselect}`, and a session init carrying `invite_id`.
- AC-9b: no invite-context element on the web landing uses `--pos` / `--green`.

**FR-10 — Installed app carries the id.** `handleDeepLink` (`deepLinks.ts:396-438`) and
`LeagueJoinScreen` (`:50-111`) capture `t` into the invite intent as `inviteId` (same 14-day
TTL, `useSession.ts:44-45`; last-write-wins like `invitedBy`). `inviteId` lives in memory
until a session-init body consumes it, like `consumeInvitedBy`, because
`consumeInvitedLeague` removes the persisted blob on pin (`useSession.ts:548-559`).
`invite_link_opened`, `invite_league_pinned` and `invite_pin_failed` carry `invite_id`.
- AC-10: a path-form link with `t` opened signed-out → after sign-in and auto-pin, the first
  session-init body carries `invite_id`; the intent survives a relaunch inside 14 days.

**FR-11 — Name the inviter from the id.** `GET /api/league/invite-meta` accepts `t` and
returns `inviter_display_name` and `invite_status` (§8.3). SignIn's banner
(`SignInScreen.tsx:203-235`) and the LeaguePicker companion state use it when the link has no
`ref`; it is cached in the intent like `leagueName` (one call site, `SignInScreen.tsx:220`).
The mobile call sends `t`: today `fetchInviteMeta` (`mobile/src/api/league.ts:953-975`) takes
only a league id, `InviteMeta` (`:947-951`) has no inviter field, and the call is skipped
once the league name is cached (`SignInScreen.tsx:218`), even when the inviter name isn't.
(Lines at the base, 678834ab. On `origin/main` 712dcbed, SignIn's block sits 20 lines lower,
`:223-255`; `league.ts` is unchanged.)
- **Launch slice: must make the 11-06 binary** (`growth-pm`, 2026-10-23, on
  `marketing-lead`'s U2, package §6; §12's binary row). FR-2 stops emitting the username
  `ref`, so without FR-11 an installed invitee's SignIn loses the inviter name it shows today
  (`SignInScreen.tsx:229-231`) and falls back to the shipped no-inviter line, "You were
  invited to {league} — sign in and we'll take you straight there." (`:232-234`). FR-11
  reuses the approved headline ladder (AC-11). Its server half (§8.3, `t` and
  `inviter_display_name`) rides §12's server row, target 11-16; until it lands, the field is
  absent and SignIn shows the ladder's no-name rungs.
- AC-11: a token-only link renders "{display name} invited you to {league}" (FR-7's
  `gp.join.headline` ladder, approved 2026-10-23, D-5), with FR-7's fallback ladder: "{display name} invited you to their
  league" when the league name is unknown; an unknown id degrades to "A leaguemate invited you
  to {league}", or "A leaguemate invited you" when the league name is unknown too.

**FR-25 — `/s/*` share landings use the same device-aware CTA target, with a label per
device** (pulled into the first build slice by `head-product`, 2026-10-15, from GB-02;
numbered last so FR-1…FR-24 keep their numbers). Every page `_share_html` renders
(`S:25460`; callers `/s/tiers` `S:25522`, `/s/trade` `S:25552`, `/s/p` `S:25650`, each
hard-coding `cta_url="/"` at `S:25548`, `:25563`, `:25669`) picks its CTA with the join
landing's device classifier (FR-7, §5 option A). The label and help line are **per device
branch**, not one string per page: neither trade label reads true when the tap starts a
TestFlight install. Today `_share_html` takes a single `cta_text` (`S:25465`, rendered at
`S:25511`), so it must take a label (and help line or note) per branch instead. Strings by
`marketing-lead`, **approved by the operator 2026-10-23** (D-5;
[package §2, "S share landings"](marketing-referral-approval.md#s-share-landings-fr-25-sp-strade);
drafted in [marketing-inputs.md, lab addendum, "Share landings `/s/*` under FR-25"](marketing-inputs.md#addendum-design-leads-lab-slots-and-growth-pms-four-questions-2026-10-15)):

| Branch | CTA target | Label | Help line or note |
|---|---|---|---|
| iPhone, `IOS_INSTALL_URL` set | `IOS_INSTALL_URL` | By host (FR-7): "Get the iOS beta" (`gp.join.cta.A_ios`) on `testflight.apple.com`; "Get the iPhone app" on `apps.apple.com` | "Installs through Apple's TestFlight app." (`gp.join.cta.A_ios_help`), or "Opens the App Store." on the store host. **No re-tap line:** a share page carries no invite, and re-tapping a share link opens the viewer's own tab, not the shared trade (GB-03) |
| iPhone, `IOS_INSTALL_URL` unset | none: a note, no button | — | "The iPhone beta isn't open to the public yet. Already have it? Open Fleeced." It promises the app, not the shared trade: the universal link opens the app (`mobile/src/utils/deepLinks.ts:229-238`), but `MatchesScreen` reads no match id from its route (`MatchesScreen.tsx:190-214`; GB-03) |
| Desktop | `/?share=<kind>` (`head-eng`'s contract C5; `kind` from the route: `tiers`, `trade`, or `package` for `/s/p`; today `/`) | Kept per page: "Build your own trade" (`/s/p`, `S:25668`), "Find your next trade" (`/s/trade`, `S:25562`) | **Added:** "Sign-in uses the Fleeced extension for Chrome or Edge." (`gp.join.cta.A_desktop_help`, the join landing's line, §5 J2), so a desktop visitor without the extension isn't stranded |
| Android and other phones | none: a note, **no web button** (a phone can't sign in on the web) | — | "Available on iPhone and desktop web for now." (`gp.join.android_note`, reused; it names no invite; marketing-lead copy batch, 2026-10-23) |

The iPhone and Android strings and the desktop help line are the same on every `/s/*` route;
only the desktop label stays per page (`/s/tiers` keeps "Build your tiers", `S:25547`). Only
the target, the label, the help line and the button-or-note choice change: `ref`
forwarding, the OG image and absolute `og:image`, `robots.txt`, landing events and the
off-Chalkline chrome stay in GB-02 (§3 non-goal 7). The response varies by device, so it can
no longer be a plain `Cache-Control: public` (today `public, max-age=300`, `S:25518`): it is
either not `public` or it carries `Vary: User-Agent`. Gate: rides `growth.join_landing`
(accepted by `growth-pm` 2026-10-15; `head-eng` still confirms it in allocation), so one
flag covers every device-aware CTA surface; with it off every device keeps today's single
button and label, only its href becomes `/?share=<kind>` (C5), and merge changes nothing
user-visible (§12).

**The desktop QR pattern (FR-7, R-F3) is not built on `/s/*` in this build; it folds into
GB-02.** `design-lead` ruled (2026-10-15, D-16) that the QR/device pattern also applies to
share landings when `IOS_INSTALL_URL` is set. Those pages are off-Chalkline (`design-lead`
F4; the `_share_html` chrome, `S:25493-25501`), so the QR and the Chalkline chrome for
`/s/*` are one rebuild in GB-02, not two passes. FR-25 in this build stays the device-aware
CTA target, labels and help lines in the table above. GB-02 inherits two facts: a share page
carries no invite, so a scan after installing credits nothing, and it opens the app, not the
shared trade, until GB-03 (`MatchesScreen` reads no match id).
- AC-25: pytest on `/s/p` and `/s/trade` (`/s/tiers` 404s while `growth.tier_board_share` is
  off and inherits the change through `_share_html`). Each branch asserts the CTA `href`,
  **its label and its help line or note**, not just the target:
  - gate off, every user agent: `href` `/?share=<kind>` (`package` on `/s/p`, `trade` on
    `/s/trade`; `head-eng`'s contract C5, not bare `/`), today's label ("Build your own
    trade" on `/s/p`, "Find your next trade" on `/s/trade`), no help line and no note;
  - gate on, iPhone UA, `IOS_INSTALL_URL` set: `href` is `IOS_INSTALL_URL`, no re-tap line,
    and the label and help line by host (AC-7g): on `testflight.apple.com`, "Get the iOS
    beta" / "Installs through Apple's TestFlight app."; on `apps.apple.com`, "Get the iPhone
    app" / "Opens the App Store."; any other host renders the unset case below;
  - gate on, iPhone UA, unset: no CTA link; the note "The iPhone beta isn't open to the
    public yet. Already have it? Open Fleeced.";
  - gate on, desktop UA: `href` `/?share=<kind>` as above, the page's label as above, help
    line "Sign-in uses the Fleeced extension for Chrome or Edge.";
  - gate on, Android UA: no CTA link; the note "Available on iPhone and desktop web for
    now.";
  - every case: the response is not `public`-cacheable, or carries `Vary: User-Agent`; the
    `og:*` tags are unchanged; no variant links `dtf://` or a user-supplied URL; no variant
    renders a QR code (that is GB-02's rebuild).

  The test asserts the words the operator approved under D-5 (2026-10-23, package §2): the
  strings above.

### H5 · Attribution

**FR-12 — Every platform's session init carries the id.** The two Sleeper builders
(`auth.ts:494-515`, `:590-608`), the ESPN builder (`buildEspnSessionInitBody`, `api/espn.ts`),
the MFL/Fleaflicker builder (`buildPlatformSessionInitBody`, `api/platformLink.ts`) and web
(`app.js:798-815`) send optional `invite_id`. One helper consumes it so the five call sites
cannot drift.
- AC-12: a structural check proves every session-init body builder includes `invite_id`.

**FR-13 — Credit by token on a new user's first session** (rules §7.4). Writes the ledger,
fires `referral_attributed`, and writes `users.invited_by` from the ledger (the referrer's
username, server-derived).
- AC-13: pytest covers Sleeper, ESPN and MFL invitees (membership verified per platform),
  unknown/expired ids, a non-member, a group-chat second joiner (§7.6), an existing user (no
  credit), and a repeat session init (idempotent).

**FR-14 — League-match fallback** (rules §7.5) when the first session carries no valid id.
Stamps `attribution_method = 'league_match'`.
- AC-14: with two opened pending rows in the invitee's first league, the most recently opened
  wins; a legacy `invited_by` matching one referrer's username breaks the tie in its favour;
  an open older than 14 days is never matched.

**FR-15 — Legacy `ref` never credits or notifies** (flag on). The client-supplied
`invited_by` is still stored in `users.invited_by` when no ledger attribution happens
(unverified, as today), and is used only as the FR-14 tie-breaker.
- AC-15: a new user arriving with only `invited_by=<someone>` gets no ledger row and the
  named user gets no bell row.

**FR-16 — `signup` says how the user arrived.** The server `signup` event (`S:22619-22630`)
gains `attribution` (`token | league_match | legacy_ref | none`) and `attribution_miss`
(`unknown | expired | not_member | null`). First-touch UTM props per [marketing-inputs.md §C](marketing-inputs.md#c-utm--install-source-convention-mkt-seo) are a
separate change: `analytics-lead` accepted the convention (P18, 2026-10-15), and it stays
outside Phase 1's critical path (§8.4).
- AC-16: each FR-13/FR-14/FR-15 test case asserts the `signup` props.

### H6 · First value

**FR-17 — Activation = the invitee's first trade opinion (funnel stage 7).** "Activated" is
the invitee's first `trade_proposed` or `match_swiped` (stage 7 `first_opinion`,
`analytics_queries.py:415`) within 14 days of `joined_at` (**proposed**). The helper takes
its qualifying events from stage 7 of `FUNNEL_STAGES` (`analytics_queries.py:406`, stage 7
at `:415`) in code, never from a hand list, so the two can't drift (analytics addendum, PR
#350: condition C5, request R3); today that stage is `trade_proposed` and `match_swiped`.
After each server emitter of those events, one helper checks for a `joined` referral whose
`referred_user_id` is this user and whose `joined_at` is within 14 days → `status =
'activated'`, `activated_at`, `qualifying_event` = the event's name, server
`referral_activated`. The emitters are the swipe route (`S:16110-16112`: like →
`trade_proposed`, else `match_swiped`), the calculator queue (`S:16572-16574`,
`trade_proposed`) and the reasoned pass (`S:16745-16746`, `match_swiped`). Both names are
server-fired only (`analytics_taxonomy.py:736`, `:769`), so no client event can activate.

Why stage 7 and not stage 6 (`trades_generated`, `analytics_queries.py:414`):
1. Stage 6 fires within seconds of the first deck load, so join and activation would land
   together and the activation row would say nothing new.
2. The weekly replenish cron emits `trades_generated` with no user present (`source =
   "replenish"`, `S:23865`, stamped as `deck_source` at `S:9228-9231` and `S:7615-7616`),
   so stage 6 can be a cron's doing, not a person's.
3. Stage 7 is the invitee acting on value: a truer quality bar.

`trades_generated` never activates, so stage 6's `count ≥ 1` guard is dropped. If
`analytics-lead` picks another stage (D-8), the helper moves to that stage's emitters
(stage 5: `ranking_complete_first_time`, `analytics_queries.py:413`, `S:10519`) and nothing
else changes.
- AC-17: the helper's qualifying set equals stage 7 of `FUNNEL_STAGES` (C5); a first
  `trade_proposed` or `match_swiped` inside 14 days stamps once, from each of the three
  emitters; outside 14 days it does nothing; a second opinion is a no-op; a
  `trades_generated` alone never activates, including a replenish deck
  (`deck_source = 'replenish'`).

### H7 · Inviter told

**FR-18 — Join row: correct, once, verified.** The `referral_joined` row fires only from a
ledger attribution (token or league match), with the shipped name and a body that is not a
copy of the title (today `push_notification` sets title = body, `database.py:12620-12634`,
and the bell renders both, `TopBar.tsx:499-501`). Words: the title
`gp.push.joined_inbox_title`, "@{new_username} joined Fleeced via your invite" (a name-only
change via `m3.push.joined`, [package §3](marketing-referral-approval.md#3-not-needing-approval-keys-only)),
and the body `gp.push.joined_inbox_body`, "Once they rank, trades with them can use their
board, not just consensus." (approved by the operator 2026-10-23,
[package §2 H7](marketing-referral-approval.md#h7-notifications), D-5). Route unchanged
(League, `deepLinks.ts:306-312`).
- AC-18: the row's title and body differ; no row fires from a legacy `invited_by` alone.
- **Launch slice: server-side, target 11-16, with the attribution work** (`growth-pm`,
  2026-10-23, on `marketing-lead`'s U3, package §6; §12's server row). Today's row,
  "@{new_username} joined Fantasy Trade Finder via your invite." (`S:22662`; title = body, so
  the bell shows it twice), must not be live at launch: the `m3.push.joined` name fix lands
  by 11-16 through the copy batch (`engagement-eng`) even if FR-18 slips (§12).

**FR-19 — Activation row.** New notification type `referral_activated` (inbox only; push is
Phase 2), posted to the inviter when FR-17 activates.
- **Routing: the Trades tab, not League.** v1 keeps the tap → Trades (`growth-pm`, on
  `ux-lead` R-F6), and the body is reworded so it doesn't promise the deck (Words, below);
  revisit if `trades-pm`'s #339 D10 ("tap starts the organic deck") ships. Register the type in mobile `V2_TRADE_KINDS` (`deepLinks.ts:318`, resolved to
  `{ tab: 'Trades' }` at `:340`; today it holds only `deck_replenished`) and in web
  `clickNotif`'s `TRADE_TYPES` (`web/js/app.js:5328`). Also register it in the glyph maps
  pinned by `mobile/tests/check-notif-glyphs.js` (it reads all four tables, `:7-10`; add the
  type to `TYPES`, `:51-60`) and in `docs/cross-client-invariants.md`'s type table, so the tap
  goes somewhere (the original `referral_joined` routing bug, `deepLinks.ts:300-305`). While
  `trades.finder_hub` is on (`config/features.json:16`), a Trades tap lands on the hub home,
  not the deck itself (`deepLinks.ts:314-317`). `engagement-pm` reviews the routing (D-9).
  The join row (FR-18) still routes to League.
- **Meta:** `new_user_id`, `new_username` and `league_id`, so the title can render the name
  (`referral_joined` already carries `new_user_id` and `new_username`, `S:22663-22667`).
- **Words** (proposed by `marketing-lead`, pending the operator; [marketing-inputs.md §A](marketing-inputs.md#a-copy-table-mkt-writer) rows
  `gp.inbox.activated_title` / `gp.inbox.activated_body`; **later slice: not in the 11-06
  binary and not in the operator's 2026-10-23 approval**,
  [package §4](marketing-referral-approval.md#4-later-slice-not-in-the-11-06-binary-not-in-this-approval);
  approved with that block only if `head-eng` lands the row by 11-16, §12): title "@{new_username} weighed in
  on their first trade"; body "When they like a trade with you, it can show up with a
  "They're interested" tag." (R-F6, D-5; lab addendum, "`ux-lead`'s review of PR #348").
  - The earlier body, "If they like a trade with you, it can surface in your deck.", is
    withdrawn: the tap lands on the hub home while `trades.finder_hub` is on, and the deck
    needs another tap (D-171), so the body promised a place the tap doesn't reach.
  - The new body names no place, so it doesn't point at the deck. It rests on likes-you
    mirroring: a leaguemate's `like` decisions from the last 90 days are mirrored into the
    other side's deck (`_inject_likes_you_cards_impl`, `S:3951-3972`), capped and
    quality-gated (`S:3979-3991`), hence "can". Flag `trade.likes_you` is on
    (`config/features.json:37`).
  - **Dependency:** the body quotes the likes-you pill label "They're interested"
    (`mobile/src/components/TradeCard.tsx:525`; web `web/js/app.js:3968`, verified at
    `60d3120b`). If that label changes, this string changes with it (→ `head-eng`).
  - The title is `marketing-lead`'s stage-7 revision (2026-10-15): it replaces "…has their
    first trade ideas", which described stage 6.
- AC-19: the row routes to Trades, not League; title and body differ; the body does not
  mention the deck; the meta carries `new_username` and `league_id`; the glyph check
  passes.

**FR-20 — Notify once.** When a join is attributed to inviter I, the `league_member_joined`
fanout (`S:22677-22720`) skips I's coalesced inbox row; I's existing per-pair push is kept
unchanged until Phase 2 replaces it with the referral push (`engagement-pm`).
- AC-20: an attributed join leaves exactly one bell row for the inviter about that join;
  other leaguemates' rows are unchanged.

### H8 · Measurement

**FR-21 — `/api/invite/impact` from the ledger** (§8.5). Drops `k_factor`; reports links
created → opened → joined → activated, per league and in total, with the method split. Stays
behind `invite.k_factor_dashboard`; the inviter-facing surface is Phase 2 (`design-lead`).
- AC-21: the payload matches §8.5 and is computed only from `referrals`.

**FR-22 — Program readout.** `analytics-lead` adds an `analytics_queries` readout for the
program (§2.4). Owner `analytics-lead`; the PRD supplies the joins (ledger `share_token` ↔
event `invite_id`).

### Cross-cutting

**FR-23 — Data rights.** Account deletion and export cover the new columns: deletion keeps
anonymising `referred_user_id` / `referrer_user_id` (`backend/accounts.py:829-838`); export
omits `share_token` alongside `invite_token` (`accounts.py:1043-1044`).
- AC-23: `test_account_deletion_coverage.py` and `test_account_data_rights.py` cover the new
  columns.

**FR-24 — Register before emit.** Every new event name and prop is registered in
`backend/analytics_taxonomy.py` (the four server names in `SERVER_FIRED_EVENTS`,
`share_link_opened` in `ALLOWED_CLIENT_EVENTS`) and classified in
`analytics_queries.NON_INTENT_EVENTS` where §10 says NON_INTENT, in the same commit as its
emitter (D-040). **The emitting eng worker does the registering and classifying**, under
`analytics-lead`'s grant (analytics addendum, PR #350, condition C7); `analytics-lead` grants
and does not edit code. Pinned by `backend/tests/test_analytics_taxonomy_referral_loop.py`
(the addendum's Verification list). **No prop key contains `token`** (C1, C3): ingest drops
any such key silently (`backend/analytics_ingest.py:160, :195`); the id travels as
`invite_id`, the public share id `t`, which names an invite, grants no access and must never
become an auth or session credential. Sibling rows' `invite_token` values
(`<share_token>~…`, §7.6) are never emitted.

---

## 7. Attribution design

### 7.1 The invite id

- 12 URL-safe characters from `secrets.token_urlsafe(9)` (72 bits): opaque, unguessable, no
  PII. Stored as `referrals.invite_token` (UNIQUE) and `referrals.share_token` on the minted row.
- Carried as `t` in links, `invite_id` in API bodies and event props, `inviteId` in the
  mobile intent, `ftf_invite_id` in web localStorage.
- **Valid for credit for 30 days from mint** (**assumed**). The client intent keeps its own
  14-day TTL from open. `expired` is derived on read (`created_at + 30 d`); v1 writes no
  `expired` status.

### 7.2 Link forms

| `growth.referral_ledger` | `growth.invite_join_link` | Mint | Emitted URL |
|---|---|---|---|
| off | off | — | `/?league=<id>&ref=<u>` (today, byte-identical) |
| off | on | — | `/app/league/join/<id>?ref=<u>` (today's path form) |
| on | off | ok | `/?league=<id>&t=<invite_id>` |
| on | off | failed | `/?league=<id>` |
| on | on | ok | `/app/league/join/<id>?t=<invite_id>` |
| on | on | failed | `/app/league/join/<id>` |

The AASA claims already match all of these (`S:12668-12678`: path `/app/league/join/*`;
legacy matcher on `league` alone).

### 7.3 Landing open record

Recorded by the join route on GET (FR-8), human user agents only. This is the open the
league-match fallback needs (the not-installed case). Installed-app opens never reach the
server (AASA resolves first); they are counted by the client `invite_link_opened` with
`invite_id`, and the readout unions the two.

### 7.4 Credit by token (session init, flag on)

Runs in the session-init daemon (`S:22552-22720`), only when `_is_new_user` (`S:22594`).
Account-only sessions skip the daemon (`S:22560`), so an Apple-first user is "new" at their
first real league session. In order:

1. Body has `invite_id` → find the minted row by `share_token`. None → miss `unknown`.
2. `created_at` older than 30 days → miss `expired`.
3. Membership: the invitee must be in the row's league. If the session's `league_id` equals
   it, membership is already proven by `resolve_session_input` (`backend/session_input.py:17-92`).
   Otherwise check `league_members` for the row's league (`database.py:8345-8420`) against the
   invitee's account and league identity. Not a member → miss `not_member`.
   (`platforms-pm` confirms the ESPN/MFL/Fleaflicker identity check.)
4. Claim: if the minted row's `referred_user_id` is NULL, set it with a conditional update
   (`WHERE referred_user_id IS NULL`); otherwise insert a sibling row (§7.6).
   Row → `status 'joined'`, `joined_at`, `attribution_method 'token'`.
5. `users.invited_by` = the referrer's username (server-derived) on the INSERT
   (`database.py:5122-5156`).
6. Fire `referral_attributed`; post the FR-18 row; apply FR-20.

A miss at steps 1–3 falls through to §7.5 and is recorded in `signup.attribution_miss`.

### 7.5 League-match fallback

Only when §7.4 credited nothing. Candidates: rows with `league_id` = the invitee's
first-session league, `status 'pending'`, `referred_user_id` NULL, `opened_at` within the
prior 14 days, `created_at` within 30 days, referrer ≠ invitee. If the body's legacy
`invited_by` matches exactly one candidate's referrer username, take it; else take the most
recent `opened_at`. Claim as §7.4 step 4 with `attribution_method 'league_match'`.

Checked against D-028 (no change to parsing or the legacy form), D-046 (the rows it produces
are receipts, not prompts) and the `league_member_joined` flow (FR-20 dedupes). It is the
ledger version of the query-only "league-scoped inference" in [marketing-inputs.md §C](marketing-inputs.md#c-utm--install-source-convention-mkt-seo) (recovery ii):
the same idea, stamped on a row so the ambiguity is visible in data instead of hidden in a
query.

**Known limit:** an invitee whose first session is in a *different* league is not matched.

### 7.6 One link, many joiners (group chats)

A share posted into a league chat reaches up to ~11 people. The minted row holds the first
joiner. Each further joiner through the same `t` gets a **sibling row**: same referrer and
league, `share_token` = the parent's id, a fresh unique `invite_token`
(`<share_token>~<6 random chars>`), `status 'joined'`. "Joins per share" = rows grouped by
`share_token`. `uq_referral_pair` (`database.py:2614-2615`) keeps one row per
(referrer, referred). A referred user is credited at most once overall (first session only).

### 7.7 Activation

FR-17. The invitee's first `trade_proposed` or `match_swiped` (stage 7 `first_opinion`)
within 14 days of `joined_at` (proposed). `trades_generated` (stage 6) never activates: it
fires seconds after the first deck load, and the replenish cron fires it with no user
present.

### 7.8 Notification rules

| Moment | Inviter gets | Others get |
|---|---|---|
| Join attributed (token or league match) | one `referral_joined` row (FR-18); their existing `league_member_joined` push, unchanged | unchanged `league_member_joined` row + push |
| Join not attributed | nothing new (a legacy `ref` alone notifies no one, FR-15) | unchanged |
| Activation | one `referral_activated` row (FR-19) | nothing |

With stage 7, the activation row no longer lands seconds after the join row; it waits for
the invitee's first like or pass. If both would still fire within 10 minutes (an invitee who
joins and swipes at once), the activation row posts as its own row: they are different
events. Holding or merging it is an open item for `engagement-pm` (D-9). `ux-lead`'s position
(R-F7): if the activation lands while the join row is still **unread**, merge the two into
one row with the activation title, so one person gets one row; otherwise post it separately,
as written.

### 7.9 Fraud and spoofing

- League scope is the structural control: no credit without verified co-membership.
- The id is minted by an authenticated, verified session for a league that session belongs
  to (§8.1); it can't be forged to credit someone else.
- New users only; one credit per referred user ever; 10 mints per inviter per league per
  day.
- A legacy `ref` can no longer make a bell row fire at an arbitrary user.

---

## 8. API contracts

### 8.1 `POST /api/invite/token` — new

- **Auth:** `X-Session-Token`; verified, non-demo session.
- **Flag:** `growth.referral_ledger`; off → `404 {"error":"not_found"}` (the client treats any
  non-201 as "fall back").
- **Body:** `{"league_id": string (required), "surface": "league_home" | "matches_empty" | "trades_banner" | "members_overlay" | "notif_empty" | "web_invite" (required)}`
- **201:** `{"invite_id": "<12 chars>", "league_id": "<id>", "expires_at": "<ISO UTC, created + 30 d>"}`
- **Errors:** `400 missing_league_id | invalid_surface`; `401 session_expired`;
  `403 verification_required` (demo/unverified) `| not_member` (caller not in `league_id`, by
  the same membership source session init uses); `429 rate_limited` with `retry_after_s`
  (FR-6).
- **Writes:** one `referrals` row: `referrer_user_id` = session `user_id`, `league_id`,
  `invite_token` = `share_token` = the id, `status 'pending'`, `surface`, `created_at`.
- **Never** returns a URL; each client builds it (one builder per client, §7.2).

### 8.2 `GET /app/league/join/<league_id>` — changed

- **Query:** `t` (optional, `^[A-Za-z0-9_-]{8,64}$`, else ignored), `ref` (legacy, optional).
  Unknown params dropped as today (T7).
- **`growth.join_landing` off:** 302 exactly as today (`S:12596-12624`), except that with the
  ledger flag on, a well-formed `t` is forwarded: `Location: /?league=<id>[&ref=<u>][&t=<id>]`,
  built with `urlencode` from a closed dict, relative, never an f-string. T4–T7 unchanged.
- **`growth.join_landing` on:** `200 text/html`, `Cache-Control: no-store`. Content per FR-7.
  League name: Sleeper public API only (as `invite-meta` today) unless decision D-10 allows a
  valid id to unlock the stored name for an imported league. Inviter: `users.display_name` of
  the id's referrer when `invite_status = valid`, else none.
- **Both modes:** FR-8 open recording.
- **Click-through, new:** `GET /app/league/join/<league_id>/go/<cta>[?t=<id>|?ref=<u>]` where
  `cta` ∈ `ios | web` (closed set, else 404). `ios` → 302 to `IOS_INSTALL_URL` (404 when
  unset); `web` → 302 to `/?league=<id>` plus `&t=<id>`, or the inbound legacy `&ref=<u>`
  only when there is no `t` (FR-9's closed contract). Records server event
  `invite_landing_cta` on a human GET only, through FR-8's tested filter (C4). No
  user-supplied URL is ever a redirect target. The landing carries no `dtf://` link in v1
  (§3 non-goal 13), and shows the `ios` click-through only when `IOS_INSTALL_URL` is set
  (FR-7). The desktop QR code (FR-7, R-F3) is not a click-through: it encodes the join URL
  itself, so a scan is recorded as a landing open from the phone (FR-8). It is generated
  server-side as inline SVG in this response; no QR service is ever called (AC-7f).
- **HEAD:** headers only; nothing recorded.

### 8.3 `GET /api/league/invite-meta` — additive

- New optional query `t`. Response adds `inviter_display_name` (string | null) and
  `invite_status` (`valid | expired | unknown | league_mismatch` | null when `t` absent).
  The field shares the event prop's name, so the status has one name everywhere
  (`growth-pm`, 2026-10-15, on condition C1; the addendum notes an API field is not a prop
  and so did not require it).
  `league_name` rules unchanged unless D-10. Still public, read-only, degrade-never-fail
  (`S:26445-26482`).

### 8.4 `POST /api/session/init` — additive

- New optional body field `invite_id` (string, same pattern as §8.2 `t`). Ignored when the
  ledger flag is off or the user is not new. Response unchanged. `invited_by` still accepted.
- **Accepted, not Phase 1 critical path:** optional `first_touch:
  {utm_source, utm_medium, utm_campaign, utm_content}` attached to `signup` props, per
  [marketing-inputs.md §C](marketing-inputs.md#c-utm--install-source-convention-mkt-seo) ("Composition and capture", "Proposal for analytics-lead"). Proposed by
  `marketing-lead`; the convention was accepted by `analytics-lead` (P18; analytics-lead,
  2026-10-15), who writes the final convention as a tracking-plan addendum before any
  emitter. Conditions:
  - It is an **API contract change**: full gates and a `docs/api-reference.md` update, never
    express (bright line).
  - Value check: a `utm_*` value that doesn't match the convention is **coerced to `other`
    with a counter, not dropped**, so the event is kept (§10).
  - Attribution covers only accounts created after it ships; **no back-fill**.

### 8.5 `GET /api/invite/impact` — contract change

Still behind `invite.k_factor_dashboard` (off → today's zeroed payload). On:

```json
{
  "enabled": true,
  "totals":  {"links_created": 0, "links_opened": 0, "joined": 0, "activated": 0},
  "last_30_days": {"links_created": 0, "links_opened": 0, "joined": 0, "activated": 0},
  "by_method": {"token": 0, "league_match": 0},
  "leagues": [{"league_id": "…", "links_created": 0, "links_opened": 0, "joined": 0, "activated": 0}]
}
```

`links_opened` counts minted rows with `open_count > 0` or status `joined` or later.
`k_factor`, `invited`, `active_rankers` and the milestone badges are removed (the web modal
reading them, `web/js/app.js:5927-5940`, is updated in the same change; the badges carry
emoji, which the design system forbids, and their return, as Chalkline icons and never emoji,
is a `design-lead` call in Phase 2, §12).

---

## 9. Schema deltas

`referrals` (`backend/database.py:2595-2617`). Added through `_migrate_db`'s
`migration_cols` (`database.py:3345-3360`) plus the table definition, with explicit
`CREATE INDEX IF NOT EXISTS` for the indexes (existing tables don't get new indexes from
`create_all`).

| Column | Type | Notes |
|---|---|---|
| `share_token` | VARCHAR, indexed | The id in the link. = `invite_token` on the minted row; the parent's id on sibling rows (§7.6) |
| `surface` | VARCHAR | `InviteSurface` at mint |
| `opened_at` | VARCHAR | First human landing open (ISO UTC) |
| `last_opened_at` | VARCHAR | Latest human landing open |
| `open_count` | INTEGER, `server_default 0` | Human landing opens |
| `unfurled_at` | VARCHAR | First link-preview fetch |
| `attribution_method` | VARCHAR | `token` \| `league_match`; NULL while pending |

New index `ix_referrals_league_status (league_id, status)` for §7.5. Reused unchanged:
`referred_user_id`, `status` (`pending → joined → activated`; `rewarded`, `rejected`,
`expired` reserved), `joined_at`, `activated_at`, `qualifying_event`
(`'trade_proposed'` or `'match_swiped'`, FR-17). Comment fix: `league_id` is any
platform's league, not only Sleeper.
`uq_referral_token` and `uq_referral_pair` stay. **No change to `users`.**

---

## 10. Events (proposals for analytics-lead)

**Granted.** `analytics-lead` granted these rows on 2026-10-15 in the analytics addendum, PR
#350 (`docs/business/analytics/2026-10-15-referral-loop-events.md`), with conditions C1–C9;
the tables below match that grant. The emitting eng worker registers and classifies each
name and prop in the emitter's own commit (C7, FR-24; D-040). Server events are new names (the
client and server namespaces must stay disjoint, `analytics_taxonomy.py:1757-1781`).

**Server-fired, inviter-owned: NON_INTENT, and that is mandatory.** `user_id` = the referrer
(or `system:invite` when no referrer resolves, following the `system:api` precedent,
`analytics_queries.py:60-62`), while the person acting is the invitee; INTENT would give the
referrer a user-day for someone else's act. They are written through a **non-touching**
path: `record_event` today bumps the owner's `users.last_active_at` and `events_count`
(`database.py:4436-4458`), which would make a dormant inviter look active to the cron ticks
(`database.py:14226-14243`). The proposal is two optional `record_event` parameters,
`platform='server'` (it has none today) and `touch_user=False` (defaults keep today's
behaviour). `head-eng` decides the mechanism (D-13); a test proves the write leaves the
referrer's `last_active_at` and `events_count` unchanged (C6).

| Event | New / changed | Props | Fires when | Class |
|---|---|---|---|---|
| `invite_landing_opened` | new, server | `invite_id`? (the well-formed `t` as received, else omitted), `league_id`, `invite_status` (`valid\|expired\|unknown\|league_mismatch`\|null when `t` is absent; renamed from `token_status`, C1), `device_class` (`ios\|android\|desktop\|other`) | **Every** human GET of the join path with the ledger flag on, landing or 302 mode, with or without `t` (FR-8, R1); human per C4's tested filter | NON_INTENT |
| `invite_landing_cta` | new, server | `invite_id`?, `league_id`, `cta` (`ios_install\|web_app`; paths `/go/ios\|/go/web`), `device_class` | A human GET (C4) of the click-through (§8.2) | NON_INTENT |
| `referral_attributed` | new, server | `invite_id`, `referral_id`, `league_id`, `attribution_method` (`token\|league_match`), `league_platform` (`sleeper\|espn\|mfl\|fleaflicker`), `notified` | §7.4 / §7.5 credit. **No invitee id** (C2): join through `referral_id` to the ledger, so the referred user's account deletion covers it | NON_INTENT |
| `referral_activated` | new, server | `invite_id`, `referral_id`, `league_id`, `days_to_activate` (int 0–14), `notified` | FR-17: the invitee's first stage-7 event, read from `FUNNEL_STAGES` (C5; today `trade_proposed` or `match_swiped`), within 14 days of `joined_at`; never `trades_generated` | NON_INTENT |
| `signup` | changed, server (owner: the new user) | + `attribution` (`token\|league_match\|legacy_ref\|none`), `attribution_miss` (`unknown\|expired\|not_member\|null`) (FR-16); first-touch props once §8.4's accepted change is built | First session | unchanged |

`notified` is accepted as a prop; there is no separate notification-created event (C8).

**Store nothing that identifies a visitor (C4).** The landing and click-through events store
only the `device_class` bucket, never the user-agent string or the IP.

**Notification meta (not event props).** The `referral_activated` bell row's meta carries
`new_user_id`, `new_username` and `league_id` (FR-19), as `referral_joined`'s meta carries
`new_user_id` and `new_username` today (`S:22663-22667`). The no-username rule below covers
event props only (C9); the meta stays in the inviter's own inbox row.

**Client-fired.**

| Event | Change | Props added | Emitters | Class |
|---|---|---|---|---|
| `invite_shared` | changed | `invite_id`? (the id the mint returned), `mint_outcome` (`ok\|failed\|timeout\|rate_limited\|disabled\|demo`); `channel` deferred (analytics addendum, PR #350, "Not tracked") | mobile `InviteLeaguematesBanner.tsx:135`; **web, new** | INTENT (unchanged) |
| `invite_cta_tapped` | new web emitter | — (`surface: 'web_invite'`) | mobile; **web, new** | INTENT (unchanged) |
| `invite_cta_shown` | new emitters | — | + Trades banner, members overlay, web modal | NON_INTENT (unchanged) |
| `invite_link_opened` | changed | `invite_id`?; `format` gains `web` | `deepLinks.ts:426`, `LeagueJoinScreen.tsx:77`; **web, new** (`captureReferralFromUrl`) | INTENT (unchanged) |
| `invite_league_pinned` | changed | `invite_id`?; `source` gains `web_autoselect` | `LeaguePickerScreen.tsx:245`; **web, new** | unchanged |
| `invite_pin_failed` | changed | `invite_id`? | `LeaguePickerScreen.tsx:273`; **web, new** | unchanged |
| `share_link_opened` | **new** (missing from the first draft; analytics-lead's P18 grant) | `kind` (`trade\|package\|ref_root`), `has_ref` (bool), `auth_state` (the `invite_link_opened` enum). `utm_*` props wait for the UTM capture build | mobile `handleDeepLink` (`deepLinks.ts:387`), when a non-league link (`/s/*`, `/?ref=`) is parsed | INTENT |

The `surface` prop domain gains `web_invite` (one closed enum shared by `invite_shared`,
`invite_cta_shown` and `invite_cta_tapped`, so it widens all three). No username, display
name or league name in any prop (C9); `has_ref` stays as it is. The client parse rows send
the well-formed `t` as received, else omit `invite_id`. The readout joins events to the
ledger on `invite_id` = `share_token` and `referral_id` = `referrals.id`, and counts an open
once: a web `invite_link_opened{format: web}` after a landing CTA is the next step, not a
second open (addendum, question 1).

**`analytics-lead`'s answers** (analytics-lead, 2026-10-15; its wave-2 report, §"Ask 5" and
§"Ask 3"):
- **P18 UTM convention: accepted** as [marketing-inputs.md §C](marketing-inputs.md#c-utm--install-source-convention-mkt-seo)
  wrote it: four params matching `^[a-z0-9_]{1,40}$`; `ref` = who sent it, UTMs = the surface
  or channel; no usernames, emails or league ids in UTMs; existing `surface` values are
  bridged, never renamed. The final convention is written in the analytics addendum, PR
  #350 ("UTM convention v1"); the build is deferred.
- **`share_link_opened`: granted as INTENT**, the twin of `invite_link_opened` (already
  INTENT), not the NON_INTENT `marketing-lead` proposed. Its row is now in the client table
  above and in scope §1 (analytics-lead's §1 review flagged it missing; `growth-pm`,
  2026-10-15).
- **Ingest value check: a coercion, not a drop.** A non-matching `utm_*` or `channel` value
  becomes `other` and a counter records it; the event is kept, so ingest's accounting
  invariant is unchanged. This is an `analytics_ingest.py` change (`head-eng`
  infrastructure, under `analytics-lead`'s review) with a sabotage test.
- **`session_init.first_touch` is an API contract change** under full gates
  (`docs/api-reference.md`), never express (§8.4, D-11).
- **Attribution exists only for accounts created after ship. No back-fill.**
- **Prod baselines stay unmeasured until W3**, including the nine invite and share event
  counts and new accounts per week. Every §2.2 value stays **assumed** until then.
- **`signup.attribution` values** (decided by `growth-pm`, 2026-10-15; **canonical in the
  analytics addendum, PR #350**, which matches): `token | league_match | legacy_ref | none`
  (FR-16), plus `attribution_miss` (`unknown | expired | not_member | null`). A `signup` row
  from before the ledger flag turns on carries no props: a missing `attribution` means
  pre-instrumentation, not `none`. They supersede the `link | none` that `analytics-lead` granted from
  `marketing-lead`'s earlier proposal, which predates the ledger: `link` splits into `token`
  and `legacy_ref`.

**Surface vocabulary** (decided by `growth-pm`, 2026-10-15; the analytics addendum, PR #350,
keeps the existing `surface` values and adds `web_invite`; [marketing-inputs.md §D](marketing-inputs.md#d-decisions-needed) D5, "vocabulary
bridge"):
- **The canonical surface vocabulary is the existing `surface` prop values.** `growth-pm`'s
  earlier ad-hoc names (`invite_card`, `invite_banner`, `league_tab`, `share_package`,
  `trade_card`) are retired; no prop, UTM or ledger column uses them.
- **Invite surfaces** (`InviteSurface`, and the ledger's `surface` column at mint):
  `league_home`, `members_overlay`, `matches_empty`, `notif_empty`, `trades_banner`, plus the
  new `web_invite` for the web modal (§8.1, FR-5). `league_tab` is dropped: the League tab's
  inline link reports `league_home` through the same handler (`LeagueScreen.tsx:478-494`),
  and v1 doesn't need to split the card from the inline link. Invite links still carry no
  UTMs (§3 non-goal 6).
- **Share surfaces** stay `calc_live`, `calc_in_league` and `trades_liked`
  (`mobile/src/utils/shareLinks.ts:28`). The link format is a separate `kind`
  (`package | trade | ref_root`), and image vs text is `utm_content` = `image | text`, so
  `share_package` and `trade_card` are not surface values.
- **Open, not on Phase 1's path:** the analytics addendum's UTM bridge table (PR #350, "UTM
  convention v1") still uses `invite_card`, `invite_banner`, `league_tab`, `share_package`
  and `trade_card` as `utm_content` values, and maps share `utm_content` to the surface
  rather than `image | text`. `growth-pm` and `analytics-lead` reconcile it before the UTM
  capture build; invite links carry no UTMs in v1 either way.

---

## 11. Flags and config

| Key | Kind | Default | Gates | Graduation | Rollback |
|---|---|---|---|---|---|
| `growth.referral_ledger` | **new flag** | false | Mint route (404 off); clients' use of the id (off ⇒ byte-identical links); open recording; §7.4–§7.8 attribution, activation and notification rules; impact v2 | Phase 0 done + 2 weeks with the §2.1 instrumentation target met | Flip off: mint 404s, clients emit today's links, attribution stops; rows stay |
| `growth.join_landing` | **new flag (proposed here; `growth-pm` to accept, D-7)** | false | Landing page vs today's 302 on `/app/league/join/<id>`; also the `/s/*` device-aware CTA target (FR-25; accepted by `growth-pm` 2026-10-15, `head-eng` confirms in allocation) | Words approved (`marketing-lead`; the launch slice approved by the operator 2026-10-23, D-5), `design-lead` `/design-review` verdict (§13), operator device pass on iPhone / desktop / Android | Flip off: today's 302, T4–T7 contract |
| `growth.invite_join_link` | existing (`config/features.json:190`) | false | Emitter form only (unchanged meaning) | **Flip in Phase 1** after the #239 device checklist passes (`docs/feedback/items/239-invite-universal-links/status.md` § Operator actions 4; procedure `config-reference.md:669`) | Flip off (legacy form parsed forever) |
| `growth.referral` | existing, **reserved** | false | Nothing in v1. Its declared meaning includes reward granting (`backend/feature_flags.py:268`) | Phase 3, gated on the operator approving the pricing memo (P20) | — |
| `invite.k_factor_dashboard` | existing (`config/features.json:20`) | false | Impact payload v2 (FR-21). Key name kept to avoid churn; meaning updated in `config-reference.md` | Phase 2 surface | Flip off |
| `IOS_INSTALL_URL` | **new env var** | unset | The landing's iOS install CTA and the desktop QR-primary layout ("Join on your iPhone" with the QR code and the iOS link, R-F3, FR-7; §5); the `/s/*` iPhone CTA (FR-25). Unset ⇒ honest note on iPhone; on desktop the web app stays primary, with no QR and no iOS link | Operator sets it to the public TestFlight link they create (D-3, 2026-10-15); on launch day (2026-11-18, §12) the App Store URL, which flips the iPhone labels to the store pair with no deploy (FR-7's host rule). Only an `https://` URL on `testflight.apple.com` or `apps.apple.com` counts; any other value is treated as unset and logged once. An environment value only: no link value is ever written in the repo | Unset it |

New flags are registered in `backend/feature_flags.py` `FLAG_KEYS`, `config/features.json` and
`backend/tests/fixtures/flags/release.json` together (an unknown JSON key fails the guard).

---

## 12. Phasing and rollout

- **Phase 0 (operator, no build):** run the #239 universal-link device checklist (D-2; the
  `app-manager` lead turns it into a device-ready version, its Run A); create the public
  TestFlight link (D-3; CTA option A is decided, D-1, 2026-10-15); approve words via
  `marketing-lead` (the launch slice approved 2026-10-23, D-5); put `gp.testflight.what_to_test` (J2) in the TestFlight build's "What to
  Test" text (D-2, `ux-lead` R-F1; `app-manager` drafts What to Test, the operator pastes it in
  App Store Connect). (The
  reward question is closed: reward-free v1, `head-product` P20.)
- **Phase 1 (build, flag-gated):** FR-1…FR-25. Backend lands first with every flag off; clients
  read the flags; nothing user-visible changes at merge except FR-3 (copy) and FR-4
  (impression events).
  - **First build slice** (`head-product` → `head-eng`, 2026-10-15, after the operator's
    "Ok. start building D1 and D3"): FR-7 (join landing), FR-8 (server open record), FR-9
    (desktop onward link and web capture), §8.2 (the join route and its click-through) and
    `IOS_INSTALL_URL` as config (§11). `head-product` pulled **FR-25**, the `/s/*` CTA target,
    forward into this slice; the rest of the `/s/*` work stays in GB-02.
- **Phase 2:** APNs `referral_joined` / `referral_activated` pushes (GD-5, `NEXT.md:532`;
  `engagement-pm`: caps, prefs, buckets); the inviter's "Your invites" surface on top of
  `/api/invite/impact` (`design-lead`: tiles with live counts in IBM Plex Mono, the operator's
  tile preference; milestone badges, if they return, use Chalkline icons, never emoji). The
  `/s/*` CTA target is no longer here: it moved into Phase 1's first build slice (FR-25).
- **Phase 3:** rewards, gated on the operator approving the pricing memo (P20). Rewards are
  paid entitlement time: `monetization-pm` designs the reward economics; `growth-pm` defines
  "activated" and the mechanics. `promo_referral` / `promo_group_unlock` sources in
  `backend/entitlements.py:50`, never granted; behind `growth.referral`.

**Phase 1 rollout sequence — each step gates the next:**

| Step | Action | Gate |
|---|---|---|
| 1 | Merge + deploy backend: schema, routes, registrations, flags off | Probes: mint → 404; join path → today's 302 byte-identical; CI green |
| 2 | Ship clients (mobile build + web) | Flags off ⇒ links byte-identical (structural guard) |
| 3 | Operator: #239 device checklist (tap a path-form link from Messages; app opens) | Pass recorded in `TEST_LEDGER.md` |
| 4 | Flip `growth.referral_ledger` | Mint 201s live; first ids in the ledger |
| 5 | Set `IOS_INSTALL_URL` (option A, D-1; the operator's link, D-3); flip `growth.join_landing` (the join landing and the `/s/*` CTA target, FR-25) | Words approved (D-5, 2026-10-23); `ux-lead` R-F1–R-F3 landed (step 1 / step 2, the "What to Test" re-tap line, the desktop QR-primary layout); `design-lead` `/design-review` verdict (`design-review.md`), including its check of R-F1's step list and R-F3's QR block against FR-7 (confirmed 2026-10-15, D-16); operator landing pass, including scope §3 steps 4b and 11b |
| 6 | Flip `growth.invite_join_link` | Only if step 3 passed; otherwise stay on the legacy form, which still carries `t` |
| 7 | Two-week read | §2.1 target → graduate `growth.referral_ledger` |

### Launch slice (launch Wed 2026-11-18)

The operator, 2026-10-23 (via `growth-pm`): "Launch relies on invites: Yes, hold for it."
Dates are `head-eng`'s (`docs/plans/org-bringup/launch-plan-1118.md`): the binary is
feature-complete **Fri 11-06**; the referral slice is live server-side **Mon 11-16**; launch
is **Wed 11-18**, when the launch-day copy flips with `IOS_INSTALL_URL`. Calls are
`growth-pm`'s, 2026-10-23.

| Piece | Runs where | Gates launch? | Note |
|---|---|---|---|
| D-1 build: join landing (FR-7), `/go/<cta>` click-through (FR-9, §8.2), FR-8 open recording, the `/s/*` CTA (FR-25) | server | **Yes** | Live by 11-16. FR-8 records nothing until `growth.referral_ledger` flips (the server row below) |
| `growth.invite_join_link` flip, after the D-2 device run | flag | **Yes** | The live binary emits legacy `/?league=` links, which skip the join landing, until it flips |
| `growth.join_landing` flip, after D-5 words (approved by the operator 2026-10-23, package §2), the OG asset and `design-lead`'s `/design-review` | flag | **Yes** | Also turns on FR-25's device-aware `/s/*` CTA |
| `IOS_INSTALL_URL` = the App Store URL on launch day | config | **Yes** | Flips the iPhone labels to "Get the iPhone app" / "Opens the App Store." on 11-18 with no deploy (FR-7's host rule). **Release-day check** (U4, package §6): as part of the flip, `release-lead` confirms the value's host is `apps.apple.com`. Any other host, or a non-`https://` value, renders the unset states (AC-7g), whose beta-era notes ("The iPhone beta isn't open to the public yet…") are false after release. The store-era unset note is later slice (below) and needs `marketing-lead`'s words; until it lands, an unset or invalid value after release is a config error, logged once per process (AC-7g) |
| Mobile token pieces: FR-1/FR-2 mobile (the mint call, `t` in the link with the league-only fallback, the busy state that ignores repeat taps; `InviteLeaguematesBanner.tsx`); `t` captured from the deep link into the invite intent (FR-10: `deepLinks.ts`, `LeagueJoinScreen.tsx`, `useSession.ts`); SignIn names the inviter from `t` (FR-11: the one `invite-meta` call sends `t` and the banner shows `inviter_display_name` through the approved headline ladder; `SignInScreen.tsx:203-235`, `api/league.ts:947-975`; U2, package §6); `invite_id` in every mobile session-init body (FR-12/FR-13: `api/auth.ts`, `api/espn.ts`, `api/platformLink.ts`); the mobile events (the `share_link_opened` emitter and the `invite_id` prop on the invite events) | binary | **Yes: must make the 11-06 binary** (it gates the binary, so it gates launch) | Safe to ship before the server: the client falls back to the league-only link while the mint 404s. FR-11 is a must here: FR-2's links carry no `ref`, so without it SignIn drops the inviter name to the shipped "You were invited to {league} — sign in and we'll take you straight there." |
| The `referral_activated` notification type in the app (FR-19: mobile `V2_TRADE_KINDS` in `mobile/src/utils/deepLinks.ts` → Trades; the glyph pinned by `mobile/tests/check-notif-glyphs.js`) | binary | **Yes: must make the 11-06 binary** | Without it, activation rows posted after 11-16 tap to nowhere in the launch binary. The row itself is server-side and can wait (last row) |
| In-app copy: FR-3's strings in the binary: the invite share text, one line with no league name, `gp.invite.msg` "Join me on Fleeced to find trades we both like → {url}" (package §5 D6; no league-name variant ships, `gp.invite.msg_league` is parked); the banner's "leaguemates" re-spelling (spelling only; the `h1.banner.body` rewrite is later slice, D7) | binary | **Yes** (gates the binary) | By 11-06 per the launch plan; words approved by the operator 2026-10-23 (D-5, package §2) |
| Server mint endpoint (§8.1), token attribution and the league-match fallback (FR-13/FR-14), FR-11's server half (§8.3: `t`, `inviter_display_name`), activation (FR-17), the FR-18 join row (ledger-only, title ≠ body, `gp.push.joined_inbox_body`; U3, package §6), the #350 server emitters, the `growth.referral_ledger` flip | server | No | Target 11-16. If it slips, invites still convert and credit starts when it lands; accounts created before it get no back-fill. Until §8.3 lands, SignIn shows the ladder's no-name rungs (FR-11) |
| The `m3.push.joined` name fix on today's `referral_joined` row ("@{new_username} joined Fantasy Trade Finder via your invite.", `S:22662`, title = body so it renders twice) | server | **Yes** | By 11-16 through the copy batch (`engagement-eng`), **even if FR-18 slips**: the old-name row must not be live at launch (U3, package §6) |
| Web legs: the web modal mint (FR-1, FR-5), web `t` capture (FR-9), the web invite events (FR-5) | web | No | |
| Can wait until after launch: the FR-19 activation row (server), FR-21 impact v2, the desktop QR if round 2 slips (fallback: the desktop layout without the QR, web app primary), FR-4 impression events and AC-4b's banner floors, Phase 2 pushes and "Your invites", GB-02 (the share chrome and OG rebuild, `ref` forwarding), rewards (Phase 3), the later-slice strings (below) | mixed | No | |

Everything server-side, web-side or config can land after the 11-06 binary cutoff; the binary
pieces (the mobile token pieces, the `referral_activated` type registration and the in-app
copy) cannot.

**Later-slice strings: not in the 11-06 binary and not in the operator's 2026-10-23
approval** ([package §4](marketing-referral-approval.md#4-later-slice-not-in-the-11-06-binary-not-in-this-approval)).
D-5 stays open for them.
- **The FR-19 activation row:** `gp.inbox.activated_title`, `gp.inbox.activated_body`. The
  binary registers only the type (the row above). If `head-eng` lands the row by 11-16, the
  operator approves these two with the §2 block; otherwise they wait.
- **Phase 2:** the pushes and "Your invites": `gp.push.referral_title`,
  `gp.push.referral_body`, `gp.push.referral_inbox`; the lab §5 labels 1 and 2, the
  "Activated" explainer, the zero-join line and the empty-state prompt; the OG variant (iii)
  line.
- **GB-02** (FR-25 keeps `og:*` unchanged): `s1.trade.title`, `s1.trade.desc`,
  `s2.pkg.title`, `s2.pkg.desc`, `s4.og_site`.
- **The store-era unset note** (U4, package §6): the honest note for an unset or invalid
  `IOS_INSTALL_URL` after release, replacing the beta-era unset notes on the landing and
  `/s/*`. No key or words yet (`marketing-lead`); until it lands, that state is a config
  error, logged once per process (the `IOS_INSTALL_URL` row above).
- **No build home in this PRD** (a later voice and claims pass): `h1.card.tick`,
  `h1.rationale`, the `h1.banner.body` rewrite (D7: in the 11-06 binary the banner body is
  re-spelled only, FR-3); `h2.web.chat`, `h2.web.groupme`, `h2.web.email`; `h3b.join.fail`,
  `h5.signin.invite`, `h5.signin.invite_noref`.
- **Parked:** `gp.invite.msg_league`, the league-name invite variant (D6; FR-3).
- **Dropped:** `gp.join.retap`, replaced by `gp.join.step2`; `gp.join.cta.B`, because option
  B wasn't chosen.

This answers `launch-plan-1118.md`'s question (its Mon 11-16 row): **yes, part of the referral
slice needs the binary**: the mobile token pieces, the type registration and the in-app copy.
Everything else is server, web or config.

---

## 13. Seams and reviews

| Seam | What they decide or review | Route |
|---|---|---|
| `marketing-lead` | All strings: invite text, join landing (`gp.join.*`), inbox rows (`gp.push.*`), activation row; UTM values | W4 direct (operator-approved 2026-10-15) |
| `design-lead` | Join landing (Chalkline, FR-7; per-surface states: logged-out, not installed, expired/unknown link, flag off; iPhone/desktop/Android; no "already joined" state: the landing has no auth and one link can credit several joiners, so that state lives in the in-app J4 path), its OG card (FR-7: static 1200×630; art direction P14), the invite card/banner diff (FR-3/FR-4: copy and events, FR-1's busy state, AC-4b's Invite button floors), Phase 2 "Your invites" tiles. **Mockup lab:** draft PR [#343](https://github.com/mattmurf77/fantasy-trade-finder/pull/343), `mockups/referral-loop/index.html` @ `899f8619` (branch `mockup/referral-loop`): landing frames **A1** iPhone with `IOS_INSTALL_URL`, **A2** iPhone without, **A3** desktop, **A4** Android, **A5** expired/unknown invite, **A6** unknown league name (plus option B drawn as not recommended); OG variants (i) wordmark only, (ii) wordmark + ram (**v1**, FR-7), (iii) league name (Phase 2); banner and card before/after, including FR-1's busy state; Phase 2 "Your invites" tiles. The "Open in the app" button drawn on A1, A2, A5 and A6 is out of v1 (§3 non-goal 13). Before-panes: the web ones (W1–W3, and the `og_image.py` card) are local renders of `origin/main` `678834a` (`head-product` P22); the mobile ones (banner, card, share text) are labelled reconstructions from source. Every string stays with `marketing-lead`; the lab tags each PROPOSED COPY and each `[copy: marketing-lead]` slot (D-14). The build gets a `/design-review` verdict at `docs/plans/referral-loop/design-review.md` before ship, on the build branch. **Gate-1 asks (`ux-lead`, PR #348) answered by `design-lead` 2026-10-15 (D-16 resolved):** R-F1's step list on A1 and R-F3's desktop QR block are confirmed with specs (FR-7, AC-7c, AC-7f), checked in `/design-review` on the build branch; `design-lead` adds the QR's chalk panel to the exceptions register; the `/s/*` QR and Chalkline chrome fold into GB-02 (FR-25). F1 (outside this PRD) is in §16 | W4 direct |
| `ux-lead` | The J2 flows, especially re-tap after a TestFlight install. **Reviewed 2026-10-15 (PR #348): approve with changes**, R-F1…R-F8 folded per `growth-pm`'s rulings (J1, J2, J4, FR-1, FR-7, FR-19, §7.8, D-9) and its checklist steps added to scope §3 | via `head-product` |
| `analytics-lead` | Event names and classes (§10: **granted 2026-10-15 in the analytics addendum, PR #350**, conditions C1–C9 folded), the grant the emitting eng worker registers under (C7), the activation stage (D-8), the readout (FR-22), the first-touch convention (P18), the W3 baseline | via `head-product` |
| `engagement-pm` | In-app entry points; the notify-once rule (FR-20); the activation row as a receipt (D-046) and its routing to Trades, not League (FR-19; v1 keeps the tap, `marketing-lead`'s reworded body names no place, R-F6); the join/activation timing open item, with `ux-lead`'s merge-when-unread position (§7.8, R-F7, D-9); Phase 2 pushes | via `head-product` |
| `onboarding-pm` | LeagueJoin, SignIn banner from `invite-meta`, web landing capture (its invite-context emphasis in flare or chalk, never `--pos` green: FR-9, AC-9b), LeaguePicker companion; the J4 league switch (R-F4: a one-line inline confirmation if checklist step 7b fails, shared with `growth-pm`) and step 7c | via `head-product` |
| `platforms-pm` | ESPN/MFL/Fleaflicker session-init attribution and per-platform co-member verification (§7.4 step 3) | via `head-product` |
| `monetization-pm` | Reward economics for Phase 3 (paid entitlement time, in its pricing memo; the operator approves it first). v1 is reward-free by `head-product` P20 | via `head-product` |
| `head-eng` | File allocation (likely `engagement-eng`: ledger, invite routes, landing, attribution; `onboarding-eng`: `web/`, LeagueJoin, SignIn); the `record_event` change; the token-gated league name (D-10, security) | via `head-product` |

Per the non-user-surface seam rule: `growth-pm` decides what the landing shows and where the
CTA points; `engagement-eng` builds the invite routes and landing; `onboarding-eng` builds
`web/`, LeagueJoin and SignIn; `marketing-lead` writes the words.

---

## 14. Risks

| Risk | Likelihood / impact | Mitigation |
|---|---|---|
| Link-preview fetchers counted as opens, inflating `o` and seeding false league matches | High / high | Bot UA list (FR-8) pinned by tests; HEAD ignored; checklist step verifies an iMessage preview does not increment `open_count` |
| League match credits the wrong inviter when several invited | Medium / medium | Most-recent-open rule, legacy-ref tie-break, `attribution_method` stamped so the readout can separate it |
| iOS invitee doesn't come back to re-tap after TestFlight | High / medium | League-match fallback; the CTA and the re-tap line numbered step 1 / step 2 of one task (R-F1); the "What to Test" line (`gp.testflight.what_to_test`, J2) in the TestFlight build, shown beside TestFlight's Open button (D-2); the cheapest test in GB-01 measures the gap |
| A re-tap inside an in-app browser (Sleeper chat, Discord, GroupMe) reopens the landing instead of the app (`ux-lead` R-F2) | Unknown until tested / medium; blocking if it loops | Checklist step 4b (scope §3); if it reproduces, A1 and A2 gain `gp.join.iab_wayout`, "Have the app and still seeing this page? Open this link in Safari, or tap it in Messages." (on A2 it replaces the note's last sentence; cut to Messages only if Safari doesn't hand off; FR-7) |
| Mint latency or a cold backend delays the share sheet | Medium / medium | 2 s deadline, fallback link, `mint_outcome` measured |
| Inviter rows bump `last_active_at` and suppress winback | High if unmitigated / medium | Non-touching write (§10) |
| `invite_id` dropped at ingest | Certain if named `*token*` / high | FR-24 naming rule, structural check |
| iPadOS presents a desktop UA | Medium / low | With `IOS_INSTALL_URL` set, the desktop layout leads with the phone path and keeps the iOS install link in its QR block as a 44px text link (R-F3, FR-7); checklist step 11b covers an iPad |
| ESPN/MFL membership can't be verified before the invitee links that platform | Medium / medium | Credit happens at the first session in that league; `platforms-pm` review |
| Imported league names exposed by a token-gated lookup | Low / medium | D-10 default is no; Sleeper public names only |
| Group-chat posting reads as spam to a league | Low / high (Sleeper relations) | League scope; 10/day cap; no automated posting; `platforms-pm` |
| Legacy links already in chats lose credit when the flag flips | Certain / low | Accepted (amendment: credit only from verified ids or league match); `legacy_ref` stays visible in `signup` props |
| TestFlight two-step and 10k tester cap | Medium / medium | Option C end state is one env value away |
| The desktop path rarely completes: the extension is an unpacked Chrome/Edge release, not a store listing (`extension/README.md:44`), so few desktop invitees will sideload it (`marketing-lead`, lab addendum) | High / medium | Option A's working install path is effectively iOS TestFlight; this strengthens D-1 (A) and D-3 (the public TestFlight link). With `IOS_INSTALL_URL` set, the desktop layout leads with "Join on your iPhone" and a QR code of the invite URL, and the web app becomes the secondary action (`ux-lead` R-F3, `growth-pm` P19, confirmed by `design-lead` 2026-10-15, D-16); unset, the desktop CTA stays the web app, with its accurate extension line (`gp.join.cta.A_desktop_help`) |

---

## 15. Decisions needed

| # | Decision | Who | Recommendation |
|---|---|---|---|
| D-1 | CTA target A/B/C before the listing (§5) | **Resolved by the operator 2026-10-15: A** ("Ok. start building D1 and D3", verbatim via `head-product`) | Option A, device-aware: iOS → `IOS_INSTALL_URL` (the public TestFlight link); desktop → the web app with the extension line; Android and other phones → the honest note (§5, FR-7, FR-25) |
| D-2 | Run the #239 device checklist; **and** put the "What to Test" line in the TestFlight build's text (`ux-lead` R-F1; proposed by `marketing-lead`, `gp.testflight.what_to_test`: "Here from a league invite? After installing, go back and tap the invite again, or rescan its code. That opens the app on your invite."; accepted by `growth-pm`: TestFlight shows it beside its Open button, so it reaches the invitee at the right moment; no code) | **operator**. **Open.** The new `app-manager` lead turns the checklist into the operator's device-ready version (its Run A; scope §3's checklist is its Run B) and drafts "What to Test"; `marketing-lead`'s line (J2) was approved by the operator 2026-10-23 with D-5 (package §2). App Store Connect is the operator's own entry | The checklist before rollout step 6; the "What to Test" line on the build Run B uses, before rollout step 5 |
| D-3 | Create a public TestFlight link | **Resolved by the operator 2026-10-15** (same quote): the operator creates it | The link becomes the `IOS_INSTALL_URL` value (§11); no link value is ever written in the repo |
| D-4 | Rewards | **Resolved by `head-product` P20 (2026-10-15): reward-free v1** | Status and recognition only in v1. Rewards are Phase 3, gated on the operator approving `monetization-pm`'s pricing memo; `monetization-pm` designs the economics, `growth-pm` defines "activated" and the mechanics (§12) |
| D-5 | Approve the words (`gp.*`). Gate 1 added to the list: the A1 step 1 / step 2 framing (R-F1); the desktop QR state's TickLabel "Join on your iPhone", its scan line, the line "Have the Fleeced extension for Chrome or Edge?" with "Open the web app", the iPad link "On an iPad? Get the iOS beta, then tap the invite again." and the QR's accessible name (e.g. "QR code: opens this invite on your iPhone") (R-F3, D-16); A1's "Install Fleeced" and step 2 "Tap the invite again, or rescan its code, to join {leagueName}." and the revised A2 note (R-F1); the reworded activation body `gp.inbox.activated_body`, "When they like a trade with you, it can show up with a "They're interested" tag." (R-F6, FR-19); the "What to Test" line (D-2); and, only if their checklist steps fail, the installed-user line `gp.join.iab_wayout` on A1/A2 (R-F2, step 4b) and the J4 league-switch confirmation (R-F4, step 7b). The launch-day copy (marketing-lead copy batch, 2026-10-23) is added too: the store pair "Get the iPhone app" / "Opens the App Store." (chosen by the `IOS_INSTALL_URL` host, FR-7), the iPad line's store form (`growth-pm`'s placeholder, adopted verbatim by `marketing-lead`, package §5 D4), the Android note "Available on iPhone and desktop web for now." and `gp.join.og_desc` | **operator** via `marketing-lead`. **Resolved for the 26 entries of [marketing-referral-approval.md §2](marketing-referral-approval.md#2-operator-approval): approved by the operator 2026-10-23**, given in `head-bizops`' session (relayed by `head-bizops`) and confirmed by `head-product` 2026-10-23. Verbatim: "Approve all three as written: the App Store listing §5 (recommended subtitle "Your rankings. Deals for both."), the copy file §6 meaning changes, and the referral package §2 (26 entries)." All 26 are approved as written, including the contingent `gp.join.iab_wayout` (it ships only if checklist step 4b fails) and the host-keyed install labels (`m4.348.cta_ios`, `m4.348.cta_ios_help`: they still flip only on 11-18, with `IOS_INSTALL_URL`). **Still open** only for strings outside §2: the later-slice strings ([package §4](marketing-referral-approval.md#4-later-slice-not-in-the-11-06-binary-not-in-this-approval), §12), and the contingent J4 league-switch confirmation, which has no words yet (step 7b) | — |
| D-6 | Accept the PRD; **supersede D-028 part 2** (a real join page instead of the 302 into `/`), because D-028's premise that the existing web funnel converts holds only on desktop with the extension | `head-product` (new DECISIONS entry, id claimed against `origin/main`) | Yes |
| D-7 | Second flag `growth.join_landing` | `head-product` / `growth-pm` | Yes: independent rollback for the riskiest surface |
| D-8 | Activation = stage 7 first opinion (vs 5 or 6) | `analytics-lead` | Stage 7: the first `trade_proposed` or `match_swiped` within 14 days of `joined_at` (FR-17) |
| D-9 | Notify-once rule (FR-20); the activation row routes to Trades, not League (FR-19; v1 keeps the tap and `marketing-lead`'s reworded body names no place, `growth-pm` on R-F6; revisit if `trades-pm`'s #339 D10 ships). Open item: an activation row within 10 minutes of the join row posts separately today; hold or merge it? (§7.8) | `engagement-pm` | As written. **`ux-lead`'s position (R-F7):** merge into one row with the activation title if the join row is still unread; otherwise post separately |
| D-10 | A valid id unlocks the stored league name for imported (ESPN/MFL) leagues on the landing and `invite-meta` | `head-eng` (security) | No in v1; revisit with evidence |
| D-11 | First-touch UTMs on `session_init` (§8.4) | **Accepted by `analytics-lead` (P18; analytics-lead, 2026-10-15)** | The [marketing-inputs.md §C](marketing-inputs.md#c-utm--install-source-convention-mkt-seo) convention is accepted; `analytics-lead` writes the final addendum before any emitter. Conditions: `first_touch` is an API contract change under full gates (`docs/api-reference.md`); a non-matching value is coerced to `other` with a counter, not dropped; attribution only for accounts created after ship, no back-fill. Outside Phase 1's critical path |
| D-12 | Mint cap 10 per inviter per league per day; token credit window 30 days | `growth-pm` | As written (assumed values) |
| D-13 | `record_event` `platform` + `touch_user` parameters vs a separate writer | `head-eng` | Either; the requirement is no denorm bump |
| D-14 | Copy questions from `design-lead`'s lab (§13). **Answered by `marketing-lead` 2026-10-15, all proposed** ([lab addendum](marketing-inputs.md#addendum-design-leads-lab-slots-and-growth-pms-four-questions-2026-10-15)): (a) every `[copy: marketing-lead]` slot is filled (the A2 note and A5's "A leaguemate invited you to {league}", FR-7; `og:title` = `gp.join.og_title`; the Phase 2 tiles' labels, "Activated" explainer, empty-state prompt and zero-join line, in the addendum); (b) FR-11's "{display name} invited you to {league}" **is** the landing headline, superseding `gp.join.headline`, with FR-7's fallback ladder; (c) "Dynasty Trade Finder" may appear on the OG card only locked up with the wordmark, smaller, never standalone (FR-7; the D-057 name is "Fleeced: Dynasty Trade Finder"); (d) **"leaguemates"**, one word (FR-3; the banner's "league-mates", `InviteLeaguematesBanner.tsx:163, :167, :176`, is respelled in this build). **Follow-up, answered** (`marketing-lead`, lab addendum, "`ux-lead`'s review of PR #348"): the A2 note now reads "…Already have it? Tap the invite again, or rescan its code.", so it names the re-tap itself (FR-7) | `marketing-lead`; the operator approves the words with D-5 (the launch slice approved 2026-10-23, package §2) | Approve with D-5, before rollout step 5 (the landing and OG card ship no words without them) |
| D-15 | The OG card wordmark's period. `marketing-lead` had asked for no period on the OG card, because next to a trade "FLEECED." reads as a verdict ("you got fleeced"); `head-product` proposed that the logotype keeps the period and running copy never uses it (FR-7) | **Resolved by `design-lead` 2026-10-15** (owns the wordmark, P14) | The OG card carries the logotype "FLEECED." with the ice period, Barlow Condensed Bold caps, chalk. Rule (`docs/design/brand.md`, PR [#349](https://github.com/mattmurf77/fantasy-trade-finder/pull/349)): the ice period belongs to the logotype; it goes wherever the logo appears and nowhere else (not verdict cards, headings, badges or buttons). Matches `head-product`'s proposed rule. PR #349 also sanctions the invite OG link card as a ram placement (variant (ii)) |
| D-16 | Desktop layout with `IOS_INSTALL_URL` set (`ux-lead` R-F3): "Get it on your iPhone" with a QR code of the invite URL (`t` included) as the primary, the iOS install link kept in that block for iPad, and "Have the Fleeced extension? Open the web app" as the secondary (FR-7, AC-7c); and R-F1's A1 step layout | **Decided by `growth-pm` 2026-10-15 (P19). Resolved by `design-lead` 2026-10-15** (confirms R-F3, which reverses the desktop rule it had accepted; checked in `/design-review` on the build branch) | Folded into FR-7, AC-7c and AC-7f: the QR block first and primary under a TickLabel ("Join on your iPhone", `marketing-lead`'s label), no ice-filled button, the web app as a Secondary (outlined) button; `--ink-0` modules on a `--chalk` panel (a sanctioned exception, added to the exceptions register), 4-module quiet zone, EC M up to version 6, ≥200 CSS px with whole-pixel modules ≥4 CSS px and `crispEdges` (version ≥7 grows at 4 px modules, never shrinks; `design-lead`'s density rule, 2026-10-15), never inverted; the iPad link inside the block with a 44px target; an accessible name; **server-side inline SVG, never a third-party QR service**. A1: a two-row step list, Plex Mono chalk-dim markers, one hairline. Unset, the desktop layout is unchanged. `/s/*`: the QR and Chalkline chrome fold into GB-02 as one rebuild; FR-25 stays target and labels only |

---

## 16. Handoffs

- **`head-product`:** accept the PRD (D-6); route D-6…D-13. The first build slice is already
  with `head-eng` (§12, 2026-10-15).
- **`head-eng`:** build the first slice first (§12: FR-7, FR-8, FR-9, FR-25, §8.2,
  `IOS_INSTALL_URL`); allocate files (builder TBD; likely `engagement-eng` backend + invite
  routes, `onboarding-eng` web/LeagueJoin/SignIn); confirm FR-25's gate
  (`growth.join_landing`, accepted by `growth-pm`); security handoff on `/s/trade` enumeration
  (`S:25552-25564`, `S:25446-25457`). Gate 1 adds to the first slice: FR-8's tested human-GET
  filter and every-GET recording (C4, R1), the `invite_status` name (C1), the desktop QR
  code (R-F3, D-16: server-side inline SVG, never a third-party QR service, AC-7f; pick a
  server-side library that emits SVG and log it in `living-memory/DEPENDENCIES.md`; apply
  FR-7's density rule and report the encoder's version in the build PR), and the emitter's
  own registration under
  the analytics addendum, PR #350 (C7). Launch slice (`growth-pm`, 2026-10-23, package §6):
  FR-11 must make the 11-06 binary (U2); FR-18 lands server-side by 11-16 with the
  attribution work, and the `m3.push.joined` name fix lands by 11-16 through the copy batch
  (`engagement-eng`) even if FR-18 slips (U3; §12).
- **`analytics-lead`:** §10 is granted (analytics addendum, PR #350; C1–C9 and R1–R3
  folded here). Still open: D-8, the FR-22 readout (including FR-8's note that a desktop QR
  scan is a second open of the same link), reconciling the addendum's UTM bridge values with
  §10's surface vocabulary before the UTM capture build, and the W3 baseline (nine
  invite/share events, new accounts per week, open → signup feasibility).
- **`marketing-lead`:** final words for every quoted string, including the activation row
  (revised to stage 7, FR-19); its S-IDs remap to the backlog's S1–S12. **Its referral
  approval package, vendored as [marketing-referral-approval.md](marketing-referral-approval.md)
  (2026-10-23), is the launch-slice authority for referral wording**; its §2 (26 entries) is
  approved by the operator 2026-10-23 (D-5), its D4–D6 and the `og_title` / `valueprop` /
  `page_title` / FR-18 body text are folded (J1, FR-3, FR-7, FR-18), and its §4 later slice is
  listed in §12. The lab's copy
  questions (D-14) are answered (the launch-slice words approved by the operator 2026-10-23,
  D-5); the OG wordmark period is
  resolved (D-15, `design-lead`: the period is logo-only). The `/s/*` CTA labels, help lines
  and notes for FR-25 are proposed (lab addendum, "Share landings `/s/*` under FR-25"),
  including a share landing's own iPhone-unset note; the operator approved them with D-5
  (2026-10-23, package §2).
  Gate 1's strings are now proposed (lab addendum, "`ux-lead`'s review of PR #348"; folded
  in J2, FR-7, FR-19): A1's step 1 / step 2 (R-F1), the desktop QR state's labels and iPad
  link (R-F3, D-16), the revised A2 note, the activation body (R-F6), the "What to Test"
  line (D-2) and the contingent installed-user line (R-F2); the operator approved them with
  D-5 (2026-10-23, package §2), except the activation body, which is later slice (§12).
  Worded since (package §5 D4, D5; FR-7): the QR's accessible name, "QR code: opens
  this invite on your iPhone", and the iPad line's store form, `growth-pm`'s placeholder
  ("On an iPad? Get the iPhone app, then tap the invite again."), both adopted verbatim. Still
  to word, only if its checklist step fails: the J4 league-switch confirmation (R-F4). Also
  to word, later slice: the store-era unset note (U4, §12). The launch-day rows (copy batch, 2026-10-23: `m4.348.*`, `m3.web.og_desc`) are
  folded in J2, FR-7 and FR-25, with the store labels keyed to the install host, not a date. Keep `gp.inbox.activated_body` in step
  with the "They're interested" pill label (`TradeCard.tsx:525`).
- **FAQ claim → P9's copy-defect batch (`onboarding-pm`) via `head-product`:**
  `web/faq.html:206` says the web app "works in any phone browser", which is false: web
  sign-in needs the desktop extension (§5). The lab's landing footer links to the FAQ.
- **Old-name strings: overlap resolved by P9.** `head-product` put old-name copy defects in
  P9's copy-defect batch (`onboarding-pm`, after this wave). This PRD renames only the strings
  its FRs touch (FR-3); the rest, including `league_member_unlocked_trades`
  (`S:10542-10543`), go to that batch. So does any old-name or name-rule string outside the
  files this PRD touches, e.g. `web/index.html:75` ("Fleeced finds trades…", Fleeced as the
  subject of an analysis verb), via `head-product`.
- **`design-lead`:** landing + OG card + states (§13; lab PR #343 folded); the
  `/design-review` verdict covers AC-4b's banner floors and checks R-F1's step list and
  R-F3's QR block against FR-7 (D-16, resolved by `design-lead` 2026-10-15). Add the QR's
  chalk panel to the exceptions register; check the reported QR version and size against
  FR-7's density rule (`design-lead`, 2026-10-15). The `/s/*` QR and chrome are GB-02's.
  D-15 (the OG wordmark's period) is resolved by `design-lead`, 2026-10-15 (`brand.md`,
  PR #349).
- **`design-lead` → `head-eng` via `head-product` (outside this PRD): F1.** On phones the
  shipped web landing hides the `WR` label but keeps the WR-blue rail
  (`web/css/styles.css:5111`), so position colour is the only encoding (accessibility floor).
- **`engagement-pm` / `onboarding-pm` / `platforms-pm` / `monetization-pm`:** §13 rows.
- **Operator (via `head-product`):** D-2's "What to Test" line (`gp.testflight.what_to_test`,
  R-F1), with Run A;
  App Store Connect configuration needs the operator's own word.
- **`release-lead`:** the doc drift listed in [loop-audit.md](loop-audit.md#contradictions-found-in-re-verification).
  On 11-18, confirm `IOS_INSTALL_URL`'s host is `apps.apple.com` as part of the flip (U4,
  §12; scope §5).

---

## 17. Docs

Row-by-row in [scope.md §4](scope.md#4-docs-scope-mandatory--hld--lld--api).
