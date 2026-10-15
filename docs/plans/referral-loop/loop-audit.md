# Loop audit — L1 invite → join (referral) — 2026-10-15

> Hop-by-hop audit of the league invite loop as it exists on `origin/main`, written before
> the referral-loop PRD ([prd.md](prd.md)) so every requirement there traces to a named
> break here. Format follows `/pm-growth`'s loop-audit mode; hop IDs H1–H8 are kept from
> growth-pm's trace. **Nothing here is evidence that anything shipped** (see
> [`../CLAUDE.md`](../CLAUDE.md)).

**Sha:** `origin/main` 678834ab (2026-10-14 21:31 -0400) · **Workers:** 2 read-only Explore
traces dispatched by `growth-pm` (invite loop H1–H8; share loops S1–S12) · **Spot-checked:**
every `file:line` below was re-opened by the plan writer in a clean worktree at 678834ab ·
**Worker-reported only:** none. The workers' `backend/server.py` line numbers were read at
6bc4602b and sit ~43 lines early on 678834ab; every server line here is re-derived.
**Method:** read-only code trace; no app run, no simulator, no prod data (D-056). Every
rate is **unmeasured** until `analytics-lead`'s W3 baseline lands.
**Owner:** `growth-pm`. **Date:** 2026-10-15.

## Contents

- [Hop model used here](#hop-model-used-here)
- [Loop map: L1 invite → join](#loop-map-l1-invite--join)
- [K-factor read](#k-factor-read)
- [Breaks, ranked](#breaks-ranked)
- [What it takes to compute invites → opens → joins → activated per inviter today](#what-it-takes-to-compute-invites--opens--joins--activated-per-inviter-today)
- [Intended but unbuilt](#intended-but-unbuilt)
- [Non-user view: the H3a join path](#non-user-view-the-h3a-join-path)
- [Share loops (S1–S12)](#share-loops-s1s12)
- [Contradictions found in re-verification](#contradictions-found-in-re-verification)
- [Decisions needed](#decisions-needed)
- [Handoffs](#handoffs)

---

## Hop model used here

The skill's seven hops, mapped to the IDs the trace already uses:

| This audit | Skill hop | Question |
|---|---|---|
| H1a–H1g | H1 Actor acts | Which surfaces let a user invite, and is each one measured? |
| H2 | H2 Artifact leaves | What link and text leave the app? |
| H3a / H3b | H3 Non-user sees + H4 Opens | What the recipient sees and where the tap lands, split by app **not installed** (a) / **installed** (b) |
| H4 | H5 Joins (league pin) | Does the invited league become active? |
| H5 | H5 Joins (sign-in + attribution) | Is the inviter credited, on every platform? |
| H6 | H6 First value | Does the invitee reach trade suggestions, and is that tied to the inviter? |
| H7 | H7 Sharer told | Does the inviter learn it worked? |
| H8 | (added) Measurement | Can anyone read the loop per inviter? |

Verdicts: **works**, **leaks** (works with a loss you can name), **breaks**, **unmeasured**
(may work; no event can tell).

## Loop map: L1 invite → join

Flags are `config/features.json` (FJ) at 678834ab. Events are client `track()` unless marked
server. "S" = `backend/server.py`.

| Hop | What happens | Code (file:line) | Event (emitter file:line) or GAP | Flag (value) | Verdict |
|---|---|---|---|---|---|
| **H1a** League Home card + inline link | "N of M leaguemates haven't joined yet" + Share, on the pushed League Home page (not the League tab root) | `mobile/src/screens/LeagueScreen.tsx:490-494` (shareInvite, `surface: 'league_home'`) | `invite_cta_shown` (`LeagueScreen.tsx:329`) → `invite_cta_tapped` → `invite_shared` (`InviteLeaguematesBanner.tsx:127, :135`) | none | **works**. Card and inline link both report `league_home`, so they can't be told apart |
| **H1b** Members overlay footer | Invite action | `LeagueScreen.tsx:1003-1012` (`surface: 'members_overlay'`) | tapped + shared; **GAP** no `invite_cta_shown` | none | **unmeasured** impressions |
| **H1c** Matches mutual-empty | Invite block; primary when <50% joined | `mobile/src/screens/MatchesScreen.tsx:930-934` | `invite_cta_shown` (`:974`) is a mount counter, not an impression (`backend/analytics_taxonomy.py:1302-1308`); tapped, shared | none | **leaks** (shown inflated) |
| **H1d** Bell empty state (D-046) | Invite ask when the inbox is empty and <50% joined | `mobile/src/components/TopBar.tsx:289-293` | `notif_empty_state_shown` (`:265`) + `invite_cta_shown{notif_empty}` (`:276`), tapped, shared | none | **works** |
| **H1e** Trades cold-start banner | "0 of N league-mates have ranked" + Invite | `mobile/src/screens/TradesScreen.tsx:570, :7051-7057`; `mobile/src/components/InviteLeaguematesBanner.tsx:142-156` | tapped + shared; **GAP** no shown event; `platform: 'unknown'` hard-coded, counts `null` (`:151-153`) | none | **leaks** |
| **H1f** Home hub | No invite entry anywhere on Home (`mobile/src/screens/HomeScreen.tsx` has no invite reference). `onboarding.share_sheet` shares a liked *trade*, not an invite (`TradesScreen.tsx:472, :8821`) | — | — | `onboarding.share_sheet` false (FJ:130) | **gap** (no surface) |
| **H1g** Web invite modal | Per-channel share grid (Email, SMS, WhatsApp, Telegram, X, GroupMe, Sleeper, Copy), opened from `web/js/app.js:3056, :6291` | `web/js/app.js:5822-5835` (URL + message), `:6018-6036` (grid), `:6130-6136` (`shareVia`) | **GAP**: no `FTFTrack` call anywhere in the invite modal | none | **unmeasured** |
| **H2** Link built | Text "Join me on Dynasty Trade Finder to find trades in <league> → URL" (old brand, D-057). URL: `https://fantasy-trade-finder.onrender.com/?league=<id>&ref=<sleeper username>`; path form `/app/league/join/<id>?ref=<u>` only when the flag is on | `InviteLeaguematesBanner.tsx:56-65` (`buildInviteUrl`), `:119-140` (`shareInvite`), text `:132`; web `app.js:5822-5835` (same shape, same old brand) | `invite_cta_tapped` fires before the sheet (`:127`); `invite_shared` only if the sheet is not dismissed (`:134-135`) | `growth.invite_join_link` false (FJ:190) | **leaks**: `ref` is a raw, mutable Sleeper username (PII in every URL and log), dropped when unknown (`:58`); no per-share id |
| **H3a** Opened, NOT installed | Path form 302s to `/?league=&ref=`; the generic `/` loads with generic OG (no league name, **no `og:image`**, `web/index.html:6-14`); the auth card shows "Invited by @ref". **On a phone, web sign-in cannot complete:** browser sign-in needs the desktop Fleeced extension (`web/js/browser-auth.js:1`, fails `extension_unavailable` after 2 s at `:45`), called unconditionally (`app.js:334`); ESPN/MFL web sign-in is "not available … yet" (`app.js:1262-1266`). No TestFlight or App Store link exists anywhere (`living-memory/NEXT.md:145-148`) | 302: `S:12596-12624`; capture: `app.js:6390-6416`, called at `:6723` | **GAP**: the 302 logs nothing; web fires no `invite_link_opened` and no pin event | none (302 unflagged) | **breaks** for every phone invitee; desktop works only with the extension |
| **H3b** Opened, installed | Universal link opens the app. Legacy form: intent saved, **no screen change** for a signed-in user (`deepLinks.ts:444` bare-path return). Path form: LeagueJoin → SignIn or LeaguePicker | AASA `S:12633-12682` (claims `:12668-12678`, unflagged); `mobile/app.json:8` (scheme `dtf`); `mobile/src/utils/deepLinks.ts:396-438`, route `:119`; `mobile/src/screens/LeagueJoinScreen.tsx:50-111` | `invite_link_opened{league_id, has_ref, format, auth_state}` (`deepLinks.ts:426-438`, `LeagueJoinScreen.tsx:77-82`): **no inviter identity**, only `has_ref` | `ux.deeplink_router_v2` true (FJ:166) | **leaks**: every link today is legacy form, so a signed-in invitee is not routed; pin waits for the picker to open |
| **H4** League pin | LeaguePicker auto-pins the invited league, or shows the platform-neutral not-member notice ("join it on your fantasy platform and open the invite again", `LeaguePickerScreen.tsx:568-571`) | `mobile/src/screens/LeaguePickerScreen.tsx:234-253`, `:261-279`; intent `mobile/src/state/useSession.ts:44-45` (14-day TTL), `:491-559` | `invite_league_pinned{picker_autopin}` (`:245`), `invite_pin_failed{not_member}` (`:273`) | none | **works** on mobile; web auto-select (`app.js:436-441`) is **unmeasured**; ESPN/MFL invitee pins only after linking that platform |
| **H5** Sign-in + attribution | SignIn banner "@ref invited you to <league> —…" (`mobile/src/screens/SignInScreen.tsx:229-235`, `:584`; name via `mobile/src/api/league.ts:953-975` → `S:26445-26482`). `invited_by` rides `/api/session/init` from the two **Sleeper** mobile builders (`mobile/src/api/auth.ts:494-515`, `:590-608`) and web (`app.js:810`); the ESPN/MFL/Fleaflicker builders send nothing (`auth.ts:442-456`). Server reads it (`S:22185`), writes `users.invited_by` **on INSERT only** (`S:22594-22604` → `backend/database.py:5122-5156`; column `:462`, a username string) | as cited | server `signup` (`S:22619-22630`) with **no props**; `signin_*` carry no invite context | none | **leaks**: credit lost for ESPN/MFL/Fleaflicker joins, inviters without a username, renamed inviters, and inviters whose last session was on web (web sends `username: user.display_name`, `app.js:801`, so `get_user_by_username` misses). **Spoofable**: any crafted `?ref=` is accepted |
| **H6** First value | Rank, then deck. Funnel stage 5 "activated" = `ranking_complete_first_time`; stage 6 `first_suggestions` = `trades_generated` (`backend/analytics_queries.py:413-414`), server-fired at `S:7617` and `S:9233-9238` | as cited | standard events, **no invite context** | — | **unmeasured** as a loop hop: nothing ties invitee value to the inviter |
| **H7** Inviter told | Inbox row "@x joined Fantasy Trade Finder via your invite." (old brand) at signup, not at value; title = body (`database.py:12620-12634`) and the bell renders both (`TopBar.tsx:499-501`), so the sentence shows twice. The inviter, as a joined leaguemate, **also** gets the `league_member_joined` coalesced row + push (`S:22677-22720`) | `S:22649-22675` (needs a new user, `invited_by`, and a username that resolves, `database.py:12597-12617`); tap routes to League (`deepLinks.ts:300-312`) | **GAP** server-side: no `record_event`, no `push_sent`; client only `notif_row_tapped{type}` | row unflagged; activity line "joined via @x's invite" (`database.py:9034`) behind `league.activity_feed` false (FJ:18) | **leaks**: fires at signup not activation; inbox only (no push, GD-5 Phase 2); notified twice; spoofable via `ref` |
| **H8** Measurement | "Your invite impact" in the web invite modal only | `S:26220-26307`; `database.py:13212-13290`; `app.js:5860-5990` | — | `invite.k_factor_dashboard` false (FJ:20) → zeroed payload | **breaks**: "k_factor" = `float(count of users whose invited_by is me)` (`S:26271`); invited ≡ joined; "active" = ≥1 `swipe_decisions` row; no mobile consumer, no admin panel, no invite query in `analytics_queries` |

**Registry facts behind the Event column.** Six invite names are registered
(`analytics_taxonomy.py:139-140`, `:258`; props `:1154-1161`, `:1309-1312`). Only
`invite_cta_shown` is NON_INTENT (`analytics_queries.py:160`). Sleeper `league_id` props were
stored `[scrubbed]` until the G-036 fix (`backend/analytics_ingest.py:167-181`), so any
history before 2026-08-12 has no league. **Any client prop key containing `token` is dropped
at ingest** (`analytics_ingest.py:160`, `:195`), which constrains the PRD's prop naming.

## K-factor read

`K = i × c`, with `c = p(open | shared) × p(join | open) × p(activated | joined)`.

| Term | Today's source | Status |
|---|---|---|
| `i` (invites shared per active user per period) | `invite_shared` on five mobile surfaces; **web sends nothing** (H1g) | **unmeasured**: query pending `analytics-lead` (W3); mobile-only lower bound at best |
| `p(open)` | `invite_link_opened` (app opens only) ÷ `invite_shared` | **unmeasurable today** for not-installed recipients: the 302 and web log nothing (H3a) |
| `p(join)` | new users with `users.invited_by` ÷ opens | **partially measurable**, Sleeper only, username-joined (H5 leaks) |
| `p(activated)` | invited cohort reaching stage 6 | computable by joining `users.invited_by` to `trades_generated`; **pending `analytics-lead`** |
| K in-product | `/api/invite/impact` | dark and mislabelled (H8) |

**K today: unknown.** No term above is a measured number at this sha. The PRD's targets are
labelled **assumed** until the W3 baseline lands.

## Breaks, ranked

Ranked by downstream cost (a break zeroes everything after it) and cost to fix.

| Rank | Hop | Break | Downstream cost | Fix: decides / builds / words | Backlog row |
|---|---|---|---|---|---|
| 1 | H3a | **Not-installed phone invitee dead-ends.** Web sign-in needs the desktop extension; no install CTA exists; an install loses the invite (no deferred deep link, `docs/plans/audit-p0-remediation/prd-p0-3.md:194-201`) | Every phone invitee without the app (most of them: invites travel in phone chats) | decides `growth-pm` + operator (CTA A/B/C); builds `engagement-eng` (join landing, invite route), `onboarding-eng` (web capture); words `marketing-lead` (`gp.join.*`, proposed) | GB-01 (PRD FR-7…FR-11) |
| 2 | H5 | **Attribution is a username string**, Sleeper-only, first-row-only and spoofable | Credit lost or forged; the loop can't be read per inviter | decides `growth-pm`; builds `engagement-eng` (server), `onboarding-eng` + mobile (session-init bodies); `platforms-pm` reviews ESPN/MFL membership | GB-01 (FR-1, FR-2, FR-12…FR-16) |
| 3 | H3a/H1g/H8 | **Web leg silent end to end** (302 logs nothing; no web invite events) | Opens and web-originated invites invisible | decides `growth-pm`; events `analytics-lead`; builds `onboarding-eng` | GB-01 (FR-5, FR-8, FR-9) |
| 4 | H6/H7 | **Inviter told at signup, not value; told twice; spoofable**; no server event | Weak reinforcement; noisy bell; forged rows | decides `growth-pm`; rules `engagement-pm`; words `marketing-lead` (`gp.push.*`, proposed) | GB-01 (FR-17…FR-20) |
| 5 | H8 | **Measurement dark and mislabelled** ("k_factor" is a join count, and "K-factor" already means the Elo update size in `docs/glossary.md:29`) | No one can see the loop | decides `growth-pm`; readout `analytics-lead` | GB-01 (FR-21, FR-22) |
| 6 | H3b | **Legacy link + signed-in user doesn't route** (`deepLinks.ts:444`) | Installed, signed-in invitees land nowhere new | operator runs the #239 device checklist, then flip `growth.invite_join_link` | GB-01 Phase 0/1 |
| 7 | H1 | **Impressions uneven** (H1b, H1e no shown event; H1c mount counter; H1e wrong props) | Tap rates per surface can't be compared | builds mobile; classification `analytics-lead` | GB-01 (FR-4) |
| 8 | H2/H7/H3a | **Old brand strings** in the invite text (mobile and web), inbox row, `/s/*` chrome | Recipient sees a name that isn't the app's (D-057) | words `marketing-lead` | GB-01 (FR-3, FR-18), GB-02 |

## What it takes to compute invites → opens → joins → activated per inviter today

- **Invites:** `user_events` rows `invite_cta_tapped` / `invite_shared` (user_id = inviter; props
  `surface`, `league_id` on `invite_shared` only). Mobile only; `league_id` usable only after
  G-036 (2026-08-12).
- **Opens:** `invite_link_opened`. Pre-sign-in rows are `device:` ids, resolved to the invitee
  through `identity_links` (`analytics_queries.py:452-470`). The **inviter** can only be
  guessed by matching `league_id` and a time window against `invite_shared`, which is
  ambiguous once two people in a league share. Web opens: none.
- **Joins:** `users.invited_by` (case-insensitive username) ↔ inviter `users.username`; time
  from `users.created_at` or the server `signup` row.
- **Activated:** invitee `trades_generated` (stage 6) or `ranking_complete_first_time`
  (stage 5) joined through `invited_by`.
- **Missing, and what the PRD adds for each:** a per-share id in the URL and on open/pin
  events (FR-1, FR-2, FR-10); web invite events and a server record of the landing open
  (FR-5, FR-8, FR-9); a server attribution event (FR-13, FR-16); attribution keyed on user ids,
  not usernames (FR-13); attribution on ESPN/MFL/Fleaflicker session-init (FR-12); a writer
  for the existing `referrals` table (`database.py:2595-2617`), which already models
  referrer, referred, league, token, `joined_at`, `activated_at` (FR-13…FR-17).

## Intended but unbuilt

| Item | Where it was intended | State |
|---|---|---|
| Deferred deep link / attribution SDK | Explicit non-goal, `prd-p0-3.md:194-201` | Still a non-goal; the PRD substitutes a re-tap step and league-match fallback |
| Give-get referral program `growth.referral` | `prd-p0-3.md:213`; ledger schema `database.py:2595-2617` (pending → joined → activated → rewarded) | Flag declared, read nowhere (`backend/feature_flags.py:268`); table has no writer (only delete/export in `backend/accounts.py:829-838, :1043-1044`); `promo_referral` / `promo_group_unlock` entitlement sources never granted (`backend/entitlements.py:50`) |
| Flip `growth.invite_join_link` | `config-reference.md:669`; operator decision `NEXT.md:194` | Device checklist pending: `docs/feedback/items/239-invite-universal-links/status.md` § Operator actions, item 4 |
| `referral_joined` APNs push | GD-5 Phase 2, `NEXT.md:532` | Not built; `engagement-pm` seam |
| ESPN/MFL invites | `prd-p0-3.md:207-211`; web dead end `PRD-p1-5.md:111-118` | The LeaguePicker copy half is **already fixed** (`LeaguePickerScreen.tsx:568-571`); the web dead end remains (`app.js:1262-1266`) |
| Named-leaguemate invite ("Dave, Priya and 7 others") | `PRD-p1-5.md:198` | Not built → backlog GB-13 |
| Invite copy A/B | Deferred OG-10, `PRD-p1-5.md:196` | Underpowered at beta scale (GB-01 power note) |
| Manual universal-link / 302 device checks | `prd-p0-3.md:290-293` | Never automated; still the operator's checklist |

## Non-user view: the H3a join path

`/pm-growth` non-user checklist, filled for **today's** surface (the 302 into `/`):

| # | Check | Today | Evidence |
|---|---|---|---|
| 1 | OG title | "Fleeced — Dynasty Trade Finder": shipped name, but says nothing about the invite or league | `web/index.html:11` |
| 2 | OG image | **None** (no `og:image` on `/`) | `web/index.html:6-14` |
| 3 | OG description | Generic product line | `web/index.html:12` |
| 4 | Unfurl renders | `/` is crawlable (`web/robots.txt:3`); unfurlers follow the 302 to it | `S:12596-12624` |
| 5 | CTA text | No invite-specific CTA; the sign-in card | `app.js:6408-6416` |
| 6 | CTA target | `/` sign-in: a dead end on phones (extension-only) | `browser-auth.js:1, :45`; `app.js:334` |
| 7 | Act without installing | Desktop with the extension only; ESPN/MFL never | `app.js:1262-1266` |
| 8 | Install-state branches | Installed: AASA opens the app. Not installed: no store/TestFlight path | `S:12668-12678`; `NEXT.md:145-148` |
| 9 | Attribution carried | `ref` + `league` to localStorage, sent as `invited_by` (Sleeper web only); lost on any app install | `app.js:6390-6403`, `:810` |
| 10 | Events | None on web, none on the 302 | H3a row |
| 11 | Indexing intent | `/` is meant to be indexed; a per-league join page is not (none exists) | `web/robots.txt` |
| 12 | Privacy | Raw username in the URL and in Render logs; spoofable `ref` | `InviteLeaguematesBanner.tsx:56-65`; `S:22649-22675` |
| 13 | Words owner | No invite-specific words exist; `marketing-lead` has drafted `gp.join.*` (proposed, pending) | marketing-lead wave 2 §A |
| 14 | Shipped name | Page title/OG correct; invite text, inbox row and `/s/*` chrome wrong | `InviteLeaguematesBanner.tsx:132`; `S:22662`; `S:25479, :25512` |

## Share loops (S1–S12)

The share-loop surfaces (trade-card image, `/s/p`, `/s/trade`, `/s/tiers`, the shared `/s/*`
chrome, send-in-league, power rankings, Year in Review, `/u/`, rating prompt, copy trade,
overhaul copy) are traced in the standing backlog:
[`docs/business/product/growth-backlog.md` § Share-loop surfaces](../../business/product/growth-backlog.md#share-loop-surfaces-s1s12).
That S1–S12 numbering is canonical; `marketing-lead`'s wave-2 S-IDs are provisional and
remap to it.

## Contradictions found in re-verification

Recorded so nobody acts on the stale version. None changes a PM decision silently; each is
carried into the PRD as written by the code.

1. **Server line numbers.** The traces' `server.py` lines were read at 6bc4602b; on 678834ab
   they are ~43 lines later (302 at `:12596`, not `:12553`; session init `:22153`; the
   `referral_joined` row `:22649-22675`; impact `:26220-26307`).
2. **Web does send `invited_by`** on its (Sleeper-only) session init (`app.js:810`). The
   statement "only Sleeper sends `invited_by`" holds per platform, not per client: the
   non-sending builders are mobile ESPN/MFL/Fleaflicker (`auth.ts:442-456`).
3. **LeaguePicker not-member copy is already platform-neutral** (`LeaguePickerScreen.tsx:568-571`);
   the `PRD-p1-5.md:111-118` follow-up is half done. The web dead end for non-Sleeper invitees
   is still open.
4. **A server event cannot reuse the name `invite_link_opened`.** Client and server namespaces
   must be disjoint; `analytics_taxonomy.py` refuses to import on a collision
   (`analytics_taxonomy.py:21-23`, enforced at `:1757-1781`). The PRD names the server event `invite_landing_opened`.
5. **`record_event` cannot write `platform='server'`** and **bumps the owner's
   `users.last_active_at` and `events_count`** on every row (`database.py:4389-4466`). A
   server event owned by the inviter would make a dormant inviter look active to the cron
   ticks that read `last_active_at` (`database.py:14226-14243`). The PRD requires a
   non-touching write path.
6. **Stage 6 is `analytics_queries.py:414`** (stage 5 is `:413`), and the funnel already names
   stage 5 "activated" (`:413`), which collides with "referral activated" at stage 6.
7. **`check-*.js` suites do gate CI** (`.github/workflows/ci.yml:47`); root `CLAUDE.md`'s
   "gate nothing yet" is stale.
8. **Doc drift outside this folder:** `NEXT.md:552` (0g, "only the banner emits `invite_shared`")
   is stale since `3ade8f28`; `NEXT.md:526` still calls notif-inbox Phase 1 unmerged though its
   TopBar empty state is on main; `living-memory/DECISIONS.md` has two entries numbered D-039.

## Decisions needed

Carried into [prd.md § Decisions needed](prd.md#15-decisions-needed); the operator-only ones:
CTA target A/B/C before the App Store listing; running the #239 universal-link device
checklist; creating a public TestFlight link if A; the reward question (default reward-free).

## Handoffs

- `analytics-lead`: W3 baseline for the nine invite/share events, new accounts per week, and
  open → signup feasibility; the event proposals in [prd.md §10](prd.md#10-events-proposals-for-analytics-lead).
- `head-eng` (security): `/s/trade/<match_id>` (`S:25552-25564`) and `/og/trade/<match_id>.png`
  (`S:25446-25457`) are unguarded and keyed by a plain integer, so any mutual match is
  enumerable. Not in this PRD's build.
- `release-lead` (scribe): the doc drift in contradiction 8.
