# G9 review — round 1 (critic: planner agent, 2026-08-16)

> Scope of review: `prd.md` + `scope.md` (final versions, both mtime 00:21)
> against `origin/main @ 0b2dcee`, with an independent re-hunt of every
> cache-repopulation path. Verdict: **sound with 1 BLOCKING correction** —
> the core plan claims survived intact, and the author's four corrections to
> the plan (base re-anchor, P6, no-jest respec, `fonts.data`) are all
> **verified correct** by this critic. Objections below; everything not
> objected to is affirmed.

## Independent verifications performed (all pass)

- **Seventh-path hunt: none found.** Every write/invalidation touching
  `['matches','all']` / `['awaiting-trades']` on `0b2dcee` is P1–P6:
  grepped all `setQueryData` / `invalidateQueries` / `prefetchQuery` /
  `fetchQuery` / `cancelQueries` / `removeQueries` / `resetQueries` /
  `queryClient.clear` sites in `mobile/src` + `App.tsx`. Writers outside
  MatchesScreen: `TabNav.tsx:747` (P5), `TradesScreen.tsx:3323` (P6),
  `useSession.ts:455-456` (P4) — nothing else. Specifically checked and
  clean: `revalidateSession` (FB-45 foreground re-mint, `useSession.ts:344-375`)
  invalidates **nothing**; `utils/deepLinks.ts` has no query writes; no bare
  `invalidateQueries()`; the focusManager IS AppState-bridged
  (`App.tsx:211-216`) but `refetchOnWindowFocus: false` keeps both keys out
  of focus refetch — the PRD's "no focus refetch" claim holds *today* (see
  NB-5 for the one-line insurance ask).
- **§V corrections verified:** `fonts.data` = `IBMPlexMono_500Medium`
  (`chalkline.ts:92`), no `fonts.mono` anywhere; no jest in
  `mobile/package.json`, transpile-under-node idiom confirmed
  (`check-trade-text.js:19-23`); `ux.swipe_undo: true` at
  `config/features.json:117`; route decorator `server.py:13254`,
  server-fired events `:13320`/`:13359`, taxonomy `analytics_taxonomy.py:433`;
  repo-wide `cancelQueries` only at `PickAssignmentScreen.tsx:459`; D-056
  present in `DECISIONS.md`.
- **Pin-range cites are accurate:** R-4's "7–12 + 13–21" and R-5's "15–18"
  match the real assertion list in `check-awaiting-dismiss.js` (verified
  against the suite's 21 named assertions).
- **CW-1's mounted-tab premise verified:** `TabNav.tsx` sets no
  `unmountOnBlur` / `freezeOnBlur` / `detachInactiveScreens` — tab screens
  stay mounted after first visit, so `hiddenKeys` state survives tab
  switches as claimed (see NB-4 for the belt-and-braces note).
- **Chalkline:** R-11 size 11 + S-11e's `fontSize ≥ 11` pin satisfy the
  11px floor; bare-mono-numeral (not CountBadge) is the correct convention
  read. **R-7's cost is honestly stated** (extra GET per visit + P3 now
  includes the key off-segment). **scope.md** W-1/W-2 are concrete, cited,
  and routed to operator sign-off before build — compliant with the gates.

---

## BLOCKING

### B-1 — R-2's accepted-flicker rationale cites the wrong mechanism; specify the unhide ordering instead (prd.md § R-2, lines "Accepted micro-window…")

R-2 accepts a "≤1 refetch of flicker" in the "POST succeeded but GET still
stale" case and dismisses it because "the backend filter makes [it]
impossible in practice." That justification is wrong on the mechanism: the
backend `retracted_at` filter (`database.py:7090`) governs GETs that read
**after** the dismiss commits. The real residual window is a **GET racing
the POST's commit**: a refetch that *starts after* `onMutate`'s
`cancelQueries` (so it isn't cancelled — e.g. P2/P3/P6 firing during the
POST round-trip), reads the row **pre-commit** server-side, and resolves
before `onSettled` unhides. Then `onSettled` unhides against a cache that
contains the resurrected row until the `onSuccess` invalidate's refetch
lands — reproducing the exact #334 symptom for one round-trip. No backend
filter can close that; it's an ordering problem in the client lifecycle.

**Required fix (spec text; ~1 line of build code):** specify the unhide
ordering in R-2 —
- `onError`: unhide **immediately** (row honestly returns, unchanged);
- `onSuccess`: unhide **after the reconcile refetch resolves** — i.e.
  `await queryClient.invalidateQueries({ queryKey })` (it returns a promise
  that settles when the refetch completes) *then* clear the key — instead
  of a bare unconditional `onSettled` clear.

This deletes the accepted window entirely at zero complexity cost and makes
the "no tile hidden forever" guarantee still hold (`invalidateQueries`
settles even on refetch failure). Update S-10c to pin the ordered clear
(success path clears after the awaited invalidate; error path clears in
`onError`), and drop or correct the "backend filter makes it impossible"
sentence. If the author prefers to keep the bare `onSettled` clear, the PRD
must instead state the *correct* residual mechanism and accept it
explicitly — but given the fix is one awaited call, adopt the ordering.

---

## NON-BLOCKING

### NB-1 — R-3's P6-cancellation consequence is mis-described (prd.md § R-3)

"A cancelled P6 `fetchQuery` rejects into its own `.catch` → `decide(false)`
→ the N6.1 beat **defers to a later focus**" — wrong last clause.
`decide(false)` calls `v2ShowN61(false)` (`TradesScreen.tsx:3316-3325`): the
bubble **shows now, with the router-less copy variant**; nothing defers.
Same benign conclusion, but CW-1 shouldn't inherit the wrong description.
Correct the clause.

### NB-2 — Dismiss → app-background/kill during the undo window is unspecced (prd.md §§ R-2/R-4, TF checklist)

iOS suspends JS timers in background: a dismiss backgrounded mid-window
fires its POST on **resume** (hidden tile persists — fine); an app **killed**
before resume never sends the POST and the row honestly returns next launch
("my dismiss didn't stick"). This is pre-existing #318/S3-PRD-03 semantics,
unchanged by G9 — but the PRD is silent and TF-4 covers only tab-switch.
Add one sentence to R-4 declaring it known, unchanged, out-of-scope (an
`AppState → 'background'` flush would be the hardening if the orchestrator
ever wants it; do **not** absorb it silently into this Polish group).

### NB-3 — Undo racing the flush timer: state the no-op (prd.md § R-4)

Undo tapped at the ~5s boundary after `flushPendingDismiss` ran is a no-op
(`pendingDismissRef` already null, `:358-361`) — tile stays dismissed while
the toast that offered Undo is disappearing. Exposure is frame-level because
the toast `holdMs` and the timer are the same 5000ms started in the same
tick, and behavior is unchanged from shipped. One sentence in R-4 so the
contract is complete rather than silent. Related, same sentence can note:
undo's snapshot-restore (`p.prev`) can overwrite a fresher mid-window
refetch result until the next refetch — also pre-existing, also unchanged.

### NB-4 — CW-1 should cover the unmounted-tab branch too (prd.md § CW-1)

The mounted-tab premise is true today (verified, no `unmountOnBlur` /
`freezeOnBlur`), but CW-1's P6 argument should add the one-line dual: if the
screen ever *were* unmounted, the unmount cleanup flushes the POST first
(`:374-377`), so lost `hiddenKeys` state is harmless — the row is being
retracted and `onMutate` re-filters the cache. Makes the proof robust to a
future navigation-config change instead of resting on it.

### NB-5 — Pin the focus-refetch assumption (test plan § S-10 or S-11)

§V's "no focus refetch" rests on `refetchOnWindowFocus: false`
(`queryClient.ts` default) while the focusManager bridge is live
(`App.tsx:211-216`). Cheap insurance: one structural assertion that neither
`matchesQuery` nor `awaitingQuery` sets `refetchOnWindowFocus: true` (or
that the default stays false), so a future per-query override can't silently
mint a seventh repopulation path that CW-1 never analyzed.

### NB-6 — Cosmetic cite drifts (no action beyond touch-up)

`scope.md` §1: `match_dismiss_undone` emitter is `MatchesScreen.tsx:365`,
not `:363`. prd.md § R-11 cites `chalkline.ts:93` for `fonts.data`; the
`data:` line is `:92` (the `fonts` block spans `:85-94`). Neither affects
substance.

---

## Verdict

**1 BLOCKING (B-1), 5 NON-BLOCKING + 1 cosmetic.** With B-1's ordering fix
(and ideally NB-1's correction folded into the same edit), the PRD is a
buildable contract: verdicts preserved from the plan, P1–P6 independently
confirmed exhaustive, tests map to requirements with honest
TestFlight-only-runtime disclosure, Chalkline compliant, scope waivers
properly surfaced. No path upgrade — still client-only Polish.

---

## ROUND 2: SIGNED OFF (critic, 2026-08-16)

Every round-1 disposition is reflected in the doc text, not merely claimed
in the reconciliation log — verified line-by-line: B-1's ordered unhide is
in R-2 (onError immediate; onSuccess only after `await
queryClient.invalidateQueries(...)` resolves) with the corrected
GET-racing-the-commit mechanism and the retracted backend-filter sentence,
pinned by S-10c's "unhide before await" named sabotage and traced in
CW-1(d); NB-1's correction is in R-3 (cancelled P6 → `v2ShowN61(false)`
shows immediately with the router-less variant — and the new
`TradesScreen.tsx:3252-3268` cite is accurate, it is the `v2ShowN61`
definition); NB-2 and NB-3 are declared in R-4 (background/kill semantics
and the undo-vs-flush no-op + stale-snapshot note, all explicitly known,
unchanged, out of scope); NB-4's flush-first unmounted-tab dual is CW-1(f);
NB-5's pin is S-10e; scope.md §1 now cites `:365`. On NB-6's rejected half
I **concede**: `fonts.data` is at `chalkline.ts:93` (`uiBold` at `:92`,
block opens at `:86`) — my `:92` claim was an off-by-one in my own sed
offset, and the PRD's original cite stands. R-5's "unhidden immediately in
onError" stays consistent with the new R-2. No new defects found; no
settled objection re-litigated. The PRD + scope are a buildable, Polish-path
contract — **G9 Phase 1 signed off for build.**
