# Tier A Briefs — Full Six-Criteria Treatment

> 14 units a user lives in. Each gets: description, strengths, shortfalls, six criteria with a grade and three ranked changes, then a holistic page priority across all eighteen changes.
> Tier tags on changes: **P0** launch blocker · **P1** first 30 days · **P2–P4** post-launch backlog. Levers: **[A]** adoption · **[R]** retention · **[A/R]** both. Effort: S/M/L.

---

## 1. Sign-in — **B−**

**What it is.** The app's only front door. Sign in with Apple is primary; a Sleeper-username field is secondary. No password, no email, no account creation. Three outcomes: Apple `linked` → League Picker; Apple `account_only` → straight into the tabs with a `no_league` sentinel; Sleeper username → League Picker.

**Strongest details.** The username-only path is the lowest-friction sign-in in the category — one typed field, no password, no verification email, and the app remembers the last username in Keychain for a one-tap return. Apple sign-in is properly implemented with a real re-auth notice when a session expires. The legal line is present and correct. Competitors either require a real account (DynastyGM) or capture a full-account Sleeper JWT at the door (DynastyDealer); FTF does neither.

**Shortfalls.** The Apple `account_only` branch drops a brand-new user into the app with no league and no path to one except Settings — a dead end at the moment of highest intent. Error copy is generic by default: the friendlier "No @x on Sleeper. Usernames aren't team names" message is gated behind `onboarding.landing`, which is off. There is no demo or try-before-sync escape (both `landing.*` flags off), so a user who hasn't decided yet has only one move: hand over an identity. And on a cold Render dyno this screen shows a bare button spinner for what the code itself documents as 30–60 seconds, with no explanatory copy.

| Criterion | Grade | Strength → Shortfall |
|---|---|---|
| **Usability** | **B** | Three sign-in outcomes all land somewhere sane → but `account_only` lands in a leagueless app with no in-context recovery. |

1. **P0 · [A] · S** — Give `account_only` users an immediate league-linking step instead of dropping them into empty tabs. Today the highest-intent moment routes to a dead end.
2. **P1 · [A] · S** — Add cold-start copy to the sign-in button's busy state. The League Picker already does this at 4s; this screen, which is hit first, does not.
3. **P2 · [A] · S** — Ungate the specific error copy from `onboarding.landing` so a mistyped username explains itself.

| **Simplicity** | **A−** | One field, no password, no email — genuinely the least friction in the category → the only cost is that it asks for identity before showing any value. |

1. **P1 · [A] · M** — Turn on a demo/sample-league path (`landing.try_before_sync` exists and is off). Every web competitor lets you use the calculator before identifying yourself.
2. **P2 · [A] · S** — Accept a pasted Sleeper league URL as well as a username (`landing.smart_start_cta`, built, off).
3. **P3 · [A] · S** — Show the "Continue as @x" Keychain hint more prominently on reinstall.

| **Retention** | **C** | Persistent sessions and Apple re-auth mean returning users rarely re-authenticate → but the screen captures nothing that lets you reach a user who leaves. |

1. **P1 · [R] · M** — Capture email at the Apple step. `auth.email_capture` is off and there is **no email infrastructure in the codebase at all**; a launch with zero reachable addresses is a launch with no second chance.
2. **P2 · [R] · S** — Persist the last-used sign-in method so returning users see one button, not a choice.
3. **P3 · [R] · S** — Record a `signin_abandoned` signal; today drop-off before submission is invisible.

| **Replicability** | **C** | Apple + username-only is a sensible pattern → it is also a two-day build for anyone. |

1. **P3 · [A] · S** — Nothing here is defensible; don't invest in differentiating it. Keep it fast and get out of the way.
2. **P4 · [A] · S** — The Keychain-remembered username is a small nicety worth keeping.
3. **P4 · [A] · S** — Consider making the demo league genuinely distinctive if you ship it; a good sample league is a real differentiator.

| **Competition** | **B+** | Lower friction than DynastyGM (real account) and safer than DynastyDealer (2FA token capture at the door) → but three competitors need no sign-in at all to deliver core value. |

1. **P1 · [A] · M** — Match the field's "use it before you join" norm via the demo path.
2. **P2 · [A] · S** — Name the platform support on-screen; ESPN/MFL users currently discover support only after signing in.
3. **P4 · [A] · S** — Consider a web calculator as the top-of-funnel front door the field uses; FTF has none.

| **Growth** | **D** | The screen accepts `?ref=` attribution → and that is the entirety of its growth function. |

1. **P0 · [A] · M** — Make an invited user's arrival mean something. Today a tapped invite carries `?ref=` and `?league=`; the app reads only `ref` and a bare no-path URL explicitly routes nowhere. An invitee lands on a generic sign-in with no idea who invited them or to what.
2. **P1 · [A] · S** — Show the inviter's name and league on the sign-in screen when `?ref=` is present. Social proof at the exact moment of decision, essentially free once the param is parsed.
3. **P2 · [A] · M** — Add a web-visible landing that doesn't require the app at all.

**Holistic priority for Sign-in:** (1) `account_only` dead end · (2) invited-user arrival is meaningless · (3) email capture · (4) demo path · (5) inviter social proof · (6) cold-start copy · (7) ungate error copy · (8) league-URL paste · (9) platform support named · (10–18) remainder.

---

## 2. League Picker — **B−**

**What it is.** A list of the user's leagues with platform badges and a rank chip, plus footer buttons to link ESPN and MFL leagues. Tapping a league runs a two-phase init: a blocking ~2–3s fetch, then an optimistic navigation into the tabs while `POST /api/session/init` finishes in the background.

**Strongest details.** The best-handled cold start in the app: at 4 seconds the copy changes to "Waking up server — first request after a quiet period can take 30s," which is honest and specific where most apps show an indefinite spinner. Multi-platform linking is genuinely ahead of most of the field. The optimistic two-phase navigation is a real engineering nicety — the user is in the app while the session finishes building, with a 409 retry ladder covering the race.

**Shortfalls.** Single-league users still have to tap their one league — `onboarding.league_autoskip` is built and off. Phase-2 session-init failure is only `console.warn`'d, so a user whose session silently failed to build gets no signal and no retry affordance; screens simply behave oddly. The rank chip is a nice touch that fails silently. And this is the last screen before the app's central IA decision, with no explanation of what happens next.

| Criterion | Grade | Strength → Shortfall |
|---|---|---|
| **Usability** | **B+** | Excellent cold-start honesty and per-row busy states → phase-2 failures are invisible to the user. |

1. **P1 · [A/R] · S** — Surface phase-2 `session_init` failure with a retry. Today it fails silently and the user experiences it as an app that's subtly broken.
2. **P2 · [A] · S** — Turn on single-league auto-skip; it's built and off.
3. **P3 · [A] · S** — Make the rank chip's failure visible in dev, silent in prod, rather than silent everywhere.

| **Simplicity** | **B+** | One decision, clearly presented → an unnecessary decision when there's only one option. |

1. **P2 · [A] · S** — Auto-skip on one league (same fix as above; graded here because it's purely a simplicity win).
2. **P3 · [A] · S** — Sort leagues by likely relevance rather than API order.
3. **P4 · [A] · S** — Say what happens after selection so the Quick Set landing isn't a surprise.

| **Retention** | **C** | Multi-league users get a real switcher in the TopBar → the picker itself gives no reason to return. |

1. **P2 · [R] · M** — Show per-league state (unread matches, new movers) on the rows so the picker becomes a dashboard.
2. **P3 · [R] · S** — Surface "N leaguemates joined" per league to make the network effect visible.
3. **P4 · [R] · S** — Remember and default to the last-active league.

| **Replicability** | **C** | Multi-platform linking takes real work → it's work, not a moat. |

1. **P3 · [A] · M** — MFL and Fleaflicker breadth is the differentiating axis here; Fleaflicker is built and off.
2. **P4 · [A] · S** — Nothing else here is defensible.
3. **P4 · [A] · S** — Keep the platform badges; they read as competence.

| **Competition** | **B** | ESPN + MFL + Sleeper is competitive breadth → DynastyGM presents this as a first-class "League Hosts" management hub; FTF splits it across connect screens. |

1. **P2 · [A] · M** — Consolidate platform linking into one managed surface rather than footer buttons plus Settings rows.
2. **P3 · [A] · S** — Turn on Fleaflicker (built, off) to match FPTrack's four-platform breadth.
3. **P4 · [A] · S** — Add per-league sync freshness, which DynastyGM shows and users read as trustworthiness.

| **Growth** | **D+** | Nothing here produces a new user → and this is where a user's whole league becomes visible to the app for the first time. |

1. **P1 · [A] · M** — This screen knows the full roster of every leaguemate at the moment of highest context. An "invite your league" step belongs here, not buried in a progress module three taps deep.
2. **P2 · [A] · S** — Show how many leaguemates are already on FTF per league row.
3. **P3 · [A] · S** — Fire an event on league selection with leaguemate count so the invite opportunity is measurable.

**Holistic priority:** (1) phase-2 failure invisible · (2) invite-your-league moment · (3) auto-skip · (4) per-league state · (5) consolidate platform linking · (6) leaguemates-already-here count · (7–18) remainder.

---

## 3. Guided Onboarding — **D**

**What it is.** A designed guided-tour system: The Analyst (an avatar with six poses, a fifteen-step script, spotlight overlay, skip controls), plus coach marks, an identity-confirm strip, a Quick Set prompt card, an Apple save-moment sheet, a provenance chip, and push priming. Governed by `onboarding.v2` plus ten per-feature sub-flags.

**Strongest details.** The engineering is genuinely good. The guide engine is single-flight ("one bubble at a time"), never intercepts a real action for action-steps, measures spotlight targets with a graceful bubble-only fallback, offers both per-step skip and a permanent opt-out, and is fully instrumented with six event types. The script is well written and the avatar art is bespoke. The design intent — quiet by default, deep on demand — is exactly right for this audience.

**Shortfalls.** Almost none of it runs. `onboarding.v2` is on, but nine of the ten sub-flags are off, and because every surface is double-gated, the shipped experience collapses to: one bubble on League Picker (only for users with 2+ leagues), a celebration on the first like, and — in the same chain tick — **`s8.1`, the tour's sign-off, which fires `completeTour()`**. A default user is told "That's the tour" having been taught nothing: no sign-in guidance, no swipe coaching, no provenance explanation, no Quick Set pitch. Nine scripted steps are structurally unreachable. `err.burst` has zero call sites anywhere. The `ProvenanceChip` — the component that would tell a user their trades are priced on consensus rather than their own board — does not merely show a default state; it never mounts.

| Criterion | Grade | Strength → Shortfall |
|---|---|---|
| **Usability** | **D** | The engine is well built and non-intrusive → it delivers a tour-complete message to users who received no tour. |

1. **P0 · [A] · S** — Either turn the guided layer on or turn `s8.1` off. Telling a user the tour is finished when they've seen one bubble is worse than no tour: it forecloses the possibility that help exists.
2. **P0 · [A] · M** — Decide the onboarding question outright. Ten built sub-flags sitting off is not a neutral state; it is a designed experience that silently didn't ship.
3. **P1 · [A] · S** — Delete `err.burst` or wire it. Dead script entries make the remaining script untrustworthy.

| **Simplicity** | **D+** | Designed to be quiet and contextual → what shipped is a user alone on a tier-sorting screen with no explanation of why. |

1. **P0 · [A] · M** — Ship the Quick Set prompt or an equivalent. A user's first screen currently explains itself only through a one-line hint.
2. **P1 · [A] · S** — Ship the identity-confirm strip; "Trading as @user — not you?" prevents the squatter-confusion case cheaply.
3. **P2 · [A] · S** — Restore the swipe-hint coach mark on the deck.

| **Retention** | **D** | Celebration beats are designed at exactly the right moments → they mostly can't fire, and the session-2 re-engagement banner is off. |

1. **P1 · [R] · M** — Ship the Apple save-moment. It is the only mechanism converting an anonymous board into a recoverable account, and without it a reinstall loses everything.
2. **P2 · [R] · S** — Turn on the celebration beats that survive; they're built and cost nothing.
3. **P3 · [R] · S** — Instrument first-session completion so the funnel is visible before tuning it.

| **Replicability** | **C−** | Bespoke avatar art and a real guide engine are a genuine investment → an unrun tour is worth zero, and guided onboarding is a well-trodden pattern. |

1. **P2 · [A] · M** — The differentiated asset here is the *explanation of the mechanic*, not the avatar. Teaching "why your board beats consensus" is the defensible part.
2. **P4 · [A] · S** — The avatar is charming but not a moat; don't over-invest.
3. **P4 · [A] · S** — Keep the single-flight arbiter; competitors routinely stack modals.

| **Competition** | **C** | Better-designed than most competitor onboarding on paper → not shipped, so it competes at zero. Dynasty Daddy ships tour modals; DynastyDealer ships a mode-select first-run. |

1. **P1 · [A] · M** — Ship something. Any of the three competitors' first-run flows currently beats what a default FTF user gets.
2. **P2 · [A] · S** — The provenance moment (consensus → your board) has no competitor equivalent; it's the strongest idea in the whole system.
3. **P3 · [A] · S** — Consider a mode-select opener (contend/rebuild) — DynastyDealer's, and it doubles as engine input.

| **Growth** | **F** | The share sheet on a liked trade was designed as an onboarding beat → `onboarding.share_sheet` is off, so a user's first delightful moment produces nothing shareable. |

1. **P0 · [A] · S** — Turn on the post-like share sheet. The first-like celebration already fires; the share affordance that was designed to accompany it does not.
2. **P1 · [A] · S** — Add the inviter's identity to the first-run experience when `?ref=` is present.
3. **P2 · [A] · M** — Instrument the first session end-to-end before tuning; today the guide fires events that describe a tour nobody sees.

**Holistic priority:** (1) `s8.1` false completion · (2) decide onboarding outright · (3) Quick Set prompt · (4) post-like share sheet · (5) Apple save-moment · (6) identity strip · (7) ship *something* vs competitors · (8) swipe hint · (9) delete `err.burst` · (10–18) remainder.

---

## 4. Global Shell — **B−**

**What it is.** The persistent chrome: a 52pt TopBar (league switcher, notification bell, settings gear), a five-tab bar (Rank · Acquire · Draft · Matches · League), the FeedbackFAB, the verify banner, toasts, and the guide overlay. Plus the deep-link router.

**Strongest details.** The TopBar's league cluster is the right call — one global switcher beats DynastyGM's per-tab approach, and the format tile ("SF TEP") answers a question users constantly ask. Re-tap-to-top and stack-popping are implemented properly. The deep-link route table is comprehensive (27 routes) with a real fallback toast. Universal links are now correctly configured — entitlement in `app.json:52`, AASA served at `server.py:8075-8108` — which reverses a finding from the July internal teardown.

**Shortfalls.** The tab bar carries a **five-tab load including a seasonal Draft tab that is manually toggled and currently on in August**, when rookie drafts happen in May. "Acquire" is a presentation-only rename over a route named `Trades` — defensible technically, but it means the app's most important verb is a word no competitor uses and no user searches for. There is **zero analytics on any tab tap**, so the most basic navigation question — which tabs do people actually use — is unanswerable. `RookieRanks` is a registered route that appears in neither ranking chooser, reachable only from the Draft Room.

| Criterion | Grade | Strength → Shortfall |
|---|---|---|
| **Usability** | **B+** | Global switcher and consistent header are well executed → five tabs is at the limit, and one of them is seasonally irrelevant right now. |

1. **P1 · [A/R] · S** — Reconsider the Draft tab's presence in August. A top-level tab whose primary feature refuses to run (see Mock Draft) spends the most valuable real estate in the app.
2. **P2 · [A] · S** — Give `RookieRanks` a chooser entry; it's a registered route nothing links to.
3. **P3 · [A] · S** — Add an explicit close affordance to modal screens that rely on swipe-dismiss.

| **Simplicity** | **B** | Tab metaphors are conventional and icons are custom-drawn → "Acquire" is invented vocabulary for the core action. |

1. **P1 · [A] · S** — Reconsider "Acquire." Users, competitors, and the App Store all say "Trades." The route name already is `Trades`; only the label diverges.
2. **P2 · [A] · S** — Four tabs beats five for a first-time user; fold Draft seasonally.
3. **P3 · [A] · S** — Make the format tile tappable to explain what SF TEP means.

| **Retention** | **C+** | The notification bell with unread badge is a real return hook → nothing in the shell surfaces what changed since last visit. |

1. **P1 · [R] · M** — Put a change signal on the tabs (new matches, new movers). The bell is the only one, and it's easy to miss.
2. **P2 · [R] · S** — What's New exists as a mechanism with exactly one hardcoded entry; either feed it or remove it.
3. **P3 · [R] · S** — Badge the Matches tab when a mutual match lands.

| **Replicability** | **C** | Custom icon set and Chalkline primitives are real design investment → shell patterns are the most copyable layer of any app. |

1. **P3 · [A] · S** — Don't invest further here; it's table stakes.
2. **P4 · [A] · S** — The format tile is a genuinely good small idea worth keeping.
3. **P4 · [A] · S** — Keep the single-modal arbiter.

| **Competition** | **B** | Global league switcher matches DynastyGM's strongest structural idea → DynastyGM also offers a global league quick-search FTF lacks. |

1. **P2 · [A] · S** — Add a quick-jump league search for multi-league users.
2. **P3 · [A] · S** — Add sync-freshness to the TopBar; competitors show "Updated: <time>" everywhere and it reads as trust.
3. **P4 · [A] · S** — Consider a persistent value-basis indicator.

| **Growth** | **D** | Universal links are correctly configured → and no link the app produces has a path for them to resolve. |

1. **P0 · [A] · S** — Give invite links a real path. `deepLinks.ts:301-302` short-circuits bare no-path URLs with "nothing to route" — so the entitlement work is currently wasted.
2. **P1 · [A] · S** — Instrument tab taps. Zero navigation analytics means no funnel can be diagnosed post-launch.
3. **P2 · [A] · M** — Add an Android intent-filter equivalent; Android universal links are absent entirely.

**Holistic priority:** (1) invite links have no path · (2) instrument tab taps · (3) Draft tab in August · (4) "Acquire" naming · (5) change signals on tabs · (6) `RookieRanks` orphan · (7) What's New content · (8–18) remainder.

---

## 5. Quick Set Tiers — **C**

**What it is.** The guided tier walk, and **the actual screen a brand-new user lands on**. One position at a time, stepping an eight-rung pick-denominated ladder from "4+ 1sts" down to FA, tapping player chips into each tier and saving to advance.

**Strongest details.** The tier ladder is the single best idea in the product. Naming tiers in draft-pick terms — "2 1sts," "a 2nd," "FA" — gives every value a shared, fungible meaning that no competitor's cosmetic buckets can match, and it maps directly onto how dynasty players actually talk. The zero-selection copy is unusually thoughtful ("Continue — no QBs this high"). Saves compose with the existing board rather than replacing it, and the whole walk is resumable.

**Shortfalls.** It is a **32-tap structural minimum** across four positions before a single trade is seen, and it is the *first thing* a new user encounters, with no explanation of why. Worse, it is the terminus of the unlock coherence break: because `ranking_method` is written only from the Rank Home chooser or Settings — neither on this path — a user who completes this entire walk still registers as `unlocked: false`, which means **the push-permission prompt never fires for them**. The screen also fires no client analytics on individual tier saves, so per-step drop-off inside its own eight-rung walk is invisible from the client.

| Criterion | Grade | Strength → Shortfall |
|---|---|---|
| **Usability** | **C+** | Clear step structure, honest zero-state copy, resumable → completing it doesn't do what the app implies it does. |

1. **P0 · [A/R] · S** — Fix the unlock break. Write `ranking_method` when a user actually uses a method, not only when they pick one from a chooser they never see.
2. **P1 · [A] · S** — Show total progress across all four positions, not just "Tier 1 of 8" within one.
3. **P2 · [A] · S** — Let a user leave mid-walk with their partial progress explicitly acknowledged.

| **Simplicity** | **C** | Each individual step is simple → thirty-two steps before any payoff is not, and it's step one. |

1. **P0 · [A] · M** — Don't make this the first screen. A new user should see a trade before being asked to do data entry. This is the single largest simplicity problem in the app.
2. **P1 · [A] · M** — Allow a one-position exit: rank QBs, get a visibly better deck, come back. The machinery exists; the routing doesn't encourage it.
3. **P2 · [A] · S** — Explain the payoff on-screen. The Trios screen has exactly this line; this screen doesn't.

| **Retention** | **C−** | Resumable progress is the right primitive → but a user who abandons mid-walk has nothing pulling them back. |

1. **P0 · [R] · S** — The unlock fix (above) restores push permission for the default path; without it your primary re-engagement channel is off for most users.
2. **P2 · [R] · S** — Fire a client event per tier save so drop-off is diagnosable.
3. **P3 · [R] · M** — Notify a partially-complete user with a specific, honest nudge.

| **Replicability** | **B−** | Pick-denominated tiers are a genuinely strong idea → they originated in an outside hobby app (TI-CALC) and are a days-long build. |

1. **P2 · [A] · M** — Deepen the anchoring. TI-CALC triple-anchored each tier (pick + WAR band + historical finish); FTF anchors on picks alone.
2. **P3 · [A] · S** — The composability of saves is subtle and good; make it visible.
3. **P4 · [A] · S** — Don't treat the ladder itself as a moat.

| **Competition** | **A−** | No competitor offers guided tier-setting with semantic value bands; Angle Ranks charges $29.99/yr for a single cosmetic drag canvas → but Angle Ranks' pool sorting is better. |

1. **P2 · [A] · S** — Add multi-key pool sort (age, ADP, team, alphabetical). Angle Ranks has six; FTF has none.
2. **P3 · [A] · S** — Add a "tiered / remaining" counter.
3. **P4 · [A] · S** — Consider a shareable tier-board image — the server route already exists (see Growth).

| **Growth** | **F** | Nothing here produces a user → and this is the most naturally shareable artifact in the product. |

1. **P0 · [A] · S** — Wire up tier-board sharing. `/s/tiers/<pos>/<username>` and its OG image are **built and live server-side with zero mobile callers**. This is a complete growth loop missing only a button.
2. **P1 · [A] · S** — Add a share affordance at walk completion — the natural moment of pride.
3. **P3 · [A] · S** — Make the shared board link back to a "build your own" flow.

**Holistic priority:** (1) unlock break · (2) don't land new users here · (3) tier-board sharing (server already built) · (4) one-position exit path · (5) cross-position progress · (6) per-step analytics · (7) payoff copy · (8) pool sort · (9–18) remainder.

---

## 6. Trios — **B**

**What it is.** The three-player forced-rank matchup loop that produces the personal Elo board. Position tabs, a format toggle, an optional "I AM SPEED" auto-submit mode, and a segmented unlock bar showing 0/10 per position.

**Strongest details.** This is the app's signature mechanic and it's well executed. Decomposing a three-way rank into three pairwise comparisons extracts meaningfully more information per interaction than a head-to-head, and the code documents the reasoning. The instruction line steps with the user's progress. Speed mode halves the interaction cost — the only bulk affordance anywhere in the ranking cluster. The unlock payoff line ("Rank 10 per position → trades priced off your board, not consensus") is the clearest value statement in the entire app.

**Shortfalls.** It is not the default — a new user lands on Quick Set and reaches Trios only via a "More ways to rank" header link, two taps deep. Forty submissions at four taps each is 160 taps to a full board, or 80 in speed mode. Individual submissions fire no client event, so the grind is only visible server-side. And the unlock it advertises is the same one the default path can't reach.

| Criterion | Grade | Strength → Shortfall |
|---|---|---|
| **Usability** | **B+** | Stepwise instructions, skeleton loading, speed mode, clear progress → skipping is ephemeral and unexplained. |

1. **P1 · [A] · S** — Surface speed mode earlier; it halves the cost and is currently a toggle users discover late.
2. **P2 · [A] · S** — Explain what Skip does — today it silently refetches with no persistence.
3. **P3 · [A] · S** — Let users see the board they're building without leaving the loop.

| **Simplicity** | **B+** | "Tap best first" needs no explanation → but it's two taps from being found at all. |

1. **P1 · [A] · S** — Make Trios discoverable from the default landing. It's the better first experience for most users and it's buried.
2. **P2 · [A] · S** — Show a 3-of-40 style global progress indicator, not just per-position.
3. **P3 · [A] · S** — Offer a "just do ten total" quick path.

| **Retention** | **B** | The streak chip and per-submission progress make this the most habit-shaped surface in the app → the streak rewards nothing. |

1. **P1 · [R] · M** — Tie streaks to something. They're computed, displayed, and leaderboarded, but earn no unlock, badge, or benefit.
2. **P2 · [R] · S** — Fire a client event per submission so the grind's drop-off curve is visible.
3. **P3 · [R] · M** — A daily "rank five" goal aimed where the engine most needs data.

| **Replicability** | **B+** | Genuinely good elicitation design → KeepTradeCut runs the identical three-player mechanic at 25M+ submissions. |

1. **P2 · [A] · M** — The defensible part isn't the mechanic, it's what the board *does* downstream. Lean the copy there.
2. **P3 · [A] · S** — The adaptive trio-selection strategies are more sophisticated than KTC's; that's worth surfacing.
3. **P4 · [A] · S** — Don't market this as novel; the category leader has it.

| **Competition** | **A** | Six elicitation methods against Angle Ranks' one canvas and DynastyGM's static editor → nobody else lets a user *build* a board this way. |

1. **P2 · [A] · S** — Say this in the App Store listing; it's the clearest differentiator you have.
2. **P3 · [A] · S** — Add the community-comparison beat KTC uses ("you're higher on him than 82%").
3. **P4 · [A] · S** — Consider cross-position trios earlier.

| **Growth** | **D** | Nothing shareable → despite producing the most opinionated, argument-starting artifact in dynasty fantasy. |

1. **P1 · [A] · M** — "You're the highest on X in your league" is a share unit that writes itself. The contrarian data already exists server-side.
2. **P2 · [A] · S** — Share the unlock moment.
3. **P3 · [A] · S** — Let users compare boards with a leaguemate — the natural two-player hook.

**Holistic priority:** (1) streaks reward nothing · (2) discoverability from default landing · (3) contrarian share unit · (4) speed mode surfacing · (5) per-submission analytics · (6) global progress · (7) explain Skip · (8–18) remainder.

---

## 7. Acquire Deck — **B−**

**What it is.** The core loop and the largest file in the app (6,158 lines). A mode bar (Guided · Team · Player · Calc · Free agents), a generate action, and a swipeable card deck with like/pass, plus a single-pin "featured trade" mode and a full Trade DNA sheet.

**Strongest details.** The generation loop is genuinely sophisticated: cards stream in as they're found, with an 800ms→4s jittered backoff, a progress strip showing opponents processed, and a "Hide" affordance that is deliberately not "Stop" because the server keeps working. The two-board mutual-gain engine underneath is the product's real differentiator. Zero-result handling is specific rather than generic, naming the fairness toggle as the fix. The deck's supporting machinery — fatigue, diversity caps, Thompson-sampled ordering, exploration slots — is more considered than anything in the competitive set.

**Shortfalls.** **A generation error is invisible.** `job.error` is never read or rendered anywhere in the file; a failed search with an empty deck falls through to the identical "Hit 'Find a Trade' to start" state as a user who never searched. With `onboarding.trades_first` off, there's also no auto-generation — so a new user's first Acquire tab is a silent empty box requiring a manual tap. Five distinct modes live in one component, and the mode bar's hint text disappears once a deck exists, removing the only explanation of what the modes do.

| Criterion | Grade | Strength → Shortfall |
|---|---|---|
| **Usability** | **C+** | Streaming results, honest progress, specific empty-state copy → failure and fresh-start are indistinguishable. |

1. **P0 · [A/R] · S** — Render `job.error`. A user whose search failed currently sees an invitation to start searching. This is the single clearest defect in the core loop.
2. **P1 · [A] · S** — Auto-generate on first open. The machinery exists behind an off flag; a new user shouldn't face an empty box.
3. **P2 · [A] · S** — Keep mode explanations available after a deck exists.

| **Simplicity** | **C** | Guided mode is a sensible default → five modes, a DNA sheet, fairness toggles, lane pills and targeting is a lot of surface for a first session. |

1. **P1 · [A] · M** — Collapse the controls for first-session users. The first-run chrome collapse is built and off.
2. **P2 · [A] · S** — Explain "fairness" inline; it materially changes results and reads as jargon.
3. **P3 · [A] · S** — Defer Team/Player modes until a user has completed a guided deck.

| **Retention** | **B−** | Deck-done summaries, replenishment messaging and fatigue modelling all aim at repeat visits → "Fresh trades arrive after waivers" is the only temporal hook. |

1. **P1 · [R] · M** — Notify on genuinely new trades. The push plumbing is excellent and this is the highest-value trigger it isn't using well.
2. **P2 · [R] · S** — Make the deck-done summary link forward to a specific next action.
3. **P3 · [R] · M** — Surface "your board changed, here's what's different" after a ranking session.

| **Replicability** | **A−** | The two-board mutual-gain engine with dual surplus gating and harmonic-mean ranking is the one thing here nobody else has → its value requires two ranked users in the same league, which has essentially never happened in production. |

1. **P0 · [A] · M** — The moat is a network effect that has never run. Everything that increases per-league adoption density is a moat investment; nothing else here is.
2. **P2 · [A] · S** — Show users when a card is priced on a real opponent board versus consensus — the distinction is the product.
3. **P3 · [A] · S** — The fairness gates are genuinely novel; don't hide them entirely.

| **Competition** | **A** | No competitor auto-discovers mutual-gain trades against personal values; DynastyDealer's equivalent is premium-gated and fairness-framed → but every serious competitor itemizes *why* a value is what it is, and FTF doesn't. |

1. **P1 · [A] · M** — Itemize the adjustments. The crown/consolidation premium is applied and never explained; DynastyDealer, FPTrack, Dynasty Daddy and DTC all publish theirs.
2. **P2 · [A] · M** — Add counter-suggestion packages (DTF offers both a single-piece and a two-piece evener).
3. **P3 · [A] · S** — Add starter-impact framing to cards.

| **Growth** | **D+** | A share path exists for matched trades → the more common case, a liked-but-unmatched trade, shares a bare referral URL. |

1. **P0 · [A] · S** — Wire the package share landing. `POST /api/share/package` + `/s/p/<id>` + OG image are **built server-side with zero mobile callers**, and the code comment claiming the route doesn't exist is stale.
2. **P1 · [A] · S** — Turn on the post-like share sheet.
3. **P2 · [A] · M** — Make shared trades open a real, viewable trade page for non-users.

**Holistic priority:** (1) `job.error` invisible · (2) package share landing unwired · (3) moat needs league density · (4) auto-generate first open · (5) itemize adjustments · (6) notify on new trades · (7) collapse first-session controls · (8) post-like share · (9–18) remainder.

---

## 8. Trade Card — **B**

**What it is.** The atomic unit of value, appearing on the deck, in Matches, in the featured window, and in the calculator. Carries the opponent, a match-strength bar, YOU SEND / YOU GET columns, the Dynasty Value Swing verdict bar, and human-readable reasons.

**Strongest details.** `TradeValueBar` is the best-designed component in the app: a diverging bar centred on even, with the margin expressed in draft-pick terms ("wins by about a mid 2nd") and ±1st/±2nd tick landmarks. That translation — from an abstract value gap into the currency dynasty players actually think in — is genuinely excellent and has no equal in the competitive set. The card is honest about provenance ("Fair-value idea — this league-mate hasn't ranked players yet"), and badges are well chosen (They're interested, WILDCARD, PAYS FOR FIT, EDITED, OTB, UNTOUCHABLE).

**Shortfalls.** The most useful actions are hidden behind long-press with no visible affordance — swap suggestions, untouchable marking, and player context all live in a gesture a new user will never discover. The "Why?" disclosure on the verdict is collapsed by default, so the reasoning that would build trust is one tap away from invisible. And the card applies a consolidation premium internally that it never itemizes, which is precisely the transparency every competitor offers.

| Criterion | Grade | Strength → Shortfall |
|---|---|---|
| **Usability** | **B** | Dense but legible; badges carry real meaning → the highest-value actions are gesture-only. |

1. **P1 · [A] · S** — Give long-press actions a visible affordance. `ux.player_context_menu` adds ⓘ twins elsewhere; the card's swap/untouchable actions need the same.
2. **P2 · [A] · S** — Expand "Why?" by default, at least for a user's first several cards.
3. **P3 · [A] · S** — Make the dimmed last-asset remove state explain itself rather than just dimming.

| **Simplicity** | **B−** | The verdict bar is instantly readable → the card carries a lot of simultaneous signal for a first-timer. |

1. **P1 · [A] · S** — Progressive disclosure for first-session users: verdict and players first, badges and meters later.
2. **P2 · [A] · S** — Define "match strength" somewhere reachable; it's a bar with no explanation.
3. **P3 · [A] · S** — Reduce badge density on a user's first few cards.

| **Retention** | **B** | "They're interested" is a genuine pull signal → nothing on the card creates a reason to come back tomorrow. |

1. **P2 · [R] · M** — Surface staleness/change ("this got better since you passed").
2. **P3 · [R] · S** — Let a user save a card for later without liking it (Queue exists, flag off).
3. **P4 · [R] · S** — Show when the counterparty last active.

| **Replicability** | **A−** | Pick-denominated verdict framing plus two-board pricing is the hardest thing here to copy → the card layout itself is straightforward. |

1. **P2 · [A] · S** — Lean harder on the pick-denominated verdict in marketing; it's the most distinctive visible artifact.
2. **P3 · [A] · S** — Make the two-board basis explicit on-card.
3. **P4 · [A] · S** — Don't over-invest in card chrome.

| **Competition** | **A−** | The verdict bar beats DynastyDealer's FAIR↔UNEVEN meter on legibility → DynastyDealer itemizes its "+668 STUD BONUS"; FTF shows nothing. |

1. **P1 · [A] · M** — Itemize adjustments in the Why? disclosure. This is the most-cited competitive gap in the internal docs and it lands on this component.
2. **P2 · [A] · M** — Add starter-impact ("your RB2 improves") — DTF's Trade Snapshot idea.
3. **P3 · [A] · S** — Add value-trend context per player.

| **Growth** | **D** | Cards are the most screenshot-worthy artifact in the app → and `ShareTradeImage` shares a PNG with no URL at all. |

1. **P0 · [A] · S** — Put a URL in the shared image. The most-shared artifact in the product currently carries no way back to the app — a one-line fix with outsized effect.
2. **P1 · [A] · S** — Add a share affordance directly on the card, not only in the calculator.
3. **P2 · [A] · M** — Make shared trade links render a real public page.

**Holistic priority:** (1) shared image has no URL · (2) itemize adjustments · (3) long-press invisibility · (4) share on card · (5) Why? expanded by default · (6) progressive disclosure · (7) starter impact · (8–18) remainder.

---

## 9. Trade Calculator — **B−**

**What it is.** A manual trade builder with three modes: In-league (real rosters, two-board verdict, Send in Sleeper), Real values (consensus, no login needed), and Demo league. Reached from the mode bar, the subnav, or a card's "Edit in calculator."

**Strongest details.** The three-mode split is smart: a no-login "Real values" mode is exactly the front door the web competitors use, and it's already built. Draft state persists across app restarts. The prefill hand-off from a deck card is seamless. `ShareTradeImage` produces a genuine PNG share card. Suggested-player rows reduce search friction.

**Shortfalls.** This is the surface most users will compare directly against KTC and FantasyCalc — and it's where FTF's lack of itemized adjustments hurts most, because a calculator's entire job is explaining a number. The share path produces an image with no link. And a strong asset — the no-login mode — is buried behind sign-in, since the whole app requires identity before reaching it.

| Criterion | Grade | Strength → Shortfall |
|---|---|---|
| **Usability** | **B** | Clear mode tabs, persistent draft, good picker → verdict reasoning is thin relative to the task. |

1. **P1 · [A] · M** — Itemize adjustments here first; this is the screen where users demand a "why."
2. **P2 · [A] · S** — Make mode differences explicit; "In league" vs "Real values" is not self-evident.
3. **P3 · [A] · S** — Surface the evener rows more prominently.

| **Simplicity** | **B+** | Add players, see verdict — the most universally understood interaction in the category → three modes is one more than most users need. |

1. **P2 · [A] · S** — Default to one mode and let the others be discovered.
2. **P3 · [A] · S** — Preload the user's own roster in In-league mode.
3. **P4 · [A] · S** — Reduce the tab row to a single switch.

| **Retention** | **C+** | Persistent draft is a real returning-user nicety → a calculator is inherently episodic. |

1. **P2 · [R] · M** — Save named trade scenarios; DynastyDealer's Trade Tracker is exactly this.
2. **P3 · [R] · S** — Notify when a saved scenario's value shifts materially.
3. **P4 · [R] · S** — Show recent calculations.

| **Replicability** | **C+** | Two-board verdict is distinctive → a calculator is the single most cloned artifact in this category. |

1. **P2 · [A] · S** — Make the dual-board framing unmissable; it's the only non-commodity part.
2. **P3 · [A] · S** — Keep the demo mode; it's a good sales tool.
3. **P4 · [A] · S** — Don't compete on calculator breadth.

| **Competition** | **B−** | Two-board verdict and Send-in-Sleeper are ahead → behind on itemization (all), buy/sell spread (DTC), post-trade simulation (Dynasty Daddy), and three-way trades (DynastyDealer premium). |

1. **P1 · [A] · M** — Itemized breakdown (same fix, highest leverage here).
2. **P2 · [A] · M** — Post-trade impact preview — Dynasty Daddy's strongest calculator idea.
3. **P3 · [A] · M** — Consider three-way support; currently built but `trade.three_team` is off.

| **Growth** | **C** | It has the only real image-share in the app → which carries no URL, and the package share landing has no caller. |

1. **P0 · [A] · S** — Add the URL to the share image and wire `POST /api/share/package`. Both halves are built; neither is connected.
2. **P1 · [A] · M** — Expose the no-login "Real values" mode as a public web calculator — the front door every web competitor uses and FTF lacks.
3. **P2 · [A] · S** — Add "sent from FTF" attribution to shared artifacts.

**Holistic priority:** (1) share image has no URL / package landing unwired · (2) itemize adjustments · (3) public no-login calculator · (4) post-trade preview · (5) named scenarios · (6) mode clarity · (7–18) remainder.

---

## 10. Matches — **C+**

**What it is.** The cross-league inbox of mutual trade matches, plus an "Awaiting them" segment for trades you've liked that the counterparty hasn't mirrored. This is where the network effect either pays off or doesn't.

**Strongest details.** Genuinely cross-league by design — matches from every league appear regardless of active session, with a client-side filter. The empty-state copy is the best in the app: *"A match needs two boards — yours and a leaguemate's… matches appear when a leaguemate likes the same trade"* explains the entire product mechanic in one sentence, then offers a primary action and a progress module. The double-opt-in design (neither side sees a one-way like) is a real product insight and is explained in a help sheet.

**Shortfalls.** **There is no Accept action.** `setMatchDisposition` is defined in the API layer and never called anywhere in the app — the only actions are Dismiss and Send in Sleeper. So the emotional peak of the product, a mutual match, terminates in either archiving it or leaving the app. On ESPN leagues, Send in Sleeper renders `null` with no explanation, meaning a matched ESPN user has *only* Dismiss. The screen also depends entirely on a network effect that, per internal data, has essentially never occurred: 16 users, one non-test user with a real board.

| Criterion | Grade | Strength → Shortfall |
|---|---|---|
| **Usability** | **B−** | Excellent empty state, undo on dismiss, cross-league filter → the primary action on a match is absent, and its absence is silent on ESPN. |

1. **P0 · [A/R] · S** — Give ESPN-league matches an explanation and a fallback instead of silently rendering no action.
2. **P1 · [A] · M** — Wire or remove `setMatchDisposition`. Dead accept/decline code means the match lifecycle is incomplete.
3. **P2 · [A] · S** — Confirm what Dismiss does — it's per-user and ELO-neutral, but a user can't know that.

| **Simplicity** | **C+** | The mechanic is explained clearly where it matters → but a user must understand a two-sided matching concept before this screen can ever populate. |

1. **P1 · [A] · S** — Teach the mechanic before the empty state — the explanation currently only appears once a user has already found the empty screen.
2. **P2 · [A] · S** — Make "Awaiting them" the default when mutual is empty and awaiting is not.
3. **P3 · [A] · S** — Show the unlock threshold plainly: one ranked leaguemate.

| **Retention** | **C+** | Match pushes are well built and correctly capped → the screen is empty for essentially every user today. |

1. **P0 · [R] · M** — This screen's value is entirely gated on a second ranked user in the same league. Everything that raises per-league density is the fix; nothing on this screen is.
2. **P2 · [R] · S** — Badge the tab on a new match.
3. **P3 · [R] · M** — Show "close calls" — near-misses that would become matches with one more ranked leaguemate.

| **Replicability** | **A** | Double-opt-in mutual matching against two personal boards exists nowhere else in the category → and it's the one thing here that can't be cloned in a fortnight. |

1. **P2 · [A] · S** — Make the mechanic the headline of your positioning; it's the most defensible idea you own.
2. **P3 · [A] · M** — Invest in anything that raises the chance a second leaguemate ranks.
3. **P4 · [A] · S** — Keep the no-one-way-likes privacy property; it's why the mechanic is socially safe.

| **Competition** | **A** | No competitor has an equivalent concept at all → the gap is that FTF's version needs two users and competitors' one-sided tools need one. |

1. **P2 · [A] · M** — Offer value in the single-player case so the screen isn't empty pre-network.
2. **P3 · [A] · S** — Position against DynastyDealer's Mass Trade Sender as the considered alternative.
3. **P4 · [A] · S** — Add real-trade comps for context.

| **Growth** | **D+** | A mutual match is the single most compelling shareable moment the product can produce → the share path exists but the moment isn't instrumented or promoted. |

1. **P1 · [A] · S** — Prompt a share at the match moment. `/s/trade/<match_id>` is built, live, and has an OG image; this is the one share loop that fully works.
2. **P2 · [A] · S** — Make the invite CTA in the empty state a primary button, not a text link inside a module.
3. **P3 · [A] · S** — Track match-to-send conversion; today Send-in-Sleeper fires no event of any kind.

**Holistic priority:** (1) ESPN matches have no action · (2) network density gates the whole screen · (3) dead accept/decline path · (4) share at the match moment · (5) invite CTA prominence · (6) teach the mechanic earlier · (7–18) remainder.

---

## 11. League Home — **C+**

**What it is.** The classic league page — hero, matches tiles, explore tiles, market pulse, coverage, contrarian ranks, leaderboards, ESPN management. Notably **not** what the League tab opens to; it's a pushed sub-route beneath League Rankings.

**Strongest details.** The low-activity treatment is the most thoughtful piece of product design in the app. Rather than showing a page of zeroes, confirmed-zero sections fold away, a single progress module appears with a real unlock sentence, and a "Works right now" card shows a labelled example trade so a user in an empty league still sees what the product does. The folds are driven by server counts, never client guesses, and sections return automatically. That is genuinely better than what any competitor does with an empty league.

**Shortfalls.** It's buried — the tab named "League" opens the power-rankings chart, and this page is a row-tap deeper. It has **zero analytics of any kind**, client or server, so nothing about league engagement is measurable. The invite affordance — the app's single most important growth action — is a text link inside a progress module, three taps from the tab bar.

| Criterion | Grade | Strength → Shortfall |
|---|---|---|
| **Usability** | **B−** | Fold system, honest empty states, good explore tiles → the page is one level deeper than its name implies. |

1. **P1 · [A] · S** — Resolve the League/League-Rankings IA. Two screens compete for one tab and the one named "home" isn't the landing.
2. **P2 · [A] · S** — Make the ESPN read-only limitation clearer at the point of impact.
3. **P3 · [A] · S** — Give the members overlay a purpose beyond display.

| **Simplicity** | **C+** | Fold system means a new user sees only what's real → but the surviving page is still a lot of sections. |

1. **P2 · [A] · S** — Order sections by what a day-one user can act on.
2. **P3 · [A] · S** — Merge Coverage and League Progress; they measure adjacent things.
3. **P4 · [A] · S** — Reduce the tile grid.

| **Retention** | **C** | Market pulse and leaderboards are real return hooks → both are gated on activity most leagues won't have. |

1. **P1 · [R] · M** — Give the page something fresh for a solo user. Market movers is the only truly evergreen module and it's easy to miss.
2. **P2 · [R] · S** — Turn on the activity feed (built, flag off) once there's activity to show.
3. **P3 · [R] · S** — Add "what changed since your last visit."

| **Replicability** | **C+** | The fold system is unusually well thought out → league home pages are commodity. |

1. **P3 · [A] · S** — The fold system is worth keeping and extending, not marketing.
2. **P4 · [A] · S** — Contrarian ranks are the distinctive module here.
3. **P4 · [A] · S** — Don't invest in tile breadth.

| **Competition** | **C+** | Contrarian leaderboard is genuinely novel → DynastyGM's league surface is richer on nearly every other axis, and FTF has no starter/bench dimension anywhere. |

1. **P1 · [A] · M** — Add a starters/bench dimension; it's DynastyGM's strongest idea and FTF lacks it entirely.
2. **P2 · [A] · M** — Add a real-trade history feed; RosterAudit and DynastyGM both have one.
3. **P3 · [A] · S** — Add per-league sync freshness.

| **Growth** | **D+** | The invite action lives here → as a text link inside a module, on a page that is three taps deep and analytically invisible. |

1. **P0 · [A] · S** — Promote invite to a primary, persistent action on this page. This is the app's most important growth affordance and it is currently the least prominent thing on a buried screen.
2. **P0 · [A] · S** — Instrument this page. Zero events client or server means the entire league/social surface is unmeasurable at launch.
3. **P1 · [A] · M** — Use the member list you already have: "8 of your 11 leaguemates haven't joined — invite them" is shippable today from existing data.

**Holistic priority:** (1) invite is buried and unmeasured · (2) zero analytics · (3) named-leaguemate invite · (4) IA collision with League Rankings · (5) starters/bench · (6) evergreen content for solo users · (7–18) remainder.

---

## 12. League Rankings — **B**

**What it is.** The League tab's actual landing: a vertical stacked-bar power-rankings chart with a basis toggle (Consensus / My board), position filters, a starters/bench control when available, drill-in focus, and a dashed league-average line.

**Strongest details.** This is the best-executed screen in the app and the one that most clearly beats its competitive reference. The chart is genuinely well designed — rank on the x-axis, position-coloured stacked segments, a dashed league-average reference line, a rank numeral in an ice pill for the caller's own team, and a drill-in that grays every other bar while keeping the focused one coloured. The **basis toggle is a dimension no competitor has**: seeing your league ranked by consensus *and* by your own board, with ghost ticks and signed delta chips where the two disagree, is a legitimately original piece of information design. It also works on day one — it renders every roster regardless of whether any leaguemate has joined FTF.

**Shortfalls.** Zero analytics, so none of this sophisticated interaction is measurable. No Maestro coverage of any interactive element. `outlook.odds` — playoff odds, FTF's self-identified #1 competitive gap — is built and dark. And it carries no share affordance despite being the most screenshot-worthy screen in the app.

| Criterion | Grade | Strength → Shortfall |
|---|---|---|
| **Usability** | **A−** | Excellent chart design, honest captions, thoughtful drill-in → the disabled "Redraft (soon)" chip advertises absence permanently. |

1. **P2 · [A] · S** — Remove or date the "Redraft (soon)" chip; a permanently disabled control erodes trust.
2. **P2 · [A] · S** — Make the basis toggle's meaning explicit on first encounter.
3. **P3 · [A] · S** — Add a legend affordance for the ghost-tick overlay.

| **Simplicity** | **B** | The chart reads instantly → the basis/subset/position control stack is a lot at once. |

1. **P2 · [A] · S** — Progressive disclosure of the filter controls.
2. **P3 · [A] · S** — Default to the caller's team pre-focused.
3. **P4 · [A] · S** — Simplify the caption grammar.

| **Retention** | **B−** | Rankings change weekly and the screen makes change visible → but nothing tells a user their rank moved. |

1. **P1 · [R] · M** — Notify on meaningful power-rank movement. This is a natural, honest weekly hook the push system could carry.
2. **P2 · [R] · M** — Turn on `outlook.odds` or delete it; playoff odds is the single strongest retention feature already built.
3. **P3 · [R] · S** — Show week-over-week deltas.

| **Replicability** | **B−** | The dual-basis overlay is original → the chart itself is a well-executed version of DynastyGM's, which FTF's own docs identify as the replication target. |

1. **P2 · [A] · S** — The basis toggle is the defensible part; make it the headline of this screen.
2. **P3 · [A] · S** — Deepen the contrarian angle here.
3. **P4 · [A] · S** — Don't invest further in chart chrome.

| **Competition** | **B+** | Beats DynastyGM on the basis dimension → loses on starters/bench recompute, which is DynastyGM's signature move, and on playoff odds. |

1. **P1 · [A] · M** — Ship the starters/bench league-wide recompute.
2. **P2 · [A] · M** — Ship playoff odds (built, dark).
3. **P3 · [A] · S** — Add picks as a labelled stack segment consistently.

| **Growth** | **D** | The single most shareable screen in the product → with no share affordance at all. |

1. **P0 · [A] · S** — Add share to this screen. A league power-rankings image with a link is the most natural viral artifact the app can produce, and OG infrastructure already exists.
2. **P1 · [A] · S** — Instrument the screen; zero events today.
3. **P2 · [A] · M** — Make a shared ranking open a public page a non-user can read.

**Holistic priority:** (1) no share affordance · (2) zero analytics · (3) playoff odds dark · (4) starters/bench · (5) rank-movement notifications · (6) "Redraft (soon)" chip · (7–18) remainder.

---

## 13. Draft Room — **C+**

**What it is.** A read-only rookie-draft board — the draft order, your picks, and undrafted rookies with a Consensus / My-board toggle. Deliberately never writes a pick; terminal CTA deep-links to the platform's own draft room. Sits behind a dedicated top-level Draft tab.

**Strongest details.** The honesty is exemplary and worth naming as a product virtue: seven typed empty states (`order_not_set`, `class_not_loaded`, `startup_draft`, `platform_unsupported`, `stale`, `mfl_reconnect`, `picks_not_assigned`), each explaining the specific reason and, where possible, offering the fix. The read-only stance — "Picks are made on the platform — Fantasy Trade Finder never drafts for you" — is a principled position that avoids the ToS exposure DynastyDealer courts. The My-board toggle on undrafted rookies is a dimension no competitor's draft tool has. Polling is correctly gated on four conditions including foreground state.

**Shortfalls.** It occupies a top-level tab in August, when rookie drafts happen in May. Its most prominent sibling feature (Mock Draft) refuses to run. Analytics are thin — four events, none on refresh, the mode toggle, or the deep-link CTA. And the whole cluster has no Maestro coverage for three of its five screens.

| Criterion | Grade | Strength → Shortfall |
|---|---|---|
| **Usability** | **B** | Best-in-app empty-state honesty; clear preconditions with fixes → the reason a user is here at all in August is unclear. |

1. **P1 · [A] · S** — Add an off-season state explaining when this becomes useful, rather than relying on `class_not_loaded`.
2. **P2 · [A] · S** — Link the "assign picks" precondition directly from every state that depends on it.
3. **P3 · [A] · S** — Instrument the deep-link CTA; the handoff to the platform is currently invisible.

| **Simplicity** | **C+** | Read-only means little to learn → but reaching a usable state requires assignment, order, and a loaded class. |

1. **P1 · [A] · M** — Reduce the precondition chain; three gates before value is a lot for a seasonal feature.
2. **P2 · [A] · S** — Explain the Consensus/My-board toggle inline.
3. **P3 · [A] · S** — Default to the state requiring least setup.

| **Retention** | **C−** | Live polling during a draft is a genuine "keep it open" moment → for a handful of hours once a year. |

1. **P1 · [R] · S** — Make the Draft tab seasonal in fact, not just in intent. It's a manual annual toggle currently on out of season.
2. **P2 · [R] · M** — Notify when a user's pick approaches — the one high-value push this feature enables.
3. **P3 · [R] · S** — Post-draft recap as a return hook.

| **Replicability** | **B** | Read-only + My-board pricing is a distinctive combination → draft boards are widely built. |

1. **P2 · [A] · S** — The My-board pricing of undrafted rookies is the defensible part.
2. **P3 · [A] · S** — Keep the read-only stance; it's differentiating on trust.
3. **P4 · [A] · S** — Don't chase mock-draft parity.

| **Competition** | **C+** | Honest states and My-board pricing beat competitors on integrity → DynastyGM ships a full working mock simulator; FTF's refuses to run. |

1. **P0 · [A] · S** — Resolve Mock Draft (see unit 23). A tab-level feature that cannot start is worse than one that doesn't exist.
2. **P2 · [A] · M** — Add pick-value context against the tier ladder.
3. **P3 · [A] · S** — Add rookie ADP.

| **Growth** | **F** | Draft boards are intensely social and screenshot-heavy → nothing here is shareable or instrumented for growth. |

1. **P1 · [A] · M** — Share a draft-board or my-picks image; drafts are the highest-social-density moment in dynasty.
2. **P2 · [A] · S** — Instrument the cluster; four events across five screens.
3. **P3 · [A] · M** — Multi-user mock drafts would be a genuine acquisition loop.

**Holistic priority:** (1) Mock Draft refuses to run · (2) seasonal tab in August · (3) precondition chain · (4) off-season state · (5) pick-approaching notification · (6) share draft board · (7–18) remainder.

---

## 14. Settings — **B−**

**What it is.** A modal covering leagues, ranking method, trade values (stud tax, pick pricing), guided tour, notifications and quiet hours, account and identity, about, and gated testing tools.

**Strongest details.** Unusually complete and legally sound: delete-account with a two-step confirm and explicit data enumeration, data export, Sleeper disconnect, and correct Guideline 5.1.1(v) handling. Optimistic toggles with revert-on-error are the right pattern. The `SteerSlider` ("We steer ↔ You steer") is a genuinely elegant way to express ranking-method preference as a spectrum rather than a list. Notification controls including quiet hours are more granular than most competitors offer.

**Shortfalls.** It is the *only* place `ranking_method` gets written outside the Rank Home chooser — making a Settings screen load-bearing for a core-loop unlock, which no user would predict. Nearly every destructive or high-intent action is uninstrumented: sign-out, delete account, export, disconnect, link-Apple, and every platform-link row fire no event. There's no in-app support or contact path beyond the feedback FAB.

| Criterion | Grade | Strength → Shortfall |
|---|---|---|
| **Usability** | **B+** | Clear IA, optimistic toggles, thorough account controls → the notification denial path is good but the rest of the screen never explains consequences. |

1. **P2 · [A] · S** — Explain what stud tax and pick pricing actually change; they materially alter every value in the app.
2. **P2 · [A] · S** — Confirm destructive-adjacent actions like Sleeper disconnect with their consequence stated.
3. **P3 · [A] · S** — Add an in-app support/contact row.

| **Simplicity** | **B** | Sectioned sensibly under v2 IA → trade-value controls are expert options presented at the same level as sign-out. |

1. **P2 · [A] · S** — Group advanced value controls behind a disclosure.
2. **P3 · [A] · S** — Move ranking-method preference nearer the ranking surfaces it governs.
3. **P4 · [A] · S** — Reduce first-level row count.

| **Retention** | **n/a** | Settings is not a retention surface; graded n/a rather than penalised. |

1. **P1 · [R] · S** — Except in one respect: notification preferences are the main retention lever a user controls, and defaults matter more than the controls. Verify defaults are sensible before launch.
2. **P2 · [R] · S** — Make quiet hours discoverable; it reduces uninstall risk.
3. **P3 · [R] · S** — Offer "fewer notifications" rather than only per-type off switches.

| **Replicability** | **C** | The SteerSlider is a nice original touch → settings screens are the definition of commodity. |

1. **P4 · [A] · S** — No investment warranted.
2. **P4 · [A] · S** — Keep the SteerSlider.
3. **P4 · [A] · S** — Keep the export/delete rigor; it's a trust asset.

| **Competition** | **B** | More granular notification control and better account hygiene than most → DynastyGM presents platform accounts as a first-class management hub. |

1. **P2 · [A] · M** — Consolidate platform account management into one surface.
2. **P3 · [A] · S** — Show connection health per platform.
3. **P4 · [A] · S** — Add an account-level value-basis preference.

| **Growth** | **D** | No growth function at all → and it's where an engaged user would look for a way to share or invite. |

1. **P1 · [A] · S** — Add an invite/share row. Settings is where motivated users look for "tell a friend."
2. **P2 · [A] · S** — Instrument high-intent actions; sign-out and delete are churn signals currently invisible.
3. **P3 · [A] · S** — Add a rate-the-app row.

**Holistic priority:** (1) `ranking_method` load-bearing here · (2) instrument churn actions · (3) explain value controls · (4) invite row · (5) notification defaults · (6) platform hub · (7–18) remainder.

