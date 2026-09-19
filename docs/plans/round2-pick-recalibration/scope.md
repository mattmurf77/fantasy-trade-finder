# Feature Scope — Round-2 draft-pick recalibration (D-084)

**Date:** 2026-08-19
**Entry point:** direct operator ask — *"Make this fix."* — after being told this is a bright-line tier-band change
**Builder:** session `feat/round2-pick-recalibration`
**Operator sign-off on waivers:** the operator directed the change with the bright line stated; §1 is waived on the reasoning below, §3 carries a TestFlight checklist rather than a waiver.

**Source of truth for the measurement:** [docs/reviews/2026-08-19-ktc-pick-value-comparison.md](../../reviews/2026-08-19-ktc-pick-value-comparison.md) (carried on this branch — it is not on `main`).
**Companion:** [docs/reviews/2026-08-19-pick-year-valuation.md](../../reviews/2026-08-19-pick-year-valuation.md) (D-079, the *year* axis).

---

## 0. What changes

Round 2 of `GENERIC_PICK_SEEDS` is deflated toward market. **Rounds 1, 3 and 4 are untouched.**

| Rung | Elo before | Elo after | Value before | Value after | ratio to same-rung 1st |
|---|---|---|---|---|---|
| 2nd Early | 1520 | **1470** | 1105.2 | **860.7** | 0.368 → **0.287** |
| 2nd Mid | 1460 | **1400** | 818.7 | **606.5** | 0.387 → **0.287** |
| 2nd Late | 1400 | **1370** | 606.5 | **522.0** | 0.407 → **0.350** |

Because `tier_config.json`'s `_calibration` defines each tier's floor as a rung of the pick ladder, the Late-2nd move forces two band edges in the **same commit**, across all 8 `(scoring_format, position)` blocks:

| Band edge | Before | After |
|---|---|---|
| `second.min` | 1400 | **1370** |
| `third.max` | 1395 | **1365** |

Ordering still holds: the new Late 2nd (1370) stays above the Early 3rd seed (1360) — margin narrowed from 40 Elo to 10.

**Why not KTC's published ratio.** KTC's raw 2nd:1st is 0.697 against our 0.387, which reads as *"our gap is twice too severe"*. That reading is a scale artifact and the memo disproves it: transplanting 0.697 would price a mid-2nd at 1482 — the **86th**-best dynasty asset, above George Kittle. The scale-free measure is player-rank equivalence, and on it our 1st round is exact while our 2nd is 22 ranks too dear.

| | FTF | KTC '26 | KTC '28 | FantasyCalc | DynastyProcess | market median |
|---|---|---|---|---|---|---|
| Mid 1st | 65 | 64 | 66 | 67 | 77 | 66.5 — **exact, do not touch** |
| Mid 2nd | 119 → **136** | 134 | 137 | 144 | 169 | 140.5 |

---

## 1. Analytics scope

- [x] **(c) WAIVED — no analytics needed because:** this change emits no events and adds no properties. It re-prices an existing asset class; every surface that already reports pick value, tier, or deck composition keeps its identical event shape and property set. The taxonomy (`backend/analytics_taxonomy.py`) and `analytics_queries.NON_INTENT_EVENTS` are **unmodified** — verified by diff.
- **Measurement instead of instrumentation.** The question that mattered ("is the overpriced 2nd costing accepted trades?") was answered from data already collected, read-only against prod — see §6. The answer is *no, not measurably*, and it did not require new events.
- **Comparability caveat worth recording:** any pre/post analysis of deck composition across 2026-08-19 will straddle **both** D-079 (year decay, shipped hours earlier) and D-084. The two confound. Do not attribute a deck shift to either one alone without an arm split, and note that `model_arm` is currently 97.5 % NULL with zero `gen_v2` rows (§6), so an arm split is not presently available.

## 2. Schema & flag scope

- **New/changed tables or columns:** none. `docs/data-dictionary.md` **not** updated — nothing stored changes shape. Existing stored values are unaffected on read: `users.tier_overrides` stores raw Elo per player, so saved boards re-bucket through the new walk with no migration (already stated in `docs/cross-client-invariants.md`).
  - One stored-value note: `draft_picks.pool_value` is written by `sync_draft_picks` at sync time. Rows synced **before** this deploy keep the old round-2 price until their next sync. This is pre-existing behaviour for every pricing change, not new, and it self-heals on the next sync tick.
- **New/changed feature flags:** none. `config/features.json` and `backend/feature_flags.py` `FLAG_KEYS` are unmodified.
- **New env vars / `model_config` keys:** **none — and that is a deliberate decision, not an omission.** See §7 for the knob argument and the revert path that replaces it.

## 3. Evidence scope

- [x] **Structural guard:** no new `check-*.js` written. The mechanically-checkable content of this change is *numeric*, and it is already pinned harder in pytest than a structural script could manage — `test_pick_pricing_m6b.py::SHIPPED_SEEDS` spells the whole 12-rung ladder as a literal tripwire, and `test_tier_occupancy.py` pins every band's occupancy against a checked-in snapshot. Four existing mobile suites that touch this surface were run and pass: `test:calc-pick-tiers`, `test:anchor-labels`, `test:picks-subset-invariance`, `test:contrast`.
- [x] **Unit tests:** eleven pre-existing pins retargeted, plus two deliberate strengthenings. Full list in §5.
- [x] **Code-walk proof:** §4 below.
- [x] **Manual TestFlight checklist:** §8 below. Required — tier colours on a real board are exactly the case D-056 says needs runtime eyes, and this change repaints them for real users.
- **`testID`s added/renamed:** none. `mobile/scripts/testid-lint.sh` → `testid-lint OK`.

## 4. Code-walk proof — how three numbers reach five clients

Every hop cited by file:line at this branch's tip.

**A. The seeds → the priced pool (backend).**
1. `backend/pick_values.py:24` — `GENERIC_PICK_SEEDS`, the three round-2 rungs edited.
2. `backend/server.py:1472` — `for (rnd, tier), seed_elo in GENERIC_PICK_SEEDS.items():` injects the 12 generic pick pseudo-players into the universal pool at those Elos. This is what makes a generic "Mid 2nd" rankable and comparable against players.
3. `backend/pick_values.py:242` — `pick_pool_value(round_, years_out, ...)` = `elo_to_value(GENERIC_PICK_SEEDS[(round_,"Mid")]) × year_decay(round_)**years_out`. This is the **owned** pick price on `GET /api/league/picks`, the calculator, and the suggestion pool. A 2026 owned 2nd therefore falls 818.7 → 606.5.
4. `backend/server.py:1347` — `_anchor_target_elo` returns `GENERIC_PICK_SEEDS[...]` for single-pick anchors, so the Pick Anchor wizard's "worth a 2nd" answer now pins a player at Elo **1400**, not 1460.

**B. The bands → the tier walk (backend).**
5. `backend/ranking_service.py:30,32,39` — `_TIER_CONFIG_PATH` → `_load_tier_config()` → `TIER_CONFIG`, evaluated **at module import**, i.e. once per process. This is why a band change needs a restart and cannot be knob-reverted (§7).
6. `backend/ranking_service.py:1673` `tier_bands_for(...)` → `1692` `tier_for_elo(...)` — the top-down walk assigning the first tier whose `min <= elo`. Only `min` gates the walk; `third.max` moved for coherence and is consumed by `apply_tiers`' Elo writes and the `pin_tier_bounded` clamp.
7. `backend/server.py:7252` — `get_tier_config()` serves `TIER_CONFIG` verbatim at `GET /api/tier-config`. **No route contract changed**: same path, same shape, same keys — only three integers inside the payload differ. This is why `docs/api-reference.md` needs no edit (§5 table).

**C. The bands → the clients.**
8. **Mobile** (`mobile/src/utils/tierBands.ts`): `thresholdsFor` at `:95` prefers the cached `/api/tier-config` response (`:99` `lb('second')`) and returns `FALLBACK` at `:115` only pre-network. `tierForElo` at `:119` walks it. So mobile picks the new bands up **at next app launch with no client release** — the edited `FALLBACK.second` at `:73` matters only for the first-launch/offline window. This is also the revert story: reverting the backend restores mobile without a TestFlight build.
9. **Web tiers page** (`web/positional-tiers.html:1649`): `TIER_CONFIG` is a pre-fetch default overwritten by the live fetch — same story as mobile.
10. **Web rankings table** (`web/js/app.js:2108`): `_eloToTierLabel` is a **pure hardcode that never fetches** `/api/tier-config`. It is the one mirror that would have drifted silently and stayed drifted. Edited, and a comment added at the function head recording that it must be hand-edited whenever the floors move.
11. **Extension**: consumes the backend walk — verified no hardcoded band numbers exist (`git grep -nE "1927|1869|1788|1580|1280|1220|1150" -- extension` → no matches). Nothing to change.
12. **Offline replay tool** (`backend/scripts/replay_trade_decisions.py:94`): carries its own duplicate seed map for historical replay. Updated so replays price like production.

**D. What the walk does to a real board.** The one badge that flips is traced in `backend/tests/test_league_picks_tier.py`'s header note: a **current-year 3rd** prices at Elo 1383.5 through `seed_elo_for_value`, which sat 16.5 below the old floor and sits 13.5 above the new one — so a 2026 3rd now badges **"2nd"**. All four round-2 rungs still badge `second`; 2027+ 3rds and every 4th still badge `third`. This is the pre-existing round-3 overprice becoming visible, not a banding defect — see §9.

## 5. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | **n/a** | No route added, renamed, removed, or contract-changed. `GET /api/tier-config` serves the same schema with different integers inside it; `GET /api/league/picks` serves the same fields with different prices. No documented contract states the band values. |
| `living-memory/LLD.md` | **n/a** | No schema, route, or convention *shape* shifted. The seeds-and-bands coupling this change honours is an existing documented convention (`tier_config.json` `_calibration`), not a new one. |
| `docs/architecture.md` | **n/a** | No module wiring or data-flow change — the same functions call the same functions with different constants. |
| `living-memory/HLD.md` | **n/a** | No new module, client, or major flow. |
| `docs/cross-client-invariants.md` | **updated** | **Governing doc.** Tier-band table rows for `second` and `third`; the "Banding rule" prose; the `1_second` row of the Pick anchor keys table (Mid 2nd seed 1460 → 1400); and a new "Round-2 amendment (D-084)" paragraph stating the rationale, the inseparability of the seed/band pair, the occupancy effect, and the no-knob revert path. |
| `docs/config-reference.md` | **n/a** | No env var or `model_config` key added — see §7. |
| `docs/data-dictionary.md` | **n/a** | Nothing stored changes shape (§2). |
| `docs/glossary.md` | **n/a** | No new domain term. |
| `backend/tier_config.json` `_calibration` prose | **updated** | Corrected `second floor = Late 2nd 1400` → `1370`, noted `third`'s max move, and appended a dated D-084 amendment. Would otherwise have become false. |
| `DECISIONS.md` entry | **updated** | **D-084** (id reserved by the operator; not computed as max+1, because three id collisions had to be untangled by hand tonight). |
| `OPEN_QUESTIONS.md` | **updated** | **Q-019** — rounds 3/4 are not fixable via seeds; the seed map is the thing to open. |
| `GOTCHAS.md` | **updated** | The seed/band coupling, and the `web/js/app.js` mirror that fetches nothing. |
| `TEST_LEDGER.md` | **updated** | §5 results below. |
| `CHANGELOG.md` | **updated** | Dated entry. |

### Tests retargeted — the eleven, plus two strengthenings

Baseline on `93ac695`: **3429 passed, 1 skipped**. After the seed+band edit, before retargeting: **11 failed / 3418 passed** — *exactly* the eleven the memo predicted, no more and no fewer. Nothing outside the predicted blast radius moved.

| # | Test | Was | Now |
|---|---|---|---|
| 1 | `test_pick_anchor::test_single_pick_anchors_pin_to_generic_pick_seeds` | `_anchor_target_elo("1_second") == 1460` | `== 1400` |
| 2 | `test_pick_anchor::test_anchor_value_and_tier_are_position_uniform` | `rb["elo"] == qb["elo"] == 1460` | `== 1400` |
| 3–6 | `test_pin_tier_bounded` ×4 | `SECOND_LO = 1400.0` | `= 1370.0` (one constant; fixed all four) |
| 7–8 | `test_pick_pricing_m6b::…byte_unchanged_in_every_mode[tier_ladder, market_slots]` | `SHIPPED_SEEDS` round 2 = 1520/1460/1400 | 1470/1400/1370, with a comment declaring the repricing intentional |
| 9 | **`test_pick_pricing_m6b::test_the_measured_reshaping_direction_is_deflation_not_inflation`** | `delta(2026,2) < -0.40` | **the honest scorecard — see below** |
| 10 | `test_league_picks_tier::test_pick_rows_carry_literal_tier_rungs` | 2026 3rd → `third` | → `second`, with the header note in §4D; **plus a new 2027-3rd row pinned to `third`** so the band is provably still reachable |
| 11 | `test_power_rankings::test_picks_value_label_literal_count` | the dollar-space sabotage trap | **re-sharpened — see below** |
| + | `test_tier_occupancy::test_anchor_rungs_land_in_matching_tiers` | `1460.0 → "second"` (passed, but asserted a seed that no longer exists) | `1400.0 → "second"` — retargeted so it keeps meaning what it says |
| + | `backend/tests/fixtures/pin_tier_bounded_golden.json` | captured with `edge_lo` pinned at 1400 | **re-captured against pristine `origin/main`** — see below |

**#9, the honest scorecard.** `delta(2026, 2)` measures how far our ladder sits above DynastyProcess's real market slot prices. It was `< -0.40` (our 2nds >40 % above market) and is now **−0.284**; `delta(2027, 2)` is **−0.244**. Rewritten to pin those values with `pytest.approx` rather than a loose bound, so drift in *either* direction must be acknowledged, and given a long docstring recording that **the remaining ~28 % gap is intentional**: Option B (full market alignment) was measured in the memo and rejected because it breaks `test_tier_occupancy.py` in three places and buckets the Mid 3rd seed as `second`; DP is also the most convex and most near-zero-anchored of the four sources, so convergence on it was never the goal. The docstring also records that **the ranking flipped** — 2nds are no longer the biggest outlier (a 2026 3rd now deflates hardest, −0.355 vs −0.284), which is precisely the round-3 residue logged as Q-019.

**#11, re-sharpening the trap.** This test proves the power-rankings pick label comes from the literal pick count (#285: 1st = 1.0, 2nd = 1/3.5, 3rd+ = 0), *not* from converting the dollar-priced `picks.value`. Its teeth came from the two answers disagreeing. They stopped disagreeing — because the new 2nd:1st ratio of **0.287** lands within 0.001 of the literal weight **1/3.5 = 0.286**. That is a genuine corroboration of the recalibration (an independently-authored heuristic now agrees with the engine to three decimals) but it defused the trap, so a 3rd was added to the fixture: the literal scale prices a 3rd at exactly 0 and the dollar scale at 406.6, restoring divergence. Documented in the fixture.

**The golden fixture, re-captured the honest way.** `pin_tier_bounded_golden.json` pins `edge_lo` to the `second` floor, so the floor move changed the fixture's *input* and the old recording could not stand. Its docstring warns against regenerating from new code, so it was not: a **pristine `origin/main` worktree at 93ac695** was created, and the capture harness was first validated by re-capturing at 1400 and confirming it reproduced the checked-in golden **byte-for-byte**, then re-run at 1370. Seven numbers moved, all mechanically forced by the single changed input: `elo.edge_lo` (he is frozen on his pin), plus small ripples in `free` (his opponent in six comparisons) and `quiet` (shares the pool). The rationale is recorded in the test docstring.

## 6. Production validation — read-only

Run against prod Postgres with `SET TRANSACTION READ ONLY`, SELECT only, connection string read programmatically from the gitignored `secrets.local.env` and never printed.

**Question:** is the overpriced 2nd actually costing accepted trades? **Answer: no, not measurably — and the data cannot support the claim either way at current volume.**

- **Exposure** (2,184 served cards): has a 2nd **300 (13.7 %)**; has a 1st, no 2nd 946 (43.3 %); no pick at all 925 (42.4 %). Pick mentions split 1,509 firsts / 303 seconds / 13 thirds — corroborating the memo's 279-of-1763 figure.
- **Outcomes**, `trade_decisions`, 60 days, n=886: no pick 35.2 % liked (n=565); **has a 2nd 34.8 % (n=46)**; 1st only 22.4 % (n=272). has-2nd vs no-pick **Fisher p = 1.00**.
- The 3-day impression-level sample (n=252) points the *opposite* way (has-2nd 17.6 %, n=17, p=0.26). **Two samples disagreeing on sign is itself the finding** — this is noise. Detecting a 10-point drop at 80 % power needs ~350 dispositions per group; there are 46.
- **Pass reasons:** cards with a 2nd draw value-reasons at 50 % vs a 53 % baseline. The one faint hint the other way — 5 of 8 passes where the user would have *received* a 2nd cited "giving up too much", the exact signature of an overpriced 2nd — is n=8 and not evidence.
- **Free text is unambiguous and is not about 2nds.** Zero of 23 free-text passes mention a 2nd. Every pricing complaint is about **1sts**: *"I think 2029 1st values are the issue"*, *"1st round picks seem undervalued"*.
- **The real signal is 1sts by side:** 1st on give 15.6 % liked vs 1st on receive 47.1 % (n=128) — a 31-point gap corroborated by pass reasons and free text.

**Consequence for this change:** ship it on the merits (four independent sources agree our 2nd is 22 ranks too dear), but **do not justify it with acceptance data and do not expect a measurable lift.** Recorded plainly here so nobody later mistakes this change for a conversion fix.

Two incidental findings, raised as their own items rather than fixed here (out of scope):
1. **`backend/database.py` on `main` is stale against prod** — prod `deck_impressions` has 26 columns to the repo's 13, and `trade_pass_reasons` exists in prod but not in `database.py` (it shipped from `chore/bakeoff-serve-interleaved`). A live footgun for anyone writing queries or a migration.
2. **`model_arm` is 97.5 % NULL and has never recorded a `gen_v2` impression** — the bake-off is not producing labelled data. This also means the arm split §1 would want is unavailable.

## 7. The knob decision — no knob, deliberately

D-079 shipped `model_config` knobs so it could be walked back without a deploy. **This change does not, and should not.**

1. **A seeds-only knob would desynchronise the exact pair this change exists to keep in step.** The Late rung of a round *is* that round's tier floor (`tier_config.json` `_calibration`). Seeds live in Python; bands live in JSON. A knob that moved the seeds without moving the bands would silently break the ladder's meaning — the precise failure mode the memo flags as making this a bright-line change.
2. **It would buy no revert speed anyway.** `ranking_service.TIER_CONFIG` is evaluated at module import (`backend/ranking_service.py:39`), so the band half needs a process restart regardless. A knob would deliver a *partial*, incoherent revert faster than the coherent one — strictly worse than no knob.
3. **The risk profile is the opposite of D-079's.** D-079's round-1 flat decay was an operator call that ran *against* every public source, which is exactly when a fast walk-back earns its complexity. D-084 moves *toward* four independent sources that agree. There is no live disagreement to hedge.

**Revert path (documented, since there is no knob):** revert the single D-084 commit and redeploy. It is self-contained — three seeds in `backend/pick_values.py`, `second.min`/`third.max` across the 8 blocks of `tier_config.json`, the two client fallback mirrors, `web/js/app.js`'s label ladder, the replay script, and the pinned test targets. Render auto-deploys `main`; **clients re-fetch `/api/tier-config` at boot, so no client release is needed** to pick the old bands back up. Also recorded in the module note at `backend/pick_values.py` and in `docs/cross-client-invariants.md`.

**Bake-off (`trade.bakeoff` ON, arms `current` + `gen_v2`).** `backend/bakeoff_profiles.py`'s knob-inventory guard fires when a key is added to `trade_service._DEFAULT_CFG`. **No key is added here, so the guard is a no-op for this change** — `trade_service.py` is not in the diff. On the substantive question, the precedent set hours ago for the D-079 pick-year keys applies unchanged and is hereby adopted: `docs/plans/three-model-bakeoff/scope-phase2.md:81` excluded them from `MODEL_A_PROFILE` because *"they price an ASSET; they do not decide which package to build out of priced assets"*, and pinning arm A to old prices would confound generation policy with a repricing. Pick **seeds** are the same class — more so, since they are a module constant and not a config key at all, and therefore not even eligible for a profile pin. **Conclusion: the seeds stay live for all arms; the value space is shared ground the arms compete on, not a variable under test.**

## 8. Manual TestFlight checklist (operator)

Runtime evidence for the band repaint. Steps are specific enough to catch a regression; expected results assume the backend has deployed.

| # | Step | Expected |
|---|---|---|
| 1 | Force-quit and relaunch the app (so `/api/tier-config` is re-fetched into the cache). | — |
| 2 | Tiers tab → any position, 1QB PPR. Find the boundary between the **2nd** (sky `#38bdf8`) and **3rd** (pink `#f472b6`) groups. | A few players that previously sat at the top of **3rd** now sit at the bottom of **2nd** — expect **2–5 per position**. No other boundary moves. |
| 3 | Same screen, switch scoring format to SF/TEP. | Same behaviour. Bands are format-uniform — if the two formats disagree, something is wrong. |
| 4 | Count the **2nd** group for WR in SF/TEP. | ≈32, and **never above 35** (the pinned ceiling). |
| 5 | Check the **4+ 1sts / 3 1sts / 2 1sts / 1 1st / 4th / FA** groups against yesterday. | **Unchanged.** Only the 2nd/3rd boundary moved. |
| 6 | Pick Anchor wizard → answer **"2nd"** for any player. | Saves, and the player lands in the **2nd** tier (the tier carrying the answer's name). |
| 7 | Trade calculator → put a generic **Mid 2nd** against a Mid 1st. | The 2nd reads **≈607**, roughly **29 %** of the 1st (was ≈819 / 39 %). |
| 8 | League → draft picks list. Look at a **2027 or later 2nd**. | Priced lower than before; badge still reads **2nd**. |
| 9 | **The known oddity — look for it explicitly.** League → draft picks, find a **current-year (2026) 3rd**. | Badge reads **"2nd"**, not "3rd". **This is expected** (§4D / §9). Report it only if a *2027-or-later* 3rd also reads "2nd", which would be a real defect. |
| 10 | Web (`/positional-tiers.html`) and the rankings table on the web app. | Same boundary as mobile. A mismatch means a client mirror drifted. |

## 9. Known consequence, stated plainly

**A current-year 3rd-round pick now carries a "2nd" badge.** It prices at Elo 1383.5 through `seed_elo_for_value`, which sat 16.5 points below the old `second` floor and sits 13.5 above the new one. All four round-2 rungs still badge `second`; 2027+ 3rds and every 4th still badge `third`.

This is **not** a banding bug. It is the pre-existing round-3 overprice becoming visible: the memo measures a mid-3rd at ~67 ranks too dear and shows the cause is `seed_elo_for_value` compressing ranks 200–300 into 32 Elo points — which **no pick-seed edit can fix**, and which is why D-084 deliberately left rounds 3–4 alone. Logged as **Q-019**; the fix is to open the seed map, which is separate work. It is pinned in `test_league_picks_tier.py` with a header note so it cannot drift unnoticed, and it is step 9 of the TestFlight checklist so the operator sees it on purpose rather than reporting it as a surprise.

## 10. Ship gate declaration

- **CI green:** `pytest backend/tests` → **3429 passed, 1 skipped** (exactly the `93ac695` baseline); `tsc --noEmit` → clean; `mobile/scripts/testid-lint.sh` → `testid-lint OK`. Four relevant `mobile/tests/check-*.js` suites pass.
- **Evidence recorded:** `living-memory/TEST_LEDGER.md`.
- **TestFlight verification:** checklist in §8, **not yet run** — operator action, outcome to be logged in TEST_LEDGER.
- **Express lane declared by the operator?** **No.** Full gates applied. The operator directed the change after being told it is a bright-line tier-band change, which is the confirming yes the bright-line rule requires — it is not an express declaration.
- **Not pushed, not merged.** Committed to `feat/round2-pick-recalibration` only.
