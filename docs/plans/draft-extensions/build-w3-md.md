# Build status — W3 M-D · live offline pick recording

**Date:** 2026-08-08 · **Status:** landed dark behind `draft.manual_picks` · **Scope:** backend + mobile
**Sources (binding):** [plan.md §6.5 M-D](plan.md) + the operator-decision block · [lld.md §2.6/§3.2/§4.6](lld.md) · [build-w3-ma-mb.md](build-w3-ma-mb.md) + [build-w3-mc.md](build-w3-mc.md) (the delivered M-A/M-B/M-C contracts this milestone builds on) · [ADR-010](../../adr/adr-010-user-asserted-pick-ownership.md)

> **This file is the delivered contract.** Where it and the LLD disagree, this file is what shipped — §6 lists every deviation and why.

---

## 1. What landed

| What | Where |
|---|---|
| `recorded_picks` table (new; `metadata.create_all` creates it, no `_migrate_db` entry needed) | `backend/database.py` |
| `record_draft_picks` (idempotent batch insert/correction/revival), `void_recorded_pick` (non-destructive), `load_recorded_picks` (live rows) | `backend/database.py` |
| `POST /api/league/recorded-picks` (batch) + `POST /api/league/recorded-picks/void` | `backend/server.py` |
| `_recorded_picks_projection` + `assigned_board(..., recorded=…)` — projects live rows into `picks[]`, subtracts from `undrafted[]`, derives `state` | `backend/draft_board_service.py` |
| Flag `draft.manual_picks` (4-touch, lands **OFF**) | `backend/feature_flags.py`, `config/features.json`, `backend/tests/fixtures/flags/release.json`, `docs/config-reference.md` |
| Shared offline-queue primitives (`uuidv4`, backoff-ladder step, disposition parser) extracted from `events.ts` | `mobile/src/api/_queue.ts` (new) — `events.ts` refactored to consume them, behavior unchanged |
| The recorder's own offline queue + API client (copies `events.ts`'s contract, `FLUSH_AT=1`, FIFO-only trim) | `mobile/src/api/recordedPicks.ts` (new) |
| `RecordPicksScreen` — the recording UI (movable cursor, one-tap record, non-destructive undo, editable team) | `mobile/src/screens/RecordPicksScreen.tsx` (new) |
| Root-stack registration (unconditional, `PickAssignment`/`DraftRoom` precedent) + deep link `app/league/record-picks` | `mobile/src/navigation/RootNav.tsx`, `mobile/src/utils/deepLinks.ts` |
| Entry point: `draft-room.record-picks` row, rendered once the ESPN board's grid is assigned | `mobile/src/screens/DraftRoomScreen.tsx` |
| Boot hook `initRecordedPicksQueue()`, mirroring `initAnalytics()` | `mobile/App.tsx` |

**Not built, deliberately:** nothing else in the W3 plan remains — M-A/M-B/M-C/M-D complete the wave. `picks_supported`, the seven read sites and provenance labelling are unchanged by this milestone; recording is orthogonal to pricing.

---

## 2. Routes — the exact delivered contract

Both gated on `draft.manual_picks`, checked **before any session work**: OFF ⇒ 404 `feature_disabled`. Both use `_gate_unverified_write`, `_require_initialized_session`, and league membership via the shared `_assignment_members` helper (403 `not_in_league`) — the same machinery M-A's routes use. **Any linked league member may record — there is no designated-recorder role** (plan §6.5), verified by `test_any_member_may_record_no_designated_recorder`.

### 2.1 `POST /api/league/recorded-picks`

```jsonc
// request
{ "league_id": "…", "season": 2026,
  "picks": [ { "event_id": "8f1c…", "overall": 3, "round": 1, "slot": 3,
               "picking_team_id": "u7", "player_id": "11635",
               "client_ts": "2026-05-11T18:02:07.113Z" } ] }
```
```jsonc
// response — the SAME reconciliation shape mobile/src/api/events.ts parses
{ "accepted": 1, "deduped": 0, "rejected": [] }
// rejected[i]: { "index": 0, "reason": "slot_out_of_range" | "unknown_player" | "not_in_league" }
```

- **Idempotency key is `(league_id, season, overall)`** — enforced by `uq_recorded_pick_slot`. A replayed batch produces `deduped`, never a duplicate row, never a 4xx.
- **Capped at 50 picks/request** (`_RECORDED_PICKS_BATCH_MAX`, mirrors the client queue's `BATCH_MAX`) — an oversized request is `400 batch_too_large` with **zero writes**, never a partial batch.
- **Validated before any write**: `round`/`slot`/`overall` positive ints, bounded against the league's stored `pick_assignment_settings` when one exists; `player_id` must resolve via `load_players_by_ids`; a non-empty `picking_team_id` must be a current `league_members` row. A batch never partially corrupts the table — invalid rows are rejected by index, valid rows in the same batch still write (`test_a_batch_never_partially_corrupts_valid_and_invalid_rows_together`).
- **Classification per row**, against any existing row at that `overall`: none → insert (`accepted`); existing **live**, same `player_id` → `deduped`; existing live, different `player_id` → UPDATE in place (`accepted`, a **correction** — the grid was wrong about the player); existing **voided**, any `player_id` → UPDATE in place (`accepted`, a **revival** — voided_at resets to NULL, which is how you reverse an undo).
- Errors: 404 `feature_disabled` · 400 `league_id is required` / `season is required` / `batch_too_large` (+`max`) · 404 `league_not_found` · 403 `not_in_league`.

### 2.2 `POST /api/league/recorded-picks/void`

```jsonc
// request
{ "league_id": "…", "season": 2026, "overall": 3 }
// response
{ "ok": true, "overall": 3, "picks": [ /* the recomputed live recorded_picks slice */ ] }
```

Sets `voided_at`; **never a DELETE**. `404 pick_not_found` when nothing live sits at that slot. Re-recording the same `overall` later revives it — there is no separate "undo the undo" endpoint, because `record_draft_picks` already handles that case.

---

## 3. Off-by-one recovery decision (task brief requirement)

**Chosen: manual-cursor-only, no auto-shift.** The task brief required picking exactly one of two options and stating why. Auto-shift (inserting a skipped pick and renumbering everything after it) was rejected for a structural reason, not a UX preference: **`overall` is the offline queue's idempotency key**, and a shift operation rewrites many rows' `overall` values in one motion — exactly the kind of write the idempotency contract cannot tolerate mid-replay (a client mid-flush during a shift could dedupe against the WRONG post-shift slot, or duplicate across a renumbering boundary). Manual-cursor-only sidesteps this entirely: `overall` never changes once assigned, correction is always a same-slot UPDATE, and the "cursor is movable" requirement (§4 below) **is** the recovery mechanism — a missed pick is fixed by tapping the correct slot and recording there directly, not by an app-computed shift.

This is documented in `docs/api-reference.md`, `docs/runbook.md` § Pick-recording queue integrity, and `docs/config-reference.md`'s flag row, and is load-bearing on the mobile side: `RecordPicksScreen`'s order list is tap-to-re-anchor on **every** row (recorded or not), which is the whole implementation of this decision.

---

## 4. The three interaction details (task brief requirement)

1. **One tap per pick.** Tap an undrafted player → `recordPick()` fires (fire-and-forget into the offline queue), the team is read off the assignment grid for the cursor's slot (never asked for), and the cursor auto-advances to the next unrecorded `pick_no`.
2. **Movable cursor.** Every row in the order list is a `Pressable` (`record-picks.order-row.<pick_no>`) that re-anchors the cursor there, whether or not that slot already has a pick — tapping a recorded row lets you inspect/undo it, tapping an unrecorded row jumps recording there. This is the highest-risk detail the brief named, and it is unconditional (no flag, no mode toggle).
3. **Off-by-one recovery** — §3 above.

**Team is editable only when the grid was wrong** (task brief, quoting M-A's own framing): the on-the-clock card defaults the team from `order[].owner_user_id` for the cursor's slot; "Change team" opens an inline picker built **only** from the grid's own owner list (`order[]`'s distinct `owner_user_id`/`owner_username` pairs), so it can never offer a team that isn't a real slot owner. The override is per-pick (`teamOverride: Map<pickNo, userId>`), not a standing correction to the grid itself — recording a pick never writes to `draft_picks` or the assignment grid.

---

## 5. Offline queue — how it was proven idempotent (task brief requirement)

**Contract copied from `mobile/src/api/events.ts`, field by field**, per the LLD's table (§4.6.1):

| Property | events.ts | recordedPicks.ts | Same? |
|---|---|---|---|
| AsyncStorage key | `ftf.events.queue.v1` | `ftf.recpicks.queue.v1` | own namespace, same `{v:1, …}` shape convention |
| Idempotency | `event_id: uuidv4()`, `crypto.getRandomValues`, never `Math.random` | identical — **same `uuidv4` function**, imported from the new shared `_queue.ts` | ✅ shared code |
| Cap | `MAX_QUEUE = 500` | `MAX_QUEUE = 500` | ✅ |
| Batch | `BATCH_MAX = 50` | `BATCH_MAX = 50` | ✅ |
| Eager flush | `FLUSH_AT = 20` | **`FLUSH_AT = 1`** | ⚠️ deliberate divergence, named in the LLD — a pick is a commitment, send immediately |
| Interval | `10_000` ms | `10_000` ms | ✅ |
| Timeout | `10_000` ms, own `AbortController` | `10_000` ms, own `AbortController` | ✅ |
| Backoff | `[30s, 2m, 10m]` ±20% jitter | identical — **same `nextBackoffStep`**, imported from `_queue.ts` | ✅ shared code |
| Reset | on consumed batch + foreground `active` | identical | ✅ |
| Trim | drop-oldest non-critical first (funnel-critical exemption) | **every pick is critical** ⇒ straight FIFO slice, and **counted** (`recordQueueDroppedCount()`) | documented divergence — no funnel-critical concept applies to a physical draft pick |
| Transport | raw `fetch`, not `apiRequest` (401 handling would clear the session token) | identical | ✅ |
| Reconciliation | `{accepted, deduped, rejected, disposition}` | `{accepted, deduped, rejected}` — no `disposition` (recording has no "disabled" business state; the surface is either flag-on or the route 404s) | ✅ — `parseQueueDisposition` treats a missing `disposition` as the no-op case, shared code |
| Guards | `inFlight`, try/catch-swallowed everywhere | identical | ✅ |

**Extraction, not duplication.** `uuidv4`, the backoff-ladder step function, and the disposition-parsing ladder (5xx retry / non-OK drop / disabled / batch-rejected drop / sum-driven purge) moved to a new `mobile/src/api/_queue.ts`; `events.ts` was refactored to call the shared functions with its exact original branch order preserved (the 5xx/non-OK short-circuit still happens **before** the response body is even parsed, matching the pre-extraction control flow byte-for-byte). `recordedPicks.ts` builds its own queue/flush loop structurally identical to `events.ts`'s — the stateful loop itself was **not** shared (see `_queue.ts`'s header comment for why: it is a battle-tested production path carrying analytics-specific concerns like the kill-switch flag gate and funnel-critical trim, and refactoring it into a shared generic class neither queue's tests were written against was judged a bigger, riskier change than the task needed).

**How idempotency was proven** (`backend/tests/test_recorded_picks.py`):
- `test_replay_is_idempotent_twice_with_zero_duplicates` — records a full batch, then replays it **twice**; both replays return `{accepted:0, deduped:N, rejected:[]}`, the raw table never grows past N rows, and the board payload is byte-identical across all three calls. This is the task brief's exact bar: *"an airplane-mode session of a full draft must replay to identical server state on reconnect, twice, with zero duplicates."*
- `test_two_devices_recording_the_same_pick_dedupe_on_overall_not_event_id` — two different `event_id`s (simulating two devices) targeting the same `overall` dedupe correctly, proving the SERVER key is the slot, not the client uuid.
- `test_correction_updates_in_place_never_a_second_row` and `test_void_is_non_destructive_and_re_recording_revives_it` — the two non-dedupe write paths (correction, revival) each verified to touch exactly one row.
- Verify-failing-first: the dedup branch was disabled (`prior = None`) and confirmed **both** idempotency tests go red before being reverted; a dead reference to `replace_draft_picks` was injected into `record_draft_picks` and confirmed the D18 AST test catches it; the flag gate on the board's read was removed and confirmed the flag-off byte-identity test catches it.

---

## 6. Board wiring — the ONE existing renderer

`draft_board_route`'s ESPN branch (already gated on `picks.assign`) now ALSO reads `load_recorded_picks(league_id, season)` when `draft.manual_picks` is on, and passes the rows into `assigned_board(..., recorded=…)`. Inside `draft_board_service.py`, `_recorded_picks_projection()` maps live rows to the **identical** `picks[]` shape every other platform's board renders (`{round, pick_no, slot, player_id, name, position, team, picked_by_user_id, picked_at}`), and `assigned_board`'s `drafted` set (fed into the shared `_undrafted()` helper) is derived from that projection — so a recorded player disappears from `undrafted[]` through the exact code path Sleeper/MFL boards already use. `state` is now derived (`complete` when every `order[]` slot has a pick, `live` when ≥1 does, `upcoming` otherwise) rather than hard-coded `upcoming`.

**No mobile change was needed to VIEW the board** — `DraftRoomScreen`'s `BoardSection`/`UndraftedSection` already match `picks[]` to `order[]` by `(round, slot)` and already render `undrafted[]` verbatim, so recorded picks appear on the existing Draft Room the moment the board route returns them. The only mobile work was the recording INPUT surface (`RecordPicksScreen`) and its entry point.

**Flag-off is byte-identical even with rows in the table**, not just with an empty one: `draft_board_route` only calls `load_recorded_picks` at all when `draft.manual_picks` is on, so a row left over from a flag that was flipped on and back off never leaks into a flag-off board (`test_flag_off_board_is_byte_identical_even_with_rows_in_the_table` inserts a full batch directly via `db.record_draft_picks` — bypassing the correctly-404'd route — and confirms the board is unchanged).

---

## 7. Flag behaviour (`draft.manual_picks`, ships **OFF**)

| Off | On |
|---|---|
| Both routes 404 `feature_disabled` before any session work | The routes answer |
| `GET /api/draft/board`'s ESPN branch never calls `load_recorded_picks` — zero reads, not just zero writes | The board projects live rows into `picks[]`/`undrafted[]` |
| `recorded_picks` stays unwritten | Written by `record_draft_picks`/`void_recorded_pick` |
| `RecordPicksScreen` renders its own honest unavailable state (defense in depth for a stale deep link); the Draft Room's entry row does not render at all | The entry row appears once the ESPN board's grid is assigned; the screen is fully functional |

Independent of `picks.assign_tradeable` — recording is about **what happened**, pricing is about **what it's worth**; the two have no read/write overlap (`recorded_picks` never feeds any of the seven pricing read sites).

---

## 8. Tests

`backend/tests/test_recorded_picks.py` — 23 tests, 3 verify-failing-first mutations confirmed red.

| Criterion | Test |
|---|---|
| D10 flag-off, zero writes | `test_flag_off_both_routes_404_before_any_session_work` |
| D10 flag-off, byte-identical board (the read is gated too) | `test_flag_off_board_is_byte_identical_even_with_rows_in_the_table` **VFF** |
| Board wiring — projection shape, undrafted subtraction, state | `test_record_batch_accepts_and_projects_into_the_board`, `test_recording_every_slot_completes_the_board`, `test_recorded_picks_projection_shape_matches_the_shipped_pick_schema`, `test_empty_recorded_is_the_exact_m_b_payload` |
| Idempotency / replay (INV-12, the zero-tolerance bar) | `test_replay_is_idempotent_twice_with_zero_duplicates` **VFF**, `test_two_devices_recording_the_same_pick_dedupe_on_overall_not_event_id` **VFF** |
| Correction | `test_correction_updates_in_place_never_a_second_row` |
| Non-destructive undo + revival | `test_void_is_non_destructive_and_re_recording_revives_it`, `test_void_of_a_never_recorded_slot_is_pick_not_found` |
| Validation / rejection reasons | `test_unknown_player_is_rejected`, `test_picking_team_not_in_league_is_rejected`, `test_slot_out_of_range_is_rejected`, `test_non_positive_overall_is_rejected`, `test_a_batch_never_partially_corrupts_valid_and_invalid_rows_together`, `test_batch_too_large_is_refused_with_zero_writes` |
| Membership / no designated recorder | `test_a_non_member_cannot_record_or_void`, `test_any_member_may_record_no_designated_recorder` |
| D18 / INV-6 — `overall` never reaches `draft_picks` | `test_d18_recording_never_touches_draft_picks_or_draft_status` (AST) **VFF**, `test_d18_runtime_no_draft_picks_row_gains_an_overall_key` (behavioral) |
| O9 survives | `test_o9_survives_recording_never_writes_draft_status` |
| Flag mirror (4-touch) | `test_manual_picks_flag_is_registered_lands_off_and_is_mirrored` |

**Gate:** `python3 -m pytest backend/tests -q` → **1988 passed, 1 skipped, exit 0** (baseline 1965 passed / 1 skipped — every new test is additive, zero regressions). `cd mobile && npx tsc --noEmit` → clean, exit 0. `node mobile/tests/check-member-entered-marker.js`, `check-mock-mode-marker.js`, `check-feedback-badge.js`, `check-session-rerank.js` → all pass (none of this milestone's files are in their scope, confirming no collateral damage to the structural checks the prior W1/W2/M-C waves left behind).

---

## 9. Deviations from the LLD

| # | LLD said | Shipped | Why |
|---|---|---|---|
| 1 | `void_recorded_pick`'s route "returns the recomputed board slice" (§4.6.2) | Returns `{ok, overall, picks}` — the **live `recorded_picks` rows** for the season (`round, slot, overall, picking_team_id, player_id, recorded_at`), not a full `assigned_board` re-render | A full board re-render needs the assignment grid AND the universal consensus pool re-resolved server-side for no reason the client needs — the client already holds the board and only needs to know what changed. The raw rows are enough to patch local state; a full re-fetch (which the recording screen already polls on a 15s interval) catches up the rest. |
| 2 | The LLD's `record_draft_picks` docstring frames voided-then-re-recorded as "the SAME player_id" reviving (§4.6.2) | Revival fires for **any** `player_id` at a voided slot, not just the same one | A voided slot's next recording IS a correction by definition — the grid was wrong, someone undid the wrong entry, and the next tap (same or different player) should land as one write, not require the recorder to know whether their fix happens to match the pre-void value. Tightening to "same player only" would silently reject the more common case (undo because the WRONG player was recorded, then record the RIGHT one). |
| 3 | `rejected[i].reason` enumerates `slot_out_of_range \| unknown_player \| not_in_league \| voided` (§2.6) | Only the first three are ever returned; `voided` is never emitted | No scenario in the shipped design rejects on a voided slot — recording always either inserts, dedupes, corrects, or revives (deviation #2), so there is nothing left for a `voided` rejection to mean. Kept the type comment noting this so a future builder does not "fix" a missing case that was never reachable. |
| 4 | Off-by-one recovery — the plan left this as an open choice between two named options | Manual-cursor-only, no auto-shift | See §3 above — the structural argument (idempotency key stability) made this the only safe choice, not a coin flip. |
| 5 | The shared queue extraction — the LLD says "extract... into a shared `mobile/src/api/_queue.ts`" without specifying scope | Only the PURE pieces (uuidv4, backoff step, disposition parser) were extracted; the stateful queue loop was NOT — each queue keeps its own `flush`/`ensureInit`/module state | Reimplementing `events.ts`'s production flush loop as a shared generic class would have been a materially bigger, riskier change to a live analytics path than this task needed, and neither queue's existing tests were written against a shared class. The extraction still satisfies "do not invent a second contract" — both queues now provably share the same idempotency-key generation and backoff math, which is the part that actually needs to never drift. |

---

## 10. Residual risks (accepted, named)

1. **No offline-mode integration test exists** — the idempotency proof (§5) exercises the SERVER'S idempotency guarantee directly (replaying the same batch through the route twice), which is the part that must never regress; it does not exercise React Native's `AppState`/network-loss simulation end-to-end. The client queue's structure (verbatim-copied from `events.ts`, which itself has no such end-to-end test either) is the existing bar in this codebase.
2. **The team override is per-recorded-pick, not a standing grid correction.** If the grid was wrong for an entire round, each recorded pick in that round needs its own team override tap; there is no "fix the grid retroactively for already-recorded picks" bulk action. Acceptable for V1 — a systematically wrong grid is caught by the M-A assignment screen's own review step before a live draft starts, not discovered mid-recording.
3. **`recordQueueDroppedCount()` is a test/observability hook only** — nothing wires it to an analytics event today (deliberately: no new `track()` calls were added, to avoid touching the strict default-deny analytics taxonomy for a counter this wave's scope did not require). A production drop would currently only be visible via this exported function in a debug build, not a dashboard.
