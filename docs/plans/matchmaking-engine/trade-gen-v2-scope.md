# Feature Scope — Trade generation pipeline v2 (`trade_gen.v2`)

**Date:** 2026-08-16
**Entry point:** direct ask — matchmaking research program, build item 2 (research: `docs/research/matchmaking/` rounds 1–2)
**Builder:** build agent, branch `feat/trade-gen-v2` (worktree)
**Operator sign-off on waivers:** pending — waivers listed below, surfaced in the ship report before merge

---

## What this is

A divergence-driven, dual-board, **staged** trade-generation engine
(`backend/trade_gen_v2.py`) implementing the round-1/round-2 matchmaking
research findings, behind the default-OFF flag `trade_gen.v2`, built
**alongside** the existing v2/v3 engine (never replacing or modifying its
paths — flag off, the module is never imported).

Pipeline (research memo 02 §6, the 7-step transfer plan):

1. **Partner + centerpiece selection** by board divergence (`v_user(X) −
   v_opp(X)` large on the opponent's roster), want/accept boards applied
   as *filters* (not_interested, untouchable) and *priority* (targets).
2. **Return-package search** around each centerpiece — packages capped at
   3 assets + picks per side; user-side returns ranked by `v_opp − v_user`
   (log-rolling direction). Never raw combinatorial search.
3. **Hard gates in order:** composition hygiene (reuses #141 filler +
   #227 pick-churn conventions) → roster feasibility both sides (v3
   `_feasible_after` rule) → **dual-board ε-gain** both sides on their OWN
   boards (`gen2_epsilon`, extending the #108 `user_gain_epsilon`
   convention to both sides) with a **non-linear consolidation discount**
   on multi-asset sides (curve documented in the module docstring +
   config-reference; junk contributes ≈ `gen2_consol_floor`·v, closing the
   KTC junk-stuffing exploit) → **consensus fairness band** ±`gen2_band`
   (defensibility constraint, never an objective).
4. **Ranking:** joint gain (sum of both own-board gains), tiebreak by
   surplus-split symmetry.
5. **Completion-probability hook:** empirical-Bayes acceptance prior per
   counterparty (`acceptance_prior`), global-prior fallback, narrow
   `{uid: (accepts, responses)}` interface a learned model can replace.
6. **Exposure shaping:** per-counterparty cap (`gen2_exposure_cap`) +
   viable-suggestion floor (`gen2_exposure_floor`); per-team exposure
   counts logged (`GenerationReport`, one JSON log line).
7. **Presentation payload:** batch dedup (documented 3-part rule), MESO
   return-package variants on each pair's top card (recipient-board
   equivalence, distinct shapes), structured two-sided `rationale` on
   every card, per-suggestion health metrics (`joint_gain`, `split_ratio`,
   IR margins, `band_position`) in `card.health` + the report.

**Direction change 2026-08-16 (operator decision, follow-up commit):
no engine truncation + tier metadata.** Uncapped discovery and an
uncapped browsable list are the ranking-signal surface; scarcity applies
only to endorsement. Concretely:
- `generate_league_suggestions(max_per_opponent=None)` — the default now
  returns the FULL post-dedup ranked survivor set; an int is a
  caller-passed presentation limit only. The TradeService integration
  deliberately does NOT forward the route's `max_per_opponent`.
- Exposure cap/floor logic is unchanged in mechanism but is now
  **ordering, never truncation**: the floor-first + cap-greedy pass
  shapes the head of the list; cap-overflow cards are demoted below the
  head in rank order instead of dropped. `GenerationReport` gains
  `shaped_head_by_opponent` alongside the full-emission
  `exposure_by_opponent`.
- Every card carries `tier`: `endorsed` (single best mutual pick per
  cycle, at most 1) / `featured` (next `gen2_featured_count`, default 4)
  / `browse` (all remaining survivors, ranked). Serialized in
  `trade_card_to_dict`. The telemetry sibling records `tier` into its
  `features_json` and ghost-exempts endorsed cards (their D-scope-8 —
  no action on this branch).
- `gen2_centerpiece_top_k` bounds **search breadth** only (documented),
  raised 3 → 5 so deep divergent rosters don't starve the browse tier of
  centerpiece variety (worst-case enumeration ≈ 9.6k combos/pair, well
  under the safety budget).

**3-team scope decision:** 2-team only, per round-2 memo 01's transfer
notes. Scoring is decomposed into directed transfers (`side_gain(in, out,
value_of)`) so a bounded-cycle 3-team layer can bolt on later by gating
and summing the same directed gains — deliberately NOT built now.

**Deliberately deferred** (documented for the ship report):
- Wiring real accept/response stats into the acceptance prior — the
  suggestion-telemetry layer (sibling branch `feat/suggestion-telemetry`)
  owns the data; the pipeline exposes the narrow kwarg + the
  `GenerationReport` return value as its consumption surface. Until
  wired, every counterparty gets the global prior (ordering unchanged).
- Cold-team priority weights (`priority_weights` kwarg) — hook exists and
  is tested-by-construction (neutral default 1.0); the policy that feeds
  it (idle-manager detection) is future work.
- Streaming per-opponent progress uses one callback invocation per
  boarded opponent with the pre-shaping snapshot (same signature as the
  existing engine); final shaping happens at batch end.

## 1. Analytics scope

- [x] **(b) Existing events cover it.** The pipeline is backend-only and
  default-OFF; when enabled it emits through the SAME `/api/trades/generate`
  job the existing engine uses, so the server-fired `trades_generated`
  event and the F1 deck-signal spine (`deck_impressions`/`deck_outcomes`)
  cover serving and outcomes unchanged. Per-suggestion health metrics and
  per-team exposure counts are logged via `GenerationReport` (one JSON
  log line per batch) and returned to the caller for the
  suggestion-telemetry layer (built concurrently on its own branch) to
  persist — this module deliberately owns no tables and no new events.
  New analytics events, if the telemetry thread wants them, are specced
  in THAT thread against the taxonomy.

## 2. Schema & flag scope

- New/changed tables or columns: **none** (deliberate — telemetry sibling
  owns persistence; `GenerationReport` is the hand-off interface).
- New/changed feature flags: `trade_gen.v2`, default **false** →
  registered in `config/features.json`, `backend/feature_flags.py`
  `FLAG_KEYS`, documented in `docs/config-reference.md`. Graduation
  criterion: offline replay / operator league A-B against the incumbent
  engine on accept-rate + health metrics; the flag itself is the
  deploy-free rollback lever.
- New env vars / `model_config` keys: 17 `gen2_*` keys in
  `trade_service._DEFAULT_CFG` (epsilon, band width, consolidation curve
  γ/floor, pool sizes, exposure cap/floor, dedup Jaccard, MESO band/max,
  acceptance-prior strength/global prior, youth age, featured count) —
  all documented in `docs/config-reference.md` § Trade generation
  pipeline v2.

## 3. Test scope (mobile test platform)

- [x] **WAIVED because:** backend-only, default-OFF flag; zero
  user-visible mobile change while dark (flag-off payloads byte-identical
  — asserted by `test_flag_off_never_touches_new_module`). A Maestro
  delta ships with the future flag-flip/client-consumption change, not
  with this dark engine.
- `testID`s added/renamed: none.
- **Capture delta:** none — no visual change.
- Smoke-suite impact: none of the 11 smoke flows change behavior
  (flag off); backend suite green (see below).
- Backend: pytest added — `backend/tests/test_trade_gen_v2.py` (24 tests,
  incl. the direction-change coverage: uncapped default returns all
  survivors + caller-passed limit still truncates; exactly one endorsed
  per cycle with tier ordering consistent with rank; exposure cap/floor
  as head-shaping without truncation; plus the original set —
  flag gating both directions, centerpiece divergence + want/accept
  boards, feasibility gate, dual-board ε incl. tunability, consolidation
  discount catching a junk-stuffed package (with the floor=1.0
  counter-proof), fairness band + configurability, EB acceptance prior
  math + ordering effect, exposure cap/floor + logged counts, dedup rule,
  MESO recipient-board equivalence + distinct shapes, two-sided rationale
  + health metrics, and a 12-team fixture league asserting the
  contender/rebuilder window trade IS found and a dual-board-tempting but
  consensus-lopsided trade is NOT emitted). Fixture parity files
  (`backend/tests/fixtures/flags/*.json`) updated for the new flag key.

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | updated | Trade-card payload: additive optional `rationale` + `meso_variants` + `tier` fields (flag-gated at generation; flag-off payloads byte-identical). No route added/renamed/removed. |
| `living-memory/LLD.md` | updated | New convention: `gen2_*` config namespace + `GenerationReport` as the generation→telemetry hand-off interface; dual-board ε extends #108 to both sides. |
| `docs/architecture.md` | n/a because | no module re-wiring: the new module hangs off the existing `generate_trades` entry point behind a flag, dark by default; wiring doc changes ship with the flag flip. |
| `living-memory/HLD.md` | n/a because | no architecture shift while dark — same entry point, same serving pipeline, no new client or store. |
| `docs/cross-client-invariants.md` | n/a because | no value is shared across clients — no client consumes the new fields yet; shape-label enums graduate to invariants when a client renders them. |
| `docs/glossary.md` | updated | Joint gain, Consolidation discount, MESO variant, Exposure budget, Acceptance prior, Band position. |
| ADR or `DECISIONS.md` entry | n/a because | the non-obvious choices (discount curve, dedup rule, band-as-constraint, 2-team-only with directed-gain decomposition) are documented in the module docstring + this scope block; if the engine graduates to the live path, that flip gets the ADR. |
| `docs/config-reference.md` | updated | Flag section + full `gen2_*` key table. |

## 5. Ship gate declaration

- **Simulator-gate tier:** Tier 4 — none / CI only (backend-only,
  default-OFF flag; no client renders any new field while dark).
  Per the matrix's backend-only dark-change class. **This branch is not
  being pushed/merged by the build agent** (operator instruction); the
  shipping session runs the gate per matrix and writes
  `qa/sim-runs/last-sim-run.json` + the TEST_LEDGER entry at that point.
- Evidence: full backend suite run in the worktree 2026-08-16 (after the
  no-truncation/tier follow-up) — **2888 passed, 1 skipped** (includes
  the 24 trade_gen_v2 tests), zero regressions.
- Operator deviation from the matrix: none.
