# Independent UX & Product Audit — FTF Mobile

**Date:** 2026-08-09 · **Surface:** iOS, `origin/main @ 72a0770` (v1.11.0) · **Scope:** 33 units across six criteria

**Companion files:** [Scorecard](01-scorecard.md) · [Tier A briefs](02-tier-a-briefs.md) · [Tier B briefs](03-tier-b-briefs.md) · [Priority backlog](04-priority-backlog.md) · [Appendix & sources](05-appendix.md)

---

## The verdict

**Composite: C+ / B−.**

This is a well-engineered product with a **distribution problem and a first-session problem**. Not a quality problem.

The engineering discipline is visible on almost every screen and is genuinely above the standard of the competitive set: typed empty states that name the actual reason, refusals that decline to ship something the team doesn't believe in, deliberate read-only postures that avoid ToS exposure competitors court, fairness gates that stop the engine proposing insulting trades, and a value ladder denominated in draft picks that translates an abstract number into the currency dynasty players actually think in.

That care stops at two places, and they happen to be the two that decide whether a launch works.

**The first ninety seconds.** A new user signs in, picks a league, and lands on a tier-sorting screen — 32 structural taps across four positions — having seen no trade, with one line of explanation. Completing that walk does not register as completing anything, so the push-permission prompt never fires for them. The guided tour that would explain any of this is built, scripted, and ninety percent switched off — and it announces its own completion after a single celebration bubble.

**Bringing a second person.** Every growth loop in the app is built and broken at the last inch. Invite links are generated with a league parameter the app never reads, on a path the router explicitly refuses to route. Two complete share landings with OG images sit on the server with zero callers. The most screenshot-worthy artifact in the product — a trade card image — is shared with no URL at all. Public profiles exist as 429 lines of code with no entry point anywhere in the app.

**The competitive position is genuinely good**, and better than the internal docs give it credit for in some places, worse in others. But the moat is narrower than the documentation claims: exactly one mechanism is hard to copy, and it has essentially never run in production.

---

## Six criteria, app-wide

| Criterion | Grade | Why |
|---|---|---|
| **Usability** | **B−** | Screens are well-built and unusually honest about their limits. The damage is at the seams — a failed trade search is indistinguishable from a fresh one, and the default path silently never completes its own progression. |
| **Simplicity** | **C+** | A new user's first act is a chore they didn't ask for, before any value is demonstrated. |
| **Retention** | **C** | Push permission never fires on the default path, there is no email capture *or email infrastructure*, and the only calendar-aware mechanism in the entire codebase is one hardcoded date. |
| **Replicability** | **C+** | One mechanism is genuinely defensible, and it needs two ranked users in the same league to do anything. |
| **Competition** | **B** | Ahead where it matters most; behind on table stakes the whole field treats as baseline. |
| **Growth** | **D** | Every loop is complete except for the last connection. |

**Growth is D or F on 28 of 31 graded units.** No other criterion is below C on more than six. That concentration is the audit's central finding.

---

## The five findings that matter most

### 1. The default path never completes its own progression
A user can finish the entire 32-step Quick Set walk across all four positions and still register `unlocked: false` — because `ranking_method` is written only from a chooser screen the default path never visits. Trades still generate correctly off their board, so the core loop works; what breaks is everything keyed to the unlock, most importantly **push permission, which never gets requested**. Your primary re-engagement channel is off for the users most likely to need it. *(P0-1 — one-line fix.)*

### 2. Growth loops are complete except for the connection
This is the most striking pattern in the audit. The server has share landing pages, OG image renderers, and referral attribution — all live. The client has invite buttons and share sheets. **They aren't wired to each other.** An invite URL carries `?league=` that nothing reads, on a bare path the router explicitly declines to route with the comment *"nothing to route, no toast."* A tier-board share endpoint has zero callers. A package-share endpoint has zero callers, and the calculator carries a stale comment claiming it doesn't exist. This is days of work, not months — and it's the difference between traffic that compounds and traffic that doesn't.

### 3. The moat is one mechanism, and it has never run
Two-board mutual-gain matching — pricing a trade against *both* sides' personal boards and requiring both to gain — is genuinely unique in this category and would take a competitor real time to replicate. Everything else is days-to-weeks copyable: the trio-Elo mechanic is what KeepTradeCut already runs at 25M+ submissions; the value curve and package math are explicitly adapted from KTC and FantasyCalc; the crown-asset premium is something your own ADR notes two competitors already converge on; the pick-denominated tier ladder originated in an outside hobby app. And per your own data — 16 users, one non-test user with a real board, zero captured trades — the mutual-gain engine has essentially never executed. **The moat is a network effect that needs per-league density, not a code asset.** That should shape where effort goes.

### 4. You will be blind on launch day, in specific places
Server-side instrumentation is better than it first appears — swipes, generations, tier saves, and trio submits all fire `record_event`. But there is **zero client instrumentation on navigation**, so you cannot answer which tabs people use; **zero on both League screens**, client or server, so the entire league and social surface is unmeasurable; and **zero on Send-in-Sleeper**, on both sides — the single highest-intent action in the product is invisible. Three targeted additions fix this.

### 5. Documentation that contradicts runtime behaviour cost this audit a false finding
This slot originally held a claim that the Mock Draft toggle led only to a refusal. **The operator corrected it and was right** — `CPU_MODEL_VALIDATED = True` (`mock_draft_service.py:294`), flipped by override on 2026-08-06, so mocks work. The claim is withdrawn.

What survives is the cause. `config/features.json` still states the mock "stays OFF" and refuses; the code comment sitting directly above the constant still reads *"the verdict is still FAILED, so this stays False and the routes still refuse."* Both assert the opposite of what runs. That contradiction produced a false blocker here and will mislead the next reader — human or agent — in exactly the same way. Tracked as **A-33**.

The methodological lesson is mine: a finding resting on a comment rather than the code is not a finding. `mock_draft_service.py` was outside my pinned snapshot and I inferred behaviour from a client branch instead of reading the constant that decides it.

---

## What's genuinely strong, and worth protecting

Auditors are paid to find problems, so it's worth being explicit about what should not change.

- **The pick-denominated tier ladder.** "Worth 2 firsts" is a better unit than any number, and it runs consistently from tier-setting through the trade verdict bar. This is the best idea in the product.
- **`TradeValueBar`.** Expressing a value gap as "wins by about a mid 2nd" with ±1st/±2nd landmarks is the clearest verdict design in the category.
- **The League Rankings basis toggle.** Seeing your league ranked by consensus *and* by your own board, with ghost ticks where they disagree, is original information design no competitor has.
- **The low-activity treatment on League Home.** Folding confirmed-zero sections and showing a labelled example trade instead of a page of zeroes is better than anything the field does with an empty league.
- **Honest empty states throughout**, especially the Draft Room's seven typed notices and the Matches empty state, which explains the entire product mechanic in one sentence.
- **The refusal to ship the mock-draft bots.** Keep that standard. Just don't ship the door.

---

## Method, and its limits

Nine Sonnet subagents read a pinned snapshot of `origin/main @ 72a0770` and returned structured evidence with `file:line` citations — six by screen cluster, three cross-cutting (competition, growth wiring, replicability). All grading, synthesis, and writing was done by one reviewer so that a `B−` means the same thing on every screen. No subagent assigned a grade.

**Corrections made during the audit**, recorded because they change conclusions:

1. **The Sleeper write path is not a launch blocker.** I flagged it as an P0 candidate mid-audit. `/api/trades/propose` carries an independent hard gate — `if not sess.get("verified")` → 403, explicitly "no grace period" (`server.py:12197`). It remains a business-continuity risk (undocumented private API, live flag, docs describing it as off) but not a security hole.
2. **"Client analytics are blind" was too strong.** Swipe disposition, generation completion, tier saves and trio submits are all captured server-side. Only Send-in-Sleeper is blind on both sides.
3. **Universal links now work.** The July internal teardown's finding that they can't fire — "the share loop terminates in Safari" — no longer holds; the entitlement and AASA are both in place. That makes the unrouted invite links a *worse* problem, not a better one: the hard part is done and unused.

**Limits.** This was a code-based audit; no screenshots or simulator run informed it, since the capture session hadn't landed. Grades reflect `config/features.json` defaults — per-device experiment overlays can differ and are flagged where relevant. Accessibility and Dynamic Type were scoped out as already covered by the July teardown. `backend/database.py` was outside the pinned snapshot for most agents, so a small number of findings cite call contracts rather than implementations; each is flagged in the briefs. The web app and browser extension were out of scope, which leaves one open question: whether `web/` parses the `?league=` invite parameter and completes that journey server-side.

---

## What I'd do first

If you want a single sequence: **fix the nine L0s, then wire the growth loops that are already built, then decide the onboarding question.** The L0s are eight small fixes and one real design decision. The growth loops are days of work against infrastructure that already exists. The onboarding decision — whether a new user sees a trade or a chore first — is the only item here that needs genuine product judgment rather than execution, and it's the one I'd most want pressure-tested before you act on it.

You said you believe you could launch today and want to know what would cap adoption and retention. My answer: nothing in this product's quality would cap it. Two things in its plumbing would — the first session doesn't demonstrate value fast enough, and nothing in the app can bring a second user. Both are fixable in less time than it took to build what's already here.
