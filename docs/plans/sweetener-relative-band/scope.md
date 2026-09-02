# Feature Scope — Gap-sweetener relative band + best-effort fallback (`sweetener_gap_frac`, `sweetener_best_effort`)

**Date:** 2026-09-02
**Entry point:** feedback #414 (mattmurf77, 2026-08-31 — "Why is there a trade offer of Drake London for CeeDee straight up when there are other players I can add to make the trade more fair?"); Q-036 direction settled by the operator 2026-09-02; the 2026-09-01 dual-agent review's sweetener diagnosis and QA's all-or-nothing finding
**Builder:** agent worktree `claude/sweetener-relative-band` (build + prove); the lead ships (D-172 pattern: deploy at defaults → confirm the seeded rows via `GET /api/admin/config` → `PUT` the live triple)
**Operator sign-off on waivers:** needed — §1(c) and §3 (structural guard, TestFlight) are waived below with reasons; surfaced to the lead in the final report

---

## 0. What changes, in one paragraph

`trade_optimizer.close_value_gap` — the 2026-08-21 gap auto-sweetener every generator calls on a finished card — had two defects the #414 card exposed. **Trigger:** its guard is `abs(gv − rv) <= gap_threshold` with `sweetener_gap_threshold` 1,539, a flat absolute, while R1 (`max_overpay_frac` 0.25) is relative — so the sweetenable window `(1539, 0.25·H)` is empty unless the richer side prices above ~6,156, and the served London-for-CeeDee 1x1 (packaged 5,932.8 / 7,328.9, gap 1,396 = 19% of the richer side, fairness 0.81) passed R1 and never reached the closer. **Closer:** it is all-or-nothing — requirement (a) "brings the recomputed gap ≤ threshold" or the card ships unsweetened at its ORIGINAL gap — so lowering the threshold alone regresses (QA: a card partially closable to 1,535 at 1,539 ships at 1,825 once the line is 750). Two `model_config` knobs, both default **0.0 = byte-identical**, both read at call time inside the helper via `_c`: **`sweetener_gap_frac`** makes the trigger `max(gap_threshold, frac × max(gv, rv))`; **`sweetener_best_effort`** (1 = on) attaches, when no single asset closes the gap, the gate-passing candidate that minimises the post-add |gap| — strictly narrower, richer side unchanged — and stamps `gap_sweetener.partial = true`. The code default of `sweetener_gap_threshold` is deliberately untouched; the live bundle lowers it to **750** by PUT alongside the two new rows (the recommended triple is in [results.md](results.md)).

## 1. Analytics scope

- [ ] **(a) New events specced:** none.
- [x] **(b) Existing events cover it** — `gap_sweetener` is already stamped on EVERY `deck_impressions` row inside `features_json` (`backend/server.py:4524`, null when unsweetened) and on the card payload (`trade_card_to_dict`, `server.py:11820`). The new `"partial": true` key rides INSIDE that dict, so the corpus can split full closes from partial closes with no new column, event or taxonomy entry; sweetened share, gap-after distribution and like rate by `partial` are all answerable from what is already logged.
- [x] **(c) WAIVED — no NEW analytics needed because:** the change is inside one helper behind two knobs; the existing per-impression `gap_sweetener` stamp is the measurement surface and it already carries the new field.

## 2. Schema & flag scope

- New/changed tables or columns: **none**. `gap_sweetener` stays a dict inside `features_json` / the card JSON; the new key is additive.
- New/changed feature flags: **none**. Each knob is its own kill switch (0 = byte-identical).
- New `model_config` keys: **`sweetener_gap_frac`** (float, default 0.0) and **`sweetener_best_effort`** (float, default 0.0; 1 = on) → registered in **both** stores: `trade_service._DEFAULT_CFG` (`:530`, `:542`, with the house comment blocks) and `database._MODEL_CONFIG_DEFAULTS` (`:2446-2447` — the boot migration at `:3187` inserts every tuple, and `set_config` at `:4433` raises for a key with no row, so without the seed `PUT /api/admin/config/<key>` 404s). Documented in `docs/config-reference.md` § Tier 3. **Ship-the-knobs (D-172 pattern):** deploy at 0.0 (boot seeds the rows) → `GET /api/admin/config` shows both keys at 0.0 → `PUT` the triple from results.md (`sweetener_gap_threshold` 750, `sweetener_gap_frac` 0.12, `sweetener_best_effort` 1) — **best-effort first, then frac, then the threshold cut**, because a threshold cut without best-effort is the measured regression. **Rollback:** PUT `sweetener_gap_threshold` back to 1539 and both new keys to 0 — deploy-free.
- `sweetener_gap_threshold` code default: **unchanged at 1539** on purpose (the lead flips the live row; the default stays the pre-change engine so arm A's pin and the goldens stand).
- **D-099 bake-off censoring (accepted cost, as for D-172):** arm D (`challenger`) is serving and inherits all three live rows by design; the PUTs are a logged engine-affecting change that censors the current window at their timestamp.
- Bake-off dispositions: `MODEL_A_PROFILE` **pins both new knobs at the identity 0.0** (`bakeoff_profiles.py:147-148`) for the D-172 reason (the live rows move; an unpinned arm A would inherit). Recorded honestly: on an arm-A thread the reads are unreachable today because `sweetener_gap_threshold` is pinned 0.0 (`:105`) and every caller guards `GAP_THR > 0`, so the pins are defence in depth and the load-bearing test proves them with the threshold pin lifted from the overlay. `MODEL_CHALLENGER_PROFILE` does not pin them. Recorded in `backend/tests/test_bakeoff_arm_a_golden.py::_PINNED_KNOBS` and `docs/plans/three-model-bakeoff/scope-phase2.md`.

## 3. Evidence scope

- [ ] **Structural guard:** `mobile/tests/check-<name>.js` — **WAIVED because:** backend-only; no mobile/web/extension file is touched and no client reads `gap_sweetener` (`git grep -n gap_sweetener -- mobile web extension` is empty).
- [x] **Unit tests:** `backend/tests/test_sweetener_relative_band.py` (21) + `test_bakeoff_arm_a_golden.py::test_sweetener_band_pins_are_load_bearing` (1) + two unpack-line updates in `test_gap_sweetener.py`:
  - **goldens, knobs 0** — `close_value_gap` on nine fixtures and full `generate_pair_trades_v3` decks (engine-quality fixture × 3 partners + the gap-sweetener v3 fixture), captured on a `git archive origin/main` (`e16bb487`) tree with the same file at prod's flag posture and `model_config` pins, `cmp`-identical to the branch capture, asserted at the default and at an explicit `0.0 / 0.0`; non-vacuous (both row sets move at the live triple);
  - **the #414 card** — the fixture reproduces the served numbers exactly (5,932.8 / 7,328.8, gap 1,396.0, fairness 0.81, 0.12·H = 879.5); untouched at today's knobs; a best-effort partial with the 1,200 piece (→ 1,058.9, `partial: True`, filler-clean at 0.15, fairness 0.859) at (750 / 0.12 / 1); a full close (1,500 → 772.1) when the bench holds one, and a full close only because the band lifted the trigger from 750; frac 0.20 lifts the trigger above the gap and the card is left alone;
  - **QA's regression** — G 5,400 / R 7,000 (gap 1,828.1): full close with 1,480 (→ 1,534.5) at 1,539; **unsweetened at (750 / 0 / 0)**; a partial with 1,480 — the tightest, not the cheapest 1,200 (→ 1,708.3) — at (750 / 0 / 1);
  - **guards** — a 3,200 piece that flips the richer side at |gap| 1,063.6 while passing R1, filler and fairness is never chosen over the 900 partial; pieces that widen the packaged gap (450 → 1,514.2, 600 → 1,445.0) are never attached even with the #141 gate off; both knobs are read through `_cfg_override`; both stores agree at 0.0, arm A pins, the challenger does not;
  - **stamp path** — consensus (the #414 card through `generate_trades`: `partial: True`, gap_before 1,396.0 / gap_after 1,058.9), v3 (QA's shape on that path: unsweetened at defaults, a partial at the triple; a full close carries no `partial` key), v2 divergence (a stamped partial); arm C via the harness `C_gen_v2` rows and the code-walk (it emits nothing on the unit fixtures);
  - **property fuzz** — 200 random rosters × 4 formats × picks on/off through the helper with the live gate stack (R1, #141 filler, #227 pick gate; ratio + feasibility inside), and 32 generated decks at the live triple with presentment rules ON: no exceptions; every sweetened card passes R1, the #141 gate on the path's own boards, the path's fairness bar (0.75 consensus; `min(0.75, fairness_floor_divergence)` on the divergence paths, which loosen it at `trade_optimizer.py:302` before any gate — pre-existing, inherited verbatim) and lineup feasibility; every partial strictly narrows the gap with the richer side unchanged; every full close sits under the effective trigger; both branches exercised.
  - Five sabotages proven red → green (byte-copy restore, `cmp`, `__pycache__` cleared — G-060); recipes in the module docstring, outcomes in [results.md](results.md) § Sabotages.
- [x] **Code-walk proof:** [code-walk.md](code-walk.md) — the call-time reads, the knob-0 identity for BOTH knobs, every call site and every overlay (arm A pins, challenger inherits, #189 relaxed pass), the `partial` stamp path and the wire payload, and the package-math note that qualifies the brief's arithmetic.
- [x] **Harness measurement:** [measure_sweetener.py](measure_sweetener.py) → `results-raw-f075.json` / `results-raw-f050.json` → [results.md](results.md). Prod-pinned baseline (D-159 bundle + `asset_floor_abs` 450 + `max_overpay_frac` 0.25 + `sweetener_gap_threshold` 1539 + `consensus_fit_weight` 0.5), `PYTHONHASHSEED=0`, clock frozen (G-065), baseline run twice and byte-identical per cell; variants V1–V4 × 4 leagues (incl. a #414-shaped 1x1 planted in the 12-team 1QB fixture) × 2 paths × 4 arms.
- [ ] **Manual TestFlight checklist** — **WAIVED because:** no client change; the runtime check is server-side and is written for the lead in results.md § After the flip (re-read the #414 league's deck for mattmurf77 after the PUTs and confirm the London/CeeDee card carries a `gap_sweetener`, `partial` or not).
- `testID`s added/renamed: none.

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` (any route added/renamed/removed/contract-changed) | **updated** | no route added or changed (both knobs ride the existing `GET/PUT /api/admin/config` contract, whose key set is "every `_MODEL_CONFIG_DEFAULTS` row"); the card-payload block gains a `gap_sweetener` entry next to `sweetener` — that dict had been undocumented there since 2026-08-21 (a pre-existing gap) and now carries the optional `partial` key, so the whole shape is written down once |
| `docs/config-reference.md` | **updated** | § Tier 3 — two new rows after `sweetener_gap_threshold` (semantics, where they bite, the `partial` stamp, arm dispositions, the DB seed, the live values and the rollback PUTs) and a sentence on the `sweetener_gap_threshold` row saying the live row moves to 750 by PUT while the default stays |
| `living-memory/LLD.md` (schema/route/invariant *conventions* shifted) | n/a | no convention shifted — the knobs follow the D-098 call-time-`_c` rule and the two-store registration discipline (the lead owns living-memory writes per the brief) |
| `docs/architecture.md` (module wiring / data flow changed) | n/a | two knob reads inside one helper; no module, import or data-flow edge changes (`_c` was already imported by `trade_optimizer`) |
| `living-memory/HLD.md` (architecture genuinely shifted) | n/a | as above |
| `docs/cross-client-invariants.md` (shared constants/enums/colors) | n/a | no client-visible constant or enum; `partial` is an optional boolean no client reads |
| `docs/glossary.md` (new domain term) | n/a | "gap sweetener" / "equalizer" already exist from 2026-08-21; "partial close" is defined in the config-reference row |
| ADR or `DECISIONS.md` entry (non-obvious choice made) | **for the lead** | three choices to record when shipping (drafted in results.md § Ledger draft): (1) the trigger is `max(absolute, relative)` — a floor plus a band, not a replacement; (2) best-effort picks the **tightest** gate-passing partial, never a flipped one, and any threshold cut ships WITH it; (3) arm A pins both identities although the reads are unreachable under its threshold pin |
| `docs/plans/three-model-bakeoff/scope-phase2.md` | **updated** | knob disposition rows |
| `docs/plans/README.md` | **updated** | thread-folder row |

## 5. Ship gate declaration

- **CI green:** `pytest backend/tests` — **4541 passed, 1 skipped** on the branch tip rebased onto `e16bb487` (clean-main baseline 4519 passed, 1 skipped the same day; +22 = the new tests exactly); `tsc --noEmit` and `testid-lint` untouched (no mobile file changed).
- **Evidence recorded:** `living-memory/TEST_LEDGER.md` — **the lead writes it** (brief: no living-memory writes from this worktree); the ledger text is drafted in results.md § Ledger draft.
- **TestFlight verification:** waived (§3) — replaced by the prod verification steps in results.md § After the flip.
- Express lane declared by the operator? **No** — full gates.
