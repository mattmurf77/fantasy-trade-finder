# Feature Scope — pick-badge value→Elo inverse (D-088)

**Date:** 2026-08-19
**Entry point:** direct ask — "round-3 draft picks are overvalued; a current-year 3rd now badges as a `second`"
**Builder:** backend session, worktree `wt-round3`, branch `fix/pick-round3-value`
**Operator sign-off on waivers:** not needed (no waivers — every section is answered)

**One-line summary:** the pick badge on `GET /api/league/picks` inverted `pool_value` with the wrong one of the codebase's two value↔Elo maps. Corrected to `trade_service.value_to_elo`. Display-only; no price, seed or tier band moved.

---

## 1. Analytics scope

- [x] **(c) WAIVED — no analytics needed because:** this changes the value of an existing serialized field (`tier`) on an existing route. No new event, no new property, no new emitter, and no existing event carries a pick's tier. `analytics_taxonomy.py` and `analytics_queries.NON_INTENT_EVENTS` are untouched.

**Cohorting note recorded rather than instrumented:** any future analysis that reads a pick badge must cohort on 2026-08-19, because the same `pool_value` badges differently before and after this change. Written into `docs/api-reference.md` and the `OwnedPick.tier` doc comment in `mobile/src/api/league.ts` so the shift is not later read as a client regression.

## 2. Schema & flag scope

- **New/changed tables or columns:** none. `draft_picks.pool_value` is read, never written; no migration. `docs/data-dictionary.md` needs no change (the column's meaning is unchanged — it was already documented as `elo_to_value` units, which is the fact the fix relies on).
- **New/changed feature flags:** none. Not flag-gated — see §5 for why.
- **New env vars / `model_config` keys:** none. **Deploy-free rollback lever: none, deliberately.** A knob here would be a knob that selects between a correct and an incorrect arithmetic inverse; there is no configuration in which the old value is right. Revert = revert the commit and redeploy (Render auto-deploys `main`). No client release is needed — the field is server-computed and clients render whatever arrives.

## 3. Evidence scope

- [x] **Structural guard:** n/a — no `mobile/tests/check-*.js` added. The only mobile change is a JSDoc comment inside an existing block comment (diff is comment-only); there is no client-side behavior to pin, because clients render the server's `tier` verbatim and are forbidden from re-deriving it (`docs/cross-client-invariants.md`).
- [x] **Unit tests:** `backend/tests/test_league_picks_tier.py` — 5 existing tests retargeted, **2 added** (5 → 7). The important one is a *property*, not a literal:
  - `test_current_year_rungs_badge_their_own_round` — a current-year pick of round R must badge exactly where `GENERIC_PICK_SEEDS[(R, "Mid")]` sits, asserted through the route for all four rounds, plus the underlying identity `value_to_elo(pick_pool_value(R, 0)) == GENERIC_PICK_SEEDS[(R, "Mid")]`. This is what `tier_config.json`'s `_calibration` already *defines* to be true. **No wrong inverse can satisfy it for all four rounds** — which is exactly the failure mode of the literal-Elo pins it supplements, since those had been written by reading the buggy output back.
  - `test_deep_far_out_pick_tiers_null_rather_than_flattering_it` — a 2029 4th prices below the `waivers` floor and must carry `null`, not a fabricated `third`.
  - Sabotage `S1b` ("wrong INVERSE") is documented in the file header alongside the pre-existing `S1`/`S2` traps.
- [x] **Code-walk proof:** `docs/reviews/2026-08-19-pick-badge-scale.md` § "The actual defect" and § "Why 1383.5, exactly" — the full file:line-cited trace (`backend/database.py:1040` for the column's scale, `backend/pick_values.py:264-266` for how `pool_value` is produced, `backend/server.py` `_pick_tier` for the conversion, `backend/tier_config.json` `_calibration` for why the seeds are on the band scale), with the arithmetic reproducing 1383.5 end to end and the single-crossing-point proof that `seed_elo_for_value` is not the inverse of `elo_to_value`.
- [x] **Manual TestFlight checklist** — runtime proof genuinely matters here: tier colours on a real board, and one case where a badge disappears rather than changing. See below.
- **`testID`s added/renamed:** none. `mobile/scripts/testid-lint.sh` → **OK**.

### Manual TestFlight checklist

Run against a Sleeper or MFL league with synced picks (ESPN leagues carry none unless assignments were entered). Expected values assume current season 2026 and a league whose picks have re-synced since D-079/D-084.

1. Open the in-league **Calculator** → tap to add an asset → scroll to the pick rows. **Expect:** a **2026 3rd** shows the `third` tier badge and colour, *not* `second`. This is the reported defect.
2. Same list: a **2026 4th** shows `fourth`, not `third`. (This one was wrong before the report and is the second rung fixed.)
3. Same list: a **2026 1st** still shows `first_1` and a **2026 2nd** still shows `second`. **If either of these moved, stop — round 1 and 2 were not supposed to change.**
4. Scroll to a **2029 4th** (or the furthest-out 4th the league holds). **Expect:** *no tier badge at all* — the row falls back to its numeric value. A badge reading `third` there is the old behaviour; a crash or a blank row is a bug worth reporting.
5. A **2027 2nd** now reads `third`. This is intended (a year of decay drops it just under the `second` floor of 1370) and is the change most likely to look surprising — confirm it renders cleanly rather than that it reads as expected.
6. Open the **Picks** screen for the league and confirm the same badges appear there, matching the calculator exactly (both read the same route).
7. Build a trade in the calculator containing a 2026 3rd and confirm the **values and the fairness verdict are unchanged** from before this build. Pricing must not move — only the badge. This is the single most important step: if any number changes, the fix leaked out of the display layer.

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | **updated** | `GET /api/league/picks` — the `tier` derivation now names `trade_service.value_to_elo`, with the D-088 correction, the two-map divergence at Elo 1548.0, and the two null cases |
| `living-memory/LLD.md` | **n/a** | no schema, route or invariant *convention* shifted — the route's contract (an additive `tier` field, server-computed, nullable) is unchanged; only the arithmetic inside it |
| `docs/architecture.md` | **n/a** | no module wiring or data-flow change; one expression inside an existing serializer |
| `living-memory/HLD.md` | **n/a** | no new module, client or flow |
| `docs/cross-client-invariants.md` | **updated** | new subsection under the banding rule: the two value↔Elo maps, which inverts which, the single crossing point at Elo 1548.0, and the current-year-rung invariant to test against. This is the doc that should have prevented the defect |
| `docs/glossary.md` | **n/a** | no new domain term (`pool_value`, seed Elo and tier band are all already defined) |
| ADR or `DECISIONS.md` entry | **updated** | [D-088](../../living-memory/DECISIONS.md). Not a formal ADR — it corrects an arithmetic error rather than choosing an architecture |
| `docs/data-dictionary.md` | **n/a** | no column added, removed or redefined |
| `docs/config-reference.md` | **n/a** | no env var, flag or `model_config` key |
| `living-memory/GOTCHAS.md` | **updated** | [G-052](../../living-memory/GOTCHAS.md) — the wrong-inverse trap, its single crossing point, and the property-vs-literal testing lesson |
| `living-memory/OPEN_QUESTIONS.md` | **updated** | Q-019 closed with its answer; the surviving seed-map half re-logged as Q-020, sized as an every-player-board change |
| `backend/pick_values.py` module note | **updated** | the D-084 note that pointed at Q-019 now carries a warning not to reach for it to explain a wrong badge, the re-derived compression figure (54.9 Elo over ranks 200–300), and the current-year-rung invariant |

## 5. Ship gate declaration

- **CI green:** `pytest backend/tests` → **3443 passed, 1 skipped, 0 failed** (baseline on `a130dfc` was 3441 + 1 skipped; +2 is exactly the two tests added). `tsc --noEmit` → **clean, exit 0**. `mobile/scripts/testid-lint.sh` → **OK**. `test_tier_occupancy.py` specifically → **47 passed, unchanged**.
- **Evidence recorded:** `living-memory/TEST_LEDGER.md`.
- **TestFlight verification:** checklist written in §3, **not yet run** — it needs the operator and a TestFlight build.
- **Express lane declared by the operator?** **No.** Full gates applied. The change touches a cross-client invariant doc, which the CLAUDE.md bright line names explicitly, so express would not have been available without a confirming yes even had it been offered.
- **Not flag-gated, deliberately:** a flag here would select between a correct and an incorrect arithmetic inverse, and the "off" position is a known-wrong badge. The change is display-only, carries no data migration, and reverts with one commit revert plus a redeploy.
- **Not pushed, not merged.** Committed to `fix/pick-round3-value` only.

## 6. What was explicitly NOT changed

Recorded because the brief named these as bright lines and because the *absence* of these edits is the main evidence that the fix stayed in its lane.

| | status |
|---|---|
| `backend/pick_values.py` `GENERIC_PICK_SEEDS` | byte-unchanged (module *comment* updated, no seed touched) |
| `backend/tier_config.json` | **not opened** |
| `mobile/src/utils/tierBands.ts` | **not opened** |
| `web/positional-tiers.html` | **not opened** |
| `web/js/app.js` `_eloToTierLabel` | **not opened** |
| `backend/scripts/replay_trade_decisions.py` | **not opened** |
| `backend/ranking_service.py`, `backend/trade_service.py`, `backend/bakeoff_runner.py` | **not opened** (concurrent siblings own these) |
| `draft_picks.pool_value` rows | never written; prod access was `SET TRANSACTION READ ONLY`, SELECT only |
| `backend/tests/test_tier_occupancy.py` | **not re-baselined** — it was never red |
