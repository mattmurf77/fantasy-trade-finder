# Offline deck-quality + timing eval — first-run consensus decks

*Generated 2026-07-17 23:10 UTC by `scripts/deck_eval.py` (onboarding-conversion plan, build item 2 — the GATE).*

Each row below is one league team simulated as a **brand-new user**: consensus-seeded board only, zero swipes/preferences, production `config/features.json` flags (incl. `trade.need_fit` fit-led decks, trade-engine v2/v3). The first 5 cards of each first-run deck are shown for human scoring.

## Thresholds (from the plan)

| Metric | Target | This run |
|---|---|---|
| Empty-deck rate | **< 5%** | 0.0% (0/47) |
| Insult rate (human-scored 'insulting? y' ÷ scored cards) | **< 3%** | _score below, then compute_ |
| First-deck gen latency (server-side) | informs <60s TTFT budget | mean 23.1 ms · p95 53.0 ms |

**Passing** = empty-deck < 5% AND human-scored insult rate < 3% AND latency compatible with the <60s warm TTFT budget → the trades-first hook screen (build item 4) may proceed. **Failing** any of these → engine cold-start / deck-quality work jumps the build queue; the funnel does not ship showcasing a deck that insults strangers.

## How to score

For each card, fill the two blank columns:
- **insulting? y/n** — would the OWNER of this team feel lowballed or mocked by this offer landing as their first impression of the app?
- **would consider? y/n** — is it plausible enough to swipe on (not obviously dead on arrival)?

Values shown are consensus (DynastyProcess-seeded) trade values — the exact numbers a first-run user's cards are built from. Δ = receive − give from the simulated user's perspective.

## Summary

- Leagues evaluated: **4** — teams (first-run sims): **47**
- Empty decks: **0** (0.0%)
- League-init time (build ranking+trade services, per team): mean **0.7 ms**, p95 **1.7 ms**
- First-deck generation time: mean **23.1 ms**, p95 **53.0 ms**
- Sleeper league fetch (client-side leg, per league): mean **394.8 ms**
- One-time warm-process setup (import: DB + consensus + demo pool): **0.6 s**; universal-pool build: **199.9 ms** (paid once per server process — this is the cold-start component the keep-warm ping, build item 3, exists to hide)
- Deck size: min 26 · median 30 · mean 29.6 · max 30
- Deck-size distribution: 0 cards ×0, 1–4 ×0, 5–9 ×0, 10+ ×47

### Auto-flagged cards (fairness < 0.7 or consensus Δ ≤ -1000 — check these first)

- Lakeview League 🏈 / @bobphil22: Jayden Daniels (QB, 6424) + Rome Odunze (WR, 2940) → Jalen Hurts (QB, 6616) (fairness 99%, consensus Δ -2748)
- Lakeview League 🏈 / @bobphil22: Jayden Daniels (QB, 6424) + Tyler Warren (TE, 2492) → Jalen Hurts (QB, 6616) (fairness 95%, consensus Δ -2300)

---

## Lakeview League 🏈 (`1101407304802574336`) — 12 teams, format `1qb_ppr`, fetch 440.2 ms

### @mlakejr — deck 30 cards · init 3.7 ms · gen 53.3 ms · outlook `rebuilder`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Marvin Harrison (WR, 4108) → **Lamar Jackson (QB, 4181)** (w/ bmcaloon) | +73 | 96% | value | 0.38 |  |  |
| 2 | Breece Hall (RB, 5409) → **James Cook (RB, 5610)** (w/ SwaggyJ0) | +201 | 92% | value | 0.50 |  |  |
| 3 | Marvin Harrison (WR, 4108) → **DeVonta Smith (WR, 4323)** (w/ bmcaloon) | +215 | 89% | value | 0.50 |  |  |
| 4 | Tucker Kraft (TE, 2726) → **Saquon Barkley (RB, 2961)** (w/ KevinLake) | +235 | 83% | value | 0.56 |  |  |
| 5 | Tucker Kraft (TE, 2726) → **Caleb Williams (QB, 2979)** (w/ gildalbora) | +253 | 82% | value | 0.62 |  |  |

### @mattmurf77 — deck 28 cards · init 0.7 ms · gen 16.8 ms · outlook `rebuilder`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Jameson Williams (WR, 2691) → **Saquon Barkley (RB, 2961)** (w/ KevinLake) | +270 | 81% | value | 0.62 |  |  |
| 2 | Drake Maye (QB, 4802) → **Jonathan Taylor (RB, 5349)** (w/ pmquinn24) | +547 | 78% | value | 0.62 |  |  |
| 3 | Drake Maye (QB, 4802) → **Breece Hall (RB, 5409)** (w/ mlakejr) | +607 | 76% | value | 0.62 |  |  |
| 4 | C.J. Stroud (QB, 1448) → **Josh Jacobs (RB, 1505)** (w/ bmcaloon) | +57 | 92% | value | 0.81 |  |  |
| 5 | Dalton Kincaid (TE, 1784) → **Javonte Williams (RB, 1882)** (w/ mlakejr) | +98 | 89% | value | 0.50 |  |  |

### @pmquinn24 — deck 30 cards · init 0.6 ms · gen 25.1 ms · outlook `contender`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Jonathan Taylor (RB, 5349) → **Breece Hall (RB, 5409)** (w/ mlakejr) | +60 | 98% | value | 0.50 |  |  |
| 2 | Patrick Mahomes (QB, 3802) → **Rome Odunze (WR, 3894)** (w/ mlakejr) | +92 | 95% | value | 0.50 |  |  |
| 3 | Jonathan Taylor (RB, 5349) → **James Cook (RB, 5610)** (w/ SwaggyJ0) | +261 | 90% | value | 0.50 |  |  |
| 4 | Patrick Mahomes (QB, 3802) → **Marvin Harrison (WR, 4108)** (w/ mlakejr) | +306 | 84% | value | 0.50 |  |  |
| 5 | Patrick Mahomes (QB, 3802) → **Lamar Jackson (QB, 4181)** (w/ bmcaloon) | +379 | 81% | value | 0.50 |  |  |

### @bmcaloon — deck 30 cards · init 0.5 ms · gen 19.4 ms · outlook `rebuilder`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Zay Flowers (WR, 3717) → **Patrick Mahomes (QB, 3802)** (w/ pmquinn24) | +85 | 95% | value | 0.62 |  |  |
| 2 | Amon-Ra St. Brown (WR, 7637) → **Jahmyr Gibbs (RB, 7760)** (w/ gildalbora) | +123 | 96% | value | 0.50 |  |  |
| 3 | Brock Bowers (TE, 5091) → **Chris Olave (WR, 5241)** (w/ KevinLake) | +150 | 94% | value | 0.38 |  |  |
| 4 | Brock Bowers (TE, 5091) → **Nico Collins (WR, 5302)** (w/ SwaggyJ0) | +211 | 91% | value | 0.44 |  |  |
| 5 | Zay Flowers (WR, 3717) → **Rome Odunze (WR, 3894)** (w/ mlakejr) | +177 | 90% | value | 0.50 |  |  |

### @KevinLake — deck 30 cards · init 0.5 ms · gen 19.8 ms · outlook `contender`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Kenneth Walker (RB, 4737) → **Drake Maye (QB, 4802)** (w/ mattmurf77) | +65 | 97% | value | 0.69 |  |  |
| 2 | Saquon Barkley (RB, 2961) → **Caleb Williams (QB, 2979)** (w/ gildalbora) | +18 | 99% | value | 0.50 |  |  |
| 3 | Chris Olave (WR, 5241) → **Nico Collins (WR, 5302)** (w/ SwaggyJ0) | +61 | 97% | value | 0.50 |  |  |
| 4 | Chris Olave (WR, 5241) → **Jonathan Taylor (RB, 5349)** (w/ pmquinn24) | +108 | 95% | window | 0.44 |  |  |
| 5 | Chris Olave (WR, 5241) → **Breece Hall (RB, 5409)** (w/ mlakejr) | +168 | 93% | value | 0.44 |  |  |

### @gildalbora — deck 29 cards · init 0.5 ms · gen 26.1 ms · outlook `rebuilder`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Tee Higgins (WR, 3180) → **Jalen Hurts (QB, 3258)** (w/ KevinLake) | +78 | 95% | value | 0.50 |  |  |
| 2 | Jahmyr Gibbs (RB, 7760) → **Jaxon Smith-Njigba (WR, 8236)** (w/ mattmurf77) | +476 | 87% | value | 0.62 |  |  |
| 3 | Caleb Williams (QB, 2979) → **Rashee Rice (WR, 3174)** (w/ SwaggyJ0) | +195 | 87% | value | 0.44 |  |  |
| 4 | Tee Higgins (WR, 3180) → **Chase Brown (RB, 3426)** (w/ bmcaloon) | +246 | 84% | value | 0.50 |  |  |
| 5 | Caleb Williams (QB, 2979) → **Jalen Hurts (QB, 3258)** (w/ KevinLake) | +279 | 82% | value | 0.50 |  |  |

### @SwaggyJ0 — deck 30 cards · init 0.6 ms · gen 23.1 ms · outlook `not_sure`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Rashee Rice (WR, 3174) → **Tee Higgins (WR, 3180)** (w/ gildalbora) | +6 | 100% | — | 0.50 |  |  |
| 2 | Nico Collins (WR, 5302) → **Jonathan Taylor (RB, 5349)** (w/ pmquinn24) | +47 | 98% | — | 0.50 |  |  |
| 3 | Nico Collins (WR, 5302) → **Breece Hall (RB, 5409)** (w/ mlakejr) | +107 | 96% | — | 0.50 |  |  |
| 4 | Rashee Rice (WR, 3174) → **Jalen Hurts (QB, 3258)** (w/ KevinLake) | +84 | 94% | — | 0.44 |  |  |
| 5 | Rashee Rice (WR, 3174) → **Chase Brown (RB, 3426)** (w/ bmcaloon) | +252 | 84% | — | 0.56 |  |  |

### @pprendergast — deck 30 cards · init 0.5 ms · gen 23.1 ms · outlook `rebuilder`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | George Pickens (WR, 4200) → **DeVonta Smith (WR, 4323)** (w/ bmcaloon) | +123 | 94% | value | 0.50 |  |  |
| 2 | Justin Herbert (QB, 2786) → **Caleb Williams (QB, 2979)** (w/ gildalbora) | +193 | 86% | value | 0.50 |  |  |
| 3 | Justin Herbert (QB, 2786) → **Saquon Barkley (RB, 2961)** (w/ KevinLake) | +175 | 87% | value | 0.38 |  |  |
| 4 | Malik Nabers (WR, 6876) → **Amon-Ra St. Brown (WR, 7637)** (w/ bmcaloon) | +761 | 79% | value | 0.50 |  |  |
| 5 | George Pickens (WR, 4200) → **Kenneth Walker (RB, 4737)** (w/ KevinLake) | +537 | 76% | value | 0.44 |  |  |

### @sauter — deck 30 cards · init 0.5 ms · gen 20.9 ms · outlook `rebuilder`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Puka Nacua (WR, 7706) → **Jahmyr Gibbs (RB, 7760)** (w/ gildalbora) | +54 | 98% | value | 0.44 |  |  |
| 2 | Kyren Williams (RB, 2663) → **Tucker Kraft (TE, 2726)** (w/ mlakejr) | +63 | 95% | window | 0.69 |  |  |
| 3 | De'Von Achane (RB, 5265) → **Jonathan Taylor (RB, 5349)** (w/ pmquinn24) | +84 | 96% | value | 0.50 |  |  |
| 4 | Trey McBride (TE, 4814) → **A.J. Brown (WR, 4889)** (w/ KevinLake) | +75 | 96% | value | 0.44 |  |  |
| 5 | De'Von Achane (RB, 5265) → **Breece Hall (RB, 5409)** (w/ mlakejr) | +144 | 94% | value | 0.50 |  |  |

### @johnphillips3289 — deck 30 cards · init 0.5 ms · gen 23.9 ms · outlook `not_sure`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Christian McCaffrey (RB, 3785) → **Patrick Mahomes (QB, 3802)** (w/ pmquinn24) | +17 | 99% | — | 0.69 |  |  |
| 2 | Bijan Robinson (RB, 8158) → **Jaxon Smith-Njigba (WR, 8236)** (w/ mattmurf77) | +78 | 98% | — | 0.69 |  |  |
| 3 | Christian McCaffrey (RB, 3785) → **Rome Odunze (WR, 3894)** (w/ mlakejr) | +109 | 94% | — | 0.62 |  |  |
| 4 | Christian McCaffrey (RB, 3785) → **Marvin Harrison (WR, 4108)** (w/ mlakejr) | +323 | 83% | — | 0.62 |  |  |
| 5 | Christian McCaffrey (RB, 3785) → **Lamar Jackson (QB, 4181)** (w/ bmcaloon) | +396 | 80% | — | 0.50 |  |  |

### @DrByron34 — deck 30 cards · init 0.5 ms · gen 23.6 ms · outlook `contender`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Sam LaPorta (TE, 3345) → **Chase Brown (RB, 3426)** (w/ bmcaloon) | +81 | 95% | window | 0.75 |  |  |
| 2 | Josh Allen (QB, 5842) → **Drake London (WR, 6265)** (w/ bmcaloon) | +423 | 85% | value | 0.62 |  |  |
| 3 | Ladd McConkey (WR, 4343) → **Kenneth Walker (RB, 4737)** (w/ KevinLake) | +394 | 82% | window | 0.62 |  |  |
| 4 | Ladd McConkey (WR, 4343) → **Drake Maye (QB, 4802)** (w/ mattmurf77) | +459 | 80% | value | 0.56 |  |  |
| 5 | Christian Watson (WR, 1895) → **Brock Purdy (QB, 1906)** (w/ pmquinn24) | +11 | 99% | value | 0.50 |  |  |

### @bobphil22 — deck 29 cards · init 0.6 ms · gen 23.5 ms · outlook `contender`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | CeeDee Lamb (WR, 7637) → **Amon-Ra St. Brown (WR, 7637)** (w/ bmcaloon) | +0 | 100% | value | 0.50 |  |  |
| 2 | Jayden Daniels (QB, 3886) → **Rome Odunze (WR, 3894)** (w/ mlakejr) | +8 | 100% | value | 0.50 |  |  |
| 3 | CeeDee Lamb (WR, 7637) → **Jahmyr Gibbs (RB, 7760)** (w/ gildalbora) | +123 | 96% | value | 0.50 |  |  |
| 4 | Jaylen Waddle (WR, 4017) → **Marvin Harrison (WR, 4108)** (w/ mlakejr) | +91 | 95% | value | 0.50 |  |  |
| 5 | Jaylen Waddle (WR, 4017) → **Lamar Jackson (QB, 4181)** (w/ bmcaloon) | +164 | 91% | value | 0.38 |  |  |

## Fantasy Football Version 3 (`1181674778942836736`) — 12 teams, format `1qb_ppr`, fetch 422.4 ms

### @mattmurf77 — deck 30 cards · init 1.7 ms · gen 59.3 ms · outlook `rebuilder`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | De'Von Achane (RB, 5265) → **Emeka Egbuka (WR, 5302)** (w/ jonbonjourvi) | +37 | 98% | value | 0.56 |  |  |
| 2 | Jaxon Smith-Njigba (WR, 8236) → **Ja'Marr Chase (WR, 8470)** (w/ smozhgani) | +234 | 94% | value | 0.50 |  |  |
| 3 | Jahmyr Gibbs (RB, 7760) → **Bijan Robinson (RB, 8158)** (w/ smozhgani) | +398 | 89% | value | 0.50 |  |  |
| 4 | Ashton Jeanty (RB, 7131) → **CeeDee Lamb (WR, 7637)** (w/ MangoPatti) | +506 | 86% | value | 0.56 |  |  |
| 5 | De'Von Achane (RB, 5265) → **James Cook (RB, 5610)** (w/ MangoPatti) | +345 | 87% | value | 0.50 |  |  |

### @jonbonjourvi — deck 29 cards · init 0.6 ms · gen 20.6 ms · outlook `rebuilder`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Puka Nacua (WR, 7706) → **Jahmyr Gibbs (RB, 7760)** (w/ mattmurf77) | +54 | 98% | value | 0.56 |  |  |
| 2 | Saquon Barkley (RB, 2961) → **TreVeyon Henderson (RB, 2967)** (w/ Bcork) | +6 | 100% | window | 0.50 |  |  |
| 3 | Quinshon Judkins (RB, 2921) → **TreVeyon Henderson (RB, 2967)** (w/ Bcork) | +46 | 96% | value | 0.50 |  |  |
| 4 | Rashee Rice (WR, 3174) → **Jalen Hurts (QB, 3258)** (w/ PaulSm3nis) | +84 | 94% | value | 0.62 |  |  |
| 5 | Rashee Rice (WR, 3174) → **Sam LaPorta (TE, 3345)** (w/ smozhgani) | +171 | 89% | value | 0.50 |  |  |

### @Shark357 — deck 30 cards · init 0.5 ms · gen 20.1 ms · outlook `rebuilder`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | George Pickens (WR, 4200) → **Ladd McConkey (WR, 4343)** (w/ Bcork) | +143 | 93% | value | 0.50 |  |  |
| 2 | Trevor Lawrence (QB, 2298) → **Harold Fannin (TE, 2518)** (w/ jonbonjourvi) | +220 | 81% | value | 0.50 |  |  |
| 3 | David Montgomery (RB, 1073) → **Josh Downs (WR, 1073)** (w/ jonbonjourvi) | +0 | 100% | window | 0.62 |  |  |
| 4 | David Montgomery (RB, 1073) → **Isaiah Likely (TE, 1073)** (w/ smozhgani) | +0 | 100% | window | 0.50 |  |  |
| 5 | David Montgomery (RB, 1073) → **Davante Adams (WR, 1087)** (w/ mattmurf77) | +14 | 97% | value | 0.56 |  |  |

### @MangoPatti — deck 30 cards · init 0.4 ms · gen 16.1 ms · outlook `contender`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Chris Olave (WR, 5241) → **De'Von Achane (RB, 5265)** (w/ mattmurf77) | +24 | 99% | value | 0.56 |  |  |
| 2 | CeeDee Lamb (WR, 7637) → **Amon-Ra St. Brown (WR, 7637)** (w/ smozhgani) | +0 | 100% | value | 0.50 |  |  |
| 3 | CeeDee Lamb (WR, 7637) → **Puka Nacua (WR, 7706)** (w/ jonbonjourvi) | +69 | 98% | value | 0.50 |  |  |
| 4 | CeeDee Lamb (WR, 7637) → **Jahmyr Gibbs (RB, 7760)** (w/ mattmurf77) | +123 | 96% | value | 0.56 |  |  |
| 5 | Chris Olave (WR, 5241) → **Emeka Egbuka (WR, 5302)** (w/ jonbonjourvi) | +61 | 97% | value | 0.50 |  |  |

### @Bcork — deck 29 cards · init 0.4 ms · gen 15.3 ms · outlook `rebuilder`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Ladd McConkey (WR, 4343) → **Drake Maye (QB, 4802)** (w/ mattmurf77) | +459 | 80% | value | 0.81 |  |  |
| 2 | TreVeyon Henderson (RB, 2967) → **Jalen Hurts (QB, 3258)** (w/ PaulSm3nis) | +291 | 81% | value | 0.62 |  |  |
| 3 | TreVeyon Henderson (RB, 2967) → **Joe Burrow (QB, 3309)** (w/ smozhgani) | +342 | 78% | value | 0.56 |  |  |
| 4 | Matthew Golden (WR, 894) → **RJ Harvey (RB, 954)** (w/ Shark357) | +60 | 86% | value | 0.81 |  |  |
| 5 | Jayden Higgins (WR, 1143) → **D'Andre Swift (RB, 1255)** (w/ MangoPatti) | +112 | 81% | value | 0.69 |  |  |

### @smozhgani — deck 29 cards · init 0.4 ms · gen 15.2 ms · outlook `rebuilder`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Jayden Daniels (QB, 3886) → **Rome Odunze (WR, 3894)** (w/ Bcork) | +8 | 100% | value | 0.75 |  |  |
| 2 | Amon-Ra St. Brown (WR, 7637) → **CeeDee Lamb (WR, 7637)** (w/ MangoPatti) | +0 | 100% | value | 0.50 |  |  |
| 3 | Amon-Ra St. Brown (WR, 7637) → **Puka Nacua (WR, 7706)** (w/ jonbonjourvi) | +69 | 98% | value | 0.50 |  |  |
| 4 | Amon-Ra St. Brown (WR, 7637) → **Jahmyr Gibbs (RB, 7760)** (w/ mattmurf77) | +123 | 96% | value | 0.56 |  |  |
| 5 | Jameson Williams (WR, 2691) → **Tucker Kraft (TE, 2726)** (w/ jonbonjourvi) | +35 | 97% | value | 0.50 |  |  |

### @PaulSm3nis — deck 30 cards · init 0.4 ms · gen 19.5 ms · outlook `contender`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Jalen Hurts (QB, 3258) → **Joe Burrow (QB, 3309)** (w/ smozhgani) | +51 | 96% | value | 0.50 |  |  |
| 2 | Jalen Hurts (QB, 3258) → **Sam LaPorta (TE, 3345)** (w/ smozhgani) | +87 | 94% | value | 0.50 |  |  |
| 3 | Kyren Williams (RB, 2663) → **Tucker Kraft (TE, 2726)** (w/ jonbonjourvi) | +63 | 95% | value | 0.44 |  |  |
| 4 | Jalen Hurts (QB, 3258) → **Chase Brown (RB, 3426)** (w/ smozhgani) | +168 | 89% | window | 0.56 |  |  |
| 5 | Kyren Williams (RB, 2663) → **Justin Herbert (QB, 2786)** (w/ jonbonjourvi) | +123 | 90% | value | 0.44 |  |  |

### @bsharp3 — deck 30 cards · init 0.5 ms · gen 21.7 ms · outlook `not_sure`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | DeVonta Smith (WR, 4323) → **Ladd McConkey (WR, 4343)** (w/ Bcork) | +20 | 99% | — | 0.50 |  |  |
| 2 | Kenneth Walker (RB, 4737) → **Trey McBride (TE, 4814)** (w/ mattmurf77) | +77 | 96% | — | 0.62 |  |  |
| 3 | Kenneth Walker (RB, 4737) → **Drake Maye (QB, 4802)** (w/ mattmurf77) | +65 | 97% | — | 0.50 |  |  |
| 4 | Marvin Harrison (WR, 4108) → **George Pickens (WR, 4200)** (w/ Shark357) | +92 | 95% | — | 0.50 |  |  |
| 5 | Kenneth Walker (RB, 4737) → **A.J. Brown (WR, 4889)** (w/ MangoPatti) | +152 | 93% | — | 0.50 |  |  |

### @gdubs10 — deck 30 cards · init 0.4 ms · gen 21.1 ms · outlook `not_sure`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Tyler Warren (TE, 3309) → **Sam LaPorta (TE, 3345)** (w/ smozhgani) | +36 | 98% | — | 0.50 |  |  |
| 2 | Jaylen Waddle (WR, 4017) → **Colston Loveland (TE, 4100)** (w/ smozhgani) | +83 | 95% | — | 0.50 |  |  |
| 3 | Malik Nabers (WR, 6876) → **Ashton Jeanty (RB, 7131)** (w/ mattmurf77) | +255 | 92% | — | 0.56 |  |  |
| 4 | Tyler Warren (TE, 3309) → **Chase Brown (RB, 3426)** (w/ smozhgani) | +117 | 92% | — | 0.50 |  |  |
| 5 | Jaylen Waddle (WR, 4017) → **George Pickens (WR, 4200)** (w/ Shark357) | +183 | 90% | — | 0.50 |  |  |

### @JohnStanfield — deck 26 cards · init 0.5 ms · gen 10.8 ms · outlook `rebuilder`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Brock Bowers (TE, 5091) → **De'Von Achane (RB, 5265)** (w/ mattmurf77) | +174 | 93% | value | 0.75 |  |  |
| 2 | Brock Bowers (TE, 5091) → **James Cook (RB, 5610)** (w/ MangoPatti) | +519 | 80% | value | 0.75 |  |  |
| 3 | Xavier Worthy (WR, 944) → **RJ Harvey (RB, 954)** (w/ Shark357) | +10 | 98% | value | 0.81 |  |  |
| 4 | Chig Okonkwo (TE, 560) → **Rico Dowdle (RB, 595)** (w/ jonbonjourvi) | +35 | 87% | value | 0.75 |  |  |
| 5 | Shedeur Sanders (QB, 280) → **Isiah Pacheco (RB, 283)** (w/ Shark357) | +3 | 97% | value | 0.75 |  |  |

### @dondags20 — deck 30 cards · init 0.5 ms · gen 22.0 ms · outlook `contender`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Lamar Jackson (QB, 4181) → **George Pickens (WR, 4200)** (w/ Shark357) | +19 | 99% | value | 0.38 |  |  |
| 2 | Lamar Jackson (QB, 4181) → **Ladd McConkey (WR, 4343)** (w/ Bcork) | +162 | 92% | value | 0.75 |  |  |
| 3 | Jonathan Taylor (RB, 5349) → **James Cook (RB, 5610)** (w/ MangoPatti) | +261 | 90% | value | 0.50 |  |  |
| 4 | Brian Thomas (WR, 2507) → **Tucker Kraft (TE, 2726)** (w/ jonbonjourvi) | +219 | 83% | value | 0.50 |  |  |
| 5 | Jonathan Taylor (RB, 5349) → **Josh Allen (QB, 5842)** (w/ MangoPatti) | +493 | 82% | value | 0.38 |  |  |

### @KevinLake — deck 30 cards · init 0.5 ms · gen 51.8 ms · outlook `not_sure`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Nico Collins (WR, 5302) → **Emeka Egbuka (WR, 5302)** (w/ jonbonjourvi) | +0 | 100% | — | 0.50 |  |  |
| 2 | Garrett Wilson (WR, 5596) → **James Cook (RB, 5610)** (w/ MangoPatti) | +14 | 99% | — | 0.50 |  |  |
| 3 | Patrick Mahomes (QB, 3802) → **Rome Odunze (WR, 3894)** (w/ Bcork) | +92 | 95% | — | 0.75 |  |  |
| 4 | Zay Flowers (WR, 3717) → **Christian McCaffrey (RB, 3785)** (w/ MangoPatti) | +68 | 96% | — | 0.50 |  |  |
| 5 | Omarion Hampton (RB, 6153) → **Drake London (WR, 6265)** (w/ mattmurf77) | +112 | 96% | — | 0.44 |  |  |

## Lakeview League 🏈 (`1312076055586050048`) — 12 teams, format `sf_tep`, fetch 316.6 ms

### @mlakejr — deck 30 cards · init 2.2 ms · gen 53.0 ms · outlook `rebuilder`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Jordan Love (QB, 4737) → **Brock Purdy (QB, 4792)** (w/ SwaggyJ0) | +55 | 97% | value | 0.50 |  |  |
| 2 | Jordan Love (QB, 4737) → **Jaxson Dart (QB, 4824)** (w/ mattmurf77) | +87 | 96% | value | 0.50 |  |  |
| 3 | Breece Hall (RB, 4154) → **James Cook (RB, 4284)** (w/ SwaggyJ0) | +130 | 93% | value | 0.50 |  |  |
| 4 | Malik Nabers (WR, 5315) → **Drake Maye (QB, 5507)** (w/ mattmurf77) | +192 | 92% | value | 0.50 |  |  |
| 5 | Tetairoa McMillan (WR, 4482) → **Brock Purdy (QB, 4792)** (w/ SwaggyJ0) | +310 | 86% | value | 0.58 |  |  |

### @mattmurf77 — deck 30 cards · init 0.7 ms · gen 33.3 ms · outlook `rebuilder`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Drake Maye (QB, 5507) → **Ashton Jeanty (RB, 5737)** (w/ pmquinn24) | +230 | 91% | value | 0.62 |  |  |
| 2 | Justin Jefferson (WR, 6924) → **Patrick Mahomes (QB, 7149)** (w/ pmquinn24) | +225 | 93% | value | 0.50 |  |  |
| 3 | Jaxson Dart (QB, 4824) → **Drake London (WR, 5056)** (w/ bmcaloon) | +232 | 90% | value | 0.50 |  |  |
| 4 | Marvin Harrison (WR, 3404) → **Kenneth Walker (RB, 3613)** (w/ KevinLake) | +209 | 87% | value | 0.62 |  |  |
| 5 | Jaxson Dart (QB, 4824) → **Trevor Lawrence (QB, 5207)** (w/ gildalbora) | +383 | 84% | value | 0.50 |  |  |

### @pmquinn24 — deck 30 cards · init 0.5 ms · gen 30.7 ms · outlook `contender`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Jonathan Taylor (RB, 4017) → **Dak Prescott (QB, 4135)** (w/ bmcaloon) | +118 | 94% | value | 0.50 |  |  |
| 2 | Jonathan Taylor (RB, 4017) → **Breece Hall (RB, 4154)** (w/ mlakejr) | +137 | 93% | value | 0.50 |  |  |
| 3 | Patrick Mahomes (QB, 7149) → **Lamar Jackson (QB, 7618)** (w/ bmcaloon) | +469 | 87% | value | 0.50 |  |  |
| 4 | Jonathan Taylor (RB, 4017) → **James Cook (RB, 4284)** (w/ SwaggyJ0) | +267 | 86% | value | 0.50 |  |  |
| 5 | Jonathan Taylor (RB, 4017) → **Tetairoa McMillan (WR, 4482)** (w/ mlakejr) | +465 | 78% | value | 0.50 |  |  |

### @bmcaloon — deck 30 cards · init 0.5 ms · gen 16.2 ms · outlook `rebuilder`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Brock Bowers (TE, 4001) → **Jonathan Taylor (RB, 4017)** (w/ pmquinn24) | +16 | 99% | value | 0.50 |  |  |
| 2 | Dak Prescott (QB, 4135) → **Breece Hall (RB, 4154)** (w/ mlakejr) | +19 | 99% | window | 0.50 |  |  |
| 3 | Amon-Ra St. Brown (WR, 6511) → **Jalen Hurts (QB, 6616)** (w/ KevinLake) | +105 | 96% | value | 0.58 |  |  |
| 4 | Zay Flowers (WR, 2934) → **Luther Burden (WR, 2986)** (w/ SwaggyJ0) | +52 | 96% | value | 0.50 |  |  |
| 5 | Amon-Ra St. Brown (WR, 6511) → **Caleb Williams (QB, 6676)** (w/ gildalbora) | +165 | 94% | value | 0.50 |  |  |

### @KevinLake — deck 30 cards · init 0.5 ms · gen 16.8 ms · outlook `contender`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Jalen Hurts (QB, 6616) → **Caleb Williams (QB, 6676)** (w/ gildalbora) | +60 | 98% | value | 0.50 |  |  |
| 2 | Chris Olave (WR, 3929) → **Emeka Egbuka (WR, 3983)** (w/ SwaggyJ0) | +54 | 97% | value | 0.50 |  |  |
| 3 | Chris Olave (WR, 3929) → **Brock Bowers (TE, 4001)** (w/ bmcaloon) | +72 | 96% | value | 0.50 |  |  |
| 4 | Chris Olave (WR, 3929) → **Jonathan Taylor (RB, 4017)** (w/ pmquinn24) | +88 | 95% | window | 0.50 |  |  |
| 5 | Jalen Hurts (QB, 6616) → **Justin Jefferson (WR, 6924)** (w/ mattmurf77) | +308 | 90% | value | 0.58 |  |  |

### @gildalbora — deck 30 cards · init 0.5 ms · gen 22.3 ms · outlook `rebuilder`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Jordyn Tyson (WR, 2915) → **Zay Flowers (WR, 2934)** (w/ bmcaloon) | +19 | 98% | value | 0.50 |  |  |
| 2 | Jahmyr Gibbs (RB, 6408) → **Amon-Ra St. Brown (WR, 6511)** (w/ bmcaloon) | +103 | 96% | value | 0.50 |  |  |
| 3 | Trevor Lawrence (QB, 5207) → **Malik Nabers (WR, 5315)** (w/ mlakejr) | +108 | 96% | value | 0.50 |  |  |
| 4 | Jordyn Tyson (WR, 2915) → **Luther Burden (WR, 2986)** (w/ SwaggyJ0) | +71 | 95% | value | 0.50 |  |  |
| 5 | Jahmyr Gibbs (RB, 6408) → **Jalen Hurts (QB, 6616)** (w/ KevinLake) | +208 | 93% | value | 0.58 |  |  |

### @SwaggyJ0 — deck 30 cards · init 0.5 ms · gen 16.9 ms · outlook `rebuilder`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Emeka Egbuka (WR, 3983) → **Brock Bowers (TE, 4001)** (w/ bmcaloon) | +18 | 99% | value | 0.50 |  |  |
| 2 | Nico Collins (WR, 3912) → **Chris Olave (WR, 3929)** (w/ KevinLake) | +17 | 99% | value | 0.50 |  |  |
| 3 | Brock Purdy (QB, 4792) → **Jaxson Dart (QB, 4824)** (w/ mattmurf77) | +32 | 98% | value | 0.50 |  |  |
| 4 | Emeka Egbuka (WR, 3983) → **Jonathan Taylor (RB, 4017)** (w/ pmquinn24) | +34 | 98% | value | 0.50 |  |  |
| 5 | Nico Collins (WR, 3912) → **Brock Bowers (TE, 4001)** (w/ bmcaloon) | +89 | 95% | window | 0.50 |  |  |

### @pprendergast — deck 30 cards · init 0.5 ms · gen 16.9 ms · outlook `rebuilder`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | George Pickens (WR, 3912) → **Chris Olave (WR, 3929)** (w/ KevinLake) | +17 | 99% | value | 0.50 |  |  |
| 2 | Justin Herbert (QB, 6379) → **Amon-Ra St. Brown (WR, 6511)** (w/ bmcaloon) | +132 | 95% | value | 0.69 |  |  |
| 3 | Carnell Tate (WR, 3677) → **A.J. Brown (WR, 3717)** (w/ KevinLake) | +40 | 98% | value | 0.50 |  |  |
| 4 | Omarion Hampton (RB, 4836) → **Drake London (WR, 5056)** (w/ bmcaloon) | +220 | 90% | value | 0.69 |  |  |
| 5 | Carnell Tate (WR, 3677) → **Chris Olave (WR, 3929)** (w/ KevinLake) | +252 | 86% | value | 0.50 |  |  |

### @sauter — deck 30 cards · init 0.6 ms · gen 18.1 ms · outlook `rebuilder`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Puka Nacua (WR, 6603) → **Jalen Hurts (QB, 6616)** (w/ KevinLake) | +13 | 100% | value | 0.58 |  |  |
| 2 | De'Von Achane (RB, 4145) → **Breece Hall (RB, 4154)** (w/ mlakejr) | +9 | 100% | value | 0.50 |  |  |
| 3 | CeeDee Lamb (WR, 6573) → **Jalen Hurts (QB, 6616)** (w/ KevinLake) | +43 | 98% | value | 0.58 |  |  |
| 4 | Puka Nacua (WR, 6603) → **Caleb Williams (QB, 6676)** (w/ gildalbora) | +73 | 98% | value | 0.50 |  |  |
| 5 | CeeDee Lamb (WR, 6573) → **Caleb Williams (QB, 6676)** (w/ gildalbora) | +103 | 96% | window | 0.50 |  |  |

### @johnphillips3289 — deck 30 cards · init 0.5 ms · gen 22.7 ms · outlook `not_sure`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Bijan Robinson (RB, 7036) → **Patrick Mahomes (QB, 7149)** (w/ pmquinn24) | +113 | 96% | — | 0.42 |  |  |
| 2 | Christian McCaffrey (RB, 3025) → **DeVonta Smith (WR, 3230)** (w/ bmcaloon) | +205 | 86% | — | 0.50 |  |  |
| 3 | Bijan Robinson (RB, 7036) → **Lamar Jackson (QB, 7618)** (w/ bmcaloon) | +582 | 84% | — | 0.42 |  |  |
| 4 | Ja'Marr Chase (WR, 7760) → **Josh Allen (QB, 8470)** (w/ pmquinn24) | +710 | 82% | — | 0.42 |  |  |
| 5 | Christian McCaffrey (RB, 3025) → **Marvin Harrison (WR, 3404)** (w/ mattmurf77) | +379 | 77% | — | 0.62 |  |  |

### @DrByron34 — deck 30 cards · init 0.5 ms · gen 22.8 ms · outlook `rebuilder`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | C.J. Stroud (QB, 3573) → **Kenneth Walker (RB, 3613)** (w/ KevinLake) | +40 | 98% | value | 0.48 |  |  |
| 2 | Ladd McConkey (WR, 3315) → **Marvin Harrison (WR, 3404)** (w/ mattmurf77) | +89 | 94% | value | 0.50 |  |  |
| 3 | C.J. Stroud (QB, 3573) → **A.J. Brown (WR, 3717)** (w/ KevinLake) | +144 | 91% | value | 0.42 |  |  |
| 4 | Garrett Wilson (WR, 4267) → **Tetairoa McMillan (WR, 4482)** (w/ mlakejr) | +215 | 90% | value | 0.50 |  |  |
| 5 | Jared Goff (QB, 2775) → **Jordyn Tyson (WR, 2915)** (w/ gildalbora) | +140 | 89% | window | 0.50 |  |  |

### @bobphil22 — deck 28 cards · init 0.5 ms · gen 12.2 ms · outlook `rebuilder`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Jayden Daniels (QB, 6424) + Rome Odunze (WR, 2940) → **Jalen Hurts (QB, 6616)** (w/ KevinLake) | -2748 | 99% | value | 0.42 |  |  |
| 2 | Jayden Daniels (QB, 6424) + Tyler Warren (TE, 2492) → **Jalen Hurts (QB, 6616)** (w/ KevinLake) | -2300 | 95% | value | 0.42 |  |  |
| 3 | Jeremiyah Love (RB, 5184) → **Trevor Lawrence (QB, 5207)** (w/ gildalbora) | +23 | 99% | value | 0.58 |  |  |
| 4 | Jayden Daniels (QB, 6424) → **Jalen Hurts (QB, 6616)** (w/ KevinLake) | +192 | 94% | value | 0.50 |  |  |
| 5 | Jayden Daniels (QB, 6424) → **Caleb Williams (QB, 6676)** (w/ gildalbora) | +252 | 92% | value | 0.50 |  |  |

## Fantasy Football Version 3 (`1312140920132497408`) — 11 teams, format `1qb_ppr`, fetch 400.1 ms

### @mattmurf77 — deck 30 cards · init 0.8 ms · gen 33.5 ms · outlook `rebuilder`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | De'Von Achane (RB, 5265) → **Emeka Egbuka (WR, 5302)** (w/ jonbonjourvi) | +37 | 98% | value | 0.56 |  |  |
| 2 | De'Von Achane (RB, 5265) → **Breece Hall (RB, 5409)** (w/ bsharp3) | +144 | 94% | value | 0.50 |  |  |
| 3 | Ashton Jeanty (RB, 7131) → **CeeDee Lamb (WR, 7637)** (w/ MangoPatti) | +506 | 86% | value | 0.56 |  |  |
| 4 | De'Von Achane (RB, 5265) → **James Cook (RB, 5610)** (w/ MangoPatti) | +345 | 87% | value | 0.50 |  |  |
| 5 | Ashton Jeanty (RB, 7131) → **Puka Nacua (WR, 7706)** (w/ jonbonjourvi) | +575 | 84% | value | 0.56 |  |  |

### @jonbonjourvi — deck 29 cards · init 0.6 ms · gen 18.1 ms · outlook `rebuilder`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Puka Nacua (WR, 7706) → **Jahmyr Gibbs (RB, 7760)** (w/ mattmurf77) | +54 | 98% | value | 0.56 |  |  |
| 2 | Saquon Barkley (RB, 2961) → **TreVeyon Henderson (RB, 2967)** (w/ Bcork) | +6 | 100% | window | 0.50 |  |  |
| 3 | Quinshon Judkins (RB, 2921) → **TreVeyon Henderson (RB, 2967)** (w/ Bcork) | +46 | 96% | value | 0.50 |  |  |
| 4 | Rashee Rice (WR, 3174) → **Jalen Hurts (QB, 3258)** (w/ PaulSm3nis) | +84 | 94% | value | 0.62 |  |  |
| 5 | Emeka Egbuka (WR, 5302) → **Breece Hall (RB, 5409)** (w/ bsharp3) | +107 | 96% | value | 0.50 |  |  |

### @Shark357 — deck 30 cards · init 0.5 ms · gen 17.2 ms · outlook `rebuilder`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | George Pickens (WR, 4200) → **DeVonta Smith (WR, 4323)** (w/ bsharp3) | +123 | 94% | value | 0.50 |  |  |
| 2 | George Pickens (WR, 4200) → **Ladd McConkey (WR, 4343)** (w/ Bcork) | +143 | 93% | value | 0.50 |  |  |
| 3 | George Pickens (WR, 4200) → **Kenneth Walker (RB, 4737)** (w/ bsharp3) | +537 | 76% | value | 0.38 |  |  |
| 4 | Trevor Lawrence (QB, 2298) → **Harold Fannin (TE, 2518)** (w/ jonbonjourvi) | +220 | 81% | value | 0.50 |  |  |
| 5 | David Montgomery (RB, 1073) → **Josh Downs (WR, 1073)** (w/ jonbonjourvi) | +0 | 100% | window | 0.62 |  |  |

### @MangoPatti — deck 30 cards · init 0.7 ms · gen 17.4 ms · outlook `contender`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Chris Olave (WR, 5241) → **De'Von Achane (RB, 5265)** (w/ mattmurf77) | +24 | 99% | value | 0.56 |  |  |
| 2 | CeeDee Lamb (WR, 7637) → **Puka Nacua (WR, 7706)** (w/ jonbonjourvi) | +69 | 98% | value | 0.50 |  |  |
| 3 | CeeDee Lamb (WR, 7637) → **Jahmyr Gibbs (RB, 7760)** (w/ mattmurf77) | +123 | 96% | value | 0.56 |  |  |
| 4 | Chris Olave (WR, 5241) → **Emeka Egbuka (WR, 5302)** (w/ jonbonjourvi) | +61 | 97% | value | 0.50 |  |  |
| 5 | Christian McCaffrey (RB, 3785) → **Rome Odunze (WR, 3894)** (w/ Bcork) | +109 | 94% | value | 0.69 |  |  |

### @Bcork — deck 29 cards · init 0.6 ms · gen 15.6 ms · outlook `rebuilder`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Ladd McConkey (WR, 4343) → **Kenneth Walker (RB, 4737)** (w/ bsharp3) | +394 | 82% | value | 0.69 |  |  |
| 2 | Ladd McConkey (WR, 4343) → **Drake Maye (QB, 4802)** (w/ mattmurf77) | +459 | 80% | value | 0.81 |  |  |
| 3 | TreVeyon Henderson (RB, 2967) → **Jalen Hurts (QB, 3258)** (w/ PaulSm3nis) | +291 | 81% | value | 0.62 |  |  |
| 4 | Matthew Golden (WR, 894) → **Jared Goff (QB, 908)** (w/ bsharp3) | +14 | 97% | value | 0.75 |  |  |
| 5 | Matthew Golden (WR, 894) → **RJ Harvey (RB, 954)** (w/ Shark357) | +60 | 86% | value | 0.81 |  |  |

### @PaulSm3nis — deck 30 cards · init 0.6 ms · gen 21.1 ms · outlook `contender`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Kyren Williams (RB, 2663) → **Tucker Kraft (TE, 2726)** (w/ jonbonjourvi) | +63 | 95% | value | 0.44 |  |  |
| 2 | Kyren Williams (RB, 2663) → **Justin Herbert (QB, 2786)** (w/ jonbonjourvi) | +123 | 90% | value | 0.44 |  |  |
| 3 | Kyren Williams (RB, 2663) → **Quinshon Judkins (RB, 2921)** (w/ jonbonjourvi) | +258 | 81% | value | 0.50 |  |  |
| 4 | Kyren Williams (RB, 2663) → **Saquon Barkley (RB, 2961)** (w/ jonbonjourvi) | +298 | 79% | value | 0.50 |  |  |
| 5 | Kyren Williams (RB, 2663) → **TreVeyon Henderson (RB, 2967)** (w/ Bcork) | +304 | 78% | value | 0.50 |  |  |

### @bsharp3 — deck 30 cards · init 0.6 ms · gen 20.5 ms · outlook `contender`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | DeVonta Smith (WR, 4323) → **Ladd McConkey (WR, 4343)** (w/ Bcork) | +20 | 99% | value | 0.50 |  |  |
| 2 | Kenneth Walker (RB, 4737) → **Trey McBride (TE, 4814)** (w/ mattmurf77) | +77 | 96% | value | 0.62 |  |  |
| 3 | Kenneth Walker (RB, 4737) → **Drake Maye (QB, 4802)** (w/ mattmurf77) | +65 | 97% | value | 0.50 |  |  |
| 4 | Marvin Harrison (WR, 4108) → **George Pickens (WR, 4200)** (w/ Shark357) | +92 | 95% | value | 0.50 |  |  |
| 5 | Kenneth Walker (RB, 4737) → **A.J. Brown (WR, 4889)** (w/ MangoPatti) | +152 | 93% | value | 0.50 |  |  |

### @gdubs10 — deck 30 cards · init 0.6 ms · gen 22.2 ms · outlook `not_sure`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Tee Higgins (WR, 3180) → **Jalen Hurts (QB, 3258)** (w/ PaulSm3nis) | +78 | 95% | — | 0.62 |  |  |
| 2 | Malik Nabers (WR, 6876) → **Ashton Jeanty (RB, 7131)** (w/ mattmurf77) | +255 | 92% | — | 0.56 |  |  |
| 3 | Jaylen Waddle (WR, 4017) → **George Pickens (WR, 4200)** (w/ Shark357) | +183 | 90% | — | 0.50 |  |  |
| 4 | Jaylen Waddle (WR, 4017) → **Ladd McConkey (WR, 4343)** (w/ Bcork) | +326 | 84% | — | 0.50 |  |  |
| 5 | Jaxson Dart (QB, 1890) → **Brock Purdy (QB, 1906)** (w/ jonbonjourvi) | +16 | 98% | — | 0.50 |  |  |

### @JohnStanfield — deck 26 cards · init 0.6 ms · gen 10.8 ms · outlook `rebuilder`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Brock Bowers (TE, 5091) → **De'Von Achane (RB, 5265)** (w/ mattmurf77) | +174 | 93% | value | 0.75 |  |  |
| 2 | Brock Bowers (TE, 5091) → **James Cook (RB, 5610)** (w/ MangoPatti) | +519 | 80% | value | 0.75 |  |  |
| 3 | Xavier Worthy (WR, 944) → **RJ Harvey (RB, 954)** (w/ Shark357) | +10 | 98% | value | 0.81 |  |  |
| 4 | Chig Okonkwo (TE, 560) → **Rico Dowdle (RB, 595)** (w/ jonbonjourvi) | +35 | 87% | value | 0.75 |  |  |
| 5 | Chig Okonkwo (TE, 560) → **Rhamondre Stevenson (RB, 627)** (w/ PaulSm3nis) | +67 | 78% | value | 0.69 |  |  |

### @dondags20 — deck 30 cards · init 0.5 ms · gen 17.9 ms · outlook `contender`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Lamar Jackson (QB, 4181) → **George Pickens (WR, 4200)** (w/ Shark357) | +19 | 99% | value | 0.38 |  |  |
| 2 | Lamar Jackson (QB, 4181) → **Ladd McConkey (WR, 4343)** (w/ Bcork) | +162 | 92% | value | 0.75 |  |  |
| 3 | Jonathan Taylor (RB, 5349) → **James Cook (RB, 5610)** (w/ MangoPatti) | +261 | 90% | value | 0.50 |  |  |
| 4 | Brian Thomas (WR, 2507) → **Tucker Kraft (TE, 2726)** (w/ jonbonjourvi) | +219 | 83% | value | 0.50 |  |  |
| 5 | Alec Pierce (WR, 1661) → **Terry McLaurin (WR, 1661)** (w/ PaulSm3nis) | +0 | 100% | window | 0.50 |  |  |

### @KevinLake — deck 30 cards · init 0.6 ms · gen 17.4 ms · outlook `not_sure`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Nico Collins (WR, 5302) → **Emeka Egbuka (WR, 5302)** (w/ jonbonjourvi) | +0 | 100% | — | 0.50 |  |  |
| 2 | Garrett Wilson (WR, 5596) → **James Cook (RB, 5610)** (w/ MangoPatti) | +14 | 99% | — | 0.50 |  |  |
| 3 | Patrick Mahomes (QB, 3802) → **Rome Odunze (WR, 3894)** (w/ Bcork) | +92 | 95% | — | 0.75 |  |  |
| 4 | Zay Flowers (WR, 3717) → **Christian McCaffrey (RB, 3785)** (w/ MangoPatti) | +68 | 96% | — | 0.50 |  |  |
| 5 | Omarion Hampton (RB, 6153) → **Drake London (WR, 6265)** (w/ mattmurf77) | +112 | 96% | — | 0.44 |  |  |

---

## Method + fidelity notes

- Built by internal import of `backend.server` (no Flask server): the same session-construction and trade-job code paths as `/api/session/init` + `/api/trades/generate`, with the production flag file.
- Brand-new-user masking: the simulated user's own swipes, tier overrides, league preference, asset prefs, past trade decisions and Thompson shape counts are excluded. League-level state (other members' saved rankings, league likes, draft picks, impressions) is used exactly as production would.
- `log_trade_impressions` is not called — the eval writes nothing user-visible to the DB.
- Latency numbers are local-machine; Render dyno numbers will differ (esp. cold start). The one-time setup line above is the piece the keep-warm ping hides.
- Flags snapshot: see the JSON artifact (`feedback-workspace/deck-eval/deck_eval_20260717T231038Z.json`).
