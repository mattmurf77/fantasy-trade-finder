# Three-model evaluation — September 22, 2026

## Decision

**Keep `owner_v2_bilateral` as the leading development candidate, not a proven acceptance winner.** In this frozen tanking-team case it best combines small packages, RB selling and the owner's known player preferences. Prioritize its price/consideration efficiency and post-filter repetition. Keep `owner_v1` as a comparator; investigate `fit`'s pick opportunities without restoring its large-package default.

The strict framework verdict is **evidence-limited for all three models**. No model has established two-sided acceptance, passed a ratified release gate, or earned a defensible overall numerical grade. This distinction is deliberate: the evaluator does not award a pass because the generator says its own trade is good.

The next actions are in the [model-revision plan](model-revision-plan.md). Machine-readable, identity-free aggregates are in [comparison-summary.json](comparison-summary.json).

## What was actually compared

| Constructor | Retained source version | Introduction commit |
|---|---|---|
| `owner_v2_bilateral` | `owner-v2-bilateral-1` | `4913ad0c`, September 20 |
| `owner_v1` | `owner-v1` | `0e3d6b70`, September 6 |
| `fit` | `fit-1` | `c6e6c3c0`, August 20 |

These are the three most recently introduced constructor families verified in Git. The September 21 first-action publication release is not a fourth model. We replayed their retained implementations from source base `73bfa41e358e8780b823f652cf8388ae209b977d`, not their original historical deployment binaries.

All three received the same frozen September 19 request and separately captured configuration. This is **one 1QB/PPR, tanking-team request against 13 counterparties**, not thousands of independent owner decisions. It contains a 580-player reference universe, an initiating-owner board with source provenance, and **no personal boards for any of the 13 counterparties**. The request also declares RB/TE acquisition interests: RB receipts are a tension to examine, not automatically a violation of an explicit user choice. The [identity-free context summary](comparison-context.json) records those facts. The replay adapter uses an ESPN league wrapper; the frozen constructor input does not include a platform field, so this run does not validate platform-specific data preparation.

The common config was read back at `2026-09-22T01:36:44.936974Z` during prior planning. That timestamp is provenance, not a fresh production-status check in this implementation run. Reference prices are reconstructed from the frozen seed using that common configuration, not asserted to be the exact historical served price. **Market publication/as-of dates are unavailable**: this is a captured-input cross-sectional diagnostic, not a historical market-freshness backtest. Normalized snapshot identity binds both. Constructors were invoked offline even if excluded from that serving configuration. No arm was enabled, disabled or deployed.

Four separate stages were evaluated: native full output, native first 30, full output after a common independent significance projection, and that projection's first 30. The projection checks individual player significance or a syntactically identified first-round pick. **It is not the complete live legality, pick-ledger, deduplication or serving-policy pipeline.** Full validated pick ownership/expiry evidence is absent. “First 30” is an evaluation lens, not a cap on generated offers.

## Results at the first 30 post-significance positions

These are descriptive package characteristics, not acceptance grades. Counts can overlap.

| Characteristic | Bilateral | Owner-v1 | Fit |
|---|---:|---:|---:|
| Small packages: 1-for-1, 1-for-2 or 2-for-1 | 30/30 | 30/30 | 0/30 |
| Outgoing RB included | 23/30 | 0/30 | 12/30 |
| Incoming RB included | 1/30 | 26/30 | 10/30 |
| Incoming first included | 13/30 | 9/30 | 29/30 |
| Distinct outgoing headliners | 5 | 3 | 4 |
| Most repeated outgoing headliner | 17/30 | 16/30 | 12/30 |
| Mean unadjusted reference return relative to amount sent | −24.8% | −3.9% | −19.5% |

“Headliner” here means the highest captured consensus-rated outgoing asset, not the user's favorite player. The raw return is the per-offer mean of `(receive reference − give reference) / give reference`; it is **not stud-adjusted**. It cannot establish that an offer is unfair or estimate acceptance. It does identify a pricing question: why do bilateral's earliest selected offers concentrate on materially negative raw returns, and are cheaper equally suitable terms available? Proper compensation bands and two-manager context must decide that.

### Personal-player direction, with coverage attached

All figures below describe manager A only. They are equal-offer averages of known focal-player hit rates, not observed likes. A “hit” buys above-market personal preference or sells below-market personal preference using the independent tier/order coordinate.

| Metric | Bilateral | Owner-v1 | Fit |
|---|---:|---:|---:|
| Outgoing focal sell hit rate | 98.3% (30 cards with known focal evidence) | 81.7% (30) | 100% (30) |
| Incoming focal target hit rate | 97.1% (17 cards with known focal evidence) | 81.3% (24) | 78.3% (30) |
| Mean known-personal value coverage, outgoing | 100% | 100% | 61.3% |
| Mean known-personal value coverage, incoming | 56.7% | 75.0% | 51.4% |
| Known favored outgoing player occurrences | 0 | 6 | 0 |
| Known disfavored incoming player occurrences | 0 | 16 | 9 |

Incoming pick-only sides account for much of bilateral's ungraded player-preference coverage. Picks are not assigned invented personal rankings. Fit's 100% outgoing hit rate is not a complete-package win: substantial outgoing value is unranked. Counterparty personal coverage is **0% across all models**; consensus fallback never becomes evidence of B's conviction.

## Generator versus presentation findings

| Native output characteristic | Bilateral | Owner-v1 | Fit |
|---|---:|---:|---:|
| Unique cards within each model | 2,843 | 2,103 | 106 |
| Retained by common significance projection | 2,383 (83.8%) | 1,854 (88.2%) | 106 (100%) |
| Small package share | 100% | 100% | 6.6% |
| Incoming first share | 31.8% | 42.3% | 80.2% |
| Incoming RB share | 7.2% | 26.2% | 49.1% |
| Outgoing RB share | 62.7% | 53.2% | 57.5% |

- **Construction:** bilateral's whole inventory has many RB sales and few RB receipts, but 460 native offers do not meet the projected significance rule. It has more incoming-first cards in absolute count than owner-v1 (905 versus 889), but a lower share. Counts alone do not measure useful pick opportunity recall.
- **Ranking:** owner-v1's inventory contains 1,118 RB-sale offers, yet none appear in its first 30 after significance. Its weakness here is not simply an inability to construct those trades; prioritization must be examined.
- **Post-filter ordering:** bilateral has six outgoing headliners in the native first 30, with one repeated 11 times. The significance projection leaves five headliners in the first 30 and increases the maximum repetition to 17. A quality filter can improve significance while making the visible sequence more repetitive. Fix ordering on the survivors, not solely inside the constructor.
- **Fit:** every early card is 3-for-3. High first-round inclusion does not outweigh package complexity or establish willingness. Its useful contribution to study is whether it finds pick transactions the smaller search misses, after reducing them to independently coherent small alternatives.

Native constructor timings in this local run were 5.649s / 3.336s / 6.119s respectively. Different built-in search budgets and output counts remain; this is neither an equal-compute speed comparison nor a device three-second KPI test. It excludes preparation, evidence persistence, network and rendering, and ran alongside other local validation.

## Six-dimensional verdict, independently for both managers

All A-give, A-receive, A-package, B-give, B-receive and B-package cells exist in the private scorecard. No opposing side was copied from the initiating manager. For the first 30 after the projection, **all six bilateral grade rows are evidence-limited for all three models**:

| Dimension | Useful evidence now | What prevents a verified bilateral pass |
|---|---|---|
| Fairness | Raw reference costs, shape, known personal direction | No independent exact-package acceptability annotations or mature two-sided outcomes; raw equality is not the target |
| Outlook | Selected tanking intent, directional RB/pick portfolio mix | No independently adjudicated exception/portfolio rubric on these exact offers; incomplete age/validity evidence |
| Team needs | Frozen roster and platform facts | No complete actual starter-slot/projection/cut evidence. Tanker's immediate starter gain is N/A; its overall roster fit is not automatically passed |
| Personal rankings | Strong descriptive A-player targeting evidence | No B boards; picks and other unknown personal entries remain unknown; direction alone is not a complete contextual grade |
| Meaningful packages | Individual tier significance and package size | A qualifying centerpiece does not establish benefit to both managers; pick-ledger validity and independent contextual annotations remain incomplete |
| Stud tax | Raw consideration and strongest-asset data | No independent exact-term compensation band or reviewed exemption evidence |

The full native scorecard also exposes known low-significance failures where evidence permits. Unknown does not mean the model is bad, and absence of a verified pass is not a recommendation to turn off serving. It means the current evidence cannot support the promised claim.

## What this does not prove

No accepted-trade/like rate was manufactured. No app mutual-match or completed-trade comparison was possible from this request-only capture. Existing KTC/Sleeper research is useful for a future pricing/shape panel but cannot retroactively label these generated offers as accepted or rejected. No causal confidence interval is justified by one request; 5,052 generated cards are not 5,052 independent trials. No cross-platform, contender, superflex, two-board, or high-load conclusion follows from this case.

The next benchmark must add real independent contexts, both-board and sparse-board cohorts, all outlooks, scoring/league sizes, complete input provenance and mature outcomes. Until then the development preference for bilateral is conditional, based on the measured owner-direction/shape fit—not an overall grade.

## Reproduction and retained evidence

Run from the implementation worktree with the pinned fixture paths shown in [validation](validation.md). The scratch replay blocks network and creates a new private SQLite database, never using the production DB. Original input artifacts are local private files; do not commit or publish them.

- Input capture SHA-256: `e64f8267958dc56826e24f470d46056414cdf99dd1e0be66d7e958c276223b22`.
- Configuration capture SHA-256: `95b9b8597cf0dacfa609bb665b5c79a381492b1eabba099d62b06ccd761be22c`.
- Per-source-file and evaluator hashes, model versions, stage aggregates and normalized-manifest hash are retained in `comparison-summary.json`.
- Full local result directory: `/private/tmp/fleeced-scorecard-run-20260922-final/`; private manifest and detailed source context stay there.

No production data, flags, users' rankings, recommendations or deployments were changed to produce this report.
