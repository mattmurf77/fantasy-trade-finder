# G419 backend build evidence

**Status:** backend implementation complete; root integration/native verification pending · 2026-09-06 · `codex/feedback-419-trade-disposition-20260906`

Backend owner only; PRD at `481b1809`. No mobile, shared docs, flags, schema or production changes. Runtime base `4026ebc8`. Python `/private/tmp/ftf-context-venv/bin/python3.12`; all reported suites use `DATABASE_URL=sqlite:///:memory:`, `PYTHONDONTWRITEBYTECODE=1`, `-p no:cacheprovider` and isolated fixture engines.

## Source interest and queue renewal

- Original-defect RED before runtime edits: `test_trade_interest_disposition.py -k incident` → **2 failed, 11 deselected**. The real injector synthesized P or boosted existing organic P from the August 14 like despite the later August 16 receiver pass; no impression/concept dependency.
- GREEN after source-reader/queue changes: `test_trade_interest_disposition.py`, `test_trade_match_flow.py`, `test_calc_trade_queue.py`, `test_awaiting_dismiss.py`, `test_league_summary_buckets.py`, `test_trade_decision_idempotency.py` → **117 passed**. Includes both real route queue→pass→requeue cases inside ten seconds; retry decision/Elo/event counts remain stable.
- Baseline queue RED alternative: unchanged runtime `4026ebc8` in the integration worktree, pre-imported database/server paths confirmed in the same process, source test file loaded with pytest importlib mode → **2 assertion failures, 38 deselected**. Both returned `already_queued:true` after the exact pass. DP player and pick fixture envs pinned before imports; no live provider data. An earlier cross-tree run accidentally selected author modules and was discarded; an unpinned pre-import attempted a DP read that failed DNS, also discarded and corrected before accepting evidence.
- Automatic approval review rejected the requested temporary queue-defect mutation, describing it as disabling the authorized fix. No such mutation landed or was retried. Root approved testing unchanged baseline runtime as the safer alternative. The baseline reader+queue failure does not independently isolate the second writer guard; the GREEN test checks the actual second durable like and Elo row, so bypassing only the reader cannot satisfy it.
- Query shape: the multi-card fixture has **20 scoped history rows / 20 candidate cards / one history SELECT**, not one query per card. History SQL is bounded by selected league/actor scope; timestamps are normalized before the in-memory time cutoff so mixed offsets and malformed exact-action barriers cannot be silently dropped. This deliberately scans older rows in those selected scopes; it is not described as a time-bounded SQL scan. Parent notified of the tradeoff.

## Reason repair increment

`test_decline_reasons.py -k 419` reproduced five assertion failures on
`c09e8a2f` (reason implementation still baseline): contextless false commit,
unrepairable failed decision insert, missing all-format binding, and both
ordinary-swipe/reason ordering cases. The unchanged fixtures now pass.

Focused current run: decline reasons, pass cooldown, decision idempotency,
calculator queue: **153 passed**. Two old `passed:false` assertions were
intentionally corrected to `true` on committed repeats, exactly the revised
API contract: state, not reason-row creation. Structural guards follow the
extracted live binding and durable ensure/atomic Elo paths instead of pinning
the removed inline implementations; no behavioral fixture was weakened.

Reason repair locks the existing reason row, verifies actor/league/actual card
ID and oriented package, and inserts only a missing durable pass. `passed`
does not depend on HTTP success or best-effort memory writes. A failed decision
insert remains banked and repairable. Elo claim + swipe rows share a transaction
for reason writes; a failed Elo insert rolls back its claim while retaining the
already committed pass. Ordinary swipe's pre-DB in-memory D-073 behavior stays
unchanged. Ordinary durable Elo consumes a matching banked reason's claim so a
late value detail cannot repeat it. Outcome/event side effects run only for a
newly committed reason pass; progressive retries bind live state but do not
repeat decisions or telemetry.

Independent unchanged-runtime alternative: pre-imported
`integration/backend/database.py` and `integration/backend/server.py` at
runtime base `4026ebc8`, then ran the author test file with pytest importlib.
Explicit player/pick CSV fixture envs were pinned. All **6 reason regression
cases failed on behavioral assertions**, including failed Elo rollback;
74 deselected. This is not an import-error or modified-runtime RED.

## Snapshot/source follow-up evidence

Before projection, `test_trade_disposition_replay.py` produced **7 assertion
failures / 1 pass** on the author tree's unchanged cache implementation.
Then the unchanged integration baseline, with explicit provider fixture pins,
produced **10 behavioral assertion failures / 1 structural test deselected**:
complete/running cached generate/status, old-ID league-switch, stale interest,
pending new ID after reason, standing-offer exact pass, initial fresh response,
and a real worker passed mid-generation before final publication. Projection
never mutates frozen impressions or snapshot payloads; the live final worker
filters before new impressions. Tests inspect SQL execution outside the global
job lock and require one decision-history SELECT per response.

Parent review identified mixed player/pick Awaiting ownership: **2 RED** tests
at the first source commit, for generic and owned picks absent from player
rosters. The correction retains the existing known-player anchor and rejects
contradictory/no-known owners, without assigning historical pick recipients.
Queue renewal tests now freeze `database.datetime` as well as `_now`.

Hermetic correction: a verbose first 5k measurement exposed import-time DP
fetch attempts when ordinary pytest ran without provider envs (DNS failed,
no data received). That timing is discarded. All final validation commands
explicitly pin `FTF_DP_VALUES_FILE` to
`backend/tests/fixtures/outlook-hypotheses/dp-values-players-2026-08-09.csv`
and `FTF_DP_PICK_VALUES_FILE` to
`backend/tests/fixtures/dp_values_picks_2026-08-06.csv`, in addition to the
in-memory DB/no-bytecode/no-pytest-cache settings. Tests' isolated DB fixtures
remain unchanged; there is no production benchmark or fixture recapture.

Pinned final snapshot/source/queue/read-amplification/bakeoff-serving/standing-
offer run: **150 passed in 3.70s**. Root explicitly approved one prerequisite
fixture correction in `test_bakeoff_serving.py`: its fake injector now supplies
the true matching source like that the real injector would require. Every
existing interleave/attribution/policy-version assertion and golden file is
unchanged. Strict unverifiable-source removal remains covered by its own test.

Pinned 5,000-row diagnostic (SQLite fixture, no hard latency oracle): reader
selected 5,000 rows and returned 5,000 likes in **38.15 ms / one SELECT**;
public projection of 20 cards used the same 5,000-row scope in **71.68 ms /
one SELECT**. Columns: id, user_id, league_id, trade_id, give_player_ids,
receive_player_ids, decision, created_at, retracted_at, impression_id,
trade_concept_id. This measures the disclosed all-scoped-history tradeoff,
not production capacity. Each response reuses its one history projection for
both pass-window and source-interest filtering; no per-card DB loop.

## Restoration and final integration

The new restoration suite executes both real production builders with the
existing isolated session-init harness. Before the helper wiring: **7 failed,
13 passed** (day-8/day-13 replenishment, fractional boundary and UTC-offset
selection, amnesty-disabled replenishment). The same unmodified fixtures on
explicitly pinned, pre-import-confirmed baseline `4026ebc8` again produced
**7 behavioral failures / 13 controls / 1 structural case deselected**.
Current restoration + replenishment + cooldown + init-call-budget run:
**51 passed**. No copied window predicate or changed policy defaults.

Two parent-reviewed follow-ups have direct pre-fix RED evidence: delayed
old-league reason binding (**1 failed**) and replenishment cached/final counts
after a just-committed pass (**2 failed**). All now pass. Replenishment uses
the same batched projection outside the job lock before counting inventory;
no notification lifecycle/flag change. Empty public snapshots do not need a
history read or key, preserving existing pure empty-payload shape tests.

Pre-provenance pinned consolidated run: **393 passed in 8.07s** across these 18 files:

- `test_trade_interest_disposition.py`, `test_trade_disposition_replay.py`,
  `test_trade_disposition_restoration.py`, `test_decline_reasons.py`
- `test_trade_match_flow.py`, `test_pass_cooldown.py`,
  `test_awaiting_dismiss.py`, `test_deck_fatigue.py`
- `test_trade_decision_idempotency.py`, `test_swipe_reconstruct.py`,
  `test_bakeoff_serving.py`, `test_calc_trade_queue.py`
- `test_deck_replenishment.py`, `test_standing_offers.py`,
  `test_trade_job_read_amplification.py`, `test_scoring_execution_context.py`
- `test_deck_first_session.py`, `test_force_supersedes_running_job.py`

## Specific source provenance — final parent finding

An old cached interested card linked to source `i1` must not be validated by
a later same-package like `i2` after the old source was resolved. Internal
cards now check their non-null `source_like_impression_id` against that
specific actionable source. Serialized cards use their own impression IDs
to read the existing owned, same-league frozen source links in one batch.
Null or absent legacy links retain the existing exact-current-evidence rule;
no source ID is invented and no frozen row or public payload is modified.

Verified unchanged runtime `cf8cc2cc` in a detached baseline checkout, with
both imported module paths asserted before pytest importlib loading and
the same explicit provider fixtures, produced **4 behavioral assertion
failures / 16 deselected**: the real cached `/status` route and three internal
source variants retained the old card incorrectly. This baseline already
contains the cache projection, so the failures isolate its missing source
identity check. No production source was disabled. A further test against
the recovered worktree found a non-null empty source ID fell through as
legacy (**1 failed / 2 passed / 17 deselected**); changing the guard from
truthiness to `is not None` honors the reviewed contract.

The new tests also pin failure-closed provenance reads, null legacy links,
account/league scoping, unchanged frozen rows and ordered survivors. The
real linked-card response issues **two SELECTs total: one decision-history
read plus one batched owned-provenance read**, outside the global job lock.
There is no provenance SELECT for internal or unlinked legacy cards without
their own impression IDs; the earlier one-SELECT fixture measurements above
remain valid for that case, not a universal claim about all responses.

Final exact 18-file command listed above, with the stated DB/provider pins:
**401 passed in 7.49s**. An intermediate recovery run before the empty-source
edge test was added passed **399 tests in 7.79s**. No full repository or
mobile QA is claimed by these focused runs.

`git diff --check` passed. Two attempted suite commands named nonexistent
winnowing/bakeoff filenames and ran no tests; corrected explicit paths are
listed above. One intermediate consolidated run caught an empty-snapshot
fixture's missing internal key (363 passed / 1 failed); the nonempty-only
projection fix restored that existing contract without changing its fixture.

Backend code-walk: [backend-code-walk.md](backend-code-walk.md). Root owns the
full repository/combined mobile run and shared spec-doc/ledger updates.
Operator TestFlight checklist remains **not run**. No Maestro, simulator,
captures, production writes, push or deployment. Remote-only invalidation of
already retained mobile decks, post-match Decline/fuzzy exemptions, and
standing-offer lifecycle remain explicitly held as in the reviewed PRD.
