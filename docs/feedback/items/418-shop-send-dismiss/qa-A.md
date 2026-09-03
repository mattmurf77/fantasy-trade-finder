# FB-418 — QA report A (independent static QA)

> QA agent A of two. Contract: [`prd.md`](prd.md) (R-1…R-9, D-1…D-3, k1–k8,
> §8). Also read: [`reconciliation-log.md`](reconciliation-log.md),
> [`build-notes.md`](build-notes.md) (treated as claims, re-verified below).
> Fix commit `f593020a` on `claude/new-user-feedback-06dabd`, parent
> `c7e75666` = `origin/main`. Every `file:line` below is the **post-fix** file
> unless marked otherwise. Date: 2026-09-03.

## Verdict: **PASS**

The diff is exactly the two files §9 names, every changed line traces to a
requirement, every requirement has a line, all three CI gates are green, the
six named sabotages each redden their target assertion and go green on
restore, the §8.2 code-walk holds for all five cases, and D-1 / D-2 are
verified against the code (and, for D-2, against `node_modules`). What I found
is all about the *fence*, not the fix: four plausible wrong implementations
that k1–k8 accept (F-1), and a few doc/comment notes.

## Contents

- [Findings](#findings)
- [1. Diff ↔ PRD traceability](#1-diff--prd-traceability)
- [2. Command results (session tree, read-only)](#2-command-results-session-tree-read-only)
- [3. Sabotage re-proof (own worktree)](#3-sabotage-re-proof-own-worktree)
- [4. Code-walk proof (§8.2, post-fix lines)](#4-code-walk-proof-82-post-fix-lines)
- [5. D-1 and D-2 verification](#5-d-1-and-d-2-verification)
- [6. Fixture honesty](#6-fixture-honesty)
- [7. Regression hunt](#7-regression-hunt)
- [8. Operator checklist delta](#8-operator-checklist-delta)

## Findings

| id | severity | file:line | description | repro / proof |
|---|---|---|---|---|
| F-1 | NON-BLOCKING | `mobile/tests/check-shop-deck.js:848-966` (section k) | **Guard k1–k8 accepts four plausible wrong implementations.** k1/k3/k4/k7 pin *that* `setSuppressed` is called, *where*, and *in what order* — never *what it writes*; k3 pins `requestPagerScroll`'s position, never its argument. So each of these passes 151/0: **X-1** `setSuppressed(new Set([key]))` (replaces the set — every earlier committed ✕ and sent offer in the session resurrects on the next render); **X-3** `setSuppressed((s) => new Set(s))` (no-op write — the bug is back, guard green); **X-2** `requestPagerScroll(0)` (pager rewinds to tile 1 on every send); **X-4** `requestPagerScroll(index + 1)` (skips a tile). The shipped code is correct on read (`ShopOffersBody.tsx:725-726`), so this is a fence weakness, not a defect. X-2/X-3/X-4 are caught at runtime by checklist steps 2/2b; X-1 is caught by **no** current checklist step — see §8 for the added step and a suggested `k9`. | §3 table, rows X-1…X-4: guard exit 0, 151 PASS, RED=[] under each |
| F-2 | NOTE | `check-shop-deck.js:947-960` (k8) | k8 counts any three `#418` strings in the file, one inside `commitDismiss`. The body carries five (`:82-85` header, `:311-314` and `:324-327` in the `suppressed` block, `:544-545` commit note, `:721` the fix's own comment), so the header clause **and** one `suppressed`-block sentence can both be deleted and k8 stays green (5−2 = 3 ≥ 3). The PRD's wording ("the three body sites") is stronger than what k8 checks. Tripwire by design (PRD says so); recording the gap. | count `#418` in post-fix body = 5 |
| F-3 | NOTE | `ShopOffersBody.tsx:725`, `:766-775`, `:748-764` | D-2 lists two mid-round-trip residuals (swipe, refetch) but not a **mode switch**. `handleSelectMode` during the sub-second await requests 0 and sets the new mode; when the like resolves, `setSuppressed` recomputes `visibleByMode` (new arrays for every mode, `:517-526`), the effect fires on the new mode's list and consumes the like's `requestPagerScroll(index_old)` → the new mode's pager jumps to `clamp(index_old)`. Position only, never a wrong tile; same class as D-2's accepted residuals. One clause in D-2 would make the decision complete. | code read; not manually reproducible with confidence (sub-second) |
| F-4 | NOTE | `.claude/skills/feedback/lessons.md:383-391`; `docs/feedback/items/INDEX.md:275`; `status.md:3` | The commit sweeps in two `2026-09-02c [triage]` lessons about #413/#417 and the `secrets.local.env` symlink — not traceable to any #418 requirement (build-notes §4.4 says they were pre-existing dirty state; they got committed anyway). And both the INDEX row ("planned … docs only, no branch yet") and `status.md` ("**Status:** planned · no branch yet") are stale now that the fix is committed — should read built / in QA before ship. | `git diff c7e75666 f593020a -- .claude docs/feedback/items/INDEX.md` |
| F-5 | NOTE | `build-notes.md` §2, row S-7b | Build-notes reports S-7b reddening **k7 only**. My S-7b (both statements moved above the `await`, the `if (res.queued)` branch left holding only the request) reddens **k4 + k7** — because once the write precedes `const res = await …` it cannot sit under an `if (res.queued)`, so k4 must go red too. The builder's exact S-7b edit is not recorded; a "k7 only" outcome implies a shape I could not reconstruct. Not a defect in the guard or the fix; the sabotage log should state the edit applied. | §3 row S-7b |
| F-6 | NOTE | guardrail 9 (PRD §7) | I symlinked the session tree's `mobile/node_modules` into my worktree per the QA task instruction rather than running `npm ci` (guardrail 9 is a build-agent rule). The guard needs only `typescript`; no result depends on it. Disclosed. | — |

No BLOCKING findings.

## 1. Diff ↔ PRD traceability

`git show f593020a --stat`: 10 files. Code: `mobile/src/components/ShopOffersBody.tsx` (+27/−6 lines incl. context), `mobile/tests/check-shop-deck.js` (+123). Docs: six files under `docs/feedback/items/418-shop-send-dismiss/`, `INDEX.md`, `.claude/skills/feedback/lessons.md` (F-4). **No** `queueCalcTrade.ts`, `ShopAssetScreen.tsx`, `TradesScreen.tsx`, `backend/**`, `config/features.json`, `mobile/package.json` (R-5, D-3, §9).

Every changed mobile line → requirement:

| Post-fix lines | Change | Req |
|---|---|---|
| `ShopOffersBody.tsx:82-85` | header ✓-like bullet: "A QUEUED like (incl. "already queued") is the SECOND gate … (#418)" | R-9 |
| `:311-314` | `suppressed` block: "TWO gates — a held dismiss that COMMITS, or a ✓ like the server QUEUED (#418, `handleLike`)" | R-9 |
| `:324-327` | `suppressed` block: memory correction — "For a QUEUED like (#418) there is NO server-side memory … the next fetch WILL re-offer the idea and this set is its only filter" | R-9 / O-2 |
| `:544-545` | `commitDismiss`: "one of TWO gates … (the other is a queued ✓ like in `handleLike`, #418)" | R-9 |
| `:720-727` | `if (res.queued) { /* #418 comment */ requestPagerScroll(index); setSuppressed((s) => new Set(s).add(key)); }` inside the `try`, after the `await`, before `onToast` | R-1, R-3, R-4, R-8, D-1, D-2 |
| `check-shop-deck.js:50-52` | header bullet: "has exactly two gates — a committed dismiss and a queued ✓ like, #418" | R-9 / O-10 |
| `check-shop-deck.js:848-966` | section (k): k1–k8 exactly per §8.1 shapes; one block-local `inside()` helper | D-3, §8.1 |

Every requirement → line: R-1 `:720,:726`; R-2 no line by design (pass criterion; counts at `:972`, `:852`, `:866`, `:500-510`, `:921-923` untouched — verified against the parent); R-3 `:725`; R-4 `:720` gate; R-5 diff name-list; R-6 no `track(` in `handleLike` (`:705-732` — none); R-7/D-1 no `flushPendingDismiss` in `handleLike`; R-8 `:707-708`, `:729-731` unchanged; R-9 the four comment sites + guard header. **No untraceable mobile line.** Untraceable non-mobile lines: F-4.

## 2. Command results (session tree, read-only)

Run from `…/happy-golick-345cf1/mobile` at `HEAD` = `059a190b` (a #417 docs-only commit on top of `f593020a`; `mobile/` identical to `f593020a`).

| Command | Result |
|---|---|
| `npx tsc --noEmit` | exit 0 |
| `npm run test:shop-deck` | **151 PASS / 0 FAIL**, "All shop-deck assertions passed.", exit 0 (143 + 8 new) |
| `bash scripts/testid-lint.sh` | "testid-lint OK", exit 0 |
| `git grep -n "invalidateQueries\|refetchQueries\|setQueryData" f593020a -- mobile/src/api/trades.ts mobile/src/utils/queueCalcTrade.ts mobile/src/components/ShopOffersBody.tsx` | no matches (exit 1) — D-1 premise holds |

## 3. Sabotage re-proof (own worktree)

Worktree `<scratchpad>/wt-qa418-a`, branch `qa418-a` at `f593020a`, `node_modules` symlinked (F-6). Method: a Python script applied each sabotage as an exact-string edit to `ShopOffersBody.tsx`, ran `node tests/check-shop-deck.js`, captured every `FAIL <id>:` line, restored with `git checkout -- <file>`, re-ran to confirm green; final file byte-equal to the original. Baseline: 151 PASS / 0 FAIL.

| Sabotage | Edit applied | RED | exit / PASS | Restored |
|---|---|---|---|---|
| S-1 | delete `setSuppressed((s) => new Set(s).add(key));` | **k1**, k3, k4, k7 | 1 / 147 | 151/0 |
| S-2 | `setLocallyRemoved((s) => new Set(s).add(key));` in its place | **k1, k2**, k3, k4, k7 | 1 / 146 | 151/0 |
| S-4b | `if (res.queued) { requestPagerScroll(index); } else { setSuppressed(…); }` | **k4** | 1 / 150 | 151/0 |
| S-5 | `if (res.queued && !res.alreadyQueued) {` | k4, **k5** | 1 / 149 | 151/0 |
| S-6 | `flushPendingDismiss();` inserted before `const res = await queueCalcTrade(` | **k6** | 1 / 150 | 151/0 |
| S-7b | `requestPagerScroll(index); setSuppressed(…);` moved above the `await`; `if (res.queued)` left with the request only | k4, **k7** | 1 / 149 | 151/0 (F-5) |
| **X-1** (own) | `setSuppressed(new Set([key]));` — replaces the set | *none* | **0 / 151** | 151/0 |
| **X-2** (own) | `requestPagerScroll(0);` — rewinds pager | *none* | **0 / 151** | 151/0 |
| **X-3** (own) | `setSuppressed((s) => new Set(s));` — no-op write | *none* | **0 / 151** | 151/0 |
| **X-4** (own) | `requestPagerScroll(index + 1);` — skips a tile | *none* | **0 / 151** | 151/0 |

Named targets all red under their sabotage; no assertion outside section (k) went red in any run (the fence `e`, `h5d`, `i1`/`i3`, `i5`/`i6`, `n2b`–`n2f`, `n3a`/`n3b` stayed green throughout). Collateral reds match the build-notes' reasoning (k3/k4/k7 are properties *of* the write; k4 forbids `!`).

**Suggested `k9` (not applied — QA does not edit source):** the first `setSuppressed` call in `handleLike` has exactly one argument that is an arrow function (`ts.isArrowFunction`) whose body text references `key` and contains `.add(` — fails X-1 (argument is a `NewExpression`) and X-3 (no `.add`). **Suggested `k3b`:** `txt(sf, reqCall.arguments[0])` is `index` or `at` — fails X-2 and X-4. Together they close every hole I found.

## 4. Code-walk proof (§8.2, post-fix lines)

1. **Tap** — `Button testID="shop.like-btn"` `:1049-1057`, `onPress={() => handleLike(item)}` `:1056`, inside `renderItem` `:997`.
2. **Lock** — `if (busyKey) return;` `:707`; `setBusyKey(key)` `:708`; `busy = busyKey === key` `:999` → `loading={busy}` `:1055`, `disabled={busy}` on ✕ `:1037`.
3. **Queue** — `await queueCalcTrade({…, screen: 'ShopAsset'})` `:710-719` → `queueCalcTrade.ts:70-75` → `queueTradeForOpponent` `api/trades.ts:601-620` → `api.post('/api/trades/queue', …)`; `calc_trade_queued` `queueCalcTrade.ts:82-86`.
4. **Branch** — `if (res.queued)` `:720`. `queueCalcTrade.ts:87-101` returns `queued: true` for both a first queue and `already_queued` (with `alreadyQueued`), `:103-110` returns `queued: false` for a server refusal or the `catch` at `:76-78`.
5. **Request, then write** — `requestPagerScroll(index)` `:725` → `pendingScrollRef.current = index` `:745-747`; `setSuppressed((s) => new Set(s).add(key))` `:726` — a copy-and-add, the `commitDismiss` shape at `:549`.
6. **Recompute** — `visibleByMode` memo `:517-526`, deps `[groups, locallyRemoved, suppressed]`, filter `:520-523`; `visibleIdeas = visibleByMode[mode]` `:527` (new reference). Derived: counter `:972` (`shown` `:800`), chip counts `:852`/`:866`, `baselineModeCount` `:500-510`, Clear-positions label `:921-923`, other-modes hint `:929`/`:945`.
7. **Effect clamp + scroll** — `:748-764`, deps `[visibleIdeas, pagerW, ideasUpdatedAt]`; `want = index` `:749`; `clamped = Math.min(want, Math.max(0, visibleIdeas.length - 1))` `:752`; `setIndex(clamped)` `:753`; `listRef.current?.scrollToOffset({offset: clamped * pagerW, animated:false})` `:754-759`.
8. **Toast + unlock** — `onToast(res.toast)` `:728` → `ShopAssetScreen.tsx:64` `setToast(t)`; `finally { setBusyKey(null) }` `:729-731`.

Cases (N tiles in the mode, like on 0-based tile k):

- **k = 0, N ≥ 2** — list → N−1; `clamped = min(0, N−2) = 0`; scroll to offset 0 (already there); former tile 1 now at index 0; counter `1 / N−1`. (Checklist 2.)
- **0 < k < N−1** — `clamped = min(k, N−2) = k`; offset `k·pagerW` equals the current `contentOffset` so no visible move; the former k+1 sits at k; counter `k+1 / N−1`. (Checklist 2b.)
- **k = N−1, N ≥ 2** — `clamped = min(N−1, N−2) = N−2`; scroll to `(N−2)·pagerW` = the new last tile; counter `N−1 / N−1`.
- **N = 1** — the render that commits `suppressed` has `visibleIdeas.length === 0` → `:895` branch: `settledSelection.length > 0` → filtered empty `:904-934` (`shop.empty`, `shop.clear-positions` `:918-928`), else per-mode empty `:940-950` (`EMPTY_HEAD[mode]`). The FlatList (`:979`) unmounts in that commit; React nulls `listRef.current` in the commit phase, before passive effects, so the effect's `?.` at `:755` skips the scroll; `setIndex(0)` still runs (`clamped = min(0, max(0, −1)) = 0`). `widenEligible` `:443-448` reads `ideasQuery.data?.groups.lateral.length` — the server's raw group, not the filtered list — so a like that empties Same value does not auto-widen (R-3). Chip reads `· 0` `:866`.
- **Refusal** — `res.queued === false` → `:720` skipped; no set written; `visibleByMode` deps unchanged → memo not recomputed → `visibleIdeas` same reference → the effect does not run; `pendingScrollRef` untouched (null); refusal toast `:728`; `busyKey` released `:730`. Tile still at `index`, both buttons re-enabled (`busy` false on the next render).

## 5. D-1 and D-2 verification

**D-1 (no flush, no invalidation).** `handleLike` `:705-732` references neither `flushPendingDismiss` nor `flushPendingDismissRef` (k6 green; read). The grep in §2 is empty; `queueTradeForOpponent` `api/trades.ts:601-620` is a bare `api.post` with no query-client access. `ideasUpdatedAt` `:681-684` derives only from `ideasQuery.dataUpdatedAt` / `widenedQuery.dataUpdatedAt`, so a like cannot enter the flush-and-rewind effect `:685-688`. The pending dismiss's `pendingDismissRef` `:530-535` and its timer `:644-647` are untouched by the like path. Toast replacement: `ShopAssetScreen.tsx:47-54` is one slot; `Toast.tsx:76-95` re-arms its hold timer on `effectiveHoldMs` change; `undoToastRef` `:540` stays set, so a later early flush's `onToastRetract` hits the `cur === t ? null : cur` no-op at `ShopAssetScreen.tsx:68`. R-7 holds.

**D-2 (render-time index, no live ref).** `index` is `useState` `:303`; `handleLike` is re-declared each render and closes over that render's binding — a `const`, so identical before and after the `await`. The cell's `onPress` is refreshed because `renderItem` `:997` is an inline arrow (new identity per parent render) passed as a prop to `CellRenderer`, which is a `React.PureComponent` (`node_modules/react-native/node_modules/@react-native/virtualized-lists/Lists/VirtualizedListCellRenderer.js:62`; prop plumbing `VirtualizedList.js:825`, RN 0.81.5) — a changed `renderItem` prop re-renders every mounted cell. `onMomentumScrollEnd` `:992-996` calls `setIndex` when a page settles, so a tap on a settled page sees the current index. No ref is read after the await (`:720-727`). Residuals: the two D-2 names, plus F-3.

## 6. Fixture honesty

The guard parses the **production** file (`parse(BODY_REL)` → `mobile/src/components/ShopOffersBody.tsx`), not a fixture; there is no synthetic shape. Vacuity check per assertion: k1, k2, k5, k6 are guarded by `!!fnLike &&` so an absent `handleLike` fails rather than passes; k3 requires both identifier lists non-empty (O-4 closure verified — S-1 reddened k3); k4 requires `supCall`, `gate`, `inside(gate, fnLike)`, and `inside(supCall, gate.thenStatement)`; k7 requires `tryStmt`, `finallyBlock`, `supCall`, `awaitExpr`. k2/k5/k6 are negative assertions and are green on a file with no fix at all — intended, k1 covers presence. The weak spots are the four holes in F-1 and the count-not-site tripwire in F-2. The "already queued ⇒ queued" premise k5 leans on is real production behaviour (`queueCalcTrade.ts:87-101`), not a fixture assumption.

## 7. Regression hunt

Read the whole post-fix `ShopOffersBody.tsx` (1,324 lines) once more against the fix:

- **`commitDismiss` `:542-570`** — only the comment changed. The one legal subtraction `:562-569` deletes the *dismissed* key on POST failure; it cannot collide with a liked key because a liked tile is out of the pager (cannot be ✕'d) and a pending-dismissed tile is out of the pager (cannot be ✓'d). Groups are read per mode from one payload; a key suppressed in one mode is filtered from all `:519-523`.
- **`undoDismiss` `:599-621`** — untouched; writes only `locallyRemoved`. After a like on B replaces the Undo toast, A's Undo is unreachable and A commits on expiry (R-7, shipped semantic).
- **`ideasUpdatedAt` rewind `:681-688`** — a like never ticks it (§5). A refetch landing mid-round-trip rewinds to 0 then the like's resolution jumps to `index` — D-2's stated residual.
- **`handleSelectMode` `:766-775`** — F-3 residual only; `track('shop_mode_selected', {n_ideas: visibleByMode[m].length})` now correctly excludes sent offers.
- **`busy` per-key lock** — `if (busyKey) return` `:707` swallows a second tile's ✓ while one is in flight (pre-existing, unchanged, R-8); ✕ on another tile is *not* gated by `busyKey` (only `disabled={busy}` per key `:1037`), which is what makes R-7's reverse ordering reachable — bounded by the clamp as the PRD says.
- **Empty states `:895-951`** — reached by the N = 1 case (§4); no counter row, no spinner (`isLoading` false), `shop.empty` in both arms.
- **Widen probe `:438-461`** — `widenEligible` is server-raw; a like cannot enable it. If the widened row *is* showing (`widenShowing`), the liked lateral key is filtered from `rendered.groups.lateral` through the same `visibleByMode` `:517-526` — no bypass.
- **Unmount during the round-trip** — the unmount flush `:661` runs; on resolution `requestPagerScroll` writes a ref (harmless), `setSuppressed` on an unmounted component is a no-op in React 18, `onToast` → `setToast` on the popped screen — pre-existing behaviour of the like path, unchanged.
- **Counter between the write and the effect** — one render where `index` may exceed `visibleIdeas.length − 1` (last-tile case); `shown = Math.min(index + 1, visibleIdeas.length)` `:800` keeps the counter honest, identical to the dismiss path today.

Nothing the fix could break was found broken.

## 8. Operator checklist delta

Hand the PRD §8.3 checklist as written (steps 1–9 all still valid, 2/2b/6/8 must-run), **plus one step** that is the only runtime fence for F-1's X-1 hole:

10. **Earlier decisions survive a send.** In a mode with ≥ 3 offers: ✕ tile A and let the Undo toast expire (5 s), so A is a *committed* dismiss. Then tap **Send** on the fronted tile B → B leaves. Now toggle a position chip, wait for the sweep, and clear it → **neither A nor B** is back; the chip count equals the step-1 count minus 2. *(Fix A — the like must ADD to the suppression set, never replace it; the structural guard cannot see the difference.)* ☐

Everything else in the PRD's table (§8.4) maps as stated; F-1's X-2/X-3/X-4 are already caught by steps 2 and 2b.
