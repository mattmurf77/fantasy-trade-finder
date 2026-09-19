# Build status — M6: slot values, display-only

**Wave:** `wave/m6` · **Date:** 2026-08-06 · **Base:** `origin/main` @ `f14223c`
**Spec:** [plan.md](plan.md) §M6 + the *Operator decisions — 2026-08-06* block · [lld.md](lld.md) §4.7, §2.1, §6.1, §6.2, §7 · [hld.md](hld.md) §2.2, KD-9, I-7
**Flag:** `picks.slot_values` — **added OFF, not flipped.**

---

## 1. What was built

Per-slot draft-pick market prices on the Draft Room board's `order[]` entries, behind a new default-off flag. Nothing else in the app can see them.

| Piece | Where |
|---|---|
| Hermetic seam `FTF_DP_PICK_VALUES_FILE` + the extended startup assertion | `backend/data_loader.py` · `backend/server.py` (~L470, the `_TEST_MODE` block only) |
| DP `values.csv` PICK reader — 24 h in-memory TTL, both formats from one fetch, failure ⇒ `{}` | `backend/data_loader.py::load_pick_slot_values` / `_fetch_pick_values_csv` / `_parse_pick_values` / `pick_slot_label` / `reset_pick_values_cache` |
| `order[].slot_value` (seed-Elo space) + `slot_value_approx`, on BOTH render paths | `backend/draft_board_service.py::_annotate_slot_values` / `_basis_slot`, called once from `_payload` |
| Flag, 4-touch | `backend/feature_flags.py` · `config/features.json` · `backend/tests/fixtures/flags/release.json` · `docs/config-reference.md` |
| Tests (33 new) | `backend/tests/test_slot_values.py` + `backend/tests/fixtures/dp_values_picks_2026-08-06.csv` |
| Docs | `docs/config-reference.md` (flag row + env var) · `docs/cross-client-invariants.md` (new *Draft-pick slot values are DISPLAY ONLY* section) |

**Order of work was the one the LLD mandates: the seam landed before any fetch code.** `values.csv` is a second live DynastyProcess egress; adding a fetch without an override would have punched a hole in exactly the rail `server.py`'s `FTF_TEST_MODE` assertion exists to hold.

### Key design points

- **`slot_value` is in seed-Elo space**, mapped through the shipped `data_loader.seed_elo_for_value`, so it is directly comparable to a player Elo on screen. DP's PICK rows are on the same 0–10000 scale as its player rows, so no new calibration was introduced.
- **Omit-when-absent, everywhere.** Flag off, read failed, `slot: null` (order unset — pricing it would invent an order through the back door, D5), a round DP does not publish (it stops at 5), or a season with no per-slot rows ⇒ the key is simply not written. Never `null`, never `0`.
- **`slot_value_approx: true` appears only when prices actually shipped AND `teams != 12`.** A 12-team board is exact and carries no marker at all (the key is absent, not `false`).
- **Annotation happens once, in `_payload`**, before `my_picks` is sliced — so the Sleeper and MFL renderers cannot drift, and `my_picks` carries the same annotated entries as `order`.
- **The percentile map anchors both ends** (see §4, deviation D-2).

---

## 2. Sanity record for M6b — the slot curve vs the shipped ladder

1QB (`value_1qb`) and Superflex (`value_2qb`) columns of the committed snapshot `backend/tests/fixtures/dp_values_picks_2026-08-06.csv`, taken from DynastyProcess `files/values.csv` on **2026-08-06** (`scrape_date` in the file: 2026-07-31). "Seed Elo" is `round(seed_elo_for_value(v), 1)` — the exact number M6 serves. "Shipped rung" is `pick_values.GENERIC_PICK_SEEDS`, byte-unchanged by this wave.

### 2.1 Current-year per-slot curve

| DP label | DP value_1qb | **seed Elo (1qb)** | DP value_2qb | seed Elo (sf) | nearest shipped rung | rung Elo | Δ (1qb − rung) |
|---|---|---|---|---|---|---|---|
| `2026 Pick 1.01` | 5633 | **1816.5** | 7225 | 1864.3 | Early 1st | 1720 | **+96.5** |
| `2026 Pick 1.06` | 2129 | **1636.5** | 2658 | 1676.3 | Mid 1st | 1650 | −13.5 |
| `2026 Pick 1.12` | 725 | **1460.5** | 882 | 1489.8 | Late 1st | 1580 | **−119.5** |
| `2026 Pick 2.01` | 612 | **1436.4** | 742 | 1463.9 | Early 2nd | 1520 | −83.6 |
| `2026 Pick 2.12` | 112 | **1269.3** | 132 | 1279.5 | Late 2nd | 1400 | −130.7 |
| `2026 Pick 3.01` | 97 | **1261.3** | 115 | 1270.8 | Early 3rd | 1360 | −98.7 |
| `2026 Pick 3.12` | 25 | **1217.7** | 30 | 1221.0 | Late 3rd | 1280 | −62.3 |
| `2026 Pick 4.01` | 22 | **1215.6** | 27 | 1219.0 | Early 4th | 1260 | −44.4 |
| `2026 Pick 5.12` | 5 | **1203.7** | 6 | 1204.4 | Late 4th | 1220 | −16.3 |

### 2.2 Future-year rungs (the direct ladder comparison)

| DP future rung | DP value_1qb | **seed Elo (1qb)** | shipped rung | rung Elo | Δ |
|---|---|---|---|---|---|
| `2027 Early 1st` | 3347 | **1718.6** | Early 1st | 1720 | **−1.4** |
| `2027 Mid 1st` | 1554 | **1581.7** | Mid 1st | 1650 | −68.3 |
| `2027 Late 1st` | 754 | **1466.3** | Late 1st | 1580 | −113.7 |
| `2027 Early 2nd` | 382 | **1376.1** | Early 2nd | 1520 | −143.9 |
| `2027 Mid 2nd` | 202 | **1311.5** | Mid 2nd | 1460 | −148.5 |
| `2027 Late 2nd` | 111 | **1268.7** | Late 2nd | 1400 | −131.3 |
| `2027 Early 3rd` | 63 | **1241.9** | Early 3rd | 1360 | −118.1 |
| `2027 Mid 3rd` | 38 | **1226.3** | Mid 3rd | 1320 | −93.7 |
| `2027 Late 3rd` | 23 | **1216.3** | Late 3rd | 1280 | −63.7 |
| `2027 Early 4th` | 15 | **1210.8** | Early 4th | 1260 | −49.2 |
| `2027 Mid 4th` | 10 | **1207.3** | Mid 4th | 1240 | −32.7 |
| `2027 Late 4th` | 8 | **1205.8** | Late 4th | 1220 | −14.2 |

### 2.3 Two plan claims checked against real data

- **"1.01 ≈ 1817 vs 'Early 1st' 1720" (plan §0.5, hld KD-9) — CONFIRMED.** Measured **1816.5** (1qb). The plan's rounded 1817 is right, and so is the conclusion drawn from it: the current-year top slot sits ~97 Elo above our Early-1st rung.
- **"its future-year rungs corroborate our shipped ladder within ~2 Elo at Early/Late" (plan §0.5) — HALF WRONG; correct it before M6b prices anything.** *Early 1st* corroborates beautifully (−1.4 Elo). *Late 1st does not*: DP prices it at **1466.3** against our **1580**, a **−114** gap, and every rung below Early 1st is 30–150 Elo BELOW ours. The agreement at Early 1st is a single coincidence, not a pattern.

**What this means for M6b, stated plainly:** DP's curve is not merely "steeper at the top" — it is *steeper everywhere*, pivoting near Early 1st. Adopting it wholesale would simultaneously **inflate** the price of a 1.01 by ~1 tier-band and **deflate** essentially every other pick, including all future-year rungs (which is what the trade engine actually prices most often, since owned future picks vastly outnumber current-year slots). The repricing decision is therefore not "do picks get more expensive" — it is a re-shaping of the whole pick curve, and the before/after matrix replay should be read for **deflation of 2nd/3rd-round packages** at least as carefully as for 1.01 inflation. Also note the 1QB/SF split: SF prices every pick higher (1.01: 1864.3 vs 1816.5), so the toggle must be format-aware.

---

## 3. Gates

| Gate | Result | Exit code |
|---|---|---|
| Baseline on `f14223c`: `python3 -m pytest backend/tests -q` | **1692 passed, 1 skipped** | 0 |
| After M6: `python3 -m pytest backend/tests -q` | **1726 passed, 1 skipped** (+34: 33 in `test_slot_values.py`, +1 param case in `test_test_support.py`) | 0 |
| `cd mobile && npx tsc --noEmit` | clean | 0 |

Exit codes were checked explicitly (`echo "EXIT=$?"`), not inferred from tail output.

Tests added, mapped to lld §7:

- **T-M6-01** — `test_m6_01_test_mode_without_pick_values_file_aborts_at_import` (subprocess `import backend.server`; asserts non-zero exit and that the message names the var, then asserts the same env *with* the var imports cleanly). Mirrored as a fifth case in `test_test_support.py::test_startup_aborts`, where the rails live. Plus `test_m6_01b_reader_refuses_live_egress_under_test_mode` for the below-the-rail belt.
- **T-M6-02** — `test_m6_02_flag_off_omits_the_key_entirely`, `..._never_reads_the_source` (patches the fetcher to raise on call), `..._ladder_and_bands_are_byte_unchanged` (compares `GENERIC_PICK_SEEDS` before/after **and** spells out the three 1st-round rungs), and a parametrized `..._do_not_reach_the_valuation_lanes` over `trade_service.py`, `trade_optimizer.py`, `pick_values.py`, `ranking_service.py`.
- **T-M6-03** — `test_m6_03_fetch_failure_renders_without_the_axis`: board renders, no key, and `degraded is None` (a missing axis is not a degraded board).
- Parse correctness against the committed fixture: full rounds-1–5 coverage, monotonicity, the exact `seed_elo_for_value` mapping, future-year rungs, both formats, DP's own column suffixes, player rows excluded, one-read TTL, missing file ⇒ `{}`.
- 12-team exact (every entry priced, values equal the map, **no** `slot_value_approx`, `my_picks` carries the axis) · non-12-team MFL (`slot_value_approx is True`, values equal the percentile-mapped lookup) · order-unset entries never priced · rounds past DP's published 5 omitted · a season DP does not publish omitted · MFL flag-off omission.

---

## 4. Deviations, and why

**D-1 — Extra files touched: `backend/tests/fixtures/seed_ui_test_db.py`, `backend/tests/test_seed_ui_test_db.py`, `backend/tests/test_test_support.py`.**
Making `FTF_DP_PICK_VALUES_FILE` mandatory under `FTF_TEST_MODE` (T-M6-01 requires exactly that) breaks every existing test-mode launcher unless they also pin the file. The seeder now emits a fifth output, `<out>/dp-values/<name>.picks.csv`, and a matching `--print-env` line; its manifest gains `outputs.dp_pick_values`; the two tests were updated in step (`len(lines) == 8`, new path asserts, new abort case). The seeded pick CSV is synthetic-but-shaped (geometric decay over 12-team rounds 1–5 + three 2027 rungs) because the harness world models no draft picks and the harness renders these numbers rather than calibrating against them. **Not touched:** `backend/tests/test_draft_board.py` (parallel agent's).

**D-2 — The percentile map anchors both ends instead of using band midpoints.**
Operator decision O3 says "percentile map"; it does not say which percentile. A midpoint-of-band map (`(s − 0.5)/T`) prices slot 1 of a 10-team round *below* DP's `1.01`, which is simply false — the first pick of a round is the first pick of a round at any league size. Implemented as `1 + (s−1)/(T−1) × 11`, rounded to nearest: slot 1 → `x.01`, slot T → `x.12`, and **T = 12 is the exact identity**, which is what makes the "12-team carries no approx marker" rule structural rather than a special case. `teams <= 1` returns slot 1 rather than dividing by zero.

**D-3 — Future-year RUNGS are parsed and returned by the reader, but the board does not fall back to them.**
The reader maps every PICK row (per the brief), so `2027 Early 1st` etc. are available and tested. The board, however, prices only the draft's **own** season from the per-slot rows; a 2027 draft board renders with no axis rather than an Early/Mid/Late-derived one. Rationale: mixing two pricing bases in a single display column would make M6b's calibration read ambiguous, and honest omission is the wave's stated degradation. **Open question for the operator** — see §6.

**D-4 — `BoardRequest.scoring` defaults to `data_loader.DEFAULT_SCORING` (`1qb_ppr`).**
The Draft Room route (M3, parallel agent's region) does not resolve a league scoring format today, and `BoardRequest` carried none. The field is additive, inert while the flag is off, and the route wave can pass the league's format when it lands. Until then a superflex league would see 1QB slot prices. Recorded in the module docstring as deviation 4. **This must be wired before the flag is flipped** — see §6.

**D-5 — No fixture for `values.csv`'s full width.** The committed `dp_values_picks_2026-08-06.csv` carries all 85 real PICK rows plus 3 real player rows (to prove the `pos` filter), not the whole 726-row file. It is a snapshot for parse/regression purposes, not a value source.

### LLD vs the 2026-08-06 operator decisions

**One conflict, called out here and in a code comment at `backend/data_loader.py` (the M6 section header).**

hld **KD-9** and lld §4.7 record engine adoption of slot values as *rejected*. Operator decision **O2 (2026-08-06) reverses that**: market slot values ARE going into the trade engine, behind a #214-style user toggle, in a dedicated calibration wave (**M6b**), with the display axis landing first (M6). Nothing about *this* wave's code changes as a result — M6 still ships display-only, and `GENERIC_PICK_SEEDS`/bands/engine are byte-untouched — but "display-only" in KD-9 should be read as *"not yet, and not from this code path"*, not as *"never"*. The operator's O10 remark (a future third mode pricing picks off the user's own rookie board) is noted; the map returned by `load_pick_slot_values` is a plain label→Elo dict with no assumptions baked in, so a third mode is not precluded.

No other operator decision touches M6. O3 (percentile map) is implemented; O2's M6b is out of scope; O1/O4/O5/O9/O10 do not reach this code.

---

## 5. What a reviewer should scrutinise

1. **The rail, first.** `backend/server.py` — confirm the `_TEST_MODE` assertion is the ONLY edit to that file (`git diff origin/main -- backend/server.py` should be ~8 lines in one hunk) and that it now requires `FTF_DP_PICK_VALUES_FILE`. Then confirm nothing can reach `values.csv` from a hermetic run: `_fetch_pick_values_csv` raises under `FTF_TEST_MODE` before the `urlopen` branch.
2. **The omit-when-absent contract.** Grep the diff for any assignment of `slot_value` to `None` or `0`. There should be none. A null here renders as "worthless pick" on every client.
3. **`_basis_slot`'s endpoints.** The whole `slot_value_approx` rule leans on `_basis_slot(s, 12) == s`. If someone "simplifies" the formula, the 12-team exactness guarantee silently becomes approximate while the marker still says exact.
4. **`_annotate_slot_values` mutates `order` in place.** That is safe only because `_order_from` / the MFL renderer build fresh lists on every render (the cache stores raw upstream payloads, not rendered ones). If a future wave starts caching rendered payloads, this becomes a bug where a flag flip or format change leaks across requests.
5. **D-4.** `BoardRequest.scoring` defaulting to 1QB is the one place a superflex user would see a wrong-but-plausible number. It is inert today only because the flag is off.
6. **The §2.3 correction.** The plan's "within ~2 Elo at Early/Late" claim is wrong at Late; if M6b inherits that sentence uncorrected, its calibration will start from a false premise.
7. **The shared registry files.** `feature_flags.py` / `features.json` / `release.json` / `config-reference.md` were appended to only. A parallel agent adds `draft.mfl` to the same four; the conflict is expected and resolves by union-dedupe. Note both JSON files' `_comment_rookie_draft` string was extended (not duplicated) — the union-dedupe must merge the *sentence*, not pick one side's whole string.

---

## 6. Open questions for the operator / next wave

1. **Future-season boards have no axis (D-3).** A Draft Room opened in Feb 2027 for the 2027 rookie draft shows no slot values at all, because DP publishes per-slot rows only for the current class. Should the board fall back to the year rungs (Early/Mid/Late by round tercile), clearly labelled as a coarser approximation — or is honest omission right? Recommend deciding alongside M6b, since it determines whether one column can carry two pricing bases.
2. **Wire `BoardRequest.scoring` from the league (D-4)** before `picks.slot_values` is flipped on.
3. **Does the client label the axis?** `slot_value_approx` and the display-only/ladder distinction are only useful if the Draft Room UI actually renders the labels — cross-client-invariants now requires it, and the mobile wave has not built it.
4. **Flag review clock.** Per the ship-by/kill-by convention, `picks.slot_values` starts its 90-day clock on merge.
