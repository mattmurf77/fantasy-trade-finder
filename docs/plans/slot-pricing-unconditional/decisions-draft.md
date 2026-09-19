# Living-memory entries to land on ship

Drafted on `feat/slot-pricing-unconditional`, **not yet written into `living-memory/`**. The main
session merges the branch and lands these.

**ID hygiene (G-048 — three collisions in three days).** Max IDs re-verified against `origin/main`
at `bb56c59` on 2026-08-21: `D-143`, `Q-025`, `G-052`, `M-004`. So the next free are **D-144**,
**Q-026**, `G-053`, `M-005`. **Re-run the grep against `origin/main` immediately before writing** —
two other sessions are live in this repo and D-144 is exactly the kind of number two of them take
at once.

```
git grep -h -oE "^## D-[0-9]+"  origin/main -- living-memory/DECISIONS.md      | sort -t- -k2 -n | tail -1
git grep -h -oE "^### Q-[0-9]+" origin/main -- living-memory/OPEN_QUESTIONS.md | sort -t- -k2 -n | tail -1
```

Note the file conventions: `DECISIONS.md` ascends **downward** (D-001 at the top), so D-144 goes at
the **end**. `CHANGELOG.md` takes a new dated H2 at the **top**.

---

## 1. `DECISIONS.md` — append at the end

```markdown
## D-144 — Draft Picks Price at Their Own Draft Slot; the Per-User Mode, Its Route and Its Flag Are Retired

**Date:** 2026-08-21 ([scope](../docs/plans/slot-pricing-unconditional/scope.md)); closes [Q-023](OPEN_QUESTIONS.md) in full, rules and defers [Q-026](OPEN_QUESTIONS.md)

**Operator ruling.** *"Market slots should be default and not an opt-in or even an option to flip. Aligned that future picks stay default for now."* Clarified the same day: "market slots" means **each pick holding *real value rather than generic*** — true per-slot pricing, not merely a market-flavoured round curve.

**Decision.** An owned pick's engine value is a three-step waterfall in `pick_values.priced_pool_value`, resolved at read time, for every user, with no flag read, no session read and no DB read:

1. **The pick's OWN slot price** — `market_pick_slot_value(season, round, slot)`, DP's `values.csv` row for e.g. `"2026 Pick 1.03"` — whenever D-090 resolves a real slot.
2. **The round curve** — `market_pick_pool_value`, the mid-tercile basis — when no slot resolves.
3. **The stored ladder `pool_value`** — when DP publishes nothing at all.

**Slot resolution is D-090's, reused rather than reimplemented**: `server._league_slot_order` (DB-backed, 60 s cache, once per *league*) → `pick_slots.slot_for`, which already refuses future seasons (#273), unknown rosters, malformed blobs and unverifiable snake reversals. `priced_pool_value` runs per *pick* and resolves nothing itself; the slot is passed in. The same resolution drives the LABEL, so a card cannot say "2026 1.03" while charging for a generic first.

**Why step 2 survives as more than a curiosity.** It is what every future-year pick gets — and it needs no branch to be so, because DP publishes per-slot rows only for the current class, so step 1 returns `None` for 2027+ by itself. The operator's "future picks stay default for now" therefore falls out of the *data*, not out of a special case that could rot.

**The three things the ruling deleted rather than defaulted:**

- **The setting.** `users.pick_pricing_mode` becomes dead data (kept — additive-schema rule; a restore would need no migration). The mobile Settings row is deleted from both the legacy flat screen and the v2 `TradeValuesSection`, with its client, its state and its `pick_pricing_mode_changed` emitter.
- **The route.** `PUT /api/settings/pick-pricing` → **410 Gone** for any body; `GET` → 200 `{mode: "market_slots", retired: true}` (the fixed state, not the dead column) so builds in the field render honestly instead of hiding the control on a 404. First retired route in this repo; the convention is in LLD § "Retiring a per-user setting".
- **The flag.** `trade.slot_pricing` stays in `FLAG_KEYS` at `true` and is **never read**. Deleting it would force a six-file change to satisfy `test_release_flags_mirror_features_json`, make the key vanish from `/api/feature-flags` for shipped builds, and reinterpret any stored override row as an unknown key.

**The spread this buys, 1QB, 2026 round 1** (pinned snapshot): 1.01 **4867.1**, 1.05 2343.2, 1.08 1435.5, 1.12 **820.8** — against one round price of 1859.5 and one ladder rung of 2117.0 that every 2026 first used to be charged at. A 1.01 is **5.9× a 1.12** and **2.30×** the old rung. Superflex is dearer again (1.01 = 6181.1). Rounds 2–4 deflate at almost every slot.

**So the headline is DISPERSION, not deflation.** The round curve alone (the intermediate step this branch also built) deflates everything — 2026 1st −12.2 %, 2028 1st −40.3 %, 2026 2nd −28.4 %, with deep-future 4ths the lone inversion at +16.6 %. Per-slot then *re-inflates the top of round 1 past the old ladder* and pushes the bottom well below it. Both regimes are shown side by side on a real served card in the scope block §7.1.

**What did NOT move.** `GENERIC_PICK_SEEDS`, the tier ladder, the absolute tier BANDS, `tier_config.json`, and `draft_picks.pool_value` (never written; pricing is read-time). Owned-pick tier BADGES do move — a badge reflects the served value (D-320-2) and the served value moved. Per-slot is where that finally bites: a 1.01 and a 1.12 now badge in genuinely different bands.

**Consequence the operator should see: `picks.slot_labels` became a PRICING flag.** `_league_slot_order` returns `None` when it is off, so turning that flag off drops every pick from step 1 to step 2 without a deploy. This is an accident of reusing D-090 and it is also the **only deploy-free lever** over the larger half of the repricing. Recommended disposition: accept and document it (labels and prices moving together is coherent — you never show "2026 1.01" while charging generic). The alternative, a separate `trade.pick_slot_pricing` flag, means adding a flag on the day we retired one, and the ruling says pricing is not "an option to flip". **Needs a call — scope §6 waiver 1.**

**Rejected: a `model_config` rollback knob for the mode itself.** D-079's precedent argues for one. Rejected because any such knob is *"an option to flip"*, which the ruling forbids in terms. Reverting to the ladder is revert-and-redeploy.

**Rejected: clamping rounds in `market_pick_slot_value`.** `market_pick_pool_value` clamps to DP's published round 5 so a round-9 pick still gets a price. The per-slot function deliberately does not: a round-9 slot has no published row and no honest analogue, so it returns `None` and rides step 2's clamp. One clamp, one place, no drift.

**Evidence.** **156 golden assertions across seven golden files pass with zero edits, twice** — once after the unconditional change and again after the per-slot extension, each time run in isolation before any fixture was touched. Arm A pins every input as a literal and its picks are Elo-map pseudo-assets, so it never constructs a `draft_picks` row and never reaches `priced_pool_value`; immune by construction. No kill-value pin, no re-capture. Gate interactions (overpay/R1, `sweetener_gap_threshold` 1539.0, `pick_gap_ok`) pass untouched — note the spread now straddles that threshold, with a 1.01 (4867.1) far above it and a 1.12 (820.8) far below, where the ladder put every first at 2117.0 on one side.

Three test files moved, all re-derived from the new pricing functions with inputs pinned as literals; no tolerance widened. One structural guard was **made stricter while being widened**: `test_m6_02b_pick_values_reads_dp_only_through_the_m6b_seam` gained a second legitimate DP reader, so it was rewritten from a source-line comparison to an AST walk asserting the reader set is *exactly* `{market_pick_pool_value, market_pick_slot_value}` in both directions, plus a module-level-import refusal. Sabotage-verified: adding a third reader fails it.

**Consequence worth naming: this change made pytest non-hermetic and required the repo's first `conftest.py`.** Unconditional pricing put a live DP fetch on the hot path of every pick-touching test — measured, a 2029 1st priced at 1459.4 from real network data. With network the suite is flaky-by-calendar; without it, it passes for the wrong reason. `backend/tests/conftest.py` `setdefault`s `FTF_DP_PICK_VALUES_FILE` to the checked-in snapshot, which already carries full per-slot coverage (2026, rounds 1–5, slots 01–12) and zero future-season slot rows — so it exercises both step 1 and step 2 without extension.

**Status:** Active. Committed to `feat/slot-pricing-unconditional`, **not pushed and not merged** by the building session.

---

## 2. `OPEN_QUESTIONS.md` — Q-023 closure note

Append to the existing **Q-023** entry (do not rewrite the history above it):

```markdown
- **CLOSED 2026-08-21 by [D-144](DECISIONS.md) — both halves.** Operator ruling: *"Market slots should be default and not an opt-in or even an option to flip. Aligned that future picks stay default for now."*, clarified the same day as meaning each pick should hold *"real value rather than generic"* — i.e. true per-slot pricing.
  - **The mode question:** all picks, not an opt-in cohort. The setting, its route and its flag are retired.
  - **The pricing question — the one this entry is actually titled after:** YES, the slot drives the value. A pick whose slot D-090 resolves prices at DP's row for that exact slot. In 1QB a 2026 1.01 is **4867.1** where a 1.12 is **820.8**; both used to be 2117.0.
  - **Unknown-order leagues:** the mid-tercile round curve, unchanged — now the explicit step-2 fallback rather than the only answer. Same for every future-year pick, and it needs no branch: DP publishes per-slot rows only for the current class.
  - **The tier band:** the BADGE follows the served value automatically (D-320-2); the BANDS do not move. Per-slot is where this finally bites — a 1.01 and a 1.12 badge differently now.
  - **The "38 of 48 badges move" figure finally applies to shipped behaviour**, having been a measurement of an unbuilt thing since it was taken. It was not re-measured for this ship; the badge movement is pinned by contract (`test_m6b_05f_the_badge_follows_the_served_value`) rather than by count, and the count is worth re-taking if anyone wants to quote it.
  - What is NOT closed here is the league-surface disagreement, which is its own question and is ruled + deferred: **Q-026**.
```

## 3. `OPEN_QUESTIONS.md` — new entry (RULED + DEFERRED, not open)

```markdown
### Q-026 — League surfaces still price picks on the ladder — RULED, DEFERRED to the next change
- **Status: RULED 2026-08-21, deferred by the operator. Not awaiting an answer.** Operator: *"I want the league values to reflect the same pick values.. But let's defer that until after finishing this one."* [D-144](DECISIONS.md) therefore shipped with the disagreement, and league-surface alignment is the **committed immediate follow-up**, sequenced after that branch merges.
- **What changed to raise it:** D-144 made pick pricing unconditional and per-slot for the trade engine and the calculator. It did **not** touch `_power_picks_by_owner` or `GET /api/league/picks`, which still serve the stored ladder `draft_picks.pool_value`. This is build-m6b's own deviation **D-7**, written down at the time as acceptable *because the market mode was dark*. It is not dark now.
- **The motivating number (1QB, 2026).** Per-slot made this much worse than the round curve did — the round curve's worst gap was −13.9 %:

  | pick | league surfaces say | engine says | gap |
  |---|---:|---:|---:|
  | **1.01** | 2117.0 | **4867.1** | **+2750.1 (+130 %)** |
  | 1.12 | 2117.0 | 820.8 | −1296.2 (−61 %) |
  | 2.01 | 606.5 | 727.6 | +121.1 (+20 %) |
  | 2.12 | 606.5 | 315.5 | −291.0 (−48 %) |
  | 3.01 | 406.6 | 303.2 | −103.4 (−25 %) |

  **Worst case: a 2026 1.01 reads 2117.0 on Power Rankings and is worth 4867.1 inside a trade card — a 2.3× disagreement about the most valuable asset a team can hold.** The two surfaces also badge the same pick differently, since a badge follows the value it is served (D-320-2).
- **Scope of the follow-up:** route `_power_picks_by_owner` and `GET /api/league/picks` through `priced_pool_value` with the same `_league_slot_order` resolution the engine uses, and re-derive `test_league_picks_tier.py`'s pinned badges — which will move, and should. Watch `_user_pick_share` and any Power-Rankings total that sums pick values, since those totals will move too.
- **Owner:** backend session, immediately after D-144 merges.
```

## 4. `CHANGELOG.md` — new dated H2 at the top

```markdown
## 2026-08-21 — Draft picks price at their own draft slot (D-144)

A draft pick is no longer worth "a first". It is worth **that** first. Every owned pick whose
draft slot we can resolve now prices at DynastyProcess's published value for that exact slot; picks
we cannot place — every future-year pick, every league with no published order — price off the
market curve for their round. The per-user pricing mode, its Settings row and the flag that gated it
are all retired.

**⚠️ VALUE-SEMANTICS BOUNDARY — cite this merge SHA.** Pick values on either side of this commit are
not comparable, in the same way `d42872f` (package pricing honesty) is a boundary. Anything that
freezes or grades pick weights must record which side of it the numbers came from — specifically
`docs/plans/receipts/` (building on `plan/receipts`), whose grader freezes pick weights
independently. There is no code coupling; the coupling is in the numbers.

- **The spread, 1QB 2026 round 1:** 1.01 **4867.1**, 1.05 2343.2, 1.08 1435.5, 1.12 **820.8** —
  where every one of them used to be 2117.0. A 1.01 is 5.9x a 1.12. Superflex is dearer again
  (1.01 = 6181.1). Rounds 2-4 deflate at almost every slot.
- **Direction is DISPERSION, not deflation.** The market curve alone deflates everything
  (2026 1st -12.2%, 2028 1st -40.3%); per-slot then re-inflates the top of round 1 past the old
  ladder and pushes the bottom well below it.
- **A real served card, three regimes:** Maye + Adams <-> 2026 1.05 + 2027 1st. Receive side
  4234.0 (ladder) -> 3364.1 (round curve) -> **3847.8** (per-slot); the card's balance goes
  +371.7 -> -498.2 -> **-14.5**. The round curve alone overshot by pricing the 1.05 generically;
  per-slot lands it at honest near-even money. The 2027 first is identical in the last two columns,
  because no slot exists for it - "future picks stay default", visible in the arithmetic.
- **Retired:** the `pick_pricing_mode` setting (column kept as dead data), the mobile Settings row,
  `PUT /api/settings/pick-pricing` (410 Gone; GET serves the fixed state for old builds), and the
  flag `trade.slot_pricing` (kept in `FLAG_KEYS` at `true`, never read).
- **Unchanged:** `GENERIC_PICK_SEEDS`, the tier ladder, the absolute tier bands,
  `draft_picks.pool_value`. Owned-pick badges move because they reflect the served value (D-320-2) -
  a 1.01 and a 1.12 now badge differently.
- **`picks.slot_labels` is now a PRICING flag**, as a side effect of reusing D-090's resolver.
  Turning it off drops every pick to the round curve without a deploy - the only rollback lever
  this change has. Needs an operator call on whether to keep the coupling or split the flag.
- **Ruled and deferred:** Power Rankings and `/api/league/picks` still show ladder prices, so a
  2026 1.01 reads 2117.0 there and 4867.1 in a trade card. Operator ruled the league surfaces
  should match and deferred it to the next change - Q-026, committed follow-up.
- Tests: 3906 passed, 1 skipped (baseline 3897/1). All 156 golden assertions pass unedited, twice.
  First `backend/tests/conftest.py` added - unconditional pricing made the suite non-hermetic
  against DP.
```

## 5. `TEST_LEDGER.md`

```markdown
## 2026-08-21 — Per-slot pick pricing (D-144), `feat/slot-pricing-unconditional`

| Gate | Result |
|---|---|
| `pytest backend/tests` | **3906 passed, 1 skipped** (baseline on `origin/main` bb56c59: 3897 passed, 1 skipped) |
| `npx tsc --noEmit` (mobile) | clean |
| `mobile/tests/check-*.js` (69 suites) | 69/69 pass |
| `mobile/scripts/testid-lint.sh` | OK |
| Goldens | 7 files, **156 assertions, zero edits, zero re-captures — verified TWICE**, once after the unconditional change and again after the per-slot extension, each run in isolation before any fixture was touched. Arm A pins every input as a literal and its picks are Elo-map pseudo-assets, so it never reaches `priced_pool_value`. |
| Gate interactions | overpay/R1, `sweetener_gap_threshold` (1539.0), `pick_gap_ok` — all pass. Worth noting for future calibration: the per-slot spread now STRADDLES the sweetener threshold (a 1.01 at 4867.1 is far above it, a 1.12 at 820.8 far below), where the ladder put every first at 2117.0 on one side of it. No gate needed changing, but this is the input that changed most. |
| Fixtures moved (honestly) | `test_owned_picks.py` ×2, `test_pick_values_in_suggestions.py` ×4 — re-derived from `market_pick_pool_value` with inputs pinned as literals. One bound restated against the curve rather than a literal: a 2029 2nd/3rd gap is 93.2 on the market vs 122.8 on the ladder — a **finding**, recorded as such. |
| Structural guard widened, and made STRICTER | `test_slot_values.py::test_m6_02b_...` pinned that `pick_values.py` reads DP from exactly one function; per-slot adds a second legitimate reader. Rewritten from a source-line comparison to an **AST walk** asserting the reader set is exactly `{market_pick_pool_value, market_pick_slot_value}` in both directions, plus a module-level-import refusal. **Sabotage-verified**: appending a third reader function fails it. |
| New tests | `test_pick_pricing_m6b.py` 26 → 34. The T-M6B-05 family: the ruling as one assertion (1.01 > 1.05 > 1.12, literals pinned), the unresolved-order fallback, the future-year fallback asserted at both levels, format awareness, every fail-soft trigger, the badge contract, and **two end-to-end tests through `_owned_pick_assets`** — with a resolved order (per-slot prices, cap sorts 1.01 above 1.12, label agrees with price) and without one (round-curve prices, generic labels). |
| Net test delta | **+9** |
| New | `backend/tests/conftest.py` — pins `FTF_DP_PICK_VALUES_FILE`. Required, not cosmetic: unconditional pricing put a live DP fetch on the suite's hot path (measured: a 2029 1st priced at 1459.4 from real network data before the pin). The checked-in snapshot already carries full per-slot coverage (2026, rounds 1–5, slots 01–12) and zero future-season slot rows, so it exercises both the per-slot lane and the round-curve fallback without extension. |
| Known non-failure to ignore | An intermediate run showed 3 `test_trade_decision_idempotency` failures. Artifact, not a defect: those tests read `server.py` through `inspect.getsource`, and `server.py` was edited **while that run was in flight**, so `linecache` served a stale line map. They pass in isolation and in every clean run. If you see them, check whether something rewrote a source file mid-run before investigating. |
| TestFlight | checklist in `docs/plans/slot-pricing-unconditional/scope.md` §8 — **NOT YET RUN**; operator to run and log the outcome here. Step 2 is the headline: a 1.01 and a 1.12 on opposite sides of the calculator must NOT cancel. |
```
