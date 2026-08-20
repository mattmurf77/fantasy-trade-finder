# Trade-engine accuracy — re-review of the 2026-08 research corpus + the plan to launch

**Date:** 2026-08-20
**Kind:** review + plan. No engine, flag, config or client line changed by this document.
**Operator brief:** *"Trade suggestions aren't getting much better with every iteration. I have
willing testers that will churn through suggestions, but I need a clear plan for how we actually
get this model in a better spot before I can launch."*

Fresh evidence in this doc comes from a read-only prod pull on 2026-08-20 (79 `bakeoff_runs`,
`deck_impressions ⨝ deck_outcomes`, `trade_pass_reasons`, `league_preferences`,
`member_rankings`), run with the `prod_analytics` safety posture
(`default_transaction_read_only=on`).

---

## Table of Contents
- [Part 1 — Re-review verdict on the existing research](#part-1--re-review-verdict-on-the-existing-research)
- [Part 2 — Why iterations aren't compounding](#part-2--why-iterations-arent-compounding)
- [Part 3 — The plan](#part-3--the-plan)
- [Part 4 — Launch gates](#part-4--launch-gates)
- [Appendix — fresh prod numbers cited above](#appendix--fresh-prod-numbers-cited-above)

---

## Part 1 — Re-review verdict on the existing research

Corpus reviewed: the arm-B audit (consolidated + 7 memos), the knockout waterfall, the
consensus-gate matrix, the matchmaking research index (3 rounds, 11 memos), the bake-off
PLAN/scopes, the matchmaking HANDOVER, and the arm-D PRD trail (D-095/D-096).

### What holds (mechanics verified against code this session)

Every load-bearing mechanical claim I checked is true at `origin/main` today:

| Claim | Verified at |
|---|---|
| Consensus path has no partner-surplus test; `rv − gv < ε`, ε = 0 | `trade_service.py:4987` (per gate-matrix), live `user_gain_epsilon` absent → default 0 |
| R5 takes no opponent argument; hard-kills for contend-side outlooks | `need_gate_ok`, `trade_service.py:1824+`; live `need_gate_min_value = 500` (armed) |
| `outlook_direction_mult` takes no partner argument (dualizing = no-op) | `trade_service.py:2420` |
| User Elo shrunk pre-surplus, partner raw | `_shrink_user_elo` callsite `trade_service.py:4110+` |
| Arm A pinned + golden; arm D dark overlay; roster `(current, challenger, gen_v2)` | `bakeoff_profiles.py`, `bakeoff_runner.arm_roster()` |
| Serving is dark: `bakeoff_serve_interleaved = 0`, only arm `current` stamps | 79/79 `bakeoff_runs.served_arm = 'current'`; `model_arm ∈ {current, NULL}` in prod |
| Live knob values match the audit's assumptions | `model_config`: overpay .25, filler .25/450, surplus floor 60 |

The audit corpus is unusually honest — it refutes its own reviewers where warranted, states
its resolution caveats, and the D-096/D-095 fixes it recommended are now merged (living-memory
still lists all three as unmerged; they are on `origin/main`: `7110af2`, `d755b3b`, `38806e0`).

### What is shaky (trust directionally, not numerically)

1. **Every replay number comes from one league.** 6 boards, 15–36 pairs, league
   `1312140920132497408`. The 96.3% / 63.2% / 88.7% levers are credible mechanism
   demonstrations, not population estimates. Worse: 5 of the 6 boarded members' boards are
   suspiciously uniform (644–646 `member_rankings` rows each) — likely bulk-seeded, so the
   genuine preference signal behind "divergence" is thinner than row counts suggest.
2. **Like rate as the success metric.** D-095 recorded the objection (a two-sided arm loses on
   a one-sided metric) and the operator accepted it with a basis-split mitigation. Fresh data
   sharpens the objection: post-fix, divergence cards like at **5.7%** vs consensus **22.4%**
   (n=35 decided, directional). Like rate may be rewarding *familiar consensus pricing*, not
   trade quality. The metric question is not settled; it is deferred.
3. **The bake-off cannot answer its question as configured.** Dark mode produces zero per-arm
   decision data by construction — now proved in prod. At n≈5 users, only within-deck
   interleaving has any statistical hope, and it was reverted after one day for a deck-shrink
   defect that D-086 has since half-fixed.
4. **The 2.5× consensus-over-divergence quality prior** (HANDOVER §5.1) was flagged as
   contaminated then; fresh data *inverts* it into a ~4× gap the other direction. Neither
   number should drive composition quotas.

### What the corpus missed entirely

1. **The funnel has no bottom.** `deck_outcomes.action = 'propose'` has fired **zero times
   ever**. The send pipe is wired end-to-end (`server.py:14780` logs it on a successful
   Sleeper send; mobile passes `impression_id`). No memo in the corpus mentions this. Every
   optimization target in the system is a proxy for a conversion that has never occurred.
2. **The ordering layer is anti-correlated with liking.** Like rate of decided cards climbs
   monotonically with deck depth: **16.9%** at positions 0–4 → **50%+** past position 25.
   Survivorship inflates the tail, but the corpus audited generation exhaustively and never
   once checked whether the serving order — seven re-ranker layers deep — correlates with
   outcomes. It anti-correlates.
3. **Input supply.** The divergence/moat strategy presumes both managers have boards. One
   production league does. And 10 of 12 declared outlooks are contend-side — the exact
   population R5 hard-kills laterals for and `outlook_direction_mult` barely steers.
4. **What users say when they pass.** 208 decline reasons existed unanalyzed: 40%
   `value_giving` ("giving up too much") on a path where the engine guarantees the user never
   pays by consensus — i.e., the card's stated value and the user's own board disagree, and
   the card wins the argument on screen. 33% `fit_outlook` against a steering lever that is
   provably partner-blind.

---

## Part 2 — Why iterations aren't compounding

Not because the engine changes are bad — several are measured improvements. Because:

1. **No stable target.** Like rate on served cards, measured across contaminated windows
   (D-091 phantom picks, 42% of one memo's rows), on 5 users, while the metric itself is
   disputed.
2. **No change control.** Five knob waves + two repricing waves + a gate wave landed inside
   the same 5-day window the measurements were taken in. `model_config` has no `updated_at`,
   so even reconstructing *when* a knob moved is impossible. Any effect is unattributable.
3. **The layer being tuned isn't the layer failing.** Generation gets audited; ordering and
   presentation — where the position curve and both top decline reasons point — ship unmeasured.

The plan below is therefore a *measurement* plan first and an engine plan second.

---

## Part 3 — The plan

### Phase 0 — Fix the scoreboard (this week, no engine changes)

| # | Action | Why |
|---|---|---|
| 0.1 | Declare the north star: **suggested trades actually sent** (`propose`), with like-on-viewed as the leading proxy and decline-reason mix as the diagnostic. | Everything else is a proxy; say so once, in writing. |
| 0.2 | Add `model_config.updated_at` + a tiny knob-change log table. | Restores attributability of every future comparison. |
| 0.3 | Persist `fairness_threshold` on **all** decks and persist targetedness on `deck_impressions`. | Both named in HANDOVER §5; both still open; both confound every read. |
| 0.4 | **Change-control rule: one engine-affecting change per measurement window** (a window = one tester week). Ordering/presentation changes may ship in parallel *only* because arms are attributed per card. | The single biggest reason iterations don't compound. |
| 0.5 | Correct stale living-memory (D-096 / balanced-string / arm D are merged). | Sessions keep re-planning shipped work. |

### Phase 1 — Serve what's already built (week 1–2)

| # | Action | Why |
|---|---|---|
| 1.1 | **Re-light `bakeoff_serve_interleaved = 1`** with the lane quota disabled (`bakeoff_group_value_slots = bakeoff_group_size`, or `bakeoff_group_size = 0`) so the outlook-lane holes can't shrink the deck again. Scope to tester leagues. | Within-deck interleaving is the only design that produces per-arm decisions at this n. Arm D already out-generates arm B in the boarded league (18.3 vs 15.0 cards/run, 2.0s vs 2.6s, fewer forfeits) and targets exactly the complaints users file. |
| 1.2 | **Read the ghost holdout.** 273 of 1,371 bake-off-era impressions are ghosts; the counterfactual arm has been running since telemetry shipped and nobody has looked. | Free measurement of the ordering stack. |
| 1.3 | **Flip `trade.outlook_direction` off** (operator already inclined). This is experiment #1 under the change-control rule: the readout is `fit_outlook` share of pass reasons (33% today) and like rate. One line, deploy-free revert, clients degrade cleanly (`OutlookBiasReceipt` renders null). | If the share doesn't move, the complaint is about *which trades exist*, not how they're ranked — which redirects the fix to generation/inputs. |
| 1.4 | Triage the ordering stack: log each re-ranker's rank delta per card (cheap, additive), and compare interleaved decks (re-rankers bypassed) against normal decks on like-on-viewed. | The position curve says the seven-layer stack may be inverted. Bypass already exists (`bypass_rerankers`). |

### Phase 2 — The tester protocol (weeks 2–5)

**Power honesty:** at a ~20% base like rate, seeing a 10pp lift needs ≈300 decided cards per
arm (≈130 for 15pp). Recent peak was ~200 decisions across 4 days from 5 users. So: **10
testers × ~40 decided cards/week ≈ 400/week → one clean two-arm comparison per week**, faster
for large effects because interleaving is within-subject.

The weekly loop:

1. **Monday** — ship at most one engine-affecting change (Phase 3 queue), stamped in the knob log.
2. **All week** — testers churn decks. Tester asks: decide (not just view) ≥40 cards, always
   pick a decline reason, and **attempt at least one real send** when a card is genuinely
   close — the propose funnel has never fired and must be exercised.
3. **Friday** — standard readout: like-on-viewed by `model_arm` × `basis`, decline-reason mix,
   position curve, proposes. ~30 minutes with the queries from this session's probe scripts.

**Tester onboarding requirements** (this is input supply, not busywork):
- Build a real board: ≥100 matchup votes before the first deck.
- Declare an outlook via Team Review (next build renders it) — inferred outlooks are a known
  wrong-input source, and 10/12 current declared outlooks being contend-side means R5 and the
  outlook machinery are firing against nearly everyone.
- At least 2 leagues where **3+ members** board up — divergence currently has exactly one
  league of supply, and every replay conclusion in the corpus is captive to it.

### Phase 3 — Engine queue (one per week, in evidence order)

1. **`user_elo_shrink = 0`** — the measured 96.3→63.2% lever; already arm D's P2, so
   interleaving reads it before committing it to arm B.
2. **Soft/dual R5** — second measured lever (→88.7%; 73.3% combined). The waterfall shows R5
   uniquely killing dual-need trades; arm C refuses to implement it; 10/12 users are in its
   kill demographic.
3. **Tier-ladder compression on consensus** (arm D's P1 values) — the stakes fix: fairness
   can't see scale and `tier_mult` (4.57× span) selects for it.
4. **Own-board value on the card** — attacks the 40% `value_giving` complaint directly: the
   engine *holds* the user's board; the card currently argues consensus at them. Presentation
   change, no generation risk.
5. **Calibrate the three uncalibrated floors** (`min_side_surplus_marginal` 60,
   `filler_min_frac` 0.25, `asset_floor_abs` 450) against tester decisions — the waterfall's
   #1 and #2 unique excluders, never tuned against anything.
6. **Partner-need term** (structural; needs `member_rankings` confidence counts that don't
   exist yet) — the recurring endpoint of every audit thread; not a launch blocker.

### Explicit strategy call this plan forces

**Launch is consensus-first.** Real traffic arrives boardless; the divergence moat is real but
it is a *retention* feature that turns on as leagues board up, not the launch surface. That
means launch quality = consensus-path quality (levers 1–4) + ordering + presentation — and the
one-sidedness findings on the 84.5% path are the launch-critical fixes, not the divergence
tuning.

---

## Part 4 — Launch gates

| Gate | Bar | Today |
|---|---|---|
| G1 — funnel proven | ≥3 real trades sent through the app by ≥2 testers | 0 ever |
| G2 — top-of-deck quality | like-on-viewed for positions 0–4 ≥ 30%, sustained 2 weeks | ~17% |
| G3 — value complaint receding | `value_giving` ≤ 25% of pass reasons | 40% |
| G4 — performance | p95 job time within `_JOB_HARD_TIMEOUT` with bake-off serving on | unmeasured (Phase-4 question, still open) |
| G5 — onboarding produces inputs | a new tester reaches a scored board + declared outlook inside first session | Team Review not yet in a build |

---

## Appendix — fresh prod numbers cited above

2026-08-20 read-only pull:

- **Arms all-time:** `(none)` 7,740 impressions / 95 likes / 289 passes; `current` 1,371 / 18 / 90. No other arm value has ever been stamped. `propose` = 0 all-time.
- **Bake-off:** 79 runs (53 on 8/19, 26 on 8/20, 6 leagues). Boarded league (61 runs): current 15.0 mean cards / 2,593ms median / 5.2 forfeits; challenger 18.3 / 2,010ms / 3.3; gen_v2 8.4 / 218ms / 2.5. Other leagues: gen_v2 zero cards in 12 of 18 runs (supply, per D-087).
- **Position curve** (decided cards, since 8/16): 0–4 16.9% like → 25–29 50.0% → 30+ 61.5%.
- **Pass reasons** (n=208): value_giving 84 · fit_outlook 68 · other_text 21 · fit_new_weakness 14 · value_getting 9 · rest ≤3 each.
- **Basis since 8/19:** consensus 1,248 imp / 22 like / 76 pass; divergence 264 / 2 / 33.
- **Ghosts:** 273 of 1,371 bake-off-era impressions (`is_ghost = 1`).
- **Outlooks declared:** contender 6 · championship 4 · not_sure 1 · rebuilder 1.
- **Board supply:** boarded members per league: 6, 2, 1, 1, 1, 1, 1; the five non-operator boards in the 6-board league hold a uniform 644–646 rows each.
- **Group fill (79 runs):** `current_divergence` filled 153 value slots against 254 short and 49 outlook against 351 short — the worst-filling group; outlook lane overall fills ~1/3 of its quota.
- **Arm C funnel (51 diagnostic runs):** 2,098,200 considered → 1,956,175 killed at composition (93.2%) → 1,677 survivors → 436 emitted.
