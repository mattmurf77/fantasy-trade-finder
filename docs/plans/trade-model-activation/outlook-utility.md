# Whole-team outlook utility

Implemented as a pure component on 2026-09-04. Shared wiring, feature flags,
activation scope, ranking and deployment belong to the main agent. This document
describes this component, not evidence of deployed behavior or acceptance uplift.

## Integration API

`backend.trade_outlook_utility.evaluate_outlook_utility` accepts keyword arguments:

```python
evaluate_outlook_utility(
    before: trade_roster.Team,
    after: trade_roster.Team,
    assets: Mapping[str, trade_roster.Asset],
    rules: trade_roster.Rules,
    explicit_outlook: str | None = None,
    inferred_outlook: str | None = None,
    inference_fresh: bool = False,
    projections: Mapping[str, float] | None = None,
    projection_basis: str | None = None,
    projection_unit: str | None = None,
    projections_fresh: bool = False,
) -> dict
```

The result is JSON serializable, with this ranking contract:

| Field | Meaning |
|---|---|
| `normalized_gain` | Float in [-1, 1], or `None` when no weighted component can be measured. Positive is improvement for this manager. A partial dynasty contribution is not evidence of positive current production. |
| `confidence` | [0, 1] evidence weight, **not** a calibrated probability of correctness or acceptance. The ranking consumer may attenuate the gain with it; it has not already been multiplied into the gain. |
| `basis` | `projected_production_and_dynasty`, `dynasty_only`, or `unavailable`. |
| `ready_for_enforcement` | True only with usable fresh, complete projections, explicit manager outlook, observed slots, known availability and no input uncertainty/duplicates. This is measurement readiness, not trade eligibility. |
| `components` | `current_production`, `future_assets`, `lineup_dynasty_proxy`, `depth`; each carries before/after/delta, normalized gain, normalization scale, unit and scoring weight. Unavailable quantities are null. |
| `outlook` | Resolved `value`, `source`, `confidence`, `reason`, `uncertainties`. |
| `reason`, `uncertainties` | Explanation of the basis and missing or unreliable evidence. |

Attach one result to **each manager's** existing roster result:

```python
from dataclasses import replace
from backend.trade_outlook_utility import evaluate_outlook_utility

after_ids = (set(team.roster) - set(outgoing)) | set(incoming)
after_ids -= set(resolved_cuts)
after = replace(team, roster=tuple(sorted(after_ids)))
# If reserve/taxi status changes, supply that actual after.inactive state too.
team_result["outlook_utility"] = evaluate_outlook_utility(
    before=team, after=after, assets=context.assets, rules=context.rules,
    explicit_outlook=manager_declared_outlook,
    inferred_outlook=manager_inferred_outlook,
    inference_fresh=inference_inputs_are_fresh,
)
```

`before` and `after` must be complete rosters for the same manager, including
owned picks, retained bench players and inactive assets. Supply actual cuts and
after-trade inactive changes; this function neither invents cuts nor simulates
ownership. Existing `Team.outlook` is deliberately ignored: its default and
adapter representation cannot distinguish explicit intent from inferred or
missing intent. Resolve the caller and opponent independently. Do not reuse the
caller's outlook for the opponent or pass a provenance-free resolved string as
`explicit_outlook`.

`resolve_outlook(explicit=..., inferred=..., inference_fresh=False)` is also a
public pure helper. Explicit `championship`, `contender`, `not_sure`, `balanced`,
`rebuilder`, `jets` wins, including explicit uncertainty. `not_sure` becomes
`balanced`. Fresh inference has confidence 0.5 and cannot select the extreme
championship/jets weights. Absent, stale or invalid inference falls back to
balanced at 0.25 confidence and is never ready for enforcement. An invalid
explicit value also stays conservative rather than being replaced by inference.

The main agent's current worktree integration uses
`trade_roster.Context.utility_inputs[manager_id]` to pass these keyword arguments
and attaches the result in `Context._add_benefits`. The worker preserves the
viewer's explicit preference before inference and supplies declared opponent
preferences independently. No live projections are supplied. The authorized
rollout posture is collection only with the strict flag dark; this component
does not flip flags or deploy. The example above also shows how a future caller
with explicit cuts must construct the after roster.

### Strict gate versus shadow ranking

**Missing projections always mean `ready_for_enforcement=False`.** So do
inferred/missing intent, duplicate roster IDs and uncertain roster observations.
Keep fallback values for rank-only shadow diagnostics. A strict two-sided utility
gate may run only when **both** attached manager results have
`ready_for_enforcement is True` and finite non-null gains. If either is unready,
skip that utility gate; do not turn `None` into zero, reject a trade for missing
evidence, or treat a dynasty proxy as a measured current-season improvement.

Utility never returns or changes `eligible`, `status` or `blockers`. Continue
requiring the outer roster evaluator's existing safety/unknown policy and every
existing valuation gate. Even a ready, positive rebuilder utility can accompany
a blocked trade that removes the last RB or protected backup. The tests prove
that attaching utility leaves those blockers intact. Readiness is not rollout
approval, statistical validation, or a replacement for those checks.

## Measurement and normalization

- **Current production:** exact Hungarian assignment from `trade_roster.assign`
  over the complete available eligible player roster, separately before and
  after, maximizing supplied fantasy points. FLEX/multi-position players occupy
  at most one slot. Picks, inactive and unavailable players do not produce
  current points. The dynasty `startable` threshold does not discard a player
  with real scoring input. All eligible available reserves need projections,
  because any could become a starter. Missing entries are never zero-filled.
- **Future assets:** the sum of supplied dynasty asset values once per unique
  roster ID, including inactive players and picks. Player/pick subtotals are a
  disjoint explanation of that sum, never additional scoring terms. This is
  present market evidence about dynasty assets, not a future points forecast or
  a discounted cash-flow model. No age premium, pick repricing or artificial
  seasonal projection is introduced.
- **Dynasty lineup proxy:** when production cannot be measured, exact lineup
  assignment using supplied dynasty values remains a `dynasty_value` diagnostic.
  `current_production` stays null. The proxy's weight is zero because its assets
  already contribute to `future_assets`; adding the proxy as another total
  would reward the same dynasty evidence twice. It is for shadow inspection and
  must not satisfy a projected-production or strict utility gate.
- **Depth/optionality:** unique usable reserve IDs/counts after the dynasty
  lineup, excluding picks and inactive/unavailable players. A dual-position
  reserve is one player. This diagnostic has zero score weight: its asset value
  is already counted, and the structural roster engine handles position-specific
  backup protection. It is not an expected injury-replacement points model.

Each scored component uses `(after - before) / max(before, after)`, with an
all-zero pair returning zero. There is no arbitrary points/value floor. This
is bounded, scale-invariant (e.g. PPG versus the same fixed period scaled equally),
and sign-symmetric under reversing a trade. Whole-team totals are used, so the
same package has a smaller relative impact on a larger team. Rescaling cannot
make dynasty units comparable to points: each component is normalized separately
before blending, and raw point/value totals are never added.

Current/future preference weights follow the existing trade-service defaults:
championship 1/0, contender .75/.25, balanced .5/.5, rebuilder .25/.75,
jets .1/.9. These are fixed, inspectable heuristics here, with no config or flag
reads. They do **not** track runtime changes to `trade_service` model knobs.

When current production is missing, keep only the weighted known dynasty
contribution. Do not renormalize the future weight to one. Thus a contender
with +50% dynasty gain and no points input returns +.125 at confidence .125;
the current-season component is null and enforcement is disabled. An explicit
championship outlook has zero future weight, so no points input means gain null
and confidence zero, while the dynasty diagnostics remain visible.

Projection evidence weight is .85, dynasty evidence weight .5, and declared
intent weight 1 (fresh inference .5, fallback .25). Confidence is the weighted
sum of available evidence multiplied by intent confidence, halved separately
for duplicates, unknown availability, unobserved lineup settings and supplied
rule uncertainties. These constants express conservative evidence handling;
none has been calibrated against actual manager acceptance.

The contender test exchanges +5 at RB2 and -9 at WR3 with unchanged dynasty
totals: starting production falls 93→89, so overall utility is negative.
The complementary test has a contender buy current production and a rebuilder
acquire a young player plus a pick. Both can gain under their own outlook while
the existing roster protection still passes. A separate case gains dynasty
utility while losing the final RB and remains structurally blocked.

## Actual available inputs and limits

Code was inspected directly in this worktree:

| Source | Available evidence and limits |
|---|---|
| [`trade_roster.py`](../../../backend/trade_roster.py), [`trade_roster_adapter.py`](../../../backend/trade_roster_adapter.py) | Complete `Team`/`Asset`/`Rules` snapshots, consensus dynasty values, owned-pick inclusion, reserve/taxi and availability observations, exact slot matching. No player projections or outlook provenance on `Team`. The adapter's observation timestamp does not prove upstream freshness. |
| [`trade_service.py`](../../../backend/trade_service.py), `outlook_alpha`, `infer_team_outlook`, opponent resolution | Existing outlook preference weights and declared→inferred resolution. Inference returns a direction score and signals, **not** a calibrated confidence or a freshness timestamp. Current starter/value and age signals are not projections. |
| [`server.py`](../../../backend/server.py), league preferences and opponent assembly | Stored per-league `team_outlook` preferences and inference inputs. Callers must preserve explicit source and resolve freshness from actual input capture; this pure component has no clock or provider access. |
| [`outlook/strength.py`](../../../backend/outlook/strength.py) | `SleeperProjectionsStrength` and `OwnModelStrength` are registered stubs raising `NotImplementedError`. Implemented sources use dynasty-lineup heuristics, team trailing scores or their blend. Trailing team scores cannot price individual incoming/outgoing players; affine dynasty-to-points output is not a real player projection. |
| [`sleeper-projections-2026.json`](../../../backend/tests/fixtures/outlook-calibration/sleeper-projections-2026.json) | Research fixture captured 2026-08-09 from the unofficial Sleeper endpoint. Week/player records retain `pts_ppr` and `pos`, restricted to roughly 527 players in two leagues. It is neither a live trade feed nor complete arbitrary-league scoring input. This utility does not load it or assume it remains fresh. |

To supply actual projections, pass a map of player ID to finite, nonnegative
points, `projections_fresh=True`, a nonempty `projection_basis` identifying
source/scoring/season/horizon, and either `fantasy_points_per_game` or
`fantasy_points_for_period`. The caller must ensure the same scoring rules,
season and horizon apply to every entry and both rosters. A label cannot verify
that externally; this API refuses missing metadata but has no provenance
verification service. An explicit zero projection is valid; missing, nonfinite,
negative and boolean values are not. Do not pass dynasty values with a points
label. Do not automatically adapt the dated research fixture into current input.

Only `trade_roster.ELIGIBILITY` slots are supported (QB/RB/WR/TE and its FLEX
variants); unsupported IDP/K/DEF lineups have no production or depth estimate.
Availability is the supplied snapshot. A period-total projection applies to a
single optimized lineup; this does not model weekly lineup rotation, future
injury recovery, bye-week substitution, schedule covariance, playoff odds or
title probability. Future market values themselves do not carry freshness
metadata in `Asset`. These limitations are why basis, component units and
readiness must travel with any ranking diagnostic.

## Focused verification

Run only `python3 -m pytest backend/tests/test_trade_outlook_utility.py -q` while
the main agent integrates. Final focused run: **49 passed**. Coverage includes full-team losses,
complementary outlooks, retained structural blockers, explicit precedence,
missing/stale inference and projections, real units, lineup reoptimization,
complete bench coverage, unique picks/reserves, scaling and zero baselines,
invalid data, statelessness and enforcement readiness. Coverage must include
every available eligible player on the union of the before/after rosters,
including reserves, outgoing-only and incoming-only players; unrelated assets
outside those rosters need no projections. Positive and negative normalized
changes remain bounded and reverse symmetrically, with point and dynasty scales
changed independently in the tests.

Two named in-memory sabotages were proven RED without changing source files:
`largest_starter_instead_of_whole_lineup` (replace the projected lineup sum with
its largest starter), and `allow_proxy_evidence_to_enforce` (force readiness true).
The first breaks the +5 RB2 / -9 WR3 regression; the second breaks the
missing-projection enforcement guard. The unmodified focused suite is GREEN.
No full suite, branch
switch, commit, shared wiring or deployment is part of this component task.
