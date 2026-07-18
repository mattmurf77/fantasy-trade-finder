# Analytics Program Plan — Reports, Dashboards, Metrics & Review Ritual

**Role:** an-funnel · **Date:** 2026-07-17 · **Status:** Spec
**Depends on:** `2026-07-17-tracking-plan-v2.md` (every formula below names events from that plan; events marked ⚡ exist today, 🌑 ship with v2). Experiment readouts: see `2026-07-17-experimentation-framework.md`.

## Question & context

Define the complete report/dashboard layer: the step-by-step UX waterfall, time-per-action / think-time, bottlenecks, churn/crash diagnostics, feature adoption, release health, and the recurring review ritual — each metric as a formula over named events so an-user-data can compute it and the dashboard can render it. This updates the seed funnel in `docs/business/context.md` (Decision below).

## Canonical funnel v2 (proposed context.md amendment)

Unit = **device** until sign-in, then **user** (stitched via `identity_links`). Stage entry criteria:

| # | Stage | Entry criterion (event) |
|---|---|---|
| 0 | Install/first open | first 🌑`app_opened` per `device_id` |
| 1 | Sign-in started | 🌑`signin_attempted` |
| 2 | Signed in | 🌑`signin_succeeded` (⚡`signup` for first-ever) |
| 3 | League selected | 🌑`league_selected` |
| 4 | Board started | first ranking action: ⚡`trio_swipe` ∨ 🌑`tier_save` ∨ 🌑`anchor_answered` ∨ 🌑`quickset_completed` |
| 5 | **Activated: board unlocked** | ⚡`ranking_complete_first_time` |
| 6 | First suggestions seen | first 🌑`trades_generated` with `count>0` |
| 7 | First trade opinion | first ⚡`trade_proposed` ∨ `match_swiped` |
| 8 | Matched | first ⚡`trade_ratified` ∨ 🌑`sleeper_send_succeeded` |
| 9 | Retained wk2+ | any event in ≥2 distinct weeks post-signup |
| 10 | Paid (future) | entitlement event TBD with pm-monetization |

## Metric definitions (formulas)

- **DAU/WAU/MAU:** distinct `user_id` with ≥1 event of an *intent* type (excludes `app_opened`, `screen_viewed`, pushes) in day/7d/28d. Report alongside "opened" counts; at beta scale always show **counts, not just rates**.
- **Activation rate:** users reaching stage 5 ≤7 days from stage 2 ÷ users at stage 2 (weekly signup cohorts).
- **Time-to-first-value (TTFV):** median minutes, stage 2 → stage 6, per cohort. (PFO's headline number.)
- **Retention (cohort):** classic triangle — % of weekly signup cohort with ≥1 intent event in week N after signup, N=1..8.
- **Churn (beta def):** no intent event in 14 days. `churned_at` = last event timestamp.
- **Trade-quality funnel:** per week: `trades_generated` Σcount → `trade_card_viewed` → likes (`trade_proposed`) → `trade_ratified` → `sleeper_send_succeeded`. Like rate = likes ÷ cards viewed; insult rate = `trade_flagged` ÷ cards viewed.
- **North star (recommendation): Weekly Active Traders (WAT)** — distinct users with ≥1 trade opinion event (`trade_proposed`/`match_swiped`/`sleeper_send_*`/`calc_trade_evaluated`) in the week. Leading indicator of the value loop (personal board → actionable trades), not vanity (screen views) and not lagging (ratified trades, which need two sides). Guardrail pair: insult rate must not rise as WAT rises.
- **Think time:** per-step median gaps (see R2).

## Report catalog

**R1. Onboarding Waterfall (the flagship).** Weekly signup cohort × stages 0–8: users reaching stage, step conversion %, cumulative %, median time-in-step, drop-off count. Segmentable by platform, signin method, ranking method, league_count, experiment variant (via the `experiments` envelope column). Beta view: per-tester row-level trace (this cohort is small enough to name names).

**R2. Time-per-Action / Think-Time.** Per stage-transition and per repeated action: p50/p90 of (a) event-gap within session (`client_ts` deltas), (b) explicit `decision_ms`/`dwell_ms` props on trios/trade cards, (c) `duration_ms` on quickset/quickrank. Highlights: swipe cadence (trios/min), trade-card dwell before like vs pass vs flag, sign-in→league-pick hesitation. "Bottleneck flag" = any step whose p50 time or drop-off worsens >25% WoW.

**R3. Bottleneck & Rage report.** Ranked list: steps by (drop-off % × cohort size), plus friction signatures — repeated `signin_failed`, `espn_link_failed`, retry taps, `client_error` clusters, `trade_flagged` spikes by lane/variant, sessions ending ≤60 s after a specific screen (screen-exit-to-churn table: last `screen_viewed` before 14-day silence).

**R4. Churn & Problem-Feature Diagnostic.** For churned users: last screen, last event, error-adjacency (had `client_error`/`_failed` within 24 h of last event), stage reached. Output: "features implicated in churn" ranked by (churners whose last session touched feature ÷ feature's active users).

**R5. Crash/Error & Release Health.** `client_error` (+ Sentry if adopted) by screen × `app_version` × platform; crash-free-session %; per-release adoption curve and deltas on activation/WAT/insult-rate vs prior version (the release regression gate ops-release checks before promoting).

**R6. Feature Adoption Matrix.** Per feature vertical (5 ranking methods, calculator, leagues suite screens, matches, send-in-Sleeper, extension, feedback): weekly users touching it, depth (events/user), overlap with WAT. Answers "what earns its screen real estate".

**R7. Engagement & Streaks.** DAU/WAU/MAU + intent breakdown, streak distribution (`users.current_streak`), push funnel (`push_sent` → `push_opened` → session within 1 h).

**R8. PFO Report** — spec owned by pm-pfo (`docs/business/product/2026-07-17-pfo-measurement-spec.md`); computed from R1/R2 slices.

**R9. Experiment Readouts** — per experimentation framework doc.

**R10. Weekly One-Pager** — auto-compiled: north star, funnel deltas, top bottleneck, top experiment update, top 3 anomalies; feeds the ritual below.

## Dashboard plan

Admin-only dashboard at `web/admin/analytics.html`, CRON_SECRET-gated backend routes `GET /api/admin/analytics/*` returning report JSON (SQL lives server-side in a new `backend/analytics_queries.py`; dashboard is a thin Chalkline-styled renderer). Pages = tabs: Waterfall · Time/Think · Bottlenecks · Churn · Releases · Adoption · Engagement · Experiments. Each report also exportable as JSON/CSV for an-user-data deep dives. No third-party BI at beta scale; revisit with Postgres migration.

## Review ritual

Weekly, Monday: an-user-data computes R10 → operator reviews (15 min agenda: north star, waterfall deltas, worst bottleneck, experiment decisions due, anomalies) → actions route to pm-* / eng-* / `/feedback`. Monthly: full R1–R7 pass + funnel-definition audit (this doc is the canon; changes via Decisions, not drift).

## Measurable today vs gaps

Measurable now (⚡ only): stages 2,4(partial),5,7,8(partial); WAT (server-side approximation); streaks; push sends. Everything else — stages 0,1,3,6, all think-time, all client/error/crash reporting, web+extension usage, per-variant slicing — **waits on tracking plan v2**. No estimated placeholders; reports render "—" until their events flow.

## Decisions needed

1. Adopt funnel v2 + WAT north star → amend `docs/business/context.md` funnel section (recommend yes).
2. Churn threshold 14 days (dynasty is slow-cadence; 7 is too twitchy offseason) — recommend 14, revisit in-season.
3. Dashboard as specced (admin HTML + gated JSON routes) vs CLI-only reports at beta — recommend build the dashboard; it's the self-service surface the operator asked for.

## Handoffs

- Event gaps → an-data-architect (all 🌑 already specced in tracking plan v2).
- Compute + first readouts once live → an-user-data. Benchmarks for activation/retention targets → an-market.
- Dashboard + query build → eng-backend/eng-web via analytics-platform PRD. Ritual owner → operator with an-user-data.
