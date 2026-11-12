# Win-now season signal — product spec

**Date:** 2026-11-11 · **Status:** spec, not built · **Entry point:** operator ask ("If I'm win now,
how does the generator know which RBs to suggest to me?") and the decisions of 2026-11-11

Design in [hld.md](hld.md) and [lld.md](lld.md). Numbers marked *prototype* come from an offline run
on the public player fixture and the committed Sleeper projections fixture
([validation §2](validation.md)); they describe a synthetic league, not production.

- [1. Who it is for, by outlook](#1-who-it-is-for-by-outlook)
- [2. Season value](#2-season-value)
- [3. The two numbers on the card](#3-the-two-numbers-on-the-card)
- [4. Labels](#4-labels)
- [5. When a card works against your plan](#5-when-a-card-works-against-your-plan)
- [6. Copy rules](#6-copy-rules)
- [7. The operator's example, before and after](#7-the-operators-example-before-and-after)
- [8. What does not change](#8-what-does-not-change)
- [9. Non-goals](#9-non-goals)
- [10. Acceptance criteria](#10-acceptance-criteria)

## 1. Who it is for, by outlook

The rules below apply in a league with a usable forecast (§2.5). Without one, every outlook gets
today's deck, unchanged.

| Your outlook | What changes for you |
|---|---|
| **All-in** | You are offered players who **start for you this season** and add the most projected points over who they replace, whatever their age. A player who would sit on your bench counts the same as a draft pick: future value, not help now. Giving up a starter whose points are not replaced counts against the trade. Cards that cost your lineup points are pushed down and say so. |
| **Contending** | The same rules at 60% strength (the engine's existing Contending weight). A card is called out only when it costs your lineup at least a point a week. |
| **Rebuilding** | *Amended 2026-11-11, operator direction.* The opposite curve to Contending: the same cards and terms as today, **ordered** so that trades which **give up lineup points a week** for future value rank higher and trades that add lineup points rank lower, at half the All-in strength (`season_shed_weight_rebuilding` 0.5). It changes the order only: no card is added or removed, nothing about fairness, the market floor or what you must be paid changes. A card that adds **1.0 point a week or more**, or whose best incoming piece is a **win-now piece** while more future value leaves than arrives, is pushed down and says so. *Amended 2026-11-12, operator direction:* the plan part of that ordering reads the labels (§4): giving up a win-now piece ranks a card higher and taking one on ranks it lower, a win-now RB most of all, while bringing back rebuild pieces, young cornerstones and picks ranks it higher, at 0.6 of Tanking's strength. Still the order only. |
| **Tanking** | *Amended 2026-11-11, operator direction.* The opposite curve to All-in, at full strength (`season_shed_weight_tanking` 1.0): a point a week shed counts for the trade exactly as a point gained counts for an All-in team. Same cards and terms as today; only the order changes. The conflict threshold is **0.5 points a week added**, plus the win-now-piece rule. Today's hard Tanking rules stay (no outgoing own next-year pick, no RB without a long-term case). *Amended 2026-11-12, operator direction:* the plan part reads the labels as for Rebuilding, at full strength. |
| **Not sure** | Nothing changes. Same cards, same order. |
| **No outlook saved** | The engine already reads your roster as Contending, Rebuilding or Not sure. A roster read as Contending gets the season scoring; a roster read as Rebuilding gets the Rebuilding ordering (amended 2026-11-11). Nothing is ever called a conflict, because you saved no plan. |

Stage 2, built in the same work but switched on separately: the same labels decide what your
league-mates are willing to sell and buy, so a rebuilder's win-now pieces are matched with the
contenders who would start them. That changes decks for every outlook and gets its own grade first
([validation §7](validation.md)).

## 2. Season value

### 2.1 Projected points

For each rostered player: the league's own scoring applied to Sleeper's weekly projections, averaged
over his upcoming games in the rest of the **regular season**. Source: the league's latest saved
forecast (the one behind the playoff odds). Fantasy playoff weeks are not in that forecast and are
not counted.

- **Upcoming** means weeks that have not started. A week in progress is left out for everyone.
- **Byes** are not games. A player's number is points per game, so a bye neither helps nor hurts him.
  (This slice does not model the week he misses.)
- **Injuries:** a player listed Out, IR, PUP, Suspended, Doubtful or Inactive does not count toward
  any lineup, exactly as today.
- **Unprojected players** (no forecast row, a changed NFL team, a waiver add since the forecast was
  saved) are **unknown, never zero**. They cannot start in the season lineup and no card makes a
  season claim about them.

### 2.2 Starts for you

Your **season lineup** is the best legal lineup your roster can field in your league's real
starting slots, flex and superflex included, by projected points per game. A player **starts for
you** when adding him to your roster raises that lineup by at least **0.5 points a week**.

### 2.3 Season value of a player to a team

*The points per week your best lineup gains with him on the roster, compared with the roster
without him.* If he starts, that is his points minus the points of whoever he pushes out. If he
would not start, it is zero. It is specific to the team: the same RB can be worth 4 points a week to
one roster and nothing to a roster already full at RB and flex.

**Replacement** is therefore your own next man up at that slot. If your roster has nobody for the
slot, the replacement is the best projected free agent for it (0 if there is none). That is the same
rule the playoff forecast is adopting in its next version, and the season map reuses that number
when the saved forecast carries it.

### 2.4 Season value of a trade

*Your season lineup after the trade minus your season lineup before, in points per week.* This is
the number on the card. It handles two incoming players competing for one slot, which adding up
single-player values would get wrong.

### 2.5 When the forecast is usable

All of these must hold, otherwise the request behaves exactly as today:

1. the league is on Sleeper and has a saved forecast;
2. the forecast was made by the current projection model and is from this week's update;
3. at least one whole upcoming regular-season week remains;
4. the league's starting slots have not changed since it was saved;
5. you hold no healthy, unprojected player worth 450 or more in dynasty value.

Rule 5 is the lineup-completeness rule of the forecast model, narrowed to the one team whose lineup
the engine is reading. The forecast's own rule withholds a suggestion for the whole league when any
team has an unknown slot (D-230); a trade search only needs the viewer's lineup to be known.

**Off-season, unsupported platforms, stale or missing forecasts:** today's behaviour, unchanged.
No season line, no label, no conflict line. Proven by test: same cards, same terms, same order as
revision 2.

## 3. The two numbers on the card

One line on the **You** side of every card built with a usable forecast, for All-in and Contending
viewers:

> **Season +2.1 pts/wk · Dynasty cost 3%**

- **Season** is §2.4, to one decimal. Shown as `+2.1`, `−1.8`, or `no change` inside ±0.5.
- **Dynasty** is the market value you give minus the market value you get (the card's own priced
  package, the same numbers behind its fairness score), as a share of your whole roster's market
  value including picks. `cost 3%` when you pay, `gain 2%` when you are paid, `even` inside ±0.5%.
  Same idea as Win Now's "dynasty budget" (a share of roster value), on market value instead of
  your personal board, because the deck's fairness is on market value.

**Where.** The deck card's fit block, under the You lead. It needs the next app build. Installed
builds show the season number inside the You lead text instead (§6), because they print whatever
lead the server sends. The web deck does not render the fit block today and is not changed.

## 4. Labels

A label says what kind of asset a player is **in this league, this season**. It is computed from
the same projected points and the same market values the engine scores with. There are three
labels; most players get none.

### 4.1 The league's starter line

For each position: count how many players at that position start when every team in the league
fields its best season lineup. If 33 RBs start league-wide, the **starter line** at RB is the 33rd
best projected RB on any roster. A player is **startable** when he projects at least a margin above
the line, **not startable** when at least a margin below, and **borderline** in between. The margin
is 0.5 points a week or 5% of the line, whichever is larger (QB projections are bunched, so QBs get
a wider band).

### 4.2 Future value

*Dynasty market value minus what this season explains.* This season explains 400 value points for
every point per week he projects above the starter line. A player worth 3,000 who projects 2 points
above the line has 3,000 − 800 = 2,200 of future value. The rate (400) and the floor below (1,500,
between a second- and a first-round pick) are starting values, to be set by the operator's grading
(§4.6).

### 4.3 Definitions

| Label | A player is this when… | In plain words |
|---|---|---|
| **Win-now piece** | startable, **and** (future value under 1,500 **or** past his position's age cliff: RB 27+, WR 30+, TE 32+) | He starts in this league and most of what you pay for is this season |
| **Cornerstone** (the "both" label) | startable, future value 1,500 or more, not past the cliff | He starts now and the market still prices a future |
| **Rebuild piece** | not startable, worth 450 or more, and young for his position (QB ≤ 27, WR ≤ 25, TE ≤ 25, RB ≤ 24). Draft picks count as rebuild pieces | Value that is all future |
| *no label* ("neither") | everyone else: bench veterans, depth, borderline players, unprojected players | Nothing is printed |

The age cliff is the engine's existing production curve (`trade_service.py:3439-3451`), used only to
stop a 29-year-old RB being called a cornerstone. It never makes anyone a win-now piece on its own:
he has to start.

*Prototype, fixture league:* 36 win-now pieces, 48 cornerstones, 16 rebuild pieces; 141 unlabelled
depth players, 37 borderline, 10 unprojected. Christian McCaffrey, Derrick Henry, Josh Jacobs,
Davante Adams, Travis Kelce: win-now piece. Justin Jefferson, Bijan Robinson, Josh Allen, Brock
Bowers: cornerstone. Makai Lemon: rebuild piece. Patrick Mahomes and Lamar Jackson: borderline (a
1-QB league starts 12 QBs who all project within a point of each other). **17 of the 36 win-now
pieces are under 27**: players today's age rule cannot see. Across four different league
make-ups, 2 of 272 players changed label.

### 4.4 The label for a given team

The league label is the same for everyone. What the engine reads for *your* plan adds one fact:
**starts for you** or **would not start for you** (§2.2). So a card can say "Win-now piece · would
not start for you", which is the operator's RB case.

### 4.5 How the engine uses labels

| Use | Rule |
|---|---|
| **Plan fit** (All-in, Contending viewer) | An incoming or outgoing player scores by a small table: starts for you and is a win-now piece or cornerstone: full credit. Starts for you with no league label: partial credit. Would not start for you: the same as a pick. The table replaces the age curve for these teams |
| **Lineup gain** | Not a label: the trade's points per week (§2.4), the number on the card |
| **Candidate seats** | Each league-mate's players who would start for you are guaranteed places among the candidates the search tries, best lineup gain first. Your own non-starters and picks are guaranteed places among what you might send |
| **Plan conflict** | §5 |
| **Plan fit** (Rebuilding, Tanking viewer; amended 2026-11-12, operator direction) | The plan part of the ordering reads a second table: a win-now piece out scores for the card and in against it (a win-now RB most of all); a rebuild piece, a cornerstone (most of all a young one) or a pick in scores for it and out against it; Tanking at full strength, Rebuilding at 0.6. It reorders the same cards (`season_viewer_label_fit`) |
| **Seller–buyer matching** (stage 2) | A Rebuilding or Tanking team is treated as willing to sell its win-now pieces and wanting rebuild pieces, cornerstones and picks; a Contending or All-in team as wanting players who would start for it |

The card prints the label the table was read with. They cannot differ: both come from one record
frozen into the card's proof ([hld §6](hld.md#6-labels-what-the-engine-reads)).

### 4.6 Grading the labels before they affect a deck

Labels do nothing to a served deck until the operator has graded a sample.

- **The sheet.** For one league at a time, a review page lists every rostered player with his
  label, projected points per game, dynasty value and the league's starter line, top dynasty values
  first. For each row: agree, or pick the label it should have. A second short list shows your own
  roster with "starts for you" yes or no.
- **The bar.** At least two leagues and 120 labelled players graded. At least 85% agreement on
  labelled players. No disagreement left unexplained among the 24 most valuable players in each
  league. The "starts for you" list right on at least 9 of 10 rows.
- **If it misses.** Change the rate, the floor or the margin, bump the label rules version,
  regenerate, grade again. Nothing ships on a miss.
- **Record.** Counts and the rule version go in `living-memory/TEST_LEDGER.md`. No roster contents.

## 5. When a card works against your plan

Decided by the operator: such a card is **pushed down and says so**. It is never removed.

### 5.1 What counts

Only for a **saved** plan, and only when the forecast is usable.

| Saved plan | The card works against it when… |
|---|---|
| All-in | the trade lowers your season lineup by **0.5 points a week or more** |
| Contending | the trade lowers your season lineup by **1.0 point a week or more** |
| Tanking | *Amended 2026-11-11, operator direction:* the trade **adds 0.5 points a week or more** to your season lineup; or the most valuable piece you receive is a **win-now piece**, you give at least one rebuild piece, cornerstone or pick, **and** less future value comes back than goes out |
| Rebuilding | *Amended 2026-11-11, operator direction:* the trade **adds 1.0 point a week or more**; or the win-now-piece rule above |
| Not sure, or nothing saved | never |

### 5.2 How far it moves

A fixed penalty of **0.10** on the card's ranking score, the size revision 4 already uses for its
strongest demotion (four of the ranker's "near-equal" steps). It moves the card below offers of
similar quality that fit the plan, not below offers that are clearly worse. It is applied after the
card has qualified, so it cannot remove a card or change its terms.

- Applies when the card qualified through **your own rankings**.
- A card that qualified because the player is on your **target list** or matches a position you
  asked for: the conflict is stated, the card is not pushed down. You asked for him.
- A card from a search you **pinned** (a chosen player or partner): no penalty, no statement.
- Likes-you, standing-offer and revised-offer cards: untouched.

*Prototype:* for an All-in viewer, 16% of the first 30 served cards worked against the plan after
the season scoring alone; with the push-down, 6%. The flagged cards' typical position moved from
132nd to 192nd of about 222. The deck's size did not change.

### 5.3 What the card says

One sentence on the You side, composed by the server:

| Case | Sentence |
|---|---|
| Qualified by your rankings, you rate the incoming player above market | `You rank {name} above market, but this moves away from {All-in}` |
| Qualified by your rankings, you rate the outgoing player below market | `You rank {name} below market, but this moves away from {All-in}` |
| Qualified by your target list | `{name} is on your target list, but this moves away from {All-in}` |
| Qualified by a position you asked for | `You asked for {RB}s, but this moves away from {All-in}` |

`{name}` is the player whose ranking made the card qualify. `{All-in}` is your saved plan's display
name. The season line beside it carries the size ("Season −1.8 pts/wk"). On installed builds, which
have one line for the You lead, the lead reads `Away from All-in: −1.8 pts/wk`; for Rebuilding and
Tanking, `Away from Rebuilding: +2.1 pts/wk` when the points rule fired and `Away from Rebuilding:
adds a win-now piece` when the win-now-piece rule did (amended 2026-11-11, operator direction).

## 6. Copy rules

All card copy stays deterministic server templates in `backend/trade_narrative.py`, composed only
from the card's frozen proof.

1. **"Win-now" must be true.** With a usable forecast, the word appears only when the named player
   is a win-now piece **and** starts for the team named **and** the trade adds at least 0.5 points a
   week to that team's lineup. The age-only rule (`trade_narrative.py:562-564`) no longer fires for
   such a request, on either side of the card.
2. **You lead, All-in or Contending, in order:** the conflict line (§5.3); else
   `Win-now: {name} starts, +{x.x}/wk`; else `Starts for you: {name}, +{x.x}/wk` (a cornerstone or
   unlabelled starter); else today's rank facts. "Upgrades RB: adds X" is not used for a
   season-scored team: its test is in dynasty value.
2a. *Amended 2026-11-11, operator direction.* **You lead, Rebuilding or Tanking**, in order: the
   conflict line (§5.3); else, when the card sheds at least 0.5 points a week, `Rebuilding: −3.2
   pts/wk, adds {asset}` / `Tanking: −3.2 pts/wk, adds {asset}` (`Rebuild-leaning: …` for a roster
   read), `{asset}` being the most valuable incoming pick or projected rebuild piece / cornerstone,
   as the engine labelled it (full name, then the short name, ≤ 44 characters, or no such lead);
   else today's lead. The season line reads as for contenders (`Season −3.2 pts/wk · Dynasty gain
   4%`).
3. **Labels** print as a short tag beside the player on the card: `Win-now piece`, `Cornerstone`,
   `Rebuild piece`. Next app build.
4. **No forecast:** today's copy, including today's age rule, with no season line or label.
5. **Never:** a season claim about an unprojected player; a projected points figure for a
   league-mate's player beyond what Sleeper already shows everyone; an engine name or version.
6. The fit block's payload version stays `fit-2`: only wording changes there. The season line,
   labels and conflict sentence travel in a new optional block the next build reads.

## 7. The operator's example, before and after

All-in team with the league's best RB room. Offered: give Davante Adams (WR, 33), get a
23-year-old backup RB the user's own rankings rate 15% above market. *Prototype numbers.*

| | Today (revision 2) | With the season signal (revision 5) |
|---|---|---|
| Why it qualifies | your rankings like the RB (`personal_board`) | the same |
| What the engine knows | Adams is 33, the RB is 23. Nothing about roles | Adams projects 11.5 a game and **starts for you**; the RB would not |
| Season value of the trade | not computed | **−1.8 pts/wk** |
| Plan part of the score (0–1) | 0.49 (neutral) | 0.00 |
| Ranking score | 0.596 | 0.497, then **0.397** after the push-down |
| Still in the deck | yes | **yes**, further down |
| What the card says | league-rank facts only | `You rank {the RB} above market, but this moves away from All-in` · `Season −1.8 pts/wk · Dynasty even` · Adams tagged `Win-now piece` |

And the cards that move up in its place: for the same team, two RBs of equal dynasty value and both
25 years old, one a starter projecting 13 a game and one a backup projecting 4. Today the engine
scores them identically. With the season signal the starter adds 3.2 points a week (he takes a flex
spot) and is offered; the backup scores like a pick and is not.

## 8. What does not change

- Prices, package pricing, the fairness score and floor, the market floor.
- The weight of your own rankings (45% of the ranking score) and the rule that they can qualify a
  card on their own.
- Deck quality rules (breakup, filler, redundant QB/TE, repeat cap) and significance.
- Rebuilding and Tanking plan scoring; the Tanking rejections.
- "Not sure" decks, and every deck in a league without a usable forecast.
- Win Now, Team Review, power rankings, the outlook suggestion, Calibration's existing rounds.
- What a like or pass teaches your dynasty rankings (D-184: season-motivated choices must not).
  Trade swipes are frozen today while the bake-off runs (`bakeoff_runner.py:66-80`); see
  [open questions](open-questions.md).

## 9. Non-goals

- An off-season or redraft signal (deferred by the operator).
- Playoff-week weighting, bye-week modelling, injury-return timing.
- Merging Win Now into the deck, or running its season simulation per card.
- Changing the filler rule so a cheap veteran starter can appear (a rules-first matter).
- A per-input grade view on the card (separate assessment).
- Projections for ESPN, MFL or Fleaflicker leagues.

## 10. Acceptance criteria

Each is a test or a replay check named in the [build plan](build-plan.md).

1. Flag off, or selector 0: every deck is byte-identical to today.
2. Revision 5 with no usable forecast: same cards, terms and order as revision 2, for every outlook.
3. Revision 5, viewer "Not sure", forecast usable: same cards, terms and order as revision 2.
4. Revision 5, viewer Rebuilding or Tanking: the same set of cards with the same terms as
   revision 2; only flagged cards change position.
5. Two players of equal dynasty value and equal age, one who starts for the viewer and one who does
   not: for an All-in viewer the starter's plan fit is strictly higher. (Today they tie.)
6. A player who would not start for an All-in viewer has the same plan fit as a pick.
7. The operator's example (§7) is flagged, keeps its terms, stays in the deck, ranks below an
   otherwise equal card that does not cost lineup points, and carries the conflict sentence.
8. A plan-conflict card is never rejected by the penalty: the inventory with the penalty at 0.10
   equals the inventory at 0.
9. A pinned search never carries a conflict penalty or sentence.
10. The string "Win-now" appears on a card with a usable forecast only under copy rule 1.
11. For every card, the label in the payload equals the label the plan-fit table read.
12. No season claim, label or number is produced for an unprojected player.
13. The fairness score, both package values and the market floor decision are identical between
    revision 2 and revision 5 for every card present in both.
14. Replay on recorded requests: served deck size under revision 5 is at least 95% of revision 2's
    at the median, and never under 30 cards where revision 2 served 30 or more.
15. The label review bar (§4.6) is met and recorded before the selector is set to 1.
