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
4. **Ghosts are OUT — operator ruling 2026-08-21 (post-sign-off amendment):**
   `is_ghost=1` rows never enter the grading queue; the dual-signed served-vs-ghost
   internal control analysis was deleted by the ruling. Historical rows stay untouched in
   the DB; user-facing numbers were never affected.
5. **Viewer-scoped v1** with the maturity/"preregistration ledger" state as the launch
   hero — the honest empty state is the trust pitch, not an apology.

## Reconciliation log

**Document type:** full planning suite · **Rounds run:** 3 (parallel independent drafts →
synthesis → cross-review → re-review) · **Converged:** YES — dual sign-off at round 3
(both lenses' round-3 review of the amended tree found the SAME single defect — the T-2
sign pin — independently; fixed, plus 13 non-blocking folds, in the closing commit).

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

### Round 2 (cross-review of commit `fad7d0f`)
Both reviewers returned NO sign-off — 8 distinct blocking objections (one shared), all
accepted and fixed in the amendment commit:

- **A/B-1 (shared with BB-1 spirit) — drift-cancellation overclaim:** "additive drift
  cancels for every shape" is false (edge = d·Δcardinality). D-1/T-2/PLAN §3.2/PRD §4.1
  restated as the true invariants; residuals disclosed per shape cell.
- **A-B2 + B-BB1 — pick weighting unit bug + import contradiction:** GENERIC_PICK_SEEDS
  are Elo units read live (deploy-variant, D-084 class) and the conversion path was
  banned/import-blocked. Fixed: `RECEIPTS_PICK_WEIGHTS` frozen value-unit constants
  inside the grader (versioned under `grader_version`); imports widened to
  `pick_values.parse_generic_pick_id` (import-safe by design); owned-pick regex copied
  locally; DR-4(2) ban qualified (valuation/edge arithmetic); T-4 deploy-invariance case.
- **A-B3 + B-BB2 — coverage denominator uncomputable / degenerate:** Σcv0 of players
  with no cv0 is always 0. Fixed: explicit weight convention (graded → cv0; unresolved →
  serve-date floor, flagged; picks → frozen weights); knob compares min(sides); ordered
  terminal checks; either-side-zero-graded ⇒ ungradeable (never one-sided — preserves the
  market control and the midpoint).
- **B-BB3 — Wilson formula wrong** (center shift dropped, 0.2–0.4 at n≤10 on a trust
  feature). Corrected + pinned to 3/5 → [0.231, 0.882].
- **B-BB4 — remaining/backfill contradiction + hot-loop:** `remaining_resolvable`
  (excludes retry-pending) precomputed into the 202; backfill terminates on two
  consecutive zero-work runs; run ledger becomes start-row + end-row pairs (killed runs
  visible, still append-only).
- **B-BB5 — n not pinned to the displayed cohort:** n and the min-n gate are now
  post-dedup, post-coverage counts, asserted `n == len(rows used)` in tests.

17 non-blocking suggestions; all folded except two recorded as positions (admin `dedup`
param defaults to the user-surface rule; `EDGE_PCT_MIN_MIDPOINT` constant chosen over a
knob to keep the honesty rules version-pinned rather than tunable). Round-3 re-review
requested from both lenses on the amended commit.

### Round 3 (re-review of commit `3e57305`) — CONVERGED
Both reviewers verified all eight round-2 blockers genuinely closed (Wilson recomputed
independently; deploy-invariance, positive denominators, ledger pairs, n-semantics all
confirmed) and **independently converged on one identical new blocker**: the amended T-2
pinned the disclosed additive-drift residual with the wrong sign — under the taxonomy
§2.1 direction convention a 2x1 (give 2, receive 1) has `n_receive − n_give = −1`, so
`edge = −d`, not `+d`. T-2 was the matrix's only sign-sensitive test, so the mis-pin
could have shipped every win rendered as a loss. Fixed: pin restated as `−d` plus an
explicit directional win case (`receive +d, give flat → edge = +d`). Thirteen further
non-blocking folds: single backfill-termination rule (zero TERMINAL rows, twice); round
≥5 owned-pick clamp to the round-4 weight; format-wide floor-date fallback; effective
window restated 11–20d; admin surfaces exempted from the user coverage filter (invariant
`n == rows used` holds per surface); skip-and-fill vs LIMIT implementation note;
disclosure example completed (`ties`, `null_edge_pct`, `low_coverage`); numeric-suffix
ordering for `grader_version`; HLD import-line sweep.

### Unresolved disagreements
None — both lenses signed off. Two synthesis positions stand as recorded above (admin
dedup default; constant-over-knob for the midpoint guard).

### Post-sign-off amendment — operator ruling 2026-08-21 (ghosts out)
After dual sign-off, the operator ruled against ghost cards entirely. Superseded on one
point: the signed design graded `is_ghost=1` rows as an internal served-vs-ghost control
(old HLD D-5, PLAN §3.5, PRD DR-6). Amended: ghost rows are excluded from the grading
queue (`is_ghost IS NULL OR is_ghost = 0`, LLD §4.1), the served-vs-ghost analysis and
admin split are deleted, PLAN Q-5 (ghost-end verification) is resolved-moot, and the P0
ghost query becomes cohort sizing only. Historical rows stay untouched in the DB
(append-only; exclusion is queue/read-time). Every user-facing denominator already
excluded ghosts, so **no user-facing number changes** — the ruling removes only the
internal control analysis. This entry, not the round-3 text, is authoritative on ghosts.

## Sibling coordination (three-plan batch)

Contract: [PLAN.md §7](PLAN.md). Counterparts: `docs/plans/counterparty-breaker/PLAN.md`
§8 (their branch) · `docs/plans/negative-results-memory/research-verification.md` (their
branch). Table prefixes: `receipts_` (here) · `negmem_` · `breaker_`. Taxonomy 1.1.0
(objection vocabulary, per-code producer column) is reserved in the shared file, authored
by the breaker session, pending three-way sign-off.
