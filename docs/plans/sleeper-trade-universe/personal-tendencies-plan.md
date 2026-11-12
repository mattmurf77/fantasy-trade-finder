# Test and validation plan — one manager's own valuations and trade tendencies

**Date:** 2026-11-12 · **Status:** plan; analysis starting on the operator's own data · **Entry point:** direct ask (operator)

> "One other hypothesis I have is user specific valuation / trade tendencies. Run that analysis with a subagent on me first. You can use offers, declines and counters from yesterday's pull for this analysis. Write a full test/validation plan first."

Companion to [research-plan.md](research-plan.md). That plan studies many leagues through completed trades only. This one studies **one manager in depth**, using the data the wide pull cannot have: offers that were made and not accepted.

## Contents

1. [The question](#1-the-question)
2. [Data](#2-data)
3. [What an offer is, and how it is labelled](#3-what-an-offer-is-and-how-it-is-labelled)
4. [Hypotheses](#4-hypotheses)
5. [Method](#5-method)
6. [Validation](#6-validation)
7. [What counts as a result](#7-what-counts-as-a-result)
8. [Threats, and what is done about each](#8-threats-and-what-is-done-about-each)
9. [Privacy](#9-privacy)
10. [Steps and gates](#10-steps-and-gates)
11. [After the operator](#11-after-the-operator)

---

## 1. The question

Does one manager value players and picks, and negotiate, in ways that are **stable, different from the market, and predictive of what they do next**? If so, the app should learn those tendencies per user and use them to order cards, size asks and suggest counters. If not, per-user tuning is noise and the market value plus league context is enough.

The test is deliberately strict because the data is one person's. A tendency only counts if it holds on data it was not fitted to.

## 2. Data

Five sources. Three are independent records of the same person's preferences, which is what makes validation possible.

| Source | What it holds | Size | Limits |
|---|---|---|---|
| A. Sleeper inbox offers (local export, 2026-11-10) | Trade offers sent and received since mid-2022 across three leagues, in conversation order, so counters are visible | Several hundred offers; roughly two in three sent by the operator; a few dozen counterparties | Sleeper's web inbox shows only the latest 50 messages per conversation, so long conversations lose their early history. Offers carry no accepted or declined status |
| B. In-app decisions | Likes and passes on generated cards since April 2026, with pass reasons where given, and which cards were shown | About a thousand decisions | Cards are chosen and ordered by the engine, so the sample is not neutral (§8) |
| C. Stated preferences | The operator's own rankings and tiers; Keep and trade-block lists | Current state, plus ranking history | A statement, not behaviour |
| D. Completed trades in the three leagues | Every trade that went through, by anyone | Already stored | Used to label outcomes in A and for league base rates |
| E. Dated market values | KeepTradeCut daily and DynastyProcess weekly values on each offer's date | Being built (research-plan §5.6) | Players outside today's top 500 and picks for past drafts may lack KeepTradeCut history |

Also used, from the pull program once it has run on the operator's leagues: each team's roster, record and remaining schedule on the date of each offer, so the operator's and the partner's outlook at that moment is known.

Message text is not used. Only the trade cards in the conversations are read.

## 3. What an offer is, and how it is labelled

**Unit:** one offer = date, league, who proposed, what each side gives. A **thread** is the run of offers between the same two managers about overlapping assets.

**Outcome labels**, inferred because Sleeper shows none:

| Label | Rule |
|---|---|
| Accepted | A completed trade in the same league with the same assets, shortly after the offer |
| Accepted with changes | A completed trade between the same two teams sharing most of the assets |
| Countered | The other manager's next offer in the thread, within a set window, sharing assets |
| Revised | The same manager's next offer in the thread, sharing assets |
| Dead | None of the above |

"Dead" mixes declined, ignored, withdrawn and expired. The analysis never treats it as an explicit "no" from a named cause.

**Label check (gate 1):** the operator hand-checks 25 randomly drawn offers against memory. Target: at least 90% agree. Below that, the labeller is fixed before any analysis runs.

## 4. Hypotheses

Each is stated so it can fail. All are about the operator; "market" means the dated value on the offer's date.

### Valuation

| # | Hypothesis | Read from |
|---|---|---|
| P1 | The operator values some positions above or below market, consistently | What is asked for and given up in sent offers; what is accepted and passed |
| P2 | The operator values youth, or production, more than the market does | Age and recent points of assets sought against assets offered |
| P3 | The operator values picks differently from the market, and discounts future years at their own rate | Picks sought and offered, by round and year |
| P4 | Endowment: the operator asks more for their own players than they would pay for the same player | The same player on both sides of offers over time; received offers passed at market-fair prices |
| P5 | Stated rankings predict behaviour better than market values do | C against A and B |
| P6 | Players on the Keep list behave as stated: no offer for them is accepted at any price | Received offers that include them |

### Asks and acceptance

| # | Hypothesis | Read from |
|---|---|---|
| P7 | Sent offers carry a consistent margin in the operator's favour by market value | Value gap of sent offers |
| P8 | The operator accepts received offers only above a threshold, and the threshold is stable | Value gap of received offers, accepted against not |
| P9 | The operator's offers are accepted more often when the margin asked is smaller, and there is a margin that maximises deals done | Sent offers, accepted against not, by gap |
| P10 | Acceptance by the partner depends on the partner's outlook and on trade shape as well as on value | Sent offers, with the partner's standing at the date |

### Structure and negotiation

| # | Hypothesis | Read from |
|---|---|---|
| P11 | The operator prefers certain shapes (for example giving two for one) more than the league does | Shape of sent offers against league completed trades |
| P12 | Counters move a consistent fraction of the way toward the other side | Value gap across consecutive offers in a thread |
| P13 | Deals that close do so within a small number of rounds; long threads rarely close | Thread length against outcome |
| P14 | The operator returns to the same targets: a player sought once is sought again | Repeat appearances of an asset across threads and months |

### Context

| # | Hypothesis | Read from |
|---|---|---|
| P15 | The tendencies shift with the operator's own standing: buying production when contending, picks when not | Offers by the operator's outlook at the date |
| P16 | The tendencies are the same in all three leagues despite different formats | Per-league estimates |
| P17 | The tendencies are stable from year to year | 2024 against 2025 against 2026 |
| P18 | Activity has a calendar: more offers around the draft, the deadline and after losses | Offers by week and by recent results |

## 5. Method

- **Describe first.** Counts, rates and value gaps with intervals, per hypothesis, before any model.
- **Revealed preference.** Sending an offer says the operator values what they get above what they give. Accepting a received offer says the same; not accepting says less (§3). Each offer becomes an inequality in the operator's own values.
- **Personal value model.** A small set of multipliers on market value (by position, age band, pick round and year, own player or not), fitted so the operator's choices are best explained. Each multiplier is pulled toward 1.0, the market, unless the data clearly disagrees. With one person's data this shrinkage matters more than the model's form.
- **A fixed, short feature list.** At most eight features, written down before fitting (gate 2). No searching for features on the test data.
- **Baselines every result is compared with:** market value alone; market value plus league format; the engine's current ordering (for source B).

## 6. Validation

A tendency is reported as real only if it passes the checks that apply to it.

| Check | What it guards against |
|---|---|
| **Time holdout.** Fit on offers through 2025; test once on 2026 | Fitting noise |
| **Cross-source.** Fit on Sleeper offers (A), predict in-app likes and passes (B); and the reverse | A finding that exists in one data source only |
| **Leave one league out.** Three leagues, three formats | A league-specific habit read as a personal trait |
| **Leave one partner out** | Learning one counterparty's behaviour instead of the operator's |
| **Shuffle test.** Re-run with outcomes shuffled within league and season | Patterns that appear by chance |
| **Intervals by thread.** Offers in one thread are not independent; resample whole threads | Overstated certainty |
| **Many comparisons.** Eighteen hypotheses: correct for it, report all of them | Cherry-picking |
| **Minimum data.** At least 30 relevant offers and an interval that excludes "no effect"; otherwise the result is "not enough data" | Stories from a handful of cases |
| **Placebo.** A feature that cannot matter (for example the player's name length) must show nothing | A method that finds effects everywhere |
| **Stability.** Same sign in 2024, 2025 and 2026 | A phase read as a trait |
| **Skeptic pass.** A second agent tries to break each finding | The analyst's own blind spots |

The 2026 holdout and the cross-source test are each run **once**, after the model and features are frozen.

## 7. What counts as a result

**For the hypothesis as a whole** ("this manager has usable personal tendencies"):

| Test | Baseline | Pass |
|---|---|---|
| Predict which received offers were accepted (2026 holdout) | Market value gap alone | Better, with an interval that excludes no gain |
| Predict in-app likes against passes from a model fitted only on Sleeper offers | Market value gap alone; the engine's order | Better than both, with an interval that excludes no gain |
| Re-order the operator's past decks with the personal model | Order as served | Liked cards move up on average |

If none pass, the honest conclusion is that per-user tuning does not earn its complexity for this manager, and that is reported as plainly as a positive result would be.

**For each tendency:** the checks in §6. Findings are listed by confidence: confirmed, suggestive, not enough data, contradicted.

## 8. Threats, and what is done about each

| Threat | Effect | Handling |
|---|---|---|
| Inbox shows only the latest 50 messages per conversation | Old and long negotiations are under-represented | Flag capped conversations; report results with and without them |
| Outcomes are inferred | Wrong labels blur every result | Gate 1 hand-check; "dead" never read as a reasoned decline |
| Sent offers are not a random sample of trades considered | They show what the operator hoped to get, not indifference points | Treated as inequalities (§5), and checked against received offers and in-app decisions |
| Hindsight in values | A player who later broke out looks like a bargain | Only values dated on or before the offer |
| In-app cards are chosen and ordered by the engine | Likes reflect what was shown and where | Control for card position; compare within a deck |
| Acceptance depends on the other manager | A "margin that works" may be about partners, not the operator | P9 and P10 include the partner's standing; leave-one-partner-out |
| Preferences drift | A 2023 habit may be gone | Stability check; weight recent seasons in the profile |
| One person | Nothing here generalises by itself | §11 |

## 9. Privacy

- The subject is the operator, at their own request, on their own data.
- Counterparties appear only as "Partner 1", "Partner 2". No usernames, ids or message text in any output.
- The inbox export stays in the git-ignored data folder. It is not committed, uploaded or copied elsewhere.
- **Results are not committed.** The findings report and the personal profile are written to the local data folder and sent to the operator. Only this method document is in the repo.

## 10. Steps and gates

| Gate | What | Pass |
|---|---|---|
| 1 | Data audit; offer and thread table; outcome labels | Operator's hand-check of 25 offers agrees at 90% or better; capped conversations counted |
| 2 | Freeze the hypotheses, features and splits | This document plus the feature list, recorded with a checksum before fitting |
| 3 | Descriptive results and model fitting on the training span | Shuffle and placebo checks behave |
| 4 | The 2026 holdout and the cross-source test, once each | §7 |
| 5 | Skeptic pass | Each finding kept, downgraded or dropped, with the reason |
| 6 | Report to the operator | Findings by confidence; the personal profile; what the product would do with each |

Unpriced questions (shape, threads, calendar, repeat targets) can run as soon as gate 1 passes. Priced questions wait for the dated values.

## 11. After the operator

One manager proves the method, not the hypothesis for everyone. If the operator's result is positive:

1. **Users who connected Sleeper:** the private offers read already collects their own offers with exact statuses. The same analysis runs per user as their history grows, under the consent they gave for that read.
2. **Users with only in-app decisions:** a lighter profile from likes, passes and rankings.
3. **League-mates and the wider pull:** completed trades only, keyed by the hashed owner key. That supports the cross-league consistency questions (M1 to M3 in the research plan) and gives the population averages that each personal profile is pulled toward.

How many decisions a user needs before a personal profile beats the market is itself a result of this work, read from how the operator's profile performs when fitted on only their first 50, 100 and 200 decisions.
