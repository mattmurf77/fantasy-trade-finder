# Org chart — charters and starting file map

The file map below is a **starting map** inferred from module and screen names. The
first inventory worker in a programme confirms it against `origin/main` and the
scribe records any correction in the programme record. Files not listed belong to
`head-eng` until it allocates them.

## Department heads

All three report to the coordinator and cover any of their own boxes left
unstaffed.

### `head-product` — Head of Product
- **Charter:** `/pm-technical`.
- **Owns:** the cross-area priority order; the PRD and scope-block standard; which
  area gets which work; promotion of items into `living-memory/NEXT.md` (through the
  scribe).
- **Manages:** the seven `<area>-pm` leads, `growth-pm`, `analytics-lead`,
  `ux-lead`, `design-lead`.
- **Workers it may use directly:** `pm-competitor` (teardowns, feature-gap matrix).
- **Accepts on:** every scope-block section answered or waived with a reason; the PRD
  pins the API contracts the eng side will build against; design and UX reviews
  attached or waived; a `models-lead` review (through `head-bizops`) attached or
  waived when model behavior changes.

### `head-eng` — Head of Eng
- **Charter:** `/eng-architect`.
- **Owns:** cross-cutting design and ADRs (`docs/adr/`); the per-wave file-ownership
  map across areas; cross-area files (`backend/server.py`, `database.py`,
  `data_loader.py`, `feature_flags.py`, `entitlements.py`, `mobile/src/navigation/`,
  shared mobile components, the `web/` shell); the contract docs
  (`docs/api-reference.md`, `data-dictionary.md`, `cross-client-invariants.md`,
  `architecture.md`, `config-reference.md`) — one named owner per wave.
- **Manages:** the seven `<area>-eng` leads, `models-eng`, `release-lead`.
- **Workers it may use directly:** `eng-security` (audits), `eng-architect` design
  passes.
- **Accepts on:** diffs from different areas agree on shared contracts; schema and
  route changes have their doc rows; no two workers touched the same file in a wave.

### `head-bizops` — Head of Business Operations
- **Charter:** no repo skill. Grounds in `docs/business/context.md` (business state,
  funnel, seasonality) and the other department heads' reports.
- **Owns:** the business side of priorities — model strategy, marketing, costs and
  P&L, support posture; `docs/business/finance/`, `docs/business/marketing/`, and
  `docs/business/ops/` except the release log (that is `release-lead`'s).
- **Manages:** `models-lead`, `marketing-lead`.
- **Workers it may use directly:** `fin-pnl` (monthly P&L, unit economics),
  `ops-support` (tester and user replies, support macros — every outbound reply
  needs the operator).
- **Hands off:** `models-lead`'s specs to `head-eng` for `models-eng`; marketing
  needs that require product changes to `head-product` for `growth-pm`; experiment
  needs to `head-product` for `analytics-lead`.
- **Accepts on:** model specs carry measurable quality bars and an eval plan
  `models-eng` can run; numbers cite their source; deliverables end with
  **Decisions needed** + **Handoffs**.

## Area leads

Every product lead is chartered by the skill listed, scoped to its area; every eng
lead by `/eng-architect` scoped to its area (it designs and allocates, it does not
implement). Eng workers are `eng-backend`, `eng-mobile`, `eng-web` unless noted.

| Area | Product lead (charter) | Eng lead owns — starting map |
|---|---|---|
| **Rankings** | `rankings-pm` (`/pm-technical`) | `rankings-eng`: `smart_matchup_generator.py`, `rankings_import.py`, `taste_service.py`, `trends_service.py`, `usage_trends.py`, `usage_trends_refresh.py`, `blind_grading.py`; screens `RankHome`, `Rank`, `QuickRank`, `QuickSetTiers`, `Tiers`, `ManualRanks`, `RookieRanks`, `Trends`, `UsageTrends`, `Calibration`; `web/positional-tiers.html`, `ranking-method.html` |
| **Trades** | `trades-pm` (`/pm-pfo` — suggestion quality is the core loop) | `trades-eng`: `trade_narrative.py`, `trade_block_service.py`, `prepared_trade_*.py`, `trade_bilateral_presentment.py`, `small_trade_presentment.py`, `suggestion_telemetry.py`, `team_review.py`, `overhaul_api.py`, `overhaul_service.py`, `overhaul_store.py`; screens `TradeFinderHub`, `Trades`, `TodaysTrade`, `TradeBrowseAll`, `ShopAsset`, `TradeCalculator`, `Matches`, `TeamReview`, the eight `Overhaul*` team-overhaul steps |
| **League** | `league-pm` (`/pm-technical`) | `league-eng`: `power_rankings.py`, `free_agent_service.py`, `roster_history.py`, `win_now_api.py`, `win_now_service.py`, `win_now_store.py`; screens `League`, `LeagueSummary`, `Standings`, `WinNow`, `Portfolio`, `FreeAgents`; `web/league-rankings.html` |
| **Draft** | `draft-pm` (`/pm-technical`) | `draft-eng`: `draft_board_service.py`, `draft_status.py`, `mock_draft_service.py`, `pick_slots.py`; screens `DraftRoom`, `MockDraft`, `PickAnchor`, `PickAssignment`, `RecordPicks` |
| **Onboarding & accounts** | `onboarding-pm` (`/pm-pfo` — onboarding friction, time to value) | `onboarding-eng`: `accounts.py`, `profile_session_init.py`, `user_data_lifecycle.py`; screens `SignIn`, `LeaguePicker`, `LeagueJoin`, `Settings` and the `settings/` subtree, `Profile`; `web/index.html` landing, `profile.html` |
| **Engagement** | `engagement-pm` (`/pm-retention`) | `engagement-eng`: notification and inbox code, `receipts_service.py`, `wrapped_collector.py`, `og_image.py`, share and invite routes; screens `Home` (the Home hub), `Receipts`, `FeedbackInbox` |
| **Platforms** | `platforms-pm` (`/pm-partnerships`) | `platforms-eng` (workers add `eng-integrations`): `sleeper_write.py`, `sleeper_trades_service.py`, `sleeper_roster.py`, `espn_service.py`, `espn_write.py`, `mfl_service.py`, `mfl_write.py`, `fleaflicker_service.py`; screens `SleeperConnect`, `EspnConnect`; `extension/` |

Mobile screens live in `mobile/src/screens/<Name>Screen.tsx`; backend modules in
`backend/`. Routes for every area live in the shared `backend/server.py` — an area
eng lead asks `head-eng` for the route block it needs each wave.

**Seams that need care**
- *Connect flows:* `platforms-eng` owns the connect screens; `onboarding-pm` owns the
  journey they sit in; `ux-lead` reviews the flow end to end.
- *Engines:* area eng leads own the services and screens that call the engines;
  `models-eng` owns the engines themselves.
- *Win Now and team overhaul:* the screens and APIs belong to League and Trades;
  the optimizers and simulators behind them are `models-eng`'s.
- *Send-to-league:* the trade card is `trades-eng`'s; the write call to the platform
  is `platforms-eng`'s.
- *Share and invites:* `growth-pm` decides the viral-loop mechanics, `engagement-pm`
  owns the retention surfaces around them, `engagement-eng` builds both. Growth work
  on the landing page or sign-in goes to `onboarding-eng`.
- *Models:* strategy is `models-lead`'s (Business Operations), code is
  `models-eng`'s (Eng), and the product surfaces showing model output belong to the
  area leads (Product). A model change touches all three departments.

## Function leads under `head-product`

### `growth-pm`
- **Charter:** `/pm-growth`. **Workers:** `an-market` (sizing), `pm-competitor`
  (competitor growth tactics).
- **Owns:** the acquisition portfolio — which channels, in what order (channel
  execution belongs to `marketing-lead`); the viral loop and referral mechanics;
  the growth experiment backlog; public-launch sequencing.
- **Hands off:** buildable invite, share and referral work as a PRD through
  `head-product` to `head-eng`; acquisition funnel events to `analytics-lead`;
  channel work to `marketing-lead` through `head-product` and `head-bizops`.
- **Accepts on:** each growth bet has a hypothesis, the cheapest test, and a success
  criterion; deliverables end with **Decisions needed** + **Handoffs**.

### `analytics-lead`
- **Charter:** `/an-funnel` (metrics) or `/an-data-architect` (taxonomy).
  **Workers:** `an-user-data`, `an-experiment`, `an-market`.
- **Owns:** metric definitions, the tracking plan, grants on
  `backend/analytics_taxonomy.py` + `analytics_queries.NON_INTENT_EVENTS`,
  experiment launches (with operator approval).
- **Accepts on:** numbers cite query, source and time; new events registered and
  classified in the emitter's commit.

### `ux-lead` — user experience
- **Charter:** `ux-design` and `ux-research` were retired on 2026-08-08 for producing
  no deliverables. Restore with
  `mv archive/skill-workspaces/retired-2026-08-08/<name> .claude/skills/<name>` (the
  operator's call), or run from `/pm-pfo` until then.
- **Owns:** cross-area flows and navigation, screen states (empty, loading, error),
  the onboarding path, interaction specs, usability evidence from feedback and
  TestFlight checklists.
- **Gives:** review of any flow or navigation change; UX specs that area product
  leads fold into their PRDs.

### `design-lead` — visual design
- **Charter:** no repo skill; user-level `/brand-lab` for palette and system work.
  Ground in ADR-004 and ADR-005.
- **Owns:** `docs/design/` (`design-system.md`, `components.md`, `brand.md`),
  `web/style-guide.html`, `mockups/`; tier and position color encodings jointly with
  `head-eng` (`docs/cross-client-invariants.md`).
- **Gives:** review of any UI change against Chalkline (no emoji icons, gradients,
  blur, system font stacks, radius over 8px, or accents beyond ice and flare). UI
  diffs reach it from `head-eng` through `head-product`.

## Function leads under `head-eng`

### `models-eng`
- **Charter:** `/eng-architect` scoped to engines. **Workers:** `eng-backend`.
- **Owns:** `ranking_service.py`, `value_model.py`, `backend/value_core/`,
  `trade_service.py` (v2 scoring), `trade_optimizer.py` (v3 package search),
  `trade_gen_*.py`, `fit_engine.py`, `trade_mutual_benefit.py`,
  `trade_significance.py`, `win_now_optimizer.py`, `season_simulator.py`,
  `season_forecasts.py`, `season_calibration.py`, `pick_values.py`,
  `dp_values_history.py`, `bakeoff_*.py`, `backend/outlook/`, `backend/eval/`,
  `backend/tier_config.json`, `model_config` keys.
- **Accepts on:** the change matches `models-lead`'s spec; backtests or eval output
  attached; `models-lead` signs off on behavior changes.

### `release-lead`
- **Charter:** `/ops-release` + `/eng-qa`. **Workers:** `eng-qa`, the scribe.
- **Owns:** merges and pushes to `main`, Render deploys, EAS builds and submits,
  prod flag flips, the independent QA pass, `living-memory/` write-back,
  `docs/recovery/`, and the release log (`docs/business/ops/release-log.md`,
  created on first use per `/ops-release`).
- **Accepts on:** operator go/no-go; CI green; evidence logged in TEST_LEDGER.

## Function leads under `head-bizops`

### `models-lead` — models strategy
- **Charter:** no repo skill. Use the user-level `/model-hypothesis-testing` for
  hypothesis rounds; ground in `living-memory/DECISIONS.md` model decisions (e.g.
  D-052, D-054, D-055, D-060).
- **Owns:** what each model optimizes (ranking Elo, value, trade scoring and
  packaging, outlook); deck and ranking quality bars; the hypothesis backlog; which
  experiments test model changes (with `analytics-lead`, through the department
  heads).
- **Does not own:** engine code — that is `models-eng`, reached through
  `head-bizops` → `head-eng`.
- **Gives:** sign-off on any change in model behavior.

### `marketing-lead`
- **Charter:** `/mkt-brand`. **Workers:** `mkt-aso`, `mkt-seo`, `mkt-content`,
  `mkt-writer`, `mkt-partners`, `mkt-lifecycle`.
- **Owns:** `docs/business/marketing/` and channel execution for `growth-pm`'s
  acquisition portfolio. Any outbound message needs the operator.
- **Accepts on:** deliverables end with **Decisions needed** + **Handoffs**.

## Roles off the chart

`pm-monetization` and `mkt-adops` join only when monetization or ads activate — as a
worker under the closest lead, or as a new lead the operator approves.
