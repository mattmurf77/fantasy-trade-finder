# Metric registry — implementation draft 1

Authoritative product rubric: [reviewed scorecard](../plans/model-evaluation-framework/scorecard-spec.md). Code: `backend/eval/scorecard_dimensions.py`, `scorecard_outcomes.py`, `scorecard_runner.py`. All coordinate/grade contracts are versioned. This registry does not ratify empirical pass-rate targets.

## Dimensional metrics

| ID | Independent raw evidence | Grade evidence / limit |
|---|---|---|
| `fairness` | Give/receive raw reference totals and net cost, personal/plan context, independently judged terms | Market equality is not willingness. Contextual grades require exact-term/snapshot-bound independent review; behavioral labels reported separately |
| `outlook` | Selected/inferred authority, incoming/outgoing pick/RB shares, evidenced youth, own next-draft pick, explicit exceptions | Missing youth classification/outlook is unknown. Tanking-own-next-pick contradiction is explicit; nuanced RB/portfolio benefits require reviewed context |
| `team_needs` | Independent legal before/after lineup assignment from real points, availability, slots and cuts | No dynasty-value-as-points. Missing rules/projections/cuts unknown; tanking immediate-start submetric N/A; net benefit and new holes distinct |
| `personal_ranks` | Signed tier then within-tier order gaps; incoming hits/outgoing relief, focal/full-package coverage and sacrificed favored assets | Same comparable universe, explicit provenance; missing B board never becomes consensus conviction. Gap coordinate is a draft measurement, not constructor weights |
| `meaningful` | Individual second-round tier or valid first, centerpiece value, filler/shape; benefit by manager | No sum of scraps qualifies. Presence alone is not both-party benefit. Explicit contexts and unsupported pick identity remain separate |
| `stud_tax` | Best asset/seller, raw return versus independently bound compensation band | Missing band = Unknown; no universal premium or duplicated crown/fit tax. First-round exemption needs independent review |

Every manager has give/receive/package assessments containing raw features, grade (0–4 or null), known/unknown/N/A, reasons and source evidence. Independent annotations bind exact terms and snapshot; synthetic annotations only apply to synthetic inputs. A known failing side must not be hidden by another side's high grade or missing evidence. All published aggregates preserve grade/status distributions, not just mean scores.

## Outcome and temporal metrics

The outcome reducer requires verified identity, timestamped events, actual expiry, frozen origin, observation coverage and an explicitly supplied eligible cohort. It does not reconstruct missing production eligibility from future actions.

- Primary: distinct valid mutual concepts / fixed pre-assignment eligible manager-league windows. No-request, empty and failed searches remain. One origin per concept; shared/unknown/carry-in explicit.
- Valid mutual milestone: overlapping active interests while exact terms are valid. Later withdrawals/cancellations do not erase history; nonoverlapping likes never count.
- Diagnostics: request/episode conversion; responder-only like share; observed exposure conversion; counterpart exposure/lag; confirmation; supported exact completion. Silence is operational nonconversion only with complete follow-up, never a negative preference label.
- Promotion guardrails: mature post-milestone reversals/confirmation, retained historical concepts per original cohort, coverage and remaining validity. Expiry is not an explicit rejection. Follow-up does not extend production validity.
- Probability calibration: literal event/population/horizon required. Responder-only calibration cannot claim general willingness. No fitted predictor is supplied by this implementation.

The runner reports missing cohort outcomes as Unknown and remains insufficient-evidence for promotion. `cluster_mean_interval` computes reproducible equal-cluster descriptive bootstrap intervals from caller-supplied independent cluster summaries, not generated cards. One cluster yields no interval. Power/MDE and valid experimental assignment remain preregistered analysis work.

## Model versus policy

Record native output, each audited policy boundary and displayed order separately. Rank cuts (1/5/10/30/full) are evaluation views, never production caps. Report removed-good opportunity yield/recall only where independent good/bad labels exist in the audited candidate universe; do not invent exhaustive recall. A significance-only replay is not the full serving pipeline.

## Change control

Rubric, feature coordinate, label semantics or source adapter changes get a version and bridge run on frozen incumbent inputs. Never change thresholds to rescue a favored challenger. Required promotion thresholds remain unratified until an independent baseline and signed decision record exist.
