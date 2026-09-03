# FB-418 — QA agent B (adversarial product / behavior review)

> Independent of QA agent A (mechanical re-proof). Angle: assume the fix is
> mechanically correct and ask whether it does the right thing on a real
> phone. Reviewed commit `f593020a` (parent `c7e75666` = `origin/main`) on
> branch `claude/new-user-feedback-06dabd`, 2026-09-03. Every `file:line`
> below is from the **fixed** tree unless marked `(main)`. Nothing was
> edited in the session tree; the builder's build-notes were treated as
> claims and re-verified where they bear on a finding.

## Contents

- [1. Verdict](#1-verdict)
- [2. Findings](#2-findings)
- [3. Scenario walk](#3-scenario-walk)
- [4. Undisclosed costs](#4-undisclosed-costs)
- [5. Copy / UX honesty](#5-copy--ux-honesty)
- [6. Improved TestFlight checklist](#6-improved-testflight-checklist)
- [7. Guard run](#7-guard-run)

## 1. Verdict

**PASS** — ship the fix as built. Zero BLOCKING findings. The eight-line
change does exactly what the report asked and respects every ruling it
touches (P-1, Fix A, R-5, R-9, B-4, Ruling A). What follows is a set of
NON-BLOCKING residuals, three product COSTs the PRD did not surface to the
operator in plain words (one of which deserves a ruling before the next
build, not this one), and a tightened checklist.

`npm run test:shop-deck`: **151 PASS / 0 FAIL** (k1–k8 all green; see §7).

## 2. Findings

| ID | Severity | Where | Description | What the operator should be told |
|---|---|---|---|---|
| B-1 | **COST** (ruling wanted) | `backend/server.py:12141+76` ("Likes never exclude here"); `ShopOffersBody.tsx:324-327`; prd §6 | A sent offer is suppressed only for **this window instance**. `POST /api/trades/asset-ideas` deliberately excludes dismissed ideas (D-067 cooldown) but **never** liked ones. So: back out, tap "More offers" on the same player again, and the idea you just sent is offered again as if new (within 60 s: guaranteed, warm cache row; later: likely, unless the Elo move re-binned it). The PRD lists this as out of scope, and checklist step 7 even uses it as a test fixture — but it never says to the operator, in product terms, "the app will keep re-offering trades you have already sent". No sender-side receipt exists in the app either (`getLikedTrades` feeds only a badge count — `TabNav.tsx:778`, `api/trades.ts:702-704` "a future inbox screen"), so the re-offer is the only place the user will ever see the sent package again, and it looks like a fresh idea. | "Sending an offer hides it for this visit only. Reopen the window and it can come back; tapping Send again just says 'Already queued'. Do you want sent offers excluded server-side like dismissed ones are (a backend change, D-067-shaped — new item), or is this acceptable for now?" |
| B-2 | NON-BLOCKING | `ShopOffersBody.tsx:725` (closure `index`), `:766-775` (`handleSelectMode`), `:752` (clamp against the **new** mode's list) | D-2 analyses a *swipe* during the round-trip but not a **mode-chip tap**. `handleLike` closes over the old mode's `index` (say 3). If the user taps Send and then switches mode before the server answers, the resolution calls `requestPagerScroll(3)`, the memo recomputes every mode's array (`:517-526`, so `visibleIdeas` is a new reference even though the suppressed key lives in the *other* group), and the effect fronts tile `min(3, newLen-1)` of the **new** mode — the user was on tile 1 of it. Same class as D-2's accepted residuals (a position, never a wrong tile removed), sub-second on a warm server, not fixable without the live ref D-2 rejected. | Accept as residual; add it to D-2's list so the next reader does not rediscover it. If it is ever seen on device it will look like "the pager jumped after I changed mode". |
| B-3 | NON-BLOCKING (pre-existing, made more reachable) | `ShopOffersBody.tsx:705-708` (`if (busyKey) return`), `:999`, `:1055` (`loading={busy}` is per-key) | While tile B's Send is in flight, every *other* tile's Send is silently a no-op — no spinner, no toast, nothing. Not new, but the fix makes "send, auto-advance, send" the natural rhythm, so a fast thumb on a slow server will hit it: the user taps Send on C, nothing happens, taps again, it works. Root cause is a global lock rendered as a per-tile spinner. | Not for this item. If it shows up in feedback ("Send sometimes doesn't respond"), the fix is to disable the pair on every tile while `busyKey` is set (one boolean), not per key. |
| B-4 | NON-BLOCKING (pre-existing copy) | `ShopOffersBody.tsx:941` (`EMPTY_HEAD[mode]`), `:176-190` (`emptyBody`), `:443-448` (`widenEligible` reads the raw server list) | Sending the **only** remaining tile renders "No tier-up offers cleared the bar — Nobody in this league holds a bigger piece that a package around X can reach under the fairness rules." That sentence is false: an offer *did* clear the bar and the user just sent it. The same lie already existed for dismiss-to-empty; the fix makes it the reward for the happiest path (send everything). PRD step 6 institutionalizes this copy as the pass condition. | Accept for this item (the copy is #402's, not #418's). Worth a follow-up ruling: when `groups[mode].length > 0 && visibleIdeas.length === 0` the empty should say "You've acted on every <mode> offer" (dismissed or sent), not that none existed. |
| B-5 | NON-BLOCKING (pre-existing, disclosed as B-4 in #402) | `ShopAssetScreen.tsx:43-54` (one toast slot), `Toast.tsx:76-95` (hold timer re-arms at 1500 ms), `ShopOffersBody.tsx:572-585` | Dismiss A, then Send B within 5 s: the "Queued" toast **replaces** "Dismissed · Undo", the Undo affordance is gone, and A commits silently ~3.5 s later. Correct per the shipped B-4 ruling and per R-7, but from the user's seat: sending B forfeited undoing A with no signal. Before this fix the same replacement happened, so nothing regressed. | Nothing to do now. Checklist step 9 already exercises it; I reworded it so the operator knows the vanished Undo is expected, not a bug. |
| B-6 | NON-BLOCKING (doc drift) | `prd.md` §8.3 step 8; `backend/server.py:13196-13205` (D-170) | Step 8 says server-side refusals "untouchable, not-interested, fairness floor" need a second account. D-170 (2026-08-31) removed all of those; the only surviving server refusal is `not_league_member`. `queueRefusalLine` still carries the dead lines (harmless), but the checklist's explanation is stale. | Read step 8 as: Airplane Mode is the only refusal you can force; the code path is the same for the one server refusal left. |
| B-7 | NON-BLOCKING (doc drift) | `docs/feedback/items/418-shop-send-dismiss/status.md` | Still says "planned · no branch yet" after the build commit. | Update at ship (built → QA'd → shipped, with the sha). |
| B-8 | NOTE (commit hygiene) | `f593020a` touches `.claude/skills/feedback/lessons.md` (+9, two 2026-09-02c *triage* lessons) and `INDEX.md` | The fix commit bundles unrelated worktree state the build-notes §4.4 explicitly said it did not touch. Not wrong content, just not this item's. | Fine to squash-merge as is; the lessons are real. Mention in the PR body so the reviewer isn't surprised. |
| B-9 | NOTE | `api/client.ts:230` (15 s deadline), `:453-456` (POST never retried), `queueCalcTrade.ts:76-78` | Deadline case: the server records the like, the response is lost, the client toasts "Couldn't queue that. Try again." and the tile **stays** (R-4 — correct, the client cannot know). The retap heals it: "Already queued" and the tile leaves (R-1/k5). Also the reason R-1 must include `alreadyQueued`; the rebuttal R-b is right. | None. |
| B-10 | NOTE (verified, not a finding) | `VirtualizedListCellRenderer.js:62` (`PureComponent`, `renderItem` is a prop `:186-189`); `ShopOffersBody.tsx:1060-1064` | "Swipe for the next offer" on the last remaining tile: the hint is gated on `visibleIdeas.length > 1`, and because `renderItem` is an inline closure the cell re-renders on every body render, so the hint disappears the moment a send leaves one tile. Opened node_modules for this per the 2026-08-30 lesson rather than trusting memory. | None. |

## 3. Scenario walk

Notation: `k` = 0-based index of the tapped tile, `N` = tiles in the mode
before the tap. `handleLike` is `ShopOffersBody.tsx:705-732`; the write is
`:720-727`; the reactive scroll effect is `:748-763`; the clamp is `:752`.

| # | Scenario | Expected (PRD) | What the code does | Verdict |
|---|---|---|---|---|
| a | Send on tile 1 of 3 | Tile 2 fronted at slot 1, counter `1 / 2`, chip `· 2` | `requestPagerScroll(0)` `:725` → `setSuppressed` `:726` → memo `:517-526` drops the key from every mode → effect clamps `min(0, 1) = 0`, `scrollToOffset(0)` is a no-op `:755` → former tile 2 sits at offset 0. Counter `:800` = `min(0+1, 2) = 1` → `1 / 2`. Chip `:868` reads `visibleByMode[m].length` = 2. `setSuppressed`, `setToast` (parent) and `setBusyKey(null)` are in one post-await continuation → one batched render, no spinner flash on the departing tile. | PASS |
| b | Send on the last tile (`k = N-1`, N ≥ 2) | Pager lands on the new last tile, counter `N-1 / N-1` | Intermediate render: `index = N-1`, length `N-1` → `shown = min(N, N-1) = N-1` — honest even before the effect. Effect: `clamped = N-2`, scrolls back one page (`animated:false`). iOS content width shrank under the current offset for one frame; identical to today's last-tile dismiss. | PASS |
| c | Send on the only tile | Empty state, no counter, no spinner; chip `· 0`; no auto-widen in Same value | `visibleIdeas.length === 0` `:895` → pager branch unmounts → `listRef.current` null → `?.` `:755` skips. Filtered empty `:896-936` if a selection is settled (with `Clear positions — N at POS`, N from `baselineModeCount` `:500-510`, itself filtered through `suppressed`), else `EMPTY_HEAD[mode]` `:941`. `widenEligible` `:443-448` reads the raw server `lateral.length`, so a send never triggers the widen. **Copy is misleading — see B-4.** | PASS (mechanics) / COPY NOTE |
| d | Send on B while A's "Dismissed · Undo" toast is up | Queue toast replaces Undo toast; A does not come back; no second toast; A commits on its own timer | `handleLike` never touches `pendingDismissRef`, `locallyRemoved`, or `flushPendingDismiss` (k2, k6). `onToast` `:728` → `setToast` `ShopAssetScreen.tsx:64` replaces the descriptor; `Toast.tsx:76-95` deps include `effectiveHoldMs` (5000 → 1500), cleanup clears the old timer, new 1500 ms timer fades it. A's `setTimeout` `:641-644` keeps running → `flushPendingDismiss({expired:true})` `:587-607` → no retract (expired), `commitDismiss(A)` `:543`. `undoToastRef` still holds the old descriptor; a later early flush's retract is the by-reference no-op `ShopAssetScreen.tsx:68`. **Reverse order** (B in flight, swipe, ✕ C): C's dismiss requests `index` and writes `locallyRemoved`; B's resolution then requests B's older `index` — clamped, C's timer/key untouched. Traced with `[A,B,C,D]`, Send B@1, ✕ C@2: after both writes the list is `[A,D]` and the pager fronts D at 1 — the tile the user was already looking at. | PASS (see B-5 for the UX cost) |
| e | Send, swipe, 60 s stale window passes, a refetch lands | Sent tile stays gone (Fix A) | Nothing in the window refetches by itself after `staleTime`; a refetch needs a trigger: foreground (`focusManager` wired, `App.tsx:225`), reconnect (`onlineManager`, `App.tsx:240`), or a selection change (a *different* cache row). Any of them ticks `ideasUpdatedAt` → `:685-688` flushes the pending dismiss and requests index 0 — the pager **rewinds to tile 1** (shipped behavior, not this fix). The sets are never cleared (n2d); `visibleByMode` filters the fresh payload through `suppressed`, so the sent key is dropped whether or not the server re-offers it. Key stability across refetch verified: `assetIdeaKey` `ideaToCard.ts:26-28` is counterparty + give ids + receive ids — no value or timestamp in it. | PASS |
| f | Send with Airplane Mode on | Tile stays, refusal toast, pair re-enabled | `api.post` throws at once (POST is never retried, `client.ts:453-456`, `:505`) → `queueCalcTrade` catch `:76-78` → `queued:false`, toast `Couldn't queue that. Try again.` tone `error` → `ux.toast_v2` is **true** (`features.json:156`) so it holds 5 s. `if (res.queued)` `:720` false → no write; `finally` `:730` releases the lock; the same cell re-renders with `busy=false`. Airplane off → `refetchOnReconnect` may rewind the pager to 1 if the row is stale (as in e). | PASS |
| g | Rapid double-tap on Send | One queue, one removal | First tap: `setBusyKey(key)` `:708`; the discrete press flushes synchronously, so by the second native tap the cell has re-rendered with `loading={busy}` `:1055` → chalkline `Button` sets `disabled={inactive}` (`Button.tsx:50-53`) and the `Pressable` swallows it. Belt-and-braces: `if (busyKey) return` `:707`; and the server is idempotent (`server.py:13285-13291`) — even two round-trips would produce `queued:true` twice and an idempotent `Set.add`. | PASS |
| h | Mode switch right after a send (tier_up → same_value) | Key suppressed in every mode; chip counts right | `visibleByMode` `:517-526` filters **all three** groups through one set, so the key is gone in every mode; chips `:868` and the a11y label `:855` read the same arrays. `handleSelectMode` `:766` flushes the pending dismiss and rewinds to 0 — the sent tile is not in either list. If the switch happens **during** the round-trip: see B-2 (pager jumps to the old index in the new mode; a position, never a wrong tile). | PASS (B-2 residual) |
| i | Background / foreground mid-round-trip | Sent tile gone when the app comes back; nothing double-applied | iOS suspends JS; the native fetch usually completes. On resume the promise continuation runs: `:720-727` writes, toast, unlock. `focusManager` refetches the row only if it is > 60 s stale; whichever lands second wins the pager position (like → `index`, refetch → 0), and the sent key is filtered either way. If the request outlived the 15 s deadline while suspended: B-9 — refusal toast, tile stays, retap says "Already queued" and removes it. If iOS killed the app: new instance, `suppressed` empty, the idea re-offered — B-1. | PASS |

## 4. Undisclosed costs

What the operator loses that the PRD's problem statement did not say in
plain words. B-1 is the one that merits a ruling; the others are notes.

1. **Sent offers are hidden per visit, not remembered** (B-1). The window
   forgets on back-navigation; the server never excludes likes from
   asset-ideas. In practice the operator will see a trade he sent yesterday
   offered again tomorrow, indistinguishable from a new idea, with no
   in-app list of what he has sent. A dismissed idea, by contrast, is
   remembered server-side for the cooldown. Asymmetric and surprising.
2. **The "Already queued" re-✓ receipt is gone from this window.** It was
   the only way to confirm a send after the toast faded (1.5 s). Now the
   tile is gone and the confirmation with it. The only remaining
   confirmation is the re-offer in a new window (cost 1) — which then
   *removes* it again on tap. Harmless, but the operator should know the
   1.5 s toast is now the whole receipt.
3. **Send on B forfeits Undo on A** (B-5). Shipped B-4 semantic, unchanged
   by this fix, but the auto-advance makes ✕-then-✓ a two-second sequence.
4. **Counts drop on a like.** The chip and counter now read "offers still
   undecided", not "offers found". The PRD calls this R-2 and it is the
   right reading, but a user who saw `· 6` at open and `· 3` after three
   sends may wonder where the offers went. No copy anywhere says "3 sent".
5. **The empty state after sending everything says nothing was found**
   (B-4). This is the one that could actually make the operator think the
   feature is broken during checklist step 6.

None of these regress anything; 1 and 5 are candidates for follow-up items.

## 5. Copy / UX honesty

| Surface | Post-fix state | Honest? |
|---|---|---|
| `1 / X` counter `:800`, `:983` | Reads the filtered list; `min(index+1, len)` keeps it honest in the pre-effect render | Yes |
| Mode chip `· N` `:868` and a11y label `:855` | Same arrays | Yes |
| "Clear positions — N at POS" `:922` | `baselineModeCount` filtered through `suppressed` `:507-509` | Yes |
| "The other modes have offers" hint `:929`, `:945` | `visibleByMode[m].length > 0` | Yes |
| "Swipe for the next offer" `:1060-1064` | Hidden when one tile remains (B-10) | Yes |
| Toast copy | Unchanged, `queueCalcTrade.ts` not in the diff (R-5) | Yes |
| Empty-state head/body `:941`, `:176-190` after the last send | "No … offers cleared the bar / Nobody in this league holds …" | **No** — B-4 |
| Header comment `:82-85`, `suppressed` block `:311-327`, `commitDismiss` `:544-545`, guard header `check-shop-deck.js:50-52` | All say two gates; the memory-claim correction (O-2) is present | Yes |
| Guard `(n)` preamble `check-shop-deck.js:1556` "added to only at commit" | A queued like *is* a commit in the sense used; borderline but not false | Acceptable |

## 6. Improved TestFlight checklist

The PRD's 10 steps are good; these changes make each step name the exact
symptom that would mean a regression, state the pre-existing behaviors the
operator will otherwise report as bugs (B-4, B-5, the refetch rewind), and
add one step for cost 1 so the ruling is taken with the behavior in hand.
Must-runs: **2, 2b, 6, 8, 10**. Fences: 3, 4, 5, 7, 9.

1. **Open.** Trades → deck card → give-side **More offers** (or a chooser
   row). Pick a mode whose chip shows **≥ 3**. Write down `1 / N` and `· N`.
   ☐
2. **Send on tile 1.** Tap **Send this offer**. In one motion: toast
   *"Queued for @X — it'll show in their suggestions."*, the tile is gone,
   the tile that was 2nd is on screen **without swiping**, counter `1 / N-1`,
   chip `· N-1`. **Regression signs:** the same tile still on screen after
   the toast (the #418 bug itself); counter or chip unchanged while the
   tile left (R-2/R-5 counter honesty); the pager visibly animating (P-1 —
   the move must be instant, `animated:false`). *(R-1, R-2, R-3)* ☐
2b. **Send on a middle tile.** Swipe to tile 2 (`2 / N-1`, need N-1 ≥ 3),
   Send. The tile that was 3rd is now on screen, counter `2 / N-2`.
   **Regression sign:** the pager snapping back to tile 1 (a rewind means
   the like went through the refetch path or requested index 0). *(R-3)* ☐
3. **It stays gone.** Swipe to the end and back: the sent package (same
   partner, same pieces) never appears. *(R-1)* ☐
4. **Survives a mode round-trip.** Tap another mode chip, then back. Still
   absent; counts equal step 2's. Note: switching modes always lands on
   tile 1 of the mode — that is shipped, not a regression. *(Fix A)* ☐
5. **Survives a refetch.** Toggle a position chip, wait for the sweep, tap
   it again to clear. Still absent. The pager rewinds to tile 1 on every
   refetch — shipped, not a regression. **Regression sign:** the sent tile
   reappearing after the sweep (the suppression set was cleared by a data
   tick — n2d). *(Fix A)* ☐
6. **Last tile → empty state.** Get a mode down to exactly 1 (dismiss the
   rest, let each Undo toast expire), Send it. Expect: toast, then the
   empty state with **no counter row and no spinner**, chip `· 0`. The copy
   will say *"No <mode> offers cleared the bar"* (or *"Nothing at POS"* with
   **Clear positions** if a chip is selected). **That copy is known to be
   misleading here (QA-B B-4) — it is not a regression of this fix.** In
   Same value the empty must **not** swap in a "showing all positions"
   notice. **Regression signs:** a spinner, a `1 / 0` counter, or a blank
   pager. *(R-3)* ☐
7. **Already queued, same visit.** Within **60 s** of step 2, go back and
   reopen the window for the same player. The sent idea **is offered
   again** (expected — see step 10). Tap Send on it: toast *"Already queued
   for @X."* **and** the tile leaves exactly as in step 2. **Regression
   sign:** the tile staying after "Already queued" (k5 — an already-queued
   like must still remove). Outside 60 s the sweep re-runs and the idea
   may be absent or in another mode; that is not a failure, redo inside
   the window. *(R-1)* ☐
8. **Refused → tile stays.** Airplane Mode on, Send on any tile. Expect
   toast *"Couldn't queue that. Try again."* (red rail, stays ~5 s), the
   **same tile still on screen**, counter unchanged, both ✕ and Send
   enabled again. If the spinner runs up to 15 s before the toast, that is
   the client deadline — the toast and the re-enabled pair are the pass.
   Airplane Mode off; the pager may rewind to tile 1 on reconnect
   (shipped). **Regression sign:** the tile leaving on a refusal (k4 — an
   optimistic or inverted write). This is the only refusal you can force:
   since D-170 the server's sole refusal is a non-member counterparty.
   *(R-4)* ☐
9. **Pending dismiss + Send on the next tile.** Dismiss A (*Dismissed ·
   Undo* shows; B is fronted). Within 5 s, Send on B. Expect: the queue
   toast **replaces** the Undo toast (the Undo button is gone for good —
   this is the shipped B-4 rule, not a regression), B leaves, A does
   **not** come back. Wait 6 s: nothing reappears, no second toast.
   **Regression signs:** A returning (the like restored or cleared the
   pending set); a second "Dismissed" toast (the like re-issued it); the
   Undo toast staying up with a dead button. *(R-7 / D-1)* ☐
10. **Cross-visit re-offer — take the ruling with the behavior in hand.**
   Send an offer, back out, wait > 60 s, reopen the window for the same
   player, look for the package in every mode. If it is there it looks like
   a new idea, and tapping Send says "Already queued". **This is expected
   today** (the server excludes dismissed ideas from the shop but never
   sent ones — QA-B B-1). Decide: acceptable for now, or file the
   server-side exclusion as a new item. ☐

## 7. Guard run

`cd mobile && npm run test:shop-deck` on `f593020a` with the worktree's own
`node_modules`: **151 PASS / 0 FAIL**, exit 0, "All shop-deck assertions
passed." Section `(k)` k1–k8 all green. Sabotage pairs were not re-run here
(agent A's remit); the builder's table in build-notes §2 lists them.
