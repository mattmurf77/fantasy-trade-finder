# R2-1a — Precedents and Sentiment for Account-Optional, Contribute-to-Consume First Sessions

**Date:** 2026-08-15
**Lens:** Does the vote-first / identity-later model actually work in dynasty fantasy, and how do real users react to it? Drills into KeepTradeCut's vote gate (mechanics + community sentiment), first-session identity across the dynasty tool category, guest→account migration engineering, App Store precedent for third-party league connection, and whether vote-gating helps or hurts crowd-data quality.
**Scope note:** Research only. No product decisions, no code. The final section is explicitly hypotheses.

---

## TL;DR

- **KTC's vote gate is not what the industry believes it is.** A code-level teardown of KTC's shipped bundle shows the full 500-player ranking table and the trade calculator render **ungated on first paint**; a non-dismissible modal fires ~2 seconds *later*; and a labeled escape link — *"I don't know all of these players"* — buys **four hours of unblocked browsing with zero data contributed**. A real vote buys 24 hours. The marketing copy (*"you need to contribute to the rankings to see the rankings"*) overstates the enforcement. **Content first, gate second, bypass always available.**
- **Community sentiment toward the vote gate is strongly positive — the *gate* is defended, not resented.** The one r/DynastyFF post teaching people to block the KTC popup was downvoted to 0 and the top replies were *"That's…what makes it useable"* (+18) and *"if everyone did this, wouldn't KTC become unusable?"* (+40). The poster's defenses sat at −29, −14, −9. This is a community that treats a 5-second contribution as a social contract.
- **The natural experiment that matters is the opposite one.** A KTC clone launched in January 2026 (Fantasy Roundup's "The Trading Post") put the same keep/trade/cut vote **behind a login**. The top comment on its announcement was *"The required login to access anything is a huge turn off fyi"* (+86), followed by *"And behind a login"* (+26) and *"Login = no effin way I'm using this"* (+19). **Same mechanic, same audience, opposite reception — the variable that flipped it was the account, not the vote.**
- **The category's revealed preference is no identity at the door.** KeepTradeCut, FantasyCalc, DynastyProcess, Dynasty Daddy and Sleeper's own API all serve full value data to a cold visitor with no account, no email and no username. Dynasty Nerds is the lone account-at-the-door player, and it pays for that with a free tier throttled to 3 trades/day and Top-5-everything.
- **"No account needed" is used as a *headline selling point* by indie dynasty builders.** Multiple 2026 r/DynastyFF launch posts lead with it verbatim — DynastyCalc (*"No account needed, no manual setup"*, +41), LeagueHistory (*"Site (no login required)"*, +32), and a prospect-rankings app (*"free web app (no login required)"*). None of the launch threads contain a single complaint about the absence of an account.
- **Vote-gating measurably *helps* crowd-data quality if you instrument it — and KTC does.** KTC's FAQ admits to *"test KTCs that ask a question with one obvious right answer"*; the shipped JS shows the full machinery: server-flagged sanity-check questions, client-side comparison against consensus values, a `scNO` failure cookie, per-question `x-ktc-submit-token` anti-scripting tokens, and a sub-4.2-second submission branch. This is textbook crowdsourcing gold-standard quality control.
- **The best-documented threats to vote quality are incentives and missing context, not anonymity.** The Trading Post added a contributor leaderboard and giveaways and immediately drew *"botting on a fantasy tool?"* — and a commenter observed voters were *"just voting 1QB as though it is superflex."* Format-context confusion and extrinsic reward are the two failure modes with direct observational evidence.
- **Guest→account migration is an unsolved problem at every auth vendor.** Firebase, Supabase and Cognito all link *identities* and explicitly refuse to merge *data*; Supabase's docs name the choice ("merge, overwrite, or custom logic"); Firebase has a documented silent-data-loss path. Anonymous rows are personal data under GDPR and need an explicit purge window.
- **The App Store risk is misfiled.** Guideline 4.8 almost certainly does not apply to a username lookup (it isn't a login service and authenticates nothing). **5.1.1(v) is the risk if generic content is gated behind the username field**, and **5.2.2 is the real long-term risk** — Sleeper's published terms permit the API only for *non-commercial* use, and Apple has enforced 5.2.2 even against apps using an official SDK.

**Evidence tags:** `[P]` primary (company's own site, docs, or shipped code) · `[S]` secondary (independent observation, archived community discussion, published research) · `[W]` weak/unverifiable.

---

## 1. What KTC's vote gate actually is

Round 1 characterised KTC as the canonical contribute-to-consume onboarding: *the entry action and the data-collection action are the same thing.* That is true of the **framing**. It is materially less true of the **enforcement**, and the difference matters for anyone copying the pattern.

**Primary observation of the live product** [P] (browser DOM inspection, cookie/localStorage enumeration, and decompilation of the shipped `keeptradecut.com/js/site.min.js`):

| Behaviour | Detail |
|---|---|
| First paint | `/dynasty-rankings` renders **all 500 players** — ranks, tiers, exact values, 30-day trend, risers/fallers. `/trade-calculator` is fully functional. No modal, no blur, no redaction. |
| Gate timing | A modal (`div#rankingsPageKTCModal`, "Your Thoughts?") opens via `setTimeout` ≈2s after `document.ready`. Whether it renders at all is a **server-rendered boolean** driven by the cookies your request carries. |
| Dismissibility | `data-backdrop="static"` (backdrop click does nothing) and `{keyboard:!1}` (Escape disabled). There is **no X**. The page behind stays legible under the dim. |
| The escape hatch | A link, *"I don't know all of these players"* (`#dont-know`), sets `DynastyKtcSubmitted` for **240 minutes** and `DefaultKtcSubmitted` for 1 hour — **without recording a vote.** |
| A real vote | Sets `DefaultKtcSubmitted` for **1 day** (some flows 6h). Matches the FAQ's *"you should only have to answer a KTC every few hours."* |
| Identity primitive | **None.** Before any interaction there is no KTC-owned cookie or localStorage key at all — everything present is ad-tech. No account, no login link, no email capture anywhere in the nav. |
| Cost | *"It's free!"* — no paywall anywhere. Ad-supported (AdThrive) plus a Donate link. |

The KTC homepage nonetheless runs a "Take A Peek" top-8 teaser with the line *"Like we said, you need to contribute to the rankings to see the rankings"* [P, on-page]. That is a **narrative** about reciprocity, not a technical constraint. The FAQ is more honest: *"you need to submit a KTC periodically to see the rankings"* and *"If you accept our cookie policy, you should only have to answer a KTC every few hours."* [P, https://keeptradecut.com/frequently-asked-questions]

Two structural notes for FTF specifically. First, **KTC's values come from "an adapted ELO algorithm"** — their words [P, FAQ] — which makes FTF's Elo matchup the closest mechanical analog in the market, not merely a thematic one. Second, **there is no KeepTradeCut iOS app** [P, App Store catalog search]; the entire vote-first precedent is web-only, so none of it has been tested against Apple's review process.

---

## 2. Community sentiment: the vote gate is defended, the login wall is not

r/DynastyFF is the relevant community. Two threads function as a near-controlled pair.

### 2.1 The vote gate (defended)

In August 2025 a user posted a uBlock Origin rule to suppress the KTC modal ([r/DynastyFF 1n1kq5u](https://www.reddit.com/r/DynastyFF/comments/1n1kq5u/), 2025-08-27) `[S]`. The post itself scored **0**. The reception:

- *"I mean if everyone did this, wouldn't KTC become unusable? Isn't the point to crowd source opinion?"* — **+40**
- *"That's…what makes it useable."* — **+18**
- *"This feels like a lot more effort than just voting"* — **+17**
- *"unironically this is incredibly antisocial behavior… your desire to benefit from society's cooperation without joining in on said cooperation is morally bankrupt"* — **+2**
- The poster's rebuttals: **−29, −14, −9**.

The only *friction* complaints in the entire thread are UX bugs, not the gate itself: *"the new Redraft questions they have you can't skip with the 'I don't know those players'. The option is there, just hitting it does nothing"*, and a +26 joke — *"Justin Jefferson, Saquon Barkley, and Josh Allen? No, Keep Trade Cut, I actually don't know these players"* — which is a complaint that the **bypass link is too easy to abuse**, not that the gate is too hard.

**Read:** in this community the 5-second vote is understood as the price of the commons and defended socially. That defence is itself a retention asset — it converts a friction step into an identity ("I contribute").

### 2.2 The login wall (rejected)

In January 2026, Fantasy Roundup launched "The Trading Post" — described in the announcement as a crowdsourced dynasty rankings tool where *"You vote keep/trade/cut on player matchups and it builds out the rankings from everyone's votes,"* with live voting feeds, a contributor leaderboard, and giveaways ([r/DynastyFF 1q64mq6](https://www.reddit.com/r/DynastyFF/comments/1q64mq6/), 2026-01-07) `[S]`. Same mechanic as KTC, same subreddit, same audience. The reception inverted:

- *"The required login to access anything is a huge turn off fyi"* — **+86** (top comment)
- *"And behind a login"* — **+26**
- *"Login = no effin way I'm using this"* — **+19**
- *"Why copy that behind a login and with fewer users?"* — **+7**
- *"Why create an account to log in for a smaller sample size of something already being provided for free?"* — **+2**

Secondary objections — *"a worse KTC"*, *"shittier delta because of less voters"* — are network-effect complaints, not identity complaints, and would apply to any new entrant. But **the single most-upvoted comment in the thread is about the login, not the values.** The launch also drew *"botting on a fantasy tool?"* (+7) and *"sounds like some kind of money grab"* (+8) in response to the leaderboard-and-giveaway framing.

I could not verify the current state of The Trading Post: fsroundup.com is a Clerk-authenticated SPA whose sitemap lists no Trading Post route, and every path returns 200 via SPA catch-all [P, direct probe]. So I cannot say whether they removed the login. The *reception* is the durable finding.

### 2.3 The corroborating pattern: builders lead with "no account"

Across 2026 r/DynastyFF launch posts, absence of an account is used as a headline feature `[S]`:

- DynastyCalc: *"enter your Sleeper username, pick your league, and it automatically pulls in every roster and detects your league settings… **No account needed, no manual setup.**"* — +41, 33 comments ([1rutkx1](https://www.reddit.com/r/DynastyFF/comments/1rutkx1/)). Every comment in the thread is about trade-engine logic (positional scarcity, QB handling, pick mapping); **not one is about identity.**
- LeagueHistory: *"Site (no login required)"* — +32 ([1rxbiz9](https://www.reddit.com/r/DynastyFF/comments/1rxbiz9/)); and a follow-up post opening *"No account needed."* ([1t6cylj](https://www.reddit.com/r/DynastyFF/comments/1t6cylj/)).
- A 2026/2027 prospect-ranking app: *"a free web app (no login required)"* ([1phd7q1](https://www.reddit.com/r/DynastyFF/comments/1phd7q1/)).
- MyFantasyAnalyzer, a no-account Sleeper analytics tool, reported *"4,200 users in a week"* off a single r/DynastyFF post ([1sas810](https://www.reddit.com/r/DynastyFF/comments/1sas810/)) `[S, self-reported]`.

The failure mode this community *does* punish in no-account tools is **sync accuracy**, exactly as round 1 predicted. DynastyDealer's KTC-alternative launch ([1kluell](https://www.reddit.com/r/DynastyFF/comments/1kluell/), +64) drew zero complaints about voting and a wall of complaints about stale rosters — *"My roster is showing a few months behind"*, *"it's not reflecting trades/draft picks from during the offseason… certainly feels like it is pulling data from 2024."* **Import is the onboarding; import failure is onboarding failure.**

---

## 3. First-session identity across the category

| Tool | Core tool without an account? | Identity primitive | Contribute-to-consume gate? | Where the wall sits |
|---|---|---|---|---|
| **KeepTradeCut** | **Yes** — full rankings + calculator ungated | **None** (first-party cookie only) | **Soft + bypassable** (modal ~2s; free bypass = 4h; vote = 24h) | Nowhere. Free, ad-supported |
| **FantasyCalc** | **Yes** — all 475 assets, no modal | **None** to read; optional **Sleeper username** to sync | **No** — values from ~6.68M observed real trades | Nowhere; open unauthenticated API |
| **DynastyProcess** | **Yes** | **None** | **No** | Nowhere; open CSV/Parquet on GitHub, Ko-fi tips |
| **Dynasty Daddy** | **Yes** — explicit **"Continue without Account"** button | Optional DD account *or* Sleeper username/League ID | **No** | Account is for persistence, not access |
| **Dynasty Nerds / DynastyGM** | **No** — *"Create a free account to get started"* | **Email + password** (Stripe) | No | **At the door**, then throttled by frequency *and* depth: 3 trade previews/day, Week-1-only optimizer, Top-5 everything, 1 league. $69.99/yr. No trial |
| **Sleeper (the API)** | **Yes** | **None** — *"No API Token is necessary"* | No | ~1000 req/min guidance |
| **FPTrack** | Values/rankings appear open | Account + subscription | No | At **league-sync** features ("Sync Required"), not at value data |
| **DLF** | Teasers only | Account + subscription | No | Depth paywall, $79.99 yr-1 / $99.99 renewal `[S]` |

All rows are direct observation `[P]` except DLF `[S]`. Dynasty Nerds' own pricing page lists the mobile app under Premium while its marketing says *"No credit card required to start"* — **unresolved contradiction**; first-launch behaviour of their iOS app (id1570526998) was not verified.

**The load-bearing fact for the whole category** is that Sleeper's API is read-only and unauthenticated [P, https://docs.sleeper.com/]. That is why "type your Sleeper username" replaced OAuth everywhere. Note the caveat Sleeper's docs attach: the API is *"free to use for non-commercial purposes"* and *"For commercial use of the Sleeper API, please reach out to us directly to discuss licensing."*

---

## 4. Does vote-gating help or hurt crowd-data quality?

### 4.1 What KTC actually does

The FAQ [P] admits the mechanism in one sentence: *"We occasionally run 'test' KTCs that ask a question with one obvious right answer. 'Keep' the stud to prove you're paying attention… This is one of several things we do behind the scenes to ensure our crowdsourced data is rock solid."*

The shipped JS shows the implementation [P, decompiled `site.min.js`]:

- Questions carry server-set sanity-check flags (`oneQBSC` / `superflexSC`).
- The client compares the user's Keep/Trade/Cut against known consensus values.
- **Pass** → `.sc-passed-banner` + an analytics goal. **Fail** → a `scNO` cookie set for 1 day, a distinct analytics goal, and `.sc-failed-banner` on next load.
- Every submission carries a per-question `x-ktc-submit-token` header — anti-CSRF / anti-scripting.
- The submit handler branches on elapsed time since modal render (`n - l < 4200` ms), consistent with a too-fast-to-be-real guard. *(Code is `[P]`; the "speed guard" interpretation is `[W]` inference from minified JS.)*

Community members independently attest to feeling these tests: *"they purposefully give very obvious keep-trade-cuts to users to test if they're giving reasonable answers"* (+3), *"KTC intentionally gives obvious prompts to identify users who have no idea what they are talking about"* (+15), *"I read something a while back about KTC discarding the obvious troll votes"* (+2) — all from a 2024 thread in which a user announced they always vote Cut on the best player ([1cdlu0w](https://www.reddit.com/r/DynastyFF/comments/1cdlu0w/), 2024-04-26) `[S]`. That thread is itself the sentiment finding: the manipulator was buried (top reply +44, *"Sounds pretty lame"*), and the sub's dominant frame was *"Tragedy of the commons type shit."*

**Negative result:** no KTC founder interview or podcast appearance on data quality could be found `[P, negative result]`. Everything above is FAQ text plus their own shipped code.

### 4.2 What the research literature supports

- **Gold-standard/control questions and attention checks are the standard quality-control mechanism in crowdsourcing**, and attention checks measurably improve performance (ACM Computing Surveys, *Quality Control in Crowdsourcing*; *Variable Effort Crowdsourcing and How Visible Gold Can Help*) `[S]`. KTC's "test KTCs" are exactly this.
- **Pairwise/forced-choice comparison is structurally manipulation-resistant.** Salganik & Levy, *Wiki Surveys* (PLOS ONE, 2015): *"Pairwise comparison makes manipulation, or 'gaming,' of results difficult because respondents cannot choose which pairs they will see"* — to game it *"a respondent would have to respond many times in order to be presented with the item that she wishes to 'vote up.'"* [P]
- **The contribution distribution is brutally skewed, and truncating it destroys most of the data.** Same paper: *"If we only accepted the first 10 responses per respondent and discarded all respondents with fewer than 10 responses, approximately 75% of the responses in each survey would have been discarded."* Their PlaNYC case: 1,436 respondents → 31,893 responses (~22 each). **A vote system's value comes disproportionately from a small heavy-voting minority.** They are equally explicit about the limit that applies to any voluntary-vote system: *"we can only draw inferences about respondents, who should not be considered a random sample from some larger population."*
- **Crowd wisdom is measurably biased in practice** even at hundreds of thousands of participants (arXiv 0909.0237) `[S]`, and vote brigading is a documented participation-bias failure mode `[W]`.

### 4.3 Three observed degradation vectors

1. **Extrinsic reward invites gaming.** The Trading Post shipped a contributor leaderboard plus giveaways ("5,000th voter gets a free team breakdown") and the immediate community response included *"botting on a fantasy tool?"* and *"sounds like some kind of money grab"* `[S]`. KTC, by contrast, offers no reward for voting at all — and gets defended for it.
2. **Missing format context corrupts votes silently.** From that same thread: *"Looks like most people don't realize there's a toggle for 1QB and Superflex, and are just voting 1QB as though it is superflex based on the rankings."* `[S]` A vote UI that doesn't make the scoring context unmissable collects confidently-wrong data.
3. **The bypass is used by people who could vote.** *"I just heard a podcaster I respect the hell out of admit that he hits the 'I don't know who that is' button"* `[S]`. The escape hatch reduces friction and reduces yield; both effects are real.

**Net read:** vote-gating does not degrade crowd data *provided* the system (a) uses forced pairwise/triadic choice the user cannot select, (b) seeds gold-standard checks, (c) offers no extrinsic reward for volume, and (d) makes format context explicit. On the evidence, KTC does all four.

---

## 5. Guest-mode → account migration: the engineering reality

Every major auth vendor draws the same line: **they link identities and explicitly refuse to merge application data.**

- **Firebase** converts an anonymous account via `linkWithCredential`, after which *"the user's new account can access the anonymous account's Firebase data."* But when the credential already belongs to someone, the docs say only: *"you must handle merging the accounts and associated data as appropriate for your app"* — the sample code contains the comment *"Merge prevUser and currentUser accounts and data"* with no implementation [P]. Firebase frames anonymous auth as strictly transitional: *"It's important to convert users to a permanent sign in method so their work can be definitively retained."*
- **Supabase** is the most explicit about the failure path: linking an anonymous user to an existing email **returns an error**, and the remedy is a manual three-step reassignment with your own *"merge, overwrite, or custom logic"* [P].
- **AWS Cognito** merges automatically — but only at the identity layer, capped at 20 linked logins, and only for developer-authenticated users, not raw guests [P].
- **Clerk does not support anonymous users at all** — "Guest Logins / Anonymous Users" sits in their public roadmap backlog [P].

**The dangerous case is three-way:** guest has data *and* the target account has data. No vendor ships a resolution. Worse, the link can silently succeed and destroy data — Firebase Android SDK issue #2579 documents a sequence where *"all data created by anonymous user is lost"* with the link returning success; closed by bot, no fix `[S]`.

**Abuse, lifecycle, privacy, analytics.** Supabase warns that *"bad actors can abuse the endpoint to increase your database size drastically"*, defaults to 30 req/hr/IP, and offers **no automatic cleanup**; Firebase Identity Platform auto-deletes anonymous accounts older than 30 days and exempts them from billing quotas when cleanup is on [P]. Device fingerprints and pseudonymous IDs remain **personal data under GDPR** (EDPB Guidelines 01/2025), so guest rows carry deletion obligations. And identity merges are one-way in analytics: Mixpanel states *"you cannot merge 2 `$user_id`s"*; Amplitude's user ID cannot be changed once set [P] — **a multi-device guest produces permanently duplicate analytics identities.**

**The demand-side evidence for deferring the ask** is solid but thinner than commonly claimed. Baymard's cart-abandonment meta-analysis (50 studies, 2006–2025) puts *"required account creation"* at **18%** of abandonment reasons — **not** the 24–26% that circulates on secondary blogs [P]. NN/g's *Login Walls Stop Users in Their Tracks* (Budiu, 2014-03-02) frames the mechanism: users unable to preview real functionality *"guess low to be on the safe side"* about value, *"because people have been burned frequently enough by online services"* [P]. Duolingo remains the strongest product datapoint (~+20% DAU from moving signup after the first lesson) `[S]`.

---

## 6. App Store precedent: the risk is misfiled

- **Guideline 4.8 almost certainly does not apply.** It triggers on a *"third-party or social login service… to set up or authenticate the user's primary account with the app."* A Sleeper username lookup fails both tests: it is not a login service and it authenticates nothing. Every 4.8 rejection findable on Apple's forums was triggered by literal Google/Facebook OAuth buttons [P + S]. **No thread anywhere addresses username-only flows against 4.8, and no Apple-staff interpretation of 4.8 exists on the forums** — a negative result worth recording.
- **5.1.1(v) is the near-term risk.** A quoted rejection notice reads *"We noticed that your app requires users to register or log in to access features that are not account-based… Registration must then only be required for account-specific features"* [P]. Gating *league-specific* value behind a username is "directly relevant to core functionality" — the guideline's own exemption. Gating *generic* content (rankings, tier ladder, manual calculator) behind it is the pattern that gets flagged.
- **5.2.2 is the underrated long-term risk.** Verbatim: *"ensure that you are specifically permitted to do so under the service's terms of use. Authorization must be provided upon request."* Apple has enforced this even against an app using Zoom's **official** SDK, and the Tesla case (*"written consent of the owner of that service"*) is the well-known precedent `[S]`. Sleeper's docs permit the API *"for non-commercial purposes"* and invite a licensing conversation for commercial use; Sleeper's General Terms grant only a *"personal and non-commercial"* licence [P]. **The moment a Sleeper-reading app monetises, the published terms stop covering it.** Multiple monetised Sleeper-reading apps are nonetheless live (Dynasty Nerds id1570526998 with IAP, Dynasty Scout id6503407267) `[S]`, so Apple is not screening proactively — but **no documented rejection of any fantasy app under 5.2.2 was found**, and that absence is itself the finding, not an all-clear.

---

## Evidence quality notes

**Strongest (`[P]`, directly observed or verbatim from source):** KTC's shipped `site.min.js` and rendered DOM — the modal timing, the `#dont-know` cookie durations, the sanity-check machinery, the submit token — plus the KTC FAQ text. Apple's guidelines and forum rejection notices quoted verbatim. Firebase/Supabase/Cognito/Clerk docs. Sleeper's API docs and Terms. Salganik & Levy (PLOS ONE, 2015). Baymard's abandonment page. NN/g's login-wall article. The live-site audits of FantasyCalc, Dynasty Daddy, DynastyProcess and Dynasty Nerds' pricing matrix.

**Moderate (`[S]`):** All Reddit evidence. **Sourcing caveat that matters:** reddit.com is blocked to both this environment's search and fetch tooling, so every thread above was retrieved via the **Arctic Shift Reddit archive API** (`arctic-shift.photon-reddit.com`), which returns Reddit's own post/comment JSON including scores. Post IDs and permalinks are given so anything can be re-checked by a human in a browser. Vote scores are point-in-time archive values, not live. Community sentiment on a single subreddit is not a representative sample of dynasty players — it skews toward high-engagement, tool-literate users, which is precisely the population most likely to defend a contribution norm. Also `[S]`: the crowdsourcing quality-control literature, and the App Store forum threads.

**Weak (`[W]`):** The "too-fast submission guard" reading of KTC's `n - l < 4200` branch is inference from minified code. DLF's pricing (search snippets only). Any characterisation of The Trading Post's *current* state. Self-reported growth numbers ("4,200 users in a week").

**Could not verify:** any KTC founder interview discussing data quality (searched; none found); KTC's post-vote behaviour observed empirically (no vote was submitted to a third party — the 24h/6h durations are read from code); whether The Trading Post still requires a login or still has a keep/trade/cut tool (fsroundup.com is a Clerk SPA whose sitemap has no such route); Dynasty Nerds' iOS first-launch behaviour (their pricing page and marketing copy contradict each other); FantasyCalc's FAQ and add-your-league text (SPA shells); any documented App Store rejection of a fantasy app under 5.2.2, or any case where a public API's ToS alone satisfied a 5.2.2 authorisation request; and any named-company engineering postmortem on anonymous→account migration — only vendor docs and GitHub issues exist publicly.

---

## Implications for FTF (hypotheses only — none of these is a recommendation to ship)

- **H1 — Copy KTC's *actual* gate, not its marketing.** Content first, gate second, always bypassable. *Hypothesis:* rendering tiers/rankings/calculator immediately and firing the matchup prompt ~2s later — with a permanent, honest escape ("I don't know these players") — will outperform a hard vote wall on both engagement and App Store review posture, because it is the design that KTC actually validated at 26.5M data points.
- **H2 — The account, not the vote, is the thing this community rejects.** The Trading Post's +86 top comment is the cleanest available evidence. *Hypothesis:* FTF can ask for a lot of *contribution* in session one and almost no *identity*, and the ratio is what determines reception. Any screen labelled "Sign up" before first value is the specific pattern that draws the −86-equivalent.
- **H3 — Make "no account needed" a stated marketing claim, not just a property.** Four separate 2026 r/DynastyFF launches used the phrase as their lede and none drew identity complaints. *Hypothesis:* the phrase is a recognised trust signal in this niche and is worth putting in App Store copy, the web hero, and any launch post.
- **H4 — Instrument vote quality from day one, and say so.** KTC ships gold-standard checks, a failure cookie, and per-question anti-scripting tokens. *Hypothesis:* FTF's Elo needs the same three — seeded obvious matchups, a per-voter trust weight derived from check performance, and a submit token — and publishing that it does so (as KTC does in its FAQ) is a differentiator against calculators whose values "arrive from nowhere."
- **H5 — Never reward vote volume extrinsically.** The one dynasty tool that added a contributor leaderboard and giveaways was immediately accused of inviting bots. *Hypothesis:* streaks/recaps that reward *consistency* are safe; leaderboards and prizes that reward *volume* poison both the data and the trust narrative.
- **H6 — Make scoring format unmissable inside the vote UI.** Observed evidence that voters answered a 1QB matchup as if it were Superflex. *Hypothesis:* if FTF's matchup doesn't display the format context as a first-class element of the card, it will silently collect wrong-context votes at a rate nobody notices.
- **H7 — Expect a heavily skewed contribution curve and design for it.** Salganik & Levy: truncating to 10 votes/user would discard ~75% of all responses. *Hypothesis:* FTF's Elo will be carried by a small heavy-voting minority; per-user vote caps intended for "fairness" would be actively harmful, and the right lever is trust-weighting, not rate-limiting.
- **H8 — Design the guest→account merge conflict before writing the link call.** Every vendor punts it; Firebase has a documented silent-data-loss path. *Hypothesis:* FTF must pick an explicit rule (guest wins / account wins / union / user chooses) for the case where a device-keyed guest has votes and boards *and* the account being linked already has both — and the link must be idempotent and logged. Two adjacent launch requirements fall out of the same evidence: an explicit purge window for unlinked guest rows (GDPR personal data, abuse vector, no vendor cleanup), and a device→account analytics alias emitted at link time, since Mixpanel and Amplitude both make user-ID merges one-way — without it the value-before-identity experiment is unmeasurable on its own terms.
- **H9 — The App Store conversation to have is 5.2.2, not 4.8.** *Hypothesis:* the durable risk is not the username field's resemblance to a social login, but Sleeper's published non-commercial-only API terms colliding with monetisation. A licensing reply on file from Sleeper is the only artifact that satisfies "authorization must be provided upon request," and no evidence exists that public ToS alone has ever satisfied it.
- **H10 — Guest mode is the mitigation for a rejection risk FTF may already carry.** 5.1.1(v) is enforced with quoted rejection language about non-account-based features. *Hypothesis:* making the calculator, tier ladder and matchup vote reachable without any input is simultaneously the growth play and the compliance answer — the same change buys both.

---

## Sources

**KeepTradeCut (primary)**
- Home / "Take A Peek" — https://keeptradecut.com/
- FAQ (vote cadence, cookies, test KTCs, adapted ELO, "It's free!") — https://keeptradecut.com/frequently-asked-questions
- About — https://keeptradecut.com/about
- Dynasty Rankings — https://keeptradecut.com/dynasty-rankings · Trade Calculator — https://keeptradecut.com/trade-calculator
- Shipped bundle (modal timing, `#dont-know` cookies, `scNO`, `x-ktc-submit-token`, `/submitKtcResult`) — https://keeptradecut.com/js/site.min.js

**Community sentiment (r/DynastyFF; retrieved via the Arctic Shift Reddit archive API)**
- uBlock rule to block the KTC popup (2025-08-27) — https://www.reddit.com/r/DynastyFF/comments/1n1kq5u/
- Fantasy Roundup "The Trading Post" launch, login backlash (2026-01-07) — https://www.reddit.com/r/DynastyFF/comments/1q64mq6/
- DynastyDealer KTC-alternative launch (2025-05-13) — https://www.reddit.com/r/DynastyFF/comments/1kluell/
- "Manipulating Keep/Trade/Cut" (2024-04-26) — https://www.reddit.com/r/DynastyFF/comments/1cdlu0w/
- DynastyCalc, "No account needed" (2026-03-15) — https://www.reddit.com/r/DynastyFF/comments/1rutkx1/
- LeagueHistory, "no login required" (2026-03-18) — https://www.reddit.com/r/DynastyFF/comments/1rxbiz9/ · follow-up (2026-05-07) — https://www.reddit.com/r/DynastyFF/comments/1t6cylj/
- Prospect rankings app, "no login required" (2025-12-08) — https://www.reddit.com/r/DynastyFF/comments/1phd7q1/
- MyFantasyAnalyzer, 4,200 users in a week (2026-04-02) — https://www.reddit.com/r/DynastyFF/comments/1sas810/
- "Was Dynasty better before KeepTradeCut?" (2025-08-06) — https://www.reddit.com/r/DynastyFF/comments/1mjc658/
- "Is KTC or FantasyCalc a better gauge?" (2025-11-03) — https://www.reddit.com/r/DynastyFF/comments/1onh4ud/
- "KTC is WAY off with its rookie valuations this year. Is it dying?" (2026-05-04) — https://www.reddit.com/r/DynastyFF/comments/1t3j1jt/
- Sleeper Stalker, public-username lookup tool (2026-02-22) — https://www.reddit.com/r/DynastyFF/comments/1rbsvj1/
- Archive API used — https://arctic-shift.photon-reddit.com/

**Category / competitor identity**
- FantasyCalc — https://fantasycalc.com/ · https://fantasycalc.com/dynasty-rankings · https://api.fantasycalc.com/values/current
- DynastyProcess — https://dynastyprocess.com/ · https://github.com/dynastyprocess · https://raw.githubusercontent.com/dynastyprocess/data/master/files/values.csv
- Dynasty Daddy ("Continue without Account") — https://dynasty-daddy.com/
- Dynasty Nerds pricing matrix — https://www.dynastynerds.com/plans-and-pricing/ · support — https://support.dynastynerds.com/
- DynastyTradeCalculator — https://dynastytradecalculator.com/ · FPTrack — https://fptrack.com/ · Dynasty Dealmaker — https://dynastydealmaker.com/ · Fantasy Roundup — https://www.fsroundup.com/roundup/polls
- Sleeper API docs (read-only, no token, non-commercial) — https://docs.sleeper.com/ · Terms — https://support.sleeper.com/en/articles/5486620-general-terms-of-use

**Crowd-data quality**
- Salganik & Levy, *Wiki Surveys: Open and Quantifiable Social Data Collection*, PLOS ONE 2015 — https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0123483
- *Quality Control in Crowdsourcing: A Survey* (ACM CSUR) — https://dl.acm.org/doi/pdf/10.1145/3148148
- *The Challenge of Variable Effort Crowdsourcing and How Visible Gold Can Help* — https://arxiv.org/pdf/2105.09457
- *Adversarial Attacks on Crowdsourcing Quality Control* (JAIR) — https://www.jair.org/index.php/jair/article/view/11332
- *Is the crowd's wisdom biased?* — https://arxiv.org/pdf/0909.0237
- Vote brigading — https://en.wikipedia.org/wiki/Vote_brigading

**Guest → account migration**
- Firebase anonymous auth — https://firebase.google.com/docs/auth/web/anonymous-auth · account linking — https://firebase.google.com/docs/auth/ios/account-linking · best practices — https://firebase.blog/posts/2023/07/best-practices-for-anonymous-authentication/
- Firebase Android SDK issue #2579 (silent data loss) — https://github.com/firebase/firebase-android-sdk/issues/2579
- Supabase anonymous sign-ins — https://supabase.com/docs/guides/auth/auth-anonymous
- AWS Cognito identity switching / merge — https://docs.aws.amazon.com/cognito/latest/developerguide/switching-identities.html · https://docs.aws.amazon.com/cognitoidentity/latest/APIReference/API_MergeDeveloperIdentities.html
- Clerk roadmap (guest logins in backlog) — https://feedback.clerk.com/roadmap
- Mixpanel ID management — https://docs.mixpanel.com/docs/tracking-methods/id-management/identifying-users-original
- EDPB Guidelines 01/2025 on pseudonymisation — https://www.edpb.europa.eu/system/files/2025-01/edpb_guidelines_202501_pseudonymisation_en.pdf

**Deferred registration demand-side**
- Baymard, cart abandonment (18% required account creation; 50-study meta-analysis) — https://baymard.com/lists/cart-abandonment-rate
- NN/g, *Login Walls Stop Users in Their Tracks* (Budiu, 2014-03-02) — https://www.nngroup.com/articles/login-walls/
- NN/g, *Don't Force Users to Register Before They Can Buy* — https://www.nngroup.com/articles/optional-registration/
- LukeW, *Killing Sign Up Forms* / gradual engagement — https://www.lukew.com/ff/entry.asp?1219= · https://alistapart.com/article/signupforms/
- First Round Review, Duolingo A/B testing (+20% DAU) — https://review.firstround.com/the-tenets-of-a-b-testing-from-duolingos-master-growth-hacker/

**App Store**
- App Store Review Guidelines (4.8, 5.1.1(v), 5.2.2) — https://developer.apple.com/app-store/review/guidelines/
- Forum thread quoting a 5.1.1(v) rejection notice — https://developer.apple.com/forums/thread/114080
- Forum thread, 5.2.2 enforced against an official Zoom SDK integration — https://developer.apple.com/forums/thread/134224
- 9to5Mac, Apple rejects "Watch for Tesla" over unofficial API (2020-08-27) — https://9to5mac.com/2020/08/27/apple-rejects-watch-for-tesla-app-as-it-starts-requiring-written-consent-for-third-party-api-use/
- 9to5Mac, Apple relaxes the Sign in with Apple requirement (2024-01-27) — https://9to5mac.com/2024/01/27/sign-in-with-apple-rules-app-store/
