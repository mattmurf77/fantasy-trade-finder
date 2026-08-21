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
## D-144 — Market Pick Pricing Is Unconditional; the Per-User Mode, Its Route and Its Flag Are Retired

**Date:** 2026-08-21 ([scope](../docs/plans/slot-pricing-unconditional/scope.md)); closes the mode half of [Q-023](OPEN_QUESTIONS.md), opens [Q-026](OPEN_QUESTIONS.md)

**Operator ruling, verbatim:** *"Market slots should be default and not an opt-in or even an option to flip. Aligned that future picks stay default for now."*

**Decision.** `trade_service.pick_pricing_mode_for_user` returns `market_slots` for every user, unconditionally — no flag read, no session read, no DB read. Every OWNED pick prices at `pick_values.market_pick_pool_value(season, round, scoring_format)`, resolved at read time, fail-softing to the stored ladder `pool_value` when DynastyProcess publishes no price. The three things the ruling deleted rather than defaulted:

- **The setting.** `users.pick_pricing_mode` becomes dead data (kept — additive-schema rule; a restore would need no migration). The mobile Settings row is deleted from both the legacy flat screen and the v2 `TradeValuesSection`, along with its client, its state and its `pick_pricing_mode_changed` emitter.
- **The route.** `PUT /api/settings/pick-pricing` → **410 Gone** for any body; `GET` → 200 `{mode: "market_slots", retired: true}` (the fixed state, not the dead column) so builds in the field render honestly instead of hiding the control on a 404. This is the repo's first retired route and the precedent — see LLD § "Retiring a per-user setting".
- **The flag.** `trade.slot_pricing` stays in `FLAG_KEYS` at `true` and is **never read**. Deleting it would force a six-file change to satisfy `test_release_flags_mirror_features_json`, make the key vanish from `/api/feature-flags` for shipped builds, and reinterpret any stored override row as an unknown key.

**Scope, stated precisely, because the obvious reading is wrong.** `market_slots` is a **ROUND-level** curve. It prices a 2026 first at the value-space mean of slots 5–8 (`UNKNOWN_SLOT_BASIS`), so **a 1.01 and a 1.12 are charged the same 1859.5** even though DP publishes them at 4867.1 and 820.8. D-090 resolves the real slot and it drives the LABEL only. **True-slot pricing — the substance of Q-023 — is NOT built**, and the "38 of 48 badges move" figure in Q-023 measures that unbuilt thing, not this. Pinned by `test_m6b_05_a_101_and_a_112_price_identically`, which fails on purpose if true-slot pricing ever lands quietly.

**The measured direction is DEFLATION.** Against the ladder, 1QB: 2026 1st **−12.2 %** (2117.0 → 1859.5), 2027 1st −28.9 %, 2028+ 1st **−40.3 %**, 2026 2nd −28.4 %, 2026 3rd −35.5 %; deep-future 4ths are the lone inversion at **+16.6 %**, which is why `_owned_pick_assets` caps AFTER pricing. Superflex is milder and a current-year SF first actually gains (+6.9 %). End-to-end on a real served card (`knockout-survivors.csv:13`): Maye + Adams ↔ 2026 1.05 + 2027 1st, receive side **4234.0 → 3364.1**, and the card's balance **inverts** from +371.7 to −498.2.

**What did NOT move.** `GENERIC_PICK_SEEDS`, the tier ladder, the absolute tier BANDS, `tier_config.json`, and `draft_picks.pool_value` (never written; pricing is read-time). Owned-pick tier BADGES do move — a badge reflects the served value (D-320-2) and the served value moved; that is a consequence, not a second decision.

**Rejected: ship a deploy-free rollback knob.** D-079's precedent argues for one (*"the risk is entirely in the number"*). Rejected because any such knob is *"an option to flip"*, which the ruling forbids in terms. Rollback is revert-and-redeploy. **Flagged to the operator as waiver 1** — this is the one place the ruling and the repo's own risk convention genuinely disagree, and the ruling won.

**Rejected: fix the Power Rankings / `/api/league/picks` divergence here.** build-m6b deviation D-7 left both on the stored ladder. Dark, invisible; live, a 2026 1st reads 2117.0 on Power Rankings and is worth 1859.5 in a trade card. Out of scope, logged as **Q-026**, surfaced as waiver 2.

**Evidence.** 114 golden assertions across six golden files pass with **zero edits** — arm A pins every input as a literal and its picks are Elo-map pseudo-assets, so it never constructs a `draft_picks` row and never reaches `priced_pool_value`. No kill-value pin, no re-capture. Two test files legitimately moved (`test_owned_picks.py`, `test_pick_values_in_suggestions.py`), fixed by re-deriving expectations from `market_pick_pool_value` with inputs pinned as literals — no tolerance was widened. One bound genuinely loosened and is documented as a finding, not a fudge: a 2029 2nd and 3rd sit 93.2 apart on the market vs 122.8 on the ladder, so a `> 100` literal was restated against the curve.

**Consequence worth naming: this change made pytest non-hermetic and required the repo's first `conftest.py`.** Unconditional pricing put a live DP fetch on the hot path of every pick-touching test — measured, `test_pick_values_in_suggestions` priced a 2029 1st at 1459.4 from real network data. With network the suite is flaky-by-calendar; without it, it passes for the wrong reason. `backend/tests/conftest.py` `setdefault`s `FTF_DP_PICK_VALUES_FILE` to the checked-in snapshot. Pick curve only; the player curve is untouched.

**Status:** Active. Committed to `feat/slot-pricing-unconditional`, **not pushed and not merged** by the building session.
```

---

## 2. `OPEN_QUESTIONS.md` — Q-023 closure note

Append to the existing **Q-023** entry (do not rewrite the history above it):

```markdown
- **CLOSED (mode question) 2026-08-21 by [D-144](DECISIONS.md); the pricing question it actually asked REMAINS OPEN.** Operator ruling, verbatim: *"Market slots should be default and not an opt-in or even an option to flip. Aligned that future picks stay default for now."*
  - **The three sub-questions this question left the implementer, answered:** all picks, not just an opt-in cohort — the opt-in is deleted. Unknown-order leagues keep the Mid-rung basis, and it is not a special case. The tier BAND follows the value automatically (D-320-2); the bands themselves do not move.
  - **But read this before citing the 38/48 figure again.** That measurement is of **TRUE-SLOT** pricing. D-144 shipped `market_slots`, which is **round-level**: a 1.01 and a 1.12 are both charged 1859.5 (1QB), against DP's published 4867.1 and 820.8. So the thing this question is titled after — *"should the slot drive its VALUE?"* — is still not built. What D-144 settled is *which curve*, not *which slot*.
  - **What remains, concretely:** `pick_values._market_round_value` still carries the documented extension point (an optional `slot` that skips the tercile), and D-090 already persists the order, so the two objections build-m6b raised against it (a live fetch on the hot path; two users of one league disagreeing) are now moot. Only the third survives: it applies to the current season only, which is 3 of 12 leagues.
  - Tripwire in place: `test_m6b_05_a_101_and_a_112_price_identically` fails the moment true-slot pricing lands, so it cannot ship silently.
```

## 3. `OPEN_QUESTIONS.md` — new entry

```markdown
### Q-026 — Power Rankings and `/api/league/picks` price picks on the ladder while the trade engine prices them on the market
- **What changed to raise this:** [D-144](DECISIONS.md) made market pick pricing unconditional for the trade engine and the calculator. It did **not** touch `_power_picks_by_owner` or `GET /api/league/picks`, which still serve the stored ladder `draft_picks.pool_value`. This is build-m6b's own deviation **D-7**, which was written down at the time as acceptable *because the market mode was dark*. It is no longer dark.
- **What the user sees:** the same 2026 first reads **2117.0** on the Power Rankings screen and is worth **1859.5** inside a trade card — a 13.9 % disagreement on the highest-value asset class in the app. Because a pick's tier badge is computed from whichever number that surface holds (D-320-2), the two surfaces can also badge the same pick differently.
- **Why it was not fixed in D-144:** it is two more serving surfaces plus `test_league_picks_tier.py`'s pinned badges, and the operator ruling was about the *setting*, not about the pick-value read path in general. Widening the change would have made the golden story harder to attribute.
- **The options, briefly:** (a) route both through `priced_pool_value` — consistent, but moves Power Rankings totals and league-picks badges, so it needs its own before/after; (b) leave them, and label the Power Rankings number as a book value; (c) leave them and accept the drift silently — the current state, and the one worth *not* choosing by default.
- **Needed to close:** an operator call on (a) vs (b). Nothing is blocked on it; D-144 ships complete without it.
- **Owner:** operator (consistency call), then a backend session.
```

## 4. `CHANGELOG.md` — new dated H2 at the top

```markdown
## 2026-08-21 — Market pick pricing is unconditional (D-144)

Pick pricing stopped being a setting. Every owned pick, for every user, now prices off DynastyProcess's
market curve for its season and round instead of our tier ladder. The per-user mode, the Settings row and
the flag that gated it are all retired.

**⚠️ VALUE-SEMANTICS BOUNDARY — cite this merge SHA.** Pick values on either side of this commit are not
comparable, in the same way `d42872f` (package pricing honesty, 2026-08-22) is a boundary. Anything that
freezes or grades pick weights must record which side of it the numbers came from — specifically
`docs/plans/receipts/` (building on `plan/receipts`), whose grader freezes pick weights independently.
There is no code coupling; the coupling is in the numbers.

- **Direction is DEFLATION, not inflation.** 1QB: a 2026 1st −12.2 % (2117.0 → 1859.5), a 2028 1st −40.3 %,
  a 2026 2nd −28.4 %. Deep-future 4ths are the one inversion (+16.6 %). Superflex is milder and a
  current-year SF first gains 6.9 %. A real served card (Maye + Adams ↔ 2026 1.05 + 2027 1st) moves from
  +371.7 in the user's favour to −498.2 against — the balance inverts.
- **It is ROUND-level, not per-slot.** A 1.01 and a 1.12 are charged the same price. True-slot pricing
  (Q-023's actual question) is still unbuilt; a test fails loudly if it lands quietly.
- **Retired:** the `pick_pricing_mode` setting (column kept as dead data), the mobile Settings row,
  `PUT /api/settings/pick-pricing` (410 Gone; GET serves the fixed state for old builds), and the flag
  `trade.slot_pricing` (kept in `FLAG_KEYS` at `true`, never read).
- **Unchanged:** `GENERIC_PICK_SEEDS`, the tier ladder, the absolute tier bands, `draft_picks.pool_value`.
  Owned-pick badges move because they reflect the served value (D-320-2).
- **Surfaced, not fixed:** Power Rankings and `/api/league/picks` still show ladder prices — Q-026.
- **No deploy-free rollback lever exists** — the ruling forbids the flag that would have been one.
  Rollback is revert + redeploy.
- Tests: 3900 passed, 1 skipped (baseline 3897/1). All 114 golden assertions pass unedited. First
  `backend/tests/conftest.py` added — unconditional pricing made the suite non-hermetic against DP.
```

## 5. `TEST_LEDGER.md`

```markdown
## 2026-08-21 — Market pick pricing unconditional (D-144), `feat/slot-pricing-unconditional`

| Gate | Result |
|---|---|
| `pytest backend/tests` | **3900 passed, 1 skipped** (baseline on `origin/main` bb56c59: 3897 passed, 1 skipped) |
| `npx tsc --noEmit` (mobile) | clean |
| `mobile/tests/check-*.js` (69 suites) | 69/69 pass |
| `mobile/scripts/testid-lint.sh` | OK |
| Goldens | `test_bakeoff_arm_a_golden`, `_serving`, `_challenger`, `_composition`, `test_engine_quality_golden`, `test_fairness_gate_golden`, `test_fit_congruence` — **114 assertions, zero edits, zero re-captures.** Arm A pins every input as a literal and its picks are Elo-map pseudo-assets, so it never reaches `priced_pool_value`. Verified by running the six files in isolation before any fixture was touched. |
| Gate interactions | overpay/R1, `sweetener_gap_threshold` (1539.0), `pick_gap_ok` — all pass; no tolerance widened anywhere |
| Fixtures moved (honestly) | `test_owned_picks.py` ×2 and `test_pick_values_in_suggestions.py` ×4 re-derived from `market_pick_pool_value` with inputs pinned as literals. One bound restated against the curve rather than a literal: a 2029 2nd/3rd gap is 93.2 on the market vs 122.8 on the ladder — a **finding**, recorded as such. |
| Net test delta | **+3** (M6b file rewritten around the inverted contract, 26 → 28: T-M6B-05 pair added, two flag/column tests split from one; plus a new premise test in `test_pick_values_in_suggestions`) |
| Known non-failure to ignore | An intermediate run showed 3 `test_trade_decision_idempotency` failures. Artifact, not a defect: those tests read `server.py` through `inspect.getsource`, and `server.py` was edited **while that run was in flight**, so `linecache` served a stale line map. They pass in isolation and in the final clean run. If you see them, check whether something rewrote a source file mid-run before investigating further. |
| New | `backend/tests/conftest.py` — pins `FTF_DP_PICK_VALUES_FILE`. Required, not cosmetic: unconditional pricing put a live DP fetch on the suite's hot path (measured: a 2029 1st priced at 1459.4 from real network data before the pin). |
| TestFlight | checklist in `docs/plans/slot-pricing-unconditional/scope.md` §8 — **NOT YET RUN**; operator to run and log the outcome here. |
```
