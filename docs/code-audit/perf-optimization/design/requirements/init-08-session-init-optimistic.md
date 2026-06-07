# REQ — INIT-08: session_init Slim + Optimistic Shell

- **Initiative / Wave / Scope:** INIT-08 · Waves 2–3 · [M] + [B]
- **Source observations:** OBS-NET-04 (client optimistic shell, Wave 2), OBS-ROUTE-06 (backend defer trade-svc, Wave 2), OBS-DB-03 Option B (snapshot replay, Wave 3)
- **Peak RICE-P:** 4.0 (OBS-NET-04); OBS-ROUTE-06 (3.2) and OBS-DB-03 Option B contribute in later waves

## Problem statement

After a user picks a league, `initLeagueSession` serially awaits `session/init`, which the codebase itself estimates at 5–10 s on the Render free tier (`auth.ts:97–99`). The user sees a blocking spinner for the full duration — nothing of the app is visible until the heavyweight backend bootstrap completes. On the backend, `session/init` performs a full synchronous pool rebuild for both scoring formats, a complete swipe-history replay, tier-override loading, and a dual trade-service build with 7 days of trade decisions, all on a single gunicorn worker — regardless of whether the user intends to open Trades at all.

## User stories

- As a dynasty manager, I want to see the main app shell immediately after picking my league, so that I can start exploring while my data loads in the background.
- As a dynasty manager, I want my Trades tab to open quickly when I navigate to it, even if its data is loaded slightly after the rest of the app, so that I do not wait for trade infrastructure I may not use.
- As a developer, I want to profile `session_init` before splitting it, so that I know exactly where the 5–10 s goes and can verify the split is real.
- As a developer (Wave 3), I want session replay to seed from the stored `member_rankings` snapshot and only replay post-snapshot swipes, so that returning users with large swipe histories do not pay full replay cost on every login.

---

## Wave 2 — Client: Optimistic Main Shell (OBS-NET-04)

### Functional requirements

- **FR-1** After the three parallel prerequisite GETs complete (`getLeagueRosters`, `getLeagueUsers`, `warmPlayerCache` at `auth.ts:114–123`), the app must navigate to the Main shell without waiting for `session/init` to return.
- **FR-2** The Main shell must render in a skeleton/loading state (no data, but real navigation structure) while `session/init` is in flight.
- **FR-3** Interactive actions that require a session token (trio swipe, trade generation, tier edits) must be gated on `hasToken` — the skeleton must not allow destructive or data-writing actions before `session/init` completes.
- **FR-4** The first-paint TanStack queries (`RankScreen.tsx:77`, `TabNav.tsx:174`) must adopt the data that arrives on `session/init` completion without requiring a navigation or remount.
- **FR-5** If `session/init` fails from inside the Main shell, the error must be surfaced within the shell (retry / fallback UI) rather than bouncing the user back to the league picker.
- **FR-6** `initLeagueSession` (`auth.ts:101–162`) must fire `setLeague` / navigate to Main before the `await sessionInit(...)` at `auth.ts:151`, using the parallel prefetch data as provisional state.

### Acceptance criteria (Wave 2 client)

- [ ] AC-1 — Given a warm dyno, when the user picks a league and the three parallel GETs complete, then the Main shell is visible (skeleton navigation, tab bar, header) within 500 ms of the league pick, before `session/init` returns.
- [ ] AC-2 — Given `session/init` is in flight, when the user attempts to submit a trio swipe or trigger trade generation, then the action is blocked or shows a "loading" state — no request is sent to the server.
- [ ] AC-3 — Given `session/init` returns successfully, when the data arrives, then the rankings/trios/progress screens populate without a full navigation transition or reload.
- [ ] AC-4 — Given `session/init` returns a network error or a 4xx/5xx, when the user is already in the Main shell, then an error banner / retry affordance appears inline — the user is not navigated back to the league picker.
- [ ] AC-5 — Given `session/init` returns after the user has navigated to the Trades tab, then the Trades tab populates correctly from the deferred backend data (see Wave 2 backend FR below).

---

## Wave 2 — Backend: Defer Trade-Service Build (OBS-ROUTE-06)

### Prerequisite: profile `session_init` first

Before implementing the split, an authed timing run of `POST /api/session/init` is required to confirm the time distribution between pool build, rankings replay, and trade-service build. The 5–10 s figure is the codebase's own estimate (`auth.ts:97–99`), not a measured value. This profiling spike must happen before the split is coded, as it may reveal a different bottleneck. Add timing logs (or use an existing profiler) around:
- `_ensure_universal_pools()` block (`server.py:4478`)
- Per-format `RankingService` build + `replay_from_db` (`server.py:4569–4606`)
- Trade-service build + decision load (`server.py:4683–4690`)

### Functional requirements

- **FR-7** The trade-service build (`server.py:4683–4690`) and 7-day trade-decision load must be deferred out of the blocking `session_init` request body. They must not run on the request thread during the initial `POST /api/session/init`.
- **FR-8** The deferred trade-service build must use the existing job/lock pattern already present in the codebase to prevent duplicate concurrent builds and to signal readiness to the client.
- **FR-9** If a user opens the Trades tab before the deferred build completes, the endpoint (`/api/trades/generate` or status check) must fall back to triggering a synchronous build rather than returning an error, so that Trades always becomes available.
- **FR-10** The rankings services, universal pool, and league-member assembly must remain in the synchronous blocking section — trio cannot render without them (`server.py:4642–4643`).
- **FR-11** `session_init` must return a `"session ready"` response as soon as the blocking section completes (pool + rankings + member assembly), without waiting for the trade-service deferral.

### Acceptance criteria (Wave 2 backend)

- [ ] AC-6 — Given a profiling run of `session_init` with a real authed session, then the timing log shows a breakdown of pool build vs rankings replay vs trade-service build, confirming the split is worth making (trade-svc build is a measurable fraction of total time).
- [ ] AC-7 — Given a `session_init` POST, when the response returns, then the trade-service build has NOT started on the request thread (confirm via log that it is dispatched asynchronously).
- [ ] AC-8 — Given the user opens Trades within 5 s of league pick (before the deferred build finishes), then Trades data becomes available within the normal generation window — no permanent error state.
- [ ] AC-9 — Given the user opens Trios immediately after `session_init` returns, then trio cards render without waiting for the trade-service build to complete.
- [ ] AC-10 — Given two concurrent `session_init` requests from the same user, the job/lock pattern prevents two simultaneous trade-service builds.

---

## Wave 3 — Backend: Snapshot-Seeded ELO Replay (OBS-DB-03 Option B)

### Prerequisite: golden ELO test harness required before coding

This wave touches ELO math — a **hard cross-client invariant**. Before any code is written, a golden-value test harness must exist that:
1. Captures the full ELO output (`_compute_elo` result) for a set of fixture users by replaying from swipe history (the current path).
2. The refactored replay-from-snapshot path must produce byte-for-byte identical ELO values for the same fixture users.

This test must be in CI before the Wave 3 code ships. See `docs/cross-client-invariants.md`.

### Functional requirements

- **FR-12** At `session_init` (and equivalent paths), when the `member_rankings` table contains a stored ELO snapshot for the user/format, the `RankingService` must be seeded from that snapshot instead of replaying from swipe zero.
- **FR-13** Only swipe decisions that postdate the snapshot's `updated_at` timestamp must be replayed after seeding; the full swipe history must not be re-applied.
- **FR-14** The seeding must correctly apply the override-anchoring logic at `ranking_service.py:623–662` — this is the subtle path that the golden test harness specifically validates.
- **FR-15** If no snapshot exists (first-ever session), the full replay-from-zero path must run unchanged.
- **FR-16** Every mutation that writes to `member_rankings` (`upsert_member_rankings`, `database.py:2528`) must update the snapshot's `updated_at` so the delta-replay window is accurate.

### Acceptance criteria (Wave 3)

- [ ] AC-11 — Given the golden ELO test harness exists and is passing, when the snapshot-replay path is implemented, then all golden test cases pass with byte-for-byte identical ELO values versus the replay-from-zero path on the same fixture users.
- [ ] AC-12 — Given a returning user with 1000+ swipe decisions and a recent `member_rankings` snapshot, when `session_init` runs, then the replay only processes swipes postdating the snapshot's `updated_at`, verified by a log count of "swipes replayed" being less than the total swipe-history row count.
- [ ] AC-13 — Given a brand-new user with no `member_rankings` entry, when `session_init` runs, then the full replay-from-zero path runs without error — no fallback path is skipped.
- [ ] AC-14 — Given the override-anchoring logic at `ranking_service.py:623–662`, when tested with fixture users who have manual tier overrides, then the snapshot-seeded result matches the replay-from-zero result exactly (covered by the golden test harness, AC-11).
- [ ] AC-15 — Tier band placements (the cross-client invariant values in `docs/cross-client-invariants.md`) are identical before and after the snapshot-seeded path for all golden test fixtures.

---

## Related components

- `mobile/src/api/auth.ts:101–162` — `initLeagueSession`; serial `await sessionInit` at `:151` (OBS-NET-04)
- `mobile/src/api/auth.ts:97–99` — in-code "5–10 s" estimate comment (OBS-NET-04)
- `mobile/src/navigation/RootNav.tsx:177` — navigation trigger post-session (OBS-NET-04)
- `mobile/src/state/useSession.ts` — `switchLeague` (OBS-NET-04)
- `mobile/src/screens/RankScreen.tsx:77` — first-paint trio query (OBS-NET-04)
- `mobile/src/navigation/TabNav.tsx:174` — first-paint prefetch (OBS-NET-04)
- `backend/server.py:4431` — `session_init` POST handler (OBS-ROUTE-06)
- `backend/server.py:4478` — `_ensure_universal_pools()` (OBS-ROUTE-06)
- `backend/server.py:4569–4606` — per-format `RankingService` build + `replay_from_db` (OBS-ROUTE-06)
- `backend/server.py:4683–4690` — trade-service build + 7-day decision load (OBS-ROUTE-06)
- `backend/server.py:4642–4643` — explicit blocking comment: "Result required before /api/trio" (OBS-ROUTE-06)
- `backend/ranking_service.py:382` — `replay_from_db` (OBS-DB-03 Opt B)
- `backend/ranking_service.py:623–662` — override-anchoring logic (OBS-DB-03 Opt B)
- `backend/database.py:2528` — `upsert_member_rankings` snapshot write (OBS-DB-03 Opt B)

## Prerequisite components / dependencies

- **Wave 2 client (FR-1 through FR-6):** no hard prerequisites, but INIT-01 (decouple splash) improves the baseline first-paint; INIT-07 (persisted cache) makes the skeleton even faster on return visits. Neither is required.
- **Wave 2 backend (FR-7 through FR-11):** a profiling spike on an authed `session_init` is **required before coding** to confirm time distribution. Without measurement, the split may not yield the expected win.
- **Wave 3 (FR-12 through FR-16):** the golden ELO test harness is a **hard prerequisite** before any Wave 3 code is written. See sequencing note in `lld.md`: `golden ELO test harness ──before──► INIT-03, INIT-08-OptB, INIT-09`. Also requires that INIT-03 (ELO memoization, Wave 1) has already landed — it shares the `_version`-keyed invalidation model.

## Non-functional requirements & invariants

- **ELO math is a hard cross-client invariant.** The override-anchoring logic at `ranking_service.py:623–662` must produce identical numeric ELO output under replay-from-snapshot as under replay-from-zero, verified by byte-for-byte golden tests. Any divergence shifts tier placement across mobile, web, and extension clients. See `docs/cross-client-invariants.md`.
- **Per-format independence (cross-client invariant):** 1QB-PPR and SF-TEP are independent rank sets. The deferred build (Wave 2 backend) must not let a format switch encounter a partially-built pool for the inactive format — lazy-build must be correct per format.
- **No interactive data before token:** the client optimistic shell must gate all data-writing actions on `hasToken`. The skeleton is a visual affordance, not a functional state.
- **Measurement before implementation (Wave 2 backend and Wave 3):** the 5–10 s estimate and the ELO replay cost are code-reasoned, not measured. Both waves have explicit profiling prerequisites; do not skip them.
- **Rollback (Wave 2 client):** reverting the optimistic shell returns to the current sequential wait on `session/init`. No data is lost.
- **Rollback (Wave 2 backend):** reverting the trade-service deferral returns to the current synchronous build. The job/lock pattern already exists for other operations.
- **Rollback (Wave 3):** reverting snapshot seeding falls back to full replay — a safe degradation, only slower for heavy-history users.

## Out of scope

- Caching the universal pools across users (OBS-ROUTE-06 Option B) — pools are already idempotent per process; confirm this is working and not paying repeat cost before implementing an additional cache layer.
- Compacting `swipe_decisions` history rows (OBS-DB-03 Option C) — orthogonal hygiene; belongs in a separate initiative.
- Web-client `session_init` path — the web client uses a different authentication flow.
- Any change to K-factors, ELO_INITIAL constants, or tier band thresholds.
