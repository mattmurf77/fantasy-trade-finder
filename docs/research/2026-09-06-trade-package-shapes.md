# Trade package shapes: completed Sleeper trades versus recorded owner views

> Read-only descriptive research, 2026-09-06. Source code baseline: `4026ebc81eaae50b345b42421641125c5b8d413e`. This is evidence for a separately reviewed presentation change, not a decision, implementation, causal experiment, or acceptance-rate estimate. No account, league, player, impression, or transaction IDs are published.

## Finding

**Observed, high confidence within the recorded cohort:** on September 5, **9 of 15 recorded viewed cards (60%) had at least three players on one side; 3 of 15 (20%) had at least three players on both sides**. The fifteen impressions were also fifteen distinct packages. Mean player count was 4.33, versus 2.89 across the last 30-day view cohort. This supports the owner's recent experience of player-heavy cards.

**Important counter-evidence:** completed trades are often pick-heavy. In the matched 30-day window, completed trades averaged **2.08 players but 4.00 total assets**, versus **2.89 players and 3.29 assets** for recorded views. An indiscriminate total-asset penalty would target a type of package that genuinely executes. The owner also completed a **3x4-player trade**; there is no basis here for banning large trades.

**Inference, limited confidence:** prefer a bounded, soft player-complexity preference in generated-deck presentation, not a hard generation cap, a valuation change, or a claim that one generator/policy caused the experience.

## Scope and collection

The account was resolved from feedback #419's stored reporter key through its one linked account and two confirmed working aliases. The authoritative public Sleeper **2026** league list contained **three leagues**, and owner/co-owner roster membership was verified for each. Nine initial DB membership/importer candidates were not treated as nine current linked leagues: historical league metadata and the importer-only `leagues.user_id` would mis-scope this analysis.

At **2026-09-06 04:52:50–04:53:08 UTC**, public transaction legs **0–18** were fetched for all three allowed leagues: **57 successful reads, zero failures**. All **28 unique completed trades** appeared on leg 1. The public transaction-ID sets exactly matched the 28 stored rows, per league (11, 12, 5); no missing or extra stored IDs were found. Older `synced_at` values therefore did not imply missing trades here. No 2025 predecessor leagues were fetched. All 28 were two-party trades; none contained FAAB. Two had a zero-asset side and remain explicitly represented, not silently discarded.

Main windows:

- Calendar 2026 in these current linked leagues: January 1 00:00 New York through collection cutoff.
- “Last 30 days”: **August 7 00:00 New York / August 7 04:00 UTC through September 6 04:52:50 UTC** (30 calendar dates plus the current partial hour).
- Latest active day, September 5 New York: **September 5 04:00 UTC through September 6 04:00 UTC**.
- September 6 New York so far: **zero recorded views and zero served impressions** at collection. September 5 is not labelled “today.”

The database connection used the existing read-only helper, asserted `transaction_read_only=on`, and enforced a **10-second statement timeout**. Public GETs used **15-second timeouts and concurrency three**. No capture/backfill writer, new trade generation, platform write, flag/config change, or production mutation ran. A stored-data detail pass completed at 2026-09-06T04:57:25.329380+00:00; all cohort counts and shape distributions remained identical to the fresh run.

## Counts and package composition

“Players” excludes draft picks. “Assets” includes players plus picks, not FAAB. Player-only shape counts may have a zero side when that side consists of picks. Two-way orientation is canonicalized as smaller side x larger side for comparison; thus 2x1 and 1x2 share one bucket. The private aggregate also retains owner give/receive orientation.

| Cohort | N | ≥3 players on either side | ≥3 players on both sides | Mean players/trade | Mean assets/trade |
|---|---:|---:|---:|---:|---:|
| Completed, 2026 current leagues | 28 | 2/28 (7.1%) | 1/28 (3.6%) | 1.50 | 3.39 |
| Owner involved, 2026 | 8 | 1/8 (12.5%) | 1/8 (12.5%) | 2.00 | 2.88 |
| Completed, last 30-day window | 12 | 2/12 (16.7%) | 1/12 (8.3%) | 2.08 | 4.00 |
| Owner involved, last 30-day window | 5 | 1/5 (20.0%) | 1/5 (20.0%) | 2.60 | 3.00 |
| Recorded viewed cards, last 30 days | 164 | 30/164 (18.3%) | 6/164 (3.7%) | 2.89 | 3.29 |
| Distinct viewed packages, last 30 days | 146 | 30/146 (20.5%) | 6/146 (4.1%) | 2.87 | 3.30 |
| Recorded viewed cards, September 5 | 15 | 9/15 (60.0%) | 3/15 (20.0%) | 4.33 | 4.47 |

All twelve recent completed trades and all 164 recent recorded owner views came from the same one of the three current leagues; the other two contributed historical 2026 trades but no recent viewed cohort. The comparison is therefore concentrated, not three independent active leagues.

| Cohort | Players only | Picks only | Mixed players + picks | FAAB | Unknown assets |
|---|---:|---:|---:|---:|---:|
| Completed, 2026 current leagues | 7 | 7 | 14 | 0 | 0 |
| Owner involved, 2026 | 5 | 2 | 1 | 0 | 0 |
| Completed, last 30-day window | 4 | 2 | 6 | 0 | 0 |
| Owner involved, last 30-day window | 4 | 1 | 0 | 0 | 0 |
| Recorded viewed cards, last 30 days | 110 | 0 | 54 | 0 | 0 |
| Recorded viewed cards, September 5 | 13 | 0 | 2 | 0 | 0 |

For strictly **player-only, positive-assets-on-both-sides** completed trades, the 2026 sample is just **six**: four 1x1, one 1x2, and one 3x4. The owner's corresponding subset is four: two 1x1, one 1x2, and one 3x4. Five of six being small is suggestive, but far too little to infer a universal small-package preference. Among recorded player-only views, small 1x1/1x2 shapes were **69/110 (62.7%)** across the month and **3/13 (23.1%)** on September 5.

### Canonical shape counts

Each cell is **player-only counts / all-asset counts** within the complete cohort, not a restricted no-picks cohort. For example, a player-for-pick trade can be 0x1 players but 1x1 assets.

| Canonical shape | Completed 2026 (N=28) | Completed last 30d (N=12) | Viewed last 30d (N=164) | Viewed Sep 5 (N=15) |
|---|---:|---:|---:|---:|
| 0x0 | 7 / 0 | 2 / 0 | 0 / 0 | 0 / 0 |
| 0x1 | 10 / 2 | 4 / 1 | 17 / 0 | 0 / 0 |
| 0x2 | 0 / 0 | 0 / 0 | 5 / 0 | 0 / 0 |
| 1x1 | 7 / 8 | 3 / 3 | 61 / 67 | 2 / 2 |
| 1x2 | 2 / 6 | 1 / 1 | 24 / 32 | 2 / 1 |
| 1x3 | 0 / 4 | 0 / 1 | 11 / 6 | 1 / 1 |
| 1x4 | 0 / 1 | 0 / 0 | 6 / 4 | 4 / 4 |
| 2x2 | 0 / 3 | 0 / 2 | 27 / 23 | 2 / 2 |
| 2x3 | 1 / 1 | 1 / 1 | 7 / 18 | 1 / 2 |
| 2x4 | 0 / 0 | 0 / 0 | 0 / 4 | 0 / 0 |
| 3x3 | 0 / 1 | 0 / 1 | 6 / 10 | 3 / 3 |
| 3x4 | 1 / 1 | 1 / 1 | 0 / 0 | 0 / 0 |
| 3x5 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |
| 4x4 | 0 / 1 | 0 / 1 | 0 / 0 | 0 / 0 |

The full-month view result is not simply a repeated-card artefact: 172 recorded view events reduce to 164 unique impressions and 146 distinct `(league, trade_hash)` packages. For distinct packages, mean players is 2.87 and 30/146 (20.5%) have three or more players on a side, versus 30/164 (18.3%) impression-weighted. All fifteen September 5 views are distinct packages.

## Served supply, source arms, and policy timing

Generated/served decks are a secondary denominator. Across the month, **6,660 non-ghost served impressions / 1,090 distinct packages** existed, versus **164 recorded viewed impressions / 146 distinct packages**. On September 5, **183 served impressions / 79 distinct packages** existed, versus fifteen views. September 5 served cards averaged **3.37 players**, while viewed cards averaged **4.33**; 68/183 served cards (37.2%) had three or more players on a side versus 9/15 views (60%). This difference is not proof of why cards reached the front: lane choice, deck position, navigation, repeat generation and missing visibility capture can all select the viewed sample.

| Source arm | Sep 5 served | Sep 5 viewed | Viewed ≥3 players either side | Viewed ≥3 players both sides | Mean players/viewed card |
|---|---:|---:|---:|---:|---:|
| challenger | 71 | 7 | 4 | 0 | 4.14 |
| current | 59 | 2 | 1 | 0 | 4.50 |
| gen_v2 | 52 | 5 | 4 | 3 | 5.00 |
| unattributed | 1 | 1 | 0 | 0 | 2.00 |

For the month, recorded views by arm were `current` 31 (mean 2.35 players), `challenger` 45 (2.98), `gen_v2` 16 (4.19), and unattributed 72 (2.78). “Unattributed” is not assigned to a fabricated arm. These small, selected samples do not identify a statistically preferred generator.

Using the supplied September 5 **16:01 UTC** policy transition:

- Before: four viewed impressions stamped `legacy`; mean 4.50 players, three with at least three players on one side.
- After: eleven viewed impressions stamped `personal_market_v1`; mean 4.27 players, six with at least three players on one side.
- The post-boundary views were also served after the boundary. Player-heavy cards already existed before it. **No causal policy comparison is supportable from 4 versus 11 views.**

## Visibility and interpretation limits

1. A `deck_impressions` row records a completed served deck, not that every card was seen. Primary views require an owned `deck_outcomes.action='viewed'` link; each impression is counted once in a window. The mobile event fires after **at least 500 ms** at the front, and current `browseLive` paging deliberately emits neither card-view event. It does **not** cover every trade chip, canvas idea, brief glance or restored display. See [TradesScreen.tsx](../../mobile/src/screens/TradesScreen.tsx) around lines 4055–4129 and [server.py](../../backend/server.py) around 9927–9960.
2. Across these leagues the owner had 7,876 stored impressions; 244 historical ghost rows were excluded. Of 7,632 non-ghost rows, 2,369 lacked `assets_json`; frozen give/receive position arrays supplied the shape fallback. No unknown asset classifications remained. Generic picks use the existing parser; owned picks use the documented league/year/round/original-roster ID format. See [pick_values.py](../../backend/pick_values.py) and [impression schema/writer](../../backend/database.py), [server writer](../../backend/server.py) around 4682–4880.
3. Legacy `trade_impressions` “shown” terminology and `suggestion_trade_links.was_recommended` do not prove viewing; the latter matches non-ghost serve records without a viewed requirement. Neither was used as the primary exposure denominator. [suggestion_telemetry.py](../../backend/suggestion_telemetry.py)
4. Completed trades have independent player, pick and FAAB fields. The completed filter is `type=trade,status=complete`; picks move `previous_owner_id → owner_id`, while pick `roster_id` is original ownership. Current owner/co-owner membership establishes the owner-involved cohort; historical manager replacements are not independently audited. [sleeper_trades_service.py](../../backend/sleeper_trades_service.py), [sleeper_roster.py](../../backend/sleeper_roster.py)
5. This compares distributions, not exact suggestion-to-completion conversions. There is no rejection opportunity denominator for unshown packages, no random assignment, and no causal acceptance-rate estimate. No installed build number or missing historical impression linkage is invented.

## Minimal follow-up to review, not implemented

Limit any change to **automatically generated deck presentation among already market/intent/roster-eligible cards**. A stable, bounded preference for fewer **players** could improve the initial reading burden while keeping larger packages available. Do not count picks as interchangeable with additional players for this complexity preference.

Preserve explicit send/receive selections and calculator/fair-package requests; preserve all current/challenger/gen_v2 candidate math, profiles and source attribution. Keep fixed special-card semantics, current market floors, intent classification, Core/Conviction composition and relevant arm/lane slot constraints. Do not silently replace selected assets, introduce a zero-result hard cap, or remove the legitimate historical 3x4 case.

The reviewable seam is the final eligible presentation order before impression serialization: [server.py](../../backend/server.py) `_evaluate_deck_policy` around 5451–5557 and [trade_policy.py](../../backend/trade_policy.py) `compose_deck` around 1035. The existing policy ranks by personal opportunity and mutual surplus, not player complexity; that is a code fact, **not proof larger packages caused the measured ordering**. Existing first-session shaping is not a general solution: it considers simple shapes only on the first deck and explicitly bypasses fixed bakeoff ordering. [server.py](../../backend/server.py) around 6523–6600 and 7549–7583; [bakeoff_runner.py](../../backend/bakeoff_runner.py) Channel 2 contract.

Any presentation adjustment must explicitly reconcile that fixed-order contract and frozen ranking/position telemetry; a global sort would not be a safe drop-in. Review scope should name the bounded movement rule and tests rather than infer a cap or movement budget from this sample. Minimum tests: eligibility/selected-package invariance; all source arms retained; picks-heavy controls unaffected; larger-only supply remains available; stable survivor ordering and duplicate handling; actual served-order/attribution snapshot agreement; unchanged baseline arm goldens. Main trade-off: simpler early cards can delay a higher-gain larger card, so preserve access and measure exposure after rollout.

## Reproduction artifacts

Outside Git, in the task workspace:

- `trade_shape_research.py`: parameterized owner resolution, allowlisted read-only SQL, public current-league/roster/leg reads, asset classification, cohort definitions and aggregation. Default mode performs the fresh public sweep; `--stored-details` explicitly uses the already-verified stored corpus without claiming a new transaction sweep.
- `trade-shape-aggregate.json`: original fresh-public-run sanitized result, including all 57-leg coverage checks.
- `trade-shape-detail-aggregate.json`: supplemental pure-player/pick/mixed and September 5 arm breakdown from the identical stored corpus.

No raw owner/league/player identifiers or private board values were written to this report or either aggregate. Counts were verified to reconcile across shape distributions, composition buckets, source-arm totals and the repeated-view reduction. No runtime code changed and no tests/deployment are claimed by this research.
