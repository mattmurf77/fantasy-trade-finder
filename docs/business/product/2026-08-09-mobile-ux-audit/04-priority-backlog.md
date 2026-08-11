# Master Priority Backlog

> Ranked against **adoption and retention weighted equally**, per the brief. Tiers reflect a launch-gate model, not a severity scale.
>
> | Tier | Meaning |
> |---|---|
> | **P0** | Would measurably suppress adoption or retention on day one. Do not go live. |
> | **P1** | Ship inside the first 30 days. Compounds damage if left. |
> | **P2–P4** | Post-launch backlog, sequenced. |
>
> Every P0 carries a **falsification handle**: the failure mechanism, the evidence, the assumption it rests on, and what would prove me wrong. Review the set, flag what you doubt, and I'll run a targeted refutation pass on only those.

---

# P0 — Launch blockers (8 standing, 1 withdrawn)

> **Operator pass, 2026-08-09.** P0-4 was withdrawn after the operator corrected it — see below. P0-6's falsifier was subsequently checked and does **not** apply (`check_for_match` at `server.py:10011` has no ESPN exclusion), so that finding is firmer than originally graded. Seven of the eight standing blockers are Bugs.

## P0-1 · The default path never completes its own progression, and push permission is the casualty
**[Retention] · Effort S · Confidence high**

**Failure mechanism.** A new user taps Rank, lands on Quick Set Tiers, and completes all 32 steps across four positions. Their board is real and their trades are priced off it. But `progress.unlocked` stays `false` forever — so `pushEnabled` in `RootNav.tsx:264` never becomes true, and **the push-permission prompt never fires**. They also never see the payoff banner they were promised, and their leaguemates see them permanently badged "in progress."

**Evidence.** `ranking_method` is written from only two call sites — `RankHomeScreen.tsx:64` and `SettingsScreen.tsx:231` — neither on the default path (`TabNav.tsx:208-237` routes new users straight to Quick Set). `get_ranking_method` returns `None` when unset (`database.py:3362-3370`). `NULL` falls to the trio branch requiring 40 interactions (`server.py:6172-6174`). Tier saves set Elo overrides without touching `_interactions`.

**Load-bearing assumption.** That most new users take the default route and never visit the Rank Home chooser or Settings.

**What would prove me wrong.** Telemetry showing most users do reach the chooser; or a server-side backfill that sets `ranking_method` on first tier save that I didn't find; or push priming firing through a path independent of `progress.unlocked`.

**Fix.** Write `ranking_method` when a user *uses* a method, not only when they pick one from a chooser. One-line change at the save sites.

---

## P0-2 · A failed trade search is indistinguishable from never having searched
**[Adoption/Retention] · Effort S · Confidence high**

**Failure mechanism.** A user taps Find a Trade. Generation errors server-side. The deck is empty, so the UI falls through to the same state as a fresh screen: *"Hit 'Find a Trade' to start."* The user concludes the product found nothing for them — or that it's broken in a way they can't name — and has no reason to retry.

**Evidence.** `job.error` is populated by the backend and **never read or rendered anywhere in `TradesScreen.tsx`** (6,158 lines, confirmed by full-file grep). The empty-state ladder at `:4910-4918` is reached identically from `status:'error'` and from never-generated.

**Load-bearing assumption.** That generation errors occur at a non-trivial rate in production — on a free-tier Render instance with cold starts and a polling job pattern.

**What would prove me wrong.** Production error rates near zero for `/api/trades/generate`; or an error surface elsewhere in the render tree I missed.

**Fix.** Render `job.error` with a retry affordance.

---

## P0-3 · The invite loop is broken at both ends
**[Adoption] · Effort S–M · Confidence high**

**Failure mechanism.** A user taps "Invite them." The share sheet sends `https://…/?league=<id>&ref=<user>`. The recipient taps it. The app reads `?ref=` for attribution, **never reads `?league=`**, and because the URL has no path, `deepLinks.ts:301-302` explicitly short-circuits: *"Bare open / referral-only URL (no path) — nothing to route, no toast."* The invitee lands on a generic sign-in with no idea who invited them, to what league, or why.

**Evidence.** `buildInviteUrl` at `InviteLeaguematesBanner.tsx:27-31`. No reader for `queryParams.league` anywhere in `mobile/src`. Universal links *are* now correctly configured (`app.json:52`, AASA at `server.py:8075-8108`) — which makes this worse, not better: the entitlement work is done and wasted.

**Load-bearing assumption.** That league-to-league spread is your growth model. Your own strategy doc says it is, and that within-league invitation is really activation.

**What would prove me wrong.** If the web app parses `?league=` and completes the journey there (unverified — `web/` was out of scope); or if invites are not intended as the primary channel.

**Fix.** Give invite links a real path, parse `?league=`, and land the invitee in the inviting league with the inviter named.

---

## ~~P0-4 · A visible, tappable dead end sits under a top-level tab~~ — **WITHDRAWN**
**Retracted 2026-08-09 on operator correction. Mock Draft works.**

`CPU_MODEL_VALIDATED = True` at `backend/mock_draft_service.py:294`, flipped by explicit operator override on 2026-08-06. `start_refusal` therefore never returns `cpu_model_unvalidated`, and the create route serves a real mock.

**How the error happened.** I trusted two secondary sources instead of the authority. The `_comment_draft_extensions` block in `config/features.json` still says the mock "stays OFF" and that the create route answers the typed-empty refusal — both untrue since the override. I saw the client's refusal branch and inferred it fired. `mock_draft_service.py` was outside the pinned snapshot, so I never read the constant that decides it.

Kept in place rather than deleted so the correction stays on the record. **Residual finding tracked as A-33 (P1):** the config comment asserts the opposite of runtime behaviour.

---

## P0-5 · A whole sign-in branch strands users with no league
**[Adoption] · Effort S · Confidence high**

**Failure mechanism.** A brand-new user signs in with Apple. No Sleeper account is bound, so the server returns `account_only`, pins a `no_league` sentinel, and the client routes **straight to the tabs** — skipping league selection. Every league-scoped surface is empty. The only route out is Settings.

**Evidence.** `_mint_account_only_session` (`server.py:17913-17949`), client handling at `SignInScreen.tsx:167-184`, routed via `onAccountSignedIn` → `replace('Main')` (`RootNav.tsx:398`).

**Load-bearing assumption.** That new users will choose Apple — reasonable, since it's the primary button.

**What would prove me wrong.** If nearly all real sign-ups arrive via Sleeper username, making this branch rare.

**Fix.** Route `account_only` users into league linking immediately.

---

## P0-6 · Matched ESPN users have no action, and aren't told why
**[Retention] · Effort S · Confidence high**

**Failure mechanism.** An ESPN-league user reaches a mutual match — the emotional peak of the product. `SendInSleeperButton` renders `null` with no message. The only remaining action is Dismiss. The payoff of the entire loop is an archive button.

**Evidence.** `SendInSleeperButton.tsx:59-66,273` excludes `platform==='espn'` silently. `setMatchDisposition` (accept/decline) exists in the API layer and is **never called anywhere in `mobile/src`**.

**Load-bearing assumption.** That ESPN users reach matches. ESPN linking is live and promoted on two screens.

**What would prove me wrong.** If ESPN leagues can't produce matches at all upstream — in which case the finding moves earlier in the funnel, not away.

**Fix.** Explain the limitation and give a fallback (copy trade details, deep-link to ESPN).

---

## P0-7 · You will be blind on launch day
**[Adoption/Retention] · Effort M · Confidence high**

**Failure mechanism.** Traffic arrives. Something underperforms. You cannot tell which tab people use, whether they finished a board, whether a match converted to a send, or where they dropped — because none of it is instrumented client-side.

**Evidence.** Zero `track()` on: tab-bar taps (`TabNav.tsx`), all of `LeagueScreen.tsx` and `LeagueSummaryScreen.tsx` (and no server `record_event` for those routes either), tier saves, trio submits, and `SendInSleeperButton.tsx` — the last of which is **genuinely blind on both client and server**, its only side effect being a `deck_outcomes` write. Fifteen of nineteen Tier B units have zero client events.

**Nuance, and a correction to my own earlier statement.** Swipe disposition, trade-generation completion, tier saves and trio submits *are* captured server-side via `record_event` (`server.py:9988-10007`, `:5231-5236`, `:7387-7397`, `:5971-5981`). They are measurable. The genuinely unmeasurable set is smaller than it first appears: Send-in-Sleeper, all League surfaces, and all navigation.

**Load-bearing assumption.** That you intend to diagnose and iterate post-launch rather than ship and wait.

**What would prove me wrong.** If server-side events plus route observability already answer your launch questions — worth checking before building anything.

**Fix.** Instrument navigation, League surfaces, and Send-in-Sleeper. Three targeted additions, not a program.

---

## P0-8 · The guided tour tells users it's over before it has begun
**[Adoption] · Effort S · Confidence high**

**Failure mechanism.** A user's first "like" fires the celebration beat `s6.1`. In the *same chain tick*, `s8.1` fires — the tour's sign-off, *"That's the tour…"* — and calls `completeTour()`. The user is told guidance has concluded having received none: no sign-in help, no swipe coaching, no provenance explanation, no Quick Set pitch. Nine of fifteen scripted steps are structurally unreachable.

**Evidence.** `TradesScreen.tsx:3129` (s6.1, gated only on `guidedAvatarActive()`), chain effect at `:2456-2459` (s8.1), `useGuide.ts:137-141` (`completeTour`). Nine steps blocked by `onboarding.*` sub-flags that are all false while `onboarding.v2` is true.

**Load-bearing assumption.** That `onboarding.guided_avatar` stays on at launch while its siblings stay off.

**What would prove me wrong.** A launch flag config differing from `config/features.json` — worth confirming, since experiment overlays can differ per device.

**Fix.** Either turn the guided layer on, or gate `s8.1` on having actually shown a tour.

---

## P0-9 · A new user's first act is a 32-tap chore, before seeing anything of value
**[Adoption] · Effort M · Confidence medium-high**

**Failure mechanism.** Sign in, pick a league, land on Quick Set Tiers at QB, tier 1 of 8. No trade has been seen. No explanation of why this matters beyond one hint line. The structural minimum to finish all four positions is 32 save/continue taps plus player selections. The trades-first alternative is built and disabled.

**Evidence.** Launch-route resolution at `TabNav.tsx:208-237`; effort arithmetic from the ranking evidence pass; `onboarding.trades_first: false`.

**Load-bearing assumption.** That first-session drop-off is sensitive to time-to-first-value — the standard finding, but unmeasured here.

**What would prove me wrong.** This is the P0 I hold most loosely. If your TestFlight users completed the walk happily, the ordering may be fine and the real problem is only that it's unexplained. **This is the one I'd most want pressure-tested before you act on it.**

**Fix.** Show a trade first. At minimum, let one position's worth of ranking visibly improve the deck, then invite the rest.

---

# P1 — Launch window, first 30 days (12)

| # | Finding | Lever | Effort |
|---|---|---|---|
| P1-1 | **Shared trade images carry no URL.** `ShareTradeImage` shares a bare PNG — the most screenshot-worthy artifact in the app with no way back into it. | [A] | S |
| P1-2 | **Two complete share landings have zero callers.** `/s/tiers/<pos>/<username>` and `POST /api/share/package` + `/s/p/<id>` are built, live, and OG-imaged server-side; nothing in the app calls them. The calculator even carries a stale comment saying the route doesn't exist. | [A] | S |
| P1-3 | **No email capture and no email infrastructure at all.** Zero SMTP/SES/SendGrid anywhere. Every re-engagement path is push-only — and push permission is currently blocked for default-path users (P0-1). | [R] | M |
| P1-4 | **Adjustments are never itemized.** A consolidation premium is applied and never explained. DynastyDealer, FPTrack, Dynasty Daddy and DTC all publish theirs. Most-cited competitive gap in your own docs. | [A] | M |
| P1-5 | **Invite is a text link inside a module, three taps deep, on an unmeasured page.** Promote it, and use the member data you already have: *"8 of your 11 leaguemates haven't joined."* | [A] | M |
| P1-6 | **Streaks reward nothing.** Computed, displayed, leaderboarded — no unlock, badge, or benefit attached. | [R] | M |
| P1-7 | **Pick Anchors can never unlock, and its labels contradict the tier ladder** ("4 1sts" vs "4+ 1sts", "No value" vs "FA") in the app's core vocabulary. | [A/R] | S |
| P1-8 | **Manual unlocks unconditionally on one chooser tap** with zero board changes — the inverse incoherence to P0-1. | [A/R] | S |
| P1-9 | **No new-trade notification.** The push system is well built and isn't used for the highest-value trigger it enables. | [R] | M |
| P1-10 | **Sleeper Connect has zero analytics** while gating the app's most consequential action. Its ESPN twin has four events. | [A] | S |
| P1-11 | **Draft tab is on out of season** and "Acquire" is invented vocabulary for the core verb. Both spend prime real estate. | [A] | S |
| P1-12 | **Sleeper write path is ToS-adverse and live.** `trade.send_in_sleeper: true` against an undocumented private GraphQL API, while every doc describes it as default-off. *(Note: the `/api/trades/propose` route is hard-gated on session verification at `server.py:12197` with no grace period — this is a business-continuity risk, not a security hole.)* | [R] | S |

---

# P2 — Near-term backlog (14)

Public no-login web calculator (the front door every web competitor has) · Turn on `outlook.odds` (playoff odds — your self-named #1 competitive gap, built and dark) · Starters/bench league-wide recompute (DynastyGM's signature move) · Player detail pages (**you have none; every competitor does**) · Public profiles turned on and linked (429 lines, zero entry points) · Multi-key pool sort on ranking surfaces · Post-trade impact preview · Portfolio exposure percentages and league context · Long-press affordance visibility on trade cards · Expand "Why?" by default · `RookieRanks` and Quick Rank chooser entries · Promote Trends (most habit-forming content, buried) · Named trade scenarios · Delete `TradeFinderHubScreen`, `PlaceholderScreen`, `TradeMeter` (1,656 lines of dead code).

# P3 — Medium-term (10)

Real-trade history feed · Searchable trade database · Contrarian share units ("you're highest on X in your league") · Community-comparison beat in Trios · Rank-movement notifications · Free-agent match notifications · Discord bot (your growth doc calls this channel under-occupied) · Three-way trades (built, flag off) · Maestro coverage for the seven uncovered screens · Consolidated platform-account hub.

# P4 — Later / opportunistic (6)

Redraft mode · Rankings marketplace · Android universal links · Value-source compare view · Scouting/athleticism data · Fleaflicker (built, off).

---

# The one-paragraph version

Nine things stand between you and a launch you'd be happy with, and **eight of the nine are small**. They are not architecture problems — they're last-inch problems: a rendered error state, a URL parameter, a flag decision, three analytics calls. The one genuinely structural item (P0-9, the 32-tap first session) is also the one I'd want you to pressure-test before acting on. Everything in P1 and below is a real product with real competitive standing that needs distribution mechanics it does not currently have.
