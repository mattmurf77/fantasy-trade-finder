# Experimentation Framework — Concurrent A/B & Multivariate Testing, Targeting, Stats, Self-Service

**Role:** an-data-architect + an-funnel joint spec · **Date:** 2026-07-17 · **Status:** Spec
**Depends on:** tracking plan v2 (envelope, `experiment_exposed`), program plan (metric formulas), PFO spec (guardrails). Engineering execution: `docs/plans/analytics-platform/` PRD/HLD/LLD.

## Requirements (operator's ask, restated)

1. Multiple versions of a page/feature live in production simultaneously.
2. Multiple A/B **and multivariate** tests running concurrently without contaminating each other.
3. Assignment at random **and** by user attributes (platform, cohort, behavior).
4. Self-service: help designing a test, picking success metrics, predicting run time, monitoring, and a decision-grade readout.
5. Works at beta scale honestly and survives SQLite→Postgres.

## Current state

One global boolean flag map (`feature_flags.py` → `GET /api/feature-flags`), identical for every user; one hard-coded MD5 bucket (`trade.aggression_ab` → light/fair/generous in `trade_service.py:965`) with its variant stamped into swipe props. No assignment records, no exposure contract, no analysis. The framework below **subsumes both**: flags become the delivery rail, `aggression_ab` becomes Experiment #1 migrated into it.

## Design

### D1. Concepts

- **Flag (rollout):** on/off or % ramp, no hypothesis, no readout. Kill switches, staged releases.
- **Experiment:** hypothesis + variants + primary metric + guardrails + stats plan. A/B = 2 variants; A/B/n and **multivariate** (factor grid, e.g. CTA-copy × card-layout → 4 cells) supported by the same machinery — an MVT is one experiment whose variants are factor combinations.
- **Layer (concurrency contract):** every experiment lives in exactly one layer; experiments in the *same* layer are mutually exclusive (traffic split between them); experiments in *different* layers hash independently → orthogonal, so concurrent tests don't bias each other. Reserved layers to start: `onboarding`, `ranking`, `trades_ui`, `engine` (server-side params), `growth`. A user can be in ≤1 experiment per layer, many across layers.
- **Unit:** `account_id` when known, else `device_id` (pre-auth experiments); unit choice fixed per experiment. Identity stitching maps device→account at sign-in; onboarding experiments therefore key on `device_id` end-to-end to avoid mid-experiment unit swaps.

### D2. Assignment (deterministic, stateless, auditable)

```
# AMENDED 2026-07-17 (approved; per LLD §4.2 — a single experiment-keyed hash cannot
# deliver in-layer mutual exclusivity: each experiment would place the same unit at a
# different bucket, so disjoint ranges would still both capture it):
layer_bucket   = sha256(f"{layer_salt}:{unit_id}") % 10000                          # experiment-INDEPENDENT — places the unit once per layer
variant_bucket = sha256(f"{layer_salt}:{experiment_key}:{version}:{unit_id}") % 10000  # variant split; version in preimage so revisions don't re-assign the same units to correlated arms
```
- Layer split: each experiment owns a **half-open** bucket range `[lo, hi)` of `layer_bucket` within its layer (e.g. exp A [0,5000), exp B [5000,10000)). Within an experiment's captured traffic, `variant_bucket` maps to variants per configured weights. Unassigned range = default experience.
- **Targeting predicate runs before hashing.** Rules = JSON AND/OR tree over the **attribute registry**: `platform`, `app_version` (semver ≥), `device_type`, `signup_week`, `league_count`, `scoring_formats`, `ranking_method`, `activation_stage` (funnel v2 stage), `verified`, `invited_by_present`, `is_tester_allowlist`, `wat_active_last_28d`. Non-matching users get default experience and are excluded from analysis (not counted as control). *(Amended: attribute availability is constrained per unit type — device-unit experiments, e.g. the onboarding layer's, can target only header-derived attributes + allowlist, because pre-auth users have no `users` row; validation rejects unit-incompatible attributes. See PRD FR-33b.)*
- Assignments are **persisted on first evaluation** (`experiment_assignments` table) even though the hash is deterministic — this freezes membership against later targeting-rule edits and gives the readout an audit trail. Rule edits after launch create a new experiment version (metrics reset; the old readout is archived, never silently blended).
- Server evaluates everything: session-init (and flag fetch) returns the resolved `{flags, experiments:{key:variant}, configs}` for that identity. Clients never hash. Server-side call sites (`trade_service`, etc.) call the same evaluator. Snapshot cached per session; changes apply at next session (no mid-session flips).

### D3. Delivery — how multiple versions coexist in production

- **Client UI variants:** code for all variants ships in the binary behind the resolved config (`useVariant('exp_key')` hook / web equivalent). App-store latency means mobile variants ship dark, then the experiment activates server-side.
- **Server behavior variants:** evaluator available wherever `is_enabled()` is used today; engine experiments override `model_config` scalars per-variant (variant → config-overlay map), which is how `aggression_ab` migrates.
- **Kill switch:** every experiment has `status ∈ {draft, running, paused, stopped, decided}`; pausing serves default to everyone within one flag-cache TTL (≤60 s server, next fetch client) without redeploy.
- Fail-open: evaluator errors → default experience + `client_error`/server log, mirroring flags' fail-open convention.

### D4. Exposure & metrics contract

- `experiment_exposed` fires at **first render/first effect** of the varied surface (not at assignment) — once per unit×experiment×session. Analysis population = exposed units only; assignment-without-exposure is diluted-intent and reported separately.
- *(Amended 2026-07-17, approved — per PRD FR-32)*: the `experiments` envelope snapshot is stamped on **funnel-stage events and events fired from surfaces inside a running experiment's declared scope** — not on every row (indiscriminate stamping bloats every `screen_viewed` forever for a join-free-query optimization). All other analysis joins `experiment_assignments`; a missing stamp is never an error.
- Metric roles per experiment: **primary** (exactly one — the decision metric), **secondary** (directional), **guardrails** (PFO five + experiment-specific). Metrics are picked from the program-plan catalog by key, not free-typed — self-service can only choose computable metrics.

### D5. Stats engine

- **Design-time (power/duration):** for proportion metrics, per-arm n = `2·(z_{α/2}+z_β)²·p̄(1−p̄)/MDE²` (α=.05 two-sided, power .80 default). Duration prediction = ceil(n × arms ÷ eligible-traffic-rate), where eligible-traffic-rate = trailing-28-day count of units matching the targeting predicate that hit the exposure surface per week. The tool shows: required n/arm, predicted weeks, and the MDE achievable in 2/4/8 weeks at current traffic — so the operator can trade off before launching.
- **Read-time:** two-proportion z-test (proportions) / Welch's t on winsorized values (continuous, p99 winsorize); 95% CI on absolute + relative lift. *(Amended 2026-07-17, approved — per PRD N6/OQ-8: the **sequential mode (mSPRT) is deferred to v2**; always-valid sequential stats are subtle enough that a solo-audited implementation is wrongness risk masquerading as rigor. v1 harm monitoring = per-guardrail relative-degradation thresholds with minimum-n gates — yellow alert rows, no always-valid-p pretense.)* Fixed-horizon is the decision rule. No peeking-driven ship calls: dashboard shows "days remaining" and withholds the verdict badge until horizon.
- **Multiple comparisons:** >2 variants or >1 primary-eligible metric → Bonferroni-adjusted α, surfaced in the readout.
- **SRM check:** χ² on observed vs expected arm sizes every readout; SRM p<.001 → data-quality red banner, verdict suppressed.
- **Beta-scale honesty (mandatory banner):** with beta-cohort traffic (tens of users), most UI A/Bs are underpowered for <20-pt effects. The duration tool says so at design time ("at 40 eligible users/week, an MDE of 10 pts on activation needs ~34 weeks — consider a bigger swing, a coarser metric, or ship-and-watch"). Framework still earns its keep pre-scale via: engine experiments on high-frequency units (swipes/cards number in thousands — `aggression_ab` readout is viable *today*), sequential harm-stops, and being launch-ready the day traffic arrives.

### D6. Lifecycle & self-service workflow

`draft → running → (paused) → stopped → decided(ship|revert|iterate)`, every transition logged with actor + reason.

Self-service surface = **admin dashboard "Experiments" tab + `/an-experiment` role skill** (new, thin: wraps this framework):
1. **Design:** operator states hypothesis in prose → skill/UI produces the experiment spec: layer, unit, targeting, variants, primary metric (suggested from the catalog by touched surface), guardrails (PFO five auto-attached), power table + predicted duration.
2. **Launch:** spec written via CRON_SECRET-gated `POST /api/admin/experiments`; validation rejects layer-range overlap, unknown metric keys, missing exposure surface.
3. **Monitor:** dashboard card per experiment — arms, exposure counts, SRM status, guardrail deltas (sequential), days remaining.
4. **Decide:** at horizon, readout renders verdict + CI + guardrail table + segment cuts (platform, cohort) with multiplicity warnings; decision recorded (`decided`, `decision`, `decided_by`, rationale) → permanent experiment log (the org's memory of what worked).

### D7. Storage (delta summary; DDL in LLD)

`experiments` (key PK, version, layer, status, hypothesis, unit_type, targeting_json, variants_json [name/weight/config-overlay], primary_metric, guardrails_json, mde, alpha, power, start/stop/decided timestamps, decision, notes) · `experiment_assignments` (unit_id, experiment_key, version, variant, assigned_at, context_json; PK unit+key+version) · `experiment_metric_snapshots` (daily rollup per experiment×variant×metric for the dashboard). All SQLite-now/Postgres-later, append-only except `experiments.status`.

## Decisions needed

1. Adopt layers as named above (recommend yes; renameable later, semantics locked).
2. ~~Fixed-horizon default + sequential harm-monitoring~~ **Decided 2026-07-17:** fixed-horizon + threshold harm alerts in v1; mSPRT deferred to v2 (see amended D5).
3. Migrate `trade.aggression_ab` into the framework as Experiment #1 and run its first real readout (recommend yes — instant dogfood with data that already exists).
4. New `/an-experiment` skill as the self-service front door (recommend yes).

## Handoffs

- PRD/HLD/LLD for the build → `docs/plans/analytics-platform/` (pm-technical/eng-architect lane, dual-agent validated).
- Backend evaluator/endpoints/stats → eng-backend; client variant hooks → eng-mobile/eng-web; QA (assignment determinism, exposure firing, kill switch) → eng-qa.
- First experiment backlog (what to test first) → pm-growth/pm-retention/pm-monetization proposals through the design workflow, PFO guardrails binding.
