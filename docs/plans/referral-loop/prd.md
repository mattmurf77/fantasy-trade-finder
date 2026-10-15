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
> them; still proposed, D-5).
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

Words in quotes are `marketing-lead`'s **proposed** strings ([marketing-inputs.md §A](marketing-inputs.md#a-copy-table-mkt-writer), keys named), pending
operator approval of words via `marketing-lead`. None is final.

### J1 — Inviter

1. Taps Invite on League Home, the members overlay, Matches mutual-empty, the bell's empty
   state, the Trades cold-start banner, or the web invite modal.
2. The button shows a pending state for up to 2 s while the app mints an invite id (FR-1).
   If minting fails, the share proceeds with a league-only link (FR-1, FR-2).
3. The share sheet opens with "Join me on Fleeced to find trades we both like → {url}"
   (`gp.invite.msg`) and a link carrying `t=<invite_id>` and no username.
4. When a leaguemate joins: one bell row, "@{new_username} joined Fleeced via your invite"
   (`gp.push.joined_inbox_title`) with a distinct body line (`gp.push.joined_inbox_body`).
5. When that leaguemate first likes or passes a trade (funnel stage 7, FR-17): a second
   bell row, "@{new_username} weighed in on their first trade" (`gp.inbox.activated_title`)
   with "If they like a trade with you, it can surface in your deck."
   (`gp.inbox.activated_body`). The tap opens Trades (FR-19).

### J2 — Invitee, app not installed

- **iPhone (option A):** taps the link in Messages or a league chat → Safari → join landing:
  "{display name} invited you to {league}" (FR-7's headline ladder), "Get the iOS beta"
  (`gp.join.cta.A_ios`) to the public TestFlight link, "Installs through Apple's TestFlight
  app." (`gp.join.cta.A_ios_help`), and
  the re-tap step "Installed? Go back to the chat and tap the invite again to join
  {leagueName}." (`gp.join.retap`). No `dtf://` "Open in the app" button (§3 non-goal 13).
  - Re-tap after installing → universal link → J3 with the invite id → credited by **token**.
  - No re-tap → the app cold-opens without the link → the user signs in and picks the
    league → credited by **league match** if their landing open was recorded (FR-14).
  - **`IOS_INSTALL_URL` unset:** the honest note only, "The iPhone beta isn't open to the
    public yet. Already have it? Open the invite in the app.", with no button and no
    TestFlight-request link (FR-7).
- **Desktop:** landing → "Open the web app" (`gp.join.cta.A_desktop`) with "Sign-in uses the
  Fleeced extension for Chrome or Edge." (`gp.join.cta.A_desktop_help`) → `/?league=&t=` →
  extension sign-in → invited league auto-selected → credited by token. When
  `IOS_INSTALL_URL` is set, a secondary line offers the iOS link ("On an iPhone or iPad?"),
  because iPadOS Safari presents a desktop user agent; unset, the line is not shown (its
  click-through 404s, §8.2, so it would be a dead path).
- **Android or another phone:** landing → "Fleeced runs on iPhone and desktop web for now."
  (`gp.join.android_note`). **No web button**, because a phone can't sign in on the web. The
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
| **A (chosen 2026-10-15, D-1): device-aware** | iOS → public TestFlight link + re-tap step (no `dtf://` button, §3 non-goal 13); desktop → web app with the extension line, plus a secondary iOS link when `IOS_INSTALL_URL` is set; Android/other phones → an honest note, **never** a web button that can't sign them in | The loop gets an install step now; league-match attribution (FR-14) recovers credit through the install; the re-tap recovers it exactly | TestFlight is a two-app install; 10k external tester cap (**benchmarked**: Apple TestFlight limit, unverified this session); beta framing. **Needs a public TestFlight link**: none exists yet (`NEXT.md:145-148`); the operator creates it (D-3, ruled 2026-10-15) |
| **B: web `/` (status quo, D-173 Companion)** | "Open the web app" on every device | Zero new decisions | **Strands every phone invitee**: the web button can't sign a phone in. Only desktop users with the extension can complete. No install step |
| **C: B until the App Store listing** | B now; the store link later | Clean end state | **Strands every phone invitee with no end date**: launch has no date |

Killed: waitlist / email capture (reverted 2026-08-12 in `65c63479`; no email channel; adds
a step).

**The desktop path rarely completes in practice.** The extension is an unpacked Chrome/Edge
release, not a store listing (`extension/README.md:44`), so few desktop invitees will
sideload it. Option A's working install path is effectively iOS TestFlight (§14). That
strengthens D-1 (A) and D-3 (the public TestFlight link).

**How the choice is applied without code.** The install link is configuration
(`IOS_INSTALL_URL`, §11). Set → option A. Unset → iOS invitees see the honest note instead of
a dead button (B and C as they can work on a phone), and the desktop layout drops its "On an
iPhone or iPad?" line, whose click-through would 404 (§8.2). When the listing ships, set it to
the App Store URL: C's end state, no deploy of code.

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

**FR-2 — Link format: id in, username out.** With the flag on, new links carry `t` and
**never `ref`**: `/app/league/join/<league_id>?t=<invite_id>` when `growth.invite_join_link`
is on, else `/?league=<league_id>&t=<invite_id>`. Mint failure drops `t` and still omits
`ref`. Both clients keep **parsing** legacy `/?league=&ref=` and `/app/league/join/<id>?ref=`
forever (D-028).
- AC-2: the 2×2×2 matrix (ledger flag × join-link flag × id present/absent) produces exactly
  the URLs in §7.2; no flag-on URL contains `ref=`.

**FR-3 — Share text says Fleeced.** Mobile (`InviteLeaguematesBanner.tsx:132`) and web
(`web/js/app.js:5834`) invite messages use `marketing-lead`'s approved string (proposed:
`gp.invite.msg`, the version without the league name, which fits ~140 characters). Ships
with the flag off too (copy is not attribution). This PRD renames only the strings its own
FRs already touch: this invite share text, the inviter rows (FR-18, FR-19) and the join
landing (FR-7). Every other old-name string, including the `league_member_unlocked_trades`
body (`S:10542-10543`), is `head-product`'s P9 copy-defect batch (`onboarding-pm`, after
this wave). Words from `marketing-lead`. Spelling: **"leaguemates"**, one word, in every
proposed string (`marketing-lead`, the voice-spec form). The shipped banner's
"league-mates" (`InviteLeaguematesBanner.tsx:163, :167, :176`) is respelled "leaguemates"
**in this build** (`marketing-lead`'s `h1.banner.title` / `h1.banner.a11y`; spelling only, no
other banner words change): FR-3 and AC-4b already touch that file, and P9 covers only
strings outside the files this PRD touches.
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
`gp.join.*` plus `marketing-lead`'s lab answers
([addendum](marketing-inputs.md#addendum-design-leads-lab-slots-and-growth-pms-four-questions-2026-10-15)),
all proposed, pending the operator's approval of words:
- **Headline:** "{display name} invited you to {league}" (supersedes `gp.join.headline`). Only
  a valid `t` names the inviter (§8.2), so the name is server-verified, never URL-supplied.
  Fallbacks, in order: "{display name} invited you to their league" (league name unknown) →
  "A leaguemate invited you to {league}" (no valid inviter) → "A leaguemate invited you"
  (neither).
- **Value line:** `gp.join.valueprop`, not the lab's "Fleeced finds trades where both sides
  come out ahead." (`web/index.html:75`), which makes Fleeced the subject of an analysis verb
  (the name rule).

With the flag off, the 302 is unchanged.

Design rules (`design-lead` review, accepted by `growth-pm`):
- **Tokens and type.** The page links `web/css/tokens.css` (served as `/css/tokens.css`, the
  single web token source) and loads Barlow Condensed / Archivo / IBM Plex Mono from Google
  Fonts per `docs/design/design-system.md`. None of the `/s/*` `_share_html` chrome
  (`S:25460`); fixing that chrome stays backlog GB-02.
- **One primary action per device state, in ice.**
  - iPhone with `IOS_INSTALL_URL` set: "Get the iOS beta" is the ice primary, then the help
    line and the re-tap step. No second button.
  - Desktop: "Open the web app" is the ice primary; the extension help line in `--chalk-dim`;
    the iOS link ("On an iPhone or iPad?") is a secondary text link, **shown only when
    `IOS_INSTALL_URL` is set** (unset, its click-through 404s, §8.2: a dead path).
  - Android, or iPhone with no `IOS_INSTALL_URL`: no button; the note in `--chalk` or
    `--chalk-dim`, never `--chalk-faint` (it's content).
  - iPhone with no `IOS_INSTALL_URL` (lab frame A2): the honest note only, "The iPhone beta
    isn't open to the public yet. Already have it? Open the invite in the app." (proposed;
    the Android note's "runs on iPhone" would be wrong on an iPhone). "Open the invite in
    the app" means re-tapping the invite link in the chat: it is a universal link and opens
    the installed app. It does not mean a `dtf://` button (§3 non-goal 13); D-14 asks
    `marketing-lead` to confirm the words read as a re-tap. **No "Request
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
  - **The Archivo line** (proposed, `marketing-lead`): "Dynasty Trade Finder" may appear only
    locked up with the FLEECED wordmark, smaller than it, so the two read as D-057's full
    name; never standalone or on a line of its own (DLF has a product with that name). AC-3
    still bans the phrase in invite share text.

- AC-7a: flag off → tests T4–T7 in `test_invite_links.py` pass unmodified.
- AC-7b: flag on → 200 HTML; `og:image` is an absolute `https://` URL; `og:title` carries the
  league name when known; a `noindex` meta is present; no username from the query string is
  echoed into the page.
- AC-7c: one primary action per device state (lab frames A1–A4, §13): iPhone UA → install
  CTA when `IOS_INSTALL_URL` is set; honest note, no button and no TestFlight-request link
  when unset; Android UA → honest note, no button; desktop UA → web-app CTA + extension line,
  plus the secondary iOS text link only when `IOS_INSTALL_URL` is set. No state renders a
  `dtf://` link.
- AC-7d: the brand on the page is "Fleeced" (D-057).
- AC-7e: the page links `/css/tokens.css` and carries none of the `_share_html` chrome; an
  unknown or expired `t` renders no inviter name.

**FR-8 — Record the open server-side.** Every GET of the join path (landing or 302) with a
well-formed `t` and the ledger flag on classifies the user agent:
- human → `opened_at` (first), `last_opened_at`, `open_count + 1` on the share's minted row,
  and server event `invite_landing_opened`;
- link-preview fetcher (iMessage, Slack, Discord, WhatsApp, X, etc.; list in a tested module
  constant) → `unfurled_at` (first) only, no event;
- HEAD → nothing.
Unknown or expired ids still fire `invite_landing_opened` (owner `system:invite`) with
`token_status`.
- AC-8: pytest with a human UA increments `open_count`; with a preview UA it sets only
  `unfurled_at`; HEAD changes nothing.

**FR-9 — Desktop onward link and web capture.** The desktop CTA goes through a recorded
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
returns `inviter_display_name` and `token_status` (§8.3). SignIn's banner
(`SignInScreen.tsx:205-235`) and the LeaguePicker companion state use it when the link has no
`ref`; it is cached in the intent like `leagueName` (one call site, `SignInScreen.tsx:220`).
- AC-11: a token-only link renders "{display name} invited you to {league}" (proposed,
  `marketing-lead`), with FR-7's fallback ladder: "{display name} invited you to their
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
`S:25511`), so it must take a label (and help line or note) per branch instead. Strings, all
**proposed** by `marketing-lead` and pending the operator's approval of words (D-5)
([marketing-inputs.md, lab addendum, "Share landings `/s/*` under FR-25"](marketing-inputs.md#addendum-design-leads-lab-slots-and-growth-pms-four-questions-2026-10-15)):

| Branch | CTA target | Label | Help line or note |
|---|---|---|---|
| iPhone, `IOS_INSTALL_URL` set | `IOS_INSTALL_URL` | "Get the iOS beta" (`gp.join.cta.A_ios`) | "Installs through Apple's TestFlight app." (`gp.join.cta.A_ios_help`). **No re-tap line:** a share page carries no invite, and re-tapping a share link opens the viewer's own tab, not the shared trade (GB-03) |
| iPhone, `IOS_INSTALL_URL` unset | none: a note, no button | — | "The iPhone beta isn't open to the public yet. Already have it? Open Fleeced." It promises the app, not the shared trade: the universal link opens the app (`mobile/src/utils/deepLinks.ts:229-238`), but `MatchesScreen` reads no match id from its route (`MatchesScreen.tsx:190-214`; GB-03) |
| Desktop | `/` (today's target) | Kept per page: "Build your own trade" (`/s/p`, `S:25668`), "Find your next trade" (`/s/trade`, `S:25562`) | **Added:** "Sign-in uses the Fleeced extension for Chrome or Edge." (`gp.join.cta.A_desktop_help`, the join landing's line, §5 J2), so a desktop visitor without the extension isn't stranded |
| Android and other phones | none: a note, **no web button** (a phone can't sign in on the web) | — | "Fleeced runs on iPhone and desktop web for now." (`gp.join.android_note`, reused; it names no invite) |

The iPhone and Android strings and the desktop help line are the same on every `/s/*` route;
only the desktop label stays per page (`/s/tiers` keeps "Build your tiers", `S:25547`). Only
the target, the label, the help line and the button-or-note choice change: `ref`
forwarding, the OG image and absolute `og:image`, `robots.txt`, landing events and the
off-Chalkline chrome stay in GB-02 (§3 non-goal 7). The response varies by device, so it can
no longer be a plain `Cache-Control: public` (today `public, max-age=300`, `S:25518`): it is
either not `public` or it carries `Vary: User-Agent`. Gate: rides `growth.join_landing`
(accepted by `growth-pm` 2026-10-15; `head-eng` still confirms it in allocation), so one
flag covers every device-aware CTA surface; with it off the CTA is today's `/` with today's
label and merge changes nothing user-visible (§12).
- AC-25: pytest on `/s/p` and `/s/trade` (`/s/tiers` 404s while `growth.tier_board_share` is
  off and inherits the change through `_share_html`). Each branch asserts the CTA `href`,
  **its label and its help line or note**, not just the target:
  - gate off, every user agent: `href` `/`, today's label ("Build your own trade" on `/s/p`,
    "Find your next trade" on `/s/trade`), no help line and no note;
  - gate on, iPhone UA, `IOS_INSTALL_URL` set: `href` is `IOS_INSTALL_URL`, label "Get the
    iOS beta", help line "Installs through Apple's TestFlight app.", no re-tap line;
  - gate on, iPhone UA, unset: no CTA link; the note "The iPhone beta isn't open to the
    public yet. Already have it? Open Fleeced.";
  - gate on, desktop UA: `href` `/`, the page's label as above, help line "Sign-in uses the
    Fleeced extension for Chrome or Edge.";
  - gate on, Android UA: no CTA link; the note "Fleeced runs on iPhone and desktop web for
    now.";
  - every case: the response is not `public`-cacheable, or carries `Vary: User-Agent`; the
    `og:*` tags are unchanged; no variant links `dtf://` or a user-supplied URL.

  The test asserts the words the operator approves under D-5; until then, the proposed
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
`analytics_queries.py:415`) within 14 days of `joined_at` (**proposed**). After each server
emitter of those events, one helper checks for a `joined` referral whose
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
- AC-17: a first `trade_proposed` or `match_swiped` inside 14 days stamps once, from each of
  the three emitters; outside 14 days it does nothing; a second opinion is a no-op; a
  `trades_generated` alone never activates, including a replenish deck
  (`deck_source = 'replenish'`).

### H7 · Inviter told

**FR-18 — Join row: correct, once, verified.** The `referral_joined` row fires only from a
ledger attribution (token or league match), with the shipped name and a body that is not a
copy of the title (today `push_notification` sets title = body, `database.py:12620-12634`,
and the bell renders both, `TopBar.tsx:499-501`). Words: `gp.push.joined_inbox_title` /
`_body` (proposed). Route unchanged (League, `deepLinks.ts:306-312`).
- AC-18: the row's title and body differ; no row fires from a legacy `invited_by` alone.

**FR-19 — Activation row.** New notification type `referral_activated` (inbox only; push is
Phase 2), posted to the inviter when FR-17 activates.
- **Routing: the Trades tab (the deck), not League**, because the body points to the deck.
  Register the type in mobile `V2_TRADE_KINDS` (`deepLinks.ts:318`, resolved to
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
  `gp.inbox.activated_title` / `gp.inbox.activated_body`): title "@{new_username} weighed in
  on their first trade"; body "If they like a trade with you, it can surface in your deck."
  - The body rests on likes-you mirroring: a leaguemate's `like` decisions from the last 90
    days are mirrored into the other side's deck (`_inject_likes_you_cards_impl`,
    `S:3951-3972`), capped and quality-gated (`S:3979-3991`), hence "can". Flag
    `trade.likes_you` is on (`config/features.json:37`).
  - The title is `marketing-lead`'s stage-7 revision (2026-10-15): it replaces "…has their
    first trade ideas", which described stage 6. The body is unchanged.
- AC-19: the row routes to Trades, not League; title and body differ; the meta carries
  `new_username` and `league_id`; the glyph check passes.

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
`backend/analytics_taxonomy.py` and classified in `analytics_queries.NON_INTENT_EVENTS` in the
same commit as (or before) its emitter (D-040). **No prop key contains `token`**: ingest drops
any such key silently (`backend/analytics_ingest.py:160, :195`); the id travels as
`invite_id`.

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
events. Holding or merging it is an open item for `engagement-pm` (D-9).

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
  the id's referrer when `token_status = valid`, else none.
- **Both modes:** FR-8 open recording.
- **Click-through, new:** `GET /app/league/join/<league_id>/go/<cta>[?t=<id>|?ref=<u>]` where
  `cta` ∈ `ios | web` (closed set, else 404). `ios` → 302 to `IOS_INSTALL_URL` (404 when
  unset); `web` → 302 to `/?league=<id>` plus `&t=<id>`, or the inbound legacy `&ref=<u>`
  only when there is no `t` (FR-9's closed contract). Records server event
  `invite_landing_cta`. No
  user-supplied URL is ever a redirect target. The landing carries no `dtf://` link in v1
  (§3 non-goal 13), and shows the `ios` click-through only when `IOS_INSTALL_URL` is set
  (FR-7).
- **HEAD:** headers only; nothing recorded.

### 8.3 `GET /api/league/invite-meta` — additive

- New optional query `t`. Response adds `inviter_display_name` (string | null) and
  `token_status` (`valid | expired | unknown | league_mismatch` | null when `t` absent).
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

`analytics-lead` decides final names and classes. Registration and NON_INTENT
classification land with or before each emitter (D-040). Server events are new names (the
client and server namespaces must stay disjoint, `analytics_taxonomy.py:1757-1781`).

**Server-fired, inviter-owned.** `user_id` = the referrer (or `system:invite` when the id
doesn't resolve, following the `system:api` precedent, `analytics_queries.py:60-62`). They
are written through a **non-touching** path: `record_event` today bumps the owner's
`users.last_active_at` and `events_count` (`database.py:4436-4458`), which would make a
dormant inviter look active to the cron ticks (`database.py:14226-14243`). The proposal is
two optional `record_event` parameters, `platform='server'` (it has none today) and
`touch_user=False` (defaults keep today's behaviour). `head-eng` decides the mechanism.

| Event | New / changed | Props | Fires when | Class (proposed) |
|---|---|---|---|---|
| `invite_landing_opened` | new, server | `invite_id`?, `league_id`, `token_status`, `device_class` (`ios\|android\|desktop\|other`) | Human GET of the join path (FR-8) | NON_INTENT |
| `invite_landing_cta` | new, server | `invite_id`?, `league_id`, `cta` (`ios_install\|web_app`), `device_class` | Click-through (§8.2) | NON_INTENT |
| `referral_attributed` | new, server | `invite_id`, `referral_id`, `league_id`, `attribution_method`, `referred_user_id`, `league_platform`, `notified` | §7.4 / §7.5 credit | NON_INTENT |
| `referral_activated` | new, server | `invite_id`, `referral_id`, `league_id`, `days_to_activate`, `notified` | FR-17: the invitee's first `trade_proposed` or `match_swiped` (stage 7) within 14 days of `joined_at`; never `trades_generated` | NON_INTENT |
| `signup` | changed, server (owner: the new user) | + `attribution`, `attribution_miss` (FR-16); first-touch props once §8.4's accepted change is built | First session | unchanged |

`notified` stands in for a separate notification-created event (none exists today); if
`analytics-lead` prefers a `notif_created{type}` event, it replaces the prop.

**Notification meta (not event props).** The `referral_activated` bell row's meta carries
`new_user_id`, `new_username` and `league_id` (FR-19), as `referral_joined`'s meta carries
`new_user_id` and `new_username` today (`S:22663-22667`). The no-username rule below covers
event props only; the meta stays in the inviter's own inbox row.

**Client-fired.**

| Event | Change | Props added | Emitters | Class |
|---|---|---|---|---|
| `invite_shared` | changed | `invite_id`?, `mint_outcome`; `channel` per [marketing-inputs.md §C](marketing-inputs.md#c-utm--install-source-convention-mkt-seo) (granted, analytics-lead, 2026-10-15) | mobile `InviteLeaguematesBanner.tsx:135`; **web, new** | INTENT (unchanged) |
| `invite_cta_tapped` | new web emitter | — (`surface: 'web_invite'`) | mobile; **web, new** | INTENT (unchanged) |
| `invite_cta_shown` | new emitters | — | + Trades banner, members overlay, web modal | NON_INTENT (unchanged) |
| `invite_link_opened` | changed | `invite_id`?; `format` gains `web` | `deepLinks.ts:426`, `LeagueJoinScreen.tsx:77`; **web, new** (`captureReferralFromUrl`) | INTENT (unchanged) |
| `invite_league_pinned` | changed | `invite_id`?; `source` gains `web_autoselect` | `LeaguePickerScreen.tsx:245`; **web, new** | unchanged |
| `invite_pin_failed` | changed | `invite_id`? | `LeaguePickerScreen.tsx:273`; **web, new** | unchanged |

The `surface` prop domain gains `web_invite`. No username, display name or league name in any
prop; `has_ref` stays as it is. The readout joins events to the ledger on
`invite_id` = `share_token`.

**`analytics-lead`'s answers** (analytics-lead, 2026-10-15; its wave-2 report, §"Ask 5" and
§"Ask 3"):
- **P18 UTM convention: accepted** as [marketing-inputs.md §C](marketing-inputs.md#c-utm--install-source-convention-mkt-seo)
  wrote it: four params matching `^[a-z0-9_]{1,40}$`; `ref` = who sent it, UTMs = the surface
  or channel; no usernames, emails or league ids in UTMs; existing `surface` values are
  bridged, never renamed. `analytics-lead` writes the final convention as a tracking-plan
  addendum before any emitter.
- **`share_link_opened`: granted as INTENT**, the twin of `invite_link_opened` (already
  INTENT), not the NON_INTENT `marketing-lead` proposed. It is GB-02/GB-03 work, not Phase 1.
- **Ingest value check: a coercion, not a drop.** A non-matching `utm_*` or `channel` value
  becomes `other` and a counter records it; the event is kept, so ingest's accounting
  invariant is unchanged. This is an `analytics_ingest.py` change (`head-eng`
  infrastructure, under `analytics-lead`'s review) with a sabotage test.
- **`session_init.first_touch` is an API contract change** under full gates
  (`docs/api-reference.md`), never express (§8.4, D-11).
- **Attribution exists only for accounts created after ship. No back-fill.**
- **Prod baselines stay unmeasured until W3**, including the nine invite and share event
  counts and new accounts per week. Every §2.2 value stays **assumed** until then.
- **`signup.attribution` values** (decided by `growth-pm`, 2026-10-15, pending
  `analytics-lead`'s addendum): `token | league_match | legacy_ref | none` (FR-16), plus
  `attribution_miss`. They supersede the `link | none` that `analytics-lead` granted from
  `marketing-lead`'s earlier proposal, which predates the ledger: `link` splits into `token`
  and `legacy_ref`.

**Surface vocabulary** (decided by `growth-pm`, 2026-10-15, pending `analytics-lead`'s final
addendum; [marketing-inputs.md §D](marketing-inputs.md#d-decisions-needed) D5, "vocabulary
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

---

## 11. Flags and config

| Key | Kind | Default | Gates | Graduation | Rollback |
|---|---|---|---|---|---|
| `growth.referral_ledger` | **new flag** | false | Mint route (404 off); clients' use of the id (off ⇒ byte-identical links); open recording; §7.4–§7.8 attribution, activation and notification rules; impact v2 | Phase 0 done + 2 weeks with the §2.1 instrumentation target met | Flip off: mint 404s, clients emit today's links, attribution stops; rows stay |
| `growth.join_landing` | **new flag (proposed here; `growth-pm` to accept, D-7)** | false | Landing page vs today's 302 on `/app/league/join/<id>`; also the `/s/*` device-aware CTA target (FR-25; accepted by `growth-pm` 2026-10-15, `head-eng` confirms in allocation) | Words approved (`marketing-lead`), `design-lead` `/design-review` verdict (§13), operator device pass on iPhone / desktop / Android | Flip off: today's 302, T4–T7 contract |
| `growth.invite_join_link` | existing (`config/features.json:190`) | false | Emitter form only (unchanged meaning) | **Flip in Phase 1** after the #239 device checklist passes (`docs/feedback/items/239-invite-universal-links/status.md` § Operator actions 4; procedure `config-reference.md:669`) | Flip off (legacy form parsed forever) |
| `growth.referral` | existing, **reserved** | false | Nothing in v1. Its declared meaning includes reward granting (`backend/feature_flags.py:268`) | Phase 3, gated on the operator approving the pricing memo (P20) | — |
| `invite.k_factor_dashboard` | existing (`config/features.json:20`) | false | Impact payload v2 (FR-21). Key name kept to avoid churn; meaning updated in `config-reference.md` | Phase 2 surface | Flip off |
| `IOS_INSTALL_URL` | **new env var** | unset | The landing's iOS install CTA and the desktop "On an iPhone or iPad?" line (§5); the `/s/*` iPhone CTA (FR-25). Unset ⇒ honest note on iPhone; no iOS line on desktop | Operator sets it to the public TestFlight link they create (D-3, 2026-10-15); later the App Store URL. An environment value only: no link value is ever written in the repo | Unset it |

New flags are registered in `backend/feature_flags.py` `FLAG_KEYS`, `config/features.json` and
`backend/tests/fixtures/flags/release.json` together (an unknown JSON key fails the guard).

---

## 12. Phasing and rollout

- **Phase 0 (operator, no build):** run the #239 universal-link device checklist (D-2; the
  `app-manager` lead turns it into a device-ready version); create the public TestFlight link
  (D-3; CTA option A is decided, D-1, 2026-10-15); approve words via `marketing-lead`. (The
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
| 5 | Set `IOS_INSTALL_URL` (option A, D-1; the operator's link, D-3); flip `growth.join_landing` (the join landing and the `/s/*` CTA target, FR-25) | Words approved; `design-lead` `/design-review` verdict (`design-review.md`); operator landing pass |
| 6 | Flip `growth.invite_join_link` | Only if step 3 passed; otherwise stay on the legacy form, which still carries `t` |
| 7 | Two-week read | §2.1 target → graduate `growth.referral_ledger` |

---

## 13. Seams and reviews

| Seam | What they decide or review | Route |
|---|---|---|
| `marketing-lead` | All strings: invite text, join landing (`gp.join.*`), inbox rows (`gp.push.*`), activation row; UTM values | W4 direct (operator-approved 2026-10-15) |
| `design-lead` | Join landing (Chalkline, FR-7; per-surface states: logged-out, not installed, expired/unknown link, flag off; iPhone/desktop/Android; no "already joined" state: the landing has no auth and one link can credit several joiners, so that state lives in the in-app J4 path), its OG card (FR-7: static 1200×630; art direction P14), the invite card/banner diff (FR-3/FR-4: copy and events, FR-1's busy state, AC-4b's Invite button floors), Phase 2 "Your invites" tiles. **Mockup lab:** draft PR [#343](https://github.com/mattmurf77/fantasy-trade-finder/pull/343), `mockups/referral-loop/index.html` @ `899f8619` (branch `mockup/referral-loop`): landing frames **A1** iPhone with `IOS_INSTALL_URL`, **A2** iPhone without, **A3** desktop, **A4** Android, **A5** expired/unknown invite, **A6** unknown league name (plus option B drawn as not recommended); OG variants (i) wordmark only, (ii) wordmark + ram (**v1**, FR-7), (iii) league name (Phase 2); banner and card before/after, including FR-1's busy state; Phase 2 "Your invites" tiles. The "Open in the app" button drawn on A1, A2, A5 and A6 is out of v1 (§3 non-goal 13). Before-panes: the web ones (W1–W3, and the `og_image.py` card) are local renders of `origin/main` `678834a` (`head-product` P22); the mobile ones (banner, card, share text) are labelled reconstructions from source. Every string stays with `marketing-lead`; the lab tags each PROPOSED COPY and each `[copy: marketing-lead]` slot (D-14). The build gets a `/design-review` verdict at `docs/plans/referral-loop/design-review.md` before ship. F1 (outside this PRD) is in §16 | W4 direct |
| `ux-lead` | The J2 flows, especially re-tap after a TestFlight install | via `head-product` |
| `analytics-lead` | Event names and classes (§10), taxonomy + NON_INTENT in the emitter's commit, the activation stage (D-8), the readout (FR-22), the first-touch convention (P18), the W3 baseline | via `head-product` |
| `engagement-pm` | In-app entry points; the notify-once rule (FR-20); the activation row as a receipt (D-046) and its routing to Trades, not League (FR-19); the join/activation timing open item (§7.8); Phase 2 pushes | via `head-product` |
| `onboarding-pm` | LeagueJoin, SignIn banner from `invite-meta`, web landing capture (its invite-context emphasis in flare or chalk, never `--pos` green: FR-9, AC-9b), LeaguePicker companion | via `head-product` |
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
| iOS invitee doesn't come back to re-tap after TestFlight | High / medium | League-match fallback; re-tap words on the landing; the cheapest test in GB-01 measures the gap |
| Mint latency or a cold backend delays the share sheet | Medium / medium | 2 s deadline, fallback link, `mint_outcome` measured |
| Inviter rows bump `last_active_at` and suppress winback | High if unmitigated / medium | Non-touching write (§10) |
| `invite_id` dropped at ingest | Certain if named `*token*` / high | FR-24 naming rule, structural check |
| iPadOS presents a desktop UA | Medium / low | Secondary iOS link on the desktop layout (only while `IOS_INSTALL_URL` is set) |
| ESPN/MFL membership can't be verified before the invitee links that platform | Medium / medium | Credit happens at the first session in that league; `platforms-pm` review |
| Imported league names exposed by a token-gated lookup | Low / medium | D-10 default is no; Sleeper public names only |
| Group-chat posting reads as spam to a league | Low / high (Sleeper relations) | League scope; 10/day cap; no automated posting; `platforms-pm` |
| Legacy links already in chats lose credit when the flag flips | Certain / low | Accepted (amendment: credit only from verified ids or league match); `legacy_ref` stays visible in `signup` props |
| TestFlight two-step and 10k tester cap | Medium / medium | Option C end state is one env value away |
| The desktop path rarely completes: the extension is an unpacked Chrome/Edge release, not a store listing (`extension/README.md:44`), so few desktop invitees will sideload it (`marketing-lead`, lab addendum) | High / medium | Option A's working install path is effectively iOS TestFlight; this strengthens D-1 (A) and D-3 (the public TestFlight link). The desktop CTA stays, with its accurate extension line (`gp.join.cta.A_desktop_help`) |

---

## 15. Decisions needed

| # | Decision | Who | Recommendation |
|---|---|---|---|
| D-1 | CTA target A/B/C before the listing (§5) | **Resolved by the operator 2026-10-15: A** ("Ok. start building D1 and D3", verbatim via `head-product`) | Option A, device-aware: iOS → `IOS_INSTALL_URL` (the public TestFlight link); desktop → the web app with the extension line; Android and other phones → the honest note (§5, FR-7, FR-25) |
| D-2 | Run the #239 device checklist | **operator**. **Open.** The new `app-manager` lead turns the checklist into the operator's device-ready version | Before rollout step 6 |
| D-3 | Create a public TestFlight link | **Resolved by the operator 2026-10-15** (same quote): the operator creates it | The link becomes the `IOS_INSTALL_URL` value (§11); no link value is ever written in the repo |
| D-4 | Rewards | **Resolved by `head-product` P20 (2026-10-15): reward-free v1** | Status and recognition only in v1. Rewards are Phase 3, gated on the operator approving `monetization-pm`'s pricing memo; `monetization-pm` designs the economics, `growth-pm` defines "activated" and the mechanics (§12) |
| D-5 | Approve the words (`gp.*`) | **operator** via `marketing-lead` | — |
| D-6 | Accept the PRD; **supersede D-028 part 2** (a real join page instead of the 302 into `/`), because D-028's premise that the existing web funnel converts holds only on desktop with the extension | `head-product` (new DECISIONS entry, id claimed against `origin/main`) | Yes |
| D-7 | Second flag `growth.join_landing` | `head-product` / `growth-pm` | Yes: independent rollback for the riskiest surface |
| D-8 | Activation = stage 7 first opinion (vs 5 or 6) | `analytics-lead` | Stage 7: the first `trade_proposed` or `match_swiped` within 14 days of `joined_at` (FR-17) |
| D-9 | Notify-once rule (FR-20); the activation row routes to Trades, not League (FR-19). Open item: an activation row within 10 minutes of the join row posts separately today; hold or merge it? (§7.8) | `engagement-pm` | As written |
| D-10 | A valid id unlocks the stored league name for imported (ESPN/MFL) leagues on the landing and `invite-meta` | `head-eng` (security) | No in v1; revisit with evidence |
| D-11 | First-touch UTMs on `session_init` (§8.4) | **Accepted by `analytics-lead` (P18; analytics-lead, 2026-10-15)** | The [marketing-inputs.md §C](marketing-inputs.md#c-utm--install-source-convention-mkt-seo) convention is accepted; `analytics-lead` writes the final addendum before any emitter. Conditions: `first_touch` is an API contract change under full gates (`docs/api-reference.md`); a non-matching value is coerced to `other` with a counter, not dropped; attribution only for accounts created after ship, no back-fill. Outside Phase 1's critical path |
| D-12 | Mint cap 10 per inviter per league per day; token credit window 30 days | `growth-pm` | As written (assumed values) |
| D-13 | `record_event` `platform` + `touch_user` parameters vs a separate writer | `head-eng` | Either; the requirement is no denorm bump |
| D-14 | Copy questions from `design-lead`'s lab (§13). **Answered by `marketing-lead` 2026-10-15, all proposed** ([lab addendum](marketing-inputs.md#addendum-design-leads-lab-slots-and-growth-pms-four-questions-2026-10-15)): (a) every `[copy: marketing-lead]` slot is filled (the A2 note and A5's "A leaguemate invited you to {league}", FR-7; `og:title` = `gp.join.og_title`; the Phase 2 tiles' labels, "Activated" explainer, empty-state prompt and zero-join line, in the addendum); (b) FR-11's "{display name} invited you to {league}" **is** the landing headline, superseding `gp.join.headline`, with FR-7's fallback ladder; (c) "Dynasty Trade Finder" may appear on the OG card only locked up with the wordmark, smaller, never standalone (FR-7; the D-057 name is "Fleeced: Dynasty Trade Finder"); (d) **"leaguemates"**, one word (FR-3; the banner's "league-mates", `InviteLeaguematesBanner.tsx:163, :167, :176`, is respelled in this build). **Follow-up, open:** `marketing-lead` confirms the A2 note's "Open the invite in the app" reads as a re-tap of the invite link (a universal link that opens the installed app), not as a button (FR-7) | `marketing-lead`; the operator approves the words with D-5 | Approve with D-5, before rollout step 5 (the landing and OG card ship no words without them) |
| D-15 | The OG card wordmark's period. `marketing-lead` had asked for no period on the OG card, because next to a trade "FLEECED." reads as a verdict ("you got fleeced"); `head-product` proposed that the logotype keeps the period and running copy never uses it (FR-7) | **Resolved by `design-lead` 2026-10-15** (owns the wordmark, P14) | The OG card carries the logotype "FLEECED." with the ice period, Barlow Condensed Bold caps, chalk. Rule (`docs/design/brand.md`, PR [#349](https://github.com/mattmurf77/fantasy-trade-finder/pull/349)): the ice period belongs to the logotype; it goes wherever the logo appears and nowhere else (not verdict cards, headings, badges or buttons). Matches `head-product`'s proposed rule. PR #349 also sanctions the invite OG link card as a ram placement (variant (ii)) |

---

## 16. Handoffs

- **`head-product`:** accept the PRD (D-6); route D-6…D-13. The first build slice is already
  with `head-eng` (§12, 2026-10-15).
- **`head-eng`:** build the first slice first (§12: FR-7, FR-8, FR-9, FR-25, §8.2,
  `IOS_INSTALL_URL`); allocate files (builder TBD; likely `engagement-eng` backend + invite
  routes, `onboarding-eng` web/LeagueJoin/SignIn); confirm FR-25's gate
  (`growth.join_landing`, accepted by `growth-pm`); security handoff on `/s/trade` enumeration
  (`S:25552-25564`, `S:25446-25457`).
- **`analytics-lead`:** §10 proposals (P18 and the baseline asks answered 2026-10-15, §10),
  D-8, FR-22 readout, the tracking-plan addendum (final UTM convention, the surface
  vocabulary and the `signup.attribution` values in §10), W3 baseline (nine invite/share events, new
  accounts per week, open → signup feasibility).
- **`marketing-lead`:** final words for every quoted string, including the activation row
  (revised to stage 7, FR-19); its S-IDs remap to the backlog's S1–S12. The lab's copy
  questions (D-14) are answered (proposed, pending the operator); the OG wordmark period is
  resolved (D-15, `design-lead`: the period is logo-only). The `/s/*` CTA labels, help lines
  and notes for FR-25 are proposed (lab addendum, "Share landings `/s/*` under FR-25"),
  including a share landing's own iPhone-unset note; the operator approves them with D-5.
- **FAQ claim → P9's copy-defect batch (`onboarding-pm`) via `head-product`:**
  `web/faq.html:206` says the web app "works in any phone browser", which is false: web
  sign-in needs the desktop extension (§5). The lab's landing footer links to the FAQ.
- **Old-name strings: overlap resolved by P9.** `head-product` put old-name copy defects in
  P9's copy-defect batch (`onboarding-pm`, after this wave). This PRD renames only the strings
  its FRs touch (FR-3); the rest, including `league_member_unlocked_trades`
  (`S:10542-10543`), go to that batch. So does any old-name or name-rule string outside the
  files this PRD touches, e.g. `web/index.html:75` ("Fleeced finds trades…", Fleeced as the
  subject of an analysis verb), via `head-product`.
- **`design-lead`:** landing + OG card + states (§13; lab PR #343 folded); the `/design-review`
  verdict covers AC-4b's banner floors. D-15 (the OG wordmark's period) is resolved by
  `design-lead`, 2026-10-15 (`brand.md`, PR #349).
- **`design-lead` → `head-eng` via `head-product` (outside this PRD): F1.** On phones the
  shipped web landing hides the `WR` label but keeps the WR-blue rail
  (`web/css/styles.css:5111`), so position colour is the only encoding (accessibility floor).
- **`engagement-pm` / `onboarding-pm` / `platforms-pm` / `monetization-pm`:** §13 rows.
- **`release-lead`:** the doc drift listed in [loop-audit.md](loop-audit.md#contradictions-found-in-re-verification).

---

## 17. Docs

Row-by-row in [scope.md §4](scope.md#4-docs-scope-mandatory--hld--lld--api).
