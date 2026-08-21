# Receipts

Grade past trade suggestions against subsequent consensus value movement — the serve-time
`deck_impressions` row is the immutable, preregistered prediction; a recurring job marks it
to market at 14/28/56 days; users see their league's track record (both sides, wins and
losses); the operator gets per-taxonomy-cell accuracy with honest intervals. No competitor
grades its own advice.

**Status:** planned, not built · 2026-08-21 · planning branch `plan/receipts`
**Process:** dual-agent doc review (Author/Feasibility × Adversary/Risk); reconciliation log below.

## Doc suite (read in this order)

| Doc | What it fixes |
|---|---|
| [scope.md](scope.md) | Feature gates: analytics events, schema/flags, D-056 evidence plan, docs table |
| [PLAN.md](PLAN.md) | Objective, phases P0–P4, honesty rules, risks/aborts, **three-plan reconciliation contract** |
| [HLD.md](HLD.md) | Architecture, data flow, 11 key decisions with rejected alternatives |
| [LLD.md](LLD.md) | Schema DDL, 3 routes, grader pseudocode, edge cases, test matrix T-1…T-10, P0 prod queries |
| [PRD.md](PRD.md) | Metric spec (swap edge), banned phrasing, 12-entry decision register, requirements & states, rollout |
| [../shared/trade-shape-taxonomy.md](../shared/trade-shape-taxonomy.md) | Shared vocabulary, v1.0.0 — co-owned with negative-results memory + counterparty breaker |

## The five decisions that matter most

1. **Swap edge, not acquire-side %** — grade `receive-delta − give-delta` on consensus;
   the give side is the market control; standalone "+14% acquire" is banned phrasing.
2. **Valuation never comes from the frozen card** — `features_json` values may be
   personal-basis; both grading endpoints come from `player_value_history`. The frozen
   prediction is the *asset set and direction*.
3. **Append-only + `grader_version`** — corrections are new versions with visible
   footnotes, never edits; preregistration is mechanical (4 forbidden ops, each test-pinned).
4. **Ghosts graded, internal-only, as a bounded cohort** (holdout closed
   ~2026-08-21T00:43Z, verify at build) — the served-vs-ghost read the accuracy plan asked
   for, without ever leaking a withheld card to users.
5. **Viewer-scoped v1** with the maturity/"preregistration ledger" state as the launch
   hero — the honest empty state is the trust pitch, not an apology.

## Reconciliation log

**Document type:** full planning suite · **Rounds run:** 2 (parallel independent drafts →
synthesis → cross-review) · **Converged:** see final report to operator.

### Round 1 (independent drafts → synthesis)
Both lens drafts are preserved in the session scratchpad (draft-A author/feasibility,
draft-B adversary/risk). Synthesis resolutions:

- **Headline metric** — A: acquire-delta headline + `beat` flag · B: swap edge, acquire-%
  banned. **Adopted B** (market-drift + exponential-units + personal-basis objections are
  each fatal); A's `beat` survives as `edge > 0` (identical), A's both-sides display
  becomes the only row format.
- **Bust handling** — A dropped window-missing players from both sums (silent
  survivorship bias flattering the engine). **Adopted B's pool-floor imputation** (D-8);
  this was the round's most valuable catch.
- **Whose receipts** — A: league track record + best/worst · B: viewer-only, no league
  aggregate. **Adopted B's scoping** (privacy/reverse-engineering at n≈5), kept A's
  best/worst-call pair within the viewer's own rows; league-wide deferred to operator (Q-2).
- **Pre-telemetry rows** — A: grade-status rows for all ~7.7k · B: excluded by queue
  predicate, disclosed by read-time count. **Adopted B** (23k junk rows avoided; NG-7).
- **Job execution** — A: inline batched cron (cap 2000) · B: 202 + daemon + single-flight
  (cap 500). **Adopted B** (single-worker reality), kept A's run-ledger table and
  backfill script.
- **Cron provisioning** — A: 4th render.yaml cron at P1 · B: operator-curl first.
  **Synthesis: dedicated endpoint + daily-tick internal guard** (roster_history
  three-trigger precedent; the value-snapshot "provisioned cron" precedent turned out to
  be fictional — commit `1e50d3e`), render.yaml optional (Q-4).
- **Taxonomy home** — A: new `backend/trade_shape_taxonomy.py` + docs/design doc ·
  coordinator ruling: the three-way-agreed `docs/plans/shared/trade-shape-taxonomy.md`
  stays the artifact of record. **A's module carried as a proposed 1.2.0 direction**
  (PLAN §7.1); A's version-stamp idea survives as a receipts-local constant. A's
  composite `shape_key` string dropped for denormalized columns (HLD D-11).
- **Analytics** — A: 3 events (viewed non-intent) · B: 1 event (opened, intent).
  **Merged: 3 events with B's intent classification** for `receipts_opened` (DR-9).
- **grader_version type** — A: integer · B: string `'receipts-1'` (fit-1 precedent).
  **Adopted B.**
- **Citation corrections during synthesis:** A's `pick_values.py:727-761`
  format-derivation cite was wrong (file is 483 lines) — replaced with
  `set_league_scoring` (`database.py:6897`) / `_detect_scoring_format_from_meta`
  (`server.py:725`); added `latest_value_snapshot_date` (`database.py:10883`) as the
  nearest-date idiom.

### Round 2 (cross-review of this committed suite)
Recorded in the final report to the operator (objections, fixes, and any unresolved items
with both positions).

## Sibling coordination (three-plan batch)

Contract: [PLAN.md §7](PLAN.md). Counterparts: `docs/plans/counterparty-breaker/PLAN.md`
§8 (their branch) · `docs/plans/negative-results-memory/research-verification.md` (their
branch). Table prefixes: `receipts_` (here) · `negmem_` · `breaker_`. Taxonomy 1.1.0
(objection vocabulary, per-code producer column) is reserved in the shared file, authored
by the breaker session, pending three-way sign-off.
