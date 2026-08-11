# Feature Scope — #169 frame E (outlook strip) + card frame C (disposition move)

**Date:** 2026-08-11
**Entry point:** feedback #169 (operator frame decisions, third pass — see
[`operator-frame-decisions-2026-08-11.md`](operator-frame-decisions-2026-08-11.md))
**Builder:** primary session + two build subagents (W1 / W2+W3 per
[`plan-e-and-card-2026-08-11.md`](plan-e-and-card-2026-08-11.md))
**Operator sign-off on waivers:** obtained 2026-08-11 — analytics waiver
**rejected** (event specced in §1a instead); frame-E Maestro waiver (§3)
**approved**

---

## 1. Analytics scope

- [x] **(a) New events specced** — analytics waiver was **rejected by the
  operator 2026-08-11** ("spec the event now"); the event ships wired in this
  build even though the flag is dark:

  | Event | Properties | Fires when | Client |
  |---|---|---|---|
  | `outlook_strip_toggled` | `league_id: string`, `expanded: boolean` (the resulting state) | user taps the outlook strip and the toggle applies (behind `outlook.odds`; `track()` is additionally a no-op unless `analytics.client_events` is on) | mobile (`api/events.ts` `track()`, screen `LeagueSummary` per the screen-string convention of existing calls) |

  → follow-through: `backend/analytics_taxonomy.py` `ALLOWED_CLIENT_EVENTS`
  gains the name (NOT `FUNNEL_CRITICAL`); tracking-plan addendum in
  `docs/business/analytics/2026-07-17-tracking-plan-v2.md` (the taxonomy
  docstring requires the addendum for new client events);
  `docs/data-dictionary.md` n/a (stored in the existing events tables, no
  schema change). Zero event volume until `outlook.odds` lights — that is
  the point: the instrumentation exists from day one of the strip
  (NULL-`platform`-incident lesson).
  - **Card disposition move:** no new events — the buttons keep the same
    `advance()` handlers, so every existing deck outcome/event fires exactly
    as before.

## 2. Schema & flag scope

- New/changed tables or columns: **none**
- New/changed feature flags: **none** — `outlook.odds` untouched (`false`),
  no new flags; the card reorder ships unflagged (PRD § Launch posture)
- New env vars / `model_config` keys: **none**
- Rollback lever: `git revert` (client-only, no state to unwind)

## 3. Test scope (mobile test platform)

- [x] **Extended flow:** `mobile/.maestro/flows/smoke/06-trades-deck.yaml` —
  **positional** delta (a plain `visible:` assert would pass identically
  before/after — law 2): assert both buttons at `visibilityPercentage: 100`
  with **no scroll step** (fails on the old below-deck layout), keep the
  like-tap, add a pass-tap on the next card (LLD §3.2)
- [x] **Extended flow (capture):** `mobile/.maestro/capture/onboarding-tour@fresh.yaml`
  — its three disposition-tap blocks anchor on `scrollUntilVisible … DOWN`
  derived from the old row position; re-derive all three on-sim (LLD §3.2)
- [x] **WAIVED (frame E only) because:** `outlook.odds` is dark and has no
  seeded harness fixture — a strip flow would fail on every hermetic run; a
  strip-absence flow passes identically before/after, testing nothing.
  Identical grounds to the signed 2026-08-10 waiver
  ([`status-outlook-v2-build-2026-08-10.md`](status-outlook-v2-build-2026-08-10.md)
  § Maestro waiver). **The lighting-time flow now owes the strip states too**
  (collapsed default → expand → persistence), on top of the section states
  already owed.
- `testID`s added/renamed: `league-summary.odds.strip` (new — its band chip
  deliberately carries no id, LLD §1.4); `trades.pass-btn`,
  `trades.like-btn` (moved, unrenamed). `testid-lint.sh` must pass; note it
  only checks flow-referenced ids, so the strip id's first real check is the
  lighting-time flow (LLD §4).
- **Capture delta (4 screens, per `screens/manifest.json` source-hash
  mapping):** `trades` (real visual change), `matches`, `sheets-trade-dna`,
  `league-summary` (all three: hash-stale, expect no visual diff — the
  no-diff captures double as regression evidence). Then
  `screen-freshness.sh` must run clean.
- Smoke-suite impact: `06-trades-deck` (extended, positional) and
  `05-trades-render` — green in the Tier-1 run. `onboarding-tour@fresh` is a
  **capture** flow, not smoke — it runs in the capture pass with re-derived
  anchors.
- Backend: one file touched — `backend/analytics_taxonomy.py` gains
  `outlook_strip_toggled` in `ALLOWED_CLIENT_EVENTS` (§1a). Extend the
  existing taxonomy test with an allowlist assertion for the new name and
  sabotage-prove it (remove the entry → test fails → restore). Full pytest
  suite must stay green in CI. New mobile static check
  `mobile/tests/check-card-disposition.js`, sabotage-proven (LLD §3.1).

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a | no route added/renamed/removed/changed |
| `living-memory/LLD.md` | n/a | no schema/route/invariant *convention* shifts — component-level moves only; item LLD covers the detail |
| `docs/architecture.md` | n/a | no module/data-flow change (HLD delta § verdict) |
| `living-memory/HLD.md` | n/a | same |
| `docs/cross-client-invariants.md` | **updated at ship** | NEW section "Deck disposition (Pass / Like)" — vocabulary (incl. VoiceOver strings, which W2 renames from "Accept this trade"), testIDs, card ordering rule (buttons beneath tiles; future outlook block below `TradeValueBar`). Own section, not under § Playoff outlook bands (that's a playoff-odds encoding family) |
| `docs/glossary.md` | n/a | no new domain term |
| ADR or `DECISIONS.md` entry | **updated at ship** | DECISIONS: strip-collapsed-by-default per league/user; card reorder unflagged; week-6+ card odds deferred by operator; a11y-label rename to match Pass/Like |
| `mobile/src/screens/CLAUDE.md` | **updated at ship** | LeagueSummaryScreen row gains the strip; TradesScreen row loses the below-deck disposition row |
| `mobile/src/components/CLAUDE.md` | **updated at ship** | TradeCard's swipe-deck prop list gains `disposition` |
| `living-memory/NEXT.md` | **already corrected this session** (item 5 staleness fixed pre-build); verify at ship it carries no forward-dated build claims |

## 5. Ship gate declaration

- **Simulator-gate tier: 1** (mobile screen change — TradeCard/TradesScreen
  are live UI): full smoke suite (11 flows) + extended `06-trades-deck` +
  re-captures per §3. The dark frame E adds no tier on its own; the card
  change sets the tier.
- Evidence: TEST_LEDGER entry + `qa/sim-runs/last-sim-run.json` after the run
- Operator deviation from the matrix: none requested
