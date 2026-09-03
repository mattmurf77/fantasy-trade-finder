# Code-walk proof — G-414 (#414 / D-173 (unshipped parallel build; see D-175)): proportional gap-sweetener trigger

> D-056 static evidence for the five PRD §6.3 targets. Every cite is against branch
> `feat/fb414-lopsided-one-for-one-backend` after the orchestrator's Gap-1/2/3 rulings
> (two-tier accept; declared re-spec of the arm-C 1e9 leg; `_PINNED_KNOBS` row).
> Companion evidence: `backend/tests/test_gap_sweetener_frac.py` (25 node ids, every
> named sabotage proven RED) and the existing seven suites green untouched except the
> two declared edits.

## Table of contents

- [(a) Four callers, one `eff`](#a-four-callers-one-eff)
- [(b) Arm A guard order](#b-arm-a-guard-order)
- [(c) The collision branch per arm](#c-the-collision-branch-per-arm)
- [(d) Past decisions and R4 exclusions re-apply to the sweetened key](#d-past-decisions-and-r4-exclusions-re-apply-to-the-sweetened-key)
- [(e) R-C serialisation precedence and the unchanged client path](#e-r-c-serialisation-precedence-and-the-unchanged-client-path)
- [(f) G-8 — the gap pass re-earns #360 avoid on receive-side equalizers](#f-g-8--the-gap-pass-re-earns-360-avoid-on-receive-side-equalizers)
- [Appendix — the two-tier accept (Gap-1 ruling)](#appendix--the-two-tier-accept-gap-1-ruling)

---

## (a) Four callers, one `eff`

**The helper.** `backend/trade_optimizer.py:855-867` `gap_close_target(gv, rv, gap_threshold, gap_frac=0.0)`:
`gap_frac <= 0` → `gap_threshold`; else `min(gap_threshold, gap_frac * max(gv, rv))`. Pure, no
config read. `close_value_gap` (`:870-875`, new keyword `gap_frac: float = 0.0` last) prices the
original card at `:932` via `_consensus_packages`, computes **`eff` once** at `:933`, and triggers at
`:934` (`abs(gv - rv) <= eff → return None`). `eff` is never recomputed inside the candidate walk
(`:959-987`).

**Every caller reads the knob through `_c`** (`trade_service.py:1239-1245` — thread-local overlay →
`_cfg` → `_DEFAULT_CFG`) and hands it to the helper:

| Arm | `_c("sweetener_gap_frac")` read | `gap_frac=` passed | Pre-check (if any) |
|---|---|---|---|
| v3 `generate_pair_trades_v3` | `trade_optimizer.py:715` (`GAP_FRAC`) | `:745` | none — the helper's own trigger at `:934` |
| v2 divergence `_generate_for_pair_v2` | `trade_service.py:6915` (`_GAP_FRAC`) | `:6946` | none — helper trigger |
| consensus `_generate_consensus_for_pair._emit` | `trade_service.py:7120`; lazy import of `gap_close_target` at `:7121-7122` | `:7249` | `:7227-7228` `abs(gv - rv) > gap_close_target(gv, rv, _GAP_THR, _GAP_FRAC)` |
| gen_v2 / arm C `_pair_survivors` | `trade_gen_v2.py:591`; import at `:133` | `:800` | `:743-744` `abs(_gv - _rv) > gap_close_target(_gv, _rv, _GAP_THR, _GAP_FRAC)` |

**The two pre-checks compute the same `eff` the helper computes.** Both price the card with the
identical functional: gen_v2 calls `_consensus_packages(give_ids, recv_ids, cval)` at `:740` — the
very function the helper calls at `trade_optimizer.py:932`; the consensus `_emit` computes `gv, rv`
with `package_value_v2(gvals, v_max, n_other=…, other_values=…)` at `trade_service.py:6389-6392`,
which is `_consensus_packages`'s body verbatim (`trade_optimizer.py:108-117`: `v_max = max(gvals +
rvals)`, then the same two `package_value_v2` calls). Same `(gv, rv)`, same `_GAP_THR`, same
`_GAP_FRAC` → `gap_close_target` returns the same number on both sides of the call, so an early-out
and a helper `None` can never disagree. (Sabotage S-4a on the consensus site — pre-check reverted to
`> _GAP_THR` and the kwarg dropped — leaves the London card bare; proven RED.)

## (b) Arm A guard order

Contract: no frac-dependent branch is evaluated while `sweetener_gap_threshold <= 0`.

| Arm | Master-switch guard (unchanged line) | Where the frac is used |
|---|---|---|
| v3 | `trade_optimizer.py:711` `if GAP_THR > 0 and cards:` | the read at `:715`, the kwarg at `:745` and the collision at `:750-754` are all **inside** that block |
| v2 divergence | `trade_service.py:6936` `if _GAP_THR > 0:` | kwarg `:6946`, `else: continue` `:6969-6976` — inside |
| consensus | `trade_service.py:7227` `if _GAP_THR > 0 and abs(gv - rv) > gap_close_target(…)` | `_GAP_THR > 0` is the **left** operand of the `and`, so `gap_close_target` is not evaluated when it is false; the `_close_gap` call (`:7229-7249`) and the `else: return` (`:7262-7269`) are inside the block |
| gen_v2 | `trade_gen_v2.py:739` `if _GAP_THR > 0:` | pre-check `:743-744` and kwarg `:800` inside |

The read of `_c("sweetener_gap_frac")` beside `_GAP_THR` at `trade_service.py:6915`, `:7120` and
`trade_gen_v2.py:591` has no side effects; the behavioural dependency sits behind the guard. On v3
even the read is inside the guard (`:715`).

`backend/bakeoff_profiles.py:105` still pins `"sweetener_gap_threshold": 0.0` and the new key is
**absent** from `MODEL_A_PROFILE` (diff of that file: none). Arm A's knob registry now lists it as an
inert companion — `backend/tests/test_bakeoff_arm_a_golden.py` `_PINNED_KNOBS` (Gap-3 ruling) and
the exclusion row in `docs/plans/three-model-bakeoff/scope-phase2.md` beside `package_floor_cross`.
`test_master_switch_beats_frac` runs all four arms at threshold 0 / frac 0.10 and asserts every card
for R is bare. Sabotage S-5′ as written in the PRD (helper returns `frac × max` when threshold ≤ 0
**and** every caller guard becomes `THR > 0 or FRAC > 0`) is **inert under the two-tier accept** —
the walk's D-143 bound at `:969` (`residual > gap_threshold → continue`) rejects every candidate at
threshold 0 — so it was completed as **S-5″**: the same implementation with the walk bound also
treating `gap_threshold <= 0` as unset. S-5″ is proven RED (`consensus sweetened under the master
switch`).

## (c) The collision branch per arm

- **v3** — `trade_optimizer.py:750` `if new_key in card_keys:` (unchanged test). New: `:751-753` —
  when `GAP_FRAC > 0`, `dropped.add(card.trade_id)` and the bare key is discarded from `card_keys`;
  `:754` `continue` in both cases (at `GAP_FRAC <= 0` nothing else happens — byte-identical). The
  `dropped` set is declared at `:719` before the loop; `:784-785` filters `cards` **once after the
  loop**, immediately before `return cards`. Nothing mutates `cards` inside `for card in cards`
  (`:735`). Safe because `card_keys` is pre-populated with every organic key at `:720-721`, so a
  collision is always with a card that is in `cards` and stays there. Sabotage S-7b (`cards.remove`
  mid-loop) skips the element after the bare — `test_sibling_wins_over_bare_when_frac_on_v3`
  places a second closable card there and is proven RED; S-7a (today's `continue`, keep both) RED.
- **v2 divergence** — `trade_service.py:6951` `if new_key not in _picked_keys:` (unchanged). New
  `else:` at `:6969-6976`: `if _GAP_FRAC > 0: continue` — the bare `TradeCard(...)` at `:6978` is
  never built and `cards.append(card)` at `:7001` never reached for it. `_picked_keys` holds every
  `ranked[:max_cards]` key (`:6931-6932`), so the sibling the bare yields to is always one this loop
  emits. Sabotage S-7a (branch neutered) proven RED by `…_v2`.
- **consensus** — `trade_service.py:7253` `if n_key not in seen:` (unchanged). New `else:` at
  `:7262-7269`: `if _GAP_FRAC > 0: return` from `_emit` without emitting the bare card. Reachable
  only when two bares close to the **same** combo (1×1s enumerate before 2×1s, so an organic
  `[G, X1] → [R]` is never already in `seen` when `[G] → [R]` is emitted — that bare sweetens in
  place at `:7254-7261` and the later organic sibling dies as a duplicate at the existing `seen`
  check). Outcome invariant (PRD R-A2.7): at most one card per balanced key, no bare surviving
  beside its balanced key — `seen` is deliberately not pre-populated.
- **gen_v2 — no collision rule, by design.** Arm C sweetens inside `_pair_survivors` at enumeration
  (`trade_gen_v2.py:739-808`; `s_give, s_recv = _ng, _nr` rebound at `:808`) **before** `_dedup_batch`
  (`:863`), so a closable bare never reaches dedup as bare; its exact-key duplicate with an organic
  `[G, X1] → [R]` collapses there (the two differ only in annotation). `test_arm_c_frac_card_is_
  sweetened_at_default` asserts the outcome: no surviving card for R is bare with gap > its `eff`.

## (d) Past decisions and R4 exclusions re-apply to the sweetened key

- **v2 / v3** cards are collected by `generate_trades` and passed through `_dedup_and_sort`
  (`trade_service.py:4911`; call sites `:4871`, `:4898`, `:6441`). Inside, `:4920` builds
  `_r4_keys` from `self._exclusion_keys` and `:4921-4928` drops any card whose
  `(frozenset(give), frozenset(recv))` is in `self._past_decision_keys` or `_r4_keys`. The key is
  computed from the card's **current** id lists — i.e. the sweetened ones, since v3 rebinds
  `card.give_player_ids/receive_player_ids` at `trade_optimizer.py:762-763` and v2 builds the
  `TradeCard` from the rebound `give_ids, recv_ids` (`trade_service.py:6962`, `:6978-6992`) before
  either reaches `_dedup_and_sort`.
- **gen_v2** re-tests inside the gate closure the sweetener must pass: `trade_gen_v2.py:593`
  `_gap_gates_ok` → `:597` `if (frozenset(g), frozenset(r)) in past_decision_keys: return False`,
  evaluated on the sweetened combo `(g, r)` by `close_value_gap` at `trade_optimizer.py:980`.
  Pinned by the untouched `test_arm_c_sweetened_combo_respects_past_decisions`.
- Untouchables / not-interested are excluded from the candidate universe at
  `trade_optimizer.py:947-951` for both triggers (T-6 proven; S-6 "drop the unclosable" RED).

## (e) R-C serialisation precedence and the unchanged client path

`backend/server.py` `trade_card_to_dict` (`def :11755`):

| Line | Does |
|---|---|
| `:11812` | `sweetener = getattr(card, "sweetener", None)`; `:11813-11814` serialises the Tier-3 dict when set |
| `:11818` | `gap_sweetener = getattr(card, "gap_sweetener", None)`; `:11819-11820` serialises the full 4-key dict when set |
| `:11825-11827` **new** | `if not sweetener and gap_sweetener: out["sweetener"] = {"player_id": …, "side": …}` — exactly two keys, only when no Tier-3 marker exists |

Precedence: Tier-3 wins when both are set (the `not sweetener` test), `gap_sweetener` is always
serialised in full beside the mirror, and a card with neither is byte-identical (no key touched).
`test_payload_mirrors_gap_sweetener_into_sweetener` pins all three states; S-8a (unconditional
overwrite) and S-8b (whole dict) proven RED.

Client path, unchanged and never reading `gap_sweetener` (`git grep gap_sweetener mobile/src web` = 0):
`mobile/src/api/trades.ts:86-95` validates `raw.sweetener` as `{player_id: string, side: 'give'|'receive'}`
→ `mobile/src/components/TradeCard.tsx:235-240` resolves `sweetenerPlayer` from the matching side →
renders "+ {name} added to balance the deal" at `:732-734` (give) / `:764-766` (receive). Web:
`web/js/app.js:3655-3657` reads `card.sweetener.player_id` / `.side` the same way.

## (f) G-8 — the gap pass re-earns #360 avoid on receive-side equalizers

Surfaced by `test_avoid_positions.py:391` going red at the new default (the D-143 pass never
re-checked #360; the absolute trigger simply never fired on that fixture). #360 is a HARD
receive-side exclusion on every path (`config/features.json` `_comment_trade_avoid_positions`).
Give-side equalizers are the viewer's own players — avoid does not apply. The four sites:

| Arm | Coverage |
|---|---|
| v3 | `trade_optimizer.py:732-737` — `_gap_extra_ok` now rejects any receive-side piece failing `avoid_ok(p, players, _avoid)` (`_avoid` from `:385`; same predicate the 3.4 rescue passes at `:678`) |
| v2 divergence | `trade_service.py:6927-6932` — same check in its `_gap_extra_ok` (`_avoid` built in `_generate_for_pair_v2`) |
| consensus | **already covered at pool construction, unchanged**: `_avoid` `:7084`, `_opp_pool` filtered by `avoid_ok` `:7085-7087`, `recv_pool = list(_opp_pool)` `:7088`, and the gap pass draws only from `recv_candidates=recv_pool` |
| gen_v2 / arm C | **no #360 concept on this arm at all** — `generate_league_suggestions` (`trade_gen_v2.py:1030-1032`) has no `avoid_positions` parameter and the call site (`trade_service.py:4693-4723`) never passes it, so the organic enumeration is un-gated too. Threading a new parameter through arm C is outside this item; reported as a pre-existing arm-C gap (flag `trade_gen_v2`), not created by #414 |

Evidence: `test_avoid_positions.py` untouched, green by the fix alone; sabotage (remove the check) →
`:391` RED → restore → green (which arm the fixture exercises is recorded in the build report).

## Appendix — the two-tier accept (Gap-1 ruling)

`trade_optimizer.py:959-987`. `fallback = None` (`:959`); per candidate `residual` (`:968`);
`residual > gap_threshold → continue` (`:969`, unchanged D-143 bound); ratio / feasibility /
`extra_ok_fn` gates (`:971-981`, unchanged); then `:983-984` tier 1 (`residual <= eff → return hit`),
`:985-986` tier 2 (first `residual <= gap_threshold` remembered), `:987` `return fallback`. At
`gap_frac <= 0`, `eff == gap_threshold`, so `:983` fires for every candidate `:969` admitted — the
walk returns on the first acceptable candidate exactly as before, byte-identical. The four D-143
fixtures whose only equalizer lands in `(eff, 1539]` (`test_gap_sweetener.py` consensus/v3/v2 at
977.7 and 1336.5) therefore still sweeten, with no test edit.
