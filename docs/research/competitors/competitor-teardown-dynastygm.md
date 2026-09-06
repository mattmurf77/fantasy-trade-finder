# Competitor Teardown — DynastyGM (Dynasty Nerds) Mobile App

*Source: 18 iPhone screenshots captured 2026-06-10. App identified as DynastyGM (Dynasty Nerds) from mascot/branding; treat identification as high-confidence but unverified.*

---

## 1. Page Tree

```
App shell
├── Global chrome (persistent)
│   ├── Hamburger menu (top-left)
│   ├── League selector dropdown (top-center, contextual — e.g. "La Resistance")
│   ├── Global player search (magnifier)
│   └── Account/brand button (top-right, red — mascot + switcher chevron)
│
├── Tab 1 — HOME
│   ├── Leagues (default)
│   │   └── Your Leagues list → tap-through to league
│   └── League Hosts
│       └── Connected platform accounts (+ Add New)
│
├── Tab 2 — TRENDS / POWER RANKINGS
│   ├── League power-rankings chart (stacked bars, all teams)
│   ├── Team standings list (total roster value)
│   └── Team drill-down (tap a team/bar)
│       ├── Position groups: QB / RB / WR / TE (per-player values)
│       └── Draft Picks group (per-pick values + projection model note)
│
├── Tab 3 — PLAYERS
│   ├── Rankings (default) — rank vs ADP, DIFF
│   ├── Shares — cross-league exposure
│   ├── Free Agents — league-scoped waiver values
│   └── Data Hub (not captured)
│
├── Tab 4 — TRADES
│   ├── Browser (default) — feed of real trades across Sleeper leagues
│   │   └── Filter panel + refresh
│   ├── Team Calc — league-aware side-by-side trade calculator
│   │   └── Player search modal (typeahead + top players)
│   └── Open Calc — free-form calculator (not captured in detail)
│
├── Tab 5 — DRAFTS
│   ├── Mock — saved mock-draft configs list (+ Add New / Delete)
│   │   └── Live mock draft room (on-clock bar, pick feed, player pool)
│   └── League Draft — synced real draft board
│       ├── Players pane (available players + values)
│       └── Your Picks pane
│
└── Tab 6 — PROFILE / ACCOUNT (not captured)
```

Bottom nav: 6 tabs — Home, Trends (line chart icon), Players (people icon), Trades (crossed arrows), Drafts (board icon), Profile.

---

## 2. Feature List

| # | Feature | Tab |
|---|---|---|
| 1 | Multi-league dashboard with per-league rank chips | Home |
| 2 | Multi-platform league host accounts (Sleeper, ESPN, +1) | Home |
| 3 | League power rankings — stacked positional value bars | Trends |
| 4 | Team drill-down: roster value audit by position group | Trends |
| 5 | Draft-pick capital valuation w/ projection model | Trends |
| 6 | Dynasty player rankings w/ ADP comparison (DIFF) | Players |
| 7 | Format toggle (SFLEX) + position/rookie/IDP filters | Players |
| 8 | Shares — cross-league player exposure % | Players |
| 9 | Free agent values per league (value + projection) | Players |
| 10 | Trade Browser — live feed of real trades league-wide | Trades |
| 11 | Team Calc — league-aware two-team trade calculator | Trades |
| 12 | Open Calc — free-form trade calculator | Trades |
| 13 | Mock draft simulator w/ saved configs (rounds, linear/3RR, format) | Drafts |
| 14 | League draft board sync (real drafts, traded-pick markers) | Drafts |
| 15 | Live mock draft room (clock, pause, draft buttons) | Drafts |
| 16 | Unified numeric player-value system used everywhere | Cross-cutting |

---

## 3. Feature-by-Feature Detail

### 3.1 Home — Your Leagues
- List of all imported leagues with platform icon, league name, format chips (`DYNASTY | SFLEXTEP PPR`, `DYNASTY | 1QB PPR`).
- Each row shows a color-coded **rank chip** — `1 / 14` (green), `5 / 12` (orange), `10 / 12` (red) — your power rank out of league size. Instant "health check" across all leagues at a glance.
- "Updated: 5/3 12:54 PM" + manual refresh icon.
- Rows tap through (chevron) to league context.

### 3.2 Home — League Hosts
- Manage connected fantasy-platform accounts. Captured: Sleeper, ESPN, and a third host — same username on two platforms supported simultaneously.
- Per host: username, "N LEAGUES SELECTED" (selective import, not all-or-nothing), Refresh button, edit (pencil), delete (trash).
- "+ ADD NEW" to connect more hosts. This is their moat vs. Sleeper-only tools: ESPN + others in one roster hub.

### 3.3 Trends — League Power Rankings
- Stacked bar chart, one bar per team, segments colored by position (QB red, RB green, WR blue, TE yellow/orange — same palette reused app-wide). Bar height = total roster value.
- Below: ranked team list with total values (e.g. `bkey5 — 60,251`), tap-through per team.
- League selector dropdown at top; position filter chips (QB/RB/WR/TE/**DP** — IDP support).
- "Updated 4/10 8:29 PM" + refresh.

### 3.4 Trends — Team Drill-Down
- Tapping a team highlights its bar in position colors while all other bars gray out — strong focus affordance.
- Header: team name, league name, format, **League Rank: 5/12**.
- Collapsible position-group cards, each header showing count + group value + group positional rank in league: `QUARTERBACKS (5) — 6,535 (3/12)`.
- Per player: headshot, name, NFL team, value, positional rank (`6,116 (QB2)`), zero-value players shown as `0 (NR)`.

### 3.5 Trends — Draft Pick Capital
- Dedicated `DRAFT PICKS` card: header summarizes inventory `(20: 9 1st, 4 2nd, 4 3rd, 3 4th)` with total pick value and league rank (`29,988 (1/12)`).
- Each pick valued individually; picks already assigned a slot show it (`2026 - 1.02 — 5,835`), traded-in picks show original owner (`2027 Mid 1st (twilson2320)`).
- Footnote: *"Pick proj using Contender rank and in-season performance"* — pick values are dynamic, derived from the original owner's projected finish. Far-future picks (2028) valued at 0/NR.

### 3.6 Players — Rankings
- Dynasty rankings table: overall rank + positional rank stacked in left column, headshot, name, NFL team chip, age (one decimal).
- **ADP** column and **DIFF** column (rank vs ADP delta; positive green = value vs market, negative red).
- Filters: QB/RB/WR/TE/DP/ROOKIES chips + **SFLEX** toggle (re-rank for superflex vs 1QB).
- Settings gear (presumably ranking preferences), help "?", "Updated: 6/9 9:35 PM".

### 3.7 Players — Shares
- Cross-league exposure report: every player you roster anywhere, with count + percentage of your leagues (`Drake Maye — 4 (80%)`), sorted by value.
- Answers "who am I over-exposed to?" — portfolio view across the 5 imported leagues.

### 3.8 Players — Free Agents
- League-scoped (uses global league dropdown). Available players sorted by dynasty **VALUE** with a **PROJ** column (0.00 in offseason captures).
- Same position-chip filters. Surfaces stash candidates the league has overlooked.

### 3.9 Trades — Browser
- Feed of **real executed trades** pulled from Sleeper leagues platform-wide (not just yours): Team A assets vs Team B assets with headshots/pick cards.
- Each card carries league context chips: platform (Sleeper League), Dynasty, format (SFLEX / SFLEXTEP), team count, starter count — so you can judge comparability to your league.
- Timestamped to the minute (`06/10/26 at 8:50 AM EDT`); colored edge bars beside each asset (appear to encode value/position). Filter button ("Filters: None") + refresh. Players' real-market comps engine, essentially.

### 3.10 Trades — Team Calc
- League-aware calculator: pick two actual teams from the selected league (dropdowns: `mattmurf77` vs `bkey5`), then choose assets from each real roster.
- Each side lists the team's players AND picks with values (`2026 - 1.02 — 5,835`). "Choose players above" CTA → presumably totals both sides and declares a winner ("compare and see who wins the trade").

### 3.11 Trades — Open Calc + Player Search
- Free-form calculator (no league context). Player picker is a modal: search field with typeahead, pre-seeded with top-value players (Bijan, Chase, JSN…), team-position chip per row. Total Value per side and "+ Add Player" slots visible behind the modal.

### 3.12 Drafts — Mock Configs
- Saved mock drafts list, each with: name (league-linked or "Non-league"), status badge (**NEW / STARTED / STOPPED** — resumable), round count (1–16), draft order type (**LINEAR / 3RR** — third-round reversal), and format tags (SUPER FLEX / TE PREMIUM / PPR).
- "+ ADD NEW" and bulk DELETE. Both rookie-only and start-up mock types.

### 3.13 Drafts — Live Mock Room
- Dark "On Clock" banner: END button, current drafter, pause control, progress/timer bar.
- Scrolling pick feed (1.05 Jordyn Tyson `NO - WR`…), current pick highlighted.
- Bottom sheet: PLAYERS / YOUR PICKS tabs, position chips, per-player DRAFT button, headshot, position+team, age with **(R)** rookie marker, overall rank number.

### 3.14 Drafts — League Draft Board
- Synced real league drafts: MOCK / LEAGUE DRAFT toggle, status ("Pre Draft"), last-sync timestamp + refresh.
- Pick list with usernames; **traded picks flagged** with a swap icon (1.04 mattmurf77 ⇄). Your picks highlighted.
- Player pool shows positional rank + overall rank on the left and dynasty value on the right (`Jeremiyah Love — RB5, #22 — 6,261`) — a live cheat sheet during real drafts.
- Bug observed: "Date: Wed Dec 31 1969" (unix-epoch zero rendering — they ship with rough edges).

### 3.15 Cross-Cutting
- **Single value currency**: one numeric dynasty value (~0–10k scale) powers rankings, rosters, picks, free agents, trade calc, and draft pools. Everything is comparable everywhere.
- Consistent position color palette across chips, charts, and bars.
- IDP ("DP") supported as a first-class position filter.
- Player rows everywhere: headshot, NFL team chip, age to one decimal, rookie (R) tag.
- Per-screen "Updated" timestamps + manual refresh throughout — sync transparency.

---

## 4. Notable Takeaways vs Fantasy Trade Finder

1. **The trade browser is their killer comp engine** — real executed trades with league-format context. FTF's mutual-gain *discovery* is different (proactive vs observational); the two are complementary, not equivalent.
2. **Pick valuation is dynamic** (contender-rank-based pick projections, original-owner tracking). FTF v2 should decide how picks are valued relative to the Elo player pool.
3. **Cross-league portfolio views** (rank chips on Home, Shares exposure) create daily-open habit loops cheaply.
4. **Multi-host import** (ESPN etc.) is their breadth play; FTF is Sleeper-only today.
5. Polish is uneven (epoch-zero date bug, 0.00 PROJ columns) — speed-to-feature clearly prioritized over QA.
