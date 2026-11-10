# What real offers say — one manager's Sleeper trade history

**Date:** 2026-11-10 · **Source:** the operator's own Sleeper inbox, read from the signed-in
website at his request, with league-mates' consent · **Scope:** pooled aggregates only

The [acceptance evaluation](acceptance-eval.md) found fewer than 5 counterparty responses in
the app's own data. This is the first sizeable sample of how real offers are answered: 612
two-party trade offers across three dynasty leagues, June 2022 to November 2026, matched
against the leagues' public completed trades and priced at the consensus values of the month
each offer was made.

Raw messages, per-manager figures and the scripts are kept locally
(`data/sleeper-export/`, git-ignored) and are not in the repository.

## Read this first

- **One account.** 70% of the offers were proposed by the operator. The sample shows how about
  30 league-mates respond to one proposer, and how he responds to them. It cannot separate
  "what gets accepted" from "how he proposes".
- **Partial history.** The website shows only the latest 50 messages per conversation; 19 of
  38 conversations are cut off. Offer cards appear in a conversation only when the proposer
  included them.
- **Outcomes are inferred.** An offer counts as accepted when a completed league trade between
  the same managers with the same assets was created within three minutes of the card. 59 of
  the 66 completed trades inside the message windows matched a card (89%), so acceptance is
  slightly under-counted.
- **Market value is DynastyProcess, monthly, raw sums.** No package or consolidation
  adjustment, so a two-for-one looks better for the side getting two than this app's own
  pricing would say. 599 of 612 offers could be priced; picks three years out are priced as
  the furthest year the board lists; IDP players are unpriced.
- **Rapid revisions inflate offer counts.** 103 offers were replaced by the same proposer
  within 15 minutes. The negotiation thread (offers between the same two managers with no gap
  over seven days) is the fairer unit: 280 threads.

## Findings

**1. Market balance barely predicts acceptance.** Ranking offers by how much the recipient
gains at market gives an AUC of 0.58 (0.60 for offers sent to league-mates). Of the accepted
trades, only 10% were within 10% of even at market, and in 40% the manager who accepted lost
more than 10% at market. Managers accept on something other than the consensus number.

| Recipient's result at market | Offers | Accepted |
|---|---|---|
| Loses more than 30% | 223 | 7% |
| Loses 10–30% | 77 | 12% |
| Within 10% | 84 | 7% |
| Wins 10–30% | 82 | 11% |
| Wins more than 30% | 133 | 17% |

The typical offer asked the recipient to lose 10% at market. Offers to league-mates reached
21% acceptance only when the recipient won by more than 30%: buying a yes with market value
alone is expensive.

**2. Deals are negotiated, not accepted.** A first offer was accepted 8% of the time. A thread
ended in a trade 20% of the time, and the rate rises with its length:

| Offers in the thread | Threads | Ended in a trade |
|---|---|---|
| 1 | 144 | 8% |
| 2 | 58 | 21% |
| 3 | 41 | 39% |
| 4 | 16 | 31% |
| 5 or more | 21 | 57% |

Of 57 completed threads, 35 closed on a later offer, 15 of those on the other manager's
counter. After an offer that was not accepted: 44% drew no further offer within a week, 34%
were revised by the proposer, 22% were countered (median 3 hours later). 84% of counters
reused at least one asset from the offer they answered.

**3. A counter asks for more, by a lot.** 70% of counters improved the countering manager's
market position; the median counter moved it by 20 points of the trade's value. That gap is
the best available estimate of how far a first offer sits from what the other side wants.

**4. Managers hold their picks.** Offers that paid picks for players were accepted 18% of the
time; offers that asked for picks in return for players, 7%; pick-for-pick, 8%. In the text
replies, "not giving up my first" and "holding my draft capital" were among the most common
reasons. A pick is worth more to the manager who owns it than the market says.

**5. Asking for the best player in exchange for pieces works half as often.** In uneven
offers, 12% were accepted when the recipient received the trade's most valuable asset and 7%
when the recipient was asked to give it up.

**6. Small beats large.** Offers of five or more assets were accepted 6% of the time, against
10–13% for two to four. Player-only offers were accepted 16% of the time, offers involving a
pick 9%.

**7. Managers differ more than offers do.** Across the 27 league-mates who received at least
eight of the operator's offers, acceptance ranged from 0% to 36% (median 9%).

**8. What people say when they decline.** 17% of unaccepted offers drew a text reply within
three days. Of roughly 60 replies that gave a reason, in rough order of frequency:

- naming a different player or pick they would move instead (a counter in words);
- waiting on an event: a draft slot, an injury report, "after pick 1.03";
- attachment to a specific player of their own;
- holding their picks;
- the trade not fitting their team's direction (too old, too long a rebuild, wrong position);
- not rating the player being offered;
- the value being too low. This was the least common stated reason, and two replies said the
  value was fair and declined anyway.

## What it means for the engine

- **It supports the product's premise.** Consensus value alone ranks acceptance barely above
  chance, and most accepted trades are not market-even. The information that decides a trade
  is personal: who a manager will not move, who they do not rate, where their team is headed.
- **Price the counterparty's own assets above market, picks most of all** (recommendation R6).
  Findings 4 and 5 are endowment effects with numbers attached.
- **Treat a suggestion as an opening offer** (R5, and the counter-offer loop in the
  matchmaking research). Showing two or three variants of one idea, or making a counter one
  tap, matches how deals actually close; a single take-it-or-leave-it card does not.
- **Use a per-manager prior.** A 0–36% spread between managers is larger than any offer-level
  effect measured here. Trade frequency from public league history is the obvious first proxy.
- **Collect the same thing in-app.** Everything above came from outcomes and counters the app
  does not record today.

## What this cannot support

A fitted acceptance model. The sample is one proposer and about 30 respondents, the labels
are inferred, and the values are a different source from the app's. It is evidence for which
effects to build in and measure, not parameters to copy.
