# Growth backlog

> Standing doc held by `growth-pm` (charter `/pm-growth`). One row per loop idea or
> growth bet, ranked. **Carried forward every `/pm-growth` run**: updated in place, history
> in the changelog. Rows feed PRDs through `head-product`; experiments launch only through
> `analytics-lead` on the operator's go.

**Last updated:** 2026-10-15 at `origin/main` 678834ab · **Owner:** `growth-pm`

**Labels.** Every number is **measured** (query, source, time, n; prod numbers only via
`analytics-lead`), **benchmarked** (cited source + check date) or **assumed**. At this sha no
loop rate is measured; every baseline below is assumed until `analytics-lead`'s W3 baseline
lands. `file:line` cites are at 678834ab. "S" = `backend/server.py`; "FJ" =
`config/features.json`.

## Contents

- [Ranked backlog](#ranked-backlog)
- [Share-loop surfaces (S1–S12)](#share-loop-surfaces-s1s12)
- [Killed and parked](#killed-and-parked)
- [Changelog](#changelog)

## Ranked backlog

**Power pre-check, read once for every row:** at TestFlight scale an A/B on a loop metric
will almost always need more than 26 weeks, so the default plan is a **before/after
descriptive read** with an instrumentation gate. Where a row says "requested", the ask goes to
`analytics-lead` for `/an-experiment`'s `POST /api/admin/experiments/preview` (`growth`
layer); `growth-pm` never calls it.

| Rank | ID | Loop / idea | Hypothesis | Cheapest test | Success criterion (number) | Power pre-check | Owner seam | Status | Evidence / links |
|---|---|---|---|---|---|---|---|---|---|
| 1 | GB-01 | **Referral loop v1** (invite → join → activated, credited per inviter; reward-free, `head-product` P20) | If invites carry a per-share id, land non-users on a device-aware join page with an install path, and credit the inviter at the invitee's first opinion (stage 7, a first swipe or proposal), then activated referrals per active user rise from unknown to measurable and above the target, because phone invitees stop dead-ending and every hop becomes visible | No build: the operator pastes the public TestFlight link under an invite in a few of their own leagues (one ESPN or MFL) and compares `league_member_joined` with `referral_joined` ([marketing-inputs.md §0.2](../../plans/referral-loop/marketing-inputs.md#02-cta-target-lead-recommendation)); plus the scope's TestFlight checklist | Instrumentation gate: ≥95% of invite-following signups carry a ledger row, 2 weeks after Phase 1. Outcome: `K_30` ≥ 0.15 at 8 weeks, joined → activated ≥ 40% (**assumed**; baseline unknown) | No A/B: before/after gated on the instrumentation target. Copy A/B underpowered (`docs/plans/audit-p1-remediation/PRD-p1-5.md:196`, OG-10) | decides `growth-pm`; builds `engagement-eng` (ledger, invite routes, landing) + `onboarding-eng` (web, LeagueJoin, SignIn); words `marketing-lead`; entry points `engagement-pm`; platforms `platforms-pm` | **specced** | [loop audit](../../plans/referral-loop/loop-audit.md) · [PRD](../../plans/referral-loop/prd.md) · [scope](../../plans/referral-loop/scope.md) |
| 2 | GB-02 | **Share landings that work** (S1, S2, S3 via the shared S5 chrome) | If `/s/*` pages unfurl with an image, carry attribution through the CTA to a target a phone can act on, and use one brand name, then share → join rises, because today previews may not render and every CTA lands on a bare `/` | Device unfurl check (iMessage, Discord, X) of one `/s/p` link before and after: absolute `og:image` + `noindex` meta replacing the `robots.txt` block on `/s/` and `/og/`. Copy and config only | Landing CTA click-through ≥ 10% of human landing views over 4 weeks (**assumed**; views are unmeasured today) | Descriptive read; no A/B | decides `growth-pm`; builds `engagement-eng` (`/s/*`, `/og/*`); words `marketing-lead`; indexing call `marketing-lead` (`mkt-seo`); chrome `design-lead` (off-Chalkline today) | idea | CTAs hard-coded `cta_url="/"` (S:25548, :25563, :25669); relative `og:image` (S:25485; callers S:25546, :25558, :25667); `robots.txt:25-26`; brands S:25479, :25512, `backend/og_image.py:171`, `ShareTradeImage.tsx:255`; no landing events (S5). `/s/trade` waits on the enumeration fix (`head-eng`). CTA option per GB-01 decision D-1 (Phase 2) |
| 3 | GB-06 | **Trade-card image share counted and branded** (S1) | If image-share completions fire an event and the card says Fleeced, then we learn whether image shares are a channel worth investing in, because today only the mint is counted | Client-only: send `trade_card_shared` (its `channel` and `surface` props are already registered and reserved, `backend/analytics_taxonomy.py:1035-1038`) on completion; fix the wordmark | ≥ 10 completed image shares per week within 4 weeks (**assumed**) before any further investment | Descriptive | decides `growth-pm`; builds mobile (`head-eng` allocates); events `analytics-lead`; brand `marketing-lead` | idea | No completion event (`mobile/src/components/ShareTradeImage.tsx:129-150`; only `share_package_created` at `:170`); wordmark "Dynasty Trade Finder" (`:255`) |
| 4 | GB-03 | **Installed recipient opens the shared trade**, not the generic Trades tab (S2, S3) | If an installed recipient of `/s/p/<id>` lands on that package in the calculator, then share opens turn into evaluations, because today they land on the Trades tab with nothing shared in view | Count installed `/s/*` opens for 2 weeks (needs `share_link_opened`, proposed in [marketing-inputs.md §C](../../plans/referral-loop/marketing-inputs.md#c-utm--install-source-convention-mkt-seo), pending `analytics-lead`); stop if volume is negligible | ≥ 30% of installed `/s/p` opens reach a calculator evaluation in the same session (**assumed**) | Descriptive | decides `growth-pm`; screen `trades-pm`; builds mobile | idea | `/s/p/<id>` → `app/trades` (`mobile/src/utils/deepLinks.ts:236`); `/s/trade/<id>` → `app/matches/<id>`, a match the recipient isn't in (`:235`) |
| 5 | GB-04 | **Trade offers that reach non-users** (S6) | If, after a send-to-league, the sender gets a one-tap "text @leaguemate the breakdown" share (an `/s/p` link with attribution), and/or an opt-in comment rides ESPN/MFL offers, then the counterparty meets Fleeced at the decision moment and some install | Manual: the operator texts `/s/p` breakdowns to counterparties of their own sent offers for 2 weeks and counts joins (no build) | ≥ 1 join per 10 breakdown shares over 4 weeks (**assumed**) | Descriptive | decides `growth-pm`; platform terms and spam `platforms-pm`; words `marketing-lead`; the post-send moment `engagement-pm` (the rating prompt already uses it) | idea | MFL `COMMENTS` (`backend/mfl_write.py:209-212`) and ESPN `comment` (`backend/espn_write.py:323-326`, "not observed in either football capture") supported; client types allow it (`mobile/src/api/sendInMfl.ts:58`, `sendInEspn.ts:66`), no caller sets it; Sleeper's mutation has no message field (`backend/sleeper_write.py:215-218`) |
| 6 | GB-09 | **League completion / group unlock** ("N of 12 leaguemates joined") | If the league has a visible shared goal, then invites per active user (`i`) rise, because the ask becomes collective, not personal | Copy-only change on the existing League Home invite card stating a goal with no reward; before/after on `invite_cta_tapped ÷ invite_cta_shown{league_home}` (that rate is sound, `analytics_taxonomy.py:1307-1308`) | +25% relative tap rate over 4 weeks (**assumed**; baseline pending W3) | Requested only if the operator wants a test; expect underpowered | decides `growth-pm`; anything paid `monetization-pm`; card `engagement-pm`; words `marketing-lead` | idea | `growth.group_unlock` declared (`backend/feature_flags.py:269`; FJ:150 false), read nowhere; `promo_group_unlock` entitlement source never granted (`backend/entitlements.py:50`) |
| 7 | GB-13 | **Named-leaguemate invite** ("Dave, Priya and 7 others haven't joined") | If the invite names the specific leaguemates still out, then tap rate rises, because names are social proof the inviter recognises | Copy change on the League Home card, before/after on the same `league_home` tap rate | +20% relative tap rate over 4 weeks (**assumed**) | As GB-09 | decides `growth-pm`; card `engagement-pm`; words `marketing-lead`; UI `design-lead` | idea | Deferred follow-on (`PRD-p1-5.md:198`); per-member `joined` already loaded (`backend/database.py:8761-8790`) |
| 8 | GB-14 | **Home hub invite tile** | If Home (a tile hub since 2026-10-10) shows an invite tile while <50% of the league has joined, then `i` rises, because today the invite needs League Home (a pushed page) or a cold-start banner | Descriptive: size Home reach vs League Home reach from `screen_viewed` for 2 weeks | Invites shared per active user +30% relative over 4 weeks (**assumed**) | Descriptive | entry point `engagement-pm` (D-046 notes five in-screen invite surfaces already exist); decides `growth-pm`; UI `design-lead` | idea | `nav.home_hub` true (FJ:107); `mobile/src/screens/HomeScreen.tsx` has no invite entry |
| 9 | GB-10 | **Rating prompt timing** (S10) | If the 7-day age anchor is minted at first session rather than at first evaluation, then a first successful send can prompt, and ratings volume at launch rises | Code-walk + count `rating_prompt_requested` per first `trade_sent` once a listing exists | ≥ 1 prompt request per 5 first successful sends after the listing (**assumed**) | Descriptive | words and ASO `marketing-lead`; the post-send moment `engagement-pm`; decides `growth-pm` | idea (dormant until a public listing) | `mobile/src/utils/ratingPrompt.ts:34-35` (≥5 sessions, 7-day age), anchor minted on first evaluation (`:42-80`); trigger only on the "Trade sent" OK (`SendInSleeperButton.tsx:244`, `SendInMflButton.tsx:116`, `SendInEspnButton.tsx:157`); `growth.rating_prompt` true (FJ:186) |
| 10 | GB-11 | **Liked-trade share** (S3 caller) | If users can share a liked trade to their league chat, the counterparty is prompted to look | Blocked first: `/s/trade/<id>` is public and enumerable; needs `head-eng`'s fix | ≥ 10% of users with a liked trade share one within 4 weeks (**assumed**) | Descriptive | flag `onboarding-pm`; decides `growth-pm`; security `head-eng` | idea (blocked) | Built, dark: `onboarding.share_sheet` false (FJ:130), `TradesScreen.tsx:472, :8821-8832`; routes S:25552-25564, S:25446-25457 unguarded |
| 11 | GB-05 | **Copy-trade text carries a link** (S11) | If the paste-into-league-chat text carries a league-scoped, flagged, evented link (no username), then the whole league sees a path to the app | Size first: register and fire a copy event for 2 weeks (none exists today) | Copy volume ≥ 20% of `invite_shared` volume (**assumed**) before adding a link | Descriptive | decides `growth-pm`; card `trades-pm`; event `analytics-lead`; words `marketing-lead` | idea | **Why no URL today:** "growth.share_landing owns share attribution … adding a ?ref= link here would widen the attribution surface with no flag and no event", pinned by `check-trade-text.js` case 27 (`mobile/src/utils/tradeText.ts:82-86`). Text ends "(Built with Fantasy Trade Finder)" (`:105`, old brand). Call site `SendInSleeperButton.tsx:157` |
| 12 | GB-07 | **League power-rankings share** (S7) | If a league-wide ranking can be shared, non-users tap to see where their team sits | 5-leaguemate check: ask five non-user leaguemates whether they'd open it | ≥ 3 of 5 say yes (**assumed** bar) before building | n/a | feature `league-pm`; share mechanics `growth-pm`; words `marketing-lead` | idea | `league.power_rankings` false (FJ:198); `web/league-rankings.html` has no share; `web/robots.txt:17` |
| 13 | GB-08 | **Dynasty Year in Review share** (S8) | Season-end per-league superlatives are a league-chat artifact sent to eleven people, ten of them not users | Rides the plan's own phases; nothing to test before P3 | ≥ 1 share per 3 active users in release week (**assumed**) | Descriptive | feature `engagement-pm`; share + landing `growth-pm`; words `marketing-lead` | idea (planned elsewhere) | Not built; P3/P4 Nov–Dec (`docs/business/product/2026-08-13-dynasty-year-in-review-plan.md:338-339`); share moment `:319`; `wrapped_viewed` reserved, never fired (`:413`) |
| 14 | GB-12 | **Re-engagement credit** for existing users who open an invite | If an inviter is credited when a dormant leaguemate returns through their invite, the loop also re-activates | Descriptive, after GB-01 ships: count existing users whose session follows an `invite_link_opened` with `invite_id` | ≥ 10% of invite opens are by existing dormant users (**assumed**) before speccing | Descriptive | retention `engagement-pm`; decides `growth-pm` | idea (needs GB-01) | GB-01 PRD non-goal 3, journey J4 |

### Column rules

- **Hypothesis:** "If <change>, then <metric> moves <direction>, because <mechanism>."
- **Cheapest test:** the smallest thing that could kill the idea; a full build is never it.
- **Success criterion:** one metric, one number, one window, plus its baseline and label.
- **Power pre-check:** a request to `analytics-lead`; >26 weeks means name the alternative.
- **Owner seam:** who decides / builds / writes the words / owns the entry point.

## Share-loop surfaces (S1–S12)

**Canonical numbering, owned by `growth-pm`.** `marketing-lead`'s wave-2 S-IDs
([marketing-inputs.md](../../plans/referral-loop/marketing-inputs.md) §A/§B/§C) are provisional and remap to these (their S1 = `/s/trade` and S2 = `/s/p` are this table's S3 and
S2). The `/?ref=` root fallback is the last rung of S1/S2, not a separate ID. Re-verified at
678834ab.

| # | Surface | Link / CTA | Event | Flag | Backlog |
|---|---|---|---|---|---|
| S1 | Trade-card image (`mobile/src/components/ShareTradeImage.tsx`): PNG + text on iOS (`:144`), text only on Android (`:133`) | URL ladder `/s/p/<id>?ref=<u>` → `/?ref=<u>` → `/` (`mobile/src/utils/shareLinks.ts:86-92, :107-150`) | **GAP** on completion; `share_package_created` at mint (`:170`) | `/s/p` rung needs `growth.share_landing` true (FJ:185) | GB-06, GB-02 |
| S2 | Calculator text share + package landing `/s/p/<id>` (S:25650-25671), `/og/p/<id>.png` (S:25673) | "Build your own: <url>" (`TradeCalculatorScreen.tsx:603`); landing CTA → `/` (S:25669) | `calc_trade_shared` (`:615`), `share_package_created` (`:598`); **GAP** landing view / CTA | `growth.share_landing` true | GB-02, GB-03 |
| S3 | `/s/trade/<match_id>` (S:25552-25564) + `/og/trade/<id>.png` (S:25446-25457) | `?ref=<u>` (`TradesScreen.tsx:5297`); CTA → `/` (S:25563) | `trade_card_shared` (`TradesScreen.tsx:5339`) | Routes unguarded; only caller behind `onboarding.share_sheet` false | GB-11, GB-02; security handoff |
| S4 | Tier board `/s/tiers` (S:25522-25550), `/og/tiers` (S:25415) | username in path | `tier_board_shared` cancelled | `growth.tier_board_share` false (FJ:188) | killed (below) |
| S5 | Shared `/s/*` chrome `_share_html` (S:25460-25520) | never forwards `ref`; every caller `cta_url="/"`; relative `og:image` (S:25485); off-Chalkline CSS (S:25493-25501) | none | — | GB-02 |
| S6 | Send in Sleeper / ESPN / MFL | no link reaches the counterparty | `sleeper_send_succeeded` (S:19404), `trade_sent` (MFL S:32680, ESPN S:33225) | `trade.send_in_sleeper` / `_mfl` true, `espn.send` true | GB-04 |
| S7 | Power rankings (`web/league-rankings.html`) | none | — | `league.power_rankings` false | GB-07 |
| S8 | Dynasty Year in Review | not built | `wrapped_viewed` reserved | — | GB-08 |
| S9 | `/u/<username>` (S:26634) | 404 | — | `profiles.public_pages` false (FJ:24), `profiles.user_toggle` false (FJ:195) | parked (below) |
| S10 | Rating prompt (`mobile/src/utils/ratingPrompt.ts`) | OS review dialog | `rating_prompt_requested` (`:90`) | `growth.rating_prompt` true | GB-10 |
| S11 | Copy trade (`SendInSleeperButton.tsx:157` → `utils/tradeText.ts`) | no URL, on purpose | none | — | GB-05 |
| S12 | Team overhaul "Copy offers" (`OverhaulSummaryScreen.tsx:207`) | no app name or link | none | — | not yet a row; fold into GB-05 if it graduates |

## Killed and parked

| ID | Idea | Status | Date | Why |
|---|---|---|---|---|
| S4 | Tier-board share | killed | 2026-08-11 | Operator ruling D-P1-12: rankings sharing is not a product surface; OFF is the resting state (`living-memory/DECISIONS.md` D-039, tier-board entry) |
| S9 | Public profile pages `/u/` | parked | 2026-10-15 | `profiles.public_pages` off by operator call (#221); not a growth candidate unless reversed |
| — | Waitlist / email capture on the invite landing | killed | 2026-08-12 | Reverted in `65c63479`; no email channel; adds a step |
| — | Attribution SDK (deferred deep link) | parked | 2026-10-15 | Known non-goal (`docs/plans/audit-p0-remediation/prd-p0-3.md:194-201`); GB-01 substitutes re-tap + league match. Revisit only if league-match error is material |

## Changelog

- 2026-10-15 — GB-01 folds `head-product` rulings. P20: v1 ships reward-free (status and
  recognition only); rewards are paid entitlement time, later, gated on the operator
  approving `monetization-pm`'s pricing memo. P9: old-name strings outside the PRD's own FRs,
  including `S:10542-10543`, go to P9's copy-defect batch (`onboarding-pm`, after this wave);
  the old-name cites in GB-02, GB-05 and GB-06 stay as evidence, and their fixes are that
  batch's too.
- 2026-10-15 — Created. Seeded GB-01…GB-14 from growth-pm's invite and share traces (H1–H8,
  S1–S12), re-verified at 678834ab; GB-01 specced as the referral-loop PRD + scope
  (`/pm-growth` loop audit, [loop audit](../../plans/referral-loop/loop-audit.md)).
