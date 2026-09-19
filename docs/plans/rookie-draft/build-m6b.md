# Build status — M6b: market slot values IN THE TRADE ENGINE (repricing)

**Wave:** `wave/m6b` · **Date:** 2026-08-06 · **Base:** `origin/main` @ `93840b1` (M5 + M6 included)
**Spec:** [plan.md](plan.md) §M6, §6, and the *Operator decisions — 2026-08-06* block, **especially O2** · [build-m6.md](build-m6.md) §2 (the measured slot curve — this wave's input data) · precedent: [`docs/feedback/items/214-stud-tax/`](../../feedback/items/214-stud-tax/)
**Flag:** `trade.slot_pricing` — **added OFF, not flipped.**
**Default mode:** `tier_ladder` — **today's behaviour, exactly. Nothing reprices for anyone.**

---

## 1. What was built

A per-user draft-pick pricing toggle, mirroring #214/#215 end to end, plus the repricing itself applied at **read** time.

| Piece | Where |
|---|---|
| `users.pick_pricing_mode` column + `PICK_PRICING_MODES` + `get_/set_pick_pricing_mode` + `_migrate_db` row | `backend/database.py` |
| Thread-local mode: `PICK_PRICING_MODES` / `PICK_PRICING_DEFAULT` / `_pick_pricing_local` / `current_pick_pricing_mode` / `pinned_pick_pricing_mode` / `pick_pricing_override` / `pick_pricing_mode_for_user` (**the single flag gate**) | `backend/trade_service.py` |
| The market curve: `market_pick_pool_value`, `_market_round_value`, `_basis_slots`, `UNKNOWN_SLOT_BASIS`, and the read-time seam `priced_pool_value` | `backend/pick_values.py` |
| Read sites: `_owned_pick_assets` (prices, then caps), `_inject_owned_picks` (pins the mode for both engine lanes), `/api/trade/evaluate` (`league_pick_vals` + the request-scoped pin) | `backend/server.py` |
| `GET/PUT /api/settings/pick-pricing` — sibling of `/api/settings/stud-tax`, with `_verified_write_denial` and `record_event('pick_pricing_mode_changed')`; **404 on both verbs while the flag is off** | `backend/server.py` |
| Settings segmented control (`testID={'settings.pick-pricing.<key>'}`, `track()`), API client | `mobile/src/screens/SettingsScreen.tsx`, `mobile/src/api/accountPrefs.ts` |
| Flag, 4-touch | `backend/feature_flags.py` · `config/features.json` · `backend/tests/fixtures/flags/release.json` · `docs/config-reference.md` |
| Tests (26 new + 1 amended file) | `backend/tests/test_pick_pricing_m6b.py`, `backend/tests/test_slot_values.py` |
| Docs | `docs/data-dictionary.md` · `docs/api-reference.md` · `docs/config-reference.md` · `docs/cross-client-invariants.md` |
| Harnesses + raw output (gitignored) | `feedback-workspace/m6b/fit_matrix.py`, `deck_diff.py`, `*.out` |

### The two things that are NOT repriced, deliberately

1. **`GENERIC_PICK_SEEDS` — byte-unchanged in BOTH modes.** The 12 generic rungs are *rankable pool assets*: users swipe them in matchups and their seed Elo anchors the tier bands, which are **absolute Elo mirrored across five clients** (`docs/cross-client-invariants.md`). Repricing them for a *per-user* setting would repaint another user's tier colours from a shared, process-global pool. They also never sit on a roster, so they are not tradeable assets — they reach a trade only through the manual calculator, where the user's own board Elo already prices them. Pinned by `test_m6b_04_generic_ladder_byte_unchanged_in_every_mode`.
2. **`draft_picks.pool_value` — never rewritten.** It is persisted by a league-wide sync path and shared by every user of the league. The brief's hard constraint; implemented by resolving the mode inside `priced_pool_value` at the point of pricing. Pinned by `test_m6b_03_read_time_only_never_writes_the_shared_column`.

---

## 2. The slot-mapping decision

DP prices per SLOT (`2026 Pick 1.07`) for the current class. An owned `draft_picks` row carries `(season, round)` and no slot — a slot exists only once the platform publishes an order, which is true for at most the current season and, per #228, only until that draft completes.

**Decision: an unknown slot prices at the VALUE-SPACE MEAN OF THE ROUND'S MIDDLE TERCILE** (slots 5–8 of a 12-team round). One home: `pick_values.UNKNOWN_SLOT_BASIS` + `_basis_slots`, with the rejected alternative named in the same comment block.

Two checkable reasons:

1. **It is DP's own definition of a "Mid" rung.** DP publishes Early/Mid/Late for future seasons; for 2027 its `Mid 1st` (Elo 1581.7) and its round-generic `1st` (1584.1) agree to 2.4 Elo. Using the mid tercile for the current class makes current-year and future-year prices mean the same thing — a single-slot basis would not.
2. **It is the market analogue of what ships today.** `pick_pool_value` prices every pick at the ladder's **Mid** rung (operator decision 2026-07-18). Same semantics, different source.

**Rejected: the value-space mean of all 12 slots.** Round 1 is strongly convex (the 1.01 spike), so the all-slot mean (Elo 1658.6) sits *above* slot 1.06 (1636.5) — it prices "a 1st" as if you held a lottery ticket on the 1.01. The tercile mean (1624.1) does not.

**Season, not `years_out`.** The market price keys off the pick's **absolute** season (`2027 Mid 1st`, `2028 1st`), not a `years_out` offset. DP publishes a distinct price per season that already embeds the market's own time discount, and this makes the price immune to the #228 window where the current season's rows are deleted and a `min(season)` recovery of "current season" would silently shift every pick a year closer. Seasons past DP's ~3-year horizon extrapolate from the deepest published season with the shipped `YEAR_DISCOUNT` (so the two curves stay on one clock in the tail).

**When the slot IS known: deliberately NOT used in V1.** The Draft Room (M3–M5) resolves a real order for both platforms, but wiring it into pricing would (a) couple the hot trade path to a live network fetch with its own TTL/circuit-breaker, (b) apply only to the current season, which #228 deletes at draft completion, and (c) give two users of the same league different prices for the same pick depending on whether either had opened the Draft Room. The extension point is named in the code: `_market_round_value` takes `(slot_map, season, round_)` and would gain an optional `slot` that skips the tercile.

---

## 3. Before/after value matrix

Source: `feedback-workspace/m6b/fit_matrix.py` → `fit_matrix.out`. DP snapshot = the committed `backend/tests/fixtures/dp_values_picks_2026-08-06.csv`. Current season = 2026. Values are in the engine value space (`elo_to_value`); Elo shown for readability.

### 3.1 Generic pool rungs — identical in both modes (the point)

| rung | seed Elo | tier_ladder | market_slots | Δ |
|---|---|---|---|---|
| Early 1st | 1720 | 3004.2 | 3004.2 | 0.0 |
| Mid 1st | 1650 | 2117.0 | 2117.0 | 0.0 |
| Late 1st | 1580 | 1491.8 | 1491.8 | 0.0 |
| Early/Mid/Late 2nd | 1520/1460/1400 | 1105.2/818.7/606.5 | same | 0.0 |
| Early/Mid/Late 3rd | 1360/1320/1280 | 496.6/406.6/332.9 | same | 0.0 |
| Early/Mid/Late 4th | 1260/1240/1220 | 301.2/272.5/246.6 | same | 0.0 |

### 3.2 Owned picks — 1QB (`1qb_ppr`)

| pick | ladder value | ladder Elo | market value | market Elo | Δ value | Δ % |
|---|---|---|---|---|---|---|
| 2026 R1 | 2117.0 | 1650 | 1859.5 | 1624 | −257.5 | **−12.2 %** |
| 2026 R2 | 818.7 | 1460 | 434.0 | 1333 | −384.7 | **−47.0 %** |
| 2026 R3 | 406.6 | 1320 | 262.3 | 1232 | −144.3 | −35.5 % |
| 2026 R4 | 272.5 | 1240 | 233.9 | 1209 | −38.6 | −14.2 % |
| 2027 R1 | 1799.5 | 1618 | 1504.6 | 1582 | −294.9 | **−16.4 %** |
| 2027 R2 | 695.9 | 1427 | 389.7 | 1312 | −306.2 | **−44.0 %** |
| 2027 R3 | 345.6 | 1288 | 254.5 | 1226 | −91.1 | −26.4 % |
| 2027 R4 | 231.7 | 1208 | 231.4 | 1207 | −0.3 | −0.1 % |
| 2028 R1 | 1529.5 | 1585 | 1263.0 | 1547 | −266.5 | −17.4 % |
| 2028 R2 | 591.5 | 1395 | 357.5 | 1294 | −234.0 | −39.6 % |
| 2028 R3 | 293.7 | 1255 | 247.8 | 1221 | −45.9 | −15.6 % |
| 2028 R4 | 196.9 | 1175 | 229.7 | 1206 | +32.8 | **+16.7 %** |
| 2029 R1 | 1300.1 | 1552 | 1073.6 | 1514 | −226.5 | −17.4 % |
| 2029 R2 | 502.8 | 1362 | 303.9 | 1262 | −198.9 | −39.6 % |
| 2029 R3 | 249.7 | 1223 | 210.7 | 1189 | −39.0 | −15.6 % |
| 2029 R4 | 167.4 | 1143 | 195.2 | 1173 | +27.8 | **+16.6 %** |
| 2030 R1 | 1105.1 | 1520 | 912.5 | 1482 | −192.6 | −17.4 % |
| 2030 R2 | 427.4 | 1330 | 258.3 | 1229 | −169.1 | −39.6 % |
| 2030 R3 | 212.2 | 1190 | 179.1 | 1156 | −33.1 | −15.6 % |
| 2030 R4 | 142.3 | 1110 | 166.0 | 1141 | +23.7 | +16.7 % |

### 3.3 Owned picks — Superflex (`sf_tep`)

| pick | ladder value | market value | Δ value | Δ % |
|---|---|---|---|---|
| 2026 R1 | 2117.0 | 2263.3 | +146.3 | **+6.9 %** |
| 2026 R2 | 818.7 | 475.2 | −343.5 | **−42.0 %** |
| 2026 R3 | 406.6 | 269.3 | −137.3 | −33.8 % |
| 2026 R4 | 272.5 | 237.0 | −35.5 | −13.0 % |
| 2027 R1 | 1799.5 | 1818.5 | +19.0 | +1.1 % |
| 2027 R2 | 695.9 | 421.9 | −274.0 | −39.4 % |
| 2027 R3 | 345.6 | 259.4 | −86.2 | −24.9 % |
| 2027 R4 | 231.7 | 233.9 | +2.2 | +0.9 % |
| 2028 R1 | 1529.5 | 1518.9 | −10.6 | −0.7 % |
| 2028 R2 | 591.5 | 384.8 | −206.7 | −34.9 % |
| 2028 R3 | 293.7 | 252.8 | −40.9 | −13.9 % |
| 2028 R4 | 196.9 | 232.2 | +35.3 | +17.9 % |
| 2029 R1 | 1300.1 | 1291.1 | −9.0 | −0.7 % |
| 2029 R2 | 502.8 | 327.1 | −175.7 | −34.9 % |
| 2029 R3 | 249.7 | 214.9 | −34.8 | −13.9 % |
| 2029 R4 | 167.4 | 197.4 | +30.0 | +17.9 % |
| 2030 R1 | 1105.1 | 1097.4 | −7.7 | −0.7 % |
| 2030 R2 | 427.4 | 278.0 | −149.4 | −35.0 % |
| 2030 R3 | 212.2 | 182.7 | −29.5 | −13.9 % |
| 2030 R4 | 142.3 | 167.8 | +25.5 | +17.9 % |

### 3.4 Pick-heavy PACKAGES (naive sum — the compounding case)

| package | 1QB ladder | 1QB market | Δ % | SF ladder | SF market | Δ % |
|---|---|---|---|---|---|---|
| three 2027 2nds | 2087.7 | 1169.1 | **−44.0 %** | 2087.7 | 1265.7 | **−39.4 %** |
| 2026 1st + 2027 1st | 3916.5 | 3364.1 | −14.1 % | 3916.5 | 4081.8 | +4.2 % |
| 2027 1st + 2nd + 3rd | 2841.0 | 2148.8 | −24.4 % | 2841.0 | 2499.8 | −12.0 % |
| four future 3rds (27/28/28/29) | 1182.7 | 960.8 | −18.8 % | 1182.7 | 979.9 | −17.1 % |
| 2028 1st + 2029 1st | 2829.6 | 2336.6 | −17.4 % | 2829.6 | 2810.0 | −0.7 % |
| 2026 1st alone ("the 1.01 case") | 2117.0 | 1859.5 | −12.2 % | 2117.0 | 2263.3 | +6.9 % |
| rebuild haul: 27/28/29 1sts + 27/28 2nds | 5916.5 | 4588.4 | **−22.4 %** | 5916.5 | 5435.2 | −8.1 % |

### 3.5 Three corrections to the premise — read these before trusting anything

1. **The plan's premise ("DP's curve is much steeper, so adoption inflates pick values") is WRONG for owned picks, in the opposite direction from what even M6 warned about.** M6 corrected "steeper at the top" to "steeper everywhere, pivoting near Early 1st". The measurement here goes one step further: **a 2026 1st gets 12 % CHEAPER in 1QB**, not dearer. The +96.5 Elo premium exists only on the literal `2026 Pick 1.01` slot; an owned pick with an unknown slot is priced at the round's mid tercile, which sits *below* our Mid rung. There is no 1.01 inflation anywhere in the owned-pick lane. Pinned by `test_the_measured_reshaping_direction_is_deflation_not_inflation`.
2. **The dominant effect is 2nd-round deflation of ~40–47 %, in BOTH formats, at every horizon.** A three-2nds package loses 44 % of its value. This is the number a reviewer should stare at.
3. **There is a tail INVERSION nobody predicted: far-future 4ths get ~17 % DEARER.** Our ladder applies a uniform 15 %/yr discount from a base of 1240 Elo, so a 2030 4th decays to value 142; DP's deep picks sit near the value floor and barely decay, landing at 166. From 2028 onward the market prices a 4th above our ladder. It is small in absolute terms but it re-orders assets: under the market curve a 2029 4th outranks a 2030 3rd, while the ladder says the opposite. This is why `_owned_pick_assets` now caps **after** pricing (`test_owned_pick_assets_caps_after_pricing_not_before`). I believe the ladder, not the market, is the wrong one out there — a uniform geometric discount on a near-worthless asset is not a market model — but that is a finding, not a fix, and I have not touched it.

---

## 4. Deck sanity diff

Source: `feedback-workspace/m6b/deck_diff.py` → `deck_diff_1qb.out`, `deck_diff_sf.out`. Operator's real Lakeview league `1312076055586050048`, worktree DB copy, read-only, **flags based on the real `config/features.json`** (not `DEFAULT_FLAGS` — an all-off overlay diffs the legacy engine, which is not what anyone sees).

### 4.1 A pre-existing bug the diff uncovered — report first, because it dominates the raw numbers

**All 156 of Lakeview's `draft_picks` rows have `pool_value` NULL.** So *today*, `_owned_pick_assets` skips every one of them (`pool_v <= 0: continue`) and the trade engine injects **zero** owned picks for this league. Unlike `_power_picks_by_owner` — which has an explicit "rows synced before the `pool_value` column existed are re-priced via `pick_pool_value` directly" fallback — `_owned_pick_assets` has no such fallback. Picks are simply invisible to the suggestion engine for any league whose rows predate the column.

This is **not M6b's bug**, and M6b is explicitly forbidden from changing today's user-visible pricing, so it is reported and not fixed. But note the consequence: **flipping `trade.slot_pricing` on this league would make 72 pick assets appear out of nowhere**, and a naive read of the diff would attribute that to the repricing. The harness therefore runs a third arm — a "backfilled ladder" baseline with `pool_value` materialised **in memory only** via `pick_pool_value` — which is the honest isolation of the repricing.

### 4.2 Numbers

Deck size is unchanged in every arm (the deck is filled to cap either way). All shapes are `1for1` — this league's decks are 1-for-1s at these caps.

**1QB (`1qb_ppr`), cap 30 (180 cards):**

| arm | injected pick assets | pick-containing cards | fairness min/med/max |
|---|---|---|---|
| `tier_ladder`, real DB (SHIPPED) | 0 | 0 | 0.752 / 0.847 / 1.000 |
| `tier_ladder`, backfilled (baseline) | 72 | 43 (all: user receives) | 0.752 / 0.845 / 1.000 |
| `market_slots` | 72 | **75** (all: user receives) | 0.752 / 0.842 / 1.000 |

- shipped vs market: overlap 105, **150/255 cards changed (59 %)**
- **backfilled vs market (repricing isolated): overlap 103, 154/257 changed (60 %), pick-containing cards 43 → 75 (+74 %)**

**Superflex (`sf_tep`), cap 30 (180 cards):**

| arm | injected pick assets | pick-containing cards | fairness min/med/max |
|---|---|---|---|
| `tier_ladder`, real DB | 0 | 0 | 0.755 / 0.840 / 0.999 |
| `tier_ladder`, backfilled | 72 | 70 (36 recv / 34 give) | 0.755 / 0.866 / 1.000 |
| `market_slots` | 72 | 72 (42 recv / 30 give) | 0.751 / 0.856 / 0.999 |

- **backfilled vs market: overlap 135, 90/225 changed (40 %), pick-containing cards 70 → 72 (+3 %)**

At cap 5 the same picture, smaller: 1QB 20/40 changed isolated, pick cards 10 → 7; SF **2/31 changed**, pick cards 9 → 9.

**Pinned owned-pick probe** (force the deck to send the user's `2026 1st` + `2027 1st`, both arms backfilled so both can see picks): 14 cards in 1QB under both modes, fairness median 0.868 → 0.884. Ladder returns A.J. Brown / Luther Burden / Tyler Warren; market returns Joe Burrow / TreVeyon Henderson / Jaylen Waddle / CMC. SF: 16 cards both arms, fairness median 0.883 → 0.897-ish. **No absurd trade appeared in any arm** — no pick-for-nothing, no stud-for-junk, no fairness score outside the gate.

### 4.3 Reading

- **The deck does not degrade, but it does churn a lot.** 60 % of 1QB cards change identity. That is a large but not obviously wrong response to a 40 % reprice of 2nds/3rds.
- **Picks do not vanish; in 1QB they FLOOD** — pick-containing cards nearly double, and every one is "the user *receives* a pick". That is the deflation working as designed: cheap 2nds/3rds are now affordable sweeteners the engine can offer for the user's fringe players. Whether users want a deck that is 42 % picks (75/180) is a product question, not a math one, and I flag it as the single most likely bad surprise on a flag flip.
- **Superflex is close to a no-op at the deck level** (40 % churn at cap 30, 6 % at cap 5, pick cards flat). Consistent with §3.3: SF round-1 prices already agree with our ladder.
- **The two formats disagree enough that a single "market is better" verdict is not supportable from this data.** If the operator flips this, flipping it per-format is worth considering.

---

## 5. Byte-identity under the legacy mode — proved, not asserted

`backend/tests/test_pick_pricing_m6b.py`:

- `test_m6b_01_flag_off_prices_at_the_stored_value_and_never_reads_dp` — patches `data_loader._fetch_pick_values_csv` to raise, stores `market_slots` for the user, and asserts every price is the stored `pool_value`. The DP source is never touched.
- `test_m6b_02_stored_market_mode_cannot_escape_the_flag` — with the flag off, `pick_pricing_mode_for_user` returns `tier_ladder` **without reading the DB at all** (asserted on a spy).
- `test_m6b_01b_tier_ladder_mode_is_the_stored_value_verbatim` — the stored float itself, no round-trip, including `0.0` and `1.234567`.
- `test_m6b_04_generic_ladder_byte_unchanged_in_every_mode` — `GENERIC_PICK_SEEDS` compared against a spelled-out literal, parametrized over both modes.
- `test_m6b_02c_route_404s_while_the_flag_is_dark` — both verbs.
- `fit_matrix.py` §D on the real 156 Lakeview rows: `tier_ladder == stored pool_value` for **156/156**.

---

## 6. Deviations, and the LLD/HLD-vs-O2 conflicts

### 6.1 LLD/HLD vs the 2026-08-06 operator block

**`hld.md` KD-9 and `lld.md` §4.7 record engine adoption of DP slot values as REJECTED ("display-only"). Operator decision O2 REVERSES both.** Both documents predate the operator block at the bottom of `plan.md`; where they conflict, the operator block wins. Called out in three places as required: a code comment at the head of `backend/pick_values.py`'s M6b section, the already-present comment in `backend/data_loader.py`'s M6 section header (M6 wrote it), and here.

Also amended, and worth naming because it is an *invariant* document rather than a design doc:

- **`docs/cross-client-invariants.md` § "Draft-pick slot values are DISPLAY ONLY"** stated flatly that the map is "not an input to the trade engine, the suggestion pool, `/api/trade/evaluate` or any anchor". After O2 that sentence is false for the first three. Amended in place with the exact new bound (one named seam, owned picks only, opt-in mode, flag-gated) and the anchor/ranking-pool/tier-band exclusions restated. **The section heading still says DISPLAY ONLY** — I left it, because it remains true of `order[].slot_value`, which is what the section is about; a reviewer may reasonably want it renamed.
- **`plan.md` §2 "Out"** lists "slot values in the trade engine" as out of scope, resolved by O2 in the same document. Not edited (it is the plan's own history).

### 6.2 Deviations from the brief

**D-1 — The universal-pool generic-pick seeding was traced and deliberately NOT changed**, although the brief lists it as a chokepoint. Reasons in §1; the decisive one is that tier bands are absolute Elo mirrored across five clients and the pricing mode is per-user, so repricing a shared pool asset would repaint another user's tier colours. Generic rungs are also not roster assets, so they never enter a suggested trade. If a reviewer disagrees, this is the single biggest scope call in the wave and the place to push back.

**D-2 — `dynasty_value`'s `position == "PICK"` branch was traced and needs no change.** It bridges `elo = 1200 + 6*pick_value` off the pseudo-`Player` that `_owned_pick_assets` builds, and that function now sets `pick_value` from the *priced* value. The legacy bridge follows automatically. Touching it would have double-applied the mode.

**D-3 — An existing M6 test was amended, exactly as its own docstring said it would have to be.** `test_m6_02_slot_values_do_not_reach_the_valuation_lanes` asserted that `pick_values.py` never contains `load_pick_slot_values`; that is now false by design. `pick_values.py` dropped out of the parametrize list, `trade_service` / `trade_optimizer` / `ranking_service` still hold, and a **stricter replacement** was added: `test_m6_02b_pick_values_reads_dp_only_through_the_m6b_seam` pins the exact two source lines that may reference the map and asserts both sit inside `market_pick_pool_value`.

**D-4 — `/api/settings/pick-pricing` is flag-gated (404 while dark); `/api/settings/stud-tax` is not.** #214 shipped its route ungated because its mode was always live. Here the mode is inert while the flag is off, so an ungated route would let a user set a preference that silently does nothing.

**D-5 — The default is `tier_ladder`, deliberately breaking the #214 pattern.** #214 shipped `market` as the default. The brief and O2 authorise the toggle and the calibration, not a default change. Pinned by `test_m6b_02b_defaults_are_todays_behaviour`.

**D-6 — Mode spelling.** The handoff wrote "market-slots / tier-ladder"; the repo's stored-mode convention is lowercase snake (`stud_tax_mode` = `market`/`heavy`/`off`, `ranking_method`), so these are `tier_ladder` / `market_slots`. Same strings in the DB, the API, the flag comment and the client.

**D-7 — Not repriced: `_power_picks_by_owner` (power rankings) and `/api/league/picks`.** Both are display surfaces, not the trade engine, and both are outside the brief's scope. A consequence worth naming: with the flag on, a user's power-rankings pick totals and their trade-engine pick values would disagree. Listed in §9.

**D-8 — The deck harness needed a third arm and a flag-source change** (§4.1, §4). Both are harness-only (`feedback-workspace/`, gitignored).

**D-9 — Files touched that the brief did not list:** `backend/tests/test_slot_values.py` (D-3, unavoidable) and `data/` in the worktree (a read-only `sqlite3 .backup` of the operator's DB plus a copy of `.sleeper_players_cache.json`, needed to build the universal pool; `/data/` is gitignored). Nothing in `backend/draft_board_service.py`, `backend/data_loader.py`, `backend/mfl_service.py`, or the Draft Room route region.

---

## 7. The future third mode (personalized pick pricing) — how it slots in

**Not built.** Concretely, a third mode `my_board` would need:

1. **`PICK_PRICING_MODES` += `"my_board"`** in the three mirrors (`pick_values`, `trade_service`, `database`) — already a tuple, and `test_m6b_02b` asserts the three agree, so adding it in one place fails loudly.
2. **`priced_pool_value` needs the user id**, which it does not take today. It resolves the *mode* from a thread-local; the same pin would have to carry the user id (or `pick_pricing_override(mode, user_id=...)` gains a second field). Every call site already runs inside a pin that knows the user (`_inject_owned_picks` takes `user_id`; `trade_evaluate_route` resolves the session), so no call-site signature changes — this is the one real piece of work.
3. **A new branch in `_market_round_value`'s place**: read the user's rookie board (`member_rankings` / the tier-override blob for the user+format), take the rookie subset in board order, and map the round's basis slots onto that ordering — i.e. "my 5th-through-8th-ranked rookie" instead of "DP's slots 5–8". The value would come from the user's own Elo for those players, so it lands in the same value space with no new calibration. The mid-tercile basis carries over unchanged, which is a real argument for having chosen it.
4. **What would break, honestly:**
   - *Fallback density.* A user who has ranked 6 rookies cannot price a round-3 pick. Needs the same "no price ⇒ fall back to the ladder" rule, per round, and it will fire often.
   - *Cache/TTL.* DP's map is process-cached for 24 h; a per-user board read is a DB hit on the hot pricing path, once per pick per job. `_owned_pick_assets` prices up to `12 × picks_pool_cap` rows per job — the board would need to be loaded once per job and passed down, not looked up per pick.
   - *Which board.* Under M2 the rookie scope is a *view filter* over the one per-user-per-format board; a personalized pick price must read the same board, or it forks the Elo space the plan spent two review rounds preventing (D2).
   - *Asymmetry.* The engine prices both sides of a trade. Pricing the *opponent's* picks off *your* board is defensible (it is your valuation) but it is a change in kind from today, where `pool_value` is symmetric. That is a product decision, not a code one.
5. **Nothing in this wave precludes it.** `load_pick_slot_values` returns a plain `label → Elo` dict; `priced_pool_value` is a single seam with a mode parameter; the flag, the column and the route already carry an open-ended string.

---

## 8. Gates

| Gate | Result | Exit code |
|---|---|---|
| Baseline on `93840b1`: `python3 -m pytest backend/tests -q` | **1733 passed, 1 skipped** | 0 |
| After M6b: `python3 -m pytest backend/tests -q` | **1759 passed, 1 skipped** (+26 in `test_pick_pricing_m6b.py`; `test_slot_values.py` net 0 — one parametrize case removed, one test added) | 0 |
| `cd mobile && npx tsc --noEmit` | clean | 0 |

Exit codes captured explicitly (`echo "EXIT=$?"` on the pytest/tsc invocation itself), not inferred from `tail`.

---

## 9. What the reviewing session should scrutinise hardest — ranked

1. **The unknown-slot basis (§2), because everything else is downstream of it.** `_basis_slots(1) == [5,6,7,8]` and the value-space mean are the whole repricing. Re-derive it: if the basis were slot 1.06 instead of the tercile mean, a 2026 1st would price at Elo 1636.5 instead of 1624.1 and the −12.2 % would become −10 %. If it were the all-slot mean it would become *positive*. The direction of the headline finding is basis-dependent, and I chose the basis.
2. **The 2nd-round deflation of 40–47 % (§3.2/3.4).** This is the number with the most user-visible consequence, it is consistent across formats and horizons, and it is what makes a three-2nds package lose 44 %. Sanity-check it against a human's intuition of what three 2027 2nds are worth before anyone flips the flag.
3. **The deck flood in 1QB (§4.2): pick-containing cards 43 → 75.** Verify this is the deflation and not a gate artifact. Specifically: cheap picks now clear the fairness gate as sweeteners, so the engine may be padding decks with pick-for-fringe-player trades that users find noisy.
4. **The NULL `pool_value` finding (§4.1).** Not M6b's bug, but it means flipping the flag on a league with unbacked rows changes pick *visibility*, not just pick price. Decide whether that backfill should land before or independently of this flag.
5. **The far-future 4th inversion (§3.5 item 3) and the cap-after-pricing rule it forced.** Confirm `_owned_pick_assets` sorting on the priced value is right, and that no other caller assumes `pool_value` order.
6. **`_inject_owned_picks`'s pin scope.** The `with pick_pricing_override(...)` wraps only `_owned_pick_assets`. That is correct today (all pricing happens inside it) but it is a `with` block whose correctness depends on where pricing lives — verify nothing below it prices a pick.
7. **`/api/trade/evaluate`'s double pin.** The route now enters two context managers and resolves the session at most once for both. Check the `_sess_for_mode is None` reuse does not change #215's behaviour for anonymous Mode A callers.
8. **The amended M6 test (D-3).** Confirm the replacement is genuinely stricter, not just different.
9. **The `market_slots` extrapolation past 2028.** `YEAR_DISCOUNT ** (season - horizon)` re-introduces exactly the uniform geometric discount the market curve was adopted to replace. It is the pragmatic choice, and it is also the reason far-future 4ths invert.
10. **Superflex.** Everything above is worst in 1QB. If the operator only ever flips this for SF leagues, most of §3 and §4 stops mattering — worth knowing before the calibration argument is had.

---

## 10. Open questions for the operator

1. **Do you want this at all, given §3.5?** The stated motivation was "DP's curve is steeper, our picks are underpriced". The measurement says the opposite for owned picks: adopting the market makes almost every pick *cheaper*, and 2nds dramatically so. If the intent was "make 1.01s expensive", this wave does not deliver it — that would need true-slot pricing (§2, deferred), which only ever applies to the current season.
2. **Per-format flip?** 1QB churns 60 % of the deck; SF churns 40 % at cap 30 and 6 % at cap 5.
3. **The NULL `pool_value` backfill** (§4.1) — separate item, before or after this flag?
4. **`_power_picks_by_owner` / `/api/league/picks`** (D-7) — should the display surfaces follow the mode, or is a disagreement between "my pick capital" and "what the engine pays" acceptable?
5. **Flag review clock.** `trade.slot_pricing` starts its 90-day ship-by/kill-by clock on merge.
