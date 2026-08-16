# HLD delta — Trade presentment rules (G6: #304, #336, #339, #340, #341)

> Author-round deliverable, 2026-08-16 feedback wave, group G6. Delta against
> [docs/architecture.md](../../../architecture.md) § "Request lifecycle (trade
> card — v2 engine)". Companion docs: [lld-delta.md](lld-delta.md) (exact
> interfaces), [prd.md](prd.md) (requirements + test plan),
> [scope.md](scope.md) (feature-gate scope block),
> [plan.md](plan.md) (Planner round), [batch-plan.md](batch-plan.md)
> (binding operator decisions).
>
> **Base note:** the Planner cited `origin/main @ d3fe3ac`; `origin/main` has
> since advanced 6 commits to `0b2dcee` (incl. `6f293f4` fit-congruence, which
> touched `trade_service.py`/`server.py`). Every cite in this doc set was
> re-verified against `0b2dcee` — the sha build branches will actually fork
> from. No Planner claim was invalidated; a handful of line numbers drifted
> by ≤3 lines and are corrected in the LLD. (Round-1 update: tip moved again
> to `2c67ea0` — engine files untouched; see lld §7.)

**The decision in ordinary words.** Today the engine can serve a trade no
human would accept (a 45% one-sided value gap survives even with fairness
"off"), a 2-RBs-for-2-WRs package that wrecks positional balance, an offer
whose headline player sits behind the user's current starter, and a trade the
user already liked or matched weeks ago. We add five presentment rules in two
layers — three "is this package sane?" rules that run *inside* the candidate
generators, and two "is this worth showing this user?" rules (a need gate in
the same generator hook, and a windowless already-matched exclusion applied at
dedup time). One feature flag reverts the whole group; each rule has its own
deploy-free knob.

---

## 1. Where the layer sits

### Current flow (architecture.md § trade-card lifecycle, verified @ `0b2dcee`)

```
/api/trades/generate → _run_trade_job (server.py:4773)
  prefs / outlooks / owned-pick injection
  → TradeService.generate_trades (trade_service.py:2286)
      → _generate_trades_v2 (:2957)
          per pair: v3 generate_pair_trades_v3 (trade_optimizer.py:193)
                    | v2 _generate_for_pair_v2 (trade_service.py:3367)
                    | consensus _generate_consensus_for_pair (:3791)
          [each generator: pinned → shape → positions → gap → #108 → #227
           → #141 → feasibility → surplus → fairness → (v3) sweetener]
      → _dedup_and_sort (:2492)  [7-day past-decision filter + sort]
      → _relaxed_targeted_pass (:2509)  [empty targeted jobs only]
      → intent filter (#172, :2404)
  → exploration split (F7) → likes-you injection (server.py:2872)
```

### Delta

```
          [each generator: … → #141 → ★ CONSTRUCTION RULES (R1 #340,
           R2 #341, R3 #339) + ★ NEED GATE (R5 #304) → feasibility →
           surplus → fairness → (v3) sweetener, ★ re-validated]
      → _dedup_and_sort  [7-day filter + ★ ELIGIBILITY EXCLUSION (R4 #336,
                          windowless awaiting/matched key set)]
      → likes-you injection  [★ R4 exclusion only — quality rules skipped
                              per Q21; D-055 user-gain floor unchanged]
```

Two genuinely new architectural facts, both small:

1. **A construction-rule hook** shared by all three generators (v3 loop, v2
   `_consider`, consensus `_emit`) and re-run inside the v3 sweetener pass.
   Everything else about generation — enumeration, scoring, ordering,
   `need_fit_weight` reordering (Q19) — is untouched.
2. **A per-job eligibility key set** built once in `_run_trade_job` from
   `trade_decisions` (awaiting likes, windowless) + `trade_matches`
   (pending/accepted), threaded into `generate_trades` and consumed at both
   presentment sites (`_dedup_and_sort` and the likes-you injector).

No new module, no schema change, no API/payload change (guarantee with
evidence in [lld-delta.md](lld-delta.md) §6).

## 2. Why construction-time hooks, not post-hoc deck filtering

This is the load-bearing design choice; it is what keeps the D-055 empty-deck
bar (<5%) satisfiable while killing 18.4% of currently-served first-5 cards.

- Each generator selects a **top-K per pair from a much larger enumeration**
  (v3 guarantees exact top-K within its pruned pools). A rule enforced inside
  the enumeration means a killed candidate's slot is **refilled** by the next
  candidate that today loses the heap race — the deck stays full, it just
  fills with sane trades.
- A post-hoc filter over the served deck would convert every kill into a
  hole: the measured worst case (5/108 decks losing all recorded organic
  first-5 cards) would be the *actual* outcome instead of a deliberately
  pessimistic upper bound.
- Precedent: this is exactly how #108, #227, and #141 already work — the
  rules join an existing gate stack rather than inventing a new stage.
- R4 (#336) is the exception and runs at presentment (`_dedup_and_sort`),
  because it is per-user duplicate state, not package quality: the same
  candidate is fine for tomorrow's job once the match resolves, and dedup
  must also cover streaming snapshots and the likes-you injector.

**Tripwire** (because stacked silent filters have zeroed decks before —
the G-046/G-047 compressed-board incident family): per-job per-rule kill
counters logged always; WARNING with rule attribution when a job's post-rule
deck is thin against a healthy pre-rule count. Shape in the LLD §5.

## 3. The two-part structure

| Part | Rules | Question | Where | Fires on |
|---|---|---|---|---|
| 1 — construction | R1 #340 overpay ceiling, R2 #341 per-position net cap, R3 #339 pick-is-the-gap | Is this package sane *at all*? | inside all three generators + sweetener re-validation | package shape/values only — user-independent |
| 2 — eligibility | R5 #304 need gate (window-scaled), R4 #336 matched/awaiting exclusion | Is this worth showing *this user*? | R5: same generator hook (needs refill too), **untargeted discovery decks only** (§7); R4: `_dedup_and_sort` + likes-you injector | user roster/window (R5); user decision/match state (R4) |

Part 1 predicates are evaluated on **raw summed consensus values**
(`seed_value` per side) — the same units as the D-055 |Δ| ≥ 500 materiality
floor and `likes_you_min_user_delta`, deliberately *not* the depth-discounted
`package_value_v2` numbers, so "insulting" is measured in the currency the
deck-quality bars were ratified in.

## 4. The likes-you carve-out (Q21 + Q-G6-1)

Likes-you injection (`server.py:2872`) stays **exempt from the quality rules**
(R1/R2/R3/R5) per the operator's Q21: a leaguemate's real like is market
information, and D-055 already gave the surface its own quality gate — the
`likes_you_min_user_delta` floor (default −500), which killed all 8 insulting
first-deck cards in the Phase A gate run while keeping 54/66 injections. That
floor precedent is exactly the posture we keep: *kill the insult, keep the
surface*.

R4 **does** apply to the injector (Q-G6-1, recommended yes): re-injecting an
already-matched trade as a likes-you card at deck position 1 *is* the #336
bug. The injector already practices this kind of dedup (its
`past_decision_keys` skip at `server.py:2957-2959`); extending it to the
windowless exclusion set is bug fix, not new filtering. Full reconciliation
note in [prd.md](prd.md) § For the operator.

## 5. Decisions and alternatives rejected

| Decision | Alternatives rejected, and why |
|---|---|
| **Filter, not reorder** (binding operator decision, batch-plan § G6 — supersedes the 2026-07-17 interview's "light multiplier" posture *for presentment*) | Heavier `need_fit_weight` / new penalty weights (Q19 closed this: a reorder still serves the horrid card, just later; testers see full decks); demote-to-bottom (same problem — the operator's complaint is that these cards exist at all). `need_fit_weight=0.15` reordering survives *underneath* the gate. |
| **Construction-time hooks with refill** | Post-hoc deck filter (§2 — converts kills into holes, fails the empty-deck bar); a separate "sanitizer" pipeline stage (new architecture for no benefit; the gate stacks exist). |
| **R1 reads raw sums and never `fairness_threshold`** | Raising `fairness_floor_divergence` (entangled with the ratified interview posture and the divergence/consensus split; a *ratio* floor also scales badly — 0.55 of a superstar package is a huge absolute gap while R1's frac+floor pair kills on materiality); making the mobile fairness toggle bypass-proof client-side (wrong layer — server must be authoritative). |
| **One group flag + 7 per-rule knobs** | Per-rule feature flags (flag proliferation; knobs already give per-rule deploy-free disable via `PUT /api/admin/config/<key>`); no flag (loses the instant byte-identical group revert). |
| **R4 windowless, exact-key, pending/accepted only** | Widening `since_days` on the existing 7-day filter (still a window — the bug is the window); fuzzy matching now (per-side Jaccard, 2.3b machinery — noted follow-up, not this wave); excluding `declined` matches too (Q-G6-2, recommended no — the 7-day dedup covers the immediate re-show, and a market-rejected trade regenerating weeks later is defensible). |
| **R5 primary-received-asset only, window-scaled, post-give incumbent, untargeted decks only** | Gating every received piece (guts 2-for-1s — secondary pieces are #141's domain); ignoring the window (operator: rebuilders accumulate value; a need gate on a rebuilder is wrong); a second outlook-resolution path (D-060's rejected-alternative lesson — reuse the resolved outlook object); pre-trade-roster incumbent (round-1 B2 — kills legitimate tier-down consolidations whose incumbent leaves in the same trade); applying R5 to targeted jobs (round-1 B3 + orchestrator arbitration — an R5 refusal on an explicit user ask is an inexplicable dead end; explicit acquire already replaces inferred need at `trade_service.py:3841`); the narrower pin+scope-only bypass (rejected in arbitration — pin-only and acquire-positions jobs hit the identical dead end). |
| **R3 two-sided band — the pick must *be* the gap, not merely exceed a fraction of it** | The one-sided floor form (round-1 B1 — collapses into "no material pick may ride the heavier side of any near-fair trade" and bans the operator's own stud-scaled pick-centerpiece consolidations); a second knob for the upper bound (same knob mirrored keeps the tuning surface at one number). |
| **R5 judges on consensus (`seed_value`), not the user's raw board** | User-board variant (named follow-up, round-1 N4 — closer to #304's verbatim wording but noisy at low comparison counts, and the corpus baselines are consensus-denominated). |
| **Part 1 + R5 are never relaxed** (#189 relaxed pass) | Letting the relaxed pass drop them (they are safety properties like #108, not taste; a "relaxed" horrid trade is still horrid). Targeted jobs may go honestly empty slightly more often — the #172/#189 honest-empty-state precedent covers the UX, and G4's operator decision independently mandates honest-empty for the Offer handoff. |

## 6. Interactions inherited from the plan (verified)

The Planner's interaction table (plan.md §3) was re-verified and stands:
fairness-OFF (threshold 0.5) cannot relax R1; sweeteners are players-only
(`trade_optimizer.py:239-241`) so a sweetener can never *introduce* an R3
violation but is re-validated for R1/R2; eveners (`server.py:992+`) add to
the lighter side by construction and are out of scope; pick pseudo-assets
(`_inject_owned_picks`, `server.py:9452`) flow through the generators and hit
Part 1 natively; retracted likes legitimately regenerate (#318,
`database.py:7090`).

## 7. Cross-group contract (G4)

G4's #330 Offer handoff consumes deck output client-side; G6 changes **no
payload field**, so the contract is untouched. The cross-group eligibility
question was **arbitrated by the orchestrator (round 1, final for this
phase)** at the boundary the critic drew: **R5 applies only to untargeted
discovery decks** — any targeted job (`pinned_give`, `pinned_receive`,
scoped `opponent_user_id`, explicit `acquire_positions`) bypasses R5, with
the bypass derived server-side in `_run_trade_job` and never
client-passable, so the request surface is unchanged. R1/R2/R3 and R4 apply
to every job. Field list and predicate in [lld-delta.md](lld-delta.md) §3;
rationale trail and the G4-PRD reconciliation note in [prd.md](prd.md) §6.
