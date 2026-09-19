---
round: 03
direction: primary->subagent
thread: perf-optimization
date: 2026-06-07
author: primary
status: open
surface: cross-client
references:
  - round-02-findings.md
  - ../../code-audit/perf-optimization/plan/optimization-plan.md
  - ../../code-audit/perf-optimization/plan/priority-matrix.md
---

## Context
Wave 1 shipped (PR #66, `main` `464a7a2`). User directive for this round:
> "Continue to iterate through all optimization changes that don't require any
> action or inputs from me. For all of the items that do require input only from
> me, share a full list of questions/decisions in chat."

So: **autonomously implement every Wave 2/3 item that needs no user input.**
The user-input items are in `artifacts/questions-for-user.md` (already posted to
chat) — **do not block on them; work around them using the documented defaults.**

## Decisions on Prior Findings
- [accept] Round-02 Wave 1 — all merged.
- [accept] B1's build-time bake refinement is OPTIONAL polish — primary's call,
  not a user input. Default: leave as-is unless you (next session) judge the
  fetch-only refactor cheap + safe.
- [defer] INIT-11b Tiers virtualization, INIT-08 Option B (snapshot replay) →
  Wave 3 (higher risk; need careful golden tests + PR #60 coord-fix preservation).

## New Tasks (Wave 2 — autonomous; order is a suggested sequence)
**Before each: read `design/requirements/init-0X-*.md` + the `design/lld.md`
section, and `git diff origin/main` for the touched files — `#62/#63/#64`
already did related work; do NOT duplicate it.**

1. **Pre-flight: reconcile with shipped work.** Diff `main` for `session_init`
   (`#64` parallelized it), Trios prefetch/gcTime (`#62`), hot-path indexes +
   cache hygiene (`#63`). Update the matrix if any Wave-2 item is already done.
   **AC:** a short note in `artifacts/wave-status-matrix.md` marking overlaps.

2. **INIT-11a render memo wins** [MOBILE, low risk] — `React.memo` on
   `PlayerCard`/`TradeCard`/OverallRanks `Row` (+ `getItemLayout`); extract the
   ManualRanks edit row so `renderItem` depends on `editingPid` not `editValue`;
   scope the over-broad `['rankings']` invalidation to position; shallow-equal
   `setJob` guard. Hoist Tiers `renderPlayerCard` inline arrows so memo bites.
   **AC:** `tsc` clean; no behavior change; see `init-11-*.md` ACs.

3. **INIT-13 poll backoff** [MOBILE] — 800 ms→4 s exponential backoff + jitter
   on the trade-status poll (reset on `opponents_done` advance) + the `setJob`
   shallow-equal guard. **AC:** job still fills to completion; ~60–75% fewer
   status requests.

4. **INIT-12b GET retry** [MOBILE] — add GET-only retry (2 attempts, 400 ms→1.2 s
   + jitter, on 502/503/504/network) to the `client.ts` wrapper, composed with
   the Wave-1 timeout. **Never** retry POSTs. **AC:** cold-start 5xx GET recovers;
   `session_init`/swipes/saves excluded.

5. **INIT-14b DB hygiene** [BACKEND] — narrow `check_for_match` (`SELECT` only
   the two ID arrays + recency bound); server-cache the community-ELO map per
   `(league_id, scoring_format)` invalidated on `upsert_member_rankings`;
   single dialect-aware bulk upsert in `upsert_league_members`. **AC:** existing
   pytest green + add targeted tests; if a column/schema changes, update
   `docs/data-dictionary.md`.

6. **INIT-09 trade-gen prune** [BACKEND, higher risk] — pre-prune give/recv
   candidate sets to ELO-eligible players before the combination loops
   (~10× fewer 3-for-2). **Build a top-K equivalence test first** (same
   top-of-deck cards before/after on fixture rosters) — it is a hard gate.
   Do NOT alter `_fairness_score`/KTC. **AC:** equivalence test passes; deep-league
   sweep no longer truncates on the 1 s deadline.

7. **INIT-07 persisted cache + key scoping** [MOBILE, structural] — **scope keys
   first** (`['rankings', format, position]`, `['progress', leagueId, format]`,
   etc.; keep invalidation prefixes matching), then add an **AsyncStorage**
   query persister (locked default — no MMKV native dep) with a dehydrate
   allowlist (exclude live trade-gen job snapshots + the trio deck). **AC:**
   format/league switch swaps cache slots (no bleed); cold launch paints
   last-known data. ADR candidate — write `docs/adr/` entry for the persistence choice.

8. **INIT-08 client optimistic shell** [MOBILE] — paint a skeleton Main shell on
   league pick before `session_init` returns; stream data in on token arrival;
   gate interactive actions on `hasToken`. (Backend `session_init` split needs a
   profiling spike — see questions-for-user #5 — so do the **client half only**.)
   **AC:** league pick paints a populated shell ~instantly; data fills after.

9. **INIT-15 docs + the pending data-dictionary update** [DOCS] — add
   `ix_players_position` to `docs/data-dictionary.md` (Wave-1 obligation); add a
   `docs/runbook.md` note on platform-gzip + edge-compression reliance (records
   the OBS-API-02 reconciliation).

## Questions (for the user — non-blocking; full text in artifacts/questions-for-user.md)
1. Infra cold-start mitigation (warm-ping cron / paid dyno / `--workers`)?
2. Merge the audit docs (`audit/perf-optimization`) to main, or keep on branch?
3. Build/ship cadence — EAS build after each wave or batch?
4. Profiling auth token for the INIT-08 backend `session_init` split?
5. Web-payload (INIT-10) prioritization — do it (web-only) or deprioritize?
6. MMKV upgrade for the persister (faster, native dep) vs AsyncStorage default?

## Out of Scope (this round)
- INIT-10 web payload (pending prioritization Q5), INIT-08 backend split (pending
  profiling Q4), INIT-11b Tiers virtualization + INIT-08 Option B (Wave 3),
  INIT-16 (deferred). Anything needing the user-input items above.

## Touches
- Wave-2 mobile: `mobile/src/components/{PlayerCard,TradeCard,StrengthBar}.tsx`,
  `mobile/src/screens/{OverallRanksScreen,ManualRanksScreen,TradesScreen,TiersScreen,MatchesScreen}.tsx`,
  `mobile/src/api/client.ts`, `mobile/src/state/queryClient.ts`, `mobile/App.tsx`,
  query-key call sites, `mobile/src/navigation/TabNav.tsx`.
- Wave-2 backend: `backend/database.py`, `backend/trade_service.py`,
  `backend/trends_service.py`, `backend/tests/`.
- Docs: `docs/data-dictionary.md`, `docs/runbook.md`, `docs/adr/`.
- **Discipline:** disjoint file sets per parallel agent; primary owns git +
  verify (`tsc` + `pytest`) + merge; one PR per coherent slice.
