# Plan — G-414 (#414) "lopsided 1-for-1 served bare": proportional gap sweetener on the model deck

> Phase 1 plan, 2026-09-02. Re-aimed twice on prod evidence from the orchestrator (final: `match_swiped {source: "deck", trade_id: "f912a777", give: [8112 London], receive: [6786 Lamb]}`; London 5989.5 / Lamb 6862.0 consensus, 1qb_ppr). All cites are against the worktree at `9145d22f` (= `origin/main` `ce3f443c` + Phase 0 commits; no engine files changed since).

## 0. What this plan corrects in the inputs

| Claim | Verdict | Evidence |
|---|---|---|
| investigation.md H1: fair fork is the surface | **Wrong.** `calc_find_a_trade_tapped {path: "model"}` + an 8-hex engine `trade_id` (`str(uuid.uuid4())[:8]` at `backend/trade_service.py:6961/7244/7762`, `backend/trade_optimizer.py:617`, `backend/trade_gen_v2.py:1193`) + `source: "deck"`. Fair ideas are `fairpk_…` (`backend/server.py:12398`). D-153 stands untouched. |
| Orchestrator drop 1: likes-you injection after impression logging | **Wrong on ordering.** The injector runs at `backend/server.py:6282`; `_log_deck_signal_impressions` runs later at `:6728` on `served_final`, so injected cards DO get rows. (Moot now — no like row exists.) |
| investigation.md Fork B: "`min_package_band` 0.10 (`_emit_best`) then prefers the bare card over a balanced sibling … pinned `test_engine_quality.py:247`" | **Wrong surface.** `min_package_band` has exactly one consumer, asset-ideas' `_emit_best` (`backend/trade_service.py:5418`; `git grep` finds no other). `test_engine_quality.py:247` pins **C1** `rank_div_min_frac` (a pick must not *raise* composite), not C2. The model deck's bare-vs-balanced behaviour is (a) C1 ranking, (b) the tie-break "fewer pieces wins" (`test_engine_quality.py:270-281`), and (c) the sweetener's **collision skip** — `trade_optimizer.py:740-741`, `trade_service.py:6940`, `:7222` keep the bare card when the balanced sibling already exists. (c) is the one this item must change. |
| `docs/config-reference.md:996` "Arm C (`trade_gen_v2`) … do NOT run the pass in v1" | **Stale.** Arm C runs `close_value_gap` at `backend/trade_gen_v2.py:740` (scope.md:59 marks it DONE). Docs row below. |
| Why the same pair re-served 14 days after the 2026-08-17 pass | D-067: `pass_cooldown_days` = 14 (`backend/server.py:19076`, seed `backend/database.py:2550`). 08-17 → 08-31 is exactly the window edge; the exclusion aged out. Working as designed. |
| Why the second deck was requested at `fairness_threshold 0.5` | The client's balancing pref is OFF unless explicitly `'on'` (`mobile/src/api/tradePregen.ts:45-47`), and OFF sends `FAIRNESS_OFF_THRESHOLD = 0.5` (`:26`). Observation only; not this item's fix. |

## 1. Problem statement and serving math

The operator gave Drake London for CeeDee Lamb straight up on an ordinary model-deck card and passed it as "value — what I'm getting", asking why the engine did not add a piece from *his* side to balance it. In the engine's currency the card favours the viewer by 872.5 (12.7%), and every served arm considers that "fair enough to serve bare":

| Gate | Value for London→Lamb | Result | Cite |
|---|---|---|---|
| Package values (1-for-1 ⇒ `package_value_v2` is identity per side) | gv 5989.5 / rv 6862.0, gap 872.5, ratio 0.873 | — | `trade_service.py:1552-1600` (equal-count ⇒ no crown, single asset ⇒ no depth) |
| `user_gain_epsilon` 0.0 (viewer must not lose) | rv − gv = +872.5 | pass | `trade_service.py:247`, `:2107`, `:7114` |
| `user_gain_ok_1for1` (own raw board) | operator's board blank (both 1100) ⇒ tie | pass | `trade_service.py:1981-2006` |
| `filler_ok` | 1-for-1 ⇒ inert | pass | `trade_service.py:2008-2042` |
| Fairness band, requested 0.50 (pref OFF); divergence floor 0.55; gen_v2 band 1 − 0.15 = 0.85 | 0.873 | pass on all arms | `tradePregen.ts:26`; `database.py:2478`; `trade_service.py:708`, `trade_gen_v2.py:699-706` |
| R1 `overpay_ok` (kill when gap ≥ 500 AND gap/max ≥ 0.25) | 872.5 ≥ 500 but 0.127 < 0.25 | pass | `trade_service.py:2264-2308`, knobs `:782-783` |
| R2 `pos_net_ok` | WR for WR, net 0 | pass | `trade_service.py:2311` |
| Gap auto-sweetener (`sweetener_gap_threshold` 1539, absolute) | 872.5 ≤ 1539 ⇒ never fires | pass bare | `trade_service.py:516`; trigger inside `close_value_gap` `trade_optimizer.py:840` (`if abs(gv - rv) <= gap_threshold: return None`) |

The only mechanism that would have added a viewer-side piece is the gap sweetener, and its trigger is **absolute** (one late 1st) — scale-blind in the opposite direction from the ratio gate: a 12.7% gap on a ~6k asset is below it, while a 12.7% gap on a 15k package is above it. The operator's bar is proportional. The fix is a proportional trigger on the existing machinery, plus the sibling rule so the balanced card wins when it already exists.

## 2. PRD (FEATURE-lite)

**Goal.** On the model deck (all served arms), a card whose consensus gap exceeds a tunable **fraction** of its larger side is balanced by adding the smallest sufficient asset from the richer side's roster — for the operator's case, from the viewer's own roster — using the shipped `close_value_gap` pass, re-earning every gate. Deploy-free revertible; knob 0 = byte-identical.

**Non-goals.** No change to the fair fork (D-153 anchor exactness stands), the tier path, the likes-you injector, the fairness-pref default, R1's 0.25, or the bakeoff composition. No mobile change required.

**Requirements.**

- **R-A (core) — proportional trigger.** New `model_config` knob `sweetener_gap_frac` (default **0.10**, ≤ 0 = today). The gap pass fires when `|gv − rv| > eff`, where `eff = gap_threshold` if `gap_frac ≤ 0` else `min(gap_threshold, gap_frac × max(gv, rv))` computed on the ORIGINAL card; the sweetened card must satisfy `|n_gv − n_rv| ≤ eff` (same target, so the tightening applies to trigger and close alike). Master switch remains `sweetener_gap_threshold > 0` (D-143 pair rollback and arm A's pin untouched). Applies to all four callers: v3, consensus, v2 divergence, gen_v2. Shape-agnostic, like the absolute trigger today.
- **R-A2 — sibling rule.** When `gap_frac > 0` and the sweetened key collides with a card the enumerator already emitted for this pair, the **bare card is dropped** and the balanced sibling stays (today: bare kept, sibling kept, C1 ranks bare first — `test_engine_quality.py:270-281`). At `gap_frac ≤ 0` the collision skip is byte-identical.
- **R-C (small, recommended) — the balanced card says so.** `trade_card_to_dict` (`backend/server.py:11810-11820`) additionally serialises `sweetener: {player_id, side}` from `gap_sweetener` when the Tier-3 `sweetener` is absent, so the existing cross-client copy "+ {player} added to balance the deal" renders on iOS (`mobile/src/components/TradeCard.tsx:235-240`, normaliser `mobile/src/api/trades.ts:86-95`) and web (`web/js/app.js:3661`) with zero client change. Today gap-sweetened cards render the extra player silently (mobile never reads `gap_sweetener`: `git grep gap_sweetener mobile/src` = 0 hits).
- **R-B (telemetry) — out of this item; follow-up paragraph in §12.** Confirmed real in code; not an engine change.

**Acceptance.** London-equivalent fixture (5989.5 vs 6862.0, viewer roster holding a ~1600 asset): at defaults the served card gives London + that asset, `gap_sweetener.side == "give"`, `gap_after ≤ 686.2`, `sweetener` present on the payload; at `sweetener_gap_frac = 0` the bare card returns unsweetened, byte-identical; at `sweetener_gap_threshold = 0` (arm A) nothing fires regardless of frac.

**Default rationale (0.10).** 10% is the codebase's existing "near-equivalent" band (asset-ideas `min_package_band` 0.10 `trade_service.py:874`; F3 `fatigue_decline_value_band` 0.10 `server.py:5019`), sits under R1's 0.25 kill so the sweetener only ever acts on cards R1 admits, and leaves the C1 fixture (bare 0.905 ⇒ 9.5% gap, `test_engine_quality.py:247-266`) untouched.

## 3. Scope block (`docs/templates/feature-scope.md`, answered)

- **Date / entry point / builder:** 2026-09-02 · feedback #414 · G-414 backend build agent.
- **§1 Analytics:** **(b) existing events cover it.** `deck_impressions.features_json.gap_sweetener` is stamped on every row (`server.py:4519-4524`, null when bare); joined to `match_swiped`/`trade_pass_layer1` by `impression_id` (`analytics_taxonomy.py:1440-1442`) it answers "sweetened vs bare like/pass rate" and "share of served 1-for-1s above 10%". No new event/prop. Caveat: the §12 impression gap under-counts streamed-then-trimmed cards.
- **§2 Schema & flags:** tables none; flags none; `model_config` key **`sweetener_gap_frac`** (seed via `_MODEL_CONFIG_DEFAULTS` INSERT OR IGNORE, `backend/database.py:2328`, `:3184-3195`; mirror in `_DEFAULT_CFG` next to `sweetener_gap_threshold` `trade_service.py:516`). Rollback lever: `sweetener_gap_frac = 0` (this feature) — `sweetener_gap_threshold` stays the D-143 pair lever.
- **§3 Evidence:** structural guard n/a (no mobile change); pytest per §9; code-walk proof per §9; TestFlight checklist per §9.
- **§4 Docs:** per §10.
- **§5 Ship gate:** CI `backend-tests` + `mobile-typecheck` green; TEST_LEDGER entry; TestFlight run by operator; no express lane.

## 4. HLD delta

**None.** No new module, client, table, route or flow; the data path (generate job → per-arm generator → gap pass → mutation stack → impressions → snapshot) is unchanged. State this in the plan header; do not open `living-memory/HLD.md`.

## 5. LLD delta — the exact contract

**5.1 Knob.** `_DEFAULT_CFG["sweetener_gap_frac"] = 0.10` (`backend/trade_service.py`, immediately after `:516`, comment in the same voice as the absolute knob) and `("sweetener_gap_frac", 0.10, "…")` in `_MODEL_CONFIG_DEFAULTS` after `backend/database.py:2445`. Read everywhere through `_c("sweetener_gap_frac")` (thread-local overlay aware, `trade_service.py:1239-1245`) so the bakeoff per-arm overlays compose; `bakeoff_profiles.MODEL_A_PROFILE` is **not** edited — arm A's `sweetener_gap_threshold: 0.0` (`bakeoff_profiles.py:105`) short-circuits every caller's `_GAP_THR > 0` guard before the frac is ever read (`trade_optimizer.py:713`, `trade_service.py:6925`, `:7204`, `trade_gen_v2.py:737`), which the test in §9 pins.

**5.2 Helper (`backend/trade_optimizer.py`).**

```python
def gap_close_target(gv: float, rv: float, gap_threshold: float,
                     gap_frac: float = 0.0) -> float:
    """Effective absolute gap target for one card: the D-143 absolute
    threshold, tightened to gap_frac x max(gv, rv) when gap_frac > 0.
    Never loosens. gap_frac <= 0 returns gap_threshold unchanged."""
```

`close_value_gap(..., gap_frac: float = 0.0)` gains one keyword (default keeps every existing caller and `test_gap_sweetener.py:112-178`, `:391-403` byte-identical). Inside: `eff = gap_close_target(gv, rv, gap_threshold, gap_frac)`; the trigger `if abs(gv - rv) <= eff: return None` and the per-candidate `if abs(n_gv - n_rv) > eff: continue` both use `eff` (the original card's scale — deterministic, and the depth discount cannot move the goalposts mid-loop). Return tuple unchanged. Pass `gap_frac` explicitly like `gap_threshold` (unit-testable without `_cfg`).

**5.3 Call sites (all read `_GAP_FRAC = _c("sweetener_gap_frac")` beside `_GAP_THR`).**

| Arm | Site | Change |
|---|---|---|
| v3 | `trade_optimizer.py:706-760` | pass `gap_frac=GAP_FRAC`; collision at `:740-741`: `if new_key in card_keys: if GAP_FRAC > 0: drop this card (collect ids, filter `cards` after the loop) else continue` |
| consensus | `trade_service.py:6905-6960` | pass `gap_frac`; at `:6940` the `else` (collision) branch skips the bare card from `cards` when `_GAP_FRAC > 0` |
| v2 divergence | `trade_service.py:7101-7230` | pre-check `:7204` becomes `abs(gv - rv) > gap_close_target(gv, rv, _GAP_THR, _GAP_FRAC)`; pass `gap_frac`; collision `:7222` `else` ⇒ `return` (skip emitting the bare) when `_GAP_FRAC > 0` |
| gen_v2 (arm C) | `trade_gen_v2.py:737-760` | pre-check `:738` uses `gap_close_target`; pass `gap_frac`; no collision rule (it sweetens pre-`_dedup_batch`, Jaccard 0.6 handles siblings) |

`gap_sweetener` payload unchanged (`player_id, side, gap_before, gap_after`). "The pass never shrinks the deck" survives as "never below the sibling": a collision drop is a dedup, not a loss.

**5.4 Payload (R-C).** In `trade_card_to_dict` after `:11820`: `if not sweetener and gap_sweetener: out["sweetener"] = {"player_id": gap_sweetener["player_id"], "side": gap_sweetener["side"]}`. `gap_sweetener` is still serialised beside it. Cards with neither are byte-identical.

**5.5 Deterministic ids.** Engine cards mint ids at creation; a sweetened card keeps its id (today's behaviour) — nothing to change. (The `fairpk_` question from the original brief is moot.)

## 6. Contracts

- `POST /api/trades/generate` / `GET /api/trades/status` card shape: **no new key**; `sweetener` (already documented at `docs/api-reference.md:299`) is now also populated for gap-sweetened cards; `gap_sweetener` becomes documented (it is served today but absent from the card-shape block at `:261-300`). Not a cross-client enum — `docs/cross-client-invariants.md:284-296` copy string is unchanged and now reached on more cards.
- No request-body change. No route added.

## 7. Platforms and file ownership (disjoint from G-413: `backend/server.py:16155-16282`, `:27715-27834`, `mobile/src/components/SendInSleeperButton.tsx`)

Backend: `backend/trade_optimizer.py` (helper, v3 site), `backend/trade_service.py` (`_DEFAULT_CFG`, consensus + v2 sites), `backend/trade_gen_v2.py` (:737-760), `backend/database.py` (`_MODEL_CONFIG_DEFAULTS` one row), `backend/server.py` **only** `trade_card_to_dict` `:11810-11822` (R-C). Tests: `backend/tests/test_gap_sweetener.py`, `backend/tests/test_gap_sweetener_arm_c.py`, new `backend/tests/test_gap_sweetener_frac.py`; `test_engine_quality.py`, `test_bakeoff_arm_a_golden.py`, `test_knockout_refine.py`, `test_shape_knob.py` must stay green untouched. Docs per §10. **Mobile: none.** Web: none.

## 8. Risks

- **Deck emptiness:** none — the pass only replaces or dedups. Collision drops are ≤ 1 card per sibling pair.
- **Shape drift:** a 2-for-1 above the trigger becomes 3-for-1 (pre-existing under the absolute trigger, more frequent now); `close_value_gap` has no shape check and `v3_shape_max_delta` is 2.0 in prod (1.0 in code, `database.py:2545`). Gate with the deck_eval readout (§9) — if 3-for-1 share jumps, restrict the frac trigger to `len(richer side) == 1` as a follow-up knob, not now.
- **Latency:** v3/consensus/v2 run the pass per served card (≤ `max_per_opponent`), cheap; gen_v2 runs it per passing combo (`:738`) and will fire far more often — watch `gen_ms` p90 against the D-154 budget; the roster enumeration is O(roster) with one `package_value_v2` per candidate.
- **Duplicate ideas:** handled by R-A2 and existing key sets (`card_keys`, `_picked_keys`, `seen`); `_dedup_and_sort` (`trade_service.py:4902-4926`) re-applies `_past_decision_keys` after sweetening for v2; v3 cards pass through the same sort. gen_v2 re-tests the sweetened key against `past_decision_keys` itself (`trade_gen_v2.py:594-595`).
- **Filler floor caps how "small" a balancing piece can be:** `filler_ok` needs ≥ 25% of the give headliner and ≥ 450 (`trade_service.py:2029-2042`), so for a 6k headliner the sweetener is ≥ ~1.5k; a roster with nothing between ~1.5k and the overshoot bound serves the card bare. Expected and honest.
- **`min_package_band`:** does not apply (asset-ideas only, §0).
- **D-143:** the pair-rollback rule is preserved; the new knob is a third, independent lever documented as tightening only.

## 9. Test plan (D-056: pytest + code-walk + TestFlight checklist)

**pytest (`backend/tests/test_gap_sweetener_frac.py`, fixtures literal, `_cfg` snapshot-restored like `test_gap_sweetener.py:56-66`):**
1. `test_helper_frac_trigger_closes_a_proportional_gap` — G 5989.5 / R 7000-scale (`_mini_league` values swapped to London/Lamb: G 5989.5, R 6862.0, X1 1600, X2 600) with `gap_frac=0.10` ⇒ returns `("X1", "give", …)` and `|n_gv−n_rv| ≤ 686.2`; **sabotage** `gap_frac=0` ⇒ `None` (872.5 < 1539).
2. `test_helper_frac_never_loosens_the_absolute_target` — 20k/16k package: eff stays 1539.
3. `test_helper_frac_default_kwarg_is_byte_identical` — re-run the existing helper cases via a parametrized wrapper with `gap_frac=0.0`.
4. Per arm, on/off: `test_consensus_frac_card_is_sweetened_at_default` / `_sabotage_frac_zero_brings_the_bare_card_back` (`_consensus_league` variant with the London/Lamb elos, X1 at 1600); same pair for v3 (`generate_pair_trades_v3`), v2 divergence (`_v2_cards` pattern at `test_gap_sweetener.py:360-388`), arm C (`test_gap_sweetener_arm_c.py` fixture).
5. `test_master_switch_beats_frac` — `sweetener_gap_threshold = 0`, `sweetener_gap_frac = 0.10` ⇒ no `gap_sweetener` on any arm (arm A pin).
6. `test_untouchable_never_balances_a_frac_card` — X1 untouchable ⇒ X2 too small ⇒ card served bare, never empty.
7. `test_sibling_wins_over_bare_when_frac_on` (v3 and consensus) — fixture where the enumerator already emits `[G, X1] → [R]`; frac 0.10 ⇒ bare `[G] → [R]` absent, sibling present, deck size −1; frac 0 ⇒ both present, bare first (the C1 tie-break).
8. `test_payload_mirrors_gap_sweetener_into_sweetener` — `trade_card_to_dict`: gap only ⇒ `sweetener == {player_id, side}`; both ⇒ Tier-3 wins; neither ⇒ key absent.
9. `test_default_and_seed_agree` — `_DEFAULT_CFG["sweetener_gap_frac"] == dict(_MODEL_CONFIG_DEFAULTS)["sweetener_gap_frac"]`.
10. Regression: full suite, with `test_engine_quality.py:247-281` (C1, 9.5% fixture) and `test_bakeoff_arm_a_golden.py` unchanged.

**deck_eval golden note:** run `scripts/deck_eval.py` prod-boards replay at frac 0 vs 0.10; record over-line share, sweetened share, 1x1/2x1/3x1 shape mix, mean deck size, `gen_ms` p90 in TEST_LEDGER.

**Code-walk proof targets:** (a) all four callers read `sweetener_gap_frac` through `_c` and reach `close_value_gap` with the same `eff`; (b) arm A guard order (`_GAP_THR > 0` before any frac read); (c) collision branches per arm; (d) `_dedup_and_sort` after sweetening; (e) R-C serialisation precedence.

**TestFlight checklist (real league, balancing pref OFF):**
1. Trades landing, empty canvas → Find a Trade → pushed model deck renders.
2. Find a 1-for-1 whose value bar shows you ahead by roughly 8–15% (or build one in the calculator and note the bar). Expect: the served card's give side carries a second asset of yours and the line "+ {player} added to balance the deal"; the bar reads near even.
3. Confirm the added asset is not on your Untouchables list; ✕ / ✓ / edit-in-calculator work on it.
4. Admin config: set `sweetener_gap_frac = 0` → force regenerate → the same pair returns bare with its full gap; set back to 0.10 → balanced again (deploy-free lever proven).
5. Read `deck_impressions.features_json.gap_sweetener` for the served card id and the `match_swiped` join.

## 10. Docs rows

| Doc | Row |
|---|---|
| `docs/api-reference.md:261-300` | card shape: `sweetener` also set for gap-sweetened cards; add `gap_sweetener {player_id, side, gap_before, gap_after}` (served today, undocumented) |
| `docs/config-reference.md` (after `:996`) | new `sweetener_gap_frac` row (default 0.10, semantics, master-switch relation, D-143 note); fix the stale "Arm C … do NOT run the pass" sentence at `:996` |
| `living-memory/DECISIONS.md` | new D-entry (draft below), amends D-143 |
| `docs/cross-client-invariants.md` | n/a — no new string/enum |
| `living-memory/LLD.md`, `docs/architecture.md`, `living-memory/HLD.md`, `docs/glossary.md` | n/a — no convention, wiring, module or term change |

**DECISIONS draft.** *D-17x — The Gap Sweetener Gains a Proportional Trigger; Above It the Balanced Sibling Beats the Bare Card (amends D-143). Date 2026-09-02, origin #414 (operator, London-for-Lamb served bare at a 12.7% consensus gap). D-143's trigger is absolute (one late 1st), so a 1-for-1 on a ~6k asset could favour the viewer by 12.7% and pass every gate — R1 kills at 25%, the ratio band at 0.5/0.75, the sweetener at 1539. `model_config` `sweetener_gap_frac` (0.10) tightens the pass on every served arm to `min(1539, 0.10 × the card's larger side)`; the sweetener is drawn as before from the richer side's roster (the viewer's, when the viewer gains), re-earning each arm's gates, untouchables and not-interested; when the balanced sibling already exists the bare card yields to it (the C1 tie-break ran the other way). Gap-sweetened cards now also carry the `sweetener` marker so the shipped "+ X added to balance the deal" line renders. `sweetener_gap_threshold ≤ 0` remains the master switch and D-143's pair-rollback rule stands; `sweetener_gap_frac ≤ 0` restores 2026-08-31 behaviour byte-identically. Not changed: D-153 (the fair fork was not the surface), R1's 0.25, the balancing-pref default. Status: decided pending build.*

## 11. Analytics

Waiver (b), reasoning in §3. Optional (not required): none. If the PRD later wants sweetened-vs-bare like rate on a dashboard, it is a SQL read over `deck_impressions.features_json->gap_sweetener` joined to `trade_decisions`.

## 12. Out of scope, with reasons

- **H1 fair fork / D-153 amendment:** not the surface; anchor exactness stands; `test_fair_packages.py:197` untouched.
- **H2 (fair-fork band 0.50→0.75), H5 (age-pref parity on the fair fork):** cheap but separable and unrelated to the reported surface; log as a NEXT.md candidate.
- **H3 tier path, H6 bakeoff interleave fallback (`bakeoff_runner.py:247`):** independent hygiene, not this item.
- **Likes-you injector:** no like/standing-offer row for the pair; D-096/D-170 untouched.
- **Balancing pref default OFF ⇒ 0.50 requested** (`tradePregen.ts:26,45-47`): product decision, separate item.
- **R-B telemetry follow-up (real, one paragraph):** streaming snapshots publish each arm's cards as partners finish (`_make_progress_cb`, `server.py:3004-3030`, wired at `:6047/:6183`) *before* the final mutation stack removes cards — F7 `_split_exploration_pool` (`:5226`, ~`:6252`), F3 `_apply_deck_suppression` (`:4993`, ~`:6339`; a 30-day decline-window near-duplicate of the 08-17 pass would match here), F9 `_apply_first_session_shaping` (`:5656`, ~`:6541`), ghost split (~`:6661`) — and impressions are logged once on `served_final` at `:6728`. The client's deck merge is append-only by `trade_id` and never refreshes a held card object (`mobile/src/screens/TradesScreen.tsx:2137-2143`), so a streamed-then-trimmed card stays swipeable with `impression_id: 'none'` (`:5292`, `:5586`) — exactly the observed row — and even kept cards only carry `impression_id` if first seen in a completed snapshot. Smallest fix is client-side: on `status === 'complete'`, copy `impression_id` by `trade_id` into held cards and drop held cards beyond the fronted one that are absent from the final snapshot. Server-side alternative (apply F3/F7 per streamed snapshot) is heavier and still leaves the F9/ghost passes. Size it first: share of `match_swiped {source: deck}` with `impression_id: 'none'`. Proposed as its own feedback-pipeline item; it touches `TradesScreen.tsx`, outside G-414.

### Critical Files for Implementation
- /Users/teresadickens/Documents/Claude/Projects/Fantasy Trade Finder/.claude/worktrees/unruffled-meitner-3596cb/backend/trade_optimizer.py
- /Users/teresadickens/Documents/Claude/Projects/Fantasy Trade Finder/.claude/worktrees/unruffled-meitner-3596cb/backend/trade_service.py
- /Users/teresadickens/Documents/Claude/Projects/Fantasy Trade Finder/.claude/worktrees/unruffled-meitner-3596cb/backend/trade_gen_v2.py
- /Users/teresadickens/Documents/Claude/Projects/Fantasy Trade Finder/.claude/worktrees/unruffled-meitner-3596cb/backend/database.py
- /Users/teresadickens/Documents/Claude/Projects/Fantasy Trade Finder/.claude/worktrees/unruffled-meitner-3596cb/backend/tests/test_gap_sweetener.py
