# Whole-team mutual benefit — item 3

Date: 2026-09-04. Pure helper implementation; serving integration and activation belong to main under [scope.md](scope.md). Work stays on `claude/fleeced-trade-engine-balance-c0c75d`; no branch changes or commits. This note, `backend/trade_mutual_benefit.py`, and `backend/tests/test_trade_mutual_benefit.py` are this subtask's entire write scope. Main owns flags, generators, final gates, shared documentation, and rollout evidence.

## API

```python
from backend.trade_mutual_benefit import evaluate_mutual_benefit, rank_key

viewer_utility = roster_result["teams"][viewer_id]["outlook_utility"]
partner_utility = roster_result["teams"][partner_id]["outlook_utility"]
mutual = evaluate_mutual_benefit(
    viewer_utility,
    partner_utility,
    viewer_preference_source=viewer_source,
    partner_preference_source=partner_source,
    minimum_gain=0.01,
    minimum_confidence=0.5,
    tolerance=1e-9,
)
order = rank_key(mutual,
                 give_count=len(card.give_player_ids),
                 receive_count=len(card.receive_player_ids))
```

Each utility mapping provides `normalized_gain: float | None`, `confidence: float` in `[0, 1]`, `basis: str`, and **`ready_for_enforcement: bool`**. The readiness field extends the initial minimal contract following the partial-production integration correction. Each gain is measured over that manager's complete before/after team in their own direction; **do not negate the partner's gain**. Both inputs must use the same normalization convention/horizons, using the normalizers produced by item 2. Raw dynasty sums, package surplus, and acceptance probabilities are not interchangeable inputs.

Readiness must be the literal `True`. Missing/false readiness or a `dynasty_only`, `unavailable`, blank, or `unknown` basis yields unknown **before** sign/threshold checks. This applies even if a partial delta is negative: missing production could offset a dynasty loss. `reported_gain` retains a finite partial input for private diagnostics, while the usable `normalized_gain`, weaker gain and total remain `None`. Confidence in incomplete whole-team benefit is zero. A complete negative on the other side still blocks. Readiness describes utility completeness; it is not a substitute for roster or market eligibility.

Pass preference provenance explicitly as `observed`, `estimated`, or `unknown`; omission means unknown. Never infer observed preferences from a utility's basis, consensus values, a seeded ranking board, the mere existence of a roster, or a default balanced outlook. Where item 2 supplies `outlook.source`, main can map actual `explicit` declarations to observed, `inferred` to estimated, and `fallback` to unknown, while accounting for any other missing preference evidence used by that utility. An observed outlook does not make consensus asset values a personal ranking board; keep those market-policy fields unchanged.

There are no imports of providers, flags, trade generators, server or database. Inputs are not changed, including nested dictionaries. Components, upstream reasons, and uncertainties are deliberately not copied into this summary; keep the original per-team `outlook_utility` alongside it in the private roster diagnostics. Do not expose opponent utility details through `PolicyResult.client_payload()`.

## Verdict and ordering

The serializable result has `schema_version=1`, `status`, `eligible`, `reason`, sorted `reasons`, `fallback_candidate`, `weaker_gain`, `total_gain`, weakest effective `confidence`, named `sides`, frozen `thresholds`, and `numeric_notes`.

| Status | Benefit-only meaning |
| --- | --- |
| `eligible` | Both complete gains clear the meaningful threshold, both preference sources are observed, and both confidence values clear the threshold. Other gates must still pass. |
| `blocked` | A complete finite gain is negative beyond zero tolerance or insufficiently positive. This takes precedence over unknown evidence on the other side. A low-confidence complete negative stays a modeled negative; it does not become an observed personal rejection. |
| `unknown` | Benefit or evidence is incomplete. This does not mean zero gain or a negative preference. |

`fallback_candidate=True` identifies two **complete**, meaningful modeled gains whose only uncertainty is low confidence or estimated/missing preferences. Invalid confidence/provenance and incomplete/invalid utility cannot qualify. This is a diagnostic for main's explicit fallback policy, **not permission to serve**. Strict `trade.mutual_benefit_v1` enforcement should require `eligible`; main may separately preserve existing fallback behavior in shadow/legacy operation, retaining its uncertainty. Do not silently admit all unknowns or call them proven mutual wins.

The ascending rank key is:

```text
(evidence_bucket, -weaker_gain, -total_gain, total_asset_count, abs(side_count_difference))
```

Buckets are eligible `0`, complete positive fallback estimates `1`, other unknowns `2`, blocked `3`. Filter before serving; sorting alone is not an eligibility gate. Within eligible candidates, the weaker manager's gain is strictly primary, total gain breaks its ties, then smaller packages win. Asset count includes picks. Equal count then prefers less imbalance (2-for-2 before 1-for-3). Final exact ties remain equal; append the existing canonical trade concept ID if caller order is not deterministic. Never use viewer-relative identity or random noise to break symmetric ties. No confidence multiplier is applied to gains, and confidence does not outrank gain inside an evidence bucket.

Examples: `(0.03, 0.04)` outranks `(0.015, 0.80)` despite its lower total. `(0.02, 0.06)` outranks `(0.02, 0.03)` even with a larger package. Equal benefits prefer 1-for-1 to 1-for-2. `(1000, -0.04)` is blocked. Unknown partner benefit never becomes `min(viewer_gain, 0)` or a one-sided total.

The default meaningful threshold is **0.01 normalized utility**, an uncalibrated policy default, not one percentage point of win probability. Gains within `1e-9` of zero become exactly zero and cannot pass. The meaningful boundary allows absolute tolerance only. No relative tolerance erases a real small loss beside a huge win. Require finite `minimum_gain > tolerance >= 0` and `0 < minimum_confidence <= 1`; invalid configuration raises `ValueError`.

Preference confidence caps are observed `1.0`, estimated `0.5`, unknown `0.25`, applied as `min(upstream_confidence, cap)` without increasing confidence. These are conservative evidence weights, not calibrated acceptance odds. Estimated/unknown provenance stays unknown even if the confidence threshold is lowered. Malformed or nonfinite confidence becomes zero; malformed/nonfinite gains become unknown. Booleans and numeric strings are not accepted as measurements. Finite extreme gains keep their signs; an overflowing total saturates at the largest finite float with `mutual_total_saturated` in `numeric_notes`. At saturation, total-gain distinctions can be lost; ordinary normalized utility is far below this bound.

Stable primary reasons are `mutual_meaningful_gain`, `mutual_negative_gain`, `mutual_gain_below_minimum`, and `mutual_evidence_incomplete`. Detail reasons are `mutual_utility_incomplete`, `mutual_gain_unknown`, `mutual_gain_invalid`, `mutual_confidence_invalid`, `mutual_low_confidence`, `mutual_preferences_estimated`, `mutual_preferences_unknown`, and `mutual_preference_source_invalid`. Side summaries identify which side supplied the evidence. Reversing sides preserves every aggregate and sort key while exchanging only the named side summaries.

## Integrating with the existing policy

Read points at implementation: `trade_policy.PolicyResult.rank_key` (around line 466), `trade_policy.compose_deck` (around line 1026), `trade_roster.evaluate` (around line 208), `server._evaluate_deck_policy` (around line 5380), the final `_run_trade_job` roster/market stages (around lines 7460–7600), and `bakeoff_runner.BakeoffRun.attribution_for/group_for` (around lines 983/1003). Main is editing shared files concurrently; function names are the durable anchors.

1. Capture both final full rosters and attach item 2's utility under each team's `outlook_utility`. Compute this summary on that exact snapshot after cuts, sweeteners, swaps, likes-you injection, wildcard/first-session shaping and replenishment. Re-evaluate after any subsequent package mutation; a cached pre-mutation verdict cannot survive.
2. Preserve all market floors, personal-market requirements, ownership, coverage, usable backups, capacity/cut checks and unknown-data handling. A benefit pass never overrides market/roster `eligible=False`. In particular, the current market policy only requires package personal gain for Conviction, while this new whole-team threshold is an additional behavior controlled by main's separate dark `trade.mutual_benefit_v1` switch.
3. In enforcement, filter on benefit **before** market deck composition, so composition measures surviving supply. In shadow mode, record prospective verdicts and ordering without altering served cards or legacy order. Main must include the new enforcement switch in `final_checks_pending` and error paths so provisional/unchecked cards cannot escape. An evaluation error is not a benefit pass.
4. Replace the current `_policy_order` objective when the new treatment is active. It currently sorts `PolicyResult.rank_key[0]` (package personal gain), then roster `mutual_utility`, then harmonic package surplus and market ratio. Putting this new key after that prefix would fail item 3. Sort surviving `(card, PolicyResult)` pairs by the new key and pass them to the existing `trade_policy.compose_deck`. Do not globally re-sort its returned deck. Keep existing `PolicyResult.lane` assignments: this helper has no authority to upgrade a Fallback card into Core or Conviction.
5. `compose_deck` preserves order inside each market lane. It takes the Core lead block, then Conviction, remaining Core, then Fallback. Defaults are three Core lead cards, a Conviction cap of `min(2, floor(0.20 * requested_size))`, and a 0.70 Core share target. Conviction requires enough Core supply to fill the lead. The loop recalculates Conviction share on **realized** length and removes Conviction until both share checks pass or none remain. It returns rejected quota candidates separately. Retain those reasons and prefer a shorter deck over relaxing these controls.
6. **Existing fallback nuance:** the Core-share loop removes only Conviction. When no Conviction remains, it exits even if Fallback makes Core share lower than 0.70; a fallback-only deck is currently retained. Thus Core minimum share is not an unconditional invariant across no-board traffic. Preserve that behavior for this ordering handoff; do not relabel fallback, invent boards, or claim a strict Core minimum for fallback-only supply. Any change to that composition rule belongs to main's separately documented rollout decision.

## Experiment and telemetry attribution

Market lanes (`core`, `conviction`, `fallback`) are separate from the bakeoff's value/outlook lanes and arm×basis groups. `bakeoff_runner.compose_deck` builds group quotas and interleaves groups before the final market stage. `attribution_for` and `group_for` use **object identity**. Preserve original card objects when sorting/filtering; do not rebuild cards just to attach a benefit result.

Retain `model_arm`, `arm_rank`, `also_proposed_by`, `group_key`, `group_rank`, `lane_slot`, effective `trade_intent`, and historical policy identity as provenance of generation/composition. Do not rewrite them to pretend they describe the new final position. The final served card index describes the new order. Keep `policy_variant` orthogonal to `model_arm`; main should freeze the actual mutual-benefit enforcement/shadow state and helper thresholds in impression diagnostics, separately from the existing personal-market variant. Do not attribute this post-processing to the learned acceptance head or any generator arm, and do not alter pinned `MODEL_A_PROFILE`.

A global benefit reorder plus market composition changes final arm/group exposure; retaining old group labels alone does not prove final group quotas or interleave were preserved. For a common final-policy treatment, apply identical rules across arms, explicitly record that final composition is the treatment, and log per-arm/group survival and underfill. If an experiment instead promises unchanged final group quotas/interleave, main must compose and attribute with those constraints jointly or keep this change shadow-only for that experiment. Never refill from an unchecked candidate or silently assign a filtered slot to another arm. Generator ranking changes must run before that arm's rank/group attribution is built, within main's experiment scope.

Freeze this summary under the roster diagnostics alongside both upstream utility mappings in `features_json` at the final package stage. Keep asset-direction validation, canonical trade concept identity, ghost holdout, and served-versus-viewed distinctions. Record blocked **and unknown** candidate outcomes with reason codes and available arm/group provenance, not only kept cards; missing exposure is not a rejection. Preserve the existing per-job/every-row nullable telemetry-key convention. This module does not write telemetry, create flags, fit a model, or claim acceptance uplift.

## Evidence and limitations

Focused command: `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -p no:cacheprovider backend/tests/test_trade_mutual_benefit.py -q`. Readiness-aware run: **101 passed**, Python 3.14.4. Production/CI uses Python 3.12; main owns that validation. No full suite was run during concurrent integration.

Sabotage proof used in-memory module replacements, leaving source files unchanged: `sum-hides-weak-manager` replaced the weaker-side minimum with the sum and the asymmetric-gain test failed; `partial-utility-promoted-to-complete` forced readiness true and all 27 partial-utility regression cases failed. The unchanged implementation passes the focused tests.

Coverage includes large win/other loss, positive asymmetry, total then simplicity ties, symmetry, repeated pure calls, missing/estimated/low-confidence preferences, readiness and incomplete-basis regression across negative/zero/positive partial deltas, known loss beside unknown benefit, thresholds/zero tolerance, malformed/NaN/infinite/overflow inputs, and existing market composition with Core/Conviction quotas and fallback-only supply.

This proves helper behavior and the ordering handoff, not final worker enforcement, flag-off identity, live deck quality, quota survival across experiments, production calibration, or deployment. Main owns those checks and the final gates. The helper trusts an upstream readiness declaration on a non-partial basis and cannot audit normalization, data freshness, provenance truth, or whole-roster completeness from two scalar mappings alone. No learned acceptance model is implemented; that is item 4.
