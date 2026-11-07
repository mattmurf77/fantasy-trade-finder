# Forecast contract and accuracy boundaries — 2026-11-07

The candidate now implements **common offense only** under `sleeper_sparse_offense_v1`; strict supplied-event mode remains supported. The model/policy/provider gates remain off. Weekly scheduling and all existing trade-model behavior are unchanged.

## Admission and provenance

The backend controls the provider adapter. It requires the observed RotoWire `company=rotowire`, `category=proj`, matching regular-season/week/game identity, native offensive eligibility, numeric `gp=1`, and finite substantive offensive inputs. A missing row, placeholder, missing reconciliation total, wrong source, or failed identity is unavailable rather than zero. `gp=1` denotes the provider's scenario, not verified health.

The finite model covers pass yards/TD/interception/two-point, rush yards/TD/two-point, reception count/yards/TD/two-point, and fumbles lost. Direct values always survive, including trick-play passing by a receiver. On admitted rows only, absent members of this finite set receive an explicitly model-assumed zero. There is no prefix rule, arbitrary coefficient override, or row-wide fill.

Admission reconciles STD/half-PPR/PPR totals with `.04*pass_yd + 4*pass_td - pass_int + 2*(pass_2pt+rush_2pt+rec_2pt) + .1*(rush_yd+rec_yd) + 6*(rush_td+rec_td) - 2*fum_lost + reception_rate*rec`. Returns are excluded from this diagnostic formula; any active custom return scoring remains required separately. The observed two-decimal bound is `.005*(1+sum(abs(coefficient) for directly supplied formula fields))`. Inputs with unexpected precision are rejected. This is an empirical source interpretation, not an official provider contract.

Finite existing `POSITION_BONUSES` derive expected receptions/TDs using **native primary position**, not dual fantasy eligibility. Unknown primary position stays missing. Native FB/DB retain their own identities. For an FB with RB fantasy eligibility or DB with WR eligibility, a missing corresponding premium remains unknown and a supplied premium is preserved; no alias premium is derived or contradicted by an invented zero. A TE premium is inapplicable only when neither primary nor fantasy eligibility is TE. Contradictory supplied bonuses fail. Finite kicker/team-defense coefficient registries are inactive only when their lineup domain has no slot. Special teams, miscellaneous fumbles, IDP and unknown fields remain active. Missing field-goal misses may be derived from supplied `fga-fgm`; negative inconsistencies fail, and missing distance bands are never invented.

Each consumed field records value and basis (`direct`, `derived`, `model_assumed`, `inapplicable`, `missing`) plus method. Immutable snapshots retain row-level provenance and source hashes; exported manifests enumerate assumed-zero keys and all per-key provenance counts. A coefficient can amplify input uncertainty; aggregate residual bounds do not bound arbitrary custom scores or assumed omitted-event error.

## Evidence

Development weeks9–14: 2,361 native-eligible offensive player-week rows ×3 totals, no declared-bound violations, maximum residual0.077. Independent withheld weeks15–18: 1,783 rows ×3 totals, no bound violations, maximum0.080; **65 additional offensive rows lacked each aggregate and are not admitted**. See [development](decoder-development.json) and [held-out identity results](decoder-holdout.json). This is decoding evidence, not future prediction accuracy. The application contract is stricter than the formula-only research decoder and is evaluated separately.

The broader kicker candidate failed4 held-out rows per aggregate (maximum0.17). Its missing bands are not admitted. Generic IDP totals constrain only a narrow five-event formula and do not validate the full custom IDP schema. These research candidates are not app fallback rules. The reference league's rare IDP/return requirements and incomplete kicker projections remain explicit gaps.

A separately explored player/position shrinkage model for rare events trained on2026 weeks1–5 and evaluated weeks6–8:6,136 covered active player-games,131 no-history abstentions. No tested rare event improved MSE over zero. It was **not promoted**, and this result does not prove those events have zero expected value. [Aggregate experiment](historical-rate-development.json).

The historical-source audit found all2,978 populated2025 projections in weeks4/8/12 were revised at or after kickoff. These retrieved historical rows cannot establish pregame accuracy. [Audit](historical-source-audit.json). Leakage-free forecast calibration still needs contemporaneous saved inputs and later outcomes. No playoff/draft accuracy, complete reference-run support or original prototype parity is claimed.

## Application amendment after holdout inspection

Native-primary position bonus review found16 FB/fantasy-RB and4 DB/fantasy-WR rows whose TE premium is inapplicable under the explicit primary-position rule. The final finite registry recognizes FB/DB without mapping their premiums to RB/WR. Follow-up review also preserves unknown/supplied alias premiums rather than assuming them zero. This deterministic bonus-policy amendment was made **after** inspection of the held-out data; it is not represented as an untouched holdout test of that new bonus policy. The original common-offense formula did not change. Four RB rows supplied a contradictory nonzero TE bonus and remain rejected; the model does not tune or absorb that residual.

## Mean-preserving joint policy — corrected engine v3

The initial v2 floor preserved dominance but raised the requested Max PF mean. Disclosure did not satisfy the specification's mean contract. It is superseded by `joint-season-scenario-v3` with `mean_preserving_positive_gap_v1`; old numeric results remain dated/attributed and are never reused as v3 output.

Let actual mean be A, requested Max PF mean M, residual scales sa/sm and latent residual correlation rho. The shared persistent team strength cancels in the gap. Its residual scale is `s = hypot(sa-sm, sqrt(2*sa*sm*(1-rho)))`. For nonnegative target gap `delta=M-A`, solve `s*phi(g/s)+g*Phi(g/s)=delta` for the latent gap mean g, once per team/week. Shift the existing correlated latent Max PF draw by `g-delta`, then floor at actual. This preserves the **unrounded expected** Max PF mean M while retaining dominance. Actual Gaussian scores, random draw consumption, seed, matchups and playoff-membership calculation remain unchanged.

A zero target gap requires Max PF=actual in every world; there is no finite latent normal mean for that singular case. A zero gap scale gives a deterministic positive gap. Any negative target gap is rejected when dominance is required. Hypothetical replacement cases that do not require dominance keep the original unconstrained correlated normal. No correlation tuning or forecast-source change is introduced.

The floor transforms variance/correlation, so configured latent parameters are not labeled as realized parameters. Advanced diagnostics and the manifest expose target, latent and simulated means; latent parameters; analytic and sampled realized variance/correlation; uplift **relative to the shifted latent draw**; floor frequency; simulation-mean standard error; and rounding bound. Centered moment accumulation avoids high-location cancellation, and the analytic gap variance avoids subtracting large squared means. The zero-gap branch reports no latent mean rather than inventing one.

With nearest score rounding, expected means can differ by at most half a scoring unit per week (0.005 at two decimals), plus Monte Carlo sampling error in a finite run. Exact sampled-mean equality is not claimed. This is a mathematical mean-contract correction, not predictive calibration or evidence that the selected uncertainty model is accurate. UI shows requested target versus simulated average and keeps technical diagnostics expandable. Saved-input weight comparisons require a baseline from the current engine, preventing a disguised simultaneous model change. Opening an old result does not enqueue a replacement. Queue admission freezes expected engine/baseline versions server-side; every worker admission and recovery rechecks them plus the owned baseline version. Old or unversioned queued work fails rather than silently migrating after deployment.

## Primary-source boundary

Observed [projection response](https://api.sleeper.app/projections/nfl/2026/10?season_type=regular), [official scoring categories](https://support.sleeper.com/en/articles/3998131-what-scoring-options-are-available), and [official API documentation](https://docs.sleeper.com/), checked2026-11-07UTC. The projection endpoint/formula is undocumented; the later user instruction authorizes best-available current-source use without another purchase/permission decision. Existing Sleeper integrations are unaffected. No source fallback, production activation, outreach or private league payload publication occurred.

## Best-available continuation — engine v4

The finite common-offense identity evidence above remains historical evidence for that decoder, not validation of every partial custom score. The selected policy now uses known raw contributions and exposes incomplete rows/coefficients. Known completed actuals and feasible Max PF assignments condition current-week outputs explicitly; future-only v3 arithmetic and RNG paths are unchanged. See implementation.md and current evidence.md.
