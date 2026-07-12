# #117 / #118 — 8-tier pick-value ladder + consensus seed recalibration

Operator decision: **"B + 8 tiers"** — ship the exact 8-tier ladder from the
feedback AND recalibrate the consensus value scale so consensus players can
actually reach the top tiers (option B). 2026-07-12, branch `trade-engine-v2`.

## The ladder

| Key | Label | Floor (Elo) | Rung |
|---|---|---|---|
| `firsts_4plus` | 4+ 1sts | 1927 | value_to_elo(4 × Mid 1st) = 1927.3 (max 1972, just under the 5-firsts rung 1972.3) |
| `firsts_3` | 3 1sts | 1869 | value_to_elo(3 × Mid 1st) = 1869.7 |
| `firsts_2` | 2 1sts | 1788 | value_to_elo(2 × Mid 1st) = 1788.6 |
| `first_1` | 1st | 1580 | Late 1st seed |
| `second` | 2nd | 1400 | Late 2nd seed |
| `third` | 3rd | 1280 | Late 3rd seed |
| `fourth` | 4th | 1220 | Late 4th seed |
| `waivers` | Waivers | 1150 | below-4th floor (below 1150 = unranked; `no_value` anchor at 1100 stays under every band) |

Same "just-under-the-rung" floor logic and old→new key safety as the
2026-07-11 six-tier migration: `tier_overrides` store raw Elo (auto
re-bucket), `apply_tiers` no-ops retired keys (`firsts_2plus`, `bench`).
New colors: `firsts_4plus` red-400 `#f87171`, `firsts_3` fuchsia-400
`#e879f9`; gold carries to `firsts_2`; `waivers` inherits the bench gray.

## The recalibration (why + math)

**Problem:** DynastyProcess values seeded Elo linearly
(`elo = 1200 + dp/10000 × 600`, ceiling 1800), while trade values map back
exponentially (`value = 1000·e^(0.005(elo−1500))`). The ceiling (DP 10000 →
Elo 1800 → value 4482 ≈ 2.1 firsts) sat BELOW the 3-firsts rung — a
calibration artifact, not a market truth. It also priced a Mid 1st (Elo
1650 → 2117) at ~47% of the ceiling; real dynasty markets price a mid 1st
at ~25–30% of a top asset, and top assets genuinely trade for 3–4 firsts.

**Mechanism chosen:** treat the DP scale as what it is — a linear
trade-value scale — and map it AFFINELY onto the engine's value space, then
back through the (unchanged) exponential curve:

```
v(dp)   = V0 + (min(dp, 10000)/10000) × (V4 − V0)
elo(dp) = 1500 + ln(v/1000)/0.005          (data_loader.seed_elo_for_value)

V0 = value(Elo 1200) = 1000·e^(−1.5)      ≈  223.13   (DP 0 → Elo 1200, the old floor, unchanged)
V4 = 4 × value(Mid 1st, Elo 1650)          ≈ 8468.0    (DP 10000 → Elo ≈ 1927.3, the 4-firsts rung)
```

Two-point calibration: the bottom anchor is exactly the old map's floor, the
top anchor is exactly the 4-firsts rung. The Elo↔value exponential, all
pick rungs (`GENERIC_PICK_SEEDS`), the league-pick bridge
(`elo = 1200 + 6·pick_value`, 0–100 scale), and fairness/package math are
untouched. Under this map a Mid 1st (value 2117) ≈ DP 2297 ≈ 25% of the top
asset — the KTC-style ratio.

**Before/after, top overall consensus assets (2026-07-10 DP snapshot):**

| Format | Asset (dp) | Old | New | New tier |
|---|---|---|---|---|
| 1QB | WR 10232 | 2.12 firsts | 4.00 firsts | firsts_4plus |
| 1QB | WR 9716 | 1.94 | 3.89 | firsts_3 |
| 1QB | RB 9580 | 1.87 | 3.84 | firsts_3 |
| 1QB | WR 9184 | 1.66 | 3.68 | firsts_3 |
| 1QB | RB 9098 | 1.62 | 3.65 | firsts_3 |
| SF | QB 10208 | 2.12 | 4.00 | firsts_4plus |
| SF | WR 9119 | 1.63 | 3.66 | firsts_3 |
| SF | QB 9034 | 1.58 | 3.62 | firsts_3 |
| SF | WR 8538 | 1.37 | 3.43 | firsts_3 |
| SF | QB 8379 | 1.30 | 3.37 | firsts_3 |

Assets 6–15 read 2.7–3.4 firsts (1QB) / 3.0–3.4 (SF) — the "next shelf ≈
2–3+ firsts" market shape. DP floor cutoffs per tier: firsts_4plus ≥ dp
9987, firsts_3 ≥ 7405, firsts_2 ≥ 4849, first_1 ≥ 1539, second ≥ 465,
third ≥ 133, fourth ≥ 29.

**Occupancy (snapshot, seeds only — user anchors/rankings can move players):**

1QB PPR:
| Pos | 4+1sts | 3 1sts | 2 1sts | 1st | 2nd | 3rd | 4th | Waivers |
|---|---|---|---|---|---|---|---|---|
| QB | 0 | 0 | 2 | 11 | 10 | 7 | 10 | 54 |
| RB | 0 | 3 | 7 | 13 | 11 | 16 | 18 | 113 |
| WR | 1 | 6 | 10 | 19 | 24 | 17 | 27 | 133 |
| TE | 0 | 0 | 2 | 7 | 8 | 12 | 10 | 90 |

SF TEP:
| Pos | 4+1sts | 3 1sts | 2 1sts | 1st | 2nd | 3rd | 4th | Waivers |
|---|---|---|---|---|---|---|---|---|
| QB | 1 | 7 | 6 | 9 | 8 | 9 | 6 | 48 |
| RB | 0 | 1 | 4 | 15 | 8 | 18 | 26 | 109 |
| WR | 0 | 6 | 4 | 19 | 27 | 19 | 30 | 132 |
| TE | 0 | 0 | 0 | 8 | 8 | 10 | 16 | 87 |

Empty top tiers for weak positions (e.g. TE) are expected — the ladder
defines the scale. Pinned by `backend/tests/test_tier_occupancy.py`.

## Downstream effects handled

- **Fairness (ratio-based):** player values are now affine in DP, not
  exponential — mid-market 1-for-1s read fairer (dp 6000 vs 8000: 0.55 →
  0.76), low-end gaps less fair (dp 500 vs 1500: 0.74 → 0.44); both match
  market intuition. The fairness-golden suite needed **zero pin changes**
  (fixtures set Elo directly; the gate math is untouched).
- **Anchor scale (#111) re-derived:** `ANCHOR_TOP_TIER_FIRSTS_DEFAULT`
  2 → 4, γ = log 4 / log N. Default anchor Elos are byte-identical
  (γ = 1 at N = 4); a scaled user's own N-firsts answer pins to the
  4-firsts rung (was the 2-firsts rung). Stored `users.anchor_scale`
  values keep their semantics.
- **player_value_history:** in-place rescale migration (invertible old
  map → new map), marker-guarded (`model_config.value_history_seed_scale`),
  atomic claim against concurrent boots. Personal `elo_history` NOT
  rescaled (no closed form) — 30d personal-trend distortion accepted,
  ages out; see runbook.
- **Trio boundary probing:** 8 bands → 7 probe edges; selector behavior
  re-verified by the trio boundary/variety suites (incl. the FB-97
  anti-repeat bounds on the recalibrated realistic pool).
- **Star tax:** now steps over 8 rungs — same value distance spans more
  tier steps, penalties bite sooner (documented in the docstring).
- **Engine value bins** (`_TIER_ELITE`/`_TIER_STARTER`, `_tier_mult_v2`
  Elo bands): deliberately unchanged; under the new scale they finally
  bind at their documented intent (elite ≈ dp 4580+, starter ≈ dp 1550+).
  Runtime knobs (`min_side_surplus`, `waiver_slot_cost`, `mutual_gain_cap`)
  left as-is — retune via `model_config` if deck quality shifts.
- **Mobile 0–10k display value** (`utils/playerValue.ts`) — an
  undocumented mirror of the old linear map, found via components.md —
  recalibrated to the new inverse.
