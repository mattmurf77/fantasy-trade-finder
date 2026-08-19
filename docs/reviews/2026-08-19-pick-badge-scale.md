# The round-3 badge was a wrong inverse, not a round-3 overprice

**Date:** 2026-08-19
**Decision:** [D-088](../../living-memory/DECISIONS.md)
**Closes:** Q-019
**Trigger:** after D-084 lowered the `second` floor to 1370, a current-year 3rd-round pick began badging **`second`** on the picks screen.
**Predecessors:** [2026-08-19-ktc-pick-value-comparison.md](2026-08-19-ktc-pick-value-comparison.md) (D-084, round-2 recalibration) · [2026-08-19-pick-year-valuation.md](2026-08-19-pick-year-valuation.md) (D-079, the year axis)

---

## Table of contents

- [The short version](#the-short-version)
- [Verifying the compression claim](#verifying-the-compression-claim)
- [The actual defect: two maps, one of them the wrong inverse](#the-actual-defect-two-maps-one-of-them-the-wrong-inverse)
- [Why 1383.5, exactly](#why-13835-exactly)
- [Mapping or seeds? Mapping, and not the one the memo pointed at](#mapping-or-seeds-mapping-and-not-the-one-the-memo-pointed-at)
- [Before and after](#before-and-after)
- [Blast radius, measured in prod](#blast-radius-measured-in-prod)
- [What this does NOT change](#what-this-does-not-change)
- [What Q-019 becomes](#what-q-019-becomes)
- [Sources](#sources)
- [What I could not determine](#what-i-could-not-determine)

---

## The short version

**The round-3 pick is not overpriced by our engine. Its badge was computed with the wrong inverse.**

A current-year 3rd is priced at **Elo 1320** — the `(3, "Mid")` rung of `GENERIC_PICK_SEEDS`, which sits **45 Elo points inside** the `third` band (1280–1365). Nothing about that price changed under D-084 and nothing about it is in dispute.

What produced the `second` badge is a display-path scale confusion in `GET /api/league/picks`. The route stored-value → Elo conversion used **`data_loader.seed_elo_for_value`**, which inverts DynastyProcess's raw 0–10000 consensus scale. But `draft_picks.pool_value` is in **`elo_to_value` units** (`backend/database.py:1040` says so in the column comment), and the exact inverse of *that* is **`trade_service.value_to_elo`**.

The two maps cross at exactly **Elo 1548.0** and diverge in both directions. Below the crossing point the wrong inverse **inflates**, and the inflation grows the cheaper the asset:

| Rung | true seed Elo | badge Elo (#320 inverse) | error |
|---|---|---|---|
| 1st Early | 1720 | 1698.7 | −21.3 |
| **1st Mid** | 1650 | 1635.5 | −14.5 |
| 1st Late | 1580 | 1574.7 | −5.3 |
| 2nd Mid | 1400 | 1435.2 | **+35.2** |
| **3rd Mid** | **1320** | **1383.5** | **+63.4** |
| 3rd Late | 1280 | 1360.4 | +80.4 |
| **4th Mid** | **1240** | **1339.3** | **+99.3** |
| 4th Late | 1220 | 1329.5 | **+109.5** |

The reported symptom is the +63.4 line. D-084 lowered `second.min` to 1370; the inflated 1383.5 cleared it by 13.5. **The map error alone was 4.7× the margin that flipped the badge.**

The fix is one expression in one route. No price moves, no seed moves, no tier band moves, no client mirror moves.

---

## Verifying the compression claim

The D-084 memo's structural claim — quoted in the task and repeated as a code comment in `backend/pick_values.py` — is:

> our seed map compresses ranks 200–300 into 32 Elo points, so the 3rd/4th divergence (~68 ranks) is largely a `seed_elo_for_value` floor artifact and is **not fixable via seeds**

**The claim is true. I re-derived it independently and it holds, with a slightly different constant.**

Measured against the checked-in snapshot `backend/tests/fixtures/dp_values_snapshot_2026-07-10.json` (`1qb_ppr`, 641 players, all four positions pooled and sorted value-desc), through the shipped `data_loader.seed_elo_for_value`:

| consensus rank | DP value | seed Elo |
|---|---|---|
| 1 | 10232 (clamps to 10000) | 1927.3 |
| 50 | 3647 | 1734.5 |
| 65 | 2372 | 1655.8 |
| 100 | 1028 | 1513.7 |
| 140 | 382 | 1376.1 |
| 200 | 100 | 1262.9 |
| 230 | 55 | 1237.0 |
| 250 | 29 | 1220.4 |
| 300 | 11 | 1208.0 |
| 400 | 4 | 1202.9 |

**Resolution per rank, by band:**

| rank band | Elo span | Elo per rank |
|---|---|---|
| 50 → 100 | 220.8 | **4.417** |
| 100 → 200 | 250.8 | **2.508** |
| **200 → 300** | **54.9** | **0.549** |

Ranks 200–300 get **54.9 Elo points**, i.e. **one eighth** the per-rank resolution of ranks 50–100. (The memo said 32 points for ranks 230–300; on this snapshot that same 70-rank window is 29.0 points. Same phenomenon, and my 200–300 window is the wider one.)

**Why.** `seed_elo_for_value` is affine in *value* space and then logarithmic into Elo:

```
v(dp)  = 223.130 + dp × 0.824487          # SEED_VALUE_FLOOR, (CEIL−FLOOR)/10000
elo(dp) = 1500 + ln(v / 1000) / 0.005
```

The constant floor **223.130** dominates once `dp` is small. At rank 200, `dp = 100` → `v = 305.58`. At rank 300, `dp = 11` → `v = 232.20`. The DP value fell by **89 %** but `v` fell by only **24 %**, because 223.130 of it is a constant that DP never contributed. `ln(305.58/232.20)/0.005 = 54.9`. As `dp → 0` every player converges onto Elo 1200 regardless of how much worse than each other they are.

**Consequence for the ladder, and the arithmetic the D-084 memo was pointing at.** The market-implied Elo for a Mid 4th is ≈1207 (memo's number), which lands inside the `waivers` band (1150–1215). To move a Mid 3rd from rank ~165 to the market's rank ~231 you would need to push its seed from 1320 down to roughly 1237 — below the `fourth` floor of 1220's neighbourhood and straight through two bands. **So the memo's conclusion stands: you cannot buy 3rd/4th rank-equivalence by editing `GENERIC_PICK_SEEDS`, because the destination ranks have almost no Elo room to land in.**

**But that has nothing to do with the reported badge.** The compression governs where *players* sit. The badge is computed from a *pick's stored price*, and never touches the player board at all.

---

## The actual defect: two maps, one of them the wrong inverse

There are two distinct value↔Elo maps in this codebase and they are not inverses of each other.

| | maps | forward | true inverse |
|---|---|---|---|
| **Engine curve** | tier-band Elo ↔ engine value | `trade_service.elo_to_value(e) = 1000·e^{0.005(e−1500)}` | `trade_service.value_to_elo` |
| **Consensus seed map** | DP 0–10000 ↔ tier-band Elo | `data_loader.seed_value_for_elo` | `data_loader.seed_elo_for_value` |

`draft_picks.pool_value` is produced by `pick_values.pick_pool_value`, which is literally `elo_to_value(GENERIC_PICK_SEEDS[(r, "Mid")]) × decay^years` (`backend/pick_values.py:264-266`). It is therefore an **engine-curve value**, and `backend/database.py:1040` labels the column exactly that: `# #158: engine/calculator value scale (elo_to_value units)`.

`server.py`'s `_pick_tier` inverted it with `seed_elo_for_value` — the inverse of the *other* map. That applies DP's affine rescale (`× 0.824487`, `+ 223.130`) to a number that was never on the DP scale.

**Proof that it is the wrong inverse, in one line.** For the correct inverse, `value_to_elo(elo_to_value(E)) == E` for every `E`. For the shipped one, `seed_elo_for_value(elo_to_value(E)) == E` holds at exactly **one** point:

```
223.130 + 0.824487·v = v   ⟹   v = 1270.9   ⟹   E = 1500 + ln(1.2709)/0.005 = 1548.0
```

Everywhere else it is wrong, deflating above 1548.0 and inflating below it. Every pick rung except the three round-1 rungs sits below 1548.0.

**Proof that `value_to_elo` is what the tier config already assumes.** `backend/tier_config.json`'s own `_calibration` field states: *"first_1 floor = Late 1st seed 1580 … second floor = Late 2nd 1370; third floor = Late 3rd 1280; fourth floor = Late 4th 1220."* The bands are **defined** as rungs of `GENERIC_PICK_SEEDS`, which is only coherent if those seeds live on the tier-band Elo scale. A badge that puts a current-year Mid 3rd anywhere but `third` contradicts the file that defines the bands. `value_to_elo` restores the identity exactly:

```
value_to_elo(pick_pool_value(r, 0)) == GENERIC_PICK_SEEDS[(r, "Mid")]   for r ∈ {1,2,3,4}
```

That identity is now pinned by `test_league_picks_tier.py::test_current_year_rungs_badge_their_own_round`.

**This is the #263 bug class, one level in.** #320's comment shows the author knew the hazard — *"never `pool_value` passed straight in (elo_to_value scale ≠ tier-band Elo scale, the exact #263 bug)"* — and reached for an inversion. It reached for the wrong one. The comment's own diagnosis names `elo_to_value` as the offending scale and then does not use `elo_to_value`'s inverse.

---

## Why 1383.5, exactly

Worked end to end, so the number in the bug report is accounted for with nothing left over.

```
GENERIC_PICK_SEEDS[(3, "Mid")]              = 1320
pick_pool_value(3, 0)
  = elo_to_value(1320)  = 1000·e^{0.005·(1320−1500)}   = 406.570   ← stored pool_value

CORRECT   value_to_elo(406.570) = 1500 + ln(0.40657)/0.005          = 1320.0  → third
SHIPPED   seed_elo_for_value(406.570)
          v = 223.130 + 406.570 × 0.824487                          = 558.32
          e = 1500 + ln(0.55832)/0.005                              = 1383.5  → second
```

`1383.5 − 1370 = 13.5` above the new `second` floor. `1383.5 − 1320 = 63.4` of pure map error. **Remove the map error and the pick sits 45 Elo below the floor it was accused of clearing.**

The same walk for a current-year 4th: true Elo 1240 (`fourth`, floor 1220); shipped badge Elo 1339.3 → `third`. **That one was already wrong before D-084 and nobody noticed**, because `third`'s max was 1395 then and 1339.3 fell inside it either way. D-084 did not create the class of defect; it moved one band edge past one inflated number and made a single instance visible.

---

## Mapping or seeds? Mapping, and not the one the memo pointed at

The task framed the choice as *mapping vs seeds*, with the D-084 memo asserting that seeds cannot do it. Both readings assumed the fix lives in `seed_elo_for_value`.

**It is a mapping fix, but the mapping at fault is the display path's choice of inverse, not `seed_elo_for_value` itself.** `seed_elo_for_value` is correct for what it does — mapping DynastyProcess values onto seed Elo — and it is used correctly everywhere else in the codebase, including `load_pick_slot_values` (`backend/data_loader.py:781`), which feeds it genuine DP 0–10000 pick-slot prices.

Why not the alternatives:

- **Not the seeds.** Elo 1320 for a Mid 3rd is not the defect. Moving it would be repricing a well-corroborated ladder to compensate for a display bug, and the D-084 memo already measured that path breaking `test_tier_occupancy.py` in three places.
- **Not the tier bands.** Nothing about the bands is wrong. Moving them would drag all five client mirrors (G-051) and repaint every player's board to work around a pick-badge arithmetic error.
- **Not re-anchoring `seed_elo_for_value` to decompress the floor.** This is the change the D-084 memo gestured at, and it is genuinely open — but it is a *rank-equivalence against the outside market* question, and it would move **every player's seed Elo in the app**, changing tier occupancy, deck composition, matchup selection and every user's board. Spending that blast radius to fix a badge that a one-expression change fixes correctly would be backwards. It is re-logged as Q-021.
- **Not clamping or special-casing round 3.** That papers over an error that is present on ten of the twelve rungs.

---

## Before and after

Route: `GET /api/league/picks`, `1qb_ppr` bands, position `None` (general-pool fallback; pick value is position-uniform). Current season 2026.

| pick | `pool_value` | badge Elo before | before | badge Elo after | after |
|---|---|---|---|---|---|
| 2026 1st | 2117.0 | 1635.5 | `first_1` | **1650.0** | `first_1` |
| 2026 2nd | 606.5 | 1435.2 | `second` | **1400.0** | `second` |
| **2026 3rd** | **406.6** | **1383.5** | **`second`** | **1320.0** | **`third`** |
| **2026 4th** | **272.5** | **1339.3** | **`third`** | **1240.0** | **`fourth`** |
| 2027 2nd | 515.6 | 1413.3 | `second` | 1367.5 | `third` |
| 2027 3rd | 345.6 | 1364.6 | `third` | 1287.5 | `third` |
| 2027 4th | 231.7 | 1323.7 | `third` | 1207.5 | `waivers` |
| 2028 3rd | 293.7 | 1347.0 | `third` | 1255.0 | `fourth` |
| 2029 1st | 2117.0 | 1635.5 | `first_1` | 1650.0 | `first_1` |
| 2029 4th | 167.4 | 1330.7 | `third` | 1142.5 | **`null`** |

**The two rungs the task asked about are both fixed**, and both land on their own round's name.

**The one badge that disappears rather than dropping** is a 2029 4th. Under D-079 rounds 2–4 still decay 15 %/yr, so a 2029 4th is worth Elo 1142.5 — 7.6 points below the `waivers` floor of 1150, i.e. genuinely worth less than the cheapest banded asset. `tier_for_elo` returns `None` there, which is the documented null-tier contract (`docs/api-reference.md`: *"absent on old servers → clients fall back to the numeric"*), and mobile already handles it (`InLeagueCalculator.tsx:273` only writes the map entry `if (p.tier)`). Claiming `third` for that pick — that a 2029 4th is worth a 3rd-round pick — was the less honest of the two options.

---

## Blast radius, measured in prod

Read-only queries against the prod Postgres (`SET TRANSACTION READ ONLY`, SELECT only), 2026-08-19.

### How often do 3rds and 4ths reach a served card? Almost never.

Joining `deck_impressions.assets_json` against `draft_picks.pick_id` over all 2,376 impressions carrying an asset list:

| | count | share |
|---|---|---|
| Cards containing ≥1 pick | 1,329 | **55.9 % of served cards** |
| Pick mentions total | 1,909 | — |
| — round 1 | 1,545 | **80.9 %** of pick mentions |
| — round 2 | 337 | 17.7 % |
| — **round 3** | **27** | **1.4 %** |
| — **round 4** | **0** | **0.0 %** |

Cards containing at least one 3rd: **27 of 2,376 = 1.1 %**. Containing a 4th: **zero**.

**Stated plainly, as the task asked: rounds 3 and 4 barely touch real decks.** This corroborates the companion memo's framing (picks in 58.5 % of cards, firsts 84 % of mentions) on a fresh pull. If this were a *pricing* change it would be close to unjustifiable on its own merits — which is a further argument for not repricing anything.

### Where it does matter: the picks screen and the calculator

The badge does not appear on deck cards at all — picks never carry a `tier` in `/api/trade/evaluate`'s `per_player`, `eveners` or `slots` rows (`backend/server.py:1032`, `:1168`; a pick's label already reads as a rung). It appears on **every row of `GET /api/league/picks`**, which is what the picks screen and the in-league calculator's pick picker render.

Every one of the 1,104 stored pick rows in prod (7 leagues, all with a non-NULL `pool_value`) was being badged through the wrong inverse. Recomputing both ways over the **actual stored** `pool_value`s:

| transition | rows | |
|---|---|---|
| `first_1` → `first_1` | 164 | unchanged |
| `second` → `second` | 252 | unchanged |
| `third` → `third` | 88 | unchanged |
| `third` → `fourth` | 188 | corrected |
| `third` → `waivers` | 152 | corrected |
| `second` → `third` | 136 | corrected |
| `second` → `first_1` | 62 | corrected (stale pre-D-079 2028 1sts at `pool_value` 1529.5 → Elo 1585, above the Late 1st rung) |
| `third` → `null` | 62 | corrected (below the `waivers` floor) |
| **total** | **1,104** | **600 change (54.3 %)** |

**Reading that honestly:** 600 changed badges is not a small display change, and it is more than the reported symptom. It is the correct size, because the defect was present on every rung below a mid-1st and grew with cheapness. The direction is downward on 538 of the 600 and upward on 62, and every one of them moves from a demonstrably wrong Elo to the pick's actual price.

---

## What this does NOT change

Explicit, because the task named these as bright lines.

| | status |
|---|---|
| `GENERIC_PICK_SEEDS` | **byte-unchanged** |
| `backend/tier_config.json` bands | **byte-unchanged** |
| `mobile/src/utils/tierBands.ts` (fallback mirror) | **untouched** |
| `web/positional-tiers.html` (fallback mirror) | **untouched** |
| `web/js/app.js` `_eloToTierLabel` (pure hardcode, G-051) | **untouched** |
| `backend/scripts/replay_trade_decisions.py` seed map | **untouched** |
| `draft_picks.pool_value` (stored prices) | **never written by this change** |
| Trade engine / deck / matchup selection | unaffected — the badge is a serializer field |
| `backend/tests/test_tier_occupancy.py` | **47 passed, unchanged** — it walks player seed Elos, which this does not touch |

No tier band moved, so the five-mirror rule in `docs/cross-client-invariants.md` is not triggered. That is a consequence of choosing the display-path fix, not an oversight.

---

## What Q-019 becomes

Q-019 asked whether the round-3 badge required opening the seed map. **Answer: no.** It is closed as **answered**, with the badge defect resolved here.

The part of it that was genuinely a seed-map question — *whether `seed_elo_for_value`'s floor compression should be re-anchored so 3rds and 4ths reach their market-equivalent player ranks* — is **not** closed, and is re-logged as **Q-021**, sized correctly this time: it moves every player's seed Elo, so it is an occupancy-and-deck change, not a pick change. The prod numbers above are the argument for leaving it parked: rounds 3–4 are 1.4 % of pick mentions and 0 % of 4th-round mentions in 2,376 served cards.

---

## Sources

| Source | What it gave | Pulled (UTC) |
|---|---|---|
| Prod Postgres (`DATABASE_URL_PROD`, `SET TRANSACTION READ ONLY`) | `draft_picks` round/season/`pool_value` distribution (1,104 rows, 7 leagues); `deck_impressions.assets_json` pick-round mentions (2,376 impressions) | **2026-08-19** |
| `backend/tests/fixtures/dp_values_snapshot_2026-07-10.json` | the 641-player `1qb_ppr` consensus board used for the compression table (checked in, deterministic) | — |
| `backend/data_loader.py`, `backend/pick_values.py`, `backend/trade_service.py`, `backend/tier_config.json`, `backend/server.py` | the shipped maps and constants, executed rather than read | — |

Every Elo/value figure in this memo was computed by running the shipped functions, not by re-implementing them. No external network source was consulted; none was needed, because the question turned out to be internal arithmetic rather than market opinion.

---

## What I could not determine

- **How many users have actually seen a wrong pick badge.** `deck_impressions` covers deck cards, which carry no pick badges. There is no impression log for the picks screen or the calculator's pick picker, so the 1,104-row count is the *population at risk*, not observed views.
- **Whether any user made a trade decision off an inflated badge.** The badge is display-only and every price the engine used was correct, so a decision would have to have been driven by the label alone. Not measurable with what is logged.
- **Whether the `null` badge on a 2029 4th reads acceptably on device.** Mobile's fallback is documented and the code path is the same one an unpriced row takes, but this was not observed at runtime — it is item 4 of the TestFlight checklist in the scope block.
- **Why prod holds pre-D-079/D-084 `pool_value`s** (2027 1sts at 1799.5, 2026 2nds at 818.7). Those leagues have not re-synced since those decisions shipped hours ago. It does not affect this change — the fix is correct for any stored value — but it means some badges will move again on the next sync, for an unrelated reason.
- **Whether `seed_elo_for_value`'s floor compression is a defect or an intentional choice.** Unchanged from the D-084 memo's finding: the docstring explains the ceiling anchor and says nothing about the floor. Carried into Q-021.
