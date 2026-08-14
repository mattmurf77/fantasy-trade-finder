# FTF Current State — the trade recommender as it runs today

> **Purpose:** file:line map of FTF's trade generation, ranking, and interaction-signal
> systems at HEAD (2026-08-14), produced as the FTF-side input to the X-algorithm audit
> in [audit-x-vs-ftf.md](audit-x-vs-ftf.md). Produced by a code-reading subagent sweep;
> all claims cite code. Supersedes `docs/plans/tiktok-discovery/current-state.md`
> (written pre-F1, now stale).

**Headline finding:** this codebase is *already* an explicit TikTok-clone recommender.
`docs/plans/tiktok-discovery/` (2026-07-26) is a 10-feature port of TikTok's
presentment + models layer, and **9 of 10 features are built and flag-ON in production
today** (only F6, the learned value model, ships dark). Any comparison against X's For
You Page should be framed as "FTF vs FYP" on an existing two-stage retrieval→ranking
system, not as a greenfield gap analysis.

---

## 1. Trade generation pipeline (candidate generation + gating)

### Entry point and orchestration
- Route: `backend/server.py:9727` `POST /api/trades/generate` → spawns background job → `backend/server.py:4653` `_run_trade_job` (the whole serving pipeline lives here, ~900 lines).
- Engine: `backend/trade_service.py:2189` `TradeService.generate_trades` → `:2199` `_generate_trades_impl` → `:2860` `_generate_trades_v2` (flag `trade_engine.v2`, **ON**) → per-opponent `:3243` `_generate_for_pair_v2` **or** `backend/trade_optimizer.py:190` `generate_pair_trades_v3` (flag `trade_engine.v3`, **ON** — so v3 is the live path for ranked opponents) → `:3667` `_generate_consensus_for_pair` for unranked opponents.
- Legacy path (`trade_engine.v2` off) at `trade_service.py:2310-2393` is a dead kill-switch fallback.

### Candidate generation (the "retrieval stage")
Opponent selection — `trade_service.py:2953-2979`:
- Eligible = every other league member with a roster. Optional single-opponent scope (`opponent_user_id`, #156).
- Sort key: **ranked opponents first** (`m.has_rankings and m.elo_ratings`), then by `partner_fit_score` descending. Rationale in comment at `:2969` — divergence cards must not be crowded out of the global budget.
- Global early-exit: `global_target = max(30, max_per_opponent * 6)` (`:2980`).

Per-pair asset pools — `trade_service.py:3548-3583`:
- Give pool = user roster ∩ (has user Elo) ∩ (has opp Elo) **minus `untouchable_ids`** (`:3548`).
- Receive pool = opponent roster, same intersection, **minus `not_interested_ids`** (`:3554`, #163).
- **Divergence prune**: give side kept only if `_vo(p) >= user_value[p] * 0.97` (opponent values it more); receive kept if `user_value[p] >= _vo(p) * 0.97`. Prune is skipped if it leaves <5 (`_PRUNE_MIN_SIZE`, `:3557`).
- Pinned receive players and `target_ids` are re-added post-prune (`:3564-3573`); `pinned_all` (#174) re-adds pinned gives.
- Anchor-first sort: give by `_vo(p) - user_value[p]` desc, receive by `user_value[p] - _vo(p)` desc (`:3582-3583`).

Enumerated shapes:
- **v2 pair path** (`:3585-3628`): 1×1, 2×1, 1×2, 3×2 only. Bounded by `_deadline = time.monotonic() + 1.0` (1s per pair, `:3289`) and `_iter_budget = 200_000` (`:3290`).
- **v3 optimizer** (`trade_optimizer.py:450-470`): all subsets of size 1–3 on both sides from pools capped at `v3_pool_size = 12`, with `abs(len(give) - len(recv)) > 1` skipped. Adds **lineup feasibility** (`_feasible_after`, `:156`) and a **sweetener pass** (`_try_sweeten`, `:607`, band `sweetener_band = 0.15`, `sweetener_max_cards = 2`).
- 3-team cycles exist (`trade_optimizer.py:669 find_three_team_cycles`) but flag `trade.three_team` is **OFF**.
- Owned draft picks are injected as `position="PICK"` pseudo-assets into the pools (flag `trade.picks_in_pool`, **ON**).

### Filters / gates (all hard vetoes, applied in `_consider`, `trade_service.py:3444-3537`)
Order of application:
1. Pinned give/receive membership (`:3445-3452`).
2. `_positions_ok` — hard positional filter from `acquire_positions` / `trade_away_positions` (`:3453`, `:3383`).
3. `_gap_ok` — `trade_elo_gap_max = 250.0` Elo between the top give and top receive (`:3455`, `:3373`).
4. **#108 user-gain gate** — `user_gain_ok_1for1` (`trade_service.py:911`) / `fit_premium_1for1` (`:1568`). A 1-for-1 may never send a player the user ranks above the one received on their **raw pre-shrinkage board**. Threshold `user_gain_epsilon = 0.0`. Exception behind `trade.fit_premium` (**ON**): a raw-board loss up to `fit_premium_max_loss = 300.0` survives if it fills a positional need, and is stamped `card.fit_premium`.
5. **#227 pick-swap gate** — `pick_swap_ok` (`:985`): 1-for-1 pick-for-pick is never emitted.
6. **#141 junk-filler gate** — `filler_ok` (`:938`): every non-headliner piece must clear **both** `filler_min_frac = 0.25` of the side's headliner **and** the absolute floor `asset_floor_abs = 450.0`, priced at `max(user_raw_value, opp_raw_value)`.
7. **Two-sided mutual-gain gate** (`:3516-3520`): `user_surplus = recv_val_user - give_val_user`, `opp_surplus = give_val_opp - recv_val_opp`, both must clear `MIN_SIDE`. With `trade.marginal_value` **ON**, that is `min_side_surplus_marginal = 60.0`; otherwise `min_side_surplus = 150.0`.
8. **Consensus fairness gate** — `_fairness` (`:3397`): point ratio `min(gv,rv)/max(gv,rv)` on consensus package values, passing if either the confidence-derived value **intervals overlap** or the ratio clears the threshold. Divergence cards get the loosened bar `min(caller_threshold, fairness_floor_divergence = 0.55)` (`:3312`); consensus cards keep the full `fairness_threshold` (default 0.75, or 0.50 for pinned/targeted jobs — `server.py:9789`).
9. Consensus path only: **consolidation raw-loss gate** `consolidation_raw_loss_frac = 0.15` (`:3787`).

**#189 relaxed fallback** (`trade_service.py:2412` `_relaxed_targeted_pass`): only fires when a *targeted* job returns zero cards. Stage 1 widens fairness to `relaxed_fairness_threshold = 0.55`; stage 2 additionally drops surplus floors to `relaxed_surplus_floor = 0.0`. **Never relaxed**: `user_gain_epsilon`, untouchables. Cards stamped `relaxed=True` + `relaxed_reason`.

### Mutual gain computation
- Value space: `elo_to_value(elo) = base · exp(k·(elo − ref))` with `elo_value_k = 0.0050`, `elo_value_ref = 1500`, `elo_value_base = 1000` (`trade_service.py:712`).
- Packages priced per side in **that side's own value space** via `package_value_v2` (`:743`) — KTC-style diminishing returns (`package_adj_gamma`), plus a crown/consolidation premium (`crown_rate`, `crown_rate_market = 0.08`, `crown_elite_value = 6000`, `skew_phaseout = 0.5`). Per-user `stud_tax_mode` ∈ {market, heavy, off} switches the shape (`:512-554`).
- Waiver-slot cost: the side receiving more players pays `waiver_slot_cost = 425.0` per extra slot (`:3507-3514`).
- Marginal valuation (flag `trade.marginal_value`, **ON**): each asset priced over the *receiving roster's* per-position replacement level (`replacement_levels`, `:1232`; `marginal_value`, `:1296`) with position/format-specific bench credits (`bench_credit_rb = 0.30`, `bench_credit_qb = 0.10`, `bench_credit_qb_sf = 0.35`, …).
- Confidence shrinkage: `_shrink_user_elo` (`:876`), `w = n/(n + shrink_pseudocount=4)` toward the consensus seed.
- **Ranking key**: `hm = harmonic_mean(user_surplus, opp_surplus)` (`:869`), then `composite = 0.70·min(hm, 1500)/1500 + 0.30·fairness` (`mismatch_weight`/`fairness_weight`), × `_tier_mult_v2` (`tier_mult_elite = 1.60` … `tier_mult_bench = 0.35`, `:2845`).
- Bounded top-K min-heap `K = max_cards × 4` (`:3430`).

### Post-gate composite multipliers (reorder only, never rescue)
All in `_generate_trades_v2`, `trade_service.py:3097-3222`:

| Layer | Flag | Knob | Line |
|---|---|---|---|
| Partner positional fit (FB-47) | `trade.finder_targeting` ON | `fit_consensus_weight 0.5` / `fit_divergence_weight 0.15` | :3101 |
| Automatic need fit (FB-96) | `trade.need_fit` ON | `need_fit_weight 0.15` | :3115 |
| Trade-block boost (FB-147) | `trade.block_boost` ON | `block_boost_weight 0.15` | :3134 |
| Directional outlook (#175) | `trade.outlook_direction` ON | `outlook_dir_penalty 3.0`, `outlook_dir_boost 1.0`, `age_gap_mult 0.15` | :3157 |
| Lane label (window/value) | `trade.lanes` ON | `lane_shift_frac 0.10` | :3168 |
| Aggression A/B | `trade.aggression_ab` ON | `aggression_weight 0.20`; variant from `experiments.variant_overlay(user_id, "trade.aggression")`, MD5 fallback `aggression_variant()` :1559 | :3179 |
| Target acquire bonus (#2) | `trade.preference_lists` ON | `target_acquire_bonus 0.20`, capped `pos_multiplier_cap 2.0` | :3533 |
| Consensus-card down-scale | — | `consensus_score_scale 0.3` | :3812 |

Post-generation **shape filter** `_filter_by_trade_intent` (`:2123`, flag `trades.intent_modes` ON): `consolidate` / `tier_up` / `tier_down` via `RankingService.tier_for_elo` on each side's best asset.

### Ordering / limiting before the client sees it — `_run_trade_job` (server.py:4795-5210)
This is the **ranking stage**, and it is a genuine multiplier stack:
1. Dedup against `_past_decision_keys` + sort by composite (`trade_service.py:2395`).
2. Likes-you injection & pinning (`server.py:2807 _inject_likes_you_cards`, flag `trade.likes_you` ON, cap 3).
3. **F3 fatigue/suppression** (`server.py:3859 _apply_deck_suppression`, `:3797 _deck_fatigue_multipliers`).
4. **F5 taste multipliers** (`backend/taste_service.py:429 taste_multipliers`).
5. **F6 value-model base-key swap** (`server.py:3050 _deck_value_scores`) — flag `deck.value_model` **OFF**, so inert.
6. **`_order_deck`** (`server.py:3344`) — the single ordering function. Key = `composite_score` (or F6 score) × Thompson draw × fatigue × taste × diversity penalty; sorted with `likes_you` pinned first; then `_cap_per_target` (`deck_max_per_target = 3`, floor `_DECK_MIN_CARDS = 5`).
7. **F7 exploration wildcard** inserted at fixed slot (`server.py:4309 _apply_exploration_slot`).
8. **F9 first-session shaping** (`server.py:4518 _apply_first_session_shaping`) — clamp to 8–10 cards, float confidence-passing cards into the top 5.
9. Impression logging: legacy `log_trade_impressions` + **F1** `_log_deck_signal_impressions` (`server.py:3516`).

**Cache:** 30-min per-`(user, league, format)` job cache, keyed on `fairness_threshold` / `outlook_value` / `trade_intent` freshness (`server.py:9829-9849`). Pinned / opponent-scoped jobs bypass. `force: true` and `refresh_fatigue: true` skip it.

**Deck order is deliberately stochastic** — documented at `docs/api-reference.md:216`: "Clients must not assume `cards[0]` is the strict `composite_score` max."

---

## 2. Player valuation / ranking (`backend/ranking_service.py`)

### Elo engine
- `RankingService` is **per-user, per-session, per-scoring-format** (`:180`). Constructed with `seed_ratings` = the global consensus map.
- Input: 3-player trios ranked best→worst, decomposed into all pairwise comparisons (`record_ranking`, `:305`). Threshold to "established": `POSITION_THRESHOLDS = {QB:10, RB:10, WR:10, TE:10, None:16}` (`:194`).
- `_compute_elo` (`:998`): standard Elo `1/(1+10^((rb−ra)/400))`. Two swipe streams: ranking swipes at `elo_k = 32.0`, trade swipes at per-signal K.
- **Manual overrides pin**: any player in `_elo_overrides` (tier saves, drag reorder, anchors) has their Elo frozen; swipes update only the *other* side (`:1023-1047`).

### K-factors (the interaction→valuation feedback loop) — `_DEFAULT_CFG`, `ranking_service.py:55-60`

| Key | Default | Fired from |
|---|---|---|
| `elo_k` | 32.0 | trio swipe |
| `trade_k_like` | 8.0 | `/api/trades/swipe` like → `record_trade_signal`, `server.py:10193` |
| `trade_k_pass` | 4.0 | `/api/trades/swipe` pass, `server.py:10202` |
| `trade_k_accept` | 20.0 | match disposition accept → `record_disposition_signal`, `server.py:13233` |
| `trade_k_decline_correction` | 20.0 | match disposition decline (net ≈ −12 after the +8 like) |

`user_player_skips` ("I don't know this player") deliberately writes **no** Elo (`database.py:953` comment).

### Tiers / pick ladder
- 8-tier **pick-denominated** ladder, `ORDERED_TIERS = ("firsts_4plus","firsts_3","firsts_2","first_1","second","third","fourth","waivers")` (`ranking_service.py:44`). Bands per (format, position) in `backend/tier_config.json`; served via `/api/tier-config` so no client drift.
- `tier_for_elo` (`:1271`), `tier_bands_for` (`:1253`), `apply_tiers` (`:1306`), `DEMOTED_ELO = 1100.0` (`:1304`).
- Generic pick Elo seeds: `backend/pick_values.py:26 GENERIC_PICK_SEEDS` (Mid 1st = 1650 = the base unit), `YEAR_DISCOUNT = 0.85`.

### Global board vs user board
- **Global/consensus board**: DynastyProcess CSV (± KTC blend) → `backend/data_loader.py:96 seed_elo_for_value` maps a 0–10000 value to a seed Elo. Shared by everyone.
- **Per-user board**: `member_rankings` table (`database.py:379`) — per `(user_id, league_id, player_id, scoring_format)` Elo snapshot, replaced atomically on every save. **This is what lets leaguemates see each other's valuations** and is the entire divergence signal.
- Blend at generation time: `_shrink_user_elo` pulls sparse personal Elos toward consensus; `_value_uncertainty` (`trade_service.py:899`) = `range_base(0.35)/sqrt(1+n)` drives the fairness interval-overlap test.
- Opponents without real boards (`has_rankings=False`) are **never** used for divergence math — they get labeled `basis="consensus"` cards (`trade_service.py:1972-1975`, `:3690`).

### Personalization that exists today in the *valuation* layer
1. Personal Elo board (trios / tiers / anchors / manual reorder).
2. Trade-swipe Elo feedback (K = 4/8/20).
3. Outlook α blend `outlook_alpha_championship 1.00` … `outlook_alpha_jets 0.10` — **but flag `trade.outlook_blend` is OFF**, so today outlook affects *labels and composite multipliers*, not values (`trade_service.py:2988` comment: "labels stay, value edits don't").
4. Per-user `stud_tax_mode` and `pick_pricing_mode` settings.
5. F5 taste vectors — but those live in the *ordering* layer, not the valuation layer.

---

## 3. Team / roster analysis

- `analyze_roster_strengths` (`trade_service.py:1033`): bins each player by dynasty value into elite ≥4000 / starter ≥1500 / bench ≥500 (`_TIER_ELITE/_TIER_STARTER/_TIER_BENCH`, `:1014-1016`); derives `position_needs` (below `_STARTER_NEED = {QB:1,RB:2,WR:2,TE:1}`, QB→2 in superflex) and `position_surplus` (at/above `_SURPLUS_AT = {QB:2,RB:4,WR:4,TE:2}`).
- `partner_fit_score` (`:1099`) — counterparty fit for user-*stated* targets, 0..1.
- `need_fit_score` (`:1132`) — automatic per-card fit, no user input required, 0.5 = neutral.
- `build_match_context` (`:1672`) — the "why this match" object on each card.
- **Contender/rebuild window detection**: `infer_team_outlook` (`:1603`) — value-weighted vet share (age ≥ `vet_age 27`), youth share (≤ `youth_age 26`), and pick-capital share centered on `1/num_teams`; weights `infer_w_vet_share 1.0`, `infer_w_youth_share 1.0`, `infer_w_pick_share 2.0`; cuts `infer_contender_cut 0.08` / `infer_rebuilder_cut −0.08`. Deliberately never infers the extremes (`championship`/`jets`).
  - Applied to **opponents** at `trade_service.py:3003-3015` (flag `trade.outlook_infer` ON), and to the **user** at `server.py:4631 _infer_user_outlook` (flag `trade.outlook_seed` ON) when no declared outlook exists in `league_preferences`.
- `replacement_levels` / `marginal_value` (`:1232`, `:1296`) — roster-construction-aware valuation (starter slots per format, bench credit rates).
- v3-only: **lineup feasibility** hard gate `_feasible_after` (`trade_optimizer.py:156`) — a trade can't break either roster's ability to field a lineup.
- `backend/power_rankings.py` — full-roster value ranking with Sleeper `roster_positions` starters/bench split. Flag `league.power_rankings` **OFF** for the league page; `/api/league/summary` uses parts of it.
- `backend/outlook/` — a full playoff/championship-odds Monte Carlo (`simulator.py`, 10k sims, `strength.py`, `playoff_format.py`). **Flag `outlook.odds` is OFF (404)**, and it **does not feed trade suggestions at all**.

---

## 4. User interaction data

### 4a. The analytics event system (`user_events`) — instrumentation, NOT a feedback loop
- Registry: `backend/analytics_taxonomy.py`. Three frozensets, disjointness asserted at import:
  - `ALLOWED_CLIENT_EVENTS` (`:38`) — 76 names. Includes `screen_viewed`, `screen_left` (with `dwell_ms`), `find_trades_tapped`, `trade_card_viewed`, `trade_flagged`, `match_opened`, `deck_card_viewed`, `swipe_undone`, `deck_reranked`, `first_session_like/_deck_completed/_adaptation_shown`, `notif_inbox_opened/_row_tapped/_empty_state_shown`, `league_candidate_pinned`, `experiment_exposed`, …
  - `SERVER_FIRED_EVENTS` (`:270`) — `trio_swipe`, `tier_save`, `anchor_answered`, `trade_proposed`, `match_swiped`, `trade_accepted/declined/ratified`, `trades_generated`, `sleeper_send_succeeded`, `trade_sent`, `trade_responded`, `asset_pref_added/removed`, `api_call`/`api_request`, `pick_assignment_changed`, …
  - `FUNNEL_CRITICAL` (`:352`) — 4 names retained under SDK queue overflow.
  - `CLIENT_EVENT_PROPS` (`:370`) — per-event prop allowlist; unknown props stripped and counted.
- Ingest: `backend/analytics_ingest.py` → `POST /api/events` (`server.py:7104`). Always-200 accounting contract; validation, dedupe on `event_id`, PII scrub (`_scrub_pii`, `:189`), rate limit (`analytics_events_per_hr`, fallback 600), `MAX_BATCH = 50`.
- **Flags today: `analytics.ingest` = TRUE and `analytics.client_events` = TRUE** (`config/features.json`). ⚠️ `backend/analytics_queries.py:23` still says *"Reality today (analytics.ingest=false): user_events holds only SERVER-fired…"* — that comment is **stale**.
- Storage: `user_events` (`database.py:1075`) — `user_id, event_type, occurred_at, league_id, session_id, device_type, os_version, app_version, source, props(JSON), event_id, device_id, platform, screen, client_ts, experiments(JSON), country`. Indexes `(user_id,occurred_at)`, `(event_type,occurred_at)`, unique `event_id`, `(device_id,occurred_at)`. `identity_links` (`:1110`) stitches pre-auth `device:<id>` rows to a signed-in identity.
- Dual-write: `record_event` also bumps `users.last_*_at`, `events_count`, and the rank streak (`architecture.md:234-241`).

**Do `user_events` feed trade suggestions or rankings? NO.** The only `user_events` readers are:
- `database.py:3330 _rank_action_counts` — ranking streak / league activity leaderboard.
- `database.py:6081` — league activity feed narrative.
- `database.py:7927` — `pick_assignment_changed` audit trail (contested-pick derivation).
- `backend/analytics_queries.py` — 15 admin reports served read-only at `/api/admin/analytics/<report>`, rendered by `web/admin/analytics.html`.
- `backend/experiments.py` — assignment/exposure.

**Instrumentation bug worth flagging:** 28 event names are `track()`ed by the mobile client but are **absent from `ALLOWED_CLIENT_EVENTS`**, so they are silently counted-and-dropped behind a 200. Directly relevant ones: `untouchable_toggled` (TradesScreen.tsx:944), `trade_keep_side_tapped` (:2091), `trade_pin_cleared` (:2123), `suppression_undo_tapped` (:2134), `trade_edit_in_calculator_tapped` (:2154), `deck_summary_viewed` (:2800), `trade_swap_suggest_opened`, `trade_asset_removed`, `player_menu_opened`, `stud_tax_mode_changed`, `pick_pricing_mode_changed`, plus `push_primer_*`, `help_*`, `prompt_shown`, `quickset_completed`, `match_dismiss_undone`, `calc_clear_undone`, `demo_bridge_tapped`, `guide_tour_reenabled`, `rating_prompt_requested`, `notif_denied_settings_*`, `apple_banner_dismissed`. The taxonomy file's own docstring calls this exact trap out.

### 4b. The deck signal spine (`deck_impressions` / `deck_outcomes`) — this IS the feedback loop
Completely separate from `user_events`. Flag `deck.signal_v2` **ON**.

**`deck_impressions`** (`database.py:481`) — one row per card in **final served order**, once per completed job:
`impression_id (uuid4 hex PK), user_id, league_id, deck_job_id, card_index, trade_hash, features_json, propensity, base_score, final_score, archetype, shape_bucket, served_at, centerpiece_id`.
`features_json` is **frozen at serve time** (`server.py:3570-3629`): shape, basis, likes_you, lane, give/receive positions, give/receive values + 500-wide bands, `involves_pick`, `partner_user_id`, `surplus_margin`, `fairness_score`, `need_fit`, `partner_fit`, `fit_premium`, `aggression_variant`, `relaxed`, plus board-state-at-serve (`ranked_player_count`, `last_board_update_at`, `user_value_basis`), plus conditional `deck_source` (F10), `taste_attrs` (F5), `wildcard`/`wildcard_pool_size`/`wildcard_provenance` (F7), `first_deck` (F9).
`propensity` = the Thompson multiplier actually applied (or the F7 uniform-draw probability) — the off-policy-evaluation prerequisite.

**`deck_outcomes`** (`database.py:518`) — append-only labels, joined by `impression_id`:
`action ∈ viewed | like | pass | not_interested | propose | undo`, `dwell_ms` (capped 120s), `detail_expanded`, `calc_opened`, `acted_at`.
Write sites, all via `server.py:3657 _save_deck_outcome_safe`:
- `POST /api/trades/swipe` → `like`/`pass` + `dwell_ms`/`detail_expanded`/`calc_opened` (`server.py:10214`)
- `POST /api/trades/flag` → `not_interested` (`server.py:10519`)
- `POST /api/trades/propose` → `propose`
- `POST /api/events` side-channel → `deck_card_viewed` → `viewed` (≥500ms front-of-deck) and `swipe_undone` → `undo` (`server.py:7132-7152`). **This scan runs before taxonomy filtering**, so it is independent of `analytics.ingest`.

Client capture: `mobile/src/screens/TradesScreen.tsx:1619-1660` — `dwellRef` timer with background pause/resume, `engagementRef.detailExpanded/calcOpened`, cap constants at `:178`.

**Legacy `trade_impressions`** (`database.py:442`) still written in parallel (`server.py:5162`) — generation-time rows with no shared key to `trade_decisions`; superseded by the F1 spine.

**`trade_decisions`** (`database.py:308`) and **`swipe_decisions`** (`:296`) are the Elo-lineage audit trail.

### 4c. What event data actually feeds back into suggestions today

| Loop | Mechanism | Flag | Code |
|---|---|---|---|
| Swipe → player Elo | like/pass/accept/decline pairwise Elo at K=8/4/20/20 | always | `ranking_service.py:334`, `:367`; `server.py:10193`, `:13233` |
| Shape-bandit ordering (v1) | Beta(1+likes, 2+passes) per `"GxR"` shape from `trade_decisions` | `trade.thompson_deck` ON | `server.py:3422-3443` |
| **Bandit v2** | pessimistic prior Beta(1, 1/p̂) at the trailing-30d **global** like rate; per-day decay γ=0.995; **viewed-gated** counts (cascade fix); arms = archetype×shape with parent warm-start | `deck.thompson_v2` ON | `server.py:3177`, `:3221`, `:3282`, `:3305` |
| **Fatigue** | per-user `w1·exp(−a·impCount) + w2·exp(−b·daysSince)` over **viewed** impressions, keyed on trade_hash / centerpiece / archetype (min, never product); 2+-pass session demotion ×0.2; floor 0.25 | `deck.fatigue` ON | `server.py:3745`, `:3797` |
| **Durable decline suppression** | 30-day near-duplicate ban (same centerpiece + shape + value ±10%) with one low-exposure retest, user-liftable via `POST /api/trades/suppressions/undo` | `deck.fatigue` ON | `database.py:545`, `server.py:3859`, `:3990` |
| **Taste vectors** | per-user decayed attribute prefs (τ_short 21d / τ_long 180d), rewards like +1 / propose +6 / accept +4 / pass −0.5 / decline −2 / not_interested −4 / long-dwell +0.3; bounded re-rank clamp [0.7, 1.4]; **board-derived prior** rewritten on every board save | `deck.taste_vectors` ON | `backend/taste_service.py`, `database.py:609` |
| **Session re-rank (client)** | after each disposition, remaining unseen cards re-sort by `1/(servedIdx+1) × (1 + 0.3·cos(attrs, boost))`; last-k=10, decay 0.8; like +1 / long-dwell(>8s) pass +0.3 / fast(<2s) pass −0.5 / not_interested −2 | `deck.session_rerank` ON | `mobile/src/utils/sessionRerank.ts` |
| **Exploration / audition** | 1 labeled `wildcard` per deck ≥8 cards at slot 4–6, drawn from bottom taste tercile → low-data arms → uniform; global archetype staging (test/general/retired) at `audition_min_views=30` | `deck.exploration` ON | `server.py:4201`, `:4309`, `:4109`; `database.py:633` |
| **League diversity** | targets shown to ≥3 other members in 7d ×0.6; intra-deck cap 3/target | `trade.deck_diversity` ON | `server.py:3461-3488` |
| **First-session shaping** | first deck per league clamped 8–10, confidence-passing cards floated to top 5 | `deck.first_session` ON | `server.py:4481`, `:4518` |
| **Trade block** | counterparty's Sleeper "on the block" flags → +15% acquire-side | `trade.block_boost` ON | `trade_service.py:3134` |
| Declared prefs | untouchable / target / not_interested hard filters + target bonus | `trade.preference_lists` ON | `server.py:13617`, `trade_service.py:3548`/`:3554`/`:3533` |
| **Learned P(like)/P(propose)** | two Platt-calibrated logistic heads, `rank_score = P(like)·V_like + P(like)·P(prop|like)·V_propose`, replaces `composite_score` as `_order_deck`'s base key | `deck.value_model` **OFF (dark)** | `backend/value_model.py`, `server.py:3037`, `:3050` |
| Offline eval | SNIPS/IPS replay over propensity logs, cluster bootstrap over deck jobs, ESS gate | operator tooling | `backend/eval/replay.py`, `nightly.py`, `scorers.py` |

### 4d. Feedback items, want/accept boards, notification inbox, dismiss/hide
- **`bad_trade_flags`** (`database.py:917`) — the explicit "the engine got this wrong" signal from the deck. Snapshots the package, counterparty, free-text `reason`, and engine telemetry at flag time (`mismatch_score`, `fairness_score`, `composite_score`, `need_fit`, `partner_fit`, `basis`). Idempotent on `dedupe_key`. **Consumers: operator readback only** (`GET /api/trades/flags/admin`, `server.py:10530`) — no automated learning loop reads this table. It *does* additionally write a `not_interested` `deck_outcomes` row, which is what actually feeds taste/session-rerank.
- **`app_feedback`** (`database.py:865`) — in-app notes, `severity ∈ bug|polish|idea`, `status ∈ new|planned|in_progress|fixed|shipped|declined`. Purely a product backlog surface; feeds nothing algorithmic.
- **Want/accept boards** = `asset_preferences` (`database.py:712`), `list_type ∈ untouchable | target | not_interested`, one tag per player per league. Add/remove writes `asset_pref_added` / `asset_pref_removed` to `user_events` — explicitly labeled "label stream for the deferred acceptance model (#65)" (`server.py:13645`) — **currently unread by any model**. `league_preferences` (`:684`) holds `team_outlook`, `acquire_positions`, `trade_away_positions`.
- **Notification inbox**: `notifications` (`database.py:835`) with `is_read` and `dismissed_at`. Routes `/api/notifications`, `/read`, `/read-all`, `/dismiss-all` (`server.py:15399-15496`). Client events `notif_inbox_opened` / `notif_row_tapped` / `notif_empty_state_shown` registered 2026-08-13 with **no emitters yet at registration time**. **No inbox interaction feeds ranking.** `notification_events_log` is used for push dedup only.
- **Dismiss/hide on trade cards**: there IS no separate "dismiss/hide" affordance. The negative surface is: `pass` swipe, the bad-trade **flag** (= `not_interested`), and the per-player `untouchable` toggle from the card's give-side context menu (`TradesScreen.tsx:944`). Match tiles have a separate Elo-neutral `POST /api/trades/matches/<id>/dismiss`.
- **No thumbs-up/down.** No star rating, no "show me less like this" control beyond flag + untouchable + not_interested.
- Undo exists (`swipe_undone` → `undo` outcome appends alongside the original, never replaces).

---

## 5. Data we hold per user (platform sync)

### Sleeper — the only platform with meaningful ingestion breadth
Endpoints actually called (`git grep` inventory over `backend/`):

| Endpoint | Purpose | Code |
|---|---|---|
| `/user/{username}`, `/user/{id}/leagues/nfl/{year}` | identity + league list | `server.py:14214`, `:14267` |
| `/league/{id}` | settings, `roster_positions`, `total_rosters`, `draft_rounds` | `server.py:688` |
| `/league/{id}/rosters` | rosters (player id lists) | `server.py:14343` |
| `/league/{id}/users` | display names/avatars | `server.py:14374` |
| `/league/{id}/traded_picks` | pick ownership overlay | `server.py:10583` |
| `/league/{id}/drafts` | draft status/order | `server.py:10602` |
| `/players/nfl` (bulk), `/players/nfl/adp` | canonical player table | `server.py:1648`, `:606` |
| **`/league/{id}/transactions/{week}`** | **executed trades** | `backend/sleeper_trades_service.py:61` |
| `/league/{id}/matchups/{week}` | schedule + weekly scores | `backend/outlook/league_state.py:260` |
| GraphQL `league_players` | trade-block `otb` flags | `backend/trade_block_service.py` |

### Do we ingest league transaction history? — Partially, and it is dead data.
**YES for trades:** `backend/sleeper_trades_service.py` sweeps legs 1–18 on every `session_init` background daemon pass (flag `market.trade_capture`, **ON**; called at `server.py:15283`), and stores rows in `sleeper_trades` (`database.py:359`): `transaction_id, league_id, week, traded_at, synced_at, roster_ids, adds, drops, draft_picks, waiver_budget, raw` (full payload retained). Idempotent on `transaction_id`.

**NO for everything else:** `parse_trade_transactions` (`sleeper_trades_service.py:93`) hard-filters `t.get("type") != "trade" or t.get("status") != "complete"`. **Waiver claims, free-agent adds/drops, and FAAB-only moves are fetched from the API and thrown away.**

**And nothing reads the trades.** `load_sleeper_trades` (`database.py:5676`) has **zero callers** outside `database.py` — no route, no service, no model. The module docstring and `data-dictionary.md:248` both state "Capture ONLY — no scoring, no aggregation, no UI… this table exists so a future observed-market model has raw material accumulating from today." Confirmed by grep: no consumer.

**Matchups**: fetched only by `backend/outlook/league_state.py`, only when the `outlook.odds` flag is on — and it is **OFF** (route 404s at `server.py:20402`). So in production we currently ingest **no** matchup/standings data. Nothing about wins/losses/points-for informs a trade suggestion.

### MFL / ESPN / Fleaflicker
`grep -n "transactions|waiver|freeagent|matchup"` across `backend/mfl_service.py`, `espn_service.py`, `fleaflicker_service.py` returns **nothing**. These integrations sync rosters, league settings, members, and (MFL) `futureDraftPicks` only. There is a *write* surface (`propose-mfl`, `respond-mfl`, `propose-espn`) but no history read.

### Full per-user data inventory
Rosters (`league_members.roster_data`), leagues (`leagues`), member Elo boards (`member_rankings`), swipes (`swipe_decisions`), trade decisions (`trade_decisions`), matches (`trade_matches`), pick ownership (`draft_picks`, `recorded_picks`), preferences (`league_preferences`, `asset_preferences`), skips (`user_player_skips`), Elo history (`elo_history`), notifications + device tokens + prefs, credentials, accounts/sessions/identities, feedback, deck signal tables, taste vectors, experiment assignments, entitlements, mock drafts, rank sets.

---

## 6. Relevant docs — what's already planned vs built

### `docs/plans/tiktok-discovery/` — the pre-existing FYP comparison
- `research/tiktok-presentment.md` and `research/tiktok-models-layer.md` — sourced research on TikTok's UX + ranking stack.
- `current-state.md` — file:line map at HEAD `786f63d`. **Now substantially stale** — it describes the pre-F1 world.
- `gap-analysis.md` — 16 mechanisms scored ✅/🟡/❌/🚫. Key 2026-07-26 verdicts: #2 impression↔outcome join ❌ ("the foundational gap"), #3 dwell ❌, #4 value model ❌, #5 interest vectors ❌, #6 session freshness ❌, #7 bandit hygiene 🟡, #8 exploration ❌, #9 fatigue 🟡, #15 offline eval ❌, #16 compulsion mechanics 🚫 ("correctly absent — keep it that way").
- `backlog.md` — 10 features RICE-scored, wave plan, and **5 standing guardrails**: (1) north star = proposals-sent + matches-accepted per weekly-active, session minutes are a *cost*; (2) no control theater; (3) no fake-infinite inventory; (4) quality gates never relax for engagement; (5) no label hand-boosts.
- `prds/F1…F10` — build-ready specs.

**Status vs plan (verified against `config/features.json`):**

| PRD | Flag | Built? | Live? |
|---|---|---|---|
| F1 signal foundation | `deck.signal_v2` | yes | **ON** |
| F2 Thompson v2 | `deck.thompson_v2` | yes | **ON** |
| F3 fatigue/suppression | `deck.fatigue` | yes | **ON** |
| F4 session re-rank | `deck.session_rerank` | yes (client-side) | **ON** — note `backend/feature_flags.py:422` still comments "reserved (no consumer yet)"; the consumer is `mobile/src/utils/sessionRerank.ts` |
| F5 taste vectors | `deck.taste_vectors` | yes | **ON** |
| F6 value model | `deck.value_model` | **yes, fully built** (`backend/value_model.py`, 812 lines) | **OFF — ships dark** pending an F8 replay win |
| F7 exploration slots | `deck.exploration` | yes | **ON** |
| F8 offline eval | (operator tooling, unflagged) | yes (`backend/eval/`) | **runs nightly** inside `/api/cron/daily-tick` (`server.py:16600`), idempotent per (UTC day, scorer, window); results in `data/eval_runs/runs.jsonl`. The F6 nightly refit sits right after it (`:16618`) but is flag-gated, so it never runs while `deck.value_model` is off |
| F9 first-session win | `deck.first_session` | yes | **ON** |
| F10 replenishment | `deck.replenishment` | yes | **ON** |
| F11 intent knobs | — | shipped as `trades.intent_modes` (#172) | **ON** |

### Other docs
- `docs/architecture.md:188-202` "Request lifecycle (trade card — v2 engine)" — **stale**: stops at Thompson + `trade_impressions`; never mentions F1/F3/F5/F7/F9. `:129` also calls `trade_service.py` "~2.1k" lines (it's 4373). `:153` describes F6 accurately.
- `docs/data-dictionary.md` — **current and detailed** for the new tables: `sleeper_trades` (`:246`), `trade_impressions` (`:307`), `deck_impressions` (`:331`), `deck_outcomes` (`:356`), `deck_suppressions` (`:374`), `user_taste` (`:427`), `archetype_auditions` (`:441`), `bad_trade_flags` (`:949`), `user_events` (`:696`).
- `docs/config-reference.md:440-500` — every deck knob documented. Note it lists all `deck.*` flags as "default false", which is the `feature_flags.py` default, not the deployed `config/features.json` value.
- `docs/api-reference.md:198-280` — Trades section exhaustive and current, incl. the "deck order is not strictly score-sorted" warning at `:216`. Analytics endpoints at `:688-737` (section header still says "ships dark", now wrong).
- `docs/adr/adr-002-trade-engine-v2-v3-rebuild.md`, `adr-007-first-party-analytics-experimentation.md`.
- `docs/business/analytics/2026-07-17-tracking-plan-v2.md` + addenda — the event taxonomy's governing spec.
- `docs/plans/analytics-platform/{prd,hld,lld}.md` + reconciliation logs.
- `docs/reviews/trade-engine-deep-dive.md`, `trade-engine-external-research.md`, `docs/plans/trade-logic-interview-2026-07-17.md` (source of many current thresholds), `docs/plans/trade-engine-tier{1,2,3}-*.md`.

---

## 7. Explicit absences (inputs to the gap analysis)

**Retrieval / candidate generation**
- No embedding-based or ANN retrieval. Candidate generation is exhaustive combinatorial enumeration over two rosters (≤3 assets/side), pruned by a 0.97 divergence heuristic and a 1-second-per-pair deadline.
- No cross-league or cross-user collaborative retrieval. The only collaborative signal is `likes_you` (exact/fuzzy mirror match) and the league-level diversity counter.
- No 3-team trades in production (`trade.three_team` OFF).
- Candidate pool never exceeds a single league.

**Ranking**
- **No learned ranker in production.** `composite_score` is 100% hand-tuned — ~130 config keys in `trade_service._DEFAULT_CFG`. F6 exists but is dark.
- No multi-objective `Σ P(action)·V(action)` in the live path; the V-vector (`V_LIKE_DEFAULT 1.0`, `V_PROPOSE_DEFAULT 6.0`, `value_model.py:84`) is only reachable with the flag on.
- No calibration/debiasing in the live ranking (position debias exists train-only inside F6).
- No real-time model updates. Taste vectors update synchronously on outcome write, but the *ranker* is static config.

**Signals not captured**
- No scroll depth, no per-element impression tracking, no video/media analogue.
- No implicit signal from the calculator, tiers, trends, or draft screens feeds the deck (their events are dropped or analytics-only).
- Waiver/FA transaction history: fetched and discarded.
- Matchups / standings / points-for: not ingested in production.
- No social graph beyond league membership; no follows.

**Feedback loops that do not close**
- `user_events` → nothing algorithmic (analytics-only).
- `bad_trade_flags` → operator review only (the algorithmic effect rides the parallel `deck_outcomes` `not_interested` row).
- `sleeper_trades` (executed market trades) → nothing. `load_sleeper_trades` has zero callers.
- `asset_pref_added/removed` label stream → written "for the deferred acceptance model (#65)"; unread.
- Notification inbox interactions → nothing.
- `trade_impressions` (legacy) → nothing (superseded by F1; still written).

**Affordances that don't exist**
- No dismiss/hide on a trade card (pass + flag + untouchable are the negatives).
- No thumbs-up/down, no explicit rating, no "less like this".
- No per-card "why am I seeing this" explanation surface (`reasons[]` and `narrative` explain the *trade*, not the *ranking*).
- No user-facing control over the ranking layers (only `refresh_fatigue`, the suppression undo, and the declared preference lists).
