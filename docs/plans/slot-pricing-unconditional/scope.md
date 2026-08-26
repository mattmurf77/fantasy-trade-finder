# Feature Scope — Market pick pricing becomes unconditional

**Date:** 2026-08-21
**Entry point:** direct operator ruling (below), closing the implementation half of [Q-023](../../../living-memory/OPEN_QUESTIONS.md)
**Builder:** backend/mobile session on `feat/slot-pricing-unconditional`
**Operator sign-off on waivers:** **NEEDED — two items in §6.** Everything else is answered.

---

## 0. The ruling, verbatim

> **"Market slots should be default and not an opt-in or even an option to flip. Aligned that future picks stay default for now."**
> — operator, 2026-08-21

Two clauses, two consequences:

Plus the operator's clarification of 2026-08-21 on what "market slots" was meant to deliver: **each pick holding *"real value rather than generic"*** — i.e. TRUE PER-SLOT pricing, not merely the round-level market curve.

| Clause | What it means in code |
|---|---|
| *"Market slots should be default"* | `trade_service.pick_pricing_mode_for_user` returns `market_slots` for every user, with no flag read, no session read and no DB read. |
| *"not an opt-in or even an option to flip"* | The per-user setting is **deleted**, not defaulted: the mobile control is removed, `PUT /api/settings/pick-pricing` is 410 Gone, and `trade.slot_pricing` is retired to a never-read key. |
| *"real value rather than generic"* | A pick whose draft slot D-090 resolves prices at **its own DP per-slot value**. A 2026 1.01 is 4867.1 in 1QB where a 1.12 is 820.8 — where both used to be 2117.0. |
| *"future picks stay default for now"* | Future-season picks keep pricing off DP's generic/`Mid` rung for that season. **Zero code change, and no branch**: DP publishes per-slot rows only for the current class, so `market_pick_slot_value` returns `None` for a future season and the waterfall falls through by itself. |

### What Q-023 asked, and which half this answers

Q-023's operator ruling of 2026-08-19 was *"Slot should drive price but we can push this live first and then solve for that."* It left three sub-questions for the implementer:

| Q-023 sub-question | Answered by this change |
|---|---|
| all picks, or only under the opt-in `trade.slot_pricing` mode? | **All picks.** The opt-in is gone. |
| does the SLOT drive the price, or only the label? | **The price.** A resolved slot prices at DP's row for that slot; a 1.01 is 4867.1 where a 1.12 is 820.8. |
| unknown-order leagues → Mid rung, or excluded? | **Mid rung** (the round curve) — unchanged, and now the explicit step-2 fallback rather than the only answer. |
| does the TIER band follow, or only the trade value? | **The badge follows the value** (D-320-2), automatically, because a badge is derived from the served value. **The bands themselves do not move.** Per-slot is where this finally bites: a 1.01 and a 1.12 now badge in different bands. |

**Q-023 is CLOSED, both halves.** The mode question ("all picks, or only an opt-in cohort?") and the pricing question ("should the slot drive the value?") are both answered and both built. What remains deferred is not part of Q-023: it is the league-surface alignment, ruled and sequenced as Q-026 (§6).

---

## 1. What this actually changes

`market_slots` was already built (rookie-draft M6b, operator decision O2) and already `true` in `config/features.json`, gated behind a per-user `users.pick_pricing_mode` that defaulted to `tier_ladder`. In practice **nobody was being repriced**: the shipped default was the ladder, and the only way off it was a Settings row almost nobody would find. This change removes the gate and the setting.

Measured, from the pinned DP snapshot (`backend/tests/fixtures/dp_values_picks_2026-08-06.csv`), ladder → market:

| pick | 1QB ladder | 1QB market | Δ | SF ladder | SF market | Δ |
|---|---:|---:|---:|---:|---:|---:|
| 2026 1st | 2117.0 | 1859.5 | **−12.2 %** | 2117.0 | 2263.3 | +6.9 % |
| 2026 2nd | 606.5 | 434.0 | −28.4 % | 606.5 | 475.2 | −21.6 % |
| 2026 3rd | 406.6 | 262.3 | −35.5 % | 406.6 | 269.3 | −33.8 % |
| 2027 1st | 2117.0 | 1504.6 | −28.9 % | 2117.0 | 1818.5 | −14.1 % |
| 2028 1st | 2117.0 | 1263.0 | **−40.3 %** | 2117.0 | 1518.9 | −28.3 % |
| 2029 4th | 167.4 | 195.2 | **+16.6 %** | 167.4 | 197.4 | +17.9 % |

**The headline is deflation, not inflation.** Every first-round pick except a current-year superflex first gets *cheaper*. Deep-future 4ths are the one place the market is dearer than our uniformly-discounted ladder — which is why `_owned_pick_assets` caps *after* pricing.

### 1.1 The pricing waterfall — three steps, and what each one is for

`pick_values.priced_pool_value` resolves an owned pick's price in three steps, each falling to the next only when it has nothing honest to say:

| step | source | when it applies |
|---|---|---|
| **1** | `market_pick_slot_value(season, round, slot)` — DP's row for that exact slot, e.g. `"2026 Pick 1.03"` | D-090 resolved a real slot: current season, published order, supported platform |
| **2** | `market_pick_pool_value(season, round)` — the mid-tercile round curve | no slot. **Every future-year pick** (DP publishes per-slot rows only for the current class), every unsupported platform, every unpublished or unresolvable order, and every call while `picks.slot_labels` is off |
| **3** | the stored ladder `pool_value` | no market price at all: DP unreachable, or a season it neither publishes nor extrapolates to |

**The slot is resolved once per LEAGUE and passed in.** `server._league_slot_order` (DB-backed, 60 s cache) → `pick_slots.slot_for` — D-090's existing machinery, reused, not reimplemented. `priced_pool_value` runs per PICK and never resolves anything itself. The same resolution drives the label, so a card cannot say "2026 1.03" while charging for a generic first.

**The spread step 1 buys, 1QB, 2026 round 1** (against `dp_values_picks_2026-08-06.csv`):

| slot | per-slot | vs round price (1859.5) | vs ladder rung (2117.0) |
|---|---:|---:|---:|
| 1.01 | **4867.1** | 2.62× | 2.30× |
| 1.02 | 4024.9 | 2.16× | 1.90× |
| 1.03 | 3343.4 | 1.80× | 1.58× |
| 1.04 | 2792.7 | 1.50× | 1.32× |
| 1.05 | 2343.2 | 1.26× | 1.11× |
| 1.06 | 1978.8 | 1.06× | 0.93× |
| 1.07 | 1680.3 | 0.90× | 0.79× |
| 1.08 | 1435.5 | 0.77× | 0.68× |
| 1.09 | 1234.9 | 0.66× | 0.58× |
| 1.10 | 1069.8 | 0.58× | 0.51× |
| 1.11 | 933.8 | 0.50× | 0.44× |
| 1.12 | **820.8** | 0.44× | 0.39× |

A 1.01 is **5.9×** a 1.12. Superflex is dearer again — a 1.01 is 6181.1. Rounds 2–4 deflate at almost every slot (a 2026 2.01 is 727.6 against a 606.5 rung; a 2.12 is 315.5).

**So the direction is no longer "deflation".** It is *dispersion*: the top of round 1 inflates hard, everything else deflates. The round-curve table in §1 still describes step 2, which is what every future-year pick gets.

### 1.2 What this still does NOT do

- **Future-year picks are not per-slot** and cannot be — nobody knows next year's order, and DP publishes no rows for it. This is the operator's explicit "for now".
- **The league surfaces are not repriced.** Power Rankings and `GET /api/league/picks` still serve the stored ladder value. Ruled and deferred — §6.
- **`draft_picks.pool_value` is still never rewritten.** Pricing stays read-time, which is what leaves the ladder recoverable as a harness axis.

## 2. Schema & flag scope

- **New/changed tables or columns:** none. `users.pick_pricing_mode` **stays** as dead data under the additive-schema rule (never drop a column). `docs/data-dictionary.md` row rewritten to say so, and to say a restore of the per-user axis would need no migration. Pinned by `test_db_accessors_survive_as_dead_data`.
- **New/changed feature flags:** none added. **`trade.slot_pricing` is RETIRED** — kept in `FLAG_KEYS` at `true`, never read. Disposition and its reasoning are written at the key itself in `backend/feature_flags.py`, and are the precedent for the next retired flag:

  | Option | Verdict |
  |---|---|
  | Delete from `FLAG_KEYS` + `config/features.json` + all 5 fixtures | **Rejected.** `test_release_flags_mirror_features_json` demands exact equality, so this is a six-file change; worse, the key vanishes from `/api/feature-flags` for builds in the field, and any stored override row silently becomes an unknown key. |
  | Keep at `true`, never read, comment says RETIRED | **Chosen.** Additive, free, honest — the flag reads `true` because market pricing *is* on. |
  | Keep and keep reading it | Rejected — the ruling says "not even an option to flip". |

  D-079's precedent supports this shape: *"the risk is entirely in the number, not in whether the code path runs, so a config knob at its old value is both a more precise and a more reversible kill switch."* Here the equivalent lever is the `tier_ladder` pin, which survives as a harness axis (§3).
- **New env vars / `model_config` keys:** none. **Deploy-free rollback lever:** there is **none for the pricing itself** — see §6, waiver 1.

---

## 3. Analytics scope

**(b) Existing events cover it, minus one retirement.**

- `pick_pricing_mode_changed` **is no longer emitted** — its only emitter was the Settings control, which is deleted. It **stays registered** in `backend/analytics_taxonomy.py` (`ALLOWED_CLIENT_EVENTS` + the props map) and in `analytics_queries.NON_INTENT_EVENTS`, so historical rows stay queryable and a de-registration does not turn old data into "unknown event" noise. Registering-but-not-emitting is the same posture the taxonomy already takes for Phase-2 names.
- No new events. The change is a server-side pricing constant with no new user decision to instrument — there is now nothing for the user to *choose*, which is the whole point of the ruling.
- Existing coverage that answers "did this help?": deck/card events already carry pick composition, and `docs/plans/rookie-draft/build-m6b.md` §4.2 measured the deck churn this repricing causes (154/257 cards in 1QB). Re-running that harness post-merge is the honest read, not a new event.

---

## 4. Cross-client / invariant scope

| Thing | Moves? |
|---|---|
| `GENERIC_PICK_SEEDS` (12 generic rungs) | **No.** Byte-unchanged. Pinned by `test_m6b_04_generic_ladder_byte_unchanged_in_every_mode`. |
| Tier **bands** (absolute Elo, mirrored across 5 clients) | **No.** `backend/tier_config.json` untouched. |
| Owned-pick tier **badges** | **Yes, automatically.** D-320-2: the badge reflects the value served, and the served value moved. No badge code changed. |
| `draft_picks.pool_value` (league-shared column) | **No.** Never written; pricing is read-time. Pinned by `test_m6b_03_read_time_only_never_writes_the_shared_column`. |
| Manual calculator generic picks (`generic_pick_*`) | **No.** They price off the user's own board Elo, not `priced_pool_value`. |

`docs/cross-client-invariants.md` § "Draft-pick slot values" updated: the M6b sentence "only while the flag `trade.slot_pricing` is on (it is off)" was false as of this merge and is replaced.

**Known live inconsistency, surfaced not fixed — see §6, waiver 2.** `_power_picks_by_owner` (Power Rankings) and `GET /api/league/picks` still price off the stored ladder `pool_value`. That is build-m6b deviation **D-7**, which was harmless while market pricing was dark and is now a visible disagreement: the same pick can show one number on the Power Rankings screen and a different one inside a trade card.

---

## 5. Evidence scope

- [x] **Structural guards** — `mobile/tests/check-settings-testids.js` gains a `DELETED_PREFIXES` inventory asserting `settings.pick-pricing.*` generates **no** testIDs anywhere under `src/` (an absence assertion, so a well-meaning revert fails loudly rather than quietly restoring a deleted setting). `mobile/tests/check-settings-ia.js` drops the "Pick pricing segmented" §4 row with the reason inline. Both run in CI via the `mobile-typecheck` job's `check-*.js` glob.
- [x] **Unit tests** — `backend/tests/test_pick_pricing_m6b.py` rewritten around the inverted contract (28 tests):
  - `test_m6b_02_the_flag_is_no_longer_read` — `is_enabled` is monkeypatched to **raise**, proving the flag is not consulted.
  - `test_m6b_02_the_stored_column_is_no_longer_read` — `get_pick_pricing_mode` records calls; asserts zero.
  - `test_mode_for_user_cannot_fail` — the DB accessor raises on sight; the resolver still answers.
  - `test_m6b_05_a_resolved_101_outprices_a_105_outprices_a_112` — **the ruling as one assertion**, with the three prices pinned as literals.
  - `test_m6b_05b_an_unresolved_slot_still_prices_at_the_round_curve` — **the fallback contract**: two unresolved 2026 firsts still price identically.
  - `test_m6b_05c_future_years_ignore_a_slot_because_dp_publishes_none` — "future picks stay default", asserted at both the DP-lookup and the waterfall level, so a snapshot that starts publishing 2027 slots fails loudly instead of silently repricing next year.
  - `test_m6b_05d_per_slot_is_format_aware`, `test_m6b_05e_slot_pricing_falls_soft_at_every_step` — SF dearer; every fallback trigger exercised, including DP unreachable.
  - `test_m6b_05f_the_badge_follows_the_served_value` — D-320-2 walked over the same inverse the clients use; a 1.01 and a 1.12 land in different bands.
  - `test_m6b_05g_the_engine_read_site_applies_the_slot` — **end-to-end through `_owned_pick_assets`**, because a seam nothing calls with a slot would pass every unit test above and still ship generic prices. Also pins that the cap sorts a 1.01 above a 1.12, and that the label agrees with the price.
  - `test_m6b_05h_no_resolved_order_reproduces_the_round_curve_at_the_read_site` — the same read site with no order: round-curve prices, generic labels, byte-identical to pre-extension.
  - `test_route_get_serves_the_fixed_state_for_old_clients`, `test_route_put_is_410_gone_whatever_the_body`, `test_route_still_requires_a_session_on_both_verbs`.
- [x] **New: `backend/tests/conftest.py`** — the first conftest in this repo, and it is *required* by this change, not a convenience. See §5.1.
- [x] **Code-walk proof** — §7.
- [x] **Manual TestFlight checklist** — §8.
- `testID`s added/renamed: **none added; `settings.pick-pricing.*` removed.** `testid-lint.sh` passes (it polices flow→source, and no `.maestro` flow references the id).

### 5.1 The hermeticity hazard this change created

Making pricing unconditional put a **live HTTP GET to DynastyProcess on the hot path of every test that prices an owned pick**. Measured, before the fix, on `test_pick_values_in_suggestions.py`: 4 failures, with a 2029 1st priced at `1459.4` — a real fetch of today's DP data, not the fixture.

Both failure modes are bad and neither is loud:

- **With network** (GitHub Actions): the suite prices off whatever DP published this morning. Pinned assertions become flaky-by-calendar.
- **Without network**: `load_pick_slot_values` fail-softs to `{}`, every pick falls back to the ladder, and the suite passes **for the wrong reason** — proving nothing about the path that ships.

`backend/tests/conftest.py` pins `FTF_DP_PICK_VALUES_FILE` (the seam `data_loader._fetch_pick_values_csv` already honours, and already *requires* under `FTF_TEST_MODE`) to the checked-in `dp_values_picks_2026-08-06.csv`. It uses `setdefault`, so an operator can still point the suite at a newer snapshot, and per-test `monkeypatch.setenv` still overrides and restores. It pins the **pick** curve only; the player curve is untouched because no unconditional path reaches it.

### 5.2 Golden disposition — nothing moved, nothing re-captured

| Golden | Verdict |
|---|---|
| `test_bakeoff_arm_a_golden.py` | **Unmoved.** Every input is a literal (player table, `seed_elo`, `user_elo`, per-opponent `elo_ratings`). Its picks are pseudo-assets `PKu`/`PKo1`/… primed directly into Elo maps; it never constructs a `draft_picks` row and never calls `priced_pool_value`. Immune by construction — which is exactly the property its docstring claims. |
| `test_bakeoff_serving.py`, `test_bakeoff_challenger.py`, `test_bakeoff_composition.py` | Unmoved, same reason. |
| `test_engine_quality_golden.py`, `test_fairness_gate_golden.py`, `test_fit_congruence.py` | Unmoved. |

**156 golden assertions across seven golden files pass with zero edits, before AND after the per-slot extension** (both runs done in isolation, before any fixture was touched). No kill-value pin was needed and no re-capture was performed. Verified by running the six files in isolation before touching any fixture, so this is a measurement rather than an inference.

**Gate interactions** (`overpay`/R1, `sweetener_gap_threshold` = 1539.0, `pick_gap_ok`) all consume pick values and all continued to pass. No tolerance was widened anywhere; the two tests that legitimately moved are named in §5.3.

### 5.3 Tests whose fixtures moved, and why that is honest

`backend/tests/test_pick_values_in_suggestions.py` (#185) derives its expectations from `pick_pool_value(...)` — deliberately, so "a retune moves the fixture with the ladder". That derivation is now wrong for owned picks, because owned picks no longer price off `pick_pool_value`. Fixed by pinning the **inputs** as literals and expecting the **market** price, not by loosening a tolerance.

---

## 6. Waivers requiring operator sign-off

**Waiver 1 — partial deploy-free rollback only, and it arrived by accident.**
D-079 chose a `model_config` knob over a flag precisely so a bad number could be reverted without a deploy. The *mode* has no such lever: it is a Python constant, and the flag that could have been one is retired by the same ruling. Reverting to the ladder means reverting the merge and redeploying.

**But per-slot pricing does have one, as a side effect of reusing D-090.** `_league_slot_order` returns `None` when `picks.slot_labels` is off, so **turning that flag off drops every pick from step 1 to step 2** — the round curve — without a deploy. That is the larger and more surprising half of the repricing, and it is now revertible in seconds.

The cost is a coupling the operator should see plainly: **a flag documented as a display switch now moves prices.** Two ways to resolve it, and this needs a call:
- **(a) Accept and document it** — `picks.slot_labels` becomes "slot labels *and* slot prices". Recommended: it costs nothing, it is the only lever available, and labels and prices moving together is coherent (you never show "2026 1.01" while charging generic).
- **(b) Split it** — add a separate `trade.pick_slot_pricing` flag. Cleaner naming, but it is a new flag on the day we retired one, and the ruling says pricing is not "an option to flip".

**Recommending (a); flagging, not deciding.** Either way `docs/config-reference.md` now says the flag moves prices.

**Waiver 2 — RULED AND DEFERRED, not open.** Power Rankings and `/api/league/picks` disagree with the trade engine.
build-m6b deviation D-7 left `_power_picks_by_owner` and `GET /api/league/picks` on the stored ladder. Dark, that was invisible. Live — and especially under per-slot pricing — it is stark.

**Operator ruling, 2026-08-21:** *"I want the league values to reflect the same pick values.. But let's defer that until after finishing this one."*

So: **this branch ships with the disagreement**, and aligning the league surfaces onto the same per-slot values is the **committed immediate follow-up**, sequenced after this merge. It is not a question awaiting an answer.

**The motivating number, quantified (1QB, 2026):**

| pick | league surfaces say | engine says | gap |
|---|---:|---:|---:|
| **1.01** | 2117.0 | **4867.1** | **+2750.1 (+130 %)** |
| 1.12 | 2117.0 | 820.8 | −1296.2 (−61 %) |
| 2.01 | 606.5 | 727.6 | +121.1 (+20 %) |
| 2.12 | 606.5 | 315.5 | −291.0 (−48 %) |
| 3.01 | 406.6 | 303.2 | −103.4 (−25 %) |
| 4.12 | 272.5 | 229.7 | −42.8 (−16 %) |

**Worst case: a 2026 1.01 reads 2117.0 on the Power Rankings screen and is worth 4867.1 inside a trade card — a 2.3× disagreement about the single most valuable asset a team can hold.** Per-slot made this materially worse than the round curve did (the round curve's worst gap was −13.9 %). It also makes the two surfaces badge the same pick differently, since a badge follows the value it is served (D-320-2).

Scope of the follow-up: route `_power_picks_by_owner` and `GET /api/league/picks` through `priced_pool_value` with the same `_league_slot_order` resolution the engine uses, and re-derive `test_league_picks_tier.py`'s pinned badges — which will move, and should.

---

## 7. Code-walk proof — the mode resolver to every pricing call site

Traced on `feat/slot-pricing-unconditional`. Line numbers are post-change.

**The resolver.** `backend/trade_service.py:1281` —
```python
def pick_pricing_mode_for_user(user_id: str | None) -> str:
    return PICK_PRICING_DEFAULT
```
with `PICK_PRICING_DEFAULT = "market_slots"` at `:1243`. No `is_enabled` import, no `database` import, no branch. `user_id` is accepted and ignored so the two call sites need no signature change.

**The thread-local.** `current_pick_pricing_mode` (`:1248`) returns the pin or `PICK_PRICING_DEFAULT`; `pick_pricing_override` (`:1265`) coerces an unknown mode to `PICK_PRICING_DEFAULT`. Net effect: *every* path — pinned, unpinned, or pinned with garbage — lands on `market_slots` unless a caller explicitly pins the string `"tier_ladder"`. Grep for that string outside tests and harnesses returns nothing.

**Slot resolution, reused not reimplemented.** `server._league_slot_order(league_id)` (D-090) → `pick_slots.slot_for(order, season, round, original_roster_id)`. `slot_for` already refuses a future season (#273), an unknown roster, a malformed blob, and a snake order with an unverifiable reversal round — so "current-year only" and every safety refusal come free rather than being re-derived. `_league_slot_order` also returns `None` when `picks.slot_labels` is off, which is how that flag became a pricing lever (§6, waiver 1).

**Call site 1 — the deck/asset-idea lane.** `backend/server.py:10830`, in `_inject_owned_picks`:
```python
_pp_mode = (_trade_service_mod.pinned_pick_pricing_mode()
            or _trade_service_mod.pick_pricing_mode_for_user(user_id))
with _trade_service_mod.pick_pricing_override(_pp_mode):
    pick_assets = _owned_pick_assets(league_id, scoring_format)
```
`user_id` is still passed and still ignored; the pin is kept because the bake-off harnesses must be able to price a whole job on the ladder. Inside, `_owned_pick_assets` resolves the order **once** (`slot_order = _league_slot_order(league_id)`), then per row computes `pick_slots.slot_for(...)` into `_slots[pick_id]` and passes it to `priced_pool_value(p, scoring_format=..., slot=...)`. It then sorts by the **priced** value and caps — the cap-after-pricing rule, now load-bearing rather than tidy: the ladder cannot rank a 1.01 above a 1.12 at all, so capping on stored values would routinely inject the wrong first.

`_owned_pick_label(p, slot_order)` re-derives the same slot for the label. That redundancy is deliberate and is called out at the call site: `slot_for` is pure and both calls pass identical arguments, so they agree by construction. Threading a precomputed slot into `_owned_pick_label` would mean touching all five of its call sites, four of which have no price to keep in step.

**Call site 2 — the manual calculator.** `backend/server.py:9697`, in `trade_evaluate_route`:
```python
_pp_mode = (_trade_service_mod.pinned_pick_pricing_mode()
            or _trade_service_mod.pick_pricing_mode_for_user(None))
```
Simplified from the old form, which resolved an optional session to read the user's stored mode. That session lookup is **deleted** — Mode A stays public and anonymous callers get the same price as signed-in ones, which they now provably do because there is only one price. The pin wraps `_trade_evaluate_impl`, whose owned-pick read calls `_league_slot_order(league_id)` **once per request** (not per pick — it is DB-backed with a 60 s cache) and threads `pick_slots.slot_for(...)` into each `priced_pool_value` call, the same discipline as the deck lane.

**The seam.** `backend/pick_values.py:priced_pool_value` — `mode=None` resolves the thread-local; `market_slots` runs the three-step waterfall of §1.1. Step 1 is `market_pick_slot_value`, which builds its DP label through `data_loader.pick_slot_label` — **the same formatter the Draft Room's display axis uses**, so the engine and the board can never disagree about which row a slot means. It returns `None` (→ step 2) for a slot DP does not publish, which is every future season, and for any junk slot. Step 2's `market_pick_pool_value` returns `None` (→ step 3) for a season DP neither publishes nor extrapolates to. `load_pick_slot_values` returns `{}` on any fetch/parse failure, so DP being unreachable degrades every pick to today's ladder price, silently. That fail-soft was a nicety when the mode was opt-in; it is now the entire safety net.

Rounds are clamped in exactly one place — `market_pick_pool_value` clamps to DP's published round 5. `market_pick_slot_value` deliberately does **not** clamp: a round-9 slot has no published row and no honest analogue, so it returns `None` and rides step 2's clamp. One clamp, one place, no drift.

**Sites deliberately NOT reached:** `_power_picks_by_owner`, `GET /api/league/picks` (§6 waiver 2), `pick_pool_value` itself (still the ladder, still what writes `draft_picks.pool_value` at sync time), `GENERIC_PICK_SEEDS`, and the rankable generic rungs.

### 7.1 End-to-end proof on a real served card

Card from `docs/reviews/2026-08-19-knockout-waterfall/knockout-survivors.csv:13` — arm B, divergence, `mattmurf77 → jonbonjourvi`:

```
give     Drake Maye + Davante Adams        cons_give = 3862.3   (players, untouched)
receive  2026 1.05 (from Bcork) + 2027 1st cons_recv = 4234.0   (as served, on the ladder)
```

Repriced through `priced_pool_value` in **all three regimes** (1QB, pinned snapshot). This is the operator's proof case:

| asset | ladder (before M6b) | round curve (this branch, step 2) | **per-slot (ships, step 1)** |
|---|---:|---:|---:|
| 2026 **1.05** (from Bcork) | 2117.0 | 1859.5 | **2343.2** |
| 2027 1st *(no slot exists)* | 2117.0 | 1504.6 | 1504.6 |
| **receive total** | **4234.0** | **3364.1** | **3847.8** |
| give total (Maye + Adams) | 3862.3 | 3862.3 | 3862.3 |
| **balance (recv − give)** | **+371.7** | **−498.2** | **−14.5** |

Three things to read off it:

1. **The ladder column reproduces the CSV's `cons_recv` of 4234.0 exactly**, which is what makes this a check rather than an illustration.
2. **The round curve alone overshot.** It priced the 1.05 at the generic 1859.5 — *below* the ladder — and swung the card from +371.7 to −498.2. Per-slot puts the 1.05 back at its real 2343.2 and lands at −14.5: a card that is now honestly, almost exactly, even money.
3. **The 2027 first is identical in the last two columns**, because no slot exists for it. That single row is the operator's "future picks stay default for now", visible in the arithmetic.

---

## 8. Manual TestFlight checklist (operator)

Backend-only pricing plus one removed Settings row. Runtime proof genuinely matters for the pricing, because no structural test can see a served deck.

1. **Settings → Trade values.** Expect: the **Stud tax** segmented control, and **nothing below it**. The "Pick pricing" row (Tier ladder / Market) must be gone entirely — not greyed, not empty-stated. *Regression this catches: the row surviving in the legacy flat screen, which is a separate file from the v2 section.*
2. **Calculator — THE HEADLINE TEST. Two of your own 2026 firsts, if you hold picks at both ends of the round.** Put a high-slot first on one side and a low-slot first on the other. Expect them **NOT to cancel**: a 1.01 should read near **4867** (1QB) / **6181** (SF) and a 1.12 near **821** / **950**. *This is the operator's ruling in one screen. If they cancel, the slot is not reaching the price and the whole extension is inert.*
3. **Check the label matches the price.** A pick priced at ~4867 must be labelled "2026 1.01", not "2026 1st". *Catches the price and the label being derived from different resolutions — the one failure mode that would look plausible on each screen alone.*
4. **Calculator, a mid first.** A 1.05-ish pick should read near **2343** (1QB) — above the old flat 2117.0, where a 1.08 (1435) is below it. *Catches a sign error in the slot mapping: if 1.01 and 1.12 are swapped, this row still looks reasonable but the ends are inverted.*
5. **Calculator, far-future first.** A 2028 or 2029 first should read near **1263.0** (1QB), down from 2117.0, and should show a generic "2028 1st" label. *Catches the future-year fallback — it must NOT pick up a slot.*
6. **A league with no published draft order** (or an unsupported platform). Its 2026 firsts should all read the same **1859.5** and label generically. *Catches step 2, the fallback contract — the thing most likely to break silently.*
7. **Generate a fresh deck** on a league that holds picks. Expect visibly different pick-bearing cards than your last deck, and expect your best pick to appear in more of them. *Catches `_inject_owned_picks` not pinning, and the cap sorting on stale values.*
8. **Pick tier badges in a trade card.** A 1.01 and a 1.12 should now badge **differently** — that is D-320-2 working, not a bug.
9. **Known inconsistency, confirm don't report:** the **Power Rankings** screen still shows the old ladder numbers (2117.0 for every 2026 first). Under per-slot the worst gap is a 1.01 reading 2117.0 there and 4867.1 in a trade card. Ruled and deferred (§6 waiver 2, Q-026) — the follow-up is already committed.
10. **Old-build safety (needs a device still on build 12x, if one exists).** Open Settings. Expect the Pick pricing row to render with **Market** selected (the retired GET serves the fixed state) and **no crash**. Tapping "Tier ladder" should show a "Could not save the pick pricing setting" warn toast and snap back to Market. *Catches the 410 being handled as a fatal error.*

**If per-slot pricing looks wrong in the field**, the fastest lever is flipping `picks.slot_labels` off: every pick drops to the round curve (step 2) without a deploy. See §6 waiver 1 — that flag now moves prices.

---

## 9. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | **updated** | `/api/settings/pick-pricing` row rewritten as RETIRED — GET fixed state, PUT 410. |
| `docs/config-reference.md` | **updated** | `trade.slot_pricing` row marked retired/never-read; the pricing description moved out of the flag row. |
| `docs/data-dictionary.md` | **updated** | `users.pick_pricing_mode` row marked dead data, kept per additive-schema. |
| `docs/cross-client-invariants.md` | **updated** | the "only while the flag is on (it is off)" sentence was false at merge; replaced, and the round-vs-slot distinction stated. |
| `living-memory/LLD.md` | **updated** | route-retirement convention (410 for a withdrawn write verb, fixed-state GET for old clients) — there was no precedent. |
| `docs/architecture.md` / `living-memory/HLD.md` | **n/a** | no module wiring or data flow changed; one constant and one deleted branch. |
| `docs/glossary.md` | **n/a** | no new domain term. "Market slots" and "tier ladder" are both already there. |
| `DECISIONS.md` entry | **drafted** | D-144, in `decisions-draft.md` beside this file. |
| `living-memory/OPEN_QUESTIONS.md` | **drafted** | Q-023 closure note + new Q-026 (§6 waiver 2). |
| `backend/tests/CLAUDE.md` | **updated** | the new conftest and what it pins. |

---

## 10. Ship gate declaration

- **CI green:** `backend-tests`, `mobile-typecheck` (incl. all 69 `check-*.js`), `maestro-testid-lint` — all run locally, all green. See TEST_LEDGER.
- **Evidence recorded:** `living-memory/TEST_LEDGER.md`.
- **TestFlight verification:** checklist in §8, to be run by the operator; outcome logged in TEST_LEDGER.
- **Express lane declared by the operator?** No — full gates.
- **Value-semantics boundary:** the merge SHA of this branch is a pick-value boundary in the same sense `d42872f` was, and must be cited as such by anything that freezes pick weights (notably `docs/plans/receipts/`, building separately on `plan/receipts` — no code coupling, but its grader freezes pick weights independently and needs to know which side of this merge its numbers came from).
