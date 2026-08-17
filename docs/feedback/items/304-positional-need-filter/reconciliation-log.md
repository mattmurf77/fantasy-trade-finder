# Reconciliation log — G6 review round 1

> Author's incorporation of [review-round-1.md](review-round-1.md)
> (3 BLOCKING, 8 NON-BLOCKING) plus the orchestrator's arbitration.
> Every objection → disposition → doc edit. New claims re-verified against
> `origin/main @ 2c67ea0` (tip moved again post-review; engine files
> `trade_service.py`/`trade_optimizer.py`/`database.py` untouched since
> `0b2dcee`, so all standing cites hold — lld §7).

## Orchestrator arbitration (recorded, final for this phase)

The critic's **targeted-vs-untargeted boundary replaces** the author's
provisional pin+scope boundary: R-5 applies only to untargeted discovery
decks; any targeted job (`pinned_give`, `pinned_receive`, scoped
`opponent_user_id`, explicit `acquire_positions`) bypasses R-5; the bypass
flag is **derived server-side in `_run_trade_job` from job fields, never
client-passable**; exact field list in lld §3 (per B3). R-1/R-2/R-3 and
R-4 apply to everything. G4's PRD assumed "no bypass" as its default — its
Dependencies section reconciles at build; the orchestrator notifies G4.
→ Docs: lld §3 (predicate + field list + exclusions), prd R-5/R-5b +
U-R5-B1..B5 + §6, hld §3 table + §5 + §7, scope §4/§waivers.

## Blocking

| # | Objection (short) | Disposition | Where |
|---|---|---|---|
| **B1** | R-3's one-sided predicate (`pick ≥ frac × gap`) kills fair pick-centerpiece consolidations — at defaults, any mid-1st on the heavier side of any gap ∈ [300, pick/0.8] dies, banning the operator's own stud-scaled consolidation style (2026-07-17 interview). Verified: gap 300, pick 3,000 → killed one-sided; U-R3-1..4 had no "large pick, small gap passes" case, so the suite would have green-lit it. | **ADOPTED** — two-sided same-knob band `frac×gap ≤ pick ≤ gap/frac`. Confirmed the #339 shape (gap 3,000, pick 3,000 ∈ [2,400, 3,750]) still dies and the centerpiece case (3,000 > 375) passes. Added U-R3-5 (the missing pass case) + band-edge case U-R3-6 + two named sabotages (with N6). **Re-audit of R-1/R-2 for the same class (coordinator ask):** R-1 is a pure ceiling on `gap/max(g,r)` — no upper-bound counterpart exists (a small relative gap is simply fair); R-2 uses `|net_P|`, symmetric by construction. Neither carries the B1 bug class; recorded in lld §3. | lld §3 R-3; prd R-3, §3.1 U-R3; hld §5 new row |
| **B2** | R-5's incumbent computed on the pre-trade roster includes players the card gives away — a contender's tier-down at a stacked position (give McBride, receive Loveland + 2nd) compares against the departing starter and dies; `tier_down` intent decks can empty wholesale (R-5 runs before the intent filter, `trade_service.py:2404` ✓). The Loveland fixture's give side is TE-free, so it never catches this. | **ADOPTED** — `user_P` computed over `roster − give_ids` (post-give). Added U-R5-10 (contender tier-down survives; sabotage: full-roster `user_P`), TF-3 amended ("unless the card also sends that starter away"). | lld §3 R-5; prd R-5, U-R5-10, TF-3; hld §5 |
| **B3** | The R-5 bypass surface was undefined in the LLD (build agents' only predicate source), and the pin+scope line failed its own rationale (pin-only jobs, explicit `acquire_positions` — which already *replaces* inferred need at `trade_service.py:3841` ✓ re-verified — and derivation ambiguity). | **ADOPTED via arbitration** (above). Field list + AND/OR semantics + explicit non-members (`trade_away_positions` alone; `trade_intent`) + "never client-passable" now in lld §3, with the likes-you injector's own targetedness skip cited as precedent. Per-branch tests U-R5-B1..B5 incl. the request-body-derivation sabotage. #156 Specific-Team (opponent scope, no pin): **in** the bypass — `opponent_user_id` is in the field list. | lld §3; prd R-5b, U-R5-B*, §6; hld §7 |

## Non-blocking

| # | Objection (short) | Disposition | Where |
|---|---|---|---|
| N1 | R-2 "per side" wording invites a gross-count misread (literal reading kills 2RB→2RB); exotic positions unstated. | **ADOPTED** — R-2 rewritten as signed net, one quantity per position, 2RB→2RB passes stated; K/DEF/IDP uncounted-by-design stated in both prd R-2 and lld §3. | prd R-2; lld §3 R-2 |
| N2 | Tripwire `pre_rule_count` unknowable at hook time (hooks precede feasibility/surplus/fairness); as pseudo-coded it blames presentment rules for fairness-thinned decks — false alarms rot the tripwire. | **ADOPTED** — attributable form `served < 5 AND served + Σkills(R1,R2,R3,R5) > 15`; hook placement unchanged (the near-miss guarantee needs it); rationale recorded in lld §5. | lld §5; prd R-9 unchanged in intent |
| N3 | Exclusion-set storage on a shared multi-league TradeService — "stored like `_past_decision_keys`" underdetermined; carry-over cross-league false-excludes identical asset sets. | **ADOPTED** — overwrite-per-call, `None` ⇒ empty set, never keep-previous; two-league test U-R4-7 (sabotage: accumulate). | lld §4; prd U-R4-7, R-4 |
| N4 | R-5's consensus-board choice (vs #304's verbatim user-board wording) and the unresolved-window fail-open should be recorded decisions, not implicit. | **ADOPTED** — both itemized in prd §6 "Recorded decisions" for the build-phase DECISIONS.md entry; user-board variant named as follow-up; consensus-vs-user-board also added to hld §5 alternatives table. | prd §6; hld §5; scope §4 |
| N5 | Base moved to `2c67ea0` (PR #133 touched `server.py`); `server.py` line cites drifted a third time — prefer symbol+anchor cites. | **ADOPTED** — re-verified @ `2c67ea0`: engine files untouched (diffstat), `_run_trade_job` still `:4773`, prefs resolution `:4840-4847`, `generate_trades` call `:4974-4975`; lld §7 now declares symbol+nearest-anchor as the contract for `server.py`, numbers as courtesy; build agents re-grep on their fork point. | lld §7; hld base note |
| N6 | U-R3 was the only test block with no named sabotage. | **ADOPTED** — two sabotages named ("lighter side's picks"; "drop the upper bound"), the second specifically failing on the B1 addition. | prd §3.1 U-R3 |
| N7 | R-4 cost: `load_awaiting_trades` is cross-league with per-league member fan-out — name the league-scoped variant as follow-up; TF-4 must state R-4 binds at generation (cached decks don't retro-filter). | **ADOPTED** — follow-up named in lld §4; TF-4 rewritten to make the force-regen step explicitly load-bearing (`_trade_job_is_fresh` reuse). | lld §4; prd TF-4 |
| N8 | DB-2 band-miss handling unstated. | **ADOPTED** — band miss = stop-and-report to operator, never silent knob-tuning; the L2 proxy-derived R-5 bands may need a report-and-re-ratify re-derivation on the first exact-counter replay (also noted: this round's B2/B3 changes shrink R-5's kill population, so a sub-floor reading takes the same re-ratify path with reason stated). | prd §2 |

## Rebuttals

None. All 11 objections adopted on merits; the only divergence from the
critic is procedural — B3's boundary was adopted through orchestrator
arbitration rather than author discretion, and is recorded as such above.

## Round-2 readiness

All BLOCKING items closed with predicate-level fixes; no change to the
two-part architecture, the flag/knob scheme, the measured baselines
(re-interpretation note in prd §2 only), or the G4 no-payload-change
contract. Remaining operator decisions: Q-G6-1, Q-G6-2, Q-G6-3 (scope §
waivers + prd §6).

## Post-sign-off amendments (2026-08-16, orchestrator-directed)

Source: the matchmaking-engine session's G6 validation verdict
(`docs/plans/matchmaking-engine/2026-08-16-g6-validation.md`), which found no
conflicts and requested two clarifying sentences before build merge:

1. **lld §5 tripwire:** `served` is the post-ghost count; ghost-withheld cards
   (suggestion.telemetry, `server.py:3629`) feed neither tripwire term; no
   band change (ghosts withhold after rules pass).
2. **lld §1 generator scope:** rules apply to the v1 construction path only;
   `trade_gen.v2` carries its own gates, no implicit inheritance; R4 rides the
   shared `past_decision_keys` kwarg (gen-v2 benefits automatically) and stays
   scoped matched/awaiting, never declined (Q-G6-2 + round-3 research
   cross-ref).

Documentation-only clarifications of existing behavior; no requirement, knob,
or contract change. Build note: main moved to `d6de017` + two matchmaking
squash merges — build agent must rebase (expect adjacent-insertion conflicts
in `_DEFAULT_CFG` tail + keep-both in 3 flag-parity fixtures).
