# Seeded mutations — testing the test system (PRD M3, LLD §7)

Three deliberate breakages. Apply one at a time (never commit), run the smoke
set, and the named flow MUST go red. If it stays green, the suite has a hole —
stop and fix the suite before trusting it. Re-run this drill after any major
suite refactor and quarterly.

## M1 — revert the FB-45 401 guard (client)
**File:** `mobile/src/api/client.ts` — the 401 handler that clears the stored
token only when the sent token still matches SecureStore.
**Patch:** make the 401 branch clear the token unconditionally (delete the
match check).
**Must fail:** TC-XC-02 (401 re-mint canary — full suite), and under the smoke
set any flow that re-auths mid-run. Verifies the suite catches auth-loop
regressions.

## M2 — break the FormatGate condition
**File:** `mobile/src/screens/TradesScreen.tsx` — the single-format gate
(FB4-59) that keys off `unlocked_formats` vs the league's detected format.
**Patch:** invert the condition so the gate renders for multi-format users.
**Must fail:** TC-TRD-01 / smoke 05 (find-btn hidden behind the gate).

## M3 — swap the Check/X wiring
**File:** `mobile/src/screens/TradesScreen.tsx` — the disposition row:
`trades.like-btn` → `advance('like')`, `trades.pass-btn` → `advance('pass')`.
**Patch:** swap the two `advance()` calls.
**Must fail:** TC-TRD-06 (full suite: like lands in liked-trades). NOTE: smoke
06 only asserts advance-without-crash — it will NOT catch this one. That gap
is deliberate at smoke scope; the P0 set covers it. (If it must be smoke-visible,
add a liked-count assert to smoke 06 at the cost of one extra API-backed check.)

Build after patching (`./mobile/scripts/sim-build.sh --env test`), run, revert
the patch, rebuild. Record each drill's date + outcome below.

| Date | Mutation | Result |
|---|---|---|
| — | — | not yet run (first drill due at W1 P0 completion) |
