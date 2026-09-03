# FB-414 — Phase 0 investigation: how a lopsided 1-for-1 gets served

> Orchestrator's engine trace (Explore agent, 2026-09-02) — input to the Phase 1 planner. Cites are against `origin/main` @ `ce3f443c`.

**Report (mattmurf77, 2026-08-31T20:25Z, v1.16.13):** "Why is there a trade offer of Drake London for ceedee straight up when there are other players I can add to make the trade more fair?"

## Headline

On the fair fork (`POST /api/trades/fair-packages`, give side populated) the complaint is **structurally reproducible and working as specified**: [D-153](../../../../living-memory/DECISIONS.md) makes the canvas give side an *exact anchor* ("every card gives away precisely what the user built; nothing added"), so the sweep can never add a user-side player to balance a return — and its 1-for-1 gate is the loosest in the codebase (fairness ≥ 0.50, no overpay ceiling, no sweetener, no age re-pricing). The report asks for the capability D-153 deliberately removed; the fix is therefore an operator ruling that amends D-153, not a silent bug fix.

## Fork A — `fair-packages` (give side populated)

- Route `backend/server.py:12401` (`fair_packages`, gated `calc.merged_layout`); default `fairness_threshold = 0.50` at `:12484`.
- Impl `backend/trade_service.py:5698` `_generate_fair_packages_impl`; gate `eval_consensus_package` `:2074`:
  - `:2102` `fairness = min(gv,rv)/max(gv,rv)`; `:2107` `if rv - gv < user_gain_epsilon: return None` (user must not lose; **no ceiling on gain**); `:2109-2113` consolidation loss frac (only `len(give) > len(recv)`); `:2114` `user_gain_ok_1for1`; `:2116` `filler_ok` (only bites with 2+ assets on a side); `:2118` `if fairness < relaxed_thr: return None`.
- Knobs: `user_gain_epsilon` **0.0** (`trade_service.py:247`, no model_config seed); `relaxed_fairness_threshold` 0.55 (`database.py:2480`); `filler_min_frac` 0.25 (`:2466`); `asset_floor_abs` 450 (`:2468`); `fair_packages_cap` 20 (`:2486`).
- `relaxed_thr = min(0.50, 0.55) = 0.50` (`:5786`) — **the #189 relaxed band is dead on this path at defaults**. 0.50 means one side may be worth 2× the other. (Unpinned model deck: 0.75 `server.py:11994`; v3 divergence floor 0.55 `trade_optimizer.py:301`.)
- Search shape `:5835-5856`: `for c in avail: _eval([c])` over the **whole** opponent roster, then `combinations(pool, r)` for r∈{2,3} — **receive side only**. `give_anchor` fixed `:5769`, re-emitted verbatim `:5820`.
- NOT applied here (all applied on the model deck): `overpay_ok` (R1 `:2264`), `pos_net_ok` (R2 `:2311`), `pick_swap_ok`, `close_value_gap` (the give-side sweetener — callers `trade_optimizer.py:728`, `trade_gen_v2.py:740`, `trade_service.py:6927`, `:7102`; **none is the fair fork**), `age_pref_value` (`_v` at `:5775` is bare `elo_to_value`; v2 `_vs` `:6004`, v3 `_sv` `trade_optimizer.py:336`, gen_v2 `:1088` all re-price through D-167).

## Fork B — model deck (empty canvas)

- `POST /api/trades/generate` `server.py:11994` → `_generate_trades_v2` `trade_service.py:5907` → `_generate_for_pair_v2` `:6454` / `_generate_consensus_for_pair` `:6986`, + v3 `trade_optimizer.py`. Knockouts `:6104-6112` (`overpay_ok` `:6107`, `pos_net_ok` `:6110`).
- Shape: `v3_shape_max_delta` 1.0 (`database.py:2545`) ⇒ 2-for-1 ok, 3-for-1 banned (`trade_optimizer.py:551`). R2 `pos_net_cap` 1.0 (`:2532`).
- 1-for-1 band: 0.75 unpinned; divergence `min(0.75, 0.55)`; consensus full threshold + `consensus_fairness_floor` 0.0.
- Sweetener `sweetener_gap_threshold` 1539 (`database.py:2445`) — fires only above ~a late 1st of absolute gap; R1 kills at gap ≥ 500 AND ≥ 25%. A ~20% 1-for-1 gap passes both, and `min_package_band` 0.10 (`:874`, `_emit_best` `:5418-5447`) then prefers the bare card over a balanced sibling (ruling C2, pinned `test_engine_quality.py:247`).
- Bakeoff: `_cfg("bakeoff_serve_interleaved", 1.0)` at `bakeoff_runner.py:247` falls back to **ON** while `database.py:2594` seeds 0.0 — a latent kill-switch inversion; D-154 vs the runner docstring disagree on prod's value.

## Tier same-value path (third surface)

Asset-ideas `lateral_scope:'tier'` (`trade_service.py:5330-5337`, applied `:5498-5502`, `:5611-5615`) prices with `gated=False`: fairness floor, ±band and #108 gates all skipped for tier-mates. Reachable from the give-side "More offers" chip. London and Lamb are plausibly one rung.

## What is pinned (would block a fix)

- `test_fair_packages.py:197` `test_every_idea_gives_exactly_the_anchor` — asserts `give_player_ids == ["a1"]` for every idea. **Any give-side filler breaks it** — that is D-153's contract.
- `:424` `test_both_surfaces_use_the_one_gate_function` — forbids `package_value_v2(`/`filler_ok(`/`user_gain_ok_1for1(`/`price_consensus_package(` inside `_generate_fair_packages_impl`. A fix lives in `eval_consensus_package` or a shared helper.
- `:328` relaxed refill only via `fairness_threshold=0.99`.
- `test_gap_sweetener.py` pins the sweetener on consensus/v3/v2-div — no fair-packages case.

## Which fork? — the analytics signal

`calc_find_a_trade_tapped {path: 'fair'|'model', give_count, receive_count, has_partner}` from the single emitter `mobile/src/utils/canvasSearch.ts:52-61` (taxonomy `analytics_taxonomy.py:1537`). The fair fork writes no server impression; a later swipe/queue carries a `fairpk_` trade id. `shop_opened` in the same window ⇒ the tier path. Prod read: see status.md.

## Ranked hypotheses → smallest change

| # | Hypothesis | Smallest change |
|---|---|---|
| H1 | Fair fork as specified: anchor forbids give-side filler (highest confidence) | After `chosen = strict or relaxed` (`:5861`) run ideas through `trade_optimizer.close_value_gap(..., give_candidates=user roster − anchor − untouchables, extra_ok_fn=eval wrapper)` behind a new `model_config` knob (0 = today). Amends D-153 + `test_fair_packages.py:197` — operator ruling. |
| H2 | 0.50 band is the wrong bar for a fairness surface; relaxed band inert | Route default `server.py:12484` 0.50 → 0.75 (re-arms the 0.55 relaxed band). One literal. |
| H3 | Tier same-value path served it ungated | `overpay_ok` on the `gated=False` branch. Confirm via `shop_opened` first. |
| H4 | Model fork, knockouts calibrated just wide | Knob reads (`max_overpay_frac`, `sweetener_gap_threshold`), not code; needs a deck-quality read. |
| H5 | Fair fork skips `age_pref_value` (not this pair — both in the identity band — but a live D-153 "same price" violation) | Wrap `_v` (`:5776-5780`) in `age_pref_value`, mirroring `_sv`. |
| H6 | Bakeoff interleave fallback inverted | `bakeoff_runner.py:247` fallback 1.0 → 0.0. Independent hygiene. |

## Prod evidence (read-only, 2026-09-02) — the fork question is settled

- **Surface:** `calc_find_a_trade_tapped` at 2026-08-31T20:24:26Z `{path: "model", give_count: 0, receive_count: 0, has_partner: false}` — 51 s before #414. **Model deck (empty canvas), not the fair fork.** H1 and the D-153 amendment are dropped.
- **The card:** `match_swiped` 20:25:20Z `{decision: pass, trade_id: "f912a777", give: ["8112"] (Drake London), receive: ["6786"] (CeeDee Lamb), target: 867953552205717504, source: "deck", lane: null}`; decline reason `value` / `value_getting`; `impression_id: "none"`, `ms_since_render: 63174`. The same pair was passed on 2026-08-17 (`caa580c6`). No like row from any league mate and no standing offer involve this pair — it is an ordinary engine card, not an injected one.
- **Values (league 1312140920132497408, 1qb_ppr, consensus 2026-09-02):** London 5989.5 (elo 1858.0) · Lamb 6862.0 (elo 1885.2). Gap **872.5 in the user's favor**, fairness **0.873**. The operator's own board in this league is blank (elo 1100.0 for both, 2026-08-22), so no user-board signal is in play. The report reads as: "I'm getting the better player; let me add a piece from my side" — a **user-side sweetener** case.
- **Why it served bare (H4 confirmed):** gap 872 < prod `sweetener_gap_threshold` 1539 → `close_value_gap` never fires; gap/max 12.7% < `max_overpay_frac` 0.25 → R1 does not kill; `user_gain_epsilon` 0. Prod knobs: `v3_shape_max_delta 2.0`, `bakeoff_serve_interleaved 1.0` (interleaved serving IS live — impressions carry `model_arm` gen_v2/current/challenger, `policy_version …@r1/bo:*`), `min_package_band` default 0.10 prefers the bare card over a balanced sibling.
- **Secondary (telemetry):** the card has **no `deck_impressions` row** — the two decks that session logged 45 of 54 and 51 of 60 generated cards — and was rendered ~20:24:17, during the 20:24 job's ~12 s generation, i.e. from a **streaming snapshot**. Hypothesis for the planner: the final publish applies filters (past-swipe replay / D-067 dismiss cooldown / exploration split / dedup) that streamed snapshots do not, so a user can swipe a card the final deck dropped, with no impression id.
