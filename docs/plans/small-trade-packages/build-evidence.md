# Small-player presentation — build evidence

2026-09-06. **Built default off; root-reviewed runtime integrated; full QA/release gates pending.**
Runtime/test commits `0bafa3a54f29dc9b38f4dbd6023d0b981c9499ca` and
`9ea562dd98861bcfae388146feca97e7e4c04942` (final), based on reviewed
#419 integration `741710c188a27e3e43b25e0b77372c5358617e72`.
Scope: approved [PRD](prd.md), [scope](scope.md), [reconciliation](reconciliation-log.md).
No activation, production write, generator/profile change, migration, dependency,
mobile edit or device run was performed by this builder.

## Results

The final consolidated 29-file run passed **741 tests in 15.00s**. It contains the
previous 401-test #419 gate, 93 new presentation cases, live policy/roster
suites, unchanged generator/arm goldens, bakeoff accounting/composition and
session initialization. `git diff --check` passed.
The initial implementation gate at `0bafa3a5` passed 731 tests in 14.82s;
the final run additionally includes the literal raw-selection exclusion below.
Root reported an independent **224-test pass in 8.44s**, reproduced the
anonymous diagnostic below, and merged runtime `9ea562dd` as `71b2b496`.
Full backend/integration QA was still running at this documentation handoff.

The new tests exercise real worker policy composition, real bakeoff drafting
and actual legacy/F1 writers with deterministic upstream candidates and
per-card policy results. No helper output is mocked. Other paths use existing
isolated route/session fixtures; cache tests inspect actual route reuse
decisions with kickoff spies, while a separate test runs actual synchronous
kickoff and verifies the capture handed to its worker. These are distinct
coverage layers, not a claim that every cache fixture runs generation end-to-end.

| Contract | Executed evidence |
|---|---|
| T1 | Both scoring formats × grouped/uncomposed actual bakeoff × F1 on/off. Shapes `3x3,1x4,2x3,1x1,1x2,1x1` become `1x1,1x2,1x1,3x3,1x4,2x3`. First-three player load **16→7**; first-six **23→23**. All six occurrences move three slots; A/B/C/A/B/C credit remains, original arm/group ranks travel with their cards. |
| T2 | Seventeen-card multi-window property fixture checks original objects and values, complete occurrence multiset, class slots, ≤5 displacement, absolute windows, a locked hole, short final window, stable/idempotent order and repeated-object occurrences. |
| T3 | Mixed/generic/owned picks contribute zero and do not break player ties; pure-pick, missing/unknown/malformed/conflicting metadata and five actual special markers lock. A real `Player(position='RB', team='PICK')` generic asset uses the existing canonical pseudo-asset rule. Missing actual attribution/group/policy does not invent organic provenance. |
| T3/T7 | Actual worker mode-0/mode-1 parity for explicit give, explicit receive, opponent, demo, ghost, shadow-only, bakeoff dark validation and policy evaluation failure. No presentation feature or helper execution in exempt cases. |
| T3 raw selection | Real `/generate` with receive targeting OFF and presentation ON bypasses matched complete/running organic cache when a raw receive selection is nonempty. No-selection and mode-off controls still reuse. Normalized receive remains None and default fairness .75. A private captured exemption also reaches the actual kickoff/worker; the exempt mode-on job cannot replace the organic shared-cache index. |
| T4/T6 | Hold at the actual final #419 boundary after first evaluated publication, assert its new order and released safety guard, commit an exact pass, then continue through real projection/writers. Four F1/suggestion-telemetry combinations. Surviving order remains, one helper call, no refill. |
| T5 | Completed and running `/generate`, session-init pregen and replenishment cache probes: missing legacy capture, 0→1, 1→0 and same-mode controls. Explicit old-ID polling keeps old order. An in-worker flag/base-version flip cannot change captured presentation/version. Actual kickoff passes the caller's capture without rereading the mode. Invalid/string/bool/nonfinite/unsupported modes stay off. |
| T6 | Distinct identical-shaped objects and repeated same-object survivors retain separate original indices `[3,5,4,2,1,6,7]`, final indices `0..6`, equal F1 `card_index`. Legacy `position_in_deck` and package order agree. Later post-freeze removal leaves stored rows untouched. A locked, unknown, unattributed first row retains null unknown counts and uniform presentation/version fields throughout the batch. |
| T6 logging | Existing suggestion-telemetry gate remains independent: candidate rows exist only when its existing logging path is enabled. No F1 rows are synthesized when F1 is off. Organic rows retain null arm attribution; valuation `policy_variant` is unchanged. |
| T7/T8 | Historical goldens and all existing bakeoff order/accounting assertions remain unchanged. Only the knob census recognizes the new post-generator default; no arm profile pins it. Optional `scoring_format` in the test harness defaults to its old value. #419, standing-offer, cooldown/fatigue, lifecycle/context, force-generation and live market/roster regressions pass. |

### Unchanged-runtime RED

A detached worktree at **unchanged `741710c1`** was created at
`/private/tmp/ftf-feedback-419-421-f1uMyt/packages-baseline`. In each process,
`backend.server.__file__` and `backend.database.__file__` were asserted to
resolve inside that checkout before pytest importlib loading of the new test
file. Its new pure helper was loaded only to satisfy test definitions: the
unchanged server never imports or calls it. No runtime source was disabled,
rewritten or monkeypatched to recreate the missing implementation.

- T1 (1QB, grouped/uncomposed, F1 on/off) plus all four cache paths:
  **19 behavioral failures, 12 passing controls, 52 deselected, 0.96s**.
  Four failures retain the old first-card shape; the other fifteen incorrectly
  reuse the incompatible cached job. The baseline harness lacks the newly
  added optional SF argument, so SF is not part of this RED selection.
- Held-publication, hot-flip and first-row frozen-feature selection:
  **7 failures, 76 deselected, 0.48s**. Four fail the first-publication order
  assertion, two expose missing captured ordering/base version, one exposes
  the absent frozen `presentation` feature. These are behavior/output
  failures, not collection errors.
- Pure-helper properties and exemption controls are GREEN invariants around
  those regressions; no separate sabotage claim is made for each individual
  lock or sort-key component. A pre-fix unknown-position test independently
  failed before the canonical-position correction.
- Root required the literal PRD exclusion even for raw receive pins ignored
  by the pre-existing targeting flag. Before the correction, at `0bafa3a5`,
  the real route test produced **2 behavioral failures, 6 passing controls,
  85 deselected, 1.58s**: both completed/running cache hits returned the organic
  deck despite supplied receive intent. All eight pass in the final gate.
  No source sabotage or normalization change was needed.

Intermediate fixture mistakes were corrected, not counted as RED evidence:
the harness constructs its pool before entering extra patches (new receivers
initially remained unknown); a real `Player` fixture initially omitted its
required age; one test initially used the wrong candidate-table attribute.
None required weakening production or an existing oracle.

### Reproducible GREEN command

Run from the packages worktree using `/private/tmp/ftf-context-venv/bin/python`:

```sh
env DATABASE_URL=sqlite:///:memory: PYTHONDONTWRITEBYTECODE=1 \
  FTF_DP_VALUES_FILE=backend/tests/fixtures/outlook-hypotheses/dp-values-players-2026-08-09.csv \
  FTF_DP_PICK_VALUES_FILE=backend/tests/fixtures/dp_values_picks_2026-08-06.csv \
  /private/tmp/ftf-context-venv/bin/python -m pytest -q -p no:cacheprovider \
  backend/tests/test_small_trade_presentment.py \
  backend/tests/test_trade_interest_disposition.py backend/tests/test_trade_disposition_replay.py \
  backend/tests/test_trade_disposition_restoration.py backend/tests/test_decline_reasons.py \
  backend/tests/test_trade_match_flow.py backend/tests/test_pass_cooldown.py \
  backend/tests/test_awaiting_dismiss.py backend/tests/test_deck_fatigue.py \
  backend/tests/test_trade_decision_idempotency.py backend/tests/test_swipe_reconstruct.py \
  backend/tests/test_bakeoff_serving.py backend/tests/test_calc_trade_queue.py \
  backend/tests/test_deck_replenishment.py backend/tests/test_standing_offers.py \
  backend/tests/test_trade_job_read_amplification.py backend/tests/test_scoring_execution_context.py \
  backend/tests/test_deck_first_session.py backend/tests/test_force_supersedes_running_job.py \
  backend/tests/test_trade_policy.py backend/tests/test_trade_policy_wiring.py \
  backend/tests/test_trade_roster.py backend/tests/test_trade_roster_wiring.py \
  backend/tests/test_bakeoff_arm_a_golden.py backend/tests/test_bakeoff_runner.py \
  backend/tests/test_bakeoff_composition.py backend/tests/test_bakeoff_challenger.py \
  backend/tests/test_engine_quality_golden.py backend/tests/test_session_init_sleeper_calls.py
```

Actual runs used equivalent absolute fixture paths. Both provider fixtures
were pinned before imports; no global conftest changed. Tests use isolated
in-memory engines. RED used the same fixture pins with `--import-mode=importlib`,
`--tb=line`, `--show-capture=no` and these selections:
`(t1_actual_worker or t5_generate_completed or t5_session_init_pregen or t5_replenish_cache) and not sf_tep`;
`t4_t6 or t5_worker_mode or t6_locked_unknown`.

## Conditional anonymous served-shape diagnostic

Root supplied two anonymous post-policy jobs, **78 served occurrences**,
from the September 5 post-policy window. Only anonymous QB/PICK shapes and
existing arm/lane/basis/policy-lane fields were used; no private values or
player/user identifiers were added. The artifact and diagnostic script remain
outside Git under the batch temporary directory.

This is **conditional on organic eligibility**, not an actual-runtime
counterfactual: historical rows cannot establish the original pins, dark
bakeoff mode or fatigue-retest flags. No acceptance-rate or causal inference
is supported. Captured grouping is absent and modeled as the approved
group-size-zero class solely for this diagnostic. No rule was widened to
produce movement.

| Anonymous job | Cards | Moved | First 3 players before→after | First 6 | Max move | No-op windows |
|---|---:|---:|---:|---:|---:|---:|
| 1 | 40 | 13 | 14→12 | 26→26 | 5 | 2/7 |
| 2 | 38 | 14 | 14→12 | 26→26 | 4 | 2/7 |

Both complete slot-class vectors, every occurrence and every classification
count match the inputs. Aggregate: 27/78 occurrences move, 4/14 windows
remain unchanged, neither entire job is a no-op. First-six player load cannot
change when merely permuting a full six-position window; its unchanged total
is expected, not missing supply. Larger packages remain available.

## Remaining handoff

Root owns independent/full backend QA, mobile guards/typecheck/testID lint,
shared documentation/decision updates, release and activation. PRD §6 physical
TestFlight checklist remains **UNRUN**; no simulator, Maestro or capture was
used. Default-off code, deployment, knob activation and tester availability
must be recorded as separate facts.

Root settled the explicit-input review note by requiring the literal PRD
contract. Final `9ea562dd` captures a private raw-receive exemption, excludes
that search from mode-on organic cache reuse/seeding and carries it to the
worker. The original normalized receive, generator selection, fairness and
flags stay unchanged; mode-off cache behavior remains baseline. The earlier
review note incorrectly grouped opponent fields with ignored receive pins:
the route always passes `opponent_user_id`, and its existing exemption remains.
