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

**Team outlook** — User's strategic mode for a league (`league_preferences.team_outlook`): `championship`, `contender`, `rebuilder`, `jets`, `not_sure`. Since the trade-engine v2 rebuild, outlook feeds the **outlook blend** (see below) — the old post-hoc score multiplier (`team_outlook_multiplier`) is deleted, and the legacy engine path ignores outlook entirely. The historic multiplier keys (`boost_strong`, `vet_age`, …) still exist in `model_config` but are unused.

**Package weights / diminishing returns** — Multi-player trade sides apply diminishing weights so "5 bench guys for an elite WR" doesn't look equal. From `model_config`: `package_weight_1..5 = 1.00, 0.75, 0.55, 0.40, 0.28`.

**Positional preferences** — The user's `acquire_positions` / `trade_away_positions` for a league. Since the v2 rebuild these are a **hard filter** on candidate packages (a card must receive an acquire position / give a trade-away position when set) in both engine paths; the old soft multipliers (`pos_acquire_bonus` etc.) are deleted from code though their `model_config` keys remain.

**Value space / `elo_to_value`** — The v2 engine does ALL trade math in dynasty-value units, not Elo. `elo_to_value(elo) = elo_value_base · exp(elo_value_k · (elo − elo_value_ref))` maps each side's (shrunk) Elos onto the same scale as consensus KTC-style values, so surpluses and fairness are commensurable. `backend/trade_service.py:235`.

**Marginal value (over-replacement)** — Tier 2 valuation (`trade.marginal_value`): a player's worth to a *specific roster* is `max(0, value − replacement_level(position))` plus a `bench_credit_rate` (15%) credit, where the replacement level is that roster's best non-starter at the position (waiver baseline if the position is thin). Makes clogger packages collapse and need-fillers keep value.

**Now/future value & outlook blend** — Tier 2 (`trade.outlook_blend`): every player has a win-now and a long-horizon age multiplier (per-position curves `_AGE_NOW_CURVE` / `_AGE_FUTURE_CURVE`); the user's outlook sets α (`outlook_alpha_*`, championship 1.00 → jets 0.10) and the value used is `α·now + (1−α)·future`. An *input* to surplus math, so it composes with the fairness gate — unlike the deleted post-hoc multiplier.

**Inferred outlook** — Backlog #1 (`trade.outlook_infer`): the opponent equivalent of the above. Where the user's α comes from their declared outlook, each *opponent's* α is resolved per trade as declared (`league_preferences`) → **inferred** → `not_sure`. `infer_team_outlook` classifies a team's contend/rebuild window from roster shape — veteran value share, youth value share, and draft-pick-capital share — bucketing into contender / not_sure / rebuilder (the extremes championship/jets are reserved for self-declaration). The opponent's side of every candidate trade is then priced through their α, so the engine stops offering aging vets to rebuilders. Cards carry `match_context.opponent_outlook = {value, source}`.

**Range-overlap fairness** — v2 fairness gate: each package's consensus value gets an uncertainty half-width from comparison counts (`range_base/√(1+n)`, value-weighted); a trade passes when the two sides' value intervals overlap OR the point ratio clears `fairness_threshold`. High-uncertainty players (rookies) pass more easily. The serialized `fairness_score` stays the point ratio (0–1).

**Consensus-basis card** — v2 card generated for an opponent with NO real rankings (`basis="consensus"`): divergence math against fabricated Elos is noise, so the engine surfaces simple fair-by-consensus, roster-fit-oriented ideas instead. Clients label them "Fair-value idea". Divergence cards carry `basis="divergence"`.

**Consensus basis (scoring)** — Pricing a trade purely on market-wide DynastyProcess consensus values (`elo_to_value` over the universal-pool seed), with NO personal Elo, NO league, and NO outlook blend. The bottom layer shared by every value surface; the open trade calculator (#27) scores entirely on this basis, while the logged-in engine layers personal Elo and league awareness on top.

**Open trade calculator** — Backlog #27: the public, no-login `web/calculator.html` page + its `POST /api/calc/score` / `GET /api/calc/values` endpoints (flag `calc.open_calculator`). Scores any two asset lists on the consensus basis and renders a #6 verdict, ending on a "connect Sleeper" conversion CTA. The acquisition/SEO front door (the category head term "dynasty trade calculator"); the consensus-only sibling of the session-authed rescore endpoint.

**Manual Trade Calculator (mobile demo)** — `TradeCalculatorScreen` in the mobile Trades stack (reached via the Calculator pill on the Trades tab). Hand-build a trade against a mock leaguemate and see a live dual-**board** fairness verdict + fair-offer suggestions. Runs entirely on seeded demo data (`mobile/src/data/tradeCalcMock.ts` + `utils/tradeCalcMath.ts`) — no league, no network; the server-authoritative replacement is planned in `docs/plans/manual-trade-calculator-plan.md`. Distinct from the **Open trade calculator** (consensus-only web tool).

**Board** — In the calculator UI, one owner's personal ranking set: their value for every player ("Your board" vs "Their board"). A trade reads as agreeable only when both boards like it — the same mutual-gain rule the finder uses.

**Likes-you card** — Tier 2 (`trade.likes_you`): a card whose mirror a league-mate already liked in the last 90 days (and which is still roster-valid). Flagged `likes_you: true`, boosted/pinned to the top of the deck (max 3 injections), rendered with the "👀 They're interested" pill.

**Sweetener** — Tier 3 (`trade_engine.v3`): a low-value asset added to the under-paying side of a *near-miss-fair* trade to bring it into the fairness band. Serialized as `sweetener: {player_id, side}` (the player is already in give/receive); clients render "+ {name} added to balance the deal".

**Thompson deck ordering** — Tier 2 amendment A5 (`trade.thompson_deck`): instead of a learned acceptance model (no training data yet — ~20 labels), the deck order is exploration-randomized by drawing one Beta(1+likes, 2+passes) sample per card *shape* (`1x1`, `2x1`, …) from the user's own decision history and multiplying ordering keys by a bounded (0.5, 1.5) factor. Deterministically seeded per job.

**Deck diversification** — Tier 2 amendment A6 (`trade.deck_diversity`): a player can only be traded once, so one stud saturating every member's deck caps total possible matches. Cards whose top receive asset appeared in ≥ `diversity_user_cap` other members' recent decks get a `diversity_penalty` ordering multiplier, and the served deck keeps ≤ `deck_max_per_target` cards per target (never below 5 cards, never dropping likes-you cards).

**Three-team cycle** — Tier 3 (`trade.three_team`): a kidney-exchange-style cycle A→B→C→A where every team's net marginal surplus clears a bar (`cycle_min_net`); found by clearing a directed gain graph over the league. A distinct card type; all three members must agree.

**Trade scoring** — Composite of mismatch and fairness components, weighted `mismatch_weight=0.70` / `fairness_weight=0.30` (both paths). Legacy path: cards below `min_mismatch_score=40` or above `max_value_ratio=2.5` are filtered; `max_candidates=30` per opponent before sort. v2 path: the mismatch term is the capped harmonic mean of the two sides' surpluses (see *Value space*). Both paths reject cross-side Elo gap > `trade_elo_gap_max=250`.

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
