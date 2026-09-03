# FB-418 — build notes (Phase 2 evidence record)

> Build agent's record for the fix specified in [`prd.md`](prd.md) /
> [`plan.md`](plan.md) / [`reconciliation-log.md`](reconciliation-log.md).
> Worktree `happy-golick-345cf1`, base `origin/main` @ `c7e75666`, 2026-09-03.
> Nothing committed — changes left in the working tree for QA.

## Contents

- [1. What changed](#1-what-changed)
- [2. Sabotage proof (k1–k8)](#2-sabotage-proof-k1k8)
- [3. Command results](#3-command-results)
- [4. Deviations and observations](#4-deviations-and-observations)

## 1. What changed

`git diff --stat -- mobile`:

```
 mobile/src/components/ShopOffersBody.tsx |  27 +++++--
 mobile/tests/check-shop-deck.js          | 123 ++++++++++++++++++++++++++++++-
 2 files changed, 144 insertions(+), 6 deletions(-)
```

`git diff --name-only` contains no `queueCalcTrade.ts`, no `ShopAssetScreen.tsx`,
no `TradesScreen.tsx`, nothing under `backend/`, no `config/features.json` (R-5, §9).
No `mobile/package.json` change (D-3).

### `mobile/src/components/ShopOffersBody.tsx` (line numbers are post-change)

| Lines | Change | Requirement |
|---|---|---|
| `:82-85` | Header "✓ like" bullet gains the second-gate clause, tagged `#418` | R-9 |
| `:311-314` | `suppressed` block: "Keys enter this set only when a held dismiss COMMITS" → "through TWO gates — a held dismiss that COMMITS, or a ✓ like the server QUEUED (#418, `handleLike`)" | R-9 |
| `:324-327` | `suppressed` block: one sentence correcting the memory claim — for a queued like there is no server-side memory, the next fetch will re-offer the idea, and this set is its only filter for the session | R-9 / O-2 |
| `:544-545` | `commitDismiss` note: "the ONE gate" → "one of TWO gates (the other is a queued ✓ like in `handleLike`, #418)" | R-9 |
| `:720-727` | **The fix.** Inside the `try`, after the `await`: `if (res.queued) { requestPagerScroll(index); setSuppressed((s) => new Set(s).add(key)); }` with a four-line comment. `onToast(res.toast)` (`:728`) and `finally { setBusyKey(null) }` (`:729-731`) unchanged | R-1, R-3, R-4, R-8; D-1, D-2 |

Nothing else in the file was touched: no count, no effect, no empty state, no
`track(` call (R-2, R-6), no `flushPendingDismiss` (D-1), no live-index ref (D-2).
The request index is the render-time `index` closure constant (D-2 — the
optional `const at = index` capture was not added; the guard accepts either).

### `mobile/tests/check-shop-deck.js`

| Lines | Change |
|---|---|
| `:50-52` | Header bullet: "the suppression set is commit-only" → "has exactly two gates — a committed dismiss and a queued ✓ like, #418 — and is never cleared by data" (O-10) |
| `:848-966` | New section `(k)`, inserted after `(i)` and before `(j)`: assertions `k1`–`k8` exactly as specced in prd §8.1, using the file's own `functionNamed` / `referencesIdentifier` / `findAll` / `nearestAncestor` / `txt` helpers and the `assert(cond, name, detail)` form. One block-local `inside(n, root)` range helper (the same inline `getStart/getEnd` idiom the file uses everywhere, named once because eight assertions use it — the `(n)` section's `labelFor` / `literalCount` precedent) |

Per-assertion shape (all on `functionNamed(sf, 'handleLike')`):

- **k1** references `setSuppressed`.
- **k2** references neither `setLocallyRemoved` nor `locallyRemoved`.
- **k3** `findAll` of both identifiers restricted to the function range; `reqIds.length > 0 && supIds.length > 0 && reqIds[0].getStart() < supIds[0].getStart()` — a missing identifier on either side fails, never vacuously passes (O-4).
- **k4** the `setSuppressed` call's nearest ancestor `IfStatement` exists, lies inside the function, its `expression` references `queued`, its condition text contains no `!`, and the call lies inside `thenStatement`'s range (O-4's inverted-branch closure).
- **k5** does not reference `alreadyQueued`.
- **k6** references neither `flushPendingDismiss` nor `flushPendingDismissRef`.
- **k7** the function's `TryStatement` has a `finallyBlock` referencing `setBusyKey`; the `setSuppressed` call is inside `tryBlock` and starts after the first `AwaitExpression`.
- **k8** `sf.text` contains `#418` at ≥ 3 offsets and at least one lies within `commitDismiss`'s `[getStart, getEnd]` range. (Textual tripwire by design.)

## 2. Sabotage proof (k1–k8)

Method: the fixed body was snapshotted (sha1 `be8f41cd…`); a script applied each
named sabotage as an exact-string edit, ran `node tests/check-shop-deck.js`,
recorded every `FAIL` id, restored the snapshot, and re-ran to confirm green.
The final file hash equals the snapshot hash; `git diff` afterwards shows only
the intended fix (section 1). Baseline before any sabotage: 151 PASS / 0 FAIL.

| Sabotage (prd §8.1) | Named target | RED assertions observed | Exit | PASS count | Restored → green |
|---|---|---|---|---|---|
| S-1 delete the `setSuppressed(...)` statement | k1 | **k1**, k3, k4, k7 | 1 | 147 | yes |
| S-2 write `setLocallyRemoved` instead of `setSuppressed` | k2 (+k1) | **k1, k2**, k3, k4, k7 | 1 | 146 | yes |
| S-3a swap the two statements (write before request) | k3 | **k3** | 1 | 150 | yes |
| S-3b delete the `requestPagerScroll` call | k3 | **k3** | 1 | 150 | yes |
| S-4a drop the `if` (suppression unconditional) | k4 | **k4** | 1 | 150 | yes |
| S-4b move the write into an `else` | k4 | **k4** | 1 | 150 | yes |
| S-5 `if (res.queued && !res.alreadyQueued)` | k5 | k4, **k5** | 1 | 149 | yes |
| S-6 insert `flushPendingDismiss();` before the queue call | k6 | **k6** | 1 | 150 | yes |
| S-7a move `setBusyKey(null)` out of `finally` into the `try` | k7 | **k7** | 1 | 150 | yes |
| S-7b move the suppression write above the `await` | k7 | **k7** | 1 | 150 | yes |
| S-8 delete the `commitDismiss` `#418` clause | k8 | **k8** | 1 | 150 | yes |

Every named target went red under its sabotage; no assertion outside section
`(k)` was collateral in any run (the existing fence — `e`, `h5d`, `i1`/`i3`,
`i5`/`i6`, `n2b`–`n2f`, `n3a`/`n3b` — stayed green throughout). The extra reds
are by construction, not noise:

- **S-1 / S-2 also red k3, k4, k7** — all three pin properties *of the
  `setSuppressed` write* (its order, its gate, its position in the `try`), and
  O-4 required k3 to fail rather than pass vacuously when the identifier is
  absent. With the write gone or renamed there is nothing for them to certify.
- **S-5 also red k4** — the prd's k4 forbids any `!` in the gate condition
  (the inverted-branch closure), and `!res.alreadyQueued` is exactly that.

### 2.1 Phase 4 additions — k3b, k9, k8 tightened (2026-09-03)

QA-A F-1 showed k1–k8 accept four wrong implementations (X-1…X-4) and F-2
showed k8 was a count (≥ 3 anywhere) rather than three named sites. Resolved
in `check-shop-deck.js` section `(k)`, no body change:

- **k9** — the `setSuppressed` call's single argument is an arrow function
  whose body references `key` and contains `.add(` (a copy-and-add updater;
  `new Set([key])` and `(s) => new Set(s)` both fail).
- **k3b** — the `requestPagerScroll` call inside the queued branch
  (`gate.thenStatement`, so the same call k3 orders and k4 gates) has exactly
  one argument whose text is `index`. Placed after k4 because it reads k4's
  `gate`.
- **k8** — now requires `#418` inside three **named** ranges: the header's
  "✓ like" bullet (the `✓ like` → `✕ dismiss` slice of the `UNDO_HOLD_MS`
  statement's leading trivia), the `suppressed` declaration's comment block
  (leading trivia of its `useState` statement), and `commitDismiss`'s text.
  The fix's own `#418` comment in `handleLike` no longer counts toward
  anything. Detail names the missing site(s).

Same method as §2: snapshot sha1 `be8f41cd…` (equal to the build snapshot),
exact-string sabotage on `ShopOffersBody.tsx`, run, restore, re-run; final
hash equals the snapshot. Baseline: **153 PASS / 0 FAIL** (151 + k3b + k9).

| Sabotage | Named target | RED assertions observed | Exit | PASS count | Restored → green |
|---|---|---|---|---|---|
| X-1 `setSuppressed(new Set([key]))` — replaces the set | k9 | **k9** | 1 | 152 | yes (153) |
| X-3 `setSuppressed((s) => new Set(s))` — no-op write | k9 | **k9** | 1 | 152 | yes (153) |
| X-2 `requestPagerScroll(0)` — rewinds the pager | k3b | **k3b** | 1 | 152 | yes (153) |
| X-4 `requestPagerScroll(index + 1)` — skips a tile | k3b | **k3b** | 1 | 152 | yes (153) |
| S-8h delete the header ✓-like bullet's `#418` clause **only** (old k8 stayed green here: 5 − 1 ≥ 3) | k8 | **k8** | 1 | 152 | yes (153) |
| S-8s delete both `suppressed`-block `#418` tags only (extra) | k8 | **k8** | 1 | 152 | yes (153) |
| S-8 delete the `commitDismiss` clause only (re-proof) | k8 | **k8** | 1 | 152 | yes (153) |

No collateral reds in any run; k1–k7 and the existing fence stayed green
throughout. Post-change gates (from `mobile/`): `npx tsc --noEmit` exit 0 ·
`npm run test:shop-deck` 153 PASS / 0 FAIL · `bash scripts/testid-lint.sh`
"testid-lint OK".

## 3. Command results

Run from `mobile/` after `npm ci` in this worktree (guardrail 9 — no symlink to
the main checkout's `node_modules`).

| Command | Result |
|---|---|
| `npm run test:shop-deck` (baseline, before any edit) | 143 PASS / 0 FAIL, exit 0 |
| `npm run test:shop-deck` (after fix + section `(k)`) | **151 PASS / 0 FAIL**, exit 0 — "All shop-deck assertions passed." |
| `npx tsc --noEmit` (baseline) | exit 0 |
| `npx tsc --noEmit` (after) | **exit 0** |
| `bash mobile/scripts/testid-lint.sh` (from repo root) | **exit 0** — "testid-lint OK" (no testID changed; run because it is a CI gate) |
| `git diff --name-only \| grep queueCalcTrade` | 0 matches (R-5) |

`mobile/package.json` has no bundled `test` / `typecheck` / `check` script — only
the per-guard `test:*` entries — so no aggregate suite was available to run;
`test:any-partner` was not run (not required by the task).

## 4. Deviations and observations

**Deviations from the PRD: none.** Every requirement R-1…R-9, decision D-1…D-3,
and reconciliation ruling O-1…O-11 was implemented as written.

Observations for QA, none of them changes:

1. The `handleLike` section banner `// ── Like: the calculator's ✓, verbatim (ruling A)` (`:704`) was left untouched — R-9 names exactly three body sites and says "no other comment is touched". Its "verbatim" claim still describes the queue call itself (which is unchanged); the new post-resolution branch is documented on the branch.
2. The guard's `(n)` section preamble (`check-shop-deck.js:1434-1436`, "added to only at commit") stays true — a queued like is a commit — and O-10 named only the `:50-51` bullet, so it was not edited. `n2b`'s name ("commitDismiss is the gate…") still asserts what it asserts and is green.
3. The body now carries `#418` at five sites (header, `suppressed` block ×2, `commitDismiss`, and the fix's own comment in `handleLike`); k8's floor is three, one inside `commitDismiss`, so the fix comment is not load-bearing for the tripwire.
4. Pre-existing dirty state in this worktree — `.claude/skills/feedback/lessons.md`, `docs/feedback/items/INDEX.md` (both modified) and the untracked `docs/feedback/items/417-pushed-deck-second-search/` — was present before this build started and was not touched, per the task's file-ownership rule.
