# Owner-authorized production learning release

## Decision and scope — 2026-09-22

After being told that model quality remains unproven and local first delivery
is15.1s versus8.4s incumbent, the owner explicitly requested: “push this live in
production now (both the documentation and the new model). Let's use user data
to see how the logic itself performs.” This supersedes the prior conditional
release hold **as a production learning decision**, not a passed performance or
six-dimensional model-quality gate. Preserve all earlier evaluation results.

Release `owner-v2-bilateral-2` with presentation `bilateral-survivors-3`, plus its
independent evaluation framework, research/implementation docs and reviewed
correctness repairs. Preserve all existing arms/settings except the single
registered `owner_bilateral_revision_enabled` selector, which becomes1 after the
tested backend is live. Prior bilateral version-1 remains the rollback artifact,
not a concurrently served comparison arm. No output cap, candidate-budget change,
new projection source, schema table, client emitter or mobile binary is added.

Accepted unresolved risks: slower cold first action; mixed/limited bilateral
quality evidence; sparse partner boards; missing compatible actual starter-point
and required-cut evidence; incomplete non-job/provider freshness; unexecuted
physical-device and production-load qualification. These remain open engineering
work, not quietly converted to passes. CI, secrets/ownership protection, historical
offer integrity and audited readback remain mandatory. An operational failure
is grounds to stop/rollback; owner risk acceptance is not permission to ignore it.

## Fresh preflight and release procedure

At12:03:42 UTC the Render service was live at
`73bfa41e358e8780b823f652cf8388ae209b977d`, main branch, unsuspended,
autodeploy disabled, one Standard Python instance. Authenticated API readback:
bilateral enabled1, owner include/serve/only1, baseline/challenger/fit/gen_v2
include0, deck/group limits0, significance mode2. The new selector was not yet
registered in the270-row production configuration. It defaults0 in new code.
Source: Render service/deploy GETs and production `/api/admin/config` and
`/api/feature-flags`; private receipt is retained locally, never committed.

1. Publish reviewed branch and documentation; attach PR and require all four
   exact-head CI jobs, including hosted Python3.12 backend tests, to pass.
2. Merge without modifying unrelated main work. Verify the tested/merged Git
   trees match and explicitly deploy that merge SHA; do not change autodeploy.
3. Read back live deployment SHA/health and all config/flags. New selector must
   default0; unrelated270 knobs and208 flags must remain unchanged.
4. Set only `owner_bilateral_revision_enabled=1` using `scripts/set_knob.py`
   with source `bilateral-revision-production-learning-20260922`. Read it back.
   Verify version attribution on subsequent actual generation when available;
   config-derived selected identity is not proof of a user-viewed offer.
5. Record timestamps, exact commit/CI/deploy IDs, config diff, verification and
   limitations in the release receipt. Existing likes/exact terms stay historical.
   No new TestFlight release is required for this backend-only change.

## Learning from production without inventing success

Use the [framework](../model-evaluation-framework/scorecard-spec.md), not raw
generated-card counts as the outcome. Freeze release boundary/model version and
separate new version-2 episodes from carry-in likes/matches and unknown provenance.
Retain A's original offer evidence and B's later occurrence/valuation separately.
Do not refresh the episode deadline when B finally sees the card.

Report these separately, with coverage and actual observation windows:

- Generation errors/empty searches, durable first-batch latency and actual
  client tap-to-first-action when measured; cold versus prepared-hit populations.
- Real viewed offer episodes, per-manager like/pass reasons and effective undo;
  repeated packages and target/outlook/league-format segments.
- Valid overlapping two-sided interest, withdrawals/expiry and confirmed exact
  platform completions. A like/send is not completion; silence is not rejection.
- All six independent dimensions for both managers, including Unknown rank,
  projection/cut and stud-compensation evidence instead of invented grades.

The framework proposes14-day origin windows and episode follow-up through the
earlier of actual expiry or14 days after qualified start; do not extend actual
offer expiry. Missing timing/linkage makes an episode evidence-limited. Fixed
eligible-cohort enrollment and complete instrumentation are not retroactively
assumed. The all-traffic switch is **not randomized A/B**: historical comparisons
are descriptive and confounded by changing users, season, market and exposure.
No minimum sample, causal acceptance uplift or calibrated probability is claimed.

Immediate post-release verification covers deployment/config/health and available
new-version attribution, not future outcomes. Reassess once enough genuine
exposures and mature independent league/manager episodes exist; do not promise a
statistically supported decision from a calendar date or thousands of generated
cards. No recurring automation is created by this document.

## Rollback

Use the same audited CLI to set the revision selector0, read effective config
back and verify subsequent version-1 attribution. Preserve other knobs/flags and
all old impressions, likes and terms. If a runtime-wide repair fails independently
of the selector, explicitly redeploy the recorded pre-release SHA above; no
destructive database cleanup. Report the reason and actual rollback readback.

## Starter-impact follow-up

The owner's requested source plan is documentation-only in this release. It must
evaluate season-long/ROS rankings and projections, weekly projections and legal
bye-week replacements for both teams, without treating dynasty prices as points.
See [research scope](spec-starter-impact-research.md). No new provider pipeline
is silently activated with this model.
