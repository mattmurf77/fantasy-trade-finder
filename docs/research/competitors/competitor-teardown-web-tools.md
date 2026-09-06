# Competitor Teardown — Web Trade Tools (5 sites)

*Source: direct HTML fetches, public APIs, and sitemaps, 2026-06-10. Covers FantasyCalc, Dynasty Daddy, DynastyTradeCalculator, FPTrack, and Dynasty Dealmaker. Companion docs: [competitor-teardown-dynastygm.md](competitor-teardown-dynastygm.md), [competitor-teardown-dynastydealer.md](competitor-teardown-dynastydealer.md). DLF Trade Analyzer still inaccessible (Cloudflare 403) — pending manual capture.*

---

## 1. FantasyCalc — fantasycalc.com

**Positioning:** market-derived values; calculator + league tools. Free. React/JS SPA over a fully open API.

### Page tree (from sitemap)
```
/                      — home
/trade-calculator      — main calculator
/trade-value-chart     — flat value chart
/dynasty-rankings      — dynasty values
/fantasy-football-rankings — redraft values
/dynasty-rookie-rankings   — rookie values
/database              — trade database
/fantasy-football-draft-app — draft tool
/add-your-league       — league data contribution
/league/import         — league import
/league/dashboard      — league dashboard
/league/players-overview · /team-comparison · /teams-overview
/about · /contact · /frequently-asked-questions · /blog
```

### Features & data model (from `api.fantasycalc.com`)
- **Open API**: `GET /values/current?isDynasty=&numQbs=&numTeams=&ppr=` returns the full dataset. Values are parameterized by league shape (1QB vs SF, team count, PPR) rather than fixed toggles.
- Per player: dynasty value, **redraft value, and the dynasty↔redraft difference** (absolute + %), overall/position rank, **30-day trend**, tier, moving standard deviation (volatility), **trade frequency** (how often the player is actually traded), and cross-platform IDs (Sleeper, MFL, ESPN, Fleaflicker, FFPC, espn/yahoo).
- Values are **derived from real trades in synced leagues** (the `add-your-league` flow feeds the dataset; tradeFrequency is a first-class field) — market-observed, not crowd-voted or expert-set.
- League suite: import → dashboard, team comparison, teams/players overviews.
- Combined dynasty+redraft "combinedValue" field suggests blended-format support.

### Notable
- The entire product is effectively a public API + thin UI. Many other tools (and spreadsheets) consume FantasyCalc data — distribution via openness.
- Trade database = browsable record of real trades (same observational-comps idea as DynastyGM's browser).

---

## 2. Dynasty Daddy — dynasty-daddy.com

**Positioning:** "ultimate free fantasy football analytics platform" — breadth play, free, solo-dev (Jeremy Timperio). Angular + Node/Express + Postgres. Originally built on scraped KeepTradeCut values; **now offers selectable "Fantasy Markets"** — pluggable value sources, each updating daily:
- **Dynasty Daddy** (their own market): calculated from real fantasy trades and real drafts
- **ADP Daddy**: from real draft ADP
- **KeepTradeCut**: crowd Keep/Trade/Cut datapoints
- **DynastyProcess**: from FantasyPros ECR rankings
- "and more"

The user picks which market prices the whole app. No other tool exposes the value source as a switch.

### Page tree (from sitemap)
```
Tools
├── /trade-calculator        ├── /trade-database
├── /trade-finder            ├── /player-rankings · /dynasty-rankings
├── /player-comparison       ├── /player-statistics
├── /start-sit-tool          ├── /waiver-wire
├── /playoff-calculator      ├── /fantasy-mock-draft
├── /fantasy-league-rankings ├── /league-standings
├── /fantasy-portfolio       ├── /league-format
├── /wrapped                 └── /fantasy-redzone
Games (engagement layer)
├── /trivia · /gridiron · /reverse-gridiron · /wordle · /connections
├── /nfl-team-game · /nfl-draft-game · /nfl-strands
└── NBA variants (wordle/connections/team-game/strands)
```

### Features & data model (from `dynasty-daddy.com/api/v1/player/all/today`)
- 705 players; per player: **1QB AND SuperFlex values** (separate fields), position ranks for both, **all-time / 3-month / 1-month highs, lows, best & worst ranks** — historical value context is a core data-model concept, not an add-on chart.
- Multi-source ADP: FantasyPros, BB10s, RTSports, Underdog (averaged).
- Cross-platform IDs: Sleeper, MFL, Fleaflicker, ESPN, Yahoo, FFPC, Fantrax.
- **/trade-finder** — has a discovery tool (closest overlap with FTF; web equivalent of DynastyDealer's Fair Trade Finder).

### Trade calculator detail (desktop screenshots, 2026-06-10)
- **League-aware**: log in → sides become real team names ("mattmurf77 gets… / Team 2 gets…"); Superflex toggle; per-side piece count + value total; Share / Clear / **Send Trade** buttons (send into the league platform).
- **Fantasy Market selector** sits on the calculator itself — same trade priced by Dynasty Daddy, KTC, DynastyProcess, etc.
- **"Even Out Trade"** button under the lighter side: auto-builds a fair trade from the actual rosters and lists recommended players to balance, filtered to the two teams in the trade. Calculator-embedded discovery-lite.
- **Post-trade simulation ("mock power rankings")**: a Team Position Ranks panel shows both teams' league rank per category (Starters, QB, RB, WR, TE, Picks) with rise/fall arrows *as if the trade went through*, team tier labels ("Contender," "Trust the Process"), and a **Contender Mode** toggle for current-season tiers/ranks.
- **Trade Demand panel**: per-player trade value over past 40 days, demand (completed-trade volume) over past 8 weeks, past-week trade volume ordered by value, and **updated season simulations if the trade were accepted** (logged in).
- **Verdict banner**: "Favors DynastyDaddyFF — Add a player with 1,478 value to even trade → View in Player Comparison" — names the winner and quantifies the exact gap.
- **"Value Adjustment"** (their package-discount formula, from their docs): *"a calculated value to determine how much a player is worth in context of the trade. I wanted to make sure the fair trades weren't splitting a dollar into 100 pennies. Under the hood, the formula takes into consideration who is the key player in the trade and what proportion of the trade he accounts for."* Same problem FPTrack's Crown Asset solves — key-asset premium scaled by its share of the package.

### Other tools (homepage carousel, 2026-06-10)
- **Playoff Calculator** — "simulate 10k seasons"; per-record playoff/title probabilities.
- **Power Rankings** — stacked value bars + contender tiers per team: **Contender / Frisky / Rebuilding**, with overall/starter/QB rank columns.
- **Fantasy Portfolio** — "track players like stock": total-value time series, shares, exposure %, price (SF), per-league format/size rows across Sleeper + Yahoo.
- **Trade Database** — "real-time trades & trends" visualized as a bubble chart (bubble size = trade volume).
- **Fantasy Redzone** — live "every point from every game" scoring across leagues.
- **Start/Sit** — projections aggregated from Sleeper, FantasyPros, FanDuel, NFL, CBS, FF Today + past production (PPG, std dev) + Vegas matchup (spread, O/U).
- **Waiver Wire** — winning-bid (FAAB) analytics charts.
- **OBS Plugin ("Stream Suite")** — player-overlay control for streamers; **Discord Bot** — community integration. Creator-ecosystem distribution no other competitor has.
- **/fantasy-portfolio** — cross-league exposure/holdings (same concept as DynastyDealer Portfolio and DynastyGM Shares).
- **/wrapped** — Spotify-Wrapped-style season recap; pure shareable/viral play.
- **Games arm** (wordle/connections/trivia/gridiron, even NBA) — daily-habit traffic engine decoupled from fantasy season.

### Notable
- Free + donation model (Buy Me a Coffee); values are *borrowed* (KTC scrape), so the moat is UX breadth, not data.
- Validates the "league rankings / power rankings / playoff odds" cluster as table stakes.

---

## 3. DynastyTradeCalculator — dynastytradecalculator.com

**Positioning:** calculator-first brand (WordPress site + JS calc app) with strong methodology opinions. Subscription content/podcast network attached.

### Page tree
```
/calculator/     — the trade calculator
/trade-wire/     — trade feed/news
/player-news/    — news
/podcasts/       — podcast network
/contact-us/
```

### Calculator methodology (their own "About the Calculator" copy)
- Values = **"open market (vacuum) player value"**; displayed value is the **mean of a player's buy line and sell line**, adjusted to the user's league parameters.
- Explicit anti-fairness framing: *"the trade calculator is not intended to be conclusive, or decide 'fairness'… prices are determined by you and your league mates."* They position the calc as an input, not a verdict.
- **Player pool toggles: Offense, IDP, and Devy** (developmental/college players; Devy IDP "coming soon") — deepest format coverage seen.
- League size: 10 / 12 / 14 / 16 — smaller leagues bump elite values, larger leagues weight depth.
- Scoring: PPR / .5 PPR / Non-PPR (4pt pass TD assumptions documented).
- Formats: Standard, **SF, 2QB (valued above SF), RB PPC (point-per-carry), TE Premium**.

### Notable
- Buy-line/sell-line spread is a genuinely different valuation concept (bid/ask, not a single number).
- 2QB treated as distinct from (and more QB-valuable than) Superflex — rare nuance.

---

## 4. FPTrack — fptrack.com

**Positioning:** multi-sport (football/hockey/baseball) content + tracking platform with a serious dynasty trade calculator embedded. Next.js, server-rendered.

### Page tree (football slice)
```
/football/trade-calculator — dynasty calculator w/ league sync
/football/player-rankings · /trending · /start-sit · /outlooks
/football/editorial · /news
/pricing · /podcasts · /writers · /discord-bot · /about
+ Track Hub, Draft Wire, Trade Wire, Lineup Wire (product surfaces)
```

### Trade calculator
- **League sync: Sleeper, Fantrax, Yahoo, MFL** (widest sync seen) — live roster settings + values; "Sending or Receiving" per-side framing.
- Scoring toggles STD/Half/PPR + SF + TEP; **Startup Draft Mode** (more rounds/picks).
- **Manual pick builder with slot precision**: year 2026–2028 × round 1–5 × pick 1–16.
- **Published "Value Boosts" modifier system**:
  - *Crown Asset* — best asset gains value in 1-for-many deals (explicit package discount / quantity-bias fix)
  - *Draft Value Boost* — high-end picks +10–45%
  - *Solo Future 1st* — lone future 1st premium (early/mid/late tags)
  - *Dominance Factor* — production lifts value above market
  - *Star Power* — position-relative leader premium, larger for thin pools (TE)
  - *Age Adjustment* — youth runway bonus / veteran penalty by position
- Save trades (account), values displayed in "pts."

### Desktop UI observations (screenshots, 2026-06-10)
- Connect row: four platform icon chips (Sleeper, Fantrax, Yahoo, MFL); the **League Context dropdown is disabled until a platform is connected** ("Connect a Platform First") — sync is the intended default path, manual mode the fallback.
- Sides labeled "Your side receives / Trade partner receives," each with a running **pts** total; center panel prompts "Add assets to see trade analysis."
- Each side has its own search + scrollable "Available Player Pool" (top players pre-listed).
- **Free tier is heavily ad-loaded**: banner ads mid-page, an autoplaying video ad pinned bottom-right, plus an editorial/news right rail sharing the calculator page. Ad-free is a headline Pro benefit for a reason — the free tool experience is degraded by design.

### Pricing
- **Free**: manual tracking up to 50 players/sport; Track Hub + Draft/Trade/Lineup Wires (20 active each); wire voting; injury/news on tracked players; full push notifications.
- **Pro $24.99/yr** (or monthly at ~30% more): ad-free, unlimited tracked players, 50 wires, **league sync (4 platforms, unlimited leagues), advanced injured/starter notifications, league-specific power rankings, waiver targets, and trade suggestions**.

### Notable
- "Trade suggestions" are a Pro feature — another player in automated trade discovery, at a much lower price point ($24.99/yr vs DynastyDealer's $49.99/yr).
- Push-notification-first "wire/tracking" model is a retention angle nobody else here has.

---

## 5. Dynasty Dealmaker — dynastydealmaker.com

**Positioning:** AI-native trade tool, web app, Sleeper-sync, token-metered pricing.

### Structure
Linear marketing site (Features / How It Works / Pricing / Login) over the app. Workflow: sync league → identify targets → execute trade.

### Features (from site copy)
- **Trade analysis**: instant evaluation against league-specific scoring + rosters; **trade acceptance probability** with strategic reasoning; "98% Fair" assessment claim.
- **Trade discovery**: automated scanning for realistic trade partners; detects **rebuild vs contend windows**; identifies positional needs and asset targets per team.
- **Team assessment**: contender-vs-pretender analysis; "agent-driven research."
- **League integration**: Sleeper sync, daily auto-update, read-only, multi-league.

### Pricing
- Free: **5 weekly tokens**, basic analysis.
- GM: **$1.49/week** → 35 weekly tokens, advanced analysis, full research.

### Notable
- The only competitor that frames output as **acceptance probability + reasoning** rather than a value delta — closest *conceptually* to FTF's "will this trade actually happen" angle.
- Token metering = LLM cost pass-through; per-analysis economics, not flat sub.
- Read-only by design (contrast DynastyDealer's full write access).

---

## 6. Comparative Takeaways for Fantasy Trade Finder

**The trade-discovery field is now crowded at the feature level:**
| Tool | Discovery feature | Price | Angle |
|---|---|---|---|
| DynastyDealer | Fair Trade Finder (AI) | $5.99/mo | fairness-balanced offers |
| Dynasty Daddy | /trade-finder + "Even Out Trade" + post-trade rank/season sims | free | multi-market values, roster-aware balancing |
| FPTrack | "trade suggestions" (Pro) | $24.99/yr | league-specific suggestions |
| Dynasty Dealmaker | partner scanning + acceptance probability | $1.49/wk tokens | AI reasoning, contend/rebuild fit |
| **FTF** | mutual-gain Elo discovery | — | both teams improve vs own rankings |

FTF's differentiation is the **personal Elo ranking layer** (trades judged against *your* values, not a global market number) — no one here has that. Defend it loudly.

1. **Value methodology is the real battleground.** Four distinct approaches observed: market-observed real trades (FantasyCalc, Dynasty Daddy's own market), crowd voting (KTC, DynastyDealer), buy/sell spread (DTC), modifier stack on base values (FPTrack). FTF's per-user Elo is a fifth. Dynasty Daddy goes a step further and makes the value source a **user-selectable switch** ("Fantasy Markets") — an implicit admission that no single market is authoritative, and a strong frame for FTF: *your Elo is just your personal market*. Publishing *how* values work (FPTrack's boost table, DTC's about page) is a trust pattern worth copying.
2. **Package-discount handling is a solved, public pattern** — FPTrack's Crown Asset boost and Dynasty Daddy's Value Adjustment ("don't split a dollar into 100 pennies"; key-player premium weighted by his proportion of the trade) both address it. Directly relevant to the trade-engine-v2 1-for-1 fairness-gate watch item: the industry consensus is an explicit key-asset multiplier, not a hard gate.
3. **2QB ≠ SF** (DTC) and parameterized values by league size/format (FantasyCalc API) set the bar for league-context sensitivity.
4. **Open API as distribution** (FantasyCalc, Dynasty Daddy unauthenticated endpoints) — consider whether FTF's Elo-derived values could be an API/marketing surface later.
5. **Pricing spans $0 → $1.49/wk tokens → $24.99/yr → $5.99/mo.** Discovery features are consistently the paywalled tier; calculators are consistently free/metered bait.
6. **Engagement layers** are everywhere: Dynasty Daddy's games + Wrapped, FPTrack's push wires, DynastyDealer's vote streaks. FTF's 3-player matchup ranking flow is its native engagement loop — gamify it (streaks, recaps).
7. Historical value context (Dynasty Daddy's all-time/3-month highs-lows per player) is cheap to store and adds perceived depth.

**Still missing:** DLF Trade Analyzer (403) and screenshots of DynastyDealer's Fair Trade Finder output + Dynasty Daddy's /trade-finder UI — capture these to complete the discovery-feature comparison.
