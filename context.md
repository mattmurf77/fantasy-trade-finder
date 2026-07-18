# Fantasy Trade Finder — Project Context

*Last refreshed: 2026-07-12*

## Overview

Fantasy Trade Finder is a dynasty fantasy football app that helps users rank their players and discover mutually beneficial trades with leaguemates. Users log in via their Sleeper username (Sleeper's API is public), import their roster, rank players through a swipe-based 3-player matchup interface, and get personalized trade card suggestions based on valuation mismatches between themselves and their leaguemates. The app is live: backend deployed on Render, iOS app on TestFlight (v1.7.0), with two scoring formats (`1qb_ppr`, `sf_tep`) and a verified-account auth layer currently in grace mode.

## Tech Stack

- **Backend:** Python 3 / Flask (`backend/`), served via `run.py` on port 5000 locally (`PORT` env); production deploys to Render (`render.yaml`, `build.sh`) on push to `main`
- **Database:** SQLite at `data/trade_finder.db` via SQLAlchemy Core; swappable to PostgreSQL via `DATABASE_URL` env var. 22 tables — see `docs/data-dictionary.md`
- **Web Frontend:** Vanilla HTML/CSS/JS in `web/` (`index.html` SPA plus profile/player/privacy/terms/FAQ pages and the Chalkline style guide)
- **Mobile App:** React Native / Expo in `mobile/` — ships to TestFlight via EAS builds (currently v1.7.0)
- **Browser Extension:** Chrome/Edge MV3 in `extension/`, talks to `/api/extension/*` with a bearer token
- **Feature flags:** `config/features.json` (backend + clients), `FTF_FLAGS` env override, runtime reload endpoint — see `docs/config-reference.md`
- **AI Integration:** Anthropic Claude API (optional) for smart matchup generation; falls back to algorithmic selection if no `ANTHROPIC_API_KEY` is set
- **Data Sources:**
  - **Sleeper API** — user lookup, league data, rosters, player database (cached locally), and now *writes*: real trade proposals via Sleeper's GraphQL API
  - **DynastyProcess GitHub CSV** — consensus dynasty trade values used to seed initial Elo ratings

## Architecture

`docs/architecture.md` is the authoritative version of this section; summary below.

### Backend Modules (`backend/`)

- **`server.py`** (~6.4k lines) — Flask routes, session management, Sleeper passthrough, in-memory ring-buffer debug logger (`GET /api/debug/log?n=100`), typed push dispatcher (prefs/dedup/quiet-hours), cron tick handlers
- **`database.py`** — SQLAlchemy Core schema (22 tables), idempotent migrations, `model_config` defaults, mirror/fuzzy trade-match check
- **`ranking_service.py`** — Elo engine: pairwise + 3-player decomposition (2.6x more information per interaction); applies tier bands from `tier_config.json`
- **`trade_service.py`** — trade discovery. **v2 engine** (flag `trade_engine.v2`, ON): single value space, marginal valuation over replacement level, outlook now↔future blend, two-sided surplus gate, harmonic ranking, Thompson deck ordering, likes-you injection. Legacy scorer kept as flag-off fallback
- **`trade_optimizer.py`** — **v3 engine** (flag ON): exact per-pair package search + sweetener pass; 3-team cycle clearing built but dark (`trade.three_team` off)
- **`trade_narrative.py`** — deterministic template rationale strings for trade cards (no LLM)
- **`smart_matchup_generator.py`** — Claude-assisted matchup picker + algorithmic fallback, tier-engine aware
- **`data_loader.py`** — DynastyProcess CSV → seed Elo (KTC curve)
- **`accounts.py`** — Apple/Google identity anchors + account-first sessions (`auth.accounts`, ships dark pending App Store Connect setup)
- **`sleeper_write.py`** — Sleeper GraphQL write path (token verify + trade propose) behind `trade.send_in_sleeper` (ON)
- **`espn_service.py`** — ESPN league linking, dark (`espn.link` off)
- Also: `trends_service.py` (risers/fallers), `wrapped_collector.py` (event recording), `og_image.py` (share images), `feature_flags.py`, `tier_config.json` (single source of truth for tier bands), `scripts/` (offline calibration), `tests/` (pytest suite, 260+ green)

### Database Schema

See `docs/data-dictionary.md` for the full 22-table dictionary. Core tables: `users`, `leagues`, `league_members`, `swipe_decisions` (the interaction log), `member_rankings` (Elo snapshots), `trade_decisions`, `trade_matches`, `trade_impressions`, `notifications` (+ queue/log/prefs/device tokens), `players`, `draft_picks`, `league_preferences`, `model_config` (runtime-tunable constants), `elo_history`, `user_events`, `player_value_history`, `accounts` + `linked_identities`, in-app `feedback`.

### Ranking System Details

- **Elo K-factors** (defaults in `model_config`, runtime-tunable): rank decisions K=32, trade likes K=8, trade passes K=4, trade accepts K=20, trade decline corrections K=20
- **Tiers:** an 8-tier pick-value ladder anchored to draft-pick equivalents (`firsts_4plus`, `firsts_3`, `firsts_2`, `first_1`, `second`, `third`, `fourth`, `waivers`), banded per `(scoring_format, position)` in `backend/tier_config.json` and served to clients via `GET /api/tier-config`. This replaced the old elite/starter/bench taxonomy
- **Outlook:** the old team-outlook Elo multipliers are gone; outlook is now a now/future valuation blend inside the v2 trade engine, and positional preferences are a hard filter on candidate packages
- **Trade decisions feed back into rankings:** likes/passes/accepts/declines update Elo with smaller K-factors
- **Progress gating:** 10 rank decisions per position (QB/RB/WR/TE) unlock the Trade Finder, tracked per scoring format
- **Auth gates:** every mutating route runs a verified-write gate (grace mode while `auth.enforce_verified_writes` is off); board-content reads are denied to username-only sessions once the owner has verified (read privacy)

### Web Frontend

- SPA (`web/index.html`) with login, league selection, 3-player ranking, tiers, and trade finder; companion pages for public profiles, player pages, positional tiers, FAQ, privacy, terms
- Styled per the **Chalkline design system** (`docs/design/`, live reference `web/style-guide.html`)
- Known gap: no verification capture flow yet (mobile-only), the top pre-enforcement priority

### Mobile App (`mobile/`)

- **Framework:** React Native + Expo; TypeScript; EAS builds auto-submitted to TestFlight (ascAppId 6771488431). Version 1.7.0
- **~20 screens** in `mobile/src/screens/` (SignIn, LeaguePicker, RankHome/Rank, Tiers, QuickSetTiers, ManualRanks, PickAnchor, Trades, TradeCalculator, Matches, League, Trends, Portfolio, Profile, Settings, Feedback inbox, …) wired in `mobile/src/navigation/` (RootNav + TabNav)
- **Highlights:** manual trade calculator (live consensus mode + demo league), Send in Sleeper (proposes real trades in-app — confirmed working end-to-end), Sign in with Apple verification banner, in-app feedback FAB
- **State:** hooks + context in `mobile/src/state/`; API client in `mobile/src/api/` (treats 403 `verification_required` as a central signal); Sentry observability; `app.config.js` layers test-harness env (Maestro UI tests in `mobile/.maestro/`)

## Key Design Decisions

ADRs live in `docs/adr/`. The big ones:

1. **Elo-based ranking over tier lists** — continuous valuations that converge with more comparisons; 3-player matchups for efficiency
2. **Trade decisions as ranking signal** — using the trade finder improves your rankings
3. **DynastyProcess seeding** — no cold start; consensus values map to starting Elo
4. **Runtime-tunable model config** — constants live in the DB, adjustable without deploys
5. **Trade engine v2/v3 rebuild (2026-06)** — mutual-gain gate in each side's own value space, marginal valuation, consensus-basis cards for opponents without real rankings; legacy scorer retained as a kill-switch fallback
6. **Feature flags everywhere** — risky features ship dark and flip via `config/features.json` or `FTF_FLAGS` env
7. **Chalkline design system (ADR-004/005)** — all UI work uses its tokens; no emoji-as-icons, no gradients, ice/flare accents only
8. **Verified-session auth (2026-07)** — Sleeper JWT (or Apple/Google anchor) proves account control; write/read gates protect boards from username squatters, currently in grace mode

## Matchup Selection

The tiered matchup engine shipped: matchup selection prioritizes higher-ranked players first (tier engine settings: `tier_engine_enabled`, `tier_size`, mix-in rates) so users get confident top-of-roster rankings early, with `trio_repeat_avoid` preventing repeats. `smart_matchup_generator.py` optionally asks Claude to pick the most dynasty-informative pair; the algorithmic fallback needs no API key.

## Development Environment

- **Local server:** `python3 run.py` → Flask on `http://0.0.0.0:5000` (macOS AirPlay squats port 5000; kill with `lsof -ti:5000 | xargs kill -9`)
- **Mobile dev:** `cd mobile && npx expo start`; typecheck with `npx tsc --noEmit`. Note: spaces in the repo path break local `expo run:ios` — use the no-space clone at `../ftf-test-clone`
- **Tests:** `python3 -m pytest backend/tests/ -q` (260+ passing); Maestro UI flows in `mobile/.maestro/`
- **Deploy:** merge to `main` → Render auto-deploys; `npx eas-cli build --platform ios --profile production --auto-submit` → TestFlight. Active work is on branch `trade-engine-v2`
- **Secrets:** `secrets.local.env` at project root (gitignored) — `CRON_SECRET` (guards admin + cron surface), `SLEEPER_TOKEN_KEY`, etc. Never paste secrets into chat
- **Session memory:** `living-memory/` (CHANGELOG, HANDOFF, NEXT, GOTCHAS, OPEN_QUESTIONS) is the session-to-session state; read it at session start
- **Housekeeping conventions:** stale root artifacts archived under `archive/root-cleanup-2026-07/`; durable feedback-fix outputs at `docs/feedback/items/<id>-<slug>/` (see its README) with gitignored scratch in `feedback-workspace/<id>/`; staged competitor-feature backlog in gitignored `staged-work/`

## Data Logging

- **User interactions:** `swipe_decisions` + `trade_decisions`, plus structured `user_events` via `wrapped_collector.record_event()` (dual-write with denormalized `users.last_*_at` columns)
- **Served trade decks:** logged to `trade_impressions`; engine like/match rates at `/api/admin/engine-metrics`
- **Backend operations:** in-memory ring-buffer logger (last 200 entries) at `GET /api/debug/log` (CRON_SECRET-gated); in prod, use the Render Logs tab

## Sleeper API Integration

- **Reads:** user lookup, league import with rosters, bulk player cache (refreshes when stale), traded-pick overlay from `/v1/league/<id>/traded_picks`
- **Writes (Send in Sleeper):** the app can propose real trades into Sleeper leagues via their GraphQL API — requires the raw JWT (no `Bearer` prefix) and browser-like headers to clear Cloudflare; token stored Fernet-encrypted (`SLEEPER_TOKEN_KEY`). The captured token doubles as the verification proof for auth
- **ESPN:** league-linking P1 built behind `espn.link` (off)

## Claude Code Skills

Repo-local skills live in `.claude/skills/` (moved from the project root in the 2026-07 cleanup; old eval workspaces archived to `archive/skill-workspaces/`):

- **`project-reorganizer`** — reorganizes messy project folders into conventional structures
- **`feature-evaluator`** — reviews a feature area and emits a severity-rated improvement report
- **`project-architect`** — generates/maintains the `docs/` reference layer and per-folder CLAUDE.md files

A large roster of role skills (eng-*, pm-*, mkt-*, an-*, plus `/feedback` and `/maestro-test` pipelines) is defined at the user level.

## Mascot / Branding

Still an open branding question (Q-009, no code dependency). Past candidates: a cartoon running back mid-fumble named "Tommy Tumble" or "Ricky Rumble".

## API Routes

`docs/api-reference.md` is the authoritative route list — the surface has grown far beyond what's worth inlining here. Major groups: session/auth (+ verified-write and read gates), account auth (Apple/Google, dark), Sleeper passthrough, trio ranking, tiers, trades (generate/swipe/liked/matches/propose), the public manual trade calculator (`/api/trade/evaluate`, `/api/trade/values`), league, notifications, cron ticks, trends, public profiles/sharing/OG images, extension, feature flags, admin (CRON_SECRET-gated), and in-app feedback.

## Open Items / Next Steps

`living-memory/NEXT.md` is the live queue. Current highlights:

- **Real-match validation** — recruit 1–2 leaguemates to prove the two-sided match loop with real people; watch `/api/admin/engine-metrics` as usage lands
- **Auth enforcement path** — `auth.accounts` dark pending App Store Connect Sign-in-with-Apple setup; web/extension verification capture is the top gap before flipping `auth.enforce_verified_writes`
- **Engine threshold tuning** — revisit once `trade_impressions` volume supports a learned acceptance model
- **3-team trades client UI** — backend live but dark until 2-team matches prove out
- **FB-47 needs-based finder scoping**, Android `versionName` alignment, Chrome Web Store submission decision, league-chat announcement follow-up to Send in Sleeper
