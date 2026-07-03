# Config Reference

Environment variables, feature flags, and `model_config` keys. Keep in sync when adding any of the three (see [docs/CLAUDE.md](CLAUDE.md)).

---

## Environment variables

| Var | Used by | Purpose |
|---|---|---|
| `DATABASE_URL` | `backend/database.py` | Postgres connection string. Unset → SQLite at `data/trade_finder.db` |
| `ANTHROPIC_API_KEY` | `backend/smart_matchup_generator.py` | Enables Claude-assisted matchup selection; unset → algorithmic fallback |
| `FTF_FLAGS` | `backend/feature_flags.py` | JSON dict of process-level feature-flag overrides (wins over `config/features.json`) |
| `CRON_SECRET` | `backend/server.py` | Shared secret (`X-Cron-Secret` header) for all operator endpoints: `/api/cron/*`, `/api/feedback/admin/*`, `/api/admin/*` (config + engine-metrics), `/api/debug/log`, `/api/feature-flags/reload`. In a non-SQLite (prod) env these **fail closed** (503) when it's unset; in SQLite dev an unset secret disables the check. Compared with `hmac.compare_digest`. |
| `SCORING_FORMAT` | `backend/server.py` | Default scoring format override |
| `SLEEPER_TOKEN_KEY` | `backend/sleeper_write.py` | Fernet key encrypting stored Sleeper write tokens (`trade.send_in_sleeper`). Unset/invalid → the link + propose routes fail closed (503 `sleeper_unconfigured`). Generate with `cryptography.fernet.Fernet.generate_key()`; set in `secrets.local.env` + Render. |

---

## Feature flags

Source of truth: `config/features.json`. Every key defaults to **false** in `backend/feature_flags.py` (`FLAG_KEYS` / `DEFAULT_FLAGS`); flipping a value in the JSON (or `FTF_FLAGS`) enables it. Reload at runtime via `POST /api/feature-flags/reload`.

Pre-existing flags (sprint UX + trade-math): see `config/features.json` directly — they are self-describing (`swipe.*`, `tiers.*`, `trades.*`, `league.*`, `invite.*`, `mobile.*`, `profiles.*`, `landing.*`, `trade_math.*`).

### Player profiles (#17)

| Flag | Default | Gates |
|---|---|---|
| `players.profile_pages` | false | `GET /api/players/<id>/profile` (404 when off) and web player-name linkification (`playerLink` in `web/js/app.js` → `web/player.html`). The daily `POST /api/cron/value-snapshot` job that feeds the profiles runs **unflagged** — it is data retention and must collect history before the UI ships. |

### Trade engine flags (Tier 1–2, landed — all currently **true** in `config/features.json`)

| Flag | Tier | Gates |
|---|---|---|
| `trade_engine.v2` | 1 | The entire v2 scorer (`trade_service._generate_trades_v2`): single value space (`elo_to_value`), `package_value_v2`, both-sides surplus gate + harmonic-mean ranking, waiver-slot cost, confidence shrinkage, range-overlap fairness, top-K heap, consensus-basis cards. Off → legacy scorer, byte-for-byte unchanged |
| `trade.marginal_value` | 2 (2.1) | Over-replacement (marginal) valuation inside the v2 pair loop; switches the per-side gate to `min_side_surplus_marginal` |
| `trade.outlook_blend` | 2 (2.2) | Now/future age-curve blend applied to the user's value map (α from `outlook_alpha_*`). Replaces the deleted `team_outlook_multiplier`. v2-only; legacy ignores outlook |
| `trade.likes_you` | 2 (2.3a) | Likes-you queue: inject/boost cards whose mirror a league-mate already liked (`server._inject_likes_you_cards`, cap 3 per deck) |
| `trade.fuzzy_match` | 2 (2.3b) | Jaccard ≥ `fuzzy_match_tau` mirror matching in `database.check_for_match`, guarded so only low-value players (`search_rank ≥ 120`) may differ |
| `trade.thompson_deck` | 2 (A5) | Thompson-sampled deck ordering: one Beta(1+likes, 2+passes) draw per card *shape* (e.g. `2x1`), bounded (0.5, 1.5) multiplier on the ordering key (`server._order_deck`) |
| `trade.deck_diversity` | 2 (A6) | League-wide diversification: penalize cards whose top receive asset saturates other members' recent decks; intra-deck cap `deck_max_per_target` |

### Trade engine flags (Tier 3, flag-gated — landing imminently, default **false**)

| Flag | Gates |
|---|---|
| `trade_engine.v3` | `backend/trade_optimizer.py` — exact per-pair package search + sweetener pass. Off → falls back to v2 (then legacy if `trade_engine.v2` is also off) |
| `trade.three_team` | 3-team cycle trades (kidney-exchange-style clearing) in `trade_optimizer.py` |
| `trade.finder_targeting` | FB-47 ([plan](plans/trade-finder-targeting.md)): `pinned_receive_players` ("I want to acquire X") + counterparty positional-fit ranking (`partner_fit` on cards, `fit_consensus_weight` / `fit_divergence_weight` composite blend) |
| `trade.outlook_infer` | Backlog #1 ([plan](plans/competitor-top20/01-opponent-outlook-classifier.md)): price each opponent's side of a trade through *their* contend/rebuild α instead of the `not_sure` 0.50 default. Per opponent: declared `league_preferences.team_outlook` → `infer_team_outlook` (roster age/value/pick-share signals) → `not_sure`. Blends `_vo` in `_generate_for_pair_v2` + `generate_pair_trades_v3` (propagates to marginal/replacement paths); stamps `match_context.opponent_outlook`. **Requires `trade.outlook_blend` ON** (supplies the multiplier); no-op otherwise. Consensus-basis cards stay market-neutral by design. Default **false**. New `model_config` keys: `infer_w_vet_share` (1.0), `infer_w_youth_share` (1.0), `infer_w_pick_share` (2.0), `infer_contender_cut` (0.08), `infer_rebuilder_cut` (-0.08). |
| `trade.preference_lists` | Backlog #2 ([plan](plans/competitor-top20/02-asset-preference-lists.md)): per-player **untouchables** (hard give-side filter — dropped from `_known_user`/`known_user` pools + sweetener candidates in all gen paths) and **targets** (survive the divergence prune + a capped composite reward). Stored in `asset_preferences`; loaded into `_run_trade_job` and passed as `untouchable_ids`/`target_ids`. Default **false**. New `model_config` key: `target_acquire_bonus` (0.20), capped by `pos_multiplier_cap` (2.0). |
| `trade.outlook_seed` | Backlog #8 ([plan](plans/competitor-top20/08-per-league-outlook.md)): leagues with **no declared `team_outlook`** are seeded with `infer_team_outlook` run on the *user's own* roster (`_infer_user_outlook` in `server.py`), resolved identically in the generate-route cache pre-read and the worker so the job-cache key agrees. `GET /api/league/preferences` adds `inferred_outlook` + `inferred_signals` (additive) for the one-tap confirm UI. Nothing is persisted — recomputed per request, so roster drift self-corrects. Declared rows always win. Requires `trade.outlook_blend` ON for the α to matter. Default **false**. No new config keys (reuses #1's `infer_*`). |
| `trade.crown_asset` | Backlog #10 ([plan](plans/competitor-top20/10-key-asset-package-adjustment.md)): key-asset consolidation premium in `package_value_v2`. The top asset of a *smaller-count* side (consolidation side) is priced up by `crown_rate · (share − floor)/(1 − floor)` where `share = v_top / Σ side`. Provably **neutral on equal-count trades** (1-for-1, 2-for-2) via an `n_other` guard, so flag-off and symmetric trades are byte-identical. Closes the 1-for-1 fairness-gate watch item the FPTrack/Dynasty-Daddy way (explicit multiplier, not a hard gate). Default **false**. New `model_config` keys: `crown_rate` (0.12), `crown_share_floor` (0.50). |
| `calc.open_calculator` | Backlog #27 ([prd](../staged-work/backlog-21-30/prds/27-open-trade-calculator.md)): gates the **public, no-session** open-trade-calculator compute routes `POST /api/calc/score` + `GET /api/calc/values` (both 404 when off). The static `web/calculator.html` SEO page ships **unflagged** (like `faq.html`); when the flag is off its Score button degrades to a "coming soon" state via the self-fetched `/api/feature-flags`. No new endpoint config keys — reuses the backlog #6 `verdict_*` `model_config` keys for band thresholds so the public calc and in-app trade cards agree on the same trade. Default **false**. |

### Send in Sleeper (flagged beta)

| Flag | Default | Gates |
|---|---|---|
| `trade.send_in_sleeper` | false | ⚠️ **ToS-adverse.** `POST/GET/DELETE /api/sleeper/link` + `POST /api/trades/propose` (all 404 when off) — sends trades through Sleeper's *undocumented* private write API (`propose_trade` GraphQL mutation). Requires `SLEEPER_TOKEN_KEY`. Adapter: `backend/sleeper_write.py`; token store: `sleeper_credentials`. Capture + ToS/risk (C4): [runbook](plans/sleeper-write-capture-runbook.md). |

---

## `model_config` keys

Two layers, both read through `trade_service._cfg` at runtime:

1. **DB-seeded keys** — `_MODEL_CONFIG_DEFAULTS` in `backend/database.py` seeds the `model_config` table (INSERT OR IGNORE on startup). Tunable live via `PUT /api/admin/config/<key>`.
2. **Code-default keys** — the trade-engine v2/Tier-2 keys below are declared only in `trade_service._DEFAULT_CFG` (and `fuzzy_match_tau` inline in `server._fuzzy_match_tau`). They are **not yet seeded into the `model_config` table**, and `database.set_config` rejects unknown keys — so until they're added to `_MODEL_CONFIG_DEFAULTS`, the admin API cannot tune them and the code defaults below are what runs.

Legacy keys (Elo K-factors, KTC curve, package weights, outlook multipliers, tier multipliers, trade-math taxes, tier-engine knobs) are documented in [glossary.md](glossary.md) and listed by `GET /api/admin/config`.

### Trade engine v2 (Tier 1) — `trade_service._DEFAULT_CFG`

| Key | Default | Meaning |
|---|---|---|
| `elo_value_k` | 0.0050 | Steepness of the Elo→value curve `value = base · exp(k · (elo − ref))` |
| `elo_value_ref` | 1500.0 | Elo that maps to the reference value |
| `elo_value_base` | 1000.0 | Value at the reference Elo |
| `package_adj_gamma` | 1.5 | Exponent in the KTC-style per-asset contribution `v · (0.15 + 0.85 · (v/v_max)^γ)` (`package_value_v2`) |
| `min_side_surplus` | 150.0 | Min per-side value gain (raw values) for a trade to surface |
| `min_side_surplus_marginal` | 60.0 | Replacement gate when `trade.marginal_value` is on (marginal values run smaller) |
| `mutual_gain_cap` | 1500.0 | Normalization ceiling for the harmonic-mean term in the composite score |
| `waiver_slot_cost` | 425.0 | Value cost per extra player received (FantasyCalc-derived ≈ rank-300 value) |
| `shrink_pseudocount` | 4.0 | n₀ in confidence shrinkage `w = n / (n + n₀)` toward seed Elo |
| `range_base` | 0.35 | Value half-width fraction at n=0 comparisons (range-overlap fairness) |

> **Tuning gotcha (TC-CFG-001):** the surplus floors (`min_side_surplus` / `min_side_surplus_marginal`) gate **divergence-basis** cards only. **Consensus-basis** cards (for opponents with no saved rankings — which dominate cold / low-coverage leagues) carry no surplus signal and are gated by **fairness only**. To throttle a consensus-heavy deck, tune `fairness_threshold` (per-request) or `consensus_score_scale`, not the surplus floors. And remember `trade.marginal_value` (on by default) makes `min_side_surplus_marginal` the live floor — tuning `min_side_surplus` alone is then a no-op.

### Tier 2 — marginal valuation + outlook blend

| Key | Default | Meaning |
|---|---|---|
| `bench_credit_rate` | 0.15 | Fraction of raw value depth players keep on top of over-replacement value |
| `waiver_baseline_value` | 250.0 | Replacement floor when a position has fewer than starters+1 players |
| `outlook_alpha_championship` | 1.00 | α (weight on NOW value; 1−α on FUTURE) per outlook |
| `outlook_alpha_contender` | 0.75 | |
| `outlook_alpha_not_sure` | 0.50 | Also used for outlook = None/unknown |
| `outlook_alpha_rebuilder` | 0.25 | |
| `outlook_alpha_jets` | 0.10 | |

The per-position age NOW/FUTURE curves are deliberately a code constant table (`_AGE_NOW_CURVE` / `_AGE_FUTURE_CURVE` in `trade_service.py`), not config keys — the breakpoints were calibrated as a set.

### Tier 2 — deck ordering, diversification, fuzzy matching

| Key | Default | Meaning |
|---|---|---|
| `diversity_window_days` | 7.0 | Lookback for league-wide impression counts |
| `diversity_user_cap` | 3.0 | Top receive asset already shown to ≥ this many OTHER members → penalize |
| `diversity_penalty` | 0.6 | Ordering-key multiplier for saturated targets |
| `deck_max_per_target` | 3.0 | Intra-deck cap: cards per top receive asset (deck never shrinks below 5) |
| `fuzzy_match_tau` | 0.8 | Min Jaccard similarity per side for a fuzzy mirror match (read inline in `server._fuzzy_match_tau`) |

### Tier 3 (flag-gated, landing imminently)

| Key | Default | Meaning |
|---|---|---|
| `v3_pool_size` | 12 | Candidate pool size per side for the exact per-pair search |
| `sweetener_band` | 0.15 | Fairness shortfall band in which a sweetener pass is attempted |
| `sweetener_max_cards` | 2 | Max sweetener-balanced cards per deck |
| `cycle_edge_min_gain` | 100.0 | Min per-edge value gain for a 3-team cycle edge |
| `cycle_min_net` | 200.0 | Min net surplus per participating team in a cycle |
| `cycle_max_results` | 3 | Max 3-team cycle cards surfaced |

### Verdict bands (backlog #6 / #27) — `trade_service._DEFAULT_CFG`

| Key | Default | Meaning |
|---|---|---|
| `verdict_fair_max_gap_pct` | 0.08 | `classify_verdict` band cut: gap ≤ this (as a fraction of the larger side) → `fair` |
| `verdict_lopsided_min_gap_pct` | 0.20 | `classify_verdict` band cut: gap ≥ this → `lopsided`; else `slight` |

These were introduced by backlog #6 (verdict banner) and are **vendored into `_DEFAULT_CFG` by backlog #27** (open calculator) when #6 is not yet integrated — the public `/api/calc/score` calls `classify_verdict`, so it shares the exact band thresholds in-app trade cards use. If #6 lands first, the keys already exist and #27's copy is a harmless duplicate to drop on merge.
