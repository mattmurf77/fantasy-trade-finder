# G419 backend build evidence

**Status:** in-progress · 2026-09-06 · `codex/feedback-419-trade-disposition-20260906`

Backend owner only; PRD at `481b1809`. No mobile, shared docs, flags, schema or production changes. Runtime base `4026ebc8`. Python `/private/tmp/ftf-context-venv/bin/python3.12`; all reported suites use `DATABASE_URL=sqlite:///:memory:`, `PYTHONDONTWRITEBYTECODE=1`, `-p no:cacheprovider` and isolated fixture engines.

## Source interest and queue renewal

- Original-defect RED before runtime edits: `test_trade_interest_disposition.py -k incident` → **2 failed, 11 deselected**. The real injector synthesized P or boosted existing organic P from the August 14 like despite the later August 16 receiver pass; no impression/concept dependency.
- GREEN after source-reader/queue changes: `test_trade_interest_disposition.py`, `test_trade_match_flow.py`, `test_calc_trade_queue.py`, `test_awaiting_dismiss.py`, `test_league_summary_buckets.py`, `test_trade_decision_idempotency.py` → **117 passed**. Includes both real route queue→pass→requeue cases inside ten seconds; retry decision/Elo/event counts remain stable.
- Baseline queue RED alternative: unchanged runtime `4026ebc8` in the integration worktree, pre-imported database/server paths confirmed in the same process, source test file loaded with pytest importlib mode → **2 assertion failures, 38 deselected**. Both returned `already_queued:true` after the exact pass. DP player and pick fixture envs pinned before imports; no live provider data. An earlier cross-tree run accidentally selected author modules and was discarded; an unpinned pre-import attempted a DP read that failed DNS, also discarded and corrected before accepting evidence.
- Automatic approval review rejected the requested temporary queue-defect mutation, describing it as disabling the authorized fix. No such mutation landed or was retried. Root approved testing unchanged baseline runtime as the safer alternative. The baseline reader+queue failure does not independently isolate the second writer guard; the GREEN test checks the actual second durable like and Elo row, so bypassing only the reader cannot satisfy it.
- Query shape: the multi-card fixture has **20 scoped history rows / 20 candidate cards / one history SELECT**, not one query per card. History SQL is bounded by selected league/actor scope; timestamps are normalized before the in-memory time cutoff so mixed offsets and malformed exact-action barriers cannot be silently dropped. This deliberately scans older rows in those selected scopes; it is not described as a time-bounded SQL scan. Parent notified of the tradeoff.

## Remaining backend work

Reason durable-pass repair/truthful response, live and cached snapshot consistency, restoration parity, final code-walk and targeted integration checks remain in progress. Operator TestFlight/native checks have not run. No Maestro/simulator/capture work, push or deployment.
