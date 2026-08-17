# Review round 1 — Critic (Planner agent) on the G6 author docs

> Reviewing `hld-delta.md`, `lld-delta.md`, `prd.md` (R-1..R-13), `scope.md`
> against the plan, the binding operator decisions (batch-plan § G6), and
> `origin/main` (re-verified where load-bearing; note the tip has moved again —
> N5). Verdict up front: **the doc set is sound in structure and honest in its
> measurement claims** — construction-time hooks, two-sided bands with real
> numbers, the `_user_needs` coupling catch (U-R5-9), and the R-4 root-cause
> regression test are all right. Three objections are BLOCKING; all three have
> concrete fixes that don't disturb the architecture.

## BLOCKING

### B1 — R-3's predicate fires on near-fair trades where the pick is the centerpiece, not the excess

**Cite:** lld §3 R-3 (`KILL when gap ≥ pick_gap_min_value AND ∃ pick p ∈ H
with seed_value(p) ≥ pick_gap_frac × gap`); prd R-3, U-R3-1..4.

The predicate is one-sided. Counterexample at the shipped defaults
(frac 0.8, min 300): user gives player 1,000 + 2026 mid-1st 3,000 (side =
4,000), receives a 3,700 stud. `gap = 300 ≥ 300`; H = give side; pick
3,000 ≥ 0.8 × 300 = 240 → **KILLED**. The sides are within 8% — this is a
fair, ordinary pick-plus-player consolidation, and the pick is *not* "the
value difference" (removing it swings the trade 2,700 the other way). As
configured, any material pick on the heavier side of any trade with
`gap ∈ [300, pick/0.8]` dies — for a 3,000-value pick that is every gap from
300 to 3,750, i.e. R-3 collapses into "no mid-1st may ever ride the heavier
side," far beyond the #339 complaint ("that draft pick **is** the value
difference"), and beyond what R-1 leaves alive.

**Fix (same knob, two-sided band):** kill only when the pick and the gap are
within the band of each other —
`pick_gap_frac × gap ≤ seed_value(p) ≤ gap / pick_gap_frac`
(with `gap ≥ pick_gap_min_value`, pick ∈ H). The Loveland-class case (heavier
by exactly one mid-1st: gap 3,000, pick 3,000) still dies; the centerpiece
case above (gap 300, pick 3,000 > 375) passes.

**Test gap that hides this:** U-R3-1..4 contain no
"large pick, small gap → passes" case, so the suite as written would green-light
the overbroad predicate. Add it, and note U-R3 is also the only test block
with **no named sabotage** (see N6).

### B2 — R-5's incumbent is computed on the pre-trade roster, including players the card itself gives away

**Cite:** lld §3 R-5 (`user_P = user's consensus values at P sorted desc`,
`incumbent = user_P[S−1]`); prd R-5.

Nothing excludes the give side from `user_P`. Counterexample: contender gives
McBride (TE, incumbent starter) + gets back Loveland + a 2nd. Primary receive
= Loveland at TE; incumbent computed pre-trade = **McBride — who is leaving in
this very trade**. Loveland < McBride → no hole, no "upgrade" → KILL. But
post-trade Loveland *is* the starter; the card is a legitimate tier-down /
consolidation shape — precisely what the #172 `tier_down` intent mode exists
to find, and since R-5 runs at construction (before the post-gen intent
filter, `trade_service.py:2404`), a contender's `tier_down` deck at a stacked
position can empty wholesale. The Loveland acceptance fixture never catches
this because its give side is TE-free.

**Fix:** compute `user_P` over `roster − give_ids` (the post-give roster at
P). One-line change to the predicate inputs; add a test — "same-position
swap-down where the incumbent is in the give side passes for a contender
under `tier_down`" — with sabotage "compute user_P from the full roster."

### B3 — the R-5 bypass surface is undefined in the LLD, and the provisional pin+scope line is not the principled one

**Cite:** prd §6 (cross-group recommendation), hld §7; absent from lld §3
(the only place build agents read predicates from).

I **endorse the partial-bypass direction** — the author's dead-end argument
is correct and I revise my plan §3 posture accordingly: an R-5 refusal on an
explicit user action produces an honest-empty state whose copy ("no trades
found") directly contradicts the user's stated intent, and G4 rightly forbids
silent relaxation. R-1/R-2/R-3/R-4 continuing to apply is also right — a
package no human accepts is noise regardless of who asked, and a pinned job
resurfacing a live match is still #336.

But the adopted line — bypass **only** for pin+opponent-scope (#330's shape)
— fails its own rationale three ways:

1. **Pin-only jobs.** "What can I get for X?" (`pinned_give`, no opponent
   scope) and "get me this player" (`pinned_receive`) are equally explicit
   user direction. Under the provisional line they still get R-5-killed into
   the same inexplicable dead end the bypass exists to prevent.
2. **Explicit position targeting.** A contender with a strong TE room who
   explicitly sets `acquire_positions = [TE]` has every TE-primary card
   killed by R-5 → guaranteed empty targeted deck (#189 relax never relaxes
   R-5). The codebase already treats explicit acquire as *replacing* inferred
   need — the consensus generator substitutes `acquire_positions` for
   `position_needs` verbatim (`trade_service.py:3841`,
   `need_positions = list(acquire_positions) or …`). R-5 as specced would
   contradict that established semantic.
3. **Masquerade/derivation ambiguity.** "The job already knows it is
   pinned+scoped" — from which fields, combined how (`pinned_give` vs
   `pinned_receive` vs `pinned_give_mode` vs `opponent_user_id`, AND vs OR)?
   Is #156 Specific-Team (opponent scope, *no* pin) in or out? None of this
   is written where an implementer will look.

**Fix:** define the bypass in lld §3 as a server-derived predicate (computed
in `_run_trade_job` from job params — never a client-passable field, so no
request-surface change and no G4 contract impact):
`bypass_need_gate = bool(pinned_give or pinned_receive or acquire_positions or opponent_user_id)`
— i.e. **R-5 applies exactly to untargeted discovery decks**, the proactive
surface #304 complained about ("the need gate filters what we proactively
SHOW" — the author's own §6 sentence, followed to its conclusion). If the
orchestrator prefers a narrower carve-out, the minimum viable alternative is:
bypass when the gate-failing position was explicitly requested
(`P ∈ acquire_positions`) or the primary receive is pinned/targeted — but
then case 1's `pinned_give` dead end must be argued away explicitly. Either
way: the chosen predicate, its field list, and a test per branch
(U-R5-bypass-*) belong in the LLD/PRD before build. Note the operator-visible
inconsistency ("same trade visible via Offer but absent from the deck") is
fine and explicable — "you asked for him" vs "we suggest what you need" — and
should be one sentence in the DECISIONS.md entry.

## NON-BLOCKING

**N1 — PRD R-2 wording invites a gross-count misread.** "any position's
player-count net exceeds ±`pos_net_cap` (1) **per side**" — net is one signed
quantity per position, not a per-side count; a literal "per side" reading
kills 2RB→2RB (net 0). The lld §3 formula is correct and authoritative; fix
the R-2 sentence. Also state (one line) that positions outside
{QB, RB, WR, TE} (K/DEF/IDP in exotic leagues) are uncounted by design.

**N2 — tripwire `pre_rule_count` mis-attributes.** lld §5 defines it as
candidates that "passed everything except the new rules," but the hooks sit
*before* `_both_feasible`/surplus/fairness (lld §3 hook table), so that count
is unknowable at hook time; as pseudo-coded, a deck thinned by fairness fires
a WARNING blaming presentment rules — false alarms train everyone to ignore
the tripwire (G-047's "absence as evidence" family, inverted). Fix with the
attributable form: fire when `served < 5 AND served + Σ kills(R1,R2,R3,R5) > 15`
(the rules themselves account for the thinness), or move the hook after the
fairness gate for counting purposes — but then it must still precede the v3
near-miss collection, which the current placement exists to guarantee; the
counter change is the cheaper fix.

**N3 — exclusion-set storage semantics on a shared service.** lld §4 stores
`exclusion_keys` "like `self._past_decision_keys`" — but the TradeService
instance is per-session/per-format and serves **multiple leagues**
(`add_league`), while the exclusion set is built league-scoped per job. Spec
overwrite-per-call semantics: the `generate_trades` kwarg replaces the stored
set every call, and `None` ⇒ empty set (never "keep previous") — otherwise
league A's awaiting keys can false-exclude identical asset sets in league B
(same players roster across leagues), or a follow-up caller inherits stale
exclusions. One sentence + one test (two-league sequence).

**N4 — R-5's board choice should be a recorded decision.** #304's verbatim
complaint ranks on the *user's* board ("who **I rank** as TE3"); lld pins
`seed_value` (consensus). Consensus is defensible (shrunk boards are noisy at
low comparison counts; the corpus measurement is consensus-based) — but it is
a choice two engineers could reasonably make differently, so record it in the
DECISIONS.md entry with the user-board variant named as a possible follow-up.
Same section should state explicitly that unresolved-window users (fresh
accounts, `trade.outlook_seed` off) get **no** need gate — currently only
implicit in the `unresolved → PASS` branch.

**N5 — the base moved again.** `origin/main` is now `2c67ea0`; PR #133
(premium import) touched `server.py` (+40/−15) after the author's `0b2dcee`
verification pass. No G6-relevant semantics changed (diff is
rankings-import-scoped), but `server.py` line cites have drifted a third
time. Build agents fork from a fresh fetch per convention; DB-1 already
guards the corpus baseline. Suggest the LLD drop exact line numbers for
`server.py` in favor of symbol names + nearest-anchor cites in §7's style.

**N6 — U-R3 is the only test block with no named sabotage** (prd §3.1 names
sabotages for R-1/R-2/R-4/R-5/R-6). Add one — "evaluate the lighter side's
picks instead of H" — which also fails the B1 addition.

**N7 — R-4 cost + cache-staleness note.** `load_awaiting_trades` is
cross-league and fans out league-member fetches per job (`database.py:7058+`)
— acceptable at 500-row bounds, but a league-scoped variant is the obvious
later trim; name it a follow-up rather than silence. Also make TF-4's
wording explicit that R-4 binds at *generation*: a like placed after a job's
snapshot won't retro-filter the cached deck (`_trade_job_is_fresh` reuse) —
the checklist's "force regen" step is doing load-bearing work there.

**N8 — band-miss arbitration is unstated.** prd §2 declares the DB-2 bands
binding, but not what happens on a miss. State: a band miss (either side)
is **stop-and-report to the operator** — never silent knob-tuning until the
replay fits — and note the R-5 bands are proxy-derived (L2), so the first
exact-counter replay may legitimately need a band re-derivation, which is a
report-and-re-ratify event, not a failure.

## Verdict

Sound doc set; no invented objections beyond the above. BLOCKING: B1
(R-3 two-sided band + missing pass-case test), B2 (post-give incumbent),
B3 (bypass predicate into the LLD, drawn at targeted-vs-discovery). On the
orchestrator's provisional arbitration: **endorse partial bypass, reject the
pin+scope boundary** — the principled line its own rationale draws is
targeted vs. untargeted jobs (B3), and the codebase already encodes that
semantic at `trade_service.py:3841`. All three fixes are predicate/spec-level;
none disturb the two-part architecture, the flag/knob scheme, the measured
bands, or the G4 no-payload-change contract.

---

# ROUND 2: SIGNED OFF

All 11 round-1 dispositions verified present in the four docs' text, not just
the reconciliation log. B1: the two-sided band `frac×gap ≤ pick ≤ gap/frac` is
in lld §3 / prd R-3 with U-R3-5 (large-pick/small-gap pass case) and both
sabotages — arithmetic re-checked: the centerpiece consolidation (gap 300,
pick 3,000, band [240, 375]) now PASSES and the #339 shape (gap 3,000,
pick 3,000 ∈ [2,400, 3,750]) still dies. B2: `roster − give_ids` incumbent in
lld §3 / prd R-5 with U-R5-10 and the amended TF-3. B3: the bypass predicate
is in lld §3 as server-derived
`bool(pinned_give or pinned_receive or opponent_user_id or acquire_positions)`
with U-R5-B1..B5; on the coordinator's re-check, excluding
`trade_away_positions` is **right** — it is give-side intent while R-5 judges
the receive side, so an R-5-filtered deck doesn't contradict the user's stated
ask the way a pin does; the codebase anchor agrees (`trade_service.py:3841-3842`
maps acquire→user needs but trade_away→*opponent* needs), the residual
thin-deck risk is covered because trade_away jobs count as "targeted" for the
#189 relax (`trade_service.py:2398-2400`), and U-R5-B5 pins the choice so it
is deliberate and revertible by a one-field predicate edit. The R-1/R-2
one-sidedness re-audit is independently confirmed, not taken on faith: R-1's
missing counterpart would be a floor on *small* gaps, which are definitionally
fair, and R-2's `|net_P|` is symmetric by construction — neither carries the
B1 class. N1–N8 all verified in text (attributable tripwire
`served + Σkills > 15` in lld §5; overwrite-per-call + U-R4-7 two-league test;
band-miss arbitration in prd §2; recorded decisions in prd §6/scope §4).
One wording nit, not an objection: prd R-9's prose still says ">15 pre-rule
survivors" while lld §5's `served + rule_kills > 15` is the authoritative,
implementable form (same intent, slightly conservative toward firing; lld
governs and U-R9-1 tests it). No round-2 objections. The doc set is
build-ready pending the operator decisions already queued (Q-G6-1, Q-G6-2,
Q-G6-3).
