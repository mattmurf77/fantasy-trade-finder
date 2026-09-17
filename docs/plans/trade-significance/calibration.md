# Frozen-review calibration — 2026-09-17

## Evidence and method

100 exact recorded owner_v1 recommendations: first 50 distinct ownership-valid packages from one full FFv3 deck and one full Newton Dynasty deck, in original order. This is a convenience sample from two jobs, not all leagues, random sampling, or newly generated offers. Original production source: 62ba9b3d22d804153a12b34a6e84c73ce0282521. Original review remains untouched.

32 recorded dispositions (all FFv3): 16 Yes, 16 No, no detailed reasons. They represent willingness to consider the package, not an independently labeled significance judgment. The owner's qualitative observation is that many packages are too trivial.

Calibration reads the exact frozen raw seed_elo, user_elo, user_sources, scoring_format, and player metadata from the two original bakeoff_runs.config_json.owner_request.input snapshots. Scoped retrieval forced PostgreSQL transaction_read_only=on. The offline replay imports the new pure evaluator and extracts the existing pure owned-pick parser without server startup. No live board substitutions, inversion of age-adjusted package values, product feedback writes, or ranking mutations.

Private input snapshots and review feedback are local research artifacts and are not committed. The research directory is trade-review-r1 under this task's visualization directory; it now also preserves significance-frozen-inputs.private.json (mode 0600, not served by the review app). The local replay entry point is /private/tmp/significance_replay.py, with frozen-input scratch at /private/tmp/significance-frozen-inputs.private.json. These paths are local evidence, not a deployment dependency. Replays resolve each review card's deck_job_id to the corresponding frozen input, pass raw boards/player metadata into evaluate_significance, and count retained cards by league and recorded disposition.

## Results

| Minimum individual player tier (viewer OR consensus) | FFv3 retained / 50 | Newton retained / 50 | Yes retained / 16 | No retained / 16 |
|---|---:|---:|---:|---:|
| 1st-round equivalent | 13 | 44 | 3 | 1 |
| 2nd-round equivalent | 33 | 46 | 11 | 5 |

Allowing an actual first-round pick to independently qualify makes no difference in this sample: those trades already contain a qualifying player. Tests must establish the independent pick behavior; these observations do not validate its effect on other packages.

The proposed second-tier rule removes 21/100 overall, including 16/32 reviewed cards. Removed reviewed Yes cards:

- F06: 2028 4th for Alvin Kamara.
- F08: Ty Simpson for Kaleb Johnson.
- F10: Justin Fields for Kaelon Black.
- F22: Ty Simpson for Jaylen Wright.
- F25: 2028 4th for Adam Randall.

These are deliberate examples for owner calibration, not relabeled user declines. No acceptance-rate claim or statistical significance claim is warranted. Newton has no recorded dispositions in this batch and nearly all its cards already meet either threshold; do not claim this change resolves every problem in that league.

## Release implication

Implement with mode off by default and threshold second as the proposed setting. Before enforcement, inspect these removed Yes examples and a broader fresh two-league sample. A low-value floor can remove obvious noise but cannot prove usable lineup improvement, fair price, diversity, or counterparty willingness; retain the existing engine checks and continue the interview exercise after deployment.

The first-tier proposal is substantially more aggressive for FFv3 and is not the implementation default. No threshold is activated by this document.
