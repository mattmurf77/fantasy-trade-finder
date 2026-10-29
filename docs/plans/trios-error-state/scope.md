# Feature Scope — B6: Trios error state

**Date:** 2026-10-27 (revised 2026-10-28 for P2-1)
**Entry point:** direct ask (B6 for the 11-06 binary, due 11-03; found in rankings-pm's review on 2026-10-27)
**Builder:** `eng-backend` worker for rankings-eng, branch `fix/trios-error-state` (base `origin/main` `b5526d9e`)
**Operator sign-off on waivers:** pending. The waivers below go to the operator through rankings-eng.

**The bug.** `mobile/src/screens/RankScreen.tsx` renders the Trios card area as one ternary chain. It tested the skeleton condition `trioQuery.isLoading || !trio` (on main `:602`) **before** `trioQuery.isError` (`:616`). After any failed `/api/trio` (5xx, timeout, 403), `trio` is undefined, so the skeleton matched first and showed forever. The existing error branch, with its Try again button (`trioQuery.refetch()`, `:627`), could never be reached.

**The fix.** Mobile only, in that one chain:
- The chain is now: rookie empty → `trioQuery.isError` error view → `isLoading || !trio` skeleton → cards.
- The error view keeps the existing "Try again" button (`trioQuery.refetch()`).
- It always shows the app's existing string "Could not load next trio", never the raw error text.

**P2-1 (release-lead QA on #500, 2026-10-28) and its fix.** The first fix guarded the error branch with `&& !trio`.
- **The regression:** if the next-trio fetch failed right after a successful submit, the cached trio was still held, so the condition was false. The **just-ranked** trio came back enabled with no message.
- **Why it matters:** ranking it again sent a duplicate `/api/rank3`, which the server double-counts (`server.py:14331-14365`, `ranking_service.py:679`). Main showed the error view there.
- **Fix (rankings-eng's call, minimal):** the condition is now plain `trioQuery.isError`, still after RookieScopeEmpty and still before the skeleton. Every Trios refetch replaces the trio, so a failed one shows "Could not load next trio" + Try again, never a stale rankable trio.
- While a refetch is pending, the held trio stays disabled (`isRefetchingTrio`), as before.
- No `resetQueries`: it would flash the skeleton on every submit.

---

## 1. Analytics scope

- [x] **(c) WAIVED.** No analytics are needed: no event is added or changed. The fix makes an existing error view reachable. It adds no user action and no new surface.

## 2. Schema & flag scope

- New/changed tables or columns: **none**. This is a client render-order fix.
- New/changed feature flags: **none**. A flag would keep the stuck skeleton reachable, and there is nothing to graduate.
- New env vars / `model_config` keys: **none**.
- API: **none**. `/api/trio` is unchanged; only how the client renders its failure changes.
- Copy: **none new**. "Could not load next trio" and "Try again" already ship in this branch, so no marketing route is needed.

## 3. Evidence scope

- [x] **Structural guard:** `mobile/tests/check-rank-trios-error.js`. It is dependency-free (fs + string scanning), so it runs under plain node without `node_modules`, and CI's `mobile-typecheck` globs `tests/check-*.js`. It pins:
  - **(a)** the RookieScopeEmpty branch stays first, and the `isError` condition comes before the `isLoading || !trio` skeleton condition;
  - **(b)** the error branch renders a pressable (chalkline `Button`, which wraps `Pressable`) whose `onPress` calls `trioQuery.refetch`;
  - **(c)** the error branch references **no `error` identifier and no `.message` at all**. This catches `error?.message ?? …`, `String(error…)` and `(error as Error).message || …`. It also shows "Could not load next trio". Comments are stripped before matching;
  - **(d)** the error condition is **exactly** `trioQuery.isError`, with no `!trio` / `!trioQuery.data` (or any other) conjunct (P2-1);
  - **(e)** nothing **above** the error branch renders a skeleton or tests `!trio`, `!trioQuery.data`, `isLoading` or `isFetching`. This catches `: !trio ? (` and `isFetching || !trio`;
  - **(f)** the error branch's Button keeps `label="Try again"`.

  Each assertion was sabotaged once (red), then restored (green):

  | Sabotage | Red | Green after restore |
  |---|---|---|
  | (a) pre-fix order (skeleton block moved back in front of the error block) | (a) + (e) FAIL | ✓ |
  | (b) `onPress={() => {}}` | (b) FAIL | ✓ |
  | (c) `{trioQuery.error?.message ?? 'Could not load next trio'}` | (c) FAIL | ✓ |
  | (c) `{String(trioQuery.error) \|\| 'Could not load next trio'}` | (c) FAIL | ✓ |
  | (c) `{(trioQuery.error as Error).message \|\| 'Could not load next trio'}` | (c) FAIL | ✓ |
  | **(d) P2-1 shape: `trioQuery.isError && !trio`** | (d) FAIL | ✓ |
  | (d) `trioQuery.isError && !trioQuery.data` | (d) FAIL | ✓ |
  | (e) a `) : !trio ? ( <skeleton> )` branch inserted above the error branch | (e) FAIL | ✓ |
  | (e) a `) : trioQuery.isFetching \|\| !trio ? ( <skeleton> )` branch inserted above | (e) FAIL | ✓ |
  | (f) `label="Retry"` | (f) FAIL | ✓ |
  | Control: main's `RankScreen.tsx` (`b5526d9e`) | (a), (c), (e) FAIL | — |
  | Control: the first B6 fix (`c6d4c3e1`, the P2-1 build) | (d) FAIL | — |

  Its header carries the G-035 "HONEST LABEL": it proves the presence and order of the wiring, not runtime behavior.
- [ ] **Unit tests:** none. There is no jest harness in `mobile/` (see `mobile/tests/README.md`), and the guard covers the wiring.
- [x] **Code-walk proof** (`mobile/src/screens/RankScreen.tsx`, branch head):
  - `:299-302` `trioEmpty` is the scoped typed-empty response; `trio` is undefined when `trioEmpty` is set **or** when there is no data (initial load, or a failed first fetch).
  - `:591` `{trioEmpty ? (` → `:596` `<RookieScopeEmpty …>`: the designed empty state, still first and unchanged.
  - `:602` `) : trioQuery.isError ? (`: **any** failed `/api/trio` renders the error view, whether or not a trio is held.
    - `:612` `<Text style={styles.errorText}>Could not load next trio</Text>`: fixed copy.
    - `:616-617` the existing ghost `Button label="Try again"` with `onPress={() => trioQuery.refetch()}`.
  - `:620` `) : trioQuery.isLoading || !trio ? (`: the three skeleton cards. This is now only reached while loading, or with no trio and no error.
  - `:634` `) : (`: the cards. TypeScript narrows `trio` to `Trio` here (the false branch of `… || !trio`), as before.
  - **After a submit (the P2-1 path):** a successful `/api/rank3` invalidates `['trio', position]` (`:238`), so the trio query refetches while still holding the just-ranked trio.
    - While that refetch is pending, `isRefetchingTrio` (`:288`) keeps every card disabled (`:645`).
    - If it **fails**, React Query keeps `data` but sets `status: 'error'`, so `:602` renders the error view. The just-ranked trio can't be ranked again.
    - If it succeeds, the new trio replaces it.
  - During a **Retry** after an error, TanStack Query v5 (`@tanstack/react-query ^5.99`) resets a data-less query to `status: 'pending'` when it refetches. So Try again shows the skeleton until the request succeeds (cards) or fails again (error view, after the app default `retry: 1`, `state/queryClient.ts:27`).
  - **Offline is a different state.** `App.tsx:240-242` bridges `onlineManager` to NetInfo `isConnected`. In airplane mode the `/api/trio` query **pauses** instead of failing: status stays `pending` and `fetchStatus` is `paused`, so the skeleton holds. It refetches on its own when the connection returns (`refetchOnReconnect: true`). That is not the stuck state this fixes: it recovers when the user is back online. The error view is reached when the device is "connected" but the request fails (5xx, timeout, 403, or no internet behind the network).
- [x] **Manual TestFlight checklist** (runtime proof matters; this is the only runtime evidence mobile gets).

  Airplane mode alone does **not** reach the error view in this app: offline queries pause (see the code-walk). Step 1 therefore needs a network that is connected but has no internet.
  1. Join a Wi-Fi network with **no internet behind it**: a second phone's personal hotspot, with **cellular data turned off** on that phone. Open Rank → Trios.
     - **Expected:** within about 30 s, the card area shows "Could not load next trio" with a **Try again** button. It must not show three grey skeleton cards indefinitely.
  2. Restore a working connection (turn the hotspot phone's cellular data back on, or switch to a normal Wi-Fi) and tap **Try again**.
     - **Expected:** the skeleton shows briefly, then a trio of three player cards loads and ranking works.
  3. **(P2-1)** On a working connection, rank a trio. Then **cut the connection before the next one loads**: turn the hotspot phone's cellular data off right as you submit, or join the no-internet hotspot.
     - **Expected:** the error view ("Could not load next trio" + Try again) appears.
     - The **same trio never comes back** as rankable. Tapping Try again after reconnecting loads a new trio.
  4. With a normal connection, open Trios fresh and rank 2–3 trios.
     - **Expected:** unchanged: three skeleton cards briefly, then the trio. No error text appears between trios.
  - *(Optional regression note.)* With **airplane mode** on, Trios shows the skeleton while paused. When airplane mode goes off it loads a trio on its own, without a tap.
- `testID`s added/renamed: none. `mobile/scripts/testid-lint.sh` → "testid-lint OK".

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a | No route added, renamed or changed |
| `living-memory/LLD.md` | n/a | No schema, route or invariant convention shifted; this is one screen's render order |
| `docs/architecture.md` | n/a | No module wiring or data flow change |
| `living-memory/HLD.md` | n/a | No new module, client or flow |
| `docs/cross-client-invariants.md` | n/a | No shared constants or enums |
| `docs/glossary.md` | n/a | No new domain term |
| ADR or `DECISIONS.md` | n/a | No non-obvious choice: the branch order follows from the bug |

## 5. Ship gate declaration

- **CI green** (`backend-tests`, `mobile-typecheck`, which runs `tsc --noEmit` and every `check-*.js`, plus `maestro-testid-lint`) on the pushed sha. This worker does not push.
- **Not run locally:**
  - `tsc` and the two existing typescript-backed `check-rank-*.js` suites (`check-rank-nav-exit`, `check-rank-presets`). They `require('typescript')`, and worktrees have no `mobile/node_modules` (G-022). Both exit "typescript not resolvable" here.
  - Neither reads `RankScreen.tsx`: nav-exit reads `TabNav.tsx`, and presets tests the CSV parser.
  - CI runs all three.
- **Evidence recorded:** the TEST_LEDGER entry is release-lead's, at merge.
- **TestFlight verification:** the 4-step checklist in §3, run by the operator on the 11-06 build.
- Express lane declared by the operator? **No.**

## Out of scope, reported

**P2-2 (release-lead QA, pre-existing).** An **offline first load** shows a paused skeleton with no message:
- Under NetInfo's `isConnected=false`, the query pauses and never errors, so the error view doesn't apply.
- It recovers on its own when the connection returns (`refetchOnReconnect`).
- Telling the user they're offline needs **new copy**, which goes through the copy route. It is not changed here.

The mode hint above the cards, "Trios · tap Rank below for more modes" (`RankScreen.tsx:447`), is stale:
- It points the user down to the tab bar.
- On these flag-on rank surfaces, the way to other ranking modes is the **"More ways to rank"** header control at top right (`mobile/src/navigation/TabNav.tsx:184-209`).

This is a separate copy item for the copy route (head-eng → head-bizops → marketing-lead). It is not changed here.
