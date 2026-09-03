# LLD delta — G-414: proportional gap-sweetener trigger + sibling rule + payload marker

> Phase 1 contract for the backend build agent. Source: [plan-g414.md](plan-g414.md) §5–§6.
> **Every file:line below was re-verified against the worktree on 2026-09-02 (HEAD `48f40de5`).**
> Symbols marked **NEW** do not exist yet. Where the plan's cite did not survive
> verification, §0 says so and the corrected cite is what the rest of this document uses.
> HLD delta: **none** — no new module, route, table or flow (plan §4).
> **Round 2 (2026-09-02):** Planner rulings 1–3 and 6 from [review-round-1.md](review-round-1.md)
> are folded into §1 (live-change lever, tuning floor), §4.1 (no backfill), §4.3 (reachable
> collision + outcome invariant), §4.4 (arm C) and §7.
> **Mini-round (2026-09-02, build-time gaps — [reconciliation-log.md §6](reconciliation-log.md)):**
> §3 now specifies a **two-tier accept** (tier 1 = `eff`, tier 2 = the D-143 `gap_threshold`
> fallback) — the round-1/2 single rule made the pass do less than D-143 on wide-gap cards;
> §1/§5/§8 add the arm-A bookkeeping (`_PINNED_KNOBS` token + scope-phase2 exclusion row) and
> the one declared test re-spec (arm C's `10 ** 9` leg). Decision label is **D-173 (unshipped parallel build; see D-175)**.

## Table of contents

- [0. Corrections to the plan's cites](#0-corrections-to-the-plans-cites)
- [1. Knob — `sweetener_gap_frac`](#1-knob--sweetener_gap_frac)
- [2. Helper — `gap_close_target` (NEW)](#2-helper--gap_close_target-new)
- [3. `close_value_gap(..., gap_frac=0.0)` — trigger and close semantics](#3-close_value_gap-gap_frac00--trigger-and-close-semantics)
- [4. Call sites — four arms, per-arm collision rule](#4-call-sites--four-arms-per-arm-collision-rule)
- [5. Arm A master-switch ordering](#5-arm-a-master-switch-ordering)
- [6. Payload — `trade_card_to_dict` mirrors `gap_sweetener` into `sweetener`](#6-payload--trade_card_to_dict-mirrors-gap_sweetener-into-sweetener)
- [7. Invariants that must survive](#7-invariants-that-must-survive)
- [8. Touch-point index](#8-touch-point-index)

---

## 0. Corrections to the plan's cites

| Plan says | Verified | Used below |
|---|---|---|
| "consensus `trade_service.py:6905-6960`" and "v2 divergence `:7101-7230`" | **Labels are swapped.** `:6905-6960` sits inside `_generate_for_pair_v2` (`def` at `trade_service.py:6454`, method ends `:6984`) — the **v2 divergence** pair generator, which passes no candidate pools (the docstring at `trade_optimizer.py:868-876` names it as such). `:7101-7230` sits inside `_generate_consensus_for_pair` (`def` at `:6986`) — the **consensus** generator, which passes `give_candidates=give_pool, recv_candidates=recv_pool` (`:7220-7221`). Mechanics in the plan's table are correct per line; only the arm names were crossed. | v2 divergence = `:6905-6983`; consensus = `:7101-7230` |
| v3 guard at `trade_optimizer.py:713` | `:711` (`if GAP_THR > 0 and cards:`); the read is `:710` | `:710-711` |
| v2 guard at `trade_service.py:6925` | `:6926` (`if _GAP_THR > 0:`); the read is `:6905` | `:6905`, `:6926` |
| consensus collision at `:7222` | `:7228` (`if n_key not in seen:`); the pre-check is `:7204` | `:7204`, `:7228` |
| "the `else` (collision) branch" at v2 `:6940` | There is **no `else`** today — `:6940` is `if new_key not in _picked_keys:` and a collision simply falls through to the `TradeCard(...)` build at `:6960` and `cards.append(card)` at `:6983`. The change adds the branch. | `:6940`, `:6983` |
| `_MODEL_CONFIG_DEFAULTS` seed loop `database.py:3184-3195` | Confirmed (`INSERT OR IGNORE` sqlite / `ON CONFLICT (key) DO NOTHING` Postgres). | `:3184-3195` |

Everything else in plan §5 verified as cited.

## 1. Knob — `sweetener_gap_frac`

| Item | Contract |
|---|---|
| Name | `sweetener_gap_frac` (`model_config` key; float) |
| Default | **0.10** |
| Semantics | Fraction of the card's larger consensus side that the gap pass tolerates. `> 0` tightens the D-143 absolute target to `min(sweetener_gap_threshold, frac × max(gv, rv))`. **`≤ 0` = byte-identical to 2026-08-31 behaviour** (absolute trigger only). It can only tighten — see §2. |
| Master switch | Unchanged: `sweetener_gap_threshold ≤ 0` disables the whole pass on every arm before this knob is consulted (§5). D-143's pair-rollback rule is untouched; this knob is a third, independent, tightening-only lever. |
| Code default | `backend/trade_service.py` `_DEFAULT_CFG` — insert **immediately after `:516`** (`"sweetener_gap_threshold": 1539.0,`), with a comment in the same voice as `:509-515`: `"sweetener_gap_frac": 0.10,` |
| DB seed | `backend/database.py` `_MODEL_CONFIG_DEFAULTS` (list starts `:2328`) — insert **immediately after `:2445`** (the `sweetener_gap_threshold` row): `("sweetener_gap_frac", 0.10, "2026-09-02 #414: proportional gap-sweetener trigger — tightens sweetener_gap_threshold to min(threshold, frac x max(give, receive)) on every served arm; <=0 restores the absolute trigger byte-identically; inert while sweetener_gap_threshold <= 0")`. Seeded by the existing loop at `:3184-3195`; existing rows survive (`INSERT OR IGNORE` / `DO NOTHING`). |
| Read | Always through `_c("sweetener_gap_frac")` (`trade_service.py:1239-1245`: thread-local overlay → `_cfg` → `_DEFAULT_CFG`). `trade_optimizer.py` already imports `_c` (`:57-61`); `trade_gen_v2.py` already uses `_c` (`:112`, e.g. `:532-533`). **Never** read `_cfg[...]` or `_DEFAULT_CFG[...]` directly at a call site. |
| Live change | **Only** `PUT /api/admin/config/sweetener_gap_frac` (`server.py:18577-18601`; `X-Cron-Secret` via `_require_cron_auth` `:20943`; body `{"value", "source"}`) — it calls `set_config` and then `_trade_service_mod.reload_config()` inline (`:18600`), and logs a `model_config_changes` row. `_cfg` is otherwise loaded once at process start (`:449`); `git grep reload_config backend/server.py` = those two sites. A raw `UPDATE model_config` is **invisible to the running dyno** until restart. |
| Tuning floor | Do not set below **0.0952** without retuning `test_engine_quality.py::test_adding_a_pick_to_a_fair_package_does_not_raise_composite` (`:247-266`): its bare card sits at a 9.52 % gap and, under `_ORTHOGONAL_GATES_OPEN` (`:219-231`, `filler_min_frac 0`), its 287-value pick is an eligible equalizer — the bare would sweeten into the organic padded sibling and be dropped by R-A2. |
| Parity | `_DEFAULT_CFG["sweetener_gap_frac"] == dict(_MODEL_CONFIG_DEFAULTS)["sweetener_gap_frac"]` — pinned by PRD T-9. |
| Not touched | `backend/bakeoff_profiles.py` `MODEL_A_PROFILE` (`:98-105`): the key is deliberately **absent** — arm A's `"sweetener_gap_threshold": 0.0` (`:105`) already short-circuits every caller (§5), same rule as `package_floor_cross` (`:99-101`). |
| Arm A bookkeeping (mini-round, Gap 3) | `backend/tests/test_bakeoff_arm_a_golden.py` `test_no_generation_knob_was_added_without_an_arm_a_decision` (`:724-727`) requires every `_DEFAULT_CFG` key to be listed in `_PINNED_KNOBS` (`:527`) **and** dispositioned in `docs/plans/three-model-bakeoff/scope-phase2.md`. So: (1) add the token `sweetener_gap_frac` to `_PINNED_KNOBS` (one word, alphabetical slot); (2) add an **exclusion** row to the scope-phase2 knob table, modelled on the `package_floor_cross` "inert companion" row at `:122`: *"gap auto-sweetener frac, 2026-09-02 (#414 / D-173 (unshipped parallel build; see D-175)) — **Inert companion.** Every caller reads it only behind `sweetener_gap_threshold > 0`, which `MODEL_A_PROFILE` pins at 0.0 (`:105`); at that pin no frac branch is reachable (`trade_optimizer.py:711`, `trade_service.py:6926`, `:7204`, `trade_gen_v2.py:737`). Pinning it would imply it matters to arm A — same rule as `package_floor_cross`."* The golden itself is **not** re-captured (arm A's output is byte-identical by the guard order in §5). |

## 2. Helper — `gap_close_target` (NEW)

`backend/trade_optimizer.py`, module level, placed **directly above** `close_value_gap` (`:840`). Pure, no `_c` read, no imports needed.

```python
def gap_close_target(gv: float, rv: float, gap_threshold: float,
                     gap_frac: float = 0.0) -> float:
    """Effective absolute gap target for ONE card (#414, 2026-09-02).

    The D-143 absolute threshold, tightened to ``gap_frac × max(gv, rv)``
    when ``gap_frac > 0``. Never loosens: the result is always
    ``<= gap_threshold``. ``gap_frac <= 0`` returns ``gap_threshold``
    unchanged, so every pre-#414 caller is byte-identical by default.
    Computed once per card on its ORIGINAL sides — the same number gates
    the trigger and the close (see close_value_gap)."""
    if gap_frac <= 0:
        return gap_threshold
    return min(gap_threshold, gap_frac * max(gv, rv))
```

Properties the tests pin (PRD §6): `gap_close_target(5989.5, 6862.0, 1539.0, 0.10) == 686.2`; `gap_close_target(20000, 16000, 1539.0, 0.10) == 1539.0`; `gap_close_target(x, y, t, 0.0) == t` for all `x, y`; result `<= gap_threshold` for all inputs.

## 3. `close_value_gap(..., gap_frac=0.0)` — trigger and close semantics

Signature today (`trade_optimizer.py:840-844`):

```python
def close_value_gap(give_ids, recv_ids, *, seed_value, gap_threshold,
                    fairness_threshold, user_roster, opp_roster, players,
                    scoring_format="1qb_ppr", untouchable_ids=None,
                    not_interested_ids=None, extra_ok_fn=None,
                    give_candidates=None, recv_candidates=None):
```

Change: append one keyword-only parameter, **`gap_frac: float = 0.0`**, after `recv_candidates=None`. The default keeps every existing caller and every existing test (`backend/tests/test_gap_sweetener.py:112-178`, `:391-403`; `test_gap_sweetener_arm_c.py`) byte-identical. Return tuple `(s_pid, side, new_give, new_recv, n_gv, n_rv, round(ratio, 3))` (`:931`) is **unchanged**.

Body — **two-tier accept** (mini-round ruling, Gap 1; supersedes the round-1/2 single accept rule
`abs(n_gv − n_rv) <= eff`, which made the pass do *less* than D-143 on wide-gap cards — see §3.1):

| Line today | Today | Becomes |
|---|---|---|
| `:890` | `gv, rv = _consensus_packages(give_ids, recv_ids, seed_value)` | unchanged, then **add** `eff = gap_close_target(gv, rv, gap_threshold, gap_frac)` |
| `:891` | `if abs(gv - rv) <= gap_threshold:` → `return None` | `if abs(gv - rv) <= eff:` (trigger) |
| before `:910` | — | **add** `fallback = None` |
| `:918` | `if abs(n_gv - n_rv) > gap_threshold:      # too small to close it` | **unchanged** — this stays the D-143 line: a residual above `gap_threshold` is rejected outright |
| `:931` | `return s_pid, side, new_give, new_recv, n_gv, n_rv, round(ratio, 3)` | `result = (s_pid, side, new_give, new_recv, n_gv, n_rv, round(ratio, 3))` then `if abs(n_gv - n_rv) <= eff: return result` (**tier 1**) else `if fallback is None: fallback = result` (**tier 2**) and continue the walk |
| `:932` | `return None` | `return fallback` |

Sketch of the candidate walk after the change (gate checks at `:916-930` are unchanged and apply to **both** tiers):

```python
    fallback = None
    for s_pid in candidates:                       # cheapest-first, unchanged
        ...                                        # build new_give/new_recv, n_gv/n_rv
        if n_gv <= 0 or n_rv <= 0: continue
        if abs(n_gv - n_rv) > gap_threshold: continue      # D-143 line, unchanged
        ...                                        # ratio band, feasibility, extra_ok_fn — unchanged
        result = (s_pid, side, new_give, new_recv, n_gv, n_rv, round(ratio, 3))
        if abs(n_gv - n_rv) <= eff:
            return result                          # tier 1: reaches the proportional target
        if fallback is None:
            fallback = result                      # tier 2: the D-143 result, kept in case no tier-1 exists
    return fallback
```

Semantics, stated as the contract:

- **`eff` is computed once, on the ORIGINAL card** (`gv, rv` of `give_ids`/`recv_ids` before any candidate is added). It is **not** recomputed per candidate: `max(n_gv, n_rv)` grows as an asset is added and would move the goalposts mid-loop. Deterministic and identical to the pre-check the consensus/gen_v2 callers run (§4), because both use `_consensus_packages` (`trade_optimizer.py:108-117`) — the consensus `_emit` computes `gv, rv` with the same `package_value_v2(…, v_max, n_other, other_values)` call (`trade_service.py:7140-7146`).
- **Trigger:** the pass fires iff `abs(gv − rv) > eff`. Unchanged from round 1.
- **Accept, tier 1:** the **first** candidate (cheapest-first, `:904-910`) whose residual `abs(n_gv − n_rv) <= eff` and which clears every gate (ratio ≥ `fairness_threshold` `:920-922`, both lineups feasible `:923-928`, `extra_ok_fn` `:929-930`) is returned **immediately**.
- **Accept, tier 2 (= D-143):** if no candidate reaches `eff`, the **first** gate-clearing candidate whose residual `<= gap_threshold` is returned after the walk completes. A candidate whose residual exceeds `gap_threshold` is rejected in both tiers (`:918`, unchanged).
- **Else `None`** — the card is served bare, exactly as today.
- **Never loosens, never widens:** `eff ≤ gap_threshold` always. At `gap_frac ≤ 0`, `eff == gap_threshold`, so tier 1 ≡ tier 2 ≡ today's single rule — the walk returns the first candidate under `gap_threshold`, byte-identical. At `gap_frac > 0` every card D-143 would have closed is still closed (tier 2 catches exactly D-143's result), and cards D-143 left bare may now close (the trigger is lower); **no served gap is ever wider than under D-143**.
- **`gap_after` may exceed `eff` on a tier-2 result** (it is ≤ `gap_threshold`); the `gap_sweetener` dict and the R-C `sweetener` marker are set the same way for both tiers — the card *is* balanced by the pass, just not all the way to the proportional target. Callers do not distinguish tiers; nothing in the return tuple changes.
- **London fixture (PRD §4):** X2 (600) is a tier-2 candidate at the helper level (residual 762.2: > 686.2, ≤ 1539) and is walked first; X1 (1550) is tier 1 (46.7) and wins the moment it is reached — so the helper returns X1 regardless of the tier-2 candidate ahead of it in the walk. In the served arms `filler_ok` removes X2 before either tier applies.

### 3.1 Why the round-1/2 single rule was wrong (build-time finding)

With `abs(n_gv − n_rv) <= eff` as the only accept, a card whose sole sufficient equalizer narrows the gap under 1539 but not under `eff` returned `None` and was served **bare with its full gap** — strictly worse than D-143 for that card. The shipped fixtures hit it: `_mini_league` (`test_gap_sweetener.py:94-110`) 1600 → 977.7 with eff = 700, and `_v3_league` (`:261-297`) 2908.7 → 1336.5 with eff ≈ 900 — turning four legacy assertions red (`test_gap_sweetener.py:235`, `:330`, `:368`, `:431`). The two-tier rule keeps those four green **without editing them**.
- Untouchables (give side) and not-interested (receive side) exclusions at `:905-908` are unchanged and therefore apply to the frac-triggered case identically.
- Docstring: add one paragraph under the existing `gap_threshold` description naming `gap_frac`, the `min(threshold, frac × max)` rule and the once-per-card computation. Do not rewrite the rest.

## 4. Call sites — four arms, per-arm collision rule

Common to all four: read `_GAP_FRAC = _c("sweetener_gap_frac")` (name it `GAP_FRAC` in v3 to match `GAP_THR`), pass `gap_frac=_GAP_FRAC` to `close_value_gap`, and keep every other argument exactly as today. Where the caller pre-checks the gap before calling the helper, the pre-check uses `gap_close_target` with the same `(gv, rv, _GAP_THR, _GAP_FRAC)` so the early-out and the helper agree.

### 4.1 v3 — `trade_optimizer.generate_pair_trades_v3` (`:706-772`)

| Line | Today | Change |
|---|---|---|
| `:710` | `GAP_THR = _c("sweetener_gap_threshold")` | unchanged |
| `:711` | `if GAP_THR > 0 and cards:` | unchanged; **inside** this block add `GAP_FRAC = _c("sweetener_gap_frac")` and `dropped: set[str] = set()` |
| `:728-736` | `close_value_gap(card.give_player_ids, …, extra_ok_fn=_gap_extra_ok)` | add `gap_frac=GAP_FRAC` |
| `:740-741` | `if new_key in card_keys:      # would collide with a sibling card` / `continue` | **Collision rule:** `if new_key in card_keys:` → `if GAP_FRAC > 0: dropped.add(card.trade_id); card_keys.discard((frozenset(card.give_player_ids), frozenset(card.receive_player_ids)))` then `continue` (both branches `continue`; at `GAP_FRAC <= 0` nothing else happens — byte-identical) |
| `:772` | `return cards` | `if dropped: cards = [c for c in cards if c.trade_id not in dropped]` before the return. Do **not** mutate `cards` inside the `for card in cards` loop. |

Why drop-after-loop is safe: `card_keys` is pre-populated with **every** organic key (`:712-713`) before the loop, so a collision is always against a card that is in `cards` and stays in `cards` (a sweetened card can only collide with a key that has one more asset than its own bare key, and nothing in the loop removes a sibling). Net effect per collision: exactly one card fewer, the balanced sibling kept.

**No backfill** (Planner ruling 2): the pair returns `max_cards − collisions` cards. The next-best candidate lives in `scored` above the diversity walk (`:647-657`) and re-entering that walk after the 3.4 rescue (`:662-702`) and the gap pass is not justified — the served deck is over-generated and globally ranked in `_dedup_and_sort` (`trade_service.py:6449`, `:4902-4926`), so a per-pair count is a generation budget, never a deck cap (D-154). Recorded in D-173 (unshipped parallel build; see D-175)'s consequences. The collision fixture is `_v3_cards` at `max_cards=2` (`test_gap_sweetener.py:314-318`): the rescue appends `[G1, G2, X1] → [R]` with `card.sweetener` (`:700-701`), and the gap pass on the organic `[G1, G2] → [R]` collides at `:741`.

### 4.2 v2 divergence — `trade_service._generate_for_pair_v2` (`:6905-6983`)

| Line | Today | Change |
|---|---|---|
| `:6905` | `_GAP_THR = _c("sweetener_gap_threshold")` | add `_GAP_FRAC = _c("sweetener_gap_frac")` beside it |
| `:6926` | `if _GAP_THR > 0:` | unchanged — every frac use below is inside this block |
| `:6927-6935` | `close_value_gap(give_ids, recv_ids, …, extra_ok_fn=_gap_extra_ok)` | add `gap_frac=_GAP_FRAC` |
| `:6940` | `if new_key not in _picked_keys:` (no `else`) | **add** `else: if _GAP_FRAC > 0: continue` — the bare card is **not built and not appended** (`:6960` / `:6983` never reached for it). At `_GAP_FRAC <= 0` the fall-through is byte-identical (bare card built and appended unsweetened). |

`_picked_keys` is pre-populated with all `ranked[:max_cards]` keys (`:6921-6922`), so the sibling the bare card yields to is always one of the cards this loop emits. `cards.append(card)` at `:6983` is unchanged.

### 4.3 consensus — `trade_service._generate_consensus_for_pair._emit` (`:7101-7230`)

| Line | Today | Change |
|---|---|---|
| `:7101` | `_GAP_THR = _c("sweetener_gap_threshold")` | add `_GAP_FRAC = _c("sweetener_gap_frac")` beside it |
| `:7102` | `from .trade_optimizer import close_value_gap as _close_gap` | also import `gap_close_target` (lazy, same line/statement — the module cycle reason at `:7096-7098` applies) |
| `:7204` | `if _GAP_THR > 0 and abs(gv - rv) > _GAP_THR:` | `if _GAP_THR > 0 and abs(gv - rv) > gap_close_target(gv, rv, _GAP_THR, _GAP_FRAC):` — `_GAP_THR > 0` stays the **left** operand |
| `:7205-7224` | `_close_gap(give_ids, recv_ids, …, give_candidates=give_pool, recv_candidates=recv_pool, extra_ok_fn=_gap_gates_ok)` | add `gap_frac=_GAP_FRAC`; pools (`:7222-7223`) and gates unchanged |
| `:7228` | `if n_key not in seen:` (no `else`) | **add** `else: if _GAP_FRAC > 0: return` — `_emit` returns without emitting the bare card. At `_GAP_FRAC <= 0` the fall-through (bare card emitted unsweetened) is byte-identical. |

Note on `seen` here vs `_picked_keys` in 4.2: `seen` is filled incrementally (`seen.add(key)` at `:7196`), so a collision can only be with a sibling emitted **earlier** in enumeration. The enumerator runs **all 1×1s first, then 2×1s, then (both-ways only) 1×2s** (`:7265-7271`, `:7273-7279`, `:7289-7295`), so for a 1×1 bare the organic `[G, X1] → [R]` sibling is never already in `seen`: the bare sweetens in place, its sweetened key is added to `seen` (`:7234`), and the later organic sibling is dropped as a duplicate at `:7138-7139` — that path already exists today and needs no change. **The new `else: return` is reachable, but only in one shape: two bares that close to the *same* combo** — `[A] → [R]` closed with `B` yields key `{A, B} → {R}`, then `[B] → [R]` closed with `A` yields the same key, already in `seen`. Without the branch the second bare would be emitted bare beside the balanced card; with it, it is skipped. The branch is therefore **not dead** — do not omit it. The contract is stated at the **outcome level** (Planner ruling 1): *after `_emit` enumeration, at most one card carries the balanced key and no bare card survives whose balanced key is present.* Do **not** pre-populate `seen` to make the site order-independent (a second enumeration pass for no observable gain). The survivor's annotation differs by path — in-place carries `gap_sweetener` + the R-C marker, an organic sibling carries neither — which is why PRD T-7 asserts keys, not annotations.

### 4.4 gen_v2 (arm C) — `trade_gen_v2._pair_survivors` (`:589`, `:737-802`)

| Line | Today | Change |
|---|---|---|
| `:127` | `from .trade_optimizer import (…)` | add `gap_close_target` to the import list |
| `:589` | `_GAP_THR = _c("sweetener_gap_threshold")` | add `_GAP_FRAC = _c("sweetener_gap_frac")` beside it |
| `:737` | `if _GAP_THR > 0:` | unchanged |
| `:738-739` | `_gv, _rv = _consensus_packages(give_ids, recv_ids, cval)` / `if abs(_gv - _rv) > _GAP_THR:` | `if abs(_gv - _rv) > gap_close_target(_gv, _rv, _GAP_THR, _GAP_FRAC):` |
| `:740-794` | `close_value_gap(give_ids, recv_ids, seed_value=cval, gap_threshold=_GAP_THR, fairness_threshold=0.0, …, give_candidates=user_assets, recv_candidates=extras_all, extra_ok_fn=_gap_gates_ok)` | add `gap_frac=_GAP_FRAC`; **keep `fairness_threshold=0.0`** (`:746` — arm C's band is re-earned inside `_gap_gates_ok`, comment `:743-745`) |
| collision | — | **No collision rule, deliberately** (Planner ruling 3 confirms). Arm C sweetens inside `_pair_survivors` at enumeration (`:737-802`; `s_give, s_recv` rebound at `:802`) *before* `_dedup_batch` (`:857-882`), so **a closable bare never reaches dedup as bare** — it arrives already balanced, and its exact-key duplicate with an organic `[G, X1] → [R]` collapses at `:863-867` (the two differ only in annotation). An *unclosable* bare with an organic balanced sibling cannot occur: the sibling passed `filler_ok` / `g6_*` / ε / band with X1 (`:657-706`), so `_gap_gates_ok` (`:591-628`) accepts X1 for the bare too — unless a cheaper asset closed first, which yields a *different* balanced sibling at Jaccard 0.5 < `gen2_dedup_jaccard` 0.6 (`trade_service.py:734`), both kept. A per-emit collision rule would be a second, redundant dedup. `_gap_gates_ok` (`:594-595`) re-tests the sweetened key against `past_decision_keys` — unchanged. **PRD T-4a (arm C) asserts the outcome:** no surviving card for R is bare with gap > eff. |

## 5. Arm A master-switch ordering

Contract: **no frac-dependent branch is evaluated while `sweetener_gap_threshold ≤ 0`.** Per arm, the guard that guarantees it:

| Arm | Guard (unchanged line) | Frac use sits… |
|---|---|---|
| v3 | `trade_optimizer.py:711` `if GAP_THR > 0 and cards:` | inside the block (read at its top, used at the call and the collision) |
| v2 divergence | `trade_service.py:6926` `if _GAP_THR > 0:` | inside the block |
| consensus | `trade_service.py:7204` `if _GAP_THR > 0 and abs(gv - rv) > gap_close_target(...)` | right operand of the `and`; the `_close_gap` call and the `:7228` `else` are inside the block |
| gen_v2 | `trade_gen_v2.py:737` `if _GAP_THR > 0:` | inside the block |

`bakeoff_profiles.MODEL_A_PROFILE` (`:105`, `"sweetener_gap_threshold": 0.0`) therefore pins arm A without listing the new key; `backend/tests/test_bakeoff_arm_a_golden.py` stays green with **one token added to `_PINNED_KNOBS`** (`:527`) plus the scope-phase2 exclusion row (§1, "Arm A bookkeeping") — its golden capture is untouched — and PRD T-5 proves the switch beats the frac on every arm.

**One declared re-spec (mini-round, Gap 2):** `backend/tests/test_gap_sweetener_arm_c.py::test_arm_c_kill_value_is_a_byte_identical_no_op` asserts `deck(10 ** 9) == off` (`:239`) — i.e. "a huge absolute threshold ≡ off". That invariant is **retired by this item**: with `sweetener_gap_frac` at its default, `eff = min(1e9, 0.10 × max)` fires, which is the feature working as specified. The builder pins `ts._cfg["sweetener_gap_frac"] = 0.0` for the `10 ** 9` leg only, with a dated `# D-173 (unshipped parallel build; see D-175) (2026-09-02)` comment stating why; the `deck(0.0)` and `deck(-1.0)` legs (`:235`, `:238`) — the real master switch — are unchanged. Recorded in PRD T-10 and TEST_LEDGER. (Reading `_c("sweetener_gap_frac")` beside `_GAP_THR` at `:6905`/`:7101`/`:589` is permitted — the read has no side effects; the *behavioural* dependency is what sits behind the guard.)

## 6. Payload — `trade_card_to_dict` mirrors `gap_sweetener` into `sweetener`

`backend/server.py` `trade_card_to_dict` (`def :11755`). Today (`:11810-11820`):

```python
    sweetener = getattr(card, "sweetener", None)          # :11812
    if sweetener:
        out["sweetener"] = sweetener                       # :11814
    ...
    gap_sweetener = getattr(card, "gap_sweetener", None)  # :11818
    if gap_sweetener:
        out["gap_sweetener"] = gap_sweetener               # :11820
```

Insert **immediately after `:11820`** (before the F3 `retest` block at `:11821`):

```python
    # #414 (2026-09-02) — a gap-sweetened card also carries the Tier-3
    # `sweetener` marker so the shipped "+ X added to balance the deal"
    # line renders on iOS/web with no client change. Tier-3 wins when both
    # are set; `gap_sweetener` is still serialised in full beside it.
    if not sweetener and gap_sweetener:
        out["sweetener"] = {"player_id": gap_sweetener["player_id"],
                            "side": gap_sweetener["side"]}
```

Precedence and byte-identity, as the contract:

| Card state | `sweetener` on the wire | `gap_sweetener` on the wire |
|---|---|---|
| Tier-3 `sweetener` set, `gap_sweetener` None | the Tier-3 dict, unchanged | absent |
| Tier-3 None, `gap_sweetener` set | `{"player_id", "side"}` copied from `gap_sweetener` (only those two keys — no `gap_before`/`gap_after`) | the full 4-key dict, unchanged |
| both set (a v3 card rescued by 3.4 then gap-closed) | the Tier-3 dict (wins) | the full dict |
| neither | absent | absent — **byte-identical** payload |

`TradeCard.sweetener` / `.gap_sweetener` (`trade_service.py:4286`, `:4295`) are untouched; the impression stamp `features_json.gap_sweetener` (`server.py:4519-4524`) is untouched. Client side needs nothing: `mobile/src/api/trades.ts:86-95` validates `{player_id: string, side: 'give'|'receive'}` → `TradeCard.tsx:235-240` resolves the player → renders the line at `:734`/`:766`; web `web/js/app.js:3655-3665`. `git grep gap_sweetener mobile/src web` = 0 hits — clients never read the gap dict, which is why the mirror is needed.

## 7. Invariants that must survive

- **The pass never empties a deck.** It replaces a card in place (all arms) or, with frac > 0, drops a bare card **only when its balanced sibling is already in the same emitted set** (§4.1–4.3). Each collision removes exactly one card and leaves the sibling; a deck of one bare card with no sibling is served bare or sweetened, never removed. Unclosable cards are kept unsweetened (`close_value_gap` returns `None` → `continue`/fall-through, unchanged).
- **The pass never widens a served gap relative to D-143.** Tier 2 (§3) returns exactly the candidate the absolute rule would have returned whenever no candidate reaches `eff`, so every card D-143 closed is still closed to at least the same gap; the proportional trigger only adds closures. A tier-2 result may carry `gap_after > eff` (still ≤ `gap_threshold`); it is annotated (`gap_sweetener`) and marked (R-C `sweetener`) exactly like a tier-1 result.
- **Collision outcome invariant (all arms, stated at the key level):** after an arm finishes its pair, at most one card carries any given balanced key, and no bare card survives whose balanced key is present. v3 and v2 enforce it with the explicit drop; consensus with the in-place path + `:7138-7139` dedup + the `else: return`; arm C with `_dedup_batch`. Annotation on the survivor is path-dependent and not part of the invariant.
- **The viewer never pays to balance a card they were winning (consensus).** `_gap_gates_ok`'s `user_gain_epsilon` re-check (`trade_service.py:7114`) rejects any equalizer that pushes `gv` above `rv`, so on a viewer-favoured card the closable window is `(gap − eff, gap]` of equalizer contribution; an overshoot serves the card bare. Pinned by PRD T-4a-ov. (v2/v3 have no such sign rule — their `_gap_extra_ok` uses the both-side surplus floor instead.)
- **Untouchables / not-interested are never balancing pieces** — `trade_optimizer.py:905-908`, unchanged, on every arm and for both triggers.
- **Every arm's own gate stack is re-earned** by the existing `extra_ok_fn` closures: v3 `_gap_extra_ok` (`trade_optimizer.py:715-725`: `filler_ok`, `pick_swap_ok`, presentment, `_gap_ok`, both-side surplus ≥ `MIN_SIDE`); v2 `_gap_extra_ok` (`trade_service.py:6907-6918`); consensus `_gap_gates_ok` (`:7104-7129` — includes `user_gain_epsilon` at `:7114`, `consolidation_raw_loss_frac`, `user_gain_ok_1for1`, `pick_swap_ok`, `filler_ok`, presentment — so on a consensus card the equalizer can never push the viewer below even); gen_v2 `_gap_gates_ok` (`trade_gen_v2.py:591-…`, includes the `past_decision_keys` re-test at `:594-595`). The `filler_ok` floor (`trade_service.py:2008-2042`: piece ≥ max(`filler_min_frac` 0.25 × headliner, `asset_floor_abs` 450)) is what makes "smallest sufficient" honest — for a ~6k headliner the equalizer is ≥ ~1.5k.
- **Past decisions and R4 exclusions re-apply after sweetening**: v2/v3 cards flow through `_dedup_and_sort` (`trade_service.py:4902-4926`) which filters `_past_decision_keys` and `_exclusion_keys` on the *sweetened* key; gen_v2 re-tests inside `_gap_gates_ok` (`trade_gen_v2.py:594-595`).
- **Ids:** engine cards mint `trade_id` at creation (`trade_optimizer.py:617`, `trade_service.py:6961`, `:7244`, `trade_gen_v2.py:1193`) and a sweetened card keeps its id — unchanged. Nothing here touches `fairpk_` (`server.py:12398`) or `calcq_` ids.
- **`gap_sweetener` dict shape** `{player_id, side, gap_before, gap_after}` (`trade_optimizer.py:765-769`, `trade_service.py:6943-6947`, `:7229-7233`, `trade_gen_v2.py:797-801`) is unchanged; `gap_before` is still the original card's gap, `gap_after` the closed one — both now measured against `eff` ≤ 1539.
- **Byte-identity at `sweetener_gap_frac ≤ 0`** on every arm and on the payload (PRD T-3, T-4b, T-8).

## 8. Touch-point index

| File | Symbol | Lines (today) | Kind |
|---|---|---|---|
| `backend/trade_service.py` | `_DEFAULT_CFG["sweetener_gap_frac"]` | insert after `:516` | NEW key |
| `backend/database.py` | `_MODEL_CONFIG_DEFAULTS` row | insert after `:2445` | NEW row |
| `backend/trade_optimizer.py` | `gap_close_target` | above `:840` | **NEW function** |
| `backend/trade_optimizer.py` | `close_value_gap` — `gap_frac` kwarg; `eff` at `:890-891`; two-tier accept around `:931-932` (`:918` unchanged) | `:840-933` | changed |
| `backend/trade_optimizer.py` | `generate_pair_trades_v3` gap block — frac read, `gap_frac=`, collision drop, filter before `return cards` | `:710-772` | changed |
| `backend/trade_service.py` | `_generate_for_pair_v2` gap block — frac read, `gap_frac=`, collision `else: continue` | `:6905`, `:6926-6940`, `:6983` | changed |
| `backend/trade_service.py` | `_generate_consensus_for_pair._emit` — frac read, `gap_close_target` import + pre-check, `gap_frac=`, collision `else: return` | `:7101-7102`, `:7204-7228` | changed |
| `backend/trade_gen_v2.py` | import; `_pair_survivors` (`def :509`) gap block — frac read, pre-check, `gap_frac=` | `:127`, `:589`, `:737-794` | changed |
| `backend/server.py` | `trade_card_to_dict` — mirror block | insert after `:11820` | changed |
| `backend/bakeoff_profiles.py` | `MODEL_A_PROFILE` | `:98-105` | **untouched** (by design) |
| `backend/tests/test_gap_sweetener_frac.py` | PRD §6 T-1…T-9 + T-4a-ov + T-11/T-12 (21 functions / 26 node ids) | — | **NEW file** |
| `backend/tests/test_bakeoff_arm_a_golden.py` | `_PINNED_KNOBS` — add the token `sweetener_gap_frac` | `:527` (set body) | changed (one token; golden capture untouched) |
| `docs/plans/three-model-bakeoff/scope-phase2.md` | knob-disposition table — exclusion row for `sweetener_gap_frac` ("inert companion", after the `sweetener_gap_threshold` row) | after `:123` | changed (one row) |
| `backend/tests/test_gap_sweetener_arm_c.py` | `test_arm_c_kill_value_is_a_byte_identical_no_op` — pin `sweetener_gap_frac = 0.0` on the `10 ** 9` leg only, dated D-173 (unshipped parallel build; see D-175) comment | `:239` | **declared re-spec** (the only test edit) |
| `backend/tests/test_gap_sweetener.py`, `test_engine_quality.py:247-281`, `test_knockout_refine.py`, `test_shape_knob.py`, `test_bakeoff_challenger.py` | — | — | must stay green **untouched** (the four `test_gap_sweetener.py` legacy asserts at `:235`, `:330`, `:368`, `:431` are what tier 2 keeps green) |

File ownership is disjoint from G-413 (`backend/server.py:16155-16282`, `:27715-27834`, `mobile/src/components/SendInSleeperButton.tsx`). **Mobile: no change. Web: no change.**

## 9. Addendum (2026-09-02, build-time): `_gap_extra_ok` re-earns #360 avoid on receive-side equalizers

`close_value_gap`'s `extra_ok_fn` on v3 and v2 checked the fairness/filler/overpay gates but not `avoid_ok` (#360); the 3.4 rescue does. With the proportional trigger the pass fires on fixtures where the only equalizer is an avoided-position player, and `test_avoid_positions.py:391` caught it. Contract: every receive-side equalizer candidate passes `avoid_ok(p, players, avoid_positions)` on every arm; give-side candidates are exempt (the viewer's own roster). See PRD §14 G-8.
