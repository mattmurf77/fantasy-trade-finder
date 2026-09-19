# Teardown: TI-CALC (friend's trade calculator)

*2026-07-09. Live app: https://fantasy-trade-calculator.vercel.app · Source: https://github.com/onrits/fantasy-trade-calculator (last commit 2025-06-20).*

Context: the author (a friend of the operator) is winding this app down to help with FTF. This teardown mines it for features/practices worth adopting. Headline interest: **its tier structure anchors every tier to a fungible dynasty asset (draft-pick equivalents), giving all users a shared, objective reading of tiers.**

## What it is

Next.js (pages router) + Firebase (Google auth, one Firestore doc per user) + static JSON data baked into the bundle. Three pages: Trade Calculator (+ read-only rankings sidebar), Edit Rankings (sign-in gated: preset generator, drag-drop tier board, "Tiers Wizard", outlier summary), My Team (unauthenticated Sleeper roster import, market-vs-my-value deltas). ~3,200 lines JS, no tests, no live data pipeline — 393 players hand-curated (FantasyCalc-derived market values + 0–10 component scores for age/production/projection/market), frozen at commit time.

## The core idea: the FRP unit

All values are denominated in **FRPs — "Base First Round Pick" equivalents**. Base First (1.0) = "generic future 1st, equally likely to be pick 1 or 12, worth ~1.25–1.75 WAR/season." Josh Allen = 4.4 FRPs. Values aren't abstract points; they're counts of an asset every dynasty player already prices intuitively.

**11 tiers, each triple-anchored** — a pick equivalent, a WAR band, and historical positional finishes — surfaced in a collapsible legend and embedded in tier header names ("CORNERSTONES – 2-3 1STS – TIER 3"):

| Tier | Name | Pick anchor | WAR (3-yr) | FRPs | Historical finishes |
|---|---|---|---|---|---|
| 1 | Prometheus | 4+ 1sts | 6.0+ | 4.4+ | QB 1–2 |
| 2 | Franchise Altering | 3+ 1sts | 5.0–6.0 | 3.33–4.0 | QB 3–4, WR 1–3 |
| 3 | Cornerstones | 2–3 1sts | 4.0–4.99 | 2.67–3.33 | QB 5–8, WR 4–8, RB 1–5, TE 1–2 |
| 4 | Portfolio Pillars | 2+ 1sts | 3.25–3.99 | 2.17–2.66 | QB 9–12, WR 9–15, RB 6–11, TE 3 |
| 5 | Hopeful Elites | 1–2 1sts | 2.5–3.24 | 1.67–2.16 | QB 13–17, WR 16–20, RB 12–16, TE 4–5 |
| 6 | Kind of Exciting | 1st+ | 2.0–2.49 | 1.33–1.66 | QB 18–21, WR 21–24, RB 17–22, TE 6–7 |
| 7 | Solid Pieces | Late 1st | 1.5–1.99 | 1.0–1.33 | QB 22–24, WR 25–32, RB 23–29, TE 8–10 |
| 8 | Bridge Players | Early 2nd | 1.0–1.49 | 0.67–0.99 | WR 33–40, RB 30–36, TE 11–13 |
| 9 | Rentals | Mid 2nd | 0.5–0.99 | 0.33–0.66 | WR 41–50, RB 37–44, TE 14–16 |
| 10 | Bench Fodder | Mid 3rd | 0.0–0.49 | 0–0.32 | WR 51–60, RB 45–52, TE 17–20 |
| 11 | Roster Cloggers | Mid 4th | <0 | <0 | WR 61+, RB 53+, TE 21+ |

Mechanics worth knowing:

- **Tier is primary; value is derived.** Generated rankings assign tier by overall-rank breakpoints, then linearly interpolate the player's FRP value inside the tier's band (`pages/rankings.js:36-70`). Moving a player between tiers snaps their value into the new band.
- **Picks share the tier taxonomy.** 66 pick assets (`data/draftPickValues.json`): current-year picks priced per slot (1.01 = 2.75, 1.10 = 1.00 — the literal base unit, 2.03 = 0.65, 3rds ≈ 0.05–0.10, 4ths = 0.01); future years bucketed Early/Mid/Late with ~25%/yr decay (2026 1st E/M/L = 1.25/1.00/0.75; 2028 1st Mid = 0.75). Every pick carries a tier, so picks participate in tier logic exactly like players.
- **The anchor is load-bearing in the UX**, not decorative: tier headers, asset chips ("Tyreek Hill (Player, Tier 8) – 0.90"), wizard questions, and trade verdicts all speak "worth X firsts."

## Trade engine (`utils/tradeLogic.js`, 177 lines, pure function)

Sum FRP values per side, then multiplicative adjustments — each emitting a human-readable explanation string rendered as an "Adjustments" list:

1. **Roster-spot adjustment**: −5% per extra player received (current-year picks count as players; future picks don't occupy a roster spot).
2. **Quantity-for-quality clogger tax**: side sending 3+ more assets × (1 − 0.10·(diff−2)). (Stacks with #1 — arguably a bug.)
3. **QB tax**: receiving a QB ≥ 1.5 FRPs with no QB back → −7.5%.
4. **Tier-mismatch / star tax**: compare each side's best tier; allowed gap = 1 tier if either top asset is tier ≤3, else 2; overage taxed 10%/tier, ×1.5 if a tier-1 asset is involved. Structurally blocks "a pile of tier-6s buys a tier-2 stud."
5. **Verdict**: even if |Δ|/max ≤ 7.5%; special case — same tier + same count on both sides → "Even Trade — differences are a matter of preference."
6. **Delta → concrete asset**: verdict expresses the gap in FRPs, finds the nearest-value pick in the table, and suggests it: "Team 1 wins by 0.15 First Round Picks — roughly equivalent to: 2025 2nd Rd. Consider adding a player or pick worth 0.15."

## Other features

- **Tiers Wizard**: per-player micro-review asking the tier's anchor question ("Are they worth 2–3 First Round Picks?") with a 5-point Likert (Worth Much Less → Worth Much More) mapped to ±2 tier moves; value re-interpolated in the new band; progress in localStorage with "skip reviewed" toggle.
- **EasySetup generator**: 5 archetype presets (Youth Focused / Contender / Balanced / All Value / Upside Chaser) pre-filling 4 component-score sliders + per-position weights; score = Σ(weight × subscore/10) × posWeight.
- **Outlier summary**: personal-vs-market deltas ≥ 0.5 FRP → top-5 "high on" / "low on" lists.
- **My Team**: unauthenticated Sleeper import (username → leagues → roster), Market/My Value/Delta table.
- Distinctive neo-brutalist identity (cream/indigo, hard borders, offset shadows, Space Mono).

## Weaknesses (don't copy)

- Static hand-maintained data in the bundle; stale immediately; 235/393 players are zero-value padding; season hardcoded to 2025.
- Tier tables duplicated in 4+ files with drifting values; overlapping rank breakpoints (T1 1–3 vs T2 2–9); phantom tiers 12–13; no tests.
- No league-format awareness at all (no SF/1QB, no TE premium).
- Rankings editor fully sign-in gated with no preview; debug routes shipped to prod (14.6 MB `/api/players` dump); stacked double roster penalties; name-string player matching against Sleeper.

## FTF vs TI-CALC

| Dimension | TI-CALC | FTF |
|---|---|---|
| Value unit | FRP (future 1st = 1.0) — fungible, intuitive | Dynasty value points via `elo_to_value` — opaque scale |
| Tier meaning | Global, cross-position, triple-anchored (picks/WAR/finishes) | 5 per-position/per-format Elo bands — relative, unanchored |
| Personalization | Sliders + drag-drop + wizard; static market baseline | Trio Elo + shrinkage toward live DP consensus — much stronger |
| Data freshness | Frozen snapshot | Live DP refresh |
| Formats | None | 1qb_ppr / sf_tep, per-league detection |
| Quantity-vs-quality | Tier-mismatch tax + roster penalties (explicit, explained) | Crown-asset premium (shipped dark) + package diminishing returns |
| Trade discovery | None (manual calculator only) | Mutual-gain finder, matches, dual-board in-league calculator |
| Verdict explainability | Itemized adjustment reasons + pick-equivalent delta | Point ratio + verdict string only |
| Picks in trades | First-class, tiered, per-slot values | Rankable generic picks; NOT in generated trades; calculator picks deferred to v2 |

## Adoption candidates (prioritized)

1. **Pick-equivalent verdict deltas** — express calculator/trade-card gaps as "≈ a mid 2nd" and suggest the nearest pick to close the gap. Picks are already seeded in our value space (`server.py:723-737`, bridge at `trade_service.py:223-251`); this is presentation-layer work on `/api/trade/evaluate` and trade cards.
2. **Tier ↔ pick anchors** — compute each tier band's value range in "base firsts" (generic 1st Mid as the unit) from `tier_config.json` + `elo_to_value`, surface in TiersScreen headers and a legend. ⚠️ Complication: our bands are per-position/per-format (QB/TE compressed in 1qb), so anchors differ by position unless we anchor on the uniform band set or show per-position anchors — TI-CALC's cross-position tiers dodge this by construction. Also our bands span ~1.5× value inside a tier, so anchors must be ranges, not points.
3. **Explainable adjustments** — emit a `reasons[]` list from the evaluator (waiver-slot cost, package adjustment, crown-asset premium, outlook blend) the way `tradeLogic.js` self-documents every modifier.
4. **Outlier report** — we already have both layers (personal Elo + consensus seed); diff them to power "you're high/low on X" trade-target discovery. TI-CALC needed manual sliders to get this; we get it free from trios.
5. **Anchor-question wizard** — "Is X worth a mid 1st?" is literally ordinal anchor placement, i.e. Lever B of `docs/plans/trios-tier-calibration-plan-2026-07-08.md`, with a pick-denominated framing. Natural complement to trios for cold-start and boundary calibration.
6. **Even-trade-by-tier language** — "same tier, same count → matter of preference" pairs well with our disposition/preference system.
7. **Cross-check pick decay constants** — his future-year decay (~25%/yr, E/M/L buckets) vs our generic-pick Elo seeds; cheap calibration sanity check before calculator picks v2.
