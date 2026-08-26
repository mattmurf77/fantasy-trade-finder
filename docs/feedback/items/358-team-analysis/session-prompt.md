# #358 — Team Review / Team Analysis: session kickoff prompt

> **What this file is:** a self-contained prompt for a *separate* session to take
> feedback #358 (+#357, #359) forward from scratch. Nothing has been built. No scope
> block exists yet. Copy the block below into a new session.
>
> Filed 2026-08-19 by the operator after triaging jonbonjourvi's 2026-08-19 feedback batch.

---

## The prompt

```
Build the plan for feedback #358 — an "Team Review / Team Analysis" experience in the
Fantasy Trade Finder mobile app. This is a meaningful new feature, part of the
find-a-trade experience, and it is worth its own session. Do not treat it as a polish
item.

WHAT THE USER ASKED FOR (tester jonbonjourvi, 2026-08-19, v1.15.0 — three linked items):

  #358 (TradeCalculator, idea): "I know it's slightly baked in already but basically
  something that's inherently obvious like an AI GM… you're sitting 6th in value and
  11th in PPG this year. We recommend a 1 year tank and best ways to do that are sell
  players X,Y,Z…. Here's good targets (picks from other bad teams / players who could
  gain value). Or like you're missing depth, consider tiering down from Loveland and
  Bijan if you want to compete this year. Also… based on your rankings you're higher on
  X and lower on Y to consensus. Target these in trades."

  #359 (TradesHome, idea): "basically an idiot version of wtf do I do next with this team"

  #357 (TradeCalculator, idea): "In all trade pages I would still love to see more data
  on what adding this player to your team does. Eg here's 6 extra PPG this year which
  raises your playoff odds to X and championship odds to Y…. Or inversely raises your
  odds at first pick overall"

OPERATOR FRAMING (2026-08-19):
  - Ship it as a "Team Review" / "Team Analysis" button inside the find-a-trade
    experience — not a separate tab, not a settings page.
  - Drive it as an ANALYST-GUIDED experience: a walked-through read of the team rather
    than a static dashboard.
  - It should pull from valuations and features that ALREADY EXIST rather than
    inventing new modeling.
  - Its job is twofold: (a) help the user SET THEIR TRADE PREFERENCES, and (b) more
    generally determine team strategy. Think of it as an idea-generation service for
    "what do I do next".

WHAT ALREADY EXISTS THAT THIS SHOULD PULL FROM (verified in-repo 2026-08-19, cite
file:line yourself before relying on any of it — do not take this list on faith):

  - Playoff-odds engine: backend/outlook/ (5 phases, Monte-Carlo, config-selected
    strength provider), served by GET /api/league/outlook (backend/server.py:20377).
    DARK behind the `outlook.odds` flag — 404s while off. Preseason payloads carry
    meta.is_preseason; meta.beta is a separate confidence signal.
    * playoff_pct is renderable ONLY as a three-band chip, never a raw number
      (cross-client invariant, docs/cross-client-invariants.md § "Playoff outlook bands").
    * title_pct IS SERVED BUT UNRENDERABLE — calibration found no demonstrated skill
      (skill CI spans zero; 3 of 6 backtested league-seasons do worse than a constant).
      See mobile/src/api/league.ts:731-737 and the #169 calibration report. Jon's
      "championship odds to Y" ask CANNOT be honored as stated. Design around it.
  - Roster value + power rankings: GET /api/league/power-rankings, per-team and
    per-position values; LeagueSummaryScreen already renders the stacked bar chart.
  - Roster needs/surplus: `position_needs` / `position_surplus` on
    GET /api/league/preferences — already drives the dashed "need"/"deep" chips in
    Trade DNA.
  - Trade preferences: `acquire_positions` / `trade_away_positions` on
    league_preferences (backend/database.py:689-690) — the Chasing/Shopping surface
    this feature is supposed to help the user SET.
  - Starter/lineup impact: `starter_impact.slots[].before/after` on
    POST /api/trade/evaluate (backend/server.py:1127 `_starter_impact`), incl. tier +
    positional rank movement behind `trade.position_impact` (already ON).
  - Board-vs-consensus divergence: the user's personal Elo board vs consensus values —
    the raw material for Jon's "you're higher on X, lower on Y, target these".
  - Trade generation: trade_service.py (v2 scoring) / trade_optimizer.py (v3 package
    search), and trade_narrative.py for deterministic, non-LLM copy.

KNOWN GAP — DO NOT PAPER OVER IT:
  There is NO per-player weekly points projection anywhere in the backend. Jon's
  "here's 6 extra PPG this year" has no data source today. The outlook strength
  providers model TEAM weekly scoring (roster_value preseason, trailing_scores in
  season — backend/outlook/strength.py), not player PPG. Either source it, derive a
  defensible team-level proxy, or explicitly cut the PPG claim from scope. Do not
  invent a number.

WHAT I WANT FROM THIS SESSION:
  1. Read living-memory/DECISIONS.md and the #169 calibration work before designing —
     the odds honesty rules are hard-won and non-negotiable.
  2. Decide and justify what "analyst-guided" means concretely (a stepped flow? a
     narrated scroll? a Q&A?) with a mockup lab under mockups/ per mockups/CLAUDE.md.
  3. A full feature scope block (docs/templates/feature-scope.md) — this crosses the
     CLAUDE.md bright line (new routes, likely new flag, new analytics events), so it
     is NOT express lane.
  4. Full-path planning per .claude/skills/feedback references/plan-phase.md: HLD delta
     + LLD delta + PRD pinning exact API contracts.
  5. An explicit call on whether `outlook.odds` gets lit as part of this, and on what
     evidence. It has been dark since 2026-07-23.

CONSTRAINTS:
  - Branch from a freshly fetched origin/main.
  - Chalkline design system only (docs/design/design-system.md) — no emoji as icons,
    no gradients, ice for actions, flare for informational highlights only.
  - Every odds figure is a projection and must be labelled as one. Never show a bare
    authoritative percentage.
  - D-056 retired Maestro and the simulator: evidence is structural checks + unit tests
    + a written code-walk proof + a concrete manual TestFlight checklist.
```

---

## Why this is its own session

It is a new user-facing surface that composes at least four existing subsystems
(outlook odds, power rankings, roster needs, board-vs-consensus divergence), it needs
a design language for guided analysis that FTF does not have yet, and it collides with
a live honesty constraint (title odds are unrenderable) that has to be designed around
rather than ignored. Folding it into a polish batch would produce a thin PRD and two
build agents guessing at different contracts.

## Related

- **#357** — the per-trade version of the same want ("what does adding this player do
  to my team"). Same data sources; likely the same feature's trade-card slice.
- **#359** — the plain-language restatement ("idiot version of wtf do I do next").
  Treat as the success criterion, not a separate item.
- **#360/#361** — the "Avoiding" positions filter. Adjacent: #358 is supposed to help
  the user *set* preferences, and Avoiding would be one of the preferences it sets.
