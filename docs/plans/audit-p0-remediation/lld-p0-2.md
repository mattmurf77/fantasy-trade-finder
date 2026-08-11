# LLD — P0-2: a failed trade search must be distinguishable from never having searched

> Code-level design for finding **P0-2** of the 2026-08-09 mobile-UX-audit remediation
> batch. Authored in worktree `ftf-p0-remediation`, branch `p0-remediation-2026-08-10`,
> base `origin/main @ ab9368f`. **Planning only — no code was changed by this document.**
>
> **Binding authority:** [`hld.md`](hld.md) is the batch authority. This LLD conforms to
> §2 **S-08…S-12**, §3 **commit 11**, §4 **W2-TS**, §6 rows **5** and **10**, §7 (docs
> rows `D-025` / `G-027` / `components.md`), §8 **R6** and **R13**, and §9 **LLD-2**.
> Where this document refines the source plan, §12 says so explicitly; there are **no
> deviations from the HLD**.
>
> **Source plan:** [`plan-p0-2.md`](plan-p0-2.md) · **scope block:** [`scope-p0-2.md`](scope-p0-2.md).
> **Sibling LLD sharing this build agent:** LLD-7 (P0-8/P0-9) — §1.3 is the composition
> contract between them.
>
> **Line numbers in this document are advisory, taken at `ab9368f`.** Per HLD §8 R1 the
> tree drifts under concurrent sessions: **every edit site below is identified by a grep
> anchor, and the build agent re-greps before editing.** A line number that disagrees with
> its anchor is stale — the anchor wins.

## Contents

- [1. Scope, ownership, and composition with P0-8/9](#1-scope-ownership-and-composition-with-p0-89)
- [2. The `DeckFailure` state](#2-the-deckfailure-state)
- [3. Every write and clear site](#3-every-write-and-clear-site)
- [4. The `job.status === 'error'` mirror effect](#4-the-jobstatus--error-mirror-effect)
- [5. The render ladder — row-4 guard and the row-7b insertion](#5-the-render-ladder--row-4-guard-and-the-row-7b-insertion)
- [6. The error card](#6-the-error-card)
- [7. `job.error` mapping](#7-joberror-mapping)
- [8. Toast `topOffset`](#8-toast-topoffset)
- [9. Maestro delta](#9-maestro-delta)
- [10. `testID`s, lint, and types](#10-testids-lint-and-types)
- [11. Verification checklist for the build agent](#11-verification-checklist-for-the-build-agent)
- [12. Refinements to the source plan, and non-deviations from the HLD](#12-refinements-to-the-source-plan-and-non-deviations-from-the-hld)

---

## 1. Scope, ownership, and composition with P0-8/9

### 1.1 Files this LLD owns

| File | Change class |
|---|---|
| `mobile/src/screens/TradesScreen.tsx` | state + 7 transition sites + 1 effect + 2 ladder edits + 1 style + toast measurement |
| `mobile/src/components/Toast.tsx` | one optional prop; `top` moved from the static style to the inline array |
| `mobile/.maestro/flows/trades-generation-failure.yaml` **(new)** | 6 legs |
| `mobile/.maestro/capture/trades.yaml` | **mandatory** — its error leg currently asserts the bug |
| `screens/mobile/trades/*` | re-capture artefact (produced by W3-QA's `screen-capture.sh` run, not hand-edited) |

**Not owned, and not to be touched by this LLD's agent:** any `docs/` or `living-memory/`
file (HLD §4 wave 3, `W3-DOCS`), `backend/**` (no backend change at all),
`mobile/.maestro/capture/leagues@fresh.yaml`, `04-tabs-navigation.yaml`,
`flows/smoke/09-league.yaml` (HLD §6 must-pass-unmodified).

### 1.2 Where this lands

HLD §3 **commit 11**: `P0-2 + P0-8/9: deck failure state, toast offset, s8.1 beat gate,
s6.1 swallow fix, celebration_shown rename, send-surface plumbing`, built by wave-2 agent
**W2-TS**, the sole owner of `TradesScreen.tsx` for the wave. P0-2 may be staged as its
own hunk inside that commit but **must not be split into a separate commit** — the
`capture/trades.yaml` inversion has to travel with the fix or `main` carries a red flow
(HLD §8 R5).

### 1.3 Composition contract with LLD-7 (P0-8/9) — disjoint regions in one file

Both findings edit `TradesScreen.tsx` under one author. Verified at `ab9368f`: **no region
overlaps**. The build agent applies both sets; this table is the map.

| Owner | Grep anchor | ~Line | Region |
|---|---|---|---|
| **P0-2** | `let adaptationMomentShownThisSession` (insert below) | 228 | module-scope constants + `jobErrorCopy` |
| **P0-2** | `function handleFindTrades(source?: string) {` | 732 | clear on retry/tap |
| **P0-2** | `function handleToggleFairness(next: boolean) {` | 740 | clear on deck reset |
| **P0-2** | `const [job, setJob] = useState<TradeJobSnapshot \| null>(null);` | 1153 | state declaration |
| **P0-2** | `onSuccess: (snapshot) => {` … `setJob(snapshot);` | 1197 | clear on success |
| **P0-2** | `autoGenRef.current = 'failed';` | 1235 | auto-path write |
| **P0-2** | `setToast({ msg: e.message \|\| 'Generate failed', tone: 'warn' });` | 1240 | manual-path write |
| **P0-2** | `if (failures >= MAX_POLL_FAILURES) {` | 1298 | poll-abandon write |
| **P0-2** | `}, [job?.job_id, job?.status]);` (insert **after**) | 1315 | new mirror effect |
| **P0-2** | `setTradeIntent(null); // #172 — a declared shape is league-specific` | 1365 | league-switch clear |
| **P0-2** | `<Toast` … `onDismiss={() => setToast(null)}` | 3316 | `topOffset` prop |
| **P0-2** | `{finderMode ? (` … `showInlineHome ? (` (mode-bar branch) | 3436 | `onLayout` wrapper |
| **P0-2** | `) : firstRun &&` … `!autoGenFailed ? (` | 4819 | ladder row-4 guard |
| **P0-2** | `<Text testID="trades.empty-text"` (insert branch **above** its `<Card>`) | 4910 | ladder row 7b |
| **P0-2** | `emptyTitle: {` (insert after its block) | 5818 | `deckErrorTitle` style |
| **P0-8** | `if (ob.guideSeen['s6.1'] && !ob.guideSeen['s8.1']` | 2457 | s8.1 beat gate |
| **P0-9 D2** | `track('celebration_fired', { beat: 'first_quickset_save' }, 'Trades');` | 2547 | rename |
| **P0-9 D1/D2** | `patchOnboardingState({ celebrationsShown: { first_like: true } });` (two sites) | 3134, 3152 | D1 condition + renames |
| **P0-6/P0-7 inherited** | `<SendInSleeperButton` (deck mount) | 4713 | name props + `surface="deck"` |

**One semantic interaction, already adjudicated (HLD S-40 / §10.5):** LLD-7 deletes the
`err_burst` guide beat from `mobile/src/components/analystScript.ts`
(`err_burst: (): GuideStep => ({ id: 'err.burst', screen: 'Trades', … })`, `:106-107`).
It has **zero call sites**, so the deletion is behaviour-preserving, and P0-2's error card
is the surface that replaces it. **P0-2 must not add a mascot line, a toast change, or any
second error surface for the same failure** — one failure, one named state.

---

## 2. The `DeckFailure` state

### 2.1 Type and constants (module scope)

Insert at module scope, immediately above `export default function TradesScreen(...)` —
anchor on the last module-level session flag:

```ts
// Current tail of the module-scope block (~:225-228):
// F9 (deck.first_session): the adaptation moment renders at most once per
// app session (module-level so a tab remount / regenerate can't re-fire it
// — "at most once per first session" with margin).
let adaptationMomentShownThisSession = false;
```

New code directly below it:

```ts
// ── P0-2: the failed-search state ────────────────────────────────────
// Three independent failure paths (POST error, job errors during polling,
// polling abandoned after MAX_POLL_FAILURES) previously all left the deck
// slot on the never-searched card, so "we tried and failed" and "you have
// never searched" were the same pixels. One funnel, LAST WRITE WINS, so the
// deck slot can render a named persistent state with a working retry.
//
// `message` is ALWAYS shipped user copy. job.error is never routed here
// verbatim — see jobErrorCopy below.
type DeckFailure = {
  kind: 'generate' | 'job_error' | 'poll_abandoned';
  message: string;
} | null;

const DECK_FAIL_GENERIC =
  "We couldn't finish that search — the server may still be waking up. Try again.";
const DECK_FAIL_NETWORK =
  'We lost the connection while searching. Your league is fine — try again.';
const DECK_FAIL_TIMEOUT =
  'That search took too long. The server may still be waking up — try again.';

// Maps the job snapshot's `error` field onto shipped copy. See §7 — the raw
// value is str(e) of a server-side Python exception, or the reaper's literal
// "timeout"; neither is user-facing.
function jobErrorCopy(raw?: string | null): string {
  return raw === 'timeout' ? DECK_FAIL_TIMEOUT : DECK_FAIL_GENERIC;
}
```

Module scope, not component scope, is deliberate: the three constants and the mapper are
the only thing standing between the renderer and a raw exception string, and a reader
grepping `DECK_FAIL_` must find every use in one place.

### 2.2 The state hook

Current code (`:1149-1153`):

```ts
  // ── Find-a-Trade: streaming job snapshot ─────────────────────────────
  // The backend runs generation in a background thread and we poll for
  // results. The job snapshot drives both the deck (cards stream in) and
  // the progress strip ("4/11 opponents searched").
  const [job, setJob] = useState<TradeJobSnapshot | null>(null);
```

Add immediately below:

```ts
  // P0-2 — the last search's failure, or null. Set by all three failure
  // paths, cleared by every path that starts or invalidates a search.
  const [deckFailure, setDeckFailure] = useState<DeckFailure>(null);
```

`useState<DeckFailure>(null)` (not `useState<DeckFailure | null>`) — `null` is already in
the union, exactly as `TradeJobSnapshot | null` is spelled out on the line above.

### 2.3 Invariants

1. **`deckFailure.message` is never a raw backend string** except on Path A, where the
   string is the API client's `parsed.message || parsed.error` — i.e. already the shipped
   user-facing copy (`handle_unexpected_error`'s `"Unexpected server error."`).
2. **Last write wins.** No path reads `deckFailure` before writing it.
3. **Every search start clears it first** (§3.1), so the card can never outlive the
   failure it describes.
4. **`job` is never cleared by P0-2.** Row 4's existing `job?.status !== 'error'` guard,
   the Find-a-Trade button's label/`disabled` logic (`deck.length > 0 && job?.status ===
   'complete'`, `disabled={!leagueId || generateMutation.isPending || job?.status ===
   'running'}`), and the progress strip all keep reading `job` unchanged.

---

## 3. Every write and clear site

Seven sites. Each is quoted as it stands at `ab9368f`, then the edit.

### 3.1 CLEAR — `handleFindTrades` (also the retry entry point)

**Anchor:** `function handleFindTrades(source?: string) {` (~`:732`)

```ts
  // #257 — shared Find-a-Trade entry point so every trigger (the on-screen
  // button in both flag states, and the "Preferences changed" strip)
  // clears the refresh nudge the same way.
  function handleFindTrades(source?: string) {
    track('find_trades_tapped', source ? { source } : undefined, 'Trades');
    prefsChangedSinceGenerateRef.current = false;
    setShowPrefsChangedStrip(false);
    pendingScrollToDeckRef.current = true; // #276
    generateMutation.mutate({});
  }
```

**Edit:** `setDeckFailure(null);` as the **first statement of the body**, above the
existing `track(...)` call.

Why first: the retry button re-enters this function, so the clear must happen before
`mutate` schedules anything. Ordering against `track` is immaterial to behaviour but
putting the state clear at the top makes "this function starts a search, and a search in
flight has no failure" readable at a glance.

**Analytics note, unchanged from the scope block (S-12):** the retry passes
`source: 'deck_error_retry'`. `backend/analytics_taxonomy.py` declares
`"find_trades_tapped": frozenset()` — an empty prop allowlist — and `analytics_ingest.py`
strips unlisted props, so `source` is **already** dropped for the existing
`'prefs_changed_strip'` call. The new value costs nothing and measures nothing. **P0-2
adds no event and no taxonomy row**; the allowlist gap is P0-7's addendum row and a
`NEXT.md` item (HLD §7).

### 3.2 CLEAR — `handleToggleFairness`

**Anchor:** `function handleToggleFairness(next: boolean) {` (~`:740`)

```ts
    flushPendingPassRef.current(); // commit any undoable pass before reset
    lastDispositionedRef.current = null; // regenerated decks can reuse ids
    setDeck([]);
    setDeckIdx(0);
    setLaneFilter(null);
    setJob(null);
    setEdits({});
    setSwapTarget(null);
    setSuggestTarget(null);
  }
```

**Edit:** add `setDeckFailure(null);` adjacent to `setJob(null);` (immediately after it).
Toggling fairness invalidates the deck *and* the reason the last deck failed.

### 3.3 CLEAR — `generateMutation.onSuccess`

**Anchor:** `onSuccess: (snapshot) => {` followed by `setJob(snapshot);` (~`:1197-1198`)

```ts
    onSuccess: (snapshot) => {
      setJob(snapshot);
      // For instant cache-hit responses (status === 'complete') the deck
      // populates immediately via the snapshot effect below. For 'running'
      // responses the polling effect takes over.
```

**Edit:** `setDeckFailure(null);` immediately after `setJob(snapshot);`.

Belt-and-braces with §3.1 (which already cleared on the way in) — but `onSuccess` also
fires for the **auto** first-run mutation and for the two `generateMutation.mutate({...})`
call sites that do **not** route through `handleFindTrades` (the inline button `onPress`
at ~`:4061`, the post-Quick-Set `force` regeneration at ~`:2537`, and the `:1974` /
`:2019` regenerations). Clearing here covers all of them without editing five call sites.

### 3.4 WRITE — `onError`, auto branch (first-run auto-start, both attempts spent)

**Anchor:** `autoGenRef.current = 'failed';` (~`:1235`)

```ts
    onError: (e: Error, vars) => {
      if (vars?.auto) {
        // First-run auto-start failed — most likely the LeaguePicker
        // background session_init hasn't landed yet. Retry once, quietly;
        // a second failure surfaces the normal manual empty state (the
        // Find a Trade button is the recovery path).
        if (autoGenRef.current === 'kicked') {
          autoGenRef.current = 'retrying';
          autoRetryTimer.current = setTimeout(() => {
            autoRetryTimer.current = null;
            generateMutation.mutate({ auto: true });
          }, 4000);
        } else {
          autoGenRef.current = 'failed';
          setAutoGenFailed(true);
        }
        return;
      }
```

**Edit:** in the `else` branch only, after `setAutoGenFailed(true);`:

```ts
          setDeckFailure({ kind: 'generate', message: DECK_FAIL_GENERIC });
```

**This is HLD S-08** — the first-run auto-start failure **shows the error card**. The app
did search on the user's behalf and showed a skeleton; "Hit Find a Trade to start" is a
lie either way, and the card is the only one of the two that carries a working retry.
The existing comment ("a second failure surfaces the normal manual empty state") becomes
wrong the moment this lands and **must be rewritten in the same edit** — HLD §8 R5 / the
handoff's A-33 class:

```
        // First-run auto-start failed — most likely the LeaguePicker
        // background session_init hasn't landed yet. Retry once, quietly;
        // a second failure surfaces the P0-2 deck-failure card (S-08), whose
        // "Try again" is the recovery path. Auto failures stay toast-free —
        // the card is the whole surface.
```

`DECK_FAIL_GENERIC`, not `readErrorCopy(e, …)`: the auto path deliberately has no toast
and the most likely cause is a session-init race, for which the generic copy is exactly
right. Echoing the API message here would put an unexplained server string on a
brand-new user's first screen.

### 3.5 WRITE — `onError`, manual branch (Path A)

**Anchor:** `setToast({ msg: e.message || 'Generate failed', tone: 'warn' });` (~`:1240`)

```ts
      setToast({ msg: e.message || 'Generate failed', tone: 'warn' });
    },
  });
```

**Edit:** add a line **after** the `setToast` call, leaving it byte-identical:

```ts
      setToast({ msg: e.message || 'Generate failed', tone: 'warn' });
      setDeckFailure({ kind: 'generate', message: readErrorCopy(e, DECK_FAIL_GENERIC) });
```

`readErrorCopy` comes from `mobile/src/utils/verification.ts` and is **not currently
imported** by `TradesScreen.tsx` (verified: zero hits for `readErrorCopy` and for
`utils/verification` in the file). Add:

```ts
import { readErrorCopy } from '../utils/verification';
```

next to the other `../utils/*` imports. `semantic` **is already imported**
(`TradesScreen.tsx:39`, inside the `../theme/chalkline` block) — the plan's "confirm it is
not already imported" resolves to **no import change for `semantic`**.

What `readErrorCopy` buys (`verification.ts:16-20`):

```ts
export function readErrorCopy(err: unknown, fallback: string): string {
  return err instanceof ApiError && err.isVerificationRequired
    ? VERIFY_READS_COPY
    : fallback;
}
```

An unverified session hitting the write gate on `/api/trades/generate` now reads
*"Verify your account to view your data."* instead of a generic search error. Every other
error falls back to the shipped `e.message`… **no** — read it again: the fallback is
`DECK_FAIL_GENERIC`, not `e.message`. That is deliberate and is a refinement over the
plan's prose; see §12.1.

**The toast is unchanged.** Its wording, tone, and hold are byte-identical. HLD LLD-2:
"Must not … change the existing toast wording."

### 3.6 WRITE — poll abandoned after four consecutive failures (Path C)

**Anchor:** `if (failures >= MAX_POLL_FAILURES) {` (~`:1298`)

```ts
      } catch {
        if (cancelled) return;
        failures += 1;
        if (failures >= MAX_POLL_FAILURES) {
          setToast({
            msg: 'Network hiccup — try Find a Trade again in a moment',
            tone: 'warn',
          });
          setJob(null);
        } else if (!cancelled) {
          setTimeout(tick, intervalMs);
        }
      }
```

**Edit:** add one line inside the `if`, after `setJob(null);`:

```ts
          setDeckFailure({ kind: 'poll_abandoned', message: DECK_FAIL_NETWORK });
```

`setJob(null)` stays — the server-side worker keeps running and the next tap can hit the
warm cache, which is why the local job is dropped. What changes is that dropping it no
longer erases the *evidence a search happened*: `deckFailure` now carries it.

The effect's own header comment (`:1248-1251`) says the toast returns the UI "to its
pre-tap state". Rewrite that clause in the same edit:

```
  // Failure handling: after MAX_POLL_FAILURES consecutive errors we surface
  // a toast, clear the local job (the server-side worker keeps running so the
  // next tap can hit the warm cache) and record a `poll_abandoned` deckFailure
  // so the deck slot shows the named failure state rather than the
  // never-searched card (P0-2).
```

### 3.7 CLEAR — league switch

**Anchor:** `setTradeIntent(null); // #172 — a declared shape is league-specific` (~`:1365`)

```ts
    setDeck([]);
    setDeckIdx(0);
    setLaneFilter(null);
    setTradeIntent(null); // #172 — a declared shape is league-specific
    setJob(null);
    setEdits({});
```

**Edit:** add `setDeckFailure(null);` immediately after `setJob(null);`.

This effect keys on `[leagueId]` and also runs on mount, so `deckFailure` starts null on
every league entry. It is additionally the reason the error card can never render with a
null `leagueId` — see §6.3.

### 3.8 Transition table (the whole state machine on one page)

| # | Trigger | Anchor | Action |
|---|---|---|---|
| 1 | Find a Trade / retry tapped | `function handleFindTrades` | `setDeckFailure(null)` — **first statement** |
| 2 | Fairness toggled (deck reset) | `function handleToggleFairness` | `setDeckFailure(null)` |
| 3 | Generate POST succeeds (any caller) | `onSuccess` → `setJob(snapshot)` | `setDeckFailure(null)` |
| 4 | Auto generate POST fails twice | `autoGenRef.current = 'failed'` | `{kind:'generate', message: DECK_FAIL_GENERIC}` |
| 5 | Manual generate POST fails | `setToast({ msg: e.message …` | `{kind:'generate', message: readErrorCopy(e, DECK_FAIL_GENERIC)}` |
| 6 | 4 consecutive poll failures | `if (failures >= MAX_POLL_FAILURES)` | `{kind:'poll_abandoned', message: DECK_FAIL_NETWORK}` |
| 7 | Job snapshot reports `status:'error'` | new effect (§4) | `{kind:'job_error', message: jobErrorCopy(job.error)}` |
| 8 | League switches | `setTradeIntent(null); // #172` | `setDeckFailure(null)` |

`kind` is carried but never branched on in v1. It exists so the field is available to a
future analytics row (P0-7 territory) and so a debugger can tell the three paths apart
without decoding copy. That is a deliberate, cheap allowance, not speculative
abstraction — it is one union member per existing code path.

---

## 4. The `job.status === 'error'` mirror effect

### 4.1 The code

Insert directly **after** the poll effect's closing dependency array — anchor
`}, [job?.job_id, job?.status]);` (~`:1315`), which is the poll effect's terminator (the
next effect down is the deck-maintenance one keyed on `[job?.cards.length, job?.status]`).

```ts
  // P0-2 — mirror a job-level failure into the one-funnel deckFailure state.
  //
  // Why an EFFECT and not a render-time read of `job?.status === 'error'`:
  // RECENCY. `job` is not cleared when a retry's POST fails (§3.5 writes
  // deckFailure and leaves `job` alone, deliberately — row 4's guard and the
  // Find-a-Trade button both still read it). A render-time read would
  // therefore resurrect the OLD job's message over the NEW failure the user
  // just caused. Mirroring makes every path a write into one slot, so
  // last-write-wins is the whole conflict-resolution rule.
  //
  // One-directional by design: this effect only SETS. Clearing lives on the
  // eight transition sites in §3 — a clear here would fight `handleFindTrades`
  // on the retry tick (job still 'error', deckFailure just cleared).
  useEffect(() => {
    if (job?.status !== 'error') return;
    setDeckFailure({ kind: 'job_error', message: jobErrorCopy(job.error) });
  }, [job?.status, job?.error]);
```

### 4.2 Why an effect, in full

Three independent reasons, all load-bearing:

1. **Recency (the reason of record).** Sequence: job errors → card shows the job-error
   copy → user taps **Try again** → `handleFindTrades` clears `deckFailure` and calls
   `mutate` → the POST itself fails → §3.5 writes a `'generate'` failure. `job` is
   **still** the stale errored snapshot at this point, because nothing clears it. A
   render-time `job?.status === 'error' ? jobErrorCopy(job.error) : deckFailure` ladder
   would show the *older* job's message over the newer, truer one. With the mirror, the
   newest write wins and the ladder reads exactly one variable.
2. **One branch in the ladder instead of two.** Row 7b tests `deckFailure` alone. A
   render-time read means every future reader of the ladder must reason about two sources
   of "failed", and the row-4 guard (§5.1) would need both conditions too.
3. **`setState` from render is illegal anyway.** Anything richer than a pure expression —
   deriving copy, marking a beat, later attaching an event — cannot live in the render
   path. The effect is the only place that stays correct when this grows.

**Why the deps are `[job?.status, job?.error]` and not `[job]`:** the poll loop's
shallow-equal guard (`if (changed) setJob(next)`) already suppresses no-op snapshots, but
`onSuccess` and the deck-maintenance path can still hand back a new object identity with
the same status. Keying on the two scalars the effect actually reads keeps it a one-shot
per real transition. Note the file's existing precedent for exactly this: the poll effect
(`[job?.job_id, job?.status]`) and the deck effect (`[job?.cards.length, job?.status]`)
both key on scalars, with the reason written out at `:1321-1327`.

**Idempotency:** re-running with the same `(status, error)` pair writes an equal-valued
new object. That is a wasted render at worst and cannot loop, because `deckFailure` is not
in the dependency array. Guarding with a `useRef` was considered and rejected — it adds a
second piece of state to keep in sync for a render that React already coalesces.

### 4.3 Path-C interaction (no double-write)

Path C sets `job` to `null` **and** writes `poll_abandoned` in the same tick (§3.6). The
mirror effect then re-runs with `job?.status === undefined` and returns early, so it never
overwrites the `poll_abandoned` message with a `job_error` one. Confirmed by inspection:
the poll loop's `catch` never calls `setJob(next)`, so `status` can only become `'error'`
through a **successful** poll returning an errored snapshot — which is Path B.

---

## 5. The render ladder — row-4 guard and the row-7b insertion

The deck slot is one ternary ladder inside `styles.deckWrap`. Post-fix order:

| # | Condition | Renders |
|---|---|---|
| 1 | `quicksetPromptShown` | `QuickSetPromptCard` |
| 2 | `adaptationMoment && topCard` | adaptation card |
| 3 | `topCard` | the deck |
| 4 | `firstRun && deck.length===0 && status!=='complete' && status!=='error' && !autoGenFailed` **`&& !deckFailure`** | `SkeletonTradeCard` |
| 5 | `generateMutation.isPending \|\| job?.status==='running'` | "Looking for trades…" |
| 6 | `deck.length>0 && summaryVisible` | deck-done summary |
| 7 | `deck.length>0` | "That's all for now" |
| **7b** | **`deckFailure`** | **the error card (§6)** |
| 8 | *(fallback)* | `trades.empty-text` — "Hit \"Find a Trade\" to start" |

Placement is doing three jobs at once and none of them is arbitrary:

- **After row 5** ⇒ a retry in flight immediately swaps the card for "Looking for trades…"
  rather than leaving a red card under a spinner.
- **After row 7** ⇒ a job that errors *after* banking cards keeps rendering the deck.
  Partial results are still results (HLD **S-09**; the inline "search stopped early" note
  is deferred). This is also the structural reason `deckFailure` can never appear over a
  populated deck, independent of the clear sites.
- **Before row 8** ⇒ the never-searched card is now genuinely never-searched. It keeps its
  `testID` and its copy (`trades.empty-text` is not renamed and not replaced).

### 5.1 Row 4 — the `!deckFailure` guard (defect G-027)

Current code (`:4819-4829`):

```tsx
          ) : firstRun &&
            deck.length === 0 &&
            job?.status !== 'complete' &&
            job?.status !== 'error' &&
            !autoGenFailed ? (
            // Onboarding item 4 — first-run skeleton deck: generation was
            // auto-started (or pregenerated at auth-return) and cards are
            // streaming in; the manual "Hit Find a Trade" empty state never
            // shows on first run. Falls through to the normal states if the
            // job completes empty or the silent auto-start gives up.
            <SkeletonTradeCard />
```

**Edit:** append one condition, and extend the comment:

```tsx
          ) : firstRun &&
            deck.length === 0 &&
            job?.status !== 'complete' &&
            job?.status !== 'error' &&
            !autoGenFailed &&
            !deckFailure ? (
            // Onboarding item 4 — first-run skeleton deck: generation was
            // auto-started (or pregenerated at auth-return) and cards are
            // streaming in; the manual "Hit Find a Trade" empty state never
            // shows on first run. Falls through to the normal states if the
            // job completes empty or the silent auto-start gives up.
            //
            // P0-2 / G-027: `!deckFailure` is NOT redundant with the
            // `status !== 'error'` guard above it. The poll-abandon path sets
            // job to NULL (not to an errored snapshot), so `job?.status` is
            // `undefined`, the status guard misses, `autoGenFailed` is only
            // ever set from the POST path, and the auto-start effect refuses
            // to re-kick (autoGenRef.current !== 'idle'). Before this guard a
            // first-run user whose polling died sat on this skeleton FOREVER.
            <SkeletonTradeCard />
```

**Why this is the whole fix for G-027** — the three blocking facts, each verified in this
worktree:

- `setJob(null)` in the poll `catch` (`:1303`) ⇒ `job?.status` is `undefined`, so
  `job?.status !== 'error'` is **true** and the exclusion misses.
- `setAutoGenFailed(true)` only ever executes in `onError`'s auto branch (`:1236`) — the
  poll loop never touches it, so `!autoGenFailed` is **true**.
- The first-run auto-start effect refuses to re-kick:
  ```ts
  useEffect(() => {
    if (!firstRun || !leagueId || gateState) return;
    if (autoGenRef.current !== 'idle') return;
    if (job || generateMutation.isPending || deck.length > 0) return;
  ```
  `autoGenRef.current` is `'kicked'` by then, so the guard returns and nothing re-arms.

With row 4 guarded, the same tick that abandons polling (§3.6) both fails the guard and
satisfies row 7b — the skeleton is *replaced by the error card*, not merely un-stuck.

### 5.2 Row 7b — the insertion point

Current code, the tail of row 7 and all of row 8 (`:4908-4919`):

```tsx
              </View>
            </Card>
          ) : (
            <Card>
              <View style={styles.emptyInner}>
                <Text testID="trades.empty-text" style={styles.emptyTitle}>Hit "Find a Trade" to start</Text>
                <Text style={styles.emptyBody}>
                  We'll pull trade ideas from your league and show them one at a time.
                </Text>
              </View>
            </Card>
          )}
        </View>
        )}
```

**Edit:** replace the bare `) : (` on the line after row 7's `</Card>` with the new
branch, leaving row 8 as the final `else`:

```tsx
              </View>
            </Card>
          ) : deckFailure ? (
            // P0-2 — the last search FAILED, and this is the only state that
            // says so. Sits below row 7 (deck.length > 0) so a job that errors
            // after banking cards keeps its partial deck (S-09), and above the
            // never-searched fallback so that card now means what it says.
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
          ) : (
            <Card>
              <View style={styles.emptyInner}>
                <Text testID="trades.empty-text" style={styles.emptyTitle}>Hit "Find a Trade" to start</Text>
```

TypeScript narrows `deckFailure` to the non-null member inside the branch, so
`deckFailure.message` needs no `?.` or `!`.

---

## 6. The error card

### 6.1 Construction

Everything is an existing primitive; nothing new is introduced but one style key.

| Element | Choice | Precedent |
|---|---|---|
| Container | `<Card>` + `<View style={styles.emptyInner}>` | every other deck-slot state (`:4834`, `:4849`, `:4877`, `:4911`) — the slot must keep its layout, and `emptyInner` supplies `alignItems:'center', gap: space.sm, paddingVertical: space.sm` |
| Title | `styles.deckErrorTitle` = `type.heading` + `semantic.neg` | `type.heading` is the uppercase display ramp (`fontSize: 22`, `textTransform: 'uppercase'`) used by `emptyTitle`, so it renders as **"SEARCH FAILED"** in the same voice as "DECK DONE" |
| Body | `styles.emptyBody` (`type.bodySm`, centred) | unchanged, shared with every sibling state |
| Action | `<Button variant="secondary" compact label="Try again">` | the deck slot's other in-Card actions are secondary/primary compact (`trades.deck-summary.see-liked`, `:4861`); `ManualRanksScreen.tsx:644` uses `secondary` for the same job |

**Colour is the whole non-confusability argument.** `semantic.neg` is `#EF4444`
(`mobile/src/theme/chalkline.ts:59`, commented "pass/decline, errors") and **no valid
empty state anywhere in the app is red**. `docs/design/components.md` § Feedback & status
specs `EmptyState` as "`heading` (condensed caps) + `body-sm` chalk-dim + one
Primary/Secondary button" and § Forms specs errors as "`--neg` … message below" — the card
is the specced EmptyState construction with the specced error colour on its headline. No
new component, no new token.

**Label is "Try again"** — HLD **S-11**, the majority in-app convention (five Rank
screens: `TiersScreen`, `QuickRankScreen`, `QuickSetTiersScreen`, `RankScreen`,
`ManualRanksScreen`). "Retry" appears only on `PickAnchorScreen`.

### 6.2 The style key

Insert after the existing `emptyTitle` block (`:5818-5821`):

```ts
  emptyTitle: {
    ...type.heading,
    textAlign: 'center',
  },
```

becomes

```ts
  emptyTitle: {
    ...type.heading,
    textAlign: 'center',
  },
  // P0-2 — the ONLY red headline in the deck slot. Same display ramp as
  // emptyTitle so the failure state reads in the same voice as "DECK DONE";
  // semantic.neg is what makes it non-confusable with a valid empty state at
  // a glance, before the copy is even read.
  deckErrorTitle: {
    ...type.heading,
    textAlign: 'center',
    color: semantic.neg,
  },
```

`emptyTitle` is **not** modified — the never-searched card, the deck-done summary, and
"That's all for now" must stay visually identical (PRD AC-7).

### 6.3 Deliberately absent: a `disabled` prop on the retry button

Considered and rejected. The three states that would justify it are all unreachable:

- `generateMutation.isPending` ⇒ row 5 wins and the card is not mounted.
- `job?.status === 'running'` ⇒ row 5 wins.
- `!leagueId` ⇒ the league-switch effect (§3.7) fires on every `leagueId` change including
  to a falsy value and clears `deckFailure`, so row 7b is false.

Adding the prop would be three conditions that can never be true — noise in the diff and a
false implication that the card can render in those states.

### 6.4 Accessibility

`Button` already renders a `Pressable` with `accessibilityRole="button"`; the label is the
accessible name, so "Try again, button" is announced without extra props. The title and
body are plain `<Text>` and are reachable in reading order. No `accessibilityLiveRegion`
is added: the toast already announces the failure via
`AccessibilityInfo.announceForAccessibility` (`Toast.tsx:64-68`) on Paths A and C, and
duplicating that announcement on the card would read the failure twice. Verified manually
in PRD test M-11.

---

## 7. `job.error` mapping

### 7.1 The mapping table

| `job.error` value | Rendered copy | Constant |
|---|---|---|
| `'timeout'` | "That search took too long. The server may still be waking up — try again." | `DECK_FAIL_TIMEOUT` |
| anything else — `str(e)` of a Python exception, `''`, `null`, `undefined` | "We couldn't finish that search — the server may still be waking up. Try again." | `DECK_FAIL_GENERIC` |

Exact-match on `'timeout'`, not `includes('timeout')`: the reaper writes the bare literal,
and a substring test would also catch an exception message that merely *mentions* a
timeout and is not the reaper's clean case.

### 7.2 Why the raw value is never echoed

Two producers, neither user-facing:

1. The job worker's catch-all (`backend/server.py`, `except Exception as e:` →
   `j["status"] = "error"`, `j["error"] = str(e)`) — that is a Python exception string,
   e.g. `KeyError: 'roster'`.
2. The stale-job reaper (`backend/server.py`) → `j["error"] = "timeout"` — a machine
   token, not a sentence.

Both pass through untouched: `_trade_job_public_view` returns `job.get("error")` verbatim,
and `normalizeJobSnapshot` (`mobile/src/api/trades.ts:251`) keeps it as
`error: raw?.error ?? null`. `TradeJobSnapshot.error` is typed `string | null | undefined`
(`mobile/src/shared/types.ts:293`).

**This is a deliberate deviation from the audit handoff's "render the backend message",
and it is recorded, not hidden:** HLD **S-08…S-12** and `D-025` (owned by W3-DOCS) both
carry it. The handoff's intent — *tell the user what went wrong* — is better served by two
mapped sentences than by a stack-trace fragment. Path A **is** echoed, because there the
message comes from the API client's `parsed.message || parsed.error`, i.e. the curated
`"Unexpected server error."` that `handle_unexpected_error` ships.

---

## 8. Toast `topOffset`

### 8.1 The diagnosis (the audit's "z-order" is a misdiagnosis)

`Toast.tsx:143-151` today:

```ts
const styles = StyleSheet.create({
  wrap: {
    position: 'absolute',
    top: space.xxl,
    left: 0,
    right: 0,
    alignItems: 'center',
    zIndex: 50,
  },
```

`space.xxl` is **32** (`chalkline.ts:74`). The toast is the first child of `TradesScreen`'s
`SafeAreaView`; the `ScrollView` immediately below it uses
`contentContainerStyle={styles.scroll}` = `{ padding: space.lg /* 16 */, gap: space.lg,
paddingBottom: 96 }`, and its first content child is the mode-bar branch, whose chips are
`minHeight: 36` (`TradeFinderModeBar.tsx:163`). So the chips occupy roughly **y = 16…52**
and the toast bubble **y = 32…~75**. They overlap; `screens/mobile/trades/error.png` shows
"Guided" clipped to "G".

`zIndex: 50` is **correct** — the toast *should* paint above the chips. Raising the mode
bar above it would hide the message, which is strictly worse. The defect is the vertical
offset. HLD §10.6 item 5 records this as the plan being right and the audit being wrong.

### 8.2 `Toast.tsx` — three surgical edits

**(a)** Add to `interface Props`, after `action`:

```ts
  /** Distance from the top of the host view. Defaults to space.xxl (32) —
   *  every existing call site is byte-identical. Screens whose top content
   *  starts above 32pt (TradesScreen's mode bar) pass a measured offset so
   *  the bubble clears it instead of clipping it. */
  topOffset?: number;
```

**(b)** Destructure it in the signature, after `action,`:

```ts
export default function Toast({
  visible,
  message,
  tone = 'default',
  onDismiss,
  holdMs = 1500,
  action,
  topOffset,
}: Props) {
```

**(c)** Move `top` out of the static style into the inline array
(`Toast.tsx:99-102` and `:144-151`):

```tsx
    <Animated.View
      pointerEvents="box-none"
      style={[styles.wrap, { top: topOffset ?? space.xxl }, animatedStyle]}
    >
```

```ts
  wrap: {
    position: 'absolute',
    left: 0,
    right: 0,
    alignItems: 'center',
    zIndex: 50,
  },
```

`animatedStyle` supplies `opacity` + `transform` only, so it cannot conflict with `top`.
Style-array order puts the inline value after `styles.wrap`, which is what makes the
override take.

**Every other call site is untouched and byte-identical** — the default reproduces
today's 32 exactly. Grep `<Toast` across `mobile/src` before shipping to confirm no site
passes a positional/spread prop that would collide.

### 8.3 `TradesScreen` — measuring the mode bar

**State**, beside the existing measurement state (`const [topCardH, setTopCardH] =
useState<number | null>(null);`, ~`:382`):

```ts
  // P0-2 — bottom edge of the mode-bar region in ScrollView content
  // coordinates, so the Toast can clear it instead of clipping the chips.
  // 0 = not measured yet / not mounted ⇒ Toast keeps its 32pt default.
  const [modeBarBottom, setModeBarBottom] = useState(0);
```

**The Toast mount** (`:3316-3323`) gains one prop:

```tsx
      <Toast
        visible={!!toast}
        message={toast?.msg || ''}
        tone={toast?.tone}
        holdMs={toast?.holdMs ?? 1500}
        action={toast?.action}
        onDismiss={() => setToast(null)}
        topOffset={modeBarBottom > 0 ? modeBarBottom + space.sm : undefined}
      />
```

`undefined` (no mode bar mounted — `finderMode` null — or not yet laid out) falls back to
today's behaviour exactly.

**The wrapper.** Current structure inside the `ScrollView` (`:3436-3479`, comments
elided):

```tsx
        {finderMode ? (
          showInlineHome ? (
            <TradeHomeUtilityRow … />
          ) : (
            <TradeFinderModeBar … />
          )
        ) : null}
        {showInlineHome ? (
          <TradingWithStrip … />
        ) : null}
```

`TradeFinderModeBar`, `TradeHomeUtilityRow` and `TradingWithStrip` are custom components
that do not forward an `onLayout` prop, so the measurement needs a host `View`. Rewrite
the two sibling slots as **one conditional wrapper**:

```tsx
        {finderMode || showInlineHome ? (
          <View
            style={styles.modeBarWrap}
            onLayout={(e) => {
              const { y, height } = e.nativeEvent.layout;
              setModeBarBottom(y + height);
            }}
          >
            {finderMode ? (
              showInlineHome ? (
                <TradeHomeUtilityRow … />
              ) : (
                <TradeFinderModeBar … />
              )
            ) : null}
            {showInlineHome ? (
              <TradingWithStrip … />
            ) : null}
          </View>
        ) : null}
```

with

```ts
  // P0-2 — host view for the mode-bar measurement. `gap` REPLICATES the
  // ScrollView content container's gap between the two slots this wrapper
  // now contains; without it the strip would sit flush against the chip row.
  modeBarWrap: { gap: space.lg },
```

**Two layout traps this shape avoids, both of which the naive wrapper hits:**

1. **Collapsed gap.** `styles.scroll` sets `gap: space.lg` *between children*. Folding two
   children into one wrapper removes the gap between them — hence `modeBarWrap`'s own
   `gap: space.lg`, which reproduces it exactly.
2. **Phantom gap.** A wrapper rendered unconditionally would still count as a flex child
   when both slots are null, so the parent's gap would apply on **both** sides of a
   zero-height view — 32pt where there is 16pt today. Hoisting `finderMode ||
   showInlineHome` onto the wrapper keeps "nothing mounted" byte-identical.

In practice `showInlineHome` implies `finderMode === 'guided'`, so the hoisted condition is
equivalent to `!!finderMode`; it is written as the disjunction so the wrapper stays correct
if that coupling is ever relaxed.

**Coordinate space, stated as a known limit (accepted).** `layout.y` is relative to the
content container and *includes* its 16pt padding, so `y + height ≈ 52` and the toast lands
at ≈ 60 — clear of the chips. Because it is a **content** coordinate, a user who has
scrolled down can still get a toast over other content. That is no worse than today
(the toast is fixed at 32 regardless), and toasts here fire immediately after a
top-of-page tap. A synchronous `measureInWindow` was rejected as disproportionate.

**First-toast timing:** if a toast fires before `onLayout` has run, `modeBarBottom` is 0
and the toast uses 32 — i.e. today's behaviour, self-correcting on the next render. The
toast holds ≥5000 ms for `warn`/`error` under `ux.toast_v2` (`Toast.tsx:39,55-60`), so the
corrected position is visible well within the hold.

---

## 9. Maestro delta

Two files: one new flow, one **mandatory** capture edit. Conforms to
`mobile/.maestro/README.md` flow-authoring laws 1-23 (law citations inline below).

### 9.1 The harness seam — no new mechanism

`backend/test_support.py` is mounted only under `FTF_TEST_MODE=1` and its module docstring
states the property that makes Path B forceable **without any new seam**:

```
    POST /__test__/fail_next {path, status, count=1, body=null}
        Response override for the next `count` requests whose path matches
        the glob `path`. `status` may be ANY code including 2xx (precondition
        overrides, e.g. faking GET /api/sleeper/link → 200 {"connected": true}).
        Carve-out: /api/trades/propose refuses status < 400 — propose can
        never be overridden to success, so `completed_proposes` stays a
        meaningful guardrail.
```

Enforced in the route itself:

```python
@bp.route("/fail_next", methods=["POST"])
def fail_next():
    ...
    if not pattern or not isinstance(status, int) or count < 1:
        return jsonify({"error": "bad_injection", "need": "path, status(int), count>=1"}), 400
    # Normative carve-out: propose can never be overridden to success.
    if status < 400 and fnmatch.fnmatch(_PROPOSE_PATH, pattern):
        return jsonify({"error": "propose_2xx_refused", ...}), 400
```

and served from the before-request hook, which matches on `request.path` (query string
excluded — law 15) and decrements the counter per hit:

```python
    with _lock:
        for inj in _fail_injections:
            if inj["count"] > 0 and fnmatch.fnmatch(path, inj["pattern"]):
                inj["count"] -= 1
                body = inj["body"] if inj["body"] is not None else {"error": "ftf_injected"}
                return jsonify(body), inj["status"]
```

So: `/api/trades/status*` matches `getTradeStatus`'s `GET /api/trades/status?job_id=…`
(`mobile/src/api/trades.ts:267-272`), and a **200 whose body is an errored job snapshot**
drives `normalizeJobSnapshot` to `status: 'error'` with `error` preserved
(`trades.ts:245-251`). That is Path B, exactly, with production client code.

**Injection budget (law 11).** `count` maps 1:1 to poll attempts here: the poll loop is a
raw `getTradeStatus` call in a self-scheduling `setTimeout`, **not** a react-query
subscription, and `mobile/src/api/client.ts` retries only `RETRY_STATUSES = new Set([502,
503, 504])` on GETs. **500 is not retried**, so `count: 4` = four failed polls =
`MAX_POLL_FAILURES` exactly. Using 502/503/504 here would silently triple the budget.

### 9.2 New flow — `mobile/.maestro/flows/trades-generation-failure.yaml`

**Header:** `appId: com.fantasytradefinder.app`, `# tc: TC-TRD-ERR-01`,
`# profile: standard`, `# flags: release` (law 16 — a resolved fixture filename under
`backend/tests/fixtures/flags/`), `tags: [trades, error]`.

**Preamble:** copied verbatim from `mobile/.maestro/flows/smoke/05-trades-render.yaml`
`:9-49` — cold `launchApp` with `clearState: true, clearKeychain: true, stopApp: true`
(law 6), sign in as `qa_standard`, tap `leagues.row.990000000000000001`, settle on
`tab.trades`, conditional `outlook.save-btn` dismissal, then
`extendedWaitUntil visible: id: trades.find-btn, timeout: 20000` (law 8 — settle on a
surface-owned control before proceeding).

**Ordering is load-bearing.** The two poll legs run **before** any successful generation:
`_trade_job_is_fresh` lets `POST /api/trades/generate` serve a cached `complete` job
straight back, in which case polling never happens and the injection never fires. A fresh
session has no cached job. `INJECT_KIND: reset` is **never** used mid-flow — it clears
in-memory sessions and signs the app out (law 14; `inject.js:21-23`).

| # | Leg | Injection (`helpers/inject.js`) | Assertions |
|---|---|---|---|
| 1 | **Path B — job errors during polling** | `INJECT_KIND: fail_next`, `INJECT_PATH: "/api/trades/status*"`, `INJECT_STATUS: "200"`, `INJECT_COUNT: "1"`, `INJECT_BODY: '{"job_id":"ftf_injected","status":"error","error":"timeout","cards":[],"opponents_done":0,"opponents_total":0}'` | `assertTrue: ${output.inject.ok}` → tap `trades.find-btn` → `extendedWaitUntil visible: id: trades.deck-error` (timeout 30000); `assertVisible: id: trades.deck-error.retry`; `assertVisible: text: ".*took too long.*"`; `assertNotVisible: id: trades.empty-text` |
| 2 | retry from 1 | none | tap `trades.deck-error.retry` → `extendedWaitUntil visible: id: trades.card-top` (timeout 120000) |
| 3 | **Path C — poll abandoned** | `fail_next`, `/api/trades/status*`, `INJECT_STATUS: "500"`, `INJECT_COUNT: "4"`, real 500 body `{"error":"internal_error","message":"Unexpected server error."}` | tap `trades.find-btn` → `extendedWaitUntil visible: id: trades.deck-error` **`timeout: 45000`**; `assertVisible: text: ".*lost the connection.*"`; `assertNotVisible: id: trades.empty-text` |
| 4 | retry from 3 | none | tap `trades.deck-error.retry` → `trades.card-top` |
| 5 | **Path A — the POST fails** | `fail_next`, `/api/trades/generate`, `INJECT_STATUS: "500"`, `INJECT_COUNT: "1"`, `INJECT_BODY: '{"error": "internal_error", "message": "Unexpected server error."}'` (law 12 — the real production shape, identical to `capture/trades.yaml:85`) | tap `trades.find-btn` → `trades.deck-error` visible; `assertVisible: text: ".*couldn't finish that search.*"` (the **card**'s copy — the toast's `"Unexpected server error."` is transient and must not be the anchor); `assertNotVisible: id: trades.empty-text` |
| 6 | retry from 5 | none | tap `trades.deck-error.retry` → `trades.card-top` |

**Law conformance, stated so review can check it:**

- **Law 1** — every `text:` matcher is wrapped in `.*` (`".*took too long.*"`,
  `".*lost the connection.*"`, `".*Unexpected server error.*"`). `id:` selectors
  everywhere else; `text:` is used *only* to assert load-bearing error copy, which
  `docs/plans/mobile-testing/lld.md:253` permits.
- **Law 5** — no `waitForAnimationToEnd` before the error assertions: legs 3-4 pass
  through an `ActivityIndicator` ("Looking for trades…"), which the wait can never
  stabilise on. Anchor on `trades.deck-error` appearing instead.
- **Law 11/12** — budgets and bodies per §9.1.
- **Law 13** — every injection is armed **before** the tap that fires the request, and
  each is followed immediately by `- assertTrue: ${output.inject.ok}`.
- **Banned patterns** — no fixed sleeps, no coordinate taps, no `tapOn: text:`;
  `mobile/scripts/testid-lint.sh` enforces all three.

**Leg-3 timeout arithmetic.** Four polls at 800 ms → ×1.5 backoff capped at 4000 ms, ±10%
jitter, plus request time: ≈ 10-15 s. `timeout: 45000` is ~3× headroom.

**Leg-3 → leg-4 injection leakage (HLD §8 R13).** `count: 4` equals `MAX_POLL_FAILURES`
exactly, so a residual injection is only possible if the loop aborts before draining the
counter. Before leg 4, either assert the counter is drained via `GET /__test__/whoami`'s
`active_injections` (the endpoint returns `"active_injections": _active_injections()`), or
raise `count` to a value the flow then drains deliberately. **Decide on-sim at build time
and write the chosen answer into the flow's header comment** — do not leave both options
in the file.

### 9.3 Mandatory — `mobile/.maestro/capture/trades.yaml`

**This flow currently asserts the bug and breaks the instant the fix lands** (HLD §6
row 10, §8 R5). The error leg as it stands (`:71-94`):

```yaml
# ── error ────────────────────────────────────────────────────────────────
# The failure surfaces as a Toast, which carries no testID today, so there is
# nothing to wait on — we settle the tap animation and shoot. Body is the REAL
# production shape from server.py's handle_unexpected_error (errorhandler at
# backend/server.py:2070), so the toast renders shipping copy ("Unexpected
# server error.") instead of the injector's "ftf_injected" placeholder:
# client.ts:552 builds the message as parsed.message || parsed.error.
- runScript:
    file: helpers/inject.js
    env:
      INJECT_KIND: fail_next
      INJECT_PATH: "/api/trades/generate"
      INJECT_STATUS: "500"
      INJECT_COUNT: "1"
      INJECT_BODY: '{"error": "internal_error", "message": "Unexpected server error."}'
- assertTrue: ${output.inject.ok}
- tapOn:
    id: "trades.find-btn"
- waitForAnimationToEnd
- takeScreenshot: trades__error
- extendedWaitUntil:
    visible:
      id: "trades.empty-text"
    timeout: 20000
```

The four lines that break are the tail — `:91-94`:

```yaml
- extendedWaitUntil:
    visible:
      id: "trades.empty-text"
    timeout: 20000
```

After the fix, a failed `POST /api/trades/generate` leaves `trades.deck-error` mounted and
`trades.empty-text` **unmounted**, so this wait times out and the capture run dies before
the `loading` and `populated` states are ever shot.

**Edit — three parts, all in the same commit as the fix:**

1. Replace the trailing wait with a wait on the new state, and add the retry tap that
   returns the screen to a clean pre-`loading` baseline:

```yaml
- extendedWaitUntil:
    visible:
      id: "trades.deck-error"
    timeout: 20000
- takeScreenshot: trades__error
- tapOn:
    id: "trades.deck-error.retry"
- extendedWaitUntil:
    visible:
      id: "trades.card-top"
    timeout: 120000
```

   Note the shutter **moves**: `takeScreenshot: trades__error` now fires **after** the
   deck-error state is asserted visible, replacing the current
   `waitForAnimationToEnd` + blind shoot. That is a strict improvement and removes a
   law-5 hazard the old leg had to work around ("there is nothing to wait on").

2. Rewrite the leg's header comment — it documents the bug in the present tense
   (A-33 class). Replacement:

```yaml
# ── error ────────────────────────────────────────────────────────────────
# P0-2: a failed generate now renders a NAMED persistent state in the deck
# slot (trades.deck-error, red "SEARCH FAILED" + Try again), not just a Toast
# that fades back to the never-searched card. We anchor the shutter on that id
# — no blind waitForAnimationToEnd needed. Body is the REAL production shape
# from server.py's handle_unexpected_error, so the card renders shipping copy
# ("Unexpected server error.") instead of the injector's "ftf_injected"
# placeholder: client.ts builds the message as parsed.message || parsed.error.
```

3. Update the state-ordering block at the top of the file (`:12-21`) — the `error` line
   currently says "count=1 so it self-clears before the real run below". Extend it to note
   that the leg now ends by **retrying into a populated deck**, which is what leaves the
   screen in a clean state for the `loading` leg.

**Do not rename or remove `trades.empty-text`.** The `empty` leg (`:66-69`) still asserts
it, and must keep passing: after the fix the never-searched card means *exactly* what it
says, and its capture is the control that proves valid empty states did not turn red.

### 9.4 Capture library

`mobile/scripts/screen-capture.sh --screen trades` at ship (executed by **W3-QA**, HLD
§4 wave 3). `screens/mobile/trades/error.png` changes materially, and every trades frame
carrying a toast shifts because the offset moves. Optional and **not** required for
acceptance: `error--poll` / `error--job` capture ids distinguishing the three failures.

### 9.5 Smoke impact

`flows/smoke/05-trades-render.yaml` and `flows/smoke/06-trades-deck.yaml` cross this
surface. Re-read at `ab9368f`: `05` asserts `trades.empty-text` only on the **resting**
state after the preamble, with no injected failure anywhere in the file, so it is expected
to stay green. **Verify on-sim, do not assume** (the whole point of HLD §8 R5).

---

## 10. `testID`s, lint, and types

**New ids (2):** `trades.deck-error` (the container `View`), `trades.deck-error.retry`
(the `Button`). Both are plain string literals, so `mobile/scripts/testid-lint.sh` finds
them by source grep over `mobile/src` and **no `testid-lint-allow.txt` entry is needed**
(law 4). They follow the in-file `trades.deck-summary` / `trades.deck-summary.see-liked`
precedent. Registration in `mobile/src/components/CLAUDE.md` is **documentation**, owned by
`W3-DOCS` (HLD §10.3 — the lint never opens that file), and is **not** a wave-2 dependency.

**Type surface (2 additions, both narrow):**

- `type DeckFailure` — module-local, not exported.
- `Toast`'s `topOffset?: number` — optional, so every existing call site type-checks
  unchanged.

`cd mobile && npx tsc --noEmit` must be clean. **`mobile/node_modules` is a symlink —
never run `npm install`.**

---

## 11. Verification checklist for the build agent

Ordered as the agent should work. Items 1-3 are the pre-fix control run: **a test that
never observed the bug proves nothing** (HLD §8 R5).

1. **Control run, before any edit:** run `capture/trades.yaml` on the unfixed tree — it
   must **pass**, ending on `trades.empty-text`. That is the recorded proof the flow was
   asserting the bug.
2. **Control run, defect G-027:** fresh state, sign in, and inject
   `fail_next /api/trades/status* 500 count:4` before the first-run auto-start settles.
   Confirm the `SkeletonTradeCard` persists indefinitely with no recovery affordance.
   Record it — this is the evidence behind the GOTCHAS row W3-DOCS will write.
3. **Re-grep every anchor in §1.3** before touching a line. Line numbers are stale by
   assumption.
4. Apply §2, §3, §4, §5, §6 to `TradesScreen.tsx`; §8.2 to `Toast.tsx`.
5. `cd mobile && npx tsc --noEmit` → clean.
6. `bash mobile/scripts/testid-lint.sh` → exit 0.
7. `python3 -m pytest backend/tests/ -q` → clean (regression only; **P0-2 changes no
   backend file**).
8. Apply §9.3 to `capture/trades.yaml`; author §9.2's flow; run both on sim. Decide the
   leg-3 drain question on-sim and write the answer into the flow header.
9. Re-run the G-027 repro from item 2: the skeleton must be **replaced by the error card**,
   not merely unstuck.
10. Eyeball every screenshot (law 23) — in particular that the deck-done summary, "That's
    all for now", and the never-searched card are **visually unchanged**, and that the
    toast now clears the mode-bar chips.
11. Hand the docs rows to `W3-DOCS` via the scope block: `D-025`, `G-027`,
    `docs/design/components.md` (resolved — see §12.4), `NEXT.md` (the
    `find_trades_tapped` allowlist gap), `CHANGELOG.md`.

---

## 12. Refinements to the source plan, and non-deviations from the HLD

**Deviations from `hld.md`: none.** Every settled decision S-08 (first-run shows the
card), S-09 (partial-deck note deferred), S-10 (unflagged), S-11 ("Try again"), S-12 (no
analytics) is implemented as written, in commit 11, under W2-TS, with §6 rows 5 and 10
delivered.

The five items below are **refinements to `plan-p0-2.md`**, made while reading the code.
None changes an HLD row, an acceptance criterion, or a surface answer.

### 12.1 Path A's fallback is `DECK_FAIL_GENERIC`, not `e.message`

The plan's prose says "Path A's message *is* echoed". Read literally against
`readErrorCopy(e, GENERIC)`, the echo only happens when `GENERIC` is replaced by
`e.message` — which the plan does not do. **Resolution, and the shipped behaviour:**
`readErrorCopy(e, DECK_FAIL_GENERIC)` returns the verification-403 copy when that is the
error and `DECK_FAIL_GENERIC` otherwise. The toast (unchanged) still carries `e.message`
verbatim, so the curated server string is not lost to the user — it is on the transient
surface, while the persistent card carries copy that is *always* actionable. This also
removes the last route by which an unmapped server string could land on the persistent
card, which is the spirit of `D-025`. Consequence for the flow: **leg 5 anchors on the
card's own copy** (`".*couldn't finish that search.*"`), not on the toast's
`"Unexpected server error."` — the toast is transient and would make the assertion a
race. The injected body still uses the real production shape (law 12) because the toast
must render shipping copy in the captured frame.

### 12.2 The mode-bar wrapper needs its own `gap`, and must be conditional

Plan item 18 says "wrap the mode-bar branch in a `<View onLayout=…>`". Done naively that
collapses the 16pt gap between the mode bar and `TradingWithStrip` (the parent's `gap`
applies between *children*, and the two slots become one child), and an unconditional
wrapper doubles the gap to 32pt when nothing is mounted. §8.3 specifies
`modeBarWrap: { gap: space.lg }` and hoists `finderMode || showInlineHome` onto the
wrapper. Byte-identical layout in all three configurations.

### 12.3 `semantic` is already imported; `readErrorCopy` is not

The plan asks the builder to "confirm before editing". Confirmed at `ab9368f`: `semantic`
is imported at `TradesScreen.tsx:39` inside the `../theme/chalkline` block — **no import
change**. `readErrorCopy` has zero hits — **one new import line** (§3.5).

### 12.4 `docs/design/components.md` resolves to **n/a**, not "check at build"

Both the plan and HLD §7 leave this open. Resolved by reading the file: its § Feedback &
status is a `| Component | Spec | Replaces |` table whose Toast row specs the **visual**
treatment (`--ink-2`, hairline border, `--shadow-sheet`, 3px tone rail, `body` text) and
the CSS/component it replaces. The document specs **no React prop surface for any
component**. `topOffset` defaults to today's `space.xxl`, so the specced visual is
unchanged. → **n/a because** the doc specs Toast's visual treatment, not its props. Passed
to W3-DOCS as a resolved row so nobody re-opens it.

### 12.5 The retry button ships without a `disabled` prop

Reasoned in §6.3: all three states that would justify it are structurally unreachable
(rows 5 and 7b are mutually exclusive; the league-switch effect clears `deckFailure` on any
`leagueId` change). Recorded so a reviewer does not read the omission as an oversight.
