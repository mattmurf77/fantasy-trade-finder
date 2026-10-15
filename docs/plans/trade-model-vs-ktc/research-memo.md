# Trade model vs KTC: research memo

> **Purpose:** the research half of the joint plan for the operator's 2026-10-15 trade-modeling ask. It covers what KeepTradeCut (KTC) launched, how KTC and others get Sleeper trade data, what the published terms allow, what FTF already holds, what a broader corpus would cost to store, and what sample sizes the questions need. The eval design, bars and verdicts live in [eval-plan.md](eval-plan.md).
>
> **Owner:** `trades-pm`. **Status:** planning, 2026-10-15. Research only. Nothing has been run, fetched or built. Building anything needs its own scope block ([`docs/templates/feature-scope.md`](../../templates/feature-scope.md)).
>
> **Sources:** two research passes for `trades-pm`, read-only, web pages read 2026-10-15. Repo citations are re-checked against `origin/main` @ `678834ab` (see [Citation notes](#citation-notes)).
>
> **Confidence labels:** **confirmed** (a primary source says so), **likely** (indirect evidence), **unknown** (no evidence found), **estimate** (arithmetic on stated assumptions).
>
> **This repo is public.** No KTC values, rankings or page content are copied here. KTC and Sleeper statements are paraphrased with their URL. At most one short clause is quoted per source. Nothing here is legal advice: where terms matter, this memo says only what the published terms prohibit without written permission.

## Table of contents

- [1. Question and context](#1-question-and-context)
- [2. What KTC launched](#2-what-ktc-launched)
- [3. How KTC and competitors get Sleeper trade data](#3-how-ktc-and-competitors-get-sleeper-trade-data)
- [4. Data rights](#4-data-rights)
- [5. FTF's current corpus and eval harness](#5-ftfs-current-corpus-and-eval-harness)
- [6. Storage cost of a broader corpus](#6-storage-cost-of-a-broader-corpus)
- [7. Feasibility and sample sizes](#7-feasibility-and-sample-sizes)
- [8. Decisions needed](#8-decisions-needed)
- [9. Handoffs](#9-handoffs)
- [Citation notes](#citation-notes)
- [Sources](#sources)

---

## 1. Question and context

The operator, 2026-10-15:

> "Trade Modeling: 1. Want to compare the three models in calibration against KTC's new trade driven rankings and evaluation. 2. Want to evaluate whether league specific valuations and adjustments make sense. Do research on how KTC gets raw sleeper trade data.. I'm assuming it's available, but right now we're really just using my leagues for eval."

**The three models** are the round-3 Calibration arms (`living-memory/NEXT.md:80`):

1. the filtered live engine (`owner_v2_bilateral` plus `deck.quality_filters`, D-193 and D-207);
2. value core v4 (`trade.value_core`, D-206);
3. fit A and fit B (`backend/fit_engine.py`, D-200).

All three price trades on **one shared market board, C0**: DynastyProcess (DP) values blended with KTC's *crowd* ordering at `ktc_blend_weight` 0.5 (`backend/data_loader.py:149-216`; `backend/database.py:2904`; D-013). They differ in how they build and select trades, not in their market source.

**Comparator shorthand** (defined fully in [eval-plan.md §1.1](eval-plan.md#11-comparators-by-data-rights-tier)):

| Key | Meaning |
|---|---|
| C0 | FTF consensus as stamped on each Calibration card (DP plus KTC crowd ordering) |
| C1 | DP only (`ktc_blend_weight = 0`, or dated DP boards) |
| K1 | KTC crowd values (what FTF's production scrape reads) |
| K2 | KTC Tradesourced values and the calculator on them ("trade-driven") |
| F2 | A substitute trade-driven source whose terms allow evaluation |

**Short answers:**

- **Ask 1 (compare against KTC's trade-driven values).** KTC's published terms prohibit collecting K2 values or calculator verdicts at scale without written permission, and they prohibit FTF's existing K1 scrape on the same grounds. The comparison can run **lawfully today only against C1 (DP only)**. A KTC comparison needs KTC's permission. A substitute (F2) needs its own terms check. See §4.1 and the run tiers in [eval-plan.md §5](eval-plan.md#5-run-tiers-and-blockers-trades-pm).
- **Ask 2 (league-specific valuation).** The operator's five franchises support a **direction** on format handling and a test of **whether league-level market effects exist**. They can't support team-count or scoring-rule adjustments: all 22 league-seasons are 12-team. See §5 and §7.
- **Ask 3 (how KTC gets Sleeper trade data).** Sleeper has no bulk trade feed. Anyone with a large corpus crawls league by league. KTC doesn't publish its method. Sleeper's current terms prohibit crawling without written consent. See §3 and §4.2.

---

## 2. What KTC launched

All KTC claims below are paraphrased. Check the exact wording at the cited URL.

### 2.1 Value sources

| Claim | Label | Source |
|---|---|---|
| KTC values now come from three selectable sources: **Crowdsourced** (the daily Keep/Trade/Cut vote), **Tradesourced** (derived from real trades) and **Crowd+Trades** (a blend) | confirmed | [KTC FAQ](https://keeptradecut.com/frequently-asked-questions) (entries on where values come from, and on Crowd+Trades) |
| Crowd values come from an adapted Elo over K/T/C answers and update continuously through the year | confirmed | KTC FAQ; [About player values](https://keeptradecut.com/about/player-values) |
| Tradesourced values aggregate real trades from several dynasty platforms through a proprietary algorithm. No method, weighting, recency window or multi-asset decomposition is published | confirmed (that it is undisclosed) | KTC FAQ (entry on how Tradesourcing works); About player values |
| KTC's own stated trade-offs: Tradesourced reflects actual market behavior, but lags on news and rookies, depends on trade volume, struggles to separate future picks into Early/Mid/Late, and thins out around lock dates. Crowdsourced moves first on news and tends to value picks higher | confirmed | [KTC trade calculator](https://keeptradecut.com/trade-calculator) (value-sources section); About player values |
| Tradesourced prices individual current-year pick slots. Future picks get one value per year and round, split Early/Mid/Late using crowd ratios | confirmed | KTC FAQ (entry on differences between value sources) |
| The Crowd+Trades blend weights are not published | confirmed (unpublished) | KTC FAQ; About player values |
| There is no separate new "trade evaluator" product. Trade evaluation is the existing calculator with a value-source selector | confirmed (calculator) / unknown (that nothing else launched: none found) | trade calculator page; searches of KTC pages, X snippets, Reddit and the web |
| The site default is still Crowdsourced | likely | trade calculator page |

### 2.2 Timing

| Claim | Label | Source |
|---|---|---|
| Tradesourced and Crowd+Trades histories start **2026-05-01**. Earlier dates are backfilled with crowd history | confirmed | KTC FAQ (entry on start dates) |
| Public launch around **2026-09-08**. A KTC post dated "Sep 8" (year not shown) announces the choice of trade-powered values; the earliest Wayback capture of the calculator is 2026-09-13; FTF's first repo mention is 2026-09-20 (ADR-022) | likely | [KTC on X](https://x.com/KeepTradeCut) (search snippets; the fetch returned 402); [StatChasers](https://statchasers.com/keeptradecut-alternative/); Wayback availability API |

### 2.3 Format handling

| Claim | Label | Source |
|---|---|---|
| Crowd values are two separate databases, Superflex and 1QB, so a non-QB can differ by format | confirmed | KTC FAQ (entry on Superflex and 1QB) |
| Tradesourced is split SF/1QB the same way | likely | the SF toggle and source selector coexist on the calculator; the Trade Database tags trades by QB count |
| Base values assume **12 teams, 0.5 PPR, no TE premium**. Scoring and starters don't adjust values | confirmed | KTC FAQ (entries on league format and on scoring settings) |
| TE premium has four tiers (off, TE+, TE++, TE+++) | confirmed | KTC FAQ; FTF's own parser reads the `tep` variant (`backend/data_loader.py:204-207`) |
| Whether Tradesourced TEP is learned from TEP-league trades or applied as an adjustment | unknown | none |
| The calculator has League Size, Future Pick Adjustment, Startup Mode and Acceptable Variance controls. Their effects aren't visible in the static page | confirmed (labels) / unknown (effects) | trade calculator page |

### 2.4 Consolidation adjustment

| Claim | Label | Source |
|---|---|---|
| The calculator adds a **Value Adjustment** to the side giving up the best piece, for roster spots and stud status. It is sized as the player the lesser side would need to add to even the trade, and it moves as assets change. Inputs: the value gap, how much of a stud each player is, and the count of lesser pieces | confirmed | KTC FAQ (entries on the Value Adjustment) |
| A 2022 third-party reverse-engineering from KTC's client script: each asset gets a raw adjustment that grows with its value relative to the trade's best asset and to the top of the scale (roughly a tenth of an asset's value at the bottom, rising to about two-fifths at the top). The side with the larger summed raw adjustment wins. The constants are unpublished | likely (inferred, possibly outdated) | [Javelin, 2022-09-30](https://www.javelinfantasyfootball.com/2022/09/30/how-the-ktc-adjustment/) |
| The adjustment is unchanged on Tradesourced values | unknown | none |

### 2.5 Fairness band

| Claim | Label | Source |
|---|---|---|
| A trade reads as fair when the adjusted totals differ by at most about **5% of combined value** (the default Acceptable Variance), with the adjustment favoring the more consolidated side. Measured by a third party in August 2026 on crowd values at TE+, on 4,461 community-judged trades | likely | [Stats Guy methodology](https://statsguyfantasy.com/methodology/comparing-trade-calculators) |
| The calculator shows per-side totals, the adjustment and the total value exchanged. KTC itself calls calculators a gut check at best | confirmed | trade calculator page; KTC FAQ (entry on calculator accuracy) |

The value core's own band is asymmetric: the viewer gives at most 20% more and takes at most 10% more (ADR-024). KTC's band is much tighter, so many FTF cards would read as unfair under it.

### 2.6 History and access

| Claim | Label | Source |
|---|---|---|
| Player pages chart value history on-site only. There is **no API, CSV or export**. KTC says an API has been discussed | confirmed | KTC FAQ (entry on API and data export) |
| The Wayback Machine holds no captures of the rankings page or the Trade Database. It has a calculator capture (2026-09-13) and an FAQ capture (2026-09-27). These pages render values client-side, so captures are unlikely to hold numbers | confirmed | Wayback availability API, queried 2026-10-15 |
| The only KTC "API" found is an unofficial scraper wrapper. **Not usable by FTF** | confirmed | parse.bot marketplace listing (URL in [Sources](#sources)) |
| A competitor app (Dynasty-Ticker) merged a change on 2026-09-26 removing every user-visible KTC mention, with no reason given. A weak signal only, not evidence of enforcement | confirmed (the change) / unknown (the reason) | [Dynasty-Ticker PR #105](https://github.com/nikoskiouris/Dynasty-Ticker/pull/105) |

---

## 3. How KTC and competitors get Sleeper trade data

### 3.1 What Sleeper's public API exposes

| Fact | Label | Source |
|---|---|---|
| Trades are readable only **per league, per leg**: `GET /v1/league/<id>/transactions/<round>`. Leagues are discoverable only **per user**: `GET /v1/user/<user_id>/leagues/nfl/<season>` | confirmed | [Sleeper API docs](https://docs.sleeper.com/) |
| **There is no bulk, global or "all trades" endpoint.** The only bulk endpoints are players and trending adds/drops | confirmed | Sleeper API docs |
| No token is needed. The documented ceiling is about 1,000 calls a minute before an IP block | confirmed | Sleeper API docs |
| Only completed trades are published. Pending offers live on the private GraphQL surface. FTF's own sweeps of more than 1,600 public trades found none in another state | confirmed | `docs/plans/sleeper-pending-trades-feasibility-2026-08-12.md:13-31` |
| The v1 API is identity-blind: full history is readable for leagues the caller isn't in | confirmed | same memo `:31` |
| Each league object carries `previous_league_id`, so earlier seasons are reachable. FTF walks it to depth 3 | confirmed | Sleeper API docs; `scripts/backfill_sleeper_trades.py` |
| League objects expose `settings.type` (2 = dynasty), `total_rosters`, `roster_positions` and `scoring_settings` publicly | confirmed | Sleeper API docs; `backend/tests/fixtures/outlook-calibration/lakeview-2025.json` |

**What this means:** a corpus beyond one's own leagues has to be crawled. The usual pattern is a snowball: seed users, then their leagues, then those leagues' members, then their leagues. At about 20 calls per league-season (FTF's own P2 count: `docs/plans/trade-relevance-engine/prds/prd-p2-market-and-history.md:107-113`), reach is limited by rate, terms and storage, not by the graph (estimate).

### 3.2 KTC

| Claim | Label | Source |
|---|---|---|
| KTC's Trade Database says its trades come from about 232,000 real dynasty leagues, and the figure is growing | confirmed | [KTC Trade Database](https://keeptradecut.com/dynasty/trade-database) |
| The Trade Database filters by QB count, PPR, team count (8–16), TE premium, starters and asset count. It has **no platform filter and no verdicts** | confirmed | KTC Trade Database |
| KTC doesn't name the platforms behind the Trade Database or Tradesourced values | confirmed (not named) | KTC FAQ; About player values |
| KTC already reads platform APIs for leagues users enter in Power Rankings, by public league ID (MFL, Sleeper, FFPC, Fleaflicker, Fantrax), re-syncing about every 10 minutes | confirmed | KTC FAQ (entries on Power Rankings and supported platforms) |
| Sleeper and MFL are among KTC's trade sources | likely | a third-party scraper listing; Sleeper and MFL are KTC's main integrations |
| Leagues users enter in Power Rankings seed the Trade Database | likely (indirect only) | the "leagues" phrasing plus the existing API pull |
| KTC crawls beyond the leagues users enter | unknown | none |
| KTC holds a Sleeper partnership or data license | unknown | none found; KTC's [privacy policy](https://keeptradecut.com/privacy-policy) says nothing about league data |

### 3.3 Competitors

| Who | Public claim | How they collect | Label | Source |
|---|---|---|---|---|
| FantasyCalc | Values fit from real trades, per format (SF, TEP, PPR, team count), recency-weighted, outliers removed, updated several times a day. A search snippet showed several million trades | not documented | claim: likely (snippet); method: unknown | `docs/reviews/trade-engine-external-research.md:13-15`; [fantasycalc.com](https://fantasycalc.com/) (JS-rendered; no content returned) |
| Dynasty Dealer | A free values API computed from real Sleeper trades (hundreds of thousands) | not documented | claim confirmed; method unknown | [dynasty-dealer-api-examples](https://github.com/elliotpollaro/dynasty-dealer-api-examples) |
| Roster Audit | Ingests thousands of real dynasty trades daily from Sleeper leagues | Sleeper sync without a password; discovery beyond sync not stated | claim confirmed; method unknown | [rosteraudit.com](https://rosteraudit.com/trade-calculator/) |
| The Trade Calc | Values solved from trades in public leagues (millions recorded), adjusted for each trade's own league settings | "public leagues" suggests crawling public league IDs | likely | [thetradecalc.com](https://thetradecalc.com/) |
| Dynasty Daddy | Repo research cites a large trade corpus | its 2021 public code scraped KTC and read Sleeper client-side with no trade crawler; current method unknown | 2021 code: confirmed; now: unknown | `docs/research/matchmaking/round-3/03-valuation-integrity-and-governance.md:470-472`; [G-Sher/dynasty-daddy](https://github.com/G-Sher/dynasty-daddy) |
| DynastyProcess | Values are FantasyPros ECR through a curve, **not trade-derived**. Its open-source `ffscrapr` reads Sleeper per league; it isn't a crawler | confirmed | `docs/integrations/dynastyprocess.md`; [ffscrapr](https://github.com/ffverse/ffscrapr) @ `b6990181` |

### 3.4 Takeaway

- At least five products hold Sleeper trade corpora of hundreds of thousands to millions of trades. **None publishes how it discovers leagues or whether it holds a Sleeper license** (likely).
- Since Sleeper offers no feed, they must crawl league by league from user-synced seeds, snowballs, or both (likely).
- That others do it is not permission. The repo already records the same point about Dynasty Daddy (`docs/plans/sleeper-pending-trades-feasibility-2026-08-12.md:94`).
- **The operator's assumption that the data "is available" is half right.** It is technically reachable, one league at a time. It is not available under Sleeper's published terms without written consent (§4.2).

---

## 4. Data rights

This section states what the published terms say and how FTF's uses line up against them. It draws no legal conclusion beyond "the published terms prohibit X without written permission".

### 4.1 KTC: Terms and FAQ

**Sources:** [KTC Terms and Conditions](https://keeptradecut.com/terms-and-conditions) (last updated 2025-11-11) and the [KTC FAQ](https://keeptradecut.com/frequently-asked-questions), both read 2026-10-15. Section numbers as rendered.

- **§2.1** prohibits "Any form of automated data collection, including but not limited to:", then lists scraping, data mining, extraction, harvesting, bots and crawlers. It also covers *systematic* collection, not only automated.
- **§2.2** prohibits commercial exploitation of site content, using KTC data on any other website or networked environment, derivative works, and redistribution.
- **§3** says content, including data compilations, belongs to KTC or its suppliers.
- **§5** limits the license to personal, non-commercial use.
- **§4** lets KTC block violators' IP addresses and end their access.
- **FAQ:** no API or CSV; scraping is forbidden; using KTC values in their entirety in other tools is forbidden; citing individual values in articles and discussion, with credit, is welcome.

| Use | What the published terms say | Facts the operator should weigh |
|---|---|---|
| **(a) FTF's existing production scrape** (K1 into C0 at weight 0.5) | The published terms prohibit automated collection, and commercial or derivative use of KTC data, without KTC's written permission (§2.1, §2.2, §5; FAQ) | <ul><li>`backend/data_loader.py:149-216` GETs `keeptradecut.com/dynasty-rankings` once per 24 h (`:186-188`) and blends KTC's ordering of the full list into every seed. The code calls it "an unsanctioned surface" (`:155`), as does `docs/runbook.md:965`.</li><li>It sends desktop-Chrome browser headers to clear Cloudflare (`data_loader.py:190-199`).</li><li>**KTC-derived data is committed to this public repo:** `backend/tests/fixtures/ktc_rankings_snapshot_2026-07-17.html` and `ktc_blend_pipeline_2026-07-17.json` (added in `71e1a617`, 2026-07-18), used by `backend/tests/test_ktc_blend.py:48-49` and `test_mock_draft.py:1586`. Review docs quote numbers from manual KTC pulls: `docs/reviews/2026-08-19-ktc-pick-value-comparison.md:85`, `2026-08-19-pick-year-valuation.md:169`, `2026-08-21-market-curve-comparison.md:365-366`.</li><li>The kill switch is `ktc_blend_weight = 0`, which is byte-identical to DP-only and skips the fetch (`docs/runbook.md:967`). It takes effect on the next pool build. The scrape already fails soft to DP-only (`:966`).</li><li>Plans that name KTC Tradesourced as a comparator don't address the terms: `docs/plans/model-evaluation-framework/plan.md:129,139`, ADR-022 (`docs/adr/adr-022-preference-led-bilateral.md:26-28`).</li><li>The only user-facing KTC mention is a comparison sentence in `web/faq.html:185`. It carries no KTC data.</li></ul> |
| **(b) A frozen, dated snapshot of K2** for internal evaluation | The published terms prohibit automated and systematic collection, and use outside the personal license, without written permission. The FAQ's "entirety" prohibition covers a full or near-full copy. No public snapshot source exists | A small, hand-read sample kept out of the repo is closest to the citing the FAQ welcomes, but it would serve a commercial product's evaluation. That is the operator's call (D-W1c). models-lead recommends against using it as decision evidence anyway: 30–60 players per format supports only position-level reads |
| **(c) Calculator verdicts** on FTF's trades | Same as (b). Automated querying is prohibited outright; hand-entering hundreds of trades is systematic collection | About 350 cards × 2 value sources at 1–2 minutes each is **12–24 operator-hours** (estimate) |

**Paths the terms leave open:**

1. **Ask KTC.** An evaluation license or data share: a dated Tradesourced snapshot plus calculator use for about 500 trades. Contact page: [keeptradecut.com/contact-us](https://keeptradecut.com/contact-us). Outbound, so operator-only (TP-3).
2. **A substitute trade-driven source (F2)** whose terms allow evaluation use. FantasyCalc is the obvious candidate, but its terms are **unverified** (D-W6).
3. **DP only (C1).** DynastyProcess data is CC-BY with an attribution obligation (`backend/dp_values_history.py:20`). It is already FTF's spine.

### 4.2 Sleeper: Terms (2026-10-06) and the API docs

**Sources:** [Sleeper Terms of Use](https://support.sleeper.com/en/articles/5486620-terms-of-use), page dated last updated 2026-10-06, read 2026-10-15. This is **newer than the 2026-07-24 revision the repo knows about** (`docs/plans/sleeper-pending-trades-feasibility-2026-08-12.md:83-92`). [Sleeper API docs](https://docs.sleeper.com/), read 2026-10-15.

- **§11.1** prohibits, without Sleeper's express written consent:
  - accessing, querying or extracting data from the Services by automated means (bots, scripts, spiders, and manual access at non-human scale);
  - "Crawl or scrape the Services in any way, shape, or form, for any purpose whatsoever,";
  - using the Services for any commercial purpose or for a third party's benefit.
- **§11.3** says no third party may access, scrape, crawl or retrieve data from the Services, directly, by automated means, or through a user's credentials, except under a separate signed agreement. A user handing over credentials is not Sleeper's authorization.
- **§11.2** lets Sleeper investigate, revoke sessions and block the third party.
- **§2.9 / §9.2:** connecting through an Approved Integration Partner under a written agreement is a permitted use.
- **API docs:** the API is "free to use for non-commercial purposes", and commercial users are told to contact Sleeper about licensing.
- **Caveats** (unknown, not resolved here): the Terms define "Services" as Sleeper's apps, site and related services without naming `api.sleeper.app`, and they bind account holders and users. Whether they reach an anonymous API caller is a legal question. What changed in §11 between 2026-07-24 and 2026-10-06 is unknown; the Wayback Machine was unreachable from the research environment.

**What the repo already records:**

- Sleeper warned the operator that its automated systems may block FTF's calls, and suggested varying where calls come from (`docs/plans/device-side-platform-auth-prd-2026-08-12.md:13,23`).
- On 2026-08-12 the operator stated FTF has an explicit agreement with Sleeper (`docs/plans/sleeper-pending-trades-feasibility-2026-08-12.md:102-104`). **The agreement artifact is not filed** (same memo, `:106-109`).
- FTF's trade capture sends a spoofed Chrome User-Agent (`backend/sleeper_trades_service.py:51-58`). The device-auth PRD calls a switch to an honest UA a gated, probed change, not a one-liner (`device-side-platform-auth-prd-2026-08-12.md:117`).

### 4.3 OQ-1

**The question:** does FTF's Sleeper agreement cover **automated, unauthenticated reads** (session-init sweeps, trade capture, the players dump), and, for this plan, **model building and commercial use of trade data**, including leagues no FTF user belongs to?

**Its status is contested in the repo:**

| Date | Where | Status |
|---|---|---|
| 2026-08-12 | `device-side-platform-auth-prd-2026-08-12.md:166` | Raised as **blocking**. The orchestrator couldn't read §11.3 in full |
| 2026-08-12 | same PRD, operator amendment (`:176-182`) | **Withdrawn** as a question for that document ("OQ-1 is CLOSED"). This was a withdrawal, not an answer from Sleeper. The reasoning on record then read §11.3 as limited to credentialed access (`:241`) |
| 2026-08-14 | `docs/plans/trade-relevance-engine/hld.md:574-590`; `prds/prd-p2-market-and-history.md:204-219` | Carried as **unresolved**. It gates any fleet-wide trade-history backfill. P2 isn't built |
| 2026-10-15 | `living-memory/OPEN_QUESTIONS.md` | **Not logged.** The highest ID at `origin/main` is Q-039 |

**What's new:** the 2026-10-06 Terms reach direct and automated retrieval in §11.3, and §11.1 bars crawling for any purpose. That removes the basis of the 2026-08-12 credential-only reading. **trades-pm recommends re-opening OQ-1**, extended to model building and to non-member leagues, and logging it through the scribe (TP-2). Asking Sleeper is outbound and operator-only (TP-3).

### 4.4 Corpus options and risk

| Path | What it adds | Terms posture | Risk |
|---|---|---|---|
| **Users' own leagues** (consent scope): leagues FTF users link, plus their `previous_league_id` history | About 20 calls × up to 4 seasons once per newly linked league, then 1–2 calls per session init. This is what FTF already runs. Today: 555 trades | **The same posture FTF already operates.** §11.3 says user consent isn't Sleeper's authorization, so this rests on the agreement covering automated reads (OQ-1) | **Low incremental.** The underlying exposure is FTF's existing one |
| **Leaguemates' other leagues** (hop 1) | About 200–600 leagues, 4,400–19,000 trades a season (estimate, assuming 2–6 leagues per manager, unverified) | Crawling under §11.1 and §11.3, for a commercial product. Nobody in those leagues consented to anything, so "consent scope" doesn't describe it | **High** |
| **Public crawl** (hop 2 and beyond) | 5,000–30,000 leagues after hop 2; 100,000+ eventually | The published terms prohibit it without a written agreement. The API docs require a commercial license. Sleeper has already warned FTF about volume | **Highest.** An IP block would hit **every live Sleeper feature** on the same egress (session init, trade capture, send-in-Sleeper), not only the corpus job |

**trades-pm recommendation:** no corpus beyond consent scope unless the operator gets written confirmation from Sleeper (OQ-1 extended) or a data license. Until then, league-specific work uses the operator's five franchises and organic growth in linked leagues.

---

## 5. FTF's current corpus and eval harness

### 5.1 Executed trades

- **The corpus:** **555 executed Sleeper trades**, 22 league-seasons, **5 franchises** (Lakeview, FFv3, La Resistance, Bush League, SFO), **all 12-team**, 2022–2026 (`docs/business/analytics/2026-08-16-organic-trade-corpus.md:17-25`).
  - Trades per complete league-season: median 22, mean 31.1, range 10–86 (`:36-38`).
  - 47% of trades fall in May–August (`:82-88`).
  - **The operator is in all five, and managers overlap** (`:151`). It is not an independent sample.
  - Positive-only: executed trades carry no Yes/No label.
- **Capture:** `market.trade_capture` is ON (`config/features.json:62`; `backend/feature_flags.py:480-485`). It stores completed trades from `GET /v1/league/<id>/transactions/<week>` into `sleeper_trades` during session init (`backend/sleeper_trades_service.py:1-21`). It captures only: no scoring, no aggregation, no UI.
- **Backfill:** `scripts/backfill_sleeper_trades.py` sweeps every synced league plus up to 3 prior seasons, idempotent on `transaction_id`.
- **Format mix visible in committed fixtures:**
  - FFv3: 1QB, half-PPR, IDP, 15 starters, 39-man rosters;
  - Lakeview: SF, full PPR, 0.5 TE premium, 10 starters, 31-man rosters;
  - La Resistance, Bush League, SFO: **unknown** (no committed fixtures).
  - So there is no team-count variety and no 6-point passing-TD variety.

### 5.2 Tables

- `sleeper_trades` (`backend/database.py:663-678`): normalized JSON columns plus the full `raw` payload, NOT NULL. The normalized columns duplicate `raw`.
- `leagues` (`:521-531`): `default_scoring` is only `1qb_ppr` or `sf_tep`; `total_rosters` is stored; `scoring_settings` and `roster_positions` are not stored raw.
- `player_value_history` (`:1817-1828`): daily consensus value per player per format. **Rows carry the KTC blend only from 2026-07-17** (#145; `docs/data-dictionary.md:1263`); before that they are DP-only. The table exists in code since about 2026-07-03 (`e0001e60`); its first prod row date is unverified.
- `grading_cards` (`backend/database.py:2870-2884`; `docs/data-dictionary.md:1957-1961`): `trade_json` (the served trade, each asset with its C0 value), `arms_json` (hidden arm provenance; shared cards carry several arms), `grade`, `skipped`, `tags_json`. Format is in `grading_sessions.source_json` (`:1942`).

### 5.3 Eval harness

- `backend/eval/value_core_recall.py` computes real-trade recall offline from **committed fixtures only** (no network, no DB): `outlook-hypotheses/`, `outlook-calibration/` and `dp-values-history/`. Committed trades cover FFv3 2022–2025 and Lakeview 2024–2025 (214 trades). The other three franchises' trades are in prod `sleeper_trades` only.
- `backend/eval/fit_scorecard_test.py` scores Calibration cards against grades by AUC and reads prod read-only. Its labels are `WOULD_SEND, WOULD_NOT = 4, 2` (`:37`), so legacy grade-3 answers drop out of its AUC.
- `backend/dp_values_history.py` gives dated DP boards from DP's git history (G-025). **24 boards are committed, all September–December 2022–2025** (`backend/tests/fixtures/dp-values-history/`). **There are no offseason boards**, yet 47% of trades are May–August. Offseason boards are free to add from DP's history.
- **No dated KTC history exists.** The scrape keeps only an in-memory 24 h copy (`backend/data_loader.py:188`). FTF's one dated K1 copy is the 2026-07-17 public-repo fixture (§4.1a).

### 5.4 How FTF prices formats today

- **One consensus seed per format bucket:** DP blended with KTC crowd ordering; the 1QB QB cap (`qb_1qb_cap_elo`); a ×1.18 TE uplift in `sf_tep` (`tep_te_uplift`; `backend/database.py:2904-2906`).
- **Format detection is binary:** Superflex **or** TE premium → `sf_tep`, else `1qb_ppr` (`backend/server.py:750-786`). **A 1QB league with TE premium is priced with superflex QB values, and a superflex league without TE premium still gets the TE uplift.** This is a concrete, testable mis-bucket (H-L1).
- **Per-roster context on top:** marginal value over each roster's replacement level, outlook and window, lineup-aware deck rules, and the fit arms' multipliers.
- **Not modelled:** PPR level, 6-point passing TD, first-down scoring, team count in base values, TE-premium magnitude, any league's own market prices (P2's `price_level` was designed and never built), and IDP on the dynasty board.

---

## 6. Storage cost of a broader corpus

For task 2 (DB storage). The prod Postgres disk is **5 GB**, expanded from 1 GB after a suspension at 98.3% full on 2026-09-15. The expansion is permanent; storage costs $0.30 per GB-month (`docs/runbook.md:1241-1246`; `docs/plans/db-storage-reduction/release.md:3`). **The dollar cost is small. The constraint is the 5 GB ceiling and that incident.**

### 6.1 Bytes per trade (measured on the 214 committed fixture trades)

| Piece | Mean | Median | p90 | Max |
|---|---|---|---|---|
| `raw` JSON | 605 B | 580 B | 817 B | 1,127 B |
| Normalized JSON columns (duplicates of `raw`) | 280 B | 249 B | 498 B | 767 B |
| Logical row text, with ids and ISO timestamps | 991 B | 934 B | 1,418 B | 2,000 B |

**On disk, today's schema:** 991 B + about 48 B heap overhead + about 100 B for three btree entries (PK, unique `transaction_id`, `league_id`) ≈ **1,139 B per trade** (estimate). Rows stay under the roughly 2 KB TOAST threshold, so nothing is compressed. **Today's 555 trades take about 0.6 MB.**

### 6.2 Projection

Trades = leagues × trades per league-season × seasons, at **22 (median) to 31.1 (mean)** trades per league-season. Bytes = trades × bytes per trade. Decimal units (1 GB = 10⁹ B).

| Leagues | Seasons | Trades | Today's schema (1,139 B) | Compact DB row (~214 B) | Off-DB gzip files (35–65 B) |
|---|---|---|---|---|---|
| 1,000 | 1 | 22,000–31,100 | 25–35 MB | 5–7 MB | 1–2 MB |
| 1,000 | 3 | 66,000–93,300 | 75–106 MB | 14–20 MB | 2–6 MB |
| 10,000 | 1 | 220,000–311,000 | 0.25–0.35 GB | 47–67 MB | 8–20 MB |
| 10,000 | 3 | 660,000–933,000 | **0.75–1.06 GB (15–21% of disk)** | 0.14–0.20 GB | 23–61 MB |
| 100,000 | 1 | 2.2M–3.1M | 2.5–3.5 GB | 0.47–0.67 GB | 77–202 MB |
| 100,000 | 3 | 6.6M–9.3M | **7.5–10.6 GB (doesn't fit)** | 1.4–2.0 GB | 0.23–0.61 GB |

**Worked example:** 10,000 leagues × 31.1 trades × 3 seasons = 933,000 trades; × 1,139 B = 1.06 GB, which is 21% of 5 GB.

**Column notes:**

- *Compact DB row:* bigint ids, epoch timestamps, compact asset lists, and no `raw`.
- *Off-DB gzip:* measured on the same 214 trades. Raw JSONL gzips to 65 B per trade. A compact JSONL (txid, epoch, roster ids, adds, picks, FAAB) is 108 B, or 36 B gzipped. A small, repetitive sample flatters gzip, so **plan on 50–150 B per trade at scale**.
- **League settings add** about 1.2 KB per league-season (format, scoring, roster, team count), or 3.1 KB for the raw league object. At 100,000 leagues that is +0.12–0.31 GB per season.
- **Waivers and free agents** would multiply everything by 10–50 (`prd-p2-market-and-history.md:50`). Don't keep them.

### 6.3 Cheaper shapes, best first

1. **Off-DB, offline files in the eval-fixture shape** that `value_core_recall` already reads: gzip JSONL or Parquet on the operator's machine or in a private bucket, versioned by capture date. **Zero bytes of prod DB.** Modelling and eval are offline anyway; only fitted parameters ship.
2. **Ship aggregates, not rows.** For example, price statistics per (format cell × asset × month): about 8 cells × 600 assets × 12 months ≈ 58,000 rows × 60 B ≈ **3.5 MB a year**. Per-league offsets (H-L4) are one row per linked league, about 1–2 KB each.
3. **Stratified sampling:** a fixed quota per format cell (for example 100–200 leagues × 12 cells) means a few thousand leagues, not 100,000.
4. **If rows must live in prod:** drop the duplicated normalized columns or `raw` (−25% to −60%), use integer ids and epochs, and prune at 3 seasons (already a P2 launch requirement).

**For task 2:** the consent-scope corpus is negligible at any realistic growth. A broader corpus is blocked by terms before it is blocked by disk (§4.4). If one is ever obtained lawfully, shape 1 keeps it out of prod entirely.

---

## 7. Feasibility and sample sizes

### 7.1 Board and engine comparisons (Calibration cards)

**Data:** about **378 answers** across rounds 1 and 2 (`living-memory/CHANGELOG.md:16`), roughly 160 Yes and 190 No as unique cards. Round 3 opened 2026-10-15.

**Paired AUC (Q-B, Q-K):** Hanley–McNeil at AUC ≈ 0.65 with about 160 Yes and 190 No:

| | Value |
|---|---|
| SE per evaluator | ≈ 0.030 |
| SE of the paired difference, score correlation r = 0.7 | ≈ 0.023 |
| SE of the paired difference, r = 0.5 | ≈ 0.030 |
| **Detectable ΔAUC, 80% power** | **≈ 0.065 at r = 0.7; ≈ 0.085 at r = 0.5** |

These figures come **before** grader clustering. Three graders grade very differently (D-208): the operator gives 1 or 5 on 95% of cards; jonbonjourvi gives 1–2 on 73%. A 0.07 bar sits at the edge of detectability.

**Would-send difference between arms (Q-C, unpaired, p ≈ 0.5, 80% power):** ±20 pp at 100 cards per arm, ±15 pp at 175, ±10 pp at 400.

**Board agreement (Q-A, Spearman ρ ≈ 0.85, Fisher z with SE ≈ 1.06/√(n−3)):** about ±0.12 to ±0.16 at 30 players per cell, ±0.08 at 60, ±0.06 at 100. A 60-per-format hand sample supports position-level reads only.

### 7.2 Executed trades

- A proportion on about 555 trades carries roughly **±4 pp** (95%).
- **The C0-vs-C1 executed-trade window is small.** Stored C0 carries KTC only from 2026-07-17 (§5.2). The 2026 seasons held 26 trades as of 2026-08-16 (corpus memo `:23`), plus whatever has been captured since. Expect fewer than 100.

### 7.3 League-specific adjustments

Planning estimate, to be replaced by measurement on the existing 555 trades:

- **Metric:** balance error on executed trades, e = |ln(V₁ / V₂)| under a value set. A value set that fits a market better makes executed trades look more balanced.
- **Independent trades needed** to detect a 0.05 drop in mean e, with paired-difference SD ≈ 0.25: ((1.96 + 0.84) × 0.25 / 0.05)² ≈ **196**.
- **With clustering** (about 30 trades per league-season, intra-league correlation ρ ≈ 0.05): design effect 1 + 29 × 0.05 ≈ 2.45, so about **480 trades from at least 16 league-seasons and 8–10 distinct franchises per cell compared**.
- **Today that supports:**
  - format direction (H-L1 / LS-1): yes, as a direction;
  - whether league effects exist (H-L4 step 1): yes;
  - team count, scoring rules and depth (H-L2, H-L3): **no**. Every team-count cell other than 12 has **zero** franchises.

### 7.4 Corpus reach by path

| Path | Leagues | Trades per season | Calendar time at FTF's planned 2,000 calls/day budget | Terms |
|---|---|---|---|---|
| Consent scope today | ~12 linked in prod (`living-memory/CHANGELOG.md:1314`, 2026-08-20) | ~260–370 | done (555 captured) | existing posture (OQ-1) |
| Consent scope, growth | +1 per newly linked league | +22–31 | ~16 league backfills a day | existing posture (OQ-1) |
| Hop 1 | ~200–600 | ~4,400–19,000 | ~2–4 weeks | prohibited without written consent |
| Hop 2+ | 5,000–100,000+ | 0.1M–0.9M+ | months to years | prohibited without written consent; commercial license per the API docs |

---

## 8. Decisions needed

trades-pm's decisions are below. The full merged list, with models-lead's D-W1 to D-W7, is in [eval-plan.md §6](eval-plan.md#6-decisions-needed).

| # | Decision | Who | trades-pm recommendation |
|---|---|---|---|
| **TP-1** (= D-W1a) | **The production KTC scrape: keep, kill or license.** Also the KTC-derived fixtures and review-doc numbers in this public repo | Operator. **Escalated to `head-product` on 2026-10-15** | Decide before any KTC contact (TP-3). The published terms prohibit the scrape without written permission whichever way Q-K lands. Q-K (eval-plan §1.5A) tells the operator what dropping the blend costs the model; it doesn't change the terms. The fixtures are a separate clean-up for `head-eng` whatever the call |
| **TP-2** | **Log OQ-1** in `living-memory/OPEN_QUESTIONS.md`, re-opened and extended to model building and non-member leagues, with the 2026-10-06 Terms revision noted | `head-product` → the scribe (trades-pm doesn't edit living-memory). Next free ID at `origin/main` is Q-040; the scribe re-greps first | Yes |
| **TP-3** | **Outbound contact:** does the operator contact Sleeper, KTC, or both? | Operator only | **Sleeper: yes, now.** OQ-1 affects FTF's live posture on every session init, not only this plan. **KTC: after TP-1.** If the operator wants ask 1 answered against KTC itself, request an evaluation license (dated Tradesourced snapshot plus calculator use for about 500 trades). models-lead would ask only if Q-K lands on K-2 (D-W1b); the operator picks the timing |

---

## 9. Handoffs

Through org boxes only.

| To | What |
|---|---|
| `head-product` → operator | TP-1, TP-3 and the eval-plan decisions (D-W1 to D-W7) |
| `head-bizops` → `head-eng` → `models-eng` | Evals E-1a, E-1b, E-2 and E-3 (eval-plan §1.6), plus a **format census** of the five corpus franchises (format, scoring, team count; consent scope, existing read authority) |
| `head-product` → `platforms-pm` | The 2026-10-06 Sleeper Terms revision and OQ-1 (§4.2, §4.3), for the platform risk register |
| `head-product` → `analytics-lead` | Share of active leagues by format, scoring class and team count; the operator's round-2 would-send rate per arm |
| `head-eng` | The KTC-derived fixtures and review-doc numbers in the public repo (§4.1a). Removing the fixtures touches `test_ktc_blend.py` and `test_mock_draft.py` |
| `head-product` → `monetization-pm` | Sleeper's API commercial-use clause (§4.2), which bears on any paid surface built on Sleeper reads |
| Task 2 (DB storage) | The storage table (§6) |

---

## Citation notes

Repo citations were re-checked against `origin/main` @ `678834ab` on 2026-10-15. Corrections against the research passes:

- **OQ-1 status.** The research called OQ-1 "open since 2026-08-12" (`device-side-platform-auth-prd-2026-08-12.md:166`). The same PRD's operator amendment (`:176-182`) withdrew it that day, and the trade-relevance HLD and P2 PRD still carry it as unresolved two days later. §4.3 records all three.
- **Calibration columns** are at `docs/data-dictionary.md:1957-1961` (the research cited `:1956-1959`).
- **KTC runbook lines:** the "unsanctioned" sourcing note is `docs/runbook.md:965`; the section spans `:961-970`.
- **Review doc lines:** `2026-08-21-market-curve-comparison.md:365-366` (the research cited `:365-370`).
- **Stored C0 and KTC.** `player_value_history` rows carry the KTC blend only from 2026-07-17 (`docs/data-dictionary.md:1263`). The research framed the executed-trade window as "after `player_value_history` began"; the binding date is 2026-07-17.
- **Round-2 results** are at `living-memory/CHANGELOG.md:31` on `origin/main` (models-lead's draft cites `:17`, which is the same line at HEAD `6bc4602b`).

## Sources

Web, all read 2026-10-15:

- KTC: [Terms and Conditions](https://keeptradecut.com/terms-and-conditions) · [FAQ](https://keeptradecut.com/frequently-asked-questions) · [About player values](https://keeptradecut.com/about/player-values) · [Trade calculator](https://keeptradecut.com/trade-calculator) · [Trade Database](https://keeptradecut.com/dynasty/trade-database) · [Power Rankings](https://keeptradecut.com/dynasty/power-rankings) · [Privacy policy](https://keeptradecut.com/privacy-policy) · [Contact](https://keeptradecut.com/contact-us) · [X](https://x.com/KeepTradeCut)
- Third parties on KTC: [Stats Guy](https://statsguyfantasy.com/methodology/comparing-trade-calculators) · [Javelin](https://www.javelinfantasyfootball.com/2022/09/30/how-the-ktc-adjustment/) · [StatChasers](https://statchasers.com/keeptradecut-alternative/) · [parse.bot listing](https://parse.bot/marketplace/b7c3ba52-2896-48b7-8cb3-883d36787c09/keeptradecut-com-api) (unofficial; not usable) · [Dynasty-Ticker PR #105](https://github.com/nikoskiouris/Dynasty-Ticker/pull/105)
- Sleeper: [Terms of Use](https://support.sleeper.com/en/articles/5486620-terms-of-use) (last updated 2026-10-06) · [API docs](https://docs.sleeper.com/)
- Competitors: [FantasyCalc](https://fantasycalc.com/) · [Roster Audit](https://rosteraudit.com/trade-calculator/) · [The Trade Calc](https://thetradecalc.com/) · [Dynasty Dealer API examples](https://github.com/elliotpollaro/dynasty-dealer-api-examples) · [Dynasty Daddy (2021)](https://github.com/G-Sher/dynasty-daddy) · [ffscrapr](https://github.com/ffverse/ffscrapr)
