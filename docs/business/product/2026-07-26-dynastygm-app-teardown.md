# DynastyGM (Dynasty Nerds) mobile app — teardown from operator screen recording

**Source:** operator screen recording, 2026-07-26 (app v2.7.4, ~110s walkthrough).
**Why it matters:** operator wants FTF's League Summary to replicate DynastyGM's
League Analyzer presentation (vertical bars + starters/bench/position filtering).

## Navigation model

- **6-item bottom tab bar:** Home (leagues) · Analyzer (League Analyzer) ·
  Players · Trades · [grid tool] · Profile.
- **Persistent league-context switcher in the header** of every league-scoped
  tab (league name + chevron dropdown) — switch leagues without leaving the
  current tool. Global search + hamburger flank it.
- League context follows you across tabs (Analyzer, Free Agents, Trades all
  scope to the header league).

## Home tab — leagues + hosts

- **Your Leagues list:** per-league row = host icon, name, format subtitle
  ("DYNASTY | SFLEXTEP PPR"), and **your rank / league size** color-coded
  (green 1/14, amber 5/12, red 10/12). Rank-at-a-glance across every league
  is the hook.
- **League Hosts tab:** multi-platform account aggregation — MFL, ESPN,
  Sleeper accounts each a card with "N LEAGUES SELECTED", edit/delete,
  per-host Refresh, + Add New. (FTF's mfl.auth_link import-all is the same
  idea; theirs is a first-class management surface.)

## League Analyzer (the screen to replicate)

- **Position pills row** (QB/RB/WR/TE/DP, each in its position color) above
  the chart. Tap a pill → chart isolates that position (single-color bars,
  re-ranked league-wide). No pill → **stacked vertical bars**, one segment
  per position in position colors.
- **Vertical bars, x-axis = rank 1..N.** Your team's rank numeral is
  highlighted on the axis. "Updated <ts>" + refresh icon top-right of the
  card; league name + "DYNASTY - 1QB PPR" caption below.
- **Ranked list under the chart:** rank numeral, team name, total value,
  chevron; your row highlighted. Tap row or bar → drill-in.
- **Drill-in (team focus):** selected team's bar keeps full color, every
  other bar goes **grayscale (segments still visible, muted)** — the
  strongest visual idea in the app. Caption swaps to team name +
  "League Rank: 1/12". X for exit.
- **Roster panel with a segmented filter: All · Optimal · Starters · Bench.**
  Position groups with colored headers: "QUARTERBACKS (2) — 7,677 (2/12)"
  (positional total + positional rank IN league). Rows: headshot, name,
  (NFL team), value + positional rank (QB2 / RB62 / NR).
- **The filter re-computes the whole league chart, not just the roster:**
  Bench selected → bars become bench-only values, league re-ranked (operator's
  team fell 1→10), team highlight follows its new rank, group headers show
  bench totals + bench positional ranks, starters grayed in the list.
  Answers "who has the best bench / best starters / best QB room" in one tap.
- Filters compose: position pill × starters/bench × drill-in.

## Players tab

Sub-tabs: **Rankings · Shares · Free Agents · Data Hub.**
- **Rankings:** pills + ROOKIES + scoring-format toggle (PPR); rows carry
  overall rank + positional rank badge, headshot, pos/team/age, **ADP and
  DIFF vs ADP** (green/red). Settings gear for the sheet.
- **Shares:** cross-league **exposure** — "Drake Maye 4 (80%)" = rostered in
  4 of 5 leagues. Sorted by count. (FTF has no cross-league exposure view;
  natural Portfolio extension.)
- **Free Agents:** league-scoped, Value + Proj columns, K pill included.

## Trades tab

Sub-tabs: **Browser · Team Calc · Open Calc.**
- **Team Calc:** two-column side-by-side — team dropdown per column, full
  rosters value-desc (headshots, value, pos-team chip), **draft picks inline
  as assets** (DRAFT badge, "2027 - 1 · 2,816"). Tap to move into the trade.
- Verdict banner: "**No Team Name wins the trade by 1,287 points**" with
  per-side Total Value bars (red/green dots + direction arrows).
- **"RECOMMENDED" evener rows** on the winning side: value-ranked add-on
  players with + buttons to balance the trade (their version of FTF's
  gap/pick-equivalent, but actionable inline).
- Collapsible **ROSTERS drawer** pinned at bottom.
- **Open Calc:** free-form any-player two-column calculator (no league).

## FTF vs DynastyGM — gaps and advantages

**Where they're ahead (presentation/navigation):**
1. Vertical rank-axis bars + drill-in grayscale focus beats FTF's horizontal
   track rows for scanability.
2. Starters/Optimal/Bench league-wide re-ranking — FTF has no starter/bench
   dimension anywhere.
3. Persistent header league switcher on every tool tab (FTF switches league
   from the League home page).
4. Home league list with color-coded your-rank per league (FTF's picker is
   plain).
5. Cross-league Shares/exposure view (FTF Portfolio is single-league).
6. ADP + DIFF columns in rankings.
7. Trade calc: inline "recommended evener" add-ons; rosters drawer.

**Where FTF is ahead:** mutual-gain suggestion engine (DynastyGM has no
find-me-a-trade), personal-board Elo values + two-board fairness, pick
pool-value pricing + gap-as-pick verdict, guided ranking flows, outlook
steering, hub modes, odds pipeline (dark), in-app feedback loop.

## Replication scope for FTF League Summary (operator-approved direction)

1. Vertical stacked bars (position hexes), x-axis rank, "you" highlight.
2. Position pills = isolate + re-rank (exists today as filter — keep).
3. NEW: All/Starters/Bench (+Optimal later) segmented filter recomputing
   league-wide values → needs backend starters/bench split per team
   (Sleeper rosters carry `starters`; MFL bundle has lineups).
4. Drill-in keeps colored bar, grays the rest; roster groups get positional
   totals + in-league positional ranks; per-player positional ranks.
5. Keep FTF's basis toggle (Consensus | My board) — a dimension DynastyGM
   doesn't have.
