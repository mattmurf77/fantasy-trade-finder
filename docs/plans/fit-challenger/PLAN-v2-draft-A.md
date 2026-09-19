# PLAN v2 — draft A (build-first): fit arm + serving re-light + measurement rail

**Date:** 2026-08-20
**Stance:** build-first. Ship working software to testers in independently mergeable cuts,
each with a one-knob rollback. The rival draft argues from risk/measurement-first; this
draft's position is that the measurement the operator needs **does not exist until arms are
served**, so serving is the first deliverable, not the last gate.
**Inputs (all read):** [PRD.md](PRD.md) (operator-ruled; §3 knockouts CLOSED),
[PLAN.md](PLAN.md), [scope.md](scope.md),
[../../reviews/2026-08-20-fit-challenger-review.md](../../reviews/2026-08-20-fit-challenger-review.md) (C1–C7, T1–T4),
[../trade-engine-accuracy/PLAN.md](../trade-engine-accuracy/PLAN.md) (Phase 0–3 + appendix prod numbers),
[../../reviews/2026-08-19-armb-audit-consolidated.md](../../reviews/2026-08-19-armb-audit-consolidated.md),
`backend/bakeoff_runner.py` (docstring, `serve_interleaved()`, `arm_roster()`, `group_size()`, `deck_limit()`),
[../matchmaking-engine/HANDOVER.md](../matchmaking-engine/HANDOVER.md) §6, root `CLAUDE.md`.

---

## 0. The build-first argument, stated once

Three facts from the accuracy plan's appendix (2026-08-20 prod pull; cited, not re-derived):

1. `model_arm ∈ {current, NULL}` on **all 9,111 impressions ever**. Arms C and D have
   generated and logged for weeks and produced **zero user decisions**, because
   `bakeoff_serve_interleaved = 0`.
2. `deck_outcomes.action = 'propose'` has fired **zero times ever** — the funnel has no bottom.
3. The one day serving was lit (2026-08-18) it was reverted for a deck-shrink defect whose
   cause (lane quotas + leave-short) is understood and knob-fixable.

Every week the fit arm is built but not served is a week the bake-off's question stays
unanswerable. So this plan runs **two parallel tracks**: Track 1 re-lights serving for the
arms that already exist (B/C/D) in week 1, with the measurement rail underneath it; Track 2
builds `fit` on the PRD's F1–F6 and rosters it into an already-serving bake-off the moment
its dry run is green. Serving is not held hostage to the fit build, and the fit build is not
held hostage to a measurement philosophy debate — the readout lands before the first Friday
it is needed.

---

## 1. Objective + success criteria

**Objective.** Testers in scoped leagues receive interleaved decks from arms `current`,
`challenger`, `gen_v2`, and (once green) `fit`; every card carries `model_arm`; every knob
change is logged; the weekly readout compares arms on the bucketed co-primary metrics.
Organic serving stays arm B throughout; `trade_gen.v2` stays false; `_generate_trades_impl`
untouched.

**Success criteria (measurable, dated from merge of PR-S):**

| # | Criterion | Bar | Baseline today |
|---|---|---|---|
| SC1 | First non-`current` decision row in prod | ≥1 within 3 days of Stage 1 | 0 ever |
| SC2 | Served deck size under interleave | median ≥ 24 cards (dark median 26.5) | 10-card shrink caused the 08-18 revert |
| SC3 | `fit` rostered and producing decisions | within 2 weeks of PR-F1 merge | arm does not exist |
| SC4 | `bakeoff_runs.arms_json[fit].diagnostics` populated per PRD §7 schema | first rostered run | — |
| SC5 | Knob attributability | 100% of `model_config` changes after PR-M1 have a log row | `model_config` has no `updated_at` (verified `backend/database.py:1489`) |
| SC6 | One clean Friday readout | ≥300 decided cards pooled in a tester week (accuracy PLAN Phase 2 power math: 10 testers × ~40) | ~200/4 days peak, 5 users |
| SC7 | Job budget | p95 bake-off job ms < `_JOB_HARD_TIMEOUT` (60s) with 4 arms | 7.5s at 3 arms, boarded league |
| SC8 | PRD §11 acceptance items | all pass in tests/dry run | — |
| SC9 | Guardrail | pooled like-rate on interleaved decks not < 50% of arm-B dark baseline for 2 consecutive readouts | 22.4% consensus / 5.7% divergence (n=35, directional) |

SC9 is deliberately a **guardrail, not a verdict** — per C3, pooled like-rate is biased
toward arm B by construction.

---

## 2. Workstreams and tickets

Three workstreams. F-tickets are the PRD's, kept intact (estimates PRD §8); S/M tickets are
the serving + measurement additions this plan owes. Owners are repo role skills.

### Workstream A — measurement rail (Track 1, first)

| ID | Ticket | Owner | Est | Depends |
|---|---|---|---:|---|
| **M1** | Knob-change log: add `model_config.updated_at` + new `model_config_log` table (`key, old_value, new_value, changed_at, source`) in `backend/database.py`; funnel every write path (locate the admin route/script surface first — knob writes today may be raw SQL) through one helper that stamps both; add `scripts/set_knob.py` as the blessed CLI so operator flips are logged with `source='operator'`. Additive migration, `INSERT OR IGNORE` seed untouched. | eng-backend | 0.5d | — |
| **M2** | Bucketed readout script `scripts/bakeoff_readout.py` (repo-tracked, runnable against prod read-only posture): like-on-viewed by `model_arm`; for `fit` cards, like-rate by presentment bucket with **`both_high`+`mixed` co-primary**; decline-reason mix per arm (`value_giving` share is the second co-primary, 40% baseline); position curve; `propose` count; pooled like-rate printed last, labelled GUARDRAIL. Encodes C4: **never splits `basis` across arms** (fit's `basis` is data-availability, arm B's is generator path). | an-experiment (design) + eng-backend (code) | 1d | M1 (log rows feed the change-annotation header) |
| **M3** | Weekly tester cadence doc: adopt accuracy PLAN Phase 2 verbatim (Monday one engine change max, ≥40 decided cards/tester, always pick a decline reason, ≥1 real send attempt; Friday readout = run M2). Lands as `docs/plans/trade-engine-accuracy/tester-protocol.md` + a `docs/runbook.md` §. Tester onboarding requirements (≥100 matchup votes, declared outlook, 2 leagues with 3+ boards) copied in as the input-supply checklist. | ops-support + an-experiment | 0.25d | — |

### Workstream B — serving re-light (Track 1)

| ID | Ticket | Owner | Est | Depends |
|---|---|---|---:|---|
| **S1** | Re-light readiness: (a) confirm `trade.bakeoff` scope covers tester leagues only — if it is global-on, add allowlist gating via the `config/tester_allowlist.json` precedent (small code change; check first, don't assume); (b) structural test in `backend/tests/test_bakeoff_serving.py`: with `bakeoff_group_size = 0` and an arm that yields zero cards, the served deck still fills to `deck_limit` from the remaining arms (the exact 08-18 failure, inverted into a regression test); (c) code-walk citation that `bypass_rerankers()` covers every reordering layer (HANDOVER trap 5 — a contaminated run is discarded, not caveated). | eng-backend + eng-qa | 0.5d | — |
| **S2** | Stage flips themselves (config, no deploy — see §4 for exact values). Every flip goes through `scripts/set_knob.py` so the serving re-light is itself the first logged knob change. | ops-release | 0.1d | M1, S1 |
| **S3** | Manual TestFlight checklist for Stage 1 (D-056: the only runtime evidence mobile gets): deck loads and fills to ~30; cards swipe; decline-reason sheet works; no duplicate cards; attempt one real propose (G1 has never fired). Operator runs it in their own league within an hour of the flip. | eng-qa (author) + operator (run) | 0.25d | S2 |

### Workstream C — the fit arm (Track 2, PRD F1–F6 + review deltas)

| ID | Ticket | Owner | Est | Depends | Deltas vs PRD (all traceable to C/T rows, §5) |
|---|---|---|---:|---|---|
| **F1** | Knockout module wrapping live K1–K7 | eng-backend | 1d | — | T1: import the **module** (`from . import trade_service as ts; ts.overpay_ok(...)`), never bind by value. C2: add `fit_r5_mode` knob (default 1 = kill, live K7; 0 = score into viewer lens) — pre-wired, default keeps the operator-CLOSED ruling; **no K-math changes**. C6: evaluate K3 (`_feasible_after`) **last** in the kill order despite its name — it is the expensive predicate. |
| **F2** | Enumerator: union pool, 1-for-1 then expand, caps, `enumerated`/`killed[K1..K7]`/`scored` counters | eng-backend | 2d | F1 | C6: cap enforced before any real-league run (PLAN.md binding note 4). |
| **F3** | Dual 0–100 scorer + `fit` payload + aggregate sort | eng-backend | 1.5d | F2 | C7a: fix the tanh comment (scale 400 ⇒ score(400) ≈ 88, not ~84; keep 400, fix the words) and pin the curve with a value-table test. C7c: tie-break unranked-pair cards (aggregate ≈ 100 by construction) by consensus fairness; document in module docstring. T3: pin lens provenance **in writing** — each lens names which board object it reads (raw member boards + seed; the fit arm never touches `shrunk_elo`) and a test asserts it. |
| **F4** | Post-score preference filters + R4 + C4/C4b | eng-backend | 0.5d | F3 | C5: pre-wire `fit_junk_floor` knob (default 0 = off) so the junk-flood response is a knob flip, not a deploy. |
| **F5** | Bake-off arm `fit`: roster entry behind `bakeoff_include_fit` (default 0), diagnostics onto `bakeoff_runs.arms_json[fit]` | eng-backend | 1d | F3 | C1: this arm lands into an **already-serving** interleave (Track 1), so rostering = serving. C4: stamp `basis` per PRD §7 (operator-ruled) **and** duplicate the value under `features_json.fit_data_basis`, with the loud analytics note in M2. T2: every impression row writes every column (`executemany` compiles from the first row's keys — write nulls, never omit). Handle both composition-on (`fit` = one group, like `gen_v2`) and composition-off paths. |
| **F6** | Tests (`backend/tests/test_trade_gen_fit.py`) | eng-qa + eng-backend | 1d | F1–F4 | Named suite in §6. Includes the T1 sabotage test and the C7b assertion. |
| **F7** | Dualize R5 | — | — | operator | Unchanged: not v1. C2's `fit_r5_mode` + prominent `killed[K7]` in the dry run make F7 a knob flip with evidence, not a new build. |

**Knob hygiene (T4, applies to every C-workstream PR that adds a key):** all `fit_*` keys +
`bakeoff_include_fit` land in `trade_service._DEFAULT_CFG` (the `gen2_*` precedent), get added
to `_PINNED_KNOBS` in `backend/tests/test_bakeoff_arm_a_golden.py`, and get their disposition
sentence in `docs/plans/three-model-bakeoff/scope-phase2.md` in the **same commit**:
*"generation knobs for a module (`trade_gen_fit.py`) arm A never calls — excluded from
`MODEL_A_PROFILE`, D-095 precedent."* The guard fails BY NAME otherwise; budget it into each
PR, not as cleanup.

**Total:** ~9.6 engineer-days. Tracks run in parallel: Track 1 ships in week 1 (~1.6d),
Track 2 lands over ~1.5–2 weeks.

---

## 3. PR / merge sequence

The PRD's suggested 3-PR shape is **kept intact as PR-F1..F3** — it is the right partition
of the fit build. Amendment: **two rail PRs are prepended and merge first**, because they are
independent of the fit build, they are what makes any fit measurement attributable, and they
start producing per-arm decisions (the scarcest resource in this program) while F2 is still
in review. That is the whole build-first sequencing claim: nothing in PR-S/PR-M waits on
`fit`, so making them wait would be pure calendar loss.

| PR | Contains | Merge gate (all PRs also: CI green — `pytest backend/tests`, `tsc --noEmit`, testid-lint) |
|---|---|---|
| **PR-M** | M1 (schema + log helper + `scripts/set_knob.py`) + M2 readout script + M3 docs | new `test_model_config_log.py` green; migration additive (existing rows untouched); `docs/data-dictionary.md` + `docs/config-reference.md` rows updated in-PR |
| **PR-S** | S1 (scope check/allowlist if needed, no-shrink regression test, bypass code-walk) + S3 checklist doc | `test_bakeoff_serving.py` green incl. the new zero-card-arm test; code-walk committed; **no knob values change in this PR** — flips are config, post-merge, logged |
| **PR-F1** | F1 + F6 skeleton (knockout unit tests only) + T4 pinning for `fit_r5_mode` and any F1 keys | knockout tests green; no bake-off hook; T1 sabotage test green |
| **PR-F2** | F2 + F3 + F6 scorer tests + T4 pinning for pool/scorer keys | fixture pair scores frozen (golden-style, inputs pinned per HANDOVER trap 7); curve value-table green; provenance test green |
| **PR-F3** | F4 + F5 + dry-run TEST_LEDGER entry + T4 pinning for `bakeoff_include_fit`, `fit_junk_floor` | dry run recorded (§6); organic byte-identical proof (grep test + fixture generate with `trade.bakeoff` off); operator yes on rostering |

Ordering: PR-M → PR-S (S2 flips after both) ∥ PR-F1 → PR-F2 → PR-F3. PR-M before PR-S so
the re-light flip is logged. PR-F1..F3 are independently mergeable against `main` at any
time; none touches serving config. Every PR branches from freshly fetched `origin/main`
(repo convention — concurrent sessions).

---

## 4. Serving rollout: dark → interleave (B/C/D) → +fit → cadence

All transitions are `model_config` writes via `scripts/set_knob.py` (logged). No stage
requires a deploy; every rollback is one knob, seconds.

### Stage 0 — today (dark)

State: `trade.bakeoff` on, `bakeoff_serve_interleaved = 0`, roster `(current, challenger, gen_v2)`,
79 runs banked. Action: merge PR-M + PR-S; capture the pre-flip readout with M2 as the
baseline snapshot.

### Stage 1 — re-light interleave for tester leagues, arms B/C/D (week 1)

Exact knob values:

| Knob | Value | Why |
|---|---|---|
| `bakeoff_serve_interleaved` | **1** | the re-light |
| `bakeoff_group_size` | **0** | kills the composition layer — plain per-arm team draft; an empty arm contributes nothing and the deck fills from the rest. This is the **structural** fix for the 08-18 shrink (lane quotas + leave-short + arm-C forfeits vanished 20 of 30 slots). The accuracy PLAN 1.1 offers `bakeoff_group_value_slots = bakeoff_group_size` as the alternative; we take `group_size = 0` because it removes the entire failure class (group-level shortfall included — arm C still yields zero cards in 12 of 18 non-boarded-league runs), not just the lane half |
| `bakeoff_deck_limit` | **30** | unchanged cap |
| `bakeoff_include_challenger` / `_gen_v2` | **1** (unchanged) | operator wants the multi-model variety; arm C's forfeits are data, not a reason to bench it |

Prerequisite check (S1a): `trade.bakeoff` scope = tester leagues only.

Verification (within 3 days): SC1 (first `challenger`/`gen_v2` decision), SC2 (deck ≥ 24
median, from `bakeoff_runs` + impressions), zero re-ranker contamination
(`bypass_rerankers()` code-walk already banked; any run with re-rankers live is discarded),
S3 TestFlight checklist run by operator.

**Rollback:** `bakeoff_serve_interleaved = 0`. Testers drop back to arm-B decks on next
refresh. Cost of a failed stage: one tester-day of odd decks.

**Trade-off accepted:** `group_size = 0` turns off lane-quota telemetry (`groups_json`
pool/short per lane). Defense in §8 R2.

### Stage 2 — roster `fit` (after PR-F3 + green dry run)

Exact knob values:

| Knob | Value | Why |
|---|---|---|
| `bakeoff_include_fit` | **1** | rosters the arm; with Stage 1 live this **is** serving |
| `fit_max_packages_per_pair` | **5,000** first, raise toward 20,000 after ms verified | C6: conservative first roster; the 60s `_JOB_HARD_TIMEOUT` is the backstop, the roster knob the relief valve |
| all other `fit_*` | PRD §9 defaults; `fit_min_them = 0`, `fit_min_aggregate = 0` | PRD binding — do not recreate `rv ≥ gv` |

Canary: the operator flips the knob and immediately refreshes their **own** deck (the
operator is a tester); reads job ms, `arms_json[fit].diagnostics` (`enumerated`, `killed[K1..K7]`
with K7 prominent per C2, `one_sided_pct`, `both_high_pct`/`mixed_pct`, pick-share and
junk-share of top-quartile-aggregate cards per C5) same hour; TEST_LEDGER entry. Other
testers pick up `fit` cards on their next scheduled job — hours of exposure lag is the canary
window.

**Rollback:** `bakeoff_include_fit = 0` (arm out of roster and serving). Second-level:
`bakeoff_serve_interleaved = 0` (all-dark). Third-level (junk flood, C5): `fit_junk_floor > 0`
knob, no deploy.

**Deliberately skipped: a prod dark-soak stage for `fit`.** With Stage 1 live, roster
membership = serving; a dark soak would require re-darkening all arms, sacrificing the
decision stream Track 1 exists to start. The fixture dry run + operator canary + 60s timeout
+ one-knob rollback replace it. §8 R3 defends this.

### Stage 3 — weekly cadence (steady state)

M3 protocol: Monday ≤1 engine-affecting change (logged via M1; accuracy PLAN Phase 3 queue
owns the candidates — `user_elo_shrink`, soft R5, etc. — those are arm-B levers outside this
plan), Friday M2 readout. `fit`'s graduation question (does it earn the serving path?) is
answered by SC6-grade readouts on C3's co-primaries, not by any single week.

---

## 5. C1–C7 / T1–T4 coverage

| ID | One-line concern | Addressed by | Where |
|---|---|---|---|
| C1 | Serving is where arms die; couple F5 to interleave re-light with the lane-quota fix | Whole of Workstream B; Stage 1 knobs (`serve_interleaved=1`, `group_size=0`); F5 lands into a live interleave | §2B, §4 |
| C2 | K7 contradicts the thesis; pre-wire deploy-free demotion | `fit_r5_mode` knob in F1 (default 1 = kill, ruling intact); `killed[K7]` prominent in dry run + M2 readout | §2C F1, §4 Stage 2 |
| C3 | Pooled like-rate misreads the arm | M2 co-primaries = like-rate on `both_high`+`mixed` + `value_giving` decline share; pooled printed as GUARDRAIL (SC9) | §2A M2, §1 |
| C4 | `basis` overloaded across arms | Keep PRD's stamp (operator-ruled) + duplicate as `features_json.fit_data_basis`; M2 never splits `basis` across arms; loud note in analytics docs + LLD | §2C F5, §2A M2, §7 |
| C5 | Junk/pick flooding returns through the open door | Dry run + Stage-2 canary report pick-share and junk-share of top-quartile cards **before** wider exposure; `fit_junk_floor` pre-wired default-off in F4 | §2C F4, §4 Stage 2 |
| C6 | Job budget at 4 arms | K3 evaluated last in kill order (F1); `fit_max_packages_per_pair` at 5,000 first roster; dry-run ms bar is the scope §6 gate; roster knob is the relief valve; SC7 | §2C F1, §4 Stage 2 |
| C7a | tanh comment wrong (score(400) ≈ 88) | Fix comment, keep scale 400; curve pinned by value-table test `test_fit_score_curve_values` | §2C F3, §6 |
| C7b | 0–200 `composite_score` must never be compared across arms as magnitude | Code-walk: team draft consumes per-arm **ranked lists** (rank-based, `bakeoff_runner.py` docstring); F6 grep-assertion that no serving-path consumer compares `composite_score` across arms; M2 never aggregates it | §2C F6, §6 |
| C7c | Unranked-pair aggregate ≈ 100 always | Tie-break unranked-pair cards by consensus fairness in F3; documented in module docstring; tested | §2C F3, §6 |
| T1 | Import-time binding makes wrapped gates silent no-ops | F1 imports the module, never the name; sabotage test monkeypatches `ts.overpay_ok` and asserts fit behavior changes (HANDOVER trap 8 style: prove it works, not that its text exists) | §2C F1, §6 |
| T2 | `executemany` compiles from first row's keys | F5: every impression row writes every column, nulls included; test asserts key-set parity across a mixed-arm deck | §2C F5, §6 |
| T3 | Lens provenance (raw vs shrunk) must be pinned in writing | F3 docstring names the board object per lens (raw member boards + seed; never `shrunk_elo`); `test_fit_lens_provenance` asserts it | §2C F3, §6 |
| T4 | Knob-inventory guard fails BY NAME on any `_DEFAULT_CFG` key | Every PR adding a `fit_*` key updates `_PINNED_KNOBS` + writes the disposition sentence in `three-model-bakeoff/scope-phase2.md` in the same commit (D-095 precedent wording) | §2C knob-hygiene note, §3 |

---

## 6. Evidence plan (D-056: no simulator; structural + code-walk + TestFlight checklist)

Backend-only build, so evidence is pytest + code-walk + the operator checklist for the one
tester-visible change (deck composition under interleave).

**Unit/structural tests** (`backend/tests/test_trade_gen_fit.py` unless noted):

| Test | Proves |
|---|---|
| `test_k1_legal_shapes` / `test_k1_kills_4_plus_and_3_for_0` | K1 incl. 3-for-1 widened shapes |
| `test_k2_byte_identical_to_live_c3` | shared fixture: 2026-1st-for-2027-1st dead; two-late-2nds-for-a-1st lives |
| `test_k3_kills_unstartable_both_sides` | dual `_feasible_after` on every path |
| `test_k3_runs_last_in_kill_order` | C6 ordering (assert via kill-counter short-circuit on a fixture where K4 also fails) |
| `test_negative_surplus_scores_not_killed` | the volume unlock: them < 50, card lives |
| `test_unranked_partner_is_l3_only` | `lenses.them.board = null`, weights renormalized |
| `test_untouchable_enumerated_then_filtered` | prefs filter post-score, never shrink the search (PRD §6 ruling) |
| `test_pool_cap_respected` | `enumerated ≤ fit_max_packages_per_pair` |
| `test_fit_score_curve_values` | C7a value table pins the tanh curve |
| `test_unranked_pair_tiebreak_consensus_fairness` | C7c |
| `test_fit_lens_provenance` | T3 |
| `test_live_predicate_sabotage` | T1: monkeypatch `ts.overpay_ok` → fit output changes |
| `test_fit_rows_write_every_column` (in `test_bakeoff_serving.py`) | T2 |
| `test_organic_never_imports_fit` | grep-style forbidden-import on the organic branch + fixture generate with `trade.bakeoff` off is byte-identical (PRD §11) |
| `test_zero_card_arm_deck_still_fills` (in `test_bakeoff_serving.py`) | the 08-18 shrink, inverted into a regression test (S1b) |
| `test_model_config_log.py` | M1: write path stamps `updated_at` + log row |

**Code-walk proofs** (committed with their PRs): `_generate_trades_impl` never references
`trade_gen_fit`; `bypass_rerankers()` covers all reordering layers; team draft is rank-based
(C7b).

**Dry run** (gate for PR-F3 merge → Stage 2): fixture league + one 16-team SF roster (PRD
§10), arm off-roster then on; TEST_LEDGER records ms, `enumerated` vs arm-B prune size,
`one_sided_pct`, bucket mix, pick-share/junk-share of top-quartile cards; operator sets the
ms fail bar from these numbers (scope §6 open item).

**Manual TestFlight checklist** (S3, Stage 1 + repeated at Stage 2): deck loads and fills
(~30 cards); swipe both directions; decline-reason sheet; no duplicates; one real propose
attempt (G1 exercise). Runtime proof for mobile exists nowhere else under D-056.

**TEST_LEDGER entries owed:** per PR merge (suite counts), per dry run, per stage flip.

---

## 7. Docs + living-memory updates owed

| Doc | Update | With PR |
|---|---|---|
| `docs/config-reference.md` | all `fit_*` knobs, `fit_r5_mode`, `fit_junk_floor`, `bakeoff_include_fit`; note the Stage-1 serving values | PR-F1..F3, PR-M |
| `docs/data-dictionary.md` | `model_config.updated_at`, `model_config_log`, `arms_json[fit].diagnostics` keys | PR-M, PR-F3 |
| `docs/api-reference.md` | additive `fit` object on TradeCard (bake-off only) | PR-F2 |
| `docs/plans/three-model-bakeoff/PLAN.md` | addendum: arm `fit`; serving Stage-1 config | PR-F3 |
| `docs/plans/three-model-bakeoff/scope-phase2.md` | T4 disposition sentences per knob | each knob's PR |
| `docs/runbook.md` | serving stage runbook + rollback ladder; `set_knob.py` convention | PR-S |
| `docs/plans/trade-engine-accuracy/tester-protocol.md` | M3 cadence | PR-M |
| `living-memory/LLD.md` | conventions: prefs filter after score; `basis` meaning per arm + `fit_data_basis`; lens provenance | PR-F2/F3 |
| `docs/adr/` | D-next: fit-challenger is a generator, not a profile (scope §4 proposal); D-next: `group_size = 0` chosen over lane-quota-off for Stage 1, and why | PR-F3, PR-S |
| `living-memory/DECISIONS.md` | same two decisions, cross-linked (grep max ID first — HANDOVER trap 9) | at merge |
| `living-memory/CHANGELOG.md` | dated entry per merged PR + per stage flip | at merge (don't bank for session end) |
| `living-memory/NEXT.md` / `HANDOFF.md` | queue + in-flight state per session | per session |
| `living-memory/TEST_LEDGER.md` | §6 entries | per evidence event |

---

## 8. Risks accepted for speed — and why they are safe

| # | Risk accepted | Why it is safe to accept |
|---|---|---|
| R1 | **Serving re-lights before `fit` exists** — testers get B/C/D for a week; arm C forfeits in unboarded leagues, so some decks lean arm B | Attribution is per card, so mixed exposure contaminates nothing; the deck fills from arm B (S1b regression test); a week of C/D decisions is the first per-arm signal this program has ever had. The alternative — holding serving for `fit` — buys zero risk reduction and costs the scarcest resource (decided cards). |
| R2 | **`group_size = 0` discards lane-quota telemetry** during serving | 79 runs of `groups_json` lane data are already banked and the composition questions they answer are answered (outlook lane fills ~1/3; `current_divergence` 153/254 short). The binding question now is per-arm like-rate, which needs decisions, and lane quotas are precisely what killed the last serving attempt. One knob restores composition if the operator wants it back. |
| R3 | **`fit` goes from fixture dry-run to tester serving with no prod dark soak** | The 60s `_JOB_HARD_TIMEOUT` bounds the worst performance case; `fit_max_packages_per_pair = 5,000` first roster bounds the work; the operator canaries their own league within the hour; rollback is one knob with hours of natural exposure lag before most testers see a card. A dark soak would force re-darkening all arms — strictly worse than the exposure it avoids. |
| R4 | **No cross-arm bucket parity in the v1 readout** (fit buckets exist only on fit cards; arm-B cards aren't scored through the fit scorer for a like-for-like `both_high` comparison) | C3's co-primaries plus the decline-reason mix carry the comparison; pooled guardrail catches gross regressions. Scoring arm-B cards through the fit scorer offline is a clean follow-up (M2b) that needs no new data collection — nothing is lost by deferring it. |
| R5 | **Knob log covers funneled writes only** — a raw SQL `UPDATE model_config` bypasses it | Perfect attribution needs DB triggers on two engines (SQLite + PG); disproportionate. The convention (`set_knob.py` + runbook rule) covers the operator and every session that reads the runbook; the `updated_at` column still catches bypassed writes as *unattributed but dated*, which is the actual Phase-0.2 bar (today there is nothing at all). |
| R6 | **`fit_r5_mode` and `fit_junk_floor` are speculative knobs shipped dark** | Both are one-line reads with defaults that preserve ruled behavior; the review explicitly asks for both pre-wires (C2, C5); the cost is two disposition sentences (T4). The alternative is a deploy in the middle of a measurement window, which the change-control rule exists to prevent. |

---

*Draft A ends. Rival draft (risk/measurement-first) cross-critiques against this; §0 and §8
are the load-bearing defenses of the sequencing.*
