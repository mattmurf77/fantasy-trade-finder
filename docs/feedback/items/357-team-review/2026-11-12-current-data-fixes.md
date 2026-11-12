# Team Review against the current engine — scope addendum (2026-11-12)

**Date:** 2026-11-12
**Entry point:** direct ask — an audit of Team Review against `origin/main` at `5053441c` found eight things the trade engine had moved past since August; operator: "Yes, fix them".
**Builder:** builder agent, branch `fix/team-review-current-data` (worktree `.claude/worktrees/team-review-fixes`)
**Operator sign-off on waivers:** not needed. One waiver (§1 analytics: no new event) follows the brief's own rule.
**Express lane:** no. All four gates apply.

Out of scope and untouched: the Depth beat's thin / deep analysis, the Divergence beat's inputs, the entry card's placement, and any merge of Team Review with Roster setup.

---

## 0. The eight fixes

| # | What was wrong | What it does now | Where |
|---|---|---|---|
| 1 | Partners' "N firsts" matched `"1st"` in the pick label, so `2026 1.08` and `2027 1.02 · projected` counted as zero. | Counts picks whose numeric `round` is 1. | `backend/server.py` `_first_round_pick_count`, used at `first_rounds[uid]` in `league_team_review_route` |
| 2 | The Standing beat showed a Likely / Toss-up / Unlikely band from the `outlook.odds` simulator while Home, Standings and the next beat read the saved weekly forecast. | `standing.playoff_chance` = the saved forecast's chance for the viewer (`{playoff_probability, captured_at, current}`), shown whenever Home shows a percentage, one decimal, "Last saved <date>" when not current. No usable forecast ⇒ no playoff line. `standing.outlook` is no longer sent. The band is still computed: it still feeds the window inference. | `backend/league_projections/recommendation.py` `saved_chance` / `load_chance`; the route's tail; `TeamReviewScreen.tsx` `Standing`, `playoffChanceLine` |
| 3 | Team Review had its own outlook names (Contender / Rebuilder / Full teardown). | Uses `OUTLOOK_DISPLAY_NAME` (All-in, Contending, Rebuilding, Tanking, Not sure) everywhere. Under the outlook choices, one line per outlook with rules of its own, in the rule catalog's names: today only Tanking ("Tanking teams keep next pick; Tanking teams skip older RBs; Tanking teams keep young favourites"). All-in has no rule in the catalog, so it gets no line. No server sentence carried the old names. | `backend/rule_catalog.py` `outlook_rule_names`; `window.outlook_rules`; `TeamReviewScreen.tsx` `OUTLOOK_LABEL`, `outlookRuleLines` |
| 4 | After Confirm, later beats used the first fetch (60 s cache, never invalidated). | Every landed save invalidates `['team-review', leagueId]`; TanStack refetches in the background and keeps the cached payload on screen (the spinner branch is `q.isLoading`, first load only), so the current beat never reloads. | `TeamReviewScreen.tsx` `savePrefs` |
| 5 | A Chase / Shop save with no saved outlook also wrote `team_outlook` = the roster read, turning an inferred outlook into a declared one. | Positions saves send no `team_outlook`. `POST /api/league/preferences` accepts a positions-only body and leaves the stored outlook untouched; with no row yet it stores `""` (`database.UNSAVED_OUTLOOK`, the NOT NULL column's "nothing declared"), which both loaders return as `None`. Every body that sends an outlook behaves as before. The plan beat's outlook chips show no selection when nothing is saved and its positions taps send no outlook. | `server.py` `set_league_preferences`; `database.py` `upsert_league_preference`, both loaders; `TeamReviewScreen.tsx` `savePrefs`, `Plan` |
| 6 | The Plan beat's player rules card: no Move list, Keep called "Never trade away", a hint to tap names on cards, a claim of "every dial the finder has", nothing on what Not interested does. | Keep and Move (the trade block, behind `trades.roster_setup`) counts; a "Set Keep and Move in Roster setup" link (`team-review.plan.roster-setup`) opens `RosterSetup {entry:'manual_dna'}`, the Trade DNA row's route and params; the bubble reads "Here's what the finder takes from you, and where you stand on each."; "Not interested makes a player less likely to be offered to you. It does not block him." (the founders' review finding in `docs/plans/founder-review/rule-waterfall-design.md`: a preference on owner decks, not a hard rule). With `trades.roster_setup` off: no Move row, no link, and the old "tap a name on any trade card" hint, which is then true. | `TeamReviewScreen.tsx` `Plan` |
| 7 | "This steers every trade we show you" under a forecast suggestion the engine does not use until Confirm. | Three states, one line each: saved ("Your saved outlook is X. Every trade we show you uses it. Pick another and tap Confirm to change it."), nothing saved beside a suggestion ("Nothing is saved yet. This is only a suggestion: until you tap Confirm, trades use our read of your roster instead."), nothing saved on the roster read ("Nothing is saved yet. Until you tap Confirm, trades use our read of your roster."). The copy does not name the engine's read: it is `_infer_user_outlook`'s four-argument roster heuristic, which can differ from the composite / odds verdict this beat shows. | `TeamReviewScreen.tsx` `windowSaveLine`, `team-review.window.save-state` |
| 8 | A Team Review save never set Find a Trade's "Preferences changed" state. | A landed save posts `state/teamReviewSaveBus`; TradesScreen consumes it on focus and does what a Trade DNA close does: marks the deck stale and, under the same rule (`prefsChangedStripVisible`, now shared by both), shows the strip. Never regenerates. Finish with a scoped partner drops the note (its hand-off search is fresh). | `teamReviewSaveBus.ts`; `TradesScreen.tsx` focus effect + `handleEditSheetClose` |

### Fix 8, traced (what happens on return)

Before: `savePrefs` invalidated only `['league-prefs']`. The server dropped the cached deck (`_invalidate_trade_jobs`), but TradesHome (mounted beneath the pushed review) kept its `deck` state and nothing set `prefsChangedSinceGenerateRef`, which only `TradeDnaSheet`'s `onAnyChange` and the sheet's intent / opponent handlers set.

After (`mobile/src/screens/TeamReviewScreen.tsx`, `mobile/src/screens/TradesScreen.tsx`):

1. **Finish with a partner picked.** `savePrefs` posted the note after each landed write (`TeamReviewScreen.tsx:224-238`). Finish clears it (`:383`) and arms the #330 hand-off with `autoRun` (`:395-399`); TradesHome's hand-off effect (`TradesScreen.tsx:3773` onward) runs a fresh search for that partner under the saved preferences. No strip: it would describe a deck that is already fresh.
2. **Finish without a partner.** `nav.navigate('TradesHome')` (`TeamReviewScreen.tsx:413`) focuses TradesHome; the focus effect (`TradesScreen.tsx:6271-6279`) consumes the note, sets `prefsChangedSinceGenerateRef.current = true` and shows the strip when `prefsChangedStripVisible(consolidateOn, deck.length, job?.status)`, the rule `handleEditSheetClose` uses (`:1335-1336`). Tapping the strip calls `handleFindTrades`, which clears both.
3. **Leaving early after a save** (back, header, tab bar): same focus path as 2.
4. **Nothing saved:** no note was posted (`noteTeamReviewSave` runs only after the awaited write resolves), so focus changes nothing.
5. A note for another league is discarded on consume (a league switch resets the deck anyway).

---

## 1. Analytics scope

- [x] **(c) WAIVED — no new event.** Saves already emit `team_review_action_taken` / `outlook_saved {source:'review'}`; the refresh strip's tap is the deck's existing Find a Trade path. The Roster setup link fires no event of its own and reuses the Trade DNA row's params `{entry:'manual_dna'}`, so `roster_setup_shown` attributes an open from Team Review as `manual_dna`. A distinct value (`team_review`) would be a new enum value for `entry` (taxonomy comment, `RosterSetupScreen`'s `Entry` type, `check-roster-setup.js`, the roster-setup analytics docs); not added here. No taxonomy change.

## 2. Schema & flag scope

- Tables / columns: none added. `league_preferences.team_outlook` gains a stored value, `""` = no outlook declared (rows created by a positions-only save). Documented in `docs/data-dictionary.md`. No migration: the column stays NOT NULL.
- Flags: none. Fix 2 rides `league.projections` (off in `config/features.json` today, so the standing beat shows no playoff line in production until it is lit); fix 6's Move row and link ride `trades.roster_setup` (on).
- Env vars / `model_config`: none.

## 3. Evidence scope

- [x] **Unit tests:** `backend/tests/test_team_review_current_data.py` (new, 23 tests): fixes 1 (round count with "2027 1st", "2026 1.08", "2027 1.02 · projected"; the route wiring by AST), 2 (`saved_chance` against Home's showable rule, the route ships `playoff_chance` and never `standing.outlook`, nothing without a usable forecast: flag off, ESPN, no run, read failure), 3 (catalog names, route field), 5 (positions-only with and without a saved outlook, both loaders, every old body shape, the 400s, the database guard).
- [x] **Structural guard:** `mobile/tests/check-team-review.js` — 10, 12b, 12e and 13a-c rewritten; 8 updated (Keep / Move, no "every dial"); 14-20 new (pure helpers `playoffChanceLine`, `outlookRuleLines`, `windowSaveLine` and the bus module are executed). `mobile/tests/check-no-beta-copy.js` p3: its positive control moved from the removed ribbon to the new "Playoff chance" card.
- [x] **Code-walk proof:** fix 8, above.
- [x] **Manual TestFlight checklist:** §6.
- `testID`s added: `team-review.standing.playoff-chance`, `team-review.window.save-state`, `team-review.window.outlook-rules`, `team-review.plan.outlook-unsaved`, `team-review.plan.roster-setup`. Removed: `team-review.beat.standing.outlook`, `team-review.standing.coverage`. `testid-lint` green.

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | updated | `POST /api/league/preferences` (positions-only body); `GET /api/league/team-review` (`standing.playoff_chance` replaces `standing.outlook`, `window.outlook_rules`, firsts by round) |
| `docs/data-dictionary.md` | updated | `league_preferences.team_outlook` (`""`) |
| `docs/cross-client-invariants.md` | updated | Outlook suggestion: Team Review's two percentages; Team Review uses the shared outlook names |
| `mobile/src/screens/CLAUDE.md` | updated | `TeamReviewScreen` row |
| `mobile/src/state/CLAUDE.md` | updated | `teamReviewSaveBus.ts` |
| `living-memory/LLD.md` | n/a here | the brief reserves `living-memory/` for the operator; a candidate LLD note: a positions-only preference save stores `""` for no outlook |
| `docs/architecture.md` / `living-memory/HLD.md` | n/a | no module wiring change |
| `docs/glossary.md` | n/a | no term changed ("Keep" / "Move" are roster setup's existing words) |
| ADR / `DECISIONS.md` | n/a here | operator writes living-memory; candidate decision: `""` as the NOT NULL column's "no outlook" rather than a nullable column (no migration on SQLite or Postgres) |

## 5. What installed builds (up to 1.22.0 (188)) see after the server deploys

| Fix | Build 188 after deploy |
|---|---|
| 1 | **Fixed** (server): Partners shows the right "N firsts". |
| 2 | **Partly**: the Standing beat no longer shows the Likely / Toss-up / Unlikely card (188 renders it only when `standing.outlook` is present, so no crash and no contradiction); it shows no playoff line at all, because 188 does not read `playoff_chance`. |
| 3 | Unchanged: 188 keeps its own names and ignores `outlook_rules`. |
| 4 | Unchanged. |
| 5 | **Not fixed for 188**: 188 still sends the backfilled outlook with every positions save, and the server cannot tell it from a real choice. |
| 6, 7, 8 | Unchanged (client only). |

## 6. Manual TestFlight checklist (new build, server deployed)

Use a Sleeper league. For steps 2-3 the flag `league.projections` must be on and the league must have a saved weekly forecast.

1. **Firsts.** In a league where a partner holds a slotted first (shown as "2026 1.08" on League rankings), open Team Review → Partners. That partner's "N firsts" counts it.
2. **Standing, forecast saved.** Home shows "Playoff chance 45.7%". Team Review → Standing shows "Playoff chance", "45.7%" and "From the forecast saved <date>." No Likely / Toss-up / Unlikely card. If Home says "last saved", Standing says "Last saved <date>."
3. **Standing, no forecast.** In a league with no saved forecast (or with `league.projections` off, or an ESPN / MFL league), Standing shows roster value and PPG and no playoff card.
4. **Names.** Window chips read All-in, Contending, Rebuilding, Tanking, Not sure; under them one line: "Choosing Tanking switches on: Tanking teams keep next pick; Tanking teams skip older RBs; Tanking teams keep young favourites." Partners and Plan use the same names.
5. **Window copy.** (a) League with a saved outlook: "Your saved outlook is <name>. Every trade we show you uses it. …" (b) No saved outlook, forecast suggestion on screen: "Nothing is saved yet. This is only a suggestion: until you tap Confirm, …" (c) No saved outlook, no suggestion: "Nothing is saved yet. Until you tap Confirm, trades use our read of your roster."
6. **Refetch after Confirm.** As a rebuilding team with nothing saved, pick Contending, Confirm. The Depth beat appears without a spinner. Skip to Partners: the heading reads "Rebuilding teams — they want picks, you want players" and the list is rebuilding teams.
7. **No silent outlook.** In a league with NO saved outlook: Window → Skip; Depth → toggle Chase WR → Save & continue. Go to Find a Trade → Trade DNA: the outlook is not set ("Not set" / the inferred prompt still shows). On the Plan beat, no Window chip is selected and "Not saved. …" shows; tapping a Chasing chip keeps it that way.
8. **Plan card.** Player rules shows Keep, Move, Targeting, Not interested in, the Not interested line, and "Set Keep and Move in Roster setup". Tap it: Roster setup opens; back returns to the Plan beat.
9. **Refresh strip.** With a deck on screen in Find a Trade, open Team Review, save something (Confirm or Save & continue), then (a) back out early, or (b) Finish without picking a partner. Find a Trade shows "Preferences changed — tap to refresh" and the old deck stays until you tap it. (c) Repeat but pick a partner on Partners and Finish: a search for that partner runs and no strip shows. (d) Open Team Review and leave without saving: no strip.
10. **Trade DNA unchanged.** Change the outlook in the Trade DNA sheet and close it: the strip shows exactly as before.

## 7. Ship gate

- CI: `pytest backend/tests`, `tsc --noEmit` + every `check-*.js`, `testid-lint` — results in the build report.
- Evidence to log in `living-memory/TEST_LEDGER.md` (operator).
- TestFlight checklist §6 run by the operator on the next build.
