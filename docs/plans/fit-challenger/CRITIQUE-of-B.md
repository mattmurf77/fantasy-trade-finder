# Critique of draft B (risk/measurement-first) — from the build-first planner

**Date:** 2026-08-20
**Reviews:** [PLAN-v2-draft-B.md](PLAN-v2-draft-B.md) against [PLAN-v2-draft-A.md](PLAN-v2-draft-A.md),
the operator mandate (variety served to testers is a **goal**, not a cost), and the cited
prod numbers in [../trade-engine-accuracy/PLAN.md](../trade-engine-accuracy/PLAN.md).

Draft B is a strong document. Its measurement machinery (pre-registered decision rules,
config-snapshot diffs, the failure-mode table, the F5b serve-bit) is better than draft A's
equivalent sections and most of it should survive into the merged plan — the Concessions
section at the end is long on purpose. The critique below is confined to the genuine
disagreements, and to the places where B's own numbers don't support B's rulings.

Already agreed, not re-argued: `bakeoff_group_size = 0` as the serving posture (both drafts,
same reasoning); M1/M2 landing before any serving flip; arm B always seated; arm A off the
roster; organic path untouched; the C/T coverage (the two tables are near-isomorphic).

---

## 1. The max-2-arms rule and pairwise rounds

### Steelman first

B's §2.1 is the most rigorous piece of thinking in either draft, and three of its
components are simply right:

- **The budget arithmetic is honest.** ~400 decided cards/week is a real ceiling, the
  bucket haircut (f ≈ 0.5) is a real haircut, and nobody before B wrote down that k arms
  divide the same testers' attention.
- **R0 (B vs D) converts idle build time into the accuracy plan's own Phase 1.1.** Arm D
  is built, out-generates B (18.3 vs 15.0 cards/run, 2.0s vs 2.6s), and carries the two
  measured arm-B levers. Reading them on users before committing them to arm B is exactly
  what D exists for. Draft A served D too, but never said *what question D's decisions
  answer* — B did.
- **Arm B seated in every round** keeps rounds mutually interpretable. Correct and adopted.

### The challenge: B's ruling is downstream of one contestable choice, and its own table says so

**(a) "k=4 answers nothing" is contradicted by B's own table.** B's §2.1 table:

| k | 15pp (130 cards) | 10pp (300 cards) |
|---:|---:|---:|
| 2 | 1.3 wk | 3.0 wk |
| 3 | 1.9 wk | 4.5 wk |
| 4 | **2.6 wk** | 6.0 wk |

At the 15pp resolution, k=4 answers in 2.6 weeks — *inside B's own 3-week contamination
ceiling*. k=3 answers in 1.9 weeks with margin. The "maximum 2 arms" ruling holds **only**
if 10pp is the required resolution for the first read. B asserts 10pp without defending it;
everything else follows mechanically.

**(b) 10pp is the wrong bar for a first read between structurally different generators.**
The effects in play are not subtle knob nudges. The prod basis split is 22.4% vs 5.7%
like-rate (~17pp between two paths of the *same* engine); the fit arm replaces the entire
candidate universe. The PRD's own success criterion (§7) is *"a measured like-rate that is
not worse on `both_high`+`mixed`"* — a non-inferiority framing, not a ±10pp superiority
test. First-round questions between generators are "is this roughly as good or obviously
better/worse," which 15pp resolution answers. Precision belongs in the *confirmatory* round,
after screening — which is standard sequential design, not corner-cutting.

**(c) B double-counts one protection and ignores another.** B concedes interleaving is
within-subject ("treat that as margin, not as license for a third arm") — but margin is
exactly what licenses are made of: paired within-deck comparisons at these n's materially
beat the independent-samples numbers the table is built on. And B's ceiling premise (rounds
>3 weeks are presumed contaminated) presumes the failure of the change-control discipline
*that the same plan enforces and mechanically verifies* (§2.3.2 snapshot diffs). B cannot
both trust its contamination machinery enough to run 3-week rounds and distrust it enough
to forbid 4.5-week ones. See §4 below.

**(d) The gen_v2 "decision budget" claim is factually wrong under the agreed serving
posture.** With `bakeoff_group_size = 0` the draft is a plain per-arm team draft: an arm
that generates **zero cards contributes zero cards to the deck and consumes zero decisions**.
gen_v2 zero-cards in 12 of 18 non-boarded-league runs — in exactly those leagues, rostering
it costs its ~218ms of job time (the cheapest arm by far: 218ms median vs current's
2,593ms) and nothing else. It consumes deck share only where it *works* (the boarded
league, 8.4 cards/run) — which is precisely where its cards are informative and precisely
the variety the operator asked to preserve. B benches an arm whose cost model B got wrong.
The honest statement of gen_v2's cost is "a modest share of the boarded league's deck,"
not "decision budget across the tester base."

**(e) The mandate is not neutral between these designs.** The operator ruled: *"a
multi-model test preserved — variety served to testers is a goal, not a cost."* B's §2.1
treats variety purely as a cost to be minimized (two arms, sequential rounds, one arm
benched indefinitely). A plan may argue the operator's goal is expensive — B does, well —
but it may not silently re-rank the operator's objective function. Draft B never states
that its design contradicts an operator ruling; it should.

**(f) Sequential rounds introduce a confound B's own evidence base names.** R0 runs W1–W2
on fresh testers; R1 runs W4–W6 on testers 3–5 weeks into churning decks. The accuracy
plan's position-curve finding (like-rate 16.9% → 50%+ across deck depth) and the fatigue
machinery both say decision behavior drifts with exposure. "Arm B always seated" controls
this *within* a round, but B's program draws cross-round conclusions (D's verdict, then
fit's verdict, then a promote decision comparing them implicitly) across different
tester-fatigue regimes. Simultaneous serving is the design that removes cross-round drift
entirely — one more reason within-subject k=3 is worth its longer 10pp clock.

### The defensible middle (proposed for the merged plan)

**Screen-then-confirm.** Serve B + fit + D simultaneously (gen_v2 rostered too — it
self-caps by supply, see (d)), pre-registered at **15pp / non-inferiority resolution**,
for 2–3 weeks. Then:

- If fit's bucketed read is decisively up or down at 15pp → verdict, done, ~3 weeks
  earlier than B's W7.
- If fit lands inside ±15pp and the decision needs 10pp precision → run B's pairwise
  round (B vs fit, k=2, `bakeoff_include_challenger = 0`) as the confirmatory window,
  exactly per B's §2.5 rules.

This preserves the operator's variety, gets fit decisions ~2–3 weeks sooner in expectation,
keeps B's worst-case calendar (the confirmatory round is B's R1, just conditional), and
adopts B's pre-registration discipline wholesale. Effective k is ~3 (gen_v2 supplies few
decks), so even the 10pp read arrives at ~4.5 weeks if the screen is ambiguous — one
window-boundary past B's ceiling, with the snapshot-diff machinery deciding validity
rather than a presumption.

---

## 2. F5b serve-bit + dark soak vs draft A's no-soak canary

**What each protects against.** B's dark soak protects against three concrete failure
modes: (i) job-time blowout — a fit run pushing p95 past `_JOB_HARD_TIMEOUT` marks the job
**error** and the tester gets *no deck at all*, which presents as an app outage, not a
bake-off artifact (B's failure row 4 — the single best row in its table); (ii) junk/pick
flood reaching testers before anyone measures top-quartile shares (C5); (iii) enumerator
supply bugs (fit cards/run < 5). Draft A's canary protects against the same list with:
fixture dry run + conservative `fit_max_packages_per_pair = 5,000` + operator-first
exposure + hours of natural lag before other testers' jobs run + one-knob rollback.

**The honest comparison.** Draft A's real reason for skipping the soak was mechanical, not
philosophical: in A's architecture, roster membership = serving once interleave is on, so
a fit dark soak would have required re-darkening all arms — the cost was the decision
stream, so A priced the soak out. **F5b dissolves that constraint for 0.5 eng-days.** With
a serve-bit, fit can soak in real prod jobs (real rosters, real ms, real bucket mix —
things the fixture cannot fully produce) while B/D/C keep serving and the decision stream
never pauses. Once the soak costs no calendar and no decisions, refusing it is not
build-first, it is just less evidence for the same speed.

**Where B still overprices it:** a full week (W3) is more soak than the failure modes
need. All three targets are visible within 2–3 days of prod runs (ms and diagnostics land
per run, not per week). And B's soak sits behind R0's two-week round, so fit serves W4 at
the earliest even if it is ready and clean in W2 — that latency is charged to the pairwise
design (§1), not to the soak itself.

**Merged position:** adopt F5b and a **3-day dark soak with B's numeric exit bars**
(p95 ≤ 30s, cards/run ≥ 15 boarded, junk ≤ 0.10, pick share ≤ B+10pp), then flip
`bakeoff_serve_fit = 1` at the next Monday boundary. Draft A's R3 (accepted risk: no prod
soak) is withdrawn — B won this point on the mechanism, and the mechanism makes the
speed/evidence trade a false choice.

**One gap in B's own treatment:** F5b is new code on the serving-composition line — the
exact line B's §9.5 warns about. B tests it in CI
(`test_serve_fit_bit_excludes_from_draft`) but arms no **prod** tripwire. The merged plan
adds one readout row: any `model_arm = 'fit'` impression while `bakeoff_serve_fit = 0` →
serving-path bug, stop. Missing from B's failure table (see §5).

---

## 3. The arm-B lever freeze ("read through arm D rounds, never shipped mid-round")

Less conflict here than the coordinator's framing suggests. Draft A never scheduled
`user_elo_shrink` or soft R5 — its Stage 3 explicitly left the Phase-3 queue to the
accuracy plan. So on the core rule — **no arm-B engine change lands inside a measurement
window** — the drafts already agree, and B's sharpening (a roster change *is* the week's
one engine-affecting change; moves land on Monday boundaries; the `trade.outlook_direction`
flip gets exactly one legal slot) is adopted without reservation. It is the operational
form of accuracy-PLAN 0.4, which both drafts claim to honor; B actually scheduled it.

Two qualifications:

1. **"Only through arm D rounds" should not mean "only through a dedicated k=2 D round."**
   Under the merged §1 design, D serves simultaneously in the screening window; its cards
   read the levers there — more slowly than a dedicated round, but continuously and without
   holding fit's serving hostage to D's verdict. If the screen resolves fit at 15pp while
   D's lever read is still accumulating, that is fine: the two questions were never
   actually coupled, only calendared together by B.
2. **The freeze needs an escape clause B omitted:** a *severity* exception. If a guardrail
   trips (deck shrink, timeout errors), the fix ships same-day and the window is
   sacrificed — B's own tripwires imply this but its change-control §2.3.1 reads as
   absolute. Write the exception down so the first incident doesn't become a debate about
   whether the rules allow fixing it.

Which yields? Draft A's Track-1 timeline survives intact — it never contained a mid-round
lever ship. B's calendar yields only where §1 already moved it (fit serves on soak-exit
rather than after R0 completes).

---

## 4. The 3-week contamination ceiling and the window-discard rule

**The ceiling: a useful prior wearing a constraint's uniform.** Its evidentiary basis is
historical change velocity (five knob waves in five days) — from *before* M1 existed,
before `config_json` snapshot diffs, before the one-change-per-window rule was operational.
B's plan then builds the machinery that makes that history obsolete (M1 log, §2.3.2
mechanical diffs, discard rules) — and *still* prices rounds as if the machinery will fail.
This is self-inconsistent in the direction that matters: the ceiling is the load-bearing
premise of the k=2 ruling (§1), so an assumption about undisciplined pasts ends up
dictating the entire serving architecture of a disciplined future. Merged plan: keep the
3-week mark as a **review trigger** (a round crossing it gets its snapshot-diff audit read
before its verdict is trusted), not as a design constraint that forbids k=3.

**The discard rule: over-extended from the one case where it's right.** HANDOVER trap 5's
"discarded, not caveated" applies to re-ranker contamination — where position balance is
destroyed *unrecoverably and without a timestamp*: there is genuinely nothing to salvage.
B extends the same rule to any engine-affecting knob change mid-window. But a knob change
is precisely the failure M1 makes *recoverable*: it has an exact logged timestamp, so the
right operation is **censoring — split the window at the change, keep both clean
segments** — not discarding a week of the scarcest resource in the program (≈400 decided
cards) because one key moved on a Wednesday. B built the knob log and then declined to use
its one analytical superpower. Merged rule: re-ranker contamination → discard (trap 5,
verbatim); logged knob change → split at timestamp, report both segments, count neither as
a full window; *unlogged* change discovered only by snapshot diff → discard, because the
timestamp is the thing you don't have. That last clause also gives the M1-bypass risk
(draft A's R5) a defined consequence, which neither draft had.

At this n the difference is not pedantry: under B's rule, one mistimed flip costs ~25% of
a round's evidence; under the split rule it costs only the boundary hours.

---

## 5. The failure-mode table — errors, redundancies, omissions

The table is the best artifact in either draft and the merged plan should carry it
forward. Specific findings:

**Wrong / miscalibrated:**
- **Row 1's abort bar is looser than its own baseline justifies.** Median < 15 on two
  consecutive days before the same-day revert — against a 26.5 dark baseline, a sustained
  median of 16–19 (a ~35% deck shrink) never trips it. The 2026-08-18 incident was a
  10-card deck from a 40-card pool; the lesson is that *partial* shrink is the silent
  version. Tighten: median < 22 investigate same day (B has this at < 20), **median < 18
  on 2 consecutive days → revert** (not 15).
- **Row 10's "extend the round 1 week (once)" quietly violates B's own 3-week ceiling**
  for a 2-week round extended — the table and §2.1 disagree about what happens in week 4.
  Under the merged §4 treatment (ceiling as review trigger) this resolves itself; under
  B's own rules it is a contradiction.

**Redundant (acceptably):** rows 6 and 7 (re-ranker contamination vs interleaver-order
bug) overlap in signal but differ in cause and remedy; keeping both is right. Row 8
duplicates §2.3.2 but a tripwire table should be self-contained; fine.

**Missing:**
- **Serve-bit leak (F5b's own failure).** New draft-exclusion code on the exact line that
  failed 2026-08-18, with CI coverage but no prod detection. Add: any `model_arm='fit'`
  impression while `bakeoff_serve_fit = 0` → serving bug, same-day stop (§2 above).
- **Cross-round tester drift.** B's sequential-rounds design has no row for its own
  largest structural exposure: R0 and R1 sample different fatigue/novelty regimes (§1f).
  Detection: arm B's own like-rate compared across rounds (it is seated in both — B built
  the control and never queried it). Divergence in arm B across rounds → cross-round
  comparisons are suspect even though each round is internally valid.
- **M3 stamp version skew is covered (row 11) but M3 stamp *absence* is not:** if the
  try/except silently eats scoring failures for a class of cards (e.g., all cards of one
  basis), bucket-matched comparison quietly becomes bucket-biased. Detection is cheap:
  readout reports `fit_diag` null-share per arm; > 5% → investigate. (B's row 2 covers
  null buckets on *fit-arm* rows only.)
- **Tester-base concentration.** ~10 testers means one hyperactive tester can be 30%+ of
  a week's decisions; a per-tester decided-cards cap or at minimum a readout row (max
  single-tester share) belongs in the table. Neither draft had it; the merged plan should.

---

## Concessions

### Accepted from B into the merged plan

1. **F5b `bakeoff_serve_fit` serve-bit** — 0.5d that dissolves the roster=serving coupling;
   withdraws draft A's accepted risk R3.
2. **Prod dark soak for fit** — at 3 days with B's numeric exit bars (p95 ≤ 30s, ≥15
   cards/run boarded, junk ≤ 0.10, pick ≤ B+10pp), not a calendar week.
3. **M3 diagnostic fit-score stamp on all bake-off arms** (`fit_diag`, version-pinned,
   inert-by-test) — upgrades draft A's "optional M2b" to build-now; it is what makes the
   co-primary genuinely bucket-matched.
4. **Pre-registered decision rules (§2.5)** — promote/iterate/kill written before serving,
   Wilson intervals, <3pp reads as "did not move," one-knob iterates.
5. **Roster changes count as the week's one engine-affecting change; all moves on Monday
   window boundaries; `trade.outlook_direction` gets one named legal slot.**
6. **No arm-B engine change mid-window; levers read via arm D before committing to arm B**
   (with the severity escape clause added, §3).
7. **The failure-mode table as a standing artifact** — with the §5 amendments (tightened
   row 1, four added rows).
8. **Daily (not weekly) deck-integrity queries during any serving transition week.**
9. **`features_json.fit.boards ∈ {both, viewer, none}` as the C4 mechanism** — cleaner
   than draft A's `fit_data_basis`; readout never splits fit by `basis`.
10. **No tester-league allowlist** — B's TestFlight-only observation is correct and
    disposes of draft A's S1a check; the note moves to NEXT.md as launch-blocking later.
11. **Knob registration → `snapshot_config()` → `config_json` diff interlock** (T4 side
    benefit draft A missed), and the two extra scope blocks (`scope-measurement.md`,
    `scope-serving.md`).
12. **Readouts as a checked-in SQL pack + dated files in `readouts/`**, and numeric S2
    bars for junk/pick shares where draft A only said "report."

### Still rejected, with reasons

1. **Max-2-arms as a hard rule** — B's own table shows k=3–4 answers 15pp inside its own
   ceiling; within-subject pairing adds margin; and the rule silently re-ranks an explicit
   operator goal (variety). Replaced by screen-at-15pp (k≈3–4) → confirm-at-10pp (k=2,
   B's own R1) only if the screen is ambiguous.
2. **gen_v2 benched indefinitely** — its stated cost ("decision budget") is factually
   wrong under the agreed plain draft: a zero-supply arm consumes zero decisions and
   ~218ms; it self-caps by supply and supplies cards only where they are informative.
3. **Fit held to W4 behind a completed 2-week R0** — the pairwise calendar, not the soak,
   is what delays fit; under screen-then-confirm fit serves at soak-exit (~W2–W3).
4. **The 3-week ceiling as a binding design constraint** — it presumes the failure of the
   discipline the same plan builds; demoted to a review trigger.
5. **Whole-window discard on any mid-window knob change** — a logged change has a
   timestamp; censor/split at it. Discard is reserved for re-ranker contamination and
   *unlogged* changes (trap 5's actual scope).
6. **S0's auto-kill at ≤1.2× arm B's distinct ideas** — the PRD says success is not "more
   cards" (§7); the dual-score/presentment change is independently capable of moving
   like-rate at equal volume. A volume shortfall at S0 is a finding that reframes the
   test, not grounds to refuse to run it. (Softened, not deleted: ≤1.2× triggers an
   operator decision, not an automatic no-roster.)
7. **A full week of dark soak** — every soak target (ms, supply, junk shares) is visible
   in 2–3 days of prod runs; the marginal 4 days buy calendar loss, not evidence.
