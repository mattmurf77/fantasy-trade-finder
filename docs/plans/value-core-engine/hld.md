# HLD — Value-core trade engine

**Date:** 2026-09-30 · **Status:** spec · Companion: [prd.md](prd.md), [lld.md](lld.md), [specs.md](specs.md)

All file:line citations are to `origin/main` at `3bb981ed`.

## 1. Shape of the system

```
                              ┌──────────────────────── backend/value_core/ (new, leaf package) ───────────────────────┐
POST /api/trades/generate     │                                                                                        │
  → _kickoff_trade_job        │  types.py      shared dataclasses (the contract every package codes against)           │
  → _run_leased_job           │  core.py       VALUE ONLY: enumerate 1–3 × 1–3 packages per partner, keep the fair     │
  → _run_trade_job ───────────┼─▶ ones (band + stud premium), hard rules → unranked pool of FairTrade        │
      prelude (unchanged)     │  windows.py    each team's window: infer_team_outlook + points-for term (ramped)       │
      ─ capture ctx           │  ranking.py    value / outlook / rank scores in [0,1] → priority; card reasons          │
      ─ boards, prefs,        │  deck.py       one card per trade idea; acquisitions in rounds; partner/asset caps     │
        untouchables          │  pipeline.py   core → ranking → deck (one call)                                        │
      ─ owned-pick injection  │  adapter.py    app objects → LeagueSnapshot/Request; DeckEntry → TradeCard + evidence  │
      ─ ★ value-core branch ──┼─▶ (only module that imports app code; never imports server.py)                    │
          (flag on ⇒ return)  └────────────────────────────────────────────────────────────────────────────────────────┘
      legacy stack (untouched when branch not taken)

backend/eval/ (new files, operator tooling, not wired to the server)
  value_core_bench.py   freeze bench leagues (prod read-only + Sleeper public) · run variants · 5 guardrails
  value_core_recall.py  historical-trade recall + fairness-band calibration from committed fixtures
  blind_grade.py        40-per-variant shuffled grade sheet · importer · served-deck card sets
```

**Two cleanly separated jobs.** `core.py` prices and judges trades on consensus market values, rosters, roster rules, untouchables and pins only, and knows nothing about anyone's window. It reads a board for one narrow purpose: a **throw-in**, a piece too small for the junk rules, may ride along only if its recipient's board (the viewer's, or the partner's published one) values it at ≥ 2× consensus (`vc_throwin_min_ratio`) with real evidence behind both numbers ([lld.md §4.3](lld.md#43-hard-rules-in-order)). `ranking.py` never drops a trade. `deck.py` orders what the core admitted and drops only the lower-priority versions of a trade idea (same partner and headliners, only minor pieces or pick years differ).

## 2. Request → card data flow

1. **Admission (unchanged).** `_kickoff_trade_job` (`server.py:9057`) claims or reuses a job. The cache freshness check `_trade_job_is_fresh` (`server.py:3488`) already compares:
   - a request signature that includes every flag and every `model_config` key (`_trade_request_signature`, `server.py:3090`);
   - a safety signature (`server.py:3367`).

   The one addition: `_trade_safety_signature` gains a `("value_core", flag)` entry. Flipping the flag then invalidates cached and running jobs of the other engine.
2. **Worker prelude (unchanged)** in `_run_trade_job` (`server.py:7427`):
   - capture the execution context;
   - load the viewer's board `elo_map_rt` and leaguemate boards;
   - read prefs, the declared outlook and the seeded outlook;
   - load untouchables and not-interested ids (flag `trade.preference_lists`, `:7679`);
   - read `confidence_counts` and `placement_bands` (`:7735`, `:7742`);
   - run owned-pick injection (`:7750-7768`), which adds pick assets to every roster, `players_dict` and `seed_map`.
3. **★ Branch (new, `server.py:~7769`, immediately after pick injection).** If `_value_core_live(...)` is true, call `_run_value_core_job(...)` and `return`. `_value_core_live` requires all of:
   - the flag is on;
   - not the demo league;
   - no `trade_intent`;
   - not a preparation job;
   - the viewer is on the tester allowlist, or `vc_testers_only = 0`.

   Nothing below that point runs for a value-core job.
4. **`_run_value_core_job` (new helper in `server.py`):**
   1. Standings: `outlook.build_league_state(league_id, "sleeper", fetch=_outlook_sleeper_fetch())` (`server.py:29497`), used for Sleeper leagues only and fail-soft. Lineup slots: `_league_lineup_slots` (`:28488`). Roster capacity: `_sleeper_roster_limit` (`:29701`). Pick shares: from the job's memoised `draft_picks` read.
   2. `windows.infer_windows(...)` gives a `TeamWindow` per team.
   3. `adapter.build_snapshot(...)` produces the `LeagueSnapshot`, and `adapter.build_request(...)` produces the `Request`. The viewer's board is shrunk with the existing `trade_service._shrink_user_elo` (`trade_service.py:1878`, w = n/(n+4)). Partners who really ranked (`has_rankings`, i.e. their Elo came from `member_rankings` rows) also get a published board in `snapshot.partner_boards`, shrunk by `adapter.partner_board_from` with the personal-market policy's symmetric rule (`trade_policy.shrink_board`). It is used only to qualify throw-ins the partner receives.
   4. `pipeline.run(snapshot, request, core_cfg, rank_cfg)` returns a `PipelineResult`: ordered `DeckEntry` items plus core diagnostics.
   5. `adapter.to_trade_cards(...)` builds `TradeCard` objects and an `{id(card): evidence}` map. Each card is registered in `trade_service._trade_cards`, which swipe, send and match lookups need (`server.py:16617`).
   6. `_project_trade_dispositions` (`server.py:3275`) removes exact passes, the #419 promise.
   7. Impressions:
      - `log_trade_impressions` writes the legacy table (`database.py:6531`);
      - `_log_deck_signal_impressions(..., value_core_evidence=...)` (`server.py:5039`) writes one `deck_impressions` row per card, with the evidence in `valuation_json`.
   8. Publish the snapshot. The shape is `trade_card_to_dict` (`server.py:14173`) plus `real_opponent`, `outlook` and `impression_id`. Then `final_checks_pending = False` and `_finish_trade_job`.
   9. `record_event(..., "trades_generated", engine_version="value_core")`.
5. **Polling (unchanged).** `GET /api/trades/status` goes through `_trade_job_public_view`. Clients render value-core cards with the existing components, and `preserve_server_order: true` stops the client re-rank.

## 3. Reused vs replaced

| Concern | Legacy (still used when flag off) | Value core (flag on) |
|---|---|---|
| Consensus value | `make_consensus_value_fn` with the age preference (`trade_service.py:3507`) | **Reused data, simpler function:** `elo_to_value(seed_elo[pid])` (`trade_service.py:1648`). This is the DP + KTC blend (`data_loader._apply_consensus_blend`, `:399`), with no age multiplier: "age is already priced into market values". It is the same number the manual calculator and `/api/trade/values` show (`server.py:12726`, `:12533`). |
| Pick value | `_inject_owned_picks` / `_pick_asset_elos` (`server.py:13839`, `:13824`) | **Reused as is.** The core reads picks from the already-primed `seed_map`. |
| Tier ladder | `tier_config.json` | **Reused:** first_1 floor (Elo 1580) = the "a 1st" threshold; firsts_4plus floor (Elo 1927) = the "elite" scale for the stud premium (`ranking_service.tier_bands_for`, `:1768`). |
| Fairness | ~15 gates: floors, R1–R5, policy floor, significance, roster gate, mutual benefit… | **Replaced** by one premium-adjusted, asymmetric band (the viewer may overpay by up to `vc_band` = 20% but gain at most `vc_gain_band` = 10%) plus the hard rules ([lld.md §4](lld.md#4-core-backendvalue_corecorepy)) |
| Consolidation | `package_value_v2` market / heavy modes (`trade_service.py:1679`) | **Replaced** by one competitor-sized stud premium: `vc_stud_premium × (headliner/elite)²` |
| Junk filler | `filler_ok` per side (`trade_service.py:2230`) | **Same two knobs** (`asset_floor_abs`, `filler_min_frac`), applied against the *trade* headliner, plus an "irreducible" rule: no piece may be removable while the trade stays fair. One exception: at most one **throw-in** per trade, a junk-sized piece its recipient values at ≥ 2× consensus and ≥ the asset floor |
| Untouchables | hard give-side exclusion | **Replaced:** allowed only when the adjusted return is ≥ `vc_untouchable_min_ratio` (1.08) |
| Lineup math | `_starter_impact` (`server.py:1195`), which is server-bound | **Reused:** `power_rankings.optimal_starters` / `optimal_starter_slots` (`power_rankings.py:99`, `:120`). These are the pure greedy lineup fill `_starter_impact`'s callers rely on; importing server-bound code is not feasible. |
| Windows | `infer_team_outlook` (`trade_service.py:3999`), age plus picks | **Reused,** plus a points-for term with a week ramp (the operator's standings decision). Declared outlooks win. |
| Board shrink | `_shrink_user_elo` (`trade_service.py:1878`) | **Reused as is:** n/(n+4) plus the D-085 placement clamp |
| Ordering | Thompson, diversity, fatigue, taste, value model, first session, presentment, policy order | **Replaced** by the 3-weight priority and a greedy assembly: one card per trade idea, acquisitions in rounds, repeat penalty, partner and asset caps in the first 30 |
| Card payload | `TradeCard` → `trade_card_to_dict` | **Reused,** additive only; no client change |
| Impressions | `deck_impressions` with arm/policy columns | **Reused.** The evidence goes into `valuation_json`, following the owner-row convention at `server.py:5496-5535` |

## 4. Flag strategy

- **One flag, `trade.value_core`, default false.** Off means the branch predicate returns False, and the `backend.value_core` package is never imported (the import is lazy inside `_run_value_core_job`). The only flag-off code changes are:
  - one predicate call;
  - one filtered tuple in `_trade_safety_signature`;
  - one defaulted kwarg on the impression logger;
  - one `and not ...` in `prepared_trade_runtime.supported` (`prepared_trade_runtime.py:86`);
  - one `vc_` prefix exclusion in the owner experiment's request-hash config filter (`server.py:15089`). The newly seeded knobs would otherwise reshuffle owner request units on deploy ([lld.md §9.1e](lld.md#91-backendserverpy)).

  All five are no-ops when off.
- **Rollout lever `vc_testers_only`** (model_config, default 1). With the flag on, only `experiments.load_tester_allowlist()` members are served (`experiments.py:120`). That list contains the operator's id (`config/tester_allowlist.json`).
- **Precedence.** When the branch is taken, the legacy bake-off, owner arms, gen_v2, policy and roster gates never run for that job. When it is not taken (flag off, non-tester, intent deck, demo, preparation), everything runs exactly as today.
- **Prepared inventories.** `prepared_trade_runtime.supported()` returns False while the flag is on. This stops adoption of inventories prepared by the legacy engine (the adoption call is at `server.py:9121`), and stops preparation. Prepared inventory already ships dark behind `prepared_trade_inventory_enabled = 0`.

## 5. Failure modes

| Failure | Behavior |
|---|---|
| Standings fetch fails, or the platform is not Sleeper | Standings are empty, and the windows use age plus picks only; `pf_index = None` is recorded in the evidence. The job proceeds. |
| Lineup slots unknown | Default template `["QB","RB","RB","WR","WR","TE","FLEX","FLEX"]` plus `SUPER_FLEX` for `sf_tep`. This mirrors `_league_lineup_slots`' platform default (`server.py:18023`). |
| Roster limit unknown (non-Sleeper) | The size rule is skipped (`max_players = None`); the lineup rule still applies |
| Core time budget (8 s) hit | Enumeration stops. The partial pool is ranked and served. `budget_exhausted` is logged in the job and the evidence. |
| Exception while building the value-core deck | Logged; `_run_value_core_job` returns `False` before anything is served, and the same job is finished by the legacy engine (PRD Q1, operator 2026-10-01). A deck never mixes engines. |
| Impression write fails | Warn. The deck is still published, without impression ids. This matches the legacy non-fatal behavior at `server.py:8725`. |
| Job superseded or timed out mid-run | `_finish_trade_job` returns None, and no event is fired. This is the existing contract (`server.py:3060`). |

## 6. Performance budget

**Sizes.**
- Per partner: at most C(N,1)+C(N,2)+C(N,3) packages per side, with N = `vc_max_assets_per_side` (14) plus up to 3 pins, so ≤ 833.
- Pairs checked per partner: ≤ 40,000, using a bisect window over package totals.
- For a 14-team league that is ≤ 520k checks. Each check is O(1) apart from the ≤ 4-removal irreducibility test and a lineup check that is rarely needed.
- The per-partner keep is ≤ 200, so the pool is ≤ 2,600.

**Time.**
- Scoring is O(pool) with two lineup fills per trade.
- Assembly is a lazy greedy, O(pool · log pool).
- Expected total 1–4 s. The hard stop is an 8 s time budget inside the core.
- For comparison, the legacy engine's median is 13.3 s and the worker median 61.1 s (`docs/plans/trade-search-latency/execution-20260921/infrastructure-and-precompute.md:23`).

## 7. Measuring stick (eval bench)

- **Freeze.**
  - Reads prod read-only, through the existing `backend/tools/prod_analytics._connect_readonly`, and asserts `transaction_read_only = on` as `capture_owner_benchmark.capture` does (`backend/eval/capture_owner_benchmark.py:61`).
  - Tables read: `leagues`, `league_members`, `draft_picks`, `member_rankings`, `players`, `player_value_history`.
  - Sleeper public API: lineup slots, capacity and standings (parsed by the reused `SleeperLeagueState`).
  - Output is one private (0600) JSON of every bench league.
- **Run.** For every league and every seat, build the snapshot and request, then run the pipeline. Compute the 5 guardrails on the first 30 cards, and write a card set per variant for blind grading.
- **Recall.** Historical in-season trades from the committed Sleeper fixtures:
  - weekly rosters from `outlook-calibration/*.json`;
  - trades from `outlook-hypotheses/*.json`;
  - dated DP values from `dp_values_history.values_as_of`.

  For each trade, report whether it or a close variant ranks top-10 for that pair, and fit the band.
- **Blind grade.** A shuffled 40-per-variant CSV sheet with the source hidden, plus a private key and an importer that scores the grades. Card sets can come from bench runs, or from the incumbent's served decks (prod `deck_impressions`, read-only).
- **Deliberately not a new framework.** It reuses the prod read-only connection, `SleeperLeagueState`, `dp_values_history` and the pipeline itself. The 36-cell scorecard is not extended.
