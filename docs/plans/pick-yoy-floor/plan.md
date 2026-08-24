# Pick YoY floor — future firsts never price below the current-year mid (D-079 re-asserted under market_slots)

> **Status:** active. Branch `claude/pick-yoy-floor-0824` from `origin/main` @ `c3791051`.
> Trigger: tester MangoPatti (via operator, 2026-08-24) — served card asked A.J. Brown + depth for Isaiah Likely + three future firsts priced ≈ 1,171 each (the ~93rd asset). Operator ruling (2026-08-24): **"The ideal solution is the D-079 ruling"** — *"firsts should hold similar value YOY. Other picks can degrade the longer away they are."*

## 1. The finding (measured, read-only prod)

- The same 2027/2028 first carries three different prices: stored `pool_value` 2,117 (never-rewritten ladder), today's market seam 1,751 / 1,459 (`priced_pool_value` step 2 riding DP's own future-year discount), and the served card's ≈ 1,171 (decomposed exactly from the recorded `receive_value`; give side reconstructs to 97% with the engine's true seeds — A.J. Brown 4,240, Swift 1,532, Likely 1,144).
- Today's injector (`server._inject_owned_picks`, probed against prod with the sweep bootstrap) produces the CORRECT market values — 1,751 / 1,751 / 1,459 — so the 1,171 was that serving boot's state (most plausibly a degraded DP `values_picks` snapshot). The Aug-19 waterfall replay also priced future firsts ~1,78x.
- Root tension regardless of the 1,171 mystery: **D-146 `market_slots` quietly overrode D-079's flat-firsts ruling for future years** — DP discounts a 2028 1st to 69% of current — exactly the Q-018 warning. The operator has now re-ruled: D-079 wins.

## 2. The change — one clamp, one knob

In `backend/pick_values.py`, inside the `market_slots` waterfall's **step 2** (`market_pick_pool_value` consumers — implement at the `priced_pool_value` seam so step 1 slotted picks are untouched):

For `round == 1` and `season > current_season` (use the same current-season source the module already has — read how `market_pick_pool_value`/its callers derive the anchor season; do not invent a new clock):

```
floor = market_r1_yoy_floor × (current-season round-1 mid value, i.e. market_pick_pool_value(current_season, 1, fmt))
value = max(market_year_value, floor)      # floor only when the floor side is resolvable
```

- Knob `market_r1_yoy_floor` default **1.0** (flat YoY — the ruling). `0` = pure market (today's behavior, byte-identical). Fractions = a dialed YoY discount (e.g. 0.85). Registered in `trade_service._DEFAULT_CFG`, `database._MODEL_CONFIG_DEFAULTS`, `_PINNED_KNOBS` (disposition: read inside the pricing seam which runs on the job thread AND under `pick_pricing_override` thread-locals — study how `current_pick_pricing_mode` interacts with arm overlays and document honestly; if arm A can reach it, pin the identity 0.0? NO — arm A predates market_slots entirely; check what mode arm A pins and follow that).
- Rounds 2–4: untouched ("other picks can degrade"). `tier_ladder` mode: untouched (already flat via D-079's per-round decay knobs). Slotted current-year picks (step 1): untouched. DP unreachable: both sides unresolvable → fallback ladder (2,117, already flat) — the floor must never turn a fallback into an error.
- Effect at default, 1qb: 2027 1st 1,751 → **2,184.6**; 2028 1st 1,459 → **2,184.6** (equal to the current-year mid, per the ruling). sf_tep inherits (2,434).

## 3. Tests (`backend/tests/test_pick_yoy_floor.py`) — sabotage-proven, byte-copy restores, clear `__pycache__` after restore (G-060)

1. Default 1.0: future-year r1 == current-year mid (both formats), with a monkeypatched slot map so the test owns its market data.
2. Knob 0: byte-identical to the unfloored market value (vendor the current step-2 arithmetic or compare against a direct `market_pick_pool_value` call).
3. Fraction 0.85: value == max(market, 0.85 × mid).
4. Rounds 2–4 and slotted step-1 picks unmoved at every knob setting.
5. DP absent: falls to stored ladder exactly as today (no exception, no floor).
6. The injector end-to-end: with the floor at default, `_inject_owned_picks`-style pricing (or `_priced_pick_value` with slot None) yields ≥ current mid for a future r1.

## 4. Ownership
One Opus builder (B1): `backend/pick_values.py`, `backend/trade_service.py` (knob row), `backend/database.py` (seed row), `backend/tests/test_bakeoff_arm_a_golden.py` (`_PINNED_KNOBS`), the new test file, `docs/config-reference.md` (knob row + a correction: the pick-pricing section's future-year sentence), `docs/plans/README.md` (row). Lead: this plan, scope, D-161, Q-018 closure note, ledger, merge, live verification. Fable: adversarial review.

## 5. Out of scope
The KTC blend for picks (players are 50% KTC-blended, picks DP-pure — structural conservatism; log as an open item, do not build). Any gate change. The sweep script's pick-less-ness (it never calls the injector — note in ledger; its knockout metrics were player-only and remain valid for what they measured).
