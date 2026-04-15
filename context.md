# Fantasy Trade Finder — Project Context

## Overview

Fantasy Trade Finder is a dynasty fantasy football app that helps users rank their players and discover mutually beneficial trades with leaguemates. Users log in via their Sleeper username (no account creation required — Sleeper's API is public), import their roster, rank players through a swipe-based interface, and then get personalized trade card suggestions based on valuation mismatches between themselves and their leaguemates.

## Tech Stack

- **Backend:** Python 3 / Flask, served via `run.py` on port 5000
- **Database:** SQLite (local dev) via SQLAlchemy Core; designed to swap to PostgreSQL via `DATABASE_URL` env var
- **Web Frontend:** Vanilla HTML/CSS/JS served from `web/index.html`
- **iPhone App:** React Native (Expo) in `iPhone/` directory, connects to the Flask backend over local network
- **AI Integration:** Anthropic Claude API (optional) for smart matchup generation; falls back to algorithmic selection if no `ANTHROPIC_API_KEY` is set
- **Data Sources:**
  - **Sleeper API** — user lookup, league data, rosters, player database (3,888+ players cached locally)
  - **DynastyProcess GitHub CSV** — consensus dynasty trade values (660 players, 636 with value > 0) used to seed initial Elo ratings

## Architecture

### Backend Modules (`backend/`)

- **`server.py`** — Flask app with all API routes, Sleeper API integration, in-memory ring-buffer debug logger (last 200 entries at `GET /api/debug/log?n=100`), and session management
- **`database.py`** — SQLAlchemy Core table definitions and persistence layer
- **`ranking_service.py`** — Elo-based ranking engine supporting both 2-player (pairwise) and 3-player (full-rank) interactions. 3-player ranking decomposes into 3 pairwise decisions, yielding 2.6x more information per interaction
- **`trade_service.py`** — Trade card generation engine that compares ranking sets across league members to find mutual-gain trade opportunities. Includes team outlook modifiers, positional preference scoring, and package diminishing-returns weights
- **`smart_matchup_generator.py`** — Claude-powered matchup selection. Computes live Elo, generates ~10 candidate pairs (nearby Elo, not yet compared), and asks Claude to pick the most dynasty-informative pair
- **`data_loader.py`** — Fetches DynastyProcess consensus values CSV and maps dynasty trade values to initial Elo ratings (value 10000 ≈ Elo 1800 elite, value 5000 ≈ Elo 1500 solid starter, value 0 ≈ Elo 1200 bench/depth)

### Database Schema (SQLite: `trade_finder.db`)

- **`users`** — Sleeper user profiles (sleeper_user_id, username, display_name, avatar)
- **`leagues`** — User's dynasty leagues with roster and opponent data (JSON)
- **`swipe_decisions`** — Every pairwise comparison (winner/loser player IDs, decision_type: 'rank' or 'trade', k_factor). This is the core interaction log
- **`trade_decisions`** — High-level trade card decisions (like/pass) with give/receive player ID arrays
- **`league_members`** — All members of every league the user has accessed, with rosters
- **`member_rankings`** — Latest Elo snapshot per player per user per league, replaced atomically
- **`trade_matches`** — Created when two users both swipe "like" on mirrored trades. Status lifecycle: pending → accepted/declined
- **`notifications`** — In-app notification inbox (types: trade_match, trade_accepted, trade_declined)
- **`players`** — Canonical player reference synced from Sleeper bulk payload (QB/RB/WR/TE, Active or prospects). Includes age, team, injury info, depth chart, ADP
- **`draft_picks`** — Dynasty draft pick assets across all upcoming seasons with computed pick values and trade tracking
- **`league_preferences`** — User's team-building outlook per league (championship/contender/rebuilder/jets/not_sure) and positional acquire/trade-away preferences
- **`model_config`** — Runtime-tunable constants for the ranking and trade engines (Elo K-factors, team outlook multipliers, KTC curve parameters, package weights, scoring thresholds)

### Ranking System Details

- **Elo K-factors:** rank decisions use K=32, trade likes K=8, trade passes K=4, trade accepts K=20, trade decline corrections K=20
- **Team Outlook multipliers:** championship mode boosts vets (1.5x), penalizes youth; rebuilder mode does the opposite; "jets" mode is extreme youth-only (penalty 0.30 for age ≥26)
- **Trade decisions feed back into rankings:** "Interested" in trading Player A for Player B implies B > A, updating Elo with a smaller K-factor
- **Progress gating:** Users must complete a minimum number of rankings per position (10 per position for QB/RB/WR/TE) before the Trade Finder tab unlocks. A segmented progress bar shows per-position completion with color coding (orange=QB, green=RB, blue=WR, purple=TE)

### Web Frontend

- Single-page app with screens for: Login, League Selection, Player Ranking (swipe interface), and Trade Finder (trade cards)
- Two-tab layout: "Rank Players" and "Trade Finder"
- Ranking interface presents 3-player matchups for the user to order best→worst
- Trade cards show give/receive players, opponent, and match score with Interested/Pass actions

### iPhone App (`iPhone/`)

- **Framework:** React Native with Expo, using `expo start --tunnel` for development
- **Screens:** LoginScreen, LeagueSelectScreen, RankPlayersScreen
- **Connects to Flask backend** at `http://192.168.1.88:5000` (local network)
- **iOS HTTP exception** configured via `NSAllowsLocalNetworking` in `app.json` to allow plain HTTP to local addresses
- **State management:** React Context via `AppContext.js`
- **Theming:** Custom theme in `utils/theme.js`

## Key Design Decisions

1. **Elo-based ranking over simple tier lists** — Provides continuous, fine-grained valuations that naturally converge with more comparisons
2. **3-player matchups** — 2.6x more efficient than pairwise, reducing the number of interactions needed for stable rankings
3. **Trade decisions as ranking signal** — Like/pass/accept/decline on trade cards implicitly update player Elo ratings, so the more you use the trade finder, the better your rankings become
4. **DynastyProcess seeding** — Gives every player a reasonable starting Elo from community consensus so rankings aren't cold-starting from scratch
5. **Runtime-tunable model config** — All hardcoded constants stored in DB so they can be adjusted without code changes
6. **Simulated leaguemates for solo mode** — Trade Finder can generate cards against four simulated opponents with distinct dynasty philosophies (DynastyKing loves vets, RookieDrafter overvalues youth, VetHeavy is WR-first, WRCorner is QB-needy) when no real league data is available

## Current Matchup Selection Logic

The current matchup generator (`smart_matchup_generator.py` + algorithmic fallback in `ranking_service.py`) finds the **tightest Elo cluster** among adjacent players regardless of rank tier. It optimizes for global information gain — a trio near rank #30 gets the same consideration as one near rank #1. The only differentiator is spread + existing-comparison count.

**Planned improvement (in progress):** A tiered matchup engine that prioritizes higher-ranked players first and gradually works through lower tiers. This would give users confident top-of-roster rankings earlier, which matters most for trade decisions.

## Development Environment

- **Local server:** `python3 run.py` → Flask on `http://0.0.0.0:5000`
- **iPhone dev:** `cd iPhone && npx expo start --tunnel --clear` → scan QR with Expo Go
- **Mac IP for mobile testing:** `192.168.1.88` (check with `ifconfig en0 | grep "inet "`)
- **Port conflicts:** macOS AirPlay Receiver uses port 5000; kill with `lsof -ti:5000 | xargs kill -9`
- **Dependencies:** `pip install anthropic flask sqlalchemy` (see `requirements.txt`)
- **No ANTHROPIC_API_KEY:** App works fine without it — uses algorithmic matchup fallback

## Data Logging

- **User interactions:** Stored in `swipe_decisions` table (pairwise comparisons) and `trade_decisions` table (trade card likes/passes)
- **Backend operations:** In-memory ring-buffer logger (last 200 entries) accessible via `GET /api/debug/log?n=100`. Covers Sleeper API requests/responses, DB operations, player syncs, errors with tracebacks
- **No persistent log files:** Everything goes to stdout and the in-memory buffer. `database.py`, `ranking_service.py`, and `trade_service.py` don't use the logging module directly

## Sleeper API Integration

- **User lookup:** Fetches user profile by Sleeper username
- **League import:** Pulls all dynasty leagues for a user, including roster data and opponent rosters
- **Player database:** Bulk player cache (3,888 players) synced from Sleeper and stored locally in `.sleeper_players_cache.json`; refreshes if empty or stale (>24 hours)
- **Draft picks:** Resolves traded picks by overlaying Sleeper's `/v1/league/<id>/traded_picks` onto the full pick grid

## Custom Cowork Skills Created

- **`project-reorganizer.skill`** — Reorganizes messy project folders into clean conventional structures. Uses a 6-phase methodology: scan, propose structure, build cross-reference tables, execute moves, update imports, verify. Benchmarked at ~83% pass rate vs ~43% without the skill (+40pp improvement)
- **`feature-evaluator.skill`** — Evaluates code features across 7 dimensions (structure, readability, performance, error handling, security, testability, maintainability). Produces structured markdown reports with severity-rated findings and prioritized recommendations

## Mascot / Branding Ideas

- Exploring a football player avatar mascot with a name rhyming with "fumble"
- Top candidates: "Tommy Tumble" or "Ricky Rumble" — a cartoon-style running back mid-fumble
- Concept: ball popping out, jersey with "TUMBLE" or "RUMBLE" on the back

## API Routes Reference

### Session & Auth
- `POST /api/session/init` — Initialize session (Sleeper auth, league load, DB setup)
- `GET /api/session/ping` — Keep-alive / session validation

### Ranking
- `GET /api/trio` — Fetch next 3-player matchup to rank
- `POST /api/rank3` — Submit 3-player ranking (decomposes into 3 pairwise Elo updates)
- `POST /api/rankings/submit` — Alternative ranking submission endpoint

### Trade Finder
- `POST /api/trades/generate` — Trigger trade card generation for a league
- `GET /api/trades` — Fetch trade cards (filtered by state)
- `POST /api/trades/swipe` — Record like/pass on a trade card (also updates Elo)
- `GET /api/trades/liked` — Fetch user's liked trades

### Trade Matching (Real Leagues)
- `GET /api/trades/matches` — Fetch mutual trade matches (both users liked mirrored trades)
- `POST /api/trades/matches/<id>/disposition` — Accept or decline a matched trade

### Notifications
- `GET /api/notifications` — Fetch notification inbox
- `POST /api/notifications/read` — Mark notification as read
- `POST /api/notifications/read-all` — Mark all as read

### Admin / Config
- `GET /api/admin/config` — Fetch all runtime-tunable constants
- `PUT /api/admin/config/<key>` — Update an individual config value

### Misc
- `GET /api/league/coverage` — Player coverage stats per league
- `POST /api/reset` — Wipe user data and start fresh
- `GET /api/debug/log?n=100` — Fetch last N entries from in-memory debug log (max 200)

## Open Items / Next Steps

- **Tiered matchup engine** — Redesign matchup selection to prioritize higher-ranked players first, then filter through lower tiers (in active discussion)
- **Player name fuzzy matching** — DynastyProcess CSV names don't always match Sleeper names exactly; a fuzzy matching script (`dump_mismatches.py`) was created to identify and fix mismatches
- **League linking for real trades** — Currently uses simulated leaguemates; full Sleeper league integration for real trade matching is the next major feature
- **iPhone app completion** — Login and league select screens built; ranking screen in progress; trade finder screen not yet ported
- **Production deployment** — Switch from SQLite to PostgreSQL, add proper authentication, deploy to a hosting provider
