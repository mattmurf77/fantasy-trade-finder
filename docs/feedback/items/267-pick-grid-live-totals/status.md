# #268/#267 — PickAssignmentScreen: saves 405ing + stale derived counts

**Covered feedback IDs:** #268, #267 (multi-ID fix, filed under the lower id
per the folder convention)
**Branch:** worktree-agent-a36d8a531dc97f0f1 (from `origin/main` @ 76cab29) ·
**Date:** 2026-08-08
**Status:** built; backend suite + mobile typecheck green.

## #268 (blocking) — "Changing picks won't save. 'Couldn't save that pick.'"

### The bug (operator, verbatim)

> "Changing picks won't save. 'Couldn't save that pick.'"

### Root cause

`mobile/src/api/pickAssignment.ts`'s `assignPick()` PUT the slot's ownership
to the literal path `/api/league/pick-assignments`, with `pick_id` carried in
the JSON body:

```ts
return api.put<AssignPickResult>('/api/league/pick-assignments', {
  league_id: args.leagueId,
  pick_id: args.pickId,
  owner_user_id: args.ownerUserId,
  if_assigned_at: args.ifAssignedAt,
});
```

The server route is registered at `/api/league/pick-assignments/<pick_id>`
(`backend/server.py:10668`, `pick_assignment_put_route(pick_id)`) — the slot
id is a URL **path segment**, read from Flask's route binding, and the
handler never reads `body["pick_id"]` at all. The only OTHER rule bound to
`/api/league/pick-assignments` (no trailing segment) is the `GET` grid route,
which does not accept `PUT`. So every save request the client actually sent
matched no PUT-capable rule and Flask answered **405 Method Not Allowed** —
not a 4xx/409 the app's typed error narrowers recognize.

`pickAssignmentErrorCode()` and `staleAssignment()` both require a JSON body
shaped like `{error: <code>}` (the latter additionally requires `status ===
409`). A bare 405 has neither, so `onError` fell through to the screen's
catch-all branch on **every single save attempt**, regardless of league,
CAS state, or the newer `suggested_order` prefill — producing the exact
"Couldn't save that pick. Try again." toast reported.

This has been broken since the route's very first commit (`791a6df`,
"draft-extensions W3: ESPN pick-assignment grid (mobile)") — the client and
server never agreed on the URL shape from day one. It is **not** the
suggested_order CAS theory (prime suspect going in): a never-assigned slot's
`if_assigned_at: null` PUT would 405 in exactly the same way as a normal
reassignment on a pristine seeded board, because the request never reaches
routing logic that would compare tokens at all. Ruled out separately:
`pick_assignment_settings`/rounds (untouched by this path), datetime
serialization in the CAS compare (never reached), and the order-PUT vs
slot-PUT split (the order route is a separate, correctly-matched `POST`).

### Fix

`mobile/src/api/pickAssignment.ts` — `assignPick()` now PUTs to
`` `/api/league/pick-assignments/${encodeURIComponent(args.pickId)}` `` and
drops the now-redundant `pick_id` body field (the server never read it).
No server change — `backend/server.py` and every existing
`backend/tests/test_pick_assignment*.py` helper already agree on
`<pick_id>` as a URL segment; the client was the one out of contract.

### Reproduction test

`backend/tests/test_pick_assignment.py::test_268_client_shaped_put_matches_the_server_route`
mimics the client's real sequence: seed the board, `GET` the grid (as the
screen does on mount), then `PUT` the EXACT body/URL shape the pre-fix
`assignPick()` sent. Asserts the request 405s with no recognizable `error`
code (proving the client-visible symptom), then asserts the corrected
`<pick_id>`-in-the-URL request against the identical body succeeds —
isolating the fix to "the URL was wrong," not a server behavior change.

## #267 — "Numbers should update after a tile is moved (don't update until user saves changes)"

### The bug

Per-slot saves already round-trip the server immediately (there is no
separate "confirm"/"save all" step — tapping an owner in the picker sheet
fires the PUT). But the on-screen derived numbers (the progress line's
"N of M assigned · K traded," each round header's "K traded" / "All
original," and the cross-season "Traded picks" summary) only reflected the
new state once that network round trip resolved and `onSuccess` patched the
cache — so a slow connection (or, before the #268 fix, EVERY save) made the
grid look like nothing happened yet, even though the user had just made a
choice.

### Fix

`mobile/src/screens/PickAssignmentScreen.tsx` — `assignMutation` gained an
`onMutate` that optimistically writes the chosen owner into the local
react-query cache and recomputes `progress` (`recomputeProgress`, new pure
helper) from that local slot list, using the SAME scope and counting rules
as the server's `_assignment_payload` (`assigned` = slots present, `traded`
= cross-season count of deviating slots, `contested`/`orphaned` = cross-season
flag counts, `total` unchanged). Tapping an owner also optimistically clears
`contested`/`orphaned` on that slot, matching the picker sheet's own copy
("Setting it here settles it.").

- `onSuccess` still applies the server's authoritative `slot`/`progress` —
  normally a no-op over the optimistic guess, and the source of truth when it
  isn't (e.g. server-side dedup logic diverges from the client's guess).
- `onError` rolls the optimistic write back via a snapshot taken in
  `onMutate`, EXCEPT the CAS-conflict branch (`staleAssignment`), which
  already replaces the guess with the server's real current row via the
  existing `applySlot(current, …)` call — the stale-token 409 path is
  unchanged.

Client-only; no route or payload contract changed, so
`docs/api-reference.md` needs no update.

## Verification

- `python3 -m pytest backend/tests -q` — 2042 passed, 1 skipped (baseline
  2041 passed / 1 skipped + the one new #268 repro test). Exit code 0.
- `cd mobile && npx tsc --noEmit` — clean, exit 0.
- Existing CAS tests (`test_w3_09_cas_stale_token_409s_with_the_current_row`,
  `test_w3_09b_blind_overwrite_of_an_assigned_row_is_never_allowed`,
  `test_w3_09c_different_slots_both_succeed`) all still pass unmodified —
  the stale-token path is untouched by either fix.
