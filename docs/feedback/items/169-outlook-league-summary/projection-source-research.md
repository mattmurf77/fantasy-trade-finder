# FB #169 — Projection-source & playoff-odds research

**Purpose:** decide how FTF sources current-season player projections and computes playoff/championship odds for the #169 "outlook odds" modeling slice (Dependency A: redraft/projection value; Dependency B: league-state season simulator; per `mockups/outlook-odds/feasibility.md`).
**Author:** research task, 2026-07-21. Every external claim is cited; unverified items are marked **[unverified]**.

---

## TL;DR (validating the internal lean)

The internal lean was **"`nflreadpy` (NFLverse) for production projections, RosterAudit API as prototype-reference-only."** Independent research **confirms the licensing logic but corrects one factual gap:**

- **NFLverse does NOT publish forward-looking player projections.** It ships historical stats and *retrospective* "expected points" (ffopportunity). Using nflreadpy "for projections" means **building your own projection model** on top of it — a real modeling project, not a data pull. This is the single most important correction to the lean.
- **The cheapest path to per-player season/weekly point projections is Sleeper's own (unofficial) projections endpoint** — same provider FTF already depends on, already in-stack, no new licensing relationship. It should be the pragmatic v1 points feed; NFLverse is the licensing-clean backbone for an eventual own-model.
- **RosterAudit stays prototype-only** — every open RA endpoint carries a mandatory attribution backlink RA enforces by revoking keys; never shippable. Confirmed.
- **A v1 playoff-odds surface may not need player projections at all.** DynastyDaddy (open-source) drives its season sim off **team starting-lineup value + historical Elo + schedule**, not a points-projection feed. FTF already has all three ingredients. This de-risks Dependency B independently of Dependency A.

---

## Projection / value source comparison

| Source | Provides | Access | Cost | Commercial ToS | Freshness | Stack-fit | Verdict |
|---|---|---|---|---|---|---|---|
| **Sleeper projections** (unofficial) | Per-player **season + weekly point projections**, position-filterable (underlying data from Sportradar/Rotowire) | `GET api.sleeper.app/projections/nfl/<season>/<week>` — undocumented | Free | **Unclear/gray** — undocumented, no commercial guarantee; can be blocked/deprecated anytime | Live in-season | **Excellent** — FTF already depends on Sleeper's API | **Pragmatic v1 points feed.** Same provider FTF already trusts. Risk: unofficial/unstable. |
| **NFLverse / `nflreadpy`** | **Historical** stats, rosters, schedules; ffopportunity **expected** (retrospective) points; `load_ff_rankings` (DynastyProcess-relayed FP ranks/ADP) — **no forward projections** | `pip install nflreadpy` (Polars) | Free | **CC-BY 4.0 data (attribution required), MIT package — commercial OK** | Weekly (historical) | **Excellent** — Python-native | **Production backbone for an own model.** Cleanest license. You must *build* the projection. |
| **RosterAudit** `/projections/ppg-rankings` | Multi-year **PPG projections (2026–28)** + dynasty value | Open REST (`/wp-json/ra/v1`) | Free | **Mandatory attribution backlink; keys revoked if stripped** | Daily | Easy to call | **Prototype reference ONLY.** Attribution + competitor-dependency = never shippable. |
| **FantasyCalc** | Dynasty **and redraft trade values** (real-trade Elo), 30-day trends, ADP — **values, not point projections** | 3 undocumented JSON endpoints | Free | **No documented public API/ToS [unverified]** | Frequent | Easy | **Candidate for the redraft-VALUE gap (Dependency A), not for sim points.** ToS unverified. |
| **FantasyPros API** | Consensus rankings + **projections**, news, injuries | Official REST, keyed | Free prototype; prod bundled w/ MVP/HOF sub; **commercial = negotiated** | **Landmine:** personal keys are non-commercial AND "may not build a product that competes with FantasyPros" | Live | Easy | **Avoid for prod** — FTF is commercial and arguably competitive; needs a paid partner deal. |
| **ESPN projections** (unofficial) | Weekly/season projections | Undocumented hidden API | Free | **Unofficial, ToS-gray**; scraping risk | Live | Medium | Skip — no advantage over Sleeper, worse ToS posture. |
| **Yahoo Fantasy API** | Stats, some projections | Official OAuth API | Free | Documented ToS but usage-restricted | Live | OAuth overhead | Skip — OAuth friction, missing datapoints, no edge over Sleeper. |

---

## What RosterAudit and DynastyDaddy actually use

**RosterAudit.** Trade values come from an Elo engine over ~611K real Sleeper trades (not a projection source). Player **stat lines are pulled from NFLverse** (`/player-stats/{id}`). It exposes **`/projections/ppg-rankings`** — multi-year PPG projections (2026–28) plus dynasty value — and computes **championship odds in its League Deep Dive via "projection source + schedule-aware Monte-Carlo."** Every open endpoint returns a mandatory `attribution` field ("Values by RosterAudit.com") and RA revokes keys that strip it, so the API is a **private benchmark / cold-start reference, never a shipped runtime dependency** (source: `docs/business/product/2026-07-20-rosteraudit-teardown.md`, live endpoint probe 2026-07-20).

**DynastyDaddy** (open-source, [G-Sher/dynasty-daddy](https://github.com/G-Sher/dynasty-daddy) — Angular + Node/Express + Postgres, Python cron). Player values come from a **daily scrape of KeepTradeCut** (KTC has no public API) tied to **Sleeper's public APIs** for league/roster data ([README](https://github.com/G-Sher/dynasty-daddy)). It ships **both dynasty and redraft**, and — notably — a **season simulator that runs 10,000 simulated seasons "factoring in schedule, historical Elo score, and starting line-up" to produce matchup and playoff probabilities** ([dynasty-daddy.com](https://dynasty-daddy.com/)). Key takeaway: **DynastyDaddy computes playoff odds without any forward player-projection feed** — it drives the sim off roster/lineup value + historical scoring + schedule. It does **not** use NFLverse/DynastyProcess/FantasyCalc for values (KTC-only). Repo license **[unverified]** — README shows no license in the fetched content; confirm before reusing any code.

---

## Playoff / championship-odds methodology (minimal viable for FTF)

The standard industry approach is a **Monte-Carlo over the remaining schedule** ([spreadsheetsolving](https://spreadsheetsolving.com/fantasy_football_monte_carlo/), [srome.github.io](http://srome.github.io//Making-Fantasy-Football-Projections-Via-A-Monte-Carlo-Simulation/), [richabdill robsim](https://richabdill.com/robsim/)):

1. Each team's weekly score is drawn from **Normal(μ, σ)** — μ = projected or trailing mean team points, σ = stdev of recent weekly team scores (common: last 4–5 games). Central Limit Theorem justifies the normal (a lineup is a sum of players).
2. For each remaining week, simulate every matchup from the two teams' draws; the higher score wins.
3. Run **N simulations** (2,000–10,000; DynastyDaddy uses 10,000), add simulated wins to **current standings**, apply **playoff-format logic** (seeds, byes, tiebreakers), and count how often each team makes playoffs / wins the title.
4. **"+N wins from this trade"** = re-run with the added player in / removed player out and diff expected wins.

**Minimal FTF build** given what already exists (`power_rankings.py`, Sleeper schedule/standings ingestion):
- **v1 (no projection source):** μ from each team's trailing weekly-points history (Sleeper scoring history), σ from recent weeks, Sleeper remaining schedule, Monte-Carlo → playoff/title %. Mirrors DynastyDaddy. Ships Dependency B without Dependency A.
- **v2 (projection-enhanced):** replace/blend μ with a **starting-lineup points projection** (Sleeper projections endpoint or an nflverse-derived model), improving early-season signal when trailing data is thin.

---

## Recommendation for #169

1. **Production projection/points feed — refine the lean.** Adopt **Sleeper's unofficial projections endpoint as the pragmatic v1 points feed** (in-stack, same provider FTF already trusts, per-player season+weekly points). Keep **NFLverse/`nflreadpy` as the licensing-clean production backbone** for an eventual **own** projection model — but budget it as a real modeling project, because **nflverse ships stats and retrospective expected points, not forward projections.** The lean's "nflreadpy for projections" is right on licensing, wrong on effort: it's build-your-own, not plug-in.
2. **Redraft-VALUE gap (Dependency A, the Redraft League-Summary tab):** this is a *value* need, not a *points* need. **FantasyCalc redraft values** are the cleanest fit (real-trade, free, redraft+dynasty) — pending ToS verification **[unverified]**. RA's redraft/PPG data is prototype-only (attribution landmine).
3. **Prototype source:** RosterAudit `/projections/ppg-rankings` for a throwaway spike **only** — never shipped (mandatory backlink). Confirmed.
4. **Playoff-odds method:** build the **v1 Monte-Carlo (team-scoring-history + Sleeper schedule + format logic)** first — it unblocks Dependency B without waiting on any projection source, exactly as DynastyDaddy does. Layer projection-based μ in v2.
5. **Off-season caveat (load-bearing — it is July 2026, preseason):** **no NFL games have been played, so there are no current-season standings and no weekly scoring history.** Any odds shown now are pure priors off preseason projections — **low signal and easily mistaken as authoritative.** Recommend **gating the odds surface until real scoring data exists (~Week 3–4)**, or labeling every preseason number "projected/beta" exactly as the mockups already do. Do not ship a hard "86% playoff odds" preseason.

**ToS/licensing landmines (explicit):**
- **RosterAudit** — mandatory attribution backlink on all open endpoints; keys revoked if stripped → **never shippable**.
- **FantasyPros** — personal keys non-commercial *and* barred from building a competing product; commercial requires a negotiated paid deal → **avoid for prod**.
- **NFLverse** — CC-BY 4.0 requires **visible attribution** to nflverse if its data is used in-product (commercial otherwise fine).
- **Sleeper projections** — undocumented, no commercial guarantee, can be blocked/deprecated without notice.

---

## Blocking unknowns for the operator

1. **Sleeper projections dependency call.** Are we comfortable taking on *another* unofficial Sleeper endpoint (data sourced from Sportradar/Rotowire) as a v1 points feed? FTF already depends on Sleeper's unofficial API, but this endpoint could be blocked or changed anytime. Ship-behind-flag or hold?
2. **Fund an own nflverse-derived projection model?** "nflreadpy for production projections" = building a model (real scope), because nflverse has no forward projections. Confirm appetite, or default to Sleeper projections indefinitely.
3. **FantasyCalc ToS [unverified].** No documented public API/terms found. Before using FantasyCalc redraft values for Dependency A, someone must confirm terms permit commercial use.
4. **DynastyDaddy license [unverified].** README showed no license in the fetched content. If we want to reuse its sim design/code, confirm the repo license first.

## Sources

- RosterAudit teardown (internal): `docs/business/product/2026-07-20-rosteraudit-teardown.md`; feasibility: `mockups/outlook-odds/feasibility.md`
- DynastyDaddy repo: https://github.com/G-Sher/dynasty-daddy · site: https://dynasty-daddy.com/
- DynastyProcess data: https://github.com/dynastyprocess/data
- nflreadpy: https://nflreadpy.nflverse.com/ · https://github.com/nflverse/nflreadpy · license: https://nflreadpy.nflverse.com/
- ffopportunity (expected points): https://ffopportunity.ffverse.com/
- Sleeper projections endpoint (unofficial): https://sleeper-api-client.readthedocs.io/en/latest/endpoints/projections.html · undocumented-endpoint discussion: https://github.com/joeyagreco/sleeper/discussions/11 · https://docs.sleeper.com/
- FantasyCalc API: https://www.fantasydatapros.com/fantasyfootball/blog/fantasycalc/1
- FantasyPros API terms: https://www.fantasypros.com/api-data/ · https://partnershq.fantasypros.com/faq
- ESPN hidden API: https://zuplo.com/learning-center/espn-hidden-api-guide · Yahoo Fantasy API ToS: https://legal.yahoo.com/us/en/yahoo/terms/product-atos/fantasysportsapi/index.html
- Monte-Carlo playoff-odds method: https://spreadsheetsolving.com/fantasy_football_monte_carlo/ · http://srome.github.io//Making-Fantasy-Football-Projections-Via-A-Monte-Carlo-Simulation/ · https://richabdill.com/robsim/
