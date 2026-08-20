# Arm-B engine audit — validation of external-review claims 3 and 4

**Date:** 2026-08-19
**Scope:** verification only. No engine code, flag, or knob was changed by this work.
**Baseline:** `origin/main` = `16d277f5c12a8d1c36b36534b74ac1cabe0df0a3` ("Merge pick horizon (D-091) + slot labels (D-090); rule Q-023"). Every line number below is on that commit.
**Empirical basis:** READ-ONLY prod (`SET TRANSACTION READ ONLY`, SELECT only), plus an offline replay of six real prod boards through the real `RankingService` / `TradeService`.

---

## 0. Verdict summary

| Sub-claim | Verdict |
|---|---|
| 3a — R5 judges only the PRIMARY received asset | **CONFIRMED** |
| 3b — the kill matrix is as quoted | **PARTIALLY CONFIRMED** (quote is accurate but drops three PASS exemptions and the consensus-board caveat that materially weaken "hard filter") |
| 3c — no partner-need term anywhere in R5 | **CONFIRMED** |
| 3d — `need_fit_score` is dual, weighted 0.15 (±7.5 %) | **CONFIRMED** |
| 3e — `trade.presentment_rules` is live | **CONFIRMED** |
| 3f — untargeted discovery only | **CONFIRMED** (code). Quantification: **CANNOT DETERMINE exactly** — targetedness is not persisted anywhere. Bounded estimate ≈ **73–80 %** of prod generations are untargeted |
| 4a — user board shrunk by `w = n/(n+4)` | **CONFIRMED** |
| 4b — `placement_tier_clamp` defaults to 1.0 and clamps | **CONFIRMED** |
| 4c — v3's `_vo` reads the partner snapshot unshrunk; no opponent confidence passed | **CONFIRMED** |
| 4d — the same pair can get different verdicts depending on who opened the deck | **CONFIRMED, and measured** — 86.9 % of 1-for-1s exist in only one orientation vs 63.2 % under a symmetric-pricing control |
| 4e — `first_1` band 205 Elo → ~2.8× value at k=0.005 | **CONFIRMED** — recomputed exactly 2.787× |
| 4 (framing) — the clamp is part of the bias | **REFUTED** — D-085's clamp **reduces** orientation-dependence (86.9 % with it on, **95.3 % with it off**) |

The reviewer is right about the mechanism and right about the arithmetic. They are wrong about one causal attribution (the clamp) and they overstate R5's shape.

---

## 1. Live knob and flag state

Read from prod `model_config` and from `config/features.json` on `16d277f`.

| Knob | `_DEFAULT_CFG` | prod `model_config` | Effective |
|---|---|---|---|
| `shrink_pseudocount` | 4.0 (`trade_service.py:186`) | 4.0 | **4.0** |
| `placement_tier_clamp` | 1.0 (`trade_service.py:750`) | *absent* | **1.0** (falls through `_c()` at `trade_service.py:810`) |
| `pin_exclude_comparisons` | 1.0 (`ranking_service.py:115`) | 1.0 | **1.0** |
| `pin_tier_bounded` | 1.0 | 1.0 | **1.0** |
| `need_fit_weight` | 0.15 (`trade_service.py:421`) | 0.15 | **0.15** |
| `need_gate_min_value` | 500.0 (`trade_service.py:657`) | 500.0 | **500.0** |
| `need_gate_upgrade_margin` | 0.0 (`trade_service.py:658`) | 0.0 | **0.0** |
| `elo_value_k` | 0.0050 (`trade_service.py:140`) | 0.005 | **0.005** |
| `range_base` | 0.35 | 0.35 | **0.35** |

Flags (`config/features.json`): `trade.presentment_rules: true` (line 67), `trade_engine.v2: true` (27), `trade_engine.v3: true` (34), `trade.need_fit: true` (37), `trade.finder_targeting: true` (36). No prod `experiments` row overrides any of them (checked `experiments.variants_json`; the five live experiments touch onboarding, trades_home_inline and aggregate_tier_labels only).

Note for anyone re-reading D-085: it says the clamp was *"Committed to `feat/placement-tier-clamp`, not pushed and not merged."* That sentence is now stale — the branch is merged, `placement_tier_clamp` is in `_DEFAULT_CFG` on `origin/main` at 1.0, and `backend/tests/test_placement_tier_clamp.py` ships with it. Not a defect; just a decision record that outran itself by a few hours.

---

## 2. Claim 3 — "R5 need gate is a hard user-receive filter"

### 2a. Judged on the primary received asset only — **CONFIRMED**

`backend/trade_service.py:1735-1798`, `need_gate_ok`. Lines 1764-1772 walk `recv_ids`, skip `is_pick_asset`, and keep the single highest `seed_value(pid)`:

```python
for pid in recv_ids:
    p = players.get(pid)
    if p is None or is_pick_asset(p):
        continue
    v = seed_value(pid)
    if v > primary_val:
        primary_val = v
        primary_pos = getattr(p, "position", None)
```

Nothing else on the receive side is consulted. The docstring says so in as many words (`:1742-1745`), and defers secondary pieces to #141.

### 2b. The kill matrix — **PARTIALLY CONFIRMED**

The quoted two lines are verbatim correct (`:1794-1797`):

```python
if outlook in ("championship", "contender"):
    return False
if outlook == "not_sure":
    return primary_pos not in (position_surplus or ())
return True
```

But the reviewer's ellipsis hides four PASS branches that must all fail before the matrix is ever reached, and one board caveat:

1. `floor <= 0` ⇒ gate off entirely (`:1759-1761`).
2. `outlook in ("rebuilder", "jets")` or unresolved ⇒ **fail-open** (`:1762-1763`).
3. `primary_pos not in _PRESENTMENT_POSITIONS` ⇒ exempt — pick-primary and exotic positions (`:1773-1774`).
4. `primary_val < need_gate_min_value` (500) ⇒ sub-floor churn, exempt (`:1775-1776`).
5. Post-give body count at P below starter slots ⇒ **fills a starting hole**, exempt (`:1786-1789`).
6. `primary_val > incumbent × (1 + margin)` ⇒ **strict starter upgrade**, exempt (`:1791-1792`). With `need_gate_upgrade_margin = 0.0` this is a bare `>`.

And the values are **consensus** (`seed_value`, threaded as `_vs` from `server.py:5177` / `trade_service.py:4046`), not the user's board — the docstring flags the user-board variant as a named follow-up (`:1746-1747`).

So "hard user-receive filter" is right in kind but wrong in reach: R5 only bites a receive that is (a) a QB/RB/WR/TE, (b) worth ≥ 500 consensus, (c) not filling a starting hole, and (d) not a strict upgrade on the incumbent starter — i.e. genuinely lateral or worse at a position the user already staffs.

**A second correction the reviewer would want.** R5 runs at *construction* time inside each generator (R-6, `trade_service.py:4140-4147`), so a killed candidate refills from the enumeration. It does not simply shrink the deck. Measured on the six real prod boards (all 30 ordered pairs, live config):

| User | Outlook | Cards, R5 on | Cards, R5 bypassed | R5 candidate kills |
|---|---|---|---|---|
| mattmurf77 | championship | 27 | 20 | 154 |
| Bcork | not_sure | 18 | 18 | 1 |
| gdubs10 | contender | 59 | 47 | 483 |
| jonbonjourvi | contender | 14 | 16 | 77 |
| johnstanfield | rebuilder | 28 | 28 | 0 |
| MangoPatti | championship | 37 | 30 | 1071 |

The rebuilder's zero is the fail-open working exactly as specified. Note that R5-on often yields *more* served cards, not fewer — the gate re-routes the enumeration rather than truncating the deck. The reviewer's worry is still legitimate, but it is "specific lateral deals never surface", not "the deck gets smaller".

### 2c. No partner-need term — **CONFIRMED**

`need_gate_ok`'s full signature (`:1735-1737`) is `give_ids, recv_ids, seed_value, players, user_pos_values, outlook, position_needs, position_surplus, scoring_format`. There is no `opp_profile`, no opponent roster, no opponent outlook. At the call site (`trade_service.py:4140-4146`) `outlook` is the **user's** resolved window, `_r5_needs` / `_r5_surplus` come from `user_profile` (`server.py:5290-5291` → `trade_service.py:4116-4117`), and `_user_pos_values` is built from `user_roster` (`:4118-4127`). The reviewer is exactly right.

**The counterexample is real, and I found live instances of it.** Across all 30 ordered pairs of the six boarded members of league `1312140920132497408`, R5 killed 1,778 distinct candidate shapes. Scoring each by the engine's own dual `need_fit_score`:

| dual `need_fit` ≥ | killed shapes | share |
|---|---|---|
| 0.60 | 265 | 14.9 % |
| 0.70 | 70 | 3.9 % |
| 0.75 | 61 | 3.4 % |
| 0.80 | 3 | 0.2 % |

The top three (fit = 0.875) are the reviewer's scenario verbatim: **MangoPatti (championship) sending a surplus RB — Jordan Mason / Kenny Gainwell / J.K. Dobbins — to johnstanfield, whose `position_needs` is `['RB']`, killed by R5 because the QB coming back is lateral on MangoPatti's own depth chart.** Sixty-one such shapes are killed league-wide. R5 is genuinely blind to the half of the trade that makes it landable.

### 2d. `need_fit_score` is dual but only ±7.5 % — **CONFIRMED**

`trade_service.py:1925-1973`. Both profiles are read: give-side terms are `0.5·strength(user, P) + 0.5·(1 − strength(opp, P))`, receive-side terms the mirror (`:1958-1970`). It is applied at `:4287-4295` as `composite *= 1 + w·(nf − 0.5)` with `w = need_fit_weight = 0.15`, i.e. a multiplier in **[0.9250, 1.0750]**, ±7.5 %. Verified numerically. The comment at `:4283-4285` states outright that it is applied **after all gates** and "reorders acceptable trades, never rescues gated ones". So the only dual-need signal in the engine cannot undo the unilateral gate — the reviewer's structural point stands.

### 2e. Flag live — **CONFIRMED**

`config/features.json:67` → `"trade.presentment_rules": true`; registered `backend/feature_flags.py:799`; consumed `backend/server.py:5205` and `:5734`. No experiment override in prod.

### 2f. Untargeted discovery only — **CONFIRMED (code); quantification CANNOT DETERMINE exactly**

The bypass is `backend/server.py:5039-5057`, `_presentment_need_gate_bypass`:

```python
return bool(pinned_give or pinned_receive or opponent_user_id
            or acquire_positions)
```

Derived server-side at `:5202`, threaded to `generate_trades` at `:5369`, and consulted only for R5 (`trade_service.py:4114`, `_r5_active = not bypass_need_gate`). R1/R2/R3/R4 apply to targeted jobs too.

**Quantification.** Targetedness is recorded nowhere: `deck_impressions` has no such column, and the `trades_generated` event's props are `{count, gen_ms, engine_version, lanes[, deck_source]}` (`server.py:5856-5862`). So an exact number is not available from prod — that is itself a finding worth logging.

What *is* measurable is the `acquire_positions` arm, because it is a **persisted league preference** (`league_preferences.acquire_positions`), not a per-request field. Joining all 410 `trades_generated` events to that table, comparing `occurred_at` against the pref's `updated_at`:

- **329 / 410 (80.2 %)** of generations happened while the user had **no** saved acquire-positions for that league — R5 was live for them unless the request also carried a pin or an opponent scope.
- Of those 329, **321 (97.6 %)** sat in a hard-kill window (198 championship + 123 contender) and only 8 in the rebuilder fail-open.
- The remaining 81 (19.8 %) were permanently R5-exempt by a saved pref.

The pin/opponent arms are unrecorded. The only proxy is `find_trades_tapped.props.mode`, where `single_pin` is 14 of 195 taps (7.2 %; the rest are `deck` = 95 and legacy `None` = 86). Netting that against the 80.2 % gives a working band of **≈73–80 % of prod trade generations running with R5 active**, and essentially all of that traffic in the championship/contender kill lane. Treat the band, not either endpoint, as the answer.

---

## 3. Claim 4 — "User Elo is shrunk + clamped; partner Elo is raw"

### 3a. `w = n/(n+4)` on the user's board — **CONFIRMED**

`backend/trade_service.py:1231-1277`, `_shrink_user_elo`. Body at `:1265-1276`:

```python
n0 = _c("shrink_pseudocount")                                     # 4.0
bands = placements if (placements and _c("placement_tier_clamp") > 0) else None
for pid, elo in user_elo.items():
    n = max(confidence.get(pid, 0), 0)
    w = n / (n + n0)
    blended = w * elo + (1.0 - w) * seed_elo.get(pid, 1500.0)
```

Called once per job at `trade_service.py:4022-4024`; `confidence` comes from `service.comparison_counts()` (`server.py:5276` → `ranking_service.py:1122`), `placements` from `service.placement_bands()` (`server.py:5283` → `ranking_service.py:610`). Both are the **requesting user's** and only the requesting user's.

### 3b. `placement_tier_clamp` defaults to 1.0 and clamps — **CONFIRMED**

Default at `trade_service.py:750`; absent from prod `model_config`, so `_c()` (`:810`) returns the default. The clamp itself is `:1269-1273`, applied **after** the blend:

```python
if bands is not None:
    band = bands.get(pid)
    if band is not None:
        blended = min(max(blended, band[0]), band[1])
```

**The D-085 Adams case reproduces exactly.** Replaying the operator's real board out of prod (625-player pool, all 1,718 stored `swipe_decisions`, 737 pins):

| | value |
|---|---|
| distinct comparison opponents in `swipe_decisions` | **36** |
| `comparison_counts()` (what `w` sees) | **1** |
| by decision_type | 2 rank rows (2 opponents), 77 trade rows (34 opponents) |
| pinned Elo | 1365.0 (`third`.max) |
| consensus seed (2026-08-19) | 1526.0 (`second`) |
| `w` | 1/(1+4) = **0.20** → 80 % consensus |
| blend before the clamp | **1493.8** |
| after the clamp | **1365.0** |

Two mechanisms, not one, both undercounting `w`: `pin_exclude_comparisons` (F1) discards the votes the band edge swallowed, and — separately, and larger here — `decision_type='trade'` rows have never entered `comparison_counts` at all (D-076's own "Correction to the audit"). 34 of the 36 opponents are trade-signal opponents. So the reviewer's mechanism is corroborated from a third angle: `w` is not merely noisy, it is systematically far below the amount of evidence the user actually supplied.

### 3c. v3's `_vo` reads the partner snapshot unshrunk, no opponent confidence — **CONFIRMED**

`backend/trade_optimizer.py:251`:

```python
opp_elo    = opponent.elo_ratings
```

and `:292-306`:

```python
def _vo(pid: str) -> float:
    v = _vo_cache.get(pid)
    if v is None:
        v = elo_to_value(opp_elo.get(pid, 1500.0))
```

No `_shrink_user_elo`, no `confidence`, no `placements`. Identical in v2 at `trade_service.py:4462` and `:4499-4514`, and in the consensus generator at `:5110`. `LeagueMember` (`trade_service.py:2822-2830`) carries `elo_ratings` and `has_rankings` and nothing else — there is no field for an opponent confidence map, so none can be passed. The values arrive from `database.load_member_rankings` (`database.py:7522-7583`), which returns `{user_id: {username, elo_ratings}}` straight off `member_rankings.elo` and is assigned verbatim at `server.py:5166-5168`.

Two consequences worth stating explicitly, both structural:

- **Asymmetric damping.** `_value_uncertainty` (`trade_service.py:1281-1295`) and the C5 `mismatch_confidence_damp` also read the user's `confidence` and nothing else. Every confidence-aware mechanism in the engine is one-sided by construction.
- **Asymmetric gating.** `user_gain_ok_1for1` (`:1486-1510`) is a receive-must-beat-give ordering gate on `raw_user_elo`, and `raw_user_elo = user_elo` — the *unshrunk* board (`:4190`, `:4224`, `:4250`). There is no counterpart gate on the partner's ordering. The reviewer's "you are double-protected; their 'yes' is cheaper to manufacture" is a fair reading of the code.

D-081 already documents the display-side half of this: the confidence band "cannot distinguish *how much* either board holds (only whether it is real)". The engine has the same blind spot one layer down.

**Measured cost of the partner-side blind spot.** Across all 30 ordered pairs, 159 cards were generated; 93 of them carry a positive partner-side surplus in raw value space. Recomputing that surplus with the partner's board shrunk *the same way the user's is* (their real `comparison_counts` and `placement_bands`), **22 of 93 (23.7 %)** lose their partner-side surplus entirely. Examples: `mattmurf77 gives De'Von Achane → gets Malik Nabers` (partner surplus +56 → −366), `Bcork gives Jayden Daniels + Jayden Higgins → gets Tyler Warren` (+960 → −33). Caveat, stated so it is not over-read: this is a **raw-value** counterfactual, while the live gate runs on marginal (over-replacement) values under `trade.marginal_value`, so the figure is indicative of magnitude, not an exact re-run of the gate.

### 3d. Different verdicts depending on who opened the deck — **CONFIRMED, and measured**

**Method.** Six boarded members of league `1312140920132497408` (`mattmurf77`, `Bcork`, `gdubs10`, `jonbonjourvi`, `johnstanfield`, `MangoPatti`) were rebuilt from read-only prod: 625-player pool and consensus seed from `player_value_history` (2026-08-19, `1qb_ppr`), every `swipe_decisions` row replayed through the **real** `RankingService.replay_from_db`, `_elo_overrides` restored from `users.tier_overrides`, then `comparison_counts()` and `placement_bands()` taken off those services. Prod `model_config` was loaded into both modules' `_cfg`. Cards were generated by the **real** `TradeService._generate_trades_impl` under the live flags. To isolate the mechanism, the partner's board is the same replayed raw board in both orientations (so the only thing that changes when the roles swap is which side gets `confidence` + `placements`). R5 was bypassed in the sweep so the need gate is not the story.

**Test.** For each unordered pair, take the 1-for-1s produced when A opens the deck, mirror the 1-for-1s produced when B opens (their `give` is A's `receive`), and compare the sets.

| Configuration | union of 1-for-1s | appear in **both** orientations | appear in **one only** |
|---|---|---|---|
| **Live** (user shrunk + clamped, partner raw) | 61 | 8 | **53 (86.9 %)** |
| Live, outlook held equal for both sides | 60 | 8 | 52 (86.7 %) |
| **Control** — both sides priced raw (`confidence=None`) | 38 | 14 | 24 (63.2 %) |
| Control, outlook held equal | 38 | 14 | 24 (63.2 %) |

Reading:

- Orientation-dependence is **real and large**. Only 8 of 61 one-for-ones survive the mirror.
- It is **not** an artifact of the users' different outlooks — holding outlook constant moves nothing (86.9 → 86.7 %).
- A meaningful floor is structural and legitimate (63.2 % under symmetric pricing): rosters differ, so replacement levels, marginal values and lineup feasibility differ, and #108 is a deliberately one-sided gate.
- The asymmetric pricing is what takes it from 63 % to 87 %, and — the sharper number — it **manufactures** candidates: the union grows 38 → 61 while mutual agreement *falls* 14 → 8. Six deals both boards would have produced in either direction stop being mutual, and 23 new one-directional deals appear that exist only because one board is being pulled toward consensus and the other is not.

Concrete instances (mattmurf77 ↔ gdubs10, R5 bypassed): `mattmurf77 gives Ashton Jeanty → gets Malik Nabers` and `mattmurf77 gives Davante Adams → gets Dak Prescott` are produced when mattmurf77 opens the deck and are absent when gdubs10 opens it. The per-asset pricing that drives the first one:

| Asset | Owner | n | raw Elo | priced as USER | priced as PARTNER | value as USER | value as PARTNER |
|---|---|---|---|---|---|---|---|
| Ashton Jeanty | mattmurf77 | 11 | 1833.7 | 1851.5 | 1833.7 | 5796.8 | 5304.2 |
| Malik Nabers | gdubs10 | 4 | 1902.8 | 1889.1 | 1902.8 | 6997.1 | 7493.2 |

Same two assets, same two managers: Jeanty is worth 9.3 % more and Nabers 6.6 % less when mattmurf77 is the one holding the phone.

### 3e. The `first_1` band arithmetic — **CONFIRMED, recomputed**

`elo_to_value` is `backend/trade_service.py:1067-1082`:

```python
return _c("elo_value_base") * math.exp(_c("elo_value_k") * (elo - _c("elo_value_ref")))
```

with `base = 1000`, `ref = 1500`, `k = 0.0050` (`:140-142`; prod `model_config` agrees). `first_1` is `[1580, 1785]` in every one of the eight `(format, position)` blocks of `backend/tier_config.json` — width **205**. `exp(0.005 × 205) = ` **2.787×**. The reviewer's "~2.8×" is exact.

Full ladder, recomputed live:

| Tier | Band | Width (Elo) | Value ratio hi/lo | Value range |
|---|---|---|---|---|
| firsts_4plus | 1927–1972 | 45 | 1.25× | 8457–10591 |
| firsts_3 | 1869–1922 | 53 | 1.30× | 6328–8248 |
| firsts_2 | 1788–1864 | 76 | 1.46× | 4221–6172 |
| **first_1** | **1580–1785** | **205** | **2.79×** | **1492–4158** |
| **second** | **1370–1575** | **205** | **2.79×** | **522–1455** |
| third | 1280–1365 | 85 | 1.53× | 333–509 |
| fourth | 1220–1275 | 55 | 1.32× | 247–325 |
| waivers | 1150–1215 | 65 | 1.38× | 174–241 |

Two bands are 205 Elo wide and the other six are 45–85. `first_1` and `second` are where the great majority of tradeable assets live, so the pin-imprecision the reviewer names is concentrated exactly where it matters most. That is a genuine finding and is not, as far as I can tell, recorded anywhere.

But the inference the reviewer draws from it — "same-tier pins make this worse" — is **misdirected**. A 205-Elo band is the width of the room the clamp *leaves*, not a value the clamp *imposes*: consensus still positions the player inside it, and D-085 says so explicitly in its rejection of a placement-aware `_value_uncertainty` ("a placement bounds *where* the point estimate sits, it asserts nothing about precision *inside* a band 45–205 Elo wide"). The band width is an argument for splitting `first_1` and `second`, not against the clamp.

### 3f. The clamp is part of the bias — **REFUTED**

The reviewer's opening sentence bundles the clamp into the bias: *"`_shrink_user_elo` pulls your board toward DynastyProcess by `w = n/(n+4)`, **then** `placement_tier_clamp = 1.0` clamps placed players into their tier."* The word "then" implies the clamp compounds the shrink. It does the opposite. Re-running the mirror sweep with the knob toggled and everything else identical:

| `placement_tier_clamp` | union | both orientations | one only |
|---|---|---|---|
| **1.0** (live) | 61 | **8** | 53 (86.9 %) |
| **0.0** (pre-D-085) | 64 | **3** | 61 (**95.3 %**) |

Turning the clamp **off** makes the who-opened-the-deck problem measurably **worse** — mutual agreement collapses from 8 pairs to 3. That is the expected direction once you look at what the clamp does: it pulls a placed player's price back toward the user's own assertion and away from the consensus seed, which is precisely the pull that creates the asymmetry with the raw partner board. D-085 is a partial mitigation of the reviewer's own claim-4, not an aggravator. Anyone acting on this review should not "revert the clamp" — that is the wrong lever and it moves the wrong way.

---

## 4. What strengthens the reviewer's case

- The asymmetry is **structural, not tunable**: `LeagueMember` has no field for opponent confidence (`trade_service.py:2822-2830`) and `load_member_rankings` returns none (`database.py:7522-7583`). No knob closes this; it needs a schema and a plumbing change.
- **Every** confidence-aware mechanism is one-sided — `_shrink_user_elo`, `_value_uncertainty`, `mismatch_confidence_damp`, and `user_gain_ok_1for1` on the raw board. Four mechanisms, all pointed at the user.
- `w` undercounts evidence far more badly than "he was barely compared" suggests: the operator's Adams has 36 distinct comparison opponents and `n = 1`, because trade-signal comparisons have never counted and F1 discards band-edge residue.
- 23.7 % of served cards with positive partner-side raw surplus would have none if the partner's board were damped the same way as the user's.
- R5 really does kill deals that fill the partner's hole — 61 measured instances in a single six-board league.

## 5. What weakens it

- **The clamp is a mitigation, not an aggravator** (§3f). Measured, and the direction is unambiguous.
- **Orientation-dependence has a large legitimate floor.** 63.2 % of the union is one-directional even with perfectly symmetric pricing, because rosters, replacement levels and the deliberately one-sided #108 gate differ by side. The asymmetric pricing is an increment on top of that, not the whole effect. Any headline number that attributes all 86.9 % to the shrink is overstated.
- **R5 is narrower than "hard filter" implies** — six PASS exemptions gate it, and it re-routes the enumeration rather than shrinking the deck (some users see *more* cards with it on).
- **`need_fit_weight = 0.15` is a deliberate, documented calibration**, not an oversight — the 2026-07-17 operator interview cut it from 0.30 precisely because need counting "should stay a LIGHT multiplier" (`trade_service.py:419-421`, `database.py:2866-2872`).
- The `first_1` 2.8× arithmetic is correct but argues for narrower mid-ladder bands, not against the clamp.

## 6. Gaps this audit found in passing (not claims, not fixed here)

1. **Targetedness is not persisted anywhere.** Neither `deck_impressions` nor the `trades_generated` event records whether a job was pinned / opponent-scoped / acquire-targeted, so the R5 exposure rate cannot be measured directly. One boolean on the impression row or one prop on the event would close it.
2. **D-085's status line is stale** — it says "not pushed and not merged"; the clamp is on `origin/main` at `16d277f`.
3. **`first_1` and `second` are 205 Elo wide against 45–85 for every other tier**, i.e. ~2.8× value spread inside one pin, concentrated where most tradeable assets sit.
4. **`decision_type='trade'` comparisons still never reach `comparison_counts`** (D-076 notes this as a correction; it remains the dominant reason `w` is small for heavily-traded players — 34 of Adams's 36 opponents).

---

## 7. Reproduction

Read-only prod (`DATABASE_URL_PROD`, `SET TRANSACTION READ ONLY`, SELECT only; the DSN was never printed). Probe scripts were kept in the auditing session's scratchpad and are deliberately not committed — they hold a prod connection helper. The replay is reconstructible from this recipe:

1. Pool + seed: `player_value_history` where `snapshot_date='2026-08-19' and scoring_format='1qb_ppr'` (625 rows), joined to `players` for `Player` fields.
2. Per user: `swipe_decisions` → `RankingService.replay_from_db`; `users.tier_overrides['1qb_ppr']` → `svc._elo_overrides`; then `get_rankings()`, `comparison_counts()`, `placement_bands()`.
3. Rosters: `league_members.roster_data` for league `1312140920132497408`. Outlooks: `league_preferences.team_outlook`.
4. Prod `model_config` loaded into `ranking_service._cfg` and `trade_service._cfg`.
5. Cards: `TradeService._generate_trades_impl(...)` under `stud_tax_override("market")`, `fairness_threshold=0.5`, `max_per_opponent=500`, live `config/features.json`.

Replay fidelity check: for the four heavily-boarded members, the replayed board and the stored `member_rankings` snapshot disagree on 105–127 of 625 players — snapshot staleness, not a different computation. The sweeps above use the replayed board on both sides so that staleness cannot confound the orientation test. (That staleness is itself a second, smaller asymmetry: what a partner reads about you is a snapshot, what you read about yourself is live.)
