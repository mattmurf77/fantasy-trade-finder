# PRD-build — Fit challenger (implementation contract)

**Date:** 2026-08-20 · **Status:** final build contract — the first doc a coding agent reads.
**Binding order (later wins):** [PRD.md](PRD.md) → [PLAN-v2.md](PLAN-v2.md) (R-1..R-12) →
[HLD.md](HLD.md) (F-1..F-9) → [LLD.md](LLD.md) (§8 rulings R-a..R-j; the closest binding
layer — build to it, this file only indexes it). Review C1–C7/T1–T4:
[../../reviews/2026-08-20-fit-challenger-review.md](../../reviews/2026-08-20-fit-challenger-review.md).
Full gates, no express (PLAN-v2 §6). Scope blocks: [scope.md](scope.md) + the two owed skeletons (LLD §7).

## 1. What ships, one paragraph

A fourth dark trade-idea generator ("fit") joins the bake-off: instead of deleting every
trade the market says you'd lose, it keeps any physically legal idea and gives it two 0–100
scores — how much *you* should like it and how much *they* should — then shows the
best-combined first. It never touches what real users see: it is off by default, and even
when turned on it only logs what it *would* have suggested until the operator flips a second
switch. Alongside it ships the measurement gear to judge it honestly: a log of every knob
change, a weekly readout script, daily tripwires, and a tester protocol — so in a few weeks
the like-rate data, not anyone's hunch, decides whether "fit" earns a real serving slot.

## 2. Work packages

Five packages = the five PRs (PLAN-v2 §3). **Parallel:** PR-M, PR-S, PR-F1 may build
concurrently (see collisions). **Strict sequence:** PR-F1 → PR-F2 → PR-F3; each F-package
branches from freshly fetched `origin/main` after its predecessor merges.

### PR-M — measurement rail (M1+M2+M4+M5) — LLD §5
- **Files:** `backend/database.py` (`model_config_changes` table + index, `model_config.updated_at`
  + `migration_cols` row, `set_config` gains `source` + change-row — LLD §5.1);
  `backend/server.py` (PUT `/api/admin/config/<key>`: optional `source`, response `old_value` — LLD §5.1);
  `scripts/set_knob.py` (new — LLD §5.2, incl. the 5 refusal cases);
  `scripts/bakeoff_readout.sql` (new — LLD §5.3, sections 1–8 incl. all M4 tripwires);
  `docs/plans/trade-engine-accuracy/tester-protocol.md` (new) + `docs/runbook.md` § (M5 — LLD §5.4);
  `backend/tests/test_model_config_log.py` (new — LLD §6.3).
- **Docs in-PR:** config-reference (PUT `source` + change-log note), data-dictionary
  (`updated_at`, `model_config_changes`), api-reference (PUT delta),
  `docs/plans/fit-challenger/scope-measurement.md` filled (LLD §7).
- **Gate:** CI green; `test_model_config_log.py` green; migration additive/idempotent; no knob values change in-PR.
- **Note (inconsistency resolved here):** LLD §6.3's `test_set_config_logs_change` names
  `fit_score_scale`, a key that exists only after PR-F2. In PR-M the test must exercise an
  already-registered live knob; add the fit-key variant in PR-F2.

### PR-S — serving safety net — PLAN-v2 §3, LLD §7
- **Files:** `backend/tests/test_bakeoff_runner.py` (or `test_bakeoff_serving.py`):
  `test_zero_card_arm_deck_still_fills` (S1b — LLD §6.2);
  `docs/plans/fit-challenger/scope-serving.md` (W1 knob table, rollback ladder = HLD §6 rungs 1–5,
  re-ranker-bypass code-walk citing `bakeoff_runner.py:374` + `server.py:5728–5858`,
  operator TestFlight checklist — draft B §7's 8 steps).
- **Gate:** CI green; **no knob values change in-PR** — all flips are post-merge `set_knob.py` writes.

### PR-F1 — knockout module (F1) — LLD §1.1, §1.2, §1.6
- **Files:** `backend/trade_gen_fit.py` (new: docstring/imports, `SCORER_VERSION`,
  `_LEGAL_SHAPES`, `FitReport`, `_kill` chain — order K1 K2 K4 K5 K6 [junk] K7 K3-LAST);
  knob registration ×5 for `fit_r5_mode`, `fit_junk_floor` (LLD §4: `trade_service._DEFAULT_CFG`,
  `database._MODEL_CONFIG_DEFAULTS`, `_PINNED_KNOBS` in `backend/tests/test_bakeoff_arm_a_golden.py`,
  disposition sentence in `docs/plans/three-model-bakeoff/scope-phase2.md`, config-reference row —
  same commit as consumer); `backend/tests/test_trade_gen_fit.py` (knockout rows of LLD §6.1).
- **Tests:** `test_k1_shapes`, `test_k2_byte_identical_to_live_c3`, `test_k3_both_rosters_all_paths`,
  `test_k3_runs_last_in_kill_order`, `test_fit_gate_binding_sabotage` (T1), `test_fit_r5_mode_knob`,
  `test_fit_junk_floor_knob`, `test_diagnostics_keys_complete`.
- **Gate:** CI green; T1 sabotage green; **no bake-off hook** (no `bakeoff_runner.py` change); no K-math diffs under live gates (scope.md §5).

### PR-F2 — enumerator + scorer + M3 (F2+F3+M3) — LLD §1.3–§1.8, §1.10–§1.11, §3.2–§3.3
- **Files:** `backend/trade_gen_fit.py` (entry point, `_build_pool`, `_enumerate_pair`,
  `_score`/`_surplus`/lenses/`_bucket`, ranker, TradeCard construction per §1.10, `stamp_fit_diag`);
  `backend/server.py` (M3 stamp after `:5682` — LLD §3.2; two unconditional `features` keys — LLD §3.3);
  knob registration ×5 for the 13 pool/scorer keys (`fit_score_scale`, `fit_score_even`, `fit_w_*` ×3,
  `fit_pool_*` ×4, `fit_max_packages_per_pair`, `fit_expand_from`, `fit_min_them`, `fit_min_aggregate`);
  tests (scorer rows of LLD §6.1 + `test_fit_diag_inert`, `test_impressions_uniform_columns` from §6.2).
- **Gate:** CI green; fixture scores frozen with pinned literal inputs (HANDOVER trap 7);
  `test_fit_score_curve_pinned` green at 1e-6 vs LLD §1.7 computed table (not PLAN-v2's rounded 88.4);
  `test_fit_lens_provenance_raw` green; `test_fit_diag_inert` green.

### PR-F3 — filters, arm wiring, serve-bit (F4+F5+F5b) — LLD §1.9, §2, §3.1, §3.4
- **Files:** `backend/trade_gen_fit.py` (§1.9 post-score filters, order pinned);
  `backend/bakeoff_runner.py` (LLD §2 verbatim: `ARM_FIT`, `ALL_ARMS`+`GENERATION_ORDER` only —
  `ARMS` and `ENGINE_ARMS` untouched; `arm_roster` entry; `serve_fit()`; `_fit_diag_tl` +
  `last_fit_diagnostics`; `gen_fit_cards`; `run_bakeoff` additive `gen_fit=None` kwarg, dispatch,
  diag drain, `fairness_threshold=None`, `serving_roster` on **both** draft paths);
  `backend/server.py` (callsite binding at `:5669` — LLD §3.1; `trade_card_to_dict` additive `fit` — LLD §3.4);
  knob registration ×5 for `bakeoff_include_fit`, `bakeoff_serve_fit` (disposition B);
  tests (remaining LLD §6.1 + §6.2 rows).
- **Gate:** CI green; knob-inventory guard green with **all 17** names + sentences; organic
  byte-identical proof; W0 dry-run TEST_LEDGER entry recorded; remaining docs rows (§7 below);
  **operator yes before `bakeoff_include_fit=1` anywhere prod-like** (scope.md §5).

### File-collision rules
- `backend/trade_gen_fit.py`, the 4 knob-registration files, and `docs/config-reference.md`
  are touched by all three F-packages — **never build two F-packages concurrently.**
- `backend/database.py` is touched by PR-M and PR-F1; `backend/server.py` by PR-M, PR-F2, PR-F3.
  PR-M merges first (PLAN-v2 §2); if PR-F1 builds concurrently with PR-M it must not touch
  `set_config`/the table DDL, and rebases before merge.
- `backend/bakeoff_runner.py` is PR-F3-only. PR-S touches tests/docs only — collision-free.

## 3. Acceptance criteria (pass/fail, reviewer-executable)

Per package: the gate lines above, plus the full LLD §6 test list — **the test names in LLD
§6.1–§6.3 are the spec** (PLAN-v2 F6). Overall, from operator PRD §11:
1. `trade.bakeoff` off ⇒ organic decks byte-identical; `trade_gen_fit` never in `sys.modules`.
2. Boarded fixture pair yields cards live arm B kills on `rv ≥ gv` / dual surplus, with
   `fit.them` populated (possibly < 50) — `test_negative_surplus_scores`.
3. Unranked partner ⇒ `lenses.them.board = null`, them-score = L3 only — `test_unranked_partner_l3_only`.
4. K2: 1-for-1 2026-vs-2027 1st dead; two late 2nds for a 1st lives — `test_k2_byte_identical_to_live_c3`.
5. K1: startable, non-R1/R2 3-for-1 scores — `test_k1_shapes` + `test_k3_both_rosters_all_paths`.
6. Dry-run diagnostics: `enumerated` ≫ live prune size on the fixture league; ms recorded.

W0 dry-run contract (PLAN-v2 §5 W0, blocking PR-F3's ledger entry): offline run on replay
boards for league `1312140920132497408` + fixture league + one 16-team SF roster; full LLD
§1.2 diagnostic set reported (incl. `killed[K7]`, `top_q_pick_share`, `top_q_junk_share`,
`one_sided_pct`, bucket mix); fixture ms recorded → operator sets the fail bar; R-8 volume
check computed (fit vs 1.2× arm B distinct ideas); baseline M2 readout snapshotted.

Not accepted (PRD §11): serving fit to users, dualizing R5, PPG/impact in the scorer.

## 4. Operator decision register

Each row: question · default if unanswered · where flagged.

| # | Decision | Default shipped | Flagged at |
|---|---|---|---|
| 1 | K1 literal shape list excludes 2-2 and 3-3 — intended, or widen? | Literal PRD §3 list ships (`_LEGAL_SHAPES`); 2-2/3-3 are kills. Widening later = one frozenset edit + test row | LLD §8 R-b |
| 2 | `trade.outlook_direction` flip at W0 — confirm or decline? | Not flipped; nothing else moves | PLAN-v2 R-10 |
| 3 | S0 volume check: fit ≤ 1.2× arm B distinct ideas at dry run — roster anyway? | Build pauses at the W0 readout for an operator call; no auto-kill, no auto-roster | PLAN-v2 R-8 |
| 4 | Roster fit after the dry run (`bakeoff_include_fit=1`) | Stays 0. PR-F3 merges but the arm never runs until the operator's yes | scope.md §5; PLAN-v2 PR-F3 gate |
| 5 | Generation-ms fail bar, set from the W0 dry-run number | No bar ⇒ decision 4 stays blocked (bar is a precondition of rostering) | scope.md §6; PRD §11 |
| 6 | F7 dual-R5: flip `fit_r5_mode=0` at verdict? (`killed[K7]` is the evidence) | 1 (kill, live-as-written); flip only as a pre-registered iterate action | PRD §12/F7; PLAN-v2 W5–W7; LLD §8 R-d |
| 7 | C4 centerpiece cap on for this arm? | On (`deck_headliner_cap`, live value) | PRD §12 open; scope.md §6 |
| 8 | Serving-window transitions W1/W3/W4 (re-light, dark roster, k=2 round) | None flip automatically; each is an operator `set_knob.py` write per the schedule | PLAN-v2 §5 |
| 9 | Mobile structural-guard waiver (no client render of `fit` in v1) | Waived per scope.md §3 — surfaced here per the feature-gate rule that silence is not a waiver | scope.md §3 |

## 5. Out of scope, restated

From PRD §1/§3/§8/§11 + PLAN-v2/LLD punts: organic serving (module never imported by
`trade_service`; no `trade_gen.v2` coupling); F7 dual-R5 (knob pre-wired, math unauthorized —
LLD R-d); likes-you injector; PPG/impact in the scorer; client rendering of `fit` (no
mobile/web ticket; additive JSON only); landability-challenger knobs (`_cfg_override`
forbidden on this arm); automated config-snapshot-diff tooling (manual per runbook — LLD
Punt-1); SQLite translations of the readout SQL (comment block only — LLD Punt-3);
module-side per-opponent cap (`max_per_opponent=None` — LLD R-g); a general
`bakeoff_serve_<arm>` mechanism (fit-only bit — HLD §5e).

## 6. Risk register for the build itself

| Trap | One line | Guarding test |
|---|---|---|
| T1 binding | Importing predicates by name binds by value; knob/monkeypatch changes silently don't propagate — import the module (`ts.overpay_ok(...)`) | `test_fit_gate_binding_sabotage` |
| T2 executemany | `save_deck_impressions` compiles columns from the first row; `fit`/`fit_diag` must ride inside `features_json`, keys present on every row | `test_impressions_uniform_columns` |
| ENGINE_ARMS (F-7) | Adding fit to `ENGINE_ARMS` gives it basis-narrowed groups + divergence fairness floors on the wrong `basis` meaning — don't | `test_fit_fairness_threshold_none` |
| Two draft paths (F-6) | Serve-bit applied only to `compose_deck` leaks fit into every real deck, because W1 runs `group_size=0` → `team_draft` | `test_serve_fit_bit_excludes_from_draft` (parametrized group_size ∈ {0, 10}) |
| `_MODEL_CONFIG_DEFAULTS` (F-1) | `_DEFAULT_CFG` alone leaves `set_config` KeyError-ing → whole rollback ladder is theater; five registrations per key, same commit | `test_set_config_unknown_key_still_raises` + knob-inventory guard |
| `ARMS` fixture (F-8) | `ARMS` is pinned by Phase-3 tests; fit goes in `ALL_ARMS`/`GENERATION_ORDER` only | existing Phase-3 tests |
| Provenance (T3) | Any lens reading `shrunk_elo` re-imports audit bug-3 asymmetry; raw boards only, `_shrink_user_elo` never called | `test_fit_lens_provenance_raw` |
| Hand-rounded curve (F-5) | Pinning PLAN-v2's rounded 88.4/11.6 bakes a wrong golden; pin LLD §1.7 computed values | `test_fit_score_curve_pinned` (1e-6) |
| Kill-order drift | Reordering the K-chain silently reattributes `killed[]` counters across runs | `test_k3_runs_last_in_kill_order` |
| Runner API (F-3) | `run_bakeoff` gains `gen_fit` as additive keyword default `None` — positional insertion breaks 6 existing callsites | `test_run_bakeoff_gen_fit_optional` |
| Prefs as kills | Filtering untouchables/not-interested before scoring recreates the search-shrink the arm exists to delete | `test_untouchable_enumerated_then_filtered` |

## 7. Definition of done

- CI green on every PR: `pytest backend/tests`, `tsc --noEmit`, `mobile/scripts/testid-lint.sh`
  (`FTF_SKIP_SIM_GATE=1` standing posture, evidence noted).
- Knob-inventory guard (`test_no_generation_knob_was_added_without_an_arm_a_decision`) green
  with all **17** keys in `_PINNED_KNOBS` + 17 disposition sentences in scope-phase2.md.
- Organic byte-identical proof on record: grep code-walk + `test_organic_never_imports_fit` +
  flag-off fixture run (PR-F3 gate).
- W0 dry-run TEST_LEDGER entry recorded (§3 contract), ms number handed to the operator.
- Docs rows landed: config-reference (17 knob rows + PUT delta), data-dictionary (M1 items +
  `arms_json['fit']` + `features_json.fit`/`.fit_diag` + `surplus_margin` fit-meaning note),
  api-reference (`fit` object + PUT `source`/`old_value`), scope-measurement.md,
  scope-serving.md, three-model-bakeoff PLAN addendum, cross-client-invariants n/a note,
  2 ADRs (PLAN-v2 §7).
- Living-memory written: CHANGELOG entry per merged PR; DECISIONS (grep max-ID first);
  TEST_LEDGER (F6 evidence + dry run); NEXT updated; `living-memory/LLD.md` conventions
  (prefs filter after score; fit analysis keys on `fit.boards`, never `basis`; five
  registrations per knob); HANDOFF overwritten if stopping mid-wave.
