# Trade model — current-state map (Phase 1)

> **Purpose:** file:line-cited map of what the trade model IS on 2026-08-27: generation paths, the
> gate stack in execution order, value inputs, learning layers, and an honest list of what the model
> does not see. Companion to [plan-2026-08-27.md](plan-2026-08-27.md). Line numbers cite this
> worktree's checkout of `main` (`69dc0cae`). Claims are **code-verified** unless labeled otherwise;
> live `model_config` values are **measured** from the 2026-08-27 prod mirror (see
> [data-readout-2026-08-27.md](data-readout-2026-08-27.md) §Provenance).

## Contents

- [The one-paragraph version](#the-one-paragraph-version)
- [Live config vs code seeds — the 16 rows that differ](#live-config-vs-code-seeds--the-16-rows-that-differ)
- [Generation paths](#generation-paths)
- [Gate stack](#gate-stack)
- [Value inputs](#value-inputs)
- [Learning layers](#learning-layers)
- [What the model does NOT see](#what-the-model-does-not-see)
- [Doc drift found while mapping](#doc-drift-found-while-mapping)

## The one-paragraph version

The served engine is **v3 exact package enumeration per boarded opponent, consensus generator for
everyone else**, inside the v2 orchestration (`trade_engine.v2` + `trade_engine.v3` both on;
`trade_gen.v2` dark). Every candidate passes ~13 conjunctive gates (pool exclusions → shape → Elo gap
→ #108 → #227 → #141 → R1/R2/R3/R5 → feasibility → dual surplus → fairness) before deck assembly caps
and serve-time layers (likes-you, fatigue, Thompson/taste reordering, diversity caps). Values are
DP-KTC-blended consensus (players) and DP-pure market-slot prices (picks, with the D-079/D-161
flat-firsts floor), mapped through one exponential Elo↔value curve. **The bake-off is serving
interleaved in prod right now** (since 2026-08-21, arms current/challenger/gen_v2), the D-159 knob
bundle is partially applied (2026-08-24, with `overpay_adjusted` deliberately OFF), and the three
genuinely predictive learners (acceptance prior, negmem, F6 value model) are all dark or unfed while
swipe-driven Elo is frozen for the bake-off.

## Live config vs code seeds — the 16 rows that differ

**measured** (prod mirror `model_config`, 234 rows vs 232 seeds; every seeded key has a live row).
The 16 divergences, with the ones that change model behavior in bold:

| Key | Live | Seed | Why it matters |
|---|---|---|---|
| **`bakeoff_serve_interleaved`** | **1.0** | 0.0 | Interleaved serving is LIVE (flipped 2026-08-21T00:43Z with `bakeoff_group_size`→0, `bakeoff_deck_limit`→60). Code comments still describe dark mode — see [Doc drift](#doc-drift-found-while-mapping) |
| **`v3_shape_max_delta`** | **2.0** | 1.0 | 3-for-1 / 1-for-3 unlocked since 2026-08-24 (D-159 bundle) |
| **`filler_min_frac`** | **0.15** | 0.25 | D-159 bundle: filler floor loosened, `asset_floor_abs` 450 held |
| **`trade_elo_gap_max`** | **0.0** | 250.0 | D-159 bundle: the Elo-gap kill is OFF |
| **`overpay_adjusted`** | **0.0** | 1.0 | R1 measures **raw sums**, not `package_value_v2` — flipped 1.0→0.0 in the same 2026-08-24 batch that applied the bundle. The D-159 record says R1-in-`package_value_v2` is part of the programme; the live flip runs the other way. Logged as an open question (Q — see OPEN_QUESTIONS) |
| `qb_1qb_cap_elo` | 1717.0 | 1785.0 | #313 1QB QB compression hand-tuned live (1785→1644→1717 across 2026-08-21) |
| `qb_1qb_cap_knee_elo` | 1200.0 | 1580.0 | Same tuning session — the compression knee is far below seed |
| `bakeoff_deck_limit` | 60.0 | 30.0 | Bigger interleave pool |
| `bakeoff_group_size` | 0.0 | 10.0 | Group quotas off |
| `tier_size` | 16.0 | 24.0 | Ranking-side tier width |
| `mix_in_rate_base` / `mix_in_rate_max` | 0.2 / 0.6 | 0.35 / 0.8 | Ranking matchup mix-in rates |
| `trio_boundary_rate` | 0.5 | 0.4 | Ranking trio selection |
| `pin_unpin_on_newer_swipe` | 1.0 | 0.0 | Ranking pins |
| `value_history_seed_scale` | 2.0 | (none) | No seed — set live only |
| `analytics.wrapped_cutover_at` | epoch | (none) | Analytics cutover stamp |

Change history (all 13 rows of `model_config_changes`): ghost holdout off + interleave batch
2026-08-21T00:43; QB compression 2026-08-21; `bakeoff_include_gen_v2` off→on 2026-08-21; the four-knob
bundle 2026-08-24T04:22.

## Generation paths

### The router: `TradeService.generate_trades`

`TradeService.generate_trades` (trade_service.py:4463) pins the user's stud-tax mode then delegates to
`_generate_trades_impl` (trade_service.py:4473) — a three-way flag router:

1. **`trade_gen.v2`** (False in prod) → `trade_gen_v2.generate_league_suggestions`
   (trade_service.py:4599–4659). Dark.
2. **`trade_engine.v2`** (True) → `_generate_trades_v2` (trade_service.py:4663–4714), with the #189
   relaxed-targeted retry (4709–4710) and the #172 intent filter (4713).
3. Neither → legacy per-pair loop (trade_service.py:4753), unreachable in prod.

Inside `_generate_trades_v2`, each opponent routes per member: boarded opponents (real
`elo_ratings`) → **v3** `generate_pair_trades_v3` under `trade_engine.v3` (trade_service.py:5850–5884);
a boarded opponent whose divergence path returns zero cards falls through to consensus under
`trade.divergence_fallback` (5922–5923); never-ranked opponents always get
`_generate_consensus_for_pair` (5925). **The live served path is v3 for boarded pairs, consensus
generator for everyone else.**

### v2 scoring (trade_service.py)

- Value space: `elo_to_value` = `base · exp(k·(elo−ref))` (trade_service.py:1502–1517); the user's
  board is confidence-shrunk toward consensus before the transform (`_shrink_user_elo`, 5647–5649).
- `package_value_v2` (1533–1615) is the KTC-style non-additive package valuation. Default mode
  `market` → `_package_value_market` (1618–1682): depth discount
  `v·(floor + (1−floor)(v/bench)^γ)`, trade-wide benchmark option, discount cap, crown credit.
- Candidate pools are divergence-pruned (give = opponent values ≥97% of user's value, receive =
  reverse; 6482–6483), highest-divergence first (6506–6507), 1s deadline / 200k iterations
  (6169–6171). Shapes: 1:1, 2:1, 1:2, 3:2 (6509–6552).
- Composite: `W_MIS · min(hm, GAIN_CAP)/GAIN_CAP · damp + W_FAIR · rank_fairness`, × tier multiplier
  and target-acquire bonus (`_composite_v2`, 6384–6403); `hm` = harmonic mean of the two sides'
  surpluses. Post-generation multipliers: partner-fit FB-47 (5930–5937), need-fit FB-96 (5944–5954),
  trade-block FB-147 (5963–5970), outlook direction #175 (5986–5993, flag off).
- `base_score` in `deck_impressions` is the logged `composite_score` (server.py:4586, 4601);
  `final_score` is post-reranker.
- Consensus fallback `_generate_consensus_for_pair` (6653): fair-by-consensus 1:1 / 2:1 around roster
  fit, `basis="consensus"`; D-095 challenger knobs `consensus_both_ways` / `consensus_fairness_floor`
  default 0.0 = live one-way.

### v3 package search (trade_optimizer.py)

Invoked per boarded pair (trade_service.py:5851–5884) — a per-pair replacement for v2's scan, not a
separate surface. Differences (trade_optimizer.py:12–28, 233–258):

- **Exact enumeration**: every give-subset × receive-subset (sizes 1–3) within pools of the top
  `v3_pool_size` (12) by divergence, with board-scale calibration under `trade.pool_calibration`
  (369–441). No deadline.
- **Same objective**: same surplus math (479–504), same gate order (553–579), same composite
  (506–525).
- **Additions**: both-rosters lineup feasibility (`_both_feasible`, 472–477, gate at 580); diverse
  top-K Jaccard `v3_diversity_max_overlap` 0.4 (635–653); near-miss sweetener pass (657–697); gap
  auto-sweetener (699–766); `find_three_team_cycles` (936, not on the deck path).
- **Shape rule**: skip when `abs(len(give) − len(recv)) > v3_shape_max_delta` (547–548), read live via
  `_c` (278–288). **Live value 2.0** ⇒ 3:1/1:3 are being enumerated in prod since 2026-08-24.

### trade_gen_v2 (dark; bake-off arm C)

Flag `trade_gen.v2` False — module never imported on the serving path (trade_service.py:4593–4599).
When invoked (7-stage pipeline, trade_gen_v2.py:24–66): centerpiece-driven sourcing (top
`gen2_centerpiece_top_k` opponent assets by divergence), packages built around each centerpiece (max
3 assets/side, picks as pseudo-assets), hard gates (hygiene → feasibility → **dual-board ε-gain**
`gen2_epsilon` both sides → consensus band ±`gen2_band` on `consolidated_value`), rank =
`joint_gain × acceptance_prior × priority_weight`, per-partner exposure floor/cap, MESO variants,
structured rationale. Reaches production logging **only** as bake-off arm C
(bakeoff_runner.py:59–64, 1156–1216), and since 2026-08-21 its cards can actually serve via
interleaving.

### Surfaces → paths

| Surface | Route | Path |
|---|---|---|
| Swipe deck | `POST /api/trades/generate` (server.py:11856) → `_run_trade_job` (5789) | Bake-off fan-out when active (server.py:6126–6148) — organic decks only; v3+consensus otherwise |
| Finder targeting | Same route, `pinned_*` / `trade_intent` / `opponent_user_id` body keys (11890–11915) | Same engine with pool constraints; **bypasses the bake-off** (6027–6028) and R5 only (5715) |
| Asset ideas | `POST /api/trades/asset-ideas` (12024) | Own consensus enumeration (`_generate_asset_ideas_impl`, trade_service.py:4982) — not v2/v3 |
| Fair packages | `POST /api/trades/fair-packages` (12236) | `_generate_fair_packages_impl` (trade_service.py:5368) |
| In-league calculator | `GET /api/trade/values` (10088), `POST /api/trade/evaluate` (10150) | No generation; reuses `trade_optimizer._consensus_packages`/`_fairness_v3` so calculator and deck agree (trade_service.py:6558–6562) |
| Likes-you injection | Post-generation pass in `_run_trade_job` (6196–6218) | No engine — mirrors league-mates' likes / #362 standing offers, gate ladder `likes_you_gate_level` 2 (server.py:3171–3186), cap 3 |

### Bake-off arms (bakeoff_runner.py)

- **A `baseline`** — live engine under the pinned `MODEL_A_PROFILE` (pre-G6 reconstruction;
  bakeoff_profiles.py:69–117). Off-roster by default.
- **B `current`** — live engine at live defaults (1556–1558); the arm served in dark mode.
- **C `gen_v2`** — `trade_gen_v2` called directly regardless of its flag (1156–1216). Rostered
  (`bakeoff_include_gen_v2` re-lit 2026-08-21T18:49).
- **D `challenger`** — arm B under `MODEL_CHALLENGER_PROFILE` (landability overlay: no board shrink,
  both-ways consensus at 0.75 floor, R5 off, compressed tier ladder — bakeoff_profiles.py:154–196).
  Rostered by default.
- **`fit`** — `trade_gen_fit` (1332–1360), off-roster.

Serving: `serve_interleaved()` = `bakeoff_enabled() and _cfg("bakeoff_serve_interleaved", …) ≥ 1.0`
(bakeoff_runner.py:247) — **True in prod today** (live row 1.0). The docstring above it (229–246)
still describes the 2026-08-19 dark decision; stale, see [Doc drift](#doc-drift-found-while-mapping).

## Gate stack

Full detail with per-gate knob defaults lives in the execution-order list below; knob values quoted
are code seeds (`trade_service._DEFAULT_CFG` / `database._MODEL_CONFIG_DEFAULTS`) except where the
[live-config table](#live-config-vs-code-seeds--the-16-rows-that-differ) overrides them.

**A. v3 divergence path, per candidate (trade_optimizer.py loop):**

1. Pool exclusions: untouchables / not-interested / avoided positions (trade_service.py:6468–6482)
2. Pin constraints (trade_optimizer.py:540–546)
3. Shape rule `> v3_shape_max_delta` (**live 2.0**) — 547–548
4. `_positions_ok` preference filter — 549–550
5. `_gap_ok` `trade_elo_gap_max` (**live 0.0 = OFF**) — 551–552
6. #108 `fit_premium_1for1` / `user_gain_ok_1for1` — raw-board 1-for-1 epsilon
   (`user_gain_epsilon` 0.0) — 560–563; trade_service.py:1960–1985
7. #227 `pick_swap_ok` pick-churn kill (`pick_pair_strip_frac` 0.85) — trade_service.py:2164
8. #141 `filler_ok` — every non-headliner ≥ `max(headliner × filler_min_frac, asset_floor_abs)`
   (**live 0.15** / 450) — trade_service.py:1989–2022
9. Presentment R1→R2→R3→R5 (`trade.presentment_rules` on; bound at trade_service.py:5740–5795):
   - **R1 `overpay_ok`** (2221–2266): kill when `gap ≥ max_overpay_min_value` (500) AND
     `gap/max ≥ max_overpay_frac` (0.25), two-sided. `overpay_adjusted` **live 0.0** ⇒ raw sums.
   - **R2 `pos_net_ok`** (2268–2340): per-position |net| > `pos_net_cap` (1) kills, unless
     starter-relief (`pos_net_starter_relief` 1.0, lit) rescues — shedder above starter depth
     before, both rosters at/above after.
   - **R3 `pick_gap_ok`** (2342–2374): pick-bearing + `gap ≥ 300` + heavier-side pick's value inside
     `[0.8×gap, gap/0.8]` kills.
   - **R5 `need_gate_ok`** (2376–2496): untargeted decks; primary (or, with `need_gate_dual_rescue`
     1.0 lit, any) received asset ≥500 must fill a starting hole or beat the post-give incumbent;
     dual-need rescue when the user sheds surplus at the partner's short position.
10. `_both_feasible` lineup feasibility — 581
11. Dual surplus: both sides ≥ `min_side_surplus` 150 (60 marginal) — 584–585
12. Consensus fairness `_fairness_v3` at `min(threshold, fairness_floor_divergence 0.55)` with
    uncertainty-overlap escape — 587, 141–150; near-misses within `sweetener_band` 0.15 → sweetener
    rescue re-running filler + presentment (775–817)
13. Diverse top-K (Jaccard 0.4)

**B. Consensus path (`_emit`, trade_service.py:6802–6870):** dedup → #108 package-delta epsilon
(6830) → consolidation raw-loss kill (`consolidation_raw_loss_frac` 0.15; 6838–6842) → #108 raw
1-for-1 (6845) → #227 → #141 (6853) → R1–R3, R5 (6857–6858) → fairness < threshold (caller 0.75
untargeted / 0.50 pinned; `consensus_fairness_floor` 0.0) → gap auto-sweetener repair
(`sweetener_gap_threshold` 1539.0) with full re-validation (6770–6795).

**C. Deck assembly (`_dedup_and_sort`, trade_service.py:4820–4894):** past-decision exclusion
(pass 14d / like 7d, `pass_cooldown_start_epoch` amnesty) → **R4** windowless awaiting/matched
exclusion (#336; keys server.py:5748–5762) → composite sort → C4 `deck_headliner_cap` 2 per
centerpiece (4862–4879) → C4b `deck_give_headliner_cap` 3 per give-headliner (D-082; 4892–4894).

**D. Serve-time (server.py):** likes-you injection (ladder level 2: package-delta floor +
directional R1 + filler; cap 3) → F3 hard decline-suppression (30d, ±10% value band, one retest,
≥5-card floor; 4915–5045) → `_order_deck` reorder (Thompson v2 draw, A6 diversity penalty 0.6, soft
fatigue, taste multipliers; 4076–4218) → A6 intra-deck cap `deck_max_per_target` 3 (3847–3872) → F7
audition removal (5380–5440) → F9 first-session shaping (reorder only, 5545–5580).

The 2026-08-22 restrictiveness review
([docs/reviews/2026-08-22-trade-model-restrictiveness.html](../../reviews/2026-08-22-trade-model-restrictiveness.html))
measured this stack's redundancy: 97.6% of rejections are co-kills by ≥2 rules ([G-058](../../../living-memory/GOTCHAS.md)).

## Value inputs

- **Elo↔value**: `elo_to_value` exponential (trade_service.py:1502–1517); consensus Elo seeded from
  DP's 0–10000 scale via `seed_elo_for_value` (data_loader.py:103–115; DP 0 → Elo 1200, 10000 →
  ≈1927.3). Footgun: `seed_elo_for_value` and `value_to_elo` are different maps crossing at Elo
  1548.0 (D-088; pick_values.py:72–83). Resolution collapses below rank ~200 (pick_values.py:59–70).
- **Tier bands**: `tier_config.json`, 8 tiers, floors defined as pick-ladder rungs; loaded at process
  start (pick_values.py:99–101) — band changes need a deploy.
- **Player consensus = DP ⊕ KTC 50/50**: DP `values-players.csv` (data_loader.py:70–72, 596–690)
  blended with KTC rank-normalized onto the DP curve, `ktc_blend_weight` 0.5
  (data_loader.py:399–457, 215); sf_tep TE ×1.18; #313 1QB QB compression applied last (446–450,
  live knobs hand-tuned — see config table). KTC failure fail-softs to DP-only.
- **Picks are DP-pure** (KTC "RDP" rows excluded at parse, data_loader.py:302–310). D-146 waterfall
  in `priced_pool_value` (pick_values.py:683–746): own slot price → round curve (mid-tercile) with
  D-079 `pick_year_decay_r1..r4` (1.0/0.85/0.85/0.85) and the D-161 `market_r1_yoy_floor` 1.0 (flat
  future firsts) → stored ladder. Single seam `server._priced_pick_value` (server.py:11235–11253).
  **`picks.slot_labels` is secretly a pricing flag** (off ⇒ every pick drops to the round curve;
  server.py:11161–11162, flag-comment stale per D-146).
- **Refresh cadence (H4)**: pool frozen until invalidated; 20-hour TTL (server.py:1834) with the
  daily-tick fallback guard (13:30 UTC) as the real trigger — **consensus moves at most ~once/day**,
  plus deploys/restarts. KTC and pick-slot caches: 24 h TTL, failures also cached 24 h. A failed DP
  fetch silently keeps the old pool. `player_value_history` snapshots write once per UTC day via the
  hourly-tick guard (server.py:20934–20948).
- **Basis**: divergence cards from real-board pairs; consensus for unboarded + the
  `trade.divergence_fallback` fall-through; `user_value_basis` (personal/consensus) is the user-side
  stamp (server.py:4463); `real_opponent` = counterparty has real stored rankings (server.py:3019,
  5832–5850).
- **Age never changes a value in the live config**: `trade.outlook_blend` off, `trade.outlook_direction`
  off, gen_v2 dark. Age reaches labels (lanes), taste attributes, and outlook inference only. Any
  veteran-vs-youth pricing bias therefore comes from DP/KTC or user boards, not an in-app curve.

## Learning layers

| Layer | Verdict | Detail |
|---|---|---|
| Thompson deck v2 | **LIVE** | Beta draw per (lane × shape) arm, ordering multiplier clamp 0.5–1.5 (server.py:4044–4069, 4123–4153); fed by viewed-gated deck outcomes + legacy shape counts, decay 0.995, 120d TTL |
| Taste vectors | **LIVE** | Per-user decayed attribute preferences (lane, positions, age bands, pick tier, value bands, partner id — taste_service.py:180–235); ordering multipliers only |
| Fatigue F3 | **LIVE** | Soft per-centerpiece/hash discounts + hard 30d decline-suppression with one retest (server.py:4855–4939) |
| Pass-cooldown | **LIVE** | Exact-package exclusion 14d (pass) / 7d (like); in-session binding (server.py:18950–18991, 12640–12653) |
| A6 diversity | **LIVE** | League-level saturation penalty 0.6 + intra-deck cap 3 per target (server.py:4193–4220) |
| Likes-you / R4 | **LIVE** | Counterparty likes injected/pinned; matured likes excluded windowlessly |
| Elo from trade swipes | **FROZEN** | `elo_freeze_mult` = 0.0 while `trade.bakeoff` is on (server.py:12590–12596) — trade swipes currently move Elo by exactly zero; ranking votes stay live. Decline reasons: only `value_giving` may write Elo (`PASS_REASON_ELO_KEEP`, ranking_service.py:203–246) |
| Acceptance prior (gen_v2) | **UNFED** | `score ×= accept_prior` exists (trade_gen_v2.py:821) but `acceptance_stats` is supplied only by negmem's M2 feed — with negmem dark the prior is uniformly `p0` for every partner |
| Negmem | **DARK** | D-147/ADR-015: flag false + allowlist empty; four consultation seams guarded; never run live; TestFlight checklist unrun (assumes prod `FTF_NEGMEM_LEAGUES` env unset — not inspectable from the repo) |
| F6 value model | **DARK** | `deck.value_model` false; gated on an F8 replay win by design (value_model.py:6–13) |

## What the model does NOT see

1. **League scoring, beyond one bit.** Format collapses to `1qb_ppr` vs `sf_tep`
   (server.py:730–766): SF and TEP are conflated (a 1QB TE-premium league gets the full superflex
   bundle); PPR magnitude is invisible (standard = half = full); the fallback pick ladder ignores
   format entirely (pick_values.py:280–281). What the bit does drive: per-format DP values + TE
   uplift, SF QB starter-need 2, per-format tier bands, format-aware market slot prices.
2. **Player age as a value input.** Stored and hydrated, consumed by labels/taste/inference only —
   every valuation-touching age path is flagged off (see Value inputs).
3. **Windows re-price nothing.** Outlook inference and two-lane labels are live
   (`trade.outlook_infer`, `trade.lanes`), and one knockout predicate reads outlook — but
   `trade.outlook_blend` / `outlook_direction` / `outlook_net_firsts` / `outlook_composite` are all
   false: the live engine never changes an asset's price because of anyone's window.
4. **Real lineup construction.** Fixed starter template `_STARTER_NEED` (QB1/RB2/WR2/TE1, QB2 in SF;
   trade_service.py:2502–2503) — a league's actual `roster_positions` (3WR, multi-flex, IDP) never
   reach the engine; v3 feasibility treats FLEX as "any body" (trade_optimizer.py:175–177). Bye
   weeks: unshipped knob 0.0 (database.py:2511–2516). Depth charts: only the inert `handcuff_rb`
   count.
5. **Injury, news, recent performance.** Injury fields are served for display; zero paths into
   generation/scoring/gating (grep-verified across all engine modules). No news ingestion. Real-world
   performance arrives only as DP/KTC consensus drift, at most daily.
6. **Partner liquidity.** `sleeper_trades` (real completed league trades) feeds the executed-trade
   matcher and telemetry only — nothing prices "this partner actually trades." The two
   partner-responsiveness signals: negmem M2 (dark) and taste `partner:<id>` (the viewer's own
   swiping, not the partner's behavior).

## Doc drift found while mapping

- `bakeoff_runner.serve_interleaved` docstring (bakeoff_runner.py:230–246) and
  `bakeoff_profiles.py:144` still say interleaving is dark ("back to 0.0, operator 2026-08-19");
  live row = 1.0 since 2026-08-21. The feature_flags.py:918 guardrail comment ("DO NOT raise
  bakeoff_serve_interleaved", #360) predates the re-light.
- `feature_flags.py:417–427` still claims `picks.slot_labels` is display-only; D-146 made it a
  pricing flag (acknowledged in D-146 as scope §6 waiver 1).
- `docs/runbook.md` § pre-ship simulator gate still describes the retired tier matrix (known, per
  CLAUDE.md).
