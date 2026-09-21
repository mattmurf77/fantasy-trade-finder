# Cache, admission and invalidation implementation evidence

Date: 2026-09-21. Worktree: `codex/trade-first-action-release`, based on research commit `c1805dc7` and production baseline `4913ad0c`. This is the bounded cache workstream from [release scope](scope.md), not evidence of deployment or of three-second tap-to-action latency. Parent owns final integration, canonical references and release gates.

## Implemented contract

- **Atomic claim or join.** `_kickoff_trade_job` now rechecks reuse and registers a new shared job in one `_trade_jobs_lock` critical section. Two simultaneous matching admissions produce one job and one worker. Input resolution, execution capture, account lifecycle preparation and worker/thread startup remain outside that lock. Session fields are shallow-snapshotted under the session lock before expensive execution capture. Source: `backend/server.py:8840`.
- **Exact request compatibility.** Running and complete reuse compare exact fairness, outlook, intent, presentation and applicable owner/policy identity. A local signature also covers resolved preferences, current trade configuration and feature flags. Failed preference resolution fails closed for reuse, both for the unresolved caller and for later callers encountering a stored explicit `request_signature=None`. Missing-key legacy job fixtures retain compatibility; production admissions always set the key. Sources: `backend/server.py:3037`, `backend/server.py:3054`, `backend/server.py:3395`, generate admission at `backend/server.py:14245`.
- **In-flight invalidation.** Jobs and pending admissions retain revocable user/league input tokens captured before input reads. Invalidating a scope revokes the token and every matching job, including selected searches with no shared cache pointer. Tokens survive deep-copy snapshots by identity. The weak index does not accumulate permanent entries after all referencing jobs/admissions disappear, and does not require another test-resettable global generation counter. Sources: `backend/server.py:2980`, `backend/server.py:8817`.
- **Publication and terminal fence.** Revocation clears public job cards but does not delete the session action store, durable offers or impression identities. `_job_live` blocks further publication; `_finish_trade_job` cannot turn an invalidated, superseded or timed-out job into a successful result, or overwrite its original terminal error. Thread startup failure becomes a retryable terminal `worker_start_failed` result. Delivery integrated these helpers into its separately owned worker. Sources: `backend/server.py:3008`, `backend/server.py:3017`, `backend/server.py:3101`.
- **Mutation coverage.** Tier saves, anchors, reorder and import-apply now invalidate immediately after successful in-memory board mutation, before subsequent persistence work. Existing rank/copy/preference/tag invalidations use the same stronger fence. Sources: `backend/server.py:11247`, `backend/server.py:11434`, `backend/server.py:11789`, `backend/server.py:12010`.
- **Search isolation.** Selected/pinned/specific-opponent jobs retain separate admission and never replace the organic pointer. Explicit force respects the existing force-supersession configuration. Background warm-up/replenishment preserves an already active interactive search only under current model/presentation/significance/safety policy, and does not classify a different fairness/intent running result as ready inventory. Sources: `backend/server.py:3067`, `backend/server.py:8840`.
- **Preparation consistency.** App-open resolves the same stored preference/inferred outlook and native fairness input as an explicit search. Replenishment uses the current live session fairness when available, the shared freshness predicate, actual stored platform and league scoring format. No schedule or notification expansion. Sources: `backend/server.py:22431`, `backend/server.py:23122`, `backend/server.py:23243`.
- **Response lock hygiene.** Generate captures `dict(job)` while locked, then deep-copies that stable shallow snapshot outside the lock. Published lists are replaced rather than mutated in place. Parent separately guards before/after disposition projection against copied-snapshot revocation. Status/public-view ownership was not duplicated in this workstream.

## Verification

Final expanded focused run: **197 passed in 7.01 seconds**, exit 0. Earlier focused run: 80 passed in 4.72 seconds. `git diff --check` and `python3 -m py_compile backend/server.py` also passed. These are correctness checks, not performance measurements. Runtime: local Python 3.14.4, not the repository-pinned Python 3.12.3. Exact-head CI remains the release gate.

The parent integration run exposed a real background-preservation defect: preserving *every* live request also preserved obsolete presentation/model work. `_trade_running_policy_matches` now requires current presentation, model, significance and any worker-stamped safety policy before background preparation preserves an active request. Different user fairness/intent remains protected only when those policy checks pass. Four real-kickoff regressions flip each policy dimension while also changing background fairness/intent and require replacement plus revocation. Session-init uses the same predicate.

Fresh reproduction before this correction produced 14 failures / 14 passes across the flagged presentation/model boundary tests. Case-by-case resolution:

- Three running presentation-change tests expected old jobs to remain unchanged and pollable. The new intentional supersession contract requires terminal error, cleared public prefix and no old-ID republishing; these assertions now prove that contract. Completed snapshots retain their original captured order.
- Three session-init running presentation-change cases exposed the real preservation bug fixed above; their replacement expectations are unchanged.
- Two unchanged-complete session-init fixtures lacked fairness/outlook/safety metadata. They now describe genuinely compatible native-0.5 jobs; original no-new-worker expectations are unchanged.
- Five replenishment presentation fixtures had 0.75 jobs but no corresponding session fairness (now correctly defaulting to native 0.5). The live session now explicitly carries the fixture's 0.75 value, isolating the presentation dimension; original reuse/replacement/card-count expectations are unchanged.
- One bilateral replenishment worker stub returned a supposed fresh job without fairness/outlook/safety metadata. It now supplies the actual request inputs and current safety signature; the original old-model-regeneration and empty-new-deck expectations are unchanged.

Test files:

- `backend/tests/test_trade_job_admission.py`: real server helper/route tests against per-test isolated SQLite; a barrier in actual execution capture reproduces concurrent admission. Covers changed fairness/outlook/intent/preferences/config, revoked copied snapshots, invalidation during admission, unresolved preference reads in both directions, selected/force isolation, background preservation, old action IDs, timeout, thread-start failure, lock-free input/startup seams, weak-token reclamation, four board mutation routes, and MFL/ESPN scoring/platform reconstruction.
- `backend/tests/test_force_supersedes_running_job.py`, `test_app_open_trades.py`, `test_deck_replenishment.py`, `test_scoring_execution_context.py`: existing force, warm-up, background generation and session-capture contracts. Fixtures now supply their actual resolved outlook/safety metadata rather than accidentally relying on missing values. The intentional terminal-contract change is superseded **error**, not successful completion.
- `backend/tests/test_research_trade_pipeline.py`: retains instrumentation-equivalence, stage partitioning and isolation guards. Baseline-only extracted bug assertions were removed because the fixed behavior is now tested against the actual server; historical reproductions remain in the research commit.
- `backend/tests/test_trade_publication_revocation_race.py`: parent's four actual status/projection regressions included in this focused run; copied snapshots withhold stale cards after epoch, force, model or significance changes.

Two named sabotage checks run in the test process without changing shared source:

1. `test_sabotage_admission_lookup_red_then_restored_green` replaces the cache lookup with a dictionary that always misses. The one-job assertion fails with `duplicate worker admitted` (expected RED), then passes after restoring the real lookup (GREEN).
2. `test_sabotage_invalidation_red_then_restored_green` replaces invalidation with a no-op. The publication guard fails with `stale worker may publish` (expected RED), then passes after restoring actual invalidation (GREEN).

Reproduction from the isolated worktree (the initial database URL must be a disposable local SQLite path; never production):

```sh
DATABASE_URL=sqlite:////private/tmp/admission-tests-20260921.sqlite \
FTF_DP_VALUES_FILE=/private/tmp/fleeced-trade-latency-plan/backend/tests/fixtures/outlook-hypotheses/dp-values-players-2026-08-09.csv \
python3 - <<'PY'
import os, socket, threading, logging
from unittest.mock import patch
os.environ.pop('ANTHROPIC_API_KEY', None)
logging.disable(logging.CRITICAL)
def block(*args, **kwargs):
    raise RuntimeError('offline tests forbid network')
socket.socket.connect = block
socket.socket.connect_ex = block
with patch.object(threading.Thread, 'start', lambda self: None):
    import backend.server
import pytest
raise SystemExit(pytest.main([
    'backend/tests/test_trade_job_admission.py',
    'backend/tests/test_force_supersedes_running_job.py',
    'backend/tests/test_app_open_trades.py',
    'backend/tests/test_deck_replenishment.py',
    'backend/tests/test_scoring_execution_context.py',
    'backend/tests/test_research_trade_pipeline.py',
    'backend/tests/test_trade_publication_revocation_race.py',
    'backend/tests/test_bilateral_routes.py',
    'backend/tests/test_small_trade_presentment.py',
    '-q', '--tb=short',
]))
PY
```

## Boundaries and remaining risks

This is **process-local request freshness**, not a complete versioned inventory. It does not create a cross-process cache, durable input-version table, or a full provider/market/roster/counterparty dependency fingerprint. Only wired invalidation events revoke captured scopes; an external dependency change without such an event is not automatically detected. Existing TTL, timeout and process restart behavior remain.

Client fairness is persisted on the client and supplied during session initialization, not newly persisted by this backend change. A truly headless reconstruction without that live session uses the native **0.5** default; it cannot recover an unknown custom client-only threshold. It resolves stored league preferences/outlook, platform and format, and a later different explicit request will not incorrectly adopt its job.

Board mutation plus invalidation is not a new transactional ranking/version protocol. Invalidation follows successful in-memory mutation and fences work captured before it; this does not claim atomic snapshots across all mutable services or all external dependencies. Existing account-deletion leases remain in place. A revocation racing a database write can leave committed evidence not subsequently published; publication and completion fail closed, and existing durable/action identities are preserved.

No candidate/pricing/search/offer cap changes were made by this workstream. No production test traffic, deployment, schema changes or flag/config changes were performed. Physical-device first-action latency, scale contention and the three-second goal remain unproven by these correctness tests.
