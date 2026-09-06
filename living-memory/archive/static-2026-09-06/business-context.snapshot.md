# FTF Business Context

Shared grounding for the role skills in `.claude/skills/` (mkt-*, an-*, eng-*, pm-*, fin-*).
Every role skill reads this first. Keep it current — when a business fact changes
(pricing decision, launch, new platform, new cost), update this file.

## What the product is

Fantasy Trade Finder (FTF): dynasty fantasy football trade discovery. Users log in with
their Sleeper account, rank players via 3-player Elo matchups, and get mutual-gain trade
suggestions against other rosters in their league. Surfaces: iOS app (React Native/Expo,
TestFlight beta, v1.6.0), web app (`web/`, Render), Chrome/Edge extension (`extension/`),
Flask backend (`backend/`, Render, SQLite → Postgres-ready).

Technical source of truth is `docs/` (architecture, api-reference, data-dictionary,
cross-client-invariants, design system). This file covers the *business*, not the code.

## Business goal

Make money from the app, via **subscriptions and/or ads**. Currently **pre-revenue and
pre-public-launch**: TestFlight beta with real testers, in-app feedback pipeline live,
no analytics instrumentation, no payment or ad SDKs integrated, no public App Store
listing yet. Solo operator (Matt) running the company through Claude Code role skills.

## Current state (update as it changes)

- 2026-07-12: v1.6.0 on TestFlight — verified-session auth (grace mode), 6-tier
  pick-value taxonomy, trade meters. Trade engine v2 branch is the working branch.
- Deploy: push `main` → Render (backend/web); EAS build → TestFlight (mobile).
- Feedback loop: testers → `POST /api/feedback` → prod DB → `/feedback` skill pipeline.
- Analytics: **server-side events exist** — `user_events` append-only table in
  `backend/database.py`, fired via `record_event()` from ~15 sites in
  `backend/server.py` (trio swipes, ranking completion, match views/dismissals, trade
  dispositions, league syncs, tier saves). **Client-side is dark**: no install,
  app_open, screen-view, or pre-signin funnel events. Verify which event_types
  actually have rows before trusting coverage.
- No revenue, no marketing presence (no site SEO work, no socials, no App Store
  listing/ASO yet).

## Market

Dynasty fantasy football is a year-round, high-engagement niche inside season-long
fantasy. Competitors/adjacent: KeepTradeCut (crowdsourced values, free, ad-supported),
FantasyCalc, DynastyProcess, Dynasty Daddy, Dynasty Nerds (subscription content),
Sleeper itself (platform; free). FTF's wedge: *personalized* values from your own Elo
rankings + actionable mutual-gain trade suggestions, not one global consensus list.

**Seasonality matters for every role**: interest ramps July–August (drafts/camp), peaks
in-season (Sep–Dec), spikes around the rookie draft (late Apr–May) and NFL trade
deadlines, and troughs Feb–Mar. Dynasty trades happen year-round but attention doesn't.

## Monetization candidates (undecided — pm-monetization owns this)

- Subscription: premium finder features, multi-league, alerts/notifications, deeper
  targeting. Apple IAP required for digital features on iOS.
- Ads: banner/native/interstitial (AdMob or similar); requires ATT prompt handling and
  scale to matter.
- Hybrid: free ad-supported tier + ad-free premium sub is the category norm (KTC model
  vs Dynasty Nerds model).

## Funnel — ADOPTED 2026-07-17 (operator decision, PRD OQ-2)

**Funnel v2 + the WAT north star are canonical.** Full stage definitions and metric
formulas live in
[analytics/2026-07-17-analytics-program-plan.md](analytics/2026-07-17-analytics-program-plan.md);
the event taxonomy feeding them is
[analytics/2026-07-17-tracking-plan-v2.md](analytics/2026-07-17-tracking-plan-v2.md).
Short form: stage 0 first-open-per-device → sign-in → league sync → board started →
board usable (activation) → first trade suggestion viewed → trade opinion expressed →
mutual match → sent in Sleeper → retained week 2+ → paid conversion (future, stage 10,
unspecced per PRD N5). **North star = WAT (Weekly Active Traders).**

Instrumentation is being built per `docs/plans/analytics-platform/` (P0 in progress).
Treat metric claims as **proposed, not measured**, until the waterfall report renders
real counts for the stage in question. If a role needs data that doesn't exist, its
first deliverable is the instrumentation ask (route to an-data-architect), not
invented numbers.

## Cost baseline (fin-* skills own keeping this honest)

Render hosting, Apple Developer Program ($99/yr), EAS builds, Anthropic API (matchup
selection + this ops tooling), domain(s). No paid marketing spend to date.

## Conventions for role deliverables

- Save deliverables to `docs/business/<dept>/YYYY-MM-DD-<slug>.md`
  (dept = marketing | analytics | product | engineering | finance).
- Every deliverable ends with two sections: **Decisions needed** (operator calls,
  each with a recommendation) and **Handoffs** (which role skill or the `/feedback`
  pipeline takes each follow-up).
- Buildable work ships through the `/feedback` pipeline or an eng-* skill — strategy
  roles don't edit product code.
- Secrets live in `secrets.local.env`, never in chat or deliverables.
