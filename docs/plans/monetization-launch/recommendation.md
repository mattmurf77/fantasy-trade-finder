# Monetization from day 1: trial mechanism, Founder pricing, the access gate

> **Owner:** `monetization-pm` · **Reviewer:** `head-product` · **Decider:** operator
> **Date:** 2026-10-24 · **Status:** **DECIDED 2026-10-25, build in progress** · **Base:** `origin/main` `3d752296`
> **What this is:** a product spec and decision memo; it builds nothing, flips no flag, and touches neither App Store
> Connect, StoreKit nor EAS. The build's full-gates scope block is [scope.md](scope.md). **Labels:** **[M]** measured ·
> **[B]** benchmarked (URL, accessed 2026-10-24 unless noted) · **[A]** assumed · **[E]** head-eng's estimate ·
> **[interp.]** a reading of Apple's text, not Apple's words.
> **Evidence:** [research/trial-rules-and-offers.md](research/trial-rules-and-offers.md) (Apple rules, guidelines of
> 2026-10-16; benchmarks), [research/repo-facts-trial-gate.md](research/repo-facts-trial-gate.md) (file:line at
> `3d752296`). Org inputs (`org/…`) live in `docs/plans/org-bringup/` on the operator's checkout, not yet on a remote:
> `monetization-day1-feasibility.md`, `reports/onboarding-pm.md`, `reports/ux-lead.md` ("Monetization UX flows", **ux §n**), `launch-plan-1118.md`, `leads/marketing-lead-copy.md`.

**The operator's direction** (2026-10-24, relayed verbatim by head-bizops → head-product; direction, not authorization):
1. "Work with product and eng to build monetization from day 1. 30 day free trial to access the product."
2. "Make sure the UX team and marketing teams have a chance to celebrate the long trial "Founder's Club" or something
   similar. Discounted pricing mentioned as well."

**The operator's decision** (2026-10-25, relayed verbatim via head-bizops → head-product): "Approve M2-M5 as recommended:
trade features only locked (C2), $4.99/$24.99 Founder then $6.99/$34.99 from 2027-01-01, rest of PR #393 incl. decision
16. Name: Founding GMs. Listing line: legal's R28.8 version." **Route (M1 = R1):** "Ok. Then we need to build it." The 4th
Eng slot is approved (engagement-eng from 10-28, weekends, the 11-03 checkpoint; R3 if it isn't green).

## TL;DR

- **Mechanism: A-preview.** Apple's 1-month introductory free trial (StoreKit; the path 3.1.2(a) names), offered on
  day 0 **after the user's first trade opinion** (ux §1), never at sign-in. The free first deck page is usage-metered,
  not timed: freemium, not an app-managed trial. **Not B** (2020 rejection precedent, unreliable clock, claimable
  identities, about 2 more eng days). **Not A at sign-in** (an invitee meets a purchase sheet before any trade and can't
  activate, which breaks the launch-MUST referral loop).
- **The gate: gated = makes or sends a trade; free = yours, or not a trade suggestion** (ux §3, plus the lead's four
  calls). Ranking and Calibration stay free forever, so lapsed users' boards keep feeding payers' two-board cards.
  Delete, export, Restore, Privacy, Terms, help and feedback are always reachable.
- **Operator ruling, 2026-10-24** (verbatim): "No to any UX reflections of a trial countdown. So scrap the 3 days and the
  day 30 items". Trial terms (duration, what happens at the end, price) and the cut-off are stated **once, at the start,
  on the offer** (3.1.2). When access ends, a gated action opens the **standard paywall**; free surfaces stay free.
- **Prices (decided): the Founding GMs price, $4.99/mo and $24.99/yr,** each with a 1-month free trial. From
  **2027-01-01** (last club day 2026-12-31) new subscribers pay $6.99/$34.99; existing ones keep their price (Apple's
  price preservation). **No Founder SKU, no lifetime, no Season Pass; tips stay dark.**
- **TestFlight users:** no app clock, no comp, the tester welcome. **Web:** the same rule behind its own knob, ungated
  until 11-18, then the first web deck and "continue on iPhone"; no web trial. The extension's routes are all free.
- **Cost: about 9.25–9.75 eng-days; ≈ 7.65 binary-critical,** 1.6–2.1 server-side or later (the ruling took 1.5 d out,
  0.75 of it binary). The lead's provisional "~8 total, 6.5–7 binary-critical" left out head-eng's own ramp-up, wiring
  and review-reserve rows (1.25 d) and ux-lead's required items.
- **Route (decided): R1.** Against 8 working days (10-28 → 11-06) it has **~0.35 working days of slack** (~2.35 calendar
  days with weekends). The 4th slot is approved; the App Store Connect lane and design-lead's 10-28 visuals still gate it.
  Checkpoint 11-03: if the client gate isn't CI-green, it comes out of the binary and we take R3.

## Decision table (all DECIDED 2026-10-25; quote above)

| # | Decision | **Decided** | Alternative not taken | Cost of being wrong |
|---|---|---|---|---|
| 1 | Trial mechanism | **A-preview:** StoreKit 1-month trial, offered after the first opinion ("rest of PR #393") | B, an app-managed 30 days | B: a likely 3.1.2(a) rejection with 8 days to launch; A at sign-in: invitees can't activate |
| 2 | What's gated | **C2:** gated = makes or sends a trade; everything else free. A gated action opens the standard paywall ("trade features only locked (C2)") | C1: everything but group A gated | C1 freezes boards and empties free surfaces, so lapsed users vanish from the network |
| 3 | Prices | **$4.99 / $24.99 at launch** with 1-month trials; **$6.99 / $34.99** for new subscribers from 2027-01-01 | Launch at $6.99/$34.99, discount by code | A later cut passes through to everyone; a founder price set too low is locked for the cohort |
| 4 | Founder mechanism | **Apple price preservation**, one SKU per plan | A separate Founder SKU; offer codes; $119 lifetime | A separate SKU either stops founders' renewals or leaks the price to everyone |
| 5 | Name, cut-off, commitment | **"Founding GMs";** last day **2026-12-31**; **commit** to keeping the price while subscribed | Another name; a later cut-off | An uncommitted line reads as bait; a cut-off that slips is a false-urgency claim (5.6) |
| 6 | Lifetime, Season Pass, tips | **Drop / defer / keep dark** | Ship tips as built | More IAPs to review on the first submission, and a perpetual grant with storage liability |
| 7 | TestFlight users | **No clock, no comp**; Founding GMs on the same terms | 90-day comp (#347) | A comp past the cut-off makes them miss the founder price |
| 8 | Web and extension | **Web gated by the server rule** under `paywall_web_enforce_enabled`, **ungated until 11-18** (head-product); extension unchanged | A web trial | A web-only free window is a bypass with no purchase path |
| 9 | Identity | **Pro counts only on verified or demo sessions** (head-eng's P47). Unverified sessions get **no free page** (P53): the existing account check answers 403 `verification_required` at the first trade action, and the client opens the same verify sheet as for the **status-blind** backstop 402 `verify_required`, subscriber or not (legal R28.9 row 4, a MUST; `org/leads/legal-lead.md:1677`) | Pro on any session; a verify gate only for subscribers | A paid entitlement usable from a claimable username; a subscriber-only gate reveals who pays |
| 10 | Route | **R1** ("Ok. Then we need to build it."); the 4th slot approved; checkpoint 11-03, else R3 | R3 | R1 slipping late puts an unproven gate in the review binary |
| 11 | Kill criteria | **K0–K3** with the deploy-free knob | None | Damage from the gate goes unseen at n ≈ 8 |

## (a) The trial mechanism

### Options, side by side

| | A at sign-in | **A-preview (decided)** | B: app-managed 30 days |
|---|---|---|---|
| Apple's rule | 3.1.2(a): "Auto-renewable subscription apps may offer a free trial period … in App Store Connect" | Same. The free first page (verified sessions) is a usage-metered free tier [interp.] | No text forbids it, none permits it for subscription apps. Tier-0 trials are for "Non-subscription apps" (3.1.1). 2.2 is a hook |
| App Review evidence | The sanctioned path | Metered free previews are common in the category: Dynasty Nerds' free tier has "3 preview trades/day" [B, #347 §2.1, 2026-10-15] | Three 2020 rejections: "please use App Store Connect to implement free trials" (forum thread 129010). One unverified 2025 "fine" report. Nothing found for 2024–2026 |
| Day-0 decision moment | Yes | **Yes, same session** | No. The ask moves to the window's end, about 12-18, mid fantasy playoffs [A] |
| Trial → paid | Opt-out: 48.8% SaaS [B]; 17–32-day trials 42.5–45.7% [B] | Same | Opt-in: 18.2% SaaS [B]; 8.9% mobile (secondhand, attributed to Adapty but not found on Adapty's page; unverified) |
| Trial starts | Lowest (a purchase sheet before any value) | Middle (only users who've seen a deck) | Every verified sign-in, automatically |
| Invitee activation (FR-17) | **Blocked:** no swipe before the sheet | **Kept:** the first opinion fires before the ask (ux §5 B6) | Kept |
| Leaguemate boards | Free under C2, but the invitee never got to value | Free forever under C2 | Full for 30 days, then the same as A |
| Mutual matches with non-payers | None | First page only | 30 days |
| Eng [E] | ~3.5 d | ~3.5 d + preview [A] | ~5–5.5 d |
| Clock and identity | Apple's, per Apple ID | Apple's, per Apple ID | A server row. First-sign-in timestamps are unreliable (`accounts.py:563`); usernames are claimable; delete-and-recreate resets it (a tombstone is a legal call, onboarding-pm §1) |

Sources: research §1, §4; repo-facts §4; `org/monetization-day1-feasibility.md` §1.

### head-product's three questions

**1. Where does Apple's sheet appear, and is a short look before it allowed without becoming B?** Apple doesn't place
the sheet; StoreKit's sheet opens when the user taps the trial button on our paywall. So the placement is ours.
**Decided: after the first value moment**, at ux-lead's §1 trigger: the first Like or Pass has settled, or the user
leaves the deck after at least one card. **A short look is allowed if it is metered by use, never by time** [interp.]:
- The 2020 rejections were for time windows ("Free until <calculated date 30 days after first launch>").
- The preview is **one deck page** (`paywall_preview_pages` = 1, decided P49): the user can Like or Pass its cards; the
  next page or a new search returns 402 `preview_used`. Sends are gated from the first tap. Cron-built decks never count.
- Copy never calls it a trial or "free access"; Review Notes describe the preview and the gate (2.3.1(a); 2.5.19).
  **Knob = 0 turns the preview off** (the fallback if App Review objects). **Residual risk is low, not zero** [A].

**2. The expected trial-start and conversion difference, A vs B, for a social, invite-driven app.** No primary mobile
data splits opt-in from opt-out; nothing rigorous exists for social or network apps (research §4). What there is:
- **SaaS end to end it's roughly a wash:** opt-in 8.5% visitor → trial × 18.2% → ≈ 1.5% visitor → paid; opt-out 2.5% ×
  48.8% ≈ 1.2% [B, FirstPageSage via Adapty, updated 2026-03-01].
- **Mobile favors the day-0 ask:** "90% of trial starts happen on Day 0" [B, Adapty 2026]; Day 0 holds 50.6% of paid
  conversions [B, RevenueCat SOSA 2026]. B gives that up; A-preview keeps it, one deck later. 17–32-day trials convert
  best: 42.5% median [B, SOSA 2026], 43.7–44.6% [B, RevenueCat 2026-09-28], 45.7% [B, Adapty].
- **FTF estimate, labelled:** A-preview: 20–35% of offer viewers start the month [A] × ~44% convert [B] ≈ **9–15% of
  offer viewers pay**. B: every verified sign-in "starts" × 9–18% opt-in conversion (18.2% SaaS [B]; 8.9% mobile,
  secondhand, attributed to Adapty but not found on Adapty's page; unverified) ≈ **9–18% of verified sign-ins pay**,
  measured when the window ends, in the fantasy playoffs [A].
- **At ≈ 8 MAU [M, W3 2026-10-20] none of this is measurable before Q1 2027** [A]; what matters is review risk, cost, network.

**3. The decision and the Founder offer form.** A-preview, with the Founder price delivered by **Apple price
preservation** on the two existing SKUs, not an offer code, a separate SKU or a lifetime (§(b)).

### The network-effect lens

Trades need leaguemates' boards, and the referral loop is a launch MUST. From the code (repo-facts §1–2):
- **Activation survives A-preview.** FR-17 activates on the invitee's first `trade_proposed` or `match_swiped`
  (`origin/plan/referral-loop:docs/plans/referral-loop/prd.md:889-899`), both fired by the swipe route before the offer; A at sign-in blocks it.
  **An unverified (username-only) invitee must verify before their first swipe,** so FR-17 activation needs
  verification. That's existing behavior from the account check (`_verified_read_denial`), not caused by monetization.
- **Boards persist.** `load_member_rankings` (`database.py:9281-9380`) loads every leaguemate's row, with no activity
  or entitlement filter. A gated user's last board keeps powering payers' two-board cards. **The gate must not filter
  this load** (scope §3 pins it). Under C2 the board doesn't freeze: every rank write republishes it.
- **New mutual matches with non-payers stop** (a match needs both users' likes, `server.py:16300-16345`): the real
  network cost of A over B, which keeps matches for 30 days. **Sends are unaffected:** a payer's proposal lands in
  Sleeper, ESPN or MFL with no FTF account on the other side (`server.py:19582-19640`). **Existing pushes to gated
  users** (`trade_match`, `league_member_unlocked_trades`) land on Matches, free to view; acting on one opens the
  standard paywall, a reactivation moment. No new push is added.

**Why not B:** the rejection precedent with 8 days to launch; untrustworthy first-sign-in timestamps; claimable
usernames; ~2 more eng days; an end-of-window ask in the playoffs. Its one advantage (30 days of matches with every
leaguemate) doesn't outweigh that. **Why gate the core loop at all:** the operator directed it; the preview protects
activation, C2 the network, and K0–K3 with the knob protect retention.

**This overturns four standing rules** (an ADR plus a D-entry, head-eng): foundation §2.2's "never wrapped" core loop
(`00-platform-foundation.md:131-134`) and the `_require_pro` docstring (`server.py:31144-31146`); the 2026-08-14
never-gated list; **never tolled, for swipes** (BL-001 makes swipes move ratings at half K; C2 keeps never-tolled for
ranking and Calibration); and the August trial ruling (14 days monthly), now 1 month on both.

## (b) Plans and prices

| SKU (one subscription group, same level) | Club open (launch → cut-off) | After the cut-off, new subscribers | Intro offer | Net at 15% (SBP) |
|---|---|---|---|---|
| `ftf_pro_annual` (**hero**, pre-selected) | **$24.99/yr** ($2.08/mo) | $34.99/yr | 1-month free trial | $21.24 → $29.74 |
| `ftf_pro_monthly` | **$4.99/mo** | $6.99/mo | 1-month free trial | $4.24 → $5.94 |

- **Arithmetic** [computed]: a 28.6% discount on both plans; annual saves 58% vs 12 × monthly. Break-even at the Founder
  price: #347's run-rate $43.45–87.45/mo (§7) ÷ $1.77 net per annual-month = **25–49 annual subscribers** (17.5–35.3 at $34.99).
- **Main today** [M]: $4.99 monthly with `trial_days` 14 and $34.99 annual with 30 (`server.py:31188-31193`), rendered
  as "30 days free" (`PaywallScreen.tsx:166-176`). The live App Store Connect intro offer is unverified (head-eng: 3 days).
- **"1 month", never "30 days":** Apple has no 30-day duration ("3 Days. 1 or 2 Weeks. 1, 2, 3, or 6 Months. 1 Year").
  The config gains a `trial_period` string; "free" copy keys off Apple eligibility (ux rule 0.3); one intro offer per
  Apple ID per group. **Supersedes** #347's 14-day monthly trial; #347's prices become the post-cut-off standard.

### The Founder mechanism: price preservation

| Mechanism | Locks the price? | Why / why not (research §3) |
|---|---|---|
| **(e) Price preservation (decided)** | **Yes, while subscribed** | At the cut-off, schedule the increase with "Keep the current price for existing subscribers": "Anyone who subscribed before the start date … won't be affected." The cohort is unlimited. A StoreKit trial "begins immediately", so trialists before the cut-off are covered [interp.]. One SKU per plan, nothing extra in Manage Subscriptions, no signing, ~0 projector work |
| Separate Founder subscription SKU (head-eng's addendum pick) | No | "Remove it from sale … to stop additional sign-ups **and renewals**." Left on sale, every subscriber sees it and can crossgrade to it from iOS Settings (Apple staff, forum threads 716772 and 829942). **This corrects the feasibility addendum; its 0.5 d is saved** |
| Intro discount | No | One intro per product per storefront, and the free month uses it. Capped at 1 year |
| Offer codes · promotional offers | No | Both renew at the standard price. Promotional offers reach existing or lapsed subscribers only. Codes are for creators and partners later, never the lock |
| $119 lifetime (#347) | Yes | A perpetual `founder_iap` row, irreversible Family Sharing, the 5d/5e cap work, and a storage liability. **Drop at launch** |

**Caveats:**
- **Plan switch** [unverified]: preservation attaches to the product, so assume a monthly founder who moves to annual
  after the cut-off pays the new annual price. Copy says "on your plan"; the annual hero minimises it.
- **Lapsed founders: the sources differ.** Apple's help (research §3e): "Subscribers whose subscription expires can
  resubscribe at the preserved price within 60 days of expiration." ux §3 reads it as active subscribers only. The
  60-day rule is Apple's cited text; **legal-lead words it,** and the offer never promises more than Apple applies.
- **FTF's promise, not Apple's guarantee:** Apple lets us "un-preserve" later; DPLA Sched. 2 §3.8(c) says "fulfill the
  offer … as marketed". **The raise needs no notice** to existing subscribers, whose price doesn't change.
- **2.3.14:** no discounted price in App Store creative. **Reference-price framing** (legal-lead): "Founder price
  $24.99/yr; new members pay $34.99 from Jan 1", never "was $34.99". **Once announced, the raise must happen** (5.6).
  Schedule the 2027-01-01 increase in App Store Connect at setup so the cut-off executes itself.
- **Dropped at launch:** the lifetime; the Season Pass (already deferred to 2027); tips (dark: three fewer IAPs on a
  first review, plus one binary line to hide the Settings tip row, `SettingsHubScreen.tsx:300-305`); #347's league cap
  (5g; moot when free users get no trades).

## (c) What's gated after the trial

**The rule (ux §3, adopted): gated = makes or sends a trade; free = yours, or not a trade suggestion.**

| Gated (a user action → 402 → the standard paywall) | Free, forever, for signed-in users |
|---|---|
| The deck and Find a trade beyond the preview page; Shop a player; team overhaul suggestions; Win Now trade targets (the four `/api/win-now/*` routes, P52); Send in Sleeper, ESPN or MFL (and MFL respond); the trade queue; standing offers; Today's Trade (dark); **from Matches: accept, send or swipe**; **from the calculator: Find a trade and its suggestions** | Rank, all modes (trios, tiers, quick, manual, rookie, anchors); **Calibration** (data-generating and feeds model evals); Trends and Usage Trends data; league standings, rosters, outlook, power rankings, free agents, receipts, team review; Settings; the Home hub (its trade tile opens the standard paywall); **the calculator's value comparison of a trade the user builds**; **viewing existing Matches** (a reactivation hook; dismiss is free); **the Draft Room** (not a trade suggestion); the "Season projections & Win Now" standings (`/api/league/season-projections`, P52); invites; profile; **P48 (Product-confirmed): `/api/trades/validate` (the calculator's value check), standing-offer revoke (your own offer), matches dismiss, `/api/trades/liked` (your own list)**; Portfolio and mock draft by the same rule [A, ux-lead to confirm] |

**The client source for engagement-eng:** ux-lead's surface classification, with its "Decide" column
(`org/reports/ux-lead.md:495`) **decided by Product:** the calculator's value comparison of a user-built trade FREE
(its deck suggestions and sends gated); viewing existing Matches FREE (dismiss free; swipe, accept, send gated); the
Draft Room FREE; Calibration FREE.

**Always reachable, the group-A floor:** sign-in and sign-out; the league picker and connect flows; Settings and its
pages; **Delete account** (`DELETE /api/account`, `server.py:28133`, with legal's subscription note); **Download my
data** (`server.py:28101`); **Restore**, on the standard paywall and in Settings › Subscription (today it is only on
`PaywallScreen.tsx:391-394`); Privacy and Terms; Help & about, FAQ and contact; the feedback FAB and inbox; the
forced-update gate; `/api/me/entitlements`, `/api/paywall/config`, `/api/events`, notifications; the billing webhooks,
admin and cron (never gated).

**When access ends** (a trial ended, a subscription lapsed, or a day-0 decline ran out of its kept page), nothing appears
on its own. The next gated action opens the **standard paywall** (the 3.1.2 disclosures, Restore, a close control); in the
deck, the kept page's end card has one button to it (ux §1's decline path). Free surfaces never show it. ux §3's
in-place gated state and its day-30 treatment are **superseded by the operator ruling of 2026-10-24**.

**Server rules for head-eng:** **per route, not per prefix** (`/api/league/*` and `/api/trades/*` mix families:
`GET /api/trades/matches` free, `…/disposition` gated; `/api/trade/evaluate` free, `/api/trades/fair-packages` gated),
one `before_request` reading a classification table, CI failing on any unclassified route (scope §3). **The client opens
the paywall only on user actions;** a background 402 never does (ux §3). Always-reachable rows fail open on network
errors (onboarding-pm §4). `load_member_rankings` is never filtered by entitlement.

**C1 vs C2.** C1 is head-eng's allowlist (everything but group A gated): a lapsed user's tabs go dark, their board
freezes, and they stop being a useful counterparty. **C2 decided,** at **+0.25 d [A]**: the free set is wider, but
non-deck gated entry points open the standard paywall, so no bespoke in-place states are built.

## (d) Existing TestFlight users

- **How many:** about 8 MAU [M, W3 2026-10-20]; ux-lead counts about 4 testers. No TestFlight signal exists in code.
- **No app-managed clock under A:** their month starts with Apple's trial on the App Store build (sandbox history leaves
  production eligibility untouched [interp.; release-lead to confirm]); their preview counts from enforcement start (ux §6).
- **Founding GMs on the same terms** (tester welcome, ux §4.1). **No comp:** #347's 90-day comp would cost them the founder price.
- **Manual grants only for** the operator's 2 allowlisted ids (`config/tester_allowlist.json`) and the entitled App
  Review demo (`/api/admin/entitlements/grant`, `server.py:31254`), by release-lead on the operator's word. **Two
  "demos", no conflict:** the **App Review demo accounts** (one granted, one never entitled) **stay gated**, so the
  reviewer sees the real gate (preview → offer → sandbox purchase; 5f caps sandbox grants at 24 h). The **try-before-sync
  session** (`_synthetic_demo_session`) **is exempt** (head-eng coded it; moot while `try_before_sync` is off). **Demo B
  is reserved for App Review** (P56): never used for testing; every never-entitled check runs on a fresh account.
- **Testers move to the App Store build;** the operator tells them (ux §6; outbound). Old TestFlight builds have no 402
  handling and will error once enforcement is on. **head-bizops' "clock from 11-18" applies only under B;** under R3
  with A there's still no app clock (11-18 to the gate go-live is simply free launch use).

## (e) Web and the extension

- **Web: the same server rule, behind its own knob `paywall_web_enforce_enabled`** (head-eng; any request without the
  native app's `X-Device` counts as web). **head-product ruled the web stays ungated until 11-18;** the knob flips on
  11-18 once `IOS_INSTALL_URL` resolves. Then, after the first web deck, web shows "continue on iPhone" (it needs a 402
  handler; none exists, repo-facts §7); free surfaces, sign-in, settings, legal and delete stay reachable.
- **No web trial** (no web purchase path; a web-only free window would be a bypass). Desktop invitees are steered to the
  iPhone (the #386 QR, ux §5 B9). Web has no Apple sign-in, so `acct_`-only users still can't use it (unchanged).
- **Server/web, not binary:** eng-web, 0.5–1 d [A], live ≤ 11-16; not in head-eng's estimate. Later: revisit Stripe "or
  subscribe on the web" (a US link-out is allowed today at 0% Apple commission, research §5).
- **The extension needs no change:** its five routes (`/api/extension/auth`, `/api/sleeper/link`, `/api/extension/rankings`,
  `/api/feature-flags`, `/api/events`) are all free or never-gated under C2, and its auth response has no `pro` field
  (`server.py:26018-26027`). If the per-route review gates any, allowlist it now and gate it in a later release.

## (f) Celebration moments: names only

ux-lead's flows are the spec. **Superseded by the operator ruling of 2026-10-24:** ux §2 in full, the day-30 part of §3,
and the T-3 items. Cited as before: rules §0, the offer §1, §3's reachability, 402 rule and classification, §4.1–§4.3,
invitees and bounce points B1–B9 §5, TestFlight users §6, the B column, copy slots `mz.*`. **design-lead** owns visuals
(~10-28); **marketing-lead** writes the copy via head-bizops (reconciling its `mon.*` drafts, `marketing-lead-copy.md`
§9); **legal-lead** reviews the purchase-adjacent strings.

| # | Moment | ux-lead | Driven by | First needed | In the 11-06 binary? |
|---|---|---|---|---|---|
| 1 | **The offer:** "Start your free month", with the Founder framing. **The one place** the trial terms (duration, what happens at the end, price) and the cut-off date are stated (3.1.2) | §1 | PaywallScreen. Copy and club window from `/api/paywall/config` (server-driven) | Day 0 | **Y** |
| 2 | **Joining:** "Welcome, Founding GM" (no dates) | §4.1 | Binary, once, after Apple's sheet | Day 0 | **Y** |
| 3 | **Founder price locked:** the Settings › Subscription status line ("Founding GM", the plan, Manage, Restore; no trial dates) | §4.2 | Binary | Day 0 | **Y** |
| 4 | **Recognition:** a private mark, not on trade cards in v1 | §4.2 | Binary Home hub header | Any time | Update 1 |
| 5 | **"You kept the founder price"** | §4.3 | Binary Home line plus a server signal | First open after the cut-off | Update ≤ ~12-20 |
| 6 | **Gated re-entry:** an existing leaguemate push → Matches (free to view); acting → the standard paywall | §5 | Existing pushes plus the 402 handler | After access ends | **Y** (the 402 handler) |

- **Dropped under the ruling:** all of ux §2, ux §3's day-30 treatment, the club's closing-reminder moment, and ux
  §4.4's mid-trial recap (it marks time in the trial). **Moments 4 and 5 ride update 1** (~11-28 [E]).
- **One yield to ux-lead:** the lead's first draft had a badge on cards; §4.2's private mark replaces it.

## Analytics (spec in [scope.md](scope.md) §1; for analytics-lead to grant)

- **Conversion truth is the ledger** (`entitlements`, `subscription_events`: INITIAL_PURCHASE `period_type=TRIAL`, the
  first RENEWAL, CANCELLATION). **Register `entitlement_granted`** (#347 5h; INTENT). **One new server event,
  `paywall_gate_hit`** (NON_INTENT; `gate`, `route_family`; capped per user, gate and family per UTC day).
- **Reuse `paywall_viewed`, widening `source`** to `first_opinion` | `left_deck` | `gate` | `settings`. **No
  `paywall_shown`** (a duplicate), no client `trial_started` or `declined` (a viewed with no purchase initiated).

## Kill criteria

#347's K1–K3, re-based (the gate removes non-payers' swipes from WAT by design); action: knob → 0; thresholds [A].

| Criterion | Trigger | Read by |
|---|---|---|
| **K0, the preview is broken** | Any 402 `preview_used` to a user who has never been served a card | analytics-lead, daily for 14 days; it's a defect |
| **K1, WAT** | WAT per entitled user (trial plus paid) below 85% of the pre-launch per-active-user rate for 2 consecutive weeks | analytics-lead |
| **K2, W1 retention** (INTENT, which includes the free surfaces) | Post-launch cohorts ≥ 10 points below pre-launch | analytics-lead |
| **K3, gate churn** | Of users with a `paywall_gate_hit` who were WAT-active in the prior 14 days: 2 of the first 5, or ≥ 30% once there are 10+, go **INTENT**-dark (not just WAT-dark) for 14 days | analytics-lead |

## Itemization (head-bizops' reconciliation)

| # | Piece | Days | Mech. | Owner | Binary by 11-06? |
|---|---|---|---|---|---|
| 1 | Global server gate: one `before_request`, a per-route classification, 402 `pro_required` + `gate`. **Under way:** head-eng's #395 (draft) keeps the P48 free routes free | 1.0 [E] | both | eng (4th slot) | Y (live before the 11-07 TestFlight build and review) |
| 2 | Deploy-free kill knob; the enforce rule `entitlements.is_enforcing()` = `monetize.entitlements` ∧ `monetize.paywall` ∧ `paywall_enforce_enabled` (5a as head-eng ruled it). **Under way:** #394 (draft) implements it | 0.25 [E] | both | eng | Y |
| 3 | Mobile client gate: a global 402 handler (user actions only) opening the standard paywall, the deck's end-of-page card, Restore on the paywall and in Settings, the tip row hidden | 1.25 [E] | both | eng | Y |
| 4 | Analytics registration: 5h, `paywall_gate_hit`, the `source` enum | 0.25 [E] | both | eng; analytics-lead grants | Y (server registration deploys before the binary) |
| 5 | 5f, the sandbox cap (24 h); 5d's perpetual-grant guard | 0.25 [E] | both | eng | Y |
| 6 | Mechanism A: 1-month intro wiring | 0.5 [E] | A | eng | Y |
| | *head-eng's A subtotal (includes the shared ~3 d)* | *3.5 [E]* | | | |
| 7 | Ramp-up: monetization has no current Eng owner | 0.5 [E] | both | eng | Y |
| 8 | Eng-side App Store Connect and RevenueCat wiring, plus a sandbox end-to-end | 0.25 [E] | both | eng | Y |
| 9 | Reserve for IAP-review rejection fixes (plus 1–2 calendar days) | 0.5 [E] | both | eng | N (after 11-10) |
| 10 | Founder annual SKU (head-eng's addendum) | ~~0.5~~ **0** | — | — | Dropped (§(b)) |
| 11 | Preview (P49): server `paywall_preview_pages` = 1, the first page of the first deck through E2 paging, a per-user "preview used" record (merges by 11-06; fixes #395's `PREVIEW_PAGES = 0`); client end card and §1 offer trigger with knob = 1 as primary | 0.5 [A] | A | server: platforms-eng; client: engagement-eng | Y |
| 12 | The offer as an interrupt surface right after `guide_step`; deck state kept across the detour (ux §0.2, §1) | 0.25 [A] | A | eng | Y |
| 13 | Rule 0.3: "free" copy keyed off RevenueCat's intro-eligibility check, not `trial_eligible` (`PaywallScreen.tsx:166`) | 0.25 [A] | A | eng | Y |
| 14 | C2 per ux-lead's classification: the wider free set; non-deck gated entry points open the standard paywall (required by the ruling) | 0.25 [A] | both | eng | Y |
| 15 | P47 + legal R28.9 row 4 + P53–P55: Pro only on verified or demo sessions; the client opens one verify sheet for the account check's 403 `verification_required` and the status-blind backstop 402 `verify_required`; Sleeper: Verify with Sleeper only; others: Apple as a new sign-in (ux-lead addendum §3, amended) | 0.25 [A] | both | eng; ux-lead specs | Y |
| 16 | The Founder window in `/api/paywall/config`, display prices, and a `founder` flag on entitlements | 0.25 [A] | A | eng | Y |
| 17 | 5b, the `enforcing` predicate; 5c, a truthful feature grid | 0.25 [A] | both | eng | 5b Y; 5c N (server config, live by 11-09) |
| 18 | ~~Trial state (`in_trial`, `will_renew`)~~ | **0** | — | — | Dropped (operator ruling 2026-10-24): nothing else needs it. Settings shows no trial dates; the gate's `trial_expired` / `lapsed` split is server-side, in row 1 |
| 19 | Celebration in the binary: the welcome (§4.1) and the Settings › Subscription status line (Founding GM, plan, Manage, Restore) | 0.5 [A] | both | eng; design-lead visuals | Y |
| 20 | Celebration in update 1: the Home hub mark (§4.2), the kept-price line (§4.3) and its server signal | 0.5 [A] | A | eng | N (update 1, before the cut-off) |
| 21 | D-056 evidence: the pytest gate matrix, allowlist completeness with sabotage, `check-paywall-gate.js`, a sandbox run | 1.0 [A] (Eng had 0.5) | both | eng, QA | Y |
| 22 | Web: a 402 handler and the "continue on iPhone" state | 0.5–1.0 [A] | both | eng-web | N (server/web, ≤ 11-16) |
| 23 | ~~The pre-charge reminder push (Pro PRD R19)~~ | **0** | — | — | Dropped (operator ruling 2026-10-24) |
| | **Total** | **9.25–9.75** | | | **Binary ≈ 7.65; server or later ≈ 1.6–2.1** |
| — | Design: the offer, welcome, deck end card, Settings section, Home mark | ~1 d | both | design-lead | Y (visuals ~10-28) |
| — | Copy (`mz.*`) | — | both | marketing-lead via head-bizops; legal-lead | Y (by ~11-02) |
| — | `web/terms.html` subscription, billing, refund, founder-price and lapse terms | — | both | legal-lead; onboarding-eng deploys | N (live by 11-09) |
| — | The operator lane (below) and the operator's TestFlight run | — | both | operator | Gates 11-10 |
| — | Review buffer | 1–2 calendar days | both | release-lead | Rides 11-10 |

**Reconciled against head-eng.** Eng's A ~3.5 / B ~5–5.5 include the shared 3 d; Eng's own A total with its addendum
was ~7 (6.5–7.5) [E]. This table is that 7, minus the 0.5 SKU, plus Product's ~2.75–3.25 d: preview +0.5, interrupt and
deck state +0.25, rule 0.3 +0.25, C2 +0.25, identity +0.25, Founder config +0.25, 5b/5c +0.25, tests +0.5 over Eng's
0.5, celebration −0.25 (1.0 vs Eng's 1.25), web +0.5–1.0. **The ruling removed 1.5 d** (rows 14, 18, 19 and 20 −0.25
each; row 23 −0.5), 0.75 of it binary. **B's equivalent is about 11.5 d.**

**head-bizops' expected gap:** Founder SKU / projector / config display **corrected** (no SKU or projector work; config
0.25). #347's 5a, 5b, 5c, 5f, 5h **confirmed** (rows 2, 17, 5, 4; 5a as `is_enforcing()`; 5d's guard stays, 5e and 5g
drop). Events and tests **resized** (0.25; 1.0). Celebration **split** (0.5 binary, 0.5 update 1; design and copy outside
the Eng slots). Review buffer **confirmed** (0.5 d plus 1–2 calendar days). **Missing from the gap:** rows 7, 8, 11–15, 22.

**No optional cuts remain:** the ruling made the row-14 cut required and removed row 18.

## Routes R1–R3 and the timeline verdict

| Route | What | Eng cost | Purchases live | Founder window | Risk | Network |
|---|---|---|---|---|---|---|
| **R1** | A 4th slot from ~10-28. The gate is in the 11-06 binary, live in prod for review on 11-10 and for the public on 11-18 | ≈ 7.65 binary + ≈ 1.6–2.1 server or later | 11-18 | 11-18 → cut-off | ~0.35 working days of slack. A first-IAP review with 8 days to launch | Paid from day 1; the preview and C2 protect activation and boards |
| **R2** | Server-dark: the same build, with enforcement switched on after approval | **The same as R1; it saves no eng days** | 11-18 | Same | Under 2.5.19 the gate and IAPs can't be dormant during review, and IAPs submitted with the binary must be reviewable (2.1(b)). So review needs them on for the demo accounts, described in Review Notes. Manual release (SB-3) means no public user exists before 11-18 anyway, so R2 differs from R1 only for testers 11-10 → 11-18. **If the IAPs aren't submitted with 11-10, there are no purchases until a later version: R2 becomes R3** | Same as R1 |
| **R3** | Launch free on 11-18; the gate ships in update 1 (built 11-18 → 11-21, live ~11-28 [E]) | The same total, no 4th slot | ~11-28 | Opens at gate go-live (≥ 4.5 weeks to 12-31) | **Misses "from day 1".** Needs B8's forced update to the gate-aware build before enforcing; the IAPs are reviewed with update 1 | **Upside:** a free launch week. Every new user and invitee builds a board, swipes and matches for ~10 days |

**The verdict: R1, decided 2026-10-25.** 10-28 → 11-06 is 8 working days (10 with weekends, approved). Binary-critical work
is ≈ 7.65 eng-days, so the slack is **about 0.35 working days, ~2.35 calendar days**. With the 4th slot approved, R1
still needs head-eng's rows 11–17 confirmed, design-lead's visuals by 10-28, the `mz.*` copy by ~11-02, and **the
operator lane:** Paid Applications Agreement, banking, tax, SBP; the subscription group with both SKUs at $4.99/$24.99, a
1-month intro on each, and the 2027-01-01 increase scheduled with "keep current price"; multiseat and Family Sharing
off; tips not submitted; RevenueCat (`pro`, offering, webhook); `REVENUECAT_WEBHOOK_SECRET` on Render;
`EXPO_PUBLIC_REVENUECAT_IOS_KEY` in EAS production by ~11-07; two App Review demo accounts (both gated); Gate 0. **Checkpoint 11-03:** if the
client gate PR isn't CI-green, pull it from the binary and run R3; a half-built gate in the review binary is the worst outcome.

## Product knock-ons, one line each

- **Gated vs reachable:** a gated action opens the standard paywall; free surfaces say they're free (ux §0.4) and never
  show it. Settings › Subscription (Restore, Manage) is always visible once `monetize.paywall` is on. **The paywall stays
  dismissible** ("Not now" and a close control), so the config gets **no non-dismissible mode** (against the lead's
  first draft): a paywall you can't close would wall off the free surfaces and Settings.
- **The Founding GMs display window:** `/api/paywall/config` serves the club block from 11-18 (or the R3 go-live) to the
  cut-off. It must equal App Store Connect's scheduled price-change date. Afterwards it shows standard prices, and the
  founder line goes to members only (ux §4.3).
- **Trial terms once, at the start** (3.1.2; the 2026-10-24 ruling): duration, end behavior, price and cut-off appear on
  the offer only, never after (Settings and the welcome included; Apple's subscription page carries the dates). So no
  `in_trial` / `will_renew` (row 18 dropped); the unstored `period_type` (`entitlements.py:421`, `:535`) matters only for
  the gate's server-side `trial_expired` / `lapsed` split.
- **Web:** ungated until 11-18, then the "continue on iPhone" state after the first web deck; no web purchase or trial.
- **"Free" claims:** the FAQ pricing line is already out (FAQ-R4, marketing-lead 10-24, `marketing-lead-copy.md:66`).
  Still to change: support macro T5 ("free today") retires the moment the RevenueCat key is in a build (`:740-751`);
  `web/index.html:7, :12` still say "Free." on main [M], and the approved `m3.web.meta_desc`/`og_desc` rewrites that cut
  it must land first. **The listing line (decided, legal's R28.8):** "Finding and sending trades needs a subscription,
  starting with 1 month free. It renews automatically until cancelled." It replaces the approved "Free to use."
  `web/terms.html` needs subscription, billing, renewal, refund, founder-price and lapse terms (legal-lead) by 11-09.
- **Unverified sessions** (legal R28.9 row 4; P53–P55): **no free page;** the first trade action meets the account
  check's 403 and the same "Verify this session first" sheet as the backstop 402 (`mon.verify.*`; ux-lead §3, amended:
  Sleeper gets Verify with Sleeper only; others get Apple's button as a new sign-in). Nothing differs by status. After
  verifying: entitled → the action continues; not entitled → the free page if unused, else the standard paywall.
- **App Store creative:** no founder price in the screenshots or preview (2.3.14), incl. the operator's 11-08 shots.
  **Review Notes** (release-lead): the preview, the gate, the window, two App Review demo accounts (one granted, both
  gated). **Invites:** the referral copy (#348, #386) must not promise "free" (marketing-lead).
- **Terms alignment (P50; the lead checked #373 @ `d866706b`):** §14.8 matches this memo ($4.99/$24.99 by 2026-12-31;
  $6.99/$34.99 for new subscribers from 2027-01-01; "won't go up … active on that plan" = keep-current-price; legal's lapse
  wording; §14.3's "1-month" trial) and `org/leads/app-manager-monetization-setup.md` steps 2d, 2e, 3a–3c. **Dependency:**
  "starting a free trial counts as subscribing" holds only if both increases start exactly 2027-01-01. §14.8 names no
  plans. **ASC step 2g display names:** `Fleeced Pro Monthly` (`ftf_pro_monthly`), `Fleeced Pro Annual`
  (`ftf_pro_annual`), plain space, no dash; group `Fleeced Pro` (proposed); marketing-lead writes the descriptions.

## Decisions (DECIDED 2026-10-25 unless noted; quote above)

1. **Mechanism:** A-preview (Apple's 1-month trial at ux §1's trigger; one free deck page). **DECIDED.**
2. **Gate scope:** C2, with the four calls (calculator value check, viewing Matches, Draft Room, Calibration free). **DECIDED.**
3. **Prices:** $4.99/$24.99 with 1-month trials; $6.99/$34.99 for new subscribers from 2027-01-01. **DECIDED.**
4. **Founder mechanism:** price preservation; no Founder SKU or lifetime; Season Pass deferred; tips dark. **DECIDED.**
5. **Name:** "Founding GMs". 6. **Cut-off:** last day 2026-12-31. 7. **Keep the founder price while subscribed on your
   plan,** with legal's lapse wording. **All three DECIDED.**
8. **TestFlight users:** no clock, no comp; grants only for the operator's 2 ids and the granted App Review demo (both
   App Review demos stay gated; the try-before-sync session is exempt). **DECIDED.**
9. **Web:** `paywall_web_enforce_enabled`, ungated until 11-18 (head-product), then "continue on iPhone". **DECIDED.**
10. **Identity:** Pro only on verified or demo sessions (P47); no free page for unverified sessions, the 403 account
    check first and the status-blind `verify_required` as backstop (legal R28.9 row 4; P53–P55). **DECIDED.**
11. **Route:** R1 with the approved 4th slot (engagement-eng from 10-28, weekends) and the 11-03 checkpoint, else R3.
    **DECIDED** ("Ok. Then we need to build it.").
12. **Kill criteria** K0–K3 with the knob. 13. **The ADR plus D-entry** for the overturn (head-eng). **Both DECIDED.**
14. **Waivers** W-MON-1 and W-MON-2 ([scope.md](scope.md) §6). **APPROVED** ("rest of PR #393").
15. **Gate 0 (#347): acknowledged; Gate 0 itself stays the operator's yes/no before launch.** No approval scope recorded.
16. **The no-countdown ruling's reading** (no dates after the offer; the deck's kept page ends in a card that opens the
    standard paywall, other gated entry points open it directly; ux §4.4's recap dropped). **DECIDED as written.**

## Handoffs

| Owner box | Deliverable |
|---|---|
| **Operator** (via head-bizops' single brief) | Decided 2026-10-25. Still yours: the operator lane (R1 list); Gate 0; every flag, knob, App Store Connect and EAS action, on your word in the acting session; the message to testers (your outbound) |
| **engagement-eng** (4th slot, via head-eng) | The client per [scope.md](scope.md): the end card and offer trigger with `paywall_preview_pages` = 1 as primary; the plan-title fallbacks to exactly `Fleeced Pro Monthly` / `Fleeced Pro Annual` (`PaywallScreen.tsx:73-74` still has the em-dash form; `org/leads/engagement-eng-paywall.md:47`), landed before the binary |
| **head-eng** | Rows 1–23 (#394 and #395 under way; platforms-eng's `paywall_preview_pages` allowance merges by 11-06). engagement-eng in the approved 4th slot from 10-28; eng-web. The per-route classification. ux-lead's required items: rule 0.3, the interrupt surface, 402 on user actions only, deck state, the kept-price signal. The ADR and D-entry. Build to [scope.md](scope.md) |
| **analytics-lead** | Grant the `entitlement_granted` registration, `paywall_gate_hit` and the `source` enum widening. The ledger queries (trial start, conversion, cancellation). K0–K3 baselines. The invitee funnel cut (ux §5) |
| **ux-lead** | Drop the flows the operator ruling of 2026-10-24 supersedes (ux §2, §3's day-30 state, the T-3 items, §4.4); non-deck gated entry points open the standard paywall. Confirm Portfolio, mock draft and standing offers are classified right |
| **design-lead** | Visuals for the offer, welcome, deck end card, Settings › Subscription and the Home mark (~10-28). Drop the visuals the ruling supersedes (ux §2, §3's day-30 state, the gated card) |
| **marketing-lead** (via head-bizops) | `mz.*` copy reconciled with `mon.*`, minus the slots the ruling supersedes (ux §2, §3's day-30 state, `mz.founder.recap`); the welcome and Settings copy carry no dates. The founder-price framing (no "was"). **The listing line is legal's R28.8:** "Finding and sending trades needs a subscription, starting with 1 month free. It renews automatically until cancelled." (replaces "Free to use."). The landing, macro T5 and invite-copy sweep. A 2.3.14 check of the screenshots |
| **legal-lead** (via head-bizops) | `web/terms.html` subscription terms. The lapsed-founder rule (60 days vs active). Reference-price framing. The offer's one-time trial terms. The delete-flow subscription note |
| **onboarding-pm** | The verify path behind ux-lead's "Verify this session first" screen (addendum §3), including the M11 dependency for ESPN/MFL entries |
| **growth-pm** | Confirm the invitee path (ux §5 B1–B9) and the B9 desktop steer against #348 and #386 |
| **release-lead** | The App Store Connect checklist with the R28.8 listing line ("Finding and sending trades needs a subscription, starting with 1 month free. It renews automatically until cancelled."), Review Notes, the two App Review demo accounts (one granted, one never entitled; both gated), manual grants, the flip precondition (`paywall_preview_pages` = 1 confirmed, page 1 served, page 2 → 402, before `paywall_enforce_enabled` = 1), the 11-18 `paywall_web_enforce_enabled` flip, FTF_FLAGS-aware flips, and the knob-kill runbook entry, each on the operator's word |
| **app-manager** | Fold [scope.md](scope.md) §3's TestFlight steps into its checklist |
| **head-bizops** | Unit economics re-run at the Founding GMs prices |
| **monetization-pm** (this box) | Mark #347's superseded rows; the stale-doc sweep listed in #347 §12 |
