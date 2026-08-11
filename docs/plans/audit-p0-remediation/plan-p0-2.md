# P0-2 — A failed trade search is indistinguishable from never having searched

> Plan for the mobile-UX-audit remediation item P0-2 (Bug, effort S). Verified against
> worktree `/Users/teresadickens/Documents/Claude/Projects/ftf-p0-remediation`, branch
> `p0-remediation-2026-08-10`, HEAD `ab9368f`. Planning only — no code changed.

- [Verified current state](#verified-current-state)
- [Design](#design)
- [Exact change list](#exact-change-list)
- [Surface changes](#surface-changes)
- [Maestro delta](#maestro-delta)
- [Docs impact](#docs-impact)
- [Test plan](#test-plan)
- [Risks and open questions](#risks-and-open-questions)

Sources: `docs/business/product/2026-08-09-mobile-ux-audit/07-build-handoff-prompt.md` §P0-2,
`04-priority-backlog.md` §P0-2, `06-resolutions.md` §P0-2. Root `CLAUDE.md` §Conventions.

---

## Verified current state

The audit's finding holds. Every line below was re-read in this worktree; the audit's
line numbers have drifted (the ladder's fallback is `:4910-4918` at audit time and
`:4910-4918` here — unchanged — but the ladder gained an `error` guard at `:4822` that
the audit did not cite, and it turns out to *cause* a second bug, below).

### Three failure paths, none of which leave a persistent trace

**Path A — `POST /api/trades/generate` fails outright (manual tap).**
`mobile/src/screens/TradesScreen.tsx:1222-1241` — `generateMutation.onError`. For a manual
tap (`vars.auto` falsy) the entire handler is:

```
setToast({ msg: e.message || 'Generate failed', tone: 'warn' });
```

`job` is untouched (stays `null` on a first search). The toast auto-dismisses; `ux.toast_v2`
is **on** (`config/features.json`), so a `warn` toast holds ≥5000 ms (`Toast.tsx:39,55-60`)
and then vanishes with nothing behind it.

**Path B — job starts, then errors during polling (`status:'error'`, `job.error` populated).**
`TradesScreen.tsx:1256-1315` is the poll loop. On a successful poll the shallow-equal guard
at `:1272-1278` sees `next.status !== job.status` and calls `setJob(next)`, so `job.status`
becomes `'error'` and `job.error` is populated. The loop then only re-schedules when
`next.status === 'running'` (`:1292-1294`), so polling stops correctly — and **nothing else
happens**. `job.error` is read nowhere in the file (grep for `job.error` / `job?.error`
returns zero hits outside the type). Confirmed.

**Path C — poll abandoned after four consecutive failures.**
`TradesScreen.tsx:1295-1307`:

```
failures += 1;
if (failures >= MAX_POLL_FAILURES) {            // MAX_POLL_FAILURES = 4 (:1260)
  setToast({ msg: 'Network hiccup — try Find a Trade again in a moment', tone: 'warn' });
  setJob(null);
}
```

`setJob(null)` erases the only evidence a search happened. The resolutions doc's claim
("after four consecutive failures the job is cleared into the same ambiguous state") is
**verified exactly**.

### Why all three land on the never-searched card

The deck slot is a single ternary ladder inside `styles.deckWrap`
(`TradesScreen.tsx:4569-4919`). In order:

| # | Line | Condition | Renders |
|---|---|---|---|
| 1 | `:4576` | `quicksetPromptShown` | `QuickSetPromptCard` |
| 2 | `:4583` | `adaptationMoment && topCard` | adaptation card |
| 3 | `:4613` | `topCard` | the deck |
| 4 | `:4819-4823` | `firstRun && deck.length===0 && job?.status!=='complete' && job?.status!=='error' && !autoGenFailed` | `SkeletonTradeCard` |
| 5 | `:4830` | `generateMutation.isPending \|\| job?.status==='running'` | "Looking for trades…" |
| 6 | `:4845` | `deck.length>0 && summaryVisible` | deck-done summary |
| 7 | `:4876` | `deck.length>0` | "That's all for now" |
| 8 | `:4910-4918` | *(fallback)* | **`trades.empty-text` — "Hit \"Find a Trade\" to start"** |

With an empty deck and no job running, all three failure paths fall through 1–7 and land on
row 8. `screens/mobile/trades/error.png` vs `empty.png` confirms it visually: below the
toast the two frames are the same "FULLY GUIDED" headline, the same ice `Find a Trade`
button, and the same "HIT \"FIND A TRADE\" TO START" card.

### Two additional defects found during re-verification (both in scope)

**(i) First-run + Path C = an infinite skeleton.** Row 4 excludes `job?.status === 'error'`
but Path C sets `job` to `null`, so `job?.status` is `undefined` — the exclusion misses.
`autoGenFailed` is only set from the *POST* auto-retry path (`:1235-1236`), never from the
poll. And the auto-start effect at `:1397-1406` refuses to re-kick because
`autoGenRef.current !== 'idle'`. Net: a first-run user whose polling dies sees
`SkeletonTradeCard` **forever**, with no button state to explain it. This is strictly worse
than the audit's finding and the fix closes it for free (row 4 must also exclude the new
failure state).

**(ii) `job.error` is a raw Python exception string, not user copy.** `backend/server.py:5241-5248`:

```
except Exception as e:
    log.exception("trade-job %s failed", job_id)
    ...
    j["status"] = "error"
    j["error"]  = str(e)
```

plus the reaper at `backend/server.py:2526-2529` which sets `j["error"] = "timeout"`.
`_trade_job_public_view` (`backend/server.py:2696-2707`) passes `job.get("error")` through
verbatim, and `normalizeJobSnapshot` (`mobile/src/api/trades.ts:250`) keeps it as-is.
So the handoff's instruction to "render the backend message" cannot be taken literally for
Path B — see [Design](#design) and [Risks](#risks-and-open-questions).

### The existing error mapping to reuse

- `mobile/src/api/client.ts` builds `Error.message` for a failed request from
  `parsed.message || parsed.error` — for a real 500 that is the curated string
  `"Unexpected server error."` from `backend/server.py`'s `handle_unexpected_error`
  (confirmed by the capture flow's own note, `mobile/.maestro/capture/trades.yaml:70-76`).
  So **Path A messages are already user-safe**; Path B's are not.
- `mobile/src/utils/verification.ts:16` — `readErrorCopy(err, fallback)` swaps in
  `"Verify your account to view your data."` for a `verification_required` 403 and
  otherwise returns the fallback. `/api/trades/status` is a gated read
  (`docs/api-reference.md:101`), so this mapper is load-bearing here.

### The Rank tab pattern to mirror

There is **no shared error-state component** anywhere in `mobile/src/`. The pattern is
copy-pasted; the canonical instance is `mobile/src/screens/TiersScreen.tsx:1336-1345`:

```
) : rankingsQuery.isError ? (
  <View style={styles.centered}>
    <Text style={styles.errorText}>Could not load rankings.</Text>
    <Button variant="ghost" compact label="Try again" onPress={() => rankingsQuery.refetch()} />
  </View>
```

with `errorText: { ...type.body, color: semantic.neg }` (`TiersScreen.tsx:1799`) and
`centered: { flex:1, alignItems:'center', justifyContent:'center', gap: space.sm }` (`:1793`).
Identical at `QuickRankScreen.tsx:401-410`, `QuickSetTiersScreen.tsx:582-591`,
`RankScreen.tsx:573-586` (trios; renders `error.message` when it is an `Error`), and
`ManualRanksScreen.tsx:638-649` (wraps in `readErrorCopy`, uses `variant="secondary"`).
`PickAnchorScreen.tsx:244-278` is the most evolved: pull-to-refresh + a `Retry` button
disabled while fetching, plus `useRecoverOnResume(poolQuery)` (`:106`).
`screens/mobile/tiers/error.png` shows the treatment: **red centred copy + a quiet
"Try again" button**, unmistakably not an empty state.

**No Rank-tab error state carries a testID.** `docs/plans/mobile-testing/lld.md` Appendix A
(`:315-331`) reserves `trios.retry-btn` / `leagues.retry-btn` / `calc.retry-btn`, none
implemented. Existing implemented convention elsewhere: `draft-room.error-text`,
`mock-draft.error-text`, `signin.error-text`.

### The toast z-order / offset defect

`Toast.tsx:143-151`:

```
wrap: { position: 'absolute', top: space.xxl, left: 0, right: 0, alignItems: 'center', zIndex: 50 },
```

`space.xxl` is 32 (`mobile/src/theme/chalkline.ts:74`). The Toast is mounted as the first
child of `TradesScreen`'s `SafeAreaView` (`:3316-3323`), i.e. at screen-content top; the
ScrollView's content starts at `padding: space.lg` = 16 (`styles.scroll`, `:5473`) and its
**first** child is the mode bar (`TradeFinderModeBar`, `:3448-3469`, or `TradeHomeUtilityRow`
under the `trades_home_inline` experiment, `:3438-3446`). The chip row is 36 pt tall
(`TradeFinderModeBar.tsx:163`), so it occupies roughly y = 16…52 while the toast bubble
occupies y = 32…~75. They overlap. `screens/mobile/trades/error.png` shows exactly that:
"Guided" clipped to "G" and "Free agents" clipped to "…ts" behind the toast bubble.
This is not a z-order bug — the toast *should* be on top — it is a **vertical offset** bug.

---

## Design

### State machine

One new piece of screen state is the single source of truth for "the last search failed",
so the three paths converge instead of each growing their own branch.

```
type DeckFailure = {
  kind: 'generate' | 'poll_abandoned' | 'job_error';
  message: string;      // already user-safe; never a raw exception string
} | null;

const [deckFailure, setDeckFailure] = useState<DeckFailure>(null);
```

Transitions:

| Trigger | Site | Action |
|---|---|---|
| Manual generate POST fails | `onError`, `:1240` | `setDeckFailure({kind:'generate', message: readErrorCopy(e, GENERIC)})` — **in addition to** the existing toast, unchanged |
| Auto (first-run) generate POST fails twice | `onError`, `:1235-1236` | after `setAutoGenFailed(true)`, also `setDeckFailure({kind:'generate', message: GENERIC})` |
| Poll returns `status:'error'` | new effect keyed on `job?.status`/`job?.error` | `setDeckFailure({kind:'job_error', message: jobErrorCopy(job.error)})` |
| 4 consecutive poll failures | `:1298-1303` | `setDeckFailure({kind:'poll_abandoned', message: NETWORK})` alongside the existing toast + `setJob(null)` |
| User taps Find a Trade / Retry | `handleFindTrades`, `:732-738` | `setDeckFailure(null)` **first**, before `mutate` |
| Generate succeeds | `onSuccess`, `:1197` | `setDeckFailure(null)` |
| League switches | `:1356-1380` | `setDeckFailure(null)` |
| Fairness toggled (deck reset) | `handleToggleFairness`, `:740-756` | `setDeckFailure(null)` |

Mirroring `job.status === 'error'` into `deckFailure` via an effect (rather than reading
`job?.status === 'error'` at render time) is deliberate: it makes **recency** correct. If
the user retries after a job error and the retry's POST fails, the stale errored `job` is
still in state; a render-time read would show the older job's message. One funnel, last
write wins.

`job.status === 'error'` is *not* cleared — row 4's existing guard at `:4822` and the
`Find a Trade` button's label/disabled logic (`:4237-4241`) keep reading it unchanged.

### Where it renders

A new branch inserted **between rows 7 and 8** of the ladder (i.e. immediately before the
never-searched fallback at `:4910`), plus row 4 gains `&& !deckFailure`:

```
Row 4:  firstRun && deck.length===0 && status!=='complete' && status!=='error'
        && !autoGenFailed && !deckFailure          ← added; closes defect (i)
...
Row 7:  deck.length > 0                             ← unchanged
Row 7b: deckFailure                                 ← NEW
Row 8:  fallback "Hit Find a Trade to start"        ← unchanged
```

Placing it *after* row 5 means a retry in flight immediately swaps to "Looking for trades…",
and placing it *after* row 7 means a job that errors mid-stream with cards already banked
keeps showing the deck rather than blanking it (partial results are still results). That
partial case is deliberately left with no inline notice — see
[Open questions](#risks-and-open-questions).

### Visual treatment

Mirrors the Rank pattern (red `semantic.neg` copy + a quiet retry) inside the deck slot's
existing `<Card>` + `styles.emptyInner` container, because every other deck-slot state is a
Card and the slot must keep its layout.

```
<Card>
  <View style={styles.emptyInner} testID="trades.deck-error">
    <Text style={styles.deckErrorTitle}>Search failed</Text>
    <Text style={styles.emptyBody}>{deckFailure.message}</Text>
    <Button
      testID="trades.deck-error.retry"
      label="Try again"
      variant="secondary"
      compact
      onPress={() => handleFindTrades('deck_error_retry')}
    />
  </View>
</Card>
```

New style key only:

```
deckErrorTitle: { ...type.heading, textAlign: 'center', color: semantic.neg },
```

`type.heading` is the uppercase display ramp already used by every deck-slot headline
(`emptyTitle`, `:5818-5821`), so "SEARCH FAILED" renders in the same voice as "DECK DONE"
and "HIT \"FIND A TRADE\" TO START" — but in `semantic.neg` (#EF4444), which no valid empty
state uses anywhere in the app. That single colour difference is what makes the states
non-confusable at a glance; the copy makes it explicit.

`variant="secondary"` (not Rank's `ghost`): the deck slot's other in-Card actions are
`secondary`/`primary` compact (`:4860-4872`), and `ghost` inside a Card reads as disabled.
This matches `ManualRanksScreen.tsx:644`.

`semantic` must be added to the theme import in `TradesScreen.tsx` — confirm it is not
already imported before editing.

### Copy

All strings are constants near the mutation so the mapper and the renderer can't drift.

| Constant | Value |
|---|---|
| `GENERIC` | `We couldn't finish that search — the server may still be waking up. Try again.` |
| `NETWORK` | `We lost the connection while searching. Your league is fine — try again.` |
| `TIMEOUT` | `That search took too long. The server may still be waking up — try again.` |

`jobErrorCopy(raw)`:

```
'timeout'  → TIMEOUT
anything else (including null) → GENERIC
```

**`job.error` is never echoed verbatim.** It is `str(e)` of a server-side Python exception
(`server.py:5247`) — e.g. `KeyError: 'roster'`. This is a deliberate deviation from the
handoff's "render the backend message"; see [Risks](#risks-and-open-questions). Path A's
message *is* echoed (via `readErrorCopy`), because it comes from the API client's curated
`parsed.message || parsed.error` and is already the shipped user-facing string.

`readErrorCopy` on Path A also buys the verification-403 case for free — `/api/trades/generate`
is behind the write gate and `/api/trades/status` behind the read gate
(`docs/api-reference.md:101`), so an unverified session's failure now says
"Verify your account to view your data." instead of a generic search error. The existing
toast at `:1240` keeps its current `e.message` wording (byte-identical) — the persistent
card is the new surface, and changing the toast too would widen the diff for no acceptance
gain.

### Toast offset fix

`Toast` gains one optional prop; **every existing call site is unchanged and byte-identical**:

```
/** Distance from the top of the host view. Defaults to space.xxl. */
topOffset?: number;
...
wrap: { position:'absolute', left:0, right:0, alignItems:'center', zIndex:50 },  // `top` removed from the static style
...
<Animated.View style={[styles.wrap, { top: topOffset ?? space.xxl }, animatedStyle]}>
```

`TradesScreen` measures the mode-bar region and passes the offset, reusing the `onLayout`
precedent already in the file (`deckCardY`, `:4574`):

- wrap the mode-bar branch (`:3436-3479`, covering `TradeFinderModeBar`,
  `TradeHomeUtilityRow`, and `TradingWithStrip`) in a `<View onLayout=…>` that records
  `layout.y + layout.height`;
- pass `topOffset={modeBarBottom > 0 ? modeBarBottom + space.sm : undefined}` to `<Toast>`.

`undefined` (no mode bar mounted, e.g. `finderMode` null) falls back to today's 32 pt.

Rejected alternatives: **bottom-anchoring** the toast — the bottom is already occupied by
the queue footer bar (`styles.queueFooter`, `:4960-4983`) and `FeedbackFAB`; **raising the
mode bar's zIndex above the toast** — that hides the message, which is worse than clipping
the chips.

Known limitation, accepted: the offset is measured in ScrollView content coordinates, so if
the user has scrolled down the toast can still land over other content. It is no worse than
today, and toasts here fire immediately after a top-of-page tap.

---

## Exact change list

All paths relative to the worktree root.

### `mobile/src/components/Toast.tsx`
1. Add `topOffset?: number` to `Props` (after `action`), documented.
2. Destructure it in the component signature.
3. Move `top` out of `styles.wrap` into the inline style array on the `Animated.View`
   (`:99-102`), as `{ top: topOffset ?? space.xxl }`.

### `mobile/src/screens/TradesScreen.tsx`
4. Import `semantic` from `../theme/chalkline` (only if absent) and `readErrorCopy` from
   `../utils/verification` (confirm absent).
5. Add the three copy constants + `jobErrorCopy()` helper at module scope, above the
   component.
6. Add `const [deckFailure, setDeckFailure] = useState<DeckFailure>(null)` beside
   `const [job, …]` (`:1153`).
7. `handleFindTrades` (`:732-738`): `setDeckFailure(null)` as the first statement.
8. `generateMutation.onSuccess` (`:1197`): `setDeckFailure(null)` immediately after
   `setJob(snapshot)`.
9. `generateMutation.onError` auto branch (`:1234-1237`): after `setAutoGenFailed(true)`,
   `setDeckFailure({ kind:'generate', message: GENERIC })`.
10. `generateMutation.onError` manual branch (`:1240`): add
    `setDeckFailure({ kind:'generate', message: readErrorCopy(e, GENERIC) })`; leave the
    `setToast` line unchanged.
11. Poll-failure branch (`:1298-1303`): add
    `setDeckFailure({ kind:'poll_abandoned', message: NETWORK })` alongside the existing
    `setToast` + `setJob(null)`.
12. New effect after the poll effect (`:1315`): when `job?.status === 'error'`,
    `setDeckFailure({ kind:'job_error', message: jobErrorCopy(job.error) })`. Deps
    `[job?.status, job?.error]`.
13. League-switch reset (`:1356-1380`): add `setDeckFailure(null)`.
14. `handleToggleFairness` (`:740-756`): add `setDeckFailure(null)`.
15. Ladder row 4 (`:4819-4823`): append `&& !deckFailure` to the condition.
16. Ladder: insert the new `deckFailure ? (…) : (` branch between `:4909` and `:4910`.
17. Styles: add `deckErrorTitle` next to `emptyTitle` (`:5818`).
18. Mode-bar `onLayout` wrapper + `modeBarBottom` state (`:3436-3479`), and
    `topOffset={…}` on `<Toast>` (`:3316-3323`).

### `mobile/.maestro/capture/trades.yaml`
19. **Required, not optional** — the existing error leg asserts the bug. `:88-91` waits for
    `trades.empty-text` to reappear after the error toast; once fixed, the deck slot shows
    `trades.deck-error` instead and this flow **fails**. Replace that wait with
    `trades.deck-error`, then tap `trades.deck-error.retry` to clear back to a clean state
    before the loading leg. Update the leg's header comment (`:71-76`) — the failure is no
    longer "a Toast, which carries no testID today".

### `mobile/.maestro/flows/trades-generation-failure.yaml` *(new)*
20. See [Maestro delta](#maestro-delta).

### `screens/mobile/trades/`
21. Re-capture (`mobile/scripts/screen-capture.sh --screen trades`): `error.png` changes,
    and the toast moves in every trades frame that carries one.

No backend file changes. No web/extension changes.

---

## Surface changes

**Confirmed: none.** Each surface checked explicitly:

| Surface | Change | Evidence |
|---|---|---|
| Feature flags | **None.** No new key; nothing added to `config/features.json`, `backend/feature_flags.py` `FLAG_KEYS`, or `docs/config-reference.md`. | This is a bug fix restoring an error state that should always have existed; gating it default-OFF would ship the bug. `ux.toast_v2` (already `true`) is read but not modified. |
| API routes | **None.** No route added, renamed, or contract-changed. `job.error` already ships in `_trade_job_public_view` (`backend/server.py:2707`) and is already typed client-side (`mobile/src/shared/types.ts:293`). | The fix only *reads* an existing field. |
| Schema | **None.** No table or column touched. | No `database.py` edit. |
| Analytics | **None — see the trap below.** | |
| Env / `model_config` | **None.** | |

**Analytics trap (do not trip this).** The retry button reuses the existing
`handleFindTrades(source)` entry point, which fires `track('find_trades_tapped', {source})`
(`TradesScreen.tsx:733`). `backend/analytics_taxonomy.py:191` declares
`"find_trades_tapped": frozenset()` — an **empty** prop allowlist — and
`analytics_ingest.py:385` strips any prop not in the allowlist. So `source` is *already*
being silently dropped for the existing `'prefs_changed_strip'` call. Passing
`'deck_error_retry'` is therefore free (no new event name, no taxonomy PR needed) **and
equally invisible**. If the operator wants to measure generation-failure rate or retry
uptake, that needs a tracking-plan PR adding `source` to `find_trades_tapped`'s allowlist
*before* the client change — this is the exact NULL-`platform` failure mode the handoff
warns about. It is deferred P0-7 territory; flagged, not built.

The pre-existing stripped-`source` drift is a small instance of the handoff's **A-33**
("do not trust comments over code") and is noted here rather than fixed — out of scope.

---

## Maestro delta

The harness supports this **with no new seam**. `backend/test_support.py` (mounted only
under `FTF_TEST_MODE=1`) exposes `POST /__test__/fail_next {path, status, count, body}`,
driven from a flow by `mobile/.maestro/capture/helpers/inject.js`. Two properties make all
three paths deterministic:

- `fail_next` matches on `request.path` via `fnmatch` (`test_support.py:144-149`), so
  `/api/trades/status*` catches the polls (query string excluded from `request.path`) —
  already used by the capture flow's loading leg (`trades.yaml:110-115`).
- **`status` may be any code including 2xx** (`test_support.py:12-15`; the only carve-out is
  `/api/trades/propose`, which refuses `< 400`, `:307-309`). That is what makes Path B
  forceable: inject a **200** whose body is an errored job snapshot.

### New flow: `mobile/.maestro/flows/trades-generation-failure.yaml`

Preamble copied verbatim from `mobile/.maestro/flows/smoke/05-trades-render.yaml`
(sign in `qa_standard` → league `990000000000000001` → `tab.trades` → conditional
`outlook.save-btn` dismissal). `tags: [trades, error]`.

**Ordering is load-bearing.** The two poll cases must run *before* any successful
generation, because `_trade_job_is_fresh` (`backend/server.py:2728-2748`) can serve a cached
`complete` job straight from the POST, in which case no polling happens and the injection
never fires. A fresh session has no cached job. Never call `INJECT_KIND: reset` mid-flow —
it clears in-memory sessions and signs the app out (`inject.js:22-25`).

| # | Leg | Injection | Assertions |
|---|---|---|---|
| 1 | **Path B — job error** | `fail_next` `/api/trades/status*`, `status: 200`, `count: 1`, body `{"job_id":"ftf_injected","status":"error","error":"timeout","cards":[],"opponents_done":0,"opponents_total":0}` | tap `trades.find-btn` → `trades.deck-error` visible; `trades.deck-error.retry` visible; `assertVisible: text: ".*took too long.*"`; `trades.empty-text` **notVisible** |
| 2 | retry from 1 | none | tap `trades.deck-error.retry` → `trades.card-top` visible (proves the retry re-fires generation and succeeds) |
| 3 | **Path C — poll abandoned** | `fail_next` `/api/trades/status*`, `status: 500`, `count: 4`, real 500 body | tap `trades.find-btn` → `trades.deck-error` visible; `assertVisible: text: ".*lost the connection.*"`; `trades.empty-text` notVisible |
| 4 | retry from 3 | none | tap `trades.deck-error.retry` → `trades.card-top` visible |
| 5 | **Path A — POST failure** | `fail_next` `/api/trades/generate`, `status: 500`, `count: 1`, body `{"error":"internal_error","message":"Unexpected server error."}` (the real production shape, same as `trades.yaml:84`) | tap `trades.find-btn` → `trades.deck-error` visible with the server's message; `trades.empty-text` notVisible |
| 6 | retry from 5 | none | tap `trades.deck-error.retry` → `trades.card-top` visible |

Every injection is preceded by `- assertTrue: ${output.inject.ok}`. Legs 3–4 need a longer
`extendedWaitUntil` (four polls with 800 ms→4000 ms backoff plus jitter ≈ 10–15 s): use
`timeout: 45000`. `id:` selectors only; `text:` used solely for asserting load-bearing error
copy, which `docs/plans/mobile-testing/lld.md:253` permits. No fixed sleeps, no coordinate
taps — `mobile/scripts/testid-lint.sh` bans both.

**Leg 3 caveat to verify at build time:** after four failed polls the client stops polling,
but the injection counter may not be fully drained if the loop aborts early. `count: 4`
matches `MAX_POLL_FAILURES` exactly; if a residual injection leaks into leg 4, either raise
`count` to a value the flow then drains, or re-arm with `count: 4` and confirm
`/__test__/whoami`'s `active_injections` is empty before leg 4.

### testIDs added

`trades.deck-error`, `trades.deck-error.retry`. Both follow the `trades.deck-summary` /
`trades.deck-summary.see-liked` precedent already in the file (`:4850`, `:4861`) and are
plain literals, so `testid-lint.sh`'s source cross-check finds them without an allowlist
entry.

### Capture delta

`mobile/scripts/screen-capture.sh --screen trades` at ship. `error.png` changes materially;
so does every trades frame that carries a toast (the offset moves). Optionally add
`error--poll` and `error--job` capture ids to `trades.yaml` so the library distinguishes the
three failures — nice to have, not required for acceptance.

### Smoke impact

`05-trades-render.yaml` and `06-trades-deck.yaml` cross this surface. Neither asserts
`trades.empty-text` after a failure, so neither should break — **verify, don't assume**.

---

## Docs impact

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | **no** | n/a — no route added, renamed, removed, or contract-changed. `job.error` already exists in the `/api/trades/status` response (`server.py:2707`) and in the client type. Optional courtesy edit: the `/api/trades/status` row (`:195`) does not mention `error` at all; adding half a clause would help the next reader. Flagged, not required. |
| `living-memory/LLD.md` | **no** | n/a — no schema/route/invariant *convention* shifted. |
| `docs/architecture.md` | **no** | n/a — no module wiring or data-flow change; one screen gains local state. |
| `living-memory/HLD.md` | **no** | n/a — no new module, client, or major flow. |
| `docs/cross-client-invariants.md` | **no** | n/a — copy and colour are mobile-only; `semantic.neg` is an existing token, not a new shared constant. |
| `docs/glossary.md` | **no** | n/a — no new domain term. |
| `docs/design/components.md` | **maybe** | `Toast` gains a public prop (`topOffset`). If the doc specs Toast's prop surface, add the row; if it only specs the visual, n/a. Check at build time. |
| ADR / `DECISIONS.md` | **yes** | New `D-026` — "A failed trade search renders a named, persistent deck state; `job.error` is mapped, never echoed." Records the deviation from the handoff and the reason (raw `str(e)`). Last id in the file is `D-024` (`living-memory/DECISIONS.md:209`). |
| `living-memory/GOTCHAS.md` | **yes** | New `G-029` — "First-run + four failed polls = a `SkeletonTradeCard` that never resolves" (defect (i)). Last id is `G-026` (`GOTCHAS.md:200`). |
| `living-memory/CHANGELOG.md` | **yes** | At ship, with the rest of the P0 batch. |
| `living-memory/TEST_LEDGER.md` | **yes** | Sim-run evidence (below). |

---

## Test plan

**Automated**
1. `cd mobile && npx tsc --noEmit` — clean. (The `DeckFailure` union and the new `Toast`
   prop are the only type surface.)
2. `python3 -m pytest backend/tests/ -q` — clean. No backend change; this is a
   regression check only.
3. `mobile/scripts/testid-lint.sh` — exit 0.
4. `mobile/.maestro/flows/trades-generation-failure.yaml` — all six legs pass.
5. `mobile/.maestro/capture/trades.yaml` — passes with the updated error leg (it fails
   against the fix if left as-is, which is itself the regression proof).
6. Smoke suite (11 flows) — tier 1, below.

**Manual / simulator**
7. Force Path A with `curl -X POST localhost:5001/__test__/fail_next -d '{"path":"/api/trades/generate","status":500,"count":1}'`, tap Find a Trade: red **SEARCH FAILED** card with the server message and a working Try again. Confirm the toast no longer covers the mode-bar chips (compare against `screens/mobile/trades/error.png`).
8. Force Path B with the 200-body injection: card reads the timeout copy; Try again succeeds.
9. Force Path C with `count:4` on `/api/trades/status*`: card reads the connection copy after ~12 s; Try again succeeds.
10. **First-run regression (defect (i)):** clear state, sign in fresh, and force Path C on the auto-started job. Assert the skeleton is *replaced* by the error card rather than persisting. This is the case the current build hangs on.
11. VoiceOver: the error card's title + body are reachable and the retry button announces as a button.
12. Confirm no valid empty state turned red — deck-done summary, "That's all for now", and the never-searched card must be visually unchanged.

**Ship gate**
Tier **1** (mobile screen/state change): full smoke suite (11 flows) + the new feature flow,
on sim, **plus** `mobile/scripts/screen-capture.sh --screen trades`. Log to
`living-memory/TEST_LEDGER.md` and write `qa/sim-runs/last-sim-run.json`
(`docs/runbook.md:94-109`).

---

## Risks and open questions

### Contradictions with the audit evidence

1. **"Render the backend message" is unsafe for Path B.** The handoff (`07:50`) and the
   resolutions doc both say to render `job.error`. Verified: `job.error` is `str(e)` of a
   server-side Python exception (`backend/server.py:5247`) or the literal `"timeout"`
   (`:2528`) — not user-facing copy. This plan maps it instead and echoes only Path A's
   message, which *is* curated. **This is a deliberate deviation and needs operator
   awareness, not approval-blocking** — it strictly improves on the spec's intent.
2. **"Fix the z-order" is a misdiagnosis.** The toast's `zIndex: 50` is correct; the defect
   is `top: space.xxl` colliding with the mode bar's y-range. The fix is an offset, not a
   stacking change. Same user-visible outcome.
3. **The audit's "the empty-state ladder at `:4910-4918` is reached identically from
   `status:'error'`"** is true, but incomplete: the ladder already *has* an
   `status !== 'error'` guard at `:4822` whose only job is to stop the first-run skeleton —
   and it misses Path C, producing an infinite skeleton the audit did not find. In scope
   and fixed here.

### Risks

| Risk | Severity | Mitigation |
|---|---|---|
| The capture flow `trades.yaml` breaks the moment the fix lands (it asserts the buggy fallback) | **certain** | Change 19 is mandatory and must land in the same commit. |
| `deckFailure` sticks after a *successful* retry, showing an error over a good deck | med | Cleared in `onSuccess`, in `handleFindTrades` before `mutate`, on league switch, and on fairness toggle. Row 7 (`deck.length > 0`) also wins over the new branch, so a non-empty deck can never render it. |
| Leg 3's `count: 4` injection leaks into leg 4 | med | Assert `/__test__/whoami` `active_injections` is empty between legs, or re-arm. Called out in the Maestro section. |
| Mode-bar `onLayout` fires late, so the first toast of a session uses the default 32 pt | low | Cosmetic and self-correcting on the next render; the toast holds ≥5 s. Not worth a synchronous measure. |
| The `trades_home_inline` experiment swaps the mode bar for `TradeHomeUtilityRow` of a different height | low | The `onLayout` wrapper spans the whole branch, so it measures whichever variant mounted. |
| Toast prop change ripples to other screens | low | `topOffset` is optional with the exact current default; every other call site is untouched and byte-identical. |
| First-run auto-failure now shows an error to a user who never tapped anything | low | See open question 1. |

### Open questions for the operator

1. **First-run auto-start failure (Path A, `auto: true`).** After the silent retry also
   fails, should the deck slot say "SEARCH FAILED"? This plan says **yes** — the app *did*
   search on the user's behalf and showed a skeleton, so "Hit Find a Trade to start" is a
   lie either way. But a brand-new user seeing red on their first screen is a real cost.
   The alternative is to leave first-run falling through to the never-searched card (which
   at least has an actionable button) and fix only defect (i). **Cheap to flip either way —
   one condition.**
2. **Partial-deck job error.** If the job errors after banking a few cards, this plan keeps
   the deck and says nothing. Should there be an inline note ("Search stopped early — 3
   trades found") above the deck? Additive, not required by the acceptance criterion,
   deliberately deferred.
3. **Feature flag.** The `flag-gated-remediation-build` convention wants user-visible
   changes default-OFF. This is a bug fix whose OFF state *is* the bug, so the plan ships
   it unflagged. Confirm — and if a flag is wanted for batch-level rollback, say so before
   build, because the flag key and its `FLAG_KEYS`/`config-reference.md` rows change the
   surface answer above from "none" to "one flag".
4. **Retry button label.** Rank says "Try again" on five screens and "Retry" on Anchors.
   This plan uses "Try again" (the majority). Non-blocking.
5. **Analytics.** Generation-failure rate is exactly the number that would falsify or
   confirm this finding's load-bearing assumption, and today it is unmeasurable from the
   client (`find_trades_tapped` allows zero props). Worth a tracking-plan PR — flagged
   under deferred P0-7, not built here.
