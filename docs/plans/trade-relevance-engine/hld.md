# HLD: Trade Relevance Engine

> **Purpose:** high-level design for the interaction-driven trade relevance initiative
> ([enhancement-plan.md](enhancement-plan.md), phases P0–P4) as one system evolution.
> Dual-agent authored (Architecture-Coherence lens + Failure-Modes/Scale lens);
> reconciliation log in [reconciliation-log.md](reconciliation-log.md). Ground truth
> for "what exists today" is [ftf-current-state.md](ftf-current-state.md); file:line
> anchors cite it. Precise DDL and signatures live in [lld.md](lld.md)
> (forthcoming — written after this HLD's sign-off).
>
> Status: **SIGNED OFF** — dual-agent converged, 4 rounds, 2026-08-14. Operator
> decisions still open are listed in §8 (⛔ items block the phases named there).
> Amended 2026-08-14 during PRD review (⟨PRD-AMENDED⟩ marks; reconciliation
> log §PRDs): D4's online clause (harm-check framing, pending OQ-4
> ratification) and D9's coverage denominator (rookie exclusion).

---

## Table of Contents
- [1. Context & Goals](#1-context--goals)
- [2. Architecture Overview](#2-architecture-overview)
- [3. Data Model & Flow](#3-data-model--flow)
- [4. Key Design Decisions](#4-key-design-decisions)
- [5. Cross-Cutting Concerns](#5-cross-cutting-concerns)
- [6. Observability](#6-observability)
- [7. Explicit Non-Goals](#7-explicit-non-goals)
- [8. Risks & Open Questions](#8-risks--open-questions)

---

## 1. Context & Goals

FTF already runs a two-stage recommender: exhaustive per-league-pair candidate
enumeration with hard quality gates (`trade_service.py:3444-3537`), then a
multiplier-stack ordering layer (`server.py:3344 _order_deck`) fed by the F1–F10
substrate — frozen-feature impression logging with propensities (`deck_impressions`,
`database.py:481`), outcome labels (`deck_outcomes`, `database.py:518`), Thompson
bandits, fatigue, taste vectors, exploration, and an offline SNIPS/IPS replay harness
(`backend/eval/`). The audit's finding: the loop doesn't *cycle*. The learned ranker
(F6, `backend/value_model.py`) is built but dark; the most business-real labels
(proposal accept/decline) never join back to impressions; and a large fraction of
captured signal (`user_events`, `sleeper_trades`, 28 dropped client events, waiver
history, pre-join league history) feeds nothing.

**Goal:** every deck, notification, and match surface orders trades by a learned,
inspectable estimate of *this user's* probability of acting on *this trade* — fed by
their swipes/dwell, their board, their league's real market, their pre-platform
history, and what they demonstrably value in players.

**Standing guardrails (constraints on every design choice below):** north star =
proposals-sent + matches-accepted per weekly active; session minutes are a cost;
quality gates never relax for engagement; dwell is a feature, never a reward; no
fake-infinite inventory.

**Design stance.** This is an *extension* HLD written for partial failure as the
steady state. Every phase attaches to an existing seam (the F1 spine, `_order_deck`,
the session-init daemon, daily-tick, the flag system). Exactly one new backend
package is introduced (`backend/relevance/`); everything else is new columns, new
nightly passes, and new readers of existing tables. Five silently load-bearing
assumptions in the plan are addressed structurally rather than optimistically:

1. *"The nightly tick can absorb five more passes"* — it is already the process that
   sends pushes, runs eval, refits F6, and replenishes decks, inline in the single
   web worker (§2.1 answers with a pass ledger).
2. *"Backfill is just more inserts"* — SQLite is single-writer and the request
   path shares it; WAL is already on (see §2.2) but nothing disciplines *how*
   batch jobs write (§2.2).
3. *"Sleeper history is one API call away"* — chain walks × seasons × weeks is the
   traffic class Sleeper already warned the operator about, and agreement coverage of
   unauthenticated reads is unresolved (OQ-1,
   `docs/plans/device-side-platform-auth-prd-2026-08-12.md:166`) (§5.1).
4. *"More heads make a better model"* — at hundreds of positives per head, more heads
   make a better-overfit model, and new ordering layers can silently corrupt the
   propensities the eval story depends on (§2.3, D5).
5. *"It's public data"* — P2-3 profiles people who never signed up; P4 shows users
   inferences about themselves that can be wrong and insulting (§5.2, D9).

## 2. Architecture Overview

### Components

**A. Serving path — EXTENDED, no new components.**
`POST /api/trades/generate` → `_run_trade_job` (`server.py:4653`) → generation +
gates → ordering stack → `_order_deck` (`server.py:3344`). Changes, all inside
existing functions:

- `_order_deck` gains (i) near-dup package dedup (P0-5), (ii) a per-class demotion
  multiplier read from `deck_class_stats` (P0-4), (iii) the F6 v2 score as base key
  when `deck.value_model` is on (P1-1/P1-2) — the seam F6 v1 already occupies via
  `_deck_value_scores` (`server.py:3050`).
- `trade_service._consider` (`trade_service.py:3444`) gains `decided_by` counters
  per gate per job (P0-6) — counting only; rejection behavior unchanged.
- Pool seeding and composite multipliers gain batch-feature inputs (league market
  pacing, opponent trade profiles, archetype need-fit) read from the profile tables
  below (P2/P3). Read-only keyed lookups; no per-request computation.
- P3-3 wiring, explicit so it isn't silently dropped: taste vectors
  (`taste_service.py`) and the F7 wildcard/audition pool gain **archetype
  dimensions** alongside today's position/shape/value-band attributes;
  `need_fit_score` learns to distinguish "needs a RB" from "needs a
  pass-catching RB." P3-4 (roster-construction taste) is **absorbed into
  `user_value_profiles`** as build-philosophy coefficients (stars-and-scrubs vs
  depth, age-barbell, QB-premium) rather than a separate table.
- `features_json` frozen at serve time (`server.py:3570-3629`) gains the new
  feature families (market_*, opp_profile_*, user_profile_*, archetype_match_*) so
  the training set and the serving inputs stay one artifact.

**B. Signal capture — EXTENDED.**
- `analytics_taxonomy.py` registers the 28 dropped client events (P0-1).
- The swipe/match/disposition path threads `impression_id` end-to-end so
  `deck_outcomes` gains the four D2 disposition labels (P0-3; D2).
- `sleeper_trades_service.py` stops discarding non-trade transactions (P2-2) and
  gains a chain-walking backfill mode (P2-3), both driven by cursor tables (§2.4).
- A weekly standings sync reuses the fetch code in
  `backend/outlook/league_state.py:260` but is scheduled and stored independently
  of the dead `outlook.odds` flag (P2-4).

**C. Nightly batch — NEW package `backend/relevance/`, run as a pass ledger (§2.1).**
Pure-Python derive jobs, each idempotent per `(pass, run_date)`, invoked from the
existing `/api/cron/daily-tick`. Jobs: `market_model` (P2-1), `opponent_profiles`
(P2-1/2-3), `flag_aggregation` (P0-4), `user_activity_features` (P2-5),
`archetype_refresh` (P3-1), `value_decomposition` (P3-2), plus the existing F8
eval → promotion report → flag-gated F6 refit (`server.py:16600`, `:16618`).

**D. Model layer — EXTENDED `backend/value_model.py`.**
F6 v1's structure (pure-Python Platt-calibrated logistic heads, append-only model
store `data/value_model/models.jsonl`, composite fallback on any failure) is kept
and widened: v2 adds heads for the logged action ladder and the explicit value
blend `score = Σ V_a · P(a)` with the V-vector versioned in `model_config`
(D5, D10). Logistic first; GBDT only as a measured escalation.

**E. Eligibility split — NEW config block, existing enforcement point.**
Push/notification assembly gains a `push_eligibility` check (P1-3, D6). Deck
serving is untouched — the split is enforced where pushes are assembled, mirroring
X's stricter out-of-network bar.

**F. Presentation — EXTENDED clients + card payload (P4).**
Server: personal-hook templates sourced from `user_value_profiles` ×
`player_archetypes` × `league_market_profiles`; a new
`GET /api/trades/why/<impression_id>` explains ranking from the frozen
`features_json` + score components — with an ownership check (the impression must
belong to the caller; uuid unguessability is not the authz story for a route
returning counterparty context). Clients render hooks, the "why" sheet, and the
(stretch) trading-profile surface. All behind flags, Chalkline rules, Maestro
deltas, template-assembled copy only (D9).

### 2.1 The pass ledger (P0 prerequisite the plan skipped)

Today `/api/cron/daily-tick` (`server.py:16494`) runs push scans, replenishment, F8
eval, conditional F6 refit, players-refresh staleness guard, and a class-load
monitor — inline in the single gunicorn worker. When the tick dies mid-way,
everything after the corpse silently doesn't run, and nothing durable records which
passes completed (eval logs a warning and continues, `server.py:16614`). The
retention endpoint was deliberately kept out of daily-tick for exactly this reason
(`server.py:16680`). This initiative adds five more passes, so the principle becomes
structure:

- **Pass registry.** Each nightly job is a named pass (`pushes`, `replenish`,
  `eval`, `refit`, `flag_agg`, `standings`, `market_model`, `archetypes`,
  `profiles`, …). The tick iterates the registry; each pass runs under its own
  try/except and its own **time budget**. Kill switches live in `model_config` as
  numeric 0/1 keys (`cron.pass_disabled.<name>`, absent ⇒ 0 ⇒ pass runs):
  inverted polarity fails safe (a typo or missing key cannot silently stop the
  `pushes` pass), and `model_config` is a live DB write, so killing a pass is
  immediate — `config/features.json` flags are baked into deploys and gated on a
  pre-declared registry (`feature_flags.py` drops unknown keys), which makes them
  the wrong store for an operational kill switch. New *feature* surfaces still
  use ordinary feature flags; the pass kills are operational valves, same class
  as D7's ingest budget. **Operational valves are read directly from
  `model_config` and are exempt from D10's resolver precedence** — an experiment
  variant overlay or per-user setting can never resurrect a killed pass or raise
  the ingest budget.
- **The registry refactor is behavior-preserving.** Moving the existing tick
  bodies (pushes, replenish, eval, refit, players-refresh guard, class-load
  monitor) into the registry must produce identical behavior with all kill keys
  absent — this initiative must not be able to destabilize non-relevance passes.
  Scope note: the ledger covers **daily-tick only**; hourly-tick and the 15-min
  realtime-tick (quiet-hours drain, digests, `match_expiring`) stay outside it —
  folding them in would break the 8am bundling contract, and the `pushes` pass
  name refers only to daily-tick's own scan.
- **Push-pass rerun safety is a stated invariant, not an assumption.** Re-run
  safety for pushes comes only from frequency caps and dedup keys logged at send
  (`log_notification_send`, `server.py:15800`); the quiet-hours queue path logs
  nothing at queue time. Rule, enforced at the registry: **every push kind
  dispatched from a ledger pass MUST carry a frequency cap or dedup key**, and
  passes are classified `resumable-next-day` (derivations, ingestion) vs
  `must-complete-today` (date-gated work like the Aug-25 `season_start` fan-out)
  — the latter retry same-day on error rather than deferring to a tick that will
  never satisfy their date gate. Same-day retries are bounded (≤2, per-pass time
  budget still binding); a final failure records `status='error'` in the ledger
  and raises the operator alert for date-gated passes.
- **Pass ledger table** `cron_pass_runs (pass, run_date, status ∈
  ok|error|skipped|timeout, started_at, duration_ms, items_processed, error_text)`
  — one row per pass per day, idempotent on `(pass, run_date)`. This is the
  observability spine (§6) and the resume mechanism: a re-POST of the tick skips
  passes already `ok` today (generalizing eval's per-day idempotency,
  `server.py:16602`).
- **Ordering + budget.** User-facing time-sensitive passes first (`pushes`,
  `replenish`), analysis second (`eval`, `refit`, `flag_agg`), ingestion/derivation
  last. A wall-clock deadline is checked **between** passes; passes past it are
  recorded `skipped` and picked up next tick — acceptable because every new pass
  is `resumable-next-day` by design (must-complete-today passes are exempt from
  the deadline skip, per the classification above).
- **Heavy passes never run inline.** Anything that talks to Sleeper or writes more
  than O(users) rows (backfill, standings, archetype refresh) runs as a chunked
  daemon-thread worker draining a work-queue/cursor table (§2.4, the
  players-refresh precedent); the tick's pass merely advances that queue's budget
  for the day. The tick itself stays O(minutes).

### 2.2 One batch-writer discipline for SQLite

New write load: P0-4 aggregation, P2-2 capture widening, P2-3 backfill (worst case
~12 leagues × 3 seasons × 18 weeks of transaction pages per newly linked user),
P3-1 archetype refresh (~2k players nightly), P3-2 profiles. SQLite is
single-writer and the request path shares it. Design answers:

- **WAL is already on — keep it asserted, don't re-do it.** The on-connect
  listener sets `journal_mode=WAL`, `busy_timeout=5000`, `synchronous=NORMAL`,
  and `wal_autocheckpoint` (`database.py:83-96`), and boot status surfaces WAL
  state (`analytics_boot_status`, `database.py:131`) — the analytics NFR-2 fix
  landed after the reconciliation doc that reported it off. The residual risk is
  therefore *writer-contention discipline*, not journal mode.
- **All new batch writes go through one helper** (`batch_write`): short
  transactions (≤200 rows), commit per chunk, pacing sleep between chunks,
  `busy_timeout` respected, and **no transaction ever held across a network call**
  — fetch a week, close the socket, then write. `batch_write` runs on the
  **product engine** (5000ms busy timeout); it must not casually adopt the ingest
  engine, which deliberately runs `busy_timeout=150` + `BEGIN IMMEDIATE` for
  fail-fast analytics writes.
- **Postgres tripwire, pre-committed:** if batch-pass durations grow >2× over a
  rolling 30 days, or the request path logs `database is locked` more than 5
  times/day (counted in the ledger), the Postgres cutover (already swappable via
  `DATABASE_URL`) happens **before P2-3 fleet-wide rollout** — the phase that
  multiplies write volume must not land on a contended SQLite.

### 2.3 Serving contract: propensity-preserving by construction

P0-4/P0-5/P1-1/P1-2/P1-3 all modify ordering. The existing stack logs the Thompson
multiplier as `propensity` into `deck_impressions` — the prerequisite for all
off-policy eval. **Contract: any change to serving order must either (a) be
deterministic given the logged `features_json` (dedup, eligibility — replayable),
or (b) contribute its factor to the logged propensity (any new stochastic layer).
A layer that is neither does not ship.** Corollary for anything that reads a
nightly-mutating table (P0-4 class demotion, profile multipliers): **the applied
value is frozen into the serve-time capture** (`features_json` alongside
propensity/final_key) — replay must never reconstruct table state at serve time,
which D8 forbids as leakage. Enforced by review checklist plus an automated
nightly propensity-drift check (§5.3).

### 2.4 Ingestion: work queues, not fan-outs

P2-2/P2-3/P2-4 sourcing runs off two small tables: `ingest_cursors` (per league ×
season × kind: last week fetched, status, attempts, next_eligible_at) and a daily
Sleeper **call budget** shared by *all* background ingestion (D7). The existing
per-session sweep (`sleeper_trades_service.py:61`, called from `server.py:15283`)
is refactored to consume the same cursor table, so "sweep on session_init" and
"backfill nightly" are one resumable machine, not two competing ones.

### Described diagram

```
                ┌──────────────── nightly /api/cron/daily-tick — PASS LEDGER (§2.1) ────────────────┐
                │ pushes · replenish │ eval · refit · flag_agg │ standings · market_model ·          │
                │ (existing)         │ (existing + P0-4)       │ archetypes · profiles (new, queued) │
                └───────┬────────────────────────────────────────────────────────────┬──────────────┘
  Sleeper API           │ writes profile tables (batch_write, §2.2)                  │ reads
  ├ transactions ─► sleeper_trades(+kind,+source) ──┐                                │
  ├ prev-league chain ─► backfill via ingest_cursors┤                    deck_impressions ⋈ deck_outcomes
  ├ standings ─► league_standings ──────────────────┤                                ▲
  nflverse files ─► player_archetypes ──────────────┘                                │ labels incl. P0-3
                                                                                     │ accepted/declined
  deck request ─► _run_trade_job ─► generate + gates(+decided_by) ─► ordering stack  │ (≤14d maturation)
                       ▲                          │                                  │
     profile tables ───┘ fail-soft keyed reads    ├─ F6 v2 · class demotion · dedup ·│
                                                  │  fatigue · taste · bandit (§2.3) │
                                                  ▼                                  │
                                           served deck ── freeze features_json ──────┘
                                                  │
  push decision ─► push_eligibility bar (D6) ─► _send_typed_push ─► inbox/push
```

Serving is request-path and cheap (keyed lookups + a linear model over frozen
features); everything expensive is nightly batch; the impression spine is the
single contract between them.

## 3. Data Model & Flow

### 3.1 Entities (named level; DDL in the LLD)

New tables (all additive, all flag-gated at their write sites, each with a stated
retention):

| Table | Phase | Keyed by | Contents / notes | Retention |
|---|---|---|---|---|
| `cron_pass_runs` | P0 | (pass, run_date) | status, duration, items, error | 90 days (existing retention endpoint) |
| `deck_class_stats` | P0-4 | (archetype, shape_bucket, value_band) | exposures, flags, flag-rate, demotion multiplier, computed_at | latest read; 30d history for operator report |
| `ingest_cursors` | P2 | (league_id, season, kind) | last_week, status ∈ pending\|active\|done\|stuck, attempts, next_eligible_at | permanent (tiny) |
| `league_lineage` | P2-3 | (league_id, ancestor_league_id) | season, depth — the walked `previous_league_id` chain; backfill provenance + resume | permanent (tiny) |
| `league_market_profiles` | P2-1 | (league_id) | trades/month, shape histogram, positional flow, per-position price level vs consensus, computed_at | derived; recomputed |
| `manager_trade_profiles` | P2-1/2-3 | (platform, platform_user_id, league_id) | trade pace, positions bought/sold, consolidation lean, FAAB aggression, waiver churn, age-lean, seasons observed, confidence_n. **League-scoped; never cross-league joined; server-internal** (§5.2) | derived; dropped on league unlink |
| `league_standings` | P2-4 | (league_id, week, roster_id) | wins/losses, points-for, pf-by-position where derivable | current season + 1 |
| `user_activity_profiles` | P2-5 | (user_id) | recency-weighted `user_events` aggregates (calc sessions/wk, board-edit recency, notif tap rate) | derived; recomputed |
| `player_archetypes` | P3-1 | (sleeper_player_id, season) | archetype vector + source stat snapshot + `archetype_confidence` | latest season live; prior seasons kept for training |
| `user_value_profiles` | P3-2 | (user_id, scoring_format) | interpretable coefficients (position/age/archetype premia), n_obs, fit diagnostics, confidence; user-visible/editable/deletable (§5.2) | recomputed; user-deletable |

Extended tables/columns:

- **`sleeper_trades`** + `kind ∈ trade|waiver|free_agent`, `source ∈
  live|backfill` (P2-2/P2-3). One table, one sweep, one idempotency key
  (`transaction_id`). Raw payload retention: 3 seasons rolling, matching the
  backfill depth cap (raws are the recovery substrate for every derived table —
  see reconciliation log for the 18-month-vs-3-season resolution).
- **`trade_matches`** + `impression_id_a` (↔ `user_a_id`, the triggering swiper
  — in hand at creation, always exact) / `impression_id_b` (↔ `user_b_id`, the
  earlier-liking counterparty — recovered at creation, inherits match fuzziness;
  nullable on recovery failure). Direct-send proposals create no match row (D2).
- **`deck_outcomes`** — `action` enum widened with four disposition labels:
  first-person `accepted` / `declined` and counterpart
  `accepted_by_partner` / `declined_by_partner`; new `join_quality ∈ exact|fuzzy`
  on those rows (D2).
- **`deck_impressions`** + **`surface TEXT DEFAULT 'deck'`** — a real column, not
  a JSON key (training-split queries need it indexed). Push-logged rows carry
  `surface='push'`, deterministic `propensity=1.0`, and a synthetic
  `deck_job_id`/`card_index`. Two rules ship **in the same change that
  introduces push rows (P1-3), not later**: (a) a closed action set — deck
  actions (`viewed`, `like`, `pass`) never ride a push impression; push rows may
  receive only push-native outcomes (tap-through); disposition labels attach to
  the match-side deck impressions per D2, never to push rows; (b)
  **every impressions⋈outcomes reader filters `surface='deck'` unless it
  explicitly opts into push rows** — in scope for P1-3: `load_decks`
  (`backend/eval/data.py:108`), the refit dataset builder, F9's prior-deck /
  `MAX(served_at)` check (`database.py:4700`), Thompson arm events
  (`database.py:~4814`), fatigue events (`database.py:~4930`), and D11's
  exposure denominator. Otherwise one-card pseudo-decks poison replay — and
  serving-side personalization — the day the feature ships. `features_json`
  gains the new feature families, versioned by a `feature_set` key inside the
  JSON.
- **`model_config`** — versioned `vblend` rows (D10), `push_eligibility_*` knobs,
  dedup overlap threshold, demotion floor, ingest budget.

### 3.2 The three loops and their partial-failure behavior

```
LOOP 1 (request path, ms):  boards/prefs + fail-soft profile reads → enumerate →
  gates(+decided_by) → composite → F6 v2 | dedup | class demotion | fatigue |
  taste | bandit → _order_deck → serve → deck_impressions (features + propensity)
LOOP 2 (user actions, sec–days): swipe/flag/propose → deck_outcomes →
  accept/decline joined by impression_id, matured ≤14d
LOOP 3 (nightly pass ledger): eval → refit → flag_agg → ingestion queues →
  market/archetype/profile derivations → tomorrow's LOOP 1 inputs
```

- **LOOP 1 reads are fail-soft:** every new input is read absent-tolerant —
  missing row ⇒ neutral multiplier 1.0 / empty feature, never an error. The deck
  must render correctly on a database where every P2/P3 table is empty (day one,
  and any day after a corrupted derivation is truncated).
- **LOOP 2 is eventually-consistent by design:** dispositions arrive days after
  serving; the join writes at disposition time keyed by the threaded
  `impression_id`; broken threads (web, older app versions) fall back to
  `trade_hash` + served-within-7d, marked `join_quality='fuzzy'`, excluded from
  training by default. **No training example is consumed until its impression is
  ≥14 days old** (label maturation), converting eventual consistency into fixed lag.
- **LOOP 3 passes are idempotent and derive-only:** every derived table can be
  truncated and rebuilt from raws (`sleeper_trades.raw`, impressions/outcomes,
  nflverse files). Corruption recovery is DELETE + re-run, never surgery.

### 3.3 Flow: a league-link backfill (P2-3)

1. At league link (and for already-linked leagues only after OQ-1 clears — §5.1),
   a queued worker walks `previous_league_id` up to **3 seasons**, writing
   `league_lineage` rows (resumable checkpoints).
2. Per ancestor league: fetch weeks 1–18 transactions (existing fetcher), store
   trades + waiver/FA rows into `sleeper_trades` with `source='backfill'`; fetch
   ancestor `/rosters` once to map `roster_id → platform owner_id`.
3. Work unit = (league, season, week); cursor updated per unit; 429/5xx →
   exponential backoff, `attempts++`; after 5 failures the cursor parks
   `status='stuck'` for the operator report.
4. Nightly `opponent_profiles` picks new rows up automatically; a new user's
   day-zero prior is their `manager_trade_profiles` row existing before their
   first swipe. Under the D7 budget, backfill may take days — day-zero degrades
   to day-two personalization; nothing downstream assumes completeness.

### 3.4 Flow: a push decision (P1-3 + P4-3)

1. A candidate trade notification arises (existing triggers).
2. `push_eligibility` (D6): score percentile ≥ bar (default P75) within the user's
   trailing decks; zero fatigue debt on centerpiece/archetype; `relaxed=False`;
   `basis != 'consensus'`; counterparty active ≤ 14d; existing per-user frequency
   caps unchanged. Applies to *unsolicited suggestion* pushes; match/response
   notifications (user-initiated loops) bypass it.
3. P4-3: the copy must bind a personal hook that clears its display threshold
   (D9); no hook → fall back to inbox-only or nothing, per kind.
4. Pass → existing `_send_typed_push` prefs/dedup/quiet-hours pipeline unchanged;
   an impression row logs with `surface='push'`.

## 4. Key Design Decisions (mini-ADRs)

**D1 — Pass ledger before any new nightly work.**
Choice: §2.1's registry + `cron_pass_runs` + budgets + per-pass kill flags,
refactoring the existing tick passes into it. Rejected: keep appending try/except
blocks (silent partial execution is the observed failure mode — nothing durable
records that eval hasn't run since a pushes-scan exception).

**D2 — P0-3 join: carry `impression_id` forward per side; label per event and per perspective.**
A match is not created by "propose" — it is created by the mirror path:
`create_trade_match` (`database.py:6684`, sole call site `server.py:10286`)
fires when a swiper's like mirrors a counterparty's *earlier* like. Its existing
semantics, which this design binds to exactly: **`user_a` = the swiper whose
like just triggered the match** (their `impression_id` is in the swipe body —
exact, in hand); **`user_b` = the counterparty who liked earlier** (their
impression must be recovered from their original like). With `trade.fuzzy_match`
on, the two sides' packages need not even share a `trade_hash`. The design:

- `trade_matches` gains `impression_id_a` (↔ `user_a_id`: captured at creation
  from the triggering swipe, always `join_quality='exact'`) and
  `impression_id_b` (↔ `user_b_id`: recovered at creation from B's original
  like — recovery inherits the match's own fuzziness, so a fuzzy-created match
  yields a side-B join born `join_quality='fuzzy'`; **nullable** for recovery
  failure, e.g. likes predating the F1 spine). LLD note: `check_for_match`
  returns only a bool and `trade_decisions` carries no `impression_id` — the
  cheapest *exact* recovery is threading `impression_id` into
  `save_trade_decision` at swipe time (the swipe body already carries it), so
  match creation reads it off the matched like row directly.
- **Direct-send proposals (Sleeper/MFL/ESPN) create no `trade_matches` row** —
  the mirror path is the only creator today. Their in-app label remains the
  impression-keyed `propose` outcome; platform-side accept/decline is out of
  P0-3's scope (a future pending-trades-inbox read may add it).
- Disposition writes outcomes **per perspective**, from a fixed event→label map:
  the disposing actor's own impression gets first-person `accepted`/`declined`
  (a first-person decline is the strongest negative in the system — it already
  triggers 30-day suppression, `server.py:13145` — and must not be lost); the
  counterpart impression gets `accepted_by_partner`/`declined_by_partner`. Four
  new enum values, not two. The two labels land on two *different* impressions,
  so there is no training double-count.
- Fuzzy `trade_hash`+served-recency join only where a thread is broken (web,
  older app versions), marked `join_quality='fuzzy'`, default-excluded from
  training.

Rejected: propose-time-only threading (misses the match-creation join entirely);
probabilistic join as the permanent mechanism (same hash legitimately re-serves;
ambiguity is label poison at an N where a few hundred accept labels carry the
whole accept head); joining through `user_events` (analytics lineage is not the
training spine).

**D3 — Ranker runs in-process, batch-trained, request-time-scored.**
Choice: F6 v2 stays a pure-Python model loaded from `models.jsonl`, scored inside
`_deck_value_scores`; training only in the nightly pass. Rationale: single Render
service is a hard constraint; linear scoring over ≤40 cards is microseconds; F6 v1
proved the seam and the fallback contract (any failure serves composite exactly).
Rejected: separate serving process (violates no-new-infra; network hop for
microsecond work); request-time feature computation (breaks snapshot semantics);
sklearn/numpy dependency (F6 v1 deliberately avoided it; keep that).

**D4 — F6 promotion criterion: pre-registered, statistical, two-sided, on a pinned artifact.**
Prerequisite: **split `train.value_model` (refit pass) from `deck.value_model`
(serving)** — today the refit runs inside `if _deck_value_model_enabled():`
(`server.py:16624`), so keeping serving dark also freezes training, and the
counting window would grade a stale artifact trained on pre-P0-3 labels. With the
split, refit runs dark nightly; then a **candidate artifact is pinned** (its
`models.jsonl` entry id recorded in the pass ledger) and the counting window
evaluates that one artifact — never a different model every night, which would
make "15 of 21" an aggregate over 21 artifacts and mean nothing.

Promote `deck.value_model` when, over the trailing **21 nightly replays of the
pinned artifact**: (a) SNIPS lift over composite is positive with
cluster-bootstrap 90% CI excluding 0 on ≥ 15 of 21 counted nights; (b) ESS ≥ gate
on every counted night (ESS-failing nights count for neither side); (c) no
replayed guardrail metric (flag rate, fast-pass rate) degrades beyond its CI; and
(d) any disposition-labeled metric restricts to impressions older than the
maturation horizon — matches never hard-expire (the 48h `match_expiring` cron
only nudges), so the newest tail of every window is censored toward "no accept"
and must not be counted. **Kill criterion is symmetric:** if after 21 counted
nights the CI still straddles 0, the pinned artifact is declared not-better, the
flag stays dark, and P1-2 (more heads, more labels via P0-3) becomes the path.
The bar is never lowered after counting starts. Online, promotion =
`experiments.py` A/B at 50% over a pre-set 4-week horizon. ⟨PRD-AMENDED,
pending OQ-4 ratification⟩ At current WAU the north star is not detectable in
4 weeks, so the online window is a pre-registered **harm check** (guardrails +
a north-star point-estimate floor decide; the offline verdict is the
promotion authority) — the P1 PRD §4 Metric 2 carries the decision rule.
Numbers are operator-ratifiable *before* counting begins (open question 4).

**D5 — Multi-head widening gated per head by positive-label count.**
Each head activates only at ≥ 300 positive labels trailing 90 days; below that it
falls back to its parent in a fixed hierarchy (`accepted → propose → like`) with
the child's V-weight zeroed. Stated honestly: **at current volume v2 launches with
~4 live heads (viewed→like, calc_open, propose, flag), not 9** — accept/decline
heads wait for P0-3 volume. The V-vector carries all slots from day one (no schema
churn). Negatives get X-style outsized magnitudes (flag ≈ −50× like), but the
blend clamps total negative contribution to ≥ −80% of the positive sum so one
miscalibrated sparse head cannot zero a deck. Dwell appears only in features,
never in the V-vector (guardrail).

**D6 — Push eligibility is a separate rule block at send-assembly.**
§3.4's rules, enforced where payloads are assembled, **not** inside `_order_deck`
— pull decks must not be silently thinned by push rules. "Counterparty active"
reads `users.last_active_at` (existing column) — no new activity signal. Push
impressions log with the `surface='push'` column semantics defined in §3.1 so
push and deck distributions are separable in training and excluded from deck
replay. Rejected: applying the deck pipeline's ordering to pushes implicitly
(conflates surfaces; a push-clicked trade is a much stronger label than a deck
view).

**D7 — All background Sleeper ingestion shares one global daily call budget.**
One token bucket (default **2,000 calls/day**, config-keyed, operator-adjustable —
open question 6) covers P2-2 sweeps + P2-3 backfill + P2-4 standings; cursor-based
resume; backoff and park on repeated failure; **kill switch: budget=0 stops all
background ingestion in one config write** and nothing downstream breaks
(fail-soft reads). Deliberately far below the traffic class that drew Sleeper's
warning. Rejected: per-feature budgets (nobody arbitrates their sum); unbudgeted
link-time backfill (burst exactly when a new user is watching).

**D8 — Feature store = frozen `features_json` (online) + purpose-named profile tables (batch).**
No generic feature store. Request-path features are whatever `features_json`
freezes at serve; batch features live in the named tables and are *copied into the
snapshot at serve time*. Training reads only `features_json` ⋈ `deck_outcomes` —
train/serve skew is structurally impossible, and every new feature has a built-in
urn-in fuse (it must be frozen for the maturation horizon before any model sees
it). Rejected: generic KV feature table (loses typed reads, invites drift);
training-time feature recomputation (current tables know the future — leakage).

**D9 — Archetypes and value decomposition are batch-derived, confidence-gated, template-rendered.**
`archetype_refresh` downloads nflverse season files (temp-file + `os.replace`,
players-cache pattern), derives vectors in-process, upserts by Sleeper id via the
existing `db_playerids` crosswalk. Unmapped players get null archetypes = neutral
features; mapping coverage < 90% of rostered players ⟨PRD-AMENDED: denominator
excludes `years_exp=0` players and picks — rookies get age-only rows; else the
gate fails every August on rookie-heavy rosters⟩ ⇒ pass reports `error` and
consumers keep yesterday's table. `value_decomposition` computes only for users
with ≥ 25 ranked players and ≥ 10 non-trivial consensus deltas; below that,
`confidence='insufficient'` and **P4 renders nothing** (never a guess).
Coefficients clamp to a plausible band before serving. All P4 copy is
template-assembled from coefficients above a display threshold — no generative
copy in the serving path. Rejected: LLM archetype classification (cost, drift,
unnecessary); request-time nflverse reads; static archetype config (goes stale).

**D10 — One precedence order and versioned value-blend config.**
Precedence, enforced by a single resolver helper (the only legal read path):
**per-user setting > experiment variant overlay > `model_config` active row >
code default.** The V-vector is versioned; note `model_config.value` is
Float-typed (`database.py:1848`), so a structured blend does not fit a scalar row
— the LLD chooses between per-head keyed rows under a version prefix
(`vblend.<id>.<head>`) or a tiny dedicated table; it must not assume a JSON
column. The active `vblend_id` is stamped into every impression's
`features_json`; rollback = flip the active pointer (one UPDATE, no deploy) and
replay stays valid because each impression knows which blend served it. The admin write endpoint validates
head names against the registry, bounds every weight, and refuses a blend whose
negative mass exceeds the D5 clamp. Rejected: weights baked into the model
artifact (couples editorial weights to retrain cadence); weights in
`config/features.json` (boolean flag semantics; `model_config` is the numeric home).

**D11 — Flag aggregation is a bounded demotion, never a gate.**
Nightly `flag_aggregation` computes exposure-normalized flag rates per class.
Join key, stated because `bad_trade_flags` carries neither `impression_id` nor
`trade_hash` (`database.py:917`): flags are attributed through the parallel
`not_interested` `deck_outcomes` row the flag path already writes (impression-
keyed); exposures are `viewed` impressions. Demotion multiplier clamped to
[0.5, 1.0]; classes below n ≥ 200 viewed impressions (trailing 30d) get 1.0. The
applied multiplier is frozen into the serve-time capture per §2.3. The operator
report lists demoted classes with their n so a human decides whether any deserves
a real hand-authored gate in `_consider` — gates stay editorial, per guardrail.
Rejected: hard-dropping high-flag classes (a gate change on noise-prone tiny
exposures — 3 flags on 40 exposures must not gate an archetype league-wide).

**D12 — One new package (`backend/relevance/`), not scattered modules.**
All derive jobs in one package with a shared idempotency/fail-soft/batch-write
harness and a single registry consumed by the tick. Rationale: server.py is at its
comprehension limit; jobs share dependencies (crosswalk, `sleeper_trades` readers);
one home keeps the batch layer testable without Flask. Rejected: growing server.py;
one module per phase (duplicated harness); separate cron endpoints per job (Render
cron slots are managed; ordering between passes matters).

## 5. Cross-Cutting Concerns

### 5.1 Platform risk (Sleeper) — the biggest external dependency

Facts on record: Sleeper warned the operator about request volume; the §11.3
agreement covers credentialed access
(`docs/plans/sleeper-pending-trades-feasibility-2026-08-12.md:88`); whether it
covers automated *public* reads is **OQ-1, unresolved**
(`device-side-platform-auth-prd-2026-08-12.md:166`); and `sleeper_trades_service`
is one of the paths that currently impersonates desktop Chrome. Posture:

- **P2-3 fleet-wide retroactive backfill is gated on OQ-1's answer** — an
  operator/legal gate recorded in the scope block. Until answered: backfill runs
  for newly-linked leagues only, under the D7 budget.
- The UA split-identity question is surfaced in this initiative's scope block:
  expanding sweep volume on a Chrome-spoofed path worsens the posture the
  device-auth programme exists to improve. Resolved before P2 ships, not here.
- Kill switch: D7's budget=0.

### 5.2 Privacy & trust boundaries

- **Non-users are profiled (P2-1/P2-3).** Design limits, as architecture not
  policy: `manager_trade_profiles` rows are league-scoped, never joined across
  leagues, never keyed to a global person; they influence ordering and features
  only — no UI surface names a non-user's inferred tendencies ("this league pays
  up for RBs" may render; "Alex overpays for RBs" never does); rows are deleted on
  league unlink; raw payloads age out with the 3-season rolling window; no display
  names/avatars/message content in the new tables (platform ids only — an
  identifier class FTF already stores). Disclosure: the privacy policy gains a
  plain-language line that FTF reads public league transaction history to model
  league markets — a docs-gate row, not optional (open question 5).
- **Users can see, correct, and delete their own inference.** `user_value_profiles`
  is user-visible (P4-4), editable (corrections stored `declared=True` and outrank
  inferred values per D10), and deletable. Copy rules: hooks describe *the market
  or the fit*, never the user's competence ("Adds the rushing-QB profile you rate
  above market" passes; "you undervalue your RBs" is banned). Push text never
  carries inferred coefficients or counterparty profiling ("X is desperate to
  sell" never sends).
- Account deletion cascades platform-identity profile rows for that identity;
  league unlink stops capture and drops that league's profiles.
- `CRON_SECRET` continues to guard all tick/admin surfaces; no new auth surface.
  The analytics PII scrub applies unchanged to the P0-1 registered events.

### 5.3 ML integrity

- **Leakage:** training reads only impressions ≥ 14 days old; features are
  exclusively the serve-time-frozen `features_json` (D8) — no training-time
  recomputation, ever.
- **Propensity:** the §2.3 contract, plus a nightly sampled check in the eval
  pass: recompute the ordering key from `features_json` for sampled impressions
  and assert the logged propensity explains the served order within tolerance;
  drift ⇒ ledger `error` and that window's eval results are marked untrusted.
- **Feedback-loop control:** the F7 exploration slot and Thompson stochasticity
  are **policy invariants** — tunable, never disabled while any learned component
  trains on serving logs (they are the randomization that keeps IPS/SNIPS
  estimable). Written into their config-reference entries.
- **Cold start:** new users serve from the hand-tuned composite + the P2-3 prior
  (when arrived) with F9 shaping unchanged; learned scores apply only past a
  per-user minimum outcome count (default 20). A model trained on power users
  must not confidently order a stranger's first deck.

### 5.4 Reliability, deploy, rollback

- Every batch pass: fail-soft, idempotent per day, skip-if-fresh for external
  fetches; nflverse unreachable ⇒ stale-with-visible-`computed_at`; profile
  missing ⇒ today's behavior; F6 scoring error ⇒ composite fallback,
  byte-identical (F6 v1 contract). Dark-flag posture: with every new flag off,
  responses are byte-identical.
- New flags (final names in LLD): `deck.value_model` (existing) stays the
  **single serving gate** — v1 vs v2 is the artifact family in `models.jsonl`
  selected by the pinned/promoted artifact, never a second serving flag that can
  disagree with the first; `train.value_model` (refit pass, split per D4),
  `deck.class_demotion`, `deck.dedup`, `push.eligibility_bar`,
  `market.transactions_all`, `market.history_backfill`, `market.standings_sync`,
  `relevance.profiles`, `data.archetypes`, `ui.personal_hooks`, `ui.why_this`,
  `ui.trading_profile`. Operational valves (pass kills
  `cron.pass_disabled.<name>`, ingest budget) live in `model_config`, not
  `features.json`, per §2.1. Capture/derive flags may run ahead of consume flags
  (accumulate dark — the `sleeper_trades` precedent).
- Rollback, uniform: flag off + derived tables truncatable + config rows
  deactivatable; schema is additive so schema rollback is never required; model
  rollback = previous `models.jsonl` entry; V-blend rollback = one UPDATE (D10).
- All four feature gates apply per shipped item; P2/P3 schema items hit the
  bright line and are never express.

## 6. Observability

One admin page (`/api/admin/analytics/relevance`, the `analytics_queries.py`
report pattern) reading only ledger + counter tables:

- **Pass ledger strip:** last 14 days × passes, status + duration trend.
- **Funnel counters (P0-6):** gate kills per gate per job from `decided_by` —
  "why is this deck thin" without reading code.
- **Loop health:** impressions/day, outcomes/day by action,
  propose→disposition join rate (P0-3's success metric), fuzzy-join fraction,
  label-maturation backlog.
- **Model health:** last refit, per-head positive counts vs D5 thresholds, last
  replay ESS, promotion-criterion progress (n of 21, current CI).
- **Ingestion:** budget consumed/remaining, cursors by status (incl. `stuck`),
  429/5xx rate, archetype mapping coverage.
- **Guardrails:** flag rate, suppression-undo rate, decline rate, first-session
  like rate.
- **Per-phase honesty checks** (from the plan's Measurement section, carried
  here as named metrics with rollback semantics): P2-1 market pacing must
  *reduce* served-but-never-viewed cards; P4-1 hooks must raise like-rate
  without raising flag-rate (tracked as flag-rate-on-hooked-cards). A phase that
  moves minutes but not proposals/accepts violates the north star and rolls back.

Logging: per-pass structured one-line summaries (existing daily-tick counter
pattern); never per-item logging in loops; errors carry pass name + cursor
coordinates so a `stuck` row is diagnosable from the ledger alone.

## 7. Explicit Non-Goals

1. No real-time or online retraining — nightly batch, per scale honesty.
2. No transformers, sequence models, or embeddings-ANN retrieval — logistic/GBDT
   ceiling; revisit at ~100× event volume.
3. No cross-league social graph or collaborative retrieval — the candidate
   universe stays one league; §5.2's no-cross-league-join rule is the same
   boundary worn as a privacy guarantee.
4. No engagement-optimized push volume — no learned component ever chooses
   whether to send *more* pushes; send volume stays an editorial cap.
5. No dwell-as-reward, ever — feature and tie-breaker only.
6. No MFL/ESPN history scraping — no read surface exists and the ToS posture is
   worse than Sleeper's; revisit only after P2 proves value, with a terms read.
7. No new infra — work-queue tables + daemon threads + the existing cron tick are
   the whole execution substrate.
8. No generative copy in the serving path — P4 hooks are template-assembled.
9. No learned quality gates — gates in `_consider` remain hand-authored; learned
   components only reorder what the gates admit.
10. No changes to gate semantics — this initiative only makes gate kills
    observable (P0-6).

## 8. Risks & Open Questions

| # | Risk | Sev | Design answer | Residual |
|---|---|---|---|---|
| R1 | Daily tick wedges; downstream passes silently skip | High | §2.1 pass ledger, budgets, per-pass flags, idempotent resume | Verify Render cron retry semantics on a mid-tick 502 once; runbook it |
| R2 | SQLite lock contention: batch writers vs request path | High | §2.2 batch-write discipline (WAL already on, asserted at boot), tripwire → Postgres before P2-3 rollout | Cutover unrehearsed; dry-run against a staging `DATABASE_URL` before the tripwire can fire |
| R3 | Sleeper throttles/blocks over ingestion volume; OQ-1 coverage doubt | High | D7 budget + backoff/park + kill switch; §5.1 gates fleet backfill on OQ-1 | OQ-1 is an operator/legal question; UA identity decision operator-owned |
| R4 | Propensity corruption → replay silently wrong → false promotion | High | §2.3 contract + nightly drift check + D4 ESS-gated counting | Drift check is sampled; review checklist covers rarely-hit layers |
| R5 | Overfit heads at tiny N; noisy negative heads zeroing decks | Med-High | D5 label floors + parent fallback + negative-mass clamp | Accept-head timeline rides P0-3 join rate — watch the §6 counter |
| R6 | Label leakage via recomputed features or immature labels | Med | D8 frozen-features-only + 14d maturation | Horizon is a guess; tune from observed disposition latency |
| R7 | Feedback-loop collapse (model trains on its own serving) | Med | §5.3 exploration invariants (F7 + Thompson stay on) | True holdout unaffordable at this N; revisit at 10× users |
| R8 | Non-user profiling becomes a trust/press problem | Med | §5.2 league-scoping, no-UI-naming, unlink deletion, disclosure | Operator signs off disclosure wording + retention numbers |
| R9 | P4 hooks misfire ("insulting inference") | Med | D9 confidence gates + banned-copy rules + templates | Copy spec gets a real review in the P4 scope block; measure flag-rate-on-hooked-cards |
| R10 | Config precedence bugs; fat-fingered V-vector | Med | D10 single resolver + write-time validation + vblend stamping | Resolver as only read path — add a lint/test, whitelisting the §2.1 operational valves (`cron.pass_disabled.*`, ingest budget), which legitimately read `model_config` directly |
| R11 | Crosswalk coverage / nflverse schema drift breaks archetypes | Low-Med | D9 null-archetype fail-soft, 90% coverage floor, keep-yesterday | Confirm nflverse attribution requirements in the P3-1 scope block |
| R12 | Push bar starvation for low-activity users | Low-Med | D6 scopes the bar to unsolicited pushes only; monitor per-segment push volume in dark launch | Bar percentile tunable per segment if starvation appears |
| R13 | Profile staleness in deadline weeks | Low | Trailing-window recency weight in market profiles (cheap) | Intra-day refresh is scope creep; only on measured need |

**Open questions for the operator (⛔ = blocking the phase named):**
1. ⛔ (P2-3 fleet rollout) **OQ-1 inheritance:** does the Sleeper agreement cover
   automated public reads? New-links-only backfill until answered.
2. ⛔ (P2-3 fleet rollout) **Postgres timing:** accept the tripwire-before-P2-3
   commitment, or schedule the cutover proactively?
3. UA identity for expanded sweeps — align `sleeper_trades_service` with the
   honest-UA paths, accepting possible Cloudflare friction?
4. D4's promotion numbers (21 nights, 90% CI, 15/21, 4-week online horizon) —
   ratify or adjust *before* counting starts (never after).
5. §5.2 disclosure line + retention numbers (3-season raws) — sign off wording.
6. D7's 2,000 calls/day default — comfortable, or start lower?
7. D6's bypass set (which notification kinds count as "unsolicited") — product
   call; the HLD assumes match/response pushes bypass the bar.
