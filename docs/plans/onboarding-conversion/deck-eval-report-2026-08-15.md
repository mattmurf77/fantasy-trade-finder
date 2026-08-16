# Offline deck-quality + timing eval — first-run consensus decks

*Generated 2026-08-15 22:00 UTC by `scripts/deck_eval.py` (onboarding-conversion plan, build item 2 — the GATE).*

Each row below is one league team simulated as a **brand-new user**: consensus-seeded board only, zero swipes/preferences, production `config/features.json` flags (incl. `trade.need_fit` fit-led decks, trade-engine v2/v3). The first 5 cards of each first-run deck are shown for human scoring.

> **Gate (a) re-run for open-access Phase A** (`docs/business/product/2026-08-14-open-access-onboarding.md` §5 Phase A item 3a).
> **Verdict: PASS on the stated bar, with one named defect the operator should rule on before the flip.**
> Run against **current production data** — see [Data provenance](#data-provenance) and [Verdict](#verdict) below.
> Every claim in the added sections is labelled **measured** (from this run's artifacts), **code-verified**
> (read at a cited `file:line`), or **assumed**.

## Data provenance

**measured.** Production Postgres (`DATABASE_URL_PROD`, Render, `trade_finder`, PostgreSQL 18.3) was accessed
**read-only** and never written to. Because importing `backend.server` runs `init_db()` (DDL), the eval was
**not** pointed at production directly. Instead every production table was `SELECT`-copied into a throwaway
local SQLite mirror (scratch dir, outside the repo) using `backend.database`'s own metadata, and the eval ran
against that mirror. Row counts copied, largest first: `player_value_history` 26 965 · `member_rankings`
**10 816** · `user_events` 8 600 · `elo_history` 8 102 · `trade_impressions` 7 664 · `deck_impressions` 4 965 ·
`players` 2 798 · `swipe_decisions` 2 513 · `draft_picks` 1 104 · `trade_decisions` 544 · `league_members` 156 ·
`model_config` 135 · `leagues` 12 · `league_preferences` 11 · `bad_trade_flags` 5. Rosters and league metadata
came live from the public Sleeper API at run time, exactly as `/api/session/init` gets them.

Leagues evaluated: the **9 numeric Sleeper league ids present in production `leagues`**
(`1180999595377590272`, `1181674778942836736`, `1182123531320094720`, `1205882571070636032`,
`1312076055586050048`, `1312140920132497408`, `1312146456701829120`, `1312583962966650880`,
`1338231586314780672`). The two non-Sleeper rows (`11896` ESPN, `62846` MFL) and the seeded
`test_league_lakeview` row were excluded — the eval's Sleeper fetch cannot resolve them.

## Thresholds (from the plan)

| Metric | Target | This run |
|---|---|---|
| Empty-deck rate | **< 5%** | **0.0%** (0/108) — PASS |
| Insult rate (see [How this run was scored](#how-this-run-was-scored)) | **< 3%** | **1.48%** (8/540) primary rule — PASS (3.70% if no materiality floor — see sensitivity) |
| First-deck gen latency (server-side) | informs <60s TTFT budget | mean 278.9 ms · p95 1015.3 ms — PASS (see [Latency](#latency-what-changed-and-why)) |

**Passing** = empty-deck < 5% AND human-scored insult rate < 3% AND latency compatible with the <60s warm TTFT budget → the trades-first hook screen (build item 4) may proceed. **Failing** any of these → engine cold-start / deck-quality work jumps the build queue; the funnel does not ship showcasing a deck that insults strangers.

## How this run was scored

The card tables below still carry the blank `insulting? y/n` / `would consider? y/n` columns the generator
writes, so a human can over-rule any call. **They are not the source of this run's number.**

**Why a rule instead of hand-marks.** *(measured)* In the prior run
(`deck-eval-report.md`, 2026-07-17) those columns were **never filled** — 235 of 235 first-5 rows are still
blank in the committed file, and no later commit touched it (`git log` shows one commit, `71e1a61`). So the
gate's human-scoring half has **never been executed**, and the prior report's insult cell still literally reads
*"score below, then compute"*. This run therefore states an explicit, reproducible rule, applies it
mechanically to all 540 first-5 cards, and — critically — **re-applies the same rule to the prior run's JSON
artifact** so the two runs are comparable.

**The rule** *(QA-authored operationalization of the prior report's own question: "would the OWNER of this team
feel lowballed or mocked by this offer landing as their first impression of the app?")*. A first-5 card counts
as **insulting** when the user's side is net-negative in consensus value by a material amount **and** at least
one of:

- **I1 — lowball.** `Δ < 0` and `|Δ| / give_value ≥ 20%` — the user eats a ≥20% haircut on the package they
  surrender.
- **I2 — junk-filler.** `Δ < 0` and the return contains an asset at or below the waiver floor
  (consensus value ≤ 350) while the give side contains a top-asset (consensus value ≥ 2500) — the
  "star for scraps" shape.

**Materiality floor: `|Δ| ≥ 500`.** Below that the assets on both sides are bench/waiver tier and the card
reads as churn, not as an insult (e.g. `Stefon Diggs (435) → Chimere Dike (277)` is a −36% haircut on a
435-value bench WR). The floor is the one judgement call in the rule and the verdict is sensitive to it, so
the full sensitivity curve is published below rather than buried.

**Screening argument for the 532 cards the rule does not examine** *(code-verified + measured)*: every card
with `Δ ≥ 0` receives at least as much consensus value as it gives, and consensus value is exactly what the
first-run user is shown (`basis: consensus`, provenance chip "CONSENSUS VALUES"). A card on which the user is
value-positive cannot be a lowball. Only the 78 negative-Δ cards were examined; 8 tripped the rule.

**Sensitivity** *(measured — same rule applied to both runs' JSON artifacts)*:

| Materiality floor | This run (2026-08-15) | Prior run (2026-07-17) |
|---|---|---|
| `|Δ| ≥ 0` (no floor) | 20/540 = **3.70%** ✗ | 2/235 = 0.85% |
| `|Δ| ≥ 250` | 13/540 = **2.41%** ✓ | 2/235 = 0.85% |
| **`|Δ| ≥ 500` (primary)** | **8/540 = 1.48%** ✓ | 2/235 = 0.85% |
| `|Δ| ≥ 1000` | 5/540 = **0.93%** ✓ | 2/235 = 0.85% |
| primary + exempt honest n-for-fewer consolidations¹ | 8/540 = **1.48%** ✓ | **0/235 = 0.00%** |

¹ A raw-Δ rule systematically trips on 2-for-1 consolidation, which loses raw value by construction and which
the engine's marginal-value model prices as fair. Exempting cards where `len(give) > len(receive)`, the return
carries no junk asset, and `fairness ≥ 0.75` removes **both** of the prior run's two hits (@bobphil22 cards
#1/#2, Δ −2748 / −2300, fairness 99%/95%) and **none** of this run's eight. That is the sharpest statement of
what changed: the prior run's only flags were arguable consolidations; this run's are not.

**Decks affected** *(measured)*: 6 of 108 simulated first decks (5.6%) contain ≥1 primary-rule card in their
first five. **0** of them at deck position #1 under the primary rule; 4 at position #1 with no materiality
floor.

Values shown are consensus (DynastyProcess-seeded, KTC-blended) trade values — the exact numbers a first-run
user's cards are built from. Δ = receive − give from the simulated user's perspective.

## Summary

- Leagues evaluated: **9** — teams (first-run sims): **108**
- Empty decks: **0** (0.0%)
- League-init time (build ranking+trade services, per team): mean **0.7 ms**, p95 **1.4 ms**
- First-deck generation time: mean **278.9 ms**, p95 **1015.3 ms**
- Sleeper league fetch (client-side leg, per league): mean **701.4 ms**
- One-time warm-process setup (import: DB + consensus + demo pool): **3.2 s**; universal-pool build: **410.1 ms** (paid once per server process — this is the cold-start component the keep-warm ping, build item 3, exists to hide)
- Deck size: min 22 · median 30.0 · mean 30.3 · max 37
- Deck-size distribution: 0 cards ×0, 1–4 ×0, 5–9 ×0, 10+ ×108

### Auto-flagged cards (fairness < 0.7 or consensus Δ ≤ -1000 — check these first)

- Fantasy Football Version 3 / @Bcork: TreVeyon Henderson (RB, 3384) → Drake Maye (QB, 5046) (fairness 67%, consensus Δ +1662)
- Fantasy Football Version 3 / @Bcork: Dont'e Thornton (WR, 240) + TreVeyon Henderson (RB, 3384) → Ashton Jeanty (RB, 7400) (fairness 48%, consensus Δ +3776)
- Fantasy Football Version 3 / @smozhgani: Isaiah Likely (TE, 1131) + Christian Watson (WR, 1881) → Drake Maye (QB, 5046) (fairness 58%, consensus Δ +2034)
- Fantasy Football Version 3 / @smozhgani: Malik Washington (WR, 336) + Christian Watson (WR, 1881) + Jakobi Meyers (WR, 748) → Drake Maye (QB, 5046) (fairness 56%, consensus Δ +2081)
- Fantasy Football Version 3 / @smozhgani: Ollie Gordon (RB, 280) + Christian Watson (WR, 1881) + Jakobi Meyers (WR, 748) → Drake Maye (QB, 5046) (fairness 55%, consensus Δ +2137)
- Fantasy Football Version 3 / @dondags20: Ricky Pearsall (WR, 630) + Josh Jacobs (RB, 1619) + Chris Godwin (WR, 721) → Drake Maye (QB, 5046) (fairness 56%, consensus Δ +2076)
- Fantasy Football Version 3 / @KevinLake: Cam Skattebo (RB, 2393) + Jayden Reed (WR, 951) → Drake Maye (QB, 5046) (fairness 64%, consensus Δ +1702)
- Lakeview League 🏈 / @KevinLake: Hunter Henry (TE, 424) + Jaylen Warren (RB, 713) → Dalton Kincaid (TE, 1499) + J.K. Dobbins (RB, 461) (fairness 58%, consensus Δ +823)
- Lakeview League 🏈 / @SwaggyJ0: Nico Collins (WR, 3965) → Marvin Harrison (WR, 2643) (fairness 95%, consensus Δ -1322)
- Lakeview League 🏈 / @bobphil22: Woody Marks (RB, 395) + Wan'Dale Robinson (WR, 882) → Dalton Kincaid (TE, 1499) + J.K. Dobbins (RB, 461) (fairness 65%, consensus Δ +683)
- Fantasy Football Version 3 / @mattmurf77: Jahmyr Gibbs (RB, 7913) → Malik Nabers (WR, 6845) (fairness 98%, consensus Δ -1068)
- Fantasy Football Version 3 / @mattmurf77: Jahmyr Gibbs (RB, 7913) + De'Von Achane (RB, 5638) → Malik Nabers (WR, 6845) + Jaxson Dart (QB, 2162) (fairness 94%, consensus Δ -4544)
- Fantasy Football Version 3 / @mattmurf77: Davante Adams (WR, 1121) + Darnell Mooney (WR, 259) → Trevor Lawrence (QB, 2208) (fairness 61%, consensus Δ +828)
- Fantasy Football Version 3 / @MangoPatti: A.J. Brown (WR, 4168) + James Cook (RB, 5677) + CeeDee Lamb (WR, 6862) → Jaxon Smith-Njigba (WR, 8073) + Devin Singletary (RB, 228) + Malik Davis (RB, 229) (fairness 78%, consensus Δ -8177)
- Fantasy Football Version 3 / @MangoPatti: Jalen McMillan (WR, 524) + Quentin Johnston (WR, 1052) + Parker Washington (WR, 1614) → Trevor Lawrence (QB, 2208) + Marvin Harrison (WR, 3297) (fairness 57%, consensus Δ +2315)
- Fantasy Football Version 3 / @PaulSm3nis: Terry McLaurin (WR, 1513) + Tre Tucker (WR, 312) + Bryce Young (QB, 504) → Trevor Lawrence (QB, 2208) + Isaiah Likely (TE, 1131) + Cam Ward (QB, 964) (fairness 54%, consensus Δ +1974)
- Fantasy Football Version 3 / @PaulSm3nis: Terry McLaurin (WR, 1513) + Tyler Lockett (WR, 224) + John Metchie (WR, 227) → RJ Harvey (RB, 982) + Trevor Lawrence (QB, 2208) + James Conner (RB, 241) (fairness 57%, consensus Δ +1467)
- Fantasy Football Version 3 / @bsharp3: Jordan Love (QB, 1241) → Davante Adams (WR, 1121) + Baker Mayfield (QB, 829) (fairness 52%, consensus Δ +709)
- Fantasy Football Version 3 / @bsharp3: Jordan Love (QB, 1241) → Davante Adams (WR, 1121) + Kimani Vidal (RB, 277) (fairness 56%, consensus Δ +157)
- Fantasy Football Version 3 / @gdubs10: Malik Nabers (WR, 6845) + Jaxson Dart (QB, 2162) → Ashton Jeanty (RB, 7400) (fairness 54%, consensus Δ -1607)
- Fantasy Football Version 3 / @gdubs10: Malik Nabers (WR, 6845) + Jordan Addison (WR, 1510) + Malik Willis (QB, 543) → Malik Davis (RB, 229) + Rasheen Ali (RB, 225) + Ashton Jeanty (RB, 7400) (fairness 89%, consensus Δ -1044)
- Fantasy Football Version 3 / @gdubs10: Jaylen Waddle (WR, 3529) + Zach Charbonnet (RB, 830) + Malik Nabers (WR, 6845) → Jahmyr Gibbs (RB, 7913) + Malik Davis (RB, 229) + Audric Estime (RB, 228) (fairness 85%, consensus Δ -2834)
- Fantasy Football Version 3 / @JohnStanfield: Xavier Worthy (WR, 916) + Jerry Jeudy (WR, 348) + Tory Horton (WR, 323) → Trevor Lawrence (QB, 2208) + Cam Ward (QB, 964) (fairness 49%, consensus Δ +1585)
- Fantasy Football Version 3 / @KevinLake: C.J. Stroud (QB, 1158) → Davante Adams (WR, 1121) + Raheim Sanders (RB, 225) (fairness 56%, consensus Δ +188)
- Fantasy Football Version 3 / @KevinLake: Jayden Reed (WR, 951) + Michael Wilson (WR, 1353) → Colston Loveland (TE, 4545) (fairness 50%, consensus Δ +2241)
- La Resistance / @bkey5: Oronde Gadsden (TE, 1046) + Jayden Reed (WR, 951) + Kyle Pitts (TE, 2219) → Makai Lemon (WR, 3179) + TreVeyon Henderson (RB, 3384) (fairness 62%, consensus Δ +2347)
- La Resistance / @bkey5: Oronde Gadsden (TE, 1046) + Jayden Reed (WR, 951) + Elijah Arroyo (TE, 296) → Makai Lemon (WR, 3179) + Tyler Shough (QB, 804) + Tory Horton (WR, 323) (fairness 54%, consensus Δ +2013)
- La Resistance / @bkey5: Oronde Gadsden (TE, 1046) + Michael Wilson (WR, 1353) + Derrick Henry (RB, 1731) → Drake Maye (QB, 5046) + Makai Lemon (WR, 3179) (fairness 50%, consensus Δ +4095)
- La Resistance / @cwoods93: Chris Bell (WR, 537) + Jadarian Price (RB, 2559) → Drake Maye (QB, 5046) (fairness 60%, consensus Δ +1950)
- La Resistance / @cwoods93: Chris Bell (WR, 537) + Isaiah Likely (TE, 1131) + Jadarian Price (RB, 2559) → Makai Lemon (WR, 3179) + TreVeyon Henderson (RB, 3384) (fairness 62%, consensus Δ +2336)
- La Resistance / @cwoods93: Isaiah Likely (TE, 1131) + Rashid Shaheed (WR, 518) + Jalen McMillan (WR, 524) → Makai Lemon (WR, 3179) + Eli Raridon (TE, 289) (fairness 61%, consensus Δ +1295)
- La Resistance / @twilson2320: Tyjae Spears (RB, 331) + Eli Stowers (TE, 1067) + Jake Ferguson (TE, 781) → Makai Lemon (WR, 3179) + Tyler Shough (QB, 804) + Tory Horton (WR, 323) (fairness 51%, consensus Δ +2127)
- La Resistance / @twilson2320: Rhamondre Stevenson (RB, 675) + Zachariah Branch (WR, 446) + David Montgomery (RB, 1083) → TreVeyon Henderson (RB, 3384) + Tory Horton (WR, 323) + Eli Raridon (TE, 289) (fairness 55%, consensus Δ +1792)
- La Resistance / @twilson2320: Eli Stowers (TE, 1067) + Terry McLaurin (WR, 1513) → Drake Maye (QB, 5046) (fairness 50%, consensus Δ +2466)
- La Resistance / @JareBear28: T.J. Hockenson (TE, 384) + George Kittle (TE, 930) + Quentin Johnston (WR, 1052) → TreVeyon Henderson (RB, 3384) + Eli Raridon (TE, 289) (fairness 64%, consensus Δ +1307)
- La Resistance / @JareBear28: Quentin Johnston (WR, 1052) + LeQuint Allen (RB, 247) + Jared Goff (QB, 867) → Makai Lemon (WR, 3179) + Eli Raridon (TE, 289) (fairness 62%, consensus Δ +1302)
- La Resistance / @JareBear28: T.J. Hockenson (TE, 384) + Quentin Johnston (WR, 1052) + Jared Goff (QB, 867) → Makai Lemon (WR, 3179) + Tyler Shough (QB, 804) + Tory Horton (WR, 323) (fairness 54%, consensus Δ +2003)
- La Resistance / @yaboyboston: Romeo Doubs (WR, 633) + Keon Coleman (WR, 292) + Dalton Kincaid (TE, 1324) → Makai Lemon (WR, 3179) + Tyler Shough (QB, 804) (fairness 56%, consensus Δ +1734)
- La Resistance / @MChammer45: Kenyon Sadiq (TE, 1682) + Jaylin Noel (WR, 394) + Tyreek Hill (WR, 377) → Makai Lemon (WR, 3179) + Tory Horton (WR, 323) (fairness 68%, consensus Δ +1049)
- La Resistance / @DerseyShore: AJ Barner (TE, 443) + Matthew Golden (WR, 1117) + Davante Adams (WR, 1121) → Makai Lemon (WR, 3179) + Tyler Shough (QB, 804) + Eli Raridon (TE, 289) (fairness 64%, consensus Δ +1591)
- La Resistance / @treyj19: Josh Jacobs (RB, 1619) + Bhayshul Tuten (RB, 1704) → Drake Maye (QB, 5046) (fairness 66%, consensus Δ +1723)
- La Resistance / @treyj19: Brenton Strange (TE, 703) + Josh Jacobs (RB, 1619) + David Njoku (TE, 280) → TreVeyon Henderson (RB, 3384) + Tory Horton (WR, 323) + Eli Raridon (TE, 289) (fairness 64%, consensus Δ +1394)
- La Resistance / @treyj19: Josh Jacobs (RB, 1619) + Bhayshul Tuten (RB, 1704) + Efton Chism (WR, 225) → Makai Lemon (WR, 3179) + TreVeyon Henderson (RB, 3384) + Eli Raridon (TE, 289) (fairness 52%, consensus Δ +3304)
- La Resistance / @treyj19: Brenton Strange (TE, 703) + Josh Jacobs (RB, 1619) + Bhayshul Tuten (RB, 1704) → Carnell Tate (WR, 4802) + Makai Lemon (WR, 3179) (fairness 50%, consensus Δ +3955)
- SFO / @jonbonjourvi: De'Von Achane (RB, 4723) → Tyler Warren (TE, 4455) + Jordyn Tyson (WR, 2872) (fairness 66%, consensus Δ +2604)

---

## Lakeview League 🏈 (`1180999595377590272`) — 12 teams, format `sf_tep`, fetch 947.5 ms

### @mlakejr — deck 30 cards · init 1.2 ms · gen 45.3 ms · outlook `rebuilder`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Jordan Love (QB, 4242) → **Colston Loveland (TE, 5033)** (w/ SwaggyJ0) | +791 | 84% | window | 0.42 |  |  |
| 2 | Javonte Williams (RB, 1661) → **Jameson Williams (WR, 2104)** (w/ mattmurf77) | +443 | 79% | window | 0.62 |  |  |
| 3 | Tetairoa McMillan (WR, 4611) → **Colston Loveland (TE, 5033)** (w/ SwaggyJ0) | +422 | 92% | value | 0.50 |  |  |
| 4 | Jordan Love (QB, 4242) → **Brock Purdy (QB, 4634)** (w/ SwaggyJ0) | +392 | 92% | value | 0.50 |  |  |
| 5 | Breece Hall (RB, 3624) → **Chris Olave (WR, 4098)** (w/ KevinLake) | +474 | 88% | value | 0.50 |  |  |

### @mattmurf77 — deck 30 cards · init 0.6 ms · gen 32.3 ms · outlook `rebuilder`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Justin Jefferson (WR, 6666) → **Brock Bowers (TE, 6723)** (w/ bmcaloon) | +57 | 99% | window | 0.62 |  |  |
| 2 | Justin Jefferson (WR, 6666) → **Caleb Williams (QB, 7085)** (w/ gildalbora) | +419 | 94% | window | 0.50 |  |  |
| 3 | Jaxson Dart (QB, 5013) → **Colston Loveland (TE, 5033)** (w/ SwaggyJ0) | +20 | 100% | value | 0.54 |  |  |
| 4 | Justin Jefferson (WR, 6666) → **Amon-Ra St. Brown (WR, 6807)** (w/ bmcaloon) | +141 | 98% | value | 0.50 |  |  |
| 5 | Justin Jefferson (WR, 6666) → **Jahmyr Gibbs (RB, 7239)** (w/ gildalbora) | +573 | 92% | value | 0.62 |  |  |

### @pmquinn24 — deck 30 cards · init 0.6 ms · gen 28.7 ms · outlook `contender`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Ashton Jeanty (RB, 6190) → **Justin Jefferson (WR, 6666)** (w/ mattmurf77) | +476 | 93% | window | 0.62 |  |  |
| 2 | Ashton Jeanty (RB, 6190) → **Amon-Ra St. Brown (WR, 6807)** (w/ bmcaloon) | +617 | 91% | window | 0.50 |  |  |
| 3 | Ashton Jeanty (RB, 6190) → **Jahmyr Gibbs (RB, 7239)** (w/ gildalbora) | +1049 | 86% | window | 0.50 |  |  |
| 4 | Ashton Jeanty (RB, 6190) → **Lamar Jackson (QB, 7404)** (w/ bmcaloon) | +1214 | 84% | window | 0.50 |  |  |
| 5 | Jordan Addison (WR, 1197) → **Derrick Henry (RB, 1335)** (w/ KevinLake) | +138 | 90% | window | 0.50 |  |  |

### @bmcaloon — deck 29 cards · init 0.7 ms · gen 37.7 ms · outlook `not_sure`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Brock Bowers (TE, 6723) → **Caleb Williams (QB, 7085)** (w/ gildalbora) | +362 | 95% | — | 0.62 |  |  |
| 2 | Amon-Ra St. Brown (WR, 6807) → **Caleb Williams (QB, 7085)** (w/ gildalbora) | +278 | 96% | — | 0.50 |  |  |
| 3 | Brock Bowers (TE, 6723) → **Jahmyr Gibbs (RB, 7239)** (w/ gildalbora) | +516 | 93% | — | 0.62 |  |  |
| 4 | Drake London (WR, 5168) → **Jalen Hurts (QB, 5568)** (w/ KevinLake) | +400 | 93% | — | 0.58 |  |  |
| 5 | Amon-Ra St. Brown (WR, 6807) → **Jahmyr Gibbs (RB, 7239)** (w/ gildalbora) | +432 | 94% | — | 0.50 |  |  |

### @KevinLake — deck 30 cards · init 0.6 ms · gen 22.2 ms · outlook `contender`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Jalen Hurts (QB, 5568) → **Patrick Mahomes (QB, 5948)** (w/ pmquinn24) | +380 | 94% | value | 0.50 |  |  |
| 2 | Chris Olave (WR, 4098) → **Jordan Love (QB, 4242)** (w/ mlakejr) | +144 | 97% | value | 0.42 |  |  |
| 3 | A.J. Brown (WR, 3325) → **DeVonta Smith (WR, 3442)** (w/ bmcaloon) | +117 | 97% | value | 0.50 |  |  |
| 4 | A.J. Brown (WR, 3325) → **Dak Prescott (QB, 3586)** (w/ bmcaloon) | +261 | 93% | value | 0.42 |  |  |
| 5 | Kenneth Walker (RB, 3817) → **Jonathan Taylor (RB, 4341)** (w/ pmquinn24) | +524 | 88% | value | 0.50 |  |  |

### @gildalbora — deck 30 cards · init 0.6 ms · gen 38.6 ms · outlook `not_sure`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Trevor Lawrence (QB, 5137) → **Drake London (WR, 5168)** (w/ bmcaloon) | +31 | 99% | — | 0.50 |  |  |
| 2 | Jahmyr Gibbs (RB, 7239) → **Lamar Jackson (QB, 7404)** (w/ bmcaloon) | +165 | 98% | — | 0.50 |  |  |
| 3 | Caleb Williams (QB, 7085) → **Lamar Jackson (QB, 7404)** (w/ bmcaloon) | +319 | 96% | — | 0.50 |  |  |
| 4 | Trevor Lawrence (QB, 5137) → **Jalen Hurts (QB, 5568)** (w/ KevinLake) | +431 | 92% | — | 0.50 |  |  |
| 5 | Jahmyr Gibbs (RB, 7239) → **Josh Allen (QB, 8281)** (w/ pmquinn24) | +1042 | 87% | — | 0.50 |  |  |

### @SwaggyJ0 — deck 22 cards · init 0.6 ms · gen 15.5 ms · outlook `rebuilder`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | James Cook (RB, 4500) → **Jaxson Dart (QB, 5013)** (w/ mattmurf77) | +513 | 90% | window | 0.54 |  |  |
| 2 | Nico Collins (WR, 3965) → **Chris Olave (WR, 4098)** (w/ KevinLake) | +133 | 97% | value | 0.50 |  |  |
| 3 | Emeka Egbuka (WR, 4584) → **Tetairoa McMillan (WR, 4611)** (w/ mlakejr) | +27 | 99% | value | 0.50 |  |  |
| 4 | James Cook (RB, 4500) → **Drake London (WR, 5168)** (w/ bmcaloon) | +668 | 87% | window | 0.50 |  |  |
| 5 | James Cook (RB, 4500) → **Trevor Lawrence (QB, 5137)** (w/ gildalbora) | +637 | 88% | window | 0.42 |  |  |

### @pprendergast — deck 30 cards · init 0.6 ms · gen 22.8 ms · outlook `rebuilder`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | George Pickens (WR, 4227) → **Tetairoa McMillan (WR, 4611)** (w/ mlakejr) | +384 | 92% | value | 0.50 |  |  |
| 2 | Justin Herbert (QB, 6253) → **Amon-Ra St. Brown (WR, 6807)** (w/ bmcaloon) | +554 | 92% | value | 0.69 |  |  |
| 3 | Omarion Hampton (RB, 4946) → **Malik Nabers (WR, 5977)** (w/ mlakejr) | +1031 | 83% | value | 0.69 |  |  |
| 4 | Justin Herbert (QB, 6253) → **Justin Jefferson (WR, 6666)** (w/ mattmurf77) | +413 | 94% | value | 0.69 |  |  |
| 5 | George Pickens (WR, 4227) → **Drake London (WR, 5168)** (w/ bmcaloon) | +941 | 82% | value | 0.50 |  |  |

### @sauter — deck 27 cards · init 0.6 ms · gen 20.3 ms · outlook `rebuilder`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | CeeDee Lamb (WR, 6153) → **Ashton Jeanty (RB, 6190)** (w/ pmquinn24) | +37 | 99% | window | 0.50 |  |  |
| 2 | CeeDee Lamb (WR, 6153) → **Drake Maye (QB, 6518)** (w/ mattmurf77) | +365 | 94% | window | 0.50 |  |  |
| 3 | Trey McBride (TE, 6284) → **Drake Maye (QB, 6518)** (w/ mattmurf77) | +234 | 96% | value | 0.62 |  |  |
| 4 | Joe Burrow (QB, 6567) → **Amon-Ra St. Brown (WR, 6807)** (w/ bmcaloon) | +240 | 96% | value | 0.50 |  |  |
| 5 | Puka Nacua (WR, 6862) → **Caleb Williams (QB, 7085)** (w/ gildalbora) | +223 | 97% | value | 0.50 |  |  |

### @johnphillips3289 — deck 30 cards · init 0.6 ms · gen 32.3 ms · outlook `contender`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Jaylen Waddle (WR, 2660) → **Tee Higgins (WR, 2744)** (w/ gildalbora) | +84 | 97% | value | 0.50 |  |  |
| 2 | Christian McCaffrey (RB, 3042) → **A.J. Brown (WR, 3325)** (w/ KevinLake) | +283 | 92% | value | 0.50 |  |  |
| 3 | Bijan Robinson (RB, 7478) → **Josh Allen (QB, 8281)** (w/ pmquinn24) | +803 | 90% | value | 0.42 |  |  |
| 4 | Christian McCaffrey (RB, 3042) → **DeVonta Smith (WR, 3442)** (w/ bmcaloon) | +400 | 88% | value | 0.50 |  |  |
| 5 | Christian McCaffrey (RB, 3042) → **Zay Flowers (WR, 3237)** (w/ bmcaloon) | +195 | 94% | value | 0.50 |  |  |

### @DrByron34 — deck 30 cards · init 0.5 ms · gen 25.1 ms · outlook `rebuilder`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Jared Goff (QB, 2705) → **Tee Higgins (WR, 2744)** (w/ gildalbora) | +39 | 99% | value | 0.50 |  |  |
| 2 | Garrett Wilson (WR, 3939) → **Chris Olave (WR, 4098)** (w/ KevinLake) | +159 | 96% | value | 0.50 |  |  |
| 3 | Garrett Wilson (WR, 3939) → **Jordan Love (QB, 4242)** (w/ mlakejr) | +303 | 93% | value | 0.50 |  |  |
| 4 | Garrett Wilson (WR, 3939) → **Tetairoa McMillan (WR, 4611)** (w/ mlakejr) | +672 | 85% | value | 0.50 |  |  |
| 5 | Garrett Wilson (WR, 3939) → **Jaxson Dart (QB, 5013)** (w/ mattmurf77) | +1074 | 79% | value | 0.50 |  |  |

### @bobphil22 — deck 29 cards · init 0.5 ms · gen 21.0 ms · outlook `rebuilder`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Jayden Daniels (QB, 6275) → **Drake Maye (QB, 6518)** (w/ mattmurf77) | +243 | 96% | value | 0.50 |  |  |
| 2 | Tyler Warren (TE, 4455) → **Jaxson Dart (QB, 5013)** (w/ mattmurf77) | +558 | 89% | value | 0.58 |  |  |
| 3 | Jayden Daniels (QB, 6275) → **Caleb Williams (QB, 7085)** (w/ gildalbora) | +810 | 89% | value | 0.50 |  |  |
| 4 | Rhamondre Stevenson (RB, 589) → **Tua Tagovailoa (QB, 690)** (w/ pmquinn24) | +101 | 85% | value | 0.58 |  |  |
| 5 | Kendre Miller (RB, 237) → **Will Howard (QB, 239)** (w/ mlakejr) | +2 | 99% | value | 0.58 |  |  |

## Fantasy Football Version 3 (`1181674778942836736`) — 12 teams, format `1qb_ppr`, fetch 814.9 ms

### @mattmurf77 — deck 29 cards · init 2.0 ms · gen 37.6 ms · outlook `rebuilder`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Trey McBride (TE, 5376) → **Emeka Egbuka (WR, 5387)** (w/ jonbonjourvi) | +11 | 100% | value | 0.56 |  |  |
| 2 | Drake Maye (QB, 5046) → **Emeka Egbuka (WR, 5387)** (w/ jonbonjourvi) | +341 | 94% | value | 0.56 |  |  |
| 3 | Jahmyr Gibbs (RB, 7913) → **Bijan Robinson (RB, 8390)** (w/ smozhgani) | +477 | 94% | value | 0.50 |  |  |
| 4 | Jaxon Smith-Njigba (WR, 8073) → **Bijan Robinson (RB, 8390)** (w/ smozhgani) | +317 | 96% | value | 0.44 |  |  |
| 5 | Davante Adams (WR, 1121) → **Josh Downs (WR, 1242)** (w/ jonbonjourvi) | +121 | 90% | value | 0.50 |  |  |

### @jonbonjourvi — deck 29 cards · init 0.6 ms · gen 118.3 ms · outlook `rebuilder`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Rashee Rice (WR, 3212) → **Marvin Harrison (WR, 3297)** (w/ bsharp3) | +85 | 97% | value | 0.50 |  |  |
| 2 | Rashee Rice (WR, 3212) → **Rome Odunze (WR, 3655)** (w/ Bcork) | +443 | 88% | value | 0.50 |  |  |
| 3 | Rashee Rice (WR, 3212) → **Jayden Daniels (QB, 4009)** (w/ smozhgani) | +797 | 80% | value | 0.50 |  |  |
| 4 | Puka Nacua (WR, 7725) → **Amon-Ra St. Brown (WR, 7725)** (w/ smozhgani) | +0 | 100% | value | 0.50 |  |  |
| 5 | Justin Herbert (QB, 2904) → **Kyren Williams (RB, 2930)** (w/ PaulSm3nis) | +26 | 99% | value | 0.44 |  |  |

### @Shark357 — deck 30 cards · init 0.6 ms · gen 121.9 ms · outlook `not_sure`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | George Pickens (WR, 4749) → **Chris Olave (WR, 4978)** (w/ MangoPatti) | +229 | 95% | — | 0.50 |  |  |
| 2 | George Pickens (WR, 4749) → **Emeka Egbuka (WR, 5387)** (w/ jonbonjourvi) | +638 | 88% | — | 0.50 |  |  |
| 3 | George Pickens (WR, 4749) → **James Cook (RB, 5677)** (w/ MangoPatti) | +928 | 84% | — | 0.38 |  |  |
| 4 | Trevor Lawrence (QB, 2208) → **Sam LaPorta (TE, 2724)** (w/ smozhgani) | +516 | 81% | — | 0.50 |  |  |
| 5 | Trevor Lawrence (QB, 2208) → **Jalen Hurts (QB, 2853)** (w/ PaulSm3nis) | +645 | 77% | — | 0.50 |  |  |

### @MangoPatti — deck 31 cards · init 0.6 ms · gen 124.5 ms · outlook `contender`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | A.J. Brown (WR, 4168) → **DeVonta Smith (WR, 4208)** (w/ bsharp3) | +40 | 99% | value | 0.50 |  |  |
| 2 | Chris Olave (WR, 4978) → **Emeka Egbuka (WR, 5387)** (w/ jonbonjourvi) | +409 | 92% | value | 0.50 |  |  |
| 3 | A.J. Brown (WR, 4168) → **Breece Hall (RB, 4575)** (w/ bsharp3) | +407 | 91% | value | 0.50 |  |  |
| 4 | CeeDee Lamb (WR, 6862) → **Amon-Ra St. Brown (WR, 7725)** (w/ smozhgani) | +863 | 89% | value | 0.50 |  |  |
| 5 | A.J. Brown (WR, 4168) → **Kenneth Walker (RB, 4669)** (w/ bsharp3) | +501 | 89% | value | 0.50 |  |  |

### @Bcork — deck 30 cards · init 0.7 ms · gen 166.4 ms · outlook `rebuilder`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | TreVeyon Henderson (RB, 3384) → **Drake Maye (QB, 5046)** (w/ mattmurf77) | +1662 | 67% | value | 0.56 |  |  |
| 2 | Dont'e Thornton (WR, 240) + TreVeyon Henderson (RB, 3384) → **Ashton Jeanty (RB, 7400)** (w/ mattmurf77) | +3776 | 48% | value | 0.54 |  |  |
| 3 | Rome Odunze (WR, 3655) → **Jayden Daniels (QB, 4009)** (w/ smozhgani) | +354 | 91% | value | 0.75 |  |  |
| 4 | Jauan Jennings (WR, 374) → **Daniel Jones (QB, 487)** (w/ Shark357) | +113 | 77% | value | 0.88 |  |  |
| 5 | Tyreek Hill (WR, 377) → **Daniel Jones (QB, 487)** (w/ Shark357) | +110 | 77% | value | 0.88 |  |  |

### @smozhgani — deck 30 cards · init 1.3 ms · gen 179.5 ms · outlook `rebuilder`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Isaiah Likely (TE, 1131) + Christian Watson (WR, 1881) → **Drake Maye (QB, 5046)** (w/ mattmurf77) | +2034 | 58% | value | 0.54 |  |  |
| 2 | Malik Washington (WR, 336) + Christian Watson (WR, 1881) + Jakobi Meyers (WR, 748) → **Drake Maye (QB, 5046)** (w/ mattmurf77) | +2081 | 56% | window | 0.59 |  |  |
| 3 | Ollie Gordon (RB, 280) + Christian Watson (WR, 1881) + Jakobi Meyers (WR, 748) → **Drake Maye (QB, 5046)** (w/ mattmurf77) | +2137 | 55% | value | 0.56 |  |  |
| 4 | Chase Brown (RB, 3993) → **Ladd McConkey (WR, 4371)** (w/ Bcork) | +378 | 91% | window | 0.69 |  |  |
| 5 | Joe Burrow (QB, 3423) → **Rome Odunze (WR, 3655)** (w/ Bcork) | +232 | 94% | window | 0.75 |  |  |

### @PaulSm3nis — deck 31 cards · init 0.6 ms · gen 119.9 ms · outlook `contender`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Dalton Kincaid (TE, 1324) → **DJ Moore (WR, 1763)** (w/ bsharp3) | +439 | 75% | window | 0.75 |  |  |
| 2 | Kyren Williams (RB, 2930) → **Saquon Barkley (RB, 3208)** (w/ jonbonjourvi) | +278 | 91% | value | 0.50 |  |  |
| 3 | Kyren Williams (RB, 2930) → **Rashee Rice (WR, 3212)** (w/ jonbonjourvi) | +282 | 91% | value | 0.56 |  |  |
| 4 | Jalen Hurts (QB, 2853) → **Rashee Rice (WR, 3212)** (w/ jonbonjourvi) | +359 | 89% | value | 0.62 |  |  |
| 5 | Kyren Williams (RB, 2930) → **Joe Burrow (QB, 3423)** (w/ smozhgani) | +493 | 86% | value | 0.44 |  |  |

### @bsharp3 — deck 28 cards · init 0.9 ms · gen 136.6 ms · outlook `contender`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Marvin Harrison (WR, 3297) → **TreVeyon Henderson (RB, 3384)** (w/ Bcork) | +87 | 97% | value | 0.31 |  |  |
| 2 | Kenneth Walker (RB, 4669) → **Chris Olave (WR, 4978)** (w/ MangoPatti) | +309 | 94% | value | 0.50 |  |  |
| 3 | Kenneth Walker (RB, 4669) → **George Pickens (WR, 4749)** (w/ Shark357) | +80 | 98% | value | 0.38 |  |  |
| 4 | Marvin Harrison (WR, 3297) → **Rome Odunze (WR, 3655)** (w/ Bcork) | +358 | 90% | value | 0.50 |  |  |
| 5 | Breece Hall (RB, 4575) → **Chris Olave (WR, 4978)** (w/ MangoPatti) | +403 | 92% | value | 0.50 |  |  |

### @gdubs10 — deck 32 cards · init 0.6 ms · gen 124.1 ms · outlook `not_sure`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Malik Nabers (WR, 6845) → **CeeDee Lamb (WR, 6862)** (w/ MangoPatti) | +17 | 100% | — | 0.50 |  |  |
| 2 | Tyler Warren (TE, 4071) → **A.J. Brown (WR, 4168)** (w/ MangoPatti) | +97 | 98% | — | 0.50 |  |  |
| 3 | Jaylen Waddle (WR, 3529) → **Rome Odunze (WR, 3655)** (w/ Bcork) | +126 | 97% | — | 0.50 |  |  |
| 4 | Tyler Warren (TE, 4071) → **Ladd McConkey (WR, 4371)** (w/ Bcork) | +300 | 93% | — | 0.62 |  |  |
| 5 | Tee Higgins (WR, 3332) → **Rome Odunze (WR, 3655)** (w/ Bcork) | +323 | 91% | — | 0.50 |  |  |

### @JohnStanfield — deck 27 cards · init 0.6 ms · gen 120.8 ms · outlook `rebuilder`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Caleb Williams (QB, 3382) → **TreVeyon Henderson (RB, 3384)** (w/ Bcork) | +2 | 100% | value | 0.81 |  |  |
| 2 | Brock Bowers (TE, 6392) → **Bijan Robinson (RB, 8390)** (w/ smozhgani) | +1998 | 76% | value | 0.75 |  |  |
| 3 | Tyler Shough (QB, 804) → **RJ Harvey (RB, 982)** (w/ Shark357) | +178 | 82% | value | 0.75 |  |  |
| 4 | Jalen Milroe (QB, 239) → **LeQuint Allen (RB, 247)** (w/ Bcork) | +8 | 97% | value | 0.81 |  |  |
| 5 | Devin Neal (RB, 246) → **LeQuint Allen (RB, 247)** (w/ Bcork) | +1 | 100% | value | 0.50 |  |  |

### @dondags20 — deck 29 cards · init 0.7 ms · gen 153.2 ms · outlook `contender`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Ricky Pearsall (WR, 630) + Josh Jacobs (RB, 1619) + Chris Godwin (WR, 721) → **Drake Maye (QB, 5046)** (w/ mattmurf77) | +2076 | 56% | value | 0.56 |  |  |
| 2 | Brian Thomas (WR, 2465) → **Justin Herbert (QB, 2904)** (w/ jonbonjourvi) | +439 | 85% | window | 0.50 |  |  |
| 3 | Kyler Murray (QB, 604) + Michael Penix (QB, 326) → **Davante Adams (WR, 1121)** (w/ mattmurf77) | +191 | 81% | value | 0.46 |  |  |
| 4 | Brian Thomas (WR, 2465) → **Saquon Barkley (RB, 3208)** (w/ jonbonjourvi) | +743 | 77% | window | 0.50 |  |  |
| 5 | Lamar Jackson (QB, 4453) → **James Cook (RB, 5677)** (w/ MangoPatti) | +1224 | 78% | window | 0.62 |  |  |

### @KevinLake — deck 31 cards · init 0.6 ms · gen 185.9 ms · outlook `not_sure`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Cam Skattebo (RB, 2393) + Jayden Reed (WR, 951) → **Drake Maye (QB, 5046)** (w/ mattmurf77) | +1702 | 64% | — | 0.54 |  |  |
| 2 | Zay Flowers (WR, 3894) → **Jayden Daniels (QB, 4009)** (w/ smozhgani) | +115 | 97% | — | 0.50 |  |  |
| 3 | Patrick Mahomes (QB, 3030) → **Rashee Rice (WR, 3212)** (w/ jonbonjourvi) | +182 | 94% | — | 0.50 |  |  |
| 4 | Garrett Wilson (WR, 4978) → **Emeka Egbuka (WR, 5387)** (w/ jonbonjourvi) | +409 | 92% | — | 0.50 |  |  |
| 5 | Patrick Mahomes (QB, 3030) → **Quinshon Judkins (RB, 3289)** (w/ jonbonjourvi) | +259 | 92% | — | 0.50 |  |  |

## La Resistance (`1182123531320094720`) — 12 teams, format `1qb_ppr`, fetch 427.3 ms

### @bkey5 — deck 29 cards · init 1.0 ms · gen 30.0 ms · outlook `not_sure`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Caleb Williams (QB, 3382) → **TreVeyon Henderson (RB, 3384)** (w/ mattmurf77) | +2 | 100% | — | 0.38 |  |  |
| 2 | Caleb Williams (QB, 3382) → **Jaylen Waddle (WR, 3529)** (w/ twilson2320) | +147 | 96% | — | 0.50 |  |  |
| 3 | Jaxon Smith-Njigba (WR, 8073) → **Ja'Marr Chase (WR, 8470)** (w/ MChammer45) | +397 | 95% | — | 0.50 |  |  |
| 4 | Jahmyr Gibbs (RB, 7913) → **Ja'Marr Chase (WR, 8470)** (w/ MChammer45) | +557 | 93% | — | 0.56 |  |  |
| 5 | Caleb Williams (QB, 3382) → **Christian McCaffrey (RB, 3796)** (w/ yaboyboston) | +414 | 89% | — | 0.75 |  |  |

### @cwoods93 — deck 29 cards · init 0.9 ms · gen 55.0 ms · outlook `not_sure`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Isaiah Likely (TE, 1131) → **Jonathon Brooks (RB, 1164)** (w/ mattmurf77) | +33 | 97% | — | 0.75 |  |  |
| 2 | C.J. Stroud (QB, 1158) → **Jonathon Brooks (RB, 1164)** (w/ mattmurf77) | +6 | 100% | — | 0.50 |  |  |
| 3 | Jayden Higgins (WR, 1175) → **Terry McLaurin (WR, 1513)** (w/ twilson2320) | +338 | 78% | — | 0.50 |  |  |
| 4 | C.J. Stroud (QB, 1158) → **Terry McLaurin (WR, 1513)** (w/ twilson2320) | +355 | 76% | — | 0.56 |  |  |
| 5 | C.J. Stroud (QB, 1158) → **Dalton Kincaid (TE, 1324)** (w/ yaboyboston) | +166 | 87% | — | 0.75 |  |  |

### @twilson2320 — deck 30 cards · init 2.1 ms · gen 27.1 ms · outlook `contender`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Jaylen Waddle (WR, 3529) → **A.J. Brown (WR, 4168)** (w/ JareBear28) | +639 | 85% | window | 0.50 |  |  |
| 2 | Jalen Hurts (QB, 2853) → **Kyren Williams (RB, 2930)** (w/ MChammer45) | +77 | 97% | value | 0.44 |  |  |
| 3 | Jalen Hurts (QB, 2853) → **Patrick Mahomes (QB, 3030)** (w/ MChammer45) | +177 | 94% | value | 0.50 |  |  |
| 4 | Nico Collins (WR, 4870) → **Garrett Wilson (WR, 4978)** (w/ JareBear28) | +108 | 98% | value | 0.50 |  |  |
| 5 | Nico Collins (WR, 4870) → **Chris Olave (WR, 4978)** (w/ yaboyboston) | +108 | 98% | value | 0.50 |  |  |

### @JareBear28 — deck 29 cards · init 0.7 ms · gen 23.0 ms · outlook `contender`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Garrett Wilson (WR, 4978) → **Chris Olave (WR, 4978)** (w/ yaboyboston) | +0 | 100% | value | 0.50 |  |  |
| 2 | Garrett Wilson (WR, 4978) → **Drake Maye (QB, 5046)** (w/ mattmurf77) | +68 | 99% | value | 0.75 |  |  |
| 3 | Tee Higgins (WR, 3332) → **TreVeyon Henderson (RB, 3384)** (w/ mattmurf77) | +52 | 98% | value | 0.69 |  |  |
| 4 | A.J. Brown (WR, 4168) → **DeVonta Smith (WR, 4208)** (w/ twilson2320) | +40 | 99% | value | 0.50 |  |  |
| 5 | Tee Higgins (WR, 3332) → **Caleb Williams (QB, 3382)** (w/ bkey5) | +50 | 98% | value | 0.50 |  |  |

### @yaboyboston — deck 31 cards · init 0.6 ms · gen 72.5 ms · outlook `rebuilder`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Christian McCaffrey (RB, 3796) → **Jayden Daniels (QB, 4009)** (w/ MChammer45) | +213 | 95% | window | 0.81 |  |  |
| 2 | Christian McCaffrey (RB, 3796) → **Drake Maye (QB, 5046)** (w/ mattmurf77) | +1250 | 75% | window | 0.88 |  |  |
| 3 | Romeo Doubs (WR, 633) + J.K. Dobbins (RB, 532) → **C.J. Stroud (QB, 1158)** (w/ cwoods93) | -7 | 100% | window | 0.79 |  |  |
| 4 | Chris Olave (WR, 4978) → **Drake Maye (QB, 5046)** (w/ mattmurf77) | +68 | 99% | value | 1.00 |  |  |
| 5 | Rashee Rice (WR, 3212) → **Caleb Williams (QB, 3382)** (w/ bkey5) | +170 | 95% | value | 0.75 |  |  |

### @mattmurf77 — deck 30 cards · init 0.6 ms · gen 29.8 ms · outlook `rebuilder`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Drake Maye (QB, 5046) → **Tetairoa McMillan (WR, 5706)** (w/ yaboyboston) | +660 | 88% | value | 1.00 |  |  |
| 2 | TreVeyon Henderson (RB, 3384) → **Luther Burden (WR, 4078)** (w/ JareBear28) | +694 | 83% | value | 0.69 |  |  |
| 3 | TreVeyon Henderson (RB, 3384) → **Tyler Warren (TE, 4071)** (w/ MChammer45) | +687 | 83% | value | 0.69 |  |  |
| 4 | Jonathon Brooks (RB, 1164) → **Jayden Higgins (WR, 1175)** (w/ cwoods93) | +11 | 99% | value | 0.69 |  |  |
| 5 | Tyler Shough (QB, 804) → **Oronde Gadsden (TE, 1046)** (w/ bkey5) | +242 | 77% | value | 0.75 |  |  |

### @MChammer45 — deck 30 cards · init 0.5 ms · gen 18.5 ms · outlook `rebuilder`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Jayden Daniels (QB, 4009) → **Colston Loveland (TE, 4545)** (w/ yaboyboston) | +536 | 88% | value | 0.75 |  |  |
| 2 | Tyler Warren (TE, 4071) → **Colston Loveland (TE, 4545)** (w/ yaboyboston) | +474 | 90% | value | 0.50 |  |  |
| 3 | Marvin Harrison (WR, 3297) → **TreVeyon Henderson (RB, 3384)** (w/ mattmurf77) | +87 | 97% | value | 0.69 |  |  |
| 4 | Marvin Harrison (WR, 3297) → **Caleb Williams (QB, 3382)** (w/ bkey5) | +85 | 98% | value | 0.50 |  |  |
| 5 | Tyler Warren (TE, 4071) → **Drake Maye (QB, 5046)** (w/ mattmurf77) | +975 | 81% | value | 0.75 |  |  |

### @dubbasparks — deck 30 cards · init 0.6 ms · gen 20.8 ms · outlook `rebuilder`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Puka Nacua (WR, 7725) → **Jaxon Smith-Njigba (WR, 8073)** (w/ bkey5) | +348 | 96% | value | 0.50 |  |  |
| 2 | Trey McBride (TE, 5376) → **Tetairoa McMillan (WR, 5706)** (w/ yaboyboston) | +330 | 94% | value | 0.50 |  |  |
| 3 | George Pickens (WR, 4749) → **Drake Maye (QB, 5046)** (w/ mattmurf77) | +297 | 94% | value | 0.75 |  |  |
| 4 | D'Andre Swift (RB, 1521) → **Parker Washington (WR, 1614)** (w/ JareBear28) | +93 | 94% | window | 0.56 |  |  |
| 5 | Josh Allen (QB, 6421) → **Jaxon Smith-Njigba (WR, 8073)** (w/ bkey5) | +1652 | 80% | window | 0.50 |  |  |

### @DerseyShore — deck 30 cards · init 0.6 ms · gen 17.5 ms · outlook `rebuilder`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Kenneth Walker (RB, 4669) → **Drake Maye (QB, 5046)** (w/ mattmurf77) | +377 | 92% | window | 0.50 |  |  |
| 2 | Kenneth Walker (RB, 4669) → **Tetairoa McMillan (WR, 5706)** (w/ yaboyboston) | +1037 | 82% | window | 0.38 |  |  |
| 3 | Lamar Jackson (QB, 4453) → **Tetairoa McMillan (WR, 5706)** (w/ yaboyboston) | +1253 | 78% | window | 0.75 |  |  |
| 4 | Davante Adams (WR, 1121) → **Jayden Higgins (WR, 1175)** (w/ cwoods93) | +54 | 95% | window | 0.50 |  |  |
| 5 | De'Von Achane (RB, 5638) → **Tetairoa McMillan (WR, 5706)** (w/ yaboyboston) | +68 | 99% | value | 0.38 |  |  |

### @treyj19 — deck 30 cards · init 1.1 ms · gen 24.2 ms · outlook `contender`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Ladd McConkey (WR, 4371) → **Breece Hall (RB, 4575)** (w/ JareBear28) | +204 | 96% | window | 0.44 |  |  |
| 2 | Ladd McConkey (WR, 4371) → **Nico Collins (WR, 4870)** (w/ twilson2320) | +499 | 90% | window | 0.50 |  |  |
| 3 | CeeDee Lamb (WR, 6862) → **Justin Jefferson (WR, 7008)** (w/ bkey5) | +146 | 98% | value | 0.50 |  |  |
| 4 | Ladd McConkey (WR, 4371) → **Colston Loveland (TE, 4545)** (w/ yaboyboston) | +174 | 96% | value | 0.50 |  |  |
| 5 | Justin Herbert (QB, 2904) → **Rashee Rice (WR, 3212)** (w/ yaboyboston) | +308 | 90% | value | 0.75 |  |  |

### @hhardy23 — deck 30 cards · init 0.6 ms · gen 17.8 ms · outlook `rebuilder`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Chase Brown (RB, 3993) → **DeVonta Smith (WR, 4208)** (w/ twilson2320) | +215 | 95% | value | 0.50 |  |  |
| 2 | Joe Burrow (QB, 3423) → **Jaylen Waddle (WR, 3529)** (w/ twilson2320) | +106 | 97% | value | 0.50 |  |  |
| 3 | Tucker Kraft (TE, 3028) → **TreVeyon Henderson (RB, 3384)** (w/ mattmurf77) | +356 | 90% | value | 0.62 |  |  |
| 4 | Chase Brown (RB, 3993) → **Breece Hall (RB, 4575)** (w/ JareBear28) | +582 | 87% | value | 0.50 |  |  |
| 5 | Chase Brown (RB, 3993) → **Garrett Wilson (WR, 4978)** (w/ JareBear28) | +985 | 80% | value | 0.56 |  |  |

### @Bcork — deck 28 cards · init 0.6 ms · gen 18.3 ms · outlook `rebuilder`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Jonathan Taylor (RB, 5403) → **Tetairoa McMillan (WR, 5706)** (w/ yaboyboston) | +303 | 95% | window | 0.50 |  |  |
| 2 | Saquon Barkley (RB, 3208) → **Caleb Williams (QB, 3382)** (w/ bkey5) | +174 | 95% | window | 0.50 |  |  |
| 3 | Saquon Barkley (RB, 3208) → **TreVeyon Henderson (RB, 3384)** (w/ mattmurf77) | +176 | 95% | window | 0.50 |  |  |
| 4 | Blake Corum (RB, 922) → **C.J. Stroud (QB, 1158)** (w/ cwoods93) | +236 | 80% | window | 0.62 |  |  |
| 5 | Blake Corum (RB, 922) → **Jayden Higgins (WR, 1175)** (w/ cwoods93) | +253 | 78% | window | 0.56 |  |  |

## Bush League  (`1205882571070636032`) — 12 teams, format `1qb_ppr`, fetch 544.4 ms

### @dwasson17 — deck 29 cards · init 0.9 ms · gen 18.3 ms · outlook `contender`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Zay Flowers (WR, 3894) → **A.J. Brown (WR, 4168)** (w/ ddragos7) | +274 | 93% | window | 0.50 |  |  |
| 2 | Zay Flowers (WR, 3894) → **Jayden Daniels (QB, 4009)** (w/ ddragos7) | +115 | 97% | value | 0.69 |  |  |
| 3 | Tetairoa McMillan (WR, 5706) → **Omarion Hampton (RB, 5983)** (w/ gsteskal23) | +277 | 95% | value | 0.56 |  |  |
| 4 | Jonathan Taylor (RB, 5403) → **James Cook (RB, 5677)** (w/ xfactr27) | +274 | 95% | value | 0.50 |  |  |
| 5 | Tetairoa McMillan (WR, 5706) → **CeeDee Lamb (WR, 6862)** (w/ Dez07) | +1156 | 79% | window | 0.50 |  |  |

### @ShanerBaner31 — deck 30 cards · init 0.5 ms · gen 22.4 ms · outlook `contender`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Marvin Harrison (WR, 3297) → **Tee Higgins (WR, 3332)** (w/ dwasson17) | +35 | 99% | window | 0.50 |  |  |
| 2 | Justin Herbert (QB, 2904) → **Saquon Barkley (RB, 3208)** (w/ Bcork) | +304 | 90% | window | 0.62 |  |  |
| 3 | Marvin Harrison (WR, 3297) → **Christian McCaffrey (RB, 3796)** (w/ xfactr27) | +499 | 87% | window | 0.50 |  |  |
| 4 | Brian Thomas (WR, 2465) → **Kyren Williams (RB, 2930)** (w/ Bcork) | +465 | 84% | window | 0.56 |  |  |
| 5 | Marvin Harrison (WR, 3297) → **Chase Brown (RB, 3993)** (w/ ddragos7) | +696 | 83% | window | 0.50 |  |  |

### @Bcork — deck 30 cards · init 0.6 ms · gen 20.1 ms · outlook `contender`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Garrett Wilson (WR, 4978) → **Chris Olave (WR, 4978)** (w/ gsteskal23) | +0 | 100% | value | 0.50 |  |  |
| 2 | Jalen Hurts (QB, 2853) → **Justin Herbert (QB, 2904)** (w/ ShanerBaner31) | +51 | 98% | value | 0.50 |  |  |
| 3 | Garrett Wilson (WR, 4978) → **Drake Maye (QB, 5046)** (w/ Dez07) | +68 | 99% | value | 0.56 |  |  |
| 4 | Garrett Wilson (WR, 4978) → **Jonathan Taylor (RB, 5403)** (w/ dwasson17) | +425 | 92% | window | 0.38 |  |  |
| 5 | Garrett Wilson (WR, 4978) → **James Cook (RB, 5677)** (w/ xfactr27) | +699 | 88% | window | 0.44 |  |  |

### @Dez07 — deck 30 cards · init 0.5 ms · gen 13.8 ms · outlook `rebuilder`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Breece Hall (RB, 4575) → **Tetairoa McMillan (WR, 5706)** (w/ dwasson17) | +1131 | 80% | window | 0.56 |  |  |
| 2 | Breece Hall (RB, 4575) → **Omarion Hampton (RB, 5983)** (w/ gsteskal23) | +1408 | 76% | window | 0.50 |  |  |
| 3 | Breece Hall (RB, 4575) → **George Pickens (WR, 4749)** (w/ ddragos7) | +174 | 96% | value | 0.50 |  |  |
| 4 | Lamar Jackson (QB, 4453) → **George Pickens (WR, 4749)** (w/ ddragos7) | +296 | 94% | value | 0.44 |  |  |
| 5 | CeeDee Lamb (WR, 6862) → **Justin Jefferson (WR, 7008)** (w/ xfactr27) | +146 | 98% | value | 0.50 |  |  |

### @gsteskal23 — deck 30 cards · init 0.6 ms · gen 18.3 ms · outlook `rebuilder`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Chris Olave (WR, 4978) → **Drake Maye (QB, 5046)** (w/ Dez07) | +68 | 99% | value | 0.50 |  |  |
| 2 | Chris Olave (WR, 4978) → **Garrett Wilson (WR, 4978)** (w/ Bcork) | +0 | 100% | value | 0.50 |  |  |
| 3 | Chris Olave (WR, 4978) → **Emeka Egbuka (WR, 5387)** (w/ Dez07) | +409 | 92% | value | 0.50 |  |  |
| 4 | DeVonta Smith (WR, 4208) → **George Pickens (WR, 4749)** (w/ ddragos7) | +541 | 89% | value | 0.50 |  |  |
| 5 | Chris Olave (WR, 4978) → **Tetairoa McMillan (WR, 5706)** (w/ dwasson17) | +728 | 87% | value | 0.50 |  |  |

### @ddragos7 — deck 28 cards · init 0.5 ms · gen 17.5 ms · outlook `contender`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | George Pickens (WR, 4749) → **Garrett Wilson (WR, 4978)** (w/ Bcork) | +229 | 95% | value | 0.50 |  |  |
| 2 | George Pickens (WR, 4749) → **Chris Olave (WR, 4978)** (w/ gsteskal23) | +229 | 95% | value | 0.50 |  |  |
| 3 | George Pickens (WR, 4749) → **Drake Maye (QB, 5046)** (w/ Dez07) | +297 | 94% | value | 0.44 |  |  |
| 4 | George Pickens (WR, 4749) → **Trey McBride (TE, 5376)** (w/ dwasson17) | +627 | 88% | value | 0.31 |  |  |
| 5 | George Pickens (WR, 4749) → **Emeka Egbuka (WR, 5387)** (w/ Dez07) | +638 | 88% | value | 0.50 |  |  |

### @xfactr27 — deck 30 cards · init 0.5 ms · gen 21.3 ms · outlook `not_sure`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | James Cook (RB, 5677) → **Tetairoa McMillan (WR, 5706)** (w/ dwasson17) | +29 | 100% | — | 0.56 |  |  |
| 2 | De'Von Achane (RB, 5638) → **Tetairoa McMillan (WR, 5706)** (w/ dwasson17) | +68 | 99% | — | 0.56 |  |  |
| 3 | Christian McCaffrey (RB, 3796) → **Zay Flowers (WR, 3894)** (w/ dwasson17) | +98 | 98% | — | 0.56 |  |  |
| 4 | Christian McCaffrey (RB, 3796) → **Jayden Daniels (QB, 4009)** (w/ ddragos7) | +213 | 95% | — | 0.69 |  |  |
| 5 | Puka Nacua (WR, 7725) → **Jahmyr Gibbs (RB, 7913)** (w/ Dez07) | +188 | 98% | — | 0.50 |  |  |

### @macbfarber — deck 30 cards · init 0.5 ms · gen 23.9 ms · outlook `contender`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Joe Burrow (QB, 3423) → **A.J. Brown (WR, 4168)** (w/ ddragos7) | +745 | 82% | window | 0.50 |  |  |
| 2 | Trevor Lawrence (QB, 2208) → **Javonte Williams (RB, 2245)** (w/ Dez07) | +37 | 98% | window | 0.56 |  |  |
| 3 | Trevor Lawrence (QB, 2208) → **Kyren Williams (RB, 2930)** (w/ Bcork) | +722 | 75% | window | 0.69 |  |  |
| 4 | Nico Collins (WR, 4870) → **Garrett Wilson (WR, 4978)** (w/ Bcork) | +108 | 98% | value | 0.50 |  |  |
| 5 | Nico Collins (WR, 4870) → **Chris Olave (WR, 4978)** (w/ gsteskal23) | +108 | 98% | value | 0.50 |  |  |

### @zinkand — deck 30 cards · init 0.7 ms · gen 46.9 ms · outlook `not_sure`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Luther Burden (WR, 4078) → **A.J. Brown (WR, 4168)** (w/ ddragos7) | +90 | 98% | — | 0.50 |  |  |
| 2 | Ladd McConkey (WR, 4371) → **Colston Loveland (TE, 4545)** (w/ gsteskal23) | +174 | 96% | — | 0.62 |  |  |
| 3 | Ashton Jeanty (RB, 7400) → **Jahmyr Gibbs (RB, 7913)** (w/ Dez07) | +513 | 94% | — | 0.50 |  |  |
| 4 | Ladd McConkey (WR, 4371) → **George Pickens (WR, 4749)** (w/ ddragos7) | +378 | 92% | — | 0.50 |  |  |
| 5 | Luther Burden (WR, 4078) → **Colston Loveland (TE, 4545)** (w/ gsteskal23) | +467 | 90% | — | 0.62 |  |  |

### @nmoore9 — deck 30 cards · init 0.6 ms · gen 17.9 ms · outlook `not_sure`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Brock Bowers (TE, 6392) → **Josh Allen (QB, 6421)** (w/ dwasson17) | +29 | 100% | — | 0.50 |  |  |
| 2 | Drake London (WR, 5853) → **Omarion Hampton (RB, 5983)** (w/ gsteskal23) | +130 | 98% | — | 0.50 |  |  |
| 3 | Rashee Rice (WR, 3212) → **Marvin Harrison (WR, 3297)** (w/ ShanerBaner31) | +85 | 97% | — | 0.50 |  |  |
| 4 | Tyler Warren (TE, 4071) → **A.J. Brown (WR, 4168)** (w/ ddragos7) | +97 | 98% | — | 0.44 |  |  |
| 5 | Tyler Warren (TE, 4071) → **DeVonta Smith (WR, 4208)** (w/ gsteskal23) | +137 | 97% | — | 0.50 |  |  |

### @chrisfarrell50 — deck 30 cards · init 0.6 ms · gen 19.1 ms · outlook `not_sure`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Kenneth Walker (RB, 4669) → **George Pickens (WR, 4749)** (w/ ddragos7) | +80 | 98% | — | 0.56 |  |  |
| 2 | Jameson Williams (WR, 2683) → **Sam LaPorta (TE, 2724)** (w/ Dez07) | +41 | 98% | — | 0.44 |  |  |
| 3 | Kenneth Walker (RB, 4669) → **Chris Olave (WR, 4978)** (w/ gsteskal23) | +309 | 94% | — | 0.56 |  |  |
| 4 | Tucker Kraft (TE, 3028) → **Saquon Barkley (RB, 3208)** (w/ Bcork) | +180 | 94% | — | 0.50 |  |  |
| 5 | Tucker Kraft (TE, 3028) → **Tee Higgins (WR, 3332)** (w/ dwasson17) | +304 | 91% | — | 0.69 |  |  |

### @tud32994 — deck 30 cards · init 0.6 ms · gen 19.7 ms · outlook `rebuilder`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Patrick Mahomes (QB, 3030) → **Marvin Harrison (WR, 3297)** (w/ ShanerBaner31) | +267 | 92% | window | 0.38 |  |  |
| 2 | Patrick Mahomes (QB, 3030) → **Jayden Daniels (QB, 4009)** (w/ ddragos7) | +979 | 76% | window | 0.50 |  |  |
| 3 | Christian Watson (WR, 1881) → **Kyle Pitts (TE, 2219)** (w/ Bcork) | +338 | 85% | window | 0.56 |  |  |
| 4 | Christian Watson (WR, 1881) → **Bucky Irving (RB, 2208)** (w/ gsteskal23) | +327 | 85% | window | 0.50 |  |  |
| 5 | Amon-Ra St. Brown (WR, 7725) → **Jahmyr Gibbs (RB, 7913)** (w/ Dez07) | +188 | 98% | value | 0.50 |  |  |

## Lakeview League 🏈 (`1312076055586050048`) — 12 teams, format `sf_tep`, fetch 544.8 ms

### @mlakejr — deck 33 cards · init 0.7 ms · gen 181.1 ms · outlook `rebuilder`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Jaylin Noel (WR, 366) → **Isaac TeSlaa (WR, 363)** (w/ mattmurf77) · likes-you | -3 | 100% | — | — |  |  |
| 2 | J.J. McCarthy (QB, 423) → **Rachaad White (RB, 427)** (w/ mattmurf77) · likes-you | +4 | 100% | — | — |  |  |
| 3 | Nicholas Singleton (RB, 439) → **Isaac TeSlaa (WR, 363)** (w/ mattmurf77) · likes-you | -76 | 97% | — | — |  |  |
| 4 | DJ Moore (WR, 1161) + Nicholas Singleton (RB, 439) → **Dalton Kincaid (TE, 1499) + J.K. Dobbins (RB, 461)** (w/ mattmurf77) | +360 | 82% | value | 0.44 |  |  |
| 5 | Malik Willis (QB, 1256) + Jordan Love (QB, 4242) → **Justin Jefferson (WR, 6666)** (w/ mattmurf77) | +1168 | 76% | value | 0.50 |  |  |

### @mattmurf77 — deck 30 cards · init 0.7 ms · gen 36.0 ms · outlook `rebuilder`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Justin Jefferson (WR, 6666) → **Brock Bowers (TE, 6723)** (w/ bmcaloon) | +57 | 99% | window | 0.62 |  |  |
| 2 | Jaxson Dart (QB, 5013) → **Colston Loveland (TE, 5033)** (w/ SwaggyJ0) | +20 | 100% | value | 0.54 |  |  |
| 3 | Justin Jefferson (WR, 6666) → **Amon-Ra St. Brown (WR, 6807)** (w/ bmcaloon) | +141 | 98% | value | 0.50 |  |  |
| 4 | Justin Jefferson (WR, 6666) → **Caleb Williams (QB, 7085)** (w/ gildalbora) | +419 | 94% | window | 0.50 |  |  |
| 5 | Justin Jefferson (WR, 6666) → **Jahmyr Gibbs (RB, 7239)** (w/ gildalbora) | +573 | 92% | value | 0.56 |  |  |

### @pmquinn24 — deck 34 cards · init 0.6 ms · gen 186.3 ms · outlook `contender`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Stefon Diggs (WR, 435) → **Chimere Dike (WR, 277)** (w/ mattmurf77) · likes-you | -158 | 93% | — | — |  |  |
| 2 | Stefon Diggs (WR, 435) → **Jack Bech (WR, 283)** (w/ mattmurf77) · likes-you | -152 | 94% | — | — |  |  |
| 3 | Cam Skattebo (RB, 1818) → **Dalton Kincaid (TE, 1499)** (w/ mattmurf77) · likes-you | -319 | 98% | — | — |  |  |
| 4 | Cam Skattebo (RB, 1818) + Stefon Diggs (WR, 435) → **Dalton Kincaid (TE, 1499) + J.K. Dobbins (RB, 461)** (w/ mattmurf77) | -293 | 87% | value | 0.44 |  |  |
| 5 | Ashton Jeanty (RB, 6190) → **Justin Herbert (QB, 6253)** (w/ pprendergast) | +63 | 99% | window | 0.50 |  |  |

### @bmcaloon — deck 31 cards · init 0.5 ms · gen 200.6 ms · outlook `rebuilder`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Eli Raridon (TE, 382) → **Jack Bech (WR, 283)** (w/ mattmurf77) · likes-you | -99 | 95% | — | — |  |  |
| 2 | Tony Pollard (RB, 459) → **Rachaad White (RB, 427)** (w/ mattmurf77) · likes-you | -32 | 99% | — | — |  |  |
| 3 | Bhayshul Tuten (RB, 1305) → **Omar Cooper (WR, 892)** (w/ mattmurf77) · likes-you | -413 | 95% | — | — |  |  |
| 4 | Josh Jacobs (RB, 1285) + Tony Pollard (RB, 459) → **Dalton Kincaid (TE, 1499) + J.K. Dobbins (RB, 461)** (w/ mattmurf77) | +216 | 89% | value | 0.47 |  |  |
| 5 | Amon-Ra St. Brown (WR, 6807) → **Caleb Williams (QB, 7085)** (w/ gildalbora) | +278 | 96% | value | 0.50 |  |  |

### @KevinLake — deck 37 cards · init 0.6 ms · gen 185.9 ms · outlook `contender`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Hunter Henry (TE, 424) → **Isaac TeSlaa (WR, 363)** (w/ mattmurf77) · likes-you | -61 | 98% | — | — |  |  |
| 2 | Tyler Shough (QB, 2123) → **Jameson Williams (WR, 2104)** (w/ mattmurf77) · likes-you | -19 | 100% | — | — |  |  |
| 3 | Jadarian Price (RB, 1937) → **Dalton Kincaid (TE, 1499)** (w/ mattmurf77) · likes-you | -438 | 97% | — | — |  |  |
| 4 | Jalen Hurts (QB, 5568) → **Justin Jefferson (WR, 6666)** (w/ mattmurf77) | +1098 | 80% | value | 0.58 |  |  |
| 5 | Hunter Henry (TE, 424) + Jaylen Warren (RB, 713) → **Dalton Kincaid (TE, 1499) + J.K. Dobbins (RB, 461)** (w/ mattmurf77) | +823 | 58% | value | 0.50 |  |  |

### @gildalbora — deck 33 cards · init 0.6 ms · gen 218.0 ms · outlook `rebuilder`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Calvin Ridley (WR, 257) → **Justin Joly (TE, 278)** (w/ mattmurf77) · likes-you | +21 | 99% | — | — |  |  |
| 2 | Jahmyr Gibbs (RB, 7239) → **Justin Jefferson (WR, 6666)** (w/ mattmurf77) · likes-you | -573 | 99% | — | — |  |  |
| 3 | Tee Higgins (WR, 2744) → **Luther Burden (WR, 3282)** (w/ SwaggyJ0) | +538 | 84% | window | 0.50 |  |  |
| 4 | Tee Higgins (WR, 2744) → **Tucker Kraft (TE, 3510)** (w/ mlakejr) | +766 | 78% | window | 0.62 |  |  |
| 5 | Trevor Lawrence (QB, 5137) → **Drake London (WR, 5168)** (w/ bmcaloon) | +31 | 99% | value | 0.50 |  |  |

### @SwaggyJ0 — deck 26 cards · init 0.6 ms · gen 174.2 ms · outlook `rebuilder`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Jerry Jeudy (WR, 329) → **Jack Bech (WR, 283)** (w/ mattmurf77) · likes-you | -46 | 98% | — | — |  |  |
| 2 | Nico Collins (WR, 3965) → **Marvin Harrison (WR, 2643)** (w/ mattmurf77) · likes-you | -1322 | 95% | — | — |  |  |
| 3 | Isaiah Likely (TE, 1362) → **Omar Cooper (WR, 892)** (w/ mattmurf77) · likes-you | -470 | 95% | — | — |  |  |
| 4 | Isaiah Likely (TE, 1362) + Jerry Jeudy (WR, 329) → **Dalton Kincaid (TE, 1499) + J.K. Dobbins (RB, 461)** (w/ mattmurf77) | +269 | 86% | value | 0.47 |  |  |
| 5 | James Cook (RB, 4500) → **Omarion Hampton (RB, 4946)** (w/ pprendergast) | +446 | 91% | window | 0.50 |  |  |

### @pprendergast — deck 30 cards · init 0.6 ms · gen 179.3 ms · outlook `rebuilder`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Justin Herbert (QB, 6253) → **Brock Bowers (TE, 6723)** (w/ bmcaloon) | +470 | 93% | window | 0.50 |  |  |
| 2 | Justin Herbert (QB, 6253) → **Justin Jefferson (WR, 6666)** (w/ mattmurf77) | +413 | 94% | value | 0.62 |  |  |
| 3 | Cam Ward (QB, 2574) → **Jordyn Tyson (WR, 2872)** (w/ gildalbora) | +298 | 90% | value | 0.62 |  |  |
| 4 | George Pickens (WR, 4227) → **Tetairoa McMillan (WR, 4611)** (w/ mlakejr) | +384 | 92% | value | 0.50 |  |  |
| 5 | Travis Etienne (RB, 1840) → **Tyler Shough (QB, 2123)** (w/ KevinLake) | +283 | 87% | window | 0.58 |  |  |

### @sauter — deck 29 cards · init 0.6 ms · gen 186.1 ms · outlook `rebuilder`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Travis Hunter (WR, 662) + CeeDee Lamb (WR, 6153) → **Justin Jefferson (WR, 6666)** (w/ mattmurf77) | -149 | 100% | value | 0.50 |  |  |
| 2 | Bo Nix (QB, 4904) → **Colston Loveland (TE, 5033)** (w/ SwaggyJ0) | +129 | 97% | value | 0.42 |  |  |
| 3 | Joe Burrow (QB, 6567) → **Amon-Ra St. Brown (WR, 6807)** (w/ bmcaloon) | +240 | 96% | value | 0.50 |  |  |
| 4 | Puka Nacua (WR, 6862) → **Caleb Williams (QB, 7085)** (w/ gildalbora) | +223 | 97% | value | 0.50 |  |  |
| 5 | Harold Fannin (TE, 3160) → **Luther Burden (WR, 3282)** (w/ SwaggyJ0) | +122 | 96% | value | 0.50 |  |  |

### @johnphillips3289 — deck 29 cards · init 0.6 ms · gen 222.6 ms · outlook `not_sure`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Parker Washington (WR, 1319) + Courtland Sutton (WR, 714) → **Dalton Kincaid (TE, 1499) + J.K. Dobbins (RB, 461)** (w/ mattmurf77) | -73 | 96% | — | 0.41 |  |  |
| 2 | Theo Johnson (TE, 287) + Matthew Stafford (QB, 1344) → **Dalton Kincaid (TE, 1499) + J.K. Dobbins (RB, 461)** (w/ mattmurf77) | +329 | 84% | — | 0.51 |  |  |
| 3 | Parker Washington (WR, 1319) + Theo Johnson (TE, 287) → **Dalton Kincaid (TE, 1499)** (w/ mattmurf77) | -107 | 96% | — | 0.50 |  |  |
| 4 | Christian McCaffrey (RB, 3042) → **Chase Brown (RB, 3206)** (w/ bmcaloon) | +164 | 95% | — | 0.50 |  |  |
| 5 | Christian McCaffrey (RB, 3042) → **Zay Flowers (WR, 3237)** (w/ bmcaloon) | +195 | 94% | — | 0.50 |  |  |

### @DrByron34 — deck 28 cards · init 1.9 ms · gen 209.1 ms · outlook `rebuilder`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Jared Goff (QB, 2705) → **Jordyn Tyson (WR, 2872)** (w/ gildalbora) | +167 | 94% | window | 0.58 |  |  |
| 2 | Christian Watson (WR, 1510) + Chris Godwin (WR, 599) → **Dalton Kincaid (TE, 1499) + J.K. Dobbins (RB, 461)** (w/ mattmurf77) | -149 | 93% | value | 0.41 |  |  |
| 3 | Jared Goff (QB, 2705) → **Tee Higgins (WR, 2744)** (w/ gildalbora) | +39 | 99% | value | 0.58 |  |  |
| 4 | C.J. Stroud (QB, 2746) → **Jordyn Tyson (WR, 2872)** (w/ gildalbora) | +126 | 96% | value | 0.58 |  |  |
| 5 | TreVeyon Henderson (RB, 2604) → **Jordyn Tyson (WR, 2872)** (w/ gildalbora) | +268 | 91% | value | 0.50 |  |  |

### @bobphil22 — deck 32 cards · init 1.4 ms · gen 187.7 ms · outlook `rebuilder`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Woody Marks (RB, 395) + Wan'Dale Robinson (WR, 882) → **Dalton Kincaid (TE, 1499) + J.K. Dobbins (RB, 461)** (w/ mattmurf77) | +683 | 65% | value | 0.41 |  |  |
| 2 | Jayden Daniels (QB, 6275) → **Caleb Williams (QB, 7085)** (w/ gildalbora) | +810 | 89% | value | 0.50 |  |  |
| 3 | Blake Corum (RB, 735) → **Ty Simpson (QB, 871)** (w/ SwaggyJ0) | +136 | 84% | window | 0.67 |  |  |
| 4 | Quinshon Judkins (RB, 2631) + Rome Odunze (WR, 2882) → **Justin Jefferson (WR, 6666)** (w/ mattmurf77) | +1153 | 78% | value | 0.54 |  |  |
| 5 | Woody Marks (RB, 395) → **J.J. McCarthy (QB, 423)** (w/ mlakejr) | +28 | 93% | window | 0.58 |  |  |

## Fantasy Football Version 3 (`1312140920132497408`) — 12 teams, format `1qb_ppr`, fetch 587.6 ms

### @mattmurf77 — deck 35 cards · init 1.9 ms · gen 653.5 ms · outlook `rebuilder`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Jahmyr Gibbs (RB, 7913) → **Malik Nabers (WR, 6845)** (w/ gdubs10) · likes-you | -1068 | 98% | — | — |  |  |
| 2 | Ashton Jeanty (RB, 7400) → **Malik Nabers (WR, 6845)** (w/ gdubs10) · likes-you | -555 | 99% | — | — |  |  |
| 3 | Jahmyr Gibbs (RB, 7913) + De'Von Achane (RB, 5638) → **Malik Nabers (WR, 6845) + Jaxson Dart (QB, 2162)** (w/ gdubs10) · likes-you | -4544 | 94% | — | — |  |  |
| 4 | Davante Adams (WR, 1121) + MarShawn Lloyd (RB, 277) + Baker Mayfield (QB, 829) → **Trevor Lawrence (QB, 2208) + James Conner (RB, 241)** (w/ jonbonjourvi) | +222 | 90% | value | 0.55 |  |  |
| 5 | Davante Adams (WR, 1121) + Darnell Mooney (WR, 259) → **Trevor Lawrence (QB, 2208)** (w/ jonbonjourvi) | +828 | 61% | value | 0.67 |  |  |

### @lofman — deck 33 cards · init 0.5 ms · gen 1032.5 ms · outlook `rebuilder`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Justin Fields (QB, 237) → **Malik Davis (RB, 229)** (w/ mattmurf77) · likes-you | -8 | 99% | — | — |  |  |
| 2 | Justin Fields (QB, 237) → **Jimmy Horn (WR, 228)** (w/ mattmurf77) · likes-you | -9 | 99% | — | — |  |  |
| 3 | Justin Fields (QB, 237) → **Audric Estime (RB, 228)** (w/ mattmurf77) · likes-you | -9 | 99% | — | — |  |  |
| 4 | Saquon Barkley (RB, 3208) + Harold Fannin (TE, 2606) → **De'Von Achane (RB, 5638)** (w/ mattmurf77) | -176 | 98% | value | 0.50 |  |  |
| 5 | Puka Nacua (WR, 7725) + Quinshon Judkins (RB, 3289) → **Drake Maye (QB, 5046) + Ashton Jeanty (RB, 7400)** (w/ mattmurf77) | +1432 | 88% | value | 0.53 |  |  |

### @Shark357 — deck 36 cards · init 0.7 ms · gen 1230.8 ms · outlook `rebuilder`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | David Montgomery (RB, 1083) → **Davante Adams (WR, 1121)** (w/ mattmurf77) · likes-you | +38 | 100% | — | — |  |  |
| 2 | David Montgomery (RB, 1083) → **Baker Mayfield (QB, 829)** (w/ mattmurf77) · likes-you | -254 | 96% | — | — |  |  |
| 3 | George Pickens (WR, 4749) + DJ Moore (WR, 1763) → **De'Von Achane (RB, 5638)** (w/ mattmurf77) | -874 | 89% | value | 0.58 |  |  |
| 4 | Tre' Harris (WR, 504) + DJ Moore (WR, 1763) + George Pickens (WR, 4749) → **Jayden Daniels (QB, 4009) + Marvin Harrison (WR, 3297)** (w/ jonbonjourvi) | +290 | 93% | value | 0.65 |  |  |
| 5 | Jakobi Meyers (WR, 748) + DJ Moore (WR, 1763) + David Montgomery (RB, 1083) → **Marvin Harrison (WR, 3297) + Cam Ward (QB, 964)** (w/ jonbonjourvi) | +667 | 84% | window | 0.57 |  |  |

### @MangoPatti — deck 33 cards · init 1.0 ms · gen 1074.1 ms · outlook `contender`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Justice Hill (RB, 229) → **Brevin Jordan (TE, 225)** (w/ mattmurf77) · likes-you | -4 | 100% | — | — |  |  |
| 2 | Josh Allen (QB, 6421) → **Jaxon Smith-Njigba (WR, 8073)** (w/ mattmurf77) · likes-you | +1652 | 98% | — | — |  |  |
| 3 | A.J. Brown (WR, 4168) + James Cook (RB, 5677) + CeeDee Lamb (WR, 6862) → **Jaxon Smith-Njigba (WR, 8073) + Devin Singletary (RB, 228) + Malik Davis (RB, 229)** (w/ mattmurf77) · likes-you | -8177 | 78% | — | — |  |  |
| 4 | Mike Evans (WR, 936) + Quentin Johnston (WR, 1052) + Parker Washington (WR, 1614) → **Jayden Daniels (QB, 4009) + James Conner (RB, 241)** (w/ jonbonjourvi) | +648 | 83% | value | 0.78 |  |  |
| 5 | Jalen McMillan (WR, 524) + Quentin Johnston (WR, 1052) + Parker Washington (WR, 1614) → **Trevor Lawrence (QB, 2208) + Marvin Harrison (WR, 3297)** (w/ jonbonjourvi) | +2315 | 57% | value | 0.70 |  |  |

### @Bcork — deck 33 cards · init 0.6 ms · gen 1015.3 ms · outlook `rebuilder`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Dont'e Thornton (WR, 240) → **Devin Singletary (RB, 228)** (w/ mattmurf77) · likes-you | -12 | 99% | — | — |  |  |
| 2 | TreVeyon Henderson (RB, 3384) → **Trey McBride (TE, 5376)** (w/ mattmurf77) · likes-you | +1992 | 95% | — | — |  |  |
| 3 | TreVeyon Henderson (RB, 3384) → **Jaxon Smith-Njigba (WR, 8073)** (w/ mattmurf77) · likes-you | +4689 | 91% | — | — |  |  |
| 4 | Ladd McConkey (WR, 4371) → **Drake Maye (QB, 5046)** (w/ mattmurf77) | +675 | 87% | value | 0.81 |  |  |
| 5 | Rome Odunze (WR, 3655) → **Drake Maye (QB, 5046)** (w/ mattmurf77) | +1391 | 72% | value | 0.81 |  |  |

### @jonbonjourvi — deck 33 cards · init 1.0 ms · gen 1013.2 ms · outlook `rebuilder`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | RJ Harvey (RB, 982) → **Brenton Strange (TE, 703)** (w/ mattmurf77) · likes-you | -279 | 96% | — | — |  |  |
| 2 | Trevor Lawrence (QB, 2208) + Bijan Robinson (RB, 8390) → **Ladd McConkey (WR, 4371) + Rome Odunze (WR, 3655) + TreVeyon Henderson (RB, 3384)** (w/ Bcork) | +812 | 97% | value | 0.75 |  |  |
| 3 | RJ Harvey (RB, 982) + Trevor Lawrence (QB, 2208) + Marvin Harrison (WR, 3297) → **TreVeyon Henderson (RB, 3384) + Jayden Higgins (WR, 1175) + Matthew Golden (WR, 1117)** (w/ Bcork) | -811 | 86% | value | 0.65 |  |  |
| 4 | Trevor Lawrence (QB, 2208) + Isaiah Likely (TE, 1131) + Jayden Daniels (QB, 4009) → **Javonte Williams (RB, 2245) + Derrick Henry (RB, 1731) + Tee Higgins (WR, 3332)** (w/ gdubs10) | -40 | 100% | value | 0.56 |  |  |
| 5 | Marvin Harrison (WR, 3297) + Jayden Daniels (QB, 4009) → **Ladd McConkey (WR, 4371) + Jayden Higgins (WR, 1175) + Matthew Golden (WR, 1117)** (w/ Bcork) | -643 | 88% | value | 0.75 |  |  |

### @PaulSm3nis — deck 33 cards · init 0.6 ms · gen 743.6 ms · outlook `contender`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Aaron Rodgers (QB, 246) → **Jimmy Horn (WR, 228)** (w/ mattmurf77) · likes-you | -18 | 99% | — | — |  |  |
| 2 | Aaron Rodgers (QB, 246) → **Audric Estime (RB, 228)** (w/ mattmurf77) · likes-you | -18 | 99% | — | — |  |  |
| 3 | Rhamondre Stevenson (RB, 675) → **Baker Mayfield (QB, 829)** (w/ mattmurf77) · likes-you | +154 | 97% | — | — |  |  |
| 4 | Terry McLaurin (WR, 1513) + Tre Tucker (WR, 312) + Bryce Young (QB, 504) → **Trevor Lawrence (QB, 2208) + Isaiah Likely (TE, 1131) + Cam Ward (QB, 964)** (w/ jonbonjourvi) | +1974 | 54% | value | 0.54 |  |  |
| 5 | Terry McLaurin (WR, 1513) + Tyler Lockett (WR, 224) + John Metchie (WR, 227) → **RJ Harvey (RB, 982) + Trevor Lawrence (QB, 2208) + James Conner (RB, 241)** (w/ jonbonjourvi) | +1467 | 57% | value | 0.60 |  |  |

### @bsharp3 — deck 34 cards · init 0.6 ms · gen 1324.3 ms · outlook `not_sure`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Jordan Love (QB, 1241) → **Davante Adams (WR, 1121)** (w/ mattmurf77) · likes-you | -120 | 99% | — | — |  |  |
| 2 | Jordan Love (QB, 1241) → **Davante Adams (WR, 1121) + Baker Mayfield (QB, 829)** (w/ mattmurf77) · likes-you | +709 | 52% | — | — |  |  |
| 3 | Jordan Love (QB, 1241) → **Davante Adams (WR, 1121) + Kimani Vidal (RB, 277)** (w/ mattmurf77) · likes-you | +157 | 56% | — | — |  |  |
| 4 | Courtland Sutton (WR, 840) + Christian Watson (WR, 1881) + Jordan Love (QB, 1241) → **Jayden Daniels (QB, 4009) + James Conner (RB, 241)** (w/ jonbonjourvi) | +288 | 91% | — | 0.65 |  |  |
| 5 | Wan'Dale Robinson (WR, 1123) + Christian Watson (WR, 1881) + Jordan Love (QB, 1241) → **RJ Harvey (RB, 982) + Marvin Harrison (WR, 3297)** (w/ jonbonjourvi) | +34 | 99% | — | 0.57 |  |  |

### @gdubs10 — deck 32 cards · init 1.1 ms · gen 1010.2 ms · outlook `rebuilder`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Malik Nabers (WR, 6845) + Jaxson Dart (QB, 2162) → **Ashton Jeanty (RB, 7400)** (w/ mattmurf77) · likes-you | -1607 | 54% | — | — |  |  |
| 2 | Malik Nabers (WR, 6845) + Jordan Addison (WR, 1510) + Malik Willis (QB, 543) → **Malik Davis (RB, 229) + Rasheen Ali (RB, 225) + Ashton Jeanty (RB, 7400)** (w/ mattmurf77) · likes-you | -1044 | 89% | — | — |  |  |
| 3 | Jaylen Waddle (WR, 3529) + Zach Charbonnet (RB, 830) + Malik Nabers (WR, 6845) → **Jahmyr Gibbs (RB, 7913) + Malik Davis (RB, 229) + Audric Estime (RB, 228)** (w/ mattmurf77) · likes-you | -2834 | 85% | — | — |  |  |
| 4 | Malik Nabers (WR, 6845) → **Ashton Jeanty (RB, 7400)** (w/ mattmurf77) | +555 | 92% | value | 0.56 |  |  |
| 5 | Malik Nabers (WR, 6845) → **Jahmyr Gibbs (RB, 7913)** (w/ mattmurf77) | +1068 | 86% | value | 0.56 |  |  |

### @JohnStanfield — deck 30 cards · init 0.8 ms · gen 932.4 ms · outlook `rebuilder`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Jalen Milroe (QB, 239) → **Isaac Guerendo (RB, 228)** (w/ mattmurf77) · likes-you | -11 | 99% | — | — |  |  |
| 2 | Tyler Shough (QB, 804) → **Brenton Strange (TE, 703)** (w/ mattmurf77) · likes-you | -101 | 98% | — | — |  |  |
| 3 | Jalen Milroe (QB, 239) → **Jaleel McLaughlin (RB, 226)** (w/ mattmurf77) · likes-you | -13 | 99% | — | — |  |  |
| 4 | Tetairoa McMillan (WR, 5706) + Brock Bowers (TE, 6392) + Luther Burden (WR, 4078) → **Jahmyr Gibbs (RB, 7913) + Ashton Jeanty (RB, 7400)** (w/ mattmurf77) | -863 | 100% | value | 0.75 |  |  |
| 5 | Xavier Worthy (WR, 916) + Jerry Jeudy (WR, 348) + Tory Horton (WR, 323) → **Trevor Lawrence (QB, 2208) + Cam Ward (QB, 964)** (w/ jonbonjourvi) | +1585 | 49% | value | 0.72 |  |  |

### @dondags20 — deck 33 cards · init 0.7 ms · gen 1441.7 ms · outlook `contender`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Kyle Monangai (RB, 968) → **Baker Mayfield (QB, 829)** (w/ mattmurf77) · likes-you | -139 | 98% | — | — |  |  |
| 2 | Kyle Monangai (RB, 968) → **Travis Kelce (TE, 388)** (w/ mattmurf77) · likes-you | -580 | 88% | — | — |  |  |
| 3 | Bhayshul Tuten (RB, 1704) → **Davante Adams (WR, 1121)** (w/ mattmurf77) · likes-you | -583 | 95% | — | — |  |  |
| 4 | DK Metcalf (WR, 1586) + Alec Pierce (WR, 1666) + Jalen Nailor (WR, 323) → **Marvin Harrison (WR, 3297) + James Conner (RB, 241)** (w/ jonbonjourvi) | -37 | 99% | value | 0.65 |  |  |
| 5 | Michael Pittman (WR, 1331) + DK Metcalf (WR, 1586) + Alec Pierce (WR, 1666) → **Jayden Daniels (QB, 4009) + Cam Ward (QB, 964)** (w/ jonbonjourvi) | +390 | 94% | value | 0.72 |  |  |

### @KevinLake — deck 31 cards · init 0.8 ms · gen 897.4 ms · outlook `rebuilder`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | C.J. Stroud (QB, 1158) → **Davante Adams (WR, 1121) + Raheim Sanders (RB, 225)** (w/ mattmurf77) · likes-you | +188 | 56% | — | — |  |  |
| 2 | Justin Jefferson (WR, 7008) → **Ashton Jeanty (RB, 7400)** (w/ mattmurf77) | +392 | 95% | window | 0.56 |  |  |
| 3 | Nico Collins (WR, 4870) → **Drake Maye (QB, 5046)** (w/ mattmurf77) | +176 | 96% | window | 0.56 |  |  |
| 4 | Jayden Reed (WR, 951) + Michael Wilson (WR, 1353) → **Colston Loveland (TE, 4545)** (w/ jonbonjourvi) | +2241 | 50% | window | 0.75 |  |  |
| 5 | Nico Collins (WR, 4870) + Garrett Wilson (WR, 4978) + Cam Skattebo (RB, 2393) → **Drake Maye (QB, 5046) + Ashton Jeanty (RB, 7400)** (w/ mattmurf77) | +205 | 94% | window | 0.55 |  |  |

## La Resistance (`1312146456701829120`) — 12 teams, format `1qb_ppr`, fetch 505.2 ms

### @bkey5 — deck 29 cards · init 0.9 ms · gen 643.3 ms · outlook `rebuilder`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Kyle Pitts (TE, 2219) + Derrick Henry (RB, 1731) → **Drake Maye (QB, 5046)** (w/ mattmurf77) | +1096 | 77% | value | 0.58 |  |  |
| 2 | Oronde Gadsden (TE, 1046) + Jayden Reed (WR, 951) + Kyle Pitts (TE, 2219) → **Makai Lemon (WR, 3179) + TreVeyon Henderson (RB, 3384)** (w/ mattmurf77) | +2347 | 62% | value | 0.60 |  |  |
| 3 | Oronde Gadsden (TE, 1046) + Jayden Reed (WR, 951) + Elijah Arroyo (TE, 296) → **Makai Lemon (WR, 3179) + Tyler Shough (QB, 804) + Tory Horton (WR, 323)** (w/ mattmurf77) | +2013 | 54% | value | 0.54 |  |  |
| 4 | Oronde Gadsden (TE, 1046) + Michael Wilson (WR, 1353) + Derrick Henry (RB, 1731) → **Drake Maye (QB, 5046) + Makai Lemon (WR, 3179)** (w/ mattmurf77) | +4095 | 50% | value | 0.55 |  |  |
| 5 | Oronde Gadsden (TE, 1046) + Elijah Arroyo (TE, 296) + Kyle Pitts (TE, 2219) → **TreVeyon Henderson (RB, 3384) + Tory Horton (WR, 323) + Eli Raridon (TE, 289)** (w/ mattmurf77) | +435 | 88% | value | 0.54 |  |  |

### @cwoods93 — deck 30 cards · init 0.5 ms · gen 890.8 ms · outlook `rebuilder`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Isaiah Likely (TE, 1131) + Jadarian Price (RB, 2559) → **Carnell Tate (WR, 4802)** (w/ mattmurf77) | +1112 | 74% | value | 0.58 |  |  |
| 2 | Chris Bell (WR, 537) + Jadarian Price (RB, 2559) → **Drake Maye (QB, 5046)** (w/ mattmurf77) | +1950 | 60% | value | 0.50 |  |  |
| 3 | Keenan Allen (WR, 232) + Jadarian Price (RB, 2559) + Theo Johnson (TE, 257) → **Makai Lemon (WR, 3179) + Tyler Shough (QB, 804) + Tory Horton (WR, 323)** (w/ mattmurf77) | +1258 | 72% | value | 0.54 |  |  |
| 4 | Chris Bell (WR, 537) + Isaiah Likely (TE, 1131) + Jadarian Price (RB, 2559) → **Makai Lemon (WR, 3179) + TreVeyon Henderson (RB, 3384)** (w/ mattmurf77) | +2336 | 62% | value | 0.55 |  |  |
| 5 | Isaiah Likely (TE, 1131) + Rashid Shaheed (WR, 518) + Jalen McMillan (WR, 524) → **Makai Lemon (WR, 3179) + Eli Raridon (TE, 289)** (w/ mattmurf77) | +1295 | 61% | window | 0.50 |  |  |

### @twilson2320 — deck 30 cards · init 0.6 ms · gen 758.1 ms · outlook `contender`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Tyjae Spears (RB, 331) + Eli Stowers (TE, 1067) + Jake Ferguson (TE, 781) → **Makai Lemon (WR, 3179) + Tyler Shough (QB, 804) + Tory Horton (WR, 323)** (w/ mattmurf77) | +2127 | 51% | value | 0.50 |  |  |
| 2 | Rhamondre Stevenson (RB, 675) + Zachariah Branch (WR, 446) + David Montgomery (RB, 1083) → **TreVeyon Henderson (RB, 3384) + Tory Horton (WR, 323) + Eli Raridon (TE, 289)** (w/ mattmurf77) | +1792 | 55% | value | 0.46 |  |  |
| 3 | Eli Stowers (TE, 1067) + David Montgomery (RB, 1083) + Jake Ferguson (TE, 781) → **TreVeyon Henderson (RB, 3384) + Eli Raridon (TE, 289)** (w/ mattmurf77) | +742 | 80% | value | 0.55 |  |  |
| 4 | Rhamondre Stevenson (RB, 675) + Eli Stowers (TE, 1067) + Terry McLaurin (WR, 1513) → **TreVeyon Henderson (RB, 3384) + Tory Horton (WR, 323)** (w/ mattmurf77) | +452 | 86% | value | 0.55 |  |  |
| 5 | Eli Stowers (TE, 1067) + Terry McLaurin (WR, 1513) → **Drake Maye (QB, 5046)** (w/ mattmurf77) | +2466 | 50% | value | 0.67 |  |  |

### @JareBear28 — deck 30 cards · init 0.7 ms · gen 849.3 ms · outlook `contender`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | T.J. Hockenson (TE, 384) + George Kittle (TE, 930) + Quentin Johnston (WR, 1052) → **TreVeyon Henderson (RB, 3384) + Eli Raridon (TE, 289)** (w/ mattmurf77) | +1307 | 64% | value | 0.65 |  |  |
| 2 | Quentin Johnston (WR, 1052) + LeQuint Allen (RB, 247) + Jared Goff (QB, 867) → **Makai Lemon (WR, 3179) + Eli Raridon (TE, 289)** (w/ mattmurf77) | +1302 | 62% | value | 0.40 |  |  |
| 3 | Luther Burden (WR, 4078) → **Breece Hall (RB, 4575)** (w/ bkey5) | +497 | 89% | window | 0.62 |  |  |
| 4 | T.J. Hockenson (TE, 384) + Quentin Johnston (WR, 1052) + Jared Goff (QB, 867) → **Makai Lemon (WR, 3179) + Tyler Shough (QB, 804) + Tory Horton (WR, 323)** (w/ mattmurf77) | +2003 | 54% | value | 0.50 |  |  |
| 5 | Luther Burden (WR, 4078) → **Nico Collins (WR, 4870)** (w/ twilson2320) | +792 | 84% | window | 0.50 |  |  |

### @yaboyboston — deck 28 cards · init 0.6 ms · gen 936.5 ms · outlook `rebuilder`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Alec Pierce (WR, 1666) + J.K. Dobbins (RB, 532) + Dalton Kincaid (TE, 1324) → **Makai Lemon (WR, 3179) + Eli Raridon (TE, 289)** (w/ mattmurf77) | -54 | 100% | window | 0.50 |  |  |
| 2 | Romeo Doubs (WR, 633) + Keon Coleman (WR, 292) + Dalton Kincaid (TE, 1324) → **Makai Lemon (WR, 3179) + Tyler Shough (QB, 804)** (w/ mattmurf77) | +1734 | 56% | window | 0.65 |  |  |
| 3 | Romeo Doubs (WR, 633) + Dalton Schultz (TE, 290) + Alec Pierce (WR, 1666) → **Makai Lemon (WR, 3179) + Tory Horton (WR, 323)** (w/ mattmurf77) | +913 | 72% | window | 0.55 |  |  |
| 4 | Christian McCaffrey (RB, 3796) → **Luther Burden (WR, 4078)** (w/ JareBear28) | +282 | 93% | window | 0.62 |  |  |
| 5 | Christian McCaffrey (RB, 3796) → **Jayden Daniels (QB, 4009)** (w/ MChammer45) | +213 | 95% | window | 0.62 |  |  |

### @mattmurf77 — deck 30 cards · init 0.6 ms · gen 26.6 ms · outlook `rebuilder`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Drake Maye (QB, 5046) → **Tetairoa McMillan (WR, 5706)** (w/ yaboyboston) | +660 | 88% | value | 0.75 |  |  |
| 2 | TreVeyon Henderson (RB, 3384) → **Luther Burden (WR, 4078)** (w/ JareBear28) | +694 | 83% | value | 0.75 |  |  |
| 3 | TreVeyon Henderson (RB, 3384) → **Tyler Warren (TE, 4071)** (w/ MChammer45) | +687 | 83% | value | 0.62 |  |  |
| 4 | Makai Lemon (WR, 3179) → **Luther Burden (WR, 4078)** (w/ JareBear28) | +899 | 78% | value | 0.50 |  |  |
| 5 | Jonathon Brooks (RB, 1164) → **Jayden Higgins (WR, 1175)** (w/ cwoods93) | +11 | 99% | value | 0.50 |  |  |

### @MChammer45 — deck 30 cards · init 0.9 ms · gen 751.9 ms · outlook `rebuilder`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Kenyon Sadiq (TE, 1682) + Marvin Harrison (WR, 3297) → **Carnell Tate (WR, 4802)** (w/ mattmurf77) | -177 | 99% | value | 0.58 |  |  |
| 2 | Kenyon Sadiq (TE, 1682) + Jaylin Noel (WR, 394) + Kyren Williams (RB, 2930) → **Makai Lemon (WR, 3179) + TreVeyon Henderson (RB, 3384) + Eli Raridon (TE, 289)** (w/ mattmurf77) | +1846 | 71% | value | 0.50 |  |  |
| 3 | Jaylin Noel (WR, 394) + Kyren Williams (RB, 2930) + Marvin Harrison (WR, 3297) → **Carnell Tate (WR, 4802) + Makai Lemon (WR, 3179)** (w/ mattmurf77) | +1360 | 83% | window | 0.50 |  |  |
| 4 | Kenyon Sadiq (TE, 1682) + Jaylin Noel (WR, 394) + Tyreek Hill (WR, 377) → **Makai Lemon (WR, 3179) + Tory Horton (WR, 323)** (w/ mattmurf77) | +1049 | 68% | value | 0.55 |  |  |
| 5 | Deebo Samuel (WR, 342) + Kenyon Sadiq (TE, 1682) + Marvin Harrison (WR, 3297) → **Makai Lemon (WR, 3179) + TreVeyon Henderson (RB, 3384)** (w/ mattmurf77) | +1242 | 78% | value | 0.60 |  |  |

### @dubbasparks — deck 29 cards · init 0.5 ms · gen 843.2 ms · outlook `rebuilder`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | D'Andre Swift (RB, 1521) + Jakobi Meyers (WR, 748) + DJ Moore (WR, 1763) → **Makai Lemon (WR, 3179) + Tyler Shough (QB, 804) + Eli Raridon (TE, 289)** (w/ mattmurf77) | +240 | 96% | window | 0.50 |  |  |
| 2 | D'Andre Swift (RB, 1521) + Tank Dell (WR, 456) + Michael Pittman (WR, 1331) → **Makai Lemon (WR, 3179) + Tyler Shough (QB, 804) + Tory Horton (WR, 323)** (w/ mattmurf77) | +998 | 78% | window | 0.50 |  |  |
| 3 | Isaiah Bond (WR, 248) + D'Andre Swift (RB, 1521) + DJ Moore (WR, 1763) → **Makai Lemon (WR, 3179) + Tory Horton (WR, 323)** (w/ mattmurf77) | -30 | 100% | window | 0.50 |  |  |
| 4 | Cam Skattebo (RB, 2393) + DJ Moore (WR, 1763) → **Carnell Tate (WR, 4802)** (w/ mattmurf77) | +646 | 85% | window | 0.50 |  |  |
| 5 | Josh Allen (QB, 6421) → **Jeremiyah Love (RB, 6966)** (w/ cwoods93) | +545 | 92% | window | 0.50 |  |  |

### @DerseyShore — deck 28 cards · init 0.5 ms · gen 813.4 ms · outlook `rebuilder`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | AJ Barner (TE, 443) + Matthew Golden (WR, 1117) + Davante Adams (WR, 1121) → **Makai Lemon (WR, 3179) + Tyler Shough (QB, 804) + Eli Raridon (TE, 289)** (w/ mattmurf77) | +1591 | 64% | value | 0.54 |  |  |
| 2 | Germie Bernard (WR, 472) + Matthew Golden (WR, 1117) + Jordan Addison (WR, 1510) → **Makai Lemon (WR, 3179) + Tory Horton (WR, 323) + Eli Raridon (TE, 289)** (w/ mattmurf77) | +692 | 82% | value | 0.50 |  |  |
| 3 | Terrance Ferguson (TE, 496) + Matthew Golden (WR, 1117) + Jordan Addison (WR, 1510) → **Makai Lemon (WR, 3179) + Tyler Shough (QB, 804)** (w/ mattmurf77) | +860 | 78% | value | 0.60 |  |  |
| 4 | Lamar Jackson (QB, 4453) → **Colston Loveland (TE, 4545)** (w/ yaboyboston) | +92 | 98% | window | 0.62 |  |  |
| 5 | De'Von Achane (RB, 5638) → **Tetairoa McMillan (WR, 5706)** (w/ yaboyboston) | +68 | 99% | value | 0.44 |  |  |

### @treyj19 — deck 30 cards · init 0.5 ms · gen 911.6 ms · outlook `contender`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Josh Jacobs (RB, 1619) + Bhayshul Tuten (RB, 1704) → **Drake Maye (QB, 5046)** (w/ mattmurf77) | +1723 | 66% | value | 0.50 |  |  |
| 2 | Elijah Sarratt (WR, 386) + Josh Jacobs (RB, 1619) + Bhayshul Tuten (RB, 1704) → **TreVeyon Henderson (RB, 3384) + Tory Horton (WR, 323)** (w/ mattmurf77) | -2 | 100% | value | 0.50 |  |  |
| 3 | Brenton Strange (TE, 703) + Josh Jacobs (RB, 1619) + David Njoku (TE, 280) → **TreVeyon Henderson (RB, 3384) + Tory Horton (WR, 323) + Eli Raridon (TE, 289)** (w/ mattmurf77) | +1394 | 64% | value | 0.50 |  |  |
| 4 | Josh Jacobs (RB, 1619) + Bhayshul Tuten (RB, 1704) + Efton Chism (WR, 225) → **Makai Lemon (WR, 3179) + TreVeyon Henderson (RB, 3384) + Eli Raridon (TE, 289)** (w/ mattmurf77) | +3304 | 52% | value | 0.46 |  |  |
| 5 | Brenton Strange (TE, 703) + Josh Jacobs (RB, 1619) + Bhayshul Tuten (RB, 1704) → **Carnell Tate (WR, 4802) + Makai Lemon (WR, 3179)** (w/ mattmurf77) | +3955 | 50% | value | 0.45 |  |  |

### @hhardy23 — deck 29 cards · init 0.6 ms · gen 792.5 ms · outlook `rebuilder`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Dallas Goedert (TE, 469) + CJ Daniels (WR, 227) + Quinshon Judkins (RB, 3289) → **Makai Lemon (WR, 3179) + Tyler Shough (QB, 804)** (w/ mattmurf77) | -2 | 100% | value | 0.55 |  |  |
| 2 | Travis Hunter (WR, 798) + Ty Johnson (RB, 227) + Quinshon Judkins (RB, 3289) → **Makai Lemon (WR, 3179) + Tyler Shough (QB, 804) + Tory Horton (WR, 323)** (w/ mattmurf77) | -8 | 100% | value | 0.46 |  |  |
| 3 | Dallas Goedert (TE, 469) + Christian Watson (WR, 1881) + Josh Downs (WR, 1242) → **Makai Lemon (WR, 3179) + Eli Raridon (TE, 289)** (w/ mattmurf77) | -124 | 99% | window | 0.55 |  |  |
| 4 | Christian Watson (WR, 1881) + Quinshon Judkins (RB, 3289) → **Drake Maye (QB, 5046)** (w/ mattmurf77) | -124 | 100% | value | 0.58 |  |  |
| 5 | Malik Nabers (WR, 6845) → **Jeremiyah Love (RB, 6966)** (w/ cwoods93) | +121 | 98% | value | 0.62 |  |  |

### @Bcork — deck 30 cards · init 0.8 ms · gen 394.7 ms · outlook `rebuilder`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Harold Fannin (TE, 2606) + Saquon Barkley (RB, 3208) + Jameson Williams (WR, 2683) → **Drake Maye (QB, 5046) + TreVeyon Henderson (RB, 3384)** (w/ mattmurf77) | -67 | 99% | value | 0.60 |  |  |
| 2 | Blake Corum (RB, 922) + Harold Fannin (TE, 2606) + Rome Odunze (WR, 3655) → **Carnell Tate (WR, 4802) + TreVeyon Henderson (RB, 3384)** (w/ mattmurf77) | +1003 | 86% | value | 0.55 |  |  |
| 3 | Saquon Barkley (RB, 3208) + Wan'Dale Robinson (WR, 1123) + Rome Odunze (WR, 3655) → **Carnell Tate (WR, 4802) + Makai Lemon (WR, 3179)** (w/ mattmurf77) | -5 | 100% | window | 0.50 |  |  |
| 4 | Harold Fannin (TE, 2606) + Jameson Williams (WR, 2683) → **Carnell Tate (WR, 4802)** (w/ mattmurf77) | -487 | 91% | value | 0.58 |  |  |
| 5 | Blake Corum (RB, 922) + Rome Odunze (WR, 3655) → **Drake Maye (QB, 5046)** (w/ mattmurf77) | +469 | 88% | value | 0.58 |  |  |

## SFO (`1312583962966650880`) — 12 teams, format `sf_tep`, fetch 1301.4 ms

### @jonbonjourvi — deck 27 cards · init 1.3 ms · gen 267.6 ms · outlook `rebuilder`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | De'Von Achane (RB, 4723) + Malik Willis (QB, 1256) → **Tyler Warren (TE, 4455) + Javonte Williams (RB, 1661)** (w/ lofman) | +137 | 98% | value | 0.54 |  |  |
| 2 | De'Von Achane (RB, 4723) → **Tyler Warren (TE, 4455) + Jordyn Tyson (WR, 2872)** (w/ lofman) | +2604 | 66% | value | 0.50 |  |  |
| 3 | Ladd McConkey (WR, 3651) + Malik Willis (QB, 1256) → **Tyler Warren (TE, 4455)** (w/ lofman) | -452 | 94% | value | 0.56 |  |  |
| 4 | Jalen Hurts (QB, 5568) → **Jeremiyah Love (RB, 5972)** (w/ icecreamboiii) | +404 | 93% | window | 0.46 |  |  |
| 5 | Jalen Hurts (QB, 5568) → **Malik Nabers (WR, 5977)** (w/ icecreamboiii) | +409 | 93% | window | 0.58 |  |  |

### @lofman — deck 31 cards · init 0.6 ms · gen 165.9 ms · outlook `rebuilder`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Chase Brown (RB, 3206) → **Zay Flowers (WR, 3237)** (w/ nhamill4) | +31 | 99% | window | 0.50 |  |  |
| 2 | Bo Nix (QB, 4904) → **Jaxson Dart (QB, 5013)** (w/ icecreamboiii) | +109 | 98% | value | 0.50 |  |  |
| 3 | Bo Nix (QB, 4904) → **Trevor Lawrence (QB, 5137)** (w/ TheRealSugarDaddy247) | +233 | 96% | value | 0.50 |  |  |
| 4 | Bo Nix (QB, 4904) → **Drake London (WR, 5168)** (w/ icecreamboiii) | +264 | 95% | value | 0.50 |  |  |
| 5 | Javonte Williams (RB, 1661) → **Kenyon Sadiq (TE, 1699)** (w/ JanC) | +38 | 98% | window | 0.50 |  |  |

### @ksculls — deck 33 cards · init 0.6 ms · gen 310.5 ms · outlook `contender`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Braelon Allen (RB, 318) → **Troy Franklin (WR, 328)** (w/ lofman) · likes-you | +10 | 100% | — | — |  |  |
| 2 | Jakobi Meyers (WR, 622) → **Rico Dowdle (RB, 556)** (w/ lofman) · likes-you | -66 | 98% | — | — |  |  |
| 3 | Quinshon Judkins (RB, 2631) → **Chase Brown (RB, 3206)** (w/ lofman) · likes-you | +575 | 82% | window | 0.50 |  |  |
| 4 | CeeDee Lamb (WR, 6153) → **Tyler Warren (TE, 4455) + Chase Brown (RB, 3206)** (w/ lofman) | +1508 | 85% | value | 0.58 |  |  |
| 5 | CeeDee Lamb (WR, 6153) → **Harold Fannin (TE, 3160) + De'Von Achane (RB, 4723)** (w/ jonbonjourvi) | +1730 | 83% | value | 0.58 |  |  |

### @icecreamboiii — deck 30 cards · init 0.6 ms · gen 429.7 ms · outlook `rebuilder`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Adonai Mitchell (WR, 357) → **Troy Franklin (WR, 328)** (w/ lofman) · likes-you | -29 | 99% | — | — |  |  |
| 2 | Luther Burden (WR, 3282) → **Chase Brown (RB, 3206)** (w/ lofman) · likes-you | -76 | 100% | — | — |  |  |
| 3 | Luther Burden (WR, 3282) → **Jordyn Tyson (WR, 2872)** (w/ lofman) · likes-you | -410 | 98% | — | — |  |  |
| 4 | Drake London (WR, 5168) + Malik Nabers (WR, 5977) → **Harold Fannin (TE, 3160) + De'Von Achane (RB, 4723) + A.J. Brown (WR, 3325)** (w/ jonbonjourvi) | +63 | 98% | value | 0.55 |  |  |
| 5 | Alec Pierce (WR, 1257) + Bryce Young (QB, 1154) → **Javonte Williams (RB, 1661) + Jayden Higgins (WR, 930)** (w/ lofman) | +180 | 95% | value | 0.56 |  |  |

### @Eastwood123 — deck 31 cards · init 0.5 ms · gen 388.0 ms · outlook `contender`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | KC Concepcion (WR, 1521) → **Christian Watson (WR, 1510)** (w/ jonbonjourvi) · likes-you | -11 | 100% | — | — |  |  |
| 2 | Rashid Shaheed (WR, 450) → **Max Klare (TE, 339)** (w/ lofman) · likes-you | -111 | 96% | — | — |  |  |
| 3 | Ricky Pearsall (WR, 529) → **Jayden Higgins (WR, 930)** (w/ lofman) · likes-you | +401 | 92% | — | — |  |  |
| 4 | Jonathan Taylor (RB, 4341) + Bucky Irving (RB, 1740) → **Tyler Warren (TE, 4455) + Javonte Williams (RB, 1661)** (w/ lofman) | +35 | 99% | value | 0.50 |  |  |
| 5 | Ricky Pearsall (WR, 529) + Bucky Irving (RB, 1740) + Breece Hall (RB, 3624) → **Chase Brown (RB, 3206) + Josh Downs (WR, 938) + Jordyn Tyson (WR, 2872)** (w/ lofman) | +1123 | 82% | value | 0.50 |  |  |

### @JanC — deck 36 cards · init 0.6 ms · gen 311.7 ms · outlook `not_sure`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Jordan Mason (RB, 402) → **Troy Franklin (WR, 328)** (w/ lofman) · likes-you | -74 | 97% | — | — |  |  |
| 2 | Michael Wilson (WR, 1020) → **Jayden Higgins (WR, 930)** (w/ lofman) · likes-you | -90 | 99% | — | — |  |  |
| 3 | D'Andre Swift (RB, 1042) → **Josh Downs (WR, 938)** (w/ lofman) · likes-you | -104 | 99% | — | — |  |  |
| 4 | Tyler Shough (QB, 2123) + Ty Simpson (QB, 871) + Xavier Worthy (WR, 751) → **Jayden Higgins (WR, 930) + Jordyn Tyson (WR, 2872)** (w/ lofman) | +57 | 97% | — | 0.57 |  |  |
| 5 | Tyler Shough (QB, 2123) → **Jordyn Tyson (WR, 2872)** (w/ lofman) | +749 | 74% | — | 0.58 |  |  |

### @nhamill4 — deck 32 cards · init 0.6 ms · gen 322.2 ms · outlook `rebuilder`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Stefon Diggs (WR, 435) → **Pat Bryant (WR, 369)** (w/ lofman) · likes-you | -66 | 98% | — | — |  |  |
| 2 | Stefon Diggs (WR, 435) → **Kaytron Allen (RB, 304)** (w/ lofman) · likes-you | -131 | 95% | — | — |  |  |
| 3 | Omar Cooper (WR, 892) → **Josh Downs (WR, 938)** (w/ lofman) · likes-you | +46 | 99% | — | — |  |  |
| 4 | RJ Harvey (RB, 795) → **Ty Simpson (QB, 871)** (w/ JanC) | +76 | 91% | window | 0.67 |  |  |
| 5 | Dallas Goedert (TE, 573) → **Anthony Richardson (QB, 575)** (w/ ksculls) | +2 | 100% | window | 0.71 |  |  |

### @TheRealSugarDaddy247 — deck 35 cards · init 0.6 ms · gen 276.6 ms · outlook `contender`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Tre' Harris (WR, 441) → **Max Klare (TE, 339)** (w/ lofman) · likes-you | -102 | 96% | — | — |  |  |
| 2 | Davante Adams (WR, 908) → **Jayden Higgins (WR, 930)** (w/ lofman) · likes-you | +22 | 100% | — | — |  |  |
| 3 | Saquon Barkley (RB, 2506) → **Brian Thomas (WR, 1999)** (w/ lofman) · likes-you | -507 | 97% | — | — |  |  |
| 4 | Trevor Lawrence (QB, 5137) → **Drake London (WR, 5168)** (w/ icecreamboiii) | +31 | 99% | value | 0.50 |  |  |
| 5 | Justin Herbert (QB, 6253) → **Trey McBride (TE, 6284)** (w/ Eastwood123) | +31 | 100% | value | 0.50 |  |  |

### @kysol — deck 26 cards · init 0.5 ms · gen 375.8 ms · outlook `not_sure`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Nico Collins (WR, 3965) + Garrett Wilson (WR, 3939) → **De'Von Achane (RB, 4723) + A.J. Brown (WR, 3325)** (w/ jonbonjourvi) | +144 | 100% | — | 0.50 |  |  |
| 2 | Nico Collins (WR, 3965) + Chris Olave (WR, 4098) → **Harold Fannin (TE, 3160) + De'Von Achane (RB, 4723)** (w/ jonbonjourvi) | -180 | 96% | — | 0.50 |  |  |
| 3 | Nico Collins (WR, 3965) → **Tyler Warren (TE, 4455)** (w/ lofman) | +490 | 89% | — | 0.50 |  |  |
| 4 | Garrett Wilson (WR, 3939) → **Tyler Warren (TE, 4455)** (w/ lofman) | +516 | 88% | — | 0.50 |  |  |
| 5 | Nico Collins (WR, 3965) → **Chase Brown (RB, 3206) + Jayden Higgins (WR, 930)** (w/ lofman) | +171 | 99% | — | 0.50 |  |  |

### @chardeemacdixon — deck 33 cards · init 0.5 ms · gen 354.8 ms · outlook `rebuilder`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Tucker Kraft (TE, 3510) + TreVeyon Henderson (RB, 2604) → **Tyler Warren (TE, 4455) + Jordyn Tyson (WR, 2872)** (w/ lofman) | +1213 | 84% | value | 0.50 |  |  |
| 2 | Tucker Kraft (TE, 3510) → **Chase Brown (RB, 3206) + Javonte Williams (RB, 1661)** (w/ lofman) | +1357 | 74% | value | 0.50 |  |  |
| 3 | Jared Goff (QB, 2705) → **Luther Burden (WR, 3282)** (w/ icecreamboiii) | +577 | 82% | window | 0.50 |  |  |
| 4 | Jared Goff (QB, 2705) → **Zay Flowers (WR, 3237)** (w/ nhamill4) | +532 | 84% | window | 0.58 |  |  |
| 5 | Amon-Ra St. Brown (WR, 6807) → **Bijan Robinson (RB, 7478)** (w/ nhamill4) | +671 | 91% | value | 0.50 |  |  |

### @SmilesD — deck 29 cards · init 0.5 ms · gen 602.5 ms · outlook `rebuilder`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Brock Purdy (QB, 4634) + Marvin Harrison (WR, 2643) + Travis Etienne (RB, 1840) → **Tyler Warren (TE, 4455) + Chase Brown (RB, 3206) + Javonte Williams (RB, 1661)** (w/ lofman) | +205 | 97% | value | 0.53 |  |  |
| 2 | Sam Darnold (QB, 1558) + Kyler Murray (QB, 2138) → **Tyler Warren (TE, 4455)** (w/ lofman) | +759 | 81% | value | 0.61 |  |  |
| 3 | Tetairoa McMillan (WR, 4611) → **De'Von Achane (RB, 4723)** (w/ jonbonjourvi) | +112 | 98% | value | 0.50 |  |  |
| 4 | Tetairoa McMillan (WR, 4611) + Carnell Tate (WR, 3840) → **Harold Fannin (TE, 3160) + De'Von Achane (RB, 4723) + Malik Willis (QB, 1256)** (w/ jonbonjourvi) | +688 | 95% | value | 0.50 |  |  |
| 5 | Brock Purdy (QB, 4634) + Sam Darnold (QB, 1558) + Cam Skattebo (RB, 1818) → **Tyler Warren (TE, 4455) + Chase Brown (RB, 3206)** (w/ lofman) | -349 | 99% | value | 0.57 |  |  |

### @obviouslygreen — deck 30 cards · init 0.8 ms · gen 361.1 ms · outlook `rebuilder`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Emeka Egbuka (WR, 4584) → **De'Von Achane (RB, 4723)** (w/ jonbonjourvi) | +139 | 97% | value | 0.56 |  |  |
| 2 | Caleb Williams (QB, 7085) → **De'Von Achane (RB, 4723) + A.J. Brown (WR, 3325)** (w/ jonbonjourvi) | +963 | 95% | value | 0.54 |  |  |
| 3 | Josh Allen (QB, 8281) → **Ja'Marr Chase (WR, 8470)** (w/ Eastwood123) | +189 | 98% | value | 0.58 |  |  |
| 4 | Tee Higgins (WR, 2744) → **Zay Flowers (WR, 3237)** (w/ nhamill4) | +493 | 85% | value | 0.50 |  |  |
| 5 | Emeka Egbuka (WR, 4584) → **Harold Fannin (TE, 3160) + A.J. Brown (WR, 3325)** (w/ jonbonjourvi) | +1901 | 71% | value | 0.50 |  |  |

## Bush League  (`1338231586314780672`) — 12 teams, format `1qb_ppr`, fetch 639.8 ms

### @dwasson17 — deck 29 cards · init 1.9 ms · gen 40.0 ms · outlook `not_sure`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Zay Flowers (WR, 3894) → **Jayden Daniels (QB, 4009)** (w/ ddragos7) | +115 | 97% | — | 0.69 |  |  |
| 2 | Tetairoa McMillan (WR, 5706) → **Omarion Hampton (RB, 5983)** (w/ gsteskal23) | +277 | 95% | — | 0.56 |  |  |
| 3 | Jonathan Taylor (RB, 5403) → **James Cook (RB, 5677)** (w/ xfactr27) | +274 | 95% | — | 0.50 |  |  |
| 4 | Zay Flowers (WR, 3894) → **A.J. Brown (WR, 4168)** (w/ ddragos7) | +274 | 93% | — | 0.50 |  |  |
| 5 | Josh Allen (QB, 6421) → **CeeDee Lamb (WR, 6862)** (w/ Dez07) | +441 | 94% | — | 0.38 |  |  |

### @ShanerBaner31 — deck 30 cards · init 0.8 ms · gen 29.5 ms · outlook `contender`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Marvin Harrison (WR, 3297) → **Tee Higgins (WR, 3332)** (w/ dwasson17) | +35 | 99% | window | 0.50 |  |  |
| 2 | Justin Herbert (QB, 2904) → **Kyren Williams (RB, 2930)** (w/ Bcork) | +26 | 99% | value | 0.62 |  |  |
| 3 | Bijan Robinson (RB, 8390) → **Ja'Marr Chase (WR, 8470)** (w/ xfactr27) | +80 | 99% | value | 0.50 |  |  |
| 4 | Marvin Harrison (WR, 3297) → **Caleb Williams (QB, 3382)** (w/ Dez07) | +85 | 98% | value | 0.50 |  |  |
| 5 | Justin Herbert (QB, 2904) → **Saquon Barkley (RB, 3208)** (w/ Bcork) | +304 | 90% | window | 0.62 |  |  |

### @Bcork — deck 30 cards · init 0.7 ms · gen 22.1 ms · outlook `contender`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Garrett Wilson (WR, 4978) → **Jonathan Taylor (RB, 5403)** (w/ dwasson17) | +425 | 92% | window | 0.38 |  |  |
| 2 | Garrett Wilson (WR, 4978) → **James Cook (RB, 5677)** (w/ xfactr27) | +699 | 88% | window | 0.44 |  |  |
| 3 | Garrett Wilson (WR, 4978) → **Chris Olave (WR, 4978)** (w/ gsteskal23) | +0 | 100% | value | 0.50 |  |  |
| 4 | Jalen Hurts (QB, 2853) → **Justin Herbert (QB, 2904)** (w/ ShanerBaner31) | +51 | 98% | value | 0.50 |  |  |
| 5 | Garrett Wilson (WR, 4978) → **Drake Maye (QB, 5046)** (w/ Dez07) | +68 | 99% | value | 0.56 |  |  |

### @Dez07 — deck 30 cards · init 0.7 ms · gen 13.8 ms · outlook `rebuilder`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Breece Hall (RB, 4575) → **Tetairoa McMillan (WR, 5706)** (w/ dwasson17) | +1131 | 80% | window | 0.56 |  |  |
| 2 | Breece Hall (RB, 4575) → **Omarion Hampton (RB, 5983)** (w/ gsteskal23) | +1408 | 76% | window | 0.50 |  |  |
| 3 | Breece Hall (RB, 4575) → **George Pickens (WR, 4749)** (w/ ddragos7) | +174 | 96% | value | 0.50 |  |  |
| 4 | Lamar Jackson (QB, 4453) → **George Pickens (WR, 4749)** (w/ ddragos7) | +296 | 94% | value | 0.44 |  |  |
| 5 | CeeDee Lamb (WR, 6862) → **Justin Jefferson (WR, 7008)** (w/ xfactr27) | +146 | 98% | value | 0.50 |  |  |

### @gsteskal23 — deck 30 cards · init 0.6 ms · gen 17.6 ms · outlook `rebuilder`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Chris Olave (WR, 4978) → **Drake Maye (QB, 5046)** (w/ Dez07) | +68 | 99% | value | 0.50 |  |  |
| 2 | Chris Olave (WR, 4978) → **Garrett Wilson (WR, 4978)** (w/ Bcork) | +0 | 100% | value | 0.50 |  |  |
| 3 | Chris Olave (WR, 4978) → **Emeka Egbuka (WR, 5387)** (w/ Dez07) | +409 | 92% | value | 0.50 |  |  |
| 4 | DeVonta Smith (WR, 4208) → **George Pickens (WR, 4749)** (w/ ddragos7) | +541 | 89% | value | 0.50 |  |  |
| 5 | Chris Olave (WR, 4978) → **Tetairoa McMillan (WR, 5706)** (w/ dwasson17) | +728 | 87% | value | 0.50 |  |  |

### @ddragos7 — deck 28 cards · init 0.7 ms · gen 16.7 ms · outlook `not_sure`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Rome Odunze (WR, 3655) → **Christian McCaffrey (RB, 3796)** (w/ xfactr27) | +141 | 96% | — | 0.50 |  |  |
| 2 | George Pickens (WR, 4749) → **Garrett Wilson (WR, 4978)** (w/ Bcork) | +229 | 95% | — | 0.50 |  |  |
| 3 | George Pickens (WR, 4749) → **Chris Olave (WR, 4978)** (w/ gsteskal23) | +229 | 95% | — | 0.50 |  |  |
| 4 | George Pickens (WR, 4749) → **Drake Maye (QB, 5046)** (w/ Dez07) | +297 | 94% | — | 0.44 |  |  |
| 5 | George Pickens (WR, 4749) → **Emeka Egbuka (WR, 5387)** (w/ Dez07) | +638 | 88% | — | 0.50 |  |  |

### @xfactr27 — deck 30 cards · init 0.5 ms · gen 19.8 ms · outlook `rebuilder`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | De'Von Achane (RB, 5638) → **Tetairoa McMillan (WR, 5706)** (w/ dwasson17) | +68 | 99% | value | 0.56 |  |  |
| 2 | De'Von Achane (RB, 5638) → **Omarion Hampton (RB, 5983)** (w/ gsteskal23) | +345 | 94% | value | 0.50 |  |  |
| 3 | Justin Jefferson (WR, 7008) → **Jahmyr Gibbs (RB, 7913)** (w/ Dez07) | +905 | 89% | value | 0.50 |  |  |
| 4 | Christian McCaffrey (RB, 3796) → **DeVonta Smith (WR, 4208)** (w/ gsteskal23) | +412 | 90% | value | 0.50 |  |  |
| 5 | Christian McCaffrey (RB, 3796) → **George Pickens (WR, 4749)** (w/ ddragos7) | +953 | 80% | value | 0.50 |  |  |

### @macbfarber — deck 30 cards · init 1.2 ms · gen 23.3 ms · outlook `contender`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Nico Collins (WR, 4870) → **Garrett Wilson (WR, 4978)** (w/ Bcork) | +108 | 98% | value | 0.50 |  |  |
| 2 | Nico Collins (WR, 4870) → **Chris Olave (WR, 4978)** (w/ gsteskal23) | +108 | 98% | value | 0.50 |  |  |
| 3 | Nico Collins (WR, 4870) → **Jonathan Taylor (RB, 5403)** (w/ dwasson17) | +533 | 90% | value | 0.44 |  |  |
| 4 | Nico Collins (WR, 4870) → **Drake Maye (QB, 5046)** (w/ Dez07) | +176 | 96% | value | 0.44 |  |  |
| 5 | Joe Burrow (QB, 3423) → **Chase Brown (RB, 3993)** (w/ ddragos7) | +570 | 86% | value | 0.50 |  |  |

### @zinkand — deck 30 cards · init 0.5 ms · gen 18.0 ms · outlook `rebuilder`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Jaylen Waddle (WR, 3529) → **Jayden Daniels (QB, 4009)** (w/ ddragos7) | +480 | 88% | window | 0.56 |  |  |
| 2 | Jaylen Waddle (WR, 3529) → **Colston Loveland (TE, 4545)** (w/ gsteskal23) | +1016 | 78% | window | 0.62 |  |  |
| 3 | Ladd McConkey (WR, 4371) → **Colston Loveland (TE, 4545)** (w/ gsteskal23) | +174 | 96% | value | 0.62 |  |  |
| 4 | Luther Burden (WR, 4078) → **Colston Loveland (TE, 4545)** (w/ gsteskal23) | +467 | 90% | value | 0.62 |  |  |
| 5 | Ladd McConkey (WR, 4371) → **Drake Maye (QB, 5046)** (w/ Dez07) | +675 | 87% | value | 0.50 |  |  |

### @nmoore9 — deck 30 cards · init 0.7 ms · gen 18.3 ms · outlook `rebuilder`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | DJ Moore (WR, 1763) → **Kyle Pitts (TE, 2219)** (w/ Bcork) | +456 | 80% | window | 0.56 |  |  |
| 2 | Rashee Rice (WR, 3212) → **Marvin Harrison (WR, 3297)** (w/ ShanerBaner31) | +85 | 97% | value | 0.50 |  |  |
| 3 | Drake London (WR, 5853) → **Omarion Hampton (RB, 5983)** (w/ gsteskal23) | +130 | 98% | value | 0.50 |  |  |
| 4 | Tyler Warren (TE, 4071) → **Colston Loveland (TE, 4545)** (w/ gsteskal23) | +474 | 90% | value | 0.50 |  |  |
| 5 | Rashee Rice (WR, 3212) → **Zay Flowers (WR, 3894)** (w/ dwasson17) | +682 | 82% | value | 0.50 |  |  |

### @chrisfarrell50 — deck 30 cards · init 0.5 ms · gen 19.8 ms · outlook `rebuilder`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Kenneth Walker (RB, 4669) → **Drake Maye (QB, 5046)** (w/ Dez07) | +377 | 92% | window | 0.50 |  |  |
| 2 | Kenneth Walker (RB, 4669) → **Emeka Egbuka (WR, 5387)** (w/ Dez07) | +718 | 87% | window | 0.62 |  |  |
| 3 | Kenneth Walker (RB, 4669) → **Tetairoa McMillan (WR, 5706)** (w/ dwasson17) | +1037 | 82% | window | 0.69 |  |  |
| 4 | Travis Etienne (RB, 2306) → **Brian Thomas (WR, 2465)** (w/ ShanerBaner31) | +159 | 94% | window | 0.62 |  |  |
| 5 | Kenneth Walker (RB, 4669) → **Omarion Hampton (RB, 5983)** (w/ gsteskal23) | +1314 | 78% | window | 0.50 |  |  |

### @tud32994 — deck 30 cards · init 0.6 ms · gen 20.8 ms · outlook `rebuilder`

| # | Trade (give → receive) | Δ | Fair | Lane | Fit | insulting? y/n | would consider? y/n |
|---|---|---|---|---|---|---|---|
| 1 | Patrick Mahomes (QB, 3030) → **Marvin Harrison (WR, 3297)** (w/ ShanerBaner31) | +267 | 92% | window | 0.38 |  |  |
| 2 | Amon-Ra St. Brown (WR, 7725) → **Jahmyr Gibbs (RB, 7913)** (w/ Dez07) | +188 | 98% | value | 0.50 |  |  |
| 3 | Amon-Ra St. Brown (WR, 7725) → **Bijan Robinson (RB, 8390)** (w/ ShanerBaner31) | +665 | 92% | value | 0.50 |  |  |
| 4 | Patrick Mahomes (QB, 3030) → **Tee Higgins (WR, 3332)** (w/ dwasson17) | +302 | 91% | value | 0.50 |  |  |
| 5 | Patrick Mahomes (QB, 3030) → **Zay Flowers (WR, 3894)** (w/ dwasson17) | +864 | 78% | value | 0.50 |  |  |

---

## Method + fidelity notes

- Built by internal import of `backend.server` (no Flask server): the same session-construction and trade-job code paths as `/api/session/init` + `/api/trades/generate`, with the production flag file.
- Brand-new-user masking: the simulated user's own swipes, tier overrides, league preference, asset prefs, past trade decisions and Thompson shape counts are excluded. League-level state (other members' saved rankings, league likes, draft picks, impressions) is used exactly as production would.
- `log_trade_impressions` is not called — the eval writes nothing user-visible to the DB.
- Latency numbers are local-machine; Render dyno numbers will differ (esp. cold start). The one-time setup line above is the piece the keep-warm ping hides.
- Flags snapshot: see the JSON artifact (`feedback-workspace/deck-eval/deck_eval_20260815T220047Z.json`).

---

## Methodology delta vs the 2026-07-17 run

| Dimension | Prior run (2026-07-17) | This run (2026-08-15) | Why it matters |
|---|---|---|---|
| DB behind the eval | whatever was in the local dev `data/trade_finder.db` | **read-only mirror of production** (see [Data provenance](#data-provenance)) | the gate's own wording is "against current production data" |
| Leagues / teams | 4 leagues, 47 first-run sims | **9 leagues, 108 first-run sims** | all numeric Sleeper leagues production actually has |
| Leaguemates with real saved boards | **0** of 47 sims had a ranked opponent | 5 of 9 leagues have ranked opponents (`real_ranked_opponents` up to 5) | unlocks the whole **divergence** code path that was dark last time |
| `divergence`-basis cards in the first 5 | **0** of 235 | **126** of 540 (23%) | first-run decks are no longer purely consensus-priced |
| `likes_you` injected cards in the first 5 | **0** of 235 | **66** of 540, in 24 of 108 decks | see [Finding 1](#finding-1--likes_you-injection-is-the-entire-insult-signal) |
| Human scoring | columns left blank; insult rate never computed | explicit rule, applied to both runs' artifacts | first actual number this gate has produced |
| Script / flags | `scripts/deck_eval.py`, production `config/features.json` | **unchanged** — same script, same flag file, no code edited | the delta above is data, not method drift |

Nothing in `scripts/deck_eval.py`, `backend/`, or `config/features.json` was modified for this run.

## Findings

### Finding 1 — `likes_you` injection is the entire insult signal

*(measured + code-verified.)* **8 of 8** primary-rule cards, and **19 of 20** no-floor cards, are
`likes_you: true`. Not one is a card the trade generator itself produced.

`_inject_likes_you_cards_impl` (`backend/server.py:2819`) mirrors a leaguemate's own liked trade into the
user's perspective (`give = their_receive`, `receive = their_give`) and then sets
`composite_score = boost_score` where `boost_score = max(existing composite) + 1.0`
(`backend/server.py:2858`), which sorts it to the **top of the deck**. The only filters applied are
roster-actionability, `untouchable_ids`, `not_interested_ids`, past-decision dedup, and `_LIKES_YOU_CAP`
(`backend/server.py:2804`, = 3 per deck).
There is **no fairness gate and no user-gain gate** on this path — the docstring says so outright: *"the card's
pull is 'they already want this', not its score."*

Consequences, all measured on this run:

- 24 of 108 first decks (22%) contain ≥1 `likes_you` card inside the first five; their positions are
  **1 (×24), 2 (×22), 3 (×20)** — never lower.
- 51 of those 66 cards are **net-negative in consensus value for the new user**; 7 are ≤ −1000.
- The worst is card **#3** of `@MangoPatti`'s first deck: give A.J. Brown (4168) + James Cook (5677) +
  CeeDee Lamb (6862) → receive Jaxon Smith-Njigba (8073) + Devin Singletary (**228**) + Malik Davis (**229**).
  Δ **−8177**. That is a first impression built out of another user's wish.

This is a **design consequence, not a bug**: on the Trades tab as it exists today, the user has already ranked
and can read a "they want this" card as intelligence. On a **brand-new user's very first deck**, top-slotted
and unlabelled by value, it is the exact failure the gate was written to catch.

The lever is coarse: `trade.likes_you` is a global flag (`config/features.json`, currently `true`) and the
first-run pregen calls the same `/api/trades/generate`. There is no first-run-only suppression today.

### Finding 2 — divergence cards make first decks look *too good*, not insulting

*(measured + code-verified.)* 39 first-5 cards sit below the engine's own default fairness threshold of 0.75;
**all of them are `basis: divergence`**, which is by design — `fairness_floor_divergence = 0.55`
(`backend/trade_service.py:154`) relaxes the consensus fairness check for cards where both sides have real
boards, because the both-sides surplus gate already proves mutual gain.

The user-visible effect on a first deck is the opposite of an insult: cards like `Oronde Gadsden (1046) +
Michael Wilson (1353) + Derrick Henry (1731) → Drake Maye (5046) + Makai Lemon (3179)` (Δ **+4095**,
fairness 0.50) read as free money against the consensus numbers the provenance chip promises. One league
(`1312146456701829120`, La Resistance) accounts for 19 of the 45 auto-flags, driven by a single leaguemate
whose saved board is far from consensus.

This does **not** trip the insult rule and does **not** fail the gate. It is flagged because a dynasty-native
audience reading "CONSENSUS VALUES" next to a +4095 offer is a **credibility** risk on first impression, and
because it is newly live in production data. Recommend it goes to `pm-pfo` as an observation, not a blocker.

### Latency — what changed, and why

*(measured.)* Deck-gen latency rose from mean 23.1 ms / p95 53.0 ms to **mean 278.9 ms / p95 1015.3 ms**
— roughly 19× on the mean. The cause is Finding 1/2's cause: production has 10 816 `member_rankings` rows, so
`load_member_rankings` now returns real boards for leaguemates and the divergence generators actually run,
where the prior run fell through to the cheap consensus path.

This is still comfortably inside the <60s warm TTFT budget — a p95 of ~1 s of server-side deck generation
leaves the budget dominated by the Sleeper fetch (mean **701 ms** per league, measured) and Render cold start
(30–60 s, documented, not measured here). Two honest caveats: these are local-machine numbers on a
**SQLite** mirror, and production is **Postgres on a Render dyno** — the `load_member_rankings` query cost in
particular will differ. League-init stayed flat (mean 0.7 ms, p95 1.4 ms).

## Verdict

**PASS — the flip is not blocked by deck quality — with one operator decision recommended first.**

| Bar (from the prior report's own Thresholds table) | Result | Verdict |
|---|---|---|
| Empty-deck rate < 5% | 0.0% (0/108) | **PASS** |
| Insult rate < 3% | 1.48% primary rule (8/540); 2.41% at a 250 floor; 3.70% with no floor | **PASS** on the primary rule; **fails only at a zero materiality floor** |
| Latency compatible with <60s warm TTFT | gen p95 1.0 s, init p95 1.4 ms | **PASS** |

**On the bar itself.** The plan calls these thresholds **"proposed"** (`plan.md`, build item 2) and no ratifying
decision exists in `living-memory/DECISIONS.md` for them. This run uses them as written. **Operator ratification
is requested** for two things: (1) that `<3%` insult / `<5%` empty-deck remain the bar, and (2) the
`|Δ| ≥ 500` materiality floor in the scoring rule, since the verdict flips to FAIL (3.70%) without it.

**Recommended pre-flip action (cheap, reversible).** Suppress or gate `likes_you` injection on the first-run
deck — either flip `trade.likes_you` off for the duration of the Phase A cohort, or add a user-gain floor to
`_inject_likes_you_cards_impl` so a mirrored card is only injected when the new user is not materially
value-negative. With those 8 cards removed the insult rate is **0.00%** at the primary floor and **0.19%**
(1/540) with no materiality floor at all — i.e. the gate would pass under *every* scoring variant, including
the one it currently fails. That is the deck quality the trades-first argument assumes. This is an operator
call, not a QA veto: the gate as written passes either way.
