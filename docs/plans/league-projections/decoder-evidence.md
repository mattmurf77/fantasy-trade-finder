# Forecast contract and accuracy boundaries — 2026-11-07

The candidate now implements **common offense only** under `sleeper_sparse_offense_v1`; strict supplied-event mode remains supported. The model/policy/provider gates remain off. Weekly scheduling and all existing trade-model behavior are unchanged.

## Admission and provenance

The backend controls the provider adapter. It requires the observed RotoWire `company=rotowire`, `category=proj`, matching regular-season/week/game identity, native offensive eligibility, numeric `gp=1`, and finite substantive offensive inputs. A missing row, placeholder, missing reconciliation total, wrong source, or failed identity is unavailable rather than zero. `gp=1` denotes the provider's scenario, not verified health.

The finite model covers pass yards/TD/interception/two-point, rush yards/TD/two-point, reception count/yards/TD/two-point, and fumbles lost. Direct values always survive, including trick-play passing by a receiver. On admitted rows only, absent members of this finite set receive an explicitly model-assumed zero. There is no prefix rule, arbitrary coefficient override, or row-wide fill.

Admission reconciles STD/half-PPR/PPR totals with `.04*pass_yd + 4*pass_td - pass_int + 2*(pass_2pt+rush_2pt+rec_2pt) + .1*(rush_yd+rec_yd) + 6*(rush_td+rec_td) - 2*fum_lost + reception_rate*rec`. Returns are excluded from this diagnostic formula; any active custom return scoring remains required separately. The observed two-decimal bound is `.005*(1+sum(abs(coefficient) for directly supplied formula fields))`. Inputs with unexpected precision are rejected. This is an empirical source interpretation, not an official provider contract.

Finite existing `POSITION_BONUSES` derive expected receptions/TDs using **native primary position**, not dual fantasy eligibility. Unknown primary position stays missing. Explicitly recognized native FB/DB remain their own primary identities: neither inherits RB/WR premiums from fantasy eligibility. Contradictory supplied bonuses fail. Finite kicker/team-defense coefficient registries are inactive only when their lineup domain has no slot. Special teams, miscellaneous fumbles, IDP and unknown fields remain active. Missing field-goal misses may be derived from supplied `fga-fgm`; negative inconsistencies fail, and missing distance bands are never invented.

Each consumed field records value and basis (`direct`, `derived`, `model_assumed`, `inapplicable`, `missing`) plus method. Immutable snapshots retain row-level provenance and source hashes; exported manifests enumerate assumed-zero keys and all per-key provenance counts. A coefficient can amplify input uncertainty; aggregate residual bounds do not bound arbitrary custom scores or assumed omitted-event error.

## Evidence

Development weeks9–14: 2,361 native-eligible offensive player-week rows ×3 totals, no declared-bound violations, maximum residual0.077. Independent withheld weeks15–18: 1,783 rows ×3 totals, no bound violations, maximum0.080; **65 additional offensive rows lacked each aggregate and are not admitted**. See [development](decoder-development.json) and [held-out identity results](decoder-holdout.json). This is decoding evidence, not future prediction accuracy. The application contract is stricter than the formula-only research decoder and is evaluated separately.

The broader kicker candidate failed4 held-out rows per aggregate (maximum0.17). Its missing bands are not admitted. Generic IDP totals constrain only a narrow five-event formula and do not validate the full custom IDP schema. These research candidates are not app fallback rules. The reference league's rare IDP/return requirements and incomplete kicker projections remain explicit gaps.

A separately explored player/position shrinkage model for rare events trained on2026 weeks1–5 and evaluated weeks6–8:6,136 covered active player-games,131 no-history abstentions. No tested rare event improved MSE over zero. It was **not promoted**, and this result does not prove those events have zero expected value. [Aggregate experiment](historical-rate-development.json).

The historical-source audit found all2,978 populated2025 projections in weeks4/8/12 were revised at or after kickoff. These retrieved historical rows cannot establish pregame accuracy. [Audit](historical-source-audit.json). Leakage-free forecast calibration still needs contemporaneous saved inputs and later outcomes. No playoff/draft accuracy, complete reference-run support or original prototype parity is claimed.

## Application amendment after holdout inspection

Native-primary position bonus review found16 FB/fantasy-RB and4 DB/fantasy-WR rows whose TE premium is inapplicable under the explicit primary-position rule. The final finite registry recognizes FB/DB without mapping their premiums to RB/WR. This deterministic bonus-policy amendment was made **after** inspection of the held-out data; it is not represented as an untouched holdout test of that new bonus policy. The original common-offense formula did not change. Four RB rows supplied a contradictory nonzero TE bonus and remain rejected; the model does not tune or absorb that residual.

## Joint-model diagnostics

Engine revision `joint-season-scenario-v2` reports each week's input Max PF mean, sampled pre-floor mean, sampled achieved mean, mean uplift and floor frequency. Enforcing Max PF≥actual scores can increase the marginal mean substantially; equal20-point independent normals with residual variance157.14 yield about7.07points/week uplift. The UI explains and quantifies this effect. Correlation was not tuned to hide it. Draft probabilities remain conditional model scenarios, not calibrated estimates. Model revision enters reuse hashes, so older result JSON cannot bypass new diagnostics.

## Primary-source boundary

Observed [projection response](https://api.sleeper.app/projections/nfl/2026/10?season_type=regular), [official scoring categories](https://support.sleeper.com/en/articles/3998131-what-scoring-options-are-available), and [official API documentation](https://docs.sleeper.com/), checked2026-11-07UTC. The projection endpoint/formula is undocumented; commercial permission evidence remains a new-capability activation gate. Existing Sleeper integrations are unaffected. No source fallback, production activation, outreach or private league payload publication occurred.
