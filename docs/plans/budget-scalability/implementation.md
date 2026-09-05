# Scoring and trade execution context — local implementation record

Date: 2026-09-04. Status: built for review, unmerged and undeployed.
Branch: `codex/scoring-execution-context`.
Base: freshly fetched `origin/main` at `606e512c`.
Worktree: `/private/tmp/ftf-scoring-execution-context`.

## Completed milestone

Requests get stable top-level session reads and format-selected service aliases.
They no longer change shared aliases just by reading with `X-Scoring-Format`.
Ordinary session writes still persist, including activity, auth metadata and
scoring-switch defaults. A request view cannot forward writes after the token's
user/account identity has changed. Legacy mapping-sensitive display helpers
accept the new view, and the direct `_effective_format` reader uses the common
resolver.

Kickoff captures frozen user/league/format ownership and selected service
references before a thread starts. Interactive requests pass their resolved
view, session/init pregen passes its newly built payload, and replenishment
captures its explicit format at synchronous kickoff. A later reinit, switch or
session eviction cannot redirect an accepted job. Pins and preloaded preference
values are copied before scheduling. Capture failures remain registered error
jobs; arbitrary unregistered league overrides still reach the engine's existing
`Unknown league` error instead of receiving a new HTTP error contract.

Generation owns a copied league/member graph and private trade-service player
and league maps. Real-member ranking injection and owned-pick mutations no
longer bleed between jobs. The original selected format's card store and
past/dismissed-decision sets remain shared, preserving pending cards, direct
swipes and live suppression. No algorithm, candidate breadth, fairness policy,
card limit, analytics emitter, pregen eligibility, caching TTL, timeout, polling
shape or deployment setting changed. This implementation adds no paid resource
or operating expense and does not enforce the $200 ceiling through feature cuts.

## Code-walk proof

- `backend/server.py:2454`: `_RequestSession` snapshots top-level reads and
  forwards normal writes under the existing session lock, now reentrant. Initial
  alias selection touches only `view.data`.
- `backend/server.py:2491`: `_require_session` resolves one view per Flask
  request; header, active format, default priority is preserved.
- `backend/server.py:2534`: raw sessions cannot reuse stale request scratch
  `_effective_format` state. `_pick_rung_year_context` and `_scope_season` accept
  mappings; the player-profile route also calls `_active_format`.
- `backend/server.py:5902`: frozen execution descriptor; capture copies only
  job-mutated league state and service maps, retaining the selected ranking
  service/card/decision-store references.
- `backend/server.py:5944`: the worker uses captured ownership and services;
  direct internal runner callers retain a capture-at-entry compatibility path.
  Existing preference loading, generation, postprocessing and event emitters
  remain in place.
- `backend/server.py:6989`: capture precedes thread scheduling and synchronous
  execution; registered error snapshots handle failed capture.
- `backend/server.py:12319` and `:19988`: generate and session/init pregen pass
  their already-resolved context. Replenishment passes its original explicit
  format through the same kickoff seam.

## Verification

Python 3.12.14 from the bundled runtime, isolated virtualenv
`/private/tmp/ftf-context-venv`. Existing requirements only; no dependency-file
changes. The runner `/private/tmp/run_ftf_pytest.py` creates scratch SQLite and a
scratch player-cache path, uses committed DP/player/pick fixtures, disables
network and import-time daemon startup, and blocks socket connections through
pytest. It does not read credentials or the user's working database.

- Final-source targeted generation/owned-pick/assignment/golden suites: **150
  passed** in 5.60 s. Includes all ten new context tests, trade match flow,
  force-supersede, replenishment, read amplification, bakeoff arm-A goldens,
  fairness goldens, ranking goldens, owned picks and tradeable pick assignments.
- Earlier targeted analytics/bakeoff/breaker/negmem/deck suites: **195 passed**
  in 22.09 s, before the final capture-error compatibility adjustment.
- Root's independent API compatibility comparison: **87 passed** on base and
  the initial implementation, covering trade match flow, cross-format copying,
  rookie scope and persistent sessions.
- Named runtime sabotages (temporary harness monkeypatches, no source changes):
  `mutable_request_aliases` → **1 failure**; `late_token_resolution` → **2
  failures**; `shared_member_graph` → **2 failures**. The unchanged final source
  passes those guards. Barriers, not sleep-based timing, force overlap.
- Initial broad run was deliberately interrupted during the unrelated CPU-bound
  mock-draft calibration: **2263 passed / 7 failed**, 259.24 s. The 7 failures
  were fixture-bootstrap conflicts in API observability and DP crosswalk/format
  tests: forced fixture environment overrides bypassed their own HTTP mocks.
  Root reproduced the exact **7 failures / 28 passes** on unchanged base, then
  ran the affected three files with overrides removed after safe import and the
  socket guard retained: **35 passed** on final source. No product change was
  made for these harness conflicts.

- Final-source broad run, excluding only
  `test_mock_draft.py::test_w2_16_calibration_gate`: **4620 passed / 8 failed /
  1 skipped / 1 deselected**, 189.65 s. The eighth failure was the same forced
  DP-fixture conflict in `test_qb_1qb_cap`; root reproduced it on unchanged base
  (1 failed / 15 passed) and verified all 16 cases pass with the override removed.
  All eight broad-run failures therefore reproduce on base. A final combined
  rerun of the four affected files plus all ten new context tests, after clearing
  fixture overrides following safe import, passed **61 tests** in 0.62 s. These
  are overlapping runs, not additive counts. The monolithic full suite is **not
  claimed green**; the slow calibration and existing opt-in backtest remain
  unverified here.
- `python -m py_compile backend/server.py backend/tests/test_scoring_execution_context.py`
  and `git diff --check`: clean. No mobile or deployment checks are claimed.

## Local capture cost

Committed `player_pool_2026.json` (340 players), twelve synthetic members with
26-player rosters and 340 Elo entries each; no external data. One hundred captures
after ten warmups on this machine: median **1.61 ms**, p95 **1.99 ms**. A separate
single-capture tracemalloc measurement peaked at **95,736 bytes**. The selected
card dictionary stayed shared. This only measures this local capture operation;
it is not a capacity test, production latency estimate or $200 deployment proof.

## Deferred and review limitations

This remains in-process groundwork. There is no durable queue, separate worker,
shared session repository, distributed cache, lease/retry protocol, job recovery,
new process count or concurrency rollout. Do not enable additional Gunicorn
workers or claim multi-instance correctness from these tests.

The execution descriptor freezes ownership/format references, not the whole
application's data. Selected ranking services still read their live board at
execution time; DB preferences, feature flags, model configuration and shared
player objects retain their existing semantics. Request views copy top-level
reads, not nested service graphs. General concurrent ranking/auth/session writes
are not transactional, and write ordering during same-user league reinitialization
still requires a broader session-version design. Card/decision publication still
relies on local memory, and reinitialization retains the existing client-side
swipe reconstruction fallback. Versioned durable snapshots and serialization
are a future milestone.

No mobile/web/extension code changed. Mobile typechecks, structural/UI runtime
checks and manual TestFlight are n/a for this backend-only contract-preserving
milestone. Maestro and simulator checks are retired by D-056. Full pre-ship CI is
still required before a later merge. The user's original dirty checkout and
its handoff state were not modified; this scoped record and TEST_LEDGER carry
this work's status instead.
