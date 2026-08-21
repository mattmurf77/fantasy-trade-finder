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

| Clause | What it means in code |
|---|---|
| *"Market slots should be default"* | `trade_service.pick_pricing_mode_for_user` returns `market_slots` for every user, with no flag read, no session read and no DB read. |
| *"not an opt-in or even an option to flip"* | The per-user setting is **deleted**, not defaulted: the mobile control is removed, `PUT /api/settings/pick-pricing` is 410 Gone, and `trade.slot_pricing` is retired to a never-read key. |
| *"future picks stay default for now"* | Future-season picks keep pricing off DP's generic/`Mid` rung for that season — which is what `market_slots` already did. **Zero code change**; this clause is a *constraint satisfied*, not a feature. |

### What Q-023 asked, and which half this answers

Q-023's operator ruling of 2026-08-19 was *"Slot should drive price but we can push this live first and then solve for that."* It left three sub-questions for the implementer:

| Q-023 sub-question | Answered by this change |
|---|---|
| all picks, or only under the opt-in `trade.slot_pricing` mode? | **All picks.** The opt-in is gone. |
| unknown-order leagues → Mid rung, or excluded? | **Mid rung** — unchanged, and it is not a special case (see §1.1). |
| does the TIER band follow, or only the trade value? | **The badge follows the value** (D-320-2), automatically, because a badge is derived from the served value. **The bands themselves do not move.** |

**Q-023 is therefore CLOSED for the mode question and REMAINS OPEN for true-slot pricing.** See §1.1 — this is the single most important line in this document.

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

### 1.1 What this does **NOT** do — read before quoting any 1.01 number

**`market_slots` is a ROUND-level curve. It does not price a pick at its own draft slot.**

`pick_values.market_pick_pool_value(season, round)` takes no slot. It prices a first at the value-space mean of slots 5–8 (`UNKNOWN_SLOT_BASIS = "mid_tercile"`), which is the market analogue of the ladder's Mid rung. D-090 resolves a current-year pick's real slot and that slot drives the **label** only — `server._owned_pick_assets:10758` passes `slot_order` to `_owned_pick_label`, never to `priced_pool_value`.

So, in 1QB, from the same snapshot:

| | value |
|---|---:|
| DP's published 2026 Pick **1.01** | 4867.1 |
| DP's published 2026 Pick **1.12** | 820.8 |
| **What the engine charges for either** | **1859.5** |

A 1.01 is worth 5.9× a 1.12 on the market curve and this build still prices them identically. **True-slot pricing is the unbuilt half of Q-023.** Pinned as an explicit tripwire by `test_m6b_05_a_101_and_a_112_price_identically` — if someone ships true-slot pricing, that test fails on purpose.

**This matters for the badge prediction.** Q-023's "38 of 48 badges move" figure is a measurement of **true-slot** pricing. It does not describe this change. What this change does to badges is smaller and follows automatically from D-320-2 (§4).

---

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
  - `test_m6b_05_a_101_and_a_112_price_identically` — **the scorecard**, §1.1.
  - `test_m6b_05b_the_badge_follows_the_served_value` — D-320-2 walked over the same inverse the clients use.
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

**114 golden assertions pass with zero edits.** No kill-value pin was needed and no re-capture was performed. Verified by running the six files in isolation before touching any fixture, so this is a measurement rather than an inference.

**Gate interactions** (`overpay`/R1, `sweetener_gap_threshold` = 1539.0, `pick_gap_ok`) all consume pick values and all continued to pass. No tolerance was widened anywhere; the two tests that legitimately moved are named in §5.3.

### 5.3 Tests whose fixtures moved, and why that is honest

`backend/tests/test_pick_values_in_suggestions.py` (#185) derives its expectations from `pick_pool_value(...)` — deliberately, so "a retune moves the fixture with the ladder". That derivation is now wrong for owned picks, because owned picks no longer price off `pick_pool_value`. Fixed by pinning the **inputs** as literals and expecting the **market** price, not by loosening a tolerance.

---

## 6. Waivers requiring operator sign-off

**Waiver 1 — there is no deploy-free rollback for the repricing.**
D-079 chose a `model_config` knob over a flag precisely so a bad number could be reverted without a deploy. This change has no such lever: the mode is a Python constant, and the flag that *could* have been the lever is being retired by the same ruling that makes the pricing unconditional. Rolling back means reverting the merge and redeploying. If the operator wants a knob, the cheapest honest one is a `model_config` boolean read inside `pick_pricing_mode_for_user` — which is *"an option to flip"* and so contradicts the ruling as written. **Flagging, not deciding.**

**Waiver 2 — Power Rankings and `/api/league/picks` now disagree with the trade engine.**
build-m6b deviation D-7 left `_power_picks_by_owner` and `GET /api/league/picks` on the stored ladder. Dark, that was invisible. Live, a 2026 1st reads **2117.0** on the Power Rankings screen and is worth **1859.5** inside a trade card, and its tier badge is computed from the ladder number on one surface and the market number on the other. Fixing it is a real change to two more surfaces (and to `test_league_picks_tier.py`'s pinned badges) and is **deliberately out of scope here**. Logged as **Q-026**.

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

**Call site 1 — the deck/asset-idea lane.** `backend/server.py:10830`, in `_inject_owned_picks`:
```python
_pp_mode = (_trade_service_mod.pinned_pick_pricing_mode()
            or _trade_service_mod.pick_pricing_mode_for_user(user_id))
with _trade_service_mod.pick_pricing_override(_pp_mode):
    pick_assets = _owned_pick_assets(league_id, scoring_format)
```
`user_id` is still passed and still ignored; the pin is kept because the bake-off harnesses must be able to price a whole job on the ladder. Inside, `_owned_pick_assets:10754` calls `priced_pool_value(p, scoring_format=...)` per row, sorts by the **priced** value, then caps (`:10768`) — the cap-after-pricing rule, which matters because the market re-orders a 2029 4th above a 2030 3rd.

**Call site 2 — the manual calculator.** `backend/server.py:9697`, in `trade_evaluate_route`:
```python
_pp_mode = (_trade_service_mod.pinned_pick_pricing_mode()
            or _trade_service_mod.pick_pricing_mode_for_user(None))
```
Simplified from the old form, which resolved an optional session to read the user's stored mode. That session lookup is **deleted** — Mode A stays public and anonymous callers get the same price as signed-in ones, which they now provably do because there is only one price. The pin wraps `_trade_evaluate_impl`, whose owned-pick read at `:9771` calls `priced_pool_value`.

**The seam.** `backend/pick_values.py:priced_pool_value` — `mode=None` resolves the thread-local; `market_slots` calls `market_pick_pool_value(season, round, fmt)` and **falls back to the stored ladder value when that returns `None`**. `market_pick_pool_value` returns `None` for a season DP does not publish and cannot extrapolate to, and `load_pick_slot_values` returns `{}` on any fetch/parse failure. So DP being unreachable degrades every pick to today's ladder price, silently. That fail-soft was a nicety when the mode was opt-in; it is now the entire safety net.

**Sites deliberately NOT reached:** `_power_picks_by_owner`, `GET /api/league/picks` (§6 waiver 2), `pick_pool_value` itself (still the ladder, still what writes `draft_picks.pool_value` at sync time), `GENERIC_PICK_SEEDS`, and the rankable generic rungs.

### 7.1 End-to-end proof on a real served card

Card from `docs/reviews/2026-08-19-knockout-waterfall/knockout-survivors.csv:13` — arm B, divergence, `mattmurf77 → jonbonjourvi`:

```
give     Drake Maye + Davante Adams        cons_give = 3862.3   (players, untouched)
receive  2026 1.05 (from Bcork) + 2027 1st cons_recv = 4234.0   (as served, on the ladder)
```

Repriced through `priced_pool_value` (1QB, pinned snapshot):

| asset | ladder | market | Δ |
|---|---:|---:|---:|
| 2026 1.05 | 2117.0 | 1859.5 | −257.5 |
| 2027 1st | 2117.0 | 1504.6 | −612.4 |
| **receive total** | **4234.0** | **3364.1** | **−869.9** |
| give total | 3862.3 | 3862.3 | 0.0 |

The recomputed ladder total reproduces the CSV's `cons_recv` of **4234.0 exactly**, which is what makes this a check rather than an illustration. **The card's balance inverts**: `+371.7` in the user's favour on the ladder becomes `−498.2` against them on the market. A card the engine served as a gain is now a loss — this is the single clearest example of what the ruling does to deck composition.

Note the 1.05: priced at **1859.5**, the generic 2026-first price. Its own slot is worth **2343.2**. §1.1.

---

## 8. Manual TestFlight checklist (operator)

Backend-only pricing plus one removed Settings row. Runtime proof genuinely matters for the pricing, because no structural test can see a served deck.

1. **Settings → Trade values.** Expect: the **Stud tax** segmented control, and **nothing below it**. The "Pick pricing" row (Tier ladder / Market) must be gone entirely — not greyed, not empty-stated. *Regression this catches: the row surviving in the legacy flat screen, which is a separate file from the v2 section.*
2. **Calculator, current-year first.** Build a trade containing one of your 2026 firsts. Expect its value near **1859.5** (1QB) / **2263.3** (SF), **not** 2117.0. *Catches: the pin not reaching the evaluate route.*
3. **Calculator, two different current-year firsts.** If you can put a high slot and a low slot on opposite sides, expect them to **cancel exactly** — the engine charges the same for both. This is the §1.1 behaviour and it is **expected, not a bug**. *Catches: someone having wired true-slot pricing in by accident.*
4. **Calculator, far-future first.** A 2028 or 2029 first should read near **1263.0** (1QB), down from 2117.0. *Catches: the extrapolation branch.*
5. **Generate a fresh deck** on a league that holds picks. Expect visibly different pick-bearing cards than your last deck — build-m6b measured ~60 % of 1QB cards changing. *Catches: `_inject_owned_picks` not pinning.*
6. **Pick tier badges in a trade card.** Firsts should still badge as firsts. *Catches: a band edge being crossed unintentionally.*
7. **Known inconsistency, confirm don't report:** the **Power Rankings** screen still shows the old ladder numbers for the same picks (§6 waiver 2, Q-026). Expect the disagreement.
8. **Old-build safety (needs a device still on build 12x, if one exists).** Open Settings. Expect the Pick pricing row to render with **Market** selected (the retired GET serves the fixed state) and **no crash**. Tapping "Tier ladder" should show a "Could not save the pick pricing setting" warn toast and snap back to Market. *Catches: the 410 being handled as a fatal error.*

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
