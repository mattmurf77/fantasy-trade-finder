# PRD — Referral loop v1: credited, measured league invites

> Requirements for making the league invite loop work end to end: an existing user's
> invite reaches a leaguemate, the leaguemate becomes an activated Fleeced user, the
> inviter is credited and told, and every hop is measured per inviter.
> **Status:** PRD drafted 2026-10-15; revised 2026-10-15 to fold `head-product` rulings P20
> (reward-free v1), P9 (old-name strings outside this PRD's own FRs go to P9's copy-defect
> batch) and P21 (the `docs/plans/README.md` row is approved); nothing else changes. Awaiting
> acceptance (`head-product`). Requirements only: **no source file is changed by this
> document.**
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
7. **`/s/*` share landings.** Their CTA, `ref` forwarding, OG and robots fixes are GB-02; CTA A
   on them is Phase 2.
8. **`/s/trade` enumeration.** A security handoff to `head-eng`, not this build.
9. **Retiring legacy URL parsing.** D-028: `/?league=&ref=` is parsed forever. New links stop
   *emitting* `ref` (FR-2); nothing stops *reading* it.
10. **APNs referral push** and the inviter-facing **"Your invites" surface.** Phase 2.
11. **An Android app.** Android invitees get an honest note (§5).
12. **Copy A/B.** §2.4.

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
   bell row, "@{new_username} has their first trade ideas" (`gp.inbox.activated_title`)
   with "If they like a trade with you, it can surface in your deck."
   (`gp.inbox.activated_body`). The tap opens Trades (FR-19).

### J2 — Invitee, app not installed

- **iPhone (option A):** taps the link in Messages or a league chat → Safari → join landing:
  league name, inviter's display name, "Get the iOS beta" (`gp.join.cta.A_ios`) to the public
  TestFlight link, "Installs through Apple's TestFlight app." (`gp.join.cta.A_ios_help`), and
  the re-tap step "Installed? Go back to the chat and tap the invite again to join
  {leagueName}." (`gp.join.retap`), plus an optional "Open in the app" button using the `dtf://`
  scheme (`mobile/app.json:8`).
  - Re-tap after installing → universal link → J3 with the invite id → credited by **token**.
  - No re-tap → the app cold-opens without the link → the user signs in and picks the
    league → credited by **league match** if their landing open was recorded (FR-14).
- **Desktop:** landing → "Open the web app" (`gp.join.cta.A_desktop`) with "Sign-in uses the
  Fleeced extension for Chrome or Edge." (`gp.join.cta.A_desktop_help`) → `/?league=&t=` →
  extension sign-in → invited league auto-selected → credited by token. A secondary line
  offers the iOS link ("On an iPhone or iPad?"), because iPadOS Safari presents a desktop
  user agent.
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

Audit decision 4. The finding that frames it ([marketing-inputs.md §0.2](marketing-inputs.md#02-cta-target-lead-recommendation), re-verified): **web
sign-in requires the desktop Fleeced extension** (`web/js/browser-auth.js:1`, fails
`extension_unavailable` after 2 s at `:45`; called unconditionally at `web/js/app.js:334`), and
ESPN/MFL browser sign-in is "not available … yet" (`app.js:1262-1266`). On a phone, web `/`
dead-ends every invitee on every platform.

| Option | What the landing does | Pros | Cons |
|---|---|---|---|
| **A (recommended): device-aware** | iOS → public TestFlight link + re-tap step (+ optional `dtf://` button); desktop → web app with the extension line, plus a secondary iOS link; Android/other phones → an honest note, **never** a web button that can't sign them in | The loop gets an install step now; league-match attribution (FR-14) recovers credit through the install; the re-tap recovers it exactly | TestFlight is a two-app install; 10k external tester cap (**benchmarked**: Apple TestFlight limit, unverified this session); beta framing. **Needs the operator to create a public TestFlight link** (none exists: `NEXT.md:145-148`) |
| **B: web `/` (status quo, D-173 Companion)** | "Open the web app" on every device | Zero new decisions | **Strands every phone invitee**: the web button can't sign a phone in. Only desktop users with the extension can complete. No install step |
| **C: B until the App Store listing** | B now; the store link later | Clean end state | **Strands every phone invitee with no end date**: launch has no date |

Killed: waitlist / email capture (reverted 2026-08-12 in `65c63479`; no email channel; adds
a step).

**How the choice is applied without code.** The install link is configuration
(`IOS_INSTALL_URL`, §11). Set → option A. Unset → iOS invitees see the honest note instead of
a dead button (B and C as they can work on a phone). When the listing ships, set it to the
App Store URL: C's end state, no deploy of code.

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
this wave). Words from `marketing-lead`.
- AC-3: no invite share text contains "Dynasty Trade Finder" or "Fantasy Trade Finder"
  (structural guard).

**FR-4 — Even impressions.** `invite_cta_shown` fires on the Trades cold-start banner and the
members-overlay footer (H1b, H1e). The banner passes the league's real `platform` and real
`not_joined` / `total_mates` where `/api/league/summary` has them (null stays honest when it
doesn't; `InviteLeaguematesBanner.tsx:146-153`).
- AC-4: every invite surface fires `invite_cta_shown` once per mount; the banner no longer
  hard-codes `platform: 'unknown'` when the league platform is known.

FR-3 and FR-4 are copy and events only: **no visual change** to the invite card or banner.
`design-lead` still reviews the diff (§13).

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
display name (resolved server-side from `t`), absolute OG tags, the device-aware CTA from §5,
the re-tap step, and an optional `dtf://app/league/join/<id>?t=<id>` button. Chalkline
styling per `docs/design/design-system.md` (rules below); it does **not** reuse the `/s/*` chrome, which is
off-Chalkline (999px pill, system/Roboto stack, 16px radius with shadow:
`S:25493-25501`; [marketing-inputs.md §0.3](marketing-inputs.md#03-loop-defects-found-for-the-prds-fix-list) defect 11). `<meta name="robots" content="noindex">`; the path
is **not** added to `robots.txt` (unfurlers that honour robots must still fetch it). Words:
`gp.join.*` (proposed). With the flag off, the 302 is unchanged.

Design rules (`design-lead` review, accepted by `growth-pm`):
- **Tokens and type.** The page links `web/css/tokens.css` (served as `/css/tokens.css`, the
  single web token source) and loads Barlow Condensed / Archivo / IBM Plex Mono from Google
  Fonts per `docs/design/design-system.md`. None of the `/s/*` `_share_html` chrome
  (`S:25460`); fixing that chrome stays backlog GB-02.
- **One primary action per device state, in ice.**
  - iPhone with `IOS_INSTALL_URL` set: "Get the iOS beta" is the ice primary; "Open in the
    app" (`dtf://`) is a secondary outlined button with the `--line-strong` border.
  - Desktop: "Open the web app" is the ice primary; the extension help line in `--chalk-dim`;
    the iOS link is a secondary text link.
  - Android, or iPhone with no `IOS_INSTALL_URL`: no button; the note in `--chalk` or
    `--chalk-dim`, never `--chalk-faint` (it's content).
- **Expired or unknown link:** drop the inviter name; neutral headline; **not** `--neg` red (an
  expired invite isn't an error to the user).
- **No "already joined" state:** the landing has no auth and one link can credit several
  joiners (§7.6), so it can't know; that state lives in the in-app J4 path.
- **Floors:** 44pt hit targets, the ice focus ring, `prefers-reduced-motion` respected, dark
  only.
- **OG card (v1, static 1200×630).** `--ink-0` field, the FLEECED wordmark in Barlow Condensed
  caps with the ice tick, one Archivo line; no gradients, no glow; text ≥48px at 1200 wide so
  it reads at iMessage thumbnail size (~300px). Art direction is `design-lead`'s (P14). The
  with-ram vs without-ram variant is chosen from `design-lead`'s mockup lab (branch
  `mockup/referral-loop`) by `growth-pm` or the operator; the ram (app icon) appears only
  inside its own box.

- AC-7a: flag off → tests T4–T7 in `test_invite_links.py` pass unmodified.
- AC-7b: flag on → 200 HTML; `og:image` is an absolute `https://` URL; `og:title` carries the
  league name when known; a `noindex` meta is present; no username from the query string is
  echoed into the page.
- AC-7c: one primary action per device state: iPhone UA → install CTA (+ `dtf://` secondary)
  when `IOS_INSTALL_URL` is set, honest note and no button when unset; Android UA → honest
  note, no button; desktop UA → web-app CTA + extension line + secondary iOS text link.
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
`invite_league_pinned{source:'web_autoselect'}`.
- AC-9: a desktop landing → web sign-in → auto-select run produces `invite_link_opened{format:'web'}`,
  `invite_league_pinned{web_autoselect}`, and a session init carrying `invite_id`.

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
- AC-11: a token-only link renders "{display name} invited you to {league}" (words per
  `marketing-lead`); an unknown id degrades to "A leaguemate invited you".

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
separate proposal owned by `analytics-lead` (P18), built only if accepted (§8.4).
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
  `gp.inbox.activated_title` / `gp.inbox.activated_body`): title "@{new_username} has their
  first trade ideas"; body "If they like a trade with you, it can surface in your deck."
  - The body rests on likes-you mirroring: a leaguemate's `like` decisions from the last 90
    days are mirrored into the other side's deck (`_inject_likes_you_cards_impl`,
    `S:3951-3972`), capped and quality-gated (`S:3979-3991`), hence "can". Flag
    `trade.likes_you` is on (`config/features.json:37`).
  - `marketing-lead` re-checks the title against the stage-7 definition (it was drafted for
    stage 6, "first suggestions").
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
  user-supplied URL is ever a redirect target. The `dtf://` button is a direct link and is
  not recorded.
- **HEAD:** headers only; nothing recorded.

### 8.3 `GET /api/league/invite-meta` — additive

- New optional query `t`. Response adds `inviter_display_name` (string | null) and
  `token_status` (`valid | expired | unknown | league_mismatch` | null when `t` absent).
  `league_name` rules unchanged unless D-10. Still public, read-only, degrade-never-fail
  (`S:26445-26482`).

### 8.4 `POST /api/session/init` — additive

- New optional body field `invite_id` (string, same pattern as §8.2 `t`). Ignored when the
  ledger flag is off or the user is not new. Response unchanged. `invited_by` still accepted.
- **Proposed, not Phase 1 critical path:** optional `first_touch:
  {utm_source, utm_medium, utm_campaign, utm_content}` attached to `signup` props, per
  [marketing-inputs.md §C](marketing-inputs.md#c-utm--install-source-convention-mkt-seo) ("Composition and capture", "Proposal for analytics-lead"). Proposed by
  `marketing-lead`, pending `analytics-lead` (P18), who owns the final convention and the value
  validation.

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
| `signup` | changed, server (owner: the new user) | + `attribution`, `attribution_miss` (FR-16); first-touch props only if §8.4's proposal is accepted | First session | unchanged |

`notified` stands in for a separate notification-created event (none exists today); if
`analytics-lead` prefers a `notif_created{type}` event, it replaces the prop.

**Notification meta (not event props).** The `referral_activated` bell row's meta carries
`new_user_id`, `new_username` and `league_id` (FR-19), as `referral_joined`'s meta carries
`new_user_id` and `new_username` today (`S:22663-22667`). The no-username rule below covers
event props only; the meta stays in the inviter's own inbox row.

**Client-fired.**

| Event | Change | Props added | Emitters | Class |
|---|---|---|---|---|
| `invite_shared` | changed | `invite_id`?, `mint_outcome`; `channel` per [marketing-inputs.md §C](marketing-inputs.md#c-utm--install-source-convention-mkt-seo) (proposed, pending) | mobile `InviteLeaguematesBanner.tsx:135`; **web, new** | INTENT (unchanged) |
| `invite_cta_tapped` | new web emitter | — (`surface: 'web_invite'`) | mobile; **web, new** | INTENT (unchanged) |
| `invite_cta_shown` | new emitters | — | + Trades banner, members overlay, web modal | NON_INTENT (unchanged) |
| `invite_link_opened` | changed | `invite_id`?; `format` gains `web` | `deepLinks.ts:426`, `LeagueJoinScreen.tsx:77`; **web, new** (`captureReferralFromUrl`) | INTENT (unchanged) |
| `invite_league_pinned` | changed | `invite_id`?; `source` gains `web_autoselect` | `LeaguePickerScreen.tsx:245`; **web, new** | unchanged |
| `invite_pin_failed` | changed | `invite_id`? | `LeaguePickerScreen.tsx:273`; **web, new** | unchanged |

The `surface` prop domain gains `web_invite`. No username, display name or league name in any
prop; `has_ref` stays as it is. The readout joins events to the ledger on
`invite_id` = `share_token`.

---

## 11. Flags and config

| Key | Kind | Default | Gates | Graduation | Rollback |
|---|---|---|---|---|---|
| `growth.referral_ledger` | **new flag** | false | Mint route (404 off); clients' use of the id (off ⇒ byte-identical links); open recording; §7.4–§7.8 attribution, activation and notification rules; impact v2 | Phase 0 done + 2 weeks with the §2.1 instrumentation target met | Flip off: mint 404s, clients emit today's links, attribution stops; rows stay |
| `growth.join_landing` | **new flag (proposed here; `growth-pm` to accept, D-7)** | false | Landing page vs today's 302 on `/app/league/join/<id>` | Words approved (`marketing-lead`), `design-lead` `/design-review` verdict (§13), operator device pass on iPhone / desktop / Android | Flip off: today's 302, T4–T7 contract |
| `growth.invite_join_link` | existing (`config/features.json:190`) | false | Emitter form only (unchanged meaning) | **Flip in Phase 1** after the #239 device checklist passes (`docs/feedback/items/239-invite-universal-links/status.md` § Operator actions 4; procedure `config-reference.md:669`) | Flip off (legacy form parsed forever) |
| `growth.referral` | existing, **reserved** | false | Nothing in v1. Its declared meaning includes reward granting (`backend/feature_flags.py:268`) | Phase 3, gated on the operator approving the pricing memo (P20) | — |
| `invite.k_factor_dashboard` | existing (`config/features.json:20`) | false | Impact payload v2 (FR-21). Key name kept to avoid churn; meaning updated in `config-reference.md` | Phase 2 surface | Flip off |
| `IOS_INSTALL_URL` | **new env var** | unset | The landing's iOS install CTA (§5). Unset ⇒ honest note | Operator sets it (public TestFlight link; later the App Store URL) | Unset it |

New flags are registered in `backend/feature_flags.py` `FLAG_KEYS`, `config/features.json` and
`backend/tests/fixtures/flags/release.json` together (an unknown JSON key fails the guard).

---

## 12. Phasing and rollout

- **Phase 0 (operator, no build):** run the #239 universal-link device checklist; decide CTA
  A/B/C; if A, create the public TestFlight link; approve words via `marketing-lead`. (The
  reward question is closed: reward-free v1, `head-product` P20.)
- **Phase 1 (build, flag-gated):** FR-1…FR-24. Backend lands first with every flag off; clients
  read the flags; nothing user-visible changes at merge except FR-3 (copy) and FR-4
  (impression events).
- **Phase 2:** APNs `referral_joined` / `referral_activated` pushes (GD-5, `NEXT.md:532`;
  `engagement-pm`: caps, prefs, buckets); the inviter's "Your invites" surface on top of
  `/api/invite/impact` (`design-lead`: tiles with live counts in IBM Plex Mono, the operator's
  tile preference; milestone badges, if they return, use Chalkline icons, never emoji);
  option A's CTA on the `/s/*` landings (GB-02).
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
| 5 | Set `IOS_INSTALL_URL` (if A); flip `growth.join_landing` | Words approved; `design-lead` `/design-review` verdict (`design-review.md`); operator landing pass |
| 6 | Flip `growth.invite_join_link` | Only if step 3 passed; otherwise stay on the legacy form, which still carries `t` |
| 7 | Two-week read | §2.1 target → graduate `growth.referral_ledger` |

---

## 13. Seams and reviews

| Seam | What they decide or review | Route |
|---|---|---|
| `marketing-lead` | All strings: invite text, join landing (`gp.join.*`), inbox rows (`gp.push.*`), activation row; UTM values | W4 direct (operator-approved 2026-10-15) |
| `design-lead` | Join landing (Chalkline, FR-7; per-surface states: logged-out, not installed, expired/unknown link, flag off; iPhone/desktop/Android; no "already joined" state: the landing has no auth and one link can credit several joiners, so that state lives in the in-app J4 path), its OG card (FR-7: static 1200×630; art direction P14), the invite card/banner diff (FR-3/FR-4: copy and events only, no visual change), Phase 2 "Your invites" tiles. Every string stays with `marketing-lead`; the mockup lab (`mockup/referral-loop`) tags each PROPOSED COPY. The build gets a `/design-review` verdict at `docs/plans/referral-loop/design-review.md` before ship. The landing's before-pane is today's 302 to `/` (the web landing), a labelled reconstruction until `head-product` rules on web before-panes (W2) | W4 direct |
| `ux-lead` | The J2 flows, especially re-tap after a TestFlight install | via `head-product` |
| `analytics-lead` | Event names and classes (§10), taxonomy + NON_INTENT in the emitter's commit, the activation stage (D-8), the readout (FR-22), the first-touch convention (P18), the W3 baseline | via `head-product` |
| `engagement-pm` | In-app entry points; the notify-once rule (FR-20); the activation row as a receipt (D-046) and its routing to Trades, not League (FR-19); the join/activation timing open item (§7.8); Phase 2 pushes | via `head-product` |
| `onboarding-pm` | LeagueJoin, SignIn banner from `invite-meta`, web landing capture, LeaguePicker companion | via `head-product` |
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
| iPadOS presents a desktop UA | Medium / low | Secondary iOS link on the desktop layout |
| ESPN/MFL membership can't be verified before the invitee links that platform | Medium / medium | Credit happens at the first session in that league; `platforms-pm` review |
| Imported league names exposed by a token-gated lookup | Low / medium | D-10 default is no; Sleeper public names only |
| Group-chat posting reads as spam to a league | Low / high (Sleeper relations) | League scope; 10/day cap; no automated posting; `platforms-pm` |
| Legacy links already in chats lose credit when the flag flips | Certain / low | Accepted (amendment: credit only from verified ids or league match); `legacy_ref` stays visible in `signup` props |
| TestFlight two-step and 10k tester cap | Medium / medium | Option C end state is one env value away |

---

## 15. Decisions needed

| # | Decision | Who | Recommendation |
|---|---|---|---|
| D-1 | CTA target A/B/C before the listing (§5) | **operator** | **A** |
| D-2 | Run the #239 device checklist | **operator** | Before rollout step 6 |
| D-3 | Create a public TestFlight link | **operator** (if A) | Yes |
| D-4 | Rewards | **Resolved by `head-product` P20 (2026-10-15): reward-free v1** | Status and recognition only in v1. Rewards are Phase 3, gated on the operator approving `monetization-pm`'s pricing memo; `monetization-pm` designs the economics, `growth-pm` defines "activated" and the mechanics (§12) |
| D-5 | Approve the words (`gp.*`) | **operator** via `marketing-lead` | — |
| D-6 | Accept the PRD; **supersede D-028 part 2** (a real join page instead of the 302 into `/`), because D-028's premise that the existing web funnel converts holds only on desktop with the extension | `head-product` (new DECISIONS entry, id claimed against `origin/main`) | Yes |
| D-7 | Second flag `growth.join_landing` | `head-product` / `growth-pm` | Yes: independent rollback for the riskiest surface |
| D-8 | Activation = stage 7 first opinion (vs 5 or 6) | `analytics-lead` | Stage 7: the first `trade_proposed` or `match_swiped` within 14 days of `joined_at` (FR-17) |
| D-9 | Notify-once rule (FR-20); the activation row routes to Trades, not League (FR-19). Open item: an activation row within 10 minutes of the join row posts separately today; hold or merge it? (§7.8) | `engagement-pm` | As written |
| D-10 | A valid id unlocks the stored league name for imported (ESPN/MFL) leagues on the landing and `invite-meta` | `head-eng` (security) | No in v1; revisit with evidence |
| D-11 | First-touch UTMs on `session_init` (§8.4) | `analytics-lead` (P18) | Accept [marketing-inputs.md §C](marketing-inputs.md#c-utm--install-source-convention-mkt-seo); outside Phase 1's critical path |
| D-12 | Mint cap 10 per inviter per league per day; token credit window 30 days | `growth-pm` | As written (assumed values) |
| D-13 | `record_event` `platform` + `touch_user` parameters vs a separate writer | `head-eng` | Either; the requirement is no denorm bump |

---

## 16. Handoffs

- **`head-product`:** accept the PRD; route D-6…D-13; take it to `head-eng` for allocation.
- **`head-eng`:** allocate files (builder TBD; likely `engagement-eng` backend + invite routes,
  `onboarding-eng` web/LeagueJoin/SignIn); security handoff on `/s/trade` enumeration
  (`S:25552-25564`, `S:25446-25457`).
- **`analytics-lead`:** §10 proposals, D-8, D-11, FR-22 readout, W3 baseline (nine invite/share
  events, new accounts per week, open → signup feasibility).
- **`marketing-lead`:** final words for every quoted string, including the activation row
  (proposed; re-check its title against stage 7, FR-19); its S-IDs remap to the backlog's
  S1–S12.
- **Old-name strings: overlap resolved by P9.** `head-product` put old-name copy defects in
  P9's copy-defect batch (`onboarding-pm`, after this wave). This PRD renames only the strings
  its FRs touch (FR-3); the rest, including `league_member_unlocked_trades`
  (`S:10542-10543`), go to that batch.
- **`design-lead`:** landing + OG card + states (§13).
- **`engagement-pm` / `onboarding-pm` / `platforms-pm` / `monetization-pm`:** §13 rows.
- **`release-lead`:** the doc drift listed in [loop-audit.md](loop-audit.md#contradictions-found-in-re-verification).

---

## 17. Docs

Row-by-row in [scope.md §4](scope.md#4-docs-scope-mandatory--hld--lld--api).
