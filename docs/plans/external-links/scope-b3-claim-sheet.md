# Feature Scope — Claim sheet → Sleeper app hand-off (#351, league-eng)

**Date:** 2026-10-27
**Entry point:** direct ask. The league-eng row of `docs/plans/external-links/scope.md` § "Deferred to other leads", building on PR #379 (`build/open-external-helper` @ `04eae95b`). The spec is the #351 PRD (`origin/plan/sleeper-fa-deeplink:docs/plans/sleeper-fa-deeplink/prd.md`) §3.2, §4.1, §4.2, §4.4, AC-1/2/9/10, guards S1/S2/S8/S9, §7.2 code-walks A and B, TestFlight rows 13/14.
**Builder:** eng-mobile worker for league-eng (task `b3-eng-mobile-1`; commit 3: task `b3-eng-mobile-3`; commit 4: task `b3-eng-mobile-4`), branch `build/b3-claim-handoff`
**Operator sign-off on waivers:** pending. Waiver to surface: §1 analytics (c), the same waiver #379 carries.

## Contents

- [What ships](#what-ships)
- [1. Analytics scope](#1-analytics-scope)
- [2. Schema & flag scope](#2-schema--flag-scope)
- [3. Evidence scope](#3-evidence-scope)
- [4. Docs scope](#4-docs-scope-mandatory--hld--lld--api)
- [5. Ship gate declaration](#5-ship-gate-declaration)
- [2026-10-28 — design-lead review](#2026-10-28--design-lead-review)
- [Copy for design-lead](#copy-for-design-lead)
- [2026-11-01 — pinned CTA footer](#2026-11-01--pinned-cta-footer)
- [Known risk](#known-risk)

---

## What ships

Four commits. Commits 2, 3 and 4 are droppable together: commit 3 reworks commit 2's steps block to design-lead's review ([2026-10-28 — design-lead review](#2026-10-28--design-lead-review)), and commit 4 adds one drop-row string from the same review.

| Commit | File | Change |
|---|---|---|
| 1 | `mobile/src/components/ClaimSheet.tsx` | The CTA (`openSleeper`) calls `openInSleeperApp({ target: 'add', leagueId, playerId: row.player_id, surface })` instead of `Linking.openURL(\`https://sleeper.com/leagues/${leagueId}/players\`).catch(() => {})`. New optional props `leagueName?: string \| null` (not rendered in commit 1) and `surface?: ExternalSurface` (default `'unspecified'`). `Linking` import removed. No `clipboardText`: copying without the on-sheet disclosure is out (PRD §4.2). `NO_ADD_REASON`, `explainNoAdd`, `resolveAddPlatform`, the `fa-claim.open-sleeper` testID and the CTA label are unchanged. |
| 1 | `mobile/src/screens/FreeAgentsScreen.tsx` | Passes `leagueName` (the session league's `league_name`; the screen's `leagueId` is the session league's id, so it is always the claim league) and `surface="free_agents"`. Release-lead QA rule: the render chain tests `query.isError` before `query.isLoading` (the two branches swapped, nothing else). |
| 1 | `mobile/src/screens/UsageTrendsScreen.tsx` | The `<ClaimSheet>` mount only (granted by rankings-eng): `leagueName={leagueMeta.get(claim.leagueId)?.name ?? (claim.leagueId === leagueId ? (leagueName ?? null) : null)}` and `surface="usage_trends"`. |
| 1 | `mobile/tests/check-external-links.js` | The league-eng LEGACY entry for `ClaimSheet.tsx` is deleted (the ratchet requires it). |
| 1 | `mobile/tests/check-sleeper-handoff.js` | S1, S2 (ClaimSheet half), S9, H1, H2. See §3. |
| 2 | `mobile/src/components/ClaimSheet.tsx` | **REMOVED 2026-11-01 (operator: no in-app instructions; see [the steps removed](#2026-11-01--operator-removes-the-in-app-steps)).** The PRD §4.2 steps block (testID `fa-claim.steps`) between the drop section and the CTA, live with the drop selection, in the `bare` rung's draft copy (the only rung proven). The CTA now also passes `clipboardText: row.name`, which the block discloses. Copy is marked `COPY: draft, pending design-lead/ux-lead (#351 PRD §4.2)`. See [Copy for design-lead](#copy-for-design-lead). **Droppable:** it waits on design-lead / ux-lead copy approval. |
| 2 | `mobile/tests/check-sleeper-handoff.js` | **REMOVED 2026-11-01 (operator: no in-app instructions; see [the steps removed](#2026-11-01--operator-removes-the-in-app-steps)).** S8. |
| 3 | `mobile/src/components/ClaimSheet.tsx` | **REMOVED 2026-11-01 (operator: no in-app instructions; see [the steps removed](#2026-11-01--operator-removes-the-in-app-steps)).** design-lead's 4 changes: the steps block becomes a `TickLabel` "IN SLEEPER" over numbered rows (a local `ClaimStep`: Plex Mono `data` chalk-dim numeral + `body-sm` chalk-dim text, `space.xs` apart, no hairlines, no card), testIDs `fa-claim.step.league` / `.search` / `.add` / `.drop` / `.bid`. Step 1 always renders, with a null-league fallback. The drop row covers a picked drop and the full-roster "pick a player above" case; a FAAB bid row is new. The clipboard line and `clipboardText: row.name` are unchanged. Copy marker now `COPY: draft, pending marketing + Sleeper label capture (#351 §7.3)`. |
| 3 | `mobile/tests/check-sleeper-handoff.js` | **REMOVED 2026-11-01 (operator: no in-app instructions; see [the steps removed](#2026-11-01--operator-removes-the-in-app-steps)).** S8 rewritten to the numbered structure (17 checks, was 7). |
| 4 | `mobile/src/components/ClaimSheet.tsx` | **REMOVED 2026-11-01 (operator: no in-app instructions; see [the steps removed](#2026-11-01--operator-removes-the-in-app-steps)).** The drop row's no-pick branch splits on `candidates.length === 0`. A full roster with an empty drop list now reads "Drop a player to make room", not "Drop: pick a player above": nothing is listed above to pick. design-lead's ruling (review 2026-10-28, a SHOULD): keep the row, since the user still has to drop someone in Sleeper; change only the words. Same chalk-dim row, no new style, no warn colour. Marked `COPY: empty-drop-list fallback, pending marketing.` `dropStep`, the numbering, the bid row, the copy line and the CTA are unchanged. |
| 4 | `mobile/tests/check-sleeper-handoff.js` | **REMOVED 2026-11-01 (operator: no in-app instructions; see [the steps removed](#2026-11-01--operator-removes-the-in-app-steps)).** S8: 2 new checks (19, was 17). The "pick a player above" check now also accepts that string as a leaf of the nested conditional. |
| 5 | `mobile/src/components/ClaimSheet.tsx` | **REMOVED 2026-11-01 (operator: no in-app instructions; see [the steps removed](#2026-11-01--operator-removes-the-in-app-steps)).** Marketing's final copy (addendum 12, 2026-10-29), two strings: row 2 becomes "Go to Players, then search **{Name}**", and the copy line becomes "Opening Sleeper copies {Name}, so you can paste it into search." The three `COPY:` markers now say "final per marketing addendum 12", and the block's adds "verbs pending #351 §7.3". No line moves, no guard change: S8 doesn't pin row 2, and the copy line still ends "…so you can paste it into search." |

Commit 5 is copy only and droppable with commits 2–4. See [Copy for design-lead](#copy-for-design-lead) for the final strings and the pre-approved verb swaps.

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
    - *(Removed 2026-11-01 with the steps; S2's continued block now guards their absence.)* **S8** (commit 2): `ClaimSheet.tsx` renders exactly one `fa-claim.steps` element, after the drop section and before the CTA. It **renders** (as `{…}` children, so a mention inside a condition doesn't count) `row.name`, the selected drop (a const that looks `dropId` up in `candidates`) and `leagueName`, and carries the "…so you can paste it into search." disclosure. `openSleeper` passes `clipboardText: row.name`.
    - **S8, rewritten in commit 3** (design-lead's numbered list): exactly one `fa-claim.steps` element, after the drop section and before the CTA, headed by one `TickLabel` "IN SLEEPER" imported from `./chalkline`, holding exactly one row each of `fa-claim.step.league` / `.search` / `.add` / `.drop` / `.bid`. The league row sits under no condition (no `?:` or `&&` between it and the block) and renders `leagueName` or, when that is null, the string "Open the league you're claiming in". The search row renders `row.name`. The drop row renders the selected drop (a const that looks `dropId` up in `candidates`), shows "Drop: pick a player above" in the no-drop branch, and is gated by a condition that (one const deep) includes `openSlots === 0`. The bid row renders the bid and is gated on `faab` and the bid. Rows carry `n` 1, 2, 3, drop 4, and bid `{<the drop row's condition> ? 5 : 4}`, so the numbering has no gap. The copy disclosure is the block's last element, after every row, and the block ends before the CTA. `openSleeper` passes `clipboardText: row.name`.
    - **S8, commit 4** (2 more checks): the drop row holds the string "Drop a player to make room" exactly once. The drop conditional's no-pick branch is itself a conditional on `candidates.length === 0` (or an equivalent, inline or one const deep: `!candidates.length`, `< 1`, or the `> 0` form with its branches read the other way). Its empty branch is exactly that string; the other branch is "pick a player above". So the two strings can't swap and the new one can't drop out.
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
    | 11 | commit 2: the drop-name interpolation removed (the PRD's named S8 sabotage) | S8 |
    | 12 | commit 2: the `leagueName` step removed | S8 |
    | 13 | commit 2: `clipboardText: row.name` dropped from the CTA | S8 |
    | 14 | commit 2: the copy disclosure line removed (a silent copy) | S8 |
    | 15 | commit 2: the steps block moved below the CTA | S8 |
    | 16 | commit 3: the league row wrapped in `{leagueName ? ( … ) : null}`, so it is omitted when null | S8 "the league row always renders" (only) |
    | 17 | commit 3: the drop-name interpolation (`<ChalkText …>{dropName}</ChalkText>`) removed | S8 "the drop row renders the selected drop" (only) |
    | 18 | commit 3: the bid row's condition `faab && bidNum != null` → `bidNum != null` | S8 "gated on faab and an entered bid" (only) |
    | 19 | commit 3: the clipboard line moved above the rows | S8 "the copy disclosure … is the block's last line" (only) |
    | 20 | commit 4: the new branch deleted (the drop row back to commit 3's) | S8 "carries "Drop a player to make room" once" and S8 "… when candidates.length === 0, else "pick a player above"" (only those two) |
    | 21 | commit 4: the two fallback strings swapped | S8 "… when candidates.length === 0, else "pick a player above"" (only) |
    | 22 | commit 4: the gate flipped to `candidates.length > 0`, strings left in place | S8 "… when candidates.length === 0, else "pick a player above"" (only) |
- [x] **Unit tests:** no backend pytest; nothing in `backend/` changed.
- [x] **Code-walk proof** (file:line at the branch tip, commit 5, which changes two strings and moves no lines over commit 4; #351 PRD §7.2 A and B). Commit 1 differs only in `ClaimSheet.tsx`: no steps block, no `clipboardText`, so step A5 and the copy in A9 don't exist there. Commit 2 renders A5 as one arrow-chain line instead of numbered rows. Commit 3 lacks A5's empty-list string, so everything after `ClaimSheet.tsx:360` sits 4 lines higher there.

  **A. Free Agents → Add → claim sheet → CTA**
  1. `FreeAgentsScreen.tsx:53` `leagueId` = the session league's id; `:56` `leagueName` = the same session league's `league_name` (or `null`).
  2. Row **Add** (`:271-275`, testID `free-agents.add.<id>`) → `onAdd` `:84-91`: `:87` a Sleeper league → `setClaimTarget(row)`; `:88` anything else → `explainNoAdd` (unchanged, S9).
  3. `:212-223` mounts `<ClaimSheet … leagueId={leagueId} leagueName={leagueName} surface="free_agents" />` (`:216-218`).
  4. `ClaimSheet.tsx:115-116` takes `leagueName` and `surface` (default `'unspecified'`); `:147` `dropName` = the selected drop candidate's name, or `null`; `:150` `dropStep` = a drop is picked or `openSlots === 0`; `:136-138` `faab` / `bidNum`.
  5. Steps block `:327-384` (`fa-claim.steps` `:332`), between the drop section and the CTA: `TickLabel` "IN SLEEPER" `:334`, then `ClaimStep` rows (`:403-421`: Plex Mono numeral + `body-sm` text, one VoiceOver element per row). `:336-346` **1** "Open **{League}**", or "Open the league you're claiming in" when `leagueName` is null; never omitted. `:347-350` **2** "Go to Players, then search **{Name}**". `:351-353` **3** "Add". `:354-369` **4** only when `dropStep`: "Drop **{Drop}**" (`:356-360`); with a full roster and no pick, "Drop a player to make room" when the drop list is empty (`:361-364`, `candidates` `:142`; the drop section above says "No droppable players found on your roster.", `:310-314`), else "Drop: pick a player above" (`:365-366`). `:372-379` the bid row, only in a FAAB league with a bid entered: "Bid **${bid}**", numbered 5 after a drop row, else 4. `:381-383` "Opening Sleeper copies {Name}, so you can paste it into search.", the block's last line. A drop-row tap (`setDropId`) or a bid edit (`setBid`) re-renders the block.
  6. CTA `:386-392` (`fa-claim.open-sleeper`, disabled while the bid is over budget) → `openSleeper` `:152-165` → `:158-164` `openInSleeperApp({ target: 'add', leagueId, playerId: row.player_id, clipboardText: row.name, surface })`.
  7. `sleeperHandoff.ts:95-106` → `:100` `sleeperAppUrl(t)` `:79-91`: `:83` keeps L only if numeric, `:84` keeps P for `add`; `:85-89` walks `SLEEPER_PROVEN_RUNGS.add` = `['bare']` (`:39`) → `rungUrl('bare')` `:71-72` → `sleeper://`. `:102` `surface: 'free_agents'`; `:103` `appMissing: 'alert'`.
  8. `openExternal.ts:70-81` `openPlatform`: `:71` no open in flight → `:72` `attempt`; `:78` 2 s lock release; `:79` release on settle.
  9. `attempt` `:83-96`: `:84` `copyText(row.name)` **before** any open (commit 1: no `clipboardText`, nothing copied); `:86` `opened('sleeper://')` → `:100-107` → `:102` `await Linking.openURL`.
  10. RN 0.81.5 `RCTLinkingManager.mm:90-99`: Sleeper handles the scheme → `resolve(@YES)` → `'app'` → `openInSleeperApp` returns `'app'` (`sleeperHandoff.ts:105`). Sleeper opens on its last-viewed screen (bare rung). No Safari.
  11. Not installed: `RCTLinkingManager.mm:111` rejects "Unable to open URL" → `opened` returns `false` (`openExternal.ts:104-105`) → `:87-90` the D2 alert (`showAppMissing` `:110-126`: "Sleeper isn’t installed" / **Cancel** · **Get Sleeper**) → `'fallback'` → `'not_installed'`. https is never tried. **Get Sleeper** (`:118-121`) opens `https://apps.apple.com/app/id987367543`; if that rejects too, "Couldn’t open that link".

  **B. Usage Trends → Add → claim sheet → CTA**
  1. Entry: a card/row Add (`UsageTrendsScreen.tsx:382`, `:407`, the focused league) or the availability sheet's per-league Add (`:674`, any league) → `doAdd` `:285-295`.
  2. `:286` `trackAction('add')` (unchanged) → `:287` `resolveAddPlatform(lgId)` → `:290` non-Sleeper `explainNoAdd` (unchanged, S9) → `:293` `switchTo(lgId)` (`:228-242`; a non-focused league goes through `switchLeague` at `:236`, so the session league becomes the claim league) → `:294` `setClaim({ target, leagueId: lgId })`.
  3. Mount `:679-692`: `leagueId={claim.leagueId}`; `:684` `leagueName` = the claim league's own name from `leagueMeta` (`:151`, the session's league list), else the session `league_name` (`:95`) only when `claim.leagueId === leagueId` (`:94`), else `null`; `:685` `surface="usage_trends"`. `faQuery` (`:135-141`) loads that league's capacity, waivers and drop candidates.
  4. Then A4–A11, with `surface: 'usage_trends'`. The steps block names the claim league, which for a non-focused league is the one FTF just switched to.

  **C. Non-Sleeper invariance.** `ClaimSheet.tsx` `resolveAddPlatform`, `NO_ADD_REASON` and `explainNoAdd` (`:59-104`): no content change (S9). Free Agents' `onAdd` and Usage Trends' `doAdd` are unchanged.

- [x] **Manual TestFlight checklist** (for the operator, on the build that carries this branch; adapted from #351 PRD rows 13, 14 and 16). Run the commit-1 variant if commits 2 and 3 are dropped, the steps variant if they ship. Rows 6–9 are the steps variant at commit 3 (numbered rows; adapted from PRD rows 13/14); row 10 is new at commit 4. Rows 6 and 7 gained a step each from ux-lead's flow re-check (2026-10-28, via head-eng).

  | # | Sleeper app | Steps | Expected |
  |---|---|---|---|
  | 1 | installed, signed in, **2+ leagues**; in Sleeper open league **M** last, then swipe Sleeper away | FTF on league **L** (not M) → League → Free agents → **Add** on a player → claim sheet → **Open in Sleeper to claim** | The **Sleeper app** opens directly: no Safari, no "Open in Sleeper?" prompt. At the bare rung it lands on whatever Sleeper last showed, so **expect league M, not L**. Record the landing screen. **Commit-1 variant:** nothing on the sheet names the league; the user has to switch to L in Sleeper themselves. |
  | 2 | as 1 | Usage Trends → a player → the availability sheet → **Add** in a league **other than** FTF's focused one | FTF switches to that league, then the claim sheet opens. The CTA opens the Sleeper app as in 1 (last-viewed league, not necessarily the claim league). |
  | 3 | **not installed** (Settings → General → iPhone Storage → Sleeper → Offload App) | Free agents → Add → CTA | Alert "Sleeper isn’t installed" with **Cancel** / **Get Sleeper**. **Get Sleeper** opens the **App Store app** on Sleeper's listing, with no Safari. **Cancel** returns to the sheet and opens nothing. Never a silent no-op. |
  | 4 | installed | Free agents → Add → **double-tap** the CTA fast | Exactly one app switch. |
  | 5 | — | An ESPN or MFL league → Free agents → **Add** | Unchanged: the "Can't add in ESPN leagues yet" / "Can't add in MFL leagues yet" alert. No sheet, no link. |
  | 6–14 | — | **Removed 2026-11-01.** The steps block, the copy line and the pinned footer are gone (operator: no in-app instructions). Rows 1–5, the commit-1 variant, are the checklist. | — |

- [ ] **WAIVED because:** n/a, not waived.
- `testID`s added/renamed: commit 1 none (`fa-claim.open-sleeper` kept); commit 2 adds `fa-claim.steps`; commit 3 adds `fa-claim.step.league` / `.search` / `.add` / `.drop` / `.bid`; commits 4 and 5 none. `bash scripts/testid-lint.sh` → `testid-lint OK` at all five.

**Commands run** (from `mobile/`; this worktree has no `node_modules` (G-022), so the guards ran with `NODE_PATH` pointed at another checkout's `mobile/node_modules`, at the same `package-lock.json`):

| Command | Result |
|---|---|
| `node tests/check-sleeper-handoff.js` | 68 PASS, 0 FAIL at commit 1; 75 PASS, 0 FAIL at commit 2 (+7 S8); 85 PASS, 0 FAIL at commit 3 (S8 rewritten, 17 checks); 87 PASS, 0 FAIL at commits 4 and 5 (S8 19 checks; commit 5 is copy only) |
| `node tests/check-external-links.js` | 46 PASS, **4 FAIL, all pre-existing at `04eae95b`** (main's #360 added a `FeedbackSheet` mailto and removed three `SettingsScreen` links; the merge didn't update the LEGACY list). Not in this change's files. Before this change: 47 PASS, the same 4 FAIL. At commits 3, 4 and 5, after the #379 ratchet-fix merge (`a935304e`): 48 PASS, 0 FAIL. |
| `node tests/check-usage-trends.js` | 76 PASS (§2i/2j, the shared ClaimSheet), at commits 2, 3, 4 and 5 |
| `node tests/check-home-destinations.js`, `check-league-drill-in.js`, `check-picker-pick-filter.js` (the other guards that read `FreeAgentsScreen`) | all pass |
| `node tests/check-send-button-platform.js`, `check-trade-text.js` | all pass (`check-send-button-platform.js` 32 PASS at commits 3, 4 and 5) |
| every `tests/check-*.js` (121), at commit 2 | 119 pass in the worktree. The two others: `check-external-links.js` (the 4 pre-existing failures above) and `check-offer-prefill-330-unit.js`, which requires `mobile/node_modules/zustand` by absolute path, so it can't run here; on the scratch copy with `node_modules` linked it passes 14/14 |
| `bash scripts/testid-lint.sh` | `testid-lint OK` |
| `tsc --noEmit` | exit 0 at commits 1, 2, 3, 4 and 5, run on a scratch copy of `mobile/` with a borrowed `node_modules` (same lock file). CI is the gate. |

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
| `docs/integrations/sleeper.md` | **updated** | §1.3: the ClaimSheet row (was "Deep link (legacy, league-eng)", https) now describes the `openInSleeperApp({ target: 'add' })` call, its two hosts and surfaces, and the last-viewed-league risk. Commit 2 adds the clipboard copy and the steps block to that row. Commit 3 updates its line refs and describes the numbered steps. Commit 4 shifts two line refs (the CTA `:386-392`, the steps block `:327-384`). |

## 5. Ship gate declaration

- **CI green:** local equivalents above, except `check-external-links.js`'s 4 pre-existing failures, which make the `mobile-typecheck` job red on #379's tip as well. Someone has to fix them before either branch merges (owner: platforms-eng, #379's builder, or the LEGACY owners). Not pushed; CI hasn't run. Update 2026-10-28 (commit 3): the `a935304e` merge brought #379's ratchet fix, and `check-external-links.js` is 48 PASS, 0 FAIL on this branch.
- **Evidence recorded:** this file. A `living-memory/TEST_LEDGER.md` entry is **pending for the coordinator** (shared doc, G-022) and required before merge.
- **TestFlight verification:** checklist in §3; the operator runs it, and the outcome goes in TEST_LEDGER.
- **Merge gate (from #379):** #351 device tests R0, 1–12 and T1–T4 recorded in `docs/plans/sleeper-fa-deeplink/device-results.md`. Test 3 (`sleeper://` registered) is go/no-go.
- Express lane declared by the operator? **No.** Full gates.

## 2026-10-28 — design-lead review

design-lead reviewed commit 2: **approve with 4 changes**. Commit 3 implements them as stated, with no new tokens and no other visual change (one ice primary).

1. **A numbered list, not an arrow chain.** A `TickLabel` heading "IN SLEEPER" (from `./chalkline`), then one row per step: the number in Plex Mono `data` chalk-dim, then `body-sm` chalk-dim text. Names (league, player, drop) keep `stepsEm` (Archivo 600, chalk). `space.xs` between rows; no hairlines, no card.
2. **Rows at the `bare` rung**, in order, numbered without gaps: (1) "Open **{leagueName}**", always first and never omitted, because bare reopens the last-viewed league, with a fallback when the name is null; (2) "Players, then search **{row.name}**"; (3) "Add"; (4) "Drop **{dropName}**" when a drop is picked, "Drop: pick a player above" (chalk-dim, not a warn colour) on a full roster with no pick, omitted when the roster has room; (5) "Bid **${bid}**" in FAAB leagues once a bid is entered, because the bid doesn't carry over to Sleeper. testIDs `fa-claim.step.league` / `.search` / `.add` / `.drop` / `.bid`; the block keeps `fa-claim.steps`.
3. **The clipboard line** ("We'll copy {Name} so you can paste it into search.") stays the block's last line, directly above the CTA, in `sectionHint`. Unchanged.
4. **Copy:** step verbs must eventually match Sleeper's real button labels from the #351 device label capture (§7.3, not recorded yet), and the words are marketing's. The block carries `COPY: draft, pending marketing + Sleeper label capture (#351 §7.3)`; the null-league fallback carries its own pending-marketing marker. `clipboardText: row.name` stays on the CTA.

A later SHOULD from the same review, the empty drop list, is commit 4: see [Copy for design-lead](#copy-for-design-lead). The strings quoted above are the review-time drafts; the final ones are marketing addendum 12 (commit 5).

## Copy for design-lead

Commits 3–5. **Final per marketing addendum 12** (2026-10-29, `docs/plans/org-bringup/leads/marketing-lead-copy.md` §6, replacing addendum 10 item 9; via head-bizops → head-eng). It needs no legal stamp and no operator ask. Only the verbs still wait on the #351 §7.3 Sleeper label capture. Bold = `stepsEm` (`fonts.uiSemi`, `chalk.base`) inside the row's `body-sm` chalk-dim text; numerals are `data` chalk-dim. Final strings:

| Row | Shown when | Final string |
|---|---|---|
| heading | always | IN SLEEPER |
| 1 | `leagueName` known | Open **{League}** |
| 1 (fallback) | `leagueName` null or empty | Open the league you're claiming in |
| 2 | always | Go to Players, then search **{Name}** (commit 5 added "Go to ", so every row starts with a verb) |
| 3 | always | Add |
| 4 | a drop is picked | Drop **{Drop}** |
| 4 | full roster (`openSlots === 0`), nothing picked, a drop list to pick from | Drop: pick a player above |
| 4 | full roster, nothing picked, an empty drop list (`candidates.length === 0`; commit 4) | Drop a player to make room (marketing picked it over "Drop: choose a player in Sleeper") |
| 4 or 5 | FAAB league, a bid entered (5 after a drop row, else 4) | Bid **${bid}** |
| copy line | always, last, above the CTA | Opening Sleeper copies {Name}, so you can paste it into search. (commit 5; no "we" in system copy, and it says when the copy happens) |

As rendered (a scratch render of the component under node at commit 3, with row 2 updated to commit 5's string):

| Case | Rows |
|---|---|
| league known, full roster, drop picked, FAAB bid 5 | 1 Open **Dynasty Degenerates** · 2 Go to Players, then search **Jalen Tolbert** · 3 Add · 4 Drop **Tyler Boyd** · 5 Bid **$5** |
| league null, roster has room | 1 Open the league you're claiming in · 2 Go to Players, then search **Jalen Tolbert** · 3 Add |
| league known, full roster, no drop picked | 1 Open **Dynasty Degenerates** · 2 Go to Players, then search **Jalen Tolbert** · 3 Add · 4 Drop: pick a player above |
| league known, room, FAAB bid 12 | 1 Open **Dynasty Degenerates** · 2 Go to Players, then search **Jalen Tolbert** · 3 Add · 4 Bid **$12** |

Every case ends with the copy line ("Opening Sleeper copies Jalen Tolbert, so you can paste it into search."). The bid renders with the budget line's `toLocaleString('en-US')` formatting (a typed "05" shows as "$5").

Still open:
- The verbs ("Players", "search", "Add", "Bid") must match Sleeper's real labels from the #351 device label capture (§7.3). Marketing pre-approved the swaps, for league-eng to make once the capture exists, with no re-route:
  - Sleeper uses another word: use Sleeper's word in that row, in sentence case.
  - Sleeper uses one word for free agents and another for waiver players: row 3 reads both, free agents first (`Add or claim`).
  - Sleeper shows only an icon: keep the word here.
  - Anything else goes back to marketing.
  - No capture by 11-03: marketing's words stand, and design-lead decides whether the unconfirmed verbs ship.
- Closed by commit 5 (marketing addendum 12): the words. "Claim in {League}", the fallback line for the off 11-03 revert, is retired.
- Closed by commit 3: the missing-league degrade (now the fallback row), the bid (now a row), and VoiceOver reading "→" as "right arrow" (no arrows left; each row reads as one element).
- Closed by commit 4: a full roster whose drop list is empty (every player untouchable, or none droppable) said "Drop: pick a player above" with no one listed above. design-lead's ruling (review 2026-10-28, a SHOULD): keep the drop row, since the user still has to drop someone in Sleeper, and change only the words, to "Drop a player to make room". Chalk-dim like every row; no new style, no warn colour. Marketing kept "Drop a player to make room" (addendum 12).

## 2026-11-01 — pinned CTA footer

**Finding** (design-lead, 2026-11-01). On an iPhone SE (375×667), in a FAAB league with a full roster, a drop picked and a $12 bid, the sheet's content is 648pt against `maxHeight: '85%'` (567pt). The CTA starts about 35pt below the visible sheet. Main's sheet, without the steps block, is 460pt. design-lead missed this in their 10-28 review.

**Fix** (design-lead's spec, with ux-lead's two conditions). The operator's design review runs in parallel and doesn't block the merge:
- The CTA (`fa-claim.open-sleeper`) and its footnote move out of the `ScrollView` into a fixed footer (`fa-claim.footer`) under it, inside the sheet's `SafeAreaView`. The footer is ink-2, with a 1px `ink.line` top border, padding 12/16/16 and a gap of 8. The `ScrollView` keeps the header, bid, drop list and steps, and the sheet keeps `maxHeight: '85%'`.
- **ux-lead 1:** the content sits in a `KeyboardAvoidingView` (`padding` on iOS), so the footer rises above the bid field's number pad. `keyboardShouldPersistTaps="handled"` stays, so one tap on the CTA works with the pad up. Without this, a tap above the sheet would hit the backdrop, which closes the sheet and loses the picks.
- **ux-lead 2:** `flashScrollIndicators()` runs when the sheet opens, so the steps under the footer read as scrollable.
- No change to the CTA's label, `onPress`, disabled logic, testID or the footnote text.

**Two choices made while building, both following existing code:**
- **The `KeyboardAvoidingView` is the outer wrapper** (`kav: { flex: 1, justifyContent: 'flex-end' }`, `pointerEvents="box-none"`), like every other sheet in `mobile/src` (FeedbackSheet, RankImportSheet, MflSignInSheet, LinkSleeperSheet and others).
  - RN 0.81.5's padding is `frame.y + frame.height − keyboard.screenY` with `frame` relative to its parent (`KeyboardAvoidingView.js:110`, `:129`). A KAV inside the bottom-anchored sheet would leave the footer about 100pt under the number pad on an SE.
  - The sheet therefore drops its `position: 'absolute'` bottom anchoring, since the KAV places it, and keeps `maxHeight: '85%'`.
- **`flexShrink: 1` on the sheet's SafeAreaView** (`sheetBody`), so the ScrollView shrinks and the footer stays on screen. This is from the Yoga layout rules, not a device run.

**Evidence** (`ClaimSheet.tsx`):
- `FLASH_DELAY_MS = 400` (`:109`). The effect is at `:145-149`, `useEffect(…, [])`, and runs once per open, after the roughly 300ms slide-in.
- KAV at `:190`, ref at `:199`, `keyboardShouldPersistTaps="handled"` at `:201`.
- `</ScrollView>` is at `:406`, after the steps. The footer `fa-claim.footer` is at `:411` (style `footerBar` `:575`: ink-2, a 1px `ink.line` top border, `space.md`/`space.lg` padding, `gap: space.sm`). The CTA and footnote are unchanged.

**Guard P1** (`check-sleeper-handoff.js`, structure only):
- (a) exactly one `fa-claim.footer` View;
- (b) the CTA is inside it and inside no ScrollView;
- (c) the footer comes after `</ScrollView>`, both as direct children of the SafeAreaView;
- (d) the footnote is inside the footer, verbatim;
- (e) the ScrollView and the footer share a KAV with `padding` on iOS;
- (f) the ref comes from `useRef`, and `flashScrollIndicators` is called once from a `[]`-deps `useEffect`;
- (g) `keyboardShouldPersistTaps="handled"`.

S2 and S8 needed no rule change.

| Command | Result |
|---|---|
| `node tests/check-sleeper-handoff.js` | 94 PASS, 0 FAIL (87 + P1a–g) |
| `check-external-links` / `check-usage-trends` / `check-send-button-platform` | 48/0, 76/0, 32/0 |
| `bash scripts/testid-lint.sh` | OK (new testID `fa-claim.footer`) |
| `tsc --noEmit` (scratch copy, shared `mobile-deps` install) | exit 0 |
| `git merge-tree` with `2eb1bf83` then `512ee3f8` | ClaimSheet and the guard merge cleanly (`hasDrop` kept). `2eb1bf83`'s only conflict is `mobile/tests/README.md`, the same as on the unmodified head, and it goes away once #509 takes main with #528 |

| # | Sabotage | Red |
|---|---|---|
| 1 | CTA back inside the ScrollView | P1b |
| 2 | Footnote left in the ScrollView | P1d |
| 3 | Footer View removed | P1a–e |
| 4 | KAV removed | P1e |
| 5 | `flashScrollIndicators` removed | P1f |
| 6 | `keyboardShouldPersistTaps` removed | P1g | TestFlight rows 11–13 are above. The render is design-lead's before/after, pane 4 (`renders/claim-sheet-se-before-after.png`).

## 2026-11-01 — operator removes the in-app steps

**Decision** (operator, design review, 11-01, via head-product and head-eng, verbatim): "For free agents the instructions should not exist. The expectation is the we create the transactions on behalf of the user."

**What #509 keeps:** commit 1. "Open in Sleeper to claim" calls `openInSleeperApp({ target: 'add', leagueId, playerId: row.player_id, surface })`, with #379's "Get Sleeper" fallback, instead of the old silent `sleeper.com` link. It also keeps `surface` on both hosts, Free Agents' `isError`-before-`isLoading` order, and the byte-identical non-Sleeper paths (S9).

**What's removed:**
- commits 2–6: the "In Sleeper" steps block, marketing's step copy (addenda 10 and 12), the empty-drop-list string, and the pinned CTA footer with its keyboard and scroll handling;
- the `clipboardText: row.name` copy, since copying without the on-sheet disclosure is out (#351 PRD §4.2);
- the `leagueName` prop, which existed only for step 1 and was never rendered (removed from `ClaimSheet` and both mounts).

The drop picker and bid predate #509 and stay.

**Guards:**
- S8 and P1 are removed.
- **S2 (ClaimSheet half, continued)** pins the operator's decision: no `clipboardText` on the hand-off (a spread also fails), no steps or footer testIDs, and no `KeyboardAvoidingView`. S10 was already taken by the `SLEEPER_PROVEN_RUNGS` check.
- H1 keeps its `surface` half.

**What follows:**
- **D1** (platforms-eng is sizing it for launch): the app submits the add/drop/claim itself, and the CTA submits instead of handing off.
- `hasDrop` (`2eb1bf83`, needs #528) still applies: the drop picker remains, and `sleeper_handoff_resolved` stays useful until D1.
- The S9 re-baseline (`512ee3f8`) still applies.

**Evidence** (from `mobile/` with the shared `mobile-deps` install):

| Check | Result |
|---|---|
| `check-sleeper-handoff` | 69 PASS / 0 FAIL (S8 and P1 removed; S2-continued adds 3) |
| `check-external-links` / `check-usage-trends` / `check-send-button-platform` | 48/0, 76/0, 32/0 |
| `check-league-drill-in` / `check-picker-pick-filter` / `check-trade-first-card-events` | 29/0, 38/0, 43/0 |
| `testid-lint` / `tsc --noEmit` | OK / exit 0 |

`ClaimSheet.tsx` equals commit 1 (`a696a809`) minus the never-rendered `leagueName` prop.

Sabotage:
- `clipboardText` back: red.
- a `fa-claim.steps` View back: red.
- `surface` dropped from Free Agents: red.
- `leagueName` re-added: green, as expected (harmless).

**Cherry-picks:** both still apply, but they now conflict, and the resolutions are known.
- `2eb1bf83` (hasDrop): the call becomes one line with `hasDrop: dropId != null`. Two guard header lines join, and H3's block goes above S2-continued. README takes #509's line.
- `512ee3f8` (S9): the guard header region becomes S2's lines plus S9's new lines.

**Superseded:** the design-lead review, Copy for design-lead, and pinned CTA footer sections below record history only.

## Known risk

At the `bare` rung Sleeper reopens its **last-viewed league** (PRD C2), not the claim league. A user with several Sleeper leagues can land in the wrong one and add the player there. The old https link had the same end state on iPhone (Safari → Sleeper's home, #351 F3), so this is not a regression, but it is not fixed either. **Without commits 2 and 3, nothing on the sheet tells the user which league to pick.** The steps block's row 1 names the league, or tells the user to open the league they're claiming in when the name is unknown. A deeper rung (`players_tab` or `league`) fixes it only once a device test proves Sleeper honours the league path.
