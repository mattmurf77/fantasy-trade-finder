# A3 — How Feature-Dense Apps Actually Onboard: Case Studies

**Date:** 2026-08-15
**Lens:** Concrete teardowns of first-session flows in complex consumer/productivity apps and fantasy-sports apps, drawn from published material. Research only — no product decisions, no code.

---

## TL;DR

- **The single best-evidenced move in the whole corpus is delaying the sign-up wall until after first value.** Duolingo's VP of Growth reports moving the sign-up screen back a few steps produced "about a 20% increase in DAUs," with a further +8.2% DAU from tuning hard vs. soft walls afterward ([First Round Review, 2017, updated 2024-11-23](https://review.firstround.com/the-tenets-of-a-b-testing-from-duolingos-master-growth-hacker/)).
- **The best complex-app onboardings teach exactly one workflow, interactively, and hide everything else.** Superhuman rebuilt onboarding around a single objective (Inbox Zero) in a *synthetic practice inbox*, and reports activation moving 40% → 50% just from re-ordering which shortcuts get taught ([First Round Review, 2025-04-23](https://review.firstround.com/superhuman-onboarding-playbook/)).
- **Mandatory-but-fast beat skippable when the step is genuinely load-bearing:** Superhuman's setup completion went 30% → 98% after moving it to a full-screen panel with smart defaults and removing the skip affordance (same source). This cuts against the reflexive "always let users skip" advice.
- **Nobody shows a feature tour of a dense product.** Notion, Slack and Canva instead *pre-fill the workspace* — templates, auto-created channels, starter designs — so the first screen is never empty ([Appcues/GoodUX on Notion](https://goodux.appcues.com/blog/notions-lightweight-onboarding); [UserGuiding on Slack, 2024-02-28](https://userguiding.com/blog/slack-user-onboarding-teardown); [Appcues on Canva](https://www.appcues.com/blog/canva-growth-process)).
- **Fantasy-sports apps differ structurally in three ways:** identity is portable and public (a Sleeper username is a working API key-less handle), personalization comes from *league context* not a questionnaire, and demand is violently seasonal.
- **The nearest competitive analog to FTF's Elo vote is KeepTradeCut, and its onboarding *is* the contribution.** KTC's entry action is a single 3-player Keep/Trade/Cut vote, it has no paywall by design ("we would actually suffer from implementing any sort of paywall"), and it uses cookies rather than accounts to avoid re-prompting ([KTC About](https://keeptradecut.com/about), [KTC FAQ](https://keeptradecut.com/frequently-asked-questions)).
- **Money-handling fantasy apps invert the "value first" rule** because KYC/geolocation forces identity early — which is why Sleeper's own flow is phone → SMS code → username → ToS → *deposit* ([Sleeper Support](https://support.sleeper.com/en/articles/5556060-how-do-i-get-started)). FTF has no such constraint, and that is an advantage worth not squandering.
- **Benchmarks are brutal and should temper any target-setting:** reported global 30-day onboarding *completion* was ~8.4% in Q2 2025, with complex apps landing 50–65% completion of the flow itself vs. 70–80% for simple ones ([Business of Apps, 2025](https://www.businessofapps.com/data/app-onboarding-rates/)).

**Evidence tags used below:** `[P]` primary (company/team member speaking on record) · `[S]` secondary (independent teardown or reported case study) · `[W]` weak (SEO/affiliate/likely-AI content, or claim reached only via a search snippet).

---

## Group 1 — Productivity & creation tools

### Superhuman (email) — the most useful case in the corpus `[P]`

Source: [First Round Review, "How to Build and Scale Onboarding," 2025-04-23](https://review.firstround.com/superhuman-onboarding-playbook/); supporting: [20VC with Rahul Vohra](https://www.thetwentyminutevc.com/rahulvohra-2).

Flow, as it evolved:

1. **Human-led phase first.** Every new user got a 1:1 video onboarding: teach shortcuts, customize settings, migrate email. Reported outcomes: **65%+ email migration completion** and **~2x activation vs. self-serve**. Vohra's scaling math on 20VC: roughly **60–70 onboarding specialists** would support $100M ARR — i.e., concierge is not automatically unscalable.
2. **A pre-onboarding Typeform** collected customer context *before* the session — the only meaningful data ask, and it happened outside the product.
3. **Productized v1** taught navigation shortcuts (`j`/`k`). **v2 abandoned navigation for the objective**: shortcuts that serve Inbox Zero (`e` = done, `h` = remind me). Activation **40% → 50%**.
4. **Full-screen mandatory setup panels** replaced a tucked-away checklist, with smart defaults for fast progression. Completion **30% → 98%** after removing skip options.
5. **A synthetic practice inbox** — a safe fake inbox the user clears to zero before touching real mail.
6. **Timed interruptions at high-receptiveness moments** — e.g., the Undo Send tutorial fires immediately *after* the user sends an email. Feature opt-in **45% → 80%**.

Stated design principles: onboarding should be **opinionated, interruptive, and interactive**. Deliberately deferred: navigation complexity, advanced shortcuts, and any flow not relevant to a brand-new user.

### Notion `[S]`, dated

Sources: [Appcues/GoodUX](https://goodux.appcues.com/blog/notions-lightweight-onboarding) (undated; internally references a 2018 video — **treat as dated**); [Candu](https://www.candu.ai/blog/how-notion-crafts-a-personalized-onboarding-experience-6-lessons-to-guide-new-users) `[S]`.

Reported flow: email/Google sign-up → profile (name, optional photo) → workspace creation → **optional** data import (Trello, Asana, Google Docs) → **optional** app/clipper installs → a "Getting Started" page taught by inline tooltips ("Type `/` for slash commands") → **five personalized templates** selected from the signup answers.

The signup survey asks *how you plan to use it* (work / personal / school) and *your role* — two questions, both of which visibly change what you see next. The teardown's stated rationale for keeping import optional is explicit: connecting your existing stack "is a big ask for folks who may be evaluating Notion more casually."

Deliberately not shown up front: the database/relation/formula surface — the actual depth of Notion — which is left to templates and slash-command discovery.

### Slack `[S]`

Sources: [UserGuiding teardown, 2024-02-28](https://userguiding.com/blog/slack-user-onboarding-teardown); [Userpilot](https://userpilot.com/blog/slack-onboarding/) `[S]`.

Sign-up asks three things in sequence: email → company/team identity → workspace purpose → invite teammates. Then, critically, **Slack does not hand you an empty workspace**: it auto-creates channels (a company channel, a general channel, a social channel), each opening with a welcome message and two or three native task cards ("invite teammates", "post a welcome"). The tasks read as channel content, not as a checklist overlay, so they guide without blocking. Everything else is contextual — empty states, tooltips, hover microcopy, Slackbot.

Slack's famous activation metric — **2,000 team messages sent → ~93% retention** — is repeated across many secondary sources ([June](https://www.june.so/blog/activation-playbook), [Appcues](https://www.appcues.com/blog/aha-moment-examples)) `[S/W]`, but I did not find a primary Slack publication for the number in this pass. Treat the *shape* of the idea (activation = a behavioral threshold, not a screen completed) as the durable lesson; treat "2,000" as folklore until sourced.

### Figma `[S]`, thin/dated

Source: [Appcues/GoodUX](https://goodux.appcues.com/blog/figmas-animated-onboarding-flow) (undated). Figma offers an **opt-in** tour via a welcome modal, then walks differentiators using animated tooltips: importing Sketch files, using design elements, inviting collaborators, with links out for complex features.

Note on evidence: the well-known [UserOnboard Figma teardown](https://www.useronboard.com/how-figma-onboards-new-users/) is a gated video — the page itself carries no readable step list. The frequently-cited [Growthmates "10 Onboarding Teardowns"](https://www.growthmates.news/p/10-onboarding-teardowns-from-top) (2025-05-27) is paywalled after the intro. Both are commonly cited second-hand; neither was independently verifiable here.

### Canva `[S]` with `[P]` quotes

Source: [Appcues on Canva's growth process](https://www.appcues.com/blog/canva-growth-process), quoting growth manager Xingyi Ho.

The onboarding mechanism is **templates plus trivially easy starter challenges** (change a circle's color; put a hat on a monkey) — competence-building micro-wins before any real task. Process detail: opportunity-spotting from high-volume/low-activation channels → user tests and churn surveys → experiment on 5% → Amplitude analysis → roll out. Reported results: **+10% activation** on the poster feature, **30–50 experiments in a year**, experiment cycle time **4–6 weeks → 2–3 weeks**, **10,000+ additional MAU**. Ho's key observation: *"When users want to create a design, they usually create the design on the first day"* — i.e., first-session or never.

---

## Group 2 — Consumer habit apps

### Duolingo — the delayed-signup canon `[P]`

Source: [First Round Review, Gina Gotthilf (VP Growth), published 2017-07-17, updated 2024-11-23](https://review.firstround.com/the-tenets-of-a-b-testing-from-duolingos-master-growth-hacker/).

- Moving the sign-up screen back a few steps: **"about a 20% increase in DAUs."**
- Follow-up finding: a prominent "Discard my progress" button was causing unintended exits; replacing it with a subtle **"Later"** created a *soft wall*. Combined subsequent hard/soft-wall optimization: **+8.2% DAU**, measured years later on a much larger base.
- Mechanism named by secondary analysis: the endowed-progress / sunk-cost effect — a wall converts better *after* investment.

Retention tactics, from [Growth.Design's Duolingo case study](https://growth.design/case-studies/duolingo-user-retention) `[S]`: reduce choice (Hick's Law) with one-tap lesson shortcuts; lower difficulty on return ("happy path"); a 100-gem welcome-back reward (Zeigarnik); a **gem wager on a 7-day commitment streak reported at +14% D7 retention**; explicit **exit points** so a session can end cleanly; and auto-suppressing notifications for inactive users.

Scale/velocity claims — ~1,200 experiments/year, 8.9% MAU→paid conversion, 50M DAU in Q3 2025 — surfaced only through [Relaunch.ai's 2026 teardown](https://relaunch.ai/blog/duolingo-onboarding-teardown-7-b-tests-behind-their-9-conver.html) and search summaries `[W]`. Directionally consistent with Duolingo's public reporting, but not verified here.

### Spotify `[W]`

Reached only through Medium teardowns and search summaries ([example](https://medium.com/@smarthvasdev/deep-dive-into-spotify-s-user-onboarding-experience-f2eefb8619d6)). Reported pattern: pick **3+ artists** on first launch → a playlist is generated immediately → music playing "within two minutes of install." The structural lesson — *convert the preference question directly into a visible artifact in the same session* — is worth carrying even though the sourcing is opinion-grade.

### Discord — server-level onboarding as progressive disclosure `[S]`

Discord's own [Community Onboarding FAQ](https://support.discord.com/hc/en-us/articles/11074987197975-Community-Onboarding-FAQ) returned 403 to automated fetch; the description below comes from search-result summaries of that page plus [a community case study](https://medium.com/@taylorbdallas/discord-server-onboarding-a-case-study-3d7c4d7e0685) `[S/W]`.

Pattern: a new member answers a few short questions; their answers assign roles and produce a **personalized channel list** rather than the full firehose; answers are revisable any time from a persistent **Channels & Roles** tab. This is the cleanest published example of *scoping the visible surface by declared interest, reversibly* — the user isn't told features are hidden, they're just not present, and the un-hide control is a permanent tab rather than a one-time modal.

---

## Group 3 — Fantasy sports and sports-adjacent

### Sleeper `[P]` for the flow

Source: [Sleeper Support — How Do I Get Started](https://support.sleeper.com/en/articles/5556060-how-do-i-get-started), [Intro to Sleeper Fantasy Football](https://support.sleeper.com/en/articles/1876010-intro-to-sleeper-fantasy-football), [sleeper.com/fantasy-football](https://sleeper.com/fantasy-football).

Sign-up: **mobile phone number → SMS verification code → choose a username → accept ToS → a landing page asking how you want to use the app.** Phone registration requires no password. Then, for the DFS side, the flow immediately pushes **wallet setup and a deposit** ("your total balance is used to enter and participate in DFS games"). League-side onboarding is separate and much lighter: league creation "in under a minute" and cross-platform invite links.

Two observations relevant to FTF. First, **one field per screen** — reviewers consistently note you're "usually only entering one piece of information before clicking on to the next page" `[W, review sites]`. Second, Sleeper's identity primitive is a **public username**, and the [Sleeper API](https://docs.sleeper.com/) is **read-only with no authentication and no OAuth** (~90 req/min/IP; guidance to stay well under 1000/min) ([Zuplo guide](https://zuplo.com/learning-center/sleeper-api)) `[P/S]`. That single fact is why essentially every third-party dynasty tool onboards with "type your Sleeper username" instead of an OAuth handshake.

### ESPN Fantasy `[P]`

Sources: [ESPN, 2025-08-04](https://www.espn.com/fantasy/football/story/_/id/45844949/2025-fantasy-football-where-play-new-features-espn); [ESPN Press Room, 2025-08](https://espnpressroom.com/us/press-releases/2025/08/espn-fantasy-football-30th-anniversary-new-design-new-features-all-new-fantasy-app-for-2025/); [ESPN Fan Support](https://support.espn.com/hc/en-us/articles/39730562109204-ESPN-Fantasy-App-What-s-New-in-2025).

The 2025 rebuild is instructive because it's a dense app *re-architecting for onboarding and re-entry* rather than adding features:

- A **new evergreen tab for creating or joining a league** — i.e., the acquisition action was promoted out of a seasonal flow into permanent navigation.
- A **personalized home screen** showing analyst rankings scoped to *your* starting lineup, plus Top Performing Players / Player Rankings / Free Agent Finds modules — editorial content placed next to the transaction it implies.
- A **dynamic roster dashboard** surfacing timely action items (waiver reminders, trade notifications) rather than requiring the user to go find them.
- An **optimized add/drop** with quick-action buttons that avoid a trip to the player card.

Separately, the main ESPN app's first launch asks **which teams to follow** and offers alert setup, and that choice propagates across the ESPN app, ESPN.com, connected TVs, the Fantasy app and ESPN+ ([ESPN personalization](https://www.espn.com/casualgames/story/_/id/35903488/ready-benefits-personalized-espn-account)). One declared preference, reused everywhere.

### Yahoo Fantasy `[P]`, minimal

Source: [Yahoo Help](https://help.yahoo.com/kb/fantasy-football/sign-join-league-create-sln24156.html), [Yahoo Sports guide](https://sports.yahoo.com/play-yahoo-fantasy-football-joining-creating-league-015015629.html). The first real decision is a fork: **join a league** (public / private / prize) or **create one**. There is essentially no product-education layer; Yahoo assumes the league is the unit of onboarding and the commissioner does the teaching. Notable as the *low* end of the range — a feature-dense product with a near-zero first-run experience.

### Underdog Fantasy `[W]`, review-site sourced

Reviews consistently describe a "famously fast" signup, **$10 minimum deposit**, a **$5 first entry** to trigger the welcome bonus, and **one-tap draft entry** ([Saturday Down South](https://www.saturdaydownsouth.com/dfs/underdog-fantasy/underdog-fantasy-review/), [ats.io](https://ats.io/dfs/underdog/)). All available sources are affiliate/promotional; treat the flow description as plausible and the praise as marketing. The genuinely transferable point: Underdog's onboarding is short **because the product concept (Best Ball) is short** — they cut product surface to cut onboarding, not the reverse.

### PrizePicks `[P/S]` — strongest fantasy-side numbers

Sources: [Braze customer case study](https://www.braze.com/customers/prizepicks-case-study); [Built In](https://builtin.com/articles/how-prizepicks-scaling-its-platform-and-what-its-next-growth-chapter-looks); [SGX Studio product intelligence report, 2025-12-16](https://sgx.studio/product-intelligence/report-prizepicks/).

- The tutorial is **"Pick 2, More/Less"** and takes seconds. PrizePicks **strips odds notation entirely** (-110, +240), collapsing the core decision to a binary. This is a deliberate reduction in *domain literacy required*, not just in UI steps.
- A **"protected play"** (risk-free first entry) removes the fear cost of the first action.
- Reported lifecycle results via Braze/Segment: **+30% app-based first-time depositors** and **+60% conversion of first deposit into first entry**.
- A free-to-play game (**Streaks**) exists partly as a top-of-funnel/engagement product: **+10% new users** at launch.

The SGX report is thorough on mechanism but carries no first-session conversion metrics of its own; it also reads as an analyst product, not a company statement.

### KeepTradeCut — the closest structural analog to FTF `[P]`

Sources: [KTC home](https://keeptradecut.com/), [About](https://keeptradecut.com/about), [FAQ](https://keeptradecut.com/frequently-asked-questions), [Power Rankings](https://keeptradecut.com/dynasty/power-rankings), [Trade Database](https://keeptradecut.com/dynasty/trade-database).

- **The onboarding action and the data-collection action are the same thing**: rank three players — Keep / Trade / Cut. One vote, ~5 seconds, no domain jargon, no account.
- The stated business rationale is a **contribute-to-consume** loop with an explicit anti-paywall stance: *"Since we rely on the community to feed our rankings and other tools, we would actually suffer from implementing any sort of paywall."*
- The FAQ notes that **accepting cookies lets you avoid voting every visit** — identity is handled by a cookie, not an account, and the vote gate is framed as the cost of entry rather than a signup.
- Scale claimed on-site: **26,486,870 crowdsourced data points** for power rankings, and a trade database of **25,000 real trades** `[P, self-reported]`.
- Instruction copy deliberately strips context: rank the three players *in isolation*, without considering roster fit or trade-market dynamics. The task is made easier than the real judgment it approximates.

I could not directly verify the visual hierarchy of the KTC homepage (fetch returned truncated content), so the "vote prompt front and center" characterization rests on the FAQ/About descriptions plus search summaries `[S]`.

### FantasyCalc and Dynasty Nerds / DynastyGM `[P]`, self-reported

- **FantasyCalc** ([fantasycalc.com](https://fantasycalc.com/)): values generated from **3,598,712 real fantasy trades**, values customized to *your league settings*, and a **league sync** that yields power rankings, waiver pickups, and trade targets "all individualized to your league." Onboarding = paste league, get personalized output.
- **Dynasty Nerds / DynastyGM** ([support](https://support.dynastynerds.com/article/82-what-is-the-dynasty-nerds-app-dynastygm), [league host support](https://support.dynastynerds.com/article/56-league-host-support), [plans](https://www.dynastynerds.com/plans-and-pricing/)): syncs Sleeper, MFL, Fleaflicker, FFPC; **new accounts sync within a few minutes**; rosters refresh in the background with manual refresh available. The free tier is explicitly positioned as *"hands-on access to every tool so you can see the value before upgrading"* — breadth-first free access, paywall at depth/frequency rather than at the door.
- Note the recurring failure mode this category documents: Dynasty Nerds maintains a dedicated ["Why Are My Leagues Not Syncing?"](https://support.dynastynerds.com/article/51-league-sync-error) support article. **Import is the onboarding, so import failure is onboarding failure.**

---

## Cross-cutting patterns

1. **Value before identity — with one clear exception.** Duolingo `[P]`, KTC `[P]`, Canva `[S]` and Notion's optional-import stance `[S]` all put a real product moment before the ask. The exception is money: Sleeper DFS, Underdog and PrizePicks front-load account + deposit + KYC because law and geolocation require it ([KYC in DFS overview](https://www.idcentral.io/blog/fantasy-app-kyc-how-to-accelerate-onboarding/)) `[S]`. Apps that copy the DFS pattern without the DFS constraint are importing friction for free.
2. **Ask few questions, and spend every answer visibly in the same session.** Notion (2 questions → 5 templates), Spotify (3 artists → a playlist), Discord (a few questions → a scoped channel list), ESPN (favorite teams → a home screen). None of these questionnaires are longer than the payoff they produce.
3. **Never show an empty state.** Slack pre-creates channels with task cards; Notion pre-loads templates; Canva pre-loads starter designs; Superhuman fabricates a practice inbox. The generalization: for a dense product, the correct opposite of "overwhelming" is not "blank" — it's "pre-populated and obviously editable."
4. **One canonical first action, taught by doing.** Superhuman = clear the inbox. Duolingo = finish a lesson. PrizePicks = make two picks. KTC = cast one vote. Canva = change a circle's color. None of them run a tour of the feature set. Figma's tour is the outlier — and it's **opt-in** `[S]`.
5. **Make the load-bearing step unskippable; make everything else contextual.** Superhuman's 30% → 98% completion after removing skip is the sharpest data point against blanket "always allow skip" advice `[P]`. The counterweight is that they only did this for a short, defaulted, genuinely necessary setup.
6. **Teach features at the moment of receptiveness.** Undo Send taught right after sending `[P]`; Slack's tooltips and empty states `[S]`; Discord's permanent Channels & Roles tab `[S]`; ESPN's roster dashboard surfacing waiver reminders when they're actionable `[P]`. Progressive disclosure as a *trigger* discipline, not a schedule (the underlying principle traces to Nielsen, 1995; note that the widely-quoted "20–40% faster task completion / 35% fewer support tickets" figures circulate on secondary blogs *citing* NN/g and I could not verify them at source) `[W]`.
7. **Human-led onboarding is a research instrument you later productize.** Superhuman's sequence — concierge → learn what actually blocks people → build the automated version — is the only case in the corpus with a stated method for *how they knew what to build* `[P]`.
8. **Activation is a behavioral threshold, not a completed flow.** Slack's message count `[S/W]`, Superhuman's activation %, Canva's "created a design on day one" `[P]`. Onboarding-completion rate is a vanity proxy; the benchmark data shows why (30-day onboarding completion ~8.4% globally in Q2 2025, median activation ~25%) ([Business of Apps](https://www.businessofapps.com/data/app-onboarding-rates/)) `[S]`.
9. **Velocity beats insight.** Canva 30–50 experiments/year `[P]`, Duolingo ~1,200/year `[W]`. Both attribute results to compounding small wins rather than one redesign.

### Where fantasy-sports apps genuinely differ from productivity apps

| Dimension | Productivity/consumer | Fantasy sports |
|---|---|---|
| Identity primitive | Email/OAuth, private | **Public username**; Sleeper's API is read-only and auth-free, so "type your username" replaces OAuth entirely ([docs.sleeper.com](https://docs.sleeper.com/)) |
| Personalization source | Self-reported questionnaire (role, goal) | **Imported league context** — roster, scoring format, TE premium, contender/rebuild — objectively true, zero user effort |
| Onboarding failure mode | User abandons a form | **Sync fails** (Dynasty Nerds has a support article for exactly this) |
| Demand curve | Roughly flat | **Violently seasonal** — draft season, rookie drafts, in-season waiver panic; ASO and install volume follow the calendar ([AppTweak on sports seasonality](https://www.apptweak.com/en/aso-blog/how-to-leverage-app-store-seasonality-for-sports)) `[S]` |
| Multiplayer dependency | Optional (invite teammates) | **Mandatory** — a trade needs a counterparty who is a real person in your league |
| Regulatory friction | None | KYC/geolocation for money apps only; tools are exempt |
| Data loop | Users consume | **Contribute-to-consume** (KTC): the onboarding act *is* the data-collection act |

The seasonality point deserves emphasis because none of the productivity case studies address it: a fantasy tool's first-run experience has to work for a user arriving mid-draft, a user arriving in a dead March offseason, and a user arriving in a Tuesday-morning waiver scramble. Industry commentary on year-round engagement is thin and mostly vendor-authored `[W]`, with one interesting exception — [Griddy's](https://news.bettingstartups.com/p/how-griddy-turned-fantasy-football-into-a-year-round-game) approach of borrowing a team-building game loop (FIFA/Madden style) rather than a box-score loop to survive the offseason `[S]`.

---

## Evidence quality notes

**Strong (`[P]`, on-record, with numbers):** First Round's Superhuman playbook (2025-04-23) and Duolingo/Gotthilf piece (2017, updated 2024-11-23); Appcues' Canva write-up quoting Xingyi Ho; ESPN's own 2025 app announcements; Sleeper's own support docs and API docs; KeepTradeCut's own About/FAQ; Dynasty Nerds' and FantasyCalc's own product pages; Braze's PrizePicks case study (vendor-published, so results are selected but specific).

**Moderate (`[S]`):** UserGuiding's Slack teardown (2024-02-28); Growth.Design's Duolingo retention study; SGX Studio's PrizePicks report (2025-12-16); Business of Apps onboarding benchmarks.

**Weak or unverifiable (`[W]`) — flagged wherever used:**
- **Undated teardowns.** Appcues/GoodUX pieces on Notion and Figma carry no publication date; the Notion one internally references a 2018 video. **Onboarding flows change every few quarters — assume both are stale.**
- **Gated/blocked sources.** The Growthmates "10 Onboarding Teardowns" (2025-05-27) is paywalled past the intro. UserOnboard's Figma teardown is a gated video with no readable transcript. Discord's own Community Onboarding FAQ returned HTTP 403 to automated fetch, so Discord's mechanics here come from search summaries of that page.
- **Affiliate/promotional.** Every Underdog description available is from DFS-affiliate review sites with active promo codes on the page.
- **Likely AI-generated SEO content.** Relaunch.ai's "Duolingo Onboarding Teardown (2026)" and several dynasty-tool explainer sites read as generated content; their claims are directionally plausible but should not be cited without corroboration.
- **Folklore.** Slack's "2,000 messages → 93% retention" appears in dozens of secondary sources with no primary Slack citation found in this pass.
- **Second-hand statistics.** The progressive-disclosure numbers attributed to NN/g (20–40% task-time reduction, 35% fewer tickets) appear only on vendor blogs citing NN/g, not on nngroup.com.
- **Search-snippet-only claims** (Spotify's flow, Discord's FAQ details, Duolingo's 2025 DAU figures, KTC's homepage layout) are marked inline and should be re-verified by direct observation before anyone builds on them.

**Coverage gaps in this pass:** no first-hand screenshots or walkthroughs of any current flow (everything is documentary); no material found on FantasyCalc's or KTC's onboarding *decisions* from their teams (only their product surface); Yahoo Fantasy has essentially no published onboarding rationale; the web-search budget was exhausted before I could source community sentiment (e.g., Reddit) on whether KTC's vote gate is experienced as friction or as fair trade.

---

## Implications for FTF (hypotheses only — not recommendations)

These are framed as testable propositions, each traceable to a case above. None is validated for FTF.

- **H1 — Vote before identity.** FTF's 3-player Elo matchup is structurally identical to KTC's Keep/Trade/Cut and to Duolingo's first lesson: a ~5-second, low-literacy, satisfying action. Hypothesis: letting a cold user cast one matchup vote *before* any Sleeper sign-in produces the endowed-progress effect Duolingo measured, and doubles as data collection from users who never convert. Risk to test: FTF's vote quality may depend on the voter being a real dynasty player, in which case an anonymous-vote channel needs a trust weight.
- **H2 — Sleeper username is the whole ask.** Because the Sleeper API is read-only and auth-free, FTF's identity ask can be a single text field that immediately yields rosters, league settings and rivals — a personalization payload no questionnaire could match. Hypothesis: one field, one screen, instantly redeemed, outperforms any multi-question onboarding survey. Corollary from Dynasty Nerds: **the sync-failure path is part of the onboarding design**, not an error state to bolt on later.
- **H3 — Pick one canonical first action, not a tour of nine features.** Every strong case teaches exactly one workflow. Hypothesis: FTF's should be *"here is one mutual-gain trade the finder built from your actual roster"* — the output that no competitor produces — with the calculator, boards, notification inbox, tier ladder and send-in-platform all left undiscovered in session one.
- **H4 — One unskippable, defaulted step is acceptable.** Superhuman's 30% → 98% suggests that if exactly one step genuinely gates all value (for FTF, the Sleeper handle + league selection), a full-screen non-skippable panel with smart defaults may beat a dismissible prompt. This is worth an experiment precisely because it contradicts the usual advice.
- **H5 — Trigger-based reveal for the rest.** Superhuman's "Undo Send taught right after sending" maps cleanly: teach the want/accept boards the first time a user rejects a suggested trade; teach send-in-platform the first time a user says yes to one; teach the notification inbox the first time something would have notified them. Discord's persistent Channels & Roles tab is a model for making the hidden surface findable without a modal.
- **H6 — Define activation behaviorally before redesigning anything.** Slack/Canva/Superhuman all optimize against a behavioral threshold, not flow completion. Hypothesis: FTF's candidate is a compound like *"viewed ≥3 trade suggestions AND cast ≥N matchup votes within 7 days"* — but it must be derived from FTF's own retention data, not assumed. Benchmarks say the honest baseline is low (median activation ~25%).
- **H7 — Seasonal onboarding variants.** No productivity case study faces this, and every fantasy app does. Hypothesis: an August arrival (draft imminent, trade urgency high) and a March arrival (offseason, exploration mode) need different first actions — and the offseason variant may lean harder on the vote loop and tier ladder, which are season-independent, than on trade discovery.
- **H8 — Contribute-to-consume as explicit framing.** KTC states outright that a paywall would damage its data. FTF's Elo has the same dependency. Hypothesis: telling users *why* the vote matters ("your votes set the market these trades are priced against") converts a chore into a purposeful act — and is a differentiator from calculators whose values arrive from nowhere.
- **H9 — Concierge as research, at FTF's scale.** Superhuman's method is directly available to a small team: manually onboard the next 20 users on a call, watch where they stall, then productize. This is the cheapest way to learn which of H1–H8 is actually the binding constraint.

---

## Sources

**Productivity / creation**
- First Round Review — Superhuman onboarding playbook (2025-04-23): https://review.firstround.com/superhuman-onboarding-playbook/
- 20VC — Rahul Vohra on scaling 1:1 onboarding: https://www.thetwentyminutevc.com/rahulvohra-2
- Lenny's Newsletter — Rahul Vohra interview: https://www.lennysnewsletter.com/p/superhumans-secret-to-success-rahul-vohra
- Appcues/GoodUX — Notion's lightweight onboarding (undated, refs 2018): https://goodux.appcues.com/blog/notions-lightweight-onboarding
- Candu — How Notion crafts a personalized onboarding experience: https://www.candu.ai/blog/how-notion-crafts-a-personalized-onboarding-experience-6-lessons-to-guide-new-users
- Appcues/GoodUX — Figma's animated onboarding flow (undated): https://goodux.appcues.com/blog/figmas-animated-onboarding-flow
- UserOnboard — How Figma onboards new users (gated video): https://www.useronboard.com/how-figma-onboards-new-users/
- UserGuiding — Slack onboarding teardown (2024-02-28): https://userguiding.com/blog/slack-user-onboarding-teardown
- Userpilot — Slack onboarding flow: https://userpilot.com/blog/slack-onboarding/
- June — Activation playbook (Slack 2,000-message claim): https://www.june.so/blog/activation-playbook
- Appcues — Aha moment examples: https://www.appcues.com/blog/aha-moment-examples
- Appcues — How Canva's growth team improves activation +10%: https://www.appcues.com/blog/canva-growth-process
- Growthmates — 10 onboarding teardowns from top PLG products (2025-05-27, paywalled): https://www.growthmates.news/p/10-onboarding-teardowns-from-top

**Consumer habit apps**
- First Round Review — Tenets of A/B testing from Duolingo's growth lead (2017-07-17, upd. 2024-11-23): https://review.firstround.com/the-tenets-of-a-b-testing-from-duolingos-master-growth-hacker/
- Growth.Design — Duolingo user retention case study: https://growth.design/case-studies/duolingo-user-retention
- Taplytics — How Duolingo A/B tested delayed sign-ups: https://taplytics.com/blog/duolingo-ab-test-onboarding/
- Relaunch.ai — Duolingo onboarding teardown (2026; likely AI-generated): https://relaunch.ai/blog/duolingo-onboarding-teardown-7-b-tests-behind-their-9-conver.html
- Discord — Community Onboarding FAQ (403 to automated fetch): https://support.discord.com/hc/en-us/articles/11074987197975-Community-Onboarding-FAQ
- Taylor B. Dallas — Discord server onboarding case study: https://medium.com/@taylorbdallas/discord-server-onboarding-a-case-study-3d7c4d7e0685
- Smarth Vasdev — Deep dive into Spotify's onboarding: https://medium.com/@smarthvasdev/deep-dive-into-spotify-s-user-onboarding-experience-f2eefb8619d6

**Fantasy sports**
- Sleeper Support — How do I get started: https://support.sleeper.com/en/articles/5556060-how-do-i-get-started
- Sleeper Support — Intro to Sleeper Fantasy Football: https://support.sleeper.com/en/articles/1876010-intro-to-sleeper-fantasy-football
- Sleeper — Fantasy football product page: https://sleeper.com/fantasy-football
- Sleeper API docs: https://docs.sleeper.com/
- Zuplo — Comprehensive guide to the Sleeper API: https://zuplo.com/learning-center/sleeper-api
- ESPN — 2025 fantasy football new app features (2025-08-04): https://www.espn.com/fantasy/football/story/_/id/45844949/2025-fantasy-football-where-play-new-features-espn
- ESPN Press Room — 30th anniversary all-new fantasy app (2025-08): https://espnpressroom.com/us/press-releases/2025/08/espn-fantasy-football-30th-anniversary-new-design-new-features-all-new-fantasy-app-for-2025/
- ESPN Fan Support — What's new in 2025: https://support.espn.com/hc/en-us/articles/39730562109204-ESPN-Fantasy-App-What-s-New-in-2025
- ESPN — Benefits of a personalized ESPN account: https://www.espn.com/casualgames/story/_/id/35903488/ready-benefits-personalized-espn-account
- Sportico — ESPN fantasy app update (2025): https://www.sportico.com/business/media/2025/espn-fantasy-app-update-design-nfl-draft-leagues-yahoo-1234866229/
- Yahoo Help — Sign up, join, create a league: https://help.yahoo.com/kb/fantasy-football/sign-join-league-create-sln24156.html
- Yahoo Sports — How to play Yahoo Fantasy Football: https://sports.yahoo.com/play-yahoo-fantasy-football-joining-creating-league-015015629.html
- Saturday Down South — Underdog review (affiliate): https://www.saturdaydownsouth.com/dfs/underdog-fantasy/underdog-fantasy-review/
- ats.io — Underdog review (affiliate): https://ats.io/dfs/underdog/
- Braze — PrizePicks case study (30% / 60% lifts): https://www.braze.com/customers/prizepicks-case-study
- Built In — How PrizePicks is scaling its platform: https://builtin.com/articles/how-prizepicks-scaling-its-platform-and-what-its-next-growth-chapter-looks
- SGX Studio — PrizePicks product intelligence report (2025-12-16): https://sgx.studio/product-intelligence/report-prizepicks/
- KeepTradeCut — Home: https://keeptradecut.com/
- KeepTradeCut — About: https://keeptradecut.com/about
- KeepTradeCut — FAQ: https://keeptradecut.com/frequently-asked-questions
- KeepTradeCut — Power Rankings (26.4M data points): https://keeptradecut.com/dynasty/power-rankings
- FantasyCalc: https://fantasycalc.com/
- Dynasty Nerds — What is the app / DynastyGM: https://support.dynastynerds.com/article/82-what-is-the-dynasty-nerds-app-dynastygm
- Dynasty Nerds — Supported league hosts: https://support.dynastynerds.com/article/56-league-host-support
- Dynasty Nerds — Why are my leagues not syncing: https://support.dynastynerds.com/article/51-league-sync-error
- Dynasty Nerds — Plans and pricing: https://www.dynastynerds.com/plans-and-pricing/
- Betting Startups — How Griddy turned fantasy football into a year-round game: https://news.bettingstartups.com/p/how-griddy-turned-fantasy-football-into-a-year-round-game

**Benchmarks, patterns, and constraints**
- Business of Apps — App onboarding rates (2025): https://www.businessofapps.com/data/app-onboarding-rates/
- Business of Apps — Mobile app onboarding guide: https://www.businessofapps.com/guide/app-onboarding/
- NN/g — Progressive disclosure (video): https://www.nngroup.com/videos/progressive-disclosure/
- userTourKit — Progressive disclosure in onboarding: https://usertourkit.com/blog/progressive-disclosure-onboarding
- RevenueCat — State of Subscription Apps 2025: https://www.revenuecat.com/state-of-subscription-apps-2025
- RevenueCat — Optimizing paywall placement: https://www.revenuecat.com/blog/growth/paywall-placement
- Adapty — High-performing paywalls in 2026: https://adapty.io/blog/high-performing-paywall-2026/
- IDcentral — Fantasy app KYC and onboarding friction: https://www.idcentral.io/blog/fantasy-app-kyc-how-to-accelerate-onboarding/
- AppTweak — App store seasonality for sports: https://www.apptweak.com/en/aso-blog/how-to-leverage-app-store-seasonality-for-sports
