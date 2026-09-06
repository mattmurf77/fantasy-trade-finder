# G420 build evidence — Win Now recovery

Date: 2026-09-06

Status: implementation complete for parent review; no deployment or TestFlight verification performed by this builder.

Runtime commit: `2de3e1d95dbcb98d491bc0dee2811c5380ec0bec` (initial implementation `b988df7d7769c96c3069a394cc00601db5d2c0af`, followed by the parent-reviewed current-401 correction) on `codex/feedback-420-421-win-now-20260906`. Approved specification: `764e0ee9bdbbcc6cf90baaf1c5bdd994d2c4bbde`; the orchestrator recorded independent approval on the integration branch. This evidence supersedes prospective “not yet run” statements in the authored scope without claiming the release gates are complete.

## Result

Win Now awaits the same current-context initialization as foreground, picker, switch, Connect and ESPN resync. The exact missing-context refusal causes one forced initialization and one logical GET replay. The projection GET has a 30-second complete-request budget; the composed attempt and each shared initializer are bounded by an original 90-second deadline. Timeout text is “This request took too long. Please try again.”

A same-token selection cancels the obsolete projection consumer and its error reporting, while an already dispatched shared init retains its separate lifecycle. Uncertain init completion blocks automatic re-entry until a later deliberate action or a different token. The picker distinguishes automatic pinning from a deliberate selection. Existing imported-platform builders still support account-only identities attached to real ESPN/MFL/Fleaflicker leagues; `no_league` and invalid account-only Sleeper lookup remain blocked.

## Executed verification

All commands below used the isolated group worktree, installed dependencies rather than symlinks, Node `24.14.1` and Python `3.12.14`. No network fixtures, private account IDs or production database were used.

| Check | Result |
|---|---|
| `cd mobile && node tests/check-win-now-recovery.js` | **38 passed, 0 failed**; production transport, state owner, auth/platform builders, mounted Win Now effect, and extracted unchanged picker/resync handler bodies execute under synthetic deferred transports and fake time. |
| Every `mobile/tests/check-*.js` file, sorted and run as a separate Node process | **94 suites passed, 0 failed** on the final runtime tree. This includes the new recovery guard; parent registers its npm script. |
| `cd mobile && npx tsc --noEmit` | Passed. |
| `cd mobile && bash scripts/testid-lint.sh` | `testid-lint OK`. |
| Four focused backend suites below | **128 passed in 3.54s**. |
| `git diff --check` and staged equivalent | Passed. |
| Runtime file comparison between the baseline checkout and `4026ebc8` | Exact equality for every module used in the seven original-defect tests; baseline checkout SHA `f3f0d0c1e2ac771f160c2ea51810aaa69110cec2` contains documentation changes only for these modules. |

Backend invocation (from repository root):

```sh
DATABASE_URL=sqlite:///:memory: PYTHONDONTWRITEBYTECODE=1 \
FTF_DP_VALUES_FILE="$PWD/backend/tests/fixtures/outlook-hypotheses/dp-values-players-2026-08-09.csv" \
FTF_DP_PICK_VALUES_FILE="$PWD/backend/tests/fixtures/dp_values_picks_2026-08-06.csv" \
/private/tmp/ftf-context-venv/bin/python -m pytest -q -p no:cacheprovider \
  backend/tests/test_verified_sessions.py \
  backend/tests/test_persistent_sessions.py \
  backend/tests/test_win_now_api.py \
  backend/tests/test_win_now_service.py
```

An initial invocation mistakenly named nonexistent `test_win_now_projections.py`; pytest collected **zero tests** and exited 4. It is not counted as verification. The corrected four-suite run above is the actual evidence. Player and pick curves were explicitly pinned for this targeted run only; `conftest.py` was not changed.

## Failure proofs

The new harness supports `FTF_MOBILE_TEST_ROOT=<unchanged-checkout>/mobile FTF_BASELINE_ONLY=1 node tests/check-win-now-recovery.js`. This executes the actual unmodified original modules, not a test reconstruction or a disabled runtime fix. The run produced **seven meaningful assertion failures**, no missing-module/export failures:

| Original-runtime case | Observed RED |
|---|---|
| T7 measured 15.2-second projection completion | Original 15-second deadline rejected before response. |
| T8 old-session verification 403 | Stale callback count was 1, expected 0. |
| T8 timeout classification/copy | Original copy asserted the server was waking up. |
| T1 mounted Win Now after server context loss | Only the original init occurred; no repair (1 versus expected 2). |
| T2 concurrent foreground reconciliation | Second caller resolved before shared init settled. |
| T4 successful same-token A→B ordering | B dispatched before A acknowledgement (2 versus expected 1 in-flight POSTs). |
| T10 uncertain init followed by foreground | Automatic re-entry sent another init (1 versus expected 0). |

Finishing review also added tests **before** fixing actual defects in the inherited uncommitted implementation. Their RED→GREEN runs were:

- Picker token/preparation timeout retained `selectingId`; automatic picker restarted an uncertain writer; ESPN resync retained `busy`: three failures, then 28/28 GREEN.
- Account-only real ESPN picker was blocked: one failure, then real ESPN/MFL/Fleaflicker builders GREEN (29/29).
- Suspended JS resumed into a late transport dispatch; expired-session callback fired after replacement token during secure deletion: two failures, then GREEN (31/31).
- Delayed Connect upgraded an old gesture into retry permission; Connect reset its deadline when target resolution completed: two failures, then GREEN (33/33).
- Old same-token projection refusal leaked to the still-displayed old league; after error fencing, its failure telemetry still fired: each failed before the consumer-supersession subscription, then GREEN (34/34).
- Added control verifies a second ambiguous explicit retry relatches and a replacement token starts a separate lane: **35/35 GREEN** at the initial runtime commit.
- Parent review identified current 401 being hidden by the revision guard after that same request cleared its token. Actual mounted Win Now and picker tests failed (missing sign-in message), while the stale-401 replacement control passed. An internal from/to revision receipt now preserves only that exact authorized transition; all account/generation/replacement checks still apply. Current picker/resync error and busy behavior, mounted Win Now, and stale replacement control now pass: final **38/38 GREEN**. All 94 suites, typecheck and testID lint were repeated successfully after this runtime correction.

These are grouped original-defect and implementation-regression proofs. They are **not** a claim that every prospective sabotage listed in the PRD was individually executed. Source-disabling sabotage was not performed; the parent directed unchanged-runtime comparisons after an earlier automatic-review denial. The new installed backend guard test protects existing behavior and passes without any backend runtime change; no guard-removal run is claimed.

## Requirement coverage and limits

T1–T3 execute real state/API recovery, simultaneous joining, second-refusal termination, available/unavailable bodies and exactly one player-cache retry. T4–T5 execute pre-dispatch supersession, successful acknowledged A→B ordering, sign-out and independently detachable consumers. T7–T8 execute exact route/method budgets, header/body waits, backoff, suspended-runtime checks, typed refusals, current/stale verification callbacks and stale 401 behavior. T10 covers finite preparation, composed deadlines, persistent uncertainty across lifecycle-like automatic calls, old queued/Connect authorization, relatching and replacement token. T11 executes actual picker/resync bodies and Connect/platform builders; a structural census supplements these paths. T12 executes actual telemetry and checks the no-upward-import/no-write-recovery boundary. Existing Win Now guards and backend suites retain feature, source, freshness, title, search-order and independent-decision coverage.

The seven native runtime checklist steps remain **unexecuted**. No simulator, Maestro, screenshot, provider proposal, production learning write, EAS build, Apple upload or tester availability is inferred from these checks. Full integrated backend tests, independent QA, shared documentation/ledger updates and release verification belong to the orchestrator.

Two residual limits are explicit:

1. A local timeout/abort cannot cancel an already accepted server init or guarantee final server ordering against it. Only successfully acknowledged A→B ordering is claimed. The client latches uncertainty and requires a later deliberate attempt; there is no server CAS/generation API here.
2. Guards run before native AsyncStorage dispatch and after it settles, preventing stale store/UI/cache/navigation publication. They cannot cancel a native storage write already dispatched before supersession or prove unconditional disk ordering against arbitrary native completion order. No new persistence transaction/protocol is claimed.

The 30-second allowance addresses a measured premature deadline; it does not establish improved server throughput or remove synchronous worker contention.

## Integration handoff

Parent registers `test:win-now-recovery`, updates the scope's shared-doc rows and TEST_LEDGER, performs independent integrated QA, and owns version metadata and deployment. This branch contains no backend runtime, web, schema, feature flag, model configuration, dependency, version or package-script edits. Existing seed and ownership guards were updated to test the shared owner; the actual old-token refusal check was retained.

See [code walk and manual checklist](code-walk.md) for the final source trace.
