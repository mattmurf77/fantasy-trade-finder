# Win-now season signal — open questions for the operator

**Date:** 2026-11-11. Most important first. Each has a recommendation; none blocks the dark build
(stages A and B). The ones marked **before serve** must be answered before stage C.

Already decided and not listed here: feed Sleeper weekly projections into the main deck for win-now
teams; no off-season signal for now; Win Now stays separate; build beside rules-first; a card that
works against a saved plan is pushed down **and** says so; labels are an engine input, graded before
they affect a deck. See the [README](README.md).

Related, decided elsewhere: whether cards show a 1–10 grade per input, and whether ranking becomes a
user-weighted average, is being assessed in `docs/plans/card-logic-grades/assessment.md`. This plan
records its parts separately so either answer fits ([hld §7](hld.md#7-named-components-for-a-later-grades-view)).

---

## 1. Seller–buyer matching: serve it with the first release, or one step later? — before serve

Matching makes your league-mates' side read the labels too: a rebuilder is treated as willing to
sell win-now pieces, a contender as wanting players who would start for it.

| Option | Consequence |
|---|---|
| **One step later (recommended)** | The first release changes decks only for users with a win-now outlook, plus the push-down for Rebuilding and Tanking. "Not sure" users are provably untouched. Matching then gets its own replay and its own graded deck |
| With the first release | One release, one grading pass. But every user's deck moves at once, including users who saved no plan, and a bad result cannot be traced to one cause |

Why later: in the prototype, scoring the other team in points as well changed every outlook's deck
(20–22 of the first 30 kept) and made the All-in viewer's own result worse (1.4 points a week added
against 2.2). The matching in this plan is narrower than that test, but it is still the riskier
half, and most league-mates' outlooks are read from rosters, not saved (a median of one saved
outlook among a request's league-mates in the recorded requests).

## 2. A team with no saved outlook that the engine reads as Contending: season-score it? — before serve

Fifteen of the 247 recorded requests are this case. The engine already treats such a team as
Contending, using age.

| Option | Consequence |
|---|---|
| **Yes, score it; never call a conflict (recommended)** | Consistent: whatever outlook the engine uses, it uses the better measure. No "moves away from your plan" line, because no plan was saved |
| No: saved plans only | The cleanest reading of "win-now teams". But a user who never opened the outlook picker keeps the age rule, and "Win-now: adds X" stays an age claim for them |

## 3. A plan-conflict card that qualified because the player is on your target list: push it down too?

The decision covered cards that qualify through your rankings. A target list is a more direct
instruction.

| Option | Consequence |
|---|---|
| **State it, do not push it down (recommended)** | You asked for the player, so he stays where his score puts him, with the sentence "{name} is on your target list, but this moves away from All-in" |
| Push it down as well | One rule for every conflict. But the app would be burying a player you explicitly asked for |
| Say nothing | Simplest. The card that most deserves the warning would not carry it |

## 4. Cheap veterans who would start for you still cannot appear. Change that?

The deck's quality rule drops any card holding a piece under 450 in dynasty value, whatever he
scores. In the fixture league four startable players sit under it, Travis Kelce among them
(11.7 a game, value 255). An All-in team is exactly who wants that trade.

| Option | Consequence |
|---|---|
| **Yes, as a follow-up after both builds land (recommended)** | One added clause in the rules-first predicate: a received player who starts for the viewer is not filler. It reads the season map, so it waits until rules-first has merged and the season signal is serving |
| Leave it | Simpler. All-in decks never offer a cheap rental |
| Do it now | It makes the two parallel builds touch the same rule, which this plan avoids |

## 5. The forecast is saved once a week, on Tuesday morning. Enough?

By Sunday it is five days old. A player ruled out on Friday is still removed (the injury check is
live), but a role change is not seen until the next Tuesday.

| Option | Consequence |
|---|---|
| **Accept for the first release, decide after stage A (recommended)** | Stage A's log shows how often the forecast is stale or unusable at search time. No change to the forecast feature now |
| Add a second weekly update (for example Saturday morning) | Fresher season values. Doubles the forecast work and touches the forecast schedule while the forecast model itself is being changed (v6) |

## 6. Label names and starting numbers

To settle while grading, not before. Two things worth a yes or no now:

- **"Cornerstone"** as the name for the "both" label (starts now, holds future value).
  Alternatives: "Core piece", "Both". Recommended: Cornerstone.
- **A young starter with a small price is a win-now piece.** By the rule, Josh Downs (24) and Bucky
  Irving (23) are win-now pieces: they start in the league and the market gives them little future.
  That is what the rule is for, and it will look odd on first sight. If it reads wrong to you, the
  fix is a lower future floor or an age guard; say so in the label review.

## 7. If trade swipes start teaching rankings again, should likes on season-led cards count?

Today they cannot: the bake-off freezes trade-swipe learning. D-184 says season-motivated choices
must not teach dynasty rankings.

| Option | Consequence |
|---|---|
| **No (recommended)** | When the freeze is lifted, a like on a card whose reason was season value teaches nothing. Needs one small rule at that time, keyed on the proof's season record |
| Yes | Liking a rental would raise an old player on your dynasty board, the thing D-184 forbids |
