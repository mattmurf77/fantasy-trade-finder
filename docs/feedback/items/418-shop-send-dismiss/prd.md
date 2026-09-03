# FB-418 — mini-PRD: "Send this offer" dismisses the shop tile

> Fast-track bug. Mobile only, two files, no schema / API / flag / analytics
> change. Companion docs: [`scope.md`](scope.md) · [`plan.md`](plan.md) ·
> [`status.md`](status.md). Every `file:line` below was read on
> `origin/main` @ `c7e75666` (2026-09-03).

## Contents

- [1. Problem](#1-problem)
- [2. Repro](#2-repro)
- [3. Root cause](#3-root-cause)
- [4. Requirements](#4-requirements)
- [5. Decisions recorded](#5-decisions-recorded)
- [6. Out of scope](#6-out-of-scope)
- [7. Guardrails — the rulings this fix must respect](#7-guardrails--the-rulings-this-fix-must-respect)
- [8. Test plan](#8-test-plan)
- [9. File ownership](#9-file-ownership)

## 1. Problem

**Report (verbatim, operator, 2026-09-02, v1.16.14, screen `ShopAsset`,
severity bug):** *"Hitting send this offer should dismiss the card"*

In the shop window (#402/#403 rev-3 — Trades deck → give-side "More offers" →
pushed `ShopAssetScreen`), each idea tile has two decisions: ✕ dismiss and ✓
**"Send this offer"**. Dismissing a tile removes it from the pager at once
(with a held, undoable POST). Sending an offer queues it server-side, shows the
success toast — and **leaves the tile exactly where it was**, counter and chip
counts unchanged. The user has acted on the idea; the surface still presents it
as undecided. Tapping ✓ again yields "Already queued for @X." — the idempotence
signal, not a bug, but proof the tile is stale.

## 2. Repro

1. Trades → any deck card → give-side **More offers** (or pick a row in the
   "Shop which player?" sheet) → the shop window opens with `1 / N` (N ≥ 2).
2. Tap **Send this offer** on tile 1.
3. Observe: toast *"Queued for @X — it'll show in their suggestions."* — and the
   same tile is still on screen; counter still `1 / N`; the active mode chip
   still says `· N`.

**Expected:** the tile leaves the pager, tile 2 is fronted at the same
position, counter reads `1 / N-1`, the chip count drops by one.

## 3. Root cause

`mobile/src/components/ShopOffersBody.tsx`:

- The ✓ button (`testID="shop.like-btn"`, `:1033`; `onPress={() => handleLike(item)}`, `:1039`)
  calls `handleLike` (`:696-715`), which awaits `queueCalcTrade(...)` (`:701-710`),
  hands the returned descriptor to the screen's toast mount (`onToast(res.toast)`,
  `:711`) and releases the `busyKey` lock in `finally` (`:712-714`). **It never
  touches the pager's data.**
- Compare `handleDismiss` (`:614-648`): it requests the pager index first
  (`requestPagerScroll(index)`, `:625`), then adds the tile's key to the pending
  set (`setLocallyRemoved(...)`, `:626`), and arms the Undo timer (`:635-638`).
  When the held POST commits, `commitDismiss` (`:534-561`) promotes the key into
  `suppressed` (`:540`) and drops it from `locallyRemoved` (`:541-545`).
- The pager renders `visibleIdeas = visibleByMode[mode]` (`:519`), and
  `visibleByMode` (`:509-518`) filters every mode's group through **both** sets
  (`!locallyRemoved.has(k) && !suppressed.has(k)`, `:514`). The `1 / X` counter
  (`:955`), the chip counts (`:835`, `:849`) and `baselineModeCount` (`:492-502`)
  all read the same shape. So a key that enters either set disappears from every
  count at once — and a liked tile's key enters neither.
- The two sets are documented at `:301-326`: `locallyRemoved` is **pending**
  (undo-able, at most one, promoted or restored), `suppressed` is **committed**
  (session-authoritative, never cleared by data — Fix A / rulings 2026-08-28 R-A).

## 4. Requirements

**R-1 — A queued like removes the tile for the rest of the shop session.**
When `queueCalcTrade` resolves with `queued: true` — **including
`alreadyQueued: true`**, which is still `queued: true`
(`mobile/src/utils/queueCalcTrade.ts:87-101`) — `handleLike` adds
`assetIdeaKey(idea)` to **`suppressed`** (`setSuppressed((s) => new Set(s).add(key))`,
the `commitDismiss` shape at `ShopOffersBody.tsx:540`). A sent offer is
committed server-side by the queue call itself; there is no undo window and no
pending state, so `locallyRemoved` is the wrong set. Like a committed dismiss,
the key lives until the pushed `ShopAssetScreen` unmounts (`:311-316`) and is
never cleared by a data tick (`:309-311`, guard `n2d`).
*Pass:* guard `k1`, `k2`, `k4`, `k5` (§8.1); checklist steps 2–5, 7 (§8.3).

**R-2 — Counter and chip counts shrink with it — automatically.** `1 / X`
(`:955`), the per-mode chip counts (`:835`, `:849`), the "Clear positions — N at
POS" label (`:904-905`) and the "other modes have offers" hint (`:912`, `:928`)
all derive from `visibleByMode` / `baselineModeCount`, which filter through
`suppressed`. **This is a pass criterion, not an implementation step**: no
count is touched by the fix; any count that does not drop is a regression.
*Pass:* existing guards `e` (counter = pager list), `n2e`, `n2f`; checklist step 2.

**R-3 — The next tile is fronted at the same index, via P-1.** Before the
state write, `handleLike` calls `requestPagerScroll(index)` (`:728-730`) — the
tap-time index — and the single reactive effect (`:731-747`) performs the
scroll on the render whose FlatList already holds the shrunk list, clamped to
`visibleIdeas.length - 1` (`:735`). Never `scrollToOffset` at event time
(`:718-726`; guard `n3a`). The arithmetic, verified against `:735` for a
like on 0-based tile `k` of `N` (list shrinks to `N-1`, request is `k`):
`k < N-1` ⇒ `clamped = k`, the former `k+1` now sits at `k` and is fronted
(the FlatList's `contentOffset` is already `k·pagerW`, so the scroll is a
no-op and the next tile is simply there); `k = N-1` (the **last** tile) ⇒
`clamped = N-2`, the new last tile; `N = 1` ⇒ `clamped = 0`, the pager branch
unmounts (`:878`), `listRef.current` is null by the time the effect runs
(React nulls refs in the commit, before effects), so the `?.` at `:738` skips
the scroll — the same path the last-tile dismiss already takes today. When it
was the **only** one the existing empties render: the **filtered** empty
(`testID="shop.empty"` with `testID="shop.clear-positions"`, `:887-917`) when a
position selection is settled, otherwise the **unfiltered** per-mode empty
(`testID="shop.empty"`, `EMPTY_HEAD[mode]`, `:923-933`). A like that empties
Same value does **not** trigger auto-widen: `widenEligible` (`:435-440`) reads
the server's raw `groups.lateral.length`, not the filtered list — the same
"dismissals don't count" rule at `:416-417`.
*Pass:* guard `k3` (request precedes the write); checklist steps 2, 6.

**R-4 — A refused queue leaves the tile in place.** `queued: false`
(`queueCalcTrade.ts:103-110` — any server reason, or the network catch at
`:76-78`) writes nothing to either set; the refusal toast is unchanged; the
tile stays at the same index; `busyKey` is released in `finally` exactly as
today (`ShopOffersBody.tsx:712-714`) and the pair re-enables.
*Pass:* guard `k4` (the write is conditional on `queued`); checklist step 8.

**R-5 — Toast copy is unchanged; `queueCalcTrade` is not edited.** Both success
lines and every refusal line come from `mobile/src/utils/queueCalcTrade.ts`,
shared with `TradesScreen.handleInlineLikeTrade` (`TradesScreen.tsx:3222-3244`)
and the pushed calculator. The helper is **not** in this fix's ownership.
*Pass:* `git diff --name-only` contains no `queueCalcTrade.ts`; checklist steps 2, 7, 8 read the shipped strings.

**R-6 — No new analytics event.** `calc_trade_queued {queued}` (and
`{queued:false, reason}`) already fires inside `queueCalcTrade`
(`queueCalcTrade.ts:82-86`) with `screen: 'ShopAsset'`
(`ShopOffersBody.tsx:709`; guard `h5d`). The removal is a client-side
consequence of an event that is already recorded; nothing new is emitted.
This is the scope block's §1(b) answer.
*Pass:* guard `h` (event registry unchanged) stays green; no `track(` added to `handleLike`.

**R-7 — A pending dismiss on a different tile is unaffected.** A like writes
only `suppressed`; the pending entry's key stays in `locallyRemoved`, its
timer keeps running, and it commits or restores on its own path. The
queue toast **replaces** the "Dismissed · Undo" toast on screen (one slot,
`ShopAssetScreen.tsx:43-54`) — that is shipped behavior, explicitly ruled at
`ShopOffersBody.tsx:572-578` (QA B-4: a newer toast replacing the Undo toast
leaves the pending dismiss on its timer; the harm B-4 named was a *dead* Undo
button, never the replacement). Liking **the tile that has the pending dismiss
is impossible**: that tile is already out of the pager (its key is in
`locallyRemoved`, filtered at `:514`), so its ✓ cannot be tapped. Two
verified details of the replacement: the screen's `Toast` re-arms its hold
timer at the new descriptor's 1500 ms (`Toast.tsx:76-92`, deps include
`effectiveHoldMs`), and `undoToastRef` stays set, so a later *early* flush's
retract is the by-reference no-op `ShopAssetScreen.tsx:68` was built for.
The reverse order is also reachable — `busy` is per-key (`:982`), so while
B's like is in flight the user can swipe and ✕ tile C, arming a pending
dismiss mid-round-trip; B's later `requestPagerScroll(at)` then supersedes
C's already-consumed request (clamped, never off-list — D-2), and C's timer,
key and toast are untouched by B's write.
*Pass:* guard `k6` (no flush from the like — see D-1 below); checklist step 9.

**R-8 — `busyKey` behavior is unchanged.** `if (busyKey) return` (`:698`),
`setBusyKey(key)` (`:699`), `finally { setBusyKey(null) }` (`:713`) stay as
they are. The suppressed tile unmounts while `busy` may still be true for one
render; harmless, and the lock releases in `finally` regardless. The
suppression write lives **inside the `try`, after the `await`** — never in
`finally` (which also runs on the refused path) and never before the queue
resolves (an optimistic removal would be a lie on refusal).
*Pass:* guard `k7` (release in `finally`, write inside the `try` after the await); `i3` (like reaches `queueCalcTrade`, never `swipeTrade`) stays green.

**R-9 — The file's own comments stay true.** Three comments currently say the
suppression set has exactly one gate and must be edited in the same diff, or
the file lies about itself: the `suppressed` block (`:306-309`, "Keys enter
this set only when a held dismiss COMMITS"), the `commitDismiss` note (`:536-537`,
"the commit is the ONE gate into the suppression set"), and the header's
"✓ like" bullet (`:77-82`). Each gains one clause naming the second gate: a
**queued like** (#418), with the item number in the clause so it can be
found. The `suppressed` block's clause must also correct its *memory* claim,
because that block says two more things a like makes false: "Cross-session
memory is the SERVER's … the next fetch simply doesn't offer a recently
dismissed idea" and "This set only bridges the in-instance gap between a
commit and that next fetch" (`:314-319`). For a queued like there is **no**
server-side memory — `POST /api/trades/asset-ideas` does not consult the
queue (§6) — so the next fetch **will** re-offer the idea and this set is its
only filter for the rest of the session. One sentence saying exactly that;
nothing else in the block changes. The guard file's own header bullet
(`check-shop-deck.js:50-51`, "the suppression set is commit-only") gets the
same clause, or the suite lies about what it pins. Surgical — no other
comment is touched.
*Pass:* guard `k8` (the three body sites carry `#418`); code review of the wording.

## 5. Decisions recorded

**D-1 — A like does NOT call `flushPendingDismiss()`.** R-9's flush triggers
(`ShopOffersBody.tsx:87-89`, lld-delta §6.1 "at most one pending") are the
events that would either create a *second* pending disposition (a second
dismiss, `:618`) or invalidate the pending one's idea reference / restore
index (mode change `:752`, selection change `:767`, clear `:779`, fresh
payload `:677`, unmount `:652`). A like does neither — it creates no pending
state and changes no idea reference — and the shipped B-4 comment at
`:572-578` already rules that a ✓ success toast replacing the Undo toast
leaves the pending dismiss on its timer. Flushing here would add a fourth
early-commit path for no invariant. Pinned by guard `k6`.
**Premise, verified:** the like path performs no query invalidation —
`git grep -n "invalidateQueries\|refetchQueries\|setQueryData" --
mobile/src/api/trades.ts mobile/src/utils/queueCalcTrade.ts
mobile/src/components/ShopOffersBody.tsx` is empty and
`queueTradeForOpponent` (`api/trades.ts:601-620`) is a bare `api.post` — so
a like never ticks `ideasUpdatedAt` and never enters the flush-and-rewind
effect at `:676-679` by the back door. If a future change makes the queue
call invalidate `['shop-ideas', …]`, D-1 is broken by construction and must
be revisited.

**D-2 — The request index is the render-time `index`, and no live ref is
added.** `handleLike` is re-created every render and closes over that
render's `index` (`useState`, `:300`); the FlatList cell's `onPress` (`:1039`)
is refreshed with it on every parent render, and `onMomentumScrollEnd`
(`:975-979`) re-renders before a settled page can be tapped — so the closure's
`index` is the tapped tile's index. Because it is a closure **constant**, its
value is identical before and after the `await`; `const at = index` (the
`restoreIndex` shape at `:619`) is therefore a readability capture, not a
correctness one — permitted, not required, and the guard `k3` accepts either
`requestPagerScroll(at)` or `requestPagerScroll(index)`. What the fix must
**not** do is read a live index (a ref updated by the pager) after the await.
Consequence, stated precisely: if the user swipes during the sub-second
round-trip, the pager fronts **the tile that took the liked tile's slot**
(the former `k+1`, now at `k`) — which is exactly where one forward swipe
left them, one tile behind two forward swipes, and one tile ahead of a
backward swipe; always clamped, never off-list. A second residual, accepted:
a refetch landing *during* the round-trip (a position toggle, or a
focus/stale refetch) rewinds the pager to 0 (`:678`) and the like's
resolution then jumps it to `at`. Both windows are sub-second and the
outcome is a position, never a wrong tile removed; a live-index ref for
this is not worth its lines (coding-guidelines §2).

**D-3 — Extend `check-shop-deck.js`; no new guard file, no `package.json`
change.** The existing suite already parses this body with the helpers the new
assertions need (`functionNamed` `:147`, `referencesIdentifier` `:141`,
`nearestAncestor` `:154`), already pins `handleLike` (`h5d`, `i1`, `i3`) and
the suppression set (`n2a-f`), and is organized in lettered sections a new
one slots into. A separate file would duplicate ~100 lines of AST helpers to
hold eight assertions. Its `npm run test:shop-deck` script exists
(`mobile/package.json:85`) and CI runs every `tests/check-*.js`
(`.github/workflows/ci.yml:47`).

## 6. Out of scope

- **Cross-session memory for a sent offer.** `POST /api/trades/asset-ideas`
  does not consult the queue table, so a queued idea can be offered again in a
  *new* shop window (a dismissed one cannot — the D-067 dismiss-cooldown,
  `:316-319`). Re-tapping ✓ there yields the honest "Already queued" toast and
  the tile leaves again (R-1). A server-side exclusion is a backend change and
  a separate item.
- **Any change to `queueCalcTrade.ts`, `ShopAssetScreen.tsx`, `TradesScreen.tsx`,
  the calculator's ✓, or the deck's swipe-like.** Only the shop body changes.
- **Undo for a sent offer.** There is no un-queue route; the like is committed
  by the call (§4 R-1).
- **Analytics.** Nothing new (R-6).

## 7. Guardrails — the rulings this fix must respect

1. **P-1 universal rule** (rulings 2026-08-28 R-C; `ShopOffersBody.tsx:718-726`):
   never `scrollToOffset` at event time. Request an index, change the data,
   let the effect scroll. Guard `n3a` fails on a second `scrollToOffset`.
2. **Fix A** (rulings 2026-08-28 R-A; `:306-326`): `suppressed` is commit-only
   and never cleared by a data tick. The like is a *second commit gate*, not a
   new clear path. `handleDismiss` / `undoDismiss` still never touch it (`n2c`).
3. **R-5 counter honesty** (402 prd §2): the counter, pager and chip counts read
   one list. Do not add a parallel count or a `-1` anywhere.
4. **R-9 held undo** (402 prd §2; lld-delta §6.1): the like does not flush the
   pending dismiss (D-1). `handleDismiss` stays timer-armed, `undoDismiss` stays
   a pure cancel (`i5`, `i6`).
5. **QA B-4 retract-by-reference** (`:568-578`; `ShopAssetScreen.tsx:65-68`):
   do not retract or re-issue the Undo toast from the like path.
6. **Ruling A** (rulings 2026-08-27 R-A): the like is `queueCalcTrade` → `POST
   /api/trades/queue` as-is; never `swipeTrade` (`i3`).
7. **Never edit `queueCalcTrade.ts`** — three hosts share it.
8. **Never open `TradesScreen.tsx`** (402 prd §5 guardrail 1).
9. **`npm ci` in the worktree**; never symlink the main checkout's
   `node_modules`.
10. **Chalkline**: no new UI. Nothing to add; guard `n4` stays green.

## 8. Test plan

D-056: no Maestro, no simulator, no captures. Evidence = structural guard +
code-walk proof + manual TestFlight checklist.

### 8.1 Structural guard — new section `(k)` in `mobile/tests/check-shop-deck.js`

Insert after section `(i)` (`:790-846`), same helpers, same `assert(cond,
name, detail)` form. **Each assertion counts only after it has been observed
red under its named sabotage, then green after revert** (402 prd §6.4).

| # | Assertion (on `functionNamed(sf,'handleLike')`) | Sabotage that proves it red |
|---|---|---|
| **k1** | references `setSuppressed` | S-1: delete the `setSuppressed(...)` statement |
| **k2** | references neither `setLocallyRemoved` nor `locallyRemoved` | S-2: write to `setLocallyRemoved` instead of `setSuppressed` (k1 also red) |
| **k3** | references `requestPagerScroll`, and the first `requestPagerScroll` identifier's start offset is **less than** the first `setSuppressed` identifier's start offset inside the function. Write it so a *missing* identifier on either side is a **fail**, not a vacuous pass (`findAll` inside the function range, then `a.length && b.length && a[0].getStart() < b[0].getStart()`) | S-3a: swap the two statements · S-3b: delete the `requestPagerScroll` call |
| **k4** | the `setSuppressed` call's nearest ancestor `IfStatement` (via `nearestAncestor`) exists, its `expression` references identifier `queued` (`res.queued` — `referencesIdentifier` matches the member name), the call lies inside that statement's **`thenStatement`** range (not an `else`), and the condition text contains no `!` — closing the inverted-branch hole (`if (res.queued) {toast} else {suppress}`) that a bare ancestor check would pass | S-4a: drop the `if` so suppression is unconditional · S-4b: move the write into an `else` |
| **k5** | does **not** reference `alreadyQueued` (an already-queued idea is still queued and still leaves) | S-5: `if (res.queued && !res.alreadyQueued)` |
| **k6** | does **not** reference `flushPendingDismiss` or `flushPendingDismissRef` (D-1) | S-6: insert `flushPendingDismiss();` before the queue call |
| **k7** | the function's `TryStatement` has a `finallyBlock` that references `setBusyKey`, and the `setSuppressed` call's start offset is inside the `tryBlock` range **and greater than** the `AwaitExpression`'s start offset (R-8: release in `finally`; the write is post-resolution, never optimistic) | S-7a: move `setBusyKey(null)` out of `finally` into the `try` · S-7b: move the suppression write above the `await` |
| **k8** | the body's source text contains `#418` in at least **three** places, and one of them lies inside `commitDismiss`'s range (R-9: the header bullet, the `suppressed` block, and the commit note all name the second gate). Textual by nature — a tripwire for a stale comment, not a semantic proof | S-8: delete the `commitDismiss` clause |

Existing assertions that must **stay green** on the fixed file, as the
regression fence: `e` (counter reads the pager's list), `h5d` (screen
`'ShopAsset'`), `i1`/`i3` (uncrossed, reaches `queueCalcTrade`), `i5`/`i6`
(dismiss held, undo pure), `n2b`/`n2c`/`n2d`/`n2e`/`n2f` (suppression-set
discipline), `n3a`/`n3b` (P-1). Run: `cd mobile && npm run test:shop-deck`.

### 8.2 Code-walk proof (QA writes this against the built diff)

A file:line trace, each hop cited against the **fixed** file:

1. **Tap** — `shop.like-btn` `onPress` → `handleLike(item)` (today `:1033-1039`).
2. **Lock** — `busyKey` guard + `setBusyKey(key)` (today `:698-699`); the tile's
   `Button` shows `loading` (today `:1038`).
3. **Queue** — `await queueCalcTrade({... screen:'ShopAsset'})` (today `:701-710`)
   → `queueTradeForOpponent` → `POST /api/trades/queue`; `calc_trade_queued`
   fires inside the helper (`queueCalcTrade.ts:82-86`).
4. **Branch** — `res.queued === true` (incl. `alreadyQueued`) → step 5; `false`
   → step 8.
5. **Request, then write (P-1)** — `requestPagerScroll(at)` sets
   `pendingScrollRef` (today `:728-730`); `setSuppressed(s => new Set(s).add(key))`.
6. **Recompute** — `visibleByMode` memo re-runs on `[groups, locallyRemoved,
   suppressed]` (today `:509-518`), filtering the key out of every mode;
   `visibleIdeas` (today `:519`) is a new reference; `1 / X` (today `:955`), chip
   counts (today `:835`, `:849`) and `baselineModeCount` (today `:492-502`)
   re-derive from it.
7. **Effect clamp + scroll** — the `[visibleIdeas, pagerW, ideasUpdatedAt]`
   effect (today `:731-747`) consumes `pendingScrollRef`, clamps to
   `visibleIdeas.length - 1` (today `:735`), `setIndex(clamped)` (today `:736`),
   `scrollToOffset({offset: clamped * pagerW, animated:false})` (today
   `:738-741`) → the next tile is fronted; if `visibleIdeas.length === 0` the
   pager branch is skipped and the empty state renders (today `:878-934`).
8. **Toast + unlock** — `onToast(res.toast)` (today `:711`) →
   `ShopAssetScreen` `setToast` (`ShopAssetScreen.tsx:64`); `finally`
   releases `busyKey` (today `:712-714`). On the refused branch this is the
   only effect — no set was written, the tile is still at `index`.

### 8.3 Manual TestFlight checklist (operator, first build carrying the fix)

Every step names the regression it catches. Steps 2, 2b, 6 and 8 are the
must-runs; 3–5, 7, 9 are the interaction fences.

1. **Open the window.** Trades → a deck card → give-side **More offers** (or a
   chooser row) → shop window; pick a mode whose chip shows **≥ 3** offers.
   Note the counter `1 / N` and the chip's `· N`. ☐
2. **Send on tile 1.** Tap **Send this offer** → toast *"Queued for @X — it'll
   show in their suggestions."*; the tile is **gone**, the **next** tile is on
   screen without you swiping, the counter reads **`1 / N-1`**, the mode chip
   reads **`· N-1`**. *(R-1, R-2, R-3)* ☐
2b. **Send on a middle tile.** Swipe to tile 2 (counter `2 / N-1`, N-1 ≥ 3)
   → tap **Send** → the tile that was 3rd is now on screen, counter reads
   **`2 / N-2`** — the pager held its position, it did not rewind to 1.
   *(R-3 — the `k < N-1` clamp case; step 2 only covers `k = 0`)* ☐
3. **It stays gone.** Swipe through every tile in this mode: the sent idea
   (same partner, same pieces) does not appear. *(R-1)* ☐
4. **Survives a mode round-trip.** Switch to another mode and back → still
   absent, counts unchanged from step 2. *(Fix A — session-authoritative)* ☐
5. **Survives a refetch.** Toggle a position chip, wait for the sweep, clear it
   → still absent. *(Fix A — never cleared by a data tick)* ☐
6. **Last tile → empty state.** In a mode with exactly **1** offer left
   (dismiss down to one if needed and let the Undo toast expire), tap **Send**
   → toast, then the **empty state** with no counter row and no spinner:
   *"No <mode> offers cleared the bar"* if no position chip is selected, or
   *"Nothing at <POS>"* with a **Clear positions** button if one is. The chip
   reads `· 0`. In Same value this must **not** silently swap in an
   all-positions notice. *(R-3)* ☐
7. **Already queued.** Go back, reopen the window for the same player
   **within a minute** of step 2 — the shop-ideas cache row is warm for
   `staleTime: 60_000` (`:410`) and the same key `['shop-ideas', league,
   asset, '']` (`:388`) is read, so the same ideas return and the new
   instance's empty `suppressed` shows the sent one again. Find the idea from
   step 2, tap **Send** → toast *"Already queued for @X."* **and** the tile
   leaves exactly as in step 2. *(R-1 — alreadyQueued is queued.)* If more
   than a minute has passed the sweep re-runs, and because the like moved
   the Elo board (ruling 2026-08-27 A, `trade_k_like`) the idea may
   legitimately be absent or in another mode — that is not a failure; redo
   the step inside the window. ☐
8. **Refused queue → tile stays.** Turn on **Airplane Mode**, tap **Send** on
   any tile → toast *"Couldn't queue that. Try again."*; the tile is **still on
   screen**, counter unchanged, both buttons enabled again. Airplane Mode off.
   iOS usually fails the request at once; if the client waits out its 15 s
   deadline instead (`api/client.ts:230`), the button shows its spinner
   until then — the toast and the re-enabled pair are the pass, not the
   latency. *(R-4. This forces the network-catch refusal; server-side
   reasons — untouchable, not-interested, fairness floor — need a second
   account's preferences and are covered by code-walk step 4 / guard k4
   only.)* ☐
9. **Pending dismiss + like on the next tile.** Dismiss tile A (the *Dismissed ·
   Undo* toast shows and tile B is fronted); within 5 s tap **Send** on B →
   the queue toast replaces the Undo toast; B leaves; A does **not** come back;
   wait 6 s → nothing reappears, no second toast. *(R-7 / D-1)* ☐

### 8.4 Pass criteria — one line per requirement

| Req | Guard | Code-walk hop | Checklist |
|---|---|---|---|
| R-1 | k1, k2, k4, k5 | 5–6 | 2, 3, 4, 5, 7 |
| R-2 | e, n2e, n2f (existing) | 6 | 2, 2b, 6 |
| R-3 | k3, n3a, n3b (existing) | 5, 7 | 2, 2b, 6 |
| R-4 | k4, k7 (write is post-resolution) | 4, 8 | 8 |
| R-5 | diff contains no `queueCalcTrade.ts` | 3 | 2, 7, 8 (copy read verbatim) |
| R-6 | h, h5d (existing); no new `track(` in `handleLike` | 3 | — |
| R-7 | k6 | 5 (only `suppressed` written) | 9 |
| R-8 | k7; i3 (existing) | 2, 8 | 8 |
| R-9 | k8 (tripwire); wording review | — | — |

## 9. File ownership

Exactly two files:

| File | Change |
|---|---|
| `mobile/src/components/ShopOffersBody.tsx` | `handleLike` (today `:696-715`): inside the `try`, after the `await`, on `res.queued` call `requestPagerScroll(index)` (or a captured `at` — D-2) then `setSuppressed(...)`; three comment clauses (R-9), each carrying `#418`. Nothing else. |
| `mobile/tests/check-shop-deck.js` | New section `(k)`, eight assertions k1–k8 (§8.1), inserted after `(i)`; one clause on the header bullet at `:50-51` (R-9). |

No `mobile/package.json` change — `test:shop-deck` exists (`:85`). Forbidden:
`mobile/src/utils/queueCalcTrade.ts`, `mobile/src/screens/ShopAssetScreen.tsx`,
`mobile/src/screens/TradesScreen.tsx`, `backend/**`, `config/features.json`.
