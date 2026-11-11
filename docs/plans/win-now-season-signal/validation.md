# Win-now season signal — how we know it is better

**Date:** 2026-11-11 · **Status:** plan · Nothing here has run against production.

Order of gates before anything serves: **prototype (done, §2) → build → offline replay (§3) →
label review by the operator (§4) → blind Calibration round (§5) → serve → production read (§8)**.
A miss at any gate stops the next one.

- [1. What "better" means](#1-what-better-means)
- [2. Evidence already in hand (prototype)](#2-evidence-already-in-hand-prototype)
- [3. Offline replay](#3-offline-replay)
- [4. Label review by the operator](#4-label-review-by-the-operator)
- [5. Blind Calibration round](#5-blind-calibration-round)
- [6. Guardrails](#6-guardrails)
- [7. Stage 2: seller–buyer matching](#7-stage-2-sellerbuyer-matching)
- [8. Production read after rollout](#8-production-read-after-rollout)
- [9. What cannot be measured yet](#9-what-cannot-be-measured-yet)

## 1. What "better" means

For a team with a saved All-in or Contending plan, in the first 30 cards it is served:

| Metric | Definition | Direction |
|---|---|---|
| **Lineup points added** | mean, over the cards, of the viewer's season lineup after minus before (points per week) | up |
| **Adds a starter** | share of cards that raise the lineup by ≥ 0.5 points a week | up |
| **Costs points** | share of cards that lower it by ≥ 0.5 | down |
| **Starter share received** | value-weighted share of received players who start for the viewer | up |
| **Starter vs backup** | two players of equal value and age, one starts for the viewer: plan fit differs | must differ |
| **Plan conflicts in view** | share of the first 30 flagged as working against the plan | down |
| **Wrong for my window** | share of graded cards carrying the existing Calibration tag `wrong_for_my_window` | down |
| **Grade** | mean blind grade (1–5) of each engine's unique cards | not lower |

All are computed on the **served** deck: after significance, presentment and the quality filters,
not on the generator's raw inventory. That is the lesson of the 2026-11-11 fast-deck incident
(D-232): a comparison that stops at the generator proves nothing about what the user sees.

## 2. Evidence already in hand (prototype)

**What was run.** A scratch subclass of revision 2, outside the repository, with the season layer
of [lld §3](lld.md#3-revision-5). League: the research's synthetic 12-team league from the public
player fixture (`backend/tests/fixtures/player_pool_2026.json`, real players and DynastyProcess
values), viewer = the team with the best RB room, holding Davante Adams. Slots: QB, 2 RB, 3 WR, TE,
2 FLEX. Projections: the committed Sleeper fixture
(`backend/tests/fixtures/outlook-calibration/sleeper-projections-2026.json`: real weekly PPR
projections, weeks 1–14, captured 2026-08-09), which covers 309 of the 340 fixture players. Served
stand-in: the shipped `deck_quality.filter_deck` (about 225 of 2,390 generated cards survive, 9%,
close to production's 7%). Six seeds, mean. Significance, presentment and the policy step were
**not** replayed. The scripts were throwaway and are kept outside the repository; WI-4 of the
[build plan](build-plan.md) turns the method into `backend/eval/season_replay.py`.

**Limits.** Synthetic boards and rosters; preseason projections; points-to-value rate 500 and the
best-bench baseline in the engine runs (the plan specifies 400 and the starter line, which the label
runs used). Levels will differ in production. The shape is what carries.

### 2.1 First 30 served cards, viewer side only

| All-in viewer | Revision 2 | Season, numbers | Season, label table | Label table + push-down |
|---|---:|---:|---:|---:|
| Lineup points added per week | 0.72 | 2.21 | 1.87 | **2.54** |
| Adds a starter | 48% | 72% | 70% | **77%** |
| Costs points | 28% | 14% | 16% | **6%** |
| Starter share received | 83% | 93% | 93% | 94% |
| Plan conflicts in view | — | 14% | 16% | **6%** |
| Value-weighted age received | 26.1 | 26.2 | 26.1 | 26.1 |
| Served deck size | 225 | 228 | 222 | 222 |
| CPU per full solve | 3.28 s | 3.21 s | — | — |

| Contending viewer | Revision 2 | Label table + push-down |
|---|---:|---:|
| Lineup points added per week | 0.23 | 2.35 |
| Adds a starter | 42% | 72% |
| Costs points | 31% | 7% |
| Served deck size | 226 | 223 |

Reading:

- The deck moves toward players who start, by a factor of about three in lineup points, with **no
  change in the age of what is received**. Today's "win-now" is age; this is not an age effect.
- About half of the first 30 cards change (14 of 30 are the same).
- The label table gives up a little against the bare numbers before the push-down (1.87 against
  2.21) and is ahead after it. That is the "label or numbers" comparison §3 repeats on real
  requests.
- Deck size holds: −1% served, although the generator emits about 10% fewer cards.
- The cost of a search does not move.

### 2.2 Other outlooks

| Viewer | Result against revision 2 |
|---|---|
| Not sure | identical cards and order, 6 of 6 leagues |
| Rebuilding, flag only | identical, 6 of 6 |
| Rebuilding, with push-down | same cards, 6 of 6; 6% of the deck flagged; 28 of the first 30 unchanged; 1% of the first 30 flagged afterwards |
| Tanking, with push-down | same cards, 6 of 6; 3% flagged; 29 of the first 30 unchanged |

**Scoring the other team in points too** (not in stage 1) changed every outlook's deck (20–22 of
the first 30 kept) and was worse for the viewer (All-in 1.41 points a week against 2.21). That is
why stage 1 scores the viewer only, and why stage 2 is the narrower label matching with its own
gate.

### 2.3 The operator's card and the two RBs

Reproduced before and after; numbers in [PRD §7](prd.md#7-the-operators-example-before-and-after).
Today a 25-year-old starter and a 25-year-old backup of equal value are scored identically (plan
fit 0.38 each). With the season layer: +0.80 and −0.50.

### 2.4 Labels

Starter-line baseline, rate 400, floor 1,500 (the plan's rules): 36 win-now pieces, 48
cornerstones, 16 rebuild pieces; 2 of 272 players change label across four league make-ups.
Seventeen of the 36 win-now pieces are under 27. The research's two naive rules agreed on 13 of 50.
Lists in [PRD §4.3](prd.md#43-definitions).

Two mistakes found and fixed while prototyping, both now rules in the design: using the engine's
`_now_lean` as the "past his peak" test called Justin Jefferson (26) a win-now piece, because that
lean turns positive at 24–26; and using the free-agent level as the baseline made 68 players
win-now pieces against 16 cornerstones.

## 3. Offline replay

Tool: `backend/eval/season_replay.py` (new, aggregate-only output). It runs revision 2 and
revision 5 on the same request in one process, applies the served-deck stand-in (significance,
bilateral presentment, quality filters: rules-first's `served_deck_replay.py` when it exists), and
prints the §1 metrics by saved outlook.

### 3.1 Inputs

| Set | What | Season map |
|---|---|---|
| **Recorded, forward** | owner requests recorded after `trade.season_signal` is on (stage A) | recorded with the request: exact |
| **Recorded, existing** | the 247 requests in the main checkout's git-ignored `data/prod-requests/` | not recorded. Optional early look: Sleeper's public weekly projections for the request's week, scored with the format's standard scoring. Directional only: Sleeper stamps past weeks after the games (D-229) |
| **Synthetic** | `backend/eval/synthetic_league.py` leagues at 12, 14 and 16 teams, 1QB and superflex, with the fixture projections | fixture |

The existing 247 are a fair sample of who this is for (aggregates only, counted on 2026-11-11):
52 All-in and 51 Contending requests (42%), 61 Tanking, 27 Rebuilding, 7 Not sure, 49 with nothing
saved (15 of those read as Contending by the roster). Thirteen leagues, 23 manager–league pairs,
all between September and November.

### 3.2 Arms

1. Revision 2 (today).
2. Revision 5, label table, push-down 0.10 (the plan).
3. Revision 5, label table, push-down 0 (isolates the push-down).
4. Revision 5 with the plan fit read from the continuous number instead of the table, a replay-only
   switch (the "label or numbers" question).

### 3.3 The outlook flip, extended

For each request, re-run with the viewer's outlook set to each of the five values, everything else
frozen. This is the research's experiment C with three additions: the metrics are the §1 points
metrics, not age; the deck is the served deck; and each flip is run under revision 2 and
revision 5.

### 3.4 The bar

All on the recorded set with exact season maps, at least 40 requests from at least 5
manager–league pairs with a saved All-in or Contending plan:

| Check | Bar |
|---|---|
| Lineup points added, first 30, All-in | at least **+1.0 point a week** over revision 2 at the median request, and higher on at least 80% of requests |
| Adds a starter, All-in | up by at least 15 percentage points |
| Costs points, All-in | no higher than revision 2 on at least 90% of requests |
| Contending | same direction, at least half the All-in size |
| Outlook flip | under revision 5, All-in ≥ Contending > Not sure on lineup points added, in at least 80% of requests. Under revision 2 this ordering is expected to fail often; report how often |
| Label table against numbers (arm 2 vs 4) | the table within 0.3 points a week of the numbers, or ahead. If it is further behind, the plan fit reads the number and the label stays the printed summary of it; the operator is told |
| Need term clipping | reported: the share of scored cards whose lineup-gain part sits at ±1. Above half means the rate is too high |
| Guardrails | §6, all |

## 4. Label review by the operator

The gate that decides whether labels may touch a served deck. Mechanics in
[PRD §4.6](prd.md#46-grading-the-labels-before-they-affect-a-deck).

1. With the flag on in production (stage A) the operator's leagues have recorded evidence.
2. `backend/eval/season_label_review.py` fetches each league's label table from the admin route and
   writes a self-contained review page. One row per rostered player: name, position, age, projected
   points per game, the league's starter line, dynasty value, future value, label. Buttons: agree,
   or the label it should be. A second list: the operator's own roster with "starts for you".
3. The operator grades at least two leagues and 120 labelled players and exports the answers.
4. The tool reports agreement overall, per label, and for the top 24 by value, plus a confusion
   table (which label was expected in place of which).

| Check | Bar |
|---|---|
| Agreement, labelled players | ≥ 85% |
| Top 24 by dynasty value, each league | no unexplained disagreement |
| "Starts for you" | ≥ 9 of 10 rows right |
| Label stability | re-running on the next weekly forecast changes ≤ 10% of labels |

On a miss: adjust the rate, floor or margin, bump `LABEL_RULES_VERSION`, repeat. The disagreements
themselves say which knob: win-now pieces the operator calls cornerstones → rate too high or floor
too high; the reverse → too low.

## 5. Blind Calibration round

How rounds work today (`backend/outlook_calibration.py:22-32`,
`docs/plans/offer-learnings/scope-revision-4-round.md`): one frozen capture of the league per deck;
two engines run on it through the same gates; up to 20 cards from each, shared trades once with
credit to both; blind and balanced order; the user grades each card 1–5 and may tag it
(`blind_grading.py:36-37`: overpay, they won't accept, junk filler, too small, wrong for my window,
wrong for their window, same guy again). Engines are named only after the deck is finished. The
admin report gives each engine's mean grade and tag rates.

**The arm this adds.** Round `outlook-v2-v5-1`, flag `grading.season_round`: revision 2 (live)
beside revision 5, with the season evidence frozen in the capture. Built only for an account and
league with a usable forecast and a saved outlook. Rebuilding and Tanking decks are included: they
test the mirror rule and should show few differences.

| Check | Bar |
|---|---|
| Decks graded | ≥ 3 decks, ≥ 2 graders, ≥ 60 graded cards unique to one engine, at least two decks from a saved All-in or Contending plan |
| Mean grade, cards unique to revision 5 | ≥ revision 2's unique cards (the report's existing comparison) |
| `wrong_for_my_window` rate | lower for revision 5's unique cards |
| `junk_filler`, `overpay` rates | not higher |
| Rebuilding / Tanking decks | no drop in mean grade |

With three labelled users in the whole product (`docs/plans/realtime-trade-engine/
acceptance-eval.md`), this is a read by the operator and two testers, not a statistical test. It is
the same standard revision 4 is being held to.

## 6. Guardrails

Checked in the replay and again as unit tests ([lld §10](lld.md#10-invariants-and-their-tests)).

| Guardrail | Check |
|---|---|
| **Deck size must not shrink** | served deck under revision 5 ≥ 95% of revision 2's at the median request; never under 30 where revision 2 served ≥ 30; a request that would break this is listed, not averaged away |
| **Fairness floor unchanged** | every card present under both revisions has identical package values, fairness score and floor decision; no card under revision 5 sits below the request's floor |
| **Not sure** | identical cards and order on every request |
| **Rebuilding / Tanking** | identical set of cards and terms; with the push-down at 0, identical order |
| **No forecast** | identical cards and order on every request with no usable evidence |
| **Speed** | full-solve CPU within 10% of revision 2; after the join, the page path equals the gated full solve |
| **The push-down removes nothing** | inventory at 0.10 equals inventory at 0 |
| **Pinned and partner-scoped searches** | no conflict recorded |

## 7. Stage 2: seller–buyer matching

Built with stage 1, served only after its own pass, because it changes decks for users who saved no
win-now plan.

- Replay: all five outlooks. Metric for a Rebuilding or Tanking viewer: share of the first 30 where
  the viewer sends a win-now piece to a team it would start for and gets back rebuild pieces,
  cornerstones or picks; and the reverse for a win-now viewer. Bar: both up; Not sure viewers'
  mean support and deck size within 2% of stage 1.
- Calibration: the same round re-run with `season_partner_matching` on in the revision 5 arm, at
  least two Rebuilding or Tanking decks. Bar: mean grade not lower; `they_wont_accept` and
  `wrong_for_their_window` rates not higher.
- Partner outlooks are mostly read from rosters, not saved (median one saved outlook among a
  request's league-mates in the recorded set). The replay reports results split by whether the
  partner's outlook was saved; if the gain is only on saved outlooks, matching is limited to them.

## 8. Production read after rollout

No new client event. Everything needed is already recorded server-side:

| Question | Existing record |
|---|---|
| How often is the forecast usable, and why not? | the `season-signal:` log line per job (new line, counts only) |
| Which engine and what season facts did a served card carry? | the frozen proof on the impression (`generator_version`, `season_signal`) |
| Do win-now users like or pass cards that add lineup points more than cards that do not? | `swipe_decisions` joined to impressions, split by `season_signal.viewer.delta_pts_week` sign |
| Are conflict cards passed more? Sent less? | same join on `season_signal.conflict.fired`; `trade_proposals` for confirmed sends |
| Does "wrong window" fall? | pass reasons (`trade_pass_layer1` / `trade_pass_layer2`, reason `fit_outlook`, `database.py:1846`) before and after, win-now users |
| Did the deck get thinner or slower? | per-job served count and timing lines that already exist |

Read at two weeks and four weeks after stage C through `backend/tools/prod_analytics.py`
(read-only), aggregates only. Stop rule: if win-now users' like rate on served cards falls by more
than a fifth against their own prior four weeks, or any deck is served under 30 cards that had 30
before, set the selector to 0 and investigate.

If a later slice adds a client-visible action (for example tapping the conflict line), that is a
new event and needs a tracking-plan addendum first (`backend/analytics_taxonomy.py`).

## 9. What cannot be measured yet

- **Acceptance.** There are fewer than five counterparty responses on record. Whether the other
  manager says yes more often is unknown and will stay unknown for months.
- **Projection quality.** The weekly projections are Sleeper's, uncalibrated (D-229). The season
  signal inherits that. A forecast that is wrong about who starts makes the label review fail,
  which is the designed catch.
- **Playoff weeks.** Not in the saved forecast. An All-in team's real horizon is longer than the
  one scored.
- **Mid-week news.** The forecast is saved on Tuesday. An injury on Thursday is not in it until the
  next Tuesday; the injury status check still removes a player listed Out.
- **The policy step.** Production runs the personal-market policy live (G-076). Whether its
  ordering changes an owner deck before presentment was not established in this plan; the replay
  must include it or state that it does not act on owner-only decks.
