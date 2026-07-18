# PRD — FTF Analytics & Experimentation Platform

**Date:** 2026-07-17 · **Status:** **Final — dual-agent validated** (3 rounds, both lenses signed off; see [prd-reconciliation.md](prd-reconciliation.md))
**Executes:** [tracking-plan-v2](../../business/analytics/2026-07-17-tracking-plan-v2.md) · [analytics-program-plan](../../business/analytics/2026-07-17-analytics-program-plan.md) · [experimentation-framework](../../business/analytics/2026-07-17-experimentation-framework.md) · [pfo-measurement-spec](../../business/product/2026-07-17-pfo-measurement-spec.md)
The strategy layer is settled input; this PRD specifies what "built correctly" means. Where it deliberately amends a strategy doc, the amendment is marked **[AMEND]** and flows back to that doc on approval.

---

## 1. Summary

FTF is a pre-revenue TestFlight beta run by a solo operator who cannot currently answer "where do new users drop off?", "did the last release make anything worse?", or "did that engine change help?" without hand-timed walkthroughs. This PRD ships the platform the strategy docs specced: a first-party event pipeline (additive `user_events` envelope + batched `POST /api/events` + fire-and-forget SDK modules per client), identity stitching, a CRON_SECRET-gated admin dashboard rendering the R1–R10 report catalog, and a layered experimentation engine (concurrent A/B + multivariate, deterministic persisted assignment, honest fixed-horizon stats) with a self-service design→launch→readout workflow.

**Primary user: the operator (Matt)** and the Claude role skills he works through. **Testers/users are measured subjects, never the audience** — zero new UI, zero added latency, no third-party analytics SDK. At beta scale much of the system's value is *readiness* rather than readouts; the engineering therefore optimizes for (a) never corrupting product DB/UX, (b) never lying statistically — the platform refuses to render underpowered verdicts, (c) maintenance that fits one person: zero new deployables.

End-user value is indirect but named: every experiment and release becomes gated on the five PFO guardrails (activation, TTFV, empty-deck rate, insult rate, crash-free core-loop sessions) — "protect the loop" turns from opinion into mechanism.

## 2. Problem & Context

**What exists:** ~15 server-side `record_event()` call sites into `user_events` (append-only, dual-writing `users` hot columns); a write-only legacy `wrapped_events` table; a global boolean flag map identical for every user (`GET /api/feature-flags` is an identity-less GET; reload is a manual cron-gated POST, not a TTL); one hard-coded MD5 experiment bucket (`trade.aggression_ab`) with no assignment records, exposure contract, stats, or readout — "running" forever with no way to conclude. **A dormant Sentry SDK (`@sentry/react-native`) is already compiled into the mobile binary** — initialized without a DSN in `mobile/src/observability/sentry.ts`, navigation tracing wired, user-id tagging pre-wired via `sentrySetUser` — so "adopting Sentry" means arming an existing dependency, not adding one (OQ-1). Server sessions are an in-process dict wiped on every deploy — token-present-but-dead is a routine state, not an edge case.

**What's dark:** the entire client side (install → sign-in → league-pick funnel, screen views, think-time/dwell, client errors/crashes, `push_opened`), all web/extension usage (lands as anonymous `source:"api"`), and all experiment audit data.

**Constraints that shape everything:** SQLite single-writer shared with product traffic; solo operator; App Store review + privacy nutrition labels; EAS→TestFlight latency makes server-first rollout and server-side kill authority load-bearing; a tester cohort small enough that row-level traces are often more honest than aggregates.

**Why now:** (a) the feedback pipeline ships fixes faster than the operator can tell whether they help; (b) monetization decisions are queued behind funnel numbers that don't exist; (c) NFL seasonality ramps July–August — rails must exist *before* the audience arrives, because dark weeks are unrecoverable; (d) every downstream role (pm-pfo guardrails, an-funnel reports, pm-growth experiments) blocks on this build.

**Build-vs-buy is settled** (tracking plan v2 options table): third-party SDKs killed on privacy/custody; self-hosted PostHog killed on ops burden. This PRD does not reopen it.

| Party | Role |
|---|---|
| Matt (operator) | Primary user: dashboards, experiment lifecycle, Monday ritual |
| Role skills (an-user-data, pm-pfo, ops-release, /an-experiment) | Programmatic users of the gated JSON routes |
| Testers / users | Measured subjects only; must never notice the platform exists |
| eng-* skills | Builders; maintainability is a first-class requirement |

## 3. Goals & Non-Goals

### Goals

1. **G1 — Full-funnel visibility:** funnel v2 stages 0–9 computable from real events, per weekly cohort, platform, and experiment variant; every event has exactly one authoritative firing site (migrations produce no double counting).
2. **G2 — Time & friction:** think-time, dwell, per-step latency, bottleneck/rage signatures computable per R2/R3.
3. **G3 — Release & error health:** client errors (crashes pending OQ-1) by screen × app_version; per-release regression view over the five PFO guardrails.
4. **G4 — Trustworthy experimentation:** concurrent A/B + MVT with layers, deterministic persisted assignment, exposure-based analysis, honest power/duration math, SRM checks, kill switch with stated latency bounds, permanent decision log; `aggression_ab` migrated as Experiment #1.
5. **G5 — Self-service for one person:** design→launch→monitor→decide without SQL or a deploy; event loss/duplication *measurable*, not assumed.
6. **G6 — Zero product cost:** fire-and-forget everywhere; analytics failure can never alter product behavior beyond serving defaults; SQLite→Postgres portable; zero new deployables.

### Non-Goals

- **N1:** Third-party analytics/BI SDKs (Amplitude, Mixpanel, Firebase, PostHog, Metabase). Sentry is the sole open exception (OQ-1), not in MVP.
- **N2:** Postgres migration itself (schema must port; migration is its own effort).
- **N3:** Real-time/streaming analytics; daily rollups + on-demand queries are the ceiling.
- **N4:** User-facing analytics (`wrapped_events` is frozen, not extended).
- **N5:** Monetization/entitlement events (stage 10) — specced later with pm-monetization.
- **N6 [AMEND — experimentation framework §D5 Decision 2]:** Bandits, CUPED, Bayesian machinery, stratified assignment, ML targeting — and **mSPRT in v1** (deferred, OQ-8): fixed-horizon + threshold harm alerts only. Always-valid sequential stats are subtle enough that a solo-audited implementation is wrongness risk masquerading as rigor; the framework doc's "sequential mode" recommendation is amended to v2 on approval.
- **N7:** Historical backfill or estimation of dark periods. Reports render "—", never estimates.
- **N8:** Marketing/attribution analytics (UTMs, install-source) — pre-ASO there is nothing to attribute.
- **N9:** Automated experiment rollback. Guardrail breach → alert + red banner; a human pauses (auto-rollback is a footgun at beta n).
- **N10:** Mid-session config flips (session-pinned snapshots by design); the kill switch is the only exception and only toward default.
- **N11:** Real admin-user auth system; the shared-secret gate is the honest single-operator answer until a second admin exists.
- **N12:** The `/an-experiment` skill is a separate skill deliverable; this PRD builds the API + dashboard it fronts.

## 4. Success Metrics

Measured 8 weeks after MVP (Phase 2) ships; each states how it's measured, because "operator makes better decisions" is not measurable and is excluded.

| # | Metric | Definition & measurement | Target |
|---|---|---|---|
| SM-1 | Funnel coverage | Stages 0–9 render real counts in the Waterfall report | 10/10 stages |
| SM-2 | Ingestion reliability | % of sessions gap-free via per-session monotonic `seq` analysis (FR-10) | ≥99% of sessions |
| SM-3 | Product-impact null check | p95 of 5 hottest product routes before/after P1 (one-week windows); cold-start delta on test device | No >10% p95 regression; <50 ms cold start |
| SM-4 | Duplicate visibility | Retried batches produce 0 visible duplicates (dedupe counters) | 0 in `user_events` |
| SM-5 | Taxonomy discipline | Unknown-type/prop drops after 2-week burn-in | Trend ~0; spikes → drift review |
| SM-6 | Operator self-service | Monday ritual runs off dashboard alone, no ad-hoc SQL, ≤30 min wall-clock (the program plan's 15-min agenda + platform-health section + overhead) | 6 of first 8 weeks |
| SM-7 | Experiment #1 concluded | `aggression_ab` readout (verdict + CI + SRM pass + guardrails) and recorded decision | Within 6 weeks of Phase 3 |
| SM-8 | Kill-switch drill | Pause dummy experiment → default served | Server ≤60 s; client bound verified |
| SM-9 | Time-to-answer | "Where did last week's signups drop off?" — operator self-times during the ritual, from opened dashboard (secret already entered) to stated answer, logged in the ritual notes | <5 min |
| SM-10 | Maintainability | New deployables/services to babysit | 0 (Sentry SaaS excepted if adopted) |
| SM-11 | Privacy | PII rows in `props` per monthly scripted regex audit | 0 |

Binary criterion: App Store review passes with the updated privacy nutrition label, no rejection attributable to analytics.

## 5. Requirements

### 5.1 User stories

- **US-1 (funnel):** operator opens Waterfall and sees last week's cohort stage-by-stage with drop-off counts and per-tester rows.
- **US-2 (friction):** "the app feels slow at ranking" becomes "trio decision p50 doubled in v1.8.0" via the Time/Think tab.
- **US-3 (churn):** churned users' last screen + error-adjacency names the features implicated in churn.
- **US-4 (release):** ops-release checks release health for red guardrails before promoting a build.
- **US-5 (design):** operator states a hypothesis, gets back layer/targeting/variants/metric/guardrails and an honest duration table ("MDE 10 pts needs ~34 weeks at current traffic") *before* committing. Delivered in two steps: P3 ships the design-time calculator + validation via the gated API (driven through Claude sessions); the P4 `/an-experiment` skill becomes the conversational front door.
- **US-6 (decide):** at horizon: verdict, CI, guardrail table, SRM status, segment cuts; ship/revert/iterate recorded permanently. Invalid launches (layer overlap, unknown metric key, weights ≠ 100%) are rejected with actionable errors.
- **US-7 (programmatic):** an-user-data fetches any report as JSON/CSV via gated routes.
- **US-8 (invisibility):** tester notices nothing — no jank, no battery drain, no blocked UI on airplane mode; analytics backend down = identical app behavior.
- **US-9 (deletion):** account deletion anonymizes event history to a tombstone and removes the user from experiment targeting.
- **US-10 (future-Matt at 5k MAU):** inherits a Postgres-portable schema and a permanent decision log, not ad-hoc scripts.

### 5.2 Functional requirements

**A. Envelope & storage** (tracking plan §S1)

- **FR-1** *(amended per LLD §3.1/§8.1d)*: `user_events` gains nullable columns `event_id`, `device_id` (indexed), `platform`, `screen`, `client_ts`, `experiments` (JSON), via additive migration. `event_id` uniqueness is a **full unique index** — NULLS DISTINCT is the default on both SQLite and Postgres, so unlimited v1/server NULL rows coexist legally (the earlier partial-index requirement rested on a wrong premise, and the shipped v0 baseline already carries the full index). Existing v1 call sites work unmodified.
- **FR-2:** New `identity_links` table (`device_id`, `sleeper_user_id`, `account_id`, `linked_at`), append-only, duplicates allowed; a row per successful sign-in. Pre-auth events store `user_id = 'device:<device_id>'`.
- **FR-3:** Client-event ingestion **must not** trigger `record_event()`'s dual-write to `users` hot columns, and must not create `users` rows for `device:` pseudo-identities. Every user-count/DAU/intent query excludes `device:`-prefixed ids; this filter lives once, in `backend/analytics_queries.py` (it is a named bug class, not a convention).
- **FR-4:** `wrapped_events` cutover is atomic: the five migrated event types (`tier_save`, `league_sync`, `swipe`, `trade_match`, `ranking_reorder`) stop writing there in the same deploy that starts writing them to `user_events` — no overlap window, no double counting. Table retained read-only. The one live reader (the Wrapped narrative builder in `database.py` ~3265) is **repointed to `user_events` in the same deploy** or the recap is explicitly declared frozen-at-cutover in its output — silent freezing is not an option. (When repointing, its `NARRATIVE_TYPES` `trade_accepted`/`trade_declined` — writer-less in `wrapped_events` — resolve to the live `user_events` variants, so the recap gains coverage.)
- **FR-5:** All schema is SQLAlchemy Core, valid under SQLite and Postgres dialects; no dialect-specific SQL outside (a) noted migration shims and (b) one named dialect-branched insert helper for conflict-ignore dedupe (`sqlite.insert().on_conflict_do_nothing()` / `postgresql.insert()…`), used only by ingestion.

**B. Ingestion** (tracking plan §S2)

- **FR-6:** `POST /api/events` accepts ≤50 envelopes `{event_id, event_type, client_ts, screen, props, session_id, seq}`; session token auth when present, else `device_id`. **Dead-token state (routine, not edge — server sessions are in-process and wiped every deploy):** a token the server doesn't recognize silently falls back to device-identity ingestion, never 4xx; rows land as `device:` identity and resolve through `identity_links` per FR-21's attribution rule. Server stamps identity, device headers, and the experiment snapshot per FR-31/FR-32. The `seq` field is **[AMEND — tracking plan §S2]** (envelope addition; flows back to the normative contract on approval).
- **FR-7:** **Partial-failure semantics:** per-envelope processing; response `{accepted, deduped, rejected:[{index, reason}]}`. A malformed envelope never rejects siblings. Duplicate `event_id` → `deduped`, treated as success by clients (safe to purge from queue). Dedupe accounting mechanism: executemany conflict-ignore rowcounts can't identify skipped rows — the `deduped` list comes from a `SELECT event_id … WHERE event_id IN (batch)` inside the same transaction, pre-insert, after de-duping the batch in memory (intra-batch repeats would otherwise count `accepted`).
- **FR-8:** Batch inserts execute in a single transaction with dialect-appropriate conflict-ignore dedupe on `event_id` (SQLite single-writer: 50 autocommit inserts under product load is self-inflicted lock contention).
- **FR-9:** Event-type/prop allowlist generated from tracking plan v2, enforced server-side; unknown types/props logged + counted + dropped, never inserted, never 4xx (old binaries fire stale events for months — tolerate + count). **Namespace rule:** client-fired event types may never collide with server-authoritative names (anything in `_EVENT_TO_USER_COL` / `_RANK_STREAK_EVENTS` / the server-fired taxonomy) — product queries over `user_events` (streaks, engagement leaderboards) live outside `analytics_queries.py` and are protected only by this rule; enforced at allowlist build (CI-checkable, OQ-5).
- **FR-10:** Clients attach a per-session monotonic `seq` to every envelope — the mechanism that makes loss (SM-2) measurable rather than assumed (part of the FR-6 [AMEND] to tracking plan §S2).
- **FR-11:** Rate limit 600 events/hr/device (config-tunable). Over-limit: **silently accept-and-drop with a counter, return 200** — never 429, which teaches offline queues to retry-storm.
- **FR-12:** `client_ts` clamp: if |`client_ts` − `occurred_at`| > 48 h, store with `props.ts_suspect=true`; think-time aggregates exclude suspect rows. `occurred_at` governs ordering; `client_ts` governs intra-session deltas only.
- **FR-13:** Ingestion failures are silent to users, loud to the operator: all counters (accepted/deduped/dropped-unknown/dropped-ratelimited/failed) surface on `GET /api/admin/analytics/health`.

**C. Client SDK modules** (tracking plan §S2–S3)

- **FR-14:** Mobile (`mobile/src/api/events.ts`), web (`web/js/events.js`), extension (background) implement one contract: in-memory queue → flush at 10 s / 20 events / app-background; persistent offline queue (AsyncStorage / localStorage / `chrome.storage.local`); **drop-oldest at 500 except events tagged `funnel_critical`** (first `app_opened` per install, `signin_*`, `experiment_exposed`), which drop last — naive drop-oldest destroys exactly the rarest, highest-value rows under backlog.
- **FR-15:** Fully fire-and-forget: all SDK errors swallowed (counted locally at most); no awaited calls on any interaction path; flush off the critical path; replay after crash is safe via `event_id` idempotency. An analytics bug must be unable to white-screen the app.
- **FR-16:** `device_id` = `dev_` + UUID: Keychain (iOS), localStorage (web), `chrome.storage.local` (extension). Documented caveats: Keychain survives app deletion → stage-0 = *first-open-per-device*, reinstalls invisible; web `device_id` is best-effort (per-origin, clearable) → web stage-0 renders with a caveat badge.
- **FR-17:** `session_id` = client UUID rotated after 30 min inactivity or cold start; all client events carry `device_id` + `session_id` + `seq`.
- **FR-18:** Clients emit the tracking-plan-v2 client taxonomy for their surface — lifecycle, pre-auth funnel, dwell/think props (`decision_ms`, `dwell_ms`), trade-surface events, `push_opened`, extension events. The tracking plan is the normative contract, incorporated by reference; event names + envelope are recorded in `docs/cross-client-invariants.md` as a cross-client contract.
- **FR-19:** Kill switches: `analytics.client_events` (client emission), `analytics.ingest` (server endpoint), `experiments.engine`, `analytics.dashboard` — each independently disables its stage. **Honest latency bounds:** server-side switches take effect at the next manual `POST /api/feature-flags/reload` (≤minutes, operator-driven — there is no TTL today); client emission stops at the next config fetch, which P1 makes bounded via FR-35's foreground refetch. The SDK treats a **missing** `analytics.client_events` key as **off** (default-dark), and the key must never enter the mobile store's baked `LAUNCHED_FLAG_DEFAULTS` — otherwise first-boot-before-fetch emits and a kill can be masked by cache. Runbook note: to kill **one** experiment fast, pause it (≤60 s via FR-38); the `experiments.engine` flag is the slower, manual-reload hammer.
- **FR-20:** Server-fired dark/mis-routed events light up at existing routes (no client release): `league_synced`, `ranking_method_changed`, `tier_save`→`user_events`, `ranking_reorder`→`user_events`, `quickset_completed`, `quickrank_completed`, `anchor_answered`, `feedback_submitted`, `trades_generated`, **`calc_trade_evaluated`** (without it the WAT north star undercounts calculator-only users and the "all-⚡" rollout claim is false).

**D. Identity** 

- **FR-21:** Stitching is resolved at **query time** via `identity_links` — events queued under `device:` identity when sign-in succeeds are never rewritten client- or server-side; no backfill job in v1. Shared devices legitimately map one `device_id` to N accounts. **Attribution rule: nearest link at-or-before the event, else first link after it** — dead-token fallback rows (FR-6) are *post*-sign-in events, so a naive first-after rule would strand every post-deploy flush as `device:` rows and silently leak signed-in activity out of DAU/funnel stages 2+. R1's per-tester trace surfaces ambiguity rather than hiding it. Rule documented in the data dictionary.
- **FR-22** *(amended per LLD §5.1 RC-5)*: `account_deleted` anonymization is one transaction rewriting `user_id`/`device_id` to a per-account tombstone hash across `user_events`, `identity_links`, `experiment_assignments`, **and `wrapped_events`** (the frozen table's pre-cutover history is still rendered by the repointed narrative reader — leaving it raw would leak deleted users' actions); the deletion response also instructs the client SDK to purge its local analytics queue; aggregates survive, identity does not; the tombstoned unit stops matching any targeting next session. On-handset Keychain `device_id` persists (unreachable) — post-deletion re-signup looks like a new user on a familiar device; disclosed behavior, routed to legal-privacy (OQ-3).

**E. Reports & dashboard** (program plan catalog)

- **FR-23:** `backend/analytics_queries.py` implements R1–R8 + R10 as parameterized server-side SQL returning JSON (R9 = experiment readouts, delivered by FR-43/FR-46 on the Experiments tab in P3); the dashboard renders and computes nothing. Every report exportable `format=json|csv`. **R8 (the PFO report — TTFV stage decomposition with grade thresholds per the pm-pfo spec) is included in P2**: it composes from R1/R2 queries and is the report OQ-9's threshold recalibration presumes.
- **FR-24:** `GET /api/admin/analytics/<report>` gated by CRON_SECRET presented as a **header** (never a query param — secrets in URLs land in Render logs and browser history), constant-time compare, rate-limited, fail-closed in prod per existing convention. **Reuse the existing `X-Cron-Secret` header name** (`_require_cron_auth`) — one secret, one name; do not mint a second alias. The dashboard page takes the secret once into `sessionStorage`.
- **FR-25:** Dashboard `web/admin/analytics.html`, Chalkline-compliant (tokens per design system; viz colors must not collide with position/tier hexes per cross-client invariants). Tabs: Waterfall · Time/Think · Bottlenecks · Churn · Releases · Adoption · Engagement · **PFO** · Experiments · Health. **P3 Experiments-tab scope, stated so no builder guesses:** monitor cards + decision recording + read-only design-calculator output; experiment *creation* is via the gated API (driven through Claude sessions) until the P4 `/an-experiment` skill lands.
- **FR-26:** First-class insufficiency states everywhere: "—" for unshipped events or pre-instrumentation windows (never zero, never estimates); "n too small (<20)" badges instead of percentages; all rates alongside raw counts; per-tester row-level trace on R1 at beta scale.
- **FR-27:** Waterfall segmentation: platform, sign-in method, ranking method, league_count, experiment variant. Demo-mode sessions (`demo_entered`) and operator/tester-allowlist devices are excluded from cohort metrics by default (query-toggleable).
- **FR-28:** Release health computes the five PFO guardrails per `app_version` vs prior, red at >10% relative degradation, per the PFO spec.
- **FR-29:** Health tab (FR-13 counters + SM-2 gap sampling + last-24h event volume by type) so the operator can trust or distrust any given week.

**F. Experimentation engine** (framework §D1–D7)

- **FR-30:** Tables `experiments`, `experiment_assignments` (PK unit+key+version, conflict-ignore on concurrent first evaluation), `experiment_metric_snapshots` per framework §D7; append-only except `experiments.status`.
- **FR-31** *(amended per LLD §4.2/§8.1a — framework §D2's single formula cannot deliver in-layer exclusivity)*: Deterministic layered assignment is **two-stage**: `layer_bucket = sha256(layer_salt:unit_id) % 10000` (experiment-independent — places the unit once per layer, making disjoint bucket ranges actually mutually exclusive) then `variant_bucket = sha256(layer_salt:experiment_key:version:unit_id) % 10000` for the variant split (version in the preimage so revisions don't re-assign the same units to correlated arms). Targeting predicate evaluated **before** hashing against the attribute registry; non-matching users get default and are excluded from analysis (not counted as control); assignments persisted on first evaluation. Server-only evaluation; clients never hash.
- **FR-32 [AMEND — experimentation framework §D4]:** The `experiments` envelope snapshot is stamped on **funnel-stage events and events fired from surfaces inside a running experiment's declared scope** — not on every row (bloating every `screen_viewed` forever is a join-free-query optimization applied indiscriminately). All other analysis joins `experiment_assignments`. Framework doc to be amended on approval.
- **FR-33:** Reserved layers seeded (`onboarding`, `ranking`, `trades_ui`, `engine`, `growth`); exactly one layer per experiment; launch validation rejects in-layer bucket overlap, unknown metric keys (must resolve to the program-plan catalog), unknown targeting attributes, **attributes unavailable for the experiment's unit type**, missing exposure surface, weights ≠ 100%.
- **FR-33b — v1 targeting attribute registry** (the concrete table FR-31/FR-33 validate against; extending it is a spec change to this PRD):

  | Attribute | Source | Available for |
  |---|---|---|
  | `platform`, `app_version`, `os_version`, `device_type` | request headers | device + account units (incl. pre-auth) |
  | `is_tester_allowlist` | config list keyed by device_id/user_id | device + account |
  | `signup_week`, `verified`, `invited_by_present` | `users` row | account units only |
  | `league_count`, `scoring_formats` | `users`/league tables | account units only |
  | `ranking_method` | `users` pref | account units only |
  | `activation_stage` | `users` hot columns (`signup_at`, `last_rank_at`, `last_match_seen_at`… — **not** an event scan; hot columns are the cheap evaluation-time proxy) | account units only |
  | `wat_active_last_28d` | `users.last_*_at` hot columns | account units only |

  Consequence stated plainly: **onboarding-layer (device-unit) targeting is structurally limited to header-derived attributes + allowlist** — pre-auth users have no `users` row (FR-3 forbids creating one). Validation enforces this; the framework doc's attribute list is amended accordingly **[AMEND — experimentation framework §D2]**.
- **FR-34:** Unit = `account_id` when known else `device_id`, fixed at creation; onboarding-layer experiments must use `device_id` (validation-enforced) to avoid mid-experiment unit swaps; client-UI experiments without an `app_version ≥` predicate get a validation warning (old binaries lack the variant code).
- **FR-35:** **Config delivery contract (specified because the current `GET /api/feature-flags` is identity-less and cannot resolve per-unit experiments):** clients send `X-Device-Id` on **every** config fetch, plus the session token when one exists; the server resolves unit = account/session identity when recognized, else `device_id`, and returns `{flags, experiments:{key:variant}, configs}` as **additive keys on the existing endpoint** (old-client parsers tolerate additive keys — verified per OQ-6). Per session class: pre-auth → device-unit resolution (the onboarding layer's path); account-only sessions (which never call session_init) and Sleeper-league sessions → the same config fetch carries their identity. **P1 adds a foreground-refetch of this config (throttled to ≥30 min since last fetch)** — this is the mechanism that makes FR-19/FR-38's client bounds real, so it must ship in the P1 binary for the P3 bounds to hold. Snapshot pinned per client `session_id` (FR-17's 30-min-rotation session, not the server token); changes apply at next rotation/foreground-refetch boundary. Clients get `useVariant('exp_key')` (mobile) / equivalent (web) reading only the snapshot; variant UI ships dark and activates server-side.
- **FR-36:** Server call sites consume the same evaluator; engine-layer experiments apply per-variant `model_config` overlays — the mechanism migrating `aggression_ab` as **Experiment #1: sha256 re-bucket, new version; no MD5-bucket continuity** (unverifiable, not worth the code); prior `aggression_variant` props remain analyzable as an archived v0 readout, never blended.
- **FR-37:** `experiment_exposed` fires at first render/effect of the varied surface, once per unit×experiment×**client `session_id`** (FR-17's 30-min-rotation session — the term "session" in exposure dedupe and snapshot pinning always means the client session, never the server token, which re-mints on foreground). Client-deduped per session key; readout queries additionally dedupe on (unit, exp, session_id) against crash-restart double-fires. Analysis population = exposed units; assignment-without-exposure reported separately as dilution.
- **FR-38:** Status machine `draft → running → (paused) → stopped → decided(ship|revert|iterate)`; transitions logged with actor + reason. Pause/stop serves default at all server call sites within ≤60 s (in-process experiment-config cache TTL — experiments get a real TTL even though boolean flags today reload manually). Clients pick it up at the next config fetch: cold start or the FR-35 foreground-refetch (≥30-min throttle), bounding worst-case client exposure to one backgrounding cycle **once the P1 binary is adopted**; for binaries predating P1 the bound is next cold start — stated honestly in the runbook.
- **FR-39:** In-place mutation of `targeting_json`/`variants_json` on a running experiment is **rejected by the API**; edits create a new version with reset metrics; prior readout archived.
- **FR-40:** Evaluator fail-open: any error → default experience + server counter (+ `client_error` client-side). An evaluator bug can never brick the product.
- **FR-41:** Permanent experiment log (hypothesis, spec, dates, verdict, decision, rationale) queryable via admin API — the org's memory of what worked.

**G. Stats engine**

- **FR-42:** **Design-time calculator (runs before launch is allowed):** per-arm n = `2·(z_{α/2}+z_β)²·p̄(1−p̄)/MDE²` (α=.05, power .80 defaults); eligible-traffic-rate from trailing 28 days of units matching targeting + hitting the exposure surface; outputs required n/arm, predicted weeks, and MDE-achievable-at-2/4/8-weeks; mandatory beta-honesty banner. Predicted duration >26 weeks requires explicit `override_underpowered: true` with logged rationale.
- **FR-43:** **Read-time:** two-proportion z (proportions) / Welch's t on p99-winsorized values (continuous); 95% CI on absolute + relative lift; Bonferroni for >2 arms or >1 primary-eligible metric; χ² SRM check — p<.001 → red banner + verdict suppressed while the experiment stays `running`. Verdict badge withheld until horizon; below minimum n the engine renders the honesty banner instead of a p-value. Implementation note for the LLD: `requirements.txt` has no scipy/numpy — the LLD decides "add scipy" vs hand-rolled special functions with golden-value tests (OQ-10).
- **FR-44:** Harm monitoring v1 = per-guardrail thresholds: any of the five PFO guardrails worse than its configured relative band with n ≥ minimum → yellow alert row on the experiment card (no always-valid-p pretense; mSPRT deferred per N6/OQ-8). A guardrail breach beyond the band marks the experiment "rollback candidate" regardless of primary-metric result.
- **FR-45:** Every experiment auto-attaches the five PFO guardrails; metrics are selected by key from the program-plan catalog only — free-typed metrics rejected.
- **FR-46:** Readouts/monitor cards compute from `experiment_metric_snapshots` — populated on-request at beta scale (cron job is the Postgres-scale upgrade; same schema either way, OQ-7) — never from live full-table scans on dashboard page-load.

**H. Privacy & lifecycle** (tracking plan §S4)

- **FR-47:** Server-side PII denylist at ingestion: no emails, names, tokens, push tokens, device serials/IDFA, free-text user input in `props`; `client_error.message` regex-scrubbed + truncated to 200 chars client-side *and* re-validated server-side.
- **FR-48:** Default-deny evolution: new event types/props require a tracking-plan doc PR; the server allowlist is generated from/checked against it (machine-readable taxonomy file shared with clients + CI check is OQ-5).

### 5.3 States & edge cases

- **E-1 Offline/airplane:** persistent queue; flush on reconnect; multi-day-late batches ordered by `occurred_at`, deltas by `client_ts` (FR-12 guard).
- **E-2 Backend down / 5xx:** bounded backoff, requeue or drop; app unchanged (US-8).
- **E-3 Duplicates:** `event_id` dedupe (FR-7/8); dashboards never double-count.
- **E-4 Pre-auth→sign-in stitch & shared devices:** FR-21 query-time rule; ambiguity surfaced in trace view.
- **E-5 Multi-device users:** `account_id` unit ⇒ consistent variants across devices; device-unit experiments accept divergence by design.
- **E-6 Mid-session stop:** snapshot holds ≤ one backgrounding cycle (FR-38); readouts exclude post-stop exposures.
- **E-7 App-version skew:** FR-34 validation warning; server tolerates stale events from old binaries (FR-9).
- **E-8 SRM:** red banner, verdict suppressed, investigation checklist (assignment vs exposure vs targeting bug) linked from the banner.
- **E-9 Tiny cohorts:** counts + "n too small" badges; no fake p-values (FR-26/43).
- **E-10 Clock skew:** FR-12.
- **E-11 Demo mode & operator traffic:** excluded by default from funnels/experiments (FR-27).
- **E-12 Deletion mid-experiment:** FR-22; pre-deletion exposures remain under tombstone.
- **E-13 Crash-restart exposure double-fire:** FR-37 rollup-level dedupe.
- **E-14 Reinstall/Keychain persistence:** FR-16 documented semantics (stage-0 = first-open-per-device).
- **E-15 Dead session token (routine post-deploy state):** FR-6 silent device-identity fallback + FR-21 at-or-before attribution keeps post-deploy flushes attributed to the signed-in user; never a 4xx, never a stranded `device:` row for a user with any link history.

### 5.4 Non-functional requirements

- **NFR-1 (client perf):** <50 ms cold-start delta; zero synchronous work on interaction paths; verified per SM-3 before promote.
- **NFR-2 (server perf):** **Enable WAL mode — it is off today** (`database.py:43`'s comment claims `connect_args` enables it; `{"check_same_thread": False}` does no such thing — spec the on-connect `PRAGMA journal_mode=WAL` listener in the LLD); batch insert p95 <50 ms at beta traffic; sustained 10× expected event traffic must not raise product-route p95 >10%; report queries p95 <3 s at 1M rows (indexes in LLD; rollup+prune plan written, not built, trigger at 1M rows).
- **NFR-3 (reliability):** fail-open everywhere; no code path where analytics/experiment failure alters product behavior beyond defaults.
- **NFR-4 (privacy/compliance):** **App Store privacy nutrition label updated for P1** — first-party collection of usage data + identifiers "linked to user" is a label change even with no third-party SDK; no ATT required (no cross-app tracking, no IDFA). legal-privacy reviews the label diff + privacy-policy delta before the P1 TestFlight build; Sentry (if adopted) triggers a second review. Extension store disclosure forms budgeted in P4.
- **NFR-5 (security):** entire admin surface CRON_SECRET-gated fail-closed (FR-24); no analytics data readable by unauthenticated or tester-level routes; secret-rotation procedure in the runbook.
- **NFR-6 (maintainability):** zero new deployables; new backend module boundaries (`analytics_queries.py`, evaluator/stats modules) documented in `docs/architecture.md` + one ADR (first-party analytics + layered experimentation), landing with P0 so the decision trail predates dependent code.
- **NFR-7 (portability):** all DDL/queries dual-dialect (FR-1/FR-5).
- **NFR-8 (design):** Chalkline conformance (FR-25); chart specs may need a small ux-design addendum (D-4).
- **NFR-9 (docs):** each phase's PR lands its doc updates (data-dictionary, api-reference, config-reference, cross-client-invariants, architecture/ADR) — drift is a launch blocker per repo convention.
- **NFR-10 (testability):** eng-qa gets Maestro-driven event assertions (flow → expected rows), evaluator determinism tests (same unit+key ⇒ same variant; cross-layer independence χ²), kill-switch drills (SM-8), and migration double-count checks (FR-4) in the platform's own suite.

## 6. Scope & Phasing

Server-first (no app-store dependency), then mobile, then the rest. **Events are perishable; reports are not** — if a phase slips, cut dashboard tabs, never the SDK.

| Phase | Contents | Vehicle | Exit criterion |
|---|---|---|---|
| **P0 — Server truth** | FR-1..5, FR-20, health counters (FR-13), ADR | Backend deploy | Migrated events single-sourced, zero `wrapped_events` writes, no double counting across cutover |
| **P1 — Ingestion + mobile SDK** | FR-6..19, FR-21..22; privacy-label update (NFR-4) | Backend deploy + TestFlight build | SM-2/3/4 green; stages 0–3 populated; operator-devices-first then all testers |
| **P2 — Dashboard + reports (MVP cut line)** | FR-23..29 (incl. R8/PFO tab) | Backend/web deploy | R1/R2/R5/R7/R8/R10 render real data; SM-1, SM-6, SM-9 green; Monday ritual live |
| **P3 — Experiment engine** | FR-30..46; Experiment #1 | Backend deploy (client hooks shipped dark in P1 binary where ready) | SM-7, SM-8 drills pass before any experiment beyond #1 launches |
| **P4 — Long tail** | Web + extension SDK emission; `/an-experiment` skill; Sentry if OQ-1 yes; snapshot cron; R3/R4/R6 full builds | Web deploy, extension store review | Web/extension rows flowing; skill drives one real design |

**MVP = end of P2.** Experimentation is deliberately not in MVP — measurement must be trusted before experiments read from it.

## 7. Dependencies & Risks

**Dependencies:** D-1 TestFlight cadence (eng-mobile/ops-release) gates P1/P3 client bits; D-2 session/auth + flag endpoint (FR-35 extends it; old-client parser check OQ-6); D-3 CRON_SECRET set in Render (fail-closed without it); D-4 Chalkline chart-spec addendum (ux-design); D-5 tracking plan v2 as frozen normative taxonomy; D-6 legal-privacy sign-offs (label diff NFR-4, anonymization OQ-3); D-7 eng-qa Maestro event-assertion harness.

**Risks (each with mitigation):**

- **R-1 Beta-scale underpower theater** (highest): operator runs UI experiments that can never conclude, loses faith. → Mandatory design-time honesty math + underpowered-launch override logging (FR-42); Experiment #1 is a high-frequency engine experiment (swipe/card units in the thousands — concludes fast); pre-scale value framed as harm-stops + launch-readiness in the ritual.
- **R-2 SQLite contention:** event writes vs product writes on one file. → FR-8 single-transaction batches, WAL verified, SM-3 hard gate, 10× headroom test (NFR-2); Postgres is the pressure valve and nothing here blocks it.
- **R-3 Migration double counting:** wrapped_events overlap or v0 `aggression_variant` blended. → FR-4 atomic cutover + FR-36 versioned separation + eng-qa count checks across the cutover week.
- **R-4 Identity mess** (shared devices, reinstalls, deletion residue). → FR-16/21/22 specify behavior instead of assuming 1:1; per-tester trace makes anomalies visible; imprecision documented; funnel unit switches to user at stage 2, confining distortion to stages 0–1.
- **R-5 App Store review:** wrong privacy label = rejection. → NFR-4 legal-privacy review before the P1 build; Sentry deferred to its own review cycle; extension disclosures budgeted.
- **R-6 Schema drift:** clients shipping unapproved props; old binaries firing stale events. → FR-9 tolerant server + counters; FR-48 default-deny; SM-5 watched; OQ-5 CI check if convention fails.
- **R-7 Shared-secret admin surface:** one secret gates cron + feedback admin + all behavioral data. → FR-24 header-only transport, constant-time compare, rate limit, rotation runbook; revisit real auth at first non-Matt admin (N11).
- **R-8 Solo-operator surface creep:** ten tabs + stats engine + three SDKs exceeds one person's upkeep. → Zero new deployables; queries centralized; reports degrade to "—" not errors; P4 items stay unbuilt until pull exists; R3/R4/R6 may lag P2 (ritual minimum is R1/R2/R5/R10).
- **R-9 Dashboard-before-data temptation.** → Phase order (events first); FR-26 no-placeholder rule.

**Open questions (operator decisions; recommendations carried from strategy docs):**

- **OQ-1:** **Arm the dormant Sentry SDK already compiled into the binary** (set DSN; the dependency, init scaffold, and user-id tagging already ship)? *Rec: yes, P4*, after first-party is proven. The legal-privacy review gates the **DSN activation**, not the dependency; it must also confirm dormant-SDK-without-DSN requires no privacy-label disclosure today, and that the pre-wired `sentrySetUser` (Sleeper id + username) is acceptable or gets stripped to pseudonymous id at arming. Until armed, guardrail #5 is `client_error(fatal)` only and readouts label it "JS-errors only".
- **OQ-2:** Adopt funnel v2 + WAT north star (context.md amendment)? *Rec: yes* — reports assume it.
- **OQ-3:** legal-privacy: tombstone anonymization satisfies privacy.html? Keychain device_id surviving deletion — disclose or engineer around? Any data-export obligation pre-launch? Blocks FR-22 sign-off only.
- **OQ-4:** Churn threshold 14 days? *Rec: yes*, revisit in-season.
- **OQ-5:** Machine-readable shared taxonomy file + CI check (server allowlist + client constants) in P2, or doc-convention only? *Rec: revisit at P2 exit based on SM-5.*
- **OQ-6:** Verify old mobile/web parsers tolerate additive keys on `GET /api/feature-flags` / session-init (FR-35). *Owner: eng-mobile, P1.*
- **OQ-7:** Snapshot compute on-request vs daily cron? *Rec: on-request now; schema unchanged either way.*
- **OQ-8:** Is threshold-based harm monitoring acceptable v1 (vs mSPRT)? *Rec: yes; revisit only if a real near-miss shows thresholds insufficient.* (pm-pfo to confirm.)
- **OQ-9:** PFO grade thresholds recalibrate after 4 weeks of P2 data (owner pm-pfo; same meeting as first monthly funnel audit).
- **OQ-10:** Stats special functions: add scipy vs hand-roll with golden-value tests (FR-43). *Owner: LLD.*

## 8. Rollout & Measurement

1. **P0** deploys as a normal Render push (additive, invisible); verify via gated routes + row counts + cutover count-consistency before trusting numbers. ADR lands here.
2. **P1** ships the SDK in the next TestFlight build behind `analytics.client_events` (armed kill switch): operator devices 48 h (Health tab: SM-2/3/4) → all testers. Privacy-label + policy diff cleared by legal-privacy **before** submission. No tester comms needed (nothing visible changes).
3. **P2** dashboard goes live (no user exposure); first full Monday ritual starts the SM-6 clock; program plan's "measurable today vs gaps" flips to all-⚡ and is verified against the catalog.
4. **P3** activates the evaluator with zero experiments, runs the SM-8 kill drill, then migrates `aggression_ab` as Experiment #1 (new version, archived v0 readout). No further experiments until #1's readout renders and the drill passes.
5. **P4** on observed pull only: dashboard latency → snapshot cron; churn-diagnosis crash blindness → forces OQ-1; web/extension SDK closes the `source:"api"` blindness; extension review latency budgeted.

**Standing measurement of the platform itself:** SM table reviewed weekly in the ritual for 8 weeks ("platform health" section of R10), then folded into the Health tab + monthly audit (which also runs the SM-11 PII sweep and the funnel-definition drift check). Every rollback path is flag-off-without-deploy except P0's cutover, whose revert deploy is rehearsed in the P0 PR.

**Exit criterion for this PRD:** the operator answers "where do users drop off / did the release regress / did the change help" from the dashboard alone, in one sitting, with numbers he trusts — and Experiment #1 reads `decided` in the permanent log.
