# Organic Trade Corpus — First Patterns Report (2026-08-16)

**What this is:** the first empirical read of the organic executed-trade corpus backfilled
from Sleeper on 2026-08-16 (operator directive). These are the **POM calibration patterns**
for the future league simulator — the "5–8 weak but cheap patterns" of Grimm et al.
pattern-oriented modelling that any ABM parameterization must hit *simultaneously*
(docs/research/matchmaking/round-3/02b-appendix-abm-validation-calibration.md §1.4 and
roadmap step 2). Any simulator parameter set that fails any filter below is rejected.

**Data source: PROD** (Render Postgres, via `DATABASE_URL_PROD`). Backfill scripts:
`scripts/backfill_sleeper_trades.py` + `scripts/backfill_suggestion_links.py` (runbook §
"Organic trade backfill"). Background capture flag `market.trade_capture` was **ON** in
`config/features.json` at backfill time (the daemon had already captured 26 current-season
trades; the backfill is flag-independent and added the historical corpus).

## Corpus summary

| | |
|---|---|
| Executed trades captured | **555** (529 new in this backfill + 26 pre-existing) |
| League-seasons | **22** (all 12-team) across **5 franchises** (Lakeview, FFv3, La Resistance, Bush League, SFO) |
| Seasons | 2022–2026 via `previous_league_id` chains (up to 3 prior seasons per synced league) |
| Complete seasons | 17 (2022–2025); the five 2026 leagues are in progress (26 trades so far) |
| Suggestion-link rows | 121 (12 live-matcher + 109 retro backfill) |

Chain map (2026 root ← historical), all reached depth-capped at 3 prior seasons:

- Lakeview: 1312076055586050048 ← 1180999595377590272 [2025] ← 1101407304802574336 [2024] (chain ends — league started 2024)
- FFv3: 1312140920132497408 ← 1181674778942836736 [2025] ← 1048263304533188608 [2024] ← 916436765509046272 [2023]; the 2025 root's own chain also reached 867593839303598080 [2022]
- La Resistance: 1312146456701829120 ← 1182123531320094720 [2025] ← 1049793265824284672 [2024] ← 918566627841703936 [2023]; 2025 root's chain reached 833049485801267200 [2022]
- Bush League: 1338231586314780672 ← 1205882571070636032 [2025] ← 1048759256180166656 [2024] ← 920453410162298880 [2023]; 2025 root's chain reached 784648979949449216 [2022]
- SFO: 1312583962966650880 ← 1181018946429943808 [2025] ← 1048322366444601344 [2024] ← 991840879893590016 [2023] — a 2022 SFO season, if it exists, is beyond the depth cap (re-run with `--max-prior-seasons 4` to check)

## Pattern 1 — Trades per league-season (distribution, complete seasons only)

Sorted, n=17: `10, 11, 11, 12, 13, 14, 18, 21, 22, 28, 31, 42, 43, 51, 52, 64, 86`

- min 10 · median **22** · mean 31.1 · max 86 — right-skewed; a single mean would mislead.
- Strong per-league propensity: SFO ran 51–86/season; Bush 10–21. League identity (not just
  season) is a first-class driver — the simulator needs a per-league activity parameter,
  not one global rate.

| Franchise | 2022 | 2023 | 2024 | 2025 | 2026 (partial) |
|---|---|---|---|---|---|
| Lakeview | — | — | 52 | 43 | 11 |
| FFv3 | 18 | 42 | 31 | 28 | 1 |
| La Resistance | 11 | 13 | 22 | 14 | 5 |
| Bush League | 21 | 12 | 11 | 10 | 0* |
| SFO | — | 51 | 86 | 64 | 9 |

*Bush 2026 league object exists but has no completed trades yet.

## Pattern 2 — Package-size mix (share of all 555 trades)

| Shape (larger side–smaller side) | Count | Share |
|---|---|---|
| 1-for-1 | 165 | 29.7% |
| 2-for-1 | 150 | 27.0% |
| 2-for-2 | 50 | 9.0% |
| 3+ on a side | 172 | **31.0%** |
| Lopsided oddities (1-0 / 0-0, FAAB-heavy legs) | 9 | 1.6% |
| Multi-team (3+ rosters) | 9 | 1.6% |

Big packages are not a tail: nearly a third of organic trades involve 3+ assets on one
side. A simulator (or suggestion engine) capped at 2x2 misses ~31% of the real market.

## Pattern 3 — Asset composition

| Mix | Count | Share |
|---|---|---|
| Players + picks (mixed) | 385 | **69.4%** |
| Picks only | 90 | 16.2% |
| Players only | 70 | 12.6% |
| Multi-team / other | 10 | 1.8% |

FAAB rode along in 11 trades (2.0%). Mixed packages dominate — pick sweeteners are the
normal grammar of dynasty trades in this corpus, not a special case.

## Pattern 4 — Timing profile

By calendar month of `traded_at` (all 555; use months, not Sleeper's `leg` — every
offseason trade lands on leg 1, so 337 "week 1" rows are an artifact):

```
Jan  5   Feb 16   Mar 20   Apr  9
May 45   Jun 49   Jul 45   Aug 120
Sep 66   Oct 79   Nov 98   Dec  3
```

- **August spike (120)** — rookie-draft/startup season and preseason repositioning.
- Steady offseason plateau May–Jul (~45–49/mo).
- In-season ramp Sep→Nov peaking at the trade deadline (in-season legs 9–11 carry
  24/32/34 trades), then **post-deadline collapse: 3 trades in December**, 5 in January.
- Feb–Apr trough (9–20/mo).

This is exactly the "preseason spike, deadline spike, post-deadline collapse" shape POM
§1.4 predicts; the simulator's weekly tick must reproduce all three phases.

## Pattern 5 — Dyad repetition (same pair trading again)

546 two-team trades: **369 distinct manager pairs observed vs 409.9 expected** if each
trade picked a uniform-random pair (12 rosters → 66 possible dyads per league-season).
120 dyads (32.5% of active dyads) traded ≥2 times. Fewer-distinct-than-expected =
positive repetition: managers re-trade with partners they've already dealt with. Heavier
in the high-volume leagues (SFO 2024: 85 trades over 45 dyads, 24 repeating; FFv3 2024:
30 over 16). The simulator needs a partner-affinity term, not memoryless pairing.

## Pattern 6 — Participation concentration (Gini of trades-per-manager)

Zero-inclusive Gini per complete league-season (all 12 rosters counted):

- n=17, mean **0.374**, range 0.234–0.583.
- Most leagues have 9–12 of 12 managers making ≥1 trade; the busiest leagues are also the
  most egalitarian (SFO 2023–25 Gini 0.23–0.26 with all 12 trading), while low-volume
  seasons concentrate (La Resistance 2022: 7/12 trading, Gini 0.583).

Moderate concentration, never one-whale markets. A simulator producing Gini ≈ 0 (everyone
equal) or ≥ 0.7 (one dominant trader) fails this filter.

## Pattern 7 — Suggested vs organic (retro links)

121 `suggestion_trade_links` rows now cover every captured current-season-league trade:
12 written by the live matcher (all `match_type` NULL) + 109 retro rows from this
backfill (all no-match). **`was_recommended` = 0/121 → suggested-share 0.0%.**

This is the honest pre-app baseline, not a failure: `deck_impressions` only exist since
2026-07-27, and exactly **one** captured trade executed after that date (FFv3,
2026-08-14 — examined by the live matcher, no suggestion matched). Essentially the whole
corpus predates the app serving suggestions in these leagues. This ratio is the
going-forward endorsement metric (`GET /api/admin/suggestion-telemetry/ratio`), with
ghost links as the incrementality control.

## Method & caveats

- **Completion-only corpus (proposal bias).** Sleeper exposes completed trades; rejected
  offers are invisible. POM pattern "accept rate conditional on offer surplus" is
  **not computable** from this corpus and must come from FTF's own offer telemetry.
- **Retro matching is exact-hash-only and undercounts.** Historical `deck_impressions`
  carry `trade_hash` but not `assets_json` (that column starts 2026-08-16), so retro
  linking reconstructs the serve-time hash and requires identity — partial overlaps are
  invisible, and suggestions whose pick side used generic-ladder ids can never hash-match
  an executed owned pick. Retro matches are marked `match_type='retro_exact'` to stay
  distinguishable from live `exact`/`partial` rows. (Given only 1 trade overlapped the
  impression era, the undercount is currently 0 in practice.)
- **No value-gap analysis.** There are no historical consensus values for 2022–2025 trade
  dates in the DB; pricing old trades with today's values would be systematically wrong
  (players age, picks resolve), so value-surplus patterns are deliberately skipped until
  dated boards (cf. `scripts/dp_values_history_capture.py`) are wired to this corpus.
- **Directional asymmetry (contenders buy vets, rebuilders buy picks) not yet computed** —
  needs standings-at-trade-time context; candidate for the next report.
- **Sample bias.** All 5 franchises share the operator as a member; manager pools overlap
  across leagues and are not independent draws from the dynasty population.
- **2026 seasons are in progress** — excluded from distributional stats, shown for
  completeness.
- **Numbers come from PROD**; the backfill is idempotent (re-running both scripts wrote 0
  new rows on the verification pass).

## Suggested POM split (for the simulator work)

Per §1.4 / roadmap step 2, hold out validation patterns before calibrating: use Patterns
1–4 (volume, size mix, composition, timing) for **construction**, and hold out Patterns
5–6 (dyad repetition, Gini) for **validation**. Pattern 7 is a live metric, not a filter.
