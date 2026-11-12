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

**Amended 2026-11-12, operator direction (the viewer's label fit).** The operator:

> "even with win now enabled, it's still dynasty. So more so I just expect that it's blended into
> dynasty specific trade cards, but the aggressive ends (all in and tanking) should get more of
> those trade suggestions if they have significant gaps or older less valuable producers."

Agreed direction: a Tanking or Rebuilding **viewer's** re-scored team plan reads the label table
(the mirror table, lld §3.3: win-now pieces out, a win-now RB most of all; rebuild pieces, young
cornerstones and picks in; Tanking at full strength, Rebuilding at 0.6) without partner matching.
Knob `season_viewer_label_fit` (default 1; 0 = the age table exactly as before). It is a ranking
term inside the existing clipped team-plan term, beside the shed term: the set of cards and their
terms are unchanged, only the order moves. **Stage 2 now means partner matching only**
(`season_partner_matching`, still off): league-mates' plan fit is untouched at stage 2 off.
**Never milder than the age rule (same day, coordinator direction).** The table alone was milder
than revision 2 on win-now RBs over 24 (−0.8 against −1.0) and turned older cornerstones from −0.45
to +0.2. Where the label decides for a win-now piece (RB or not) or an older cornerstone, the fit
is now the lower of the table's and revision 2's age fit, both at the outlook's scale (`NEVER_MILDER`;
Rebuilding stays exactly 0.6 × Tanking). Young cornerstones, rebuild pieces and picks take the
table's fit. No constant changed.

Measured on the fixture league (knob 0 → 1, combined rule): the first 30 are unchanged for both
Tanking and Rebuilding (30 of 30, same order); about 2% of cards' ranking score moves, at most 0.013
(Tanking) / 0.025 (Rebuilding). The only fits that still differ from the age rule are the ones
where the age rule was soft on a seller's piece or wrong on a rebuild piece (a young win-now piece
+0.45 → −0.45, a young win-now RB −0.15 → −0.8, a young backup RB coming back −0.15 → +0.7), and
those cards sit outside the first 30. The first 30 already sell older producers through the age
rule and the shed term (15 of 30 Tanking cards send a win-now piece, against 10 for revision 2),
and two limits stop the plan term moving them further: the ranker orders by the weaker side's
support, and the viewer is the weaker side on only 11 (Tanking) / 8 (Rebuilding) of the first 30;
and the team-plan term is capped at 0.20 and already saturated on 14 Tanking cards. What would
move it (approximate re-rank, not built): a plan weight of 0.3 on both sides (Tanking 14 → 19 of
30 sending a win-now piece), or a sell bonus outside the clipped plan term, applied to both supports
as the demotion is, of 0.05 × the card's market share of older producers sent (14 → 22)
([lld §3.1](lld.md)).

**The sell bonus (2026-11-12, operator approved: "Spin up a subagent to… write the sell bonus").**
Built as recommended: for a Tanking / Rebuilding viewer, both supports move after eligibility by
b × the card's market share of older producers (win-now pieces, older cornerstones) sent minus
received, outside the clipped team plan; b = 0.05 Tanking / 0.03 Rebuilding
(`season_sell_bonus_*`, ≤ 0 off); a negative bonus is dropped on a card the conflict rule
demotes. Same cards, order only. Measured with the real ranker (first 30, off → defaults):
fixture Tanking sends a win-now piece 15 → 19 (an older producer 17 → 23), 17 of 30 kept;
Rebuilding 13 → 19 (14 → 22), 22 kept; a 12-team synthetic league Tanking 13 → 23, 18 kept,
Rebuilding 18 → 24, 23 kept; a 14-team synthetic league with few older producers barely moves.
Largest support move 0.029 (Tanking) / 0.018 (Rebuilding). The approximate re-rank had said
22 of 30 for Tanking at 0.05; the real ranker gives 19 (fixture). ([lld §3.1](lld.md))

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
