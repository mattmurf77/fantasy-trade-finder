# Feature Scope — #313: 1QB consensus QB values cap at "1 1st"

**Date:** 2026-08-14
**Entry point:** feedback #313 (backend wave plan `docs/feedback/items/311-lineup-values-nonsleeper/plan-2026-08-13.md` § Item #313)
**Builder:** build-313 agent (worktree `.claude/worktrees/build-313`, base `origin/main` @ `21df73f`)
**Operator sign-off on waivers:** granted 2026-08-15 — the operator directed the ship to continue after the resume summary surfaced both waivers and the Tier-4 deviation explicitly ("Continue the opus sub agent task"). Mechanism itself (value-side compression, order-preserving, defaults 1785/1580, kill switch = either knob ≤ 0) was **operator-confirmed before build**.

---

## 1. Analytics scope

- [x] **(c) WAIVED — no analytics needed because:** this is a pure valuation
  recalibration. No new user action, no new surface, no new state: the same
  screens render the same fields with re-priced numbers, and the tier label is
  derived client-side from the served Elo (no new client branch). The event
  taxonomy (`backend/analytics_taxonomy.py`) is untouched — no event is added,
  renamed, or given a new property.
- Existing funnels are the outcome read: swipe/verdict/DraftRoom-view events
  already fire on these surfaces and need no change to observe the effect.

## 2. Schema & flag scope

- **New/changed tables or columns:** none. No migration. `docs/data-dictionary.md` n/a.
- **New/changed feature flags:** none. This is knob-gated, not flag-gated — the
  knobs *are* the ship-the-knob lever (below), so a flag would be a second,
  redundant switch on the same behaviour.
- **New `model_config` keys (2):** seeded in `backend/database.py`
  `_MODEL_CONFIG_DEFAULTS` (INSERT OR IGNORE, idempotent); `data_loader`'s
  module constants are the no-DB fallback.

  | Key | Default | Meaning |
  |---|---|---|
  | `qb_1qb_cap_elo` | `1785.0` | Max seed Elo a QB may reach in `1qb_ppr` (top of the `first_1` band; `firsts_2` starts at 1788). QB values are compressed onto it. |
  | `qb_1qb_cap_knee_elo` | `1580.0` | Seed Elo below which 1QB QB values pass through untouched (the `first_1` floor). |

  **Ship-the-knob / deploy-free rollback:** set either key ≤ 0 in `model_config`
  and rebuild the pool — the seed pipeline returns to byte-identical pre-#313
  output (proven: `status-2026-08-14.md` § Kill-switch proof, full 633-player ×
  2-format pool, 60,276 bytes identical against base `21df73f`).
  → proposed `docs/config-reference.md` rows are in the status file for the
  orchestrator to apply (shared doc — not edited by this agent).

## 3. Test scope (mobile test platform)

- [x] **WAIVED (Maestro delta) because:** no UI change ships. No new screen,
  component, testID, navigation path, or client branch — the DraftRoom label
  the operator complained about is *derived* from the served Elo by the
  existing `tierForElo` walk (`mobile/src/utils/tierBands.ts`), so it self-
  corrects from the value alone. A Maestro flow can only assert what the
  seeded hermetic backend serves, and the hermetic harness seeds its own
  fixture values rather than the DP pool, so a flow would pin the fixture, not
  the fix. Correctness is pinned where the behaviour lives: 15 backend tests,
  6 of them proven RED under their named sabotage.
- `testID`s added/renamed: none.
- **Capture delta:** none — no visual change beyond the numbers/labels that
  already render from served data.
- **Smoke-suite impact:** none of the 11 smoke flows assert absolute player
  values or tier labels for a named QB (verified by grep for real QB names
  across the flows and backend tests — only historical DP fixture CSVs in
  `backend/tests/fixtures/dp-values-history/` contain them, and that module
  imports only name-normalisation helpers, never the seed map). Flows stay green.
- **Backend pytest:** baseline `2763 passed, 1 skipped` → final `2779 passed,
  1 skipped`, both run inside the worktree; 0 failures either side.
  - added `backend/tests/test_qb_1qb_cap.py` (16 tests, 6 sabotage-proven)
  - amended `backend/tests/test_ktc_blend.py` — `test_blend_off_is_byte_identical`
    and `test_blend_with_empty_ktc_is_dp_only` now also neutralise the #313
    knobs, because "the pre-#145 pipeline" now means *every* seed knob neutral.
  - amended `backend/tests/test_dp_format_mapping.py` — the raw-DP-column test
    neutralises the #313 knobs exactly as it already did the KTC blend.
    Rationale + honest disclosure for all three in the status file § 7.

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a | No route added, renamed, removed, or contract-changed. Existing routes serve the same fields; only the numbers move. |
| `living-memory/LLD.md` | n/a | No schema/route/invariant *convention* shifted. The seed pipeline gains a stage inside an existing function; the module's contract (in → maps out) is unchanged. |
| `docs/architecture.md` | n/a | No module wiring or data-flow change — one new private helper inside `backend/data_loader.py`, called from the function directly above it. |
| `living-memory/HLD.md` | n/a | No new module, client, or major flow. |
| `docs/cross-client-invariants.md` | **updated (orchestrator, ship commit)** | One line under the pick ladder recording that 1QB QB seeds are compressed below the `firsts_2` floor while the **bands themselves are unchanged** — the point being that no client mirror forks. Text in the status file. |
| `docs/glossary.md` | n/a | No new domain term — "compression", "knee", "cap" are described in place in `data_loader.py`'s section comment. |
| `docs/config-reference.md` | **updated (orchestrator, ship commit)** | Two new `model_config` rows + an amendment to the `ktc_blend_weight` row, whose byte-identity claim now needs the #313 knobs off too. Verbatim text in the status file. |
| ADR / `DECISIONS.md` | **updated (orchestrator, ship commit)** | D-entry: value-side re-pricing chosen over a tier-band/label fork; order-preserving compression over a hard clamp; knobs + kill switch. |

## 5. Ship gate declaration

- **Simulator-gate tier:** **Tier 4 — CI only** proposed. Rationale: backend-only
  change, zero client files touched, no new UI state, no route/schema/flag
  surface; the mobile clients render served numbers through code paths that did
  not change. The hermetic Maestro harness seeds its own values, so a sim run
  would exercise fixtures unaffected by this change and produce no evidence
  about it.
- **Tier deviation recorded as an operator decision (2026-08-15):** the
  change *is* user-visible (every 1QB trade valuation moves), which normally
  argues for a higher tier. The deviation was surfaced to the operator in the
  resume summary and the operator directed the ship to continue — **Tier 4
  (CI only) confirmed**. Doc rows in §4 were applied by the orchestrator in
  the same ship commit.
- Evidence on file: full-suite pytest before/after, a 6-row sabotage matrix
  with actual output, the before/after top-8 QB table generated by running the
  real pipeline, and the kill-switch byte-identity proof — all in
  `status-2026-08-14.md`. TEST_LEDGER entry + `qa/sim-runs/last-sim-run.json`
  are orchestrator-owned.
