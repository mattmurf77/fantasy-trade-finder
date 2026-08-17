# PRD — Trade presentment rules (G6: #304, #336, #339, #340, #341)

> Author-round deliverable, 2026-08-16 wave. Requirements bind the build
> agents; interfaces in [lld-delta.md](lld-delta.md), architecture rationale
> in [hld-delta.md](hld-delta.md), scope block in [scope.md](scope.md).
> QA regime: D-056 (no Maestro/simulator — pytest + code-walk proof +
> operator TestFlight checklist).

**Plainly:** stop serving trades that are lopsided beyond what any human
would accept, that wreck positional balance, that dump a pick to paper over
the gap, that offer a contender a player worse than their current starter,
or that the user has already liked or matched.

## 1. Requirements

Each requirement maps to ≥1 feedback item and ≥1 test (§3).

| ID | Requirement | Item(s) | Tests |
|---|---|---|---|
| **R-1** | A package whose raw-consensus gap is ≥ `max_overpay_min_value` (500) AND ≥ `max_overpay_frac` (0.25) of the larger side is never served — **either side overpaying**, and **independent of `fairness_threshold`** (the client fairness toggle cannot relax it). | #340 | U-R1-*, DB-2, TF-1 |
| **R-2** | For each position in {QB, RB, WR, TE}, the signed net `count(receive at P) − count(give at P)` — **one quantity per position, not a per-side count** — must satisfy `|net_P| ≤ pos_net_cap` (1); `PICK` pseudo-assets and positions outside the four (K/DEF/IDP) are uncounted by design. 2RB→2RB (net 0) passes. | #341 | U-R2-*, DB-2, TF-2 |
| **R-3** | For a gap ≥ `pick_gap_min_value` (300), a package is never served when a pick on the heavier side sits **inside the two-sided band** `pick_gap_frac × gap ≤ pick ≤ gap / pick_gap_frac` (0.8) — the pick *is* the gap. A pick far larger than the gap (centerpiece consolidation — the operator's own stud-scaled style) passes. | #339 | U-R3-*, TF-5 |
| **R-4** | A trade whose (give, receive) sets match one of the user's un-retracted awaiting likes (**no time window**) or a `pending`/`accepted` match in this league is never served — organic deck, streaming snapshots, relaxed pass, **and likes-you injection** alike. `declined` matches and retracted likes may regenerate. The exclusion set is overwrite-per-call, league-scoped (lld §4). | #336 | U-R4-*, TF-4 |
| **R-5** | **Untargeted discovery decks only** (R-5b). For `championship`/`contender` windows, a card whose primary received player (value ≥ `need_gate_min_value`) neither fills a starting hole nor strictly upgrades the worst starter at its position **on the post-give roster (`roster − give_ids`)** is never served; `not_sure` kills only on surplus positions; `rebuilder`/`jets`/unresolved windows are exempt. Declared window beats inferred. | #304 | U-R5-*, DB-2, TF-3 |
| **R-5b** | R-5 is bypassed for every **targeted** job — `pinned_give`, `pinned_receive`, `opponent_user_id`, or explicit `acquire_positions` — via a flag **derived server-side in `_run_trade_job` from job fields, never client-passable** (lld §3). R-1/R-2/R-3/R-4 apply to targeted and untargeted jobs alike. (Orchestrator arbitration, final.) | #304 × G4 #330 | U-R5-B*, U-R10-1 |
| **R-6** | R-1/R-2/R-3/R-5 run **inside** every generator (v3, v2, consensus) at construction time so killed candidates are refilled from the enumeration, and are re-validated on every sweetened combo. No post-hoc deck filtering. | #304, #339–341 | U-R6-*, CW-1 |
| **R-7** | The #189 relaxed pass never relaxes R-1/R-2/R-3/R-5 (documented in the never-relaxed list alongside #108). | all | U-R7-1, CW-1 |
| **R-8** | `trade.presentment_rules` OFF ⇒ byte-identical decks to today; each rule's knob at its disable value ⇒ that rule alone is byte-identically off. | all | U-R8-*, DB-1 |
| **R-9** | Per-job per-rule kill counters are logged on **every flag-ON job** (the call site is inside the `trade.presentment_rules` check, `server.py:5538` — flag OFF ⇒ no line at all, which is what R-8 byte-identity requires); a WARNING with rule attribution fires when a post-rule deck has <5 cards despite >15 pre-rule survivors. | all | U-R9-1 |
| **R-10** | **No API/payload change**: no new request params; the `trade_card_to_dict` **key-set** is identical flag-ON vs flag-OFF (`server.py:9727`) — the rules only remove candidates *before* the serializer, so no enum vocabulary changes either, but the automated pin is the key-set (U-R10-1); the enum half rests on that construction argument, not on an assertion. This is G4's contract guarantee. | contract | U-R10-1 |
| **R-11** | The D-055 bars hold flag-ON: insult rate (|Δ| ≥ 500) < 3%, empty-deck < 5%, on a deck-eval re-run over the same 9 production leagues. | all | DB-2, DB-3 |
| **R-12** | **Deferred-tuning task (build phase, explicit):** #339's `pick_gap_frac`/`pick_gap_min_value` defaults are unmeasured (0/540 corpus cards carry a pick). Before ship: run `scripts/deck_eval.py` against ≥1 pick-synced league with `trade.picks_in_pool` active, record pick-card kill rate, and set/confirm the knobs from that replay. If no pick-league replay is possible this wave, ship at defaults with the knob named as the tuning lever and a NEXT.md follow-up — not silently. | #339 | DB-4 |
| **R-13** | Likes-you injection is exempt from R-1/R-2/R-3/R-5 (Q21); the D-055 `likes_you_min_user_delta` floor remains its only quality gate; R-4 dedup **does** apply to it (Q-G6-1). | #336 + Q21 | U-R4-4, U-R13-1 |

## 2. Baseline kill-rate expectations (two-sided)

Corpus: `feedback-workspace/deck-eval/deck_eval_20260815T220047Z.json`
(gitignored workspace, present on the operator's machine, 478,439 bytes,
2026-08-15) — the D-055 gate run: 108 first-run decks, 9 production leagues,
540 first-5 cards, 474 organic. Measured by the Planner via predicate replay;
the build phase re-derives these with exact predicates (deck-eval counters,
DB-2) — **both bounds bind: a rule killing ~0% is as suspect as one killing
2× baseline** (2026-08-10 lesson: an unmeasured threshold that never fires
is a silent no-op, one that over-fires is a deck-wrecker).

| Rule | Measured baseline (organic first-5) | Acceptance band flag-ON replay |
|---|---|---|
| R-1 #340 | 8.9% (42/474) | **4% – 16%** |
| R-2 #341 | 7.8% (37/474) | **3% – 14%** (multi-asset shapes only; 420/540 corpus cards are 1-for-1 and must pass) |
| R-3 #339 | unmeasured (0 pick cards) | on the R-12 pick-league replay: **> 0% and ≤ 15% of pick-carrying cards**; on this corpus: exactly 0 |
| R-4 #336 | n/a (first-run sims have no like/match history) | unit + TF only; replay expectation: 0 kills on history-free corpus (any kill = key bug) |
| R-5 #304 (proxy) | 5.3% overall; 14.8% contender decks; 0% rebuilder | overall **2% – 10%**; contender **7% – 25%**; rebuilder **exactly 0%** (any rebuilder kill = window bug) |
| Combined R1∪R2∪R5 | 18.4% (87/474) | **10% – 25%** |
| Insult coverage | 8/8 D-055 insult cards dead | **8/8 — hard floor** |
| Worst-case empty-deck | 4.6% (5/108, pessimistic: first-5 = whole deck) | **< 5%** post-refill (D-055 bar) |

Known baseline limitations, carried from the plan and binding on DB-2's
interpretation: L1 first-5-only (deck-wide rates likely lower), L2 R-5
measured by `need_fit < 0.45` proxy (build phase adds exact counters), L3
no pick cards (R-12).

**Band-miss arbitration (round-1 N8):** a DB-2 band miss — either side —
is **stop-and-report to the operator**, never silent knob-tuning until the
replay fits. One expected exception, pre-declared: the R-5 bands are
proxy-derived (L2), so the first exact-counter replay may legitimately need
a band re-derivation — that is a report-and-re-ratify event (operator
signs the new band), not a failure. Bands changed after the boundary
updates in this round (post-give incumbent, targeted bypass) shrink R-5's
kill population; if the exact-counter replay lands below the 2% floor, the
same re-ratify path applies with the reason stated.

## 3. Test plan (D-056)

### 3.1 Unit — `backend/tests/test_presentment_rules.py`

Every behavioral test lands only after being **proven to fail on a named
sabotage** (invert the predicate, zero the knob, or skip the hook in a
fixture override, and watch the test catch it). Sabotages are listed per
test in the file's docstring.

- **U-R1-1..5:** opponent-overpay killed; user-overpay killed; gap 499 @ 30%
  passes (floor); gap ≥500 @ 24% passes (frac boundary); `fairness_threshold
  = 0.5` (toggle OFF) still kills. Sabotage: replace `max(g,r)` with
  `min(g,r)`.
- **U-R1-6:** fit-premium card at exactly 300 raw loss survives.
- **U-R2-1..4:** 2RB→2WR killed; 2RB→1RB+1WR passes; **2 picks + RB → 1 WR
  passes** (picks uncounted — corrected 2026-08-16 by the orchestrator: the
  earlier "pick+RB→2WR passes" gloss contradicted the R-2 formula, which
  kills that shape on net WR +2; the formula binds, and pick+RB→2WR KILLS,
  pinned as an explicit test); `pos_net_cap = 0` disables. Sabotage: count
  `PICK` as a position (net_PICK = −2 on the two-pick shape → RED).
- **U-R2-5 / U-R6-2:** a sweetener that creates a ±2 net is caught by the
  re-validation. Sabotage: drop `presentment_ok_fn` from `_try_sweeten`.
- **U-R3-1..6:** pick inside the band on the heavier side killed (gap 3,000,
  pick 3,000); same pick on lighter side passes; sub-300 gap passes;
  `pick_gap_frac = 0` disables; **large pick, small gap passes** (gap 300,
  pick 3,000 — the B1 centerpiece-consolidation case the round-1 suite would
  have green-lit); pick exactly at each band edge. Sabotages (round-1 N6 —
  this block previously had none): evaluate the lighter side's picks instead
  of H; drop the band's upper bound (must be caught by U-R3-5).
- **U-R5-1..8:** the Loveland fixture (TE-primary behind rostered starter,
  contender → killed; identical card, rebuilder → served); not_sure without
  surplus → served; not_sure with surplus → killed; hole-filling receive
  passes; strict starter upgrade passes; sub-500 primary passes;
  pick-primary exempt; declared window beats inferred. Sabotage: swap
  `position_needs`/`position_surplus`.
- **U-R5-9:** R-5 fires with `trade.fit_premium` OFF (the `_user_needs`
  coupling in lld §3 — regression against silent flag dependence).
- **U-R5-10:** contender tier-down at a stacked position survives — the
  incumbent is **in the give side** (give McBride + …, receive Loveland +
  2nd) and the card is served, because `user_P` is computed on
  `roster − give_ids` (B2). Sabotage: compute `user_P` from the full
  pre-trade roster.
- **U-R5-B1..B5 (bypass branches, R-5b):** an R-5-failing card is served
  when the job has (B1) `pinned_give`, (B2) `pinned_receive`, (B3)
  `opponent_user_id`, (B4) explicit `acquire_positions`; (B5) the same card
  is killed on a fully untargeted job, and `trade_away_positions` alone
  does **not** bypass. Sabotage: derive the bypass from a request-body
  field.
- **U-R4-1..6:** 8-day-old awaiting like excluded (**the root-cause
  regression test** — must fail on today's `since_days=7` behavior);
  `pending` and `accepted` matches excluded in both `user_a` and `user_b`
  orientations; `declined` regenerates; retracted regenerates; exclusion
  visible in a streaming snapshot. Sabotage: reintroduce `since_days=7`
  into the exclusion query.
- **U-R4-4 / U-R13-1:** likes-you injector refuses an already-matched
  mirror; a quality-rule-violating (R-1-shaped) like above the D-055 floor
  is still injected (carve-out proof).
- **U-R4-7:** two-league sequence on one TradeService instance — league A's
  exclusion set never filters league B's job, and a `None` kwarg clears the
  stored set (round-1 N3). Sabotage: accumulate instead of overwrite.
- **U-R7-1:** targeted job whose only candidates violate R-1 comes back
  empty from the relaxed pass (not R-1-relaxed).
- **U-R8-1..2:** flag OFF ⇒ identical card list to a pre-change golden run
  (`test_user_gain_gate.py` flag-flip pattern); each knob at disable ⇒ that
  rule's fixtures pass through.
- **U-R9-1:** thin-deck fixture emits the `presentment-tripwire` WARNING
  with non-zero rule attribution.
- **U-R10-1:** serialized card key-set identical flag-ON vs flag-OFF.

### 3.2 Distributional — deck-eval replay (two-sided, §2 bands)

- **DB-1:** flag-OFF replay reproduces §2 baselines ±2pp (guards against a
  changed corpus/engine — the 6 commits since `d3fe3ac` make this
  non-optional).
- **DB-2:** flag-ON replay: every §2 band holds; served-card R1∪R2
  violation rate == 0 (one-sided by construction); mean deck size ≥ 80% of
  flag-OFF; insult rate ≤ flag-OFF; empty-deck < 5%.
- **DB-3:** D-055 bars asserted on the same run (R-11).
- **DB-4:** the R-12 pick-league replay, recorded in `status.md` with the
  chosen knob values.

### 3.3 Code-walk proof (D-056)

- **CW-1:** file:line-cited trace, committed to this folder, that every
  generator path — v3 organic, v3 sweetened, v2, consensus, relaxed,
  likes-you — passes through exactly its stated gate set (R-6, R-7, R-13).

### 3.4 Operator TestFlight checklist (runtime proof)

1. **#340:** main league, fairness toggle **OFF**, full deck swipe — no card
   whose value bar shows one side ≥ ~25% above the other (either direction).
2. **#341:** same swipe — no package sending 2 of a position without getting
   one back (check both sides of every multi-player card).
3. **#304:** on a league where your window is contender: no discovery-deck
   card whose headline acquisition plays behind your current starter at that
   position — *unless* the card also sends that starter away (tier-down
   consolidations are legitimate, B2); set a league to rebuild and confirm
   value-accumulation cards still appear; then run a **targeted** job (pin a
   player, or set acquire positions to a position you're stacked at) and
   confirm suggestions appear — the need gate must not apply there (R-5b).
4. **#336:** like a card, note it, then **force a regen** (pull-to-refresh
   next session) — R-4 binds at *generation time*, so a like placed after a
   job's snapshot will still show in the cached deck until regen
   (`_trade_job_is_fresh` reuse); the force-regen step is load-bearing, not
   ritual. After regen it must not reappear; open Matches → confirm no deck
   card duplicates a pending or accepted match; retract a like → that trade
   may reappear (expected, #318).
5. **#339:** on the pick-synced league only: no card where the other side's
   excess is explained by a 1st/2nd they're dumping; pick-sweetened
   near-fair offers should still exist.
6. **Tripwire read:** after the session, grep Render logs for
   `presentment-tripwire` — expect zero hits on healthy leagues; any hit
   goes to `status.md` with its rule attribution.

## 4. Guardrails

- D-055 bars are hard gates (R-11): insult < 3% with |Δ| ≥ 500, empty-deck
  < 5% — DB-2/DB-3 must pass before merge.
- Tripwire (R-9) ships with the feature, not after.
- Rollback ladder: knob (live, per-rule) → flag (one-line commit, group) —
  named in scope.md §2.
- Contender decks thin most (14.8% proxy kill) — intended per the operator
  (#304 is a contender complaint); watch the tripwire on contender-heavy
  leagues the first week.

## 5. Out of scope

- Likes-you **quality** rules (Q21 — R-4 dedup only).
- Client changes of any kind (mobile/web/extension untouched; G4 owns the
  #330 client surface).
- G4's files and the `/api/trades/generate` request surface (coordinate the
  `server.py` merge — disjoint functions, same file).
- Asset-ideas surface, manual calculator, eveners (lld §3).
- Fuzzy R-4 matching (Jaccard 2.3b) — follow-up.
- Any schema change; any new analytics event (waiver in scope.md §1).

## 6. For the operator / reconciliation

**Q-G6-1 — likes-you rule subset (planner's flag). Recommendation: confirm
the planned default.** Likes-you gets exactly one new rule: **R-4 dedup**.
It gets none of R-1/R-2/R-3/R-5. Why: Q21 exempts the surface from quality
filtering, and D-055 already ratified its quality mechanism (the −500
user-gain floor — "kill the insult, keep the surface"); but re-injecting an
already-matched trade at deck position 1 is precisely the #336 complaint,
and the injector already does past-decision dedup (`server.py:2957-2959`) —
extending that is bug fix, not new filtering.

**Cross-group (G4, #330) — ARBITRATED, final for this phase.** The
orchestrator adopted the round-1 critic's boundary, which replaces both the
author's provisional pin+scope line and G4's "no bypass" default: **R-5
applies only to untargeted discovery decks**; any targeted job —
`pinned_give`, `pinned_receive`, scoped `opponent_user_id`, or explicit
`acquire_positions` — bypasses R-5 (R-5b). The bypass flag is derived
server-side in `_run_trade_job` from job fields, never client-passable;
exact field list in lld §3. R-1/R-2/R-3 construction rules and R-4 dedup
apply to everything, targeted or not. Rationale trail: the author's dead-end
argument (an R-5 refusal on an explicit user action produces an
honest-empty state whose copy contradicts the user's stated intent, and G4
forbids silent relaxation) extended by the critic to *all* targeted shapes —
pin-only jobs and explicit `acquire_positions` hit the identical dead end,
and the codebase already treats explicit acquire as replacing inferred need
(`trade_service.py:3841`). The operator-visible asymmetry — a card
reachable via Offer/targeting but absent from the discovery deck — is
intended and explicable ("you asked for him" vs "we suggest what you
need"); one sentence on this goes in the build-phase DECISIONS.md entry.
**G4 coordination note:** G4's PRD assumed "no bypass" as its default — its
Dependencies section reconciles at build (orchestrator is notifying G4).

**Q-G6-3 — flag ship-state. Recommendation: launch ON** (`features.json`
`true` in the ship PR). These are tester-filed bugs against live behavior;
launching dark ships the fix to nobody and postpones the only measurement
that matters. The LAUNCHED_FLAG_DEFAULTS lesson (fail-open defaults for
launched features) points the same direction, though it is about client
flag-fetch failure and this flag is backend-only. Rollout step: merge with
flag ON **only after** DB-1/DB-2 pass and the code-walk proof is committed;
TestFlight checklist (§3.4) runs on the first build after deploy; knobs are
the live per-rule kill switches if the checklist finds a miss. Alternative
(staged: merge dark, flip after checklist) costs one extra deploy and leaves
live users on the buggy behavior meanwhile — only preferable if the operator
wants zero exposure before personally swiping a deck.

**Q-G6-2 — declined matches (carried from the plan). Recommendation: no
hard exclusion.** The 7-day dedup covers the immediate re-show; a
market-rejected trade regenerating weeks later is defensible and keeps R-4's
semantics clean ("blocked = currently live in your match pipeline").

**Recorded decisions for the build-phase DECISIONS.md entry (round-1 N4 +
arbitration):** (1) filter-not-reorder supersession (operator, batch-plan
§ G6); (2) the targeted-vs-untargeted R-5 boundary and its one-sentence
asymmetry rationale (above); (3) **R-5 judges on the consensus board**
(`seed_value`), not the user's raw board, even though #304's verbatim
complaint ranks on the user's board ("who I rank as TE3") — chosen because
shrunk user boards are noisy at low comparison counts and the corpus
measurement is consensus-based; the user-board variant is a named possible
follow-up, not an oversight; (4) unresolved-window users (fresh accounts,
`trade.outlook_seed` off) get **no** need gate — the `unresolved → PASS`
branch is deliberate fail-open, stated explicitly rather than left implicit.
