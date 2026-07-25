# #183 research note — IDP dynasty value sources (for eventually enabling IDPs)

2026-07-25. Companion to the #183 fix (hide metadata-less roster ids). Research only — nothing built.

## What the hidden entries are

Sleeper rosters in IDP leagues carry defensive player ids (LB/DB/DL) and some leagues carry team-DST ids. Neither exists in FTF's player pool (built from DynastyProcess offense-only values), so `/api/league/power-rankings` used to serialize them as id-only rows that rendered as nameless "Other" entries. Sleeper's own player cache DOES have full metadata for IDPs (name/position/team/age) — identification is not the gap; **valuation** is.

## Candidate value/ranking sources

- **FantasyPros IDP dynasty ECR** — the most credible consensus source: [dynasty IDP rankings](https://www.fantasypros.com/nfl/rankings/dynasty-idp.php) updated daily from 100+ experts, plus [IDP dynasty rookie ranks](https://www.fantasypros.com/2026/07/idp-dynasty-rookie-draft-rankings-2026-fantasy-football/). FTF's existing values are "built on FantasyPros Dynasty Ranks" via DynastyProcess, so this is the same family. Access would need the FantasyPros partner API or scraping (ToS check required).
- **DynastyProcess** — its [trade calculator](https://calc.dynastyprocess.com/) and public values CSV are offense + picks only today; no IDP values sheet. If DP ever ships one, it drops straight into our existing loader path (lowest integration cost).
- **KeepTradeCut** — [crowdsourced calculator](https://keeptradecut.com/trade-calculator), offense only: **no IDP values** ([survey of calculators](https://apexfantasyleagues.com/dynasty-trade-calculators/) confirms IDPs are generally absent from the big free calculators).
- **Niche IDP charts** — [The IDP Center trade chart](https://www.theidpcenter.com/idp-trade-chart) (proprietary, per-format), [Dynasty Nerds top-275 IDP ranks](https://www.dynastynerds.com/idp/dynasty-idp-rankings-tiers/), [Draft Sharks dynasty IDP](https://www.draftsharks.com/dynasty-rankings/idp), [DynastyTradeCalculator.com](https://dynastytradecalculator.com/) (paid; supports an IDP player group). Mostly paid/manual — fine for a seed table, not for a live feed.

## Feasibility

Moderate, and gated on a value source rather than engineering. The pipeline shape already exists: extend the universal pool with an IDP seed (FantasyPros ECR mapped through the same rank→Elo affine used for offense, or a manually refreshed seed table from one of the charts above), tag pool players `idp: true`, and let rankings/trades/power-rankings work unchanged. Two product cautions: (1) IDP values only make sense in IDP leagues — surfaces would need per-league gating off roster composition; (2) cross-community value scales differ (offense-vs-IDP exchange rates are contested), so a first slice should probably show IDPs in rosters/power-rankings (identification + rough value) before letting them into trade generation. Suggested trigger to revisit: an operator/tester request from an actual IDP league, or DynastyProcess shipping IDP values.
