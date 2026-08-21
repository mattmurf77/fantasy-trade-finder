# Feature Scope — Counterparty breaker

**Date:** 2026-08-21
**Entry point:** direct operator ask (relayed via the tweet-product-gap-review session; item 3 of the three-plan batch: Receipts · Negative-results memory · Counterparty breaker)
**Builder:** counterparty-breaker planning session (branch `claude/counterparty-breaker-plan`)
**Operator sign-off on waivers:** PENDING — waivers listed in §3/§4 below are surfaced in PLAN.md §9 (decision register) and must get a yes before build. **This scope covers the PLANNED feature; no build starts until the doc suite is operator-approved.**

---

## 1. Analytics scope

- [x] **(b) Existing events cover it** — no new client events in v1.
  - `deck_outcomes.action` (`viewed | like | pass | not_interested | propose | undo`) — the outcome measures. The breaker's effect question ("does naming the counterparty's likely objection change like/propose behavior?") is answered by joining outcomes to the breaker stamp in `deck_impressions.features_json.breaker` (uniform-keys rule, see §2), split by flag state.
  - `trade_pass_reasons` layer-1/layer-2 codes (`database.py:5580-5582`) — the calibration measure. The breaker's top objection is expressed **in the same vocabulary** as the shipped decline-reason codes, so "predicted objection" vs "actual pass reason filed" is a direct join, no new instrumentation.
  - If the PRD lands a tappable "why they'd hesitate" UI element (vs. a plain narrative sentence), that adds a taxonomy row (`breaker_hesitation_expanded` or similar) — **deferred to the PRD**; registering an event and its emitter in the same commit per CLAUDE.md if that variant wins.

## 2. Schema & flag scope

- **New/changed tables or columns: none in v1.** The breaker result rides the card (`fit_diag`-precedent: attribute on the card object → copied into `deck_impressions.features_json` at impression-log time). The `breaker_` table prefix is RESERVED for this feature (coordinated with siblings: `receipts_` = Receipts, `negmem_` = negative-results memory) but v1 claims no tables. Stamp mechanics must respect the `save_deck_impressions` executemany first-row-keys trap (`database.py:5427`; precedent guard `test_impressions_uniform_columns`): the `breaker` key present (null-valued when unscored) on **every** row of a deck. *(Errata 2026-08-21, round-3 review: `save_deck_impressions` is at `database.py:5503` in this checkout, not `:5427`.)*
- **New feature flags** (both default **false**, both in `config/features.json` + `FLAG_KEYS` + `docs/config-reference.md`):
  - `trade.breaker` — compute + stamp only. Dark-measurement first, zero user-visible effect, zero ordering effect. Graduation criterion: stamp coverage ≥99% of served cards with no p95 job-time regression, and the calibration readout (PLAN §6) runs once.
  - `trade.breaker_narrative` — the on-card "their likely hesitation" line (product outcome 2). Requires `trade.breaker`. Graduation criterion: operator TestFlight pass + the A/B readout in PLAN §6.
  - Product outcome 1 (filter/demote) is **v2, not flagged here** — it gets its own scope block if/when the operator elects it (bright-line: it changes deck composition; see PLAN §3 for the interleave-discipline constraint that keeps it out of v1).
- **New `model_config` keys:** `breaker_*` family (severity thresholds per objection class, `breaker_min_severity` for the narrative line, `breaker_ms_budget`). Exact list is LLD territory; every key follows the five-registration rule (`trade_service.py:869-877`) and carries a documented disable value. **Deploy-free rollback lever:** `trade.breaker_narrative → false` (hot reload) kills the user-visible surface; `trade.breaker → false` kills compute entirely; knob levels 0 restore byte-identical behavior with flags on.
- **Env vars: none.**

## 3. Evidence scope

**Status 2026-08-21 (W3 closeout, tip `fdd1683`): every row LANDED except the TestFlight checklist, which is operator-owed and UNRUN.** Counts verified by collection in this checkout, not quoted from a commit message.

- [x] **Unit tests — LANDED: `backend/tests/test_trade_breaker.py`, 67 collected.** Covers the row above name by name: determinism (`test_breaker_deterministic`), vocabulary **and evidence-key** closure against `database.PASS_REASON_LAYER2` by import (`test_breaker_vocabulary_closure`), per-class predicate correctness on the shared fixture (`test_fit_outlook_predicate`, `test_fit_new_weakness_predicate`, `test_fit_duplicate_predicate`, `test_value_giving_one_code_path`, `test_other_player_keep_predicate`, `test_roster_crunch_predicate`), degenerate inputs per §3.10 cell (`test_degenerate_inputs_per_class`), tie-break and vector completeness (`test_top_tiebreak_priority`, `test_objections_vector_complete`), the knob/valuation binding sabotages (`test_breaker_binding_sabotage`, `test_knob_snapshot_frozen_within_job`, `test_stud_tax_pinned_market`), the whole degradation ladder (`test_per_class_exception_contained`, `test_budget_ladder_labeling`, `test_exception_rungs`, `test_rung5_marker_version_pinned`, `test_partner_snapshot_rung1`, `test_bulk_reader_failure_field_level`), the format envelope and shadow (`test_format_envelope`, `test_shadow_run`), and the default-ordering pin (`test_default_knob_ordering`).
  - **Narrative honesty — LANDED in `backend/tests/test_trade_narrative.py` (22 collected in the file, 10 of them new):** `test_hesitation_line_honesty` (missing **or present-but-null** evidence ⇒ `None`, never "None-year-old"; names resolve from evidence ids only, D-053), `test_hesitation_templates_snapshot`, `test_narration_switch_ladder`, `test_narration_whitelist_dark_classes`, `test_narration_floors_and_min_severity`, `test_narration_outlook_margin`, `test_repetition_suppression`, `test_narration_template_error_contained`, `test_tmpl_ver_stamped`.
  - **Seam / serving / serialization — LANDED in `backend/tests/test_breaker_seam.py`, 30 collected:** interleave safety and zero ordering effect (`test_breaker_zero_ordering_effect`, parametrized `bakeoff_group_size ∈ {0, N}` + organic), the D-11 seam-creep grep guard (`test_breaker_inert_seam_creep_guard`), flag-off byte-identity and non-import (`test_flag_off_never_imports_breaker`, `test_flag_off_payload_byte_identical`), the dark-window payload guarantee (`test_breaker_payload_absent_during_dark_window`, `test_breaker_shadow_never_serialized`), the full republish matrix (`test_narrated_payload_reaches_snapshot_all_flag_combos`), and the reserved-unused prefix (`test_no_breaker_tables`).
  - **Stamp uniformity — LANDED in `backend/tests/test_bakeoff_serving.py` (+4 collected rows, 3 functions):** `test_impressions_breaker_uniform_keys` (parametrized ×2, organic **and** bake-off), `test_midjob_flag_flip_no_crash`, `test_flag_off_features_json_carries_no_breaker_key`.
  - Run in this checkout 2026-08-21: the three breaker files together = **119 passed**.
- [x] **Code-walk proof — LANDED: [code-walk.md](code-walk.md).** File:line-cited at tip `fdd1683` across five parts: the seam placement and why order is unaffected (`server.py:6063-6143`, bounded by F9 shaping above and the ghost split below), the stamp path incl. every marker rung (`trade_breaker.py:714-765` + the rung table), the narration gate chain (switches → whitelist → basis → envelope → floors → outlook margin → repetition → template), the dark-window payload guarantee (`server.py:11176-11190` + the mobile gate), and the republish path per flag combination. **Correction to this row as originally written:** the composition site is **not** `trade_narrative.build_narrative` — D-5 kept `build_narrative` untouched, because no client renders `TradeCard.narrative`; the sentence is composed by the additive `trade_narrative.hesitation_line` and delivered as its own payload field.
- [x] **Structural guard — LANDED: `mobile/tests/check-breaker-card.js`, 12 assertions, sabotage-proven.** Run in this checkout: **12 passed, 0 failed**. Pins the element gated on `data.breaker?.sentence` (payload presence IS the gate — the client holds **no** flag read, which is a correction to this row's original wording), no ungated read of the sentence, both testIDs on the gated element, no rendering of `code`/`severity` and no client-side sentence copy, token-only styling (no hex literals, flare dot, radius within spec), optional-chaining null-safety, the optional wire type, and that **no** mobile file references `breaker_shadow`.
- [ ] **Manual TestFlight checklist — AUTHORED, NOT RUN.** [PRD](PRD.md) §8.3, 19 numbered steps (steps 1–4 are the dark-window sub-checklist and may run at P1). Required before `trade.breaker_narrative` graduates; **operator-owed**, needs a build containing the element, which does not exist. Not required for `trade.breaker`. Per D-056 this is the ONLY runtime evidence this feature gets, so **no runtime evidence exists today**. To be logged verbatim in TEST_LEDGER when run.
- [ ] **WAIVED:** none claimed at scope time; none claimed at build.
- `testID`s — **LANDED:** `trade-card.breaker-hesitation` and `trade-card.breaker-hesitation.body` (repo dot idiom; the hyphen form in this scope's original text was illustrative, LLD §9 Q-8). `mobile/scripts/testid-lint.sh` run in this checkout: **OK**.

## 4. Docs scope (MANDATORY — HLD / LLD / API)

**Status 2026-08-21 (W3 closeout, tip `fdd1683`):** every row below is now written. `config-reference` and `data-dictionary` were not in the original table and are added as rows — the 25 knobs and two flags, and the two `features_json` keys, both trip the standing trigger tables.

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | **updated** (wave 2) | trade-card payload block `:338-350` — `trade_card_to_dict` gains the additive optional `breaker` object (`code`, `severity`, `sentence`), documented as **narration-gated** (absent entirely during the dark window); no new routes in v1 |
| `docs/config-reference.md` | **updated** (waves 1–2) | the two flags (`trade.breaker`, `trade.breaker_narrative`) + the 25 `breaker_*` `model_config` knobs with defaults and disable values |
| `living-memory/LLD.md` | **updated** (W3) | new H2 *"Predicting a user's own vocabulary: objection codes, uniform-key stamps, narration-gated payloads (2026-08-21, D-142)"* — vocabulary + producer column, the `features_json` uniform-keys rule with marker-object-never-bare-null, narration-gated payloads, one-job-one-knob-state |
| `docs/architecture.md` | **updated** (W3) | `trade_breaker.py` module row in § Components → Backend, plus a new step 7 in § Request lifecycle (trade card): post-mutation evaluation → stamp → `features_json` copy → narration-gated payload |
| `docs/data-dictionary.md` | **updated** (W3) | § `deck_impressions` — `features_json.breaker` / `.breaker_shadow` documented on the `fit`/`fit_diag` precedent, incl. the marker shape and the readout filters; § `trade_pass_reasons` gains the second-consumer + producer-column note |
| `living-memory/HLD.md` | **updated** (W3) | Flow C gains the evaluation-layer step (generator arms → **breaker evaluation** → presentment → serving) |
| `docs/cross-client-invariants.md` | **updated — recorded as NOT an invariant** (W3) | new § *"Counterparty-breaker objection codes — deliberately NOT a cross-client invariant in v1"*: the sentence is server-composed and rendered verbatim, no client may switch on `code`, payload presence is the gate, web/extension render nothing. The row states what would make it become one |
| `docs/glossary.md` | **updated** (W3) | "Breaker" (with the `draft_board_service` circuit-breaker disambiguation), "Objection (breaker)", "Hesitation line" |
| ADR or `DECISIONS.md` entry | **updated** (W3) | [D-142](../../../living-memory/DECISIONS.md) — objection-vocabulary-equals-decline-taxonomy + v1 stamp/narrative-only (interleave safety; filter/demote is v2) + narration-gated payload privacy. Cites the doc suite rather than restating it |

Shared artifact: `docs/plans/shared/trade-shape-taxonomy.md` (seeded by the Receipts session; this plan cites it and contributes the objection-vocabulary section; changes only by PR touching that file).

## 5. Ship gate declaration

- **CI green:** `backend-tests` + `mobile-typecheck` (+ `check-*.js` suites) + `maestro-testid-lint` on the pushed sha. `FTF_SKIP_SIM_GATE=1` standing posture (D-056), evidence noted.
- **Evidence recorded:** `living-memory/TEST_LEDGER.md` entry at each merge naming what ran and what it proved.
- **TestFlight verification:** required before `trade.breaker_narrative` lights; checklist authored in the PRD.
- **Express lane declared by the operator?** **No — full gates, explicitly** (the assigning brief states "This is NOT express").
- **Change-control:** serving-affecting flips obey the one-engine-change-per-tester-week rule (`docs/plans/trade-engine-accuracy/PLAN.md`) and go through `scripts/set_knob.py` so `model_config_changes` logs them.
