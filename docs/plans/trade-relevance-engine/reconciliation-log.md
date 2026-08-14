# Reconciliation Log — Trade Relevance Engine planning artifacts

> **Purpose:** the dual-agent authoring record for [hld.md](hld.md), [lld.md](lld.md),
> and the five phase PRDs in [prds/](prds/). Each artifact was drafted by two
> adversarial Fable-model subagents (Author/Coherence lens vs Adversary/Risk lens),
> synthesized by the orchestrator, then cross-reviewed until sign-off or the round
> cap. This log records what each lens challenged, what changed, and anything left
> unresolved. Process definition: `.claude/skills/dual-agent-doc-review`.

---

## HLD (hld.md)

**Document type:** HLD **Status:** in review (round 2 running)

### Round 1 — independent drafts → candidate v1

Two independent drafts (A: architecture-coherence; B: failure-modes/scale)
converged on the same fundamentals independently — a good sign the shape is real:
extension-not-new-system, one new batch package, purpose-named profile tables,
in-process logistic ranker widened from F6, platform-identity keying for pre-join
history, exposure-normalized flag demotion as a bounded multiplier (never a gate),
push bar enforced at send-assembly.

Synthesis decisions where the drafts differed:

| Topic | A's position | B's position | Candidate v1 resolution |
|---|---|---|---|
| Nightly job execution | Jobs inline in daily-tick, fail-soft try/except each | Pass registry + `cron_pass_runs` ledger + per-pass budgets/kill flags; heavy work in queued daemon threads | **B adopted wholesale** (§2.1, D1). A's fail-soft-only pattern is the observed failure mode (silent partial execution); the ledger is cheap and doubles as the observability spine |
| SQLite posture | "WAL and short transactions should hold" (risk note only) | WAL is actually OFF today; enable as P0 hygiene + one batch-write helper + pre-committed Postgres tripwire | **B adopted** (§2.2). A's assumption was factually wrong per `analytics-platform/prd-reconciliation.md:25` |
| Promotion criterion | "Assume SNIPS lift with ESS gate, numbers belong to the scope block" | Pre-registered two-sided criterion with concrete numbers (21 nights, 90% CI, 15/21, symmetric kill) | **B adopted as D4**, with the numbers marked operator-ratifiable before counting starts (open question 4). A's deferral is how "graduate or kill" rode NEXT.md for a week |
| Multi-head honesty | Ships all 9 heads, "hierarchical fallback past a minimum-label threshold" | Per-head ≥300-positive floor; honest statement that v2 launches ~4 live heads; negative-mass clamp | **B adopted as D5**; A's framing understated the sparsity reality |
| Backfill scope | League-link + retroactive daemon sweep for already-linked leagues | New-links-only until Sleeper OQ-1 (public-read agreement coverage) is answered; global 2k/day budget | **B adopted** (§5.1, D7). OQ-1 is on record as unresolved-blocking in the device-auth PRD |
| Raw retention for backfilled transactions | Prune raws ≥3 seasons old | 18-month raw retention | **A adopted (3 seasons)**: B's own recovery model (derived tables rebuild from raws) is incoherent with pruning raws before the 3-season backfill depth. Flagged for operator sign-off (open question 5) |
| Table names | `league_market_profiles`, `manager_trade_profiles`, `deck_class_stats` | `league_market_stats`, `opponent_profiles`, `flag_class_stats` | **A's names** (purpose-named, platform-identity keying is more precise); B's retention column and league-scoping guarantees folded in |
| Push impressions | Not addressed | Push sends log `surface='push'` impression rows so surfaces are separable in training | **B adopted** (D6) |
| Cold-start serving | Not addressed | Learned scores only past ≥20 outcomes per user | **B adopted** (§5.3) |
| Label maturation | Not addressed | 14-day maturation horizon; fuzzy joins marked and default-excluded | **B adopted** (§3.2, D2) |
| P4/privacy copy rules | Product sign-off needed (risk note) | Confidence gates, banned-copy rules, templates-only, user-editable/deletable profiles | **B adopted as D9 + §5.2**; A's "needs sign-off" kept as open questions 5/7 |

Live questions carried into round 2: the push-bar bypass set (which kinds are
"unsolicited") — operator question 7; whether the pass-ledger refactor's blast
radius on existing push idempotency is understated; the two-sided impression join
for P0-3 (proposer's vs counterparty's impressions).

### Round 2 — cross-review (8 blocking objections, all fixed in v2)

Both reviewers spot-checked the codebase; every structural seam claim held except
one shared factual error.

**A raised (2 blocking):**
- *WAL claim stale* — the HLD said "WAL is actually off" citing the analytics
  reconciliation, but that finding was fixed and shipped (v1.9.0): on-connect
  listener sets WAL + busy_timeout + autocheckpoint (`database.py:83-96`), boot
  check exists. → §2.2 rewritten: keep the assert, real content is batch-writer
  discipline + Postgres tripwire; noted which engine `batch_write` uses (product,
  not the fail-fast ingest engine). B raised the same error independently.
- *P0-4 demotion breaks the §2.3 replay contract* — the multiplier reads a
  nightly-mutating table, so "deterministic given features_json" was false; replay
  would need serve-time table state, which D8 forbids. → §2.3 gains the corollary:
  any value read from a mutating table is frozen into the serve-time capture;
  D11 states it.

**B raised (6 blocking, one shared with A):**
- *P0-3 join incoherent about match lifecycle* — matches are created by mirrored
  likes (`server.py:10265`), not proposes: two like-moments, two impressions;
  fuzzy matches can't share a trade_hash; B's own first-person decline (the
  strongest negative, drives 30-day suppression) had no label; direct-send
  counterparties have no impression at all. → D2 rewritten: per-perspective
  event→label map (first-person `accepted`/`declined` + counterpart
  `accepted_by_partner`/`declined_by_partner`, four enum values not two),
  `impression_id_a` recovered at match creation inheriting the match's fuzziness,
  `impression_id_b` nullable.
- *D4's 21 nights ill-defined* — refit is gated behind the same flag D4 keeps
  dark (stale artifact), or ungated (different model nightly, aggregate
  meaningless); replay has no maturation cutoff and matches never hard-expire, so
  the newest tail is censored toward "no accept." → D4 rewritten: split
  `train.value_model` from `deck.value_model`; pin the candidate artifact id for
  the whole window; disposition-labeled metrics restrict to matured impressions.
- *`surface='push'` corrupts replay as designed* — no surface column was
  declared; `load_decks` selects everything; push rows would fabricate NOT-NULL
  fields and enter training as one-card pseudo-decks. → §3.1: `surface` is a real
  column with defined push-row semantics (propensity=1.0), and the
  `surface='deck'` filters land in `load_decks` + refit builder in the same
  change as push logging (P1-3), not later.
- *WAL* — same as A's; one fix.
- *`cron.pass.<name>` flags fail unsafe* — `feature_flags.py` drops undeclared
  keys and `is_enabled(unknown)=False`, so "default ON" either breaks the
  all-False convention or silently kills the pushes pass; features.json also has
  deploy latency. → kills moved to `model_config` as `cron.pass_disabled.<name>`
  (absent ⇒ runs; typo fails safe; live DB write = immediate).
- *Pushes pass isn't idempotent as claimed* — rerun safety exists only via
  send-time caps/dedup; quiet-hours queueing logs nothing; date-gated
  `season_start` work is lost forever if deferred past its date. → §2.1 gains
  the registry-enforced invariant (every push kind needs a cap or dedup key) and
  the resumable-next-day vs must-complete-today classification.

**Non-blocking suggestions applied:** vblend storage can't assume a JSON column
(`model_config.value` is Float — LLD chooses keyed rows or a small table); D11's
join key named (flags attribute via the impression-keyed `not_interested`
outcome row); counterparty activity = `users.last_active_at`; behavior-preserving
registry refactor + hourly/realtime-tick out of ledger scope; `why` endpoint
ownership check; P3-3 taste/wildcard archetype widening reinstated + P3-4
absorbed into `user_value_profiles` (both had been silently dropped); per-phase
honesty checks carried into §6; header marks lld.md forthcoming.

### Round 3 — cross-review of v2 (A signs off; B raises 2, fixed in v3)

**A: SIGN-OFF yes.** Verified both round-2 blockers resolved against code
(`database.py:83-96`/`131` for WAL; §2.3/D11 for the frozen demotion value) and
all cross-lens fixes coherent. Non-blocking suggestions applied: Component B now
says "four D2 disposition labels" (was still the two-label shorthand);
`deck.value_model` declared the single serving gate (v1 vs v2 = artifact family,
no second gate that can disagree); operational valves declared exempt from D10's
resolver precedence.

**B: SIGN-OFF no (2 blocking), after verifying all six round-2 fixes as real
against code.**
- *A/B side-binding inverted vs code* — `create_trade_match` (`database.py:6684`)
  defines `user_a` = the swiper whose like *triggered* the match (impression in
  hand) and `user_b` = the earlier-liking counterparty (needs recovery); the v2
  text had the letters backwards and made `_b` the nullable direct-send slot —
  transcribing it would silently swap `accepted`/`accepted_by_partner`
  attribution on the sparse accept head. → D2 + §3.1 rebound to code semantics:
  `impression_id_a` ↔ `user_a_id` (exact, in hand), `impression_id_b` ↔
  `user_b_id` (recovered, inherits match fuzziness, nullable on recovery
  failure); stated that direct-send proposals create **no** match row (mirror
  path is the only creator; platform-side dispositions out of P0-3 scope); LLD
  note added that exact recovery is cheapest by threading `impression_id` into
  `save_trade_decision` at swipe time.
- *Push-row filters covered only 2 of 6 readers* — F9's prior-deck check,
  Thompson arm events, fatigue events, and D11's exposure denominator would
  still ingest push rows. → §3.1 now defines a closed action set for push
  impressions (deck actions never ride them) and a default rule: every
  impressions⋈outcomes reader filters `surface='deck'` unless it explicitly
  opts in — all six readers named as in-scope for P1-3.

B's non-blocking applied: bounded same-day retries for must-complete-today
passes (≤2, then `error` + operator alert); valve exemption from D10 (same as
A's); D2 recovery-mechanics LLD note.

### Round 4 — cross-review of v3 (cap round): **CONVERGED, both sign-offs**

Both lenses ran delta reviews of v3 with code spot-checks. B verified both of
its round-3 blockers genuinely closed (`create_trade_match` docstring and sole
call site match the rebound letters; all six reader anchors check out). A
verified the same from the coherence side and confirmed every factual claim in
the rebound D2 (including that the swipe body carries `impression_id`, grounding
the recovery route). Zero blocking objections from either lens.

Final polish applied from A's last non-blocking notes: push-native outcomes
tightened to tap-through only (dispositions attach to match-side deck
impressions, never push rows); R10's future resolver lint whitelists the §2.1
operational valves.

**Document type:** HLD **Rounds run:** 4 **Converged:** yes
**Unresolved disagreements:** none between the lenses. Operator decisions
remain open by design — hld.md §8 lists 7, two blocking (Sleeper OQ-1 coverage
for public reads; Postgres cutover timing), plus ratification of the D4
promotion numbers, retention/disclosure wording, ingest budget, and the push-bar
bypass set.

---

## LLD (lld.md)

**Document type:** LLD **Status:** in review (round 2 running)

### Round 1 — independent drafts → candidate v1

The drafts converged independently on: vblend as per-head keyed `model_config`
rows + active pointer (identical decision, both lenses); the `backend/relevance/`
package; `find_matching_like` returning the matched like's impression;
disposition labels written per-perspective; nflverse via downloaded season files
with a coverage gate. Divergences, adjudicated:

| Topic | Implementer (A) | Reviewer (B) | Resolution |
|---|---|---|---|
| Dedup placement | Post-final-sort, pre-cap (interacts with the Thompson draw) | Pre-Thompson on the base-keyed list, pre-capture (deterministic; dropped cards never logged) | **B** — cleaner under the §2.3 propensity contract; A's min-cards restore + likes_you immunity folded in |
| Dedup tau | 0.6 | 0.75 | **0.75** (conservative start; it's a `model_config` knob) |
| Ingest budget persistence | Process-local counter + daily table flush (restart overshoot ≤ chunk) | `ingest_budget` table with atomic check-and-take UPDATE | **B** — restart-proof and race-free at no real cost |
| Pass-ledger claim | Composite-PK upsert | INSERT-claim on `uq_pass_run` + `running` status + mandatory stale-claim recovery | **B** — the stale-`running` rule is what prevents a mid-pass OOM wedging a pass all day |
| Pushes pass classification | Statically must-complete-today (self-flagged as too strict in its §8) | Only the Aug-25 date gate needs it | **Split `season_start` into its own must-complete-today pass** (A's own alternative); `pushes` stays resumable |
| D4 pin mechanics | `promotion.json` + CLI | `activate` records in `models.jsonl`; eval scorer gains `record_id` param | **Both, separated**: promotion.json = eval-counting state (pin ≠ activation); activate records = serving pointer (solves v1/v2 mixed-deploy + rollback-by-append) |
| Disposition label write site | Route-level after `record_match_disposition` returns | Inside `record_match_disposition`'s existing transaction | **B** — atomic (decision + labels commit together); adds `source_match_id` idempotency key |
| Fuzzy recovery | Inline at disposition time | Nightly `join_repair` pass, unique-hit-only | **B** — one mechanism, covers pre-P0-3 matches, keeps the route fast; unique-hit-only guards label poison |
| Push bar thin history | Fail-closed ("insufficient history" ⇒ ineligible) | Fail-open with `reason='no_history'`, counted | **B** — the no-history cohort is the new-user cohort the replenish push activates (HLD R12); logged as a genuine disagreement resolved on HLD-intent grounds |
| Archetype formulas | Named absolute per-game thresholds | Within-season z-scores + REQUIRED_COLS drift gate | **A's axes/thresholds** (concrete, testable) + **B's REQUIRED_COLS gate**; z-scores noted as a future refinement |
| `why` route authz failure | 403 on foreign impression | Uniform 404 + rate limit (anti-oracle) | **B** |
| Coefficient clamp | ±300 Elo | ±600 Elo | **±300** (conservative; D9 "plausible band") |
| v2 artifact schema | `SCHEMA_VERSION=2`, `from_dict` dispatch | v2 records omit the `"model"` key so the v1 loader skips them (v1 would otherwise deserialize an empty-weight head scoring constant 0.5) | **B** — survives mixed deploys, not just clean upgrades |

B also surfaced a **live bug** (foreign/stale `impression_id` accepted by
`_save_deck_outcome_safe` → another user's taste vector poisoned) — specced as
§4.3 validation and flagged to the operator as a standalone fix candidate.
B's Platt guard (≥50 rows AND ≥8 positives + slope clamps) and class-weighted
loss adopted wholesale; A's full DDL, market/activity formulas, and
value-decomposition design matrix adopted wholesale.

### Round 2 — cross-review (9 unique blockers, all fixed in v2)

**A raised (3):** the vblend validator's weight-space negative-mass rule
mathematically rejects `DEFAULT_VBLEND` (Σ|neg| 68 vs 0.8·Σpos 30.2) and every
X-style blend D5 prescribes → rule dropped, protection stays the D5 runtime
clamp; `sends_push: bool` had nothing to check against → `push_kinds` tuple +
registration assert + lint; `UPDATE … ORDER BY LIMIT` cursor claim not portable
→ two-step select-then-guarded-update (shared with B).

**B raised (6 more):** promotion machinery unimplementable against
`backend/eval/` as it exists (no lift CI, 95%-vs-90% mismatch, ambiguous
baseline) → §4.7 now specs the replay deltas (new metrics flag/fast_pass/
accepted-matured, paired cluster-bootstrap lift CI with `ci_level`, baseline
frozen as `"production"` in promotion.json, pinned-scorer factory);
opponent-profile formulas were a circular reference and `faab_aggression` had no
denominator → four formulas written out + `settings.waiver_budget` persisted at
`/league/{id}` fetch; the D10 resolver had no overlay-discovery mechanism →
`KNOB_EXPERIMENTS` registry, unregistered knobs skip the overlay tier; the HLD
§5.3 cold-start minimum (20 outcomes) had silently regressed to ≥1 → seeded
knob + v2 serving gate + T-31; the `season_start` split repealed the Aug-25
winback suppression → `pushes` retains the `is_aug25` skip, T-1 fixture includes
Aug-25; the 3-season raw-retention window and the account-deletion cascade had
no implementation story → ingest retention step (§4.9.6) + §6.5 deletion-registry
rule + T-32/T-33.

Non-blocking applied: six (not four) `_save_deck_outcome_safe` call sites with
the validated-id return; D11 class key fixed to `receive_value_band` with the
JSON-parse note; `_replenish_deck_for` return extension; mixed-scale percentile
noted as accepted artifact; `get_scorer` factory mechanism; migration idiom
(Column in Table + data-dictionary rows); `cron_pass_runs` retention
registration in the B1 diff; 14×14 matrix; `budget_s` semantics;
`save_deck_outcome` signatures; activate-pointer interface; `card_meta` keys;
rate-limiter mechanism; T-34 lift-CI test.

### Round 3 — cross-review of v2 (2 blockers, both fixed in v3)

Both lenses verified every round-2 fix against code (six call sites exact;
replay.py/scorers.py/nightly.py match the §4.7 delta spec; the Aug-25 fan-out
`continue` and inbox-before-push ordering hold; retention-vs-profiles racing
benign).

- **A:** the v2 vblend fix wasn't propagated to T-26, whose sabotage list still
  demanded the removed negative-mass rejection — the test layer would have
  reintroduced the bug. → T-26 reworded to sign-class violation +
  "DEFAULT_VBLEND passes its own validator."
- **B:** `waiver_budget` had no storage home (no `leagues` metadata column
  exists; ancestor leagues have no `leagues` row at all). → `waiver_budget`
  column added to `ingest_cursors` (per-(league, season) — matching both the
  semantics and the fetch sites); §4.9.5/§4.10 reference it.

Non-blocking applied: §4.3 call-site count aligned to §2.1's six; pinned-scorer
registration made idempotent with a late-binding factory reading promotion.json
at call time (raised by both lenses); §6.5 anchor corrected to
`delete_user_data` (`accounts.py:619`) + the export tuple (`:754`) added for
symmetry; §4.9.6 clarified to run in the synchronous pass body, not the daemon
thread.

### Round 4 — cross-review of v3 (cap round): **CONVERGED, both sign-offs**

Both lenses ran narrow delta reviews. A re-verified the T-26/vblend fix against
the actual constants (DEFAULT_VBLEND is sign-consistent and passes) and the
six-site enumeration; B traced every `waiver_budget` reference and confirmed
the `ingest_cursors` home works for live and ancestor leagues with no competing
storage location left in the doc. Zero blocking objections. Final polish from
the round: the `MAX(waiver_budget)` read rule (NULL sibling rows can't shadow),
the §4.1 `ingest_advance` parenthetical, and T-32 wording.

**Document type:** LLD **Rounds run:** 4 **Converged:** yes
**Unresolved disagreements:** none between the lenses. §8 carries 7
non-blocking flags for scope blocks (web impression_id echo recommended;
match-scan index; 21-counted-nights calendar expectation; dual join_quality
columns rationale; price_level small-n; nflverse column verification; Chrome-UA
posture pending the HLD's operator question 3).

---

## PRDs (prds/)

**Document type:** PRD ×5 (one per phase) **Rounds run:** 2 each (dual
independent drafts → synthesis → one strict cross-review + fixes)
**Converged:** yes (P0 signed off clean; P1–P4 each had 2 blockers, all fixed
and the fixes verified against the objection text)

**Scaling note:** per the skill's effort-scaling license, the review round ran
as ONE reviewer per PRD holding both bars (product + feasibility) instead of
two — the drafts were independent, the synthesis was the orchestrator's, and
the parents had already survived 4-round reviews. Blocker yield (8 across 5
docs) suggests the compressed round still had teeth.

### Round 1 — drafts → candidates

Per PRD, the product lens supplied structure/stories/goals and the risk lens
supplied decision rules; notable adjudications: P0 pulled the web
`impression_id` echo INTO scope (A had left it operator-optional; the join
metric is structurally broken without it); P1 adopted the ESS-starvation
verdict, the 12-week pin cap, and the A/B-as-harm-check framing; P2 replaced
"day-zero personalization" with the honest 48h/7d SLO and operationalized
OQ-1 (owner, 14-day ask, 60-day default, defined "no" branch); P3 adopted the
Gate-0 measurements (incl. the honest note that the prod eligibility query
was permission-blocked during authoring — the number is unmeasured), the
threshold panel, and the anti-circularity single-source rule; P4 adopted the
20% coverage flip bar, the kill-metric thresholds, template governance, the
tombstone/opt-out edit semantics, and the conditional P4-4 descope.

### Round 2 — cross-review (8 blockers, all fixed; parent docs amended)

- **P0: sign-off, no blockers.** Six polish items applied (M4 baseline
  computed flag-off, M1 deadline-skip split, web-echo non-goal reword, taste-
  reward non-goal, M2 phrasing).
- **P1 (2):** the D4-online-clause refinement was unflagged (parent-wins rule
  would have silently overridden the pre-registered harm-check) → named as an
  explicit D4 amendment, HLD D4 updated pending OQ ratification; the push-bar
  success paragraph prescribed a comparison it simultaneously ruled
  inadmissible → verdict-bearing contrast named (in-window sent vs suppressed
  counterfactual, DiD on the dark-window baseline; the *naive* cross-date
  comparison is what's banned). Non-blocking: cold-start count aligned to the
  LLD (no maturation filter); OQ-4 marked ⛔ (audit row precondition = LLD
  route delta); post-cap semantics (fresh window, no partial credit);
  `pass(no_history)` counted as sent-with-reason.
- **P2 (2):** the §8 flag order contradicted LLD §6.1 AND the PRD's own SLO →
  aligned to profile-passes-before-backfill, and LLD §6.1 amended to decouple
  `relevance.profiles` from `data.archetypes` (flips end of P2; P3 extends it
  with the holdback) — else P2's success metric waits on P3; R5's standings
  catch-up was a silent LLD §4.9 override → kept, landed as a logged LLD
  amendment with the corrected ≤18-call bound. Non-blocking: arithmetic
  phrasing fixed (60 = per-league 3-season total); T-35 propagated into LLD
  §7 with the parked-mechanism and **last-unlink** condition; the OQ-1 "no"
  mechanism named (no per-class budget knob exists).
- **P3 (2):** three legitimate refinements silently amended parent text
  (coverage denominator, blend rule, `season_source`) → explicit
  parent-amendments preamble + HLD D9 and LLD §3.3/§4.11 updated in the same
  change; Sep–Oct tag serving was self-contradictory → defined (tags travel
  with the served row; suppression on the served row's own games; veterans
  keep prior tags, rookies stay suppressed). Non-blocking: lift criterion
  stated (CI excludes zero); holdback disables ALL archetype consumption;
  `relevance.profiles` co-gating caveat; draft-capital pedigree deferred (no
  source); weekly-actives defined.
- **P4 (2):** R7's propensity exclusion was vacuous where it pointed and
  overridden where it mattered (the signed-off route served raw propensity in
  `score_components`) → LLD §2.3 amended: relative-contribution labels only,
  raw internals never serialized, serializer test covers the full payload;
  R14/R15 rewrote LLD schema semantics unflagged and the opt-out had no home
  → explicit LLD-amendments note; writer invariant + tombstone test land with
  B14 (P3); full delete = opt-out **stub row** (one table, covered by
  cascade/export/T-32). Non-blocking: all thresholds declared
  operator-ratifiable seeds; hook is a distinct payload field with
  min-app-version gating (never prepended into `reasons[]`); counterfactual
  hook-eligibility stamping for a like-for-like kill metric; interim trust
  posture (hooks live without the correction surface) surfaced for operator
  sign-off.

### Unresolved disagreements

None between lenses. The operator decision queue (consolidated): HLD §8's 7
questions (2 ⛔: Sleeper OQ-1, Postgres timing) + P1 OQ-1..4 (3 ⛔:
D4+R5+harm-check ratification, D6 bypass set, WAU/MDE arithmetic; OQ-4 now
also ⛔ for P1-4 activation) + P2's OQ-1 ownership clock + P3's Gate-0
measurements and panel + P4's threshold ratification and interim-trust
sign-off.
