# PRD: P0 — Close the Loops

> Phase P0 of the trade-relevance initiative
> ([enhancement-plan.md](../enhancement-plan.md) §Phase 0). Parents are SIGNED
> OFF and binding: [hld.md](../hld.md) (D1/D2/D11, §2.1, §6) and
> [lld.md](../lld.md) (build steps B1–B8, §4.1–4.6, tests T-1..T-9, T-23,
> T-29). This PRD frames WHY and WHAT; mechanics live in the LLD and are
> referenced, not restated. Dual-agent authored; log in
> [../reconciliation-log.md](../reconciliation-log.md).

## 1. Summary

FTF already paid for a full learning loop — frozen-feature impressions, outcome
labels, bandits, an offline replay harness — and the loop doesn't cycle. The
strongest labels we collect (a user accepting or declining a real proposal)
never join back to the impressions that produced them; 28 kinds of client
signal are silently discarded with a 200 OK; a live bug lets any stale or
foreign impression id poison another user's taste vector; near-identical cards
repeat inside one deck; a "bad trade" flag helps exactly one user once; and the
nightly cron everything depends on fails silently partway through. P0 closes
these loops with no new data sources and no new models. **P0's success is
loop-integrity counters, not engagement movement** — six items ship, only two
(dedup, class demotion) touch serving at all, and those two flip serially,
alone, with observation windows. Everything later (F6 promotion, market data,
archetypes) compounds on these labels and this observability.

## 2. Problem & Context

Five loops are open today, each with a named cost:

1. **The nightly tick is a single point of silent failure.** Pushes,
   replenishment, eval, and refit run inline in one worker; an exception
   mid-way silently skips everything after it, and nothing durable records
   which passes ran (HLD §2.1). The operator cannot answer "did eval run last
   night?" without reading logs. Hidden prerequisite the plan under-weighted:
   fixing this is a behavior-preserving refactor of *live push-sending code* —
   its blast radius is real users' notifications, so it gates everything else.
2. **Our most business-real labels are orphaned.** `trade_accepted`/`declined`
   events know the trade but not the impression that served it; a first-person
   decline — the strongest negative in the system, already worth a 30-day
   suppression — teaches the ranker nothing. P1's accept/decline heads starve
   until this join exists.
3. **A live data-integrity hole poisons taste vectors today.**
   `_save_deck_outcome_safe` accepts any ≤64-char impression id and taste then
   mutates the *impression owner's* vector (LLD §4.3/E3). Not a future risk —
   silently active now.
4. **Signal we already emit is thrown away.** 28 mobile event types
   (`untouchable_toggled`, `trade_keep_side_tapped`, …) are 200-OK'd and
   dropped; P2-5's activity features have nothing to read.
5. **Protection doesn't generalize; decks repeat.** A flag suppresses one card
   for one user while the same *class* of bad suggestion keeps serving to
   everyone; near-identical packages around one centerpiece burn the user's
   limited swipe attention.

Users affected: **end users** (fewer duplicate cards; flagged classes demoted
fleet-wide; accept/decline finally teaches the system) and the **operator**
(queryable answers to "did the tick run", "why is this deck thin", "what's the
join rate").

## 3. Goals & Non-Goals

**Goals**

- G1: Every nightly pass leaves a durable, queryable record; a mid-tick death
  never silently cancels downstream passes (D1).
- G2: Proposal dispositions land as impression-keyed `deck_outcomes` labels,
  per perspective, exactly once (D2).
- G3: Outcome writes are validated server-side — the taste-poisoning hole
  closes the day B5 ships.
- G4: The 28 dropped client events are registered and accepted per the
  taxonomy process (P0-1).
- G5: Flag signal aggregates per exposure; bad classes are demoted fleet-wide,
  bounded, never gated (D11).
- G6: Served decks contain no near-duplicate packages per the LLD §4.6 metric.
- G7: Gate kills are countable per gate per job; "why is this deck thin" is
  answerable from the admin report (P0-6, HLD §6).
- G8: Ordering changes preserve replayability by construction — frozen
  multipliers + nightly drift check (B8, HLD §2.3).

**Non-Goals** (each is a rejection rule in review)

- No F6 promotion decision or serving flip — `deck.value_model` stays dark;
  P0-2's read-the-gate call and all D4 machinery are P1 (B9/B10). Stating this
  here prevents "while we're in the tick, let's flip the model."
- No new data sources: no ingestion widening, backfill, standings, archetypes,
  profiles (P2/P3).
- No push-surface impressions, no push eligibility bar (P1-3/B11).
- No user-visible UI changes — backend + taxonomy + admin report only; the R7
  web `impression_id` echo is invisible client plumbing (Maestro-waived);
  Maestro waivers filed per backend step.
- No taste-reward changes for the four new disposition labels —
  `_reward_for`'s unknown→0.0 stands (a correct fail-safe); explicit rewards
  are a later, separate PR (LLD §6.2). This is the adjacent surface a builder
  might "helpfully" extend during B5.
- No gate-semantics changes: P0-6 counts kills, never alters a verdict (T-29);
  demotion is a bounded multiplier, never a drop (D11).
- No changes to hourly/realtime ticks — the ledger covers daily-tick only.

## 4. Success Metrics

All readable from `/api/admin/analytics/relevance` (HLD §6). Honest
denominators are part of the definition:

| # | Metric | Definition | Target | Window |
|---|---|---|---|---|
| M1 | Ledger green-rate | `ok / (ok + error + timeout)` over **enabled** passes; `skipped` rows are excluded from the denominator but split by cause — valve-off/flag-dark ("dark: n") vs **global-deadline skips**, which get their own line and an alarm on N consecutive deadline-skips of the same pass (a chronically starved pass must not show 100% green) | 100%; any `error` is a page-the-operator line; zero undetected-skip days | trailing 14d |
| M2 | Exact join rate | exact-joined disposition labels / disposition events **whose disposing actor's original like/swipe carried an `impression_id`** — a blended all-dispositions rate is refused (it would measure client mix, not code). Separately reported: fuzzy-fill rate on NULL sides (no target — unique-hit is deliberately conservative) and %-of-dispositions-with-carrier (driven toward ~100% by the R7 web echo) | exact ≥ 95% | trailing 30d, from B5+7d |
| M3 | Client-event acceptance | events accepted / received for the 28 names; forecast-vs-actual volume within 2×; per-event arrival table at +14d — **zero arrivals for a name is a finding (dead emitter), not a failure** | drop count = 0 | from B3 |
| M4 | Near-dup rate | served pairs meeting the §4.6 metric / served cards, plus the mandatory `deduped_cards_per_job` counter — drops are pre-capture, so **only a counter can see them**. Baseline mechanics: B7 computes the metric per job **regardless of flag state** (the flag gates only the drop), accumulating ≥7d before the flip — the logged `features_json` alone can't reconstruct it | < 1% with `deck.dedup` on (vs that measured baseline) | trailing 7d |
| M5 | Rejection visibility | `outcome_rejected{reason}` live; foreign/stale/push writes accepted = 0 (T-8); rejections < 1% of outcome writes (higher ⇒ client bug or probing — either is a finding) | as stated | from B5 |
| M6 | Demotion pipeline honesty | count of classes reaching n ≥ 200 views (at current volume **may be ~0 — a reported honesty number, not failure**; P0's deliverable is the pipeline + operator report); flag-rate trend on any demoted classes | pipeline green; trend not worsening | 30d post-flip |

**Explicitly not P0 metrics:** north star (proposals+accepts/WAU), flag-rate
reduction, any engagement number. P0 exits on loop integrity; claiming
engagement wins from plumbing invites attribution theater.

Guardrails (regression ⇒ rollback per flag): north star does not regress; p95
`/api/trades/generate` unchanged (±5%); decks never thinned below
`_DECK_MIN_CARDS` (T-5); tick behavior-preservation (T-1).

## 5. Requirements

Numbered, testable; each cites the binding LLD section.

- **R1 — Pass ledger (B1; LLD §3.3/§4.1).** Registry + `cron_pass_runs`, one
  row per (pass, run_date); states `running|ok|error|skipped|timeout`;
  double-POST claims via `uq_pass_run` (T-2); **mandatory stale-`running`
  recovery** (T-3); `season_start` split out as `must_complete_today` with the
  Aug-25 winback suppression preserved (T-1 fixture); kill valves
  `cron.pass_disabled.<name>` in `model_config`, absent ⇒ runs. "Green-rate"
  is defined before launch (M1). Render's mid-tick-502 retry semantics are
  verified and runbook'd **during** the B1 soak, not after an incident.
- **R2 — Behavior-preserving refactor (B1).** Identical side effects and
  response JSON (minus `passes`) with all valves absent; T-1 green gates every
  later P0 PR; the ledger merges first and **soaks ≥3 days** before any new
  pass registers.
- **R3 — Package skeleton (B2; LLD §2.1).** `backend/relevance/` with
  `batch_write` (product engine, short transactions, no socket held across a
  write) and the D10 `resolve()`/`valve()` resolver as the only legal knob
  read path (T-28 lint).
- **R4 — Event registration (B3; P0-1). ⟨SUPERSEDED 2026-08-14, same day as
  authoring⟩** The G-031 session independently shipped this (PR #116, merged
  to `main` @ `4733f78`): 27 names registered with props mirroring emitters,
  INTENT/NON-INTENT classified same-commit, `quickset_completed`'s client
  emitter deleted rather than registered, and a dated seam note (no
  historical series before 2026-08-14). **Remaining B3 work is
  verification-only:** confirm the registered set covers every event P2-5's
  activity features read, and inherit PR #116's seam annotation instead of
  this PRD's forecast/annotation steps (kept below for the record). Original
  requirement — bright line, never express:
  Sequence: (1) one week of drop-counting first, producing an events/day
  forecast (actual within 2× or alert); (2) registration with props specced
  against the taxonomy up front (the NULL-`platform` incident rule); (3)
  dashboard baselines annotated with the registration date — no KPI spans the
  boundary as a raw count series; (4) per-event arrival reported for 14d. PII
  scrub unchanged.
- **R5 — Gate counters (B4; LLD §4.2).** Counters per gate per job; one
  `deck_job_stats` insert per completed job (its request-path latency
  contribution measured once); counting only — a diff flipping any gate
  boolean fails review and T-29.
- **R6 — Swipe validation (B5; LLD §4.3).** All **six** call sites pass
  `acting_user_id` (required kwarg — a missed site is a loud TypeError);
  writes require impression exists + owner matches + `served_at ≥ now−14d` +
  deck surface; rejection ⇒ no outcome row, no taste write, counted; route
  still 200s. Acceptance: T-8.
- **R7 — Disposition join (B5; LLD §4.4–4.5, D2).** Per-side threading, four
  enum labels written per-perspective **atomically inside the disposition
  transaction**, idempotent on `(impression_id, action, source_match_id)`;
  NULL side-B never guessed; nightly `join_repair` fuzzy-fills on unique hash
  hits only; fuzzy default-excluded from training; direct-send proposals
  create no match row. **Scope includes the ~20-line web diff echoing
  `impression_id` on swipe** (LLD §8.1) — without it M2's
  carrier-share is a structural hole the D4 promotion timeline inherits.
  Acceptance: T-6, T-7, T-9.
- **R8 — Flag aggregation + demotion (B6; LLD §4.6, D11).** EB-shrunk
  flag-rate per (archetype, shape_bucket, receive_value_band); demotion
  clamped [0.5, 1.0]; n < 200 views ⇒ exactly 1.0; applied multiplier frozen
  into `features_json`. Two pre-build checks: (1) **numerator purity** —
  verify the flag route is the sole writer of `not_interested`, else mint a
  distinct action (a shared action demotes innocent classes); (2) the
  Python-side JSON group-by states a row ceiling + chunked iteration (the 60s
  budget is a hope, not a design, at 10× volume). Operator report lists
  demoted classes with n; a human decides if any deserves a real gate.
  Acceptance: T-23.
- **R9 — Dedup (B7; LLD §4.6).** Deterministic, pre-Thompson, **pre-capture**
  (dropped cards never logged ⇒ replay untouched by construction); `likes_you`
  immune; min-cards restore. States story, stated: dedup applies at job
  creation only — a served deck is never recomposed under the user; there is
  no "restored card" UX because drops are never served. Operator undo: flag
  off (hard) or `dedup_overlap_tau`=1.0 (soft); both act within one job cycle
  with zero data repair. Acceptance: T-5.
- **R10 — Propensity freeze + drift check (B8; LLD §4.13, HLD §2.3).** Applied
  multipliers frozen at serve; nightly sampled drift check; violation ⇒ pass
  `error` + `untrusted-<date>` marker. Acceptance: T-4.
- **R11 — Admin relevance report (P0-6; HLD §6).** Ledger strip, gate-kill
  funnel, loop health (M1–M6), guardrails; read-only engine; ledger + counter
  tables only.
- **R12 — Doc hygiene (plan §P0).** Fix the stale `analytics_queries.py:23`
  comment, `architecture.md` request-lifecycle, `feature_flags.py:422` F4
  comment, `api-reference.md` "ships dark" header; repoint
  `tiktok-discovery/current-state.md` at `ftf-current-state.md`.

**NFRs.** All schema additive + idempotent (T-25); rollback never needs schema
removal; serving-path additions are keyed lookups + O(n²≤40) set math — no
per-card queries, no request-path network; `cron_pass_runs` registered in the
90d retention endpoint in the B1 diff; dialect-portable statements (LLD §6.4);
full four-gate treatment per item — schema/analytics items hit the bright
line, never express.

## 6. Scope & Phasing

**MVP cut line = LLD build steps B1–B8, in build order** (each ships alone):
B1 ledger (R1/R2) → B2 skeleton (R3) → B3 registration (R4) → B4 counters
(R5) → B5 threading + validation + web echo (R6/R7) → B6 flag aggregation
(R8) → B7 dedup (R9) → B8 freeze + drift (R10). Plus R11 report and R12 doc
hygiene. Below the line: B9–B15 entirely (F6 v2, promotion, surface column +
push bar, ingestion, archetypes, P4 surfaces).

## 7. Dependencies & Risks

**Dependencies.** B6 needs B1+B2; B8 needs B1; the rest independent. No
external data, no OQ-1/Sleeper exposure — P0 deliberately avoids every ⛔ item
in HLD §8. Code-seam anchors verified at HEAD 2026-08-14; **re-verify before
build** (concurrent sessions ship to this repo).

| Risk | Sev | Mitigation | Residual |
|---|---|---|---|
| B1 refactor destabilizes live pushes (HLD R1) | High | T-1 equivalence incl. Aug-25 fixture; merge-first + 3d soak; per-pass valves | Render retry semantics verified during soak |
| Propensity corruption via new layers (HLD R4) | High | §2.3 contract; pre-capture dedup; frozen demotion; T-4 | Drift check is sampled |
| Six items ⇒ unattributable metric soup | Med | Only 2 serving-visible flags, flipped serially with windows; everything else claims no user metric | — |
| Demotion punishes a class on noise | Med | 200-view floor, EB shrinkage, 0.5 clamp, report-not-gate; T-23 | Thresholds tuned after first real data |
| Join mislabeling poisons future training | Med | Exact-first; fuzzy marked + excluded; ambiguity ⇒ NULL; T-6/T-9 | Carrier share on web until the R7 echo ships |
| `not_interested` numerator conflation | Med | R8 sole-writer verification before build | — |
| Validation rejects legitimate laggard swipes | Low | 14d window; older-but-valid ids pass; M5 reasons watched | Window tuned from data |
| SQLite contention from flag_agg | Low at P0 volume | `batch_write` discipline; locked-count feeds the Postgres tripwire | Tripwire matters at P2 |

## 8. Rollout & Measurement

Flags (default False, registered in the same PR): `deck.dedup`,
`deck.class_demotion`. Valves: `cron.pass_disabled.<name>` (unseeded). Seeds:
`class_demotion_floor` 0.5, `class_demotion_min_views` 200,
`dedup_overlap_tau` 0.75.

**Dark-launch order (LLD §6.1; flags flip only left→right; no two
serving-visible flips inside one observation window; a flip during an
unresolved anomaly on the previous flip is forbidden):**

1. Schema adds land dark (NULL-tolerant readers; day-one-empty invariant).
2. B1 ledger merges on T-1 green; **3-day soak**; watch M1.
3. B3 registration (after the 7-day forecast) + B4 counters + B5 threading
   ship **write-only**; M2/M3/M5 accumulate.
4. `deck.dedup` ON, alone; 7d window on M4 + latency guardrail.
5. `flag_agg` runs dark ≥7d → operator reviews the demoted-class report →
   `deck.class_demotion` ON, alone; M6 + drift check green.

**Rollback:** every step is flag-off + truncate-safe (LLD §6.3); residue
tables are truthful history, never hand-repaired. **Exit = M1–M5 at target,
M6 pipeline green, guardrails clean** — that state is P1's entry condition:
D4 promotion counting needs these labels and a trustworthy ledger.
