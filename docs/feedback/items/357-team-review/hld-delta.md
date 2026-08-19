# HLD delta — Team Review

**Date:** 2026-08-19 · **Items:** #357 / #358 / #359 · **Flag:** `trades.team_review` (dark)
**Written as a delta against** [`docs/architecture.md`](../../../architecture.md) and [`living-memory/HLD.md`](../../../../living-memory/HLD.md) — not a rewrite.

---

## Table of contents

- [1. What changes](#1-what-changes)
- [2. The new module and why it is a composer](#2-the-new-module-and-why-it-is-a-composer)
- [3. Data flow](#3-data-flow)
- [4. Decisions, with the alternatives rejected](#4-decisions-with-the-alternatives-rejected)
- [5. The `outlook.odds` ruling](#5-the-outlookodds-ruling)
- [6. What this does NOT change](#6-what-this-does-not-change)
- [7. Risks](#7-risks)

---

## 1. What changes

Three things, and nothing else:

| Layer | Change |
|---|---|
| Backend | **New module `backend/team_review.py`** — a pure composer with no DB access of its own. **New route `GET /api/league/team-review`** in `server.py`, which loads inputs the same way `/api/league/power-rankings` already does and hands them to the composer. |
| Mobile | **New screen `mobile/src/screens/TeamReviewScreen.tsx`**, registered in `TradesStackNav` only. **New entry card** at the top of `TradesScreen`. Both behind `trades.team_review`. |
| Analytics | Four new client events + two extended `source` enums (see [`scope.md` §1](scope.md)). |

No schema change. No new write route — every write goes through the existing
`POST /api/league/preferences` and the existing pin path.

---

## 2. The new module and why it is a composer

`backend/team_review.py` computes nothing new. It calls five things that already
exist and shapes their output into six beats:

| It calls | Which lives at | For |
|---|---|---|
| `power_rankings.compute_power_rankings` | `backend/power_rankings.py:134` | value rank, per-position value split, every team's rank (beats `standing`, `partners`) |
| `power_rankings.optimal_starter_slots` | `backend/power_rankings.py:120` | the weakest starting slot (beat `depth`) |
| `trade_service.infer_team_outlook` | `backend/trade_service.py` | the user's window **and** each league-mate's, from the same pure function (beats `window`, `partners`) |
| `trade_service.analyze_roster_strengths` | `backend/trade_service.py:1826` | `tier_depth` / `position_needs` / `position_surplus` (beat `depth`) |
| `trends_service.compute_consensus_gap` | `backend/trends_service.py:300` | board-vs-market divergence when a league baseline exists (beat `divergence`) |

**The architectural point:** this is the first route in the codebase whose entire
job is to *compose* existing service outputs into a narrative sequence. That is
deliberate, and it is what makes the feature cheap and honest at once — there is
no new model to calibrate, so there is no new way to be wrong. Every number the
screen shows is already shown somewhere else in the app under the same
definition.

**One new convention, to be recorded in `living-memory/LLD.md`** — amended
2026-08-19 after [D-094](../../../../living-memory/DECISIONS.md) put odds back
in scope. The first draft of this convention said a composer route *must not
import a subsystem behind another feature flag*. That is too strong, and the
operator's override proved it: Team Review now deliberately consumes
`outlook.odds`. The rule that actually protects the kill switches is about
**degradation, not isolation**:

> A read-only aggregate route may compose a subsystem that sits behind a
> *different* feature flag, but only behind that flag's own `is_enabled` check,
> and it must remain **fully functional with the flag off**. The dependency is
> allowed to add a field; it is never allowed to remove one. Concretely: with
> `outlook.odds` off — or on a non-Sleeper league, or when the simulator throws
> — `standing.outlook` is simply **absent** and the other five beats are
> byte-identical. Neither flag may break the other's surface.

Consequence: beat `standing` calls `outlook.league_state.build_league_state` for
weekly scores (ingestion, not flag-gated itself) **and**, only when
`is_enabled("outlook.odds")` and the league is Sleeper, `run_outlook` for the
playoff band. Both calls are individually try/except'd: an odds failure costs the
chip, never the beat. **The `trades.team_review` flag remains a clean kill
switch, and `outlook.odds` remains a clean kill switch, because the dependency
is one-directional and additive.**

---

## 3. Data flow

```
TradesHome  ──[entry card, trades.team_review]──▶  TeamReviewScreen
                                                        │
                                    GET /api/league/team-review?basis=…
                                                        │
                                        server.py: _team_review_route
                                     (session load, P2.5 gate, flag gate)
                                                        │
                                          backend/team_review.py  (pure)
                        ┌───────────────┬───────────────┼───────────────┬───────────────┐
                 power_rankings   trade_service    trade_service    trends_service   outlook.*
                  (value, slots)  (infer_outlook)  (roster_strengths) (consensus_gap)   league_state → weekly scores
                                                                                        run_outlook  → playoff BAND,
                                                                                        both guarded, both optional
                                                        │
                                            one JSON payload, six beats
                                                        │
                        beats B2 / B3 write ──▶ POST /api/league/preferences  (existing route)
                        beat  B4 writes     ──▶ existing finder-pin path
                        beat  B5 writes     ──▶ existing opponent_user_id deck scope
                                                        │
                                       B6 ──▶ TradesHome with the deck reshaped
```

The closed loop is the feature. `league_preferences.team_outlook`,
`acquire_positions` and `trade_away_positions` already steer generation through
`trade.outlook_direction`, `trade.lanes`, the G6 R5 need gate and
`_filter_by_trade_intent`. Team Review does not add a new steering mechanism — it
adds the first surface whose *purpose* is to populate the one that exists.

---

## 4. Decisions, with the alternatives rejected

### 4.1 Stepped beats, not a narrated scroll and not a Q&A

**Decision:** six full-screen beats, each *one finding → one plain read → one
action*, with local disposable step state.

**Rejected — narrated scroll.** It is a dashboard with prose on top, which the
operator explicitly ruled out, and it has nowhere to put a decision: a user
scrolls past a preference control exactly as fast as past a chart. The feature's
first stated job (help the user set their trade preferences) would simply not
happen.

**Rejected — conversational Q&A.** A fixed menu of canned questions is a worse
navigation list. An open text box needs either an intent parser or an LLM call
per request, which contradicts the operator's "pull from what already exists
rather than inventing new modeling", adds per-user API cost on a TestFlight
build, and breaks the house precedent that trade-facing copy is deterministic
(`backend/trade_narrative.py` is templates, no LLM, by design).

**Why stepped wins on its merits, not by elimination:** it is the only form in
which the two stated jobs are the *same gesture*. On beat `window`, reading the
strategy verdict and setting `team_outlook` are one interaction. Agreeing with
the analyst *is* configuring the engine.

### 4.2 Reuse the Analyst persona, not the `AnalystGuide` overlay

**Decision:** reuse `mobile/src/components/analyst/` (six mascot poses,
`AnalystAvatar`) and the voice rules in
`docs/plans/onboarding-conversion/guided-avatar-script.md`. Do **not** reuse
`AnalystGuide.tsx` or `useGuide.ts`.

**Rejected — mount Team Review as an `AnalystGuide` tour.** That overlay exists
to *teach a control* by cutting a spotlight hole over it; Team Review *presents
data*, so there is no control to spotlight and a cutout over a chart is theatre.
It also mounts once in `RootNav` above the whole nav tree, whereas a data surface
needs to be a routed screen with real back behavior and a real deep-link target.
And `useGuide` is coupled to the onboarding tour's lifecycle (`dismissTour`,
per-tour persistence, `onboarding.guide_v2`) — borrowing it would tie a Trades
feature's kill switch to an onboarding flag.

### 4.3 The entry point is a card, not a seventh mode chip

**Decision:** a dismissible entry card at the top of `TradesHome` (primary,
and exactly where #359 was filed), plus a persistent entry on the deck's
empty/exhausted state (secondary).

**Rejected — a `TradeFinderModeBar` chip.** On the source's own measurement
(`mobile/src/components/TradeFinderModeBar.tsx:50–58`): the shipped chips
"already measure ≈402pt against ≈361pt of usable width, so the strip is genuinely
scrolled — an **APPENDED** sixth chip would sit off-screen and never be seen."
A sixth (Draft) was already added and had to *lead* the strip for that reason. A
seventh would either be invisible or would displace the operator's 2026-08-06
decision that the draft chip leads. The user who most needs this feature — the
one who does not know what to do — is the least likely to scroll a chip rail to
find it.

**Rejected — a separate tab.** Ruled out by the operator's framing.

### 4.4 One call, not six

**Decision:** the whole review is one `GET`.

**Rejected — per-beat lazy fetch.** Six beats fetching independently is six
loading states inside a flow whose entire value is feeling like one continuous
read. The composer's inputs all come from session state that is already loaded
for the deck, so the marginal cost of computing all six at once is small and
paid before the first beat renders.

**Accepted cost, named:** the payload includes work the user may never scroll to
(a user who abandons at beat 2 paid for beats 3–6). The mitigation is that
`compute_power_rankings` and `analyze_roster_strengths` are the same calls the
Trades tab already makes; the genuinely additive cost is the per-league-mate
`infer_team_outlook` sweep in beat `partners`, which is a pure function over data
already in memory. See [`prd.md` §6](prd.md) for the latency budget.

### 4.5 Forward PPG is cut; lineup movement replaces it

**Decision:** no per-player points projection enters the product. #357's "what
does adding this player do to my team" is answered by
`starter_impact.slots[].before/after` with tier and positional rank
(`trade.position_impact`, already ON).

**Rejected — source Sleeper's projections endpoint.** Undocumented, no commercial
guarantee, can be deprecated without notice. If the operator wants it, it is a
new external dependency on a gray-ToS endpoint and belongs in its own scoped
project with a `DEPENDENCIES.md` entry — not smuggled into a UI feature.

**Rejected — derive a team-level PPG proxy from roster value.** This proxy
already exists: it is `RosterValueStrength`'s
`mu = MEAN_POINTS + POINTS_PER_VALUE_SD · z(lineup_value)`. Its own source file
calls it "a documented heuristic, NOT an empirically fit model", and the
calibration report records its three constants as un-fit against measured
values (`outlook_mean_points = 110` against a pooled empirical 130.6). Rendering
that as "+6 PPG" would be inventing a number with a citation attached, which is
worse than inventing one plainly.

**Why the replacement is better, not merely safer:** "your TE slot goes from TE31
to TE2 and your RB slot from RB3 to RB19" is more specific than a single scalar,
and it is in units the app already defends everywhere else.

---

## 5. The `outlook.odds` ruling — REVERSED BY THE OPERATOR

> **2026-08-19, operator, verbatim: *"Outlook odds should be visible. Forward PPG
> cut. I waive maestro"*.** This section originally recommended keeping the flag
> dark. That recommendation was overruled. The flag is now **`true`** in
> `config/features.json`; the reversal is recorded as
> [D-094](../../../../living-memory/DECISIONS.md), which supersedes D-093.

**What the operator's call changes.** `outlook.odds` is lit, which makes live the
#169 layer that has been built-but-dark since `f27c0f5` — the D-025 collapsed
one-line "your outlook" strip on League Summary, the full section behind it, and
`GET /api/league/outlook`. Team Review's `standing` beat gains a playoff **band
chip**. Because that seam was designed in from the start, lighting cost this
feature one payload field and one chip, not a redesign.

**Two of my four original objections were weaker than I stated, and that is worth
recording rather than quietly dropping:**

1. **The platform objection was already solved in shipped code.** I wrote an "L2"
   criterion requiring an explicit non-Sleeper state instead of a 501.
   `LeagueSummaryScreen` already has one: the `outlookSupported` selector gates
   the query on the league's platform and resolves *unknown* to supported, so
   ESPN/MFL leagues render **no section at all** — honest absence, no error, no
   501. The criterion was met before I wrote it.
2. **The preseason objection was about first impressions, not validity.** The
   calibration explicitly supports **bands from week 0** — preseason skill
   excludes zero (+21.3 %, CI [+2.9, +39.1]) — and withholds only finer
   granularity. My "+2.9 % lower bound" figure was the argument against a
   *percentage*, and I was reusing it against a *band*, which the same document
   endorses.

**What does NOT change, and could not be changed by any preference:**

| Rule | Status after the override |
|---|---|
| `title_pct` unrenderable at any week, in any form, banded or numeric | **Unchanged and now mechanically enforced.** Not a calibration judgement — an absence of demonstrated skill (pooled +4.2 %, 90 % CI [−13.1 %, +20.0 %]; 3 of 6 backtested league-seasons worse than climatology; 8 predictions above 0.4 containing one champion). Team Review does not even serialize it. |
| `playoff_pct` renders only as the three-band chip | **Unchanged.** Thresholds 0.65 / 0.35, semantic pos/warn/neg, label always beside the color. |
| `OUTLOOK_WEEK6_PERCENT_ENABLED` | **Still `false`.** "Odds should be visible" is satisfied by the band chip; a bare percentage is a separate risk call on pooled, non-week-stratified calibration and is left for an explicit decision. |
| Every odds figure labelled a projection | **Unchanged.** "Projected · preseason · beta" ribbon travels with the chip. |

**Today's live posture** (`completed_weeks == 0`): Sleeper leagues only,
`meta.beta` true → **bands and row order, no win-loss numbers**, ribbon attached.

**Evidence, after the Maestro waiver.** The operator waived the Maestro flow this
lighting used to owe; it was already void under D-056. It is replaced by
**`mobile/tests/check-outlook-bands.js`** — a dependency-free structural guard
pinning the two thresholds, the band→semantic-color map, a label per band,
top-down bucketing, that no client reads `title_pct`, and that the week-6
percentage switch is off. **All six assertions were proven to fail under
deliberate sabotage** before the guard was accepted (the 2026-08-10 lesson), and
it gates CI automatically — `ci.yml`'s `mobile-typecheck` globs `tests/check-*.js`.

**Two live risks are accepted rather than solved, and should be watched:**

- A preseason band can be confidently wrong for an individual league. Two of six
  backtested league-seasons lose to climatology outright, one with an ordering
  correlation of **+0.022** — a user in such a league sees ordered, wrong bands
  all season. A band is immune to being *precisely* wrong, not to being wrong.
- **IDP and kicker leagues price a minority of their starting slots** — 7 of 15
  in the operator's own FFV3 league — so their bands are an offensive-core
  estimate. `meta.priced_slot_coverage` exists to caption exactly this and **has
  never been rendered by any client**. Team Review's `standing` beat is
  specified as its first consumer ([`lld-delta.md` §8](lld-delta.md)); League
  Summary still shows nothing.

## 6. What this does NOT change

Stated explicitly because a feature this broad invites scope drift:

- **The trade engine.** No generation path, scoring function, gate or knob
  changes. Team Review writes the same preference fields a user can already set
  by hand in Trade DNA.
- **`league_preferences` semantics.** Same table, same route, same fields. The
  only new thing is a fourth `source` value on two analytics receipts.
- **The deck's presentation.** No change to `TradeCard`, the disposition pair,
  `TradeValueBar`, or D-025's card-ordering rule.
- **`outlook.odds`, `trade_gen.v2`, `trades.presentation_v2`.** All stay exactly
  as they are.

---

## 7. Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| The composer drifts into a second source of truth — someone "improves" a number here and it disagrees with League Summary | Medium | `team_review.py` is a pure composer with no arithmetic of its own; the structural suite pins that it imports the shared functions rather than reimplementing them. Any new math is a review-blocking change. |
| Beat `partners` is O(members) `infer_team_outlook` calls and could be slow on a 14-team league | Low | Pure function over in-memory data; measure in the latency budget ([`prd.md` §6](prd.md)) and cap at the league's member count, which is bounded by the platform. |
| The entry card becomes banner blindness and nobody opens it | Medium | `team_review_opened` by `source` is the measurement; the deck-empty entry is the second surface precisely because it catches the high-intent moment. If the card's open rate is flat after two weeks lit, the answer is placement, not more copy. |
| A user sets an outlook they do not mean and their deck gets worse | Low | Every write is reversible from Trade DNA, and beat B6 says so on screen. B2 offers `not_sure` as a first-class option rather than forcing a call. |
| ESPN/MFL users read the degraded PPG card as a bug | Medium | The card names the platform reason in plain words rather than showing an empty state. Called out as waiver 3 in [`scope.md` §6](scope.md) for an operator yes. |
