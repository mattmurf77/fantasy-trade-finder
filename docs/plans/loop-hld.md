# High-Level Design — FTF Self-Training Loops (Plan 1)

> **Purpose:** the architectural bird's-eye view of the five FTF self-training loops — what each loop is, what's in scope, how it composes with the existing backend, and the trade-offs taken. Read before any change that touches loop telemetry, rollups, experiments, or guardrails.
>
> **Companions:** [`loop-lld.md`](loop-lld.md) (column-level schemas, module maps, signatures, config keys) and [`loop-prd.md`](loop-prd.md) (requirements, tests, work breakdown). Spec source: `~/Documents/Claude/Skills/files/loop-plans-ftf-gmb-dfs-bb.md` § Plan 1.
>
> **Status:** design only — no code changes in this package.

---

## Table of Contents
- [System overview](#system-overview)
- [1A — Trade-Engine Quality Loop](#1a--trade-engine-quality-loop)
- [1B — Growth Loop](#1b--growth-loop)
- [1C — Activation & Onboarding Loop](#1c--activation--onboarding-loop)
- [1D — Retention Loop](#1d--retention-loop)
- [1E — UX, Performance & Consistency Loop](#1e--ux-performance--consistency-loop)
- [Shared infrastructure](#shared-infrastructure)
- [Sequencing](#sequencing)
- [Outstanding / Known Gaps](#outstanding--known-gaps)

---

## System overview

### What this is

Five closed loops (instrument → measure → hypothesize → ship one change → re-measure) layered onto the existing Flask backend. One model loop (1A, the trade engine) and four product loops (1B growth, 1C activation, 1D retention, 1E UX/perf/consistency). They share four pieces of new infrastructure:

1. **Event plumbing** — the existing `user_events` table + `record_event()` dual-write, extended with new event types and a client ingestion route (`POST /api/events`) so web/mobile/extension can emit loop events that the server can't observe (card detail views, shares, nudge dismissals).
2. **Proposal & state logging** — `league_state_snapshots` + `engine_proposal_log`, written at trade-generation time. This is the offline-replay substrate: log now, replay capability arrives free later.
3. **Experiment harness** — `config/experiment.json` (exactly one live experiment) overlaying one flag in `config/features.json` with deterministic per-user bucketing, recorded in `experiment_assignments`.
4. **Rollup + report layer** — a daily idempotent rollup job (`loop_metrics.rollup_daily`, run from the existing `/api/cron/daily-tick`) writing `loop_rollups`, with admin report endpoints per loop and a `guardrails` check that flags breaches.

### Scope

- **In scope:** telemetry schemas, rollup jobs, per-loop reports, A/B harness, fairness audit, guardrails (nudge fatigue, notification opt-out), CI invariant checks, perf budgets + synthetic checks, cold-start tracking, human review checklists.
- **Out of scope:** the replay *engine* (schema only — see 1A trade-off), any change to trade-engine math itself, multi-variant experiments (one live variant at a time, by design), external analytics vendors (telemetry is the operator's own product data, in the operator's own DB), automated shipping of engine changes (every ship is human-gated).

### Architecture

```
 Clients (web / mobile / extension)          Backend (Flask, backend/)
 ──────────────────────────────────          ─────────────────────────────────────────
 emit: card view-detail, share,              POST /api/events ──► record_event()
       nudge shown/dismissed,                                      │
       invite sent  (client-tagged)                                ▼
                                             ┌──────────── user_events ─────────────┐
 Trade generation (server-side)              │  (existing, + new event types)        │
 ──────────────────────────────              └────────────────┬──────────────────────┘
 _run_trade_job ─► log_trade_impressions     trade_impressions │ trade_decisions
        │          (+engine_version,                │          │ trade_matches
        ▼           variant, trade_id)              ▼          ▼
 loop_logging.snapshot_league_state    ┌──────────────────────────────────────┐
        │                              │ loop_metrics.rollup_daily()          │
        ▼                              │  (cron daily-tick; idempotent upsert)│
 league_state_snapshots ◄── FK ──      └───────────────┬──────────────────────┘
 engine_proposal_log                                   ▼
                                                  loop_rollups
 experiments.variant_for(user) ──►                     │
 experiment_assignments                                ▼
                                       GET /api/admin/loop/{engine,growth,
 config/experiment.json ─► feature_flags    activation,retention}-report
 config/features.json   ─►  resolution      GET /api/admin/loop/guardrails

 CI / deploy time:  check_invariants.py · synthetic_check.py (perf budgets)
 Human cadence:     quarterly reward-hacking review · per-release persona walkthroughs
```

### Design trade-offs (system-wide)

- **Reuse `user_events` instead of a new event store.** It's already client-tagged (`device_type`, `source`, `props`), indexed for analytical scans, and dual-written for hot reads. New loops add event *types*, not tables — minimum new surface.
- **Rollups in Python, not SQL JSON functions.** Matches the existing `load_engine_telemetry` pattern; keeps SQLite/Postgres portability (no dialect-specific JSON SQL).
- **One generic `loop_rollups` table, not one table per metric.** Metrics will churn; dims live in a canonical-JSON column with a uniqueness key. Cheap to extend, trivially portable.
- **Privacy: IDs only in payloads.** Event props and state snapshots carry Sleeper user IDs and player IDs — never usernames, display names, or device identifiers beyond the existing coarse enums.

---

## 1A — Trade-Engine Quality Loop

### What this is

The model loop. The engine has no ground truth, so the reward signal is behavioral: a **pre-registered weighted action score** per served proposal (dismiss < view-detail < save < share/send), computed per engine version and per experiment variant, with fairness as the standing guardrail and a quarterly human review as the check the metric can't run on itself.

### Scope

- **In:** action-score metric (weights in `model_config`, revisited quarterly at most), telemetry rollup + per-engine-version report, league-state + proposal logging (replay schema), feature-flag A/B harness, automated fairness audit, quarterly reward-hacking review checklist.
- **Out:** the replay runner itself; automated weight tuning; any engine math change (those are *hypotheses the loop produces*, shipped separately through the normal plan process).

### Architecture

```
serve deck ──► trade_impressions (+trade_id, engine_version, variant, job_id, client)
     │    └──► engine_proposal_log ──FK──► league_state_snapshots (hash-deduped)
     ▼
user acts ──► trade_decisions (like/pass)              ┐
          ──► user_events: trade_card_view_detail,     ├─► rollup_daily
                            trade_card_shared          ┘      │
                                                              ▼
              action_score = Σ w_action · n_action  per (engine_version, variant)
                                                              │
   fairness_audit.py (per release + daily guardrail)          ▼
   value-delta distribution bounds; 1-for-1 gate seed   engine-report endpoint
```

### Major components

| Component | Where | Role |
|---|---|---|
| Action-score weights | `model_config` (`action_w_*`) | Pre-registered reward weights; admin-tunable but governed by the quarterly-review rule |
| Impression enrichment | `trade_impressions` ALTERs | `trade_id`, `engine_version`, `variant`, `job_id`, `client` columns make every shown card attributable |
| Proposal/state log | `engine_proposal_log` + `league_state_snapshots` | Full replay substrate: deck + frozen league state per generation job |
| Engine versioning | `loop_logging.current_engine_version()` | Deterministic string from active flags (`legacy`/`v2`/`v3`+modifiers) + config hash |
| Rollup + report | `loop_metrics.py` | Daily action-score rollup; `GET /api/admin/loop/engine-report` |
| Fairness audit | `backend/scripts/fairness_audit.py` + guardrail | Distribution bounds on proposal value deltas; the 1-for-1 fairness gate is the seed check |
| Reward-hacking review | `docs/loop-reviews/quarterly-reward-hacking.md` | Human checklist; stratified proposal sample; sign-off log |

### Key flows

1. **Logging:** `_run_trade_job` finishes → snapshot league state (deduped by content hash) → write proposal-log row (job, engine version, config hash, variant, snapshot FK, ordered deck JSON) → write enriched impressions.
2. **Scoring:** daily rollup joins impressions ↔ decisions ↔ view/share events on `trade_id` (fallback: give/receive-set join for legacy rows) → action score per `(engine_version, variant, client, day)`.
3. **Audit:** fairness audit reads recent proposal-log decks, computes consensus value-delta distribution, asserts bounds (incl. the 1-for-1 subset); breach → guardrail flag + nonzero exit in release mode.
4. **Quarterly:** human reviews a stratified sample of high-action-score proposals against the checklist; only then may weights be revised.

### Design trade-offs (this loop)

- **Behavioral reward, not "trade quality."** Accepted-in-league outcomes are too sparse and lagged; action score is dense and available now. The fairness audit + human review exist precisely because action score is gameable (flashy-lopsided proposals).
- **Snapshot dedup by hash.** League states change slowly between generation jobs; hashing the canonical payload avoids storing near-identical multi-KB blobs per job. Cost: a hash computation per job — negligible next to generation itself.
- **`trade_id` joins over set-equality joins.** The existing labeling join (give/receive sets) survives for old rows, but a stable `trade_id` per card makes every downstream join trivial and index-friendly.

---

## 1B — Growth Loop

### What this is

League-unit virality instrumentation: the invite funnel (nudge shown → invite sent → accepted → activated) measured end-to-end, a weekly viral-coefficient report, and a nudge-fatigue guardrail. The cold-start invite nudge just shipped — this loop instruments it before anyone iterates on it.

### Scope

- **In:** funnel event schema, weekly viral-coefficient (k) report, frequency cap, dismiss-rate kill metric.
- **Out:** new nudge surfaces or copy variants (those are the experiments the loop will run later, via the 1A harness), incentive mechanics.

### Architecture

```
nudge surfaced ──► user_events: invite_nudge_shown   (client-tagged)
user dismisses ──► user_events: invite_nudge_dismissed
user invites  ──► user_events: invite_sent  (channel in props)
invitee joins ──► users.invited_by (existing)  ⇒ "accepted"
invitee ranks ──► user_events: ranking_complete_first_time ⇒ "activated"
                                   │
                                   ▼
        rollup_daily ──► weekly funnel stages + k = i · a · v
        guardrails  ──► dismiss-rate kill metric; server-side frequency cap
```

### Major components

| Component | Where | Role |
|---|---|---|
| Funnel events | `user_events` (4 new/reused types) | Stage instrumentation, client-tagged |
| Acceptance attribution | `users.invited_by` (existing) | Joins invitee signup to inviter |
| Viral-coefficient report | `loop_metrics.growth_report()` + endpoint | Weekly k and per-stage conversion |
| Frequency cap | `model_config: nudge_max_per_user_per_week` + server check | Hard cap before a nudge renders |
| Kill metric | guardrails: trailing dismiss rate vs `nudge_dismiss_kill_rate` | Breach flags the nudge for disablement |

### Key flows

1. Weekly report: per ISO week — nudges shown, invites sent, accepts (new users with `invited_by` resolving to an inviter active that week), activations (first ranking session); `k = invites_per_active_user × accept_rate × activation_rate`.
2. Guardrail: daily rollup computes trailing-14d `dismissed / shown`; above threshold → breach row in the guardrails report (human kills the nudge flag; no auto-disable in v1).

### Design trade-offs

- **Acceptance via `invited_by`, not invite tokens.** The attribution column already exists; tokenized invite links are a later experiment, not loop infrastructure.
- **Guardrail flags, human kills.** Auto-disabling flags from a rollup job is more machinery than the traffic justifies; the daily guardrails report is the alarm, the operator is the actuator.

---

## 1C — Activation & Onboarding Loop

### What this is

Time-to-first-value instrumentation: the step funnel Sleeper login → league import → first matchup session → **first trade suggestion seen** (the aha moment), reported per signup-week cohort, plus the diagnostic pair *matchups-before-abandon* vs *matchups-before-value*.

### Scope

- **In:** step funnel from existing events, cohort activation report, matchup-count instrumentation.
- **Out:** onboarding changes themselves (default rankings, progressive disclosure — those are the hypotheses the report will rank).

### Architecture

```
signup (user_events) ─► league_synced ─► first trio_swipe ─► first deck served
                                                              (trade_impressions)
        all stages already emitted ─────► rollup_daily
                                              │
                  cohort = ISO week of users.signup_at
                                              ▼
            activation-report: per-cohort stage conversion +
            matchups_before_abandon vs matchups_before_value distributions
```

### Major components

| Component | Where | Role |
|---|---|---|
| Funnel stages | existing `user_events` types + `trade_impressions` | No new client emission needed — the four stages are already logged server-side |
| Cohort report | `loop_metrics.activation_report()` + endpoint | Per signup-week stage conversion |
| Matchup counters | derived from `swipe_decisions` counts per user | `matchups_before_value` = rank-decision count at first impression; `matchups_before_abandon` = total count for users with no impression and ≥14 days inactivity |

### Key flows

1. Daily rollup assigns each user a signup-week cohort and computes furthest-stage-reached; activation = reached stage 4 (first deck served) within 14 days of signup.
2. The matchups histogram pair quantifies the Elo-effort wall: how much ranking work users do before quitting vs how much the gate actually requires before first value.

### Design trade-offs

- **Zero new instrumentation.** Every stage is already observable server-side; the loop is pure derivation. This is deliberate — 1C's cost should be one report, not a client release.
- **14-day activation window** keeps cohorts comparable and reportable two weeks after close; documented as part of the metric definition so it never silently shifts.

---

## 1D — Retention Loop

### What this is

D7/D30 cohort retention as the goal metric, notification experiments keyed to league events as the lever, opt-out rate as the hard guardrail, and a **season-window comparability rule** so August numbers are never compared to March numbers.

### Scope

- **In:** D7/D30 cohort job, notification A/B slots riding the shared experiment harness (variant recorded per push), per-variant opt-out guardrail, season-window tagging.
- **Out:** new notification kinds/content (hypotheses, not infrastructure); churn prediction.

### Architecture

```
users.signup_at + user_events activity ──► rollup_daily ──► D7/D30 per cohort,
                                                            tagged season_window
push_sent (props: variant) ─┐
notif_pref_changed          ├─► per-variant opt-out + open rates
notification_prefs toggles ─┘            │
                                         ▼
              retention-report (refuses cross-window comparison rows)
              guardrails: variant opt-out delta vs control > threshold
```

### Major components

| Component | Where | Role |
|---|---|---|
| Cohort job | `loop_metrics.retention_report()` + rollup | D7/D30 return rate per signup-week cohort |
| Notification A/B | experiment harness (`unit=user`) + `variant` in `push_sent` props | One live notification experiment at a time, same harness as 1A |
| Opt-out guardrail | guardrails check on `notification_prefs` flips per variant | Kill metric: treatment opt-out exceeding control by `retention_optout_kill_delta` |
| Season windows | `season_window(date)` constant table | Tags every rollup row; reports compare only within a window |

### Key flows

1. Daily rollup: for each cohort whose D7/D30 horizon closed, compute returned-users share (any `user_events` activity in the window) and upsert tagged rows.
2. Notification experiment: dispatcher asks `variant_for(user_id)`; variant rides the push props and the `notification_events_log` kind; rollup splits opens and opt-outs by variant.

### Design trade-offs

- **Activity-based retention (any event), not session-based.** `user_events` is the cheapest reliable signal across three clients; defining a "session" cross-client is real work for marginal precision.
- **Season windows as a code constant table** (like the age curves) — boundaries are calibrated as a set, changed by code review, not by an admin endpoint.

---

## 1E — UX, Performance & Consistency Loop

### What this is

Three mechanical checks plus one human ritual: (1) cross-client invariant CI generated from a machine-readable manifest of `docs/cross-client-invariants.md` — the cheapest win, built first; (2) per-page time-to-first-action budgets in a checked-in file with a deploy-time synthetic check; (3) Render cold-start tracking (`backend/profile_session_init.py` already measures the expensive path); (4) per-release persona walkthrough checklists.

### Scope

- **In:** invariants manifest + checker + CI workflow, `config/perf-budgets.json` + synthetic post-deploy check, cold-start event logging, persona checklist docs.
- **Out:** fixing any drift or budget breach found (separate work items), full E2E browser automation.

### Architecture

```
docs/cross-client-invariants.md ──(hand-derived once)──► config/invariants.json
                                                              │
            CI (GitHub Actions, per push) ◄───────────────────┤
            check_invariants.py: assert each invariant's      │
            pattern/value in every listed client file ────────┘

deploy ──► synthetic_check.py: hit key endpoints, compare against
           config/perf-budgets.json (TTFA + API latency budgets)
server boot ──► first request records user_events: server_cold_start (boot_ms)
release ──► docs/release-checklists/persona-walkthroughs.md (3 personas × 3 clients)
```

### Major components

| Component | Where | Role |
|---|---|---|
| Invariants manifest | `config/invariants.json` | Machine-readable mirror of the invariants doc: id, expected value(s), per-file location patterns |
| Checker | `backend/scripts/check_invariants.py` | Greps each location, asserts value; nonzero exit on drift |
| CI workflow | `.github/workflows/loop-checks.yml` | Runs checker + pytest on push/PR |
| Perf budgets | `config/perf-budgets.json` | Per page/screen TTFA budgets + API latency budgets, checked in |
| Synthetic check | `backend/scripts/synthetic_check.py` | Post-deploy probe against the live host; budget comparison |
| Cold-start tracking | `server_cold_start` event + rollup | Boot-to-first-request ms, trended in loop_rollups |
| Persona walkthroughs | `docs/release-checklists/persona-walkthroughs.md` | Scripted task checklists (find a trade ≤ N taps, ranking session, send invite) per client per release |

### Key flows

1. **Invariant drift:** a PR changes a tier color in one client → checker finds mismatch against manifest → CI fails with the invariant id and the offending file. Changing an invariant legitimately = update manifest + all listed locations + the doc, in one commit.
2. **Budget breach:** post-deploy synthetic run exceeds a budget → deploy log flags it (advisory in v1, not a rollback gate).

### Design trade-offs

- **Manifest derived from the doc, not parsed from it.** Parsing prose Markdown is brittle; a one-time hand conversion to JSON, with the doc updated to point at the manifest as the machine source, is honest about which artifact CI trusts.
- **Advisory perf gate in v1.** Render deploy timing is noisy (cold starts); failing deploys on a noisy signal would train the operator to ignore the check. Trend first, gate later.

---

## Shared infrastructure

| Piece | Used by | Notes |
|---|---|---|
| `user_events` + `record_event()` | 1A–1E | New event types only; taxonomy in data-dictionary + invariants doc |
| `POST /api/events` ingestion route | 1A, 1B, 1E | Batched, whitelist-validated, client-tagged, PII-stripped |
| Experiment harness | 1A, 1B, 1D | One live experiment globally — enforced by config shape (single object) |
| `loop_rollups` + `rollup_daily` | 1A–1E | Idempotent upsert; runs inside existing `/api/cron/daily-tick` |
| Guardrails report | 1A, 1B, 1D | One endpoint aggregating all breach checks |
| `living-memory/` | all | Loop state, HANDOFF/NEXT/CHANGELOG discipline per the PGA template |

## Sequencing

Per the spec: **1E invariants CI and the 1A reward-metric definition are this-month work** (cheap, and weights must be pre-registered before telemetry is optimized against). 1A's full loop reads when traffic supports it (Aug–Sept); 1B/1C/1D instrument now, iterate during the Aug–Dec season. Full WP ordering in [`loop-prd.md`](loop-prd.md) § Sequencing.

## Outstanding / Known Gaps

- **Replay runner** (1A) — schema lands now; the runner ("would v2.3 have surfaced what v2.2's users dismissed?") is a follow-up once ≥1 engine change is queued behind it.
- **Telemetry volume** — most loop reports will be too thin to act on until the season ramps; that's expected and is itself the 1B cold-start motivation. Escalation rule: thin data → no ship, not a noisy ship.
- **Auto-kill actuators** — guardrails flag, humans act, in v1 across all loops.
- **Extension event coverage** — the extension emits the fewest events; acceptable since it consumes rankings rather than driving funnels.
