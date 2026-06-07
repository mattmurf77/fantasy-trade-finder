# REQ — INIT-13: Trade-Status Poll Backoff

- **Initiative / Wave / Scope:** INIT-13 · Wave 2 · [M]
- **Source observations:** OBS-API-03, OBS-RENDER-04
- **Peak RICE-P:** 3.0 (OBS-RENDER-04); OBS-API-03 scored 2.4

## Problem statement

The Find-a-Trade feature polls `/api/trades/status` on a fixed 1.5 s interval
from the moment a job starts until it completes. During multi-opponent jobs —
which may run for 10–15 s — the majority of poll ticks return an unchanged
in-progress snapshot. Each no-change tick re-renders `TradesScreen` (because
`setJob` receives a new object identity unconditionally) and re-normalizes the
full growing card list client-side. On a single free-tier gunicorn worker, the
poll storm also contends with the generation job itself, degrading the streaming
fill tail.

## User stories

- As a **dynasty manager** running a Find-a-Trade job, I want the screen to
  fill trade cards smoothly as opponents complete, so that I can see progress
  without dropped frames or battery drain from unnecessary re-renders.
- As a **dynasty manager** on cellular data, I want the app to stop polling
  dozens of times per job when nothing has changed, so that I'm not burning data
  or radio wake-ups on no-op requests.
- As an **operator**, I want trade-status poll requests to back off on unchanged
  ticks so that the single-worker free dyno has more headroom to actually
  complete the generation job rather than answering a flood of status checks.

## Functional requirements

- **FR-1 (exponential backoff with jitter):** Replace the fixed `setInterval(tick, 1500)`
  (`TradesScreen.tsx:256`) with a self-scheduling poll that uses exponential
  backoff. Starting interval: 800 ms. Per *unchanged* tick (where `opponents_done`
  has not advanced): multiply by 1.5, capped at 4 000 ms. Add per-tick uniform
  jitter of ±10 % of the current interval to prevent synchronized polls across
  concurrent sessions. An "unchanged tick" is defined as one where `opponents_done`
  equals the value from the previous tick.

- **FR-2 (reset on progress):** When `opponents_done` increments (progress
  detected), reset the interval to 800 ms for the next tick. This ensures the
  final card(s) are not delayed up to the 4 s cap when generation is actively
  advancing.

- **FR-3 (setJob shallow-equal guard):** Before calling `setJob(next)`, check
  whether the incoming snapshot is shallow-equal to the current `job` on the
  fields the UI reads: `status`, `opponents_done`, `opponents_total`, and
  `cards.length`. If all four are equal, skip the `setState` call and retain
  the previous object reference, so React skips the `TradesScreen` re-render.
  This is the render-side complement to FR-1's network-cadence reduction.

- **FR-4 (running→complete transition):** The `running → complete` status flip
  must fire promptly regardless of the current interval. If `status` changes
  from `running` to `complete` on any tick, the `setJob` update must be applied
  (the shallow-equal guard must pass through status changes).

- **FR-5 (cards.length growth):** Any increase in `cards.length` must pass
  through the shallow-equal guard so streaming trade cards land on screen.
  Do not suppress a `setJob` call when `cards.length` is greater than the prior
  tick's value.

- **FR-6 (interval cleanup):** On job completion, error, or screen unmount, the
  self-scheduling poll timeout must be cleared (equivalent to the existing
  `clearInterval` at `TradesScreen.tsx:257–260`). No dangling poll after
  the screen unmounts.

## Acceptance criteria

- [ ] **AC-1 — Backoff cadence:** On a simulated job where `opponents_done` does
  not advance for 10 consecutive ticks, the inter-poll intervals grow: ~800 ms,
  ~1200 ms, ~1800 ms, ~2700 ms, ~4000 ms (capped), ~4000 ms (capped, with jitter).
  No tick fires in < 700 ms (accounting for jitter floor).

- [ ] **AC-2 — Reset on progress:** When `opponents_done` increments after 3 no-
  change ticks (at which point the interval would be ~1800 ms), the *next* poll
  fires at ~800 ms, not at the backed-off interval.

- [ ] **AC-3 — Poll count reduction:** On a real or simulated 12 s multi-opponent
  job, the total number of poll requests is reduced by ≥ 60 % compared to the
  fixed 1500 ms cadence (fixed: ~8 polls; backoff: ≤ 3–4 polls at the same job
  length, given the early ticks are more frequent and the tail backs off).

- [ ] **AC-4 — Complete fires:** On a job that completes normally, the
  `status === 'complete'` transition is detected on the first poll tick that
  returns it. The deck-append effect at `TradesScreen.tsx:274–282` fires and
  all final cards render. The `running → complete` delay is ≤ (current interval
  + jitter), which is at most ~4.4 s at maximum backoff.

- [ ] **AC-5 — No re-render on no-change tick:** While a job's `opponents_done`,
  `opponents_total`, `cards.length`, and `status` are all unchanged, a poll tick
  does not cause a `TradesScreen` re-render. Verify with a React DevTools
  profiler trace or a render-count ref: the component render count does not
  increment on no-change ticks.

- [ ] **AC-6 — Re-render on change:** When `cards.length` increases by 1 (a new
  trade card streams in), `setJob` is called and `TradesScreen` re-renders,
  showing the new card in the deck.

- [ ] **AC-7 — Cleanup on unmount:** Navigating away from `TradesScreen` while a
  job is running cancels all pending poll timeouts. No network requests fire
  after unmount (verify in dev with a network tab or a console log in the poll
  callback that confirms it does not execute after unmount).

- [ ] **AC-8 — No regression on existing comment invariant:** The guard
  described in `TradesScreen.tsx:266–273` (same-length-different-content edge
  case) is accounted for: when `status` flips to `complete` with an unchanged
  `cards.length`, the update passes through the shallow-equal guard because
  `status` has changed.

## Related components

- `mobile/src/screens/TradesScreen.tsx:256` — `setInterval(tick, 1500)` (OBS-API-03)
- `mobile/src/screens/TradesScreen.tsx:243` — `setJob(next)` unconditional every tick (OBS-RENDER-04)
- `mobile/src/screens/TradesScreen.tsx:233–261` — poll effect with `failures` counter
- `mobile/src/screens/TradesScreen.tsx:274–282` — deck-append effect guarded by `cards.length`/`status`
- `mobile/src/screens/TradesScreen.tsx:266–273` — comment on same-length-different-content case
- `mobile/src/screens/TradesScreen.tsx:551,570–576` — JSX reading `job.*` directly (re-render trigger)
- `mobile/src/api/trades.ts:84–96` — `normalizeJobSnapshot` re-runs on every tick (OBS-API-03)
- `mobile/src/api/trades.ts:107` — `getTradeStatus(job.job_id)` call site (OBS-API-03)

## Prerequisite components / dependencies

None. This initiative is fully client-side and independent of other INITs.
It pairs naturally with INIT-11 (FR-W2-5, the `setJob` shallow-equal guard
is the same change described in both initiatives — coordinate to avoid duplicate
implementation; whichever lands first owns the guard).

## Non-functional requirements & invariants

- **No ELO or trade-fairness invariant:** This initiative modifies only the
  client-side polling cadence and render-skip logic. No `_fairness_score`, ELO
  math, or KTC values are touched. Trade generation and server-side job state are
  unchanged.
- **Idempotent polling:** The poll endpoint (`/api/trades/status`) is a read-only
  GET. Backoff changes its frequency but not its semantics. No mutation risk.
- **Battery/data:** The backoff target is ≥ 60 % poll-count reduction on a
  representative multi-opponent job (AC-3). This is a battery and cellular-data
  improvement as well as a contention reduction on the single-worker dyno.
- **Maximum cap:** The 4 s cap is chosen to bound the worst-case delay on the
  final card. A job that finishes exactly at maximum backoff waits at most ~4.4 s
  (cap + jitter) for the `complete` transition to be detected. This is acceptable
  given the job's own runtime is typically 10–15 s.
- **Rollback:** If backoff causes user complaints about delayed final cards,
  the cap can be reduced to 2.5 s with a one-line change. The shallow-equal guard
  (FR-3) is independently removable.

## Out of scope

- Server-sent events / long-poll to eliminate polling entirely (OBS-API-03
  Option B — deferred).
- Changes to `/api/trades/status` backend handler.
- Incremental normalization of the card list in `normalizeJobSnapshot`
  (`trades.ts:84–96`) — the per-tick re-normalization cost is already reduced by
  the backoff reducing poll frequency; a separate incremental-normalize refactor
  is not part of this initiative.
- Any change to the trade generation or scoring logic.
