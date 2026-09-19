# Competitor Teardown — DynastyDealer (iOS)

*Source: 27 iPhone screenshots captured 2026-06-10 (IMG_9339–9365). App: DynastyDealer by Elliot Pollaro (dynastydealer.com). Version observed: v1.1.1.7. Complements the website fetch that returned only a JS shell.*

---

## 1. Page Tree

```
App
├── Onboarding
│   └── Mode select: DYNASTY vs REDRAFT ("the whole app adapts", switchable anytime)
│
├── Bottom nav: HOME · MARKET · [Calculator FAB, center] · LEAGUE · VOTE
│
├── Tab 1 — HOME
│   ├── Dynasty/Redraft mode toggle (persistent, top)
│   ├── Quick actions: Trade Calc · Rankings
│   ├── Plan card: Free vs Premium ($5.99/mo, $49.99/yr) + upgrade CTA
│   ├── Command Center (below fold)
│   └── Notifications + account (top-right)
│
├── Tab 2 — MARKET HUB ("Real-time player values and trade trends")
│   ├── Rankings
│   ├── Rookies
│   ├── PRISM (prospect model)
│   │   ├── Prospects — graded list w/ class-year + position filters
│   │   └── Combine — sortable table (PRISM, RAS, 40yd, speed, ht, wt)
│   └── Charts (reachable from Trade Hub too)
│       ├── Overall Market index + ticker tape + Rotowire news crawl
│       ├── DD Indices: Overall · Top 50 · QB · RB · WR · TE · Rookie
│       ├── Chart overlays: Bollinger, SMA, EMA, RSI, MACD, Log, Compare
│       ├── Stats: constituents, VIX, breadth, market cap
│       ├── Performance: 1W/1M/3M/6M/YTD/1Y
│       └── Players / Picks value lists + watchlist
│
├── Center FAB — TRADE HUB ("manual and automated deal-making suite")
│   ├── Calculator — SF/TE+ toggles, league SYNC, 2-way/3-way, FAIR meter
│   │   └── Sync League Settings modal (Sleeper username)
│   ├── Trade DB
│   ├── Trade Finder (AI "Fair Trade Finder" — premium)
│   └── Charts
│
├── Tab 3 — LEAGUE HUB ("Portfolio and scouting tools")
│   ├── PORTFOLIO (your account, @switchable)
│   │   ├── Tool chips: Trades · Dashboard · Analysis · Injuries ·
│   │   │              Lineups · Waivers · Live Draft · News Feed
│   │   ├── Trades → Offers (accept/modify/decline real Sleeper offers)
│   │   │          → History
│   │   │          → Mass Send (same trade to every eligible league)
│   │   ├── Summary: leagues count, unique players, position distribution,
│   │   │   overall record (W/L, win rate, avg rank), multi-league players
│   │   ├── Your Leagues cards (rank, record, players, trades, avg age/exp)
│   │   ├── Team Portfolio Value chart + Team Rankings
│   │   ├── Roster Breakdown (per-position groups w/ player values + ages)
│   │   ├── Optimal Starting Lineup (slot-by-slot)
│   │   └── Waivers (free agents w/ values + in-app Claim)
│   ├── RECON — scout ANY Sleeper username (year, league-type & settings
│   │   filters; Players exposure + Rookie Targets views)
│   └── DISPERSAL — live dispersal draft tool (create/join via link,
│       commissioner flow, picks auto-sync to Sleeper via 2FA)
│
├── Tab 4 — VOTE HUB ("Influence market values by voting")
│   ├── Vote — Start/Sit/Drop game (3 players, streaks, daily count)
│   ├── Leaderboard — top voters
│   └── Polls
│
└── Auth overlays
    ├── Sleeper 2FA sign-in (username/email/phone → Send Code, or manual token)
    └── "Credentials sent directly to Sleeper; tokens stored locally"
```

---

## 2. Feature List

| # | Feature | Free/Premium |
|---|---|---|
| 1 | Dynasty ↔ Redraft app-wide mode switch | Free |
| 2 | Trade calculator (SF, TE+, league sync, FAIR meter) | Free, 5 trades/day |
| 3 | Unlimited trade calculator | Premium |
| 4 | 3-way trade calculator | Premium (gated toggle) |
| 5 | **Fair Trade Finder (AI-powered)** | Premium |
| 6 | Trade Database | Free |
| 7 | Stock-market value charts (indices, technical overlays, VIX/breadth) | Free-ish |
| 8 | Watchlist | Premium |
| 9 | Trade Tracker | Premium |
| 10 | Dynasty rankings + rookies | Free |
| 11 | PRISM prospect model (grades + combine data) | Premium |
| 12 | Portfolio analysis (cross-league record, exposure, value rank) | Premium |
| 13 | Roster Recon — scout any Sleeper username | Premium |
| 14 | In-app Sleeper trade offers: accept / modify / decline | Free w/ Sleeper auth |
| 15 | **Mass Trade Sender** — same offer to all eligible leagues, sent in Sleeper | Premium |
| 16 | Optimal lineup optimizer | Premium |
| 17 | Waiver wire w/ in-app claims | Premium |
| 18 | Dispersal draft tool (live, commissioner-run, auto-sync) | Premium |
| 19 | Draft Rush (mini-game, not captured) | Free |
| 20 | Community voting (Start/Sit/Drop) feeding market values + leaderboard/polls | Free |
| 21 | Injuries, news feed (Rotowire), live draft, dashboards | Mixed |

Monetization: Free $0 forever (calculator 5/day, rankings, trade DB, voting, Draft Rush) vs **Premium $5.99/mo or $49.99/yr**.

---

## 3. Feature-by-Feature Detail

### 3.1 Onboarding — Mode Select
First-run asks "How do you play?" with two cards: **Dynasty** (keeper/dynasty values, rookie picks, long-term roster building) and **Redraft** (single-season values, this-year rankings, in-season trades & waivers). The entire app re-skins per mode; a persistent Dynasty/Redraft pill toggle lives on Home. One codebase serving two markets.

### 3.2 Home / Monetization
Marketing-forward home ("Build a Dominant Dynasty Empire — the industry's most advanced community-driven toolkit"), quick links to Trade Calc and Rankings, then the paywall card laid out as a feature checklist. Free: Trade Calculator (5/day), Dynasty Rankings, Trade Database, Community Voting, Draft Rush. Premium ($5.99/mo, $49.99/yr): Unlimited calculator, **Fair Trade Finder (AI-Powered)**, Portfolio Analysis, Roster Recon, PRISM Prospect Model, Trade Tracker, Watchlist, Dispersal Drafts, Lineup Optimizer, Waiver Wire, **Mass Trade Sender (Send in Sleeper)**.

### 3.3 Market Charts — Full Stock-Market Metaphor
The signature design choice: dynasty values presented as an equities market.
- **Overall Market index**: total value of top 200 players indexed to 1000, explicitly pitched as "the S&P 500 of dynasty" (observed: 957.4, +0.27%).
- **DD Indices**: Top 50, QB, RB, WR, TE, Rookie — each with daily % change.
- Scrolling **ticker tape** of index moves + a **Rotowire news crawl**.
- Chart timeframes (1M→ALL) and genuine technical overlays: Bollinger bands, SMA, EMA, RSI, MACD, log scale, compare mode.
- Stats: constituents (200), **VIX 0.28** (volatility), **breadth 133↑/63↓**, market cap.
- Performance summary (1W/1M/3M/6M/YTD/1Y), watchlist, Players/Picks value lists (Josh Allen 9,927 top) with trend-colored edge bars.

### 3.4 Trade Hub — Calculator
Tabs: Calculator / Trade DB / Trade Finder / Charts. Calculator has SF and TE+ format toggles, a **SYNC** button (modal asks for Sleeper username to import league settings), **2-WAY/3-WAY** selector (3-way gated), a **FAIR meter** bar that fills as the trade balances, Team A/Team B running totals, typeahead search and "Add Asset" slots. Free-tier counter shown in-context: "0/5 free trades today."

### 3.5 Trade Hub — Fair Trade Finder (AI)
Premium headline feature (marketed as "instantly surfaces balanced offers for any roster"). Not captured in screenshots — worth a follow-up capture. **This is the direct competitor to FTF's mutual-gain discovery engine.**

### 3.6 League Hub — Portfolio
Cross-league command center for the signed-in Sleeper account (switchable):
- Summary tiles: 4 leagues, 81 unique players; **position distribution** bars (incl. IDP: LB/DL/DE); **overall record** across leagues (77-132, 36.8% win rate, avg rank 8) with All/Active filter; **multi-league players** exposure list.
- **Your Leagues cards**: per league — team count, format chip (1QB/SF), rank, record, players, trades count, **avg age, avg experience**.
- **Team Portfolio Value**: stacked position-colored bar for your team vs gray bars for others, caption "MATTMURF77 • RANK 1 • 130,693", plus full team-rankings list with totals.
- **Roster Breakdown**: per-position groups with group totals (QB 9,139; RB 27,776) and per-player value + age (Drake Maye, NE, 23yo — 5,698).
- **Optimal Starting Lineup**: slot chips (QB/RB/WR/TE/FLEX) filled with the value-maximizing starters.
- **Waivers**: league-scoped free agents sorted by value with **in-app Claim buttons**.
- Tool chips also expose Dashboard, Analysis, Injuries, Lineups, Live Draft, News Feed.

### 3.7 League Hub — Trades (deep Sleeper write integration)
The boldest feature set. After a **Sleeper 2FA sign-in** (username/email/phone → code, or manual auth token; copy stresses "credentials sent directly to Sleeper; auth tokens stored locally"):
- **Offers inbox**: real pending Sleeper trade offers rendered in-app ("Lakeview League — from bobphil22 — RECEIVED: you receive Rachaad White, you send Jayden Higgins") with **ACCEPT / MODIFY / DECLINE** buttons.
- **History** of past trades.
- **Mass Send**: build one trade (You Send / You Want) and blast it to every eligible league in two steps ("All 3 leagues"). The offers are actually created inside Sleeper.

### 3.8 League Hub — Recon
Scouting tool that works on **any Sleeper username**, not just your own: enter a username + league year (2025/2026/2027), filter by league type (All/Dynasty/Dynasty Bestball) and settings (SF, TE Prem, .5 PPR, 1 PPR), then view that user's player exposure (Drake Maye — 3 leagues, 75%) or **Rookie Targets** ("spot league-wide trends, your opponents' rookie targets, and early-round favorites"). Opposition research as a product.

### 3.9 League Hub — Dispersal Draft
Commissioner tool for dispersal drafts (when teams are orphaned): create a draft, select orphaned teams, share a link/ID, managers claim teams and make picks, and **picks auto-sync to Sleeper in real time via 2FA**. Join-by-link flow for participants.

### 3.10 Vote Hub — Community Data Engine
"Influence market values by voting." A **Start/Sit/Drop** game shows three players (format-contextual: "Superflex · TE Premium"); each gets a Start/Sit/Drop vote. Streak mechanic, daily vote counter, skip button. **Leaderboard** with medals (top voter: 3,393 votes) and a **Polls** tab. This is their KeepTradeCut-style crowdsourcing loop, gamified — votes feed the market values the whole app runs on.

### 3.11 Market Hub — PRISM Prospect Model
"Prospect Rating Index for Statistical Modeling" — statistical grades from historical data, explicitly *not* rankings ("a 92 and a 90 are both elite-tier prospects"). Prospects view: graded list (Tyler Warren 95.0, Omarion Hampton 94.0…) with class-year (2025/2026) and position filters. **Combine view**: sortable table of PRISM grade, RAS, 40-yard, speed score, height, weight.

### 3.12 Cross-Cutting
- Dark "fintech terminal" aesthetic throughout; values ~0–10k scale.
- Player rows: position chip, NFL team, age; rookie/up-arrow badges.
- IDP positions appear in portfolio distribution (LB/DL/DE).
- Sleeper-only platform integration, but unusually deep (read **and write**).
- Version footer `v1.1.1.7 - Fix 2025 picks + debug` visible in production UI — indie-speed shipping, low polish.

---

## 4. Notable Takeaways vs Fantasy Trade Finder

1. **Fair Trade Finder is FTF's most direct competitor feature** — AI-powered balanced-offer discovery, but paywalled at $5.99/mo and (from marketing copy) framed around *fairness*, not mutual gain. FTF's Elo-driven "both teams improve" angle is still differentiated; get screenshots of their finder output to confirm.
2. **Write-access to Sleeper is their moat**: accept/modify/decline offers, mass-send offers, waiver claims, dispersal picks — all executed inside Sleeper via user auth tokens. Raises the bar for "actionability"; FTF currently stops at suggesting trades.
3. **Mass Trade Sender** is a power-user growth feature with viral surface area (every offer lands in someone else's Sleeper inbox).
4. **Community voting → proprietary values** (KTC playbook + streak gamification + leaderboard) gives them free, fresh data and a daily-open habit. FTF's Elo 3-player matchups are the analogous loop — the leaderboard/streak gamification here is worth stealing.
5. **Stock-market framing** (indices, VIX, MACD) is memorable branding but mostly cosmetic depth.
6. **Freemium structure**: calculator metered at 5/day, discovery/automation features paywalled. Free tier deliberately keeps the community-data engines (voting, Draft Rush) open.
7. Recon-on-any-username is a clever zero-auth acquisition hook (scout your rival → tell your league).
