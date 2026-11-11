# Win-now season signal

**Status:** plan, nothing built · 2026-11-11 · baseline `origin/main` @ `8b5f076a` · branch
`plan/win-now-season-signal`

## The problem, in the operator's words

> "If I'm win now, how does the generator (and the entire process) know which RBs to suggest to me?"

Mostly it does not. Research (`docs/research/window-asset-identification/`, on its own branch) and
this plan's own reading of the code agree: "win-now" is computed from age and position; the lineup
check is in dynasty value, so a starter and a backup of equal value score the same; a saved All-in
plan cannot flag a trade that works against it; and "Win-now: adds X" on a card is an age claim.
The trigger was an All-in team with the league's best RB room being shown a 23-year-old backup RB
for a 33-year-old WR who starts.

## The capability

The trade engine reads the league's saved weekly projections, already captured for the playoff
forecast, and uses them for teams trying to win now. A player helps an All-in team when he **starts
for that team and adds points**, not when he is old. The same numbers give every player a label
(win-now piece, cornerstone, rebuild piece) that the engine reads and the card prints.

## What changes for a user

- **All-in / Contending:** more cards that bring back someone who starts for you. Each says what it
  does this season and what it costs: `Season +2.1 pts/wk · Dynasty cost 3%`.
- **Any saved plan:** a card that works against it is pushed down the deck and says so:
  `You rank {name} above market, but this moves away from All-in`. It is never removed.
- **Not sure, the off-season, ESPN/MFL/Fleaflicker, or no current forecast:** exactly today's deck.

Prototype on a synthetic league with real players and real Sleeper projections, first 30 served
cards, All-in viewer: lineup points added per card 0.7 → 2.5 a week; cards that add a starter
48% → 77%; cards that cost lineup points 28% → 6%; deck size and search time unchanged; the age of
players received unchanged ([validation §2](validation.md)).

## Decisions

**Made by the operator, 2026-11-11:**

1. Feed Sleeper weekly projections into the main deck for win-now teams.
2. Off-season signal deferred. No projection, no change.
3. Win Now stays a separate feature.
4. Build now, beside the rules-first deck build.
5. A plan-conflict card is pushed down **and** states the conflict.
6. Labels are an engine input, defined precisely, derived from the engine's numbers, and graded by
   the operator before they affect a served deck.

**Made in this plan (reversible, each justified where cited):**

- The engine reads the **label** for "what kind of asset is this for this team" and the **number**
  for "how much" ([hld §6](hld.md#6-labels-what-the-engine-reads)).
- Season scoring applies to the viewer's team first; league-mates' side is a second, separately
  graded step ([open question 1](open-questions.md)).
- A new bilateral revision (`owner-v2-bilateral-5`) built dark, not an edit to revision 2.
- The push-down is a fixed penalty of 0.10 on the ranking score, the size revision 4 already uses.

**Open:** [open-questions.md](open-questions.md) (seven, two needed before serving).

## Files

| File | What it is |
|---|---|
| [prd.md](prd.md) | The rules per outlook, the season value and label definitions, the conflict rule, card copy, the operator's example before and after, acceptance criteria |
| [hld.md](hld.md) | Data flow, the season map, who reads it and who must not, flags, failure modes, the seam with rules-first |
| [lld.md](lld.md) | Schemas, algorithms, proof and payload fields, change list with sizes, invariants and sabotages |
| [validation.md](validation.md) | Prototype results, replay, label review, Calibration round, guardrails, production read |
| [scope.md](scope.md) | The feature-scope block for the first slice |
| [build-plan.md](build-plan.md) | Work items, parallelism with rules-first, rollout, kill switches, TestFlight checklist |
| [open-questions.md](open-questions.md) | What the operator still has to decide |

## How it fits with the rules-first build

Rules-first decides which packages may be shown; this decides how good an admitted package is for
you and what the card says. They share no logic and four small touch points
([hld §11](hld.md#11-the-seam-with-the-rules-first-build)). Everything up to serving can be built
and graded in parallel. Serving at rules-first speed needs one joining work item after rules-first
merges; without it, or if rules-first is off, the new revision serves at today's speed.

## Size

About 1,400 lines of backend code and 110 of mobile, with roughly twice that in tests; seven or
eight backend builder sessions and one mobile. No schema change, no new user route, no new client
event. One app build for the full card; the first serve does not wait for it.
