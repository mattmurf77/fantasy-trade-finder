# Build status — W2a: FTF-native mock draft, backend (engine + calibration)

**Date:** 2026-08-06 · **Wave:** draft-extensions W2a · **Status:** built, gated, **CPU-bot mock CUT by the abort criterion**
**Spec:** [plan.md](plan.md) §5 + the three binding amendments · [lld.md](lld.md) §2.3 / §3.3 / §4.2 / §7 · [rookie-draft/mock-draft-plan.md](../rookie-draft/mock-draft-plan.md) §4–9
**Gate artifact (I-10):** [mock-calibration-2026-08.md](mock-calibration-2026-08.md)

---

## Headline

The engine, the store, the routes, the flag and the full test matrix shipped and are green.
**The calibration gate FAILED**, so plan §5's W2 abort criterion fired: the CPU-bot mock is
**cut**, `draft.mock` lands and stays OFF, and even with the flag ON the create route answers
the typed-empty `200 {"empty": true, "reason": "cpu_model_unvalidated"}` rather than serving
bots whose noise model could not be validated.

Everything except the noise model validated cleanly, which is exactly the shape the amendment
was written to produce: a re-specced model can be re-gated by re-running **one test**, not by
rebuilding a wave.

### The calibration numbers, in one table

| Stage | Corpus | n | Bar | Result | |
|---|---|---|---|---|---|
| Fit | `lakeview-complete` r1–2 | 23 | min W₁ over jitter ∈ [0.25, 3.00] | fitted **3.00** — *pinned at the grid boundary*, W₁ only 2.348 → 2.059 across a 12× parameter change | ⚠️ degenerate |
| Hold-out | `lakeview-complete` r3–4 | 20 | KS not rejected at α = 0.05 | D = 0.567, **p = 2.3 × 10⁻⁶** | **FAIL** |
| Hold-out | " | 20 | \|Δ mean\|d\|\| ≤ 1.0 | observed 2.65 vs simulated 0.280 ⇒ **Δ = 2.37** | **FAIL** |
| Independent (no refit) | `mfl-complete` | 28 | KS at α = 0.05 | D = 0.570, **p = 9.4 × 10⁻⁹** | **FAIL** |
| Independent (no refit) | " | 28 | \|Δ mean\|d\|\| ≤ 1.0 | observed 5.36 vs simulated 0.295 ⇒ **Δ = 5.06** | **FAIL** |

**Why — structural, not a tuning miss.** A candidate at rank *r* wins the argmin only while
`r − need_bonus − jitter < 1`, so the model's reachable support is bounded by ≈ `max_reach +
jitter` ≈ 6 slots (and hard-capped by the `K = 8` window). The corpora put **21 % of real picks
at 6–9 slots**, and `mfl-complete` contains reaches of 11, 17, 26 and 33. Human rookie drafting
is mixture-shaped — mostly exact BPA (44 % of Lakeview picks are `d = 0`), occasionally a
private conviction nine slots off the board. A single additive uniform noise term is the wrong
family. Matching the *mean* alone would need `mock_jitter_slots ≈ 28`, nine times the product's
own reach cap, and the shape would still be wrong. Full derivation in the artifact §5.

---

## What shipped

| Artifact | Notes |
|---|---|
| `backend/mock_draft_service.py` (new, ~640 lines) | Pure, injection-driven engine. `MockContext` · `consensus_pool` · `positional_needs`/`slot_targets`/`severity` · `cpu_pick` · `pick_slots`/`owner_of` · `build_settings`/`new_state`/`advance_cpu`/`apply_user_pick` · `state_payload`/`empty_payload` · `dumps`/`loads` · the calibration harness (`reach_series`, `simulate_reaches`) |
| `backend/database.py` | New `mock_drafts` table + `create_mock_draft` / `load_mock_draft` / `load_current_mock_draft` / `update_mock_draft`. Table lands via `metadata.create_all` — no migration needed |
| `backend/server.py` | One new region: `_mock_league_context`, `_mock_context_from_row`, `_mock_resolve_league` and the four routes. No existing line changed except the `database` import list |
| `backend/feature_flags.py` + `config/features.json` + `backend/tests/fixtures/flags/release.json` + `docs/config-reference.md` | The 4-touch for `draft.mock`, default **false**; the mirror test passes |
| `backend/tests/test_mock_draft.py` (new) | 53 tests — T-W2-01..17 plus the abort-criterion enforcement tests |
| `docs/plans/draft-extensions/mock-calibration-2026-08.md` | **The I-10 gate artifact** |
| `docs/api-reference.md` · `data-dictionary.md` · `config-reference.md` · `glossary.md` · `architecture.md` | Per the CLAUDE.md trigger table |

**Not touched:** any `mobile/` file (owned by another agent this wave), `draft_board_service.py`,
`trade_service.py`, `power_rankings.py`, `_MODEL_CONFIG_DEFAULTS`.

## The three binding amendments, as implemented

1. **CPU basis = market consensus via the shipped seam.** `server._get_universal_pool(fmt)[1]`
   is injected as `MockContext.consensus_elo`, and the pool is
   `draft_board_service._undrafted(basis="consensus")` **itself** — not a re-implementation.
   `test_w2_15_the_mock_pool_is_undrafted_basis_consensus_element_for_element` asserts equality
   element for element; `test_w2_14_the_service_declares_no_second_consensus` is an AST check
   that the module contains **no `sorted`/`.sort` call at all**, so a second ordering cannot
   creep in later. The user's board changes the user's undrafted sort and provably no CPU pick.
2. **Fit separated from validation.** Implemented exactly per lld §4.2.3 — grid search on the
   fit block only, 1000 seeded simulations per grid point, both bars on the hold-out, then the
   independent corpus with no refit. The simulator drives the **shipped** `cpu_pick`, so the
   number in the artifact and the number the engine produces cannot drift.
3. **Abort criterion, expressed in code.** `CPU_MODEL_VALIDATED = False` makes `advance_cpu`
   raise `CalibrationGateClosed` unless a caller explicitly opts in — the harness and the engine
   tests do, the routes never do. `test_w2_16_calibration_gate` asserts
   `passed is CPU_MODEL_VALIDATED`, **in both directions**: if a future change made the model
   pass, the test goes red and forces a deliberate re-publish rather than an accidental flip.

## Gates

| Gate | Result |
|---|---|
| `python3 -m pytest backend/tests -q` | **1817 passed, 1 skipped, exit 0** (baseline ~1764; +53 new) |
| `cd mobile && npx tsc --noEmit` | **clean, exit 0** — untouched, as required (`mobile/node_modules` was symlinked from the main checkout for the run and removed after) |
| Flag mirror (`test_release_flags_mirror_features_json`) | green |
| Zero platform egress | T-W2-13: AST import check + an unbound-fetcher check + a full mock run under `FTF_TEST_MODE` with `test_support.counters` byte-unchanged |
| Determinism / resume | T-W2-05, T-W2-11: same seed ⇒ byte-identical picks JSON; a rehydrated row and a continuous one advance identically |

## Deviations from the LLD, and why (each is load-bearing)

### 1. The reach observable — the LLD's `d_i` is self-contradictory

lld §4.2.3 writes `d_i = consensus_rank_at_pick − i` **and** says the rank is taken "over the
pool as it stood at that pick (drafted players removed)". Those cannot both hold: over a
remaining pool the BPA pick always ranks 1, so `rank − i` reads `1 − i` and a pure-BPA draft
scores a huge "fall" — contradicting the same paragraph's "`d_i < 0` = a fall".

Measured both ways on `lakeview-complete`:

| Reading | mean \|d\| r1–2 | r3–4 | drift |
|---|---|---|---|
| Remaining-pool rank − 1 (**adopted**) | 2.35 | 2.65 | **0.30** |
| Static pre-draft rank − pick index | 2.65 | 5.55 | **2.90** |

The static reading is non-stationary by 2.9 slots — **more than the ±1.0 hold-out bar itself**,
so under it the gate would reject every possible single-parameter model and be testing the split
rather than the model. Adopted the stationary reading; pinned by
`test_w2_16_the_observable_is_stationary_across_the_split`, which asserts both the absolute bar
and the comparison, so the choice cannot silently rot. Consequence: `d ≥ 0` always, `|d| = d`,
and a "fall" is not expressible — every bar is otherwise unchanged.

### 2. `mfl-multi-unit` is excluded — but not for the reason the LLD gives

The LLD calls it "startup-shaped". By the shipped discriminator
(`draft_status.ROOKIE_MAX_ROUNDS = 8` / `STARTUP_MIN_ROUNDS = 15`) it is **not**: it runs 5
rounds. The real disqualifier is that it is a **two-unit conference-split draft**
(`CONFERENCE00`/`CONFERENCE01`, 96 picks and 16 franchises each), so "the pool as it stood at
that pick" is undefined across units. Excluded on that ground, asserted in T-W2-17.

Also corrected: `mfl-complete` is a **3-round** draft (30 picks / 10 teams) and `mfl-partial` is
3 rounds made of 6 (36 of 72) — the LLD's "30/30" and "36/72" counts are right, the round shapes
were never stated.

### 3. `not_rookie_draft` is a data test, not a live board build

lld §2.3 specifies `400 not_rookie_draft` "when the M3 board's `kind != "rookie"`". Building the
M3 board at create would mean a live platform read on the create path. Implemented instead as
`rounds` outside `1..ROOKIE_MAX_ROUNDS`, which makes **creation itself egress-free** — strictly
stronger than the spec's "zero egress *after* creation" bar — and keeps O-M7 (a league with no
draft object is the *primary* mock case) working without a branch.

### 4. `mock_max_reach_slots` / `mock_jitter_slots` are not seeded into `_MODEL_CONFIG_DEFAULTS`

They belong to a feature whose gate is closed, so the module default is the single source until
an operator inserts a row; `mock_draft_service._c` overlays `database.get_config()` either way,
so they are tunable the moment anyone wants them. This also kept the change inside this wave's
file ownership (`_MODEL_CONFIG_DEFAULTS` is a shared region).

### 5. `cpu_model_unvalidated` rides the existing typed-empty contract

A new state was needed and D10 forbids new members in closed client enums. It reuses M2's
`200 {"empty": true, "reason": …}` shape — the same contract `class_not_loaded` already uses —
rather than a new error code or a new `state`/`kind`/`order_confidence` value.

### 6. The calibration consensus is hermetic and trimmed — stated, not hidden

The corpora are ranked from the committed `player_pool_2026.json` snapshot through the shipped
`seed_elo_for_value` and the shipped `_undrafted`, but that snapshot is top-N-per-position and
carries no live KTC blend. The resulting rookie universe is 50 (Lakeview, `sf_tep` — it is a
superflex league) and 56 (MFL, `1qb_ppr`); 5 of 48 Lakeview picks and 2 of 30 MFL picks fall
outside and are dropped, with the ranking **and** the sequence restricted to the same
sub-universe so `d` stays self-consistent. A richer universe would only *widen* the observed
tail, so it cannot rescue the verdict.

## Recommended next steps (for the operator, not decided here)

1. **Re-scope W2b/W2c to practice/replay, or defer them.** Practice/replay needs no noise model
   — the non-user picks come from a recorded corpus — and plan O5 already recommends the tester
   allowlist for it. The mobile wave as specced assumes bots.
2. **If the bots are wanted, re-spec the model, don't retune it.** The artifact §7 records what
   the evidence says a passing model needs: a two-parameter mixture (mostly BPA + a heavy-tailed
   reach branch), the `K` cap removed from the fit, and a full-shaped consensus snapshot. Keep
   the split and both bars exactly as they are — they worked.
3. **Leave `draft.mock` off the quarterly flag-review kill list until (1) is decided.** The code
   is inventory with a recorded reason, not archive.
