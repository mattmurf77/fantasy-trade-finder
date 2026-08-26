# Critique of PLAN-v2-draft-A — from the risk-and-measurement-first draft (B)

**Date:** 2026-08-20
**Reviews:** [PLAN-v2-draft-A.md](PLAN-v2-draft-A.md) against [PLAN-v2-draft-B.md](PLAN-v2-draft-B.md)
**Posture:** this is a critique for reconciliation, not a defense of B's every line. Where A
is right, it says so; §7 lists what B now adopts.

---

## 0. Corrections to B's own predictions first

B's summary predicted A would re-light via the quota patch
(`bakeoff_group_value_slots = bakeoff_group_size`) with Friday-only monitoring. **Wrong on
the first half:** A chose `bakeoff_group_size = 0`, for the same structural reason B did
(removes the whole failure class, not the lane half), and A owes an ADR saying so
(A §7). The two drafts also independently converged on: the K3-last ordering (C6),
`fit_r5_mode` default-kill pre-wire (C2), module-import binding (T1), raw-board lens
provenance (T3), `_DEFAULT_CFG` registration + same-commit disposition sentences (T4),
the tanh comment fix with a pinned value table (C7a), the consensus-fairness tie-break
(C7c), and knob-log-before-first-flip. The disagreement space is real but narrower than
either draft's framing implied: **arm count, the dark soak, tripwire cadence, window
alignment, and verdict machinery.**

---

## 1. Arm count: A's 3-then-4-arm roster, and the within-subject question, honestly

**Does per-card team-draft interleaving change B's k=2 conclusion?** Partly — the
arithmetic, stated plainly:

1. The cited ≈300/arm (10pp) and ≈130/arm (15pp) figures are independent-Bernoulli
   two-proportion numbers. Tester-level heterogeneity (some testers like 5% of cards,
   some 40%) would normally *inflate* those n's by a cluster design effect. Within-deck
   interleaving balances every tester across every arm, which **neutralizes the tester
   cluster** — so interleaving is what makes ≈300 approximately *achievable*, not a
   further discount on it. B's table already assumed this; it was not conservative slack.
2. The residual paired gain is the shared deck/session component (a tester's mood on one
   deck). A paired analysis removes it: `n_eff ≈ n·(1−ρ_deck)`. At a generous
   ρ_deck = 0.15, 300 → ≈255 and 130 → ≈110. A **~15% haircut, not a 2× one.**
3. **A's week-1 roster (B/C/D) costs less than B's table implied**, because the table
   assumed even splits and arm C self-starves: zero cards in 12 of 18 non-boarded-league
   runs means boardless decks split ≈ two ways anyway. Realized supply ≈ 170–185
   decided/wk for B and D each → a 10pp B-vs-D read in ~1.5 weeks. On week 1, the two
   drafts differ far less than B's rhetoric suggested. Concession registered (§7).
4. **A's steady state (B/C/D/fit) is where the math breaks.** Boardless decks split
   ≈ three ways (B/D/fit; C absent), the boarded league four ways → fit ≈ 120–130
   decided/wk. Apply the bucket restriction (co-primary counts only `both_high`+`mixed`,
   planning f ≈ 0.5): **≈ 60–65 co-primary decisions/wk.** Against the paired-adjusted
   bars: 15pp needs ≈ 110 → ~1.8 wk (fine); **10pp needs ≈ 255 → ~4 weeks**, and ~5 at
   f = 0.4 — past the 3-week contamination ceiling this repo's own knob-wave history
   justifies. So A's four-arm design can only read effects of ~15pp and up on its own
   chosen co-primary. Nothing in A states this; SC6 implies the opposite (see §5.1).

**Verdict:** within-subject pairing softens B's k=2 argument by ~15%, and C's
self-starvation softens the week-1 half almost entirely — but it does **not** rescue the
four-arm fit round. Held position: during R1, serve exactly two arms (B and fit).

And two non-power reasons C should still not serve, unanswered by A's "forfeits are data,
not a reason to bench it" (A §4 Stage 1): (a) C's decided-card sample is league-captive —
essentially all of it comes from the one boarded league, so its like-rate is confounded
with league and unreadable at any n it will actually reach; (b) in that same boarded
league — the only league with divergence supply, i.e. the most informative league in the
program — C's slots dilute B's and D's n exactly where the divergence comparison lives.
C's forfeit *diagnostics* are indeed data, and they keep accruing in dark generation; its
*served slots* buy nothing readable.

## 2. The no-dark-soak position (A §4 Stage 2, R3)

A's defense: fixture dry run + 5,000 cap + 60s timeout + operator same-hour canary +
one-knob rollback; a dark soak "would force re-darkening all arms — strictly worse."

**The dichotomy is false.** Re-darkening is only forced *absent a serve-bit*. B's F5b
(`bakeoff_serve_fit`, 0.5 day: fit generates and logs, excluded from draft participants)
gives 3 days of real-league prod diagnostics at **zero** decision-stream cost while B vs D
keeps serving. R3 argues against a cost F5b removes; A never considers the ticket.

**What concretely escapes A's canary:** the operator is in the 6-board league; the dry-run
replay boards are from that *same* league; the fixture suite pins expectations rather than
discovering distributions. So the one thing no pre-serving evidence in A's plan ever
observes is **fit's behavior on a real boardless league** — which is most tester leagues
and, per the review's own launch argument (C1/PRD lens-3 case), the population that
matters. Specifically: every unranked-pair card mirrors to aggregate ≈ 100 (C7c), so a
boardless deck's entire ordering hangs on the consensus-fairness tie-break; a subtle
tie-break or L3-scaling defect makes the boardless tester's deck top effectively
arbitrary. A's first detection of that is tester behavior in the Friday readout — days of
burned goodwill and a contaminated window. The dark soak sees it in
`arms_json[fit].diagnostics` (bucket mix, `median_aggregate`, top-quartile junk/pick
shares, per-league ms) before any tester does.

**Honest likelihood:** A's fixture suite is good and the 5,000 cap makes a timeout
unlikely; probability of a *serious* escape is maybe 15–25%. But the downside is a burned
week of a 7-week program plus tester trust — and with ~10 testers, trust is the program's
scarcest non-renewable input: the 400 decided/wk supply figure is an assumption about
willing testers, not a law. Expected cost of the escape exceeds the cost of the soak
(0.5d + 3 calendar days, mostly parallel with R0's second week). Held position, with the
mechanism (F5b) that dissolves A's stated objection.

## 3. Monitoring: A verifies health at start; B detects degradation later

Did B under-read A? Partially. Credit where due: A's SC2 bar (median ≥ 24) is **stricter**
than B's ≥ 20 target; A's S1b regression test (`test_zero_card_arm_deck_still_fills`)
structurally *prevents* the exact 08-18 recurrence rather than merely detecting it; SC1
(first non-`current` decision within 3 days) is a liveness criterion B simply lacked. All
three are adopted (§7).

But the monitoring is genuinely thinner where it matters — **cadence and triggers after
day 3:**

| Failure | A's detection | B's tripwire |
|---|---|---|
| Deck degrades on day 9 (supply shift, roster change side-effect) | nothing between the day-3 verification and Friday readouts | daily deck-median query; < 20 investigate; < 15 ×2 days → named one-knob revert same day |
| Position imbalance (draft bug, not re-ranker) | not monitored | per-arm mean `card_index`, Δ > 2 → window suspect |
| Arm starved by timeout mid-round | SC7 is a criterion, no cadence attached | daily p95 + per-arm error/forfeit counts, numeric bars |
| Mid-window knob drift | M1 logs it; **no stated consequence** | Friday `config_json` diff → **window discarded, not caveated** |
| Tester supply collapse | none | < 250 decided/wk → extend round once, tell operator |
| Guardrail latency | SC9 needs **2 consecutive Friday readouts** — up to 2 weeks of exposure before it can trip | pooled < 5% for one week → pause and inspect |

The pattern: A's numbers answer "did it come up healthy?"; a 7-week program also needs
"will we notice when it degrades?" The merged plan should take A's verification set
*plus* B's daily tripwires — they are 30 lines of SQL, not a workstream.

## 4. Ordering and parallelism: mostly right, two real attribution breaks

Concede the big one: A's PR structure is correct and B's strictly serial W0 framing was
weaker. PR-M → PR-S ∥ PR-F1..F3 *is* measurement-first where it counts (the log precedes
the first flip; flips are config-only and logged via `set_knob.py`), and holding the rail
hostage to the fit build would be pure calendar loss. Adopted wholesale.

Two places A's ordering does break attribution, concretely:

1. **Stage 2 is untethered from window boundaries.** A rosters fit "after PR-F3 + green
   dry run" with a same-hour canary — i.e., whenever a PR merges, possibly Wednesday.
   Rostering a served arm is an engine-affecting change; landing it mid-week splits that
   week's data into pre/post segments, each below useful n, in a program where fit's
   co-primary already needs multi-week accumulation. The fix costs nothing: flips land on
   Monday boundaries. A already has the Monday rule (M3) — it just exempts its own stage
   flips from it.
2. **Stage 3 lets the control arm mutate weekly while fit is being read.** A §4 Stage 3
   explicitly allows one accuracy-queue engine change per Monday (`user_elo_shrink`, soft
   R5 — "arm-B levers outside this plan") during steady-state serving. Per-card
   attribution survives, but the comparison "fit vs B" then spans a different B each week
   — and per §1.4, fit's 10pp co-primary needs ~4 weeks pooled at A's arm count. **A
   readout that cannot pool weeks, in a design that needs pooling, is structurally unable
   to reach its own verdict.** B's rule — the control arm is frozen for the duration of a
   round; the queue consumes the between-rounds slots — is not a philosophy preference,
   it is what makes A's own SC-machinery able to conclude anything.

## 5. Coverage-table and criteria review — factual errors and hand-waves

1. **SC6 conflates supply with power (factual misuse).** "≥300 decided cards *pooled* in a
   tester week … (accuracy PLAN Phase 2 power math)" — the cited ≈300 is **per arm**, not
   pooled. 300 pooled across 3–4 arms is 75–100/arm: enough for nothing below ~18pp. As
   written, SC6 invites calling a single 300-decided week "powered." The supply arithmetic
   (10 × 40) and the per-arm n requirement are different numbers and the criterion quotes
   one while gesturing at the other.
2. **SC9's baseline is cross-regime (invalid comparison).** It compares interleaved pooled
   like-rate against the *dark* arm-B baseline — but dark serving runs the full re-ranker
   stack and interleaved serving bypasses it (`bypass_rerankers()`, by design). The two
   regimes differ by the entire ordering layer, which the accuracy plan's own
   position-curve finding (16.9% → 50%+ by depth) says is a large effect of unknown sign
   at top-of-deck. SC9 can trip, or pass, on the bypass alone. A within-regime guardrail
   (week-over-week within interleaved serving, or arm-B-cards-within-interleave vs
   themselves) is the valid form.
3. **R4 defers cross-arm bucket parity — and flips the bias direction (hand-wave with a
   hole).** C3's problem was pooled like-rate biased *against* fit. A's v1 readout
   compares fit's like-rate *on its best buckets* against arm B's un-bucketed rate —
   biased *for* fit, the same apples-to-oranges error mirrored. "Nothing is lost by
   deferring" is wrong twice: (a) every readout until M2b is verdict-invalid, and M2b is
   the verdict machinery; (b) offline re-scoring of arm-B cards is not the clean follow-up
   claimed — the lenses need boards *as of serving time*, and boards move (the
   `board_updated_at` capture exists precisely because of that drift). Stamping
   `fit_diag` at generation time (B's M3, 0.5d) is exact, cheap, and testable-inert;
   the offline variant is neither exact nor specified.
4. **No verdict machinery at all.** A has nine success criteria for the *machinery*
   (serving lit, diagnostics populated, knobs logged) and none for the *question*: no
   pre-registered per-arm n bar, no effect-size threshold, no promote/iterate/kill rules
   — "answered by SC6-grade readouts on C3's co-primaries, not by any single week" is the
   hand-wave where the decision should be. Combined with §4.2 (mutating control) and §1.4
   (four-arm power), A's plan can serve four arms indefinitely without ever being *forced*
   to conclude. B's §2.5 rules should transfer verbatim.
5. Smaller notes: S1a's "check `trade.bakeoff` scope, don't assume" instinct is right and
   more careful than B's flat cut — but the conditional allowlist build is dead weight
   (the app is TestFlight-only; global-on *is* tester-only today; the allowlist becomes
   real work only when a public release date exists). C7b via grep-assertion + code-walk
   is acceptable, though B's sabotage-style `test_draft_rank_only` (double one arm's
   composite scale, assert identical draft) proves behavior rather than text, per
   HANDOVER trap 8's own standard — prefer it. A's T4 mechanics (`_PINNED_KNOBS` +
   `scope-phase2.md`, same commit) are more concrete than B's and should be the merged
   wording.

---

## 7. Concessions

### Accepted from A into the merged plan

1. **Track parallelism and the 5-PR structure** (PR-M → PR-S ∥ PR-F1..F3; flips config-only,
   post-merge, logged) — B's serial W0 loses calendar for no risk reduction.
2. **Week-1 re-light before fit exists** — shared position, but concede A's implicit point
   that arm C's presence in week 1 costs little *power* (C self-starves; §1.3).
3. **SC1** — first non-`current` decision within 3 days; a liveness criterion B lacked.
4. **SC2 bar at median ≥ 24** — stricter than B's ≥ 20; keep B's < 15 ×2-days as the revert floor.
5. **S1b regression test** (`test_zero_card_arm_deck_still_fills`) — structural prevention
   of the 08-18 shrink beats B's tripwire-only posture; keep both.
6. **`scripts/set_knob.py`** as the blessed, source-attributing write path, plus R5's honest
   raw-SQL-bypass caveat — better specified than B's bare route hook.
7. **`fit_max_packages_per_pair = 5,000` at first roster** — a concrete conservative number
   now beats B's "dry-run-derived" placeholder.
8. **`fit_junk_floor` pre-built default-off in F4** — B deferred building the knob itself,
   which would have meant a deploy mid-window; R6's reasoning is correct.
9. **T4 mechanics as A words them** (`_PINNED_KNOBS` + disposition sentence in
   `scope-phase2.md`, same commit, D-095 precedent wording).
10. **M3 tester-protocol as a committed doc** (`tester-protocol.md` + runbook section)
    rather than B's uncommitted brief.
11. **The operator same-hour canary ritual at every stage flip** — adopted as an addition
    to the dark soak, not a replacement.

### Still rejected, one sentence each

1. **Serving arm C** — its decided sample is league-captive and unreadable at any n it
   will reach, and its slots dilute B/D exactly in the one divergence-supply league;
   bench it with B's written re-entry condition (≥2 leagues with 3+ boards).
2. **Four served arms during the fit round** — ≈60–65 bucketed co-primary decisions/week
   puts a 10pp read at ~4–5 weeks even with the paired-analysis credit, past the 3-week
   contamination ceiling; k = 2 for R1 (D benched after its round).
3. **No prod dark soak for fit** — R3's "forces re-darkening all arms" is a false
   dichotomy dissolved by the 0.5-day `bakeoff_serve_fit` bit, and the escaping failure
   class (boardless-league ordering, invisible to a boarded-league canary and a
   same-league fixture) lands on testers days before A's first detection.
4. **Stage flips untethered from window boundaries** — a mid-week roster change splits a
   week's data below useful n; every flip lands on a Monday, per A's own M3 rule.
5. **Weekly arm-B queue changes during fit's readout** — a control that mutates weekly
   makes multi-week pooling impossible in a design that needs it; freeze B for the round,
   queue consumes between-round slots.
6. **Deferring cross-arm bucket parity (R4)** — the v1 readout as specced is biased *for*
   fit (best-buckets vs everything), and offline re-scoring is neither exact (boards
   drift) nor specified; generation-time `fit_diag` stamping is 0.5d and testably inert.
7. **SC9 as written** — a cross-regime guardrail (interleaved, re-rankers bypassed, vs a
   dark baseline with re-rankers on) measures the ordering stack, not the arms; make it
   within-regime.
8. **Absent verdict machinery** — adopt B §2.5's pre-registered promote/iterate/kill rules
   and per-arm n bars, or the program can serve forever without concluding.

*Critique ends.*
