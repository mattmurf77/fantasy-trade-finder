# PFO Measurement Spec — Instrumented Core-Loop Reports & Regression Gates

**Role:** pm-pfo · **Date:** 2026-07-17 · **Status:** Spec
**Companions:** tracking plan v2 + analytics program plan (`docs/business/analytics/2026-07-17-*`). This spec turns the manual PFO walkthrough into standing, instrumented reports. Until the 🌑 events ship, every number below is **unmeasured** — no placeholders.

## Question & context

The primary function is: sign in → sync league → rank via matchups → personalized values → mutual-gain trade suggestions. PFO audits are currently hand-timed walkthroughs. Once tracking plan v2 lands, the PFO report (R8 in the program plan) becomes computed, continuous, and experiment-aware — and every proposed feature/experiment gets judged against hard core-loop guardrails instead of my opinion.

## PFO report definition (computed weekly, per release, per experiment variant)

**Headline: Time-to-First-Value (TTFV)** — median minutes from `signin_succeeded` to first `trades_generated` with `count>0`, weekly signup cohorts, with the stage decomposition:

| Loop stage | Measure | Grade thresholds (proposed, calibrate after 4 wks of data) |
|---|---|---|
| Sign-in | `signin_attempted`→`signin_succeeded` conversion; failure loop count | works ≥95% / friction 85–95% / broken <85% |
| League pick | `signin_succeeded`→`league_selected` p50 gap; ESPN link failure rate | p50 ≤1 min |
| Board build | `league_selected`→`ranking_complete_first_time` p50; ranking actions required; per-method completion rate (quickset vs trios vs anchors vs tiers vs manual) | p50 ≤15 min same-session |
| First suggestions | unlock→`trades_generated(count>0)` p50; empty-deck rate (`count=0`) | empty-deck <5% |
| Opinion formed | cards viewed until first like; dwell p50; **insult rate** (`trade_flagged`÷cards viewed) | insult <3% |
| Real-world action | like→`sleeper_send_succeeded` conversion + failure rate | send failure <5% |

**Suggestion-quality rubric stays human** (sample + score fairness/fit/explanation per prior audits) — instrumentation adds *which* cards to sample: worst dwell-before-pass, all flagged cards, and the like-rate outlier lanes.

## Core-loop guardrail set (binding for every experiment & release)

Any experiment or release that degrades these beyond the noise band is a rollback candidate, regardless of its primary metric win:

1. Activation rate (stage 2→5, 7-day)
2. TTFV p50
3. Empty-deck rate
4. Insult rate
5. Crash-free session % on core-loop screens (SignIn, LeaguePicker, rank screens, TradesHome)

These five ship as the default guardrail block in the experimentation framework's test template. Burden of proof stays with the proposer: a feature adding a step before first suggestion must show TTFV neutrality at minimum.

## Regression watch (release health tie-in)

Per `app_version` (R5): the five guardrails vs prior version, flagged red at >10% relative degradation. ops-release consults this before expanding a rollout; eng-qa adds Maestro coverage for any stage that goes red twice.

## Decisions needed

1. Adopt the five guardrails as binding experiment/release gates (recommend yes — this is the "PFO protects the loop" contract, made mechanical).
2. Grade thresholds above are proposed from feel; confirm or recalibrate after first month of real data.

## Handoffs

- Events powering this: already specced in tracking plan v2 (an-data-architect) — no new asks.
- Computation + weekly render → an-user-data / analytics dashboard (R8 tab).
- Guardrail enforcement in the experiment engine → experimentation framework doc → eng-backend.
- Manual quality-rubric audits continue quarterly (pm-pfo), now data-targeted.
