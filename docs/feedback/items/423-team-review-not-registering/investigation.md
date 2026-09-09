# G-423 investigation — #423 (team review "didn't register") + #424 (outlook "Not set")

Date: 2026-09-08. Planner read-only code-walk on branch `claude/feedback-422-428` (worktree `open-feedback-summary-b43796`). Line numbers are this tree's; build agents re-cite after editing.

## 1. Timeline reconstructed from Render (user 313560442465169408, 2026-09-06 UTC)

| Time | Server saw | Client action it maps to |
|---|---|---|
| 17:55:52–17:56:21 | team-review GET + 3× `POST /api/league/preferences` for FFV3 (`…497408`), all 200 | Ran the review on FFV3 |
| 17:56:40 | league meta reads for Lakeview (`…050048`) | League switch FFV3 → Lakeview (`useSession.switchLeague`, `useSession.ts:444-491`) |
| 17:56:47 | `GET /api/league/team-review?league_id=…050048` 200 | First TeamReview mount on Lakeview (`TeamReviewScreen.tsx:117-122`, staleTime 60 s) |
| 17:57:01 → 17:58:47 | 12× prefs POST, all 200; outlook contender → rebuilder; positions alternate `acquire=None away=None` and `['WR','TE']` | Outlook-only bodies = the **window** beat's Confirm (`:264-275` posts `{team_outlook}` only). Full triples = **depth** Save & continue (`:276-290`) or **plan**-beat chip taps (`:1078-1089`, always the full triple) |
| 17:58:00 | second team-review GET | Second mount — 73 s > 60 s staleTime, so the user re-entered the review (entry row "Run team review again" or Start) |
| 17:58:47 | last POST `outlook=rebuilder acquire=['WR','TE'] away=[]` **immediately followed by** `GET /api/league/preferences` 200, 158 B | The only invalidation inside the review is the plan beat's `commit` (`:1088`) — so the user was ON the plan beat and changed outlook there. The GET is the refetch of the shared `['league-prefs', '…050048']` key |
| 17:59:16 / 17:59:28 | feedback #423, #424 from screen TradesHome | User is back on the Acquire landing within 30 s |
| 18:05:36 | prefs GET, 158 B again | Same content — server unchanged |

**What 158 bytes means.** `get_league_preferences` (`backend/server.py:19728-19796`) returns the 4-key row plus `position_needs`/`position_surplus`; Flask compact JSON + newline for `{"acquire_positions":["WR","TE"],"avoid_positions":[],"team_outlook":"rebuilder","trade_away_positions":[]}` is 108 B, and 158 B is exactly one one-item need + one one-item surplus (e.g. `["QB"]`/`["WR"]`). A **null** outlook would instead carry `inferred_outlook` + `inferred_signals` (a dict) and be far larger. So at 17:58:47 both the server **and the client's react-query cache** held `team_outlook: "rebuilder"` for Lakeview. Whatever showed "Not set" 29 s later was not reading that cache.

## 2. #424 — the "Not set" the operator saw is a hardcoded string

Which outlook surface renders on the Acquire landing under production flags:

1. `trades.finder_hub` **true** (`config/features.json:14`) → `TradesHome` gets `initialParams {mode:'guided'}` (`TabNav.tsx:453-460`) → `finderMode === 'guided'` (`TradesScreen.tsx:931-933`).
2. `calc.inline_home` **true** (`:95`) → `canvasHost === 'flag'` (`TradesScreen.tsx:6083-6098`).
3. `trades.edit_full_sheet` **true** (`:230`) → `consolidateOn` (`TradesScreen.tsx:740, 984`) → the legacy controls card, including the "Outlook / Edit" row at `TradesScreen.tsx:7234-7250` (the L7241 "Not set"), sits inside `{!consolidateOn ? (` (`:7157`) and **never renders** here.
4. TradesHome's own `trades.outlook-fallback` row (`TradesScreen.tsx:6908-6952`, the L6915 "Not set", which #394 gave a real value mapping via `OUTLOOK_FALLBACK_LABEL` `:9837-9849`) is suppressed by the T-1 conjunct `canvasHost !== 'flag'` (`:6908`) — by design, so the hosted calculator's outlook section is the covering surface (comment `:6896-6907`).
5. TradesHome's own `<OutlookBiasReceipt>` (`:6870`) renders `null` (step 6).
6. The covering surface is `TradeBuildCanvas` (`TradesScreen.tsx:8006-8020`) → `InLeagueCalculator` (`TradeBuildCanvas.tsx:4`) → `calc.outlook-row` (`InLeagueCalculator.tsx:922-955`): an `OutlookBiasReceipt` plus a fallback shown when the receipt reports hidden.
7. `OutlookBiasReceipt.tsx:49-53` — `outlookReceiptCovers()` returns **false whenever `!directionOn`**; `:83-88` its prefs query is `enabled: directionOn && !!leagueId`; `:96-102` `hidden` → `onHiddenChange(true)`, render null. `trade.outlook_direction` is **false** in prod (`config/features.json:67`; also `docs/config-reference.md:232`, `:371`).
8. `InLeagueCalculator.tsx:317` `outlookHidden` ← true → `:925-931` renders the **literal** `Outlook · Not set`. `InLeagueCalculator.tsx` has **no** `['league-prefs']` query and never reads `team_outlook` (grep: zero hits).

So on the merged landing every user sees "Not set" regardless of what is saved. Not stale, not the wrong league, not a missed invalidation — the row has no data source at all.

**How it got here.** #384 W5 added the fallback as an "honest 'Not set'" for the flag-off receipt (`docs/feedback/items/384-calc-finder-merge/scope.md:97`, `status.md:150`) — honest only if "receipt hidden" implied "nothing declared", which the flag-off branch never did. #376/#394 fixed exactly this on TradesHome's twin (value mapping, "Not sure" for `not_sure`, "Not set" only for null — `376-finder-filters-regression/prd.md:41`), then T-1 (2026-08-28, `402-more-offers-shop/merged-view-trim-2026-08-28.md`) retired the *fixed* row on the flag path in favour of the *unfixed* calculator twin. #394 regressed by route.

**Secondary (latent, not this incident):** the review's window and depth beats write through `savePrefs` (`TeamReviewScreen.tsx:148-183`, callers `:264-290`) which never invalidates `['league-prefs']`; only the plan beat's `commit` does (`:1088`). A user who confirms the window beat and backs out before the plan beat leaves TradesHome's `prefsQuery` (`TradesScreen.tsx:1284-1290`, staleTime 5 min, no focus refetch — `queryClient.ts:29` `refetchOnWindowFocus:false`) stale for up to 5 minutes. Harmless today only because the row doesn't read it; it matters the moment the row does.

## 3. #423 — the marker is written on one button and read once per mount

**Write half.** `markTeamReviewCompleted(leagueId)` (`TeamReviewEntryCard.tsx:48-58`) is called from exactly one place: the plan beat's "Find my trades" `onPress` (`TeamReviewScreen.tsx:291-327`, call at `:324`). Leaving the review any other way — back gesture, header, tab bar, from any beat including the plan beat — never records completion. "Skip this" (`:336-340`) only advances. The operator's definition (2026-08-20, quoted `TeamReviewEntryCard.tsx:23-24`) is "once they've gone through it", which reaching the plan beat satisfies.

**Read half.** `TeamReviewEntryCard` reads `ftf_team_review_completed` once, in a `useEffect` keyed on `leagueId` only (`:70-83`). TradesHome stays mounted beneath the pushed TeamReview (both in `TradesStack`, `TabNav.tsx:455-460` + the TeamReview registration after `:483`), and the finish button's `nav.navigate('TradesHome')` (`:325`) pops to the *existing* instance — no remount, no re-read. So even the happy path shows the full "Start team review" card until relaunch or league switch. (`if (collapsed === null) return null` at `:96` is pre-hydration only and is fine.)

**Operator path.** The 17:58:47 invalidation proves the plan beat was reached. Whether "Find my trades" was tapped cannot be told from the log (no scoped partner → no auto-run request). Either way the card showed un-done on return; if they left via back, the marker was never written at all.

**Note on a focus-based re-read.** `useFocusEffect` in the card would work (nav context is present) but races the write: `void markTeamReviewCompleted()` is fire-and-forget (readMap → setItem, two awaits) and `nav.navigate` runs synchronously after it, so a focus re-read can land before `setItem` resolves. An in-memory store updated synchronously avoids the race.

## 4. Hypothesis ranking

| # | Hypothesis | Verdict | Evidence |
|---|---|---|---|
| **(e)** | The visible row reads no preference source — literal string | **#424 root cause** | `InLeagueCalculator.tsx:925-931`; receipt gate `OutlookBiasReceipt.tsx:49-53, 83-88`; flag `features.json:67`; host chain §2 steps 1-6 |
| **(c)** | Marker written only on "Find my trades"; read only on mount | **#423 root cause (both halves)** | `TeamReviewScreen.tsx:291-327`; `TeamReviewEntryCard.tsx:70-83`; stack `TabNav.tsx:455-460` |
| (b) | Review writes invalidate a key the row doesn't read | Partly true, not causal | Row reads nothing (e). Latent: window/depth writes don't invalidate at all (`:148-183`) — harden in the same change |
| (a) | Row refreshed only at session init | Ruled out | `seedLeagueSessionCaches` seeds only rosters/users (`queryClient.ts:55-66`); `['league-prefs']` is never seeded; the 17:58:47 GET refreshed it |
| (d) | League switch left the row bound to FFV3 | Ruled out | Key includes `leagueId` (`queryClient.ts:52-54`); TradesScreen and TeamReviewScreen both derive it from `useSession.league` (`TradesScreen.tsx:457`, `TeamReviewScreen.tsx:104-105`); switch happened at 17:56:40, before the review |

## 5. Guards in play (do not trip)

- `check-team-review.js` (13 green now): #6 needs `getLeaguePreferences` + `'league-prefs'` + `refetchOnMount` inside `function Plan(`; #7 no `done.current` in Plan; #10 **exactly one** `saveLeaguePreferences(` call site in the screen and its literal must lead with `team_outlook:` — add invalidation to `savePrefs`, never a second write site.
- `check-calc-merged-layout.js` #5: `calc.outlook-fallback` / `.change` testIDs must exist only inside the `merged ?` region — keep the fallback there.
- `check-finder-conditions-reachable.js` #2 pins the TradesHome row gate `consolidateOn && !outlookReceiptShown && !firstRun && canvasHost !== 'flag'` verbatim; `check-inline-home.js` #11 pins the T-1 conjunct. Do not touch that gate.
- CI runs every `mobile/tests/check-*.js` (`.github/workflows/ci.yml:47`), so a new guard is live on push.
