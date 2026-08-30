# Reconciliation log — FB-406 (dual-agent loop)

> Running record of arbitrations, provisional decisions, and critic outcomes for
> the G-406 polish path. Started by the Author agent, 2026-08-30. The critic round
> is explicitly invited to attack anything marked *provisional*.

## Round 1 — Orchestrator arbitrations of the plan's open questions (2026-08-30, PROVISIONAL)

Logged verbatim from the orchestrator's brief; the PRD is written to these. Status:
**orchestrator-provisional — critic round invited to attack.**

- **OQ-1 (default scope after #407):** "KEEP the first-opponent display default (the
  calculator's evaluate UX needs a roster to browse), do NOT default to 'Anyone'.
  Post-#407 an untouched default already searches all teams; the 'Anyone' row is the
  explicit, honest affordance on top. The dropdown label must not lie: when the
  partner is only the auto-default and unchosen, the UI should make clear the search
  is league-wide (exact copy/presentation is yours to spec within Chalkline)."
  → PRD: display default unchanged; honesty delivered as the R-4 scope-truth note.
- **OQ-2 (receive-side pool under Anyone):** "hint-only. No league-wide receive-side
  picker this round — that is scope creep past a polish item. Spec the hint line."
  → PRD R-6; league-wide pool listed in out-of-scope.
- **OQ-3 (deck targeting sheet 'Any team' row):** "OUT OF SCOPE — the deck sheet
  already has tap-again-to-clear. Note it as a possible follow-up in out-of-scope."
  → PRD out-of-scope list.

## Round 1 — Author-level decisions inside the arbitration space (2026-08-30, PROVISIONAL)

Decisions the plan/arbitrations left to the Author; each is fair game for the critic:

1. **`partnerChosen` state MIRROR rather than promoting `opponentChosenRef` to
   state** (PRD R-4). OQ-1's honesty mandate makes chosen-ness render, but FB-407
   shipped it as a ref ("nothing renders from it") and FB-407's structural
   assertions pin the ref's write sites. Chosen: keep the ref authoritative for the
   payload, add a same-initializer state written `true` on the adjacent line at the
   same two tap sites, pin the adjacency structurally (E-1 A-11). Rejected
   alternatives: (a) promote ref→state and rewrite FB-407's just-shipped
   assertions — churn on a concurrent item's fresh guard; (b) read the ref during
   render — works today only because the sheet path always re-renders via
   `setTeamPickerOpen(false)`, and is a React anti-pattern under concurrency.
   *Critic question: is the mirror's duplication acceptable vs. consolidating and
   updating the FB-407 pins in the same commit?*
2. **Scope-note placement and copy** (R-4): one conditional chalk-dim line under
   the action row, visible exactly when the payload would be partnerless
   ("Find a Trade searches all teams — pick a team to target one."), no
   scoped-state caption — the D-157 frame budget argues against an always-on line,
   and the unscoped states are the near-empty-canvas states where a line is cheap.
3. **Receive "Add player" under Anyone redirects to the team sheet** (R-6) instead
   of opening the empty player picker (dead end) or hiding the button (requires a
   `TradeSide` interface change — its `onAdd` is required). One branch at the call
   site.
4. **NB-1 accepted:** after a *scoped* search, choosing Anyone and searching
   remounts the canvas (host key includes `scopedOpponent`,
   `TradeBuildCanvas.tsx:168`) and the display reverts to the honest
   default-unchosen state (still league-wide, scope note back) rather than keeping
   the "Anyone" label. Fixing the display needs a host diff (planned zero) or a
   sentinel (banned). Documented in PRD §Known behavior.
   *Critic question: is display-reversion acceptable for ship, or does it warrant
   the TradesScreen thread-through?*
5. **Receive column `teamName` reads "any team" under Anyone** (R-3) — call-site
   ternary only.
6. **No new analytics property** for explicit-Anyone vs default-unchosen
   (scope.md §1) — taxonomy bright line; measurement deferred to an operator call.

## Round 2 — Critic ([review-round-2.md](review-round-2.md), 2026-08-30)

Verdict: 3 BLOCKING (B-1 wrong-runtime post-search narrative; B-2 token-presence
pin on the scope note; B-3 missing member-row reset guard), 6 NON-BLOCKING
(N-1…N-6). Rulings on the Author's four flagged items: mirror **accepted** (with
N-1 tightening; consolidation rejected), stale-verdict fix **confirmed real and
complete**, NB-1 **rejected as written** (acceptance survives, trace doesn't),
analytics waiver **accepted**. All three OQ arbitrations upheld on attack.

## Round 3 — Author incorporation (2026-08-30, final round before arbitration)

Every objection accepted; none rebutted. Dispositions:

| # | Disposition | Where |
|---|---|---|
| **B-1** | **Accepted, incorporated in full.** NB-1 rewritten around the browse session (seeding effect `TradesScreen.tsx:5811-5823` remounts the canvas as the fronted idea on every successful search; "Anyone" is a pre-search display by construction; session-end paths land honest default-unchosen; the key-remount trace now scoped to the zero-results case). E-4 rewritten against the pager UI (7 steps; counterparties verified by paging; the stale-verdict check moved to the pre-search route since the dropdown is session-locked; explicit pager-Clear vs canvas-Clear disambiguation). Code-walk extended to hops 11-13 tracing the seeding effect. | prd.md §NB-1, §E-4, §E-3 |
| **B-2** | **Accepted.** A-10 now pins the exact predicate text `partnerAny \|\| (!partnerChosen && receiveIds.length === 0)` (whitespace-normalized); two sabotages (S-10a anyone-only, S-10b `\|\|`→`&&` conjunction-flip) must both go red. | prd.md §E-1 A-10 |
| **B-3** | **Accepted.** New A-13 pins all four member-row onPress calls (`setPartnerAny(false)`, ref write, `setPartnerChosen(true)`, `setOpponentId`); sabotage S-13 "sticky-anyone". **Side effect:** this exposed round-1's over-claim that member rows are "byte-identical" — corrected in R-1 and the guardrails to "presentation byte-identical, onPress extended by exactly two writes" (verified `check-calc-partner-labels.js` pins label/summary construction only, so it stays green). | prd.md §E-1 A-13, R-1, §Guardrails |
| **N-1** | **Accepted.** A-11 window pinned at ±3 lines; new A-11b pins initializer **equality** between the ref and state declarations (post-R-10: both `!!initialOpponentId && !seededPrefill`); sabotage S-11b initializer-drift. The critic's residual (conditionally-wrapped adjacent pair passes both pins) is stated honestly in R-4. | prd.md R-4, §E-1 A-11 |
| **N-2** | **Accepted.** A-7 re-specced as: exactly one occurrence of the string `evalQ.data` in the file (the gated derivation). | prd.md §E-1 A-7 |
| **N-3** | **Accepted.** The false "CI runs the check-*.js suites" claim removed from PRD success-criterion 2 and scope.md §3/§5; both now state the suites gate nothing in CI and the build agent runs the full `mobile/tests` set explicitly pre-push, recorded in TEST_LEDGER. | prd.md §E-1 note + success criteria; scope.md §3, §5 |
| **N-4** | **Accepted.** Unknown-`initialOpponentId` edge documented in R-4 as a known one-sided edge (league-wide search unannounced; never the dangerous direction), with the reasoning for not adding an `!opponent` term. | prd.md R-4 |
| **N-5** | **Accepted.** The redirected-Add two-tap seam stated in R-6 so the TestFlight runner doesn't file it; also folded into E-4 step 2's expectation. | prd.md R-6, §E-4.2 |
| **N-6** | **Accepted.** A-8 marked best-effort with the real guards named (`tsc` + A-6/A-7 gating). | prd.md §E-1 A-8 |

### 407-QA-B-1 seed-prefill call — **(a) SPEC THE FIX** (new R-10, author-decided this round)

The orchestrator routed FB-407's Known limitation (browse-session seeding effect,
`TradesScreen.tsx:5811-5823`, auto-seeds the fronted idea's counterparty with no
tap; the remount initializes `opponentChosenRef` **true**; canvas action-row Clear
then leaves a scoped restart) to this build for an explicit call. **Decision:
fix it here (R-10), not defer.** Reasoning:

1. **It directly attacks this item's headline honesty**: Anyone search → results →
   canvas Clear → Find a Trade silently runs a single-team sweep — the exact
   silent-scope class #406/#407 exist to kill, reachable *from* the Anyone flow.
2. **The design-intent check says it is a bug, not intended #402 behavior**:
   in-session scoping to the browsed idea is carried by the FB-407
   `receiveIds.length > 0` clause (fair/model ideas are always two-sided), so
   marking the seed unchosen changes NOTHING while the idea is on the canvas;
   the ref only matters once the sides are emptied, and #402's own
   pass-exhaustion comment (`:5654-5657` — restore blank "so … Find a Trade
   honestly reads as the restart") defines an emptied canvas's search as an
   unscoped restart. FB-407's mini-prd names this exact fix shape as the
   intended follow-up.
3. **Surgical**: one optional `seeded?: boolean` on `CanvasPrefill`
   (`TradeBuildCanvas.tsx:59`), set only by the seeding write (`:5815`), one
   prop pass-through, one initializer term — pinned by new A-14/A-15 and
   TestFlight step 6. Tap/handoff prefill sites (`loadCanvasPrefill`,
   `loadSuggestion`, route params) stay chosen.
4. **Interaction with B-1 resolved jointly**: with R-10, the post-search
   state is coherent end to end — seeded idea = materially-scoped browse
   (honest), cleared canvas = league-wide restart with the R-4 note rendering
   (honest). Known corner accepted and documented in R-10: the note's "pick a
   team" clause is weak while the dropdown is session-locked.

Cost acknowledged: `TradesScreen.tsx` / `TradeBuildCanvas.tsx` move from
expected-zero-diff to one-line diffs each — amended through the declared channel
(the orchestrator's routing IS the plan-§8 declaration); R-5 and success
criteria updated. FB-407's follow-up closes on this ship (bookkeeping note in
`../407-finder-forced-team/status.md` at ship time).

**Nothing remains BLOCKING-ON-OPERATOR.** The only operator-routable question is
the deferred explicit-Anyone adoption measurement (scope.md §1), which the critic
agreed stays a routed decision, not a blocker.

## Round 3b — Critic's targeted verification of the R-10 material ([review-round-2.md](review-round-2.md) §Round 3) + final fixes (2026-08-30)

Critic verdict on round 3: incorporation of B-1…B-3/N-1…N-6 **confirmed
faithful**; R-10 mechanics, prefill-site classification, A-14/A-15 sabotage
audit, and all 7 E-4 steps **verified sound**; two new BLOCKING spec-text items
(B-4, B-5), no design change. Both **accepted and incorporated**; final round —
orchestrator verifies by diff.

| # | Disposition | Where |
|---|---|---|
| **B-4** | **Accepted.** R-10's twin initializer turns FB-407's shipped 20a red (`check-calc-merged-behavior.js:417-419` pins the old declaration verbatim). PRD now (i) declares the 20a re-spec explicitly — new regex matching the twin-initializer declaration, hint text extended with the seed exception, assertion kept two-sided — and states 20b/20b-bis/20c/20c-bis/20d need no edits (critic-verified); (ii) adds `check-calc-merged-behavior.js` to the diff set (success-criterion 2 pins its diff to exactly the 20a re-spec; scope.md §2 rollback + §3 guard bullet updated); (iii) adds the ordering line to R-1 and A-13: new member-row writes must keep the ref write within 20c-bis's ~200-char before-window. The R-4 "pins byte-identical" over-claim corrected to reference the declared re-spec. | prd.md R-10 (new bullet), R-1, §E-1 A-13, R-4, R-9, success criteria; scope.md §2, §3 |
| **B-5** | **Accepted.** (i) R-4's browse-state bullet rewritten: a seeded mount initializes `partnerChosen`/ref **false** per R-10 (the old text said true — a genuine contradiction two engineers would build differently from); the note is hidden on seeded mounts by the **receive term**, with non-seed prefills still initializing true. (ii) R-10's "always two-sided" claim qualified to *server-emitted* ideas (`trade_service.py:5849-5857`) with the edited-reseed vector stated (`TradesScreen.tsx:5813`, `:5817-5818` replay snapshots that can carry `receive: []`): a seeded give-only mount searches league-wide with the note rendering mid-session — explicitly folded into the already-accepted honest Clear corner. NB-1's matching sentence qualified the same way. | prd.md R-4 (browse bullet), R-10 (design-intent check), NB-1 |

No other text changed. **Nothing blocking-on-operator**; status unchanged
otherwise — ready for orchestrator diff-verification and arbitration.
