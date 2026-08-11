# mobile/src/screens/

One file per top-level route. MAP, not a changelog — present behavior only, no dated amendments. History: `git log -- <this file>` and `living-memory/CHANGELOG.md`.

| Screen | Purpose |
|---|---|
| `SignInScreen` | Apple sign-in is the primary entry (`auth.accounts`); Sleeper username is the fallback. `onboarding.landing` flips Sleeper to primary with a demo escape when Sleeper is down |
| `LeaguePickerScreen` | Pick which league to use; footer links open the ESPN/MFL/Fleaflicker league-linking sheets |
| `LeagueScreen` | Classic league home (pushed `LeagueHome` sub-route): hero identity, Matches tiles, Explore rows, activity, contrarian, coverage, leaderboards. Adds a progress module + action row while any unlock is outstanding, and a "Draft picks" section for ESPN leagues (flag `picks.assign`) |
| `RankHomeScreen` | Build-your-board chooser: Quick set / Trios / Tiers as primary cards, Anchors / Overall ranks / Trends behind a "More ways to rank" disclosure; optional rankings-import link (flag `ranks.import`); saves `rankingMethodPref` |
| `RankScreen` | 3-player swipe matchup loop (Trios), three-across mini player cards. Also the Rank tab's launch route once all four quick-tiers positions are complete |
| `TiersScreen` | Tiered roster view |
| `QuickSetTiersScreen` | Guided per-position tier walk (top→FA); default Rank-tab launch route for no-pref users, resuming at the next unset position |
| `QuickRankScreen` | Within-tier click-order ranking pass offered after Quick Set finishes |
| `PickAnchorScreen` | Pick Anchor wizard: value one player at a time in draft-pick terms, position scope pills; shares its rung grid with `AnchorSheet` |
| `ManualRanksScreen` | Editable drag/tap rank board, labeled "Overall Ranks" in the UI |
| `RookieRanksScreen` | Consolidated cross-position rookie board (flag `ranks.rookie_subset`), filterable by position; drag-reorder only — must never reach the tiers-save path; two-way bridge to/from Draft Room |
| `TradeFinderHubScreen` | UNROUTED since the guided-first landing shipped — kept in the tree, no navigator registers it. DNA editor moved to `TradeDnaSheet`; FA link superseded by the mode-bar chip |
| `TradesScreen` | Trade card browser and the `TradeDeck` route (`mode`: guided/team/player); also the Acquire tab's landing. Pin board, featured-trade window + asset-ideas list in single-pin mode, swap suggestions, per-asset edit/remove, mode-switch chip strip. Pass/Like live inside the top card (via `TradeCard`'s `disposition` prop), not below the deck (#169) |
| `TradeCalculatorScreen` | Manual trade builder — Live / In-league / Demo modes; optional `prefill` route param from a deck card's edit action; "Find a trade" link back to the finder |
| `MatchesScreen` | Mutual trade matches inbox; progress module + "Find a trade" CTA on the empty state |
| `SleeperConnectScreen` | WebView Sleeper login; captures the JWT for Send-in-Sleeper (beta) and doubles as account verification |
| `SettingsScreen` | Settings modal: leagues (+ ESPN link row), ranking pref, notifications, Account section (link/verify/delete), Trade Values stud-tax mode |
| `LeagueSummaryScreen` | League/power rankings — the League tab's root: per-team bar chart + ranked list, Consensus/My-board toggle, All/Starters/Bench subset, draft-capital section, inline drill-in roster. Also hosts the dark "Season outlook" section (flag `outlook.odds`): projected standings and playoff odds merged into one seed-ordered list — row order + cutline are the standings, a three-band chip is the odds; defaults to a collapsed one-line "your outlook" strip (per-league/user persisted, `state/outlookStrip.ts`) with the full section one tap away (#169 frame E) |
| `FreeAgentsScreen` | Free-agent finder: position-filtered best-available list by the caller's board values; per-row Add opens a claim sheet (Sleeper) or explains the missing write path (other platforms) |
| `DraftRoomScreen` | Read-only Draft Room (flag `draft.room`): picks/board/undrafted rookies, honest per-platform refusal states, deep link to the platform's draft room. Optional live polling (`draft.live_poll`), Mock-mode entry (`draft.mock`), inline rank/anchor actions (`draft.rank_inline`), ESPN assign-picks entry (`picks.assign`) |
| `MockDraftScreen` | FTF-native mock draft session (flag `draft.mock`): the user picks for their own team, CPU drafts the rest, nothing reaches the platform; persistent mode-marker rail distinguishes it from the real board |
| `PickAssignmentScreen` | ESPN pick-ownership grid (flag `picks.assign`): season tabs, one-time drag-order setup, collapsible rounds, optimistic-concurrency conflict sheet on a stale write. No value entry anywhere — prices are server-computed |
| `PlaceholderScreen` | Stub for unfinished routes |
| `TestStagesScreen` | Operator QA: spawn a synthetic adoption-stage user and swap this device into it; device-only factory reset (Settings → Testing, flag `testing.stage_users`) |
| `EspnConnectScreen` | WebView ESPN login (flag `espn.webview_capture`): captures `espn_s2`/`SWID` from native cookies and hands them back to `EspnLinkSheet`, which auto-advances |

## Sharp edges

- `RookieRanksScreen` must never call `/api/tiers/save` or the merged-band `apply_tiers` path — reorder only, pinned by `backend/tests/test_rookie_ranks_editable.py`.
- Pick-assignment surfaces never send a value field — prices are computed server-side from (round, years_out, format); the server 400s any value-shaped key.
- `DraftRoomScreen`, `MockDraftScreen`, `PickAssignmentScreen` register UNCONDITIONALLY — their flags gate the entry point, not the route, so a stale deep link lands on an honest unavailable state instead of 404ing.
- Root-stack pushes over `headerShown:false` Main tabs (FreeAgents, LeagueSummary, TestStages, PickAssignment, MockDraft, EspnConnect) need the explicit `HeaderBack` control — native back is dead on iOS 26 (RNS#3294).
- `MockDraftScreen`'s mode-marker rail must render outside the ScrollView and every conditional (`mobile/tests/check-mock-mode-marker.js`) — it lets the room safely omit "never drafts for you" copy in Mock mode.
- `LeagueSummaryScreen`'s Season outlook section is a calibration result, not a style: no raw percentages, no `title_pct` at any week, no win-loss numbers while `meta.beta` is true, and bands read from `docs/cross-client-invariants.md` § "Playoff outlook bands". Non-Sleeper leagues get an explanatory row and no request — `backend/outlook/league_state.py` implements Sleeper only.
- Every new user-facing screen mounts `FeedbackFAB` by default; modals/sheets and onboarding flows are the exceptions.
- Anchors/Tiers/Quick Set/Overall/Quick Rank/Trios/RookieRanks share `RookieScopeControl` + `state/rookieScope.ts` (flag `ranks.rookie_subset`) — it narrows candidates only, never save semantics.
