# Shared trade-significance requirement

Date: 2026-09-17. Entry: owner feedback on the FFv3 / Newton review; plan approved in the Review app functionality task. Status: implementation in progress; not released.

## Product contract

Distinguish eligibility/fairness from whether a generated recommendation deserves attention. Apply one significance rule across all generation arms, including owner_v1, without changing arm selection, fairness, outlook/need utility, filler rules, or offer-count limits.

Provisional calibration candidate: at least one player in the viewer-personal OR consensus 2nd-round-equivalent tier or better; an actual first-round pick can independently qualify. A second-round pick alone cannot qualify. Summing cheap pieces cannot satisfy the requirement. Use shared tier definitions and canonical pick parsing, not a new Elo or market-value scale. This is a minimum significance check, not proof of trade quality; all existing eligibility rules still apply.

Explicit asset searches preserve the chosen low-value asset. General discovery, positional chasing/shopping, outlook, and partner-only filters do not create an exception. Genuine incoming offers and manually constructed/evaluated packages remain available. Exemption provenance comes from the server, not client-supplied card metadata.

Do not change the existing filler policy in this work. In particular, adding the missing owner filler gate is a separate experiment.

## 1. Analytics scope

Existing deck_impressions and bakeoff generation diagnostics cover the change; extend their existing private JSON evidence with significance version, mode, thresholds, eligible/reason, qualifying asset/source, and exemption when applicable. Aggregate evaluated/eligible/rejected counts by arm in existing run diagnostics; no new analytics event names or emitters. Preserve generated-versus-served semantics. Never log a rejected candidate as served. Bounded rejection evidence must not create one persistent row per discarded candidate.

The 100-card local review and its feedback are separate research data, not production dispositions. Preserve them unchanged. No ranking updates from calibration. Final field ownership/storage paths must be verified in implementation evidence before release.

## 2. Schema and configuration

- No new tables/columns, environment variables, client flags, or public route shapes planned.
- Proposed model_config keys: significance_mode (0 off, 1 shadow, 2 enforce; default 0), significance_player_min_tier (draft-round label selector; proposed 2), significance_allow_first_round_pick (default 1).
- Register numeric knobs through established database defaults and trade_service configuration; document resolved tier semantics. Values are captured once per generation job.
- Rollback: mode 0, effective readback, and affected cache regeneration. Do not toggle any arm settings.
- Rule version, mode, and thresholds participate in recommendation safety/cache signatures. Previously generated unversioned recommendations cannot be used as an enforcement bypass.

## 3. Evidence scope

- Pure unit tests: boundary tiers; personal versus consensus; missing/nonfinite data; pick classification; no junk summation; explicit exemptions; no caps; mode behavior.
- Integration tests: every arm's recommendations pass the final boundary, owner legacy-policy separation does not bypass it, cache invalidation, no provisional/after-mutation bypass, impressions contain final evidence, trusted incoming exceptions, targeted versus broad search distinctions.
- Preserve pinned baseline generator/profile tests; apply significance outside historical generation identity.
- Replay frozen local review inputs against proposed thresholds and inspect removed Yes decisions; a Yes is not an independently labeled significance judgment. Follow with broader two-league sampling before activation.
- No mobile source/testID changes planned. No new mobile structural test required; normal CI remains required. Manual existing-client check before release: discovery filters, explicit cheap-player search remains usable, incoming offer remains visible, cached old feed refreshes, empty result does not backfill trivial cards. Native TestFlight build is unnecessary unless native code changes; no simulator/Maestro.

## 4. Canonical documentation scope

| Reference | Planned update |
|---|---|
| docs/config-reference.md | Numeric mode/threshold defaults, capture, rollback |
| docs/architecture.md | Shared final recommendation boundary and cache lifecycle |
| docs/data-dictionary.md | Existing private JSON evidence extension; no migration |
| docs/api-reference.md | Recommendation filtering/cache semantics; no new route |
| docs/cross-client-invariants.md | n/a: existing tiers reused, no client enum/constants change |
| docs/glossary.md | Define recommendation significance if existing vocabulary needs it |
| docs/engineering-notes.md | n/a: no general schema/route conventions changed |
| Initiative evidence | Approved exceptions, provisional threshold, replay and test results |

## 5. Ship gates

No express waivers. Parent review of all agent diffs; targeted and broader regressions; normal CI green on the release SHA; calibration evidence and actual rejected examples reviewed before enforcement. Update reference docs and test ledger with run/unexecuted status. Deployment, flag activation, and new browser batch are distinct actions, not implied by a passing test or implementation completion. Current task asks agents to write code; no production mutation in this coding phase.

After release approval: deploy backend dark, verify live SHA and configuration, enable the selected rule without changing owner-only serving, regenerate stale decks, validate actual production recommendations, then create a NEW local review batch targeting 50 per league. Never force 50 by relaxing the filter; never overwrite round one's feedback.
