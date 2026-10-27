# Feature Scope — Claim sheet → Sleeper app hand-off (#351, league-eng)

**Date:** 2026-10-27
**Entry point:** direct ask. The league-eng row of `docs/plans/external-links/scope.md` § "Deferred to other leads", building on PR #379 (`build/open-external-helper` @ `04eae95b`). The spec is the #351 PRD (`origin/plan/sleeper-fa-deeplink:docs/plans/sleeper-fa-deeplink/prd.md`) §3.2, §4.1, §4.2, §4.4, AC-1/2/9/10, guards S1/S2/S8/S9, §7.2 code-walks A and B, TestFlight rows 13/14.
**Builder:** eng-mobile worker for league-eng (task `b3-eng-mobile-1`), branch `build/b3-claim-handoff`
**Operator sign-off on waivers:** pending. Waiver to surface: §1 analytics (c), the same waiver #379 carries.

## Contents

- [What ships](#what-ships)
- [1. Analytics scope](#1-analytics-scope)
- [2. Schema & flag scope](#2-schema--flag-scope)
- [3. Evidence scope](#3-evidence-scope)
- [4. Docs scope](#4-docs-scope-mandatory--hld--lld--api)
- [5. Ship gate declaration](#5-ship-gate-declaration)
- [Known risk](#known-risk)

---

## What ships

Two commits. The second is droppable on its own.

| Commit | File | Change |
|---|---|---|
| 1 | `mobile/src/components/ClaimSheet.tsx` | The CTA (`openSleeper`) calls `openInSleeperApp({ target: 'add', leagueId, playerId: row.player_id, surface })` instead of `Linking.openURL(\`https://sleeper.com/leagues/${leagueId}/players\`).catch(() => {})`. New optional props `leagueName?: string \| null` (not rendered in commit 1) and `surface?: ExternalSurface` (default `'unspecified'`). `Linking` import removed. No `clipboardText`: copying without the on-sheet disclosure is out (PRD §4.2). `NO_ADD_REASON`, `explainNoAdd`, `resolveAddPlatform`, the `fa-claim.open-sleeper` testID and the CTA label are unchanged. |
| 1 | `mobile/src/screens/FreeAgentsScreen.tsx` | Passes `leagueName` (the session league's `league_name`; the screen's `leagueId` is the session league's id, so it is always the claim league) and `surface="free_agents"`. Release-lead QA rule: the render chain tests `query.isError` before `query.isLoading` (the two branches swapped, nothing else). |
| 1 | `mobile/src/screens/UsageTrendsScreen.tsx` | The `<ClaimSheet>` mount only (granted by rankings-eng): `leagueName={leagueMeta.get(claim.leagueId)?.name ?? (claim.leagueId === leagueId ? (leagueName ?? null) : null)}` and `surface="usage_trends"`. |
| 1 | `mobile/tests/check-external-links.js` | The league-eng LEGACY entry for `ClaimSheet.tsx` is deleted (the ratchet requires it). |
| 1 | `mobile/tests/check-sleeper-handoff.js` | S1, S2 (ClaimSheet half), S9, H1, H2. See §3. |

No native change, no `Info.plist` key, no `app.json`/`eas.json` change, no flag, no route, no event, no backend change.

## 1. Analytics scope

- [ ] **(a) New events specced:** none.
- [x] **(b) Existing events cover part of it:** Usage Trends' `usage_trends_action {action: 'add'}` still fires on the Add tap (`UsageTrendsScreen.tsx:286`), before the sheet opens. Nothing fires on the claim sheet's CTA, before or after this change.
- [x] **(c) WAIVED, pending analytics-lead's grant.** `surface` feeds no event. `ExternalTarget.surface` is carried into `openPlatform` so that, once analytics-lead grants `external_link_opened` (or #351's `sleeper_handoff_resolved`) and registers it in `backend/analytics_taxonomy.py` + `analytics_queries.NON_INTENT_EVENTS`, the emitter goes inside `openPlatform` with no call-site change. Not granted, so nothing fires. The PRD's `hasDrop` property exists only for that event, so it isn't passed.

## 2. Schema & flag scope

- New/changed tables or columns: **none**
- New/changed feature flags: **none**. Rollback is revert + EAS build (#351 PRD §10).
- New env vars / `model_config` keys: **none**
- Native config: **none**.

## 3. Evidence scope

- [x] **Structural guards** (live in CI through the `tests/check-*.js` glob):
  - `check-sleeper-handoff.js`, new checks. All are AST checks that prove wirings, not behavior (G-035); no claim-sheet code is executed.
    - **S1:** `ClaimSheet.tsx`, `FreeAgentsScreen.tsx` and `UsageTrendsScreen.tsx` hold no `sleeper.com/leagues` string or template literal, and no `Linking.openURL` whose argument mentions Sleeper.
    - **S2 (ClaimSheet half):** `ClaimSheet.tsx` imports `openInSleeperApp` from `../utils/sleeperHandoff`. There is exactly one `fa-claim.open-sleeper` Button, its label is still "Open in Sleeper to claim", and its `onPress` is `openSleeper`. `openSleeper` calls `openInSleeperApp({ target: 'add', … })` with `leagueId`, `playerId: row.player_id` and `surface`.
    - **S9:** the eight `NO_ADD_REASON` strings, evaluated from the AST, equal the `04eae95b` strings copied into the guard. `explainNoAdd` and `resolveAddPlatform` are byte-identical to `04eae95b`.
    - **H1** (the b3 brief's, not a PRD id): Free Agents mounts `ClaimSheet` with `surface="free_agents"` and `leagueName={leagueName}`, where `leagueId` and `leagueName` both read `useSession` → `s.league`. Usage Trends mounts it with `surface="usage_trends"` and the exact `leagueName` expression above, so the session name is used only when the claim league is the session league.
    - **H2** (the b3 brief's): in `FreeAgentsScreen`, the `query.isLoading` conditional sits inside the `query.isError` conditional's false branch.
  - `check-external-links.js`: the ClaimSheet LEGACY entry is gone, and a1 now covers `ClaimSheet.tsx` like any other file.
  - **Sabotage run** (applied, guard run, restored byte-for-byte; all green after):

    | # | Sabotage | Red |
    |---|---|---|
    | 1 | `openSleeper` restored to `Linking.openURL(\`https://sleeper.com/leagues/${leagueId}/players\`).catch(() => {})` (the PRD's named S1 sabotage) | sleeper-handoff S1 ×2, S2 ×2; external-links a1 |
    | 2 | `target: 'add'` → `'trade'` | S2 |
    | 3 | one character of `NO_ADD_REASON.espn.body` (the PRD's named S9 sabotage) | S9 |
    | 4 | `explainNoAdd` → `Alert.alert(reason.title)` | S9 |
    | 5 | `resolveAddPlatform` drops `\|\| isDemo` | S9 |
    | 6 | Free Agents drops `surface="free_agents"` | H1 |
    | 7 | Usage Trends: `leagueName={leagueMeta.get(claim.leagueId)?.name ?? (leagueName ?? null)}` (the session name for any claim league) | H1 |
    | 8 | Usage Trends drops `leagueName` | H1 |
    | 9 | the ClaimSheet LEGACY entry re-added | external-links a2 ("matches none") |
    | 10 | Free Agents' `isLoading` branch moved back above `isError` | H2 |
- [x] **Unit tests:** no backend pytest; nothing in `backend/` changed.
- [x] **Code-walk proof** (file:line at commit 1; #351 PRD §7.2 A and B):

  **A. Free Agents → Add → claim sheet → CTA**
  1. `FreeAgentsScreen.tsx:53` `leagueId` = the session league's id; `:56` `leagueName` = the same session league's `league_name` (or `null`).
  2. Row **Add** (`:271-275`, testID `free-agents.add.<id>`) → `onAdd` `:84-91`: `:87` a Sleeper league → `setClaimTarget(row)`; `:88` anything else → `explainNoAdd` (unchanged, S9).
  3. `:212-223` mounts `<ClaimSheet … leagueId={leagueId} leagueName={leagueName} surface="free_agents" />` (`:216-218`).
  4. `ClaimSheet.tsx:114` takes `surface`; `:123` declares `leagueName` (unrendered in commit 1).
  5. CTA `:314-320` (`fa-claim.open-sleeper`, disabled while the bid is over budget) → `openSleeper` `:146-152` → `:151` `openInSleeperApp({ target: 'add', leagueId, playerId: row.player_id, surface })`.
  6. `sleeperHandoff.ts:95-106` → `:100` `sleeperAppUrl(t)` `:79-91`: `:83` keeps L only if numeric, `:84` keeps P for `add`; `:85-89` walks `SLEEPER_PROVEN_RUNGS.add` = `['bare']` (`:39`) → `rungUrl('bare')` `:71-72` → `sleeper://`. `:102` `surface: 'free_agents'`; `:103` `appMissing: 'alert'`.
  7. `openExternal.ts:70-81` `openPlatform`: `:71` no open in flight → `:72` `attempt`; `:78` 2 s lock release; `:79` release on settle.
  8. `attempt` `:83-96`: `:84` no `clipboardText`, so nothing is copied; `:86` `opened('sleeper://')` → `:100-107` → `:102` `await Linking.openURL`.
  9. RN 0.81.5 `RCTLinkingManager.mm:90-99`: Sleeper handles the scheme → `resolve(@YES)` → `'app'` → `openInSleeperApp` returns `'app'` (`sleeperHandoff.ts:105`). Sleeper opens on its last-viewed screen (bare rung). No Safari.
  10. Not installed: `RCTLinkingManager.mm:111` rejects "Unable to open URL" → `opened` returns `false` (`openExternal.ts:104-105`) → `:87-90` the D2 alert (`showAppMissing` `:110-126`: "Sleeper isn’t installed" / **Cancel** · **Get Sleeper**) → `'fallback'` → `'not_installed'`. https is never tried. **Get Sleeper** (`:118-121`) opens `https://apps.apple.com/app/id987367543`; if that rejects too, "Couldn’t open that link".

  **B. Usage Trends → Add → claim sheet → CTA**
  1. Entry: a card/row Add (`UsageTrendsScreen.tsx:382`, `:407`, the focused league) or the availability sheet's per-league Add (`:674`, any league) → `doAdd` `:285-295`.
  2. `:286` `trackAction('add')` (unchanged) → `:287` `resolveAddPlatform(lgId)` → `:290` non-Sleeper `explainNoAdd` (unchanged, S9) → `:293` `switchTo(lgId)` (`:228-242`; a non-focused league goes through `switchLeague` at `:236`, so the session league becomes the claim league) → `:294` `setClaim({ target, leagueId: lgId })`.
  3. Mount `:679-692`: `leagueId={claim.leagueId}`; `:684` `leagueName` = the claim league's own name from `leagueMeta` (`:151`, the session's league list), else the session `league_name` (`:95`) only when `claim.leagueId === leagueId` (`:94`), else `null`; `:685` `surface="usage_trends"`. `faQuery` (`:135-141`) loads that league's capacity, waivers and drop candidates.
  4. Then A4–A10, with `surface: 'usage_trends'`.

  **C. Non-Sleeper invariance.** `ClaimSheet.tsx` `resolveAddPlatform`, `NO_ADD_REASON` and `explainNoAdd` (`:59-104`): no content change (S9). Free Agents' `onAdd` and Usage Trends' `doAdd` are unchanged.

- [x] **Manual TestFlight checklist** (for the operator, on the build that carries this branch; adapted from #351 PRD rows 13, 14 and 16). Run the commit-1 variant if commit 2 is dropped, the commit-2 variant if it ships.

  | # | Sleeper app | Steps | Expected |
  |---|---|---|---|
  | 1 | installed, signed in, **2+ leagues**; in Sleeper open league **M** last, then swipe Sleeper away | FTF on league **L** (not M) → League → Free agents → **Add** on a player → claim sheet → **Open in Sleeper to claim** | The **Sleeper app** opens directly: no Safari, no "Open in Sleeper?" prompt. At the bare rung it lands on whatever Sleeper last showed, so **expect league M, not L**. Record the landing screen. **Commit-1 variant:** nothing on the sheet names the league; the user has to switch to L in Sleeper themselves. |
  | 2 | as 1 | Usage Trends → a player → the availability sheet → **Add** in a league **other than** FTF's focused one | FTF switches to that league, then the claim sheet opens. The CTA opens the Sleeper app as in 1 (last-viewed league, not necessarily the claim league). |
  | 3 | **not installed** (Settings → General → iPhone Storage → Sleeper → Offload App) | Free agents → Add → CTA | Alert "Sleeper isn’t installed" with **Cancel** / **Get Sleeper**. **Get Sleeper** opens the **App Store app** on Sleeper's listing, with no Safari. **Cancel** returns to the sheet and opens nothing. Never a silent no-op. |
  | 4 | installed | Free agents → Add → **double-tap** the CTA fast | Exactly one app switch. |
  | 5 | — | An ESPN or MFL league → Free agents → **Add** | Unchanged: the "Can't add in ESPN leagues yet" / "Can't add in MFL leagues yet" alert. No sheet, no link. |

- [ ] **WAIVED because:** n/a, not waived.
- `testID`s added/renamed: **none** (`fa-claim.open-sleeper` kept). `bash scripts/testid-lint.sh` → `testid-lint OK`.

**Commands run** (from `mobile/`; this worktree has no `node_modules` (G-022), so the guards ran with `NODE_PATH` pointed at another checkout's `mobile/node_modules`, at the same `package-lock.json`):

| Command | Result |
|---|---|
| `node tests/check-sleeper-handoff.js` | 68 PASS, 0 FAIL |
| `node tests/check-external-links.js` | 46 PASS, **4 FAIL, all pre-existing at `04eae95b`** (main's #360 added a `FeedbackSheet` mailto and removed three `SettingsScreen` links; the merge didn't update the LEGACY list). Not in this change's files. Before this change: 47 PASS, the same 4 FAIL. |
| `node tests/check-usage-trends.js` | 76 PASS (§2i/2j, the shared ClaimSheet) |
| `node tests/check-home-destinations.js`, `check-league-drill-in.js`, `check-picker-pick-filter.js` (the other guards that read `FreeAgentsScreen`) | all pass |
| `node tests/check-send-button-platform.js`, `check-trade-text.js` | all pass |
| `bash scripts/testid-lint.sh` | `testid-lint OK` |
| `tsc --noEmit` | exit 0, run on a scratch copy of `mobile/` with a borrowed `node_modules` (same lock file). CI is the gate. |

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a | No route added, renamed or changed. |
| `living-memory/LLD.md` | n/a | No new convention. "Every outside link goes through `utils/openExternal`" is #379's, already handed to the coordinator in `scope.md` §4. |
| `docs/architecture.md` | n/a | No backend module or data-flow change. |
| `living-memory/HLD.md` | n/a | No new module, client or major flow. |
| `docs/cross-client-invariants.md` | n/a | No shared constant or enum. |
| `docs/glossary.md` | n/a | No new UI term. |
| ADR or `DECISIONS.md` | n/a | No new non-obvious choice. The `leagueName` precedence follows the brief; the hand-off design is #379's. |
| `docs/integrations/sleeper.md` | **updated** | §1.3: the ClaimSheet row (was "Deep link (legacy, league-eng)", https) now describes the `openInSleeperApp({ target: 'add' })` call, its two hosts and surfaces, and the last-viewed-league risk. |

## 5. Ship gate declaration

- **CI green:** local equivalents above, except `check-external-links.js`'s 4 pre-existing failures, which make the `mobile-typecheck` job red on #379's tip as well. Someone has to fix them before either branch merges (owner: platforms-eng, #379's builder, or the LEGACY owners). Not pushed; CI hasn't run.
- **Evidence recorded:** this file. A `living-memory/TEST_LEDGER.md` entry is **pending for the coordinator** (shared doc, G-022) and required before merge.
- **TestFlight verification:** checklist in §3; the operator runs it, and the outcome goes in TEST_LEDGER.
- **Merge gate (from #379):** #351 device tests R0, 1–12 and T1–T4 recorded in `docs/plans/sleeper-fa-deeplink/device-results.md`. Test 3 (`sleeper://` registered) is go/no-go.
- Express lane declared by the operator? **No.** Full gates.

## Known risk

At the `bare` rung Sleeper reopens its **last-viewed league** (PRD C2), not the claim league. A user with several Sleeper leagues can land in the wrong one and add the player there. The old https link had the same end state on iPhone (Safari → Sleeper's home, #351 F3), so this is not a regression, but it is not fixed either. **Without commit 2, nothing on the sheet tells the user which league to pick.** Commit 2's steps block names the league. A deeper rung (`players_tab` or `league`) fixes it only once a device test proves Sleeper honours the league path.
