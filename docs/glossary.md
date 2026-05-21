# Glossary

Domain terms used throughout the codebase. Add a term when new jargon appears.

---

**Elo** — Rating system from chess. Each player has a numeric rating; comparing two players updates both based on actual vs. expected outcome. Used to rank fantasy players within a single user's preferences.

**K-factor** — How aggressively an Elo update moves a rating. Higher K = bigger swings. Per decision type (defaults from `model_config`):
- Rank (3-player matchup): `elo_k = 32`
- Trade like: `trade_k_like = 8`
- Trade pass: `trade_k_pass = 4`
- Trade accept: `trade_k_accept = 20`
- Trade decline correction: `trade_k_decline_correction = 20`

**3-player matchup (trio)** — User orders 3 players best→worst. Decomposed into 3 pairwise rows in `swipe_decisions` (A>B, B>C, A>C) → 3 Elo updates. ~2.6× more information per interaction than pairwise.

**KTC value** — Dynasty trade value styled after [KeepTradeCut](https://keeptradecut.com/). Used as UI display value and as the seed for initial Elo. Curve params in `model_config`: `ktc_max=10000`, `ktc_k=0.0126`, `ktc_fallback_rank=300`.

**DynastyProcess (DP)** — GitHub CSV of consensus dynasty values; seed source for initial Elo via `data_loader.py`.

**Tier band** — Bucket of similar Elo ratings rendered as a labeled, colored badge (Elite gold / Starter green / Solid blue / Depth purple / Bench gray). Cutoffs in client-side `tierBands.ts` and equivalents — keep in sync.

**Team outlook** — User's strategic mode for a league (`league_preferences.team_outlook`):
- `championship` — boost vets (1.50×), penalize youth
- `contender` — moderate vet boost (1.25×)
- `rebuilder` — mirror of championship — boost youth
- `jets` — extreme youth-only; heavy 0.30× penalty for age ≥`jets_age` (25)
- `not_sure` — neutral

Age thresholds (`model_config`): `vet_age=27`, `youth_age=26`, `jets_age=25`. Multipliers: `boost_strong=1.50`, `boost_moderate=1.25`, `neutral=1.00`, `penalty_soft=0.75`, `penalty_mod=0.60`, `penalty_heavy=0.30`.

**Package weights / diminishing returns** — Multi-player trade sides apply diminishing weights so "5 bench guys for an elite WR" doesn't look equal. From `model_config`: `package_weight_1..5 = 1.00, 0.75, 0.55, 0.40, 0.28`.

**Positional preference multipliers** — Bonuses/penalties for trades that match the user's `acquire_positions` / `trade_away_positions`. `pos_acquire_bonus=0.20`, `pos_tradeaway_bonus=0.15`, `pos_conflict_penalty=0.15`, capped at `pos_multiplier_cap=2.00`.

**Trade scoring** — Composite of mismatch and fairness components. `mismatch_weight=0.70`, `fairness_weight=0.30`. Cards below `min_mismatch_score=40` or above `max_value_ratio=2.5` are filtered. `max_candidates=500` per opponent before sort. Cross-side Elo gap > `trade_elo_gap_max=250` rejects the trade.

**Trade-math adjustments (flag-gated)** — Optional penalties enabled via feature flags:
- `qb_tax_rate=0.075` — penalty for receiving a premium QB without giving one back
- `star_tax_per_tier_gap=0.10` × `star_tax_elite_multiplier=1.5` for Tier-1 stars
- `roster_spot_penalty=0.05` per extra roster spot used
- `roster_clogger_penalty=0.10` additional per player beyond 2 in 3+ one-way trades, threshold `roster_clogger_threshold=3`

**Tier engine** — Pre-unlock matchup filter that focuses trios on top `tier_size=24` per position. Post-unlock, mixes in lower-tier players at probability `mix_in_rate_base=0.35` rising to `mix_in_rate_max=0.80` as comparisons saturate (`mix_in_saturation_pct=0.70`). Pre-unlock mix-in begins at `mix_in_pre_unlock_start=5` interactions. Toggle via `tier_engine_enabled` (1.0).

**Smart matchup** — Claude-powered matchup selection. Generates ~10 candidate pairs (nearby Elo, not yet compared), asks Claude to pick the most dynasty-informative. Toggle via `smart_matchup_enabled` (1.0). Falls back to algorithmic without `ANTHROPIC_API_KEY`.

**Mutual gain trade / Trade match** — Both sides improve by their own Elo math. When both users like mirrored trades, a `trade_matches` row is created (status `pending`) and both inboxes get a `trade_match` notification.

**Mirrored trade** — Same player set viewed from both sides: A's "give X get Y" and B's "give Y get X" are mirrors.

**Sleeper user / league ID** — Public Sleeper IDs. We never create accounts; the Sleeper username is the identity.

**Decision type** — `swipe_decisions.decision_type`: `'rank'` (3-player) or `'trade'` (trade card).

**Ranking method** — `users.ranking_method`: `null`, `'trio'`, `'manual'`, or `'tiers'`. How the user is building their rankings.

**Scoring format** — Stored as `'1qb_ppr'` or `'sf_tep'`. Affects which seed values are loaded and which `member_rankings` rows are visible. Per-league via `leagues.default_scoring`.

**Unlocked formats** — `users.unlocked_formats` JSON list — formats in which the user has met the gating threshold and unlocked Trade Finder.

**Tier overrides** — `users.tier_overrides`: per-format `{player_id: elo}` map of manual overrides applied on top of the trio-derived Elo.

**Contrarian** — A user's ranking that materially disagrees with the league or community consensus. Surfaced via `/api/trends/contrarian` and `/api/league/contrarian`.

**Wrapped** — Year-end recap powered by `wrapped_events`. Event types: `swipe`, `trade_match`, `trade_accepted`, `trade_declined`, `tier_save`, `ranking_reorder`, `league_sync`.

**user_events vs wrapped_events** — `user_events` is the structured product analytics log (one row per meaningful action with denormalized hot-read columns mirrored on `users`). `wrapped_events` is the silent stream specifically for the year-end recap. Both are append-only.

**OG image** — Open Graph share image (1200×630 PNG) generated server-side by `og_image.py` for tier and trade share links.

**Notification kind** — Granular type recorded in `notification_events_log.kind` (e.g. `new_match`, `winback_dormant`). Maps to a user-facing **bucket** (`trade_matches` / `weekly_digest` / `reengagement`) via `get_pref_bucket()` in the push dispatcher; the bucket controls the user's toggle in `notification_prefs`.

**Quiet hours** — When `notification_prefs.quiet_hours_enabled = 1`, pushes that fire during the user's local night land in `notification_queue` instead. The hourly cron tick collapses each user's queued rows into one summary push at their local 8am and clears the queue.

**Cron tick** — External scheduler (Render cron) hits `/api/cron/realtime-tick`, `/api/cron/hourly-tick`, or `/api/cron/daily-tick`. Real-time drains queued pushes ready to deliver; hourly handles bundle drain + 8am summaries; daily runs digests and re-engagement scans.

**Dedup key** — Identifier used to avoid sending the same notification twice (e.g. `match_id` for `new_match`, week-stamp for digests). Stored in `notification_events_log.dedup_key`.

**Streak** — Current user's daily-activity streak (consecutive days with a meaningful event). Surfaced via `/api/me/streak`.

**Leaderboard** — League + Universal leaderboards rendered inside the League tab. Backed by `/api/leaderboard`.
