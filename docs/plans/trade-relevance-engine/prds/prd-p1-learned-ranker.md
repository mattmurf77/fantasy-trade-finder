# PRD: P1 — Learned Ranker Live

> Phase P1 of the trade-relevance initiative
> ([enhancement-plan.md](../enhancement-plan.md) §Phase 1). Parents SIGNED OFF
> and binding: [hld.md](../hld.md) (D3/D4/D5/D6/D10, §5.3) and
> [lld.md](../lld.md) (B9–B11, §4.7/4.8/4.13). This PRD states what users and
> the operator get, the decision rules, and how we know it worked; mechanics
> are referenced, not restated. Dual-agent authored; log in
> [../reconciliation-log.md](../reconciliation-log.md).

## 1. Summary

Every deck today is ordered by one hand-tuned formula — the same for the
rebuilder who only calc-opens 2-for-1s and the contender who proposes every WR
consolidation. F6, the learned model that predicts what *this* user acts on, is
built, evaluated nightly, and dark. P1: promote it with statistical discipline
(P1-1, the D4 pinned-artifact criterion), widen it from 2 predicted actions to
the logged action ladder (P1-2 — honestly ~4 live heads at current volume),
hold unsolicited pushes to a stricter bar than requested decks (P1-3), and move
ranking tuning into versioned config (P1-4). The engineering risk is not the
code — seams, fallbacks, and rollback are specified — it is that **the phase's
clock and verdict are both statistical objects at a data volume that may not
support them**; this PRD's job is the decision rules for exactly that.

## 2. Problem & Context

- The learned ranker exists and nobody reads its nightly evidence (plan P0-2);
  "graduate or kill `deck.value_model`" has ridden NEXT.md since 2026-08-08.
- The composite formula cannot express per-user taste beyond bounded
  multipliers; the logged ladder (view → like → calc-open → propose →
  accepted/declined, plus flags) is mostly unmodeled.
- Pushed suggestions clear no higher bar than in-deck cards: an unsolicited
  notification can carry a card the deck pipeline would have buried.

**User value:** decks ordered by what this user actually acts on; fewer,
better push interruptions; every ranking change proven offline before any user
sees it. **Operator value:** graduate-or-kill decided by pre-registered
numbers, not vibes; ranking tuning becomes a validated config write with
one-UPDATE rollback.

## 3. Goals & Non-Goals

**Goals**

- G1: A serving decision on `deck.value_model` is *reached* — **promoted or
  killed, both are success** (D4 is symmetric; a clean kill that routes effort
  to P1-2 labels is a shipped outcome).
- G2: F6 v2 live with the honest D5 head roster (~4 heads at current volume:
  viewed→like, calc_open, propose, flag); disposition heads activate only at
  ≥300 matured positives.
- G3: Push eligibility enforced at send-assembly for unsolicited suggestion
  pushes, after a dark counting window; match/response loops untouched.
- G4: V-blend in versioned config, governed, stamped into every impression.

**Non-Goals — each names its creep vector; refusals are part of the spec**

1. **No dwell-as-reward.** Dwell never enters the V-vector; session minutes
   are a cost (standing guardrail).
2. **No engagement-optimized push volume.** No learned component ever decides
   to send *more* pushes; volume stays an editorial cap. P1-3 only makes
   pushes rarer and better.
3. **No per-user V-vectors.** D10's "per-user setting" precedence slot is for
   existing prefs, not per-user blends; the first request to personalize V
   goes to a future phase with its own eval story.
4. **No bar on match/response pushes.** Someone will ask to bar them "for
   consistency" — the bar exists only for unsolicited recommendations. The
   bypass set is ratified once (OQ-2), then changes only by ADR.
5. **No second serving flag** — v1 vs v2 is the artifact pointer behind the
   one gate.
6. **No realtime/online refit.** "The model didn't learn from my swipe yet" is
   correct behavior, not a bug.
7. **No mid-experiment tuning.** During any counting or A/B window: no vblend
   activation, no criterion edit, no bar change except full rollback — tuning
   during measurement voids the measurement.
8. No transformer/sequence models; no learned quality gates; no P2/P3/P4 work
   (the V-vector schema carries all 9 slots from day one so their arrival is
   config, not schema).

## 4. Success Metrics

**Primary, sequenced:**

1. **Offline (the promotion authority):** the pinned artifact meets D4 — over
   21 counted nightly replays, positive SNIPS lift over composite with 90%
   cluster-bootstrap CI excluding 0 on ≥15 nights, ESS gate every counted
   night, no replayed guardrail degrading beyond its CI.
2. **Online (a guardrail trial, pre-registered as such). Explicit refinement
   of HLD D4's online clause:** D4's letter says the A/B is "judged on the
   north star over a pre-set 4-week horizon"; at current TestFlight-scale WAU
   a 4-week 50% split has an MDE far above any plausible lift, so judging on
   an undetectable metric would be theater. This PRD refines the clause —
   **the online window checks for harm; the offline D4 verdict is the
   promotion authority** — and D4's online sentence is amended to match upon
   OQ-1 ratification (recorded in the reconciliation log; until ratified,
   D4's letter stands). Decision rule, written before the flag flips: keep
   the flag on iff (a) no guardrail (flag rate, suppression-undo, decline
   rate, first-session like rate, retention) degrades beyond its pre-set
   bound, and (b) the north-star point estimate is not negative beyond a
   pre-set floor. Inconclusive north-star CI with clean guardrails ⇒ **stay
   on**, keep measuring passively. The A/B still runs (exposure logging,
   future pooled analysis) with its power limits stated in the scope block,
   arithmetic shown (OQ-3).

**Push-bar success — the verdict-bearing contrast, named:** run the bar
**dark ≥2 weeks** (evaluated + counted, not enforced) to calibrate cohorts;
then, **within the enforcement window**, compare engagement on sent pushes vs
the suppressed cohort's inbox-only engagement (the counterfactual), using the
dark window as the difference-in-differences baseline for how those cohorts
compared before enforcement. Success = the sent cohort out-engages its
suppressed counterfactual beyond the dark-window gap, with unsolicited volume
down; **volume down alone proves nothing.** What is inadmissible is the
*naive* cross-date comparison (raw tap-through before vs after the enable
date) — the dynasty calendar confounds it; the DiD structure above is exactly
how the dark window is used instead.

**Guardrails:** flag rate, fast-pass rate, decline rate, first-session like
rate, per-segment push volume (starvation watch: sustained >60% suppression in
any active segment triggers the per-segment bar review). **Explicitly not a
metric:** session minutes.

## 5. Requirements

### P1-1 — Promote by the pre-registered criterion (LLD B10 §4.7; HLD D4)
- R1. Split `train.value_model` (refit) from `deck.value_model` (serving);
  refit runs dark nightly.
- R2. Pin one artifact; the window evaluates only it; re-pin mid-count
  refused; disposition metrics matured-only; drift-marked nights don't count.
- R3. Numbers (21/15/90%/ESS/4-week horizon) **operator-ratified before
  counting, never lowered after** (OQ-1).
- R4. **Symmetric kill** at 21 counted without 15 wins — no silent extension.
- R5. **ESS starvation is itself a verdict.** If after 8 calendar weeks
  `counted < 14`, the pass emits `ESS_STARVED`; the pin is **not-evaluable**
  (distinct from not-better); the response is fixing estimability
  (exploration invariants, exact-join rate) — never waiting harder, never
  lowering `ess_min` mid-count. **Hard cap: 12 weeks per pin, then unpin.**
  Post-cap semantics, explicit: a re-pin (same or different artifact) starts
  a fresh window with **zero carried counted nights** — a window at 20
  counted / 14 wins at week 12 is discarded wholesale, no partial credit, no
  "one more night" (that temptation is exactly when the rule must hold);
  repeated ESS_STARVED loops have no automatic exit — operator-owned.
- R6. Criterion met ⇒ human steps by design: operator activates the artifact,
  flips the flag, starts the A/B.

### P1-2 — Multi-head widening, honestly scoped (LLD B9 §4.7–4.8; HLD D5)
- R7. Full 9-head registry; ≥300-matured-positive activation floor; parent
  fallback with child V zeroed. **Honest launch ≈ 4 live heads.**
- R8. Score = Σ V_a·P(a), inspectable in config; runtime negative-mass clamp
  so one sparse miscalibrated head cannot zero a deck.
- R9. Any scoring failure serves composite byte-identically; users never see
  an error state.
- R10. Training/eval read deck-surface, matured, non-fuzzy rows only; push
  impressions never contaminate deck training or cold-start status.
- R11. **Claims gate:** until a head is `active=true`, no user-facing, App
  Store, or push copy may claim the ranker learns from accepted/declined
  trades; P4 hook templates referencing disposition learning block on the
  same predicate; the admin report's head roster is the source of truth. The
  V-vector carrying `accepted: 20.0` from day one is a config slot, not a
  capability claim.

### P1-3 — Push/pull split + surface separation (LLD B11 §4.13; HLD D6)
- R12. Unsolicited suggestion pushes clear: percentile ≥ P75 of the user's
  trailing deck scores, zero fatigue debt, `relaxed` falsy,
  `basis != 'consensus'`, counterparty active ≤14d. Enforced at
  send-assembly; pull decks never thinned by push rules.
- R13. Fail-open under thin history (<5 deck jobs), counted
  (`reason='no_history'`) — the percentile bar suppresses
  mediocre-relative-to-known-taste, a judgment requiring history; it must not
  silence activation pushes.
- R14. **Silence is not a state.** Every evaluation is counted:
  `sent | suppressed(reason=percentile|fatigue|relaxed|consensus|partner_stale)
  | pass(no_history) | no_candidate`. A `pass(no_history)` evaluation results
  in a send and is recorded as **both** (`sent` with `reason='no_history'`) so
  the >60% suppression watch and the dark-window mix review have one
  unambiguous denominator (evaluations, not sends). A suppressed push still writes its
  inbox row, visually identical to a pushed one — no "you missed a push"
  affordance. Existing caps/prefs/dedup/quiet-hours unchanged.
- R15. Match/response/digest kinds bypass — ratified once (OQ-2), then frozen.
- R16. Push impressions log `surface='push'`; the reader surface-filter sweep
  ships in the same change (LLD §6.1 hard ordering).

### P1-4 — Value blend as governed config (LLD §2.2; HLD D10)
- R17. Versioned per-head rows + active pointer; tuning is an ops change
  under an experiment; rollback = one UPDATE; `vblend_id` stamped per
  impression so replay stays valid across changes.
- R18. Validation: registry heads, |V| ≤ 100, sign-class check; the runtime
  clamp — not a weight-space bound — is the negative-mass protection.
- R19. **Governance:** operator-only activation via the `X-Cron-Secret`
  route; POST carries a required `actor` string persisted with timestamp +
  payload (config-audit row); blend ids append-only and immutable once
  activated; each activation gets a CHANGELOG line. Agents may *propose*
  blends (write inactive ids); only the operator activates.
- R20. **Defaults are tunable parameters, not requirements:** P75, 2000ms
  fast-pass, 14d partner-active, 20-outcome cold-start floor, 300-positive
  head floor are `model_config` seeds, each with a named owner metric on the
  admin report; retuning is a logged ops change — never mid-window.

### Cross-cutting
- R21. `deck.value_model` stays the single serving gate; cold-start users
  (<20 deck-surface outcomes, per the LLD §4.7 gate — no maturation filter on
  the *count*) silently serve composite, counted.
- R22. Full feature gates; flag/config surfaces hit the bright line, never
  express.

## 6. Scope & Phasing

MVP = LLD B9 (v2 + vblend, refit-side; serving unchanged) ∥ B10 (promotion
machinery) → B11 (surface column + reader sweep + push bar dark → enforce).
The honest calendar — **a decision pipeline with a progress meter, not a
date**: counting is ESS-dependent (LLD §8.3: 6–10 calendar weeks for 21
counted nights; R5 checkpoints at wk 8, cap wk 12); worst honest case to the
end of the online window ≈ 4 months. If that is unacceptable, the levers are
label volume (P0-3 join rate, the web echo) and exploration — never the bar.

## 7. Dependencies & Risks

**Dependencies:** P0 exit criteria (labels + trustworthy ledger) precede
counting; B9 needs B2+B5; B10 needs B1+B9; B11 needs B8. F7 exploration +
Thompson stochasticity are **policy invariants** while any learned component
trains on serving logs — turning them off invalidates the replays this
phase's primary metric depends on.

| Risk | Trigger | Response |
|---|---|---|
| ESS never fills | counted <14 at wk 8 / cap wk 12 | R5: not-evaluable verdict; fix estimability; never lower `ess_min` mid-count |
| Underpowered A/B misread as mandate or indictment | any post-hoc north-star claim | Pre-registered R3-style rule; offline verdict is the authority; guardrails decide online |
| Sparse negative head zeroes decks | LLD E14/E15 | Platt guard + clamps + head floors + runtime clamp; composite fallback |
| Propensity drift poisons counting | `untrusted-<date>` markers | Nights don't count; >3 markers/14d ⇒ stop counting, root-cause first |
| Push-bar starvation | segment suppression >60% sustained | Per-segment percentile review; fail-open no_history covers new users |
| Fat-fingered vblend | validation reject / E16 | Write-time validation; activation-only flips; audit row; one-UPDATE rollback |
| Mixed score scales in the push percentile | serving flag flips mid-window | Accepted ≤30d artifact (LLD §4.13) — monitored, not engineered around |

## 8. Rollout & Measurement

1. **Dark:** `train.value_model` on; nightly refit; serving stays composite,
   byte-identical.
2. **Count:** ratify numbers (OQ-1) → pin → window on the admin report ("n of
   21 counted / m elapsed"). Outcome ∈ promote | kill | not-evaluable — no
   fourth state.
3. **Online:** on promote — activate artifact, flip flag, 50% A/B with
   exposure logging, 4-week fixed horizon, pre-registered harm-check rule.
4. **Push bar:** ≥2-week dark count → operator review of suppression mix →
   enforce; per-segment starvation watch.
5. **Rollback inventory:** serving flag off (byte-identical); artifact =
   previous `models.jsonl` entry; vblend = pointer UPDATE. No schema rollback
   exists or is needed.

**Open questions (⛔ blocks the step named):**

| # | Question | Blocks |
|---|---|---|
| OQ-1 ⛔ | Ratify D4 numbers **plus** R5's wk-8 checkpoint / wk-12 cap and the online harm-check rule — one sitting, before counting | P1-1 counting |
| OQ-2 ⛔ | Ratify the D6 bypass set (assumed: match/response/digest), then frozen per Non-Goal 4 | P1-3 enforcement |
| OQ-3 ⛔ | Exact current WAU + swipes/day into the scope block with the MDE arithmetic shown — the power claim must be checkable | online window |
| OQ-4 ⛔ | Confirm operator owns the post-launch V-tuning loop; config-audit row storage (reuse a table or add one) — **blocking P1-4 activation** because R19 makes the audit row a precondition of any activation, and the `actor` field + audit row are an LLD §2.3 route-contract delta (logged) | P1-4 activation |
