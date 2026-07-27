# DynastyDealer + Dynasty Trade Factory — teardowns from operator recordings

**Source:** two operator screen recordings, 2026-07-26 (~187s + ~151s).
**Operator read:** "I don't think there's much the apps do better… potentially
some minor polish work to consider." Confirmed — both are calculator-first
tools with no mutual-gain engine, no personal boards, no guided ranking.
Notes below focus on presentation polish worth borrowing.

---

## App 2 — DynastyDealer (dark "market" toolkit; Sleeper-only, community values)

**Nav:** Home · Market · [center calculator FAB] · League · Vote. Dark navy,
electric-blue accents, ALL-CAPS microlabels; premium-analytics branding
("Command Center"). Community-driven values (users vote on trades → VOTE tab).

**Trade Hub** (Calculator / Trade DB / Trade Finder / Charts):
- League sync by Sleeper username → league chip; **2-WAY / 3-WAY** toggle
  (3-team calculator!); SF/TE+ chips.
- **FAIR ↔ UNEVEN meter** = full-width bar split by each side's share, label
  flips FAIR (green) / UNEVEN (red) with the raw value gap number on the bar.
- **"+668 STUD BONUS"** shown under a side's total, and a collapsible
  **"Trade Adjustments Breakdown"** panel itemizing each adjustment per team
  with plain-language rationale ("elite assets are harder to acquire, earning
  a value bonus"). Transparent premium itemization — FTF applies a crown/stud
  consolidation premium internally but never itemizes it.
- **"Add to Team B to even trade →"** expander (their evener).
- **"Screenshot & Share"** — renders the trade card to a PNG → native share
  sheet. Slicker than FTF's text share.

**Market Hub** (Rankings / Rookies / PRISM):
- Filter pills include **PICKS and IDP** as first-class asset classes.
- League-context chip on the rankings ("La Resistance · 1QB · Change") —
  values shown in the league's format.
- **Top Risers / Top Fallers side-by-side cards (14 days)** above the list.
- Rows annotate community evidence: "Rising: above market price in **83% of
  trades**."

**League Hub** (Portfolio / Recon / Dispersal):
- **Recon**: analyze ANY Sleeper username + league year (scout your leaguemates
  — FTF backlog #48 validation, second competitor doing it after RosterAudit).
- Portfolio tool chips: Trades, Dashboard, Analysis, Injuries, Lineups,
  **Waivers**, Live Draft, News Feed.
- **Waivers/Claim flow (direct #179 reference):** FA list with values +
  Claim buttons → sheet with **FAAB bid input + "$994 remaining" budget**,
  "Select a player to drop (or claim directly if you have open slots)" with
  value-sorted drop candidates (cheapest first), and **"Add Without
  Dropping"** when slots are open. Roster-limit/FAAB awareness built into the
  add UX.

---

## App 3 — Dynasty Trade Factory ("DTF"; Sleeper-import, calculator-first)

**Nav:** landing page with username import + 4 tool cards (Trade Analyzer /
Smart Trade Finder / League Analyzer / Top Assets). No tab bar — hub-and-spoke
with Back buttons. Copy voice: "Trade with your head, not heart."

**Trade Analyzer:**
- Partner picker rows show an inline **positional value summary, color-coded
  per position** ("bkey5 · QB 930 | RB 2225 | WR 2948 | TE 856") — you see a
  team's shape before you even open the trade. My Team line includes PICKS.
- Dynasty/Redraft + Superflex/1QB + TEP toggles.
- Full-roster Add lists per side (players + Draft Picks section), values inline.
- **Sticky verdict header** while scrolling: TEAM A 801 · "+801 Strong edge to
  Team A" · TEAM B 0, with a gradient balance slider.
- **Trade Snapshot** card: "Value gap: 140. **Starter impact: Team A likely
  gains more immediate lineup value.**" — a lineup-impact one-liner next to
  raw value.
- **Counter Suggestions:** "Team B is about 140 value short" →
  "**Woody Marks — best single-piece fix (130)**" AND "**Or try a 2-piece
  package: Elijah Arroyo + Travis Kelce (140)**". Single + multi-piece eveners.
- **Team A/B Analysis tables:** PLAYER · POS · AGE · ADP · VALUE · TIER
  (Starter/Bench badge per player in the trade).

**Smart Trade Finder:**
- Pick one of YOUR assets + "Include picks" / "Include packages" checkboxes →
  results grouped **"Upgrade Ideas" vs "Downgrade Ideas"** (tier-up/tier-down
  — validates FTF feedback #172), each row "Drake Maye ↔ Derrick Henry +
  Justin Jefferson · Team: bkey5 · Total value · Difference: −11", ordered by
  closeness.
- **Team Analysis** mode: "Current Build" (strongest/weakest position,
  per-position value + player-count tiles), then per-counterparty suggested
  trades with "+45" gain, **"Why this trade works"** expander, and **"Open in
  Trade Analyzer"** handoff (finder → calculator continuity, FTF's #190
  equivalent).

**League Analyzer:**
- Educational "What to do with it" copy block (surplus teams = trade partners).
- Two league-wide stacked charts: **Depth (player counts) by position** and
  **Total Roster Value by position**, both with a **League Average dashed
  line** overlay, and **PICK as a first-class stack segment**.

---

## Polish candidates for FTF (ranked, operator to choose)

1. **Itemized adjustments breakdown** in the calculator verdict (DynastyDealer):
   surface the consolidation/crown premium, TEP uplift, waiver-slot cost etc.
   as labeled rows with plain-language whys — the math exists; only the
   itemization UI is missing. Pairs with `trade_math.human_explanations`.
2. **League Average marker** on the League Summary bars + PICK segment in the
   stack (DTF League Analyzer; FTF already has the picks filter/segment data).
3. **Starter-impact line** in the calculator verdict ("Team A likely gains
   more immediate lineup value") — derivable once the League-Summary agent's
   optimal-lineup computation lands (same starters logic, reused).
4. **2-piece package evener** ("or try: X + Y") in the eveners feature —
   single-piece is already in flight.
5. **Share-as-image** for trades (render card → PNG → share sheet).
6. **Partner-picker positional summary** (color-coded QB/RB/WR/TE values +
   picks inline in the calculator's opponent selector).
7. **Top Risers / Fallers cards** on Trends once history accumulates (#164's
   fix started recording 2026-07-25).
8. **Upgrade/Downgrade grouping** for finder results when a single asset is
   targeted (maps to #172's tier-up/tier-down intents).
9. **Recon** (scout any username) — third competitor validation for backlog
   #48; bigger than polish.
10. **FAAB-aware FA add sheet** (bid input + budget + drop suggestions) —
    extends #179's honest add flow if/when a write path exists; the drop-
    candidate suggestion works even for the deep-link flow today.

---

## Operator decisions (2026-07-26)

- **Risers/fallers + market-driven rankings** (app-wide AND league-specific):
  not now — but ensure the DATA ARCHITECTURE exists to build later →
  market-data readiness audit/plumbing tasked (see docs/plans/market-data-readiness.md when it lands).
- **Waiver claim / FAAB / budget remaining / value-sorted (ascending) drop
  candidates:** TOP PRIORITY → in build (claim-preparation sheet; Sleeper
  executes, FTF prepares).
- **Visible trade adjustments breakdown:** approved (assuming simple) → in build.
- **3-way trades:** fun, not important → BACKLOG.
- **Counter suggestions:** loved; shipped as calculator eveners (incl. 2-piece
  packages); ALSO to serve as the "player changer" on find-a-trade deck cards →
  follow-up after the asset-ideas build lands.
- **Upgrade/Downgrade/Lateral grouping on single-asset targeting:** "literally
  exactly what I expect" (the #189 complaint's real fix) → in build
  (trade.asset_ideas).
- **Pick stack segment + filter-aware league-average line on League Summary:**
  approved → amended into the in-flight League Analyzer replication build.
