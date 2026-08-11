# Screen×State Capture Matrix — DRAFT (2026-08-09)

*One row per (screen, state) capture for the screen library. Grounded in `app-inventory-2026-08-09.md`. **DRAFT — the orchestrator signs off before any flow is authored.** Rows marked ⚠ are ones I am NOT confident are reachable or capturable from the current fixture set; each carries a reason.*

---

## Conventions

- **screen dir** — the testID `<screen>` segment (as-built vocabulary, inventory §4). Captures land in `qa/screens/<screen-dir>/<state>.png`.
- **state filename** — kebab-case; `--` introduces a modifier (`populated--all-tab`, `error--404`).
- **profile** — `backend/tests/fixtures/profiles/<name>.json`. Rows are grouped by profile so one seeded backend serves a whole block.
- **injections** — `/__test__` arming. `fail_next: <METHOD> <path glob> → <status>` fires once for the next matching request; `latency: <path glob> <ms>` delays every matching request for the cell. Blank = none.
- **nav path** — abbreviated; `→` is a tap/navigate. `boot` = cold launch into the profile's initial route.
- **traps** — from the inventory §7 hazard list; the flow author must handle these or the capture is nondeterministic.
- **Flag pinning:** every profile pins only the 13 legacy keys; anything else must be passed via `FTF_FLAGS`. The `flags` needed beyond `release` are called out in the traps column as `pin:<key>=<v>`.

**Row totals:** fresh 38 · standard 80 · near-unlock 10 · two-leagues 12 · single-format 6 — **146 rows**, of which **41 are ⚠**.

---

## Profile: `fresh` (38 rows)

*Brand-new user: 1 league (10-team 1QB PPR), locked, zero rankings/tiers/history, no matches. Extra fixture user `qa_no_leagues` has an empty league list.*

| # | screen dir | state filename | injections | nav path | traps |
|---|---|---|---|---|---|
| 1 | signin | `idle` | — | boot (no stored user) | Apple button presence depends on `auth.accounts` + `isAvailableAsync`; sim may report Apple unavailable → capture `idle--no-apple` instead |
| 2 | signin | `idle--hint` | — | boot after a prior signed-in run leaves the Keychain last-username | hint row resolves ASYNC → layout shift; wait for `signin.hint-btn` |
| 3 | signin | `idle--no-apple` | — | boot | pin `auth.accounts=false` to force deterministically |
| 4 | signin | `focused-keyboard` | — | boot → tap `signin.username-input` | keyboard covers the legal line; capture must include the keyboard |
| 5 | signin | `busy` | latency: `/api/extension/auth` 4000 | boot → type `qa_standard` → `signin.continue-btn` | 3 mutually-disabling busy flags |
| 6 | signin | `error--notfound` | fail_next: POST `/api/extension/auth` → 404 | boot → submit | copy differs with `onboarding.landing`; capture the release (flag-off) copy |
| 7 | signin | `error--unavailable` | fail_next: POST `/api/extension/auth` → 503 | boot → submit | — |
| 8 | ⚠ signin | `idle--landing` | — | boot | ⚠ `onboarding.landing=false` in `release`; needs `pin:onboarding.v2=true,onboarding.landing=true`. Also flips 5 other states' copy — confirm the orchestrator wants the landing variant in the library at all |
| 9 | ⚠ signin | `demo-link` | — | boot | ⚠ profile pins `landing.try_before_sync=false`; needs `pin:landing.try_before_sync=true` AND `onboarding.landing=true` (backend `/api/session/demo` 404s otherwise — flag pairing note in `config/features.json`) |
| 10 | leagues | `loading` | latency: `/api/sleeper/leagues/*` 3000 | signin → submit | capture inside the 4s window before the slow-load copy swaps |
| 11 | leagues | `slow-load` | latency: `/api/sleeper/leagues/*` 7000 | signin → submit | 4s timer; copy swaps to "Waking up server" |
| 12 | leagues | `populated` | — | signin → submit | ⚠-adjacent: `onboarding.league_autoskip` is off in `release`, so the single-league picker DOES render — confirm before authoring |
| 13 | leagues | `empty` | — | signin as `qa_no_leagues` | uses the profile's `extra_users` entry |
| 14 | leagues | `error` | fail_next: GET `/api/sleeper/leagues/*` → 500 | signin → submit | — |
| 15 | leagues | `row-busy` | latency: `/api/sleeper/rosters/*` 4000 | leagues → tap `leagues.row.990000000000000001` | two-phase nav — the screen navigates to Main before `/api/session/init` resolves; capture before the transition |
| 16 | ⚠ leagues | `link-footer` | — | signin → submit | ⚠ `espn.link` and `mfl.link` are ON in `release`, so the footer should render — but `EspnLinkSheet`'s own `espn.league_picker` path needs stored cookies the fixtures don't have. Verify the footer buttons render before authoring |
| 17 | rank-home | `populated` | — | boot(Main) → Rank tab → `rank.more-ways` / RankMenu → RankHome | with `ux.rank_tab_destination=true` (release) the Rank tab navigates; RankHome is reached via the header control |
| 18 | rank-home | `populated--more-expanded` | — | rank-home → `rank-home.more-toggle` | below the fold — scroll first |
| 19 | quick-set | `step-populated` | — | boot(Main) → Rank tab | `fresh` has no pref → #244 routes to QuickSetTiers at QB, tier 1 |
| 20 | quick-set | `step--selection` | — | quick-set → tap 3 `quick-set.chip.*` | chip IDs are player-id templated — resolve from the fixture roster |
| 21 | quick-set | `saving` | latency: `/api/tiers/save` 4000 | quick-set → select → `quick-set.save-btn` | save auto-advances the step on success — capture during the latency window |
| 22 | quick-set | `empty--search-miss` | — | quick-set → `quick-set.search` type `zzzz` | keyboard inside `KeyboardAvoidingView` over an absolute footer |
| 23 | quick-set | `error` | fail_next: GET `/api/rankings*` → 500 | Rank tab (cold) | — |
| 24 | ⚠ quick-set | `alert--tiers-set` | — | quick-set → save/skip through all 8 rungs | ⚠ native `Alert` — not in the RN tree; capturable only as an OS screenshot, and requires 8 sequential steps. Confirm whether native alerts belong in the library |
| 25 | quick-rank | `empty--no-walkable-tiers` | — | Rank menu → `rankmenu.quickset` → … → QuickRank, or deep link | `fresh` has no tiers with ≥2 members → this is the only reachable QuickRank state on this profile |
| 26 | trios | `loading` | latency: `/api/trio*` 4000 | Rank menu → `rankmenu.trios` | 3 skeleton cards |
| 27 | trios | `populated` | — | Rank menu → `rankmenu.trios` | trio CONTENTS are server-chosen — nondeterministic across runs; the library captures shape, not identity |
| 28 | trios | `partial-selection` | — | trios → tap `trios.card.a` | instruction copy changes per selection count |
| 29 | trios | `all-ranked` | — | trios → tap a, b, c | requires `trios.speed-toggle` OFF, else the 2nd tap auto-submits. **Speed mode persists in AsyncStorage — erase sim data** |
| 30 | trios | `error` | fail_next: GET `/api/trio*` → 500 | Rank menu → `rankmenu.trios` | — |
| 31 | trios | `progress-locked` | — | trios (scroll to the progress bar) | per-position `n/threshold` counters render only while locked |
| 32 | tiers | `populated--unassigned-pool` | — | Rank menu → `rankmenu.tiers` | `fresh` has `tiers: null` → everything sits in Unassigned |
| 33 | manual-ranks | `empty--filter` | — | Rank menu → more → `rankmenu.manual` | `fresh` has zero rankings → "No rankings yet" |
| 34 | trends | `empty--no-history` | — | Rank menu → more → `rankmenu.trends` | three independent sections; capture the whole scroll |
| 35 | trades | `skeleton--first-run` | latency: `/api/trades/generate` 6000 | Acquire tab (cold) | first-run auto-generate fires on mount; `firstRun` latches at mount — needs a fresh launch |
| 36 | trades | `generating` | latency: `/api/trades/status*` 6000 | Acquire tab → `trades.find-btn` | ScrollView is DISABLED while generating |
| 37 | trades | `empty--cold` | — | Acquire tab, before pressing Find | may be pre-empted by the first-run auto-generate — pin `onboarding.trades_first=false` (release default) and capture the very first frame |
| 38 | matches | `empty--mutual` | — | Matches tab | `matches.progress-module` also renders here (summary+coverage resolved); pull-to-refresh does NOT work on empty states |

---

## Profile: `standard` (80 rows)

*12-team SF TEP, unlocked in both formats, 4-position rankings + 30d history, seeded-suggested tiers, 1 ranked + 1 unranked opponent, 2 mutual + 1 awaiting match.*

### Rank surfaces (24)

| # | screen dir | state filename | injections | nav path | traps |
|---|---|---|---|---|---|
| 39 | trios | `populated--unlocked` | — | Rank tab → Trios | position counters hidden once unlocked |
| 40 | trios | `unlock-banner` | — | Trios (scroll to bottom) | 2 copy variants by `ux.outlook_inline_default` (ON in release) |
| 41 | trios | `speed-mode-on` | — | Trios → `trios.speed-toggle` | persists to AsyncStorage — must be reset after this cell |
| 42 | ⚠ trios | `info-sheet` | — | Trios → long-press `trios.card.a` | ⚠ long-press 400/500ms; needs `swipe.gesture_audit=true` (ON in the profile's overrides) — but the delay differs with `ux.player_context_menu`. Verify the sheet, not the context menu, opens |
| 43 | ⚠ trios | `scope-rookie` | — | Trios → `trios.scope-rookie` | ⚠ `ranks.rookie_subset` is not in `config/features.json` at all → defaults false. Needs `pin:ranks.rookie_subset=true`, and the fixture pool may still be a thin-pool empty |
| 44 | ⚠ trios | `toast--streak` | — | Trios → complete a trio | ⚠ toast is timer-dismissed (1500ms, or ≥5000ms under `ux.toast_v2`) AND only fires when `streak.current > 0` — the seeder does not seed a streak. Confirm reachability |
| 45 | tiers | `loading` | latency: `/api/rankings*` 4000 | Rank menu → `rankmenu.tiers` | — |
| 46 | tiers | `populated` | — | Rank menu → `rankmenu.tiers` | opens on QB |
| 47 | tiers | `populated--all-tab` | — | tiers → `tiers.pos-tab.all` | All view fans out to 4 parallel saves on save |
| 48 | tiers | `multi-select` | — | tiers → "Select" (no testID — text) | Select toggle has NO testID |
| 49 | tiers | `multi-select--active` | — | tiers → Select → tap 2 rows | player rows have NO testIDs — text/a11y-label selection |
| 50 | tiers | `expanded` | — | tiers → expand (no testID) | expanded mode UNMOUNTS header/format/scope/copy chrome |
| 51 | tiers | `sticky-header` | — | tiers → scroll past a tier header | overlay is `accessibilityElementsHidden` — invisible to a11y scrapers, visible in a screenshot |
| 52 | ⚠ tiers | `search-highlight` | — | tiers → `tiers.search` type a player name | ⚠ needs `ux.board_search=true` (ON in `release`); search SCROLLS + highlights rather than filtering, and `onScrollToIndexFailed` schedules a 250ms retry — timing-sensitive |
| 53 | tiers | `saving` | latency: `/api/tiers/save` 4000 | tiers → move a player → `tiers.save-btn` | move via chevron or multi-select, NOT drag |
| 54 | tiers | `error` | fail_next: GET `/api/rankings*` → 500 | Rank menu → `rankmenu.tiers` | — |
| 55 | ⚠ tiers | `alert--copy-confirm` | — | tiers → "Copy tier list from 1QB PPR" | ⚠ native Alert (see row 24 note) |
| 56 | ⚠ tiers | `alert--reset-confirm` | — | tiers → "Reset to suggested" | ⚠ native Alert; title/body vary by scope and All-vs-position |
| 57 | ⚠ tiers | `toast--drag-reject` | — | tiers → drag a tiered player into Unassigned | ⚠ requires a real 220ms/18px drag AND the guarded drop; a failed drag is indistinguishable from a no-op |
| 58 | quick-set | `step-populated--seeded` | — | Rank menu → `rankmenu.quickset` | with seeded tiers the chips show their current tier label |
| 59 | quick-rank | `step-populated` | — | Rank menu → quickset → finish alert → "Quick rank" | requires clearing the native Alert first (row 24) |
| 60 | quick-rank | `step--clicked` | — | quick-rank → tap 3 chips | numeric rank badges |
| 61 | anchors | `loading` | latency: `/api/rankings*` 4000 | Rank menu → more → `rankmenu.anchors` | two-phase paint (query + AsyncStorage) |
| 62 | anchors | `question` | — | Rank menu → more → `rankmenu.anchors` | `ftf_anchor_done_v1_<fmt>` persists — erase sim data or a done-card appears |
| 63 | anchors | `consequence-line` | — | anchors → tap a rung | replaces the hint line |
| 64 | anchors | `error` | fail_next: GET `/api/rankings*` → 500 | Rank menu → more → `rankmenu.anchors` | staleTime Infinity — a prior success in the same launch blocks the refetch |
| 65 | ⚠ anchors | `done-card` | — | anchors → exhaust the queue | ⚠ the queue is the full ranked pool (hundreds) — not exhaustible in a flow. Only reachable by pre-seeding `ftf_anchor_done_v1_sf_tep` in the sim data volume, which the harness does not currently do |
| 66 | manual-ranks | `populated` | — | Rank menu → more → `rankmenu.manual` | — |
| 67 | manual-ranks | `row--editing` | — | manual-ranks → tap a rank number | number-pad has no return key — commits on blur |
| 68 | manual-ranks | `save-pill--saving` | latency: `/api/rankings/reorder` 4000 | manual-ranks → move 2 rows via a11y `moveUp` | 600ms debounce before the request; <2 ids silently skips the save |
| 69 | manual-ranks | `save-pill--saved` | — | manual-ranks → move → wait | "saved" auto-clears after 1500ms — narrow window |
| 70 | manual-ranks | `save-pill--error` | fail_next: POST `/api/rankings/reorder` → 500 | manual-ranks → move | — |
| 71 | ⚠ manual-ranks | `search-highlight` | — | manual-ranks → `manual-ranks.search` | ⚠ same 250ms scroll-retry timing as row 52; no-match renders NOTHING (silent) |
| 72 | manual-ranks | `error` | fail_next: GET `/api/rankings*` → 500 | Rank menu → more → `rankmenu.manual` | — |
| 73 | rookie-ranks | `flag-off` | — | deep link `app/rank/rookie-ranks` | the honest "aren't available yet" gate — reachable on `release` defaults |
| 74 | ⚠ rookie-ranks | `populated` | — | rank-home → `rank-home.rookie-ranks` | ⚠ needs `pin:ranks.rookie_subset=true`; the fixture player pool has no `years_experience: 0` cohort guarantee → may render `scope-empty` instead |
| 75 | trends | `loading` | latency: `/api/trends/*` 4000 | Rank menu → more → `rankmenu.trends` | — |
| 76 | trends | `populated` | — | Rank menu → more → `rankmenu.trends` | `standard` has 30d history + a ranked opponent → both sections should populate |
| 77 | trends | `error` | fail_next: GET `/api/trends/risers-fallers*` → 500 | Rank menu → more → `rankmenu.trends` | risers and fallers share ONE query — both sections show the error together |
| 78 | ⚠ trends | `empty--no-gaps` | — | Rank menu → more → `rankmenu.trends`, scroll | ⚠ `standard` seeds a ranked opponent, so the gap section should populate, not empty. To capture the empty variant needs a profile with a baseline but no standout gaps — none exists |

### Trade surfaces (23)

| # | screen dir | state filename | injections | nav path | traps |
|---|---|---|---|---|---|
| 79 | trades | `guided-landing` | — | Acquire tab | `trades.finder_hub=true` in `release` → `mode:'guided'`; mode bar + `OutlookBiasReceipt` render |
| 80 | trades | `controls-consolidated` | — | Acquire tab | consolidated layout is active whenever `trades.edit_full_sheet` AND a finder mode are on — verify which layout `release` yields and capture the other via `pin:trades.edit_full_sheet=false` |
| 81 | trades | `card-top` | — | Acquire → `trades.find-btn` → wait for the deck | poll loop 800→4000ms ±10% jitter — wait on `trades.card-top`, never a fixed sleep |
| 82 | trades | `progress-strip` | latency: `/api/trades/status*` 6000 | Acquire → `trades.find-btn` | — |
| 83 | trades | `error--generate` | fail_next: POST `/api/trades/generate` → 500 | Acquire → `trades.find-btn` | `/api/trades/generate` is on the client's NO_RETRY list — one shot |
| 84 | trades | `toast--undo` | — | Acquire → deck → `trades.pass-btn` | 5000ms hold under `ux.swipe_undo` (ON in release) |
| 85 | ⚠ trades | `deck-summary` | — | Acquire → swipe the whole deck out | ⚠ deck length is job-dependent and nondeterministic; needs N presses of `trades.pass-btn` with an unknown N. Suggest a `/__test__` deck-size pin before authoring |
| 86 | ⚠ trades | `exhausted` | — | Acquire → `trades.find-btn` twice after the deck empties | ⚠ same nondeterminism as row 85 |
| 87 | ⚠ trades | `outlook-sheet-auto` | — | Acquire tab (cold, prefs with no outlook) | ⚠ the force-open is suppressed when `ux.outlook_inline_default` is ON — and it IS on in `release`. Needs `pin:ux.outlook_inline_default=false` AND `trades.edit_full_sheet=false` |
| 88 | trades | `dna-sheet` | — | deep link `app/trades/finder?editDna=1`, or mode bar → edit | `TradeDnaSheet` auto-opens from the route param; it is a LONG scroll |
| 89 | ⚠ trades | `pin-board--player-mode` | — | mode bar → Player chip | ⚠ requires `trades.finder_hub=true` (yes) and the player-mode chip to be present — `trades.sheet_targeting` hides Team/Player chips when consolidated. Verify chip visibility under `release` |
| 90 | ⚠ trades | `pin-summary` | — | player mode → pin one asset | ⚠ single-pin mode also suppresses the deck and the Find button; confirm this is the intended library state |
| 91 | ⚠ trades | `featured-window` | — | single-pin mode | ⚠ needs `pin:trade.asset_ideas=true` (ON in `config/features.json`) and a pinned asset; depends on `POST /api/trades/asset-ideas` returning ideas for the fixture roster |
| 92 | ⚠ trades | `asset-ideas` | — | single-pin mode, scroll | ⚠ same dependency as row 91 |
| 93 | ⚠ trades | `queue-footer` | — | deck → Queue → Queue a 2nd | ⚠ `trades.queue_2k=false` in the profile overrides AND in `config/features.json`; needs `pin:trades.queue_2k=true` |
| 94 | ⚠ trades | `player-menu` | — | deck → long-press a give-side player | ⚠ long-press; `ux.player_context_menu` ON in `release` |
| 95 | ⚠ trades | `swap-suggest-sheet` | — | deck → `trade-card.swap-suggest.<pid>` | ⚠ reached from the context menu (row 94) → nested-modal risk; needs the evaluate call to return eveners |
| 96 | ⚠ trades | `help-sheet` | — | Acquire → `trades.fairness-help` | ⚠ only rendered when `ux.help_surface` (ON in `release`) AND the full controls card is shown (`!consolidateOn`) |
| 97 | ⚠ trades | `target-picker` | — | Acquire → target toggle → picker | ⚠ `trade.finder_targeting=true` in the profile; but the targeting block is suppressed in player mode and moved into the sheet under `trades.sheet_targeting`. Confirm which layout exposes it |
| 98 | calc | `live-populated` | — | Acquire → `trades.subnav.calculator` (or mode bar Calc) | subnav is hidden in finder modes — use the mode-bar Calc chip |
| 99 | calc | `live-loading` | latency: `/api/trade/values*` 4000 | calc → `calc.mode-tab.live` | — |
| 100 | calc | `live-error` | fail_next: GET `/api/trade/values*` → 500 | calc → `calc.mode-tab.live` | offers "switch to demo" |
| 101 | calc | `verdict--live` | — | calc live → add to both sides via `calc.side-a-add`/`calc.side-b-add` | 250ms debounce before evaluate |

### Matches / League / FA (18)

| # | screen dir | state filename | injections | nav path | traps |
|---|---|---|---|---|---|
| 102 | calc | `demo-verdict` | — | calc → `calc.mode-tab.demo` → fill both sides | local math, no network |
| 103 | calc | `one-sided-read` | — | calc demo → fill one side only | — |
| 104 | calc | `league-mode` | — | calc → `calc.mode-tab.league` | delegates to `InLeagueCalculator`; picker/TradeSides unmount |
| 105 | calc | `picker-open` | — | calc live → `calc.side-a-add` | `calc.picker.search` raises the keyboard |
| 106 | calc | `suggestions` | — | calc live → build an unbalanced package | suggestions arrive ~2 round-trips after the evaluate |
| 107 | ⚠ calc | `no-suggestions` | — | calc live → an unmatchable package | ⚠ requires knowing a package the engine cannot balance — data-dependent |
| 108 | matches | `skeleton` | latency: `/api/trades/matches/all` 4000 | Matches tab | 3 static tiles |
| 109 | matches | `populated--mutual` | — | Matches tab | `standard` seeds 2 mutual |
| 110 | matches | `populated--awaiting` | — | Matches → `matches.segment.awaiting` | lazily fetched on first open |
| 111 | matches | `error` | fail_next: GET `/api/trades/matches/all` → 500 | Matches tab | — |
| 112 | matches | `filter-chips` | — | Matches tab | single-league profile → "All" + one chip only; the multi-chip shape belongs to `two-leagues` |
| 113 | matches | `toast--dismiss-undo` | — | Matches → Dismiss on a card | POST is held 5000ms and flushes on unmount — do not navigate away mid-capture |
| 114 | league-summary | `loading` | latency: `/api/league/power-rankings*` 4000 | League tab | BOTH bases are fetched in parallel |
| 115 | league-summary | `populated` | — | League tab | tab ROOT is `LeagueRankings` |
| 116 | league-summary | `basis--personal` | — | League tab → `league-summary.basis.personal` | — |
| 117 | league-summary | `focused-roster` | — | League tab → `league-summary.team.<uid>` | while focused, `subset.*`/`posfilter.*` UNMOUNT — use the `roster-` prefixed set |
| 118 | league-summary | `posfilter--qb` | — | League tab → `league-summary.posfilter.qb` | — |
| 119 | league-summary | `error` | fail_next: GET `/api/league/power-rankings*` → 500 | League tab | — |

### League / FA / Settings / chrome (15)

| # | screen dir | state filename | injections | nav path | traps |
|---|---|---|---|---|---|
| 120 | ⚠ league-summary | `overlay-on` | — | League tab | ⚠ ticks/Δ chips render only when the personal board DIFFERS from consensus in view (#248/#208). `standard` seeds generated rankings — whether they diverge enough is not guaranteed |
| 121 | ⚠ league-summary | `subset--starters` | — | League tab → `league-summary.subset.starters` | ⚠ the control only mounts when `starters_available === true` AND every team carries a starters array — depends on the fixture league's Sleeper slot template |
| 122 | ⚠ league-summary | `roster-picks` | — | focused roster, subset=all, no filter or PICKS | ⚠ needs the team to hold ≥1 draft pick; the seeder does not seed pick ownership |
| 123 | ⚠ league-summary | `odds` | — | League tab, scroll | ⚠ `outlook.odds=false` in `config/features.json`; needs `pin:outlook.odds=true` AND a backend outlook payload the fixtures do not seed |
| 124 | league | `populated` | — | League tab → `league-summary.league-home` | LeagueScreen has NO error state — failures render as dashes |
| 125 | league | `first-paint-pending` | latency: `/api/league/summary*` 4000 | League tab → `league-summary.league-home` | em-dashes everywhere; Meter forced to 0 |
| 126 | league | `members-overlay` | — | league → joined chip | the chip is HIDDEN when `joined === 0`; no testID on the chip or the overlay |
| 127 | ⚠ league | `market-pulse` | — | league, scroll below Explore | ⚠ `MarketPulseStrip` returns NULL on loading, error, flag-off and thin data alike — `market.movers=true` in config but the fixtures seed no movers history |
| 128 | ⚠ league | `rookie-board-sheet` | — | league → `league.rookie-board-row` | ⚠ the tile only renders when `draft.room` is OFF and `league.rookie_board_entry` is ON; `draft.room` is not in `config/features.json` (defaults false) so this should be reachable — verify `league.rookie_board_entry` |
| 129 | free-agents | `populated` | — | league → `league.free-agents-row` | — |
| 130 | free-agents | `empty--position` | — | free-agents → `free-agents.pos-tab.te` | each tab is its own request + full-screen spinner (no `placeholderData`) |
| 131 | free-agents | `error--rosters-unavailable` | fail_next: GET `/api/league/free-agents*` → 503 | league → `league.free-agents-row` | the 503 body's message is surfaced VERBATIM — the injection must carry a body |
| 132 | free-agents | `claim-sheet` | — | free-agents → `free-agents.add.<pid>` | Sleeper-only; a NON-NUMERIC league id or a demo session yields the refusal Alert instead. Fixture ids ARE numeric ✅ |
| 133 | ⚠ free-agents | `claim-sheet--faab` | — | claim sheet on a FAAB league | ⚠ depends on the fixture league's `waivers.type`; the seeder does not set it — likely renders the "no waivers info" variant |
| 134 | ⚠ free-agents | `claim-sheet--over-budget` | — | claim sheet → type a bid > budget | ⚠ requires row 133 first; number-pad keyboard inside an 85%-height sheet with no KeyboardAvoidingView — the CTA may be occluded |

### Settings / profile / feedback / chrome (12)

| # | screen dir | state filename | injections | nav path | traps |
|---|---|---|---|---|---|
| 135 | settings | `populated` | — | TopBar → `topbar.settings` | whole tree is absent until `/api/notifications/prefs` resolves; section ORDER flips with `account.settings_v2` — pin it explicitly |
| 136 | settings | `account-section` | — | settings → scroll to Account | several rows appear only after their query resolves — absence ≠ flag-off |
| 137 | ⚠ settings | `alert--delete` | — | settings → Delete account | ⚠ NESTED two-step native Alert; destructive against the fixture user |
| 138 | ⚠ settings | `notif-denied-banner` | — | settings | ⚠ requires the OS notification permission to be DENIED on the simulator — a device-state precondition the harness does not set today |
| 139 | profile | `flag-off` | — | deep link `dtf://u/qa_standard` | `profiles.public_pages=false` in the profile overrides → the "coming soon" gate |
| 140 | ⚠ profile | `populated` | — | deep link `dtf://u/qa_standard` | ⚠ needs `pin:profiles.public_pages=true`; screen has ZERO testIDs — text-only assertions |
| 141 | profile | `error--404` | — | deep link `dtf://u/nobody_here` | no retry on 404 |
| 142 | feedback | `sheet` | — | any screen → `feedback.fab` | the FAB floats over every screen and occludes bottom-right content in EVERY other capture |
| 143 | feedback-inbox | `empty` | — | settings → Test feedback | Clear can be enabled while the list looks empty (closed items) |
| 144 | rankmenu | `collapsed` | — | any rank surface → `rank.more-ways` | the same `rankmenu.*` IDs render in both the collapsed and expanded lists |
| 145 | rankmenu | `more-expanded` | — | rankmenu → `rankmenu.more-toggle` | — |
| 146 | topbar | `notif-sheet--empty` | — | TopBar → bell | the bell button has NO testID (a11y label only: "Notifications, N unread") |

### Excluded / deferred from `standard` (recorded so the orchestrator can rule)

| screen dir | why no row |
|---|---|
| ⚠ draft-room | Registered and reachable, but **no fixture seeds a draft board** — every state would be `unavailable` or a notice. Recommend a `draft` profile before capturing. `draft.room`/`draft.tab` also default false |
| ⚠ mock-draft | Only reachable through the Draft Room's mock entry, which needs `draft.mock` + a loaded rookie class — neither seeded |
| ⚠ pick-assignment | **ESPN-only.** No ESPN fixture profile exists |
| ⚠ record-picks | **ESPN-only** + requires assigned picks |
| ⚠ espn-link sheet | Reachable from `leagues.link-espn`, but the team step needs real ESPN cookies |
| ⚠ guide | `AnalystGuide` steps need `onboarding.v2` + `onboarding.guided_avatar`; the overlay auto-advances on a 2400ms timer and its tap-catcher swallows taps — hostile to deterministic capture |
| ⚠ tab (5-tab bar) | `draft.tab` decides tab presence ONCE at mount and is not in `config/features.json` |
| sleeperconnect / espn-connect / test-stages / placeholder | Excluded by the inventory (live WebViews / non-product) |
| finder-hub | UNROUTED dead code — unreachable |

---

## Profile: `near-unlock` (10 rows)

*threshold−1 trios per position in `sf_tep` only, still locked, 7d history.*

| # | screen dir | state filename | injections | nav path | traps |
|---|---|---|---|---|---|
| 147 | trios | `progress-near-threshold` | — | Rank tab → Trios | per-position bar one segment from full |
| 148 | trios | `unlock-crossing` | — | Trios → complete one trio per position | the threshold cross invalidates `progress` (extra round-trip) — wait on the banner |
| 149 | trios | `unlock-banner--fresh` | — | after row 148 | 2 copy variants by `ux.outlook_inline_default` |
| 150 | ⚠ trios | `toast--qc-compliment` | — | Trios → answer a QC trio in the expected order | ⚠ QC trios are server-selected (`is_qc_trio`) and nondeterministic; needs `swipe.qc_compliments=true` (ON in the profile) plus luck. Suggest a `/__test__` QC pin |
| 151 | ⚠ push | `priming-modal` | — | after the unlock crosses | ⚠ `PushPrimingModal` has NO testIDs and is gated on `progress.unlocked` + OS permission `undetermined` + `ux.prompt_arbiter` deferral. Erase sim data so permission is undetermined |
| 152 | league | `progress-module` | — | League tab → `league-summary.league-home` | requires summary AND coverage both resolved — never on the first frame |
| 153 | league | `works-now` | — | league, scroll | renders only when mutual matches == 0 (true for `near-unlock`) |
| 154 | matches | `progress-module` | — | Matches tab (empty state) | `matches.progress-module` |
| 155 | trades | `locked-gate` | — | Acquire tab | verify what the deck renders while locked — the inventory found no explicit lock branch on TradesScreen; the gate lives on progress |
| 156 | rank-home | `populated--partial` | — | Rank tab → `rank.more-ways` → RankHome | quick-set card copy is completion-aware |

---

## Profile: `two-leagues` (12 rows)

*12-team SF TEP + 10-team 1QB PPR, unlocked in both formats.*

| # | screen dir | state filename | injections | nav path | traps |
|---|---|---|---|---|---|
| 157 | leagues | `populated--two` | — | boot → signin | two rows + platform badges |
| 158 | portfolio | `populated` | — | Acquire → `trades.subnav.portfolio` | subnav hidden in finder modes — use the mode bar or a deep link |
| 159 | ⚠ portfolio | `empty` | — | Portfolio with no shared players | ⚠ the two fixture leagues share the same generated members, so overlap is likely non-empty. Not controllable today |
| 160 | portfolio | `refreshing` | latency: `/api/portfolio*` 4000 | Portfolio → pull to refresh | each row has a HORIZONTAL chip ScrollView — chips can be off-screen sideways |
| 161 | topbar | `league-switcher` | — | TopBar → `topbar.league` | league rows have no testIDs; `league.switcher.add-league` is the only one |
| 162 | trades | `switching-overlay` | latency: `/api/session/init` 4000 | league switcher → pick the other league | — |
| 163 | trades | `slow-switch-overlay` | latency: `/api/session/init` 7000 | league switcher → pick the other league | 4s timer swaps in the "Waking up server" copy |
| 164 | trades | `subnav--portfolio-visible` | — | Acquire tab | the Portfolio pill only renders with ≥2 leagues AND no finder mode |
| 165 | matches | `populated--all-filter` | — | Matches tab | cross-league list with per-row league badges |
| 166 | matches | `filter--league-scoped` | — | Matches → a league chip | filtering is client-side; can flip the list into a per-filter empty |
| 167 | settings | `league-rows` | — | settings | the league-switch rows are HIDDEN when `leagues.length <= 1` — this is the only profile that shows them |
| 168 | league | `hero--second-league` | — | switch league → League tab → league home | — |

---

## Profile: `single-format` (6 rows)

*League resolves `sf_tep`; the user is ranked + unlocked only in `1qb_ppr`.*

| # | screen dir | state filename | injections | nav path | traps |
|---|---|---|---|---|---|
| 169 | trades | `format-gate` | — | Acquire tab | `FormatGate` REPLACES the entire controls+deck block |
| 170 | ⚠ trades | `format-gate--copy-alert` | — | format gate → "Copy tiers" | ⚠ native Alert ("Copy tiers from X?") |
| 171 | tiers | `format-toggle--other` | — | Rank menu → tiers → format toggle | `POST /api/scoring/switch` round-trip; toggle disabled meanwhile |
| 172 | trios | `format-toggle` | — | Rank tab → Trios → format toggle | switching clears the current selection |
| 173 | league | `coverage--single-format` | — | League tab → league home | coverage card hides entirely at 0 |
| 174 | league-summary | `populated--single-format` | — | League tab | caption reads `Dynasty · SF TEP` |

---

## ⚠ Summary — 41 rows needing a ruling

Grouped by the reason I am unsure:

**A. Flag not on in `release` / not in `config/features.json` at all (11):**
rows 8, 9, 43, 74, 93, 123, 140 — plus the deferred blocks for `draft.room`/`draft.tab`/`draft.mock`/`ranks.rookie_subset`. Each needs an explicit `FTF_FLAGS` pin, and pinning changes sibling states' copy. **Ruling needed: does the library capture the `release` truth, or the flag-on future?**

**B. Native `Alert` — outside the RN tree (7):**
rows 24, 55, 56, 137, 170, plus MockDraft's End alert and Settings' merge-conflict alert. Capturable only as an OS-level screenshot. **Ruling needed: are native alerts in scope for the library?**

**C. Fixture data does not seed the precondition (13):**
rows 44 (no streak), 65 (anchor queue never exhausts), 78 (no "no gaps" profile), 107 (no unmatchable package), 120 (boards may not diverge), 121 (starters template), 122 (no pick ownership), 123 (no outlook payload), 127 (no movers history), 133/134 (no waivers config), 159 (portfolio overlap not controllable), plus the whole draft/ESPN block. **Ruling needed: add a `draft` profile and an `espn` profile, or accept the gaps?**

**D. Nondeterministic length / server choice (4):**
rows 85, 86 (deck length job-dependent), 150 (QC trio server-selected), 27 (trio contents). Suggest `/__test__` pins for deck size and QC selection.

**E. Gesture- or timer-only reachability (6):**
rows 42, 57, 71, 94, 95 (long-press / drag / 250ms scroll retry), 151 (push priming + OS permission state), plus the `guide` block (2400ms auto-advance + tap-catcher).

**Recommended orchestrator decisions before flows are authored:**
1. Rule on A and B — they together account for 18 rows.
2. Authorize two new fixture profiles: **`draft`** (seeded rookie class + draft board, Sleeper) and **`espn`** (ESPN-platform league with assigned picks). Without them, 5 screens — `draft-room`, `mock-draft`, `pick-assignment`, `record-picks`, and LeagueScreen's ESPN branch — get zero coverage.
3. Authorize three `/__test__` pins: deck size, QC-trio selection, and a streak seed. They convert 4 nondeterministic rows into deterministic ones.
4. Confirm whether `TradeFinderHubScreen` is deleted (inventory §2.30) — it currently duplicates `dna.*` testIDs with `TradeDnaSheet`, which will confuse any grep-based selector work.
