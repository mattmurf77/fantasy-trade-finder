# Experiment: onboarding_v2_rollout (v1 — operator smoke)

*Role: an-experiment · 2026-07-18 · Status: validated locally end-to-end; awaiting prod deploy + launch*

## Hypothesis & primary metric

Value-first onboarding (username-first landing → trades-first hook → contextual Quick Set → save-moment Apple ask; docs/plans/onboarding-conversion/plan.md v2.1) raises **activation_rate** (first swipe in session 1) versus the current sign-in-first flow.

**v1 is explicitly NOT a powered test.** It is an allowlist-targeted rollout so the operator's device receives the full new experience in production while every other unit keeps the default flow and the pre-flip baseline stays clean. No readout will be drawn from v1. The powered activation test ships later as v2 via `/revise` (see Graduation).

## Spec

| Field | Value | Why |
|---|---|---|
| key / version | `onboarding_v2_rollout` v1 | One key across phases; `/revise` bumps versions |
| layer | `onboarding` | Semantically correct home; reserves in-layer exclusivity for future onboarding tests |
| unit_type | `device` | Mandated for the onboarding layer (pre-auth assignment; stable across sign-in) |
| buckets | `[0, 10000)` | Full layer — targeting (not bucketing) does the narrowing; the allowlisted device must never miss on bucket |
| targeting | `{"is_tester_allowlist": true}` | Resolved from env `FTF_TESTER_ALLOWLIST` (comma-separated unit ids); missing attr = excluded, so non-listed units can never be captured |
| variants | `control` 0 bp / `treatment` 10000 bp | Weights must sum to 10000 with ≥2 variants; 0-weight control makes treatment certain for captured units |
| treatment client_config | `flags`: all 10 `onboarding.*` keys true | Overlaid client-side onto the flag map (mobile `flags.ts` merge) |
| primary_metric | `activation_rate` | Catalog metric the redesign exists to move |
| exposure_surface | `landing` | First treated surface |
| scope | funnel events + SignIn/Trades/QuickSetTiers screens | FR-32 envelope stamping for later analysis |
| guardrails | 5 PFO guardrails (auto-attached) | Non-omittable |

## Power & duration (calculator output, honest read)

`POST /api/admin/experiments/preview` with baseline 0.40, MDE 0.15, 1 eligible/week:

> ~174/arm (~348 weeks). **UNDERPOWERED at beta scale** — launching requires an explicit override.

Correct and intended: launch uses `override_underpowered: true` with rationale "n=1 targeted rollout for operator validation, not a powered test." The engine records the override forever.

## Engineering changes made to enable this (this session)

1. **`is_tester_allowlist` resolution implemented** (`backend/experiments.py`): the attribute was registered but nothing resolved it (missing attr = excluded, so it matched nobody). Now resolved from `FTF_TESTER_ALLOWLIST` env on the engine's 60s cache refresh. Not `model_config`: its `value` column is Float. 3 new tests in `backend/tests/test_analytics_p3.py` (21 pass).
2. **Dual-unit resolution in `/api/feature-flags`** (`backend/server.py`): the route resolved session-user *or* device; a signed-in user could never be captured by a device-unit experiment, and a new user's assignment evaporated the moment their session validated. Now resolves both identities and merges (disjoint by construction — each experiment has one unit_type).
3. **Client overlay merge** (`mobile/src/api/flags.ts`): the app read only `.flags` and ignored `configs`; a variant's `client_config.flags` now overlays the global map (overlay wins, merged map cached for offline boots).
4. `experiments.engine` flipped true in `config/features.json` (inert with no running experiments).

## Local end-to-end validation (2026-07-18, scratch DB, port 5099)

Preview → create draft → launch (with override) → flags fetch:
- `X-Device-Id: dev_e2e_test` (allowlisted) → `experiments: {onboarding_v2_rollout: treatment}`, overlay carries all 10 onboarding flags.
- `X-Device-Id: dev_stranger` → empty. Global `flags` map unchanged for everyone.

## Prod launch runbook

1. Ship the code: merge `trade-engine-v2` → `main` (Render auto-deploys); EAS build → TestFlight (client merge + onboarding UI are in the new build).
2. Install the new build, open it once signed in — the events SDK mints `dev_<uuid>` and first batches land.
3. Find the device id (Render shell / prod DB): `SELECT device_id FROM identity_links WHERE sleeper_user_id='<operator user_id>' ORDER BY linked_at DESC LIMIT 1;` (fallback: same filter on `user_events`).
4. Render env: set `FTF_TESTER_ALLOWLIST=device:dev_<uuid>,<operator user_id>` (service restarts; ≤60s cache refresh).
5. Create + launch against prod with the same two curls used locally (host swapped, `X-Cron-Secret` from `secrets.local.env`).
6. Force-quit and reopen the app: boot flags fetch resolves treatment → full new onboarding on the operator's device only. Fresh-install state means first-run surfaces (skeleton deck, identity strip, chip, coach marks) show even though the account is old; sign out to smoke the landing itself.

**Known limitation:** `landing.try_before_sync` stays globally false, and the backend demo endpoint checks it server-side — the client overlay can't open it. The demo/sample-league path smokes locally only, until that flag flips globally at public launch (plan's launch pairing note).

## Graduation to a powered test (v2, later)

`POST /api/admin/experiments/onboarding_v2_rollout/revise` with: targeting `{"app_version_gte": "<onboarding build>"}` (drop the allowlist), 50/50 weights, same primary metric + guardrails, eligibility = new devices/week from measured `landing_username_submitted`. Re-run preview with measured baseline activation from the instrumented cohort; launch only if the calculator's horizon is acceptable — else ship-and-watch against the pre-flip baseline instead of a theater A/B.

## Decisions needed

- Operator go for merge → deploy → TestFlight build (the rollout is inert until the code ships).
- v2 graduation timing (post-smoke, ideally inside the July–Aug window).

## Handoffs

- Prod launch curls + env: operator (this doc). Readout discipline: none for v1 by design.
- v2 powered test design: an-experiment (this role) once baseline activation is measured.
