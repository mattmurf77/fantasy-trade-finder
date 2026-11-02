# Feature Scope — Trios: remove the stale mode hint

**Date:** 2026-10-29
**Entry point:** direct ask (11-06 binary; marketing §6 addendum 10 item 6, from Product's pre-launch review)
**Builder:** build worker for rankings-eng, branch `fix/trios-hint-remove` (base `origin/main` `a0e12076`)
**Operator sign-off on waivers:** pending. The waivers below go to the operator through rankings-eng.

**The bug.** `mobile/src/screens/RankScreen.tsx` rendered, unconditionally, `Trios · tap Rank below for more modes` (on main `:445-448`). It has been wrong since `ux.rank_tab_destination` went on (`config/features.json:166`):
- The Rank tab now navigates instead of opening a mode menu.
- The other modes sit under the header's "More ways to rank" control on every flag-on rank surface (`mobile/src/navigation/TabNav.tsx:167-209`).
- The screen's own prompt, `Tap in order of preference — best first`, already says what to do.

**The fix.** Mobile only, in `RankScreen.tsx`:
- The hint `<Text>` and its comment are deleted.
- The `modeHint` / `modeHintDim` styles are deleted (now unused).
- `const cleanupOn = useFlag('visual.chalkline_cleanup')` is deleted: the hint was its only reader. `useFlag` stays imported (four other flags use it), and no theme import became unused (`chalk`, `type` and `space` are used elsewhere).
- Nothing else changes. The trio render chain (open PR #500, `fix/trios-error-state`) is untouched, and the two branches merge cleanly.

**Copy:** marketing's §6 addendum 10 item 6: "Recommended: remove the hint." It's a removal, so there's no legal stamp, and no operator ask by marketing's reading (that's head-bizops' call).

---

## 1. Analytics scope

- [x] **(c) WAIVED.** No analytics are needed: the hint had no event, and no event is added or changed.

## 2. Schema & flag scope

- New/changed tables or columns: **none**. This is a client copy removal.
- New/changed feature flags: **none**. `visual.chalkline_cleanup` keeps its other readers; only RankScreen's read of it goes. `ux.rank_tab_destination` is unchanged (the guard pins it on).
- New env vars / `model_config` keys: **none**.
- API: **none**.

## 3. Evidence scope

- **Maestro delta:** retired (D-056).
- [x] **Structural guard:** `mobile/tests/check-rank-trios-hint.js`. It is dependency-free (fs + string scanning, comments stripped), so it runs under plain node without `node_modules`, and CI's `mobile-typecheck` globs `tests/check-*.js`. It pins:
  - **(a)** RankScreen.tsx has no `tap Rank below` and no `for more modes`;
  - **(b)** RankScreen.tsx has no `modeHint` identifier;
  - and the three premises that make the removal safe. If one breaks, the failure says the hint question needs reopening:
  - **(c)** RankScreen.tsx still shows `Tap in order of preference — best first`;
  - **(d)** `config/features.json` still has `"ux.rank_tab_destination": true`;
  - **(e)** `mobile/src/navigation/TabNav.tsx` still has `More ways to rank`.

  No `npm run test:` script was added: `mobile/package.json` is outside this change's file grant, and CI runs the file through the glob.

  Each assertion was sabotaged once (red), then restored (green):

  | Sabotage | Red | Green after restore |
  |---|---|---|
  | (a) `<Text>Trios · tap Rank below for more modes</Text>` re-added (no style) | (a) FAIL | ✓ |
  | (b) `modeHint: { ...type.bodySm },` re-added to the StyleSheet | (b) FAIL | ✓ |
  | (c) the prompt changed to `'Tap your favourite first'` | (c) FAIL | ✓ |
  | (d) `"ux.rank_tab_destination": false` | (d) FAIL | ✓ |
  | (e) every `More ways to rank` in TabNav.tsx → `Other modes` | (e) FAIL | ✓ |
  | Control: main's `RankScreen.tsx` (`a0e12076`) | (a) + (b) FAIL | — |

  Its header carries the G-035 "HONEST LABEL": it proves the source text, not runtime behavior.
- [ ] **Unit tests:** none. There is no jest harness in `mobile/` (see `mobile/tests/README.md`), and the guard covers the removal.
- [x] **Code-walk proof** (file:line on main `a0e12076` unless marked "branch"):
  - **The hint rendered unconditionally.** `RankScreen.tsx:443` closes the streak-chip conditional (`) : null}`). The hint at `:445-448` sat outside any condition, between that and `<FormatToggle>` at `:455`. Its only condition was a style toggle (`cleanupOn && styles.modeHintDim`, `:446`; `cleanupOn` read at `:145`).
  - **The flag is on.** `config/features.json:166` `"ux.rank_tab_destination": true`.
  - **The Rank tab navigates.** `TabNav.tsx:847-862`: with `rankDest` on, `tabPress` only tracks and pops to the stack root ("Mode switching lives in the surfaces' 'More ways to rank' header control"). The mode-menu path (`setRankMenuOpen(true)`, `:870`) is the flag-off branch.
  - **"More ways to rank" is on every flag-on rank surface.** `TabNav.tsx:184-198` `MoreWaysButton` (`testID="rank.more-ways"`, text "More ways to rank") navigates to `RankHome`. `:204-210` `rankSubScreenOptions` puts it in `headerRight`. `RankStackNav` reads `rankDest` at `:289`, and every rank surface takes `rankSubScreenOptions` when it's on: Trios `:315-318` (RankScreen itself), Pick Anchors `:327`, Tiers `:336`, Quick Set Tiers `:365`, Quick Rank `:403`, Overall Ranks `:412`, Rookie Ranks `:424`, Trends `:433`. `RankHome`'s title is "Build your board" (`RankHomeScreen.tsx:198`).
  - **The prompt.** `RankScreen.tsx:575` (branch `:569`) `'Tap in order of preference — best first'`, the instruction line's first state, shown before any card is tapped.
  - **Spacing after the removal (branch).** The streak chip row (`:416`) is followed directly by `<FormatToggle>` (`:449`). The ScrollView's `gap: space.md` (`:898`, 12 pt) is now the only space between them. The hint had pulled itself 4 pt up (`marginTop: -space.xs`), and that's gone with it.
- [x] **Manual TestFlight checklist** (run by the operator on the 11-06 build):
  1. Open Rank → Head-to-heads (Trios).
     - **Expected:** the "Trios · tap Rank below for more modes" line is gone.
     - The format toggle sits under the streak chip (or at the top, with no streak) with normal spacing: nothing overlapping or crowded.
  2. Tap "More ways to rank" in the header.
     - **Expected:** it still opens the "Build your board" chooser.
  3. Rank a trio: tap the three players in order.
     - **Expected:** it still works. The prompt reads "Tap in order of preference — best first", then steps through as you tap, and the next trio loads.
- `testID`s added/renamed: none. `mobile/scripts/testid-lint.sh` → "testid-lint OK".

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a | No route added, renamed or changed |
| `living-memory/LLD.md` | n/a | No schema, route or invariant convention shifted; one screen loses a line of copy |
| `docs/architecture.md` | n/a | No module wiring or data flow change |
| `living-memory/HLD.md` | n/a | No new module, client or flow |
| `docs/cross-client-invariants.md` | n/a | No shared constants or enums; the hint was mobile-only |
| `docs/glossary.md` | n/a | No new domain term |
| ADR or `DECISIONS.md` | n/a | No non-obvious choice: marketing's recommended option, applied as written |

## 5. Ship gate declaration

- **Simulator-gate tier:** retired (D-056).
- **CI green** (`backend-tests`, `mobile-typecheck`, which runs `tsc --noEmit` and every `check-*.js`, plus `maestro-testid-lint`) on the pushed sha. This worker does not push.
- **Not run locally:** `tsc`, and the `check-*.js` suites that `require('typescript')`. Worktrees have no `mobile/node_modules` (G-022), so they exit "typescript not resolvable" here. CI runs them.
- **Evidence recorded:** the TEST_LEDGER entry is release-lead's, at merge.
- **TestFlight verification:** the 3-step checklist in §3, run by the operator on the 11-06 build.
- Express lane declared by the operator? **No.**
