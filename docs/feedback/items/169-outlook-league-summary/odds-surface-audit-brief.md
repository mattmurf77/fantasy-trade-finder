# Brief: odds & projected-standings surface audit (design orchestrator)

**Written 2026-08-09 for a design-orchestrator agent. Not yet dispatched.**
Paste the section below the rule as the orchestrator's prompt.

---

You are a **design orchestrator** for Fantasy Trade Finder. Your job is to audit **every
surface in the app where playoff odds and/or projected standings should appear**, decide
where they genuinely earn their place, and produce mockups for the ones that do. You
coordinate sub-agents; you do not write product code. Nothing you produce ships — the
operator reviews your audit and picks.

FIRST: `git fetch origin && git reset --hard origin/main`. **Mockups and docs only** —
zero changes to `mobile/`, `backend/`, `web/`, `extension/`.

## What the engine actually produces

`backend/outlook/` (flag `outlook.odds`, currently **dark**) runs a Monte-Carlo season
simulation and serializes, per team: **playoff odds**, **title odds**, **projected wins**,
and seeding/bye information. Two distinct products come out of one engine, and the audit
must treat them separately:

- **Playoff odds** — a probability ("68% to make playoffs"). Probabilistic, needs framing.
- **Projected standings** — expected final W-L and seed order. Reads like a table, not a
  forecast, and is far more legible to non-technical users. **No surface currently shows
  this at all**, and it may be the more valuable of the two.

Read before anything else: [`odds-pipeline-lld.md`](odds-pipeline-lld.md),
[`calibration-report-2026-08-09.md`](calibration-report-2026-08-09.md),
[`status.md`](status.md), [`phase-2-plan.md`](phase-2-plan.md), and the existing mockups in
`mockups/outlook-odds/` (`outlook-card.html`, `league-summary.html`, `value-bar.html`,
`feasibility.md`).

## Constraints that shape every design decision — these are binding

1. **Playoff odds are validated; title odds are NOT.** Backtest over 6 real league-seasons:
   playoff Brier 0.1113, **+55% skill** over guessing (CI excludes zero). Title odds:
   6 champion events, CI spans zero, **worse than a coin flip at week 3**. The July-approved
   `outlook-card.html` shows playoff% and title% as a paired set — that design is no longer
   shippable as drawn. Either drop title odds and rebalance the layout, or propose an
   honest treatment that visibly distinguishes a validated number from an unvalidated one.
   Do not quietly keep both at equal visual weight.
2. **Show BANDS, not percentages — this is the load-bearing design constraint.**
   Preseason odds were backtested 2026-08-09
   ([`dated-values-revalidation-2026-08-09.md`](dated-values-revalidation-2026-08-09.md))
   and have **real but marginal skill**: playoff Brier 0.1959, +21.6% over climatology,
   but the CI's lower bound is only +4.1%, the model is **over-confident at the extremes**
   (95% predictions realize 75%; 4% predictions realize 18%), and it **loses to climatology
   in 2 of 6 league-seasons**. Shrinking the numbers recovers almost nothing (2.2% of
   Brier), so this cannot be tuned into a trustworthy percentage. The recommended
   presentation is a **band — "likely / toss-up / unlikely"** — which is both what the
   statistics support and what the operator's design tenets (#205: simple beats complex,
   non-technical users first) independently argue for. **A bold "68%" is not shippable at
   any point in the season on current evidence.** If you propose exposing a raw percentage
   anywhere, you must justify it against these numbers.
3. **The week-3 gate is now questionable — re-derive it, don't inherit it.** Preseason odds
   scored 0.1959 vs the week-3 in-season model's 0.1972: **statistically indistinguishable**.
   So `completed_weeks >= 3` buys no measured accuracy over showing preseason bands from
   day one; the honest case for a gate is **weeks 6+**, where the in-season model pulls
   clearly ahead (0.120 at wk 6 → 0.055 at wk 12). Your design should decide, with reasons:
   bands from week 0 with the label changing as confidence grows, or nothing until the
   numbers earn their place. This is a product judgment the audit should make a
   recommendation on.
4. **The "beta" label must persist past preseason.** Today `meta.beta` is an alias of
   `is_preseason`, so the word disappears at week 1 while the model is still uncalibrated.
   Propose the honest labeling lifecycle.
5. **Chalkline design system** (`docs/design/design-system.md`, `components.md`, live
   reference `web/style-guide.html`). The approved odds visual language is the amber
   "Projected" treatment in `outlook-card.html` — flare accent is for informational
   highlights, which is exactly this. No emoji, no gradients.
6. **Known engine bug, unfixed:** BUG-1 (G-024) — median-match leagues ignored, producing
   nonsense projected wins (22 in a 14-week season). **Projected-standings designs must
   assume this is fixed**, but flag anywhere your design would expose the bug loudly if it
   shipped first. Note the revalidation found the odds are also materially worse on the
   median-match league (Brier 0.2298 vs 0.1789 on head-to-head leagues) — barely better than
   guessing. Whatever you design must degrade honestly for league formats the model handles
   poorly, not present all leagues with equal confidence.

## The places INITIALLY PLANNED (start here, then go beyond)

These were scoped in July, before calibration. Treat them as the inherited baseline to
validate or revise — not as the answer.

| Surface | What was planned | Current state |
|---|---|---|
| **`LeagueSummaryScreen`** (League tab root) | The primary home: per-team playoff%/title% in the ranked list, a beta ribbon when `meta.beta`, a source caption from `meta.source`. Specced in the LLD's UI section against `mockups/outlook-odds/league-summary.html`. | **Built and parked** behind `outlook.odds`. Layer compiles into the current screen; contract reconciled 2026-08-09. The screen has since gained a bar chart, position filter, drill-in roster, tier labels, and the operator-only aggregate "≈X firsts" labels — the July design predates all of it. |
| **Trade suggestion card** (`mockups/outlook-odds/outlook-card.html`) | The "Season outlook" card — odds attached to a suggested trade, i.e. "this trade moves your odds." | **Mockup only, never built.** This is also the origin of feedback #169's ask ("this trade makes your playoff/champion odds in 2026/27/28…"). Note the operator later narrowed #169 to position-specific improvements first — see [`169-position-impact/status.md`](../169-position-impact/status.md) — so trade-level odds are the *next* step, not a closed one. |

Everything else is unexplored. **That is the real work of this audit.**

## Your audit task

Enumerate every surface in the app, then judge each one. Screens live in
`mobile/src/screens/` (read `mobile/src/screens/CLAUDE.md` for the map — LeagueScreen,
TradesScreen, MatchesScreen, TradeCalculatorScreen, FreeAgentsScreen, DraftRoomScreen,
RankHomeScreen, SettingsScreen, and others), plus `web/` and `extension/` as separate
clients, plus push notifications (`backend/` notification ticks) as a non-screen surface.

For **each** surface produce a verdict with reasoning:

- **Belongs** — odds and/or projected standings genuinely improve the surface. Say which of
  the two, what the user learns, and what they'd do differently because of it.
- **Belongs later** — right idea, blocked on something (name the blocker: title-odds
  validation, trade-delta simulation, cross-client parity, BUG-1).
- **Doesn't belong** — say why. A surface that would merely *decorate* with a percentage is
  a "doesn't belong." **Be willing to return a short list.** The operator's stated design
  tenets (feedback #205) are: simple beats complex; too much information is worse than none;
  every experience must work for non-technical users. A percentage sprinkled on six screens
  violates all three. Rank ruthlessly.

Specifically interrogate these questions, which nobody has answered yet:
- **Where do projected standings live?** Nothing shows them today. Is it a tab on the League
  screen, a toggle on the existing ranked list (current standings ↔ projected finish), or its
  own view? This is the highest-upside unexplored question in the audit.
- **Does a trade need to move odds to be worth showing?** The trade card's whole promise is
  "this changes your season." Running the sim twice (with and without the trade) is a real
  backend cost — is the payoff worth it, and at which surface: deck card, trade summary, or
  the calculator?
- **Do odds belong on a notification?** ("Your playoff odds moved 12 points this week.")
  Compelling or creepy? Argue it.
- **What about non-Sleeper leagues?** The engine needs schedule + scoring history. ESPN/MFL
  coverage may differ — check `backend/outlook/league_state.py` and the integration docs, and
  design the honest unavailable state rather than assuming parity.

## How to run it

Spin **parallel sub-agents scoped by surface area** (suggested: League-tab surfaces; trade
surfaces; peripheral surfaces incl. free agents/draft/notifications; cross-client web +
extension). Each returns a verdict table with reasoning grounded in the real shipped code —
they must read the actual screens, not imagine them. Then you reconcile into one ranked
recommendation and commission mockups **only for the surfaces that made the cut**.

Where two sub-agents disagree about a surface, re-verify against the code yourself and
record the resolution — the dual-lens reconciliation in
[`dynastydaddy-sim-reference.md`](dynastydaddy-sim-reference.md) is the house pattern.

## Deliverables

1. `docs/feedback/items/169-outlook-league-summary/odds-surface-audit.md` — the full
   enumeration with per-surface verdicts, the four interrogation answers, a ranked build
   order, and open questions for the operator.
2. `mockups/outlook-odds/` additions — new/revised frames at 393×852pt, Chalkline tokens
   only, grounded in the CURRENT shipped screens (not the July versions). Minimum:
   a revised league-summary treatment reflecting today's screen, a playoff-only card that
   doesn't look amputated, the pre-week-3 state, and whatever projected-standings surface
   you recommend. Each frame carries its rationale and tradeoff, per the house lab
   convention — see `mockups/polish-lab-2026-08/` for structure.
3. Update `mockups/outlook-odds/index.html` so the lab is navigable.

Commit `"outlook: odds & projected-standings surface audit + revised mockups"`. Do not merge
or push. Report: the ranked verdict list, what you rejected and why, and the single
recommendation you'd ship first.
